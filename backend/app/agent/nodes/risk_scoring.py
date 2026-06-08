"""
nodes/risk_scoring.py

Risk Scoring node: aggregates signals from all upstream nodes into a single
weighted composite risk score.

Scoring formula (from SYSTEM.md §4):
  Final Score = Σ (dimension_score × weight)

  Dimensions & Weights:
    content_quality      : 0.20
    compliance           : 0.35  ← highest (legal risk)
    fraud_signals        : 0.30
    creator_credibility  : 0.15

Thresholds:
  0  - 29  → LOW    → Recommend APPROVE
  30 - 69  → MEDIUM → Recommend ESCALATE
  70 - 100 → HIGH   → Recommend REJECT

OFAC hard override: any OFAC-blocked campaign is always clamped to >= 70
(HIGH/REJECT) regardless of the weighted score.

No LLM call — pure deterministic aggregation.
"""

import logging

from app.agent.state import RiskDimension

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dimension weights — must sum to 1.0
# ---------------------------------------------------------------------------

DIMENSION_WEIGHTS: dict[str, float] = {
    "content_quality":     0.20,
    "compliance":          0.35,
    "fraud_signals":       0.30,
    "creator_credibility": 0.15,
}


def _creator_credibility_score(normalized: dict) -> tuple[int, list[str]]:
    """
    Derive creator credibility score from normalised data.

    Separate from fraud_signals: credibility measures trust indicators
    (account age, verified email, documents), whereas fraud_signals measures
    behavioural red flags (urgency, large goals on new accounts, etc.).
    """
    account_age = int(normalized.get("account_age_days") or 0)
    has_documents = bool(normalized.get("has_documents"))
    creator_email = (normalized.get("creator_email") or "").strip()

    signals: list[str] = []
    score = 0

    # Account age
    if account_age >= 365:
        score += 5
        signals.append("long_standing_account")
    elif account_age >= 180:
        score += 15
        signals.append("established_account")
    elif account_age >= 90:
        score += 30
        signals.append("moderate_account_history")
    elif account_age >= 30:
        score += 50
        signals.append("recent_account")
    else:
        score += 75
        signals.append("new_account_low_credibility")

    # Has supporting documents
    if has_documents:
        signals.append("documents_provided")
        score = max(0, score - 10)
    else:
        signals.append("no_documents_provided")
        score = min(100, score + 5)

    # Verified email (non-free domains are a positive signal)
    free_email_domains = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "proton.me"}
    if creator_email:
        domain = creator_email.split("@")[-1] if "@" in creator_email else ""
        if domain and domain not in free_email_domains:
            signals.append("custom_domain_email")
            score = max(0, score - 5)
        else:
            signals.append("free_email_provider")

    return max(0, min(100, score)), signals


def risk_scoring_node(state: dict) -> dict:
    """
    Risk Scoring node: aggregate per-node scores into a weighted final score.

    Consumes: normalized_data, _content_score, _compliance_score,
              _fraud_score, _is_ofac_blocked (all from upstream nodes)
    Produces: risk_dimensions (dict[str, RiskDimension]), risk_score (int)
    """
    campaign_id = state.get("campaign_id", "unknown")
    normalized = state.get("normalized_data") or {}

    # Upstream node scores (written to state with _ prefix by convention)
    content_score: int  = state.get("_content_score", 20)
    compliance_score: int = state.get("_compliance_score", 10)
    fraud_score: int = state.get("_fraud_score", 10)
    is_ofac_blocked: bool = state.get("_is_ofac_blocked", False)

    # Upstream signals lists
    content_flags: list[str] = state.get("content_flags") or []
    compliance_flags: list[str] = state.get("compliance_flags") or []
    fraud_signals: list[str] = state.get("fraud_signals") or []

    logger.info(
        "[risk_scoring] campaign_id=%s content=%d compliance=%d fraud=%d ofac=%s",
        campaign_id,
        content_score,
        compliance_score,
        fraud_score,
        is_ofac_blocked,
    )

    # Compute creator credibility (this node owns it, no upstream node for it)
    credibility_score, credibility_signals = _creator_credibility_score(normalized)

    # ---------------------------------------------------------------------------
    # Build risk dimensions
    # ---------------------------------------------------------------------------
    risk_dimensions: dict[str, RiskDimension] = {
        "content_quality": RiskDimension(
            score=content_score,
            signals=content_flags,
            weight=DIMENSION_WEIGHTS["content_quality"],
        ),
        "compliance": RiskDimension(
            score=compliance_score,
            signals=compliance_flags,
            weight=DIMENSION_WEIGHTS["compliance"],
        ),
        "fraud_signals": RiskDimension(
            score=fraud_score,
            signals=fraud_signals,
            weight=DIMENSION_WEIGHTS["fraud_signals"],
        ),
        "creator_credibility": RiskDimension(
            score=credibility_score,
            signals=credibility_signals,
            weight=DIMENSION_WEIGHTS["creator_credibility"],
        ),
    }

    # ---------------------------------------------------------------------------
    # Weighted composite score
    # ---------------------------------------------------------------------------
    weighted = sum(
        dim.score * dim.weight
        for dim in risk_dimensions.values()
    )
    final_score = int(round(weighted))
    final_score = max(0, min(100, final_score))

    # OFAC hard override — legal block trumps the math
    if is_ofac_blocked:
        final_score = max(final_score, 70)

    logger.info(
        "[risk_scoring] Weighted score=%.1f -> final=%d (ofac_override=%s)",
        weighted,
        final_score,
        is_ofac_blocked,
    )

    return {
        "risk_dimensions": risk_dimensions,
        "risk_score": final_score,
        # Propagate OFAC flag for decision node
        "_is_ofac_blocked": is_ofac_blocked,
    }
