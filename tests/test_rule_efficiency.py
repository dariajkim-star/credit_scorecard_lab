"""Story 3.1 rule efficiency audit tests.

Synthetic-data behavior tests for the pure diagnostics (predicate boundaries,
NaN-not-0 on zero exclusions, verdict rule branches, opportunity-loss reuse,
join fail-fast) plus one real-artifact end-to-end sanity check gated like the
other real-data suites.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scorecard import rule_efficiency as re
from scorecard.config import ACCEPTED_PARQUET


def _pop(rows: list[dict]) -> pd.DataFrame:
    """Build a rule_frame-shaped population (single model_type/vintage)."""
    base = {"model_type": "champion", "vintage": 2015, "score": 500.0,
            "bad_flag": 0, "int_rate": 12.0, "total_pymnt": 11000.0,
            "recoveries": 0.0, "dti": 10.0, "delinq_2yrs": 0,
            "inq_last_6mths": 0, "loan_amnt": 10000.0}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_dti_predicate_boundary_is_strict():
    # DTI_GT_40 uses strict > : exactly 40 is NOT excluded, 40.01 is.
    dti_rule = next(r for r in re.RULE_SET if r.rule_id == "DTI_GT_40")
    df = _pop([{"dti": 40.0}, {"dti": 40.01}, {"dti": 39.9}])
    mask = dti_rule.predicate(df)
    assert list(mask) == [False, True, False]


def test_nan_rule_input_is_not_excluded():
    # Missing rule input -> predicate False (conservative, Task 2 decision).
    dti_rule = next(r for r in re.RULE_SET if r.rule_id == "DTI_GT_40")
    df = _pop([{"dti": np.nan}, {"dti": 99.0}])
    mask = dti_rule.predicate(df).fillna(False)
    assert list(mask) == [False, True]


def test_zero_exclusion_gives_none_bad_rate_and_diagnosis_verdict():
    # A rule that excludes nobody: excluded_bad_rate None (not 0.0), verdict
    # says "진단 불가", opportunity loss 0.
    df = _pop([{"dti": 5.0}, {"dti": 8.0}])  # nobody has dti > 40
    out = re.rule_efficiency(df, "champion", current_cutoff=546.0)
    dti = next(r for r in out if r["rule_id"] == "DTI_GT_40")
    assert dti["excluded_count"] == 0
    assert dti["excluded_bad_rate"] is None
    assert dti["opportunity_loss_est"] == 0.0
    assert "진단 불가" in dti["verdict"]


def test_verdict_keep_when_high_bad_rate_multiple_and_low_overlap():
    # Excluded group is much riskier than the population AND the model score
    # does NOT already reject them (high scores) -> keep.
    rows = (
        [{"dti": 50.0, "bad_flag": 1, "score": 600.0} for _ in range(3)]  # excluded, risky, high score
        + [{"dti": 10.0, "bad_flag": 0, "score": 600.0} for _ in range(17)]  # kept, good
    )
    out = re.rule_efficiency(_pop(rows), "champion", current_cutoff=546.0)
    dti = next(r for r in out if r["rule_id"] == "DTI_GT_40")
    assert dti["excluded_count"] == 3
    assert dti["excluded_bad_rate"] == 1.0  # all excluded defaulted
    assert "유지 권장" in dti["verdict"]


def test_verdict_review_when_model_overlap_high():
    # Excluded group is risky, but the model already rejects them (low scores
    # below cutoff) -> redundant -> review, regardless of the bad-rate multiple.
    rows = (
        [{"dti": 50.0, "bad_flag": 1, "score": 500.0} for _ in range(4)]  # excluded, below cutoff
        + [{"dti": 10.0, "bad_flag": 0, "score": 600.0} for _ in range(16)]
    )
    out = re.rule_efficiency(_pop(rows), "champion", current_cutoff=546.0)
    dti = next(r for r in out if r["rule_id"] == "DTI_GT_40")
    assert "재검토 권장" in dti["verdict"]
    assert "모형 컷오프 미만" in dti["verdict"]


def test_opportunity_loss_sums_only_positive_profit_of_excluded_good():
    # Excluded rows: one good+profitable, one good+lossy, one bad. Only the
    # first contributes to opportunity loss.
    rows = [
        {"dti": 50.0, "bad_flag": 0, "loan_amnt": 10000.0, "total_pymnt": 11500.0, "recoveries": 0.0},  # +1500
        {"dti": 50.0, "bad_flag": 0, "loan_amnt": 10000.0, "total_pymnt": 9000.0, "recoveries": 0.0},   # -1000 (ignored)
        {"dti": 50.0, "bad_flag": 1, "loan_amnt": 10000.0, "total_pymnt": 3000.0, "recoveries": 500.0},  # bad (ignored)
    ]
    out = re.rule_efficiency(_pop(rows), "champion", current_cutoff=546.0)
    dti = next(r for r in out if r["rule_id"] == "DTI_GT_40")
    assert dti["opportunity_loss_est"] == pytest.approx(1500.0)


def test_empty_population_fails_fast():
    df = _pop([{"dti": 5.0}])
    with pytest.raises(ValueError, match="no rows"):
        re.rule_efficiency(df, "challenger", current_cutoff=546.0)  # no challenger rows


def test_load_rule_frame_fails_fast_on_unmatched(tmp_path):
    frame = pd.DataFrame({
        "applicant_id": ["A", "Z"], "vintage": [2015, 2015],
        "model_type": ["champion", "champion"], "score": [500.0, 500.0],
        "bad_flag": [0, 1], "int_rate": [12.0, 12.0],
        "recoveries": [0.0, 0.0], "total_pymnt": [11000.0, 3000.0],
    })
    raw = tmp_path / "raw.parquet"
    pd.DataFrame({
        "id": ["A"], "dti": [10.0], "delinq_2yrs": [0],
        "inq_last_6mths": [0], "loan_amnt": [10000.0],
    }).to_parquet(raw)
    with pytest.raises(ValueError, match="did not match"):
        re.load_rule_frame(frame, raw)


def test_load_rule_frame_allows_matched_row_with_null_inputs(tmp_path):
    # A genuinely matched applicant whose rule inputs are all NULL must NOT be
    # flagged as unmatched (the guard checks the join key, not the inputs).
    frame = pd.DataFrame({
        "applicant_id": ["A"], "vintage": [2015], "model_type": ["champion"],
        "score": [500.0], "bad_flag": [0], "int_rate": [12.0],
        "recoveries": [0.0], "total_pymnt": [11000.0],
    })
    raw = tmp_path / "raw.parquet"
    pd.DataFrame({
        "id": ["A"], "dti": [np.nan], "delinq_2yrs": [np.nan],
        "inq_last_6mths": [np.nan], "loan_amnt": [np.nan],
    }).to_parquet(raw)
    out = re.load_rule_frame(frame, raw)  # must not raise
    assert len(out) == 1


def test_verdict_zero_population_bad_rate_is_not_nan_string():
    # Degenerate population (no defaults): verdict must not format "nan배".
    rows = [{"dti": 50.0, "bad_flag": 0, "score": 600.0} for _ in range(5)]
    out = re.rule_efficiency(_pop(rows), "champion", current_cutoff=546.0)
    dti = next(r for r in out if r["rule_id"] == "DTI_GT_40")
    assert "nan" not in dti["verdict"]
    assert "진단 불가" in dti["verdict"]


# --- real-data end-to-end sanity (gated) ------------------------------------

ARTIFACTS_PRESENT = ACCEPTED_PARQUET.exists()


@pytest.mark.skipif(not ARTIFACTS_PRESENT, reason="raw parquet not present")
def test_real_data_rule_efficiency_is_sane():
    from app.loader import SCORED_FRAME_PATH

    if not SCORED_FRAME_PATH.exists():
        pytest.skip("scored frame not present")
    frame = pd.read_parquet(SCORED_FRAME_PATH)
    rule_frame = re.load_rule_frame(frame, ACCEPTED_PARQUET)
    out = re.rule_efficiency(rule_frame, "champion", current_cutoff=546.0)
    assert len(out) == len(re.RULE_SET)
    for r in out:
        assert r["excluded_count"] > 0  # every rule excludes someone on real data
        assert r["population_bad_rate"] > 0
        assert r["verdict"]  # non-empty rationale
