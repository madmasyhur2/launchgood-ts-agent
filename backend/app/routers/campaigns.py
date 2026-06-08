"""
app/routers/campaigns.py

Campaign-related API endpoints:
  POST /campaigns/submit           — Accept a new campaign for AI review
  GET  /campaigns/queue            — Paginated queue with filter support
  GET  /campaigns/{id}/analysis    — Full AI analysis detail for one campaign

Note: The AI agent (LangGraph) is not wired yet — this session stubs out
the analysis with pre-computed mock data injected at seed time. The agent
integration is planned for Session 2.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.ai_analysis import AIAnalysis
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.schemas.campaign import (
    AIAnalysisDetail,
    CampaignAnalysisResponse,
    CampaignQueueItem,
    CampaignQueueResponse,
    CampaignSubmitRequest,
    CampaignSubmitResponse,
)
from app.schemas.common import AnalysisFlag, RiskDimension

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


# =============================================================================
# POST /campaigns/submit
# =============================================================================

@router.post(
    "/submit",
    response_model=CampaignSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a campaign for AI-assisted Trust & Safety review",
)
async def submit_campaign(
    payload: CampaignSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> CampaignSubmitResponse:
    """
    Accepts a campaign submission, persists it to the database, and queues it
    for asynchronous AI analysis.

    In this session the Celery worker is not active yet, so the campaign
    lands in 'pending' status. Once the agent is wired (Session 2) the status
    will transition to 'analyzing' → 'completed'.
    """
    # Build the ORM object — store creator info denormalised for fast queue queries
    campaign = Campaign(
        title=payload.title,
        story=payload.story,
        category=payload.category,
        goal_amount=payload.goal_amount,
        currency=payload.currency,
        creator_name=payload.creator.name,
        creator_email=payload.creator.email,
        creator_country=payload.creator.country,
        creator_account_age_days=payload.creator.account_age_days,
        beneficiary_country=payload.beneficiary_country,
        organization_name=payload.organization_name,
        status="pending",
        # Persist the full raw payload for re-analysis / debugging
        raw_data=payload.model_dump(),
    )
    db.add(campaign)
    await db.flush()  # Get the generated UUID before creating audit log

    # Log the submission event for audit trail
    audit = AuditLog(
        campaign_id=campaign.id,
        event_type="campaign_submitted",
        actor="system",
        actor_id="api",
        payload={
            "title": payload.title,
            "goal_amount": payload.goal_amount,
            "currency": payload.currency,
            "beneficiary_country": payload.beneficiary_country,
        },
    )
    db.add(audit)
    # Session commit happens automatically via get_db dependency

    return CampaignSubmitResponse(
        campaign_id=campaign.id,
        status="queued",
        estimated_analysis_seconds=15,
    )


# =============================================================================
# GET /campaigns/queue
# =============================================================================

@router.get(
    "/queue",
    response_model=CampaignQueueResponse,
    summary="Get the campaign review queue",
)
async def get_campaign_queue(
    status: str | None = Query(
        None,
        description="Filter by campaign status (pending, completed, approved, rejected)",
    ),
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] | None = Query(
        None,
        description="Filter by AI-assessed risk level",
    ),
    recommendation: Literal["APPROVE", "ESCALATE", "REJECT"] | None = Query(
        None,
        description="Filter by AI recommendation",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_db),
) -> CampaignQueueResponse:
    """
    Returns a paginated, filterable list of campaigns awaiting human review.
    Results are sorted by risk score descending (highest risk first) so
    reviewers see the most critical campaigns at the top.
    """
    # -------------------------------------------------------------------------
    # Build the base query
    # -------------------------------------------------------------------------
    base_query = select(Campaign)

    # Apply optional filters
    if status:
        base_query = base_query.where(Campaign.status == status)
    if risk_level:
        base_query = base_query.where(Campaign.ai_risk_level == risk_level)
    if recommendation:
        base_query = base_query.where(Campaign.ai_recommendation == recommendation)

    # -------------------------------------------------------------------------
    # Count queries (total matching + total pending)
    # -------------------------------------------------------------------------
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    pending_query = select(func.count()).where(Campaign.status == "pending")
    pending_result = await db.execute(pending_query)
    pending = pending_result.scalar_one()

    # -------------------------------------------------------------------------
    # Paginated result — sort by risk score DESC (nulls last)
    # -------------------------------------------------------------------------
    offset = (page - 1) * limit
    items_query = (
        base_query
        .order_by(Campaign.ai_risk_score.desc().nulls_last(), Campaign.submitted_at.asc())
        .offset(offset)
        .limit(limit)
    )
    items_result = await db.execute(items_query)
    campaigns = items_result.scalars().all()

    # -------------------------------------------------------------------------
    # Build response items
    # -------------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    queue_items = []
    for c in campaigns:
        # Calculate how long the campaign has been waiting
        submitted = c.submitted_at
        if submitted.tzinfo is None:
            # Ensure timezone-aware comparison
            submitted = submitted.replace(tzinfo=timezone.utc)
        time_in_queue = (now - submitted).total_seconds() / 60.0

        queue_items.append(
            CampaignQueueItem(
                campaign_id=c.id,
                title=c.title,
                category=c.category,
                goal_amount=float(c.goal_amount) if c.goal_amount else None,
                currency=c.currency,
                creator_country=c.creator_country,
                beneficiary_country=c.beneficiary_country,
                status=c.status,
                risk_score=c.ai_risk_score,
                risk_level=c.ai_risk_level,  # type: ignore[arg-type]
                recommendation=c.ai_recommendation,  # type: ignore[arg-type]
                submitted_at=c.submitted_at,
                time_in_queue_minutes=round(time_in_queue, 1),
            )
        )

    return CampaignQueueResponse(
        total=total,
        pending=pending,
        page=page,
        limit=limit,
        items=queue_items,
    )


# =============================================================================
# GET /campaigns/{campaign_id}/analysis
# =============================================================================

@router.get(
    "/{campaign_id}/analysis",
    response_model=CampaignAnalysisResponse,
    summary="Get full AI analysis for a specific campaign",
)
async def get_campaign_analysis(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CampaignAnalysisResponse:
    """
    Returns the campaign's details and its most recent AI analysis.
    If no analysis has been run yet, ai_analysis will be None.
    """
    # Load campaign with its analyses (eager load to avoid N+1)
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(selectinload(Campaign.analyses))
    )
    campaign = result.scalar_one_or_none()

    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    # Grab the most recent analysis (analyses are ordered by created_at DESC)
    latest_analysis: AIAnalysis | None = campaign.analyses[0] if campaign.analyses else None

    # Build the AI analysis detail if available
    ai_analysis_detail: AIAnalysisDetail | None = None
    if latest_analysis:
        # Deserialise JSONB risk_dimensions into typed RiskDimension objects
        parsed_dimensions: dict[str, RiskDimension] | None = None
        if latest_analysis.risk_dimensions:
            parsed_dimensions = {
                key: RiskDimension(**val)
                for key, val in latest_analysis.risk_dimensions.items()
            }

        # Deserialise JSONB flags into typed AnalysisFlag objects
        parsed_flags: list[AnalysisFlag] | None = None
        if latest_analysis.flags:
            parsed_flags = [AnalysisFlag(**f) for f in latest_analysis.flags]

        ai_analysis_detail = AIAnalysisDetail(
            risk_score=latest_analysis.risk_score,
            risk_level=latest_analysis.risk_level,  # type: ignore[arg-type]
            recommendation=latest_analysis.recommendation,  # type: ignore[arg-type]
            confidence=float(latest_analysis.confidence) if latest_analysis.confidence else None,
            reasoning_summary=latest_analysis.reasoning_summary,
            risk_dimensions=parsed_dimensions,
            flags=parsed_flags,
            processing_time_ms=latest_analysis.processing_time_ms,
            model_version=latest_analysis.model_version,
            analyzed_at=latest_analysis.created_at,
        )

    return CampaignAnalysisResponse(
        campaign_id=campaign.id,
        title=campaign.title,
        story=campaign.story,
        category=campaign.category,
        goal_amount=float(campaign.goal_amount) if campaign.goal_amount else None,
        currency=campaign.currency,
        creator_name=campaign.creator_name,
        creator_country=campaign.creator_country,
        beneficiary_country=campaign.beneficiary_country,
        organization_name=campaign.organization_name,
        status=campaign.status,
        submitted_at=campaign.submitted_at,
        ai_analysis=ai_analysis_detail,
    )
