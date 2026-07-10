# stack.md — 기술 스택 · 디렉토리 · 워크플로우 규약

## 기술 스택

Python 3.12 · pandas · optbinning(WOE/IV·스코어카드) · scikit-learn · LightGBM · Optuna · SHAP · FastAPI · Streamlit · pytest · kagglehub(데이터 확보) · SAS OnDemand for Academics(킥4, 외부 도구)

## 디렉토리 구조

```
credit_scorecard-lab/
├── app/                    # FastAPI 서빙
│   ├── main.py
│   ├── schemas.py          # pydantic 요청/응답 (IV 선정 후 확정)
│   └── loader.py           # 모델 아티팩트 로드
├── scorecard/               # 모델링 라이브러리
│   ├── sample_design.py    # 빈티지·라벨·분할 (CAP-1)
│   ├── preprocessing.py    # 결측·이상치 (CAP-2)
│   ├── binning.py          # WOE/IV (CAP-3)
│   ├── champion.py         # 스코어카드 (CAP-4)
│   ├── challenger.py       # LightGBM+calibration (CAP-5)
│   ├── evaluation.py       # AUC·KS·PR-AUC·PSI (CAP-6, CAP-8)
│   ├── grading.py          # 등급 매핑·단조성 (CAP-7)
│   ├── strategy.py         # cutoff·swap-set (CAP-9, CAP-10)
│   ├── reasons.py          # reason code 이원화 (CAP-11)
│   ├── profit.py           # 손익 기반 cutoff (CAP-14)
│   ├── rule_efficiency.py  # 룰 효율성 진단 (CAP-15)
│   └── text_features.py    # emp_title 파생변수 (CAP-16)
├── pipelines/              # 단계별 실행 스크립트
├── notebooks/              # EDA·리포트용 (스크립트와 이원화)
├── dashboard/              # Streamlit (CAP-13)
├── sas/                    # SAS 재현 스크립트 (CAP-17)
├── models/artifacts/       # 학습 산출물 (gitignore, 재생성 스크립트로 대체)
├── data/                   # (gitignore)
├── tests/
└── docs/MDD.md              # 모형 개발 문서
```

## 진행 방식 (BMAD)

1. `bmad-spec` → 본 SPEC (완료)
2. `bmad-architecture` → 아키텍처 스파인 (다음 단계)
3. `bmad-create-epics-and-stories` → 에픽·스토리
4. 준비도 점검 → 스프린트 → 스토리 사이클(CS→DS→CR), 각 단계 fresh context
5. 스토리 dev 완료 시 `review-bundle-{story}.md` 생성 → GPT 교차검증 → triage(patch/defer/dismiss) → 재검증 (밸류업 프로젝트에서 확립한 패턴)
6. 산출 문서는 옵시디언 `Desktop\ob_storage\신용평가_CRM_사이드프로젝트\`에 미러

환경: `.venv`(Python 3.12), 테스트 `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -q`. 설정 파일은 ASCII 우선(cp949 이슈 회피).

## 일정 (2.5주, 파트타임 — 참고용, 스프린트 계획 시 재확정)

| Phase | 작업 | 대응 CAP |
|---|---|---|
| 0. 셋업 | .venv, kagglehub 다운로드, parquet 변환 | — |
| 1. 표본 설계·EDA | 누수 필드 감사, 빈티지·라벨·분할 | CAP-1 |
| 2. 비닝·챔피언 | 결측·이상치, WOE/IV, 상관제거, 스코어카드 | CAP-2,3,4 |
| 3. 챌린저·검증 | LightGBM+Optuna, 3면 비교, calibration, 등급+단조성, PSI | CAP-5,6,7,8 |
| 4. 전략·API | cutoff, swap-set, reason code, FastAPI | CAP-9,10,11,12 |
| 5. 컨설턴트 킥①② | 손익 cutoff, 룰 효율성 진단 | CAP-14,15 |
| 6. 킥③④·대시보드·문서 | 텍스트 파생변수, SAS 재현, Streamlit, MDD | CAP-16,17,13 |

## 리스크·대응

| 리스크 | 대응 | 관련 CAP |
|---|---|---|
| 원본 CSV 1.6GB+ 메모리 부담 | 최초 1회 usecols+dtype 지정 로드 → 빈티지 필터 후 parquet 저장, 이후 parquet만 사용 | CAP-1 |
| 누수 필드가 100+ 컬럼에 산재 | 전 컬럼을 "신청시점/사후" 이분 감사 — 애매하면 배제(보수 원칙) | CAP-1 |
| optbinning 학습 곡선 | 초기 스파이크 검증, 실패 시 수동 분위수 비닝 폴백 | CAP-3 |
| 성과기간 정의 논쟁 여지 | "만기 기준 최종 상태"를 주 정의로 고정, 12개월 창은 부록 실험 — 선택 근거를 MDD에 기록 | CAP-1 |
| Lending Club은 승인된 대출만 포함(reject inference 불가) | 한계 단락으로 정면 돌파, rejected loans 파일 존재 사실도 언급 | CAP-1, 비목표 |
| 손익 시뮬레이션이 과장된 확신으로 보일 위험 | API·1페이저에 assumptions 필드로 가정 항상 명시 | CAP-14 |
| SAS OnDemand 계정·환경 이슈로 일정 지연 | 최저 우선순위 — 시간 부족 시 스코어카드 로직만 최소 이식 또는 문서화로 축소, 본 파이프라인엔 영향 없음 | CAP-17 |
| emp_title 텍스트 노이즈(자유 입력) | 소문자화·특수문자 제거·상위 빈도 카테고리 매핑 정도로 범위 최소화 | CAP-16 |
