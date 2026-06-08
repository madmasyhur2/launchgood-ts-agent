"""
app/schemas/review.py

Pydantic v2 schemas for human reviewer decisions.
Matches the API contract defined in SYSTEM.md §5 for POST /api/campaigns/{id}/review.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    """Request body for POST /api/campaigns/{id}/review."""

    reviewer_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique identifier of the reviewer (user ID or username)",
    )
    decision: Literal["APPROVE", "REJECT", "ESCALATE"] = Field(
        ...,
        description="Final human decision for this campaign",
    )
    override_reason: str | None = Field(
        None,
        max_length=2000,
        description=(
            "Required when the decision overrides the AI recommendation. "
            "Explain why the AI was wrong."
        ),
    )
    notes: str | None = Field(
        None,
        max_length=5000,
        description="Optional reviewer notes (visible to the campaign team internally)",
    )

    model_config = {"json_schema_extra": {
        "example": {
            "reviewer_id": "rev_xyz",
            "decision": "APPROVE",
            "override_reason": "Organisation documents verified via direct email",
            "notes": "Ask creator to upload registration certificate before campaign goes live",
        }
    }}


class ReviewResponse(BaseModel):
    """Response after a human review decision is recorded."""

    campaign_id: uuid.UUID
    review_id: uuid.UUID
    decision: Literal["APPROVE", "REJECT", "ESCALATE"]
    ai_recommendation: str | None = Field(
        None,
        description="What the AI had recommended before this human review",
    )
    is_override: bool = Field(
        ...,
        description="True if the human decision differs from the AI recommendation",
    )
    audit_log_id: uuid.UUID = Field(
        ...,
        description="ID of the audit log entry created for this decision",
    )
    processed_at: datetime
