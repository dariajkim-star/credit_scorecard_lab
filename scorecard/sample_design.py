"""CAP-1 표본 설계: 누수 필드 감사, bad/good 라벨, 빈티지 기반 train/valid/OOT 분할.

Input contract: the parquet produced by ``pipelines/01_download.py``
(columns = ``pipelines.loading.USECOLS`` + ``vintage``). This module only
labels and splits; missing/outlier handling is Story 1.3, WOE/variable
selection is Story 1.4.
"""

from __future__ import annotations

import pandas as pd

# --- Leakage audit (FR1) -----------------------------------------------------
# classification: "id" (not a feature), "label_source" (loan_status only),
# "application_time" (feature candidate), "post_origination" (excluded).
# rationale documents why each field is included/excluded from the feature set.
LEAKAGE_AUDIT: list[dict[str, str]] = [
    {"field": "id", "classification": "id", "excluded": "n/a", "rationale": "row identifier, not a predictor"},
    {"field": "issue_d", "classification": "id", "excluded": "n/a", "rationale": "origination date, used for vintage/split only"},
    {"field": "term", "classification": "id", "excluded": "n/a", "rationale": "constant 36 months after Story 1.1 filter"},
    {"field": "vintage", "classification": "id", "excluded": "n/a", "rationale": "derived split key, not a predictor"},
    {"field": "loan_status", "classification": "label_source", "excluded": "n/a", "rationale": "source of bad_flag; never a feature"},
    {"field": "loan_amnt", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "int_rate", "classification": "application_time", "excluded": "yes", "rationale": "conservative exclusion: LC assigns this post-decision, based on the same risk assessment our model aims to replace -> circular with the label"},
    {"field": "grade", "classification": "application_time", "excluded": "yes", "rationale": "conservative exclusion: same reasoning as int_rate (LC's own underwriting outcome)"},
    {"field": "sub_grade", "classification": "application_time", "excluded": "yes", "rationale": "conservative exclusion: same reasoning as grade"},
    {"field": "emp_title", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "emp_length", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "home_ownership", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "annual_inc", "classification": "application_time", "excluded": "no", "rationale": "known at application (self-reported)"},
    {"field": "verification_status", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "purpose", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "dti", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "delinq_2yrs", "classification": "application_time", "excluded": "no", "rationale": "known at application (credit bureau snapshot)"},
    {"field": "fico_range_low", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "fico_range_high", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "inq_last_6mths", "classification": "application_time", "excluded": "no", "rationale": "known at application (credit bureau snapshot)"},
    {"field": "open_acc", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "pub_rec", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "revol_bal", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "revol_util", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "total_acc", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "addr_state", "classification": "application_time", "excluded": "no", "rationale": "known at application"},
    {"field": "recoveries", "classification": "post_origination", "excluded": "yes", "rationale": "only known after default; kept in the frame for Story 2.4 profit calc, excluded from the feature set"},
    {"field": "total_pymnt", "classification": "post_origination", "excluded": "yes", "rationale": "only known at loan closure; kept in the frame for Story 2.4 profit calc, excluded from the feature set"},
    {"field": "last_pymnt_d", "classification": "post_origination", "excluded": "yes", "rationale": "only known at loan closure; used only for the Task 4 performance-window EDA, not a feature"},
]


def audit_columns() -> pd.DataFrame:
    """Return the leakage audit table (AC 1)."""
    return pd.DataFrame(LEAKAGE_AUDIT)


def feature_candidate_columns() -> list[str]:
    """Fields classified application_time and not excluded (candidates for Story 1.4)."""
    return [
        row["field"]
        for row in LEAKAGE_AUDIT
        if row["classification"] == "application_time" and row["excluded"] == "no"
    ]


# --- Label (FR1/NFR8) --------------------------------------------------------
BAD_STATUSES = {"Charged Off", "Default"}
GOOD_STATUSES = {"Fully Paid"}


def make_label(df: pd.DataFrame) -> pd.Series:
    """bad_flag: 1 for bad, 0 for good, <NA> for in-progress statuses (NFR8).

    Nullable Int64 so callers can filter on ``.notna()`` without a separate
    mask, and so the dtype never flips to float64 (the pitfall found in
    Story 1.1's derive_vintage).
    """
    status = df["loan_status"].astype("string")
    label = pd.Series(pd.NA, index=df.index, dtype="Int64")
    label = label.mask(status.isin(BAD_STATUSES), 1)
    label = label.mask(status.isin(GOOD_STATUSES), 0)
    return label


def label_and_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Attach bad_flag and drop in-progress loans (NFR8)."""
    out = df.copy()
    out["bad_flag"] = make_label(out)
    out = out.loc[out["bad_flag"].notna()].reset_index(drop=True)
    return out


# --- Vintage split (FR1) ------------------------------------------------------
# Decision (story-owner call, not specified in SPEC): split train/valid by
# vintage year rather than a random draw, so the split is fully deterministic
# with no RNG dependency. train=2012-2013, valid=2014, OOT=2015 (NFR8 fixed).
TRAIN_VINTAGES = {2012, 2013}
VALID_VINTAGES = {2014}
OOT_VINTAGES = {2015}


def split_by_vintage(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split a labeled frame into train/valid/oot by vintage (AC 3).

    Raises ValueError if any split is empty, or if any input row falls
    outside the known vintage sets - both are sample design failures, not
    silent drops (e.g. if config.VINTAGE_MIN/MAX is widened without updating
    TRAIN/VALID/OOT_VINTAGES here).
    """
    groups = {
        "train": df.loc[df["vintage"].isin(TRAIN_VINTAGES)].reset_index(drop=True),
        "valid": df.loc[df["vintage"].isin(VALID_VINTAGES)].reset_index(drop=True),
        "oot": df.loc[df["vintage"].isin(OOT_VINTAGES)].reset_index(drop=True),
    }
    for name, group in groups.items():
        if len(group) == 0:
            raise ValueError(f"split '{name}' is empty - sample design failure")

    accounted = sum(len(group) for group in groups.values())
    if accounted != len(df):
        unmatched = sorted(df.loc[~df["vintage"].isin(TRAIN_VINTAGES | VALID_VINTAGES | OOT_VINTAGES), "vintage"].unique())
        raise ValueError(
            f"{len(df) - accounted} row(s) have vintage(s) {unmatched} outside "
            "TRAIN/VALID/OOT_VINTAGES - update the split definition or the "
            "upstream vintage filter"
        )
    return groups


def split_summary(groups: dict[str, pd.DataFrame]) -> dict[str, dict[str, float]]:
    """rows + bad_rate per split (AC 3 evidence)."""
    return {
        name: {
            "rows": int(len(group)),
            "bad_rate": float(group["bad_flag"].mean()),
        }
        for name, group in groups.items()
    }


# --- Performance window (AC 4, SPEC open question) ---------------------------
def performance_window_months(df: pd.DataFrame) -> pd.Series:
    """Months between issue_d and last_pymnt_d, nullable Int64.

    EDA input for the Task 4 decision record; not used to change make_label.
    """
    issue = pd.to_datetime(df["issue_d"], format="%b-%Y", errors="coerce")
    last = pd.to_datetime(df["last_pymnt_d"], format="%b-%Y", errors="coerce")
    months = (last.dt.year - issue.dt.year) * 12 + (last.dt.month - issue.dt.month)
    return months.astype("Int64")
