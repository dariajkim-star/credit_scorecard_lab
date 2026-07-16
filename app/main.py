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
from app.loader import CURRENT_CUTOFF, ModelStore, load_store
from scorecard import strategy
from scorecard.evaluation import challenger_p_bad, champion_p_bad, generalized_score
from scorecard.grading import assign_grade
from scorecard.preprocessing import CATEGORICAL_COLUMNS
from scorecard.profit import find_optimal_cutoff
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


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Anything unanticipated (unseen-category edge case an underlying
    # library does decide to raise on, a version-skew joblib load issue,
    # etc.) previously escaped as FastAPI's bare default 500 body - no
    # "detail"/"error_code", breaking the §0 contract every other response
    # path honors (code review finding). Not one of the 3 documented codes,
    # but keeps the response *shape* consistent for the P3 consumer.
    logger.exception("unhandled error in %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"internal error: {exc}", "error_code": "INTERNAL_ERROR"},
    )


def _require_loaded() -> None:
    if not STORE.loaded:
        raise ApiError(503, f"model artifacts not loaded: {STORE.error}", "MODEL_NOT_LOADED")


def _check_bounds(payload: schemas.ScoreRequest, index: int | None = None) -> list[str]:
    """400 on hard-bound violations; warnings for missing fields and unseen
    categorical values (both scored, but silently - the caller should know).
    Bounds rationale: schemas.HARD_BOUNDS docstring. ``index`` (batch only)
    names which applicant failed, so a 400 doesn't discard 499 good results
    with no way to identify the culprit (code review finding)."""
    prefix = f"applicant[{index}]: " if index is not None else ""
    warnings: list[str] = []
    for field_name, (lo, hi) in schemas.HARD_BOUNDS.items():
        value = getattr(payload, field_name)
        if value is None:
            continue
        if value < lo or value > hi:
            raise ApiError(
                400,
                f"{prefix}{field_name}={value} is outside the acceptable range [{lo}, {hi}] - "
                "the model cannot produce a trustworthy score for this input",
                "VALUE_OUT_OF_RANGE",
            )
    for field_name in ("fico_range_low", "annual_inc", "dti", "revol_util", "inq_last_6mths"):
        if getattr(payload, field_name) is None:
            warnings.append(f"{field_name} is missing")
    # Unseen category: silently routed through the Special bin (champion) or
    # an uncalibrated fresh category code (challenger) with no error - found
    # empirically in code review (neither path raises). Warn instead of
    # trusting the model's silent handling.
    for field_name in ("home_ownership", "purpose"):
        value = getattr(payload, field_name)
        known = STORE.known_categories.get(field_name)
        if value is not None and known is not None and value not in known:
            warnings.append(f"{field_name}={value!r} was not observed in training data")
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
        with STORE.explainer_lock:  # shared TreeExplainer, not verified thread-safe
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
    if model in ("champion", "challenger"):
        warnings = _check_bounds(payload)
        return _score_one(payload, model, warnings)
    # _check_bounds is called once per model rather than sharing one list -
    # a shared list instance embedded in both response objects would alias
    # (mutating one response's warnings would silently mutate the other's),
    # and a single bounds check can't be re-run per model anyway since
    # ApiError already stops the request on the first violation regardless
    # (code review finding).
    champ = _score_one(payload, "champion", _check_bounds(payload))
    chall = _score_one(payload, "challenger", _check_bounds(payload))
    return schemas.BothScoreResponse(
        champion=champ, challenger=chall,
        score_gap=round(chall.score - champ.score, 1),
    )


@app.post("/v1/score/batch")
def score_batch(
    payload: schemas.BatchScoreRequest,
    model: schemas.ModelChoiceSingle = Query("champion"),
) -> schemas.BatchScoreResponse:
    _require_loaded()
    # Validate every applicant BEFORE scoring any of them: scoring runs SHAP
    # per applicant, so failing fast after applicant #500 of 1000 (previous
    # behavior) wasted 499 SHAP computations and discarded all their results
    # for a single bad input, with no indication which one failed (code
    # review finding). The index in the error lets the caller find it.
    all_warnings = [
        _check_bounds(applicant, index=i) for i, applicant in enumerate(payload.applicants)
    ]
    results = [
        _score_one(applicant, model, warnings)
        for applicant, warnings in zip(payload.applicants, all_warnings)
    ]
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


def _profit_point(base_curve: pd.DataFrame, cutoff: float, avg_loan_amnt: float) -> tuple[dict, float]:
    """Nearest-cutoff lookup on the precomputed unscaled curve (avg_loan_amnt=1
    baked in at startup, scaled here) + its approval_rate. Nearest instead of
    exact match since current_cutoff (546.0) rarely lands exactly on one of
    the 101 grid points."""
    idx = (base_curve["cutoff"] - cutoff).abs().idxmin()
    row = base_curve.loc[idx]
    approval_rate = None if pd.isna(row["approval_rate"]) else float(row["approval_rate"])
    expected_annual_profit = float(row["expected_annual_profit"]) * avg_loan_amnt
    return {"approval_rate": approval_rate, "expected_annual_profit": expected_annual_profit}, float(row["cutoff"])


@app.post("/v1/simulate/profit-cutoff")
def simulate_profit_cutoff(payload: schemas.ProfitCutoffRequest) -> schemas.ProfitCutoffResponse:
    _require_loaded()
    base_curve = STORE.profit_base_curves[payload.model]  # avg_loan_amnt=1.0 baked in, precomputed

    current, current_snapped = _profit_point(base_curve, CURRENT_CUTOFF, payload.avg_loan_amnt)
    optimal_cutoff = find_optimal_cutoff(base_curve)  # argmax is scale-invariant to avg_loan_amnt
    optimal, _ = _profit_point(base_curve, optimal_cutoff, payload.avg_loan_amnt)

    curve = [
        schemas.ProfitCurvePoint(
            cutoff=round(row["cutoff"], 2),
            approval_rate=None if pd.isna(row["approval_rate"]) else round(row["approval_rate"], 4),
            expected_annual_profit=round(float(row["expected_annual_profit"]) * payload.avg_loan_amnt, 2),
        )
        for row in base_curve.to_dict("records")
    ]
    delta_approval_pp = None
    if current["approval_rate"] is not None and optimal["approval_rate"] is not None:
        delta_approval_pp = round((optimal["approval_rate"] - current["approval_rate"]) * 100, 2)

    logger.info("profit cutoff simulation: model_version=%s current=%.1f optimal=%.1f",
                STORE.model_version(payload.model), current_snapped, optimal_cutoff)
    return schemas.ProfitCutoffResponse(
        current_cutoff=round(current_snapped, 2),
        optimal_cutoff=round(optimal_cutoff, 2),
        current=schemas.ProfitPoint(**current),
        optimal=schemas.ProfitPoint(**optimal),
        delta=schemas.ProfitDelta(
            approval_rate_pp=delta_approval_pp if delta_approval_pp is not None else 0.0,
            annual_profit_krw=round(optimal["expected_annual_profit"] - current["expected_annual_profit"], 2),
        ),
        curve=curve,
        assumptions=[
            "연간 볼륨은 OOT 검증 표본(2015 빈티지) 규모를 그대로 1년치 승인 볼륨으로 가정한다(별도 확대 계수 없음).",
            "평균 대출금액은 요청 파라미터(avg_loan_amnt)로 스케일링하며, 실제 승인 건별 대출금액 분포는 반영하지 않는다.",
            "회수율(recoveries)·상환액(total_pymnt)은 검증 표본의 실측치를 그대로 사용하며, 향후 금리·매크로 환경 변화는 반영하지 않는다.",
            "이 값은 손익 시뮬레이션이며 실제 재무 데이터가 아니다.",
        ],
    )
