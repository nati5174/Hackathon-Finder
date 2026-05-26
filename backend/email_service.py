import os
import resend
from dotenv import load_dotenv

load_dotenv()

resend.api_key = os.getenv("RESEND_API_KEY")

FROM_EMAIL = os.getenv("FROM_EMAIL", "alerts@yourdomain.com")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


def send_confirmation_email(to_email: str, token: str):
    confirm_url = f"{BASE_URL}/api/confirm/{token}"
    resend.Emails.send({
        "from": FROM_EMAIL,
        "to": to_email,
        "subject": "Confirm your Hackathon Travel alerts",
        "html": f"""
        <p>Thanks for signing up!</p>
        <p>Click below to confirm your email and start receiving alerts when new hackathons with travel reimbursement are posted.</p>
        <p><a href="{confirm_url}">Confirm my subscription</a></p>
        <p>If you didn't sign up, ignore this email.</p>
        """,
    })


def send_digest_email(to_email: str, unsubscribe_token: str, new_hackathons: list):
    if not new_hackathons:
        return

    unsubscribe_url = f"{BASE_URL}/api/unsubscribe/{unsubscribe_token}"

    items_html = "".join(
        f"""
        <div style="margin-bottom:16px;">
            <a href="{h['hackathon_url']}" style="font-size:16px;font-weight:bold;">{h['name']}</a>
            <p style="margin:4px 0;">{h['location']} &mdash; {h['date_str']}</p>
            {f"<p style='margin:4px 0;color:#555;'>{h['travel_details']}</p>" if h.get('travel_details') else ""}
        </div>
        """
        for h in new_hackathons
    )

    resend.Emails.send({
        "from": FROM_EMAIL,
        "to": to_email,
        "subject": f"{len(new_hackathons)} new hackathon{'s' if len(new_hackathons) > 1 else ''} with travel reimbursement",
        "html": f"""
        <h2>New hackathons with travel reimbursement</h2>
        {items_html}
        <hr style="margin-top:32px;">
        <p style="font-size:12px;color:#999;">
            <a href="{unsubscribe_url}">Unsubscribe</a>
        </p>
        """,
    })


def send_digest_to_all(new_hackathons: list):
    """Send digest email to all confirmed subscribers."""
    if not new_hackathons:
        print("[email] No new hackathons — skipping digest")
        return

    from sqlmodel import Session, select
    from backend.db import engine, Subscriber

    with Session(engine) as session:
        subscribers = session.exec(
            select(Subscriber).where(Subscriber.confirmed == True)
        ).all()

    if not subscribers:
        print("[email] No confirmed subscribers — skipping digest")
        return

    print(f"[email] Sending digest to {len(subscribers)} subscribers ({len(new_hackathons)} new hackathons)")
    for sub in subscribers:
        try:
            send_digest_email(sub.email, sub.token, new_hackathons)
        except Exception as e:
            print(f"[email] Failed to send to {sub.email}: {e}")
