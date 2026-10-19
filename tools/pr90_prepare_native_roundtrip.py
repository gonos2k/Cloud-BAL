#!/usr/bin/env python3
"""Prepare a hash-bound C5 diagnostic or warm-output-contract source set."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C5_EM_SHA256 = "0d3b1fe91a01c747a2339487695d82c7109ad4df3da5cbc561ca338c1fecf91d"
C5_CORE_SHA256 = "aef7f536f85983f4fcb9dd266fafc6c5e900dbf0e1c485b1afd55a8dee56bd51"
C5_SUPPORT_SHA256 = "98f9f546b6273609a261c8ec39c2cb578d301eaff7ce0b829bb6e2dad3aea348"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_embedded_core(source: str, core: str) -> str:
    end = source.index("end module cloud_bal_joint_transport")
    end += len("end module cloud_bal_joint_transport\n")
    previous = source[:end]
    if hashlib.sha256(previous.encode()).hexdigest() != C5_CORE_SHA256:
        raise ValueError("C5 embedded joint transport identity mismatch")
    return core + source[end:]


def replace_public_helper(source: str, helper: str) -> str:
    start = source.index("subroutine pr87_number_public_store(")
    ending = "end subroutine pr87_number_public_store"
    end = source.index(ending, start) + len(ending)
    next_helper = helper.index("\nsubroutine pr87_number_volume_store(")
    replacement = helper[:next_helper].rstrip().replace(
        "pr87_rain_public_store", "pr87_number_public_store")
    return source[:start] + replacement + source[end:]


def prepare(parent: Path, support: Path, output: Path, columns: bool = False,
            producer_trace: bool = False, warm_output: bool = False,
            final_rain_bounds: bool = False) -> dict:
    if final_rain_bounds:
        warm_output = True
    baseline = json.loads(parent.read_text())
    if baseline.get("identity") != "PR89-C5":
        raise ValueError("expected the preserved C5 source manifest")
    overrides = baseline["source_overrides"].copy()
    for member, name in overrides.items():
        if sha256(Path(name)) != baseline["source_sha256"][member]:
            raise ValueError(f"C5 source changed: {member}")
    em = Path(overrides["module_em.o"])
    if sha256(em) != C5_EM_SHA256 or sha256(support) != C5_SUPPORT_SHA256:
        raise ValueError("C5 EM or support source identity mismatch")
    core = ROOT / "src/common/cloud_bal_joint_transport.f90"
    helper = ROOT / "tools/pr87_rain_public_store.f90"
    prepared_em = replace_embedded_core(em.read_text(), core.read_text())
    prepared_support = replace_public_helper(support.read_text(), helper.read_text())
    kdm = Path(overrides["module_mp_kdm6.o"])
    prepared_kdm = kdm.read_text()
    if warm_output:
        from pr90_warm_rain_output import add_unreconstructed_rain_output_check
        prepared_kdm = add_unreconstructed_rain_output_check(prepared_kdm)
    if final_rain_bounds:
        from pr90_rain_final_psd import add_exact_final_rain_bound_check
        prepared_kdm = add_exact_final_rain_bound_check(prepared_kdm)
    if producer_trace:
        from pr90_rain_producer_trace import add_t7_trace
        prepared_kdm = add_t7_trace(
            prepared_kdm, expected_sha256=hashlib.sha256(prepared_kdm.encode()).hexdigest())
    if columns:
        from pr90_cold_column_summary import add_column_summary
        prepared_kdm = add_column_summary(
            prepared_kdm, expected_sha256=hashlib.sha256(prepared_kdm.encode()).hexdigest())
    output.mkdir(parents=True, exist_ok=False)
    em_output = output / "module_em.F"
    em_output.write_text(prepared_em)
    support_output = output / "pr90_cycle_support.f90"
    support_output.write_text(prepared_support)
    overrides["module_em.o"] = str(em_output.resolve())
    if columns or producer_trace or warm_output:
        kdm_output = output / "module_mp_kdm6.F"
        kdm_output.write_text(prepared_kdm)
        overrides["module_mp_kdm6.o"] = str(kdm_output.resolve())
    result = {
        "schema": "pr90_native_sources_v1",
        "identity": ("PR90-C7" if final_rain_bounds else
                     "PR90-C6" if warm_output else
                     "PR90 column diagnostics" if columns else "PR90 diagnostic-only C5"),
        "base_commit": "3bc7bb8df6a100b60c6f8908ad93a7c3d981f360",
        "parent_manifest": str(parent.resolve()),
        "parent_manifest_sha256": sha256(parent),
        "source_overrides": overrides,
        "source_sha256": {key: sha256(Path(value)) for key, value in overrides.items()},
        "extra_support_source": str(support_output.resolve()),
        "extra_support_sha256": sha256(support_output),
        "parent_support_source": str(support.resolve()),
        "parent_support_sha256": sha256(support),
        "maintained_core_sha256": sha256(core),
        "public_store_helper_sha256": sha256(helper),
        "column_summary_enabled": columns,
        "producer_trace_enabled": producer_trace,
        "warm_output_contract_enabled": warm_output,
        "final_rain_bounds_enabled": final_rain_bounds,
        "physics_changed": warm_output or final_rain_bounds,
        "scope": ("selected-object partial host; warm packet output admission and exact final rain PSD reconstruction after the last number cap; "
                  "no initial-input/prior/FP change" if final_rain_bounds else
                  "selected-object partial host; warm packet output admission; "
                  "no initial-input/prior/FP change" if warm_output else
                  "selected-object partial host; failure diagnostics; no initial-input/prior/FP change"),
    }
    (output / "sources.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "overrides.json").write_text(json.dumps(overrides, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--support", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns", action="store_true")
    parser.add_argument("--producer-trace", action="store_true")
    parser.add_argument("--warm-output", action="store_true")
    parser.add_argument("--final-rain-bounds", action="store_true",
                        help="apply warm output admission and final rain PSD bound correction")
    args = parser.parse_args()
    result = prepare(args.parent, args.support, args.output, args.columns,
                     args.producer_trace, args.warm_output, args.final_rain_bounds)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
