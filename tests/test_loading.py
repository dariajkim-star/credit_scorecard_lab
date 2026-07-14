"""Tests for the vintage/term filter logic (no network / no 1.6GB download)."""

from __future__ import annotations

import pandas as pd

from pipelines.loading import (
    derive_vintage,
    filter_accepted,
    parse_term_months,
    summarize,
)


def _synthetic_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": ["a", "b", "c", "d", "e", "f", "g"],
            "issue_d": [
                "Jan-2011",  # before window -> drop
                "Jun-2012",  # lower boundary (VINTAGE_MIN), 36m -> keep
                "Dec-2014",  # in window, 36m -> keep
                "Mar-2015",  # in window but 60m -> drop
                "Feb-2016",  # after window -> drop
                "Aug-2013",  # in window, 36m -> keep
                "Nov-2015",  # upper boundary (VINTAGE_MAX), 36m -> keep
            ],
            "term": [
                " 36 months",
                " 36 months",
                " 36 months",
                " 60 months",
                " 36 months",
                " 36 months",
                " 36 months",
            ],
            "loan_status": ["Fully Paid"] * 7,
        }
    )


def test_derive_vintage_parses_year():
    s = derive_vintage(pd.Series(["Dec-2015", "Jan-2012"]))
    assert list(s) == [2015, 2012]


def test_parse_term_months_extracts_int():
    s = parse_term_months(pd.Series([" 36 months", " 60 months"]))
    assert list(s) == [36, 60]


def test_filter_keeps_only_window_and_36m():
    out = filter_accepted(_synthetic_frame())
    assert set(out["id"]) == {"b", "c", "f", "g"}
    # both boundaries inclusive: 2012 (VINTAGE_MIN) and 2015 (VINTAGE_MAX) kept
    assert set(out["vintage"]) == {2012, 2013, 2014, 2015}


def test_filter_adds_vintage_column():
    out = filter_accepted(_synthetic_frame())
    assert "vintage" in out.columns


def test_vintage_dtype_stable_with_unparseable_dates():
    # .dt.year alone flips int -> float64 on the first NaT; we pin Int64
    clean = derive_vintage(pd.Series(["Dec-2015", "Jan-2012"]))
    dirty = derive_vintage(pd.Series(["Dec-2015", None, "garbage"]))
    assert str(clean.dtype) == "Int64"
    assert str(dirty.dtype) == "Int64"
    assert dirty.isna().sum() == 2


def test_summarize_reports_rows_and_terms():
    out = filter_accepted(_synthetic_frame())
    stats = summarize(out)
    assert stats["rows"] == 4
    assert stats["term_values"] == [" 36 months"]
    assert stats["vintage_counts"] == {2012: 1, 2013: 1, 2014: 1, 2015: 1}
