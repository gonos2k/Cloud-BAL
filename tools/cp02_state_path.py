#!/usr/bin/env python3
"""Strictly validate and analyze CBSP0001 CP02 state-path binary captures.

The reader uses call inventories to validate complete tile coverage, compares
global snapshots through bounded memmaps, and retains selected history only
for the eight frozen RN1 locations. It never fills uncalled global cells.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
from typing import Any
import zipfile

import numpy as np

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = REPO / "docs/evidence/cp02_state_path_20261104/native/state_schema.json"
DEFAULT_CORNERS = REPO / "docs/evidence/cp02_state_path_20261104/cohorts/point_corners.csv"
MAGIC = b"CBSP0001"
HEADER_BYTES = 8 + 15 * 4
HEADER = struct.Struct(">8s15i")
CALL_FIELDS = ("itimestep", "rank", "call_id", "ids", "ide", "jds", "jde", "kds", "kde",
               "ims", "ime", "jms", "jme", "kms", "kme", "its", "ite", "jts", "jte", "kts", "kte")
STAGE_NAMES = {1: "entry", 2: "pre_update", 3: "post_process", 4: "kdm62d_return",
               5: "wrapper_return", 6: "selected_entry", 7: "selected_return"}
PUBLIC_STAGES = {1, 5, 6, 7}
GLOBAL_STAGES = {1, 2, 3, 4, 5}
SELECTED_STAGES = {6, 7}
CALL_FILE_RE = re.compile(r"state_calls_rank(\d+)\.txt$")
BLOCK_FILE_RE = re.compile(r"state_([a-z0-9_]+)_rank(\d+)\.bin(\.gz)?$")
FLOAT32 = np.dtype(">f4")
WORD32 = np.dtype(">u4")
EXPECTED_RANK_MANIFEST_SHA256 = "fd7873a5adcaa3940f35c03c587da5b4e233ee58013c6e7aab4087bda84fa67d"
EXPECTED_SCHEMA_SHA256 = "96207bce9553f94f0457f1daaea0afb534fd34a07a107f24973adc87141afced"
EXPECTED_CORNERS_SHA256 = "c32694fbcdd1fbe85c7b37c4bfb6978f43a1efc417aef0052db7e4ce62bb4618"
RANK_IDS = tuple(range(8))
ARCHIVE_SIDECAR_TYPES = {"BUILD_RECEIPT", "CASE_PLAN", "DIAGNOSTIC_PLAN", "FAILED_ATTEMPT_FORMAT_ADDENDUM",
                        "HISTORY_GATE_SUMMARY", "HISTORY_PREFIX_GATE", "CBSP_SCAN_REPORT", "PATCH_RECEIPT",
                        "PRELAUNCH_GATE", "QUICK_BINARY_SCAN", "QUICK_FORMAT_GATE", "QUICK_RUN_RECEIPT",
                        "RUNTIME_ENVIRONMENT_GATE"}


class StatePathError(ValueError):
    """Input does not satisfy the frozen state-capture contract."""


@dataclass(frozen=True)
class Call:
    timestep: int
    rank: int
    call_id: int
    ids: int
    ide: int
    jds: int
    jde: int
    kds: int
    kde: int
    ims: int
    ime: int
    jms: int
    jme: int
    kms: int
    kme: int
    its: int
    ite: int
    jts: int
    jte: int
    kts: int
    kte: int

    @property
    def key(self) -> tuple[int, int, int]:
        return self.timestep, self.rank, self.call_id

    @property
    def core(self) -> tuple[int, int, int, int, int, int]:
        return max(self.its, self.ids), min(self.ite, self.ide - 1), max(self.jts, self.jds), min(self.jte, self.jde - 1), self.kts, self.kte


@dataclass(frozen=True)
class BlockHeader:
    stage_id: int
    rank: int
    call_id: int
    timestep: int
    ilo: int
    ihi: int
    jlo: int
    jhi: int
    klo: int
    khi: int
    istride: int
    jstride: int
    kstride: int
    field_count: int
    record_count: int

    @classmethod
    def unpack(cls, data: bytes, path: Path, offset: int) -> "BlockHeader":
        if len(data) != HEADER_BYTES:
            raise StatePathError(f"{path}: truncated block header at byte {offset}: {len(data)} bytes")
        values = HEADER.unpack(data)
        if values[0] != MAGIC:
            raise StatePathError(f"{path}: invalid CBSP magic at byte {offset}: {values[0]!r}")
        return cls(*values[1:])


@dataclass(frozen=True)
class StageSpec:
    stage_id: int
    name: str
    fields: tuple[str, ...]
    selected: bool


@dataclass(frozen=True)
class ExpectedBlock:
    call: Call
    stage_id: int
    private_j: int | None
    bounds: tuple[int, int, int, int, int, int]
    records: int

    @property
    def key(self) -> tuple[int, int, int, int | None]:
        return self.call.timestep, self.call.rank, self.call.call_id, self.private_j


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_schema(path: Path) -> tuple[dict[str, Any], dict[int, StageSpec]]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    if schema.get("format") != "CBSP0001":
        raise StatePathError(f"unsupported state schema format: {schema.get('format')!r}")
    if "big_endian" not in schema.get("encoding", ""):
        raise StatePathError("schema must pin Intel -convert big_endian encoding")

    def resolve_fields(name: str, raw: dict[str, Any], seen: set[str]) -> list[str] | None:
        if name in seen:
            raise StatePathError(f"cyclic field reference in schema at {name}")
        fields = raw.get("fields_float32")
        if fields is not None:
            return fields
        target_name = raw.get("fields_same_as")
        if not target_name:
            return None
        target = schema.get("global_stages", {}).get(target_name) or schema.get("selected_stages", {}).get(target_name)
        if target is None:
            raise StatePathError(f"cannot resolve field list {target_name!r} for {name}")
        return resolve_fields(str(target_name), target, seen | {name})

    specs: dict[int, StageSpec] = {}
    for group in ("global_stages", "selected_stages"):
        for name, raw in schema.get(group, {}).items():
            stage_id = int(raw["stage_id"])
            if stage_id not in STAGE_NAMES or STAGE_NAMES[stage_id] != name:
                raise StatePathError(f"unexpected stage id/name pair: {stage_id}/{name}")
            fields = resolve_fields(name, raw, set())
            if not isinstance(fields, list) or not fields or len(fields) != len(set(fields)):
                raise StatePathError(f"{name}: invalid or duplicate float field list")
            expected_count = {1: 14, 2: 15, 3: 15, 4: 15, 5: 14, 6: 14, 7: 14}[stage_id]
            if raw.get("field_count") != len(fields) or len(fields) != expected_count:
                raise StatePathError(f"{name}: schema field_count/list differs from pinned {expected_count}-field contract")
            specs[stage_id] = StageSpec(stage_id, name, tuple(str(v) for v in fields), group == "selected_stages")
    if set(specs) != set(STAGE_NAMES):
        raise StatePathError(f"schema must define all seven stages; found {sorted(specs)}")
    return schema, specs


def validate_frozen_source_pins(schema_path: Path, corners_path: Path) -> None:
    if sha256(schema_path) != EXPECTED_SCHEMA_SHA256:
        raise StatePathError("state schema SHA-256 differs from the frozen native capture schema")
    if sha256(corners_path) != EXPECTED_CORNERS_SHA256:
        raise StatePathError("selected point corners SHA-256 differs from the frozen RN1 cohort")


def read_call_inventory(root: Path, expected_ranks: tuple[int, ...] = RANK_IDS,
                        expected_timesteps: tuple[int, ...] = tuple(range(1, 361))) -> dict[tuple[int, int, int], Call]:
    paths = sorted(root.glob("state_calls_rank*.txt"))
    if not paths:
        raise StatePathError(f"{root}: missing state_calls_rank*.txt call inventory")
    file_ranks = {int(match.group(1)) for path in paths if (match := CALL_FILE_RE.fullmatch(path.name))}
    if file_ranks != set(expected_ranks):
        raise StatePathError(f"{root}: rank inventory {sorted(file_ranks)} != expected {list(expected_ranks)}")
    calls: dict[tuple[int, int, int], Call] = {}
    for path in paths:
        match = CALL_FILE_RE.fullmatch(path.name)
        if not match:
            raise StatePathError(f"invalid call inventory filename: {path.name}")
        file_rank = int(match.group(1))
        with path.open(encoding="ascii") as stream:
            for line, text in enumerate(stream, 1):
                parts = text.split()
                if len(parts) != len(CALL_FIELDS):
                    raise StatePathError(f"{path}:{line}: expected 21 whitespace-separated integers, got {len(parts)}")
                try:
                    values = dict(zip(CALL_FIELDS, map(int, parts)))
                    values["timestep"] = values.pop("itimestep")
                    call = Call(**values)
                except (TypeError, ValueError, KeyError) as exc:
                    raise StatePathError(f"{path}:{line}: invalid integer call field") from exc
                if call.rank != file_rank or call.rank < 0:
                    raise StatePathError(f"{path}:{line}: row rank does not match file rank")
                if call.timestep < 1 or call.timestep > 360 or call.call_id < 1:
                    raise StatePathError(f"{path}:{line}: timestep/call_id outside declared range")
                for lo, hi, name in ((call.ids, call.ide, "i domain"), (call.jds, call.jde, "j domain"),
                                     (call.kds, call.kde, "k domain"), (call.its, call.ite, "i tile"),
                                     (call.jts, call.jte, "j tile"), (call.kts, call.kte, "k tile")):
                    if lo < 1 or hi < lo:
                        raise StatePathError(f"{path}:{line}: invalid {name} bounds {lo}:{hi}")
                for lo, hi, name in ((call.ims, call.ime, "i memory"), (call.jms, call.jme, "j memory"),
                                     (call.kms, call.kme, "k memory")):
                    if hi < lo:
                        raise StatePathError(f"{path}:{line}: invalid {name} bounds {lo}:{hi}")
                if not (call.ids <= call.its <= call.ite < call.ide and call.ims <= call.its <= call.ite <= call.ime and
                        call.jds <= call.jts <= call.jte < call.jde and call.jms <= call.jts <= call.jte <= call.jme and
                        call.kds <= call.kts <= call.kte < call.kde and call.kms <= call.kts <= call.kte <= call.kme):
                    raise StatePathError(f"{path}:{line}: tile bounds outside memory/domain bounds")
                if call.key in calls:
                    raise StatePathError(f"{path}:{line}: duplicate call inventory key {call.key}")
                calls[call.key] = call
    present_steps = {call.timestep for call in calls.values()}
    wanted_steps = set(expected_timesteps)
    if present_steps != wanted_steps:
        missing, extra = sorted(wanted_steps - present_steps), sorted(present_steps - wanted_steps)
        raise StatePathError(f"call inventory timestep coverage differs; missing={missing[:8]}, unexpected={extra[:8]}")
    return calls


def _resolve_pinned_path(raw_path: str, manifest_path: Path, arm_root: Path | None = None) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    candidates = [manifest_path.parent / path, manifest_path.parent.parent / path, REPO / path]
    if arm_root is not None:
        candidates.extend((arm_root / path, arm_root / path.name))
    candidates.append(Path.cwd() / path)
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def _inventory_file_summary(path: Path) -> dict[str, Any]:
    first, last, lines = None, None, 0
    with path.open(encoding="ascii") as stream:
        for line, text in enumerate(stream, 1):
            parts = text.split()
            if len(parts) != len(CALL_FIELDS):
                raise StatePathError(f"{path}:{line}: expected 21 whitespace-separated integers, got {len(parts)}")
            try:
                timestep = int(parts[0])
            except ValueError as exc:
                raise StatePathError(f"{path}:{line}: invalid timestep") from exc
            first = timestep if first is None else min(first, timestep)
            last = timestep if last is None else max(last, timestep)
            lines += 1
    return {"sha256": sha256(path), "byte_count": path.stat().st_size, "line_count": lines,
            "first_timestep": first, "last_timestep": last}


def validate_rank_manifests(expected_path: Path, observed_path: Path,
                            arm_roots: dict[str, Path]) -> dict[str, Any]:
    if sha256(expected_path) != EXPECTED_RANK_MANIFEST_SHA256:
        raise StatePathError("expected-rank manifest SHA-256 differs from the pinned prelaunch gate")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    if expected.get("format") != "CBSP_EXPECTED_RANKS_v1" or expected.get("mpi_ranks") != len(RANK_IDS):
        raise StatePathError("unsupported expected-rank manifest format or MPI rank count")
    expected_ids = expected.get("expected_rank_ids")
    if expected_ids != list(RANK_IDS):
        raise StatePathError(f"expected-rank manifest must list exact IDs {list(RANK_IDS)}")
    observed = json.loads(observed_path.read_text(encoding="utf-8"))
    if observed.get("format") != "CBSP_OBSERVED_RANKS_v1":
        raise StatePathError("unsupported observed-rank manifest format")
    expected_binding = observed.get("expected_manifest", {})
    expected_ref = _resolve_pinned_path(str(expected_binding.get("path", expected_binding.get("archive_path", ""))),
                                        observed_path)
    if expected_ref.resolve() != expected_path.resolve() or expected_binding.get("sha256") != EXPECTED_RANK_MANIFEST_SHA256:
        raise StatePathError("observed-rank manifest does not bind the pinned expected-rank sidecar")
    checks = observed.get("checks", {})
    required_checks = ("all_expected_rank_files_present", "exact_rank_sets",
                       "per_rank_inventory_hash_equal", "arm_inventories_identical")
    byte_check = checks.get("per_rank_inventory_bytes_and_counts_equal", checks.get("per_rank_inventory_bytes_equal"))
    if byte_check is not True or any(checks.get(name) is not True for name in required_checks):
        raise StatePathError("observed-rank manifest reports a failed completeness/equality check")
    arms = observed.get("arms", {})
    if set(arms) != set(arm_roots):
        raise StatePathError(f"observed-rank arms differ from requested pair: {sorted(arms)}")
    resolved = {}
    for arm, root in arm_roots.items():
        record = arms[arm]
        if record.get("expected_rank_ids") != list(RANK_IDS) or record.get("observed_rank_ids") != list(RANK_IDS):
            raise StatePathError(f"{arm}: observed rank IDs do not match expected 0..7")
        inventories = record.get("inventories", {})
        if set(inventories) != {str(rank) for rank in RANK_IDS}:
            raise StatePathError(f"{arm}: observed inventory must contain exactly ranks 0..7")
        launch = record.get("launch_receipt", {})
        launch_path = _resolve_pinned_path(str(launch.get("path", launch.get("archive_path", ""))), observed_path, root)
        if not launch_path.is_file() or sha256(launch_path) != launch.get("sha256"):
            raise StatePathError(f"{arm}: launch receipt is missing or its SHA-256 differs from the observed manifest")
        for rank in RANK_IDS:
            name = f"state_calls_rank{rank}.txt"
            path = root / name
            inventory = inventories[str(rank)]
            if not path.is_file():
                raise StatePathError(f"{arm}: rank {rank} inventory is missing")
            manifest_path = _resolve_pinned_path(str(inventory.get("path", inventory.get("archive_path", ""))),
                                                 observed_path, root)
            if manifest_path.resolve() != path.resolve():
                raise StatePathError(f"{arm}: rank {rank} inventory path differs from requested runtime root")
            actual = _inventory_file_summary(path)
            for key in ("sha256", "byte_count", "line_count", "first_timestep", "last_timestep"):
                if actual[key] != inventory.get(key):
                    raise StatePathError(f"{arm}: rank {rank} inventory {key} differs from observed manifest")
            if actual["line_count"] and (actual["first_timestep"] != 1 or actual["last_timestep"] != 360):
                raise StatePathError(f"{arm}: rank {rank} invocation inventory does not span steps 1..360")
        resolved[arm] = {"launch_receipt_path": launch_path.name,
                         "launch_receipt_sha256": launch["sha256"],
                         "inventory_sha256_by_rank": {rank: inventories[str(rank)]["sha256"] for rank in RANK_IDS}}
    if resolved["OLD"]["inventory_sha256_by_rank"] != resolved["FIX"]["inventory_sha256_by_rank"]:
        raise StatePathError("OLD/FIX call inventory SHA-256 differs by rank")
    return {"expected_manifest_path": expected_path.name, "expected_manifest_sha256": EXPECTED_RANK_MANIFEST_SHA256,
            "observed_manifest_path": observed_path.name, "observed_manifest_sha256": sha256(observed_path),
            "expected_rank_ids": list(RANK_IDS), "arms": resolved, "checks": checks}


def validate_capture_archive(archive_path: Path, expected_path: Path, observed_path: Path,
                             schema_path: Path, arm_roots: dict[str, Path]) -> dict[str, Any]:
    """Verify every canonical archive input and the copied manifest/schema pins."""
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    if archive.get("format") != "CBSP_CAPTURE_ARCHIVE_v1":
        raise StatePathError("unsupported capture archive manifest format")
    base = archive_path.parent

    def resolve_archive_path(raw: str) -> Path:
        path = Path(raw)
        if path.is_absolute():
            return path
        candidates = (base / path, base.parent / path, REPO / path, Path.cwd() / path)
        return next((candidate for candidate in candidates if candidate.exists()), candidates[0])

    def stable_path(path: Path) -> str:
        try:
            return path.resolve().relative_to(REPO.resolve()).as_posix()
        except ValueError:
            return path.name

    pinned = (("expected_manifest", expected_path), ("observed_manifest", observed_path), ("state_schema", schema_path))
    pins = {}
    for key, local_path in pinned:
        item = archive.get(key, {})
        path = resolve_archive_path(str(item.get("archive_path", "")))
        if path.resolve() != local_path.resolve() or not path.is_file() or sha256(path) != item.get("sha256"):
            raise StatePathError(f"capture archive {key} path or SHA-256 mismatch")
        pins[key] = {"path": stable_path(path), "sha256": item["sha256"]}
    records = archive.get("files")
    if not isinstance(records, list) or not records:
        raise StatePathError("capture archive manifest has no file records")
    seen: set[str] = set()
    resolved_records: dict[str, Path] = {}
    for record in records:
        rel = str(record.get("archive_path", ""))
        path = resolve_archive_path(rel)
        if not rel or rel in seen or not path.is_file():
            raise StatePathError(f"capture archive has duplicate, empty, or missing file record {rel!r}")
        seen.add(rel)
        if path.stat().st_size != record.get("archive_bytes") or sha256(path) != record.get("archive_sha256"):
            raise StatePathError(f"capture archive bytes/SHA-256 mismatch: {rel}")
        raw_sha = str(record.get("raw_sha256", ""))
        raw_bytes = record.get("raw_bytes")
        if not re.fullmatch(r"[0-9a-f]{64}", raw_sha) or not isinstance(raw_bytes, int) or raw_bytes < 0:
            raise StatePathError(f"capture archive raw input binding is malformed: {rel}")
        if record.get("content_type") == "CBSP0001":
            compression = record.get("compression", {})
            if not path.name.endswith(".bin.gz") or compression != {"format": "gzip", "level": 9, "mtime": 0}:
                raise StatePathError(f"capture archive gzip contract differs for {rel}")
            raw_digest, raw_size = hashlib.sha256(), 0
            with gzip.open(path, "rb") as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    raw_digest.update(chunk)
                    raw_size += len(chunk)
            if raw_size != raw_bytes or raw_digest.hexdigest() != raw_sha:
                raise StatePathError(f"capture archive decompressed bytes/SHA-256 mismatch: {rel}")
        elif path.name.startswith("state_calls_rank"):
            if record.get("content_type") != "CALL_INVENTORY" or record.get("compression", {}).get("format") != "none":
                raise StatePathError(f"capture archive call inventory content type differs for {rel}")
        elif path.name == "launch_receipt.json":
            if record.get("content_type") != "LAUNCH_RECEIPT" or record.get("compression", {}).get("format") != "none":
                raise StatePathError(f"capture archive launch receipt content type differs for {rel}")
        elif record.get("content_type") == "KDM6_TRACE_TEXT_CHUNK":
            if record.get("compression", {}).get("format") != "gzip" or record.get("compression", {}).get("mtime") != 0:
                raise StatePathError(f"capture archive trace compression differs for {rel}")
            raw_digest, raw_size = hashlib.sha256(), 0
            with gzip.open(path, "rb") as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    raw_digest.update(chunk)
                    raw_size += len(chunk)
            if raw_size != raw_bytes or raw_digest.hexdigest() != raw_sha:
                raise StatePathError(f"capture archive decompressed trace bytes/SHA-256 mismatch: {rel}")
        elif record.get("content_type") in (ARCHIVE_SIDECAR_TYPES | {"EXPECTED_RANK_MANIFEST", "OBSERVED_RANK_MANIFEST",
                                                                       "STATE_SCHEMA", "CALL_INVENTORY", "LAUNCH_RECEIPT"}):
            if record.get("compression", {}).get("format") != "none":
                raise StatePathError(f"capture archive sidecar compression differs for {rel}")
        else:
            raise StatePathError(f"capture archive contains unexpected arm file type: {rel}")
        if record.get("compression", {}).get("format") == "none" and (raw_sha != sha256(path) or raw_bytes != path.stat().st_size):
            raise StatePathError(f"capture archive uncompressed raw binding differs: {rel}")
        resolved_records[rel] = path.resolve()
    for arm, root in arm_roots.items():
        actual = {path.resolve() for path in root.iterdir() if path.is_file()}
        recorded = {resolved_records[record["archive_path"]] for record in records
                    if record.get("arm") == arm and resolved_records[record["archive_path"]].parent == root.resolve()}
        if actual != recorded:
            raise StatePathError(f"{arm}: archived arm file inventory differs; missing={sorted(recorded-actual)[:5]}, unbound={sorted(actual-recorded)[:5]}")
    provenance = [{"arm": record.get("arm"), "archive_path": stable_path(resolved_records[record["archive_path"]]),
                  "content_type": record.get("content_type"), "raw_sha256": record["raw_sha256"],
                  "raw_bytes": record["raw_bytes"], "archive_sha256": record["archive_sha256"],
                  "archive_bytes": record["archive_bytes"], "compression": record.get("compression")}
                 for record in records]
    return {"path": stable_path(archive_path), "sha256": sha256(archive_path), "format": archive["format"],
            "verified_file_count": len(records), "pins": pins, "files": provenance}


def _calls_equal(old: dict[tuple[int, int, int], Call], fix: dict[tuple[int, int, int], Call]) -> None:
    if old.keys() != fix.keys():
        missing = sorted(old.keys() - fix.keys())[:5]
        extra = sorted(fix.keys() - old.keys())[:5]
        raise StatePathError(f"OLD/FIX call keys differ; FIX missing={missing}, extra={extra}")
    for key in sorted(old):
        if old[key] != fix[key]:
            raise StatePathError(f"OLD/FIX call bounds/metadata differ for {key}")


def load_selected_cells(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise StatePathError(f"empty selected corner file: {path}")
    grouped: dict[str, list[dict[str, Any]]] = {}
    keys: set[tuple[int, int]] = set()
    corners = {"00", "10", "01", "11"}
    for row in rows:
        try:
            row["i"] = int(row["wrf_i_1based"])
            row["j"] = int(row["wrf_j_1based"])
            if int(row["native_i_zero_based"]) + 1 != row["i"] or int(row["native_j_zero_based"]) + 1 != row["j"]:
                raise ValueError("zero-based and one-based native cell coordinates disagree")
            row["weight"] = float(row["weight"])
            row["k_start"] = 1
        except (KeyError, ValueError) as exc:
            raise StatePathError(f"invalid selected point corner row: {row}") from exc
        cell = (row["j"], row["i"])
        if cell in keys:
            raise StatePathError(f"duplicate selected global cell: {cell}")
        keys.add(cell)
        if row["i"] < 1 or row["j"] < 1 or not math.isfinite(row["weight"]):
            raise StatePathError(f"invalid selected cell coordinate/weight: {row}")
        grouped.setdefault(row["point_id"], []).append(row)
    expected_ids = [f"P{i:02d}" for i in range(1, 5)] + [f"FA{i:02d}" for i in range(1, 5)]
    if list(grouped) != expected_ids:
        raise StatePathError(f"selected point order/IDs mismatch: expected {expected_ids}, got {list(grouped)}")
    for point_id, group in grouped.items():
        if len(group) != 4 or {row["corner"] for row in group} != corners:
            raise StatePathError(f"{point_id}: must contain exactly corners 00, 10, 01, 11")
        if abs(sum(row["weight"] for row in group) - 1.0) > 1e-12:
            raise StatePathError(f"{point_id}: bilinear corner weights do not sum to one")
    if len(keys) != 32:
        raise StatePathError(f"expected 32 unique native selected cells, got {len(keys)}")
    return expected_ids, rows


def _core_bounds(call: Call) -> tuple[int, int, int, int, int, int]:
    bounds = call.core
    if bounds[0] > bounds[1] or bounds[2] > bounds[3] or bounds[4] > bounds[5]:
        return bounds[0], bounds[0] - 1, bounds[2], bounds[2] - 1, bounds[4], bounds[5]
    return bounds


def expected_blocks(spec: StageSpec, calls: dict[tuple[int, int, int], Call], selected_cells: list[dict[str, Any]]) -> dict[tuple[int, int, int, int | None], ExpectedBlock]:
    result = {}
    selected_by_cell: dict[tuple[int, int], int] = {}
    for row in selected_cells:
        selected_by_cell[(row["i"], row["j"])] = selected_by_cell.get((row["i"], row["j"]), 0) + 1
    for call in calls.values():
        if spec.stage_id in GLOBAL_STAGES and call.timestep != 1:
            continue
        if spec.stage_id in SELECTED_STAGES:
            ilo, ihi, jlo, jhi, klo, khi = _core_bounds(call)
            cells = sum(1 for (i, j) in selected_by_cell if ilo <= i <= ihi and jlo <= j <= jhi)
            count = cells * max(0, khi - klo + 1)
            item = ExpectedBlock(call, spec.stage_id, None, (ilo, ihi, jlo, jhi, klo, khi), count)
            if item.key in result:
                raise StatePathError(f"duplicate expected selected block {item.key}")
            result[item.key] = item
        elif spec.stage_id in {1, 5}:
            bounds = _core_bounds(call)
            ni = max(0, bounds[1] - bounds[0] + 1)
            nj = max(0, bounds[3] - bounds[2] + 1)
            nk = max(0, bounds[5] - bounds[4] + 1)
            item = ExpectedBlock(call, spec.stage_id, None, bounds, ni * nj * nk)
            if item.key in result:
                raise StatePathError(f"duplicate expected global block {item.key}")
            result[item.key] = item
        else:
            for j in range(call.jts, call.jte + 1):
                bounds = (call.its, call.ite, j, j, call.kts, call.kte)
                records = max(0, call.ite - call.its + 1) * max(0, call.kte - call.kts + 1)
                item = ExpectedBlock(call, spec.stage_id, j, bounds, records)
                if item.key in result:
                    raise StatePathError(f"duplicate expected private block {item.key}")
                result[item.key] = item
    return result


def _expected_owner_key(header: BlockHeader, stage_id: int) -> tuple[int, int, int, int | None]:
    private_j = header.jlo if stage_id in {2, 3, 4} else None
    return header.timestep, header.rank, header.call_id, private_j


def _header_matches(header: BlockHeader, expected: ExpectedBlock, spec: StageSpec, path: Path) -> None:
    call = expected.call
    if header.stage_id != spec.stage_id or header.rank != call.rank or header.call_id != call.call_id or header.timestep != call.timestep:
        raise StatePathError(f"{path}: block identity does not match call inventory")
    if header.field_count != len(spec.fields):
        raise StatePathError(f"{path}: field_count {header.field_count} != expected {len(spec.fields)} for {spec.name}")
    if (header.ilo, header.ihi, header.jlo, header.jhi, header.klo, header.khi) != expected.bounds:
        raise StatePathError(f"{path}: bounds differ from call inventory for {spec.name}: got {(header.ilo,header.ihi,header.jlo,header.jhi,header.klo,header.khi)}, expected {expected.bounds}")
    if (header.istride, header.jstride, header.kstride) != (1, 1, 1):
        raise StatePathError(f"{path}: all CBSP0001 strides must be one")
    if header.record_count != expected.records:
        raise StatePathError(f"{path}: record_count {header.record_count} != expected {expected.records}")


def _block_paths(root: Path, spec: StageSpec) -> list[tuple[int, Path]]:
    paths = []
    seen_ranks = set()
    for path in sorted(root.glob(f"state_{spec.name}_rank*.bin*")):
        match = BLOCK_FILE_RE.fullmatch(path.name)
        if not match or match.group(1) != spec.name:
            raise StatePathError(f"invalid CBSP binary filename: {path.name}")
        rank = int(match.group(2))
        if rank in seen_ranks:
            raise StatePathError(f"{root}: duplicate plain/gzip files for stage {spec.name}, rank {rank}")
        seen_ranks.add(rank)
        paths.append((rank, path))
    return paths


def validate_runtime_filenames(root: Path) -> None:
    seen = set()
    for path in root.glob("state_*.bin*"):
        match = BLOCK_FILE_RE.fullmatch(path.name)
        if not match or match.group(1) not in STAGE_NAMES.values():
            raise StatePathError(f"{root}: unrecognized CBSP binary filename {path.name}")
        key = (match.group(1), int(match.group(2)))
        if key in seen:
            raise StatePathError(f"{root}: duplicate plain/gzip files for stage/rank {key}")
        seen.add(key)
    for path in root.glob("state_calls_*"):
        if not CALL_FILE_RE.fullmatch(path.name):
            raise StatePathError(f"{root}: unrecognized call inventory filename {path.name}")


def _linear_index(i: np.ndarray, j: np.ndarray, k: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    nj, ni, nk = shape
    if ((i < 1) | (i > ni) | (j < 1) | (j > nj) | (k < 1) | (k > nk)).any():
        raise StatePathError("CBSP row key lies outside declared history shape")
    return ((j - 1) * nk + (k - 1)) * ni + (i - 1)


def _owner_token(rank: int, call_id: int) -> np.int64:
    return np.int64((int(rank) << 32) | int(call_id))


def _owner_counts(owners: np.ndarray) -> dict[str, int]:
    tokens, counts = np.unique(owners[owners >= 0], return_counts=True)
    return {f"rank{int(token) >> 32}_call{int(token) & 0xffffffff}": int(count)
            for token, count in zip(tokens, counts)}


def _coords_for_range(start: int, count: int, bounds: tuple[int, int, int, int, int, int], shape: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ilo, ihi, jlo, jhi, klo, khi = bounds
    ni, nk = ihi - ilo + 1, khi - klo + 1
    local = np.arange(start, start + count, dtype=np.int64)
    i = ilo + local % ni
    k = klo + (local // ni) % nk
    j = jlo + local // (ni * nk)
    return i, j, k


def _values_finite(values: np.ndarray, path: Path, offset: int) -> None:
    bad = np.argwhere(~np.isfinite(values))
    if bad.size:
        row, field = map(int, bad[0])
        raise StatePathError(f"{path}: non-finite physical field at byte {offset}, row {row}, field-column {field}")


def _open_binary(path: Path):
    return gzip.open(path, "rb") if path.name.endswith(".gz") else path.open("rb")


def _assert_expected_inventory(actual: set[tuple[int, int, int, int | None]], expected: dict[tuple[int, int, int, int | None], ExpectedBlock], spec: StageSpec, root: Path) -> None:
    if actual != set(expected):
        missing = sorted(set(expected) - actual)[:5]
        extra = sorted(actual - set(expected))[:5]
        raise StatePathError(f"{root}: {spec.name} block inventory mismatch; missing={missing}, unexpected={extra}")


def read_global_stage(root: Path, spec: StageSpec, calls: dict[tuple[int, int, int], Call], selected_cells: list[dict[str, Any]], shape: tuple[int, int, int], work: Path) -> tuple[np.memmap, np.ndarray, np.ndarray, dict[str, Any]]:
    nj, ni, nk = shape
    cell_count = nj * ni * nk
    expected = expected_blocks(spec, calls, selected_cells)
    fields = len(spec.fields)
    work.mkdir(parents=True, exist_ok=True)
    values = np.memmap(work / f"{spec.name}.dat", dtype=FLOAT32, mode="w+", shape=(fields, cell_count))
    values[:] = np.nan  # uncalled cells remain explicitly unobserved
    occupied = np.zeros(cell_count, dtype=np.bool_)
    owners = np.full(cell_count, -1, dtype=np.int64)
    actual: set[tuple[int, int, int, int | None]] = set()
    block_count = 0
    for file_rank, path in _block_paths(root, spec):
        if file_rank < 0:
            raise StatePathError(f"negative rank in filename {path.name}")
        with _open_binary(path) as stream:
            while True:
                offset = stream.tell()
                raw = stream.read(HEADER_BYTES)
                if not raw:
                    break
                header = BlockHeader.unpack(raw, path, offset)
                if header.rank != file_rank:
                    raise StatePathError(f"{path}: header rank {header.rank} differs from filename rank {file_rank}")
                key = _expected_owner_key(header, spec.stage_id)
                item = expected.get(key)
                if item is None:
                    raise StatePathError(f"{path}: unexpected {spec.name} block key {key}")
                if key in actual:
                    raise StatePathError(f"{path}: duplicate {spec.name} block key {key}")
                _header_matches(header, item, spec, path)
                actual.add(key)
                block_count += 1
                ni_block = header.ihi - header.ilo + 1
                nj_block = header.jhi - header.jlo + 1
                nk_block = header.khi - header.klo + 1
                total_records = header.record_count
                rows_per_chunk = max(1, min(65536, total_records))
                row_offset = 0
                while row_offset < total_records:
                    nrows = min(rows_per_chunk, total_records - row_offset)
                    nbytes = nrows * fields * 4
                    payload = stream.read(nbytes)
                    if len(payload) != nbytes:
                        raise StatePathError(f"{path}: truncated {spec.name} payload at byte {stream.tell()}")
                    block_values = np.frombuffer(payload, dtype=FLOAT32).reshape(nrows, fields)
                    _values_finite(block_values, path, stream.tell() - nbytes)
                    i, j, k = _coords_for_range(row_offset, nrows, item.bounds, shape)
                    indices = _linear_index(i, j, k, shape)
                    if occupied[indices].any():
                        raise StatePathError(f"{path}: duplicate owner cell in {spec.name} at global key {(int(i[0]),int(j[0]),int(k[0]))}")
                    occupied[indices] = True
                    owners[indices] = _owner_token(header.rank, header.call_id)
                    values[:, indices] = block_values.T
                    row_offset += nrows
                if total_records == 0 and spec.stage_id in {2, 3, 4}:
                    # Empty private columns are only legal when their tile extent is empty.
                    if ni_block > 0 and nk_block > 0:
                        raise StatePathError(f"{path}: unexpected empty private column block")
    _assert_expected_inventory(actual, expected, spec, root)
    if np.any(owners[occupied] < 0):
        raise StatePathError(f"{root}: owner map has an unowned observed cell")
    if np.any(occupied & ~np.isfinite(values[0])):
        raise StatePathError(f"{root}: observed mask includes unwritten data")
    values.flush()
    return values, occupied, owners, {"blocks": block_count, "observed_cells": int(occupied.sum()), "field_count": fields,
                                      "owner_cells_by_rank_call": _owner_counts(owners)}


def read_selected_stage(root: Path, spec: StageSpec, calls: dict[tuple[int, int, int], Call], selected_cells: list[dict[str, Any]], shape: tuple[int, int, int], work: Path) -> tuple[np.memmap, np.ndarray, dict[str, Any]]:
    timesteps = 360
    levels = shape[2]
    cell_keys = sorted({(int(row["i"]), int(row["j"])) for row in selected_cells}, key=lambda cell: (cell[1], cell[0]))
    cell_index = {cell: index for index, cell in enumerate(cell_keys)}
    fields = len(spec.fields)
    work.mkdir(parents=True, exist_ok=True)
    values = np.memmap(work / f"{spec.name}.dat", dtype=FLOAT32, mode="w+", shape=(timesteps, levels, len(cell_keys), fields))
    values[:] = np.nan
    occupied = np.zeros((timesteps, levels, len(cell_keys)), dtype=np.bool_)
    owners = np.full((timesteps, levels, len(cell_keys)), -1, dtype=np.int64)
    expected = expected_blocks(spec, calls, selected_cells)
    actual: set[tuple[int, int, int, int | None]] = set()
    record_dtype = np.dtype([("i", ">i4"), ("j", ">i4"), ("k", ">i4"), ("values", ">f4", (fields,))])
    block_count = 0
    for file_rank, path in _block_paths(root, spec):
        with _open_binary(path) as stream:
            while True:
                offset = stream.tell()
                raw = stream.read(HEADER_BYTES)
                if not raw:
                    break
                header = BlockHeader.unpack(raw, path, offset)
                if header.rank != file_rank:
                    raise StatePathError(f"{path}: header rank differs from filename")
                key = _expected_owner_key(header, spec.stage_id)
                item = expected.get(key)
                if item is None:
                    raise StatePathError(f"{path}: unexpected {spec.name} block key {key}")
                if key in actual:
                    raise StatePathError(f"{path}: duplicate {spec.name} block key {key}")
                _header_matches(header, item, spec, path)
                actual.add(key)
                block_count += 1
                remaining = header.record_count
                while remaining:
                    count = min(32768, remaining)
                    nbytes = count * record_dtype.itemsize
                    payload = stream.read(nbytes)
                    if len(payload) != nbytes:
                        raise StatePathError(f"{path}: truncated selected payload at byte {stream.tell()}")
                    records = np.frombuffer(payload, dtype=record_dtype)
                    vals = records["values"]
                    _values_finite(vals, path, stream.tell() - nbytes)
                    ii, jj, kk = records["i"], records["j"], records["k"]
                    bounds = item.bounds
                    if ((ii < bounds[0]) | (ii > bounds[1]) | (jj < bounds[2]) | (jj > bounds[3]) |
                        (kk < bounds[4]) | (kk > bounds[5])).any():
                        raise StatePathError(f"{path}: selected row lies outside its owning call bounds")
                    _linear_index(ii, jj, kk, shape)
                    try:
                        ci = np.fromiter((cell_index[(int(i), int(j))] for i, j in zip(ii, jj)), dtype=np.int64, count=count)
                    except KeyError as exc:
                        raise StatePathError(f"{path}: selected key absent from frozen 32-cell cohort: {exc.args[0]}") from exc
                    composite = (kk.astype(np.int64) - 1) * len(cell_keys) + ci
                    if np.unique(composite).size != composite.size:
                        raise StatePathError(f"{path}: duplicate selected row within payload chunk at timestep {header.timestep}")
                    ti = header.timestep - 1
                    ki = kk - 1
                    if (occupied[ti, ki, ci]).any():
                        raise StatePathError(f"{path}: duplicate selected row at timestep {header.timestep}")
                    occupied[ti, ki, ci] = True
                    owners[ti, ki, ci] = _owner_token(header.rank, header.call_id)
                    values[ti, ki, ci, :] = vals
                    remaining -= count
    _assert_expected_inventory(actual, expected, spec, root)
    if not occupied.all():
        missing = np.argwhere(~occupied)[0]
        raise StatePathError(f"{root}: selected {spec.name} has missing cell/timestep/level {tuple(map(int, missing))}")
    values.flush()
    return values, occupied, {"blocks": block_count, "selected_rows": int(occupied.sum()), "field_count": fields,
                              "selected_cells": len(cell_keys), "timesteps": timesteps, "levels": levels,
                              "owner_cells_by_rank_call": _owner_counts(owners)}


def _float_word(value: np.float32) -> str:
    return "0x%08x" % int(np.asarray(value, dtype=FLOAT32).view(WORD32))


def compare_global(old: np.memmap, fix: np.memmap, mask_old: np.ndarray, mask_fix: np.ndarray,
                   spec: StageSpec, shape: tuple[int, int, int]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not np.array_equal(mask_old, mask_fix):
        raise StatePathError(f"OLD/FIX observed call masks differ for stage {spec.name}")
    indices = np.flatnonzero(mask_old)
    nj, ni, nk = shape
    rows, divergences, numeric_divergences = [], [], []
    for f, field in enumerate(spec.fields):
        bit_equal = numeric_equal = 0
        max_abs = max_rel = max_over_ulp = 0.0
        min_delta = math.inf
        max_delta = -math.inf
        rel_count = 0
        nonzero_old = 0
        nan_count = inf_count = 0
        first = first_numeric = None
        # Iterate in deterministic k,j,i key order, independent of MPI block write order.
        for k in range(1, nk + 1):
            plane = np.array([((j - 1) * nk + (k - 1)) * ni + i for j in range(1, nj + 1) for i in range(ni)], dtype=np.int64)
            selected = plane[mask_old[plane]]
            if not selected.size:
                continue
            a = np.asarray(old[f, selected], dtype=np.float32)
            b = np.asarray(fix[f, selected], dtype=np.float32)
            finite = np.isfinite(a) & np.isfinite(b)
            nan_count += int(np.count_nonzero(np.isnan(a) | np.isnan(b)))
            inf_count += int(np.count_nonzero(np.isinf(a) | np.isinf(b)))
            if not finite.all():
                raise StatePathError(f"non-finite state encountered during comparison at {spec.name}.{field}")
            a_bits, b_bits = a.view(np.uint32), b.view(np.uint32)
            bit_same = a_bits == b_bits
            num_same = a == b
            bit_equal += int(bit_same.sum())
            numeric_equal += int(num_same.sum())
            diff_mask = ~bit_same
            if diff_mask.any() and first is None:
                n = int(np.flatnonzero(diff_mask)[0])
                linear = int(selected[n])
                j1 = linear // (ni * nk) + 1
                rem = linear % (ni * nk)
                k1 = rem // ni + 1
                i1 = rem % ni + 1
                first = {"k": k1, "j": j1, "i": i1, "old": float(a[n]), "fix": float(b[n]),
                         "old_word": _float_word(a[n]), "fix_word": _float_word(b[n]),
                         "numeric_equal": bool(num_same[n]), "signed_zero_only": bool(num_same[n] and a[n] == 0.0)}
            numeric_diff_mask = ~num_same
            if numeric_diff_mask.any() and first_numeric is None:
                n = int(np.flatnonzero(numeric_diff_mask)[0])
                linear = int(selected[n])
                j1 = linear // (ni * nk) + 1
                rem = linear % (ni * nk)
                k1 = rem // ni + 1
                i1 = rem % ni + 1
                first_numeric = {"k": k1, "j": j1, "i": i1, "old": float(a[n]), "fix": float(b[n]),
                                 "old_word": _float_word(a[n]), "fix_word": _float_word(b[n]),
                                 "numeric_equal": False, "signed_zero_only": False}
            delta = b.astype(np.float64) - a.astype(np.float64)
            if delta.size:
                min_delta = min(min_delta, float(delta.min()))
                max_delta = max(max_delta, float(delta.max()))
                max_abs = max(max_abs, float(np.max(np.abs(delta))))
                abs_old = np.abs(a.astype(np.float64))
                nonzero = abs_old > 0.0
                nonzero_old += int(nonzero.sum())
                if nonzero.any():
                    max_rel = max(max_rel, float(np.max(np.abs(delta[nonzero]) / abs_old[nonzero])))
                    rel_count += int(nonzero.sum())
                ulp = np.abs(np.spacing(a))
                good = ulp > 0.0
                if good.any():
                    max_over_ulp = max(max_over_ulp, float(np.max(np.abs(delta[good]) / ulp[good])))
        n = int(indices.size)
        row = {"stage_id": spec.stage_id, "stage": spec.name, "timestep": 1, "field_index": f,
               "field": field, "observed_cells": n, "bitwise_equal": bit_equal,
               "bitwise_different": n - bit_equal, "numeric_equal": numeric_equal,
               "numeric_different": n - numeric_equal, "signed_zero_only": numeric_equal - bit_equal,
               "finite_values_per_arm": n, "nan_values": nan_count, "inf_values": inf_count,
               "max_abs_difference": max_abs, "max_relative_difference_old_nonzero": max_rel,
               "relative_denominator_cells": rel_count, "max_difference_over_float32_ulp_of_old_value": max_over_ulp,
               "min_signed_difference_fix_minus_old": min_delta if min_delta < math.inf else 0.0,
               "max_signed_difference_fix_minus_old": max_delta if max_delta > -math.inf else 0.0,
               "first_bitwise_difference_kji": json.dumps(first, sort_keys=True) if first else "",
               "first_numeric_difference_kji": json.dumps(first_numeric, sort_keys=True) if first_numeric else ""}
        rows.append(row)
        if first:
            divergences.append({"timestep": 1, "stage_id": spec.stage_id, "stage": spec.name,
                                "field_index": f, "field": field, **first})
        if first_numeric:
            numeric_divergences.append({"timestep": 1, "stage_id": spec.stage_id, "stage": spec.name,
                                        "field_index": f, "field": field, **first_numeric})
    earliest = min(divergences, key=lambda d: (d["timestep"], d["stage_id"], d["field_index"], d["k"], d["j"], d["i"])) if divergences else None
    earliest_numeric = min(numeric_divergences, key=lambda d: (d["timestep"], d["stage_id"], d["field_index"], d["k"], d["j"], d["i"])) if numeric_divergences else None
    return rows, {"earliest_global_difference": earliest, "earliest_global_bitwise_difference": earliest,
                  "earliest_global_numeric_difference": earliest_numeric,
                  "divergent_fields_bitwise": len(divergences), "divergent_fields_numeric": len(numeric_divergences),
                  "scope": "deterministic checkpoint/field/global-key order; MPI rank/call/write order is not a causal chronology"}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise StatePathError(f"refusing empty output table {path.name}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _update_aggregate(acc: dict[str, Any], diff: float, scale_value: float, ulp_scale: float,
                      time: int, k: int) -> None:
    if diff != 0.0 and acc["first"] is None:
        acc["first"] = {"timestep": time, "k": k, "difference": diff}
    if abs(diff) > acc["max_abs"]:
        acc["max_abs"] = abs(diff)
        acc["max_signed"] = diff
        acc["max_location"] = {"timestep": time, "k": k}
        acc["scale_value_at_max"] = scale_value
        acc["ulp_ratio_at_max"] = abs(diff) / ulp_scale if ulp_scale > 0 else None
    if scale_value != 0.0:
        acc["max_relative"] = max(acc["max_relative"], abs(diff) / abs(scale_value))


def selected_ledger(old_entry: np.memmap, old_return: np.memmap, fix_entry: np.memmap, fix_return: np.memmap,
                    cells: list[dict[str, Any]], fields: tuple[str, ...],
                    weighted_profiles: dict[str, np.ndarray] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    point_ids = list(dict.fromkeys(row["point_id"] for row in cells))
    if weighted_profiles is None:
        weighted_profiles = selected_weighted_profiles(old_entry, old_return, fix_entry, fix_return,
                                                       cells, point_ids, fields)
    accum = {(point_id, f, phase): {"first": None, "max_abs": 0.0, "max_signed": 0.0, "max_location": None,
                                    "scale_value_at_max": 0.0, "ulp_ratio_at_max": None, "max_relative": 0.0}
             for point_id in point_ids for f in range(len(fields)) for phase in ("incoming", "within", "between")}
    unit_roundoff = np.finfo(np.float64).eps / 2.0
    gamma8 = (8.0 * unit_roundoff) / (1.0 - 8.0 * unit_roundoff)
    residual_by_field = {field: {"max_abs_residual": 0.0, "max_gamma8_bound": 0.0,
                                 "max_residual_over_bound": 0.0, "bound_violation_count": 0,
                                 "worst_location": None} for field in fields}
    for t in range(360):
        for pi, point_id in enumerate(point_ids):
            for k0 in range(old_entry.shape[1]):
                for f, field in enumerate(fields):
                    old_e = float(weighted_profiles["old_entry_weighted"][t, k0, pi, f])
                    fix_e = float(weighted_profiles["fix_entry_weighted"][t, k0, pi, f])
                    old_r = float(weighted_profiles["old_return_weighted"][t, k0, pi, f])
                    fix_r = float(weighted_profiles["fix_return_weighted"][t, k0, pi, f])
                    incoming = float(weighted_profiles["D_entry"][t, k0, pi, f])
                    within = float(weighted_profiles["within_delta"][t, k0, pi, f])
                    return_diff = float(weighted_profiles["D_return"][t, k0, pi, f])
                    residual = return_diff - (incoming + within)
                    bound = gamma8 * (abs(old_e) + abs(fix_e) + abs(old_r) + abs(fix_r))
                    ratio = abs(residual) / bound if bound > 0.0 else (0.0 if residual == 0.0 else math.inf)
                    diag = residual_by_field[field]
                    diag["max_abs_residual"] = max(diag["max_abs_residual"], abs(residual))
                    diag["max_gamma8_bound"] = max(diag["max_gamma8_bound"], bound)
                    diag["bound_violation_count"] += int(abs(residual) > bound)
                    if ratio > diag["max_residual_over_bound"]:
                        diag["max_residual_over_bound"] = ratio
                        diag["worst_location"] = {"point_id": point_id, "timestep": t + 1, "k": k0 + 1,
                                                   "residual": residual, "gamma8_bound": bound}
                    ulp_e = float(abs(np.spacing(np.float32(old_e))))
                    location = (t + 1, k0 + 1)
                    _update_aggregate(accum[(point_id, f, "incoming")], incoming, old_e, ulp_e, *location)
                    _update_aggregate(accum[(point_id, f, "within")], within, old_e, ulp_e, *location)
                    if t < 359:
                        between = float(weighted_profiles["between_delta"][t, k0, pi, f])
                        _update_aggregate(accum[(point_id, f, "between")], between, old_r, float(abs(np.spacing(np.float32(old_r)))),
                                         t + 2, k0 + 1)
    rows = []
    for (point_id, f, phase), values in sorted(accum.items()):
        rows.append({"point_id": point_id, "field": fields[f], "ledger_component": phase,
                     "max_abs_difference": values["max_abs"], "max_signed_difference": values["max_signed"],
                     "max_relative_difference_old_nonzero": values["max_relative"],
                     "difference_over_float32_ulp_of_scale_baseline_at_max": values["ulp_ratio_at_max"],
                     "scale_baseline_value_at_max": values["scale_value_at_max"],
                     "max_profile_time_level": json.dumps(values["max_location"], sort_keys=True),
                     "first_nonzero_profile_time_level": json.dumps(values["first"], sort_keys=True) if values["first"] else ""})
    violations = sum(item["bound_violation_count"] for item in residual_by_field.values())
    return rows, {"max_abs_same_call_ledger_residual": max(item["max_abs_residual"] for item in residual_by_field.values()),
                  "same_call_residual_roundoff_model": "gamma8 bound on eight binary64 operations: gamma8*(|OLD_entry|+|FIX_entry|+|OLD_return|+|FIX_return|); zero scale requires zero residual",
                  "binary64_unit_roundoff": unit_roundoff, "gamma8": gamma8,
                  "same_call_residual_bound_violation_count": violations,
                  "same_call_residual_by_field": residual_by_field,
                  "ledger_identity": "D_return = D_entry + [(FIX_return-FIX_entry)-(OLD_return-OLD_entry)]",
                  "between_identity": "D_entry(t+1)-D_return(t); net between-call change from every non-KDM6 operation, not pure transport",
                  "aggregation": "four bilinear corners weighted per point; levels/timesteps are scanned without averaging or pooling points",
                  "ulp_scale": "incoming/within use ULP of OLD entry REAL32 state; between uses ULP of OLD return REAL32 state; relative differences use the same old state value as denominator"}


def selected_weighted_profiles(old_entry: np.ndarray, old_return: np.ndarray, fix_entry: np.ndarray, fix_return: np.ndarray,
                               cells: list[dict[str, Any]], point_ids: list[str], fields: tuple[str, ...]) -> dict[str, np.ndarray]:
    ordered_cells = sorted({(int(row["i"]), int(row["j"])) for row in cells}, key=lambda cell: (cell[1], cell[0]))
    cell_index = {cell: index for index, cell in enumerate(ordered_cells)}
    point_corners: dict[str, list[dict[str, Any]]] = {point_id: [] for point_id in point_ids}
    for row in cells:
        point_corners[row["point_id"]].append({**row, "cell_index": cell_index[(int(row["i"]), int(row["j"]))]})
    profile_shape = (360, old_entry.shape[1], len(point_ids), len(fields))
    profiles = {name: np.empty(profile_shape, dtype=np.float64) for name in
                ("old_entry_weighted", "old_return_weighted", "fix_entry_weighted", "fix_return_weighted")}
    for t in range(360):
        for k in range(old_entry.shape[1]):
            for pi, point_id in enumerate(point_ids):
                corners = point_corners[point_id]
                for f in range(len(fields)):
                    for output_name, data in (("old_entry_weighted", old_entry), ("old_return_weighted", old_return),
                                              ("fix_entry_weighted", fix_entry), ("fix_return_weighted", fix_return)):
                        profiles[output_name][t, k, pi, f] = math.fsum(
                            row["weight"] * float(data[t, k, row["cell_index"], f]) for row in corners)
    old_delta_entry = profiles["old_entry_weighted"]
    old_delta_return = profiles["old_return_weighted"]
    fix_delta_entry = profiles["fix_entry_weighted"]
    fix_delta_return = profiles["fix_return_weighted"]
    profiles["D_entry"] = fix_delta_entry - old_delta_entry
    profiles["D_return"] = fix_delta_return - old_delta_return
    profiles["within_delta"] = (fix_delta_return - fix_delta_entry) - (old_delta_return - old_delta_entry)
    profiles["between_delta"] = profiles["D_entry"][1:] - profiles["D_return"][:-1]
    profiles["between_time"] = np.arange(2, 361, dtype=np.int32)
    profiles["time"] = np.arange(1, 361, dtype=np.int32)
    profiles["point_ids"] = np.asarray(point_ids, dtype="U4")
    profiles["fields"] = np.asarray(fields, dtype="U64")
    profiles["cell_i"] = np.asarray([i for i, _ in ordered_cells], dtype=np.int32)
    profiles["cell_j"] = np.asarray([j for _, j in ordered_cells], dtype=np.int32)
    profiles["cell_point_id"] = np.asarray([next(row["point_id"] for row in cells if (int(row["i"]), int(row["j"])) == cell) for cell in ordered_cells], dtype="U4")
    profiles["cell_corner"] = np.asarray([next(row["corner"] for row in cells if (int(row["i"]), int(row["j"])) == cell) for cell in ordered_cells], dtype="U2")
    profiles["cell_weight"] = np.asarray([next(float(row["weight"]) for row in cells if (int(row["i"]), int(row["j"])) == cell) for cell in ordered_cells], dtype=np.float64)
    profiles["axis_order"] = np.asarray(["time", "k", "point_or_cell", "field"], dtype="U32")
    return profiles


def selected_point_first_differences(old_entry: np.ndarray, old_return: np.ndarray, fix_entry: np.ndarray, fix_return: np.ndarray,
                                     cells: list[dict[str, Any]], point_ids: list[str], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    ordered_cells = sorted({(int(row["i"]), int(row["j"])) for row in cells}, key=lambda cell: (cell[1], cell[0]))
    cell_index = {cell: index for index, cell in enumerate(ordered_cells)}
    grouped = {point_id: sorted([row for row in cells if row["point_id"] == point_id],
                               key=lambda row: (int(row["j"]), int(row["i"]))) for point_id in point_ids}
    results = []
    for point_id in point_ids:
        point_cells = grouped[point_id]
        for f, field in enumerate(fields):
            first_entry = first_return = first_entry_numeric = first_return_numeric = first_within = None
            for t in range(360):
                for k in range(old_entry.shape[1]):
                    for cell in point_cells:
                        ci = cell_index[(int(cell["i"]), int(cell["j"]))]
                        oe, fe = np.float32(old_entry[t, k, ci, f]), np.float32(fix_entry[t, k, ci, f])
                        if first_entry is None and int(oe.view(np.uint32)) != int(fe.view(np.uint32)):
                            first_entry = _raw_difference_record(point_id, cell, field, "selected_entry", t, k, oe, fe)
                        if first_entry_numeric is None and oe != fe:
                            first_entry_numeric = _raw_difference_record(point_id, cell, field, "selected_entry", t, k, oe, fe)
                        ore, fre = np.float32(old_return[t, k, ci, f]), np.float32(fix_return[t, k, ci, f])
                        if first_return is None and int(ore.view(np.uint32)) != int(fre.view(np.uint32)):
                            first_return = _raw_difference_record(point_id, cell, field, "selected_return", t, k, ore, fre)
                        if first_return_numeric is None and ore != fre:
                            first_return_numeric = _raw_difference_record(point_id, cell, field, "selected_return", t, k, ore, fre)
                        delta_old, delta_fix = float(ore) - float(oe), float(fre) - float(fe)
                        if first_within is None and delta_old != delta_fix:
                            first_within = {"timestep": t + 1, "k": k + 1, "j": int(cell["j"]), "i": int(cell["i"]),
                                            "corner": cell["corner"], "old_entry": float(oe), "old_entry_word": _float_word(oe),
                                            "old_return": float(ore), "old_return_word": _float_word(ore),
                                            "fix_entry": float(fe), "fix_entry_word": _float_word(fe),
                                            "fix_return": float(fre), "fix_return_word": _float_word(fre),
                                            "old_delta_f64": delta_old, "fix_delta_f64": delta_fix,
                                            "within_difference_f64": delta_fix - delta_old}
            results.append({"point_id": point_id, "field": field,
                            "incoming_differs_bitwise": first_entry is not None,
                            "return_differs_bitwise": first_return is not None,
                            "within_process_differs_numerically": first_within is not None,
                            "incoming_differs_numerically": first_entry_numeric is not None,
                            "return_differs_numerically": first_return_numeric is not None,
                            **_flatten_first("incoming", first_entry), **_flatten_first("incoming_numeric", first_entry_numeric),
                            **_flatten_first("return", first_return), **_flatten_first("return_numeric", first_return_numeric),
                            **_flatten_first("within", first_within)})
    return results


def _raw_difference_record(point_id: str, cell: dict[str, Any], field: str, stage: str, t: int,
                          k: int, old: np.float32, fix: np.float32) -> dict[str, Any]:
    return {"point_id": point_id, "field": field, "checkpoint": stage, "timestep": t + 1, "k": k + 1,
            "j": int(cell["j"]), "i": int(cell["i"]), "corner": cell["corner"], "old": float(old), "fix": float(fix),
            "old_word": _float_word(old), "fix_word": _float_word(fix), "numeric_equal": bool(old == fix),
            "signed_zero_only": bool(old == fix and old == 0.0), "difference_fix_minus_old": float(fix) - float(old)}


def _flatten_first(prefix: str, record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {f"{prefix}_{field}": "" for field in ("timestep", "k", "j", "i", "corner", "old", "fix", "old_word", "fix_word", "difference")}
    return {f"{prefix}_{field}": record.get(source, "") for field, source in
            (("timestep", "timestep"), ("k", "k"), ("j", "j"), ("i", "i"), ("corner", "corner"),
             ("old", "old" if prefix != "within" else "old_delta_f64"),
             ("fix", "fix" if prefix != "within" else "fix_delta_f64"),
             ("old_word", "old_word"), ("fix_word", "fix_word"),
             ("difference", "difference_fix_minus_old" if prefix != "within" else "within_difference_f64"))}


def _file_records(root: Path) -> list[dict[str, Any]]:
    paths = sorted(path for path in root.glob("state_*_rank*.bin*") if path.is_file()) + sorted(path for path in root.glob("state_calls_rank*.txt") if path.is_file())
    return [{"path": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size} for path in paths]


def _write_deterministic_npz(path: Path, **arrays: np.ndarray) -> None:
    """Write compressed NPY members with fixed ZIP metadata for replay stability."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, array in arrays.items():
            member = f"{name}.npy"
            info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info._compresslevel = 9
            info.external_attr = 0o600 << 16
            with tempfile.TemporaryFile() as payload:
                np.lib.format.write_array(payload, np.asarray(array), version=(2, 0), allow_pickle=False)
                payload.seek(0)
                with archive.open(info, "w") as target:
                    shutil.copyfileobj(payload, target, length=1 << 20)


def _global_ownership_arrays(mask_old: np.ndarray, mask_fix: np.ndarray, owners_old: np.ndarray,
                             owners_fix: np.ndarray, shape: tuple[int, int, int]) -> dict[str, np.ndarray]:
    nj, ni, nk = shape
    return {"called_old": mask_old.reshape(nj, nk, ni).transpose(0, 2, 1),
            "called_fix": mask_fix.reshape(nj, nk, ni).transpose(0, 2, 1),
            "owner_tokens_old": owners_old.reshape(nj, nk, ni).transpose(0, 2, 1),
            "owner_tokens_fix": owners_fix.reshape(nj, nk, ni).transpose(0, 2, 1),
            "history_shape_yxz": np.asarray(shape, dtype=np.int32),
            "axis_order": np.asarray("j,i,k", dtype="U8"),
            "owner_token_encoding": np.asarray("-1=uncalled; otherwise (rank<<32)|call_id", dtype="U48")}


def _write_selected_archives(directory: Path, selected_data: dict[tuple[str, int], np.ndarray],
                             profiles: dict[str, np.ndarray]) -> list[Path]:
    weighted_path = directory / "selected_history.npz"
    _write_deterministic_npz(weighted_path, **profiles)
    raw_metadata = {name: profiles[name] for name in
                    ("time", "point_ids", "fields", "cell_i", "cell_j", "cell_point_id", "cell_corner",
                     "cell_weight", "axis_order")}
    raw_metadata["axis_order"] = np.asarray(["time", "k", "cell", "field"], dtype="U32")
    raw_paths = []
    for arm in ("OLD", "FIX"):
        path = directory / f"selected_raw_{arm}.npz"
        raw_fields = {"entry": selected_data[arm, 6], "return": selected_data[arm, 7]}
        _write_deterministic_npz(path, **raw_fields, **raw_metadata)
        raw_paths.append(path)
    paths = [weighted_path, *raw_paths]
    oversized = [(path.name, path.stat().st_size) for path in paths if path.stat().st_size >= 100_000_000]
    if oversized:
        raise StatePathError(f"selected archive exceeds the 100,000,000-byte file cap: {oversized}")
    return paths


def _verify_selected_global_checkpoint(global_values: np.ndarray, selected_values: np.ndarray,
                                       cells: list[dict[str, Any]], shape: tuple[int, int, int],
                                       arm: str, selected_stage: str, global_stage: str) -> None:
    """Cross-bind selected t=1 rows to the matching full-grid state checkpoint."""
    nj, ni, nk = shape
    cell_keys = sorted({(int(row["i"]), int(row["j"])) for row in cells}, key=lambda cell: (cell[1], cell[0]))
    if global_values.ndim != 2 or selected_values.shape[1:] != (nk, len(cell_keys), global_values.shape[0]):
        raise StatePathError(f"{arm}: incompatible {selected_stage}/{global_stage} checkpoint shapes")
    sample = np.empty((nk, len(cell_keys), global_values.shape[0]), dtype=FLOAT32)
    for ci, (i, j) in enumerate(cell_keys):
        indices = np.asarray([((j - 1) * nk + k) * ni + (i - 1) for k in range(nk)], dtype=np.int64)
        sample[:, ci, :] = global_values[:, indices].T
    selected_first = np.asarray(selected_values[0], dtype=FLOAT32)
    mismatch = sample.view(np.uint32) != selected_first.view(np.uint32)
    if mismatch.any():
        k0, ci, field = map(int, np.argwhere(mismatch)[0])
        i, j = cell_keys[ci]
        raise StatePathError(f"{arm}: selected {selected_stage} differs bitwise from global {global_stage} at t=1, k={k0+1}, j={j}, i={i}, field={field}")


def analyze_pair(old_root: Path, fix_root: Path, schema_path: Path, corners_path: Path, output: Path,
                 expected_manifest_path: Path | None = None, observed_manifest_path: Path | None = None,
                 archive_manifest_path: Path | None = None) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise StatePathError(f"output path already exists (including dangling symlink): {output}")
    if not old_root.is_dir() or not fix_root.is_dir():
        raise StatePathError("OLD and FIX input roots must be directories")
    if expected_manifest_path is None or observed_manifest_path is None or archive_manifest_path is None:
        raise StatePathError("expected-ranks, observed-ranks, and capture-archive manifests are required")
    validate_frozen_source_pins(schema_path, corners_path)
    schema, specs = load_schema(schema_path)
    point_ids, selected_cells = load_selected_cells(corners_path)
    shape = tuple(int(value) for value in schema["coverage"]["history_shape_yxz"])
    if len(shape) != 3 or shape != (282, 234, 39):
        raise StatePathError(f"unexpected WRF history shape: {shape}")
    old_calls, fix_calls = read_call_inventory(old_root), read_call_inventory(fix_root)
    _calls_equal(old_calls, fix_calls)
    rank_validation = validate_rank_manifests(expected_manifest_path, observed_manifest_path,
                                              {"OLD": old_root, "FIX": fix_root})
    archive_validation = validate_capture_archive(archive_manifest_path, expected_manifest_path,
                                                  observed_manifest_path, schema_path,
                                                  {"OLD": old_root, "FIX": fix_root})
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    old_work, fix_work = temp / "old", temp / "fix"
    old_work.mkdir()
    fix_work.mkdir()
    stage_validation = {}
    ownership_outputs = []
    global_rows, global_bitwise_first, global_numeric_first = [], [], []
    selected_data: dict[tuple[str, int], np.memmap] = {}
    selected_masks: dict[tuple[str, int], np.ndarray] = {}
    try:
        validate_runtime_filenames(old_root)
        validate_runtime_filenames(fix_root)
        for stage_id in sorted(GLOBAL_STAGES):
            spec = specs[stage_id]
            old_values, old_mask, old_owners, old_info = read_global_stage(old_root, spec, old_calls, selected_cells, shape, old_work)
            fix_values, fix_mask, fix_owners, fix_info = read_global_stage(fix_root, spec, fix_calls, selected_cells, shape, fix_work)
            if not np.array_equal(old_mask, fix_mask):
                raise StatePathError(f"OLD/FIX observed mask differs at stage {spec.name}")
            if not np.array_equal(old_owners >= 0, fix_owners >= 0):
                raise StatePathError(f"OLD/FIX owner occupancy differs at stage {spec.name}")
            if not np.array_equal(old_owners, fix_owners):
                raise StatePathError(f"OLD/FIX cell owners differ at stage {spec.name}")
            ownership_path = temp / f"global_ownership_{spec.name}.npz"
            _write_deterministic_npz(ownership_path, **_global_ownership_arrays(
                old_mask, fix_mask, old_owners, fix_owners, shape))
            ownership_outputs.append(ownership_path)
            stats, first = compare_global(old_values, fix_values, old_mask, fix_mask, spec, shape)
            global_rows.extend(stats)
            if first["earliest_global_bitwise_difference"]:
                global_bitwise_first.append(first["earliest_global_bitwise_difference"])
            if first["earliest_global_numeric_difference"]:
                global_numeric_first.append(first["earliest_global_numeric_difference"])
            stage_validation[spec.name] = {"OLD": old_info, "FIX": fix_info, "mask_equal": True,
                                           "owner_cells": int(np.count_nonzero(old_owners >= 0))}
            del old_values, fix_values, old_owners, fix_owners
        for stage_id in (6, 7):
            spec = specs[stage_id]
            for label, root, calls in (("OLD", old_root, old_calls), ("FIX", fix_root, fix_calls)):
                data, mask, info = read_selected_stage(root, spec, calls, selected_cells, shape,
                                                       old_work if label == "OLD" else fix_work)
                selected_data[label, stage_id] = data
                selected_masks[label, stage_id] = mask
                stage_validation[spec.name] = stage_validation.get(spec.name, {})
                stage_validation[spec.name][label] = info
            old_mask_info = stage_validation[spec.name]["OLD"]
            fix_mask_info = stage_validation[spec.name]["FIX"]
            if not np.array_equal(selected_masks["OLD", stage_id], selected_masks["FIX", stage_id]):
                raise StatePathError(f"OLD/FIX selected row masks differ at stage {spec.name}")
        public_fields = specs[6].fields
        if specs[7].fields != public_fields or specs[1].fields != public_fields or specs[5].fields != public_fields:
            raise StatePathError("global entry/wrapper and selected entry/return public field order differs")
        for label, stage_data, work in (("OLD", selected_data, old_work), ("FIX", selected_data, fix_work)):
            for global_id, selected_id in ((1, 6), (5, 7)):
                spec = specs[global_id]
                full_grid = np.memmap(work / f"{spec.name}.dat", dtype=FLOAT32, mode="r",
                                       shape=(len(spec.fields), shape[0] * shape[1] * shape[2]))
                _verify_selected_global_checkpoint(full_grid, stage_data[label, selected_id], selected_cells,
                                                   shape, label, specs[selected_id].name, spec.name)
                del full_grid
                stage_validation[f"selected_{specs[selected_id].name}_matches_{spec.name}_t1"] = {
                    label: {"bitwise_equal": True, "selected_points": point_ids, "selected_cells": len(selected_cells),
                            "levels": shape[2], "fields": list(spec.fields)}}
        profiles = selected_weighted_profiles(selected_data["OLD", 6], selected_data["OLD", 7],
                                               selected_data["FIX", 6], selected_data["FIX", 7],
                                               selected_cells, point_ids, public_fields)
        ledger_rows, ledger_summary = selected_ledger(selected_data["OLD", 6], selected_data["OLD", 7],
                                                      selected_data["FIX", 6], selected_data["FIX", 7],
                                                      selected_cells, public_fields, profiles)
        if ledger_summary["same_call_residual_bound_violation_count"]:
            raise StatePathError("selected public same-call ledger exceeds its binary64 gamma8 roundoff bound")
        point_first_rows = selected_point_first_differences(selected_data["OLD", 6], selected_data["OLD", 7],
                                                             selected_data["FIX", 6], selected_data["FIX", 7],
                                                             selected_cells, point_ids, public_fields)
        selected_bitwise_divergences, selected_numeric_divergences = [], []
        selected_cells_order = sorted({(int(r["i"]), int(r["j"])) for r in selected_cells}, key=lambda cell: (cell[1], cell[0]))
        # Find one first bitwise and numeric difference per selected stage/field.
        for stage_id in (6, 7):
            spec = specs[stage_id]
            old_data, fix_data = selected_data["OLD", stage_id], selected_data["FIX", stage_id]
            order = sorted(range(len(selected_cells_order)), key=lambda n: (selected_cells_order[n][1], selected_cells_order[n][0]))
            for f, field in enumerate(spec.fields):
                found_bitwise = found_numeric = None
                for t in range(360):
                    for k0 in range(shape[2]):
                        for ci in order:
                            a = np.float32(old_data[t, k0, ci, f])
                            b = np.float32(fix_data[t, k0, ci, f])
                            if found_bitwise is None and int(a.view(np.uint32)) != int(b.view(np.uint32)):
                                i, j = selected_cells_order[ci]
                                found_bitwise = {"timestep": t + 1, "stage_id": stage_id, "stage": spec.name,
                                                 "field_index": f, "field": field, "k": k0 + 1, "j": j, "i": i,
                                                 "old": float(a), "fix": float(b), "old_word": _float_word(a),
                                                 "fix_word": _float_word(b), "numeric_equal": bool(a == b),
                                                 "signed_zero_only": bool(a == b and a == 0.0)}
                            if found_numeric is None and a != b:
                                i, j = selected_cells_order[ci]
                                found_numeric = {"timestep": t + 1, "stage_id": stage_id, "stage": spec.name,
                                                 "field_index": f, "field": field, "k": k0 + 1, "j": j, "i": i,
                                                 "old": float(a), "fix": float(b), "old_word": _float_word(a),
                                                 "fix_word": _float_word(b), "numeric_equal": False,
                                                 "signed_zero_only": False}
                            if found_bitwise and found_numeric:
                                break
                        if found_bitwise and found_numeric:
                            break
                    if found_bitwise and found_numeric:
                        break
                if found_bitwise:
                    selected_bitwise_divergences.append(found_bitwise)
                if found_numeric:
                    selected_numeric_divergences.append(found_numeric)
        key_order = lambda d: (d["timestep"], d["stage_id"], d["field_index"], d["k"], d["j"], d["i"])
        all_bitwise = global_bitwise_first + selected_bitwise_divergences
        all_numeric = global_numeric_first + selected_numeric_divergences
        earliest_bitwise = min(all_bitwise, key=key_order) if all_bitwise else None
        earliest_numeric = min(all_numeric, key=key_order) if all_numeric else None
        _write_csv(temp / "global_checkpoint_comparison.csv", global_rows)
        _write_csv(temp / "selected_ledger_summary.csv", ledger_rows)
        _write_csv(temp / "selected_point_first_differences.csv", point_first_rows)
        selected_archive_outputs = _write_selected_archives(temp, selected_data, profiles)
        (temp / "earliest_divergence.json").write_text(json.dumps({"earliest_deterministic_numeric_difference": earliest_numeric,
              "earliest_deterministic_bitwise_difference": earliest_bitwise,
              "global_snapshot_first_bitwise_difference_per_field_stage": global_bitwise_first,
              "global_snapshot_first_numeric_difference_per_field_stage": global_numeric_first,
              "selected_history_first_bitwise_difference_per_field_stage": selected_bitwise_divergences,
              "selected_history_first_numeric_difference_per_field_stage": selected_numeric_divergences,
              "interpretation_limit": "ordering is by model timestep, checkpoint stage ID, schema field order, then global k,j,i; MPI rank/call/write order is not a global causal chronology"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (temp / "ledger_summary.json").write_text(json.dumps(ledger_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        source_files = {"OLD": _file_records(old_root), "FIX": _file_records(fix_root)}
        receipt = {"status": "complete", "format": schema["format"], "endianness": "big", "integer_type": "int32", "float_type": "IEEE REAL32",
                   "schema_path": schema_path.name, "schema_sha256": sha256(schema_path),
                   "corners_path": corners_path.name, "corners_sha256": sha256(corners_path),
                   "selected_point_ids": point_ids, "selected_native_cells": len(selected_cells),
                   "history_shape_yxz": list(shape), "global_scope": "actual call inventory bounds only; uncalled cells retained as unobserved",
                   "global_stage_validation": stage_validation,
                   "inputs": {"OLD": {"files": source_files["OLD"]},
                              "FIX": {"files": source_files["FIX"]}},
                   "rank_manifest_validation": rank_validation,
                   "capture_archive_validation": archive_validation,
                   "outputs": [{"path": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size}
                               for path in [temp / "global_checkpoint_comparison.csv", *ownership_outputs,
                                            temp / "selected_ledger_summary.csv", temp / "selected_point_first_differences.csv",
                                            *selected_archive_outputs, temp / "earliest_divergence.json",
                                            temp / "ledger_summary.json"]],
                   "ledger": ledger_summary}
        (temp / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        # Close memmaps before moving the staging directory to its final path.
        for data in selected_data.values():
            data.flush()
        selected_data.clear()
        selected_masks.clear()
        for path in temp.rglob("*.dat"):
            path.unlink()
        if output.exists() or output.is_symlink():
            raise StatePathError(f"output path appeared during analysis: {output}")
        os.rename(temp, output)
        return receipt
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True, help="OLD runtime directory containing CBSP0001 files")
    parser.add_argument("--fix", type=Path, required=True, help="FIX runtime directory containing CBSP0001 files")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--corners", type=Path, default=DEFAULT_CORNERS)
    parser.add_argument("--expected-ranks", type=Path, required=True,
                        help="sealed CBSP_EXPECTED_RANKS_v1 manifest copied into the archive")
    parser.add_argument("--observed-ranks", type=Path, required=True,
                        help="sealed CBSP_OBSERVED_RANKS_v1 manifest copied into the archive")
    parser.add_argument("--archive-manifest", type=Path, required=True,
                        help="CBSP_CAPTURE_ARCHIVE_v1 manifest binding all repository inputs")
    parser.add_argument("--output", type=Path, required=True, help="new result directory; existing paths and symlinks are refused")
    args = parser.parse_args()
    receipt = analyze_pair(args.old, args.fix, args.schema, args.corners, args.output,
                           args.expected_ranks, args.observed_ranks, args.archive_manifest)
    print(json.dumps({"status": receipt["status"], "output": str(args.output),
                      "global_stages": sorted(receipt["global_stage_validation"]),
                      "selected_cells": receipt["selected_native_cells"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
