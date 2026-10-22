#!/usr/bin/env python3
"""Account actual KDM6 cutoff stores in the receipt-bound same-call water budget."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import netCDF4
import numpy as np

from native_kdm6_trace import read_dump
from pr67_kdm6_process_budget import parse_process_capture
from pr95_call_budget import WATER, HISTORY, _read_map_geometry
from pr97_t1_rounding import analyze as analyze_pr97, read_columns, same_call_bottom


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def add_two_sum(total: np.ndarray, compensation: np.ndarray,
               index: tuple[int, int, int], value: float) -> None:
    """Retain the low part when adding one weighted source store change."""
    current, tail = float(total[index]), value
    high = current + tail
    back = high - current
    low = (current - (high - back)) + (tail - back)
    total[index] = high
    compensation[index] += low


def cutoff_columns(path: Path, bounds: dict, density: np.ndarray,
                   thickness: np.ndarray, area: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, np.ndarray]:
    """Sum only water changes recorded at the existing cutoff assignments."""
    expected_state = (bounds["jte"] - bounds["jts"] + 1,
                      bounds["kte"] - bounds["kts"] + 1,
                      bounds["ite"] - bounds["its"] + 1)
    expected_area = (expected_state[0], expected_state[2])
    if (density.shape != expected_state or thickness.shape != expected_state or area.shape != expected_area or
            not np.isfinite(density).all() or not np.isfinite(thickness).all() or
            not np.isfinite(area).all() or np.any(density <= 0) or
            np.any(thickness <= 0) or np.any(area <= 0)):
        raise ValueError("cutoff weights must match finite positive same-call geometry")
    shape = area.shape
    by_species = np.zeros((5, *shape), dtype=np.float64)
    species_compensation = np.zeros_like(by_species)
    counts = np.zeros(shape, dtype=np.int64)
    seen: set[tuple[int, int, int, int]] = set()
    rows = 0
    with path.open(encoding="ascii") as stream:
        for line in stream:
            if not line.startswith("PR85_KDM6_CUTOFF"):
                continue
            fields = line.split()
            if len(fields) != 33:
                raise ValueError("invalid PR85 cutoff record width")
            i, j, k, loop, mask = map(int, fields[1:6])
            if not (bounds["its"] <= i <= bounds["ite"] and
                    bounds["jts"] <= j <= bounds["jte"] and
                    bounds["kts"] <= k <= bounds["kte"] and loop >= 1):
                raise ValueError("cutoff record lies outside the same KDM6 call")
            identity = (i, j, k, loop)
            if identity in seen:
                raise ValueError("duplicate cutoff event in isolated single-call replay")
            seen.add(identity)
            values = np.asarray(fields[6:31], dtype=np.float64)
            if not np.isfinite(values).all():
                raise ValueError("nonfinite cutoff operand")
            if values[0] <= 0 or np.any(values[3:13] < 0) or np.any(values[1:3] < 0):
                raise ValueError("invalid cutoff density, threshold, or water store")
            qmin, qcrmin = values[1:3]
            before, after = values[3:8], values[8:13]
            expected_mask = sum(bit for bit, q, threshold in zip(
                (1, 2, 4, 8, 16), before, (qmin, qmin, qcrmin, qcrmin, qcrmin), strict=True)
                if q <= threshold)
            if mask != expected_mask:
                raise ValueError("cutoff threshold mask differs from captured before stores")
            for n, (q, threshold) in enumerate(zip(before, (qmin, qmin, qcrmin, qcrmin, qcrmin), strict=True)):
                if q <= threshold and after[n] != 0.0:
                    raise ValueError("cutoff assignment did not clear its thresholded water store")
                if q > threshold and after[n] != q:
                    raise ValueError("cutoff assignment changed a store above its threshold")
            row, col, level = j - bounds["jts"], i - bounds["its"], k - bounds["kts"]
            weight = float(density[row, level, col]) * float(thickness[row, level, col]) * area[row, col]
            for species in range(5):
                add_two_sum(by_species, species_compensation,
                            (species, row, col), (float(after[species]) - float(before[species])) * weight)
            counts[row, col] += 1
            rows += 1
    by_species += species_compensation
    totals = np.sum(by_species, axis=0, dtype=np.float64)
    return totals, counts, rows, by_species


def stats(values: np.ndarray, event_counts: np.ndarray | None = None) -> dict[str, float | int]:
    return {"signed_kg": math.fsum(values.flat),
            "L1_column_kg": math.fsum(np.abs(values).flat),
            "max_abs_column_kg": float(np.max(np.abs(values))),
            "columns_with_events": int(np.count_nonzero(event_counts if event_counts is not None else values))}


def count_rows(path: Path, prefix: str) -> int:
    with path.open(encoding="ascii") as source:
        return sum(line.startswith(prefix) for line in source)


def verify_replay_manifest(path: Path, *, executable: Path, pre: Path, post: Path,
                           replay_post: Path, liquid: Path, cutoff: Path,
                           rain: Path, ice: Path) -> dict:
    """Bind captured ledgers to the completed isolated-executable invocation."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required_hashes = {
        "executable_before_sha256": executable,
        "executable_after_sha256": executable,
        "input_pre_sha256": pre,
        "native_post_sha256": post,
        "replay_post_sha256": replay_post,
        "liquid_columns_sha256": liquid,
        "cutoff_rows_sha256": cutoff,
        "rain_rows_sha256": rain,
        "ice_rows_sha256": ice,
    }
    if manifest.get("schema") != "pr98_isolated_c1_t1_replay_v1" or manifest.get("returncode") != 0:
        raise ValueError("isolated replay manifest is incomplete")
    for field, artifact in required_hashes.items():
        if manifest.get(field) != sha256(artifact):
            raise ValueError(f"isolated replay manifest hash mismatch: {field}")
    expected_rows = {
        "liquid_columns": count_rows(liquid, "LIQCOL"),
        "cutoff_events": count_rows(cutoff, "PR85_KDM6_CUTOFF"),
        "rain_sedimentation": count_rows(rain, "PR87_RAIN_SED"),
        "ice_sedimentation": count_rows(ice, "PR85_ICE_SED"),
    }
    if manifest.get("row_counts") != expected_rows:
        raise ValueError("isolated replay manifest row counts differ from its hashed ledgers")
    return manifest


def sedimentation_q_residual(path: Path, prefix: str, bounds: dict,
                             area: np.ndarray) -> tuple[np.ndarray, int]:
    """Reduce the paired sediment helper's independently stored Q residual."""
    totals = np.zeros(area.shape, dtype=np.float64)
    seen: set[tuple[int, int, int]] = set()
    rows = 0
    with path.open(encoding="ascii") as stream:
        for line in stream:
            fields = line.split()
            if not fields or fields[0] != prefix:
                continue
            if len(fields) != 17:
                raise ValueError(f"invalid {prefix} sediment record width")
            i, j, substep = map(int, fields[1:4])
            if not (bounds["its"] <= i <= bounds["ite"] and
                    bounds["jts"] <= j <= bounds["jte"] and substep >= 1):
                raise ValueError(f"{prefix} sediment record outside the same call")
            key = (i, j, substep)
            if key in seen:
                raise ValueError(f"duplicate {prefix} sediment event")
            seen.add(key)
            values = np.asarray(fields[5:], dtype=np.float64)
            if not np.isfinite(values).all():
                raise ValueError(f"nonfinite {prefix} sediment residual")
            totals[j - bounds["jts"], i - bounds["its"]] += values[10] * area[j - bounds["jts"], i - bounds["its"]]
            rows += 1
    return totals, rows


def analyze(root: Path, pre_path: Path, post_path: Path, process_path: Path,
            replay_post: Path, liquid_path: Path, cutoff_path: Path,
            rain_path: Path, ice_path: Path, executable_source: Path,
            replay_manifest_path: Path) -> dict:
    """Join direct cutoff changes with existing receipt-bound PR97 same-call terms."""
    liquid = analyze_pr97(root, pre_path, post_path, process_path, replay_post, liquid_path)
    pre, post = read_dump(pre_path), read_dump(post_path)
    bounds = pre["bounds"]
    density, thickness = pre["fields"]["DEN"].astype(np.float64), pre["fields"]["DELZ"].astype(np.float64)
    history = root / "run" / HISTORY
    with netCDF4.Dataset(history) as dataset:
        dataset.set_auto_mask(False)
        area, _, _ = _read_map_geometry(dataset,
            slice(bounds["jts"] - 1, bounds["jte"]), slice(bounds["its"] - 1, bounds["ite"]))
    cutoff, event_counts, event_rows, cutoff_by_species = cutoff_columns(
        cutoff_path, bounds, density, thickness, area)
    parse_process_capture(process_path)  # validates same-call stage rows before reduction
    bottom = same_call_bottom(process_path, pre, area)
    water_delta = np.zeros_like(cutoff)
    for name in WATER:
        water_delta += np.sum((post["fields"][name].astype(np.float64) -
                               pre["fields"][name].astype(np.float64)) *
                              density * thickness * area[:, None, :], axis=1)
    raw = water_delta + bottom
    _, liquid_values = read_columns(liquid_path, bounds)
    liquid_term = (liquid_values[:, :, 0] + liquid_values[:, :, 1]) * area
    unexplained_before = raw - liquid_term
    rain_q, rain_rows = sedimentation_q_residual(rain_path, "PR87_RAIN_SED", bounds, area)
    ice_q, ice_rows = sedimentation_q_residual(ice_path, "PR85_ICE_SED", bounds, area)
    remaining = unexplained_before - cutoff
    original_order = np.argsort(np.abs(unexplained_before), axis=None)[-20:][::-1]
    order = np.argsort(np.abs(remaining), axis=None)[-20:][::-1]
    exe = replay_post.parent / "replay.exe"
    if not exe.is_file():
        raise ValueError("isolated replay executable is missing beside replay output")
    executable_before = sha256(executable_source)
    executable_after = sha256(exe)
    if executable_before != executable_after:
        raise ValueError("isolated replay executable differs from its recorded copy source")
    replay_manifest = verify_replay_manifest(replay_manifest_path, executable=exe,
        pre=pre_path, post=post_path, replay_post=replay_post, liquid=liquid_path,
        cutoff=cutoff_path, rain=rain_path, ice=ice_path)
    return {
        "schema": "pr98_samecall_cutoff_account_v1", "arm": liquid["arm"],
        "columns": int(area.size), "measure": liquid["measure"], "R_raw": liquid["R_raw"],
        "C_liquid_store": liquid["C_liquid_store"],
        "C_cutoff_actual_store_change": stats(cutoff, event_counts),
        "PR87_RAIN_SED_Q_stage_residual": stats(rain_q),
        "PR85_ICE_SED_Q_stage_residual": stats(ice_q),
        "R_unexplained_after_liquid_and_cutoff": stats(remaining),
        "cutoff": {"source": "PR85_KDM6_CUTOFF source before/after Q stores at the existing qmin/qcrmin assignments",
                   "events": event_rows, "columns_with_events": int(np.count_nonzero(event_counts)),
                   "event_counts_by_column": int(np.sum(event_counts)),
                   "independent_term": True},
        "other_process_q_store_error": {
            "PR87_RAIN_SED": {**stats(rain_q), "ledger_rows": rain_rows,
                              "selected_184_147_kg": float(rain_q[147 - bounds["jts"], 184 - bounds["its"]])},
            "PR85_ICE_SED": {**stats(ice_q), "ledger_rows": ice_rows,
                             "selected_184_147_kg": float(ice_q[147 - bounds["jts"], 184 - bounds["its"]])}},
        "selected_column_184_147": {
            "R_raw_kg": float(raw[147 - bounds["jts"], 184 - bounds["its"]]),
            "C_liquid_store_kg": float(liquid_term[147 - bounds["jts"], 184 - bounds["its"]]),
            "C_cutoff_actual_store_change_kg": float(cutoff[147 - bounds["jts"], 184 - bounds["its"]]),
            "PR87_RAIN_SED_Q_stage_residual_kg": float(rain_q[147 - bounds["jts"], 184 - bounds["its"]]),
            "PR85_ICE_SED_Q_stage_residual_kg": float(ice_q[147 - bounds["jts"], 184 - bounds["its"]]),
            "cutoff_store_change_by_species_kg": dict(zip(
                ("QC", "QI", "QR", "QS", "QG"),
                map(float, cutoff_by_species[:, 147 - bounds["jts"], 184 - bounds["its"]]), strict=True)),
            "remaining_kg": float(remaining[147 - bounds["jts"], 184 - bounds["its"]])},
        "largest_remaining_columns": [
            {"i": int(n % area.shape[1] + bounds["its"]),
             "j": int(n // area.shape[1] + bounds["jts"]),
             "R_raw_kg": float(raw.flat[n]), "C_liquid_store_kg": float(liquid_term.flat[n]),
             "C_cutoff_actual_store_change_kg": float(cutoff.flat[n]),
             "PR87_RAIN_SED_Q_stage_residual_kg": float(rain_q.flat[n]),
             "PR85_ICE_SED_Q_stage_residual_kg": float(ice_q.flat[n]),
             "remaining_kg": float(remaining.flat[n])} for n in order],
        "largest_original_unexplained_columns": [
            {"i": int(n % area.shape[1] + bounds["its"]),
             "j": int(n // area.shape[1] + bounds["jts"]),
             "R_raw_kg": float(raw.flat[n]), "C_liquid_store_kg": float(liquid_term.flat[n]),
             "C_cutoff_actual_store_change_kg": float(cutoff.flat[n]),
             "remaining_kg": float(remaining.flat[n])} for n in original_order],
        "largest_positive_remaining_columns": [
            {"i": int(n % area.shape[1] + bounds["its"]),
             "j": int(n // area.shape[1] + bounds["jts"]),
             "remaining_kg": float(remaining.flat[n]),
             "C_cutoff_actual_store_change_kg": float(cutoff.flat[n]),
             "PR87_RAIN_SED_Q_stage_residual_kg": float(rain_q.flat[n]),
             "PR85_ICE_SED_Q_stage_residual_kg": float(ice_q.flat[n])}
            for n in np.argsort(remaining, axis=None)[-20:][::-1]],
        "identity": {"receipt_sha256": liquid["identity"]["receipt_sha256"],
                     "executable_sha256": liquid["identity"]["executable_sha256"],
                     "KDM6_source_sha256": liquid["identity"]["KDM6_source_sha256"],
                     "pre_sha256": sha256(pre_path), "post_sha256": sha256(post_path),
                     "process_sha256": sha256(process_path), "replay_post_sha256": sha256(replay_post),
                     "cutoff_rows_sha256": sha256(cutoff_path),
                     "rain_rows_sha256": sha256(rain_path), "ice_rows_sha256": sha256(ice_path),
                     "all_17_fields_and_XLAND_byte_equal": liquid["identity"]["all_17_fields_and_XLAND_byte_equal"],
                     "replay_invocation": {
                         "schema": "pr98_isolated_c1_t1_replay_v1", "status": "COMPLETE",
                         "executable_before_sha256": executable_before,
                         "executable_after_sha256": executable_after,
                         "executable_copy_source": str(executable_source),
                         "input_pre_sha256": sha256(pre_path),
                         "native_post_sha256": sha256(post_path), "replay_post_sha256": sha256(replay_post),
                         "same_invocation_artifacts": {
                             "liquid_rows_sha256": sha256(liquid_path), "cutoff_rows_sha256": sha256(cutoff_path),
                             "rain_rows_sha256": sha256(rain_path), "ice_rows_sha256": sha256(ice_path)},
                         "row_counts": {"liquid_columns": count_rows(liquid_path, "LIQCOL"),
                                        "cutoff_events": event_rows,
                                        "rain_sedimentation": rain_rows, "ice_sedimentation": ice_rows},
                         "area_source_path": str(history),
                         "area_source_sha256": liquid["identity"]["history_sha256"],
                         "area_variable": "MAPFAC_M", "area_bounds_1based": {
                             "jts": bounds["jts"], "jte": bounds["jte"],
                             "its": bounds["its"], "ite": bounds["ite"]},
                         "profile": "tests/intel_toolchain.sh; prebuilt frozen C1 diagnostic executable",
                         "execution": "fresh empty directory; OMP_NUM_THREADS=1; unlimited stack",
                         "manifest_sha256": sha256(replay_manifest_path),
                         "manifest_row_counts": replay_manifest["row_counts"]}},
        "limits": ["Cutoff is a direct removal from the five captured Q stores; it is reported as an independent term.",
                   "The remaining residual is open and is not assigned to rounding or physical water loss.",
                   "This does not establish native hybrid host water, energy, mass-wind, or observation closure."],
        "physical_approval": "FAIL_OPEN"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-root", "pre", "post", "process", "replay-post", "liquid-columns",
                 "cutoff-rows", "rain-rows", "ice-rows", "executable-source",
                 "replay-manifest", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.run_root, args.pre, args.post, args.process,
                     args.replay_post, args.liquid_columns, args.cutoff_rows,
                     args.rain_rows, args.ice_rows, args.executable_source,
                     args.replay_manifest)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
