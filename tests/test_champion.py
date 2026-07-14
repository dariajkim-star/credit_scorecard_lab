"""Tests for the champion logistic scorecard (Story 1.5, synthetic data only)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scorecard.binning import fit_binning, transform_woe
from scorecard.champion import (
    BASE_ODDS,
    BASE_SCORE,
    PDO,
    check_coefficient_signs,
    fit_champion,
    save_champion_artifact,
    score_applicant,
    score_formula,
)


def _synthetic_train(n: int = 3000, seed: int = 1):
    """dti (higher -> more risk) and fico (higher -> less risk), both signal."""
    rng = np.random.default_rng(seed)
    fico = pd.array(rng.uniform(300, 850, n), dtype="Float64")
    dti = pd.array(rng.uniform(0, 60, n), dtype="Float64")
    logit_bad = -0.02 * (fico.to_numpy(dtype=float) - 575) + 0.05 * (dti.to_numpy(dtype=float) - 25)
    p_bad = 1 / (1 + np.exp(-logit_bad))
    y = pd.Series((rng.random(n) < p_bad).astype(int), dtype="Int64")
    df = pd.DataFrame({"fico_range_low": fico, "dti": dti})
    return df, y


VARS = ["fico_range_low", "dti"]


@pytest.fixture(scope="module")
def fitted_champion():
    df, y = _synthetic_train()
    binners = fit_binning(df, y, variables=VARS)
    woe = transform_woe(df, binners)
    model = fit_champion(woe, y, VARS)
    return df, y, binners, woe, model


# --- fit_champion / check_coefficient_signs -----------------------------------


def test_fit_champion_all_coefficients_negative(fitted_champion):
    _, _, _, _, model = fitted_champion
    assert model.coef_.shape == (1, len(VARS))
    assert (model.coef_.ravel() < 0).all()


def test_fit_champion_rejects_missing_labels(fitted_champion):
    df, y, _, woe, _ = fitted_champion
    y_bad = y.copy()
    y_bad.iloc[0] = pd.NA
    with pytest.raises(ValueError, match="missing"):
        fit_champion(woe, y_bad, VARS)


def test_check_coefficient_signs_flags_reversal(fitted_champion):
    _, _, _, _, model = fitted_champion
    tbl = check_coefficient_signs(model, VARS)
    assert set(tbl.columns) == {"variable", "coefficient", "sign_ok"}
    assert tbl["sign_ok"].all()  # both variables correctly signed (WOE convention)


def test_check_coefficient_signs_detects_positive_coefficient():
    # Fabricate a model-like stub with one reversed (positive) coefficient
    class _Stub:
        coef_ = np.array([[-1.5, 0.3]])

    tbl = check_coefficient_signs(_Stub(), ["a", "b"])
    assert tbl.loc[tbl["variable"] == "a", "sign_ok"].iloc[0]
    assert not tbl.loc[tbl["variable"] == "b", "sign_ok"].iloc[0]


# --- score_formula -------------------------------------------------------------


def test_score_formula_matches_hand_calculation():
    factor = PDO / np.log(2)
    offset = BASE_SCORE - factor * np.log(BASE_ODDS)
    logit_bad = 0.5
    expected = offset + factor * (-logit_bad)
    assert score_formula(logit_bad) == pytest.approx(expected)


def test_score_formula_zero_logit_equals_offset():
    factor = PDO / np.log(2)
    offset = BASE_SCORE - factor * np.log(BASE_ODDS)
    assert score_formula(0.0) == pytest.approx(offset)


def test_score_formula_higher_logit_bad_gives_lower_score():
    assert score_formula(1.0) < score_formula(0.0) < score_formula(-1.0)


def test_score_formula_vectorized_matches_scalar():
    logits = np.array([-1.0, 0.0, 1.0])
    vec = score_formula(logits)
    scalars = [score_formula(float(v)) for v in logits]
    np.testing.assert_allclose(vec, scalars)


# --- score_applicant (AC 1) ----------------------------------------------------


def test_score_applicant_end_to_end(fitted_champion):
    df, _, binners, woe, model = fitted_champion
    row = woe.iloc[0]
    score = score_applicant(model, row, VARS)
    assert isinstance(score, float)
    # sanity: manual recomputation matches
    x = row[VARS].astype(float).to_numpy().reshape(1, -1)
    logit_bad = model.decision_function(x)[0]
    assert score == pytest.approx(score_formula(logit_bad))


def test_score_applicant_safer_profile_scores_higher(fitted_champion):
    df, _, binners, woe, model = fitted_champion
    # pick the highest-fico, lowest-dti row vs the opposite
    safe_idx = (df["fico_range_low"].astype(float) - df["dti"].astype(float) * 3).idxmax()
    risky_idx = (df["fico_range_low"].astype(float) - df["dti"].astype(float) * 3).idxmin()
    safe_score = score_applicant(model, woe.loc[safe_idx], VARS)
    risky_score = score_applicant(model, woe.loc[risky_idx], VARS)
    assert safe_score > risky_score


# --- save_champion_artifact (AC 4 / AD-1) -------------------------------------


def test_save_champion_artifact_roundtrip_and_manifest(fitted_champion, tmp_path):
    df, _, binners, woe, model = fitted_champion
    model_path = save_champion_artifact(model, binners, VARS, tmp_path)

    assert model_path.exists()
    manifest_path = tmp_path / "champion_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))

    for key in ["model_type", "model_version", "trained_at", "feature_order", "pdo", "base_score", "woe_bin_edges"]:
        assert key in manifest, f"missing manifest key: {key}"
    assert manifest["model_type"] == "champion"
    assert manifest["feature_order"] == VARS
    assert manifest["pdo"] == PDO
    assert manifest["base_score"] == BASE_SCORE
    assert set(manifest["woe_bin_edges"]) == set(VARS)

    import joblib

    reloaded = joblib.load(model_path)
    row = woe.iloc[0]
    original_score = score_applicant(model, row, VARS)
    reloaded_score = score_applicant(reloaded, row, VARS)
    assert reloaded_score == pytest.approx(original_score)
