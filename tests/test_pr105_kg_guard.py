from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parents[1] / "docs/evidence/pr105_observation_pairing_20261026/kg"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


preflight = load("pr105_kg_preflight_test", HERE / "preflight_kg.py")
sys.modules["preflight_kg"] = preflight
apply = load("pr105_kg_apply_test", HERE / "apply_kg.py")


class TestParentReceiptAndSnapshotPlan(unittest.TestCase):
    def test_corrected_pr103_parent_receipt_binds_current_parent(self):
        self.assertEqual(preflight.sha(preflight.PRIOR), preflight.PRIOR_SHA)
        prior = json.loads(preflight.PRIOR.read_text())
        inventory = preflight.expected_published_inventory(prior)
        self.assertEqual(len(inventory), 124)
        self.assertEqual(prior["source_commit"], preflight.PRIOR_COMMIT)
        self.assertEqual(prior["maintained_source_snapshot"], preflight.EXPECTED_SOURCE)
        self.assertEqual(len(prior["inherited_immutable_pins_after"]), 197)
        self.assertEqual(len(prior["protected_content_sha256"]), 13)
        active = preflight.active250_root_go_snapshot()
        self.assertEqual(active["sha256"], preflight.ACTIVE250_ROOT_GO_SHA)
        self.assertEqual(active["source_pin_count"], 250)

    def test_two_corpora_get_only_raw_and_named_pr105_targets(self):
        self.assertEqual(preflight.BASE, "334969e120afff720f1b5da4eb1d8f0991f1a6c1")
        self.assertEqual(preflight.GRAPH_BASE, "6d33aa06856e4e892dd792e8def350f15c54c058")
        self.assertEqual(preflight.PR105_SNAPSHOT, "2026-10-26-pr105-observation-pairing")
        raw = preflight.raw_snapshot_name("2026-10-26", True)
        self.assertEqual(raw, "2026-10-26-pr105-graphify-raw")
        targets = preflight.publication_paths((Path("/klaps50"), Path("/cloud-bal")),
                                              "2026-10-26", raw)
        self.assertEqual(len(targets), 4)
        self.assertEqual(preflight.EXPECTED_SNAPSHOTS + 4, 128)


class TestCombinedSourceSelection(unittest.TestCase):
    def test_allowlist_includes_missed_pr104_and_pr105_sources(self):
        for path in (
            "docs/PR104_VALIDTIME_FORECAST_20261026.md",
            "tools/pr104_validtime_observation.py",
            "tools/pr103_surface_temperature_observation.py",
            "tests/test_pr104_validtime_observation.py",
            "tools/pr86_time_response.py",
            "tests/test_pr86_time_response.py",
            "docs/PR105_OBSERVATION_PAIRING_20261026.md",
            "tools/pr105_paired_scores.py",
            "tests/test_pr105_paired_scores.py",
        ):
            self.assertTrue(preflight.graph_path_allowed(path), path)
            self.assertTrue(preflight.selected_path(path), path)

    def test_evidence_and_unrelated_paths_are_not_extracted(self):
        evidence = "docs/evidence/pr105_observation_pairing_20261026/kg/publication_design.md"
        self.assertTrue(preflight.graph_path_allowed(evidence))
        self.assertFalse(preflight.selected_path(evidence))
        self.assertFalse(preflight.graph_path_allowed("src/common/unrelated.f90"))
        self.assertFalse(preflight.graph_path_allowed("tools/pr103_unrelated.py"))


class TestCodeAndRuntimePhases(unittest.TestCase):
    def evidence_row(self, directory: Path, name: str, state: str, closed: bool) -> dict:
        path = directory / f"{name}.json"
        path.write_text(json.dumps({"name": name, "state": state}), encoding="utf-8")
        return {
            "state": state,
            "closed": closed,
            "evidence_path": str(path),
            "evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "scope": f"{name} evidence",
            "recorded_utc": "2026-10-26T10:00:00Z",
        }

    def manifest(self, directory: Path, runtime_state: str, runtime_closed: bool = False,
                 code_state: str = "PASS") -> tuple[Path, str]:
        body = {
            "schema": "pr105_kg_evidence_v1",
            "source_commit": "commit",
            "approval_base_commit": preflight.BASE,
            "graph_selection_base_commit": preflight.GRAPH_BASE,
            "pr_url": "https://github.com/gonos2k/Cloud-BAL/pull/105",
            "code_validation": self.evidence_row(directory, "code", code_state, True),
            "runtime_observation": {
                **self.evidence_row(directory, "runtime", runtime_state, runtime_closed),
                "evidence_path": str(preflight.RUNTIME_STATUS),
                "evidence_sha256": preflight.RUNTIME_STATUS_SHA,
                "recorded_utc": json.loads(preflight.RUNTIME_STATUS.read_text())["observed_utc"],
            },
            "forecast_verdict": "PENDING",
            "physical_approval": "FAIL_OPEN",
            "observation_skill": "NOT_EVALUATED",
        }
        path = directory / "results_manifest.json"
        path.write_text(json.dumps(body), encoding="utf-8")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_code_pass_and_running_observation_keep_pending_forecast_verdict(self):
        with tempfile.TemporaryDirectory() as temp:
            path, digest = self.manifest(Path(temp), "RUNNING")
            result = preflight.validate_manifest(
                path, digest, "commit", "https://github.com/gonos2k/Cloud-BAL/pull/105")
        self.assertEqual(result["code_validation"]["state"], "PASS")
        self.assertEqual(result["runtime_observation"]["state"], "RUNNING")
        self.assertFalse(result["runtime_observation"]["closed"])
        self.assertEqual(result["forecast_verdict"], "PENDING")
        self.assertEqual(result["physical_approval"], "FAIL_OPEN")
        self.assertEqual(result["observation_skill"], "NOT_EVALUATED")

    def test_pending_verdict_cannot_be_misreported_as_runtime_state(self):
        with tempfile.TemporaryDirectory() as temp:
            path, digest = self.manifest(Path(temp), "PENDING")
            with self.assertRaisesRegex(RuntimeError, "runtime observation"):
                preflight.validate_manifest(
                    path, digest, "commit", "https://github.com/gonos2k/Cloud-BAL/pull/105")

    def test_running_observation_cannot_be_marked_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path, digest = self.manifest(Path(temp), "RUNNING", runtime_closed=True)
            with self.assertRaisesRegex(RuntimeError, "closed flag"):
                preflight.validate_manifest(
                    path, digest, "commit", "https://github.com/gonos2k/Cloud-BAL/pull/105")

    def test_nonpass_code_validation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path, digest = self.manifest(Path(temp), "RUNNING", code_state="INCOMPLETE")
            with self.assertRaisesRegex(RuntimeError, "code validation"):
                preflight.validate_manifest(
                    path, digest, "commit", "https://github.com/gonos2k/Cloud-BAL/pull/105")


class TestReceiptPhase(unittest.TestCase):
    def test_root_go_binds_the_reviewed_plan_and_stage_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "root_go.json"
            path.write_text(json.dumps({
                "decision": "GO",
                "plan_sha256": "plan-hash",
                "stage_sha256": "stage-receipt-hash",
                "source_commit": "commit",
                "automatic_snapshot_date": "2026-10-26",
                "reviewed_by": "root",
            }))
            go = apply.load_root_go(path, "plan-hash", "stage-receipt-hash",
                                    "commit", "2026-10-26")
            self.assertEqual(go["decision"], "GO")
            with self.assertRaisesRegex(RuntimeError, "exact plan"):
                apply.load_root_go(path, "plan-hash", "other-stage-hash",
                                   "commit", "2026-10-26")

    def test_apply_receipt_marks_kg_publication_separately(self):
        tree = ast.parse((HERE / "apply_kg.py").read_text())
        assignment = next(node for node in ast.walk(tree)
                          if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "receipt"
                                  for target in node.targets)
                          and isinstance(node.value, ast.Dict)
                          and any(isinstance(key, ast.Constant) and key.value == "schema" and
                                  isinstance(value, ast.Constant) and value.value ==
                                  "pr105_observation_pairing_selected_source_graphify_kg_v1"
                                  for key, value in zip(node.value.keys, node.value.values)))
        pairs = [(key, value) for key, value in zip(assignment.value.keys, assignment.value.values)
                 if (key is None and isinstance(value, ast.Name) and value.id == "plan") or
                 (isinstance(key, ast.Constant) and key.value in
                  {"schema", "status", "writes_performed", "preflight_status"})]
        expression = ast.Expression(ast.Dict(keys=[key for key, _ in pairs],
                                             values=[value for _, value in pairs]))
        plan = {"schema": "plan", "status": "PREFLIGHT_PASS_NO_WRITES", "writes_performed": False}
        result = eval(compile(ast.fix_missing_locations(expression), "receipt phase", "eval"),
                      {"plan": plan})
        self.assertEqual(result["schema"], "pr105_observation_pairing_selected_source_graphify_kg_v1")
        self.assertEqual(result["status"], "PASS")
        self.assertIs(result["writes_performed"], True)
        self.assertEqual(result["preflight_status"], "PREFLIGHT_PASS_NO_WRITES")
        self.assertFalse(plan["writes_performed"])


if __name__ == "__main__":
    unittest.main()
