"""
app/agent/graph.py

LangGraph campaign analysis graph — FULL IMPLEMENTATION (Session 2).

Node flow:
  START -> intake -> content_analysis -> compliance_check
        -> fraud_signals -> risk_scoring -> decision -> END

Architecture note:
  LangGraph StateGraph accumulates state by merging the dicts returned by
  each node into the running state. We use a TypedDict-compatible schema
  so that all keys are preserved across the full pipeline.

Public API (unchanged from Session 1 stub):
  run_analysis(campaign_id: str, campaign_data: dict) -> AgentState
"""

import logging
import time
import uuid
from typing import Any, Optional
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.state import AgentState, RiskDimension
from app.agent.nodes.intake import intake_node
from app.agent.nodes.content_analysis import content_analysis_node
from app.agent.nodes.compliance_check import compliance_check_node
from app.agent.nodes.fraud_signals import fraud_signals_node
from app.agent.nodes.risk_scoring import risk_scoring_node
from app.agent.nodes.decision import decision_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline state schema (TypedDict so LangGraph preserves all keys)
# ---------------------------------------------------------------------------

class PipelineState(TypedDict, total=False):
    # Input
    campaign_id: str
    campaign_data: dict

    # Intake outputs
    normalized_data: Optional[dict]

    # Content analysis outputs
    content_flags: Optional[list]
    _content_score: int
    _content_brief: str

    # Compliance outputs
    compliance_flags: Optional[list]
    _compliance_score: int
    _is_ofac_blocked: bool

    # Fraud signal outputs
    fraud_signals: Optional[list]
    _fraud_score: int

    # Risk scoring outputs
    risk_dimensions: Optional[dict]
    risk_score: Optional[int]

    # Decision outputs
    risk_level: Optional[str]
    recommendation: Optional[str]
    confidence: Optional[float]
    reasoning_summary: Optional[str]
    model_version: Optional[str]

    # Metadata
    errors: list


def _build_graph():
    """Construct and compile the LangGraph StateGraph."""
    builder = StateGraph(PipelineState)

    # Register nodes
    builder.add_node("intake", intake_node)
    builder.add_node("content_analysis", content_analysis_node)
    builder.add_node("compliance_check", compliance_check_node)
    builder.add_node("fraud_signals", fraud_signals_node)
    builder.add_node("risk_scoring", risk_scoring_node)
    builder.add_node("decision", decision_node)

    # Wire edges (linear pipeline)
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "content_analysis")
    builder.add_edge("content_analysis", "compliance_check")
    builder.add_edge("compliance_check", "fraud_signals")
    builder.add_edge("fraud_signals", "risk_scoring")
    builder.add_edge("risk_scoring", "decision")
    builder.add_edge("decision", END)

    return builder.compile()


# Compile once at import time for performance
_graph = _build_graph()


# ---------------------------------------------------------------------------
# State -> AgentState converter
# ---------------------------------------------------------------------------

def _state_to_agent_state(state: dict, elapsed_ms: int) -> AgentState:
    """
    Convert the raw LangGraph state dict into a validated AgentState.
    """
    raw_dims = state.get("risk_dimensions") or {}
    typed_dims: dict[str, RiskDimension] = {}
    for key, val in raw_dims.items():
        if isinstance(val, RiskDimension):
            typed_dims[key] = val
        elif isinstance(val, dict):
            typed_dims[key] = RiskDimension(
                score=int(val.get("score", 0)),
                signals=list(val.get("signals", [])),
                weight=float(val.get("weight", 0.0)),
            )

    return AgentState(
        campaign_id=state.get("campaign_id", str(uuid.uuid4())),
        campaign_data=state.get("campaign_data", {}),
        normalized_data=state.get("normalized_data"),
        content_flags=state.get("content_flags"),
        compliance_flags=state.get("compliance_flags"),
        fraud_signals=state.get("fraud_signals"),
        risk_dimensions=typed_dims if typed_dims else None,
        risk_score=state.get("risk_score"),
        risk_level=state.get("risk_level"),  # type: ignore[arg-type]
        recommendation=state.get("recommendation"),  # type: ignore[arg-type]
        confidence=state.get("confidence"),
        reasoning_summary=state.get("reasoning_summary"),
        processing_time_ms=elapsed_ms,
        model_version=state.get("model_version", "langgraph-v2.0"),
        errors=state.get("errors", []),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_analysis(campaign_id: str, campaign_data: dict) -> AgentState:
    """
    Run the full LangGraph campaign analysis pipeline.

    Args:
        campaign_id: UUID string for the campaign being analysed.
        campaign_data: Raw campaign submission payload (from API request body).

    Returns:
        Fully populated AgentState with risk score, level, recommendation,
        reasoning summary, and per-dimension breakdown.
    """
    logger.info("[graph] Starting analysis for campaign_id=%s", campaign_id)
    start_ms = int(time.time() * 1000)

    initial_state: PipelineState = {
        "campaign_id": campaign_id,
        "campaign_data": campaign_data,
        # All other fields start as None / empty
        "normalized_data": None,
        "content_flags": None,
        "compliance_flags": None,
        "fraud_signals": None,
        "risk_dimensions": None,
        "risk_score": None,
        "risk_level": None,
        "recommendation": None,
        "confidence": None,
        "reasoning_summary": None,
        "errors": [],
        # Private per-node scores (not part of AgentState public API)
        "_content_score": 20,
        "_content_brief": "",
        "_compliance_score": 10,
        "_is_ofac_blocked": False,
        "_fraud_score": 10,
    }

    try:
        final_state: dict = await _graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("[graph] Pipeline failed for campaign_id=%s: %s", campaign_id, exc)
        # Return a safe failure state so the API never crashes
        elapsed_ms = int(time.time() * 1000) - start_ms
        return AgentState(
            campaign_id=campaign_id,
            campaign_data=campaign_data,
            risk_score=50,
            risk_level="MEDIUM",
            recommendation="ESCALATE",
            confidence=0.30,
            reasoning_summary=(
                "Analysis pipeline encountered an unexpected error. "
                "Campaign has been escalated for manual review as a precaution."
            ),
            processing_time_ms=elapsed_ms,
            model_version="langgraph-error-fallback",
            errors=[f"pipeline_error: {exc}"],
        )

    elapsed_ms = int(time.time() * 1000) - start_ms
    logger.info("[graph] Pipeline complete in %dms for campaign_id=%s", elapsed_ms, campaign_id)

    result = _state_to_agent_state(final_state, elapsed_ms)
    return result
