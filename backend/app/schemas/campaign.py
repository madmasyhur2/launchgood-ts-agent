"""
app/schemas/campaign.py

Pydantic v2 schemas for campaign submission, queue listing, and AI analysis responses.
Matches the API contract defined in SYSTEM.md §5.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import AnalysisFlag, RiskDimension


# =============================================================================
# POST /api/campaigns/submit — Request & Response
# =============================================================================

class CreatorInfo(BaseModel):
    """Creator (campaign organiser) details submitted with the campaign."""

    name: str = Field(..., min_length=1, max_length=255, description="Creator's full name")
    email: EmailStr = Field(..., description="Creator's email address")
    country: str = Field(
        ...,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code of the creator",
    )
    account_age_days: int = Field(
        ...,
        ge=0,
        description="Number of days since account was created (0 = brand new)",
    )


class CampaignSubmitRequest(BaseModel):
    """Request body for POST /api/campaigns/submit."""

    title: str = Field(..., min_length=5, max_length=500, description="Campaign title")
    story: str | None = Field(
        None,
        max_length=50_000,
        description="Full campaign story / description",
    )
    category: str | None = Field(
        None,
        max_length=50,
        description="Campaign category (e.g. 'humanitarian', 'education', 'medical')",
    )
    goal_amount: float = Field(..., gt=0, description="Fundraising goal in the specified currency")
    currency: str = Field("USD", min_length=3, max_length=3, description="ISO 4217 currency code")
    creator: CreatorInfo
    beneficiary_country: str | None = Field(
        None,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code where funds will be used",
    )
    organization_name: str | None = Field(
        None,
        max_length=255,
        description="Name of the beneficiary organisation (if applicable)",
    )
    documents: list[str] = Field(
        default_factory=list,
        description="URLs to supporting documents (IDs, charity registration, etc.)",
    )

    model_config = {"json_schema_extra": {
        "example": {
            "title": "Build a Water Well in Somalia",
            "story": "Our community in Mogadishu needs clean water access...",
            "category": "humanitarian",
            "goal_amount": 15000,
            "currency": "USD",
            "creator": {
                "name": "Ahmad Hassan",
                "email": "ahmad@example.com",
                "country": "US",
                "account_age_days": 245,
            },
            "beneficiary_country": "SO",
            "organization_name": "Al-Noor Foundation",
            "documents": ["https://example.com/doc1.pdf"],
        }
    }}


class CampaignSubmitResponse(BaseModel):
    """Response after a campaign is accepted into the review queue."""

    campaign_id: uuid.UUID
    status: Literal["queued", "analyzing", "completed"] = "queued"
    estimated_analysis_seconds: int = Field(
        15,
        description="Estimated seconds before AI analysis is complete",
    )


# =============================================================================
# GET /api/campaigns/queue — Response
# =============================================================================

class CampaignQueueItem(BaseModel):
    """A single row in the campaign review queue."""

    campaign_id: uuid.UUID
    title: str
    category: str | None
    goal_amount: float | None
    currency: str | None
    creator_country: str | None
    beneficiary_country: str | None
    status: str
    risk_score: int | None
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] | None
    recommendation: Literal["APPROVE", "ESCALATE", "REJECT"] | None
    submitted_at: datetime
    # Minutes since submission — computed at query time
    time_in_queue_minutes: float | None


class CampaignQueueResponse(BaseModel):
    """Paginated list of campaigns in the review queue."""

    total: int = Field(..., description="Total number of campaigns matching the filter")
    pending: int = Field(..., description="Number of campaigns awaiting human review")
    page: int
    limit: int
    items: list[CampaignQueueItem]


# =============================================================================
# GET /api/campaigns/{id}/analysis — Response
# =============================================================================

class AIAnalysisDetail(BaseModel):
    """Detailed AI analysis result embedded in the campaign analysis response."""

    risk_score: int = Field(..., ge=0, le=100)
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    recommendation: Literal["APPROVE", "ESCALATE", "REJECT"]
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    reasoning_summary: str | None
    risk_dimensions: dict[str, RiskDimension] | None
    flags: list[AnalysisFlag] | None
    processing_time_ms: int | None
    model_version: str | None
    analyzed_at: datetime


class CampaignAnalysisResponse(BaseModel):
    """Full campaign detail with embedded AI analysis."""

    campaign_id: uuid.UUID
    title: str
    story: str | None
    category: str | None
    goal_amount: float | None
    currency: str | None
    creator_name: str | None
    creator_country: str | None
    beneficiary_country: str | None
    organization_name: str | None
    status: str
    submitted_at: datetime
    # Latest AI analysis — None if analysis hasn't run yet
    ai_analysis: AIAnalysisDetail | None
