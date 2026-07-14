# Binning & Variable Selection Report — Story 1.4

## Spike result (AC 3 — first task, executed 2026-07-14)

**optbinning 0.21.0: PASS — no fallback needed.** Verified on synthetic data
before any implementation:

| Check | Result |
|---|---|
| Accepts nullable Float64/string input directly | PASS (no numpy adapter needed) |
| `monotonic_trend="auto_asc_desc"` produces monotone event rates | PASS (10 bins, strictly decreasing) |
| Missing values isolated into their own Missing bin | PASS |
| `dtype="categorical"` solver | PASS (status OPTIMAL, sensible per-category WOE) |
| IV extraction via `binning_table.build().loc["Totals","IV"]` | PASS |
| joblib-serializable (sklearn-style object) | expected PASS (verified in 1.5 when bundling) |

**Critical spike finding**: `OptimalBinning.transform` defaults
`metric_missing=0` — missing inputs silently map to WOE 0 even when the
fitted Missing bin carries strong signal (reproduced: Missing-bin WoE −1.27,
transform returned 0.0). Every transform call in `scorecard/binning.py`
therefore passes `metric_missing="empirical"` and
`metric_special="empirical"`. This is exactly the failure mode FR2's
"missing as its own bin" principle exists to prevent — without the flag the
whole missing-information design would be silently defeated at serving time.

The manual-quantile-binning fallback (pd.qcut + hand-rolled WOE) was NOT
needed and was not implemented.

## Binning candidates

17 variables = 18 feature candidates (`feature_candidate_columns()`) minus
`emp_title` (`BINNING_EXCLUDED_COLUMNS`): free-text with tens of thousands of
distinct values — not meaningfully binnable as a regular categorical; deriving
features from it is Story 3.2's consultant kick. (Note: leakage-audit-1-2.md
says "21 fields" in prose — that's a typo, the enumerated list and code both
have 18.)

Numeric variables are fitted with `monotonic_trend="auto_asc_desc"`;
zero-inflated counts (delinq_2yrs, inq_last_6mths, pub_rec — uncapped per the
1.3 review fix) are binned directly on raw values.

## Selection rules (AC 2)

1. **IV filter**: drop variables with IV < 0.02 (industry convention for
   "unpredictive").
2. **Correlation pruning**: on WOE-transformed values, walk variables in
   descending IV; drop any with |pairwise corr| > 0.7 against an
   already-kept variable (the lower-IV member loses). fico_range_low/high
   (corr ≈ 1) is the canonical case — exactly one survives.
3. Post-selection assertion: max off-diagonal |corr| of the final set must be
   ≤ 0.7 or `select_variables` raises (quantified success criterion enforced
   in code, verified by `test_select_variables_final_set_under_corr_cap`).

**VIF**: omitted. After univariate WOE transformation, pairwise correlation
pruning at 0.7 is the scorecard-industry norm and the AC's stated success
criterion is pairwise corr ≤ 0.7; VIF would add a second collinearity screen
without changing the outcome on WOE-transformed inputs.

## Illustrative run (synthetic — real parquet still absent)

The test fixture (`tests/test_binning.py::_synthetic_train`) has: a monotone
fico signal with 5% informative missing, a near-duplicate fico twin, a real
home_ownership effect, and a pure-noise dti. Selection behaves as designed:
noise dti dropped (IV < 0.02), exactly one fico twin kept, home_ownership
kept.

## Real-data snippet (run when the parquet exists)

```python
import pandas as pd
from scorecard.sample_design import label_and_filter, split_by_vintage
from scorecard.preprocessing import CAPPABLE_NUMERIC_COLUMNS, coerce_percent_columns, fit_caps, apply_caps
from scorecard.binning import fit_binning, transform_woe, iv_table, select_variables

df = pd.read_parquet("data/lc_accepted_2012_2015_36m.parquet")
groups = split_by_vintage(label_and_filter(df))
for name in groups:
    groups[name] = coerce_percent_columns(groups[name], ["revol_util"])
caps = fit_caps(groups["train"], CAPPABLE_NUMERIC_COLUMNS)
groups = {name: apply_caps(g, caps) for name, g in groups.items()}

binners = fit_binning(groups["train"], groups["train"]["bad_flag"])
woe_train = transform_woe(groups["train"], binners)
tbl = iv_table(binners)
selected, decisions = select_variables(woe_train, tbl)
print(tbl)
print(decisions.to_string())
print("selected:", selected)
```
