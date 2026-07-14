"""CAP-2 결측·이상치 전처리: 퍼센트 문자열 파싱, 결측 방치(대치 금지), 이상치 캡핑.

Input contract: the labeled/split output of ``scorecard.sample_design``
(``label_and_filter`` + ``split_by_vintage``). Missing values are NEVER
imputed here - FR2 requires they remain missing so Story 1.4's optbinning
can bin them separately. Only numeric feature candidates are capped;
categorical columns are passed through untouched.
"""

from __future__ import annotations

import pandas as pd

from scorecard.sample_design import feature_candidate_columns

# --- Column classification (Task 2) ------------------------------------------
# Split of scorecard.sample_design.feature_candidate_columns() (21 fields) into
# numeric (capping candidates) and categorical (pass-through, no-op here).
NUMERIC_COLUMNS: list[str] = [
    "loan_amnt",
    "annual_inc",
    "dti",
    "delinq_2yrs",
    "fico_range_low",
    "fico_range_high",
    "inq_last_6mths",
    "open_acc",
    "pub_rec",
    "revol_bal",
    "revol_util",
    "total_acc",
]
CATEGORICAL_COLUMNS: list[str] = [
    "emp_title",
    "emp_length",
    "home_ownership",
    "verification_status",
    "purpose",
    "addr_state",
]


def _assert_matches_feature_candidates() -> None:
    """Guard against this module's column split drifting from Story 1.2's audit."""
    expected = set(feature_candidate_columns())
    actual = set(NUMERIC_COLUMNS) | set(CATEGORICAL_COLUMNS)
    if actual != expected:
        raise AssertionError(
            "NUMERIC_COLUMNS + CATEGORICAL_COLUMNS no longer matches "
            f"scorecard.sample_design.feature_candidate_columns(): "
            f"missing={expected - actual}, extra={actual - expected}"
        )


_assert_matches_feature_candidates()


# --- Task 1: percent-string parsing ------------------------------------------
def parse_percent(series: pd.Series) -> pd.Series:
    """Parse "45.3%" -> 45.3 (percent scale kept, not divided by 100).

    Returns nullable ``Float64`` so a parse failure or missing value stays
    NaN/NA rather than silently flipping dtype (the pitfall found in Story
    1.1's derive_vintage) - this is never imputation, values that don't parse
    simply remain missing.
    """
    stripped = series.astype("string").str.strip().str.rstrip("%")
    return pd.to_numeric(stripped, errors="coerce").astype("Float64")


def coerce_percent_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Apply parse_percent to the given columns (e.g. ["revol_util"])."""
    out = df.copy()
    for col in columns:
        out[col] = parse_percent(out[col])
    return out


# --- Task 3: missing value reporting (no imputation) -------------------------
def missing_summary(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Missing count/rate per column - reporting only, never fills anything."""
    rows = []
    for col in columns:
        n_missing = int(df[col].isna().sum())
        rows.append(
            {
                "field": col,
                "n_missing": n_missing,
                "missing_rate": n_missing / len(df) if len(df) else 0.0,
            }
        )
    return pd.DataFrame(rows)


# --- Task 4: outlier capping (fit on train only) -----------------------------
def fit_caps(
    train_df: pd.DataFrame, columns: list[str], lower_q: float = 0.01, upper_q: float = 0.99
) -> dict[str, tuple[float, float]]:
    """Compute (lower, upper) percentile caps from the TRAIN split only.

    Fitting on train and applying the same thresholds to valid/oot mirrors
    the fit-on-train/transform pattern Story 1.4's WOE binning will use, and
    avoids leaking valid/oot distribution info into the cap boundaries.
    Percentiles ignore NaN (pandas default), so missing values never affect
    the cap and are never touched by it.
    """
    caps: dict[str, tuple[float, float]] = {}
    for col in columns:
        lo = train_df[col].quantile(lower_q)
        hi = train_df[col].quantile(upper_q)
        caps[col] = (float(lo), float(hi))
    return caps


def apply_caps(df: pd.DataFrame, caps: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """Clip each column to its fitted [lower, upper] cap; NaN stays NaN.

    Never imputes: ``Series.clip`` passes NaN through untouched, so a value
    that was missing before capping is still missing after.
    """
    out = df.copy()
    for col, (lo, hi) in caps.items():
        out[col] = out[col].clip(lower=lo, upper=hi)
    return out


# --- Task 5: before/after distribution report --------------------------------
def distribution_report(before_df: pd.DataFrame, after_df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Per-column min/max/mean/n_missing, before vs after (AC 3 evidence)."""
    rows = []
    for col in columns:
        rows.append(
            {
                "field": col,
                "min_before": before_df[col].min(),
                "min_after": after_df[col].min(),
                "max_before": before_df[col].max(),
                "max_after": after_df[col].max(),
                "mean_before": before_df[col].mean(),
                "mean_after": after_df[col].mean(),
                "n_missing_before": int(before_df[col].isna().sum()),
                "n_missing_after": int(after_df[col].isna().sum()),
            }
        )
    return pd.DataFrame(rows)
