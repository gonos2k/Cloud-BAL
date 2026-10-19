#!/usr/bin/env python3
"""Source-bound per-column cold-process activity summary and area join."""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

TAG = "PR90_KDM6_COLD_COLUMN"
HEADER = ("# PR90_KDM6_COLD_COLUMN v1 step,lat,i,loops,cell_transactions; "
          "group-major NG,AUT,G; stage-major proposed,applied,deferred; "
          "each stage signed,half-L1; units kg m-2 per column (vertical sum); "
          "weight=DEN*DELZ; diagnostic request activity, not reaction throughput")
GROUPS = ("NG", "AUT", "G")
STAGES = ("proposed", "applied", "deferred")
METRICS = ("signed_kg_m2", "half_l1_kg_m2")
AREA_METRICS = ("signed_kg", "half_l1_kg")
SOURCE_SHA256 = "14c6145df549541fae2aab84e98ee480ba6ac8a7c769dd926a6d44f22451c35d"
LAUNCH_REQUEST_SHA256 = hashlib.sha256(
    b"export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE").hexdigest()

_NATIVE_SPEC = importlib.util.spec_from_file_location(
    "pr90_native_history", Path(__file__).with_name("pr87_native_history.py"))
native = importlib.util.module_from_spec(_NATIVE_SPEC)
assert _NATIVE_SPEC.loader is not None
_NATIVE_SPEC.loader.exec_module(native)


class ColumnSummaryError(ValueError):
    """Raised when source, summary, or area mapping violates its contract."""


def _replace_once(source: str, old: str, new: str, name: str) -> str:
    if source.count(old) != 1:
        raise ColumnSummaryError(f"KDM6 {name} anchor missing or ambiguous")
    return source.replace(old, new, 1)


def add_column_summary(source: str, expected_sha256: str = SOURCE_SHA256) -> str:
    """Add i-resolved accumulators beside the existing PR89 accumulator."""
    actual = hashlib.sha256(source.encode()).hexdigest()
    if actual != expected_sha256:
        raise ColumnSummaryError(f"unexpected KDM6 source hash: {actual}")
    if TAG in source:
        raise ColumnSummaryError("column summary instrumentation already present")

    anchor = "   real(kind=8) :: pr89_cold_water(2,3,3),pr89_cold_weight\n"
    addition = ("   integer :: pr90_cold_i,pr90_cold_unit,pr90_cold_ios\n"
                "   integer :: pr90_cold_transactions(its:ite)\n"
                "   real(kind=8) :: pr90_cold_water(2,3,3,its:ite)\n")
    source = _replace_once(source, anchor, anchor + addition, "declarations")
    anchor = "   pr89_cold_water=0.0d0\n"
    source = _replace_once(source, anchor, anchor +
                           "   pr90_cold_water=0.0d0\n   pr90_cold_transactions=0\n",
                           "initialization")
    anchor = "            pr89_cold_transactions=pr89_cold_transactions+1\n"
    source = _replace_once(source, anchor, anchor +
                           "            pr90_cold_transactions(i)=pr90_cold_transactions(i)+1\n",
                           "transaction count")
    anchor = ("                pr89_cold_water(2,pr89_cold_stage,pr89_cold_group)= &\n"
              "                     pr89_cold_water(2,pr89_cold_stage,pr89_cold_group)+ &\n"
              "                     pr89_cold_half_l1*pr89_cold_weight\n")
    column_metrics = ("                pr90_cold_water(1,pr89_cold_stage,pr89_cold_group,i)= &\n"
                      "                     pr90_cold_water(1,pr89_cold_stage,pr89_cold_group,i)+ &\n"
                      "                     pr89_cold_signed*pr89_cold_weight\n"
                      "                pr90_cold_water(2,pr89_cold_stage,pr89_cold_group,i)= &\n"
                      "                     pr90_cold_water(2,pr89_cold_stage,pr89_cold_group,i)+ &\n"
                      "                     pr89_cold_half_l1*pr89_cold_weight\n")
    source = _replace_once(source, anchor, anchor + column_metrics, "column accumulation")
    anchor = "   close(pr89_cold_unit,iostat=pr89_cold_ios)\n"
    writer = ("   open(newunit=pr90_cold_unit,file='pr90_kdm6_cold_column.raw', &\n"
              "        form='formatted',status='unknown',position='append',action='write', &\n"
              "        iostat=pr90_cold_ios)\n"
              "   if (pr90_cold_ios.ne.0) error stop 'PR90 cold column open failed'\n"
              "   write(pr90_cold_unit,'(a)',iostat=pr90_cold_ios) &\n"
              "        '# PR90_KDM6_COLD_COLUMN v1 step,lat,i,loops,cell_transactions; '// &\n"
              "        'group-major NG,AUT,G; stage-major proposed,applied,deferred; '// &\n"
              "        'each stage signed,half-L1; units kg m-2 per column (vertical sum); '// &\n"
              "        'weight=DEN*DELZ; diagnostic request activity, not reaction throughput'\n"
              "   if (pr90_cold_ios.ne.0) error stop 'PR90 cold column header failed'\n"
              "   write(pr90_cold_unit,'(a,4i10)',iostat=pr90_cold_ios) &\n"
              "        'PR90_KDM6_COLD_BLOCK',pr87_model_timestep,lat,its,ite\n"
              "   if (pr90_cold_ios.ne.0) error stop 'PR90 cold column block failed'\n"
              "   do pr90_cold_i=its,ite\n"
              "     write(pr90_cold_unit,'(a,5i10,1p,*(1x,e24.16))',iostat=pr90_cold_ios) &\n"
              "          'PR90_KDM6_COLD_COLUMN',pr87_model_timestep,lat,pr90_cold_i,loops, &\n"
              "          pr90_cold_transactions(pr90_cold_i),pr90_cold_water(:,:,:,pr90_cold_i)\n"
              "     if (pr90_cold_ios.ne.0) error stop 'PR90 cold column write failed'\n"
              "   enddo\n"
              "   close(pr90_cold_unit,iostat=pr90_cold_ios)\n"
              "   if (pr90_cold_ios.ne.0) error stop 'PR90 cold column close failed'\n")
    return _replace_once(source, anchor, anchor + writer, "column output")


def _read_lines(path: Path) -> list[str]:
    if path.is_symlink() or not path.is_file():
        raise ColumnSummaryError(f"summary is not a regular file: {path}")
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    try:
        with opener(path, "rt", encoding="utf-8") as stream:
            return list(stream)
    except (OSError, EOFError, UnicodeError) as exc:
        raise ColumnSummaryError(f"cannot read summary text: {path}") from exc


def parse_column_summary(path: Path) -> dict[str, Any]:
    headers, rows, keys, blocks = 0, [], set(), []
    active_block = None
    header_pending = False

    def finish_block(block: dict[str, Any] | None) -> None:
        if block is None:
            return
        expected = list(range(block["i_start"], block["i_end"] + 1))
        actual = [row["i"] for row in block["rows"]]
        if actual != expected:
            raise ColumnSummaryError("call block does not contain every active i exactly once")
        blocks.append(block)

    for line_no, line in enumerate(_read_lines(path), 1):
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "#":
            if line.strip() == HEADER:
                if header_pending:
                    raise ColumnSummaryError(f"line {line_no}: header is not followed by a call block")
                finish_block(active_block)
                headers += 1
                active_block = None
                header_pending = True
            continue
        if fields[0] == "PR90_KDM6_COLD_BLOCK":
            if not header_pending or active_block is not None:
                raise ColumnSummaryError(f"line {line_no}: call block is out of order")
            if len(fields) != 5:
                raise ColumnSummaryError(f"line {line_no}: malformed call block")
            try:
                step, lat, i_start, i_end = map(int, fields[1:])
            except ValueError as exc:
                raise ColumnSummaryError(f"line {line_no}: invalid call block") from exc
            if i_end < i_start:
                raise ColumnSummaryError(f"line {line_no}: invalid active i bounds")
            active_block = {"timestep": step, "lat": lat, "i_start": i_start,
                            "i_end": i_end, "rows": []}
            header_pending = False
            continue
        if fields[0] != TAG or len(fields) != 24:
            raise ColumnSummaryError(f"line {line_no}: malformed {TAG} record")
        if active_block is None or header_pending:
            raise ColumnSummaryError(f"line {line_no}: column row is outside a call block")
        try:
            step, lat, i, loops, transactions = map(int, fields[1:6])
            values = [float(x.replace("D", "E").replace("d", "e")) for x in fields[6:]]
        except ValueError as exc:
            raise ColumnSummaryError(f"line {line_no}: invalid numeric field") from exc
        if step < 0 or loops < 1 or transactions < 0 or not all(map(math.isfinite, values)):
            raise ColumnSummaryError(f"line {line_no}: invalid count or nonfinite value")
        key = step, lat, i
        if key in keys:
            raise ColumnSummaryError(f"line {line_no}: duplicate step/lat/i {key}")
        keys.add(key)
        if (step, lat) != (active_block["timestep"], active_block["lat"]):
            raise ColumnSummaryError(f"line {line_no}: row does not match its call block")
        groups, offset = {}, 0
        for group in GROUPS:
            groups[group] = {}
            for stage in STAGES:
                groups[group][stage] = dict(zip(METRICS, values[offset:offset + 2]))
                offset += 2
        row = {"timestep": step, "lat": lat, "i": i, "loops": loops,
               "cell_transactions": transactions, "groups": groups}
        rows.append(row)
        active_block["rows"].append(row)
    if header_pending:
        raise ColumnSummaryError("column summary ends before its call block")
    finish_block(active_block)
    if headers == 0 or headers != len(blocks):
        raise ColumnSummaryError("column summary has missing or incomplete call blocks")
    if not rows:
        raise ColumnSummaryError("column summary contains no column records")
    return {"status": "EVALUATED", "column_records": len(rows), "columns": rows,
            "blocks": blocks,
            "call_blocks": len(blocks),
            "weight_units": "kg m-2 per column (vertical sum); no grid-area/global kg"}


def _area_weight_columns(rows: list[dict[str, Any]], *, dx_m: float, dy_m: float,
                         mapfac_mx: np.ndarray, mapfac_my: np.ndarray,
                         nx: int, ny: int) -> dict[int, dict[str, Any]]:
    """Pure area arithmetic for already verified one-based i/j rows."""
    totals: dict[int, dict[str, Any]] = {}
    for row in rows:
        j, i = row["lat"] - 1, row["i"] - 1
        if not (0 <= j < ny and 0 <= i < nx):
            raise ColumnSummaryError("one-based stage i/j lies outside history grid")
        mx, my = float(mapfac_mx[j, i]), float(mapfac_my[j, i])
        if not math.isfinite(mx) or not math.isfinite(my) or mx <= 0 or my <= 0:
            raise ColumnSummaryError("native map factors must be finite and positive")
        area = dx_m * dy_m / (mx * my)
        step = row["timestep"]
        step_totals = totals.setdefault(step, {
            g: {s: {m: 0.0 for m in AREA_METRICS} for s in STAGES} for g in GROUPS})
        for group in GROUPS:
            for stage in STAGES:
                for source_metric, area_metric in zip(METRICS, AREA_METRICS):
                    step_totals[group][stage][area_metric] += (
                        row["groups"][group][stage][source_metric] * area)
    return totals


def _receipt_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ColumnSummaryError(f"cannot read receipt: {path}") from exc
    if not isinstance(value, dict):
        raise ColumnSummaryError(f"receipt is not an object: {path}")
    return value


def _sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ColumnSummaryError(f"evidence path is not a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_bound_output(receipt: dict[str, Any], path: Path) -> None:
    bindings = native._receipt_history_hashes(receipt)
    if bindings.get(path.name) != _sha256(path):
        raise ColumnSummaryError(f"run receipt does not bind output: {path}")


def _verify_execution_layout(receipt: dict[str, Any]) -> dict[str, Any]:
    layout = receipt.get("execution_layout")
    if (not isinstance(layout, dict) or layout.get("status") != "VERIFIED_SINGLE"
            or layout.get("single_execution_layout") is not True
            or (layout.get("domain_count"), layout.get("mpi_ranks"),
                layout.get("tiles_per_domain"), layout.get("threads")) != (1, 1, 1, 1)):
        raise ColumnSummaryError("area weighting requires VERIFIED_SINGLE receipt-bound execution layout")
    sources = layout.get("source_sha256")
    if not isinstance(sources, dict):
        raise ColumnSummaryError("verified execution layout lacks source hashes")
    namelist_sha = receipt.get("candidate_namelist_sha256")
    launch = receipt.get("launch_environment")
    if (not isinstance(namelist_sha, str) or sources.get("candidate_namelist") != namelist_sha
            or not isinstance(launch, dict) or launch.get("status") != "CONFIGURED_BY_RUNNER"
            or launch.get("OMP_NUM_THREADS") != "1" or launch.get("OMP_DYNAMIC") != "FALSE"
            or launch.get("launch_request_sha256") != LAUNCH_REQUEST_SHA256
            or sources.get("launch_request") != launch.get("launch_request_sha256")):
        raise ColumnSummaryError("execution layout source hashes do not match receipt-bound launch inputs")
    rsl_payload = sources.get("rsl_out_0000_payload")
    rsl_artifact = sources.get("rsl_out_0000_artifact")
    if not isinstance(rsl_payload, str) or not isinstance(rsl_artifact, str):
        raise ColumnSummaryError("execution layout lacks same-run RSL source hashes")
    generated = receipt.get("generated_files", [])
    plain_bound = any(row.get("path") == "rsl.out.0000"
                      and row.get("sha256") == rsl_payload == rsl_artifact
                      for row in generated if isinstance(row, dict))
    compressed_bound = any(row.get("sha256") == rsl_payload
                           and row.get("compressed_sha256") == rsl_artifact
                           and Path(row.get("compressed_path", "")).name == "rsl.out.0000.gz"
                           for row in receipt.get("compressed_outputs", [])
                           if isinstance(row, dict))
    if not (plain_bound or compressed_bound):
        raise ColumnSummaryError("execution layout RSL hashes are not bound to same-run output")
    return layout


def _verify_source_wrapper(source: str) -> None:
    normalized = re.sub(r"\s+", "", source.lower())
    if "doj=jts,jtedo" not in normalized:
        raise ColumnSummaryError("compiled KDM source lacks the supported wrapper j loop")
    call = normalized.find("callkdm62d(")
    if call < 0:
        raise ColumnSummaryError("compiled KDM source lacks wrapper call to KDM62D")
    call_text = normalized[call:call + 3000]
    if not re.search(r",j&?,itimestep", call_text) or "q(ims,kms,j)" not in normalized:
        raise ColumnSummaryError("compiled KDM wrapper does not bind lat to its j row")
    if "doi=its,ite" not in normalized or "ims,ime" not in normalized:
        raise ColumnSummaryError("compiled KDM source lacks explicit active and memory i bounds")


def _stage_record_bounds(path: Path) -> tuple[dict[str, int], dict[str, int], set[int]]:
    """Stream PR85 stage headers while seeking over field payloads."""
    import struct

    opener = gzip.open if path.suffix.lower() == ".gz" else open
    magic_fields = {b"PR85PLB1": 5, b"PR85QND2": 12, b"PR85QNB1": 12}
    state_bounds = None
    pbl_bounds = None
    state_steps: set[int] = set()
    first_labels: list[str] = []
    try:
        with opener(path, "rb") as stream:
            while magic := stream.read(8):
                if magic not in magic_fields:
                    raise ColumnSummaryError(f"unknown stage record magic: {magic!r}")
                label = stream.read(32)
                header = stream.read(60)
                if len(label) != 32 or len(header) != 60:
                    raise ColumnSummaryError("truncated stage record header")
                try:
                    label_text = label.decode("ascii").strip()
                except UnicodeDecodeError as exc:
                    raise ColumnSummaryError("stage label is not ASCII") from exc
                if (magic == b"PR85PLB1" and len(first_labels) == 0) or (
                        magic != b"PR85PLB1" and len(first_labels) == 1):
                    first_labels.append(label_text)
                (kind, timestep, _rk, ims, ime, jms, jme, kms, kme,
                 its, ite, jts, jte, kts, kte) = struct.unpack(">15i", header)
                expected_kind = 2 if magic == b"PR85PLB1" else 1
                if kind != expected_kind:
                    raise ColumnSummaryError("invalid stage record kind or bounds")
                bounds = {"ims": ims, "ime": ime, "jms": jms, "jme": jme,
                          "kms": kms, "kme": kme, "its": its, "ite": ite,
                          "jts": jts, "jte": jte, "kts": kts, "kte": kte}
                for start, end, memory_start, memory_end in (
                        ("its", "ite", "ims", "ime"), ("jts", "jte", "jms", "jme"),
                        ("kts", "kte", "kms", "kme")):
                    if (bounds[memory_start] > bounds[memory_end]
                            or bounds[start] > bounds[end]
                            or bounds[start] < bounds[memory_start]
                            or bounds[end] > bounds[memory_end]):
                        raise ColumnSummaryError(f"invalid active {start[0]} stage bounds")
                cells = (ite - its + 1) * (jte - jts + 1) * (kte - kts + 1)
                stream.seek(cells * 4 * magic_fields[magic], 1)
                if magic == b"PR85PLB1" and label_text == "POST_PBL_TEND" and pbl_bounds is None:
                    pbl_bounds = bounds
                if magic != b"PR85PLB1" and label_text == "PRE_RK":
                    state_bounds = bounds if state_bounds is None else state_bounds
                    if bounds != state_bounds:
                        raise ColumnSummaryError("PRE_RK consumer bounds vary in stage trace")
                    state_steps.add(timestep)
    except (OSError, EOFError) as exc:
        raise ColumnSummaryError(f"cannot read stage trace: {path}") from exc
    if pbl_bounds is None or state_bounds is None:
        raise ColumnSummaryError("stage trace lacks POST_PBL_TEND or PRE_RK consumer bounds")
    if first_labels != ["POST_PBL_TEND", "PRE_RK"]:
        raise ColumnSummaryError("stage trace does not begin with the required PBL and PRE_RK records")
    return pbl_bounds, state_bounds, state_steps


def area_weighted_totals(summary_path: Path, *, run_receipt_path: Path,
                         history_path: Path, stage_record_path: Path) -> dict[str, Any]:
    """Receipt/build/source-bound whole-grid totals grouped by model timestep."""
    summary = parse_column_summary(summary_path)
    receipt = _receipt_json(run_receipt_path)
    if receipt.get("status") not in ("COMPLETE", "INCOMPLETE"):
        raise ColumnSummaryError("area weighting requires a recognized run receipt")
    build_ref = receipt.get("candidate_build")
    if not isinstance(build_ref, dict) or not build_ref.get("receipt_path"):
        raise ColumnSummaryError("run receipt lacks candidate build identity")
    build_path = Path(build_ref["receipt_path"])
    if build_ref.get("receipt_sha256") != _sha256(build_path):
        raise ColumnSummaryError("run receipt candidate-build hash mismatch")
    build = _receipt_json(build_path)
    if build.get("status") != "PASS_OVERLAY_BUILD":
        raise ColumnSummaryError("candidate build receipt is not a passed overlay build")
    executable = Path(build.get("executable_path", ""))
    exe_hash = _sha256(executable)
    if (build.get("executable_sha256") != exe_hash
            or receipt.get("executed_executable_sha256") != exe_hash
            or build_ref.get("executable_sha256") != exe_hash):
        raise ColumnSummaryError("run receipt does not bind the candidate executable")
    override = build.get("source_overrides", {}).get("module_mp_kdm6.o")
    if not isinstance(override, dict):
        raise ColumnSummaryError("candidate build does not identify compiled KDM source")
    source_path = Path(override.get("staged_path", ""))
    source_hash = _sha256(source_path)
    if (override.get("requested_sha256") != source_hash
            or override.get("staged_sha256") != source_hash):
        raise ColumnSummaryError("candidate build does not bind compiled KDM source bytes")
    source = source_path.read_text(encoding="utf-8")
    if TAG not in source:
        raise ColumnSummaryError("compiled KDM source does not contain the PR90 column collector")
    _verify_source_wrapper(source)

    layout = _verify_execution_layout(receipt)
    _require_bound_output(receipt, history_path)
    _require_bound_output(receipt, summary_path)
    _require_bound_output(receipt, stage_record_path)

    indices, grid = native._file_index([history_path])
    times = sorted(indices)
    if len(times) < 2:
        raise ColumnSummaryError("area join requires multi-record history times")
    interval = int((times[1] - times[0]).total_seconds())
    endpoint = int((times[-1] - times[0]).total_seconds())
    native._receipt_window(run_receipt_path, [history_path], times, endpoint, interval, True)
    ny, nx = grid["shape"]
    pbl_bounds, state_bounds, state_steps = _stage_record_bounds(stage_record_path)
    if ((pbl_bounds["its"], pbl_bounds["ite"], pbl_bounds["jts"], pbl_bounds["jte"])
            != (1, nx, 1, ny)):
        raise ColumnSummaryError("POST_PBL_TEND does not record full physical bounds 1..nx/1..ny")
    if ((state_bounds["its"], state_bounds["ite"], state_bounds["jts"], state_bounds["jte"])
            != (2, nx - 1, 2, ny - 1)):
        raise ColumnSummaryError("PRE_RK does not record the supported interior consumer bounds")
    if any(pbl_bounds[key] != state_bounds[key]
           for key in ("ims", "ime", "jms", "jme", "kms", "kme")):
        raise ColumnSummaryError("PBL and PRE_RK stage memory bounds differ")
    if (state_bounds["ims"] > 1 or state_bounds["ime"] < nx
            or state_bounds["jms"] > 1 or state_bounds["jme"] < ny):
        raise ColumnSummaryError("stage memory bounds do not contain the full physical grid")
    if any(block["i_start"] != 2 or block["i_end"] != nx - 1
           or not 2 <= block["lat"] <= ny - 1 or block["timestep"] not in state_steps
           or not 1 <= block["timestep"] <= len(receipt.get("expected_model_timestamps", []))
           for block in summary["blocks"]):
        raise ColumnSummaryError("column blocks disagree with same-run PRE_RK consumer bounds")
    with netCDF4.Dataset(history_path) as ds:
        ds.set_auto_mask(False)
        dx, dy = float(ds.DX), float(ds.DY)
        mx_var, my_var = ds.variables["MAPFAC_MX"], ds.variables["MAPFAC_MY"]
        if tuple(mx_var.shape[1:]) != (ny, nx) or tuple(my_var.shape[1:]) != (ny, nx):
            raise ColumnSummaryError("history map-factor shapes do not match mass-grid geometry")
        mx = np.asarray(mx_var[0], dtype=np.float64)
        my = np.asarray(my_var[0], dtype=np.float64)
        for record in range(1, len(times)):
            if not np.array_equal(mx, np.asarray(mx_var[record])) or not np.array_equal(
                    my, np.asarray(my_var[record])):
                raise ColumnSummaryError("history map factors vary across the run window")
    weighted = _area_weight_columns(summary["columns"], dx_m=dx, dy_m=dy,
                                    mapfac_mx=mx, mapfac_my=my, nx=nx, ny=ny)
    final_completed_step = receipt.get("final_completed_step")
    if not isinstance(final_completed_step, int) or final_completed_step < 0:
        raise ColumnSummaryError("run receipt lacks final completed model timestep")
    expected_j = set(range(2, ny))
    expected_columns = (nx - 2) * (ny - 2)
    coverage = {}
    for timestep in sorted(weighted):
        step_rows = [row for row in summary["columns"] if row["timestep"] == timestep]
        seen_j = {row["lat"] for row in step_rows}
        missing_j = sorted(expected_j - seen_j)
        complete_step = timestep <= final_completed_step
        if complete_step and missing_j:
            raise ColumnSummaryError(
                f"completed timestep {timestep} lacks full j coverage; missing {missing_j}")
        coverage[timestep] = {
            "status": "FULL" if not missing_j else "PARTIAL",
            "completed": complete_step,
            "expected_j": [2, ny - 1],
            "seen_j": sorted(seen_j),
            "missing_j": missing_j,
            "expected_columns": expected_columns,
            "observed_columns": len(step_rows),
        }
    return {"status": "AREA_WEIGHTED_CUMULATIVE", "units": "kg per model timestep over recorded KDM columns",
            "run_status": receipt["status"],
            "accumulation": "cumulative cold-process request activity summed over KDM calls at each model timestep",
            "area_formula": "DX*DY/(MAPFAC_MX*MAPFAC_MY)",
            "run_receipt_sha256": _sha256(run_receipt_path),
            "candidate_build_receipt_sha256": _sha256(build_path),
            "candidate_executable_sha256": exe_hash,
            "compiled_kdm_source_sha256": source_hash,
            "execution_layout_status": layout["status"],
            "execution_layout_source_sha256": layout["source_sha256"],
            "history_sha256": _sha256(history_path),
            "stage_record_sha256": _sha256(stage_record_path),
            "history_times": [t.strftime("%Y-%m-%d_%H:%M:%S") for t in times],
            "native_grid": {"nx": nx, "ny": ny, "dx_m": dx, "dy_m": dy},
            "by_timestep": weighted, "coverage_by_timestep": coverage,
            "final_completed_step": final_completed_step}


def inspect_legacy_ledger(path: Path) -> dict[str, Any]:
    """Legacy rows cannot recover PR90 per-call column aggregates."""
    if path.is_symlink() or not path.is_file():
        raise ColumnSummaryError(f"ledger is not a regular file: {path}")
    return {"status": "NOT_EVALUATED",
            "reason": "legacy raw rows cannot recover PR90 compact per-call columns",
            "source": str(path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    output = json.dumps(parse_column_summary(args.summary), indent=2, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
