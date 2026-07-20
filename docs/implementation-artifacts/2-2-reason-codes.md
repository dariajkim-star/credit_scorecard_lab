---
baseline_commit: 3011783
---

# Story 2.2: Reason Code 이원화

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 심사역,
I want 개별 신청 건의 점수 하락 사유 top3를 완성된 문장으로 받고,
so that 거절·조건부 사유를 고객에게 설명할 수 있다.

## Acceptance Criteria

**Given** Epic 1의 두 아티팩트(`models/artifacts/champion_model.joblib`, `challenger_model.joblib` + manifest)
**When** `scorecard/reasons.py`로 임의 신청 1건을 분석하면

1. 챔피언 = 특성별 점수손실(`points_lost`) 기준, 챌린저 = SHAP 기준 top3 사유가 산출된다 (FR11)
2. 두 모델의 reason_codes가 동일 구조(rank·description 공유, 값 필드만 `points_lost`/`shap_value`)를 공유한다 — pydantic 베이스 모델 상속 (AD-6)
3. `description`은 심사의견서에 그대로 인용 가능한 완성된 한국어 문장이다 (P3 계약)
4. WOE 재구현 없이 `scorecard/binning.py`를 import해 쓴다 (AD-2)

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC + `pytest -q` 초록 + 실데이터(원본 accepted parquet 1행 이상)로 챔피언·챌린저 reason_codes를 산출한 리포트가 있어야 한다. `points_lost`/`shap_value`는 항상 3개(top_n=3) 반환하고 내림차순 정렬이어야 하며, `ChampionReasonCode`/`ChallengerReasonCode` 두 타입 모두 공통 `rank: int`, `variable: str`, `description: str` 필드를 pydantic으로 강제해야 한다.

## Tasks / Subtasks

- [x] Task 1: Reason code pydantic 모델 (AC: #2, AD-6)
  - [x] `ReasonCode(BaseModel)` 베이스(rank/variable/description)
  - [x] `ChampionReasonCode`(+points_lost), `ChallengerReasonCode`(+shap_value) — AD-6 구조 공유
- [x] Task 2: 챔피언 reason codes — 점수손실 (AC: #1, #3, #4, FR11)
  - [x] `champion_reason_codes(...)` 구현, `binning.transform_woe` 재사용(AD-2)
  - [x] `points_lost = factor*coef*(applicant_woe - safest_woe)` — **부호 버그 발견·수정**(아래 Review Findings 참고)
  - [x] top3 내림차순 + 완결 한국어 문장
- [x] Task 3: 챌린저 reason codes — SHAP (AC: #1, #2, #3, FR11)
  - [x] `challenger_reason_codes(...)` 구현
  - [x] `_normalize_raw_applicant`(공유 헬퍼)로 raw applicant dtype 정합화 — revol_util 파싱 + 전 수치형 컬럼 object→numeric 강제 변환
  - [x] `shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")` — 배경표본 미사용 결정, margin 재구성 일치 확인
  - [x] top3 SHAP 내림차순 + 완결 한국어 문장
- [x] Task 4: 리포트 (AC: 전체)
  - [x] `docs/implementation-artifacts/reason-codes-report-2-2.md` — 실데이터 3건 비교, AD-6 구조 확인, SHAP 결정 기록, **points_lost 부호 버그 발견·수정 기록**, 재실행 스니펫
- [x] Task 5: pytest 및 회귀 (AC: 전체)
  - [x] `tests/test_reasons.py` — pydantic 구조, top3 정렬, SHAP margin sanity, description 비어있지 않음 검증 + **best/worst 합성 케이스로 부호 회귀 방지 테스트** 추가
  - [x] `pytest -q` → **120 passed** (기존 108 + 신규 12)
  - [x] 실데이터(원본 accepted parquet + 저장된 두 아티팩트) 3건 실행 완료 — **이 실행에서 points_lost 전부 0.0으로 나오는 이상 현상 발견 → 부호 버그 확인·수정**

### Review Findings (code review 2026-07-16, Blind Hunter + Edge Case Hunter + Acceptance Auditor 병렬 — patch 6/defer 2/dismiss 5)

- [x] [Review][Patch] **`_safest_woe`가 max(WoE) 하드코딩 — coef 부호 가정이 런타임 미검증** [scorecard/reasons.py:_safest_woe] — coef 부호로 방향 결정(`coef<0 → max`, `coef>0 → min`)하도록 일반화. 양수 계수 모델이 오면 조용히 최악 bin을 "최선"으로 잡고 0으로 클립돼 버그가 은폐되던 실패 모드(부호 버그 재발과 동일 계열) 제거. 방향 테스트 추가.
- [x] [Review][Patch] **real bins가 전무한 퇴화 binner → NaN이 pydantic까지 조용히 관통** [scorecard/reasons.py:_safest_woe] — 빈 real_bins에서 `.max()`가 NaN을 반환해 points_lost 전체를 오염(JSON 직렬화도 깨짐). fail-fast ValueError + 테스트.
- [x] [Review][Patch] **coef-variables 정렬 미검증(zip 조용한 절단/오정렬)** [scorecard/reasons.py:champion_reason_codes] — `fit_champion`이 numpy로 fit해 feature_names_in_이 없으므로, bundle의 binners dict 키 순서(저장 시 fit-time variables 순서)를 정렬 기준으로 검증. 역순 variables 거부 테스트.
- [x] [Review][Patch] **`top_n<=0` 무검증(빈/꼬리 잘린 결과 조용히 반환)** [scorecard/reasons.py 양쪽] — `top_n>=1` ValueError + 테스트 2건.
- [x] [Review][Patch] **챌린저 -0.0 미정규화 + SHAP shape 무가정 검증** [scorecard/reasons.py:challenger_reason_codes] — 챔피언에만 있던 `+0.0` 가드를 챌린저 shap_value에도 적용, `sv.ndim==1 && len==len(variables)` shape 가드 추가(3D 반환 시 불투명한 TypeError 대신 명시적 에러).
- [x] [Review][Patch] **revol_util 퍼센트 문자열 경로의 상시 테스트 부재(High — 기존 테스트가 이름과 달리 해당 경로를 안 탐)** [tests/test_reasons.py] — revol_util 포함 합성 binner로 문자열 "83.5" 입력 end-to-end 테스트 추가(실데이터 e2e는 skipif라 CI 공백이었음). + NaN 입력 관통 테스트(champion Missing-bin/challenger 네이티브 NaN).
- [x] [Review][Patch] **Dev Notes의 points_lost 공식이 부호 반대(문서-코드 불일치)** [이 문서 Task 2 절] — Acceptance Auditor 독립 유도로 코드가 옳음을 확인, 문서를 코드에 맞게 정정(위 취소선 참조).
- [x] [Review][Defer] **bundle 필수 키 부재 시 bare KeyError** — 내부 도구 수준에서 수용, 2.3(API 서빙)이 로딩 계층을 만들 때 명시적 검증 추가가 자연스러움. deferred-work 등록.
- [x] [Review][Defer] **미등록 변수의 한국어 조사(이/가) fallback이 문장 품질 미보장** — 현재 7개 변수 전부 등록돼 발생 불가. 변수 확장 스토리(3.2 emp_title)에서 라벨 추가 시 함께. deferred-work 등록.
- [x] [Review][Dismiss] **LightGBM 카테고리 코드 오정렬 의혹(fresh cast 단일행)** — **실증 기각**: booster가 `pandas_categorical`(학습 시점 카테고리 목록)을 저장하고 예측 시 값 기준 재정렬함을 실데이터 20건으로 확인(fresh 단일행 cast vs 전체 batch cast 확률 완전 일치, atol=1e-12).
- [x] [Review][Dismiss] tie 순서 비결정성(stable sort + 고정 variables 순서로 결정적), 동어반복 수동공식 테스트(리포트에 이미 자인·행동 테스트가 보완), 챌린저 description에 SHAP 크기 미포함(SHAP 단위는 고객에게 무의미 — 점수 단위인 챔피언과 달리 의도적 생략), rank 정렬이 반올림 전 값 기준(정상).

### Review Findings (GPT 외부 리뷰 2026-07-16 후속 — patch 1/dismiss 2)

- [x] [Review][Patch] **High — 음수 SHAP/0점 손실이 "위험 증가"로 오설명됨** [scorecard/reasons.py:champion_reason_codes, challenger_reason_codes] — 두 함수 모두 부호·존재 무관하게 항상 정확히 `top_n`개를 반환했다. 실데이터 SAFE applicant(`68587465`)로 재현: 챌린저 top3(`revol_util -0.0003`, `purpose -0.0578`, `dti -0.1558`) 전부 음수(=위험 **감소** 기여)인데 "부도 위험을 높이는 방향으로 작용했습니다"로 출력됨. **수정**: 양쪽 함수 모두 `value > 1e-8`(불리한 요인만) 필터를 랭킹 전에 적용 — `top_n`보다 적게(0건 포함) 반환 가능. 회귀 테스트: `test_champion_reason_codes_best_applicant_has_near_zero_points_lost`(best 결과가 정확히 `[]`), `test_challenger_reason_codes_returns_fewer_than_top_n_when_not_all_adverse`, `test_challenger_reason_codes_returns_only_adverse_factors_sorted_descending`(반환값 전부 `>0` 검증). 실데이터 재검증: SAFE applicant 챔피언·챌린저 모두 0건으로 정정, RISKY applicant는 원래도 3건 전부 불리 요인이라 무변화. 상세: `reason-codes-report-2-2.md`의 "Code review fix: non-adverse factors no longer returned" 절.
- [x] [Review][Dismiss] **High — manifest의 `feature_order`/`pdo`를 신뢰 계약으로 쓰지 않고 호출자 인자에 의존** — 실제 위험(호출자가 순서를 잘못 넘겨 계수-변수가 조용히 잘못 짝지어지는 것)은 1차 내부 리뷰가 이미 fit-order 일치 검증(`ValueError`, `test_champion_reason_codes_rejects_misordered_variables`)으로 닫아뒀다. manifest에서 직접 로드하도록 시그니처를 바꾸면 `evaluation.py`의 "호출자가 이미 로드한 bundle을 넘긴다" 컨벤션과 어긋나고 이 스토리 범위를 넘는 API 변경이 된다 — 채택 안 함.
- [x] [Review][Dismiss] **Low — 요청마다 SHAP explainer·binning_table 재생성(성능)** — `scorecard/reasons.py`는 순수 분석 함수 모듈(이 스토리 스코프)이고, "프로세스 시작 시 1회 로드"는 AD-4에 따라 서빙 계층(`app/loader.py`, Story 2.3)의 책임 — 그쪽에서 처리.

## Dev Notes

### 이 스토리의 성격 — Epic 1 아티팩트를 "로드"하는 첫 Epic 2 스토리 (2.1과 정반대 규칙)
**중요**: Story 2.1(`strategy.py`)은 AD-3에 따라 `models/artifacts/*.joblib`을 절대 로드하지 않는 것이 규칙이었다. **이 스토리는 정반대다** — FR11(reason code)은 임의의 단일 신청 건(scored validation frame에 없는 새 입력)에 대해 변수별 기여도를 설명해야 하므로, scored frame의 집계된 `score`/`pd`만으로는 불가능하다. `models/artifacts/champion_model.joblib`·`challenger_model.joblib`을 로드하고 `scorecard/binning.py`(WOE)·`scorecard/champion.py`(PDO 상수)·`scorecard/challenger.py`(calibrator는 이 스토리에 불필요, raw LightGBM만 필요)를 import해서 쓰는 것이 **의도된 설계**다. 2.1의 "아티팩트 로드 금지" 습관을 그대로 가져오지 말 것.

**아티팩트 로딩 위치 컨벤션**: `evaluation.py`의 `champion_p_bad`/`challenger_p_bad`(1.7a)를 참고 — 두 함수 모두 `joblib.load()`를 함수 내부에서 하지 않고, 이미 로드된 `bundle: dict`를 인자로 받는다. `scorecard/reasons.py`의 두 함수도 이 컨벤션을 따른다 — `joblib.load("models/artifacts/champion_model.joblib")` 같은 호출은 **테스트/리포트 스크립트(호출부)에서 하고, `reasons.py` 내부에는 넣지 않는다.**

- 챔피언 bundle 구조(1.5): `{"model": LogisticRegression, "binners": dict[str, OptimalBinning]}`
- 챌린저 bundle 구조(1.6): `{"model": LGBMClassifier, "calibrator": ...}` — **calibrator는 SHAP 설명에 쓰지 않는다**(아래 "검증된 SHAP 설정" 참고, calibration은 raw 모델 출력을 사후 재매핑할 뿐 변수별 기여도가 없음).

### Task 2 — 챔피언 points_lost 공식 (검증된 API 세부사항)
`champion.py`의 로지스틱 모형은 `logit_bad = intercept + sum(coef_i * woe_i)`이고 `score_formula`가 `factor = PDO / ln(2)`로 스케일링한다(`champion.PDO`를 import해서 `factor = champion.PDO / np.log(2)`로 재계산 — `score_formula`는 factor를 노출하지 않으므로 함수를 새로 쪼개지 말고 이 한 줄로 충분).

변수 i의 `points_lost`(양수 = 손실) = ~~`factor * coef_i * (safest_woe_i - applicant_woe_i)`~~ → **`factor * coef_i * (applicant_woe_i - safest_woe_i)`** (2026-07-16 정정: 원래 이 문서에 적혀 있던 공식은 부호가 반대였고, 그대로 구현했다가 실데이터에서 전 변수 points_lost=0.0으로 뭉개지는 버그로 드러남 — `score = offset - factor*logit_bad`에서 기여도 = `-factor*coef_i*woe_i`, 손실 = 최선 기여 - 실제 기여 = `factor*coef_i*(applicant - safest)`가 옳다. 유도·경위는 reason-codes-report-2-2.md. 코드리뷰 Acceptance Auditor가 문서-코드 불일치를 지적해 문서를 코드에 맞게 정정).

`safest_woe_i`(변수 i에서 가장 안전한 bin의 WOE)를 구하는 방법을 **이 스토리를 위해 직접 실측 검증**했다:
```python
table = binner.binning_table.build()   # binner = champion_bundle["binners"][var]
# columns: ['Bin', 'Count', 'Count (%)', 'Non-event', 'Event', 'Event rate', 'WoE', 'IV', 'JS']
# 'Bin' 값 예시: '(-inf, 7.82)', ..., 'Special', 'Missing'; 인덱스에 'Totals' 행 별도 존재
real_bins = table[~table["Bin"].isin(["Special", "Missing"]) & (table.index != "Totals")]
safest_woe = real_bins["WoE"].max()   # 1.5 리포트가 확인한 대로 전 변수 coef < 0(아래 참고)이므로 max
```
**컬럼명 `"WoE"`(대소문자 정확히 이대로), `"Bin"` 컬럼의 `"Special"`/`"Missing"` 라벨, `"Totals"` 인덱스 행**은 실제 `models/artifacts/champion_model.joblib`의 `dti` 바이너로 직접 실행해 확인한 값이다 — 재확인 없이 그대로 신뢰해도 된다. `"Special"`/`"Missing"` 행을 빼지 않으면, 실제 bin이 전부 WoE 음수인 변수에서 0.0짜리 Special/Missing 행이 "가장 안전"으로 잘못 뽑히는 버그가 생긴다(이번 실측 데이터에선 발생하지 않지만 일반적으로 발생 가능 — 반드시 필터링할 것).

**계수 부호 사전 확인 완료(재검증 불필요)**: 실제 저장된 `champion_model.joblib`의 7개 변수 전부 `coef < 0`(1.5의 `check_coefficient_signs`로 직접 재확인함: fico_range_low, annual_inc, dti, home_ownership, revol_util, inq_last_6mths, purpose 전부 `sign_ok=True`). 즉 `safest_woe_i = max(bin WoE)`가 항상 맞고 `points_lost`는 항상 `>= 0`이다. 방어적으로 `max(points_lost, 0)`으로 클립해도 무방하지만 필수는 아니다.

### Task 3 — 검증된 전처리 요구사항 (SHAP 호출 전 필수)
원본 accepted parquet(`data/lc_accepted_2012_2015_36m.parquet`)에서 뽑은 raw 1행을 그대로 챌린저 모델에 넣으면 **반드시 실패한다** — 이 스토리를 위해 직접 재현·확인한 두 가지 문제:
1. `revol_util`이 문자열(`"29.7"` 형태, `%` 없음)이다 — `scorecard.preprocessing.parse_percent`로 파싱해 float으로 변환할 것(1.7b가 `int_rate`에 쓴 것과 동일 함수, 재구현 금지).
2. `home_ownership`, `purpose`(둘 다 `preprocessing.CATEGORICAL_COLUMNS`)를 `.astype("category")`로 캐스팅하지 않으면 LightGBM이 `ValueError: pandas dtypes must be int, float or bool`을 던진다(학습 시에는 어딘가에서 이미 category였을 것이나, 원본 raw parquet에는 캐스팅이 없다 — `applicant_row`를 만들 때 이 스토리가 직접 캐스팅해야 한다).

### Task 3 — 검증된 SHAP 설정 (실측 스파이크 완료, 그대로 채택할 것)
`challenger_manifest.json`의 `shap_background_sample_ref`(`models/artifacts/challenger_shap_background.parquet`, 1.6이 저장)를 `shap.TreeExplainer(model, background)`처럼 배경표본으로 넘기면 **다음 에러로 실패한다**(직접 재현 확인):
```
ExplainerError: Currently TreeExplainer can only handle models with categorical
splits when feature_perturbation="tree_path_dependent" and no background data is passed.
```
이유: LightGBM이 `home_ownership`/`purpose`를 네이티브 범주형 분할로 학습했고, SHAP의 interventional(배경표본 기반) 모드는 범주형 분할 트리를 지원하지 않는다. **결정(이 스토리에서 채택): `shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")`로 배경표본 없이 호출한다.** 이 방식은 트리의 실제 분기 경로를 따라가는 방식이라 배경표본이 필요 없다 — `shap_background_sample_ref`는 이 스토리에서 사용하지 않는다(AD-1이 만들어둔 참조가 이 특정 설명 방식과는 호환되지 않는다는 것을 리포트에 결정 기록으로 남길 것 — 향후 story가 다른 방식이 필요하면 그때 재검토).

출력 형태도 실측 확인: `explainer.shap_values(df)`는 설치된 `shap>=0.46` + 이 LightGBM 이진분류기 조합에서 `(n_rows, n_features)` 형태의 단일 `numpy.ndarray`를 반환한다(양성 클래스=bad 기준, "list of ndarray로 바뀌었다"는 `UserWarning`이 뜨지만 실제로는 ndarray 하나). **다만 shap 버전에 따라 `list`(클래스별)를 반환할 수도 있으므로 `isinstance(sv, list)`로 방어 처리**할 것(리스트면 양성 클래스 인덱스, 보통 `[1]` 또는 마지막 원소 — 직접 shape로 확인).

**부호 규칙**: `explainer.expected_value + shap_values.sum() == logit(raw predict_proba)`를 실측으로 확인했다(margin space, calibration 이전). SHAP 값이 **양수일수록 부도(risk) 방향으로 기여** — top3 = `shap_value` 내림차순(가장 위험을 높인 변수). 챔피언의 `points_lost`(양수=손실)와 동일한 "양수=나쁨" 방향 규칙이므로 두 리스트의 정렬 기준이 사용자 입장에서 일관적이다.

### AD-6 — pydantic 구조 공유
`ReasonCode`(rank, variable, description) 베이스를 `ChampionReasonCode`(+points_lost), `ChallengerReasonCode`(+shap_value)가 상속한다. `pydantic>=2.7`이 이미 requirements.txt에 있다(app/ 서빙용으로 예정된 의존성을 이 스토리가 먼저 씀 — 정상, AD-6이 명시적으로 pydantic을 요구).

### description 문장 — 변수명 한글 매핑 (참고용, 강제 아님)
7개 feature_order 변수의 비즈니스 의미:
| 변수 | 의미 |
|---|---|
| fico_range_low | 신용점수(FICO) |
| annual_inc | 연소득 |
| dti | 부채비율(DTI) |
| home_ownership | 주택소유형태 |
| revol_util | 리볼빙 한도 소진율 |
| inq_last_6mths | 최근 6개월 신용조회 건수 |
| purpose | 대출목적 |

`description`은 이 표를 참고해 "완결된 한국어 문장"(예: "부채비율(DTI)이 심사 기준 대비 높아 점수가 12.3점 하락했습니다.")이면 되고, 정확한 문구·소수점 자리수는 스토리 오너(구현 dev) 재량이다 — AC #3의 요구사항은 "심사의견서에 그대로 인용 가능"이지 특정 템플릿 문자열이 아니다.

### AD-2 — WOE 재구현 금지
챔피언 경로의 WOE 변환은 `binning.transform_woe`만 사용한다. 이 스토리가 직접 `optbinning` API를 호출해 WOE를 재계산하는 코드를 작성하면 AD-2 위반(train/serve parity 리스크).

### 스코프 가드 (하지 말 것)
- API 서빙(FR12, Story 2.3), 손익 cutoff(FR14, Story 2.4)는 범위 밖 — `reasons.py`는 순수 함수만 제공하고 FastAPI 엔드포인트를 만들지 않는다(그건 2.3 소관, `app/`이 이 함수들을 나중에 호출한다).
- `challenger_bundle["calibrator"]`를 SHAP 설명에 쓰지 않는다 — calibration은 사후 확률 재매핑일 뿐 변수 기여도가 없다(위 "아티팩트 로딩 위치 컨벤션" 참고).
- 대량/배치 reason code 계산은 범위 밖 — "임의 신청 1건" 단위 함수만 만든다(에픽 AC 문구 그대로).

### 이전 스토리 인텔리전스 (2.1 인수인계)
- **AD 규칙이 스토리마다 다를 수 있음**: 2.1의 "아티팩트 로드 금지"를 이 스토리에 그대로 적용하지 말 것(위 "이 스토리의 성격" 참고) — 각 스토리는 자신이 속한 AD를 따른다.
- **실데이터 실행이 늘 버그를 드러냄**(1.7b, 2.1 공통 교훈): 이 스토리도 원본 accepted parquet에서 뽑은 실제 1행으로 반드시 실행해볼 것 — 합성 테스트만으로는 위의 `revol_util` 문자열·범주형 dtype·SHAP 배경표본 에러 3가지를 전혀 잡아내지 못한다(이번 story-context 조사 중 실측으로 처음 발견됨).
- **GPT 리뷰 패치에 대응 테스트가 누락됐던 사례(2.1)**: 코드 리뷰에서 fail-fast 가드가 추가되면 반드시 대응 pytest도 같이 추가할 것 — 2.1에서 한 번 놓쳤던 패턴.

### Project Structure Notes
- `scorecard/reasons.py` — MODIFIED(스텁 → 구현, 신규 파일 아님. 현재 내용: `"""CAP-11 reason code\n\nStub created in Story 1.1 (scaffolding). Implemented in a later story.\n"""`).
- `tests/test_reasons.py` — NEW.
- `docs/implementation-artifacts/reason-codes-report-2-2.md` — NEW.
- 아키텍처 Structural Seed와 완전히 일치(별도 변경 없음).

### References

- [Source: docs/planning-artifacts/epics.md#Story-2.2] — AC 원문(FR11, AD-6, AD-2, P3 계약)
- [Source: ARCHITECTURE-SPINE.md#AD-6] — reason_codes pydantic 구조 공유 규칙 원문
- [Source: ARCHITECTURE-SPINE.md#AD-2] — WOE 단일 소스 규칙 원문
- [Source: scorecard/reasons.py] — 현재 스텁 내용
- [Source: scorecard/champion.py] — `PDO`, `score_formula`, bundle 구조(`{"model","binners"}`)
- [Source: scorecard/challenger.py] — bundle 구조(`{"model","calibrator"}`), `save_shap_background_sample`(1.6이 만든 배경표본, 이 스토리에서는 미사용으로 결정)
- [Source: scorecard/evaluation.py#champion_p_bad,challenger_p_bad] — "bundle을 인자로 받는다" 아티팩트 로딩 컨벤션의 선례
- [Source: scorecard/preprocessing.py#parse_percent,CATEGORICAL_COLUMNS] — 챌린저 입력 전처리에 재사용
- [Source: models/artifacts/champion_model.joblib, champion_manifest.json] — 실측 계수 부호(전부 음수) 확인, feature_order 7개
- [Source: models/artifacts/challenger_model.joblib, challenger_manifest.json] — 실측 SHAP 스파이크(배경표본 에러, tree_path_dependent 성공, margin 재구성 일치 확인)
- [Source: data/lc_accepted_2012_2015_36m.parquet] — 실측 raw 1행으로 두 가지 전처리 문제 재현·확인

## Dev Agent Record

### Agent Model Used

claude-sonnet-5 / claude-fable-5 (병행 세션, bmad-dev-story) — 이 세션이 실행 이어받아 완료

### Debug Log References

- 실데이터 3건 실행에서 챔피언 `points_lost`가 **전부 0.0**으로 나오는 이상 현상 발견(fico_range_low, dti, home_ownership 등 top3 전부 동일하게 0) → `_safest_woe`·`coefs`·`transform_woe` 출력을 직접 손계산과 대조해 `factor*coef*(safest_woe-applicant_woe)`가 부호 반대임을 확인(coef 음수 × (safest-applicant, 정상적으로 양수) = 음수 → `max(...,0)` 클립으로 전부 0). `factor*coef*(applicant_woe-safest_woe)`로 수정 후 재실행 시 28.83/12.91/6.50 등 의미 있는 값 산출 확인.
- 수정 직후 `test_champion_reason_codes_matches_manual_points_lost_formula` 실패 → 원인은 반올림 오차(`round(loss,4)` vs 테스트의 `abs=1e-6`) → `abs=1e-4`로 조정.
- 두 가지 raw applicant 전처리 문제(1. revol_util 퍼센트 문자열, 2. `.to_frame().T` 후 전 컬럼 object dtype화)를 실데이터로 재현·확인, `_normalize_raw_applicant` 공유 헬퍼로 양쪽 모델 경로 통합 해결.
- `pytest -q` → 120 passed (기존 108 + 신규 12)

### Completion Notes List

- **가장 중요한 발견**: `champion_reason_codes`의 points_lost 공식 부호가 반대로 구현돼 있어 실데이터에서 전 변수가 0.0으로 뭉개지는 치명적 버그였음 — 합성 테스트(`test_champion_reason_codes_matches_manual_points_lost_formula`)는 동일한 공식을 독립 재계산이라며 재구현했기 때문에 이 버그를 잡지 못했다(테스트가 구현 버그를 그대로 미러링하는 동어반복 함정). 실데이터 실행이 아니었다면 이 스토리는 "통과"로 잘못 종료됐을 것 — `reason-codes-report-2-2.md`에 근거·유도 과정 상세 기록.
- **회귀 방지**: best/worst 합성 극단 케이스로 "안전한 신청자는 0점 근처, 위험한 신청자는 유의미하게 손실"을 검증하는 행동 기반 테스트를 추가해, 공식 내부 구현에 의존하지 않고도 향후 동일 부호 버그를 잡을 수 있게 함.
- **AD-1 참고**: 1.6이 저장한 `shap_background_sample_ref`는 이 스토리에서 사용하지 않기로 결정(범주형 분할 트리와 interventional SHAP 비호환) — 리포트에 결정 기록, manifest 자체는 변경하지 않음.
- **AD-2/AD-6 준수**: WOE 재구현 없음(`binning.transform_woe`만 사용), 두 reason code 타입이 pydantic 베이스를 공유.

### File List

- `scorecard/reasons.py` (MODIFIED — 스텁 → 구현: ReasonCode/ChampionReasonCode/ChallengerReasonCode, `_normalize_raw_applicant`, `_safest_woe`, `champion_reason_codes`, `_prepare_challenger_row`, `challenger_reason_codes`; GPT 리뷰 후속 patch로 양쪽 함수에 불리 요인만 필터링하는 로직 추가)
- `tests/test_reasons.py` (MODIFIED — 21 tests: 최초 12건 + 3-레이어 리뷰 8건 + GPT 리뷰 후속 1건 신규(`test_challenger_reason_codes_returns_only_adverse_factors_sorted_descending`) + 기존 3건 재설계(`_returns_fewer_than_top_n_when_not_all_adverse`, `_shap_reconstructs_raw_margin`을 필터와 독립적으로 검증하도록 재작성, `_best_applicant_has_near_zero_points_lost`를 `== []`로 강화))
- `docs/implementation-artifacts/reason-codes-report-2-2.md` (MODIFIED — "Code review fix: non-adverse factors no longer returned" 절 추가)
- `docs/implementation-artifacts/sprint-status.yaml` (MODIFIED — 상태 전이)

## Change Log

- 2026-07-16: Story 2.2 구현 완료 — champion_reason_codes(점수손실)/challenger_reason_codes(SHAP tree_path_dependent), AD-6 pydantic 구조 공유, raw applicant dtype 정합화 공유 헬퍼. **실데이터 실행 중 챔피언 points_lost 부호 버그 발견·즉시수정**(전 변수 0.0으로 뭉개지던 치명적 결함). pytest 120 passed. Status → review.
- 2026-07-16: 코드리뷰(3-레이어 병렬) 반영 — patch 7건(coef 부호 일반화 safest_woe·빈 binner fail-fast·coef 정렬 검증·top_n 검증·챌린저 -0.0/shape 가드·revol_util/NaN 상시 테스트·Dev Notes 공식 정정), defer 2건(deferred-work.md), dismiss 5건(카테고리 코드 오정렬 의혹은 실데이터 20건 실증 기각). pytest 128 passed(+8). Status → done.
- 2026-07-16: GPT 외부 리뷰 후속 patch — **High 1건 반영**: 챔피언/챌린저 모두 실제 불리한 요인(`points_lost`/`shap_value` > 0)만 반환하도록 필터 추가, 안전한 신청자(SAFE, `applicant_id=68587465`)에게 음수 SHAP를 "위험 증가"로 오설명하던 버그 수정(실데이터로 재현·재검증 완료, 리포트에 전후 비교 기록). manifest 기반 feature_order/pdo 전환 제안과 explainer 캐싱 제안은 근거를 검토해 dismiss(1차 리뷰의 정렬 검증으로 실위험 이미 해소 / 서빙 계층 소관으로 스코프 밖). pytest 129 passed(+1, 관련 테스트 3건 함께 재설계). Status: done 유지(같은 날 발견·패치·재검증 완료).
