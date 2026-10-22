#!/usr/bin/env python3
"""PR100 guarded KG wrapper; check-only by default and review-bound before apply."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PREFLIGHT = HERE / "preflight_kg.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def current_snapshot_pins(preflight) -> dict:
    result = {}
    for corpus in (preflight.ROOT, preflight.MAINT):
        graph_dir = corpus / "graphify-out"
        for folder in sorted(graph_dir.iterdir()):
            if not folder.is_dir() or not re.match(r"^2026-\d\d-\d\d", folder.name):
                continue
            if folder.is_symlink():
                raise RuntimeError(f"symlinked dated snapshot: {folder}")
            members = {}
            for path in sorted(folder.iterdir()):
                if path.is_symlink():
                    raise RuntimeError(f"symlinked snapshot member: {path}")
                if path.is_dir():
                    raise RuntimeError(f"nested snapshot directory is outside backup contract: {path}")
                if path.is_file():
                    members[path.name] = {"sha256": digest(path)}
            result[str(folder)] = members
    if len(result) != preflight.EXPECTED_DATED_SNAPSHOTS:
        raise RuntimeError("current dated snapshot inventory changed after preflight")
    return result


def engine_plan(preflight, check: dict, commit: str, pr_url: str) -> tuple[object, dict]:
    engine = preflight._load_pinned_helper()
    prior = json.loads(preflight.PRIOR.read_text())
    git = lambda *args: subprocess.check_output(["git", *args], cwd=preflight.SOURCE, text=True).strip()
    names = git("diff", "--name-only", "--diff-filter=ACMRT", preflight.GRAPH_BASE, commit).splitlines()
    rows = []
    for relative in names:
        path = preflight.SOURCE / relative
        base = subprocess.run(["git", "show", f"{preflight.GRAPH_BASE}:{relative}"], cwd=preflight.SOURCE,
                             capture_output=True, check=False)
        selected = preflight.selected_path(relative) and Path(relative).suffix.lower() in preflight.GRAPH_SUFFIXES
        rows.append({"path": relative, "sha256": digest(path),
                     "base_sha256": hashlib.sha256(base.stdout).hexdigest() if base.returncode == 0 else None,
                     "maintained_before_sha256": digest(preflight.MAINT / relative)
                     if (preflight.MAINT / relative).is_file() else None,
                     "graphify_extraction": "SELECTED" if selected else "HASH_ONLY"})
    graph_rows = [row for row in rows if row["graphify_extraction"] == "SELECTED"]
    pins = engine.immutable_pin_snapshot(prior)
    snapshots = current_snapshot_pins(preflight)
    previous_snapshots = preflight._dated_snapshot_inventory(prior)
    for directory, members in previous_snapshots.items():
        if snapshots.get(directory) != members:
            raise RuntimeError(f"prior dated snapshot changed after closed PR98 receipt: {directory}")
    additions = set(snapshots) - set(previous_snapshots)
    expected_additions = {str(root / "graphify-out" / prior["new_snapshot"])
                          for root in (preflight.ROOT, preflight.MAINT)}
    if additions != expected_additions:
        raise RuntimeError("current dated snapshots are not exactly the two closed PR98 additions")
    added_graphs = {}
    for label, root in (("KLAPS50", preflight.ROOT), ("Cloud-BAL", preflight.MAINT)):
        graph = root / "graphify-out" / prior["new_snapshot"] / "graph.json"
        expected = prior["corpora"][label]["sha256"]
        if digest(graph) != expected:
            raise RuntimeError(f"closed PR98 snapshot graph pin differs for {label}")
        added_graphs[label] = expected
    updater = engine.load("pr100_pinned_updater", preflight.MAINT / "scratch/pr59_publish_kg_20261002/update.py",
                          "7c626b398f44a4013a607e2a5ae932528d2caaf41e37a479366aa80e0b146aa0")
    rollback_baseline = {}
    for label, root in (("KLAPS50", preflight.ROOT), ("Cloud-BAL", preflight.MAINT)):
        graph_dir = root / "graphify-out"
        for name in updater.GRAPH_FILES:
            path = graph_dir / name
            if path.exists():
                rollback_baseline[f"{label}/{name}"] = digest(path)
    for raw_dir, members in snapshots.items():
        folder = Path(raw_dir)
        label = "KLAPS50" if folder.parent == preflight.ROOT / "graphify-out" else "Cloud-BAL"
        for name, row in members.items():
            rollback_baseline[f"{label}/{folder.name}/{name}"] = row["sha256"]
    for name in engine.WIKI_FILES:
        rollback_baseline[f"wiki/{name}"] = digest(preflight.ROOT / "wiki" / name)
    manifest_path = Path(check["results_manifest"]["path"])
    manifest = json.loads(manifest_path.read_text())
    states = ", ".join(f"{name}={row['state']}" for name, row in manifest["runtime_gates"].items())
    audit_state = (f"PR100 integration gates: {states}; physical approval FAIL_OPEN; "
                   "observation skill NOT_EVALUATED")
    engine.SOURCE, engine.BASE, engine.OUT = preflight.SOURCE, preflight.GRAPH_BASE, preflight.OUT
    engine.PRIOR, engine.PRIOR_SHA = preflight.PRIOR, preflight.PRIOR_SHA
    engine.SNAPSHOT = preflight.SNAPSHOT
    engine.EXPECTED_DATED_SNAPSHOTS = preflight.EXPECTED_DATED_SNAPSHOTS
    engine.GRAPH_PINS = dict(preflight.GRAPH_PINS)
    engine.RESULTS_AUDIT_STATE = audit_state
    wiki = {f"wiki/{name}": digest(preflight.ROOT / "wiki" / name) for name in engine.WIKI_FILES}
    plan = {
        "source_commit": commit, "base": preflight.BASE, "approval_base": preflight.BASE,
        "graph_selection_base": preflight.GRAPH_BASE, "pr": pr_url,
        "pr99_merged_without_kg_apply": True,
        "selected_paths": rows, "graph_source_paths": [row["path"] for row in graph_rows],
        "prior_receipt_sha256": preflight.PRIOR_SHA,
        "maintained_source_snapshot_before": check["maintained_source_inventory"],
        "inherited_immutable_pins": pins, "wiki_baseline": wiki,
        "protected_content_sha256": check["protected_content_sha256"],
        "protected_content_helper": check["protected_content_helper_chain"],
        "dated_snapshot_baseline": snapshots, "prior_receipt_snapshot": prior["new_snapshot"],
        "snapshot_inventory_provenance": {
            "prior_receipt_snapshot_count_unchanged": len(previous_snapshots),
            "prior_receipt_snapshot_inventory_sha256": hashlib.sha256(json.dumps(
                previous_snapshots, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "closed_pr98_added_snapshot": prior["new_snapshot"],
            "closed_pr98_added_graph_sha256": added_graphs,
            "current_snapshot_count": len(snapshots),
            "current_snapshot_inventory_sha256": hashlib.sha256(json.dumps(
                snapshots, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        },
        "new_snapshot": preflight.SNAPSHOT,
        "baseline_graphs": {name: {"sha256": value} for name, value in preflight.GRAPH_PINS.items()},
        "immutable_pin_count_verified": len(pins), "results_manifest": check["results_manifest"],
        "rollback_baseline": rollback_baseline,
        "graphify_version": check["graphify_version"],
        "graphify_interpreter": str(engine.PINNED_PYTHON),
        "engine_helper_expected_sha256": preflight.HELPER_SHA,
        "runtime_gates": manifest["runtime_gates"],
        "physical_approval": manifest["physical_approval"],
        "observation_skill": manifest["observation_skill"],
    }
    return engine, plan


def plan_hash(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_text(path: Path, data: str) -> None:
    temp = path.with_name(path.name + ".pr100-tmp")
    try:
        temp.write_text(data)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def format_log_entry(engine, plan: dict, receipt: dict, limits: str) -> str:
    gates = ", ".join(f"{name}={row['state']}" for name, row in plan["runtime_gates"].items())
    corpus_rows = "".join(
        f"- {name}: {row['snapshot']}; {row['nodes']} nodes / {row['edges']} edges / "
        f"{row['communities']} communities; delta nodes={row['delta_nodes']}, "
        f"edges={row['delta_edges']}.\n"
        for name, row in receipt["corpora"].items()
    )
    source_inventory = plan["maintained_source_snapshot_before"]
    return (
        f"## [2026-10-22] kg-update | PR100 C2 native closure selected overlay\n"
        f"- Source `{plan['source_commit']}`; approval base `{plan['approval_base']}`; "
        f"graph selection includes lineage from `{plan['graph_selection_base']}`; PR {plan['pr']}.\n"
        + corpus_rows
        + f"- Maintained-source inventory: {source_inventory['entry_count']} entries, "
        f"SHA-256 `{source_inventory['sha256']}`; "
        f"{plan['immutable_pin_count_verified']} inherited immutable pins verified.\n"
        f"- Extraction limits: {limits}\n"
        f"- Runtime gates: {gates}; physical approval FAIL_OPEN; observation skill NOT_EVALUATED.\n"
        "- PR99 was merged without a KG apply; PR100 graph selection includes its inherited source/doc delta. "
        "PR100 evidence payloads are hash-bound only. Graph freshness does not establish runtime or scientific validation.\n"
    )


def correct_outputs(engine, plan: dict) -> None:
    snapshot_name = engine.SNAPSHOT
    limits = ("Separate KLAPS50 and Cloud-BAL snapshots extract allowlisted PR99 lineage and PR100 source/docs; "
              "evidence payloads are hash-bound only. Cross-file Fortran CALL extraction is partial; "
              "Fortran embedded in Python generator strings is not extracted as standalone procedures. "
              "Graph freshness is navigation evidence, not runtime/scientific approval.")
    for label, directory in (("KLAPS50", engine.ROOT), ("Cloud-BAL", engine.MAINT)):
        report = directory / "graphify-out/GRAPH_REPORT.md"
        content = report.read_text()
        section = (f"## Graph Freshness\n\n- PR100 source `{plan['source_commit']}`; approval base "
                   f"`{plan['approval_base']}`; graph selection lineage from `{plan['graph_selection_base']}`; "
                   f"{len(plan['graph_source_paths'])} selected paths.\n- {limits}\n")
        replaced, count = re.subn(r"## Graph Freshness\n.*?(?=\n## |\Z)", section, content, flags=re.S)
        if count != 1:
            raise RuntimeError(f"expected one graph freshness section in {report}")
        write_text(report, replaced)
        shutil.copy2(report, directory / "graphify-out" / snapshot_name / "GRAPH_REPORT.md")
        mirror = "graph-report-klaps50.md" if label == "KLAPS50" else "graph-report-cloud-bal.md"
        shutil.copy2(report, engine.ROOT / "wiki" / mirror)

    receipt_path = engine.OUT / "kg_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    index = engine.ROOT / "wiki/graph-report.md"
    rows = index.read_text().splitlines()
    replacements = 0
    for n, line in enumerate(rows):
        if line.startswith("| KLAPS50 |") or line.startswith("| Cloud-BAL |"):
            updated = line.replace("(PR98 native effect)", "(PR100 C2 native closure)")
            replacements += updated != line
            rows[n] = updated
    if replacements != 2:
        raise RuntimeError("expected exactly two PR98 snapshot labels in wiki graph table")
    write_text(index, "\n".join(rows) + "\n")
    log = engine.ROOT / "wiki/log.md"
    contents = log.read_text()
    marker = "## [2026-10-22] kg-update | PR98 native effect selected overlay"
    start = contents.rfind(marker)
    if start < 0 or contents[start:].count(marker) != 1:
        raise RuntimeError("expected one appended PR98 KG log entry")
    entry = format_log_entry(engine, plan, receipt, limits)
    write_text(log, contents[:start] + entry)

    for label, directory in (("KLAPS50", engine.ROOT), ("Cloud-BAL", engine.MAINT)):
        record = receipt["corpora"][label]
        graph = directory / "graphify-out/graph.json"
        snapshot = directory / "graphify-out" / snapshot_name
        if digest(graph) != record["sha256"] or digest(snapshot / "graph.json") != record["sha256"]:
            raise RuntimeError(f"graph/snapshot graph binding failed for {label}")
        report = directory / "graphify-out/GRAPH_REPORT.md"
        mirror = engine.ROOT / "wiki" / ("graph-report-klaps50.md" if label == "KLAPS50" else "graph-report-cloud-bal.md")
        record["report_sha256"] = digest(report)
        record["wiki_report_sha256"] = digest(mirror)
        record["graph_path"] = str(graph)
        record["report_path"] = str(report)
        record["snapshot_path"] = str(snapshot)
        record["wiki_report_path"] = str(mirror)
        record["snapshot_files_sha256"] = {name: digest(snapshot / name)
                                            for name in ("graph.json", "GRAPH_REPORT.md", "manifest.json")}
    receipt["wiki_sha256"] = {f"wiki/{name}": digest(engine.ROOT / "wiki" / name)
                              for name in engine.WIKI_FILES}
    receipt["schema"] = "pr100_c2_native_closure_selected_source_graphify_kg_v1"
    receipt["approval_base"] = plan["approval_base"]
    receipt["graph_selection_base"] = plan["graph_selection_base"]
    receipt["pr99_merged_without_kg_apply"] = True
    receipt["limitations"] = limits
    receipt["results_manifest"] = plan["results_manifest"]
    receipt["runtime_gates"] = plan["runtime_gates"]
    receipt["physical_approval"] = plan["physical_approval"]
    receipt["observation_skill"] = plan["observation_skill"]
    receipt["graphify_version"] = plan["graphify_version"]
    receipt["graphify_interpreter"] = plan["graphify_interpreter"]
    receipt["engine_helper_sha256"] = digest(Path(engine.__file__))
    if receipt["engine_helper_sha256"] != plan["engine_helper_expected_sha256"]:
        raise RuntimeError("pinned PR98 engine helper changed during apply")
    receipt["engine_helper_expected_sha256"] = plan["engine_helper_expected_sha256"]
    receipt["apply_wrapper_sha256"] = digest(Path(__file__))
    if receipt.get("source_commit") != plan["source_commit"] or receipt.get("results_manifest") != plan["results_manifest"]:
        raise RuntimeError("PR100 KG receipt lost its source or integration-manifest binding")
    write_text(receipt_path, json.dumps(receipt, indent=2) + "\n")

def rollback(engine, plan: dict) -> None:
    guard = engine.load("pr99_rollback_guard", engine.GUARD, engine.GUARD_SHA)
    backups = engine.OUT / "backups"
    actual = {}
    for backup in sorted(path for path in backups.rglob("*") if path.is_file()):
        parts = backup.relative_to(backups).parts
        key = "/".join(parts)
        guard.guard_destination(backup)
        expected = plan["rollback_baseline"].get(key)
        if expected is None or digest(backup) != expected:
            raise RuntimeError(f"unbound or modified rollback backup: {backup}")
        if parts[0] == "wiki":
            destination = engine.ROOT / "wiki" / Path(*parts[1:])
        elif parts[0] in {"KLAPS50", "Cloud-BAL"}:
            root = engine.ROOT if parts[0] == "KLAPS50" else engine.MAINT
            destination = root / "graphify-out" / Path(*parts[1:])
        else:
            raise RuntimeError(f"unknown backup root label: {parts[0]}")
        guard.guard_destination(destination)
        actual[key] = backup
    if set(actual) != set(plan["rollback_baseline"]):
        raise RuntimeError("rollback backup inventory is incomplete")
    for key, backup in actual.items():
        parts = key.split("/")
        destination = (engine.ROOT / "wiki" / Path(*parts[1:]) if parts[0] == "wiki" else
                       (engine.ROOT if parts[0] == "KLAPS50" else engine.MAINT) /
                       "graphify-out" / Path(*parts[1:]))
        guard.copy_checked(backup, destination)
    for directory in (engine.ROOT, engine.MAINT):
        snapshot = directory / "graphify-out" / engine.SNAPSHOT
        if snapshot.exists():
            shutil.rmtree(snapshot)
    receipt = engine.OUT / "kg_receipt.json"
    if receipt.exists():
        receipt.unlink()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--pr-url", required=True)
    parser.add_argument("--results-manifest", required=True, type=Path)
    parser.add_argument("--results-sha256", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-only", action="store_true")
    modes.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewed-plan-sha256", help="required by --apply; root-reviewed CHECK_ONLY plan hash")
    args = parser.parse_args()
    apply_started = False
    try:
        preflight = load("pr100_kg_preflight", PREFLIGHT)
        check = preflight.preflight(args.commit, args.pr_url, args.results_manifest, args.results_sha256)
        engine, plan = engine_plan(preflight, check, args.commit, args.pr_url)
        fingerprint = plan_hash(plan)
        if args.check_only:
            print(json.dumps({"status": "CHECK_ONLY_NO_WRITES", "plan_sha256": fingerprint,
                              "plan": plan, "writes_performed": False}, indent=2))
            return 0
        if not args.reviewed_plan_sha256 or args.reviewed_plan_sha256 != fingerprint:
            raise RuntimeError("--apply requires the matching root-reviewed check-only plan SHA-256")
        apply_started = True
        engine.apply(plan)
        correct_outputs(engine, plan)
    except BaseException as exc:
        if apply_started and "engine" in locals():
            try:
                rollback(engine, plan)
            except BaseException as rollback_error:
                print(json.dumps({"status": "ROLLBACK_FAILED", "reason": str(exc),
                                  "rollback_error": str(rollback_error)}, indent=2))
                return 3
        state = "APPLY_FAILED_ROLLED_BACK" if apply_started else "BLOCKED_NO_WRITES"
        print(json.dumps({"status": state, "reason": str(exc),
                          "rollback_attempted": apply_started}, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
