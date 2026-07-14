"""CAP-7 등급 매핑: 점수 -> 1~n등급, 단조 부도율 강제 (FR7).

Grade 1 = highest score (safest), grade n = lowest score (riskiest) - the
convention fixed by API_SPEC.md's ``/v1/grades`` example
(``grade:1, score_min:720``). Boundaries are fit on TRAIN only (same
fit-on-train principle as Stories 1.3/1.4/1.6) via equal-frequency
quantiles, then adjacent grades are merged until the bad rate is fully
monotonic - the final grade count may be less than the requested
``n_grades``, which is expected, not a failure (FR7's success criterion is
monotonicity, not a fixed count).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _bin_edges_open(edges: np.ndarray) -> np.ndarray:
    """Open-ended outer edges so future (e.g. serving-time) scores outside
    the observed train range still fall into the extreme bin."""
    open_edges = edges.copy()
    open_edges[0] = -np.inf
    open_edges[-1] = np.inf
    return open_edges


def _assign_bin(scores: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """0-indexed ascending-score bin index (0 = lowest score)."""
    open_edges = _bin_edges_open(np.asarray(edges, dtype=float))
    codes = pd.cut(pd.Series(scores, dtype=float), bins=open_edges, include_lowest=True, labels=False)
    return codes.to_numpy()


def fit_grade_thresholds(train_scores: np.ndarray, n_grades: int = 10) -> np.ndarray:
    """Equal-frequency score-quantile edges from TRAIN (ascending, length n_grades+1)."""
    train_scores = np.asarray(train_scores, dtype=float)
    edges = np.unique(np.quantile(train_scores, np.linspace(0, 1, n_grades + 1)))
    if len(edges) < 2:
        raise ValueError("train_scores has insufficient variation to form grade bins")
    return edges


def assign_grade(scores: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Map scores to grades (1 = highest score / safest) using fitted edges."""
    edges = np.asarray(edges, dtype=float)
    n_bins = len(edges) - 1
    bin_idx = _assign_bin(scores, edges)
    return (n_bins - bin_idx).astype(int)


def enforce_monotonic_grades(
    train_scores: np.ndarray, train_bad_flag: np.ndarray, n_grades: int = 10
) -> tuple[np.ndarray, pd.DataFrame]:
    """Fit initial equal-frequency grades, then merge adjacent grades until
    the bad rate is non-decreasing from grade 1 to the highest grade number.

    Returns (final edges, per-grade count/bad_rate table). The final number
    of grades may be fewer than ``n_grades`` after merging - expected.
    """
    edges = fit_grade_thresholds(train_scores, n_grades)
    train_scores = np.asarray(train_scores, dtype=float)
    train_bad_flag = np.asarray(train_bad_flag, dtype=int)

    while len(edges) > 2:
        bin_idx = _assign_bin(train_scores, edges)
        bad_rates = pd.Series(train_bad_flag).groupby(bin_idx).mean().sort_index().to_numpy()
        # ascending bin_idx = ascending score = should be non-increasing bad rate
        violations = np.where(np.diff(bad_rates) > 0)[0]
        if len(violations) == 0:
            break
        edges = np.delete(edges, int(violations[0]) + 1)

    grade = assign_grade(train_scores, edges)
    table = (
        pd.DataFrame({"grade": grade, "bad": train_bad_flag})
        .groupby("grade")["bad"]
        .agg(["count", "mean"])
        .rename(columns={"mean": "bad_rate"})
        .reset_index()
        .sort_values("grade")
        .reset_index(drop=True)
    )
    return edges, table


def validate_monotonic(grade_bad_rate_table: pd.DataFrame) -> bool:
    """True iff bad_rate is non-decreasing from grade 1 upward (FR7)."""
    rates = grade_bad_rate_table.sort_values("grade")["bad_rate"].to_numpy()
    return bool(np.all(np.diff(rates) >= 0))
