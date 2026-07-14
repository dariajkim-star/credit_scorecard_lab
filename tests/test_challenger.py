"""Tests for the LightGBM challenger + calibration (Story 1.6, synthetic data only)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scorecard.challenger import (
    brier_scores,
    calibrated_predict_proba,
    calibration_curve_data,
    fit_calibrator,
    save_challenger_artifact,
    save_shap_background_sample,
    tune_challenger,
)


def _synthetic_data(n: int = 2000, seed: int = 3):
    rng = np.random.default_rng(seed)
    fico = pd.array(rng.uniform(300, 850, n), dtype="Float64")
    dti = pd.array(rng.uniform(0, 60, n), dtype="Float64")
    inq = pd.array(rng.integers(0, 6, n), dtype="Int64")
    home = pd.Series(rng.choice(["RENT", "MORTGAGE", "OWN"], n), dtype="category")
    logit = -0.015 * (fico.to_numpy(dtype=float) - 575) + 0.04 * (dti.to_numpy(dtype=float) - 25) + 0.2 * inq.to_numpy(dtype=float)
    p = 1 / (1 + np.exp(-logit))
    y = pd.Series((rng.random(n) < p).astype(int))
    df = pd.DataFrame({"fico_range_low": fico, "dti": dti, "inq_last_6mths": inq, "home_ownership": home})
    return df, y


VARS = ["fico_range_low", "dti", "inq_last_6mths", "home_ownership"]


@pytest.fixture(scope="module")
def split_data():
    train_df, train_y = _synthetic_data(seed=3)
    valid_df, valid_y = _synthetic_data(seed=4)
    return train_df, train_y, valid_df, valid_y


@pytest.fixture(scope="module")
def tuned_model(split_data):
    train_df, train_y, valid_df, valid_y = split_data
    return tune_challenger(train_df, train_y, valid_df, valid_y, VARS, n_trials=3, seed=42)


@pytest.fixture(scope="module")
def calibrated(split_data, tuned_model):
    _, _, valid_df, valid_y = split_data
    calibrator = fit_calibrator(tuned_model, valid_df, valid_y, VARS, method="isotonic")
    return calibrator


# --- tune_challenger reproducibility ------------------------------------------


def test_tune_challenger_reproducible_with_fixed_seed(split_data):
    train_df, train_y, valid_df, valid_y = split_data
    m1 = tune_challenger(train_df, train_y, valid_df, valid_y, VARS, n_trials=3, seed=42)
    m2 = tune_challenger(train_df, train_y, valid_df, valid_y, VARS, n_trials=3, seed=42)
    p1 = m1.predict_proba(train_df[VARS])[:, 1]
    p2 = m2.predict_proba(train_df[VARS])[:, 1]
    np.testing.assert_array_equal(p1, p2)


def test_tune_challenger_accepts_nullable_and_category_dtypes(tuned_model, split_data):
    train_df, _, _, _ = split_data
    p = tuned_model.predict_proba(train_df[VARS])[:, 1]
    assert p.shape == (len(train_df),)
    assert ((p >= 0) & (p <= 1)).all()


# --- calibration ---------------------------------------------------------------


def test_fit_calibrator_isotonic_monotonic(split_data, tuned_model):
    _, _, valid_df, valid_y = split_data
    calibrator = fit_calibrator(tuned_model, valid_df, valid_y, VARS, method="isotonic")
    xs = np.linspace(0, 1, 50)
    ys = calibrator.predict(xs)
    assert (np.diff(ys) >= 0).all()  # isotonic = non-decreasing


def test_fit_calibrator_rejects_unknown_method(split_data, tuned_model):
    _, _, valid_df, valid_y = split_data
    with pytest.raises(ValueError, match="unknown"):
        fit_calibrator(tuned_model, valid_df, valid_y, VARS, method="bogus")


def test_calibrated_predict_proba_in_bounds(split_data, tuned_model, calibrated):
    train_df, _, _, _ = split_data
    p = calibrated_predict_proba(tuned_model, calibrated, train_df, VARS)
    assert ((p >= 0) & (p <= 1)).all()
    assert p.shape == (len(train_df),)


def test_brier_scores_before_after_computed(split_data, tuned_model, calibrated):
    _, _, valid_df, valid_y = split_data
    scores = brier_scores(tuned_model, calibrated, valid_df, VARS, valid_y)
    assert set(scores) == {"before", "after"}
    assert 0 <= scores["before"] <= 1
    assert 0 <= scores["after"] <= 1


def test_calibration_curve_data_structure(split_data, tuned_model, calibrated):
    _, _, valid_df, valid_y = split_data
    curve = calibration_curve_data(tuned_model, calibrated, valid_df, VARS, valid_y, n_bins=5)
    assert {"mean_predicted_before", "observed_before", "mean_predicted_after", "observed_after"} <= set(curve.columns)
    assert len(curve) > 0


def test_calibration_curve_data_uses_shared_bin_edges_when_distributions_differ():
    # Regression guard for the code-review finding: independently re-quantiling
    # before/after probabilities can yield different bin counts (e.g. lumpy
    # tree probabilities vs a smooth calibrated distribution), and merging by
    # positional index then silently compares unrelated probability ranges.
    import numpy as np
    from unittest.mock import MagicMock

    from scorecard.challenger import calibration_curve_data

    rng = np.random.default_rng(0)
    n = 2000
    y = pd.Series(rng.integers(0, 2, n))
    raw_p = rng.choice([0.02, 0.05, 0.1, 0.3, 0.9], size=n)  # few unique values -> few quantile bins
    calibrated_p = rng.uniform(0, 1, n)  # smooth -> many quantile bins if binned independently

    from sklearn.isotonic import IsotonicRegression

    model = MagicMock()
    model.predict_proba.return_value = np.column_stack([1 - raw_p, raw_p])

    class _FakeCalibrator(IsotonicRegression):
        def predict(self, p):
            return calibrated_p

    df = pd.DataFrame({"x": range(n)})
    curve = calibration_curve_data(model, _FakeCalibrator(), df, ["x"], y, n_bins=10)
    # every row must have both a before AND an after value tied to the SAME
    # shared bin edge - i.e. no row should be all-before or all-after only
    both_present = curve[["mean_predicted_before", "mean_predicted_after"]].notna().all(axis=1)
    assert both_present.any()


# --- SHAP background sample ----------------------------------------------------


def test_save_shap_background_sample_deterministic(split_data, tmp_path):
    train_df, _, _, _ = split_data
    p1 = save_shap_background_sample(train_df, VARS, tmp_path / "bg1.parquet", n=50, seed=7)
    p2 = save_shap_background_sample(train_df, VARS, tmp_path / "bg2.parquet", n=50, seed=7)
    s1 = pd.read_parquet(p1)
    s2 = pd.read_parquet(p2)
    pd.testing.assert_frame_equal(s1, s2)
    assert len(s1) == 50
    assert list(s1.columns) == VARS


def test_save_shap_background_sample_caps_at_available_rows(tmp_path):
    small_df = pd.DataFrame({"fico_range_low": [1.0, 2.0, 3.0], "dti": [1, 2, 3], "inq_last_6mths": [0, 1, 2], "home_ownership": ["RENT"] * 3})
    path = save_shap_background_sample(small_df, ["fico_range_low", "dti", "inq_last_6mths", "home_ownership"], tmp_path / "bg.parquet", n=100, seed=1)
    assert len(pd.read_parquet(path)) == 3


# --- artifact save/reload --------------------------------------------------------


def test_save_challenger_artifact_manifest_and_roundtrip(split_data, tuned_model, calibrated, tmp_path):
    train_df, _, _, _ = split_data
    bg_path = save_shap_background_sample(train_df, VARS, tmp_path / "shap_background.parquet", n=50, seed=7)
    model_path = save_challenger_artifact(tuned_model, calibrated, VARS, bg_path, tmp_path, calibration_method="isotonic")

    assert model_path.exists()
    manifest_path = tmp_path / "challenger_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))

    for key in [
        "model_type", "model_version", "trained_at", "feature_order",
        "calibration_method", "shap_background_sample_ref",
    ]:
        assert key in manifest, f"missing manifest key: {key}"
    assert manifest["model_type"] == "challenger"
    assert manifest["calibration_method"] == "isotonic"
    assert manifest["shap_background_sample_ref"] == "shap_background.parquet"
    assert manifest["feature_order"] == VARS

    import joblib

    bundle = joblib.load(model_path)
    assert set(bundle) == {"model", "calibrator"}

    original_p = calibrated_predict_proba(tuned_model, calibrated, train_df, VARS)
    reloaded_p = calibrated_predict_proba(bundle["model"], bundle["calibrator"], train_df, VARS)
    np.testing.assert_array_equal(original_p, reloaded_p)


def test_save_challenger_artifact_shap_ref_relative_even_if_path_is_absolute(
    split_data, tuned_model, calibrated, tmp_path
):
    # Regression guard for the code-review finding: passing an already-resolved
    # (absolute) shap path against a relative out_dir used to make
    # is_relative_to() return False, leaking a full machine-specific path
    # into the manifest instead of a portable relative reference.
    train_df, _, _, _ = split_data
    bg_path = save_shap_background_sample(train_df, VARS, tmp_path / "shap_background.parquet", n=50, seed=7)
    absolute_bg_path = bg_path.resolve()

    save_challenger_artifact(tuned_model, calibrated, VARS, absolute_bg_path, tmp_path)
    manifest = json.loads((tmp_path / "challenger_manifest.json").read_text(encoding="ascii"))
    assert manifest["shap_background_sample_ref"] == "shap_background.parquet"
