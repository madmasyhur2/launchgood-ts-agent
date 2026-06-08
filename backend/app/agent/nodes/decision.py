"""
nodes/decision.py

Decision node: the final node in the LangGraph pipeline.

Responsibilities:
  1. Map risk_score → risk_level (LOW / MEDIUM / HIGH)
  2. Map risk_level → recommendation (APPROVE / ESCALATE / REJECT)
  3. Compute confidence score (0.0–1.0)
  4. Generate a human-readable reasoning summary (max 3 sentences)
  5. Apply OFAC hard override (always REJECT + HIGH if OFAC blocked)

LLM call: YES — Gemini Pro via LangChain with_structured_output() for
natural-language reasoning summaries readable by human reviewers.

Fallback: if the LLM call fails, a deterministic template-based summary
is generated so the pipeline never stalls.
"""

import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schema for structured LLM output
# ---------------------------------------------------------------------------

class DecisionOutput(BaseModel):
    """Structured output from the decision LLM call."""
    reasoning_summary: str = Field(
        ...,
        description=(
            "Human-readable reasoning summary for the Trust & Safety reviewer. "
            "Exactly 2-3 sentences. Must mention the key risk factors and the recommended action."
        ),
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model's confidence in the recommendation (0.0–1.0).",
    )


# ---------------------------------------------------------------------------
# Score → level / recommendation mapping
# ---------------------------------------------------------------------------

def _score_to_level_and_rec(
    score: int,
    is_ofac_blocked: bool,
) -> tuple[str, str]:
    """Return (risk_level, recommendation) for a given score."""
    if is_ofac_blocked:
        return "HIGH", "REJECT"
    if score < 30:
        return "LOW", "APPROVE"
    elif score < 70:
        return "MEDIUM", "ESCALATE"
    else:
        return "HIGH", "REJECT"


# ---------------------------------------------------------------------------
# Deterministic fallback reasoning generator
# ---------------------------------------------------------------------------

def _fallback_reasoning(
    score: int,
    level: str,
    recommendation: str,
    campaign_data: dict,
    compliance_flags: list[str],
    fraud_signals: list[str],
    content_flags: list[str],
) -> str:
    """Template-based reasoning summary used when the LLM is unavailable (≤ 3 sentences)."""
    title = campaign_data.get("title") or "This campaign"
    beneficiary = campaign_data.get("beneficiary_country") or "unknown"
    sentences: list[str] = []

    sentences.append(
        f'Campaign "{title}" received a risk score of {score}/100 ({level}).'
    )

    if "ofac_sanctioned_beneficiary_country" in compliance_flags:
        sentences.append(
            f"Beneficiary country ({beneficiary}) is on the OFAC sanctions list — "
            "a hard compliance block requiring mandatory legal team review."
        )
    elif "high_risk_beneficiary_country" in compliance_flags:
        sentences.append(
            f"Beneficiary country ({beneficiary}) is a high-risk jurisdiction; "
            "additional organisational documentation is required before approval."
        )
    elif "brand_new_account" in fraud_signals or "new_account" in fraud_signals:
        sentences.append(
            "Creator account was created very recently, which is a common fraud indicator; "
            "identity verification is recommended."
        )
    elif "suspiciously_high_goal_amount" in fraud_signals or "suspicious_round_amount" in fraud_signals:
        sentences.append(
            "Goal amount is unusually high or follows a suspicious pattern for this campaign category."
        )
    elif level == "LOW":
        sentences.append(
            "No significant risk factors were detected; jurisdiction, account age, "
            "and content quality are all within normal ranges."
        )

    rec_map = {
        "APPROVE":  "AI recommendation: APPROVE — no further review required unless spot-checking policy applies.",
        "ESCALATE": "AI recommendation: ESCALATE — human review is required to verify flagged concerns before a decision.",
        "REJECT":   "AI recommendation: REJECT — do not approve without thorough compliance and legal team review.",
    }
    sentences.append(rec_map.get(recommendation, f"Recommendation: {recommendation}."))

    return " ".join(sentences)


# ---------------------------------------------------------------------------
# Confidence computation (deterministic)
# ---------------------------------------------------------------------------

def _compute_confidence(
    score: int,
    level: str,
    is_ofac_blocked: bool,
    llm_used: bool,
) -> float:
    """
    Confidence is higher when the score is far from threshold boundaries
    (clear-cut case) or OFAC block is present (100% certain).
    """
    if is_ofac_blocked:
        return 0.99

    boundaries = [30, 70]
    distance = min(abs(score - b) for b in boundaries)
    distance_boost = min(distance / 35.0 * 0.30, 0.30)

    base = 0.65
    llm_boost = 0.10 if llm_used else 0.0
    return round(min(1.0, base + distance_boost + llm_boost), 2)


# ---------------------------------------------------------------------------
# LLM reasoning prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior Trust & Safety analyst at LaunchGood, an Islamic crowdfunding platform.
Write a clear, concise reasoning summary for a campaign risk assessment.
This summary will be read by a human reviewer who needs to make a fast, informed decision.

Rules:
- Write EXACTLY 2-3 sentences. No more, no less.
- Mention the most important risk factor first.
- If OFAC sanctions are involved, say so explicitly.
- Avoid technical jargon — write for a non-technical reviewer.
- End with a clear action statement matching the recommendation.
- Do not start with "I" or "The AI".\
"""

USER_TEMPLATE = """\
Campaign: {title}
Category: {category}
Goal: {goal_amount} {currency}
Beneficiary country: {beneficiary_country}
Creator account age: {account_age_days} days

Risk Score: {risk_score}/100 ({risk_level})
Recommendation: {recommendation}

Risk Dimensions:
{dim_summary}

Key Flags:
  Compliance: {compliance_flags}
  Fraud: {fraud_signals}
  Content: {content_flags}

Write the reasoning summary and confidence score.\
"""

_prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", USER_TEMPLATE),
])


def _get_llm() -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=settings.gemini_pro_model,
        google_api_key=settings.google_api_key,
        temperature=0.1,
    )


async def _llm_reasoning(
    campaign_data: dict,
    risk_score: int,
    risk_level: str,
    recommendation: str,
    compliance_flags: list[str],
    fraud_signals: list[str],
    content_flags: list[str],
    risk_dimensions: dict,
) -> DecisionOutput | None:
    """Call Gemini Pro to generate the reasoning summary. Returns None on failure."""
    settings = get_settings()
    if not settings.google_api_key:
        return None

    try:
        # Build compact dimension summary
        dim_lines: list[str] = []
        for dim_name, dim_data in (risk_dimensions or {}).items():
            if hasattr(dim_data, "score"):
                signals_str = ", ".join(dim_data.signals[:3])
                dim_lines.append(f"  {dim_name}: {dim_data.score}/100 — {signals_str}")
            elif isinstance(dim_data, dict):
                signals_str = ", ".join(dim_data.get("signals", [])[:3])
                dim_lines.append(f"  {dim_name}: {dim_data.get('score', '?')}/100 — {signals_str}")

        creator = campaign_data.get("creator") or {}
        llm = _get_llm()
        structured_llm = llm.with_structured_output(DecisionOutput)
        chain = _prompt | structured_llm

        output: DecisionOutput = await chain.ainvoke({
            "title": campaign_data.get("title", "Unknown"),
            "category": campaign_data.get("category", "unknown"),
            "goal_amount": campaign_data.get("goal_amount", 0),
            "currency": campaign_data.get("currency", "USD"),
            "beneficiary_country": campaign_data.get("beneficiary_country", "unknown"),
            "account_age_days": creator.get("account_age_days", 0),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "dim_summary": "\n".join(dim_lines) or "  (no dimension data)",
            "compliance_flags": ", ".join(compliance_flags[:5]) or "none",
            "fraud_signals": ", ".join(fraud_signals[:5]) or "none",
            "content_flags": ", ".join(content_flags[:3]) or "none",
        })

        return output

    except Exception as exc:
        logger.warning("[decision] LLM reasoning call failed: %s — using fallback", exc)
        return None


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

async def decision_node(state: dict) -> dict:
    """
    Decision node: final recommendation + human-readable reasoning.

    Consumes: risk_score, risk_dimensions, compliance_flags, fraud_signals,
              content_flags, _is_ofac_blocked, campaign_data
    Produces: risk_level, recommendation, confidence, reasoning_summary, model_version
    """
    campaign_id = state.get("campaign_id", "unknown")
    risk_score: int = state.get("risk_score") or 0
    is_ofac_blocked: bool = state.get("_is_ofac_blocked", False)

    compliance_flags: list[str] = state.get("compliance_flags") or []
    fraud_signals: list[str] = state.get("fraud_signals") or []
    content_flags: list[str] = state.get("content_flags") or []
    risk_dimensions = state.get("risk_dimensions") or {}
    campaign_data = state.get("campaign_data") or {}

    logger.info(
        "[decision] campaign_id=%s risk_score=%d ofac=%s",
        campaign_id, risk_score, is_ofac_blocked,
    )

    risk_level, recommendation = _score_to_level_and_rec(risk_score, is_ofac_blocked)

    # Try LLM reasoning (Gemini Pro)
    llm_output = await _llm_reasoning(
        campaign_data=campaign_data,
        risk_score=risk_score,
        risk_level=risk_level,
        recommendation=recommendation,
        compliance_flags=compliance_flags,
        fraud_signals=fraud_signals,
        content_flags=content_flags,
        risk_dimensions=risk_dimensions,
    )

    llm_used = llm_output is not None

    if llm_used:
        reasoning_summary = llm_output.reasoning_summary  # type: ignore[union-attr]
        llm_conf = llm_output.confidence  # type: ignore[union-attr]
        confidence = llm_conf if 0.5 <= llm_conf <= 1.0 else _compute_confidence(
            risk_score, risk_level, is_ofac_blocked, llm_used=True
        )
    else:
        reasoning_summary = _fallback_reasoning(
            score=risk_score,
            level=risk_level,
            recommendation=recommendation,
            campaign_data=campaign_data,
            compliance_flags=compliance_flags,
            fraud_signals=fraud_signals,
            content_flags=content_flags,
        )
        confidence = _compute_confidence(risk_score, risk_level, is_ofac_blocked, llm_used=False)

    settings = get_settings()
    model_tag = settings.gemini_pro_model if llm_used else "rules"

    logger.info(
        "[decision] Result: level=%s rec=%s confidence=%.2f llm=%s",
        risk_level, recommendation, confidence, llm_used,
    )

    return {
        "risk_level": risk_level,
        "recommendation": recommendation,
        "confidence": confidence,
        "reasoning_summary": reasoning_summary,
        "model_version": f"langgraph-gemini-{model_tag}-v3.0" if llm_used else "langgraph-rules-v3.0",
    }
