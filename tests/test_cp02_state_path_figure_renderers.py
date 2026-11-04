"""Integrity and scope checks for the new CP02 state-path figure renderers."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


native = load("cp02_native_plot", "tools/plot_cp02_state_path_native.py")
rain = load("cp02_rain_plot", "tools/plot_cp02_rain_number_evaluation.py")


def test_rain_renderer_rejects_modified_receipt_bound_input(tmp_path):
    folder = tmp_path / "analysis"
    folder.mkdir()
    data = folder / "categorical_scores.csv"
    data.write_text("case,lead_hour,threshold_mm,CSI\n", encoding="utf-8")
    required = {"categorical_scores.csv", "continuous_scores.csv", "admission_constraints.csv", "winner.json",
                *(f"hour_{hour}_arrays.npz" for hour in rain.HOURS)}
    outputs = {"categorical_scores.csv": {"size_bytes": data.stat().st_size, "sha256": rain.sha256(data)}}
    for name in required - outputs.keys():
        path = folder / name
        path.write_bytes(b"fixture")
        outputs[name] = {"size_bytes": path.stat().st_size, "sha256": rain.sha256(path)}
    receipt = {"status": "COMPLETE", "rows": {"categorical": 108, "continuous": 18, "constraints": 26}, "outputs": outputs}
    (folder / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    data.write_text(data.read_text() + "changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        rain.verify_analysis(folder)


def test_native_scope_rejects_missing_frozen_point(tmp_path):
    folder = tmp_path / "analysis"
    folder.mkdir()
    outputs = []
    for name in ("global_checkpoint_comparison.csv", "selected_ledger_summary.csv", "selected_point_first_differences.csv",
                 "selected_history.npz", "earliest_divergence.json", "ledger_summary.json"):
        path = folder / name
        path.write_text("fixture", encoding="utf-8")
        outputs.append({"path": name, "size_bytes": path.stat().st_size, "sha256": native.sha256(path)})
    receipt = {"status": "complete", "selected_point_ids": list(native.POINTS[:-1]), "outputs": outputs}
    (folder / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="eight frozen points"):
        native.verify_analysis(folder)


def test_rain_score_scope_keeps_every_lead_threshold_and_case():
    rows = []
    for case in rain.CASES:
        for lead in range(1, 7):
            for threshold in rain.THRESHOLDS:
                rows.append({"case": case, "lead_hour": str(lead), "threshold_mm": str(threshold), "CSI": "0.25"})
    scores = {(r["case"], int(r["lead_hour"]), float(r["threshold_mm"])): float(r["CSI"]) for r in rows}
    assert len(scores) == 108
    assert set(scores) == {(case, lead, threshold) for case in rain.CASES for lead in range(1, 7) for threshold in rain.THRESHOLDS}


def test_candidate_arrays_require_actual_sample_coordinates(tmp_path):
    path = tmp_path / "hour_13_arrays.npz"
    n = 3688
    np.savez(path, reference=np.zeros(n), ORIGINAL=np.zeros(n), IMPROVED_BG_FIXED=np.zeros(n),
             B1_RAIN_NUMBER_PRIOR=np.zeros(n), latitude=np.arange(n, dtype=float),
             longitude=np.arange(n, dtype=float), flat_index_yx=np.arange(n))
    values = rain._npz_values(path)
    assert values["latitude"].shape == (3688,)
    with np.load(path) as arrays:
        broken = {key: arrays[key] for key in arrays.files}
    broken["flat_index_yx"][-1] = broken["flat_index_yx"][-2]
    np.savez(path, **broken)
    with pytest.raises(ValueError, match="duplicate paired sample"):
        rain._npz_values(path)


def test_all_valid_hours_share_absolute_and_delta_map_scales():
    hourly = {}
    for index, hour in enumerate(rain.HOURS):
        base = np.full(3688, index + 1.0)
        hourly[hour] = {"reference": base, "ORIGINAL": base + index,
                        "IMPROVED_BG_FIXED": base + 2 * index,
                        "B1_RAIN_NUMBER_PRIOR": base + 3 * index}
    absolute, delta = rain.shared_map_scales(hourly)
    assert absolute == (1.0, 21.0)
    assert delta == 10.0
    cmap, norm, bounds = rain.precipitation_norm(absolute)
    assert norm.vmin == absolute[0] and norm.vmax == absolute[1]
    assert bounds[0] == absolute[0] and bounds[-1] == absolute[1]
    assert all(rain.precipitation_norm(absolute)[1].vmax == 21.0 for _hour in rain.HOURS)


def test_native_checkpoint_layout_preserves_public_private_field_sets():
    schema = json.loads((ROOT / "docs/evidence/cp02_state_path_20261104/native/state_schema.json").read_text())
    public, private, public_stages, private_stages = native.checkpoint_layout(schema)
    assert (len(public), len(private)) == (14, 15)
    assert public_stages == ("entry", "wrapper_return")
    assert private_stages == ("pre_update", "post_process", "kdm62d_return")
    assert len(public) * len(public_stages) + len(private) * len(private_stages) == 73
