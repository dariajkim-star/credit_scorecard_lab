"""Tests for CAP-14 profit-based cutoff (Story 2.4)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scorecard.config import ACCEPTED_PARQUET, DATA_DIR
from scorecard.profit import (
    find_optimal_cutoff,
    load_profit_frame,
    profit_cutoff_curve,
    realized_profit,
    realized_return_rate,
)
from scorecard.strategy import OOT_VINTAGE

SCORED_FRAME_PATH = DATA_DIR / "scored_validation_frame.parquet"
ARTIFACTS_PRESENT = ACCEPTED_PARQUET.exists() and SCORED_FRAME_PATH.exists()


# --- pure functions -----------------------------------------------------


def test_realized_profit_positive_for_a_good_loan():
    # borrower paid back more than principal, no recoveries needed
    assert realized_profit(loan_amnt=10000, total_pymnt=11200, recoveries=0) == pytest.approx(1200)


def test_realized_profit_negative_for_a_charged_off_loan():
    # borrower defaulted early, recoveries only partially offset the loss
    profit = realized_profit(loan_amnt=10000, total_pymnt=2000, recoveries=500)
    assert profit == pytest.approx(2000 + 500 - 10000)
    assert profit < 0


def test_realized_profit_vectorized_over_series():
    loan_amnt = pd.Series([10000.0, 5000.0])
    total_pymnt = pd.Series([11000.0, 1000.0])
    recoveries = pd.Series([0.0, 200.0])
    result = realized_profit(loan_amnt, total_pymnt, recoveries)
    assert list(result) == pytest.approx([1000.0, -3800.0])


def test_realized_return_rate_is_scale_invariant():
    """Two loans of different sizes with the same proportional outcome
    must produce the same rate - this is the whole point of rate-izing
    before averaging across loans of different loan_amnt."""
    rate_small = realized_return_rate(loan_amnt=1000, total_pymnt=1100, recoveries=0)
    rate_large = realized_return_rate(loan_amnt=100000, total_pymnt=110000, recoveries=0)
    assert rate_small == pytest.approx(rate_large)
    assert rate_small == pytest.approx(0.10)


def test_realized_return_rate_guards_against_zero_loan_amnt():
    with pytest.raises(ValueError, match="loan_amnt"):
        realized_return_rate(loan_amnt=0, total_pymnt=100, recoveries=0)


def test_realized_return_rate_guards_against_zero_in_a_vectorized_call():
    """The guard must fire for the array/Series call path too - this is the
    ONLY call path profit_cutoff_curve actually uses (code review finding:
    the original np.isscalar check silently passed a zero hidden inside an
    array, producing inf via plain float division with no exception)."""
    loan_amnt = np.array([10000.0, 0.0, 5000.0])
    with pytest.raises(ValueError, match="loan_amnt"):
        realized_return_rate(loan_amnt, np.array([11000.0, 100.0, 5500.0]), np.array([0.0, 0.0, 0.0]))


# --- profit_cutoff_curve / find_optimal_cutoff (synthetic) ---------------


def _synthetic_profit_frame(n=500, seed=5):
    rng = np.random.default_rng(seed)
    score = rng.uniform(400, 700, n)
    loan_amnt = rng.uniform(5000, 20000, n)
    # higher score -> better repayment (less loss), by construction
    repay_fraction = np.clip((score - 400) / 300, 0.3, 1.0) + rng.normal(0, 0.05, n)
    total_pymnt = loan_amnt * repay_fraction
    recoveries = np.where(repay_fraction < 0.9, loan_amnt * 0.05, 0.0)
    return pd.DataFrame({
        "applicant_id": [f"A{i}" for i in range(n)],
        "vintage": OOT_VINTAGE,
        "model_type": "champion",
        "score": score,
        "loan_amnt": loan_amnt,
        "total_pymnt": total_pymnt,
        "recoveries": recoveries,
    })


def test_profit_cutoff_curve_has_expected_columns():
    frame = _synthetic_profit_frame()
    curve = profit_cutoff_curve(frame, "champion", avg_loan_amnt=12000.0)
    assert {"cutoff", "approval_rate", "expected_annual_profit"} <= set(curve.columns)
    assert len(curve) > 1


def test_find_optimal_cutoff_matches_curve_max():
    frame = _synthetic_profit_frame()
    curve = profit_cutoff_curve(frame, "champion", avg_loan_amnt=12000.0)
    optimal = find_optimal_cutoff(curve)
    best_row = curve.loc[curve["expected_annual_profit"].idxmax()]
    assert optimal == pytest.approx(best_row["cutoff"])


def test_profit_curve_not_forced_monotonic():
    """Unlike the risk trade-off curve, profit is not monotonic in cutoff -
    raising the bar always lowers bad debt but also shrinks volume, so the
    curve can rise then fall. This test only asserts it's *computable*
    without any (wrong) monotonicity assumption breaking it."""
    frame = _synthetic_profit_frame()
    curve = profit_cutoff_curve(frame, "champion", avg_loan_amnt=12000.0)
    assert curve["expected_annual_profit"].notna().any()


def test_zero_approval_cutoff_is_nan_not_zero():
    """A cutoff above every observed score approves nobody - its
    expected_annual_profit must be NaN (undefined), not 0.0, so it can never
    win find_optimal_cutoff's argmax over a genuinely lossy population
    (code review finding: 0.0 could silently beat an all-negative curve and
    get reported as the profit-optimal policy)."""
    frame = _synthetic_profit_frame()
    max_score = frame["score"].max()
    curve = profit_cutoff_curve(
        frame, "champion", avg_loan_amnt=12000.0, cutoffs=np.array([max_score + 1000.0])
    )
    assert curve.loc[0, "approved_count"] == 0
    assert np.isnan(curve.loc[0, "expected_annual_profit"])
    assert curve.loc[0, "approval_rate"] == pytest.approx(0.0)


def test_find_optimal_cutoff_raises_when_every_cutoff_has_zero_approvals():
    frame = _synthetic_profit_frame()
    max_score = frame["score"].max()
    curve = profit_cutoff_curve(
        frame, "champion", avg_loan_amnt=12000.0,
        cutoffs=np.array([max_score + 1000.0, max_score + 2000.0]),
    )
    with pytest.raises(ValueError, match="zero approved"):
        find_optimal_cutoff(curve)


def test_find_optimal_cutoff_delta_matches_independent_recomputation():
    """Recomputes the max profit and its cutoff independently (via a plain
    python loop, not the same pandas idxmax expression the code uses) so a
    sign or aggregation error in find_optimal_cutoff would actually be
    caught, unlike a test that re-derives the identical expression."""
    frame = _synthetic_profit_frame()
    curve = profit_cutoff_curve(frame, "champion", avg_loan_amnt=12000.0)
    rows = curve.to_dict("records")
    best = None
    for row in rows:
        if row["expected_annual_profit"] != row["expected_annual_profit"]:  # NaN check without numpy
            continue
        if best is None or row["expected_annual_profit"] > best["expected_annual_profit"]:
            best = row
    assert find_optimal_cutoff(curve) == pytest.approx(best["cutoff"])


def test_population_with_nan_values_raises_fail_fast():
    """A NaN in score/loan_amnt/total_pymnt/recoveries would otherwise
    silently poison every cutoff whose approved set includes that row via
    numpy's non-NaN-skipping .mean() (code review finding) - must fail
    fast instead, mirroring strategy.py's population-completeness guard."""
    frame = _synthetic_profit_frame()
    frame.loc[frame.index[0], "total_pymnt"] = np.nan
    with pytest.raises(ValueError, match="missing values"):
        profit_cutoff_curve(frame, "champion", avg_loan_amnt=12000.0)


# --- real data: loan_amnt join (AD-3-compliant augmentation) -------------


@pytest.mark.skipif(not ARTIFACTS_PRESENT, reason="scored frame / raw parquet not generated locally")
def test_load_profit_frame_joins_loan_amnt_from_raw_parquet():
    frame = pd.read_parquet(SCORED_FRAME_PATH)
    profit_frame = load_profit_frame(frame, ACCEPTED_PARQUET)
    assert "loan_amnt" in profit_frame.columns
    # frame's own columns must survive untouched (AD-3: augmentation, not
    # recomputation)
    for col in ("score", "pd", "grade", "bad_flag"):
        assert col in profit_frame.columns
    assert profit_frame["loan_amnt"].notna().all()  # 100% match verified in story Dev Notes


def test_load_profit_frame_raises_on_duplicate_raw_id(tmp_path):
    """validate="many_to_one" must fire if the raw parquet ever has a
    duplicate id - otherwise the join silently fans out (many-to-many),
    inflating the population and skewing every rate with no error
    (code review finding)."""
    frame = pd.DataFrame({
        "applicant_id": ["A1", "A2"],
        "score": [500.0, 600.0],
    })
    raw = pd.DataFrame({"id": ["A1", "A1", "A2"], "loan_amnt": [10000.0, 10000.0, 5000.0]})
    raw_path = tmp_path / "raw.parquet"
    raw.to_parquet(raw_path)
    with pytest.raises(Exception):  # pandas raises MergeError (ValueError subclass)
        load_profit_frame(frame, raw_path)


@pytest.mark.skipif(not ARTIFACTS_PRESENT, reason="scored frame / raw parquet not generated locally")
def test_load_profit_frame_raises_on_unmatched_applicant(monkeypatch):
    frame = pd.read_parquet(SCORED_FRAME_PATH).head(5).copy()
    frame.loc[frame.index[0], "applicant_id"] = "not-a-real-id-999999"
    with pytest.raises(ValueError, match="did not match"):
        load_profit_frame(frame, ACCEPTED_PARQUET)


@pytest.mark.skipif(not ARTIFACTS_PRESENT, reason="scored frame / raw parquet not generated locally")
def test_real_data_profit_cutoff_end_to_end():
    frame = pd.read_parquet(SCORED_FRAME_PATH)
    profit_frame = load_profit_frame(frame, ACCEPTED_PARQUET)
    curve = profit_cutoff_curve(profit_frame, "champion", avg_loan_amnt=12000.0)
    optimal = find_optimal_cutoff(curve)
    assert np.isfinite(optimal)
    assert curve["expected_annual_profit"].notna().any()
