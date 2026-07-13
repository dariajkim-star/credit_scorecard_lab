---
baseline_commit: 1c6ce0ff02fb0f02f12b503ea2687f54a899a5e8
---

# Story 1.1: 프로젝트 스캐폴딩과 데이터 확보

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 모형 개발자,
I want .venv 환경과 Lending Club 원본 데이터를 빈티지 필터된 parquet으로 준비하고,
so that 이후 모든 스토리가 재현 가능한 환경과 가벼운 데이터 위에서 시작할 수 있다.

## Acceptance Criteria

**Given** Python 3.12과 requirements.txt가 있는 빈 프로젝트
**When** .venv 생성·의존성 설치 후 kagglehub로 Lending Club accepted loans를 다운로드하면
1. usecols+dtype 지정 로드 → 2012~2015 빈티지·36개월물 필터 → `data/` 하위 parquet 저장이 완료된다
2. kagglehub 실패 시 폴백(Kaggle CLI 또는 수동 다운로드) 절차가 README 스텁에 기록된다 (Kaggle 계정/키 필요 여부 확인 포함)
3. parquet 재생성 스크립트(`pipelines/01_download.py`)가 존재한다 (NFR5)
4. pytest가 구동되는 tests/ 골격과 시드 고정 유틸이 존재한다 (NFR1, NFR3)

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC를 만족하고, `pytest -q`가 초록으로 통과하며, 생성된 parquet의 행 수·빈티지 분포·term 단일값(36개월)이 로그로 출력되어야 done.

## Tasks / Subtasks

- [x] Task 1: 그린필드 디렉토리 스캐폴딩 생성 (AC: 3, 4)
  - [x] `scorecard/`, `pipelines/`, `notebooks/`, `app/`, `dashboard/`, `sas/`, `models/artifacts/`, `data/`, `tests/`, `docs/` 디렉토리 생성 (Structural Seed 준수)
  - [x] 각 Python 패키지 디렉토리(`scorecard/`, `app/`, `pipelines/`, `tests/`)에 `__init__.py` 생성
  - [x] `.gitkeep`으로 gitignore된 빈 디렉토리(`models/artifacts/`, `data/`) 추적 유지 (선택) — 생성했으나 두 디렉토리가 .gitignore 대상이라 git엔 미추적. 재생성 스크립트가 data/를 만들므로 무해.
- [x] Task 2: 재현성 기반 유틸 (AC: 4 / NFR1)
  - [x] `scorecard/config.py` — `RANDOM_SEED = 42` 상수 + `set_global_seed()` (random, numpy 시드 고정, numpy는 lazy import) 구현
  - [x] 경로 상수(PROJECT_ROOT, DATA_DIR, ARTIFACTS_DIR) + 표본 고정 상수(VINTAGE_MIN/MAX, TERM_MONTHS, ACCEPTED_PARQUET)를 한 곳에 정의 (ASCII 전용, NFR6)
- [x] Task 3: 데이터 다운로드·변환 파이프라인 (AC: 1, 3 / Phase 0)
  - [x] `pipelines/01_download.py` — kagglehub로 `wordsforthewise/lending-club` 다운로드 (thin CLI, 로직은 `pipelines/loading.py`로 분리해 테스트 가능화)
  - [x] usecols(28컬럼: 후속 스토리 대비 광범위) + dtype 지정 로드 (원본 1.6GB+ 메모리 리스크 대응)
  - [x] `issue_d`에서 빈티지 파생 → 2012~2015 유지, `term` == 36개월만 유지
  - [x] 필터 결과를 `data/lc_accepted_2012_2015_36m.parquet`로 저장 (pyarrow)
  - [x] 실행 로그: 원본 행 수 → 필터 후 행 수 → 빈티지별 건수 → term 유일값 출력
  - [x] kagglehub 실패 시 폴백 처리: 명확한 에러 메시지 + `--csv` 재실행 옵션 + README 폴백 안내 (AC 2)
- [x] Task 4: 폴백 문서화 & README 스텁 (AC: 2)
  - [x] `README.md` — "Data acquisition" 섹션에 kagglehub 방식 + Kaggle CLI/수동 다운로드 폴백 3단계, Kaggle 계정·API 키 필요 여부 확인 안내 기록
- [x] Task 5: pytest 골격 (AC: 4 / NFR3)
  - [x] `tests/test_smoke.py` — 시드 결정성·경로 상수·표본 고정 상수 테스트 (4개)
  - [x] `tests/test_loading.py` — 필터 로직 합성 데이터 단위 테스트 (5개, 네트워크·대용량 다운로드 불요)
  - [x] `pytest.ini`(testpaths=tests, ASCII) 작성
  - [x] `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -q` → 9 passed
- [x] Task 6: .venv 셋업 및 검증
  - [x] `python -m venv .venv` (Python 3.12.10) → `pip install -r requirements.txt` 성공
  - [x] `import optbinning, lightgbm, fastapi, kagglehub, shap, optuna` 스모크 OK

## Dev Notes

### 이 스토리의 성격
- **그린필드 첫 스토리** = 이전 스토리 없음. 전체 Structural Seed(아래) 뼈대를 세우고 Phase 0(셋업·데이터 확보)만 수행한다. 모델링 로직(sample_design 이후)은 **이 스토리 범위 밖** — 빈 `__init__.py`와 디렉토리만 만들고 채우지 않는다.
- 현재 리포 상태: `requirements.txt`, `.gitignore`(`.venv/ data/ models/artifacts/ .env` 등 이미 포함), `API_SPEC.md`, `DEV_PLAN.md`, `docs/`(planning-artifacts·specs)만 존재. **소스 코드 폴더는 아직 하나도 없다** — 전부 이 스토리에서 생성.

### 데이터 소스 (검증 필요)
- Kaggle 데이터셋 slug 추정: **`wordsforthewise/lending-club`** (파일 `accepted_2007_to_2018Q4.csv.gz`). dev 착수 시 `kagglehub.dataset_download("wordsforthewise/lending-club")` 반환 경로에서 실제 파일명을 **먼저 확인**하고 하드코딩하지 말 것. slug가 다르면 README 폴백 절차대로 수동 확보.
- NFR8(데이터·표본 고정): Kaggle Lending Club accepted loans(2007~2018Q4), **train/valid=2012~2014 빈티지, OOT=2015 빈티지, 36개월물 우선**. 이 스토리는 2012~2015 전체를 필터해 저장만 하고, train/valid/OOT **분할은 Story 1.2 소관**. 라벨 생성(bad/good)도 1.2 소관 — 여기서는 원시 컬럼 그대로 저장.
- `issue_d` 포맷은 `"Dec-2015"` 형태 문자열 — 연도 파싱 시 주의(`pd.to_datetime(format="%b-%Y")`).
- usecols는 최소한으로 시작하되 **후속 스토리가 필요로 하는 컬럼을 미리 포함**해야 재다운로드를 피한다: 최소 `issue_d, term, loan_status, int_rate, recoveries, total_pymnt, last_pymnt_d, emp_title, loan_amnt, annual_inc, dti, grade, sub_grade, fico_range_low, fico_range_high` + 신청시점 주요 변수. 넓게 잡되 명백한 사후(post-origination) 컬럼 다수는 1.2 누수 감사에서 걸러지므로 이 단계에서 과도하게 좁힐 필요 없음. (메모리 부담 시 usecols 축소가 1순위 대응)

### 아키텍처 가드레일 (반드시 준수)
- **Structural Seed** (ARCHITECTURE-SPINE.md#Structural-Seed) — 정확히 이 트리를 만든다:
  ```
  credit_scorecard-lab/
  ├── app/ (main.py, schemas.py, loader.py)   # 이 스토리는 빈 골격만
  ├── scorecard/ (sample_design.py … text_features.py = CAP별 1파일)  # 빈 골격만
  ├── pipelines/          # 01_download.py 여기
  ├── notebooks/
  ├── dashboard/
  ├── sas/
  ├── models/artifacts/   # gitignore
  ├── data/               # gitignore
  ├── tests/
  └── docs/MDD.md         # docs는 이미 존재, MDD.md는 3.4 스토리 소관
  ```
  주의: `scorecard/*.py` 스텁을 미리 만들지 여부는 재량 — 만든다면 빈 파일 + 헤더 주석(CAP 번호)만. 로직 금지.
- **AD-8 배포 봉투** [Source: ARCHITECTURE-SPINE.md#AD-8]: 로컬 dev 전용. DB 없음, parquet/파일 기반. 컨테이너·클라우드·CI 도입 금지.
- **NFR5** [Source: epics.md#NonFunctional]: 데이터·모델 아티팩트는 gitignore, **재생성 스크립트로 대체**. `01_download.py`가 그 스크립트. `data/`, `models/artifacts/`는 이미 .gitignore됨(확인 완료).
- **NFR6** [Source: epics.md#NonFunctional]: 설정 파일 ASCII 우선(cp949 인코딩 이슈 회피). `pytest.ini`/`pyproject.toml`/`config.py`는 ASCII 유지, 한글 주석 지양.
- **NFR1/NFR3** [Source: epics.md#NonFunctional]: 전 실험 시드 고정 + 노트북/스크립트 이원화, pytest 단위 테스트. 시드 유틸은 이후 모든 스토리가 import.

### 스코프 가드 (하지 말 것)
- 라벨 생성, train/valid/OOT 분할, 누수 감사 → **Story 1.2**. 여기서 하면 스토리 경계 침범.
- WOE/모델/API/대시보드 로직 일절 금지. 디렉토리·__init__.py 골격까지만.
- reject inference, rejected loans 파일 처리는 SPEC Non-goal — 언급만(README/MDD), 구현 금지.

### 환경·실행 규약 [Source: stack.md]
- 환경: `.venv`(Python 3.12). Windows 경로이므로 인터프리터는 `.venv/Scripts/python.exe`.
- 테스트 실행: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -q`
- OS: Windows 11, PowerShell 우선. venv 활성화 없이 `.venv/Scripts/python.exe` 직접 호출이 안전.

### Project Structure Notes
- 리포 루트는 `credit_scorecard-lab/`이며 planning 산출물이 `docs/planning-artifacts`, specs가 `docs/specs`에 이미 있음. 코드는 루트 직하위에 Structural Seed대로 배치(별도 `src/` 계층 없음 — 스파인이 flat 구조 지정).
- 변경 대상 파일은 전부 **NEW**. 기존 파일(`requirements.txt`, `.gitignore`) 수정 불요(이미 충분). README는 신규 생성(스텁).
- `_bmad/bmm/config.yaml`의 planning/implementation 경로가 valueup-washing-lab을 가리키는 전역 오설정이 있으나, 이 프로젝트의 실제 산출물은 `credit_scorecard-lab/docs/**` — dev 시 경로 혼동 주의.

### References
- [Source: docs/planning-artifacts/epics.md#Story-1.1] — AC 원문, 그린필드 스캐폴딩 지침, 가정·미결정(kagglehub 폴백)
- [Source: docs/planning-artifacts/epics.md#NonFunctional] — NFR1,3,5,6,8
- [Source: docs/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md#Structural-Seed] — 디렉토리 트리
- [Source: docs/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md#AD-8] — 로컬 dev 전용 봉투
- [Source: docs/specs/spec-credit-scorecard-lab/stack.md] — 스택 버전, 실행 규약, 리스크(원본 1.6GB usecols+dtype 대응)
- [Source: requirements.txt] — 고정 의존성(이미 작성됨)

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

- `pytest -q` → 9 passed in 1.28s
- 스모크 임포트: `optbinning, lightgbm, fastapi, kagglehub, shap, optuna` OK
- end-to-end 파이프라인 검증: 합성 `accepted.csv.gz`(4행: 2012/36m, 2015/60m, 2016/36m, 2013/36m)로 `01_download.py --csv` 실행 → 2012·2013 36m 2행만 통과, 2015-60m·2016 정확히 제외, parquet 저장 + 요약 로그 확인 후 합성 산출물 정리.

### Completion Notes List

- **범위 준수**: Structural Seed 전체 뼈대 + Phase 0(셋업·데이터 확보)만 구현. `scorecard/*.py`는 CAP 번호 헤더만 있는 스텁(로직 없음) — 라벨/분할/누수감사는 Story 1.2 소관으로 남김.
- **테스트 전략**: 1.6GB 실다운로드·Kaggle 인증 없이 검증 가능하도록 필터 로직을 `pipelines/loading.py` 순수 함수로 분리(`01_download.py`는 파일명이 숫자로 시작해 import 불가하므로 thin CLI). 다운로드 자체는 사용자가 `01_download.py` 실행 시 수행(폴백 README 기록).
- **데이터 소스 미검증 주의**: Kaggle slug `wordsforthewise/lending-club` + `accepted_*.csv.gz` 글롭으로 파일 탐색. 실제 다운로드 시 반환 경로에서 파일명 재확인 필요(README·스토리 Dev Notes에 명시).
- **usecols 광범위 채택**: 28개 컬럼(신청시점 후보변수 + 손익/라벨용 recoveries·total_pymnt·last_pymnt_d 포함)을 미리 로드해 재다운로드 회피. int_rate·revol_util 등 `%` 포함 컬럼은 string으로 안전 로드, 수치 변환은 1.3 소관.
- **버전 메모**: 설치된 실제 버전이 requirements 하한보다 상위(numpy 2.4, pandas 2.3, scikit-learn 1.9, fastapi 0.139 등). 현 스토리 테스트는 전부 통과하나 후속 스토리에서 API 차이 발생 가능성 유의.
- **빈 디렉토리**: `dashboard/`, `sas/`, `notebooks/`는 이 스토리에서 파일이 없어 git에 미추적(정상). `models/artifacts/`·`data/`는 .gitignore 대상.

### File List

- `README.md` (NEW)
- `pytest.ini` (NEW)
- `scorecard/__init__.py` (NEW)
- `scorecard/config.py` (NEW)
- `scorecard/sample_design.py` (NEW, stub)
- `scorecard/preprocessing.py` (NEW, stub)
- `scorecard/binning.py` (NEW, stub)
- `scorecard/champion.py` (NEW, stub)
- `scorecard/challenger.py` (NEW, stub)
- `scorecard/evaluation.py` (NEW, stub)
- `scorecard/grading.py` (NEW, stub)
- `scorecard/strategy.py` (NEW, stub)
- `scorecard/reasons.py` (NEW, stub)
- `scorecard/profit.py` (NEW, stub)
- `scorecard/rule_efficiency.py` (NEW, stub)
- `scorecard/text_features.py` (NEW, stub)
- `app/__init__.py` (NEW, stub)
- `pipelines/__init__.py` (NEW)
- `pipelines/loading.py` (NEW)
- `pipelines/01_download.py` (NEW)
- `tests/__init__.py` (NEW)
- `tests/test_smoke.py` (NEW)
- `tests/test_loading.py` (NEW)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 상태 전이)

## Change Log

- 2026-07-13: Story 1.1 구현 완료 — 그린필드 스캐폴딩(Structural Seed), 재현성 유틸(config.py), Lending Club 다운로드·필터 파이프라인(loading.py + 01_download.py), README 데이터확보/폴백 문서, pytest 골격(9 passed). Status → review.
