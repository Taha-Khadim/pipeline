import enum
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Text,
    Float,
    Integer,
    Enum,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LeadStatus(str, enum.Enum):
    FOUND = "FOUND"
    RESEARCHED = "RESEARCHED"
    CONTACTED = "CONTACTED"
    RESPONDED = "RESPONDED"
    CALL_BOOKED = "CALL_BOOKED"
    PROPOSAL_SENT = "PROPOSAL_SENT"
    CLOSED_WON = "CLOSED_WON"
    CLOSED_LOST = "CLOSED_LOST"


class OutreachChannel(str, enum.Enum):
    EMAIL = "EMAIL"
    COLD_CALL = "COLD_CALL"
    LINKEDIN_DM = "LINKEDIN_DM"
    INSTAGRAM_DM = "INSTAGRAM_DM"
    FACEBOOK_DM = "FACEBOOK_DM"
    WHATSAPP = "WHATSAPP"


class ScrapeJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _utcnow():
    return datetime.now(timezone.utc)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_name: Mapped[str] = mapped_column(String(300), index=True)
    owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    industry: Mapped[str] = mapped_column(String(100), index=True)
    category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str] = mapped_column(String(100), index=True)
    country: Mapped[str] = mapped_column(String(100), index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    emails: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    has_website: Mapped[bool] = mapped_column(default=False)
    google_maps_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    google_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    google_reviews: Mapped[int | None] = mapped_column(Integer, nullable=True)
    social_links: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    website_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    website_issues: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lead_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_research: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus), default=LeadStatus.FOUND, index=True
    )
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_action_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    outreach_logs: Mapped[list["OutreachLog"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


class OutreachLog(Base):
    __tablename__ = "outreach_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    channel: Mapped[OutreachChannel] = mapped_column(Enum(OutreachChannel))
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    lead: Mapped["Lead"] = relationship(back_populates="outreach_logs")


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String(300))
    industry: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(100))
    status: Mapped[ScrapeJobStatus] = mapped_column(
        Enum(ScrapeJobStatus), default=ScrapeJobStatus.PENDING
    )
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
