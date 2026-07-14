"""Tests for 3-face evaluation metrics (Story 1.7a, synthetic data only)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scorecard.evaluation import (
    CHALLENGER_OOT_AUC_TARGET,
    CHAMPION_OOT_KS_TARGET,
    compute_metrics,
    evaluation_table,
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
