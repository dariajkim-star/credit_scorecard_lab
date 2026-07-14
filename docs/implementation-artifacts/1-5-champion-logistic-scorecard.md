---
baseline_commit: 4ed30a0
---

# Story 1.5: 로지스틱 스코어카드 (챔피언)

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 모형 개발자,
I want 선정된 WOE 변수로 PDO=20, Base=600 스코어카드를 구축하고,
so that 설명 가능한 업계 표준 챔피언 모형을 확보한다.

## Acceptance Criteria

**Given** 1.4의 최종 변수셋(`select_variables`가 반환한 선정 변수 + 해당 WOE 변환 DataFrame)
**When** `scorecard/champion.py`로 로지스틱 스코어카드를 학습하면
1. 신청 1건 입력 시 점수가 산출된다 (FR4)
2. 전 변수 계수의 부호가 비즈니스 상식과 일치함을 검증한 표가 산출된다
3. 점수 변환(WOE→선형결합→PDO 스케일링)에 pytest가 있다
4. 챔피언 아티팩트(joblib)와 manifest 필수키(`pdo`, `base_score`, `woe_bin_edges` 포함)가 저장된다 (AD-1)

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC + `pytest -q` 초록. AC2의 "부호 일치"는 **전 계수가 음수**여야 통과(아래 "WOE 부호 관례" 참고 — 양수 계수가 하나라도 있으면 실패로 간주). `joblib.load()`로 아티팩트를 되읽어 `manifest.json`의 필수키가 전부 존재하고, 저장된 로지스틱 모델로 재계산한 점수가 원본과 소수점 이하까지 일치해야 done.

## Tasks / Subtasks

- [x] Task 1: 로지스틱 회귀 학습 (AC: 1, 2)
  - [x] `fit_champion(train_woe_df, y, variables)` 구현 — train WOE로 fit, y 결측 시 ValueError(1.4 `fit_binning` 가드와 동일 패턴)
  - [x] `check_coefficient_signs(model, variables)` 구현 — 계수·부호 테이블, 예외 없이 반환(호출자가 최종 판정)
- [x] Task 2: 점수 변환 — WOE→선형결합→PDO 스케일링 (AC: 1, 3)
  - [x] `PDO=20`, `BASE_SCORE=600`, **`BASE_ODDS=50`(스토리 오너 결정, 근거는 리포트에 기록)**
  - [x] `score_formula(logit_bad, pdo, base_score, base_odds)` — Siddiqi 공식, 스칼라/벡터 모두 지원. `decision_function` 사용(손계산값 일치 확인)
  - [x] `score_applicant(model, woe_row, variables)` — 신청 1건 end-to-end
- [x] Task 3: 아티팩트 저장 (AC: 4 / AD-1)
  - [x] `save_champion_artifact(model, binners, variables, out_dir)` — joblib 모델 + `champion_manifest.json`
  - [x] 공통키(model_type, model_version, trained_at, feature_order) + 챔피언 전용키(pdo, base_score, woe_bin_edges) 전부 포함
  - [x] `grade_thresholds` 의도적 생략(1.7 소관) — manifest·리포트에 근거 기록
  - [x] 출력 디렉토리 자동 생성(`out_dir.mkdir(parents=True, exist_ok=True)`)
- [x] Task 4: 학습 결과 리포트 (AC: 2)
  - [x] `docs/implementation-artifacts/champion-scorecard-report-1-5.md` — BASE_ODDS 근거, 부호 검증표, 점수 산출 예시, 실데이터 재실행 스니펫
- [x] Task 5: pytest 및 회귀 (AC: 3)
  - [x] `tests/test_champion.py` — 11개 테스트(계수 부호, y결측 거부, 부호반전 탐지, score_formula 손계산 일치·단조성·벡터화, score_applicant end-to-end·안전/위험 프로필 비교, 아티팩트 저장→joblib.load 재현 점수 일치, manifest 필수키)
  - [x] `pytest -q` → **55 passed** (기존 44 + 신규 11)
  - [x] **실parquet 재확인**(`test -f` → 없음, 2026-07-14). 합성 데이터로만 검증

## Dev Notes

### 이 스토리의 성격
- Story 1.4(WOE 비닝·변수선정)의 다음 단계. **`scorecard/champion.py`는 현재 4줄 스텁**(CAP-4 헤더만) — 이 스토리가 최초로 채운다.
- 입력 계약: 1.4의 `fit_binning(train_df, y, variables=BINNING_CANDIDATES)` → `transform_woe(train_df, binners)` → `select_variables(woe_df, iv_table(binners))`가 반환하는 `(selected_variables, decisions)`. 이 스토리는 `selected_variables`만 갖고 로지스틱 회귀를 fit한다 — **1.4가 이미 산출한 WOE DataFrame·binners를 그대로 재사용**하고 다시 비닝하지 않는다(AD-2, WOE 재구현 금지 — champion.py는 sklearn LogisticRegression만 새로 학습).
- 스코프 경계: **비닝 자체(1.4)와 등급화·PSI(1.7)는 건드리지 않는다.** 이 스토리는 딱 "선정된 WOE 변수 → 로지스틱 회귀 → 점수 변환 → 아티팩트 저장"까지.

### WOE 부호 관례 (실증 확인 완료 — 이 스토리 착수 전 검증됨)
optbinning의 WOE는 **위험도가 높을수록(event rate=bad rate가 높을수록) WOE가 낮다**(음수까지 감). 합성 데이터로 실증 확인: `dti`(높을수록 위험) 비닝 시 낮은 dti 구간의 WOE=+5.06, 높은 dti 구간의 WOE=−5.73 (`corr(dti, WOE) = −0.947`). 즉 **WOE가 높을수록 안전(good), 낮을수록(음수) 위험(bad)**.

y=`bad_flag`(1=bad)로 로지스틱 회귀를 fit하면, "WOE가 높을수록 안전"이 모형에 올바르게 반영됐다면 **WOE 계수는 반드시 음수**여야 한다(WOE↑ → P(bad)의 logit↓). **AC2의 "부호가 비즈니스 상식과 일치"는 구체적으로 "전 계수가 음수"로 판정한다.** 계수가 양수인 변수가 있다면 부호 반전(비닝·데이터 문제 가능성) — 이 스토리에서 원인 규명까지 할 필요는 없으나(스코프 밖), 검증표에 명확히 드러나야 한다.

### 점수 변환 공식 (Siddiqi 표준 스코어카드 공식)
```
factor = PDO / ln(2)                          # PDO=20 -> factor ≈ 28.85
offset = BASE_SCORE - factor * ln(BASE_ODDS)   # BASE_SCORE=600
log_odds_good = -(intercept + sum(coef_i * woe_i))   # logistic model's raw decision function, negated
score = offset + factor * log_odds_good
```
`LogisticRegression.decision_function(X)`이 `intercept + sum(coef*x)`를 직접 반환한다(sklearn) — `predict_proba`를 거쳐 역산할 필요 없음, `decision_function`을 그대로 쓸 것.

**BASE_ODDS는 스토리 오너가 결정해야 하는 미명시 값**이다(SPEC·epics 어디에도 없음) — 업계 관행값 50(호청 시 good:bad=50:1)을 기본값으로 권장하지만, 다른 값을 골라도 무방하다. 어떤 값이든 **문서에 근거를 남길 것**(1.2 train/valid 분할, 1.3 zero-inflated 캡핑 제외와 같은 패턴).

### 아키텍처 가드레일
- **AD-1 (핵심)**: manifest.json 공통키(`model_type`, `model_version`, `trained_at`, `feature_order`) + 챔피언 전용키(`pdo`, `base_score`, `woe_bin_edges`) 전부 필수. `feature_order`는 이후 API 서빙(2.3)이 입력 순서를 맞추는 유일한 근거가 되므로 **`transform_woe` 출력 컬럼 순서와 반드시 동일하게 저장**할 것.
- **AD-2**: WOE 변환은 1.4의 `scorecard.binning.transform_woe`를 그대로 import해서 쓴다 — champion.py 안에 WOE 계산을 재구현하지 않는다. 이 스토리가 새로 만드는 것은 로지스틱 회귀 fit과 점수 변환 함수뿐.
- **모듈 위치**: `scorecard/champion.py` = CAP-4 (ARCHITECTURE-SPINE.md Capability→Architecture Map).
- **NFR1(재현성)**: `LogisticRegression`은 기본 solver가 결정론적(정규화 없는 기본 설정이면 lbfgs로 수렴 오차 미미) — 정규화(C 파라미터) 등 하이퍼파라미터를 쓸 경우 고정값으로 문서화. `random_state` 불필요(로지스틱 회귀 자체엔 랜덤성 거의 없음, solver에 따라 다를 수 있어 명시적으로 고정 권장).
- **NFR6(ASCII)**.

### 스코프 가드 (하지 말 것)
- WOE 비닝 재구현 → 절대 금지(AD-2), 1.4의 `transform_woe`만 사용
- 등급 매핑(1~10등급), 단조성 검증, PSI → Story 1.7
- LightGBM/챌린저 → Story 1.6
- `grade_thresholds`를 이 스토리에서 임의로 계산해 manifest에 채우지 말 것 — 1.7 산출물이며 아직 없음(위 Task 3 참고)

### 이전 스토리 인텔리전스 (1.1~1.4 누적)
- **패턴**: 순수 함수 + 합성 데이터 pytest + 실데이터 부재 시 재실행 스니펫 문서화(1.1~1.4 리포트 전부 동일 패턴, 이번에도 `champion-scorecard-report-1-5.md`로 계승). nullable dtype 주의(Int64/Float64) — 다만 sklearn `LogisticRegression.fit`은 nullable dtype을 못 받을 수 있으니 **WOE DataFrame을 `.astype(float)`로 변환해서 sklearn에 넘길 것**(1.4의 `transform_woe` 출력이 이미 일반 float일 가능성이 높지만, 넘기기 전 dtype을 확인하고 필요시 명시적으로 변환 — 1.4 코드리뷰에서 이런 종류의 dtype 가정 문제가 반복적으로 나왔음).
- **1.4 코드리뷰 학습**: 상관행렬 등 NaN이 조용히 검증을 무력화하는 패턴이 실제로 발견됐다(post-selection assertion이 skipna로 NaN 무시) — 이 스토리의 "전 계수 음수" 검증도 NaN 계수가 있을 때 `all(coef < 0)` 류의 비교가 NaN을 조용히 통과시키지 않는지 확인할 것(NaN과의 비교는 항상 False이므로 `all()`은 오히려 안전하게 실패로 처리되지만, `any(coef > 0)`처럼 실패 조건을 직접 검사하는 게 더 명확).
- **드리프트 가드 패턴**: 1.3(`_assert_matches_feature_candidates`)·1.4(`BINNING_CANDIDATES` 테스트)가 상수 집합의 일치를 로드 시점/테스트에서 강제하는 패턴을 확립했다 — 이 스토리는 새 상수 집합을 만들지 않으므로(변수 리스트는 1.4의 `select_variables` 반환값을 그대로 받음) 해당 없음.
- **실parquet 부재 지속**(1.1~1.4 전부): 이번에도 합성 검증 예상.
- **병행 세션 주의**: 이 프로젝트는 여러 모델(fable-5/sonnet-5/opus)이 번갈아 작업 중이었다 — dev 착수 전 `git log --oneline -5`와 `sprint-status.yaml`로 실제 최신 상태를 반드시 재확인할 것(1-4 진행 중 실제로 병행 세션이 앞서 나가 있던 사례 있음).

### References
- [Source: docs/planning-artifacts/epics.md#Story-1.5] — AC 원문
- [Source: ARCHITECTURE-SPINE.md#AD-1] — manifest.json 스키마(공통키+챔피언 전용키)
- [Source: ARCHITECTURE-SPINE.md#AD-2] — WOE 변환 단일 소스(binning.py)
- [Source: scorecard/binning.py] — `transform_woe`, `select_variables`, `bin_edges`, WOE 부호 관례(이 스토리 착수 전 실증 확인)
- [Source: docs/implementation-artifacts/1-4-woe-binning-variable-selection.md] — 이전 스토리 Dev Notes/Completion Notes 전체(위 "이전 스토리 인텔리전스" 절에 핵심만 발췌)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (bmad-dev-story)

### Debug Log References

- 착수 전 `transform_woe` 출력 dtype 확인(합성 데이터): 이미 plain `float64` — sklearn에 넘길 때 nullable dtype 어댑터 불필요(Dev Notes가 우려했던 지점, 실증으로 기각)
- optbinning WOE 부호 관례를 1.4 Dev Notes의 실증 결과(dti corr=-0.947)를 그대로 재사용해 "전 계수 음수" 기대를 코드/테스트에 반영
- `pytest -q` → 55 passed (기존 44 + 신규 11), 재작성 없이 첫 실행에 전부 통과
- 실parquet 재확인: 없음(1.1~1.5 연속)

### Completion Notes List

- **BASE_ODDS=50 결정**: SPEC/epics 어디에도 명시 없어 스토리 오너 결정. 업계 관행값(Siddiqi 문헌 기준) 채택, 근거는 `champion-scorecard-report-1-5.md`에 기록 — 실제 포트폴리오 good:bad 배당률이 확보되면 이 상수만 교체하면 되도록 공식과 상수를 분리 설계.
- **WOE 부호 검증**: `check_coefficient_signs`는 예외를 던지지 않고 판정 테이블만 반환(합성 데이터에선 실제 반전이 나올 수 있어 함수 레벨에서 강제하면 유연성 상실) — 최종 판정은 리포트/호출자 몫. 정상 신호를 가진 합성 데이터에서는 전 계수 음수 확인.
- **grade_thresholds 생략**: AD-1 공통키지만 CAP-7(1.7)이 아직 없음 — manifest에 넣지 않고 리포트에 시퀀싱 근거 기록. 1.7이 같은 manifest.json을 갱신할 것으로 예상.
- **decision_function 사용**: `predict_proba`가 아닌 `decision_function`(raw logit)을 스코어 공식에 직접 연결 — 손계산값과 일치 확인(`test_score_formula_matches_hand_calculation`).
- **1.4 학습 재사용**: WOE 재구현 없이 `scorecard.binning.transform_woe`/`bin_edges`를 그대로 import(AD-2). champion.py가 새로 만든 것은 로지스틱 fit + 점수변환 + 아티팩트 저장뿐.

### File List

- `scorecard/champion.py` (MODIFIED — 스텁 → 구현: PDO/BASE_SCORE/BASE_ODDS, fit_champion, check_coefficient_signs, score_formula, score_applicant, save_champion_artifact)
- `tests/test_champion.py` (NEW — 11 tests)
- `docs/implementation-artifacts/champion-scorecard-report-1-5.md` (NEW)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 상태 전이)

## Change Log

- 2026-07-14: Story 1.5 구현 완료 — 로지스틱 회귀(train WOE) + 계수부호 검증 + Siddiqi PDO 점수변환 + 아티팩트/manifest 저장(grade_thresholds는 1.7 소관으로 의도적 생략). pytest 55 passed(합성 데이터, 실parquet 미존재). Status → review.
