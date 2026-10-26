from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parents[1] / "docs/evidence/pr104_validtime_observation_20261026/kg"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


preflight = load("pr104_kg_preflight_test", HERE / "preflight_kg.py")
sys.modules["preflight_kg"] = preflight
apply = load("pr104_kg_apply_test", HERE / "apply_kg.py")


class TestParentReceiptAndSnapshotLineage(unittest.TestCase):
    def test_corrected_pr103_parent_receipt_binds_124_snapshots(self):
        self.assertEqual(preflight.sha(preflight.PRIOR), preflight.PRIOR_SHA)
        prior = json.loads(preflight.PRIOR.read_text())
        inventory = preflight.expected_published_inventory(prior)
        self.assertEqual(len(inventory), 124)
        self.assertEqual(prior["source_commit"], preflight.PRIOR_COMMIT)
        self.assertEqual(prior["maintained_source_snapshot"], preflight.EXPECTED_SOURCE)
        self.assertEqual(len(prior["inherited_immutable_pins_after"]), 197)

    def test_existing_pr102_pinned_helper_api_is_loaded_without_copying_it(self):
        helper_path = preflight.SOURCE / "docs/evidence/pr102_wind_structure_native_20261025/kg/preflight_kg.py"
        self.assertTrue(helper_path.is_file())
        pr102 = load("pr104_actual_pr102_preflight_api_test", helper_path)
        helper = pr102._load_pinned_helper()
        self.assertEqual(pr102.GUARD_SHA, helper.GUARD_SHA)
        self.assertTrue(Path(helper.GUARD).is_file())
        for name in ("PINNED_PYTHON", "PINNED_BIN", "snapshot_identity", "load",
                     "load_previous_helpers", "immutable_pin_snapshot", "PRIOR_HELPER_SHA"):
            self.assertTrue(hasattr(helper, name), name)

    def test_raw_date_collision_and_exact_four_publication_targets(self):
        raw_name = preflight.raw_snapshot_name("2026-10-26", True)
        self.assertEqual(raw_name, "2026-10-26-pr104-graphify-raw")
        roots = (Path("/klaps50"), Path("/cloud-bal"))
        targets = preflight.publication_paths(roots, "2026-10-26", raw_name)
        self.assertEqual(len(targets), 4)
        self.assertEqual(sum("pr104-graphify-raw" in path for path in targets), 2)
        self.assertEqual(sum(preflight.PR104_SNAPSHOT in path for path in targets), 2)
        self.assertEqual(preflight.EXPECTED_SNAPSHOTS + 4, 128)

    def test_unoccupied_day_preserves_automatic_graphify_raw_name(self):
        self.assertEqual(preflight.raw_snapshot_name("2026-10-27", False), "2026-10-27")


class TestFinalGateClosure(unittest.TestCase):
    def manifest(self, directory: Path, states: dict[str, str]) -> tuple[Path, str]:
        rows = {}
        for name, state in states.items():
            evidence = directory / f"{name}.json"
            evidence.write_text(json.dumps({"gate": name, "state": state}), encoding="utf-8")
            rows[name] = {
                "state": state,
                "closed": True,
                "evidence_path": str(evidence),
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "scope": f"closed {name} result",
            }
        manifest = {
            "schema": "pr104_integration_results_v1",
            "source_commit": "commit",
            "approval_base_commit": preflight.BASE,
            "graph_selection_base_commit": preflight.GRAPH_BASE,
            "pr_url": "https://github.com/gonos2k/Cloud-BAL/pull/104",
            "runtime_gates": rows,
            "physical_approval": "FAIL_OPEN",
            "observation_skill": "NOT_EVALUATED",
        }
        path = directory / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_closed_pass_fail_incomplete_and_not_evaluated_states_are_preserved(self):
        states = {
            "hydro_3600": "FAIL",
            "amplitude_3600": "INCOMPLETE",
            "structured_3600": "PASS",
            "valid_time_observation": "NOT_EVALUATED",
        }
        with tempfile.TemporaryDirectory() as temp:
            path, digest = self.manifest(Path(temp), states)
            result = preflight.validate_manifest(path, digest, "commit",
                                                  "https://github.com/gonos2k/Cloud-BAL/pull/104")
        self.assertEqual(result["runtime_gates"], states)
        self.assertEqual(result["physical_approval"], "FAIL_OPEN")
        self.assertEqual(result["observation_skill"], "NOT_EVALUATED")

    def test_open_or_unclosed_gate_is_rejected(self):
        states = {name: "PASS" for name in preflight.REQUIRED_GATES}
        with tempfile.TemporaryDirectory() as temp:
            path, digest = self.manifest(Path(temp), states)
            manifest = json.loads(path.read_text())
            manifest["runtime_gates"]["hydro_3600"]["state"] = "OPEN"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "closed terminal state"):
                preflight.validate_manifest(path, hashlib.sha256(path.read_bytes()).hexdigest(), "commit",
                                            "https://github.com/gonos2k/Cloud-BAL/pull/104")

        with tempfile.TemporaryDirectory() as temp:
            path, digest = self.manifest(Path(temp), states)
            manifest = json.loads(path.read_text())
            manifest["runtime_gates"]["structured_3600"]["closed"] = False
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "closed terminal state"):
                preflight.validate_manifest(path, hashlib.sha256(path.read_bytes()).hexdigest(), "commit",
                                            "https://github.com/gonos2k/Cloud-BAL/pull/104")


class TestSelectionAndReceiptPhase(unittest.TestCase):
    def test_selection_is_exact_to_pr104_and_two_shared_pr86_paths(self):
        self.assertEqual(preflight.SOURCE, Path(__file__).resolve().parents[1])
        self.assertEqual(preflight.BASE, "6d33aa06856e4e892dd792e8def350f15c54c058")
        for path in (
            "docs/PR104_VALIDTIME_FORECAST_20261026.md",
            "tools/pr104_validtime_observation.py",
            "tools/pr103_surface_temperature_observation.py",
            "tests/test_pr104_validtime_observation.py",
            "tools/pr86_time_response.py",
            "tests/test_pr86_time_response.py",
        ):
            self.assertTrue(preflight.graph_path_allowed(path), path)
            self.assertTrue(preflight.selected_path(path), path)
        evidence = "docs/evidence/pr104_validtime_observation_20261026/kg/publication_design.md"
        self.assertTrue(preflight.graph_path_allowed(evidence))
        self.assertFalse(preflight.selected_path(evidence))
        self.assertFalse(preflight.graph_path_allowed("src/common/unrelated.f90"))
        self.assertFalse(preflight.graph_path_allowed("tools/pr103_unrelated.py"))

    def test_apply_receipt_fields_override_read_only_plan_fields(self):
        tree = ast.parse((HERE / "apply_kg.py").read_text())
        assignment = next(node for node in ast.walk(tree)
                          if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "receipt"
                                  for target in node.targets)
                          and isinstance(node.value, ast.Dict))
        pairs = [(key, value) for key, value in zip(assignment.value.keys, assignment.value.values)
                 if (key is None and isinstance(value, ast.Name) and value.id == "plan") or
                 (isinstance(key, ast.Constant) and key.value in
                  {"schema", "status", "writes_performed", "preflight_status"})]
        expression = ast.Expression(ast.Dict(keys=[key for key, _ in pairs],
                                             values=[value for _, value in pairs]))
        plan = {"schema": "plan", "status": "PREFLIGHT_PASS_NO_WRITES", "writes_performed": False}
        result = eval(compile(ast.fix_missing_locations(expression), "receipt phase", "eval"),
                      {"plan": plan})
        self.assertEqual(result["schema"], "pr104_validtime_observation_selected_source_graphify_kg_v1")
        self.assertEqual(result["status"], "PASS")
        self.assertIs(result["writes_performed"], True)
        self.assertEqual(result["preflight_status"], "PREFLIGHT_PASS_NO_WRITES")
        self.assertFalse(plan["writes_performed"])


if __name__ == "__main__":
    unittest.main()
