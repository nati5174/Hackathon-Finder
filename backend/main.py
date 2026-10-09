import os
from typing import Literal
from fastapi import FastAPI, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from backend.db import engine, init_db, Hackathon, Subscriber
from backend.scheduler import recheck_hackathon
from backend.email_service import send_confirmation_email
from backend.filters import preference_summary

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


class SubscribeRequest(BaseModel):
    email: EmailStr
    region: Literal["all", "us", "intl"] = "all"
    in_person_only: bool = False


def _apply_subscriber_prefs(sub: Subscriber, body: SubscribeRequest):
    sub.region = body.region
    sub.in_person_only = body.in_person_only


@app.post("/api/subscribe")
def subscribe(body: SubscribeRequest):
    with Session(engine) as session:
        existing = session.exec(
            select(Subscriber).where(Subscriber.email == body.email)
        ).first()
        if existing:
            if existing.confirmed:
                return {"message": "Already subscribed."}
            _apply_subscriber_prefs(existing, body)
            session.add(existing)
            session.commit()
            send_confirmation_email(
                existing.email, existing.token, existing.region, existing.in_person_only
            )
            return {"message": "Confirmation email resent."}
        sub = Subscriber(
            email=body.email,
            region=body.region,
            in_person_only=body.in_person_only,
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        send_confirmation_email(sub.email, sub.token, sub.region, sub.in_person_only)
    return {"message": "Check your email to confirm your subscription."}


@app.get("/api/confirm/{token}", response_class=HTMLResponse)
def confirm(token: str):
    with Session(engine) as session:
        sub = session.exec(select(Subscriber).where(Subscriber.token == token)).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Invalid token.")
        sub.confirmed = True
        session.add(sub)
        session.commit()
        prefs = preference_summary(sub.region, sub.in_person_only)
    return (
        f"<h2>You're confirmed!</h2>"
        f"<p>You'll get an email when new {prefs} hackathons with travel reimbursement are posted.</p>"
        f"<p><a href=\"/api/preferences/{token}\">Update preferences</a></p>"
    )


@app.get("/api/preferences/{token}", response_class=HTMLResponse)
def preferences_form(token: str, saved: int = 0):
    with Session(engine) as session:
        sub = session.exec(select(Subscriber).where(Subscriber.token == token)).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Invalid token.")
        region = sub.region
        in_person_only = sub.in_person_only

    checked = "checked" if in_person_only else ""
    def selected(r): return "selected" if region == r else ""

    return f"""
    <html><body style="font-family:sans-serif;max-width:480px;margin:2rem auto;">
    <h2>Alert preferences</h2>
    {"<p style='color:#2e7d32;'>Preferences saved.</p>" if saved else ""}
    <form method="post" action="/api/preferences/{token}">
        <p>
            <label>Region<br>
            <select name="region">
                <option value="all" {selected("all")}>All</option>
                <option value="us" {selected("us")}>US</option>
                <option value="intl" {selected("intl")}>International</option>
            </select>
            </label>
        </p>
        <p>
            <label>
                <input type="checkbox" name="in_person_only" value="true" {checked}>
                In-person only (exclude hybrid)
            </label>
        </p>
        <button type="submit">Save preferences</button>
    </form>
    </body></html>
    """


@app.post("/api/preferences/{token}")
def preferences_update(
    token: str,
    region: Literal["all", "us", "intl"] = Form("all"),
    in_person_only: str | None = Form(None),
):
    with Session(engine) as session:
        sub = session.exec(select(Subscriber).where(Subscriber.token == token)).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Invalid token.")
        sub.region = region
        sub.in_person_only = in_person_only == "true"
        session.add(sub)
        session.commit()
    return RedirectResponse(url=f"/api/preferences/{token}?saved=1", status_code=303)


@app.get("/api/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(token: str):
    with Session(engine) as session:
        sub = session.exec(select(Subscriber).where(Subscriber.token == token)).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Invalid token.")
        session.delete(sub)
        session.commit()
    return "<h2>You've been unsubscribed. You won't receive any more emails.</h2>"


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
