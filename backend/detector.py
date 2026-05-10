"""
Uses Claude to determine if a hackathon offers travel reimbursement.
Returns (offers_reimbursement: bool, details: str)
"""
import os
import anthropic


def detect_travel_reimbursement(hackathon_name: str, site_content: str) -> tuple[bool, str]:
    if not site_content.strip():
        return False, "Could not fetch hackathon website content"

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""You are analyzing the website of a hackathon called "{hackathon_name}".

Here is the text content scraped from their website:

{site_content}

---

Does this hackathon offer travel reimbursement, travel stipends, travel grants, or cover any travel costs for attendees (flights, bus, train, etc.)?

Answer in this exact format:
VERDICT: YES or NO
DETAILS: One or two sentences summarizing what travel support is offered, or why you concluded there is none.
"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    response = message.content[0].text.strip()
    lines = response.splitlines()

    verdict = False
    details = response  # fallback

    for line in lines:
        if line.startswith("VERDICT:"):
            verdict = "YES" in line.upper()
        if line.startswith("DETAILS:"):
            details = line.replace("DETAILS:", "").strip()

    return verdict, details
