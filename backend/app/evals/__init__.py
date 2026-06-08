"""
app/evals/__init__.py

Eval framework for the LaunchGood T&S Agent.

Three modules:
  deterministic  — Rule-based unit tests for the agent pipeline
  llm_judge      — LLM-as-judge reasoning quality scorer
  metrics        — Database-driven performance metric calculators
"""

from app.evals.deterministic import (
    EvalResult,
    ALL_EVALS,
    run_all as run_deterministic_evals,
    summarise as summarise_evals,
)
from app.evals.llm_judge import (
    JudgeScores,
    score_reasoning,
    score_agent_result,
)
from app.evals.metrics import (
    EvalMetrics,
    AIPerformanceMetrics,
    ThroughputMetrics,
    RiskDistribution,
    OverrideBreakdown,
    compute_all_metrics,
    accuracy_rate,
    override_rate,
    false_positive_rate,
    avg_processing_time_ms,
    avg_human_review_time_minutes,
    human_time_saved_hours,
)

__all__ = [
    # deterministic
    "EvalResult",
    "ALL_EVALS",
    "run_deterministic_evals",
    "summarise_evals",
    # llm_judge
    "JudgeScores",
    "score_reasoning",
    "score_agent_result",
    # metrics
    "EvalMetrics",
    "AIPerformanceMetrics",
    "ThroughputMetrics",
    "RiskDistribution",
    "OverrideBreakdown",
    "compute_all_metrics",
    "accuracy_rate",
    "override_rate",
    "false_positive_rate",
    "avg_processing_time_ms",
    "avg_human_review_time_minutes",
    "human_time_saved_hours",
]
