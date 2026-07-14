"""Tests for grade mapping and monotonicity enforcement (Story 1.7a, synthetic data only)."""

from __future__ import annotations

import numpy as np
import pytest

from scorecard.grading import (
    assign_grade,
    enforce_monotonic_grades,
    finalize_manifest,
    fit_grade_thresholds,
    validate_monotonic,
)


def _clean_signal(n=5000, seed=0):
    """Score higher = safer; bad rate strictly decreases with score."""
    rng = np.random.default_rng(seed)
    score = rng.uniform(500, 700, n)
    p_bad = 1 / (1 + np.exp((score - 600) / 20))
    bad = (rng.random(n) < p_bad).astype(int)
    return score, bad


# --- fit_grade_thresholds / assign_grade --------------------------------------


def test_fit_grade_thresholds_returns_ascending_edges():
    score, _ = _clean_signal()
    edges = fit_grade_thresholds(score, n_grades=10)
    assert len(edges) >= 2
    assert (np.diff(edges) > 0).all()


def test_assign_grade_highest_score_gets_grade_1():
    score, _ = _clean_signal()
    edges = fit_grade_thresholds(score, n_grades=10)
    grades = assign_grade(score, edges)
    top_score_idx = np.argmax(score)
    assert grades[top_score_idx] == 1


def test_assign_grade_lowest_score_gets_highest_grade_number():
    score, _ = _clean_signal()
    edges = fit_grade_thresholds(score, n_grades=10)
    grades = assign_grade(score, edges)
    n_bins = len(edges) - 1
    bottom_score_idx = np.argmin(score)
    assert grades[bottom_score_idx] == n_bins


def test_assign_grade_handles_out_of_range_scores():
    score, _ = _clean_signal()
    edges = fit_grade_thresholds(score, n_grades=10)
    extreme = np.array([-1000.0, 1000.0])
    grades = assign_grade(extreme, edges)
    n_bins = len(edges) - 1
    assert grades[0] == n_bins  # far below range -> worst grade
    assert grades[1] == 1  # far above range -> best grade


# --- enforce_monotonic_grades / validate_monotonic ----------------------------


def test_enforce_monotonic_grades_clean_signal_keeps_all_grades():
    score, bad = _clean_signal()
    edges, table = enforce_monotonic_grades(score, bad, n_grades=10)
    assert len(edges) - 1 == 10
    assert validate_monotonic(table)


def test_enforce_monotonic_grades_merges_on_noisy_input():
    # Pure noise: bad rate has no real relationship with score, so raw
    # equal-frequency bins are very likely non-monotonic and must be merged.
    rng = np.random.default_rng(1)
    n = 300
    score = rng.uniform(0, 100, n)
    bad = rng.integers(0, 2, n)
    edges, table = enforce_monotonic_grades(score, bad, n_grades=10)
    assert validate_monotonic(table)
    assert (len(edges) - 1) <= 10


def test_enforce_monotonic_grades_bad_rate_actually_increases_with_grade():
    score, bad = _clean_signal()
    _, table = enforce_monotonic_grades(score, bad, n_grades=10)
    rates = table.sort_values("grade")["bad_rate"].to_numpy()
    assert rates[0] < rates[-1]  # grade 1 (safest) has materially lower bad rate than the worst grade


def test_validate_monotonic_detects_violation():
    import pandas as pd

    bad_table = pd.DataFrame({"grade": [1, 2, 3], "bad_rate": [0.05, 0.20, 0.10]})
    assert not validate_monotonic(bad_table)

    good_table = pd.DataFrame({"grade": [1, 2, 3], "bad_rate": [0.05, 0.10, 0.20]})
    assert validate_monotonic(good_table)


# --- finalize_manifest (AD-1 completion) --------------------------------------


def test_finalize_manifest_adds_grade_thresholds_preserving_existing_keys(tmp_path):
    import json

    manifest_path = tmp_path / "champion_manifest.json"
    manifest_path.write_text(
        json.dumps({"model_type": "champion", "model_version": "champion-1.0.0", "pdo": 20.0}),
        encoding="ascii",
    )
    edges = np.array([496.4, 526.1, 600.9])
    finalize_manifest(manifest_path, edges)

    result = json.loads(manifest_path.read_text(encoding="ascii"))
    assert result["model_type"] == "champion"  # existing keys preserved
    assert result["pdo"] == 20.0
    assert result["grade_thresholds"] == pytest.approx([496.4, 526.1, 600.9])


def test_finalize_manifest_overwrites_existing_grade_thresholds(tmp_path):
    import json

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"grade_thresholds": [1.0, 2.0]}), encoding="ascii")
    finalize_manifest(manifest_path, np.array([9.0, 10.0, 11.0]))
    result = json.loads(manifest_path.read_text(encoding="ascii"))
    assert result["grade_thresholds"] == pytest.approx([9.0, 10.0, 11.0])
