"""
Daily scraping job. Run by Railway cron once per day.

Architecture:
- WORKERS threads, each owning one shared Playwright browser (reused across hackathons)
- Per hackathon: compliance (HTTP) runs concurrently with scraping (Playwright)
- Results written to DB immediately as each hackathon finishes
"""
import queue
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv()

from sqlmodel import Session, select

from backend.db import engine, init_db, Hackathon
from backend.scraper import get_mlh_hackathons, scrape_hackathon_site
from backend.compliance import is_scraping_allowed
from backend.detector import detect_travel_reimbursement

WORKERS = 10


def _save_result(result: dict):
    try:
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
    except Exception as db_err:
        print(f"[scheduler] Skipping duplicate: {result['name']} ({db_err})")


def process_hackathon(h: dict, browser) -> dict:
    """
    Process one hackathon using the worker's shared Playwright browser.
    Compliance check (HTTP only) runs concurrently with scraping.
    """
    name = h["name"]
    url = h["hackathon_url"]

    # Kick off compliance in a background thread while we scrape on this thread
    with ThreadPoolExecutor(max_workers=1) as ex:
        compliance_future = ex.submit(is_scraping_allowed, url)

        content = ""
        try:
            content = scrape_hackathon_site(url, browser=browser)
        except Exception as e:
            print(f"[scheduler] Scrape error {name}: {e}")

        try:
            allowed, notes = compliance_future.result()
        except Exception as e:
            allowed, notes = True, f"compliance check failed: {e}"

    if not allowed:
        print(f"[scheduler] SKIPPED (compliance) {name} — {notes}")
        return {**h, "skipped": True, "skip_reason": notes,
                "compliance_ok": False, "compliance_notes": notes,
                "travel_reimbursement": False, "travel_details": None}

    try:
        offers, details = detect_travel_reimbursement(name, content)
    except Exception as e:
        offers, details = False, f"Detection error: {e}"

    print(f"[scheduler] {'YES' if offers else 'NO'} — {name}")
    return {**h, "skipped": False, "skip_reason": None,
            "compliance_ok": True, "compliance_notes": notes,
            "travel_reimbursement": offers, "travel_details": details}


def _worker(q: queue.Queue, results: list, lock: threading.Lock):
    """
    Worker thread: owns one Playwright browser for its lifetime.
    Pulls hackathons from the queue until empty.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            while True:
                try:
                    h = q.get_nowait()
                except queue.Empty:
                    break
                try:
                    result = process_hackathon(h, browser)
                    with lock:
                        results.append(result)
                        _save_result(result)
                except Exception as e:
                    print(f"[scheduler] Worker error for {h['name']}: {e}")
                finally:
                    q.task_done()
        finally:
            browser.close()


def run():
    print(f"[scheduler] Starting at {datetime.utcnow().isoformat()}")
    init_db()

    hackathons = get_mlh_hackathons()
    if not hackathons:
        print("[scheduler] No hackathons found — aborting")
        return

    with Session(engine) as session:
        existing_urls = set(
            row.hackathon_url for row in session.exec(select(Hackathon)).all()
        )

    to_process = [h for h in hackathons if h["hackathon_url"] not in existing_urls]
    skipped_count = len(hackathons) - len(to_process)
    if skipped_count:
        print(f"[scheduler] Skipping {skipped_count} already in DB")

    n_workers = min(WORKERS, len(to_process))
    print(f"[scheduler] Processing {len(to_process)} hackathons with {n_workers} workers")

    q = queue.Queue()
    for h in to_process:
        q.put(h)

    results = []
    lock = threading.Lock()
    threads = [
        threading.Thread(target=_worker, args=(q, results, lock), daemon=True)
        for _ in range(n_workers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    compliance_skipped = [r for r in results if r.get("skipped")]
    if compliance_skipped:
        print(f"\n[scheduler] === SKIPPED DUE TO COMPLIANCE ({len(compliance_skipped)}) ===")
        for r in compliance_skipped:
            print(f"  - {r['name']} | {r['hackathon_url']}")
            print(f"    Reason: {r['skip_reason']}")
    else:
        print("[scheduler] No hackathons were blocked by compliance checks")

    yes_count = sum(1 for r in results if r.get("travel_reimbursement"))
    print(f"\n[scheduler] Done. {yes_count}/{len(results)} hackathons offer travel reimbursement.")


if __name__ == "__main__":
    run()
