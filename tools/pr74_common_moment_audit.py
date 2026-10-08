#!/usr/bin/env python3
"""Audit all common KDM6 Q/N/B moment states from one retained input trace."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np

from native_kdm6_trace import read_dump


SPECIES = (
    ("rain", "QR", "NR", "specific_number"),
    ("cloud", "QC", "NC", "specific_number"),
    ("ice", "QI", "NI", "specific_number"),
    ("graupel", "QG", "BG", "specific_volume"),
)
ISSUES = ("nonfinite", "negative", "mass_only", "moment_only")


def _load_geometry_tools():
    path = Path(__file__).with_name("native_kdm6_call_geometry.py")
    spec = importlib.util.spec_from_file_location("pr74_geometry", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load geometry audit helpers at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _classify(mass: np.ndarray, moment: np.ndarray) -> dict[str, np.ndarray]:
    finite = np.isfinite(mass) & np.isfinite(moment)
    negative = (np.isfinite(mass) & (mass < 0)) | (np.isfinite(moment) & (moment < 0))
    mass_only = finite & (mass > 0) & (moment == 0)
    moment_only = finite & (mass == 0) & (moment > 0)
    absent = finite & (mass == 0) & (moment == 0)
    active = finite & (mass > 0) & (moment > 0)
    invalid = (~finite) | negative
    return {"finite": finite, "nonfinite": ~finite, "negative": negative,
            "mass_only": mass_only, "moment_only": moment_only,
            "absent": absent, "active": active, "invalid": invalid}


def _location(mask: np.ndarray, bounds: dict[str, int]) -> dict[str, int] | None:
    positions = np.argwhere(mask)
    if not len(positions):
        return None
    j0, k0, i0 = (int(x) for x in positions[0])
    return {"i": bounds["its"] + i0, "j": bounds["jts"] + j0,
            "k": bounds["kts"] + k0}


def _finite_stats(values: np.ndarray) -> dict[str, Any]:
    finite = np.isfinite(values)
    sample = values[finite]
    return {"count": int(values.size), "finite": int(finite.sum()),
            "nonfinite": int((~finite).sum()), "negative": int((values < 0).sum()),
            "zero": int((values == 0).sum()), "positive": int((values > 0).sum()),
            "min": float(sample.min()) if sample.size else None,
            "max": float(sample.max()) if sample.size else None}


def audit_fields(fields: dict[str, np.ndarray], dry_density: np.ndarray,
                 dry_mass_weight: np.ndarray, bounds: dict[str, int]) -> dict[str, Any]:
    """Summarize exact paired-state classes in active (j,k,i) trace arrays."""
    expected = dry_density.shape
    if dry_mass_weight.shape != expected:
        raise ValueError("carrier weights and dry density must share active shape")
    species_rows = []
    first_violations = []
    for name, q_field, moment_field, public_basis in SPECIES:
        mass = np.asarray(fields[q_field])
        public_moment = np.asarray(fields[moment_field])
        if mass.shape != expected or public_moment.shape != expected:
            raise ValueError(f"active shape mismatch for {name}")

        # KDM6 converts public N [kg-1 dry air] to internal N [m-3] using
        # moist_to_dry_density followed by specific_number_to_volume.
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            internal_moment = (public_moment * dry_density
                               if public_basis == "specific_number"
                               else public_moment)
        state = _classify(mass, internal_moment)
        counts = {key: int(state[key].sum()) for key in
                  ("absent", "active", "nonfinite", "negative", "mass_only", "moment_only", "invalid")}
        issue_rows = {}
        for issue in ISSUES:
            mask = state[issue]
            issue_rows[issue] = {"count": int(mask.sum()),
                                 "first": _location(mask, bounds)}
        stats = {
            "public_q_kg_kg": _finite_stats(mass),
            "public_moment": _finite_stats(public_moment),
            "internal_moment": _finite_stats(internal_moment),
            "public_moment_basis": (
                "number_per_kg_dry_air" if public_basis == "specific_number"
                else "specific_volume_m3_kg"
            ),
            "internal_moment_basis": (
                "number_per_m3" if public_basis == "specific_number"
                else "specific_volume_m3_kg"
            ),
        }
        weighted = {}
        for issue in ISSUES:
            mask = state[issue] & np.isfinite(mass) & np.isfinite(dry_mass_weight)
            with np.errstate(over="ignore", invalid="ignore"):
                amount = mass[mask].astype(np.float64) * dry_mass_weight[mask].astype(np.float64)
            weighted[issue] = {"cells": int(mask.sum()),
                               "absolute_q_dry_air_mass_kg": float(np.abs(amount).sum())}
        negative_mass = mass[np.isfinite(mass) & (mass < 0)]
        negative_moment = internal_moment[np.isfinite(internal_moment) & (internal_moment < 0)]
        mass_only_values = mass[state["mass_only"]]
        moment_only_values = internal_moment[state["moment_only"]]
        maxima = {
            "most_negative_q_kg_kg": float(negative_mass.min()) if negative_mass.size else None,
            "most_negative_internal_moment": float(negative_moment.min()) if negative_moment.size else None,
            "largest_mass_only_q_kg_kg": float(mass_only_values.max()) if mass_only_values.size else None,
            "largest_moment_only_internal_moment": float(moment_only_values.max()) if moment_only_values.size else None,
        }
        maxima["locations"] = {
            "most_negative_q": _location(np.isfinite(mass) & (mass == maxima["most_negative_q_kg_kg"]), bounds)
            if negative_mass.size else None,
            "most_negative_internal_moment": _location(
                np.isfinite(internal_moment) & (internal_moment == maxima["most_negative_internal_moment"]), bounds)
            if negative_moment.size else None,
            "largest_mass_only_q": _location(state["mass_only"] & (mass == maxima["largest_mass_only_q_kg_kg"]), bounds)
            if mass_only_values.size else None,
            "largest_moment_only_internal_moment": _location(
                state["moment_only"] & (internal_moment == maxima["largest_moment_only_internal_moment"]), bounds)
            if moment_only_values.size else None,
        }
        if state["invalid"].any() or state["mass_only"].any() or state["moment_only"].any():
            first_violations.append((name, state, mass, public_moment, internal_moment))
        species_rows.append({"species": name, "counts": counts, "issues": issue_rows,
                             "values": stats, "max_violation": maxima,
                             "same_carrier_mass_weighted_scale": weighted})

    # The host calls KDM62D once per j; within a call its validator loops k, i,
    # then checks rain, cloud, ice, graupel in that order.
    first = None
    ordered = {name: (state, mass, public_moment, internal_moment)
               for name, state, mass, public_moment, internal_moment in first_violations}
    for j in range(expected[0]):
        for k in range(expected[1]):
            for i in range(expected[2]):
                for name, _, _, _ in SPECIES:
                    if name not in ordered:
                        continue
                    state, mass, public_moment, internal_moment = ordered[name]
                    if state["invalid"][j, k, i] or state["mass_only"][j, k, i] or state["moment_only"][j, k, i]:
                        labels = [key for key in ISSUES if state[key][j, k, i]]
                        first = {
                            "species": name,
                            "state": labels[0] if labels else "invalid",
                            "i": bounds["its"] + i,
                            "j": bounds["jts"] + j,
                            "k": bounds["kts"] + k,
                            "q_kg_kg": float(mass[j, k, i]),
                            "public_moment": float(public_moment[j, k, i]),
                            "internal_moment": float(internal_moment[j, k, i]),
                        }
                        break
                if first:
                    break
            if first:
                break
        if first:
            break
    global_counts = {key: sum(row["counts"][key] for row in species_rows)
                     for key in ("absent", "active", "nonfinite", "negative", "mass_only", "moment_only", "invalid")}
    max_candidates = {
        "most_negative_q_kg_kg": [(row["max_violation"]["most_negative_q_kg_kg"], row)
                                    for row in species_rows if row["max_violation"]["most_negative_q_kg_kg"] is not None],
        "most_negative_internal_moment": [(row["max_violation"]["most_negative_internal_moment"], row)
                                           for row in species_rows if row["max_violation"]["most_negative_internal_moment"] is not None],
        "largest_mass_only_q_kg_kg": [(row["max_violation"]["largest_mass_only_q_kg_kg"], row)
                                      for row in species_rows if row["max_violation"]["largest_mass_only_q_kg_kg"] is not None],
        "largest_moment_only_internal_moment": [(row["max_violation"]["largest_moment_only_internal_moment"], row)
                                                for row in species_rows if row["max_violation"]["largest_moment_only_internal_moment"] is not None],
    }
    global_max = {}
    for key, candidates in max_candidates.items():
        if not candidates:
            global_max[key] = None
            continue
        selected = min(candidates, key=lambda row: row[0]) if key.startswith("most_negative") else max(candidates, key=lambda row: row[0])
        global_max[key] = {"value": selected[0], "species": selected[1]["species"],
                           "location": selected[1]["max_violation"]["locations"][key.removesuffix("_kg_kg")
                               if key.endswith("_kg_kg") else key]}
    global_weighted = {issue: {"cells": sum(row["same_carrier_mass_weighted_scale"][issue]["cells"] for row in species_rows),
                               "absolute_q_dry_air_mass_kg": sum(row["same_carrier_mass_weighted_scale"][issue]["absolute_q_dry_air_mass_kg"] for row in species_rows)}
                       for issue in ISSUES}
    return {"scope": {"shape_jki": list(expected), "bounds": bounds,
                      "positive_carrier_zero_equivalence": "exact: absent iff q == 0 and internal moment == 0; active iff both > 0",
                      "issue_counts_are_independent_predicates": True},
            "first_violation": first,
            "global_counts": global_counts,
            "global_max_violation": global_max,
            "global_same_carrier_mass_weighted_scale": global_weighted,
            "species": species_rows}


def _declared_output_hashes(receipt: dict[str, Any]) -> dict[str, str]:
    isolation = receipt.get("isolation_receipt", {})
    if isolation.get("output_isolation") != "PASS":
        raise ValueError("native capture did not pass output isolation")
    return {row["path"]: row["sha256"] for row in isolation.get("outputs", [])}


def audit_capture_files(trace_path: Path, geometry_path: Path) -> dict[str, Any]:
    """Audit one stage-1 trace with its same-call pre-geometry capture."""
    for path in (trace_path, geometry_path):
        if not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1:
            raise ValueError(f"capture is missing or has unsafe identity: {path}")
    trace = read_dump(trace_path)
    if trace["stage"] != 1:
        raise ValueError("expected KDM6 input trace stage 1")
    geometry_tools = _load_geometry_tools()
    records = geometry_tools.parse_geometry(geometry_path.read_bytes(), require_pair=False)
    pre_geometry = records[0]
    geometry_tools._bound_header_match(pre_geometry, trace)
    measure = geometry_tools.active_geometry_measure(pre_geometry, trace)
    dry_mass = np.transpose(measure["dry_mass"], (1, 0, 2))
    fields = trace["fields"]
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        dry_density = fields["DEN"] / (np.float32(1.0) + fields["Q"])
    if not np.isfinite(dry_density).all() or np.any(dry_density <= 0):
        raise ValueError("same-call source dry carrier density is not finite and positive")
    report = audit_fields(fields, dry_density, dry_mass, trace["bounds"])
    report.update({
        "trace": {"path": str(trace_path), "sha256": trace["sha256"],
                  "stage": trace["stage"], "timestep": trace["itimestep"],
                  "dt_s": trace["params"]["dt_s"]},
        "geometry": {"path": str(geometry_path), "sha256": _sha256(geometry_path),
                     "same_call_bounds_and_dt_verified": True,
                     "dry_mass_weight_source_equation": "dp_k*DX*DY/(MSFTX*MSFTY*g)",
                     "dry_mass_weight_total_kg": float(dry_mass.sum())},
    })
    return report


def audit(native_receipt_path: Path, output: Path | None = None) -> dict[str, Any]:
    native_receipt = json.loads(native_receipt_path.read_text(encoding="utf-8"))
    root = Path(native_receipt["run_root"])
    source_meta = native_receipt["durable_source_artifacts"]
    source_path = native_receipt_path.parent / source_meta["instrumented_source"]
    if (not source_path.is_file() or source_path.is_symlink()
            or _sha256(source_path) != source_meta["instrumented_source_sha256"]
            or source_meta["instrumented_source_sha256"] != native_receipt.get("instrumented_source_sha256")):
        raise ValueError("instrumented native source does not match the PR73 native receipt")
    output_hashes = _declared_output_hashes(native_receipt)
    trace_path = root / "kdm6_first_call_pre.raw"
    geometry_path = root / "pr63_geometry.raw"
    for path in (trace_path, geometry_path):
        if output_hashes.get(path.name) != _sha256(path):
            raise ValueError(f"capture hash does not match native receipt: {path.name}")
    report = audit_capture_files(trace_path, geometry_path)
    native_first = native_receipt.get("first_violation_line", "")
    report.update({
        "schema": "pr74_common_moment_audit_v1",
        "status": "AUDITED_SAME_CALL_TRACE",
        "native_receipt": str(native_receipt_path),
        "native_receipt_sha256": _sha256(native_receipt_path),
        "source_identity": {"source_sha256": native_receipt.get("source_sha256"),
                            "instrumented_source_sha256": native_receipt.get("instrumented_source_sha256"),
                            "instrumented_source_path": str(source_path),
                            "instrumented_source_receipt_hash_verified": True,
                            "native_status": native_receipt.get("status")},
        "native_first_violation_line": native_first,
        "scope_limits": [
            "Trace records public Q and moments at KDM6 entry; it does not capture post-call state.",
            "NC/NI/NR are public specific number per kg dry air; internal volume number is reproduced from the source dry-density conversion.",
            "BG is retained as specific volume; it is not re-labeled as public number concentration.",
            "The hybrid dry-air mass is a same-call carrier scale, not a closed hydrometeor budget or physical validation.",
            "Native run is a controlled first rejection on a retained partialhost research build."
        ],
    })
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native_receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit(args.native_receipt, args.output)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"PR74_COMMON_MOMENT_AUDIT {report['status']}")
    print(f"PR74_FIRST_VIOLATION {report['first_violation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
