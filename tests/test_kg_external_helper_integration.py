"""Integration checks bound to parent KG receipts and scratch helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestExternalPinnedHelperIntegration:
    def test_pr103_guard_chain_matches_actual_pr102_helper(self):
        preflight = load(
            "pr103_external_preflight_integration",
            ROOT / "docs/evidence/pr103_amplitude_control_20261026/kg/preflight_kg.py",
        )
        pr102 = preflight.load(
            "pr103_external_pr102_preflight_integration",
            preflight.SOURCE / "docs/evidence/pr102_wind_structure_native_20261025/kg/preflight_kg.py",
        )
        helper = pr102._load_pinned_helper()
        assert not hasattr(pr102, "GUARD")
        assert hasattr(helper, "GUARD")
        assert pr102.GUARD_SHA == helper.GUARD_SHA
        assert Path(helper.GUARD).is_file()
        assert preflight.sha(Path(helper.GUARD)) == helper.GUARD_SHA
        for name in ("PINNED_PYTHON", "PINNED_BIN", "snapshot_identity", "load",
                     "load_previous_helpers", "immutable_pin_snapshot", "PRIOR_HELPER_SHA"):
            assert hasattr(helper, name), name
        guard = helper.load("pr103_external_guard_api", helper.GUARD, pr102.GUARD_SHA)
        assert callable(guard.maintained_source_snapshot)
        _, protected, _ = helper.load_previous_helpers()
        assert callable(protected.protected_content)
        updater = helper.load("pr103_external_updater_api", preflight.UPDATER, preflight.UPDATER_SHA)
        auditor = helper.load("pr103_external_auditor_api", preflight.AUDITOR, preflight.AUDITOR_SHA)
        assert callable(updater.update_graph) and updater.GRAPH_FILES
        assert callable(auditor.record_snapshot) and callable(auditor.verify_private_profile)

    def test_pr104_parent_receipt_binds_124_snapshots(self):
        preflight = load(
            "pr104_external_preflight_integration",
            ROOT / "docs/evidence/pr104_validtime_observation_20261026/kg/preflight_kg.py",
        )
        assert preflight.sha(preflight.PRIOR) == preflight.PRIOR_SHA
        prior = preflight.json.loads(preflight.PRIOR.read_text())
        inventory = preflight.expected_published_inventory(prior)
        assert len(inventory) == 124
        assert prior["source_commit"] == preflight.PRIOR_COMMIT
        assert prior["maintained_source_snapshot"] == preflight.EXPECTED_SOURCE
        assert len(prior["inherited_immutable_pins_after"]) == 197

    def test_pr104_existing_pr102_pinned_helper_api_is_loaded(self):
        preflight = load(
            "pr104_external_helper_preflight_integration",
            ROOT / "docs/evidence/pr104_validtime_observation_20261026/kg/preflight_kg.py",
        )
        helper_path = preflight.SOURCE / "docs/evidence/pr102_wind_structure_native_20261025/kg/preflight_kg.py"
        assert helper_path.is_file()
        pr102 = load("pr104_external_pr102_preflight_integration", helper_path)
        helper = pr102._load_pinned_helper()
        assert pr102.GUARD_SHA == helper.GUARD_SHA
        assert Path(helper.GUARD).is_file()
        for name in ("PINNED_PYTHON", "PINNED_BIN", "snapshot_identity", "load",
                     "load_previous_helpers", "immutable_pin_snapshot", "PRIOR_HELPER_SHA"):
            assert hasattr(helper, name), name

    def test_pr105_parent_receipt_and_active_root_go_are_real(self):
        preflight = load(
            "pr105_external_preflight_integration",
            ROOT / "docs/evidence/pr105_observation_pairing_20261026/kg/preflight_kg.py",
        )
        assert preflight.sha(preflight.PRIOR) == preflight.PRIOR_SHA
        prior = preflight.json.loads(preflight.PRIOR.read_text())
        inventory = preflight.expected_published_inventory(prior)
        assert len(inventory) == 124
        assert prior["source_commit"] == preflight.PRIOR_COMMIT
        assert prior["maintained_source_snapshot"] == preflight.EXPECTED_SOURCE
        assert len(prior["inherited_immutable_pins_after"]) == 197
        assert len(prior["protected_content_sha256"]) == 13
        active = preflight.active250_root_go_snapshot()
        assert active["sha256"] == preflight.ACTIVE250_ROOT_GO_SHA
        assert active["source_pin_count"] == 250


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
