"""HTTP client — the ONLY place the dashboard touches the network (AD-9).

Screen code never imports requests or reads artifacts/parquet directly; it
calls these functions, which go through app/'s HTTP API exclusively. This
keeps the AD-9 boundary (dashboard depends on app only via HTTP) auditable
at a single grep-able location and makes the screens unit-testable by
monkeypatching this module.
"""

from __future__ import annotations

import os

import requests

DEFAULT_BASE_URL = "http://localhost:8000"
TIMEOUT_S = 10


def base_url() -> str:
    """Resolved at call time (not import time) so tests and demos can point
    the dashboard at a different host via DASHBOARD_API_URL without reloading
    the module."""
    # `or` (not a .get default) so an empty/whitespace value falls back too -
    # an empty base URL turns every request into a confusing MissingSchema
    # error instead of a clean "server not running" notice (code review).
    url = os.environ.get("DASHBOARD_API_URL", "").strip() or DEFAULT_BASE_URL
    return url.rstrip("/")


class ApiUnavailable(Exception):
    """The scoring API could not be reached or reported it is not ready.

    Raised for connection failures, timeouts, non-2xx responses, and the
    documented degraded state (model not loaded). Screens catch this to show
    a calm 'start the server' notice instead of crashing mid-demo.
    """


def _check(path: str, resp: requests.Response) -> dict:
    """Shared status + body validation for _get/_post (kept in one place so
    the two paths can't drift). resp.json() is inside the error mapping: a
    200 with a non-JSON body (wrong process on the port, proxy error page)
    must surface as ApiUnavailable, not a raw JSONDecodeError traceback on
    the screen (code review finding)."""
    if resp.status_code != 200:
        raise ApiUnavailable(f"{path} → HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError as e:
        raise ApiUnavailable(f"{path} → 200이지만 JSON이 아닌 응답: {e}") from e


def _get(path: str, params: dict | None = None) -> dict:
    try:
        resp = requests.get(base_url() + path, params=params, timeout=TIMEOUT_S)
    except requests.RequestException as e:
        raise ApiUnavailable(f"{path} 요청 실패: {e}") from e
    return _check(path, resp)


def _post(path: str, body: dict) -> dict:
    try:
        resp = requests.post(base_url() + path, json=body, timeout=TIMEOUT_S)
    except requests.RequestException as e:
        raise ApiUnavailable(f"{path} 요청 실패: {e}") from e
    return _check(path, resp)


def check_health() -> dict:
    """Return the /health payload, raising ApiUnavailable if the service is
    unreachable OR reports status != 'ok' (degraded = model not loaded, which
    every data screen depends on). /health itself returns HTTP 200 even when
    degraded (API_SPEC §1), so the status field is what gates the screens."""
    payload = _get("/health")
    if payload.get("status") != "ok":
        raise ApiUnavailable(
            f"API가 degraded 상태입니다(model_loaded={payload.get('model_loaded')})."
        )
    return payload


def get_model_info() -> dict:
    return _get("/v1/model/info")


def get_grades(model: str) -> dict:
    return _get("/v1/grades", params={"model": model})


def simulate_cutoff(cutoff_score: float, model: str) -> dict:
    return _post("/v1/simulate/cutoff", {"cutoff_score": cutoff_score, "model": model})


def simulate_profit_cutoff(model: str, avg_loan_amnt: float) -> dict:
    return _post(
        "/v1/simulate/profit-cutoff", {"model": model, "avg_loan_amnt": avg_loan_amnt}
    )
