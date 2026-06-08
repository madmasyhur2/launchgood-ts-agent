"""
app/agent/state.py

AgentState schema for the LangGraph campaign analysis pipeline.
Uses TypedDict (required by LangGraph) + a Pydantic output model for
type-safe returns to the caller.

Node flow:
  intake → content_analysis → compliance_check → fraud_signals
         → risk_scoring → decision
"""

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models (shared between TypedDict state and Pydantic output)
# ---------------------------------------------------------------------------

class RiskDimension(BaseModel):
    """Score and signals for a single risk analysis dimension."""

    score: int = Field(..., ge=0, le=100, description="Risk score for this dimension (0-100)")
    signals: list[str] = Field(
        default_factory=list,
        description="Human-readable detected signals",
    )
    weight: float = Field(..., gt=0.0, le=1.0, description="Weight in the final composite score")


# ---------------------------------------------------------------------------
# AgentState — Pydantic model used as the canonical state representation.
# LangGraph StateGraph uses this directly via its __annotations__.
# ---------------------------------------------------------------------------

class AgentState(BaseModel):
    """
    Shared state object threaded through every LangGraph node.

    Each node reads from this state and writes back its outputs.
    The graph builds up a complete picture incrementally:
      intake_node → content_analysis_node → compliance_check_node
        → fraud_signal_node → risk_scoring_node → decision_node

    Pydantic validates the state at each node transition, catching
    data quality issues early during development.
    """

    # -------------------------------------------------------------------------
    # Input
    # -------------------------------------------------------------------------
    campaign_id: str = Field(..., description="UUID of the campaign being analysed")
    campaign_data: dict = Field(..., description="Full raw campaign submission payload")

    # -------------------------------------------------------------------------
    # Per-node outputs (populated incrementally as the graph runs)
    # -------------------------------------------------------------------------

    # intake_node: normalised / cleaned version of campaign_data
    normalized_data: Optional[dict] = None

    # content_analysis_node: flags from content screening
    content_flags: Optional[list[str]] = None

    # compliance_check_node: OFAC / jurisdiction flags
    compliance_flags: Optional[list[str]] = None

    # fraud_signal_node: pattern-based fraud signals
    fraud_signals: Optional[list[str]] = None

    # -------------------------------------------------------------------------
    # Risk dimensions — populated by risk_scoring_node
    # -------------------------------------------------------------------------
    # Keys match the scoring formula in SYSTEM.md §4:
    #   "content_quality", "compliance", "fraud_signals", "creator_credibility"
    risk_dimensions: Optional[dict[str, RiskDimension]] = None

    # -------------------------------------------------------------------------
    # Final outputs — populated by decision_node
    # -------------------------------------------------------------------------
    risk_score: Optional[int] = Field(None, ge=0, le=100)
    risk_level: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None
    recommendation: Optional[Literal["APPROVE", "ESCALATE", "REJECT"]] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    reasoning_summary: Optional[str] = None

    # Wall-clock time for the full agent run (used in SLA eval)
    processing_time_ms: Optional[int] = None

    # Model version used for traceability / regression testing
    model_version: Optional[str] = None

    # -------------------------------------------------------------------------
    # Internal tracking
    # -------------------------------------------------------------------------
    # Errors encountered during processing (non-fatal, for debugging)
    errors: list[str] = Field(default_factory=list)

    class Config:
        # Allow arbitrary types for dict fields
        arbitrary_types_allowed = True
