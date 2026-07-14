# Preprocessing Report — Story 1.3

## Rules (AC 2, 3)

- **Missing values are never imputed.** `missing_summary()` reports counts
  only; no `fillna`/`SimpleImputer` anywhere in `scorecard/preprocessing.py`.
  Missing stays missing so Story 1.4's optbinning can bin it separately
  (FR2's "결측=별도 빈" principle).
- **`revol_util` is parsed from a percent string** (`"45.3%"` -> `45.3`,
  percent scale kept, not divided by 100) via `parse_percent()` /
  `coerce_percent_columns()`. This must run before capping — the raw column
  is `dtype="string"` from Story 1.1's loader and has no numeric percentiles
  to compute otherwise. `int_rate` uses the same raw string format but is
  already excluded from the feature set by Story 1.2's leakage audit, so it
  is out of scope here.
- **Outlier caps are fit on the train split only** (default 1st/99th
  percentile via `fit_caps()`) and applied unchanged to valid/oot via
  `apply_caps()`. This mirrors the fit-on-train/transform-only pattern Story
  1.4's WOE binning will use, and avoids leaking valid/oot distribution
  information into the cap boundaries.
- **Capping never changes the missing count.** `Series.clip()` passes NaN
  through untouched; `test_apply_caps_never_fills_missing` asserts this
  directly.
- **Categorical columns are pass-through, no-op** in this story: `emp_title,
  emp_length, home_ownership, verification_status, purpose, addr_state`.
  Encoding/binning for these is Story 1.4's job.

Numeric columns capped (12, from `scorecard.sample_design.feature_candidate_columns()`):
`loan_amnt, annual_inc, dti, delinq_2yrs, fico_range_low, fico_range_high,
inq_last_6mths, open_acc, pub_rec, revol_bal, revol_util, total_acc`.

## Data availability

As with Story 1.1/1.2, `data/lc_accepted_2012_2015_36m.parquet` does not exist
in this dev environment (2026-07-14) — the user has not yet run
`pipelines/01_download.py`. All tests use synthetic data. Once the real
parquet exists, run the full pipeline and inspect the report:

```python
import pandas as pd
from scorecard.sample_design import label_and_filter, split_by_vintage
from scorecard.preprocessing import (
    NUMERIC_COLUMNS, coerce_percent_columns, fit_caps, apply_caps,
    missing_summary, distribution_report,
)

df = pd.read_parquet("data/lc_accepted_2012_2015_36m.parquet")
labeled = label_and_filter(df)
groups = split_by_vintage(labeled)

# revol_util must be parsed from "45.3%" strings before capping
for name in groups:
    groups[name] = coerce_percent_columns(groups[name], ["revol_util"])

print(missing_summary(groups["train"], NUMERIC_COLUMNS))

caps = fit_caps(groups["train"], NUMERIC_COLUMNS)
capped = {name: apply_caps(g, caps) for name, g in groups.items()}
print(distribution_report(groups["train"], capped["train"], NUMERIC_COLUMNS))
```

## Illustrative example (synthetic)

To show the mechanism concretely without real data, a small synthetic
`dti` column with two outliers (-50, 500) and one missing value, capped
against a train split of 1..100:

| field | min_before | min_after | max_before | max_after | n_missing_before | n_missing_after |
|---|---|---|---|---|---|---|
| dti | -50 | ~1.99 (train p1) | 500 | ~99.01 (train p99) | 1 | 1 |

(Exact cap values depend on the train distribution's 1st/99th percentile —
see `tests/test_preprocessing.py::test_fit_caps_computed_from_train_percentiles`
for the precise assertion.) Note the missing count is unchanged (1 -> 1):
capping clips extreme values, it does not touch or fill missing entries.
