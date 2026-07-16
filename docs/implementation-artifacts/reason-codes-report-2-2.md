# Reason Codes Report — Story 2.2

## AD-6 structure (pydantic base + value-field-only difference)

`ReasonCode(rank, variable, description)` is the shared base;
`ChampionReasonCode` adds `points_lost: float`, `ChallengerReasonCode` adds
`shap_value: float`. Both share the exact same `rank`/`variable`/`description`
fields (verified: `ChampionReasonCode.model_fields - ReasonCode.model_fields
== {"points_lost"}`, same for challenger with `shap_value`).

## Critical bug found and fixed while running against real applicants

The initial implementation computed
`points_lost = factor * coef_i * (safest_woe_i - applicant_woe_i)`. Running
this against 3 real applicants (`data/lc_accepted_2012_2015_36m.parquet`)
produced **every single variable at exactly `points_lost=0.0`** for all
three applicants — an implausible result that prompted a derivation check:

- A variable's contribution to the PDO score is `-factor * coef_i * woe_i`
  (`score = offset - factor * logit_bad`, Story 1.5's `score_formula`).
- `points_lost` = best-possible contribution minus actual contribution
  = `-factor*coef_i*safest_woe_i - (-factor*coef_i*applicant_woe_i)`
  = `factor * coef_i * (applicant_woe_i - safest_woe_i)`.
- The implemented formula had the subtraction **flipped**. Since
  `coef_i < 0` (verified for all 7 variables, Story 1.5) and a below-safest
  applicant has `applicant_woe_i < safest_woe_i`, the flipped formula
  produced a *negative* raw value for the overwhelming majority of
  real-world cases, which the `max(points_lost, 0.0)` defensive floor then
  silently clipped to zero — collapsing every variable to a tie and making
  the "top 3" ranking arbitrary and meaningless.

Fixed to `factor * coef_i * (applicant_woe_i - safest_woe_i)`. Re-running
against the same 3 applicants now produces varied, non-zero,
per-applicant-specific rankings (see below). A behavioral regression test
(`test_champion_reason_codes_best_applicant_has_near_zero_points_lost`) locks
this in: a synthetic best-case applicant loses ~0 points, a worst-case
applicant loses meaningfully more - this is exactly the check that would
have caught the flipped-subtraction bug, unlike the original test which
independently re-derived the same (initially also flipped) formula and thus
passed tautologically.

## Real-applicant examples (3 applicants, both models)

| applicant_id | champion top-3 (points_lost) | challenger top-3 (shap_value) |
|---|---|---|
| 68407277 | fico_range_low 28.83, annual_inc 12.91, inq_last_6mths 6.50 | fico_range_low 0.194, annual_inc 0.029, inq_last_6mths 0.027 |
| 68355089 | fico_range_low 15.94, inq_last_6mths 14.95, purpose 14.61 | purpose 0.931, inq_last_6mths 0.445, annual_inc 0.028 |
| 68426831 | fico_range_low 25.45, annual_inc 20.60, purpose 5.79 | annual_inc 0.396, fico_range_low 0.141, home_ownership 0.086 |

Both models tend to agree on the broad direction (fico/annual_inc/inq
frequently rank highly for both), consistent with them being trained on the
same 7-variable feature set, while the exact top-3 order can differ (e.g.
applicant 68355089: champion ranks fico_range_low first, challenger ranks
purpose first) — expected, since one is a linear WOE model and the other a
tree ensemble that can pick up interactions.

All `description` fields are complete Korean sentences directly quotable in
an adverse-action / 심사의견서 context, e.g.: "신용점수(FICO)이(가) 심사
기준 대비 불리하여 점수가 28.8점 하락했습니다."

## Two real preprocessing bugs found and fixed (real applicant row, not synthetic)

A raw applicant row (`df.iloc[0]`) is a `pd.Series` spanning numeric +
categorical values, which pandas necessarily stores as a single `object`
dtype for the whole Series. Two consequences, both caught only by running
against real data:

1. `revol_util` arrives as a plain numeral string (`"29.7"`, no `%` sign) in
   the raw accepted parquet - unlike Story 1.3's `apply_caps`/`coerce_percent_columns`
   pipeline output, this raw column was never parsed. Both model paths
   reuse `scorecard.preprocessing.parse_percent` (not re-derived).
2. After `.to_frame().T`, every column - not just `revol_util` - collapses
   to `object` dtype, including genuinely numeric ones like `fico_range_low`
   and `dti`. `transform_woe` (champion path) and LightGBM's `predict_proba`/
   SHAP `TreeExplainer` (challenger path) both reject `object`-dtype numeric
   columns, so both paths need explicit `pd.to_numeric` coercion, not just
   the percent-string column.

Both are fixed once in a shared `_normalize_raw_applicant()` helper reused by
both `champion_reason_codes` and `challenger_reason_codes` (AD-2 spirit:
don't duplicate the same dtype-recovery logic per model path).

## SHAP configuration decision (AD-1 note)

`challenger_manifest.json`'s `shap_background_sample_ref` (Story 1.6's fixed
background sample) is **not used** by this story. Passing it as
interventional background data to `shap.TreeExplainer` raises:

```
ExplainerError: Currently TreeExplainer can only handle models with
categorical splits when feature_perturbation="tree_path_dependent" and no
background data is passed.
```

Root cause: LightGBM trained native categorical splits on
`home_ownership`/`purpose` (Story 1.6), and SHAP's interventional
(background-sample) mode cannot handle categorical-split trees. **Decision:
use `shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")`**,
which needs no background data at all. Verified the margin-reconstruction
identity holds: `expected_value + sum(all shap_values) == logit(raw
predict_proba)` (within float tolerance). If a future story needs
interventional SHAP (e.g. for a different explanation granularity), the
background sample Story 1.6 saved would need to be revisited alongside a
non-categorical-split retrain - out of this story's scope.

## Sign convention

`shap_value` is positive when a variable pushes risk **up** (same "higher =
worse" direction as `points_lost`), so both lists sort consistently
descending by "how much this hurt the applicant."

## Data availability

Real parquet + Story 1.5/1.6 artifacts exist in this dev environment.
Reproduce with:

```python
import json, joblib, pandas as pd
from scorecard.reasons import champion_reason_codes, challenger_reason_codes

variables = json.load(open("models/artifacts/champion_manifest.json"))["feature_order"]
champion_bundle = joblib.load("models/artifacts/champion_model.joblib")
challenger_bundle = joblib.load("models/artifacts/challenger_model.joblib")

raw = pd.read_parquet("data/lc_accepted_2012_2015_36m.parquet", columns=variables + ["id"])
applicant = raw.iloc[0]
print(champion_reason_codes(champion_bundle, applicant, variables))
print(challenger_reason_codes(challenger_bundle, applicant, variables))
```
