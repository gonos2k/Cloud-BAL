#!/usr/bin/env python3
"""Audit native RK-boundary QC increments and completed-update neutrality."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from pr67_negative_qc_replay import (  # noqa: E402
    PRE_COLUMNS, first_appearance_sets, mask_negative_sets, read_observer, sha256,
    summarize as replay_summary,
    verify_receipt_file,
)

NEUTRAL_OUTPUTS = (
    "wrfout_d01_2026-08-16_12:00:00", "namelist.output",
    "pr63_transition_masks.bin", "kdm6_first_call_pre.raw",
    "kdm6_first_call_post.raw", "pr63_transition_stages.raw",
    "pr63_geometry.raw", "pr65_pbl_operator.raw", "pr65_pbl_nc.raw",
)


def read_targets(path: Path) -> set[tuple[int, int, int]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines:
        raise ValueError("target coordinate file is empty")
    expected = int(lines[0])
    coords = [tuple(map(int, line.split())) for line in lines[1:]]
    if len(coords) != expected or len(set(coords)) != expected or any(len(c) != 3 for c in coords):
        raise ValueError("target coordinate file has duplicate, malformed, or missing keys")
    return set(coords)


def validate_input_inventory(run_root: Path, inputs: list[dict]) -> dict[str, Path]:
    """Rehash a unique, run-local inventory of regular single-link inputs."""
    root = run_root.resolve(strict=True)
    normalized: dict[str, Path] = {}
    for row in inputs:
        raw_path = Path(row.get("path", ""))
        before, after = row.get("sha256_before"), row.get("sha256_after")
        if (not raw_path.is_absolute() or not isinstance(before, str) or
                not re.fullmatch(r"[0-9a-fA-F]{64}", before) or
                not isinstance(after, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", after) or
                before.lower() != after.lower()):
            raise ValueError("run input inventory has malformed paths or SHA256 values")
        try:
            resolved = raw_path.resolve(strict=True)
            relative = resolved.relative_to(root).as_posix()
            metadata = raw_path.lstat()
        except (FileNotFoundError, ValueError) as exc:
            raise ValueError(f"run input escapes its root or is missing: {raw_path}") from exc
        if relative in normalized:
            raise ValueError(f"run input inventory contains duplicate normalized path: {relative}")
        if (raw_path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or
                sha256(resolved) != before.lower()):
            raise ValueError(f"run input does not match its unchanged hash-bound file: {raw_path}")
        normalized[relative] = resolved
    return normalized


def read_stages(path: Path, targets: set[tuple[int, int, int]]) -> dict[str, dict[tuple[int, tuple[int, int, int]], tuple[np.float32, np.float32]]]:
    stages: dict[str, dict[tuple[int, tuple[int, int, int]], tuple[np.float32, np.float32]]] = {}
    last_rank: dict[tuple[int, tuple[int, int, int]], int] = {}
    ranks = {"P1_POST": 0, "P2_POST": 1, "RK_TEND_PRE": 2,
             "RK_TEND_POST": 3, "UPDATE_PRE": 4, "UPDATE_POST": 5}
    with path.open(encoding="ascii") as stream:
        for line_no, line in enumerate(stream, 1):
            fields = line.split()
            if len(fields) != 8 or fields[0] != "QC_STAGE":
                raise ValueError(f"malformed stage record at line {line_no}")
            label = fields[1]
            if label not in {"P1_POST", "P2_POST", "RK_TEND_PRE", "RK_TEND_POST", "UPDATE_PRE", "UPDATE_POST"}:
                raise ValueError(f"unexpected stage label at line {line_no}: {label}")
            rk, i, j, k = map(int, fields[2:6])
            coord = (i, j, k)
            if coord not in targets:
                raise ValueError(f"stage record outside declared target mask at line {line_no}")
            vals = tuple(np.float32(float(v)) for v in fields[6:8])
            if not all(np.isfinite(v) for v in vals) or rk not in (1, 2, 3):
                raise ValueError(f"invalid stage value or RK step at line {line_no}")
            bucket = stages.setdefault(label, {})
            key = (rk, coord)
            if key in bucket:
                raise ValueError(f"duplicate stage key {label} {key}")
            rank = ranks[label] if rk == 1 and label in ("P1_POST", "P2_POST") else 2 + (rk - 1) * 4 + ranks[label] - 2
            if rank <= last_rank.get(key, -1):
                raise ValueError(f"stage boundary is out of order for {key}: {label}")
            last_rank[key] = rank
            bucket[key] = vals
    return stages


def keyed_target_rows(observer: Path, targets: set[tuple[int, int, int]]) -> tuple[dict, dict]:
    before, after, _ = read_observer(observer / "pr67_qc_rk.raw")
    target_before = {key: row for key, row in before.items() if key[1] in targets}
    target_after = {
        stage: {key: value for key, value in values.items() if key[1] in targets}
        for stage, values in after.items()
    }
    return target_before, target_after


def keyed_equal(left: dict, right: dict, label: str) -> int:
    if left.keys() != right.keys():
        raise ValueError(f"{label} key sets differ: {len(left)} vs {len(right)}")
    for key in left:
        a, b = np.asarray(left[key], dtype=np.float32), np.asarray(right[key], dtype=np.float32)
        if not np.array_equal(a, b):
            raise ValueError(f"{label} initialized binary32 values differ at {key}")
    return len(left)


def read_initialized_process_rows(path: Path) -> dict[tuple[int, int, int, int], np.ndarray]:
    """Read only flags, aggregate tendency, and active PBL/CU source arrays."""
    expected_header = ("QCCHAN", "rkstep", "i", "j", "k", "bl_pbl", "cu", "shcu",
                       "diff_opt", "km_opt", "qc_moist_tend", "rqcblten", "rqccuten",
                       "rqcshten", "rqcncuten", "rqcnshten")
    rows: dict[tuple[int, int, int, int], np.ndarray] = {}
    with path.open(encoding="ascii") as stream:
        header = tuple(stream.readline().split())
        if header != expected_header:
            raise ValueError("unexpected PR64 process-channel header")
        for line_no, line in enumerate(stream, 2):
            fields = line.split()
            if len(fields) != len(expected_header) or fields[0] != "QCCHAN":
                raise ValueError(f"malformed PR64 process-channel record at line {line_no}")
            key = tuple(map(int, fields[1:5]))
            if key in rows:
                raise ValueError(f"duplicate PR64 process-channel key {key}")
            # Do not even parse SHCU or NC channel columns: these can contain stale data.
            flags = np.asarray(list(map(int, fields[5:10])), dtype=np.int32)
            active = np.asarray([np.float32(float(fields[index])) for index in (10, 11, 12)], dtype=np.float32)
            if not np.isfinite(active).all():
                raise ValueError(f"non-finite initialized PR64 source value at line {line_no}")
            if tuple(flags) != (11, 37, 0, 1, 4):
                raise ValueError(f"unexpected configured process flags at line {line_no}")
            rows[key] = np.concatenate((flags.astype(np.float32), active))
    return rows


def increment_stats(values: list[np.float32]) -> dict[str, object]:
    if not values:
        raise ValueError("cannot summarize empty increment")
    arr = np.asarray(values, dtype=np.float32)
    signs = Counter("negative" if x < 0 else "positive" if x > 0 else "zero" for x in arr)
    return {"count": len(arr), "signs": dict(sorted(signs.items())),
            "min": float(np.min(arr)), "max": float(np.max(arr)),
            "sum_abs_binary32_values": float(np.sum(np.abs(arr), dtype=np.float64))}


def _first_namelist_value(text: str, name: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}\s*=\s*([^,\s]+)", text, re.IGNORECASE | re.MULTILINE)
    if match is None:
        raise ValueError(f"runtime namelist output omits {name}")
    value = match.group(1).upper()
    return value.split("*", 1)[1] if "*" in value else value


def read_runtime_configuration(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="ascii", errors="replace")
    integer_names = ("BL_PBL_PHYSICS", "CU_PHYSICS", "SHCU_PHYSICS", "DIFF_OPT",
                     "DIFF_6TH_OPT", "KM_OPT", "USE_Q_DIABATIC")
    logical_names = ("MOIST_MIX2_OFF", "MOIST_MIX6_OFF", "SPECIFIED", "NESTED", "HAVE_BCS_MOIST")
    config: dict[str, object] = {name.lower(): int(_first_namelist_value(text, name))
                                 for name in integer_names}
    for name in logical_names:
        value = _first_namelist_value(text, name)
        if value not in ("T", "F", ".TRUE.", ".FALSE."):
            raise ValueError(f"unexpected runtime logical value for {name}: {value}")
        config[name.lower()] = value in ("T", ".TRUE.")
    expected = {"bl_pbl_physics": 11, "cu_physics": 37, "shcu_physics": 0,
                "diff_opt": 1, "diff_6th_opt": 0, "km_opt": 4,
                "use_q_diabatic": 0, "moist_mix2_off": False,
                "moist_mix6_off": False, "specified": True,
                "nested": False, "have_bcs_moist": False}
    if config != expected:
        raise ValueError(f"runtime configuration differs from reviewed capture profile: {config}")
    return config


def verify_build_chain(observer_source: Path, expected_executable: Path) -> dict[str, object]:
    build_dir = observer_source.parent
    compile_path = build_dir / "compile_command.json"
    link_path = build_dir / "link_final_command.json"
    compile_argv = json.loads(compile_path.read_text(encoding="utf-8"))
    link_argv = json.loads(link_path.read_text(encoding="utf-8"))
    source_arg = next((Path(arg) for arg in compile_argv if arg == str(observer_source)), None)
    object_arg = Path(compile_argv[compile_argv.index("-o") + 1])
    if source_arg is None or sha256(source_arg) != sha256(observer_source):
        raise ValueError("recorded compile argv does not compile the audited observer source")
    archive_arg = next((arg for arg in link_argv if arg.endswith("libwrflib_pr65.a")), None)
    if archive_arg is None or "-o" not in link_argv:
        raise ValueError("recorded link argv omits candidate archive or output")
    linked_exe = Path(link_argv[link_argv.index("-o") + 1])
    archive = linked_exe.parent / archive_arg
    if linked_exe.resolve() != expected_executable.resolve():
        raise ValueError("recorded link argv output does not match expected executable")
    archived_object = subprocess.run(["ar", "p", str(archive), "solve_em.o"],
                                     check=True, capture_output=True).stdout
    archived_hash = hashlib.sha256(archived_object).hexdigest()
    if archived_hash != sha256(object_arg):
        raise ValueError("linked solve_em.o member differs from freshly compiled observer object")
    return {"compile_command_sha256": sha256(compile_path),
            "observer_object_sha256": sha256(object_arg),
            "link_command_sha256": sha256(link_path),
            "link_archive_sha256": sha256(archive),
            "archived_solve_em_member_sha256": archived_hash,
            "linked_executable_sha256": sha256(linked_exe)}


def audit(observer: Path, baseline: Path, reference: Path, expected_executable: Path,
          observer_source: Path) -> dict[str, object]:
    receipt_path = observer / "run-isolation.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("returncode") != 0 or receipt.get("input_integrity") != "PASS" or receipt.get("output_isolation") != "PASS":
        raise ValueError("guarded run did not pass isolation")
    outputs = {record["path"]: record for record in receipt.get("outputs", [])}
    if len(outputs) != len(receipt.get("outputs", [])):
        raise ValueError("run receipt contains duplicate output paths")
    for name in ("pr67_qc_rk.raw", "pr68_qc_stages.raw", *NEUTRAL_OUTPUTS):
        if name not in outputs:
            raise ValueError(f"run receipt omits required output {name}")
        verify_receipt_file(observer, outputs[name])
    inputs = receipt.get("inputs", [])
    if len(inputs) != 102:
        raise ValueError("run inputs are incomplete or changed")
    inventory = validate_input_inventory(observer, inputs)
    executable_paths = [path for relative, path in inventory.items()
                        if Path(relative).name == "wrf.exe"]
    coordinate_paths = [path for relative, path in inventory.items()
                        if Path(relative).name == "pr68_target_qc_coords.txt"]
    if len(executable_paths) != 1 or len(coordinate_paths) != 1:
        raise ValueError("run executable or target list is not uniquely declared as an input")
    run_exe_hash = sha256(observer / "wrf.exe")
    executable_row = next(row for row in inputs if Path(row["path"]).resolve() == executable_paths[0])
    coordinate_row = next(row for row in inputs if Path(row["path"]).resolve() == coordinate_paths[0])
    if run_exe_hash != sha256(expected_executable) or run_exe_hash != executable_row["sha256_before"]:
        raise ValueError("run executable differs from the linked, declared executable")
    if sha256(observer / "pr68_target_qc_coords.txt") != coordinate_row["sha256_before"]:
        raise ValueError("runtime target coordinate input differs from its declared input hash")
    if observer_source.is_symlink() or not observer_source.is_file():
        raise ValueError("observer source is not a regular file")
    build = verify_build_chain(observer_source, expected_executable)

    replay = replay_summary(observer, baseline, expected_executable, observer_source,
                            expected_input_count=102)
    runtime_config = read_runtime_configuration(observer / "namelist.output")
    for name in NEUTRAL_OUTPUTS:
        if sha256(observer / name) != sha256(baseline / name):
            raise ValueError(f"completed state differs byte-for-byte from pinned baseline: {name}")
    targets = read_targets(observer / "pr68_target_qc_coords.txt")
    if len(targets) != 23494:
        raise ValueError("target mask size differs from the 23,494-cell KDM-entry mask")

    ref_before, ref_after = keyed_target_rows(reference, targets)
    cur_before, cur_after = keyed_target_rows(observer, targets)
    pre_matches = keyed_equal(ref_before, cur_before, "initialized PRE_COLUMNS")
    post_matches = keyed_equal(ref_after["AFTER_UPDATE"], cur_after["AFTER_UPDATE"], "AFTER_UPDATE QC")
    reference_process = read_initialized_process_rows(reference / "pr64_qc_channels.raw")
    current_process = read_initialized_process_rows(observer / "pr64_qc_channels.raw")
    process_matches = keyed_equal(reference_process, current_process,
                                  "initialized PR64 flags/aggregate/PBL/CU channels")

    stages = read_stages(observer / "pr68_qc_stages.raw", targets)
    _, negative_masks = mask_negative_sets(baseline / "pr63_transition_masks.bin")
    if targets != negative_masks[3]:
        raise ValueError("runtime coordinate list differs from the completed RK3 KDM-entry negative mask")
    first_negative_groups = first_appearance_sets(negative_masks, targets)
    if [len(group) for group in first_negative_groups] != [
            replay["negative_qc"][f"first_negative_after_rk{rk}"] for rk in (1, 2, 3)]:
        raise ValueError("completed-boundary first-negative groups differ from replay")
    expected_keys_by_label = {
        "P1_POST": {(1, coord) for coord in targets},
        "P2_POST": {(1, coord) for coord in targets},
        **{label: {(rk, coord) for rk in (1, 2, 3) for coord in targets}
           for label in ("RK_TEND_PRE", "RK_TEND_POST", "UPDATE_PRE", "UPDATE_POST")},
    }
    for label, expected_keys in expected_keys_by_label.items():
        if stages.get(label, {}).keys() != expected_keys:
            raise ValueError(f"{label} stage has duplicate/missing target keys")
    if set(stages) != {"P1_POST", "P2_POST", "RK_TEND_PRE", "RK_TEND_POST", "UPDATE_PRE", "UPDATE_POST"}:
        raise ValueError("inactive qdiag or boundary stages were unexpectedly captured")

    # Stage boundary identities establish which initialized source is being differenced.
    exact = Counter()
    source_increments: dict[int, list[np.float32]] = {rk: [] for rk in (1, 2, 3)}
    diffusion_increments: dict[int, list[np.float32]] = {rk: [] for rk in (1, 2, 3)}
    first_negative_diffusion: dict[int, list[np.float32]] = {rk: [] for rk in (1, 2, 3)}
    first_negative_source: list[np.float32] = []
    for rk, coord in expected_keys_by_label["RK_TEND_PRE"]:
        key = (rk, coord)
        tend_pre = stages["RK_TEND_PRE"][key][1]
        tend_post = stages["RK_TEND_POST"][key][1]
        update_pre = stages["UPDATE_PRE"][key][1]
        update_post = stages["UPDATE_POST"][key][0]
        if tend_post != update_pre:
            raise ValueError(f"post-diffusion tendency does not match update entry: {key}")
        is_first_negative = coord in first_negative_groups[rk - 1]
        if is_first_negative and key not in cur_after["AFTER_UPDATE"]:
            raise ValueError(f"first-negative cell missing PR67 AFTER_UPDATE value: {key}")
        if key in cur_after["AFTER_UPDATE"] and update_post != cur_after["AFTER_UPDATE"][key]:
            raise ValueError(f"completed QC differs between stage capture and PR67 AFTER_UPDATE: {key}")
        if is_first_negative:
            first_negative_diffusion[rk].append(np.float32(tend_post - tend_pre))
            exact["first_negative_update_post_match"] += 1
        exact["diffusion_to_update_entry"] += 1
        diffusion_increments[rk].append(np.float32(tend_post - tend_pre))
        if rk == 1:
            p1 = stages["P1_POST"][key][1]
            p2 = stages["P2_POST"][key][1]
            if p2 != tend_pre:
                raise ValueError(f"post-physics tendency does not match RK tendency entry: {key}")
            exact["physics_to_rk_entry"] += 1
            source_increments[rk].append(np.float32(p2 - p1))
            if coord in first_negative_groups[0]:
                first_negative_source.append(np.float32(p2 - p1))
            row = cur_before.get(key)
            if row is not None:
                physical_idx = PRE_COLUMNS.index("physical_tend")
                if row[physical_idx] != update_pre:
                    raise ValueError(f"captured aggregate physical tendency differs at RK1 update boundary: {key}")
                exact["aggregate_physical_to_update_pre"] += 1

    if exact["aggregate_physical_to_update_pre"] != replay["negative_qc"]["first_negative_after_rk1"]:
        raise ValueError("initialized RK1 aggregate tendency rows do not match the first-negative event count")

    return {
        "schema": "pr68_completed_qc_audit_v1",
        "provenance": {
            "observer_receipt_sha256": sha256(receipt_path),
            "observer_stage_sha256": sha256(observer / "pr68_qc_stages.raw"),
            "observer_source_sha256": sha256(observer_source),
            "build_chain": build,
            "run_executable_sha256": run_exe_hash,
            "target_coordinate_sha256": sha256(observer / "pr68_target_qc_coords.txt"),
            "reference_qc_raw_sha256": sha256(reference / "pr67_qc_rk.raw"),
            "observer_qc_raw_sha256": sha256(observer / "pr67_qc_rk.raw"),
            "declared_unchanged_input_count": len(inputs),
            "namelist_input_sha256": sha256(observer / "namelist.input"),
            "namelist_output_sha256": sha256(observer / "namelist.output"),
            "matched_baseline_output_sha256": {
                name: {"observer": sha256(observer / name), "baseline": sha256(baseline / name)}
                for name in NEUTRAL_OUTPUTS},
            "keyed_initialized_pre_column_matches": pre_matches,
            "keyed_after_update_matches": post_matches,
            "keyed_initialized_pr64_process_matches": process_matches,
            "neutral_baseline_outputs_byte_identical": list(NEUTRAL_OUTPUTS),
            "raw_diagnostic_whole_file_hashes_differ_from_reference": {
                name: {"reference": sha256(reference / name), "observer": sha256(observer / name)}
                for name in ("pr67_qc_rk.raw", "pr64_qc_channels.raw")
            },
        },
        "stage_boundary_exact_identity_counts": dict(exact),
        "stage_increment_summary_binary32": {
            "update_phy_ten_increment_P2_minus_P1": {"rk1": increment_stats(source_increments[1])},
            "rk_scalar_tend_increment_post_minus_pre": {f"rk{rk}": increment_stats(vals) for rk, vals in diffusion_increments.items()},
            "first_negative_cell_increments": {
                "update_phy_ten_increment_rk1_P2_minus_P1": increment_stats(first_negative_source),
                "rk_scalar_tend_increment_post_minus_pre": {
                    f"rk{rk}": increment_stats(vals) for rk, vals in first_negative_diffusion.items()},
            },
        },
        "pr67_first_negative_replay": replay,
        "process_interpretation": {
            "runtime_configuration_from_namelist_output": runtime_config,
            "rk1_source_increment": "P2_POST - P1_POST measures the active update_phy_ten QC tendency increment. With BL PBL and CU options active and SHCU inactive, it is the aggregate of configured PBL and convection source contributions. Per-cell channel arrays were not read from potentially stale inactive channels.",
            "rk1_diffusion_increment": "RK_TEND_POST - RK_TEND_PRE measures the binary32 tendency change inside rk_scalar_tend. The receipt-bound namelist.output has diff_opt=1, diff_6th_opt=0, moist_mix2_off=F and bl_pbl_physics=11. In the linked rk_scalar_tend source, horizontal diffusion is active for diff_opt=1 when moist_mix2_off is false; its vertical diffusion guard requires bl_pbl_physics=0 and is therefore false. Sixth-order diffusion is disabled. This measured increment is the active horizontal-diffusion tendency change for RK1 under this configuration.",
            "rk1_closure": "For each target RK1 cell, P2_POST equals RK_TEND_PRE, RK_TEND_POST equals UPDATE_PRE, and UPDATE_PRE equals the aggregate physical_tend recorded by PR67. Thus the aggregate physical update is resolved into the actual physics-source increment and later RK tendency increment at these boundaries.",
            "limits": ["No face fluxes were captured; the cell advection tendency cannot establish face-by-face conservative flux behavior.",
                       "No PBL-versus-convection numeric split is claimed; the captured increment is the active aggregate source update.",
                       "No inactive or uninitialized process channel values are interpreted.",
                       "No QC floor, tendency zeroing, or physics-option change was applied."]
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observer", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("reference", type=Path, help="retained PR67 run3")
    parser.add_argument("expected_executable", type=Path)
    parser.add_argument("observer_source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.observer, args.baseline, args.reference,
                       args.expected_executable, args.observer_source)
    except (OSError, ValueError, KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
        print(f"pr68_completed_qc_audit: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
