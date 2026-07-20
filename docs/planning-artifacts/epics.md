---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - docs/specs/spec-credit-scorecard-lab/SPEC.md
  - docs/specs/spec-credit-scorecard-lab/stack.md
  - docs/specs/spec-credit-scorecard-lab/pipeline-diagram.md
  - ../API_SPEC.md
  - docs/planning-artifacts/architecture/architecture-credit-scorecard-lab-2026-07-10/ARCHITECTURE-SPINE.md
---

# credit-scorecard-lab - Epic Breakdown

## Overview

이 문서는 credit-scorecard-lab의 에픽·스토리 분해를 담는다. 이 프로젝트는 PRD 대신 **SPEC-first 경로**(bmad-spec → bmad-architecture)로 진행했으므로, 아래 FR 목록은 `SPEC.md`의 CAP-1~17(각 intent+success)에서, NFR 목록은 SPEC의 Constraints에서, Additional Requirements는 `ARCHITECTURE-SPINE.md`의 AD-1~9에서 추출했다. 별도 UX 스펙 문서는 없음(대시보드 UI 요구사항은 CAP-13으로 이미 FR에 포함).

## Requirements Inventory

### Functional Requirements

FR1 (CAP-1): 신청시점 기준 누수 필드를 배제하고 빈티지 기반 train/valid/OOT 표본을 분리한다. 성공기준: 배제 필드 목록 문서 + 3그룹 건수·부도율 테이블 산출.
FR2 (CAP-2): 결측=WOE 별도 빈, 이상치=캡핑 규칙으로 정제한다. 성공기준: 정제 규칙 문서 + 전후 분포 비교 리포트.
FR3 (CAP-3): 전 변수 WOE/IV 비닝 후 IV+상관/VIF로 최종 변수셋을 선정한다. 성공기준: IV 테이블 산출 + pairwise 상관 ≤0.7.
FR4 (CAP-4): PDO=20, Base=600 로지스틱 스코어카드(챔피언)를 구축한다. 성공기준: 신청 1건 점수 산출 + 계수 부호가 상식과 일치.
FR5 (CAP-5): Optuna 튜닝 LightGBM + isotonic/Platt calibration(챌린저)을 학습한다. 성공기준: calibration 전후 Brier score 개선 + 캘리브레이션 곡선.
FR6 (CAP-6): 챔피언·챌린저를 train/valid/OOT 3면에서 AUC·KS·PR-AUC로 비교한다. 성공기준: 3면 비교표 + OOT 챔피언 KS≥0.25 & 챌린저 AUC≥0.70.
FR7 (CAP-7): 점수를 1~10등급으로 매핑하고 단조성을 검증한다. 성공기준: 등급별 부도율 완전 단조.
FR8 (CAP-8): train 대비 OOT의 변수·점수 분포 PSI를 산출한다. 성공기준: 점수 PSI < 0.1.
FR9 (CAP-9): cutoff에 따른 승인율-부도율 트레이드오프 곡선을 산출한다. 성공기준: 전 구간 curve + 특정 cutoff 즉시 조회.
FR10 (CAP-10): 챔피언→챌린저 교체시 판정이 바뀌는 swap-set을 정량화한다. 성공기준: swap-in/out 건수 + 부도율 비교표.
FR11 (CAP-11): 개별 신청 건의 사유 top3를 모형 유형별(점수손실/SHAP)로 산출한다. 성공기준: 완성된 한국어 문장 최대 3개 반환. *(개정 2026-07-16, Story 2.2 리뷰: 실제 불리 요인만 사유로 인정 — 안전한 신청 건은 3개 미만(0건 포함)이 정상. SPEC CAP-11·API_SPEC v0.3 동일 개정.)*
FR12 (CAP-12): FastAPI로 점수·PD·등급·reason code·cutoff 시뮬레이션을 서빙한다(판정은 하지 않음). 성공기준: API_SPEC.md 전 엔드포인트 pytest 통과 + `/v1/score` p95<300ms.
FR13 (CAP-13): Streamlit으로 성능·등급분포·PSI·cutoff를 시각화한다. 성공기준: 4개 화면 라이브 구동.
FR14 (CAP-14, 킥①): int_rate/recoveries로 손익 기반 cutoff을 산출한다. 성공기준: 현재 대비 최적 cutoff의 승인율·연간기대손익 delta가 assumptions와 함께 산출.
FR15 (CAP-15, 킥②): 가상 하드룰셋의 배제집단 부도율·기회손실·verdict를 규칙기반으로 진단한다. 성공기준: 룰 3개 이상 verdict 리포트.
FR16 (CAP-16, 킥③): emp_title 파생변수의 IV 기여도를 검증한다. 성공기준: 기여도 비교 결과 문서화(효과 유무 무관).
FR17 (CAP-17, 킥④): 스코어카드 로직을 SAS로 이식해 대조 검증한다. 성공기준: 10건 이상 SAS-Python 오차 <0.5점.

### NonFunctional Requirements

NFR1: 재현성 — 전 실험 시드 고정, 파이프라인 단계별 스크립트화, 노트북/스크립트 이원화.
NFR2: API 응답 p95 < 300ms.
NFR3: pytest로 라벨생성·비닝·점수변환·API 스키마 단위 테스트.
NFR4: MDD 축약판에 표본설계 근거·성능·reject inference 등 한계를 포함.
NFR5: 데이터·모델 아티팩트는 gitignore, 재생성 스크립트로 대체.
NFR6: 설정 파일 ASCII 우선(cp949 인코딩 이슈 회피).
NFR7: 손익·룰 진단 산출물은 항상 가정/근거(assumptions)를 함께 반환.
NFR8: 데이터·표본 고정 — Kaggle Lending Club accepted loans(2007~2018Q4), train/valid=2012~2014 빈티지, OOT=2015 빈티지, bad=`loan_status ∈ {Charged Off, Default}`, good=`Fully Paid`, 진행중 제외, 36개월물 우선. 표본 부족 시 60개월물 확장 가능하나 **만기 성숙 제약으로 2013 이전 빈티지 한정**(2015 빈티지 60개월물은 만기 2020 > 데이터 종료 2018Q4). 모든 스토리가 이 정의를 임의로 변경할 수 없다.

### Additional Requirements

- 스타터 템플릿 없음 — 아키텍처는 그린필드 커스텀 구조(Structural Seed)를 지정, 외부 스캐폴드 미사용.
- [AD-1] 파이프라인↔API 간 유일한 통로는 버저닝된 아티팩트 번들(joblib+manifest.json, 공통키+모델유형별 필수키 고정) — Epic 1 마지막 스토리에서 매니페스트 스키마를 확정해야 이후 서빙 에픽이 시작 가능.
- [AD-2] WOE 변환 로직은 `scorecard/binning.py` 단일 모듈, API가 재구현 금지 — train/serve parity.
- [AD-3] scored validation frame(컬럼 스키마 고정: applicant_id,vintage,model_type,score,pd,grade,bad_flag,int_rate,recoveries,total_pymnt)이 cutoff·swap-set·손익·룰진단·대시보드의 유일한 데이터 소스.
- [AD-4] `app/`은 read-only 서빙만 — 학습·재학습 금지.
- [AD-5] API 스키마는 `API_SPEC.md`가 구속 — 필드 변경은 그 문서 선(先)수정.
- [AD-6] reason_codes는 챔피언/챌린저 동일 구조(값 필드만 상이).
- [AD-7] `profit.py`/`rule_efficiency.py`의 verdict는 순수 규칙기반, LLM/외부API 호출 금지.
- [AD-8] 배포는 로컬 단일 환경(dev only)로 한정 — 컨테이너화·클라우드·CI는 범위 밖.
- [AD-9] `dashboard/`는 반드시 `app/`의 HTTP API 경유, 아티팩트 직접 접근 금지.
- 인증 없음(로컬 개발용, API_SPEC.md §0) — 보안 구현 요구사항 없음.
- **API 표면 인벤토리(API_SPEC.md v0.2, 총 8개)**: `GET /health`, `GET /v1/model/info`, `GET /v1/grades`, `POST /v1/score`, `POST /v1/score/batch`, `POST /v1/simulate/cutoff` (이상 6개=FR12 스토리), `POST /v1/simulate/profit-cutoff` (FR14 스토리에 귀속), `GET /v1/rules/efficiency` (FR15 스토리에 귀속). 킥 엔드포인트 2개도 AD-5(스키마 구속)의 적용 대상.
- **Epic 1 첫 스토리 = 그린필드 스캐폴딩**: 스타터 템플릿이 없으므로 첫 스토리가 .venv(Python 3.12) 셋업, requirements.txt 설치, kagglehub 데이터 다운로드, usecols+dtype 지정 로드 → 빈티지 필터 → parquet 변환(stack.md Phase 0)을 포함해야 한다.
- **최종 에픽 산출 문서**: `docs/MDD.md`(NFR4) + `README.md`(5분 내 전체 파악 가능) + GitHub 공개 + 옵시디언 미러(작업 원칙) — 문서화 스토리로 명시적으로 배정할 것.
- **스코프 가드(SPEC Non-goals)**: 실시간 CB 연동, pricing(한도·금리), 회수 모형, reject inference 코드 구현(문서화만), P3 자체 구현, A/B 테스트·프로덕션 배포·멀티테넌시는 어느 스토리에도 포함 금지.
- **스토리 설계에 반영할 가정·미결정 사항**: ① kagglehub 다운로드에 Kaggle 계정/키 필요 여부는 Epic 1 첫 스토리에서 확인하고, **실패 시 폴백(Kaggle CLI/수동 다운로드)을 스토리 AC에 명시**(SPEC assumption) ② 12개월 성과창 근사 채택 여부는 Epic 1 EDA 스토리의 AC에 "결정 기록"으로 포함(SPEC open question) ③ CAP-17(SAS)은 사용자 계정 확보 확인 전까지 착수 보류 — 다른 스토리를 블로킹하지 않는 독립 스토리로 배치.
- **에픽 공통 DoD(pre-mortem 반영)**: 각 에픽 종료 시 ⓐ 면접에서 바로 보여줄 수 있는 데모 산출물 1개(성능표/라이브 데모/1페이저) ⓑ git 커밋 ⓒ 옵시디언 미러가 완료되어야 에픽 done. 문서화·커밋을 마지막 에픽에 몰지 않는다.
- **스토리 설계 추가 지침(엘리시테이션 반영)**: ① E1 스토리 수 상한 7개 — optbinning 스파이크 검증을 E1 초반 스토리에 배치(최약 가정 A1 보강) ② FR15 룰셋은 실무 관행(DTI·연체이력·조회수 기반)에 근거해 설계했음을 AC에 명시 ③ 문서화 스토리의 README AC에 결과 이미지·핵심 수치 포함(비기술 독자 대응) ④ E2에서 P3(loan-agent-lab)용 예시 요청/응답 페어를 `docs/` 하위에 저장하는 AC 포함.

### UX Design Requirements

해당 없음 — 별도 UX 스펙 문서 없음. Streamlit 대시보드(FR13/CAP-13)의 UI 요구사항은 FR에 이미 포함되어 있고, 화면 4개(성능/등급분포/PSI/cutoff 시뮬레이션) 외 별도 디자인 토큰·컴포넌트 규격은 없음.

### FR Coverage Map

FR1: Epic 1 — 표본 설계(누수 감사·빈티지·라벨)
FR2: Epic 1 — 결측·이상치 전처리
FR3: Epic 1 — WOE 비닝·변수선정
FR4: Epic 1 — 로지스틱 스코어카드(챔피언)
FR5: Epic 1 — LightGBM 챌린저+calibration
FR6: Epic 1 — 3면 평가(AUC·KS·PR-AUC)
FR7: Epic 1 — 등급 매핑·단조성
FR8: Epic 1 — PSI 안정성 검증
FR9: Epic 2 — 리스크 기반 cutoff 시뮬레이션
FR10: Epic 2 — swap-set 분석
FR11: Epic 2 — reason code 이원화
FR12: Epic 2 — FastAPI 스코어링 API(기본 6개 엔드포인트)
FR13: Epic 2 — Streamlit 대시보드
FR14: Epic 2 — 손익 기반 cutoff(킥①, /v1/simulate/profit-cutoff 포함) ※엘리시테이션(pre-mortem)으로 E3→E2 이동
FR15: Epic 3 — 룰 효율성 진단(킥②, /v1/rules/efficiency 포함)
FR16: Epic 3 — 비금융 텍스트 파생변수(킥③)
FR17: Epic 3 — SAS 재현(킥④, 사용자 계정 확보 후 착수)

전 17개 FR 커버 확인. NFR1~8은 전 에픽 공통 적용, NFR4(MDD)·문서화 산출물은 Epic 3 마지막 스토리에 배정.

## Epic List

### Epic 1: 신용평가모형 개발 기반 (Model Development Foundation)
표본 설계부터 검증까지 — 스캐폴딩·데이터 확보 후, 누수 없는 표본 위에 WOE 스코어카드(챔피언)와 LightGBM(챌린저)을 개발하고 3면 평가·등급화·PSI까지 완료한다. 에픽 종료 시점에 아티팩트 번들(AD-1 manifest 스키마 확정)과 scored validation frame(AD-3 컬럼 스키마 고정)이 생성되어 이후 에픽의 기반이 된다. 이 에픽만으로도 "완성된 신용평가모형"을 성능표와 함께 시연 가능. 성능 수치(KS≥0.25, AUC≥0.70)는 통과 목표이며, 미달 시 원인 분석 문서가 대체 산출물이다 — 미달=에픽 실패가 아니다.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8

### Epic 2: 심사 전략 분석과 라이브 스코어링 (Underwriting Strategy & Live Scoring)
Epic 1의 frozen 아티팩트를 소비해 cutoff 트레이드오프·swap-set·reason code에 더해 **손익 기반 cutoff(킥①)까지** 산출하고 — 리스크와 손익 두 언어로 심사 전략을 말하는 에픽 — FastAPI(기본 6개+profit-cutoff 엔드포인트)와 Streamlit 대시보드로 서빙한다. 에픽 종료 시점에 "신청 1건 입력 → 점수·등급·사유 3개 반환" 라이브 데모와 손익 1페이저가 가능해진다(P3 loan-agent-lab이 소비할 인터페이스 완성 + P3용 예시 요청/응답 페어 저장).
**FRs covered:** FR9, FR10, FR11, FR12, FR13, FR14

### Epic 3: 컨설턴트 킥과 포트폴리오 완성 (Consultant Kicks & Portfolio Finish)
남은 킥 3종(룰 효율성 진단 리포트, 비금융 텍스트 검증, SAS 대조)을 얹고, MDD·README·GitHub 공개·옵시디언 미러로 포트폴리오를 마감한다. 룰 진단 API는 기존 서빙에 추가만 한다(AD-5 하위호환). FR17은 SAS 계정 확보 확인 전까지 보류 가능한 독립 스토리.
**FRs covered:** FR15, FR16, FR17

**의존 흐름:** Epic 1 → Epic 2 → Epic 3 (각 에픽은 이전 에픽 산출물만 소비, 미래 에픽 불요). 개발 순서 = 발표 임팩트 역순(면접에서는 최종 킥 산출물부터 보여주는 것을 권장). FR14를 E2로 당겨 차별화 산출물(손익 1페이저)이 E3 미착수 시에도 확보되도록 조정(pre-mortem 반영).

## Epic 1: 신용평가모형 개발 기반

누수 없는 표본 위에 챔피언·챌린저 모형을 개발하고 검증까지 완료해, 아티팩트 번들과 scored validation frame이라는 이후 전 에픽의 기반을 확정한다. (스토리 7개 — 상한 준수)

### Story 1.1: 프로젝트 스캐폴딩과 데이터 확보

As a 모형 개발자,
I want .venv 환경과 Lending Club 원본 데이터를 빈티지 필터된 parquet으로 준비하고,
So that 이후 모든 스토리가 재현 가능한 환경과 가벼운 데이터 위에서 시작할 수 있다.

**Acceptance Criteria:**

**Given** Python 3.12과 requirements.txt가 있는 빈 프로젝트
**When** .venv 생성·의존성 설치 후 kagglehub로 Lending Club accepted loans를 다운로드하면
**Then** usecols+dtype 지정 로드 → 2012~2015 빈티지·36개월물 필터 → `data/` 하위 parquet 저장이 완료된다
**And** kagglehub 실패 시 폴백(Kaggle CLI 또는 수동 다운로드) 절차가 README 스텁에 기록된다 (Kaggle 계정/키 필요 여부 확인 포함)
**And** parquet 재생성 스크립트(`pipelines/01_download.py`)가 존재한다 (NFR5)
**And** pytest가 구동되는 tests/ 골격과 시드 고정 유틸이 존재한다 (NFR1, NFR3)

### Story 1.2: 표본 설계 — 누수 감사·라벨·분할

As a 모형 개발자,
I want 신청시점 기준 누수 필드를 배제하고 빈티지 기반 train/valid/OOT를 분리하고,
So that 모형이 실제 심사 시점에 쓸 수 없는 정보로 학습되는 것을 원천 차단한다.

**Acceptance Criteria:**

**Given** 1.1의 parquet 데이터
**When** 전 컬럼을 신청시점/사후 이분 감사하면 (`scorecard/sample_design.py`)
**Then** 배제 필드 목록 문서(필드별 배제 근거 포함)가 산출된다 (FR1, 애매하면 배제 보수 원칙)
**And** bad=`Charged Off/Default`, good=`Fully Paid`, 진행중 제외 라벨이 생성되고 라벨 생성 로직에 pytest가 있다 (NFR8)
**And** train/valid=2012~2014, OOT=2015 분할과 3그룹 건수·부도율 테이블이 산출된다
**And** 12개월 성과창 근사(last_pymnt_d 기반) 채택 여부를 EDA 근거와 함께 결정 기록으로 남긴다 (SPEC open question 해소)

### Story 1.3: 결측·이상치 전처리

As a 모형 개발자,
I want 결측=별도 빈 원칙과 캡핑 규칙으로 데이터를 정제하고,
So that 비닝 단계가 안전한 입력을 받으면서 결측의 정보량도 보존된다.

**Acceptance Criteria:**

**Given** 1.2의 라벨·분할된 표본
**When** `scorecard/preprocessing.py`로 정제하면
**Then** 결측은 대치하지 않고 별도 빈 처리 대상으로 표시되고, 이상치 캡핑 규칙이 적용된다 (FR2)
**And** 정제 규칙 문서와 정제 전후 분포 비교 리포트가 산출된다
**And** 캡핑 로직에 pytest가 있다

### Story 1.4: WOE 비닝과 변수선정 (optbinning 스파이크 포함)

As a 모형 개발자,
I want 전 변수를 WOE/IV로 비닝하고 IV+상관/VIF로 최종 변수셋을 확정하고,
So that 판별력 있고 중복 없는 변수만 스코어카드에 들어간다.

**Acceptance Criteria:**

**Given** 1.3의 정제된 표본
**When** optbinning으로 전 후보 변수를 단조 제약 비닝하면 (`scorecard/binning.py` — AD-2 단일 소스)
**Then** 변수별 WOE/IV 테이블이 산출된다 (FR3)
**And** IV 필터 후 pairwise 상관 ≤0.7이 되도록 중복 변수가 제거되고 선정 근거가 문서화된다
**And** 스토리 착수 첫 작업으로 optbinning 스파이크 검증을 수행하고, 실패 시 수동 분위수 비닝 폴백으로 전환한 기록을 남긴다 (최약 가정 A1 보강)
**And** 비닝 변환에 pytest가 있다 (NFR3)

### Story 1.5: 로지스틱 스코어카드 (챔피언)

As a 모형 개발자,
I want 선정된 WOE 변수로 PDO=20, Base=600 스코어카드를 구축하고,
So that 설명 가능한 업계 표준 챔피언 모형을 확보한다.

**Acceptance Criteria:**

**Given** 1.4의 최종 변수셋
**When** `scorecard/champion.py`로 로지스틱 스코어카드를 학습하면
**Then** 신청 1건 입력 시 점수가 산출된다 (FR4)
**And** 전 변수 계수의 부호가 비즈니스 상식과 일치함을 검증한 표가 산출된다
**And** 점수 변환(WOE→선형결합→PDO 스케일링)에 pytest가 있다
**And** 챔피언 아티팩트(joblib)와 manifest 필수키(pdo, base_score, woe_bin_edges 포함)가 저장된다 (AD-1)

### Story 1.6: LightGBM 챌린저와 Calibration

As a 모형 개발자,
I want Optuna 튜닝 LightGBM에 calibration을 적용한 챌린저를 학습하고,
So that 챔피언과 성능·설명가능성 트레이드오프를 비교할 상대를 확보한다.

**Acceptance Criteria:**

**Given** 1.4의 최종 변수셋 (WOE 변환 전 원변수 사용 가능)
**When** `scorecard/challenger.py`로 Optuna 튜닝 후 isotonic/Platt calibration을 적용하면
**Then** calibration 전후 Brier score 개선이 확인되고 캘리브레이션 곡선이 산출된다 (FR5)
**And** 챌린저 아티팩트와 manifest 필수키(calibration_method, shap_background_sample_ref 포함)가 저장된다 (AD-1)
**And** 시드 고정으로 재실행 시 동일 결과가 재현된다 (NFR1)

### Story 1.7: 평가·등급·PSI와 아티팩트 계약 확정

As a 모형 개발자,
I want 두 모형을 3면 평가하고 등급 매핑·PSI까지 완료해 scored validation frame을 확정하고,
So that "검증 완료된 신용평가모형"을 성능표와 함께 시연할 수 있고 이후 에픽의 유일한 데이터 소스가 고정된다.

**Acceptance Criteria:**

**Given** 1.5·1.6의 두 아티팩트
**When** `scorecard/evaluation.py`·`grading.py`로 평가·등급화하면
**Then** train/valid/OOT 3면 AUC·KS·PR-AUC 비교표가 산출된다 (FR6 — OOT 챔피언 KS≥0.25·챌린저 AUC≥0.70이 통과 목표, 미달 시 원인 분석 문서가 대체 산출물)
**And** 1~10등급 매핑과 등급별 부도율 완전 단조 검증이 완료되고 grade_thresholds가 manifest에 기록된다 (FR7, AD-1)
**And** train 대비 OOT 변수·점수 PSI가 산출된다 (FR8 — 점수 PSI<0.1 목표)
**And** scored validation frame parquet이 AD-3 고정 스키마(applicant_id, vintage, model_type, score, pd, grade, bad_flag, int_rate, recoveries, total_pymnt)로 생성된다
**And** 에픽 DoD: 성능표 데모 산출물 + git 커밋 + 옵시디언 미러 완료

## Epic 2: 심사 전략 분석과 라이브 스코어링

frozen 아티팩트를 소비해 리스크·손익 두 언어의 심사 전략과 라이브 스코어링 데모를 완성한다. (스토리 5개)

### Story 2.1: Cutoff 시뮬레이션과 Swap-set 분석

As a 심사 전략 담당자,
I want cutoff별 승인율-부도율 곡선과 챔피언↔챌린저 swap-set을 보고,
So that 심사 기준 조정과 모형 교체의 영향을 정량적으로 판단할 수 있다.

**Acceptance Criteria:**

**Given** Epic 1의 scored validation frame (AD-3 스키마)
**When** `scorecard/strategy.py`로 분석하면
**Then** 전 구간 cutoff 트레이드오프 curve와 특정 cutoff의 승인율·부도율 즉시 조회가 가능하다 (FR9)
**And** swap-in/swap-out 건수와 각 집단의 부도율 비교표가 산출된다 (FR10)
**And** frame을 소비만 하고 예측을 재계산하지 않는다 (AD-3)

### Story 2.2: Reason Code 이원화

As a 심사역,
I want 개별 신청 건의 점수 하락 사유 top3를 완성된 문장으로 받고,
So that 거절·조건부 사유를 고객에게 설명할 수 있다.

**Acceptance Criteria:**

**Given** Epic 1의 두 아티팩트
**When** `scorecard/reasons.py`로 임의 신청 1건을 분석하면
**Then** 챔피언=특성별 점수손실, 챌린저=SHAP 기준 top3 사유가 산출된다 (FR11)
**And** 두 모형의 reason_codes가 동일 구조(값 필드만 points_lost/shap_value)를 공유한다 (AD-6)
**And** description은 심사의견서에 그대로 인용 가능한 완성된 한국어 문장이다 (P3 계약)
**And** WOE 재구현 없이 binning.py를 import해 쓴다 (AD-2)

### Story 2.3: FastAPI 스코어링 서빙

As a P3 에이전트(그리고 대시보드),
I want HTTP API로 점수·PD·등급·사유·cutoff 시뮬레이션을 조회하고,
So that 판정 로직 없이 스코어링 결과를 소비할 수 있다.

**Acceptance Criteria:**

**Given** Epic 1의 frozen 아티팩트와 validation frame
**When** `app/`을 uvicorn으로 구동하면
**Then** API_SPEC.md의 기본 6개 엔드포인트(/health, /v1/model/info, /v1/grades, /v1/score, /v1/score/batch, /v1/simulate/cutoff)가 스키마 그대로 동작한다 (FR12, AD-5)
**And** /v1/score p95<300ms (NFR2), 전 엔드포인트 pytest 통과 (NFR3)
**And** app/은 로드만 하고 학습·아티팩트 변경을 하지 않으며(AD-4), 비닝은 binning.py import로 처리한다(AD-2)
**And** 에러 응답 3종(422 스키마 위반, 400 VALUE_OUT_OF_RANGE, 503 MODEL_NOT_LOADED)이 API_SPEC §0 포맷(detail+error_code)으로 반환되고 pytest로 검증된다
**And** 요청별 model_version이 로그에 남는다 (컨벤션)
**And** P3용 예시 요청/응답 페어가 `docs/` 하위에 저장된다

### Story 2.4: 손익 기반 Cutoff (컨설턴트 킥①)

As a 경영진 보고를 준비하는 컨설턴트,
I want 리스크 지표가 아닌 실현손익 기준의 최적 cutoff과 1페이저를 얻고,
So that "cutoff 조정 시 연간 기대손익이 얼마 변하는가"로 심사 전략을 제안할 수 있다.

**Acceptance Criteria:**

**Given** validation frame의 int_rate·recoveries·total_pymnt 컬럼
**When** `scorecard/profit.py`로 건별 실현손익을 집계하면
**Then** 현재 대비 최적 cutoff의 승인율·연간 기대손익 delta가 산출된다 (FR14)
**And** `/v1/simulate/profit-cutoff` 엔드포인트가 API_SPEC.md §7 스키마로 동작하고 assumptions 필드가 항상 포함된다 (NFR7, AD-5)
**And** 판정 로직은 순수 규칙·통계 함수다 — LLM/외부 API 호출 없음 (AD-7)
**And** 경영진 보고용 1페이저(md)가 산출된다 — 에픽 DoD 데모 산출물

### Story 2.5: Streamlit 대시보드

As a 면접에서 시연하는 지원자,
I want 성능·등급분포·PSI·cutoff(리스크+손익)를 한 화면씩 탐색하고,
So that 모형 개발 전 과정을 5분 안에 시각적으로 보여줄 수 있다.

**Acceptance Criteria:**

**Given** 2.3·2.4의 구동 중인 API
**When** `dashboard/`를 streamlit으로 구동하면
**Then** 4개 화면(성능/등급분포/PSI/cutoff 시뮬레이션)이 라이브로 동작한다 (FR13)
**And** 모든 데이터는 app/의 HTTP API 경유로만 가져온다 — 아티팩트 직접 읽기 금지 (AD-9)
**And** 스크린샷이 확보된다
**And** 에픽 DoD: 라이브 데모 + git 커밋 + 옵시디언 미러 완료

## Epic 3: 컨설턴트 킥과 포트폴리오 완성

남은 킥 3종과 문서화로 "심사 전략을 컨설팅하는 지원자" 포지셔닝을 완성한다. (스토리 4개)

### Story 3.1: 룰 효율성 진단 (컨설턴트 킥②)

As a 룰 기반 의사결정 시스템을 고도화하는 컨설턴트,
I want 기존 하드룰들이 실제로 얼마나 효율적인지 데이터로 진단하고,
So that "유지/재검토" 근거를 가진 룰 정비 제안을 할 수 있다.

**Acceptance Criteria:**

**Given** validation frame과 실무 관행(DTI·연체이력·조회수)에 근거해 설계한 가상 하드룰셋 3개 이상
**When** `scorecard/rule_efficiency.py`로 룰별 배제집단을 분석하면
**Then** 룰별 배제 건수·배제집단 부도율·모집단 대비 비율·기회손실 추정이 산출된다 (FR15)
**And** verdict(유지/재검토 권장)가 규칙 기반으로 산출되고 근거가 명시된다 (AD-7, NFR7)
**And** `/v1/rules/efficiency` 엔드포인트가 API_SPEC.md §8 스키마로 동작한다 (AD-5 — 기존 서빙에 추가만)
**And** 룰 정비 제안 리포트(md)가 산출된다

### Story 3.2: 비금융 텍스트 파생변수 (컨설턴트 킥③)

As a 비금융 데이터 활용을 검증하는 분석가,
I want emp_title 텍스트에서 파생변수를 만들어 IV 기여도를 측정하고,
So that "비금융 데이터를 실제로 검증했다"는 결과를 효과 유무와 무관하게 제시할 수 있다.

**Acceptance Criteria:**

**Given** 원본 데이터의 emp_title 컬럼
**When** `scorecard/text_features.py`로 소문자화·특수문자 제거·상위 빈도 카테고리 매핑하면 (정교한 NLP 지양)
**Then** 파생변수의 WOE/IV가 산출되고 정형 변수 대비 기여도가 비교된다 (FR16)
**And** 효과가 없으면 없다고 기록한다 — 검증 자체가 산출물
**And** 결과 문서가 MDD에 편입될 형태로 산출된다

### Story 3.3: SAS 재현 (컨설턴트 킥④ — 계정 확보 후 착수)

As a SAS 레거시 환경의 채용사를 대비하는 지원자,
I want 스코어카드 점수산출 로직을 SAS로 이식해 Python과 대조하고,
So that "Python으로 개발, SAS로 이식 검증" 역량을 증빙할 수 있다.

**Acceptance Criteria:**

**Given** 사용자의 SAS OnDemand for Academics 계정 확보 확인 (미확보 시 이 스토리는 문서화로 축소)
**When** `sas/scorecard_scoring.sas`로 WOE 변환→선형결합→PDO 스케일링을 이식하면
**Then** 동일 입력 10건 이상에서 SAS-Python 점수 오차 <0.5점 (FR17)
**And** 대조 리포트가 산출된다
**And** 이 스토리는 다른 스토리를 블로킹하지 않는다

### Story 3.4: MDD·README·GitHub 공개

As a 포트폴리오를 제출하는 지원자,
I want 모형 개발 문서와 README를 완성해 GitHub에 공개하고,
So that 채용담당자가 5분 안에, 실무 면접관이 깊이 있게 프로젝트를 파악할 수 있다.

**Acceptance Criteria:**

**Given** Epic 1~3의 전 산출물
**When** `docs/MDD.md`와 README.md를 작성하면
**Then** MDD에 표본설계 근거·성능·한계(reject inference 실무 보정 방법 서술 포함)가 담긴다 (NFR4)
**And** README 첫 화면에 결과 이미지·핵심 수치가 있고 5분 내 전체 파악이 가능하다
**And** GitHub 공개(데이터·아티팩트는 gitignore, NFR5) + 옵시디언 미러가 완료된다
**And** 에픽 DoD: 1페이저·리포트 데모 산출물 + git 커밋 + 옵시디언 미러 완료
