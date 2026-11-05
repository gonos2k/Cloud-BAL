#!/usr/bin/env python3
"""Independently validate the frozen grouped-forecast KG stage without publishing."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
KG = ROOT / "docs/evidence/cp02_grouped_forecast_20261105/kg"
EVIDENCE = ROOT / "docs/evidence/cp02_grouped_forecast_20261105"
STAMP = "2026-11-05-grouped-forecast"
GRAPH_FILES = ("graph.json", "GRAPH_REPORT.md", "manifest.json")
WIKI_FILES = ("graph-report.md", "graph-report-klaps50.md", "graph-report-cloud-bal.md",
              "index.md", "log.md")
MAINTAINED = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing or unsafe JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def graph_counts(graph: dict) -> dict:
    nodes = graph.get("nodes", [])
    edges = graph.get("links", graph.get("edges", []))
    return {"nodes": len(nodes), "edges": len(edges),
            "communities": len({node.get("community") for node in nodes
                                 if node.get("community") is not None})}


def graph_integrity(graph: dict) -> dict:
    nodes = {row["id"] for row in graph.get("nodes", []) if "id" in row}
    links = graph.get("links", graph.get("edges", []))
    edge_seen, endpoint_counts = set(), {}
    duplicates = 0
    missing, dangling, self_loops = 0, 0, 0
    for edge in links:
        source, target = edge.get("source"), edge.get("target")
        missing += source is None or target is None
        dangling += ((source is not None and source not in nodes)
                     or (target is not None and target not in nodes))
        self_loops += source == target
        endpoint_counts[(source, target)] = endpoint_counts.get((source, target), 0) + 1
        signature = json.dumps(edge, sort_keys=True, separators=(",", ":"))
        if signature in edge_seen:
            duplicates += 1
        edge_seen.add(signature)
    return {"missing_endpoint_edges": int(missing), "dangling_endpoint_edges": int(dangling),
            "self_loop_edges": int(self_loops), "exact_duplicate_edges": duplicates,
            "same_endpoint_group_count": sum(count > 1 for count in endpoint_counts.values())}


def check_graph_corpus(label: str, stage: Path, baseline: dict,
                       lock: dict, receipt: dict) -> dict:
    maintained_root = MAINTAINED if label == "KLAPS50" else MAINTAINED / "Cloud-BAL"
    prior_graph = json.loads((maintained_root / "graphify-out/graph.json").read_text(encoding="utf-8"))
    graph_root = stage / label / "graphify-out"
    snapshot = graph_root / STAMP
    require(snapshot.is_dir() and not snapshot.is_symlink(), f"{label}: snapshot missing/unsafe")
    files = sorted(path.name for path in snapshot.iterdir())
    require(files == sorted(GRAPH_FILES), f"{label}: snapshot must contain exactly active graph trio")
    staged_graph = {}
    hashes = receipt["corpora"][label]["snapshot_file_sha256"]
    require(set(hashes) == set(GRAPH_FILES), f"{label}: receipt graph-file set differs")
    for name in GRAPH_FILES:
        active, saved = graph_root / name, snapshot / name
        require(active.is_file() and not active.is_symlink() and saved.is_file() and not saved.is_symlink(),
                f"{label}: active or dated {name} is missing/unsafe")
        require(sha256(active) == sha256(saved) == hashes[name], f"{label}: {name} hash mismatch")
    staged_graph = json.loads((graph_root / "graph.json").read_text(encoding="utf-8"))
    before, after = graph_counts(prior_graph), graph_counts(staged_graph)
    require(before == receipt["corpora"][label]["before"], f"{label}: before graph counts differ")
    require(after == receipt["corpora"][label]["after"], f"{label}: after graph counts differ")
    integrity = graph_integrity(staged_graph)
    require(not any(integrity.values()), f"{label}: staged graph integrity is nonzero: {integrity}")
    require(integrity == receipt["corpora"][label].get("integrity_zero_counts"),
            f"{label}: receipt integrity counts differ from independent recomputation")
    prior_ids = {node["id"] for node in prior_graph.get("nodes", []) if "id" in node}
    staged_ids = {node["id"] for node in staged_graph.get("nodes", []) if "id" in node}
    require(prior_ids <= staged_ids, f"{label}: prior graph nodes were removed")

    old_manifest = json.loads((maintained_root / "graphify-out/manifest.json").read_text(encoding="utf-8"))
    new_manifest = json.loads((graph_root / "manifest.json").read_text(encoding="utf-8"))
    selected = set(lock["selected_source_sha256"])
    selected_manifest_keys = {f"Cloud-BAL/{path}" for path in selected} if label == "KLAPS50" else selected
    require(set(receipt["corpora"][label].get("selected_manifest_keys", [])) == selected_manifest_keys,
            f"{label}: receipt manifest keys do not match reviewed source selection")
    changed = {key for key in set(old_manifest) | set(new_manifest)
               if old_manifest.get(key) != new_manifest.get(key)}
    require(set(old_manifest) <= set(new_manifest), f"{label}: manifest pruned previous rows")
    require(changed <= selected_manifest_keys,
            f"{label}: manifest changed unselected rows: {sorted(changed-selected_manifest_keys)[:5]}")
    return {"before": before, "after": after,
            "delta": {key: after[key] - before[key] for key in before},
            "integrity_zero_counts": integrity, "prior_node_ids_preserved": len(prior_ids),
            "removed_prior_node_ids": 0, "manifest_changed_keys": len(changed),
            "snapshot_sha256": hashes}


def check_wiki(stage: Path) -> None:
    wiki = stage / "wiki"
    require(wiki.is_dir() and {path.name for path in wiki.iterdir()} == set(WIKI_FILES),
            "stage wiki must contain exactly five maintained mirrors")
    require(all(path.is_file() and not path.is_symlink() for path in wiki.iterdir()),
            "stage wiki contains an unsafe or non-file entry")
    require((wiki / "graph-report-klaps50.md").read_bytes() ==
            (stage / "KLAPS50/graphify-out/GRAPH_REPORT.md").read_bytes(),
            "KLAPS50 wiki report mirror differs from staged report")
    require((wiki / "graph-report-cloud-bal.md").read_bytes() ==
            (stage / "Cloud-BAL/graphify-out/GRAPH_REPORT.md").read_bytes(),
            "Cloud-BAL wiki report mirror differs from staged report")
    old_report = (MAINTAINED / "wiki/graph-report.md").read_text(encoding="utf-8").splitlines()
    new_report = (wiki / "graph-report.md").read_text(encoding="utf-8").splitlines()
    prefixes = ("| KLAPS50 |", "| Cloud-BAL |")
    for prefix in prefixes:
        require(sum(line.startswith(prefix) for line in old_report) == 1
                and sum(line.startswith(prefix) for line in new_report) == 1,
                "graph-report index must have exactly one row per corpus")
    require([line for line in old_report if not line.startswith(prefixes)] ==
            [line for line in new_report if not line.startswith(prefixes)],
            "graph-report index changed text outside the two corpus rows")
    old_index = (MAINTAINED / "wiki/index.md").read_text(encoding="utf-8")
    new_index = (wiki / "index.md").read_text(encoding="utf-8")
    marker = "## Graph snapshot"
    require(old_index.count(marker) == new_index.count(marker) == 1,
            "wiki index must contain one Graph snapshot section")

    def outside_snapshot(text: str) -> tuple[str, str]:
        start = text.index(marker)
        end = text.find("\n## ", start + len(marker))
        if end < 0:
            end = len(text)
        prefix, suffix = text[:start], text[end:]
        import re
        prefix, count = re.subn(r"(?m)^(date_modified:\s*)[^\r\n]+", r"\1<DATE>", prefix, count=1)
        require(count == 1, "wiki index date_modified is missing or ambiguous")
        return prefix, suffix

    require(outside_snapshot(old_index) == outside_snapshot(new_index),
            "wiki index changed content outside Graph snapshot section")
    old_log = (MAINTAINED / "wiki/log.md").read_bytes()
    new_log = (wiki / "log.md").read_bytes()
    require(new_log.startswith(old_log), "stage did not preserve the previous wiki log as a byte prefix")
    heading = b"\n## [2026-11-05] kg-update | B1 grouped forecast\n"
    suffix = new_log[len(old_log):]
    require(suffix.startswith(heading) and suffix.count(heading) == 1,
            "stage wiki log must append exactly one grouped forecast entry")


def validate() -> dict:
    helper_spec = __import__("importlib.util", fromlist=["spec_from_file_location"])
    spec = helper_spec.spec_from_file_location("grouped_prepare", KG / "prepare_kg.py")
    if spec is None or spec.loader is None:
        raise ValueError("cannot load frozen KG prepare helper")
    helper = helper_spec.module_from_spec(spec)
    spec.loader.exec_module(helper)

    baseline = helper.verify_baseline()
    lock_path = KG / "selection_lock.json"
    stage_path = KG / "stage_receipt.json"
    lock, receipt = load(lock_path), load(stage_path)
    baseline_hash, lock_hash, receipt_hash = sha256(KG / "baseline.json"), sha256(lock_path), sha256(stage_path)
    require(lock.get("status") == "FROZEN" and lock.get("review_status") == "GO",
            "selection lock is not frozen with independent source/evidence GO")
    require(lock.get("snapshot") == STAMP and lock.get("source_commit") == baseline["source_worktree"]["head"],
            "selection lock snapshot or source commit differs from baseline")
    require(receipt.get("status") == "STAGED_ONLY_NO_MAINTAINED_WRITES"
            and receipt.get("maintained_roots_written") is False,
            "stage receipt does not declare isolated stage-only state")
    require(receipt.get("snapshot") == STAMP and receipt.get("dated_snapshots_preserved") == 244,
            "stage receipt did not preserve 244 existing snapshots")
    require(receipt.get("baseline_sha256") == baseline_hash == lock.get("baseline_sha256"),
            "baseline hashes differ across receipts")
    require(receipt.get("selection_lock_sha256") == lock_hash
            and lock.get("review_sha256") == sha256(EVIDENCE / "review/independent_kg_review.json"),
            "selection review or lock binding differs")

    selected = lock.get("selected_source_sha256", {})
    hash_only = lock.get("hash_only_sha256", {})
    require(selected and len(selected) == len(set(selected)), "selected-source set is empty or duplicated")
    require(receipt.get("source_extraction_scope") == sorted(selected)
            and receipt.get("manifest_update_scope") == sorted(selected),
            "receipt source extraction or manifest update scope differs from freeze")
    require(receipt.get("hash_only_sha256") == hash_only, "hash-only inventory differs from freeze")
    for relative, expected in {**selected, **hash_only}.items():
        path = ROOT / relative
        require(path.is_file() and not path.is_symlink() and sha256(path) == expected,
                f"frozen source/evidence hash mismatch: {relative}")

    stage = Path(receipt["stage"])
    require(stage.is_dir() and not stage.is_symlink(), "isolated stage missing or unsafe")
    corpora = {label: check_graph_corpus(label, stage, baseline, lock, receipt)
               for label in ("KLAPS50", "Cloud-BAL")}
    check_wiki(stage)
    staged_wiki = receipt.get("staged_wiki_sha256", {})
    require(set(staged_wiki) == set(WIKI_FILES), "receipt must hash exactly five wiki mirrors")
    require(all(sha256(stage / "wiki" / name) == expected for name, expected in staged_wiki.items()),
            "staged wiki hashes differ from receipt")

    raw_extractions = receipt.get("raw_extractions", [])
    require(len(raw_extractions) == 2, "expected raw extraction receipts for both corpus updates")
    for row in raw_extractions:
        path = Path(row["path"])
        require(path.is_file() and not path.is_symlink() and sha256(path) == row["sha256"],
                "raw extraction hash mismatch")
        json.loads(path.read_text(encoding="utf-8"))

    source_graph = ROOT / "graphify-out"
    cloud_graph = stage / "Cloud-BAL/graphify-out"
    cloud_hashes = receipt["corpora"]["Cloud-BAL"]["snapshot_file_sha256"]
    for name in GRAPH_FILES:
        require(sha256(source_graph / name) ==
                baseline["maintained_roots"]["Cloud-BAL"]["active_graph_trio_sha256"][name],
                f"source worktree active {name} changed since baseline")
        require(sha256(cloud_graph / name) == cloud_hashes[name],
                f"source worktree copy input differs for {name}")
    source_snapshot = source_graph / STAMP
    require(not source_snapshot.exists() and not source_snapshot.is_symlink(),
            "source worktree dated snapshot must remain absent before publication")
    require(helper.snapshot_inventory(MAINTAINED) == baseline["maintained_roots"]["KLAPS50"]["dated_snapshots"]
            and helper.snapshot_inventory(MAINTAINED / "Cloud-BAL") ==
            baseline["maintained_roots"]["Cloud-BAL"]["dated_snapshots"],
            "staging altered maintained roots")

    checks = {
        "baseline_244_snapshots_and_dirty_roots": {"pass": True, "detail": "Read-only baseline verifier confirms the unchanged 120/124 snapshot inventories, graph trios, wiki mirrors, HEADs and dirty-state hashes."},
        "stage_scope_and_source_pins": {"pass": True, "detail": f"Frozen lock and receipt bind {len(selected)} selected Python sources and {len(hash_only)} hash-only files."},
        "graph_integrity_prior_nodes_and_manifest_subset": {"pass": True, "detail": "Both graph JSONs parse; prior nodes are retained; independently recomputed integrity counts are zero; manifest updates are confined to the selected paths."},
        "dated_snapshots_and_deltas": {"pass": True, "detail": "Both staged graph trios match their separately dated snapshots; counts and deltas are independently recomputed."},
        "five_wiki_mirrors_and_old_content": {"pass": True, "detail": "Exactly five mirrors are hash-bound; report mirrors match staged reports; old log bytes remain a prefix."},
        "raw_extraction_hashes": {"pass": True, "detail": "Both retained raw extraction artifacts match their receipt hashes and parse as JSON."},
        "source_worktree_mirror_and_no_writes": {"pass": True, "detail": "Active Cloud-BAL graph trio remains at baseline; four source mirror targets are staged; no maintained root was written."},
        "publisher_target_inventory": {"pass": True, "detail": "The staged publication inventory contains six active graph files, two dated directories and five wiki files (13 targets)."},
    }
    return {"schema": "cp02_grouped_forecast_independent_kg_stage_validation_v1",
            "status": "PASS_STAGED_ONLY", "maintained_roots_written": False,
            "baseline_sha256": baseline_hash, "selection_lock_sha256": lock_hash,
            "stage_receipt_sha256": receipt_hash, "stage": str(stage),
            "maintained_snapshot_count": 244, "source_pin_count": len(selected),
            "hash_only_pin_count": len(hash_only), "target_count": 13,
            "source_worktree_target_count": 4, "checks": checks, "graph_deltas": corpora,
            "raw_extractions": raw_extractions,
            "limits": ["Only reviewed Python source paths are structurally extracted; other new evidence is hash-only.",
                       "External import targets may be absent; Fortran cross-file CALL extraction is partial.",
                       "Graph freshness does not establish runtime behavior, physical correctness, conservation or scientific validity."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=KG / "stage_validation.json")
    args = parser.parse_args()
    result = validate()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(f"preserve existing stage validation: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]),
                      "stage": result["stage"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
