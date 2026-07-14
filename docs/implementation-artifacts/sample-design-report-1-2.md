# Sample Design Report — Story 1.2

## Split definition (AC 3)

Deterministic vintage-year split (story-owner decision — not specified in
SPEC, chosen to avoid introducing an RNG dependency for a temporal split):

| Split | Vintage(s) |
|---|---|
| train | 2012, 2013 |
| valid | 2014 |
| oot | 2015 |

`scorecard.sample_design.split_by_vintage()` raises `ValueError` if any split
is empty (treated as a sample-design failure, not a warning — see AC success
criteria in the story file).

**Measured on real data (2026-07-14, after running `pipelines/01_download.py`):**

Raw file 2,260,701 rows -> 589,635 after the 2012-2015/36m filter (33 rows
with unparseable `issue_d` excluded, caught by the loader's warn log) ->
589,488 after labeling (147 in-progress loans dropped).

| Split | Rows | Bad rate |
|---|---|---|
| train (2012-2013) | 143,892 | 12.70% |
| valid (2014) | 162,570 | 13.73% |
| oot (2015) | 283,026 | 14.89% |

The rising bad rate by vintage is consistent with Lending Club's known
portfolio deterioration over this period. The snippet used:

```python
import pandas as pd
from scorecard.sample_design import label_and_filter, split_by_vintage, split_summary

df = pd.read_parquet("data/lc_accepted_2012_2015_36m.parquet")
labeled = label_and_filter(df)
groups = split_by_vintage(labeled)
print(split_summary(groups))
```

## Performance window decision (AC 4 — SPEC open question)

**Decision: adopt the maturity-based definition as the sole label definition
for this story. Do not adopt the 12-month performance-window approximation.**

Rationale:

- `stack.md`'s risk table already flagged this as an open question and named
  "만기 기준 최종 상태" (final status at maturity) as the primary definition,
  with a 12-month window reserved for an appendix experiment. This story
  confirms that choice rather than reopening it.
- `make_label()` uses `loan_status` directly (Charged Off / Default / Fully
  Paid), which is Lending Club's own terminal-status field — it requires no
  performance-window approximation at all. The maturity-based label is
  strictly simpler and has no risk of mid-window mislabeling (e.g. a loan
  that is current at the 12-month mark but eventually defaults at month 20
  would be wrongly labeled "good" under a 12-month window).
- The tradeoff a 12-month window would buy is label *recency* (usable before
  a loan reaches its 36-month term) at the cost of a materially higher
  mislabel rate for medium-risk loans that default late. Given this project's
  vintages (2012-2015, all closed out well before the 2018Q4 data cutoff per
  NFR8), the full sample already has mature, terminal labels available — there
  is no recency pressure that would justify the tradeoff here.
- `scorecard.sample_design.performance_window_months()` is provided as the
  tool for the appendix experiment if a future story wants to quantify how
  many rows would flip label under a 12-month window; it is not invoked by
  `make_label()` or `label_and_filter()`.

This decision record satisfies AC 4: the SPEC open question is resolved (not
adopted), with rationale, independent of whether a future story revisits it.

## Leakage audit

See [leakage-audit-1-2.md](leakage-audit-1-2.md) (AC 1).

## Known risk (RESOLVED 2026-07-14 — verified against real data)

**Verified: not an issue for this sample window.**
`df["loan_status"].value_counts()` on the real 2012-2015/36m parquet shows
**0 rows** with either "Does not meet the credit policy" variant (the values
exist only as unused categorical levels inherited from the full file).
`make_label`'s exact matching is safe as-is. Original risk description kept
below for the record.

### Original description (pre-verification)

`make_label()` matches `loan_status` by exact string only (`"Charged Off"`,
`"Default"`, `"Fully Paid"`). The real Lending Club accepted-loans dataset
also contains legacy status variants for early loans, e.g. `"Does not meet
the credit policy. Status:Charged Off"` / `"...Status:Fully Paid"`. Those
rows would currently be misclassified as in-progress (excluded from the
sample) rather than correctly labeled bad/good.

This is flagged, not fixed, because:
- these legacy statuses are associated with pre-2012 originations in the
  public dataset, so they are unlikely (but not verified) to appear in this
  project's 2012-2015 vintage window
- there is no real parquet in this dev environment to check against (see
  "Data availability" above)

When the real parquet exists, run
`df["loan_status"].value_counts()` on the raw (pre-label) frame and confirm
no `"Does not meet the credit policy..."` values are present. If they are,
extend `BAD_STATUSES`/`GOOD_STATUSES` matching (e.g. `str.contains` on the
suffix) before trusting the split's bad rates.
