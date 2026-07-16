"""CAP-15 rule efficiency audit (FR15, AD-7 rule/arithmetic-only).

Diagnoses whether each hard rule in a HYPOTHETICAL rule set (designed here
from industry practice - not a real deployed policy) actually earns its keep
against the model score, on the scored validation frame. Two rule-based
signals drive the verdict, with no LLM/judgment (AD-7):

  1. discrimination - the excluded group's bad rate vs the population's
     (a rule that excludes genuinely riskier applicants is doing work).
  2. model overlap - how much of the excluded group the model score would
     already reject at the current cutoff (a rule that mostly duplicates the
     score adds little).

Rule inputs (dti/delinq_2yrs/inq_last_6mths) and the opportunity-loss
principal (loan_amnt) are NOT in the AD-3 scored frame (its columns are
score/pd/grade/bad_flag/int_rate/recoveries/total_pymnt). They are augmented
read-only from the raw accepted parquet - the same AD-3-compliant join Story
2.4 established (frame's own columns are never recomputed; only rule-input
columns are added alongside).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from scorecard.profit import realized_profit
from scorecard.strategy import OOT_VINTAGE

# --- Verdict thresholds (AD-7: deterministic rule constants) -----------------
# Excluded bad rate at or above this multiple of the population bad rate reads
# as "the rule really is catching riskier applicants" -> keep.
BAD_RATE_MULTIPLE_KEEP: float = 1.5
# If at least this fraction of the excluded group already sits below the
# model's current cutoff (i.e. the model alone would reject them), the rule
# is largely redundant with the score -> review.
MODEL_OVERLAP_REVIEW: float = 0.7

# Rule-input columns augmented from the raw parquet (loan_amnt also powers the
# opportunity-loss estimate; the other three are rule predicates' inputs).
RULE_INPUT_COLUMNS: list[str] = ["dti", "delinq_2yrs", "inq_last_6mths", "loan_amnt"]


@dataclass(frozen=True)
class Rule:
    """A hard rule: applicants matching ``predicate`` are excluded (rejected).

    ``predicate`` takes the population DataFrame and returns a boolean mask of
    the EXCLUDED rows. NaN inputs compare False under pandas' ``>``/``>=``, so
    a missing rule input means "rule does not apply / not excluded" - the
    conservative choice (excluding on missing data would over-state both the
    exclusion count and the opportunity loss). Recorded per story Task 2.
    """

    rule_id: str
    description: str
    predicate: Callable[[pd.DataFrame], pd.Series]


# Hypothetical hard rule set (story-owner decision, Task 2): three rules
# grounded in common underwriting practice, all on variables that exist in the
# raw data. Boundaries are stated explicitly (strict > vs >=) so the report and
# tests agree.
RULE_SET: list[Rule] = [
    Rule("DTI_GT_40", "DTI > 40 거절", lambda df: df["dti"] > 40),
    Rule("INQ_GE_3", "최근 6개월 신용조회 3건 이상 거절", lambda df: df["inq_last_6mths"] >= 3),
    Rule("DELINQ_GE_1", "최근 2년 연체 이력 1건 이상 거절", lambda df: df["delinq_2yrs"] >= 1),
]


def load_rule_frame(frame: pd.DataFrame, raw_parquet_path: str | Path) -> pd.DataFrame:
    """Augment the AD-3 scored frame with the rule-input columns from the raw
    accepted parquet (read-only join on applicant_id == id). Same fail-fast +
    ``validate="many_to_one"`` contract as profit.load_profit_frame: the raw
    ``id`` must be unique, and every applicant must match (a diverged raw
    source is an error, not a silent NaN)."""
    raw = pd.read_parquet(raw_parquet_path, columns=["id", *RULE_INPUT_COLUMNS])
    merged = frame.merge(
        raw, left_on="applicant_id", right_on="id", how="left", validate="many_to_one"
    )
    # all-NaN across every rule input for a row means the join found no raw
    # match (real missing values are per-column, not whole-row); flag it.
    unmatched = merged[RULE_INPUT_COLUMNS].isna().all(axis=1).sum()
    if unmatched:
        raise ValueError(
            f"{unmatched} applicant_id(s) did not match any row in the raw parquet "
            f"({raw_parquet_path}) - the scored frame and raw source have diverged"
        )
    return merged.drop(columns=["id"])


def _opportunity_loss(excluded: pd.DataFrame) -> float:
    """Estimated profit foregone by excluding applicants who would actually
    have been good (bad_flag == 0). Reuses profit.realized_profit (AD-2: no
    reimplementation) and sums only the POSITIVE realized profits - a rejected
    good loan that would have lost money is not a missed opportunity. Story
    Task 3 decision, recorded in the report."""
    good = excluded[excluded["bad_flag"] == 0]
    if good.empty:
        return 0.0
    profit = realized_profit(
        good["loan_amnt"].to_numpy(dtype=float),
        good["total_pymnt"].to_numpy(dtype=float),
        good["recoveries"].to_numpy(dtype=float),
    )
    return float(profit[profit > 0].sum())


def _verdict(
    excluded_count: int,
    excluded_bad_rate: float | None,
    population_bad_rate: float,
    model_overlap: float | None,
) -> str:
    """Deterministic keep/review verdict with its rationale (AD-7, NFR7)."""
    if excluded_count == 0:
        return "진단 불가 — 이 표본에서 이 룰이 배제하는 신청 건이 없음"
    multiple = excluded_bad_rate / population_bad_rate if population_bad_rate else float("nan")
    if model_overlap is not None and model_overlap >= MODEL_OVERLAP_REVIEW:
        return (
            f"재검토 권장 — 배제집단의 {model_overlap:.0%}가 이미 모형 컷오프 미만"
            "(점수와 판별력 중복, 룰의 한계 기여 미미)"
        )
    if multiple >= BAD_RATE_MULTIPLE_KEEP:
        return f"유지 권장 — 배제집단 부도율이 모집단 대비 {multiple:.2f}배"
    return f"재검토 권장 — 배제집단 부도율이 모집단 대비 {multiple:.2f}배로 판별력이 낮음"


def rule_efficiency(
    rule_frame: pd.DataFrame,
    model_type: str,
    current_cutoff: float,
    vintage: int | None = OOT_VINTAGE,
    rule_set: list[Rule] | None = None,
) -> list[dict]:
    """Per-rule exclusion diagnostics on the OOT population (FR15).

    Returns one dict per rule matching API_SPEC §8: rule_id, description,
    excluded_count, excluded_bad_rate, population_bad_rate,
    opportunity_loss_est, verdict. excluded_bad_rate is None (not 0.0) when a
    rule excludes nobody - undefined, not "zero risk" (same NaN-not-0
    convention as strategy/profit).
    """
    rules = RULE_SET if rule_set is None else rule_set
    pop = rule_frame[rule_frame["model_type"] == model_type]
    if vintage is not None:
        pop = pop[pop["vintage"] == vintage]
    if pop.empty:
        raise ValueError(
            f"no rows for model_type={model_type!r}, vintage={vintage!r} - check "
            "model_type spelling and that vintage matches the frame's dtype"
        )
    if pop["score"].isna().any() or pop["bad_flag"].isna().any():
        raise ValueError(
            f"population for model_type={model_type!r}, vintage={vintage!r} has missing "
            "score/bad_flag - the AD-3 frame is expected to be complete"
        )

    population_bad_rate = float(pop["bad_flag"].mean())
    results: list[dict] = []
    for rule in rules:
        excluded_mask = rule.predicate(pop).fillna(False).astype(bool)
        excluded = pop[excluded_mask]
        count = int(len(excluded))
        excluded_bad_rate = float(excluded["bad_flag"].mean()) if count else None
        # overlap: fraction of the excluded already rejected by the model
        # (score strictly below the current cutoff). None when nobody excluded.
        overlap = float((excluded["score"] < current_cutoff).mean()) if count else None
        results.append({
            "rule_id": rule.rule_id,
            "description": rule.description,
            "excluded_count": count,
            "excluded_bad_rate": excluded_bad_rate,
            "population_bad_rate": population_bad_rate,
            "opportunity_loss_est": _opportunity_loss(excluded),
            "verdict": _verdict(count, excluded_bad_rate, population_bad_rate, overlap),
        })
    return results
