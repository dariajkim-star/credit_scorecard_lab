# Story 2.1 리포트: Cutoff 트레이드오프 curve와 Swap-set 분석 (FR9, FR10)

`scorecard/strategy.py`(`cutoff_trade_off_curve`, `lookup_cutoff`, `swap_set_table`)로
`data/scored_validation_frame.parquet`(AD-3, 891,192행)을 실측 실행한 결과다. 예측 재계산
없이 frame의 `score`/`bad_flag`만 소비한다(AD-3).

## Task 3 결정 기록 — 분석 모집단은 OOT(2015)만 기본값

frame은 valid(2014, 162,570명)와 oot(2015, 283,026명) 두 빈티지를 포함한다. valid는 Epic 1의
등급 임계치·PSI 베이스라인 산출에 이미 쓰였으므로 향후 심사 전략을 시뮬레이션하는 용도로는
낙관적으로 편향될 수 있다. oot는 두 모델 모두 학습에 쓰지 않은 미래 시점 근사이므로, 이번
스토리의 함수들은 **`vintage=2015(OOT_VINTAGE)`를 기본값**으로 둔다. `vintage=None`을 넘기면
valid+oot 전체 모집단(445,596명)으로도 조회 가능하다 — 두 결과 모두 아래에 실측했다.

## Cutoff 트레이드오프 Curve (FR9) — OOT, 101포인트 그리드 중 10구간 발췌

### 챔피언

| cutoff | approval_rate | bad_rate | approved_count |
| ---: | ---: | ---: | ---: |
| 491.14 | 1.0000 | 0.1489 | 283,026 |
| 502.11 | 0.9995 | 0.1488 | 282,877 |
| 513.09 | 0.9886 | 0.1471 | 279,805 |
| 524.06 | 0.9186 | 0.1382 | 260,001 |
| 535.03 | 0.7345 | 0.1195 | 207,890 |
| 546.01 | 0.4771 | 0.0949 | 135,034 |
| 556.98 | 0.2450 | 0.0682 | 69,331 |
| 567.96 | 0.1015 | 0.0452 | 28,735 |
| 578.93 | 0.0341 | 0.0287 | 9,642 |
| 589.91 | 0.0081 | 0.0279 | 2,292 |
| 600.88 | 0.0002 | 0.0317 | 63 |

### 챌린저

| cutoff | approval_rate | bad_rate | approved_count |
| ---: | ---: | ---: | ---: |
| 507.12 | 1.0000 | 0.1489 | 283,026 |
| 564.92 | 0.1018 | 0.0432 | 28,802 |
| 622.71 | 0.0006 | 0.0184 | 163 |
| 680.51 | 0.0006 | 0.0185 | 162 |
| (이후 구간부터 최상위 161명 근방에서 정체 — 챌린저 score 분포의 롱테일) |

**단조성 확인**: 두 모델 모두 cutoff 증가에 따라 `approval_rate`가 non-increasing(전 구간
101포인트 실측, 위반 없음). cutoff가 관측 score 최대값(챌린저 1085.07)을 넘는 지점은 그리드에
포함하지 않으므로(관측 범위 밖은 정의상 근사치 없음), 최저 approval_rate는 정확히 0이 아니라
최상위 1명(1/283,026)에 수렴한다 — `cutoff_trade_off_curve`의 설계상 특성이며 pytest
(`test_cutoff_trade_off_curve_covers_full_approval_range`)로 고정했다.

## 특정 Cutoff 즉시 조회 (FR9) — `lookup_cutoff` 예시

cutoff = 546.01 (그리드 중앙값 예시):

| model | approval_rate | bad_rate | approved_count |
| --- | ---: | ---: | ---: |
| champion | 0.4771 | 0.0949 | 135,023 |
| challenger | 0.4415 | 0.0900 | 124,957 |

같은 cutoff에서 챌린저가 챔피언보다 더 보수적으로 승인한다(승인율 44.2% vs 47.7%)는 것이
곧바로 swap-set 분석으로 이어진다.

## Swap-set 분석 (FR10) — cutoff = 546.01

### OOT(2015)만, 모집단 283,026명

| segment | count | bad_rate |
| --- | ---: | ---: |
| swap_in (챔피언 거절→챌린저 승인) | 5,049 | 0.1355 |
| swap_out (챔피언 승인→챌린저 거절) | 15,115 | 0.1495 |
| stable_approved (양쪽 승인) | 119,908 | 0.0881 |
| stable_rejected (양쪽 거절) | 142,954 | 0.2003 |
| **합계** | **283,026** | — |

4분면 합계(5,049 + 15,115 + 119,908 + 142,954 = 283,026)가 모집단과 정확히 일치함을 확인했다
(AC 성공기준).

**해석**: `swap_out` 집단(챔피언은 승인하지만 챌린저는 거절하는 15,115명)의 부도율(14.95%)이
`stable_approved`(8.81%)보다 뚜렷이 높다 — 챌린저로 교체 시 이 집단을 걸러내면서 승인
포트폴리오의 위험이 낮아진다는 방향과 일치한다. 반대로 `swap_in`(5,049명, 부도율 13.55%)은
`stable_rejected`(20.03%)보다는 안전하지만 `stable_approved`보다는 위험한 중간 집단 — 챌린저가
새로 승인하는 인원이 기존 승인 인원보다 약간 더 위험함을 뜻한다.

### 참고: valid+oot 전체, 모집단 445,596명

| segment | count | bad_rate |
| --- | ---: | ---: |
| swap_in | 8,145 | 0.1294 |
| swap_out | 23,098 | 0.1429 |
| stable_approved | 184,777 | 0.0848 |
| stable_rejected | 229,576 | 0.1935 |

방향성은 OOT-only와 동일 — Task 3의 결정(OOT를 기본 모집단으로)이 valid 포함 여부와 무관하게
일관된 결론을 낸다는 것을 뒷받침한다.

## 실데이터 재실행 스니펫

```python
import pandas as pd
from scorecard.strategy import cutoff_trade_off_curve, lookup_cutoff, swap_set_table

df = pd.read_parquet("data/scored_validation_frame.parquet")

curve = cutoff_trade_off_curve(df, "champion")          # 기본값: OOT(2015)만
point = lookup_cutoff(df, "champion", cutoff=546.01)
swaps = swap_set_table(df, cutoff=546.01)                 # 기본값: OOT(2015)만
swaps_full = swap_set_table(df, cutoff=546.01, vintage=None)  # valid+oot 전체
```

## 검증

- `pytest -q` — 전체 101 passed(기존 92 + 신규 9), 회귀 없음.
- `tests/test_strategy.py::test_real_scored_frame_bad_flag_consistent_across_models` — 실데이터
  기준 챔피언/챌린저 행의 `bad_flag`가 동일 applicant에서 100% 일치함을 확인(swap_set_table이
  챔피언 쪽 `bad_flag`만 ground truth로 쓰는 전제 검증).
- AD-3 위반 없음 — `models/artifacts/*.joblib`, `scorecard/binning.py`, `champion.py`,
  `challenger.py`를 이 스토리 코드 어디서도 import/호출하지 않는다(`scorecard/strategy.py`
  import 목록: `numpy`, `pandas`만).
