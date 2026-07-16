# Deferred Work

이 문서는 코드리뷰·개발 중 발견했지만 지금 당장 손대지 않기로 한 항목을 기록합니다. "실재하는 리스크지만 현재 스코프·데이터·소비 경로에서는 발생하지 않거나 후속 스토리 소관"인 것들입니다.

## Deferred from: code review (story-2-1) (2026-07-14)

- **임의 `cutoffs` 배열(비정렬·중복·음수 값)이 검증되지 않음** [scorecard/strategy.py:cutoff_trade_off_curve] — 현재 소비자(2.1 자체 테스트·리포트)는 전부 기본 그리드(`_default_cutoff_grid`, 정렬됨) 또는 단일 정렬 배열만 사용, 실사용 경로에서 발생 불가. 후속 스토리(2.4 손익 cutoff 등)가 임의 배열을 직접 노출하게 되면 그때 하드닝.
- **`_filter_population`이 `model_type` 컬럼 존재를 가정(누락 시 미가공 `KeyError`)** [scorecard/strategy.py:_filter_population] — AD-3가 scored validation frame 스키마를 고정 보장하므로(1.7b), 컬럼 자체 부재는 프레임 생성 로직의 버그이지 이 스토리 소관이 아님. 프레임 생성 쪽(1.7b)에서 스키마 검증을 강화할 필요가 있다면 그쪽 스토리에서.
- **Cutoff 그리드가 정확히 0% 승인률에 도달하지 못함(설계상)** [scorecard/strategy.py:_default_cutoff_grid] — 그리드 상한이 `max(score)`라 최고 득점자 1인은 항상 승인(`1/total`로 수렴, 정확히 0 아님). 테스트(`test_cutoff_trade_off_curve_covers_full_approval_range`)에 의도로 명시돼 있고 docstring도 보강함. 진짜 0% 승인이 필요한 소비자가 나타나면(예: 스트레스 테스트) 그리드에 `max(score) + epsilon` 포인트 추가를 검토.

## Deferred from: code review (story-2-2) (2026-07-16)

- **bundle 필수 키(`model`/`binners`/`calibrator`) 부재 시 bare KeyError** [scorecard/reasons.py] — 잘못된 아티팩트/구식 스키마 bundle이 들어오면 진단 맥락 없는 KeyError. 내부 도구 수준에서는 수용 가능하고, Story 2.3(FastAPI 서빙)이 아티팩트 로딩 계층을 만들 때 그 계층에서 명시적 스키마 검증(어느 파일의 어떤 키가 없는지)을 넣는 것이 자연스러운 위치.
- **미등록 변수의 한국어 조사 fallback** [scorecard/reasons.py:_korean_label] — KOREAN_LABELS에 없는 변수는 raw 변수명 + "이(가)"로 조사가 어색한 문장이 됨(크래시는 아님). 현재 7개 변수 전부 등록돼 발생 불가. 변수가 추가되는 스토리(3.2 emp_title 파생 등)에서 라벨 등록을 DoD에 포함할 것.
