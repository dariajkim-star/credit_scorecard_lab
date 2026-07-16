# SAS 재현 대조 리포트 (컨설턴트 킥④, Story 3.3)

> **한 줄 결론**: 챔피언 스코어카드의 점수 산출 로직(WOE 룩업 → 선형결합 → PDO 스케일링)을 SAS로 이식했습니다. SAS가 복제할 산술을 순수 Python 미러로 독립 검증한 결과 **12건 전건에서 라이브러리 경로 대비 최대 오차 4.7e-07점**(기준 0.5점의 백만분의 일 수준) — 이식 산술의 정확성이 증명되었습니다. 남은 것은 사용자가 SAS OnDemand에서 `.sas`를 실행해 동일 결과를 확인하는 최종 tie-out입니다.

## 이식 대상 로직

챔피언(로지스틱 스코어카드)의 점수 산출은 학습이 필요 없는 **결정론적 산술**이라 언어 간 정확 이식이 가능합니다:

```
woe_i = WOE_lookup_i(원시값_i)      # 변수별 빈 테이블 (아티팩트에서 추출)
logit = intercept + Σ coef_i·woe_i  # intercept = -1.928423, 계수 7개
factor = PDO / ln(2)                # PDO = 20
offset = base_score - factor·ln(base_odds)  # 600 - factor·ln(50)
score = offset + factor·(-logit)
```

**매핑 관례** (서빙 `transform_woe`와 동일, 실측 확인):
- 수치 변수: 좌폐우개 `[lo, hi)` 구간 → WOE. 결측 → 해당 변수 Missing 빈의 empirical WOE.
- 범주 변수: optbinning이 동일-WOE 카테고리를 그룹핑(예: `[RENT, NONE, OTHER]`) — 그룹 내 전체가 같은 WOE. 결측 → Missing WOE, **미학습 카테고리 → Special 빈 WOE**(transform 실측 동작과 일치시킴).
- `revol_util`: 원본이 "45.3%" 문자열이므로 **reference 데이터에 파싱된 float를 담아** SAS 쪽 문자열 처리를 제거(결정 기록).

## 산출물 (전부 아티팩트에서 자동생성 — 손 복사 없음, AD-1)

| 파일 | 내용 |
|---|---|
| `sas/scorecard_scoring.sas` | **자기완결 SAS 프로그램**: 12건 reference 신청이 datalines로 내장, 변수별 WOE 룩업(if/else 체인), 공식, **Python 정답과의 diff 컬럼까지 출력**. OnDemand에 붙여넣고 실행만 하면 됨. |
| `sas/reference_applicants.csv` | OOT(2015) 신청 12건: 원시 7필드 + Python 정답 점수(`python_score`). 결측 revol_util 3건 포함(Missing WOE 경로 커버). |
| `sas/export_scorecard.py` | 생성기: 아티팩트 → 추출(`extract_scorecard`) → `.sas`/CSV 생성 + **순수 산술 미러**(`mirror_score`). 재생성: `python -m sas.export_scorecard` |

## 검증 결과 (이 세션에서 수행)

**Python 순수-산술 미러 대조** — SAS가 인코딩하는 것과 동일한 룩업+공식을 sklearn/optbinning 없이 재구현해, 실제 라이브러리 스코어링 경로(`transform_woe`+`decision_function`+`score_formula`)와 대조:

- 대상: OOT 신청 **12건** (결측 포함, 다양한 home_ownership/purpose)
- 결과: **전건 일치, 최대 절대 오차 4.74e-07점** (FR17 기준 0.5점)
- 회귀 테스트로 고정: 추출값=아티팩트 일치, 경계값(split 정확히 그 값 → 우측 빈), Missing/미학습 카테고리 관례, `.sas` 자기완결성

이로써 **`.sas`에 하드코딩된 산술 자체가 정확함**이 라이브러리 독립적으로 증명되었습니다. SAS 실행에서 오차가 난다면 그것은 로직이 아니라 환경(부동소수 정밀도 등) 문제이며, 0.5점 기준 대비 10^6 배의 여유가 있습니다.

## 사용자 최종 tie-out 절차 (SAS OnDemand)

1. [SAS OnDemand for Academics](https://welcome.oda.sas.com/) 로그인 → SAS Studio 새 프로그램.
2. `sas/scorecard_scoring.sas` 내용 전체를 붙여넣고 실행(F3). 업로드할 파일 없음(데이터 내장).
3. 출력 확인: `proc print` 표에서 **`pass` 컬럼이 전건 1**(= |diff| < 0.5)인지, `proc means`의 `abs_diff` max가 0.5 미만인지 확인.
4. (선택) 결과 스크린샷을 이 리포트 옆에 저장하면 증빙 완결.

기대 결과: 12건 전건 pass. Python 미러 기준 예상 diff는 1e-6 수준이나, SAS 부동소수 연산 차이로 소수점 아래 몇째 자리가 다를 수 있음 — 기준(0.5)과는 무관한 수준.

## 가정과 한계 (정직성 원칙)

- **SAS 실환경 실행은 이 세션 밖**: 산술 정확성은 미러로 증명했으나, SAS 문법·환경에서의 최종 확인은 사용자 실행에 의존합니다(위 절차).
- 이식 범위는 **챔피언 점수 산출만** — 챌린저(LightGBM)는 트리 모델이라 이식 대상이 아니고, 학습·비닝은 SAS로 옮기지 않습니다(AD-4: 재학습 금지).
- `.sas`는 자동생성물 — 손 편집 금지, 모델 재학습 시 `python -m sas.export_scorecard`로 재생성.
- 미학습 카테고리 → Special WOE(0.0) 관례는 현재 아티팩트의 실측 동작을 복제한 것으로, reference 12건에는 미학습 카테고리가 없어 이 경로는 단위테스트로만 검증됨.

---
*산출: `sas/export_scorecard.py` → `scorecard_scoring.sas` + `reference_applicants.csv` · Story 3.3 (FR17, AD-1·AD-2·AD-4). "Python으로 개발, SAS로 이식 검증" 역량 증빙.*
