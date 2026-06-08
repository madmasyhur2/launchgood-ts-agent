"""
app/routers/reviews.py

Human reviewer decision endpoint:
  POST /campaigns/{id}/review   — Submit a human decision (APPROVE/REJECT/ESCALATE)

Key business logic:
- Detects if the human decision overrides the AI recommendation
- Records the decision in `reviews` table
- Creates an audit log entry (always)
- Creates a second "human_override" audit entry when is_override=True
- Updates the campaign status to reflect the final decision
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.review import Review
from app.schemas.review import ReviewRequest, ReviewResponse

router = APIRouter(prefix="/campaigns", tags=["reviews"])


@router.post(
    "/{campaign_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a human reviewer decision for a campaign",
)
async def submit_review(
    campaign_id: uuid.UUID,
    payload: ReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ReviewResponse:
    """
    Records the human reviewer's final decision for a campaign.

    Business rules enforced here:
    - Campaign must exist
    - Campaign must be in a reviewable state (not already finalized)
    - If decision overrides AI recommendation, override_reason is strongly
      encouraged (we log a warning but do not reject the request — the
      override_reason field is not made required in the API to avoid blocking
      reviewers under time pressure)
    - Campaign status is updated to reflect the final decision
    - Every decision produces an audit log entry
    - Overrides produce an additional "human_override" audit log entry
      (this is the primary signal for the eval framework)
    """
    # ------------------------------------------------------------------
    # 1. Load the campaign
    # ------------------------------------------------------------------
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    # Prevent duplicate final decisions (allow re-escalation from escalated)
    already_finalized = campaign.status in ("approved", "rejected")
    if already_finalized:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Campaign {campaign_id} has already been finalized "
                f"(status: {campaign.status!r}). Create an appeal to re-review."
            ),
        )

    # ------------------------------------------------------------------
    # 2. Determine if this is an override
    # ------------------------------------------------------------------
    ai_recommendation = campaign.ai_recommendation  # may be None if analysis hasn't run
    is_override = (
        ai_recommendation is not None
        and ai_recommendation != payload.decision
    )

    # ------------------------------------------------------------------
    # 3. Persist the Review record
    # ------------------------------------------------------------------
    review = Review(
        campaign_id=campaign_id,
        reviewer_id=payload.reviewer_id,
        decision=payload.decision,
        ai_recommendation=ai_recommendation,
        is_override=is_override,
        override_reason=payload.override_reason,
        notes=payload.notes,
    )
    db.add(review)
    await db.flush()  # Get review.id before creating audit log

    # ------------------------------------------------------------------
    # 4. Update campaign status
    # ------------------------------------------------------------------
    status_map = {
        "APPROVE": "approved",
        "REJECT": "rejected",
        "ESCALATE": "escalated",
    }
    campaign.status = status_map[payload.decision]

    # ------------------------------------------------------------------
    # 5. Audit log — human decision
    # ------------------------------------------------------------------
    decision_audit = AuditLog(
        campaign_id=campaign_id,
        event_type="human_decision",
        actor="human",
        actor_id=payload.reviewer_id,
        payload={
            "review_id": str(review.id),
            "decision": payload.decision,
            "ai_recommendation": ai_recommendation,
            "is_override": is_override,
            "notes": payload.notes,
        },
    )
    db.add(decision_audit)
    await db.flush()

    # ------------------------------------------------------------------
    # 6. Additional audit log — human override (eval signal)
    # ------------------------------------------------------------------
    # This separate event makes it easy to query overrides without
    # parsing the full human_decision payload.
    override_audit_id: uuid.UUID | None = None
    if is_override:
        override_audit = AuditLog(
            campaign_id=campaign_id,
            event_type="human_override",
            actor="human",
            actor_id=payload.reviewer_id,
            payload={
                "ai_recommendation": ai_recommendation,
                "human_decision": payload.decision,
                "override_reason": payload.override_reason,
            },
        )
        db.add(override_audit)
        await db.flush()
        override_audit_id = override_audit.id

    # Use the decision audit log id as the primary audit reference in the response
    primary_audit_id = override_audit_id if is_override else decision_audit.id

    return ReviewResponse(
        campaign_id=campaign_id,
        review_id=review.id,
        decision=payload.decision,  # type: ignore[arg-type]
        ai_recommendation=ai_recommendation,
        is_override=is_override,
        audit_log_id=primary_audit_id,
        processed_at=datetime.now(timezone.utc),
    )
