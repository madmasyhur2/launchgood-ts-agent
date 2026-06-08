"""
app/routers/analytics.py

Analytics / eval metrics endpoints:
  GET  /analytics/eval-metrics        — Aggregated AI performance metrics
  POST /analytics/run-deterministic   — Trigger the deterministic eval suite
  GET  /analytics/eval-metrics/schema — Describe what each metric means

Metrics are computed via app.evals.metrics (independently testable functions).
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.evals.metrics import compute_all_metrics, OverrideBreakdown as MetricsOverrideBreakdown
from app.schemas.analytics import (
    AIPerformance,
    EvalMetricsResponse,
    OverrideBreakdown,
    RiskDistributionMetrics,
    Throughput,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


# ---------------------------------------------------------------------------
# GET /analytics/eval-metrics
# ---------------------------------------------------------------------------

@router.get(
    "/eval-metrics",
    response_model=EvalMetricsResponse,
    summary="Get AI performance evaluation metrics",
    description=(
        "Computes real-time eval metrics from the database. "
        "Returns accuracy rate, override rate, false positive rate, "
        "processing time, throughput, and risk distribution. "
        "All metrics are from the `period_days` lookback window."
    ),
)
async def get_eval_metrics(
    period_days: int = Query(
        30,
        ge=1,
        le=365,
        description="Number of days to look back (default: 30)",
    ),
    db: AsyncSession = Depends(get_db),
) -> EvalMetricsResponse:
    """
    Computes real-time eval metrics from the database using the eval framework.

    Metrics explained (SYSTEM.md §8):
      - accuracy_rate: % reviews where human agreed with AI (target > 85%)
      - override_rate: % reviews where human overrode AI (target < 15%)
      - false_positive_rate: AI REJECT → human APPROVE (target < 5%)
      - avg_processing_time_ms: AI analysis latency (target P95 < 10s)
      - risk_distribution: LOW/MEDIUM/HIGH split across all campaigns
      - human_time_saved_hours: estimated reviewer time saved by AI pre-screening
    """
    try:
        metrics = await compute_all_metrics(db, period_days=period_days)
    except Exception as exc:
        logger.exception("[analytics] Failed to compute metrics: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to compute eval metrics")

    period_label = f"last_{period_days}_days"
    bd = metrics.ai_performance.override_breakdown

    return EvalMetricsResponse(
        period=period_label,
        total_campaigns=metrics.throughput.total_campaigns,
        ai_performance=AIPerformance(
            accuracy_rate=metrics.ai_performance.accuracy_rate,
            override_rate=metrics.ai_performance.override_rate,
            false_positive_rate=metrics.ai_performance.false_positive_rate,
            override_breakdown=OverrideBreakdown(
                ai_approve_human_reject=bd.ai_approve_human_reject,
                ai_reject_human_approve=bd.ai_reject_human_approve,
                ai_escalate_human_approve=bd.ai_escalate_human_approve,
            ),
            avg_processing_time_ms=metrics.ai_performance.avg_processing_time_ms,
            avg_human_review_time_minutes=metrics.ai_performance.avg_human_review_time_minutes,
        ),
        throughput=Throughput(
            ai_auto_resolved=metrics.throughput.ai_auto_resolved,
            required_human_review=metrics.throughput.required_human_review,
            human_time_saved_hours=metrics.throughput.human_time_saved_hours,
        ),
        risk_distribution=RiskDistributionMetrics(
            LOW=metrics.risk_distribution.LOW,
            MEDIUM=metrics.risk_distribution.MEDIUM,
            HIGH=metrics.risk_distribution.HIGH,
        ),
    )


# ---------------------------------------------------------------------------
# POST /analytics/run-deterministic
# ---------------------------------------------------------------------------

class DeterministicEvalResponse(EvalMetricsResponse.__base__):  # type: ignore
    """Response schema for the deterministic eval run endpoint."""
    pass


from pydantic import BaseModel


class EvalRunResponse(BaseModel):
    """Response for POST /analytics/run-deterministic."""
    total: int
    passed: int
    failed: int
    pass_rate: float
    results: list[dict]


@router.post(
    "/run-deterministic",
    response_model=EvalRunResponse,
    summary="Run deterministic eval suite",
    description=(
        "Triggers the full deterministic eval suite against the live agent pipeline. "
        "Returns pass/fail results for all 9 eval cases. "
        "Does NOT require a database — tests the agent logic directly. "
        "Note: Each eval makes LangGraph calls so this takes ~10-30 seconds."
    ),
    tags=["analytics", "evals"],
)
async def run_deterministic_evals_endpoint() -> EvalRunResponse:
    """
    Runs all deterministic evals and returns a structured report.
    Useful for CI/CD health checks and monitoring.
    """
    from app.evals.deterministic import run_all, summarise
    try:
        results = await run_all()
        summary = summarise(results)
        logger.info(
            "[analytics] Deterministic evals: %d/%d passed",
            summary["passed"],
            summary["total"],
        )
        return EvalRunResponse(**summary)
    except Exception as exc:
        logger.exception("[analytics] Deterministic eval run failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Eval run failed: {exc}")


# ---------------------------------------------------------------------------
# GET /analytics/eval-metrics/targets
# ---------------------------------------------------------------------------

class MetricTarget(BaseModel):
    """Description of a single metric and its target threshold."""
    metric: str
    description: str
    target: str
    measurement: str


class MetricsSchemaResponse(BaseModel):
    """Response for the metrics schema endpoint."""
    metrics: list[MetricTarget]
    source: str


@router.get(
    "/eval-metrics/targets",
    response_model=MetricsSchemaResponse,
    summary="Get eval metric definitions and targets",
    description="Returns descriptions and target thresholds for all eval metrics.",
    tags=["analytics"],
)
async def get_eval_metrics_targets() -> MetricsSchemaResponse:
    """Describes each metric, its target, and how it's measured."""
    return MetricsSchemaResponse(
        source="SYSTEM.md §8",
        metrics=[
            MetricTarget(
                metric="accuracy_rate",
                description="Fraction of reviewed campaigns where human agreed with AI recommendation",
                target="> 85%",
                measurement="1 - override_rate",
            ),
            MetricTarget(
                metric="override_rate",
                description="Fraction of reviewed campaigns where human overrode AI decision",
                target="< 15%",
                measurement="overrides / total_reviews",
            ),
            MetricTarget(
                metric="false_positive_rate",
                description="AI recommended REJECT but human approved (costly errors)",
                target="< 5%",
                measurement="(AI_REJECT → human_APPROVE) / total_reviews",
            ),
            MetricTarget(
                metric="avg_processing_time_ms",
                description="Average AI analysis latency in milliseconds",
                target="P95 < 10,000ms",
                measurement="avg(ai_analyses.processing_time_ms)",
            ),
            MetricTarget(
                metric="avg_human_review_time_minutes",
                description="Average time a human reviewer spends per campaign",
                target="< 5 minutes",
                measurement="avg(review_completed_at - review_started_at) [baseline: 4.2 min]",
            ),
            MetricTarget(
                metric="human_time_saved_hours",
                description="Estimated reviewer hours saved by AI pre-screening",
                target="Maximise",
                measurement="ai_auto_resolved × avg_human_review_minutes / 60",
            ),
            MetricTarget(
                metric="reasoning_quality",
                description="LLM-as-judge score for reasoning summary quality",
                target="> 3.5/5.0",
                measurement="avg(clarity, completeness, actionability, accuracy) via LLM judge",
            ),
        ],
    )
