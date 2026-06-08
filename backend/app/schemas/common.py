"""
app/schemas/common.py

Shared Pydantic v2 schemas reused across multiple routers.
"""

from typing import Literal

from pydantic import BaseModel, Field


class RiskDimension(BaseModel):
    """Score breakdown for a single risk dimension.

    Matches the structure stored in ai_analyses.risk_dimensions (JSONB).
    """

    score: int = Field(..., ge=0, le=100, description="Risk score for this dimension (0-100)")
    signals: list[str] = Field(
        default_factory=list,
        description="Human-readable signals detected (e.g. 'high_risk_beneficiary_country')",
    )
    weight: float = Field(..., gt=0.0, le=1.0, description="Weight applied in final score calculation")


class AnalysisFlag(BaseModel):
    """A specific flag raised during AI analysis."""

    type: Literal["COMPLIANCE", "FRAUD", "CONTENT", "CREDIBILITY", "SYSTEM"] = Field(
        ..., description="Category of the flag"
    )
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        ..., description="Severity level"
    )
    detail: str = Field(..., description="Human-readable description for the reviewer")
