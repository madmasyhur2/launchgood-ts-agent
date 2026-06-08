"""
app/models/ai_analysis.py

SQLAlchemy ORM model for AI analysis results.
One campaign can have multiple analyses (e.g. re-analysis after appeal).
"""

import uuid
from datetime import datetime

from sqlalchemy import DECIMAL, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AIAnalysis(Base):
    """Result produced by the LangGraph analysis agent for a campaign."""

    __tablename__ = "ai_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign key to the campaign this analysis belongs to
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------------------------
    # Core risk assessment
    # ---------------------------------------------------------------------------
    # Composite score 0-100 (formula in SYSTEM.md §4)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    # LOW | MEDIUM | HIGH (derived from risk_score thresholds)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)
    # APPROVE | ESCALATE | REJECT
    recommendation: Mapped[str] = mapped_column(String(10), nullable=False)
    # Confidence of the AI recommendation (0.0 – 1.0)
    confidence: Mapped[float | None] = mapped_column(DECIMAL(3, 2), nullable=True)

    # Human-readable explanation for the reviewer
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---------------------------------------------------------------------------
    # Detailed breakdown (stored as JSONB for schema flexibility)
    # ---------------------------------------------------------------------------
    # Structure: {"content_quality": {"score": N, "signals": [...], "weight": 0.20}, ...}
    risk_dimensions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Structure: [{"type": "COMPLIANCE", "severity": "MEDIUM", "detail": "..."}]
    flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ---------------------------------------------------------------------------
    # Performance / provenance
    # ---------------------------------------------------------------------------
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Track which model/version produced this analysis (important for eval)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    campaign: Mapped["Campaign"] = relationship(  # type: ignore[name-defined]
        "Campaign",
        back_populates="analyses",
    )

    def __repr__(self) -> str:
        return (
            f"<AIAnalysis campaign={self.campaign_id} "
            f"score={self.risk_score} rec={self.recommendation!r}>"
        )
