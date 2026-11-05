from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "b1_failure_focus", ROOT / "tools/plot_cp02_b1_failure_focus.py")
plot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plot)


def test_real_focus_counts_and_hit_only_repair_algebra():
    receipt, hourly, _, _ = plot.grouped.verify_analysis(plot.ANALYSIS)
    assert receipt["initial_time_utc"] == "2026-08-16T12:00:00Z"
    counts = plot.exact_counts(hourly)
    assert [counts[key] for key in (
        "h2_weak_c_recovered", "h2_weak_still_lost", "h2_new_fa", "h2_resolved_fa",
        "h5_new_5mm_fa", "h5_resolved_5mm_fa", "h5_5mm_hit_loss", "h5_5mm_hit_gain",
        "h5_weak_c_lost")] == [3, 7, 53, 24, 12, 1, 1, 0, 17]
    assert counts["h5_A_CSI"] == pytest.approx(0.19891500904159132)
    assert (counts["h5_csi_delta_hit_numerator"], counts["h5_csi_delta_fa_numerator"],
            counts["h5_csi_delta_numerator"], counts["h5_csi_delta_denominator"]) == (-553, -1210, -1763, 553 * 564)
    assert counts["h5_hit_only_repair_CSI"] == pytest.approx(110 / (330 + 234))
    assert counts["h5_hit_only_repair_CSI"] < counts["h5_A_CSI"]
    assert (counts["h5_A_hit"], counts["h5_C_hit"], counts["h5_C_fa"] - counts["h5_A_fa"]) == (110, 109, 11)
    masks = plot.focus_masks(hourly)
    target_receipt, cohorts, controls, algebra = plot.verify_targets(
        plot.TARGETS, hourly, plot.ANALYSIS, masks, counts)
    assert target_receipt["matched_control_pairs"] == 158
    assert target_receipt["reused_control_ids_across_cohorts"] == 21
    assert {key: int(mask.sum()) for key, mask in cohorts.items()}["h02_loss_recovered_by_C"] == 3
    assert len(controls["h2_weak_matched_controls"]) == 10
    assert algebra["restored_baseline_hit_with_candidate_F_exact_CSI"] == "55/282"
    states, state_receipt = plot.load_state_bundle(plot.STATE, hourly, target_receipt)
    assert len(states) == 28 and state_receipt["status"] == "PASS"
    assert max(row["max_abs_error_mm"] for row in state_receipt["surface_score_checks"]) < 1e-10
    for point in plot.SERIES_POINTS:
        assert point in set(map(int, states[("B1_OLD_KDM6", 13)]["flat_index_yx"]))


def test_analysis_and_sealed_bundles_load_after_relocation(tmp_path):
    relocated = tmp_path / "clean-export" / "analysis"
    shutil.copytree(plot.ANALYSIS, relocated)
    receipt, hourly, _, _ = plot.grouped.verify_analysis(relocated)
    assert receipt["initial_time_utc"] == "2026-08-16T12:00:00Z"
    counts = plot.exact_counts(hourly)
    masks = plot.focus_masks(hourly)
    target_receipt, _, _, _ = plot.verify_targets(
        plot.TARGETS, hourly, relocated, masks, counts)
    states, state_receipt = plot.load_state_bundle(plot.STATE, hourly, target_receipt)
    assert len(states) == 28
    assert state_receipt["status"] == "PASS"


def test_context_layer_contrasts_recount_from_native_corners(tmp_path):
    _, hourly, _, _ = plot.grouped.verify_analysis(plot.ANALYSIS)
    counts = plot.exact_counts(hourly)
    target, _, _, _ = plot.verify_targets(
        plot.TARGETS, hourly, plot.ANALYSIS, plot.focus_masks(hourly), counts)
    states, state_receipt = plot.load_state_bundle(plot.STATE, hourly, target)
    rows, receipt = plot.load_context(plot.CONTEXT, target, state_receipt)
    assert receipt["status"] == "COMPLETE"
    plot.configure_font()
    output = tmp_path / "conditional.png"
    summary = plot.draw_physical_context(
        rows, plot.read_csv(plot.TARGETS / "matched_controls.csv"),
        plot.read_csv(plot.TARGETS / "focus_membership.csv"), states, output)
    assert output.stat().st_size > 100_000
    assert summary["1_0_h05_A_C_5mm_new_FA"]["n"] == 12
    assert summary["1_0_h05_A_C_5mm_new_FA"]["median"] == pytest.approx(-0.002375116243126009)
    assert summary["1_0_control_for:h05_A_C_5mm_new_FA"]["median"] == pytest.approx(-0.0020790, abs=1e-8)


def test_mutated_context_fails_before_creating_output(tmp_path, monkeypatch):
    context = tmp_path / "context"
    shutil.copytree(plot.CONTEXT, context)
    with (context / "layer_features.csv").open("ab") as stream:
        stream.write(b"mutation")
    monkeypatch.setattr(plot, "CONTEXT", context)
    output = tmp_path / "figures"
    with pytest.raises(ValueError, match="context output hash mismatch: layer_features.csv"):
        plot.render(plot.ANALYSIS, output)
    assert not output.exists()


def test_focus_masks_are_disjoint_for_h2_weak_partition():
    _, hourly, _, _ = plot.grouped.verify_analysis(plot.ANALYSIS)
    masks = plot.focus_masks(hourly)
    assert not np.any(masks["h2_weak_c_recovered"] & masks["h2_weak_still_lost"])
    assert not np.any(masks["h2_weak_c_recovered"] & masks["h2_weak_retained"])
    assert not np.any(masks["h2_weak_still_lost"] & masks["h2_weak_retained"])


def test_empty_h5_event_scope_is_rejected():
    empty = {name: np.zeros(0, dtype=float) for name in
             ("reference", "A", "C", "ORIGINAL", "B", "D", "latitude", "longitude")}
    hourly = {hour: empty for hour in range(13, 19)}
    with pytest.raises(ValueError, match="CSI denominator is empty"):
        plot.exact_counts(hourly)


def test_mutated_source_preserves_existing_output(tmp_path):
    analysis = tmp_path / "analysis"
    shutil.copytree(plot.ANALYSIS, analysis)
    output = tmp_path / "figures"
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    with (analysis / "hour_14_arrays.npz").open("ab") as stream:
        stream.write(b"mutation")
    with pytest.raises(ValueError, match="analysis output hash mismatch"):
        plot.render(analysis, output)
    assert not output.exists()
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_renderer_refuses_existing_output(tmp_path):
    output = tmp_path / "figures"
    output.mkdir()
    marker = output / "marker"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        plot.render(plot.ANALYSIS, output)
    assert marker.read_text(encoding="utf-8") == "keep"


def test_mutated_target_table_fails_before_creating_output(tmp_path, monkeypatch):
    targets = tmp_path / "targets"
    shutil.copytree(plot.TARGETS, targets)
    with (targets / "csi_algebra.csv").open("ab") as stream:
        stream.write(b"mutation")
    monkeypatch.setattr(plot, "TARGETS", targets)
    output = tmp_path / "figures"
    with pytest.raises(ValueError, match="target output hash mismatch: csi_algebra.csv"):
        plot.render(plot.ANALYSIS, output)
    assert not output.exists()
