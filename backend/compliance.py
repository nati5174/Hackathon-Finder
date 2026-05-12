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
    try:
        r = httpx.get(robots_url, timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})

        content_type = r.headers.get("content-type", "")
        body = r.text.strip()

        # Server returned an HTML page instead of a real robots.txt — no restrictions
        if "text/html" in content_type or body.startswith("<!"):
            return True, "No robots.txt found (server returned HTML) — assuming allowed"

        # AI content signals format — parse ai-input signal specifically
        if "content-signal" in body.lower() or "ai-input" in body.lower():
            for line in body.splitlines():
                stripped = line.strip().lower()
                if stripped.startswith("ai-input:"):
                    value = stripped.split(":", 1)[1].strip()
                    if value == "no":
                        return False, "robots.txt AI content signal explicitly disallows ai-input"
                    if value == "yes":
                        return True, "robots.txt AI content signal explicitly allows ai-input"
            # No explicit ai-input signal — neither grants nor restricts (per the format spec)
            return True, "robots.txt AI content signals file — no ai-input restriction found"

        # Standard robots.txt — hybrid check: our bot name + wildcard
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(body.splitlines())

        bot_allowed = rp.can_fetch("HackathonFinder-Bot", base_url)
        wildcard_allowed = rp.can_fetch("*", base_url)

        if not bot_allowed and not wildcard_allowed:
            return False, "robots.txt disallows both our bot and all crawlers from root"
        if not bot_allowed:
            return False, "robots.txt explicitly disallows HackathonFinder-Bot from root"
        if not wildcard_allowed:
            return True, "robots.txt disallows wildcard but no specific rule blocks our bot — allowed"
        return True, "robots.txt allows access (bot and wildcard both permitted)"
    except Exception:
        return True, "robots.txt unreachable — assuming allowed"


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
