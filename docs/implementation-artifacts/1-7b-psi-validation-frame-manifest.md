---
baseline_commit: bf80f08
---

# Story 1.7b: PSI, Scored Validation Frame, Manifest 최종화 (FR8, AD-3, AD-1 완결)

Status: review

<!-- Split from epics.md Story 1.7 (see 1-7a-evaluation-grading.md for the
same note). This is 1-7b: FR8(PSI) + AD-3(scored validation frame) +
finalizing both manifests with grade_thresholds + Epic 1 DoD. This is
Epic 1's LAST story. -->

## Story

As a 모형 개발자,
I want train 대비 OOT PSI를 산출하고 scored validation frame을 고정 스키마로 생성하고 두 모델 manifest에 grade_thresholds를 확정하고,
so that "검증 완료된 신용평가모형"의 안정성이 증빙되고 이후 Epic 2의 모든 분석이 소비할 유일한 데이터 소스가 확정된다.

## Acceptance Criteria

**Given** 1.5(챔피언)·1.6(챌린저) 아티팩트 + 1.7a의 평가·등급화 함수
**When** `scorecard/evaluation.py`(PSI 추가)·`scorecard/grading.py`(manifest 최종화)로 처리하면
1. train 대비 OOT 변수·점수 PSI가 산출된다 (FR8 — **점수 PSI < 0.1이 통과 목표**, 미달 시 1.7a와 동일하게 원인분석 문서가 대체 산출물)
2. `grade_thresholds`가 챔피언·챌린저 **양쪽 manifest 모두에** 최종 기록된다 (AD-1 완결)
3. scored validation frame parquet이 AD-3 고정 스키마(`applicant_id, vintage, model_type, score, pd, grade, bad_flag, int_rate, recoveries, total_pymnt`)로 생성된다
4. 에픽 DoD: 성능표 데모 산출물 + git 커밋 + 옵시디언 미러 완료 (Epic 1 마지막 스토리)

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC + `pytest -q` 초록. scored validation frame은 valid+oot 두 split을 합쳐 model_type(champion/challenger) 별로 행이 중복 생성되는 long format이어야 하고, 컬럼 순서·이름이 AD-3과 정확히 일치해야 한다(오탈자·별칭 금지 — ARCHITECTURE-SPINE.md AD-3 원문 그대로).

## Tasks / Subtasks

- [x] Task 1: 챔피언·챌린저 공통 "일반화 점수" 정의 (1.7a 오픈퀘스천 해소 — AC 2, 3의 전제)
  - [x] `generalized_score(p_bad)` 구현 — `logit_bad = ln(p/(1-p))` → `score_formula`, `np.clip(p, eps, 1-eps)`로 극단값 안전 처리
  - [x] 챔피언 `generalized_score` vs `score_formula(decision_function(...))` 일치 확인(max abs diff 5.7e-14)
  - [x] 챌린저도 자체 `grade_thresholds` 확보(Task 2) — 오픈퀘스천 해소
- [x] Task 2: PSI (AC: 1)
  - [x] `population_stability_index(expected, actual, n_buckets=10)` — expected 경계 고정, actual 동일 경계 사용(1.6 교훈 반영)
  - [x] `variable_psi(train_df, oot_df, numeric_columns)` — 변수별 PSI 테이블
  - [x] 챔피언·챌린저 score PSI 산출(**둘 다 목표 <0.1 통과**: 0.0017/0.0013)
  - [x] **실데이터 실행 중 발견한 버그 2건 즉시 수정**: ①낮은 카디널리티/치우친 변수(inq_last_6mths)에서 분위수 비닝이 1개 버킷으로 붕괴 → 고유값≤n_buckets면 정확값 매칭 방식으로 전환 ②**NaN이 np.quantile을 통해 전파돼 결측 있는 변수(revol_util)의 PSI가 조용히 0.0으로 마스킹되던 심각한 버그** → 버킷팅 전 NaN 제거로 수정, 회귀 테스트 2건 추가
- [x] Task 3: Scored Validation Frame (AC: 3 / AD-3)
  - [x] `int_rate` 최초 파싱(`parse_percent` 재사용) — 1.3은 revol_util만 파싱, int_rate는 피처가 아니라 안 건드렸었음
  - [x] `build_scored_frame(...)` — valid+oot만 포함(train 제외), model_type별 long format, AD-3 컬럼 순서 정확히 일치
  - [x] `data/scored_validation_frame.parquet` 저장(gitignore, 실측 891,192행 = (162,570+283,026)×2모델)
- [x] Task 4: Manifest 최종화 (AC: 2 / AD-1)
  - [x] `finalize_manifest(manifest_path, grade_thresholds)` — 기존 manifest 읽어 키 추가/patch, 모델 파일 재덤프 없음
  - [x] 챔피언·챌린저 manifest 양쪽에 각자의 grade_thresholds 실제 반영 확인(AD-1 완결)
- [x] Task 5: 리포트 + 에픽 DoD (AC: 1, 4)
  - [x] `docs/implementation-artifacts/psi-validation-frame-report-1-7b.md` — PSI(변수·점수), scored frame 스키마·행수, manifest 최종 키셋, 실데이터 재실행 스니펫, 버그 수정 기록
  - [x] **에픽 1 DoD**: 1.1~1.7b 성능 요약표 + git 커밋 + **옵시디언 미러**(`12_P1_에픽1_완료_요약.md` — REST API 서버 미실행으로 mcp-obsidian 연결 실패, 파일 직접 작성으로 대체)
- [x] Task 6: pytest 및 회귀 (AC: 전체)
  - [x] `tests/test_evaluation.py`에 추가 — generalized_score 극단값·챔피언 일치, PSI 동일/이동 분포, PSI NaN 마스킹 회귀 2건, variable_psi, build_scored_frame 스키마
  - [x] `tests/test_grading.py`에 추가 — finalize_manifest 키 보존·덮어쓰기
  - [x] `pytest -q` → **92 passed** (기존 80 + 신규 12)
  - [x] **실데이터 실행 완료**: PSI 실측(스코어·변수 전부 <0.1), scored frame 891,192행 생성, 두 manifest grade_thresholds 반영 확인

## Dev Notes

### 이 스토리의 성격 — Epic 1 마지막
- 1.7a(FR6+FR7)의 다음 절반. **`scorecard/evaluation.py`는 1.7a가 이미 채웠음**(CAP-6) — 이 스토리는 같은 파일에 CAP-8(PSI) 함수를 추가한다. `scorecard/grading.py`도 1.7a가 채웠음 — manifest 최종화 함수만 추가.
- 이 스토리가 끝나면 Epic 1 전체가 done — Epic 2(cutoff/swap-set/reason-code/API/대시보드)는 전부 이 스토리가 만드는 **scored validation frame**과 **완결된 manifest**만 소비한다(AD-3, AD-1). 이후 어떤 Epic 2 스토리도 예측을 재계산하지 않는다.

### 1.7a 오픈퀘스천 해소 방식 (Task 1)
1.7a 리포트가 남긴 질문: "챔피언(PDO 스케일)과 챌린저(확률 스케일)의 등급 체계를 어떻게 통일할 것인가?" → 이 스토리의 해법: **`generalized_score(p_bad) = score_formula(logit(p_bad))`를 두 모델 모두에 적용**해 동일 Siddiqi PDO 스케일로 통일한다. 챔피언은 이 값이 1.5의 `decision_function` 기반 점수와 사실상 동일(로짓↔확률 변환의 역함수라 수학적으로 동치, 부동소수점 오차만 존재) — **새 개념이 아니라 챌린저에도 같은 잣대를 적용한 것뿐**. 등급 경계(`grade_thresholds`)는 두 모델 각자의 train 분포로 **개별 fit**(공용 스케일이지만 분포 모양이 다를 수 있어 개별 경계가 더 정확한 단조성을 준다) — manifest에도 각자 기록.

### PSI 버킷팅 — 1.6 교훈 재적용
1.6 코드리뷰에서 "두 분포를 각자 독립적으로 비닝한 뒤 위치기준으로 합치면 서로 다른 확률구간을 비교하게 된다"는 실제 버그가 나왔다(`calibration_curve_data`). PSI는 원래부터 "expected(train) 분위수로 버킷 고정, actual(OOT)도 같은 경계 사용"이 표준 정의이므로 이 함정에 애초에 해당하지 않지만, **구현 시 반드시 `_assign_bin`(grading.py, train 경계 고정)을 그대로 재사용**해 독립 비닝을 하지 않도록 할 것 — 새로 짜다가 실수로 `actual`을 자기 분포로 다시 분위수화하면 1.6과 동일한 버그가 재발한다.

### int_rate 파싱 (놓치기 쉬운 지점)
1.3 스토리는 `revol_util`만 `parse_percent`로 변환했다(`int_rate`는 1.2 누수감사에서 피처 후보에서 배제됐으므로 1.3~1.6 어디서도 안 건드림). 하지만 AD-3 스키마는 `int_rate`를 요구한다(2.4 손익계산이 씀) — **원본 `df["int_rate"]`가 여전히 `"13.5%"` 같은 문자열**이라는 것을 잊지 말 것. `scorecard.preprocessing.parse_percent`를 그대로 재사용(새로 구현 금지).

### 아키텍처 가드레일
- **AD-3 (핵심)**: 컬럼 스키마 고정 — `applicant_id, vintage, model_type, score, pd, grade, bad_flag, int_rate, recoveries, total_pymnt`. 다른 이름(`is_bad` 등) 사용 금지. 어느 캡(2.1/2.4/2.5/3.1)도 이 frame 외의 경로로 예측을 재계산하지 않는다 — 그 원칙의 유일한 데이터 소스를 이 스토리가 만든다.
- **AD-1 완결**: 두 manifest 모두 공통키+모델별 전용키+`grade_thresholds`까지 전부 채워져야 "완결"로 간주.
- **NFR5**: `data/scored_validation_frame.parquet`은 gitignore 대상(이미 `data/`가 .gitignore).
- **NFR1**: PSI·일반화 점수 계산 전부 결정론적.

### 스코프 가드 (하지 말 것)
- Epic 2 소관(cutoff/swap-set/reason-code/API/대시보드) 로직 일체 금지 — 이 스토리는 frame을 만들기만 한다
- train split은 scored frame에 포함하지 않는다(모델이 train으로 학습됐으므로 valid/oot만 검증용 — "scored **validation**/OOT" 명칭이 이를 시사)

### 이전 스토리 인텔리전스 (1.1~1.7a 누적)
- **아티팩트 로드 계약**: 1.7a와 동일 — `joblib.load` 후 `{"model","binners"}`/`{"model","calibrator"}` 번들, `feature_order`는 각 manifest에서 읽음.
- **1.7a 산출물 재사용**: `scorecard.evaluation.champion_p_bad`/`challenger_p_bad`(P(bad) 산출), `scorecard.grading.fit_grade_thresholds`/`assign_grade`/`enforce_monotonic_grades`/`_assign_bin`(등급·PSI 버킷팅 공용) — 전부 그대로 import해서 쓸 것, 재구현 금지.
- **1.6 교훈**: 두 분포 독립 비닝 후 위치 병합 금지(PSI 절 참고).
- **실데이터**: 1.5/1.6 아티팩트, 1.7a 평가 결과 전부 실측 완료 — 이 스토리도 동일하게 실행.

### Project Structure Notes
- 신규 파일: `docs/implementation-artifacts/psi-validation-frame-report-1-7b.md`(NEW). `scorecard/evaluation.py`·`scorecard/grading.py`는 MODIFIED(1.7a가 만든 파일에 함수 추가).
- `data/scored_validation_frame.parquet`은 gitignore.

### References
- [Source: docs/planning-artifacts/epics.md#Story-1.7] — AC 원문(FR8, AD-3, 에픽 DoD)
- [Source: ARCHITECTURE-SPINE.md#AD-3] — scored validation frame 고정 스키마 원문
- [Source: ARCHITECTURE-SPINE.md#AD-1] — manifest 완결 요구사항
- [Source: scorecard/evaluation.py, scorecard/grading.py] — 1.7a가 만든 재사용 대상 함수
- [Source: scorecard/preprocessing.py] — `parse_percent`(int_rate 파싱용, 재사용)
- [Source: docs/implementation-artifacts/evaluation-grading-report-1-7a.md] — 1.7a 오픈퀘스천(챔피언/챌린저 등급 체계 분리 이슈) — 이 스토리가 해소

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (bmad-dev-story)

### Debug Log References

- `pytest -q` → 92 passed (기존 80 + 신규 12), 첫 실행에 전부 통과
- 실데이터 1차 실행에서 `variable_psi`가 `inq_last_6mths`(치우친 카운트)에서 `ValueError: insufficient variation` 발생 → 정확값 매칭 폴백으로 수정, 재실행 성공
- 실데이터 2차 실행에서 `revol_util`(결측 존재) PSI가 `0.000000`으로 의심스럽게 정확히 나옴 → 디버깅 결과 `np.quantile`의 NaN 전파로 버킷 fit이 모든 시도에서 실패해 "변동 없음" 폴백으로 조용히 빠진 것 확인 → NaN 제거 후 버킷팅으로 수정, 재실행 시 0.0592로 정상 산출
- 챔피언 `generalized_score` vs `decision_function` 기반 점수: max abs diff 5.7e-14(부동소수점 오차 수준, 동치 확인)

### Completion Notes List

- **1.7a 오픈퀘스천 해소**: 챔피언·챌린저 모두 `generalized_score`(동일 Siddiqi 스케일)로 통일, 각자 독립적으로 `grade_thresholds` fit — 두 manifest 모두 완결.
- **실데이터 실행이 실제 버그 2건을 잡아냄**(합성 데이터 테스트만으론 안 드러났을 사례): 저카디널리티 변수의 분위수 붕괴, 그리고 더 심각하게는 **NaN이 PSI를 조용히 0으로 마스킹**하는 문제 — 결측이 있는 모든 변수에서 "안정적"이라는 거짓 결론을 낼 뻔했음. 둘 다 즉시 수정 및 회귀 테스트 추가.
- **PSI 버킷팅 설계**: 1.6의 "두 분포 독립 비닝 후 위치기준 병합" 교훈을 처음부터 반영 — expected(train) 경계 고정, actual은 그 경계 재사용. 저카디널리티는 정확값 매칭으로 대체(표준 이산변수 PSI 관행).
- **manifest 완결**: `finalize_manifest`가 모델 파일을 재덤프하지 않고 JSON만 patch — 1.5/1.6이 이미 검증한 아티팩트 번들과 절대 어긋나지 않음.
- **Epic 1 DoD**: 성능 요약표(리포트)+git 커밋+옵시디언 미러(REST API 미실행으로 파일 직접 작성) 전부 완료. Epic 1 종료.

### File List

- `scorecard/evaluation.py` (MODIFIED — generalized_score, population_stability_index, variable_psi, build_scored_frame, SCORED_FRAME_COLUMNS, PSI_TARGET 추가)
- `scorecard/grading.py` (MODIFIED — finalize_manifest 추가)
- `tests/test_evaluation.py` (MODIFIED — 12 tests 추가)
- `tests/test_grading.py` (MODIFIED — 2 tests 추가)
- `docs/implementation-artifacts/psi-validation-frame-report-1-7b.md` (NEW)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 상태 전이)
- `C:\Users\user\Desktop\ob_storage\신용평가_CRM_사이드프로젝트\12_P1_에픽1_완료_요약.md` (NEW, 프로젝트 외부 — 옵시디언 미러)
- (gitignored, 커밋 대상 아님) `data/scored_validation_frame.parquet`, `models/artifacts/champion_manifest.json`·`challenger_manifest.json`(grade_thresholds 추가 갱신)

## Senior Developer Review (AI)

- 리뷰 일자: 2026-07-14, 도구: claude /code-review (medium)
- 결과: 1건 발견(CONFIRMED, simplification) → 패치 완료. 정확성 버그는 발견되지 않음(실데이터 실행 중 이미 잡은 2건은 구현 단계에서 선반영됨).
- Findings:
  - [x] [Low/simplification] `build_scored_frame`의 챔피언/챌린저 블록이 `model_type`·bundle·variables·grade_edges만 다르고 거의 동일하게 반복 → `_model_rows(df, model_type, p_bad, grade_edges, int_rate)` 내부 헬퍼로 통합, 중복 제거. 향후 AD-3 스키마 변경 시 한쪽만 고치고 다른 쪽을 빠뜨리는 리스크 해소.
- 최종 pytest: 92 passed(회귀 없음).

## Change Log

- 2026-07-14: Story 1.7b 구현 완료 — generalized_score(챔피언·챌린저 통일 스케일), PSI(변수·점수, 저카디널리티+NaN 마스킹 버그 2건 실데이터 실행 중 발견·즉시 수정), scored validation frame(AD-3, 891,192행), manifest 완결(grade_thresholds, AD-1). pytest 92 passed. Epic 1 DoD 완료(성능표+커밋+옵시디언 미러). Status → review.
- 2026-07-14: 코드리뷰 1건 패치(build_scored_frame 챔피언/챌린저 블록 중복 제거, _model_rows 헬퍼 도입). 92 passed.
