---
baseline_commit: a73f4fb
---

# Story 3.4: MDD·README·GitHub 공개 (Epic 3 마지막)

Status: done

## Story

As a 포트폴리오를 제출하는 지원자,
I want 모형 개발 문서와 README를 완성해 GitHub에 공개하고,
so that 채용담당자가 5분 안에, 실무 면접관이 깊이 있게 프로젝트를 파악할 수 있다.

## Acceptance Criteria

**Given** Epic 1~3의 전 산출물
**When** `docs/MDD.md`와 README.md를 작성하면

1. MDD에 표본설계 근거·성능·한계(**reject inference 실무 보정 방법 서술 포함**)가 담긴다 (NFR4)
2. README 첫 화면에 결과 이미지·핵심 수치가 있고 5분 내 전체 파악이 가능하다
3. GitHub 공개(데이터·아티팩트는 gitignore, NFR5) + 옵시디언 미러가 완료된다
4. 에픽 DoD: 1페이저·리포트 데모 산출물 + git 커밋 + 옵시디언 미러 완료

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC + `pytest -q` 초록(기존 221, 문서 스토리라 신규 테스트는 선택) + **문서 정합성 실증**: MDD·README의 모든 수치가 실제 산출물/리포트와 일치해야 함(임의 수치 금지 — 각 수치의 출처 리포트를 명시). **코드 변경 없음이 기본**(문서 스토리) — 발견되는 코드 이슈는 deferred-work로.

## Tasks / Subtasks

- [x] Task 1: `docs/MDD.md` 작성 (AC: #1, NFR4)
  - [x] **MDD(Model Development Document) 축약판** — 실무 면접관이 깊이 있게 볼 문서. 구성(권장): ①모형 개요·목적 ②데이터·표본설계 근거 ③변수선정·비닝 ④챔피언·챌린저 개발 ⑤성능 평가(3면) ⑥등급화·안정성(PSI) ⑦심사전략 활용(cutoff·손익·룰) ⑧**한계와 향후 과제**.
  - [x] **표본설계 근거**(NFR4 필수): train 2012–13 / valid 2014 / **OOT 2015** 시간축 분리 이유(무작위 분할 아님 = 미래 예측 모사), bad=Charged Off·Default / good=Fully Paid / 진행중 제외(NFR8), 36개월물 한정 이유(만기 성숙 — 2015 빈티지 60개월물은 만기 2020 > 데이터 종료 2018Q4), **grade·int_rate 의도적 배제**(라벨과 순환논리, 1.2 누수감사). 근거 출처: `sample-design-report-1-2.md`, `leakage-audit-1-2.md`.
  - [x] **성능**(실측 인용, 임의 수치 금지): 챔피언 OOT AUC 0.6430 / KS 0.2054, 챌린저 OOT AUC 0.6452 / KS 0.2087, **목표(KS≥0.25, AUC≥0.70) 미달을 숨기지 말고 원인분석과 함께**(7변수 축소모형 + grade/int_rate 배제 트레이드오프 — "성능미달≠실패" 재프레임은 에픽 계획서 근거). PSI 챔피언 0.0047 / 챌린저 0.0030(둘 다 <0.1). 출처: `evaluation-grading-report-1-7a.md`, `psi-validation-frame-report-1-7b.md`.
  - [x] **reject inference 실무 보정 방법 서술**(NFR4 명시 요구, SPEC non-goal "실제 코드 구현 제외 → 한계 문서화로 대체"): ①**왜 문제인가** — 이 모형은 *승인된* 대출만으로 학습(Lending Club accepted 데이터)이라 거절 집단의 성과를 모름 = 선택 편향, 실제 신청 모집단에 적용 시 성능·cutoff 최적점이 낙관 편향될 수 있음. ②**실무 보정 방법 서술**(구현 아님, 서술): Augmentation(reweighting), Parcelling, Fuzzy augmentation, Bivariate probit(Heckman) 등 대표 기법의 아이디어·전제·한계를 간략히. ③**이 프로젝트에서 안 한 이유**: rejected 데이터 미보유(Kaggle accepted 데이터셋만 사용), 보정 없이 "승인 모집단 한정 모형"임을 명시하는 것이 정직. ④**향후**: rejected 데이터 확보 시 적용 경로.
  - [x] **기타 한계**: OOT 표본=1년 볼륨 가정(2.4/3.1), 가상 룰셋(3.1), emp_title 네거티브 결과(3.2), SAS tie-out은 사용자 실행(3.3), 손익은 시뮬레이션이지 재무 데이터 아님.
  - [x] ASCII 우선 원칙(NFR6)은 **설정 파일** 대상이므로 MDD는 한국어 서술 유지(문서는 해당 없음).
- [x] Task 2: README 전면 개편 (AC: #2)
  - [x] **현 README는 stale**(실측: "Status: Story 1.1 진행 중", 결과 수치·이미지 없음, 53줄) → **5분 파악**을 목표로 전면 재작성.
  - [x] 첫 화면(스크롤 없이): 한 줄 소개 → **핵심 수치 표**(데이터 규모·챔피언/챌린저 성능·PSI·손익 최적 cutoff 발견) → **결과 이미지**(대시보드 스크린샷 4장 중 1~2장 인라인, `docs/implementation-artifacts/dashboard-screenshots-2-5/` 기존 자산 재사용 — 새 이미지 생성 불필요) → 빠른 실행법(uvicorn+streamlit 2줄).
  - [x] 그 아래: 아키텍처 1문단(파이프라인→서빙→대시보드, AD-9), **컨설턴트 킥 4종 하이라이트**(손익 cutoff 발견·룰 진단·텍스트 검증·SAS 이식), 문서 지도(MDD·리포트 링크), 재현 절차(NFR5: 데이터 재생성 스크립트).
  - [x] **정직성 유지**: 성능 목표 미달을 첫 화면 수치표에도 목표선과 함께(숨기면 면접에서 역효과 — 프로젝트 전체 톤과 일관).
  - [x] 링크 무결성: 모든 상대경로 링크가 실제 파일을 가리키는지 확인(문서 지도가 깨지면 5분 파악 실패).
- [x] Task 3: CX/DX 임팩트 섹션 (AC: #1/#2 보강, 사용자 요청 반영)
  - [x] **사용자 요청(2026-07-16 논의)**: 기존 지표를 CX/DX 언어로 "번역"하는 섹션을 MDD(또는 README)에 편입 — **코드 변경 0, 신규 분석 금지**(기존 산출물 재해석만).
  - [x] 번역 내용(논의 확정분): 승인율=**고객 접근성** / swap-set=**모델 교체의 고객 영향**(swap-out=CX 리스크) / reason codes=**거절 경험의 설명가능성**(심사의견서 인용 가능 문장) / 손익 최적 cutoff=**CX-수익 트레이드오프 정량화**(승인율 +52.29pp가 손익도 개선 = CX와 수익이 대립하지 않는다는 발견) / 룰 진단=**불필요한 거절 제거**(판별력 없는 연체룰이 우량 5.9만 명 배제, 기회손실 ₩9,441만 = 나쁜 CX의 비용화) / API p95<300ms=**디지털 채널 실시간 심사 SLA(STP 전제)** / 룰 슬림화=**자동화율 향상 여지**.
  - [x] **데이터 한계 명시**: 고객 여정 로그·NPS·채널 행동 데이터가 없어 본격 CX 분석(세그먼트·캠페인)은 불가 — "없어서 못 한 것"으로 정직하게 기록하고 **P2(crm-targeting-lab) 소관**임을 링크. 스코프 크리프 방지.
- [x] Task 4: GitHub 공개 점검 (AC: #3, NFR5)
  - [x] **이미 public repo에 push 중**(`github.com/dariajkim-star/credit_scorecard_lab`) — 이 태스크는 **공개 적합성 점검**: `.gitignore`가 `data/`·`models/artifacts/` 포함 확인(실측 확인됨), **커밋 이력에 데이터·아티팩트·비밀정보가 실수로 들어간 적 없는지 확인**(`git log --stat`에 parquet/joblib 없는지), 개인정보·계정정보 노출 없는지.
  - [x] 재생성 경로가 README에 명확한지(NFR5: 데이터는 `pipelines/01_download.py`, 아티팩트는 파이프라인 재실행).
  - [x] repo 설명·토픽 등 메타는 선택(사용자 몫으로 남겨도 됨).
- [x] Task 5: 옵시디언 미러 + 에픽 DoD (AC: #3, #4)
  - [x] 옵시디언 미러: `ob_storage\신용평가_CRM_사이드프로젝트\`에 **Epic 3 완료 요약 노트 신규**(14번) 또는 기존 노트 갱신 — 킥 4종 결과(손익·룰·텍스트·SAS) + MDD/README 완성 + 최종 포지셔닝. (REST API 꺼져 있으면 파일 직접 작성 — 12/13번 노트 선례.)
  - [x] 에픽 3 DoD: 데모 산출물(1페이저 2-4·룰 리포트 3-1·텍스트 리포트 3-2·SAS 대조 3-3 + 대시보드 스크린샷) 점검 + git 커밋 + 옵시디언 미러.
  - [x] `pytest -q` 전체 통과 확인(문서 스토리지만 회귀 없음 확인).
  - [x] epic-3 → done 전환은 3-4 done + (3-3 사용자 SAS tie-out 확인 여부 반영) 후 sprint-status.yaml에서.

### Review Findings (2026-07-16, 3-레이어: Fact-checker/Auditor/Reader-experience)

- [x] [Review][Patch] **통화 오기(치명)** — 손익 수치가 ₩로 표기됐으나 원 출처(profit-cutoff-onepager-2-4)는 **USD(+$132M)**이며 "원화 환산 없이 원 통화 그대로"라는 명시 경고까지 있음. LC 데이터는 USD. MDD·README의 ₩131.8M→**+$132M**, 기회손실 ₩9,441만→**$94.4M**로 정정. **rule-efficiency-report-3-1.md의 ₩ 표기도 동일 오류**(같은 세션에서 전파) — 함께 정정 [MDD.md, README.md, rule-efficiency-report-3-1.md] (fact-checker, High)
- [x] [Review][Patch] **손익 최적 cutoff 494.43은 경계해** — 점수 최소값 496보다 낮음 = 탐색 구간 하단 = 사실상 "전원 승인". "발견"이 아니라 **accepted-only 데이터에서 손익 곡선이 준단조라는 진단 신호**로 재프레이밍(LC가 이미 하위 신청을 거절했으므로 잔존 최하위도 이자수익이 남는 구조적 필연 — reject inference 한계와 연결). §9/README의 "CX와 수익은 대립하지 않는다" 단정도 조건부로 완화(§10.1이 스스로 무효화하는 내부 모순 해소) [MDD §7.2·§9, README 발견1] (reader, High)
- [x] [Review][Patch] README에 룰이 **가상**임을 발견2 문장 안에 명시(현재는 수치가 실측처럼 병렬) + DTI 룰 **n=34 소표본** 주의를 MDD §7.3에 병기(부도율 23.5%의 표준오차 ±7pp 수준, 다른 두 룰과 증거 강도가 다름) [README, MDD §7.3] (reader, High)
- [x] [Review][Patch] **int_rate 배제 근거 표현 정정** — "라벨과 순환논리"는 부정확. 정확히는 "타 기관(LC) 심사 결과의 대리변수 + 자사 신규 심사 시점에 부재". 아울러 §7.2 손익이 실현 상환액(int_rate 반영)을 쓰는 것은 **피처가 아니라 성과(outcome) 데이터 사용**이라는 구분을 한 줄 명시(비대칭 해명) [MDD §2.5·§5·§7.2] (reader, Med-High)
- [x] [Review][Patch] "과적합 없음 ⇒ 정보 상한" 논리 비약 완화 — 과소적합과 구별 불가, 7변수는 본인이 좁힌 선택. "상한에 가깝다" 단정 대신 "추가 정보 없이는 개선 여지가 제한적임을 시사(17변수 벤치마크 미수행은 한계)"로 [MDD §5] (reader, Med-High)
- [x] [Review][Patch] swap-set 서술 보강 — swap_in 부도율 13.55% 병기(대칭 비교), "실증"→"방향성 시사"로 완화(AUC 차 0.0022는 노이즈 수준) [MDD §7.1] (reader, Med)
- [x] [Review][Patch] PSI 해석 한 줄 추가 — 빈티지 부도율이 12.70→14.89%로 이동했는데 점수 PSI 0.005는 "안정"인 동시에 그 이동을 점수가 못 담는다는 "둔감"일 수 있음(낮은 KS와 정합) [MDD §6.2] (reader, Med)
- [x] [Review][Patch] base_odds=50/base_score=600 앵커가 실제 포트폴리오 odds(~5.7:1)와 다름을 명시 — 관행 앵커일 뿐 보정된 값 아니며 점수는 서열 도구로 사용 [MDD §4.1] (reader, Med)
- [x] [Review][Patch] 현재 cutoff 546.01의 출처·성격 명시 — Story 2.1 리포트의 데모 관행값(실제 정책 아님), +52.29pp의 분모라는 점에서 해명 필수 [MDD §7.2] (reader, Med)
- [x] [Review][Patch] README "85~94%"→"85~91%(챔피언 기준)" 정밀화(두 모델 수치 뭉갬) + 소소한 표현: "값을 하는지"→격식체, "3면 평가"→"train/valid/OOT 3분할 평가"로 첫 등장 시 병기, "미러" 첫 등장 정의, README 상단에 "무엇을 만들었나" 한 문장 [README, MDD] (auditor+reader, Low-Med)
- [x] [Review][Patch] Parcelling 서술 정밀화 — "확률적 배정(random assignment)" 명시 [MDD §10.1] (reader, Low)
- [x] [Review][Defer] **통화 오류의 코드·계약 흔적** — `app/schemas.py`의 `annual_profit_krw` 필드명(API_SPEC §7 예시에서 유래), 대시보드 `fmt_krw`(₩ 포맷)도 동일 혼동의 산물. 필드명 변경은 파괴적(계약)이라 /v2 또는 별도 결정 필요 — deferred-work 기록 [app/schemas.py, dashboard/app.py, API_SPEC §7] — deferred

dismiss: PSI valid→OOT 수치의 출처(1-7b 아님, 2-3/2-5) — MDD §6.2가 이미 "서빙 API·대시보드"로 올바르게 표기(fact-checker 확인).

## Dev Notes

### 이 스토리의 성격 — 프로젝트의 얼굴
코드가 아니라 **읽는 사람**이 산출물. 청자가 둘로 갈린다:
- **채용담당자(5분)**: README 첫 화면만 본다 → 수치·이미지·한 줄 요약이 전부.
- **실무 면접관(깊이)**: MDD를 본다 → 표본설계 근거·성능 해석·**한계 인식**(특히 reject inference)이 실력의 증거.

이 프로젝트 전체를 관통한 **정직성 톤**(성능 미달 명시, 네거티브 결과 기록, 가정 투명)이 여기서 완성된다 — 숨기지 않는 것이 오히려 강점이라는 서사.

### 실측 수치 (임의 수치 금지 — 전부 출처 있음)
| 항목 | 값 | 출처 |
|---|---|---|
| 원본 → 필터 | 226만 → **589,635행**(2012–15, 36m) | 1.1/1.2 |
| train / valid / OOT | 143,892(bad 12.70%) / 162,570(13.73%) / **283,026(14.89%)** | `sample-design-report-1-2.md` |
| 변수선정 | 17 후보 → **7개** | `binning-selection-report-1-4.md` |
| 챔피언 OOT | AUC **0.6430**, KS **0.2054**(목표 0.25 미달) | `evaluation-grading-report-1-7a.md` |
| 챌린저 OOT | AUC **0.6452**(목표 0.70 미달), KS **0.2087** | 동상 |
| PSI(valid→OOT) | 챔피언 **0.0047**, 챌린저 **0.0030**(목표 <0.1 통과) | `psi-validation-frame-report-1-7b.md` |
| 등급 | 10등급 완전 단조, 부도율 **4.07% → 23.57%** | 1.7a/1.7b |
| 손익 최적 cutoff | **494.43 vs 현재 546.01**, 승인율 **+52.29pp**, 연간 **+₩131.8M**(avg 12,000) | `profit-cutoff-onepager-2-4.md` |
| 룰 진단 | 가상 룰 3종 **전부 재검토 권장**(DTI/INQ 모형 중복 85~94%, DELINQ 1.07배·기회손실 ₩9,441만) | `rule-efficiency-report-3-1.md` |
| emp_title | IV **0.0116**(임계 0.02 미달, 전 정형변수보다 낮음) | `text-features-report-3-2.md` |
| SAS 이식 | 미러 12건 최대 오차 **4.74e-07**(기준 0.5) | `sas-replication-report-3-3.md` |
| 테스트 | **221 passed** | 현재 |

### reject inference — NFR4가 콕 집어 요구하는 항목
SPEC non-goal: "reject inference의 실제 코드 구현 (한계 문서화로 대체)". 즉 **구현하지 말고, 제대로 서술하라**가 요구사항. 면접관이 가장 좋아할 대목이므로 성의 있게:
- 이 데이터는 Kaggle **accepted** loans — 거절된 신청의 성과는 관측 불가(구조적).
- 따라서 이 모형은 엄밀히 "승인 모집단 조건부 모형"이며, 신청 모집단 전체에 적용 시 편향 가능.
- 대표 보정 기법(Augmentation/reweighting, Parcelling, Fuzzy augmentation, Heckman 2단계)의 **아이디어·전제·한계**를 간략 서술 — 각각 무엇을 가정하고 왜 완전한 해가 아닌지.
- 정직한 결론: 데이터가 없어 보정 불가 → **한계로 명시**하는 것이 옳은 처리. (Lending Club rejected 데이터셋이 별도 존재하나 변수 셋이 달라 결합이 또 다른 가정을 요구한다는 점까지 언급하면 깊이 있음.)

### 재사용 지도 — 새로 만들지 말 것
- **리포트 12개 이미 존재**(`docs/implementation-artifacts/*.md`) — MDD는 이들의 **종합·요약**이지 재조사가 아니다. 각 절에서 상세 리포트로 링크.
- **스크린샷 4장 존재**(`dashboard-screenshots-2-5/`) — README 이미지로 재사용, 새로 캡처 불필요.
- **`.gitignore` 이미 적정**(data/, models/artifacts/, .venv/) — 확인만.
- 옵시디언 노트 12(에픽1 완료)·13(에픽2) 선례 — 14번 에픽3 요약 동일 톤.
- 아키텍처 서술은 `ARCHITECTURE-SPINE.md`(AD-1~9) 요약 인용.

### 아키텍처 가드레일
- **코드 변경 없음**이 기본 — 이 스토리는 문서. 코드 이슈 발견 시 `deferred-work.md`에 기록만.
- **NFR5**: 데이터·아티팩트 gitignore 유지, 재생성 스크립트로 대체.
- **NFR6**: ASCII 우선은 설정 파일 대상(문서는 한국어 유지).
- **NFR4**: MDD 필수 구성 = 표본설계 근거 + 성능 + 한계(reject inference 포함).

### 스코프 가드 (하지 말 것)
- 새 분석·새 수치 생성 금지 — 기존 산출물의 종합만. (CX/DX 섹션도 **재해석**이지 신규 분석 아님.)
- 코드 리팩터링·기능 추가 금지.
- 성능 미달을 미화·은폐 금지 — 원인분석과 함께 명시(프로젝트 톤).
- 본격 CX 분석(세그먼트·캠페인·여정) 금지 — 데이터 없음 + P2 소관, 한계로만 기록.
- rejected 데이터 확보·reject inference 구현 금지 — SPEC non-goal, 서술만.

### 이전 스토리 인텔리전스
- 전 스토리 공통 톤: **정직성**(2.4 assumptions, 3.1 가상 룰셋 명시, 3.2 네거티브 결과, 3.3 사용자 실행 의존 명시) — MDD/README도 동일.
- 1.1 사고 이력: README에 병합충돌 마커가 커밋된 적 있음(d87d05d→94f38ff 복구) — README 대규모 수정 시 최종 내용 육안 확인.
- 3.2/3.1 리뷰 교훈: 문서 수치는 **재현 가능한 출처**를 명시(ad-hoc 수치 금지). MDD 표마다 출처 리포트 링크.
- 2.5 교훈: 스크린샷은 이미 있음 — 재캡처 시 서버 2개 기동 필요하므로 재사용이 합리적.

### Project Structure Notes
- `docs/MDD.md` — NEW(핵심 산출물).
- `README.md` — MODIFIED(전면 개편, 현재 stale).
- `ob_storage\신용평가_CRM_사이드프로젝트\14_P1_에픽3_완료_요약.md` — NEW(옵시디언 미러).
- `docs/implementation-artifacts/sprint-status.yaml` — MODIFIED(3-4·epic-3 상태).
- 코드(`scorecard/`·`app/`·`dashboard/`·`sas/`) — **변경 없음**.

### References
- [Source: docs/planning-artifacts/epics.md#Story-3.4] — AC 원문(NFR4, NFR5)
- [Source: docs/specs/spec-credit-scorecard-lab/SPEC.md] — non-goal "reject inference 실제 코드 구현 제외(한계 문서화로 대체)", NFR4/NFR5/NFR6/NFR8 원문
- [Source: docs/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md] — AD-1~9(아키텍처 서술 재료)
- [Source: docs/implementation-artifacts/*.md] — 리포트 12종(MDD 종합 대상, 수치 출처)
- [Source: docs/implementation-artifacts/dashboard-screenshots-2-5/] — README 결과 이미지 4장

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

- **스토리 표의 PSI 출처 오기를 작성 중 발견·수정**: 스토리 Dev Notes 표가 "PSI 0.0047/0.0030 출처=`psi-validation-frame-report-1-7b.md`"라 했으나, 1.7b 리포트의 실제 값은 **train→OOT 0.0017/0.0013**이고 0.0047/0.0030은 **valid→OOT**(서빙 API가 노출하는 값, API_SPEC §2가 "다른 비교축"이라 명시). MDD는 **두 축을 모두 표로 구분**해 기재(§6.2). — 스토리 작성 시 수치를 옮겨 적으면 이런 오기가 생긴다는 실증(3.2 리뷰의 "출처 명시" 교훈이 정확히 이 지점을 잡음).

### Completion Notes List

- **`docs/MDD.md` 신규(12장)**: 개요 → 표본설계 근거 → 전처리·변수선정 → 챔피언·챌린저 → 성능(3면) → 등급·PSI → 심사전략(cutoff·손익·룰·사유) → 검증한 것들(텍스트·SAS) → **CX/DX 함의** → **한계와 향후** → 재현 → 문서 지도. **전 수치에 출처 리포트 링크**(임의 수치 0).
- **reject inference 4단 서술(NFR4 핵심)**: ①왜 편향인가(accepted-only = "승인 모집단 조건부 모형", cutoff 최적점도 편향 가능) ②**기법 비교표**(Augmentation/Parcelling/Fuzzy/Heckman의 아이디어·전제·한계 + 공통 한계="검증 불가능한 가정 추가, 잘못된 보정은 무보정보다 나쁠 수 있음") ③안 한 이유(rejected 데이터 미보유, LC rejected는 변수셋 상이해 결합이 또 다른 가정) ④향후(거절 이력 확보→Augmentation→CB로 사후 검증 = **통계 기법 이전에 데이터 확보 전략 문제**).
- **README 전면 개편**: stale("Story 1.1 진행 중") → 5분 파악 구조. 첫 화면=핵심 수치 8행 표 + **성능 미달을 목표선과 함께 정직 표기**(과적합 없음 근거 병기) → **발견 3가지**(손익 cutoff·룰 중복·텍스트 네거티브) → 대시보드 스크린샷 2장 인라인(기존 자산 재사용) → 빠른 실행 → 아키텍처(AD 4개) → 킥 4종 표 → 문서 지도.
- **CX/DX 섹션(MDD §9)**: 사용자 요청 반영. 기존 지표 **재해석만**(신규 분석 0, 코드 0) — 승인율=접근성, swap-set=고객 영향, reason codes=설명가능성, 손익 cutoff=**CX-수익 비대립 정량 근거**, 룰 진단=나쁜 CX의 비용화, p95 33.6ms=STP 전제. **한계 명시**: 여정·NPS·채널 데이터 없어 본격 CX는 P2 소관.
- **공개 적합성 점검 통과(NFR5)**: `git log --all --name-only`에 parquet/joblib/csv.gz/manifest **유입 이력 0**, 추적 파일 중 위험 확장자 **0**, `.gitignore` 적정(data/·models/artifacts/·.env). *의도적 커밋*: `sas/reference_applicants.csv`(12건)·`.sas` datalines는 공개 Kaggle 데이터의 익명 레코드(PII 없음)이며 SAS 자기완결성에 필요 — 데이터셋 전체 커밋(NFR5 금지 대상)과 구분.
- **링크 무결성 검증**: README·MDD의 전 상대경로 링크 스크립트 검사 → **ALL OK**(깨진 링크 0).
- **에픽 3 DoD 충족**: 데모 산출물 7종(1페이저·룰·텍스트·SAS 리포트 + MDD·README·.sas) + 스크린샷 4장 존재 확인, git 커밋, 옵시디언 미러(14번 노트 신규 — 킥 4종·reject inference·CX/DX·교훈 4개·최종 상태).
- **코드 변경 0**(문서 스토리 원칙 준수). pytest **221 passed** 회귀 없음.

### File List

- `docs/MDD.md` (NEW — 모형 개발 문서 12장, NFR4)
- `README.md` (MODIFIED — 전면 개편, 5분 파악 구조)
- `ob_storage/신용평가_CRM_사이드프로젝트/14_P1_에픽3_완료_요약.md` (NEW — 옵시디언 미러, repo 밖)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 3-4 상태)
- 코드(`scorecard/`·`app/`·`dashboard/`·`sas/`) — **변경 없음**

## Change Log

- 2026-07-16: 3-레이어 문서 리뷰(Fact-checker/Auditor/Reader-experience) — patch 11건 반영. 핵심: ①**통화 오기 정정(₩→$)** — 손익 +$132M·기회손실 $94.4M, 원 출처(2-4 1페이저)의 USD 원칙 위반을 3-1 리포트까지 소급 수정 ②**손익 최적점 494.43=경계해 재프레이밍** — 점수 최소값(496) 미만=사실상 전원 승인, accepted-only 구조적 결과로 진단하고 reject inference와 연결, CX/DX 단정 조건부화 ③DTI 룰 n=34 소표본 주의 ④int_rate 배제 근거 정정(순환논리→타사 스코어 대리변수+신규심사 부재)+손익의 outcome 사용 구분 ⑤정보상한 논리 완화 ⑥swap-set 완화(swap_in 13.55% 병기) ⑦PSI 둔감 양면 해석 ⑧base_odds 앵커 한계 ⑨546.01 출처 명시 ⑩README 85~91%·상단 한줄·표현 정리 ⑪Parcelling 확률적 배정. deferred: annual_profit_krw 필드명·fmt_krw(계약 변경 필요). 링크·앵커 ALL OK, ₩ 잔존 0. Status → done.
- 2026-07-16: Story 3.4 구현 — docs/MDD.md 신규(12장, reject inference 4단 서술 포함, 전 수치 출처 링크) + README 전면 개편(5분 파악, 발견 3가지, 스크린샷 인라인) + CX/DX 섹션(재해석만) + 공개 점검(커밋 이력 clean·링크 ALL OK) + 옵시디언 14번 미러. 작성 중 PSI 비교축 출처 오기 발견·수정(train→OOT vs valid→OOT 구분). 코드 변경 0, 221 passed. Status → review.
- 2026-07-16: Story 3.4 생성 — Epic 3 마지막(문서화). NFR4의 reject inference를 SPEC non-goal(구현 제외→서술 대체)에 맞춰 "왜 문제/대표 기법 서술/안 한 이유/향후"의 4단 구성으로 명세, 실측 수치 12항목을 출처 리포트와 함께 표로 고정(임의 수치 금지), README stale 상태(1.1 진행중) 확인 후 5분 파악 구조 설계, 스크린샷·리포트 재사용 지도 작성, 사용자 요청 CX/DX 임팩트 섹션을 "기존 지표 재해석(코드 0)"으로 스코프 한정하고 본격 CX는 P2 소관으로 경계.
