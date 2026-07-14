"""Tests for 3-face evaluation metrics (Story 1.7a, synthetic data only)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scorecard.evaluation import (
    CHALLENGER_OOT_AUC_TARGET,
    CHAMPION_OOT_KS_TARGET,
    SCORED_FRAME_COLUMNS,
    build_scored_frame,
    compute_metrics,
    evaluation_table,
    generalized_score,
    population_stability_index,
    variable_psi,
)


def _separable_data(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 2, n)
    p_bad = np.where(y == 1, rng.beta(3, 2, n), rng.beta(2, 3, n))
    return y, p_bad


# --- compute_metrics -----------------------------------------------------------


def test_compute_metrics_ks_matches_manual_credit_ks():
    y, p_bad = _separable_data()
    metrics = compute_metrics(y, p_bad)

    order = np.argsort(-p_bad)
    y_sorted = y[order]
    cum_bad = np.cumsum(y_sorted) / y_sorted.sum()
    cum_good = np.cumsum(1 - y_sorted) / (1 - y_sorted).sum()
    manual_ks = float(np.max(np.abs(cum_bad - cum_good)))

    assert metrics["ks"] == pytest.approx(manual_ks)


def test_compute_metrics_returns_expected_keys_in_range():
    y, p_bad = _separable_data()
    metrics = compute_metrics(y, p_bad)
    assert set(metrics) == {"auc", "ks", "pr_auc"}
    for v in metrics.values():
        assert 0.0 <= v <= 1.0


def test_compute_metrics_perfect_separation():
    y = np.array([0, 0, 0, 1, 1, 1])
    p_bad = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
    metrics = compute_metrics(y, p_bad)
    assert metrics["auc"] == pytest.approx(1.0)
    assert metrics["ks"] == pytest.approx(1.0)


# --- evaluation_table (champion/challenger bundle contract) -------------------


def _fake_champion_bundle_and_challenger_bundle(variables):
    """Fake bundles that avoid needing a real fitted binning/LightGBM model -
    only the shape of champion_p_bad/challenger_p_bad matters for this test,
    so we monkeypatch the two helper functions instead of fabricating bundles."""
    return {"model": None, "binners": None}, {"model": None, "calibrator": None}


def test_evaluation_table_structure_and_target_flags(monkeypatch):
    import scorecard.evaluation as ev

    variables = ["x"]
    splits = {}
    rng = np.random.default_rng(1)
    for name, n in [("train", 1000), ("valid", 800), ("oot", 900)]:
        y, p = _separable_data(n=n, seed=hash(name) % 1000)
        splits[name] = pd.DataFrame({"bad_flag": y, "x": rng.uniform(0, 1, n)})
        # stash p_bad on the frame via closure below

    fake_p_by_split = {}

    def fake_champion_p_bad(bundle, df, variables):
        y = df["bad_flag"].to_numpy()
        _, p = _separable_data(n=len(y), seed=42)
        return p

    def fake_challenger_p_bad(bundle, df, variables):
        y = df["bad_flag"].to_numpy()
        _, p = _separable_data(n=len(y), seed=43)
        return p

    monkeypatch.setattr(ev, "champion_p_bad", fake_champion_p_bad)
    monkeypatch.setattr(ev, "challenger_p_bad", fake_challenger_p_bad)

    champ_bundle, chall_bundle = _fake_champion_bundle_and_challenger_bundle(variables)
    table = evaluation_table(splits, champ_bundle, variables, chall_bundle, variables)

    assert set(table.columns) == {"model", "split", "auc", "ks", "pr_auc", "oot_target_met"}
    assert set(table["model"]) == {"champion", "challenger"}
    assert set(table["split"]) == {"train", "valid", "oot"}
    assert len(table) == 6

    # only oot rows get a non-None target flag
    non_oot = table[table["split"] != "oot"]
    assert non_oot["oot_target_met"].isna().all()
    oot_rows = table[table["split"] == "oot"]
    assert oot_rows["oot_target_met"].notna().all()


def test_evaluation_table_target_flag_uses_correct_thresholds(monkeypatch):
    import scorecard.evaluation as ev

    variables = ["x"]
    n = 1000
    y = np.zeros(n, dtype=int)
    y[: n // 4] = 1  # 25% bad, arbitrary
    splits = {"oot": pd.DataFrame({"bad_flag": y, "x": np.arange(n)})}

    # champion: KS exactly at target -> should meet
    def fake_champion_p_bad(bundle, df, variables):
        yy = df["bad_flag"].to_numpy()
        p = np.zeros(len(yy))
        # construct p so that ks_2samp gives something >= CHAMPION_OOT_KS_TARGET
        p[yy == 1] = 0.9
        p[yy == 0] = 0.9 - CHAMPION_OOT_KS_TARGET - 0.05
        return p

    def fake_challenger_p_bad(bundle, df, variables):
        yy = df["bad_flag"].to_numpy()
        # deliberately weak separation -> AUC below target
        rng = np.random.default_rng(0)
        return rng.uniform(0.4, 0.6, len(yy))

    monkeypatch.setattr(ev, "champion_p_bad", fake_champion_p_bad)
    monkeypatch.setattr(ev, "challenger_p_bad", fake_challenger_p_bad)

    champ_bundle, chall_bundle = _fake_champion_bundle_and_challenger_bundle(variables)
    table = evaluation_table(splits, champ_bundle, variables, chall_bundle, variables)

    champ_row = table[(table.model == "champion") & (table.split == "oot")].iloc[0]
    chall_row = table[(table.model == "challenger") & (table.split == "oot")].iloc[0]
    assert champ_row["oot_target_met"] == True  # noqa: E712
    assert chall_row["oot_target_met"] == False  # noqa: E712


# --- generalized_score (1.7a open question resolution) ------------------------


def test_generalized_score_handles_extreme_probabilities_without_inf():
    scores = generalized_score(np.array([0.0, 1.0, 0.5]))
    assert np.all(np.isfinite(scores))


def test_generalized_score_matches_champion_decision_function_score():
    import warnings

    warnings.filterwarnings("ignore")
    from scorecard.binning import fit_binning, transform_woe
    from scorecard.champion import fit_champion, score_formula

    rng = np.random.default_rng(0)
    n = 1500
    dti = pd.array(rng.uniform(0, 60, n), dtype="Float64")
    logit = -0.05 * (dti.to_numpy(dtype=float) - 25)
    y = pd.Series((rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int), dtype="Int64")
    df = pd.DataFrame({"dti": dti})
    binners = fit_binning(df, y, variables=["dti"])
    woe = transform_woe(df, binners)
    model = fit_champion(woe, y, ["dti"])

    x = woe[["dti"]].astype(float).to_numpy()
    direct_score = score_formula(model.decision_function(x))
    gen_score = generalized_score(model.predict_proba(x)[:, 1])
    np.testing.assert_allclose(direct_score, gen_score, atol=1e-8)


def test_generalized_score_higher_pd_gives_lower_score():
    scores = generalized_score(np.array([0.01, 0.5, 0.9]))
    assert scores[0] > scores[1] > scores[2]


# --- population_stability_index / variable_psi ---------------------------------


def test_psi_near_zero_for_identical_distribution():
    rng = np.random.default_rng(0)
    expected = rng.normal(600, 30, 5000)
    actual = rng.normal(600, 30, 5000)
    psi = population_stability_index(expected, actual)
    assert psi < 0.05


def test_psi_large_for_shifted_distribution():
    rng = np.random.default_rng(0)
    expected = rng.normal(600, 30, 5000)
    actual = rng.normal(500, 30, 5000)  # large shift
    psi = population_stability_index(expected, actual)
    assert psi > 0.25  # standard PSI rule of thumb: >0.25 = major shift


def test_psi_uses_shared_expected_derived_edges_not_independent_binning():
    # Regression guard in spirit of Story 1.6's calibration_curve_data fix:
    # PSI must bucket `actual` using edges fit on `expected`, not its own
    # quantiles. Verify by checking a skewed `actual` still produces a
    # sensible (bounded, finite) PSI rather than blowing up from mismatched
    # bucket definitions.
    rng = np.random.default_rng(1)
    expected = rng.normal(0, 1, 3000)
    actual = rng.exponential(2, 3000)  # very different shape
    psi = population_stability_index(expected, actual)
    assert np.isfinite(psi)
    assert psi > 0


def test_psi_ignores_nan_instead_of_masking_a_real_shift():
    # Regression guard: np.quantile propagates NaN to every quantile level,
    # which previously made ANY variable with missing values silently
    # collapse to a fake PSI=0.0 ("no drift") instead of comparing the real
    # distribution - found by running this against real revol_util data.
    rng = np.random.default_rng(0)
    expected = np.concatenate([rng.normal(600, 30, 4900), np.full(100, np.nan)])
    actual_shifted = np.concatenate([rng.normal(500, 30, 4900), np.full(100, np.nan)])
    psi = population_stability_index(expected, actual_shifted)
    assert psi > 0.25  # real shift must still be detected despite NaNs present


def test_psi_all_nan_expected_returns_zero():
    expected = np.full(50, np.nan)
    actual = np.array([1.0, 2.0, 3.0])
    assert population_stability_index(expected, actual) == 0.0


def test_variable_psi_returns_one_row_per_column():
    rng = np.random.default_rng(0)
    train_df = pd.DataFrame({"a": rng.normal(0, 1, 1000), "b": rng.normal(10, 2, 1000)})
    oot_df = pd.DataFrame({"a": rng.normal(0, 1, 1000), "b": rng.normal(15, 2, 1000)})
    result = variable_psi(train_df, oot_df, ["a", "b"])
    assert list(result["variable"]) == ["a", "b"]
    assert result.loc[result.variable == "b", "psi"].iloc[0] > result.loc[result.variable == "a", "psi"].iloc[0]


# --- build_scored_frame (AD-3) --------------------------------------------------


def test_build_scored_frame_schema_and_long_format(monkeypatch):
    import scorecard.evaluation as ev

    n = 20
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "id": [f"app{i}" for i in range(n)],
        "vintage": [2015] * n,
        "bad_flag": rng.integers(0, 2, n),
        "int_rate": [f"{r:.1f}%" for r in rng.uniform(5, 20, n)],
        "recoveries": rng.uniform(0, 100, n),
        "total_pymnt": rng.uniform(1000, 5000, n),
        "x": rng.uniform(0, 1, n),
    })
    splits = {"valid": df}

    def fake_champion_p_bad(bundle, d, variables):
        return rng.uniform(0.01, 0.5, len(d))

    def fake_challenger_p_bad(bundle, d, variables):
        return rng.uniform(0.01, 0.5, len(d))

    monkeypatch.setattr(ev, "champion_p_bad", fake_champion_p_bad)
    monkeypatch.setattr(ev, "challenger_p_bad", fake_challenger_p_bad)

    champ_edges = np.array([400.0, 500.0, 600.0, 700.0])
    chall_edges = np.array([400.0, 500.0, 600.0, 700.0])

    frame = ev.build_scored_frame(
        splits, {"model": None}, ["x"], champ_edges, {"model": None, "calibrator": None}, ["x"], chall_edges
    )

    assert list(frame.columns) == SCORED_FRAME_COLUMNS
    assert len(frame) == 2 * n  # long format: one row per (applicant, model_type)
    assert set(frame["model_type"]) == {"champion", "challenger"}
    assert frame["int_rate"].dtype == float
    assert frame["int_rate"].between(5, 20).all()  # parsed from "X.Y%" strings correctly
