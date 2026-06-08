"""
app/models/audit_log.py

Append-only audit trail for every significant event.
Every state change (campaign submitted, AI analysis done, human decision)
creates a new audit log entry — never updates, never deletes.
This is required for compliance and to support the eval framework.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuditLog(Base):
    """Immutable event record for compliance and evaluation tracking."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Event classification
    # -------------------------------------------------------------------------
    # Known event types:
    # "campaign_submitted"   — campaign first received by the API
    # "ai_analysis_started"  — LangGraph agent began processing
    # "ai_analysis_complete" — agent finished, results stored
    # "human_review_started" — reviewer opened the campaign detail
    # "human_decision"       — reviewer submitted their final decision
    # "human_override"       — decision differs from AI recommendation
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Who triggered the event: "ai" | "human" | "system"
    actor: Mapped[str] = mapped_column(String(20), nullable=False)
    # Specific actor identifier (reviewer_id, agent version, "system", etc.)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Flexible payload — anything relevant to the event
    # For "human_override": {"ai_recommendation": "X", "human_decision": "Y", "reason": "..."}
    # For "ai_analysis_complete": {"risk_score": N, "recommendation": "X"}
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

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
        back_populates="audit_logs",
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog campaign={self.campaign_id} "
            f"event={self.event_type!r} actor={self.actor!r}>"
        )
