"""
tests/test_evals.py

Eval framework tests — validates both the deterministic suite and
individual metric logic without requiring a database.

Run with: uv run pytest tests/test_evals.py -v
"""

import pytest

from app.agent.graph import run_analysis
from app.evals.deterministic import (
    EvalResult,
    eval_ofac_always_high_risk,
    eval_verified_uk_low_risk,
    eval_high_risk_country_medium,
    eval_processing_time_sla,
    eval_confidence_in_valid_range,
    eval_decision_always_valid,
    eval_risk_score_bounded,
    eval_reasoning_summary_quality,
    eval_risk_dimensions_complete,
    run_all,
    summarise,
)
from app.evals.llm_judge import JudgeScores, score_reasoning


# =============================================================================
# Deterministic eval suite — individual function tests
# (These run the actual agent pipeline, same as test_agent.py)
# =============================================================================

@pytest.mark.asyncio
async def test_eval_ofac_always_high_risk():
    """All 7 OFAC-sanctioned countries must produce HIGH/REJECT."""
    result = await eval_ofac_always_high_risk()
    assert result.passed, f"OFAC eval failed: {result.message}"


@pytest.mark.asyncio
async def test_eval_verified_uk_low_risk():
    """Verified UK campaign must produce LOW/APPROVE with score < 30."""
    result = await eval_verified_uk_low_risk()
    assert result.passed, f"UK low-risk eval failed: {result.message}"


@pytest.mark.asyncio
async def test_eval_high_risk_country_medium():
    """Somalia campaign must produce MEDIUM/ESCALATE."""
    result = await eval_high_risk_country_medium()
    assert result.passed, f"High-risk country eval failed: {result.message}"


@pytest.mark.asyncio
async def test_eval_processing_time_sla():
    """Processing time must be < 10,000ms for all test campaigns."""
    result = await eval_processing_time_sla()
    assert result.passed, f"SLA eval failed: {result.message}"


@pytest.mark.asyncio
async def test_eval_confidence_in_valid_range():
    """Confidence must always be in [0.0, 1.0]."""
    result = await eval_confidence_in_valid_range()
    assert result.passed, f"Confidence range eval failed: {result.message}"


@pytest.mark.asyncio
async def test_eval_decision_always_valid():
    """Recommendation and risk_level must always be valid enum values."""
    result = await eval_decision_always_valid()
    assert result.passed, f"Valid enum eval failed: {result.message}"


@pytest.mark.asyncio
async def test_eval_risk_score_bounded():
    """Risk score must always be an integer in [0, 100]."""
    result = await eval_risk_score_bounded()
    assert result.passed, f"Score bounds eval failed: {result.message}"


@pytest.mark.asyncio
async def test_eval_reasoning_summary_quality():
    """Reasoning summary must be non-empty and within length bounds."""
    result = await eval_reasoning_summary_quality()
    assert result.passed, f"Reasoning quality eval failed: {result.message}"


@pytest.mark.asyncio
async def test_eval_risk_dimensions_complete():
    """All 4 risk dimensions must be present in every result."""
    result = await eval_risk_dimensions_complete()
    assert result.passed, f"Risk dimensions eval failed: {result.message}"


# =============================================================================
# run_all() suite runner
# =============================================================================

@pytest.mark.asyncio
async def test_run_all_returns_all_evals():
    """run_all() must return exactly one result per registered eval."""
    from app.evals.deterministic import ALL_EVALS
    results = await run_all()
    assert len(results) == len(ALL_EVALS), (
        f"Expected {len(ALL_EVALS)} results, got {len(results)}"
    )


@pytest.mark.asyncio
async def test_summarise_structure():
    """summarise() must return a dict with the required keys."""
    results = [
        EvalResult("a", True, "ok", 100),
        EvalResult("b", False, "fail", 200),
        EvalResult("c", True, "ok", 50),
    ]
    summary = summarise(results)
    assert summary["total"] == 3
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert abs(summary["pass_rate"] - 2/3) < 0.001
    assert len(summary["results"]) == 3


# =============================================================================
# LLM judge — structural tests (no API key needed)
# =============================================================================

@pytest.mark.asyncio
async def test_llm_judge_returns_fallback_without_api_key():
    """LLM judge must return a fallback (not raise) when no API key configured."""
    scores = await score_reasoning(
        reasoning_summary="This campaign received a HIGH risk score due to OFAC sanctions.",
        risk_score=85,
        risk_level="HIGH",
        recommendation="REJECT",
        flags=["ofac_sanctioned_beneficiary_country"],
    )
    # Either real scores or fallback — must never raise
    assert isinstance(scores, JudgeScores)
    # overall_score is always a valid float
    assert isinstance(scores.overall_score, float)


def test_judge_scores_overall_score_calculation():
    """JudgeScores.overall_score must compute the weighted average correctly."""
    scores = JudgeScores(
        clarity=5,
        completeness=4,
        actionability=3,
        accuracy=5,
        rationale="Test rationale.",
    )
    # weights: clarity=0.30, completeness=0.25, actionability=0.20, accuracy=0.25
    expected = 5 * 0.30 + 4 * 0.25 + 3 * 0.20 + 5 * 0.25
    assert abs(scores.overall_score - expected) < 0.01


def test_judge_scores_as_dict():
    """JudgeScores.as_dict() must include all required keys."""
    scores = JudgeScores(
        clarity=4, completeness=4, actionability=3, accuracy=4,
        rationale="Test."
    )
    d = scores.as_dict()
    assert "clarity" in d
    assert "completeness" in d
    assert "actionability" in d
    assert "accuracy" in d
    assert "overall_score" in d
    assert "rationale" in d


# =============================================================================
# Legacy tests from original test_evals.py (kept for backward compatibility)
# =============================================================================

@pytest.mark.asyncio
async def test_override_detected_when_human_differs():
    """Override is correctly detected when human and AI decisions differ."""
    ai_rec = "APPROVE"
    human_decision = "REJECT"
    is_override = ai_rec != human_decision
    assert is_override is True


@pytest.mark.asyncio
async def test_no_override_when_human_agrees():
    """No override when human agrees with AI."""
    ai_rec = "ESCALATE"
    human_decision = "ESCALATE"
    is_override = ai_rec != human_decision
    assert is_override is False


@pytest.mark.asyncio
async def test_all_risk_levels_covered():
    """Ensure all three risk levels can be produced by the agent."""
    scenarios = [
        ("GB", "LOW"),
        ("SO", "MEDIUM"),
        ("SY", "HIGH"),
    ]
    results = []
    for country, expected_level in scenarios:
        campaign = {
            "title": f"Test {expected_level}",
            "story": "A detailed story with enough context for analysis.",
            "category": "humanitarian",
            "goal_amount": 5000,
            "currency": "USD",
            "creator": {
                "name": "Test",
                "email": "t@t.com",
                "country": "US",
                "account_age_days": 400,
            },
            "beneficiary_country": country,
            "organization_name": "Test Org",
            "documents": [],
        }
        result = await run_analysis(f"eval-test-{country}", campaign)
        results.append(result.risk_level)
        assert result.risk_level == expected_level, (
            f"Expected {expected_level} for {country}, got {result.risk_level}"
        )

    assert "LOW" in results
    assert "MEDIUM" in results
    assert "HIGH" in results
