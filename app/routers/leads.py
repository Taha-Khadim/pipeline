from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templating import templates
from app.models import Lead, LeadStatus, OutreachLog

log = logging.getLogger(__name__)

router = APIRouter()

STATUSES = [s.value for s in LeadStatus]


@router.get("", response_class=HTMLResponse)
async def leads_page(request: Request):
    return templates.TemplateResponse(
        request,
        "leads.html",
        {"active_page": "leads", "statuses": STATUSES},
    )


@router.get("/api/list")
async def list_leads(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    industry: str | None = None,
    city: str | None = None,
    has_website: str | None = None,
    has_phone: str | None = None,
    has_email: str | None = None,
    q: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    limit: int = 500,
):
    query = select(Lead)

    if status:
        try:
            query = query.where(Lead.status == LeadStatus(status))
        except ValueError:
            pass
    if industry:
        query = query.where(Lead.industry == industry)
    if city:
        query = query.where(Lead.city.ilike(f"%{city}%"))
    if has_website == "false":
        query = query.where(Lead.has_website == False)
    elif has_website == "true":
        query = query.where(Lead.has_website == True)
    if has_phone == "true":
        query = query.where(Lead.phone.isnot(None), Lead.phone != "")
    elif has_phone == "false":
        query = query.where(or_(Lead.phone.is_(None), Lead.phone == ""))
    if has_email == "true":
        query = query.where(Lead.emails.isnot(None))
    elif has_email == "false":
        query = query.where(Lead.emails.is_(None))
    if q:
        query = query.where(
            or_(
                Lead.business_name.ilike(f"%{q}%"),
                Lead.owner_name.ilike(f"%{q}%"),
                Lead.city.ilike(f"%{q}%"),
            )
        )

    sort_col = getattr(Lead, sort, Lead.created_at)
    query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
    query = query.limit(min(max(limit, 1), 2000))

    result = await db.execute(query)
    leads = result.scalars().all()

    return [
        {
            "id": l.id,
            "business_name": l.business_name,
            "owner_name": l.owner_name,
            "industry": l.industry,
            "city": l.city,
            "country": l.country,
            "phone": l.phone,
            "emails": l.emails,
            "has_website": l.has_website,
            "website_url": l.website_url,
            "google_rating": l.google_rating,
            "google_reviews": l.google_reviews,
            "lead_score": l.lead_score,
            "status": l.status.value if l.status else "FOUND",
            "source": l.source,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in leads
    ]


@router.get("/api/stats")
async def lead_stats(db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count(Lead.id)))
    no_website = await db.scalar(select(func.count(Lead.id)).where(Lead.has_website == False))

    status_counts = {}
    for s in LeadStatus:
        count = await db.scalar(select(func.count(Lead.id)).where(Lead.status == s))
        status_counts[s.value] = count or 0

    industries = await db.execute(
        select(Lead.industry, func.count(Lead.id)).group_by(Lead.industry).order_by(func.count(Lead.id).desc()).limit(10)
    )

    return {
        "total": total or 0,
        "no_website": no_website or 0,
        "by_status": status_counts,
        "by_industry": {row[0]: row[1] for row in industries},
    }


@router.get("/api/{lead_id}")
async def get_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import JSONResponse
    lead = await db.get(Lead, lead_id)
    if not lead:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return _lead_to_dict(lead)


@router.put("/api/{lead_id}")
async def update_lead(lead_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import JSONResponse

    lead = await db.get(Lead, lead_id)
    if not lead:
        return JSONResponse({"error": "Not found"}, status_code=404)

    body = await request.json()

    if "status" in body:
        try:
            lead.status = LeadStatus(body["status"])
        except ValueError:
            return JSONResponse(
                {"error": f"Invalid status '{body['status']}'"}, status_code=400
            )

    for field in [
        "owner_name", "phone", "notes", "next_action",
        "website_url", "industry", "city", "country",
    ]:
        if field in body:
            setattr(lead, field, body[field])

    if "has_website" in body:
        lead.has_website = bool(body["has_website"])
    if "emails" in body:
        lead.emails = body["emails"] or None
    if "social_links" in body:
        lead.social_links = body["social_links"]

    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(lead)
    return {
        "status": "updated",
        "lead_status": lead.status.value if lead.status else None,
    }


@router.delete("/api/{lead_id}")
async def delete_lead(lead_id: int, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import JSONResponse
    from sqlalchemy import delete as sql_delete

    lead = await db.get(Lead, lead_id)
    if not lead:
        return JSONResponse({"error": "Not found"}, status_code=404)

    # Drop outreach history first so we don't hit FK constraint failures
    # in environments where cascade isn't enforced at the DB level.
    await db.execute(sql_delete(OutreachLog).where(OutreachLog.lead_id == lead_id))
    await db.delete(lead)
    await db.commit()
    log.info("Deleted lead %d (%s)", lead_id, lead.business_name)
    return {"status": "deleted", "id": lead_id}


@router.post("/api/bulk-delete")
async def bulk_delete(request: Request, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete as sql_delete

    body = await request.json()
    lead_ids = body.get("lead_ids") or []
    if not lead_ids:
        return {"status": "noop", "deleted": 0}

    await db.execute(sql_delete(OutreachLog).where(OutreachLog.lead_id.in_(lead_ids)))
    await db.execute(sql_delete(Lead).where(Lead.id.in_(lead_ids)))
    await db.commit()
    log.info("Bulk-deleted %d leads", len(lead_ids))
    return {"status": "deleted", "deleted": len(lead_ids)}


@router.post("/api/{lead_id}/enrich")
async def enrich_lead(
    lead_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import JSONResponse
    lead = await db.get(Lead, lead_id)
    if not lead:
        return JSONResponse({"error": "Not found"}, status_code=404)
    background_tasks.add_task(_enrich_lead_task, lead_id)
    return {"status": "enriching"}


async def _enrich_lead_task(lead_id: int):
    from app.database import async_session
    from app.scrapers.contact_finder import enrich_contact
    from app.scrapers.website_analyzer import analyze_website

    async with async_session() as db:
        lead = await db.get(Lead, lead_id)
        if not lead:
            return

        contact = await enrich_contact(
            website_url=lead.website_url,
            business_name=lead.business_name,
            existing_phone=lead.phone,
            city=lead.city,
        )

        merged_emails = list(contact.emails)
        for guess in contact.guessed_emails:
            if guess not in merged_emails:
                merged_emails.append(guess + "  (guess)")
        if merged_emails:
            lead.emails = merged_emails
        if contact.phones and not lead.phone:
            lead.phone = contact.phones[0]
        if contact.social_links:
            lead.social_links = contact.social_links
        if contact.owner_name:
            lead.owner_name = contact.owner_name

        if lead.website_url and lead.has_website:
            analysis = await analyze_website(
                lead.website_url,
                take_screenshot=True,
                lead_id=lead.id,
            )
            lead.website_quality_score = analysis.quality_score
            lead.website_issues = analysis.issues
            lead.screenshot_path = analysis.screenshot_path

        lead.updated_at = datetime.now(timezone.utc)
        await db.commit()
        log.info("Enriched lead %d: %s", lead_id, lead.business_name)


@router.post("/api/bulk-enrich")
async def bulk_enrich(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    lead_ids = body.get("lead_ids", [])
    for lid in lead_ids:
        background_tasks.add_task(_enrich_lead_task, lid)
    return {"status": "enriching", "count": len(lead_ids)}


@router.get("/{lead_id}", response_class=HTMLResponse)
async def lead_detail_page(lead_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    lead = await db.get(Lead, lead_id)
    if not lead:
        return HTMLResponse("<h1>Lead not found</h1>", status_code=404)

    result = await db.execute(
        select(OutreachLog).where(OutreachLog.lead_id == lead_id).order_by(OutreachLog.sent_at.desc())
    )
    outreach_logs = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "lead_detail.html",
        {
            "active_page": "leads",
            "lead": lead,
            "outreach_logs": outreach_logs,
            "statuses": STATUSES,
        },
    )


def _lead_to_dict(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "business_name": lead.business_name,
        "owner_name": lead.owner_name,
        "industry": lead.industry,
        "category": lead.category,
        "address": lead.address,
        "city": lead.city,
        "country": lead.country,
        "phone": lead.phone,
        "emails": lead.emails,
        "website_url": lead.website_url,
        "has_website": lead.has_website,
        "google_maps_url": lead.google_maps_url,
        "google_rating": lead.google_rating,
        "google_reviews": lead.google_reviews,
        "social_links": lead.social_links,
        "website_quality_score": lead.website_quality_score,
        "website_issues": lead.website_issues,
        "screenshot_path": lead.screenshot_path,
        "lead_score": lead.lead_score,
        "ai_research": lead.ai_research,
        "status": lead.status.value if lead.status else "FOUND",
        "source": lead.source,
        "notes": lead.notes,
        "next_action": lead.next_action,
        "next_action_date": lead.next_action_date.isoformat() if lead.next_action_date else None,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
    }
