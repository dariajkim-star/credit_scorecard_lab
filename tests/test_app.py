"""Story 2.3 scoring API tests (real artifacts + frame, skipif-gated like the
other real-data suites; the 503 contract test runs always via a monkeypatched
empty store)."""

from __future__ import annotations

import time

import numpy as np
import pytest

from app.loader import SCORED_FRAME_PATH, ModelStore
from scorecard.config import ARTIFACTS_DIR

ARTIFACTS_PRESENT = (
    (ARTIFACTS_DIR / "champion_model.joblib").exists()
    and (ARTIFACTS_DIR / "challenger_model.joblib").exists()
    and SCORED_FRAME_PATH.exists()
)

APPLICANT = {
    "fico_range_low": 690, "annual_inc": 65000, "dti": 18.5,
    "home_ownership": "MORTGAGE", "revol_util": 42.3,
    "inq_last_6mths": 1, "purpose": "debt_consolidation",
}

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


@pytest.fixture(scope="module")
def client():
    if not ARTIFACTS_PRESENT:
        pytest.skip("artifacts/frame not generated locally")
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


# --- error contract (always-on, no artifacts needed) -------------------------


def test_degraded_health_and_503_when_store_not_loaded(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main_mod

    empty = ModelStore(loaded=False, error="synthetic: artifacts absent")
    monkeypatch.setattr(main_mod, "STORE", empty)
    c = TestClient(main_mod.app)

    health = c.get("/health")
    assert health.status_code == 200  # spec: degraded is 200, not 503
    assert health.json()["status"] == "degraded"
    assert health.json()["model_loaded"] is False

    r = c.post("/v1/score", json=APPLICANT)
    assert r.status_code == 503
    body = r.json()
    assert body["error_code"] == "MODEL_NOT_LOADED"
    assert "detail" in body


# --- 6 endpoints happy paths -------------------------------------------------


def test_health_ok(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "model_loaded": True, "model_version": "champion-1.0.0"}


def test_model_info_metrics_match_frame(client):
    body = client.get("/v1/model/info").json()
    assert set(body) == {"champion", "challenger", "sample_design"}
    champ = body["champion"]
    assert champ["pdo"] == 20.0 and champ["base_score"] == 600.0
    # 1.7a real-data values (frame-derived, must reproduce)
    assert champ["metrics"]["auc_oot"] == pytest.approx(0.643, abs=0.001)
    assert champ["metrics"]["ks_oot"] == pytest.approx(0.2054, abs=0.001)
    assert 0 < champ["metrics"]["psi_score"] < 0.1  # valid->oot (train not in frame)
    assert body["challenger"]["calibration"] == "isotonic"


def test_grades_table_consistent_with_scoring(client):
    grades = client.get("/v1/grades").json()
    assert grades["monotonic_validated"] is True
    table = grades["grades"]
    assert len(table) >= 10
    assert table[0]["grade"] == 1 and table[0]["score_max"] is None  # best band open-ended

    # a scored applicant's grade must fall in the band the table describes.
    # Boundary is right-inclusive (pd.cut convention): score_min EXCLUSIVE,
    # score_max INCLUSIVE (code review finding - the original assertion here
    # used >= on score_min, which is backwards at an exact-edge score).
    scored = client.post("/v1/score", json=APPLICANT).json()
    band = next(t for t in table if t["grade"] == scored["grade"])
    if band["score_min"] is not None:
        assert scored["score"] > band["score_min"]
    if band["score_max"] is not None:
        assert scored["score"] <= band["score_max"] + 1e-6


def test_grade_band_boundary_is_right_inclusive(client):
    """A score exactly ON an edge belongs to the interval that INCLUDES it:
    (score_min, score_max] is right-inclusive, so a score equal to grade g's
    score_min falls into the NEXT-WORSE grade (g+1), not grade g itself."""
    from scorecard.grading import assign_grade

    grades = client.get("/v1/grades").json()["grades"]
    edge_grade = next(t for t in grades if t["score_min"] is not None)
    edge_score = edge_grade["score_min"]

    import json

    from scorecard.config import ARTIFACTS_DIR

    thresholds = json.loads((ARTIFACTS_DIR / "champion_manifest.json").read_text())["grade_thresholds"]
    computed = int(assign_grade(np.array([edge_score]), np.asarray(thresholds))[0])
    assert computed == edge_grade["grade"] + 1  # one grade WORSE than the band listing it as score_min


def test_score_champion_response_shape(client):
    r = client.post("/v1/score", json=APPLICANT)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"score", "pd", "grade", "reason_codes", "warnings", "model"}
    assert body["model"] == {"name": "champion", "version": "champion-1.0.0", "type": "champion"}
    assert 300 < body["score"] < 900 and 0 < body["pd"] < 1
    assert 1 <= len(body["reason_codes"]) <= 3
    ranks = [rc["rank"] for rc in body["reason_codes"]]
    assert ranks == list(range(1, len(ranks) + 1))
    assert all("points_lost" in rc for rc in body["reason_codes"])


def test_score_challenger_uses_shap_field(client):
    body = client.post("/v1/score?model=challenger", json=APPLICANT).json()
    assert body["model"]["type"] == "challenger"
    assert all("shap_value" in rc for rc in body["reason_codes"])


def test_score_both_returns_gap(client):
    body = client.post("/v1/score?model=both", json=APPLICANT).json()
    assert set(body) == {"champion", "challenger", "score_gap"}
    assert body["score_gap"] == pytest.approx(
        body["challenger"]["score"] - body["champion"]["score"], abs=0.11
    )


def test_score_with_missing_fields_warns_but_scores(client):
    partial = {"fico_range_low": 700, "dti": 12.0}
    body = client.post("/v1/score", json=partial).json()
    assert 300 < body["score"] < 900
    assert any("annual_inc" in w for w in body["warnings"])


def test_batch_scoring_and_distribution(client):
    r = client.post("/v1/score/batch", json={"applicants": [APPLICANT] * 5})
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 5
    assert sum(body["grade_distribution"].values()) == 5


def test_batch_over_limit_is_422(client):
    r = client.post("/v1/score/batch", json={"applicants": [APPLICANT] * 1001})
    assert r.status_code == 422


def test_batch_bad_applicant_named_by_index_before_any_scoring(client):
    """A bound violation anywhere in the batch must name which applicant
    failed, and must be caught before any SHAP computation runs (code
    review finding: the original implementation interleaved validation with
    scoring, wasting work and never identifying the culprit)."""
    applicants = [APPLICANT] * 3 + [{**APPLICANT, "dti": 99999}] + [APPLICANT]
    r = client.post("/v1/score/batch", json={"applicants": applicants})
    assert r.status_code == 400
    body = r.json()
    assert body["error_code"] == "VALUE_OUT_OF_RANGE"
    assert "applicant[3]" in body["detail"]


def test_batch_rejects_model_both(client):
    r = client.post("/v1/score/batch", json={"applicants": [APPLICANT]}, params={"model": "both"})
    assert r.status_code == 422


def test_simulate_cutoff_matches_strategy(client):
    r = client.post("/v1/simulate/cutoff", json={"cutoff_score": 546.0, "model": "champion"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["curve"]) == 101
    assert 0 < body["approval_rate"] < 1
    assert body["bad_rate_approved"] < body["bad_rate_rejected"]  # score must separate risk

    import pandas as pd

    from scorecard import strategy

    frame = pd.read_parquet(SCORED_FRAME_PATH)
    expected = strategy.lookup_cutoff(frame, "champion", 546.0)
    assert body["approval_rate"] == pytest.approx(expected["approval_rate"])
    assert body["bad_rate_rejected"] == pytest.approx(expected["bad_rate_rejected"])


def test_simulate_cutoff_extreme_values_degrade_gracefully(client):
    """A cutoff above every observed score (0% approval) or below every
    observed score (100% approval) must not crash - one of the two bad
    rates becomes null (no approved/rejected population on that side)."""
    r_high = client.post("/v1/simulate/cutoff", json={"cutoff_score": 100000.0, "model": "champion"})
    assert r_high.status_code == 200
    assert r_high.json()["approval_rate"] == 0.0
    assert r_high.json()["bad_rate_approved"] is None

    r_low = client.post("/v1/simulate/cutoff", json={"cutoff_score": -100000.0, "model": "champion"})
    assert r_low.status_code == 200
    assert r_low.json()["approval_rate"] == 1.0
    assert r_low.json()["bad_rate_rejected"] is None


# --- error contract with loaded store ----------------------------------------


def test_value_out_of_range_is_400_with_error_code(client):
    r = client.post("/v1/score", json={**APPLICANT, "dti": 99999})
    assert r.status_code == 400
    body = r.json()
    assert body["error_code"] == "VALUE_OUT_OF_RANGE"
    assert "dti" in body["detail"]


def test_all_null_request_is_422(client):
    assert client.post("/v1/score", json={}).status_code == 422


def test_misspelled_field_is_422_not_silently_dropped(client):
    """extra='forbid': a typo'd field name must not be silently ignored and
    scored as if that real field were missing (code review finding)."""
    typo = {**APPLICANT}
    typo["anual_inc"] = typo.pop("annual_inc")
    r = client.post("/v1/score", json=typo)
    assert r.status_code == 422


def test_hard_bound_edges_are_inclusive(client):
    """FICO 300/850 and annual_inc=0 are real, valid inputs - the boundary
    check must accept them, not just values strictly inside the range."""
    edge = {**APPLICANT, "fico_range_low": 300.0, "annual_inc": 0.0}
    assert client.post("/v1/score", json=edge).status_code == 200
    edge2 = {**APPLICANT, "fico_range_low": 850.0}
    assert client.post("/v1/score", json=edge2).status_code == 200


def test_unseen_category_scores_with_warning_not_silently(client):
    """A category value never observed in training (e.g. a typo or a new
    Lending Club value) is silently routed through the Special/Missing bin
    by both models with no error (verified empirically in code review) -
    the API must at least surface a warning instead of pretending it's a
    normal, fully-supported input."""
    body = client.post(
        "/v1/score", json={**APPLICANT, "home_ownership": "CONDO"}
    ).json()
    assert any("home_ownership" in w and "CONDO" in w for w in body["warnings"])


# --- NFR2: /v1/score p95 < 300ms ----------------------------------------------


def test_score_latency_p95_under_300ms(client):
    for _ in range(3):  # warmup
        client.post("/v1/score", json=APPLICANT)
    samples = []
    for _ in range(30):
        t0 = time.perf_counter()
        r = client.post("/v1/score", json=APPLICANT)
        samples.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
    p95 = float(np.percentile(samples, 95))
    print(f"\n/v1/score latency: p50={np.percentile(samples,50):.1f}ms p95={p95:.1f}ms")
    assert p95 < 300, f"p95={p95:.1f}ms exceeds NFR2 300ms"


def test_score_logs_model_version(client, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="app.api"):
        client.post("/v1/score", json=APPLICANT)
    assert any("model_version=champion-1.0.0" in r.message for r in caplog.records)
