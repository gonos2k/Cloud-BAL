#!/usr/bin/env python3
"""Strict, bounded collector for the selected CP04 protected-process streams."""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import sys
import uuid
from typing import Iterable, Iterator

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/cp02_protected_process_20261106"
SCHEMA_PATH = EVIDENCE / "native/schema/cp05_schema.json"
SOURCE_RECEIPT = EVIDENCE / "native/source/source_generation_receipt.json"
ANALYSIS_PLAN = EVIDENCE / "analysis_plan.json"
POINTS_PATH = EVIDENCE / "cohorts/point_corners.csv"
UNIQUE_PATH = EVIDENCE / "cohorts/unique_global_corners.csv"
ROLES_PATH = EVIDENCE / "cohorts/role_membership.csv"
COHORT_RECEIPT_PATH = EVIDENCE / "cohorts/receipt.json"
QUICK_PLAN_PATH = EVIDENCE / "native/plans/quick_gate_plan.json"
PLAN_FREEZE_PATH = EVIDENCE / "native/plans/plan_freeze.json"
CAPTURE_PLAN_PATH = EVIDENCE / "native/plans/capture_plan.md"
SCHEMA_SHA256 = "677847102d32b1637340d94bcd24c3856d63348bd15ceb0a319d8b5eda8ff25c"
SOURCE_RECEIPT_SHA256 = "7ed9bf6189249468695e5ce4784f3733d04eed41dae95b3cb31bb46d6bc0ae37"
POINTS_SHA256 = "12a000e1dab5963f7327cce49a44e988940b8e1c208049dd7f5285f126e85ea9"
UNIQUE_SHA256 = "62b365cb0cc57b7b6006d8f6f760021f7424b94d7b381b507aeed093a9664b58"
ROLES_SHA256 = "54cbe13a13a7494fdaf10159919c480f90dfad26dcdcf8337735828d05132cb6"
COHORT_RECEIPT_SHA256 = "cd1e03fbc075c25f6a4904ce278935dea8d23a2157162274835fca21fc911826"
PLAN_FREEZE_SHA256 = "1daab2769d031faecfc84560cbb6f67eecf0bf45b02e92de18a7fa683d1b35a2"
CAPTURE_PLAN_SHA256 = "9183bd9f6bf7d0781cb6793d7f88e7ad6e44d2adb166e065c923bb0b7e67434e"
PROCESS_WINDOWS = ((1, 360), (721, 900))
PROCESS_BLOCKS = ((1, 180), (181, 360), (721, 900))
FULL_BLOCKS = ((1, 180), (181, 360), (361, 540), (541, 720), (721, 900))
CHUNK_STEPS = 3
LEVELS = 39
RANKS = tuple(range(8))
MANDATORY_PHASES = (1, 2, 3, 4, 5, 6, 7, 8, 11, 12)
FRAME_MAGIC = b"C4FR0001"
FRAME_HEADER = struct.Struct(">8i")
RECORD_HEADER = struct.Struct(">7i")
STATE_HEADER = struct.Struct(">8s15i")
STATE_ROW = np.dtype([("i", ">i4"), ("j", ">i4"), ("k", ">i4"), ("v", ">f4", (16,))])
SURFACE_ROW = struct.Struct(">8s5i3f")
FLOAT32 = np.float32


@dataclass(frozen=True)
class CaptureMode:
    name: str
    actual_steps: tuple[int, ...]
    process_steps: tuple[int, ...]
    ranks: tuple[int, ...]
    required_phases: tuple[int, ...]
    plan_path: Path
    plan_sha256: str
    quick_plan_sha256: str
    launch_receipt_path: Path
    launch_receipt_sha256: str
    launch_receipt: dict


def load_mode_contract(mode: str, launch_receipt_path: Path,
                       launch_receipt_sha256: str) -> CaptureMode:
    """Bind capture mode to the completed native-run receipt and its exact plan pin."""
    launch_receipt_path = Path(launch_receipt_path)
    if sha256(launch_receipt_path) != launch_receipt_sha256:
        raise ValueError("native launch-receipt hash mismatch")
    launch_receipt = json.loads(launch_receipt_path.read_text(encoding="utf-8"))
    if mode == "quick":
        path = QUICK_PLAN_PATH
        steps = (1,)
        process_steps = (1,)
        expected_status, expected_duration = "RAW_PROBE_COMPLETED_AWAITING_CAPTURE_GATE", 20
    elif mode == "full":
        path = PLAN_FREEZE_PATH
        steps = tuple(range(1, 901))
        process_steps = tuple(range(1, 361)) + tuple(range(721, 901))
        expected_status, expected_duration = "PASS", 18000
    else:
        raise ValueError("capture mode must be exactly 'quick' or 'full'")
    plan_path = QUICK_PLAN_PATH
    quick_plan_sha = launch_receipt.get("quick_plan_sha256")
    if (launch_receipt.get("stage") != mode or launch_receipt.get("status") != expected_status or
            launch_receipt.get("duration_seconds") != expected_duration or
            not isinstance(quick_plan_sha, str) or sha256(plan_path) != quick_plan_sha):
        raise ValueError(f"launch receipt does not bind the completed {mode} run and current plan")
    if sha256(CAPTURE_PLAN_PATH) != CAPTURE_PLAN_SHA256:
        raise ValueError("frozen capture-plan content hash mismatch")
    if sha256(PLAN_FREEZE_PATH) != PLAN_FREEZE_SHA256:
        raise ValueError("frozen plan-freeze hash mismatch")
    if launch_receipt.get("build_receipt_sha256") != json.loads(plan_path.read_text(encoding="utf-8")).get("pins", {}).get("build_receipt_sha256"):
        raise ValueError("launch receipt does not bind the plan's paired build receipt")
    arm_receipts = launch_receipt.get("arms", {})
    if set(arm_receipts) != {"OLD", "FIX"}:
        raise ValueError("launch receipt must contain exactly OLD and FIX arms")
    for arm, arm_receipt in arm_receipts.items():
        if (arm_receipt.get("arm") != arm or arm_receipt.get("stage") != mode or
                arm_receipt.get("status") != expected_status or arm_receipt.get("exit_code") != 0 or
                not arm_receipt.get("success_marker")):
            raise ValueError(f"{mode} launch receipt has a failed or mismatched {arm} arm")
        comparisons = arm_receipt.get("history_comparisons", {})
        expected_hours = ("12",) if mode == "quick" else tuple(f"{hour:02d}" for hour in range(12, 18))
        if tuple(sorted(comparisons)) != expected_hours or not all(
                row.get("all_variables_coordinates_attributes_exact") for row in comparisons.values()):
            raise ValueError(f"{mode} launch receipt lacks exact expected history parity for {arm}")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if mode == "quick":
        if (plan.get("status") != "FROZEN_QUICK_GATE_PLAN" or
                plan.get("model", {}).get("actual_timesteps") != [1] or
                plan.get("model", {}).get("duration_seconds") != 20 or
                plan.get("mpi", {}).get("ranks") != 8 or
                plan.get("cohort", {}).get("native_columns") != 381):
            raise ValueError("quick plan does not bind the sealed one-step, 8-rank, 381-column gate")
        if plan.get("capture", {}).get("process_chunk_pattern") != "cp04_t000001-000003_rank{rank}.bin":
            raise ValueError("quick plan process filename pattern changed")
        if plan.get("capture", {}).get("required_phase_cell_coverage") != [1, 2, 3, 4, 5, 6, 7, 8, 11, 12]:
            raise ValueError("quick plan required-phase coverage differs from the collector contract")
        pins = plan.get("pins", {})
        if (pins.get("capture_plan_sha256") != CAPTURE_PLAN_SHA256 or
                pins.get("schema_sha256") != SCHEMA_SHA256 or
                pins.get("source_generation_receipt_sha256") != SOURCE_RECEIPT_SHA256):
            raise ValueError("quick plan does not bind final capture/schema/source inputs")
    else:
        if (plan.get("status") != "FROZEN_AWAITING_INDEPENDENT_PLAN_AND_SOURCE_REVIEW" or
                plan.get("capture_steps") != [[1, 360], [721, 900]] or
                plan.get("surface_steps") != [1, 900] or
                plan.get("unique_native_columns") != 381):
            raise ValueError("full plan does not bind the complete declared five-hour capture")
        if plan.get("cohort_sha256", {}).get("capture_plan.md") != CAPTURE_PLAN_SHA256:
            raise ValueError("full plan freeze does not bind final capture-plan hash")
    required_phases = MANDATORY_PHASES
    return CaptureMode(mode, steps, process_steps, RANKS, required_phases, path, sha256(path), quick_plan_sha,
                       launch_receipt_path, launch_receipt_sha256, launch_receipt)


def chunk_starts(steps: Iterable[int]) -> tuple[int, ...]:
    return tuple(sorted({((int(step) - 1) // CHUNK_STEPS) * CHUNK_STEPS + 1 for step in steps}))


def expected_chunk_names(prefix: str, steps: Iterable[int], ranks: Iterable[int]) -> set[str]:
    return {f"{prefix}_t{first:06d}-{min(first + CHUNK_STEPS - 1, 900):06d}_rank{rank}.bin"
            for first in chunk_starts(steps) for rank in ranks}


def validate_case_file_inventory(case_dir: Path, mode: CaptureMode,
                                 inventory: CallInventory | None = None) -> dict[str, list[Path]]:
    """Reject missing/extra files and all unexpected timesteps before decoding data."""
    case_dir = Path(case_dir)
    if not case_dir.is_dir():
        raise ValueError(f"capture case directory does not exist: {case_dir}")
    steps = mode.actual_steps
    expected_full = expected_chunk_names("state_selected_entry", mode.process_steps, mode.ranks)
    expected_return = expected_chunk_names("state_selected_return", mode.process_steps, mode.ranks)
    expected_calls = {f"state_calls_rank{rank}.txt" for rank in mode.ranks}
    actual_entry = {path.name for path in case_dir.glob("state_selected_entry_t*.bin")}
    actual_return = {path.name for path in case_dir.glob("state_selected_return_t*.bin")}
    actual_calls = {path.name for path in case_dir.glob("state_calls_rank*.txt")}
    actual_surface = {path.name for path in case_dir.glob("surface_cp04_rank*.bin")}
    if inventory is None:
        surface_ranks = {int(re.fullmatch(r"surface_cp04_rank(\d+)\.bin", name).group(1))
                         for name in actual_surface}
        if not surface_ranks or not surface_ranks.issubset(mode.ranks):
            raise ValueError(f"{mode.name} surface file rank set is empty or outside plan ranks: {sorted(surface_ranks)}")
        expected_surface = actual_surface
    else:
        surface_ranks = {int(re.fullmatch(r"surface_cp04_rank(\d+)\.bin", name).group(1))
                         for name in actual_surface}
        expected_surface_ranks = set(map(int, np.unique(inventory.owners_rank[
            np.asarray(mode.actual_steps, dtype=np.int32) - 1, 0, :])))
        if surface_ranks != expected_surface_ranks:
            raise ValueError(f"{mode.name} surface ranks differ from selected bottom-level owners")
        expected_surface = {f"surface_cp04_rank{rank}.bin" for rank in expected_surface_ranks}
    for label, actual, expected in (("entry state", actual_entry, expected_full),
                                    ("return state", actual_return, expected_return),
                                    ("call inventory", actual_calls, expected_calls),
                                    ("surface", actual_surface, expected_surface)):
        if actual != expected:
            raise ValueError(f"{mode.name} {label} filenames differ: missing={sorted(expected-actual)[:4]}, extra={sorted(actual-expected)[:4]}")
    process_paths = list(case_dir.glob("cp04_t*.bin"))
    expected_process_steps = mode.process_steps
    expected_by_chunk = {}
    for step in expected_process_steps:
        first = ((step - 1) // CHUNK_STEPS) * CHUNK_STEPS + 1
        expected_by_chunk.setdefault(first, set()).add(step)
    if inventory is not None:
        expected_process = set()
        for first, chunk_steps in expected_by_chunk.items():
            owners = {rank for (step, rank, call), count in inventory.selected_per_call.items()
                      if step in chunk_steps and count > 0}
            expected_process.update(expected_chunk_names("cp04", chunk_steps, owners))
    else:
        actual_ranks = {parse_chunk_filename(path, "cp04")[2] for path in process_paths}
        expected_process = expected_chunk_names("cp04", expected_process_steps, actual_ranks)
    actual_process = {path.name for path in process_paths}
    if actual_process != expected_process:
        raise ValueError(f"{mode.name} process filenames differ: missing={sorted(expected_process-actual_process)[:4]}, extra={sorted(actual_process-expected_process)[:4]}")
    return {
        "entry": sorted(case_dir / name for name in expected_full),
        "return": sorted(case_dir / name for name in expected_return),
        "calls": sorted(case_dir / name for name in expected_calls),
        "surface": sorted(case_dir / name for name in expected_surface),
        "process": sorted(process_paths),
    }


@dataclass(frozen=True)
class Frame:
    rank: int
    call_id: int
    timestep: int
    j: int
    its: int
    ite: int
    kts: int
    kte: int
    constants: tuple[float, ...]


@dataclass(frozen=True)
class Record:
    phase: int
    i: int
    k: int
    loop: int
    loops: int
    substep: int
    mstep: int
    values: np.ndarray


@dataclass
class Cohort:
    cells: list[tuple[int, int]]  # WRF (i,j), 1-based and in unique_global_corners.csv order.
    cell_ids: list[str]
    point_ids: list[str]
    point_cells: np.ndarray
    point_weights: np.ndarray
    point_roles: dict[str, list[str]]


@dataclass
class CallInventory:
    owners_rank: np.ndarray  # (step, level, cell), rank int16, -1 means missing.
    owners_call: np.ndarray  # same shape, call ID int32.
    calls: dict[tuple[int, int, int], tuple[int, int, int, int, int, int]]
    selected_per_call: dict[tuple[int, int, int], int]
    ranks: tuple[int, ...]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_exact(stream, count: int, label: str) -> bytes:
    result = stream.read(count)
    if len(result) != count:
        raise ValueError(f"{label}: truncated stream; wanted {count} bytes, got {len(result)}")
    return result


def load_contract() -> tuple[dict, Cohort, dict]:
    if sha256(SCHEMA_PATH) != SCHEMA_SHA256 or sha256(SOURCE_RECEIPT) != SOURCE_RECEIPT_SHA256:
        raise ValueError("CP05 binary schema hash mismatch")
    source_receipt = json.loads(SOURCE_RECEIPT.read_text(encoding="utf-8"))
    if source_receipt.get("schema_sha256") != SCHEMA_SHA256:
        raise ValueError("source receipt does not bind CP05 schema")
    source_arms = {row.get("arm"): row for row in source_receipt.get("arms", [])}
    if set(source_arms) != {"OLD", "FIX"}:
        raise ValueError("source receipt must bind exactly OLD and FIX source arms")
    for arm, row in source_arms.items():
        source_path = EVIDENCE / "native/source" / Path(row.get("source", "")).name
        if not source_path.is_file() or sha256(source_path) != row.get("sha256"):
            raise ValueError(f"{arm} generated source differs from the source-generation receipt")
    if (sha256(POINTS_PATH) != POINTS_SHA256 or sha256(UNIQUE_PATH) != UNIQUE_SHA256 or
            sha256(ROLES_PATH) != ROLES_SHA256 or sha256(COHORT_RECEIPT_PATH) != COHORT_RECEIPT_SHA256):
        raise ValueError("frozen selected-cohort inputs changed")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if schema.get("phase_window_steps") != [1, 360, 721, 900] or schema.get("chunk_steps") != CHUNK_STEPS:
        raise ValueError("schema process windows or chunk size changed")
    if schema.get("cohort", {}).get("columns") != 381 or schema["cohort"].get("points") != 150:
        raise ValueError("schema selected-cohort counts changed")
    cells_rows = list(csv.DictReader(UNIQUE_PATH.open(newline="", encoding="utf-8")))
    cells = [(int(row["wrf_i_1based"]), int(row["wrf_j_1based"])) for row in cells_rows]
    cell_ids = [row["global_corner_id"] for row in cells_rows]
    if len(cells) != 381 or len(set(cells)) != len(cells) or len(set(cell_ids)) != len(cell_ids):
        raise ValueError("native column selector must contain 381 unique cells and IDs")
    cell_index = {cell: index for index, cell in enumerate(cells)}
    grouped: dict[str, list[tuple[str, int, float]]] = {}
    with POINTS_PATH.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            cell = (int(row["wrf_i_1based"]), int(row["wrf_j_1based"]))
            if cell not in cell_index:
                raise ValueError(f"point {row['point_id']}: corner absent from unique-cell selector")
            grouped.setdefault(row["point_id"], []).append((row["corner"], cell_index[cell], float(row["weight"])))
    point_ids, point_cells, point_weights = [], [], []
    for point_id, rows in grouped.items():
        if len(rows) != 4 or {row[0] for row in rows} != {"00", "10", "01", "11"}:
            raise ValueError(f"{point_id}: expected exactly four native corners")
        weights = np.asarray([row[2] for row in rows], dtype=np.float64)
        if not np.isfinite(weights).all() or np.any(weights < 0) or not math.isclose(float(weights.sum()), 1.0, rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"{point_id}: invalid bilinear weights")
        point_ids.append(point_id)
        point_cells.append([row[1] for row in rows])
        point_weights.append(weights)
    if len(point_ids) != 150:
        raise ValueError("point/corner selector must contain 150 point IDs")
    role_rows: dict[str, list[str]] = {}
    with ROLES_PATH.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            role_rows.setdefault(row["point_id"], []).append(row["role"])
    if set(role_rows) - set(point_ids):
        raise ValueError("role membership references a point outside the frozen selector")
    cohort = Cohort(cells, cell_ids, point_ids, np.asarray(point_cells, dtype=np.int32),
                    np.asarray(point_weights, dtype=np.float64), role_rows)
    return schema, cohort, source_receipt


def parse_chunk_filename(path: Path, prefix: str) -> tuple[int, int, int]:
    match = re.fullmatch(rf"{re.escape(prefix)}_t(\d{{6}})-(\d{{6}})_rank(\d+)\.bin", Path(path).name)
    if not match:
        raise ValueError(f"invalid chunked stream filename: {Path(path).name}")
    first, last, rank = map(int, match.groups())
    if first < 1 or last > 900 or first > last or first % CHUNK_STEPS != 1 or last != min(first + 2, 900):
        raise ValueError(f"invalid timestep chunk bounds in {Path(path).name}")
    return first, last, rank


def timestep_in_process_window(step: int) -> bool:
    return any(start <= step <= end for start, end in PROCESS_WINDOWS)


def validate_process_chunk_step(path: Path, step: int) -> None:
    first, last, _rank = parse_chunk_filename(path, "cp04")
    expected = ((step - 1) // CHUNK_STEPS) * CHUNK_STEPS + 1
    if not timestep_in_process_window(step) or (first, last) != (expected, min(expected + 2, 900)):
        raise ValueError(f"{Path(path).name}: actual timestep {step} is outside its accepted window/chunk")


def iter_process_frames(path: Path, field_counts: dict[int, int], rank: int) -> Iterator[tuple[Frame, list[Record]]]:
    """Decode CP04 one frame at a time without buffering the full stream."""
    with Path(path).open("rb", buffering=1024 * 1024) as stream:
        while magic := stream.read(8):
            if magic != FRAME_MAGIC:
                raise ValueError(f"{path}: invalid CP04 frame marker")
            head = FRAME_HEADER.unpack(read_exact(stream, FRAME_HEADER.size, "CP04 frame header"))
            constants = struct.unpack(">10f", read_exact(stream, 40, "CP04 source constants"))
            if not np.isfinite(constants).all():
                raise ValueError("nonfinite CP04 source constant")
            frame = Frame(*head, tuple(constants))
            first, last, file_rank = parse_chunk_filename(path, "cp04")
            if file_rank != rank or frame.rank != rank or frame.call_id <= 0:
                raise ValueError("CP04 frame rank or call differs from its filename")
            if not first <= frame.timestep <= last:
                raise ValueError("CP04 frame timestep differs from chunk filename")
            validate_process_chunk_step(path, frame.timestep)
            if (frame.j < 1 or frame.its > frame.ite or frame.kts != 1 or frame.kte != LEVELS):
                raise ValueError("invalid CP04 frame tile bounds")
            records: list[Record] = []
            while True:
                phase = struct.unpack(">i", read_exact(stream, 4, "CP04 record marker"))[0]
                if phase == -1:
                    break
                if phase not in field_counts:
                    raise ValueError(f"unknown CP04 phase {phase}")
                i, k, loop, loops, substep, mstep, count = RECORD_HEADER.unpack(
                    read_exact(stream, RECORD_HEADER.size, "CP04 record header"))
                if count != field_counts[phase]:
                    raise ValueError(f"phase {phase}: wrong field count {count}; expected {field_counts[phase]}")
                if not frame.its <= i <= frame.ite or not frame.kts <= k <= frame.kte:
                    raise ValueError("CP04 record lies outside frame core")
                if phase in (1, 2):
                    if (loop, loops, substep, mstep) != (0, 0, 0, 0):
                        raise ValueError("entry phase has invalid loop/substep key")
                elif loop != 1 or loops != 1:
                    raise ValueError("process phase must retain the single actual microphysics loop")
                if phase in (9, 10):
                    if not 1 <= substep <= mstep:
                        raise ValueError("invalid actual sedimentation substep")
                elif substep != 0 or mstep != 0:
                    raise ValueError("unexpected process substep")
                raw = read_exact(stream, count * 4, f"CP04 phase {phase} payload")
                values = np.frombuffer(raw, dtype=">f4").astype(np.float32, copy=True)
                if not np.isfinite(values).all():
                    raise ValueError(f"phase {phase}: nonfinite payload")
                records.append(Record(phase, i, k, loop, loops, substep, mstep, values))
            yield frame, records


def read_call_inventory(paths: Iterable[Path], cells: list[tuple[int, int]], steps: int = 900,
                        levels: int = LEVELS, expected_ranks: tuple[int, ...] = RANKS) -> CallInventory:
    paths = sorted(map(Path, paths))
    if not paths:
        raise ValueError("missing state_calls rank files")
    calls: dict[tuple[int, int, int], tuple[int, int, int, int, int, int]] = {}
    owners_rank = np.full((steps, levels, len(cells)), -1, dtype=np.int16)
    owners_call = np.full((steps, levels, len(cells)), -1, dtype=np.int32)
    selected_per_call: dict[tuple[int, int, int], int] = {}
    ranks_seen = set()
    step_ranks = set()
    for path in paths:
        match = re.fullmatch(r"state_calls_rank(\d+)\.txt", path.name)
        if not match:
            raise ValueError(f"invalid call inventory filename: {path.name}")
        file_rank = int(match.group(1))
        if file_rank in ranks_seen:
            raise ValueError(f"duplicate call inventory file for rank {file_rank}")
        ranks_seen.add(file_rank)
        with path.open("r", encoding="ascii") as stream:
            for number, line in enumerate(stream, 1):
                words = line.split()
                if len(words) != 21:
                    raise ValueError(f"{path}:{number}: call inventory row must have 21 int32 fields")
                try:
                    row = [int(word, 10) for word in words]
                except ValueError as exc:
                    raise ValueError(f"{path}:{number}: noninteger call metadata") from exc
                step, rank, call = row[:3]
                ids, ide, jds, jde, kds, kde = row[3:9]
                ims, ime, jms, jme, kms, kme = row[9:15]
                its, ite, jts, jte, kts, kte = row[15:21]
                if not (rank == file_rank and call > 0 and 1 <= step <= steps and
                        ids <= its <= ite < ide and ims <= its <= ite <= ime and
                        jds <= jts <= jte < jde and jms <= jts <= jte <= jme and
                        kds <= kts <= kte < kde and kms <= kts <= kte <= kme and
                        1 <= kts <= kte <= levels):
                    raise ValueError(f"{path}:{number}: invalid rank/call/tile bounds")
                key = (step, rank, call)
                if key in calls:
                    raise ValueError(f"{path}:{number}: duplicate call key")
                bounds = (its, ite, jts, jte, kts, kte)
                calls[key] = bounds
                step_ranks.add((step, rank))
                selected = 0
                for ci, (i, j) in enumerate(cells):
                    if its <= i <= ite and jts <= j <= jte:
                        for k in range(kts, kte + 1):
                            if k > levels:
                                raise ValueError("call owns a level outside selected 39-level contract")
                            ix = (step - 1, k - 1, ci)
                            if owners_rank[ix] != -1:
                                raise ValueError(f"overlapping selected native core at step={step}, cell={(i,j)}, k={k}")
                            owners_rank[ix], owners_call[ix] = rank, call
                            selected += 1
                if selected:
                    selected_per_call[key] = selected
    if ranks_seen != set(expected_ranks):
        raise ValueError(f"call inventory rank set differs: expected {expected_ranks}, got {sorted(ranks_seen)}")
    missing_steps = {(step, rank) for step in range(1, steps + 1) for rank in expected_ranks} - step_ranks
    if missing_steps:
        raise ValueError(f"call inventory missing rank-step rows: {sorted(missing_steps)[:8]}")
    if np.any(owners_rank < 0) or np.any(owners_call < 0):
        raise ValueError("call inventory lacks one selected-column/level owner for every actual step")
    return CallInventory(owners_rank, owners_call, calls, selected_per_call, tuple(sorted(ranks_seen)))


def _expected_frame_keys(inventory: CallInventory, cells: list[tuple[int, int]], steps: Iterable[int]) -> set[tuple[int, int, int, int, int, int, int, int]]:
    expected = set()
    for step in steps:
        for (call_step, rank, call), bounds in inventory.calls.items():
            if call_step != step or (step, rank, call) not in inventory.selected_per_call:
                continue
            its, ite, jts, jte, kts, kte = bounds
            for i, j in cells:
                if its <= i <= ite and jts <= j <= jte:
                    expected.add((step, rank, call, j, its, ite, kts, kte))
    return expected


def read_state_chunks(paths: Iterable[Path], stage: int, cohort: Cohort, inventory: CallInventory,
                      actual_steps: Iterable[int] = range(1, 901)) -> tuple[np.ndarray, dict]:
    """Read one bounded three-step selected-state chunk at a time into its final slab."""
    if stage not in (6, 7):
        raise ValueError("wrapper-state stage must be entry(6) or return(7)")
    stage_name = {6: "entry", 7: "return"}[stage]
    actual_steps = tuple(map(int, actual_steps))
    if not actual_steps or len(set(actual_steps)) != len(actual_steps):
        raise ValueError("selected-state collector requires a nonempty unique actual-time axis")
    step_index = {step: index for index, step in enumerate(actual_steps)}
    result = np.full((len(actual_steps), LEVELS, len(cohort.cells), 16), np.nan, dtype=np.float32)
    seen = np.zeros((len(actual_steps), LEVELS, len(cohort.cells)), dtype=bool)
    expected_step_set = set(actual_steps)
    expected_blocks = {(step, rank, call) for step, rank, call in inventory.calls
                       if step in expected_step_set}
    seen_blocks = set()
    cell_index = {cell: ci for ci, cell in enumerate(cohort.cells)}
    rows_per_call = {key: count for key, count in inventory.selected_per_call.items()}
    for path in sorted(map(Path, paths)):
        first, last, rank = parse_chunk_filename(path, f"state_selected_{stage_name}")
        if rank not in inventory.ranks:
            raise ValueError(f"{path.name}: rank absent from call inventory")
        with path.open("rb", buffering=1024 * 1024) as stream:
            while raw_header := stream.read(STATE_HEADER.size):
                if len(raw_header) != STATE_HEADER.size:
                    raise ValueError(f"{path}: truncated state block header")
                (magic, sid, fr, call, step, ilo, ihi, jlo, jhi, klo, khi,
                 si, sj, sk, fields, count) = STATE_HEADER.unpack(raw_header)
                key = (step, rank, call)
                expected_bounds = inventory.calls.get(key)
                if (magic != b"CBSP0001" or sid != stage or fr != rank or
                        step not in expected_step_set or not first <= step <= last or expected_bounds is None or
                        expected_bounds != (ilo, ihi, jlo, jhi, klo, khi) or
                        (si, sj, sk, fields) != (1, 1, 1, 16) or count < 0 or
                        count != rows_per_call.get(key, 0) or key in seen_blocks):
                    raise ValueError(f"{path.name}: invalid, duplicate or incomplete selected-state block")
                seen_blocks.add(key)
                rows = np.frombuffer(read_exact(stream, count * STATE_ROW.itemsize, "selected-state rows"), dtype=STATE_ROW)
                if not np.isfinite(rows["v"]).all():
                    raise ValueError("nonfinite selected wrapper state")
                for row in rows:
                    i, j, k = int(row["i"]), int(row["j"]), int(row["k"])
                    ci = cell_index.get((i, j))
                    if (ci is None or not 1 <= k <= LEVELS or
                            inventory.owners_rank[step - 1, k - 1, ci] != rank or
                            inventory.owners_call[step - 1, k - 1, ci] != call):
                        raise ValueError("wrapper state record does not match selected cell owner")
                    ix = (step_index[step], k - 1, ci)
                    if seen[ix]:
                        raise ValueError("duplicate selected wrapper state row")
                    seen[ix] = True
                    result[ix] = row["v"]
    if seen_blocks != expected_blocks:
        raise ValueError(f"selected-state block coverage mismatch: missing {len(expected_blocks-seen_blocks)} blocks")
    if not seen.all():
        raise ValueError("selected wrapper stream lacks full declared actual-step/39-level/native-column coverage")
    th_times_pii = np.multiply(result[..., 0], result[..., 15], dtype=np.float32)
    if not np.array_equal(th_times_pii.view("u4"), result[..., 13].view("u4")):
        raise ValueError("wrapper TK differs bitwise from source-order float32 TH*PII")
    return result, {"blocks": len(seen_blocks), "rows": int(seen.sum()), "stage": stage_name}


def validate_wrapper_binding(wrapper: np.ndarray, internal: dict[int, np.ndarray], phase: int) -> None:
    """Bind public wrapper fields to their actual internal raw/clamped boundary."""
    state = internal[phase]
    pairs = ((14, 0), (1, 1), (13, 2), (12, 3), (2, 4), (4, 5), (3, 6), (5, 7), (6, 8), (11, 15))
    for wrapper_index, state_index in pairs:
        if not np.array_equal(wrapper[..., wrapper_index].view("u4"), state[..., state_index].view("u4")):
            raise ValueError(f"wrapper field {wrapper_index} differs from internal phase {phase} field {state_index}")
    for wrapper_index, state_index in ((8, 9), (9, 10), (7, 11), (10, 12)):
        product = np.multiply(wrapper[..., wrapper_index], wrapper[..., 12], dtype=np.float32)
        if not np.array_equal(product.view("u4"), state[..., state_index].view("u4")):
            raise ValueError("wrapper/internal number density conversion mismatch")


def read_surface(paths: Iterable[Path], cohort: Cohort, inventory: CallInventory,
                 actual_steps: Iterable[int] = range(1, 901)) -> np.ndarray:
    actual_steps = tuple(map(int, actual_steps))
    if not actual_steps or len(set(actual_steps)) != len(actual_steps):
        raise ValueError("surface collector requires a nonempty unique actual-time axis")
    step_index = {step: index for index, step in enumerate(actual_steps)}
    result = np.full((len(actual_steps), len(cohort.cells), 3), np.nan, dtype=np.float32)
    seen = np.zeros((len(actual_steps), len(cohort.cells)), dtype=bool)
    cell_index = {cell: ci for ci, cell in enumerate(cohort.cells)}
    for path in sorted(map(Path, paths)):
        match = re.fullmatch(r"surface_cp04_rank(\d+)\.bin", path.name)
        if not match:
            raise ValueError(f"invalid surface return filename: {path.name}")
        rank = int(match.group(1))
        with path.open("rb", buffering=1024 * 1024) as stream:
            while raw := stream.read(SURFACE_ROW.size):
                if len(raw) != SURFACE_ROW.size:
                    raise ValueError(f"{path}: truncated surface return record")
                magic, file_rank, call, step, j, i, rainncv, rain, sr = SURFACE_ROW.unpack(raw)
                ci = cell_index.get((i, j))
                if (magic != b"C4SR0001" or file_rank != rank or ci is None or step not in step_index or
                        inventory.owners_rank[step - 1, 0, ci] != rank or
                        inventory.owners_call[step - 1, 0, ci] != call or seen[step - 1, ci]):
                    raise ValueError("invalid, duplicate or nonowned surface-return record")
                if not np.isfinite((rainncv, rain, sr)).all():
                    raise ValueError("nonfinite surface return")
                seen[step_index[step], ci] = True
                result[step_index[step], ci] = rainncv, rain, sr
    if not seen.all():
        raise ValueError("surface return lacks complete declared actual-step/native-column coverage")
    return result


class ProcessSlab:
    """Three-step actual-time slab; conditional channels remain NaN with masks."""
    def __init__(self, actual_steps: Iterable[int], schema: dict, ncell: int):
        self.actual_steps = np.asarray(tuple(actual_steps), dtype=np.int32)
        if self.actual_steps.size == 0 or len(np.unique(self.actual_steps)) != self.actual_steps.size:
            raise ValueError("process slab must have unique actual timesteps")
        self.first, self.last = int(self.actual_steps[0]), int(self.actual_steps[-1])
        self.index = {int(step): offset for offset, step in enumerate(self.actual_steps)}
        self.counts = {int(phase): len(spec["fields"]) for phase, spec in schema["phases"].items()}
        self.phases = {phase: np.full((len(self.actual_steps), LEVELS, ncell, count), np.nan, dtype=np.float32)
                       for phase, count in self.counts.items() if phase not in (9, 10, 13, 14)}
        self.phase_masks = {phase: np.zeros((len(self.actual_steps), LEVELS, ncell), dtype=bool)
                            for phase in self.phases}
        self.surface_phases = np.full((2, len(self.actual_steps), ncell, self.counts[13]), np.nan, dtype=np.float32)
        self.surface_masks = np.zeros((2, len(self.actual_steps), ncell), dtype=bool)
        self.mstep = np.zeros((len(self.actual_steps), LEVELS, ncell), dtype=np.int16)
        self.sed_net = np.zeros((len(self.actual_steps), LEVELS, ncell, 3), dtype=np.float64)
        self.sed_fall = np.zeros((len(self.actual_steps), LEVELS, ncell, 5), dtype=np.float64)
        self.sed_falk = np.zeros((len(self.actual_steps), LEVELS, ncell, 5), dtype=np.float64)
        self.sed_pre_first = np.full((len(self.actual_steps), LEVELS, ncell, self.counts[9]), np.nan, dtype=np.float32)
        self.sed_post_last = np.full((len(self.actual_steps), LEVELS, ncell, self.counts[10]), np.nan, dtype=np.float32)
        self.sed_pre_mask = np.zeros((len(self.actual_steps), LEVELS, ncell), dtype=bool)
        self.sed_post_mask = np.zeros_like(self.sed_pre_mask)
        self.phase_counts = {phase: 0 for phase in self.counts}


def _frame_selected_cells(frame: Frame, cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(i, j) for i, j in cells if j == frame.j and frame.its <= i <= frame.ite]


def _store_process_frame(frame: Frame, records: list[Record], slab: ProcessSlab, cohort: Cohort,
                         inventory: CallInventory, cell_index: dict[tuple[int, int], int],
                         required_phases: tuple[int, ...]) -> None:
    """Validate exact cell/phase/substep coverage for one source frame."""
    selected = _frame_selected_cells(frame, cohort.cells)
    if not selected:
        raise ValueError("CP04 frame has no selected native cell in its actual core")
    selected_set = set(selected)
    seen: set[tuple[int, int, int, int, int]] = set()
    loops_by_cell: dict[tuple[int, int], int] = {}
    mstep_by_cell: dict[tuple[int, int], int] = {}
    pending: dict[tuple[int, int, int], np.ndarray] = {}
    sed_substeps: dict[tuple[int, int], set[int]] = {}
    surface_presence: dict[int, set[int]] = {}
    tix = slab.index[frame.timestep]
    for record in records:
        point = (record.i, frame.j)
        if point not in selected_set:
            raise ValueError("CP04 frame contains an unselected native cell")
        ci = cell_index[point]
        if not frame.kts <= record.k <= frame.kte:
            raise ValueError("CP04 record level is outside source core")
        owner_ix = (frame.timestep - 1, record.k - 1, ci)
        if (inventory.owners_rank[owner_ix] != frame.rank or inventory.owners_call[owner_ix] != frame.call_id):
            raise ValueError("CP04 frame record differs from call-inventory owner")
        key = (record.phase, record.i, record.k, record.loop, record.substep)
        if key in seen:
            raise ValueError("duplicate CP04 phase/cell/level/loop/substep record")
        seen.add(key)
        cell_key = (record.i, record.k)
        if record.phase not in (1, 2):
            loops_by_cell[cell_key] = record.loops
            if cell_key in mstep_by_cell and mstep_by_cell[cell_key] != record.mstep and record.phase in (9, 10):
                raise ValueError("sedimentation substep count changed within selected cell")
        if record.phase in slab.phases:
            if record.phase in (15, 16, 17) and slab.phase_masks[record.phase][tix, record.k - 1, ci]:
                raise ValueError("duplicate optional PREVP/cap phase")
            if record.phase not in (15, 16, 17) and slab.phase_masks[record.phase][tix, record.k - 1, ci]:
                raise ValueError("duplicate required CP04 phase")
            slab.phases[record.phase][tix, record.k - 1, ci] = record.values
            slab.phase_masks[record.phase][tix, record.k - 1, ci] = True
        elif record.phase in (13, 14):
            if record.k != frame.kts:
                raise ValueError("conditional surface phase recorded above bottom model level")
            phase_index = record.phase - 13
            if slab.surface_masks[phase_index, tix, ci]:
                raise ValueError("duplicate conditional surface phase")
            slab.surface_phases[phase_index, tix, ci] = record.values
            slab.surface_masks[phase_index, tix, ci] = True
            surface_presence.setdefault(record.i, set()).add(record.phase)
        elif record.phase in (9, 10):
            subkey = (record.i, record.k, record.substep)
            mstep_by_cell[cell_key] = record.mstep
            sed_substeps.setdefault(cell_key, set()).add(record.substep)
            if record.phase == 9:
                if subkey in pending:
                    raise ValueError("duplicate sedimentation pre substep")
                pending[subkey] = record.values.copy()
                if record.substep == 1:
                    slab.sed_pre_first[tix, record.k - 1, ci] = record.values
                    slab.sed_pre_mask[tix, record.k - 1, ci] = True
                slab.sed_fall[tix, record.k - 1, ci] += record.values[17:22].astype(np.float64)
            else:
                before = pending.pop(subkey, None)
                if before is None or record.mstep != mstep_by_cell[cell_key]:
                    raise ValueError("sedimentation post substep lacks matching pre")
                slab.sed_net[tix, record.k - 1, ci] += record.values[5:8].astype(np.float64) - before[5:8].astype(np.float64)
                slab.sed_falk[tix, record.k - 1, ci] += record.values[22:27].astype(np.float64)
                slab.sed_post_last[tix, record.k - 1, ci] = record.values
                slab.sed_post_mask[tix, record.k - 1, ci] = True
        slab.phase_counts[record.phase] += 1
    if pending:
        raise ValueError("sedimentation phase 9/10 records are not paired in the same source frame")
    for i, j in selected:
        ci = cell_index[(i, j)]
        for k in range(frame.kts, frame.kte + 1):
            idx = (tix, k - 1, ci)
            for phase in required_phases:
                if not slab.phase_masks[phase][idx]:
                    raise ValueError(f"missing mandatory phase {phase} at {(frame.timestep, i, j, k)}")
            if bool(slab.phase_masks[11][idx]) != bool(slab.phase_masks[12][idx]):
                raise ValueError("conditional condensation phases 11/12 are not paired")
            if (i, k) not in loops_by_cell or loops_by_cell[(i, k)] != 1:
                raise ValueError("selected cell lacks exactly one source process loop")
            mstep = mstep_by_cell.get((i, k))
            actual_sed_steps = sed_substeps.get((i, k), set())
            if not actual_sed_steps:
                raise ValueError("selected cell/level lacks required sedimentation substep 1")
            if mstep is None or mstep < 1 or actual_sed_steps != set(range(1, mstep + 1)):
                raise ValueError("sedimentation substep coverage differs from actual mstep")
            if int(slab.mstep[idx]) not in (0, mstep):
                raise ValueError("sedimentation mstep changed across frames")
            if mstep is not None:
                slab.mstep[idx] = mstep
            if bool(slab.sed_pre_mask[idx]) != bool(slab.sed_post_mask[idx]):
                raise ValueError("selected cell lacks paired sedimentation state endpoints")
            if surface_presence.get(i, set()) not in (set(), {13, 14}):
                raise ValueError("conditional surface phases 13/14 are not paired")


def read_process_chunk(paths: Iterable[Path], first: int, last: int, schema: dict,
                       cohort: Cohort, inventory: CallInventory,
                       constants_seen: list[tuple[float, ...]],
                       actual_steps: Iterable[int] | None = None,
                       required_phases: tuple[int, ...] = MANDATORY_PHASES
                       ) -> tuple[ProcessSlab, set[tuple[int, int, int, int, int, int, int, int]]]:
    expected_steps = set(actual_steps if actual_steps is not None else range(first, last + 1))
    if any(not timestep_in_process_window(step) for step in expected_steps):
        raise ValueError("requested process slab crosses the uncaptured timestep interval")
    slab = ProcessSlab(sorted(expected_steps), schema, len(cohort.cells))
    cell_index = {cell: ci for ci, cell in enumerate(cohort.cells)}
    expected = _expected_frame_keys(inventory, cohort.cells, expected_steps)
    actual = set()
    paths = sorted(map(Path, paths))
    by_name: dict[tuple[int, int, int], Path] = {}
    for path in paths:
        chunk_first, chunk_last, rank = parse_chunk_filename(path, "cp04")
        if (chunk_first, chunk_last) != (first, last):
            raise ValueError(f"{path.name}: unexpected process chunk range")
        key = (chunk_first, chunk_last, rank)
        if key in by_name:
            raise ValueError(f"duplicate process stream chunk {key}")
        by_name[key] = path
    expected_ranks = {key[1] for key in expected}
    if set(rank for _start, _end, rank in by_name) != expected_ranks:
        raise ValueError(f"process rank files differ from expected selected-frame owners: {set(rank for _,_,rank in by_name)} vs {expected_ranks}")
    counts = {int(phase): len(spec["fields"]) for phase, spec in schema["phases"].items()}
    for (_start, _end, rank), path in sorted(by_name.items()):
        for frame, records in iter_process_frames(path, counts, rank):
            bounds = inventory.calls.get((frame.timestep, rank, frame.call_id))
            if bounds is None:
                raise ValueError("CP04 frame call key absent from full call inventory")
            its, ite, jts, jte, kts, kte = bounds
            if (frame.its, frame.ite, frame.kts, frame.kte) != (its, ite, kts, kte) or not jts <= frame.j <= jte:
                raise ValueError("CP04 frame tile bounds differ from call inventory")
            key = (frame.timestep, rank, frame.call_id, frame.j, frame.its, frame.ite, frame.kts, frame.kte)
            if key in actual:
                raise ValueError("duplicate CP04 frame key")
            actual.add(key)
            if frame.constants not in constants_seen:
                constants_seen.append(frame.constants)
            if len(constants_seen) > 1:
                raise ValueError("source constants changed across actual CP04 frames")
            _store_process_frame(frame, records, slab, cohort, inventory, cell_index, required_phases)
    if actual != expected:
        raise ValueError(f"CP04 frame coverage mismatch: missing={len(expected-actual)}, extra={len(actual-expected)}")
    for phase in slab.phases:
        if phase not in required_phases:
            continue
        if not slab.phase_masks[phase].all():
            raise ValueError(f"incomplete phase {phase} coverage in actual-time slab {first}:{last}")
    if not np.array_equal(slab.sed_pre_mask, slab.sed_post_mask):
        raise ValueError("incomplete phase 9/10 endpoint coverage")
    return slab, actual


def _field_base(name: str) -> str:
    match = re.fullmatch(r"([^()]+)\(([^()]*)\)", name)
    if match:
        field, indices = match.groups()
        index = indices.split(",")[-1].strip()
        if index.isdigit():
            field = f"{field}_{index}"
        name = field
    return name.replace("%", "_").replace("/", "_")


def _f32_add(a, b):
    return np.add(a, b, dtype=np.float32)


def _f32_sub(a, b):
    return np.subtract(a, b, dtype=np.float32)


def _f32_mul(a, b):
    return np.multiply(a, b, dtype=np.float32)


def _f32_div(a, b):
    with np.errstate(divide="raise", invalid="raise", over="raise"):
        return np.divide(a, b, dtype=np.float32)


def process_channels(slab: ProcessSlab, schema: dict, t0c: float) -> tuple[dict[str, np.ndarray], dict]:
    """Return observed source channels and explicit, source-order closure residuals."""
    channels: dict[str, np.ndarray] = {}
    for phase, values in slab.phases.items():
        fields = schema["phases"][str(phase)]["fields"]
        for index, field in enumerate(fields):
            channels[f"phase{phase:02d}_{_field_base(field)}"] = values[..., index]
            channels[f"phase{phase:02d}_{_field_base(field)}_present"] = slab.phase_masks[phase]
    sed_present = slab.sed_pre_mask & slab.sed_post_mask
    for index, name in enumerate(("QR", "QS", "QG")):
        channels[f"sedimentation_net_{name}"] = np.where(sed_present, slab.sed_net[..., index], np.nan)
        channels[f"sedimentation_net_{name}_present"] = sed_present
    for index, name in enumerate(("rain", "snow", "graupel", "number", "bulk")):
        channels[f"sedimentation_fall_sum_{name}"] = np.where(sed_present, slab.sed_fall[..., index], np.nan)
        channels[f"sedimentation_falk_sum_{name}"] = np.where(sed_present, slab.sed_falk[..., index], np.nan)
        channels[f"sedimentation_fall_sum_{name}_present"] = sed_present
        channels[f"sedimentation_falk_sum_{name}_present"] = sed_present

    pre, post, latent, rates = (slab.phases[key] for key in (6, 8, 7, 5))
    rate_fields = [_field_base(name) for name in schema["phases"]["5"]["fields"]]
    rate_index = {name: index for index, name in enumerate(rate_fields)}
    expected_q = _f32_add(pre[..., 1], _f32_mul(pre[..., 16], pre[..., 17]))
    expected_t = _f32_sub(pre[..., 2], _f32_mul(_f32_div(latent[..., 1], latent[..., 2]), latent[..., 3]))
    actual_deltas = {
        "phase8_minus_phase6_QV": post[..., 1].astype(np.float64) - pre[..., 1].astype(np.float64),
        "phase8_minus_phase6_QC": post[..., 4].astype(np.float64) - pre[..., 4].astype(np.float64),
        "phase8_minus_phase6_QR": post[..., 6].astype(np.float64) - pre[..., 6].astype(np.float64),
        "phase8_minus_phase6_TK": post[..., 2].astype(np.float64) - pre[..., 2].astype(np.float64),
    }
    channels.update(actual_deltas)
    q_residual = post[..., 1].astype(np.float64) - expected_q.astype(np.float64)
    t_residual = post[..., 2].astype(np.float64) - expected_t.astype(np.float64)
    channels["source_update_QV_residual"] = q_residual
    channels["source_update_TK_residual"] = t_residual
    channels["source_update_QV_bitwise_match"] = (post[..., 1].view("u4") == expected_q.view("u4"))
    channels["source_update_TK_bitwise_match"] = (post[..., 2].view("u4") == expected_t.view("u4"))
    process_present = slab.phase_masks[5] & slab.phase_masks[6] & slab.phase_masks[7] & slab.phase_masks[8]
    channels["source_update_process_present"] = process_present
    channels["source_update_QV_bitwise_match"] &= process_present
    channels["source_update_TK_bitwise_match"] &= process_present

    pre_cond, post_cond = slab.phases[11], slab.phases[12]
    expected_cond_q = _f32_sub(pre_cond[..., 1], _f32_mul(pre_cond[..., 9], pre_cond[..., 10]))
    expected_cond_t = _f32_add(pre_cond[..., 2],
                               _f32_mul(_f32_div(_f32_mul(pre_cond[..., 9], pre_cond[..., 11]),
                                                pre_cond[..., 12]), pre_cond[..., 10]))
    channels["phase12_minus_phase11_QV"] = post_cond[..., 1].astype(np.float64) - pre_cond[..., 1].astype(np.float64)
    channels["phase12_minus_phase11_QC"] = post_cond[..., 4].astype(np.float64) - pre_cond[..., 4].astype(np.float64)
    channels["phase12_minus_phase11_TK"] = post_cond[..., 2].astype(np.float64) - pre_cond[..., 2].astype(np.float64)
    channels["source_condensation_QV_residual"] = post_cond[..., 1].astype(np.float64) - expected_cond_q.astype(np.float64)
    channels["source_condensation_TK_residual"] = post_cond[..., 2].astype(np.float64) - expected_cond_t.astype(np.float64)
    channels["source_condensation_QV_bitwise_match"] = (post_cond[..., 1].view("u4") == expected_cond_q.view("u4"))
    channels["source_condensation_TK_bitwise_match"] = (post_cond[..., 2].view("u4") == expected_cond_t.view("u4"))
    channels["source_condensation_present"] = slab.phase_masks[11] & slab.phase_masks[12]

    # The signed rain-evaporation product is reported as a source term; it is
    # deliberately separate from the observed phase-8 minus phase-6 delta.
    prevp = rates[..., rate_index["prevp"]]
    prevp_dt = _f32_mul(prevp, pre[..., 17])
    channels["PREVP_times_dtcld_source_term"] = prevp_dt

    # Rebuild the source-ordered rates with an f32 operation after each term.
    def rate_sum(names: tuple[str, ...]) -> np.ndarray:
        value = rates[..., rate_index[names[0]]].copy()
        for name in names[1:]:
            value = _f32_add(value, rates[..., rate_index[name]]) if not name.startswith("-") else _f32_sub(value, rates[..., rate_index[name[1:]]])
        return value

    cold_names = ("praut", "pracw", "prevp", "-piacr", "-pgacr", "-psacr", "-pmulrs", "-pmulrg")
    warm_names = ("praut", "pracw", "prevp", "paacw", "paacw", "-pseml", "-pgeml")
    cold_rate = rate_sum(cold_names)
    warm_rate = rate_sum(warm_names)
    cold = pre[..., 2] <= FLOAT32(t0c)
    qr_source_rate = np.where(cold, cold_rate, warm_rate).astype(np.float32)
    cold_work2 = np.negative(rate_sum(("prevp", "psdep", "pgdep", "pinud", "pidep")), dtype=np.float32)
    warm_work2 = np.negative(rate_sum(("prevp", "psevp", "pgevp")), dtype=np.float32)
    work2_source = np.where(cold, cold_work2, warm_work2).astype(np.float32)
    work2 = pre[..., 16]
    rate_residual = work2.astype(np.float64) - work2_source.astype(np.float64)
    channels["source_work2_cold_warm_rate_residual"] = rate_residual
    channels["source_work2_cold_warm_rate_bitwise_match"] = work2.view("u4") == work2_source.view("u4")
    channels["source_process_rates_present"] = slab.phase_masks[5]
    channels["source_work2_cold_warm_rate_bitwise_match"] &= slab.phase_masks[5]
    qr_term = _f32_mul(qr_source_rate, pre[..., 17])
    qr_candidate = _f32_add(pre[..., 6], qr_term)
    qr_expected = np.maximum(qr_candidate, FLOAT32(0)).astype(np.float32)
    channels["source_QR_cold_warm_residual"] = post[..., 6].astype(np.float64) - qr_expected.astype(np.float64)
    channels["source_QR_cold_warm_bitwise_match"] = post[..., 6].view("u4") == qr_expected.view("u4")
    channels["source_QR_cold_warm_bitwise_match"] &= process_present

    diagnostics = {
        "phase8_QV_source_formula_bitwise_matches": int(np.count_nonzero(channels["source_update_QV_bitwise_match"])),
        "phase8_QV_source_formula_cells": int(process_present.sum()),
        "phase8_TK_source_formula_bitwise_matches": int(np.count_nonzero(channels["source_update_TK_bitwise_match"])),
        "phase8_TK_source_formula_cells": int(process_present.sum()),
        "phase12_QV_source_formula_bitwise_matches": int(np.count_nonzero(channels["source_condensation_QV_bitwise_match"])),
        "phase12_QV_source_formula_cells": int(channels["source_condensation_QV_bitwise_match"].size),
        "phase12_TK_source_formula_bitwise_matches": int(np.count_nonzero(channels["source_condensation_TK_bitwise_match"])),
        "phase12_TK_source_formula_cells": int(channels["source_condensation_TK_bitwise_match"].size),
        "phase5_work2_replayed_bitwise_matches": int(np.count_nonzero(channels["source_work2_cold_warm_rate_bitwise_match"])),
        "phase5_work2_replayed_cells": int(slab.phase_masks[5].sum()),
        "QR_cold_warm_replayed_bitwise_matches": int(np.count_nonzero(channels["source_QR_cold_warm_bitwise_match"])),
        "QR_cold_warm_replayed_cells": int(process_present.sum()),
        "source_QR_replay_status": ("NO_APPLICABLE_SOURCE_RECORDS" if not process_present.any() else
                                    "BITWISE_MATCH" if np.all(channels["source_QR_cold_warm_bitwise_match"][process_present]) else
                                    "UNRESOLVED_NONZERO_RESIDUAL_RECORDED"),
    }
    return channels, diagnostics


def surface_channels(surface: np.ndarray) -> tuple[dict[str, np.ndarray], dict]:
    """Keep source accumulators distinct and compute observed adjacent-step changes."""
    rainncv, rain, sr = (surface[..., index].astype(np.float32, copy=True) for index in range(3))
    rain_delta = np.full(rain.shape, np.nan, dtype=np.float64)
    rain_delta[1:] = rain[1:].astype(np.float64) - rain[:-1].astype(np.float64)
    channels = {"surface_rain_cumulative": rain, "surface_rain_actual_adjacent_delta": rain_delta,
                "surface_rainncv_per_call_increment": rainncv, "surface_sr_source_value": sr}
    return channels, {"steps": int(surface.shape[0]), "native_columns": int(surface.shape[1]),
                      "first_step_delta": "MISSING_NO_PRIOR_CAPTURED_STEP"}


def surface_process_channels(slab: ProcessSlab, schema: dict) -> tuple[dict[str, np.ndarray], dict]:
    channels = {}
    for phase in (13, 14):
        for index, field in enumerate(schema["phases"][str(phase)]["fields"]):
            channels[f"phase{phase:02d}_{_field_base(field)}"] = slab.surface_phases[phase - 13, ..., index]
            channels[f"phase{phase:02d}_{_field_base(field)}_present"] = slab.surface_masks[phase - 13]
    before, after = slab.surface_phases
    present = slab.surface_masks[0]
    # Source computes one float32 operation per expression boundary.
    product = _f32_mul(before[..., 4], before[..., 7])
    rate = _f32_div(product, before[..., 8])
    timed = _f32_mul(rate, before[..., 9])
    amount = _f32_mul(timed, FLOAT32(1000.0))
    expected_rain = _f32_add(before[..., 10], amount)
    expected_rainncv = _f32_add(before[..., 11], amount)
    rain_match = (after[..., 10].view("u4") == expected_rain.view("u4")) & present
    rainncv_match = (after[..., 11].view("u4") == expected_rainncv.view("u4")) & present
    channels["surface_phase14_minus_phase13_rain"] = after[..., 10].astype(np.float64) - before[..., 10].astype(np.float64)
    channels["surface_phase14_minus_phase13_rainncv"] = after[..., 11].astype(np.float64) - before[..., 11].astype(np.float64)
    channels["surface_rain_source_formula_residual"] = after[..., 10].astype(np.float64) - expected_rain.astype(np.float64)
    channels["surface_rainncv_source_formula_residual"] = after[..., 11].astype(np.float64) - expected_rainncv.astype(np.float64)
    channels["surface_rain_source_formula_bitwise_match"] = rain_match
    channels["surface_rainncv_source_formula_bitwise_match"] = rainncv_match
    return channels, {"paired_observed_updates": int(present.sum()),
                      "rain_formula_bitwise_matches": int(rain_match.sum()),
                      "rainncv_formula_bitwise_matches": int(rainncv_match.sum()),
                      "rain_formula_status": ("NO_APPLICABLE_RECORDS" if not present.any() else
                                              "BITWISE_MATCH" if np.array_equal(rain_match, present) else
                                              "UNRESOLVED_NONZERO_RESIDUAL_RECORDED"),
                      "rainncv_formula_status": ("NO_APPLICABLE_RECORDS" if not present.any() else
                                                 "BITWISE_MATCH" if np.array_equal(rainncv_match, present) else
                                                 "UNRESOLVED_NONZERO_RESIDUAL_RECORDED")}


def require_known_source_formula_closure(process: dict, surface: dict) -> None:
    """Fail on a mismatch in source equations whose operands are fully captured."""
    required = (
        ("phase8_QV_source_formula_bitwise_matches", "phase8_QV_source_formula_cells"),
        ("phase8_TK_source_formula_bitwise_matches", "phase8_TK_source_formula_cells"),
        ("phase12_QV_source_formula_bitwise_matches", "phase12_QV_source_formula_cells"),
        ("phase12_TK_source_formula_bitwise_matches", "phase12_TK_source_formula_cells"),
    )
    for matches_key, cells_key in required:
        if process[cells_key] <= 0 or process[matches_key] != process[cells_key]:
            raise ValueError(f"known source arithmetic did not close bitwise: {matches_key}")
    paired = surface["paired_observed_updates"]
    if paired <= 0:
        return
    for channel in ("rain", "rainncv"):
        matched = surface[f"{channel}_formula_bitwise_matches"]
        if matched != paired:
            raise ValueError(f"known surface {channel} source arithmetic did not close bitwise")


def channel_units(name: str, schema: dict) -> str:
    explicit = {
        "phase8_minus_phase6_QV": "kg kg-1", "phase8_minus_phase6_QC": "kg kg-1",
        "phase8_minus_phase6_QR": "kg kg-1", "phase8_minus_phase6_TK": "K",
        "phase12_minus_phase11_QV": "kg kg-1", "phase12_minus_phase11_QC": "kg kg-1",
        "phase12_minus_phase11_TK": "K", "PREVP_times_dtcld_source_term": "kg kg-1 source term",
        "sedimentation_net_QR": "kg kg-1", "sedimentation_net_QS": "kg kg-1",
        "sedimentation_net_QG": "kg kg-1", "surface_rain_cumulative": "mm",
        "surface_rain_actual_adjacent_delta": "mm", "surface_rainncv_per_call_increment": "mm source increment",
        "surface_sr_source_value": "source units as captured",
    }
    if name in explicit:
        return explicit[name]
    if name.endswith("bitwise_match"):
        return "boolean"
    if name.endswith("_present"):
        return "boolean"
    if name.endswith("residual"):
        return "source unit; actual minus source-order replay"
    if name.startswith("surface_") or name.startswith("phase13_") or name.startswith("phase14_"):
        return "source units as captured; see CP05 schema"
    if name.startswith("sedimentation_fall") or name.startswith("sedimentation_falk"):
        return "source units as captured; see CP05 schema"
    if name.startswith("state_"):
        field = name.split("_", 2)[-1]
        return {"TH": "K", "QV": "kg kg-1", "QC": "kg kg-1", "QR": "kg kg-1",
                "QI": "kg kg-1", "QS": "kg kg-1", "QG": "kg kg-1", "NN": "kg-1 number mixing ratio",
                "NC": "kg-1 number mixing ratio", "NI": "kg-1 number mixing ratio",
                "NR": "kg-1 number mixing ratio", "BG": "m3 kg-1 (bg/brs volume mixing ratio)",
                "DEN": "kg m-3", "TK": "K", "P": "Pa", "PII": "dimensionless"}.get(field, "see CP05 schema")
    if name.startswith("phase05_"):
        field = name.removeprefix("phase05_")
        rates = {}
        for index, field_name in enumerate(schema["phases"]["5"]["fields"]):
            unit = "kg kg-1 s-1" if index < 27 else "m-3 s-1" if index < 39 else "dimensionless"
            rates[_field_base(field_name)] = unit
        return rates.get(field, "source units as captured")
    if name.startswith("phase"):
        field = name.split("_", 1)[1]
        if re.fullmatch(r"(?:nci|nrs)_\d+", field):
            return "m-3 internal number concentration"
        if re.fullmatch(r"(?:qci|qrs)_\d+", field):
            return "kg kg-1 mixing ratio"
        if field in {"q", "qs", "qr", "qc", "qi", "qg"}:
            return "kg kg-1 mixing ratio"
        if field in {"p", "pcond"}:
            return "Pa" if field == "p" else "kg kg-1 s-1"
        if field in {"t"}:
            return "K"
        if field in {"den", "dend"}:
            return "kg m-3"
        if field in {"brs", "bg"}:
            return "m3 kg-1 volume mixing ratio"
    if any(f"_{n}_" in name for n in ("p",)) or name.endswith("_p"):
        return "Pa"
    return "source units as captured; see CP05 schema"


class ChannelBank:
    """Disk-backed channel store; RAM holds only one three-step slab at a time."""
    def __init__(self, scratch: Path, process_steps: tuple[int, ...], full_steps: tuple[int, ...], ncell: int):
        self.root = Path(scratch)
        self.process_steps, self.full_steps, self.ncell = process_steps, full_steps, ncell
        self.axes = {"process": process_steps, "full": full_steps}
        self.indices = {axis: {step: offset for offset, step in enumerate(steps)} for axis, steps in self.axes.items()}
        self.entries: dict[str, dict] = {}

    def put(self, name: str, axis: str, actual_steps: Iterable[int], values: np.ndarray, units: str) -> None:
        if axis not in self.axes:
            raise ValueError(f"unknown output timeline {axis}")
        steps = tuple(map(int, actual_steps))
        array = np.asarray(values)
        if array.ndim == 2:
            array = array[:, None, :]
        if array.ndim != 3 or array.shape[0] != len(steps) or array.shape[2] != self.ncell:
            raise ValueError(f"{name}: channel shape must be (actual_time, level, native_column)")
        if not set(steps).issubset(self.indices[axis]):
            raise ValueError(f"{name}: actual timestep is outside its declared timeline")
        entry = self.entries.get(name)
        if entry is None:
            path = self.root / f"{name}.npy"
            path.parent.mkdir(parents=True, exist_ok=True)
            mapped = np.lib.format.open_memmap(path, mode="w+", dtype=array.dtype,
                                               shape=(len(self.axes[axis]), array.shape[1], self.ncell))
            mapped[:] = np.nan if np.issubdtype(array.dtype, np.floating) else 0
            entry = {"axis": axis, "path": path, "array": mapped, "units": units,
                     "written": np.zeros(len(self.axes[axis]), dtype=bool), "levels": array.shape[1], "dtype": str(array.dtype)}
            self.entries[name] = entry
        elif entry["axis"] != axis or entry["levels"] != array.shape[1] or entry["dtype"] != str(array.dtype):
            raise ValueError(f"{name}: channel axis or dtype changed during stream")
        ids = np.asarray([self.indices[axis][step] for step in steps], dtype=np.int64)
        if np.any(entry["written"][ids]):
            raise ValueError(f"{name}: duplicate actual timestep write")
        entry["array"][ids] = array
        entry["written"][ids] = True

    def verify_complete(self) -> None:
        for name, entry in self.entries.items():
            if not entry["written"].all():
                missing = self.axes[entry["axis"]][int(np.flatnonzero(~entry["written"])[0])]
                raise ValueError(f"{name}: output channel lacks actual timestep {missing}")

    def publish(self, stage: Path, cohort: Cohort, max_bytes: int = 100 * 1024 * 1024) -> list[dict]:
        self.verify_complete()
        identities = []
        for name, entry in sorted(self.entries.items()):
            axis = entry["axis"]
            blocks = PROCESS_BLOCKS if axis == "process" else FULL_BLOCKS
            steps_lookup = {step: offset for offset, step in enumerate(self.axes[axis])}
            for first, last in blocks:
                block_steps = tuple(range(first, last + 1))
                if first not in steps_lookup or last not in steps_lookup:
                    raise ValueError(f"{name}: output block {first}-{last} crosses a missing actual-time span")
                offsets = np.asarray([steps_lookup[step] for step in block_steps], dtype=np.int64)
                native = np.asarray(entry["array"][offsets])
                target = stage / name.split("__", 1)[0] / f"lead_{(first + 179) // 180:02d}"
                target.mkdir(parents=True, exist_ok=True)
                path = target / f"{name}.npz"
                arrays = {"actual_timestep": np.asarray(block_steps, dtype=np.int32),
                          "native_column_ids": np.asarray(cohort.cell_ids),
                          "native_i_1based": np.asarray([cell[0] for cell in cohort.cells], dtype=np.int32),
                          "native_j_1based": np.asarray([cell[1] for cell in cohort.cells], dtype=np.int32),
                          "native_values": native,
                          "point_ids": np.asarray(cohort.point_ids),
                          "point_native_corner_indices": cohort.point_cells,
                          "point_corner_weights": cohort.point_weights,
                          "point_roles_json": np.asarray(json.dumps(cohort.point_roles, sort_keys=True)),
                          "units": np.asarray(entry["units"])}
                if np.issubdtype(native.dtype, np.floating):
                    picked = np.take(native, cohort.point_cells, axis=-1)
                    valid = np.isfinite(picked).all(axis=-1)
                    point_values = np.sum(picked.astype(np.float64) * cohort.point_weights, axis=-1)
                    point_values = np.where(valid, point_values, np.nan)
                    arrays["point_values"] = point_values
                    arrays["point_valid"] = valid
                elif np.issubdtype(native.dtype, np.bool_):
                    arrays["point_all_corners_valid"] = np.all(
                        np.take(native, cohort.point_cells, axis=-1), axis=-1)
                np.savez_compressed(path, **arrays)
                size = path.stat().st_size
                if size > max_bytes:
                    raise ValueError(f"{path.name}: compact output exceeds 100 MiB safety limit ({size} bytes)")
                identities.append({"path": str(path.relative_to(stage)), "size_bytes": size,
                                   "sha256": sha256(path), "channel": name, "actual_start": first,
                                   "actual_end": last, "units": entry["units"]})
        return identities


def collect_case(case_dir: Path, mode: str, output_dir: Path,
                 launch_receipt_path: Path, launch_receipt_sha256: str) -> dict:
    """Validate one sealed mode and write a compact, mode-labeled capture receipt."""
    contract = load_mode_contract(mode, launch_receipt_path, launch_receipt_sha256)
    arm = Path(case_dir).name.upper()
    if arm not in ("OLD", "FIX"):
        raise ValueError("case directory must identify exactly one arm by basename OLD or FIX")
    if Path(case_dir).resolve() != Path(contract.launch_receipt["arms"][arm]["case_path"]).resolve():
        raise ValueError(f"capture case directory differs from the sealed {arm} launch receipt")
    schema, cohort, source_receipt = load_contract()
    files = validate_case_file_inventory(case_dir, contract)
    calls = read_call_inventory(files["calls"], cohort.cells, steps=max(contract.actual_steps),
                                expected_ranks=contract.ranks)
    # Revalidate process rank filenames against actual selected-cell owners.
    files = validate_case_file_inventory(case_dir, contract, calls)
    surface = read_surface(files["surface"], cohort, calls, contract.actual_steps)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    scratch = output_dir / ".channel_scratch"
    process_axis = contract.process_steps
    bank = ChannelBank(scratch, process_axis, contract.actual_steps, len(cohort.cells))
    state_names = ("TH", "QV", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG", "DEN", "TK", "P", "PII")
    state_stats = {"entry": [], "return": []}
    for first in chunk_starts(contract.process_steps):
        steps = tuple(step for step in contract.process_steps if first <= step <= first + 2)
        for stage, stage_name in ((6, "entry"), (7, "return")):
            state_files = [path for path in files[stage_name]
                           if parse_chunk_filename(path, f"state_selected_{stage_name}")[:2] == (first, min(first + 2, 900))]
            state, stats = read_state_chunks(state_files, stage, cohort, calls, steps)
            state_stats[stage_name].append(stats)
            for field_ix, field in enumerate(state_names):
                bank.put(f"state_{stage_name}_{field}", "process", steps, state[..., field_ix],
                         channel_units(f"state_{stage_name}_{field}", schema))
    surface_values, surface_stats = surface_channels(surface)
    for name, values in surface_values.items():
        bank.put(name, "full", contract.actual_steps, values, channel_units(name, schema))

    actual_process_frames = 0
    constants_seen: list[tuple[float, ...]] = []
    diagnostics = []
    surface_totals = {"paired_observed_updates": 0, "rain_formula_bitwise_matches": 0,
                      "rainncv_formula_bitwise_matches": 0}
    for first in chunk_starts(contract.process_steps):
        steps = tuple(step for step in contract.process_steps if first <= step <= first + 2)
        chunk_paths = [path for path in files["process"] if parse_chunk_filename(path, "cp04")[:2] ==
                       (first, min(first + 2, 900))]
        slab, frame_keys = read_process_chunk(chunk_paths, first, min(first + 2, 900), schema,
                                              cohort, calls, constants_seen, steps,
                                              contract.required_phases)
        actual_process_frames += len(frame_keys)
        channels, diagnostic = process_channels(slab, schema, constants_seen[0][1])
        surface_channels_for_slab, surface_diagnostic = surface_process_channels(slab, schema)
        require_known_source_formula_closure(diagnostic, surface_diagnostic)
        for key in surface_totals:
            surface_totals[key] += surface_diagnostic[key]
        channels.update(surface_channels_for_slab)
        diagnostics.append({"actual_start": first, "actual_end": steps[-1],
                            "process": diagnostic, "surface": surface_diagnostic})
        for name, values in channels.items():
            bank.put(name, "process", steps, values, channel_units(name, schema))
    surface_totals["formula_scope_status"] = (
        "NO_APPLICABLE_SOURCE_RECORDS" if surface_totals["paired_observed_updates"] == 0 else
        "BITWISE_MATCH" if (surface_totals["rain_formula_bitwise_matches"] == surface_totals["paired_observed_updates"] and
                            surface_totals["rainncv_formula_bitwise_matches"] == surface_totals["paired_observed_updates"]) else
        "UNRESOLVED_NONZERO_RESIDUAL_RECORDED")
    if mode == "quick":
        bank.verify_complete()
        quick_dir = output_dir / "quick_channels"
        quick_dir.mkdir()
        for name, entry in sorted(bank.entries.items()):
            values = np.asarray(entry["array"])
            arrays = {"actual_timestep": np.asarray(contract.actual_steps),
                      "native_column_ids": np.asarray(cohort.cell_ids), "native_values": values,
                      "point_ids": np.asarray(cohort.point_ids), "point_native_corner_indices": cohort.point_cells,
                      "point_corner_weights": cohort.point_weights,
                      "point_roles_json": np.asarray(json.dumps(cohort.point_roles, sort_keys=True)),
                      "units": np.asarray(entry["units"])}
            if np.issubdtype(values.dtype, np.floating):
                picked = np.take(values, cohort.point_cells, axis=-1)
                valid = np.isfinite(picked).all(axis=-1)
                arrays["point_values"] = np.where(valid,
                    np.sum(picked.astype(np.float64) * cohort.point_weights, axis=-1), np.nan)
                arrays["point_valid"] = valid
            elif np.issubdtype(values.dtype, np.bool_):
                arrays["point_all_corners_valid"] = np.all(np.take(values, cohort.point_cells, axis=-1), axis=-1)
            np.savez_compressed(quick_dir / f"{name}.npz", **arrays)
        identities = [{"path": str(path.relative_to(output_dir)), "size_bytes": path.stat().st_size,
                       "sha256": sha256(path)} for path in sorted(quick_dir.glob("*.npz"))]
    else:
        identities = bank.publish(output_dir, cohort)
    total_output_bytes = sum(item["size_bytes"] for item in identities)
    if total_output_bytes > 32 * 1024**3:
        raise ValueError(f"compact diagnostic output exceeds 32 GiB cap ({total_output_bytes} bytes)")
    shutil.rmtree(scratch)
    raw_files = sorted(set(files["entry"] + files["return"] + files["calls"] + files["surface"] + files["process"]))
    receipt = {
        "status": "ONE_STEP_QUICK_GATE_ONLY" if mode == "quick" else "FULL_CAPTURE_STREAMS_VALIDATED",
        "mode": mode,
        "arm": arm,
        "mode_plan_path": str(contract.plan_path.relative_to(ROOT)),
        "mode_plan_sha256": contract.plan_sha256,
        "quick_plan_sha256": contract.quick_plan_sha256,
        "launch_receipt_path": str(contract.launch_receipt_path.resolve()),
        "launch_receipt_sha256": contract.launch_receipt_sha256,
        "capture_plan_sha256": CAPTURE_PLAN_SHA256,
        "tool_sha256": sha256(Path(__file__)),
        "argv": sys.argv[:],
        "schema_sha256": sha256(SCHEMA_PATH),
        "source_generation_receipt_sha256": sha256(SOURCE_RECEIPT),
        "cohort_receipt_sha256": COHORT_RECEIPT_SHA256,
        "actual_timesteps": list(contract.actual_steps),
        "process_actual_timesteps": list(contract.process_steps),
        "rank_ids": list(contract.ranks),
        "native_columns": len(cohort.cells),
        "levels": LEVELS,
        "call_rows": len(calls.calls),
        "selected_call_blocks": len(calls.selected_per_call),
        "entry_state": state_stats["entry"],
        "return_state": state_stats["return"],
        "surface_rows": int(surface.shape[0] * surface.shape[1]),
        "surface_checks": surface_stats,
        "process_frames": actual_process_frames,
        "source_arithmetic_by_chunk": diagnostics,
        "surface_formula_totals": surface_totals,
        "outputs": identities,
        "total_output_bytes": total_output_bytes,
        "raw_stream_files": [{"path": str(path.resolve()), "size_bytes": path.stat().st_size,
                              "sha256": sha256(path)} for path in raw_files],
        "raw_case_dir": str(Path(case_dir).resolve()),
        "full_science_evidence": False,
        "evidence_scope": ("one-step quick gate only" if mode == "quick" else
                           "native streams and source arithmetic only; external history parity gate still required"),
    }
    receipt_path = output_dir / "capture_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("quick", "full"), required=True)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--launch-receipt", type=Path, required=True)
    parser.add_argument("--launch-receipt-sha256", required=True)
    args = parser.parse_args()
    output = fresh_output_path(args.output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name(f".{output.name}.staging-{uuid.uuid4().hex}")
    try:
        receipt = collect_case(args.case_dir, args.mode, stage,
                              args.launch_receipt, args.launch_receipt_sha256)
        stage.rename(output)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    print(json.dumps({"status": receipt["status"], "mode": receipt["mode"],
                      "receipt": str(output / "capture_receipt.json")}, sort_keys=True))
    return 0


def fresh_output_path(path: Path) -> Path:
    """Reject existing paths and symlinks before and after resolving the target."""
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError(f"output directory must be fresh: {path}")
    resolved = path.resolve()
    if resolved.exists() or resolved.is_symlink():
        raise ValueError(f"output directory target must be fresh: {resolved}")
    return resolved


if __name__ == "__main__":
    raise SystemExit(main())




