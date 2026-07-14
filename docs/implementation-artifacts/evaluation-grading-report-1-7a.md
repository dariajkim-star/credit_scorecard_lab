# Evaluation & Grading Report — Story 1.7a

## KS calculation (verified pre-story)

`scipy.stats.ks_2samp(p_bad[y==1], p_bad[y==0]).statistic` was verified
against a manual implementation of the classic credit-scoring KS (max
separation between cumulative bad-rate and good-rate distributions sorted by
risk score) on synthetic data — identical to 9 decimal places. Used as-is;
no custom KS implementation needed.

## 3-face evaluation table (AC 1) — real data

| model | split | AUC | KS | PR-AUC | OOT target met |
|---|---|---|---|---|---|
| champion | train | 0.6468 | 0.2120 | 0.1978 | — |
| challenger | train | 0.6603 | 0.2298 | 0.2071 | — |
| champion | valid | 0.6406 | 0.2022 | 0.2073 | — |
| challenger | valid | 0.6440 | 0.2064 | 0.2076 | — |
| **champion** | **oot** | 0.6430 | **0.2054** | 0.2239 | **No** (target KS ≥ 0.25) |
| **challenger** | **oot** | **0.6452** | 0.2087 | 0.2222 | **No** (target AUC ≥ 0.70) |

**Both OOT targets are missed** (champion KS 0.205 < 0.25; challenger AUC
0.645 < 0.70). Per FR6's success criterion, this is **not a story failure** -
epics.md explicitly frames "성능 미달 시 원인 분석 문서가 대체 산출물"
(a root-cause writeup is the alternative deliverable).

### Root-cause analysis (required per FR6)

The model works from only 7 application-time features (`fico_range_low,
annual_inc, dti, home_ownership, revol_util, inq_last_6mths, purpose`), after
Story 1.2's leakage audit conservatively excluded `grade`/`sub_grade`/
`int_rate` — Lending Club's own underwriting output, which is exactly the
kind of feature that would trivially push AUC toward 0.70+ (it's a proxy for
LC's internal, presumably more feature-rich risk model). The remaining
application-time bureau/income fields carry real but modest signal (each
individually has IV < 0.13 per Story 1.4/1.6's IV table) - a 7-variable
scorecard from bureau data typically lands in the 0.60-0.68 AUC range in
practice, which is exactly what both models show, consistently across train/
valid/OOT (no overfitting - the gap between splits is <2 points of AUC).

This is a designed tradeoff, not a bug: the project's leakage-audit
conservative-exclusion principle (Story 1.2) trades headline performance for
a model that is actually usable at real application time, rather than one
that circularly reproduces Lending Club's own risk assessment. If a future
iteration wants to close the gap to 0.70, the SPEC's non-goals would need
revisiting (e.g. relaxing the grade/int_rate exclusion), which is out of this
story's scope.

## Grade mapping (AC 2) — real data (champion PDO score, train-fit)

10 equal-frequency grades from train, **fully monotonic with no merging
needed** (validated via `validate_monotonic`):

| grade | count | bad_rate |
|---|---|---|
| 1 (safest) | 14,390 | 4.07% |
| 2 | 14,389 | 6.50% |
| 3 | 14,389 | 8.55% |
| 4 | 14,389 | 9.67% |
| 5 | 14,388 | 11.32% |
| 6 | 14,390 | 12.95% |
| 7 | 14,389 | 14.44% |
| 8 | 14,389 | 16.44% |
| 9 | 14,389 | 19.54% |
| 10 (riskiest) | 14,390 | 23.57% |

Grade 1 = highest champion PDO score (per API_SPEC.md's `/v1/grades`
convention: `grade:1, score_min:720` — highest score gets grade 1). Score
edges (train-fit): `[496.4, 526.1, 532.2, 536.8, 540.9, 544.8, 548.9, 553.5,
559.1, 567.3, 600.9]`.

Synthetic stress test (`tests/test_grading.py::test_enforce_monotonic_grades_merges_on_noisy_input`):
pure-noise scores/labels merge all the way down to **1 grade** — confirms
the merge algorithm terminates correctly even in the worst case, rather than
looping or leaving a non-monotonic result.

## Champion vs challenger grade thresholds (open question)

Grade thresholds are fit separately per model - `champion_scores` (PDO scale,
~496-601) and `challenger_scores` (probability scale, 0-1, or its own
calibrated score if one were defined) are on different scales, so a single
shared `grade_thresholds` would not make sense. **Story 1.7b must decide**:
does the challenger even need its own grade thresholds, or does the
API/dashboard only expose grades for the champion (which is the
explainable, primary scorecard per epics.md's framing)? This story computes
grading for the champion only; 1.7b should resolve this before writing
`grade_thresholds` into either manifest.

## Data availability

Real parquet + Story 1.5/1.6 artifacts already exist in this dev environment.
Reproduce with:

```python
import json, joblib, pandas as pd
from scorecard.sample_design import label_and_filter, split_by_vintage
from scorecard.preprocessing import coerce_percent_columns, fit_caps, apply_caps, CAPPABLE_NUMERIC_COLUMNS
from scorecard.binning import transform_woe
from scorecard.champion import score_formula
from scorecard.evaluation import evaluation_table
from scorecard.grading import enforce_monotonic_grades, validate_monotonic

df = pd.read_parquet("data/lc_accepted_2012_2015_36m.parquet")
groups = split_by_vintage(label_and_filter(df))
for name in groups:
    groups[name] = coerce_percent_columns(groups[name], ["revol_util"])
caps = fit_caps(groups["train"], CAPPABLE_NUMERIC_COLUMNS)
splits = {name: apply_caps(g, caps) for name, g in groups.items()}

champion_bundle = joblib.load("models/artifacts/champion_model.joblib")
challenger_bundle = joblib.load("models/artifacts/challenger_model.joblib")
champion_vars = json.load(open("models/artifacts/champion_manifest.json"))["feature_order"]
challenger_vars = json.load(open("models/artifacts/challenger_manifest.json"))["feature_order"]

print(evaluation_table(splits, champion_bundle, champion_vars, challenger_bundle, challenger_vars))

train = splits["train"]
woe_train = transform_woe(train, champion_bundle["binners"])
logit_bad = champion_bundle["model"].decision_function(woe_train[champion_vars].astype(float).to_numpy())
champion_scores = score_formula(logit_bad)
edges, table = enforce_monotonic_grades(champion_scores, train["bad_flag"].to_numpy(dtype=int), n_grades=10)
print(table)
print("monotonic:", validate_monotonic(table))
```
