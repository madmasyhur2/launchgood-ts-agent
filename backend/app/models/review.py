"""
app/models/review.py

SQLAlchemy ORM model for human reviewer decisions.
Captures the final decision, whether it overrides the AI, and the reviewer's notes.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Review(Base):
    """A human reviewer's final decision on a campaign."""

    __tablename__ = "reviews"

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

    # Who made the decision
    reviewer_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # Final human decision: APPROVE | REJECT | ESCALATE
    decision: Mapped[str] = mapped_column(String(10), nullable=False)

    # What the AI had recommended before the human reviewed
    ai_recommendation: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # True when the human decision differs from the AI recommendation
    # This is the primary signal for continuous evaluation / model improvement.
    is_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Required when is_override=True — explains WHY the human disagreed
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional free-text notes (e.g. "asked creator to upload docs")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    campaign: Mapped["Campaign"] = relationship(  # type: ignore[name-defined]
        "Campaign",
        back_populates="reviews",
    )

    def __repr__(self) -> str:
        return (
            f"<Review campaign={self.campaign_id} decision={self.decision!r} "
            f"override={self.is_override}>"
        )
