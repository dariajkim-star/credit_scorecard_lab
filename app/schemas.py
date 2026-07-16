"""Pydantic request/response schemas for the scoring API (Story 2.3, AD-5).

The input schema is the FR-5-confirmed 7-field feature set (API_SPEC v0.3 §4,
identical to the manifests' feature_order). Every field is nullable - the WOE
Missing bin (champion) and LightGBM native NaN routing (challenger) handle
missing values - but an all-null request is rejected as meaningless.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scorecard.reasons import ChallengerReasonCode, ChampionReasonCode

ModelChoice = Literal["champion", "challenger", "both"]
ModelChoiceSingle = Literal["champion", "challenger"]

# Hard sanity bounds -> 400 VALUE_OUT_OF_RANGE (story-owner decision, recorded
# in the 2.3 report): generous physical/plausibility limits, NOT the training
# range - values outside the observed binning range but inside these bounds
# score fine (WOE open-ended outer bins) and only earn a warning.
HARD_BOUNDS: dict[str, tuple[float, float]] = {
    "fico_range_low": (300.0, 850.0),   # FICO scale limits
    "annual_inc": (0.0, 1e9),
    "dti": (0.0, 999.0),
    "revol_util": (0.0, 500.0),
    "inq_last_6mths": (0.0, 100.0),
}


class ScoreRequest(BaseModel):
    # extra="forbid": a misspelled field name (e.g. "annual_income") would
    # otherwise be silently dropped and the real field scored as missing -
    # a wrong score with no error, for a credit decision input (code review
    # finding; matches this codebase's fail-fast convention elsewhere).
    model_config = ConfigDict(extra="forbid")

    fico_range_low: float | None = None
    annual_inc: float | None = None
    dti: float | None = None
    home_ownership: str | None = None
    revol_util: float | None = None
    inq_last_6mths: float | None = None
    purpose: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ScoreRequest":
        if all(v is None for v in self.model_dump().values()):
            raise ValueError("all fields are null - at least one input is required")
        return self


class ModelBlock(BaseModel):
    name: str
    version: str
    type: str


class SingleScoreResponse(BaseModel):
    score: float
    pd: float
    grade: int
    reason_codes: list[ChampionReasonCode] | list[ChallengerReasonCode]
    warnings: list[str]
    model: ModelBlock


class BothScoreResponse(BaseModel):
    champion: SingleScoreResponse
    challenger: SingleScoreResponse
    score_gap: float


class BatchScoreRequest(BaseModel):
    applicants: list[ScoreRequest] = Field(..., min_length=1, max_length=1000)


class BatchScoreResponse(BaseModel):
    results: list[SingleScoreResponse]
    grade_distribution: dict[int, int]


class CutoffSimRequest(BaseModel):
    cutoff_score: float
    model: Literal["champion", "challenger"] = "champion"


class CurvePoint(BaseModel):
    cutoff: float
    approval_rate: float | None
    bad_rate: float | None


class CutoffSimResponse(BaseModel):
    cutoff_score: float
    approval_rate: float | None
    bad_rate_approved: float | None
    bad_rate_rejected: float | None
    curve: list[CurvePoint]
