#!/usr/bin/env python3
"""Bind the existing PR84 v2 moment prior to one actual HYDRO real input."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from initialize_native_moments import (
    PR84_EXPECTED_POLICY_SHA256,
    PR94_HYDRO_POLICY_ID,
    PR94_HYDRO_POLICY_SCHEMA,
    _validate_same13_policy_file,
    initialize_same13_copy,
)


BASE_POLICY = Path(__file__).resolve().parents[1] / "docs/PR84_NATIVE_MOMENT_POLICY_20261013.json"
REAL_INPUT_RECEIPT_SCHEMA = "pr94_hydro_real_input_receipt_v1"
HYDRO_CANDIDATE_SHA256 = "5e69e8b1c2f36119cead2ca4b6ca632a8898a2fa1082d9faa9dd1ea5075b7535"
HYDRO_CANDIDATE_SHA256S = {
    HYDRO_CANDIDATE_SHA256,
    "97a98c5bb05a8dc70528c2b6c025ae8cb359ed46f23b7d3c28941535f71ae9d6",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_receipt(path: Path) -> tuple[dict[str, Any], Path, str]:
    receipt_path = path.resolve(strict=True)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (receipt.get("schema") != REAL_INPUT_RECEIPT_SCHEMA
            or receipt.get("status") != "PASS_HYDRO_REAL_INPUT"
            or receipt.get("role") != "HYDRO"):
        raise ValueError("expected a successful PR94 HYDRO real-input receipt")
    candidate = receipt["source_candidate"]
    if (candidate.get("mode") != "HYDRO"
            or candidate.get("sha256") not in HYDRO_CANDIDATE_SHA256S):
        raise ValueError("source candidate is not a pinned PR94 actual HYDRO product")
    candidate_path = Path(candidate["path"]).resolve(strict=True)
    if sha256(candidate_path) != candidate["sha256"]:
        raise ValueError("HYDRO source candidate differs from its stage receipt")
    wrfinput = Path(receipt["wrfinput"]["path"]).resolve(strict=True)
    expected = receipt["wrfinput"]["sha256"]
    if sha256(wrfinput) != expected:
        raise ValueError("HYDRO wrfinput hash differs from its source receipt")
    for item in receipt.get("source_chain_receipts", []):
        source_receipt = Path(item["path"]).resolve(strict=True)
        if sha256(source_receipt) != item["sha256"]:
            raise ValueError(f"HYDRO source-chain receipt changed: {source_receipt}")
    return receipt, wrfinput, expected


def write_policy(receipt_path: Path, output_path: Path,
                 base_policy_path: Path = BASE_POLICY) -> dict[str, Any]:
    base_path = base_policy_path.resolve(strict=True)
    if sha256(base_path) != PR84_EXPECTED_POLICY_SHA256:
        raise ValueError("frozen PR84 v2 policy hash mismatch")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    receipt, wrfinput, input_hash = load_receipt(receipt_path)
    output = output_path.resolve()
    if output.exists():
        raise ValueError(f"policy output already exists: {output}")
    policy = json.loads(json.dumps(base))
    policy["schema"] = PR94_HYDRO_POLICY_SCHEMA
    policy["policy_id"] = PR94_HYDRO_POLICY_ID
    policy["preflight"]["authorized_source_inputs"] = [
        *policy["preflight"]["authorized_source_inputs"],
        {"role": "HYDRO", "sha256": input_hash},
    ]
    policy["hydro_input_binding"] = {
        "source_receipt_path": str(receipt_path.resolve(strict=True)),
        "source_receipt_sha256": sha256(receipt_path.resolve(strict=True)),
        "wrfinput_path": str(wrfinput),
        "wrfinput_sha256": input_hash,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(policy, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    # Keep the receipt object used to construct the policy live through the write.
    if receipt.get("wrfinput", {}).get("sha256") != input_hash:
        raise ValueError("HYDRO receipt changed while making the policy")
    return policy


def initialize_hydro(receipt_path: Path, policy_path: Path,
                     output_path: Path, initializer_receipt: Path) -> dict[str, Any]:
    _, wrfinput, _ = load_receipt(receipt_path)
    return initialize_same13_copy(
        wrfinput, output_path, initializer_receipt, policy_path=policy_path
    )


def write_final_receipt(stage_path: Path, policy_path: Path,
                        initialized_receipt_path: Path,
                        output_path: Path) -> dict[str, Any]:
    stage, _, _ = load_receipt(stage_path)
    policy_path = policy_path.resolve(strict=True)
    initialized_receipt_path = initialized_receipt_path.resolve(strict=True)
    wrfbdy = Path(stage["wrfbdy"]["path"]).resolve(strict=True)
    if sha256(wrfbdy) != stage["wrfbdy"]["sha256"]:
        raise ValueError("HYDRO boundary input changed after staging")
    contract_boundary = stage.get("comparison_contract", {}).get("boundary_sha256")
    if contract_boundary != stage["wrfbdy"]["sha256"]:
        raise ValueError("HYDRO comparison-contract boundary hash differs from staged boundary")
    initialized = json.loads(initialized_receipt_path.read_text(encoding="utf-8"))
    policy = _validate_same13_policy_file(policy_path)
    stage_input = Path(stage["wrfinput"]["path"]).resolve(strict=True)
    stage_input_sha = stage["wrfinput"]["sha256"]
    policy_binding = policy.get("hydro_input_binding", {})
    if (policy_binding.get("source_receipt_path") != str(stage_path.resolve(strict=True))
            or policy_binding.get("source_receipt_sha256") != sha256(stage_path.resolve(strict=True))
            or policy_binding.get("wrfinput_path") != str(stage_input)
            or policy_binding.get("wrfinput_sha256") != stage_input_sha):
        raise ValueError("HYDRO moment policy is not bound to this stage receipt and raw input")
    if (initialized.get("source_input_role") != "HYDRO"
            or Path(initialized.get("source_input", "")).resolve() != stage_input
            or initialized.get("source_input_sha256") != stage_input_sha
            or initialized.get("policy_sha256") != sha256(policy_path)
            or initialized.get("hydro_input_binding") != policy_binding):
        raise ValueError("HYDRO initializer receipt is not bound to this stage and policy")
    output_wrfinput = Path(initialized["output_input"]).resolve(strict=True)
    if (initialized.get("status") != "RESEARCH_PRIOR_CREATED"
            or initialized.get("source_input_role") != "HYDRO"
            or initialized.get("policy_schema") != PR94_HYDRO_POLICY_SCHEMA
            or initialized.get("output_input_sha256") != sha256(output_wrfinput)):
        raise ValueError("HYDRO moment initializer receipt did not pass identity checks")
    receipt = {
        "schema": "pr94_hydro_native_input_v1",
        "status": "PASS_HYDRO_NATIVE_INPUT",
        "role": "HYDRO",
        "wrfinput": {"path": str(output_wrfinput), "sha256": sha256(output_wrfinput)},
        "wrfbdy": {"path": str(wrfbdy), "sha256": stage["wrfbdy"]["sha256"]},
        "source_candidate": stage["source_candidate"],
        "moment_policy": {
            "path": str(policy_path), "sha256": sha256(policy_path),
            "parent_policy_sha256": PR84_EXPECTED_POLICY_SHA256,
        },
        "initialization_receipt": {
            "path": str(initialized_receipt_path),
            "sha256": sha256(initialized_receipt_path),
        },
        "source_chain_receipts": stage.get("source_chain_receipts", []),
        "comparison_contract": stage["comparison_contract"],
    }
    output = output_path.resolve()
    if output.exists():
        raise ValueError(f"final receipt already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    policy_parser = subparsers.add_parser("make-policy")
    policy_parser.add_argument("--hydro-input-receipt", type=Path, required=True)
    policy_parser.add_argument("--policy-output", type=Path, required=True)
    initialize_parser = subparsers.add_parser("initialize")
    initialize_parser.add_argument("--hydro-input-receipt", type=Path, required=True)
    initialize_parser.add_argument("--policy", type=Path, required=True)
    initialize_parser.add_argument("--output", type=Path, required=True)
    initialize_parser.add_argument("--receipt", type=Path, required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--stage-receipt", type=Path, required=True)
    finalize_parser.add_argument("--policy", type=Path, required=True)
    finalize_parser.add_argument("--initialization-receipt", type=Path, required=True)
    finalize_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "make-policy":
            policy = write_policy(args.hydro_input_receipt, args.policy_output)
            print(f"policy_sha256={sha256(args.policy_output)}")
            print(f"source_sha256={policy['hydro_input_binding']['wrfinput_sha256']}")
        elif args.command == "initialize":
            result = initialize_hydro(
                args.hydro_input_receipt, args.policy, args.output, args.receipt
            )
            print(f"{result['status']}: {result.get('output_input') or 'no candidate written'}")
        else:
            receipt = write_final_receipt(
                args.stage_receipt, args.policy, args.initialization_receipt, args.output
            )
            print(f"{receipt['status']}: {receipt['wrfinput']['sha256']}")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
