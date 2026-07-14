---
baseline_commit: c1ed76a
---

# Story 1.7a: 3면 평가와 등급 매핑 (FR6, FR7)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

<!-- Split from epics.md Story 1.7 per the readiness report (2026-07-13): "1-7
LARGE story - split into 1-7a (evaluation+grading) / 1-7b (PSI+frame+manifest)
if dev context runs short." This is 1-7a. 1-7b covers PSI, the scored
validation frame (AD-3), and finalizing both manifests with grade_thresholds. -->

## Story

As a 모형 개발자,
I want 챔피언·챌린저를 train/valid/OOT 3면에서 AUC·KS·PR-AUC로 비교하고 1~10등급으로 매핑하고,
so that "검증 완료된 신용평가모형"을 성능표와 함께 시연할 수 있다.

## Acceptance Criteria

**Given** 1.5(챔피언)·1.6(챌린저)의 두 아티팩트
**When** `scorecard/evaluation.py`·`scorecard/grading.py`로 평가·등급화하면
1. train/valid/OOT 3면 AUC·KS·PR-AUC 비교표가 산출된다 (FR6 — **OOT 챔피언 KS≥0.25·챌린저 AUC≥0.70이 통과 목표, 미달 시 원인 분석 문서가 대체 산출물**, 미달=스토리 실패 아님)
2. 1~10등급 매핑과 등급별 부도율 완전 단조 검증이 완료된다 (FR7)
3. `grade_thresholds`가 산출된다(이 스토리는 계산까지만 — **manifest에 실제로 써넣는 것은 1.7b 소관**, AD-1 최종 확정은 1.7b)

> 성공기준 계량화(스토리 오너 보강): 위 3개 AC + `pytest -q` 초록. 등급 매핑은 최종 등급 수가 10개에 못 미치더라도(단조성 확보를 위한 병합 결과) 실패가 아니다 — **완전 단조성이 등급 수보다 우선**(FR7 문구 그대로).

## Tasks / Subtasks

- [x] Task 1: 평가 지표 함수 (AC: 1)
  - [x] `compute_metrics(y_true, p_bad)` — AUC/PR-AUC(sklearn) + KS(`scipy.stats.ks_2samp`, **착수 전 손계산 대비 실증 확인** — 신용평가 KS 정의와 소수점 9자리까지 일치)
  - [x] `champion_p_bad`/`challenger_p_bad` — 1.5/1.6 번들 계약대로 WOE변환+predict_proba / calibrated_predict_proba
  - [x] `evaluation_table(splits, champion_bundle, champion_vars, challenger_bundle, challenger_vars)` — model×split 6행, P(bad) 확률 기준
  - [x] OOT pass/fail 플래그(`oot_target_met`) — non-OOT 행은 `None`, 미달이어도 예외 없이 `False`
- [x] Task 2: 등급 매핑 (AC: 2, 3)
  - [x] `fit_grade_thresholds(train_scores, n_grades=10)` — train 등빈도 분위수 경계(오름차순). **`train_bad_flag` 파라미터는 불필요해 시그니처에서 제외**(순수 점수 분위수 계산에만 라벨이 안 쓰임 — 실제 사용은 `enforce_monotonic_grades`에서). 등급 1=최고점수 관례는 API_SPEC.md 예시 확인
  - [x] `assign_grade(scores, edges)` — 범위 밖 점수도 안전 처리(open-ended 외곽 경계)
  - [x] `enforce_monotonic_grades(train_scores, train_bad_flag, n_grades=10)` — 인접 등급 반복 병합, 실증: 깨끗한 신호는 10등급 유지, 순수 노이즈는 1등급까지 병합(알고리즘 정상 종료 확인)
  - [x] `validate_monotonic(table)` — boolean 반환
  - [x] manifest 기록은 1.7b 소관으로 범위 밖 유지(코드에서 건드리지 않음)
- [x] Task 3: 평가·등급화 리포트 (AC: 1, 2)
  - [x] `docs/implementation-artifacts/evaluation-grading-report-1-7a.md` — 3면 비교표(실측), OOT 목표 미달 원인분석(7변수 한계·grade/int_rate 배제 트레이드오프), 등급표(실측, 10등급 자연 단조), 챔피언/챌린저 등급체계 분리 이슈를 1.7b 오픈퀘스천으로 기록, 재실행 스니펫
- [x] Task 4: pytest 및 회귀 (AC: 전체)
  - [x] `tests/test_evaluation.py` — 5개 테스트(KS 손계산 일치, 지표 범위, 완전분리 케이스, 번들 계약 monkeypatch로 table 구조·6행·플래그 None/bool 분리, 임계값 정확성)
  - [x] `tests/test_grading.py` — 8개 테스트(경계 오름차순, 최고/최저 점수 등급, 범위밖 점수, 클린신호 10등급 유지, 노이즈 병합, 단조성 실질 확인, validate_monotonic 위반 탐지)
  - [x] `pytest -q` → **80 passed** (기존 67 + 신규 13)
  - [x] **실데이터 실행 완료**: 3면 평가표 실측(OOT 챔피언 KS=0.2054<0.25 미달, 챌린저 AUC=0.6452<0.70 미달 — 원인분석 리포트에 기록), 등급표 실측(10등급 자연 단조, 부도율 4.07%→23.57%)

## Dev Notes

### 이 스토리의 성격 — 1.7 분할
- 원래 epics.md의 Story 1.7(FR6+FR7+FR8+scored validation frame+manifest 확정)은 준비도 점검 리포트(2026-07-13)가 "사이즈 큼 → dev시 1.7a/1.7b 분할 옵션"으로 미리 승인해둔 항목이다. 이 스토리(1.7a)는 **FR6(3면 평가)+FR7(등급화)까지만**. PSI(FR8), scored validation frame(AD-3) 생성, 두 manifest에 `grade_thresholds` 써넣기(AD-1 완결)는 **1.7b**로 넘어간다.
- `scorecard/evaluation.py`(CAP-6,8 — 이 스토리는 CAP-6만), `scorecard/grading.py`(CAP-7) 둘 다 현재 4줄 스텁.

### 아티팩트 로드 계약 (1.5/1.6 코드리뷰로 확정된 포맷)
- 챔피언: `joblib.load("models/artifacts/champion_model.joblib")` → `{"model": LogisticRegression, "binners": {var: OptimalBinning}}`. 점수 산출은 `scorecard.binning.transform_woe(df, bundle["binners"])` → `bundle["model"].predict_proba(...)`. **원시 df를 바로 모델에 넣으면 안 됨** — WOE 변환이 선행돼야 함(1.5 코드리뷰가 이걸 위해 binners를 번들에 넣었음).
- 챌린저: `joblib.load("models/artifacts/challenger_model.joblib")` → `{"model": LGBMClassifier, "calibrator": IsotonicRegression|LogisticRegression}`. 점수 산출은 `scorecard.challenger.calibrated_predict_proba(bundle["model"], bundle["calibrator"], df, variables)` — **원값 그대로**(WOE 불필요).
- `variables`(feature_order)는 각 manifest.json의 `feature_order` 키에서 읽을 것 — 하드코딩하지 말 것(1.5/1.6 다시 실행 시 선정 변수가 바뀔 수 있음).

### KS 계산 방식 (실증 검증 없이 채택 — dev 시 pytest로 확인 필수)
`scipy.stats.ks_2samp(p_bad[y==1], p_bad[y==0]).statistic`이 신용평가 업계의 KS 정의(누적 부도율-정상율 분포의 최대 이격)와 동일한지 **dev 착수 시 소규모 합성 데이터로 직접 검증할 것**(이 스토리 작성 시점엔 미검증 — 이전 스토리들의 "착수 전 실증 확인" 관행을 이어갈 것). 다른 라이브러리(`optbinning`이 이미 내부적으로 KS를 계산해 `binning_table`에 노출할 수도 있음 — 있다면 직접 구현 대신 그걸 재사용하는 것도 고려 가능, 단 AD-2 위반(비닝 로직 재사용은 허용, WOE 변환 자체를 새로 만드는 게 아니므로 무방) 아님을 확인).

### 등급화 알고리즘 (Task 2) — 설계 노트
- **등급 1 = 최고 점수(가장 안전)** 관례는 `API_SPEC.md`의 `/v1/grades` 응답 예시(`grade:1, score_min:720`)와 일치시킬 것 — 이 프로젝트의 유일한 등급 방향 근거 문서.
- 등빈도(equal-frequency) 분위수로 초기 10등급을 만들되, 표본이 143,892건(train)이라도 실제 부도율이 낮은 좋은 신용 구간에서 등급 간 부도율 차이가 미세해 비단조가 나올 가능성이 있음 — `enforce_monotonic_grades`의 인접 병합 로직이 실제로 필요할 가능성이 높다(챔피언 sanity AUC가 0.647로 완벽과 거리가 있어 등급 경계 근처에서 순서 역전 여지 있음).
- 병합 결과 최종 등급 수가 10보다 작아도 **정상**(AC 성공기준 명시) — 무리하게 10개를 유지하려 하지 말 것.

### 아키텍처 가드레일
- **AD-3 대비**: 이 스토리는 아직 scored validation frame을 만들지 않는다(1.7b 소관) — 하지만 1.7b가 쓸 컬럼 스키마(`applicant_id, vintage, model_type, score, pd, grade, bad_flag, int_rate, recoveries, total_pymnt`)를 염두에 두고 `evaluation_table`/`grading` 함수의 출력이 그 스키마로 조립 가능한 형태(점수·PD·등급이 분리된 배열/Series)를 유지할 것.
- **AD-1 대비**: `grade_thresholds`는 이 스토리가 값을 계산하지만 manifest에 쓰지 않는다 — 1.7b가 두 모델 모두에 동일 `grade_thresholds`(등급 경계는 모델 공용이 아니라 **모델별로 다를 수 있음** — 챔피언 점수와 챌린저 확률은 스케일이 다르므로 별도 등급 체계가 필요할 수 있음, 이 스토리에서 확인·문서화할 것).
- **모듈 위치**: `scorecard/evaluation.py` = CAP-6(이 스토리)+CAP-8(1.7b), `scorecard/grading.py` = CAP-7.
- NFR1(재현성): 등빈도 분위수·병합 알고리즘 전부 결정론적, 랜덤성 없음.

### 스코프 가드 (하지 말 것)
- PSI 계산 → 1.7b
- scored validation frame parquet 생성 → 1.7b
- manifest.json에 grade_thresholds 기록 → 1.7b
- 에픽 DoD(옵시디언 미러 등) → 1.7b가 Epic 1 마지막 스토리이므로 거기서 처리

### 이전 스토리 인텔리전스 (1.1~1.6 누적)
- **아티팩트 로드 계약**: 위 "아티팩트 로드 계약" 절 참고 — 1.5/1.6 코드리뷰로 확정된 번들 포맷을 반드시 지킬 것(바로 `joblib.load(path)`가 모델이라고 가정하면 즉시 깨짐).
- **패턴**: 순수 함수 + pytest + 리포트 문서 + 실데이터 검증(이제 항상 가능) 확립.
- **1.6 코드리뷰 학습**: "곡선/분포 비교" 류 함수를 만들 때 두 그룹을 독립적으로 비닝/분위수화한 뒤 위치기준으로 합치면 안 됨(calibration_curve_data 버그) — 등급별 비교표를 만들 때도 동일 원칙: 등급 경계는 반드시 **하나의 기준(train 분위수)**으로 고정하고 train/valid/OOT 전부 그 경계로 배정할 것(각 split마다 별도로 분위수를 새로 매기면 등급의 의미가 split마다 달라짐 — 이는 이번 스토리에서 처음부터 피해야 할 함정).
- **실데이터 존재**: 1.5/1.6 아티팩트가 `models/artifacts/`에 이미 저장돼 있음(champion_model.joblib, challenger_model.joblib+manifest들). 이 스토리는 그것들을 로드해서 바로 평가할 수 있다.

### Project Structure Notes
- 신규 파일: `scorecard/evaluation.py`(스텁 → 구현), `scorecard/grading.py`(스텁 → 구현), `tests/test_evaluation.py`(NEW), `tests/test_grading.py`(NEW), `docs/implementation-artifacts/evaluation-grading-report-1-7a.md`(NEW).

### References
- [Source: docs/planning-artifacts/epics.md#Story-1.7] — AC 원문(FR6+FR7+FR8 통합, 이 스토리는 FR6+FR7만)
- [Source: docs/planning-artifacts/sprint-status.yaml 상단 주석] — 1-7 분할 사전 승인 근거
- [Source: API_SPEC.md#3-GET-v1-grades] — 등급 방향 관례(등급 1=최고점수) 유일한 근거 문서
- [Source: scorecard/champion.py, scorecard/challenger.py] — 아티팩트 번들 포맷(1.5/1.6 코드리뷰 확정)
- [Source: docs/implementation-artifacts/1-6-challenger-lightgbm-calibration.md] — 이전 스토리 Dev Notes/Completion Notes(위 "이전 스토리 인텔리전스"에 핵심만 발췌), calibration_curve_data 버그의 일반화 교훈

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (bmad-dev-story)

### Debug Log References

- 착수 전 KS 검증: `scipy.stats.ks_2samp`과 수동 누적분포 최대이격 계산이 소수점 9자리까지 일치 확인
- 등급 알고리즘 실증(구현 직후): 깨끗한 신호(로지스틱 형태 부도확률) → 10등급 자연 단조, 순수 노이즈(300건) → 1등급까지 반복 병합되며 정상 종료
- `pytest -q` → 80 passed (기존 67 + 신규 13), 재작성 없이 첫 실행에 전부 통과
- 실데이터 실행: 3면 평가표(OOT 목표 둘 다 미달, 원인분석 리포트 기재), 등급표(10등급 자연 유지, 병합 불필요)

### Completion Notes List

- **아티팩트 로드 계약 준수**: 챔피언은 `transform_woe`로 WOE 변환 후 `predict_proba`, 챌린저는 원값 그대로 `calibrated_predict_proba` — 1.5/1.6 코드리뷰가 확정한 번들 포맷(`{"model","binners"}` / `{"model","calibrator"}`)을 그대로 재사용, 새 로직 없음.
- **OOT 목표 미달, 실패 아님**: FR6 성공기준대로 원인분석을 리포트에 서술(7개 변수 한계, grade/int_rate 배제 트레이드오프) — 예외나 assert 실패 없이 `oot_target_met=False`로 조용히 기록.
- **등급 알고리즘 설계**: equal-frequency 초기 분할 + 인접 병합(pool-adjacent-violators 방식)으로 완전 단조 강제. 실데이터는 우연히 병합이 전혀 필요 없었지만(10등급 자연 단조), 노이즈 스트레스 테스트로 병합 로직 자체의 정상 동작(극단적으로 1등급까지 수렴)을 확인.
- **1.7b로 넘긴 오픈퀘스천**: 챔피언(PDO 스케일)과 챌린저(확률 스케일)는 등급 경계가 서로 다를 수밖에 없음 — 챌린저도 별도 등급을 낼지, API/대시보드가 챔피언 등급만 노출할지는 1.7b가 결정. 이 스토리는 챔피언 등급화만 실측.
- **fit_grade_thresholds 시그니처 조정**: 스토리 문서 초안엔 `train_bad_flag` 파라미터가 있었으나 순수 분위수 계산엔 라벨이 필요 없어 제외(라벨은 `enforce_monotonic_grades`에서만 사용) — 스코프·인터페이스 단순화, 기능 손실 없음.

### File List

- `scorecard/evaluation.py` (MODIFIED — 스텁 → 구현: compute_metrics, champion_p_bad, challenger_p_bad, evaluation_table, CHAMPION_OOT_KS_TARGET, CHALLENGER_OOT_AUC_TARGET)
- `scorecard/grading.py` (MODIFIED — 스텁 → 구현: fit_grade_thresholds, assign_grade, enforce_monotonic_grades, validate_monotonic)
- `tests/test_evaluation.py` (NEW — 5 tests)
- `tests/test_grading.py` (NEW — 8 tests)
- `docs/implementation-artifacts/evaluation-grading-report-1-7a.md` (NEW)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 상태 전이, 1-7 분할 반영)

## Senior Developer Review (AI)

- 리뷰 일자: 2026-07-14, 도구: claude /code-review (medium)
- 결과: 1건 발견(PLAUSIBLE) → 영향 낮아 **사용자 결정으로 defer**, 패치 없음
- Findings (1건: PLAUSIBLE):
  - [ ] [Low/correctness, defer] `enforce_monotonic_grades`의 병합 루프가 빈 bin(이산적/중복값 많은 점수 분포) 발생 시 `groupby().to_numpy()`의 위치 기반 배열 변환에서 `bin_idx` 값과 배열 위치가 어긋날 수 있는 취약한 가정에 의존. 실증 재현은 됐으나(인위적 이산 분포), 422건 fuzz 테스트(`assign_grade`로 독립 재검증)에서 실제 잘못된 단조성 판정은 0건 — 매 반복 전체 재계산 + 최종 독립 재검증 구조로 자기교정됨. 실데이터(연속적 PDO 점수)에서는 발생 가능성 낮음. **사용자 판단으로 패치하지 않고 넘어감**(영향 낮음).
- 최종 pytest: 80 passed (변경 없음).

## Change Log

- 2026-07-14: Story 1.7a 구현 완료 — 3면(train/valid/oot) AUC/KS/PR-AUC 평가표(FR6) + 챔피언 등급 매핑·완전단조 강제(FR7). pytest 80 passed. 실데이터 실행: OOT 목표 둘 다 미달(원인분석 기록, 실패 아님), 등급 10개 자연 단조(부도율 4.07%→23.57%). Status → review.
