#!/usr/bin/env python3
"""Verify and extract the receipt-bound C7 T8 rain PSD event from both arms."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
TARGET = (8, 222, "rain", "stage3", "188", "222", "5", "1")
EXPECTED_HEX = {
    "q_internal": "3481DDEF",
    "rho_dry": "3F8E9DE1",
    "pidnr": "4644597C",
    "power": "40400000",
    "lambda_min": "44704000",
    "lambda_max": "4708B800",
    "nvol_before": "3C9BEEF8",
    "nvol_directed": "3C9BEEF9",
}
STAGE_TRACE_SCHEMA_SHA256 = "5c2e9ccb3537a6bc251845e2b87c3efb991002ebbc1db5232d475e29f6c31720"
STATE_FIELDS = ("DEN", "Q", "QC", "QI", "QR", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
PBL_FIELDS = ("QV_TEND", "QC_TEND", "QI_TEND", "QNC_TEND", "QNI_TEND")


def read_exact(stream, count: int, digest) -> bytes:
    data = stream.read(count)
    if len(data) != count:
        raise ValueError(f"truncated stage trace: expected {count} bytes, got {len(data)}")
    digest.update(data)
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def r32_hex(text: str) -> str:
    return struct.pack(">f", float(text)).hex().upper()


def r64_hex(text: str) -> str:
    return struct.pack(">d", float(text)).hex().upper()


def extract_post_kdm6(run_dir: Path, receipt: dict) -> dict:
    trace_source = ROOT / "tools/pr85_joint_stage_trace.py"
    if sha256(trace_source.read_bytes()) != STAGE_TRACE_SCHEMA_SHA256:
        raise ValueError("joint stage trace schema source hash mismatch")
    matches = [item for item in receipt["compressed_outputs"]
               if item["path"] == "pr85_joint_moment_stages.raw"]
    if len(matches) != 1:
        raise ValueError(f"{run_dir}: expected one joint stage trace artifact")
    artifact = matches[0]
    compressed_path = run_dir / "run" / artifact["compressed_path"]
    if sha256_file(compressed_path) != artifact["compressed_sha256"]:
        raise ValueError(f"{run_dir}: compressed joint stage trace hash mismatch")
    digest = hashlib.sha256()
    raw_bytes = 0
    record_count = 0
    target_state = None
    with gzip.open(compressed_path, "rb") as stream:
        while True:
            magic = stream.read(8)
            if not magic:
                break
            digest.update(magic)
            raw_bytes += 8
            label = read_exact(stream, 32, digest).decode("ascii").strip()
            raw_bytes += 32
            header = read_exact(stream, 60, digest)
            raw_bytes += 60
            (kind, timestep, rkstep, ims, ime, jms, jme, kms, kme,
             its, ite, jts, jte, kts, kte) = struct.unpack(">15i", header)
            if kind == 1:
                fields = STATE_FIELDS
                if magic not in (b"PR85QND2", b"PR85QNB1"):
                    raise ValueError(f"{run_dir}: bad state trace magic {magic!r}")
            elif kind == 2:
                fields = PBL_FIELDS
                if magic != b"PR85PLB1":
                    raise ValueError(f"{run_dir}: bad tendency trace magic {magic!r}")
            else:
                raise ValueError(f"{run_dir}: unknown trace record kind {kind}")
            cells = (jte - jts + 1) * (kte - kts + 1) * (ite - its + 1)
            if min(cells, ime - ims + 1, jme - jms + 1, kme - kms + 1) <= 0:
                raise ValueError(f"{run_dir}: invalid trace geometry")
            location = None
            is_target = kind == 1 and timestep == 8 and label == "POST_KDM6"
            if is_target:
                gi, gj, gk = 188, 222, 5
                loc = (gj - jts, gk - kts, gi - its)
                shape = (jte - jts + 1, kte - kts + 1, ite - its + 1)
                if all(0 <= loc[n] < shape[n] for n in range(3)):
                    location = (loc[0] * shape[1] + loc[1]) * shape[2] + loc[2]
            target_values = {}
            for field in fields:
                data = read_exact(stream, cells * 4, digest)
                raw_bytes += cells * 4
                if location is not None and field in ("QR", "NR", "DEN"):
                    bits = struct.unpack_from(">I", data, location * 4)[0]
                    target_values[field] = {"hex": f"{bits:08X}",
                                            "decimal": struct.unpack(">f", struct.pack(">I", bits))[0]}
            record_count += 1
            if is_target:
                if location is None:
                    raise ValueError(f"{run_dir}: target is outside active POST_KDM6 bounds")
                if target_state is not None:
                    raise ValueError(f"{run_dir}: duplicate T8 POST_KDM6 state")
                target_state = {
                    "global_i_j_k": [188, 222, 5],
                    "record_bounds": {"its": its, "ite": ite, "jts": jts, "jte": jte,
                                      "kts": kts, "kte": kte},
                    "QR_kg_per_kgdry": target_values["QR"],
                    "NR_public_per_kgdry": target_values["NR"],
                    "DEN_kg_per_m3": target_values["DEN"],
                    "source_call_status": "POST_KDM6 after timestep 8 KDM6 returned normally",
                }
    if raw_bytes != artifact["bytes"] or digest.hexdigest() != artifact["sha256"]:
        raise ValueError(f"{run_dir}: raw joint stage trace hash/size mismatch")
    if target_state is None:
        raise ValueError(f"{run_dir}: missing T8 POST_KDM6 target state")
    if (target_state["QR_kg_per_kgdry"]["hex"] != EXPECTED_HEX["q_internal"] or
        target_state["DEN_kg_per_m3"]["hex"] != EXPECTED_HEX["rho_dry"] or
        target_state["NR_public_per_kgdry"]["hex"] != "3C8BF3B3"):
        raise ValueError(f"{run_dir}: public POST_KDM6 tuple mismatch")
    return {
        "trace_schema": {"path": str(trace_source), "sha256": STAGE_TRACE_SCHEMA_SHA256,
                         "state_fields": list(STATE_FIELDS)},
        "artifact": {"path": artifact["path"], "raw_sha256": artifact["sha256"],
                     "raw_bytes": artifact["bytes"],
                     "compressed_path": artifact["compressed_path"],
                     "compressed_sha256": artifact["compressed_sha256"],
                     "compressed_bytes": artifact["compressed_bytes"],
                     "records_parsed": record_count},
        "post_kdm6_public_state": target_state,
    }


def extract_arm(run_dir: Path, expected_arm: str) -> dict:
    receipt_path = run_dir / "receipt.json"
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    if receipt.get("arm") != expected_arm:
        raise ValueError(f"{run_dir}: wrong run arm")
    if receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0:
        raise ValueError(f"{run_dir}: run receipt is not successful and closed")
    if receipt.get("timestep_count") != 9:
        raise ValueError(f"{run_dir}: expected nine completed timesteps")
    build = receipt["candidate_build"]
    build_path = Path(build["receipt_path"])
    build_bytes = build_path.read_bytes()
    if sha256(build_bytes) != build["receipt_sha256"]:
        raise ValueError(f"{run_dir}: candidate build receipt hash mismatch")
    build_receipt = json.loads(build_bytes)
    exe_sha = sha256(Path(build["executable_path"]).read_bytes())
    if exe_sha != build["executable_sha256"]:
        raise ValueError(f"{run_dir}: executable hash mismatch")
    if exe_sha != receipt["executed_executable_sha256"]:
        raise ValueError(f"{run_dir}: executed executable differs from build")
    source_overrides = build_receipt["source_overrides"]
    compiled_source_hashes = {
        name: {
            "staged_path": source_overrides[name]["staged_path"],
            "sha256": source_overrides[name]["staged_sha256"],
        }
        for name in ("module_em.o", "module_mp_kdm6.o")
    }
    support = build_receipt["extra_observer"]
    compiled_source_hashes["support"] = {
        "staged_path": support["source_path"], "sha256": support["source_sha256"]
    }

    artifact = next(
        (item for item in receipt["compressed_outputs"]
         if item["path"] == "pr85_kdm6_psd_boundary.raw"),
        None,
    )
    if artifact is None:
        raise ValueError(f"{run_dir}: PSD boundary ledger missing from receipt")
    compressed_path = run_dir / "run" / artifact["compressed_path"]
    compressed_bytes = compressed_path.read_bytes()
    if sha256(compressed_bytes) != artifact["compressed_sha256"]:
        raise ValueError(f"{run_dir}: compressed PSD ledger hash mismatch")
    raw = gzip.decompress(compressed_bytes)
    if len(raw) != artifact["bytes"] or sha256(raw) != artifact["sha256"]:
        raise ValueError(f"{run_dir}: raw PSD ledger hash/size mismatch")

    step = lat = None
    found = []
    for line in raw.decode("ascii").splitlines():
        if line.startswith("# PR90_KDM6_PSD_BOUNDARY_CONTEXT"):
            step, lat = map(int, line.split()[-2:])
        elif line.startswith("PR85_KDM6_PSD_BOUNDARY,"):
            fields = line.split(",")
            key = (step, lat, *fields[1:7])
            if key == TARGET:
                found.append(fields)
    if len(found) != 1:
        raise ValueError(f"{run_dir}: expected exactly one target side-1 row, got {len(found)}")
    fields = found[0]
    row = {
        "species": fields[1], "stage": fields[2], "i": int(fields[3]),
        "lat": int(fields[4]), "k": int(fields[5]), "side": int(fields[6]),
        "q_r32": fields[7].strip(), "rho_dry_r32": fields[8].strip(),
        "lambda_min_r32": fields[9].strip(), "lambda_max_r32": fields[10].strip(),
        "number_volume_before_r32": fields[11].strip(),
        "number_volume_native_r32": fields[12].strip(),
        "number_volume_directed_r32": fields[13].strip(),
        "native_delta_r64": fields[14].strip(),
        "storage_correction_r64": fields[15].strip(), "exact_number_min_r64": fields[16].strip(),
        "exact_number_max_r64": fields[17].strip(), "legacy_available": fields[18].strip(),
    }
    actual_hex = {
        "q_internal": r32_hex(row["q_r32"]), "rho_dry": r32_hex(row["rho_dry_r32"]),
        "nvol_before": r32_hex(row["number_volume_before_r32"]),
        "nvol_directed": r32_hex(row["number_volume_directed_r32"]),
    }
    if actual_hex != {key: EXPECTED_HEX[key] for key in actual_hex}:
        raise ValueError(f"{run_dir}: target R32 bits differ: {actual_hex}")
    if r64_hex(row["native_delta_r64"]) != "3E20000000000000":
        # The serialized decimal is the exact R64 subtraction of the two R32 values.
        raise ValueError(f"{run_dir}: unexpected native delta {row['native_delta_r64']}")
    if float(row["storage_correction_r64"]) != 0.0:
        raise ValueError(f"{run_dir}: unexpected storage correction")
    return {
        "arm": expected_arm,
        "run_receipt": {"path": str(receipt_path), "sha256": sha256(receipt_bytes),
                        "status": receipt["status"], "returncode": receipt["returncode"],
                        "wall_seconds": receipt["wall_seconds"],
                        "timesteps": receipt["timestep_count"]},
        "candidate_build": {"path": str(build_path), "sha256": build["receipt_sha256"],
                            "status": build_receipt["status"], "identity": build_receipt["identity"],
                            "executable_sha256": exe_sha,
                            "compiled_source_sha256": compiled_source_hashes},
        "psd_ledger": {"raw_sha256": artifact["sha256"], "raw_bytes": artifact["bytes"],
                       "compressed_path": artifact["compressed_path"],
                       "compressed_sha256": artifact["compressed_sha256"],
                       "compressed_bytes": artifact["compressed_bytes"]},
        "target_row": row,
        "target_bits": actual_hex,
        "native_post_kdm6_trace": extract_post_kdm6(run_dir, receipt),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off", type=Path, required=True, help="closed OFF run directory")
    parser.add_argument("--coupled", type=Path, required=True, help="closed COUPLED run directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    arms = [extract_arm(args.off, "OFF"), extract_arm(args.coupled, "COUPLED")]
    if arms[0]["target_row"] != arms[1]["target_row"]:
        raise ValueError("OFF and COUPLED target ledger rows differ")
    result = {
        "schema": "pr90_c7_psd_t8_event_v1",
        "status": "PASS_RECEIPT_BOUND_TARGET_EVENT",
        "scope": {
            "interpretation": "one final PSD boundary-reconstruction event in each arm",
            "internal_volume_number_unit": "number per m3 dry air; PR85 PSD row N values",
            "public_specific_number_unit": "number per kg dry air; actual POST_KDM6 NR state trace",
            "internal_nvol_and_public_nr_are_distinct_fields": True,
            "not_a_global_number_budget": True,
            "not_a_physical_nucleation_claim": True,
            "ledger_row_semantics": "events; repeated rows are not deduplicated unique cells",
            "legacy_paths_may_also_be_logged": True,
        },
        "source_failure_binding": {
            "c6_failure_replay": "../c6/OFF_t8_failure_replay.json",
            "c6_failure_replay_sha256": "e084d1738cc14a5efe1c581975502f967ecb7464602fa011295e5626c61196b4",
            "input_hex": {
                "q_internal": EXPECTED_HEX["q_internal"],
                "nvol_internal": EXPECTED_HEX["nvol_before"],
                "dry_density": EXPECTED_HEX["rho_dry"],
                "pidnr": EXPECTED_HEX["pidnr"],
                "power": EXPECTED_HEX["power"],
                "lambda_min": EXPECTED_HEX["lambda_min"],
                "lambda_max": EXPECTED_HEX["lambda_max"],
            },
        },
        "extractor": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256(Path(__file__).read_bytes()),
        },
        "arms": arms,
    }
    if arms[0]["native_post_kdm6_trace"]["post_kdm6_public_state"] != \
       arms[1]["native_post_kdm6_trace"]["post_kdm6_public_state"]:
        raise ValueError("OFF and COUPLED POST_KDM6 target states differ")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "sha256": sha256(args.output.read_bytes())}, sort_keys=True))


if __name__ == "__main__":
    main()
