# Story 2.3: FastAPI 스코어링 서빙

Status: ready-for-dev

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

- [ ] Task 1: `app/loader.py` — 아티팩트 로딩 계층 (AC: #3, AD-4)
  - [ ] 시작 시 1회 로드: `champion_model.joblib`({"model","binners"}), `challenger_model.joblib`({"model","calibrator"}), 두 manifest(JSON), `data/scored_validation_frame.parquet`
  - [ ] **bundle 필수 키 명시 검증**(2.2 defer 인수인계 — 어느 파일의 어떤 키가 없는지 말하는 명확한 에러). manifest의 `feature_order`·`grade_thresholds`·`pdo`/`base_score`/`base_odds` 존재 검증
  - [ ] 파일 부재/검증 실패 시 앱은 뜨되 `model_loaded=False` 상태 유지(→ /health degraded, 업무 엔드포인트 503) — 크래시하지 않는다(P3가 /health로 가용성 판단)
  - [ ] 학습·재적합·아티팩트 쓰기 코드 금지(AD-4). `scorecard/` 모듈만 import(AD-9 방향 준수: app→scorecard)
- [ ] Task 2: `app/schemas.py` — pydantic 요청/응답 스키마 (AC: #1, AD-5)
  - [ ] 입력 스키마는 **manifest `feature_order` 7개 필드**(fico_range_low, annual_inc, dti, home_ownership, revol_util, inq_last_6mths, purpose) — API_SPEC §4의 12필드 예시는 "IV 변수선정(FR-5) 결과로 최종 확정" 전 예상 후보였고, FR-5 확정 결과가 7개(1.4). **API_SPEC §4에 확정 스키마를 반영(AD-5: 스펙 먼저 수정 후 구현)**
  - [ ] 결측 허용: 전 필드 `| None`(WOE Missing 빈 처리, 1.4 metric_missing 계약) — 단 전 필드 null이면 의미 없으므로 최소 1개 non-null 검증
  - [ ] 응답 스키마: score/pd/grade/reason_codes(2.2의 ReasonCode 모델 재사용)/warnings/model 블록. `model=both` 시 champion/challenger/score_gap
- [ ] Task 3: 조회 3종 — /health, /v1/model/info, /v1/grades (AC: #1)
  - [ ] `/health`: 미로드 시 `status:"degraded"` + **HTTP 200**(spec 명시 — 503 아님)
  - [ ] `/v1/model/info`: manifest 메타 + **metrics는 scored validation frame(AD-3)에서 시작 시 1회 계산**(oot 행의 AUC/KS + PSI: valid→oot, `evaluation.compute_metrics`·`population_stability_index` 재사용 — 재계산이 아니라 frame 소비이므로 AD-3 위반 아님, 수치는 1.7a/b 리포트 실측값과 일치해야 함: 챔피언 AUC_oot≈0.643/KS≈0.205, PSI≈0.0017)
  - [ ] `/v1/grades`: manifest `grade_thresholds` 기반 등급표 + frame에서 등급별 observed_bad_rate 계산, `monotonic_validated`(grading.validate_monotonic)
- [ ] Task 4: POST /v1/score(핵심) + /v1/score/batch (AC: #1, #2, #4)
  - [ ] champion: raw→`_normalize` 계열 전처리→`binning.transform_woe`(AD-2)→`champion.score_applicant`→p_bad(`evaluation.champion_p_bad` 경로)→`grading.assign_grade`(champion thresholds)→`reasons.champion_reason_codes`
  - [ ] challenger: `evaluation.challenger_p_bad`(calibrated)→`evaluation.generalized_score`→challenger thresholds 등급→`reasons.challenger_reason_codes`
  - [ ] `model` 쿼리 파라미터 champion(기본)|challenger|both. both: `{"champion":{...},"challenger":{...},"score_gap":float}`
  - [ ] 400 VALUE_OUT_OF_RANGE: 수치 필드가 **학습 관측 범위의 하드 배수 초과**(스토리오너 결정 필요 — 권장: manifest `woe_bin_edges` 최외곽 유한 경계의 ±10배 또는 상식 상한 dti>1000 등, 결정과 근거를 Dev Notes/리포트에 기록). 경계 근처(범위 밖이지만 차단 기준 미만)는 200 + `warnings`
  - [ ] batch: JSON 배열 최대 1,000건(초과 422), 응답 = 단건 배열 + `grade_distribution` 요약
  - [ ] 요청별 `model_version` 로깅(AC #5) — logging 표준 모듈, 미들웨어 또는 엔드포인트 공통 의존성
- [ ] Task 5: POST /v1/simulate/cutoff (AC: #1)
  - [ ] **`strategy.py` 재사용**(2.1 산출물 — `cutoff_trade_off_curve`·`lookup_cutoff`를 frame에 적용, 재구현 금지). 응답: cutoff_score/approval_rate/bad_rate_approved/bad_rate_rejected/curve
  - [ ] `bad_rate_rejected`는 strategy.py에 없음 — 거절집단(score<cutoff) 부도율 계산 추가는 **app 계층이 아니라 strategy.py에 추가**(scorecard가 로직 소유, app은 조립만 — AD-9 정신). strategy.py 수정 시 기존 2.1 테스트 불변 확인
- [ ] Task 6: 에러 계약 + P3 예시 (AC: #4, #6)
  - [ ] 503 MODEL_NOT_LOADED(전 업무 엔드포인트, 로더 미로드 시), 400 VALUE_OUT_OF_RANGE, 422(FastAPI 기본 — 단 `error_code` 필드 추가 여부는 spec이 "FastAPI 기본"이라 하므로 기본 형태 유지 허용, `detail`+`error_code` 포맷은 400/503에 적용)
  - [ ] `docs/implementation-artifacts/p3-examples-2-3.md`(또는 json) — /health→/v1/score?model=champion→/v1/grades 순 실제 요청/응답 페어(§9 P3 소비 순서)
- [ ] Task 7: pytest + 성능 + 라이브 실증 (AC: #2, 전체)
  - [ ] `tests/test_app.py` — 6개 엔드포인트 정상 경로, 에러 3종, model=both, batch 상한, 결측 필드 스코어링, grade 정합(등급표와 단건 응답 등급 일치)
  - [ ] p95 계측: TestClient로 /v1/score 워밍업 후 ≥20회, p95<300ms assert(수치는 리포트 기록)
  - [ ] 라이브 uvicorn 기동 → 실제 HTTP로 6개 엔드포인트 호출 실증(응답을 P3 예시 문서에 사용)
  - [ ] `pytest -q` 전체 통과(기존 128 + 신규)

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

### Debug Log References

### Completion Notes List

### File List

## Change Log

- 2026-07-16: Story 2.3 생성 — API_SPEC 6개 엔드포인트, 재사용 지도(Epic1+2.1+2.2 함수 시그니처), 성능 캐싱 전략(SHAP explainer·curve 사전계산), 입력 스키마 7필드 확정(AD-5 스펙 선수정), bad_rate_rejected는 strategy.py에 추가(app은 조립만), 2.2 defer(bundle 키 검증) 인수.
