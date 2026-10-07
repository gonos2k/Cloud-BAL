#!/usr/bin/env python3
"""Replay receipt-bound native-carrier water checkpoints from a PR69 observer."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np

from native_kdm6_call_geometry import active_geometry_measure, audit as audit_geometry, parse_geometry
from native_kdm6_trace import read_dump
from pr67_kdm6_process_budget import CaptureError, _verify_receipt, parse_process_capture

MAGIC = b"PR69W001"
STAGES = ("entry", "post_cleanup", "post_mixed_sedimentation", "post_first_ice_substep", "return")
WATER_FIELDS = ("QV", "QC", "QR", "QI", "QS", "QG")
FALL_FIELDS = ("rain", "snow", "graupel", "ice")


def parse_water_capture(path: Path) -> list[dict[str, Any]]:
    """Read complete ordered rows of source-native water and bottom-flux snapshots."""
    raw = path.read_bytes()
    offset = 0
    records: list[dict[str, Any]] = []
    expected_stage = 0
    expected_j: int | None = None
    active_bounds: tuple[int, int, int, int] | None = None
    call_dt: float | None = None
    call_denr: float | None = None
    while offset < len(raw):
        if raw[offset:offset + 8] != MAGIC:
            raise CaptureError(f"wrong PR69 water record magic at byte {offset}")
        offset += 8
        end = offset + 24
        if end > len(raw):
            raise CaptureError(f"truncated PR69 header at byte {offset}")
        stage, j, its, ite, kts, kte = struct.unpack_from(">6i", raw, offset)
        offset = end
        if stage != expected_stage:
            raise CaptureError(f"expected stage {expected_stage}, found {stage}")
        nx, nk = ite - its + 1, kte - kts + 1
        if nx <= 0 or nk <= 0:
            raise CaptureError("invalid PR69 active bounds")
        bounds = (its, ite, kts, kte)
        if active_bounds is None:
            active_bounds = bounds
            expected_j = j
        elif bounds != active_bounds:
            raise CaptureError("PR69 active bounds changed within the call")
        if stage == 0 and j != expected_j:
            raise CaptureError(f"expected ordered j row {expected_j}, found {j}")
        if stage > 0 and j != expected_j:
            raise CaptureError("checkpoint stages do not match the active j row")

        end = offset + 8
        if end > len(raw):
            raise CaptureError("truncated PR69 timestep and DENR")
        dtcld, denr = struct.unpack_from(">2f", raw, offset)
        offset = end
        if stage < 2:
            if dtcld != 0 or denr != 0:
                raise CaptureError("entry and cleanup records must not claim process timing")
        elif not math.isfinite(dtcld) or dtcld <= 0 or not math.isfinite(denr) or denr <= 0:
            raise CaptureError("invalid PR69 timestep or water density")
        elif call_dt is None:
            call_dt, call_denr = dtcld, denr
        elif dtcld != call_dt or denr != call_denr:
            raise CaptureError("PR69 timestep or DENR changed within the call")

        counts = (nx * len(WATER_FIELDS), nx * len(FALL_FIELDS), nx)
        values: list[np.ndarray] = []
        for label, count in zip(("water columns", "bottom fall", "bottom DELZ"), counts, strict=True):
            end = offset + count * 8
            if end > len(raw):
                raise CaptureError(f"truncated PR69 {label} at byte {offset}")
            values.append(np.frombuffer(raw, dtype=">f8", count=count, offset=offset).astype(np.float64))
            offset = end
        water = values[0].reshape((nx, len(WATER_FIELDS)), order="F").T
        bottom_fall = values[1].reshape((nx, len(FALL_FIELDS)), order="F").T
        bottom_delz = values[2]
        if not all(np.isfinite(value).all() for value in (*values, water, bottom_fall)):
            raise CaptureError("PR69 checkpoint contains nonfinite values")
        if np.any(bottom_delz < 0) or np.any(bottom_fall < 0):
            raise CaptureError("PR69 bottom fall or DELZ is negative")
        if stage < 2 and (np.any(bottom_fall != 0) or np.any(bottom_delz != 0)):
            raise CaptureError("entry and cleanup records must not claim bottom flux")
        if stage >= 2 and np.any(bottom_delz <= 0):
            raise CaptureError("process checkpoints require positive bottom DELZ")
        records.append({"stage": stage, "j": j, "bounds": bounds, "dtcld": dtcld,
                        "denr": denr, "water_kg_m2": water,
                        "bottom_fall_kg_m2_s": bottom_fall,
                        "bottom_delz_m": bottom_delz})
        expected_stage += 1
        if expected_stage == len(STAGES):
            expected_stage = 0
            expected_j = j + 1
    if not records or expected_stage != 0:
        raise CaptureError("capture must contain complete five-stage j rows")
    if records[0]["stage"] != 0:
        raise CaptureError("capture does not begin at the entry checkpoint")
    return records


def _read_receipt(path: Path) -> dict[str, Any]:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("returncode") != 0 or receipt.get("input_integrity") != "PASS" or receipt.get("output_isolation") != "PASS":
        raise CaptureError("water observer run is not a successful isolated run")
    return receipt


def audit_build_provenance(path: Path, observer_source_sha256: str,
                           selected_source_sha256: str, receipt: dict[str, Any],
                           executable_sha256: str, receipt_path: Path) -> dict[str, Any]:
    """Bind source/object/archive/link evidence to the executable in the run receipt."""
    provenance = json.loads(path.read_text(encoding="utf-8"))
    if provenance.get("observer_source_sha256") != observer_source_sha256:
        raise CaptureError("build provenance observer source hash differs")
    if provenance.get("selected_source_sha256") != selected_source_sha256:
        raise CaptureError("build provenance selected source hash differs")
    if (provenance.get("member_matches_object") is not True or
            provenance.get("object_sha256") != provenance.get("archive_member_sha256")):
        raise CaptureError("build provenance archive member does not match the compiled object")
    expected_executable = provenance.get("executable_sha256")
    if (not expected_executable or expected_executable != executable_sha256 or
            receipt.get("executable", {}).get("sha256_before") != expected_executable or
            receipt.get("executable", {}).get("sha256_after") != expected_executable):
        raise CaptureError("run executable does not match source-bound build provenance")
    receipt_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    if provenance.get("run_receipt_sha256") != receipt_hash:
        raise CaptureError("run receipt hash differs from build provenance")
    link_argv = path.parent / provenance.get("link_argv_file", "")
    if (not link_argv.is_file() or hashlib.sha256(link_argv.read_bytes()).hexdigest() !=
            provenance.get("link_argv_sha256")):
        raise CaptureError("link argv does not match build provenance")
    return {**provenance, "verified_run_receipt_sha256": receipt_hash}


def audit_process_alignment(rows: list[list[dict[str, Any]]],
                            water_rows: list[list[dict[str, Any]]],
                            expected_bounds: tuple[int, int, int, int]) -> dict[str, Any]:
    """Cross-check PR67 process headers/carriers against PR69 same-call cutoffs."""
    if len(rows) != len(water_rows):
        raise CaptureError("PR67 process and PR69 water row counts differ")
    endpoint_rows = []
    for process_row, water_row in zip(rows, water_rows, strict=True):
        if len(process_row) != 3 or len(water_row) != len(STAGES):
            raise CaptureError("process or water row has incomplete stages")
        expected_j = water_row[0]["j"]
        for stage, record in enumerate(process_row):
            header = (record["its"], record["ite"], record["kts"], record["kte"])
            if (record["stage"] != stage or record["lat"] != expected_j or
                    header != expected_bounds):
                raise CaptureError("PR67 process row stage, j, or active bounds differ from PR69")
            if record["dtcld"] != water_row[min(stage + 2, 4)]["dtcld"]:
                raise CaptureError("PR67 and PR69 process timestep differs")

        # Reproduce the observer's ordered vertical sum for the two QI cutoffs.
        for pr_stage, water_stage in ((0, 2), (1, 3)):
            source = process_row[pr_stage]
            qice = source["qice"]
            density, delz = process_row[0]["density"], process_row[0]["delz"]
            if density is None or delz is None or qice.shape != density.shape or qice.shape != delz.shape:
                raise CaptureError("PR67 QI carrier arrays are missing or have inconsistent shapes")
            integral = np.zeros(qice.shape[1], dtype=np.float64)
            for k in range(qice.shape[0]):
                integral += qice[k] * density[k] * delz[k]
            captured = water_row[water_stage]["water_kg_m2"][3]
            if not np.array_equal(integral, captured):
                raise CaptureError(f"PR67 QI carrier does not match PR69 stage {STAGES[water_stage]}")

        bottom, endpoint = process_row[2], water_row[4]
        if (bottom["denr"] != endpoint["denr"] or
                not np.array_equal(bottom["fall"], endpoint["bottom_fall_kg_m2_s"]) or
                not np.array_equal(bottom["delz"], endpoint["bottom_delz_m"]) or
                not np.array_equal(process_row[0]["density"][0], bottom["density"])):
            raise CaptureError("PR67 bottom-flux operands differ from PR69 KDM6 return capture")
        endpoint_rows.append(expected_j)
    return {"status": "PASS", "rows": len(rows), "first_j": endpoint_rows[0],
            "last_j": endpoint_rows[-1],
            "crosschecks": ["stage-0/1 QI*DEND*DELZ column carrier",
                            "stage-2 bottom FALL, DELZ, DEN, DENR, DTCLD"]}


def analyze(water_path: Path, geometry_path: Path, pre_path: Path, post_path: Path,
            process_path: Path, receipt_path: Path, source_path: Path,
            expected_source_sha256: str, selected_source_sha256: str,
            build_provenance_path: Path) -> dict[str, Any]:
    """Reconcile each captured cutoff with mapped native-carrier storage and export."""
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if source_hash != expected_source_sha256:
        raise CaptureError("observer source does not match the declared source hash")
    if len(selected_source_sha256) != 64 or any(c not in "0123456789abcdef" for c in selected_source_sha256):
        raise CaptureError("selected source SHA-256 must be 64 lowercase hexadecimal characters")
    receipt = _read_receipt(receipt_path)
    _verify_receipt((water_path, geometry_path, pre_path, post_path, process_path), receipt_path)
    records = parse_water_capture(water_path)
    geometry_audit = audit_geometry(geometry_path, pre_path, post_path, receipt_path)
    build_provenance = audit_build_provenance(build_provenance_path, source_hash,
                                               selected_source_sha256, receipt,
                                               geometry_audit["executable_sha256"], receipt_path)
    geometry = parse_geometry(geometry_path.read_bytes())[0]
    pre = read_dump(pre_path)
    post = read_dump(post_path)
    area = active_geometry_measure(geometry, {"bounds": pre["bounds"]})["area"]
    bounds = pre["bounds"]
    expected = (bounds["its"], bounds["ite"], bounds["kts"], bounds["kte"])
    jts, jte = bounds["jts"], bounds["jte"]
    nx, ny = expected[1] - expected[0] + 1, jte - jts + 1
    rows = [records[i:i + len(STAGES)] for i in range(0, len(records), len(STAGES))]
    if len(rows) != ny or any(len(row) != len(STAGES) for row in rows):
        raise CaptureError("PR69 checkpoint rows do not span the KDM6 tile")
    for joff, row in enumerate(rows):
        for stage, record in enumerate(row):
            if (record["stage"] != stage or record["j"] != jts + joff or
                    record["bounds"] != expected or record["water_kg_m2"].shape != (6, nx)):
                raise CaptureError("PR69 rows disagree with KDM6 bounds or stage order")
    if area.shape != (ny, nx):
        raise CaptureError("mapped area does not match PR69 water columns")

    water_by_stage = np.stack([
        np.stack([record["water_kg_m2"] for record in row], axis=0)
        for row in rows
    ]).transpose(1, 0, 2, 3)
    # stages,j,species,i; mapped active area is j,i.
    water_kg = np.sum(water_by_stage * area[None, :, None, :], axis=(1, 3), dtype=np.float64)
    bottom_fall = np.stack([
        np.stack([record["bottom_fall_kg_m2_s"] for record in row], axis=0)
        for row in rows
    ]).transpose(1, 0, 2, 3)
    bottom_delz = np.stack([
        np.stack([record["bottom_delz_m"] for record in row], axis=0)
        for row in rows
    ]).transpose(1, 0, 2)
    process_record = records[2]
    denr = float(process_record["denr"])
    dtcld = float(process_record["dtcld"])
    bottom_export_kg = np.sum(
        bottom_fall * (bottom_delz[:, :, None, :] / denr) * dtcld * 1000.0
        * area[None, :, None, :], axis=(1, 3), dtype=np.float64,
    )
    checkpoint_results = []
    start_total = float(np.sum(water_kg[0], dtype=np.float64))
    for stage, name in enumerate(STAGES):
        stored = float(np.sum(water_kg[stage], dtype=np.float64))
        exported = float(np.sum(bottom_export_kg[stage], dtype=np.float64))
        checkpoint_results.append({
            "stage": name,
            "water_kg": {field: float(water_kg[stage, i]) for i, field in enumerate(WATER_FIELDS)},
            "total_water_kg": stored,
            "cumulative_bottom_export_kg": exported,
            "cumulative_storage_plus_export_residual_kg": stored - start_total + exported,
        })
    interval_results = []
    for i in range(1, len(STAGES)):
        storage_delta = float(np.sum(water_kg[i] - water_kg[i - 1], dtype=np.float64))
        export_delta = float(np.sum(bottom_export_kg[i] - bottom_export_kg[i - 1], dtype=np.float64))
        interval_results.append({
            "stage_interval": f"{STAGES[i - 1]} -> {STAGES[i]}",
            "storage_delta_kg": storage_delta,
            "bottom_export_increment_kg": export_delta,
            "measured_residual_kg": storage_delta + export_delta,
        })

    process_rows = parse_process_capture(process_path)
    if len(process_rows) != ny * 3:
        raise CaptureError("PR67 process capture and PR69 row count differ")
    process_by_row = [process_rows[i * 3:(i + 1) * 3] for i in range(ny)]
    process_alignment = audit_process_alignment(process_by_row, rows, expected)
    density = np.stack([row[0]["density"] for row in process_by_row], axis=1)
    delz = np.stack([row[0]["delz"] for row in process_by_row], axis=1)
    if density.shape != (expected[3] - expected[2] + 1, ny, nx) or delz.shape != density.shape:
        raise CaptureError("PR67 carrier arrays do not match PR69 water columns")
    native_carrier = density * delz * area[None, :, :]
    pre_species = np.stack([pre["fields"][name].transpose(1, 0, 2) for name in ("Q", "QC", "QR", "QI", "QS", "QG")])
    post_species = np.stack([post["fields"][name].transpose(1, 0, 2) for name in ("Q", "QC", "QR", "QI", "QS", "QG")])
    if native_carrier.shape != pre_species.shape[1:] or post_species.shape != pre_species.shape:
        raise CaptureError("endpoint water fields do not match source-native carrier arrays")
    return_total = float(np.sum(water_kg[-1], dtype=np.float64))
    # Promote each source float field before subtraction. Subtracting first in
    # the native float kind loses a material fraction of this call's budget.
    endpoint_change = post_species.astype(np.float64) - pre_species.astype(np.float64)
    endpoint_storage_delta = float(np.sum(endpoint_change * native_carrier[None, :, :, :], dtype=np.float64))
    source_bottom_export = float(np.sum(bottom_export_kg[-1], dtype=np.float64))
    return {
        "schema": "pr69_same_call_native_water_budget_v1",
        "source_binding": {"observer_source": str(source_path), "observer_source_sha256": source_hash,
                           "selected_source_sha256": selected_source_sha256},
        "receipt": {"path": str(receipt_path),
                    "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                    "returncode": receipt["returncode"],
                    "input_integrity": receipt["input_integrity"],
                    "output_isolation": receipt["output_isolation"]},
        "geometry_audit": geometry_audit,
        "build_provenance": {"path": str(build_provenance_path),
                              "sha256": hashlib.sha256(build_provenance_path.read_bytes()).hexdigest(),
                              **{key: value for key, value in build_provenance.items()
                                 if key != "link_argv_file"}},
        "process_alignment": process_alignment,
        "measure_class": "SOURCE_CARRIER_EQUIVALENT_NOT_PHYSICAL_WATER_MASS",
        "quantity_interpretation": {
            "ledger": "The reported kg-valued fields are a source-carrier-equivalent measure formed from captured DEND*Q*DELZ and mapped area.",
            "density_basis": "Host moist_physics_prep_em forms moist DEN as rho=1/ALT*(1+QV), while the reviewed host field declaration identifies Q as specific to dry air. The current source-carrier product therefore is not established as physical water mass on a dry-air carrier.",
            "export": "The bottom increment replays the selected source FALL*DELZ/DENR*DTCLD precipitation equation. Comparing it with source-carrier storage is a source-equation accounting diagnostic, not physical whole-water closure.",
            "status": "PHYSICAL_WATER_MASS_UNSUPPORTED_PENDING_SELECTED_SOURCE_DENSITY_ROUTING",
        },
        "native_measure": "source-carrier-equivalent kg-valued measure: captured DEND*DELZ column integrals times same-call DX*DY/(MSFTX*MSFTY) mapped area; checkpoint columns use binary64 accumulation of captured source float fields; DEND is not proven to be the physical dry-air density",
        "bottom_export_equation": "selected-source precipitation increment: sum(fall_phase(i,kts) * DELZ(i,kts) / DENR * DTCLD * 1000 mm/m) * mapped_area; phase channels follow source rain/snow/graupel/ice ordering",
        "checkpoints": checkpoint_results,
        "intervals": interval_results,
        "endpoint_crosscheck": {
            "checkpoint_return_total_kg": return_total,
            "pre_post_native_carrier_delta_kg": endpoint_storage_delta,
            "checkpoint_minus_pre_post_delta_kg": (return_total - start_total) - endpoint_storage_delta,
            "cumulative_bottom_export_kg": source_bottom_export,
            "native_storage_plus_export_residual_kg": return_total - start_total + source_bottom_export,
        },
        "energy": {"status": "UNSUPPORTED", "reason": "This observer captures water states and precipitation flux only; it does not capture a complete source-defined native energy measure, pressure work, or kinetic-energy terms."},
        "limitations": [
            "The five cutoffs separate entry cleanup, mixed precipitation sedimentation, the first ice substep, and remaining KDM6 evolution; they do not identify individual process-rate transfers within the final interval.",
            "A measured residual is reported as an unresolved term and is not assigned to clipping, rounding, or an inferred source.",
            "Observer reductions are binary64 sums of source-stored fields and are not a model roundoff tolerance or scientific acceptance threshold.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("water", "geometry", "pre", "post", "process", "receipt", "source"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--selected-source-sha256", required=True,
                        help="SHA-256 of the uninstrumented KDM6 source")
    parser.add_argument("--build-provenance", type=Path, required=True,
                        help="source/object/archive/executable binding JSON")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze(args.water, args.geometry, args.pre, args.post, args.process,
                         args.receipt, args.source, args.source_sha256,
                         args.selected_source_sha256, args.build_provenance)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (CaptureError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"PR69 water audit: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
