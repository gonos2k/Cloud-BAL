#!/usr/bin/env python3
"""Compose the frozen PR70 process patch with the selected KDM6 unit routing."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

SELECTED_SOURCE_SHA256 = "97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa"
TRANSFORMER_PATH = Path(__file__).with_name("pr69_transform_selected_kdm6.py")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_unit_transformer():
    spec = importlib.util.spec_from_file_location("pr69_transform_selected_kdm6", TRANSFORMER_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load unit transformer: {TRANSFORMER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kdm62d_bounds(source: str) -> tuple[int, int]:
    lowered = source.lower()
    start = lowered.index("   subroutine kdm62d(")
    end = lowered.index("   end subroutine kdm62d", start)
    return start, end


def inventory_all_density_uses(source: str, unit_transformer: Any) -> list[dict[str, Any]]:
    start, end = kdm62d_bounds(source)
    records: list[dict[str, Any]] = []
    for offset, line in enumerate(source[start:end].splitlines(), 1):
        code = line.split("!", 1)[0].lower()
        matches = list(re.finditer(r"\bden\s*\(", code))
        if not matches:
            continue
        if "rain_t_fixed,rain_t_process,den(i,k)" in code:
            role, action = "dry_number_to_mass_process_gate", "use dry carrier"
        elif "den(i,k)" in code:
            try:
                role, action = unit_transformer.density_role(line)
            except ValueError as error:
                raise SystemExit(
                    f"unclassified DEN reference on selected-source line {offset}: {line.strip()}"
                ) from error
            if action not in ("retain moist DEN", "retain moist DEN pending equation units", "use dry carrier"):
                raise SystemExit(f"unsupported DEN action on selected-source line {offset}: {action}")
        elif re.search(r"\bden\s*\(\s*its\s*,\s*k\s*\)", code):
            role, action = "moist_gas_density_velocity_input", "retain as gas_density"
        elif re.search(r"\bden\s*\(\s*its\s*:\s*ite\s*,\s*kts\s*\)", code):
            role, action = "moist_gas_density_trace_input", "retain as gas_density"
        else:
            raise SystemExit(f"unclassified DEN reference on selected-source line {offset}: {line.strip()}")
        records.append({
            "source_line_in_kdm62d": offset,
            "role": role,
            "action": action,
            "references": len(matches),
            "source": line.strip(),
        })
    if not records:
        raise SystemExit("selected KDM6 source has no inventoried DEN references")
    return records


def extend_density_role_profile(unit_transformer: Any) -> None:
    original_role = unit_transformer.density_role

    def density_role(line: str) -> tuple[str, str]:
        code = line.split("!", 1)[0].lower().replace(" ", "")
        if ("rain_t_fixed,rain_t_process,den(i,k)" in code or
                "den(i,k),pidnr,qmin,ncmin" in code):
            return "dry_number_to_mass_process_gate", "use dry carrier"
        return original_role(line)

    unit_transformer.density_role = density_role

    original_replace_once = unit_transformer.replace_once

    def replace_once(source: str, old: str, new: str, label: str) -> str:
        if label != "unit helpers":
            return original_replace_once(source, old, new, label)
        anchor = "    contains\n\n    subroutine kdm6_mass_volume_rate"
        if source.count(anchor) != 1:
            raise SystemExit("expected the module-level PR70 helper insertion anchor")
        helper_text = new[len(old):].strip("\n")
        replacement = "    contains\n\n" + helper_text + "\n\n    subroutine kdm6_mass_volume_rate"
        return source.replace(anchor, replacement, 1)

    unit_transformer.replace_once = replace_once


def apply_explicit_density_names(source: str, records: list[dict[str, Any]]) -> str:
    start, end = kdm62d_bounds(source)
    body = source[start:end]
    declaration = "   real, dimension(its:ite,kts:kte)   :: den_tmp, delz_tmp, den_carrier\n"
    if body.count(declaration) != 1:
        raise SystemExit("expected one transformed carrier declaration")
    body = body.replace(
        declaration,
        "   real, dimension(its:ite,kts:kte)   :: den_tmp, delz_tmp, dry_carrier_density\n"
        "   real, dimension(its:ite,kts:kte) :: gas_density\n",
        1,
    )
    body = body.replace("den_carrier", "dry_carrier_density")

    code_lines: list[str] = []
    alias_line = "   gas_density = den(its:ite,kts:kte)\n"
    for line in body.splitlines(keepends=True):
        code, separator, comment = line.partition("!")
        code = re.sub(r"\bden\s*\(", "gas_density(", code, flags=re.IGNORECASE)
        code_lines.append(code + (separator + comment if separator else ""))
    body = "".join(code_lines)

    anchor = "   kte_in = kte\n"
    if body.count(anchor) != 1:
        raise SystemExit("expected one KDM62D gas-density initialization anchor")
    body = body.replace(anchor, anchor + alias_line, 1)
    return source[:start] + body + source[end:]


def audit_transformed_density(source: str, records: list[dict[str, Any]]) -> dict[str, int]:
    start, end = kdm62d_bounds(source)
    body = source[start:end]
    gas_count = len(re.findall(r"\bgas_density\s*\(", body, re.IGNORECASE))
    carrier_count = len(re.findall(r"\bdry_carrier_density\s*\(", body, re.IGNORECASE))
    raw_den_count = len(re.findall(r"\bden\s*\(", body, re.IGNORECASE))
    alias = "gas_density = den(its:ite,kts:kte)"
    if raw_den_count != 1 or alias not in body:
        raise SystemExit("unrouted DEN references remain in KDM62D")

    expected_gas = sum(
        int(record["references"])
        for record in records
        if record["action"] in ("retain moist DEN", "retain moist DEN pending equation units", "retain as gas_density")
    )
    expected_carrier = sum(
        int(record["references"])
        for record in records
        if record["action"] == "use dry carrier"
    )
    # Unit conversion adds one moist-density input and replaces the legacy DEND seed.
    if gas_count != expected_gas + 1 or carrier_count != expected_carrier + 1:
        raise SystemExit(
            f"density routing count mismatch: gas {gas_count}/{expected_gas + 1}, "
            f"dry carrier {carrier_count}/{expected_carrier + 1}"
        )
    if "qi0 =" not in body.lower():
        raise SystemExit("unresolved qi0 density role disappeared from selected KDM6")
    return {
        "gas_density_references": gas_count,
        "dry_carrier_density_references_including_initialization": carrier_count,
        "intentional_raw_den_alias_references": raw_den_count,
        "unresolved_qi0_retained": 1,
    }


def compose(source_path: Path, process_patch: Path, output_path: Path,
            expected_patch_sha256: str) -> dict[str, Any]:
    if source_path.resolve() == output_path.resolve():
        raise SystemExit("refusing to overwrite or alias the retained selected source")
    if output_path.exists():
        raise SystemExit(f"refusing to overwrite existing composed output: {output_path}")
    source_bytes = source_path.read_bytes()
    patch_bytes = process_patch.read_bytes()
    source_digest = sha256(source_bytes)
    patch_digest = sha256(patch_bytes)
    if source_digest != SELECTED_SOURCE_SHA256:
        raise SystemExit(f"selected source SHA-256 mismatch: {source_digest}")
    if patch_digest != expected_patch_sha256:
        raise SystemExit(f"PR70 process patch SHA-256 mismatch: {patch_digest}")

    with tempfile.TemporaryDirectory(prefix="pr70_compose_") as scratch:
        scratch_path = Path(scratch)
        staged_source = scratch_path / source_path.name
        staged_source.write_bytes(source_bytes)
        result = subprocess.run(
            ["patch", "--fuzz=0", "-p0", "-d", str(scratch_path)],
            input=patch_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit("PR70 patch failed at fuzz=0:\n" + result.stdout.decode(errors="replace"))
        process_bytes = staged_source.read_bytes()
        process_digest = sha256(process_bytes)

    process_source = process_bytes.decode("utf-8")
    transform = load_unit_transformer()
    extend_density_role_profile(transform)
    inventory = inventory_all_density_uses(process_source, transform)
    unit_source, _, role_counts = transform.transform(process_source)
    composed = apply_explicit_density_names(unit_source, inventory)
    routing_counts = audit_transformed_density(composed, inventory)
    composed_bytes = composed.encode("utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as stream:
        stream.write(composed_bytes)
    inventory_path = output_path.with_suffix(".density_roles.json")
    receipt = {
        "selected_source_sha256": source_digest,
        "process_patch_sha256": patch_digest,
        "process_patched_source_sha256": process_digest,
        "composed_source_sha256": sha256(composed_bytes),
        "unit_transformer_sha256": sha256(TRANSFORMER_PATH.read_bytes()),
        "unit_role_counts": role_counts,
        "routing_counts": routing_counts,
        "density_uses": inventory,
    }
    with inventory_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("process_patch", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-process-patch-sha256", required=True)
    args = parser.parse_args()
    receipt = compose(args.source, args.process_patch, args.output,
                      args.expected_process_patch_sha256)
    print(f"SELECTED_SOURCE_SHA256 {receipt['selected_source_sha256']}")
    print(f"PROCESS_PATCH_SHA256 {receipt['process_patch_sha256']}")
    print(f"PROCESS_PATCHED_SOURCE_SHA256 {receipt['process_patched_source_sha256']}")
    print(f"COMPOSED_SOURCE_SHA256 {receipt['composed_source_sha256']}")
    print(f"DENSITY_ROUTING_COUNTS {json.dumps(receipt['routing_counts'], sort_keys=True)}")


if __name__ == "__main__":
    main()
