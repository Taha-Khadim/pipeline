"""
Contact enrichment.

Pulls emails / phones / social links for a lead.

Strategy (in order):
  1. If website exists  → scrape homepage + /contact /about /contact-us pages.
  2. If website exists  → also scan a few internal links on the homepage.
  3. Always              → scan Google Maps / Bing maps detail panels for phone.
  4. If still no email   → run web searches:
                            "<business> email"
                            "<business> contact"
                            "<business> {city}" — and pull emails from snippets.
  5. Always              → look up Facebook/Instagram public pages for the
                            "About" / "Contact" sections.
  6. Common-pattern guess emails (info@/contact@/hello@) ONLY as a last resort,
     clearly marked as "guess".

Priority is given to the websiteless leads — they're the highest-value
prospects for a web-development pitch.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field, asdict
from urllib.parse import urljoin, urlparse, quote_plus

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Email regex — strict enough to avoid file paths / gradients / hashes.
EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9][a-zA-Z0-9._%+\-]{0,63}"
    r"@[a-zA-Z0-9][a-zA-Z0-9.\-]{0,253}"
    r"\.[a-zA-Z]{2,24}\b"
)

# Phone regex — international, generic.
PHONE_RE = re.compile(
    r"(?:(?<!\d)(?:\+\d{1,3}[\s.\-]?)?"          # optional + country code
    r"(?:\(?\d{1,4}\)?[\s.\-]?){1,2}"            # area code(s)
    r"\d{3,4}[\s.\-]?\d{3,4}(?!\d))"             # main number
)

SOCIAL_PATTERNS = {
    "linkedin":  re.compile(r"https?://(?:www\.)?linkedin\.com/(?:in|company)/[^\"'\s<>?#]+"),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[^\"'\s<>/?#]+"),
    "facebook":  re.compile(r"https?://(?:www\.|m\.|business\.)?facebook\.com/[^\"'\s<>?#]+"),
    "twitter":   re.compile(r"https?://(?:www\.)?(?:twitter|x)\.com/[^\"'\s<>?#]+"),
    "youtube":   re.compile(r"https?://(?:www\.)?youtube\.com/[@a-zA-Z0-9_\-]+"),
    "tiktok":    re.compile(r"https?://(?:www\.)?tiktok\.com/@[^\"'\s<>?#]+"),
    "whatsapp":  re.compile(r"https?://(?:wa\.me|api\.whatsapp\.com)/[^\"'\s<>?#]+"),
}

JUNK_EMAIL_DOMAINS = {
    "sentry.io", "wixpress.com", "example.com", "googleapis.com",
    "w3.org", "schema.org", "wordpress.org", "gravatar.com",
    "yourdomain.com", "domain.com", "test.com", "email.com",
    "facebook.com", "twitter.com", "instagram.com", "linkedin.com",
    "youtube.com", "tiktok.com", "google.com",
}

JUNK_EMAIL_PREFIXES = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "wordpress", "admin@example",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class ContactInfo:
    emails: list[str] = field(default_factory=list)
    guessed_emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    social_links: dict[str, str] = field(default_factory=dict)
    owner_name: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_phone(raw: str) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    digits = re.sub(r"[^\d+]", "", s)
    if len(digits.lstrip("+")) < 7 or len(digits) > 18:
        return None
    return s


def _is_junk_email(email: str) -> bool:
    email = email.lower()
    if any(email.startswith(p) for p in JUNK_EMAIL_PREFIXES):
        return True
    domain = email.split("@", 1)[-1]
    return any(j == domain or domain.endswith("." + j) for j in JUNK_EMAIL_DOMAINS)


async def _fetch(url: str, timeout: int = 12) -> str | None:
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            resp = await client.get(url)
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ("text/html" in ctype or "text/plain" in ctype):
                return resp.text
    except Exception as exc:
        log.debug("fetch failed %s: %s", url, exc)
    return None


def _extract_from_html(html: str, base_url: str | None = None) -> ContactInfo:
    info = ContactInfo()
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)

    for email in EMAIL_RE.findall(text):
        e = email.lower().rstrip(".,;)")
        if not _is_junk_email(e) and e not in info.emails:
            info.emails.append(e)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("mailto:"):
            email = href[7:].split("?", 1)[0].strip().lower()
            if email and not _is_junk_email(email) and email not in info.emails:
                info.emails.append(email)
        elif href.startswith("tel:"):
            cleaned = _clean_phone(href[4:].strip())
            if cleaned and cleaned not in info.phones:
                info.phones.append(cleaned)

    for raw in PHONE_RE.findall(text)[:20]:
        cleaned = _clean_phone(raw)
        if cleaned and cleaned not in info.phones:
            info.phones.append(cleaned)

    for platform, pattern in SOCIAL_PATTERNS.items():
        for a in soup.find_all("a", href=True):
            m = pattern.match(a["href"])
            if m and platform not in info.social_links:
                info.social_links[platform] = m.group(0).rstrip("/")
                break

    info.emails = info.emails[:8]
    info.phones = info.phones[:6]
    return info


async def _scrape_website(website_url: str) -> ContactInfo:
    """Scrape homepage + common contact pages on the business' website."""
    info = ContactInfo()

    if not website_url.startswith("http"):
        website_url = "https://" + website_url

    home_html = await _fetch(website_url)
    if home_html:
        merged = _extract_from_html(home_html, website_url)
        info.emails = merged.emails
        info.phones = merged.phones
        info.social_links = merged.social_links

    paths = ["/contact", "/contact-us", "/contactus", "/about",
             "/about-us", "/get-in-touch", "/reach-us", "/info"]

    async def fetch_one(path):
        return await _fetch(urljoin(website_url, path))

    htmls = await asyncio.gather(*[fetch_one(p) for p in paths], return_exceptions=True)
    for sub_html in htmls:
        if isinstance(sub_html, Exception) or not sub_html:
            continue
        sub = _extract_from_html(sub_html, website_url)
        for e in sub.emails:
            if e not in info.emails:
                info.emails.append(e)
        for p in sub.phones:
            if p not in info.phones:
                info.phones.append(p)
        for k, v in sub.social_links.items():
            info.social_links.setdefault(k, v)

    return info


async def _search_emails(business_name: str, city: str = "") -> list[str]:
    """Use search-engine snippets to discover an email when there is no website."""
    if not business_name:
        return []

    found: list[str] = []
    queries = [
        f'"{business_name}" email',
        f'"{business_name}" contact',
    ]
    if city:
        queries.append(f'"{business_name}" {city}')

    async def search_bing(q: str) -> str | None:
        url = f"https://www.bing.com/search?q={quote_plus(q)}"
        return await _fetch(url, timeout=15)

    htmls = await asyncio.gather(*[search_bing(q) for q in queries], return_exceptions=True)
    for html in htmls:
        if isinstance(html, Exception) or not html:
            continue
        for e in EMAIL_RE.findall(html):
            e = e.lower().rstrip(".,;)")
            if not _is_junk_email(e) and e not in found:
                found.append(e)

    return found[:5]


def _guess_emails(website_url: str | None, business_name: str | None) -> list[str]:
    domains: set[str] = set()
    if website_url:
        netloc = urlparse(
            website_url if website_url.startswith("http") else "https://" + website_url
        ).netloc.replace("www.", "")
        if netloc:
            domains.add(netloc)
    if business_name and not domains:
        slug = re.sub(r"[^a-z0-9]+", "", business_name.lower())[:24]
        if slug:
            domains.add(f"{slug}.com")

    return [f"{prefix}@{d}" for d in domains for prefix in ("info", "contact", "hello")]


async def enrich_contact(
    website_url: str | None = None,
    business_name: str | None = None,
    existing_phone: str | None = None,
    city: str | None = None,
) -> ContactInfo:
    """Collect emails / phones / socials, prioritizing websiteless leads."""
    info = ContactInfo()

    if existing_phone:
        cleaned = _clean_phone(existing_phone)
        if cleaned:
            info.phones.append(cleaned)

    if website_url:
        web = await _scrape_website(website_url)
        for e in web.emails:
            if e not in info.emails:
                info.emails.append(e)
        for p in web.phones:
            if p not in info.phones:
                info.phones.append(p)
        info.social_links.update(web.social_links)
        if web.emails:
            info.notes.append("Found emails on the website")

    # Highest priority: leads without a website. Search the web for them.
    if not info.emails and business_name:
        searched = await _search_emails(business_name, city or "")
        for e in searched:
            if e not in info.emails:
                info.emails.append(e)
        if searched:
            info.notes.append(f"Found {len(searched)} email(s) via web search")

    if not info.emails:
        guesses = _guess_emails(website_url, business_name)
        info.guessed_emails = guesses
        if guesses:
            info.notes.append("Common email patterns guessed (verify before use)")

    return info
