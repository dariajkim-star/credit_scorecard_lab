"""CAP-4 로지스틱 스코어카드(챔피언): WOE 변수 fit, PDO 스코어 변환, 아티팩트 저장.

Input contract: the WOE-transformed frame from ``scorecard.binning.transform_woe``
and the final variable list from ``scorecard.binning.select_variables``. This
module does not re-derive WOE (AD-2) - it only fits a logistic regression on
already-transformed values and converts the raw decision function into a
Siddiqi-style credit score.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

# Scorecard scaling constants (FR4).
PDO: float = 20.0
BASE_SCORE: float = 600.0
# Base odds (good:bad) at BASE_SCORE - not specified anywhere in SPEC/epics;
# 50 is a common industry default. See champion-scorecard-report-1-5.md for
# the rationale (story-owner decision, same pattern as prior stories').
BASE_ODDS: float = 50.0

MODEL_TYPE: str = "champion"
MODEL_VERSION: str = "champion-1.0.0"


def fit_champion(train_woe_df: pd.DataFrame, y: pd.Series, variables: list[str]) -> LogisticRegression:
    """Fit a logistic regression on TRAIN-split WOE values only.

    ``y`` must have no missing labels (mirrors the guard in
    ``scorecard.binning.fit_binning``).
    """
    y_arr = pd.Series(y).astype("Int64").to_numpy(dtype=int, na_value=-1)
    if (y_arr == -1).any():
        raise ValueError("y contains missing values - label rows before fitting the champion model")

    X = train_woe_df[variables].astype(float).to_numpy()
    model = LogisticRegression(random_state=0)
    model.fit(X, y_arr)
    return model


def check_coefficient_signs(model: LogisticRegression, variables: list[str]) -> pd.DataFrame:
    """Coefficient table with a sign-reversal flag.

    optbinning's WOE convention (verified empirically before this story): a
    higher WOE means a safer bin. Fit against y=bad_flag, a correctly signed
    coefficient must be negative (WOE up -> logit(bad) down). Any positive
    coefficient is a reversal and is flagged here; it does not raise -
    callers (the report generation step) make the final pass/fail call.
    """
    coefs = model.coef_.ravel()
    return pd.DataFrame(
        {
            "variable": variables,
            "coefficient": coefs,
            "sign_ok": coefs < 0,
        }
    )


def score_formula(
    logit_bad: np.ndarray | float,
    pdo: float = PDO,
    base_score: float = BASE_SCORE,
    base_odds: float = BASE_ODDS,
) -> np.ndarray | float:
    """Siddiqi-style scaling: WOE-based logit -> credit score.

    ``logit_bad`` is the model's raw decision function output
    (intercept + sum(coef_i * woe_i)), NOT predict_proba.
    """
    factor = pdo / np.log(2)
    offset = base_score - factor * np.log(base_odds)
    arr = np.asarray(logit_bad, dtype=float)
    log_odds_good = -arr
    score = offset + factor * log_odds_good
    return float(score) if arr.ndim == 0 else score


def score_applicant(model: LogisticRegression, woe_row: pd.Series, variables: list[str]) -> float:
    """End-to-end: one applicant's WOE-transformed row -> credit score (AC 1)."""
    x = woe_row[variables].astype(float).to_numpy().reshape(1, -1)
    logit_bad = model.decision_function(x)[0]
    return score_formula(logit_bad)


def save_champion_artifact(
    model: LogisticRegression,
    binners: dict,
    variables: list[str],
    out_dir: Path,
) -> Path:
    """Save the joblib model bundle + manifest.json (AD-1).

    The bundle includes the fitted binners (not just the logistic model) -
    serving (Story 2.3) needs them to WOE-transform a raw applicant before
    scoring; AD-4 forbids retraining at serve time, so they must ship in the
    artifact rather than be refit.

    ``grade_thresholds`` is an AD-1 common key but is produced by CAP-7
    (Story 1.7, not yet built) - it is intentionally omitted here and left
    for Story 1.7 to add when it finalizes this manifest.
    """
    from scorecard.binning import bin_edges

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = out_dir / "champion_model.joblib"
    joblib.dump({"model": model, "binners": {var: binners[var] for var in variables}}, model_path)

    all_edges = bin_edges(binners)
    woe_bin_edges = {var: all_edges[var] for var in variables}

    manifest = {
        "model_type": MODEL_TYPE,
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_order": variables,
        "pdo": PDO,
        "base_score": BASE_SCORE,
        "base_odds": BASE_ODDS,
        "woe_bin_edges": woe_bin_edges,
    }
    manifest_path = out_dir / "champion_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="ascii")

    return model_path
