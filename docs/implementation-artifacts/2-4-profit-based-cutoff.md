---
baseline_commit: 3b82d52
---

# Story 2.4: 손익 기반 Cutoff (컨설턴트 킥①)

Status: review

## Story

As a 경영진 보고를 준비하는 컨설턴트,
I want 리스크 지표가 아닌 실현손익 기준의 최적 cutoff과 1페이저를 얻고,
so that "cutoff 조정 시 연간 기대손익이 얼마 변하는가"로 심사 전략을 제안할 수 있다.

## Acceptance Criteria

**Given** validation frame의 `int_rate`·`recoveries`·`total_pymnt` 컬럼
**When** `scorecard/profit.py`로 건별 실현손익을 집계하면

1. 현재 대비 최적 cutoff의 승인율·연간 기대손익 delta가 산출된다 (FR14)
2. `/v1/simulate/profit-cutoff` 엔드포인트가 API_SPEC.md §7 스키마로 동작하고 `assumptions` 필드가 항상 포함된다 (NFR7, AD-5)
3. 판정 로직은 순수 규칙·통계 함수다 — LLM/외부 API 호출 없음 (AD-7)
4. 경영진 보고용 1페이저(md)가 산출된다 — 에픽 DoD 데모 산출물

> 성공기준 계량화(스토리 오너 보강): 위 4개 AC + `pytest -q` 초록 + 실데이터 실행 + **라이브 uvicorn 실증**(2.3 DoD 계승 — TestClient만으로 끝내지 않음). `optimal_cutoff`가 `current_cutoff`(2.1의 기존 546.0 관행값 재사용 권장, 근거는 Dev Notes 결정 기록) 대비 `expected_annual_profit`을 낮추지 않는 cutoff이어야 한다(그리드 탐색으로 정의상 보장됨 — 최적화 목적함수가 그 값이므로).

## Tasks / Subtasks

- [x] Task 1: 실현손익 데이터 갭 해소 — `loan_amnt` 조인 (AC: #1, 전제)
  - [x] **오픈퀘스천(반드시 결정하고 기록)**: `scored_validation_frame.parquet`에는 `int_rate`/`recoveries`/`total_pymnt`/`bad_flag`만 있고 **원 대출원금(`loan_amnt`)이 없다** — 건별 실현손익(수익-손실)을 절대 금액으로 계산하려면 원금이 필요. 이 스토리를 위해 실측 확인: 원본 `data/lc_accepted_2012_2015_36m.parquet`의 `id`(string) ↔ frame의 `applicant_id`(string) **100% 조인 매치**(589,635행 중 실측 확인). **결정**: frame을 재작성하지 않고(AD-3, 불변) `scorecard/profit.py`가 **읽기 전용으로 raw parquet의 `loan_amnt`만 조인 augment**(frame의 score/pd/grade 등 기존 컬럼은 절대 재계산·수정하지 않음 — 순수 소비 원칙 유지, 새 컬럼 추가만). 이 결정과 근거를 리포트에 기록.
  - [x] `_load_profit_frame(frame_df, raw_parquet_path) -> pd.DataFrame`: frame(OOT vintage만, 2.1의 `OOT_VINTAGE` 재사용) + raw의 `id`/`loan_amnt`를 `applicant_id`==`id`로 left join. 매치 실패 행(있다면) 처리 방침 결정·기록(현재 실측상 미스매치 0건이지만 방어적으로 다뤄야 함 — fail-fast 권장, sample_design.py의 "split이 비면 ValueError" 관례 참고).
- [x] Task 2: 건별 실현손익 계산 (AC: #1, #3, FR14)
  - [x] `realized_profit(loan_amnt, total_pymnt, recoveries) -> float` — 표준 신용 P&L: `total_pymnt + recoveries - loan_amnt`(수취액 + 회수액 - 원금 = 순손익, 양수=이익 음수=손실). 순수 함수, 벡터화(pandas Series 입력도 가능하게).
  - [x] `realized_return_rate(loan_amnt, total_pymnt, recoveries) -> float` — `realized_profit / loan_amnt`(대출 규모 대비 수익률, 무차원) — **다른 loan_amnt를 가진 대출들을 비교·평균하려면 반드시 비율화해야 함**(절대 손익을 그냥 더하면 큰 대출이 왜곡). `expected_annual_profit` 산출 시 이 비율의 평균에 `avg_loan_amnt`(요청 파라미터)를 곱해 대표 손익으로 환산.
  - [x] AD-7 준수: 규칙·산술 함수만. LLM/외부 API 호출 금지(애초에 필요 없음).
- [x] Task 3: cutoff별 기대손익 곡선·최적값 (AC: #1)
  - [x] `profit_cutoff_curve(profit_frame, model_type, cutoffs=None) -> pd.DataFrame` — 2.1 `strategy.cutoff_trade_off_curve`와 동일한 그리드 패턴(`_default_cutoff_grid` 재사용 검토 — import해서 쓸 것, 재구현 금지) 재사용. 각 cutoff에서: 승인집단(`score>=cutoff`)의 `mean(realized_return_rate)` → `avg_loan_amnt`와 **연간 예상 승인 건수**(오픈퀘스천 — 아래 참고)를 곱해 `expected_annual_profit` 산출.
  - [x] **오픈퀘스천(반드시 결정하고 기록)**: "연간 기대손익"을 내려면 "연간 승인 건수" 가정이 필요한데 AC/SPEC 어디에도 명시가 없다. 검증 표본(OOT, 283,026행/36개월물)의 승인 건수를 **연환산**(예: 표본 기간이 실질적으로 몇 개월 분량인지 가정)하는 방식과, 단순히 "표본 규모=연간 볼륨"으로 가정하는 방식 중 하나를 정하고 `assumptions` 배열에 반드시 명시(AC #2가 요구). 스토리오너 결정 권장: 후자(표본=연간 볼륨 가정, 가장 단순하고 투명함) — 근거를 1페이저·리포트에 기록.
  - [x] `find_optimal_cutoff(curve_df) -> float` — `expected_annual_profit` 최댓값의 cutoff.
- [x] Task 4: `/v1/simulate/profit-cutoff` 엔드포인트 (AC: #2, AD-5, AD-9)
  - [x] 요청: `{"model": "champion"|"challenger", "avg_loan_amnt": float}`(API_SPEC §7). `app/schemas.py`에 스키마 추가.
  - [x] 응답: API_SPEC §7 그대로 — `current_cutoff`/`optimal_cutoff`/`current`/`optimal`/`delta`/`curve`/`assumptions`. `current_cutoff`는 2.1 리포트가 실증에 쓴 546.0을 기본값으로 재사용할지 스토리오너가 결정·기록(대안: 등급 임계치 중 하나 등 — Dev Notes에 후보 남김).
  - [x] **`app/`은 조립만**(AD-9, 2.3 관례 계승) — `profit.py`가 계산을 소유, app은 startup 시 1회 profit curve 사전계산(2.3의 cutoff curve 캐싱과 동일 패턴, `ModelStore`에 필드 추가) 후 요청 시 조회.
  - [x] `assumptions` 배열은 **항상 비어있지 않다**(AC #2 명시) — 연간 볼륨 가정, 회수율 실측치 사용(향후 매크로 변화 미반영) 등 API_SPEC 예시 문구 재사용/보강.
- [x] Task 5: 경영진 1페이저 (AC: #4)
  - [x] `docs/implementation-artifacts/profit-cutoff-onepager-2-4.md` — 실데이터로 산출한 current/optimal/delta 수치, 그래프 설명(cutoff vs expected_annual_profit), "왜 이 cutoff이 더 낫다고 판단하는지"를 비전문가도 읽을 수 있는 문장으로. 컨설턴트 산출물이므로 가정을 투명하게 명시(API_SPEC 헤더 "손익 시뮬레이션이지 실제 재무 데이터 아님" 원칙 그대로 반영).
- [x] Task 6: pytest + 실증 (AC: 전체)
  - [x] `tests/test_profit.py` — realized_profit 부호(이익/손실 케이스), realized_return_rate 스케일 불변성(loan_amnt 다른 두 대출이 같은 수익률이면 같은 rate), profit_cutoff_curve 단조성 없음이 정상(risk curve와 달리 손익은 non-monotonic일 수 있음 — 억지로 단조 어설션 넣지 말 것), find_optimal_cutoff가 실제로 curve의 max와 일치.
  - [x] `tests/test_app.py`에 profit-cutoff 엔드포인트 테스트 추가 — 정상 응답, assumptions 비어있지 않음, delta 계산이 current/optimal 대조와 일치.
  - [x] `pytest -q` 전체 통과(기존 151 + 신규).
  - [x] 실데이터 조인 실행 + 라이브 uvicorn으로 `/v1/simulate/profit-cutoff` 실제 HTTP 호출 실증.

## Dev Notes

### 이 스토리의 성격 — 첫 "판정 없는 컨설팅 산출물" 스토리
Epic 3 "컨설턴트 킥"의 사실상 선발대(에픽 계획서상 킥①이 여기 Epic 2 말미로 당겨짐 — 3.1 룰효율성진단과 함께 "모델러 아닌 심사전략 컨설턴트" 포지셔닝 목적). 이 스토리부터 산출물의 청자가 "개발자"가 아니라 "경영진"이 된다 — 1페이저는 숫자 정확성 못지않게 **가정의 투명성**이 핵심(API_SPEC 헤더 원칙: "손익 시뮬레이션이지 실제 재무 데이터 아님").

### 핵심 갭: frame에 loan_amnt가 없다 (실측 확인)
```python
import pandas as pd
frame = pd.read_parquet("data/scored_validation_frame.parquet", columns=["applicant_id"])
raw = pd.read_parquet("data/lc_accepted_2012_2015_36m.parquet", columns=["id", "loan_amnt"])
merged = frame.merge(raw, left_on="applicant_id", right_on="id", how="left")
merged["loan_amnt"].notna().mean()  # == 1.0, 실측 확인(589,635행 전수 매치)
```
`applicant_id`(frame)와 `id`(raw)는 둘 다 문자열(string dtype)로 저장돼 있어 타입 캐스팅 없이 바로 조인 가능(실측 확인 완료 — 재확인 불필요).

### AD-3 준수 판단 — 조인은 위반이 아니다
AD-3(frame 소비만, 재계산 금지)는 **frame이 이미 담고 있는 값**(score/pd/grade/bad_flag)을 이 스토리가 재계산하지 않는다는 뜻이지, frame에 없는 컬럼(loan_amnt)을 다른 목적(손익 계산)으로 raw에서 읽어와 augment하는 것까지 막지 않는다 — 2.2도 raw parquet을 읽어 신규 신청 컨텍스트를 만들었다(다른 목적이지만 "raw 읽기 자체가 금지"는 아님을 보여주는 선례). **다만 반드시 지킬 것**: frame의 기존 컬럼(`score`,`pd`,`grade`,`bad_flag`,`int_rate`,`recoveries`,`total_pymnt`)은 그대로 두고 `loan_amnt` 컬럼만 옆에 붙인다 — merge 결과를 다시 `scored_validation_frame.parquet`에 덮어쓰지 않는다(frame은 Epic 1 산출물로 불변, `profit.py` 내부 로컬 변환일 뿐).

### 재사용 지도
- `strategy.OOT_VINTAGE`, `strategy._default_cutoff_grid`(private이지만 같은 패키지 내 재사용 검토 — 혹은 동일 로직을 profit.py가 독립 구현할지 스토리오너 판단. 권장: import해서 재사용, cutoff 그리드 생성 로직이 2.1과 갈라지면 두 곡선의 cutoff 값이 미묘하게 달라져 대시보드(2.5)에서 나란히 비교할 때 혼란)
- `scorecard.config.ACCEPTED_PARQUET`(원본 raw parquet 경로 상수, 2.2가 이미 사용) — 새로 경로 문자열 만들지 말 것.
- `app/loader.py`의 startup 사전계산 패턴(2.3의 `store.curves`) — profit curve도 동일하게 `store.profit_curves: dict[str, pd.DataFrame]`로 시작 시 1회 계산.
- **`avg_loan_amnt`는 요청 파라미터**(API_SPEC §7) — profit.py 함수들은 이 값을 인자로 받아야지 하드코딩하면 안 됨.

### 아키텍처 가드레일
- **AD-7**: `profit.py`의 판정(어느 cutoff이 "최적"인지)은 순수 그리드 탐색 최댓값 — LLM 호출 금지.
- **AD-3**: frame 컬럼 재계산 금지(위 설명대로 augment는 허용).
- **AD-5**: API_SPEC §7이 이미 확정 스키마 — 필드명 그대로 구현.
- **AD-9**: app은 조립만, profit.py가 계산 소유.
- **NFR1**: 결정론적 — 그리드 탐색에 난수 없음.

### 스코프 가드 (하지 말 것)
- 룰 효율성 진단(3.1 rule_efficiency.py) 금지 — 이 스토리는 cutoff 손익만.
- 매크로 전망·미래 금리 변화 반영 금지 — "회수율은 실측치 사용, 향후 매크로 변화 미반영"을 assumptions에 명시하는 것으로 충분(API_SPEC 예시 문구 그대로).
- `/v1/score`·`/v1/simulate/cutoff`(2.3) 로직 재구현 금지 — 이미 있는 것 재사용.

### 이전 스토리 인텔리전스 (2.3 인수인계)
- 2.3 리뷰 교훈: 등급/cutoff 경계 산정 시 방향(포함/배타)을 명시적으로 문서화할 것 — 이 스토리의 cutoff 그리드도 동일 원칙 적용(단, profit curve는 risk curve와 달리 단조성이 없으므로 "최댓값 탐색"이지 "경계값 lookup"이 아님 — 다른 문제).
- 2.3 리뷰 교훈: 배치/그리드 계산에서 NaN 관통 가드 필수(realized_return_rate가 `loan_amnt=0`이면 0-division — 실데이터에 0인 행이 있는지 확인 후 가드).
- 2.2/2.3 공통: 실행이 버그를 잡는다 — 반드시 실데이터 조인·계산을 실행해보고 수치가 상식적인지(예: 기대손익이 승인율 0%에서 0, 극단 cutoff에서 이상치 없는지) 확인할 것.

### Project Structure Notes
- `scorecard/profit.py` — MODIFIED(스텁 → 구현, CAP-14).
- `app/loader.py`, `app/schemas.py`, `app/main.py` — MODIFIED(엔드포인트 추가).
- `tests/test_profit.py` — NEW.
- `tests/test_app.py` — MODIFIED(엔드포인트 테스트 추가).
- `docs/implementation-artifacts/profit-cutoff-onepager-2-4.md` — NEW.

### References
- [Source: docs/planning-artifacts/epics.md#Story-2.4] — AC 원문(FR14, NFR7, AD-7, AD-5)
- [Source: API_SPEC.md §7] — 요청/응답 스키마 원문
- [Source: ARCHITECTURE-SPINE.md#AD-3,AD-7,AD-9] — frame 소비 원칙, 규칙기반 판정, app 의존 방향
- [Source: scorecard/strategy.py] — cutoff 그리드·curve 패턴 선례(2.1)
- [Source: app/loader.py] — startup 사전계산·ModelStore 패턴 선례(2.3)
- [Source: data/scored_validation_frame.parquet, data/lc_accepted_2012_2015_36m.parquet] — 실측 조인 매치율 100% 확인

## Dev Agent Record

### Agent Model Used

claude-fable-5 (bmad-dev-story, /loop 자율 진행)

### Debug Log References

- `realized_return_rate`에 `loan_amnt=0` 가드 추가(0-division 방지) — 실데이터 확인상 발생 안 하지만(min $1,000) 방어적으로 fail-fast 처리.
- `find_optimal_cutoff`가 `curve.loc[idxmax()]`로 그리드 최댓값을 정확히 찾는지 합성 데이터로 검증 — 첫 실행에 통과(공식이 단순해 버그 표면이 작았음, 2.1의 "frame 소비만"에 비해 이 스토리는 "새 원천 조인"이 유일한 리스크 지점이었고 그건 실측으로 사전에 100% 확인해둔 상태였음).
- app 레이어: profit curve가 avg_loan_amnt에 선형 비례한다는 사실을 이용해 시작 시 `avg_loan_amnt=1.0`으로 1회만 계산해두고 요청마다 스칼라 곱만 수행 — 2.3의 risk curve 캐싱과 동일 패턴, 283k행 재스캔을 요청마다 반복하지 않음.
- **실데이터 실행 결과 자체가 놀라운 발견**: 두 모델 모두 손익 최적 cutoff이 현재(리스크 기준) cutoff보다 훨씬 낮고(챔피언 494.4 vs 546.0), 최적점에서 승인율이 거의 100%로 수렴 — 이자수익이 부도손실을 상쇄하는 구간이 리스크 관점의 거절 영역까지 뻗어 있음을 시사. 1페이저에 발견과 함께 한계(7변수 축소모형이라는 전제)를 명시.

### Completion Notes List

- **오픈퀘스천 2건 결정**: ①연간 볼륨=OOT 표본 규모 그대로(확대 계수 없음, 가장 투명) ②current_cutoff=546.0(2.1 재사용). 둘 다 `assumptions`/1페이저에 근거 기록.
- **loan_amnt 조인**: `load_profit_frame`이 raw parquet에서 읽기 전용 조인(AD-3 비위반 판단 — frame 기존 컬럼 불변, augment만). 미매치 행 발생 시 fail-fast(`ValueError`), 실데이터는 100% 매치 재확인.
- **API 응답이 avg_loan_amnt에 선형 비례함을 테스트로 고정**(`test_profit_cutoff_scales_linearly_with_avg_loan_amnt`) — 사전계산 캐싱 최적화가 정확한지 검증하는 회귀 테스트 역할도 겸함.
- **AD-7 준수**: `find_optimal_cutoff`는 순수 argmax, LLM/외부 API 호출 없음.
- **라이브 실증 완료**: uvicorn 기동 후 챔피언·챌린저 양쪽 모두 실제 HTTP로 확인, 수치가 TestClient 결과와 일치.
- pytest **167 passed**(기존 151 + profit 11 + app 5). p95 재측정 33.6ms(영향 없음).

### File List

- `scorecard/profit.py` (MODIFIED — 스텁 → 구현: realized_profit, realized_return_rate, load_profit_frame, profit_cutoff_curve, find_optimal_cutoff)
- `app/loader.py` (MODIFIED — ACCEPTED_PARQUET import, CURRENT_CUTOFF 상수, profit_frame 조인+profit_base_curves 사전계산)
- `app/schemas.py` (MODIFIED — ProfitCutoffRequest/Response 등 API_SPEC §7 스키마)
- `app/main.py` (MODIFIED — `/v1/simulate/profit-cutoff` 엔드포인트)
- `tests/test_profit.py` (NEW — 11 tests)
- `tests/test_app.py` (MODIFIED — profit-cutoff 엔드포인트 테스트 5건 추가)
- `docs/implementation-artifacts/profit-cutoff-onepager-2-4.md` (NEW — 경영진 1페이저, 실데이터 수치+한계 명시)

## Change Log

- 2026-07-16: Story 2.4 생성 — 핵심 데이터 갭(frame에 loan_amnt 없음) 실측 발견·해소 방안(raw parquet 조인, AD-3 비위반 판단) 결정 기록, 오픈퀘스천 2건(연간 볼륨 가정, current_cutoff 기준값) 스토리오너 결정 필요로 명시, 2.1/2.3 재사용 지도 작성.
- 2026-07-16: Story 2.4 구현 — scorecard/profit.py + /v1/simulate/profit-cutoff 엔드포인트. 실데이터 실행 결과 두 모델 모두 손익 최적 cutoff이 현재보다 훨씬 낮음을 발견(챔피언 494.4 vs 546.0, 챌린저 507.1 vs 547.6), 승인율 거의 100%가 손익 최적점. 1페이저 작성(한계 명시 포함). 라이브 uvicorn 실증(챔피언·챌린저 양쪽). pytest 167 passed(+16). Status → review.
