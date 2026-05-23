import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from backend.db import engine, init_db, Hackathon
from backend.scheduler import recheck_hackathon

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/hackathons")
def get_hackathons():
    """Returns hackathons that offer travel reimbursement."""
    with Session(engine) as session:
        results = session.exec(
            select(Hackathon).where(Hackathon.travel_reimbursement == True)
        ).all()
        return results


@app.get("/api/hackathons/all")
def get_all_hackathons():
    """Returns all hackathons including those without travel reimbursement."""
    with Session(engine) as session:
        return session.exec(select(Hackathon)).all()


@app.get("/api/stats")
def get_stats():
    with Session(engine) as session:
        all_h = session.exec(select(Hackathon)).all()
        total = len(all_h)
        with_travel = sum(1 for h in all_h if h.travel_reimbursement)
        skipped = sum(1 for h in all_h if h.skipped)
        last_checked = max((h.last_checked for h in all_h), default=None)
        return {
            "total": total,
            "with_travel_reimbursement": with_travel,
            "skipped_compliance": skipped,
            "last_updated": last_checked,
        }


@app.post("/api/admin/recheck/{hackathon_id}")
def admin_recheck(hackathon_id: int):
    """Force re-scrape and re-classify a single hackathon by id."""
    result = recheck_hackathon(hackathon_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Hackathon not found")
    return result


# Serve React frontend in production
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        return FileResponse(os.path.join(frontend_dist, "index.html"))
