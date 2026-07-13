"""Project-wide configuration: reproducibility seed and canonical paths.

This module is the single source of truth for the random seed and directory
locations. Every downstream story imports from here (NFR1 reproducibility).
ASCII-only per NFR6 (avoid cp949 encoding issues on Windows).
"""

from __future__ import annotations

import os
import random
from pathlib import Path

# --- Reproducibility (NFR1) --------------------------------------------------
RANDOM_SEED: int = 42

# --- Canonical paths ---------------------------------------------------------
# scorecard/config.py -> project root is one level up.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"
ARTIFACTS_DIR: Path = PROJECT_ROOT / "models" / "artifacts"

# Sample fixation (NFR8): Lending Club accepted loans, 2012-2015 vintages,
# 36-month term. Story 1.1 saves the filtered frame here; splitting/labeling
# happens in Story 1.2.
VINTAGE_MIN: int = 2012
VINTAGE_MAX: int = 2015
TERM_MONTHS: int = 36
ACCEPTED_PARQUET: Path = DATA_DIR / "lc_accepted_2012_2015_36m.parquet"


def set_global_seed(seed: int = RANDOM_SEED) -> int:
    """Seed Python's ``random`` and NumPy so runs are reproducible.

    Returns the seed used so callers can log it. NumPy is imported lazily to
    keep this module importable before dependencies are installed.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:  # numpy not installed yet (bare scaffolding)
        pass
    return seed
