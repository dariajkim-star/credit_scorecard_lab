"""CAP-9,10 cutoff trade-off simulation and champion/challenger swap-set (FR9, FR10).

Consumes the scored validation frame (AD-3) only - never reloads model
artifacts (models/artifacts/*.joblib) or recomputes predictions. Story 1.7b
already put champion and challenger on one shared Siddiqi PDO scale via
``scorecard.evaluation.generalized_score``, so a single ``score`` cutoff
value is directly comparable across both models (higher score = safer,
grade-1 convention from scorecard/grading.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# --- Analysis population (Story 2.1 decision record) ------------------------
# The scored validation frame mixes two vintages: valid (2014) and oot
# (2015). valid was already used during Epic 1 model selection (grade
# thresholds, PSI baseline), so its bad rate is optimistically biased for a
# forward-looking underwriting decision. oot (2015) approximates unseen
# future applicants, which is what a cutoff/swap-set decision is meant to
# simulate. -> default analysis population is OOT-only; callers may pass
# vintage=None to analyze the full valid+oot population instead.
OOT_VINTAGE: int = 2015


def _filter_population(df: pd.DataFrame, model_type: str, vintage: int | None) -> pd.DataFrame:
    """Rows for a single model_type, optionally restricted to one vintage.

    Raises fail-fast if the filter yields zero rows (unknown model_type, or a
    vintage/dtype mismatch that would otherwise crash later with a cryptic
    numpy/pandas error, or silently propagate an empty result - code review
    finding, same fail-fast convention as binning.py/champion.py/sample_design.py).
    """
    out = df[df["model_type"] == model_type]
    if vintage is not None:
        out = out[out["vintage"] == vintage]
    if out.empty:
        raise ValueError(
            f"no rows for model_type={model_type!r}, vintage={vintage!r} - "
            "check model_type spelling and that vintage matches the frame's dtype"
        )
    if out["score"].isna().any() or out["bad_flag"].isna().any():
        raise ValueError(
            f"population for model_type={model_type!r}, vintage={vintage!r} contains "
            "missing score/bad_flag values - the AD-3 scored frame is expected to be "
            "complete; label/score rows before calling strategy.py"
        )
    return out


def _default_cutoff_grid(scores: np.ndarray, n_points: int = 101) -> np.ndarray:
    """Evenly spaced grid spanning the observed score range.

    Covers every score in the observed population, but by construction the
    top grid point equals max(score), so the single highest-scoring
    applicant is always approved - true 0% approval would require a cutoff
    strictly above max(score), which is outside this grid (see
    test_cutoff_trade_off_curve_covers_full_approval_range).
    """
    lo, hi = float(np.min(scores)), float(np.max(scores))
    return np.linspace(lo, hi, n_points)


def cutoff_trade_off_curve(
    df: pd.DataFrame,
    model_type: str,
    cutoffs: np.ndarray | None = None,
    vintage: int | None = OOT_VINTAGE,
) -> pd.DataFrame:
    """Full-range approval-rate / bad-rate trade-off curve (FR9).

    Approve iff ``score >= cutoff``. ``bad_rate`` is computed within the
    approved population only; a cutoff with zero approvals gets NaN
    (never 0/0). Returns columns: cutoff, approval_rate, bad_rate,
    approved_count.
    """
    population = _filter_population(df, model_type, vintage)
    scores = population["score"].to_numpy()
    bad = population["bad_flag"].to_numpy()
    total = len(population)

    if cutoffs is None:
        cutoffs = _default_cutoff_grid(scores)
    cutoffs = np.asarray(cutoffs, dtype=float)

    rows = []
    for cutoff in cutoffs:
        approved = scores >= cutoff
        approved_count = int(approved.sum())
        approval_rate = approved_count / total if total else np.nan
        bad_rate = float(bad[approved].mean()) if approved_count else np.nan
        rows.append({
            "cutoff": float(cutoff),
            "approval_rate": approval_rate,
            "bad_rate": bad_rate,
            "approved_count": approved_count,
        })
    return pd.DataFrame(rows)


def lookup_cutoff(
    df: pd.DataFrame,
    model_type: str,
    cutoff: float,
    vintage: int | None = OOT_VINTAGE,
) -> dict:
    """Immediate single-cutoff lookup (FR9): approval_rate, bad_rate, approved_count."""
    curve = cutoff_trade_off_curve(df, model_type, cutoffs=np.array([float(cutoff)]), vintage=vintage)
    row = curve.iloc[0]
    return {
        "cutoff": float(row["cutoff"]),
        "approval_rate": float(row["approval_rate"]) if pd.notna(row["approval_rate"]) else None,
        "bad_rate": float(row["bad_rate"]) if pd.notna(row["bad_rate"]) else None,
        "approved_count": int(row["approved_count"]),
    }


def swap_set_table(
    df: pd.DataFrame,
    cutoff: float,
    vintage: int | None = OOT_VINTAGE,
) -> dict:
    """Champion -> challenger swap-set at one shared cutoff (FR10).

    Pivots the long-format AD-3 frame to one row per applicant with
    champion/challenger scores side by side, joined on
    (applicant_id, vintage) - never assumes matching row order between the
    two model_type slices. Ground-truth bad_flag is read from the champion
    rows for all four segments (champion/challenger bad_flag are expected
    to be identical per applicant - see
    test_real_scored_frame_bad_flag_consistent_across_models).

    Returns swap_in (rejected by champion, approved by challenger),
    swap_out (approved by champion, rejected by challenger),
    stable_approved, stable_rejected - each with count and bad_rate, plus
    the total population.
    """
    population = df if vintage is None else df[df["vintage"] == vintage]
    population = population[population["model_type"].isin(["champion", "challenger"])]

    if population.empty:
        raise ValueError(f"no champion/challenger rows for vintage={vintage!r}")
    present_models = set(population["model_type"].unique())
    missing_models = {"champion", "challenger"} - present_models
    if missing_models:
        raise ValueError(
            f"swap_set_table requires both champion and challenger rows, missing: "
            f"{sorted(missing_models)} (vintage={vintage!r})"
        )
    if population["score"].isna().any() or population["bad_flag"].isna().any():
        raise ValueError(
            f"population for vintage={vintage!r} contains missing score/bad_flag values - "
            "the AD-3 scored frame is expected to be complete"
        )
    dup_key = ["applicant_id", "vintage", "model_type"]
    dup_mask = population.duplicated(subset=dup_key, keep=False)
    if dup_mask.any():
        dup_ids = sorted(population.loc[dup_mask, "applicant_id"].unique())
        raise ValueError(
            f"duplicate (applicant_id, vintage, model_type) rows found for "
            f"{len(dup_ids)} applicant(s) (e.g. {dup_ids[:5]}) - each applicant must "
            "have at most one row per model_type per vintage"
        )

    wide = population.pivot(index=["applicant_id", "vintage"], columns="model_type", values=["score", "bad_flag"])
    wide.columns = [f"{value}_{model}" for value, model in wide.columns]
    wide = wide.dropna(subset=["score_champion", "score_challenger"])

    mismatched = wide["bad_flag_champion"] != wide["bad_flag_challenger"]
    if mismatched.any():
        bad_ids = sorted(wide.index[mismatched].get_level_values("applicant_id"))
        raise ValueError(
            f"champion/challenger bad_flag disagree for {mismatched.sum()} applicant(s) "
            f"(e.g. {bad_ids[:5]}) - this violates the frame's shared-label invariant "
            "(see test_real_scored_frame_bad_flag_consistent_across_models); investigate "
            "the scored validation frame build (1.7b) before trusting swap-set results"
        )

    champion_approved = wide["score_champion"] >= cutoff
    challenger_approved = wide["score_challenger"] >= cutoff

    segments = {
        "swap_in": ~champion_approved & challenger_approved,
        "swap_out": champion_approved & ~challenger_approved,
        "stable_approved": champion_approved & challenger_approved,
        "stable_rejected": ~champion_approved & ~challenger_approved,
    }

    def _segment(mask: pd.Series) -> dict:
        count = int(mask.sum())
        bad_rate = float(wide.loc[mask, "bad_flag_champion"].mean()) if count else np.nan
        return {"count": count, "bad_rate": bad_rate if not np.isnan(bad_rate) else None}

    result = {"cutoff": float(cutoff), "population": int(len(wide))}
    result.update({name: _segment(mask) for name, mask in segments.items()})
    return result
