"""
AI-powered lead research agent (Google Gemini).

Analyzes a lead's gathered data and produces actionable intelligence:
pain points, opportunities, recommended approach, and a lead-quality score.
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.ai._gemini import gemini_json

log = logging.getLogger(__name__)

RESEARCH_PROMPT = """\
You are a B2B sales-research analyst helping a freelance web-development \
agency identify high-value clients to pitch a new (or improved) website to.

Analyze this business lead and return ACTIONABLE intelligence for cold outreach.

## Business Data
- Name: {business_name}
- Industry: {industry}
- Category: {category}
- Location: {city}, {country}
- Has Website: {has_website}
- Website URL: {website_url}
- Website Quality Score: {website_quality_score}/10
- Website Issues: {website_issues}
- Google Rating: {google_rating} ({google_reviews} reviews)
- Phone: {phone}
- Emails: {emails}
- Social Links: {social_links}

## Required Analysis

1. **summary** — 2-3 sentences: what this business does and who they serve.
2. **pain_points** — 3-5 specific problems caused by no website / a weak \
website (industry-specific).
3. **opportunity** — what a great website would unlock for THIS business \
(bookings, portfolio, local SEO, lead capture, etc.).
4. **competitor_insight** — what their direct competitors typically have \
that they're missing.
5. **recommended_approach** — best outreach channel + tone + 2-3 talking \
points for first contact.
6. **lead_score** — integer 1-10. 10 = perfect fit (no website + active \
business + affordable industry + strong reviews).
7. **score_reasoning** — 1 sentence explaining the score.

Respond with ONLY valid JSON in this exact shape:
{{
  "summary": "...",
  "pain_points": ["...", "..."],
  "opportunity": "...",
  "competitor_insight": "...",
  "recommended_approach": "...",
  "lead_score": 8,
  "score_reasoning": "..."
}}
"""


async def research_lead(lead_data: dict) -> dict:
    """Run AI research on a lead using Google Gemini."""
    settings = get_settings()
    if not settings.google_api_key:
        return {
            "error": "Google Gemini API key not configured. "
                     "Add it via Settings page."
        }

    prompt = RESEARCH_PROMPT.format(
        business_name=lead_data.get("business_name", "Unknown"),
        industry=lead_data.get("industry", "Unknown"),
        category=lead_data.get("category", ""),
        city=lead_data.get("city", ""),
        country=lead_data.get("country", ""),
        has_website=lead_data.get("has_website", False),
        website_url=lead_data.get("website_url", "None"),
        website_quality_score=lead_data.get("website_quality_score", "N/A"),
        website_issues=lead_data.get("website_issues", "N/A"),
        google_rating=lead_data.get("google_rating", "N/A"),
        google_reviews=lead_data.get("google_reviews", "N/A"),
        phone=lead_data.get("phone", "N/A"),
        emails=lead_data.get("emails", "N/A"),
        social_links=lead_data.get("social_links", "N/A"),
    )

    return await gemini_json(prompt, settings.google_api_key, temperature=0.4)
