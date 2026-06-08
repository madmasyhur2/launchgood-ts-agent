"""
nodes/content_analysis.py

Content Analysis node: uses Gemini Flash via LangChain to analyse campaign
title + story for quality signals, red flags, and prohibited content patterns.

LLM call: YES — gemini-2.0-flash with with_structured_output() (Pydantic v2)
"""

import logging
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic output schema — used by with_structured_output()
# ---------------------------------------------------------------------------

class ContentAnalysisOutput(BaseModel):
    """Structured output from the content analysis LLM call."""

    content_score: int = Field(
        ..., ge=0, le=100,
        description="Content quality risk score. Higher = more concerning (0-100)."
    )
    quality_signals: list[str] = Field(
        default_factory=list,
        description="Positive signals: clear_goal, compelling_story, realistic_amount, etc."
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="Negative signals: vague_story, prohibited_keywords, urgency_manipulation, etc."
    )
    all_signals: list[str] = Field(
        default_factory=list,
        description="Combined list of all signals (quality + red flags)."
    )
    brief_assessment: str = Field(
        ...,
        description="One sentence content quality assessment for the reasoning summary."
    )


# ---------------------------------------------------------------------------
# Deterministic pre-check (fast, no LLM)
# ---------------------------------------------------------------------------

PROHIBITED_PATTERNS = [
    "bomb", "weapon", "explosive", "jihad", "terrorism", "terrorist",
    "money laundering", "drug trafficking", "human trafficking",
    "illegal", "murder", "assassination",
]

URGENCY_MANIPULATORS = [
    "last chance", "act now", "send money immediately", "wire transfer",
    "western union", "gift card", "untraceable",
]


def _deterministic_content_flags(title: str, story: str) -> tuple[list[str], int]:
    """Fast pre-check for prohibited keywords before LLM call."""
    text = f"{title} {story}".lower()
    flags: list[str] = []
    score_bump = 0

    for pattern in PROHIBITED_PATTERNS:
        if pattern in text:
            flags.append(f"prohibited_keyword:{pattern}")
            score_bump += 25

    for pattern in URGENCY_MANIPULATORS:
        if pattern in text:
            flags.append(f"urgency_manipulation:{pattern}")
            score_bump += 15

    return flags, min(score_bump, 60)


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a Trust & Safety analyst for LaunchGood, an Islamic crowdfunding platform.
Assess the campaign title and story for:
1. Content quality: Is the story clear, specific, and compelling?
2. Red flags: Vague descriptions, manipulation tactics, suspicious patterns
3. Prohibited content: Illegal activities, hate speech, violence

Signal naming convention (use these exact strings where applicable):
  Positive: "clear_goal", "compelling_story", "specific_use_of_funds",
             "realistic_amount", "credible_organization", "supporting_documents"
  Negative: "vague_story", "no_specific_use_of_funds", "emotional_manipulation",
             "urgency_language", "generic_appeal", "suspicious_patterns",
             "inconsistent_details", "unrealistic_claims"

Return a JSON object with content_score (0-100, higher=worse), quality_signals,
red_flags, all_signals, and brief_assessment (one sentence).\
"""

USER_TEMPLATE = """\
Campaign Title: {title}
Category: {category}
Story:
{story}

Analyse this campaign submission.\
"""

_prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", USER_TEMPLATE),
])


def _get_llm() -> ChatGoogleGenerativeAI:
    """Build Gemini Flash LLM with structured output bound."""
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=settings.gemini_flash_model,
        google_api_key=settings.google_api_key,
        temperature=0.0,
    )


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

async def content_analysis_node(state: dict) -> dict:
    """
    Content Analysis node: LLM-powered campaign content assessment.

    Consumes: normalized_data.title, normalized_data.story
    Produces:
        content_flags     (list[str])
        _content_score    (int)
        _content_brief    (str)
    """
    settings = get_settings()
    normalized = state.get("normalized_data") or state.get("campaign_data") or {}

    title = normalized.get("title", "")
    story = normalized.get("story", "")
    category = normalized.get("category", "")
    campaign_id = state.get("campaign_id", "unknown")

    logger.info(
        "[content_analysis] Analysing campaign_id=%s title='%s'",
        campaign_id, title[:60],
    )

    # --- Fast deterministic pre-check ---
    det_flags, det_score_bump = _deterministic_content_flags(title, story)
    if det_flags:
        logger.warning("[content_analysis] Deterministic flags: %s", det_flags)

    # --- LLM content analysis ---
    try:
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY not set — using rule-based fallback")

        llm = _get_llm()
        structured_llm = llm.with_structured_output(ContentAnalysisOutput)
        chain = _prompt | structured_llm

        output: ContentAnalysisOutput = await chain.ainvoke({
            "title": title,
            "category": category,
            "story": story[:3000],
        })

        logger.info(
            "[content_analysis] LLM score=%d signals=%s",
            output.content_score, output.all_signals,
        )

        all_signals = list(set(output.all_signals + det_flags))
        final_score = min(100, output.content_score + det_score_bump)

        return {
            "content_flags": all_signals,
            "_content_score": final_score,
            "_content_brief": output.brief_assessment,
        }

    except Exception as exc:
        logger.error("[content_analysis] LLM call failed: %s — using fallback", exc)
        story_len = len(story)
        if not story:
            fallback_score, fallback_signals = 50, ["missing_story", "incomplete_submission"]
        elif story_len < 100:
            fallback_score, fallback_signals = 30, ["thin_story", "low_detail"]
        elif story_len < 300:
            fallback_score, fallback_signals = 20, ["brief_story", "moderate_detail"]
        else:
            fallback_score, fallback_signals = 10, ["clear_goal", "compelling_story"]

        return {
            "content_flags": fallback_signals + det_flags,
            "_content_score": min(100, fallback_score + det_score_bump),
            "_content_brief": "Content assessment used rule-based fallback (LLM unavailable).",
            "errors": state.get("errors", []) + [f"content_analysis_llm_error: {exc}"],
        }
