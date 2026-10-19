#!/usr/bin/env python3
"""Parse and source-bind one native PR90 rain-store failure, then replay it."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

HEADER = re.compile(
    r"^\s*PR90_RAIN_FAILURE stages=(\d+)\s+(-?\d+)\s+([a-z_]+)\s+"
    r"((?:[0-9a-fA-F]{8}\s+){6}[0-9a-fA-F]{8})\s*$",
    re.MULTILINE,
)
DERIVED = re.compile(
    r"^\s*PR90_RAIN_FAILURE_DERIVED_HEX\s+"
    r"((?:[0-9a-fA-F]{16}\s*)+)\s*$",
    re.MULTILINE,
)
CALLER = re.compile(r"^\s*PR87_RAIN_PUBLIC_STORE_REJECT\s+(.+?)\s*$", re.MULTILINE)
HEX32 = re.compile(r"^[0-9a-fA-F]{8}$")
HEX64 = re.compile(r"^[0-9a-fA-F]{16}$")
REAL_TOKEN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?$")


class ReplayError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def parse_capture(text: str, derived_count: int) -> dict[str, Any]:
    headers = list(HEADER.finditer(text))
    derived = list(DERIVED.finditer(text))
    callers = list(CALLER.finditer(text))
    if len(headers) != 1:
        raise ReplayError(f"expected exactly one PR90 failure header, found {len(headers)}")
    if len(derived) != 1:
        raise ReplayError(f"expected exactly one derived HEX record, found {len(derived)}")
    if len(callers) != 1:
        raise ReplayError(f"expected exactly one legacy caller index line, found {len(callers)}")

    header = headers[0]
    derived_match = derived[0]
    if derived_match.start() < header.end():
        raise ReplayError("derived HEX record must follow the failure header")
    input_hex = header.group(4).split()
    derived_hex = derived_match.group(1).split()
    if len(input_hex) != 7 or not all(HEX32.fullmatch(value) for value in input_hex):
        raise ReplayError("failure input HEX record is malformed or truncated")
    if len(derived_hex) != derived_count or not all(HEX64.fullmatch(value) for value in derived_hex):
        raise ReplayError(f"derived HEX record must contain {derived_count} complete REAL64 words")

    caller_tokens = callers[0].group(1).split()
    if len(caller_tokens) == 4:
        next_line = text[callers[0].end():].lstrip("\r\n").splitlines()
        if not next_line:
            raise ReplayError("legacy caller numeric continuation is missing")
        caller_tokens.extend(next_line[0].split())
    if len(caller_tokens) != 7:
        raise ReplayError("legacy caller record must contain timestep, j/i/k, and Q/N/rho")
    try:
        timestep, j, i, k = map(int, caller_tokens[:4])
    except ValueError as exc:
        raise ReplayError("legacy caller indices are malformed") from exc
    if any(not REAL_TOKEN.fullmatch(value) for value in caller_tokens[4:]):
        raise ReplayError("legacy caller Q/N/rho fields are malformed")

    return {
        "helper_stage": int(header.group(1)),
        "core_stage": int(header.group(2)),
        "reason": header.group(3),
        "input_hex": dict(zip(
            ("q_internal", "nvol_internal", "dry_density", "pidnr", "power", "lambda_min", "lambda_max"),
            (value.upper() for value in input_hex),
        )),
        "derived_hex": [value.upper() for value in derived_hex],
        "caller": {
            "timestep": timestep, "j": j, "i": i, "k": k,
            "printed_values": caller_tokens[4:],
        },
    }


def read_capture(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    content = gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw
    return content.decode("utf-8", errors="strict"), sha256_bytes(raw)


def verify_provenance(preflight_path: Path, build_path: Path, run_receipt_path: Path,
                      capture_path: Path, capture_raw_sha256: str) -> dict[str, Any]:
    preflight_bytes = preflight_path.read_bytes()
    build_bytes = build_path.read_bytes()
    run_bytes = run_receipt_path.read_bytes()
    preflight = json.loads(preflight_bytes)
    build = json.loads(build_bytes)
    run_receipt = json.loads(run_bytes)
    if run_receipt.get("status") in (None, "RUNNING", "OPEN"):
        raise ReplayError("native run receipt is not closed")
    if not isinstance(run_receipt.get("wall_seconds"), (int, float)) or run_receipt["wall_seconds"] <= 0:
        raise ReplayError("closed native run receipt lacks a positive duration")
    if not isinstance(run_receipt.get("returncode"), int):
        raise ReplayError("closed native run receipt lacks an exit status")
    expected_build_sha = preflight["candidate_build"]["receipt_sha256"]
    if sha256_bytes(build_bytes) != expected_build_sha:
        raise ReplayError("candidate build receipt hash does not match preflight")
    candidate = preflight["candidate_build"]
    if candidate["executable_sha256"] != build["executable_sha256"]:
        raise ReplayError("preflight and build receipt executable hashes differ")
    run_build = run_receipt.get("candidate_build", {})
    if (run_build.get("receipt_path") != str(build_path) or
            run_build.get("receipt_sha256") != expected_build_sha):
        raise ReplayError("closed run receipt does not bind the candidate build receipt")
    if run_receipt.get("expected_executed_executable_sha256") != build["executable_sha256"]:
        raise ReplayError("closed run receipt executable identity differs from candidate build")
    if run_receipt.get("executed_executable_sha256") != build["executable_sha256"]:
        raise ReplayError("closed run receipt does not confirm the candidate executable ran")
    if run_receipt.get("source_receipt_sha256") != preflight.get("source_receipt_sha256"):
        raise ReplayError("closed run and preflight source receipt hashes differ")
    output_entries = run_receipt.get("generated_files", []) + run_receipt.get("compressed_outputs", [])
    capture_matches = [entry for entry in output_entries
                       if entry.get("sha256") == capture_raw_sha256]
    if len(capture_matches) != 1:
        raise ReplayError("closed run receipt does not uniquely bind the captured stdout/member hash")
    capture_entry = capture_matches[0]
    expected_name = capture_entry.get("path")
    if expected_name and capture_path.name != expected_name:
        raise ReplayError("capture filename does not match its closed run receipt artifact")
    executable = Path(build["executable_path"])
    if sha256_file(executable) != build["executable_sha256"]:
        raise ReplayError("candidate executable hash changed after native run")
    profile = Path(build["compiler_profile_path"])
    if sha256_file(profile) != build["compiler_profile_sha256"]:
        raise ReplayError("pinned Intel profile hash changed")

    required_sources: dict[str, tuple[Path, str]] = {}
    for object_name in ("module_em.o", "module_mp_kdm6.o"):
        entry = build["source_overrides"][object_name]
        required_sources[object_name] = (Path(entry["staged_path"]), entry["staged_sha256"])
    support = build["extra_observer"]
    required_sources["support"] = (Path(support["source_path"]), support["source_sha256"])
    source_rows: dict[str, dict[str, str]] = {}
    for name, (path, expected) in required_sources.items():
        actual = sha256_file(path)
        if actual != expected:
            raise ReplayError(f"compiled source hash mismatch for {name}: {path}")
        source_rows[name] = {"path": str(path), "sha256": actual}
    support_text = required_sources["support"][0].read_text()
    diagnostic_proc = extract_fortran_block(
        support_text, "subroutine", "pr90_rain_public_store_diagnostic"
    )
    diagnostic_shape = re.search(
        r"real\(real64\)\s*,\s*intent\(out\)\s*::\s*diagnostic\((\d+)\)",
        diagnostic_proc, re.I,
    )
    if not diagnostic_shape:
        raise ReplayError("compiled diagnostic support lacks a declared diagnostic array size")
    kdm_text = required_sources["module_mp_kdm6.o"][0].read_text()
    legacy_scalar_conversion = "call volume_number_to_specific(nrs(i,k,1), dry_density(i,k), number_value, number_valid)"
    public_store_call = "call pr87_number_public_store(qrs(i,k,1),nrs(i,k,1),dry_density(i,k), &"
    if legacy_scalar_conversion not in kdm_text or public_store_call not in kdm_text or \
            kdm_text.index(legacy_scalar_conversion) > kdm_text.index(public_store_call):
        raise ReplayError("compiled KDM6 source does not prove wrapper scalar conversion precedes rain store")

    return {
        "preflight": {"path": str(preflight_path), "sha256": sha256_bytes(preflight_bytes)},
        "build_receipt": {"path": str(build_path), "sha256": sha256_bytes(build_bytes)},
        "closed_run_receipt": {"path": str(run_receipt_path), "sha256": sha256_bytes(run_bytes),
                               "status": run_receipt.get("status"),
                               "returncode": run_receipt.get("returncode"),
                               "wall_seconds": run_receipt.get("wall_seconds"),
                               "capture_artifact": capture_entry},
        "candidate_executable": {"path": str(executable), "sha256": build["executable_sha256"]},
        "compiler_profile": {"path": str(profile), "sha256": build["compiler_profile_sha256"]},
        "compiled_sources": source_rows,
        "diagnostic_count": int(diagnostic_shape.group(1)),
        "wrapper_ordering": {
            "legacy_scalar_conversion": legacy_scalar_conversion,
            "rain_public_store_call": public_store_call,
            "scalar_conversion_precedes_store": True,
        },
    }


def extract_fortran_block(source: str, kind: str, name: str) -> str:
    start = re.search(rf"(?im)^\s*(?:(?:pure|recursive)\s+)?{kind}\s+{re.escape(name)}\s*\(", source)
    if not start:
        raise ReplayError(f"could not find compiled Fortran {kind} {name}")
    end = re.search(rf"(?im)^\s*end\s+{kind}\s+{re.escape(name)}\s*$", source[start.start():])
    if not end:
        raise ReplayError(f"unterminated compiled Fortran {kind} {name}")
    return source[start.start():start.start() + end.end()].strip()


def extract_core_module(source: str) -> str:
    start = re.search(r"(?im)^\s*module\s+cloud_bal_joint_transport\s*$", source)
    if not start:
        raise ReplayError("compiled override lacks cloud_bal_joint_transport")
    end = re.search(r"(?im)^\s*end\s+module\s+cloud_bal_joint_transport\s*$", source[start.start():])
    if not end:
        raise ReplayError("compiled cloud_bal_joint_transport is unterminated")
    return source[start.start():start.start() + end.end()].strip()


def make_harness(capture: dict[str, Any], consumer: str, diagnostic_count: int) -> str:
    bits = capture["input_hex"]
    decls = "\n".join(
        f"  {name}=transfer(int(z'{bits[name]}',int32),0.0_real32)"
        for name in ("q_internal", "nvol_internal", "dry_density", "pidnr", "power", "lambda_min", "lambda_max")
    )
    diag_values = ", &\n      ".join(f"transfer(diagnostic({i}),0_int64)" for i in range(1, diagnostic_count + 1))
    return f"""program pr90_failure_replay
  use iso_fortran_env, only: real32,real64,int32,int64
  use pr90_replay_consumer, only: kdm6_rain_ng_pair_valid
  implicit none
  real(real32) :: q_internal,nvol_internal,dry_density,pidnr,power,lambda_min,lambda_max
  real(real32) :: q_public,n_specific,q_restored,nvol_restored
  real(real64) :: delta_q,delta_n,delta_q_back,delta_nvol_back,diagnostic({diagnostic_count})
  real(real64) :: rain_min,rain_max
  integer :: adjustment,helper_stage,core_stage,adjustment_back,consumer_reason
  logical :: valid,restored,consumer_valid
  character(len=32) :: reason
  external :: pr90_rain_public_store_diagnostic,pr87_number_volume_store
{decls}
  diagnostic=0.0_real64
  call pr90_rain_public_store_diagnostic(q_internal,nvol_internal,dry_density,pidnr,power, &
      lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n,adjustment, &
      reason,diagnostic,helper_stage,core_stage)
  restored=.false.; consumer_valid=.false.; consumer_reason=-1
  q_restored=-1.0_real32; nvol_restored=-1.0_real32
  if (valid) then
    call pr87_number_volume_store(q_public,n_specific,dry_density,pidnr,power, &
        lambda_min,lambda_max,q_restored,nvol_restored,restored,delta_q_back, &
        delta_nvol_back,adjustment_back)
    if (restored) then
      rain_min=real(dry_density,real64)*real(lambda_min,real64)**real(power,real64)/real(pidnr,real64)
      rain_max=real(dry_density,real64)*real(lambda_max,real64)**real(power,real64)/real(pidnr,real64)
      call kdm6_rain_ng_pair_valid(q_restored,nvol_restored,rain_min,rain_max,.true.,.true., &
          consumer_valid,consumer_reason)
    endif
  endif
  write(*,'(A,2(I0,1X),A,1X,L1,1X,4(Z8.8,1X),2(L1,1X),I0)') &
      'PR90_REPLAY ',helper_stage,core_stage,trim(reason),valid, &
      transfer(q_public,0_int32),transfer(n_specific,0_int32), &
      transfer(q_restored,0_int32),transfer(nvol_restored,0_int32), &
      restored,consumer_valid,consumer_reason
  write(*,'(A,{diagnostic_count}(1X,Z16.16))') 'PR90_REPLAY_DIAGNOSTIC_HEX', &
      {diag_values}
end program pr90_failure_replay
"""


def parse_replay_output(text: str, diagnostic_count: int) -> dict[str, Any]:
    status_lines = [line.split() for line in text.splitlines() if line.startswith("PR90_REPLAY ")]
    diagnostic_lines = [line.split() for line in text.splitlines()
                        if line.startswith("PR90_REPLAY_DIAGNOSTIC_HEX")]
    if len(status_lines) != 1 or len(diagnostic_lines) != 1:
        raise ReplayError("source replay output is malformed or duplicated")
    status = status_lines[0]
    diagnostic = diagnostic_lines[0]
    if len(status) != 12 or len(diagnostic) != diagnostic_count + 1:
        raise ReplayError("source replay output is truncated")
    if not all(HEX32.fullmatch(value) for value in status[5:9]):
        raise ReplayError("source replay REAL32 result bits are malformed")
    if not all(HEX64.fullmatch(value) for value in diagnostic[1:]):
        raise ReplayError("source replay diagnostic bits are malformed")
    if status[4] not in ("T", "F") or status[9] not in ("T", "F") or status[10] not in ("T", "F"):
        raise ReplayError("source replay logical fields are malformed")
    return {
        "helper_stage": int(status[1]), "core_stage": int(status[2]),
        "reason": status[3], "public_store_valid": status[4] == "T",
        "result_hex": {"q_public": status[5], "n_specific": status[6],
                       "q_restored": status[7], "nvol_restored": status[8]},
        "roundtrip_executed": status[9] == "T",
        "consumer_executed": status[9] == "T",
        "consumer_valid": status[10] == "T" and int(status[11]) == 0,
        "consumer_reason": int(status[11]),
        "diagnostic_hex": diagnostic[1:],
    }


def run_replay(capture: dict[str, Any], provenance: dict[str, Any], profile: str) -> dict[str, Any]:
    build_path = Path(provenance["build_receipt"]["path"])
    build = json.loads(build_path.read_text())
    source_core = Path(build["source_overrides"]["module_em.o"]["staged_path"]).read_text()
    source_kdm = Path(build["source_overrides"]["module_mp_kdm6.o"]["staged_path"]).read_text()
    source_support = Path(build["extra_observer"]["source_path"]).read_text()
    core = extract_core_module(source_core)
    diagnostic = extract_fortran_block(source_support, "subroutine", "pr90_rain_public_store_diagnostic")
    number_volume = extract_fortran_block(source_support, "subroutine", "pr87_number_volume_store")
    consumer = extract_fortran_block(source_kdm, "subroutine", "kdm6_rain_ng_pair_valid")
    consumer_module = ("module pr90_replay_consumer\n"
                       "  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite\n"
                       "contains\n" + consumer + "\nend module pr90_replay_consumer\n")
    scratch = Path(tempfile.mkdtemp(prefix=f"pr90_failure_replay_{profile}_", dir="/var/tmp"))
    (scratch / "core.f90").write_text(core)
    (scratch / "support.f90").write_text(diagnostic + "\n\n" + number_volume)
    (scratch / "consumer.f90").write_text(consumer_module)
    diagnostic_count = provenance["diagnostic_count"]
    (scratch / "harness.f90").write_text(make_harness(capture, consumer, diagnostic_count))
    command = [
        "bash", "-c",
        'source "$1/tests/intel_toolchain.sh" && '
        'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
        'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
        '"$CLOUD_BAL_FC" "${flags[@]}" -free -module "$3" -I "$3" '
        '"$3/core.f90" "$3/support.f90" "$3/consumer.f90" "$3/harness.f90" '
        '-o "$3/replay.exe" && "$3/replay.exe"',
        "pr90-replay", str(Path(build["compiler_profile_path"]).parents[1]), profile, str(scratch),
    ]
    # The toolchain script is under Cloud-BAL/tests; pass the repository root separately.
    command[4] = str(Path(build["compiler_profile_path"]).parents[1])
    result = subprocess.run(command, cwd=scratch, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise ReplayError(f"{profile} source-bound replay failed:\n{result.stdout}")
    replayed = parse_replay_output(result.stdout, diagnostic_count)
    replayed["profile"] = profile
    replayed["scratch"] = str(scratch)
    replayed["stdout"] = result.stdout.strip()
    replayed["stdout_sha256"] = sha256_bytes(result.stdout.encode())
    replayed["matches_native_failure"] = (
        replayed["helper_stage"] == capture["helper_stage"] and
        replayed["core_stage"] == capture["core_stage"] and
        replayed["reason"] == capture["reason"] and
        replayed["diagnostic_hex"][:len(capture["derived_hex"])] == capture["derived_hex"]
    )
    return replayed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True, help="closed native stdout or compressed stdout")
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--run-receipt", type=Path, required=True, help="closed native run receipt")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-replay", action="store_true", help="parse and bind without compiling replay")
    args = parser.parse_args()
    try:
        capture_text, capture_sha = read_capture(args.capture)
        provenance = verify_provenance(args.preflight, args.build_receipt, args.run_receipt,
                                       args.capture, capture_sha)
        event = parse_capture(capture_text, provenance["diagnostic_count"])
        result: dict[str, Any] = {
            "schema": "pr90_rain_failure_replay_v1",
            "capture": {"path": str(args.capture), "raw_sha256": capture_sha,
                        "decoded_sha256": sha256_bytes(capture_text.encode())},
            "event": event,
            "stage_trace": {
                "initial_internal_volume_predicate": (
                    "failed" if event["reason"] == "internal_volume_precheck" else
                    "passed" if event["helper_stage"] >= 5 else "not_reached"
                ),
                "wrapper_prior_scalar_conversion": "completed",
                "main_path_internal_quotient": (
                    "computed" if event["helper_stage"] >= 5 else "not_reached"
                ),
                "failure_probe_internal_quotient": (
                    "computed" if event["reason"] == "internal_volume_precheck" else "not_recorded"
                ),
                "public_store": "attempted" if event["helper_stage"] >= 6 else "not_reached",
                "restore": "not_executed_until_public_store_valid",
                "consumer": "not_executed_until_restore_valid",
            },
            "provenance": provenance,
            "replays": [],
        }
        if not args.no_replay:
            result["replays"] = [run_replay(event, provenance, profile) for profile in ("O0", "O2")]
            for replay in result["replays"]:
                replay["stage_trace"] = {
                    "initial_internal_volume_predicate": (
                        "failed" if replay["reason"] == "internal_volume_precheck" else
                        "passed" if replay["helper_stage"] >= 5 else "not_reached"
                    ),
                    "wrapper_prior_scalar_conversion": "completed",
                    "main_path_internal_quotient": (
                        "computed" if replay["helper_stage"] >= 5 else "not_reached"
                    ),
                    "failure_probe_internal_quotient": (
                        "computed" if replay["reason"] == "internal_volume_precheck" else "not_recorded"
                    ),
                    "public_store": "attempted" if replay["helper_stage"] >= 6 else "not_reached",
                    "restore": "executed" if replay["roundtrip_executed"] else "not_executed",
                    "consumer": "executed" if replay["consumer_executed"] else "not_executed",
                }
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"output": str(args.output), "reason": event["reason"],
                          "helper_stage": event["helper_stage"], "replays": len(result["replays"])}, indent=2))
        return 0
    except (ReplayError, OSError, KeyError, json.JSONDecodeError, gzip.BadGzipFile) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
