"""
nodes/compliance_check.py

Compliance Check node: OFAC sanctions screening + high-risk jurisdiction check.

This is the highest-weight dimension (0.35) because legal/sanctions risk is
non-negotiable — a campaign to a sanctioned country is a hard block regardless
of everything else.

No LLM call — deterministic rule-based for 100% reliability on compliance.
OFAC list is static and must not depend on an external API call for safety.
"""

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sanction & risk lists
# Per user spec: SY, IR, KP, CU, VE, BY, ER
# ---------------------------------------------------------------------------

OFAC_SANCTIONED_COUNTRIES: frozenset[str] = frozenset({
    "SY",  # Syria
    "IR",  # Iran
    "KP",  # North Korea
    "CU",  # Cuba
    "VE",  # Venezuela
    "BY",  # Belarus
    "ER",  # Eritrea
})

# High-risk but NOT sanctioned — requires additional due diligence
HIGH_RISK_COUNTRIES: frozenset[str] = frozenset({
    "SO",  # Somalia
    "YE",  # Yemen
    "LY",  # Libya
    "AF",  # Afghanistan
    "ML",  # Mali
    "SD",  # Sudan
    "SS",  # South Sudan
    "CF",  # Central African Republic
    "CD",  # DR Congo
    "NI",  # Nicaragua
    "ZW",  # Zimbabwe
    "MM",  # Myanmar
    "HT",  # Haiti
    "PK",  # Pakistan (FATF grey list)
    "NG",  # Nigeria (FATF grey list)
    "AO",  # Angola
    "PS",  # Palestine / Gaza (enhanced due diligence required)
    "IQ",  # Iraq
    "LB",  # Lebanon
})

# ---------------------------------------------------------------------------
# Suspicious organisation name patterns
# ---------------------------------------------------------------------------

SUSPICIOUS_ORG_PATTERNS = [
    "anonymous", "unknown", "n/a", "na", "none", "test", "fake",
]


def _check_account_age(account_age: int) -> tuple[int, list[str]]:
    """Returns (base_fraud_score, signals) based purely on account age."""
    if account_age < 7:
        return 100, ["brand_new_account", "high_fraud_risk"]
    elif account_age < 30:
        return 65, ["new_account", "limited_history"]
    elif account_age < 90:
        return 30, ["recent_account", "limited_history"]
    elif account_age < 180:
        return 15, ["moderate_account_age"]
    elif account_age < 365:
        return 8, ["established_account"]
    else:
        return 5, ["veteran_account", "positive_history"]


def compliance_check_node(state: dict) -> dict:
    """
    Compliance Check node: OFAC screening + high-risk jurisdiction classification.

    Consumes: normalized_data.beneficiary_country, normalized_data.creator_country,
              normalized_data.organization_name
    Produces: compliance_flags (list[str]), _compliance_score (int)
    """
    normalized = state.get("normalized_data") or state.get("campaign_data") or {}
    campaign_id = state.get("campaign_id", "unknown")

    beneficiary_country = (normalized.get("beneficiary_country") or "XX").upper()
    creator_country = (normalized.get("creator_country") or "XX").upper()
    org_name = (normalized.get("organization_name") or "").strip().lower()

    logger.info(
        "[compliance] Screening campaign_id=%s beneficiary=%s creator=%s",
        campaign_id,
        beneficiary_country,
        creator_country,
    )

    flags: list[str] = []
    score = 0

    # ------------------------------------------------------------------
    # 1. Beneficiary country OFAC check (highest severity)
    # ------------------------------------------------------------------
    if beneficiary_country in OFAC_SANCTIONED_COUNTRIES:
        flags.extend(["ofac_sanctioned_beneficiary_country", "hard_block_required"])
        score = 100  # Hard maximum — OFAC is a legal block
        logger.warning(
            "[compliance] OFAC HARD BLOCK: beneficiary_country=%s", beneficiary_country
        )

    # ------------------------------------------------------------------
    # 2. Creator country OFAC check
    # ------------------------------------------------------------------
    elif creator_country in OFAC_SANCTIONED_COUNTRIES:
        flags.extend(["ofac_sanctioned_creator_country", "creator_jurisdiction_risk"])
        score = max(score, 90)
        logger.warning(
            "[compliance] OFAC creator country: creator_country=%s", creator_country
        )

    # ------------------------------------------------------------------
    # 3. High-risk beneficiary country (not OFAC)
    # ------------------------------------------------------------------
    if beneficiary_country in HIGH_RISK_COUNTRIES and score < 100:
        flags.extend(["high_risk_beneficiary_country", "additional_docs_required"])
        score = max(score, 72)
        logger.info(
            "[compliance] High-risk beneficiary: %s (score→%d)", beneficiary_country, score
        )

    # ------------------------------------------------------------------
    # 4. High-risk creator country (not OFAC)
    # ------------------------------------------------------------------
    if creator_country in HIGH_RISK_COUNTRIES and score < 90:
        flags.append("high_risk_creator_country")
        score = max(score, 40)

    # ------------------------------------------------------------------
    # 5. Low-risk / clean jurisdiction
    # ------------------------------------------------------------------
    if not flags:
        flags.append("low_risk_jurisdiction")
        score = 10

    # ------------------------------------------------------------------
    # 6. Suspicious organisation name
    # ------------------------------------------------------------------
    if org_name in SUSPICIOUS_ORG_PATTERNS or not org_name:
        flags.append("suspicious_organization_name")
        score = min(100, score + 10)

    logger.info(
        "[compliance] Result: score=%d flags=%s", score, flags
    )

    return {
        "compliance_flags": flags,
        "_compliance_score": score,
        "_is_ofac_blocked": beneficiary_country in OFAC_SANCTIONED_COUNTRIES
                           or creator_country in OFAC_SANCTIONED_COUNTRIES,
    }
