# Leakage Audit — Story 1.2 (FR1)

Generated from `scorecard.sample_design.audit_columns()` — the single source of
truth is that function; this file is a snapshot for readability. All 28
columns from `pipelines.loading.USECOLS` (plus the `vintage` column added by
Story 1.1's `filter_accepted`) are classified below.

- **id**: not a predictor (row id, timing, split key).
- **label_source**: `loan_status` — the origin of `bad_flag`, never a feature.
- **application_time**: known at the moment of application; feature candidate
  for Story 1.4 unless explicitly excluded.
- **post_origination**: only knowable after the loan closes; always excluded
  from the feature set (kept in the frame only where a later story needs it).

Conservative-exclusion principle (per epics.md Story 1.2 AC1): when in doubt,
exclude. `grade`/`sub_grade`/`int_rate` are Lending Club's own underwriting
output — assigned after approval, using the same kind of risk assessment our
model is meant to replace. Using them as predictors would be circular with the
label we're trying to predict, so they are excluded even though they are
technically known "at" the time of the loan (post-decision, not
post-application).

| field | classification | excluded | rationale |
|---|---|---|---|
| id | id | n/a | row identifier, not a predictor |
| issue_d | id | n/a | origination date, used for vintage/split only |
| term | id | n/a | constant 36 months after Story 1.1 filter |
| vintage | id | n/a | derived split key, not a predictor |
| loan_status | label_source | n/a | source of bad_flag; never a feature |
| loan_amnt | application_time | no | known at application |
| int_rate | application_time | yes | conservative exclusion: LC assigns this post-decision, based on the same risk assessment our model aims to replace -> circular with the label |
| grade | application_time | yes | conservative exclusion: same reasoning as int_rate (LC's own underwriting outcome) |
| sub_grade | application_time | yes | conservative exclusion: same reasoning as grade |
| emp_title | application_time | no | known at application |
| emp_length | application_time | no | known at application |
| home_ownership | application_time | no | known at application |
| annual_inc | application_time | no | known at application (self-reported) |
| verification_status | application_time | no | known at application |
| purpose | application_time | no | known at application |
| dti | application_time | no | known at application |
| delinq_2yrs | application_time | no | known at application (credit bureau snapshot) |
| fico_range_low | application_time | no | known at application |
| fico_range_high | application_time | no | known at application |
| inq_last_6mths | application_time | no | known at application (credit bureau snapshot) |
| open_acc | application_time | no | known at application |
| pub_rec | application_time | no | known at application |
| revol_bal | application_time | no | known at application |
| revol_util | application_time | no | known at application |
| total_acc | application_time | no | known at application |
| addr_state | application_time | no | known at application |
| recoveries | post_origination | yes | only known after default; kept in the frame for Story 2.4 profit calc, excluded from the feature set |
| total_pymnt | post_origination | yes | only known at loan closure; kept in the frame for Story 2.4 profit calc, excluded from the feature set |
| last_pymnt_d | post_origination | yes | only known at loan closure; used only for the Task 4 performance-window EDA, not a feature |

**Feature candidate set for Story 1.4** (application_time, not excluded — 21
fields): `loan_amnt, emp_title, emp_length, home_ownership, annual_inc,
verification_status, purpose, dti, delinq_2yrs, fico_range_low,
fico_range_high, inq_last_6mths, open_acc, pub_rec, revol_bal, revol_util,
total_acc, addr_state`.

Note: this is an audit of the 28 columns Story 1.1 chose to load, not the full
Lending Club schema. If Story 1.4's IV analysis calls for additional raw
columns, they need this same audit before being added to the feature set.
