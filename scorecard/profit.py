"""CAP-14 profit-based cutoff simulation (FR14, AD-7 rule/arithmetic-only).

The scored validation frame (AD-3) has int_rate/recoveries/total_pymnt but
NOT the original loan principal (loan_amnt) needed to compute realized
per-loan profit in absolute terms - a gap discovered while writing this
story (Dev Notes, docs/implementation-artifacts/2-4-profit-based-cutoff.md).
Decision: read the raw accepted parquet read-only to augment the frame with
loan_amnt (join on applicant_id == id, both string dtype, verified 100%
match on the real data). The frame's own columns (score/pd/grade/bad_flag/
int_rate/recoveries/total_pymnt) are never recomputed - this is AD-3-
compliant augmentation, not a violation, mirroring how Story 2.2 already
read the raw parquet for a different purpose.

Judgment (LLM/external calls) is never used here (AD-7) - "optimal" means
the grid point maximizing a plain arithmetic aggregate.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scorecard.strategy import OOT_VINTAGE, _default_cutoff_grid


def realized_profit(loan_amnt, total_pymnt, recoveries):
    """Net realized profit/loss on one loan (or vectorized over a Series):
    what was collected minus what was lent. Positive = profit, negative =
    loss. Standard credit P&L identity - no modeling assumptions."""
    return total_pymnt + recoveries - loan_amnt


def realized_return_rate(loan_amnt, total_pymnt, recoveries):
    """realized_profit scaled by loan_amnt (dimensionless rate).

    Loans of different sizes cannot be compared or averaged in absolute
    profit terms without distorting the result toward whichever loans
    happened to be larger - this rate makes them comparable, and is what
    gets averaged across the approved population before being scaled back
    to dollars via the request's avg_loan_amnt (see profit_cutoff_curve).
    """
    if np.isscalar(loan_amnt) and loan_amnt == 0:
        raise ValueError("loan_amnt must be nonzero to compute a return rate")
    return realized_profit(loan_amnt, total_pymnt, recoveries) / loan_amnt


def load_profit_frame(frame: pd.DataFrame, raw_parquet_path: str | Path) -> pd.DataFrame:
    """Augment the AD-3 scored frame with loan_amnt from the raw accepted
    parquet (read-only join on applicant_id == id). Fails fast on any
    unmatched applicant rather than silently dropping/NaN-ing loans out of
    the profit calculation (same fail-fast convention as strategy.py).
    """
    raw = pd.read_parquet(raw_parquet_path, columns=["id", "loan_amnt"])
    merged = frame.merge(raw, left_on="applicant_id", right_on="id", how="left")
    unmatched = merged["loan_amnt"].isna().sum()
    if unmatched:
        raise ValueError(
            f"{unmatched} applicant_id(s) did not match any row in the raw parquet "
            f"({raw_parquet_path}) - the scored frame and raw source have diverged"
        )
    return merged.drop(columns=["id"])


def profit_cutoff_curve(
    profit_frame: pd.DataFrame,
    model_type: str,
    avg_loan_amnt: float,
    cutoffs: np.ndarray | None = None,
    vintage: int | None = OOT_VINTAGE,
) -> pd.DataFrame:
    """Cutoff -> approval_rate / expected_annual_profit trade-off (FR14).

    Story-owner decision (annual volume assumption, recorded per AC #2's
    requirement that assumptions be explicit): the OOT sample IS treated as
    one year's origination volume - the simplest, most transparent reading
    with no extrapolation factor to justify. approved_count in the sample
    becomes the assumed annual approved count directly.

    expected_annual_profit = mean(realized_return_rate over approved loans)
    * avg_loan_amnt * approved_count - i.e. "if every approved loan were of
    size avg_loan_amnt and returned the population's average rate, this is
    the total profit across this year's approved volume." Not a monotonic
    curve (unlike the risk trade-off curve) - raising cutoff shrinks
    approved volume but improves average quality; the optimum trades these
    off.
    """
    population = profit_frame[profit_frame["model_type"] == model_type]
    if vintage is not None:
        population = population[population["vintage"] == vintage]
    if population.empty:
        raise ValueError(f"no rows for model_type={model_type!r}, vintage={vintage!r}")

    scores = population["score"].to_numpy()
    rates = realized_return_rate(
        population["loan_amnt"].to_numpy(),
        population["total_pymnt"].to_numpy(),
        population["recoveries"].to_numpy(),
    )
    total = len(population)

    if cutoffs is None:
        cutoffs = _default_cutoff_grid(scores)
    cutoffs = np.asarray(cutoffs, dtype=float)

    rows = []
    for cutoff in cutoffs:
        approved = scores >= cutoff
        approved_count = int(approved.sum())
        approval_rate = approved_count / total if total else np.nan
        avg_rate = float(rates[approved].mean()) if approved_count else np.nan
        expected_annual_profit = (
            avg_rate * avg_loan_amnt * approved_count if approved_count else 0.0
        )
        rows.append({
            "cutoff": float(cutoff),
            "approval_rate": approval_rate,
            "avg_return_rate": avg_rate,
            "approved_count": approved_count,
            "expected_annual_profit": expected_annual_profit,
        })
    return pd.DataFrame(rows)


def find_optimal_cutoff(curve: pd.DataFrame) -> float:
    """The cutoff maximizing expected_annual_profit (AD-7: pure grid-search
    argmax, no external judgment)."""
    return float(curve.loc[curve["expected_annual_profit"].idxmax(), "cutoff"])
