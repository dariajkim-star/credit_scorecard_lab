---
baseline_commit: 4f03fee
---

# Story 2.5: Streamlit 대시보드 (Epic 2 마지막)

Status: done

## Story

As a 면접에서 시연하는 지원자,
I want 성능·등급분포·PSI·cutoff(리스크+손익)를 한 화면씩 탐색하고,
so that 모형 개발 전 과정을 5분 안에 시각적으로 보여줄 수 있다.

## Acceptance Criteria

**Given** 2.3·2.4의 구동 중인 API (`uvicorn app.main:app`, localhost:8000)
**When** `dashboard/`를 streamlit으로 구동하면

1. 4개 화면(성능/등급분포/PSI/cutoff 시뮬레이션)이 라이브로 동작한다 (FR13)
2. 모든 데이터는 app/의 HTTP API 경유로만 가져온다 — 아티팩트·parquet·scorecard/* 직접 읽기 금지 (AD-9)
3. 스크린샷이 확보된다 (4화면 각 1장 이상, `docs/implementation-artifacts/` 하위 또는 스토리 파일에 경로 기록)
4. 에픽 DoD: 라이브 데모 + git 커밋 + 옵시디언 미러 완료

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC + `pytest -q` 초록(대시보드 헬퍼 함수 테스트 — Streamlit 화면 자체는 pytest 대상 아님, 아래 Task 6) + **배선 실증**: 화면이 뜨는 것만으로는 done이 아니다 — 각 화면이 실제 API 응답으로 렌더링됨을 uvicorn 액세스 로그(어느 엔드포인트가 호출됐는지) + 라이브 조작(cutoff 슬라이더를 움직이면 서버에 새 요청이 가고 숫자가 바뀜)으로 증빙한다. (플러드이스케이프 3.3 반려 교훈: "화면 존재≠배선".)

## Tasks / Subtasks

- [x] Task 1: 대시보드 스캐폴딩 + API 클라이언트 (AC: #2, AD-9)
  - [x] `dashboard/api_client.py` — requests 기반 얇은 클라이언트: `get_health()`, `get_model_info()`, `get_grades(model)`, `simulate_cutoff(cutoff_score, model)`, `simulate_profit_cutoff(model, avg_loan_amnt)`. base URL은 `DASHBOARD_API_URL` 환경변수(기본 `http://localhost:8000`). **이 모듈이 대시보드에서 유일하게 네트워크를 만지는 곳** — 화면 코드에 requests 직접 호출 금지(테스트 가능성 + AD-9 감사 지점 단일화).
  - [x] API 다운/degraded 처리: `/health`가 실패하거나 `status != "ok"`면 각 화면 대신 명확한 안내(st.error + 기동 명령어 안내)를 표시. 대시보드가 크래시하면 안 됨(면접 데모 도구).
  - [x] `dashboard/app.py` — 엔트리포인트. `st.set_page_config(layout="wide")`, 사이드바 네비게이션(4화면). Streamlit 멀티페이지(`dashboard/pages/`) 대신 사이드바 라디오/`st.navigation` 중 택1하고 이유 기록(권장: 단일 `app.py` + 화면별 함수 — 4화면 고정이라 pages/ 디렉토리 오버헤드 불필요, 상태 공유 쉬움).
  - [x] `st.cache_data`(TTL 부여, 예: 60s)로 model_info/grades 등 정적 응답 캐싱 — cutoff 시뮬레이션은 파라미터가 캐시 키에 포함되므로 그대로 캐싱 가능. **st.cache_resource는 클라이언트 세션에 쓰지 말 것**(requests.Session 공유 문제 불필요, 단순 함수로 충분).
- [x] Task 2: 화면① 성능 개요 (AC: #1)
  - [x] 데이터: `GET /v1/model/info` — champion/challenger 각각 `metrics.auc_oot`/`ks_oot`(+ champion `psi_score`), `sample_design` 블록.
  - [x] 챔피언 vs 챌린저 지표 비교(st.metric 나란히 + delta 표시), 표본설계 요약(train/valid/oot 빈티지, bad 정의) 카드.
  - [x] **정직성 원칙**: OOT 목표 미달 사실(챔피언 KS 0.2054<0.25, 챌린저 AUC 0.6452<0.70)을 숨기지 말고 목표선과 함께 표기 — "7변수 축소모형 + grade/int_rate 의도적 배제" 맥락 한 줄 병기(1-7a 리포트 원인분석 재사용). 면접 데모에서 이 투명성이 오히려 강점.
- [x] Task 3: 화면② 등급 분포 (AC: #1)
  - [x] 데이터: `GET /v1/grades?model=champion|challenger`(모델 선택 위젯).
  - [x] 등급별 관측 부도율 바차트(등급 1→10, 단조 증가가 한눈에 보이게) + 등급 경계 테이블(score_min/score_max, **우측폐구간 관례를 캡션에 명시** — API_SPEC §3).
  - [x] `monotonic_validated` 뱃지 표시. `observed_bad_rate=null`(OOT 무관측 등급) 가능성 방어 — null이면 차트에서 비우고 캡션 처리(2-3 deferred 항목 인지).
- [x] Task 4: 화면③ PSI 안정성 (AC: #1)
  - [x] 데이터: `GET /v1/model/info`의 `metrics.psi_score`(valid→OOT 점수 PSI). **변수별 PSI는 API에 없음** — AD-9상 대시보드가 frame을 직접 읽을 수 없으므로 이 화면의 스코프는 점수 PSI로 한정하고, 화면 캡션에 "변수별 PSI는 1.7b 리포트 참조" 링크 문구로 처리(스코프 확장 금지 — API에 엔드포인트를 추가하는 것은 이 스토리 소관 아님, 필요성이 생기면 deferred-work에 기록).
  - [x] PSI 게이지/불릿 형태 시각화: 실측값(챔피언 0.0017/챌린저 0.0013 수준) vs 경고선 0.1/0.25(업계 관행 임계). "무엇을 의미하는가" 해설 2~3문장(Evidently 드리프트 리포트 문법 참고 — 수치+임계선+판정을 한 카드에).
- [x] Task 5: 화면④ cutoff 시뮬레이션 — 리스크+손익 통합 (AC: #1)
  - [x] 데이터: `POST /v1/simulate/cutoff`(리스크) + `POST /v1/simulate/profit-cutoff`(손익). 모델 선택 + cutoff 슬라이더(리스크) + avg_loan_amnt 숫자 입력(손익, 기본 12000, **schemas 상한 10,000,000 이내로 위젯 max 설정** — 422 예방).
  - [x] 리스크 곡선(cutoff vs approval_rate/bad_rate 이중축 또는 두 패널)과 손익 곡선(cutoff vs expected_annual_profit, current/optimal 수직선 마커) — altair 사용(streamlit 내장 의존성 6.2.2, **plotly 미설치 — 새 의존성 추가 금지**).
  - [x] 손익 응답의 nullable 필드 방어(2.4 리뷰 반영: `expected_annual_profit`/`delta.*`가 null일 수 있음 — 현재 실데이터에선 발생 안 하지만 렌더링 크래시 금지) + `assumptions` 배열을 화면에 **항상** 표시(expander 가능하되 기본 접힘 금지 — 컨설팅 정직성 원칙, 2.4 1페이저와 동일 톤).
  - [x] 2.4의 핵심 발견(손익 최적 cutoff이 리스크 cutoff보다 훨씬 낮음, 승인율≈100%)이 화면에서 자연스럽게 드러나는지 확인 — current vs optimal 마커 간격이 데모 포인트.
- [x] Task 6: 테스트 + 배선 실증 + 에픽 DoD (AC: #3, #4)
  - [x] `tests/test_dashboard.py` — api_client 함수들의 URL/페이로드 구성(requests mock 또는 responses 없이 monkeypatch로 충분), degraded 처리 분기, nullable 응답 방어 로직. **Streamlit 렌더링 자체는 테스트하지 않음**(streamlit.testing.v1.AppTest 사용은 선택 — 4화면 스모크 정도면 가치 있음, 과투자 금지).
  - [x] 라이브 실증: uvicorn + `streamlit run dashboard/app.py` 동시 구동 → 4화면 각각 스크린샷 → cutoff 슬라이더 조작 시 uvicorn 로그에 새 POST 찍히는 것 확인(네트워크 배선 증빙, 프론트 DoD 원칙).
  - [x] `pytest -q` 전체 통과(기존 175 + 신규).
  - [x] 에픽 2 DoD: git 커밋 + 옵시디언 미러(`ob_storage\신용평가_CRM_사이드프로젝트\` — 에픽2 완료 요약, 13번 중간요약 노트 갱신 또는 14번 신규) + 데모 산출물(스크린샷).
  - [x] epic-2 상태 done 전환은 2-5 done + 에픽 DoD 확인 후 sprint-status.yaml에서.

### Review Findings (2026-07-16, 3-레이어 리뷰: Blind/Edge/Auditor)

- [x] [Review][Patch] HTTP 200 + 비JSON body 시 `resp.json()`이 try 밖이라 ApiUnavailable로 매핑 안 됨 — 화면 raw traceback 크래시 [dashboard/api_client.py:42-59] (blind+edge, High)
- [x] [Review][Patch] `grades: []` 빈 목록 시 등급 테이블의 컬럼 선택이 KeyError — 차트만 가드되고 테이블은 무방비 [dashboard/app.py:279-283] (blind+edge+auditor, High)
- [x] [Review][Patch] 화면① 메트릭이 present-but-null(`auc_oot: null` 등, loader._clean이 실제로 None 반환 가능) 시 `f"{None:.4f}"`/`None - 0.25` TypeError [dashboard/app.py:202-220] (blind+edge+auditor, High)
- [x] [Review][Patch] `delta.approval_rate_pp` null 시 "None pp 승인율" 리터럴 표시 — em-dash 처리 누락(다른 nullable 필드는 전부 처리됨) [dashboard/app.py:371] (blind+edge+auditor, Med)
- [x] [Review][Patch] altair color `range`만 주고 `domain` 미고정 — Vega-Lite가 카테고리를 정렬 순서로 색 배정해 현재/최적 마커 색이 의도와 뒤바뀔 수 있음(리스크 차트도 동일 패턴) [dashboard/app.py:348,394-404] (blind, Med)
- [x] [Review][Patch] current/optimal cutoff이 null이면 rule 레이어가 조용히 사라지거나 깨진 차트 — curve는 null 필터하면서 rule은 안 함 [dashboard/app.py:394-398] (blind+edge, Med)
- [x] [Review][Patch] `DASHBOARD_API_URL=""`(빈 문자열) 시 MissingSchema로 오해 소지 있는 에러 — `or DEFAULT` 폴백 필요 [dashboard/api_client.py:26-30] (edge, Low)
- [x] [Review][Patch] `_post` 에러 경로·200+비JSON 경로 테스트 부재(_get만 커버) — 위 1번 수정과 함께 회귀 테스트 추가 [tests/test_dashboard.py] (blind, Low)
- [x] [Review][Defer] 슬라이더 드래그 틱마다 blocking POST(10s 타임아웃) — 로컬 데모+사전계산 조회(ms 단위)라 실사용 영향 없음, 원격 API로 전환 시 debounce 검토 [dashboard/app.py:327-328] — deferred
- [x] [Review][Defer] health 게이트(매 rerun)와 60s TTL 캐시의 정합 창 — 재시작 직후 최대 60초 구모델 메트릭 표시 가능, 로컬 데모 수용 [dashboard/app.py:160-177] — deferred
- [x] [Review][Defer] `CURRENT_CUTOFF=546.0` 대시보드 하드코딩 — 슬라이더 초기값 시드로만 쓰이고 표시값은 전부 API 응답이지만, API의 current_cutoff와 드리프트 가능(챌린저는 547.6) [dashboard/app.py] — deferred

dismiss 3건: ①`delta: null` 객체 AttributeError(ProfitCutoffResponse가 delta를 필수 객체로 구성 — 스키마상 불가) ②curve point의 `cutoff` 키 부재 melt KeyError(CurvePoint.cutoff는 required float) ③`get_health()`→`check_health()` 명명 차이(문서 표기 문제, 동작 동일).

## Dev Notes

### 이 스토리의 성격 — Epic 2 피날레, "보여주는" 스토리
계산은 전부 이전 스토리들이 끝냈다. 이 스토리의 리스크는 수식이 아니라 **배선과 시연 품질**: ① AD-9 위반(편하다고 parquet 직접 읽기) ② 화면은 떴는데 실제 API를 안 부르는 목업 ③ 데모 중 API 다운 시 크래시. 세 가지 모두 Tasks에 방어 장치 명시.

### AD-9가 이 스토리의 헌법
`dashboard/`는 **오직 HTTP**로만 데이터를 가져온다. `import scorecard.*`, `pd.read_parquet(...)`, `joblib.load(...)`가 dashboard/ 안에 하나라도 있으면 아키텍처 위반. 코드리뷰에서 가장 먼저 grep될 항목. PSI 화면에서 변수별 PSI가 탐나도 API에 없으면 안 보여주는 게 맞다(스코프 가드 참조).

### 소비 가능한 API 전량 (2.3+2.4 구현 완료분)
| 엔드포인트 | 화면 | 비고 |
|---|---|---|
| GET /health | 공통 가드 | degraded 시 안내 화면 |
| GET /v1/model/info | ①성능, ③PSI | champion.metrics에 psi_score 포함(challenger도 동일 구조 — 구현 확인: loader._metrics가 양쪽 다 psi_score 반환) |
| GET /v1/grades?model= | ②등급분포 | 우측폐구간, observed_bad_rate null 가능 |
| POST /v1/simulate/cutoff | ④cutoff | curve 포함 |
| POST /v1/simulate/profit-cutoff | ④cutoff | nullable 필드(2.4 리뷰), assumptions 필수 표시 |
| POST /v1/score, /v1/score/batch | (선택) | 4화면 AC에 없음 — 여유 있으면 단건 스코어링 데모 탭 추가 가능하나 **AC 우선, 스코프 크리프 주의** |

### UX 레퍼런스 (2026-07-13 조사분, 준비도 리포트 §4 — dev 컨텍스트 첨부 지시사항)
조사 원문 요지: Streamlit 크레딧 리스크 대시보드 4종 + Evidently 드리프트 리포트 문법 + Dribbble/Behance 핀테크 톤. 적용 지침:
- **레이아웃**: wide 모드, 화면당 "핵심 숫자 카드(st.metric 3~4개) 상단 → 차트 본문 → 해설/가정 하단" 3단 구성. 크레딧 대시보드 관행 = 숫자 먼저, 차트는 근거.
- **Evidently 문법**(PSI 화면): 지표값 + 임계선(0.1/0.25) + 판정(OK/Warning) + "이 지표가 뭔가" 1문단을 한 카드에 묶기. 판정 색상은 텍스트 뱃지로(초록 OK).
- **핀테크 톤**: 채도 낮은 배경 + 포인트 컬러 1개(파랑 계열), 이모지 남발 금지, 숫자는 천단위 콤마·% 포맷 통일. Streamlit 기본 테마로 충분 — 커스텀 CSS 해킹 금지(유지보수·데모 안정성).
- **5분 데모 동선**: 사이드바 순서 = 성능→등급→PSI→cutoff (모형 신뢰 구축 후 전략 제안으로 끝나는 내러티브). 각 화면 상단 1줄 요지 캡션.

### 재사용 지도
- `dashboard/` 디렉토리 이미 존재(빈 폴더, 1.1 스캐폴딩) — 새로 만들 필요 없음.
- streamlit 1.59.1 / altair 6.2.2 / requests 2.34.2 **전부 .venv에 설치 확인 완료** — requirements.txt에 streamlit>=1.38 이미 있음. plotly 없음(추가 금지).
- 서버 기동: `./.venv/Scripts/python -m uvicorn app.main:app --port 8000` (2.3/2.4 실증에서 사용한 그대로).
- 등급·PSI·cutoff의 실측 기대값은 2.1~2.4 리포트에 있음 — 화면 수치가 이와 일치하는지 대조(champion PSI 0.0017, 등급 부도율 4.07%→23.57%, 손익 optimal 494.4/546.0 등).

### 아키텍처 가드레일
- **AD-9**: dashboard→app HTTP만. 역방향·우회 금지.
- **AD-5**: API 스키마는 API_SPEC.md가 구속 — 대시보드 사정으로 응답 필드를 바꾸고 싶으면 스펙 먼저(단, 이 스토리에서 API 변경은 원칙적으로 불필요·비권장).
- **AD-8**: 로컬 2프로세스(uvicorn+streamlit). 도커·배포 금지.
- **NFR1**: 대시보드는 표시만 — 자체 계산(재집계·재점수화) 금지, 반올림·포맷팅만 허용.

### 스코프 가드 (하지 말 것)
- API 엔드포인트 추가/변경 금지(변수별 PSI 포함) — 필요하면 deferred-work.md에 기록만.
- 인증·멀티유저·세션 관리 금지(AD-8 로컬 데모).
- swap-set 화면·룰 진단 화면 금지(각각 AC 밖, 3.1 소관).
- 커스텀 CSS/HTML 해킹, plotly 등 신규 의존성 추가 금지.

### 이전 스토리 인텔리전스 (2.4 인수인계)
- 2.4 리뷰 교훈: profit 응답의 `expected_annual_profit`/`delta.*`는 nullable — 소비자(=이 대시보드)가 null 방어해야 함. `avg_loan_amnt`는 gt=0, le=10,000,000, inf/nan 422.
- 2.3 리뷰 교훈: `/v1/grades`의 `observed_bad_rate`는 OOT 무관측 등급에서 null 가능.
- 2.2 교훈: reason_codes는 0~3개(빈 배열 = SAFE 신청자가 정상) — 스코어링 데모 탭을 추가할 경우에만 해당.
- 프론트 DoD(플러드이스케이프 3.3 반려 교훈, 사용자 피드백): **화면 존재≠배선**. 네트워크 로그 + 라이브 조작 증빙 필수 — Task 6에 반영됨.
- 공통 패턴: 실행이 버그를 잡는다 — 합성 mock으로 초록 만들고 끝내지 말고 반드시 두 프로세스 라이브로 띄워 실제 응답으로 확인.

### Project Structure Notes
- `dashboard/app.py` — NEW (엔트리포인트 + 4화면 함수).
- `dashboard/api_client.py` — NEW (유일한 HTTP 계층).
- `tests/test_dashboard.py` — NEW.
- `requirements.txt` — 변경 없음(전부 기설치).
- 스크린샷: `docs/implementation-artifacts/dashboard-screenshots-2-5/` — NEW.

### References
- [Source: docs/planning-artifacts/epics.md#Story-2.5] — AC 원문(FR13, AD-9)
- [Source: API_SPEC.md §1-§7] — 소비할 응답 스키마 전량 (§8 rules는 3.1 소관)
- [Source: ARCHITECTURE-SPINE.md#AD-8,AD-9] — 로컬 envelope, 의존 방향
- [Source: docs/planning-artifacts/implementation-readiness-report-2026-07-13.md §4] — UX 레퍼런스 첨부 지시
- [Source: docs/implementation-artifacts/2-4-profit-based-cutoff.md] — nullable 계약·실측 수치
- [Source: docs/implementation-artifacts/evaluation-grading-report-1-7a.md] — OOT 목표 미달 원인분석(화면① 정직성 문구 재료)

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

- Streamlit 페이지가 열린 websocket을 계속 유지해 networkidle에 도달하지 않음 → Claude Browser 페인의 스크린샷 도구가 30초 타임아웃. 대안으로 텍스트 추출(get_page_text)로 각 화면 렌더 검증 + Playwright MCP(고정 타임아웃)로 스크린샷 4장 캡처. 라디오 `<input>`이 오버레이에 가려 클릭 인터셉트 → 라벨 텍스트(getByText) 클릭으로 우회.
- 사이드바가 좁은 뷰포트(1280)에서 접힘 → 1600폭으로 리사이즈 후 라디오 노출.

### Completion Notes List

- **배선 실증 완료(프론트 DoD)**: uvicorn+streamlit 2프로세스 라이브 구동. uvicorn 액세스 로그로 각 화면이 실제 API를 호출함을 증빙 — 로드 시 `GET /health`+`GET /v1/model/info`, cutoff 화면 진입 시 `POST /v1/simulate/cutoff`+`POST /v1/simulate/profit-cutoff`. **라이브 조작 증빙**: 모델 라디오를 challenger로 전환하니 서버 로그에 `model_version=challenger-1.0.0`(current=547.6, optimal=507.1)로 새 요청이 재발화 — 화면이 목업이 아니라 실제 재조회함을 확인. 화면 존재≠배선 원칙 충족.
- **4화면 실측 수치 대조 통과**: 성능(챔피언 KS 0.2054/PSI 0.0047, 챌린저 AUC 0.6452 — 1.7a/1.7b 리포트 일치), 등급(10등급 단조, 우측폐구간 캡션), PSI(챔피언 0.0047/챌린저 0.0030, 둘 다 OK 판정), cutoff(리스크 곡선 + 손익 optimal 494.43 vs current 546.01, +52.29pp, ₩131.8M — 2.4 발견 재현).
- **AD-9 준수**: dashboard/는 `dashboard.api_client`(requests) 단일 HTTP 계층만 사용. `import scorecard`/`read_parquet`/`joblib` 없음. 화면 코드는 api_client 함수만 호출.
- **스코프 가드 준수**: 변수별 PSI(API 부재)는 화면에서 캡션 안내로 처리하고 엔드포인트 추가 안 함. plotly 등 신규 의존성 없이 altair(기설치)만 사용. 스코어링 데모 탭 등 AC 밖 기능 미추가.
- **nullable/degraded 방어**: `expected_annual_profit`/`delta.*`/`observed_bad_rate` null을 `grades_to_chart_rows`/`profit_curve_to_rows`/`fmt_*` 헬퍼에서 방어(단위테스트로 고정). API 다운/degraded 시 health 게이트가 `st.error`+기동 명령 안내 후 `st.stop()` — 크래시 없음.
- pytest **185 passed**(기존 175 + dashboard 10). 스크린샷 4장 `docs/implementation-artifacts/dashboard-screenshots-2-5/`.

### File List

- `dashboard/api_client.py` (NEW — 유일한 HTTP 계층, ApiUnavailable, DASHBOARD_API_URL)
- `dashboard/app.py` (NEW — 엔트리포인트 + 4화면 함수 + 순수 표시 헬퍼 fmt_pct/fmt_krw/grades_to_chart_rows/profit_curve_to_rows)
- `tests/test_dashboard.py` (NEW — 10 tests: api_client URL/payload/degraded/error, 헬퍼 null 방어)
- `docs/implementation-artifacts/dashboard-screenshots-2-5/{01-performance,02-grades,03-psi,04-cutoff}.png` (NEW — 4화면 라이브 스크린샷)

## Change Log

- 2026-07-16: 3-레이어 코드리뷰(Blind/Edge/Auditor) — patch 8건 반영(200+비JSON ApiUnavailable 매핑·빈 grades 테이블 가드·화면① null 메트릭 fmt_metric/target_delta·"None pp" 방어·altair color domain 고정·rule null 필터·빈 env 폴백·회귀 테스트 4건), defer 3건 deferred-work.md 기록, dismiss 3건. pytest 189 passed, 라이브 재검증(리스크/손익 차트 색 매핑 DOM 확인). Status → done.
- 2026-07-16: Story 2.5 구현 — dashboard/api_client.py(HTTP 단일 계층, AD-9)+app.py(4화면). uvicorn+streamlit 라이브 구동, 액세스 로그+모델 전환 재조회로 배선 실증. 4화면 실측 수치 대조 통과, 스크린샷 4장 확보. pytest 185 passed(+10). Status → review.
- 2026-07-16: Story 2.5 생성 — 소비 가능 API 전량 매핑(변수별 PSI 부재 → 화면 스코프 한정 결정), UX 레퍼런스(2026-07-13 조사분) 적용 지침으로 구체화, 배선 실증 DoD(네트워크 로그+라이브 조작) 명시, altair 사용 확정(plotly 미설치·신규 의존성 금지), nullable 응답 방어 인수인계.
