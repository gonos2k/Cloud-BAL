#!/usr/bin/env python3
"""Refresh only derived thermo outputs; verify every fixed input pin unchanged."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/pr101_cloud_thermo_20261023"
SUMMARY = "docs/evidence/pr101_cloud_thermo_20261023/four_arm_summary.json"
BASE_SOURCE = ("/var/tmp/pr100_qc_observer_build_fresh_20261022/src/module_mp_kdm6_pr100.f90",
               "0c76fdae6e58e336dfafd581779a0979415e7b0fa64c30f701d1e22594d3e2a1")
GENERATED_SOURCE = ("/var/tmp/pr101_cloud_thermo_private_20261023/module_mp_kdm6_pr101_r64.f90",
                    "f7ef82b945c409ea2c54ce88139f544250c9360af611fdd8515cbae8e23c3dca")
PROFILE = ("tests/intel_toolchain.sh",
           "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4")
MODULE_INVENTORY = ("/var/tmp/pr101_cloud_thermo_build_20261023_r64/precompile_seed_inventory.json",
                    "658a31c3359f1b091c9fe99f4d700b60fb40deb54b847187d3555aac83c0da5a")
EXECUTABLE = ("/var/tmp/pr101_cloud_thermo_build_20261023_r64/link/pr101_cloud_thermo_replay.exe",
              "0fa1b8d44dc2a1fe9f438351c10f0e07e707e8c22c7850f32d54b484a12a3622")
BUILD_PLAN = ("docs/evidence/pr101_cloud_thermo_20261023/build_r64/build_plan.json",
              "65478f6d00648fc62cd36734a49e4445571d92920f7bf561aa8f5aa510210a69")
DERIVED_PATHS = {
    SUMMARY,
    "docs/PR101_CLOUD_THERMO_20261023.md",
    "docs/evidence/pr101_cloud_thermo_20261023/build_r64/link_inputs_post_link.json",
    "docs/evidence/pr101_cloud_thermo_20261023/build_r64/stager_recheck.json",
    "docs/evidence/pr101_cloud_thermo_20261023/build_r64/reproducibility_readback.json",
    "tools/pr101_cloud_thermo_aggregate.py",
    "tests/test_pr101_cloud_thermo_aggregate.py",
    "tools/pr101_cloud_thermo_refresh_manifest.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def verify_file_pin(path: str, expected: str) -> None:
    resolved = resolve(path)
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    actual = sha256(resolved)
    if actual != expected:
        raise ValueError(f"fixed input hash mismatch: {path}: {actual} != {expected}")


def output_record(path: str) -> dict:
    resolved = resolve(path)
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return {"path": path, "sha256": sha256(resolved)}


def verify_pairs(value, location="manifest") -> int:
    """Read-only verification; never repairs a stale input hash."""
    checked = 0
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            verify_file_pin(value["path"], value["sha256"])
            checked += 1
        for key, child in value.items():
            checked += verify_pairs(child, f"{location}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            checked += verify_pairs(child, f"{location}/{index}")
    return checked


def refresh_derived_pairs(value, location="manifest") -> int:
    """Refresh explicitly derived artifacts; verify every other path/hash pair."""
    changed = 0
    if isinstance(value, dict):
        path = value.get("path")
        digest = value.get("sha256")
        if isinstance(path, str) and isinstance(digest, str):
            normalized = Path(path)
            key = normalized.as_posix() if normalized.is_absolute() else normalized.as_posix()
            if key in DERIVED_PATHS:
                resolved = resolve(path)
                if not resolved.is_file():
                    raise FileNotFoundError(resolved)
                value["sha256"] = sha256(resolved)
                changed += 1
            else:
                verify_file_pin(path, digest)
        for name, child in value.items():
            changed += refresh_derived_pairs(child, f"{location}/{name}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            changed += refresh_derived_pairs(child, f"{location}/{index}")
    return changed


def verify_fixed_build_and_replay_inputs(main: dict) -> None:
    for path, digest in (BASE_SOURCE, GENERATED_SOURCE, PROFILE, MODULE_INVENTORY, EXECUTABLE):
        verify_file_pin(path, digest)
    if (main["input_prepared_source"]["path"] != BASE_SOURCE[0]
            or main["input_prepared_source"]["sha256"] != BASE_SOURCE[1]):
        raise ValueError("manifest prepared-source path/hash pin changed")
    if main["private_generated_source"]["sha256"] != GENERATED_SOURCE[1]:
        raise ValueError("manifest generated-source hash pin changed")
    build = main["build"]
    profile_pin = build.get("profile", {"path": build.get("profile_path"), "sha256": build.get("profile_sha256")})
    module_pin = build.get("precompile_module_inventory", {
        "path": "docs/evidence/pr101_cloud_thermo_20261023/build_r64/precompile_seed_inventory.json",
        "sha256": build.get("precompile_module_inventory_sha256")})
    executable_pin = build.get("executable", {"path": EXECUTABLE[0], "sha256": build.get("executable_sha256")})
    if (resolve(profile_pin["path"]) != resolve(PROFILE[0]) or profile_pin["sha256"] != PROFILE[1]
            or module_pin["sha256"] != MODULE_INVENTORY[1]
            or executable_pin["path"] != EXECUTABLE[0] or executable_pin["sha256"] != EXECUTABLE[1]
            or build["module_seed_count"] != 30
            or build["compile_rc"] != 0 or build["link_rc"] != 0):
        raise ValueError("fixed build metadata pin changed")
    pins_path = EVIDENCE / "aggregation_inputs.json"
    pins = json.loads(pins_path.read_text())
    if set(pins.get("arms", {})) != {"OFF", "HYDRO", "COUPLED", "P20"}:
        raise ValueError("aggregation inputs must pin exactly the four required arms")
    verify_file_pin("docs/evidence/pr101_cloud_thermo_20261023/aggregation_inputs.json",
                    main["files"]["aggregation_inputs"]["sha256"])
    plan = json.loads((EVIDENCE / "build_r64/build_plan.json").read_text())
    verify_file_pin(BUILD_PLAN[0], BUILD_PLAN[1])
    if (plan["source_sha256"] != GENERATED_SOURCE[1]
            or plan["profile_sha256"] != PROFILE[1]
            or plan["module_count"] != 30
            or plan["module_search_paths"] != ["/var/tmp/pr101_cloud_thermo_build_20261023_r64/mod"]
            or plan["compile"]["returncode"] != 0 or plan["link"]["returncode"] != 0
            or plan["link"]["executable_sha256"] != EXECUTABLE[1]):
        raise ValueError("retained build-plan source/profile/module/output pins changed")
    inventory = json.loads(Path(MODULE_INVENTORY[0]).read_text())
    if inventory.get("count") != 30 or len(inventory.get("modules", [])) != 30:
        raise ValueError("retained precompile module inventory is not the pinned 30-module set")
    link_inventory = json.loads((EVIDENCE / "build_r64/link_inputs_post_link.json").read_text())
    if link_inventory.get("build_time_hash_pins_available") is not False:
        raise ValueError("link input inventory must retain its post-link-only limitation")
    for item in link_inventory["explicit_object_archive_paths"]:
        if item.get("exists_at_post_link_readback"):
            verify_file_pin(item["path"], item["sha256"])
    for arm, pin in pins["arms"].items():
        for record in (pin["manifest"], pin["receipt"], pin["capture"]):
            verify_file_pin(record["path"], record["sha256"])
        receipt = json.loads(resolve(pin["receipt"]["path"]).read_text())
        guarded = json.loads(resolve(pin["manifest"]["path"]).read_text())
        bound_plan = [entry for entry in guarded["bindings"] if entry["path"] == str(ROOT / BUILD_PLAN[0])]
        if len(bound_plan) != 1 or bound_plan[0]["sha256"] != BUILD_PLAN[1]:
            raise ValueError(f"{arm}: guarded manifest does not retain the frozen build-plan binding")
        if (receipt["status"] != "COMPLETE" or receipt["returncode"] != 0
                or receipt["manifest_sha256"] != pin["manifest"]["sha256"]
                or receipt["artifacts"]["pr101_cloud_thermo.raw"]["sha256"] != pin["capture"]["sha256"]):
            raise ValueError(f"{arm}: fixed replay receipt/input binding changed")


def refresh() -> dict:
    revision_path = EVIDENCE / "source_r64_manifest.json"
    manifest_path = EVIDENCE / "manifest.json"
    revision = json.loads(revision_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    prior_revision_outputs = revision["outputs"]
    verify_fixed_build_and_replay_inputs(manifest)
    if (revision.get("base_prepared_source", {}).get("path") != BASE_SOURCE[0]
            or revision.get("base_prepared_source", {}).get("sha256") != BASE_SOURCE[1]):
        raise ValueError("source-revision prepared-source path/hash pair changed")
    if revision["private_generated_source"]["sha256"] != GENERATED_SOURCE[1]:
        raise ValueError("source-revision generated-source pin changed")
    rev_module = revision["build"].get("module_inventory", {})
    rev_module_sha = rev_module.get("sha256", revision["build"].get("module_inventory_sha256"))
    if revision["build"]["module_count"] != 30 or rev_module_sha != MODULE_INVENTORY[1]:
        raise ValueError("source-revision module inventory pin changed")
    rev_plan = revision["build"].get("plan", {})
    rev_plan_path = rev_plan.get("path") if isinstance(rev_plan, dict) else rev_plan
    rev_plan_sha = rev_plan.get("sha256") if isinstance(rev_plan, dict) else revision["build"].get("plan_sha256")
    if rev_plan_path != BUILD_PLAN[0] or rev_plan_sha != BUILD_PLAN[1]:
        raise ValueError("source-revision frozen build-plan pin changed")
    if (revision["outputs"]["aggregation_inputs.json"]["sha256"]
            != sha256(EVIDENCE / "aggregation_inputs.json")):
        raise ValueError("source-revision aggregation input pin changed")
    if (manifest.get("input_prepared_source", {}).get("path") != BASE_SOURCE[0]
            or manifest.get("input_prepared_source", {}).get("sha256") != BASE_SOURCE[1]):
        raise ValueError("main-manifest prepared-source path/hash pair changed")
    revision["base_prepared_source"] = {
        "path": BASE_SOURCE[0], "sha256": BASE_SOURCE[1],
        "role": "prepared PR100 observer source used as additive-transform input",
    }
    revision.pop("base_prepared_source_sha256", None)
    revision["build"]["post_link_input_inventory"] = {
        "path": "docs/evidence/pr101_cloud_thermo_20261023/build_r64/link_inputs_post_link.json",
        "sha256": sha256(EVIDENCE / "build_r64/link_inputs_post_link.json"),
        "timing": "post-link readback; not a build-time input pin",
    }
    revision["build"].pop("post_link_input_inventory_path", None)
    revision["build"].pop("post_link_input_inventory_timing", None)
    revision["build"]["module_count"] = 30
    prior_plan = prior_revision_outputs.get("build_plan.json", {})
    prior_plan_hash = prior_plan.get("sha256", rev_plan_sha)
    if (manifest["files"]["build_plan"]["path"] != BUILD_PLAN[0]
            or ("path" in prior_plan and prior_plan["path"] != BUILD_PLAN[0])):
        raise ValueError("manifest build-plan path differs from frozen replay binding")
    if manifest["files"]["build_plan"]["sha256"] not in (
            BUILD_PLAN[1], "b1264d5254bd2c863711a8bba909ec6950a0d18938d704601b698c628bb61160"):
        raise ValueError("main-manifest frozen build-plan pin changed")
    if prior_plan_hash not in (
            BUILD_PLAN[1], "b1264d5254bd2c863711a8bba909ec6950a0d18938d704601b698c628bb61160"):
        raise ValueError("source-revision frozen build-plan output pin changed")
    manifest["files"]["build_plan"]["sha256"] = BUILD_PLAN[1]
    revision["outputs"] = {}
    revision["build"]["plan"] = {"path": BUILD_PLAN[0], "sha256": BUILD_PLAN[1]}
    revision["build"].pop("plan_sha256", None)
    revision["build"]["module_inventory"] = {
        "path": "docs/evidence/pr101_cloud_thermo_20261023/build_r64/precompile_seed_inventory.json",
        "sha256": MODULE_INVENTORY[1],
    }
    revision["build"].pop("module_inventory_sha256", None)
    revision["build"]["executable"] = {"path": EXECUTABLE[0], "sha256": EXECUTABLE[1]}
    revision["build"].pop("executable_sha256", None)
    manifest["build"]["profile"] = {"path": PROFILE[0], "sha256": PROFILE[1]}
    manifest["build"].pop("profile_path", None)
    manifest["build"].pop("profile_sha256", None)
    manifest["build"]["precompile_module_inventory"] = {
        "path": "docs/evidence/pr101_cloud_thermo_20261023/build_r64/precompile_seed_inventory.json",
        "sha256": MODULE_INVENTORY[1],
    }
    manifest["build"].pop("precompile_module_inventory_sha256", None)
    manifest["build"]["executable"] = {"path": EXECUTABLE[0], "sha256": EXECUTABLE[1]}
    manifest["build"].pop("executable_sha256", None)
    for name, path in {
        "four_arm_summary.json": SUMMARY,
        "report": "docs/PR101_CLOUD_THERMO_20261023.md",
        "link_inputs_post_link.json": "docs/evidence/pr101_cloud_thermo_20261023/build_r64/link_inputs_post_link.json",
        "stager_recheck.json": "docs/evidence/pr101_cloud_thermo_20261023/build_r64/stager_recheck.json",
        "reproducibility_readback.json": "docs/evidence/pr101_cloud_thermo_20261023/build_r64/reproducibility_readback.json",
        "aggregate_tool.py": "tools/pr101_cloud_thermo_aggregate.py",
        "aggregate_test.py": "tests/test_pr101_cloud_thermo_aggregate.py",
        "manifest_refresh_tool.py": "tools/pr101_cloud_thermo_refresh_manifest.py",
    }.items():
        revision["outputs"][name] = output_record(path)
    fixed_outputs = {
        "off_summary.json": "docs/evidence/pr101_cloud_thermo_20261023/off_summary.json",
        "replay_off_guarded_manifest.json": "docs/evidence/pr101_cloud_thermo_20261023/replay_off_guarded_manifest.json",
        "replay_hydro_guarded_manifest.json": "docs/evidence/pr101_cloud_thermo_20261023/replay_hydro_guarded_manifest.json",
        "replay_coupled_guarded_manifest.json": "docs/evidence/pr101_cloud_thermo_20261023/replay_coupled_guarded_manifest.json",
        "replay_p20_guarded_manifest.json": "docs/evidence/pr101_cloud_thermo_20261023/replay_p20_guarded_manifest.json",
        "off_runtime_retry_note.json": "docs/evidence/pr101_cloud_thermo_20261023/off_runtime_retry_note.json",
        "replay_off_loader_failure_receipt.json": "docs/evidence/pr101_cloud_thermo_20261023/replay_off_loader_failure_receipt.json",
        "aggregation_inputs.json": "docs/evidence/pr101_cloud_thermo_20261023/aggregation_inputs.json",
    }
    for name, path in fixed_outputs.items():
        old = prior_revision_outputs.get(name, {})
        old_digest = old.get("sha256")
        if old_digest and old_digest != sha256(resolve(path)):
            raise ValueError(f"fixed source-revision output changed: {name}")
        revision["outputs"][name] = output_record(path)
    refresh_derived_pairs(revision)
    revision_path.write_text(json.dumps(revision, indent=2) + "\n")

    manifest.pop("input_prepared_source_sha256", None)
    manifest["outputs"] = {
        "report": output_record("docs/PR101_CLOUD_THERMO_20261023.md"),
        "r64_build_plan": output_record(BUILD_PLAN[0]),
        "four_arm_summary": output_record(SUMMARY),
        "off_summary": output_record("docs/evidence/pr101_cloud_thermo_20261023/off_summary.json"),
        "source_revision_manifest": output_record("docs/evidence/pr101_cloud_thermo_20261023/source_r64_manifest.json"),
    }
    for name, path in {
        "aggregate_tool": "tools/pr101_cloud_thermo_aggregate.py",
        "aggregate_test": "tests/test_pr101_cloud_thermo_aggregate.py",
        "aggregation_inputs": "docs/evidence/pr101_cloud_thermo_20261023/aggregation_inputs.json",
        "manifest_refresh_tool": "tools/pr101_cloud_thermo_refresh_manifest.py",
        "report": "docs/PR101_CLOUD_THERMO_20261023.md",
        "link_input_inventory": "docs/evidence/pr101_cloud_thermo_20261023/build_r64/link_inputs_post_link.json",
        "stager_recheck": "docs/evidence/pr101_cloud_thermo_20261023/build_r64/stager_recheck.json",
        "reproducibility_readback": "docs/evidence/pr101_cloud_thermo_20261023/build_r64/reproducibility_readback.json",
    }.items():
        manifest["files"][name] = {"path": path, "sha256": sha256(resolve(path))}
    manifest["outputs"]["source_revision_manifest"] = output_record("docs/evidence/pr101_cloud_thermo_20261023/source_r64_manifest.json")
    refresh_derived_pairs(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    # Readback is verification only. A changed fixed input fails without repair.
    revision_check = json.loads(revision_path.read_text())
    manifest_check = json.loads(manifest_path.read_text())
    checked = verify_pairs(revision_check, "source_revision") + verify_pairs(manifest_check, "main")
    verify_fixed_build_and_replay_inputs(manifest_check)
    if manifest_check["outputs"]["source_revision_manifest"]["sha256"] != sha256(revision_path):
        raise ValueError("main manifest source-revision-manifest hash is stale")
    return {"summary_sha256": sha256(resolve(SUMMARY)),
            "source_revision_manifest_sha256": sha256(revision_path),
            "main_manifest_sha256": sha256(manifest_path),
            "path_sha_pairs_verified": checked}


if __name__ == "__main__":
    print(json.dumps(refresh(), sort_keys=True))
