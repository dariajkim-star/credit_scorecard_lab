# credit-scorecard-lab

Lending Club 신용평가 스코어카드 개발 랩. 누수 없는 표본 위에 WOE 스코어카드(챔피언)와
LightGBM(챌린저)을 개발하고, 심사 전략 분석·FastAPI 서빙·Streamlit 대시보드까지 이어지는
포트폴리오 프로젝트. (상세: `docs/planning-artifacts/epics.md`)

> Status: Story 1.1 (scaffolding + data acquisition) 진행 중. 결과 이미지·핵심 수치는
> 문서화 스토리(3.4)에서 채운다.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Data acquisition (Phase 0)

원본 데이터(Lending Club accepted loans, 2007~2018Q4)는 gitignore 대상이며 아래 스크립트로
재생성한다 (NFR5). 스크립트는 usecols+dtype 지정 로드로 원본 CSV(~1.6GB)를 메모리 안전하게
읽어 **2012~2015 빈티지 · 36개월물**만 `data/lc_accepted_2012_2015_36m.parquet`로 저장한다.

```powershell
.venv\Scripts\python.exe pipelines\01_download.py
```

### 폴백 (kagglehub 실패 시)

`kagglehub`는 첫 호출 시 Kaggle 데이터셋을 내려받는다. 공개 데이터셋이라 계정 없이도
받아지는 경우가 많으나, 인증/네트워크 문제로 실패하면 다음 순서로 대체한다:

1. **Kaggle CLI** — `pip install kaggle` 후 `~/.kaggle/kaggle.json` API 토큰
   (Kaggle 계정 > Settings > Create New Token)을 두고
   `kaggle datasets download -d wordsforthewise/lending-club`.
2. **수동 다운로드** — <https://www.kaggle.com/datasets/wordsforthewise/lending-club>
   에서 `accepted_2007_to_2018Q4.csv.gz`를 내려받는다.
3. 내려받은 파일 경로로 재실행:
   `.venv\Scripts\python.exe pipelines\01_download.py --csv <path-to-csv.gz>`.

> Kaggle 계정/키 필요 여부: kagglehub 익명 접근이 막힌 환경에서는 위 1·2번이 필요하다.
> dev 착수 시 `kagglehub.dataset_download(...)` 반환 경로에서 실제 파일명을 먼저 확인할 것.

## Testing

```powershell
$env:PYTHONIOENCODING="utf-8"; .venv\Scripts\python.exe -m pytest -q
```

## Structure

파이프라인(`pipelines/`, `scorecard/`)이 아티팩트 번들을 만들고, 서빙(`app/`)이 읽기 전용으로
소비하며, 대시보드(`dashboard/`)는 API만 경유한다. 상세 불변식은
`docs/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md` 참조.
