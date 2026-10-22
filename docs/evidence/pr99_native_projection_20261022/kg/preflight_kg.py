#!/usr/bin/env python3
"""Read-only PR99 KG publication preflight; this command never updates graph or wiki."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SOURCE = Path(__file__).resolve().parents[4]
ROOT = SOURCE.parents[2]
MAINT = ROOT / "Cloud-BAL"
BASE = "6ac1ddb6a50c9e4f909e47243bbd656e09fc85a3"
PRIOR = MAINT / "scratch/pr98_native_effect_closed_20261022/kg/kg_receipt.json"
PRIOR_SHA = "6483bca8400f8ced959f23cde9a71208e8a525284fecfae843eb7e46730f2c06"
HELPER = ROOT / "scratch/pr98_native_effect_20261022/Cloud-BAL/docs/evidence/pr98_native_effect_20261022/kg/update_kg.py"
HELPER_SHA = "92ca3f6aa630807dfde2e7fbb1559b87a1ba0d3f746e211a993be963be01d685"
GUARD_SHA = "a2b4de3e7941e3d0cf2cf8d60ee3956338fe2471df960c1f93c04bcf554ea9cf"
OUT = MAINT / "scratch/pr99_native_contract_20261022/kg"
SNAPSHOT = "2026-10-22-pr99-native-contract"
EXPECTED_DATED_SNAPSHOTS = 110
EXPECTED_SOURCE_INVENTORY = {
    "entry_count": 627,
    "sha256": "0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f",
}
GRAPH_PINS = {
    "KLAPS50": "983942df987a14cfbe4b78a7b51f73f092d58fb208e0b4c92278a7f73ddec2bc",
    "Cloud-BAL": "be2ccfd8d33823dc984bcc4621e55da45c304ae6387febce745e4c7c37be57a6",
}
GRAPH_SUFFIXES = {".md", ".py", ".f", ".for", ".f90", ".f95", ".f03", ".f08", ".sh"}
EXACT_SELECTED = {
    "src/common/cloud_bal_balance_operator.f90",
    "src/common/cloud_bal_joint_transport.f90",
    "tests/test_background_continuity_balance.f90",
    "tests/test_balance_omega_authority.f90",
    "tests/pr81_joint_thermo_retained.f90",
    "tests/test_pr86_time_response.py",
    "tests/test_pr92_source_store_fixture.py",
    "tests/run_unit_tests.sh",
    "tools/cp06a_state_force_flux.py",
    "tools/pr86_time_response.py",
    "tools/pr98_budget_faces.py",
}
REQUIRED_GATES = ("native_20s", "off640", "water_compact_fulltile", "bulk_candidate_640_three_arm")
WIKI_FILES = ("graph-report.md", "graph-report-klaps50.md", "graph-report-cloud-bal.md", "index.md", "log.md")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def selected_path(relative: str) -> bool:
    if relative.startswith("docs/evidence/"):
        return False
    if relative == "tests/fixtures/pr99_c1_core_pre_certificate.f90":
        return False
    prefixes = (
        "docs/PR99_", "tools/pr99_", "tests/pr99_", "tests/test_pr99_",
        "tests/fixtures/pr99_", "tests/run_pr99_",
    )
    return relative.startswith(prefixes) or relative in EXACT_SELECTED


def _load_pinned_helper():
    require(sha(HELPER) == HELPER_SHA, "pinned PR98 KG helper hash drift")
    spec = importlib.util.spec_from_file_location("pr99_pinned_kg_guard", HELPER)
    require(spec is not None and spec.loader is not None, "cannot load pinned PR98 KG helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dated_snapshot_inventory(receipt: dict) -> dict[str, dict[str, dict[str, str]]]:
    baseline = receipt["dated_snapshot_baseline"]
    result = {}
    for raw_directory, expected_members in baseline.items():
        directory = Path(raw_directory)
        require(directory.is_dir(), f"previous dated snapshot directory missing: {directory}")
        actual_names = {path.name for path in directory.iterdir() if path.is_file()}
        require(actual_names == set(expected_members), f"dated snapshot membership changed: {directory}")
        actual = {name: sha(directory / name) for name in sorted(actual_names)}
        expected = {name: row["sha256"] for name, row in expected_members.items()}
        require(actual == expected, f"dated snapshot bytes changed: {directory}")
        result[str(directory)] = {name: {"sha256": digest} for name, digest in actual.items()}
    return result


def _current_dated_count() -> int:
    total = 0
    for directory in (ROOT, MAINT):
        total += sum(1 for path in (directory / "graphify-out").iterdir()
                     if path.is_dir() and re.match(r"^2026-\d\d-\d\d", path.name))
    return total


def _validate_results_manifest(path: Path, expected_sha256: str | None,
                               commit: str, pr_url: str) -> dict:
    require(path.is_file() and not path.is_symlink(), "PR99 integration results manifest missing or symlinked")
    digest = sha(path)
    if expected_sha256:
        require(digest == expected_sha256, "PR99 integration results manifest hash mismatch")
    manifest = json.loads(path.read_text())
    require(manifest.get("source_commit") == commit, "results manifest source commit differs from PR commit")
    require(manifest.get("pr_url") == pr_url, "results manifest PR URL differs from requested PR")
    gates = manifest.get("runtime_gates")
    require(isinstance(gates, dict), "results manifest lacks runtime_gates object")
    require(set(REQUIRED_GATES) <= set(gates), "results manifest lacks required runtime gate records")
    for name in REQUIRED_GATES:
        row = gates[name]
        require(isinstance(row, dict) and row.get("state") in {"COMPLETE", "INCOMPLETE", "OPEN"},
                f"runtime gate {name} must report its explicit COMPLETE/INCOMPLETE/OPEN state")
        require(row.get("evidence_sha256") and re.fullmatch(r"[0-9a-f]{64}", row["evidence_sha256"]),
                f"runtime gate {name} lacks an evidence hash")
    require(manifest.get("physical_approval") == "FAIL_OPEN",
            "PR99 manifest must preserve physical approval as FAIL_OPEN")
    require(manifest.get("observation_skill") == "NOT_EVALUATED",
            "PR99 manifest must preserve observation skill as NOT_EVALUATED")
    return {"path": str(path.resolve()), "sha256": digest,
            "runtime_gates": {name: gates[name]["state"] for name in REQUIRED_GATES},
            "physical_approval": manifest["physical_approval"],
            "observation_skill": manifest["observation_skill"]}


def preflight(commit: str, pr_url: str, results_manifest: Path,
              results_sha256: str | None) -> dict:
    helper = _load_pinned_helper()
    require(sys.executable == str(helper.PINNED_PYTHON),
            f"run with pinned Graphify interpreter {helper.PINNED_PYTHON}")
    import graphify
    require(Path(graphify.__file__).resolve().is_relative_to(helper.PINNED_BIN.parent.resolve()),
            f"Graphify imported outside pinned uv tool: {graphify.__file__}")
    version = subprocess.check_output([str(helper.PINNED_PYTHON), "-m", "graphify", "--version"], text=True).strip()
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
    require(match and tuple(map(int, match.groups())) >= (0, 8, 24), "Graphify >= 0.8.24 required for Fortran")
    match_pr = re.fullmatch(r"https://github\.com/gonos2k/Cloud-BAL/pull/(\d+)", pr_url)
    require(match_pr is not None, "expected actual Cloud-BAL pull request URL")

    git = lambda *args: subprocess.check_output(["git", *args], cwd=SOURCE, text=True).strip()
    require(git("rev-parse", "--show-toplevel") == str(SOURCE), "source checkout root changed")
    require(git("rev-parse", "HEAD") == commit, "source HEAD differs from supplied final commit")
    require(not git("status", "--porcelain"), "source must be clean at reviewed PR commit")
    require(git("merge-base", BASE, commit) == BASE, "source commit is not based on pinned main base")
    require(sha(PRIOR) == PRIOR_SHA, "closed PR98 prior KG receipt hash drift")
    prior = json.loads(PRIOR.read_text())
    require(prior.get("status") == "PASS" and prior.get("physical_approval") == "FAIL_OPEN",
            "closed PR98 prior KG state changed")
    require(prior.get("maintained_source_snapshot_after") == EXPECTED_SOURCE_INVENTORY,
            "627-file maintained-source inventory pin changed")
    require(prior.get("immutable_pin_count_verified") == 197 and
            len(prior.get("inherited_immutable_pins_after", {})) == 197,
            "197 inherited immutable pins missing")
    pins = helper.immutable_pin_snapshot(prior)

    guard = helper.load("pr99_maintained_source_guard", helper.GUARD, GUARD_SHA)
    current_inventory = helper.snapshot_identity(guard.maintained_source_snapshot())
    require(current_inventory == EXPECTED_SOURCE_INVENTORY,
            "maintained source inventory differs from the closed PR98 baseline")
    _, protected_helper, protected_chain = helper.load_previous_helpers()
    protected = protected_helper.protected_content(guard)
    require(protected == prior.get("protected_content_sha256"),
            "protected wiki/profile content differs from the closed PR98 receipt")
    for name, directory in (("KLAPS50", ROOT), ("Cloud-BAL", MAINT)):
        require(sha(directory / "graphify-out/graph.json") == GRAPH_PINS[name],
                f"{name} maintained graph changed")
        require(not (directory / "graphify-out" / SNAPSHOT).exists(),
                f"PR99 dated snapshot already exists: {directory / 'graphify-out' / SNAPSHOT}")
    require(_current_dated_count() == EXPECTED_DATED_SNAPSHOTS,
            f"expected {EXPECTED_DATED_SNAPSHOTS} dated graph snapshots")
    prior_snapshots = _dated_snapshot_inventory(prior)
    expected_new_snapshot = prior["new_snapshot"]
    for directory in (ROOT / "graphify-out", MAINT / "graphify-out"):
        require((directory / expected_new_snapshot).is_dir(),
                f"closed PR98 dated snapshot missing: {directory / expected_new_snapshot}")
    wiki_baseline = {f"wiki/{name}": sha(ROOT / "wiki" / name) for name in WIKI_FILES}
    require(wiki_baseline == prior["wiki_sha256"], "maintained wiki baseline differs from closed PR98 receipt")

    names = git("diff", "--name-only", "--diff-filter=ACMRT", BASE, commit).splitlines()
    require(names, "no PR99 source delta from pinned main base")
    for relative in names:
        require(relative.startswith(("docs/PR99_", "docs/evidence/pr99_", "tools/pr99_",
                                     "tests/pr99_", "tests/test_pr99_", "tests/fixtures/pr99_",
                                     "tests/run_pr99_")) or relative in EXACT_SELECTED,
                f"source diff is outside the PR99 allowlist: {relative}")
    selected = [name for name in names if selected_path(name) and Path(name).suffix.lower() in GRAPH_SUFFIXES]
    require(selected, "no PR99 source/docs paths selected for incremental graph update")
    gh = json.loads(subprocess.check_output(
        ["gh", "api", f"repos/gonos2k/Cloud-BAL/pulls/{match_pr.group(1)}"], text=True))
    require(gh.get("html_url") == pr_url and gh.get("state") == "open" and
            gh.get("head", {}).get("sha") == commit and gh.get("base", {}).get("ref") == "main",
            "actual GitHub PR does not match the reviewed source commit and main base")
    result_binding = _validate_results_manifest(results_manifest, results_sha256, commit, pr_url)
    require(not OUT.exists(), "refuse existing PR99 KG output directory")
    return {
        "status": "PREFLIGHT_PASS_NO_WRITES",
        "source": str(SOURCE), "source_commit": commit, "base": BASE, "pr_url": pr_url,
        "graphify_version": version, "selected_graph_paths": selected,
        "hash_only_paths": [name for name in names if name not in selected],
        "hash_only_sha256": {name: sha(SOURCE / name) for name in names if name not in selected},
        "prior_receipt_sha256": PRIOR_SHA, "prior_receipt": str(PRIOR),
        "prior_graphs": GRAPH_PINS, "dated_snapshot_count": EXPECTED_DATED_SNAPSHOTS,
        "prior_dated_snapshot_files_verified": sum(len(rows) for rows in prior_snapshots.values()),
        "maintained_source_inventory": current_inventory,
        "inherited_immutable_pins_verified": len(pins), "wiki_baseline": wiki_baseline,
        "protected_content_sha256": protected, "protected_content_helper_chain": protected_chain,
        "results_manifest": result_binding,
        "output_directory": str(OUT),
        "writes_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True, help="reviewed, clean PR99 source commit")
    parser.add_argument("--pr-url", required=True, help="actual open Cloud-BAL PR URL")
    parser.add_argument("--results-manifest", required=True, type=Path,
                        help="root-owned integration manifest binding runtime and open-status evidence")
    parser.add_argument("--results-sha256", help="optional independent pin for the integration manifest")
    args = parser.parse_args()
    try:
        result = preflight(args.commit, args.pr_url, args.results_manifest, args.results_sha256)
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "PREFLIGHT_BLOCKED_NO_WRITES", "reason": str(exc),
                          "writes_performed": False}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
