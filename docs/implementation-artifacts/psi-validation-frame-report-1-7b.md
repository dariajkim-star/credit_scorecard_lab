# PSI, Scored Validation Frame, Manifest Finalization — Story 1.7b (Epic 1 DoD)

## Generalized score (resolves Story 1.7a's open question)

`generalized_score(p_bad) = score_formula(ln(p_bad/(1-p_bad)))` (Story 1.5's
Siddiqi PDO/BASE_SCORE/BASE_ODDS constants) is now used for **both** champion
and challenger. For the champion this is mathematically identical to
`score_formula(decision_function(x))` from Story 1.5 (verified: max abs diff
5.7e-14, floating-point noise only). This gives both models a single
comparable score scale, so the scored validation frame's one `score` column
means the same thing regardless of `model_type` — and each model still gets
its own independently-fit `grade_thresholds` (their score *distributions*
differ even on a shared scale, so separate monotonic-grade fitting per model
is more accurate than forcing shared boundaries).

## PSI (AC 1) — real data, train vs OOT

| | PSI | Target |
|---|---|---|
| **champion score** | 0.0017 | < 0.1 ✅ |
| **challenger score** | 0.0013 | < 0.1 ✅ |

Both models are highly stable between train (2012-2013) and OOT (2015)
vintages on the generalized score.

Variable-level PSI (selected 7 variables, numeric subset):

| variable | PSI |
|---|---|
| fico_range_low | 0.0314 |
| annual_inc | 0.0094 |
| dti | 0.0489 |
| revol_util | 0.0592 |
| inq_last_6mths | 0.0539 |

All well under 0.1 (no major population shift by any standard PSI
interpretation: <0.1 stable, 0.1-0.25 moderate shift, >0.25 major shift).

### Code-review-style fixes made during this story (found while running against real data)

1. **Low-cardinality/skewed variables** (e.g. `inq_last_6mths`, a
   zero-inflated count Story 1.3 left uncapped): quantile-based bucketing
   can collapse to a single bin, silently hiding real distributional shift.
   `population_stability_index()` now buckets by **exact value** when
   `expected` has at most `n_buckets` distinct values (the standard PSI
   treatment for discrete/categorical-like variables), falling back to
   quantile buckets otherwise.
2. **NaN masking (more serious)**: `np.quantile` propagates NaN to every
   quantile level, so any variable with missing values (e.g. `revol_util`,
   which has ~97-126 missing rows per split by design — FR2 leaves missing
   unimputed) made the bucket-fitting loop fail for every bucket count and
   silently return `PSI=0.0` ("no drift"), when the real answer was simply
   uncomputed. Caught by running this exact function against real
   `revol_util` data and noticing an implausibly exact zero. Fixed by
   dropping NaN from both `expected` and `actual` before bucketing;
   regression tests added (`test_psi_ignores_nan_instead_of_masking_a_real_shift`,
   `test_psi_all_nan_expected_returns_zero`).

Both bucketing edges are always fit on `expected` (train) only and reused
for `actual` (OOT) — never independently re-quantiled, which is the general
form of the bug Story 1.6's code review found in `calibration_curve_data`
(comparing unrelated probability ranges after independent binning).

## Scored validation frame (AC 3, AD-3)

`build_scored_frame()` produces a long-format frame: one row per
(applicant, model_type), covering **valid + OOT only** (train was used to
fit the models, so it is not part of the validation frame). Columns exactly
match AD-3's fixed schema: `applicant_id, vintage, model_type, score, pd,
grade, bad_flag, int_rate, recoveries, total_pymnt`.

**Real data**: 162,570 (valid) + 283,026 (oot) = 445,596 applicants x 2
model types = **891,192 rows**. Saved to
`data/scored_validation_frame.parquet` (gitignored, NFR5 — regenerate via
the snippet below).

`int_rate` required parsing here for the first time: Story 1.3 only parsed
`revol_util` (the only percent-string column actually used as a model
feature); `int_rate` was excluded as a feature by Story 1.2's leakage audit
so nothing touched its raw `"13.5%"` string format until this frame needed
it as auxiliary data for Story 2.4's profit calculation. Reused
`scorecard.preprocessing.parse_percent` — no new parsing logic.

## Manifest finalization (AC 2, AD-1 completion)

`finalize_manifest()` patches each model's existing `manifest.json` to add
`grade_thresholds`, without re-dumping the joblib artifact (so the model
bundle Story 1.5/1.6 already validated can never desync from its manifest).

Both manifests now carry the full AD-1 key set:

- **Common**: `model_type`, `model_version`, `trained_at`, `feature_order`
- **Champion-only**: `pdo`, `base_score`, `base_odds`, `woe_bin_edges`
- **Challenger-only**: `calibration_method`, `shap_background_sample_ref`
- **Both** (new in this story): `grade_thresholds` (10 fully monotonic
  grades each, fit independently per model on the shared generalized score)

`grade_thresholds` was the one AD-1 key intentionally deferred since Story
1.5/1.6 (CAP-7 hadn't run yet) — this story closes that gap. Both manifests
are now considered **complete** per AD-1.

## Epic 1 DoD (AC 4) — performance summary

Epic 1 (모형개발기반) is complete. Consolidated headline numbers across the
full pipeline (all measured against real Lending Club data, 2012-2015
vintages, 589,635 rows after Story 1.1's filter):

| Metric | Champion | Challenger |
|---|---|---|
| OOT AUC | 0.6430 | 0.6452 |
| OOT KS | 0.2054 (target 0.25, miss) | — |
| OOT PR-AUC | 0.2239 | 0.2222 |
| Score PSI (train vs OOT) | 0.0017 | 0.0013 |
| Grade count (monotonic) | 10 / 10 | 10 / 10 |

Both OOT performance targets (champion KS>=0.25, challenger AUC>=0.70) are
missed — root-caused in Story 1.7a's report to the conservative exclusion of
`grade`/`sub_grade`/`int_rate` as features (Story 1.2's leakage audit). Both
models are, however, fully monotonic in grading and highly stable (PSI) —
the "검증 완료된 신용평가모형" (verified, validated model) framing holds even
though headline discrimination is modest, per epics.md's explicit
"성능 미달 = 실패 아님" reframe.

Git commit: this story's implementation commit (see Change Log). Obsidian
mirror: see `Desktop\ob_storage\신용평가_CRM_사이드프로젝트\` (added as part of
this story's completion, per project convention established in
`feedback_bmad_obsidian_workflow`).

## Data availability

Real parquet + all Story 1.5/1.6/1.7a artifacts exist in this dev
environment. Reproduce with:

```python
import json, joblib, pandas as pd
from scorecard.sample_design import label_and_filter, split_by_vintage
from scorecard.preprocessing import coerce_percent_columns, fit_caps, apply_caps, CAPPABLE_NUMERIC_COLUMNS
from scorecard.evaluation import (
    champion_p_bad, challenger_p_bad, generalized_score,
    population_stability_index, variable_psi, build_scored_frame,
)
from scorecard.grading import enforce_monotonic_grades, finalize_manifest

df = pd.read_parquet("data/lc_accepted_2012_2015_36m.parquet")
groups = split_by_vintage(label_and_filter(df))
for name in groups:
    groups[name] = coerce_percent_columns(groups[name], ["revol_util"])
caps = fit_caps(groups["train"], CAPPABLE_NUMERIC_COLUMNS)
splits = {name: apply_caps(g, caps) for name, g in groups.items()}
train = splits["train"]

champion_bundle = joblib.load("models/artifacts/champion_model.joblib")
challenger_bundle = joblib.load("models/artifacts/challenger_model.joblib")
champion_vars = json.load(open("models/artifacts/champion_manifest.json"))["feature_order"]
challenger_vars = json.load(open("models/artifacts/challenger_manifest.json"))["feature_order"]

champ_score_train = generalized_score(champion_p_bad(champion_bundle, train, champion_vars))
champ_edges, _ = enforce_monotonic_grades(champ_score_train, train["bad_flag"].to_numpy(dtype=int), n_grades=10)
chall_score_train = generalized_score(challenger_p_bad(challenger_bundle, train, challenger_vars))
chall_edges, _ = enforce_monotonic_grades(chall_score_train, train["bad_flag"].to_numpy(dtype=int), n_grades=10)

frame = build_scored_frame(
    {"valid": splits["valid"], "oot": splits["oot"]},
    champion_bundle, champion_vars, champ_edges,
    challenger_bundle, challenger_vars, chall_edges,
)
frame.to_parquet("data/scored_validation_frame.parquet")

finalize_manifest("models/artifacts/champion_manifest.json", champ_edges)
finalize_manifest("models/artifacts/challenger_manifest.json", chall_edges)
```
