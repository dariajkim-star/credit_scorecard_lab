"""Artifact loading layer for the scoring API (Story 2.3, AD-4: load-only).

Everything is loaded/validated/precomputed exactly once at startup into a
ModelStore. Load failure never crashes the app - the store records the error
and /health reports "degraded" while business endpoints return 503
MODEL_NOT_LOADED (the P3 agent uses /health to decide tool availability).

Explicit bundle/manifest key validation lives here by design - Story 2.2
deferred it to "the loading layer Story 2.3 builds" (deferred-work.md).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from scorecard import strategy
from scorecard.config import ARTIFACTS_DIR, DATA_DIR
from scorecard.evaluation import compute_metrics, population_stability_index
from scorecard.grading import validate_monotonic
from scorecard.reasons import build_challenger_explainer

logger = logging.getLogger("app.loader")

SCORED_FRAME_PATH = DATA_DIR / "scored_validation_frame.parquet"

REQUIRED_BUNDLE_KEYS = {
    "champion": {"model", "binners"},
    "challenger": {"model", "calibrator"},
}
REQUIRED_MANIFEST_KEYS = {
    "champion": {"model_type", "model_version", "feature_order", "grade_thresholds",
                 "pdo", "base_score", "base_odds"},
    "challenger": {"model_type", "model_version", "feature_order", "grade_thresholds",
                   "calibration_method"},
}


@dataclass
class ModelStore:
    loaded: bool = False
    error: str | None = None
    bundles: dict[str, dict] = field(default_factory=dict)
    manifests: dict[str, dict] = field(default_factory=dict)
    variables: list[str] = field(default_factory=list)
    frame: pd.DataFrame | None = None
    explainer: Any = None
    # Precomputed at startup (frame and artifacts are immutable, AD-4):
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    curves: dict[str, pd.DataFrame] = field(default_factory=dict)
    grade_tables: dict[str, list[dict]] = field(default_factory=dict)
    monotonic_validated: dict[str, bool] = field(default_factory=dict)

    def model_version(self, model_type: str) -> str:
        return self.manifests.get(model_type, {}).get("model_version", "unknown")


def _validate_bundle(name: str, bundle: dict) -> None:
    missing = REQUIRED_BUNDLE_KEYS[name] - set(bundle)
    if missing:
        raise ValueError(
            f"{name}_model.joblib bundle is missing required key(s) {sorted(missing)} - "
            f"expected {sorted(REQUIRED_BUNDLE_KEYS[name])}; the artifact may predate "
            "Story 1.5/1.6's bundle format"
        )


def _validate_manifest(name: str, manifest: dict) -> None:
    missing = REQUIRED_MANIFEST_KEYS[name] - set(manifest)
    if missing:
        raise ValueError(
            f"{name}_manifest.json is missing required key(s) {sorted(missing)} - "
            "grade_thresholds is finalized by Story 1.7b; re-run that pipeline if absent"
        )


def _frame_metrics(frame: pd.DataFrame, model_type: str) -> dict[str, float]:
    """OOT AUC/KS + valid->oot score PSI from the AD-3 frame (consumption,
    not recomputation - pd/score/bad_flag are already in the frame)."""
    rows = frame[frame["model_type"] == model_type]
    oot = rows[rows["vintage"] == strategy.OOT_VINTAGE]
    valid = rows[rows["vintage"] != strategy.OOT_VINTAGE]
    m = compute_metrics(
        oot["bad_flag"].to_numpy(dtype=int), oot["pd"].to_numpy(dtype=float)
    )
    psi = population_stability_index(
        valid["score"].to_numpy(dtype=float), oot["score"].to_numpy(dtype=float)
    )
    return {"auc_oot": round(m["auc"], 4), "ks_oot": round(m["ks"], 4),
            "psi_score": round(psi, 4)}


def _grade_table(frame: pd.DataFrame, model_type: str, thresholds: list[float]) -> tuple[list[dict], bool]:
    """API_SPEC §3 grade rows (score range + observed bad rate) from the frame.

    grade_thresholds are the FULL ascending bin-edge array from
    grading.fit_grade_thresholds (length n_grades+1, both endpoints
    included; the outer bins are open-ended at grading time via
    _bin_edges_open). n_grades = len(edges) - 1, grade 1 = the highest-score
    bin. Grade g occupies the pd.cut interval
    (edges[n_bins-g], edges[n_bins-g+1]] with the outer bounds reported as
    null (open-ended) - mirroring assign_grade exactly so the table and the
    /v1/score grade can never disagree (a first-cut version here treated the
    edges as internal thresholds and produced 12 phantom grades, caught by
    test_grades_table_consistent_with_scoring).

    The frame already carries each row's assigned grade (1.7b), so
    observed_bad_rate is a groupby - no re-grading here.
    """
    rows = frame[(frame["model_type"] == model_type) & (frame["vintage"] == strategy.OOT_VINTAGE)]
    edges = np.asarray(thresholds, dtype=float)
    n_bins = len(edges) - 1
    by_grade = rows.groupby("grade")["bad_flag"].agg(["mean", "size"])

    table: list[dict] = []
    for grade in range(1, n_bins + 1):
        bin_idx = n_bins - grade
        score_min = None if bin_idx == 0 else float(edges[bin_idx])
        score_max = None if bin_idx == n_bins - 1 else float(edges[bin_idx + 1])
        observed = float(by_grade.loc[grade, "mean"]) if grade in by_grade.index else None
        table.append({
            "grade": grade,
            "score_min": score_min,
            "score_max": score_max,
            "observed_bad_rate": round(observed, 4) if observed is not None else None,
        })
    bad_rate_df = pd.DataFrame({
        "grade": [t["grade"] for t in table],
        "bad_rate": [t["observed_bad_rate"] for t in table],
    }).dropna()
    monotonic = validate_monotonic(bad_rate_df)
    return table, monotonic


def load_store() -> ModelStore:
    store = ModelStore()
    try:
        for name in ("champion", "challenger"):
            model_path = ARTIFACTS_DIR / f"{name}_model.joblib"
            manifest_path = ARTIFACTS_DIR / f"{name}_manifest.json"
            if not model_path.exists() or not manifest_path.exists():
                raise FileNotFoundError(f"artifact missing: {model_path.name} or {manifest_path.name}")
            bundle = joblib.load(model_path)
            _validate_bundle(name, bundle)
            manifest = json.loads(manifest_path.read_text())
            _validate_manifest(name, manifest)
            store.bundles[name] = bundle
            store.manifests[name] = manifest

        if store.manifests["champion"]["feature_order"] != store.manifests["challenger"]["feature_order"]:
            raise ValueError("champion/challenger manifests disagree on feature_order")
        store.variables = list(store.manifests["champion"]["feature_order"])

        if not SCORED_FRAME_PATH.exists():
            raise FileNotFoundError(f"scored validation frame missing: {SCORED_FRAME_PATH}")
        store.frame = pd.read_parquet(SCORED_FRAME_PATH)

        store.explainer = build_challenger_explainer(store.bundles["challenger"])

        for name in ("champion", "challenger"):
            store.metrics[name] = _frame_metrics(store.frame, name)
            store.curves[name] = strategy.cutoff_trade_off_curve(store.frame, name)
            table, mono = _grade_table(
                store.frame, name, store.manifests[name]["grade_thresholds"]
            )
            store.grade_tables[name] = table
            store.monotonic_validated[name] = mono

        store.loaded = True
        logger.info(
            "model store loaded: variables=%s champion=%s challenger=%s frame_rows=%d",
            store.variables, store.model_version("champion"),
            store.model_version("challenger"), len(store.frame),
        )
    except Exception as exc:  # degrade, never crash (P3 checks /health)
        store.loaded = False
        store.error = str(exc)
        logger.error("model store failed to load: %s", exc)
    return store
