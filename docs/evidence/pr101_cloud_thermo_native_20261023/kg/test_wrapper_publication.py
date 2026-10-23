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


preflight = load("pr101_kg_preflight_test", HERE / "preflight_kg.py")
apply = load("pr101_kg_apply_test", HERE / "apply_kg.py")


class TestGraphPathAllowlist(unittest.TestCase):
    def test_pr100_evidence_is_allowed_but_hash_only(self):
        path = "docs/evidence/pr100_c2_native_closure_20261022/kg/publication.md"
        prefixes = ("docs/PR100_", "docs/evidence/pr100_")
        self.assertTrue(preflight.graph_path_allowed(path, prefixes, set()))
        self.assertFalse(preflight.selected_path(path))

    def test_unknown_graph_path_is_rejected(self):
        self.assertFalse(preflight.graph_path_allowed("src/unrelated.f90", ("docs/PR101_",), set()))


class TestPinnedEnginePublicationCorrection(unittest.TestCase):
    def setUp(self):
        self.plan = {"new_snapshot": "2026-10-23-pr101-cloud-thermo-native", "rollback_baseline": {}}
        self.receipt = {"corpora": {
            "KLAPS50": {"snapshot": "time", "nodes": 100, "edges": 200, "communities": 10,
                         "delta_nodes": 10, "delta_edges": 20},
            "Cloud-BAL": {"snapshot": "time", "nodes": 50, "edges": 75, "communities": 5,
                          "delta_nodes": 5, "delta_edges": 10},
        }}

    def test_graph_index_rewrites_only_engine_rows(self):
        baseline = (
            b"header\n"
            b"| KLAPS50 | `.` | 2026-10-22-pr100-c2-native-closure (PR100 C2 native closure) | 90 | 180 | 9 | [[graph-report-klaps50]] |\n"
            b"| Cloud-BAL | `Cloud-BAL/` | 2026-10-22-pr100-c2-native-closure (PR100 C2 native closure) | 45 | 65 | 4 | [[graph-report-cloud-bal]] |\n"
            b"tail\n"
        )
        self.plan["rollback_baseline"]["wiki/graph-report.md"] = hashlib.sha256(baseline).hexdigest()
        generated = (
            b"header\n"
            b"| KLAPS50 | `.` | 2026-10-23-pr101-cloud-thermo-native (PR98 native effect) | 100 | 200 | 10 | [[graph-report-klaps50]] |\n"
            b"| Cloud-BAL | `Cloud-BAL/` | 2026-10-23-pr101-cloud-thermo-native (PR98 native effect) | 50 | 75 | 5 | [[graph-report-cloud-bal]] |\n"
            b"tail\n"
        )
        updated = apply.rewrite_engine_graph_index(generated, baseline, self.plan, self.receipt)
        self.assertIn(b"(PR101 Cloud-BAL native thermo)", updated)
        self.assertNotIn(b"(PR98 native effect)", updated)
        self.assertTrue(updated.startswith(b"header\n"))
        self.assertTrue(updated.endswith(b"tail\n"))

    def test_graph_index_rejects_unexpected_engine_mutation(self):
        baseline = b"| KLAPS50 | old (PR100 C2 native closure) |\n| Cloud-BAL | old (PR100 C2 native closure) |\n"
        self.plan["rollback_baseline"]["wiki/graph-report.md"] = hashlib.sha256(baseline).hexdigest()
        with self.assertRaises(RuntimeError):
            apply.rewrite_engine_graph_index(b"unexpected\n", baseline, self.plan, self.receipt)

    def test_wiki_index_verifies_engine_output_then_sets_pr101_date(self):
        baseline = (
            b"---\ndate_modified: 2026-10-22\n---\n"
            b"## Graph snapshot\n\n- old snapshot\n"
            b"## Other\nkeep this section\n"
        )
        self.plan["rollback_baseline"]["wiki/index.md"] = hashlib.sha256(baseline).hexdigest()
        engine_output = apply.snapshot_index_bytes(
            baseline, self.plan["new_snapshot"], self.receipt, "2026-10-22")
        updated = apply.rewrite_engine_wiki_index(engine_output, baseline, self.plan, self.receipt)
        self.assertIn(b"date_modified: 2026-10-23", updated)
        self.assertIn(b"## Other\nkeep this section", updated)
        self.assertNotIn(b"old snapshot", updated)
        with self.assertRaises(RuntimeError):
            apply.rewrite_engine_wiki_index(engine_output + b"unexpected", baseline, self.plan, self.receipt)

    def test_log_replaces_only_pinned_engine_suffix_and_preserves_baseline(self):
        baseline = b"Historical PR100 entry\n"
        self.plan["rollback_baseline"]["wiki/log.md"] = hashlib.sha256(baseline).hexdigest()
        self.plan["source_commit"] = "d531fdd"
        self.plan["pr"] = "https://github.com/gonos2k/Cloud-BAL/pull/101"
        engine = SimpleNamespace(BASE="870dd5c9", RESULTS_AUDIT_STATE="P_C2_640=OPEN", PRIOR_SHA="abc123")
        generated_suffix = apply.expected_engine_log_suffix(engine, self.plan, self.receipt)
        entry = "## [2026-10-23] kg-update | PR101\n- gated\n"
        updated = apply.rewrite_engine_log(baseline + generated_suffix, baseline, generated_suffix, self.plan, entry)
        self.assertTrue(updated.startswith(baseline))
        self.assertEqual(updated, baseline + b"\n" + entry.encode())
        self.assertNotIn(b"PR98 native effect", updated)

    def test_log_rejects_mutated_baseline_prefix(self):
        baseline = b"Historical PR100 entry\n"
        self.plan["rollback_baseline"]["wiki/log.md"] = hashlib.sha256(baseline).hexdigest()
        with self.assertRaises(RuntimeError):
            apply.rewrite_engine_log(b"altered" + baseline, baseline, b"", self.plan, "PR101\n")

    def test_expected_engine_log_suffix_binds_current_plan_and_receipt(self):
        engine = SimpleNamespace(BASE="870dd5c9", RESULTS_AUDIT_STATE="P_C2_640=OPEN", PRIOR_SHA="abc123")
        self.plan["source_commit"] = "d531fdd"
        self.plan["pr"] = "https://github.com/gonos2k/Cloud-BAL/pull/101"
        receipt = {"corpora": {"KLAPS50": {"snapshot": "time", "nodes": 1, "edges": 2,
                                             "communities": 3, "delta_nodes": 4, "delta_edges": 5}}}
        result = apply.expected_engine_log_suffix(engine, self.plan, receipt)
        self.assertIn(b"d531fdd", result)
        self.assertIn(b"P_C2_640=OPEN", result)
        self.assertIn(b"abc123", result)


if __name__ == "__main__":
    unittest.main()
