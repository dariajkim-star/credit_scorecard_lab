"""Story 2.5 dashboard tests.

Scope: the api_client HTTP layer (URL/payload construction, the degraded
gate, error mapping) and the pure display helpers in dashboard.app. The
Streamlit screens themselves are not rendered here - AD-9 says the dashboard
only consumes the API, so the logic worth testing is 'did we build the right
request' and 'do we survive the nullable/degraded responses', both of which
are pure and mockable without a running server or browser.
"""

from __future__ import annotations

import requests

from dashboard import api_client
from dashboard.app import (
    fmt_krw,
    fmt_pct,
    grades_to_chart_rows,
    profit_curve_to_rows,
)


class _FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def test_base_url_reads_env(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_URL", "http://example.test:9000/")
    assert api_client.base_url() == "http://example.test:9000"  # trailing slash stripped
    monkeypatch.delenv("DASHBOARD_API_URL")
    assert api_client.base_url() == api_client.DEFAULT_BASE_URL


def test_get_grades_builds_url_and_params(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResp(json_data={"model": "challenger", "grades": []})

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(api_client, "base_url", lambda: "http://localhost:8000")
    out = api_client.get_grades("challenger")
    assert captured["url"] == "http://localhost:8000/v1/grades"
    assert captured["params"] == {"model": "challenger"}
    assert out["model"] == "challenger"


def test_simulate_profit_cutoff_builds_body(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResp(json_data={"current_cutoff": 546.0})

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(api_client, "base_url", lambda: "http://localhost:8000")
    api_client.simulate_profit_cutoff("champion", 15000)
    assert captured["url"] == "http://localhost:8000/v1/simulate/profit-cutoff"
    assert captured["json"] == {"model": "champion", "avg_loan_amnt": 15000}


def test_check_health_ok(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _FakeResp(json_data={"status": "ok"})
    )
    monkeypatch.setattr(api_client, "base_url", lambda: "http://x")
    assert api_client.check_health()["status"] == "ok"


def test_check_health_degraded_raises(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: _FakeResp(json_data={"status": "degraded", "model_loaded": False}),
    )
    monkeypatch.setattr(api_client, "base_url", lambda: "http://x")
    try:
        api_client.check_health()
        raised = False
    except api_client.ApiUnavailable:
        raised = True
    assert raised


def test_connection_error_maps_to_api_unavailable(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(api_client, "base_url", lambda: "http://x")
    try:
        api_client.get_model_info()
        raised = False
    except api_client.ApiUnavailable:
        raised = True
    assert raised


def test_non_200_maps_to_api_unavailable(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _FakeResp(status_code=500, text="boom")
    )
    monkeypatch.setattr(api_client, "base_url", lambda: "http://x")
    try:
        api_client.get_model_info()
        raised = False
    except api_client.ApiUnavailable:
        raised = True
    assert raised


# ---- pure display helpers ----


def test_fmt_pct_and_krw_handle_none():
    assert fmt_pct(None) == "—"
    assert fmt_krw(None) == "—"
    assert fmt_pct(0.4771) == "47.7%"
    assert fmt_krw(164770262.49) == "₩164,770,262"


def test_grades_to_chart_rows_drops_null_bad_rate():
    grades = [
        {"grade": 1, "score_min": 567.0, "score_max": None, "observed_bad_rate": 0.046},
        {"grade": 2, "score_min": 559.0, "score_max": 567.0, "observed_bad_rate": None},
    ]
    rows = grades_to_chart_rows(grades)
    # grade 2 has a null observed_bad_rate (OOT-unobserved) - excluded from the
    # bar chart data rather than crashing altair, per the 2.3 deferred note.
    assert len(rows) == 1
    assert rows[0]["grade"] == 1


def test_profit_curve_to_rows_skips_null_profit():
    curve = [
        {"cutoff": 494.4, "approval_rate": 1.0, "expected_annual_profit": 3.2e8},
        {"cutoff": 700.0, "approval_rate": 0.0, "expected_annual_profit": None},
    ]
    rows = profit_curve_to_rows(curve)
    # nullable expected_annual_profit (2.4 review) must not crash the chart.
    assert len(rows) == 1
    assert rows[0]["cutoff"] == 494.4
