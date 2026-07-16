---
baseline_commit: 3529544
---

# Story 2.3: FastAPI 스코어링 서빙

Status: done

## Story

As a P3 에이전트(그리고 대시보드),
I want HTTP API로 점수·PD·등급·사유·cutoff 시뮬레이션을 조회하고,
so that 판정 로직 없이 스코어링 결과를 소비할 수 있다.

## Acceptance Criteria

**Given** Epic 1의 frozen 아티팩트(`models/artifacts/*.joblib` + manifest)와 validation frame(`data/scored_validation_frame.parquet`)
**When** `app/`을 uvicorn으로 구동하면

1. API_SPEC.md의 기본 6개 엔드포인트(`GET /health`, `GET /v1/model/info`, `GET /v1/grades`, `POST /v1/score`, `POST /v1/score/batch`, `POST /v1/simulate/cutoff`)가 스키마 그대로 동작한다 (FR12, AD-5)
2. `/v1/score` p95 < 300ms (NFR2), 전 엔드포인트 pytest 통과 (NFR3)
3. `app/`은 로드만 하고 학습·아티팩트 변경을 하지 않으며(AD-4), 비닝은 `binning.py` import로 처리한다(AD-2)
4. 에러 응답 3종(422 스키마 위반, 400 `VALUE_OUT_OF_RANGE`, 503 `MODEL_NOT_LOADED`)이 API_SPEC §0 포맷(`detail`+`error_code`)으로 반환되고 pytest로 검증된다
5. 요청별 `model_version`이 로그에 남는다 (컨벤션)
6. P3용 예시 요청/응답 페어가 `docs/` 하위에 저장된다

> 성공기준 계량화(스토리 오너 보강): 위 6개 AC + `pytest -q` 초록 + **라이브 uvicorn 기동 후 실제 HTTP 호출로 6개 엔드포인트 전부 실증**(TestClient만으로 끝내지 않음 — 프론트 DoD "배선 실증" 원칙의 백엔드판). p95는 TestClient 반복 측정(워밍업 제외 ≥20회)으로 계측해 리포트에 수치 기록.

## Tasks / Subtasks

- [x] Task 1: `app/loader.py` — 아티팩트 로딩 계층 (AC: #3, AD-4)
  - [x] 시작 시 1회 로드: `champion_model.joblib`({"model","binners"}), `challenger_model.joblib`({"model","calibrator"}), 두 manifest(JSON), `data/scored_validation_frame.parquet`
  - [x] **bundle 필수 키 명시 검증**(2.2 defer 인수인계 — 어느 파일의 어떤 키가 없는지 말하는 명확한 에러). manifest의 `feature_order`·`grade_thresholds`·`pdo`/`base_score`/`base_odds` 존재 검증
  - [x] 파일 부재/검증 실패 시 앱은 뜨되 `model_loaded=False` 상태 유지(→ /health degraded, 업무 엔드포인트 503) — 크래시하지 않는다(P3가 /health로 가용성 판단)
  - [x] 학습·재적합·아티팩트 쓰기 코드 금지(AD-4). `scorecard/` 모듈만 import(AD-9 방향 준수: app→scorecard)
- [x] Task 2: `app/schemas.py` — pydantic 요청/응답 스키마 (AC: #1, AD-5)
  - [x] 입력 스키마는 **manifest `feature_order` 7개 필드**(fico_range_low, annual_inc, dti, home_ownership, revol_util, inq_last_6mths, purpose) — API_SPEC §4의 12필드 예시는 "IV 변수선정(FR-5) 결과로 최종 확정" 전 예상 후보였고, FR-5 확정 결과가 7개(1.4). **API_SPEC §4에 확정 스키마를 반영(AD-5: 스펙 먼저 수정 후 구현)**
  - [x] 결측 허용: 전 필드 `| None`(WOE Missing 빈 처리, 1.4 metric_missing 계약) — 단 전 필드 null이면 의미 없으므로 최소 1개 non-null 검증
  - [x] 응답 스키마: score/pd/grade/reason_codes(2.2의 ReasonCode 모델 재사용)/warnings/model 블록. `model=both` 시 champion/challenger/score_gap
- [x] Task 3: 조회 3종 — /health, /v1/model/info, /v1/grades (AC: #1)
  - [x] `/health`: 미로드 시 `status:"degraded"` + **HTTP 200**(spec 명시 — 503 아님)
  - [x] `/v1/model/info`: manifest 메타 + **metrics는 scored validation frame(AD-3)에서 시작 시 1회 계산**(oot 행의 AUC/KS + PSI: valid→oot, `evaluation.compute_metrics`·`population_stability_index` 재사용 — 재계산이 아니라 frame 소비이므로 AD-3 위반 아님, 수치는 1.7a/b 리포트 실측값과 일치해야 함: 챔피언 AUC_oot≈0.643/KS≈0.205, PSI≈0.0017)
  - [x] `/v1/grades`: manifest `grade_thresholds` 기반 등급표 + frame에서 등급별 observed_bad_rate 계산, `monotonic_validated`(grading.validate_monotonic)
- [x] Task 4: POST /v1/score(핵심) + /v1/score/batch (AC: #1, #2, #4)
  - [x] champion: raw→`_normalize` 계열 전처리→`binning.transform_woe`(AD-2)→`champion.score_applicant`→p_bad(`evaluation.champion_p_bad` 경로)→`grading.assign_grade`(champion thresholds)→`reasons.champion_reason_codes`
  - [x] challenger: `evaluation.challenger_p_bad`(calibrated)→`evaluation.generalized_score`→challenger thresholds 등급→`reasons.challenger_reason_codes`
  - [x] `model` 쿼리 파라미터 champion(기본)|challenger|both. both: `{"champion":{...},"challenger":{...},"score_gap":float}`
  - [x] 400 VALUE_OUT_OF_RANGE: 수치 필드가 **학습 관측 범위의 하드 배수 초과**(스토리오너 결정 필요 — 권장: manifest `woe_bin_edges` 최외곽 유한 경계의 ±10배 또는 상식 상한 dti>1000 등, 결정과 근거를 Dev Notes/리포트에 기록). 경계 근처(범위 밖이지만 차단 기준 미만)는 200 + `warnings`
  - [x] batch: JSON 배열 최대 1,000건(초과 422), 응답 = 단건 배열 + `grade_distribution` 요약
  - [x] 요청별 `model_version` 로깅(AC #5) — logging 표준 모듈, 미들웨어 또는 엔드포인트 공통 의존성
- [x] Task 5: POST /v1/simulate/cutoff (AC: #1)
  - [x] **`strategy.py` 재사용**(2.1 산출물 — `cutoff_trade_off_curve`·`lookup_cutoff`를 frame에 적용, 재구현 금지). 응답: cutoff_score/approval_rate/bad_rate_approved/bad_rate_rejected/curve
  - [x] `bad_rate_rejected`는 strategy.py에 없음 — 거절집단(score<cutoff) 부도율 계산 추가는 **app 계층이 아니라 strategy.py에 추가**(scorecard가 로직 소유, app은 조립만 — AD-9 정신). strategy.py 수정 시 기존 2.1 테스트 불변 확인
- [x] Task 6: 에러 계약 + P3 예시 (AC: #4, #6)
  - [x] 503 MODEL_NOT_LOADED(전 업무 엔드포인트, 로더 미로드 시), 400 VALUE_OUT_OF_RANGE, 422(FastAPI 기본 — 단 `error_code` 필드 추가 여부는 spec이 "FastAPI 기본"이라 하므로 기본 형태 유지 허용, `detail`+`error_code` 포맷은 400/503에 적용)
  - [x] `docs/implementation-artifacts/p3-examples-2-3.md`(또는 json) — /health→/v1/score?model=champion→/v1/grades 순 실제 요청/응답 페어(§9 P3 소비 순서)
- [x] Task 7: pytest + 성능 + 라이브 실증 (AC: #2, 전체)
  - [x] `tests/test_app.py` — 6개 엔드포인트 정상 경로, 에러 3종, model=both, batch 상한, 결측 필드 스코어링, grade 정합(등급표와 단건 응답 등급 일치)
  - [x] p95 계측: TestClient로 /v1/score 워밍업 후 ≥20회, p95<300ms assert(수치는 리포트 기록)
  - [x] 라이브 uvicorn 기동 → 실제 HTTP로 6개 엔드포인트 호출 실증(응답을 P3 예시 문서에 사용)
  - [x] `pytest -q` 전체 통과(기존 128 + 신규)

### Review Findings (code review 2026-07-16, Blind Hunter + Edge Case Hunter + Acceptance Auditor 병렬 — patch 12/defer 3/dismiss 3)

- [x] [Review][Patch] **등급 경계가 우측폐구간인데 문서·테스트가 반대 방향으로 가정**(High, 두 리뷰어 독립 발견) [app/loader.py:_grade_table, tests] — `score_min`은 배타적·`score_max`는 포함이 맞는데 테스트가 `score>=score_min`으로 검증하고 있었음(정확히 경계인 점수는 사실 한 등급 아래). docstring에 명시 + API_SPEC §3에 경계 규칙 문서화 + 테스트 방향 수정 + 경계 실증 테스트 신규.
- [x] [Review][Patch] **`/v1/model/info` 메트릭에 NaN 관통 시 JSON 직렬화 파괴**(High) [app/loader.py:_frame_metrics] — 다른 모든 경로는 NaN 가드가 있는데 이 사전계산 값만 없었음. `_clean()`로 비유한 값→None 정규화.
- [x] [Review][Patch] **미확인 카테고리 값이 두 모델 다 조용히 통과**(실증 확인 — champion은 Special-bin WOE≈0, challenger는 크래시 없이 예측) [app/loader.py, app/main.py] — 학습 시점 카테고리 목록을 champion binner에서 추출해 `STORE.known_categories`로 저장, 미확인 값은 경고로 노출(차단은 아님). 라이브 실증 완료.
- [x] [Review][Patch] **배치: 하나가 잘못되면 전체 폐기 + 어느 건인지 안 알려줌**(500번째에서 실패 시 이미 SHAP 계산한 499건 낭비) [app/main.py:score_batch] — 스코어링 전에 **전건 선검증**으로 변경, 에러 메시지에 `applicant[i]` 인덱스 포함. 라이브 실증.
- [x] [Review][Patch] **`model=both`에서 warnings 리스트 객체 공유(에일리어싱) + 챔피언 전용 문구가 챌린저에도 붙음** [app/main.py:score] — 모델별로 `_check_bounds` 독립 호출, 문구를 모델 중립적으로 단순화("is missing"만, WOE/네이티브 NaN 언급 제거).
- [x] [Review][Patch] **미문서 예외가 계약 밖 500으로 새어나감**(422/400/503 3종 외) [app/main.py] — `Exception` 핸들러 추가, `{detail, error_code:"INTERNAL_ERROR"}` 형태로 최소한 계약 형태는 유지.
- [x] [Review][Patch] **공유 SHAP TreeExplainer의 스레드 안전성이 검증되지 않음(동시 요청 시 위험)** [app/loader.py, app/main.py] — `threading.Lock` 추가(호출당 ~30ms, NFR2 300ms 예산 대비 비용 무시 가능, p95 재측정 33.0ms로 영향 없음 확인).
- [x] [Review][Patch] **필드명 오탈자가 조용히 무시되고 해당 필드가 "결측"으로 스코어링됨** [app/schemas.py] — `ScoreRequest`에 `extra="forbid"` 추가, 422로 전환.
- [x] [Review][Patch] **등급 groupby가 grade 컬럼 dtype 불일치 시 전부 None으로 조용히 실패할 수 있음** [app/loader.py:_grade_table] — groupby 전 `astype(int)` 명시 캐스팅.
- [x] [Review][Patch] **API_SPEC v0.3 스펙-구현 필드명 불일치 3건**(Acceptance Auditor) — `sample_design` 키(train_vintages 등 실제 구현에 맞춤), `/v1/grades`의 `pd_max`(미산출 필드라 스펙에서 제거 + 사유 명시), reason_codes의 `code`→`variable`(2.2 실제 필드명으로 스펙 예시 갱신).
- [x] [Review][Patch] **배치 `model` 파라미터가 타입 불일치(regex string vs Literal) + "both" 허용 여부 불문명** [app/main.py] — `ModelChoiceSingle` Literal 타입으로 정합, "both" 명시 거부(422) 테스트 추가.
- [x] [Review][Patch] **HARD_BOUNDS 경계값(FICO 300/850, annual_inc=0) 포함 여부 미검증** — 경계 포함 테스트 추가(실제 유효 신청자 케이스라 배타적으로 바뀌면 안 됨).
- [x] [Review][Patch] **극단 cutoff_score(관측범위 밖) 미검증** — 0%/100% 승인률 양끝 케이스 테스트 추가(None 필드 정상 처리 확인).
- [x] [Review][Defer] **점수 반올림(1자리)과 등급이 원값 기준이라 경계 부근에서 표시 불일치 가능**(코스메틱, 실사용 영향 낮음) — deferred-work.md.
- [x] [Review][Defer] **등급표에서 OOT 관측 0건인 등급이 monotonic 검증에서 조용히 제외됨** — grading.py 변경이 필요해 이 스토리 범위 밖, deferred-work.md.
- [x] [Review][Defer] **`/v1/score` 응답이 `SingleScoreResponse`/`BothScoreResponse` 두 타입이라 명시 response_model 없음** — FastAPI에서 쿼리파라미터에 따라 다른 셰이프를 반환하는 의도된 패턴(OpenAPI 문서화 개선은 후속 스토리), deferred-work.md.
- [x] [Review][Dismiss] **단일행 category 캐스팅이 잘못된 코드로 인코딩될 것이라는 의혹**(Blind Hunter #1) — **실증 기각**: 서로 다른 home_ownership/purpose 값이 실제로 다른 예측 확률을 낸다는 것을 직접 확인(2.2에서 이미 같은 계열 의혹을 20행 실증으로 기각한 것과 동일 메커니즘 — LightGBM booster가 `pandas_categorical`을 저장해 값 기준 재정렬).
- [x] [Review][Dismiss] **STORE를 import 시점에 무겁게 로드 + 재로드 경로 없음** — AD-8(로컬 단일 프로세스) 설계상 의도된 것, 재로드가 필요하면 프로세스 재시작.
- [x] [Review][Dismiss] **`dict[int,int]` grade_distribution의 JSON 키가 문자열로 직렬화됨** — JSON 표준 자체의 제약(객체 키는 항상 문자열), 코드 결함 아님.

## Dev Notes

### 이 스토리의 성격 — 첫 서빙 스토리, scorecard/의 순수 소비자
`app/`은 조립 계층이다: 로직은 전부 `scorecard/`에 이미 있다(1.4 binning, 1.5 champion, 1.6 challenger, 1.7a evaluation/grading, 1.7b generalized_score/PSI/frame, 2.1 strategy, 2.2 reasons). **app에 수식·변환 로직을 새로 쓰면 그 자체가 설계 오류 신호**다 — 없으면 scorecard 쪽에 추가하고 app은 호출만 한다(Task 5의 bad_rate_rejected가 그 예).

### 재사용 지도 (검증된 함수 시그니처)
- `champion_bundle = joblib.load(...)` → `{"model": LogisticRegression, "binners": dict}` / challenger → `{"model": LGBMClassifier, "calibrator": IsotonicRegression}`
- `evaluation.champion_p_bad(bundle, raw_df, variables)` / `challenger_p_bad(bundle, raw_df, variables)` — 1.7a가 만든 번들 소비 컨벤션(로드는 호출부=loader, 함수는 bundle 인자)
- `evaluation.generalized_score(p_bad)` — 두 모델 공통 Siddiqi 스케일(1.7b)
- `grading.assign_grade(scores, thresholds)` — thresholds는 각 manifest의 `grade_thresholds`(1.7b가 최종 기록, 등급 1=최우량)
- `reasons.champion_reason_codes(bundle, applicant_row, variables)` / `challenger_reason_codes(...)` — **variables는 반드시 manifest feature_order 그대로**(2.2 리뷰가 넣은 정렬 가드가 다른 순서를 거부함)
- `strategy.cutoff_trade_off_curve(frame_df, model_type, vintage=OOT)` — 2.1, frame 소비
- raw 신청 dtype 정합화는 `reasons._normalize_raw_applicant` 참고(2.2) — 단 app 입력은 pydantic이 이미 타입을 강제하므로 revol_util이 float으로 들어옴(문자열 파싱 불필요). **pydantic 스키마→DataFrame 변환 시 category 캐스팅만 필요**(challenger 경로)
- 2.2 실측 교훈: 단일행 Series→to_frame().T는 전 컬럼 object화 — pydantic dict에서 DataFrame을 만들 때 `pd.DataFrame([model_dump])`로 만들면 컬럼별 dtype이 보존됨(Series 경유 금지)

### 아키텍처 가드레일
- **AD-4**: app은 로드만. 아티팩트 파일 쓰기/재학습 코드 금지.
- **AD-2**: WOE는 `binning.transform_woe`만.
- **AD-5**: API_SPEC.md가 구속력. §4 입력 스키마를 7필드 확정본으로 **먼저 수정** 후 구현(v0.2→v0.3, 변경 이력 명시). §7(profit)·§8(rules)은 이 스토리 범위 밖 — 라우터 만들지 말 것(2.4/3.1 소관).
- **AD-9**: dashboard(2.5)가 이 API만 소비하게 됨 — 응답 필드명이 곧 계약.
- **NFR1**: 서빙 경로에 난수 없음(SHAP tree_path_dependent 결정적, isotonic 결정적).

### 성능 노트 (NFR2 p95<300ms)
- SHAP TreeExplainer 생성은 요청마다 하지 말 것 — **loader에서 1회 생성해 재사용**(2.2는 함수 내 생성이었으나 단건 분석용이었음. explainer는 상태 없는 재사용 안전 — 필요 시 reasons.py에 explainer 주입 파라미터를 추가하는 쪽이 scorecard 소유 원칙에 맞음).
- `/v1/simulate/cutoff`의 curve(101 cutoff × 283k행)는 요청마다 재계산하면 느릴 수 있음 — 시작 시 1회 계산·캐시(frame과 cutoff grid는 불변이므로 안전). 단건 lookup은 실시간.
- `_safest_woe`의 binning_table.build()도 요청마다 재계산 금지 — 캐시 고려(2.2 리뷰 Low 지적).

### 스코프 가드 (하지 말 것)
- §7 profit-cutoff(2.4), §8 rules/efficiency(3.1) 엔드포인트 금지.
- 인증/CORS/컨테이너화 금지(AD-8 로컬 전용).
- 판정(승인/거절) 로직 금지 — cutoff 적용은 소비자 몫(P3 계약, API_SPEC 헤더 문구).

### 이전 스토리 인텔리전스
- 2.2 defer 인수인계: **bundle 키 명시 검증은 이 스토리 loader가 정위치**(deferred-work.md).
- 2.1/2.2 공통: 실데이터/라이브 실행이 매번 실질 버그를 잡음 — TestClient 통과로 끝내지 말고 uvicorn 라이브 기동 실증(AC 계량화에 반영됨).
- 2.2 리뷰 교훈: 가드 추가 시 대응 테스트 동시 추가.

## Dev Agent Record

### Agent Model Used

claude-fable-5 (bmad-dev-story, /loop 자율 진행)

### Debug Log References

- **등급표 경계 버그를 정합성 테스트가 즉시 잡음**: `grade_thresholds`(11개)를 내부 임계로 해석해 12개 유령 등급 생성 → `test_grades_table_consistent_with_scoring`(등급표 vs 단건 스코어 등급 대조)이 첫 실행에서 실패(542.8점이 6등급인데 표의 6등급 하한이 544.8). 실제 의미는 **양끝 포함 bin 경계(len=n_grades+1, 바깥 open-ended)** — `grading._assign_bin`/`_bin_edges_open` 소스 확인 후 grade g = 구간 (edges[n_bins-g], edges[n_bins-g+1]]로 재작성.
- **AC #5(model_version 로깅)가 라이브 실증에서만 걸림**: TestClient+caplog은 자체 핸들러라 통과처럼 보이지만, uvicorn 하에선 app.* 로거에 핸들러가 없어 INFO가 전부 버려짐 → main.py에서 root 핸들러 부재 시 basicConfig 1회 설정. 라이브 로그로 재실증(scored applicant/cutoff simulation 두 라인).
- PSI 불일치 원인 확인: 1.7b 리포트는 **train→OOT**(0.0017), 서빙은 frame(valid+oot)만 소비 가능하므로 **valid→OOT**(0.0047) — 다른 비교축이며 둘 다 <0.1. /v1/model/info의 psi_score는 valid→oot로 문서화.
- p95 실측: **32.9ms**(p50 32.3ms) — SHAP explainer 시작 시 1회 생성(reasons.build_challenger_explainer 신설, challenger_reason_codes에 explainer 주입 파라미터 추가)·curve 101점 시작 시 사전계산 덕분에 NFR2(300ms) 대비 9배 여유.

### Completion Notes List

- **AD-5 스펙 선수정**: API_SPEC v0.2→v0.3 — §4 입력을 FR-5 확정 7필드로 교체, reason_codes 3개 미만 가능(2.2 결정) 명시, §6에 bad_rate_rejected 추가.
- **bad_rate_rejected는 strategy.py에 추가**(additive 컬럼, app은 조립만 — 2.1 테스트 12건 불변 통과), 2.2 defer였던 bundle 키 명시 검증은 loader에 구현(champion/challenger 각각 필수 키·manifest 필수 키, 어느 파일의 어떤 키가 없는지 말하는 에러).
- **VALUE_OUT_OF_RANGE 하드 경계(스토리오너 결정)**: 물리적/상식 한계(FICO 300-850, dti≤999, revol_util≤500, annual_inc≤1e9, inq≤100) — 학습 관측 범위 밖이지만 한계 내면 open-ended 외곽 WOE bin으로 정상 스코어링(+결측 warnings). 근거: 관측범위 기반 차단은 정상적 신규 고객(예: FICO 845)을 오차단.
- **미로드 degraded 계약**: /health는 200+degraded(spec 명시), 업무 엔드포인트는 503 MODEL_NOT_LOADED — 아티팩트 없이도 도는 always-on 테스트(monkeypatch 빈 store)로 커버.
- **라이브 실증 완료**: uvicorn:8100 기동, 6개 엔드포인트 실제 HTTP 호출(응답을 p3-examples-2-3.md에 수록), 400/422 에러 계약, model_version 로그 2종 확인.
- pytest **144 passed**(기존 129 + app 15). /v1/model/info 수치가 1.7a 실측(AUC 0.643/KS 0.2054)과 재현 일치.

### File List

- `app/loader.py` (NEW — ModelStore, 검증, 시작 시 사전계산: metrics·curves·grade tables·SHAP explainer)
- `app/schemas.py` (NEW — 7필드 ScoreRequest·응답 스키마·HARD_BOUNDS)
- `app/main.py` (NEW — 6 엔드포인트, ApiError 핸들러, 로깅)
- `scorecard/strategy.py` (MODIFIED — bad_rate_rejected additive)
- `scorecard/reasons.py` (MODIFIED — build_challenger_explainer + explainer 주입 파라미터)
- `tests/test_app.py` (NEW — 15 tests, p95 계측 포함)
- `API_SPEC.md` (MODIFIED — v0.3, AD-5 선수정)
- `docs/implementation-artifacts/p3-examples-2-3.md` (NEW — 라이브 실측 예시)

## Change Log

- 2026-07-16: Story 2.3 생성 — API_SPEC 6개 엔드포인트, 재사용 지도(Epic1+2.1+2.2 함수 시그니처), 성능 캐싱 전략(SHAP explainer·curve 사전계산), 입력 스키마 7필드 확정(AD-5 스펙 선수정), bad_rate_rejected는 strategy.py에 추가(app은 조립만), 2.2 defer(bundle 키 검증) 인수.
- 2026-07-16: Story 2.3 구현 — app/{loader,schemas,main}.py 신규, 6개 엔드포인트 전부 라이브 실증, p95=32.9ms(NFR2 9배 여유), 등급표 경계 버그·uvicorn 로깅 공백 2건을 정합성 테스트·라이브 실행이 각각 잡음. 144 passed. Status → review.
- 2026-07-16: 코드리뷰(3-레이어 병렬) 반영 — patch 12건(등급경계 문서화·NaN가드·미확인 카테고리 경고·배치 선검증+인덱스·warnings 에일리어싱·전역 예외핸들러·SHAP 락·extra=forbid·grade dtype 캐스팅·API_SPEC 필드명 3건 동기화·배치 model 타입·경계값 테스트), defer 3건, dismiss 3건(카테고리 인코딩 의혹 실증 기각). 라이브 재검증(unseen category 경고·배치 인덱스·422 typo·등급 경계) 완료. pytest 151 passed(+7). p95 재측정 33.0ms(영향 없음). Status → done.
