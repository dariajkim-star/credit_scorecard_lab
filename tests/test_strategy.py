"""Tests for CAP-9,10 cutoff trade-off curve and swap-set analysis (Story 2.1)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scorecard.config import DATA_DIR
from scorecard.strategy import (
    OOT_VINTAGE,
    cutoff_trade_off_curve,
    lookup_cutoff,
    swap_set_table,
)

SCORED_FRAME_PATH = DATA_DIR / "scored_validation_frame.parquet"


def _synthetic_frame(n=200, seed=0):
    rng = np.random.default_rng(seed)
    applicant_id = [f"A{i}" for i in range(n)]
    vintage = rng.choice([2014, OOT_VINTAGE], size=n)
    bad_flag = rng.integers(0, 2, n)
    champ_score = rng.normal(550, 30, n)
    # correlated-but-different challenger score so swap-set is non-trivial
    chall_score = champ_score + rng.normal(0, 15, n)

    def _rows(model_type: str, score: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame({
            "applicant_id": applicant_id,
            "vintage": vintage,
            "model_type": model_type,
            "score": score,
            "pd": 0.1,
            "grade": 5,
            "bad_flag": bad_flag,
            "int_rate": 10.0,
            "recoveries": 0.0,
            "total_pymnt": 1000.0,
        })

    return pd.concat([_rows("champion", champ_score), _rows("challenger", chall_score)], ignore_index=True)


# --- cutoff_trade_off_curve (FR9) -----------------------------------------


def test_cutoff_trade_off_curve_approval_rate_nonincreasing():
    df = _synthetic_frame()
    curve = cutoff_trade_off_curve(df, "champion", vintage=None)
    diffs = np.diff(curve["approval_rate"].to_numpy())
    assert np.all(diffs <= 1e-12)


def test_cutoff_trade_off_curve_covers_full_approval_range():
    df = _synthetic_frame()
    total = int((df["model_type"] == "champion").sum())
    curve = cutoff_trade_off_curve(df, "champion", vintage=None)
    # at the lowest grid cutoff, everyone is approved
    assert curve["approval_rate"].max() == pytest.approx(1.0)
    # at the highest grid cutoff (== max observed score), only the single
    # top scorer remains approved - true 0% requires cutoff > max(score),
    # which is outside the observed-range grid by design
    assert curve["approval_rate"].min() == pytest.approx(1 / total)


def test_cutoff_trade_off_curve_zero_approvals_gives_nan_bad_rate_not_zero_div():
    df = _synthetic_frame()
    max_score = df.loc[df["model_type"] == "champion", "score"].max()
    curve = cutoff_trade_off_curve(df, "champion", cutoffs=np.array([max_score + 1000.0]), vintage=None)
    assert curve.loc[0, "approved_count"] == 0
    assert curve.loc[0, "approval_rate"] == pytest.approx(0.0)
    assert np.isnan(curve.loc[0, "bad_rate"])


def test_cutoff_trade_off_curve_respects_vintage_filter():
    df = _synthetic_frame()
    oot_only = cutoff_trade_off_curve(df, "champion", vintage=OOT_VINTAGE)
    both = cutoff_trade_off_curve(df, "champion", vintage=None)
    oot_population = (df["model_type"] == "champion") & (df["vintage"] == OOT_VINTAGE)
    assert oot_only["approved_count"].max() == oot_population.sum()
    assert both["approved_count"].max() == (df["model_type"] == "champion").sum()


def test_lookup_cutoff_matches_curve_single_value():
    df = _synthetic_frame()
    cutoff = 550.0
    result = lookup_cutoff(df, "champion", cutoff, vintage=None)
    curve = cutoff_trade_off_curve(df, "champion", cutoffs=np.array([cutoff]), vintage=None)
    assert result["approved_count"] == curve.loc[0, "approved_count"]
    assert result["approval_rate"] == pytest.approx(curve.loc[0, "approval_rate"])
    assert result["bad_rate"] == pytest.approx(curve.loc[0, "bad_rate"])


# --- swap_set_table (FR10) --------------------------------------------------


def test_swap_set_table_segments_sum_to_population():
    df = _synthetic_frame()
    result = swap_set_table(df, cutoff=550.0, vintage=None)
    total = (
        result["swap_in"]["count"]
        + result["swap_out"]["count"]
        + result["stable_approved"]["count"]
        + result["stable_rejected"]["count"]
    )
    assert total == result["population"]


def test_swap_set_table_direction_definitions():
    champion = pd.DataFrame({
        "applicant_id": ["A", "B", "C", "D"],
        "vintage": [2015, 2015, 2015, 2015],
        "model_type": "champion",
        "score": [400.0, 600.0, 700.0, 300.0],
        "pd": 0.0,
        "grade": 0,
        "bad_flag": [0, 0, 1, 1],
        "int_rate": 0.0,
        "recoveries": 0.0,
        "total_pymnt": 0.0,
    })
    challenger = champion.copy()
    challenger["model_type"] = "challenger"
    # A: champion rejects(400<500) -> challenger approves(600) = swap_in
    # B: champion approves(600)    -> challenger rejects(400)  = swap_out
    # C: both approve                                          = stable_approved
    # D: both reject                                            = stable_rejected
    challenger["score"] = [600.0, 400.0, 750.0, 200.0]
    frame = pd.concat([champion, challenger], ignore_index=True)

    result = swap_set_table(frame, cutoff=500.0, vintage=None)

    assert result["swap_in"]["count"] == 1
    assert result["swap_out"]["count"] == 1
    assert result["stable_approved"]["count"] == 1
    assert result["stable_rejected"]["count"] == 1
    assert result["population"] == 4
    # ground-truth bad_flag used for the swap_in segment is applicant A's (0)
    assert result["swap_in"]["bad_rate"] == pytest.approx(0.0)
    # stable_approved segment is applicant C, bad_flag=1
    assert result["stable_approved"]["bad_rate"] == pytest.approx(1.0)


def test_swap_set_table_uses_default_oot_vintage():
    df = _synthetic_frame()
    result_default = swap_set_table(df, cutoff=550.0)
    result_explicit_oot = swap_set_table(df, cutoff=550.0, vintage=OOT_VINTAGE)
    assert result_default["population"] == result_explicit_oot["population"]


# --- Guard rails added in code review (empty/malformed populations) --------


def test_cutoff_trade_off_curve_raises_on_empty_population():
    df = _synthetic_frame()
    with pytest.raises(ValueError, match="no rows"):
        cutoff_trade_off_curve(df, "champion", vintage=1999)


def test_cutoff_trade_off_curve_raises_on_unknown_model_type():
    df = _synthetic_frame()
    with pytest.raises(ValueError, match="no rows"):
        cutoff_trade_off_curve(df, "not_a_model", vintage=None)


def test_cutoff_trade_off_curve_raises_on_nan_score():
    df = _synthetic_frame()
    df.loc[df["model_type"] == "champion", "score"] = np.nan
    with pytest.raises(ValueError, match="missing score/bad_flag"):
        cutoff_trade_off_curve(df, "champion", vintage=None)


def test_swap_set_table_raises_on_empty_population():
    df = _synthetic_frame()
    with pytest.raises(ValueError, match="no champion/challenger rows"):
        swap_set_table(df, cutoff=550.0, vintage=1999)


def test_swap_set_table_raises_when_one_model_type_entirely_missing():
    df = _synthetic_frame()
    champion_only = df[df["model_type"] == "champion"]
    with pytest.raises(ValueError, match="missing"):
        swap_set_table(champion_only, cutoff=550.0, vintage=None)


def test_swap_set_table_raises_on_duplicate_applicant_rows():
    df = _synthetic_frame()
    dup_row = df[df["applicant_id"] == "A0"].copy()
    df_with_dup = pd.concat([df, dup_row], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        swap_set_table(df_with_dup, cutoff=550.0, vintage=None)


def test_swap_set_table_raises_on_mismatched_bad_flag():
    champion = pd.DataFrame({
        "applicant_id": ["A", "B"],
        "vintage": [2015, 2015],
        "model_type": "champion",
        "score": [400.0, 600.0],
        "pd": 0.0,
        "grade": 0,
        "bad_flag": [0, 1],
        "int_rate": 0.0,
        "recoveries": 0.0,
        "total_pymnt": 0.0,
    })
    challenger = champion.copy()
    challenger["model_type"] = "challenger"
    challenger["bad_flag"] = [1, 1]  # applicant A disagrees with champion (0 vs 1)
    frame = pd.concat([champion, challenger], ignore_index=True)
    with pytest.raises(ValueError, match="disagree"):
        swap_set_table(frame, cutoff=500.0, vintage=None)


# --- Real data regression (AD-3 frame integrity) ---------------------------


@pytest.mark.skipif(not SCORED_FRAME_PATH.exists(), reason="scored validation frame not generated locally")
def test_real_scored_frame_bad_flag_consistent_across_models():
    """Guards against a frame-generation bug where the same applicant's
    ground-truth outcome would differ between champion/challenger rows -
    swap_set_table's use of a single model's bad_flag as ground truth
    depends on this invariant holding."""
    df = pd.read_parquet(SCORED_FRAME_PATH)
    wide = df.pivot(index=["applicant_id", "vintage"], columns="model_type", values="bad_flag")
    assert (wide["champion"] == wide["challenger"]).all()
