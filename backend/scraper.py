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
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# Only check the two pages most likely to mention travel reimbursement
TRAVEL_HINT_PATHS = ["/", "/travel"]


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
    # There are two separate JSON arrays: upcoming and past events. Parse both.
    decoded = html.unescape(r.text)

    def extract_array(text, start_pos):
        depth = 0
        for i, ch in enumerate(text[start_pos:], start=start_pos):
            if ch == '[': depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    try: return json.loads(text[start_pos:i+1]), i
                    except json.JSONDecodeError: return [], i
        return [], len(text)

    events_data, search_from = [], 0
    while True:
        idx = decoded.find('"websiteUrl"', search_from)
        if idx == -1:
            break
        array_start = decoded.rfind('[', search_from, idx)
        if array_start == -1 or array_start < search_from:
            search_from = idx + 1
            continue
        arr, end_pos = extract_array(decoded, array_start)
        if arr:
            events_data.extend(arr)
        search_from = end_pos + 1

    if not events_data:
        print("[scraper] Could not find event data in MLH page")
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
            # Keep ended events — page is already season-scoped so all belong to 2026

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


def _fetch_page_text(url: str, page) -> str:
    """Fetch a single page with Playwright and return visible text."""
    try:
        page.goto(url, timeout=12000, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        # Scroll to bottom so lazy-loaded sections render
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)

        # Click any FAQ accordion items mentioning travel so content expands
        try:
            els = page.locator("button, summary, [role='button'], dt, .faq-question, .accordion").all()
            for el in els:
                try:
                    if any(k in el.inner_text(timeout=500).lower() for k in ["travel", "reimburse", "stipend"]):
                        el.click(timeout=500)
                        page.wait_for_timeout(300)
                except Exception:
                    pass
        except Exception:
            pass

        soup = BeautifulSoup(page.content(), "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)
    except Exception:
        return ""


def scrape_hackathon_site(url: str, browser_page=None) -> str:
    """
    Fetches text from a hackathon site using Playwright (handles JS-rendered sites).
    Pass an existing browser_page to reuse across calls (faster).
    If none is passed, opens its own browser instance.
    """
    from urllib.parse import urlparse
    from playwright.sync_api import sync_playwright

    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    combined_text = []

    def _scrape(page):
        for path in TRAVEL_HINT_PATHS:
            text = _fetch_page_text(urljoin(base, path), page)
            if text:
                combined_text.append(f"[Page: {path}]\n{text[:8000]}")

    if browser_page is not None:
        _scrape(browser_page)
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=BROWSER_UA)
            _scrape(page)
            browser.close()

    return "\n\n".join(combined_text)[:12000]
