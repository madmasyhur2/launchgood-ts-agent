"""
app/evals/metrics.py

Database-driven eval metrics calculation for the analytics endpoint.

All functions accept a SQLAlchemy AsyncSession and an optional period_start
datetime, making them independently testable with a test database.

Metrics computed:
  - accuracy_rate         : % of reviewed campaigns where human agreed with AI
  - override_rate         : % where human overrode AI
  - false_positive_rate   : AI rejected but human approved (costly errors)
  - avg_processing_time_ms: average AI analysis latency
  - avg_human_review_time_minutes: average time per human review decision
  - human_time_saved_hours: estimated reviewer time saved by AI pre-screening

These functions are used by the analytics router but are also directly
importable for ad-hoc analysis or the eval dashboard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_analysis import AIAnalysis
from app.models.campaign import Campaign
from app.models.review import Review

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Baseline constants (from SYSTEM.md §8 targets)
# ---------------------------------------------------------------------------

# Baseline human review time in minutes — used when no historical data exists
BASELINE_HUMAN_REVIEW_MINUTES: float = 4.2

# Target thresholds for dashboard status indicators
TARGET_ACCURACY_RATE: float = 0.85
TARGET_OVERRIDE_RATE: float = 0.15
TARGET_FALSE_POSITIVE_RATE: float = 0.05
TARGET_P95_PROCESSING_MS: float = 10_000.0


# ---------------------------------------------------------------------------
# Data classes for structured metric results
# ---------------------------------------------------------------------------

@dataclass
class OverrideBreakdown:
    """Detailed breakdown of human-AI override patterns."""
    ai_approve_human_reject: float = 0.0   # AI said approve, human said reject
    ai_reject_human_approve: float = 0.0   # AI said reject, human approved (false positive)
    ai_escalate_human_approve: float = 0.0 # AI escalated, human approved directly


@dataclass
class AIPerformanceMetrics:
    """AI model accuracy and latency metrics."""
    accuracy_rate: float = 0.0
    override_rate: float = 0.0
    false_positive_rate: float = 0.0
    override_breakdown: OverrideBreakdown = field(default_factory=OverrideBreakdown)
    avg_processing_time_ms: float = 0.0
    avg_human_review_time_minutes: float = BASELINE_HUMAN_REVIEW_MINUTES
    total_reviewed: int = 0
    total_overrides: int = 0


@dataclass
class ThroughputMetrics:
    """Volume and efficiency metrics."""
    total_campaigns: int = 0
    ai_auto_resolved: int = 0
    required_human_review: int = 0
    human_time_saved_hours: float = 0.0


@dataclass
class RiskDistribution:
    """Proportion of campaigns at each risk level."""
    LOW: float = 0.0
    MEDIUM: float = 0.0
    HIGH: float = 0.0


@dataclass
class EvalMetrics:
    """Complete set of eval metrics for the analytics endpoint."""
    period_days: int
    period_start: datetime
    ai_performance: AIPerformanceMetrics = field(default_factory=AIPerformanceMetrics)
    throughput: ThroughputMetrics = field(default_factory=ThroughputMetrics)
    risk_distribution: RiskDistribution = field(default_factory=RiskDistribution)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _safe_rate(numerator: int | float, denominator: int | float) -> float:
    """Safely compute numerator/denominator, returning 0.0 on division by zero."""
    if not denominator:
        return 0.0
    return round(numerator / denominator, 4)


# ---------------------------------------------------------------------------
# Individual metric calculators (independently testable)
# ---------------------------------------------------------------------------

async def accuracy_rate(
    db: AsyncSession,
    period_start: Optional[datetime] = None,
) -> float:
    """
    Calculate AI accuracy rate = 1 - override_rate.

    Accuracy is defined as the fraction of reviewed campaigns where the human
    reviewer agreed with the AI recommendation (is_override=False).

    Returns:
        Float in [0.0, 1.0]. Returns 0.0 if no reviews exist in the period.
    """
    start = period_start or (datetime.now(timezone.utc) - timedelta(days=30))

    result = await db.execute(
        select(
            func.count(Review.id).label("total"),
            func.sum(
                cast(Review.is_override, Integer)
            ).label("overrides"),
        ).where(Review.reviewed_at >= start)
    )
    row = result.one()
    total = row.total or 0
    overrides = int(row.overrides or 0)

    rate = _safe_rate(total - overrides, total)
    logger.debug("[metrics] accuracy_rate=%.4f (total=%d overrides=%d)", rate, total, overrides)
    return rate


async def override_rate(
    db: AsyncSession,
    period_start: Optional[datetime] = None,
) -> float:
    """
    Calculate human override rate = overrides / total_reviews.

    A review is an override when the human decision differs from the AI
    recommendation (Review.is_override=True).

    Returns:
        Float in [0.0, 1.0].
    """
    start = period_start or (datetime.now(timezone.utc) - timedelta(days=30))

    result = await db.execute(
        select(
            func.count(Review.id).label("total"),
            func.sum(cast(Review.is_override, Integer)).label("overrides"),
        ).where(Review.reviewed_at >= start)
    )
    row = result.one()
    total = row.total or 0
    overrides = int(row.overrides or 0)

    rate = _safe_rate(overrides, total)
    logger.debug("[metrics] override_rate=%.4f", rate)
    return rate


async def false_positive_rate(
    db: AsyncSession,
    period_start: Optional[datetime] = None,
) -> float:
    """
    Calculate false positive rate = (AI REJECT → human APPROVE) / total_reviews.

    False positives are the most costly error: legitimate campaigns are blocked.
    Target: < 5% (SYSTEM.md §8).

    Returns:
        Float in [0.0, 1.0].
    """
    start = period_start or (datetime.now(timezone.utc) - timedelta(days=30))

    # Denominator: total reviews in period
    total_result = await db.execute(
        select(func.count(Review.id)).where(Review.reviewed_at >= start)
    )
    total = total_result.scalar_one() or 0

    # Numerator: AI said REJECT but human said APPROVE
    fp_result = await db.execute(
        select(func.count(Review.id)).where(
            Review.reviewed_at >= start,
            Review.is_override.is_(True),
            Review.ai_recommendation == "REJECT",
            Review.decision == "APPROVE",
        )
    )
    false_positives = fp_result.scalar_one() or 0

    rate = _safe_rate(false_positives, total)
    logger.debug("[metrics] false_positive_rate=%.4f (fp=%d total=%d)", rate, false_positives, total)
    return rate


async def avg_processing_time_ms(
    db: AsyncSession,
    period_start: Optional[datetime] = None,
) -> float:
    """
    Calculate average AI processing time in milliseconds.

    Returns:
        Float. Falls back to 2850.0ms baseline if no data exists.
    """
    start = period_start or (datetime.now(timezone.utc) - timedelta(days=30))

    result = await db.execute(
        select(func.avg(AIAnalysis.processing_time_ms)).where(
            AIAnalysis.created_at >= start,
            AIAnalysis.processing_time_ms.is_not(None),
        )
    )
    avg = result.scalar_one()
    value = float(avg) if avg is not None else 2850.0
    logger.debug("[metrics] avg_processing_time_ms=%.1f", value)
    return round(value, 1)


async def avg_human_review_time_minutes(
    db: AsyncSession,
    period_start: Optional[datetime] = None,
) -> float:
    """
    Estimate average human review time per campaign in minutes.

    Since we don't track reviewer session duration in v1, this uses the
    baseline from SYSTEM.md §8 (4.2 minutes). In a production system,
    this would compute: (review_completed_at - review_started_at).mean().

    Returns:
        Float minutes. Always returns the baseline for now.
    """
    # TODO (v2): track reviewer session start time and compute real duration
    return BASELINE_HUMAN_REVIEW_MINUTES


async def human_time_saved_hours(
    db: AsyncSession,
    period_start: Optional[datetime] = None,
    avg_review_minutes: float = BASELINE_HUMAN_REVIEW_MINUTES,
) -> float:
    """
    Estimate hours saved by AI pre-screening.

    Calculation: campaigns where AI recommended APPROVE and human agreed
    (auto-resolved) × avg_review_minutes / 60.

    This represents campaigns that would have required full human review
    without AI pre-screening.

    Returns:
        Float hours saved.
    """
    start = period_start or (datetime.now(timezone.utc) - timedelta(days=30))

    # Campaigns AI auto-resolved: LOW risk that were approved without override
    auto_result = await db.execute(
        select(func.count(Campaign.id)).where(
            Campaign.submitted_at >= start,
            Campaign.ai_risk_level == "LOW",
            Campaign.status == "approved",
        )
    )
    auto_resolved = auto_result.scalar_one() or 0

    saved = round((auto_resolved * avg_review_minutes) / 60, 2)
    logger.debug("[metrics] human_time_saved_hours=%.2f (auto_resolved=%d)", saved, auto_resolved)
    return saved


async def override_breakdown(
    db: AsyncSession,
    period_start: Optional[datetime] = None,
) -> OverrideBreakdown:
    """
    Compute detailed override breakdown by pattern.

    Returns:
        OverrideBreakdown with three rates (fractions of total reviews).
    """
    start = period_start or (datetime.now(timezone.utc) - timedelta(days=30))

    total_result = await db.execute(
        select(func.count(Review.id)).where(Review.reviewed_at >= start)
    )
    total = total_result.scalar_one() or 1  # avoid division by zero

    async def _count_pattern(ai_rec: str, human_dec: str) -> int:
        r = await db.execute(
            select(func.count(Review.id)).where(
                Review.reviewed_at >= start,
                Review.is_override.is_(True),
                Review.ai_recommendation == ai_rec,
                Review.decision == human_dec,
            )
        )
        return r.scalar_one() or 0

    approve_to_reject  = await _count_pattern("APPROVE",  "REJECT")
    reject_to_approve  = await _count_pattern("REJECT",   "APPROVE")
    escalate_to_approve = await _count_pattern("ESCALATE", "APPROVE")

    return OverrideBreakdown(
        ai_approve_human_reject=_safe_rate(approve_to_reject, total),
        ai_reject_human_approve=_safe_rate(reject_to_approve, total),
        ai_escalate_human_approve=_safe_rate(escalate_to_approve, total),
    )


async def risk_distribution(
    db: AsyncSession,
    period_start: Optional[datetime] = None,
) -> RiskDistribution:
    """
    Compute the proportion of campaigns at each risk level.

    Returns:
        RiskDistribution with LOW/MEDIUM/HIGH fractions (sum ≈ 1.0).
    """
    start = period_start or (datetime.now(timezone.utc) - timedelta(days=30))

    result = await db.execute(
        select(
            Campaign.ai_risk_level,
            func.count(Campaign.id).label("count"),
        )
        .where(
            Campaign.submitted_at >= start,
            Campaign.ai_risk_level.is_not(None),
        )
        .group_by(Campaign.ai_risk_level)
    )
    rows = result.all()

    counts: dict[str, int] = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    for row in rows:
        if row.ai_risk_level in counts:
            counts[row.ai_risk_level] = row.count

    total = sum(counts.values())
    return RiskDistribution(
        LOW=_safe_rate(counts["LOW"], total),
        MEDIUM=_safe_rate(counts["MEDIUM"], total),
        HIGH=_safe_rate(counts["HIGH"], total),
    )


# ---------------------------------------------------------------------------
# Composite metric builder
# ---------------------------------------------------------------------------

async def compute_all_metrics(
    db: AsyncSession,
    period_days: int = 30,
) -> EvalMetrics:
    """
    Compute all eval metrics for the given period in a single call.

    This is the primary function used by the analytics router.
    All sub-queries are run sequentially (simple) — could be parallelised
    with asyncio.gather() for high-traffic deployments.

    Args:
        db: SQLAlchemy async session.
        period_days: Number of days to look back (default: 30).

    Returns:
        EvalMetrics dataclass with all computed values.
    """
    period_start = datetime.now(timezone.utc) - timedelta(days=period_days)
    logger.info("[metrics] Computing eval metrics for last %d days", period_days)

    # AI performance
    acc_rate = await accuracy_rate(db, period_start)
    ovr_rate = await override_rate(db, period_start)
    fp_rate = await false_positive_rate(db, period_start)
    breakdown = await override_breakdown(db, period_start)
    avg_proc_ms = await avg_processing_time_ms(db, period_start)
    avg_human_min = await avg_human_review_time_minutes(db, period_start)

    # Counts for override totals
    total_result = await db.execute(
        select(
            func.count(Review.id).label("total"),
            func.sum(cast(Review.is_override, Integer)).label("overrides"),
        ).where(Review.reviewed_at >= period_start)
    )
    review_row = total_result.one()
    total_reviewed = review_row.total or 0
    total_overrides = int(review_row.overrides or 0)

    # Total campaigns
    total_camps_result = await db.execute(
        select(func.count(Campaign.id)).where(Campaign.submitted_at >= period_start)
    )
    total_campaigns = total_camps_result.scalar_one() or 0

    # Throughput
    auto_result = await db.execute(
        select(func.count(Campaign.id)).where(
            Campaign.submitted_at >= period_start,
            Campaign.ai_risk_level == "LOW",
            Campaign.status == "approved",
        )
    )
    ai_auto_resolved = auto_result.scalar_one() or 0
    time_saved = round((ai_auto_resolved * avg_human_min) / 60, 2)

    # Risk distribution
    dist = await risk_distribution(db, period_start)

    return EvalMetrics(
        period_days=period_days,
        period_start=period_start,
        ai_performance=AIPerformanceMetrics(
            accuracy_rate=acc_rate,
            override_rate=ovr_rate,
            false_positive_rate=fp_rate,
            override_breakdown=breakdown,
            avg_processing_time_ms=avg_proc_ms,
            avg_human_review_time_minutes=avg_human_min,
            total_reviewed=total_reviewed,
            total_overrides=total_overrides,
        ),
        throughput=ThroughputMetrics(
            total_campaigns=total_campaigns,
            ai_auto_resolved=ai_auto_resolved,
            required_human_review=total_reviewed,
            human_time_saved_hours=time_saved,
        ),
        risk_distribution=dist,
    )
