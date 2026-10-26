#!/usr/bin/env python3
"""PR103 guarded staged Graphify publisher; check-only by default."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
import preflight_kg as preflight
SNAPSHOT_FILES = ("graph.json", "GRAPH_REPORT.md", "manifest.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan_hash(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_root_go(path: Path, fingerprint: str, commit: str, raw_date: str) -> dict:
    preflight.require(path.is_file() and not path.is_symlink(), "--apply requires a regular root GO JSON")
    go = json.loads(path.read_text())
    preflight.require(go.get("decision") == "GO" and go.get("plan_sha256") == fingerprint and
                      go.get("source_commit") == commit and go.get("automatic_snapshot_date") == raw_date and
                      isinstance(go.get("reviewed_by"), str) and go["reviewed_by"].strip(),
                      "root GO does not bind this exact plan, commit, and automatic date")
    return go


def write_atomic(path: Path, data: bytes) -> None:
    temp = path.with_name(path.name + ".pr103-tmp")
    try:
        preflight.require(not temp.exists() and not temp.is_symlink(),
                         f"refuse pre-existing temporary destination {temp}")
        with temp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def load_execution_helpers(plan: dict, out: Path):
    engine = preflight.load("pr103_pinned_pr98_engine", Path(plan["pinned_helpers"]["pr98_engine"]["path"]))
    updater = preflight.load("pr103_pinned_pr59_updater", Path(plan["pinned_helpers"]["pr59_updater"]["path"]))
    auditor = preflight.load("pr103_pinned_pr99_auditor", Path(plan["pinned_helpers"]["pr99_auditor"]["path"]))
    for name, module in (("pr98_engine", engine), ("pr59_updater", updater), ("pr99_auditor", auditor)):
        expected = plan["pinned_helpers"][name]["sha256"]
        preflight.require(digest(Path(module.__file__)) == expected, f"pinned {name} hash drift")
    updater.SOURCE = preflight.SOURCE
    updater.OUT = out
    updater.BASE_COMMIT = plan["graph_selection_base"]
    updater.PR = plan["pr_url"]
    auditor.OUT = out
    auditor.PATHS = tuple(plan["selected_graph_paths"])
    return engine, updater, auditor


def copy_stage_graph_inputs(stage_root: Path, maintained_root: Path) -> None:
    graph_out = maintained_root / "graphify-out"
    stage_out = stage_root / "graphify-out"
    stage_out.mkdir(parents=True)
    for item in sorted(graph_out.iterdir()):
        preflight.require(not item.is_symlink(), f"symlinked graphify-out input: {item}")
        if item.is_dir():
            # Dated history is pinned in the plan and is not needed to build the staged overlay.
            continue
        preflight.require(item.is_file() and not item.is_symlink(),
                          f"unsupported graphify-out input: {item}")
        shutil.copy2(item, stage_out / item.name)


def graphify_metadata_inventory(graph_out: Path, graph_files: tuple[str, ...]) -> dict:
    result = {}
    for path in sorted(graph_out.iterdir()):
        preflight.require(not path.is_symlink(), f"symlinked Graphify output {path}")
        if path.is_dir():
            continue
        preflight.require(path.is_file(), f"non-regular Graphify output {path}")
        if path.name not in graph_files:
            result[path.name] = digest(path)
    return result


def graphify_file_inventory(graph_out: Path) -> dict:
    result = {}
    for path in sorted(graph_out.iterdir()):
        preflight.require(not path.is_symlink(), f"symlinked staged Graphify file {path}")
        if path.is_dir():
            continue
        preflight.require(path.is_file(), f"non-regular staged Graphify file {path}")
        result[path.name] = digest(path)
    return result


def prepare_stage(plan: dict, out: Path) -> tuple[Path, Path, dict]:
    stage = out / "staging"
    stage_root, stage_maint = stage / "KLAPS50", stage / "Cloud-BAL"
    stage_root.mkdir(parents=True)
    stage_maint.mkdir(parents=True)
    copy_stage_graph_inputs(stage_root, preflight.ROOT)
    copy_stage_graph_inputs(stage_maint, preflight.MAINT)
    graph_files = tuple(plan["pinned_helpers"]["graph_artifact_names"])
    for label, directory in (("KLAPS50", stage_root), ("Cloud-BAL", stage_maint)):
        expected_files = {**plan["baseline_graph_artifacts"][label],
                          **plan["baseline_graphify_metadata"][label]}
        preflight.require(graphify_file_inventory(directory / "graphify-out") == expected_files,
                          f"copied staged graph/report/manifest/metadata differs from plan for {label}")
        actual_metadata = graphify_metadata_inventory(directory / "graphify-out", graph_files)
        preflight.require(actual_metadata == plan["baseline_graphify_metadata"][label],
                          f"staged Graphify metadata differs from plan for {label}")
    for label, directory in (("KLAPS50", stage_root), ("Cloud-BAL", stage_maint)):
        condition = preflight.automatic_backup_condition(directory / "graphify-out")
        preflight.require(condition == plan["graphify_automatic_backup_conditions"][label] and
                          condition["automatic_backup_enabled"],
                          f"staged graphify metadata will not preserve the automatic raw backup for {label}")
    (stage_root / "wiki").mkdir()
    for name in preflight.WIKI_FILES:
        shutil.copy2(preflight.ROOT / "wiki" / name, stage_root / "wiki" / name)

    engine, updater, auditor = load_execution_helpers(plan, out)
    auditor.ROOT = stage_root
    auditor.MAINTAINED = stage_maint
    original_graphs = {
        "KLAPS50": json.loads((stage_root / "graphify-out/graph.json").read_text()),
        "Cloud-BAL": json.loads((stage_maint / "graphify-out/graph.json").read_text()),
    }
    selected_items = [{"path": name, "sha256": plan["selected_source_sha256"][name]}
                      for name in plan["selected_graph_paths"]]
    env = os.environ.copy()
    env["PATH"] = str(engine.PINNED_BIN) + os.pathsep + env.get("PATH", "")
    old_path = os.environ.get("PATH", "")
    old_no_backup = os.environ.pop("GRAPHIFY_NO_BACKUP", None)
    os.environ["PATH"] = env["PATH"]
    records = {}
    try:
        for label, directory, prefix in (("KLAPS50", stage_root, "Cloud-BAL"),
                                         ("Cloud-BAL", stage_maint, "")):
            records[label] = updater.update_graph(label, directory, prefix, selected_items)
            extraction = json.loads((out / f"{label.lower().replace('-', '_')}_extraction.json").read_text())
            auditor.record_snapshot(label, directory, original_graphs[label], extraction)
        private_profile = auditor.verify_private_profile(original_graphs)
    finally:
        os.environ["PATH"] = old_path
        if old_no_backup is not None:
            os.environ["GRAPHIFY_NO_BACKUP"] = old_no_backup

    raw_date = plan["automatic_snapshot_date"]
    raw_stage_paths = {}
    for label, directory in (("KLAPS50", stage_root), ("Cloud-BAL", stage_maint)):
        raw = directory / "graphify-out" / raw_date
        preflight.require(raw.is_dir() and not raw.is_symlink(),
                          f"staged Graphify did not produce its automatic raw snapshot: {raw}")
        stage_dirs = {path.name for path in (directory / "graphify-out").iterdir() if path.is_dir()}
        preflight.require(stage_dirs == {raw_date},
                          f"staging contains unexpected dated output directories for {label}: {stage_dirs}")
        raw_stage_paths[label] = str(raw)
    return stage_root, stage_maint, {"corpora": records, "private_profile": private_profile,
                                     "raw_stage_paths": raw_stage_paths}


def freshness_limits() -> str:
    return ("Separate KLAPS50 and Cloud-BAL graphs use the allowlisted PR103 source/docs/tests and reviewed "
            "shared PR86 response files; evidence payloads are hash-bound only. Fortran cross-file CALL "
            "extraction is partial. Graph freshness is navigation evidence, not runtime or scientific approval.")


def finalize_stage(plan: dict, stage_root: Path, stage_maint: Path,
                   build: dict) -> dict:
    records = build["corpora"]
    limits = freshness_limits()
    for label, directory in (("KLAPS50", stage_root), ("Cloud-BAL", stage_maint)):
        report = directory / "graphify-out/GRAPH_REPORT.md"
        content = report.read_text()
        section = (f"## Graph Freshness\n\n- PR103 source `{plan['source_commit']}`; approval and graph-selection "
                   f"base `{plan['approval_base']}`; {len(plan['selected_graph_paths'])} selected paths.\n- {limits}\n")
        updated, count = re.subn(r"## Graph Freshness\n.*?(?=\n## |\Z)", section, content, flags=re.S)
        preflight.require(count == 1, f"expected one Graph Freshness section in {report}")
        report.write_text(updated)
        mirror = "graph-report-klaps50.md" if label == "KLAPS50" else "graph-report-cloud-bal.md"
        shutil.copy2(report, stage_root / "wiki" / mirror)
        snapshot = directory / "graphify-out" / preflight.PR103_SNAPSHOT
        preflight.require(not snapshot.exists(), f"staged final snapshot path already exists: {snapshot}")
        snapshot.mkdir()
        for name in SNAPSHOT_FILES:
            shutil.copy2(directory / "graphify-out" / name, snapshot / name)
        records[label]["snapshot"] = preflight.PR103_SNAPSHOT
        records[label]["report_sha256"] = digest(report)

    graph_index = stage_root / "wiki/graph-report.md"
    lines = graph_index.read_text().splitlines()
    replacements = 0
    for index, line in enumerate(lines):
        label = "KLAPS50" if line.startswith("| KLAPS50 |") else (
            "Cloud-BAL" if line.startswith("| Cloud-BAL |") else None)
        if label is None:
            continue
        preflight.require("PR102" in line, f"{label} graph index lacks the inherited PR102 row")
        record = records[label]
        folder = "." if label == "KLAPS50" else "Cloud-BAL/"
        mirror = "graph-report-klaps50" if label == "KLAPS50" else "graph-report-cloud-bal"
        lines[index] = (f"| {label} | `{folder}` | {preflight.PR103_SNAPSHOT} (PR103 amplitude matched control) | "
                        f"{record['nodes']} | {record['edges']} | {record['communities']} | [[{mirror}]] |")
        replacements += 1
    preflight.require(replacements == 2, "expected exactly two graph index corpus rows")
    graph_index.write_text("\n".join(lines) + "\n")

    page = stage_root / "wiki/index.md"
    body = page.read_bytes()
    start = body.find(b"## Graph snapshot")
    preflight.require(start >= 0, "wiki index lacks Graph snapshot section")
    end = body.find(b"\n## ", start + 3)
    if end < 0:
        end = len(body)
    section = "## Graph snapshot\n\n" + "\n".join(
        f"- {label}: {preflight.PR103_SNAPSHOT}; {records[label]['nodes']} nodes / "
        f"{records[label]['edges']} edges / {records[label]['communities']} communities."
        for label in ("KLAPS50", "Cloud-BAL")) + "\n- Separate corpus reports retain extraction limits; graph freshness is not scientific validation.\n"
    updated = body[:start] + section.encode() + body[end:]
    updated, count = re.subn(rb"(?m)^(date_modified:\s*)[^\r\n]+",
                             lambda match: match.group(1) + plan["automatic_snapshot_date"].encode(),
                             updated, count=1)
    preflight.require(count == 1, "wiki index date_modified field missing or ambiguous")
    page.write_bytes(updated)

    log = stage_root / "wiki/log.md"
    gates = ", ".join(f"{name}={state}" for name, state in plan["runtime_gates"].items())
    entry = (f"\n## [{plan['automatic_snapshot_date']}] kg-update | PR103 amplitude matched control\n"
             f"- Source `{plan['source_commit']}`; approval and graph-selection base `{plan['approval_base']}`; PR {plan['pr_url']}.\n")
    for label in ("KLAPS50", "Cloud-BAL"):
        row = records[label]
        entry += (f"- {label}: {preflight.PR103_SNAPSHOT}; {row['nodes']} nodes / {row['edges']} edges / "
                  f"{row['communities']} communities; delta nodes={row['delta_nodes']}, edges={row['delta_edges']}.\n")
    entry += (f"- Maintained-source inventory: {plan['maintained_source_snapshot']['entry_count']} entries, "
              f"SHA-256 `{plan['maintained_source_snapshot']['sha256']}`; "
              f"{plan['inherited_immutable_pin_count']} inherited immutable pins verified.\n"
              f"- Runtime gates: {gates}; physical approval FAIL_OPEN; observation skill NOT_EVALUATED.\n"
              f"- Extraction limits: {limits}\n")
    with log.open("a") as stream:
        stream.write(entry)

    return {"corpora": records, "private_profile": build["private_profile"], "limitations": limits}


def copy_tree_checked(source: Path, destination: Path) -> None:
    preflight.require(source.is_dir() and not source.is_symlink(), f"invalid staged snapshot {source}")
    for item in source.iterdir():
        preflight.require(item.is_file() and not item.is_symlink(),
                          f"unexpected staged snapshot member {item}")
    shutil.copytree(source, destination)


def directory_inventory(directory: Path) -> dict:
    result = {}
    for path in sorted(directory.iterdir()):
        preflight.require(path.is_file() and not path.is_symlink(),
                          f"unexpected snapshot member {path}")
        result[path.name] = {"sha256": digest(path)}
    return result


def verify_source_guards(plan: dict) -> dict:
    pr102 = preflight.load("pr103_post_guard_preflight",
                           preflight.SOURCE / "docs/evidence/pr102_wind_structure_native_20261025/kg/preflight_kg.py")
    helper = pr102._load_pinned_helper()
    guard = helper.load("pr103_post_source_guard", pr102.GUARD, pr102.GUARD_SHA)
    actual_source = helper.snapshot_identity(guard.maintained_source_snapshot())
    preflight.require(actual_source == plan["maintained_source_snapshot"],
                      "maintained source inventory changed during KG publication")
    _, protected_helper, chain = helper.load_previous_helpers()
    protected = protected_helper.protected_content(guard)
    preflight.require(protected == plan["protected_content_sha256"] and
                      chain == plan["protected_content_helper_chain"],
                      "protected wiki/profile content or helper chain changed")
    parent = json.loads(preflight.PRIOR.read_text())
    pins = helper.immutable_pin_snapshot(parent)
    preflight.require(pins == parent["inherited_immutable_pins_after"],
                      "inherited immutable pins changed during KG publication")
    return {"maintained_source_snapshot_after": actual_source,
            "protected_content_sha256": protected,
            "protected_content_helper_chain": chain,
            "inherited_immutable_pins_after": pins}


def verify_rollback(plan: dict, backups: Path, roots: tuple[Path, Path],
                    graph_files: tuple[str, ...]) -> None:
    current = preflight.current_snapshot_inventory(roots)
    preflight.verify_inventory_matches(plan["dated_snapshot_baseline"], current)
    for label, root in (("KLAPS50", roots[0]), ("Cloud-BAL", roots[1])):
        expected = plan["baseline_graph_artifacts"][label]
        for name in graph_files:
            path = root / "graphify-out" / name
            if name in expected:
                preflight.require(path.is_file() and digest(path) == expected[name],
                                  f"rollback graph artifact mismatch: {path}")
            else:
                preflight.require(not path.exists(), f"rollback left new graph artifact: {path}")
        preflight.require(graphify_metadata_inventory(root / "graphify-out", graph_files) ==
                          plan["baseline_graphify_metadata"][label],
                          f"rollback Graphify metadata mismatch for {label}")
    for name, expected in plan["wiki_baseline"].items():
        preflight.require(digest(preflight.ROOT / name) == expected,
                          f"rollback wiki mismatch: {name}")
    verify_source_guards(plan)


def rollback(guard, backups: Path, roots: tuple[Path, Path], targets: set[str],
            graph_files: tuple[str, ...], wiki_files: tuple[str, ...], absent: dict) -> None:
    for label, root in (("KLAPS50", roots[0]), ("Cloud-BAL", roots[1])):
        for name in graph_files:
            destination = root / "graphify-out" / name
            backup = backups / label / name
            guard.guard_destination(destination, root=root)
            if backup.is_file():
                preflight.require(digest(backup) == absent["backup_hashes"][label][name],
                                  f"rollback backup hash drift: {backup}")
                write_atomic(destination, backup.read_bytes())
            elif absent[label].get(name, False) and destination.exists():
                destination.unlink()
    for name in wiki_files:
        destination = preflight.ROOT / "wiki" / name
        guard.guard_destination(destination)
        backup = backups / "wiki" / name
        preflight.require(digest(backup) == absent["backup_hashes"]["wiki"][name],
                          f"rollback wiki backup hash drift: {backup}")
        write_atomic(destination, backup.read_bytes())
    for raw in targets:
        path = Path(raw)
        if path.exists():
            root = roots[0] if path.is_relative_to(roots[0]) else roots[1]
            guard.guard_directory(path, root=root)
            shutil.rmtree(path)


def apply(plan: dict, fingerprint: str, root_go_path: Path, out: Path) -> dict:
    preflight.require(out == Path(plan["private_output_directory"]) and
                      out.parent == Path("/var/tmp") and out.name.startswith("pr103_kg_apply_"),
                      "apply output must use the reviewed private /var/tmp directory")
    require_absent = not out.exists()
    preflight.require(require_absent and not out.is_symlink(), f"refuse existing PR103 KG output {out}")
    go = load_root_go(root_go_path, fingerprint, plan["source_commit"], plan["automatic_snapshot_date"])
    preflight.require(plan["automatic_snapshot_date"] == date.today().isoformat(),
                      "local automatic date changed since the reviewed plan")
    out.mkdir(parents=True)
    (out / "reviewed_plan.json").write_text(json.dumps(
        {"plan_sha256": fingerprint, "plan": plan}, indent=2) + "\n")
    shutil.copy2(root_go_path, out / "root_go.json")
    manifest_source = Path(plan["results_manifest"]["path"])
    preflight.require(digest(manifest_source) == plan["results_manifest"]["sha256"],
                      "results manifest changed after plan review")
    shutil.copy2(manifest_source, out / "results_manifest.json")
    stage_root = stage_maint = None
    published = False
    roots = (preflight.ROOT, preflight.MAINT)
    target_paths = set(plan["expected_new_snapshot_paths"])
    backups = out / "backups"
    backups.mkdir()
    absent = {"backup_hashes": {"wiki": {}}}
    staged_target_sources = {}
    engine = preflight.load("pr103_apply_engine", Path(plan["pinned_helpers"]["pr98_engine"]["path"]))
    guard = engine.load("pr103_apply_guard", Path("/var/tmp/pr91_refresh_kg_host_store_20261020.py"),
                        "a2b4de3e7941e3d0cf2cf8d60ee3956338fe2471df960c1f93c04bcf554ea9cf")
    graph_files = tuple(plan["pinned_helpers"]["graph_artifact_names"])
    backups_wiki = backups / "wiki"
    backups_wiki.mkdir()
    for label, root in (("KLAPS50", roots[0]), ("Cloud-BAL", roots[1])):
        absent[label] = {}
        absent["backup_hashes"][label] = {}
        for name in graph_files:
            source = root / "graphify-out" / name
            absent[label][name] = not source.exists()
            expected = plan["baseline_graph_artifacts"][label].get(name)
            if source.exists():
                preflight.require(source.is_file() and not source.is_symlink(), f"unsafe graph file {source}")
                preflight.require(expected == digest(source), f"graph artifact changed since plan: {source}")
                destination = backups / label / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                absent["backup_hashes"][label][name] = digest(destination)
            else:
                preflight.require(expected is None, f"planned graph artifact is missing: {source}")
    for name in preflight.WIKI_FILES:
        source = preflight.ROOT / "wiki" / name
        preflight.require(digest(source) == plan["wiki_baseline"][f"wiki/{name}"],
                          f"wiki changed since plan: {source}")
        destination = backups_wiki / name
        shutil.copy2(source, destination)
        absent["backup_hashes"]["wiki"][name] = digest(destination)
    try:
        stage_root, stage_maint, build = prepare_stage(plan, out)
        final = finalize_stage(plan, stage_root, stage_maint, build)
        fresh = preflight.preflight(
            plan["source_commit"], plan["pr_url"], Path(plan["results_manifest"]["path"]),
            plan["results_manifest"]["sha256"], require_output_absent=False)
        preflight.require(plan_hash(fresh) == fingerprint,
                          "source, gates, or maintained baselines changed during staging")
        preflight.require(plan["automatic_snapshot_date"] == date.today().isoformat(),
                          "local automatic date changed during staging")
        raw_name = plan["automatic_raw_publish_name"]
        for label, source_root, target_root in (("KLAPS50", stage_root, roots[0]),
                                                ("Cloud-BAL", stage_maint, roots[1])):
            stage_out = source_root / "graphify-out"
            original_top = plan["baseline_graph_artifacts"][label]
            for name in graph_files:
                staged_file = stage_out / name
                if staged_file.exists():
                    preflight.require(staged_file.is_file() and not staged_file.is_symlink(),
                                      f"unsafe staged graph artifact {staged_file}")
            unexpected = {path.name for path in stage_out.iterdir() if path.is_file()} - set(graph_files)
            preflight.require(unexpected == set(plan["baseline_graphify_metadata"][label]),
                              f"staging added or removed Graphify metadata files for {label}")
            preflight.require(graphify_metadata_inventory(stage_out, graph_files) ==
                              plan["baseline_graphify_metadata"][label],
                              f"staged Graphify metadata changed for {label}")
            for name in graph_files:
                staged_file = stage_out / name
                if staged_file.is_file() and (name not in original_top or digest(staged_file) != original_top[name]):
                    destination = target_root / "graphify-out" / name
                    baseline_hash = original_top.get(name)
                    if baseline_hash is None:
                        preflight.require(not destination.exists(),
                                          f"unplanned graph artifact appeared during apply: {destination}")
                    else:
                        preflight.require(destination.is_file() and digest(destination) == baseline_hash,
                                          f"graph artifact changed immediately before publish: {destination}")
                    guard.guard_destination(destination, root=target_root)
                    published = True
                    write_atomic(destination, staged_file.read_bytes())
            raw_stage = stage_out / plan["automatic_snapshot_date"]
            raw_target = target_root / "graphify-out" / raw_name
            named_stage = stage_out / preflight.PR103_SNAPSHOT
            named_target = target_root / "graphify-out" / preflight.PR103_SNAPSHOT
            for destination in (raw_target, named_target):
                preflight.require(not destination.exists(), f"publication target appeared during apply: {destination}")
                guard.guard_destination(destination, root=target_root)
            published = True
            copy_tree_checked(raw_stage, raw_target)
            copy_tree_checked(named_stage, named_target)
            staged_target_sources[str(raw_target)] = raw_stage
            staged_target_sources[str(named_target)] = named_stage
        for wiki_name in preflight.WIKI_FILES:
            source = stage_root / "wiki" / wiki_name
            destination = preflight.ROOT / "wiki" / wiki_name
            preflight.require(digest(destination) == plan["wiki_baseline"][f"wiki/{wiki_name}"],
                              f"wiki changed immediately before publish: {destination}")
            guard.guard_destination(destination)
            published = True
            write_atomic(destination, source.read_bytes())

        current = preflight.current_snapshot_inventory(roots, preflight.EXPECTED_SNAPSHOTS + 4)
        base = plan["dated_snapshot_baseline"]
        preflight.require(set(current) - set(base) == target_paths,
                         "post-publish dated additions differ from exact four targets")
        preflight.require({k: v for k, v in current.items() if k in base} == base,
                         "a pre-existing dated snapshot changed during publication")
        for target, source in staged_target_sources.items():
            preflight.require(current[target] == directory_inventory(source),
                             f"published snapshot differs from staged source: {target}")
        for label, root in (("KLAPS50", roots[0]), ("Cloud-BAL", roots[1])):
            if digest(root / "graphify-out/graph.json") != final["corpora"][label]["sha256"]:
                raise RuntimeError(f"published current graph mismatch for {label}")
            stage_root_for_label = stage_root if label == "KLAPS50" else stage_maint
            for name in graph_files:
                expected = stage_root_for_label / "graphify-out" / name
                actual = root / "graphify-out" / name
                if expected.is_file():
                    preflight.require(actual.is_file() and digest(actual) == digest(expected),
                                      f"published graph artifact differs from staged output: {actual}")
                else:
                    preflight.require(not actual.exists(), f"unexpected published graph artifact: {actual}")
        for name in preflight.WIKI_FILES:
            preflight.require(digest(preflight.ROOT / "wiki" / name) ==
                              digest(stage_root / "wiki" / name),
                              f"published wiki file differs from staged output: {name}")
        for label, root in (("KLAPS50", roots[0]), ("Cloud-BAL", roots[1])):
            preflight.require(graphify_metadata_inventory(root / "graphify-out", graph_files) ==
                              plan["baseline_graphify_metadata"][label],
                              f"publication changed unplanned Graphify metadata for {label}")
        post_source_guards = verify_source_guards(plan)
        published_corpora = {}
        for label, root in (("KLAPS50", roots[0]), ("Cloud-BAL", roots[1])):
            report = root / "graphify-out/GRAPH_REPORT.md"
            mirror = preflight.ROOT / "wiki" / (
                "graph-report-klaps50.md" if label == "KLAPS50" else "graph-report-cloud-bal.md")
            named = root / "graphify-out" / preflight.PR103_SNAPSHOT
            published_corpora[label] = {
                **final["corpora"][label],
                "graph_path": str(root / "graphify-out/graph.json"),
                "current_graph_sha256": digest(root / "graphify-out/graph.json"),
                "report_path": str(report), "report_sha256": digest(report),
                "wiki_report_path": str(mirror), "wiki_report_sha256": digest(mirror),
                "snapshot_path": str(named),
                "snapshot_files_sha256": {name: digest(named / name) for name in SNAPSHOT_FILES},
            }
        receipt = {
            "schema": "pr103_amplitude_control_selected_source_graphify_kg_v1", "status": "PASS",
            **plan, "reviewed_plan_sha256": fingerprint,
            "root_go_record": {"path": str(root_go_path.resolve()), "sha256": digest(root_go_path),
                               "reviewed_by": go["reviewed_by"], "decision": "GO"},
            "recorded_utc": datetime.now(timezone.utc).isoformat(),
            "corpora": published_corpora,
            "private_profile_preservation": final["private_profile"],
            "limitations": final["limitations"],
            "post_apply_dated_snapshot_count": len(current),
            "post_apply_dated_snapshot_inventory_sha256": hashlib.sha256(json.dumps(
                current, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "post_apply_snapshot_additions": {path: current[path] for path in sorted(target_paths)},
            "post_apply_snapshot_roles": {
                path: (("GRAPHIFY_AUTOMATIC_RAW_SNAPSHOT_RENAMED_FOR_DATE_COLLISION"
                        if plan["automatic_raw_name_collision"] else "GRAPHIFY_AUTOMATIC_RAW_SNAPSHOT")
                       if Path(path).name == raw_name else "FINAL_NAMED_PR103_SNAPSHOT")
                for path in sorted(target_paths)},
            "post_apply_dated_snapshot_baseline_preserved": True,
            **post_source_guards,
            "inherited_immutable_pin_count_verified": plan["inherited_immutable_pin_count"],
            "wiki_sha256": {f"wiki/{name}": digest(preflight.ROOT / "wiki" / name)
                            for name in preflight.WIKI_FILES},
            "apply_wrapper_sha256": digest(Path(__file__)),
            "engine_helper_sha256": digest(Path(plan["pinned_helpers"]["pr98_engine"]["path"])),
            "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED",
        }
        (out / "kg_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        return receipt
    except BaseException as apply_error:
        if published:
            try:
                rollback(guard, backups, roots, target_paths, graph_files, preflight.WIKI_FILES, absent)
                verify_rollback(plan, backups, roots, graph_files)
            except BaseException as rollback_error:
                raise RuntimeError(f"ROLLBACK_FAILED: {rollback_error}") from rollback_error
            raise RuntimeError(f"APPLY_FAILED_ROLLED_BACK: {apply_error}") from apply_error
        raise RuntimeError(f"STAGING_FAILED_NO_MAINTAINED_WRITES: {apply_error}") from apply_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--pr-url", required=True)
    parser.add_argument("--results-manifest", required=True, type=Path)
    parser.add_argument("--results-sha256", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewed-plan-sha256")
    parser.add_argument("--root-go", type=Path)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    try:
        plan = preflight.preflight(args.commit, args.pr_url, args.results_manifest, args.results_sha256)
        fingerprint = plan_hash(plan)
        if args.check_only:
            print(json.dumps({"status": "CHECK_ONLY_NO_WRITES", "plan_sha256": fingerprint,
                              "plan": plan, "writes_performed": False}, indent=2))
            return 0
        preflight.require(args.reviewed_plan_sha256 == fingerprint,
                          "--apply requires the exact reviewed CHECK_ONLY plan hash")
        preflight.require(args.root_go is not None and args.out_dir is not None,
                          "--apply requires --root-go and a fresh --out-dir")
        receipt = apply(plan, fingerprint, args.root_go, args.out_dir)
        print(json.dumps({"status": "APPLY_COMPLETE", "receipt": str(args.out_dir / "kg_receipt.json"),
                          "post_apply_dated_snapshot_count": receipt["post_apply_dated_snapshot_count"]}, indent=2))
        return 0
    except BaseException as exc:
        reason = str(exc)
        status = ("ROLLBACK_FAILED" if reason.startswith("ROLLBACK_FAILED:") else
                  "APPLY_FAILED_ROLLED_BACK" if reason.startswith("APPLY_FAILED_ROLLED_BACK:") else
                  "BLOCKED_OR_STAGING_FAILED_NO_WRITES")
        print(json.dumps({"status": status, "reason": reason}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
