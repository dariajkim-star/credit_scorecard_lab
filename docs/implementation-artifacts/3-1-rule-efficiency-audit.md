---
baseline_commit: 300d6e3
---

# Story 3.1: 룰 효율성 진단 (컨설턴트 킥②)

Status: done

## Story

As a 룰 기반 의사결정 시스템을 고도화하는 컨설턴트,
I want 기존 하드룰들이 실제로 얼마나 효율적인지 데이터로 진단하고,
so that "유지/재검토" 근거를 가진 룰 정비 제안을 할 수 있다.

## Acceptance Criteria

**Given** validation frame과 실무 관행(DTI·연체이력·조회수)에 근거해 설계한 가상 하드룰셋 3개 이상
**When** `scorecard/rule_efficiency.py`로 룰별 배제집단을 분석하면

1. 룰별 배제 건수·배제집단 부도율·모집단 대비 비율·기회손실 추정이 산출된다 (FR15)
2. verdict(유지/재검토 권장)가 규칙 기반으로 산출되고 근거가 명시된다 (AD-7, NFR7)
3. `/v1/rules/efficiency` 엔드포인트가 API_SPEC.md §8 스키마로 동작한다 (AD-5 — 기존 서빙에 추가만)
4. 룰 정비 제안 리포트(md)가 산출된다

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC + `pytest -q` 초록(기존 189 + 신규) + 실데이터 실행 + **라이브 uvicorn 실증**(2.3~2.5 DoD 계승 — TestClient만으로 끝내지 않음, 실제 HTTP로 `/v1/rules/efficiency` 호출). verdict는 순수 규칙 함수(그리드·비율·상관 임계)여야 하고 LLM 호출이 없어야 한다(AD-7).

## Tasks / Subtasks

- [x] Task 1: 룰 입력 데이터 갭 해소 — raw parquet 조인 (AC: #1, 전제)
  - [x] **핵심 갭(2.4와 동형)**: 룰 조건 변수(`dti`, `delinq_2yrs`, `inq_last_6mths`)와 기회손실 계산용 `loan_amnt`가 **AD-3 scored validation frame에 없다**(프레임 컬럼은 `applicant_id/vintage/model_type/score/pd/grade/bad_flag/int_rate/recoveries/total_pymnt`뿐 — `scorecard/evaluation.py:SCORED_FRAME_COLUMNS` 확인). raw `lc_accepted_2012_2015_36m.parquet`에 전부 존재함(실측 확인: dti/delinq_2yrs/inq_last_6mths/loan_amnt True).
  - [x] `load_rule_frame(frame, raw_parquet_path) -> pd.DataFrame` — **2.4의 `profit.load_rule_frame` 패턴을 그대로 재사용**(import 검토 또는 동형 구현): `applicant_id`==`id`로 left join, `validate="many_to_one"`, 미매치 시 fail-fast ValueError. 조인 컬럼 = `["id", "dti", "delinq_2yrs", "inq_last_6mths", "loan_amnt"]`. **AD-3 비위반 판단 동일**(frame 기존 컬럼 재계산·수정 없음, 룰 입력 컬럼만 augment) — 근거를 docstring·리포트에 기록.
  - [x] `int_rate`/`total_pymnt`/`recoveries`는 이미 프레임에 있으므로 **재조인 금지**(중복). loan_amnt만 profit과 공유되는 조인 컬럼.
- [x] Task 2: 가상 하드룰셋 정의 (AC: #1, 오픈퀘스천)
  - [x] **오픈퀘스천(반드시 결정·기록)**: 3개 이상 하드룰의 조건·임계를 스토리오너가 확정하고 실무 근거를 명시. 권장 세트(실무 관행 + 프레임/raw에 실재하는 변수):
    - `DTI_GT_40`: `dti > 40` 거절 (과다부채 관행 임계)
    - `INQ_GE_3`: `inq_last_6mths >= 3` 거절 (신용 갈증 신호)
    - `DELINQ_GE_1`: `delinq_2yrs >= 1` 거절 (최근 연체 이력)
    - (선택) `PUB_REC_GE_1`: raw `pub_rec >= 1` — 필요 시 추가(raw에 존재)
  - [x] 룰은 **선언적 구조**로(예: `RULE_SET: list[Rule]`, 각 Rule = rule_id/description/predicate). 하드코딩 조건식을 함수 본문에 흩뿌리지 말 것 — 리뷰·확장·문서화 용이성. `dti`/`inq`/`delinq`는 raw에 결측 가능성 있으니 predicate에서 NaN 처리 방침 결정(권장: NaN은 "룰 미해당=배제 안 함", 근거 기록 — 보수적 배제는 기회손실을 과대추정).
- [x] Task 3: 룰별 배제집단 진단 지표 (AC: #1, #2, FR15)
  - [x] `rule_efficiency(rule_frame, model_type, current_cutoff, vintage=OOT_VINTAGE) -> list[dict]` — 룰별로:
    - `excluded_count`: 룰 조건 충족(배제) 건수
    - `excluded_bad_rate`: 배제집단의 `bad_flag` 평균 (배제 0건이면 NaN, 0.0 아님 — 2.4/2.1 NaN-not-0 관례)
    - `population_bad_rate`: 전체 모집단 부도율 (분모 고정)
    - `opportunity_loss_est`: **기회손실 = 배제됐지만 실제로 우량이었던(bad_flag=0) 대출들의 실현손익 합의 추정**. 권장 정의(스토리오너 결정·기록): `profit.realized_profit(loan_amnt, total_pymnt, recoveries)`를 배제-우량 집단에 적용해 합산(음수 방어: 우량이라도 손실 대출이면 기회손실에서 제외할지 결정 — 권장: 양수 실현손익만 합산해 "놓친 이익"으로 해석). **profit.py의 realized_profit을 재사용**(재구현 금지, AD-2 정신).
  - [x] **verdict 규칙(AD-7 순수 함수)**: 두 신호의 조합으로 산출하고 근거 문자열을 함께 반환:
    - ① **판별력**: `excluded_bad_rate / population_bad_rate` 배수 (≥1.5 등 임계 → 배제집단이 실제로 더 위험 = 유지 근거)
    - ② **모형과의 중복도**: 배제집단 중 이미 `score < current_cutoff`(모형이 이미 거절)인 비율. 높으면(예 ≥0.7) "모형 점수와 중복, 룰의 한계 기여 미미 = 재검토". API_SPEC §8 예시 verdict 문구("유지 권장 — 배제집단 부도율이 모집단 대비 1.75배", "재검토 권장 — 모형 점수와 판별력 중복, 배제 효과 미미")를 그대로 톤 매칭.
    - 임계값(배수·중복도)은 상수로 노출하고 근거 주석. **verdict는 결정론적 규칙 조합** — LLM/외부 호출 금지(AD-7).
- [x] Task 4: `/v1/rules/efficiency` 엔드포인트 (AC: #3, AD-5, AD-9)
  - [x] 응답: API_SPEC §8 스키마 그대로 — `{"rules": [{rule_id, description, excluded_count, excluded_bad_rate, population_bad_rate, opportunity_loss_est, verdict}, ...]}`. `app/schemas.py`에 `RuleEfficiency`/`RuleEfficiencyResponse` 추가(NaN→null 방어, 2.3/2.4 관례).
  - [x] **GET 엔드포인트**(§8이 GET). `?model=champion|challenger`(기본 champion) 쿼리 — cutoff 중복도 계산이 model_type별 score에 의존하므로 모델 선택 필요(§8 예시엔 없지만 두 모델 점수 스케일이 달라 필요, 추가만 = AD-5 위반 아님 — 근거 기록). `_require_loaded()` 게이트.
  - [x] **`app/`은 조립만**(AD-9): `rule_efficiency.py`가 계산 소유. startup 시 profit_base_curves처럼 rule_frame을 1회 조인해두고(또는 profit_frame에 loan_amnt가 이미 있으니 거기에 dti/delinq/inq만 추가 조인), 요청 시 `rule_efficiency()` 호출. current_cutoff는 `loader.CURRENT_CUTOFF`(546.0) 재사용.
  - [x] NaN 가드: `excluded_bad_rate`가 NaN(배제 0건)이면 응답 null + verdict는 "배제 0건 — 진단 불가/무의미" 류로 명시.
- [x] Task 5: 룰 정비 제안 리포트 (AC: #4)
  - [x] `docs/implementation-artifacts/rule-efficiency-report-3-1.md` — 실데이터로 산출한 룰별 표(배제건수/부도율/배수/기회손실/verdict) + "각 룰을 유지/재검토해야 하는 이유"를 비전문가도 읽을 수 있는 문장으로. 컨설팅 산출물이므로 **가정 투명 명시**(가상 룰셋이라는 점, 기회손실 정의, OOT 표본=모집단 가정). MDD 편입 가능한 형태(3.4 대비).
- [x] Task 6: pytest + 실증 (AC: 전체)
  - [x] `tests/test_rule_efficiency.py` — 룰 predicate 정확성(경계값 dti=40 배타/포함 명시), excluded_bad_rate NaN(배제 0건) 케이스, verdict 규칙 분기(고배수→유지, 고중복→재검토) 행동 테스트, opportunity_loss 부호·재사용 검증, load_rule_frame 미매치 fail-fast.
  - [x] `tests/test_app.py`에 `/v1/rules/efficiency` 엔드포인트 테스트 추가 — §8 스키마 준수, model 쿼리, NaN→null.
  - [x] `pytest -q` 전체 통과(기존 189 + 신규).
  - [x] 실데이터 조인 실행 + 라이브 uvicorn으로 `/v1/rules/efficiency` 실제 HTTP 호출 실증(챔피언·챌린저 양쪽, verdict가 상식적인지 — 예: DTI 룰이 실제로 배제집단 부도율을 높이는지).

### Review Findings (2026-07-16, 3-레이어 리뷰: Blind/Edge/Auditor)

- [x] [Review][Patch] valid model인데 대상 rows 없음 → `rule_efficiency`의 ValueError가 500으로 새어 §0 에러계약 위반. 엔드포인트에서 잡아 적절 처리(현재 실데이터엔 두 모델·2015 다 있으나 방어) [app/main.py] (blind, Med)
- [x] [Review][Patch] `STORE.rule_frame`가 None일 때 subscript 500 — startup try/except가 loaded=False로 degrade시키므로 정상경로는 안전하나, 방어적 명시 가드 추가 [app/main.py] (blind, Med)
- [x] [Review][Patch] unmatched-join 검사가 join 키(`id`)가 아닌 RULE_INPUT_COLUMNS 전체 NaN을 봄 — 매치됐지만 전 컬럼 결측인 행을 오탐(startup 크래시)하거나 미탐 가능. `merged["id"].isna()`로 교체(정확한 신호) [scorecard/rule_efficiency.py:load_rule_frame] (blind+edge, Med)
- [x] [Review][Patch] `population_bad_rate==0`이면 verdict가 "nan배" 리터럴 출력 — 실데이터 미발생이나 저비용 가드(다른 문구로) [scorecard/rule_efficiency.py:_verdict] (blind+edge+auditor, Low)
- [x] [Review][Patch] API_SPEC §8을 실제 응답에 맞춰 갱신 — 추가된 `assumptions` 필드·`?model=` 쿼리를 §8에 명시(AD-5 스펙 정합, 지금은 문서화된 확장이지만 스펙 본문 미반영) [API_SPEC.md] (auditor, Low)
- [x] [Review][Patch] model_overlap 재검토 분기가 강한 keep 신호(고배수)를 무조건 덮는다는 설계 의도를 주석으로 명시(현재 미문서) [scorecard/rule_efficiency.py:_verdict] (blind, Low)
- [x] [Review][Defer] `opportunity_loss_est`가 양수 실현손익만 합산 → 순 포트폴리오 수치와 tie-out 안 됨. Task 3에서 "놓친 이익" 정의로 의도한 결정(리포트 명시), 순액 지표가 필요해지면 별도 필드 [scorecard/rule_efficiency.py:_opportunity_loss] — deferred
- [x] [Review][Defer] vintage/model_type dtype mismatch 시 조용히 빈 population→500 — strategy.py 등 기존 소비자와 동일 관례(fail-fast), AD-3 프레임 스키마가 dtype 보장. 프레임 생성(1.7b) 소관 [scorecard/rule_efficiency.py] — deferred
- [x] [Review][Defer] raw `id` 중복 시 `validate="many_to_one"`가 startup 전체 차단(MergeError) — profit.load_profit_frame과 동일 계약, 데이터 품질 문제를 전체 장애로 전환하나 fail-fast가 의도. 부분 강등 필요 시 재평가(2.4 startup-crash defer와 동류) — deferred

dismiss: overlap 방향(score<cutoff=거절)은 1.7b `generalized_score`가 "높은 점수=안전"으로 확정한 계약이라 반전 위험 없음(파이프라인 전체 관례); `nan`/enum 관련 일부는 Edge가 이미 가드 확인.

## Dev Notes

### 이 스토리의 성격 — 컨설턴트 킥②, "룰을 데이터로 심판"
2.4(손익 cutoff, 킥①)와 쌍을 이루는 "판정 없는 컨설팅 산출물". 청자는 경영진/룰 운영팀이고, 핵심은 **"이 하드룰이 모형 대비 실제로 값을 하는가"**를 데이터로 답하는 것. 정직성 원칙: 룰셋은 **가상**(실무 관행 기반으로 이 스토리가 설계)이라는 점을 리포트에 명시.

### 핵심 갭: 룰 입력 변수가 프레임에 없다 (실측 확인, 2.4와 동형)
```python
# scored_validation_frame 컬럼(evaluation.SCORED_FRAME_COLUMNS):
#   applicant_id, vintage, model_type, score, pd, grade, bad_flag,
#   int_rate, recoveries, total_pymnt
# → dti / delinq_2yrs / inq_last_6mths / loan_amnt 없음
# raw lc_accepted_2012_2015_36m.parquet: 위 4개 전부 존재(실측 True)
```
**해결**: 2.4 `profit.load_profit_frame`와 동일한 읽기전용 조인. AD-3 비위반 판단도 동일(frame 컬럼 불변, 룰 입력만 augment). `validate="many_to_one"` + 미매치 fail-fast 그대로 계승.

### AD-3 준수 판단 — 조인은 위반이 아니다 (2.4 선례 확립)
AD-3는 frame이 **이미 담은 값**(score/pd/grade/bad_flag)을 재계산하지 말라는 것이지, frame에 없는 컬럼을 다른 목적(룰 진단)으로 raw에서 읽어 augment하는 것까지 막지 않는다. 2.4가 loan_amnt로 이미 이 선례를 확립·리뷰 통과함. **반드시 지킬 것**: frame 기존 컬럼은 그대로 두고 룰 입력 컬럼만 옆에 붙인다, 재작성·덮어쓰기 금지.

### 재사용 지도
- `scorecard/profit.py:load_profit_frame` — 조인 패턴 원본(many_to_one, fail-fast). loan_amnt는 profit과 공유되므로 loader에서 profit_frame을 이미 만들 때 dti/delinq/inq만 추가하는 방식 검토(중복 조인 회피).
- `scorecard/profit.py:realized_profit(loan_amnt, total_pymnt, recoveries)` — 기회손실 계산에 **재사용**(재구현 금지).
- `scorecard/strategy.py:OOT_VINTAGE`, `_filter_population` 패턴 — 모집단 필터·fail-fast 관례.
- `scorecard.config.ACCEPTED_PARQUET` — raw parquet 경로 상수(2.2/2.4가 사용). 새 경로 문자열 만들지 말 것.
- `app/loader.py`: `CURRENT_CUTOFF=546.0`(중복도 계산 기준), startup 사전계산 패턴(profit_base_curves), `_require_loaded()`, NaN→null `_clean` 관례.
- `app/main.py`: 엔드포인트 등록·`ApiError`·`RequestValidationError` 핸들러·model 쿼리 파라미터 패턴(§3 grades, §6 cutoff 참고).
- `scorecard/rule_efficiency.py` — **현재 CAP-15 스텁**(스캐폴딩만) → 구현 대상.

### 아키텍처 가드레일
- **AD-7**: verdict는 순수 규칙(배수·중복도 임계 조합) — LLM/외부 호출 금지. profit의 find_optimal_cutoff가 순수 argmax인 것과 동일 정신.
- **AD-3**: frame 컬럼 재계산 금지(augment는 허용, 위 설명).
- **AD-5**: API_SPEC §8이 확정 스키마 — 필드명 그대로. model 쿼리 추가는 "추가만"이라 위반 아님(근거 기록).
- **AD-9**: app은 조립만, rule_efficiency.py가 계산 소유.
- **NFR1**: 결정론적 — 난수 없음.
- **NFR7**: verdict에 근거 명시(§8 verdict 문자열이 "왜"를 담음).

### 스코프 가드 (하지 말 것)
- 룰 자동 최적화·룰 학습 금지 — 이 스토리는 **고정 가상 룰셋의 진단**만(룰 생성 AI는 AD-7 위반이자 스코프 밖).
- 실제 정책 룰이라 사칭 금지 — "가상 룰셋(실무 관행 기반 설계)"임을 리포트·응답 맥락에 유지.
- 3.2(text_features)·3.3(SAS) 침범 금지.
- 대시보드에 룰 화면 추가는 이 스토리 밖(2.5 스코프 가드에서 이미 배제) — 필요 시 deferred-work.

### 이전 스토리 인텔리전스 (2.4/2.5 인수인계)
- 2.4 교훈: raw 조인은 `many_to_one` + 미매치 fail-fast. NaN-not-0.0(배제/승인 0건은 미정의를 null로, 0으로 위장 금지). `RequestValidationError`로 비유한 입력 422 처리(rule 엔드포인트는 입력이 쿼리뿐이라 위험 낮지만 model 값 검증은 pattern으로).
- 2.4 교훈: **startup 사전계산이 degenerate 입력에서 크래시하면 uvicorn이 안 뜬다**(deferred-work 기록됨). rule_frame 조인도 startup에서 fail-fast하면 동일 — 현재 실데이터 100% 매치라 발생 안 하지만 인지.
- 2.3 교훈: 엔드포인트가 두 모델 셰이프를 반환할 때 model 쿼리 파라미터 패턴, 에러 3종 계약.
- 공통: **실데이터 실행이 버그를 잡는다** — 합성 mock 초록으로 끝내지 말고 실제 조인·계산 실행해 verdict가 상식적인지(고DTI 배제집단이 실제로 부도율 높은지) 확인.
- 리포트 정직성(2.4 1페이저 톤): 가정을 숨기지 않는다 — 가상 룰셋·기회손실 정의·표본 가정 명시.

### Project Structure Notes
- `scorecard/rule_efficiency.py` — MODIFIED(스텁 → 구현, CAP-15): RULE_SET, load_rule_frame(또는 profit_frame 확장), rule_efficiency, verdict 규칙.
- `app/schemas.py` — MODIFIED(RuleEfficiency/RuleEfficiencyResponse 추가).
- `app/loader.py` — MODIFIED(rule 입력 조인 + 필요 시 사전계산).
- `app/main.py` — MODIFIED(`GET /v1/rules/efficiency` 추가).
- `tests/test_rule_efficiency.py` — NEW.
- `tests/test_app.py` — MODIFIED(엔드포인트 테스트 추가).
- `docs/implementation-artifacts/rule-efficiency-report-3-1.md` — NEW.

### References
- [Source: docs/planning-artifacts/epics.md#Story-3.1] — AC 원문(FR15, AD-7, AD-5, NFR7)
- [Source: API_SPEC.md §8] — `/v1/rules/efficiency` 요청/응답 스키마 원문
- [Source: ARCHITECTURE-SPINE.md#AD-3,AD-7,AD-9] — frame 소비·규칙기반 verdict·app 의존 방향
- [Source: scorecard/profit.py] — 조인(load_profit_frame)·realized_profit 재사용 원본(2.4)
- [Source: scorecard/strategy.py] — OOT 모집단 필터·fail-fast 선례
- [Source: app/loader.py, app/main.py] — startup 사전계산·CURRENT_CUTOFF·엔드포인트 등록 패턴
- [Source: data/lc_accepted_2012_2015_36m.parquet] — 룰 입력 변수 실재 확인(dti/delinq_2yrs/inq_last_6mths/loan_amnt)

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

- 콘솔 출력 인코딩(cp949)이 한글 verdict/description을 깨뜨림 → 실측 확인은 `PYTHONIOENCODING=utf-8` + `requests`로 in-process 검증(엔드포인트 응답 자체는 정상 UTF-8, curl→shell 파이프 아티팩트였음).

### Completion Notes List

- **데이터 갭 해소(2.4 동형)**: 룰 입력(dti/delinq_2yrs/inq_last_6mths/loan_amnt)이 AD-3 프레임에 없어 `load_rule_frame`이 raw parquet에서 읽기전용 조인(`many_to_one`+미매치 fail-fast). frame 기존 컬럼 불변 — AD-3 비위반.
- **가상 룰셋 3종**(선언적 `RULE_SET`): DTI>40(strict) / INQ≥3 / DELINQ≥1. NaN 입력은 pandas 비교상 False = "배제 안 함"(보수적, 기회손실 과대추정 방지).
- **verdict(AD-7 순수 규칙)**: ①배제집단 부도율/모집단 배수(≥1.5 유지) ②모형 컷오프 중복도(≥0.7 재검토, 판별력과 무관하게 우선). 임계 상수 노출. **기회손실**은 배제-우량 대출에 `profit.realized_profit` 재사용(양수만 합산).
- **실데이터 발견(강력한 컨설팅 인사이트)**: 세 룰 **모두 재검토 권장**. DTI·INQ는 배제집단이 위험(1.58/1.64배)하지만 85~94%를 모형이 이미 거절(중복). DELINQ는 58,974건(21%)을 배제하면서 부도율 1.07배(판별력 낮음)+기회손실 최대(₩9,441만). → "스코어카드가 있으면 하드룰 상당수는 중복/비효율"이라는 정직한 결론.
- **엔드포인트**: `GET /v1/rules/efficiency?model=` (§8 스키마 + model 쿼리 추가, AD-5 비위반 근거 기록 + assumptions 항상 포함). loader가 startup에 rule_frame 1회 조인, app은 조립만(AD-9).
- **라이브 실증**: uvicorn HTTP로 챔피언·챌린저 양쪽 200(중복도 91/85 vs 94/89로 model 쿼리 실제 작동), bad model 422, 액세스 로그에 model_version 확인. UTF-8 응답 검증.
- pytest **201 passed**(기존 189 + rule_efficiency 9 + app 3).

### File List

- `scorecard/rule_efficiency.py` (MODIFIED — 스텁 → 구현: Rule/RULE_SET, load_rule_frame, _opportunity_loss, _verdict, rule_efficiency)
- `app/schemas.py` (MODIFIED — RuleEfficiency/RuleEfficiencyResponse 추가)
- `app/loader.py` (MODIFIED — rule_frame 필드 + startup 조인, load_rule_frame import)
- `app/main.py` (MODIFIED — GET /v1/rules/efficiency)
- `tests/test_rule_efficiency.py` (NEW — 9 tests)
- `tests/test_app.py` (MODIFIED — 엔드포인트 테스트 3건)
- `docs/implementation-artifacts/rule-efficiency-report-3-1.md` (NEW — 룰 정비 제안 리포트, 실데이터+한계 명시)

## Change Log

- 2026-07-16: 3-레이어 코드리뷰(Blind/Edge/Auditor) — patch 6건 반영(no-rows/None rule_frame 방어, unmatched-join을 id 키 기준으로 수정, nan배 verdict 가드, model_overlap 우선순위 주석, API_SPEC §8에 assumptions·model 쿼리 반영), defer 3건, dismiss 일부(overlap 방향은 generalized_score 계약). 회귀 테스트 2건, pytest 203 passed, 라이브 재실증. Auditor 차단 위반 0건. Status → done.
- 2026-07-16: Story 3.1 구현 — scorecard/rule_efficiency.py + GET /v1/rules/efficiency. 실데이터 결과 세 룰 모두 재검토 권장(DTI·INQ 모형 중복 85~94%, DELINQ 판별력 1.07배·기회손실 최대). 리포트 작성(한계 명시). 라이브 uvicorn 실증(챔피언·챌린저). pytest 201 passed(+12). Status → review.
- 2026-07-16: Story 3.1 생성 — 핵심 데이터 갭(룰 입력 변수 dti/delinq/inq + loan_amnt가 프레임에 없음) 실측 발견·해소 방안(2.4 조인 패턴 재사용, AD-3 비위반) 결정, 가상 룰셋 3+개 후보·기회손실 정의·verdict 규칙(배수+모형 중복도) 오픈퀘스천 명시, GET /v1/rules/efficiency에 model 쿼리 추가 근거 기록, profit.realized_profit 재사용 지도 작성.
