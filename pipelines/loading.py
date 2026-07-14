"""Lending Club raw-load column contract and vintage/term filtering.

Pure, importable helpers so the transform logic is unit-testable WITHOUT the
1.6GB download or Kaggle credentials. ``pipelines/01_download.py`` is a thin CLI
wrapper around these functions.

Memory strategy (stack.md risk): read the raw CSV with an explicit ``usecols``
subset + ``dtype`` map, then filter to 2012-2015 vintages / 36-month term before
anything else, and persist as parquet.
"""

from __future__ import annotations

import pandas as pd

from scorecard.config import TERM_MONTHS, VINTAGE_MAX, VINTAGE_MIN

# Columns kept at load time. Deliberately broad: includes fields later stories
# need (leakage audit in 1.2 will drop post-origination ones) so we never have
# to re-download. Keep ASCII (NFR6).
USECOLS: list[str] = [
    # identifiers / timing
    "id",
    "issue_d",
    "term",
    "loan_status",
    # application-time features (candidate predictors)
    "loan_amnt",
    "int_rate",
    "grade",
    "sub_grade",
    "emp_title",
    "emp_length",
    "home_ownership",
    "annual_inc",
    "verification_status",
    "purpose",
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
    "addr_state",
    # outcome / profit fields (used by later stories: label, profit cutoff)
    "recoveries",
    "total_pymnt",
    "last_pymnt_d",
]

# Explicit dtypes to curb memory. Numeric coercion of messy cols (int_rate has
# a trailing '%', revol_util too) is handled downstream in Story 1.3; here we
# read them as string to load safely.
DTYPES: dict[str, str] = {
    "id": "string",
    "term": "string",
    "loan_status": "category",
    "grade": "category",
    "sub_grade": "category",
    "emp_title": "string",
    "emp_length": "category",
    "home_ownership": "category",
    "verification_status": "category",
    "purpose": "category",
    "addr_state": "category",
    "int_rate": "string",
    "revol_util": "string",
}


def derive_vintage(issue_d: pd.Series) -> pd.Series:
    """Parse the origination year from Lending Club's ``issue_d`` ("Dec-2015").

    Returns nullable ``Int64`` so the dtype is stable whether or not any rows
    fail to parse (plain ``.dt.year`` flips int32 -> float64 on the first NaT,
    which would leak a float vintage column into the saved parquet).
    """
    parsed = pd.to_datetime(issue_d, format="%b-%Y", errors="coerce")
    return parsed.dt.year.astype("Int64")


def parse_term_months(term: pd.Series) -> pd.Series:
    """Extract the integer month count from ``term`` (" 36 months")."""
    return (
        term.astype("string")
        .str.extract(r"(\d+)", expand=False)
        .astype("Int64")
    )


def filter_accepted(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only 2012-2015 vintages and the 36-month term (NFR8).

    Adds a numeric ``vintage`` column and returns a filtered copy.
    """
    out = df.copy()
    out["vintage"] = derive_vintage(out["issue_d"])
    term_months = parse_term_months(out["term"])

    mask = (
        out["vintage"].between(VINTAGE_MIN, VINTAGE_MAX)
        & (term_months == TERM_MONTHS)
    )
    return out.loc[mask].reset_index(drop=True)


def summarize(df: pd.DataFrame) -> dict:
    """Small, log-friendly summary of the filtered frame (AC 1 evidence)."""
    return {
        "rows": int(len(df)),
        "vintage_counts": {
            int(k): int(v) for k, v in df["vintage"].value_counts().sort_index().items()
        },
        "term_values": sorted(df["term"].dropna().unique().tolist()),
    }
