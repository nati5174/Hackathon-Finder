"""
Uses Claude to determine if a hackathon offers travel reimbursement.
Returns (offers_reimbursement: bool, details: str)
"""
import os
import anthropic


TRAVEL_KEYWORDS = [
    "travel reimbursement", "travel stipend", "travel grant", "travel support",
    "travel assistance", "travel award", "travel funding", "travel subsidy",
    "reimburse travel", "cover travel", "flight reimbursement", "bus reimbursement",
    "transportation reimbursement", "travel scholarship", "travel allowance",
    "travel expenses", "travel costs covered", "we cover", "we reimburse",
    "travel voucher", "bus transportation", "chartered bus", "shuttle",
    "travel help", "travel aid",
]


def _keyword_check(content: str) -> bool:
    """Fast pre-check: if any travel keyword appears, likely YES."""
    lower = content.lower()
    return any(kw in lower for kw in TRAVEL_KEYWORDS)


def detect_travel_reimbursement(hackathon_name: str, site_content: str) -> tuple[bool, str]:
    if not site_content.strip():
        return False, "Could not fetch hackathon website content"

    # Fast path: keyword hit → still confirm with Claude for accurate details
    keyword_hit = _keyword_check(site_content)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""You are analyzing the website of a hackathon called "{hackathon_name}".

Here is the text content scraped from their website:

{site_content}

---

Does this hackathon offer ANY form of travel support for attendees? This includes:
- Travel reimbursement, stipends, grants, or scholarships
- Covered flights, buses, trains, or shuttles
- Transportation subsidies or vouchers
- Any financial help for getting to the event

Important rules:
- Be generous in interpretation — if travel support is mentioned even conditionally or for select participants, answer YES.
- If a dedicated travel page (e.g. /travel, /reimbursement, /logistics) exists but was blocked by Cloudflare or a security check and you could not read its content, answer YES — the existence of a travel-specific page strongly implies travel support is offered.
- Only answer NO if you have actually read enough site content to be confident travel support is not mentioned anywhere.

Answer in this exact format:
VERDICT: YES or NO
DETAILS: One or two sentences summarizing what travel support is offered, or why you concluded there is none.
"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=250,
        messages=[{"role": "user", "content": prompt}],
    )

    response = message.content[0].text.strip()
    lines = response.splitlines()

    verdict = keyword_hit  # default to keyword result if parsing fails
    details = response

    for line in lines:
        if line.startswith("VERDICT:"):
            verdict = "YES" in line.upper()
        if line.startswith("DETAILS:"):
            details = line.replace("DETAILS:", "").strip()

    return verdict, details
