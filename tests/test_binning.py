"""Tests for WOE binning and variable selection (Story 1.4, synthetic data only)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scorecard.binning import (
    BINNING_CANDIDATES,
    BINNING_EXCLUDED_COLUMNS,
    bin_edges,
    fit_binning,
    iv_table,
    select_variables,
    transform_woe,
)
from scorecard.preprocessing import CATEGORICAL_COLUMNS, NUMERIC_COLUMNS


def _synthetic_train(n: int = 2000, seed: int = 42) -> tuple[pd.DataFrame, pd.Series]:
    """Two informative numerics (one a near-copy), one categorical, with missing."""
    rng = np.random.default_rng(seed)
    fico = pd.array(rng.uniform(300, 850, n), dtype="Float64")
    miss = rng.choice(n, 100, replace=False)
    fico[miss] = pd.NA
    fico_filled = pd.Series(fico).astype("float").fillna(575).to_numpy()
    home = pd.Series(rng.choice(["RENT", "MORTGAGE", "OWN"], n, p=[0.4, 0.5, 0.1]), dtype="string")
    # higher fico -> lower bad probability (monotone signal) + home effect so
    # home_ownership carries independent IV
    home_shift = home.map({"RENT": 0.15, "MORTGAGE": -0.10, "OWN": 0.0}).to_numpy(dtype=float)
    p_bad = 1 / (1 + np.exp((fico_filled - 575) / 60)) * (1 + home_shift) + home_shift * 0.1
    p_bad = np.clip(p_bad, 0.01, 0.99)
    y = pd.Series((rng.random(n) < p_bad).astype(int), dtype="Int64")

    # near-duplicate of fico -> should be pruned by correlation filter
    fico_twin = pd.array(fico_filled + rng.normal(0, 5, n), dtype="Float64")
    noise = pd.array(rng.uniform(0, 1, n), dtype="Float64")  # no signal -> low IV

    df = pd.DataFrame(
        {
            "fico_range_low": fico,
            "fico_range_high": fico_twin,
            "home_ownership": home,
            "dti": noise,
        }
    )
    return df, y


VARS = ["fico_range_low", "fico_range_high", "home_ownership", "dti"]


@pytest.fixture(scope="module")
def fitted():
    df, y = _synthetic_train()
    binners = fit_binning(df, y, variables=VARS)
    return df, y, binners


# --- candidates ---------------------------------------------------------------


def test_binning_candidates_exclude_emp_title_only():
    assert BINNING_EXCLUDED_COLUMNS == ["emp_title"]
    assert "emp_title" not in BINNING_CANDIDATES
    assert set(BINNING_CANDIDATES) == (set(NUMERIC_COLUMNS) | set(CATEGORICAL_COLUMNS)) - {"emp_title"}
    assert len(BINNING_CANDIDATES) == 17


# --- fit / transform ----------------------------------------------------------


def test_fit_binning_accepts_nullable_dtypes(fitted):
    _, _, binners = fitted
    assert set(binners) == set(VARS)
    assert binners["fico_range_low"].status == "OPTIMAL"


def test_fit_binning_rejects_missing_labels():
    df, y = _synthetic_train(n=200)
    y = y.copy()
    y.iloc[0] = pd.NA
    with pytest.raises(ValueError, match="missing"):
        fit_binning(df, y, variables=["fico_range_low"])


def test_transform_woe_monotone_in_fico(fitted):
    df, y, binners = fitted
    woe = transform_woe(df, binners)
    # WOE of fico should correlate with fico value (monotone constraint)
    mask = df["fico_range_low"].notna()
    corr = np.corrcoef(
        df.loc[mask, "fico_range_low"].astype(float), woe.loc[mask, "fico_range_low"]
    )[0, 1]
    assert abs(corr) > 0.9


def test_transform_woe_missing_gets_empirical_bin_not_zero():
    # informative missingness: missing rows are much worse credits
    rng = np.random.default_rng(7)
    n = 3000
    x = pd.array(rng.uniform(0, 100, n), dtype="Float64")
    miss = rng.choice(n, 600, replace=False)
    x[miss] = pd.NA
    y = (rng.random(n) < 0.10).astype(int)
    y[miss] = (rng.random(600) < 0.40).astype(int)
    df = pd.DataFrame({"dti": x})
    binners = fit_binning(df, pd.Series(y, dtype="Int64"), variables=["dti"])
    woe = transform_woe(df, binners)
    missing_woe = woe.loc[pd.Series(x).isna().to_numpy(), "dti"].unique()
    assert len(missing_woe) == 1
    assert missing_woe[0] != 0.0  # the silent-zero default would fail this


def test_transform_woe_same_rules_for_new_data(fitted):
    df, _, binners = fitted
    valid = df.iloc[:50]
    woe_all = transform_woe(df, binners)
    woe_valid = transform_woe(valid, binners)
    pd.testing.assert_frame_equal(woe_valid, woe_all.iloc[:50])


# --- iv_table / bin_edges -------------------------------------------------------


def test_iv_table_descending_and_signal_ranks_first(fitted):
    _, _, binners = fitted
    tbl = iv_table(binners)
    assert list(tbl.columns) == ["variable", "iv"]
    assert tbl["iv"].is_monotonic_decreasing
    assert tbl.iloc[0]["variable"] in {"fico_range_low", "fico_range_high"}
    assert tbl.set_index("variable").loc["dti", "iv"] < 0.02  # noise stays unpredictive


def test_bin_edges_numeric_floats_and_categorical_groups(fitted):
    _, _, binners = fitted
    edges = bin_edges(binners)
    assert all(isinstance(e, float) for e in edges["fico_range_low"])
    assert len(edges["fico_range_low"]) > 0
    assert isinstance(edges["home_ownership"], list)


# --- select_variables -----------------------------------------------------------


def test_select_variables_prunes_low_iv_and_high_corr(fitted):
    df, _, binners = fitted
    woe = transform_woe(df, binners)
    tbl = iv_table(binners)
    selected, decisions = select_variables(woe, tbl)

    assert "dti" not in selected  # low IV
    # fico twins are |corr|~1: exactly one survives
    assert len({"fico_range_low", "fico_range_high"} & set(selected)) == 1
    assert "home_ownership" in selected

    dropped = decisions.loc[~decisions["selected"].astype(bool), "variable"].tolist()
    assert "dti" in dropped
    assert set(decisions["variable"]) == set(VARS)


def test_select_variables_final_set_under_corr_cap(fitted):
    df, _, binners = fitted
    woe = transform_woe(df, binners)
    selected, _ = select_variables(woe, iv_table(binners))
    if len(selected) > 1:
        corr = woe[selected].corr().abs()
        off = corr.where(~np.eye(len(selected), dtype=bool))
        assert float(off.max().max()) <= 0.7
