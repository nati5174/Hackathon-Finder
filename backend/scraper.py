"""
Scrapes MLH for the list of hackathons, then fetches content
from each hackathon's own website for travel reimbursement detection.
"""
import os
import re
import html
import json
import time
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {"User-Agent": "HackathonFinder-Bot/1.0 (educational tool; not for commercial use)"}
TIMEOUT = 15
REQUEST_DELAY = 2  # seconds between requests — be polite

# Pages on each hackathon site that might mention travel reimbursement
TRAVEL_HINT_PATHS = ["/", "/travel", "/faq", "/about", "/info", "/attend"]


def get_mlh_hackathons() -> list[dict]:
    """
    Scrapes MLH events page and returns a list of dicts:
    {name, hackathon_url, mlh_url, location, date_str}

    MLH embeds event data as HTML-entity encoded JSON directly in the page HTML.
    Each event object has: name, websiteUrl, location, dateRange, formatType.
    """
    season = os.getenv("MLH_SEASON", "2026")
    mlh_url = f"https://www.mlh.com/seasons/{season}/events"

    try:
        r = httpx.get(mlh_url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        print(f"[scraper] Failed to fetch MLH page: {e}")
        return []

    # MLH embeds event data as HTML-entity encoded JSON in the raw HTML.
    # We find it by locating the "websiteUrl" key and extracting the full JSON array.
    page_text = r.text
    decoded = html.unescape(page_text)

    # Find all event objects by extracting the JSON array containing websiteUrl fields
    # The pattern: find a JSON array of objects with "websiteUrl" and "name" fields
    matches = re.findall(
        r'\{"id":"[0-9a-f\-]+".*?"websiteUrl":"(https?://[^"]+)".*?\}',
        decoded,
    )

    # Better approach: find the whole JSON blob and parse it
    # Look for the array start before the first event id
    idx = decoded.find('"websiteUrl"')
    if idx == -1:
        print("[scraper] Could not find event data in MLH page")
        return []

    # Walk back to find the opening [ of the events array
    array_start = decoded.rfind('[', 0, idx)
    # Walk forward to find the closing ] — find matching bracket
    depth = 0
    array_end = array_start
    for i, ch in enumerate(decoded[array_start:], start=array_start):
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                array_end = i
                break

    try:
        events_data = json.loads(decoded[array_start:array_end + 1])
    except json.JSONDecodeError as e:
        print(f"[scraper] Failed to parse events JSON: {e}")
        return []

    hackathons = []
    for event in events_data:
        try:
            if not isinstance(event, dict):
                continue
            website_url = event.get("websiteUrl", "")
            name = event.get("name", "").strip()
            if not website_url or not name:
                continue
            # Skip digital/online-only events
            if event.get("formatType") == "digital":
                continue

            mlh_event_path = event.get("url", "")
            hackathons.append({
                "name": name,
                "hackathon_url": website_url,
                "mlh_url": f"https://www.mlh.com{mlh_event_path}",
                "location": event.get("location", "Unknown"),
                "date_str": event.get("dateRange", "Unknown"),
            })
        except Exception as e:
            print(f"[scraper] Error parsing event: {e}")
            continue

    print(f"[scraper] Found {len(hackathons)} in-person hackathons on MLH")
    return hackathons


def scrape_hackathon_site(url: str) -> str:
    """
    Fetches text content from a hackathon's website.
    Tries the homepage plus travel/faq/about pages.
    Returns combined plain text (capped to avoid huge Claude costs).
    """
    from urllib.parse import urlparse
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    combined_text = []

    for path in TRAVEL_HINT_PATHS:
        target = urljoin(base, path)
        try:
            r = httpx.get(target, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            # Strip scripts/styles
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            combined_text.append(f"[Page: {path}]\n{text[:3000]}")
            time.sleep(REQUEST_DELAY)
        except Exception:
            continue

    return "\n\n".join(combined_text)[:12000]  # cap total to ~12k chars
