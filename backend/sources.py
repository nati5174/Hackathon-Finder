"""
Additional hackathon listing sources beyond MLH.

Each public function returns list[dict] matching the standard format:
  {name, hackathon_url, mlh_url (used as source_url), location, date_str, format_type}

Luma:       Uses their public API — no key required.
Eventbrite: Uses their official API — requires EVENTBRITE_TOKEN env var (free).
            Register at: https://www.eventbrite.com/platform/api
"""
import os
import json
import re
import httpx
from datetime import datetime, timezone

HEADERS = {"User-Agent": "HackathonFinder-Bot/1.0 (educational tool; not for commercial use)"}
TIMEOUT = 15


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _normalize_date(dt_str: str) -> str:
    """Convert ISO datetime string to 'MON DD' format, e.g. 'MAR 15'."""
    if not dt_str:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d").upper()
    except Exception:
        return dt_str[:10] if dt_str else "Unknown"


def _is_past(dt_str: str) -> bool:
    """Return True if the datetime string represents a past event."""
    if not dt_str:
        return False
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        # Make naive datetimes timezone-aware (assume UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt < datetime.now(timezone.utc)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Luma
# ---------------------------------------------------------------------------

def get_luma_hackathons() -> list[dict]:
    """
    Fetches upcoming hackathon events from luma.com city pages.

    Luma has no open search API. City pages (lu.ma/sf, lu.ma/nyc, etc.) redirect to
    luma.com and embed up to 20 upcoming events per city in __NEXT_DATA__ JSON.
    We fetch each city page with httpx, parse the JSON, and filter for hackathons.
    """
    CITY_SLUGS = [
        "sf", "nyc", "toronto", "boston", "seattle",
        "london", "berlin", "austin", "chicago", "la",
    ]

    results = []
    seen: set[str] = set()

    for slug in CITY_SLUGS:
        try:
            r = httpx.get(
                f"https://lu.ma/{slug}",
                headers=HEADERS,
                timeout=TIMEOUT,
                follow_redirects=True,
            )
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                r.text, re.DOTALL
            )
            if not match:
                continue
            page_data = json.loads(match.group(1))
            events = (
                page_data.get("props", {})
                .get("pageProps", {})
                .get("initialData", {})
                .get("data", {})
                .get("events", [])
            )
            for entry in events:
                _parse_luma_event(entry, results, seen)
        except Exception as e:
            print(f"[luma] Error loading {slug}: {e}")

    results = [h for h in results if h["format_type"] != "digital"]
    print(f"[luma] Found {len(results)} in-person/hybrid hackathons")
    return results


def _parse_luma_event(entry: dict, results: list, seen: set):
    # Entry format from city pages: {event: {...}, start_at: ..., ...}
    # Entry format from API search: the event dict directly
    event = entry.get("event") if "event" in entry else entry
    if not isinstance(event, dict):
        return

    name = (event.get("name") or "").strip()
    if not name:
        return

    # Only keep events that are hackathons
    name_lower = name.lower()
    if not ("hackathon" in name_lower or "hack" in name_lower):
        return

    # Build URL — city page events have a slug, not a full URL
    raw_url = event.get("url") or ""
    if raw_url.startswith("http"):
        event_url = raw_url
    elif raw_url:
        event_url = f"https://lu.ma/{raw_url}"
    else:
        api_id = event.get("api_id", "")
        event_url = f"https://lu.ma/{api_id}" if api_id else ""

    if not event_url or event_url in seen:
        return

    # Date — entry-level start_at is more reliable than event-level
    start_at = entry.get("start_at") or event.get("start_at") or ""
    if _is_past(start_at):
        return

    seen.add(event_url)

    # Location + format
    geo = event.get("geo_address_info") or {}
    location_type = event.get("location_type", "")
    if isinstance(geo, dict):
        city = geo.get("city") or ""
        region = geo.get("region") or ""
        country = geo.get("country") or ""
        location = ", ".join(filter(None, [city, region, country])) or "Unknown"
    else:
        location = str(geo) if geo else "Unknown"

    if location_type in ("online", "virtual") or event.get("virtual"):
        format_type = "digital"
    elif location_type == "hybrid":
        format_type = "hybrid"
    else:
        format_type = "in_person" if location != "Unknown" else "digital"

    results.append({
        "name": name,
        "hackathon_url": event_url,
        "mlh_url": event_url,
        "location": location,
        "date_str": _normalize_date(start_at),
        "format_type": format_type,
    })


# ---------------------------------------------------------------------------
# Eventbrite
# ---------------------------------------------------------------------------

def get_eventbrite_hackathons() -> list[dict]:
    """
    Fetches hackathon events from the Eventbrite API.
    Requires EVENTBRITE_TOKEN env var.
    Get a free token at: https://www.eventbrite.com/platform/api
    """
    token = os.getenv("EVENTBRITE_TOKEN")
    if not token:
        print("[eventbrite] EVENTBRITE_TOKEN not set — skipping")
        return []

    results = []
    seen = set()
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}

    params = {
        "q": "hackathon",
        "categories": "102",   # Science & Technology
        "status": "live",
        "expand": "venue",
        "page_size": 50,
    }

    for page in range(1, 6):   # max 5 pages = 250 events
        try:
            r = httpx.get(
                "https://www.eventbriteapi.com/v3/events/search/",
                params={**params, "page": page},
                headers=headers,
                timeout=TIMEOUT,
            )
            if r.status_code == 401:
                print("[eventbrite] Invalid token — check EVENTBRITE_TOKEN")
                break
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[eventbrite] API error page {page}: {e}")
            break

        for event in data.get("events", []):
            if event.get("online_event"):
                continue

            name = (event.get("name") or {}).get("text", "").strip()
            url = event.get("url", "")
            if not name or not url or url in seen:
                continue

            # Skip past events
            start_local = (event.get("start") or {}).get("local", "")
            if _is_past(start_local):
                continue

            seen.add(url)

            venue = event.get("venue") or {}
            address = venue.get("address") or {}
            location = ", ".join(filter(None, [
                address.get("city"),
                address.get("region"),
                address.get("country"),
            ])) or "Unknown"

            results.append({
                "name": name,
                "hackathon_url": url,
                "mlh_url": url,
                "location": location,
                "date_str": _normalize_date(start_local),
                "format_type": "in_person",
            })

        if not (data.get("pagination") or {}).get("has_more_items"):
            break

    print(f"[eventbrite] Found {len(results)} in-person hackathons")
    return results
