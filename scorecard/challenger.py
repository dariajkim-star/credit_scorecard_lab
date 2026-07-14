"""CAP-5 LightGBM 챌린저 + Optuna 튜닝 + calibration.

Input contract: the raw (post-1.3, NOT WOE-transformed) train/valid frames
from scorecard.sample_design/preprocessing, and the final variable list from
scorecard.binning.select_variables (reused as-is, but fed as raw values -
LightGBM does not need WOE). No WOE re-derivation happens here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

from scorecard.config import RANDOM_SEED

MODEL_TYPE: str = "challenger"
MODEL_VERSION: str = "challenger-1.0.0"

# Not specified in SPEC/epics - story-owner decision (documented in
# challenger-report-1-6.md): keep the search small so dev iteration stays
# fast even against the real ~144k-row train split.
N_TRIALS: int = 20


def _to_matrix(df: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    """Select the variable columns, preserving dtype (nullable/category ok - verified pre-story)."""
    return df[variables]


def tune_challenger(
    train_df: pd.DataFrame,
    y_train: pd.Series,
    valid_df: pd.DataFrame,
    y_valid: pd.Series,
    variables: list[str],
    n_trials: int = N_TRIALS,
    seed: int = RANDOM_SEED,
) -> lgb.LGBMClassifier:
    """Optuna-tuned LightGBM, fit on train, selected by valid logloss.

    LightGBM's sklearn API accepts nullable Float64/Int64 and pandas
    category dtype directly (verified empirically before this story) - no
    dtype adapter needed.
    """
    X_train, X_valid = _to_matrix(train_df, variables), _to_matrix(valid_df, variables)
    y_train_arr = y_train.to_numpy(dtype=int)
    y_valid_arr = y_valid.to_numpy(dtype=int)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "num_leaves": trial.suggest_int("num_leaves", 7, 63),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
        }
        clf = lgb.LGBMClassifier(random_state=seed, verbosity=-1, **params)
        clf.fit(X_train, y_train_arr)
        p_valid = clf.predict_proba(X_valid)[:, 1]
        return log_loss(y_valid_arr, p_valid)

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_model = lgb.LGBMClassifier(random_state=seed, verbosity=-1, **study.best_params)
    best_model.fit(X_train, y_train_arr)
    return best_model


def fit_calibrator(
    model: lgb.LGBMClassifier,
    valid_df: pd.DataFrame,
    y_valid: pd.Series,
    variables: list[str],
    method: str = "isotonic",
):
    """Fit a calibration mapping on VALID predictions vs actual labels.

    ``method="isotonic"`` (default) or ``"sigmoid"`` (Platt, via a 1-feature
    LogisticRegression on the raw probability - simpler than
    CalibratedClassifierCV(cv="prefit") which is deprecated in recent
    sklearn).
    """
    raw_p = model.predict_proba(_to_matrix(valid_df, variables))[:, 1]
    y_arr = y_valid.to_numpy(dtype=int)

    if method == "isotonic":
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(raw_p, y_arr)
    elif method == "sigmoid":
        calibrator = LogisticRegression()
        calibrator.fit(raw_p.reshape(-1, 1), y_arr)
    else:
        raise ValueError(f"unknown calibration method: {method!r}")
    return calibrator


def calibrated_predict_proba(
    model: lgb.LGBMClassifier, calibrator, df: pd.DataFrame, variables: list[str]
) -> np.ndarray:
    """Raw LightGBM probability -> calibrated probability."""
    raw_p = model.predict_proba(_to_matrix(df, variables))[:, 1]
    if isinstance(calibrator, IsotonicRegression):
        return calibrator.predict(raw_p)
    return calibrator.predict_proba(raw_p.reshape(-1, 1))[:, 1]


def brier_scores(
    model: lgb.LGBMClassifier, calibrator, df: pd.DataFrame, variables: list[str], y: pd.Series
) -> dict[str, float]:
    """Brier score before (raw) vs after (calibrated) - AC1 evidence."""
    y_arr = y.to_numpy(dtype=int)
    raw_p = model.predict_proba(_to_matrix(df, variables))[:, 1]
    calibrated_p = calibrated_predict_proba(model, calibrator, df, variables)
    return {
        "before": float(brier_score_loss(y_arr, raw_p)),
        "after": float(brier_score_loss(y_arr, calibrated_p)),
    }


def calibration_curve_data(
    model: lgb.LGBMClassifier, calibrator, df: pd.DataFrame, variables: list[str], y: pd.Series, n_bins: int = 10
) -> pd.DataFrame:
    """Before/after reliability-curve points (mean predicted vs observed)."""
    y_arr = y.to_numpy(dtype=int)
    raw_p = model.predict_proba(_to_matrix(df, variables))[:, 1]
    calibrated_p = calibrated_predict_proba(model, calibrator, df, variables)

    obs_before, pred_before = calibration_curve(y_arr, raw_p, n_bins=n_bins, strategy="quantile")
    obs_after, pred_after = calibration_curve(y_arr, calibrated_p, n_bins=n_bins, strategy="quantile")

    return pd.DataFrame(
        {
            "mean_predicted_before": pred_before,
            "observed_before": obs_before,
        }
    ).merge(
        pd.DataFrame({"mean_predicted_after": pred_after, "observed_after": obs_after}),
        left_index=True,
        right_index=True,
        how="outer",
    )


def save_shap_background_sample(
    train_df: pd.DataFrame, variables: list[str], out_path: Path, n: int = 100, seed: int = RANDOM_SEED
) -> Path:
    """Persist a fixed, deterministic background sample for SHAP (Story 2.2).

    Saved once here so serving never recomputes/reselects it per request.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = min(n, len(train_df))
    sample = train_df[variables].sample(n=n, random_state=seed).reset_index(drop=True)
    sample.to_parquet(out_path)
    return out_path


def save_challenger_artifact(
    model: lgb.LGBMClassifier,
    calibrator,
    variables: list[str],
    shap_background_path: Path,
    out_dir: Path,
    calibration_method: str = "isotonic",
) -> Path:
    """Save the joblib bundle {"model", "calibrator"} + manifest.json (AD-1).

    Mirrors Story 1.5's fix: the artifact must contain everything serving
    needs (AD-4 forbids refitting at serve time), so calibrator ships with
    the model rather than only the raw LightGBM classifier.

    ``grade_thresholds`` is omitted for the same reason as the champion
    manifest - CAP-7 (Story 1.7) hasn't produced it yet.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = out_dir / "challenger_model.joblib"
    joblib.dump({"model": model, "calibrator": calibrator}, model_path)

    shap_background_path = Path(shap_background_path)
    shap_ref = str(shap_background_path.relative_to(out_dir)) if shap_background_path.is_relative_to(out_dir) else str(shap_background_path)

    manifest = {
        "model_type": MODEL_TYPE,
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_order": variables,
        "calibration_method": calibration_method,
        "shap_background_sample_ref": shap_ref,
    }
    manifest_path = out_dir / "challenger_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="ascii")

    return model_path
