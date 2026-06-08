"""
tests/test_agent.py

Deterministic unit tests for the AI risk scoring agent.
These tests validate the rule-based scoring logic and will also cover
the real LangGraph agent once it's implemented in Session 2.

Run with: uv run pytest tests/test_agent.py -v
"""

import pytest

from app.agent.graph import run_analysis


def make_campaign(**overrides) -> dict:
    """Helper: create a minimal campaign payload with sensible defaults."""
    base = {
        "title": "Test Campaign",
        "story": "A detailed story about why this campaign matters and how funds will be used.",
        "category": "humanitarian",
        "goal_amount": 5000,
        "currency": "USD",
        "creator": {
            "name": "Test Creator",
            "email": "creator@example.com",
            "country": "US",
            "account_age_days": 365,
        },
        "beneficiary_country": "GB",
        "organization_name": "Test Org",
        "documents": [],
    }
    base.update(overrides)
    return base


# =============================================================================
# Deterministic Tests (from SYSTEM.md §8)
# =============================================================================

@pytest.mark.asyncio
async def test_ofac_country_always_high_risk():
    """OFAC-sanctioned beneficiary country (Syria) must always be HIGH risk."""
    campaign = make_campaign(beneficiary_country="SY")
    result = await run_analysis("test-id-sy", campaign)
    assert result.risk_level == "HIGH", f"Expected HIGH, got {result.risk_level}"
    assert result.risk_score >= 70, f"Expected score >= 70, got {result.risk_score}"
    assert result.recommendation == "REJECT"


@pytest.mark.asyncio
async def test_ofac_iran_always_high_risk():
    """OFAC-sanctioned beneficiary country (Iran) must always be HIGH risk."""
    campaign = make_campaign(beneficiary_country="IR")
    result = await run_analysis("test-id-ir", campaign)
    assert result.risk_level == "HIGH"
    assert result.risk_score >= 70
    assert result.recommendation == "REJECT"


@pytest.mark.asyncio
async def test_verified_uk_campaign_low_risk():
    """Long-standing creator with UK beneficiary should be LOW risk."""
    campaign = make_campaign(
        beneficiary_country="GB",
        creator={"name": "Alice", "email": "alice@example.co.uk", "country": "GB", "account_age_days": 500},
        goal_amount=5000,
    )
    result = await run_analysis("test-id-gb", campaign)
    assert result.risk_level == "LOW", f"Expected LOW, got {result.risk_level}"
    assert result.risk_score < 30, f"Expected score < 30, got {result.risk_score}"
    assert result.recommendation == "APPROVE"


@pytest.mark.asyncio
async def test_brand_new_account_high_risk():
    """A 3-day-old account should generate elevated fraud signals."""
    campaign = make_campaign(
        creator={"name": "New", "email": "new@example.com", "country": "TR", "account_age_days": 3},
        beneficiary_country="SY",
    )
    result = await run_analysis("test-id-new", campaign)
    # OFAC country takes precedence
    assert result.risk_level == "HIGH"
    assert "brand_new_account" in (result.fraud_signals or []) or "new_account" in (result.fraud_signals or [])


@pytest.mark.asyncio
async def test_high_risk_country_medium_risk():
    """Somalia (high-risk but not OFAC) with established creator should be MEDIUM."""
    campaign = make_campaign(
        beneficiary_country="SO",
        creator={"name": "Ahmad", "email": "a@example.com", "country": "US", "account_age_days": 245},
        goal_amount=15000,
    )
    result = await run_analysis("test-id-so", campaign)
    assert result.risk_level == "MEDIUM"
    assert result.recommendation == "ESCALATE"


@pytest.mark.asyncio
async def test_processing_time_sla():
    """Processing time should be under 10 seconds (10,000ms)."""
    campaign = make_campaign()
    result = await run_analysis("test-id-sla", campaign)
    assert result.processing_time_ms is not None
    assert result.processing_time_ms < 10_000, (
        f"SLA breach: processing took {result.processing_time_ms}ms (limit: 10,000ms)"
    )


@pytest.mark.asyncio
async def test_reasoning_summary_not_empty():
    """Every analysis must produce a non-empty reasoning summary."""
    campaign = make_campaign()
    result = await run_analysis("test-id-reasoning", campaign)
    assert result.reasoning_summary is not None
    assert len(result.reasoning_summary) > 50


@pytest.mark.asyncio
async def test_confidence_in_valid_range():
    """Confidence score must be between 0.0 and 1.0."""
    campaign = make_campaign()
    result = await run_analysis("test-id-confidence", campaign)
    assert result.confidence is not None
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_risk_dimensions_present():
    """Risk dimensions dict must contain all 4 required keys."""
    required_keys = {"content_quality", "compliance", "fraud_signals", "creator_credibility"}
    campaign = make_campaign()
    result = await run_analysis("test-id-dims", campaign)
    assert result.risk_dimensions is not None
    assert required_keys.issubset(set(result.risk_dimensions.keys()))


@pytest.mark.asyncio
async def test_score_aligns_with_risk_level():
    """Risk level must match the defined score thresholds."""
    for beneficiary_country, expected_level in [("GB", "LOW"), ("SO", "MEDIUM"), ("SY", "HIGH")]:
        campaign = make_campaign(beneficiary_country=beneficiary_country)
        result = await run_analysis(f"test-id-{beneficiary_country}", campaign)
        if expected_level == "LOW":
            assert result.risk_score < 30
        elif expected_level == "MEDIUM":
            assert 30 <= result.risk_score < 70
        else:
            assert result.risk_score >= 70
