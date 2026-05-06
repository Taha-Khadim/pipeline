"""
Application configuration.

The data store is **always Supabase Postgres**. The .deb / .exe bundles
ship with a working connection string baked in (see app/_bundled_defaults.py
and build/_bake_defaults.py) so the app works out of the box.

Settings are loaded, in order of precedence:
  1. Environment variables
  2. .env file
  3. The app's settings.json (written by the in-app Settings page)
  4. Bundled defaults (baked at build time, see app/_bundled_defaults.py)
  5. Hardcoded defaults below

The settings.json file is what end users edit through the UI — they do NOT
need to touch any environment file.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Bundled defaults — populated by the build pipeline.
# ---------------------------------------------------------------------------
try:
    from app._bundled_defaults import BUNDLED  # type: ignore
except Exception:
    BUNDLED: dict = {}


# ---------------------------------------------------------------------------
# Hard-coded fallback connection string. The build pipeline overrides this
# via _bundled_defaults.py for production artifacts; this constant keeps
# `python launcher.py` working straight out of `git clone`.
# ---------------------------------------------------------------------------
DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://postgres.ailespxrkdfvureeleox:OzP7sCzv1XRGjZnn"
    "@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
)
DEFAULT_SUPABASE_URL = "https://ailespxrkdfvureeleox.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = "sb_publishable_n5-DKZgPSLAoDN53NsdFdw_GLPLbhMF"


def _user_data_dir() -> Path:
    """Where to store settings.json and screenshots.

    Uses platform-appropriate locations:
      - LUMORA_DATA_DIR env var (if set) — wins over everything
      - Linux:   ~/.local/share/lumora-pipeline
      - Windows: %APPDATA%/LumoraPipeline
      - macOS:   ~/Library/Application Support/LumoraPipeline
    """
    override = os.environ.get("LUMORA_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "LumoraPipeline"

    if os.uname().sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "LumoraPipeline"

    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "lumora-pipeline"


DATA_DIR = _user_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = DATA_DIR / "settings.json"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_settings_json() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_settings_json(updates: dict) -> None:
    """Merge updates into settings.json on disk and clear the cache."""
    current = _load_settings_json()
    current.update({k: v for k, v in updates.items() if v is not None})
    SETTINGS_FILE.write_text(json.dumps(current, indent=2))
    get_settings.cache_clear()


# Industries: a wide net for any agency/freelancer hunting clients.
TARGET_INDUSTRIES = [
    "Dentist", "Doctor", "Chiropractor", "Veterinarian", "Optometrist",
    "Physiotherapist", "Dermatologist", "Pediatrician", "Psychologist",
    "Lawyer", "Accountant", "Tax Consultant", "Insurance Broker",
    "Real Estate Agent", "Mortgage Broker", "Property Management",
    "Architect", "Interior Designer", "Landscape Designer",
    "Salon", "Hair Salon", "Barber Shop", "Nail Salon", "Spa", "Massage Therapist",
    "Tattoo Studio", "Piercing Studio", "Esthetician",
    "Plumber", "HVAC Contractor", "Electrician", "Roofer", "Painter",
    "Carpenter", "Locksmith", "Handyman", "Pest Control",
    "General Contractor", "Pool Service", "Cleaning Service",
    "Restaurant", "Cafe", "Bakery", "Bar", "Pizzeria", "Food Truck",
    "Catering Service", "Ice Cream Shop", "Juice Bar",
    "Photographer", "Videographer", "DJ", "Wedding Planner", "Event Venue",
    "Florist", "Caterer", "Party Rental",
    "Personal Trainer", "Gym", "Yoga Studio", "Pilates Studio",
    "Martial Arts School", "Dance Studio", "Crossfit Gym",
    "Tutor", "Music Teacher", "Driving School", "Daycare", "Preschool",
    "Marketing Consultant", "Business Coach", "Life Coach", "Career Coach",
    "Auto Repair", "Auto Detailing", "Car Wash", "Towing Service",
    "Boutique", "Jewelry Store", "Optical Shop", "Pet Shop", "Pet Groomer",
    "Pet Boarding", "Dog Trainer",
    "Travel Agency", "Tour Operator", "Limousine Service",
    "Moving Company", "Storage Facility",
    "Print Shop", "Sign Shop", "Embroidery Service",
    "Clothing Boutique", "Tailor", "Shoe Repair", "Dry Cleaner",
    "Hardware Store", "Furniture Store", "Mattress Store",
    "Fishing Charter", "Boat Rental", "Bike Shop",
]

# Cities — top 60-80 per major country. End user can also free-type.
CITIES_BY_COUNTRY = {
    "United States": [
        "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
        "Philadelphia", "San Antonio", "San Diego", "Dallas", "Austin",
        "San Jose", "San Francisco", "Seattle", "Denver", "Boston",
        "Nashville", "Portland", "Las Vegas", "Atlanta", "Miami",
        "Tampa", "Orlando", "Jacksonville", "Charlotte", "Raleigh",
        "Indianapolis", "Columbus", "Cleveland", "Cincinnati", "Detroit",
        "Milwaukee", "Minneapolis", "St. Paul", "Kansas City", "St. Louis",
        "Memphis", "Louisville", "Birmingham", "New Orleans", "Oklahoma City",
        "Tulsa", "Albuquerque", "Tucson", "Salt Lake City", "Sacramento",
        "Fresno", "Bakersfield", "Long Beach", "Oakland", "Anaheim",
        "Santa Ana", "Riverside", "Stockton", "Fort Worth", "Arlington",
        "El Paso", "Corpus Christi", "Lubbock", "Plano", "Irving",
        "Scottsdale", "Mesa", "Chandler", "Gilbert", "Glendale",
        "Boise", "Spokane", "Honolulu", "Anchorage", "Madison",
        "Omaha", "Lincoln", "Wichita", "Des Moines", "Little Rock",
        "Richmond", "Virginia Beach", "Norfolk", "Baltimore", "Washington DC",
        "Hartford", "Providence", "Buffalo", "Rochester", "Pittsburgh",
    ],
    "United Kingdom": [
        "London", "Manchester", "Birmingham", "Leeds", "Glasgow",
        "Liverpool", "Bristol", "Sheffield", "Edinburgh", "Leicester",
        "Coventry", "Bradford", "Cardiff", "Belfast", "Nottingham",
        "Newcastle", "Southampton", "Portsmouth", "Brighton", "Plymouth",
        "Reading", "Oxford", "Cambridge", "Bath", "York",
        "Aberdeen", "Dundee", "Stirling", "Inverness", "Swansea",
        "Newport", "Wrexham", "Stoke-on-Trent", "Wolverhampton", "Derby",
        "Sunderland", "Milton Keynes", "Northampton", "Norwich", "Ipswich",
        "Peterborough", "Bournemouth", "Poole", "Exeter", "Gloucester",
        "Worcester", "Chester", "Lancaster", "Carlisle", "Durham",
        "Hull", "Middlesbrough", "Doncaster", "Huddersfield", "Bolton",
        "Blackburn", "Preston", "Blackpool", "Salford", "Croydon",
    ],
    "Canada": [
        "Toronto", "Montreal", "Vancouver", "Calgary", "Edmonton",
        "Ottawa", "Winnipeg", "Quebec City", "Hamilton", "Kitchener",
        "London", "Victoria", "Halifax", "Oshawa", "Windsor",
        "Saskatoon", "Regina", "St. John's", "Kelowna", "Barrie",
        "Sherbrooke", "Guelph", "Kingston", "Sudbury", "Saguenay",
        "Trois-Rivières", "Moncton", "Saint John", "Thunder Bay", "Lethbridge",
        "Mississauga", "Brampton", "Surrey", "Burnaby", "Richmond",
        "Markham", "Vaughan", "Gatineau", "Longueuil", "Laval",
        "Oakville", "Burlington", "Whitby", "Coquitlam", "Langley",
        "Abbotsford", "Saanich", "Levis", "Kanata", "Brossard",
    ],
    "Australia": [
        "Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide",
        "Gold Coast", "Canberra", "Newcastle", "Wollongong", "Hobart",
        "Geelong", "Townsville", "Cairns", "Darwin", "Toowoomba",
        "Ballarat", "Bendigo", "Launceston", "Mackay", "Rockhampton",
        "Bunbury", "Bundaberg", "Hervey Bay", "Wagga Wagga", "Coffs Harbour",
        "Sunshine Coast", "Mandurah", "Albany", "Dubbo", "Tamworth",
        "Orange", "Mildura", "Albury", "Shepparton", "Gladstone",
        "Port Macquarie", "Warrnambool", "Lismore", "Maitland", "Devonport",
    ],
    "UAE": [
        "Dubai", "Abu Dhabi", "Sharjah", "Al Ain", "Ajman",
        "Ras Al Khaimah", "Fujairah", "Umm Al Quwain", "Khor Fakkan",
        "Dibba Al-Fujairah", "Madinat Zayed", "Ruwais", "Liwa Oasis",
        "Hatta", "Kalba", "Dhaid",
    ],
    "Ireland": [
        "Dublin", "Cork", "Galway", "Limerick", "Waterford",
        "Drogheda", "Dundalk", "Swords", "Bray", "Navan",
        "Kilkenny", "Ennis", "Tralee", "Carlow", "Athlone",
        "Wexford", "Sligo", "Letterkenny", "Mullingar", "Newbridge",
    ],
    "New Zealand": [
        "Auckland", "Wellington", "Christchurch", "Hamilton", "Tauranga",
        "Napier-Hastings", "Dunedin", "Palmerston North", "Nelson", "Rotorua",
        "Whangārei", "New Plymouth", "Invercargill", "Whanganui", "Gisborne",
    ],
    "India": [
        "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
        "Kolkata", "Pune", "Ahmedabad", "Surat", "Jaipur",
        "Lucknow", "Kanpur", "Nagpur", "Indore", "Thane",
        "Bhopal", "Visakhapatnam", "Patna", "Vadodara", "Ghaziabad",
        "Ludhiana", "Agra", "Nashik", "Faridabad", "Meerut",
        "Rajkot", "Kalyan", "Vasai-Virar", "Varanasi", "Srinagar",
        "Aurangabad", "Dhanbad", "Amritsar", "Allahabad", "Ranchi",
        "Howrah", "Coimbatore", "Jabalpur", "Gwalior", "Vijayawada",
        "Jodhpur", "Madurai", "Raipur", "Kota", "Chandigarh",
        "Guwahati", "Solapur", "Hubli", "Mysore", "Tiruchirappalli",
        "Bareilly", "Aligarh", "Tiruppur", "Gurgaon", "Noida",
    ],
    "Pakistan": [
        "Karachi", "Lahore", "Islamabad", "Rawalpindi", "Faisalabad",
        "Multan", "Peshawar", "Quetta", "Sialkot", "Gujranwala",
        "Hyderabad", "Bahawalpur", "Sargodha", "Sukkur", "Larkana",
        "Sheikhupura", "Mirpur Khas", "Rahim Yar Khan", "Jhang", "Dera Ghazi Khan",
        "Mardan", "Kasur", "Sahiwal", "Okara", "Wah Cantonment",
        "Mingora", "Abbottabad", "Mansehra", "Kohat", "Bannu",
        "Muzaffarabad", "Mirpur", "Gilgit", "Skardu",
    ],
    "Germany": [
        "Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt",
        "Stuttgart", "Düsseldorf", "Leipzig", "Dortmund", "Essen",
        "Bremen", "Dresden", "Hanover", "Nuremberg", "Duisburg",
        "Bochum", "Wuppertal", "Bonn", "Münster", "Karlsruhe",
        "Mannheim", "Augsburg", "Wiesbaden", "Kiel", "Mönchengladbach",
        "Chemnitz", "Aachen", "Braunschweig", "Magdeburg", "Krefeld",
    ],
    "France": [
        "Paris", "Marseille", "Lyon", "Toulouse", "Nice",
        "Nantes", "Montpellier", "Strasbourg", "Bordeaux", "Lille",
        "Rennes", "Reims", "Saint-Étienne", "Le Havre", "Toulon",
        "Grenoble", "Dijon", "Angers", "Nîmes", "Villeurbanne",
        "Clermont-Ferrand", "Le Mans", "Aix-en-Provence", "Brest", "Tours",
        "Amiens", "Limoges", "Annecy", "Perpignan", "Boulogne-Billancourt",
    ],
    "Spain": [
        "Madrid", "Barcelona", "Valencia", "Seville", "Zaragoza",
        "Málaga", "Murcia", "Palma", "Las Palmas", "Bilbao",
        "Alicante", "Córdoba", "Valladolid", "Vigo", "Gijón",
        "L'Hospitalet", "A Coruña", "Granada", "Vitoria-Gasteiz", "Elche",
    ],
    "Netherlands": [
        "Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven",
        "Tilburg", "Groningen", "Almere", "Breda", "Nijmegen",
        "Enschede", "Haarlem", "Arnhem", "Zaanstad", "Amersfoort",
    ],
    "Singapore": [
        "Singapore", "Jurong", "Tampines", "Bedok", "Woodlands",
        "Sengkang", "Hougang", "Yishun", "Punggol", "Choa Chu Kang",
    ],
    "South Africa": [
        "Johannesburg", "Cape Town", "Durban", "Pretoria", "Port Elizabeth",
        "Bloemfontein", "East London", "Pietermaritzburg", "Kimberley", "Polokwane",
        "Nelspruit", "Rustenburg", "George", "Welkom", "Newcastle",
    ],
    "Saudi Arabia": [
        "Riyadh", "Jeddah", "Mecca", "Medina", "Dammam",
        "Khobar", "Dhahran", "Tabuk", "Buraidah", "Khamis Mushait",
        "Hail", "Hofuf", "Taif", "Najran", "Yanbu",
    ],
}

COUNTRIES = list(CITIES_BY_COUNTRY.keys())


_PROJECT_REF_RE = re.compile(r"https?://([a-z0-9]+)\.supabase\.co", re.IGNORECASE)


def _normalize_pg_url(url: str) -> str:
    """Make sure SQLAlchemy uses the asyncpg driver for any Postgres URL."""
    u = url.strip()
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://"):]
    if u.startswith("postgresql://"):
        u = "postgresql+asyncpg://" + u[len("postgresql://"):]
    return u


def supabase_postgres_url(supabase_url: str, password: str) -> str | None:
    """Build an asyncpg-friendly direct-connection URL from project URL + password.

    Used when the user wants the IPv6-only direct host
    (db.<ref>.supabase.co:5432). For IPv4-friendly setups, use the pooler
    URL directly (paste it into the `database_url` setting).
    """
    if not supabase_url or not password:
        return None
    m = _PROJECT_REF_RE.search(supabase_url.strip())
    if not m:
        return None
    ref = m.group(1).lower()
    return (
        f"postgresql+asyncpg://postgres:{quote_plus(password)}"
        f"@db.{ref}.supabase.co:5432/postgres"
    )


class Settings(BaseSettings):
    app_name: str = "Lumora Code — Client Pipeline"

    # API keys (only Gemini is needed for AI features)
    google_api_key: str = BUNDLED.get("google_api_key", "")

    # Sender info — used to personalize generated outreach
    sender_name: str = BUNDLED.get("sender_name", "")
    sender_company: str = BUNDLED.get("sender_company", "")
    sender_website: str = BUNDLED.get("sender_website", "")
    sender_email: str = BUNDLED.get("sender_email", "")

    # Supabase (cloud Postgres). Direct DB connection over SQL.
    supabase_url: str = BUNDLED.get("supabase_url", DEFAULT_SUPABASE_URL)
    supabase_anon_key: str = BUNDLED.get("supabase_anon_key", DEFAULT_SUPABASE_ANON_KEY)
    supabase_db_password: str = BUNDLED.get("supabase_db_password", "")

    # Full Postgres connection URL. Defaults to the bundled pooler URL so the
    # app works with no setup. Override via the Settings page if you want to
    # point at your own Supabase project (or your own Postgres entirely).
    database_url: str = BUNDLED.get("database_url", "") or DEFAULT_DATABASE_URL
    screenshots_dir: str = str(SCREENSHOTS_DIR)

    # Scraping
    scrape_delay_min: float = 1.5
    scrape_delay_max: float = 3.0
    max_results_per_scrape: int = 60

    # Reference data
    target_industries: list[str] = TARGET_INDUSTRIES
    target_countries: list[str] = COUNTRIES
    cities_by_country: dict[str, list[str]] = CITIES_BY_COUNTRY

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def __init__(self, **values):
        merged = {**_load_settings_json(), **values}
        super().__init__(**merged)

    # -- Resolved connection helpers ----------------------------------------
    @property
    def effective_database_url(self) -> str:
        """The Postgres URL the engine actually uses.

        Resolution order:
          1. Explicit `database_url` (env / settings.json / bundled)
          2. Supabase URL + DB password → derive direct host URL
          3. Hard-coded DEFAULT_DATABASE_URL (the project's own pooler)
        Always Postgres — no SQLite anywhere.
        """
        if self.database_url:
            return _normalize_pg_url(self.database_url)
        derived = supabase_postgres_url(self.supabase_url, self.supabase_db_password)
        if derived:
            return derived
        return DEFAULT_DATABASE_URL

    @property
    def database_backend(self) -> str:
        return "postgres"


@lru_cache
def get_settings() -> Settings:
    return Settings()
