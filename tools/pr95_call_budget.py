#!/usr/bin/env python3
"""Receipt-bound T1 KDM6 water change and actual surface-fall account."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import struct
import tempfile
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

from native_kdm6_trace import read_dump
from pr67_kdm6_process_budget import parse_process_capture
from pr87_native_history import _finite

WATER = ("Q", "QC", "QI", "QR", "QS", "QG")
HISTORY = "wrfout_d01_2026-08-16_13:00:00"
TRACE_FIELDS = ("DEN", "Q", "QC", "QI", "QR", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
STATE_MAGICS = {b"PR85QND2", b"PR85QNB1"}
PBL_MAGIC = b"PR85PLB1"
ROOT = Path(__file__).resolve().parents[1]
HELPER_REPORT = ROOT / "docs/evidence/pr93_active_ice_20261020/runtime/c4_pr85_kdm6_paired_sediment_column.json"
HELPER_SOURCE = HELPER_REPORT.with_suffix(".F90")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _expand_bound(run: Path, row: dict[str, Any], temp: Path) -> tuple[Path, dict[str, str]]:
    source = run / row["compressed_path"]
    if sha256(source) != row["compressed_sha256"]:
        raise ValueError(f"compressed receipt hash mismatch: {source}")
    target = temp / Path(row["path"]).name
    with gzip.open(source, "rb") as compressed, target.open("wb") as output:
        while block := compressed.read(8 << 20):
            output.write(block)
    if sha256(target) != row["sha256"]:
        raise ValueError(f"expanded receipt hash mismatch: {target}")
    return target, {"compressed_sha256": row["compressed_sha256"],
                    "expanded_sha256": row["sha256"]}


def _same_float32_bytes(left: np.ndarray, right: np.ndarray) -> bool:
    return (left.shape == right.shape and np.isfinite(left).all() and
            np.isfinite(right).all() and
            left.astype(">f4", copy=False).tobytes() ==
            right.astype(">f4", copy=False).tobytes())


def _read_map_geometry(dataset: netCDF4.Dataset, ys: slice, xs: slice
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read validated history geometry, then select the captured KDM6 tile."""
    mx = _finite(dataset, "MAPFAC_MX", 0)
    my = _finite(dataset, "MAPFAC_MY", 0)
    latitude = _finite(dataset, "XLAT", 0)
    longitude = _finite(dataset, "XLONG", 0)
    dx, dy = float(dataset.DX), float(dataset.DY)
    if not np.isfinite(dx) or not np.isfinite(dy) or dx <= 0 or dy <= 0:
        raise ValueError("DX and DY must be finite and positive")
    if np.any(mx <= 0) or np.any(my <= 0):
        raise ValueError("MAPFAC_MX and MAPFAC_MY must be positive")
    area = dx * dy / (mx[ys, xs] * my[ys, xs])
    if (not np.isfinite(area).all() or np.any(area <= 0) or
            not np.isfinite(latitude[ys, xs]).all() or
            not np.isfinite(longitude[ys, xs]).all()):
        raise ValueError("invalid receipt-bound map area or coordinates")
    return area, latitude[ys, xs], longitude[ys, xs]


def _stats(cell: np.ndarray) -> dict[str, float]:
    if cell.ndim not in (2, 3) or not np.isfinite(cell).all():
        raise ValueError("budget statistics require finite 2D or 3D arrays")
    if cell.ndim == 2:
        return {"signed_kg": float(np.sum(cell, dtype=np.float64)),
                "L1_column_kg": float(np.sum(np.abs(cell), dtype=np.float64)),
                "max_abs_column_kg": float(np.max(np.abs(cell)))}
    column = np.sum(cell, axis=1, dtype=np.float64)
    return {"signed_kg": float(np.sum(cell, dtype=np.float64)),
            "L1_cell_kg": float(np.sum(np.abs(cell), dtype=np.float64)),
            "max_abs_cell_kg": float(np.max(np.abs(cell))),
            "L1_column_kg": float(np.sum(np.abs(column), dtype=np.float64)),
            "max_abs_column_kg": float(np.max(np.abs(column)))}


def _bottom_phase_mass(fall: np.ndarray, delz: np.ndarray, denr: float,
                       dt: float, area: np.ndarray) -> np.ndarray:
    """Map source fall rates through its mm accumulator and water-density conversion."""
    if (fall.ndim != 2 or delz.shape != fall.shape[1:] or area.shape != delz.shape or
            not np.isfinite(fall).all() or np.any(fall < 0) or
            not np.isfinite(delz).all() or np.any(delz <= 0) or
            not np.isfinite(area).all() or np.any(area <= 0) or
            not np.isfinite([denr, dt]).all() or denr <= 0 or dt <= 0):
        raise ValueError("invalid source bottom-fall operands")
    depth_mm = fall * delz[None, :] / denr * dt * 1000.0
    return depth_mm * (denr / 1000.0) * area[None, :]


def _remove_recorded_term(residual: np.ndarray, term: np.ndarray) -> np.ndarray:
    """Remove a signed stored-water change from the pre-numerical residual."""
    if residual.shape != term.shape or not np.isfinite(residual).all() or not np.isfinite(term).all():
        raise ValueError("residual and recorded term must have matching finite shapes")
    return residual - term


def _first_public_call_source_proof(module_sha256: str) -> dict[str, str]:
    """Pin the first-public-call gate that owns the transition ledger."""
    metadata = json.loads(HELPER_REPORT.read_text())
    source_path = Path(metadata["source_path"])
    source = source_path.read_text()
    if sha256(source_path) != module_sha256:
        raise ValueError("first-call gate source is not bound to the C4 module")
    normalized = re.sub(r"\s+", "", source).lower()
    required = ("pr67_trace_this_call=.not.pr67_trace_complete",
                "callkdm62d(", "pr67_trace_this_call&", "pr67_trace_complete=.true.",
                "if(pr67_trace_this_call)thenopen(newunit=pr85_trace_unit,file='pr85_ice_transition_branch.raw'")
    if any(item not in normalized for item in required):
        raise ValueError("transition ledger first-public-call gate changed")
    lines = source.splitlines()
    locations = {
        "gate_assignment_line": next(n for n, line in enumerate(lines, 1)
                                      if "pr67_trace_this_call = .not. pr67_trace_complete" in line),
        "kdm62d_call_line": next(n for n, line in enumerate(lines, 1)
                                 if "call kdm62D(" in line),
        "writer_guard_line": next(n for n, line in enumerate(lines, 1)
                                   if "if (pr67_trace_this_call) then" in line and n > 2500),
        "call_complete_line": next(n for n, line in enumerate(lines, 1)
                                    if "pr67_trace_complete = .true." in line),
    }
    return {"status": "SOURCE_BOUND_FIRST_PUBLIC_CALL", "source_sha256": module_sha256,
            **{key: str(value) for key, value in locations.items()},
            "reason": "KDM6 sets the first-public-call flag, passes it to kdm62D, whose transition writer is guarded by it; KDM6 sets the completion flag before returning. All loop markers in this one-time ledger belong to that public call."}


def _first_call_transition(path: Path, bounds: dict[str, int], mass: np.ndarray,
                         dt: float) -> tuple[np.ndarray, int]:
    """Reduce all loop events in the explicitly first-public-call ledger."""
    transition = np.zeros_like(mass)
    event_count = 0
    current_loop = current_lat = None
    seen_markers: set[tuple[int, int]] = set()
    loops_by_lat: dict[int, set[int]] = {}
    with path.open(encoding="ascii") as source:
        for line in source:
            fields = line.split()
            if not fields:
                continue
            if fields[0] == "PR85_ICE_TRANSITION_LOOP":
                if len(fields) != 8:
                    raise ValueError("ice-transition loop marker contract changed")
                current_loop, current_lat = int(fields[1]), int(fields[2])
                its, ite, kts, kte = map(int, fields[3:7])
                if ((its, ite, kts, kte) != tuple(bounds[key] for key in ("its", "ite", "kts", "kte")) or
                        not bounds["jts"] <= current_lat <= bounds["jte"] or
                        current_loop < 1 or float(fields[7]) != dt):
                    raise ValueError("ice-transition loop marker has invalid call geometry")
                key = (current_loop, current_lat)
                if key in seen_markers:
                    raise ValueError("duplicate ice-transition loop marker")
                seen_markers.add(key)
                loops_by_lat.setdefault(current_lat, set()).add(current_loop)
                continue
            if fields[0] != "PR85_ICE_TRANSITION":
                continue
            if len(fields) != 18 or current_loop is None or current_lat is None:
                raise ValueError("ice-transition event lacks its loop marker")
            i, j, k, loop = map(int, fields[1:5])
            if j != current_lat or loop != current_loop:
                raise ValueError("ice-transition event differs from its loop marker")
            if not (bounds["its"] <= i <= bounds["ite"] and
                    bounds["jts"] <= j <= bounds["jte"] and
                    bounds["kts"] <= k <= bounds["kte"]):
                raise ValueError("ice-transition event lies outside the captured KDM6 tile")
            values = np.asarray(fields[5:], dtype=np.float64)
            if not np.isfinite(values).all() or values[0] != dt:
                raise ValueError("ice-transition event has invalid values or cloud timestep")
            slot = (j - bounds["jts"], k - bounds["kts"], i - bounds["its"])
            phase_delta = (values[10] - values[4]) + (values[11] - values[5])
            transition[slot] += phase_delta * mass[slot]
            event_count += 1
    expected_lats = set(range(bounds["jts"], bounds["jte"] + 1))
    if set(loops_by_lat) != expected_lats:
        raise ValueError("transition ledger does not cover all rows of the first public call")
    for lat, loops in loops_by_lat.items():
        if loops != set(range(1, max(loops) + 1)):
            raise ValueError(f"transition loop markers are incomplete at latitude {lat}")
    return transition, event_count


def _verify_stage_pair(path: Path, expected_sha: str,
                       pre: dict[str, Any], post: dict[str, Any]) -> None:
    """Match full KDM6 arrays to the independent T1 runtime stage observer."""
    if sha256(path) != expected_sha:
        raise ValueError("joint-stage trace compressed hash differs from receipt")
    matches: dict[str, dict[str, np.ndarray]] = {}
    bounds_match = {"PRE_KDM6": False, "POST_KDM6": False}
    with gzip.open(path, "rb") as source:
        while magic := source.read(8):
            label = source.read(32).decode("ascii").strip()
            header = source.read(60)
            if len(header) != 60:
                raise ValueError("truncated joint-stage header")
            kind, timestep, _, *raw_bounds = struct.unpack(">15i", header)
            state = magic in STATE_MAGICS
            if not state and magic != PBL_MAGIC:
                raise ValueError(f"unknown joint-stage record magic: {magic!r}")
            names = TRACE_FIELDS if state else ("QV_TEND", "QC_TEND", "QI_TEND", "QNC_TEND", "QNI_TEND")
            bounds = dict(zip(("ims", "ime", "jms", "jme", "kms", "kme",
                               "its", "ite", "jts", "jte", "kts", "kte"),
                              raw_bounds, strict=True))
            shape = (bounds["jte"] - bounds["jts"] + 1,
                     bounds["kte"] - bounds["kts"] + 1,
                     bounds["ite"] - bounds["its"] + 1)
            size = int(np.prod(shape)) * 4
            target = state and timestep == 1 and label in matches.keys() | {"PRE_KDM6", "POST_KDM6"}
            arrays = {}
            for name in names:
                raw = source.read(size)
                if len(raw) != size:
                    raise ValueError(f"truncated joint-stage {label} {name}")
                if target:
                    arrays[name] = np.frombuffer(raw, dtype=">f4").copy().reshape(shape)
            if target:
                if label in matches:
                    raise ValueError(f"duplicate T1 {label} stage record")
                matches[label] = arrays
                expected = pre if label == "PRE_KDM6" else post
                bounds_match[label] = all(bounds[key] == expected["bounds"][key]
                                          for key in bounds)
            if len(matches) == 2:
                break
    if set(matches) != {"PRE_KDM6", "POST_KDM6"} or not all(bounds_match.values()):
        raise ValueError("joint-stage trace lacks matching T1 pre/post state records")
    for label, expected in (("PRE_KDM6", pre), ("POST_KDM6", post)):
        for name in TRACE_FIELDS:
            observed = matches[label][name]
            captured = expected["fields"][name]
            if not _same_float32_bytes(observed, captured):
                raise ValueError(f"KDM6 dump does not byte-match {label}(1) field {name}")


def _top_boundary_source_proof(module_sha256: str) -> dict[str, Any]:
    """Pin the no-inflow top stencil for paired sedimentation and snow."""
    metadata = json.loads(HELPER_REPORT.read_text())
    body = HELPER_SOURCE.read_text()
    normalized = re.sub(r"\s+", "", body).upper()
    if (metadata.get("routine") != "pr85_kdm6_paired_sediment_column" or
            metadata.get("source_sha256") != module_sha256 or
            sha256(HELPER_SOURCE) != metadata.get("body_sha256")):
        raise ValueError("captured source/helper identity does not support top-face proof")
    required = ("DOK=KTE-1,KTS,-1", "CALLCOMMIT_FACE(K+1,K,.TRUE.)",
                "CALLCOMMIT_FACE(KTS,0,.FALSE.)", "DOK=KTS,KTE-1",
                "CALLCOMMIT_FACE(K+1,K,.TRUE.)")
    if any(item not in normalized for item in required):
        raise ValueError("captured paired sedimentation stencil changed")

    source_path = Path(metadata["source_path"])
    if sha256(source_path) != module_sha256:
        raise ValueError("KDM6 source used for snow top-face proof is not C4-bound")
    source = source_path.read_text()
    start = source.index("subroutine kdm6(")
    snow_top_start = source.index("        k = kte\n", start)
    snow_internal_start = source.index("       do k = kte_in-1,kts,-1", snow_top_start)
    snow_top_block = source[snow_top_start:snow_internal_start]
    snow_block_sha = hashlib.sha256(snow_top_block.encode()).hexdigest()
    if (snow_block_sha != "0bd4d20825171af73374108440c3676772aaf6944c2c484d8b90be287bba5f42" or
            "kte_in = kte" not in source[start:snow_internal_start]):
        raise ValueError("captured snow top-level stencil changed")
    return {"status": "SOURCE_STENCIL_ZERO_FOR_SELECTED_SEDIMENTATION_TOP_FLUX",
            "source_sha256": module_sha256,
            "paired_sedimentation": {"routine": metadata["routine"],
                "body_sha256": metadata["body_sha256"],
                "source_lines": f"{metadata['source_line_start']}-{metadata['source_line_end']}",
                "phases": ["rain", "ice", "graupel"],
                "reason": "The bound helper commits only internal kts..kte faces and a ground face at kts; no upper face is in its interface or stencil."},
            "snow": {"source_path": str(source_path),
                "top_block_sha256": snow_block_sha,
                "line_range": "2914-2926",
                "reason": "kte_in equals kte; at k=kte snow fall is computed from its own top-level state and subtracts only that own outflow. The following internal-transfer loop begins at kte_in-1, so no above-top snow inflow is added."},
            "scope": "Source proves no top precipitation inflow for rain, ice, graupel, and snow in the selected captured KDM6 implementation; no independent runtime top-face flux was captured."}


def _verify_executable_binding(receipt: dict[str, Any], build: dict[str, Any]) -> str:
    executable = build.get("executable_sha256")
    candidate_executable = receipt.get("candidate_build", {}).get("executable_sha256")
    executed = receipt.get("executed_executable_sha256")
    expected = receipt.get("expected_executed_executable_sha256")
    if not executable or {candidate_executable, executed, expected} != {executable}:
        raise ValueError("executed C4 executable does not match the receipt-bound candidate build")
    return executable


def analyze(root: Path) -> dict[str, Any]:
    receipt_path = root / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0:
        raise ValueError(f"run is not a successful COMPLETE receipt: {root}")
    run = root / "run"
    compressed = {Path(row["path"]).name + ".gz": row
                  for row in receipt["compressed_outputs"]}
    generated = {Path(row["path"]).name: row["sha256"]
                 for row in receipt["generated_files"]}
    required = ("kdm6_first_call_pre.raw.gz", "kdm6_first_call_post.raw.gz",
                "pr67_kdm6_process.raw.gz")
    identities = {"receipt_sha256": sha256(receipt_path), "captures": {}}
    candidate = receipt.get("candidate_build", {})
    build_path = Path(candidate.get("receipt_path", ""))
    if not build_path.is_file() or sha256(build_path) != candidate.get("receipt_sha256"):
        raise ValueError("candidate build receipt is missing or not bound by run receipt")
    build = json.loads(build_path.read_text())
    identities["candidate_executable_sha256"] = _verify_executable_binding(receipt, build)
    source = build.get("source_overrides", {}).get("module_mp_kdm6.o")
    if not source or sha256(Path(source["staged_path"])) != source["staged_sha256"]:
        raise ValueError("candidate KDM6 source override is not bound by build receipt")
    identities["candidate_build_receipt_sha256"] = candidate["receipt_sha256"]
    identities["candidate_module_mp_kdm6_sha256"] = source["staged_sha256"]
    top_boundary = _top_boundary_source_proof(source["staged_sha256"])
    transition_source = _first_public_call_source_proof(source["staged_sha256"])
    with tempfile.TemporaryDirectory(prefix="pr95_call_budget_") as directory:
        temp = Path(directory)
        expanded = {}
        for name in required:
            if name not in compressed:
                raise ValueError(f"receipt lacks required capture: {name}")
            expanded[name] = _expand_bound(run, compressed[name], temp)[0]
            identities["captures"][name] = {
                "compressed_sha256": compressed[name]["compressed_sha256"],
                "expanded_sha256": compressed[name]["sha256"]}
        pre = read_dump(expanded[required[0]])
        post = read_dump(expanded[required[1]])
        if (pre["stage"], post["stage"], pre["itimestep"], post["itimestep"]) != (1, 2, 1, 1):
            raise ValueError("captures are not the pre/post T1 KDM6 pair")
        if pre["bounds"] != post["bounds"] or pre["params"] != post["params"]:
            raise ValueError("pre/post call geometry or parameters differ")
        stage_name = "pr85_joint_moment_stages.raw.gz"
        stage_row = compressed.get(stage_name)
        if stage_row is None:
            raise ValueError("receipt lacks the independent T1 joint-stage trace")
        _verify_stage_pair(run / stage_name, stage_row["compressed_sha256"], pre, post)
        identities["stage_pair"] = {"path": str(run / stage_name),
                                     "compressed_sha256": stage_row["compressed_sha256"],
                                     "matched_fields": list(TRACE_FIELDS),
                                     "timestep": 1}
        bounds = pre["bounds"]
        rows = parse_process_capture(expanded[required[2]])
        if len(rows) != 3 * (bounds["jte"] - bounds["jts"] + 1):
            raise ValueError("process capture is not one complete 3-stage call")
        process_rows = [rows[offset:offset + 3] for offset in range(0, len(rows), 3)]
        if any(tuple(row["stage"] for row in group) != (0, 1, 2) for group in process_rows):
            raise ValueError("process capture has incomplete or reordered stages")
        if any(row[0]["lat"] != bounds["jts"] + j for j, row in enumerate(process_rows)):
            raise ValueError("process rows do not span T1 active j bounds")
        if any(row[0]["dtcld"] != pre["params"]["dt_s"] for row in process_rows):
            raise ValueError("process substep duration differs from T1 call duration")

        history = run / HISTORY
        if HISTORY not in generated or sha256(history) != generated[HISTORY]:
            raise ValueError("initial history file is not bound by the run receipt")
        ys = slice(bounds["jts"] - 1, bounds["jte"])
        xs = slice(bounds["its"] - 1, bounds["ite"])
        with netCDF4.Dataset(history) as dataset:
            dataset.set_auto_mask(False)
            area, latitude, longitude = _read_map_geometry(dataset, ys, xs)
        identities["initial_history_sha256"] = generated[HISTORY]

        density = pre["fields"]["DEN"].astype(np.float64)
        delz = pre["fields"]["DELZ"].astype(np.float64)
        if (not np.isfinite(density).all() or not np.isfinite(delz).all() or
                np.any(density <= 0) or np.any(delz <= 0) or
                not np.array_equal(density, post["fields"]["DEN"].astype(np.float64)) or
                not np.array_equal(delz, post["fields"]["DELZ"].astype(np.float64))):
            raise ValueError("same-call DEN/DELZ must be finite, positive, and fixed")
        mass = density * delz * area[:, None, :]
        water_delta = np.zeros_like(mass)
        species = {}
        for name in WATER:
            before = pre["fields"][name].astype(np.float64)
            after = post["fields"][name].astype(np.float64)
            if not np.isfinite(before).all() or not np.isfinite(after).all():
                raise ValueError(f"nonfinite same-call water state: {name}")
            delta = (after - before) * mass
            water_delta += delta
            species[name] = _stats(delta)

        bottom_by_phase = np.zeros((4, area.shape[0], area.shape[1]), dtype=np.float64)
        for j, group in enumerate(process_rows):
            expected = (bounds["its"], bounds["ite"], bounds["kts"], bounds["kte"])
            for row in group:
                if ((row["its"], row["ite"], row["kts"], row["kte"]) != expected or
                        row["lat"] != bounds["jts"] + j or
                        row["dtcld"] != pre["params"]["dt_s"]):
                    raise ValueError(f"process stage header differs from same-call T1 at row {j}")
            # Stage 0 independently binds the process geometry to the KDM6 input.
            if not (np.array_equal(group[0]["density"], density[j]) and
                    np.array_equal(group[0]["delz"], delz[j])):
                raise ValueError(f"process DEN/DELZ differ from same-call input at j row {j}")
            bottom = group[2]
            if not np.array_equal(bottom["delz"], group[0]["delz"][0]):
                raise ValueError(f"stage-2 bottom DELZ differs from same-call stage-0 at j row {j}")
            bottom_by_phase[:, j, :] = _bottom_phase_mass(
                bottom["fall"], bottom["delz"], bottom["denr"], bottom["dtcld"], area[j])
        bottom = np.sum(bottom_by_phase, axis=0, dtype=np.float64)
        residual_before_numerics = np.sum(water_delta, axis=1, dtype=np.float64) + bottom
        rain_name = "pr87_rain_sedimentation_budget.raw.gz"
        rain_row = compressed.get(rain_name)
        if rain_row is None:
            raise ValueError("receipt lacks timestep-marked rain sedimentation ledger")
        rain_path = run / rain_name
        if sha256(rain_path) != rain_row["compressed_sha256"]:
            raise ValueError("rain sedimentation ledger differs from receipt")
        rain_ground = np.zeros_like(area)
        rain_internal_residual = np.zeros_like(area)
        rain_calls = rain_rows = 0
        current_step = current_j = None
        with gzip.open(rain_path, "rt", encoding="ascii") as source:
            for line in source:
                fields = line.split()
                if not fields:
                    continue
                if fields[0] == "PR87_RAIN_CALL":
                    if len(fields) != 4:
                        raise ValueError("rain call marker contract changed")
                    current_step, current_j = int(fields[1]), int(fields[2])
                    if current_step == 1:
                        if current_j != bounds["jts"] + rain_calls or float(fields[3]) != pre["params"]["dt_s"]:
                            raise ValueError("T1 rain call markers do not cover active rows")
                        rain_calls += 1
                    continue
                if fields[0] != "PR87_RAIN_SED" or current_step != 1:
                    continue
                if len(fields) != 17 or current_j is None:
                    raise ValueError("T1 rain sedimentation row contract changed")
                i, j, _substep, nlevels = map(int, fields[1:5])
                values = np.asarray(fields[5:], dtype=np.float64)
                if (not np.isfinite(values).all() or j != current_j or
                        nlevels != bounds["kte"] - bounds["kts"] + 1 or
                        not (bounds["its"] <= i <= bounds["ite"])):
                    raise ValueError("T1 rain sedimentation row has invalid geometry or values")
                ji = (j - bounds["jts"], i - bounds["its"])
                rain_ground[ji] += values[6] * area[ji]
                rain_internal_residual[ji] += values[10] * area[ji]
                rain_rows += 1
        if rain_calls != area.shape[0] or rain_rows == 0:
            raise ValueError("T1 rain ledger does not cover the captured call")
        identities[rain_name] = {"compressed_sha256": rain_row["compressed_sha256"]}
        rain_helper_difference = rain_ground - bottom_by_phase[0]
        transition_name = "pr85_ice_transition_branch.raw.gz"
        transition_row = compressed.get(transition_name)
        if transition_row is None:
            raise ValueError("receipt lacks timestep-marked ice transition ledger")
        transition_path, transition_identity = _expand_bound(run, transition_row, temp)
        transition_map, transition_events = _first_call_transition(
            transition_path, bounds, mass, pre["params"]["dt_s"])
        identities[transition_name] = transition_identity
        transition_by_column = np.sum(transition_map, axis=1, dtype=np.float64)
        residual_by_column = _remove_recorded_term(residual_before_numerics, transition_by_column)
        return {
            "schema": "pr95_samecall_water_account_v1", "arm": receipt["arm"],
            "timestep": 1, "call_seconds": pre["params"]["dt_s"],
            "active_shape_jki": list(mass.shape),
            "measure": "captured KDM6 DEN * DELZ * DX*DY/(MAPFAC_MX*MAPFAC_MY)",
            "units": {"water_inventory_and_bottom_fall": "kg",
                      "bottom_fall_map": "kg per native column",
                      "bottom_fall_source_increment": "mm per KDM6 call; 1 mm = 1 kg m-2"},
            "species_water_delta": species,
            "six_water_delta": _stats(water_delta),
            "actual_bottom_fall_by_species_kg": {
                f"phase_{index + 1}": float(np.sum(bottom_by_phase[index], dtype=np.float64))
                for index in range(4)},
            "actual_bottom_fall": _stats(bottom),
            "focused_delta_plus_bottom_column": _stats(residual_before_numerics),
            "recorded_ice_to_snow_water_delta": _stats(transition_map),
            "recorded_ice_to_snow_event_rows_first_public_call": transition_events,
            "transition_source_call_identity": transition_source,
            "residual_after_reduced_numerical_terms": _stats(residual_by_column),
            "rain_helper_vs_actual_bottom": {
                "ground_approved_minus_public_rain_kg": _stats(rain_helper_difference),
                "ground_approved_rain_kg": _stats(rain_ground),
                "captured_public_rain_kg": _stats(bottom_by_phase[0]),
                "internal_residual_by_column_kg": float(np.sum(rain_internal_residual)),
                "timestep_1_call_markers": rain_calls,
                "timestep_1_rows": rain_rows},
            "numerical_terms": {"status": "PARTIALLY_REDUCED",
                                "reduced": ["all ice-to-snow stored water deltas in the source-bound first public call"],
                                "unreduced_or_unjoinable": [
                                    "cutoff cleanup ledger has no model-timestep marker",
                                    "other stored process-rounding residuals and numerical water adjustments"],
                                "ledger_names": [Path(row["path"]).name
                                                 for row in receipt["compressed_outputs"]
                                                 if "budget.raw" in row["path"] or
                                                 "transition" in row["path"]]},
            "top_boundary_water_flux": top_boundary,
            "closure_status": "OPEN_MISSING_EXACT_CUTOFF_AND_OTHER_NUMERICAL_TERM_REDUCTION",
            "column_residual_shape_ji": list(residual_by_column.shape),
            "identities": identities,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.run_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
