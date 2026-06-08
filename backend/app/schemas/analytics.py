"""
app/schemas/analytics.py

Pydantic v2 schemas for the analytics / eval metrics endpoint.
Matches the API contract defined in SYSTEM.md §5 for GET /api/analytics/eval-metrics.
"""

from pydantic import BaseModel, Field


class OverrideBreakdown(BaseModel):
    """Breakdown of how human overrides differ from AI recommendations."""

    # Fraction of total reviews where AI approved but human rejected
    ai_approve_human_reject: float = Field(..., ge=0.0, le=1.0)
    # Fraction where AI rejected but human approved (costly false positives)
    ai_reject_human_approve: float = Field(..., ge=0.0, le=1.0)
    # Fraction where AI escalated but human approved without escalation
    ai_escalate_human_approve: float = Field(..., ge=0.0, le=1.0)


class AIPerformance(BaseModel):
    """AI model performance metrics over the reporting period."""

    # % of cases where human agreed with AI recommendation
    accuracy_rate: float = Field(..., ge=0.0, le=1.0, description="Human-AI agreement rate")
    # % of cases where human overrode AI recommendation
    override_rate: float = Field(..., ge=0.0, le=1.0, description="Human override rate")
    # % of cases where AI rejected but human approved (costly false positives)
    false_positive_rate: float = Field(
        ..., ge=0.0, le=1.0, description="AI REJECT -> human APPROVE rate"
    )
    override_breakdown: OverrideBreakdown
    # Median AI analysis latency
    avg_processing_time_ms: float = Field(..., description="Average AI processing time in ms")
    # Average time a human reviewer spends on a campaign
    avg_human_review_time_minutes: float = Field(
        ..., description="Average human review duration in minutes"
    )


class Throughput(BaseModel):
    """Volume and efficiency metrics."""

    # Campaigns resolved entirely by AI (no human needed)
    ai_auto_resolved: int
    # Campaigns that required a human decision
    required_human_review: int
    # Estimated hours saved by AI pre-screening (based on avg_human_review_time)
    human_time_saved_hours: float


class RiskDistributionMetrics(BaseModel):
    """Proportion of campaigns at each risk level."""

    LOW: float = Field(..., ge=0.0, le=1.0)
    MEDIUM: float = Field(..., ge=0.0, le=1.0)
    HIGH: float = Field(..., ge=0.0, le=1.0)


class EvalMetricsResponse(BaseModel):
    """Full eval metrics response for the analytics dashboard."""

    period: str = Field("last_30_days", description="Reporting period label")
    total_campaigns: int = Field(..., description="Total campaigns processed in the period")
    ai_performance: AIPerformance
    throughput: Throughput
    risk_distribution: RiskDistributionMetrics
