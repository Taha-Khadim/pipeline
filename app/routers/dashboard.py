from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templating import templates
from app.models import Lead, LeadStatus, OutreachLog, ScrapeJob

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count(Lead.id))) or 0
    no_website = await db.scalar(
        select(func.count(Lead.id)).where(Lead.has_website == False)
    ) or 0
    contacted = await db.scalar(
        select(func.count(Lead.id)).where(
            Lead.status.in_([
                LeadStatus.CONTACTED,
                LeadStatus.RESPONDED,
                LeadStatus.CALL_BOOKED,
                LeadStatus.PROPOSAL_SENT,
                LeadStatus.CLOSED_WON,
            ])
        )
    ) or 0
    responded = await db.scalar(
        select(func.count(Lead.id)).where(
            Lead.status.in_([
                LeadStatus.RESPONDED,
                LeadStatus.CALL_BOOKED,
                LeadStatus.PROPOSAL_SENT,
                LeadStatus.CLOSED_WON,
            ])
        )
    ) or 0
    closed_won = await db.scalar(
        select(func.count(Lead.id)).where(Lead.status == LeadStatus.CLOSED_WON)
    ) or 0
    total_outreach = await db.scalar(select(func.count(OutreachLog.id))) or 0

    response_rate = round((responded / contacted * 100), 1) if contacted else 0

    status_counts = {}
    for s in LeadStatus:
        c = await db.scalar(select(func.count(Lead.id)).where(Lead.status == s))
        status_counts[s.value] = c or 0

    recent_leads = (await db.execute(
        select(Lead).order_by(Lead.created_at.desc()).limit(5)
    )).scalars().all()

    top_industries_raw = (await db.execute(
        select(Lead.industry, func.count(Lead.id).label("cnt"))
        .group_by(Lead.industry)
        .order_by(func.count(Lead.id).desc())
        .limit(5)
    )).all()
    top_industries = [{"industry": row[0], "cnt": row[1]} for row in top_industries_raw]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_page": "dashboard",
            "total": total,
            "no_website": no_website,
            "contacted": contacted,
            "responded": responded,
            "closed_won": closed_won,
            "total_outreach": total_outreach,
            "response_rate": response_rate,
            "status_counts": status_counts,
            "recent_leads": recent_leads,
            "top_industries": top_industries,
        },
    )
