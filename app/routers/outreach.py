from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templating import templates
from app.models import Lead, OutreachLog, OutreachChannel, LeadStatus

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def outreach_page(request: Request, db: AsyncSession = Depends(get_db), lead_id: int | None = None):
    lead = None
    if lead_id:
        lead = await db.get(Lead, lead_id)

    result = await db.execute(
        select(Lead)
        .where(Lead.status.in_([LeadStatus.FOUND, LeadStatus.RESEARCHED, LeadStatus.CONTACTED]))
        .order_by(Lead.lead_score.desc().nulls_last(), Lead.created_at.desc())
        .limit(100)
    )
    leads = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "outreach.html",
        {
            "active_page": "outreach",
            "leads": leads,
            "selected_lead": lead,
            "channels": [c.value for c in OutreachChannel],
        },
    )


@router.post("/api/generate")
async def generate_outreach_content(request: Request, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import JSONResponse
    from app.ai.outreach_gen import generate_outreach
    from app.routers.leads import _lead_to_dict

    body = await request.json()
    lead_id = body.get("lead_id")
    outreach_type = body.get("type", "email")
    channel = body.get("channel", "LinkedIn")
    followup_type = body.get("followup_type", "case_study")
    user_context = body.get("context", "") or body.get("user_context", "")
    previous_outreach = body.get("previous_outreach", "")

    lead = await db.get(Lead, lead_id)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    lead_data = _lead_to_dict(lead)

    # If the user didn't supply previous-outreach text, auto-attach the most
    # recent logged message so the follow-up references something real.
    if outreach_type == "followup" and not previous_outreach:
        last = await db.execute(
            select(OutreachLog)
            .where(OutreachLog.lead_id == lead_id)
            .order_by(OutreachLog.sent_at.desc())
            .limit(1)
        )
        last_log = last.scalars().first()
        if last_log:
            previous_outreach = (
                f"Subject: {last_log.subject or '(none)'}\n\n{last_log.content}"
            )

    result = await generate_outreach(
        lead_data,
        outreach_type=outreach_type,
        channel=channel,
        followup_type=followup_type,
        previous_outreach=previous_outreach,
        user_context=user_context,
    )

    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(result, status_code=400)

    return result


@router.post("/api/log")
async def log_outreach(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    lead_id = body.get("lead_id")
    channel = body.get("channel", "EMAIL")
    subject = body.get("subject", "")
    content = body.get("content", "")

    lead = await db.get(Lead, lead_id)
    if not lead:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    log_entry = OutreachLog(
        lead_id=lead_id,
        channel=OutreachChannel(channel),
        subject=subject,
        content=content,
    )
    db.add(log_entry)

    if lead.status == LeadStatus.FOUND or lead.status == LeadStatus.RESEARCHED:
        lead.status = LeadStatus.CONTACTED
    lead.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return {"status": "logged", "id": log_entry.id}


@router.post("/api/research/{lead_id}")
async def research_lead_endpoint(
    lead_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    lead = await db.get(Lead, lead_id)
    if not lead:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    background_tasks.add_task(_research_lead_task, lead_id)
    return {"status": "researching"}


async def _research_lead_task(lead_id: int):
    from app.database import async_session
    from app.ai.research_agent import research_lead
    from app.routers.leads import _lead_to_dict

    async with async_session() as db:
        lead = await db.get(Lead, lead_id)
        if not lead:
            return

        lead_data = _lead_to_dict(lead)
        research = await research_lead(lead_data)

        lead.ai_research = research
        if "lead_score" in research:
            try:
                lead.lead_score = float(research["lead_score"])
            except (ValueError, TypeError):
                pass

        if lead.status == LeadStatus.FOUND:
            lead.status = LeadStatus.RESEARCHED

        lead.updated_at = datetime.now(timezone.utc)
        await db.commit()
        log.info("Research complete for lead %d", lead_id)
