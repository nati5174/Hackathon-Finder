"""
Daily scraping job. Run by Railway cron once per day.
Processes hackathons in parallel (5 at a time) for speed.
"""
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv()

from sqlmodel import Session, select
from urllib.parse import urlparse

from backend.db import engine, init_db, Hackathon
from backend.scraper import get_mlh_hackathons, scrape_hackathon_site
from backend.compliance import check_robots
from backend.detector import detect_travel_reimbursement

WORKERS = 5  # parallel hackathons


def process_hackathon(h: dict) -> dict:
    """
    Runs in a thread. Returns a result dict to be saved to DB.
    """
    name = h["name"]
    url = h["hackathon_url"]

    # robots.txt check
    try:
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        allowed, notes = check_robots(base)
    except Exception as e:
        allowed, notes = True, f"robots.txt check failed: {e}"

    if not allowed:
        print(f"[scheduler] SKIPPED (robots.txt) {name} | {url} — {notes}")
        return {**h, "skipped": True, "skip_reason": notes,
                "compliance_ok": False, "compliance_notes": notes,
                "travel_reimbursement": False, "travel_details": None}

    # Scrape
    content = ""
    try:
        content = scrape_hackathon_site(url)
    except Exception as e:
        print(f"[scheduler] Scrape error {name}: {e}")

    # Claude detection
    try:
        offers, details = detect_travel_reimbursement(name, content)
    except Exception as e:
        offers, details = False, f"Detection error: {e}"

    status = "YES" if offers else "NO"
    print(f"[scheduler] {status} — {name}")

    return {**h, "skipped": False, "skip_reason": None,
            "compliance_ok": True, "compliance_notes": notes,
            "travel_reimbursement": offers, "travel_details": details}


def run():
    print(f"[scheduler] Starting at {datetime.utcnow().isoformat()}")
    init_db()

    hackathons = get_mlh_hackathons()
    if not hackathons:
        print("[scheduler] No hackathons found — aborting")
        return

    # Filter out already-processed ones
    with Session(engine) as session:
        existing_urls = set(
            row.hackathon_url for row in session.exec(select(Hackathon)).all()
        )

    to_process = [h for h in hackathons if h["hackathon_url"] not in existing_urls]
    skipped_count = len(hackathons) - len(to_process)
    if skipped_count:
        print(f"[scheduler] Skipping {skipped_count} already in DB")
    print(f"[scheduler] Processing {len(to_process)} hackathons with {WORKERS} workers")

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(process_hackathon, h): h for h in to_process}
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
                # Write immediately so the UI updates in real-time
                with Session(engine) as session:
                    session.add(Hackathon(
                        name=result["name"],
                        hackathon_url=result["hackathon_url"],
                        mlh_url=result["mlh_url"],
                        location=result["location"],
                        date_str=result["date_str"],
                        compliance_ok=result["compliance_ok"],
                        compliance_notes=result["compliance_notes"],
                        skipped=result["skipped"],
                        skip_reason=result["skip_reason"],
                        travel_reimbursement=result["travel_reimbursement"],
                        travel_details=result["travel_details"],
                        last_checked=datetime.utcnow(),
                    ))
                    session.commit()
            except Exception as e:
                h = futures[future]
                print(f"[scheduler] Worker error for {h['name']}: {e}")

    compliance_skipped = [r for r in results if r.get("skipped")]
    if compliance_skipped:
        print(f"\n[scheduler] === SKIPPED DUE TO ROBOTS.TXT ({len(compliance_skipped)}) ===")
        for r in compliance_skipped:
            print(f"  - {r['name']} | {r['hackathon_url']}")
            print(f"    Reason: {r['skip_reason']}")
    else:
        print("[scheduler] No hackathons were blocked by robots.txt")

    yes_count = sum(1 for r in results if r.get("travel_reimbursement"))
    print(f"\n[scheduler] Done. {yes_count}/{len(results)} hackathons offer travel reimbursement.")


if __name__ == "__main__":
    run()
