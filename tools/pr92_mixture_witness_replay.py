#!/usr/bin/env python3
"""Replay hash-pinned C15 graupel mixture witnesses against D1 FULL candidates."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr92_graupel_store_replay as store_replay
import pr92_source_replay as source_replay
import pr92_diffusion_producer_capture as producer_capture

SOURCE = ROOT / "docs/evidence/pr92_source_store_20261020/graupel_store/witness/module_em_c15.F"
SOURCE_SHA256 = "1ec3131abace4337314279ac833a6bcae32c0080261cccc912b45f0afba16399"
D1_OFF = ROOT / "docs/evidence/pr92_source_store_20261020/graupel_store/input/off_consumer.raw.gz"
D1_CPL = ROOT / "docs/evidence/pr92_source_store_20261020/graupel_store/input/cpl_consumer.raw.gz"
D1_SOURCE_SHA256 = "1d6538e3e1aeb59a2f0f38b2ec8de8aef11c4991e2d6ae0c8d4641b065c821ef"
D1_COMBINED = ROOT / "docs/evidence/pr92_source_store_20261020/graupel_store/combined.json"
D1_COMBINED_SHA256 = "caecb9360f54c49c0c369aa825eb9e35c470228a50dd459af81e59032e8542e5"
TARGETS = set(producer_capture.TARGETS)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract(source: str, name: str) -> str:
    starts = list(re.finditer(rf"(?im)^\s*(?:pure\s+)?(?:logical\s+)?(?:subroutine|function)\s+{name}\s*\(", source))
    if len(starts) != 1:
        raise ValueError(f"expected one pinned helper {name}")
    end = re.search(rf"(?im)^\s*end\s+(?:subroutine|function)\s+{name}\s*$", source[starts[0].start():])
    if not end:
        raise ValueError(f"helper {name} has no end")
    return source[starts[0].start():starts[0].start() + end.end()].rstrip()


def parse_witness(path: Path) -> list[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", errors="strict") as stream:
        lines = stream.read().splitlines()
    records: list[dict[str, Any]] = []
    block: dict[str, Any] | None = None
    expected = {"PR92_MIXTURE_TRIAL": 8, "PR92_MIXTURE_WEIGHTS64": 8,
                "PR92_MIXTURE_TERMS32": 15, "PR92_MIXTURE_VALUES64": 12,
                "PR92_MIXTURE_VALUES32": 9, "PR92_MIXTURE_END": 1}
    sequence = ["PR92_MIXTURE_TRIAL", "PR92_MIXTURE_WEIGHTS64", "PR92_MIXTURE_TERMS32",
                "PR92_MIXTURE_VALUES64", "PR92_MIXTURE_VALUES32", "PR92_MIXTURE_END"]
    for line in lines:
        fields = line.split()
        if not fields:
            continue
        tag = fields[0]
        if tag not in expected or len(fields) != expected[tag]:
            raise ValueError(f"unknown or malformed C15 witness row: {tag}")
        if tag == "PR92_MIXTURE_TRIAL":
            if block is not None:
                raise ValueError("nested C15 mixture witness")
            nums = list(map(int, fields[1:]))
            step, rk, i, j, k, cell, source_first = nums
            if (step, rk) != (15, 1) or (i, j, k) not in TARGETS or source_first not in (0, 1):
                raise ValueError("C15 witness is outside the pinned T15/RK1 target contract")
            block = {"coordinate": [step, rk, i, j, k], "cell": cell,
                     "source_first_pair": bool(source_first), "_next_tag": 1}
        elif block is None:
            raise ValueError(f"C15 witness row outside trial block: {tag}")
        elif tag != sequence[block["_next_tag"]]:
            raise ValueError(f"out-of-order or duplicate C15 witness row: {tag}")
        elif tag == "PR92_MIXTURE_WEIGHTS64":
            block["weights64_bits"] = fields[1:]
            block["_next_tag"] += 1
        elif tag == "PR92_MIXTURE_TERMS32":
            block["terms32_bits"] = fields[1:]
            block["_next_tag"] += 1
        elif tag == "PR92_MIXTURE_VALUES64":
            block["values64_bits"] = fields[1:]
            block["_next_tag"] += 1
        elif tag == "PR92_MIXTURE_VALUES32":
            block["values32_bits"] = fields[1:]
            block["_next_tag"] += 1
        else:
            required = {"weights64_bits", "terms32_bits", "values64_bits", "values32_bits"}
            if not required.issubset(block):
                raise ValueError("incomplete C15 mixture witness")
            if any(re.fullmatch(r"[0-9A-Fa-f]{16}", value) is None for value in block["weights64_bits"] + block["values64_bits"]):
                raise ValueError("malformed C15 REAL64 bits")
            if any(re.fullmatch(r"[0-9A-Fa-f]{8}", value) is None for value in block["terms32_bits"] + block["values32_bits"]):
                raise ValueError("malformed C15 REAL32 bits")
            records.append(block)
            block = None
    if block is not None:
        raise ValueError("truncated C15 mixture witness")
    if not records:
        raise ValueError("C15 mixture witness capture is empty")
    return records


def d1_full_candidates(path: Path, arm: str) -> tuple[dict[tuple[int, ...], dict], dict[str, int]]:
    combined_bytes = D1_COMBINED.read_bytes()
    if sha256(combined_bytes) != D1_COMBINED_SHA256:
        raise ValueError("archived D1 combined replay hash mismatch")
    combined = json.loads(combined_bytes)
    if combined.get("hashes", {}).get(arm, {}).get("d1_module_sha256") != D1_SOURCE_SHA256:
        raise ValueError("D1 source hash does not match the pinned combined replay")
    expected_capture_hash = combined["hashes"][arm]["consumer_capture_sha256"]
    if sha256(path.read_bytes()) != expected_capture_hash:
        raise ValueError(f"D1 {arm} consumer capture hash does not match combined replay")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", errors="strict") as stream:
        text = stream.read()
    with __import__("tempfile").TemporaryDirectory(prefix="pr92_d1_candidate_") as folder:
        capture = Path(folder) / "consumer.raw"
        capture.write_text(text)
        parsed = source_replay.parse_consumer_capture(capture)
    all_rows = parsed["store_failures"]
    selected = [row for row in all_rows if row["context"] == "FULL" and row["step"] == 15 and row["rk"] == 1]
    expected = {"OFF": 7, "CPL": 12}[arm]
    if len(selected) != expected:
        raise ValueError(f"expected {expected} D1 FULL T15/RK1 candidates for {arm}")
    expected_stage2 = {"OFF": 6, "CPL": 11}[arm]
    expected_stage6 = 1
    if sum(row["failure_stage"] == 2 for row in selected) != expected_stage2 or \
            sum(row["failure_stage"] == 6 for row in selected) != expected_stage6:
        raise ValueError(f"unexpected D1 FULL stage2/stage6 counts for {arm}")
    mapping = {tuple(row[key] for key in ("step", "rk", "i", "j", "k")): row for row in selected}
    if len(mapping) != len(selected):
        raise ValueError("duplicate D1 FULL candidate coordinate")
    historical: dict[str, int] = {}
    for row in all_rows:
        if row["step"] == 15 and row["rk"] == 1:
            continue
        key = f"step={row['step']}/rk={row['rk']}/{row['context']}"
        historical[key] = historical.get(key, 0) + 1
    return mapping, historical


def adapter(source: str) -> str:
    strict = extract(source, "strict_graupel_pair")
    mixture = extract(source, "store_graupel_mixture")
    return """module c15_mixture_adapter
  use iso_fortran_env, only: int32,int64,real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer,parameter :: real128=selected_real_kind(33,4931)
contains
""" + strict + "\n" + mixture + "\nend module c15_mixture_adapter\n"


def data_module(records: list[dict]) -> str:
    coords = [v for row in records for v in row["coordinate"] + [row["cell"], int(row["source_first_pair"])]]
    arrays = {"coords": (coords, 7, "int32"),
              "weights": ([x for row in records for x in row["weights64_bits"]], 7, "int64"),
              "terms": ([x for row in records for x in row["terms32_bits"]], 14, "int32"),
              "values64": ([x for row in records for x in row["values64_bits"]], 11, "int64"),
              "values32": ([x for row in records for x in row["values32_bits"]], 8, "int32")}
    lines = ["module witness_data", "  use iso_fortran_env, only: int32,int64", "  implicit none"]
    for name, (values, width, kind) in arrays.items():
        literals = ", &\n    ".join(f"int(z'{value}',{kind})" for value in values)
        lines.append(f"  integer({kind}),parameter :: {name}({width},{len(records)})=reshape([ &\n    {literals}], [{width},{len(records)}])")
    lines.append("end module witness_data")
    return "\n".join(lines) + "\n"


def harness() -> str:
    return r"""program replay_c15_mixture_witness
  use iso_fortran_env, only: int32,int64,real32,real64
  use witness_data
  use c15_mixture_adapter
  implicit none
  real(real64) :: weights_local(7),minimum_ratio,maximum_ratio,reference_q,reference_b,delta_q,delta_b
  real(real64) :: candidate_q,candidate_b
  real(real32) :: qterms(7),bterms(7),denominator,stored_q,stored_b
  integer(int32) :: terms_local(14),inputs32(8)
  integer(int64) :: values_local(11),words64(6),candidate_q_bits,candidate_b_bits
  integer :: row,j,adjust
  logical :: valid,candidate_strict,stored_strict
  do row=1,size(coords,2)
    terms_local=terms(:,row); inputs32=values32(:,row); values_local=values64(:,row)
    do j=1,7
      weights_local(j)=transfer(weights(j,row),0.0_real64)
      qterms(j)=transfer(terms_local(j),qterms(j)); bterms(j)=transfer(terms_local(7+j),bterms(j))
    end do
    candidate_q=transfer(values_local(1),candidate_q); candidate_b=transfer(values_local(2),candidate_b)
    reference_q=candidate_q; reference_b=candidate_b
    delta_q=0.0_real64; delta_b=0.0_real64
    minimum_ratio=transfer(values_local(9),minimum_ratio); maximum_ratio=transfer(values_local(10),maximum_ratio)
    denominator=transfer(inputs32(5),denominator)
    candidate_q_bits=values_local(1); candidate_b_bits=values_local(2)
    candidate_strict=strict_graupel_pair(candidate_q,candidate_b,minimum_ratio,maximum_ratio)
    call store_graupel_mixture(weights_local,qterms,bterms,denominator,minimum_ratio,maximum_ratio, &
      reference_q,reference_b,stored_q,stored_b,delta_q,delta_b,valid)
    stored_strict=.false.
    if (valid) stored_strict=strict_graupel_pair(real(stored_q,real64),real(stored_b,real64), &
      minimum_ratio,maximum_ratio)
    words64=[transfer(delta_q,words64(1)),transfer(delta_b,words64(2)), &
      transfer(candidate_q_bits,words64(3)),transfer(candidate_b_bits,words64(4)), &
      values_local(3),values_local(4)]
    write(*,'(A,1X,I0,3(1X,L1),2(1X,Z8.8),6(1X,Z16.16))') 'MIXTURE_REPLAY',row,valid, &
      candidate_strict,stored_strict,transfer(stored_q,0_int32),transfer(stored_b,0_int32),words64
  end do
end program replay_c15_mixture_witness
"""


def parse_output(stdout: str, records: list[dict], d1: dict[tuple[int, ...], dict]) -> list[dict]:
    lines = [line.split() for line in stdout.splitlines() if line.strip()]
    rows = {}
    for fields in lines:
        if fields[0] != "MIXTURE_REPLAY" or len(fields) != 13:
            raise ValueError(f"unknown or malformed mixture replay row: {fields[0]}")
        index = int(fields[1])
        if index in rows:
            raise ValueError("duplicate mixture replay output row")
        rows[index] = {"valid": fields[2] == "T", "candidate_strict": fields[3] == "T",
                       "stored_strict": fields[4] == "T", "stored_q_bits": fields[5],
                       "stored_b_bits": fields[6], "delta_q_bits": fields[7], "delta_b_bits": fields[8],
                       "candidate_q_bits": fields[9], "candidate_b_bits": fields[10],
                       "stored_delta_q_bits": fields[11], "stored_delta_b_bits": fields[12]}
    if set(rows) != set(range(1, len(records) + 1)):
        raise ValueError("mixture replay output row count differs from capture")
    results = []
    for index, record in enumerate(records, 1):
        output = rows[index]
        coord = tuple(record["coordinate"])
        ref = d1.get(coord)
        candidate_q, candidate_b = record["values64_bits"][:2]
        exact_helper = (output["valid"] and output["stored_strict"] and
                        output["stored_q_bits"].upper() == record["values32_bits"][0].upper() and
                        output["stored_b_bits"].upper() == record["values32_bits"][1].upper() and
                        output["delta_q_bits"].upper() == record["values64_bits"][2].upper() and
                        output["delta_b_bits"].upper() == record["values64_bits"][3].upper() and
                        output["stored_delta_q_bits"].upper() == record["values64_bits"][2].upper() and
                        output["stored_delta_b_bits"].upper() == record["values64_bits"][3].upper() and
                        output["candidate_q_bits"].upper() == candidate_q.upper() and
                        output["candidate_b_bits"].upper() == candidate_b.upper())
        d1_bits_match = ref is not None and [value.upper() for value in ref["candidate_bits64"][0:2]] == \
            [candidate_q.upper(), candidate_b.upper()]
        d1_cell_match = ref is not None and ref["cell"] == record["cell"]
        results.append({"coordinate": list(coord), "cell": record["cell"],
            "source_first_pair": record["source_first_pair"],
            "candidate_q_bits64": candidate_q, "candidate_b_bits64": candidate_b,
            "source_payload_bits64": {
                "q_source": record["values64_bits"][4], "b_source": record["values64_bits"][5],
                "q_after": record["values64_bits"][6], "b_after": record["values64_bits"][7],
                "minimum_ratio": record["values64_bits"][8], "maximum_ratio": record["values64_bits"][9],
                "new_carrier_r64": record["values64_bits"][10]},
            "weights64_bits": record["weights64_bits"], "donor_q_and_b_terms32_bits": record["terms32_bits"],
            "store_inputs32_bits": {
                "dt": record["values32_bits"][2], "old_carrier": record["values32_bits"][3],
                "new_carrier": record["values32_bits"][4], "dry_density": record["values32_bits"][5],
                "q_base": record["values32_bits"][6], "b_base": record["values32_bits"][7]},
            "stored_q_bits32": record["values32_bits"][0], "stored_b_bits32": record["values32_bits"][1],
            "delta_q_bits64": record["values64_bits"][2], "delta_b_bits64": record["values64_bits"][3],
            "candidate_strict": output["candidate_strict"], "stored_strict": output["stored_strict"],
            "helper_replay_exact": exact_helper, "candidate_bits_match_d1_full": d1_bits_match,
            "cell_matches_d1_full": d1_cell_match,
            "candidate_matches_d1_full": d1_bits_match and d1_cell_match,
            "d1_failure_stage": ref["failure_stage"] if ref else None,
            "d1_candidate_bits64": ref["candidate_bits64"][:2] if ref else None,
            "transaction_commit_status": "NOT_CAPTURED"})
    return results


def replay(witness_path: Path, d1_consumer_path: Path, output: Path, arm: str,
           source_path: Path = SOURCE) -> dict[str, Any]:
    source_bytes = source_path.read_bytes()
    if sha256(source_bytes) != SOURCE_SHA256:
        raise ValueError("C15 helper source hash mismatch")
    d1_bytes = d1_consumer_path.read_bytes()
    records = parse_witness(witness_path)
    d1, historical = d1_full_candidates(d1_consumer_path, arm)
    adapter_text = adapter(source_bytes.decode())
    data_text = data_module(records)
    sources = {"mixture_adapter.f90": adapter_text, "witness_data.f90": data_text,
               "replay.f90": harness()}
    output.mkdir(parents=True, exist_ok=True)
    generated = output / "generated"
    generated.mkdir(exist_ok=True)
    for name, text in sources.items():
        generated.joinpath(name).write_text(text)
    o0 = store_replay.run_source_profile("O0", sources, executable="pr92_mixture_o0")
    o2 = store_replay.run_source_profile("O2", sources, executable="pr92_mixture_o2")
    runtime0 = strict_runtime_rows(o0["stdout"])
    runtime2 = strict_runtime_rows(o2["stdout"])
    if runtime0 != runtime2:
        raise RuntimeError("C15 mixture witness O0/O2 outputs differ")
    results = parse_output(runtime0, records, d1)
    expected_d1 = set(d1)
    expected_stage2 = {coord for coord, row in d1.items() if row["failure_stage"] == 2}
    witnessed = {tuple(row["coordinate"]) for row in results}
    witness_stage2 = {tuple(row["coordinate"]) for row in results
                      if tuple(row["coordinate"]) in expected_stage2}
    complete_coordinates = expected_stage2.issubset(witness_stage2)
    all_trials_exact = all(row["helper_replay_exact"] for row in results)
    all_d1_candidates_match = all(
        any(tuple(row["coordinate"]) == coord and row["candidate_matches_d1_full"] for row in results)
        and all(row["candidate_matches_d1_full"] for row in results if tuple(row["coordinate"]) == coord)
        for coord in expected_stage2)
    witnessed_targets = {(coord[2], coord[3], coord[4]) for coord in witnessed}
    status = ("LOCAL_TRIAL_REPLAY_CLOSED_COMMIT_UNVERIFIED"
              if complete_coordinates and all_trials_exact and all_d1_candidates_match else "UNRESOLVED")
    report = {"schema": "pr92_c15_mixture_witness_replay_v1", "status": status,
        "arm": arm, "local_trial_count": len(results), "d1_full_candidate_count": len(d1),
        "global_target_coordinate_coverage": {"covered": len(witnessed_targets),
            "expected_union": len(TARGETS), "coordinates": [list(coord) for coord in sorted(witnessed_targets)]},
        "d1_full_count": len(expected_d1), "d1_full_stage2_count": len(expected_stage2),
        "d1_full_stage6_count": sum(row["failure_stage"] == 6 for row in d1.values()),
        "stage2_witness_coordinate_count": len(witness_stage2),
        "d1_full_stage2_coordinate_coverage_complete": complete_coordinates,
        "all_local_trials_replay_exactly": all_trials_exact,
        "all_overlapping_d1_full_candidates_match": all_d1_candidates_match,
        "transaction_commit_status": "NOT_CAPTURED", "historical_excluded_store_counts": historical,
        "local_trials": results, "profiles": {"O0": o0, "O2": o2},
        "runtime_stdout_sha256": sha256(runtime0.encode()),
        "hashes": {"c15_source_sha256": sha256(source_bytes), "d1_consumer_capture_sha256": sha256(d1_bytes),
            "d1_combined_replay_sha256": sha256(D1_COMBINED.read_bytes()),
            "mixture_capture_sha256": sha256(witness_path.read_bytes()),
            "mixture_helper_text_sha256": sha256(adapter_text.encode()),
            "tool_sha256": sha256(Path(__file__).read_bytes()),
            "source_parser_sha256": sha256(Path(source_replay.__file__).read_bytes()),
            "producer_target_source_sha256": sha256(Path(producer_capture.__file__).read_bytes()),
            "compiler_wrapper_sha256": sha256(Path(store_replay.__file__).read_bytes()),
            "intel_profile_sha256": sha256((ROOT / "tests/intel_toolchain.sh").read_bytes())},
        "generated_source_files": {name: sha256(text.encode()) for name, text in sources.items()}}
    output.joinpath("replay.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def strict_runtime_rows(stdout: str) -> str:
    rows = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        if line.startswith("MIXTURE_REPLAY"):
            fields = line.split()
            if len(fields) != 13 or fields[0] != "MIXTURE_REPLAY":
                raise ValueError("malformed C15 mixture replay output")
            rows.append(line)
        elif rows:
            raise ValueError(f"unexpected output after C15 replay rows: {line}")
    if not rows:
        raise ValueError("C15 mixture replay emitted no rows")
    return "\n".join(rows)


def summary_payload(result: dict[str, Any], arm: str, report_path: Path) -> dict[str, Any]:
    return {"status": result["status"], "arm": arm,
        "local_trials": result["local_trial_count"],
        "d1_stage2_covered": result["d1_full_stage2_coordinate_coverage_complete"],
        "local_trials_exact": result["all_local_trials_replay_exactly"],
        "transaction_commit_status": result["transaction_commit_status"],
        "report": str(report_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--witness", required=True, type=Path)
    parser.add_argument("--d1-consumer", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arm", required=True, choices=("OFF", "CPL"))
    parser.add_argument("--c15-source", type=Path, default=SOURCE)
    args = parser.parse_args()
    result = replay(args.witness, args.d1_consumer, args.output, args.arm, args.c15_source)
    print(json.dumps(summary_payload(result, args.arm, args.output / "replay.json"), sort_keys=True))


if __name__ == "__main__":
    main()
