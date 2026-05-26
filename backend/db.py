import os
import uuid
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, create_engine, Session
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is not set")
engine = create_engine(DATABASE_URL)


class Hackathon(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    hackathon_url: str = Field(unique=True)  # the hackathon's own website
    mlh_url: str                # the MLH listing page
    location: str
    date_str: str
    # compliance
    compliance_ok: bool = False
    compliance_notes: Optional[str] = None
    # result
    skipped: bool = False
    skip_reason: Optional[str] = None
    travel_reimbursement: bool = False
    travel_details: Optional[str] = None
    last_checked: datetime = Field(default_factory=datetime.utcnow)


class Subscriber(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True)
    confirmed: bool = False
    token: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
