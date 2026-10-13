#!/usr/bin/env python3
"""Run detached same-time WRF initialization, then classify first-step outcome."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import stat
from pathlib import Path

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from run_isolated_native import copy_detached_input, run_isolated

WORKSPACE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL")
OFF_CHAIN_ARTIFACTS = {
    "off_wps": Path("/var/tmp/pr83_same13_off_20261013c/build/same13_off.wps"),
    "off_wps_readback": Path("/var/tmp/pr83_same13_off_20261013c/build/readback.final.json"),
    "off_metgrid": WORKSPACE / "scratch/pr83_same13_off_metgrid_20261013c/met_em.d01.2026-08-16_13:00:00.nc",
    "off_metgrid_readback": WORKSPACE / "scratch/pr83_same13_off_metgrid_20261013c/readback.json",
    "off_real_boundary_wrfinput": WORKSPACE / "scratch/pr83_same13_off_real_boundary_20261013a/wrfinput_d01",
    "off_real_boundary_wrfbdy": WORKSPACE / "scratch/pr83_same13_off_real_boundary_20261013a/wrfbdy_d01",
    "off_real_boundary_contract": WORKSPACE / "scratch/pr83_same13_off_real_boundary_20261013a/input_contract.json",
    "off_real_boundary_readback": WORKSPACE / "scratch/pr83_same13_off_real_boundary_20261013a/boundary_readback.json",
}
EXPECTED_OFF_SOURCE_NAMELIST_SHA256 = "59e949a1a9feffec06204f8abc9b090b3c294e1a501e9f9599cbfc10503646f6"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def provenance_paths(initialized_input_policy: Path | None = None) -> dict[str, Path]:
    paths = {
        "runner": Path(__file__).resolve(),
        "isolated_runtime_helper": ROOT / "tools/run_isolated_native.py",
        "initialization_readback_checker": ROOT / "tools/check_native_hybrid_geometry.py",
        "intel_setvars": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh"),
        "mpi_vars": Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh"),
    }
    paths.update(OFF_CHAIN_ARTIFACTS)
    if initialized_input_policy is not None:
        paths["native_moment_initializer"] = ROOT / "tools/initialize_native_moments.py"
        paths["native_moment_policy"] = initialized_input_policy.resolve(strict=True)
    return paths


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=re.IGNORECASE | re.MULTILINE)
    if count != 1:
        raise ValueError(f"expected one {label} namelist assignment; found {count}")
    return updated


def effective_namelist(source: Path) -> tuple[str, str]:
    original = source.read_text()
    if re.search(r"\buse_input_w\s*=", original, flags=re.IGNORECASE):
        raise ValueError("refusing to override inherited use_input_w source option")
    updated = original
    updated = replace_once(updated, r"^\s*run_seconds\s*=\s*\d+\s*,",
                           " run_seconds = 20,", "run_seconds")
    updated = replace_once(updated, r"^\s*end_hour\s*=\s*\d+\s*,",
                           " end_hour = 13,", "end_hour")
    updated = replace_once(updated, r"^\s*end_second\s*=\s*\d+\s*,",
                           " end_second = 20,", "end_second")
    # Freeze the intended start, rather than inheriting it silently.
    updated = replace_once(updated, r"^\s*start_hour\s*=\s*\d+\s*,",
                           " start_hour = 13,", "start_hour")
    updated = replace_once(updated, r"^\s*start_second\s*=\s*\d+\s*,",
                           " start_second = 00,", "start_second")
    if "run_seconds = 20" not in updated or "end_hour = 13" not in updated:
        raise AssertionError("effective diagnostic namelist differs from requested 13 UTC interval")
    return original, updated


def validate_off_source_namelist(source: Path) -> str:
    """Pin the retained MODE_OFF start configuration before any native launch."""
    actual = sha256(source)
    if actual != EXPECTED_OFF_SOURCE_NAMELIST_SHA256:
        raise ValueError("MODE_OFF native control requires the reviewed same13 source namelist")
    return actual


def write_new(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-case", type=Path, required=True,
                        help="retained source-bound diagnostic runtime and physics tables")
    parser.add_argument("--real-case", type=Path, required=True,
                        help="same-13 real.exe run containing wrfinput and 13-15 wrfbdy")
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--initialized-input-receipt", type=Path,
                        help="verified PR83 same13 prior receipt authorizing an alternate copied wrfinput")
    parser.add_argument("--initialized-input-policy", type=Path,
                        help="declared policy bound by the PR83 prior receipt")
    args = parser.parse_args()
    if args.initialized_input_receipt is not None or args.initialized_input_policy is not None:
        raise ValueError("MODE_OFF mass-only control cannot accept a PR83 prior receipt or candidate input")
    runtime = args.runtime_case.resolve(strict=True)
    real_case = args.real_case.resolve(strict=True)
    executable = args.executable.resolve(strict=True)
    run_dir = args.run_dir.absolute()
    if run_dir.exists() or run_dir.is_symlink():
        raise FileExistsError(f"fresh run directory required: {run_dir}")
    for name in ("wrfinput_d01", "wrfbdy_d01", "namelist.input"):
        if not (real_case / name).is_file():
            raise FileNotFoundError(real_case / name)
    source_namelist_sha256 = validate_off_source_namelist(real_case / "namelist.input")
    original_nml, effective_nml = effective_namelist(real_case / "namelist.input")
    if "use_sh_qv                           = .true." not in original_nml:
        raise ValueError("expected unchanged direct-QV real configuration")
    if "sfcp_to_sfcp                        = .true." not in original_nml:
        raise ValueError("expected retained sfcp_to_sfcp physics/configuration")
    if "mp_physics                          = 37," not in original_nml:
        raise ValueError("unexpected microphysics selection")
    if not re.search(r"^\s*max_dom\s*=\s*1\s*,", original_nml, flags=re.IGNORECASE | re.MULTILINE):
        raise ValueError("same13 prior path is restricted to its declared single domain")
    for flag, rejected in (("restart", {".true.", "1"}),
                           ("cycling", {".true.", "1"}),
                           ("dfi_opt", {"1", "2", "3", "4"})):
        configured = re.findall(rf"^\s*{flag}\s*=\s*([^,\s]+)", original_nml,
                                flags=re.IGNORECASE | re.MULTILINE)
        if any(value.lower() in rejected for value in configured):
            raise ValueError(f"same13 prior path does not cover enabled {flag}")
    cold_start_scope_guard = {
        "status": "PASS",
        "source_namelist_sha256": source_namelist_sha256,
        "max_dom": 1,
        "restart": "disabled; no enabled assignment in source namelist; source-bound WRF default",
        "cycling": "disabled; no enabled assignment in source namelist; source-bound WRF default",
        "dfi_opt": "disabled; no enabled assignment in source namelist; source-bound WRF default",
        "scope": "single-domain same13 cold-start; no restart/nesting/cycling/DFI extension",
    }
    if cold_start_scope_guard["source_namelist_sha256"] != EXPECTED_OFF_SOURCE_NAMELIST_SHA256:
        raise AssertionError("validated MODE_OFF source namelist identity changed")

    run_dir.mkdir(parents=True)
    # Copy only runtime tables and static inputs. Replace all date-bound files
    # with the genuine same-13 real.exe products and the declared nml.
    excluded = {
        "wrfinput_d01", "wrfbdy_d01", "namelist.input", "namelist.output",
        "namelist.input.original", "namelist.input.source", "wrf.exe", "rsl.error.0000", "rsl.out.0000",
        "candidate_run.log",
    }
    excluded_prefixes = ("wrfout", "wrfrst", "wrfdiag")
    trace_outputs = {
        "kdm6_first_call_pre.raw", "kdm6_first_call_post.raw", "pr63_geometry.raw", "pr63_transition_masks.bin",
        "pr63_transition_stages.raw", "pr64_host_neighborhood.raw", "pr64_qc_channels.raw",
        "pr65_nc_donor_faces.raw", "pr65_pbl_nc.raw", "pr65_pbl_operator.raw",
        "pr74_qni_driver.raw", "pr76_target_call.raw", "pr76_thread_entry.raw",
        "pr77_host_fp.raw", "pr77_native_species.raw", "stdout.raw",
    }
    source_snapshot: dict[str, str] = {}
    for source in sorted(runtime.iterdir()):
        if (not source.is_file() or source.name in excluded or source.name in trace_outputs
                or source.name.startswith(excluded_prefixes)):
            continue
        source_snapshot[source.name] = sha256(source)
        copy_detached_input(source, run_dir / source.name)
    copied_hashes = {
        path.name: sha256(path) for path in sorted(run_dir.iterdir()) if path.is_file()
    }
    if copied_hashes != source_snapshot:
        raise AssertionError("detached static runtime copy differs from retained source")
    wrfinput_source = real_case / "wrfinput_d01"
    prior_receipt_path: Path | None = None
    prior_policy_path: Path | None = None
    prior_receipt: dict[str, object] | None = None
    prior_candidate_preflight: dict[str, object] | None = None
    if args.initialized_input_receipt is not None:
        if args.initialized_input_policy is None:
            raise ValueError("PR83 alternate input also requires its declared policy")
        prior_receipt_path = args.initialized_input_receipt.resolve(strict=True)
        prior_receipt = json.loads(prior_receipt_path.read_text())
        prior_policy_path = args.initialized_input_policy.resolve(strict=True)
        prior_policy = json.loads(prior_policy_path.read_text())
        if prior_receipt.get("schema") != "pr83_same13_native_moment_prior_receipt_v1":
            raise ValueError("alternate wrfinput requires a PR83 same13 moment-prior receipt")
        if prior_receipt.get("status") != "RESEARCH_PRIOR_CREATED":
            raise ValueError("alternate wrfinput receipt is not a completed prior")
        if prior_receipt.get("source_input_sha256") != sha256(wrfinput_source):
            raise ValueError("PR83 prior receipt is not bound to this same13 real input")
        if Path(prior_receipt["source_input"]).resolve(strict=True) != wrfinput_source.resolve(strict=True):
            raise ValueError("PR83 prior receipt source path differs from this same13 real input")
        if prior_receipt.get("policy_id") != prior_policy.get("policy_id"):
            raise ValueError("PR83 prior receipt names a different policy")
        if prior_receipt.get("policy_sha256") != sha256(prior_policy_path):
            raise ValueError("PR83 prior receipt policy hash differs from the declared policy")
        wrfinput_source = Path(prior_receipt["output_input"]).resolve(strict=True)
        if sha256(wrfinput_source) != prior_receipt.get("output_input_sha256"):
            raise ValueError("PR83 prior input hash differs from its receipt")
        if prior_receipt.get("all_other_variables_unchanged") is not True:
            raise ValueError("PR83 prior receipt does not prove nonmoment field preservation")
        if prior_receipt.get("changed_nonmoment_variables") != []:
            raise ValueError("PR83 prior changed nonmoment fields")
        field_receipts = prior_receipt.get("field_prior_receipts")
        if not isinstance(field_receipts, dict) or set(field_receipts) != {
            "QNCLOUD", "QNICE", "QNRAIN", "QIB"
        }:
            raise ValueError("PR83 prior receipt does not cover every declared Q/N/B field")
        for name, result in field_receipts.items():
            if (not isinstance(result, dict)
                    or result.get("positive_mass_without_representable_moment") != 0):
                raise ValueError(f"PR83 prior receipt leaves unresolved positive mass: {name}")
        from pr83_moment_candidate_readback import validate_candidate_input

        prior_candidate_preflight = validate_candidate_input(
            real_case / "wrfinput_d01", wrfinput_source,
            prior_receipt_path, prior_policy_path,
        )
    candidate_inputs = {
        "wrfinput_d01": wrfinput_source,
        "wrfbdy_d01": real_case / "wrfbdy_d01",
        "wrf.exe": executable,
    }
    for name, source in candidate_inputs.items():
        copy_detached_input(source, run_dir / name)
    write_new(run_dir / "namelist.input", effective_nml.encode())
    write_new(run_dir / "namelist.input.source", original_nml.encode())

    if prior_receipt_path is None and sha256(run_dir / "wrfinput_d01") != "6ed69cbd2bdb8d128dbd7273ac8de216fe4537748a0e4ca474213ac408060730":
        raise ValueError("same13 MODE_OFF real wrfinput hash differs from this runner pin")
    if sha256(run_dir / "wrfbdy_d01") != "885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7":
        raise ValueError("same-13 real wrfbdy hash differs from reviewed artifact")

    inputs = [path for path in sorted(run_dir.iterdir()) if path.is_file()]
    outputs = ["wrfout_d01_2026-08-16_13:00:00", "rsl.error.0000", "rsl.out.0000",
               "candidate_run.log", "namelist.output"]
    source_provenance_paths = provenance_paths(prior_policy_path)
    provenance_before = {name: sha256(path) for name, path in source_provenance_paths.items()}
    source_candidate_hashes = {name: sha256(path) for name, path in candidate_inputs.items()}
    runtime_setup = (
        '. /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh --force '
        '>/dev/null 2>&1; '
        '. /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh '
        '>/dev/null 2>&1; '
        'export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE; '
        'export LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:${LD_LIBRARY_PATH:-}; '
        'ulimit -s unlimited; ./wrf.exe > candidate_run.log 2>&1'
    )
    run_result = run_isolated(
        run_dir, inputs, outputs,
        ["/bin/bash", "-c", runtime_setup],
        reserved_outputs=sorted(trace_outputs),
    )
    record: dict[str, object] = {
        "schema": ("pr83_same13_native_initialization_v1" if prior_receipt_path is not None
                   else "pr83_same13_off_native_initialization_v1"),
        "artifact_class": "RESEARCH_DIAGNOSTIC",
        "science_authority": "NONE",
        "operational_authority": "NONE",
        "native_runtime_case": str(runtime),
        "native_executable": str(executable),
        "native_executable_sha256": sha256(executable),
        "intel_setvars_sha256": sha256(Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh")),
        "mpi_vars_sha256": sha256(Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh")),
        "wrf_static_runtime_library": "/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib",
        "native_source_component": "retained PR81 nine-object WRF v4.8 diagnostic build; not the WRF v4.6 real.exe",
        "candidate_real_directory": str(real_case),
        "initialization_control": "MODE_OFF mass-only native control; no PR83 moment prior was applied",
        "moment_prior_status": "NOT_APPLIED",
        "native_off_chain_sources": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in OFF_CHAIN_ARTIFACTS.items()
        },
        "candidate_input_prior_receipt": str(prior_receipt_path) if prior_receipt_path else None,
        "candidate_input_prior_receipt_sha256": sha256(prior_receipt_path) if prior_receipt_path else None,
        "candidate_input_prior_status": prior_receipt.get("status") if prior_receipt_path else None,
        "candidate_input_prelaunch_validation": prior_candidate_preflight,
        "candidate_wrfinput_sha256": sha256(run_dir / "wrfinput_d01"),
        "candidate_wrfbdy_sha256": sha256(run_dir / "wrfbdy_d01"),
        "wrfinput_time": "2026-08-16_13:00:00",
        "wrfbdy_authority": "genuine retained legacy boundary states at 13, 14, 15 UTC; candidate science identity is only at 13 UTC",
        "boundary_source_contains_12_utc": False,
        "native_namelist_source_sha256": sha256(real_case / "namelist.input"),
        "cold_start_scope_guard": cold_start_scope_guard,
        "native_namelist_effective_sha256": sha256(run_dir / "namelist.input"),
        "native_namelist_change": {
            "run_seconds": {"source": "0", "effective": "20", "purpose": "enter one existing native initialization/first-step interval"},
            "time_control_start": "retained 2026-08-16 13:00:00",
            "time_control_end": {"source": "2026-08-16 15:00:00", "effective": "2026-08-16 13:00:20"},
            "interval_seconds": "preserved from real.exe 13-15 detached config",
            "physics_and_use_sh_qv_sfcp_to_sfcp": "preserved",
            "use_input_w": "not set in namelist; inherited source default retained",
        },
        "static_runtime_source_hashes": source_snapshot,
        "runner_and_runtime_source_hashes_before": provenance_before,
        "candidate_input_source_hashes_before": source_candidate_hashes,
        "run_isolation": run_result,
    }
    output_path = run_dir / "wrfout_d01_2026-08-16_13:00:00"
    if output_path.is_file():
        check = subprocess.run(
            [sys.executable, str(ROOT / "tools/check_native_hybrid_geometry.py"),
             str(output_path), "--initial-input", str(run_dir / "wrfinput_d01"),
             "--gravity", "9.81"],
            capture_output=True, text=True, check=False,
        )
        record["initial_wrfo_readback_exit_status"] = check.returncode
        if check.returncode == 0:
            record["initial_wrfo_readback"] = json.loads(check.stdout)
        else:
            record["initial_wrfo_readback_error"] = check.stderr.strip()
        record["initial_wrfo_sha256"] = sha256(output_path)
        if check.returncode == 0:
            with netCDF4.Dataset(run_dir / "wrfinput_d01") as initial_input, \
                    netCDF4.Dataset(output_path) as initial_output:
                physical = {}
                for name in ("QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP"):
                    values = np.asarray(initial_input.variables[name][:], dtype=np.float32)
                    physical[name] = {
                        "min": float(values.min()), "max": float(values.max()),
                        "positive_cells": int(np.count_nonzero(values > 0)),
                        "zero_cells": int(np.count_nonzero(values == 0)),
                        "units": getattr(initial_input.variables[name], "units", None),
                    }
                number_moments = {}
                for name in sorted(key for key in initial_input.variables if key.startswith("QN")):
                    values = np.asarray(initial_input.variables[name][:], dtype=np.float32)
                    number_moments[name] = {
                        "min": float(values.min()), "max": float(values.max()),
                        "positive_cells": int(np.count_nonzero(values > 0)),
                        "zero_cells": int(np.count_nonzero(values == 0)),
                        "units": getattr(initial_input.variables[name], "units", None),
                    }
                record["same13_input_hydromass_and_number_moments"] = {
                    "positive_mass_and_zero_numbers_are_not_a_microphysics_pass": (
                        prior_receipt_path is None
                    ),
                    "hydromass_fields": physical,
                    "available_number_moment_fields": number_moments,
                    "initial_wrfo_hydromass_matches_input": all(
                        np.array_equal(initial_input[name][:], initial_output[name][:])
                        for name in physical
                    ),
                    "initial_wrfo_number_moments_match_input": all(
                        np.array_equal(initial_input[name][:], initial_output[name][:])
                        for name in number_moments
                    ),
                }
    else:
        record["initial_wrfo_readback_exit_status"] = None
        record["initial_wrfo_readback_error"] = "initial-time wrfout was not produced"

    log_path = run_dir / "candidate_run.log"
    log_tail = log_path.read_text(errors="replace")[-12000:] if log_path.exists() else ""
    rsl_error = run_dir / "rsl.error.0000"
    rsl_text = rsl_error.read_text(errors="replace") if rsl_error.exists() else ""
    provenance_after = {name: sha256(path) for name, path in source_provenance_paths.items()}
    candidate_hashes_after = {name: sha256(path) for name, path in candidate_inputs.items()}
    source_runtime_after = {name: sha256(runtime / name) for name in source_snapshot}
    record["runner_and_runtime_source_hashes_after"] = provenance_after
    record["candidate_input_source_hashes_after"] = candidate_hashes_after
    record["static_runtime_source_hashes_after"] = source_runtime_after
    record["sources_unchanged"] = (
        provenance_before == provenance_after
        and source_candidate_hashes == candidate_hashes_after
        and source_snapshot == source_runtime_after
    )
    isolated_ok = (run_result["input_integrity"] == "PASS"
                   and run_result["output_isolation"] == "PASS")
    record["initialization_gate"] = (
        "PASS_SCOPED_INITIALIZATION_READBACK"
        if record["initial_wrfo_readback_exit_status"] == 0 and isolated_ok and record["sources_unchanged"]
        else "FAIL"
    )
    if "KDM6 unsupported positive mass without number/volume state" in rsl_text:
        record["first_step_gate"] = "REJECTED_KDM6_UNSUPPORTED_NUMBER_BASIS"
        record["first_step_rejection"] = "KDM6 unsupported positive mass without number/volume state"
    elif run_result["returncode"] == 0:
        completed = any(marker in rsl_text for marker in
                        ("SUCCESS COMPLETE WRF", "SUCCESS COMPLETE REAL-TIME WRF"))
        record["first_step_gate"] = "PASS" if completed else "UNASSESSED_NO_COMPLETION_MARKER"
    else:
        record["first_step_gate"] = "REJECTED_OR_ABORTED"
    record["rsl_error_sha256"] = sha256(rsl_error) if rsl_error.exists() else None
    record["rsl_error_last_lines"] = rsl_text.splitlines()[-20:]
    record["run_log_tail"] = log_tail
    record["native_trace_outputs"] = {
        name: {"sha256": sha256(run_dir / name), "bytes": (run_dir / name).stat().st_size}
        for name in sorted(trace_outputs) if (run_dir / name).is_file() and not (run_dir / name).is_symlink()
    }
    for name in trace_outputs:
        trace_path = run_dir / name
        if trace_path.exists() or trace_path.is_symlink():
            info = trace_path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                record["native_trace_output_issues"] = [f"trace output is not a detached regular file: {name}"]
    record["native_trace_output_issues"] = record.get("native_trace_output_issues", [])
    record["native_trace_output_integrity"] = "PASS" if not record["native_trace_output_issues"] else "FAIL"
    if record["native_trace_output_integrity"] != "PASS":
        record["initialization_gate"] = "FAIL"
    species_path = run_dir / "pr77_native_species.raw"
    if species_path.is_file() and not species_path.is_symlink():
        lines = species_path.read_text(errors="replace").splitlines()
        record["first_native_species_observer"] = {
            "sha256": sha256(species_path), "bytes": species_path.stat().st_size,
            "first_line": lines[0] if lines else None,
            "counts_line": next((line for line in lines if line.startswith("PR77_COUNTS,")), None),
            "scope": "first KDM6 diagnostic observation; not a native moment initialization or acceptance gate",
        }
    record_path = run_dir / "pr83_same13_off_native_initialization.json"
    write_new(record_path, (json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
    print(json.dumps({
        "run_dir": str(run_dir), "initialization_gate": record["initialization_gate"],
        "first_step_gate": record["first_step_gate"],
        "native_returncode": run_result["returncode"],
        "wrfout_sha256": record.get("initial_wrfo_sha256"),
        "receipt": str(record_path),
    }, sort_keys=True))
    return 0 if record["initialization_gate"] == "PASS_SCOPED_INITIALIZATION_READBACK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
