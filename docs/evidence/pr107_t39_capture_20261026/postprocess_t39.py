#!/usr/bin/env python3
"""Join receipt-bound T39/RK2 group and consumer captures with T39/RK1 producers."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any


TOOLS = Path(__file__).resolve().parents[3] / "tools"
sys.path.insert(0, str(TOOLS))

import pr92_source_replay  # noqa: E402
import pr99_group_failure_capture  # noqa: E402


FATAL_CONSUMER = (39, 2, 2, 219, 13)
PRODUCER_EPOCH = (39, 1)
PRODUCER_CHANNELS = (7, 8)
FATAL_CALLBACK_PAIR = 4


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_closed_hydro_receipt(path: Path) -> dict[str, Any]:
    receipt = json.loads(path.read_text())
    if receipt.get("arm") != "HYDRO":
        raise ValueError("closed receipt must identify the HYDRO arm")
    if receipt.get("status") not in {"COMPLETE", "INCOMPLETE"}:
        raise ValueError("receipt is not closed with a terminal COMPLETE/INCOMPLETE status")
    returncode = receipt.get("returncode")
    if not isinstance(returncode, int) or isinstance(returncode, bool):
        raise ValueError("closed receipt must record the final integer return code")
    if receipt.get("candidate_build_unchanged") is not True:
        raise ValueError("closed receipt does not confirm the candidate build is unchanged")
    if receipt.get("candidate_input_unchanged") is not True:
        raise ValueError("closed receipt does not confirm candidate inputs are unchanged")
    expected_exe = receipt.get("expected_executed_executable_sha256")
    if expected_exe and receipt.get("executed_executable_sha256") != expected_exe:
        raise ValueError("closed receipt executed executable differs from the expected candidate")
    if receipt.get("changed_staged_inputs") != []:
        raise ValueError("closed receipt reports changed staged inputs")
    if receipt.get("changed_original_inputs") != []:
        raise ValueError("closed receipt reports changed original inputs")
    if receipt.get("processing_errors") != []:
        raise ValueError("closed receipt reports output processing errors")
    return receipt


def _receipt_artifact_hashes(receipt: dict[str, Any], name: str) -> tuple[set[str], set[str]]:
    file_hashes: set[str] = set()
    payload_hashes: set[str] = set()
    for row in receipt.get("generated_files", []):
        if Path(row.get("path", "")).name == name:
            file_hashes.add(row["sha256"])
    for row in receipt.get("compressed_outputs", []):
        if Path(row.get("path", "")).name == name:
            file_hashes.add(row["sha256"])
        if Path(row.get("compressed_path", "")).name == name:
            file_hashes.add(row["compressed_sha256"])
            payload_hashes.add(row["sha256"])
    return file_hashes, payload_hashes


def verify_capture_artifact(path: Path, receipt: dict[str, Any]) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"capture file does not exist: {path}")
    expected_file, expected_payload = _receipt_artifact_hashes(receipt, path.name)
    if len(expected_file) != 1:
        raise ValueError(f"receipt has no unique hash for capture artifact {path.name}")
    actual_file = file_sha256(path)
    if actual_file not in expected_file:
        raise ValueError(f"capture hash differs from closed receipt: {path.name}")
    hashes = {"file_sha256": actual_file}
    if path.suffix == ".gz":
        if len(expected_payload) != 1:
            raise ValueError(f"receipt has no unique uncompressed hash for {path.name}")
        digest = hashlib.sha256()
        with gzip.open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        actual_payload = digest.hexdigest()
        if actual_payload not in expected_payload:
            raise ValueError(f"capture payload hash differs from closed receipt: {path.name}")
        hashes["uncompressed_payload_sha256"] = actual_payload
    else:
        hashes["uncompressed_payload_sha256"] = actual_file
    return hashes


def materialize_text(path: Path, directory: Path) -> Path:
    if path.suffix != ".gz":
        return path
    output = directory / path.name.removesuffix(".gz")
    with gzip.open(path, "rt", encoding="ascii") as source:
        output.write_text(source.read())
    return output


def _one(rows: list[dict[str, Any]], description: str) -> dict[str, Any]:
    if len(rows) != 1:
        raise ValueError(f"expected one {description}; found {len(rows)}")
    return rows[0]


def join_fatal_producers(producers: dict[tuple[int, ...], dict[str, Any]],
                         consumer: dict[str, Any]) -> dict[str, Any]:
    identity = consumer.get("producer_identity")
    if not isinstance(identity, list) or len(identity) != 8:
        raise ValueError("fatal consumer has no complete producer identity bounds")
    bounds = list(map(int, identity))
    if tuple(bounds[:2]) != PRODUCER_EPOCH:
        raise ValueError(f"fatal consumer producer identity is not T39/RK1: {bounds[:2]}")
    step, rk, il, ih, jl, jh, kl, kh = bounds
    joined: dict[str, Any] = {}
    for channel in PRODUCER_CHANNELS:
        matches = [(key, record) for key, record in producers.items()
                   if key[0:3] == (step, rk, channel)
                   and key[4:] == (consumer["i"], consumer["j"], consumer["k"])]
        key, record = _one(matches, f"channel {channel} T39/RK1 producer at fatal consumer cell")
        if record["identity"] != bounds:
            raise ValueError(f"channel {channel} producer bounds differ from consumer identity")
        if not (il <= key[4] <= ih and jl <= key[5] <= jh and kl <= key[6] <= kh):
            raise ValueError(f"channel {channel} producer cell is outside consumer identity bounds")
        joined[str(channel)] = {
            "producer_key": list(key),
            "producer_identity_bounds": list(record["identity"]),
            "before32_bits": str(record["before32_bits"]).upper(),
            "after32_bits": str(record["after32_bits"]).upper(),
            "diffusion64_bits": str(record["diffusion64_bits"]).upper(),
            "scale32_bits": [str(value).upper() for value in record["scale32_bits"]],
            "metrics32_bits": [str(value).upper() for value in record["metrics32_bits"]],
            "stencil32_bits": record["stencil"],
            "matches_consumer_source_rate": str(record["diffusion64_bits"]).upper()
            == str(consumer["r64_bits"][channel - 7]).upper(),
            "matches_consumer_recomputed_diffusion": str(record["diffusion64_bits"]).upper()
            == str(consumer["r64_bits"][channel - 5]).upper(),
        }
    return {"producer_identity_bounds": bounds, "channels": joined}


def link_first_group_to_fatal(first_group: dict[str, Any],
                              fatal_cell: list[int]) -> tuple[bool, bool, str, dict[str, Any] | None]:
    group_cell = [first_group["i"], first_group["j"], first_group["k"]]
    same_cell = group_cell == fatal_cell
    pair_matches_callback = first_group["pair"] == FATAL_CALLBACK_PAIR
    if same_cell and pair_matches_callback:
        status = "LINKED_SAME_CELL_PAIR4"
        link = {"group_event_index": 0, "group_event_key": list(first_group["key"]),
                "pair": first_group["pair"], "group_predicate": first_group["group_predicate"],
                "candidate64_hex": first_group["hex"]["HEX64_CANDIDATE"],
                "store_failure_stage": first_group["store_failure_stage"]}
    elif same_cell:
        status = "SAME_CELL_PAIR_MISMATCH"
        link = None
    else:
        status = "DIFFERENT_CELL"
        link = None
    return same_cell, pair_matches_callback, status, link


def build_report(receipt_path: Path, group_path: Path, producer_path: Path,
                 consumer_path: Path) -> dict[str, Any]:
    receipt = verify_closed_hydro_receipt(receipt_path)
    input_hashes = {"closed_receipt_sha256": file_sha256(receipt_path),
                    "group_capture": verify_capture_artifact(group_path, receipt),
                    "producer_capture": verify_capture_artifact(producer_path, receipt),
                    "consumer_capture": verify_capture_artifact(consumer_path, receipt)}
    with tempfile.TemporaryDirectory(prefix="pr107-t39-postprocess-") as temporary:
        directory = Path(temporary)
        group = pr99_group_failure_capture.parse_capture(
            materialize_text(group_path, directory), timestep=39, rk=2)
        producers = pr92_source_replay.parse_producer_capture(
            materialize_text(producer_path, directory))
        parsed_consumer = pr92_source_replay.parse_consumer_capture(
            materialize_text(consumer_path, directory))

    first_group = group["events"][0]
    run_id = receipt.get("diagnostic_environment", {}).get("PR91_RUN_ID")
    if run_id and any(event["run_id"] != run_id for event in group["events"]):
        raise ValueError("group capture run ID differs from the closed HYDRO receipt")
    fatal_step, fatal_rk, fatal_i, fatal_j, fatal_k = FATAL_CONSUMER
    fatal = _one([
        row for row in parsed_consumer["identity_failures"]
        if (row["step"], row["rk"], row["i"], row["j"], row["k"])
        == FATAL_CONSUMER
    ], "known T39/RK2 fatal consumer identity at (2,219,13)")
    producer_join = join_fatal_producers(producers, fatal)
    fatal_cell = [fatal_i, fatal_j, fatal_k]
    same_cell, pair_matches_callback, group_link_status, group_link = link_first_group_to_fatal(
        first_group, fatal_cell)
    group_cell = [first_group["i"], first_group["j"], first_group["k"]]
    fatal_stores = [
        row for row in parsed_consumer["store_failures"]
        if (row["step"], row["rk"], row["i"], row["j"], row["k"])
        == FATAL_CONSUMER
    ]
    final_hashes = {
        "closed_receipt_sha256": file_sha256(receipt_path),
        "group_capture": verify_capture_artifact(group_path, receipt),
        "producer_capture": verify_capture_artifact(producer_path, receipt),
        "consumer_capture": verify_capture_artifact(consumer_path, receipt),
    }
    if final_hashes != input_hashes:
        raise ValueError("receipt or capture artifact changed during postprocessing")
    first_group_report = dict(first_group)
    first_group_report["key"] = list(first_group["key"])
    first_group_report["hex"] = {key: list(value) for key, value in first_group["hex"].items()}
    return {
        "schema": "pr107_t39_group_consumer_producer_join_v1",
        "arm": receipt["arm"],
        "run_status": receipt["status"],
        "run_returncode": receipt["returncode"],
        "run_id": run_id,
        "final_completed_step": receipt.get("final_completed_step"),
        "executed_executable_sha256": receipt.get("executed_executable_sha256"),
        "hashes": input_hashes,
        "selection": {"group_timestep": 39, "group_rk": 2,
                      "known_fatal_consumer": {"timestep": fatal_step, "rk": fatal_rk,
                                                "i": fatal_i, "j": fatal_j, "k": fatal_k},
                      "producer_timestep": PRODUCER_EPOCH[0], "producer_rk": PRODUCER_EPOCH[1],
                      "producer_channels": list(PRODUCER_CHANNELS)},
        "group_capture": {"event_count": group["event_count"], "first_event_index": 0,
                          "first_event_key": list(first_group["key"]),
                          "cell": group_cell, "pair": first_group["pair"],
                          "group_predicate": first_group["group_predicate"],
                          "classification": first_group["classification"],
                          "store_failure_stage": first_group["store_failure_stage"],
                          "candidate64_hex": first_group["hex"]["HEX64_CANDIDATE"],
                          "first_event": first_group_report},
        "fatal_consumer": {"event_key": [fatal_step, fatal_rk, fatal_i, fatal_j, fatal_k],
                           "cell": fatal_cell,
                           "producer_identity_bounds": fatal["producer_identity"],
                           "source_r64_bits": fatal["r64_bits"][:2],
                           "recomputed_diffusion_r64_bits": fatal["r64_bits"][2:4],
                           "matching_store_failures": [
                               {"context": row["context"], "failure_stage": row["failure_stage"],
                                "candidate_bits64": row["candidate_bits64"]}
                               for row in fatal_stores]},
        "producer_join": producer_join,
        "group_same_cell_as_fatal_consumer": same_cell,
        "group_pair_matches_fatal_callback_pair4": pair_matches_callback,
        "group_fatal_link_status": group_link_status,
        "group_event_link_to_fatal_consumer": group_link,
        "interpretation_scope": (
            "The first T39/RK2 grouped failure is reported independently. It is linked to the "
            "known T39/RK2 fatal consumer only when both records have the same (i,j,k). The "
            "producer join is independently bound by the fatal consumer's T39/RK1 identity "
            "bounds and channels 7 and 8; this does not establish a full-domain group cause "
            "or a comparison to a T39 baseline state."),
        "parser_sha256": {
            "pr99_group_failure_capture": file_sha256(Path(pr99_group_failure_capture.__file__)),
            "pr92_source_replay": file_sha256(Path(pr92_source_replay.__file__)),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closed-receipt", required=True, type=Path)
    parser.add_argument("--group-raw", required=True, type=Path)
    parser.add_argument("--producer-raw", required=True, type=Path)
    parser.add_argument("--consumer-raw", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = build_report(args.closed_receipt, args.group_raw,
                          args.producer_raw, args.consumer_raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
