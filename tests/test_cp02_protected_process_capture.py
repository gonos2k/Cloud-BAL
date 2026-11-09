from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("capture", ROOT / "tools/cp02_protected_process_capture.py")
capture = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = capture
SPEC.loader.exec_module(capture)


def _make_quick_inventory(path: Path) -> None:
    path.mkdir()
    for rank in range(8):
        (path / f"state_calls_rank{rank}.txt").touch()
        (path / f"surface_cp04_rank{rank}.bin").touch()
        for stage in ("entry", "return"):
            (path / f"state_selected_{stage}_t000001-000003_rank{rank}.bin").touch()
        (path / f"cp04_t000001-000003_rank{rank}.bin").touch()


def _launch_receipt(tmp_path: Path, mode: str) -> tuple[Path, str]:
    import json

    plan = json.loads(capture.QUICK_PLAN_PATH.read_text(encoding="utf-8"))
    hours = ("12",) if mode == "quick" else tuple(f"{hour:02d}" for hour in range(12, 18))
    status = "RAW_PROBE_COMPLETED_AWAITING_CAPTURE_GATE" if mode == "quick" else "PASS"
    arms = {}
    for arm in ("OLD", "FIX"):
        arms[arm] = {"arm": arm, "stage": mode, "status": status, "exit_code": 0,
                     "success_marker": True, "case_path": str(tmp_path / arm),
                     "history_comparisons": {hour: {"all_variables_coordinates_attributes_exact": True}
                                             for hour in hours}}
    receipt = {"stage": mode, "status": status,
               "duration_seconds": 20 if mode == "quick" else 18000,
               "quick_plan_sha256": capture.sha256(capture.QUICK_PLAN_PATH),
               "build_receipt_sha256": plan["pins"]["build_receipt_sha256"], "arms": arms}
    path = tmp_path / f"{mode}_launch_receipt.json"
    path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    return path, capture.sha256(path)


def test_mode_contracts_are_sealed_and_noninterchangeable():
    # The launch receipt supplies the exact plan hash; no mutable plan hash is
    # embedded in the collector source.
    tmp_path = Path(__import__("tempfile").mkdtemp())
    quick_receipt, quick_sha = _launch_receipt(tmp_path, "quick")
    full_receipt, full_sha = _launch_receipt(tmp_path, "full")
    quick = capture.load_mode_contract("quick", quick_receipt, quick_sha)
    full = capture.load_mode_contract("full", full_receipt, full_sha)
    assert quick.actual_steps == (1,)
    assert quick.process_steps == (1,)
    assert quick.plan_sha256 == quick.quick_plan_sha256
    assert full.plan_path == capture.PLAN_FREEZE_PATH
    assert full.plan_sha256 == capture.sha256(capture.PLAN_FREEZE_PATH)
    assert full.quick_plan_sha256 == capture.sha256(capture.QUICK_PLAN_PATH)
    assert full.actual_steps == tuple(range(1, 901))
    assert full.process_steps == tuple(range(1, 361)) + tuple(range(721, 901))
    with pytest.raises(ValueError, match="exactly"):
        capture.load_mode_contract("quick-2h", quick_receipt, quick_sha)
    with pytest.raises(ValueError, match="launch-receipt hash"):
        capture.load_mode_contract("quick", quick_receipt, "0" * 64)


def test_quick_inventory_requires_exact_one_step_chunks(tmp_path):
    case = tmp_path / "quick"
    _make_quick_inventory(case)
    receipt, receipt_sha = _launch_receipt(tmp_path, "quick")
    mode = capture.load_mode_contract("quick", receipt, receipt_sha)
    files = capture.validate_case_file_inventory(case, mode)
    assert len(files["calls"]) == len(files["surface"]) == len(files["process"]) == 8
    assert all("000001-000003" in path.name for path in files["entry"] + files["return"] + files["process"])

    (case / "cp04_t000004-000006_rank0.bin").touch()
    with pytest.raises(ValueError, match="process filenames differ"):
        capture.validate_case_file_inventory(case, mode)


def test_process_chunks_reject_the_uncaptured_gap(tmp_path):
    path = tmp_path / "cp04_t000361-000363_rank0.bin"
    path.touch()
    with pytest.raises(ValueError, match="outside its accepted window"):
        capture.validate_process_chunk_step(path, 361)


def test_full_chunk_axis_preserves_the_360_to_721_gap():
    tmp_path = Path(__import__("tempfile").mkdtemp())
    receipt, receipt_sha = _launch_receipt(tmp_path, "full")
    full = capture.load_mode_contract("full", receipt, receipt_sha)
    starts = capture.chunk_starts(full.process_steps)
    assert 358 in starts
    assert 361 not in starts
    assert 718 not in starts
    assert 721 in starts
    assert len(full.process_steps) == 540
    state_chunks = capture.expected_chunk_names("state_selected_entry", full.process_steps, (0,))
    assert "state_selected_entry_t000358-000360_rank0.bin" in state_chunks
    assert "state_selected_entry_t000721-000723_rank0.bin" in state_chunks
    assert "state_selected_entry_t000361-000363_rank0.bin" not in state_chunks


def test_call_inventory_detects_missing_and_overlapping_cell_owners(tmp_path):
    paths = []
    for rank in range(8):
        path = tmp_path / f"state_calls_rank{rank}.txt"
        paths.append(path)
        # Only rank 0 owns selected (1,1); the other ranks own an adjacent core.
        i = 1 if rank == 0 else 2
        row = [1, rank, rank + 1,
               1, 3, 1, 3, 1, 3,
               1, 3, 1, 3, 1, 3,
               i, i, 1, 1, 1, 1]
        path.write_text(" ".join(map(str, row)) + "\n", encoding="ascii")
    inventory = capture.read_call_inventory(paths, [(1, 1)], steps=1, levels=1)
    assert inventory.owners_rank[0, 0, 0] == 0

    paths[0].write_text("", encoding="ascii")
    with pytest.raises(ValueError, match="missing rank-step rows"):
        capture.read_call_inventory(paths, [(1, 1)], steps=1, levels=1)

    overlap = [tmp_path / f"overlap_rank{rank}.txt" for rank in range(8)]
    for rank, path in enumerate(overlap):
        path.write_text(" ".join(map(str, [1, rank, rank + 1,
                                           1, 3, 1, 3, 1, 3,
                                           1, 3, 1, 3, 1, 3,
                                           1, 1, 1, 1, 1, 1])) + "\n", encoding="ascii")
        path.rename(tmp_path / f"state_calls_rank{rank}.txt")
    with pytest.raises(ValueError, match="overlapping selected native core"):
        capture.read_call_inventory(paths, [(1, 1)], steps=1, levels=1)


def _frame_bytes(count: int = 16, payload_count: int = 16) -> bytes:
    frame = b"C4FR0001" + struct.pack(">8i", 0, 1, 1, 1, 1, 1, 1, 39)
    frame += struct.pack(">10f", *([1.0] * 10))
    frame += struct.pack(">i", 1)
    frame += struct.pack(">7i", 1, 1, 0, 0, 0, 0, count)
    frame += struct.pack(">" + "f" * payload_count, *([1.0] * payload_count))
    return frame + struct.pack(">i", -1)


def test_stream_parser_checks_schema_width_and_truncation(tmp_path):
    path = tmp_path / "cp04_t000001-000003_rank0.bin"
    path.write_bytes(_frame_bytes())
    parsed = list(capture.iter_process_frames(path, {1: 16}, rank=0))
    assert parsed[0][0].timestep == 1
    assert len(parsed[0][1][0].values) == 16

    path.write_bytes(_frame_bytes(count=15, payload_count=15))
    with pytest.raises(ValueError, match="wrong field count"):
        list(capture.iter_process_frames(path, {1: 16}, rank=0))

    path.write_bytes(_frame_bytes()[:-3])
    with pytest.raises(ValueError, match="truncated stream"):
        list(capture.iter_process_frames(path, {1: 16}, rank=0))


def test_conditional_phases_can_be_absent_but_required_condensation_cannot():
    import json
    import numpy as np

    schema = json.loads(capture.SCHEMA_PATH.read_text(encoding="utf-8"))
    cohort = capture.Cohort([(1, 1)], ["cell-1"], ["RN1_1"], np.zeros((1, 4), dtype=np.int32),
                            np.full((1, 4), 0.25), {"RN1_1": ["test"]})
    owners_rank = np.zeros((1, 39, 1), dtype=np.int16)
    owners_call = np.ones((1, 39, 1), dtype=np.int32)
    inventory = capture.CallInventory(owners_rank, owners_call, {(1, 0, 1): (1, 1, 1, 1, 1, 39)},
                                      {(1, 0, 1): 39}, (0,))
    frame = capture.Frame(0, 1, 1, 1, 1, 1, 1, 39, tuple([1.0] * 10))

    def records(include_phase12=True):
        out = []
        for k in range(1, 40):
            for phase in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12):
                if phase == 12 and not include_phase12:
                    continue
                width = len(schema["phases"][str(phase)]["fields"])
                loop = 0 if phase in (1, 2) else 1
                loops = 0 if phase in (1, 2) else 1
                substep, mstep = (1, 1) if phase in (9, 10) else (0, 0)
                out.append(capture.Record(phase, 1, k, loop, loops, substep, mstep,
                                          np.ones(width, dtype=np.float32)))
        return out

    slab = capture.ProcessSlab((1,), schema, 1)
    required = (1, 2, 3, 4, 5, 6, 7, 8, 11, 12)
    capture._store_process_frame(frame, records(), slab, cohort, inventory, {(1, 1): 0}, required)
    assert slab.phase_masks[5].all() and slab.phase_masks[8].all()
    assert slab.phase_masks[11].all() and slab.phase_masks[12].all()
    assert slab.sed_pre_mask.all() and slab.sed_post_mask.all()

    invalid = capture.ProcessSlab((1,), schema, 1)
    with pytest.raises(ValueError, match="missing mandatory phase 12"):
        capture._store_process_frame(frame, records(include_phase12=False), invalid, cohort, inventory,
                                     {(1, 1): 0}, required)

    for missing_phase in (5, 6, 7, 8):
        invalid = capture.ProcessSlab((1,), schema, 1)
        with pytest.raises(ValueError, match=f"missing mandatory phase {missing_phase}"):
            capture._store_process_frame(frame,
                [record for record in records() if record.phase != missing_phase],
                invalid, cohort, inventory, {(1, 1): 0}, required)

    invalid = capture.ProcessSlab((1,), schema, 1)
    without_sedimentation = [record for record in records() if record.phase not in (9, 10)]
    with pytest.raises(ValueError, match="lacks required sedimentation substep"):
        capture._store_process_frame(frame, without_sedimentation, invalid, cohort, inventory,
                                     {(1, 1): 0}, required)


def test_source_arithmetic_replay_reports_exact_f32_closure():
    import json
    import numpy as np

    schema = json.loads(capture.SCHEMA_PATH.read_text(encoding="utf-8"))
    slab = capture.ProcessSlab((1,), schema, 1)
    for phase in (5, 6, 7, 8, 11, 12):
        slab.phase_masks[phase][:] = True
        slab.phases[phase][:] = 0
    rate_indices = {capture._field_base(field): ix for ix, field in enumerate(schema["phases"]["5"]["fields"])}
    rate_values = {"praut": 0.5, "pracw": 0.25, "prevp": -0.5, "piacr": 0.125,
                   "pgacr": 0.0625, "psacr": 0.03125, "pmulrs": 0.015625, "pmulrg": 0.0078125,
                   "psdep": 0.5, "pgdep": 0.25, "pinud": 0.125, "pidep": 0.0625,
                   "paacw": 0.125, "pseml": 0.03125, "pgeml": 0.015625,
                   "psevp": 0.125, "pgevp": 0.0625}
    for name, value in rate_values.items():
        slab.phases[5][..., rate_indices[name]] = np.float32(value)
    slab.phases[6][..., 1] = np.float32(1.0)
    temperatures = np.where(np.arange(39) < 20, np.float32(260), np.float32(280))
    slab.phases[6][0, :, 0, 2] = temperatures
    slab.phases[6][..., 3] = np.float32(1.0)
    slab.phases[6][..., 6] = np.float32(0.005)
    slab.phases[6][..., 17] = np.float32(20.0)
    cold_work2 = np.float32(-0.4375)
    warm_work2 = np.float32(0.3125)
    work2 = np.where(temperatures <= np.float32(273.15), cold_work2, warm_work2)
    slab.phases[6][0, :, 0, 16] = work2
    slab.phases[7][..., 2] = np.float32(1000.0)
    slab.phases[7][..., 3] = np.float32(20.0)
    slab.phases[8][0, :, 0, 1] = np.add(np.float32(1.0), np.multiply(work2, np.float32(20.0), dtype=np.float32), dtype=np.float32)
    slab.phases[8][0, :, 0, 2] = temperatures
    cold_qr_rate = np.float32(0.0078125)
    warm_qr_rate = np.float32(0.453125)
    qr_rate = np.where(temperatures <= np.float32(273.15), cold_qr_rate, warm_qr_rate)
    slab.phases[8][0, :, 0, 6] = np.add(np.float32(0.005), np.multiply(qr_rate, np.float32(20.0), dtype=np.float32), dtype=np.float32)
    for phase in (11, 12):
        slab.phases[phase][0, :, 0, 1] = np.float32(1.0)
        slab.phases[phase][0, :, 0, 2] = temperatures
        slab.phases[phase][..., 12] = np.float32(1000.0)
        slab.phases[phase][..., 10] = np.float32(20.0)

    channels, diagnostics = capture.process_channels(slab, schema, 273.15)
    assert diagnostics["phase8_QV_source_formula_bitwise_matches"] == 39
    assert diagnostics["phase8_TK_source_formula_bitwise_matches"] == 39
    assert diagnostics["phase5_work2_replayed_bitwise_matches"] == 39
    assert diagnostics["QR_cold_warm_replayed_bitwise_matches"] == 39
    assert diagnostics["source_QR_replay_status"] == "BITWISE_MATCH"
    assert channels["source_work2_cold_warm_rate_bitwise_match"][0, 0, 0]
    assert channels["source_QR_cold_warm_bitwise_match"][0, 0, 0]
    assert channels["phase8_minus_phase6_QV"][0, 0, 0] < 0
    assert channels["source_work2_cold_warm_rate_residual"][0, 0, 0] == 0
    # Cold-branch QV work2 is negative while its separate QR source rate is positive.
    assert work2[0] < 0 < qr_rate[0]

    passing_surface = {"paired_observed_updates": 1,
                       "rain_formula_bitwise_matches": 1,
                       "rainncv_formula_bitwise_matches": 1}
    capture.require_known_source_formula_closure(diagnostics, passing_surface)
    slab.phases[8][0, 0, 0, 1] = np.nextafter(slab.phases[8][0, 0, 0, 1], np.float32(np.inf))
    _mutated_channels, mutated_diagnostics = capture.process_channels(slab, schema, 273.15)
    with pytest.raises(ValueError, match="phase8_QV_source_formula"):
        capture.require_known_source_formula_closure(mutated_diagnostics, passing_surface)


def test_surface_source_gate_rejects_mutated_phase14_rain():
    import json
    import numpy as np

    schema = json.loads(capture.SCHEMA_PATH.read_text(encoding="utf-8"))
    slab = capture.ProcessSlab((1,), schema, 1)
    slab.surface_masks[:] = True
    slab.surface_phases[:] = 0
    slab.surface_phases[0, 0, 0, 4] = np.float32(1)
    slab.surface_phases[0, 0, 0, 7:10] = np.float32(1)
    slab.surface_phases[1, 0, 0, 10:12] = np.float32(1000)
    _channels, surface_diag = capture.surface_process_channels(slab, schema)
    process_diag = {"phase8_QV_source_formula_bitwise_matches": 1, "phase8_QV_source_formula_cells": 1,
                    "phase8_TK_source_formula_bitwise_matches": 1, "phase8_TK_source_formula_cells": 1,
                    "phase12_QV_source_formula_bitwise_matches": 1, "phase12_QV_source_formula_cells": 1,
                    "phase12_TK_source_formula_bitwise_matches": 1, "phase12_TK_source_formula_cells": 1}
    empty_slab = capture.ProcessSlab((1,), schema, 1)
    _empty_channels, empty_surface_diag = capture.surface_process_channels(empty_slab, schema)
    assert empty_surface_diag["rain_formula_status"] == "NO_APPLICABLE_RECORDS"
    capture.require_known_source_formula_closure(process_diag, empty_surface_diag)
    capture.require_known_source_formula_closure(process_diag, surface_diag)
    slab.surface_phases[1, 0, 0, 10] = np.nextafter(slab.surface_phases[1, 0, 0, 10], np.float32(np.inf))
    _channels, mutated_surface_diag = capture.surface_process_channels(slab, schema)
    with pytest.raises(ValueError, match="surface rain source arithmetic"):
        capture.require_known_source_formula_closure(process_diag, mutated_surface_diag)


def test_channel_bank_publishes_separate_actual_time_blocks(tmp_path):
    import numpy as np

    process_steps = tuple(range(1, 361)) + tuple(range(721, 901))
    full_steps = tuple(range(1, 901))
    cohort = capture.Cohort([(1, 1)], ["corner-1"], ["RN1_1"], np.zeros((1, 4), dtype=np.int32),
                            np.full((1, 4), 0.25), {"RN1_1": ["role"]})
    bank = capture.ChannelBank(tmp_path / "scratch", process_steps, full_steps, 1)
    proc = np.arange(len(process_steps) * 39, dtype=np.float32).reshape(len(process_steps), 39, 1)
    surf = np.arange(len(full_steps), dtype=np.float32)[:, None]
    bank.put("phase08_test", "process", process_steps, proc, "unit")
    bank.put("surface_test", "full", full_steps, surf, "mm")
    identities = bank.publish(tmp_path / "out", cohort)
    assert len(identities) == 8
    process_first_hour = np.load(tmp_path / "out/phase08_test/lead_01/phase08_test.npz")
    process_last_hour = np.load(tmp_path / "out/phase08_test/lead_05/phase08_test.npz")
    assert process_first_hour["actual_timestep"][0] == 1
    assert process_last_hour["actual_timestep"][0] == 721
    assert process_last_hour["actual_timestep"][-1] == 900
    surface_gap_hour = np.load(tmp_path / "out/surface_test/lead_03/surface_test.npz")
    assert surface_gap_hour["actual_timestep"][0] == 361
    assert surface_gap_hour["actual_timestep"][-1] == 540


def test_phase5_units_follow_the_schema_field_groups():
    import json

    schema = json.loads(capture.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert capture.channel_units("phase05_praut", schema) == "kg kg-1 s-1"
    assert capture.channel_units("phase05_paacw", schema) == "kg kg-1 s-1"
    assert capture.channel_units("phase05_nraut", schema) == "m-3 s-1"
    assert capture.channel_units("phase05_delta2", schema) == "dimensionless"
    assert capture.channel_units("state_entry_NN", schema) == "kg-1 number mixing ratio"
    assert capture.channel_units("state_entry_NC", schema) == "kg-1 number mixing ratio"
    assert capture.channel_units("state_entry_BG", schema) == "m3 kg-1 (bg/brs volume mixing ratio)"
    assert capture.channel_units("phase01_nci_1", schema) == "m-3 internal number concentration"
    assert capture.channel_units("phase01_qci_2", schema) == "kg kg-1 mixing ratio"
    for phase, details in schema["phases"].items():
        names = [capture._field_base(field) for field in details["fields"]]
        assert len(names) == len(set(names)), f"phase {phase} output names collide"


def test_species_indices_survive_channel_export_without_payload_overwrite():
    import json
    import numpy as np

    schema = json.loads(capture.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert [capture._field_base(name) for name in schema["phases"]["1"]["fields"][4:9]] == [
        "qci_1", "qci_2", "qrs_1", "qrs_2", "qrs_3"
    ]
    assert [capture._field_base(name) for name in schema["phases"]["13"]["fields"][:4]] == [
        "fall_1", "fall_2", "fall_3", "fall_4"
    ]
    with pytest.raises(ValueError, match="duplicate output channel names"):
        capture._phase_channel_names(1, ["qrs(i,k,1)", "qrs(i,k,1)"])

    slab = capture.ProcessSlab((1,), schema, 1)
    for phase in slab.phases:
        slab.phase_masks[phase][:] = True
    slab.phases[1][..., 4:9] = np.asarray([0.11, 0.22, 0.33, 0.44, 0.55], dtype=np.float32)
    slab.phases[6][..., 1] = np.float32(1)
    slab.phases[6][..., 2] = np.float32(270)
    slab.phases[6][..., 3] = np.float32(1)
    slab.phases[6][..., 17] = np.float32(1)
    slab.phases[7][..., 2] = np.float32(1)
    channels, _ = capture.process_channels(slab, schema, 273.15)
    species_names = ["phase01_qci_1", "phase01_qci_2", "phase01_qrs_1",
                     "phase01_qrs_2", "phase01_qrs_3"]
    assert all(name in channels for name in species_names)
    np.testing.assert_array_equal(
        np.asarray([channels[name][0, 0, 0] for name in species_names]),
        np.asarray([0.11, 0.22, 0.33, 0.44, 0.55], dtype=np.float32),
    )
    assert len([name for name in channels if name.startswith("phase01_") and not name.endswith("_present")]) == len(
        schema["phases"]["1"]["fields"]
    )

    slab.surface_phases[0, ..., :4] = np.asarray([1, 2, 3, 4], dtype=np.float32)
    surface_channels, _ = capture.surface_process_channels(slab, schema)
    fall_names = [f"phase13_fall_{index}" for index in range(1, 5)]
    assert all(name in surface_channels for name in fall_names)
    assert [float(surface_channels[name][0, 0]) for name in fall_names] == [1, 2, 3, 4]
    assert len([name for name in surface_channels if name.startswith("phase13_") and not name.endswith("_present")]) == len(
        schema["phases"]["13"]["fields"]
    )


def test_output_path_guard_rejects_dangling_symlinks(tmp_path):
    target = tmp_path / "new-output"
    assert capture.fresh_output_path(target) == target.resolve()

    target.symlink_to(tmp_path / "missing-target")
    assert target.exists() is False and target.is_symlink()
    with pytest.raises(ValueError, match="must be fresh"):
        capture.fresh_output_path(target)


def test_entry_wrapper_binding_rejects_state_copy_mutation():
    import numpy as np

    wrapper = np.zeros((1, 39, 1, 16), dtype=np.float32)
    wrapper[..., 0] = 300.0
    wrapper[..., 1:7] = np.arange(1, 7, dtype=np.float32) * np.float32(0.001)
    wrapper[..., 7] = np.float32(0.007)
    wrapper[..., 8:12] = np.asarray([10, 20, 30, 40], dtype=np.float32)
    wrapper[..., 12] = np.float32(1.2)
    wrapper[..., 13] = np.float32(270.0)
    wrapper[..., 14] = np.float32(90000.0)
    wrapper[..., 15] = np.float32(0.9)
    internal = np.zeros_like(wrapper)
    for wrapper_ix, state_ix in ((14, 0), (1, 1), (13, 2), (12, 3), (2, 4),
                                 (4, 5), (3, 6), (5, 7), (6, 8), (11, 15)):
        internal[..., state_ix] = wrapper[..., wrapper_ix]
    for wrapper_ix, state_ix in ((8, 9), (9, 10), (7, 11), (10, 12)):
        internal[..., state_ix] = np.multiply(wrapper[..., wrapper_ix], wrapper[..., 12], dtype=np.float32)

    capture.validate_wrapper_binding(wrapper, {1: internal}, phase=1)
    wrapper[..., 3] = np.nextafter(wrapper[..., 3], np.float32(np.inf))
    with pytest.raises(ValueError, match="wrapper field 3 differs"):
        capture.validate_wrapper_binding(wrapper, {1: internal}, phase=1)

