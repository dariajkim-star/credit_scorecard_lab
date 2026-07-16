# P3(loan-agent-lab) 연동 예시 — Story 2.3

P3 에이전트의 소비 순서(API_SPEC §9): `/health` → `/v1/score?model=champion` → `/v1/grades`.
아래 응답은 전부 **라이브 서버(uvicorn, 실제 아티팩트)에서 실측 수집**한 것이다(2026-07-16).

## 1. GET /health — 도구 가용성 판단

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_version": "champion-1.0.0"
}
```

미로드 시 `{"status": "degraded", "model_loaded": false}` + HTTP 200 (503 아님 — P3는 이 응답으로 스코어링 도구를 비활성화).

## 2. POST /v1/score?model=champion — 단건 스코어링

요청:
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

응답 (200):
```json
{
  "score": 542.8,
  "pd": 0.126666,
  "grade": 6,
  "reason_codes": [
    {
      "rank": 1,
      "variable": "fico_range_low",
      "description": "신용점수(FICO)이(가) 심사 기준 대비 불리하여 점수가 25.4점 하락했습니다.",
      "points_lost": 25.4493
    },
    {
      "rank": 2,
      "variable": "annual_inc",
      "description": "연소득이(가) 심사 기준 대비 불리하여 점수가 10.6점 하락했습니다.",
      "points_lost": 10.5888
    },
    {
      "rank": 3,
      "variable": "dti",
      "description": "부채비율(DTI)이(가) 심사 기준 대비 불리하여 점수가 6.7점 하락했습니다.",
      "points_lost": 6.7129
    }
  ],
  "warnings": [],
  "model": {
    "name": "champion",
    "version": "champion-1.0.0",
    "type": "champion"
  }
}
```

- `reason_codes[].description`은 심사의견서에 그대로 인용 가능한 완성 문장(P3 계약).
- reason_codes는 **실제 불리 요인만** 포함(0점 요인 제외 — 3개 미만일 수 있음, Story 2.2 결정).
- 판정(승인/거절)은 P3의 룰 엔진 몫 — 이 API는 cutoff을 적용하지 않는다.

## 3. GET /v1/grades — 등급 체계

```json
{
  "model": "champion",
  "grades": [
    {
      "grade": 1,
      "score_min": 567.2779459460421,
      "score_max": null,
      "observed_bad_rate": 0.0463
    },
    {
      "grade": 2,
      "score_min": 559.0502258062196,
      "score_max": 567.2779459460421,
      "observed_bad_rate": 0.0801
    },
    {
      "grade": 3,
      "score_min": 553.4990724757654,
      "score_max": 559.0502258062196,
      "observed_bad_rate": 0.1051
    },
    {
      "...": "grade 4~10 생략"
    }
  ],
  "monotonic_validated": true
}
```

## 에러 계약 (§0)

| HTTP | error_code | 예 |
|---|---|---|
| 422 | (FastAPI 기본) | 전 필드 null, 스키마 위반 |
| 400 | VALUE_OUT_OF_RANGE | `{"detail": "dti=99999.0 is outside the acceptable range [0.0, 999.0] - the model cannot produce a trustworthy score for this input", "error_code": "VALUE_OUT_OF_RANGE"}` |
| 503 | MODEL_NOT_LOADED | 아티팩트 미로드 시 전 업무 엔드포인트 |

## 재현

```bash
.venv/Scripts/uvicorn app.main:app --port 8000
curl http://127.0.0.1:8000/health
```
