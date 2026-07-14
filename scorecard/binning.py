"""CAP-3 WOE/IV 비닝과 변수선정 (AD-2 단일 소스).

This module is the ONLY place WOE transformation logic lives (AD-2
train/serve parity): pipeline scripts and app/loader.py must both import
from here; re-implementing WOE anywhere else is forbidden.

Spike findings baked into this implementation (Story 1.4 Task 1):
- optbinning 0.21 accepts nullable Float64/string inputs directly.
- ``transform`` defaults ``metric_missing=0`` which silently maps missing
  values to WOE 0 even when the Missing bin is informative - every transform
  call here passes ``metric_missing="empirical"`` so the fitted Missing-bin
  WOE is used (FR2's "missing as its own bin" principle end-to-end).
- IV is read from ``binning_table.build()`` Totals row.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from optbinning import OptimalBinning

from scorecard.preprocessing import CATEGORICAL_COLUMNS, NUMERIC_COLUMNS

# Free-text, high-cardinality - not binnable as a regular categorical.
# Deriving features from it is Story 3.2 (consultant kick #3).
BINNING_EXCLUDED_COLUMNS: list[str] = ["emp_title"]

BINNING_CANDIDATES: list[str] = [
    c for c in NUMERIC_COLUMNS + CATEGORICAL_COLUMNS if c not in BINNING_EXCLUDED_COLUMNS
]

# Selection thresholds (industry practice: IV < 0.02 = unpredictive).
IV_MIN: float = 0.02
CORR_MAX: float = 0.7


def fit_binning(
    train_df: pd.DataFrame, y: pd.Series, variables: list[str] | None = None
) -> dict[str, OptimalBinning]:
    """Fit one OptimalBinning per variable on the TRAIN split only.

    Numeric variables get a monotonic event-rate constraint
    (``auto_asc_desc``); categoricals use optbinning's categorical solver.
    """
    if variables is None:
        variables = BINNING_CANDIDATES
    y_arr = pd.Series(y).astype("Int64").to_numpy(dtype=int, na_value=-1)
    if (y_arr == -1).any():
        raise ValueError("y contains missing values - label rows before binning")

    binners: dict[str, OptimalBinning] = {}
    for var in variables:
        if var in NUMERIC_COLUMNS:
            ob = OptimalBinning(name=var, dtype="numerical", monotonic_trend="auto_asc_desc")
        else:
            ob = OptimalBinning(name=var, dtype="categorical")
        ob.fit(train_df[var], y_arr)
        binners[var] = ob
    return binners


def transform_woe(df: pd.DataFrame, binners: dict[str, OptimalBinning]) -> pd.DataFrame:
    """WOE-transform every fitted variable; the single AD-2 transform path.

    ``metric_missing="empirical"``/``metric_special="empirical"`` ensure
    missing/special rows get their fitted bin WOE instead of the silent 0
    default (spike finding).
    """
    out = pd.DataFrame(index=df.index)
    for var, ob in binners.items():
        out[var] = ob.transform(
            df[var], metric="woe", metric_missing="empirical", metric_special="empirical"
        )
    return out


def iv_table(binners: dict[str, OptimalBinning]) -> pd.DataFrame:
    """Per-variable IV, descending (FR3 deliverable)."""
    rows = [
        {"variable": var, "iv": float(ob.binning_table.build().loc["Totals", "IV"])}
        for var, ob in binners.items()
    ]
    return pd.DataFrame(rows).sort_values("iv", ascending=False).reset_index(drop=True)


def bin_edges(binners: dict[str, OptimalBinning]) -> dict[str, list]:
    """Numeric split points per variable - feeds AD-1's woe_bin_edges manifest key (Story 1.5)."""
    edges: dict[str, list] = {}
    for var, ob in binners.items():
        if var in NUMERIC_COLUMNS:
            edges[var] = [float(s) for s in ob.splits]
        else:
            edges[var] = [list(group) for group in ob.splits]
    return edges


def select_variables(
    woe_df: pd.DataFrame,
    iv_tbl: pd.DataFrame,
    iv_min: float = IV_MIN,
    corr_max: float = CORR_MAX,
) -> tuple[list[str], pd.DataFrame]:
    """IV filter then greedy correlation pruning on WOE values (FR3/AC2).

    Walking variables in descending IV order, drop any variable whose
    absolute pairwise correlation with an already-kept variable exceeds
    ``corr_max`` (the lower-IV member of each offending pair is the one
    dropped). Returns (selected variables, decision table with reasons).
    """
    decisions: list[dict[str, object]] = []
    passed_iv: list[str] = []
    for _, row in iv_tbl.iterrows():
        var, iv = str(row["variable"]), float(row["iv"])
        if iv < iv_min:
            decisions.append({"variable": var, "iv": iv, "selected": False, "reason": f"IV {iv:.4f} < {iv_min}"})
        else:
            passed_iv.append(var)

    corr = woe_df[passed_iv].corr().abs()
    selected: list[str] = []
    for var in passed_iv:  # already in descending-IV order
        clash = next((kept for kept in selected if corr.loc[var, kept] > corr_max), None)
        if clash is None:
            selected.append(var)
            decisions.append({"variable": var, "iv": float(iv_tbl.set_index("variable").loc[var, "iv"]), "selected": True, "reason": "passed IV and correlation filters"})
        else:
            decisions.append({"variable": var, "iv": float(iv_tbl.set_index("variable").loc[var, "iv"]), "selected": False, "reason": f"|corr|={corr.loc[var, clash]:.3f} with higher-IV '{clash}' > {corr_max}"})

    if len(selected) > 1:
        final_corr = woe_df[selected].corr().abs()
        off_diagonal = final_corr.where(~np.eye(len(selected), dtype=bool))
        max_offdiag = float(off_diagonal.max().max())
        if max_offdiag > corr_max:
            raise AssertionError(f"post-selection max |corr| {max_offdiag:.3f} > {corr_max}")

    return selected, pd.DataFrame(decisions)
