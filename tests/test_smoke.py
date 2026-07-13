"""Smoke tests for the reproducibility utilities and path contract (NFR1, NFR3)."""

from __future__ import annotations

import numpy as np

from scorecard import config


def test_seed_is_deterministic():
    config.set_global_seed(config.RANDOM_SEED)
    first = np.random.rand(5)
    config.set_global_seed(config.RANDOM_SEED)
    second = np.random.rand(5)
    assert np.array_equal(first, second)


def test_set_global_seed_returns_seed():
    assert config.set_global_seed(123) == 123


def test_path_constants_point_under_project_root():
    assert config.DATA_DIR.parent == config.PROJECT_ROOT
    assert config.ARTIFACTS_DIR.parent.parent == config.PROJECT_ROOT
    assert config.ACCEPTED_PARQUET.parent == config.DATA_DIR


def test_sample_fixation_constants():
    assert config.VINTAGE_MIN == 2012
    assert config.VINTAGE_MAX == 2015
    assert config.TERM_MONTHS == 36
