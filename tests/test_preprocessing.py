"""Tests for percent parsing, missing reporting, and capping (Story 1.3, synthetic data only)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scorecard.preprocessing import (
    CAPPABLE_NUMERIC_COLUMNS,
    CAPPING_EXCLUDED_COLUMNS,
    CATEGORICAL_COLUMNS,
    NUMERIC_COLUMNS,
    apply_caps,
    coerce_percent_columns,
    distribution_report,
    fit_caps,
    missing_summary,
    parse_percent,
)
from scorecard.sample_design import feature_candidate_columns


# --- column classification ----------------------------------------------------


def test_numeric_and_categorical_columns_match_feature_candidates():
    assert set(NUMERIC_COLUMNS) | set(CATEGORICAL_COLUMNS) == set(feature_candidate_columns())
    assert set(NUMERIC_COLUMNS).isdisjoint(CATEGORICAL_COLUMNS)


def test_zero_inflated_count_columns_excluded_from_capping():
    assert set(CAPPING_EXCLUDED_COLUMNS) == {"delinq_2yrs", "inq_last_6mths", "pub_rec"}
    assert set(CAPPING_EXCLUDED_COLUMNS).isdisjoint(CAPPABLE_NUMERIC_COLUMNS)
    assert set(CAPPABLE_NUMERIC_COLUMNS) | set(CAPPING_EXCLUDED_COLUMNS) == set(NUMERIC_COLUMNS)


def test_capping_a_zero_inflated_count_column_would_collapse_signal():
    # Regression guard for the code-review finding: a blanket 1%/99% cap on a
    # heavily zero-inflated count column collapses distinct risk levels (2 vs
    # 5 public records) into the same value - this is why pub_rec etc. are
    # excluded from CAPPABLE_NUMERIC_COLUMNS above.
    train = pd.DataFrame({"pub_rec": [0] * 985 + [1] * 10 + [2] * 4 + [5] * 1})
    caps = fit_caps(train, ["pub_rec"])
    valid = pd.DataFrame({"pub_rec": [0, 1, 2, 5]})
    out = apply_caps(valid, caps)
    assert out["pub_rec"].tolist() == [0, 1, 1, 1]  # demonstrates the collapse
    assert "pub_rec" not in CAPPABLE_NUMERIC_COLUMNS


# --- parse_percent / coerce_percent_columns -----------------------------------


def test_parse_percent_basic():
    s = pd.Series(["45.3%", "0%", "100%"])
    out = parse_percent(s)
    assert str(out.dtype) == "Float64"
    assert out.tolist() == [45.3, 0.0, 100.0]


def test_parse_percent_missing_and_malformed_stay_missing():
    s = pd.Series(["45.3%", None, "garbage", ""])
    out = parse_percent(s)
    assert out.isna().tolist() == [False, True, True, True]


def test_parse_percent_handles_whitespace():
    s = pd.Series([" 12.5% ", "  7%"])
    out = parse_percent(s)
    assert out.tolist() == [12.5, 7.0]


def test_coerce_percent_columns_only_touches_named_columns():
    df = pd.DataFrame({"revol_util": ["50%", "10%"], "other": ["50%", "10%"]})
    out = coerce_percent_columns(df, ["revol_util"])
    assert out["revol_util"].tolist() == [50.0, 10.0]
    assert out["other"].tolist() == ["50%", "10%"]  # untouched


# --- missing_summary (no imputation) ------------------------------------------


def test_missing_summary_counts_and_rate():
    df = pd.DataFrame({"a": [1, None, 3, None], "b": [1, 2, 3, 4]})
    summary = missing_summary(df, ["a", "b"])
    a_row = summary.loc[summary["field"] == "a"].iloc[0]
    b_row = summary.loc[summary["field"] == "b"].iloc[0]
    assert a_row["n_missing"] == 2
    assert a_row["missing_rate"] == pytest.approx(0.5)
    assert b_row["n_missing"] == 0


# --- fit_caps / apply_caps -----------------------------------------------------


def _train_valid_frames():
    train = pd.DataFrame({"dti": list(range(1, 101))})  # 1..100
    valid = pd.DataFrame({"dti": [-50, 5, 50, 500, np.nan]})
    return train, valid


def test_fit_caps_computed_from_train_percentiles():
    train, _ = _train_valid_frames()
    caps = fit_caps(train, ["dti"], lower_q=0.01, upper_q=0.99)
    lo, hi = caps["dti"]
    assert lo == pytest.approx(train["dti"].quantile(0.01))
    assert hi == pytest.approx(train["dti"].quantile(0.99))


def test_apply_caps_clips_valid_using_train_fitted_caps():
    train, valid = _train_valid_frames()
    caps = fit_caps(train, ["dti"])
    out = apply_caps(valid, caps)
    lo, hi = caps["dti"]
    assert out["dti"].iloc[0] == pytest.approx(lo)  # -50 clipped up to lo
    assert out["dti"].iloc[3] == pytest.approx(hi)  # 500 clipped down to hi
    assert out["dti"].iloc[1] == 5  # untouched, within range


def test_apply_caps_never_fills_missing():
    train, valid = _train_valid_frames()
    caps = fit_caps(train, ["dti"])
    before_missing = valid["dti"].isna().sum()
    out = apply_caps(valid, caps)
    after_missing = out["dti"].isna().sum()
    assert before_missing == after_missing == 1
    assert pd.isna(out["dti"].iloc[4])


# --- distribution_report -------------------------------------------------------


def test_distribution_report_reports_min_max_mean_missing():
    before = pd.DataFrame({"dti": [-50, 5, 50, 500, np.nan]})
    caps = fit_caps(pd.DataFrame({"dti": list(range(1, 101))}), ["dti"])
    after = apply_caps(before, caps)
    report = distribution_report(before, after, ["dti"])
    row = report.iloc[0]
    assert row["field"] == "dti"
    assert row["min_before"] == -50
    assert row["min_after"] == pytest.approx(caps["dti"][0])
    assert row["max_before"] == 500
    assert row["max_after"] == pytest.approx(caps["dti"][1])
    assert row["n_missing_before"] == 1
    assert row["n_missing_after"] == 1
