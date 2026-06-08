"""
nodes/intake.py

Intake node: parse, validate, and normalize the raw campaign submission.

Responsibilities:
- Extract and clean key fields (title, story, amounts, countries)
- Normalise country codes to uppercase ISO 2-letter
- Compute derived metadata (account age bucket, goal tier)
- Return a clean `normalized_data` dict downstream nodes can rely on

No LLM call — pure deterministic transformation for speed and reliability.
"""

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Country code normalisation
# ---------------------------------------------------------------------------

def _normalize_country(code: str | None) -> str:
    """Return uppercase 2-letter ISO code, or 'XX' if invalid."""
    if not code:
        return "XX"
    code = code.strip().upper()
    return code[:2] if len(code) >= 2 else "XX"


# ---------------------------------------------------------------------------
# Account age bucketing (for downstream scoring)
# ---------------------------------------------------------------------------

def _account_age_bucket(days: int) -> str:
    if days < 7:
        return "brand_new"
    elif days < 30:
        return "new"
    elif days < 90:
        return "recent"
    elif days < 365:
        return "established"
    else:
        return "veteran"


# ---------------------------------------------------------------------------
# Goal tier bucketing
# ---------------------------------------------------------------------------

def _goal_tier(amount: float) -> str:
    if amount <= 5_000:
        return "micro"
    elif amount <= 25_000:
        return "small"
    elif amount <= 100_000:
        return "medium"
    elif amount <= 500_000:
        return "large"
    else:
        return "ultra"


# ---------------------------------------------------------------------------
# Urgency language detection (simple regex; full NLP in content_analysis)
# ---------------------------------------------------------------------------

_URGENCY_PATTERNS = re.compile(
    r"\b(urgent|emergency|immediately|critical|crisis|desperate|"
    r"last chance|dying|catastrophic|please help now)\b",
    re.IGNORECASE,
)


def intake_node(state: dict) -> dict:
    """
    Intake node: parse and normalise the raw campaign submission.

    Input fields consumed from state:
        campaign_data: dict  — raw submission payload from the API

    Output fields written to state:
        normalized_data: dict — cleaned, enriched version of campaign_data
    """
    logger.info("[intake] Starting intake for campaign_id=%s", state.get("campaign_id"))

    raw = state.get("campaign_data", {})

    # -- Creator sub-object --
    creator = raw.get("creator") or {}
    account_age = int(creator.get("account_age_days") or 0)
    creator_country = _normalize_country(creator.get("country"))

    # -- Goal amount --
    try:
        goal_amount = float(raw.get("goal_amount") or 0)
    except (TypeError, ValueError):
        goal_amount = 0.0

    # -- Story / title --
    title = (raw.get("title") or "").strip()
    story = (raw.get("story") or "").strip()

    # -- Beneficiary --
    beneficiary_country = _normalize_country(raw.get("beneficiary_country"))

    # -- Documents --
    documents = raw.get("documents") or []

    # -- Urgency detection (quick pass for downstream) --
    combined_text = f"{title} {story}"
    urgency_match_count = len(_URGENCY_PATTERNS.findall(combined_text))

    normalized = {
        # Identity
        "campaign_id": state.get("campaign_id"),
        "title": title,
        "story": story,
        "category": (raw.get("category") or "").lower().strip(),
        # Financial
        "goal_amount": goal_amount,
        "goal_tier": _goal_tier(goal_amount),
        "currency": (raw.get("currency") or "USD").upper(),
        # Creator
        "creator_name": (creator.get("name") or "").strip(),
        "creator_email": (creator.get("email") or "").strip().lower(),
        "creator_country": creator_country,
        "account_age_days": account_age,
        "account_age_bucket": _account_age_bucket(account_age),
        # Beneficiary / org
        "beneficiary_country": beneficiary_country,
        "organization_name": (raw.get("organization_name") or "").strip(),
        # Content metadata
        "story_word_count": len(story.split()) if story else 0,
        "story_char_count": len(story),
        "has_documents": len(documents) > 0,
        "document_count": len(documents),
        "urgency_word_count": urgency_match_count,
    }

    logger.info(
        "[intake] Normalized: beneficiary=%s creator_country=%s "
        "goal=%.0f tier=%s account_age=%d(%s)",
        beneficiary_country,
        creator_country,
        goal_amount,
        normalized["goal_tier"],
        account_age,
        normalized["account_age_bucket"],
    )

    return {"normalized_data": normalized}
