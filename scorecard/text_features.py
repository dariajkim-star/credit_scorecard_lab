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

    NaN stays NaN (preserved as its own category downstream, not silently
    dropped - mirrors the binning Missing-bin principle). An entry that
    cleans down to an empty string (was all punctuation) also becomes NaN so
    it lands in MISSING rather than a bogus empty category.
    """
    cleaned = (
        series.astype("string")
        .str.lower()
        .str.replace(_NON_ALNUM, " ", regex=True)
        .str.replace(_MULTISPACE, " ", regex=True)
        .str.strip()
    )
    return cleaned.replace("", pd.NA)


def fit_top_titles(train_cleaned: pd.Series, k: int = 20) -> list[str]:
    """The k most frequent cleaned titles in the TRAIN split (leakage
    boundary: frequencies are learned on train only, then applied unchanged
    to valid/oot - same fit-on-train convention as binning). Ties resolve by
    pandas value_counts order (count desc, then first-seen)."""
    counts = train_cleaned.dropna().value_counts()
    return list(counts.head(k).index)


def map_emp_title_category(cleaned: pd.Series, top_titles: list[str]) -> pd.Series:
    """Map each cleaned title to one of: a top-K title (its own category),
    OTHER (a real but non-top title), or MISSING (null/empty). Pure mapping -
    top_titles is passed in, never recomputed here (leakage boundary)."""
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
    return map_emp_title_category(clean_emp_title(df[source]), top_titles)
