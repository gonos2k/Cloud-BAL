"""Focused checks for native correction inner-product accounting."""
import sys
import json
import struct
from pathlib import Path

import numpy as np
import netCDF4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr98_native_effect import (pair_metrics, support_native_mask, native_face_triplet,
                                support_column_mask,
                                native_selected_sum_triplet, read_initial_fields,
                                validate_capture_run_binding, verify_c1_source_build_pin)
import pr98_native_effect as effect
import pr94_cloud_response as cloud


def test_pair_metrics_preserves_h_dot_b_and_net_norm_identity():
    h = np.array([1.0, -2.0, 0.5])
    b = np.array([-0.25, 0.75, 2.0])
    result = pair_metrics(h, h + b)
    assert result["dot_a_delta"] == np.dot(h, b)
    assert result["delta_l2"] == np.linalg.norm(b)
    assert np.isclose(result["b_l2"] ** 2,
                      result["a_l2"] ** 2 + 2 * result["dot_a_delta"] + result["delta_l2"] ** 2)


def test_pair_metrics_rejects_mismatched_or_nonfinite_arrays():
    try:
        pair_metrics(np.array([1.0]), np.array([1.0, 2.0]))
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched vectors must fail")
    try:
        pair_metrics(np.array([np.nan]), np.array([0.0]))
    except ValueError:
        pass
    else:
        raise AssertionError("nonfinite vectors must fail")


def test_verified_history_identity_does_not_depend_on_generated_file_order(tmp_path):
    root = tmp_path / "OFF"
    run = root / "run"
    run.mkdir(parents=True)
    history = run / "wrfout_d01_2026-08-16_13:00:00"
    history.write_bytes(b"history")
    broad = run / "BROADBAND_CLOUD_GODDARD.bin"
    broad.write_bytes(b"other generated output")
    receipt = {"arm": "OFF", "status": "COMPLETE", "returncode": 0,
               "final_completed_step": 30,
               "generated_files": [
                   {"path": broad.name, "sha256": cloud.sha256(broad)},
                   {"path": history.name, "sha256": cloud.sha256(history)}]}
    (root / "receipt.json").write_text(json.dumps(receipt))
    path, _, identity = cloud.verify_run("OFF", root)
    assert path == history
    assert identity["sha256"] == cloud.sha256(history)
    assert identity["sha256"] != receipt["generated_files"][0]["sha256"]


def test_source_support_maps_to_native_face_union_without_duplicates():
    meta = {"fortran_bounds": [-4, 240, 1, 40, -4, 288,
                               1, 235, 1, 40, 1, 283]}
    support = np.zeros((39, 280, 232), dtype=bool)
    support[0, 0, 0] = True
    support[0, 0, 1] = True
    shape = (245, 40, 293)
    u = support_native_mask(meta, shape, support, "i")
    v = support_native_mask(meta, shape, support, "j")
    w = support_native_mask(meta, shape, support, "k")
    assert u.sum() == 3
    assert v.sum() == 4
    assert w.sum() == 4
    # History support [k=0,j=0,i=0] maps to native mass cell (i=2,j=2,k=1),
    # hence allocated-array index (i=6,j=6,k=0) for these capture bounds.
    assert u[6, 0, 6] and u[7, 0, 6] and u[8, 0, 6]
    assert v[6, 0, 6] and v[6, 0, 7] and v[7, 0, 6] and v[7, 0, 7]
    assert w[6, 0, 6] and w[6, 1, 6] and w[7, 0, 6] and w[7, 1, 6]


def test_composition_target_maps_to_actual_native_capture_cell():
    meta3 = {"fortran_bounds": [-4,240,1,40,-4,288,1,235,1,40,1,283]}
    support = np.zeros((39,280,232),dtype=bool)
    # Pinned QC composition target_i0=133,target_j0=15 indexes raw input;
    # history support is cropped by one mass cell on its west/south edges.
    support[0,14,132] = True
    u = support_native_mask(meta3,(245,40,293),support,"i")
    v = support_native_mask(meta3,(245,40,293),support,"j")
    assert u[138,0,20] and u[139,0,20]
    assert v[138,0,20] and v[138,0,21]
    meta2 = {"fortran_bounds": [-4,240,-4,288,1,235,1,283]}
    columns = support.any(axis=0)
    mu = support_column_mask(meta2,(245,293),columns)
    assert mu[138,20]


def test_native_triplet_transposes_face_mask_with_fortran_array(tmp_path):
    roots = {}
    support = np.zeros((2, 2, 2), dtype=bool)
    support[0, 0, 0] = True
    bounds = (0, 3, 1, 2, 0, 3, 1, 2, 1, 2, 1, 2)
    for arm, offset in (("OFF", 0), ("HYDRO", 2), ("COUPLED", 5)):
        root = tmp_path / arm
        root.mkdir()
        for suffix, value in (("in", offset), ("out", offset + 1)):
            array = np.full((4, 2, 4), value, dtype=">f4")
            name = root / f"pr98_x_{suffix}_1_2_1_2_.bin"
            name.write_bytes(struct.pack(">12i", *bounds) + array.tobytes(order="F"))
        roots[arm] = root
    result = native_face_triplet(roots, "pr98_x", "i", support,
                                 add_out_minus_in="delta")
    assert result["support_values"] == 2
    assert result["absolute_by_arm"]["OFF"]["l2"] == np.sqrt(2)
    assert result["increments"]["h_H_minus_O"]["l2"] == 0
    assert result["increments"]["b_C_minus_H"]["l2"] == 0


def test_native_triplet_promotes_before_subtracting_float32_snapshots(tmp_path):
    roots = {}
    support = np.zeros((1, 1, 2), dtype=bool)
    support[0, 0, :] = True
    bounds = (0, 4, 1, 1, 0, 2, 1, 3, 1, 1, 1, 2)
    for arm, before, after in (("OFF",0,0), ("HYDRO",1,2**25), ("COUPLED",0,2**25)):
        root = tmp_path / arm
        root.mkdir()
        for suffix, value in (("in",before),("out",after)):
            array = np.full((5,1,3), value, dtype=">f4")
            (root / f"pr98_x_{suffix}_1_2_1_1_.bin").write_bytes(
                struct.pack(">12i", *bounds) + array.tobytes(order="F"))
        roots[arm] = root
    result = native_face_triplet(roots,"pr98_x","i",support,add_out_minus_in="delta")
    assert np.isclose(result["absolute_by_arm"]["HYDRO"]["l2"],np.sqrt(3)*(2**25-1))
    assert np.isclose(result["increments"]["h_H_minus_O"]["l2"],np.sqrt(3)*(2**25-1))
    assert np.isclose(result["increments"]["b_C_minus_H"]["l2"],np.sqrt(3))


def test_selected_native_sum_promotes_each_component_before_reduction(tmp_path):
    roots = {}
    support = np.ones((1, 1, 1), dtype=bool)
    bounds = (0, 3, 1, 1, 0, 2, 1, 2, 1, 1, 1, 2)
    values = {"OFF": ((0,0),(0,0)),
              "HYDRO": ((0,0),(2**24,0)),
              "COUPLED": ((0,0),(2**24,1))}
    for arm, (a_pair,b_pair) in values.items():
        root = tmp_path / arm
        root.mkdir()
        for prefix, (before,after) in (("pg",a_pair),("cor",b_pair)):
            for suffix, value in (("in",before),("out",after)):
                array = np.full((4,1,3),value,dtype=">f4")
                (root / f"{prefix}_{suffix}_1_1_1_1_.bin").write_bytes(
                    struct.pack(">12i",*bounds)+array.tobytes(order="F"))
        roots[arm] = root
    result = native_selected_sum_triplet(roots,("pg","cor"),"i",support)
    assert np.isclose(result["increments"]["b_C_minus_H"]["l2"],np.sqrt(2))


def test_initial_wind_stats_reject_declared_finite_fill_values(tmp_path, monkeypatch):
    path = tmp_path / "input.nc"
    fill = np.float32(-9999)
    with netCDF4.Dataset(path,"w") as ds:
        ds.createDimension("Time",1)
        ds.createDimension("j",1)
        ds.createDimension("i",2)
        for name in ("U","V"):
            var = ds.createVariable(name,"f4",("Time","j","i"),fill_value=fill)
            var[:] = np.array([[[1,fill]]],dtype=np.float32)
    monkeypatch.setattr(effect,"INITIAL_FIELDS",("U","V"))
    try:
        read_initial_fields(path)
    except ValueError as exc:
        assert "sentinel" in str(exc)
    else:
        raise AssertionError("declared finite fill values must be rejected before native statistics")


def test_capture_receipt_binding_rejects_wrong_executable_step_and_mutated_input(tmp_path):
    source_receipt = tmp_path / "source.json"
    source_receipt.write_text("pinned source")
    build_receipt = tmp_path / "build.json"
    build_receipt.write_text("pinned build")
    source_hash, build_hash = cloud.sha256(source_receipt), cloud.sha256(build_receipt)
    baseline = {"candidate_wrfinput_sha256":"input", "candidate_wrfbdy_sha256":"bdy",
                "candidate_namelist_sha256":"namelist"}
    preflight = {"source_receipt":str(source_receipt), "source_receipt_sha256":source_hash}
    receipt = {"status":"COMPLETE", "returncode":0, "timestep_count":1,
               "final_completed_step":1, "expected_model_timestamps":["2026-08-16_13:00:20"],
               "model_timestamps":[{"timestamp":"2026-08-16_13:00:20"}],
               "executed_executable_sha256":"exe", "expected_executed_executable_sha256":"exe",
               "candidate_build_unchanged":True, "candidate_input_unchanged":True,
               "changed_staged_inputs":[], "changed_original_inputs":[],
               "source_receipt_sha256":source_hash,
               **baseline, "candidate_build":{"receipt_path":str(build_receipt),
                    "receipt_sha256":build_hash, "executable_sha256":"exe", "profile_sha256":"profile"}}
    assert validate_capture_run_binding("OFF",receipt,preflight,baseline,"exe","profile")["candidate_build_receipt_sha256"] == build_hash
    for field, bad in (("executed_executable_sha256","wrong"),("timestep_count",2),
                       ("candidate_input_unchanged",False),
                       ("changed_staged_inputs",None),
                       ("changed_original_inputs",None),
                       ("source_receipt_unchanged",False)):
        changed = dict(receipt)
        changed[field] = bad
        try:
            validate_capture_run_binding("OFF",changed,preflight,baseline,"exe","profile")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid capture receipt field {field} must fail")


def test_c1_source_build_pin_is_checked(tmp_path):
    source = tmp_path / "c1_build.json"
    source.write_text("C1 build receipt")
    digest = cloud.sha256(source)
    assert verify_c1_source_build_pin(source,digest) == digest
    try:
        verify_c1_source_build_pin(source,"0"*64)
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched frozen source receipt pin must fail")
