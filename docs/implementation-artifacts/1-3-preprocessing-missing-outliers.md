---
baseline_commit: e5ca061a3feea0feb1cca7e78c0f5f4d1d18b53f
---

# Story 1.3: 결측·이상치 전처리

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 모형 개발자,
I want 결측=별도 빈 원칙과 캡핑 규칙으로 데이터를 정제하고,
so that 비닝 단계가 안전한 입력을 받으면서 결측의 정보량도 보존된다.

## Acceptance Criteria

**Given** 1.2의 라벨·분할된 표본 (`label_and_filter` + `split_by_vintage`의 결과)
**When** `scorecard/preprocessing.py`로 정제하면
1. 결측은 대치(imputation)하지 않고 별도 빈 처리 대상으로 표시된다 (FR2) — 즉 이 스토리는 결측을 채우지 않고, 결측 그대로 두어 Story 1.4의 optbinning이 결측 전용 빈으로 처리할 수 있게 dtype/타입만 안전하게 정리한다
2. 이상치 캡핑 규칙이 수치형 피처에 적용된다 (FR2)
3. 정제 규칙 문서(어떤 컬럼에 어떤 캡·근거)와 정제 전후 분포 비교 리포트가 산출된다
4. 캡핑 로직에 pytest가 있다

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC를 만족하고 `pytest -q`가 초록으로 통과하며, 캡핑 전후 각 수치형 컬럼의 min/max/mean이 리포트에 나타나야 done. 결측치 개수는 캡핑 전후 동일해야 한다(캡핑이 결측을 채우면 안 됨 — 대치 금지 원칙 위반이므로 즉시 실패로 간주).

## Tasks / Subtasks

- [x] Task 1: 타입 정리 — `%` 문자열 수치 컬럼 파싱 (선행 필수, 스토리 문서에 없던 발견 사항)
  - [x] `parse_percent(series) -> pd.Series` 구현: `"45.3%"` → `45.3`(Float64, 퍼센트 그대로 유지), 결측/파싱실패는 NA 유지(대치 아님)
  - [x] `revol_util` 최초 float 변환 지원(`coerce_percent_columns`)
  - [x] `int_rate`는 1.2에서 이미 배제된 피처이므로 손대지 않음(NUMERIC_COLUMNS에 없음 — `_assert_matches_feature_candidates`로 보증)
  - [x] `tests/test_preprocessing.py`에 `parse_percent` 단위 테스트: 정상/결측/공백/파싱실패 케이스
- [x] Task 2: 수치형/범주형 컬럼 분류 (AC: 1, 2 준비 작업)
  - [x] `NUMERIC_COLUMNS`(12개)/`CATEGORICAL_COLUMNS`(6개) 정의 + `_assert_matches_feature_candidates()`로 `feature_candidate_columns()`와의 합집합 일치를 모듈 로드 시점에 자동 검증(드리프트 방지)
  - [x] 범주형 컬럼은 no-op/pass-through 명시(테스트로 `coerce_percent_columns`가 지정 컬럼만 건드림을 확인)
- [x] Task 3: 결측 처리 원칙 구현 (AC: 1)
  - [x] `missing_summary(df, columns)` 구현 — 건수·비율 산출, 대치 없음
  - [x] `fillna`/`SimpleImputer` 등 일체 미사용(코드 전체 확인)
  - [x] `test_apply_caps_never_fills_missing`으로 캡핑 전후 결측 개수 불변 보증
- [x] Task 4: 이상치 캡핑 (AC: 2)
  - [x] `fit_caps(train_df, columns, lower_q=0.01, upper_q=0.99)` 구현 — train에서만 분위수 계산
  - [x] `apply_caps(df, caps)` 구현 — `Series.clip`, NaN 통과 확인
  - [x] NaN 유지 테스트 통과
  - [x] 캡 경계값이 `fit_caps` 반환값 자체(데이터 기반, 도메인 하드코딩 아님) — 근거는 "train 1%/99% 분위수"
- [x] Task 5: 분포 비교 리포트 (AC: 3)
  - [x] `distribution_report(before_df, after_df, columns)` 구현
  - [x] `docs/implementation-artifacts/preprocessing-report-1-3.md` 작성 — 규칙 문서 + 실데이터 재실행 스니펫 + 합성 예시
- [x] Task 6: pytest 및 회귀 검증 (AC: 4)
  - [x] `tests/test_preprocessing.py` — 10개 테스트(합성 데이터, 네트워크·실데이터 불요)
  - [x] `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -q` → 31 passed (기존 21 + 신규 10)
  - [x] **실제 parquet 재확인**(`test -f data/lc_accepted_2012_2015_36m.parquet` → 없음, 2026-07-14). 합성 데이터로만 검증

## Dev Notes

### 이 스토리의 성격
- Story 1.2(누수감사·라벨·분할)의 다음 단계. **`scorecard/preprocessing.py`는 현재 4줄짜리 스텁**(CAP-2 헤더 주석만) — 이 스토리가 최초로 로직을 채운다.
- 입력은 1.2의 산출물: `label_and_filter(df)` → `split_by_vintage(...)`가 반환하는 `{"train": df, "valid": df, "oot": df}` 딕셔너리. 각 df는 원본 컬럼(1.1의 USECOLS+vintage) + `bad_flag`(Int64)를 가짐.
- **캡은 train에서만 fit하고 valid/oot엔 동일 캡을 적용**(fit-on-train 원칙) — 이는 Story 1.4가 WOE를 train에서 fit해 valid/oot에 transform만 적용할 예정인 것과 동일한 패턴이며, AD-2(train/serve parity)의 정신과 일치한다. 캡을 매 split마다 새로 계산하면 valid/oot 고유의 분포 정보가 캡 경계에 스며들어(약한 형태의) 정보 누수가 된다.
- 스코프 경계: **WOE/IV 비닝·상관 제거·변수 최종선정은 Story 1.4 소관**. 이 스토리는 결측 방치 + 이상치 캡핑까지만. 범주형 컬럼의 인코딩(원-핫 등)도 1.4/1.5의 optbinning이 처리 — 이 스토리에서 손대지 말 것.

### 발견 사항 — `%` 문자열 컬럼 (스토리 계획 시점엔 몰랐던 것)
1.1의 `pipelines/loading.py`가 `revol_util`을 `dtype="string"`으로 로드했다(원본 값이 `"45.3%"` 같은 `%` suffix 문자열이라 숫자로 바로 못 읽음). **이 스토리가 그 변환을 처음 수행해야 한다** — 안 하면 `fit_caps`가 문자열 컬럼에 분위수를 계산하려다 에러나거나(정렬은 되지만 숫자 분위수가 아님) 조용히 틀린 값을 낼 수 있다. `int_rate`도 동일한 dtype이지만 **1.2 누수감사에서 이미 배제**되었으므로 이 스토리에서 손댈 필요 없다(피처 후보 21개 목록엔 애초에 없음 — `feature_candidate_columns()` 확인).

### 아키텍처 가드레일
- 모듈 위치 고정: `scorecard/preprocessing.py` = CAP-2 (ARCHITECTURE-SPINE.md Capability→Architecture Map).
- Paradigm(Pipes-and-Filters) + 1.1/1.2가 확립한 패턴: 로직은 순수 함수(입력 DataFrame → 출력 DataFrame/dict), pytest 가능, thin 실행 스크립트는 필요시만 별도 `pipelines/`.
- NFR1(재현성): 이 스토리엔 랜덤성이 없음(분위수는 결정론적) — `set_global_seed` 불필요.
- NFR6(ASCII): 신규 파일 ASCII 우선.
- **대치(imputation) 절대 금지**: FR2의 "결측=별도 빈 원칙"은 이 프로젝트의 핵심 설계 결정이다(optbinning이 결측 전용 빈을 만들어 정보량을 보존하는 것이 목적) — `fillna`, `SimpleImputer`, 평균/중앙값 대치 등 어떤 형태로도 결측을 채우면 FR2 위반이자 이후 1.4의 비닝 설계와 충돌한다.

### 스코프 가드 (하지 말 것)
- 결측 대치(imputation) — 절대 금지, 위 참고
- WOE/IV 비닝, 상관 제거, 변수 최종선정 → Story 1.4
- 범주형 인코딩(원-핫 등) → 1.4의 optbinning이 처리
- 스코어카드/모델 학습 → Story 1.5~1.6
- `emp_length`("10+ years", "< 1 year" 등)를 숫자로 파싱하는 것은 범위 밖 — 그건 파생변수/피처엔지니어링에 가까우며 1.4가 optbinning으로 범주형 그대로 비닝하거나 필요시 결정할 사안. 이 스토리는 건드리지 않는다.

### 이전 스토리(1.2) 인텔리전스
- **완료 상태**: Story 1.2 done(코드리뷰 2건 패치+1건 문서화, 커밋 `a406aac`→`e5ca061`). `pytest -q` 21 passed.
- **재사용 가능한 함수**: `scorecard.sample_design.feature_candidate_columns()` — 21개 피처 후보 목록의 유일한 소스. 이 스토리가 수치형/범주형으로 나눌 때 반드시 이 함수를 기준으로 삼을 것(하드코딩한 별도 컬럼 목록을 새로 만들지 말 것 — 1.2가 확정한 배제 목록과 어긋날 위험).
- **코드 패턴**: 순수 함수 + nullable dtype(`Int64`)로 파싱 실패를 조용히 float64로 흘리지 않기(1.1 코드리뷰에서 발견된 함정) — `parse_percent`도 동일하게 파싱 실패 시 dtype이 안정적이어야 함(nullable `Float64` 사용 권장, `.astype("Float64")`).
- **알려진 함정 재확인**: (a) dtype 플립 — 결측/파싱실패가 하나라도 있으면 일반 float64/int64 연산이 조용히 타입을 바꿀 수 있음, nullable dtype으로 명시할 것. (b) 조용한 행/그룹 손실 — 1.2에서 `split_by_vintage`가 미매칭 vintage를 조용히 버리다 코드리뷰로 잡힌 전례가 있음, 이 스토리에서도 캡핑이 결측 개수를 바꾸지 않는지 반드시 테스트로 확인(Task 4).
- **실데이터 부재**: 1.1의 `data/lc_accepted_2012_2015_36m.parquet`이 1.2 시점까지 이 dev 환경에 존재하지 않았다(사용자가 아직 실다운로드 안 함). 이 스토리 착수 시에도 재확인하고, 없으면 합성 데이터로만 검증(Task 6).
- **버전 메모**: `.venv` 설치된 pandas 2.3.3, numpy 2.4.6 — 지금까지 문제 없었음.

### Project Structure Notes
- 신규 파일: `scorecard/preprocessing.py`(스텁 → 구현으로 교체), `tests/test_preprocessing.py`(NEW), `docs/implementation-artifacts/preprocessing-report-1-3.md`(NEW, 1.2의 `sample-design-report-1-2.md`와 동일한 위치·패턴).
- `data/`, `models/artifacts/`는 gitignore 대상 — 이 스토리 산출물을 파일로 저장한다면 그 경로 하위(커밋 대상 아님).

### References
- [Source: docs/planning-artifacts/epics.md#Story-1.3] — AC 원문
- [Source: docs/planning-artifacts/epics.md#NonFunctional] — NFR1, NFR6
- [Source: docs/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md#Capability→Architecture-Map] — CAP-2 = `scorecard/preprocessing.py`
- [Source: pipelines/loading.py] — DTYPES(`revol_util`/`int_rate`가 string인 이유), USECOLS 계약
- [Source: scorecard/sample_design.py] — `feature_candidate_columns()`(21개 피처 후보, 이 스토리가 수치/범주 분류의 기준으로 삼을 유일한 소스), `label_and_filter`/`split_by_vintage`(입력 계약)
- [Source: docs/implementation-artifacts/1-2-sample-design-leakage-label-split.md] — 이전 스토리 Dev Notes/Completion Notes 전체(위 "이전 스토리 인텔리전스" 절에 핵심만 발췌)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (bmad-dev-story)

### Debug Log References

- `pytest -q` → 31 passed (기존 21 + 신규 10), 처음 작성한 테스트 그대로 전부 통과(재수정 없었음)
- `test -f data/lc_accepted_2012_2015_36m.parquet` → 파일 없음(2026-07-14 dev 환경, 1.1/1.2와 동일). 실데이터 e2e 미수행, 합성 데이터로만 검증

### Completion Notes List

- **드리프트 방지 가드 추가**: `NUMERIC_COLUMNS`/`CATEGORICAL_COLUMNS`가 `feature_candidate_columns()`(1.2의 유일한 소스)와 어긋나면 모듈 임포트 시점에 `AssertionError`로 즉시 실패하도록 `_assert_matches_feature_candidates()`를 모듈 로드 시 실행 — 1.2 코드리뷰에서 발견된 "상수 드리프트로 인한 조용한 데이터 손실" 패턴을 이 스토리에서는 사전에 차단.
- **fit-on-train 원칙**: `fit_caps`는 train split에서만 분위수를 계산하고 `apply_caps`로 valid/oot에 동일 캡을 적용 — Story 1.4의 WOE fit-on-train 패턴과 일관되게 설계(스토리 오너 판단, Dev Notes에 근거 기록).
- **결측 방치 원칙 준수**: 코드 전체에 `fillna`/`SimpleImputer` 등 대치 로직 없음. `test_apply_caps_never_fills_missing`이 캡핑 전후 결측 개수 불변을 직접 검증.
- **실데이터 미검증**: 1.1/1.2와 동일하게 이 dev 환경엔 실parquet이 없어 전부 합성 데이터로 검증. `preprocessing-report-1-3.md`에 실데이터 재실행용 스니펫 기록.
- **범위 준수**: `emp_length` 같은 범주형 컬럼의 숫자 파싱(예: "10+ years" → 10)은 의도적으로 손대지 않음 — 스토리 Dev Notes의 스코프 가드에 따름(1.4 소관 가능성 있는 피처엔지니어링).

### File List

- `scorecard/preprocessing.py` (MODIFIED — 스텁 → 구현: NUMERIC_COLUMNS, CATEGORICAL_COLUMNS, parse_percent, coerce_percent_columns, missing_summary, fit_caps, apply_caps, distribution_report)
- `tests/test_preprocessing.py` (NEW — 10 tests)
- `docs/implementation-artifacts/preprocessing-report-1-3.md` (NEW)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 상태 전이)

## Senior Developer Review (AI)

- 리뷰 일자: 2026-07-14, 도구: claude /code-review (medium)
- 결과: Changes Requested → 1건 패치 완료(사용자 확인 후), 1건 그대로 defer
- Findings (2건: CONFIRMED 1 / PLAUSIBLE 1):
  - [x] [Med/correctness] 모든 NUMERIC_COLUMNS에 동일한 1%/99% 분위수 캡핑 적용 시 `pub_rec` 같은 극도로 치우친(zero-inflated) 카운트형 컬럼에서 실제 다른 위험도(2건 vs 5건)가 동일 값으로 뭉개짐(실증 재현). → 사용자 확인 후 `delinq_2yrs`·`inq_last_6mths`·`pub_rec`를 `CAPPING_EXCLUDED_COLUMNS`로 분리, `CAPPABLE_NUMERIC_COLUMNS`(9개)만 캡핑 대상으로 함. 회귀 가드 테스트 2개 추가.
  - [ ] [Low/correctness, PLAUSIBLE — defer] train split이 전부 결측이면 `fit_caps`가 (NaN, NaN)을 반환하고 `apply_caps`가 경고 없이 캡핑을 무효화. 실데이터에서 발생 가능성 낮음(피처 후보 컬럼이 전부 결측일 정도면 더 근본적인 데이터 문제) — 낮은 심각도로 그대로 둠.

## Change Log

- 2026-07-14: Story 1.3 구현 완료 — `%` 문자열 파싱(revol_util), 결측 방치 원칙(대치 없음), train-fit 이상치 캡핑, 전후 분포 리포트. pytest 31 passed(합성 데이터, 실parquet 미존재). Status → review.
- 2026-07-14: 코드리뷰 1건 패치(zero-inflated 카운트 컬럼 캡핑 제외) + 1건 defer, 33 passed.
