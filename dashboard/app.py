"""Streamlit dashboard (Story 2.5, FR13) — 4 screens over app/'s HTTP API.

AD-9: every datum comes from dashboard.api_client (HTTP only). This module
never imports scorecard.*, reads parquet, or loads artifacts. It formats and
charts what the API returns; NFR1 forbids it from re-computing anything.

Run (two local processes, AD-8):
    ./.venv/Scripts/python -m uvicorn app.main:app --port 8000
    ./.venv/Scripts/python -m streamlit run dashboard/app.py
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import api_client
from dashboard.api_client import ApiUnavailable

# Champion metric targets (P1 goals) — surfaced honestly alongside the actual
# OOT values, which fall short on a deliberately reduced 7-variable model.
KS_TARGET = 0.25
AUC_TARGET = 0.70
PSI_WARN = 0.10
PSI_ALERT = 0.25
CURRENT_CUTOFF = 546.0  # Story 2.1 policy value reused by the profit endpoint

ACCENT = "#2563eb"  # single fintech-tone accent (low-saturation blue)


# --------------------------------------------------------------------------- #
# Pure display helpers (unit-tested in tests/test_dashboard.py)
# --------------------------------------------------------------------------- #
def fmt_pct(value: float | None, digits: int = 1) -> str:
    """Fraction (0.477) → '47.7%'. None → em dash (nullable API fields)."""
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f}%"


def fmt_krw(value: float | None) -> str:
    """KRW amount → '₩1,234,567' (no decimals). None → em dash."""
    if value is None:
        return "—"
    return f"₩{value:,.0f}"


def fmt_metric(value: float | None, digits: int = 4) -> str:
    """Plain number for st.metric. None → em dash: the server's loader._clean
    legitimately returns null for degenerate metrics (2.3 review), and
    dict.get defaults don't cover present-but-null (code review finding)."""
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def target_delta(value: float | None, target: float) -> str | None:
    """st.metric delta text vs a target line; None hides the delta entirely
    rather than fabricating a shortfall from a missing metric."""
    if value is None:
        return None
    return f"목표 {target} 대비 {value - target:+.4f}"


def grades_to_chart_rows(grades: list[dict]) -> list[dict]:
    """Rows for the grade bar chart, dropping grades whose observed_bad_rate
    is null (OOT-unobserved — 2.3 deferred note) so altair doesn't choke."""
    return [g for g in grades if g.get("observed_bad_rate") is not None]


def profit_curve_to_rows(curve: list[dict]) -> list[dict]:
    """Profit-curve points with a defined expected_annual_profit. The field is
    nullable (2.4 review: zero-approval cutoffs have undefined economics)."""
    return [p for p in curve if p.get("expected_annual_profit") is not None]


# --------------------------------------------------------------------------- #
# Cached API reads (static-ish responses; cutoff sims keyed by their params)
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=60)
def _model_info() -> dict:
    return api_client.get_model_info()


@st.cache_data(ttl=60)
def _grades(model: str) -> dict:
    return api_client.get_grades(model)


@st.cache_data(ttl=60)
def _cutoff(cutoff_score: float, model: str) -> dict:
    return api_client.simulate_cutoff(cutoff_score, model)


@st.cache_data(ttl=60)
def _profit_cutoff(model: str, avg_loan_amnt: float) -> dict:
    return api_client.simulate_profit_cutoff(model, avg_loan_amnt)


def _psi_verdict(psi: float | None) -> tuple[str, str]:
    if psi is None:
        return "—", "gray"
    if psi < PSI_WARN:
        return "안정 (OK)", "green"
    if psi < PSI_ALERT:
        return "주의 (Warning)", "orange"
    return "불안정 (Alert)", "red"


# --------------------------------------------------------------------------- #
# Screen 1 — 성능 개요
# --------------------------------------------------------------------------- #
def screen_performance() -> None:
    st.subheader("① 모형 성능 개요")
    st.caption("챔피언(로지스틱 스코어카드) vs 챌린저(LightGBM) — OOT(2015) 검증 성능")
    info = _model_info()
    champ, chall = info["champion"], info["challenger"]
    cm, hm = champ["metrics"], chall["metrics"]

    c1, c2, c3 = st.columns(3)
    c1.metric("챔피언 AUC (OOT)", fmt_metric(cm.get("auc_oot")))
    c2.metric(
        "챔피언 KS (OOT)",
        fmt_metric(cm.get("ks_oot")),
        delta=target_delta(cm.get("ks_oot"), KS_TARGET),
        delta_color="normal",
    )
    c3.metric("챔피언 점수 PSI", fmt_metric(cm.get("psi_score")))

    c4, c5, c6 = st.columns(3)
    c4.metric(
        "챌린저 AUC (OOT)",
        fmt_metric(hm.get("auc_oot")),
        delta=target_delta(hm.get("auc_oot"), AUC_TARGET),
        delta_color="normal",
    )
    c5.metric("챌린저 KS (OOT)", fmt_metric(hm.get("ks_oot")))
    c6.metric("챌린저 점수 PSI", fmt_metric(hm.get("psi_score")))

    st.info(
        "OOT 목표(챔피언 KS≥0.25, 챌린저 AUC≥0.70)에 일부 미달합니다. 이는 신청 시점에 "
        "알 수 있는 7개 변수만 사용하고 grade·int_rate를 라벨 순환논리 방지를 위해 "
        "의도적으로 배제한 축소모형의 트레이드오프입니다(1.7a 원인분석). 수치를 숨기지 "
        "않고 목표선과 함께 투명하게 제시합니다."
    )

    sd = info["sample_design"]
    st.markdown("**표본 설계**")
    st.table(
        pd.DataFrame(
            [
                ["학습 빈티지", sd["train_vintages"]],
                ["검증 빈티지", sd["valid_vintage"]],
                ["OOT 빈티지", sd["oot_vintage"]],
                ["Bad 정의", sd["bad_definition"]],
            ],
            columns=["항목", "값"],
        ).set_index("항목")
    )


# --------------------------------------------------------------------------- #
# Screen 2 — 등급 분포
# --------------------------------------------------------------------------- #
def screen_grades() -> None:
    st.subheader("② 등급 분포와 단조성")
    model = st.radio("모델 선택", ["champion", "challenger"], horizontal=True, key="grade_model")
    data = _grades(model)
    rows = grades_to_chart_rows(data["grades"])

    badge = "✅ 단조성 검증 통과" if data.get("monotonic_validated") else "⚠️ 단조성 미검증"
    st.markdown(f"**{badge}** · 등급 1 = 최고 점수(최저 위험)")

    if rows:
        df = pd.DataFrame(rows)
        chart = (
            alt.Chart(df)
            .mark_bar(color=ACCENT)
            .encode(
                x=alt.X("grade:O", title="등급 (1=우량)"),
                y=alt.Y("observed_bad_rate:Q", title="관측 부도율", axis=alt.Axis(format="%")),
                tooltip=[
                    alt.Tooltip("grade:O", title="등급"),
                    alt.Tooltip("observed_bad_rate:Q", title="부도율", format=".2%"),
                ],
            )
            .properties(height=320)
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.warning("표시할 등급 데이터가 없습니다(관측 부도율 전부 null).")

    st.caption(
        "등급 경계는 우측폐구간 `(score_min, score_max]` 관례입니다 — `score_min`은 배타적, "
        "`score_max`는 포함(API_SPEC §3). 관측 부도율이 null인 등급(OOT 무관측)은 차트에서 제외됩니다."
    )
    if data["grades"]:
        # Guarded like the chart above: an empty list gives a zero-column
        # DataFrame where the column selection raises KeyError (code review).
        st.dataframe(
            pd.DataFrame(data["grades"])[["grade", "score_min", "score_max", "observed_bad_rate"]],
            use_container_width=True,
            hide_index=True,
        )


# --------------------------------------------------------------------------- #
# Screen 3 — PSI 안정성
# --------------------------------------------------------------------------- #
def screen_psi() -> None:
    st.subheader("③ 점수 안정성 (PSI)")
    st.caption("검증(2014)→OOT(2015) 점수 분포 안정성 — Population Stability Index")
    info = _model_info()

    for label, key in [("챔피언", "champion"), ("챌린저", "challenger")]:
        psi = info[key]["metrics"].get("psi_score")
        verdict, color = _psi_verdict(psi)
        col1, col2 = st.columns([1, 3])
        col1.metric(f"{label} PSI", f"{psi:.4f}" if psi is not None else "—")
        col2.markdown(
            f"판정: :{color}[**{verdict}**] "
            f"— 경고선 {PSI_WARN}, 경보선 {PSI_ALERT}"
        )
        if psi is not None:
            df = pd.DataFrame({"PSI": [psi]})
            base = alt.Chart(df).mark_bar(color=ACCENT, size=24).encode(
                x=alt.X("PSI:Q", scale=alt.Scale(domain=[0, max(PSI_ALERT * 1.2, psi * 1.2)]), title=None),
            )
            warn = alt.Chart(pd.DataFrame({"t": [PSI_WARN]})).mark_rule(color="orange").encode(x="t:Q")
            alert = alt.Chart(pd.DataFrame({"t": [PSI_ALERT]})).mark_rule(color="red").encode(x="t:Q")
            st.altair_chart((base + warn + alert).properties(height=80), use_container_width=True)

    st.info(
        "PSI < 0.1 = 안정, 0.1~0.25 = 주의, ≥0.25 = 불안정(재학습 검토). 두 모형 모두 점수 PSI가 "
        "0.01 미만으로 매우 안정적입니다. 변수별 PSI는 API가 노출하지 않으므로(AD-9: 대시보드는 "
        "frame 직접 접근 금지) 이 화면은 점수 PSI로 한정하며, 변수별 상세는 1.7b 리포트를 참조하세요."
    )


# --------------------------------------------------------------------------- #
# Screen 4 — cutoff 시뮬레이션 (리스크 + 손익)
# --------------------------------------------------------------------------- #
def screen_cutoff() -> None:
    st.subheader("④ Cutoff 시뮬레이션 — 리스크 + 손익")
    model = st.radio("모델 선택", ["champion", "challenger"], horizontal=True, key="cutoff_model")

    st.markdown("#### 리스크 관점")
    cutoff_score = st.slider("Cutoff 점수", 480, 610, int(CURRENT_CUTOFF), step=1)
    risk = _cutoff(float(cutoff_score), model)
    r1, r2, r3 = st.columns(3)
    r1.metric("승인율", fmt_pct(risk.get("approval_rate")))
    r2.metric("승인집단 부도율", fmt_pct(risk.get("bad_rate_approved"), digits=2))
    r3.metric("거절집단 부도율", fmt_pct(risk.get("bad_rate_rejected"), digits=2))

    risk_rows = [
        p for p in risk.get("curve", [])
        if p.get("approval_rate") is not None and p.get("bad_rate") is not None
    ]
    if risk_rows:
        rdf = pd.DataFrame(risk_rows).melt(
            "cutoff", ["approval_rate", "bad_rate"], "지표", "값"
        )
        rchart = (
            alt.Chart(rdf)
            .mark_line()
            .encode(
                x=alt.X("cutoff:Q", title="Cutoff 점수"),
                y=alt.Y("값:Q", axis=alt.Axis(format="%")),
                # domain pinned: with range alone Vega-Lite assigns colors by
                # SORTED category order, not declaration order (code review) -
                # keep the mapping explicit so approval=blue, bad=red always.
                color=alt.Color(
                    "지표:N",
                    scale=alt.Scale(
                        domain=["approval_rate", "bad_rate"], range=[ACCENT, "#dc2626"]
                    ),
                ),
            )
            .properties(height=280)
        )
        marker = alt.Chart(pd.DataFrame({"c": [cutoff_score]})).mark_rule(
            color="gray", strokeDash=[4, 4]
        ).encode(x="c:Q")
        st.altair_chart(rchart + marker, use_container_width=True)

    st.markdown("#### 손익 관점")
    avg_loan_amnt = st.number_input(
        "평균 대출금액 (avg_loan_amnt)",
        min_value=1.0,
        max_value=10_000_000.0,  # matches schemas upper bound → avoids 422
        value=12000.0,
        step=1000.0,
    )
    profit = _profit_cutoff(model, avg_loan_amnt)
    p1, p2, p3 = st.columns(3)
    delta_pp = profit.get("delta", {}).get("approval_rate_pp")
    p1.metric("현재 cutoff", f"{profit.get('current_cutoff')}")
    p2.metric(
        "손익 최적 cutoff",
        f"{profit.get('optimal_cutoff')}",
        # ProfitDelta fields are nullable (2.4 contract); None must hide the
        # delta, not print a literal "None pp" (code review finding).
        delta=None if delta_pp is None else f"{delta_pp} pp 승인율",
    )
    p3.metric(
        "연간 기대손익 개선",
        fmt_krw(profit.get("delta", {}).get("annual_profit_krw")),
    )

    prows = profit_curve_to_rows(profit.get("curve", []))
    if prows:
        pdf = pd.DataFrame(prows)
        pchart = (
            alt.Chart(pdf)
            .mark_line(color=ACCENT)
            .encode(
                x=alt.X("cutoff:Q", title="Cutoff 점수"),
                y=alt.Y("expected_annual_profit:Q", title="연간 기대손익", axis=alt.Axis(format="~s")),
                tooltip=[
                    alt.Tooltip("cutoff:Q", format=".1f"),
                    alt.Tooltip("expected_annual_profit:Q", title="기대손익", format=",.0f"),
                ],
            )
            .properties(height=280)
        )
        # Null-filtered like the curve itself, and color domain pinned so
        # "현재"=gray / "최적"=green regardless of category sort order (code
        # review findings - a swapped or silently-vanishing marker misleads
        # on a decision-support chart).
        line_rows = [
            r
            for r in (
                {"c": profit.get("current_cutoff"), "label": "현재"},
                {"c": profit.get("optimal_cutoff"), "label": "최적"},
            )
            if r["c"] is not None
        ]
        if line_rows:
            rule = alt.Chart(pd.DataFrame(line_rows)).mark_rule(strokeDash=[4, 4]).encode(
                x="c:Q",
                color=alt.Color(
                    "label:N",
                    scale=alt.Scale(domain=["현재", "최적"], range=["gray", "#16a34a"]),
                ),
            )
            pchart = pchart + rule
        st.altair_chart(pchart, use_container_width=True)

    st.markdown("**가정 (assumptions)**")
    for a in profit.get("assumptions", []):
        st.markdown(f"- {a}")
    st.caption("이 값은 손익 시뮬레이션이며 실제 재무 데이터가 아닙니다(컨설팅 정직성 원칙).")


SCREENS = {
    "① 성능 개요": screen_performance,
    "② 등급 분포": screen_grades,
    "③ PSI 안정성": screen_psi,
    "④ Cutoff 시뮬레이션": screen_cutoff,
}


def main() -> None:
    st.set_page_config(page_title="credit-scorecard-lab", layout="wide")
    st.title("신용 스코어카드 대시보드")
    st.caption(
        "모형 개발 전 과정을 성능 → 등급 → 안정성 → 심사전략(cutoff) 순으로 탐색합니다. "
        "모든 데이터는 스코어링 API(HTTP)를 경유합니다."
    )

    # Health gate: if the API is down/degraded, show a calm notice on every
    # screen instead of letting each screen's first request crash the app.
    try:
        api_client.check_health()
    except ApiUnavailable as e:
        st.error(
            "스코어링 API에 연결할 수 없습니다. 아래 명령으로 서버를 먼저 기동하세요:\n\n"
            "`./.venv/Scripts/python -m uvicorn app.main:app --port 8000`\n\n"
            f"상세: {e}"
        )
        st.stop()

    choice = st.sidebar.radio("화면", list(SCREENS.keys()))
    try:
        SCREENS[choice]()
    except ApiUnavailable as e:
        st.error(f"API 요청 중 오류가 발생했습니다: {e}")


if __name__ == "__main__":
    main()
