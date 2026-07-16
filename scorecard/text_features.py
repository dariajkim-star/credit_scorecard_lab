"""CAP-16 emp_title text-derived feature (FR16, consultant kick #3).

Verifies whether a NON-financial free-text field (job title) carries credit
signal, WITHOUT sophisticated NLP (AC: lowercase + strip punctuation +
top-frequency category mapping only). A negative result is a valid outcome -
the point is to have actually checked (AC #2), so nothing here tries to
manufacture signal via stemming, embeddings, or keyword grouping.

WOE/IV are NOT computed here: the category column is fed to the single AD-2
binning path (scorecard.binning.fit_binning categorical solver + iv_table).
This module only does the deterministic text -> coarse-category mapping.
"""

from __future__ import annotations

import re

import pandas as pd

MISSING_CATEGORY: str = "MISSING"
OTHER_CATEGORY: str = "OTHER"

# Keep letters, digits, and spaces only; everything else becomes a space. No
# stemming / stopword lists / synonym merging (AC: avoid sophisticated NLP).
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_MULTISPACE = re.compile(r"\s+")


def clean_emp_title(series: pd.Series) -> pd.Series:
    """Lowercase, strip punctuation to spaces, collapse whitespace, trim.

    Output is StringDtype: input NaN comes out as pd.NA (not np.nan), and an
    entry that cleans down to an empty string - all punctuation, blanks, or
    entirely non-ASCII text, since only [a-z0-9 ] survives - also becomes
    pd.NA so it lands in MISSING downstream rather than a bogus empty
    category. On Lending Club data titles are English, so the non-ASCII
    collapse is a documented non-event, not a handled population (code
    review: docstring made precise).
    """
    cleaned = (
        series.astype("string")
        .str.lower()
        .str.replace(_NON_ALNUM, " ", regex=True)
        .str.replace(_MULTISPACE, " ", regex=True)
        .str.strip()
    )
    # mask-on-length instead of replace("", NA): Series.replace semantics for
    # StringDtype have shifted across pandas 2.x; this pins the MISSING
    # boundary version-robustly (code review finding).
    return cleaned.mask(cleaned.str.len() == 0)


def fit_top_titles(train_cleaned: pd.Series, k: int = 20) -> list[str]:
    """The k most frequent cleaned titles in the TRAIN split (leakage
    boundary: frequencies are learned on train only, then applied unchanged
    to valid/oot - same fit-on-train convention as binning).

    Deterministic tie-break (code review finding: value_counts does not
    contractually order ties, and this list is a persisted modeling artifact):
    count descending, then title ascending.
    """
    if k < 0:
        raise ValueError(f"k must be >= 0, got {k}")  # head(-k) would misbehave
    counts = train_cleaned.dropna().value_counts()
    ordered = counts.reset_index()
    ordered.columns = ["title", "count"]
    ordered = ordered.sort_values(["count", "title"], ascending=[False, True])
    return list(ordered.head(k)["title"])


def map_emp_title_category(cleaned: pd.Series, top_titles: list[str]) -> pd.Series:
    """Map each cleaned title to one of: a top-K title (its own category),
    OTHER (a real but non-top title), or MISSING (null/empty). Pure mapping -
    top_titles is passed in, never recomputed here (leakage boundary).

    Sentinel collision is impossible from fit_top_titles output (cleaned
    titles are lowercase, sentinels uppercase) - but top_titles may come from
    anywhere, so the invariant is enforced, not assumed (code review).
    """
    bad = {MISSING_CATEGORY, OTHER_CATEGORY} & set(top_titles)
    if bad or any(pd.isna(t) for t in top_titles):
        raise ValueError(
            f"top_titles must not contain the sentinels {sorted(bad)} or NA values"
        )
    top = set(top_titles)
    out = pd.Series(OTHER_CATEGORY, index=cleaned.index, dtype="object")
    out = out.mask(cleaned.isna(), MISSING_CATEGORY)
    in_top = cleaned.isin(top)  # NaN -> False, already covered by MISSING above
    out = out.where(~in_top, cleaned)
    return out.astype("string")


def derive_emp_title_category(
    df: pd.DataFrame, top_titles: list[str], source: str = "emp_title"
) -> pd.Series:
    """Convenience: clean ``df[source]`` then map to the coarse category using
    a pre-fitted ``top_titles``. Returned Series is ready to hand to
    binning.fit_binning as a categorical variable."""
    if source not in df.columns:
        raise KeyError(
            f"{source!r} column not found in frame - expected the raw accepted "
            "parquet's emp_title (or pass source=)"
        )
    return map_emp_title_category(clean_emp_title(df[source]), top_titles)


# The 7 structured variables the champion model uses (FR-5 selection) - the
# apples-to-apples comparison set for the report's IV table.
STRUCTURED_COMPARISON_VARIABLES: list[str] = [
    "fico_range_low", "annual_inc", "dti", "home_ownership",
    "revol_util", "inq_last_6mths", "purpose",
]


def iv_comparison(raw_parquet_path=None, k: int = 20) -> pd.DataFrame:
    """Reproduce the report's IV table end-to-end from the raw parquet: label
    + vintage-split via sample_design, fit top-K on train, bin the 7
    structured variables AND emp_title_category on the same train split with
    the same AD-2 binning path, return the IV table (descending).

    This is the single committed code path behind
    text-features-report-3-2.md's numbers - previously they came from an
    ad-hoc run, which an MDD-bound document can't rest on (code review
    finding, NFR1 reproducibility).
    """
    from scorecard.binning import fit_binning, iv_table
    from scorecard.config import ACCEPTED_PARQUET
    from scorecard.preprocessing import parse_percent
    from scorecard.sample_design import label_and_filter, split_by_vintage

    path = ACCEPTED_PARQUET if raw_parquet_path is None else raw_parquet_path
    raw = pd.read_parquet(
        path, columns=["emp_title", "loan_status", "vintage", *STRUCTURED_COMPARISON_VARIABLES]
    )
    train = split_by_vintage(label_and_filter(raw))["train"].copy()
    train["revol_util"] = parse_percent(train["revol_util"])
    top = fit_top_titles(clean_emp_title(train["emp_title"]), k=k)
    train["emp_title_category"] = derive_emp_title_category(train, top)
    binners = fit_binning(
        train, train["bad_flag"],
        variables=[*STRUCTURED_COMPARISON_VARIABLES, "emp_title_category"],
    )
    return iv_table(binners)


def emp_title_woe_table(raw_parquet_path=None, k: int = 20) -> pd.DataFrame:
    """Per-category WOE for emp_title_category on the train split (which
    titles lean risky vs safe) - the report's WOE-direction table (code
    review finding: Task 4 required it and it was missing)."""
    from scorecard.binning import fit_binning
    from scorecard.config import ACCEPTED_PARQUET
    from scorecard.sample_design import label_and_filter, split_by_vintage

    path = ACCEPTED_PARQUET if raw_parquet_path is None else raw_parquet_path
    raw = pd.read_parquet(path, columns=["emp_title", "loan_status", "vintage"])
    train = split_by_vintage(label_and_filter(raw))["train"].copy()
    top = fit_top_titles(clean_emp_title(train["emp_title"]), k=k)
    train["emp_title_category"] = derive_emp_title_category(train, top)
    binner = fit_binning(train, train["bad_flag"], variables=["emp_title_category"])[
        "emp_title_category"
    ]
    table = binner.binning_table.build()
    return table[table.index != "Totals"][["Bin", "Count", "WoE"]]
