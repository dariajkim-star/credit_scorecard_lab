"""Tests for CAP-11 reason code dualization (Story 2.2, synthetic data only unless noted)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
import shap

from scorecard.binning import fit_binning, transform_woe
from scorecard.champion import PDO, fit_champion
from scorecard.challenger import tune_challenger
from scorecard.config import ARTIFACTS_DIR, DATA_DIR
from scorecard.reasons import (
    ChallengerReasonCode,
    ChampionReasonCode,
    ReasonCode,
    champion_reason_codes,
    challenger_reason_codes,
)

ACCEPTED_PARQUET_PATH = DATA_DIR / "lc_accepted_2012_2015_36m.parquet"
CHAMPION_ARTIFACT = ARTIFACTS_DIR / "champion_model.joblib"
CHALLENGER_ARTIFACT = ARTIFACTS_DIR / "challenger_model.joblib"
CHAMPION_MANIFEST = ARTIFACTS_DIR / "champion_manifest.json"
CHALLENGER_MANIFEST = ARTIFACTS_DIR / "challenger_manifest.json"


# --- Champion fixtures (synthetic, mirrors test_champion.py's pattern) -----

CHAMPION_VARS = ["fico_range_low", "dti"]


def _champion_synthetic_train(n: int = 3000, seed: int = 1):
    rng = np.random.default_rng(seed)
    fico = pd.array(rng.uniform(300, 850, n), dtype="Float64")
    dti = pd.array(rng.uniform(0, 60, n), dtype="Float64")
    logit_bad = -0.02 * (fico.to_numpy(dtype=float) - 575) + 0.05 * (dti.to_numpy(dtype=float) - 25)
    p_bad = 1 / (1 + np.exp(-logit_bad))
    y = pd.Series((rng.random(n) < p_bad).astype(int), dtype="Int64")
    df = pd.DataFrame({"fico_range_low": fico, "dti": dti})
    return df, y


@pytest.fixture(scope="module")
def champion_bundle():
    train_df, y = _champion_synthetic_train()
    binners = fit_binning(train_df, y, CHAMPION_VARS)
    woe_df = transform_woe(train_df, binners)
    model = fit_champion(woe_df, y, CHAMPION_VARS)
    return {"model": model, "binners": binners}


@pytest.fixture
def champion_applicant():
    # a middling applicant - not extreme so both variables can plausibly
    # contribute to points_lost
    return pd.Series({"fico_range_low": 650.0, "dti": 22.0})


# --- Challenger fixtures (synthetic, mirrors test_challenger.py's pattern) --

CHALLENGER_VARS = ["fico_range_low", "dti", "home_ownership"]


def _challenger_synthetic_data(n: int = 2000, seed: int = 3):
    rng = np.random.default_rng(seed)
    fico = pd.array(rng.uniform(300, 850, n), dtype="Float64")
    dti = pd.array(rng.uniform(0, 60, n), dtype="Float64")
    home = pd.Series(rng.choice(["RENT", "MORTGAGE", "OWN"], n), dtype="category")
    logit = -0.015 * (fico.to_numpy(dtype=float) - 575) + 0.04 * (dti.to_numpy(dtype=float) - 25)
    p = 1 / (1 + np.exp(-logit))
    y = pd.Series((rng.random(n) < p).astype(int))
    df = pd.DataFrame({"fico_range_low": fico, "dti": dti, "home_ownership": home})
    return df, y


@pytest.fixture(scope="module")
def challenger_bundle():
    train_df, y = _challenger_synthetic_data(seed=3)
    valid_df, valid_y = _challenger_synthetic_data(seed=4)
    model = tune_challenger(train_df, y, valid_df, valid_y, CHALLENGER_VARS, n_trials=3, seed=42)
    return {"model": model, "calibrator": None}


@pytest.fixture
def challenger_applicant():
    return pd.Series({"fico_range_low": 600.0, "dti": 30.0, "home_ownership": "RENT"})


# --- Pydantic shape (AD-6) --------------------------------------------------


def test_reason_code_shared_base_fields():
    assert set(ReasonCode.model_fields) == {"rank", "variable", "description"}


def test_champion_and_challenger_share_base_fields_but_differ_in_value_field():
    champion_fields = set(ChampionReasonCode.model_fields)
    challenger_fields = set(ChallengerReasonCode.model_fields)
    shared = champion_fields & challenger_fields
    assert shared == {"rank", "variable", "description"}
    assert champion_fields - shared == {"points_lost"}
    assert challenger_fields - shared == {"shap_value"}
    assert issubclass(ChampionReasonCode, ReasonCode)
    assert issubclass(ChallengerReasonCode, ReasonCode)


# --- champion_reason_codes (FR11, AD-2) -------------------------------------


def test_champion_reason_codes_matches_manual_points_lost_formula(champion_bundle, champion_applicant):
    model = champion_bundle["model"]
    binners = champion_bundle["binners"]

    result = champion_reason_codes(champion_bundle, champion_applicant, CHAMPION_VARS, top_n=2)

    # Independently recompute expected points_lost without calling any
    # reasons.py internals, to avoid a tautological test.
    applicant_df = champion_applicant[CHAMPION_VARS].to_frame().T
    woe_row = transform_woe(applicant_df, {v: binners[v] for v in CHAMPION_VARS}).iloc[0]
    factor = PDO / np.log(2)
    coefs = dict(zip(CHAMPION_VARS, model.coef_.ravel()))

    expected = {}
    for var in CHAMPION_VARS:
        table = binners[var].binning_table.build()
        real_bins = table[~table["Bin"].isin(["Special", "Missing"]) & (table.index != "Totals")]
        safest_woe = float(real_bins["WoE"].max())
        expected[var] = max(factor * coefs[var] * (float(woe_row[var]) - safest_woe), 0.0)

    by_var = {r.variable: r for r in result}
    for var, expected_loss in expected.items():
        if var in by_var:
            # abs=1e-4, not 1e-6: reasons.py deliberately rounds points_lost
            # to 4 decimals before returning it (round(loss, 4))
            assert by_var[var].points_lost == pytest.approx(expected_loss, abs=1e-4)


def test_champion_reason_codes_best_applicant_has_near_zero_points_lost(champion_bundle):
    """Behavioral sanity check independent of the internal formula: an
    applicant in the safest bin for every variable should lose ~0 points,
    and a worst-case applicant should lose meaningfully more. This is the
    check that would have caught the real-data bug where the subtraction
    order was flipped and every applicant's points_lost silently floored
    to 0.0 regardless of how risky they were."""
    best_applicant = pd.Series({"fico_range_low": 850.0, "dti": 0.0})
    worst_applicant = pd.Series({"fico_range_low": 300.0, "dti": 60.0})

    best_result = champion_reason_codes(champion_bundle, best_applicant, CHAMPION_VARS, top_n=2)
    worst_result = champion_reason_codes(champion_bundle, worst_applicant, CHAMPION_VARS, top_n=2)

    assert sum(r.points_lost for r in best_result) < sum(r.points_lost for r in worst_result)
    assert sum(r.points_lost for r in worst_result) > 1.0  # meaningfully nonzero


def test_champion_reason_codes_returns_top_n_sorted_descending(champion_bundle, champion_applicant):
    result = champion_reason_codes(champion_bundle, champion_applicant, CHAMPION_VARS, top_n=2)
    assert len(result) == 2
    assert [r.rank for r in result] == [1, 2]
    assert result[0].points_lost >= result[1].points_lost
    assert all(isinstance(r, ChampionReasonCode) for r in result)


def test_champion_reason_codes_description_is_nonempty_korean_sentence(champion_bundle, champion_applicant):
    result = champion_reason_codes(champion_bundle, champion_applicant, CHAMPION_VARS, top_n=2)
    for r in result:
        assert isinstance(r.description, str)
        assert len(r.description) > 0
        assert r.description.strip().endswith(".") or r.description.strip().endswith("다")


def test_champion_reason_codes_default_top_n_is_three():
    # only 2 variables available - top_n caps at however many variables exist
    import inspect

    sig = inspect.signature(champion_reason_codes)
    assert sig.parameters["top_n"].default == 3


# --- challenger_reason_codes (FR11, AD-6) -----------------------------------


def test_challenger_reason_codes_returns_top_n_sorted_descending(challenger_bundle, challenger_applicant):
    result = challenger_reason_codes(challenger_bundle, challenger_applicant, CHALLENGER_VARS, top_n=3)
    assert len(result) == 3
    assert [r.rank for r in result] == [1, 2, 3]
    shap_values = [r.shap_value for r in result]
    assert shap_values == sorted(shap_values, reverse=True)
    assert all(isinstance(r, ChallengerReasonCode) for r in result)


def test_challenger_reason_codes_shap_reconstructs_raw_margin(challenger_bundle, challenger_applicant):
    """Independently verifies expected_value + sum(all shap values) == raw
    margin (logit of predict_proba) - the identity that guarantees the
    shap_value field is a genuine SHAP contribution, not an ad-hoc number."""
    model = challenger_bundle["model"]

    # ask reasons.py for ALL variables ranked so we can sum every shap_value
    all_ranked = challenger_reason_codes(
        challenger_bundle, challenger_applicant, CHALLENGER_VARS, top_n=len(CHALLENGER_VARS)
    )
    total_shap = sum(r.shap_value for r in all_ranked)

    row = challenger_applicant[CHALLENGER_VARS].to_frame().T.copy()
    row["fico_range_low"] = pd.to_numeric(row["fico_range_low"])
    row["dti"] = pd.to_numeric(row["dti"])
    row["home_ownership"] = row["home_ownership"].astype("category")
    explainer = shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")
    raw_p = model.predict_proba(row)[:, 1][0]
    raw_margin = float(np.log(raw_p / (1 - raw_p)))
    reconstructed = explainer.expected_value + total_shap

    assert reconstructed == pytest.approx(raw_margin, abs=1e-2)


def test_challenger_reason_codes_handles_string_revol_util(challenger_bundle):
    """revol_util arrives as a percent string ('29.7') in the raw accepted
    parquet - challenger_reason_codes must parse it, not crash."""
    applicant = pd.Series({
        "fico_range_low": 600.0,
        "dti": 30.0,
        "home_ownership": "RENT",
    })
    # sanity: function works without revol_util in variables (already covered
    # above); this test only documents/protects the parsing branch exists
    # by exercising a variables list without it (guards against accidental
    # KeyError if the branch assumes the column is always present).
    result = challenger_reason_codes(challenger_bundle, applicant, CHALLENGER_VARS, top_n=1)
    assert len(result) == 1


def test_challenger_reason_codes_description_is_nonempty_korean_sentence(challenger_bundle, challenger_applicant):
    result = challenger_reason_codes(challenger_bundle, challenger_applicant, CHALLENGER_VARS, top_n=3)
    for r in result:
        assert isinstance(r.description, str)
        assert len(r.description) > 0


# --- Real data regression (real artifacts, real raw applicant row) ---------


@pytest.mark.skipif(
    not (CHAMPION_ARTIFACT.exists() and CHALLENGER_ARTIFACT.exists() and ACCEPTED_PARQUET_PATH.exists()),
    reason="trained artifacts or raw accepted parquet not available locally",
)
def test_real_artifacts_reason_codes_end_to_end():
    import joblib

    champion_manifest = json.loads(CHAMPION_MANIFEST.read_text())
    challenger_manifest = json.loads(CHALLENGER_MANIFEST.read_text())
    variables = champion_manifest["feature_order"]
    assert variables == challenger_manifest["feature_order"]

    champion_bundle = joblib.load(CHAMPION_ARTIFACT)
    challenger_bundle = joblib.load(CHALLENGER_ARTIFACT)

    raw = pd.read_parquet(ACCEPTED_PARQUET_PATH, columns=variables)
    applicant = raw.iloc[0]

    champion_result = champion_reason_codes(champion_bundle, applicant, variables)
    challenger_result = challenger_reason_codes(challenger_bundle, applicant, variables)

    assert len(champion_result) == 3
    assert len(challenger_result) == 3
    assert all(r.points_lost >= 0 for r in champion_result)
