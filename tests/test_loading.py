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
            "id": ["a", "b", "c", "d", "e", "f"],
            "issue_d": [
                "Jan-2011",  # before window -> drop
                "Jun-2012",  # in window, 36m -> keep
                "Dec-2014",  # in window, 36m -> keep
                "Mar-2015",  # in window but 60m -> drop
                "Feb-2016",  # after window -> drop
                "Aug-2013",  # in window, 36m -> keep
            ],
            "term": [
                " 36 months",
                " 36 months",
                " 36 months",
                " 60 months",
                " 36 months",
                " 36 months",
            ],
            "loan_status": ["Fully Paid"] * 6,
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
    assert set(out["id"]) == {"b", "c", "f"}
    assert set(out["vintage"]) == {2012, 2013, 2014}


def test_filter_adds_vintage_column():
    out = filter_accepted(_synthetic_frame())
    assert "vintage" in out.columns


def test_summarize_reports_rows_and_terms():
    out = filter_accepted(_synthetic_frame())
    stats = summarize(out)
    assert stats["rows"] == 3
    assert stats["term_values"] == [" 36 months"]
    assert stats["vintage_counts"] == {2012: 1, 2013: 1, 2014: 1}
