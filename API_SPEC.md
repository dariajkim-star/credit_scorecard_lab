# credit-scorecard-lab — API 명세서 v0.3

> v0.3 (2026-07-16, Story 2.3): §4 입력 스키마를 FR-5 변수선정 확정 결과(7필드)로 교체(§4의 기존 12필드는 확정 전 예상 후보였음 — AD-5 스펙 선수정). reason_codes는 실제 불리 요인만 반환(0점 요인 미포함 — 3개 미만 가능, Story 2.2 결정). §6 응답에 `bad_rate_rejected` 명시.

> 스코어링 서빙 API. 판정(승인/거절)은 이 API의 책임이 아님 — 점수·PD·등급·사유를 반환하고, cutoff 적용은 소비자(대시보드·P3 에이전트)의 몫.
> Base URL: `http://localhost:8000` · 모든 업무 엔드포인트는 `/v1` prefix.

## 0. 공통

- 인증: 없음 (로컬 개발용). P3 연동 시에도 로컬 네트워크 한정.
- 응답 공통 필드: 모든 스코어링 응답에 `model` 블록(모델명·버전·유형) 포함 — 감사 추적용.
- 에러 포맷 (FastAPI 표준 + 확장):

```json
{ "detail": "메시지", "error_code": "MODEL_NOT_LOADED" }
```

| HTTP | error_code | 상황 |
|---|---|---|
| 422 | (FastAPI 기본) | 요청 스키마 위반 (필수 필드 누락, 타입 오류) |
| 400 | VALUE_OUT_OF_RANGE | 값이 학습 범위를 심하게 벗어남 (예: dti=999). 비닝상 처리 가능해도 신뢰 불가 경고 |
| 503 | MODEL_NOT_LOADED | 모델 아티팩트 미로드 |

## 1. GET /health

서비스·모델 로드 상태.

```json
{ "status": "ok", "model_loaded": true, "model_version": "scorecard-v1.0.0" }
```

모델 미로드 시 `status: "degraded"` + HTTP 200 (P3가 도구 가용성 판단에 사용).

## 2. GET /v1/model/info

모델 메타데이터 + 검증 성능. 대시보드 헤더·MDD 링크용.

```json
{
  "champion": {
    "name": "logistic-scorecard", "version": "1.0.0",
    "trained_at": "2026-07-20", "pdo": 20, "base_score": 600,
    "metrics": { "auc_oot": 0.71, "ks_oot": 0.27, "psi_score": 0.04 }
  },
  "challenger": {
    "name": "lightgbm", "version": "1.0.0", "calibration": "isotonic",
    "metrics": { "auc_oot": 0.74, "ks_oot": 0.31 }
  },
  "sample_design": {
    "train_vintages": "2012-2013", "valid_vintage": "2014", "oot_vintage": "2015",
    "bad_definition": "loan_status in (Charged Off, Default), 36-month term"
  }
}
```

`metrics.psi_score`는 valid→OOT 점수 PSI(서빙이 소비 가능한 것은 `scored_validation_frame`의 valid+oot뿐 — 1.7b 리포트의 train→OOT PSI와는 다른 비교축, 둘 다 <0.1 목표는 동일).

## 3. GET /v1/grades

등급 체계 테이블 (등급별 점수 구간·관측 부도율).

```json
{
  "model": "champion",
  "grades": [
    { "grade": 1, "score_min": 567.28, "score_max": null, "observed_bad_rate": 0.0463 },
    { "grade": 2, "score_min": 559.05, "score_max": 567.28, "observed_bad_rate": 0.0801 }
  ],
  "monotonic_validated": true
}
```

- `?model=champion|challenger`(기본 champion) — 두 모델의 등급 임계치가 다르므로 모델별 표.
- **경계는 우측폐구간**(`(score_min, score_max]`, `pd.cut` 관례): `score_min`은 배타적, `score_max`는 포함. 정확히 `score_min`과 같은 점수는 이 등급이 아니라 한 단계 아래(더 낮은) 등급이다.
- `pd_max` 필드는 제공하지 않는다(v0.2 예시에 있었으나 등급별 PD 상한을 산출하는 로직이 스코프에 없음 — 등급은 점수 분위수 기반, PD는 관측 부도율로만 노출).

## 4. POST /v1/score — 단건 스코어링 (핵심)

### 요청

입력 필드는 IV 변수선정(FR-5, Story 1.4) 결과로 **7개 필드로 확정** (manifest `feature_order`와 동일 — 신청 시점에 알 수 있는 필드만, 기준시점 원칙):

```json
{
  "fico_range_low": 690,
  "annual_inc": 65000,
  "dti": 18.5,
  "home_ownership": "MORTGAGE",
  "revol_util": 42.3,
  "inq_last_6mths": 1,
  "purpose": "debt_consolidation"
}
```

- 모든 필드 `null` 허용 (WOE Missing 빈으로 처리, Story 1.4 metric_missing 계약) — 단 전 필드 null 요청은 422
- `model` 쿼리 파라미터: `champion`(기본) | `challenger` | `both`

### 응답 (200)

```json
{
  "score": 646,
  "pd": 0.061,
  "grade": 4,
  "reason_codes": [
    { "rank": 1, "variable": "revol_util", "description": "리볼빙 한도 소진율이(가) 심사 기준 대비 불리하여 점수가 22.0점 하락했습니다.", "points_lost": 22.0 },
    { "rank": 2, "variable": "inq_last_6mths", "description": "최근 6개월 신용조회 건수이(가) 심사 기준 대비 불리하여 점수가 11.0점 하락했습니다.", "points_lost": 11.0 },
    { "rank": 3, "variable": "dti", "description": "부채비율(DTI)이(가) 심사 기준 대비 불리하여 점수가 9.0점 하락했습니다.", "points_lost": 9.0 }
  ],
  "warnings": [],
  "model": { "name": "champion", "version": "champion-1.0.0", "type": "champion" }
}
```

- `reason_codes`: 챔피언=특성별 점수손실 상위 3, 챌린저=SHAP 상위 3 (필드 구조 동일 — `rank`/`variable`/`description` 공유, 값 필드만 `points_lost` ↔ `shap_value`, Story 2.2 AD-6). **실제로 불리한 요인만 포함**(0점 요인 제외) — 3개 미만일 수 있다.
- `model=both` 시 `{ "champion": {...}, "challenger": {...}, "score_gap": ... }` 형태 — swap-set 데모용
- `warnings`: 결측 필드·미학습 카테고리 값 등 비차단 경고 목록(문자열)

## 5. POST /v1/score/batch

CSV 업로드 대신 JSON 배열 (최대 1,000건). 응답은 단건 응답의 배열 + 요약(`grade_distribution`). 대시보드·swap-set 분석용.

## 6. POST /v1/simulate/cutoff

cutoff 시뮬레이션 — 검증 표본(서버 내장) 기준.

### 요청
```json
{ "cutoff_score": 640, "model": "champion" }
```

### 응답
```json
{
  "cutoff_score": 640,
  "approval_rate": 0.72,
  "bad_rate_approved": 0.043,
  "bad_rate_rejected": 0.19,
  "curve": [ { "cutoff": 600, "approval_rate": 0.88, "bad_rate": 0.062 } ]
}
```

`curve`는 전 구간 트레이드오프 곡선 (대시보드 차트 데이터).

## 7. POST /v1/simulate/profit-cutoff — 손익 기반 cutoff (킥①)

리스크 지표(부도율)가 아닌 **실현 손익**으로 cutoff을 평가. `int_rate`(수익) vs `recoveries`/`total_pymnt` 기반 손실을 검증 표본에서 건별 집계.

### 요청
```json
{ "model": "champion", "avg_loan_amnt": 12000 }
```

### 응답
```json
{
  "current_cutoff": 640,
  "optimal_cutoff": 655,
  "current": { "approval_rate": 0.72, "expected_annual_profit": 184000000 },
  "optimal": { "approval_rate": 0.66, "expected_annual_profit": 201000000 },
  "delta": { "approval_rate_pp": -6.0, "annual_profit_krw": 17000000 },
  "curve": [ { "cutoff": 600, "approval_rate": 0.88, "expected_annual_profit": 150000000 } ],
  "assumptions": ["평균 대출금액·건수는 검증 표본 분포로 스케일링", "회수율은 recoveries/total_pymnt 실측치 사용, 향후 매크로 변화 미반영"]
}
```

- 이 값은 손익 시뮬레이션이지 실제 재무 데이터 아님 — `assumptions`로 가정을 항상 명시 (컨설팅 산출물의 정직성 원칙)

## 8. GET /v1/rules/efficiency — 룰 효율성 진단 (킥②)

가상 하드룰셋을 검증 표본에 적용해 룰별 배제 효과를 진단.

### 응답
```json
{
  "rules": [
    {
      "rule_id": "DTI_GT_40", "description": "DTI > 40 거절",
      "excluded_count": 1820, "excluded_bad_rate": 0.091, "population_bad_rate": 0.052,
      "opportunity_loss_est": 12000000,
      "verdict": "유지 권장 — 배제집단 부도율이 모집단 대비 1.75배"
    },
    {
      "rule_id": "SCORE_REDUNDANT_INQ", "description": "최근 6개월 조회 2건↑ 거절",
      "excluded_count": 640, "excluded_bad_rate": 0.058, "population_bad_rate": 0.052,
      "opportunity_loss_est": 4300000,
      "verdict": "재검토 권장 — 모형 점수와 판별력 중복, 배제 효과 미미"
    }
  ]
}
```

- `verdict`는 배제집단 부도율/모집단 부도율 비율 + 모형 점수와의 중복도(상관)로 규칙 기반 산출 (LLM 생성 아님 — P3의 "결정은 룰과 모형" 원칙과 일관)

## 9. 버저닝·P3 연동 계약

- 스키마 변경은 `/v1` 내 하위호환(필드 추가만), 파괴적 변경 시 `/v2`
- P3(loan-agent-lab)는 `/health` → `/v1/score?model=champion` → `/v1/grades` 순으로 소비. reason_codes의 `description`은 심사의견서에 그대로 인용 가능한 완성 문장으로 작성
