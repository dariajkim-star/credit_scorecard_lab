"""Story 3.3 (FR17): export the champion scorecard to SAS and prove the port.

Three jobs, all driven by the champion artifact as the single source of truth
(AD-1 - nothing is hand-copied, so the .sas can never drift from the model):

1. ``extract_scorecard`` - pull the exact WOE lookup tables (numeric bin
   edges -> WOE, categorical groups -> WOE, empirical Missing/Special WOE),
   logistic coefficients/intercept, and PDO constants out of
   ``champion_model.joblib``.
2. ``mirror_score`` - a pure-arithmetic re-implementation of the scoring path
   (no sklearn/optbinning at score time). This is the SAS logic written in
   Python: if the mirror matches ``champion.score_applicant`` to <0.5 on real
   applicants, the arithmetic the .sas encodes is proven correct in this
   session, independent of any library.
3. ``generate_sas`` / ``write_outputs`` - emit a fully self-contained
   ``scorecard_scoring.sas`` (reference applicants embedded as datalines,
   expected Python scores included, per-row diff printed) plus
   ``reference_applicants.csv``. The user pastes the .sas into SAS OnDemand
   and reads the diff column - the final SAS-vs-Python tie-out (AC #1).

Mapping conventions replicated from ``binning.transform_woe`` (verified
empirically before implementation):
- numeric bins are left-closed/right-open on the fitted splits; NaN -> the
  Missing bin's empirical WOE.
- categorical: optbinning groups same-WOE categories (e.g. [RENT, NONE,
  OTHER]); missing -> Missing WOE; an UNSEEN category -> the Special bin's
  WOE (measured: transform maps unseen values to Special, not Missing).
- revol_util: the raw column is a percent STRING ("45.3%"); the reference CSV
  and datalines carry the parsed float so the SAS side needs no string
  munging (story-owner decision, recorded in the report).
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from scorecard.champion import BASE_ODDS, BASE_SCORE, PDO, MODEL_VERSION, score_formula
from scorecard.config import ACCEPTED_PARQUET, ARTIFACTS_DIR
from scorecard.preprocessing import parse_percent

SAS_DIR = Path(__file__).resolve().parent
N_REFERENCE = 12  # >= 10 per AC #1

NUMERIC_VARS = ["fico_range_low", "annual_inc", "dti", "revol_util", "inq_last_6mths"]
CATEGORICAL_VARS = ["home_ownership", "purpose"]


# --------------------------------------------------------------------------- #
# 1. Extraction (artifact -> plain dict, no optbinning objects past this point)
# --------------------------------------------------------------------------- #
def extract_scorecard(bundle: dict | None = None) -> dict:
    """Champion artifact -> a plain-python scorecard spec: per-variable WOE
    lookup (numeric: ascending split edges + per-bin WOE; categorical:
    category->WOE map), missing/special WOE, coefficients, intercept, and the
    PDO scaling constants."""
    if bundle is None:
        bundle = joblib.load(ARTIFACTS_DIR / "champion_model.joblib")
    model, binners = bundle["model"], bundle["binners"]
    variables = list(binners.keys())

    spec: dict = {
        "model_version": MODEL_VERSION,
        "intercept": float(model.intercept_[0]),
        "coefficients": {v: float(c) for v, c in zip(variables, model.coef_.ravel())},
        "pdo": PDO, "base_score": BASE_SCORE, "base_odds": BASE_ODDS,
        "variables": {},
    }
    for var, binner in binners.items():
        table = binner.binning_table.build()
        # Bin holds numpy arrays for categorical bins, so vectorized string
        # comparison is ambiguous - classify rows element-wise instead.
        is_sentinel = table["Bin"].apply(lambda b: isinstance(b, str) and b in ("Special", "Missing"))
        body = table[(table.index != "Totals") & ~is_sentinel]
        missing_woe = float(
            table[table["Bin"].apply(lambda b: isinstance(b, str) and b == "Missing")]["WoE"].iloc[0]
        )
        special_woe = float(
            table[table["Bin"].apply(lambda b: isinstance(b, str) and b == "Special")]["WoE"].iloc[0]
        )
        if binner.dtype == "categorical":
            mapping = {
                str(cat): float(row["WoE"])
                for _, row in body.iterrows()
                for cat in row["Bin"]  # Bin is an array of grouped categories
            }
            spec["variables"][var] = {
                "type": "categorical", "mapping": mapping,
                "missing_woe": missing_woe, "special_woe": special_woe,
            }
        else:
            spec["variables"][var] = {
                "type": "numeric",
                "splits": [float(s) for s in binner.splits],
                "woes": [float(w) for w in body["WoE"]],  # len == len(splits) + 1
                "missing_woe": missing_woe, "special_woe": special_woe,
            }
            assert len(spec["variables"][var]["woes"]) == len(binner.splits) + 1
    return spec


# --------------------------------------------------------------------------- #
# 2. Pure-arithmetic mirror (the SAS logic, in Python, for in-session proof)
# --------------------------------------------------------------------------- #
def _lookup_woe(var_spec: dict, value) -> float:
    if value is None or (isinstance(value, float) and np.isnan(value)) or pd.isna(value):
        return var_spec["missing_woe"]
    if var_spec["type"] == "categorical":
        return var_spec["mapping"].get(str(value), var_spec["special_woe"])
    for split, woe in zip(var_spec["splits"], var_spec["woes"]):
        if value < split:  # left-closed/right-open bins on ascending splits
            return woe
    return var_spec["woes"][-1]


def mirror_score(spec: dict, applicant: dict) -> float:
    """SAS-logic score: WOE lookup + linear combination + PDO scaling, using
    nothing but the extracted spec and plain arithmetic."""
    logit = spec["intercept"]
    for var, coef in spec["coefficients"].items():
        logit += coef * _lookup_woe(spec["variables"][var], applicant.get(var))
    factor = spec["pdo"] / np.log(2)
    offset = spec["base_score"] - factor * np.log(spec["base_odds"])
    return float(offset + factor * (-logit))


# --------------------------------------------------------------------------- #
# 3. Reference applicants (raw OOT rows + the Python ground-truth score)
# --------------------------------------------------------------------------- #
def build_reference_applicants(n: int = N_REFERENCE, bundle: dict | None = None) -> pd.DataFrame:
    """n diverse OOT-vintage applicants: raw 7 fields (revol_util parsed to
    float) + the champion's ground-truth score via the REAL library path
    (transform_woe + decision_function + score_formula). Deterministic
    selection: first n//2 rows, plus rows chosen to include missing values
    and varied categories."""
    from scorecard.binning import transform_woe

    if bundle is None:
        bundle = joblib.load(ARTIFACTS_DIR / "champion_model.joblib")
    model, binners = bundle["model"], bundle["binners"]
    variables = list(binners.keys())

    raw = pd.read_parquet(
        ACCEPTED_PARQUET, columns=["id", "vintage", *variables]
    )
    oot = raw[raw["vintage"] == 2015].copy()
    oot["revol_util"] = parse_percent(oot["revol_util"])

    base = oot.head(n // 2)
    with_missing = oot[oot[variables].isna().any(axis=1)].head(max(2, n // 4))
    rest = oot[~oot.index.isin(base.index) & ~oot.index.isin(with_missing.index)]
    varied = rest.drop_duplicates(subset=["home_ownership", "purpose"]).head(n)
    picked = pd.concat([base, with_missing, varied]).drop_duplicates(subset=["id"]).head(n)
    if len(picked) < max(10, n):
        raise ValueError(f"only {len(picked)} reference applicants selected - need >= 10 (AC #1)")

    woe = transform_woe(picked, binners)
    logits = model.decision_function(woe[variables].astype(float).to_numpy())
    scores = score_formula(logits)
    out = picked[["id", *variables]].reset_index(drop=True)
    out["python_score"] = np.round(scores, 6)
    return out


# --------------------------------------------------------------------------- #
# 4. SAS generation (fully self-contained: lookups + datalines + diff print)
# --------------------------------------------------------------------------- #
def _sas_numeric_block(var: str, vs: dict) -> str:
    lines = [f"  if missing({var}) then woe_{var} = {vs['missing_woe']:.10f};"]
    for split, woe in zip(vs["splits"], vs["woes"]):
        lines.append(f"  else if {var} < {split:.10f} then woe_{var} = {woe:.10f};")
    lines.append(f"  else woe_{var} = {vs['woes'][-1]:.10f};")
    return "\n".join(lines)


def _sas_categorical_block(var: str, vs: dict) -> str:
    lines = [f"  if missing({var}) then woe_{var} = {vs['missing_woe']:.10f};"]
    # group categories that share a WOE back together for readable SAS
    by_woe: dict[float, list[str]] = {}
    for cat, woe in vs["mapping"].items():
        by_woe.setdefault(woe, []).append(cat)
    for woe, cats in by_woe.items():
        quoted = ", ".join(f"'{c}'" for c in sorted(cats))
        lines.append(f"  else if {var} in ({quoted}) then woe_{var} = {woe:.10f};")
    lines.append(f"  else woe_{var} = {vs['special_woe']:.10f}; /* unseen category -> Special bin (transform_woe parity) */")
    return "\n".join(lines)


def generate_sas(spec: dict, reference: pd.DataFrame) -> str:
    """Emit a self-contained DATA step: reference applicants as datalines,
    WOE lookups, logit + PDO scaling, and a diff-vs-Python print. AUTOGENERATED
    - regenerate with `python -m sas.export_scorecard`, never hand-edit."""
    factor = spec["pdo"] / np.log(2)
    offset = spec["base_score"] - factor * np.log(spec["base_odds"])

    datalines = []
    for _, r in reference.iterrows():
        vals = []
        for var in [*NUMERIC_VARS]:
            vals.append("." if pd.isna(r[var]) else f"{float(r[var]):.6f}")
        for var in CATEGORICAL_VARS:
            vals.append("." if pd.isna(r[var]) else str(r[var]))
        datalines.append(f"{r['id']} " + " ".join(vals) + f" {r['python_score']:.6f}")

    woe_blocks = []
    for var in spec["coefficients"]:
        vs = spec["variables"][var]
        block = _sas_numeric_block(var, vs) if vs["type"] == "numeric" else _sas_categorical_block(var, vs)
        woe_blocks.append(f"  /* --- {var} --- */\n{block}")

    logit_terms = " +\n    ".join(
        f"({coef:.10f}) * woe_{var}" for var, coef in spec["coefficients"].items()
    )

    nl = "\n"
    return f"""/* ===========================================================================
   scorecard_scoring.sas - champion scorecard ported to SAS (Story 3.3, FR17)
   AUTOGENERATED from {spec['model_version']} artifact - do not hand-edit.
   Regenerate: python -m sas.export_scorecard
   Run as-is in SAS OnDemand: scores {len(reference)} embedded reference
   applicants and prints the diff vs the Python ground truth (pass = every
   |diff| < 0.5).
   =========================================================================== */

data reference;
  infile datalines dsd dlm=' ' truncover;
  length id $24 home_ownership $20 purpose $40;
  input id $ fico_range_low annual_inc dti revol_util inq_last_6mths
        home_ownership $ purpose $ python_score;
datalines;
{nl.join(datalines)}
;
run;

data scored;
  set reference;

{(nl + nl).join(woe_blocks)}

  /* logistic scorecard: logit(bad) then Siddiqi PDO scaling */
  logit = {spec['intercept']:.10f} +
    {logit_terms};
  factor = {factor:.10f};
  offset = {offset:.10f};
  sas_score = offset + factor * (-logit);

  diff = sas_score - python_score;
  abs_diff = abs(diff);
  pass = (abs_diff < 0.5);
run;

title "SAS vs Python scorecard tie-out (pass = every abs_diff < 0.5)";
proc print data=scored noobs;
  var id sas_score python_score diff abs_diff pass;
  format sas_score python_score 12.4 diff abs_diff 12.6;
run;

proc means data=scored max n;
  var abs_diff;
run;
"""


def write_outputs(out_dir: Path | None = None) -> tuple[Path, Path]:
    """Generate scorecard_scoring.sas + reference_applicants.csv from the
    current champion artifact."""
    out_dir = SAS_DIR if out_dir is None else Path(out_dir)
    bundle = joblib.load(ARTIFACTS_DIR / "champion_model.joblib")
    spec = extract_scorecard(bundle)
    reference = build_reference_applicants(bundle=bundle)

    sas_path = out_dir / "scorecard_scoring.sas"
    sas_path.write_text(generate_sas(spec, reference), encoding="utf-8")
    csv_path = out_dir / "reference_applicants.csv"
    reference.to_csv(csv_path, index=False)
    return sas_path, csv_path


if __name__ == "__main__":
    sas_path, csv_path = write_outputs()
    print(f"wrote {sas_path}\nwrote {csv_path}")
