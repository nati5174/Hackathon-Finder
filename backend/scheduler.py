"""
Daily scraping job. Run by Railway cron once per day.
"""
import time
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from sqlmodel import Session, select

from backend.db import engine, init_db, Hackathon
from backend.scraper import get_mlh_hackathons, scrape_hackathon_site
from backend.compliance import is_scraping_allowed
from backend.detector import detect_travel_reimbursement

REQUEST_DELAY = 3  # seconds between hackathons


def run():
    print(f"[scheduler] Starting scrape job at {datetime.utcnow().isoformat()}")
    init_db()

    hackathons = get_mlh_hackathons()
    if not hackathons:
        print("[scheduler] No hackathons found — aborting")
        return

    with Session(engine) as session:
        for h in hackathons:
            existing = session.exec(
                select(Hackathon).where(Hackathon.hackathon_url == h["hackathon_url"])
            ).first()

            # Skip if already processed — only process new hackathons
            if existing:
                print(f"[scheduler] Already in DB, skipping: {h['name']}")
                continue

            # --- Compliance check ---
            print(f"[scheduler] Checking compliance for: {h['name']}")
            try:
                allowed, notes = is_scraping_allowed(h["hackathon_url"])
            except Exception as e:
                allowed, notes = False, f"Compliance check error: {e}"

            if not allowed:
                print(f"[scheduler] SKIPPED (compliance): {h['name']} — {notes}")
                record = Hackathon(**h)
                record.skipped = True
                record.skip_reason = notes
                record.compliance_ok = False
                record.compliance_notes = notes
                record.last_checked = datetime.utcnow()
                session.add(record)
                session.commit()
                time.sleep(REQUEST_DELAY)
                continue

            # --- Scrape hackathon site ---
            print(f"[scheduler] Scraping site: {h['name']}")
            try:
                content = scrape_hackathon_site(h["hackathon_url"])
            except Exception as e:
                content = ""
                print(f"[scheduler] Scrape error for {h['name']}: {e}")

            # --- Detect travel reimbursement ---
            print(f"[scheduler] Detecting travel reimbursement: {h['name']}")
            try:
                offers, details = detect_travel_reimbursement(h["name"], content)
            except Exception as e:
                offers, details = False, f"Detection error: {e}"

            # --- Save to DB ---
            record = Hackathon(**h)
            record.name = h["name"]
            record.location = h["location"]
            record.date_str = h["date_str"]
            record.compliance_ok = True
            record.compliance_notes = notes
            record.skipped = False
            record.skip_reason = None
            record.travel_reimbursement = offers
            record.travel_details = details
            record.last_checked = datetime.utcnow()

            session.add(record)
            session.commit()

            status = "YES" if offers else "NO"
            print(f"[scheduler] Travel reimbursement: {status} — {h['name']}")
            time.sleep(REQUEST_DELAY)

    print(f"[scheduler] Done at {datetime.utcnow().isoformat()}")


if __name__ == "__main__":
    run()
