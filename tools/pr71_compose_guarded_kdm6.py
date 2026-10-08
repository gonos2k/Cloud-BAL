#!/usr/bin/env python3
"""Compose PR70, PR71 output validity, and checked substep-count sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pr71_compose_selected_kdm6 import compose as compose_base

BASE_SOURCE_SHA256 = "5de1884ab59e3de30a3e4ef1d8317405f1ba0591cf7ed9aa6fbca574d5233f41"
STEP_COUNT_PATCH_SHA256 = "7bc37047bf616b50ebb506f130a2f1f0535e0a5afc26bb26183a27ee188ebb24"
CHECKED_SOURCE_SHA256 = "6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compose_guarded(source: Path, process_patch: Path, validity_patch: Path,
                    step_count_patch: Path, output: Path,
                    expected_validity_patch_sha256: str,
                    expected_step_count_patch_sha256: str) -> dict[str, Any]:
    inventory_path = output.with_suffix(output.suffix + ".composition.json")
    for path in (output, inventory_path):
        if path.exists() or path.is_symlink():
            raise SystemExit(f"refusing to overwrite guarded source or receipt: {path}")
    for path in (source, process_patch, validity_patch, step_count_patch):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"input must be a regular non-symlink file: {path}")

    validity_hash = sha256(validity_patch.read_bytes())
    count_hash = sha256(step_count_patch.read_bytes())
    if validity_hash != expected_validity_patch_sha256:
        raise SystemExit(f"PR71 output-contract patch SHA-256 mismatch: {validity_hash}")
    if count_hash != expected_step_count_patch_sha256:
        raise SystemExit(f"PR71 step-count patch SHA-256 mismatch: {count_hash}")

    with tempfile.TemporaryDirectory(prefix="pr71_compose_guarded_") as temporary:
        stage = Path(temporary)
        base_source = stage / "frozen_base.F"
        base_receipt = compose_base(
            source, process_patch, validity_patch, base_source,
            expected_validity_patch_sha256,
        )
        if base_receipt["pr71_composed_source_sha256"] != BASE_SOURCE_SHA256:
            raise SystemExit("base PR71 source differs from the frozen count-guard input")
        if base_source.name != "frozen_base.F":
            raise SystemExit("internal base source filename mismatch")
        result = subprocess.run(
            ["patch", "--fuzz=0", "-p0", "-d", str(stage)],
            input=step_count_patch.read_bytes(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        if result.returncode:
            raise SystemExit("PR71 step-count patch failed at fuzz=0:\n" +
                             result.stdout.decode(errors="replace"))
        checked_source = base_source
        final_bytes = checked_source.read_bytes()
        final_hash = sha256(final_bytes)
        if final_hash != CHECKED_SOURCE_SHA256:
            raise SystemExit(f"checked PR71 source SHA-256 mismatch: {final_hash}")
        base_inventory = json.loads(
            base_source.with_suffix(base_source.suffix + ".composition.json").read_text()
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink() or inventory_path.exists() or inventory_path.is_symlink():
        raise SystemExit("refusing to overwrite guarded source or receipt created during composition")
    receipt = {
        "schema": "pr71_guarded_same_source_composition_v1",
        "base_pr71_source_sha256": base_inventory["pr71_composed_source_sha256"],
        "base_composition_receipt": base_inventory,
        "step_count_patch_sha256": count_hash,
        "step_count_patch_application_log": result.stdout.decode(errors="replace"),
        "checked_source_sha256": final_hash,
        "checked_source": str(output),
    }
    with output.open("xb") as stream:
        stream.write(final_bytes)
    with inventory_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("process_patch", type=Path)
    parser.add_argument("validity_patch", type=Path)
    parser.add_argument("step_count_patch", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-validity-patch-sha256", required=True)
    parser.add_argument("--expected-step-count-patch-sha256", required=True)
    args = parser.parse_args()
    receipt = compose_guarded(
        args.source, args.process_patch, args.validity_patch, args.step_count_patch,
        args.output, args.expected_validity_patch_sha256,
        args.expected_step_count_patch_sha256,
    )
    print(f"PR71_BASE_SOURCE_SHA256 {receipt['base_pr71_source_sha256']}")
    print(f"PR71_STEP_COUNT_PATCH_SHA256 {receipt['step_count_patch_sha256']}")
    print(f"PR71_CHECKED_SOURCE_SHA256 {receipt['checked_source_sha256']}")
    print(f"COMPOSITION_RECEIPT {args.output.with_suffix(args.output.suffix + '.composition.json')}")


if __name__ == "__main__":
    main()
