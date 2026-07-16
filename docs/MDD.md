# 모형 개발 문서 (MDD 축약판) — credit-scorecard-lab

> Lending Club 실데이터로 개발한 신용평가 스코어카드(챔피언) + LightGBM(챌린저), 그리고 심사전략 분석(cutoff·손익·룰)까지의 개발 기록. **모든 수치는 실데이터 실행 결과이며 각 절 끝에 출처 리포트를 명시**합니다.
>
> 작성: Story 3.4 (NFR4) · 대상 독자: 실무 면접관·리뷰어 (5분 요약은 [README](../README.md))

---

## 1. 모형 개요와 목적

| 항목 | 내용 |
|---|---|
| 목적 | 신청 시점 정보로 대출 부도(bad) 확률을 추정하고, **점수·등급·사유**를 산출해 심사 의사결정을 지원 |
| 챔피언 | WOE 로지스틱 스코어카드 (Siddiqi PDO 스케일: PDO=20, base_score=600, base_odds=50) |
| 챌린저 | LightGBM + isotonic calibration |
| 산출 | score / PD / grade / reason_codes — **판정(승인·거절)은 산출하지 않음** (cutoff 적용은 소비자 몫) |
| 서빙 | FastAPI 8개 엔드포인트, Streamlit 4화면 대시보드 |

**설계 철학**: 모형은 점수를 주고, 판정은 정책이 한다. 그래서 이 프로젝트의 절반은 "점수를 어떻게 심사 전략으로 번역하는가"(cutoff·손익·룰 진단)에 있습니다.

---

## 2. 데이터와 표본설계 근거 (NFR8)

### 2.1 데이터

Kaggle Lending Club accepted loans (2007–2018Q4) → **필터 후 589,635건** (2012–2015 빈티지, 36개월물).

### 2.2 표본 분할 — 왜 무작위가 아니라 시간축인가

| split | 빈티지 | 건수 | 부도율 |
|---|---|---:|---:|
| train | 2012–2013 | 143,892 | 12.70% |
| valid | 2014 | 162,570 | 13.73% |
| **OOT** | **2015** | **283,026** | **14.89%** |

**근거**: 무작위 분할은 같은 시점 데이터가 학습·검증에 섞여 실제 운영(과거로 학습 → 미래에 적용)을 모사하지 못합니다. 빈티지 기준 분리는 **미래 예측 상황을 그대로 재현**하고 완전 결정론적(RNG 없음)입니다. 빈티지별 부도율이 12.70% → 14.89%로 상승하는 것도 실제 시계열 특성이며, OOT가 가장 보수적인 평가가 됩니다.

### 2.3 라벨 정의

- **bad** = `loan_status ∈ {Charged Off, Default}`, **good** = `Fully Paid`
- **진행중(Current 등) 제외** — 성과가 확정되지 않은 건을 라벨링하면 오분류.
- 만기 기준 라벨이므로 별도 12개월 성과창은 **미채택**(중도 상태 오분류 위험이 더 큼).

### 2.4 36개월물 한정 — 만기 성숙 제약

60개월물로 확장하면 표본이 늘지만, **2015 빈티지 60개월물은 만기가 2020년**으로 데이터 종료(2018Q4)를 넘어 성과가 미확정입니다. 확장하려면 2013 이전 빈티지로 한정해야 하므로, 일관성을 위해 36개월물만 사용했습니다.

### 2.5 누수 감사 — grade·int_rate 의도적 배제

Lending Club의 `grade`/`sub_grade`/`int_rate`는 **Lending Club 자체 심사 결과**입니다. 이를 피처로 쓰면 "남의 모형 결과로 내 모형을 만드는" 순환논리이고, 실제 신규 심사 시점에는 존재하지 않습니다. → **보수적으로 배제**.

이 결정이 성능 상한을 낮춘 주요 원인이며(§5), 그럼에도 방법론적으로 올바른 선택이었다고 판단합니다.

> 출처: [`sample-design-report-1-2.md`](implementation-artifacts/sample-design-report-1-2.md), [`leakage-audit-1-2.md`](implementation-artifacts/leakage-audit-1-2.md)

---

## 3. 전처리·변수선정·비닝

- **결측**: 대치하지 않고 **WOE의 별도 빈**으로 처리(결측 자체가 정보). 서빙까지 일관되게 `metric_missing="empirical"` 적용 — 기본값(0)을 쓰면 결측 빈의 실제 WOE가 무력화되는 함정을 스파이크에서 발견해 단일 경로로 고정(AD-2).
- **이상치**: train 1%/99% 분위수 캡핑. 단 `delinq_2yrs`·`inq_last_6mths`·`pub_rec` 같은 **zero-inflated 카운트 변수는 캡핑 제외** — 2건과 5건의 실제 위험 차이가 뭉개지는 것을 실측 확인.
- **비닝**: optbinning, 수치형은 단조 제약(`auto_asc_desc`), 범주형은 categorical solver.
- **변수선정**: IV ≥ 0.02 필터 → IV 내림차순 그리디 상관 제거(|corr| > 0.7). **17개 후보 → 7개 확정**. fico_range_low/high는 상관 ≈ 1.000으로 정확히 하나만 생존.

**최종 7개 변수**: `fico_range_low`, `annual_inc`, `dti`, `home_ownership`, `revol_util`, `inq_last_6mths`, `purpose`

> 출처: [`preprocessing-report-1-3.md`](implementation-artifacts/preprocessing-report-1-3.md), [`binning-selection-report-1-4.md`](implementation-artifacts/binning-selection-report-1-4.md)

---

## 4. 챔피언·챌린저 개발

### 4.1 챔피언 — WOE 로지스틱 스코어카드

- train WOE에 로지스틱 회귀 fit → **계수 7개 전부 음수**(WOE ↑ = 안전 ⇒ logit(bad) ↓)로 부호 검증 통과.
- 점수 변환: `score = offset + factor × (−logit)`, `factor = PDO/ln2`, `offset = base_score − factor×ln(base_odds)`. **base_odds=50은 SPEC 미명시 → 업계 관행값으로 스토리오너 결정·기록**.
- 점수 분포 496~601.

### 4.2 챌린저 — LightGBM + 보정

- Optuna(고정 시드, 20 trials), valid logloss로 선정. **원변수 사용**(WOE 미변환) — LightGBM이 nullable/category dtype을 직접 처리.
- Isotonic calibration: Brier **0.11491 → 0.11480** (개선).

### 4.3 공통 점수 스케일

`generalized_score(p_bad) = score_formula(logit(p_bad))`로 챔피언·챌린저를 **동일 Siddiqi 스케일**에 올려, 단일 cutoff 값으로 두 모형을 직접 비교할 수 있게 했습니다(챔피언 자체 점수와 diff 5.7e-14로 동치 확인).

> 출처: [`champion-scorecard-report-1-5.md`](implementation-artifacts/champion-scorecard-report-1-5.md), [`challenger-report-1-6.md`](implementation-artifacts/challenger-report-1-6.md)

---

## 5. 성능 평가 (3면) — 목표 미달과 그 원인

| model | split | AUC | KS | PR-AUC | OOT 목표 |
|---|---|---:|---:|---:|---|
| champion | train | 0.6468 | 0.2120 | 0.1978 | — |
| challenger | train | 0.6603 | 0.2298 | 0.2071 | — |
| champion | valid | 0.6406 | 0.2022 | 0.2073 | — |
| challenger | valid | 0.6440 | 0.2064 | 0.2076 | — |
| **champion** | **oot** | **0.6430** | **0.2054** | 0.2239 | **미달** (KS ≥ 0.25) |
| **challenger** | **oot** | **0.6452** | 0.2087 | 0.2222 | **미달** (AUC ≥ 0.70) |

### 두 OOT 목표 모두 미달했습니다 — 숨기지 않고 원인을 밝힙니다

1. **7변수 축소모형**: IV 필터·상관 제거를 거쳐 신청시점 변수 7개만 사용. 변수를 늘리면 성능은 오르지만 누수·과적합 위험이 커집니다.
2. **grade·int_rate 의도적 배제(§2.5)**: 이들을 넣으면 AUC는 즉시 크게 오르지만, **라벨과 순환논리**입니다. 성능 숫자를 위해 방법론을 포기하지 않았습니다.
3. **train/valid/OOT 간 성능 차가 작음**(0.6468/0.6406/0.6430) — **과적합은 없습니다**. 즉 "모형이 데이터를 외운" 문제가 아니라, 사용 가능한 정보의 상한에 가깝다는 뜻입니다.

에픽 계획서는 이 상황을 사전에 **"성능 미달 ≠ 실패, 원인 분석 문서가 대체 산출물"**(FR6)로 재프레임해 두었고, 이 문서가 그 산출물입니다. 실무적으로도 "왜 낮은지 설명할 수 있는 모형"이 "왜 높은지 모르는 모형"보다 안전합니다.

> 출처: [`evaluation-grading-report-1-7a.md`](implementation-artifacts/evaluation-grading-report-1-7a.md)

---

## 6. 등급화와 안정성

### 6.1 등급 (10등급)

- train 등빈도 분위수로 임계치 fit, **등급 1 = 최고 점수(최저 위험)**, 경계는 우측폐구간 `(score_min, score_max]`.
- **10등급 자연 단조 달성**(병합 불필요): 부도율 **4.07%(1등급) → 23.57%(10등급)**.
- 단조가 깨질 경우를 대비한 인접 등급 반복 병합 로직도 구현·검증(깨끗한 신호는 10등급 유지, 순수 노이즈는 1등급까지 병합 후 정상 종료).

### 6.2 PSI — 두 비교축을 구분합니다

| 비교축 | 챔피언 | 챌린저 | 목표 | 용도 |
|---|---:|---:|---|---|
| **train → OOT** | **0.0017** | **0.0013** | <0.1 ✅ | 개발 안정성(1.7b 리포트) |
| **valid → OOT** | **0.0047** | **0.0030** | <0.1 ✅ | 서빙 API·대시보드가 노출하는 값 |

두 축은 **다른 비교**입니다(서빙은 scored validation frame의 valid+oot만 소비 가능). 둘 다 목표를 통과하며 점수 분포는 매우 안정적입니다. 변수별 PSI도 전부 <0.1.

> **실데이터가 잡은 버그**: `np.quantile`이 NaN을 전파해 결측 있는 변수(revol_util)의 PSI가 **조용히 0.0으로 마스킹**되던 문제를 실행 중 발견·수정(합성 테스트로는 안 잡혔음).

> 출처: [`evaluation-grading-report-1-7a.md`](implementation-artifacts/evaluation-grading-report-1-7a.md), [`psi-validation-frame-report-1-7b.md`](implementation-artifacts/psi-validation-frame-report-1-7b.md)

---

## 7. 심사전략 활용 — 점수를 의사결정으로

### 7.1 Cutoff 트레이드오프와 swap-set

- 전 구간 cutoff별 승인율·부도율 곡선 산출(OOT 기준).
- **챔피언 → 챌린저 교체 시**: `swap_out`(챔피언 승인·챌린저 거절) **15,115명의 부도율 14.95%** vs `stable_approved` **8.81%** — 챌린저가 걸러내는 집단이 실제로 더 위험. 교체 방향성 실증.

### 7.2 손익 기반 cutoff (컨설턴트 킥①) — 이 프로젝트의 핵심 발견

리스크(부도율)가 아닌 **실현 손익**(`total_pymnt + recoveries − loan_amnt`)으로 cutoff을 평가한 결과:

| | 현재 cutoff | 손익 최적 cutoff | 차이 |
|---|---:|---:|---|
| 챔피언 | 546.01 | **494.43** | 승인율 **+52.29pp**, 연간 기대손익 **+₩131.8M** |
| 챌린저 | 547.60 | **507.10** | — |

**발견**: 손익 최적점이 리스크 기준 cutoff보다 **훨씬 낮고**, 최적점에서 승인율이 거의 100%로 수렴합니다. 이자수익이 부도손실을 상쇄하는 구간이 리스크 관점의 거절 영역까지 뻗어 있다는 뜻입니다.

*(가정: OOT 표본 = 1년 승인 볼륨, avg_loan_amnt=12,000 스케일링. 손익 시뮬레이션이지 재무 데이터가 아닙니다.)*

### 7.3 룰 효율성 진단 (컨설턴트 킥②)

실무 관행 기반 **가상** 하드룰 3종을 진단(모두 재검토 권장):

| 룰 | 배제 | 배제집단 부도율 | 모집단 대비 | 판정 근거 |
|---|---:|---:|---:|---|
| DTI > 40 | 34 | 23.5% | 1.58배 | **91%를 모형이 이미 거절**(중복) |
| 조회 ≥ 3 | 11,686 | 24.4% | 1.64배 | **85%를 모형이 이미 거절**(중복) |
| 연체 ≥ 1 | 58,974 | 16.0% | **1.07배** | 판별력 낮음, 기회손실 **₩9,441만** |

**시사점**: 스코어카드가 있으면 이 하드룰들은 중복이거나 비효율입니다. 특히 연체 룰은 모집단의 21%를 거절하면서 판별력이 거의 없어 우량 고객을 대량으로 잃습니다.

### 7.4 사유 코드 (reason codes)

챔피언=특성별 점수손실, 챌린저=SHAP. **동일 구조**(rank/variable/description 공유, 값 필드만 상이)로 심사의견서에 그대로 인용 가능한 완성 문장을 반환. **실제 불리한 요인만** 반환하므로 안전한 신청자는 0건이 정상입니다.

> **실데이터가 잡은 치명 버그**: `points_lost` 공식의 부호가 반대로 구현돼 전 변수가 0.0으로 뭉개지던 문제 — 기존 테스트가 같은(틀린) 공식을 "독립 검증"이라며 재구현한 **동어반복 함정**이었고, best/worst 행동 테스트로 교체해 회귀 방지.

> 출처: [`cutoff-swapset-report-2-1.md`](implementation-artifacts/cutoff-swapset-report-2-1.md), [`profit-cutoff-onepager-2-4.md`](implementation-artifacts/profit-cutoff-onepager-2-4.md), [`rule-efficiency-report-3-1.md`](implementation-artifacts/rule-efficiency-report-3-1.md), [`reason-codes-report-2-2.md`](implementation-artifacts/reason-codes-report-2-2.md)

---

## 8. 검증한 것들 — 효과가 없어도 기록

### 8.1 비금융 텍스트 파생변수 (컨설턴트 킥③) — 네거티브 결과

`emp_title`(직함)에서 상위 20개 빈도 카테고리 + OTHER + MISSING 파생변수를 만들어 IV 측정:

| 변수 | IV |
|---|---:|
| fico_range_low | 0.1298 |
| annual_inc | 0.0986 |
| dti | 0.0422 |
| home_ownership | 0.0346 |
| revol_util | 0.0297 |
| inq_last_6mths | 0.0284 |
| purpose | 0.0244 |
| **emp_title_category** | **0.0116** ← 임계(0.02) 미달, 최하위 |

**결론: 이 데이터·이 방식에서 비금융 텍스트는 유의미한 추가 판별력을 주지 못했습니다.** 원인: 고유값 207,516개의 롱테일이라 상위 20개로도 88.8%가 OTHER로 뭉치고, 직종과 고용주가 혼재(us army/walmart/bank of america)하며, 직업의 위험 정보는 이미 소득·연체 변수에 흡수돼 있습니다.

**효과가 없다는 것을 검증한 것 자체가 산출물입니다** — 근거 없이 피처를 늘려 모형을 복잡하게 만드는 것을 피한 판단.

### 8.2 SAS 이식 (컨설턴트 킥④)

점수 산출 로직(WOE 룩업 → 선형결합 → PDO 스케일)을 SAS로 이식. 아티팩트에서 **자동생성**해 손 복사 오차를 원천 차단했고, 순수 산술 미러로 검증한 결과 **12건 최대 오차 4.74e-07점**(기준 0.5점). "Python으로 개발, SAS로 이식 검증"이 가능함을 증빙합니다.

> 출처: [`text-features-report-3-2.md`](implementation-artifacts/text-features-report-3-2.md), [`sas-replication-report-3-3.md`](implementation-artifacts/sas-replication-report-3-3.md)

---

## 9. CX·DX 관점의 함의

이 프로젝트의 지표들은 그대로 고객경험(CX)·디지털경험(DX) 지표로 읽을 수 있습니다. **기존 산출물의 재해석**이며, 별도 CX 분석을 수행한 것은 아닙니다.

| 모형 지표 | CX/DX 함의 |
|---|---|
| 승인율 (cutoff 곡선) | **고객 접근성** — cutoff 1점이 몇 명의 승인/거절을 가르는가 |
| swap-set 4분면 | **모형 교체의 고객 영향** — swap_out 15,115명은 기존이라면 승인됐을 고객(CX 리스크), swap_in 5,049명은 새 기회 |
| reason codes | **거절 경험의 품질** — "왜 거절인지" 완성 문장 제공 = 설명가능성·공정성 |
| 손익 최적 cutoff | **CX와 수익은 대립하지 않는다** — 승인율 +52.29pp가 손익도 +₩131.8M (§7.2). CX 개선의 근거를 수익 언어로 제시 |
| 룰 효율성 진단 | **불필요한 거절 제거** — 판별력 없는 연체룰이 우량 고객 배제, 기회손실 ₩9,441만 = 나쁜 CX의 비용화 |
| API p95 < 300ms (실측 33.6ms) | **DX: 디지털 채널 실시간 심사 SLA** — 즉시 응답 = STP(무인 자동심사)의 전제 |
| 룰 레이어 슬림화 제안 | **DX: 자동화율 향상 여지** — 수동 개입 룰 축소 |

**한계**: 고객 여정 로그·NPS·채널 행동 데이터가 없어 세그먼트·캠페인·여정 분석 같은 **본격 CX 분석은 불가능**합니다. 이 데이터셋으로 할 수 있는 것은 "심사 결과가 고객에게 미치는 영향"까지이며, 이탈×LTV 타겟팅 등은 자매 프로젝트(P2 crm-targeting-lab) 소관입니다.

---

## 10. 한계와 향후 과제

### 10.1 Reject inference — 이 모형의 가장 근본적 한계

**무엇이 문제인가.** 이 모형은 Kaggle Lending Club **accepted**(승인) 데이터로만 학습했습니다. 거절된 신청자의 성과(부도 여부)는 **구조적으로 관측 불가능**합니다 — 대출이 나가지 않았으니 결과가 없습니다. 따라서 이 모형은 엄밀히 말해 **"승인 모집단 조건부 모형"**이며, 실제 신청 모집단 전체에 적용하면:

- 성능 지표가 낙관 편향될 수 있고,
- cutoff 최적점(§7.2의 손익 발견 포함)이 실제와 다를 수 있으며,
- 저품질 신청 구간의 위험을 과소평가할 수 있습니다.

**실무 보정 방법 (서술 — 이 프로젝트에서 구현하지 않음)**

| 기법 | 아이디어 | 전제 | 한계 |
|---|---|---|---|
| **Augmentation (reweighting)** | 승인 건에 "승인 확률의 역수"로 가중치를 부여해 신청 모집단을 대표하도록 재가중 | 승인 확률이 관측 변수로 모형화 가능(MAR) | 미관측 요인으로 승인이 갈렸다면(MNAR) 보정 실패 |
| **Parcelling** | 거절 건에 모형 점수를 매기고, 점수 구간별로 승인 건의 부도율(에 배수 적용)을 배정해 라벨 대체 | 같은 점수면 승인·거절 집단의 위험이 (배수 조정 후) 같다 | 배수가 **자의적** — 결국 가정을 데이터로 검증할 수 없음 |
| **Fuzzy augmentation** | 거절 건을 good/bad 두 레코드로 복제하고 추정 확률을 가중치로 부여 | 추정 확률이 신뢰 가능 | 자기충족적 — 기존 모형의 편향을 그대로 재생산 |
| **Bivariate probit (Heckman 2단계)** | 승인 방정식과 부도 방정식을 동시 추정해 선택 편향을 명시적으로 모델링 | 승인에만 영향을 주고 부도엔 영향 없는 **배제 제약(exclusion restriction)** 변수 존재 | 그런 변수를 찾기가 실무적으로 매우 어려움; 분포 가정에 민감 |

**공통 한계**: 어떤 기법도 "관측되지 않은 결과"를 만들어내지 못합니다. 전부 **검증 불가능한 가정**을 추가하는 것이며, 잘못된 보정은 무보정보다 나쁠 수 있습니다.

**이 프로젝트에서 하지 않은 이유.** rejected 데이터를 보유하지 않았습니다. Lending Club rejected 데이터셋이 별도로 존재하지만 **변수 셋이 accepted와 달라**(대부분의 신용 변수 부재) 결합 자체가 또 다른 강한 가정을 요구합니다. 근거 없이 보정을 흉내내기보다, **"승인 모집단 한정 모형"임을 명시하는 것이 정직한 처리**라고 판단했습니다. SPEC도 이를 non-goal("reject inference의 실제 코드 구현 — 한계 문서화로 대체")로 명시하고 있습니다.

**향후.** 실제 심사 환경에서는 자사의 거절 이력(신청 변수 + 거절 사유)이 남으므로, ①거절 신청의 변수 분포 확보 → ②Augmentation으로 1차 보정 → ③외부 신용정보(CB)로 거절자의 실제 연체 여부를 사후 확인해 **보정의 타당성을 검증**하는 경로가 현실적입니다. 즉 reject inference는 통계 기법이기 이전에 **데이터 확보 전략**의 문제입니다.

### 10.2 기타 한계

- **표본 가정**: OOT 표본(2015)을 1년치 승인 볼륨으로 가정(손익·룰 진단 공통). 별도 확대 계수 없음 — 가장 단순·투명한 선택.
- **손익은 시뮬레이션**: 실현 손익 실측치 기반이나 재무 데이터가 아니며, 향후 금리·매크로 변화를 반영하지 않음.
- **가상 룰셋**: §7.3의 하드룰은 실무 관행 기반으로 이 프로젝트가 설계한 가상 룰이며 실제 운영 정책이 아님.
- **텍스트 검증의 범위**: 단순 빈도 매핑만 적용(정교한 NLP 미적용) — 의미론적 정보를 활용하면 결과가 달라질 여지는 있으나, 그 경우 비용 대비 효과를 별도 평가해야 함.
- **SAS tie-out**: 이식 산술은 미러로 증명했으나 SAS 실환경 실행 확인은 사용자 수행 몫.
- **배포 범위**: 로컬 단일 환경(uvicorn + streamlit). 컨테이너화·클라우드·CI는 스코프 밖(AD-8).

---

## 11. 재현 방법

```powershell
# 1. 환경
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 데이터 (gitignore 대상 — NFR5)
.venv\Scripts\python.exe pipelines\01_download.py

# 3. 파이프라인 → 아티팩트 생성 (gitignore 대상)
#    scorecard/ 모듈을 순서대로 실행 (표본설계 → 전처리 → 비닝 → 챔피언/챌린저 → 평가·등급·PSI·frame)

# 4. 서빙 + 대시보드
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
.venv\Scripts\python.exe -m streamlit run dashboard\app.py

# 5. 테스트 (221 passed)
.venv\Scripts\python.exe -m pytest
```

전 실험 시드 고정, 난수 미사용 경로 우선 — **결정론적 재현 보장**(NFR1).

---

## 12. 문서 지도

| 문서 | 내용 |
|---|---|
| [`sample-design-report-1-2.md`](implementation-artifacts/sample-design-report-1-2.md) · [`leakage-audit-1-2.md`](implementation-artifacts/leakage-audit-1-2.md) | 표본설계·누수감사 |
| [`preprocessing-report-1-3.md`](implementation-artifacts/preprocessing-report-1-3.md) · [`binning-selection-report-1-4.md`](implementation-artifacts/binning-selection-report-1-4.md) | 전처리·WOE·변수선정 |
| [`champion-scorecard-report-1-5.md`](implementation-artifacts/champion-scorecard-report-1-5.md) · [`challenger-report-1-6.md`](implementation-artifacts/challenger-report-1-6.md) | 모형 개발 |
| [`evaluation-grading-report-1-7a.md`](implementation-artifacts/evaluation-grading-report-1-7a.md) · [`psi-validation-frame-report-1-7b.md`](implementation-artifacts/psi-validation-frame-report-1-7b.md) | 평가·등급·PSI |
| [`cutoff-swapset-report-2-1.md`](implementation-artifacts/cutoff-swapset-report-2-1.md) · [`profit-cutoff-onepager-2-4.md`](implementation-artifacts/profit-cutoff-onepager-2-4.md) | 심사전략(cutoff·손익) |
| [`reason-codes-report-2-2.md`](implementation-artifacts/reason-codes-report-2-2.md) · [`p3-examples-2-3.md`](implementation-artifacts/p3-examples-2-3.md) | 사유코드·API 예시 |
| [`rule-efficiency-report-3-1.md`](implementation-artifacts/rule-efficiency-report-3-1.md) · [`text-features-report-3-2.md`](implementation-artifacts/text-features-report-3-2.md) · [`sas-replication-report-3-3.md`](implementation-artifacts/sas-replication-report-3-3.md) | 컨설턴트 킥 ②③④ |
| [`../API_SPEC.md`](../API_SPEC.md) | API 계약 (8 엔드포인트) |
| [`planning-artifacts/`](planning-artifacts/) · [`specs/`](specs/) | SPEC(CAP-1~17)·아키텍처(AD-1~9)·에픽 |
| [`implementation-artifacts/deferred-work.md`](implementation-artifacts/deferred-work.md) | 의도적으로 미룬 항목과 근거 |
