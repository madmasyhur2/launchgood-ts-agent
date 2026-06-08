"""
app/models/campaign.py

SQLAlchemy ORM model for campaign submissions.
Maps to the `campaigns` table defined in SYSTEM.md §6.
"""

import uuid
from datetime import datetime

from sqlalchemy import DECIMAL, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Campaign(Base):
    """A campaign submitted by a creator, awaiting Trust & Safety review."""

    __tablename__ = "campaigns"

    # Primary key — UUID generated in Python to keep it consistent across
    # async sessions (PostgreSQL gen_random_uuid() would also work).
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    # Core campaign fields
    title: Mapped[str] = mapped_column(Text, nullable=False)
    story: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    goal_amount: Mapped[float | None] = mapped_column(DECIMAL(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True, default="USD")

    # Creator information — denormalised for quick access without join
    creator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    creator_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creator_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creator_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    creator_account_age_days: Mapped[int | None] = mapped_column(nullable=True)

    # Geographic / organisational context
    beneficiary_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    organization_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Workflow status: pending → analyzing → completed → reviewed
    # "pending"   — just submitted, waiting for AI analysis
    # "analyzing" — LangGraph agent is processing
    # "completed" — AI analysis done, awaiting human decision
    # "approved"  — human approved
    # "rejected"  — human rejected
    # "escalated" — flagged for senior review
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # AI recommendation from latest analysis (for quick sorting)
    ai_recommendation: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ai_risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ai_risk_score: Mapped[int | None] = mapped_column(nullable=True)

    # Full raw submission payload — useful for re-analysis & debugging
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    analyses: Mapped[list["AIAnalysis"]] = relationship(  # type: ignore[name-defined]
        "AIAnalysis",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="AIAnalysis.created_at.desc()",
    )
    reviews: Mapped[list["Review"]] = relationship(  # type: ignore[name-defined]
        "Review",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # type: ignore[name-defined]
        "AuditLog",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Campaign id={self.id} title={self.title!r} status={self.status!r}>"
