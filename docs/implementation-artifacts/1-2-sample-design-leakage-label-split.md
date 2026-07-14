---
baseline_commit: 6c11c322b7bf9cc74f209324c5538ee5a4ccade1
---

# Story 1.2: 표본 설계 — 누수 감사·라벨·분할

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 모형 개발자,
I want 신청시점 기준 누수 필드를 배제하고 빈티지 기반 train/valid/OOT를 분리하고,
so that 모형이 실제 심사 시점에 쓸 수 없는 정보로 학습되는 것을 원천 차단한다.

## Acceptance Criteria

**Given** 1.1의 parquet 데이터 (`data/lc_accepted_2012_2015_36m.parquet`)
**When** 전 컬럼을 신청시점/사후 이분 감사하면 (`scorecard/sample_design.py`)
1. 배제 필드 목록 문서(필드별 배제 근거 포함)가 산출된다 (FR1, 애매하면 배제 보수 원칙)
2. bad=`Charged Off/Default`, good=`Fully Paid`, 진행중 제외 라벨이 생성되고 라벨 생성 로직에 pytest가 있다 (NFR8)
3. train/valid=2012~2014, OOT=2015 분할과 3그룹 건수·부도율 테이블이 산출된다
4. 12개월 성과창 근사(last_pymnt_d 기반) 채택 여부를 EDA 근거와 함께 결정 기록으로 남긴다 (SPEC open question 해소)

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC를 만족하고 `pytest -q`가 초록으로 통과하며, train/valid/OOT 3그룹 각각의 건수·bad_rate가 로그/문서로 출력되어야 done. 어느 그룹도 0건이면 실패(표본 설계 오류).

## Tasks / Subtasks

- [x] Task 1: 누수 필드 감사 (AC: 1)
  - [x] `scorecard/sample_design.py`에 `audit_columns()` 구현 — USECOLS 28개 컬럼(+vintage)을 "id/label_source/application_time/post_origination"으로 분류
  - [x] 사후 필드로 분류: `recoveries`, `total_pymnt`, `last_pymnt_d`. `loan_status`는 label_source로 별도 취급
  - [x] `grade`/`sub_grade`/`int_rate`를 보수적으로 배제(순환논리 근거 명시)
  - [x] `docs/implementation-artifacts/leakage-audit-1-2.md`로 문서화 (필드·분류·배제여부·근거 4열, `audit_columns()`에서 생성)
- [x] Task 2: 라벨 생성 (AC: 2 / NFR8)
  - [x] `make_label(df)`(Int64, 1/0/NA) + `label_and_filter(df)`(NA행 제거) 구현
  - [x] `tests/test_sample_design.py`에 bad/good/제외 3케이스 + 대소문자·공백 변형 불일치(정확 매칭) 테스트
- [x] Task 3: 빈티지 기반 분할 (AC: 3)
  - [x] `split_by_vintage(df)` 구현: train=2012-2013, valid=2014, oot=2015 (결정: 시간 기반 결정론적 분할 채택, RNG 불필요 — story Dev Notes에 근거 기록)
  - [x] `split_summary(groups)`로 건수·bad_rate 테이블 산출, `docs/implementation-artifacts/sample-design-report-1-2.md`에 실행 방법 기록
  - [x] 빈 그룹이면 `ValueError` (경고 아닌 즉시 실패) — 테스트로 검증
- [x] Task 4: 12개월 성과창 결정 기록 (AC: 4 — SPEC open question 해소)
  - [x] `performance_window_months(df)` 구현(EDA 도구, synthetic 검증 완료)
  - [x] 결정: 만기 기준 라벨을 유일 정의로 채택, 12개월 근사 미채택 — 근거를 `sample-design-report-1-2.md`에 문서화
  - [x] 12개월 근사 구현은 범위 밖 유지(도구만 제공)
- [x] Task 5: pytest 및 통합 검증
  - [x] `tests/test_sample_design.py` — audit/label/split/performance_window 10개 테스트 (합성 데이터, 네트워크·실데이터 불요)
  - [x] `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -q` → 20 passed (기존 10 + 신규 10)
  - [x] **실제 parquet 부재 확인**(`test -f data/lc_accepted_2012_2015_36m.parquet` → 없음, 2026-07-14 dev 환경). 합성 데이터로만 검증 — `sample-design-report-1-2.md`에 실데이터 실행용 1줄 스니펫 기록해둠

## Dev Notes

### 이 스토리의 성격
- Story 1.1(스캐폴딩+데이터 확보)의 다음 단계. **`scorecard/sample_design.py`는 현재 4줄짜리 스텁**(CAP-1 헤더 주석만) — 이 스토리가 최초로 실제 로직을 채운다.
- 입력은 1.1이 만든 `data/lc_accepted_2012_2015_36m.parquet` (컬럼: 1.1의 `USECOLS` 28개 + `vintage`(Int64, 코드리뷰로 dtype 고정 완료)). **주의**: 이 parquet은 gitignore 대상이라 실제로 존재하는지는 실행 환경마다 다름 — 사용자가 아직 실다운로드를 안 했을 수 있음. 존재하면 실측, 없으면 합성 데이터로 로직만 검증(Task 5 참고).
- 스코프 경계: **WOE/비닝/전처리는 Story 1.3~1.4 소관**, 이 스토리는 라벨+분할까지만. `champion.py`/`preprocessing.py` 등 다른 스텁 건드리지 말 것.

### 누수 감사 — 컬럼별 판정 가이드 (1.1의 USECOLS 기준, `pipelines/loading.py` 참조)
1.1이 로드한 28개 컬럼을 다음과 같이 분류할 것(스토리 오너가 실제 데이터로 재검증 필요, 아래는 출발점):

| 분류 | 컬럼 | 비고 |
|---|---|---|
| 식별자/타이밍 | `id`, `issue_d`, `term`, `vintage` | 피처 아님, 분할/추적용 |
| 라벨 원천 | `loan_status` | 피처로 쓰지 않음 — `make_label`의 입력 |
| 신청시점(피처 후보) | `loan_amnt`, `emp_title`, `emp_length`, `home_ownership`, `annual_inc`, `verification_status`, `purpose`, `dti`, `delinq_2yrs`, `fico_range_low`, `fico_range_high`, `inq_last_6mths`, `open_acc`, `pub_rec`, `revol_bal`, `revol_util`, `total_acc`, `addr_state` | 신청 시점에 이미 알 수 있는 값 — 대부분 유지 후보 |
| 애매(보수적 배제 검토) | `grade`, `sub_grade`, `int_rate` | Lending Club이 심사 후 배정하는 값 — 실제 신청 시점 심사역이 모형을 쓸 때는 아직 모름(모형이 곧 이걸 대체하는 것). **배제 원칙 적용 권장**(FR1 근거: "신청시점 기준" — grade/int_rate는 LC 자체 심사 결과이므로 우리 모형의 학습 타깃과 순환논리·데이터 누수) |
| 사후(배제 확정) | `recoveries`, `total_pymnt`, `last_pymnt_d` | 대출 종료 후에만 알 수 있음. `recoveries`/`total_pymnt`는 Story 2.4(손익 cutoff)가 scored validation frame에서 사용하므로 **parquet에는 남기되 champion/challenger 피처셋에서는 배제** — 1.4(변수선정)로 넘길 "후보 제외" 표시만 이 스토리에서 남기면 충분 |

이 표는 초안이다. 실데이터 컬럼 설명(Lending Club data dictionary)과 대조해 최종 배제 목록을 확정하고 AC1의 문서 산출물에 근거를 적을 것.

### 라벨 정의 (NFR8, 절대 임의 변경 금지)
[Source: docs/planning-artifacts/epics.md#NonFunctional NFR8] — bad=`loan_status ∈ {Charged Off, Default}`, good=`Fully Paid`, 진행중(Current 등) 제외. train/valid=2012~2014 빈티지, OOT=2015 빈티지, 36개월물. **어느 스토리도 이 정의를 임의로 바꿀 수 없다** — 이미 1.1이 36개월물 필터를 적용해 parquet에 반영했으므로, 이 스토리는 라벨만 추가하면 됨.

### 아키텍처 가드레일
- 모듈 위치 고정: `scorecard/sample_design.py` = CAP-1 (ARCHITECTURE-SPINE.md Capability→Architecture Map). 다른 모듈에 로직 분산 금지.
- Paradigm(Pipes-and-Filters): 이 스토리는 파이프라인의 첫 실제 필터 단계. 순수 함수(입력 DataFrame → 출력 DataFrame/Series/dict) 형태를 유지해 1.1의 `pipelines/loading.py` 스타일(로직은 import 가능한 모듈, thin 실행 스크립트는 필요시 `pipelines/02_sample_design.py`로 별도)과 일관되게 갈 것.
- NFR1(재현성): 랜덤 분할을 쓴다면 `scorecard.config.RANDOM_SEED`와 `set_global_seed()`를 반드시 사용(1.1이 만든 유틸, 이미 검증됨).
- NFR6(ASCII): 신규 파일은 ASCII 우선.

### 스코프 가드 (하지 말 것)
- WOE/IV 비닝, 상관 제거, 변수 최종선정 → Story 1.4
- 결측·이상치 전처리 → Story 1.3 (이 스토리는 원본 값 그대로 라벨·분할만)
- 스코어카드/모델 학습 → Story 1.5~1.6
- 이 스토리가 만드는 "배제 필드 목록"은 문서일 뿐, 실제 컬럼 드롭(피처셋 확정)은 1.4가 수행 — 여기서는 판정과 근거만 남기면 된다.

### 이전 스토리(1.1) 인텔리전스
- **완료 상태**: Story 1.1 done(코드리뷰 4건 패치 반영, 커밋 `6c11c32`). `pytest -q` 10 passed.
- **재사용 가능한 유틸**: `scorecard.config`(`RANDOM_SEED`, `set_global_seed()`, `DATA_DIR`, `ACCEPTED_PARQUET`, `VINTAGE_MIN/MAX`, `TERM_MONTHS`) — 이 스토리가 그대로 import해서 쓸 것. 새로 만들지 말 것.
- **코드 패턴**: `pipelines/loading.py`처럼 "로직은 순수 함수로 분리해 pytest 가능하게, thin 실행 스크립트는 별도"가 이 프로젝트의 확립된 패턴. `scorecard/sample_design.py`도 동일하게: 함수는 여기, 실행이 필요하면 `pipelines/02_*.py`에 CLI 래퍼(선택사항 — story AC가 스크립트 파일을 요구하지 않으므로 `scorecard/sample_design.py`에 직접 함수만 둬도 무방).
- **알려진 함정(1.1 코드리뷰에서 발견)**: pandas의 `.dt.year` 같은 파생 컬럼은 결측/파싱실패 시 dtype이 float64로 조용히 바뀔 수 있다 — 이 스토리에서 새 파생 컬럼(예: 성과기간 개월수)을 만들 때도 동일 위험 주의, nullable dtype(`Int64`) 명시할 것. 또한 nullable dtype과 스칼라 비교(`Int64 == int`) 시 NA 전파로 조용히 행이 빠질 수 있음 — 필터링 후 반드시 그룹별 건수를 로그로 남겨 예상과 다르면 즉시 드러나게 할 것(1.1의 `[filter]`/`[warn]` 로그 패턴 참고).
- **버전 메모**: `.venv` 설치된 pandas 2.3.3, numpy 2.4.6(requirements.txt 하한보다 상위) — 지금까지 문제 없었음.

### Project Structure Notes
- 신규 파일: `scorecard/sample_design.py`(스텁 → 구현으로 교체), `tests/test_sample_design.py`(NEW).
- 문서 산출물(`leakage-audit-1-2.md` 등)은 story Dev Notes에 인라인으로 남겨도 되고 별도 md로 분리해도 됨 — 스토리 오너 재량. 별도 파일로 만들 경우 `docs/implementation-artifacts/` 하위에 둘 것(sprint-status의 `story_location`과 일치).
- `data/`, `models/artifacts/`는 gitignore 대상이므로 이 스토리의 산출물(라벨 붙은 데이터프레임 등)을 파일로 저장한다면 그 경로 하위에 둘 것 — 커밋 대상 아님.

### References
- [Source: docs/planning-artifacts/epics.md#Story-1.2] — AC 원문
- [Source: docs/planning-artifacts/epics.md#NonFunctional] — NFR1, NFR6, NFR8(라벨·표본 고정 정의, 절대 불변)
- [Source: docs/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md#Capability→Architecture-Map] — CAP-1 = `scorecard/sample_design.py`
- [Source: docs/specs/spec-credit-scorecard-lab/stack.md#리스크·대응] — "성과기간 정의 논쟁 여지" 리스크, 만기 기준 주 정의 채택 근거
- [Source: pipelines/loading.py] — USECOLS 28컬럼 계약, vintage/term 필터 로직(1.1에서 이미 적용됨)
- [Source: scorecard/config.py] — RANDOM_SEED, set_global_seed, 경로·표본 상수 (재사용)
- [Source: docs/implementation-artifacts/1-1-scaffolding-data-acquisition.md] — 이전 스토리 Dev Notes/Completion Notes 전체(위 "이전 스토리 인텔리전스" 절에 핵심만 발췌)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 (bmad-dev-story)

### Debug Log References

- `pytest -q` → 20 passed (기존 10 + 신규 10)
- 초기 테스트 실패 1건: `test_split_summary_reports_rows_and_bad_rate`에서 예상 bad_rate 계산 오류(1/3 → 실제 2/3, train 그룹 {a:good, b:bad, c:bad}) — 테스트 수식 수정 후 통과
- `performance_window_months` 합성 검증: issue=Jan-2013/last=Jan-2016 → 36개월, 파싱실패 → NA, 동월 → 0개월 확인
- `test -f data/lc_accepted_2012_2015_36m.parquet` → 파일 없음(2026-07-14 dev 환경). 실데이터 e2e는 수행하지 못함 — 합성 데이터 20개 테스트로만 검증

### Completion Notes List

- **결정 사항 1 (train/valid 분할 방식)**: 랜덤 분할 대신 **빈티지 연도 기반 결정론적 분할**(train=2012-2013, valid=2014, oot=2015) 채택. SPEC에 명시 없어 스토리 오너 재량으로 결정 — RNG 의존성 제거, 완전 재현 가능. `scorecard.sample_design.py` 모듈 docstring 인근에 근거 기록.
- **결정 사항 2 (12개월 성과창)**: 미채택. `sample-design-report-1-2.md`에 근거 기록 — `loan_status`가 이미 만기 기준 종결 상태를 제공하므로 근사가 불필요하고, 중도 상태 오분류 위험이 있어 이번 스토리 범위에서는 제외. `performance_window_months()`는 도구로만 제공(향후 부록 실험용).
- **실데이터 미검증 주의**: 1.1의 `data/lc_accepted_2012_2015_36m.parquet`이 이 dev 환경에는 없음(gitignore 대상, 사용자가 별도로 다운로드해야 생성됨). 모든 검증은 합성 데이터. 사용자가 실다운로드 후 `sample-design-report-1-2.md`의 스니펫으로 실측 건수·bad_rate를 재확인해야 함.
- **누수 감사 판정 근거**: `grade`/`sub_grade`/`int_rate`를 보수적으로 배제(Lending Club 자체 심사 결과이므로 라벨과 순환논리). `recoveries`/`total_pymnt`/`last_pymnt_d`는 parquet엔 남기되(Story 2.4 손익계산·본 스토리 성과창 EDA용) 피처셋에서는 배제 — 실제 드롭은 Story 1.4 소관.
- **재사용**: 1.1의 nullable Int64 패턴(파싱 실패 시 dtype 안정성)을 `make_label`·`performance_window_months`에 동일 적용해 1.1 코드리뷰에서 발견된 float64 플립 함정을 처음부터 회피.

### File List

- `scorecard/sample_design.py` (MODIFIED — 스텁 → 구현: audit_columns, feature_candidate_columns, make_label, label_and_filter, split_by_vintage, split_summary, performance_window_months)
- `tests/test_sample_design.py` (NEW — 10 tests)
- `docs/implementation-artifacts/leakage-audit-1-2.md` (NEW)
- `docs/implementation-artifacts/sample-design-report-1-2.md` (NEW)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 상태 전이)

## Change Log

- 2026-07-14: Story 1.2 구현 완료 — 누수 감사(28컬럼 분류+문서화), bad/good 라벨링(NFR8), 빈티지 기반 train/valid/OOT 분할(결정론적), 12개월 성과창 미채택 결정 기록. pytest 20 passed(합성 데이터, 실parquet 미존재). Status → review.
