# Deferred Work

이 문서는 코드리뷰·개발 중 발견했지만 지금 당장 손대지 않기로 한 항목을 기록합니다. "실재하는 리스크지만 현재 스코프·데이터·소비 경로에서는 발생하지 않거나 후속 스토리 소관"인 것들입니다.

## Deferred from: code review (story-2-1) (2026-07-14)

- **임의 `cutoffs` 배열(비정렬·중복·음수 값)이 검증되지 않음** [scorecard/strategy.py:cutoff_trade_off_curve] — 현재 소비자(2.1 자체 테스트·리포트)는 전부 기본 그리드(`_default_cutoff_grid`, 정렬됨) 또는 단일 정렬 배열만 사용, 실사용 경로에서 발생 불가. 후속 스토리(2.4 손익 cutoff 등)가 임의 배열을 직접 노출하게 되면 그때 하드닝.
- **`_filter_population`이 `model_type` 컬럼 존재를 가정(누락 시 미가공 `KeyError`)** [scorecard/strategy.py:_filter_population] — AD-3가 scored validation frame 스키마를 고정 보장하므로(1.7b), 컬럼 자체 부재는 프레임 생성 로직의 버그이지 이 스토리 소관이 아님. 프레임 생성 쪽(1.7b)에서 스키마 검증을 강화할 필요가 있다면 그쪽 스토리에서.
- **Cutoff 그리드가 정확히 0% 승인률에 도달하지 못함(설계상)** [scorecard/strategy.py:_default_cutoff_grid] — 그리드 상한이 `max(score)`라 최고 득점자 1인은 항상 승인(`1/total`로 수렴, 정확히 0 아님). 테스트(`test_cutoff_trade_off_curve_covers_full_approval_range`)에 의도로 명시돼 있고 docstring도 보강함. 진짜 0% 승인이 필요한 소비자가 나타나면(예: 스트레스 테스트) 그리드에 `max(score) + epsilon` 포인트 추가를 검토.

## Deferred from: code review (story-2-2) (2026-07-16)

- **bundle 필수 키(`model`/`binners`/`calibrator`) 부재 시 bare KeyError** [scorecard/reasons.py] — 잘못된 아티팩트/구식 스키마 bundle이 들어오면 진단 맥락 없는 KeyError. 내부 도구 수준에서는 수용 가능하고, Story 2.3(FastAPI 서빙)이 아티팩트 로딩 계층을 만들 때 그 계층에서 명시적 스키마 검증(어느 파일의 어떤 키가 없는지)을 넣는 것이 자연스러운 위치.
- **미등록 변수의 한국어 조사 fallback** [scorecard/reasons.py:_korean_label] — KOREAN_LABELS에 없는 변수는 raw 변수명 + "이(가)"로 조사가 어색한 문장이 됨(크래시는 아님). 현재 7개 변수 전부 등록돼 발생 불가. 변수가 추가되는 스토리(3.2 emp_title 파생 등)에서 라벨 등록을 DoD에 포함할 것.

## Deferred from: code review (story-2-3) (2026-07-16)

- **점수 반올림(1자리 표시)과 등급 산출(원값 기준) 경계 부근 표시 불일치** [app/main.py:_score_one] — score=546.04는 546.0으로 표시되지만 등급은 546.04 원값으로 산출됨. 경계 부근(±0.05점)에서만 발생하는 코스메틱 이슈, 실사용 영향 낮음. 필요해지면 표시용 점수를 등급 산출 후 스냅하는 방식 검토.
- **등급표에서 OOT 관측 0건인 등급이 monotonic 검증에서 조용히 제외** [app/loader.py:_grade_table, scorecard/grading.py:validate_monotonic] — `observed_bad_rate=None` 행이 dropna로 빠지면서 그 등급의 데이터 공백이 monotonic_validated=true에 반영 안 됨. `grading.py` 변경(빈 등급 명시 플래그)이 필요해 서빙 스토리 범위 밖.
- **`/v1/score`가 `SingleScoreResponse`/`BothScoreResponse` 두 타입을 반환하는데 명시 response_model 없음** [app/main.py] — 쿼리파라미터(`model=both`)에 따라 셰이프가 달라지는 의도된 패턴이라 FastAPI의 단일 response_model로 표현 불가. OpenAPI 문서화 개선(oneOf 등)은 대시보드(2.5) 연동 시 필요성 재평가.

## Deferred from: code review (story-3-1) (2026-07-16)

- **`opportunity_loss_est`가 양수 실현손익만 합산 → 순 포트폴리오 수치와 tie-out 불가** [scorecard/rule_efficiency.py:_opportunity_loss] — Task 3에서 "배제된 우량 대출의 놓친 이익"으로 의도한 정의(리포트에 명시). 순액(양수-음수) 지표나 포트폴리오 대조가 필요해지면 별도 필드로 추가.
- **vintage/model_type dtype mismatch 시 빈 population→500** [scorecard/rule_efficiency.py] — strategy.py 등 기존 소비자와 동일한 fail-fast 관례. AD-3 프레임 스키마가 dtype를 보장하므로 정상 데이터에선 미발생. 프레임 생성(1.7b) 스키마 검증 강화 소관.
- **raw `id` 중복 시 many_to_one이 startup 전체 차단** [scorecard/rule_efficiency.py:load_rule_frame] — profit.load_profit_frame과 동일 계약. 데이터 품질 문제를 부분 강등(rule 엔드포인트만 503) 없이 전체 장애로 전환하나 fail-fast가 의도. 2.4 startup-crash defer와 동류 — 대시보드/가용성 요구가 명확해지면 재평가.

## Deferred from: code review (story-2-5) (2026-07-16)

- **슬라이더 드래그 틱마다 blocking POST(10s 타임아웃)** [dashboard/app.py:screen_cutoff] — Streamlit rerun 특성상 슬라이더 값 변경마다 `/v1/simulate/cutoff` POST가 순차 발화. 현재는 로컬 API+startup 사전계산 조회(ms 단위)라 체감 지연 없음. 원격 API로 전환하거나 응답이 느려지면 debounce(st.form 또는 on_change 지연) 검토.
- **health 게이트와 60s TTL 캐시의 정합 창** [dashboard/app.py] — API가 새 모델로 재시작해도 최대 60초간 구모델 메트릭이 캐시에서 서빙될 수 있음(역방향: degraded 전환 감지는 매 rerun health로 즉시). 로컬 단일 사용자 데모에서 수용. 필요 시 health의 model_version을 캐시 키에 포함.
- **`CURRENT_CUTOFF=546.0` 대시보드 중복 상수** [dashboard/app.py] — 슬라이더 초기값 시드로만 사용(표시 수치는 전부 API의 current_cutoff). 서버 상수와 드리프트 가능성 있으나 UI 시드 특성상 영향 미미. profit 응답의 current_cutoff로 슬라이더를 시드하려면 위젯 생성 순서 재구성이 필요해 보류.

## Deferred from: code review (story-2-4) (2026-07-16)

- **degenerate profit curve 시 앱이 startup에서 크래시** [app/loader.py, scorecard/profit.py:find_optimal_cutoff] — 리뷰 patch로 `load_profit_frame`(조인 미매치·팬아웃)과 `find_optimal_cutoff`(전 cutoff 승인 0건)가 fail-fast ValueError를 던지게 되면서, startup 사전계산 경로에서 이 예외가 발생하면 uvicorn 자체가 뜨지 못함(503 MODEL_NOT_LOADED로 우아하게 강등되지 않음). 현재 실데이터에서는 발생 불가(100% 매치·정상 curve 실측)이고, "잘못된 아티팩트로는 서빙을 시작하지 않는다"는 관점에서 크래시가 오히려 안전한 기본값이라 수용. 부분 강등(profit 엔드포인트만 503, 나머지 서빙 유지)이 필요해지면 loader의 사전계산을 try/except로 감싸 `profit_base_curves`를 비우는 방식 검토 — 대시보드(2.5)가 가용성 요구를 명확히 할 때 재평가.
