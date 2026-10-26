from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "docs/evidence/pr103_amplitude_control_20261026/kg"
SPEC = importlib.util.spec_from_file_location("pr103_kg_preflight_test", HERE / "preflight_kg.py")
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
sys.modules["preflight_kg"] = preflight
SPEC.loader.exec_module(preflight)
APPLY_SPEC = importlib.util.spec_from_file_location("pr103_kg_apply_test", HERE / "apply_kg.py")
assert APPLY_SPEC is not None and APPLY_SPEC.loader is not None
apply = importlib.util.module_from_spec(APPLY_SPEC)
sys.modules[APPLY_SPEC.name] = apply
APPLY_SPEC.loader.exec_module(apply)


class TestRawSnapshotCollision(unittest.TestCase):
    def test_existing_automatic_day_gets_distinct_pr103_raw_name(self):
        self.assertEqual(preflight.raw_snapshot_name("2026-10-26", True),
                         "2026-10-26-pr103-graphify-raw")

    def test_unoccupied_automatic_day_keeps_graphify_name(self):
        self.assertEqual(preflight.raw_snapshot_name("2026-10-27", False), "2026-10-27")

    def test_four_targets_are_two_raw_and_two_final_named(self):
        roots = (Path("/a"), Path("/b"))
        targets = preflight.publication_paths(roots, "2026-10-26", "2026-10-26-pr103-graphify-raw")
        self.assertEqual(len(targets), 4)
        self.assertEqual(sum("pr103-graphify-raw" in path for path in targets), 2)
        self.assertEqual(sum("2026-10-26-pr103-amplitude-control" in path for path in targets), 2)
        self.assertTrue(all("/2026-10-26" not in path or "-pr103-" in path for path in targets))

    def test_automatic_date_changes_plan_fingerprint(self):
        day_one = {"automatic_snapshot_date": "2026-10-26",
                   "automatic_raw_publish_name": "2026-10-26-pr103-graphify-raw"}
        day_two = {"automatic_snapshot_date": "2026-10-27",
                   "automatic_raw_publish_name": "2026-10-27"}
        self.assertNotEqual(apply.plan_hash(day_one), apply.plan_hash(day_two))

    def test_root_go_binds_plan_source_and_automatic_date(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "go.json"
            path.write_text(json.dumps({"decision": "GO", "plan_sha256": "plan",
                                        "source_commit": "commit", "automatic_snapshot_date": "2026-10-26",
                                        "reviewed_by": "root"}))
            self.assertEqual(apply.load_root_go(path, "plan", "commit", "2026-10-26")["decision"], "GO")
            with self.assertRaises(RuntimeError):
                apply.load_root_go(path, "plan", "commit", "2026-10-27")

    def test_curated_stage_metadata_enables_graphify_raw_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            labels = out / ".graphify_labels.json"
            labels.write_text(json.dumps({"1": "Maintained label"}))
            self.assertTrue(preflight.automatic_backup_condition(out)["automatic_backup_enabled"])


class TestInheritedSnapshotContract(unittest.TestCase):
    def test_exact_116_plus_four_parent_folders_are_retained(self):
        baseline = {f"/old/{number}": {} for number in range(116)}
        additions = {f"/new/{number}": {"graph.json": {"sha256": f"{number:064x}"}}
                     for number in range(4)}
        roles = {f"/new/{number}": ("GRAPHIFY_AUTOMATIC_RAW_SNAPSHOT" if number < 2
                                    else "FINAL_NAMED_PR102_SNAPSHOT") for number in range(4)}
        prior = {
            "status": "PASS", "source_commit": preflight.PRIOR_COMMIT,
            "post_apply_dated_snapshot_count": 120,
            "maintained_source_snapshot_after": preflight.EXPECTED_SOURCE,
            "immutable_pin_count_verified": 197,
            "inherited_immutable_pins_after": {f"pin{n}": {} for n in range(197)},
            "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED",
            "dated_snapshot_baseline": baseline,
            "post_apply_snapshot_additions": additions,
            "post_apply_snapshot_roles": roles,
        }
        merged_for_hash = {**baseline, **additions}
        prior["post_apply_dated_snapshot_inventory_sha256"] = __import__("hashlib").sha256(
            json.dumps(merged_for_hash, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        merged = preflight.expected_published_inventory(prior)
        self.assertEqual(len(merged), 120)
        self.assertEqual(set(merged) - set(baseline), set(additions))

    def test_missing_or_ambiguous_parent_role_is_rejected(self):
        prior = {
            "status": "PASS", "source_commit": preflight.PRIOR_COMMIT,
            "post_apply_dated_snapshot_count": 120,
            "maintained_source_snapshot_after": preflight.EXPECTED_SOURCE,
            "immutable_pin_count_verified": 197,
            "inherited_immutable_pins_after": {f"pin{n}": {} for n in range(197)},
            "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED",
            "dated_snapshot_baseline": {f"/old/{n}": {} for n in range(116)},
            "post_apply_snapshot_additions": {}, "post_apply_snapshot_roles": {},
        }
        with self.assertRaises(RuntimeError):
            preflight.expected_published_inventory(prior)


class TestStageGraphInventory(unittest.TestCase):
    def test_full_staged_file_set_can_be_bound_before_graphify(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            graph_out = Path(temp)
            contents = {"graph.json": b"graph", "GRAPH_REPORT.md": b"report",
                        "manifest.json": b"manifest", ".graphify_labels.json": b"labels"}
            for name, data in contents.items():
                (graph_out / name).write_bytes(data)
            inventory = apply.graphify_file_inventory(graph_out)
            expected = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
            self.assertEqual(inventory, expected)


class TestSelectionBoundary(unittest.TestCase):
    def test_source_root_is_the_pr103_cloud_bal_checkout(self):
        self.assertEqual(preflight.SOURCE, Path(__file__).resolve().parents[1])

    def test_pr103_evidence_is_hash_only(self):
        path = "docs/evidence/pr103_amplitude_control_20261026/kg/publication_design.md"
        self.assertTrue(preflight.graph_path_allowed(path))
        self.assertFalse(preflight.selected_path(path))

    def test_only_two_shared_pr86_paths_are_allowed(self):
        self.assertTrue(preflight.selected_path("tools/pr86_time_response.py"))
        self.assertFalse(preflight.graph_path_allowed("tools/pr86_unrelated.py"))
        self.assertFalse(preflight.graph_path_allowed("src/common/unrelated.f90"))

    def test_ifx_oracle_is_exactly_allowlisted_and_other_programs_rejected(self):
        oracle = "tests/pr103_gdtost_oracle_program.f90"
        comparator = "tests/compare_pr103_gdtost_oracle.py"
        self.assertTrue(preflight.graph_path_allowed(oracle))
        self.assertTrue(preflight.selected_path(oracle))
        self.assertTrue(preflight.graph_path_allowed(comparator))
        self.assertTrue(preflight.selected_path(comparator))
        self.assertFalse(preflight.graph_path_allowed("tests/pr103_unrelated_program.f90"))
        self.assertFalse(preflight.graph_path_allowed("tests/compare_pr103_unrelated.py"))
        self.assertTrue(preflight.selected_path("tests/test_pr103_amplitude_control.py"))


class TestPinnedPr102HelperBindings(unittest.TestCase):
    def test_guard_api_is_read_from_the_actual_pinned_helper(self):
        pr102 = preflight.load(
            "pr103_actual_pr102_preflight_api_test",
            preflight.SOURCE / "docs/evidence/pr102_wind_structure_native_20261025/kg/preflight_kg.py",
        )
        helper = pr102._load_pinned_helper()
        self.assertFalse(hasattr(pr102, "GUARD"))
        self.assertTrue(hasattr(helper, "GUARD"))
        self.assertEqual(pr102.GUARD_SHA, helper.GUARD_SHA)
        self.assertTrue(Path(helper.GUARD).is_file())
        self.assertEqual(preflight.sha(Path(helper.GUARD)), helper.GUARD_SHA)
        for name in ("PINNED_PYTHON", "PINNED_BIN", "snapshot_identity", "load",
                     "load_previous_helpers", "immutable_pin_snapshot", "PRIOR_HELPER_SHA"):
            self.assertTrue(hasattr(helper, name), name)
        guard = helper.load("pr103_actual_guard_api_test", helper.GUARD, pr102.GUARD_SHA)
        self.assertTrue(callable(guard.maintained_source_snapshot))
        _, protected, _ = helper.load_previous_helpers()
        self.assertTrue(callable(protected.protected_content))
        updater = helper.load("pr103_actual_updater_api_test", preflight.UPDATER, preflight.UPDATER_SHA)
        auditor = helper.load("pr103_actual_auditor_api_test", preflight.AUDITOR, preflight.AUDITOR_SHA)
        self.assertTrue(callable(updater.update_graph))
        self.assertTrue(updater.GRAPH_FILES)
        self.assertTrue(callable(auditor.record_snapshot))
        self.assertTrue(callable(auditor.verify_private_profile))


class TestManifestEvidenceHash(unittest.TestCase):
    def test_gate_evidence_must_match_its_file_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = root / "receipt.json"
            evidence.write_text("{}\n")
            import hashlib
            digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
            gates = {name: {"state": "OPEN", "evidence_sha256": digest,
                            "evidence_path": str(evidence), "scope": "bounded test scope"}
                     for name in preflight.REQUIRED_GATES}
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema": "pr103_integration_results_v1", "source_commit": "commit",
                "approval_base_commit": preflight.BASE,
                "graph_selection_base_commit": preflight.GRAPH_BASE,
                "pr_url": "https://github.com/gonos2k/Cloud-BAL/pull/103",
                "runtime_gates": gates, "physical_approval": "FAIL_OPEN",
                "observation_skill": "NOT_EVALUATED",
            }))
            manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
            parsed = preflight.validate_manifest(
                manifest, manifest_sha, "commit", "https://github.com/gonos2k/Cloud-BAL/pull/103")
            self.assertEqual(parsed["runtime_gates"], {name: "OPEN" for name in preflight.REQUIRED_GATES})
            gates["observation_input_consistency"]["evidence_sha256"] = "0" * 64
            manifest.write_text(json.dumps({
                "schema": "pr103_integration_results_v1", "source_commit": "commit",
                "approval_base_commit": preflight.BASE,
                "graph_selection_base_commit": preflight.GRAPH_BASE,
                "pr_url": "https://github.com/gonos2k/Cloud-BAL/pull/103",
                "runtime_gates": gates, "physical_approval": "FAIL_OPEN",
                "observation_skill": "NOT_EVALUATED",
            }))
            manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
            with self.assertRaises(RuntimeError):
                preflight.validate_manifest(
                    manifest, manifest_sha, "commit", "https://github.com/gonos2k/Cloud-BAL/pull/103")


if __name__ == "__main__":
    unittest.main()
