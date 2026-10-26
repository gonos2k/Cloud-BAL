#!/usr/bin/env python3
"""Read-only PR105 KG plan generator. It never writes to maintained KG roots."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[3]
ROOT = SOURCE.parents[2]
MAINT = ROOT / "Cloud-BAL"
BASE = "334969e120afff720f1b5da4eb1d8f0991f1a6c1"
GRAPH_BASE = "6d33aa06856e4e892dd792e8def350f15c54c058"
PRIOR = ROOT / "scratch/pr103_amplitude_control_20261026/Cloud-BAL/docs/evidence/pr103_amplitude_control_20261026/kg/publication/kg_receipt.json"
PRIOR_SHA = "77e096bd1b1e8409c7f8a71d51b090ec5f8a2b88d8079120ac48f870dc15de82"
PRIOR_COMMIT = "e73203b9c2f070a58aeb8488bf1e5e67a66d5f2e"
PR105_SNAPSHOT = "2026-10-26-pr105-observation-pairing"
OUT = Path("/var/tmp/pr105_kg_apply_v1_20261026")
UPDATER = MAINT / "scratch/pr59_publish_kg_20261002/update.py"
UPDATER_SHA = "7c626b398f44a4013a607e2a5ae932528d2caaf41e37a479366aa80e0b146aa0"
AUDITOR = MAINT / "scratch/pr59_team_audit_20261006/update_kg.py"
AUDITOR_SHA = "bfe6242618e8ca1b60ab1304221d1fd215476d7f23281b69e48963611c0b76e1"
EXPECTED_SNAPSHOTS = 124
EXPECTED_SOURCE = {
    "entry_count": 627,
    "sha256": "0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f",
}
ACTIVE250_ROOT_GO = SOURCE / "docs/evidence/pr104_validtime_observation_20261026/execution/launch/root_go.json"
ACTIVE250_ROOT_GO_SHA = "f3dcc7f68660fcff2905802fdd3bb076e08dcfa76b15b2c2f90c13689b47d411"
ACTIVE250_PIN_COUNT = 250
RUNTIME_STATUS = SOURCE / "docs/evidence/pr105_observation_pairing_20261026/execution/status_at_start.json"
RUNTIME_STATUS_SHA = "f1cb354108eeaa1eedbe2943fe019ceb60667c1ae9917536377462d1dbbdf6a2"
GRAPH_SUFFIXES = {".md", ".py", ".f", ".for", ".f90", ".f95", ".f03", ".f08", ".sh"}
WIKI_FILES = ("graph-report.md", "graph-report-klaps50.md", "graph-report-cloud-bal.md",
              "index.md", "log.md")
RUNTIME_STATES = {"RUNNING"}
TERMINAL_RUNTIME_STATES = {"PASS", "FAIL", "INCOMPLETE", "NOT_EVALUATED"}
PR86_SHARED_PATHS = {"tools/pr86_time_response.py", "tests/test_pr86_time_response.py"}
PR104_EXACT_PATHS = {
    "tools/pr103_surface_temperature_observation.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active250_root_go_snapshot() -> dict:
    require(ACTIVE250_ROOT_GO.is_file() and not ACTIVE250_ROOT_GO.is_symlink() and
            sha(ACTIVE250_ROOT_GO) == ACTIVE250_ROOT_GO_SHA,
            "active250 ROOTGO snapshot hash drift")
    root_go = json.loads(ACTIVE250_ROOT_GO.read_text())
    pins = root_go.get("source_pins")
    require(root_go.get("decision") == "GO" and isinstance(pins, dict) and
            len(pins) == ACTIVE250_PIN_COUNT,
            "active250 ROOTGO does not bind its 250 source pins")
    mismatches = []
    for name, expected in pins.items():
        path = Path(name)
        if (not path.is_file() or
                not re.fullmatch(r"[0-9a-f]{64}", expected) or sha(path) != expected):
            mismatches.append(name)
    require(not mismatches, f"active250 ROOTGO source pins changed: {mismatches[:3]}")
    return {"path": str(ACTIVE250_ROOT_GO.resolve()), "sha256": ACTIVE250_ROOT_GO_SHA,
            "source_pin_count": len(pins),
            "source_pins_sha256": hashlib.sha256(json.dumps(
                pins, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot load helper {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def graph_path_allowed(relative: str) -> bool:
    return relative.startswith((
        "docs/PR104_", "docs/PR105_", "docs/evidence/pr104_", "docs/evidence/pr105_",
        "tools/pr104_", "tests/test_pr104_", "tools/pr105_", "tests/test_pr105_",
    )) or relative in (PR86_SHARED_PATHS | PR104_EXACT_PATHS)


def selected_path(relative: str) -> bool:
    if relative.startswith("docs/evidence/"):
        return False
    return relative.startswith((
        "docs/PR104_", "docs/PR105_", "tools/pr104_", "tests/test_pr104_",
        "tools/pr105_", "tests/test_pr105_",
    )) or relative in (PR86_SHARED_PATHS | PR104_EXACT_PATHS)


def raw_snapshot_name(raw_date: str, occupied: bool) -> str:
    """Retain the actual Graphify raw snapshot under a unique dated name."""
    return f"{raw_date}-pr105-graphify-raw" if occupied else raw_date


def publication_paths(roots: tuple[Path, Path], raw_date: str,
                      raw_name: str) -> set[str]:
    named = PR105_SNAPSHOT
    return {str(root / "graphify-out" / folder)
            for root in roots for folder in (raw_name, named)}


def automatic_backup_condition(graph_out: Path) -> dict:
    marker = (graph_out / ".graphify_semantic_marker").is_file()
    labels_path = graph_out / ".graphify_labels.json"
    labels = json.loads(labels_path.read_text()) if labels_path.is_file() else {}
    curated = any(value != f"Community {key}" for key, value in labels.items())
    return {"semantic_marker": marker, "curated_labels": curated,
            "automatic_backup_enabled": marker or curated}


def current_snapshot_inventory(roots: tuple[Path, Path], expected_count: int = EXPECTED_SNAPSHOTS) -> dict:
    inventory = {}
    for corpus_root in roots:
        graph_dir = corpus_root / "graphify-out"
        require(graph_dir.is_dir(), f"missing graph root {graph_dir}")
        for folder in sorted(graph_dir.iterdir()):
            if not re.match(r"^\d{4}-\d{2}-\d{2}", folder.name):
                continue
            require(not folder.is_symlink(), f"symlinked dated snapshot {folder}")
            require(folder.is_dir(), f"dated snapshot path is not a directory: {folder}")
            members = {}
            for item in sorted(folder.iterdir()):
                require(not item.is_symlink(), f"symlinked snapshot member {item}")
                require(not item.is_dir(), f"nested snapshot directory outside contract {item}")
                if item.is_file():
                    members[item.name] = {"sha256": sha(item)}
            inventory[str(folder)] = members
    require(len(inventory) == expected_count,
            f"expected {expected_count} dated snapshot folders, found {len(inventory)}")
    return inventory


def expected_published_inventory(prior: dict) -> dict:
    require(prior.get("status") == "PASS", "PR103 parent receipt is not PASS")
    require(prior.get("source_commit") == PRIOR_COMMIT, "PR103 receipt source commit changed")
    require(prior.get("post_apply_dated_snapshot_count") == EXPECTED_SNAPSHOTS,
            "PR103 receipt does not bind 124 dated folders")
    require(prior.get("maintained_source_snapshot") == EXPECTED_SOURCE,
            "627-entry maintained-source baseline changed")
    require(prior.get("inherited_immutable_pin_count_verified") == 197 and
            len(prior.get("inherited_immutable_pins_after", {})) == 197,
            "PR103 receipt does not bind all 197 immutable pins")
    require(prior.get("physical_approval") == "FAIL_OPEN" and
            prior.get("observation_skill") == "NOT_EVALUATED",
            "PR103 approval boundary changed")
    baseline = dict(prior["dated_snapshot_baseline"])
    additions = prior.get("post_apply_snapshot_additions", {})
    roles = prior.get("post_apply_snapshot_roles", {})
    require(len(baseline) == 120 and len(additions) == 4,
            "PR103 receipt must contain its exact 120+4 snapshot lineage")
    require(set(roles) == set(additions),
            "PR103 snapshot roles must bind every exact addition")
    require(sum(role.startswith("GRAPHIFY_AUTOMATIC_RAW_SNAPSHOT") for role in roles.values()) == 2 and
            sum(role == "FINAL_NAMED_PR103_SNAPSHOT" for role in roles.values()) == 2,
            "PR103 raw/named snapshot roles changed")
    for folder, members in additions.items():
        require(folder not in baseline, f"duplicate snapshot path in parent receipt: {folder}")
        baseline[folder] = {name: {"sha256": row["sha256"]}
                            for name, row in members.items()}
    require(len(baseline) == EXPECTED_SNAPSHOTS,
            "PR103 120+4 snapshot lineage does not yield 124 folders")
    inventory_hash = hashlib.sha256(json.dumps(
        baseline, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(inventory_hash == prior.get("post_apply_dated_snapshot_inventory_sha256"),
            "PR103 published inventory hash does not bind its 124-folder lineage")
    return baseline


def verify_inventory_matches(expected: dict, actual: dict) -> None:
    require(expected == actual, "current 124-folder snapshot inventory differs from PR103 receipt")


def validate_evidence_row(row: object, label: str, allowed_states: set[str],
                          require_closed: bool, require_timestamp: bool = False) -> dict:
    require(isinstance(row, dict) and row.get("state") in allowed_states,
            f"{label} must have an explicit supported state")
    require(row.get("closed") is require_closed,
            f"{label} closed flag does not match its required evidence phase")
    evidence = row.get("evidence_sha256")
    require(isinstance(evidence, str) and re.fullmatch(r"[0-9a-f]{64}", evidence),
            f"{label} lacks a SHA-256 evidence pin")
    evidence_path = row.get("evidence_path")
    require(isinstance(evidence_path, str) and evidence_path.strip(),
            f"{label} lacks an evidence path")
    evidence_file = Path(evidence_path)
    if not evidence_file.is_absolute():
        evidence_file = SOURCE / evidence_file
    require(evidence_file.is_file() and not evidence_file.is_symlink() and sha(evidence_file) == evidence,
            f"{label} evidence file is missing, symlinked, or hash-mismatched")
    require(isinstance(row.get("scope"), str) and row["scope"].strip(),
            f"{label} lacks a bounded scope")
    if require_timestamp:
        require(isinstance(row.get("recorded_utc"), str) and row["recorded_utc"].strip(),
                f"{label} lacks its observed-at timestamp")
    return {"state": row["state"], "closed": require_closed,
            "evidence_path": str(evidence_file.resolve()), "evidence_sha256": evidence,
            "scope": row["scope"], "recorded_utc": row.get("recorded_utc")}


def validate_manifest(path: Path, expected_sha256: str, commit: str,
                      pr_url: str) -> dict:
    require(path.is_file() and not path.is_symlink(), "missing or symlinked PR105 result manifest")
    require(sha(path) == expected_sha256, "PR105 result manifest SHA-256 mismatch")
    manifest = json.loads(path.read_text())
    require(manifest.get("schema") == "pr105_kg_evidence_v1", "unexpected PR105 KG evidence schema")
    require(manifest.get("source_commit") == commit, "manifest source commit mismatch")
    require(manifest.get("approval_base_commit") == BASE and
            manifest.get("graph_selection_base_commit") == GRAPH_BASE,
            "manifest must bind PR105 approval and graph-selection bases")
    require(manifest.get("pr_url") == pr_url, "manifest PR URL mismatch")
    code = validate_evidence_row(manifest.get("code_validation"), "code validation",
                                 {"PASS"}, True)
    observation = validate_evidence_row(manifest.get("runtime_observation"),
                                        "runtime observation", RUNTIME_STATES, False,
                                        require_timestamp=True)
    require(Path(observation["evidence_path"]) == RUNTIME_STATUS.resolve() and
            observation["evidence_sha256"] == RUNTIME_STATUS_SHA,
            "runtime observation must pin the immutable active-process status snapshot")
    runtime_record = json.loads(RUNTIME_STATUS.read_text())
    require(observation["recorded_utc"] == runtime_record.get("observed_utc"),
            "runtime observation timestamp differs from its immutable status snapshot")
    arms = {"HYDRO", "AMPLITUDE", "STRUCTURED"}
    supervision = runtime_record.get("supervision")
    progress = runtime_record.get("progress", {}).get("arms")
    require(isinstance(supervision, dict) and set(supervision) == arms and
            isinstance(progress, dict) and set(progress) == arms,
            "runtime status snapshot must bind exactly HYDRO, AMPLITUDE, and STRUCTURED")
    require(all(supervision[name].get("status") == "RUNNING" and
                supervision[name].get("closed_result") is None and
                progress[name].get("supervision") == "RUNNING"
                for name in arms),
            "runtime status snapshot does not show all three supervisors and progress arms RUNNING")
    require(runtime_record.get("cohort_closed_exists") is False,
            "runtime status snapshot unexpectedly reports a closed forecast cohort")
    require(manifest.get("forecast_verdict") == runtime_record.get("forecast_3600_verdict") == "PENDING",
            "forecast verdict must remain the separately recorded PENDING snapshot value")
    require(manifest.get("physical_approval") == "FAIL_OPEN",
            "physical approval must remain FAIL_OPEN")
    require(manifest.get("observation_skill") == "NOT_EVALUATED",
            "observation skill must remain NOT_EVALUATED")
    return {"path": str(path.resolve()), "sha256": expected_sha256,
            "code_validation": code, "runtime_observation": observation,
            "forecast_verdict": "PENDING",
            "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED"}


def preflight(commit: str, pr_url: str, manifest_path: Path,
              manifest_sha256: str, *, require_output_absent: bool = True) -> dict:
    prior_bytes = PRIOR.read_bytes()
    require(hashlib.sha256(prior_bytes).hexdigest() == PRIOR_SHA,
            "PR103 final receipt hash drift")
    prior = json.loads(prior_bytes)
    expected_snapshots = expected_published_inventory(prior)

    pr103 = load("pr105_pr103_kg_preflight",
                 SOURCE / "docs/evidence/pr102_wind_structure_native_20261025/kg/preflight_kg.py")
    helper = pr103._load_pinned_helper()
    require(Path(sys.executable).resolve() == helper.PINNED_PYTHON.resolve(),
            f"run with pinned Graphify interpreter {helper.PINNED_PYTHON}")
    import graphify
    require(Path(graphify.__file__).resolve().is_relative_to(helper.PINNED_BIN.parent.resolve()),
            f"Graphify imported outside pinned environment: {graphify.__file__}")
    graphify_version = subprocess.check_output(
        [str(helper.PINNED_PYTHON), "-m", "graphify", "--version"], text=True).strip()
    version_match = re.search(r"(\d+)\.(\d+)\.(\d+)", graphify_version)
    require(version_match and tuple(map(int, version_match.groups())) >= (0, 8, 24),
            "pinned Graphify >= 0.8.24 is required for Fortran extraction")
    require(helper.snapshot_identity(helper.load(
        "pr105_source_guard", helper.GUARD, pr103.GUARD_SHA).maintained_source_snapshot()) == EXPECTED_SOURCE,
        "maintained-source inventory differs from PR103's 627-entry pin")
    guard = helper.load("pr105_protected_guard", helper.GUARD, pr103.GUARD_SHA)
    _, protected_helper, protected_chain = helper.load_previous_helpers()
    protected = protected_helper.protected_content(guard)
    require(protected == prior.get("protected_content_sha256"),
            "protected wiki/profile content differs from PR103 receipt")
    require(protected_chain == prior.get("protected_content_helper_chain"),
            "PR103 protected-content helper chain changed")
    pins = helper.immutable_pin_snapshot(prior)
    require(pins == prior.get("inherited_immutable_pins_after") and len(pins) == 197,
            "PR103's inherited immutable pins changed")

    require(sha(UPDATER) == UPDATER_SHA, "pinned PR59 Graphify updater hash drift")
    updater = helper.load("pr105_pinned_updater", UPDATER, UPDATER_SHA)
    require(sha(AUDITOR) == AUDITOR_SHA, "pinned PR99 Graphify auditor hash drift")
    auditor = helper.load("pr105_pinned_auditor", AUDITOR, AUDITOR_SHA)
    require(helper.PRIOR_HELPER_SHA == "6bfc82441304c67f0a49688e380d66757a7b09cfbe88c64f42bb2363a4d53855",
            "pinned PR98 helper's prior-helper identity changed")
    graph_artifacts = {}
    graphify_metadata = {}
    backup_conditions = {}
    for label, corpus_root in (("KLAPS50", ROOT), ("Cloud-BAL", MAINT)):
        backup_conditions[label] = automatic_backup_condition(corpus_root / "graphify-out")
        require(backup_conditions[label]["automatic_backup_enabled"],
                f"Graphify would not create an automatic raw snapshot for {label}")
        artifacts = {}
        metadata = {}
        for name in updater.GRAPH_FILES:
            path = corpus_root / "graphify-out" / name
            if path.exists():
                require(path.is_file() and not path.is_symlink(),
                        f"graph artifact is not a regular file: {path}")
                artifacts[name] = sha(path)
        for path in sorted((corpus_root / "graphify-out").iterdir()):
            if path.is_dir() or path.name in updater.GRAPH_FILES:
                continue
            require(path.is_file() and not path.is_symlink(),
                    f"unsupported non-regular graphify metadata file: {path}")
            metadata[path.name] = sha(path)
        graph_artifacts[label] = artifacts
        graphify_metadata[label] = metadata

    roots = (ROOT, MAINT)
    for name, corpus_root in zip(("KLAPS50", "Cloud-BAL"), roots):
        expected_graph = prior["corpora"][name]["sha256"]
        require(sha(corpus_root / "graphify-out/graph.json") == expected_graph,
                f"{name} current graph differs from PR103 receipt")
    snapshots = current_snapshot_inventory(roots)
    verify_inventory_matches(expected_snapshots, snapshots)
    wiki = {f"wiki/{name}": sha(ROOT / "wiki" / name) for name in WIKI_FILES}
    require(wiki == prior["wiki_sha256"], "derived wiki differs from PR103 final receipt")

    raw_date = date.today().isoformat()
    occupied = any((root / "graphify-out" / raw_date).exists() for root in roots)
    raw_name = raw_snapshot_name(raw_date, occupied)
    targets = publication_paths(roots, raw_date, raw_name)
    require(not any(Path(target).exists() for target in targets),
            "a PR105 raw or named publication path already exists")
    if require_output_absent:
        require(not OUT.exists() and not OUT.is_symlink(),
                f"private PR105 output path already exists: {OUT}")

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=SOURCE, text=True).strip()

    require(git("rev-parse", "--show-toplevel") == str(SOURCE), "wrong source checkout root")
    require(git("rev-parse", "HEAD") == commit, "source HEAD differs from requested PR105 commit")
    require(not git("status", "--porcelain"), "PR105 source checkout must be clean")
    require(git("merge-base", BASE, commit) == BASE,
            "PR105 commit is not based on main 334969e")
    require(git("merge-base", GRAPH_BASE, commit) == GRAPH_BASE,
            "PR105 commit does not include the PR103 maintained graph selection base")
    changed = git("diff", "--name-only", "--diff-filter=ACMRT", GRAPH_BASE, commit).splitlines()
    require(changed, "no PR105 source delta from graph-selection base")
    for relative in changed:
        require(graph_path_allowed(relative),
                f"path outside explicit combined PR104+PR105/PR86 graph allowlist: {relative}")
    selected = [name for name in changed if selected_path(name) and Path(name).suffix.lower() in GRAPH_SUFFIXES]
    require(selected, "no approved combined PR104+PR105 source/doc/test paths selected")

    match = re.fullmatch(r"https://github\.com/gonos2k/Cloud-BAL/pull/(\d+)", pr_url)
    require(match is not None, "expected actual Cloud-BAL PR URL")
    pull = json.loads(subprocess.check_output(
        ["gh", "api", f"repos/gonos2k/Cloud-BAL/pulls/{match.group(1)}"], text=True))
    require(pull.get("html_url") == pr_url and pull.get("state") == "open" and
            pull.get("head", {}).get("sha") == commit and pull.get("base", {}).get("ref") == "main",
            "actual PR must be open against main at the reviewed commit")
    manifest = validate_manifest(manifest_path, manifest_sha256, commit, pr_url)
    active250 = active250_root_go_snapshot()
    return {
        "schema": "pr105_guarded_kg_plan_v1", "status": "PREFLIGHT_PASS_NO_WRITES",
        "source": str(SOURCE), "source_commit": commit, "approval_base": BASE,
        "graph_selection_base": GRAPH_BASE, "pr_url": pr_url,
        "prior_receipt": str(PRIOR), "prior_receipt_sha256": PRIOR_SHA,
        "prior_source_commit": PRIOR_COMMIT, "maintained_source_snapshot": EXPECTED_SOURCE,
        "pinned_helpers": {
            "pr98_engine": {"path": str(pr103.HELPER), "sha256": pr103.HELPER_SHA},
            "pr59_updater": {"path": str(UPDATER), "sha256": UPDATER_SHA},
            "pr99_auditor": {"path": str(AUDITOR), "sha256": AUDITOR_SHA},
            "graph_artifact_names": list(updater.GRAPH_FILES),
            "auditor_private_profile_check": callable(getattr(auditor, "verify_private_profile", None)),
        },
        "graphify_version": graphify_version,
        "graphify_interpreter": str(helper.PINNED_PYTHON),
        "baseline_graph_artifacts": graph_artifacts,
        "baseline_graphify_metadata": graphify_metadata,
        "graphify_automatic_backup_conditions": backup_conditions,
        "inherited_immutable_pin_count": len(pins), "protected_content_sha256": protected,
        "protected_content_helper_chain": protected_chain,
        "baseline_graphs": {name: {"sha256": prior["corpora"][name]["sha256"]}
                            for name in ("KLAPS50", "Cloud-BAL")},
        "dated_snapshot_count_before": len(snapshots), "dated_snapshot_baseline": snapshots,
        "prior_post_apply_inventory_sha256": prior["post_apply_dated_snapshot_inventory_sha256"],
        "wiki_baseline": wiki, "automatic_snapshot_date": raw_date,
        "automatic_raw_name_collision": occupied, "automatic_raw_publish_name": raw_name,
        "named_snapshot": PR105_SNAPSHOT, "expected_new_snapshot_paths": sorted(targets),
        "expected_dated_snapshot_count_after": EXPECTED_SNAPSHOTS + 4,
        "private_output_directory": str(OUT),
        "selected_graph_paths": selected,
        "hash_only_paths": [name for name in changed if name not in selected],
        "selected_source_sha256": {name: sha(SOURCE / name) for name in selected},
        "hash_only_sha256": {name: sha(SOURCE / name) for name in changed if name not in selected},
        "results_manifest": manifest,
        "code_validation": manifest["code_validation"],
        "runtime_observation": manifest["runtime_observation"],
        "forecast_verdict": manifest["forecast_verdict"],
        "active250_root_go_snapshot": active250,
        "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED",
        "writes_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--pr-url", required=True)
    parser.add_argument("--results-manifest", required=True, type=Path)
    parser.add_argument("--results-sha256", required=True)
    args = parser.parse_args()
    try:
        plan = preflight(args.commit, args.pr_url, args.results_manifest, args.results_sha256)
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "PREFLIGHT_BLOCKED_NO_WRITES", "reason": str(exc),
                          "writes_performed": False}, indent=2))
        return 2
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
