#!/usr/bin/env python3
"""Evaluate one declared B1 rain-number prior against ORIGINAL and current B1."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BALANCE = ROOT / "tools/cp02_weak_strong_balance.py"
BALANCE_SHA256 = "2572d41d352c70d72d8488fe9f0dc9d961de8b10c21f7ade459f131e7c4fbdb5"
CANDIDATE = "B1_RAIN_NUMBER_PRIOR"
CURRENT = "IMPROVED_BG_FIXED"
CASES = ("ORIGINAL", CURRENT, CANDIDATE)
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)


def identity(path: Path) -> dict:
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path.resolve()), "sha256": sha, "size_bytes": path.stat().st_size}


def require_identity(path: Path, expected: dict) -> dict:
    actual = identity(path)
    if any(actual[key] != expected[key] for key in ("sha256", "size_bytes")):
        raise ValueError(f"artifact differs from its frozen identity: {path}")
    return actual


def compare_scores(arrays: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Keep each lead and threshold separate; select with exact count fractions."""
    if set(arrays) != set(range(13, 19)):
        raise ValueError("six hourly forecast arrays are required")
    categorical, continuous = [], []
    for hour in range(13, 19):
        values = arrays[hour]
        if any(np.asarray(values[name]).shape != (3688,) or not np.isfinite(values[name]).all()
               for name in (*CASES, "reference")):
            raise ValueError("all cases must cover the same 3,688 finite samples")
        observed = values["reference"]
        for case in CASES:
            prediction = values[case]
            error = prediction - observed
            continuous.append({"lead_hour": hour - 12, "case": case,
                               "MAE_mm": float(np.abs(error).mean()),
                               "RMSE_mm": float(np.sqrt(np.square(error).mean()))})
            for threshold in THRESHOLDS:
                obs, pred = observed >= threshold, prediction >= threshold
                h = int(np.count_nonzero(obs & pred))
                m = int(np.count_nonzero(obs & ~pred))
                f = int(np.count_nonzero(~obs & pred))
                denominator = h + m + f
                if not denominator:
                    raise ValueError("CSI is undefined in a required comparison")
                categorical.append({"lead_hour": hour - 12, "threshold_mm": threshold, "case": case,
                                    "points": 3688, "hit": h, "miss": m, "false_alarm": f,
                                    "CSI": h / denominator})
    keyed = {(r["lead_hour"], r["threshold_mm"], r["case"]): r for r in categorical}
    constraints = []
    for lead in range(1, 7):
        for threshold in THRESHOLDS:
            protect = lead == 1 or threshold == 5
            recover = lead >= 2 and threshold in (0.1, 0.5, 1.0)
            if not protect and not recover:
                continue
            baseline = CURRENT if protect else "ORIGINAL"
            candidate, control = keyed[lead, threshold, CANDIDATE], keyed[lead, threshold, baseline]
            exact = lambda r: Fraction(r["hit"], r["hit"] + r["miss"] + r["false_alarm"])
            constraints.append({"goal": "preserve_current_B1" if protect else "recover_low_threshold_vs_ORIGINAL",
                                "lead_hour": lead, "threshold_mm": threshold, "baseline": baseline,
                                "candidate_CSI": candidate["CSI"], "baseline_CSI": control["CSI"],
                                "satisfied": exact(candidate) >= exact(control)})
    if len(categorical) != 108 or len(continuous) != 18 or len(constraints) != 26:
        raise ValueError("evaluation scope differs from the declared 108/18/26 rows")
    return categorical, continuous, constraints


def csv_output(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(plan_path: Path, plan_sha256: str, runtime: Path, gate_path: Path, output: Path) -> dict:
    if os.path.lexists(output):
        raise FileExistsError(output)
    if identity(plan_path)["sha256"] != plan_sha256:
        raise ValueError("evaluation plan hash differs")
    plan = json.loads(plan_path.read_text())
    if (plan.get("schema") != "b1_rain_number_evaluation_v1" or plan.get("candidate") != CANDIDATE
            or plan.get("thresholds_mm") != list(THRESHOLDS) or plan.get("leads_hours") != list(range(1, 7))
            or plan.get("constraint_count") != 26):
        raise ValueError("evaluation scope differs from the frozen contract")
    gate = json.loads(gate_path.read_text())
    if gate.get("status") != "COMPLETE" or gate.get("case") != CANDIDATE:
        raise ValueError("complete candidate runtime gate is required")
    for key in ("policy_sha256", "input_sha256", "executable_sha256", "boundary_sha256", "namelist_sha256"):
        if gate.get(key) != plan.get(key) or not isinstance(plan.get(key), str) or len(plan[key]) != 64:
            raise ValueError(f"runtime differs from the frozen plan: {key}")
    inputs = [identity(plan_path), identity(gate_path)]
    artifacts = plan.get("bound_artifacts", {})
    if set(artifacts) != {"policy", "initialization", "candidate_preflight"}:
        raise ValueError("policy, initialization, and candidate first-call preflight bindings are required")
    for record in artifacts.values():
        inputs.append(require_identity(ROOT / record["path"], record))
    if artifacts["policy"]["sha256"] != plan["policy_sha256"]:
        raise ValueError("policy file differs from the declared policy hash")
    preflight = json.loads((ROOT / artifacts["candidate_preflight"]["path"]).read_text())
    if (preflight.get("status") != "PASS" or preflight.get("policy_sha256") != plan["policy_sha256"]
            or preflight.get("candidate_input_sha256") != plan["input_sha256"]):
        raise ValueError("candidate first-call preflight does not admit this policy and input")
    for name, key in (("wrfinput_d01", "input_sha256"), ("wrf.exe", "executable_sha256"),
                      ("wrfbdy_d01", "boundary_sha256"), ("namelist.input", "namelist_sha256")):
        record = identity(runtime / name)
        if record["sha256"] != plan[key]:
            raise ValueError(f"candidate runtime input changed: {name}")
        inputs.append(record)
    history = gate.get("history", {})
    expected = {f"wrfout_d01_2026-08-16_{h:02d}:00:00" for h in range(12, 19)}
    if set(history) != expected:
        raise ValueError("candidate runtime requires all seven hourly histories")
    inputs.extend(require_identity(runtime / name, history[name]) for name in sorted(expected))
    if identity(BALANCE)["sha256"] != BALANCE_SHA256:
        raise ValueError("pinned remapping source changed")
    spec = importlib.util.spec_from_file_location("rain_number_mapping", BALANCE)
    balance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(balance)
    _, baselines, prior_records = balance.load_prior_arrays()
    balance.CASE_IDS = (CANDIDATE,)
    balance.CONTEXT_IDS = ("ORIGINAL", CURRENT)
    arrays, _, histories, mapping, resets = balance.build_candidate_arrays({CANDIDATE: runtime}, baselines)
    categorical, continuous, constraints = compare_scores(arrays)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".rain-number-evaluation-", dir=output.parent))
    try:
        for name, rows in (("categorical_scores.csv", categorical), ("continuous_scores.csv", continuous),
                           ("admission_constraints.csv", constraints)):
            csv_output(stage / name, rows)
        for hour, values in arrays.items():
            np.savez_compressed(stage / f"hour_{hour}_arrays.npz", **values)
        np.savez_compressed(stage / "bilinear_mapping.npz", **mapping)
        verdict = {"candidate": CANDIDATE, "qualified": all(r["satisfied"] for r in constraints),
                   "selection": CANDIDATE if all(r["satisfied"] for r in constraints) else "NO_QUALIFIED_CANDIDATE",
                   "passed_constraints": sum(r["satisfied"] for r in constraints), "required_constraints": 26,
                   "ranking_metric": "CSI per lead and threshold, no averaging; RMSE diagnostic only"}
        (stage / "winner.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
        for record in inputs:
            require_identity(Path(record["path"]), record)
        receipt = {"status": "COMPLETE", "inputs": inputs + prior_records + histories,
                   "scorer": identity(Path(__file__)), "mapping_source": identity(BALANCE),
                   "reset_report": resets, "rows": {"categorical": 108, "continuous": 18, "constraints": 26},
                   "outputs": {p.name: identity(p) for p in sorted(stage.iterdir())}}
        for record in receipt["outputs"].values():
            record.pop("path")
        (stage / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        stage.rename(output)
        return verdict
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--runtime-gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.plan, args.plan_sha256, args.runtime, args.runtime_gate, args.output), sort_keys=True))
