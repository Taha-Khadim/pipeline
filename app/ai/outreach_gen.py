"""
AI-powered outreach content generator (Google Gemini).

Produces personalized cold emails, call scripts, DMs and follow-ups based
on a lead's data, optional AI research, and any free-form context the
user adds on the outreach page (e.g. "I noticed they're hiring", "they
launched a new location").

Design notes:
  * Tries multiple Gemini models in order so that whichever model is
    available on the user's free quota will work (gemini-1.5-flash is the
    most universally available).
  * Falls back gracefully with a clear error message if the API key is
    missing or all models fail, so the UI can show what to fix.
"""

from __future__ import annotations

import json
import logging

from app.config import get_settings
from app.ai._gemini import gemini_json

log = logging.getLogger(__name__)


EMAIL_PROMPT = """\
You are an elite cold-email copywriter writing on behalf of {sender_name}, who runs \
{sender_business_blurb}.

Your job: write a SHORT, SHARP, attention-grabbing cold email to the owner of a small \
business so that they actually open, read, and reply. This email is being sent to a \
real business — be respectful, be specific, no spam tropes ("Hope this finds you well", \
"Quick question", "Just checking in" are BANNED).

# About the prospect
- Business: {business_name}
- Owner / contact: {owner_name}
- Industry: {industry}
- Location: {city}, {country}
- Address: {address}
- Has Website: {has_website}
- Website URL: {website_url}
- Website issues we've noticed: {website_issues}
- Google rating: {google_rating} ({google_reviews} reviews)
- Source: {source}

# AI research (use specifics from here)
{ai_research}

# Extra context from the sender (use this — it's the most important hook)
{user_context}

# How the email must be structured
1. SUBJECT — under 7 words, lower-case, sounds like a friend (NOT a marketer). \
   Reference something specific about THEM: their city, their name, their service, \
   or the hook above. No emojis. No clickbait.
2. OPENING LINE — one short sentence that proves we actually looked at them. \
   Reference something concrete: a Google review, the number of reviews they have, \
   the fact they don't have a website, a service they offer, the neighbourhood, etc.
3. PROBLEM / OBSERVATION — one or two sentences. Frame a *believable* gap a \
   {industry} in {city} probably has (e.g. losing customers because there's no \
   site to book on, missing online reviews, slow site, hard to find on phone).
4. SPECIFIC OFFER — one sentence. Concrete deliverable, not "we do websites". \
   Example pattern: "I'd put together a 1-page site for {business_name} so people \
   can book / order / contact you straight from Google — for free, just to show you \
   what it'd look like."
5. SOFT CTA — one sentence. Tiny ask: "Want me to send a mock-up?" or \
   "Worth a 10-minute chat next week?". No calendar links, no phone numbers.
6. SIGN-OFF — Just first name on its own line, then a single signature line: \
   {sender_signature_line}.

# Hard rules
- Plain text. NO markdown, NO bullet points in the body.
- Total body length: 70-130 words.
- Sound human, slightly casual, confident — not corporate, not pushy.
- Do NOT promise traffic or rankings. Do NOT say "boost", "synergy", "leverage", \
  "in today's digital age", "I hope this finds you well".
- Do NOT mention you're using AI or that you scraped data.
- It's fine to use the owner's first name only.
- If "Has Website" is False, your hook should center on that: they're losing \
  customers who Google them and find nothing.

Respond with ONLY valid JSON, no commentary, no code fences:
{{"subject": "...", "body": "..."}}
"""

CALL_SCRIPT_PROMPT = """\
Write a cold-call script for {sender_name} ({sender_business_blurb}) calling \
{business_name} in {city}.

# Lead
- Owner: {owner_name}
- Industry: {industry}
- Has website: {has_website}
- Website issues: {website_issues}
- Source: {source}

# Research
{ai_research}

# Custom context from sender
{user_context}

# Required structure
- opening: 2 sentences. Friendly, name them, mention how you found them.
- value_pitch: 2-3 sentences. Specific outcome a website would give them.
- cta: 1 sentence. Ask for a 5-minute follow-up or permission to send a free mock-up.
- objection_responses: a JSON object with these exact keys:
    "too expensive", "too busy", "word of mouth", "we already have a website"
  Each value is a 1-2 sentence reframe.

Respond with ONLY valid JSON, no code fences:
{{
  "opening": "...",
  "value_pitch": "...",
  "cta": "...",
  "objection_responses": {{
    "too expensive": "...",
    "too busy": "...",
    "word of mouth": "...",
    "we already have a website": "..."
  }}
}}
"""

DM_PROMPT = """\
Write a casual {channel} DM from {sender_name} ({sender_business_blurb}) to \
{business_name} ({industry}, {city}).

# Lead
- Owner: {owner_name}
- Has website: {has_website}

# Research
{ai_research}

# Custom context
{user_context}

# Rules
- 3-4 sentences max.
- Friendly, complimentary, specific.
- Soft ask: "mind if I send a quick idea?"
- No links unless asked. No emojis unless they fit naturally.

Respond with ONLY valid JSON: {{"message": "..."}}
"""

FOLLOWUP_PROMPT = """\
Write a follow-up email from {sender_name} for a lead who didn't respond.

# Lead
- Business: {business_name}
- Owner: {owner_name}
- Industry: {industry}, {city}
- Has website: {has_website}

# Previous outreach
{previous_outreach}

# Custom context
{user_context}

# Follow-up style: {followup_type}
- "case_study": share a brief, relevant before/after success story (1 short paragraph)
- "breakup": final follow-up, no pressure, leave the door open

# Rules
- Subject under 7 words.
- Body 70-110 words.
- Reference the original message indirectly.
- One soft CTA only.

Respond with ONLY valid JSON: {{"subject": "...", "body": "..."}}
"""


async def generate_outreach(
    lead_data: dict,
    outreach_type: str = "email",
    channel: str = "LinkedIn",
    followup_type: str = "case_study",
    previous_outreach: str = "",
    user_context: str = "",
) -> dict:
    """Generate a personalized outreach piece for ``lead_data``.

    Returns ``{"subject": "...", "body": "..."}`` for emails / followups,
    ``{"message": "..."}`` for DMs, the full call-script JSON for calls,
    or ``{"error": "..."}`` if anything fails.
    """
    settings = get_settings()
    if not settings.google_api_key:
        return {
            "error": (
                "Google Gemini API key is not set. Open the Settings page, "
                "paste your free key from https://aistudio.google.com/apikey, "
                "click Save, then come back."
            ),
        }

    ai_research = lead_data.get("ai_research") or {}
    if isinstance(ai_research, dict) and ai_research:
        ai_research_str = json.dumps(ai_research, indent=2)
    else:
        ai_research_str = "(no research yet — rely on the lead fields above)"

    sender_name = (settings.sender_name or "").strip() or "Your Name"
    sender_company = (settings.sender_company or "").strip()
    sender_website = (settings.sender_website or "").strip()
    sender_email = (settings.sender_email or "").strip()

    if sender_company and sender_website:
        sender_blurb = f"{sender_company} ({sender_website}) — small-business websites"
    elif sender_company:
        sender_blurb = f"{sender_company} — small-business websites"
    else:
        sender_blurb = "a small studio that builds websites for local businesses"

    sig_parts = [p for p in [sender_company, sender_website, sender_email] if p]
    sender_signature_line = " | ".join(sig_parts) if sig_parts else "(your contact info)"

    user_context_clean = (user_context or "").strip() or "(none provided — use the lead data above)"

    base_vars = {
        "business_name": lead_data.get("business_name") or "the business",
        "owner_name": lead_data.get("owner_name") or "there",
        "industry": lead_data.get("industry") or "small business",
        "city": lead_data.get("city") or "",
        "country": lead_data.get("country") or "",
        "address": lead_data.get("address") or "N/A",
        "has_website": lead_data.get("has_website", False),
        "website_url": lead_data.get("website_url") or "(no website)",
        "website_issues": lead_data.get("website_issues") or "N/A",
        "google_rating": lead_data.get("google_rating") or "N/A",
        "google_reviews": lead_data.get("google_reviews") or "N/A",
        "source": lead_data.get("source") or "Google Maps",
        "ai_research": ai_research_str,
        "user_context": user_context_clean,
        "sender_name": sender_name,
        "sender_business_blurb": sender_blurb,
        "sender_signature_line": sender_signature_line,
    }

    if outreach_type == "email":
        prompt = EMAIL_PROMPT.format(**base_vars)
    elif outreach_type == "call_script":
        prompt = CALL_SCRIPT_PROMPT.format(**base_vars)
    elif outreach_type == "dm":
        prompt = DM_PROMPT.format(channel=channel, **base_vars)
    elif outreach_type == "followup":
        prompt = FOLLOWUP_PROMPT.format(
            followup_type=followup_type,
            previous_outreach=previous_outreach or "(no previous outreach recorded)",
            **base_vars,
        )
    else:
        return {"error": f"Unknown outreach type: {outreach_type}"}

    return await gemini_json(prompt, settings.google_api_key, temperature=0.85)
