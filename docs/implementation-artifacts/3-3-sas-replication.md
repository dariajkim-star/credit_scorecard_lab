---
baseline_commit: 4a9383f
---

# Story 3.3: SAS 재현 (컨설턴트 킥④)

Status: ready-for-dev

## Story

As a SAS 레거시 환경의 채용사를 대비하는 지원자,
I want 스코어카드 점수산출 로직을 SAS로 이식해 Python과 대조하고,
so that "Python으로 개발, SAS로 이식 검증" 역량을 증빙할 수 있다.

## Acceptance Criteria

**Given** 사용자의 SAS OnDemand for Academics 계정 확보 확인 (**확보 확인됨 — 2026-07-16, 풀 구현 진행**)
**When** `sas/scorecard_scoring.sas`로 WOE 변환→선형결합→PDO 스케일링을 이식하면

1. 동일 입력 10건 이상에서 SAS-Python 점수 오차 <0.5점 (FR17)
2. 대조 리포트가 산출된다
3. 이 스토리는 다른 스토리를 블로킹하지 않는다

> 성공기준 계량화(스토리 오너 보강): 위 3개 AC + `pytest -q` 초록(기존 210 + 신규) + 실데이터. **환경 제약 명시**: SAS OnDemand는 클라우드 대화형 환경이라 이 개발 세션에서 직접 실행 불가. 따라서 dev가 산출하는 것은 ①아티팩트에서 **정확히 자동생성**한 `scorecard_scoring.sas`(WOE 룩업+공식 하드코딩) ②동일 신청 10건+의 Python 기준 점수(CSV) ③**Python 자체 검증**: 라이브러리(sklearn/optbinning) 없이 순수 산술로 SAS와 동일한 룩업+공식을 재구현한 "SAS 로직 미러"가 `champion.score_applicant`와 <0.5 일치함을 증명(SAS가 미러할 산술이 옳음을 독립 증명). **SAS-Python 최종 tie-out은 사용자가 OnDemand에서 .sas 실행 후 CSV 대조**로 완료(대조 절차·기대값을 리포트에 명시).

## Tasks / Subtasks

- [ ] Task 1: 챔피언 점수 산출 로직 추출 (AC: #1, 전제)
  - [ ] **이식 대상 확정(실측 확인)**: `champion.score_applicant` 경로 = 원시값 →(WOE 룩업)→ `logit = intercept + Σ(coef_i · woe_i)` →(PDO 스케일)→ `score = offset + factor·(−logit)`, `factor = PDO/ln(2)`, `offset = base_score − factor·ln(base_odds)`. 상수: PDO=20, base_score=600, base_odds=50(`champion.py`). intercept=−1.928423, 7개 계수 전부 음수(fico −0.7686 … inq −1.0981) — 아티팩트에서 실측.
  - [ ] `sas/export_scorecard.py`(또는 유사) — 챔피언 아티팩트(`champion_model.joblib`)에서 **정확히** 추출: (a) 7변수 각각의 WOE 빈 테이블(수치 변수=구간 경계→WOE, 범주 변수 home_ownership/purpose=카테고리→WOE), (b) 로지스틱 계수·절편, (c) 상수. **Missing/Special 빈의 WOE는 binning_table의 실측값 사용**(서빙 `transform_woe`가 `metric_missing="empirical"`이므로 SAS도 동일 empirical WOE로 매핑 — 0 하드코딩 금지, 1.4 함정 계승).
  - [ ] 추출 산출물을 SAS가 소비할 형태로: 권장 — 추출값을 그대로 `.sas`에 하드코딩 생성(외부 파일 의존 없이 OnDemand에 붙여넣기 가능). 부동소수 정밀도는 최소 6자리 유지(오차 <0.5 여유 확보).
- [ ] Task 2: `scorecard_scoring.sas` 생성 (AC: #1)
  - [ ] SAS DATA step: 각 변수의 원시값 → WOE (수치=`if lo <= x < hi then woe=...` 체인, 범주=`if var in (...) then woe=...`), 미해당/결측 → 해당 변수의 Missing WOE. **경계 방향은 Python 빈과 동일하게**(optbinning은 `[lo, hi)` 좌폐우개 — SAS도 동일 부등호). 그다음 `logit = intercept + sum(coef*woe)`, `score = offset + factor*(-logit)`.
  - [ ] 결정론적·자기완결적: 외부 매크로·PROC 의존 최소화(순수 DATA step 권장), OnDemand에서 그대로 실행 가능하게. 상단 주석에 "이 파일은 champion 아티팩트에서 자동생성됨 + 재생성 방법" 명시.
  - [ ] **자동생성**을 권장(손으로 WOE 표 옮기면 오타 리스크) — `export_scorecard.py`가 `.sas` 텍스트를 통째로 써내도록. 값이 아티팩트와 100% 일치 보장.
- [ ] Task 3: Python 기준 점수 + SAS 로직 미러 (AC: #1)
  - [ ] `sas/reference_applicants.csv` — OOT(2015)에서 10건+ 신청의 원시 입력 7필드 + `champion.score_applicant` 점수(Python 정답). 결측·범주 케이스 포함(경계·Missing 매핑까지 커버되게 다양하게 선정).
  - [ ] **Python SAS-로직 미러**(`sas/sas_logic_mirror.py` 또는 export의 일부): sklearn/optbinning 없이 **순수 산술**로 SAS와 동일한 WOE 룩업+선형결합+PDO를 재구현. 이것이 `champion.score_applicant`와 10건 전부 <0.5(사실상 <1e-6) 일치함을 검증 → **SAS가 미러할 산술이 정확함을 라이브러리 독립적으로 증명**. (SAS 실행 없이도 이식 로직의 정확성을 이 세션에서 보증하는 핵심 장치.)
- [ ] Task 4: 대조 리포트 (AC: #2)
  - [ ] `docs/implementation-artifacts/sas-replication-report-3-3.md` — 이식 대상 로직·공식, WOE 룩업 방식, 상수, **대조 절차**(사용자가 OnDemand에서 `.sas` 실행 → 출력 점수 → `reference_applicants.csv`의 Python 점수와 차이 계산 → 전 건 <0.5 확인), Python 미러 검증 결과(이 세션에서 산출), 한계(SAS 최종 tie-out은 사용자 실행 의존). "Python 개발 / SAS 이식 검증" 역량 증빙 톤.
- [ ] Task 5: pytest + 실증 (AC: 전체)
  - [ ] `tests/test_sas_replication.py` — SAS 로직 미러가 `champion.score_applicant`와 10건+ 일치(<0.5, 실제 <1e-6), 경계값·범주·Missing 케이스 포함. export가 아티팩트 값과 일치(계수/절편/WOE). reference CSV 생성 재현성.
  - [ ] `pytest -q` 전체 통과(기존 210 + 신규).
  - [ ] 실데이터: 실제 champion 아티팩트에서 SAS 자동생성 + 10건 미러 대조 실행(이 세션). SAS 실제 실행은 사용자 몫으로 명확히 인계(리포트에 절차).

## Dev Notes

### 이 스토리의 성격 — 컨설턴트 킥④, "이식 가능성 증빙"
"Python으로 개발한 스코어카드를 SAS 레거시로 옮길 수 있다"를 증빙. 핵심은 점수 산출이 **결정론적 산술**(WOE 룩업 + 선형결합 + PDO 스케일)이라 어느 언어로든 정확히 재현된다는 점. 모델 학습이 아니라 **점수 산출만** 이식(SAS에서 재학습 금지).

### 환경 제약 (반드시 인지)
SAS OnDemand for Academics는 웹 기반 대화형 환경 — 이 dev 세션에서 SAS 코드를 직접 실행할 수 없다. 그래서:
- **이 세션이 보증하는 것**: `.sas` 자동생성(아티팩트와 값 일치) + Python 순수-산술 미러가 챔피언과 <0.5 일치(SAS가 복제할 산술의 정확성 증명).
- **사용자가 완료하는 것**: OnDemand에 `.sas` 붙여넣기 실행 → 출력을 `reference_applicants.csv`와 대조 → 전 건 <0.5 확인. 절차를 리포트에 상세히.
- 이 분업으로 AC #1(오차 <0.5)의 **산술적 정확성은 세션에서, 실환경 tie-out은 사용자가** 각각 담보.

### 이식 대상 로직 (실측)
```
score_applicant(원시 7필드):
  woe_i   = WOE_lookup_i(원시값_i)         # optbinning 빈, 좌폐우개 [lo,hi), Missing=empirical WOE
  logit   = intercept + Σ coef_i * woe_i    # intercept=-1.928423, coef 전부 음수
  factor  = 20 / ln(2)                       # PDO=20
  offset  = 600 - factor * ln(50)            # base_score=600, base_odds=50
  score   = offset + factor * (-logit)
```
- 수치 변수(fico_range_low, annual_inc, dti, revol_util, inq_last_6mths): 구간→WOE. **revol_util은 원시가 "45.3%" 문자열**이므로 SAS도 % 파싱 필요(또는 reference CSV를 파싱된 float로 제공해 SAS 입력 단순화 — 스토리오너 결정·기록).
- 범주 변수(home_ownership, purpose): 카테고리→WOE. optbinning이 동일 WOE 카테고리를 묶은 그룹(예 `[RENT, NONE, OTHER]`)은 그룹 내 전 카테고리를 같은 WOE로 매핑.
- **미학습 카테고리/결측**: 해당 변수 Missing 빈 WOE로(서빙 관례와 일치).

### 재사용 지도
- `scorecard/champion.py`: `score_formula`(공식 상수·factor·offset), `score_applicant`(정답 경로), PDO/BASE_SCORE/BASE_ODDS/MODEL_VERSION.
- `scorecard/binning.py`: `transform_woe`(정답 WOE, metric_missing="empirical") — 미러 검증의 대조군. 아티팩트 binners의 `binning_table.build()`로 빈·WOE 추출.
- `scorecard/config.py:ARTIFACTS_DIR`, `champion_model.joblib`/`champion_manifest.json`(feature_order·woe_bin_edges).
- `scorecard/preprocessing.py:parse_percent`(revol_util % 파싱, reference/미러 일관).
- `scorecard/sample_design.py`+`app/loader.py:SCORED_FRAME_PATH` 또는 raw — 10건 신청 원시값 확보. (OOT applicant_id로 raw 조인해 원시 7필드 추출 — 2.4/3.1 조인 패턴 참고.)

### 아키텍처 가드레일
- **AD-2**: WOE 정답은 binning.py. SAS/미러는 그 값을 **복제**하는 것이지 새 WOE 계산이 아니다(미러는 하드코딩 룩업).
- **AD-4**: SAS는 점수 산출만(재학습 금지).
- **NFR1**: 결정론적 — 난수 없음.
- **AD-1**: 이식은 아티팩트(model/manifest)를 단일 진실로 삼아 자동생성(손 복사 금지 → 값 불일치 방지).

### 스코프 가드 (하지 말 것)
- SAS에서 모델 재학습·재비닝 금지 — 점수 산출 이식만.
- 챌린저(LightGBM) 이식 금지 — 트리 모델은 SAS 이식 대상 아님(스코프는 챔피언 스코어카드).
- WOE/공식 손 복사 금지 — 아티팩트에서 자동생성(오타=오차).
- 이 스토리가 다른 스토리 블로킹 금지(AC #3) — 독립 산출물.

### 이전 스토리 인텔리전스
- 1.4/1.5 교훈: `metric_missing="empirical"` — Missing WOE를 0으로 두면 서빙과 어긋남. SAS Missing 매핑도 empirical 값.
- 1.5 교훈: score_formula는 `decision_function`(logit) 기반이지 predict_proba 아님 — 미러도 logit 경로.
- 2.4/3.1 교훈: 원시 필드는 raw 조인으로(프레임엔 원시 7필드 없음 — score/pd/grade만). applicant_id==id.
- 공통: **실데이터로 검증** — 실제 아티팩트에서 생성·미러 대조.

### Project Structure Notes
- `sas/scorecard_scoring.sas` — NEW(자동생성, 이식 코드).
- `sas/export_scorecard.py` — NEW(아티팩트→.sas 생성 + reference CSV + 미러).
- `sas/reference_applicants.csv` — NEW(10건+ 원시입력 + Python 점수).
- `tests/test_sas_replication.py` — NEW.
- `docs/implementation-artifacts/sas-replication-report-3-3.md` — NEW(대조 절차 포함).
- `scorecard/`·`app/` 기존 코드 — 변경 없음(읽기만).

### References
- [Source: docs/planning-artifacts/epics.md#Story-3.3] — AC 원문(FR17)
- [Source: scorecard/champion.py] — score_formula/score_applicant 공식·상수(이식 대상)
- [Source: scorecard/binning.py] — WOE 정답·binning_table 추출
- [Source: ARCHITECTURE-SPINE.md#AD-1,AD-2,AD-4] — 아티팩트 단일진실·WOE 단일경로·재학습 금지
- [Source: data/champion_model.joblib, champion_manifest.json] — 계수·절편·WOE·feature_order 실측(intercept −1.928423 등)

## Dev Agent Record

### Agent Model Used

(dev-story 시 기록)

### Debug Log References

### Completion Notes List

### File List

## Change Log

- 2026-07-16: Story 3.3 생성 — 사용자 SAS OnDemand 계정 확보 확인(풀 구현). 환경 제약(SAS 세션 내 실행 불가) 반영: `.sas` 자동생성 + Python 순수-산술 미러로 이식 산술 정확성을 세션에서 증명, 실환경 SAS-Python tie-out은 사용자 실행으로 분업. 이식 대상 로직(WOE 룩업+선형결합+PDO, intercept/계수 실측) 확정, Missing empirical WOE·revol_util % 파싱·범주 그룹 매핑 등 이식 함정 명시, 아티팩트 자동생성으로 손복사 오차 차단.
