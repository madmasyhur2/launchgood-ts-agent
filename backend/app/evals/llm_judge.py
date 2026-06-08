"""
app/evals/llm_judge.py

LLM-as-judge eval for campaign reasoning summary quality.

Uses Gemini Pro via LangChain with_structured_output() to evaluate the
quality of reasoning summaries produced by the decision node.

Judge scores 4 dimensions (1-5 each):
  - Clarity      : understandable to a non-technical reviewer?
  - Completeness : covers all major risk factors?
  - Actionability: gives clear next steps?
  - Accuracy     : consistent with the risk score / level?

The judge is intentionally separate from the agent LLM to avoid circular bias.

Usage:
    from app.evals.llm_judge import score_reasoning, JudgeScores
    scores = await score_reasoning(
        reasoning_summary="...",
        risk_score=42,
        risk_level="MEDIUM",
        recommendation="ESCALATE",
        flags=["high_risk_beneficiary_country"],
    )
    print(scores.overall_score)   # float 1.0–5.0
"""

from __future__ import annotations

import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic output schema — used by with_structured_output()
# ---------------------------------------------------------------------------

class JudgeScores(BaseModel):
    """
    Structured quality scores from the LLM-as-judge eval.
    All dimensions scored 1 (poor) to 5 (excellent).
    """

    clarity: int = Field(
        ..., ge=1, le=5,
        description=(
            "Is the summary understandable to a non-technical T&S reviewer? "
            "1=confusing jargon, 5=perfectly clear."
        ),
    )
    completeness: int = Field(
        ..., ge=1, le=5,
        description=(
            "Does the summary mention all major risk factors flagged by the analysis? "
            "1=missing key info, 5=comprehensive."
        ),
    )
    actionability: int = Field(
        ..., ge=1, le=5,
        description=(
            "Does the summary give clear next steps for the reviewer? "
            "1=no guidance, 5=explicit clear action."
        ),
    )
    accuracy: int = Field(
        ..., ge=1, le=5,
        description=(
            "Is the reasoning consistent with the risk score and recommendation? "
            "1=contradicts the score, 5=fully aligned."
        ),
    )
    rationale: str = Field(
        ...,
        description="One sentence justification for the scores.",
    )

    @property
    def overall_score(self) -> float:
        """Weighted average: clarity and accuracy weighted slightly higher."""
        weights = {
            "clarity": 0.30,
            "completeness": 0.25,
            "actionability": 0.20,
            "accuracy": 0.25,
        }
        return round(
            self.clarity * weights["clarity"]
            + self.completeness * weights["completeness"]
            + self.actionability * weights["actionability"]
            + self.accuracy * weights["accuracy"],
            2,
        )

    def as_dict(self) -> dict:
        return {
            "clarity": self.clarity,
            "completeness": self.completeness,
            "actionability": self.actionability,
            "accuracy": self.accuracy,
            "overall_score": self.overall_score,
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# Fallback scores (when LLM is unavailable)
# ---------------------------------------------------------------------------

def _make_fallback_scores(reason: str = "Judge LLM unavailable.") -> JudgeScores:
    """
    Return a neutral fallback when the judge LLM call fails.
    Uses ge=1 minimum so Pydantic validation still passes.
    overall_score = 0.0 signals the caller that this is a fallback.
    """
    # Patch: use a subclass trick to bypass the ge=1 constraint
    # by constructing directly via model_construct (no validation)
    obj = JudgeScores.model_construct(
        clarity=0,
        completeness=0,
        actionability=0,
        accuracy=0,
        rationale=reason,
    )
    return obj  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_PROMPT = """\
You are an expert evaluator of AI-generated Trust & Safety reasoning summaries.
Score a reasoning summary produced by an automated campaign moderation system.

The summary is read by human reviewers who make fast, high-stakes decisions.
Evaluate it on FOUR dimensions (scale 1-5):

1. CLARITY (1-5): Is it understandable to a non-technical reviewer?
   1=confusing jargon or unclear structure
   3=mostly clear with minor ambiguity
   5=crystal clear plain language

2. COMPLETENESS (1-5): Does it cover all major risk factors?
   1=misses the most important flags
   3=covers the main issue but omits secondary factors
   5=comprehensively addresses all significant risk dimensions

3. ACTIONABILITY (1-5): Does it give the reviewer clear next steps?
   1=no guidance on what to do
   3=implies an action but not explicitly stated
   5=explicitly states action, why, and who should do it

4. ACCURACY (1-5): Is the reasoning consistent with the score/level?
   1=reasoning contradicts the score
   3=mostly consistent with minor gaps
   5=perfectly aligned — reasoning justifies the exact score\
"""

_JUDGE_USER_TEMPLATE = """\
Evaluate this reasoning summary:

---
{reasoning_summary}
---

Context (what produced this summary):
  Risk Score     : {risk_score}/100
  Risk Level     : {risk_level}
  Recommendation : {recommendation}
  Top Flags      : {flags}

Return scores for all 4 dimensions and a one-sentence rationale.\
"""

_prompt = ChatPromptTemplate.from_messages([
    ("system", _JUDGE_SYSTEM_PROMPT),
    ("human", _JUDGE_USER_TEMPLATE),
])


def _get_judge_llm() -> ChatGoogleGenerativeAI:
    """Build Gemini Pro judge LLM with structured output."""
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=settings.gemini_pro_model,
        google_api_key=settings.google_api_key,
        temperature=0.1,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def score_reasoning(
    reasoning_summary: str,
    risk_score: int,
    risk_level: str,
    recommendation: str,
    flags: list[str] | None = None,
) -> JudgeScores:
    """
    Score a reasoning summary using Gemini Pro as judge.

    Returns a JudgeScores object. If the LLM is unavailable or key is missing,
    returns a fallback with all dimensions set to 0 and overall_score=0.0.

    Args:
        reasoning_summary: The summary text to evaluate.
        risk_score: The composite risk score (0-100).
        risk_level: LOW | MEDIUM | HIGH.
        recommendation: APPROVE | ESCALATE | REJECT.
        flags: List of detected signal strings (compliance, fraud, etc.)
    """
    settings = get_settings()

    if not settings.google_api_key or settings.google_api_key == "your-google-api-key-here":
        logger.warning("[llm_judge] GOOGLE_API_KEY not set — returning fallback scores")
        return _make_fallback_scores("GOOGLE_API_KEY not configured.")

    if not reasoning_summary or len(reasoning_summary.strip()) < 10:
        logger.warning("[llm_judge] reasoning_summary too short — returning fallback")
        return _make_fallback_scores("reasoning_summary too short to evaluate.")

    flags_str = ", ".join(flags[:6]) if flags else "none"

    try:
        llm = _get_judge_llm()
        structured_llm = llm.with_structured_output(JudgeScores)
        chain = _prompt | structured_llm

        scores: JudgeScores = await chain.ainvoke({
            "reasoning_summary": reasoning_summary[:1500],
            "risk_score": risk_score,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "flags": flags_str,
        })

        logger.info(
            "[llm_judge] Scores: clarity=%d completeness=%d actionability=%d "
            "accuracy=%d overall=%.2f",
            scores.clarity,
            scores.completeness,
            scores.actionability,
            scores.accuracy,
            scores.overall_score,
        )
        return scores

    except Exception as exc:
        logger.warning("[llm_judge] Judge call failed: %s — returning fallback", exc)
        return _make_fallback_scores(f"Judge LLM call failed: {exc}")


async def score_agent_result(agent_state) -> JudgeScores:
    """
    Convenience wrapper: score a complete AgentState object.
    Extracts the fields needed by `score_reasoning`.

    Args:
        agent_state: An AgentState Pydantic model instance.
    """
    all_flags: list[str] = []
    if agent_state.compliance_flags:
        all_flags.extend(agent_state.compliance_flags[:3])
    if agent_state.fraud_signals:
        all_flags.extend(agent_state.fraud_signals[:3])

    return await score_reasoning(
        reasoning_summary=agent_state.reasoning_summary or "",
        risk_score=agent_state.risk_score or 0,
        risk_level=agent_state.risk_level or "MEDIUM",
        recommendation=agent_state.recommendation or "ESCALATE",
        flags=all_flags,
    )
