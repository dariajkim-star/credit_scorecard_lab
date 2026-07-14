# Challenger Report — Story 1.6

## n_trials decision (story-owner call)

`N_TRIALS = 20` in `scorecard/challenger.py`. Not specified in SPEC/epics.
Chosen to keep dev iteration fast even against the real ~144k-row train
split (20 trials completed in ~27s on real data) while still covering a
useful hyperparameter range (`num_leaves`, `learning_rate`,
`min_child_samples`, `n_estimators`). If a future story wants a more
exhaustive search, increase `n_trials` - the search space and objective
(valid-split logloss) don't need to change.

## Variables (reused from Story 1.4, raw not WOE)

Same 7 variables Story 1.4/1.5 selected: `fico_range_low, annual_inc, dti,
home_ownership, revol_util, inq_last_6mths, purpose`. Fed to LightGBM as raw
(post-1.3) values, not WOE-transformed - trees handle non-linearity and
missing values natively, so WOE isn't needed here (per the AC's "WOE 변환 전
원변수 사용 가능"). `home_ownership`/`purpose` are passed as pandas `category`
dtype directly; `fico_range_low`/`annual_inc`/`dti`/`revol_util` are the
capped Float64 values from Story 1.3; `inq_last_6mths` is the raw
(uncapped, per Story 1.3's zero-inflated-count exclusion) Int64 count.

## Calibration (AC 1)

`fit_calibrator()` fits an `IsotonicRegression` (default) or a 1-feature
`LogisticRegression` (Platt/"sigmoid") on **valid-split** predictions vs
actual labels - the model was fit on train, so valid is the first
out-of-sample point where its raw probabilities aren't optimistic.

**Real-data result (2026-07-14, valid split, isotonic):**

| | Brier score |
|---|---|
| before (raw LightGBM) | 0.11491 |
| after (isotonic calibrated) | 0.11480 |

Improvement direction confirmed (`after < before`), though the raw model was
already reasonably well-calibrated (small absolute gain) - LightGBM with a
modest number of trees on a class-imbalanced binary target tends to start
closer to calibrated than, say, an unconstrained boosted tree with many
rounds.

Calibration curve (10 quantile bins on the raw probability, valid split,
shared bin edges between before/after per the code-review fix below): the
"after" column tracks `observed` almost exactly at every bin (isotonic
regression is fit directly against this relationship, so this is expected -
it's an in-sample calibration check, not an out-of-sample one; a fully
rigorous check would calibrate on one held-out set and evaluate reliability
on a third, but this project's OOT split is reserved untouched for Story
1.7's evaluation).

**Code review fix**: `calibration_curve_data()` originally binned the raw and
calibrated probabilities independently (`sklearn.calibration.calibration_curve`
per curve) and merged the two result sets by positional index. When one
distribution has few unique values (verified with a synthetic lumpy-probability
case: 5 bins vs 10), that merge silently compared unrelated probability
ranges row-by-row. Fixed by deriving one set of bin edges from the raw
probability's quantiles and binning both curves against those same edges
(`pd.cut` + groupby); the returned frame now has an explicit `bin` column so
each row's probability range is unambiguous.

## Real-data sanity AUC (informal, like Story 1.5's champion check)

| Split | Champion AUC (1.5) | Challenger AUC (calibrated) |
|---|---|---|
| train | 0.647 | 0.660 |
| valid | 0.641 | 0.644 |
| oot | 0.643 | 0.645 |

Challenger is marginally ahead of champion on every split, with no
overfitting signal (train isn't dramatically higher than valid/oot). Formal
3-way comparison (the project's stated OOT champion KS>=0.25 /
challenger AUC>=0.70 targets) is Story 1.7's scope - these numbers are
directional only.

## Reproducibility (AC 3)

Verified empirically before this story: LightGBM with a fixed `random_state`
and Optuna's `TPESampler(seed=...)` both produce bit-identical results across
repeated runs (`tests/test_challenger.py::test_tune_challenger_reproducible_with_fixed_seed`
re-verifies this for the actual `tune_challenger` function, not just the raw
libraries).

## Artifact (AD-1)

`challenger_model.joblib`: `{"model": LGBMClassifier, "calibrator": IsotonicRegression}` -
both ship together (Story 1.5's code-review lesson: the bundle must contain
everything serving needs, since AD-4 forbids refitting at serve time).

`challenger_manifest.json` keys: common (`model_type="challenger"`,
`model_version`, `trained_at`, `feature_order`) + challenger-only
(`calibration_method`, `shap_background_sample_ref` - a relative path to the
fixed SHAP background sample saved by `save_shap_background_sample()`, so
Story 2.2's SHAP explainer never recomputes/reselects it per request).
`grade_thresholds` intentionally omitted (Story 1.7's CAP-7 hasn't produced
it yet, same as the champion manifest).

## Data availability

Unlike Stories 1.1-1.5, the real parquet **now exists** in this dev
environment (589,635 rows, downloaded during Story 1.5). All numbers above
were measured against it directly - not just illustrative synthetic
examples. Reproduce with:

```python
import pandas as pd
from scorecard.sample_design import label_and_filter, split_by_vintage
from scorecard.preprocessing import coerce_percent_columns, fit_caps, apply_caps, CAPPABLE_NUMERIC_COLUMNS
from scorecard.binning import fit_binning, transform_woe, iv_table, select_variables
from scorecard.challenger import (
    tune_challenger, fit_calibrator, brier_scores, calibration_curve_data,
    save_shap_background_sample, save_challenger_artifact, N_TRIALS,
)

df = pd.read_parquet("data/lc_accepted_2012_2015_36m.parquet")
groups = split_by_vintage(label_and_filter(df))
for name in groups:
    groups[name] = coerce_percent_columns(groups[name], ["revol_util"])
caps = fit_caps(groups["train"], CAPPABLE_NUMERIC_COLUMNS)
train, valid = apply_caps(groups["train"], caps), apply_caps(groups["valid"], caps)

binners = fit_binning(train, train["bad_flag"])
selected, _ = select_variables(transform_woe(train, binners), iv_table(binners))

model = tune_challenger(train, train["bad_flag"], valid, valid["bad_flag"], selected, n_trials=N_TRIALS, seed=42)
calibrator = fit_calibrator(model, valid, valid["bad_flag"], selected, method="isotonic")
print(brier_scores(model, calibrator, valid, selected, valid["bad_flag"]))

bg_path = save_shap_background_sample(train, selected, "models/artifacts/challenger_shap_background.parquet", n=100, seed=42)
save_challenger_artifact(model, calibrator, selected, bg_path, "models/artifacts")
```
