#!/usr/bin/env python3
"""Compose frozen PR70 source with the PR71 ProgB output-contract patch."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

PR70_SOURCE_SHA256 = "97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa"
PR70_PROCESS_PATCH_SHA256 = "5f1b75925ec803838f5b3cfa81012336f4d21727073c5d8c0703fb70ddc37670"
PR70_COMPOSED_SHA256 = "487afbf064b6a3598ecb12248224fc3b91c77e1b0ed921d0e0e8130cacb9b583"
PR70_COMPOSER = Path(__file__).with_name("pr70_compose_selected_kdm6.py")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compose(source: Path, process_patch: Path, validity_patch: Path,
            output: Path, expected_validity_patch_sha256: str) -> dict[str, Any]:
    for path in (source, process_patch, validity_patch):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"input must be a regular file: {path}")
    output_inventory = output.with_suffix(output.suffix + ".composition.json")
    if output.exists() or output.is_symlink():
        raise SystemExit(f"refusing to overwrite existing composed output: {output}")
    if output_inventory.exists() or output_inventory.is_symlink():
        raise SystemExit(f"refusing to overwrite existing composition receipt: {output_inventory}")
    if output.resolve() in (source.resolve(), process_patch.resolve(), validity_patch.resolve()):
        raise SystemExit("refusing to alias the composed output with an input")

    source_hash = sha256(source.read_bytes())
    process_hash = sha256(process_patch.read_bytes())
    validity_hash = sha256(validity_patch.read_bytes())
    if source_hash != PR70_SOURCE_SHA256:
        raise SystemExit(f"PR70 selected source SHA-256 mismatch: {source_hash}")
    if process_hash != PR70_PROCESS_PATCH_SHA256:
        raise SystemExit(f"PR70 process patch SHA-256 mismatch: {process_hash}")
    if validity_hash != expected_validity_patch_sha256:
        raise SystemExit(f"PR71 output-contract patch SHA-256 mismatch: {validity_hash}")

    with tempfile.TemporaryDirectory(prefix="pr71_compose_kdm6_") as temporary:
        stage = Path(temporary)
        pr70_source = stage / "composed_pr70.F"
        result = subprocess.run(
            ["python3", str(PR70_COMPOSER), str(source), str(process_patch),
             str(pr70_source), "--expected-process-patch-sha256", PR70_PROCESS_PATCH_SHA256],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        if result.returncode:
            raise SystemExit("PR70 composition failed:\n" + result.stdout.decode(errors="replace"))
        pr70_bytes = pr70_source.read_bytes()
        pr70_hash = sha256(pr70_bytes)
        if pr70_hash != PR70_COMPOSED_SHA256:
            raise SystemExit(f"PR70 composed source SHA-256 mismatch: {pr70_hash}")

        # The generator records the PR70 module basename in its unified diff.
        staged_source = pr70_source
        applied = subprocess.run(
            ["patch", "--fuzz=0", "-p0", "-d", str(stage)],
            input=validity_patch.read_bytes(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        if applied.returncode:
            raise SystemExit("PR71 output-contract patch failed at fuzz=0:\n" +
                             applied.stdout.decode(errors="replace"))
        final_bytes = staged_source.read_bytes()

        pr70_inventory_path = pr70_source.with_suffix(".density_roles.json")
        pr70_inventory = json.loads(pr70_inventory_path.read_text(encoding="utf-8"))

    output.parent.mkdir(parents=True, exist_ok=True)
    # Recheck after composition in case another process created either path.
    if output.exists() or output.is_symlink() or output_inventory.exists() or output_inventory.is_symlink():
        raise SystemExit("refusing to overwrite composed output or receipt created during composition")
    with output.open("xb") as stream:
        stream.write(final_bytes)
    receipt = {
        "schema": "pr71_same_source_composition_v1",
        "selected_source_sha256": source_hash,
        "pr70_process_patch_sha256": process_hash,
        "pr70_composed_source_sha256": pr70_hash,
        "pr71_output_validity_patch_sha256": validity_hash,
        "pr71_composed_source_sha256": sha256(final_bytes),
        "pr70_density_routing_counts": pr70_inventory["routing_counts"],
        "pr70_density_role_inventory": pr70_inventory,
        "pr70_composition_log": result.stdout.decode(errors="replace"),
        "pr71_patch_application_log": applied.stdout.decode(errors="replace"),
        "output_source": str(output),
    }
    with output_inventory.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("process_patch", type=Path)
    parser.add_argument("validity_patch", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-validity-patch-sha256", required=True)
    args = parser.parse_args()
    receipt = compose(args.source, args.process_patch, args.validity_patch,
                      args.output, args.expected_validity_patch_sha256)
    print(f"PR70_COMPOSED_SOURCE_SHA256 {receipt['pr70_composed_source_sha256']}")
    print(f"PR71_VALIDITY_PATCH_SHA256 {receipt['pr71_output_validity_patch_sha256']}")
    print(f"PR71_COMPOSED_SOURCE_SHA256 {receipt['pr71_composed_source_sha256']}")
    print(f"COMPOSITION_RECEIPT {args.output.with_suffix(args.output.suffix + '.composition.json')}")


if __name__ == "__main__":
    main()
