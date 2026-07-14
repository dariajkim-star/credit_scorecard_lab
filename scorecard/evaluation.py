"""CAP-6 3면 평가(AUC/KS/PR-AUC) + CAP-8 PSI + AD-3 scored validation frame.

Input contract: the artifact bundles from Story 1.5 (``{"model", "binners"}``)
and Story 1.6 (``{"model", "calibrator"}``), plus the labeled train/valid/oot
frames from Story 1.2/1.3. All metrics are computed on P(bad), not on the
champion's PDO display score - the score is a monotone decreasing function of
P(bad) (higher score = safer), which would flip the sign of rank-based
metrics if used directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from scorecard.binning import transform_woe
from scorecard.challenger import calibrated_predict_proba
from scorecard.champion import score_formula
from scorecard.grading import _assign_bin, assign_grade, fit_grade_thresholds
from scorecard.preprocessing import parse_percent

# AC1 pass/fail targets (informational only - missing them is not a failure,
# per FR6's "미달 시 원인 분석 문서가 대체 산출물" success criterion).
CHAMPION_OOT_KS_TARGET: float = 0.25
CHALLENGER_OOT_AUC_TARGET: float = 0.70

# FR8 success criterion: score PSI below this is a pass (informational only).
PSI_TARGET: float = 0.1

# AD-3 canonical column order - do not reorder/rename without updating the
# architecture spine.
SCORED_FRAME_COLUMNS: list[str] = [
    "applicant_id", "vintage", "model_type", "score", "pd", "grade",
    "bad_flag", "int_rate", "recoveries", "total_pymnt",
]


def compute_metrics(y_true: np.ndarray, p_bad: np.ndarray) -> dict[str, float]:
    """AUC, KS (scipy ks_2samp, verified pre-story to match the classic
    credit-scoring KS definition), and PR-AUC for one split."""
    from scipy.stats import ks_2samp

    auc = roc_auc_score(y_true, p_bad)
    ks = ks_2samp(p_bad[y_true == 1], p_bad[y_true == 0]).statistic
    pr_auc = average_precision_score(y_true, p_bad)
    return {"auc": float(auc), "ks": float(ks), "pr_auc": float(pr_auc)}


def champion_p_bad(champion_bundle: dict, df: pd.DataFrame, variables: list[str]) -> np.ndarray:
    """P(bad) from the champion bundle - WOE transform, then predict_proba."""
    woe = transform_woe(df, champion_bundle["binners"])
    return champion_bundle["model"].predict_proba(woe[variables].astype(float).to_numpy())[:, 1]


def challenger_p_bad(challenger_bundle: dict, df: pd.DataFrame, variables: list[str]) -> np.ndarray:
    """P(bad) from the challenger bundle - raw values, calibrated."""
    return calibrated_predict_proba(challenger_bundle["model"], challenger_bundle["calibrator"], df, variables)


def evaluation_table(
    splits: dict[str, pd.DataFrame],
    champion_bundle: dict,
    champion_variables: list[str],
    challenger_bundle: dict,
    challenger_variables: list[str],
) -> pd.DataFrame:
    """3-face (train/valid/oot) x 2-model comparison table (FR6).

    Includes an informational pass/fail flag against the OOT targets;
    missing a target does NOT raise - it's a documented, non-failing outcome
    per the story's success criteria.
    """
    rows = []
    for split_name, df in splits.items():
        y_true = df["bad_flag"].to_numpy(dtype=int)

        champ_p = champion_p_bad(champion_bundle, df, champion_variables)
        champ_metrics = compute_metrics(y_true, champ_p)
        champ_metrics["model"] = "champion"
        champ_metrics["split"] = split_name
        rows.append(champ_metrics)

        chall_p = challenger_p_bad(challenger_bundle, df, challenger_variables)
        chall_metrics = compute_metrics(y_true, chall_p)
        chall_metrics["model"] = "challenger"
        chall_metrics["split"] = split_name
        rows.append(chall_metrics)

    table = pd.DataFrame(rows)[["model", "split", "auc", "ks", "pr_auc"]]

    def _target_met(row: pd.Series) -> bool | None:
        if row["split"] != "oot":
            return None
        if row["model"] == "champion":
            return bool(row["ks"] >= CHAMPION_OOT_KS_TARGET)
        return bool(row["auc"] >= CHALLENGER_OOT_AUC_TARGET)

    table["oot_target_met"] = table.apply(_target_met, axis=1)
    return table


# --- Generalized score (resolves Story 1.7a's champion/challenger scale question) ---
_P_CLIP_EPS: float = 1e-9


def generalized_score(p_bad: np.ndarray) -> np.ndarray:
    """P(bad) -> Siddiqi PDO score, on the SAME scale for champion and challenger.

    logit_bad = ln(p/(1-p)); score = score_formula(logit_bad) (Story 1.5's
    PDO/BASE_SCORE/BASE_ODDS constants). For the champion this is
    mathematically equivalent to score_formula(decision_function(x)) - up to
    floating point - since predict_proba = sigmoid(decision_function). Using
    this one function for both models is what makes a single ``score``
    column meaningful across model_type in the scored validation frame.
    """
    p = np.clip(np.asarray(p_bad, dtype=float), _P_CLIP_EPS, 1 - _P_CLIP_EPS)
    logit_bad = np.log(p / (1 - p))
    return score_formula(logit_bad)


# --- PSI (FR8) ----------------------------------------------------------------
def population_stability_index(expected: np.ndarray, actual: np.ndarray, n_buckets: int = 10) -> float:
    """PSI of ``actual`` vs ``expected``, bucketed on EXPECTED's quantile edges.

    Both series are binned on the SAME edges (fit on ``expected``, reusing
    scorecard.grading's bucketing helpers) - never independently re-quantiled,
    which is exactly the bug Story 1.6's code review found in
    calibration_curve_data (comparing unrelated ranges after independent
    binning). Bucket proportions of zero are clipped to avoid log(0).

    Low-cardinality/heavily skewed ``expected`` inputs (e.g. zero-inflated
    counts like inq_last_6mths, which Story 1.3 left uncapped) can make
    quantile edges collapse to far fewer bins than requested, or even a
    single bin, silently understating any real distributional shift -
    quantile bucketing simply cannot resolve a variable dominated by one
    repeated value. When ``expected`` has at most ``n_buckets`` distinct
    values, this bucket-by-EXACT-VALUE instead of by quantile range, which
    is the standard PSI treatment for discrete/categorical-like variables.
    If ``expected`` has no variation at all, PSI is 0.0 (nothing to compare).

    NaN values (this project deliberately leaves missing values unimputed,
    per FR2) are dropped before bucketing: ``np.quantile`` propagates NaN to
    every quantile level, which previously made ANY variable with missing
    values silently collapse to a fake "0 drift" result instead of raising
    or comparing the real distribution - a masked-failure bug caught by
    running this against real revol_util data (which has missing values).
    """
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    expected = expected[~np.isnan(expected)]
    actual = actual[~np.isnan(actual)]
    if len(expected) == 0:
        return 0.0
    distinct_values = np.unique(expected)

    if len(distinct_values) <= 1:
        return 0.0

    if len(distinct_values) <= n_buckets:
        # discrete: bucket by exact value (present in expected), not quantile range
        expected_bins = np.searchsorted(distinct_values, expected)
        actual_bins = np.searchsorted(distinct_values, actual, side="left")
        actual_bins = np.clip(actual_bins, 0, len(distinct_values) - 1)
        n_bins = len(distinct_values)
    else:
        edges = None
        for effective_buckets in range(n_buckets, 1, -1):
            try:
                edges = fit_grade_thresholds(expected, n_grades=effective_buckets)
                if len(edges) - 1 >= 2:
                    break
            except ValueError:
                continue
        if edges is None or len(edges) - 1 < 2:
            return 0.0
        expected_bins = _assign_bin(expected, edges)
        actual_bins = _assign_bin(actual, edges)
        n_bins = len(edges) - 1

    eps = 1e-6
    expected_pct = pd.Series(expected_bins).value_counts(normalize=True).reindex(range(n_bins), fill_value=0.0).sort_index()
    actual_pct = pd.Series(actual_bins).value_counts(normalize=True).reindex(range(n_bins), fill_value=0.0).sort_index()
    expected_pct = expected_pct.clip(lower=eps)
    actual_pct = actual_pct.clip(lower=eps)

    return float(((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)).sum())


def variable_psi(train_df: pd.DataFrame, oot_df: pd.DataFrame, numeric_columns: list[str], n_buckets: int = 10) -> pd.DataFrame:
    """PSI per numeric variable, train (expected) vs OOT (actual)."""
    rows = []
    for col in numeric_columns:
        expected = train_df[col].astype(float).to_numpy()
        actual = oot_df[col].astype(float).to_numpy()
        rows.append({"variable": col, "psi": population_stability_index(expected, actual, n_buckets)})
    return pd.DataFrame(rows)


# --- Scored validation frame (AD-3) --------------------------------------------
def build_scored_frame(
    splits: dict[str, pd.DataFrame],
    champion_bundle: dict,
    champion_variables: list[str],
    champion_grade_edges: np.ndarray,
    challenger_bundle: dict,
    challenger_variables: list[str],
    challenger_grade_edges: np.ndarray,
) -> pd.DataFrame:
    """Build the canonical scored validation/OOT frame (AD-3 fixed schema).

    ``splits`` should contain only valid/oot (not train - the models were
    fit on train, so it is not part of the validation frame). One row per
    (applicant, model_type) - long format, model_type in {"champion",
    "challenger"}. ``int_rate`` is parsed here from its raw "45.3%" string
    (Story 1.3 only parsed revol_util; int_rate was never a feature so it
    was left untouched until this frame needs it for Story 2.4's profit calc).
    """
    frames = []
    for _, df in splits.items():
        int_rate = parse_percent(df["int_rate"]).astype(float).to_numpy()

        champ_p = champion_p_bad(champion_bundle, df, champion_variables)
        champ_score = generalized_score(champ_p)
        champ_grade = assign_grade(champ_score, champion_grade_edges)
        frames.append(pd.DataFrame({
            "applicant_id": df["id"].to_numpy(),
            "vintage": df["vintage"].to_numpy(),
            "model_type": "champion",
            "score": champ_score,
            "pd": champ_p,
            "grade": champ_grade,
            "bad_flag": df["bad_flag"].to_numpy(dtype=int),
            "int_rate": int_rate,
            "recoveries": df["recoveries"].astype(float).to_numpy(),
            "total_pymnt": df["total_pymnt"].astype(float).to_numpy(),
        }))

        chall_p = challenger_p_bad(challenger_bundle, df, challenger_variables)
        chall_score = generalized_score(chall_p)
        chall_grade = assign_grade(chall_score, challenger_grade_edges)
        frames.append(pd.DataFrame({
            "applicant_id": df["id"].to_numpy(),
            "vintage": df["vintage"].to_numpy(),
            "model_type": "challenger",
            "score": chall_score,
            "pd": chall_p,
            "grade": chall_grade,
            "bad_flag": df["bad_flag"].to_numpy(dtype=int),
            "int_rate": int_rate,
            "recoveries": df["recoveries"].astype(float).to_numpy(),
            "total_pymnt": df["total_pymnt"].astype(float).to_numpy(),
        }))

    return pd.concat(frames, ignore_index=True)[SCORED_FRAME_COLUMNS]
