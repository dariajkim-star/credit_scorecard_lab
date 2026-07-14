---
baseline_commit: e6d595a
---

# Story 1.4: WOE 비닝과 변수선정 (optbinning 스파이크 포함)

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 모형 개발자,
I want 전 변수를 WOE/IV로 비닝하고 IV+상관/VIF로 최종 변수셋을 확정하고,
so that 판별력 있고 중복 없는 변수만 스코어카드에 들어간다.

## Acceptance Criteria

**Given** 1.3의 정제된 표본 (percent 파싱 + 캡핑 적용된 train/valid/oot)
**When** optbinning으로 전 후보 변수를 단조 제약 비닝하면 (`scorecard/binning.py` — AD-2 단일 소스)
1. 변수별 WOE/IV 테이블이 산출된다 (FR3)
2. IV 필터 후 pairwise 상관 ≤0.7이 되도록 중복 변수가 제거되고 선정 근거가 문서화된다
3. **스토리 착수 첫 작업으로 optbinning 스파이크 검증**을 수행하고, 실패 시 수동 분위수 비닝 폴백으로 전환한 기록을 남긴다 (최약 가정 A1 보강)
4. 비닝 변환에 pytest가 있다 (NFR3)

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC + `pytest -q` 초록. 스파이크는 "합성 데이터에서 OptimalBinning fit→transform(metric='woe')이 단조 이벤트율로 동작 + 결측 별도 빈 확인"이 통과 기준. 선정된 최종 변수셋의 pairwise |상관| 최댓값이 0.7 이하임을 코드로 검증(문서 주장만으로는 불충분).

## Tasks / Subtasks

- [x] Task 1: optbinning 스파이크 (AC: 3 — **반드시 첫 작업으로 수행 완료**)
  - [x] 합성 데이터로 수치형·범주형 fit → transform → IV 추출 검증 — 전부 PASS, 폴백 불필요
  - [x] 확인 결과: ① monotonic_trend 동작(이벤트율 완전 단조) ② 결측 Missing 빈 분리 ③ **nullable Float64/string 직접 수용**(어댑터 불필요) ④ IV는 `binning_table.build().loc["Totals","IV"]`
  - [x] **핵심 발견**: `transform`의 기본 `metric_missing=0`이 결측을 WOE 0으로 조용히 매핑(Missing 빈 WoE −1.27인 케이스에서 재현) → `metric_missing="empirical"` 필수. binning.py 전 transform 경로에 반영 + 회귀 테스트. 스파이크 상세는 `binning-selection-report-1-4.md`
- [x] Task 2: WOE 비닝 엔진 (AC: 1 / AD-2)
  - [x] `fit_binning(train_df, y, variables)` — train에서만 fit, NUMERIC/CATEGORICAL 상수 재사용, 수치형은 auto_asc_desc 단조 제약, y 결측 시 ValueError
  - [x] `transform_woe(df, binners)` — 유일한 WOE 변환 경로(AD-2), metric_missing/special="empirical"
  - [x] `iv_table(binners)` — IV 내림차순 테이블
  - [x] `emp_title` 제외(`BINNING_EXCLUDED_COLUMNS`) — 후보 17개, 근거 주석+문서
  - [x] (1.5 대비) `bin_edges(binners)` — woe_bin_edges manifest 키용 접근자
- [x] Task 3: IV 필터 + 상관 제거 (AC: 2)
  - [x] `select_variables(woe_df, iv_tbl, iv_min=0.02, corr_max=0.7)` — IV 필터 → IV 내림차순 그리디 상관 제거 → 선정/탈락 근거 테이블
  - [x] 최종 셋 off-diagonal |상관| > 0.7이면 AssertionError (코드 강제)
  - [x] fico 쌍둥이 케이스: 정확히 하나만 생존함을 테스트로 확인
- [x] Task 4: 선정 근거 문서화 (AC: 2)
  - [x] `docs/implementation-artifacts/binning-selection-report-1-4.md` — 스파이크 결과표, 후보 17개 근거, 선정 규칙, VIF 생략 근거, 실데이터 스니펫
- [x] Task 5: pytest 및 회귀 (AC: 4)
  - [x] `tests/test_binning.py` — 10개 테스트(후보 목록, nullable 수용, y 결측 거부, 단조 WOE, 결측 empirical WOE(0 아님), train/valid 동일 규칙, IV 순서, bin_edges, 선정/탈락, 상관 상한)
  - [x] `pytest` → **43 passed** (기존 33 + 신규 10)
  - [x] 실parquet 여전히 없음(2026-07-14) — 합성 검증만, 기록

## Dev Notes

### 이 스토리의 성격
- **`scorecard/binning.py`는 AD-2의 단일 소스** — 여기 구현되는 WOE 변환이 이후 champion(1.5), reasons(2.2), app/loader(2.3)가 전부 import해서 쓰는 유일한 경로. 재구현 금지 조항의 원본이 이 파일이다. 설계 시 "fit 산출물(binners)이 joblib로 직렬화 가능해야 함"(AD-1 아티팩트 번들에 포함될 예정)을 염두에 둘 것 — optbinning 객체는 joblib 직렬화 가능(sklearn 스타일).
- 입력 계약: 1.2 `label_and_filter`+`split_by_vintage` → 1.3 `coerce_percent_columns`(revol_util)+`apply_caps`(CAPPABLE 9개만) 순서로 정제된 splits. **bad_flag가 y(Int64)**.
- **피처 후보는 18개**(`feature_candidate_columns()` — 수치 12 + 범주 6). 주의: `leakage-audit-1-2.md` 본문에 "21 fields"라고 적힌 것은 오타(실제 나열·코드 모두 18개). 문서 수정은 이 스토리에서 겸사겸사 해도 되고 안 해도 됨.
- 비닝 실제 대상: 18 − emp_title(3.2 소관 제외) = **17개**.

### 스파이크가 첫 작업인 이유 (엘리시테이션 A1)
epics.md 스토리 설계 지침: "optbinning 스파이크 검증을 E1 초반 배치(최약 가정 A1 보강)". optbinning 0.21.0이 .venv에 설치·임포트 확인은 됐지만(1.1) **실제 fit/transform/단조제약/결측빈/nullable dtype 수용 여부는 미검증**. 특히 1.3 산출물이 nullable Float64/Int64인데 optbinning 내부는 numpy 배열 기반이라 nullable을 못 받을 가능성이 실질적 리스크 — 스파이크에서 확인하고, 필요하면 binning.py 안에 `to_numpy(dtype=float, na_value=np.nan)` 어댑터를 두는 것으로 해결(AD-2 위반 아님 — 변환 로직이 단일 모듈 안에 있으면 됨).

### 아키텍처 가드레일
- **AD-2 (핵심)**: WOE 변환 로직은 `scorecard/binning.py` 단일 모듈에만. 파이프라인 스크립트와 `app/loader.py` 둘 다 이 모듈을 import. 다른 모듈에 WOE 수식 복제 금지.
- **AD-1 대비**: 1.5에서 champion manifest에 `woe_bin_edges` 필수키가 들어간다 — binners에서 빈 경계를 추출할 수 있는 접근자(예: `binning_table` 활용)를 이 스토리에서 노출해두면 1.5가 편해짐(과설계는 금물, 접근 경로만 확인).
- fit-on-train / transform-everywhere: 1.3 캡핑과 동일 원칙.
- NFR6(ASCII), NFR1(결정론 — optbinning MIP 솔버는 결정론적이지만 만일을 위해 고정 파라미터 기록).

### 스코프 가드 (하지 말 것)
- 스코어카드 점수 변환(PDO 스케일링) → Story 1.5
- LightGBM/모델 학습 → 1.5~1.6
- emp_title 텍스트 파생 → Story 3.2
- VIF는 AC에 "상관/VIF"로 병기되어 있으나 pairwise 상관 ≤0.7 달성이 명시 성공기준 — 상관 제거로 충분하면 VIF는 생략 가능(WOE 단변량 변환 후에는 pairwise 상관이 관행상 충분). 생략 시 근거 한 줄 기록.

### 이전 스토리 인텔리전스 (1.1~1.3 누적)
- **패턴**: 순수 함수 + 합성 데이터 pytest + 실데이터 부재 시 재실행 스니펫 문서화. nullable dtype 명시(Int64/Float64)로 dtype 플립 방지. 상수 드리프트는 로드 시점 assert로 차단(1.3의 `_assert_matches_feature_candidates` 패턴 — 이 스토리도 비닝 대상 목록이 preprocessing 상수와 어긋나지 않게 동일 가드 권장).
- **1.3 코드리뷰 학습**: zero-inflated 카운트 3종(delinq_2yrs, inq_last_6mths, pub_rec)은 캡핑 미적용 원값 — optbinning이 직접 비닝(이게 제외의 전제였음). 비닝 대상에는 **포함**된다.
- **실parquet 부재 지속**(1.1~1.3 전부): 이번에도 합성 검증 예상.
- 커밋 이력: 각 스토리 = 구현 커밋 + 리뷰패치 커밋 + done 커밋 패턴.

### References
- [Source: docs/planning-artifacts/epics.md#Story-1.4] — AC 원문, 스파이크 지침
- [Source: ARCHITECTURE-SPINE.md#AD-2] — binning.py 단일 소스
- [Source: ARCHITECTURE-SPINE.md#AD-1] — woe_bin_edges manifest 필수키(1.5 대비)
- [Source: scorecard/preprocessing.py] — NUMERIC/CATEGORICAL/CAPPABLE 상수, 정제 입력 계약
- [Source: scorecard/sample_design.py] — feature_candidate_columns(18), bad_flag
- [Source: docs/implementation-artifacts/preprocessing-report-1-3.md] — 정제 파이프라인 재실행 스니펫(이 스토리 입력의 생성 절차)

## Dev Agent Record

### Agent Model Used

claude-fable-5 (bmad-dev-story)

### Debug Log References

- 스파이크 3회 실행: ① 수치형 nullable Float64 + 단조 + IV — PASS ② 범주형 + 정보성 결측 — Missing 빈 WoE −1.20 확인, 그러나 transform이 0.0 반환 ③ `metric_missing="empirical"` 전달 시 −1.27로 테이블과 일치 확인
- `pytest` → 43 passed. 테스트 1건 초기 실패: 픽스처 y가 fico로만 생성돼 home_ownership IV≈0으로 정당 탈락 → 픽스처에 home 효과 추가 후 통과(구현 문제 아님)
- protobuf DeprecationWarning 2건은 optbinning→ortools 임포트 경유, 무해
- 실parquet 부재 재확인(1.1~1.4 연속)

### Completion Notes List

- **스파이크 성공, 폴백 미사용**: optbinning 0.21.0이 nullable dtype 직접 수용 — 어댑터 불필요. 수동 분위수 비닝 폴백은 구현하지 않음(AC3의 "실패 시에만" 조건 미충족).
- **가장 중요한 산출**: `metric_missing=0` 기본값 함정 발견·차단. 이 플래그 없이는 FR2의 "결측=별도 빈" 설계 전체가 서빙 시점에 조용히 무력화된다. `transform_woe`가 유일 경로(AD-2)이므로 이 지점 한 곳만 지키면 전 시스템이 보호됨 — AD-2의 가치를 실증한 사례.
- **선정 로직**: IV<0.02 필터 → IV 내림차순 그리디 상관 제거(낮은 IV 쪽 탈락) → 최종 셋 상관 상한을 AssertionError로 강제. VIF는 생략(WOE 단변량 변환 후 pairwise 0.7이 업계 관행이자 AC 명시 기준 — 리포트에 근거 기록).
- **1.5 대비**: `bin_edges()` 접근자로 AD-1 manifest의 `woe_bin_edges` 키 추출 경로 확보.
- **드리프트 가드 연속성**: BINNING_CANDIDATES는 preprocessing 상수에서 파생(17개 assert 테스트) — 1.3의 패턴 유지.

### File List

- `scorecard/binning.py` (MODIFIED — 스텁 → 구현: BINNING_CANDIDATES, fit_binning, transform_woe, iv_table, bin_edges, select_variables)
- `tests/test_binning.py` (NEW — 10 tests)
- `docs/implementation-artifacts/binning-selection-report-1-4.md` (NEW)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 상태 전이)

## Senior Developer Review (AI)

- 리뷰 일자: 2026-07-14, 도구: claude /code-review (medium) — 구현 세션(fable-5)과 다른 세션(sonnet-5)에서 진행, 코드를 신뢰하지 않고 실증 검증
- 결과: Changes Requested → 2건 전부 패치 완료
- Findings (2건: PLAUSIBLE 1 / CONFIRMED 1):
  - [x] [Med/correctness] `select_variables`의 post-selection assertion(AC2의 "최종 |corr|≤0.7" 정량 보장)이 `.max().max()`의 skipna 기본값 때문에 NaN 상관계수(상수/퇴화 WOE 컬럼 발생 시)를 조용히 건너뜀 — 실증 재현. `skipna=False`로 1차 수정했으나 대각선 마스킹 자체가 NaN이라 정상 케이스까지 깨짐(테스트 2건 실패) → `np.triu_indices`로 상삼각만 추출해 대각선과 실제 NaN을 구분하는 방식으로 재수정, 회귀 테스트(`test_select_variables_raises_on_nan_correlation`) 추가.
  - [x] [Low/efficiency] `select_variables`가 루프 반복마다 `iv_tbl.set_index("variable")` 재구축 — 루프 앞에서 `iv_map = dict(zip(...))` 한 번만 생성하도록 변경.
- 검증한 것(문제 없음 확인): IV 필터→그리디 상관 제거 로직 자체(합성 데이터로 fico 쌍둥이·약변수 정확히 처리 확인), `metric_missing="empirical"` 처리.

## Change Log

- 2026-07-14: Story 1.4 구현 완료 — optbinning 스파이크(PASS, metric_missing 함정 발견), WOE 비닝 엔진(AD-2 단일 소스), IV+상관 변수선정, bin_edges 접근자. pytest 43 passed(합성 데이터, 실parquet 미존재). Status → review.
- 2026-07-14: 코드리뷰 2건 패치(NaN 상관 검사 강화 + iv_map 캐싱), 44 passed.
