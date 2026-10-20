#!/usr/bin/env python3
"""Replay receipt-closed C4 ice sedimentation captures through the exact helper."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shlex
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
HELPER = EVIDENCE / "c4_pr85_kdm6_paired_sediment_column.F90"
RECEIPT_LEDGER = "pr85_kdm6_psd_boundary.raw.gz"
TARGET = (230, 247, 24)
SOURCE_SHA256 = "b358064642d81c86ee1f914c52620ade2c7589ccf302dcffd26d25809fd5adaa"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_closed_audit(audit_path: Path) -> tuple[dict, Path, dict, Path]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("schema") != "pr93_closed_run_audit_v1":
        raise ValueError("input is not a closed-run audit")
    arm = str(audit.get("arm", "")).upper()
    if arm not in {"OFF", "COUPLED"}:
        raise ValueError("audit arm must be OFF or COUPLED")
    receipt_row = audit.get("receipt", {})
    if receipt_row.get("status") not in {"COMPLETE", "INCOMPLETE"}:
        raise ValueError("audit receipt is not collector-closed")
    receipt_path = Path(receipt_row["path"])
    if not receipt_path.is_file() or sha256(receipt_path) != receipt_row.get("sha256"):
        raise ValueError("closed receipt is missing or its audited hash differs")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("arm", "").upper() != arm or receipt.get("status") not in {"COMPLETE", "INCOMPLETE"}:
        raise ValueError("receipt contents do not match the closed audit")
    if ("snapshots" not in receipt or "compressed_outputs" not in receipt or
            "processing_errors" not in receipt):
        raise ValueError("receipt lacks collector-closed fields")
    if receipt["processing_errors"]:
        raise ValueError("collector recorded processing errors")
    if receipt.get("maximum_seen_timestep", 0) < TARGET[2]:
        raise ValueError("receipt did not observe target timestep 24")
    capture = audit.get("selected_ice_sedimentation_capture", {})
    if capture.get("status") == "NO_SELECTED_CAPTURE" or not capture.get("all_observed_pairs"):
        raise ValueError("closed audit has no selected before/after capture")
    entries = [row for row in receipt.get("compressed_outputs", [])
               if row.get("compressed_path") == RECEIPT_LEDGER]
    if len(entries) != 1:
        raise ValueError("receipt must bind exactly one selected ice PSD ledger")
    ledger_row = entries[0]
    required = {"path", "sha256", "bytes", "compressed_path", "compressed_sha256", "compressed_bytes"}
    if not required.issubset(ledger_row):
        raise ValueError("receipt ledger row is incomplete")
    generated_raw = [row for row in receipt.get("generated_files", [])
                     if row.get("path") == ledger_row["path"]]
    generated_compressed = [row for row in receipt.get("generated_files", [])
                            if row.get("path") == ledger_row["compressed_path"]]
    generated = generated_raw if generated_raw else generated_compressed
    expected_hash, expected_bytes = ((ledger_row["sha256"], ledger_row["bytes"])
                                     if generated_raw else
                                     (ledger_row["compressed_sha256"], ledger_row["compressed_bytes"]))
    if len(generated) != 1 or generated[0].get("sha256") != expected_hash or \
            generated[0].get("bytes") != expected_bytes:
        raise ValueError("ledger identity is not closed by generated_files receipt rows")
    run_root = receipt_path.parent / "run"
    ledger_path = run_root / ledger_row["compressed_path"]
    if not ledger_path.is_file():
        raise ValueError("receipt-bound compressed ledger is missing")
    return audit, receipt_path, ledger_row, ledger_path


def verify_ledger_hashes(row: dict, path: Path) -> dict:
    compressed_hash = sha256(path)
    compressed_bytes = path.stat().st_size
    if compressed_hash != row["compressed_sha256"] or compressed_bytes != row["compressed_bytes"]:
        raise ValueError("compressed ledger does not match closed receipt")
    expanded_hash = hashlib.sha256()
    expanded_bytes = 0
    with gzip.open(path, "rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            expanded_hash.update(block)
            expanded_bytes += len(block)
    if expanded_hash.hexdigest() != row["sha256"] or expanded_bytes != row["bytes"]:
        raise ValueError("expanded ledger does not match closed receipt")
    return {"compressed_sha256": compressed_hash, "compressed_bytes": compressed_bytes,
            "expanded_sha256": expanded_hash.hexdigest(), "expanded_bytes": expanded_bytes}


def selected_calls(path: Path) -> list[dict]:
    paired: dict[tuple[int, int, int], dict[int, dict[str, str]]] = {}
    pattern = re.compile(rb"^PR93_ICE_SED_(BEFORE|AFTER)\s+")
    with gzip.open(path, "rb") as stream:
        for raw in stream:
            if not pattern.match(raw):
                continue
            fields = raw.decode("ascii").split()
            if len(fields) != 15:
                raise ValueError("malformed C4 selected-column capture row")
            timestep, i, lat, loop, substep, mstep, k = map(int, fields[1:8])
            if (i, lat, timestep) != TARGET:
                continue
            row = {
                "loop": loop, "substep": substep, "mstep": mstep, "k": k,
                "q_hex": fields[8].upper(), "n_hex": fields[9].upper(),
                "rho_hex": fields[10].upper(), "delz": float(fields[11].replace("D", "E")),
                "mass_rate": float(fields[12].replace("D", "E")),
                "number_rate": float(fields[13].replace("D", "E")),
                "dt": float(fields[14].replace("D", "E")),
            }
            for name in ("delz", "dt"):
                packed = struct.pack(">f", row[name])
                if struct.unpack(">f", packed)[0] != row[name]:
                    raise ValueError(f"captured {name} is not an exact promoted REAL32 value")
            side = 0 if fields[0].endswith("BEFORE") else 1
            call = paired.setdefault((loop, substep, mstep), {})
            level = call.setdefault(k, {})
            if side in level:
                raise ValueError("duplicate before/after row for captured level")
            level[side] = row
    calls = []
    for key, levels_by_k in sorted(paired.items()):
        levels = sorted(levels_by_k)
        if len(levels) != 39 or levels != list(range(levels[0], levels[0] + 39)):
            raise ValueError(f"capture call {key} does not cover 39 contiguous levels")
        rows = []
        first_dt = None
        for k in levels:
            pair = levels_by_k[k]
            if set(pair) != {0, 1}:
                raise ValueError(f"capture call {key} has an unmatched level {k}")
            before, after = pair[0], pair[1]
            if any(before[field] != after[field] for field in ("rho_hex", "delz", "mass_rate", "number_rate", "dt")):
                raise ValueError(f"captured source operands changed across call for level {k}")
            if first_dt is None:
                first_dt = before["dt"]
            elif before["dt"] != first_dt:
                raise ValueError(f"captured timestep differs across levels in call {key}")
            rows.append({"before": before, "after": after})
        calls.append({"key": key, "kts": levels[0], "kte": levels[-1], "rows": rows})
    if not calls:
        raise ValueError("receipt-bound ledger contains no selected C4 target call")
    return calls


def verify_audit_pairs(audit: dict, calls: list[dict]) -> None:
    audited = audit["selected_ice_sedimentation_capture"].get("all_observed_pairs", [])
    audit_calls: dict[tuple[int, int, int], set[int]] = {}
    for pair in audited:
        key = tuple(map(int, pair["loop_substep_k"]))
        if len(key) != 4 or not pair.get("before_raw") or not pair.get("after_raw"):
            raise ValueError("audit contains an incomplete before/after capture pair")
        audit_calls.setdefault(key[:3], set()).add(key[3])
    ledger_calls = {call["key"] for call in calls}
    if set(audit_calls) != ledger_calls:
        raise ValueError("selected call keys differ between the closed audit and receipt-bound ledger")
    for call in calls:
        call_key = call["key"]
        levels = {row["before"]["k"] for row in call["rows"]}
        if audit_calls.get(call_key) != levels:
            raise ValueError(f"receipt-bound ledger call {call_key} differs from its closed audit capture")


def f64(value: float) -> str:
    return format(value, ".17g")


def generate_driver(calls: list[dict], path: Path) -> None:
    kts, kte, ncall = calls[0]["kts"], calls[0]["kte"], len(calls)
    if any((call["kts"], call["kte"]) != (kts, kte) for call in calls):
        raise ValueError("selected calls have different level bounds")
    rows = [
        "program replay_c4_ice_call",
        "  use, intrinsic :: iso_fortran_env, only: real32, real64, int32",
        "  implicit none",
        "  interface",
        "    subroutine pr85_kdm6_paired_sediment_column(kts,kte,cell_i,lat,substep,dt,mstep, &",
        "         dry_density,delz,mass_rate,second_rate,qstate,second_state,mode,q_active_min, &",
        "         second_active_min,density_min,density_max,approved_q_rate,approved_second_rate, &",
        "         budget_unit,trace,valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)",
        "      import real32, real64",
        "      integer, intent(in) :: kts,kte,cell_i,lat,substep,dt_dummy,mstep,budget_unit",
        "      real(real32), intent(in) :: dt,dry_density(kts:kte),delz(kts:kte)",
        "      real(real64), intent(in) :: mass_rate(kts:kte),second_rate(kts:kte)",
        "      real(real32), intent(inout) :: qstate(kts:kte),second_state(kts:kte)",
        "      integer, intent(in) :: mode",
        "      real(real32), intent(in) :: q_active_min,second_active_min,density_min,density_max",
        "      real(real64), intent(out) :: approved_q_rate(kts:kte),approved_second_rate(kts:kte)",
        "      logical, intent(in) :: trace",
        "      logical, intent(out) :: valid",
        "      real(real32), intent(in) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max",
        "    end subroutine pr85_kdm6_paired_sediment_column",
        "  end interface",
        f"  integer, parameter :: kts={kts}, kte={kte}, ncall={ncall}",
        "  integer :: c, k",
        "  real(real32) :: dt, rho(kts:kte), dz(kts:kte), q(kts:kte), n(kts:kte)",
        "  real(real64) :: mr(kts:kte), nr(kts:kte), qout(kts:kte), nout(kts:kte)",
        "  logical :: valid",
        "",
    ]
    # Keep the original source interface's declared kinds and argument order.
    rows[rows.index("      integer, intent(in) :: kts,kte,cell_i,lat,substep,dt_dummy,mstep,budget_unit")] = \
        "      integer, intent(in) :: kts,kte,cell_i,lat,substep,mstep,budget_unit"
    for call_index, call in enumerate(calls, start=1):
        loop, substep, mstep = call["key"]
        rows += [f"  ! source call {call_index}: loop={loop}, substep={substep}, mstep={mstep}"]
        for item in call["rows"]:
            before = item["before"]
            k = before["k"]
            rows.extend([
                f"  rho({k})=transfer(int(z'{before['rho_hex']}',int32),0.0_real32)",
                f"  dz({k})=real({f64(before['delz'])},real32)",
                f"  mr({k})={f64(before['mass_rate'])}_real64",
                f"  nr({k})={f64(before['number_rate'])}_real64",
            ])
        rows.append(f"  dt=real({f64(call['rows'][0]['before']['dt'])},real32)")
        for item in call["rows"]:
            before = item["before"]
            k = before["k"]
            rows.extend([
                f"  q({k})=transfer(int(z'{before['q_hex']}',int32),0.0_real32)",
                f"  n({k})=transfer(int(z'{before['n_hex']}',int32),0.0_real32)",
            ])
        rows.extend([
            f"  call pr85_kdm6_paired_sediment_column(kts,kte,230,247,{substep},dt,{mstep}, &",
            "       rho,dz,mr,nr,q,n,1,0.0_real32,0.0_real32,0.0_real32,0.0_real32, &",
            "       qout,nout,0,.false.,valid,0.0_real32,0.0_real32,0.0_real32,0.0_real32)",
            f"  write(*,'(a,1x,i0,1x,l1)') 'CALL', {call_index}, valid",
            "  do k=kts,kte",
            f"    write(*,'(a,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') 'STATE',{call_index},k, &",
            "         transfer(q(k),0_int32),transfer(n(k),0_int32)",
            "  enddo",
        ])
    rows += ["end program replay_c4_ice_call", ""]
    path.write_text("\n".join(rows), encoding="ascii")


def run_pinned(helper: Path, driver: Path, scratch: Path, profile: str) -> tuple[int, str]:
    executable = scratch / f"replay_{profile}"
    script = f"""set -euo pipefail
. {shlex.quote(str(ROOT / 'tests/intel_toolchain.sh'))}
if [[ {profile} == O0 ]]; then flags=(\"${{CLOUD_BAL_FREE_FLAGS[@]}}\"); else flags=(\"${{CLOUD_BAL_REPRO_FLAGS[@]}}\"); fi
\"$CLOUD_BAL_FC\" \"${{flags[@]}}\" -module {shlex.quote(str(scratch))} -I {shlex.quote(str(scratch))} {shlex.quote(str(helper))} {shlex.quote(str(driver))} -o {shlex.quote(str(executable))}
{shlex.quote(str(executable))}
"""
    result = subprocess.run(["bash", "-lc", script], text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    return result.returncode, result.stdout


def compare_output(output: str, calls: list[dict]) -> dict:
    actual: dict[tuple[int, int], tuple[str, str]] = {}
    valid: dict[int, bool] = {}
    for line in output.splitlines():
        fields = line.split()
        if fields and fields[0] == "CALL":
            valid[int(fields[1])] = fields[2].upper() == "T"
        elif fields and fields[0] == "STATE":
            actual[(int(fields[1]), int(fields[2]))] = (fields[3].upper(), fields[4].upper())
    mismatches = []
    for call_index, call in enumerate(calls, start=1):
        if valid.get(call_index) is not True:
            mismatches.append({"call": call_index, "reason": "helper_returned_invalid"})
        for item in call["rows"]:
            expected = item["after"]
            found = actual.get((call_index, expected["k"]))
            target = (expected["q_hex"], expected["n_hex"])
            if found != target:
                mismatches.append({"call": call_index, "k": expected["k"],
                                   "expected_after_bits": target, "actual_bits": found})
    expected_states = sum(len(call["rows"]) for call in calls)
    return {"call_count": len(calls), "expected_state_count": expected_states,
            "actual_state_count": len(actual), "mismatch_count": len(mismatches),
            "mismatches": mismatches[:20], "status": "PASS" if not mismatches and
            len(actual) == expected_states else "FAIL"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True,
                        help="closed C4 arm audit JSON; must bind a terminal receipt and T24 capture")
    parser.add_argument("--out", type=Path, required=True, help="new evidence output directory")
    args = parser.parse_args()
    audit, receipt_path, ledger_row, ledger_path = verify_closed_audit(args.audit)
    ledger_identity = verify_ledger_hashes(ledger_row, ledger_path)
    calls = selected_calls(ledger_path)
    verify_audit_pairs(audit, calls)
    helper_sha = sha256(HELPER)
    if helper_sha != "26b6c268ca1bc243438c06c1be209dcc33b0b31612e48aaca16476cdda35505a":
        raise ValueError("extracted helper body changed from the selected C4 source")
    args.out.mkdir(parents=True, exist_ok=False)
    driver = args.out / "replay_fixture.F90"
    generate_driver(calls, driver)
    profile_results = {}
    for profile in ("O0", "O2"):
        with tempfile.TemporaryDirectory(prefix=f"pr93_ice_replay_{profile.lower()}_", dir="/var/tmp") as temp:
            scratch = Path(temp)
            code, output = run_pinned(HELPER, driver, scratch, profile)
            (args.out / f"{profile}.log").write_text(output, encoding="utf-8")
            comparison = compare_output(output, calls) if code == 0 else {
                "status": "NOT_RUN", "mismatch_count": None, "call_count": len(calls)}
            profile_results[profile] = {"returncode": code, **comparison}
    status = "PASS_CALL_LEVEL" if all(row["returncode"] == 0 and row["status"] == "PASS"
                                       for row in profile_results.values()) else "FAIL_CALL_REPLAY"
    summary = {
        "schema": "pr93_c4_ice_sedimentation_replay_v1",
        "status": status,
        "arm": audit["arm"],
        "receipt_path": str(receipt_path),
        "receipt_sha256": audit["receipt"]["sha256"],
        "ledger_path": str(ledger_path),
        "ledger_identity": ledger_identity,
        "helper_path": str(HELPER),
        "helper_sha256": helper_sha,
        "source_sha256": SOURCE_SHA256,
        "calls": [{"key": list(call["key"]), "levels": len(call["rows"])} for call in calls],
        "driver_sha256": sha256(driver),
        "profile_results": profile_results,
        "replay": "Pinned Intel O0/O2; each helper output QI/NI REAL32 bit pair compared to captured AFTER for every level.",
        "completion_claim": "Call-level evidence only; whole-step completion through T24 is not required or claimed.",
        "attribution": "C4 selected-call replay only; this does not by itself prove C18 historical causality.",
    }
    (args.out / "prepared.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if status == "PASS_CALL_LEVEL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
