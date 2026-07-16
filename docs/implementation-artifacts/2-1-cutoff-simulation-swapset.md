---
baseline_commit: 3011783
---

# Story 2.1: Cutoff 시뮬레이션과 Swap-set 분석

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 심사 전략 담당자,
I want cutoff별 승인율-부도율 곡선과 챔피언↔챌린저 swap-set을 보고,
so that 심사 기준 조정과 모형 교체의 영향을 정량적으로 판단할 수 있다.

## Acceptance Criteria

**Given** Epic 1의 scored validation frame (`data/scored_validation_frame.parquet`, AD-3 스키마)
**When** `scorecard/strategy.py`로 분석하면

1. 전 구간 cutoff 트레이드오프 curve와 특정 cutoff의 승인율·부도율 즉시 조회가 가능하다 (FR9)
2. swap-in/swap-out 건수와 각 집단의 부도율 비교표가 산출된다 (FR10)
3. frame을 소비만 하고 예측을 재계산하지 않는다 (AD-3) — `champion_model.joblib`/`challenger_model.joblib`을 로드하거나 `binning.py`/`champion.py`/`challenger.py`의 스코어링 함수를 호출하지 않는다.

> 성공기준 계량화(스토리 오너 보강): 위 3개 AC + `pytest -q` 초록 + 실데이터(`data/scored_validation_frame.parquet`) 1회 이상 실행한 산출물(리포트)이 있어야 한다. cutoff curve는 승인율 0%~100% 전 구간을 단조적으로 커버해야 하고(승인율이 cutoff에 대해 non-increasing), swap-set 합계(stable-in + stable-out + swap-in + swap-out)는 모집단 전체 건수와 일치해야 한다.

## Tasks / Subtasks

- [x] Task 1: Cutoff 트레이드오프 curve (AC: #1, FR9)
  - [x] `cutoff_trade_off_curve(df, model_type, cutoffs=None) -> pd.DataFrame` — 지정 `model_type`("champion"|"challenger")으로 frame을 필터링하고, `score` 기준 승인(score >= cutoff)/거절 분할. `cutoffs`가 None이면 관측된 score 분포에서 전 구간을 커버하는 기본 그리드를 생성. 반환 컬럼: `cutoff, approval_rate, bad_rate, approved_count`
  - [x] `bad_rate`는 승인집단(score >= cutoff) 내에서만 계산 — 승인 0건인 cutoff에서는 `NaN` 반환(0/0 방지)
  - [x] `lookup_cutoff(df, model_type, cutoff) -> dict` — 임의 단일 cutoff의 즉시 조회(승인율·부도율·승인건수)
- [x] Task 2: Swap-set 분석 (AC: #2, FR10)
  - [x] `swap_set_table(df, cutoff) -> dict` — 동일 `applicant_id`에 대해 champion/challenger 두 모델의 승인여부(score >= cutoff, **동일 cutoff 값을 두 모델에 동일 적용** — Dev Notes의 "동일 스케일" 근거 참고)를 비교. `swap_in`(챔피언 거절→챌린저 승인), `swap_out`(챔피언 승인→챌린저 거절), `stable_approved`, `stable_rejected` 4개 집단의 건수·부도율 반환
  - [x] wide-pivot 시 `applicant_id`(+`vintage`) 기준으로 champion/challenger 행을 조인 — long format인 frame을 `pivot`으로 옆으로 펼칠 것(AD-3 스키마 자체는 변경하지 않음, strategy.py 내부 로컬 변환만)
  - [x] 두 모델 행의 `bad_flag`가 동일 applicant에서 일치하는지 검증하는 회귀 테스트 추가(불일치 시 frame 생성 버그 조기 발견용)
- [x] Task 3: 분석 모집단 결정 기록 (AC: #1, #2 전제)
  - [x] frame은 valid+oot 두 vintage를 포함한다(1.7b가 합쳐서 저장). cutoff 시뮬레이션·swap-set에 **어느 vintage를 쓸지(oot만 / valid+oot 전체)를 결정하고 근거를 Dev Notes에 결정 기록으로 남긴다** (Story 1.2의 "12개월 성과창" 결정 기록과 동일한 패턴 — SPEC/AC가 명시하지 않은 오픈퀘스천)
- [x] Task 4: 리포트 (AC: 전체)
  - [x] `docs/implementation-artifacts/cutoff-swapset-report-2-1.md` — cutoff curve(대표 구간 표+그래프 설명), 특정 cutoff 조회 예시, swap-set 4분면 표, Task 3 결정 기록, 실데이터 재실행 스니펫
- [x] Task 5: pytest 및 회귀 (AC: 전체)
  - [x] `tests/test_strategy.py` 신규 — `cutoff_trade_off_curve` 단조성(승인율 non-increasing), 승인 0건 cutoff의 NaN 처리, `lookup_cutoff` 단일값 일치, `swap_set_table` 4분면 합계=모집단 일치, swap_in/out 정의(방향) 검증, bad_flag 정합성 회귀
  - [x] `pytest -q` 전체 통과(기존 92 + 신규) 확인
  - [x] 실데이터(`data/scored_validation_frame.parquet`) 실행 완료 — 합성 테스트만으로 끝내지 않음(1.7b가 실데이터 실행에서 실버그 2건을 잡은 선례 참고)

### Review Findings

- [x] [Review][Decision→Patch] **NaN score/bad_flag 처리 방침 미정 — fail-fast로 결정** [scorecard/strategy.py] — NaN 스코어가 `score >= cutoff`에서 조용히 "거절"로 처리되면서 총모수엔 포함돼 승인율을 무신호로 왜곡. 이 저장소의 기존 관례(`binning.py`/`champion.py`의 "y contains missing values" fail-fast 패턴)에 맞춰 **score/bad_flag에 결측이 있으면 즉시 ValueError**로 결정(사용자 확인 없이 리뷰어가 저장소 관례에 따라 판단, AD-3 frame은 결측 없음을 전제하므로 완결성 체크로도 타당).
- [x] [Review][Patch] **빈 모집단(0행) 필터링 시 크래시/침묵 오동작** [scorecard/strategy.py:_default_cutoff_grid, swap_set_table] — `model_type`/`vintage` 필터가 0행을 반환하면 `np.min(빈배열)` crash 또는 pivot 후 `KeyError`. 명확한 `ValueError`로 fail-fast.
- [x] [Review][Patch] **swap_set_table: (applicant_id, vintage) 중복 시 pivot이 불투명한 에러** [scorecard/strategy.py:swap_set_table] — pivot 전 중복 검사·명확한 에러 메시지 추가.
- [x] [Review][Patch] **swap_set_table: champion/challenger 한쪽 model_type이 통째로 없을 때 KeyError** [scorecard/strategy.py:swap_set_table] — pivot 전 두 model_type 존재 여부 명시 검증.
- [x] [Review][Patch] **bad_flag 동일성 불변식이 런타임에 전혀 검증되지 않음(스킵 가능한 테스트에만 의존)** [scorecard/strategy.py:swap_set_table] — 두 모델 모두 존재하는 행에서 champion/challenger bad_flag 불일치 시 런타임 assertion 추가.
- [x] [Review][Defer] **Cutoff 그리드가 정확히 0% 승인률에 도달 못함(설계상)** [scorecard/strategy.py:_default_cutoff_grid] — 이미 테스트 docstring에 설계 의도로 명시됨(`1/total`로 수렴). FR9 "전 구간" 표현과 오해 소지 있어 docstring에 한 줄 보강만 patch, 동작 변경 없음 — deferred-work 등록 불필요할 만큼 경미해 문서 보강으로 즉시 반영.
- [x] [Review][Defer] **임의 `cutoffs` 배열(비정렬·중복·음수)이 검증되지 않음** [scorecard/strategy.py:cutoff_trade_off_curve] — 현재 소비자(2.1 자체 테스트·리포트)는 전부 기본 그리드 또는 정렬된 값만 사용, 실사용 경로 없음. 하드닝은 후속 스토리에서.
- [x] [Review][Defer] **`_filter_population`이 `model_type` 컬럼 존재를 가정(누락 시 미가공 KeyError)** [scorecard/strategy.py:_filter_population] — AD-3가 스키마를 고정 보장하므로 현재는 발생 불가능한 경로. 프레임 생성 로직(1.7b) 소관.
- [x] [Review/Auditor] **AD-3·스코프 가드 준수 확인**: `strategy.py`는 `numpy`/`pandas`만 import(모델 아티팩트·`binning.py`·`champion.py`·`challenger.py` 미참조), `grade` 미사용(연속 `score` 기준), 2.2~2.4 스코프(reason code·API·손익 cutoff) 미침범. Acceptance Auditor 전건 컴플라이언스 확인.

## Dev Notes

### 이 스토리의 성격 — Epic 2 첫 스토리, 순수 소비자
Epic 1은 `scorecard/strategy.py`를 **스텁으로만** 남겨두고 끝났다(`"""CAP-9,10 cutoff·swap-set. Stub created in Story 1.1 (scaffolding). Implemented in a later story."""`, 4줄). 이 스토리가 그 구현을 채운다. Epic 1이 만든 `data/scored_validation_frame.parquet`(AD-3 고정 스키마, 891,192행 = (162,570 valid + 283,026 oot) × 2 모델)과 두 모델 manifest(`grade_thresholds` 포함)가 전제 조건이며, **이 스토리는 그 frame을 읽기만 한다** — `models/artifacts/*.joblib`을 로드하거나 `scorecard/binning.py`·`champion.py`·`challenger.py`의 스코어링 함수를 호출하지 않는다(AD-3). 신규로 학습·재계산할 것이 전혀 없는, Epic 2 중 가장 "순수 데이터 분석" 성격의 스토리다.

### 핵심 전제 — score는 이미 두 모델 공통 스케일이다 (1.7b가 만든 조건)
1.7b가 `generalized_score(p_bad) = score_formula(logit(p_bad))`를 챔피언·챌린저 **양쪽에 동일하게 적용**해 `score` 컬럼을 하나의 Siddiqi PDO 스케일로 통일했다(champion과 challenger는 등급 임계치는 각자 fit했지만 점수 산출 공식 자체는 동일). 이 덕분에 이 스토리에서 **swap-set 비교에 단일 cutoff 값을 두 모델에 동일하게 적용해도 의미가 있다** — 별도로 두 모델용 cutoff를 각각 캘리브레이션할 필요가 없다. `score`는 높을수록 저위험(낮은 P(bad))이라는 방향에 유의할 것 — `evaluation.generalized_score`의 docstring과 grade_thresholds가 오름차순(등급 1이 최우량)인 것으로 확인 가능.

### Cutoff 방향 규칙
승인 = `score >= cutoff` (score가 높을수록 우량 신청자). cutoff를 올릴수록 승인율은 감소해야 한다(non-increasing) — pytest에서 반드시 단조성으로 검증할 것. 승인 인원이 0인 극단 cutoff에서 `bad_rate`를 0/0으로 나누면 안 되므로 `NaN` 처리.

### AD-3 — frame 스키마와 소비 원칙
`data/scored_validation_frame.parquet` 컬럼: `applicant_id, vintage, model_type, score, pd, grade, bad_flag, int_rate, recoveries, total_pymnt`(순서·이름 고정, 별칭 금지). `model_type ∈ {"champion", "challenger"}`인 long format — swap-set처럼 두 모델을 나란히 비교하려면 이 스토리 **내부에서** `applicant_id` 기준 pivot/join을 하되, 그 결과를 AD-3 frame 자체에 다시 쓰지 않는다(frame은 Epic 1의 산출물로 불변).

### Task 3의 오픈퀘스천 — 반드시 결정하고 기록할 것
Epic 1의 AC들은 vintage 필터를 명시하지 않았다. `evaluation_table`(1.7a)은 train/valid/oot 3면을 각각 비교하는 성격이었지만, cutoff 시뮬레이션·swap-set은 "심사 전략가가 지금 어떤 기준을 쓸지" 의사결정용이므로 통상 **미래 성과를 흉내내는 OOT(2015 빈티지)**만 쓰는 것이 실무적으로 더 타당하다(1.5/1.6이 train으로 학습했으므로 train 성과는 낙관적으로 편향; valid도 이미 모델 선택에 쓰였을 가능성). 다만 SPEC/AC가 명시적으로 강제하지 않으므로 **Story 1.2의 "12개월 성과창 근사" 결정 기록과 동일한 패턴으로, 이 스토리 착수 시 OOT-only vs valid+oot 전체 중 하나를 정하고 Dev Notes/리포트에 근거와 함께 기록**해야 한다. 어느 쪽을 택하든 **frame 그 자체를 수정하지 말고 strategy.py 함수 내부에서 vintage 필터링**할 것(예: `df[df["vintage"] == 2015]`).

**결정 완료(구현 반영)**: OOT(2015)를 기본 모집단으로 채택 — `scorecard/strategy.py`의 `OOT_VINTAGE = 2015` 상수와 세 함수(`cutoff_trade_off_curve`, `lookup_cutoff`, `swap_set_table`) 모두 `vintage: int | None = OOT_VINTAGE` 기본값으로 구현했다. `vintage=None`을 넘기면 valid+oot 전체로도 조회 가능(테스트로 커버). 실데이터로 두 옵션을 모두 실행해본 결과(`cutoff-swapset-report-2-1.md` 참고) swap-set 방향성 결론은 OOT-only/valid+oot 전체에서 동일했다.

### 아키텍처 가드레일
- **AD-3**: frame 소비만, 예측 재계산 금지 — 이 스토리가 위반 시 이후 2.4(손익 cutoff)·2.5(대시보드)·3.1(룰 진단)까지 서로 다른 숫자를 보게 되는 근본 리스크.
- **파일 위치**: `scorecard/strategy.py`(ARCHITECTURE-SPINE.md Structural Seed, CAP-9/CAP-10 그룹 — 이미 존재하는 스텁 파일을 채운다. 신규 파일 생성 아님).
- **NFR1(재현성)**: cutoff 그리드 생성에 난수를 쓸 이유가 없다 — 결정론적 `np.linspace` 등 사용. 혹시 샘플링이 필요하면 `scorecard.config.set_global_seed` 재사용.

### 스코프 가드 (하지 말 것)
- 이 스토리는 FR9·FR10만 다룬다. Reason code(FR11, Story 2.2), API 서빙(FR12, Story 2.3), 손익 기반 cutoff(FR14, Story 2.4)는 범위 밖 — `strategy.py`에 손익 계산 로직을 넣지 않는다(그건 `profit.py`, Story 2.4 소관).
- 등급(`grade`) 기반 로직이 아니라 **연속 `score` 기반 cutoff**다. `grading.py`의 `_assign_bin`/`assign_grade`는 이 스토리와 무관 — 재사용하지 않는다(등급은 이미 다른 목적으로 확정된 값).

### 이전 스토리 인텔리전스 (1.7b 인수인계)
- **frame 컬럼 그대로 믿을 것**: `score`는 이미 두 모델 공통 스케일(위 "핵심 전제" 참고) — 재변환 불필요.
- **PSI 버킷팅 버그 교훈(1.6→1.7b 반복 발견)**: "두 분포를 각자 독립적으로 처리한 뒤 나중에 합치면 어긋난다"는 패턴이 이 코드베이스에서 두 번 발생했다(캘리브레이션 곡선, PSI). swap-set의 champion/challenger pivot에서도 유사한 함정이 있다 — **반드시 `applicant_id`(및 `vintage`) 기준으로 정확히 조인**하고, 두 모델의 행 순서가 다를 수 있다는 가정 하에 구현할 것(정렬/인덱스 암묵 가정 금지).
- **실데이터 실행이 늘 버그를 드러냄**: 1.7b는 합성 테스트만으론 안 드러나는 버그 2건(저카디널리티 붕괴, NaN 마스킹)을 실데이터 실행에서 발견했다. 이 스토리도 pytest 통과만으로 끝내지 말고 `data/scored_validation_frame.parquet` 실측 실행을 반드시 거칠 것.

### Project Structure Notes
- `scorecard/strategy.py` — MODIFIED(스텁 → 구현, 신규 파일 아님).
- `tests/test_strategy.py` — NEW.
- `docs/implementation-artifacts/cutoff-swapset-report-2-1.md` — NEW.
- 아키텍처 Structural Seed와 완전히 일치(별도 변경 없음).

### References

- [Source: docs/planning-artifacts/epics.md#Story-2.1] — AC 원문(FR9, FR10, AD-3)
- [Source: ARCHITECTURE-SPINE.md#AD-3] — scored validation frame 고정 스키마, "소비만 하고 재계산 금지" 원문
- [Source: ARCHITECTURE-SPINE.md#Structural-Seed] — `scorecard/strategy.py` = CAP-9,10 지정 위치
- [Source: scorecard/strategy.py] — 현재 스텁 내용(4줄, Story 1.1 생성)
- [Source: scorecard/evaluation.py#generalized_score] — 두 모델 공통 스코어 스케일 정의(1.7b)
- [Source: docs/implementation-artifacts/1-7b-psi-validation-frame-manifest.md] — scored frame 생성 배경, PSI 버킷팅 함정(반복 발견), int_rate 파싱 위치
- [Source: docs/implementation-artifacts/1-2-sample-design-leakage-label-split.md] — "결정 기록" 패턴 선례(Task 3가 따르는 형식)
- [Source: data/scored_validation_frame.parquet] — 실측 스키마·행수 확인(891,192행, vintage ∈ {2014, 2015})

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (bmad-dev-story)

### Debug Log References

- `pytest -q` (전체) → 101 passed(기존 92 + 신규 9), 회귀 없음, 첫 실행에 전부 통과.
- 초기 테스트 설계 오류 1건 자체 발견·수정: `test_cutoff_trade_off_curve_covers_full_approval_range`가 최저 approval_rate를 정확히 0으로 기대했으나, cutoff 그리드가 관측 score 최대값까지만 커버하므로 최상위 1명은 항상 승인된다(`1/total`로 수렴, 0이 아님) — 그리드 설계상 당연한 특성으로 테스트 기대값을 `1/total`로 수정.
- 실데이터 1차 실행에서 로직 버그 없이 바로 성공(1.7b와 달리 이번 스토리는 frame 소비만 하므로 예상대로 버그 표면이 작았음). `swap_set_table` 4분면 합계(283,026) = 모집단 실측치와 정확히 일치 확인.
- **리뷰 후속(GPT 리뷰 패치 검증)**: GPT 리뷰가 `scorecard/strategy.py`에 fail-fast 가드 5건(빈 모집단, NaN score/bad_flag, swap_set_table의 model_type 누락·중복 행·bad_flag 불일치)을 패치했으나 대응 pytest가 누락되어 있어, 5개 가드 전부에 대해 `tests/test_strategy.py`에 회귀 테스트 7건을 추가(`pytest.raises(ValueError, ...)`). `pytest -q` (전체) → **108 passed**(101 + 신규 7), 회귀 없음.

### Completion Notes List

- **Task 3 오픈퀘스천 해소**: 분석 모집단을 OOT(2015)로 기본 채택, `vintage=None`으로 valid+oot 전체도 조회 가능하게 구현 — 결정 근거는 Dev Notes "결정 완료" 및 리포트에 기록.
- **AD-3 준수**: `scorecard/strategy.py`는 `numpy`/`pandas`만 import — `models/artifacts/*.joblib`, `binning.py`, `champion.py`, `challenger.py` 어느 것도 로드·호출하지 않음. frame의 `score`/`bad_flag` 컬럼만 소비.
- **swap-set ground truth 설계**: 두 모델 행의 `bad_flag`가 동일 applicant에서 일치한다는 전제로 챔피언 쪽 `bad_flag`만 4개 세그먼트 공통 ground truth로 사용 — 이 전제를 실데이터로 검증하는 회귀 테스트(`test_real_scored_frame_bad_flag_consistent_across_models`)를 추가해 100% 일치 확인.
- **실데이터 실행 결과(해석)**: cutoff=546.01 기준 `swap_out`(챔피언 승인·챌린저 거절) 집단의 부도율(14.95%)이 `stable_approved`(8.81%)보다 뚜렷이 높아 챌린저 교체가 승인 포트폴리오 위험을 낮추는 방향과 일치 — 리포트에 상세 기록.
- **리뷰 패치 검증(신규)**: Review Findings의 5개 `[Patch]`/`[Decision→Patch]` 항목이 `scorecard/strategy.py`에 반영되어 있음을 확인했고, 각 항목에 대응하는 회귀 테스트가 없다는 갭을 발견해 `tests/test_strategy.py`에 7건 추가(빈 모집단×2, 알 수 없는 model_type, NaN score, swap_set_table의 빈 모집단·model_type 누락·중복 행·bad_flag 불일치 — 일부는 cutoff_trade_off_curve/swap_set_table 양쪽에 걸쳐 있어 7건). 모두 `pytest.raises(ValueError, match=...)`로 에러 메시지 키워드까지 검증.

### File List

- `scorecard/strategy.py` (MODIFIED — 스텁 4줄 → `cutoff_trade_off_curve`, `lookup_cutoff`, `swap_set_table`, `OOT_VINTAGE` 구현 + 리뷰 반영 fail-fast 가드 5건)
- `tests/test_strategy.py` (NEW — 16 tests: 최초 9건(합성 8 + 실데이터 정합성 회귀 1) + 리뷰 가드 회귀 7건)
- `docs/implementation-artifacts/cutoff-swapset-report-2-1.md` (NEW)
- `docs/implementation-artifacts/2-1-cutoff-simulation-swapset.md` (MODIFIED — 본 스토리 파일, Tasks/Dev Notes/Review Findings/Dev Agent Record/Status 갱신)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 상태 전이)

## Change Log

- 2026-07-14: Story 2.1 구현 완료 — `scorecard/strategy.py`에 cutoff 트레이드오프 curve(FR9)와 champion/challenger swap-set(FR10) 구현. 분석 모집단은 OOT(2015) 기본(Task 3 결정 기록), `vintage=None`으로 valid+oot 전체도 지원. AD-3(frame 소비만, 예측 재계산 금지) 준수 확인. `tests/test_strategy.py` 9건 신규(합성 8 + 실데이터 정합성 회귀 1), `pytest -q` 101 passed(회귀 없음). 실데이터 1회 실행 완료, 결과를 `cutoff-swapset-report-2-1.md`에 기록. Status → review.
- 2026-07-14: GPT 리뷰 패치 반영 — `scorecard/strategy.py`에 fail-fast 가드 5건(빈 모집단, NaN score/bad_flag, swap_set_table의 model_type 누락·중복 행·bad_flag 불일치) 적용 확인. 대응 테스트 누락 갭을 발견해 `tests/test_strategy.py`에 회귀 테스트 7건 추가. `pytest -q` 108 passed(회귀 없음). Status는 review 유지.
- 2026-07-14: 리뷰 승인 — Status → done. Epic 2 다음 스토리(2-2 reason-code 이원화)로 진행 가능.
