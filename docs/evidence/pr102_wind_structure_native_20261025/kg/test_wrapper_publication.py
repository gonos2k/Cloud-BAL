from __future__ import annotations

import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


preflight = load("pr102_kg_preflight_test", HERE / "preflight_kg.py")
apply = load("pr102_kg_apply_test", HERE / "apply_kg.py")


class TestGraphPathAllowlist(unittest.TestCase):
    def test_pr101_evidence_is_allowed_but_hash_only(self):
        path = "docs/evidence/pr101_cloud_thermo_native_20261023/kg/publication.md"
        prefixes = ("docs/PR101_", "docs/evidence/pr101_")
        self.assertTrue(preflight.graph_path_allowed(path, prefixes, set()))
        self.assertFalse(preflight.selected_path(path))

    def test_unknown_graph_path_is_rejected(self):
        self.assertFalse(preflight.graph_path_allowed("src/unrelated.f90", ("docs/PR102_",), set()))


class TestInheritedSnapshotInventory(unittest.TestCase):
    def test_keeps_two_raw_and_two_final_folders_distinct(self):
        prior = {f"/old/{i}": {} for i in range(112)}
        readback = {"new_dated_directories": {
            f"/new/{i}": {"role": role, "files": {"graph.json": {"sha256": str(i)}}}
            for i, role in enumerate([
                "GRAPHIFY_AUTOMATIC_RAW_SNAPSHOT_BEFORE_FINAL_PRESERVATION_AND_REPORT_CORRECTION",
                "GRAPHIFY_AUTOMATIC_RAW_SNAPSHOT_BEFORE_FINAL_PRESERVATION_AND_REPORT_CORRECTION",
                "FINAL_REVIEWED_PR101_SNAPSHOT", "FINAL_REVIEWED_PR101_SNAPSHOT"])
        }}
        merged = preflight.merge_published_snapshot_inventory(prior, readback)
        self.assertEqual(len(merged), 116)
        self.assertEqual(len(set(merged) - set(prior)), 4)

    def test_requires_exactly_two_of_each_publication_role(self):
        prior = {f"/old/{i}": {} for i in range(112)}
        with self.assertRaises(RuntimeError):
            preflight.merge_published_snapshot_inventory(prior, {"new_dated_directories": {}})


class TestRootGoGate(unittest.TestCase):
    def test_go_is_bound_to_exact_plan_source_and_raw_snapshot_date(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "go.json"
            path.write_text(json.dumps({"decision": "GO", "plan_sha256": "abc",
                                        "source_commit": "def", "automatic_snapshot_date": "2026-10-25",
                                        "reviewed_by": "root"}))
            self.assertEqual(apply.validate_root_go(path, "abc", "def", "2026-10-25")["decision"], "GO")
            with self.assertRaises(RuntimeError):
                apply.validate_root_go(path, "changed", "def", "2026-10-25")
            with self.assertRaises(RuntimeError):
                apply.validate_root_go(path, "abc", "def", "2026-10-26")

    def test_raw_snapshot_date_is_part_of_reviewed_plan_and_path_inventory(self):
        roots = (Path("/maint/KLAPS50"), Path("/maint/Cloud-BAL"))
        day_one = apply.expected_post_apply_snapshot_paths(roots, "2026-10-25",
                                                            "2026-10-25-pr102-wind-structure")
        day_two = apply.expected_post_apply_snapshot_paths(roots, "2026-10-26",
                                                            "2026-10-25-pr102-wind-structure")
        self.assertEqual(len(day_one), 4)
        self.assertEqual(len(day_two), 4)
        self.assertNotEqual(day_one, day_two)
        self.assertTrue(any(path.endswith("/2026-10-26") for path in day_two))
        plan_one = {"automatic_snapshot_date": "2026-10-25"}
        plan_two = {"automatic_snapshot_date": "2026-10-26"}
        self.assertNotEqual(apply.plan_hash(plan_one), apply.plan_hash(plan_two))


class TestPinnedEnginePublicationCorrection(unittest.TestCase):
    def setUp(self):
        self.plan = {"new_snapshot": "2026-10-25-pr102-wind-structure", "rollback_baseline": {}}
        self.receipt = {"corpora": {
            "KLAPS50": {"snapshot": "time", "nodes": 100, "edges": 200, "communities": 10,
                         "delta_nodes": 10, "delta_edges": 20},
            "Cloud-BAL": {"snapshot": "time", "nodes": 50, "edges": 75, "communities": 5,
                          "delta_nodes": 5, "delta_edges": 10},
        }}

    def test_graph_index_rewrites_only_engine_rows(self):
        baseline = (
            b"header\n"
            b"| KLAPS50 | `.` | 2026-10-23-pr101-cloud-thermo-native (PR101 Cloud-BAL native thermo) | 90 | 180 | 9 | [[graph-report-klaps50]] |\n"
            b"| Cloud-BAL | `Cloud-BAL/` | 2026-10-23-pr101-cloud-thermo-native (PR101 Cloud-BAL native thermo) | 45 | 65 | 4 | [[graph-report-cloud-bal]] |\n"
            b"tail\n"
        )
        self.plan["rollback_baseline"]["wiki/graph-report.md"] = hashlib.sha256(baseline).hexdigest()
        generated = (
            b"header\n"
            b"| KLAPS50 | `.` | 2026-10-25-pr102-wind-structure (PR98 native effect) | 100 | 200 | 10 | [[graph-report-klaps50]] |\n"
            b"| Cloud-BAL | `Cloud-BAL/` | 2026-10-25-pr102-wind-structure (PR98 native effect) | 50 | 75 | 5 | [[graph-report-cloud-bal]] |\n"
            b"tail\n"
        )
        updated = apply.rewrite_engine_graph_index(generated, baseline, self.plan, self.receipt)
        self.assertIn(b"(PR102 wind structure)", updated)
        self.assertNotIn(b"(PR98 native effect)", updated)
        self.assertTrue(updated.startswith(b"header\n"))
        self.assertTrue(updated.endswith(b"tail\n"))

    def test_graph_index_rejects_unexpected_engine_mutation(self):
        baseline = b"| KLAPS50 | old (PR101 C2 native closure) |\n| Cloud-BAL | old (PR101 C2 native closure) |\n"
        self.plan["rollback_baseline"]["wiki/graph-report.md"] = hashlib.sha256(baseline).hexdigest()
        with self.assertRaises(RuntimeError):
            apply.rewrite_engine_graph_index(b"unexpected\n", baseline, self.plan, self.receipt)

    def test_wiki_index_verifies_engine_output_then_sets_pr102_date(self):
        baseline = (
            b"---\ndate_modified: 2026-10-24\n---\n"
            b"## Graph snapshot\n\n- old snapshot\n"
            b"## Other\nkeep this section\n"
        )
        self.plan["rollback_baseline"]["wiki/index.md"] = hashlib.sha256(baseline).hexdigest()
        self.plan["automatic_snapshot_date"] = "2026-10-25"
        engine_output = apply.snapshot_index_bytes(
            baseline, self.plan["new_snapshot"], self.receipt, "2026-10-22")
        updated = apply.rewrite_engine_wiki_index(engine_output, baseline, self.plan, self.receipt)
        self.assertIn(b"date_modified: 2026-10-25", updated)
        self.assertIn(b"## Other\nkeep this section", updated)
        self.assertNotIn(b"old snapshot", updated)
        with self.assertRaises(RuntimeError):
            apply.rewrite_engine_wiki_index(engine_output + b"unexpected", baseline, self.plan, self.receipt)

    def test_wiki_and_log_publication_dates_follow_automatic_snapshot_date(self):
        baseline = (
            b"---\ndate_modified: 2026-10-24\n---\n"
            b"## Graph snapshot\n\n- old snapshot\n"
        )
        self.plan["rollback_baseline"]["wiki/index.md"] = hashlib.sha256(baseline).hexdigest()
        self.plan["automatic_snapshot_date"] = "2026-10-26"
        engine_output = apply.snapshot_index_bytes(
            baseline, self.plan["new_snapshot"], self.receipt, "2026-10-22")

        updated = apply.rewrite_engine_wiki_index(engine_output, baseline, self.plan, self.receipt)
        self.assertIn(b"date_modified: 2026-10-26", updated)

        engine = SimpleNamespace(BASE="2345bc1d", RESULTS_AUDIT_STATE="C2_640=OPEN", PRIOR_SHA="abc123")
        self.plan.update({
            "source_commit": "1e2c45eb", "approval_base": "1e2c45eb",
            "graph_selection_base": "2345bc1d", "pr": "https://github.com/gonos2k/Cloud-BAL/pull/102",
            "automatic_snapshot_date": "2026-10-26",
            "runtime_gates": {"C2_640": {"state": "OPEN"}},
            "maintained_source_snapshot_before": {"entry_count": 627, "sha256": "a" * 64},
            "immutable_pin_count_verified": 197,
        })
        log_entry = apply.format_log_entry(engine, self.plan, self.receipt, "pinned extraction limits")
        self.assertTrue(log_entry.startswith("## [2026-10-26] kg-update"))

    def test_log_replaces_only_pinned_engine_suffix_and_preserves_baseline(self):
        baseline = b"Historical PR101 entry\n"
        self.plan["rollback_baseline"]["wiki/log.md"] = hashlib.sha256(baseline).hexdigest()
        self.plan["source_commit"] = "1e2c45eb"
        self.plan["pr"] = "https://github.com/gonos2k/Cloud-BAL/pull/102"
        engine = SimpleNamespace(BASE="2345bc1d", RESULTS_AUDIT_STATE="C2_640=OPEN", PRIOR_SHA="abc123")
        generated_suffix = apply.expected_engine_log_suffix(engine, self.plan, self.receipt)
        entry = "## [2026-10-25] kg-update | PR102\n- gated\n"
        updated = apply.rewrite_engine_log(baseline + generated_suffix, baseline, generated_suffix, self.plan, entry)
        self.assertTrue(updated.startswith(baseline))
        self.assertEqual(updated, baseline + b"\n" + entry.encode())
        self.assertNotIn(b"PR98 native effect", updated)

    def test_log_rejects_mutated_baseline_prefix(self):
        baseline = b"Historical PR101 entry\n"
        self.plan["rollback_baseline"]["wiki/log.md"] = hashlib.sha256(baseline).hexdigest()
        with self.assertRaises(RuntimeError):
            apply.rewrite_engine_log(b"altered" + baseline, baseline, b"", self.plan, "PR102\n")

    def test_expected_engine_log_suffix_binds_current_plan_and_receipt(self):
        engine = SimpleNamespace(BASE="2345bc1d", RESULTS_AUDIT_STATE="C2_640=OPEN", PRIOR_SHA="abc123")
        self.plan["source_commit"] = "1e2c45eb"
        self.plan["pr"] = "https://github.com/gonos2k/Cloud-BAL/pull/102"
        receipt = {"corpora": {"KLAPS50": {"snapshot": "time", "nodes": 1, "edges": 2,
                                             "communities": 3, "delta_nodes": 4, "delta_edges": 5}}}
        result = apply.expected_engine_log_suffix(engine, self.plan, receipt)
        self.assertIn(b"1e2c45eb", result)
        self.assertIn(b"C2_640=OPEN", result)
        self.assertIn(b"abc123", result)


if __name__ == "__main__":
    unittest.main()
