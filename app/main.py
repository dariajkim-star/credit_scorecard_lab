"""Scoring API (Story 2.3, FR12): 6 endpoints per API_SPEC.md v0.3 §1-§6.

Pure assembly layer (AD-9): every calculation lives in scorecard/* - this
module wires pydantic I/O to those functions and enforces the error contract
(422 schema / 400 VALUE_OUT_OF_RANGE / 503 MODEL_NOT_LOADED, §0). Cutoff
decisions are deliberately absent - the API returns score/pd/grade/reasons
and the consumer (dashboard, P3 agent) applies its own cutoff.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from app import schemas
from app.loader import ModelStore, load_store
from scorecard import strategy
from scorecard.evaluation import challenger_p_bad, champion_p_bad, generalized_score
from scorecard.grading import assign_grade
from scorecard.preprocessing import CATEGORICAL_COLUMNS
from scorecard.reasons import challenger_reason_codes, champion_reason_codes

logger = logging.getLogger("app.api")

# AC #5 (per-request model_version logging): under uvicorn only uvicorn's own
# loggers get handlers, so "app.*" INFO records were silently dropped (found
# in the live-run proof, not by TestClient - caplog attaches its own handler
# and masks this). Give the root logger a handler once if nothing configured.
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
logging.getLogger("app").setLevel(logging.INFO)

app = FastAPI(title="credit-scorecard-lab scoring API", version="0.3")
STORE: ModelStore = load_store()


class ApiError(Exception):
    def __init__(self, status_code: int, detail: str, error_code: str):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": exc.error_code},
    )


def _require_loaded() -> None:
    if not STORE.loaded:
        raise ApiError(503, f"model artifacts not loaded: {STORE.error}", "MODEL_NOT_LOADED")


def _check_bounds(payload: schemas.ScoreRequest) -> list[str]:
    """400 on hard-bound violations; warnings inside bounds but clearly
    atypical (outside FICO-adjacent typical ranges handled by open-ended
    outer WOE bins). Bounds rationale: schemas.HARD_BOUNDS docstring."""
    warnings: list[str] = []
    for field_name, (lo, hi) in schemas.HARD_BOUNDS.items():
        value = getattr(payload, field_name)
        if value is None:
            continue
        if value < lo or value > hi:
            raise ApiError(
                400,
                f"{field_name}={value} is outside the acceptable range [{lo}, {hi}] - "
                "the model cannot produce a trustworthy score for this input",
                "VALUE_OUT_OF_RANGE",
            )
    for field_name in ("fico_range_low", "annual_inc", "dti", "revol_util", "inq_last_6mths"):
        if getattr(payload, field_name) is None:
            warnings.append(f"{field_name} is missing - scored via the fitted Missing bin")
    return warnings


def _applicant_frame(payload: schemas.ScoreRequest, variables: list[str]) -> pd.DataFrame:
    """pydantic payload -> 1-row DataFrame with per-column dtypes preserved.

    Built from a list-of-dicts (NOT via a Series transpose - Story 2.2 found
    that route collapses every column to object dtype). Categoricals are cast
    for the challenger path; champion's transform_woe accepts plain object
    strings for categoricals and floats for numerics.
    """
    df = pd.DataFrame([payload.model_dump()])[variables]
    for col in variables:
        if col in CATEGORICAL_COLUMNS:
            df[col] = df[col].astype("category")
        else:
            df[col] = pd.to_numeric(df[col])
    return df


def _score_one(payload: schemas.ScoreRequest, model_type: str, warnings: list[str]) -> schemas.SingleScoreResponse:
    variables = STORE.variables
    df = _applicant_frame(payload, variables)
    manifest = STORE.manifests[model_type]
    bundle = STORE.bundles[model_type]

    if model_type == "champion":
        p_bad = float(champion_p_bad(bundle, df, variables)[0])
        reason_codes = champion_reason_codes(bundle, df.iloc[0], variables)
    else:
        p_bad = float(challenger_p_bad(bundle, df, variables)[0])
        reason_codes = challenger_reason_codes(
            bundle, df.iloc[0], variables, explainer=STORE.explainer
        )
    score = float(np.asarray(generalized_score(np.array([p_bad])))[0])
    grade = int(assign_grade(np.array([score]), np.asarray(manifest["grade_thresholds"]))[0])

    logger.info("scored applicant: model_version=%s score=%.1f grade=%d",
                manifest["model_version"], score, grade)
    return schemas.SingleScoreResponse(
        score=round(score, 1),
        pd=round(p_bad, 6),
        grade=grade,
        reason_codes=reason_codes,
        warnings=warnings,
        model=schemas.ModelBlock(
            name=manifest["model_type"], version=manifest["model_version"], type=model_type
        ),
    )


@app.get("/health")
def health() -> dict:
    if STORE.loaded:
        return {"status": "ok", "model_loaded": True,
                "model_version": STORE.model_version("champion")}
    return {"status": "degraded", "model_loaded": False, "model_version": None}


@app.get("/v1/model/info")
def model_info() -> dict:
    _require_loaded()
    champ_m, chall_m = STORE.manifests["champion"], STORE.manifests["challenger"]
    return {
        "champion": {
            "name": champ_m["model_type"], "version": champ_m["model_version"],
            "trained_at": champ_m.get("trained_at"), "pdo": champ_m["pdo"],
            "base_score": champ_m["base_score"], "metrics": STORE.metrics["champion"],
        },
        "challenger": {
            "name": chall_m["model_type"], "version": chall_m["model_version"],
            "calibration": chall_m["calibration_method"],
            "metrics": STORE.metrics["challenger"],
        },
        "sample_design": {
            "train_vintages": "2012-2013", "valid_vintage": "2014", "oot_vintage": "2015",
            "bad_definition": "loan_status in (Charged Off, Default), 36-month term",
        },
    }


@app.get("/v1/grades")
def grades(model: str = Query("champion", pattern="^(champion|challenger)$")) -> dict:
    _require_loaded()
    return {
        "model": model,
        "grades": STORE.grade_tables[model],
        "monotonic_validated": STORE.monotonic_validated[model],
    }


@app.post("/v1/score")
def score(
    payload: schemas.ScoreRequest,
    model: schemas.ModelChoice = Query("champion"),
):
    _require_loaded()
    warnings = _check_bounds(payload)
    if model in ("champion", "challenger"):
        return _score_one(payload, model, warnings)
    champ = _score_one(payload, "champion", warnings)
    chall = _score_one(payload, "challenger", warnings)
    return schemas.BothScoreResponse(
        champion=champ, challenger=chall,
        score_gap=round(chall.score - champ.score, 1),
    )


@app.post("/v1/score/batch")
def score_batch(
    payload: schemas.BatchScoreRequest,
    model: str = Query("champion", pattern="^(champion|challenger)$"),
) -> schemas.BatchScoreResponse:
    _require_loaded()
    results = []
    for applicant in payload.applicants:
        warnings = _check_bounds(applicant)
        results.append(_score_one(applicant, model, warnings))
    distribution: dict[int, int] = {}
    for r in results:
        distribution[r.grade] = distribution.get(r.grade, 0) + 1
    return schemas.BatchScoreResponse(
        results=results, grade_distribution=dict(sorted(distribution.items()))
    )


@app.post("/v1/simulate/cutoff")
def simulate_cutoff(payload: schemas.CutoffSimRequest) -> schemas.CutoffSimResponse:
    _require_loaded()
    point = strategy.lookup_cutoff(STORE.frame, payload.model, payload.cutoff_score)
    curve_df = STORE.curves[payload.model]  # precomputed at startup (immutable frame)
    curve = [
        schemas.CurvePoint(
            cutoff=round(row["cutoff"], 2),
            approval_rate=None if pd.isna(row["approval_rate"]) else round(row["approval_rate"], 4),
            bad_rate=None if pd.isna(row["bad_rate"]) else round(row["bad_rate"], 4),
        )
        for row in curve_df.to_dict("records")
    ]
    logger.info("cutoff simulation: model_version=%s cutoff=%.1f",
                STORE.model_version(payload.model), payload.cutoff_score)
    return schemas.CutoffSimResponse(
        cutoff_score=payload.cutoff_score,
        approval_rate=point["approval_rate"],
        bad_rate_approved=point["bad_rate"],
        bad_rate_rejected=point["bad_rate_rejected"],
        curve=curve,
    )
