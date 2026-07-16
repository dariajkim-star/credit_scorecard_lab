---
baseline_commit: 6e34f2e
---

# Story 3.2: 비금융 텍스트 파생변수 (컨설턴트 킥③)

Status: done

## Story

As a 비금융 데이터 활용을 검증하는 분석가,
I want emp_title 텍스트에서 파생변수를 만들어 IV 기여도를 측정하고,
so that "비금융 데이터를 실제로 검증했다"는 결과를 효과 유무와 무관하게 제시할 수 있다.

## Acceptance Criteria

**Given** 원본 데이터의 emp_title 컬럼
**When** `scorecard/text_features.py`로 소문자화·특수문자 제거·상위 빈도 카테고리 매핑하면 (정교한 NLP 지양)

1. 파생변수의 WOE/IV가 산출되고 정형 변수 대비 기여도가 비교된다 (FR16)
2. 효과가 없으면 없다고 기록한다 — 검증 자체가 산출물
3. 결과 문서가 MDD에 편입될 형태로 산출된다

> 성공기준 계량화(스토리 오너 보강): 위 3개 AC + `pytest -q` 초록(기존 203 + 신규) + **실데이터 실행**(emp_title 파생변수의 IV를 실제 학습 표본에서 산출하고, 7개 정형 변수 IV와 나란히 비교). **이 스토리는 API 엔드포인트가 없다**(AC에 없음 — 3.1과 다름): 산출물은 `text_features.py` 모듈 + WOE/IV 수치 + MDD 편입용 리포트. 효과가 낮으면 낮다고 정직하게 기록하는 것이 성공(검증 자체가 산출물, AC #2).

## Tasks / Subtasks

- [x] Task 1: emp_title 정제 (AC: #1, 전제)
  - [x] **실측 확인 완료(스토리 생성 시)**: raw `lc_accepted_2012_2015_36m.parquet`에 `emp_title` 존재, 589,635행 중 **결측 6.7%**, **고유값 207,516개**(극단적 롱테일 — 그대로 categorical 비닝 불가). 상위: teacher/manager/owner/registered nurse/supervisor/driver/... `emp_length`도 raw에 있으나 **이 스토리 스코프 밖**(AC는 emp_title만).
  - [x] `clean_emp_title(series) -> pd.Series` — 소문자화 + 앞뒤 공백 제거 + 특수문자/다중공백 정규화(예: 영문·숫자·공백만 남김). **정교한 NLP 지양**(AC 명시) — 어간추출·임베딩·불용어 사전 금지. 순수 문자열 정규화만.
  - [x] 결측(`NaN`) 처리 방침 결정·기록: 정제 후에도 결측은 별도 `MISSING` 카테고리로 보존(binning의 Missing 빈과 일관, 1.4 metric_missing 계약 정신 — 결측을 조용히 버리지 않음).
- [x] Task 2: 상위 빈도 카테고리 매핑 (AC: #1)
  - [x] **오픈퀘스천(반드시 결정·기록)**: 정제된 문자열을 소수 카테고리로 축약하는 규칙. 권장(가장 단순·투명): **train 표본 기준 상위 K개 빈도 직함을 각자 카테고리로, 나머지는 `OTHER`, 결측은 `MISSING`**. K는 스토리오너 결정(권장 20 — 상위 20개가 표본의 상당 비중을 덮고 각 빈이 통계적으로 충분). **키워드 그룹핑(manager 계열 묶기 등)은 하지 말 것** — "정교한 NLP 지양" 및 자의적 그룹핑이 결과를 왜곡(효과를 인위적으로 키움). 빈도 컷은 **train에서만** 정하고 valid/oot에 동일 적용(누수 방지, 1.4 fit-on-train 원칙 계승).
  - [x] `map_emp_title_category(cleaned, top_titles) -> pd.Series` — 순수 매핑. `top_titles`(train 상위 K)는 인자로 받아 train/valid/oot에 동일 적용(하드코딩 금지).
  - [x] `fit_top_titles(train_cleaned, k=20) -> list[str]` — train에서 상위 K 직함 추출(누수 경계 단일화).
- [x] Task 3: WOE/IV 산출 + 정형 변수 대비 비교 (AC: #1, #2, FR16)
  - [x] **학습 표본 재구성**: raw에서 `emp_title` + 라벨용 `loan_status` + `vintage`를 읽어 `sample_design.label_and_filter`(bad_flag 부착) + `split_by_vintage`로 train/valid/oot 분리. **기존 함수 재사용**(재구현 금지) — sample_design은 raw df를 받아 동작함(실측: raw에 loan_status/vintage/id 존재).
  - [x] **WOE/IV는 binning.py 재사용**(AD-2 단일 경로): emp_title_category를 categorical 변수로 `fit_binning(train, y, variables=["emp_title_category"])` → `iv_table` → IV. `transform_woe`로 WOE 매핑. **직접 WOE/IV 공식 재구현 금지**(optbinning categorical solver 사용, 1.4와 동일).
  - [x] **정형 변수 대비 비교**: 동일 train 표본에서 7개 정형 변수의 IV를 **같은 방식으로 재산출**해 emp_title_category IV와 나란히 표로(사과 대 사과 — 1.4 리포트 수치를 그대로 인용하기보다 같은 코드경로로 재계산 권장). "emp_title이 정형 변수 대비 어느 수준인가"를 정량 비교.
- [x] Task 4: 결과 리포트 (AC: #2, #3, MDD 편입)
  - [x] `docs/implementation-artifacts/text-features-report-3-2.md` — emp_title 정제·매핑 방식, 파생변수 IV vs 7개 정형 변수 IV 표, WOE 방향(어느 직함이 위험/안전 쪽인지), **결론을 정직하게**: 효과가 낮으면(IV<0.02 등 관행 임계) "비금융 텍스트 파생변수는 이 데이터·이 방식에서 유의미한 추가 판별력을 주지 못했다"고 명시. **검증 자체가 산출물**(AC #2) — 효과 유무와 무관하게 "실제로 검증했다"는 것이 가치. MDD(3.4) 편입 가능한 형태·톤.
  - [x] 한계 명시: 단순 빈도 매핑(NLP 미적용)이라 직함의 의미론적 정보는 활용 안 함 / emp_title 결측 6.7% / 자영업·프리랜서 등 표준화 안 된 직함의 노이즈.
- [x] Task 5: pytest + 실증 (AC: 전체)
  - [x] `tests/test_text_features.py` — clean_emp_title 정규화(대소문자·특수문자·공백), map_emp_title_category 매핑(상위 직함→자기카테고리, 미등록→OTHER, 결측→MISSING), fit_top_titles가 train 상위 K 반환, 누수 경계(top_titles는 train에서만). IV 산출은 binning 재사용이므로 파이프 연결만 검증(공식 재검증 불필요).
  - [x] `pytest -q` 전체 통과(기존 203 + 신규).
  - [x] **실데이터 실행**: emp_title_category IV를 실제 train에서 산출, 7개 정형 변수 IV와 비교, 리포트에 실측값 기입. (엔드포인트 없으므로 uvicorn 실증은 해당 없음 — 실데이터 IV 산출이 이 스토리의 "실증".)

### Review Findings (2026-07-16, 3-레이어 리뷰: Blind/Edge/Auditor)

- [x] [Review][Patch] `fit_top_titles`의 tie-break이 비결정적 — `value_counts`는 동점 순서를 계약 보장하지 않아 pandas 버전/플랫폼에 따라 K번째 직함이 바뀔 수 있음. 이건 valid/oot에 적용되는 지속 아티팩트(top_titles)라 재현성 필수. 2차 정렬키(count desc, then title) 추가 [scorecard/text_features.py:fit_top_titles] (blind+edge, Med)
- [x] [Review][Patch] 통합 테스트의 IV 단언이 tautological — `iv.iloc[0]["iv"] >= 0`은 IV가 수학적으로 항상 ≥0이라 아무것도 검증 못 하고 inf도 통과. `variable=="emp_title_category"`로 필터 + 유한성 단언으로 교체 [tests/test_text_features.py] (blind+edge, Med)
- [x] [Review][Patch] 통합 테스트가 누수 경계를 실증 안 함 — valid/oot split을 계산하고 버림. train-fit top_titles를 OOT에 적용하면 카테고리가 {top∪OTHER∪MISSING}로만 나옴을 단언(미학습 카테고리 폭발 없음) [tests/test_text_features.py] (blind, Med)
- [x] [Review][Patch] 리포트에 WOE 방향 누락 — Task 4가 "어느 직함이 위험/안전 쪽인지" 명시를 요구했고 체크했으나 리포트에 카테고리별 WOE 표·방향 없음. 카테고리별 WOE + 위험/안전 방향 추가 [text-features-report-3-2.md] (auditor, Med)
- [x] [Review][Patch] 정형 7변수 IV 비교가 커밋 코드에서 재현 불가 — 리포트 수치(fico 0.1298…)가 ad-hoc 실행 결과로만 존재, 커밋된 테스트/스크립트가 산출 안 함. 재현 가능한 형태로 캡처(테스트/스크립트) [tests/test_text_features.py 또는 스크립트] (auditor, Med, NFR1)
- [x] [Review][Patch] 리포트가 MISSING 처리 메커니즘 오기 — "WOE는 empirical"이라 했으나 실제로는 NaN을 문자열 "MISSING" 카테고리로 변환해 optbinning Missing-빈 기계가 관여 안 함(일반 범주 빈). 동작은 정상이나 MDD 문서 정확성 위해 문구 수정 [text-features-report-3-2.md] (auditor, Med)
- [x] [Review][Patch] docstring 부정확 — `clean_emp_title` "NaN stays NaN"이나 실제로 pd.NA(StringDtype)로 변환; "MISSING=null/empty"이나 비ASCII 직함도 MISSING이 됨. 정확히 기술 [scorecard/text_features.py] (blind+edge, Low)
- [x] [Review][Patch] 방어 가드 소묶음 — `fit_top_titles` k<0 시 head(-k)로 오작동(k≥0 검증), `derive_emp_title_category` source 컬럼 부재 시 bare KeyError, `map_emp_title_category`의 top_titles에 MISSING/OTHER 유입 시 충돌(assert), `replace("", pd.NA)`를 버전 견고한 `mask(str.len()==0)`로 [scorecard/text_features.py] (edge+blind, Low)

dismiss: 비ASCII 직함이 MISSING으로 소실되는 "동작 변경"은 Lending Club 데이터가 영문이라 실제 영향 없음 — 동작은 유지하고 docstring 정직화(위 patch)로 처리. non-string 숫자 stringify는 emp_title이 string dtype이라 발생 불가.

## Dev Notes

### 이 스토리의 성격 — 컨설턴트 킥③, "네거티브 결과도 산출물"
2.4(손익)·3.1(룰)과 다른 결의 킥: **효과가 없어도 성공**이다. "비금융 데이터(직함 텍스트)를 실제로 검증해봤다"는 사실 자체가 산출물(AC #2). 채용 맥락에서 "무작정 넣지 않고 검증 후 판단"하는 태도를 보이는 게 목적. 따라서 IV가 낮게 나와도 그대로 정직하게 기록 — 억지로 효과를 만들려고 키워드 그룹핑·NLP를 끌어들이면 오히려 스토리 취지에 반한다.

### API 엔드포인트 없음 (3.1과의 차이)
3.1은 §8 엔드포인트가 AC였지만, **3.2 AC에는 엔드포인트가 없다**. 산출물은 모듈 + WOE/IV + 리포트. `app/`·`API_SPEC.md` 변경 없음. uvicorn 실증도 해당 없음(실데이터 IV 산출이 실증 역할).

### 핵심 제약: emp_title은 롱테일 + 결측 (실측)
```
결측 6.7% · 고유값 207,516개 (589,635행)
상위: teacher, manager, owner, registered nurse, supervisor, driver, sales, rn, ...
```
그대로 categorical 비닝하면 20만 개 빈 → 무의미. **상위 K 빈도 + OTHER + MISSING**으로 축약해야 함. `rn`↔`registered nurse` 같은 동의어가 보이지만, **정규화로 합치려 들지 말 것**(NLP 지양 + 자의성) — 단순 빈도 매핑의 한계로 리포트에 명시.

### 재사용 지도
- `scorecard/sample_design.py`: `label_and_filter`(bad_flag), `split_by_vintage`(train=2012-13/valid=2014/oot=2015), `TRAIN_VINTAGES`. raw df를 받아 동작 — raw에 loan_status/vintage/id 존재(실측).
- `scorecard/binning.py`: `fit_binning(train, y, variables=[...])`(categorical solver 자동), `transform_woe`(AD-2 단일 WOE 경로, metric_missing="empirical"), `iv_table`. **직접 WOE/IV 공식 재구현 절대 금지.**
- `scorecard.config.ACCEPTED_PARQUET` — raw 경로 상수.
- `scorecard/text_features.py` — **현재 CAP-16 스텁** → 구현 대상.
- 7개 정형 변수 IV 비교: 같은 코드경로(`fit_binning`+`iv_table`)로 train에서 재산출 권장(1.4 리포트 수치 인용보다 apples-to-apples).

### 아키텍처 가드레일
- **AD-2**: WOE/IV는 binning.py 단일 경로 재사용. 새 WOE 구현 금지.
- **AD-3**: 이 스토리는 scored frame이 아니라 raw + sample_design 재라벨을 쓴다(1.4와 동일 학습 경로) — frame 재계산 아님, 신규 파생변수의 독립 IV 산출.
- **NFR1**: 결정론적 — 상위 K 빈도는 train 고정 표본에서 결정(난수 없음).
- **누수 방지**: top_titles·binning 전부 **train에서만 fit**, valid/oot는 적용만.

### 스코프 가드 (하지 말 것)
- 정교한 NLP(어간추출·임베딩·불용어·동의어 사전) 금지 — AC 명시. 소문자화·특수문자 제거·빈도 매핑까지만.
- 키워드 의미 그룹핑(manager 계열 묶기) 금지 — 자의적, 효과 인위적 확대.
- `emp_length`·기타 변수 확장 금지 — AC는 emp_title만.
- emp_title을 챔피언/챌린저 모형에 실제 편입 금지 — 이 스토리는 **IV 기여도 검증**만(모형 재학습은 스코프 밖, 별도 의사결정).
- API 엔드포인트·대시보드 화면 추가 금지.

### 이전 스토리 인텔리전스 (3.1/1.4 인수인계)
- 1.4 교훈: `transform` 기본 `metric_missing=0`이 결측을 WOE 0으로 조용히 매핑 → `transform_woe`는 이미 `metric_missing="empirical"`로 고정됨. emp_title MISSING 카테고리도 이 경로로 처리하면 결측 빈의 실제 WOE 반영.
- 1.4 교훈: 저카디널리티/치우친 변수는 optbinning이 1개 빈으로 붕괴 가능 — emp_title_category가 특정 빈으로 쏠리면 IV가 왜곡될 수 있으니 빈 분포도 리포트에 기록.
- 3.1/2.4 공통: **실데이터 실행이 결론을 만든다** — 합성으로 파이프만 검증하고, 실제 IV는 반드시 real train에서 산출해 리포트에 기입.
- 정직성(2.4/3.1 톤): 네거티브 결과·한계를 숨기지 않는다.

### Project Structure Notes
- `scorecard/text_features.py` — MODIFIED(스텁 → 구현: clean_emp_title, fit_top_titles, map_emp_title_category, + IV 산출은 binning 재사용 래핑).
- `tests/test_text_features.py` — NEW.
- `docs/implementation-artifacts/text-features-report-3-2.md` — NEW(MDD 편입용).
- `app/`·`API_SPEC.md`·`scored_validation_frame` — 변경 없음.

### References
- [Source: docs/planning-artifacts/epics.md#Story-3.2] — AC 원문(FR16)
- [Source: ARCHITECTURE-SPINE.md#AD-2] — WOE 단일 경로(binning.py)
- [Source: scorecard/binning.py] — fit_binning(categorical)·transform_woe·iv_table 재사용
- [Source: scorecard/sample_design.py] — label_and_filter·split_by_vintage 학습표본 재구성
- [Source: docs/implementation-artifacts/binning-selection-report-1-4.md] — 정형 변수 IV·선정 기준(IV≥0.02 관행)
- [Source: data/lc_accepted_2012_2015_36m.parquet] — emp_title 실재·분포 확인(결측 6.7%, 고유 207,516)

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Completion Notes List

- **네거티브 결과 확정(이 스토리의 성공 형태)**: emp_title_category IV = **0.0116** — 업계 임계(0.02) 미만, 7개 정형 변수 전부보다 낮음(최약 정형 변수 purpose 0.0244). "비금융 텍스트는 이 데이터·이 방식에서 유의미한 추가 판별력 없음"을 정직하게 기록(AC #2 = 검증 자체가 산출물).
- **정형 변수 IV 비교(apples-to-apples)**: 동일 train(143,892건, 부도율 12.70%)에서 같은 코드경로(fit_binning+iv_table)로 재산출 — fico 0.1298 / annual_inc 0.0986 / dti 0.0422 / home_ownership 0.0346 / revol_util 0.0297 / inq 0.0284 / purpose 0.0244 / **emp_title 0.0116**.
- **약한 신호의 원인(리포트 기록)**: ①롱테일 → 상위 20개로도 88.8%가 OTHER 한 덩어리 ②직종·고용주 혼재(us army/bank of america/walmart가 상위) ③소득·연체 등 정형 변수에 이미 흡수.
- **AD-2 준수**: WOE/IV는 binning.py(optbinning categorical) 재사용, 공식 재구현 없음. **누수 방지**: top_titles·binning 전부 train fit.
- **정교한 NLP 미적용**(AC): clean은 소문자화+특수문자 제거+공백 정리까지만. 동의어(rn↔registered nurse) 병합·키워드 그룹핑 안 함(한계로 리포트 명시).
- **엔드포인트 없음**: app/·API_SPEC 변경 없음. 실증=실데이터 IV 산출.
- pytest **210 passed**(기존 203 + text_features 7).

### File List

- `scorecard/text_features.py` (MODIFIED — 스텁 → 구현: clean_emp_title, fit_top_titles, map_emp_title_category, derive_emp_title_category)
- `tests/test_text_features.py` (NEW — 7 tests: 텍스트 정제/매핑/누수경계 + 실데이터 binning 통합)
- `docs/implementation-artifacts/text-features-report-3-2.md` (NEW — MDD 편입용, IV 비교표+네거티브 결론+한계)

## Change Log

- 2026-07-16: 3-레이어 코드리뷰 — patch 8건 반영(tie-break 결정화·tautological IV 테스트 교체·누수 경계 OOT 실증·리포트 WOE 방향 표 추가·iv_comparison() 재현 경로 커밋·MISSING 메커니즘 문구 정정·docstring 정직화·방어 가드 4종). 발견: optbinning이 22개 카테고리를 2개 빈으로 병합(위험 쪽=usps·walmart·sales·MISSING, WoE −0.347) — 빈 붕괴 자체가 약신호 증거. pytest 215 passed. Status → done.
- 2026-07-16: Story 3.2 구현 — scorecard/text_features.py(clean/fit_top_titles/map_category, NLP 지양) + binning.py 재사용 IV 산출. 실데이터 결과 emp_title IV=0.0116(임계 미달, 전 정형변수보다 낮음) → "비금융 텍스트 유의미한 판별력 없음" 정직 기록(네거티브 결과=산출물). 리포트 작성(IV 비교표+원인+한계). 엔드포인트 없음. pytest 210 passed(+7). Status → review.
- 2026-07-16: Story 3.2 생성 — emp_title 실측(결측 6.7%·고유 207,516, 롱테일) 확인 후 상위 K 빈도 매핑 방식 결정, WOE/IV는 binning.py 재사용(AD-2)·학습표본은 sample_design 재라벨 재사용, 엔드포인트 없는 순수 분석 스토리임을 명시, "네거티브 결과도 산출물"(AC #2) 정직성 원칙과 NLP 지양 스코프 가드 작성.
