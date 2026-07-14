"""Phase 0: download Lending Club accepted loans and save a filtered parquet.

Regeneration script (NFR5): raw data is gitignored; running this reproduces
``data/lc_accepted_2012_2015_36m.parquet`` from scratch.

Flow:
  kagglehub download -> locate accepted_*.csv.gz -> usecols+dtype load
  -> filter to 2012-2015 vintage / 36-month term -> parquet.

On kagglehub failure it prints the manual fallback (see README "Data
acquisition"). Because the filename starts with a digit it is not importable;
the testable logic lives in ``pipelines/loading.py``.

Usage:
    .venv/Scripts/python.exe pipelines/01_download.py
    .venv/Scripts/python.exe pipelines/01_download.py --csv path/to/accepted.csv.gz
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Allow running as a script: ensure project root on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipelines.loading import (  # noqa: E402
    DTYPES,
    USECOLS,
    derive_vintage,
    filter_accepted,
    summarize,
)
from scorecard.config import (  # noqa: E402
    ACCEPTED_GLOB,
    ACCEPTED_PARQUET,
    DATA_DIR,
    KAGGLE_DATASET,
)

FALLBACK_MSG = (
    "\n[FALLBACK] kagglehub download failed. Manual options:\n"
    "  1. Kaggle CLI:  pip install kaggle && kaggle datasets download "
    f"-d {KAGGLE_DATASET} (needs ~/.kaggle/kaggle.json API token)\n"
    "  2. Manual:      download 'accepted_2007_to_2018Q4.csv.gz' from\n"
    f"     https://www.kaggle.com/datasets/{KAGGLE_DATASET}\n"
    "  3. Re-run with: python pipelines/01_download.py --csv <path-to-csv.gz>\n"
    "See README.md 'Data acquisition' for details.\n"
)


def locate_csv_via_kagglehub() -> Path:
    """Download the dataset with kagglehub and return the accepted CSV path."""
    import kagglehub

    dataset_dir = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    matches = sorted(dataset_dir.rglob(ACCEPTED_GLOB))
    if not matches:
        raise FileNotFoundError(
            f"No file matching {ACCEPTED_GLOB} under {dataset_dir}. "
            "Inspect the download directory and pass --csv explicitly."
        )
    return matches[0]


def load_and_filter(csv_path: Path) -> pd.DataFrame:
    """Load the raw CSV with the column contract, then filter (memory-safe)."""
    print(f"[load] reading {csv_path} (usecols={len(USECOLS)} cols)")
    raw = pd.read_csv(
        csv_path,
        usecols=USECOLS,
        dtype=DTYPES,
        low_memory=False,
        compression="infer",
    )
    print(f"[load] raw rows: {len(raw):,}")
    n_unparseable = int(derive_vintage(raw["issue_d"]).isna().sum())
    if n_unparseable:
        print(f"[warn] {n_unparseable:,} rows with unparseable issue_d (excluded)")
    filtered = filter_accepted(raw)
    print(f"[filter] rows after 2012-2015 / 36m: {len(filtered):,}")
    return filtered


def main() -> int:
    parser = argparse.ArgumentParser(description="Download + filter Lending Club data")
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Path to accepted_*.csv.gz (skips kagglehub download)",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        csv_path = args.csv if args.csv is not None else locate_csv_via_kagglehub()
    except Exception as exc:  # noqa: BLE001 - surface any download/auth failure
        print(f"[error] could not obtain source CSV: {exc}", file=sys.stderr)
        print(FALLBACK_MSG, file=sys.stderr)
        return 1

    if not Path(csv_path).exists():
        print(f"[error] CSV not found: {csv_path}", file=sys.stderr)
        print(FALLBACK_MSG, file=sys.stderr)
        return 1

    df = load_and_filter(Path(csv_path))
    df.to_parquet(ACCEPTED_PARQUET, index=False)

    stats = summarize(df)
    print(f"[save] {ACCEPTED_PARQUET}")
    print(f"[summary] rows={stats['rows']:,}")
    print(f"[summary] vintage_counts={stats['vintage_counts']}")
    print(f"[summary] term_values={stats['term_values']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
