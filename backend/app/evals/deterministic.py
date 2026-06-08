"""
app/evals/deterministic.py

Deterministic (rule-based) eval suite for the LaunchGood T&S AI agent.

These tests are 100% deterministic — they do NOT require an LLM or database.
They run the agent pipeline against known inputs and assert exact outcomes.

Design principles (SYSTEM.md §8):
  - OFAC country MUST always produce HIGH risk + REJECT
  - Verified low-risk campaign MUST produce LOW + APPROVE
  - Processing SLA MUST be < 10 seconds
  - Confidence MUST be in [0.0, 1.0]
  - Recommendation MUST be one of {APPROVE, ESCALATE, REJECT}

Each eval function is independently callable and also collected by pytest
(they're async functions with the `eval_` prefix, runnable via pytest-asyncio).

Usage:
    # Run all deterministic evals programmatically:
    from app.evals.deterministic import run_all
    results = asyncio.run(run_all())

    # Or via pytest:
    uv run pytest tests/ -v -k "deterministic"
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.agent.graph import run_analysis
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    """Outcome of a single deterministic eval."""
    name: str
    passed: bool
    message: str
    duration_ms: int
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name} ({self.duration_ms}ms): {self.message}"


# ---------------------------------------------------------------------------
# Campaign fixture builder
# ---------------------------------------------------------------------------

def _make_campaign(
    title: str = "Test Campaign",
    story: str = (
        "A detailed story explaining how funds will be used transparently "
        "for the community benefit. All financial records are available."
    ),
    category: str = "humanitarian",
    goal_amount: float = 5000.0,
    currency: str = "USD",
    creator_name: str = "Test Creator",
    creator_email: str = "creator@example.org",
    creator_country: str = "US",
    account_age_days: int = 400,
    beneficiary_country: str = "GB",
    organization_name: str = "Registered Charity UK",
    documents: list[str] | None = None,
) -> dict:
    """Build a minimal campaign payload with sensible defaults."""
    return {
        "title": title,
        "story": story,
        "category": category,
        "goal_amount": goal_amount,
        "currency": currency,
        "creator": {
            "name": creator_name,
            "email": creator_email,
            "country": creator_country,
            "account_age_days": account_age_days,
        },
        "beneficiary_country": beneficiary_country,
        "organization_name": organization_name,
        "documents": documents or [],
    }


# ---------------------------------------------------------------------------
# Individual eval functions
# ---------------------------------------------------------------------------

async def eval_ofac_always_high_risk() -> EvalResult:
    """
    OFAC-sanctioned beneficiary country (Syria) must ALWAYS produce:
      - risk_level = HIGH
      - risk_score >= 70
      - recommendation = REJECT
    This is a hard compliance rule — no amount of positive signals should override it.
    """
    name = "ofac_country_always_high_risk"
    t0 = time.perf_counter()

    ofac_countries = [
        ("SY", "Syria"),
        ("IR", "Iran"),
        ("KP", "North Korea"),
        ("CU", "Cuba"),
        ("VE", "Venezuela"),
        ("BY", "Belarus"),
        ("ER", "Eritrea"),
    ]

    failures: list[str] = []
    for code, country_name in ofac_countries:
        campaign = _make_campaign(
            title=f"Aid Campaign - {country_name}",
            beneficiary_country=code,
            # Give the creator the most favourable profile possible —
            # OFAC should still force HIGH regardless
            account_age_days=1000,
            goal_amount=1000.0,
        )
        result = await run_analysis(f"eval-ofac-{code}", campaign)

        if result.risk_level != "HIGH":
            failures.append(f"{code}: expected HIGH, got {result.risk_level}")
        if (result.risk_score or 0) < 70:
            failures.append(f"{code}: expected score >= 70, got {result.risk_score}")
        if result.recommendation != "REJECT":
            failures.append(f"{code}: expected REJECT, got {result.recommendation}")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    passed = len(failures) == 0
    return EvalResult(
        name=name,
        passed=passed,
        message=(
            f"All {len(ofac_countries)} OFAC countries correctly forced HIGH/REJECT"
            if passed else f"Failures: {'; '.join(failures)}"
        ),
        duration_ms=elapsed_ms,
        details={"countries_tested": [c for c, _ in ofac_countries], "failures": failures},
    )


async def eval_verified_uk_low_risk() -> EvalResult:
    """
    A well-established UK creator fundraising for a UK beneficiary should produce:
      - risk_level = LOW
      - risk_score < 30
      - recommendation = APPROVE
    """
    name = "verified_uk_campaign_low_risk"
    t0 = time.perf_counter()

    campaign = _make_campaign(
        title="Quran School Renovation - Birmingham, UK",
        story=(
            "Our Quran school in Birmingham has served the community for 20 years. "
            "We need renovation funds for the roof, classrooms, and heating. "
            "Full council documentation and charity registration available on request. "
            "All funds go directly to verified contractors with receipts provided."
        ),
        category="education",
        goal_amount=8000.0,
        creator_country="GB",
        account_age_days=730,
        beneficiary_country="GB",
        organization_name="Al-Noor Educational Trust",
        documents=["charity_cert_uk.pdf"],
    )

    result = await run_analysis("eval-uk-low", campaign)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    checks = {
        "risk_level_is_low": result.risk_level == "LOW",
        "risk_score_lt_30": (result.risk_score or 100) < 30,
        "recommendation_approve": result.recommendation == "APPROVE",
    }
    passed = all(checks.values())

    return EvalResult(
        name=name,
        passed=passed,
        message=(
            "UK verified campaign correctly assessed as LOW/APPROVE"
            if passed
            else f"Failed checks: {[k for k, v in checks.items() if not v]}"
                 f" | score={result.risk_score} level={result.risk_level} rec={result.recommendation}"
        ),
        duration_ms=elapsed_ms,
        details={
            "risk_score": result.risk_score,
            "risk_level": result.risk_level,
            "recommendation": result.recommendation,
            "checks": checks,
        },
    )


async def eval_high_risk_country_medium() -> EvalResult:
    """
    A campaign to a high-risk (non-OFAC) country like Somalia with an established
    creator should produce MEDIUM risk and ESCALATE recommendation.
    """
    name = "high_risk_country_escalates"
    t0 = time.perf_counter()

    campaign = _make_campaign(
        title="Water Well Project - Somalia",
        story=(
            "Our community in Mogadishu needs clean water. We partner with local NGOs "
            "to build water wells serving 2,000 people. Documentation available."
        ),
        category="humanitarian",
        goal_amount=15000.0,
        creator_country="US",
        account_age_days=245,
        beneficiary_country="SO",
        organization_name="Al-Noor Foundation",
    )

    result = await run_analysis("eval-so-medium", campaign)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    checks = {
        "risk_level_is_medium": result.risk_level == "MEDIUM",
        "risk_score_in_range": 30 <= (result.risk_score or 0) < 70,
        "recommendation_escalate": result.recommendation == "ESCALATE",
    }
    passed = all(checks.values())

    return EvalResult(
        name=name,
        passed=passed,
        message=(
            "Somalia high-risk campaign correctly escalated"
            if passed
            else f"Failed: {[k for k, v in checks.items() if not v]}"
                 f" | score={result.risk_score} level={result.risk_level} rec={result.recommendation}"
        ),
        duration_ms=elapsed_ms,
        details={
            "risk_score": result.risk_score,
            "risk_level": result.risk_level,
            "recommendation": result.recommendation,
            "checks": checks,
        },
    )


async def eval_processing_time_sla() -> EvalResult:
    """
    Processing time must be < 10,000ms (10 seconds) for any campaign.
    Tests 3 representative campaigns to check P100 latency.
    """
    name = "processing_time_sla_lt_10s"
    t0 = time.perf_counter()

    scenarios = [
        ("eval-sla-low", _make_campaign(beneficiary_country="GB", account_age_days=400)),
        ("eval-sla-med", _make_campaign(beneficiary_country="SO", account_age_days=200)),
        ("eval-sla-high", _make_campaign(beneficiary_country="SY", account_age_days=3)),
    ]

    violations: list[str] = []
    times: list[int] = []

    for cid, campaign in scenarios:
        result = await run_analysis(cid, campaign)
        ms = result.processing_time_ms or 99999
        times.append(ms)
        if ms >= 10_000:
            violations.append(f"{cid}: {ms}ms (limit: 10000ms)")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    passed = len(violations) == 0
    max_ms = max(times) if times else 0

    return EvalResult(
        name=name,
        passed=passed,
        message=(
            f"All campaigns within SLA. Max={max_ms}ms (limit: 10000ms)"
            if passed else f"SLA violations: {'; '.join(violations)}"
        ),
        duration_ms=elapsed_ms,
        details={"times_ms": times, "max_ms": max_ms, "violations": violations},
    )


async def eval_confidence_in_valid_range() -> EvalResult:
    """
    Confidence score must always be in [0.0, 1.0].
    Tests multiple campaigns across all risk tiers.
    """
    name = "confidence_always_in_valid_range"
    t0 = time.perf_counter()

    test_cases = [
        ("eval-conf-gb",  _make_campaign(beneficiary_country="GB", account_age_days=500)),
        ("eval-conf-so",  _make_campaign(beneficiary_country="SO", account_age_days=200)),
        ("eval-conf-sy",  _make_campaign(beneficiary_country="SY", account_age_days=5)),
        ("eval-conf-my",  _make_campaign(beneficiary_country="MY", account_age_days=412)),
        ("eval-conf-new", _make_campaign(beneficiary_country="US", account_age_days=1, goal_amount=999999)),
    ]

    violations: list[str] = []
    confidences: list[float] = []

    for cid, campaign in test_cases:
        result = await run_analysis(cid, campaign)
        conf = result.confidence
        if conf is None:
            violations.append(f"{cid}: confidence is None")
        elif not (0.0 <= conf <= 1.0):
            violations.append(f"{cid}: confidence={conf} out of range [0.0, 1.0]")
        else:
            confidences.append(conf)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    passed = len(violations) == 0

    return EvalResult(
        name=name,
        passed=passed,
        message=(
            f"All {len(test_cases)} confidence scores valid. Range: "
            f"[{min(confidences):.2f}, {max(confidences):.2f}]"
            if passed else f"Violations: {'; '.join(violations)}"
        ),
        duration_ms=elapsed_ms,
        details={"confidences": confidences, "violations": violations},
    )


async def eval_decision_always_valid() -> EvalResult:
    """
    Recommendation must always be exactly one of: APPROVE, ESCALATE, REJECT.
    Risk level must always be exactly one of: LOW, MEDIUM, HIGH.
    """
    name = "decision_always_valid_enum"
    t0 = time.perf_counter()

    valid_recs = {"APPROVE", "ESCALATE", "REJECT"}
    valid_levels = {"LOW", "MEDIUM", "HIGH"}

    test_cases = [
        ("eval-enum-1", _make_campaign(beneficiary_country="GB", account_age_days=730)),
        ("eval-enum-2", _make_campaign(beneficiary_country="SO", account_age_days=100)),
        ("eval-enum-3", _make_campaign(beneficiary_country="SY", account_age_days=3)),
        ("eval-enum-4", _make_campaign(beneficiary_country="PK", account_age_days=30, goal_amount=999999)),
        ("eval-enum-5", _make_campaign(beneficiary_country="MY", account_age_days=500)),
    ]

    violations: list[str] = []

    for cid, campaign in test_cases:
        result = await run_analysis(cid, campaign)

        if result.recommendation not in valid_recs:
            violations.append(
                f"{cid}: recommendation={result.recommendation!r} not in {valid_recs}"
            )
        if result.risk_level not in valid_levels:
            violations.append(
                f"{cid}: risk_level={result.risk_level!r} not in {valid_levels}"
            )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    passed = len(violations) == 0

    return EvalResult(
        name=name,
        passed=passed,
        message=(
            f"All {len(test_cases)} campaigns returned valid enum values"
            if passed else f"Invalid enums: {'; '.join(violations)}"
        ),
        duration_ms=elapsed_ms,
        details={"violations": violations},
    )


async def eval_risk_score_bounded() -> EvalResult:
    """
    Risk score must always be an integer in [0, 100].
    """
    name = "risk_score_always_0_to_100"
    t0 = time.perf_counter()

    test_cases = [
        ("eval-score-1", _make_campaign(beneficiary_country="GB", account_age_days=730)),
        ("eval-score-2", _make_campaign(beneficiary_country="SY", account_age_days=1)),
        ("eval-score-3", _make_campaign(beneficiary_country="SO", account_age_days=90, goal_amount=500000)),
        ("eval-score-4", _make_campaign(goal_amount=0.0, account_age_days=1)),
    ]

    violations: list[str] = []
    scores: list[int] = []

    for cid, campaign in test_cases:
        result = await run_analysis(cid, campaign)
        score = result.risk_score

        if score is None:
            violations.append(f"{cid}: risk_score is None")
        elif not isinstance(score, int):
            violations.append(f"{cid}: risk_score={score!r} is not an int (type={type(score).__name__})")
        elif not (0 <= score <= 100):
            violations.append(f"{cid}: risk_score={score} out of [0, 100]")
        else:
            scores.append(score)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    passed = len(violations) == 0

    return EvalResult(
        name=name,
        passed=passed,
        message=(
            f"All risk scores valid. Observed: {scores}"
            if passed else f"Violations: {'; '.join(violations)}"
        ),
        duration_ms=elapsed_ms,
        details={"scores": scores, "violations": violations},
    )


async def eval_reasoning_summary_quality() -> EvalResult:
    """
    Reasoning summary must:
      - Never be None or empty
      - Be at least 50 characters (meaningful content)
      - Be at most 2000 characters (≤ 3 sentences as required)
      - Mention the campaign title or risk level
    """
    name = "reasoning_summary_quality"
    t0 = time.perf_counter()

    test_cases = [
        ("eval-reason-1", _make_campaign(title="Birmingham Quran School", beneficiary_country="GB")),
        ("eval-reason-2", _make_campaign(title="Somalia Water Wells", beneficiary_country="SO")),
        ("eval-reason-3", _make_campaign(title="Syria Humanitarian Aid", beneficiary_country="SY")),
    ]

    violations: list[str] = []

    for cid, campaign in test_cases:
        result = await run_analysis(cid, campaign)
        summary = result.reasoning_summary
        title = campaign["title"]

        if not summary:
            violations.append(f"{cid}: reasoning_summary is None or empty")
            continue

        if len(summary) < 50:
            violations.append(
                f"{cid}: reasoning_summary too short ({len(summary)} chars < 50)"
            )

        if len(summary) > 2000:
            violations.append(
                f"{cid}: reasoning_summary too long ({len(summary)} chars > 2000)"
            )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    passed = len(violations) == 0

    return EvalResult(
        name=name,
        passed=passed,
        message=(
            f"All {len(test_cases)} reasoning summaries passed quality checks"
            if passed else f"Violations: {'; '.join(violations)}"
        ),
        duration_ms=elapsed_ms,
        details={"violations": violations},
    )


async def eval_risk_dimensions_complete() -> EvalResult:
    """
    Every result must include all 4 required risk dimensions with valid scores.
    """
    name = "risk_dimensions_always_complete"
    t0 = time.perf_counter()

    required_dims = {"content_quality", "compliance", "fraud_signals", "creator_credibility"}
    campaign = _make_campaign(beneficiary_country="SO")

    result = await run_analysis("eval-dims", campaign)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    violations: list[str] = []

    if result.risk_dimensions is None:
        violations.append("risk_dimensions is None")
    else:
        missing = required_dims - set(result.risk_dimensions.keys())
        if missing:
            violations.append(f"Missing dimensions: {missing}")

        for dim_name, dim in result.risk_dimensions.items():
            score = dim.score if hasattr(dim, "score") else dim.get("score")
            if score is None or not (0 <= score <= 100):
                violations.append(f"Dimension {dim_name}: invalid score {score}")

    passed = len(violations) == 0
    return EvalResult(
        name=name,
        passed=passed,
        message=(
            f"All {len(required_dims)} dimensions present with valid scores"
            if passed else f"Violations: {'; '.join(violations)}"
        ),
        duration_ms=elapsed_ms,
        details={"violations": violations},
    )


# ---------------------------------------------------------------------------
# Registry — all evals in execution order
# ---------------------------------------------------------------------------

ALL_EVALS = [
    eval_ofac_always_high_risk,
    eval_verified_uk_low_risk,
    eval_high_risk_country_medium,
    eval_processing_time_sla,
    eval_confidence_in_valid_range,
    eval_decision_always_valid,
    eval_risk_score_bounded,
    eval_reasoning_summary_quality,
    eval_risk_dimensions_complete,
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all(
    evals: list | None = None,
    fail_fast: bool = False,
) -> list[EvalResult]:
    """
    Run all deterministic evals and return their results.

    Args:
        evals: Subset of eval functions to run. Defaults to ALL_EVALS.
        fail_fast: If True, stop after the first failure.

    Returns:
        List of EvalResult objects (one per eval function).
    """
    suite = evals or ALL_EVALS
    results: list[EvalResult] = []

    for eval_fn in suite:
        try:
            result = await eval_fn()
        except Exception as exc:
            result = EvalResult(
                name=eval_fn.__name__,
                passed=False,
                message=f"EXCEPTION: {exc}",
                duration_ms=0,
            )
            logger.exception("Eval %s raised an exception", eval_fn.__name__)

        results.append(result)
        logger.info("%s", result)

        if fail_fast and not result.passed:
            logger.warning("Stopping early — fail_fast=True")
            break

    return results


def summarise(results: list[EvalResult]) -> dict:
    """Return a summary dict suitable for the API or logging."""
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    return {
        "total": len(results),
        "passed": len(passed),
        "failed": len(failed),
        "pass_rate": round(len(passed) / len(results), 4) if results else 0.0,
        "results": [
            {
                "name": r.name,
                "passed": r.passed,
                "message": r.message,
                "duration_ms": r.duration_ms,
            }
            for r in results
        ],
    }
