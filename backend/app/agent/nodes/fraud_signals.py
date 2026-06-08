"""
nodes/fraud_signals.py

Fraud Signal node: analyses behavioural and structural signals that correlate
with fraudulent campaign submissions.

Signals checked:
  1. Goal amount reasonableness vs. category norms
  2. Creator account age risk (new accounts are high fraud risk)
  3. Urgency / manipulation language patterns (from intake pre-detection)
  4. Goal amount / account age interaction (new account + large goal)
  5. Round-number amounts (e.g. $999,999 — common fraud indicator)

No LLM call — deterministic rule-based for speed and auditability.
All thresholds are documented inline and tunable.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Goal amount thresholds by category (USD baseline)
# Values approximate realistic crowdfunding ranges per campaign type.
# ---------------------------------------------------------------------------

CATEGORY_GOAL_LIMITS: dict[str, tuple[float, float]] = {
    # (soft_max, hard_max)  — above soft_max triggers a flag, above hard_max is suspicious
    "education":    (50_000,   200_000),
    "humanitarian": (100_000,  500_000),
    "emergency":    (200_000, 1_000_000),
    "medical":      (75_000,   300_000),
    "community":    (30_000,   150_000),
    "mosque":       (500_000, 2_000_000),
    "zakat":        (100_000,  500_000),
    "sadaqah":      (50_000,   200_000),
    "orphan":       (50_000,   250_000),
}
DEFAULT_GOAL_LIMITS = (50_000, 500_000)


# ---------------------------------------------------------------------------
# Urgency / manipulation language patterns
# (intake does a quick regex pass; here we do a more thorough analysis)
# ---------------------------------------------------------------------------

URGENCY_PATTERNS = re.compile(
    r"\b("
    r"urgent|urgently|emergency|immediately|critical|crisis|desperate|"
    r"last chance|act now|dying|catastrophic|please help now|"
    r"wire transfer|western union|gift card|untraceable|"
    r"send money|cash only|no questions|guaranteed return|"
    r"double your|100% success|risk free"
    r")\b",
    re.IGNORECASE,
)

MANIPULATION_PATTERNS = re.compile(
    r"\b("
    r"god will reward|divine punishment|hell|haram if you don't|"
    r"cursed|blessed if|sin to ignore|religious obligation to donate"
    r")\b",
    re.IGNORECASE,
)


def _check_goal_reasonableness(
    goal_amount: float,
    category: str,
    account_age: int,
) -> tuple[int, list[str]]:
    """
    Returns (score_contribution, signals).
    score_contribution is added to the fraud score.
    """
    signals: list[str] = []
    score = 0

    soft_max, hard_max = CATEGORY_GOAL_LIMITS.get(category, DEFAULT_GOAL_LIMITS)

    if goal_amount == 0:
        signals.append("zero_goal_amount")
        score += 20
    elif goal_amount > hard_max:
        signals.append("suspiciously_high_goal_amount")
        score += 40
    elif goal_amount > soft_max:
        signals.append("elevated_goal_amount")
        score += 15
    else:
        signals.append("reasonable_goal_amount")
        # No score penalty

    # Round-number anomaly: $999,999 or $1,000,000 are fraud indicators
    if goal_amount >= 100_000:
        # Amounts like 999999, 1000000, 500000 exactly
        str_amount = str(int(goal_amount))
        if all(c in "90" for c in str_amount) or str_amount.rstrip("0") in ("1", "5", "2"):
            signals.append("suspicious_round_amount")
            score += 10

    # Interaction: new account + large goal
    if account_age < 30 and goal_amount > 10_000:
        signals.append("new_account_large_goal_combo")
        score += 25
    elif account_age < 90 and goal_amount > 50_000:
        signals.append("moderate_account_elevated_goal_combo")
        score += 15

    return score, signals


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


def _check_urgency_language(title: str, story: str) -> tuple[int, list[str]]:
    """Returns (score_bump, signals) for detected manipulation patterns."""
    combined = f"{title} {story}"
    signals: list[str] = []
    score = 0

    urgency_matches = URGENCY_PATTERNS.findall(combined)
    if urgency_matches:
        unique = list({m.lower() for m in urgency_matches})
        if len(unique) >= 3:
            signals.append("high_urgency_language_density")
            score += 25
        else:
            signals.append("urgency_language_detected")
            score += 10

    manipulation_matches = MANIPULATION_PATTERNS.findall(combined)
    if manipulation_matches:
        signals.append("religious_manipulation_language")
        score += 20

    return score, signals


def fraud_signals_node(state: dict) -> dict:
    """
    Fraud Signal node: detect behavioural and structural fraud indicators.

    Consumes: normalized_data (from intake_node)
    Produces:
      - fraud_signals (list[str]) — all detected fraud signals
      - _fraud_score (int 0-100) — raw score for this dimension
    """
    normalized = state.get("normalized_data") or state.get("campaign_data") or {}
    campaign_id = state.get("campaign_id", "unknown")

    account_age = int(normalized.get("account_age_days") or 0)
    goal_amount = float(normalized.get("goal_amount") or 0)
    category = (normalized.get("category") or "").lower().strip()
    title = normalized.get("title") or ""
    story = normalized.get("story") or ""

    # Pre-detected urgency count from intake (quick pass)
    urgency_word_count = int(normalized.get("urgency_word_count") or 0)

    logger.info(
        "[fraud_signals] Analysing campaign_id=%s account_age=%d goal=%.0f category=%s",
        campaign_id,
        account_age,
        goal_amount,
        category,
    )

    all_signals: list[str] = []
    cumulative_score = 0

    # 1. Account age
    age_score, age_signals = _check_account_age(account_age)
    cumulative_score += age_score
    all_signals.extend(age_signals)

    # 2. Goal amount reasonableness
    goal_score, goal_signals = _check_goal_reasonableness(goal_amount, category, account_age)
    cumulative_score += goal_score
    all_signals.extend(goal_signals)

    # 3. Urgency language (deep pass — intake already did a quick pass)
    urgency_score, urgency_signals = _check_urgency_language(title, story)
    cumulative_score += urgency_score
    all_signals.extend(urgency_signals)

    # Bonus bump if intake also flagged high urgency word count
    if urgency_word_count >= 5:
        all_signals.append("very_high_urgency_count")
        cumulative_score += 10

    # Clamp to [0, 100]
    final_score = max(0, min(100, cumulative_score))

    # Deduplicate signals while preserving order
    seen: set[str] = set()
    unique_signals: list[str] = []
    for s in all_signals:
        if s not in seen:
            seen.add(s)
            unique_signals.append(s)

    logger.info(
        "[fraud_signals] Result: score=%d signals=%s",
        final_score,
        unique_signals,
    )

    return {
        "fraud_signals": unique_signals,
        "_fraud_score": final_score,
    }
