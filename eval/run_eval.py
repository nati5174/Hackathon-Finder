"""
Eval script for travel reimbursement detection.

Modes:
  python eval/run_eval.py ground_truth   -- run LLM against ground_truth.json, report precision/recall
  python eval/run_eval.py consistency    -- re-run LLM on DB entries, flag label changes
  python eval/run_eval.py spot <n>       -- re-run on a random sample of n DB entries
"""
import sys
import json
import random
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from backend.scraper import scrape_hackathon_site
from backend.detector import detect_travel_reimbursement


def run_ground_truth():
    gt_path = Path(__file__).parent / "ground_truth.json"
    cases = json.loads(gt_path.read_text())

    results = []
    for case in cases:
        print(f"\n  Checking: {case['name']} ({case['url']})")
        try:
            content = scrape_hackathon_site(case["url"])
            predicted, details = detect_travel_reimbursement(case["name"], content)
        except Exception as e:
            print(f"    ERROR: {e}")
            predicted, details = None, str(e)

        expected = case["travel_reimbursement"]
        correct = predicted == expected
        status = "PASS" if correct else "FAIL"
        print(f"    Expected: {expected} | Got: {predicted} | {status}")
        print(f"    Details: {details[:100]}")
        results.append({"name": case["name"], "expected": expected, "predicted": predicted, "correct": correct})

    tp = sum(1 for r in results if r["expected"] and r["predicted"])
    fp = sum(1 for r in results if not r["expected"] and r["predicted"])
    fn = sum(1 for r in results if r["expected"] and not r["predicted"])
    tn = sum(1 for r in results if not r["expected"] and not r["predicted"])
    total = len(results)
    correct_count = sum(1 for r in results if r["correct"])

    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    print(f"\n{'='*50}")
    print(f"RESULTS: {correct_count}/{total} correct ({100*correct_count/total:.0f}%)")
    print(f"  True Positives:  {tp}  (correctly found travel)")
    print(f"  False Positives: {fp}  (hallucinated travel)")
    print(f"  False Negatives: {fn}  (missed travel) <- worst kind")
    print(f"  True Negatives:  {tn}  (correctly said no travel)")
    print(f"  Precision: {precision:.2f} | Recall: {recall:.2f} | F1: {f1:.2f}")
    print(f"{'='*50}")

    fails = [r for r in results if not r["correct"]]
    if fails:
        print("\nFailed cases:")
        for r in fails:
            print(f"  - {r['name']}: expected={r['expected']}, got={r['predicted']}")


def run_consistency(sample_n: int = 20):
    from backend.db import engine, Hackathon
    from sqlmodel import Session, select

    with Session(engine) as session:
        all_h = session.exec(select(Hackathon).where(Hackathon.skipped == False)).all()

    sample = random.sample(all_h, min(sample_n, len(all_h)))
    print(f"Re-running detector on {len(sample)} DB entries to check consistency...\n")

    flips = []
    errors = []
    for h in sample:
        print(f"  {h.name} (stored: {'YES' if h.travel_reimbursement else 'NO'})", end=" ... ", flush=True)
        try:
            content = scrape_hackathon_site(h.hackathon_url)
            predicted, details = detect_travel_reimbursement(h.name, content)
            changed = predicted != h.travel_reimbursement
            if changed:
                print(f"FLIP → {'YES' if predicted else 'NO'}")
                flips.append({
                    "name": h.name,
                    "url": h.hackathon_url,
                    "stored": h.travel_reimbursement,
                    "new": predicted,
                    "details": details,
                })
            else:
                print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
            errors.append(h.name)

    print(f"\n{'='*50}")
    print(f"Consistency check: {len(flips)} flips out of {len(sample)} checked")
    if flips:
        print("\nLabel flips (need manual review):")
        for f in flips:
            print(f"  - {f['name']}")
            print(f"    URL: {f['url']}")
            print(f"    Stored={f['stored']} → New={f['new']}")
            print(f"    Details: {f['details'][:120]}")
    if errors:
        print(f"\nErrors ({len(errors)}): {', '.join(errors)}")
    print(f"{'='*50}")


def run_spot(n: int):
    run_consistency(sample_n=n)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "ground_truth"

    if mode == "ground_truth":
        run_ground_truth()
    elif mode == "consistency":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        run_consistency(n)
    elif mode == "spot":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        run_spot(n)
    else:
        print("Usage: python eval/run_eval.py [ground_truth | consistency [n] | spot [n]]")
