from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.templating import templates
from app.database import get_db
from app.models import Lead, ScrapeJob, ScrapeJobStatus

log = logging.getLogger(__name__)

router = APIRouter()

ALL_SOURCES = ["openstreetmap", "google_maps", "yelp"]


@router.get("", response_class=HTMLResponse)
async def discover_page(request: Request):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "discover.html",
        {
            "active_page": "discover",
            "industries": settings.target_industries,
            "countries": settings.target_countries,
            "cities_by_country": settings.cities_by_country,
            "sources": ALL_SOURCES,
        },
    )


@router.get("/cities/{country}")
async def get_cities(country: str):
    """Return suggested cities for a given country."""
    settings = get_settings()
    return {"cities": settings.cities_by_country.get(country, [])}


async def _run_scrape(
    job_id: int, industry: str, city: str, country: str, sources: list[str]
):
    """Background task that runs scrapers from multiple sources in parallel."""
    from app.database import async_session
    from app.scrapers.google_maps import scrape_google_maps
    from app.scrapers.yelp import scrape_yelp
    from app.scrapers.yellowpages import scrape_yellowpages
    from app.scrapers.openstreetmap import scrape_openstreetmap

    async with async_session() as db:
        job = await db.get(ScrapeJob, job_id)
        if not job:
            return
        job.status = ScrapeJobStatus.RUNNING
        await db.commit()

        try:
            async def _wrap(name: str, coro):
                try:
                    res = await coro
                    return name, res
                except Exception as exc:
                    log.error("%s scraper failed: %s", name, exc)
                    return name, exc

            tasks: list[asyncio.Task] = []
            if "openstreetmap" in sources:
                tasks.append(asyncio.create_task(_wrap("OpenStreetMap",
                    scrape_openstreetmap(industry, city, country, max_results=80))))
            if "yelp" in sources:
                tasks.append(asyncio.create_task(_wrap("Bing Maps",
                    scrape_yelp(industry, city, country, max_results=30))))
            if "google_maps" in sources:
                tasks.append(asyncio.create_task(_wrap("Google Maps",
                    scrape_google_maps(industry, city, country, max_results=30))))
            if "yellowpages" in sources:
                tasks.append(asyncio.create_task(_wrap("Yellow Pages",
                    scrape_yellowpages(industry, city, country, max_results=30))))

            if not tasks:
                tasks.append(asyncio.create_task(_wrap("OpenStreetMap",
                    scrape_openstreetmap(industry, city, country, max_results=80))))
                tasks.append(asyncio.create_task(_wrap("Google Maps",
                    scrape_google_maps(industry, city, country, max_results=30))))

            source_label = ", ".join({"openstreetmap": "OpenStreetMap",
                                       "yelp": "Bing Maps",
                                       "google_maps": "Google Maps",
                                       "yellowpages": "Yellow Pages"}.get(s, s)
                                      for s in sources) or "All sources"

            # Persist leads progressively as each scraper finishes so the UI
            # does not stay on "0 leads" while a slow scraper (Google Maps)
            # is still enriching results.
            existing_leads: dict[str, Lead] = {}
            existing_q = await db.execute(
                select(Lead).where(Lead.city == city, Lead.industry == industry)
            )
            for l in existing_q.scalars().all():
                existing_leads[(l.business_name or "").lower()] = l

            created = 0

            def _has_contact(biz: dict) -> bool:
                """A lead is worth keeping only if we can reach the business."""
                return bool(
                    (biz.get("phone") or "").strip()
                    or (biz.get("email") or "").strip()
                    or (biz.get("website_url") or "").strip()
                )

            async def _persist(source_name: str, businesses: list[dict]):
                nonlocal created
                skipped_no_contact = 0
                for biz in businesses:
                    name = (biz.get("name") or "").strip()
                    if not name:
                        continue
                    key = name.lower()
                    if key in existing_leads:
                        # Same business from a different source — fill gaps
                        # even if this entry alone has no contact info, since
                        # the existing record is already kept.
                        lead = existing_leads[key]
                        if not lead.phone and biz.get("phone"):
                            lead.phone = biz["phone"]
                        if not lead.website_url and biz.get("website_url"):
                            lead.website_url = biz["website_url"]
                            lead.has_website = True
                        if not lead.address and biz.get("address"):
                            lead.address = biz["address"]
                        if not lead.category and biz.get("category"):
                            lead.category = biz["category"]
                        if not lead.google_rating and biz.get("google_rating"):
                            lead.google_rating = biz["google_rating"]
                        if not lead.google_reviews and biz.get("google_reviews"):
                            lead.google_reviews = biz["google_reviews"]
                        if biz.get("email"):
                            cur = lead.emails or []
                            if biz["email"] not in cur:
                                lead.emails = cur + [biz["email"]]
                        continue

                    if not _has_contact(biz):
                        skipped_no_contact += 1
                        continue

                    emails_payload = [biz["email"]] if biz.get("email") else None
                    lead = Lead(
                        business_name=name,
                        industry=industry,
                        category=biz.get("category", ""),
                        address=biz.get("address", ""),
                        city=biz.get("city") or city,
                        country=biz.get("country") or country,
                        phone=biz.get("phone", ""),
                        emails=emails_payload,
                        website_url=biz.get("website_url", ""),
                        has_website=biz.get("has_website", False),
                        google_maps_url=biz.get("google_maps_url", ""),
                        google_rating=biz.get("google_rating"),
                        google_reviews=biz.get("google_reviews"),
                        source=f"{source_name}: {industry} in {city}",
                    )
                    db.add(lead)
                    existing_leads[key] = lead
                    created += 1
                await db.commit()
                job.results_count = created
                await db.commit()
                if skipped_no_contact:
                    log.info(
                        "%s: skipped %d leads with no phone / email / website",
                        source_name, skipped_no_contact,
                    )

            for fut in asyncio.as_completed(tasks):
                source_name, result = await fut
                if isinstance(result, Exception):
                    continue
                if isinstance(result, list):
                    log.info("%s returned %d businesses", source_name, len(result))
                    await _persist(source_name, result)

            job.status = ScrapeJobStatus.COMPLETED
            job.results_count = created
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            log.info(
                "Scrape job %d complete: %d new leads from %s",
                job_id, created, source_label,
            )

        except Exception as exc:
            log.error("Scrape job %d failed: %s", job_id, exc)
            job.status = ScrapeJobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()


@router.post("/start")
async def start_scrape(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    industry = body.get("industry", "").strip()
    city = body.get("city", "").strip()
    country = body.get("country", "").strip()
    sources = body.get("sources", ALL_SOURCES)

    if not industry or not city or not country:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"error": "Industry, city, and country are required"}, status_code=400
        )

    if not isinstance(sources, list) or not sources:
        sources = ALL_SOURCES

    source_label = " + ".join(sources)
    job = ScrapeJob(
        query=f"{industry} in {city}, {country} [{source_label}]",
        industry=industry,
        city=city,
        country=country,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_run_scrape, job.id, industry, city, country, sources)

    return {"job_id": job.id, "status": "started"}


@router.get("/job/{job_id}")
async def get_job_status(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Job not found"}, status_code=404)

    leads = []
    if job.status in (ScrapeJobStatus.COMPLETED, ScrapeJobStatus.RUNNING):
        query = (
            select(Lead)
            .where(Lead.industry == job.industry, Lead.city == job.city)
            .order_by(Lead.id.desc())
        )
        result = await db.execute(query)
        leads = [
            {
                "id": l.id,
                "business_name": l.business_name,
                "category": l.category,
                "phone": l.phone,
                "website_url": l.website_url,
                "has_website": l.has_website,
                "google_rating": l.google_rating,
                "google_reviews": l.google_reviews,
                "address": l.address,
                "source": l.source,
            }
            for l in result.scalars().all()
        ]

    return {
        "job_id": job.id,
        "status": job.status.value,
        "results_count": job.results_count,
        "error_message": job.error_message,
        "leads": leads,
    }


@router.get("/recent-jobs")
async def recent_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScrapeJob).order_by(ScrapeJob.id.desc()).limit(10)
    )
    jobs = result.scalars().all()
    return [
        {
            "id": j.id,
            "query": j.query,
            "status": j.status.value,
            "results_count": j.results_count,
            "started_at": j.started_at.isoformat() if j.started_at else None,
        }
        for j in jobs
    ]
