"""CAP-6 3면 평가(AUC/KS/PR-AUC). PSI(CAP-8) is Story 1.7b.

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

# AC1 pass/fail targets (informational only - missing them is not a failure,
# per FR6's "미달 시 원인 분석 문서가 대체 산출물" success criterion).
CHAMPION_OOT_KS_TARGET: float = 0.25
CHALLENGER_OOT_AUC_TARGET: float = 0.70


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
