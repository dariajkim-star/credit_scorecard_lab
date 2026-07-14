# Champion Scorecard Report — Story 1.5

## Scaling constants (AC 4)

| Constant | Value | Source |
|---|---|---|
| PDO | 20 | epics.md AC (fixed) |
| Base score | 600 | epics.md AC (fixed) |
| Base odds (good:bad at base score) | **50** | **not specified anywhere in SPEC/epics — story-owner decision** |

`BASE_ODDS = 50` follows the same pattern as prior stories' unspecified-detail
decisions (Story 1.2's train/valid split, Story 1.3's zero-inflated capping
exclusion): a reasonable industry-common default, documented here rather than
silently assumed. 50:1 is a widely used illustrative baseline in credit
scorecard literature (e.g. Siddiqi's *Credit Risk Scorecards*) when no
business-specific odds target is given. If the real portfolio's actual
good:bad ratio at a chosen reference score is known, replace this constant and
re-derive `offset` accordingly — the formula itself does not change.

## Score formula (AC 1, 3)

```
factor = PDO / ln(2)                         # 20 / ln(2) ~= 28.85
offset = BASE_SCORE - factor * ln(BASE_ODDS)  # 600 - 28.85 * ln(50) ~= 487.8
log_odds_good = -logit_bad                    # logit_bad = model.decision_function(x)
score = offset + factor * log_odds_good
```

`logit_bad` is sklearn's `LogisticRegression.decision_function` output
(`intercept + sum(coef_i * woe_i)`), not `predict_proba`. Verified in
`tests/test_champion.py::test_score_formula_matches_hand_calculation`.

## WOE sign convention and coefficient check (AC 2)

optbinning's WOE is higher for safer bins (verified empirically before this
story, in Story 1.4's dev notes: `corr(dti, WOE) ~= -0.95` for a variable
where higher values mean more risk). Fit against `y=bad_flag`, a correctly
signed logistic coefficient must be **negative** (WOE up -> logit(bad) down).
`check_coefficient_signs()` flags any positive coefficient as a reversal.

Synthetic example (`fico_range_low`, `dti`, both genuine risk drivers):

| variable | coefficient | sign_ok |
|---|---|---|
| fico_range_low | negative | True |
| dti | negative | True |

Both correctly signed — see
`tests/test_champion.py::test_fit_champion_all_coefficients_negative`.

## Manifest (AD-1)

`save_champion_artifact()` writes `champion_model.joblib` +
`champion_manifest.json`.

**`champion_model.joblib` (code review fix)**: a dict `{"model": ..., "binners":
{selected_var: OptimalBinning, ...}}`, not the bare LogisticRegression. Serving
(Story 2.3) receives a raw applicant, not a pre-WOE'd one - it needs the fitted
binners from this bundle to transform before scoring; AD-4 forbids refitting
at serve time. Verified end-to-end on real data: reload the bundle, WOE-transform
a raw training row using only `bundle["binners"]`, score with `bundle["model"]`
- reproduces the original score exactly.

Manifest keys:
- Common: `model_type="champion"`, `model_version="champion-1.0.0"`,
  `trained_at` (ISO-8601 UTC), `feature_order` (must match the WOE DataFrame's
  column order used at scoring time)
- Champion-only: `pdo`, `base_score`, `base_odds` (code review fix - the score
  formula's offset depends on it; omitting it broke reproducibility if the
  constant were ever changed later), `woe_bin_edges` (per-variable split
  points, from Story 1.4's `bin_edges()`, restricted to the selected variables)

**`grade_thresholds` is intentionally omitted.** AD-1 lists it as a common
manifest key, but it is produced by CAP-7 (Story 1.7's grading/monotonicity
work), which has not run yet. Story 1.7 is expected to update this same
manifest file to add it once grading is complete — this is a sequencing
consequence, not an AD-1 violation.

## Illustrative example (synthetic)

Given a synthetic training set where `fico_range_low` (higher = safer) and
`dti` (higher = riskier) both carry genuine signal, fitting `fit_champion` and
scoring one applicant end-to-end (`score_applicant`) produces a single float
score. A "safe" synthetic profile (high fico, low dti) scores strictly higher
than a "risky" one (low fico, high dti) — see
`tests/test_champion.py::test_score_applicant_safer_profile_scores_higher`.

## Real-data results (2026-07-14)

The full 1.1-1.5 pipeline was run against the real parquet (589,488 labeled
rows; see sample-design-report-1-2.md for split details):

- **IV table (top)**: fico_range_low/high 0.130 (twins, |corr|=1.000 — the
  correlation pruning kept exactly one), annual_inc 0.099, dti 0.042,
  home_ownership 0.035, revol_util 0.030, inq_last_6mths 0.028, purpose 0.024.
  9 variables dropped for IV < 0.02 (incl. loan_amnt/delinq_2yrs at ~0).
- **Selected (7)**: fico_range_low, annual_inc, dti, home_ownership,
  revol_util, inq_last_6mths, purpose.
- **Coefficient signs: all 7 negative — AC2's business-sense check PASSES on
  real data.**
- **Score distribution (train)**: min 496 / median 545 / max 601; mean score
  good=547 vs bad=539.
- **Sanity AUC** (predict_proba, informal — formal 3-way evaluation is Story
  1.7's scope): train 0.647 / valid 0.641 / oot 0.643. Stable across splits
  (no overfit). Modest by design: grade/sub_grade/int_rate — LC's own
  underwriting outputs — were conservatively excluded in the Story 1.2
  leakage audit, so the model works only from application-time bureau/income
  fields.
- Champion artifact + manifest written to `models/artifacts/` (gitignored).

## Data availability

As with Stories 1.1-1.4, `data/lc_accepted_2012_2015_36m.parquet` does not
exist in this dev environment (2026-07-14). All tests use synthetic data.
Once the real pipeline (1.1-1.4) has been run against real data, fit and score
the champion:

```python
import pandas as pd
from scorecard.sample_design import label_and_filter, split_by_vintage
from scorecard.preprocessing import coerce_percent_columns, fit_caps, apply_caps, CAPPABLE_NUMERIC_COLUMNS
from scorecard.binning import fit_binning, transform_woe, iv_table, select_variables
from scorecard.champion import fit_champion, check_coefficient_signs, score_applicant, save_champion_artifact

df = pd.read_parquet("data/lc_accepted_2012_2015_36m.parquet")
groups = split_by_vintage(label_and_filter(df))
for name in groups:
    groups[name] = coerce_percent_columns(groups[name], ["revol_util"])
caps = fit_caps(groups["train"], CAPPABLE_NUMERIC_COLUMNS)
train = apply_caps(groups["train"], caps)

binners = fit_binning(train, train["bad_flag"])
woe_train = transform_woe(train, binners)
selected, decisions = select_variables(woe_train, iv_table(binners))

model = fit_champion(woe_train, train["bad_flag"], selected)
print(check_coefficient_signs(model, selected))

applicant_score = score_applicant(model, woe_train.iloc[0], selected)
print("first applicant score:", applicant_score)

save_champion_artifact(model, binners, selected, "models/artifacts")
```
