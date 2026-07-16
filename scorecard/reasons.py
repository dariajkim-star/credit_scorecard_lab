"""CAP-11 reason code dualization: champion points-lost vs challenger SHAP (FR11).

Both entry points take an already-loaded artifact bundle (same convention as
scorecard/evaluation.py's champion_p_bad/challenger_p_bad) - joblib.load()
happens in the caller, never inside this module. WOE transformation reuses
scorecard.binning.transform_woe exclusively (AD-2); no WOE logic is
re-derived here. Reason code shapes share a common pydantic base
(rank, variable, description) and differ only in their value field
(points_lost vs shap_value), per AD-6.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

from scorecard.binning import transform_woe
from scorecard.champion import PDO
from scorecard.preprocessing import CATEGORICAL_COLUMNS, parse_percent

# Business-readable Korean labels for the 7 known feature_order variables.
# Falls back to the raw variable name for anything not listed here.
KOREAN_LABELS: dict[str, str] = {
    "fico_range_low": "신용점수(FICO)",
    "annual_inc": "연소득",
    "dti": "부채비율(DTI)",
    "home_ownership": "주택소유형태",
    "revol_util": "리볼빙 한도 소진율",
    "inq_last_6mths": "최근 6개월 신용조회 건수",
    "purpose": "대출목적",
}


class ReasonCode(BaseModel):
    rank: int
    variable: str
    description: str


class ChampionReasonCode(ReasonCode):
    points_lost: float


class ChallengerReasonCode(ReasonCode):
    shap_value: float


def _korean_label(variable: str) -> str:
    return KOREAN_LABELS.get(variable, variable)


def _normalize_raw_applicant(applicant_row: pd.Series, variables: list[str]) -> pd.DataFrame:
    """Raw applicant Series -> a 1-row DataFrame with per-column dtypes restored.

    A pd.Series assembled from mixed numeric/string values (a hand-built
    applicant dict, or df.iloc[0] on a row spanning numeric + categorical
    columns) collapses to a single object dtype for every field once
    transposed - both the champion (transform_woe) and challenger
    (LightGBM) paths need real per-column dtypes, not object. revol_util
    additionally arrives as a percent string ("29.7", no "%") in the raw
    accepted parquet and must be parsed via
    scorecard.preprocessing.parse_percent (reused, not re-derived,
    idempotent on already-numeric input) - this applies to BOTH models,
    since the champion binner was fit on parsed revol_util (Story 1.3), not
    the raw percent string (verified empirically: transform_woe on an
    unparsed applicant row raises TypeError comparing str against the
    binner's float split points).
    """
    row = applicant_row[variables].to_frame().T.copy()
    if "revol_util" in row.columns:
        row["revol_util"] = parse_percent(row["revol_util"]).astype(float)
    for col in variables:
        if col not in CATEGORICAL_COLUMNS and col != "revol_util":
            row[col] = pd.to_numeric(row[col])
    return row


def _safest_woe(binner) -> float:
    """WoE of the safest real bin (excludes Special/Missing/Totals rows).

    Verified empirically against a real fitted binner (Story 2.2 context):
    binning_table.build() columns include "Bin" (row labels, with
    "Special"/"Missing" among them) and "WoE" (exact casing), plus a
    "Totals" index row - all three must be excluded before taking max().
    """
    table = binner.binning_table.build()
    real_bins = table[~table["Bin"].isin(["Special", "Missing"]) & (table.index != "Totals")]
    return float(real_bins["WoE"].max())


def champion_reason_codes(
    champion_bundle: dict,
    applicant_row: pd.Series,
    variables: list[str],
    top_n: int = 3,
) -> list[ChampionReasonCode]:
    """Top-``top_n`` champion reason codes by points lost (FR11, AD-2).

    A variable's score CONTRIBUTION is -factor * coef_i * woe_i (score =
    offset - factor * logit_bad = offset - factor * sum(coef_i * woe_i),
    from champion.score_formula). points_lost for variable i = best
    possible contribution minus actual contribution =
    factor * coef_i * (woe_i - safest_woe_i), where factor = PDO / ln(2)
    (Story 1.5's Siddiqi scaling). Every champion coefficient is verified
    negative (Story 1.5's check_coefficient_signs, re-confirmed on the real
    artifact for Story 2.2), so points_lost is always >= 0 in practice
    (coef_i negative times (woe_i - safest_woe_i) <= 0 is >= 0); clipped at
    0 as a defensive floor regardless. Real-data run caught an earlier
    version with the subtraction order flipped, which silently zeroed out
    every applicant's points_lost (see reason-codes-report-2-2.md).
    """
    model = champion_bundle["model"]
    binners = champion_bundle["binners"]

    applicant_df = _normalize_raw_applicant(applicant_row, variables)
    woe_row = transform_woe(applicant_df, {v: binners[v] for v in variables}).iloc[0]

    factor = PDO / np.log(2)
    coefs = dict(zip(variables, model.coef_.ravel()))

    losses: dict[str, float] = {}
    for var in variables:
        safest_woe = _safest_woe(binners[var])
        applicant_woe = float(woe_row[var])
        points_lost = factor * coefs[var] * (applicant_woe - safest_woe)
        # max(..., 0.0) can still yield IEEE754 negative zero (e.g. a
        # negative factor times an exact-zero WOE gap) - normalize so the
        # rendered description never reads "-0.0점 하락".
        losses[var] = max(points_lost, 0.0) + 0.0

    ranked = sorted(losses.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [
        ChampionReasonCode(
            rank=i + 1,
            variable=var,
            points_lost=round(loss, 4),
            description=(
                f"{_korean_label(var)}이(가) 심사 기준 대비 불리하여 점수가 {loss:.1f}점 하락했습니다."
            ),
        )
        for i, (var, loss) in enumerate(ranked)
    ]


def _prepare_challenger_row(applicant_row: pd.Series, variables: list[str]) -> pd.DataFrame:
    """Raw applicant -> the dtypes the challenger model was trained on.

    Builds on _normalize_raw_applicant, additionally casting the
    categorical columns to pandas "category" dtype - LightGBM raises
    "pandas dtypes must be int, float or bool" without it (verified
    empirically, Story 2.2 spike).
    """
    row = _normalize_raw_applicant(applicant_row, variables)
    for col in variables:
        if col in CATEGORICAL_COLUMNS:
            row[col] = row[col].astype("category")
    return row


def challenger_reason_codes(
    challenger_bundle: dict,
    applicant_row: pd.Series,
    variables: list[str],
    top_n: int = 3,
) -> list[ChallengerReasonCode]:
    """Top-``top_n`` challenger reason codes by SHAP value (FR11, AD-6).

    Uses shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")
    - verified empirically (Story 2.2 spike): passing the manifest's
    shap_background_sample_ref as interventional background data raises
    ExplainerError, because LightGBM trained native categorical splits on
    home_ownership/purpose, which interventional SHAP cannot handle.
    tree_path_dependent needs no background data and was confirmed to
    reconstruct the raw model margin exactly
    (expected_value + sum(shap_values) == logit(raw predict_proba)).
    Explains the RAW (uncalibrated) LightGBM output, never the calibrator -
    calibration has no per-feature attribution.
    """
    import shap

    model = challenger_bundle["model"]
    row = _prepare_challenger_row(applicant_row, variables)

    explainer = shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")
    sv = explainer.shap_values(row)
    if isinstance(sv, list):
        sv = sv[-1]
    sv = np.asarray(sv)[0]

    shap_by_var = dict(zip(variables, sv))
    ranked = sorted(shap_by_var.items(), key=lambda kv: kv[1], reverse=True)[:top_n]

    return [
        ChallengerReasonCode(
            rank=i + 1,
            variable=var,
            shap_value=round(float(value), 4),
            description=f"{_korean_label(var)}이(가) 부도 위험을 높이는 방향으로 작용했습니다.",
        )
        for i, (var, value) in enumerate(ranked)
    ]
