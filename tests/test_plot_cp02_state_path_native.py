"""Native state-path renderer schema and axis contracts."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_state_path_renderer", ROOT / "tools/plot_cp02_state_path_native.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def test_global_checkpoint_layout_keeps_distinct_public_and_private_fields():
    schema = json.loads((ROOT / "docs/evidence/cp02_state_path_20261104/native/state_schema.json").read_text())
    public, private, public_stages, private_stages = native.checkpoint_layout(schema)
    assert (len(public), len(private)) == (14, 15)
    assert public_stages == ("entry", "wrapper_return")
    assert private_stages == ("pre_update", "post_process", "kdm62d_return")
    assert len(public) * len(public_stages) + len(private) * len(private_stages) == 73
    assert "TH_PUBLIC_RAW" in public and "T_K_DERIVED_TH_TIMES_PII" in public
    assert "NR_PUBLIC_RAW" in public and "NR_INTERNAL" in private


def test_history_contract_keeps_all_eight_points_and_between_timestep_axis(tmp_path):
    path = tmp_path / "selected_history.npz"
    arrays = {name: np.zeros(shape, dtype=np.float32) for name, shape in (
        ("D_entry", (360, 39, 8, 14)), ("D_return", (360, 39, 8, 14)),
        ("within_delta", (360, 39, 8, 14)), ("between_delta", (359, 39, 8, 14)))}
    arrays.update(point_ids=np.asarray(native.POINTS), fields=np.asarray([f"field_{i}" for i in range(14)]),
                  between_time=np.arange(2, 361))
    np.savez(path, **arrays)
    values = native._load_history(tmp_path)
    assert tuple(values["point_ids"]) == native.POINTS
    assert np.array_equal(values["between_time"], np.arange(2, 361))
    values["between_time"] = np.arange(1, 360)
    assert not np.array_equal(values["between_time"], np.arange(2, 361))


def test_global_checkpoint_rows_reject_incomplete_scope():
    schema = json.loads((ROOT / "docs/evidence/cp02_state_path_20261104/native/state_schema.json").read_text())
    public, private, public_stages, private_stages = native.checkpoint_layout(schema)
    assert len(public) * len(public_stages) + len(private) * len(private_stages) == 73
    with pytest.raises(ValueError, match="14 public and 15 private"):
        native.checkpoint_layout({"global_stages": {"entry": {"fields_float32": ["x"]},
                                                    "pre_update": {"fields_float32": ["y"]}}})
