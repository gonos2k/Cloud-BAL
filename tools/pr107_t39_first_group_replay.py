#!/usr/bin/env python3
"""Replay the captured first T39/RK2 grouped-store failure through pinned C2 core."""
from __future__ import annotations

import argparse
from fractions import Fraction
import gzip
import hashlib
import json
import re
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import pr99_group_failure_capture as capture  # noqa: E402
import pr99_group_failure_scalar_replay as scalar  # noqa: E402

EVIDENCE = ROOT / "docs/evidence/t39_closed_replay_20261027"
RAW_GZ = EVIDENCE / "pr99_group_failure.raw.gz"
JOIN = EVIDENCE / "t39_join.json"
RUN_RECEIPT = EVIDENCE / "HYDRO_T39_receipt.json"
C2_SOURCE = Path("/var/tmp/pr99_bulk_candidate_native_c2_20261022/source/overrides/module_em.F")
PR107_BUILD = Path("/var/tmp/pr107_t39_native_capture_20261026/build_receipt.json")
C2_BUILD = Path("/var/tmp/pr99_bulk_candidate_native_c2_20261022/pr87_native_overlay_build.json")
EXPECTED_C2_SOURCE_SHA256 = "d82efa15ee1c0a44080a8ef40b8a8aef436661f2093b6f66bef7e666584aa296"
EXPECTED_PR107_BUILD_SHA256 = "b66d9f87b58f371f8fce79e2b7c9727cfd13096cd2db9c51efa435efff0e5767"
EXPECTED_C2_BUILD_SHA256 = "9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb"
EXPECTED_EXECUTABLE_SHA256 = "7af1f907eb70e8f4ea234cbf18cfad0f408e8b374a0aecc9e695100bc485918c"
EXPECTED_RUN_RECEIPT_SHA256 = "a71f157b19695cae4cb228cd92b91f05a837fdcd913b1eff3d0d25809697a697"
EXPECTED_JOIN_SHA256 = "a5d9feeac67965928923c4c9f269fe34f9f6408d9bd1467b4244c5411f934ed4"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_sha256(label: str, data: bytes, expected: str) -> str:
    actual = sha256(data)
    if actual != expected:
        raise ValueError(f"{label} SHA256 mismatch: expected {expected}, got {actual}")
    return actual


def verify_join_bytes(data: bytes) -> dict:
    require_sha256("preserved T39 join", data, EXPECTED_JOIN_SHA256)
    return json.loads(data)


def write_exclusive(path: Path, result: dict) -> None:
    serialized = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(serialized)


def exact64(bits: str) -> Fraction:
    value = struct.unpack(">d", bytes.fromhex(bits))[0]
    return Fraction.from_float(value)


def module_core_sha256(source: str) -> str:
    matches = list(re.finditer(
        r"(?ims)^\s*module\s+cloud_bal_joint_transport\b.*?^\s*end\s+module\s+cloud_bal_joint_transport\s*$",
        source,
    ))
    if len(matches) != 1:
        raise ValueError("C2 source must contain exactly one cloud_bal_joint_transport module")
    return sha256(matches[0].group(0).encode())


def verify_build_binding(source: Path, pr107_build: Path, c2_build: Path,
                         run_receipt: dict) -> dict:
    source_bytes = source.read_bytes()
    source_sha = require_sha256("C2 module_em source", source_bytes, EXPECTED_C2_SOURCE_SHA256)
    pr107_bytes = pr107_build.read_bytes()
    pr107_sha = require_sha256("PR107 build receipt", pr107_bytes, EXPECTED_PR107_BUILD_SHA256)
    c2_bytes = c2_build.read_bytes()
    c2_sha = require_sha256("C2 overlay receipt", c2_bytes, EXPECTED_C2_BUILD_SHA256)
    pr107 = json.loads(pr107_bytes)
    c2 = json.loads(c2_bytes)
    module_object = [row for row in pr107["compiled_overrides"]
                     if row.get("member") == "module_em.o"]
    source_override = [row for row in c2["compiled_overrides"]
                       if row.get("member") == "module_em.o"]
    if len(module_object) != 1 or module_object[0].get("base_source_sha256") != source_sha:
        raise ValueError("PR107 compiled module_em object is not bound to the replay C2 source")
    if len(source_override) != 1 or source_override[0].get("source_sha256") != source_sha:
        raise ValueError("C2 overlay receipt does not bind its module_em override to replay source")
    if len(module_object) != 1 or len(source_override) != 1:
        raise ValueError("build receipts must have one module_em.o provenance row each")
    pr107_generated = Path(module_object[0]["generated_source_path"])
    c2_generated = Path(source_override[0]["generated_source_path"])
    pr107_generated_bytes = pr107_generated.read_bytes()
    c2_generated_bytes = c2_generated.read_bytes()
    require_sha256("PR107 preprocessed module_em", pr107_generated_bytes,
                   module_object[0]["generated_source_sha256"])
    require_sha256("C2 preprocessed module_em", c2_generated_bytes,
                   source_override[0]["generated_source_sha256"])
    pr107_core_sha = module_core_sha256(pr107_generated_bytes.decode())
    c2_core_sha = module_core_sha256(c2_generated_bytes.decode())
    if pr107_core_sha != c2_core_sha:
        raise ValueError("PR107 executed module and C2 overlay have different preprocessed core modules")
    if pr107.get("parent_receipt_sha256") != c2_sha:
        raise ValueError("PR107 build receipt parent hash differs from C2 overlay receipt")
    if run_receipt.get("candidate_build", {}).get("receipt_sha256") != pr107_sha:
        raise ValueError("HYDRO T39 run receipt does not bind the pinned PR107 build receipt")
    executed = pr107.get("executable_sha256")
    if executed != EXPECTED_EXECUTABLE_SHA256 or run_receipt.get("executed_executable_sha256") != executed:
        raise ValueError("PR107 executable hash differs from the executed HYDRO T39 receipt")
    if not run_receipt.get("candidate_build_unchanged"):
        raise ValueError("HYDRO T39 receipt does not confirm unchanged candidate build")
    require_sha256("pinned Intel toolchain profile", scalar.PROFILE.read_bytes(), scalar.PROFILE_SHA256)
    return {
        "c2_module_em_source_sha256": source_sha,
        "c2_cloud_bal_joint_transport_raw_module_sha256": module_core_sha256(source_bytes.decode()),
        "c2_preprocessed_module_em_sha256": sha256(c2_generated_bytes),
        "pr107_preprocessed_module_em_sha256": sha256(pr107_generated_bytes),
        "c2_preprocessed_cloud_bal_joint_transport_module_sha256": c2_core_sha,
        "pr107_preprocessed_cloud_bal_joint_transport_module_sha256": pr107_core_sha,
        "c2_overlay_build_receipt_sha256": c2_sha,
        "pr107_executed_build_receipt_sha256": pr107_sha,
        "pr107_module_em_object_base_source_sha256": module_object[0]["base_source_sha256"],
        "pr107_module_em_object_sha256": module_object[0].get("object_sha256"),
        "pr107_executable_sha256": executed,
        "hydro_t39_receipt_executed_executable_sha256": run_receipt["executed_executable_sha256"],
        "binding": "PR107 compiled module_em.o base source == C2 overlay module_em source; PR107 parent receipt == C2 overlay receipt; executed executable == HYDRO T39 run receipt",
    }


def classify(event: dict) -> dict:
    h = event["hex"]
    base_bits = h["HEX32_BASE"]
    if base_bits != ["00000000", "00000000"]:
        raise ValueError("this exact-ratio classification is pinned to zero REAL32 base moments")
    mass_bounds = [exact64(x) for x in h["HEX64_MASS_BOUNDS"]]
    if mass_bounds != [Fraction(100), Fraction(900)]:
        raise ValueError("first grouped pair must carry exact strict mass bounds [100,900]")
    carriers_dt = [struct.unpack(">f", bytes.fromhex(x))[0] for x in h["HEX32_CARRIERS_DT"]]
    old_carrier, new_carrier, density, timestep = carriers_dt
    if not (old_carrier > 0 and new_carrier > 0 and density > 0 and timestep > 0):
        raise ValueError("captured carrier, density, and timestep inputs must be positive")
    qsrc, nsrc = (exact64(x) for x in h["HEX64_SOURCE_RATE"])
    qtr, ntr = (exact64(x) for x in h["HEX64_TRANSPORT_RATE"])
    qcap, ncap = (exact64(x) for x in h["HEX64_CANDIDATE"])
    source_delta = qsrc - 900 * nsrc
    transport_delta = qtr - 900 * ntr
    combined_delta = (qsrc + qtr) - 900 * (nsrc + ntr)
    candidate_delta = qcap - 900 * ncap
    return {
        "strict_mass_bounds": [int(mass_bounds[0]), int(mass_bounds[1])],
        "base_moment_bits": base_bits,
        "carrier_density_dt_real32": carriers_dt,
        "source_q_minus_900n_exact": str(source_delta),
        "transport_q_minus_900n_exact": str(transport_delta),
        "combined_q_minus_900n_exact": str(combined_delta),
        "combined_ratio_delta_above_900": float(combined_delta / (nsrc + ntr)),
        "candidate_q_minus_900n_exact": str(candidate_delta),
        "candidate_ratio": float(qcap / ncap),
        "candidate_is_inside_exact_strict_mass_cone": mass_bounds[0] * ncap <= qcap <= mass_bounds[1] * ncap,
        "real32_rounded_candidate": _rounded_candidate(event, mass_bounds),
        "interpretation": "The exact captured REAL64 inputs and their formed REAL64 candidate are slightly above the strict upper bound. The pre-round candidate is rejected at store stage 2; separately, rounding q and n first would place that REAL32 pair inside the interval.",
    }


def _rounded_candidate(event: dict, mass_bounds: tuple[Fraction, Fraction] | list[Fraction]) -> dict:
    q, n = (struct.unpack(">d", bytes.fromhex(x))[0]
            for x in event["hex"]["HEX64_CANDIDATE"])
    q32 = struct.unpack(">f", struct.pack(">f", q))[0]
    n32 = struct.unpack(">f", struct.pack(">f", n))[0]
    return {"q_bits": struct.pack(">f", q32).hex().upper(),
            "n_bits": struct.pack(">f", n32).hex().upper(),
            "ratio": q32 / n32,
            "inside_strict_mass_bounds": mass_bounds[0] * n32 <= q32 <= mass_bounds[1] * n32}


def replay(source_path: Path, output: Path, pr107_build: Path = PR107_BUILD,
           c2_build: Path = C2_BUILD) -> dict:
    if output.resolve() in {source_path.resolve(), RAW_GZ.resolve(), JOIN.resolve(), RUN_RECEIPT.resolve(),
                            pr107_build.resolve(), c2_build.resolve()}:
        raise ValueError("output must be a separate evidence file")
    run_receipt = json.loads(RUN_RECEIPT.read_text())
    require_sha256("HYDRO T39 run receipt", RUN_RECEIPT.read_bytes(), EXPECTED_RUN_RECEIPT_SHA256)
    binding = verify_build_binding(source_path, pr107_build, c2_build, run_receipt)
    join = verify_join_bytes(JOIN.read_bytes())
    require_sha256("group capture parser", Path(capture.__file__).read_bytes(),
                   join["parser_sha256"]["pr99_group_failure_capture"])
    compressed = RAW_GZ.read_bytes()
    payload = gzip.decompress(compressed)
    group_join = join["hashes"]["group_capture"]
    require_sha256("compressed grouped capture", compressed, group_join["file_sha256"])
    require_sha256("decompressed grouped capture", payload, group_join["uncompressed_payload_sha256"])
    with tempfile.TemporaryDirectory(prefix="pr107-t39-first-group-") as tmp:
        raw_path = Path(tmp) / "pr99_group_failure.raw"
        raw_path.write_bytes(payload)
        parsed = capture.parse_capture(raw_path, timestep=39, rk=2)
        if parsed["event_count"] != 1:
            raise ValueError("pinned T39/RK2 grouped capture must contain exactly one first event")
        event = parsed["events"][0]
        captured_event = join["group_capture"]["first_event"]
        if [captured_event["i"], captured_event["j"], captured_event["k"]] != [199, 52, 21]:
            raise ValueError("preserved T39 join first-event cell does not match the requested group")
        if (event["cell"], event["pair"], event["group_predicate"], event["store_failure_stage"],
                event["hex"]["HEX64_CANDIDATE"]) != (
                captured_event["cell"], captured_event["pair"], captured_event["group_predicate"],
                captured_event["store_failure_stage"], captured_event["hex"]["HEX64_CANDIDATE"]):
            raise ValueError("raw T39 event differs from the preserved closed-join first event")
        module_source = source_path.read_text()
        runs = [scalar.run_one(event, module_source, level, group_join["uncompressed_payload_sha256"])
                for level in ("FREE", "REPRO")]
    return {
        "schema": "pr107_t39_first_group_replay_v1",
        "source_binding": binding,
        "capture": {"compressed_sha256": group_join["file_sha256"],
                    "payload_sha256": group_join["uncompressed_payload_sha256"],
                    "run_receipt_sha256": sha256(RUN_RECEIPT.read_bytes()),
                    "run_id": event["run_id"], "event_key": list(event["key"]),
                    "cell_ijk": [199, 52, 21], "pair": 4, "rk": 2, "timestep": 39,
                    "store_failure_stage": event["store_failure_stage"],
                    "group_predicate": event["group_predicate"],
                    "group_predicate_input": "(-1,-1) REAL32 sentinel after failed store"},
        "exact_classification": classify(event),
        "replays": runs,
        "scope": {
            "claim": "Input-local replay of captured values through receipt-pinned C2 core; event was observed in the PR107 diagnostic overlay whose shared core-module hash matches C2.",
            "not_claimed": "No full 2,533,440 by 4 group replay, forecast causality, or physical validation.",
            "producer_stencil": "The first-producer stencil values are not captured for this grouped cell; source/transport rates are captured.",
            "sentinel": "Predicate 1 is evaluated on the (-1,-1) sentinel installed after store rejection, so it is not an independent physical group failure.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=C2_SOURCE)
    parser.add_argument("--pr107-build", type=Path, default=PR107_BUILD)
    parser.add_argument("--c2-build", type=Path, default=C2_BUILD)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.source, args.output, args.pr107_build, args.c2_build)
    write_exclusive(args.output, result)
    print(json.dumps({"schema": result["schema"], "output": str(args.output),
                      "event_key": result["capture"]["event_key"],
                      "replay_summaries": [{"optimization": row["optimization"],
                                            "candidate_hex": row["candidate_hex"],
                                            "store_failure_stage": row["store_failure_stage"],
                                            "valid": row["valid"],
                                            "executable_sha256": row["executable_sha256"],
                                            "compiler_sha256": row["compiler_sha256"]}
                                           for row in result["replays"]]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
