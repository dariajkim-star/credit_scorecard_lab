---
id: SPEC-credit-scorecard-lab
companions:
  - stack.md
  - pipeline-diagram.md
  - ../../../API_SPEC.md
sources:
  - ../../../DEV_PLAN.md
  - C:\Users\user\Desktop\ob_storage\신용평가_CRM_사이드프로젝트\01_신용스코어카드_랩.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability only — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# credit-scorecard-lab — 신용 스코어카드 개발 랩

## Why

"AI 기반 분석 컨설턴트(신용평가·CRM·AI)" 채용공고는 신용평가모형 개발, 금융권 여신 도메인, XGBoost/LightGBM, SAS/Python/SQL, 심사 전략(룰 기반 의사결정 시스템 고도화) 경험을 우대사항·주요업무로 명시한다. 이 프로젝트는 그 공백을 메우는 포트폴리오로, Lending Club 공개 여신 데이터로 표본 설계부터 심사 전략까지 신용평가모형 개발 풀사이클을 구현하되, 리스크 지표(KS·PSI·AUC)에 그치지 않고 손익·룰 효율성 언어로 번역해 "모델을 잘 만드는 지원자"가 아니라 "심사 전략을 컨설팅하는 지원자"로 포지셔닝하는 것을 목표로 한다.

## Capabilities

- **CAP-1 표본 설계**
  - **intent:** 신청시점 기준으로 알 수 있던 정보만 사용하도록 누수 필드를 배제하고, 빈티지 기반으로 train/valid/OOT 표본을 분리한다.
  - **success:** 배제 필드 목록 문서가 존재하고, train/valid/OOT 각각의 건수·부도율 테이블이 산출된다.

- **CAP-2 결측·이상치 전처리**
  - **intent:** 결측은 WOE 별도 빈으로, 이상치는 캡핑 규칙으로 정제해 이후 비닝 단계에 안전한 입력을 제공한다.
  - **success:** 정제 규칙 문서와 정제 전후 분포 비교 리포트가 산출된다.

- **CAP-3 WOE 비닝 및 변수선정**
  - **intent:** 전 후보 변수를 WOE/IV로 비닝하고, IV 기준 1차 선별 후 상관/VIF로 다중공선성이 높은 변수를 제거해 최종 변수셋을 확정한다.
  - **success:** IV 테이블이 산출되고, 최종 변수셋의 pairwise 상관이 임계치(0.7) 이하다.

- **CAP-4 로지스틱 스코어카드 (챔피언)**
  - **intent:** 선정된 WOE 변수로 PDO=20, Base Score=600 기준의 스코어카드를 구축한다.
  - **success:** 신청 1건을 입력하면 점수가 산출되고, 전 변수 계수의 부호가 비즈니스 상식과 일치한다.

- **CAP-5 LightGBM 챌린저**
  - **intent:** Optuna로 튜닝한 LightGBM을 학습하고 isotonic/Platt calibration을 적용해 확률 해석이 가능한 챌린저 모델을 만든다.
  - **success:** calibration 전후 Brier score가 개선되고 캘리브레이션 곡선이 산출된다.

- **CAP-6 모형 평가**
  - **intent:** 챔피언·챌린저를 train/valid/OOT 3면에서 AUC·KS·PR-AUC로 비교한다.
  - **success:** 3면 비교표가 산출되고, OOT 기준 챔피언 KS≥0.25, 챌린저 AUC≥0.70을 만족한다.

- **CAP-7 등급 매핑**
  - **intent:** 점수를 1~10등급으로 매핑하고 등급별 부도율의 단조성을 검증한다.
  - **success:** 등급별 관측 부도율이 완전 단조 감소한다.

- **CAP-8 PSI 안정성 검증**
  - **intent:** train 빈티지 대비 OOT 빈티지의 변수·점수 분포 안정성을 PSI로 검증한다.
  - **success:** 점수 PSI < 0.1.

- **CAP-9 리스크 기반 Cutoff 시뮬레이션**
  - **intent:** cutoff 점수에 따른 승인율–부도율 트레이드오프를 산출해 심사 전략 논의의 근거를 제공한다.
  - **success:** 전 구간 트레이드오프 curve와 특정 cutoff의 승인율·부도율을 즉시 조회할 수 있다.

- **CAP-10 Swap-set 분석**
  - **intent:** 챔피언에서 챌린저로 모형을 교체할 때 판정이 뒤바뀌는 고객군을 정량화한다.
  - **success:** swap-in/swap-out 건수와 각 집단의 부도율 비교표가 산출된다.

- **CAP-11 Reason Code**
  - **intent:** 개별 신청 건의 점수 하락 사유 상위 3개를 모형 유형별(챔피언=점수손실, 챌린저=SHAP)로 제공한다.
  - **success:** 임의 신청 1건에 대해 완성된 한국어 설명 문장을 포함한 사유 3개가 반환된다.

- **CAP-12 스코어링 API**
  - **intent:** FastAPI로 점수·PD·등급·reason code·cutoff 시뮬레이션을 서빙하되, 판정(승인/거절)은 내리지 않는다.
  - **success:** API_SPEC.md의 전 엔드포인트가 pytest를 통과하고 `/v1/score` 응답 p95 < 300ms.

- **CAP-13 Streamlit 대시보드**
  - **intent:** 모형 성능·등급 분포·PSI·cutoff 시뮬레이션을 한 화면에서 시각적으로 탐색할 수 있게 한다.
  - **success:** 4개 화면이 라이브로 구동되고 스크린샷이 확보된다.

- **CAP-14 손익 기반 Cutoff (컨설턴트 킥①)**
  - **intent:** 이자수익(int_rate)과 회수·손실(recoveries/total_pymnt)로 건별 실현손익을 계산해, 리스크 지표가 아닌 손익 기준으로 최적 cutoff을 제시한다.
  - **success:** 현재 cutoff 대비 최적 cutoff의 승인율·연간 기대손익 delta가 명시적 가정(assumptions)과 함께 산출된다.

- **CAP-15 룰 효율성 진단 (컨설턴트 킥②)**
  - **intent:** 가상 하드룰셋을 검증 표본에 적용해 룰별 배제집단의 실제 부도율·기회손실을 측정하고 유지/재검토 여부를 규칙 기반으로 판정한다.
  - **success:** 룰 3개 이상에 대해 근거가 명시된 verdict를 포함한 리포트가 산출된다.

- **CAP-16 비금융 텍스트 파생변수 (컨설턴트 킥③)**
  - **intent:** emp_title 텍스트를 정제·카테고리화해 파생변수를 만들고 정형 변수 대비 IV 기여도를 검증한다.
  - **success:** 파생변수의 IV 값과 기여도 비교 결과가 효과 유무와 무관하게 문서화된다.

- **CAP-17 SAS 재현 (컨설턴트 킥④)**
  - **intent:** 스코어카드 점수산출 로직(WOE 변환→선형결합→PDO 스케일링)을 SAS로 이식해 Python 산출값과 대조 검증한다.
  - **success:** 동일 입력 10건 이상에서 SAS-Python 점수 오차가 0.5점 미만이다.

## Constraints

- 데이터는 Kaggle Lending Club accepted loans(2007~2018Q4)로 고정. train/valid=2012–2014 빈티지, OOT=2015 빈티지로 시점 분리. 부도 정의는 `loan_status ∈ {Charged Off, Default}`=bad, `Fully Paid`=good.
- 결측치는 WOE 별도 빈으로 처리하고 대치(imputation)는 최소화한다 — WOE 비닝 표준 관행을 우선한다.
- 스코어링 API는 승인/거절을 판정하지 않는다 — 점수·PD·등급·reason_codes만 반환하고 cutoff 적용은 소비자(대시보드, 추후 P3 loan-agent-lab 에이전트) 책임이다.
- 손익 시뮬레이션(CAP-14)과 룰 효율성 진단(CAP-15)의 verdict는 규칙 기반으로 산출한다(LLM 생성 아님) — 결정적 판정 원칙을 유지한다.
- 손익·룰 진단 산출물은 항상 근거·가정(assumptions)을 함께 반환해 과장된 확신으로 보이지 않게 한다.
- API 응답 p95 < 300ms.
- 전 실험은 시드를 고정하고 파이프라인을 단계별 스크립트로 재현 가능하게 만든다. 데이터·모델 아티팩트는 gitignore하고 재생성 스크립트로 대체한다.
- 설정 파일은 ASCII 우선(cp949 인코딩 이슈 회피 — 선행 프로젝트 교훈).

## Non-goals

- 실시간 신용정보(CB) 조회 연동
- 한도·금리 산정(pricing)
- 연체 회수 모형
- reject inference의 실제 코드 구현 (한계 문서화로 대체)
- P3(loan-agent-lab) 자체 구현 — API 계약만 동결해 인터페이스로 제공
- 실제 A/B 테스트, 프로덕션 배포, 멀티테넌시

## Success signal

OOT 기준 챔피언 KS≥0.25·챌린저 AUC≥0.70을 달성하고, 등급별 부도율이 완전 단조이며 점수 PSI<0.1이다. 신청 1건을 API에 입력하면 점수·등급·사유 3개가 p95<300ms로 반환되는 라이브 데모가 가능하고, 손익 기반 cutoff 1페이저와 룰 효율성 리포트가 각 1건 이상 산출되며, SAS-Python 점수 오차가 0.5점 미만이다.

## Assumptions

- kagglehub로 Lending Club 데이터셋을 다운로드할 수 있다고 가정한다.
- 36개월물만으로 표본 규모가 충분하다고 가정하며, 부족할 경우 60개월물로 확장한다.

## Open Questions

- 12개월 성과창 근사(last_pymnt_d 기반)를 주 정의로 채택할지는 Phase 1 EDA 후 데이터 분포를 보고 결정해야 한다.
- SAS OnDemand for Academics 계정 확보 가능 여부가 미확인이다 — 불가할 경우 CAP-17은 스코어카드 로직 문서화로 축소한다.
