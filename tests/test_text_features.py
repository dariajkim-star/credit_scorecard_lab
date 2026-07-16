"""Story 3.2 emp_title text-feature tests.

Pure text-op behavior (cleaning, top-K fit, category mapping, leakage
boundary) plus one real-data integration that runs the derived category
through the AD-2 binning path to confirm an IV is produced (the value itself
is reported, not asserted - a negative result is a valid outcome).
"""

from __future__ import annotations

import pandas as pd
import pytest

from scorecard import text_features as tf
from scorecard.config import ACCEPTED_PARQUET


def test_clean_lowercases_strips_punctuation_and_collapses_space():
    s = pd.Series(["  Registered Nurse!! ", "TRUCK-DRIVER", "Office   Manager"])
    out = tf.clean_emp_title(s)
    assert list(out) == ["registered nurse", "truck driver", "office manager"]


def test_clean_empty_and_null_become_na():
    s = pd.Series(["!!!", None, "   ", "***"])
    out = tf.clean_emp_title(s)
    assert out.isna().all()  # all-punctuation / blank / null -> NA


def test_fit_top_titles_returns_train_most_frequent():
    train = pd.Series(["teacher"] * 5 + ["manager"] * 3 + ["owner"] * 1 + [pd.NA] * 4)
    assert tf.fit_top_titles(train, k=2) == ["teacher", "manager"]


def test_fit_top_titles_tie_break_is_deterministic():
    # Equal counts at the k-th slot: ties break by title ascending, so the
    # persisted top-K artifact is reproducible across pandas versions (code
    # review finding - value_counts does not contractually order ties).
    train = pd.Series(["zebra"] * 2 + ["apple"] * 2 + ["mango"] * 2 + ["kiwi"])
    assert tf.fit_top_titles(train, k=2) == ["apple", "mango"]


def test_fit_top_titles_rejects_negative_k():
    with pytest.raises(ValueError, match="k must be >= 0"):
        tf.fit_top_titles(pd.Series(["a"]), k=-1)


def test_map_category_rejects_sentinel_or_na_in_top_titles():
    cleaned = pd.Series(["teacher"])
    with pytest.raises(ValueError, match="sentinels"):
        tf.map_emp_title_category(cleaned, top_titles=["teacher", tf.OTHER_CATEGORY])
    with pytest.raises(ValueError, match="sentinels"):
        tf.map_emp_title_category(cleaned, top_titles=["teacher", None])


def test_derive_missing_source_column_raises_domain_error():
    with pytest.raises(KeyError, match="column not found"):
        tf.derive_emp_title_category(pd.DataFrame({"x": [1]}), top_titles=["a"])


def test_map_category_top_other_missing():
    cleaned = pd.Series(["teacher", "manager", "astronaut", pd.NA])
    out = tf.map_emp_title_category(cleaned, top_titles=["teacher", "manager"])
    assert list(out) == ["teacher", "manager", tf.OTHER_CATEGORY, tf.MISSING_CATEGORY]


def test_map_category_is_pure_uses_passed_top_titles_only():
    # top_titles is applied verbatim: a frequent title NOT in the list still
    # maps to OTHER (no recomputation / leakage from the mapped split).
    cleaned = pd.Series(["nurse"] * 100 + ["teacher"])
    out = tf.map_emp_title_category(cleaned, top_titles=["teacher"])
    assert set(out) == {"teacher", tf.OTHER_CATEGORY}
    assert (out == tf.OTHER_CATEGORY).sum() == 100


def test_derive_reads_source_column():
    df = pd.DataFrame({"emp_title": ["Teacher", "weird$$$"]})
    out = tf.derive_emp_title_category(df, top_titles=["teacher"])
    assert list(out) == ["teacher", tf.OTHER_CATEGORY]


# --- real-data integration: category -> AD-2 binning -> IV --------------------

ARTIFACTS_PRESENT = ACCEPTED_PARQUET.exists()


@pytest.mark.skipif(not ARTIFACTS_PRESENT, reason="raw parquet not present")
def test_iv_comparison_reproduces_report_table():
    """The single committed reproduction path for the report's IV numbers
    (code review: previously an ad-hoc run). Pins the negative result and the
    apples-to-apples ordering, and asserts finiteness properly (the old
    `iv >= 0` was tautological - IV is non-negative by construction and inf
    passed it)."""
    import numpy as np

    iv = tf.iv_comparison()
    by_var = dict(zip(iv["variable"], iv["iv"]))
    emp = by_var["emp_title_category"]
    assert np.isfinite(emp)
    assert emp < 0.02  # the honest negative result the report records
    # below every structured variable (report's core comparison claim)
    assert all(emp < by_var[v] for v in tf.STRUCTURED_COMPARISON_VARIABLES)


@pytest.mark.skipif(not ARTIFACTS_PRESENT, reason="raw parquet not present")
def test_leakage_boundary_oot_maps_to_known_categories_only():
    """Train-fitted top_titles applied to the OOT split must yield only
    {top-K, OTHER, MISSING} - no unseen-category explosion at apply time
    (code review: the boundary was claimed but never exercised)."""
    from scorecard.sample_design import label_and_filter, split_by_vintage

    raw = pd.read_parquet(
        ACCEPTED_PARQUET, columns=["emp_title", "loan_status", "vintage"]
    )
    splits = split_by_vintage(label_and_filter(raw))
    top = tf.fit_top_titles(tf.clean_emp_title(splits["train"]["emp_title"]), k=20)
    oot_cats = set(tf.derive_emp_title_category(splits["oot"], top).unique())
    allowed = set(top) | {tf.OTHER_CATEGORY, tf.MISSING_CATEGORY}
    assert oot_cats <= allowed
