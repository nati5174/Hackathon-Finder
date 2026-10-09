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
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {"User-Agent": "HackathonFinder-Bot/1.0 (educational tool; not for commercial use)"}
TIMEOUT = 15
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# Paths most likely to mention travel reimbursement, checked in order
TRAVEL_PATHS = [
    "/", "/faq", "/travel", "/logistics", "/about", "/info",
    "/apply", "/application", "/register", "/sponsors", "/details",
]

# Keywords used to identify travel-relevant links on the page
TRAVEL_LINK_KEYWORDS = [
    "travel", "reimburse", "logistics", "transport", "shuttle", "funding",
    "stipend", "scholarship", "getting here", "getting-here", "bus", "flight",
    "faq", "apply", "financial", "support", "aid", "grant",
]


def normalize_format_type(raw: str) -> str:
    if not raw:
        return "in_person"
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    if normalized in ("digital", "online"):
        return "digital"
    if normalized == "hybrid":
        return "hybrid"
    return "in_person"


_MLH_MONTHS = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

def _mlh_date_with_year(date_range: str, season: int) -> str:
    """Append the correct calendar year to an MLH dateRange string.
    In season S: Aug-Dec hackathons are in year S-1; Jan-Jul are in year S.
    """
    if not date_range or date_range == "Unknown":
        return date_range
    m = re.search(r'([A-Z]{3})', date_range.upper())
    if not m:
        return date_range
    month = _MLH_MONTHS.get(m.group(1), 0)
    if not month:
        return date_range
    year = season - 1 if month >= 8 else season
    return f"{date_range}, {year}"


def get_mlh_hackathons() -> list[dict]:
    """
    Scrapes MLH events page and returns a list of dicts:
    {name, hackathon_url, mlh_url, location, date_str, format_type}

    MLH embeds event data as HTML-entity encoded JSON directly in the page HTML.
    Each event object has: name, websiteUrl, location, dateRange, formatType.
    """
    _now = datetime.now()
    _auto_season = _now.year + 1 if _now.month >= 8 else _now.year
    season = int(os.getenv("MLH_SEASON") or _auto_season)
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
            format_type = normalize_format_type(event.get("formatType", ""))
            # Skip digital/online-only events
            if format_type == "digital":
                continue
            # Keep ended events — page is already season-scoped so all belong to 2026

            mlh_event_path = event.get("url", "")
            hackathons.append({
                "name": name,
                "hackathon_url": website_url,
                "mlh_url": f"https://www.mlh.com{mlh_event_path}",
                "location": event.get("location", "Unknown"),
                "date_str": _mlh_date_with_year(event.get("dateRange", "Unknown"), season),
                "format_type": format_type,
                "source": "mlh",
            })
        except Exception as e:
            print(f"[scraper] Error parsing event: {e}")
            continue

    print(f"[scraper] Found {len(hackathons)} in-person hackathons on MLH")
    return hackathons


def _sitemap_urls(base: str) -> list[str]:
    """
    Fetch /sitemap.xml or /sitemap_index.xml and return all internal URLs listed.
    Handles both standard sitemaps and sitemap index files.
    """
    from urllib.parse import urlparse
    import xml.etree.ElementTree as ET

    candidates = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/sitemap.xml"]
    urls = []
    seen = set()
    for path in candidates:
        try:
            r = httpx.get(urljoin(base, path), headers=HEADERS, timeout=8, follow_redirects=True)
            if r.status_code != 200 or "xml" not in r.headers.get("content-type", ""):
                continue
            root = ET.fromstring(r.text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            # sitemap index → recurse into child sitemaps
            for loc in root.findall(".//sm:sitemap/sm:loc", ns):
                try:
                    child = httpx.get(loc.text.strip(), headers=HEADERS, timeout=8, follow_redirects=True)
                    child_root = ET.fromstring(child.text)
                    for u in child_root.findall(".//sm:url/sm:loc", ns):
                        href = u.text.strip()
                        if urlparse(href).netloc == urlparse(base).netloc and href not in seen:
                            seen.add(href)
                            urls.append(href)
                except Exception:
                    pass
            # regular sitemap
            for loc in root.findall(".//sm:url/sm:loc", ns):
                href = loc.text.strip()
                if urlparse(href).netloc == urlparse(base).netloc and href not in seen:
                    seen.add(href)
                    urls.append(href)
            if urls:
                break
        except Exception:
            continue
    return urls


def _extract_internal_links(page, base: str) -> list[str]:
    """Return all unique internal URLs found on the current rendered page."""
    from urllib.parse import urlparse, urldefrag
    try:
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
    except Exception:
        return []
    seen, links = set(), []
    for href in hrefs:
        href, _ = urldefrag(href)  # strip #fragment — same page, already visited
        parsed = urlparse(href)
        if parsed.netloc != urlparse(base).netloc:
            continue
        if parsed.scheme not in ("http", "https"):
            continue
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".css", ".js", ".svg", ".ico")):
            continue
        norm = href.rstrip("/") or base
        if norm not in seen:
            seen.add(norm)
            links.append(href)
    return links


def _travel_relevant_links(page, base: str) -> list[str]:
    """
    Scan all links on the current page and return those whose anchor text
    or URL path contains travel-related keywords. These are inserted at the
    front of the scrape queue so we never miss a hidden travel page.
    """
    from urllib.parse import urlparse, urldefrag
    try:
        items = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href: e.href, text: e.innerText.trim().toLowerCase()}))"
        )
    except Exception:
        return []

    seen, results = set(), []
    for item in items:
        href = item.get("href", "")
        text = item.get("text", "")
        href, _ = urldefrag(href)
        parsed = urlparse(href)
        if parsed.netloc != urlparse(base).netloc:
            continue
        if parsed.scheme not in ("http", "https"):
            continue
        combined = text + " " + parsed.path.lower()
        if any(kw in combined for kw in TRAVEL_LINK_KEYWORDS):
            norm = href.rstrip("/") or base
            if norm not in seen:
                seen.add(norm)
                results.append(href)
    return results


def _text_from_html(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def _render_page(url: str, page) -> str:
    """
    Render a page with Playwright (handles React/Vue/Angular/Next.js/static HTML/etc).
    Waits for JS, scrolls fully, and expands every collapsible element.
    Falls back to a plain httpx fetch if Playwright fails or returns empty content.
    """
    text = ""
    try:
        # First try: domcontentloaded + settle time (fast, works for most sites)
        resp = page.goto(url, timeout=12000, wait_until="domcontentloaded")
        page.wait_for_timeout(600)

        # Scroll to trigger lazy-loaded sections
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(400)

        # --- Layer 1: Expand accordions / collapsibles ---
        # Covers: HTML5 details, ARIA, Bootstrap 3/4/5, generic class patterns
        try:
            els = page.locator(
                "details:not([open]), "
                "[aria-expanded='false'], "
                "[data-toggle='collapse'], [data-bs-toggle='collapse'], "
                ".accordion-button.collapsed, "
                "[class*='accordion'], [class*='collapse']"
            ).all()
            for el in els[:15]:
                try:
                    el.click(timeout=200)
                except Exception:
                    pass
        except Exception:
            pass

        text = _text_from_html(page.content())

        # --- Layer 2: Tab cycling ---
        # Principle-based selectors: ARIA standard → Bootstrap → container-scoped → class patterns
        # Deliberately avoids content-based selectors (no hardcoded "travel", "faq", etc.)
        try:
            tabs = page.locator(
                # ARIA standard
                "[role='tab'], "
                "[role='tablist'] *, "
                # Bootstrap 3/4/5
                ".nav-tabs a, .nav-tabs button, .nav-tabs li, "
                ".nav-pills a, .nav-pills button, "
                "[data-toggle='tab'], [data-bs-toggle='tab'], "
                "[data-toggle='pill'], [data-bs-toggle='pill'], "
                # Container-scoped: buttons inside any element whose id/class signals tabs or FAQ
                "[id*='tab'] button, [class*='tab'] button, "
                "[id*='faq'] button, [class*='faq'] button, "
                # Button class patterns
                "button[class*='tab'], button[class*='Tab']"
            ).all()
            tab_sections = []
            seen_names = set()
            for tab in tabs[:25]:
                try:
                    tab_name = tab.inner_text(timeout=100).strip()
                    # Skip empty, overly long (not a nav label), or duplicates
                    if not tab_name or len(tab_name) > 60 or tab_name in seen_names:
                        continue
                    seen_names.add(tab_name)
                    tab.click(timeout=200)
                    page.wait_for_timeout(350)
                    # Prefer the active panel; fall back to full page text
                    try:
                        panel = page.locator(
                            "[role='tabpanel']:visible, "
                            ".tab-pane.active, .tab-pane:visible, "
                            "[class*='tab-content']:visible > *:not([hidden]), "
                            "[class*='tab-panel']:visible, [class*='tabPanel']:visible, "
                            "[class*='faq-content']:visible, [class*='faq-body']:visible"
                        ).first
                        panel_text = panel.inner_text(timeout=500)
                    except Exception:
                        panel_text = _text_from_html(page.content())
                    if panel_text:
                        tab_sections.append(f"[Tab: {tab_name}]\n{panel_text}")
                except Exception:
                    pass
            if tab_sections:
                text += "\n\n" + "\n\n".join(tab_sections)
        except Exception:
            pass

        # --- Layer 3: JS force-reveal ---
        # Fallback for SPAs (React/Vue/Angular) where click events don't update state.
        # Force-shows known hidden panel/accordion containers via inline styles.
        try:
            page.evaluate("""
                const sel = [
                    '[role="tabpanel"]', '.tab-pane',
                    '[class*="accordion-body"]', '[class*="accordion-content"]',
                    '[class*="collapse-content"]', '[class*="faq-answer"]',
                    '[class*="faq-body"]', '[class*="faq-content"]',
                    '[class*="panel-body"]', '[class*="panel-content"]'
                ].join(',');
                document.querySelectorAll(sel).forEach(el => {
                    const s = el.style;
                    s.setProperty('display', 'block', 'important');
                    s.setProperty('visibility', 'visible', 'important');
                    s.setProperty('height', 'auto', 'important');
                    s.setProperty('max-height', 'none', 'important');
                    s.setProperty('overflow', 'visible', 'important');
                    s.setProperty('opacity', '1', 'important');
                });
            """)
            page.wait_for_timeout(200)
            revealed = _text_from_html(page.content())
            if len(revealed) > len(text):
                text = revealed
        except Exception:
            pass

        # If very little text came back, the page may be a heavy SPA still loading —
        # wait for network idle and try once more
        if len(text) < 800:
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
                text = _text_from_html(page.content())
            except Exception:
                pass
    except Exception:
        pass

    # Fallback: plain HTTP fetch (handles simple HTML / XML / server-rendered pages
    # and sites that block headless browsers)
    if not text:
        try:
            r = httpx.get(url, headers={"User-Agent": BROWSER_UA}, timeout=TIMEOUT, follow_redirects=True)
            ct = r.headers.get("content-type", "")
            if "xml" in ct:
                # strip XML tags, keep text nodes
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(r.text)
                    text = " ".join(root.itertext())
                except Exception:
                    text = re.sub(r"<[^>]+>", " ", r.text)
            else:
                text = _text_from_html(r.text)
        except Exception:
            pass

    return text


def scrape_hackathon_site(url: str, browser=None, browser_page=None) -> str:
    """
    Scrapes a hackathon site by hitting targeted paths most likely to contain
    travel reimbursement info (homepage, /faq, /travel, /about, etc.).
    Falls back to plain httpx if Playwright fails on a page.

    browser: a shared Playwright Browser instance (reused across hackathons)
    browser_page: a pre-created Page (takes priority over browser)
    """
    from urllib.parse import urlparse
    from playwright.sync_api import sync_playwright

    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    combined_text = []
    visited = set()

    def _scrape_targets(page):
        # Start with the homepage + fixed path candidates
        candidates = [url]
        for path in TRAVEL_PATHS:
            candidate = base + path
            if candidate not in candidates:
                candidates.append(candidate)

        homepage_scanned = False

        for target in candidates:
            norm = target.rstrip("/") or base
            if norm in visited:
                continue
            visited.add(norm)

            text = _render_page(target, page)
            if text:
                path_label = urlparse(target).path or "/"
                combined_text.append(f"[Page: {path_label}]\n{text[:10000]}")

                # After loading the homepage, inject any travel-relevant links
                # discovered on that page at the front of the remaining queue
                if not homepage_scanned and target in (url, base, base + "/"):
                    homepage_scanned = True
                    discovered = _travel_relevant_links(page, base)
                    # Insert discovered links right after current position
                    # (deduplicated against already-queued candidates)
                    existing = set(candidates)
                    new_links = [l for l in discovered if l.rstrip("/") not in existing]
                    if new_links:
                        insert_at = candidates.index(target) + 1
                        for i, link in enumerate(new_links):
                            candidates.insert(insert_at + i, link)

            if len(combined_text) >= 8:
                break

    if browser_page is not None:
        _scrape_targets(browser_page)
    elif browser is not None:
        # Reuse the shared browser — create a fresh page, close after
        page = browser.new_page(user_agent=BROWSER_UA)
        try:
            _scrape_targets(page)
        finally:
            page.close()
    else:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_page(user_agent=BROWSER_UA)
            _scrape_targets(page)
            b.close()

    return "\n\n".join(combined_text)[:25000]
