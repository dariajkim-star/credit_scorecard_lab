---
baseline_commit: 90fbe2b
---

# Story 1.6: LightGBM 챌린저와 Calibration

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 모형 개발자,
I want Optuna 튜닝 LightGBM에 calibration을 적용한 챌린저를 학습하고,
so that 챔피언과 성능·설명가능성 트레이드오프를 비교할 상대를 확보한다.

## Acceptance Criteria

**Given** 1.4의 최종 변수셋(WOE 변환 전 원변수 사용 가능 — 1.3까지 정제된 원값)
**When** `scorecard/challenger.py`로 Optuna 튜닝 후 isotonic/Platt calibration을 적용하면
1. calibration 전후 Brier score 개선이 확인되고 캘리브레이션 곡선이 산출된다 (FR5)
2. 챌린저 아티팩트와 manifest 필수키(`calibration_method`, `shap_background_sample_ref` 포함)가 저장된다 (AD-1)
3. 시드 고정으로 재실행 시 동일 결과가 재현된다 (NFR1)

> 성공기준 계량화(스토리 오너 보강): 위 3개 AC + `pytest -q` 초록. AC1의 "개선"은 valid split에서 `brier_score_loss(calibrated) <= brier_score_loss(uncalibrated)`로 판정(합성 데이터에서 반드시 개선되지 않을 수 있으니 테스트는 "계산이 정확히 되는지"를 검증하고, 실데이터에서 방향성을 확인). 동일 시드로 2회 fit한 모델의 `predict_proba` 출력이 완전히 동일해야 NFR1 통과.

## Tasks / Subtasks

- [x] Task 1: LightGBM 챌린저 학습 + Optuna 튜닝 (AC: 3)
  - [x] `tune_challenger(train_df, y_train, valid_df, y_valid, variables, n_trials, seed)` — Optuna TPESampler(seed) 최적화(`num_leaves`, `learning_rate`, `min_child_samples`, `n_estimators`), objective=valid logloss. train fit, valid 평가, OOT 미접근
  - [x] 원변수 사용 확인 — nullable Float64/Int64·category dtype 전부 변환 없이 fit(스파이크 실증대로 동작)
  - [x] `N_TRIALS=20`(스토리 오너 결정, 근거는 리포트)
  - [x] 재현성: 동일 seed 2회 fit → `predict_proba` 완전 동일(테스트로 검증, 실데이터로도 확인)
- [x] Task 2: Calibration (AC: 1)
  - [x] `fit_calibrator(model, valid_df, y_valid, variables, method="isotonic")` — valid 확률 vs 라벨로 IsotonicRegression(기본) 또는 sigmoid(1피처 LogisticRegression) fit
  - [x] `calibrated_predict_proba(model, calibrator, df, variables)`
  - [x] `brier_scores(model, calibrator, df, variables, y)` — 전후 비교(**실데이터: 0.11491→0.11480, 개선 확인**)
  - [x] `calibration_curve_data(model, calibrator, df, variables, y, n_bins)` — `sklearn.calibration.calibration_curve` 기반
- [x] Task 3: SHAP 배경표본 고정 (AC: 2 대비)
  - [x] `save_shap_background_sample(train_df, variables, out_path, n, seed)` — 결정론적 표본 추출 후 parquet 저장(동일 시드 재현 테스트 포함)
- [x] Task 4: 아티팩트 저장 (AC: 2 / AD-1)
  - [x] `save_challenger_artifact(model, calibrator, variables, shap_background_path, out_dir, calibration_method)` — `{"model","calibrator"}` joblib 번들(1.5 패턴 재사용)
  - [x] manifest 공통키 + `calibration_method`/`shap_background_sample_ref`(상대경로) 전부 포함
  - [x] `grade_thresholds` 의도적 생략(1.7 소관, 챔피언과 동일 근거)
- [x] Task 5: 학습 결과 리포트 (AC: 1)
  - [x] `docs/implementation-artifacts/challenger-report-1-6.md` — n_trials 근거, 실데이터 Brier/calibration curve/AUC 비교(챔피언 대비), 재실행 스니펫
- [x] Task 6: pytest 및 회귀 (AC: 3)
  - [x] `tests/test_challenger.py` — 10개 테스트(재현성, nullable/category dtype 수용, isotonic 단조성, 잘못된 method 거부, 확률 범위, Brier 계산, calibration curve 구조, SHAP 표본 결정론성·행수 캡, 아티팩트 저장→재로드 예측 완전일치, manifest 필수키)
  - [x] `pytest -q` → **65 passed** (기존 55 + 신규 10)
  - [x] **실데이터 실행 완료**: Optuna 20 trials 약 27초(실 train 143,892행), Brier 0.11491→0.11480(개선), calibration curve "after"가 관측치와 거의 일치, sanity AUC train/valid/oot = 0.660/0.644/0.645(챔피언 0.647/0.641/0.643 대비 근소 우위, 과적합 없음). 아티팩트 `models/artifacts/challenger_model.joblib`+`challenger_manifest.json`+`challenger_shap_background.parquet` 저장 완료

## Dev Notes

### 이 스토리의 성격
- Story 1.5(챔피언)의 다음 단계, 1.4(WOE/변수선정)를 champion과 공유하되 **변수는 원값(raw)으로 사용**한다는 점이 champion과의 핵심 차이. `scorecard/challenger.py`는 현재 4줄 스텁(CAP-5 헤더만).
- 입력 계약: 1.4 `select_variables`가 반환한 최종 변수 리스트(실데이터 기준 7개: `fico_range_low, annual_inc, dti, home_ownership, revol_util, inq_last_6mths, purpose`) + 1.2/1.3이 만든 train/valid의 **raw(원값)** 데이터프레임(`bad_flag` 포함, WOE 미적용). 1.4의 WOE 변환·binners는 챌린저에 불필요 — import하지 않는다.
- 스코프 경계: **평가(3면 AUC/KS/PR-AUC 비교, 등급화, PSI)는 Story 1.7**. 이 스토리는 챌린저 학습 + calibration + 아티팩트 저장까지.

### 실증 확인 완료 (스토리 착수 전 검증)
- `lightgbm==4.6.0`, `optuna==4.9.0` (`.venv` 설치 버전).
- LightGBM의 sklearn API(`LGBMClassifier`)가 **nullable Float64/Int64와 pandas `category` dtype을 변환 없이 직접 fit**함(합성 데이터로 검증: 결측 포함 Float64, uncapped Int64 카운트, category dtype 컬럼 혼합 입력에서 fit 성공).
- 동일 `random_state`로 2회 fit한 모델의 `predict_proba` 출력이 **완전히 동일**(NFR1 재현성 확인).
- Optuna `TPESampler(seed=...)`로 생성한 두 study가 동일 seed에서 **완전히 동일한 best_value**를 산출(재현성 확인).
- 결론: 1.4/1.1에서 반복됐던 "nullable dtype 어댑터 필요" 우려는 이 스토리에서는 **불필요**로 기각됨 — 곧바로 원값 DataFrame을 LightGBM에 넘기면 된다.

### 원변수 선택 시 주의 (1.3 산출물과의 정합)
- 1.4가 선정한 변수 중 `inq_last_6mths`는 **1.3에서 캡핑 제외**된 컬럼(zero-inflated count, `CAPPING_EXCLUDED_COLUMNS`)이므로 원값 그대로(캡 미적용) 사용해야 한다 — 별도 처리 불필요, 그냥 원본 컬럼을 쓰면 됨.
- `revol_util`은 1.3에서 `"45.3%"` 문자열을 `coerce_percent_columns`로 **미리 변환해야** 사용 가능(1.3 리포트 스니펫과 동일 절차). 이 스토리의 실행 스니펫에도 그 단계를 포함할 것.
- `fico_range_low`, `annual_inc`, `dti`, `revol_util`은 1.3에서 캡핑된(`CAPPABLE_NUMERIC_COLUMNS`) 값을 그대로 사용.

### 아키텍처 가드레일
- **AD-1**: manifest 공통키 + 챌린저 전용키(`calibration_method`, `shap_background_sample_ref`) 필수. `shap_background_sample_ref`는 반드시 **파일로 저장된 고정 표본**을 가리켜야 하며, 2.2가 매 요청마다 SHAP 배경표본을 재계산하지 않도록 하는 것이 목적 — 이 스토리에서 실제로 파일을 만들어 저장해야 함(문자열만 채워넣고 파일을 안 만들면 AD-1 정신 위반).
- **AD-4 대비**: 서빙(2.3)이 재학습하지 않으므로, 챌린저 아티팩트 번들에는 예측에 필요한 모든 것(model + calibrator)이 들어있어야 함 — 1.5 코드리뷰에서 확립된 "번들에 서빙 필요 요소 전부 포함" 원칙을 그대로 적용.
- **모듈 위치**: `scorecard/challenger.py` = CAP-5.
- **NFR1(재현성)**: LightGBM `random_state` + Optuna sampler seed 전부 `scorecard.config.RANDOM_SEED` 사용. SHAP 배경표본 추출도 같은 시드로 결정론적 샘플링(`df.sample(n, random_state=seed)`).
- **NFR6(ASCII)**.

### 스코프 가드 (하지 말 것)
- 3면(train/valid/OOT) AUC·KS·PR-AUC 비교, 등급 매핑, PSI, scored validation frame 생성 → Story 1.7 (OOT는 이 스토리에서 건드리지 않는다 — 1.5도 "sanity" 목적의 informal 확인만 했을 뿐 공식 평가는 아니었음, 이 스토리도 동일 원칙 유지)
- WOE 변환 재구현 → 애초에 챌린저는 WOE를 쓰지 않으므로 해당 없음, 1.4 binners를 import하지 않는다
- 실제 SHAP 값 계산(reason code) → Story 2.2. 이 스토리는 "배경표본을 고정해서 저장"까지만, SHAP explainer를 돌려 실제 기여도를 내는 것은 범위 밖

### 이전 스토리 인텔리전스 (1.1~1.5 누적)
- **패턴**: 순수 함수 + pytest + 리포트 문서(재실행 스니펫 포함)가 확립된 프로젝트 컨벤션. 이번에도 `challenger-report-1-6.md`로 계승.
- **1.5 코드리뷰 학습(가장 중요)**: 아티팩트 번들에 서빙이 필요로 하는 모든 fit된 구성요소를 반드시 포함할 것 — 챔피언에서 binners를 빠뜨렸다가 서빙 불가 상태였던 사고가 있었음(커밋 cd174de로 해소). 챌린저는 `{"model", "calibrator"}` 번들 + manifest에 `base_odds` 같은 "당연히 필요한데 깜빡하기 쉬운 상수"가 없는지 재차 점검할 것(이 스토리엔 base_odds 상당의 것이 없어 보이지만, calibration_method·shap_background_sample_ref가 그 역할).
- **실데이터 이제 존재**: 1.1의 `data/lc_accepted_2012_2015_36m.parquet`(589,635행)이 1.5 스토리 진행 중 사용자가 직접 다운로드해 **이제 이 dev 환경에 실제로 있다**(1.1~1.5 문서에 반복된 "실데이터 없음" 문구는 이 스토리부터 더 이상 사실이 아님). 1.2~1.5 실측 결과(1.5 리포트에 기록됨): train 143,892행(bad 12.70%)/valid 162,570행(13.73%)/oot 283,026행(14.89%); 1.4 최종 선정 변수 7개(fico_range_low, annual_inc, dti, home_ownership, revol_util, inq_last_6mths, purpose); 챔피언 sanity AUC train/valid/oot = 0.647/0.641/0.643. 이 스토리는 합성 데이터 pytest에 더해 **실데이터로도 최소 1회 실행**해 결과를 리포트에 남길 것(Task 6).
- **버전 확인 완료**: lightgbm 4.6.0, optuna 4.9.0 — 둘 다 nullable/category dtype 직접 수용, 재현성 확인(위 "실증 확인" 참고).

### Project Structure Notes
- 신규 파일: `scorecard/challenger.py`(스텁 → 구현), `tests/test_challenger.py`(NEW), `docs/implementation-artifacts/challenger-report-1-6.md`(NEW).
- SHAP 배경표본 파일은 `models/artifacts/`(gitignore 대상) 하위에 저장 — 1.5의 `champion_model.joblib`/`champion_manifest.json`과 같은 디렉토리.

### References
- [Source: docs/planning-artifacts/epics.md#Story-1.6] — AC 원문
- [Source: ARCHITECTURE-SPINE.md#AD-1] — manifest.json 스키마(챌린저 전용키: calibration_method, shap_background_sample_ref)
- [Source: ARCHITECTURE-SPINE.md#AD-4] — 서빙 재학습 금지, 아티팩트 완결성 요구
- [Source: scorecard/sample_design.py, scorecard/preprocessing.py] — 1.2/1.3 산출 데이터 계약(라벨·분할·캡핑·퍼센트파싱)
- [Source: scorecard/binning.py] — 1.4 `select_variables`가 반환한 최종 변수 리스트(원값으로 재사용, WOE 자체는 미사용)
- [Source: docs/implementation-artifacts/champion-scorecard-report-1-5.md] — 실데이터 파이프라인 실행 결과(변수셋·분할 통계), 1.5 코드리뷰가 확립한 "아티팩트 번들 완결성" 원칙
- [Source: docs/implementation-artifacts/1-5-champion-logistic-scorecard.md] — 이전 스토리 Dev Notes/Completion Notes 전체(위 "이전 스토리 인텔리전스" 절에 핵심만 발췌)

## Dev Agent Record

### Agent Model Used

claude-fable-5 (bmad-dev-story)

### Debug Log References

- 착수 전 LightGBM 4.6.0 + Optuna 4.9.0 스파이크: nullable Float64/Int64·category dtype 직접 fit 성공, 동일 seed 재현성(모델·Optuna 둘 다) 확인 — 어댑터 불요로 확정
- `pytest -q` → 65 passed (기존 55 + 신규 10), 재작성 없이 첫 실행에 전부 통과
- 실데이터 실행: `tune_challenger` 20 trials 27초(실 train 143,892행), Brier 0.11491→0.11480, sanity AUC train/valid/oot=0.660/0.644/0.645

### Completion Notes List

- **N_TRIALS=20 결정**: SPEC/epics 미명시, 스토리 오너 결정. 실데이터 기준 27초로 dev 반복에 부담 없음 확인 후 확정.
- **원변수 vs WOE**: 챌린저는 1.4의 WOE/binners를 전혀 import하지 않음 — 1.4가 선정한 변수 리스트(이름)만 재사용하고 값은 1.3 산출 raw(캡핑·퍼센트파싱 적용) 그대로 사용. LightGBM이 nullable/category dtype을 직접 처리해 결측 방치 원칙(FR2)도 자연히 지켜짐(별도 처리 불필요).
- **calibration 방법론 한계 인지**: isotonic calibration을 fit한 것과 같은 valid split에서 개선을 평가해 다소 in-sample 성격(리포트에 명시). 완전히 독립적인 3-way(fit/calibrate/evaluate) 분리는 이 프로젝트의 OOT를 1.7 평가 전용으로 남겨두는 설계와 맞지 않아 범위 밖으로 유지.
- **1.5 패턴 재사용**: 아티팩트 번들에 서빙 필요 요소(model+calibrator) 전부 포함 — 1.5 코드리뷰에서 확립된 원칙을 처음부터 적용해 동일 사고 재발 방지.
- **SHAP 배경표본**: 2.2가 나중에 쓸 고정 표본을 이 스토리에서 실제로 저장(파일 존재 확인 가능) — manifest 참조 문자열만 채우고 파일을 안 만드는 실수 방지.

### File List

- `scorecard/challenger.py` (MODIFIED — 스텁 → 구현: tune_challenger, fit_calibrator, calibrated_predict_proba, brier_scores, calibration_curve_data, save_shap_background_sample, save_challenger_artifact)
- `tests/test_challenger.py` (NEW — 10 tests)
- `docs/implementation-artifacts/challenger-report-1-6.md` (NEW)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 상태 전이)

## Change Log

- 2026-07-14: Story 1.6 구현 완료 — Optuna 튜닝 LightGBM(원변수, WOE 미사용) + isotonic calibration + SHAP 배경표본 고정 + 아티팩트/manifest 저장. pytest 65 passed. 실데이터로 전체 파이프라인 실행: Brier 개선 확인(0.11491→0.11480), sanity AUC 챔피언 대비 근소 우위(0.660/0.644/0.645 vs 0.647/0.641/0.643). Status → review.
