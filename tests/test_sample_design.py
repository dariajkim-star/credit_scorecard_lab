"""Tests for leakage audit, labeling, and vintage splitting (Story 1.2, synthetic data only)."""

from __future__ import annotations

import pandas as pd
import pytest

from scorecard.sample_design import (
    audit_columns,
    feature_candidate_columns,
    label_and_filter,
    make_label,
    performance_window_months,
    split_by_vintage,
    split_summary,
)


def _labeled_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": ["a", "b", "c", "d", "e", "f", "g"],
            "vintage": pd.array([2012, 2012, 2013, 2014, 2015, 2015, 2015], dtype="Int64"),
            "loan_status": [
                "Fully Paid",  # good
                "Charged Off",  # bad
                "Default",  # bad
                "Fully Paid",  # good
                "Fully Paid",  # good
                "Current",  # in-progress -> excluded
                "Late (31-120 days)",  # in-progress -> excluded
            ],
        }
    )


# --- audit_columns / feature_candidate_columns -------------------------------


def test_audit_columns_returns_dataframe_with_expected_shape():
    audit = audit_columns()
    assert set(audit.columns) == {"field", "classification", "excluded", "rationale"}
    assert len(audit) > 0
    assert audit["field"].is_unique


def test_audit_excludes_grade_int_rate_sub_grade():
    audit = audit_columns()
    excluded_fields = set(audit.loc[audit["excluded"] == "yes", "field"])
    assert {"grade", "sub_grade", "int_rate", "recoveries", "total_pymnt", "last_pymnt_d"} <= excluded_fields


def test_feature_candidate_columns_excludes_ids_and_leaky_fields():
    features = feature_candidate_columns()
    assert "loan_status" not in features
    assert "id" not in features
    assert "grade" not in features
    assert "int_rate" not in features
    assert "loan_amnt" in features


# --- make_label / label_and_filter -------------------------------------------


def test_make_label_bad_good_and_excluded():
    df = _labeled_frame()
    label = make_label(df)
    assert str(label.dtype) == "Int64"
    assert label.tolist() == [0, 1, 1, 0, 0, pd.NA, pd.NA]


def test_label_and_filter_drops_in_progress_rows():
    df = _labeled_frame()
    out = label_and_filter(df)
    assert set(out["id"]) == {"a", "b", "c", "d", "e"}
    assert out["bad_flag"].isna().sum() == 0
    assert str(out["bad_flag"].dtype) == "Int64"


def test_make_label_exact_string_match_only():
    df = pd.DataFrame({"loan_status": ["fully paid", "charged off ", "Fully Paid"]})
    label = make_label(df)
    # only an exact, case-sensitive match should resolve to good/bad
    assert label.tolist() == [pd.NA, pd.NA, 0]


# --- split_by_vintage / split_summary ----------------------------------------


def test_split_by_vintage_groups_correctly():
    df = label_and_filter(_labeled_frame())
    groups = split_by_vintage(df)
    assert set(groups["train"]["id"]) == {"a", "b", "c"}  # 2012, 2012, 2013
    assert set(groups["valid"]["id"]) == {"d"}  # 2014
    assert set(groups["oot"]["id"]) == {"e"}  # 2015 (only e survives labeling)


def test_split_by_vintage_raises_on_empty_group():
    df = label_and_filter(_labeled_frame())
    oot_only = df.loc[df["vintage"] == 2015].reset_index(drop=True)
    with pytest.raises(ValueError, match="empty"):
        split_by_vintage(oot_only)


def test_split_by_vintage_raises_on_unmatched_vintage():
    df = label_and_filter(_labeled_frame())
    stray = pd.DataFrame(
        {"id": ["z"], "vintage": pd.array([2011], dtype="Int64"), "bad_flag": pd.array([0], dtype="Int64")}
    )
    df_with_stray = pd.concat([df, stray], ignore_index=True)
    with pytest.raises(ValueError, match="outside"):
        split_by_vintage(df_with_stray)


def test_split_summary_reports_rows_and_bad_rate():
    df = label_and_filter(_labeled_frame())
    groups = split_by_vintage(df)
    summary = split_summary(groups)
    assert summary["train"]["rows"] == 3
    assert summary["train"]["bad_rate"] == pytest.approx(2 / 3)
    assert summary["valid"]["rows"] == 1
    assert summary["valid"]["bad_rate"] == 0.0
    assert summary["oot"]["rows"] == 1
    assert summary["oot"]["bad_rate"] == 0.0


# --- performance_window_months ------------------------------------------------


def test_performance_window_months_computes_gap():
    df = pd.DataFrame(
        {
            "issue_d": ["Jan-2013", "Jun-2013", "Mar-2014"],
            "last_pymnt_d": ["Jan-2016", "garbage", "Mar-2014"],
        }
    )
    months = performance_window_months(df)
    assert str(months.dtype) == "Int64"
    assert months.tolist() == [36, pd.NA, 0]
