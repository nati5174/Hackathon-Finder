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
        "source": "luma",
    })


# ---------------------------------------------------------------------------
# Eventbrite
# ---------------------------------------------------------------------------

def _parse_eventbrite_server_data(html: str, results: list, seen: set):
    """Extract events from Eventbrite's window.__SERVER_DATA__ embedded JSON."""
    match = re.search(r'window\.__SERVER_DATA__\s*=\s*(\{)', html)
    if not match:
        return
    start = match.start(1)
    depth, end = 0, start
    for end, ch in enumerate(html[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
    try:
        data = json.loads(html[start : end + 1])
    except Exception:
        return

    events = data.get("search_data", {}).get("events", {}).get("results", [])
    for event in events:
        if event.get("is_online_event") or event.get("is_cancelled"):
            continue

        name = (event.get("name") or "").strip()
        url = event.get("url") or event.get("tickets_url") or ""
        if not name or not url or url in seen:
            continue

        # Only keep actual hackathon events
        name_lower = name.lower()
        if not ("hackathon" in name_lower or "hack" in name_lower):
            continue

        start_date = event.get("start_date", "")
        if _is_past(start_date + "T00:00:00"):
            continue

        seen.add(url)

        venue = event.get("primary_venue") or {}
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
            "date_str": _normalize_date(start_date),
            "format_type": "in_person",
        })


def get_eventbrite_hackathons() -> list[dict]:
    """
    Fetches hackathon events by scraping Eventbrite's public search pages.
    Eventbrite deprecated their public search API in 2023; this uses the
    window.__SERVER_DATA__ JSON embedded in their search result pages instead.
    No API key required.
    """
    BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    results = []
    seen: set[str] = set()

    # Search across US/Canada and major international regions
    search_urls = [
        "https://www.eventbrite.com/d/united-states--canada/hackathon/",
        "https://www.eventbrite.com/d/united-kingdom/hackathon/",
        "https://www.eventbrite.com/d/germany/hackathon/",
        "https://www.eventbrite.com/d/india/hackathon/",
    ]

    for search_url in search_urls:
        for page in range(1, 4):   # 3 pages × 20 events = up to 60 per region
            url = f"{search_url}?page={page}"
            try:
                r = httpx.get(url, headers={"User-Agent": BROWSER_UA}, timeout=TIMEOUT, follow_redirects=True)
                r.raise_for_status()
                before = len(results)
                _parse_eventbrite_server_data(r.text, results, seen)
                # Stop paginating if no new results on this page
                if len(results) == before:
                    break
            except Exception as e:
                print(f"[eventbrite] Error fetching {url}: {e}")
                break

    print(f"[eventbrite] Found {len(results)} in-person hackathons")
    return results
