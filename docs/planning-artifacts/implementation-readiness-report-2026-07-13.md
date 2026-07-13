---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments:
  - docs/specs/spec-credit-scorecard-lab/SPEC.md
  - docs/specs/spec-credit-scorecard-lab/stack.md
  - docs/specs/spec-credit-scorecard-lab/pipeline-diagram.md
  - API_SPEC.md
  - docs/planning-artifacts/architecture/architecture-credit-scorecard-lab-2026-07-10/ARCHITECTURE-SPINE.md
  - docs/planning-artifacts/epics.md
---

# Implementation Readiness Assessment Report

**Date:** 2026-07-13
**Project:** credit-scorecard-lab

## 1. 문서 인벤토리

| 문서 유형 | 파일 | 상태 |
|---|---|---|
| PRD | 없음 — **SPEC-first 경로**: `docs/specs/spec-credit-scorecard-lab/SPEC.md`(CAP-1~17)가 PRD 대체 | 단일본 ✅ |
| SPEC companions | stack.md, pipeline-diagram.md, API_SPEC.md(루트), ARCHITECTURE-SPINE.md(편입) | ✅ |
| Architecture | `docs/planning-artifacts/architecture/architecture-credit-scorecard-lab-2026-07-10/ARCHITECTURE-SPINE.md` (AD-1~9, status: final) | 단일본 ✅ |
| Epics & Stories | `docs/planning-artifacts/epics.md` (3에픽/16스토리, stepsCompleted [1,2,3,4]) | 단일본 ✅ |
| UX Design | 없음 — 의도적 부재(대시보드 요구는 FR13에 포함, epics.md에 명기) | 해당없음 |

- 중복(whole/sharded 병존) 없음.
- PRD·UX 부재는 SPEC-first 설계 결정으로 이슈 아님 — 이후 단계에서 SPEC.md를 요구사항 원천으로 사용.

## 2. PRD(=SPEC) 분석

### Functional Requirements (SPEC CAP-1~17 → FR1~17)

FR1 (CAP-1): 표본 설계 — 누수 필드 배제 + 빈티지 train/valid/OOT 분리. 성공: 배제 목록 문서 + 3그룹 건수·부도율 테이블.
FR2 (CAP-2): 결측=WOE 별도 빈·이상치 캡핑 전처리. 성공: 규칙 문서 + 전후 분포 리포트.
FR3 (CAP-3): WOE/IV 비닝 + IV·상관/VIF 변수선정. 성공: IV 테이블 + pairwise 상관 ≤0.7.
FR4 (CAP-4): PDO=20/Base=600 로지스틱 스코어카드. 성공: 1건 점수 산출 + 계수 부호 상식 일치.
FR5 (CAP-5): LightGBM+Optuna+calibration 챌린저. 성공: Brier 개선 + 캘리브레이션 곡선.
FR6 (CAP-6): 3면(train/valid/OOT) AUC·KS·PR-AUC 비교. 성공: 비교표 + OOT KS≥0.25/AUC≥0.70.
FR7 (CAP-7): 1~10등급 매핑. 성공: 등급별 부도율 완전 단조.
FR8 (CAP-8): PSI 안정성 검증. 성공: 점수 PSI<0.1.
FR9 (CAP-9): cutoff 승인율-부도율 곡선. 성공: 전 구간 curve + 즉시 조회.
FR10 (CAP-10): swap-set 정량화. 성공: swap-in/out 건수 + 부도율 비교표.
FR11 (CAP-11): reason code 이원화(점수손실/SHAP). 성공: 한국어 완성 문장 3개.
FR12 (CAP-12): FastAPI 서빙(판정 없음). 성공: 전 엔드포인트 pytest 통과 + p95<300ms.
FR13 (CAP-13): Streamlit 4화면. 성공: 라이브 구동 + 스크린샷.
FR14 (CAP-14): 손익 기반 cutoff(킥①). 성공: delta + assumptions 산출.
FR15 (CAP-15): 룰 효율성 진단(킥②). 성공: 룰 3개+ verdict 리포트.
FR16 (CAP-16): 비금융 텍스트 파생변수(킥③). 성공: IV 기여도 문서화.
FR17 (CAP-17): SAS 재현(킥④). 성공: 10건+ 오차<0.5점.
**Total FRs: 17**

### Non-Functional Requirements (SPEC Constraints → NFR1~8)

NFR1: 재현성(시드 고정·단계별 스크립트·이원화). NFR2: API p95<300ms. NFR3: pytest 단위테스트(라벨·비닝·점수변환·API 스키마 — CAP-12 success 및 stack.md에서 도출). NFR4: MDD 축약판(표본설계·성능·한계 포함 — SPEC Why·stack.md에서 도출). NFR5: 데이터·아티팩트 gitignore+재생성 스크립트. NFR6: 설정 ASCII 우선. NFR7: 손익·룰 진단 assumptions 항상 명시. NFR8: 데이터·표본 고정(Lending Club·빈티지·부도정의·36개월물, 60개월 확장은 2013 이전 빈티지 한정).
**Total NFRs: 8**

### Additional Requirements

- SPEC Non-goals 6건(CB 연동·pricing·회수모형·reject inference 구현·P3 구현·A/B·배포·멀티테넌시) — 스코프 가드.
- SPEC Assumptions 2건(kagglehub 가용, 36개월물 표본 충분) / Open Questions 2건(12M 성과창→1.2 AC로 해소 예정, SAS 계정→사용자 확인 대기, 3.3 AC에 반영됨).
- 아키텍처 AD-1~9 전건이 epics.md Additional Requirements에 전사됨.

### PRD 완전성 평가

SPEC은 전 CAP에 intent+success 쌍을 갖추고 있어 추적성 검증에 충분. PRD 고유 요소 중 부재한 것은 사용자 여정(User Journey)·성공지표(비즈니스 KPI)·페르소나 — 1인 포트폴리오 프로젝트 특성상 낮은 리스크이나, 면접 스토리텔링용으로 추후 bmad-prd 보완 여지 있음(차단 사유 아님).

## 3. Epic Coverage Validation

### Coverage Matrix (SPEC FR ↔ epics.md 스토리 대조)

| FR | Epic 커버리지 | 스토리 AC 확인 | Status |
|---|---|---|---|
| FR1 | Epic 1 / Story 1.2 | 배제 목록·3그룹 테이블·12M 결정기록 AC 존재 | ✓ |
| FR2 | Epic 1 / Story 1.3 | 별도 빈·캡핑·전후 리포트 AC 존재 | ✓ |
| FR3 | Epic 1 / Story 1.4 | IV 테이블·상관≤0.7·스파이크 AC 존재 | ✓ |
| FR4 | Epic 1 / Story 1.5 | 점수 산출·부호 검증·manifest 키 AC 존재 | ✓ |
| FR5 | Epic 1 / Story 1.6 | Brier·곡선·manifest 키 AC 존재 | ✓ |
| FR6 | Epic 1 / Story 1.7 | 3면 비교표+통과목표 재프레임 AC 존재 | ✓ |
| FR7 | Epic 1 / Story 1.7 | 단조 검증+grade_thresholds AC 존재 | ✓ |
| FR8 | Epic 1 / Story 1.7 | PSI<0.1 목표 AC 존재 | ✓ |
| FR9 | Epic 2 / Story 2.1 | curve+즉시 조회 AC 존재 | ✓ |
| FR10 | Epic 2 / Story 2.1 | swap 비교표 AC 존재 | ✓ |
| FR11 | Epic 2 / Story 2.2 | 이원화+완성 문장+AD-6 AC 존재 | ✓ |
| FR12 | Epic 2 / Story 2.3 | 6개 엔드포인트+p95+pytest AC 존재 | ✓ |
| FR13 | Epic 2 / Story 2.5 | 4화면+AD-9 AC 존재 | ✓ |
| FR14 | Epic 2 / Story 2.4 | delta+assumptions+1페이저 AC 존재 | ✓ |
| FR15 | Epic 3 / Story 3.1 | 룰 3개+·verdict·엔드포인트 AC 존재 | ✓ |
| FR16 | Epic 3 / Story 3.2 | IV 기여도·효과무관 기록 AC 존재 | ✓ |
| FR17 | Epic 3 / Story 3.3 | 오차<0.5·계정 전제조건 AC 존재 | ✓ |

### Missing Requirements

없음. 역방향 점검(에픽에는 있으나 SPEC에 없는 FR)도 없음 — Story 1.1(스캐폴딩)과 3.4(문서화)는 FR 비귀속이지만 각각 Additional Requirements(그린필드 스캐폴딩·최종 문서화 산출물)에 근거를 둠.

### Coverage Statistics

- Total SPEC FRs: 17 / 에픽 커버: 17 / **커버리지 100%**

## 4. UX Alignment Assessment

### UX Document Status

Not Found — 의도적 부재.

### 평가

UI가 존재하는 프로젝트(Streamlit 대시보드, FR13)이므로 UX 함의는 있음. 다만:
- 대시보드는 내부 분석·데모 도구(4화면 고정)이지 고객 대상 제품 UI가 아님 — 디자인 토큰·컴포넌트 체계·접근성 요구 수준이 낮음.
- 화면 구성(성능/등급분포/PSI/cutoff)이 Story 2.5 AC에 명세되어 있고, AD-9(API 경유)가 데이터 흐름을 고정.
- 2026-07-13 사용자 요청으로 UX/UI 레퍼런스 조사 완료(Streamlit 크레딧 리스크 대시보드 4종, Evidently 드리프트 리포트 문법, Dribbble/Behance 핀테크 톤) — Story 2.5 착수 시 참고 자료로 활용 가능.

### Warnings

⚠️ (낮음) 별도 UX 스펙 없이 Story 2.5의 AC만으로 대시보드를 구현하면 시각 품질이 dev 에이전트 재량에 좌우됨. 완화: 조사된 레퍼런스를 2.5 dev 컨텍스트에 첨부하거나, 착수 전 bmad-ux로 경량 화면 노트 작성(선택 사항, 차단 아님).

## 5. Epic Quality Review

### 에픽 구조 검증

- **사용자 가치**: E1은 "기술 마일스톤" 경계선상이나, 에픽 단독으로 "검증된 신용평가모형 + 성능표"라는 시연 가능한 가치를 산출하고 goal에 명시되어 있어 합격. E2(라이브 데모+손익 1페이저)·E3(리포트+공개 포트폴리오)는 명확한 가치 단위.
- **에픽 독립성**: E1 단독 완결 ✓ / E2는 E1 산출물만 소비 ✓ / E3는 E1·E2 산출물만 소비 ✓. 역방향·순환 의존 없음.

### 스토리 품질 검증 (16개 전수)

- **전방 의존 없음**: 2.4→2.3(이전 ✓), 2.5→2.3·2.4(이전 ✓), 3.1→E2 산출물(이전 에픽 ✓). 미래 스토리 참조 위반 0건.
- **스캐폴딩 배치**: 스타터 템플릿 미지정(그린필드) → 1.1 셋업 스토리 존재 ✓. CI/CD 부재는 AD-8의 명시적 스코프 제외로 정당화됨(위반 아님).
- **엔티티 생성 시점**: DB 없음. parquet·라벨·frame이 각각 최초 필요 스토리(1.1/1.2/1.7)에서 생성 ✓.
- **AC 형식**: 전 스토리 Given/When/Then + FR·AD 참조 ✓.

### 발견 사항

**🔴 Critical: 0건 / 🟠 Major: 0건 / 🟡 Minor: 3건**

1. 🟡 **Story 2.3 에러 경로 AC 부재** — API_SPEC §0의 에러 계약(422/400 VALUE_OUT_OF_RANGE/503 MODEL_NOT_LOADED, error_code 포맷)이 AC에 명시되지 않음. "전 엔드포인트 pytest 통과"가 암묵 포함한다고 볼 수 있으나, dev 에이전트가 happy path만 테스트할 위험. **권고**: 2.3 AC에 "에러 응답 3종이 API_SPEC §0 포맷으로 반환되고 pytest로 검증된다" 1줄 추가.
2. 🟡 **Story 1.7 사이즈 큼** — FR 3개(6·7·8)+frame 생성+manifest 확정을 한 스토리에 묶음. 전부 동일 frame 위 연산이라 응집도는 높으나 단일 dev 세션 경계선. **권고**: dev 시점에 컨텍스트 부족이 감지되면 "1.7a 평가·등급 / 1.7b PSI·frame·manifest"로 분할 옵션을 스프린트 계획에 메모.
3. 🟡 **Story 3.3 조건부 스코프** — "계정 미확보 시 문서화로 축소"가 AC 안에 조건 분기로 존재. 의도된 설계(사용자 확인 대기)이나, 스프린트 계획에서 상태를 blocked-external로 명시 관리 필요.

세 건 모두 차단 사유 아님 — 1건은 epics.md 1줄 수정으로 즉시 해소 가능(§6 최종 평가에서 처리 여부 결정).

## Summary and Recommendations

### Overall Readiness Status

**READY** ✅

### Critical Issues Requiring Immediate Action

없음. Critical 0 / Major 0 / Minor 3 중:
- Minor 1 (2.3 에러 경로 AC 부재): **본 점검 중 해소** — epics.md Story 2.3에 에러 응답 3종 검증 AC 추가 완료.
- Minor 2 (1.7 사이즈): 스프린트 계획 메모로 이관 — dev 컨텍스트 부족 감지 시 1.7a/1.7b 분할.
- Minor 3 (3.3 조건부 스코프): 스프린트 계획에서 blocked-external(SAS 계정 사용자 확인 대기) 상태로 관리.

### Recommended Next Steps

1. `bmad-sprint-planning`으로 sprint-status 생성 — 1.7 분할 옵션과 3.3 blocked-external 상태를 계획에 반영.
2. Story 1.1(스캐폴딩·데이터 확보)부터 스토리 사이클(CS→DS→CR) 시작 — fresh context 권장.
3. Story 2.5 착수 전 UX 레퍼런스(2026-07-13 조사분)를 dev 컨텍스트에 첨부.

### Final Note

이 점검은 6단계에 걸쳐 3건의 Minor 이슈를 발견했고 그중 1건을 점검 중 해소했다. FR 커버리지 100%(17/17), 전방 의존 0건, 에픽 독립성 충족, AD-1~9 전건이 스토리 AC에 전사됨. 구현 착수를 차단하는 이슈 없음.

**평가자**: Claude (bmad-check-implementation-readiness) / **평가일**: 2026-07-13
