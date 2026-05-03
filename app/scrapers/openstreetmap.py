"""
OpenStreetMap scraper using the Overpass API.

This is a free, official, structured-data source — no scraping, no anti-bot
issues. Returns business POIs with phone / website / email / address / hours
when contributors have filled them in.

Each industry maps to one or more OSM tag combinations. The query asks
Nominatim for the city's bounding area, then Overpass returns all matching
POIs inside it.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass

import httpx

log = logging.getLogger(__name__)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

USER_AGENT = "LumoraPipeline/1.0 (lumora-code; client-hunter)"

# Map our industry labels to OSM tag filters.
# Multiple alternates allowed — we OR them all in a single Overpass query.
INDUSTRY_OSM_TAGS: dict[str, list[tuple[str, str]]] = {
    "Dentist":            [("amenity", "dentist"), ("healthcare", "dentist")],
    "Doctor":             [("amenity", "doctors"), ("healthcare", "doctor")],
    "Pediatrician":       [("healthcare", "doctor"), ("healthcare:speciality", "paediatrics")],
    "Optometrist":        [("shop", "optician"), ("healthcare", "optometrist")],
    "Dermatologist":      [("healthcare:speciality", "dermatology")],
    "Chiropractor":       [("healthcare", "chiropractor")],
    "Veterinarian":       [("amenity", "veterinary")],
    "Physiotherapist":    [("healthcare", "physiotherapist")],
    "Psychologist":       [("healthcare", "psychotherapist")],
    "Lawyer":             [("office", "lawyer")],
    "Accountant":         [("office", "accountant"), ("office", "tax_advisor")],
    "Tax Consultant":     [("office", "tax_advisor")],
    "Insurance Broker":   [("office", "insurance")],
    "Real Estate Agent":  [("office", "estate_agent")],
    "Mortgage Broker":    [("office", "financial")],
    "Architect":          [("office", "architect")],
    "Interior Designer":  [("craft", "interior_decorator"), ("office", "interior_design")],
    "Salon":              [("shop", "hairdresser"), ("shop", "beauty")],
    "Hair Salon":         [("shop", "hairdresser")],
    "Barber Shop":        [("shop", "hairdresser"), ("shop", "barber")],
    "Nail Salon":         [("shop", "beauty")],
    "Spa":                [("leisure", "spa"), ("shop", "beauty")],
    "Massage Therapist":  [("shop", "massage"), ("amenity", "spa")],
    "Tattoo Studio":      [("shop", "tattoo")],
    "Piercing Studio":    [("shop", "tattoo"), ("shop", "piercing")],
    "Esthetician":        [("shop", "beauty")],
    "Plumber":            [("craft", "plumber"), ("office", "plumber")],
    "HVAC":               [("craft", "hvac"), ("craft", "plumber")],
    "HVAC Contractor":    [("craft", "hvac")],
    "Electrician":        [("craft", "electrician")],
    "Roofer":             [("craft", "roofer")],
    "Painter":            [("craft", "painter")],
    "Carpenter":          [("craft", "carpenter")],
    "Locksmith":          [("shop", "locksmith"), ("craft", "locksmith")],
    "Handyman":           [("craft", "handyman")],
    "Pest Control":       [("craft", "pest_control")],
    "General Contractor": [("craft", "builder")],
    "Pool Service":       [("craft", "pool_cleaner")],
    "Cleaning Service":   [("craft", "cleaning"), ("office", "cleaning_services")],
    "Restaurant":         [("amenity", "restaurant")],
    "Cafe":               [("amenity", "cafe")],
    "Bakery":             [("shop", "bakery")],
    "Bar":                [("amenity", "bar"), ("amenity", "pub")],
    "Pizzeria":           [("amenity", "fast_food"), ("cuisine", "pizza")],
    "Food Truck":         [("amenity", "fast_food")],
    "Catering Service":   [("craft", "caterer")],
    "Ice Cream Shop":     [("amenity", "ice_cream"), ("shop", "ice_cream")],
    "Juice Bar":          [("amenity", "juice_bar")],
    "Photographer":       [("craft", "photographer")],
    "Videographer":       [("craft", "photographer")],
    "DJ":                 [("craft", "dj")],
    "Wedding Planner":    [("office", "wedding")],
    "Event Venue":        [("amenity", "events_venue")],
    "Florist":            [("shop", "florist")],
    "Caterer":            [("craft", "caterer")],
    "Party Rental":       [("shop", "party")],
    "Personal Trainer":   [("leisure", "fitness_centre"), ("sport", "fitness")],
    "Gym":                [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
    "Yoga Studio":        [("leisure", "fitness_centre"), ("sport", "yoga")],
    "Pilates Studio":     [("leisure", "fitness_centre"), ("sport", "pilates")],
    "Martial Arts School": [("leisure", "sports_centre"), ("sport", "karate")],
    "Dance Studio":       [("leisure", "dance"), ("amenity", "dancing_school")],
    "Crossfit Gym":       [("leisure", "fitness_centre")],
    "Tutor":              [("amenity", "school"), ("amenity", "training")],
    "Music Teacher":      [("amenity", "music_school")],
    "Driving School":     [("amenity", "driving_school")],
    "Daycare":            [("amenity", "kindergarten")],
    "Preschool":          [("amenity", "kindergarten")],
    "Marketing Consultant": [("office", "marketing"), ("office", "advertising_agency")],
    "Business Coach":     [("office", "consulting")],
    "Life Coach":         [("office", "consulting")],
    "Career Coach":       [("office", "consulting")],
    "Auto Repair":        [("shop", "car_repair")],
    "Auto Detailing":     [("shop", "car_repair")],
    "Car Wash":           [("amenity", "car_wash")],
    "Towing Service":     [("amenity", "vehicle_inspection")],
    "Boutique":           [("shop", "boutique"), ("shop", "clothes")],
    "Jewelry Store":      [("shop", "jewelry")],
    "Optical Shop":       [("shop", "optician")],
    "Pet Shop":           [("shop", "pet")],
    "Pet Groomer":        [("shop", "pet_grooming"), ("amenity", "pet_grooming")],
    "Pet Boarding":       [("amenity", "animal_boarding")],
    "Dog Trainer":        [("amenity", "dog_training")],
    "Travel Agency":      [("shop", "travel_agency")],
    "Tour Operator":      [("shop", "travel_agency"), ("tourism", "information")],
    "Limousine Service":  [("amenity", "taxi")],
    "Moving Company":     [("office", "moving_company")],
    "Storage Facility":   [("shop", "storage_rental")],
    "Print Shop":          [("shop", "copyshop")],
    "Sign Shop":          [("craft", "signmaker")],
    "Embroidery Service": [("craft", "embroiderer")],
    "Clothing Boutique":  [("shop", "clothes")],
    "Tailor":             [("shop", "tailor"), ("craft", "tailor")],
    "Shoe Repair":        [("shop", "shoe_repair")],
    "Dry Cleaner":        [("shop", "dry_cleaning")],
    "Hardware Store":     [("shop", "hardware"), ("shop", "doityourself")],
    "Furniture Store":    [("shop", "furniture")],
    "Mattress Store":     [("shop", "bed")],
    "Fishing Charter":    [("leisure", "fishing")],
    "Boat Rental":        [("amenity", "boat_rental")],
    "Bike Shop":          [("shop", "bicycle")],
}


@dataclass
class OsmBusiness:
    name: str = ""
    category: str = ""
    address: str = ""
    city: str = ""
    country: str = ""
    phone: str = ""
    email: str = ""
    website_url: str = ""
    has_website: bool = False
    google_maps_url: str = ""
    google_rating: float | None = None
    google_reviews: int | None = None
    osm_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _build_overpass_query_area(tags: list[tuple[str, str]], area_id: int) -> str:
    parts = []
    for k, v in tags:
        for kind in ("node", "way", "relation"):
            parts.append(f'  {kind}["{k}"="{v}"](area.searchArea);')
    body = "\n".join(parts)
    return (
        "[out:json][timeout:60];\n"
        f"area({area_id})->.searchArea;\n"
        "(\n"
        f"{body}\n"
        ");\n"
        "out tags center;"
    )


def _build_overpass_query_bbox(
    tags: list[tuple[str, str]], south: float, west: float, north: float, east: float
) -> str:
    bbox = f"{south},{west},{north},{east}"
    parts = []
    for k, v in tags:
        for kind in ("node", "way", "relation"):
            parts.append(f'  {kind}["{k}"="{v}"]({bbox});')
    body = "\n".join(parts)
    return (
        "[out:json][timeout:60];\n"
        "(\n"
        f"{body}\n"
        ");\n"
        "out tags center;"
    )


async def _resolve_location(city: str, country: str) -> tuple[int | None, tuple[float, float, float, float] | None]:
    """Return (area_id, bbox) for a city. Either or both may be None."""
    params = {
        "q": f"{city}, {country}",
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as c:
            r = await c.get(NOMINATIM, params=params)
            r.raise_for_status()
            data = r.json()
        if not data:
            return None, None
        item = data[0]
        area_id: int | None = None
        if item.get("osm_type") == "relation":
            area_id = 3600000000 + int(item["osm_id"])
        elif item.get("osm_type") == "way":
            area_id = 2400000000 + int(item["osm_id"])

        bbox: tuple[float, float, float, float] | None = None
        bb = item.get("boundingbox")
        if bb and len(bb) == 4:
            try:
                south, north, west, east = float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])
                bbox = (south, west, north, east)
            except ValueError:
                bbox = None
        return area_id, bbox
    except Exception as exc:
        log.warning("Nominatim lookup failed for %s: %s", city, exc)
        return None, None


async def _query_overpass(q: str) -> list[dict]:
    last_exc: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            async with httpx.AsyncClient(
                timeout=70,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as c:
                r = await c.post(endpoint, content=q.encode("utf-8"),
                                 headers={"Content-Type": "text/plain"})
            if r.status_code == 200:
                return r.json().get("elements", [])
            log.warning("Overpass %s -> HTTP %d", endpoint, r.status_code)
        except Exception as exc:
            last_exc = exc
            log.warning("Overpass %s failed: %s", endpoint, exc)
            continue
    if last_exc:
        raise last_exc
    return []


def _tag(t: dict, *keys: str) -> str:
    for k in keys:
        v = t.get(k)
        if v:
            return v
    return ""


def _build_address(t: dict) -> str:
    if t.get("addr:full"):
        return t["addr:full"]
    parts: list[str] = []
    if t.get("addr:housenumber") and t.get("addr:street"):
        parts.append(f"{t['addr:housenumber']} {t['addr:street']}")
    elif t.get("addr:street"):
        parts.append(t["addr:street"])
    for k in ("addr:city", "addr:postcode", "addr:country"):
        if t.get(k):
            parts.append(t[k])
    return ", ".join(parts)


def _element_to_business(el: dict, default_city: str, country: str) -> OsmBusiness | None:
    tags = el.get("tags") or {}
    name = _tag(tags, "name", "name:en", "official_name", "brand")
    if not name:
        return None

    biz = OsmBusiness(
        name=name.strip(),
        city=_tag(tags, "addr:city") or default_city,
        country=_tag(tags, "addr:country") or country,
    )
    biz.phone = _tag(tags, "contact:phone", "phone")
    biz.email = _tag(tags, "contact:email", "email")
    site = _tag(tags, "contact:website", "website", "url")
    if site:
        if not site.startswith("http"):
            site = "https://" + site.lstrip("/")
        biz.website_url = site
        biz.has_website = True
    biz.address = _build_address(tags)
    biz.category = (
        _tag(tags, "amenity", "shop", "office", "craft", "leisure",
             "healthcare", "tourism")
        .replace("_", " ").title()
    )

    osm_type = el.get("type")
    osm_id = el.get("id")
    if osm_type and osm_id:
        biz.osm_url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"

    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    if lat and lon:
        biz.google_maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

    return biz


async def scrape_openstreetmap(
    industry: str,
    city: str,
    country: str,
    max_results: int = 60,
) -> list[dict]:
    """Fetch businesses from OpenStreetMap via Overpass."""
    tags = INDUSTRY_OSM_TAGS.get(industry)
    if not tags:
        # Generic fallback: try shop=<industry> normalized
        slug = industry.lower().replace(" ", "_")
        tags = [("shop", slug), ("amenity", slug), ("office", slug), ("craft", slug)]

    log.info("OSM scrape: %s in %s, %s", industry, city, country)
    area_id, bbox = await _resolve_location(city, country)
    if not area_id and not bbox:
        log.warning("OSM: could not resolve location for %s, %s", city, country)
        return []

    elements: list[dict] = []
    if area_id:
        try:
            elements = await _query_overpass(_build_overpass_query_area(tags, area_id))
        except Exception as exc:
            log.warning("OSM area query failed: %s — will try bbox", exc)

    if not elements and bbox:
        try:
            elements = await _query_overpass(_build_overpass_query_bbox(tags, *bbox))
        except Exception as exc:
            log.error("OSM bbox query failed: %s", exc)
            return []

    log.info("OSM: %d raw elements", len(elements))
    seen: set[str] = set()
    out: list[dict] = []
    for el in elements:
        biz = _element_to_business(el, city, country)
        if not biz or biz.name in seen:
            continue
        seen.add(biz.name)
        out.append(biz.to_dict())
        if len(out) >= max_results:
            break

    log.info("OSM: %d businesses extracted", len(out))
    return out
