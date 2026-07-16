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
def test_emp_title_category_runs_through_binning_and_yields_iv():
    from scorecard.binning import fit_binning, iv_table
    from scorecard.sample_design import label_and_filter, split_by_vintage

    raw = pd.read_parquet(
        ACCEPTED_PARQUET, columns=["emp_title", "loan_status", "vintage"]
    )
    labeled = label_and_filter(raw)
    splits = split_by_vintage(labeled)
    train = splits["train"]

    top = tf.fit_top_titles(tf.clean_emp_title(train["emp_title"]), k=20)
    train = train.assign(emp_title_category=tf.derive_emp_title_category(train, top))

    binners = fit_binning(
        train, train["bad_flag"], variables=["emp_title_category"]
    )
    iv = iv_table(binners)
    assert "emp_title_category" in set(iv["variable"])
    assert float(iv.iloc[0]["iv"]) >= 0.0  # a finite IV is produced (value reported in the report)
