"""
Checks robots.txt and ToS of a hackathon website before scraping.
Returns (allowed: bool, notes: str).
"""
import httpx
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlparse
import anthropic
import os

HEADERS = {"User-Agent": "HackathonFinder-Bot/1.0 (educational tool; not for commercial use)"}
TOS_PATHS = ["/terms", "/terms-of-service", "/tos", "/legal", "/privacy-policy"]
TIMEOUT = 10


def _base_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def check_robots(base_url: str) -> tuple[bool, str]:
    robots_url = urljoin(base_url, "/robots.txt")
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        # Check against wildcard agent — only block if the site explicitly
        # disallows all crawlers from the root path
        allowed = rp.can_fetch("*", base_url)
        if not allowed:
            return False, "robots.txt disallows all crawlers from root"
        return True, "robots.txt allows access"
    except Exception:
        # If robots.txt is unreachable, assume allowed (common for small hackathon sites)
        return True, "robots.txt not found — assuming allowed"


def _find_tos_url(base_url: str) -> str | None:
    # Try common ToS paths directly
    for path in TOS_PATHS:
        url = urljoin(base_url, path)
        try:
            r = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
            if r.status_code == 200 and len(r.text) > 200:
                return url
        except Exception:
            continue

    # Fall back: look for a ToS link in the homepage footer
    try:
        r = httpx.get(base_url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")
        keywords = ["terms", "tos", "legal"]
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            href = a["href"]
            if any(k in text or k in href.lower() for k in keywords):
                return urljoin(base_url, href)
    except Exception:
        pass

    return None


def check_tos(base_url: str) -> tuple[bool, str]:
    tos_url = _find_tos_url(base_url)
    if not tos_url:
        return True, "No ToS page found — assuming scraping is allowed"

    try:
        r = httpx.get(tos_url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        tos_text = r.text[:8000]  # cap to avoid huge token usage
    except Exception:
        return True, "Could not fetch ToS — assuming allowed"

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Here is a website's Terms of Service:\n\n{tos_text}\n\n"
                    "Does this ToS explicitly prohibit automated scraping or data collection by bots? "
                    "Answer with only YES or NO, then one short sentence explaining why."
                ),
            }
        ],
    )
    response = message.content[0].text.strip()
    prohibited = response.upper().startswith("YES")
    return (not prohibited), f"ToS check ({tos_url}): {response}"


def is_scraping_allowed(url: str) -> tuple[bool, str]:
    base = _base_url(url)

    robots_ok, robots_notes = check_robots(base)
    if not robots_ok:
        return False, robots_notes

    tos_ok, tos_notes = check_tos(base)
    return tos_ok, tos_notes
