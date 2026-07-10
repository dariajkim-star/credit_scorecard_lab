# credit-scorecard-lab — 개발계획서 v1.2

> Lending Club 데이터 기반 신용 스코어카드 개발 풀사이클 + 컨설턴트 킥 4종(손익 cutoff·룰 효율성·비금융 텍스트·SAS 재현). 기획·SRS는 옵시디언 `신용평가_CRM_사이드프로젝트/01_신용스코어카드_랩.md`, API 계약은 `API_SPEC.md`.

## 1. 확정 사항

- **데이터**: Kaggle Lending Club accepted loans (2007~2018Q4, ~226만 건). `kagglehub`로 다운로드, `data/`는 gitignore
- **표본 설계**: 만기 도래 빈티지만 사용. train/valid = 2012~2014 빈티지, **OOT = 2015 빈티지** (시점 분리). 부도 정의 = `loan_status ∈ {Charged Off, Default}` = bad, `Fully Paid` = good, 진행중(Current 등) 제외. 36개월물 우선(만기 성숙도 확보), 60개월물은 확장 옵션
- **성과기간 주의**: 월별 연체 이력이 없어 성과 정의는 "만기 기준 최종 상태". 12개월 창(window) 근사는 `last_pymnt_d` 기반 실험으로 부록 처리 — 한계를 숨기지 않고 MDD에 명시
- **모형**: 챔피언 = WOE 로지스틱 스코어카드(PDO=20, Base=600), 챌린저 = LightGBM(+isotonic calibration)
- **파이프라인 14단계** (01 노트 v1.1과 동일): 기준시점 → 관찰·성과기간 → 결측·이상치 → WOE → IV+상관제거 → 스코어카드 → 챌린저 → AUC·KS·PR-AUC → Calibration → 등급 매핑+단조성 → PSI → Cutoff → Swap-set → Reason Code
- **컨설턴트 킥 4종** (01 노트 v1.2, FR-17~20): ① 손익 기반 cutoff(`int_rate`·`recoveries` 실현손익) ② 룰 효율성 진단(가상 하드룰셋 배제집단 분석) ③ 비금융 텍스트 파생변수(`emp_title`) ④ SAS 재현(점수산출 로직 이식·대조)

## 2. 디렉토리 구조 (예정)

```
CRM_sideproject/            # 코드 위치: Desktop\CRM_sideproject
├── app/                    # FastAPI 서빙 (API_SPEC.md 구현)
│   ├── main.py
│   ├── schemas.py          # pydantic 요청/응답 (IV 선정 후 확정)
│   └── loader.py           # 모델 아티팩트 로드
├── scorecard/              # 모델링 라이브러리 (파이프라인 로직)
│   ├── sample_design.py    # 빈티지·라벨·분할 (FR-1,2)
│   ├── preprocessing.py    # 결측·이상치 (FR-3)
│   ├── binning.py          # WOE/IV (FR-4,5)
│   ├── champion.py         # 스코어카드 (FR-6)
│   ├── challenger.py       # LightGBM+calibration (FR-7,9)
│   ├── evaluation.py       # AUC·KS·PR-AUC·PSI (FR-8,11)
│   ├── grading.py          # 등급 매핑·단조성 (FR-10)
│   ├── strategy.py         # cutoff·swap-set (FR-12,13)
│   ├── reasons.py          # reason code 이원화 (FR-14)
│   ├── profit.py           # 손익 기반 cutoff (FR-17, 킥①)
│   ├── rule_efficiency.py  # 룰 효율성 진단 (FR-18, 킥②)
│   └── text_features.py    # emp_title 파생변수 (FR-19, 킥③)
├── pipelines/              # 단계별 실행 스크립트 (01_download.py ~ )
├── notebooks/              # EDA·리포트용 (스크립트와 이원화)
├── dashboard/              # Streamlit
├── sas/                    # SAS 재현 스크립트 (FR-20, 킥④) — scorecard_scoring.sas + 대조 리포트
├── models/artifacts/       # 학습 산출물 (gitignore, 재생성 스크립트로 대체)
├── data/                   # (gitignore)
├── tests/
├── requirements.txt / API_SPEC.md / DEV_PLAN.md
└── docs/MDD.md             # 모형 개발 문서 (Phase 6)
```

## 3. 진행 방식 — BMAD

밸류업 프로젝트에서 확립한 패턴 그대로:

1. **bmad-spec** → SPEC 커널 (CAP 단위, 파이프라인 14단계 + 서빙)
2. **bmad-architecture** → 아키텍처 스파인 (AD: 아티팩트 계약 = 파이프라인 산출물과 API 로더의 결합점이 핵심 결정)
3. **bmad-create-epics-and-stories** → 에픽·스토리 (아래 Phase가 에픽 초안)
4. 준비도 점검 → 스프린트 → 스토리 사이클(CS→DS→CR), 각 단계 fresh context
5. **GPT 교차검증**: 스토리 dev 완료 시 `review-bundle-{story}.md` 생성 → GPT 리뷰 → triage(patch/defer/dismiss) → 재검증
6. 산출 문서는 옵시디언 `신용평가_CRM_사이드프로젝트/`에 미러

환경: `.venv` (Python 3.12), 테스트 `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -q`. 설정 파일은 ASCII 우선(cp949 이슈 — 밸류업 alembic 교훈).

## 4. 일정 (2.5주, 파트타임)

| Phase | 기간 | 작업 (FR) | DoD |
|---|---|---|---|
| **0. 셋업** | 0.5일 | .venv, kagglehub 다운로드, 원본 → parquet 변환 | 데이터 로드 노트북 1회전 |
| **1. 표본 설계·EDA** | 1~3일차 | 누수 필드 감사(FR-1), 빈티지·라벨·분할(FR-2), EDA | 배제 필드 목록 문서, train/valid/OOT 건수·부도율 테이블 |
| **2. 비닝·챔피언** | 4~6일차 | 결측·이상치(FR-3), WOE/IV(FR-4), 상관 제거(FR-5), 스코어카드(FR-6) | 비닝 리포트(IV 테이블), 스코어카드 점수표 |
| **3. 챌린저·검증** | 7~9일차 | LightGBM+Optuna(FR-7), 3면 비교(FR-8), calibration(FR-9), 등급+단조성(FR-10), PSI(FR-11) | 챔피언–챌린저 비교표, 등급별 부도율 단조 테이블, PSI 리포트 |
| **4. 전략·API** | 10~12일차 | cutoff(FR-12), swap-set(FR-13), reason code(FR-14), FastAPI(FR-15) | `/v1/score` 라이브 검증, 전략 문서 |
| **5. 컨설턴트 킥①②** | 13~15일차 | 손익 기반 cutoff(FR-17), 룰 효율성 진단(FR-18) | 손익 1페이저, 룰 정비 제안 리포트, `/v1/simulate/profit-cutoff`·`/v1/rules/efficiency` 라이브 검증 |
| **6. 킥③④·대시보드·문서** | 16~18일차 | 텍스트 파생변수(FR-19), SAS 재현(FR-20), Streamlit(FR-16), MDD, README, GPT 교차검증 총정리 | IV 기여도 리포트, SAS-Python 대조표, 대시보드 스크린샷, GitHub 공개 |

Phase 1이 이 프로젝트의 승부처(표본 설계 증거물), **Phase 5가 차별화 승부처**(리스크 지표를 손익·룰 언어로 번역한 증거물).

## 5. 리스크·대응

| 리스크 | 대응 |
|---|---|
| 원본 CSV 1.6GB+ 메모리 부담 | 최초 1회 usecols+dtype 지정 로드 → 빈티지 필터 후 parquet 저장, 이후 parquet만 사용 |
| 누수 필드가 100+ 컬럼에 산재 | Phase 1에서 전 컬럼을 "신청시점/사후" 이분 감사 — 애매하면 배제(보수 원칙) |
| optbinning 학습 곡선 | Phase 2 첫날 스파이크 검증, 실패 시 수동 분위수 비닝 폴백 |
| 성과기간 정의 논쟁 여지 | "만기 기준 최종 상태"를 주 정의로 고정, 12M 창은 부록 실험 — MDD에 선택 근거 기록 |
| Lending Club은 승인된 대출만 포함 | reject inference 한계 단락으로 정면 돌파 (rejected loans 파일 존재 사실도 언급) |
| 손익 시뮬레이션이 과장된 확신으로 보일 위험 | API·1페이저에 `assumptions` 필드로 가정 항상 명시 (실제 재무데이터 아님을 못박기) |
| SAS OnDemand 계정·환경 이슈로 일정 지연 | 킥④는 P2 우선순위 — 시간 부족 시 스코어카드 로직만 최소 이식, 실패해도 본 파이프라인엔 영향 없음 |
| emp_title 텍스트 노이즈(자유 입력) | 소문자화·특수문자 제거·상위 빈도 카테고리 매핑 정도로 범위 최소화, 정교한 NLP 지양 |

## 6. 성공 기준

- OOT 기준: 스코어카드 KS ≥ 0.25, 챌린저 AUC ≥ 0.70
- 등급별 부도율 완전 단조 + 점수 PSI(train vs OOT) < 0.1
- `/v1/score` 단건 응답 p95 < 300ms, pytest 전건 통과
- 신청 1건 → 점수·등급·사유 3개 반환 라이브 데모 + MDD·README로 5분 내 전체 파악 가능
- 손익 기반 cutoff 1페이저(FR-17) + 룰 효율성 리포트(FR-18) 각 1건 산출
- SAS 이식 점수 vs Python 점수 오차 < 0.5점(FR-20)

## 7. 다음 액션

1. `bmad-spec`으로 SPEC 커널 생성 (이 문서 + 01 노트가 입력)
2. `.venv` 셋업 + Phase 0
3. P3(loan-agent-lab)와의 API 계약은 `API_SPEC.md` §7 기준으로 동결
