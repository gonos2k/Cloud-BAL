#!/usr/bin/env python3
"""Measure native C1 initial-wind corrections and their saved early responses."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import netCDF4

ROOT = Path(__file__).resolve().parents[1]
RUNS = {arm: Path(f"/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/runs_on_lustre/{arm}_600s_c1")
        for arm in ("OFF", "HYDRO", "COUPLED")}
CAPTURE_RUNS = {arm: Path(f"/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr98_native_effect_20261022/native_capture_runs/{arm}_20s/run")
                for arm in ("OFF", "HYDRO", "COUPLED")}
CAPTURE_EVIDENCE = ROOT / "docs/evidence/pr98_native_capture_20261022"
EXPECTED_C1_BUILD_RECEIPT = Path("/var/tmp/pr96_native_build_c1_20261021/pr87_native_overlay_build.json")
EXPECTED_C1_BUILD_RECEIPT_SHA256 = "ac7b1cbefc2cbbf128b7bbe08573d79b575b3b50d51db3a955f1bb0d6d02ae56"
ADVANCE_MU_SOURCE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/dyn_em/module_small_step_em.F")
ADVANCE_MU_SOURCE_SHA256 = "cabf1a177d50fb0096db79644af20cfe6d75217dbe63ab406a7e29bb54c17634"
# The PR98 support is cropped from raw WRF mass indices [2..233, 2..281]
# before it reaches this module. Capture arrays use full native Fortran indices.
SUPPORT_ORIGIN_IJK = (2, 1, 2)
COMPOSITION = ROOT / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
EXECUTABLE_SHA256 = "a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d"
INITIAL_FIELDS = ("T", "QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP",
                  "QNCLOUD", "QNICE", "QNRAIN", "QNCCN", "QIB", "P", "PB", "PH", "PHB",
                  "U", "V", "W", "MU", "MUB")
sys.path.insert(0, str(ROOT / "tools"))
import pr94_cloud_response as cloud  # noqa: E402
from pr86_compare_response import load_history  # noqa: E402
from pr94_hydro_response import validate_receipt_triplet  # noqa: E402
from pr98_native_capture import read_capture, summarize  # noqa: E402
from pr87_native_history import _finite  # noqa: E402


def pair_metrics(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """Describe b-a and the actual vector inner products on the supplied support."""
    av, bv = np.asarray(a, dtype=np.float64).ravel(), np.asarray(b, dtype=np.float64).ravel()
    if av.shape != bv.shape or not np.isfinite(av).all() or not np.isfinite(bv).all():
        raise ValueError("paired native arrays must be finite and have identical shape")
    d = bv - av
    return {"a_l2": float(np.linalg.norm(av)), "b_l2": float(np.linalg.norm(bv)),
            "dot_a_b": float(np.dot(av, bv)), "dot_a_delta": float(np.dot(av, d)),
            "dot_b_delta": float(np.dot(bv, d)), "delta_l2": float(np.linalg.norm(d)),
            "delta_rms": float(np.sqrt(np.mean(d*d))), "delta_max_abs": float(np.max(np.abs(d))),
            "delta_sum": float(np.sum(d, dtype=np.float64)), "n": int(d.size)}


def read_initial_fields(path: Path) -> dict[str, dict[str, Any]]:
    """Read finite initial fields with native shape, dtype, units, and staggering."""
    result = {}
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_mask(False)
        for name in INITIAL_FIELDS:
            if name not in ds.variables:
                raise ValueError(f"required initial field {name} is absent from {path}")
            var = ds.variables[name]
            values = np.asarray(var[0])
            if not np.isfinite(values).all():
                raise ValueError(f"initial field {name} has nonfinite values")
            finite_values = np.asarray(_finite(ds, name, 0))
            result[name] = {"values": values, "finite_values": finite_values,
                            "metadata": {"shape": list(values.shape), "dtype": values.dtype.str,
                                         "units": getattr(var, "units", None),
                                         "stagger": getattr(var, "stagger", "")}}
        absent = [name for name in ("QNGRAUPEL", "QNGRAUP") if name not in ds.variables]
        result["_number_moment_variables"] = sorted(name for name in ds.variables if name.startswith("QN"))
        result["_absent_candidate_names"] = absent
    return result


def compare_initial_states(roots: dict[str, Path], receipts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    loaded = {}
    for arm, root in roots.items():
        path = root / "run/wrfinput_d01"
        digest = cloud.sha256(path)
        if digest != receipts[arm].get("candidate_wrfinput_sha256"):
            raise ValueError(f"{arm} wrfinput does not match its closed receipt")
        loaded[arm] = read_initial_fields(path)
    comparisons, metadata = {}, {}
    pairs = {"HYDRO_minus_OFF": ("OFF", "HYDRO"),
             "COUPLED_minus_HYDRO": ("HYDRO", "COUPLED"),
             "COUPLED_minus_OFF": ("OFF", "COUPLED")}
    for name in INITIAL_FIELDS:
        base = loaded["OFF"][name]
        if any(loaded[arm][name]["metadata"] != base["metadata"] for arm in roots):
            raise ValueError(f"initial field {name} metadata differs across arms")
        metadata[name] = base["metadata"]
        comparisons[name] = {}
        for pair, (left, right) in pairs.items():
            a = loaded[left][name]["finite_values"]
            b = loaded[right][name]["finite_values"]
            if a.shape != b.shape or a.dtype != b.dtype:
                raise ValueError(f"initial field {name} shape/dtype differs in {arm}")
            delta = b.astype(np.float64) - a.astype(np.float64)
            maxloc = np.unravel_index(int(np.argmax(np.abs(delta))), delta.shape)
            comparisons[name][pair] = {
                "bitwise_equal": bool(np.array_equal(a, b)),
                "mismatch_count": int(np.count_nonzero(a != b)),
                "max_abs": float(np.max(np.abs(delta))),
                "signed_at_max": float(delta[maxloc]),
                "index_native": [int(x) for x in maxloc]}
    first = loaded["OFF"]["_absent_candidate_names"]
    if any(loaded[arm]["_absent_candidate_names"] != first for arm in roots):
        raise ValueError("candidate number-graupel aliases differ across arms")
    return {"fields": comparisons, "metadata": metadata,
            "absent_candidate_names_on_all_arms": first,
            "number_moment_variables_on_all_arms": loaded["OFF"]["_number_moment_variables"],
            "scope": "Selected-field detail for native U/V maxima and array metadata. Complete HYDRO/COUPLED identity of all stored wrfinput variables is reported in the separate all-variable audit."}


def _attribute_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def compare_all_initial_variables(roots: dict[str, Path],
                                  receipts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Check every stored HYDRO/COUPLED wrfinput variable and global attribute."""
    left_path = roots["HYDRO"] / "run/wrfinput_d01"
    right_path = roots["COUPLED"] / "run/wrfinput_d01"
    for arm, path in (("HYDRO", left_path), ("COUPLED", right_path)):
        if cloud.sha256(path) != receipts[arm].get("candidate_wrfinput_sha256"):
            raise ValueError(f"{arm} wrfinput does not match its closed receipt")
    variables = {}
    with netCDF4.Dataset(left_path) as h, netCDF4.Dataset(right_path) as c:
        h.set_auto_mask(False); c.set_auto_mask(False)
        hnames, cnames = set(h.variables), set(c.variables)
        missing_h, missing_c = sorted(cnames-hnames), sorted(hnames-cnames)
        for name in sorted(hnames & cnames):
            hv, cv = h.variables[name], c.variables[name]
            hattrs = {a: _attribute_value(hv.getncattr(a)) for a in hv.ncattrs()}
            cattrs = {a: _attribute_value(cv.getncattr(a)) for a in cv.ncattrs()}
            hmeta = {"dimensions": list(hv.dimensions), "shape": list(hv.shape),
                     "dtype": hv.dtype.str, "units": hattrs.get("units"),
                     "stagger": hattrs.get("stagger")}
            cmeta = {"dimensions": list(cv.dimensions), "shape": list(cv.shape),
                     "dtype": cv.dtype.str, "units": cattrs.get("units"),
                     "stagger": cattrs.get("stagger")}
            metadata_equal = hmeta == cmeta
            attrs_equal = hattrs == cattrs
            if not metadata_equal:
                variables[name] = {"metadata_equal": False, "HYDRO": hmeta, "COUPLED": cmeta,
                                   "attributes_equal": attrs_equal,
                                   "different_attribute_names": sorted(set(hattrs) | set(cattrs)),
                                   "data_bitwise_equal": False, "different_bytes": None}
                continue
            a, b = np.asarray(hv[:]), np.asarray(cv[:])
            if a.shape != b.shape or a.dtype != b.dtype:
                variables[name] = {"metadata_equal": True, "data_bitwise_equal": False,
                                   "different_bytes": None, "different_elements": None}
                continue
            if a.dtype.kind in "biufcV":
                byte_diff = int(np.count_nonzero(a.view(np.uint8).ravel() != b.view(np.uint8).ravel()))
                equal = byte_diff == 0
                element_diff = int(np.count_nonzero(a != b)) if a.dtype.kind != "V" else None
            else:
                equal = bool(np.array_equal(a, b))
                element_diff = int(np.count_nonzero(a != b))
                byte_diff = None
            variables[name] = {"metadata_equal": True, "attributes_equal": attrs_equal,
                               "different_attribute_names": sorted(a for a in set(hattrs) | set(cattrs)
                                                                    if hattrs.get(a) != cattrs.get(a)),
                               "data_bitwise_equal": equal,
                               "different_bytes": byte_diff, "different_elements": element_diff,
                               "metadata": hmeta}
        hglobals = {a: _attribute_value(h.getncattr(a)) for a in h.ncattrs()}
        cglobals = {a: _attribute_value(c.getncattr(a)) for a in c.ncattrs()}
    differences = [name for name,row in variables.items()
                   if row.get("metadata_equal") is not True or row.get("attributes_equal") is not True or
                   row.get("data_bitwise_equal") is not True]
    return {"HYDRO_path": str(left_path), "COUPLED_path": str(right_path),
            "HYDRO_sha256": receipts["HYDRO"]["candidate_wrfinput_sha256"],
            "COUPLED_sha256": receipts["COUPLED"]["candidate_wrfinput_sha256"],
            "variable_names_equal": not missing_h and not missing_c,
            "missing_from_HYDRO": missing_h, "missing_from_COUPLED": missing_c,
            "global_attributes_equal": hglobals == cglobals,
            "global_attribute_differences": {"HYDRO": hglobals, "COUPLED": cglobals} if hglobals != cglobals else {},
            "variable_count": len(variables), "differing_variables": differences,
            "variables": variables,
            "all_except_UV_exact": not [n for n in differences if n not in {"U", "V"}],
            "all_stored_variables_bitwise_equal": not differences and not missing_h and not missing_c}


def support_native_mask(meta: dict[str, Any], shape_ikj: tuple[int, int, int],
                        support_kji: np.ndarray, face_axis: str) -> np.ndarray:
    """Map mass support to the boolean union of adjacent native staggered faces."""
    if support_kji.ndim != 3 or face_axis not in {"i", "j", "k"}:
        raise ValueError("expected a KJI support and native i/j/k face axis")
    encoded = meta["fortran_bounds"]
    if len(encoded) != 12:
        raise ValueError("expected allocated and active bounds in rank-3 capture header")
    ims, ime, kms, kme, jms, jme = encoded[:6]
    its, ite, kts, kte, jts, jte = encoded[6:]
    if shape_ikj != (ime - ims + 1, kme - kms + 1, jme - jms + 1):
        raise ValueError("capture array shape disagrees with its allocated Fortran bounds")
    out = np.zeros(shape_ikj, dtype=bool)
    origin_i, origin_k, origin_j = SUPPORT_ORIGIN_IJK
    for k0, j0, i0 in np.argwhere(support_kji):
        native_i = origin_i + int(i0)
        native_k = origin_k + int(k0)
        native_j = origin_j + int(j0)
        i, k, j = native_i - ims, native_k - kms, native_j - jms
        if not (its <= native_i <= ite and kts <= native_k <= kte and
                jts <= native_j <= jte):
            raise ValueError("source support falls outside captured active tile")
        points = {"i": ((i,k,j),(i+1,k,j)),
                  "j": ((i,k,j),(i,k,j+1)),
                  "k": ((i,k,j),(i,k+1,j))}[face_axis]
        for point in points:
            pi, pk, pj = point
            if not (0 <= pi < shape_ikj[0] and 0 <= pk < shape_ikj[1] and 0 <= pj < shape_ikj[2]):
                raise ValueError(f"native {face_axis} face is outside captured allocation")
            out[point] = True
    return out


def support_column_mask(meta: dict[str, Any], shape_ij: tuple[int,int],
                        support_columns_ji: np.ndarray) -> np.ndarray:
    """Project source levels to unique columns and map them to native MU cells."""
    bounds = meta["fortran_bounds"]
    if len(bounds) != 8:
        raise ValueError("expected allocated and active bounds in rank-2 capture header")
    ims, ime, jms, jme, its, ite, jts, jte = bounds
    if shape_ij != (ime-ims+1, jme-jms+1):
        raise ValueError("MU capture shape disagrees with allocated Fortran bounds")
    if support_columns_ji.ndim != 2:
        raise ValueError("expected a JI column support")
    out = np.zeros(shape_ij, dtype=bool)
    origin_i, _, origin_j = SUPPORT_ORIGIN_IJK
    for j0,i0 in np.argwhere(support_columns_ji):
        native_i=origin_i+int(i0); native_j=origin_j+int(j0)
        i=native_i-ims; j=native_j-jms
        if not (its <= native_i <= ite and jts <= native_j <= jte):
            raise ValueError("source columns fall outside captured active tile")
        if not (0 <= i < shape_ij[0] and 0 <= j < shape_ij[1]):
            raise ValueError("source MU column falls outside capture allocation")
        out[i,j] = True
    return out


def native_capture_file(run_root: Path, prefix: str, rank: int) -> tuple[dict[str,Any], np.ndarray]:
    matches = sorted(run_root.glob(prefix + "*.bin"))
    if len(matches) != 1:
        raise ValueError(f"expected one {prefix} snapshot in {run_root}, found {len(matches)}")
    return read_capture(matches[0], rank)


def native_face_triplet(roots: dict[str,Path], prefix: str, axis: str,
                        support: np.ndarray, *, add_out_minus_in: str | None = None) -> dict[str,Any]:
    """Analyze a matched source-native U/V/W face array triplet on one fixed mask."""
    payloads = {} if add_out_minus_in else {
        arm: native_capture_file(root,prefix,3) for arm,root in roots.items()}
    arrays, masks, metas = {}, {}, {}
    for arm in roots:
        if add_out_minus_in:
            before_meta,before_array = native_capture_file(roots[arm],prefix+"_in",3)
            meta,arr = native_capture_file(roots[arm],prefix+"_out",3)
            if before_meta["fortran_bounds"] != meta["fortran_bounds"]:
                raise ValueError(f"{prefix} before/after bounds differ in {arm}")
            payloads[arm] = (meta,arr)
            arrays[arm] = (arr.transpose(1,2,0).astype(np.float64) -
                           before_array.transpose(1,2,0).astype(np.float64))
        else:
            meta,arr = payloads[arm]
            arrays[arm] = arr.transpose(1,2,0)  # the source support uses KJI
        metas[arm] = meta
        masks[arm] = support_native_mask(meta,arr.shape,support,axis).transpose(1,2,0)
    if any(metas[arm]["fortran_bounds"] != metas["OFF"]["fortran_bounds"] for arm in roots):
        raise ValueError(f"{prefix} Fortran bounds differ across arms")
    mask = masks["OFF"]
    if any(not np.array_equal(mask,masks[arm]) for arm in roots):
        raise ValueError(f"{prefix} support differs across arms")
    if add_out_minus_in:
        label=add_out_minus_in
    else:
        label=prefix
    result=increment_metrics(arrays["OFF"],arrays["HYDRO"],arrays["COUPLED"],mask)
    result["array_bounds_fortran"] = metas["OFF"]["fortran_bounds"]
    result["source_array_axes"] = metas["OFF"]["axes"]
    result["source_field"] = label
    result["array_sha256"] = {arm: metas[arm]["sha256"] for arm in roots}
    return result


def native_column_triplet(roots: dict[str,Path], prefix: str,
                          support_columns_ji: np.ndarray) -> dict[str,Any]:
    """Analyze one rank-2 source mass array over unique fixed-support columns."""
    payloads = {arm: native_capture_file(root,prefix,2) for arm,root in roots.items()}
    arrays, masks = {}, {}
    for arm,(meta,arr) in payloads.items():
        arrays[arm] = arr
        masks[arm] = support_column_mask(meta,arr.shape,support_columns_ji)
    if any(payloads[arm][0]["fortran_bounds"] != payloads["OFF"][0]["fortran_bounds"]
           for arm in roots):
        raise ValueError(f"{prefix} Fortran bounds differ across arms")
    if any(not np.array_equal(masks["OFF"],masks[arm]) for arm in roots):
        raise ValueError(f"{prefix} support differs across arms")
    result = increment_metrics(arrays["OFF"],arrays["HYDRO"],arrays["COUPLED"],masks["OFF"])
    result["array_bounds_fortran"] = payloads["OFF"][0]["fortran_bounds"]
    result["array_sha256"] = {arm: payloads[arm][0]["sha256"] for arm in roots}
    result["source_field"] = prefix
    return result


def native_selected_sum_triplet(roots: dict[str,Path], prefixes: tuple[str,...], axis: str,
                               support: np.ndarray) -> dict[str,Any]:
    """Sum compatible captured source deltas before taking paired norms."""
    source_arrays = {}
    reference_bounds = None
    mask = None
    per_component_hashes = {}
    for prefix in prefixes:
        values, hashes, metas = {}, {}, {}
        for arm,root in roots.items():
            before_meta,before = native_capture_file(root,f"{prefix}_in",3)
            after_meta,after = native_capture_file(root,f"{prefix}_out",3)
            if before_meta["fortran_bounds"] != after_meta["fortran_bounds"]:
                raise ValueError(f"{prefix} before/after bounds differ in {arm}")
            metas[arm] = after_meta
            values[arm] = (after.transpose(1,2,0).astype(np.float64) -
                           before.transpose(1,2,0).astype(np.float64))
            hashes[arm] = {"in":before_meta["sha256"],"out":after_meta["sha256"]}
        if any(metas[a]["fortran_bounds"] != metas["OFF"]["fortran_bounds"] for a in roots):
            raise ValueError(f"{prefix} bounds differ across arms")
        candidate_mask = support_native_mask(metas["OFF"],
                                             native_capture_file(roots["OFF"],f"{prefix}_out",3)[1].shape,
                                             support,axis).transpose(1,2,0)
        if mask is not None and not np.array_equal(mask,candidate_mask):
            raise ValueError("selected source terms do not share one native face mask")
        mask = candidate_mask
        if reference_bounds is None:
            reference_bounds = metas["OFF"]["fortran_bounds"]
        elif metas["OFF"]["fortran_bounds"] != reference_bounds:
            raise ValueError("selected source terms do not share native array bounds")
        source_arrays[prefix] = values
        per_component_hashes[prefix] = hashes
    summed = {arm:sum((source_arrays[p][arm] for p in prefixes),
                      start=np.zeros(source_arrays[prefixes[0]][arm].shape, dtype=np.float64))
              for arm in roots}
    result = increment_metrics(summed["OFF"],summed["HYDRO"],summed["COUPLED"],mask)
    result.update({"source_terms":list(prefixes),"array_bounds_fortran":reference_bounds,
                   "component_input_output_sha256":per_component_hashes,
                   "interpretation":"Raw compatible RU/RV source-array deltas are summed componentwise before norms; this is a selected partial RHS, not a complete force balance."})
    return result


def native_mu_update_triplet(roots: dict[str,Path], support_columns_ji: np.ndarray) -> dict[str,Any]:
    """Measure the captured native MU update divided by its captured RK step."""
    updates, masks, dts, hashes = {}, {}, {}, {}
    for arm,root in roots.items():
        in_meta,mu_in = native_capture_file(root,"pr98_mu_small_in_",2)
        out_meta,mu_out = native_capture_file(root,"pr98_mu_small_out_",2)
        dt_meta,dt_value = native_capture_file(root,"pr98_dts_small",0)
        if in_meta["fortran_bounds"] != out_meta["fortran_bounds"]:
            raise ValueError(f"MU before/after bounds differ in {arm}")
        if dt_value.ndim != 0 or not np.isfinite(dt_value).all() or float(dt_value) <= 0:
            raise ValueError(f"invalid native RK time step in {arm}")
        mask = support_column_mask(in_meta,mu_in.shape,support_columns_ji)
        if (out_meta["fortran_bounds"] != in_meta["fortran_bounds"] or
                not np.array_equal(support_column_mask(out_meta,mu_out.shape,support_columns_ji),mask)):
            raise ValueError(f"MU support shape differs in {arm}")
        updates[arm] = (mu_out.astype(np.float64)-mu_in.astype(np.float64))/float(dt_value)
        masks[arm] = mask
        dts[arm] = float(dt_value)
        hashes[arm] = {"mu_in":in_meta["sha256"],"mu_out":out_meta["sha256"],"dts":dt_meta["sha256"]}
    if any(dts[a] != dts["OFF"] for a in roots):
        raise ValueError("native RK step sizes differ across arms")
    if any(not np.array_equal(masks["OFF"],masks[a]) for a in roots):
        raise ValueError("native MU support differs across arms")
    result = increment_metrics(updates["OFF"],updates["HYDRO"],updates["COUPLED"],masks["OFF"])
    return {"step_seconds":dts["OFF"],"source_field":"(MU_after-MU_before)/dts_small",
            "array_sha256":hashes,**result}


def compare_mu_update_to_mudf(roots: dict[str,Path], support_columns_ji: np.ndarray) -> dict[str,Any]:
    """Check the saved MU increment rate against native combined MUDF output."""
    rows = {}
    for arm,root in roots.items():
        in_meta,mu_in = native_capture_file(root,"pr98_mu_small_in_",2)
        out_meta,mu_out = native_capture_file(root,"pr98_mu_small_out_",2)
        _,dts = native_capture_file(root,"pr98_dts_small",0)
        mudf_meta,mudf = native_capture_file(root,"pr98_mudf_small_out_",2)
        if not (in_meta["fortran_bounds"] == out_meta["fortran_bounds"] == mudf_meta["fortran_bounds"]):
            raise ValueError(f"MU/MUDF capture bounds differ in {arm}")
        mask = support_column_mask(in_meta,mu_in.shape,support_columns_ji)
        update = (mu_out.astype(np.float64)-mu_in.astype(np.float64))/float(dts)
        delta = update[mask]-mudf.astype(np.float64)[mask]
        if not np.isfinite(delta).all():
            raise ValueError(f"nonfinite MU update comparison in {arm}")
        rows[arm] = {"n":int(delta.size),"l2":float(np.linalg.norm(delta)),
                     "rms":float(np.sqrt(np.mean(delta*delta))),
                     "max_abs":float(np.max(np.abs(delta))),
                     "bitwise_equal_after_float64_rate":bool(np.array_equal(update[mask],mudf.astype(np.float64)[mask]))}
    return {"comparison":"(MU_after-MU_before)/dts_small minus native MUDF output",
            "arms":rows,
            "interpretation":"MUDF is the captured combined DMDT+MU_TEND source output. Agreement checks the saved update against that combined output; it does not isolate or close the dry-mass flux divergence."}


def validate_capture_run_binding(arm: str, receipt: dict[str,Any], preflight: dict[str,Any],
                                 baseline_receipt: dict[str,Any],
                                 expected_executable: str, expected_profile: str) -> dict[str,str]:
    """Reject incomplete, changed, or provenance-crossed native capture receipts."""
    if receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0:
        raise ValueError(f"{arm} native capture run did not complete successfully")
    if receipt.get("timestep_count") != 1 or receipt.get("final_completed_step") != 1 or \
            receipt.get("expected_model_timestamps") != ["2026-08-16_13:00:20"] or \
            receipt.get("model_timestamps", [{}])[0].get("timestamp") != "2026-08-16_13:00:20":
        raise ValueError(f"{arm} native capture does not bind the expected first 20-second step")
    if receipt.get("executed_executable_sha256") != expected_executable or \
            receipt.get("expected_executed_executable_sha256") != expected_executable:
        raise ValueError(f"{arm} native executable differs from the pinned observer build")
    if receipt.get("candidate_build_unchanged") is not True or \
            receipt.get("candidate_input_unchanged") is not True or \
            receipt.get("changed_staged_inputs") != [] or receipt.get("changed_original_inputs") != [] or \
            ("source_receipt_unchanged" in receipt and receipt["source_receipt_unchanged"] is not True):
        raise ValueError(f"{arm} staged build or inputs changed during the native capture")
    source_receipt_path = Path(preflight.get("source_receipt", ""))
    if not source_receipt_path.is_file() or \
            cloud.sha256(source_receipt_path) != preflight.get("source_receipt_sha256") or \
            receipt.get("source_receipt_sha256") != preflight.get("source_receipt_sha256"):
        raise ValueError(f"{arm} capture source receipt does not match its preflight pin")
    for key in ("candidate_wrfinput_sha256","candidate_wrfbdy_sha256"):
        if receipt.get(key) != baseline_receipt.get(key):
            raise ValueError(f"{arm} candidate {key} differs from its frozen C1 baseline")
    candidate_build = receipt.get("candidate_build", {})
    candidate_build_receipt = Path(candidate_build.get("receipt_path", ""))
    if not candidate_build_receipt.is_file() or \
            cloud.sha256(candidate_build_receipt) != candidate_build.get("receipt_sha256") or \
            candidate_build.get("executable_sha256") != expected_executable or \
            candidate_build.get("profile_sha256") != expected_profile:
        raise ValueError(f"{arm} run's capture-build binding differs from public provenance")
    return {"source_receipt_path":str(source_receipt_path),
        "source_receipt_hash_binding":"preflight hash equals closed receipt hash and current source-file hash",
            "candidate_build_receipt_path":str(candidate_build_receipt),
            "candidate_build_receipt_sha256":candidate_build["receipt_sha256"]}


def verify_c1_source_build_pin(path: Path, expected_sha256: str) -> str:
    """Verify the C1 source-build receipt against its frozen SHA pin."""
    actual = cloud.sha256(path)
    if actual != expected_sha256:
        raise ValueError("pinned C1 source build receipt changed")
    return actual


def analyze_native_capture(roots: dict[str,Path], support_kji: np.ndarray) -> dict[str,Any]:
    """Summarize direct native momentum and dry-mass snapshots on fixed support."""
    if set(roots) != {"OFF","HYDRO","COUPLED"}:
        raise ValueError("expected OFF, HYDRO, and COUPLED native capture roots")
    support_columns_ji = support_kji.any(axis=0)
    dynamic_mass_geometry = {}
    for name in ("mu","mut","muu","muv"):
        payloads = {arm:native_capture_file(root,f"pr98_geom_{name}_",2)
                    for arm,root in roots.items()}
        arrays = {arm:payloads[arm][1] for arm in roots}
        if name in ("mu", "mut"):
            masks = {arm:support_column_mask(payloads[arm][0],arrays[arm].shape,support_columns_ji)
                     for arm in roots}
            support_description = "unique 16 mass columns"
        else:
            face_axis = "i" if name == "muu" else "j"
            masks = {}
            for arm in roots:
                meta3, _ = native_capture_file(roots[arm],
                                               f"pr98_dyn_{'ru' if face_axis == 'i' else 'rv'}_final_",3)
                face_mask = support_native_mask(meta3,
                    (meta3["fortran_bounds"][1]-meta3["fortran_bounds"][0]+1,
                     meta3["fortran_bounds"][3]-meta3["fortran_bounds"][2]+1,
                     meta3["fortran_bounds"][5]-meta3["fortran_bounds"][4]+1), support_kji, face_axis)
                masks[arm] = face_mask.any(axis=1)
                if masks[arm].shape != arrays[arm].shape:
                    raise ValueError(f"geometry {name} shape differs from native {face_axis}-face union")
            support_description = f"unique native {face_axis}-face columns"
        if any(payloads[arm][0]["fortran_bounds"] != payloads["OFF"][0]["fortran_bounds"]
               for arm in roots):
            raise ValueError(f"geometry {name} bounds differ across arms")
        if any(not np.array_equal(masks["OFF"],masks[arm]) for arm in roots):
            raise ValueError(f"geometry {name} support differs across arms")
        dynamic_mass_geometry[name] = {
            "all_array_sha256":{arm:payloads[arm][0]["sha256"] for arm in roots},
            "active_support":increment_metrics(arrays["OFF"],arrays["HYDRO"],arrays["COUPLED"],masks["OFF"]),
            "support_description":support_description,
            "units":"captured native geometry field units"}
    momentum = {}
    for variable,axis in (("ru","i"),("rv","j"),("rw","k")):
        momentum[variable] = {
            "full_dynamics_endpoint": native_face_triplet(roots,f"pr98_dyn_{variable}_final_",axis,support_kji),
            "dry_rk_assembled_out": native_face_triplet(roots,f"pr98_assembled_{variable}_tend_out_",axis,support_kji),
            "dry_rk_assembled_increment": native_face_triplet(
                roots,f"pr98_assembled_{variable}_tend",axis,support_kji,
                add_out_minus_in="assembled_out_minus_in")}
    selected_operators = ("advu_ru_tend","advv_rv_tend","advw_rw_tend",
                          "pgrad_ru_tend","pgrad_rv_tend","coriolis_ru_tend",
                          "coriolis_rv_tend","coriolis_rw_tend","curvature_ru_tend",
                          "curvature_rv_tend","curvature_rw_tend","hdifu_ru_tendf",
                          "hdifv_rv_tendf","hdifw_rw_tendf")
    axes = {"u":"i","v":"j","w":"k","ru":"i","rv":"j","rw":"k"}
    operator_rows = {}
    for prefix in selected_operators:
        variable = prefix.split("_")[1]
        operator_rows[prefix] = native_face_triplet(
            roots,f"pr98_{prefix}",axes[variable],support_kji,
            add_out_minus_in="operator_out_minus_in")
    selected_pressure_coriolis = {
        "ru":native_selected_sum_triplet(roots,("pr98_pgrad_ru_tend","pr98_coriolis_ru_tend"),"i",support_kji),
        "rv":native_selected_sum_triplet(roots,("pr98_pgrad_rv_tend","pr98_coriolis_rv_tend"),"j",support_kji)}
    mass = {name: native_column_triplet(roots,f"pr98_{name}_",support_columns_ji)
            for name in ("mu_large_in","mu_large_out","mu_small_in","mu_small_out",
                         "mu_tend_small","mudf_small_out")}
    mass["mu_update_rate"] = native_mu_update_triplet(roots,support_columns_ji)
    mass["mu_update_vs_mudf"] = compare_mu_update_to_mudf(roots,support_columns_ji)
    return {"native_units": "source operator / MUDF units; equal-cell unweighted L2; no energy norm or closure",
            "support_native_mass_origin_ijk":list(SUPPORT_ORIGIN_IJK),
            "support_origin_mapping":"History support indices are already cropped by one raw outer mass ring; cropped index (k,j,i) maps to native Fortran mass cell (i=2+i0,j=2+j0,k=1+k0).",
            "difference_arithmetic":"Captured R32 operands are individually promoted to float64 before source-call subtraction and compatible-source summation; these deltas retain any R32 accumulation rounding already present within the model call.",
            "support_mass_cells": int(support_kji.sum()),
            "support_unique_columns": int(support_columns_ji.sum()),
            "dynamic_mass_geometry_active_support":dynamic_mass_geometry,
            "momentum_arrays": momentum,
            "selected_operator_contributions": operator_rows,
            "selected_pressure_gradient_plus_coriolis_partial_rhs":selected_pressure_coriolis,
            "dry_mass_arrays": mass,
            "dry_mass_interpretation": "MUDF is the native combined DMDT+MU_TEND output; MU change divided by captured dts is a net rate only. DMDT flux terms were not separately captured, so this is not a continuity-flux closure.",
            "momentum_interpretation": "RU/RV/RW are raw native coupled RHS arrays at their actual C-grid staggering. These norms are descriptive source-coordinate diagnostics; they are not acceleration, energy, or closure diagnostics.",
            "selected_operator_coverage": "Partial: not captured are pg_buoy_w, w_damp, implicit advection, sixth-order diffusion and Rayleigh terms if active. Vertical-diffusion hooks are present in the instrumented source but emitted no snapshots because the current namelist's bl_pbl_physics=11 bypasses that bl_pbl_physics==0 branch. The listed call contributions are not exhaustive; full-dynamics and assembled arrays are reported separately.",
            "endpoint_timing": "dyn_*_final is sampled at the end of rk_tendency before rk_addtend_dry; assembled_*_out is sampled after rk_addtend_dry. The assembled arrays are the broadest directly captured momentum RHS endpoint for this call path.",
            "capture_stage_context": "Guarded rank-2/rank-3 snapshots are the first per-tag/per-tile calls. Source pins place momentum operators inside rk_tendency called from the Runge_Kutta_loop; the record itself has no timestep/RK-step identifier. MU snapshots are at the first advance_mu_t call after RK tendency assembly. Rank-1 c1h/c2h files are overwritten on each source call; these INTENT(IN) arrays are immutable in the called code and the final captured hashes match across arms. The matching native run completed only its first 20-second timestep; exact RK ordinal is inferred from source call order, not encoded in the raw files.",
            "units_by_source_array": {"ru":"native RU coupled tendency units","rv":"native RV coupled tendency units","rw":"native RW coupled tendency units","mu":"native mass units","mudf":"native mass tendency units"}}


def verify_capture_manifests(roots: dict[str,Path], evidence_dir: Path,
                             build_provenance: dict[str,Any],
                             noninterference: dict[str,Any]) -> dict[str,Any]:
    """Verify stable raw hashes against both private manifests and run receipts."""
    result = {}
    geometry_hashes = {}
    candidate_build_receipt_hashes = set()
    source_c1_build_sha = verify_c1_source_build_pin(EXPECTED_C1_BUILD_RECEIPT,
                                                     EXPECTED_C1_BUILD_RECEIPT_SHA256)
    prepare_source = ROOT / "tools/pr98_prepare_native_capture.py"
    expected_pin = f'C1_RECEIPT_SHA256 = "{EXPECTED_C1_BUILD_RECEIPT_SHA256}"'
    if expected_pin not in prepare_source.read_text():
        raise ValueError("native capture builder no longer pins the expected C1 source receipt")
    expected_executable = build_provenance.get("executable_sha256")
    if not expected_executable:
        raise ValueError("capture build provenance has no executable hash")
    for arm,run_root in roots.items():
        receipt_path = run_root.parent / "receipt.json"
        manifest_path = evidence_dir / f"{arm}_snapshot_manifest.json"
        inventory_path = evidence_dir / f"{arm}_inventory.json"
        receipt = json.loads(receipt_path.read_text())
        manifest = json.loads(manifest_path.read_text())
        inventory = json.loads(inventory_path.read_text())
        preflight_path = run_root.parent / "preflight.json"
        preflight = json.loads(preflight_path.read_text())
        baseline_receipt_path = RUNS[arm] / "receipt.json"
        baseline_receipt_sha = cloud.sha256(baseline_receipt_path)
        baseline_receipt = json.loads(baseline_receipt_path.read_text())
        run_binding = validate_capture_run_binding(arm,receipt,preflight,baseline_receipt,
                                                   expected_executable,
                                                   build_provenance.get("compiler_profile_sha256"))
        source_receipt_path = Path(run_binding["source_receipt_path"])
        if noninterference["arms"][arm].get("baseline_receipt_sha256") != baseline_receipt_sha:
            raise ValueError(f"{arm} noninterference result is not bound to the frozen C1 run receipt")
        candidate_build = receipt.get("candidate_build", {})
        candidate_build_receipt = Path(run_binding["candidate_build_receipt_path"])
        candidate_build_receipt_hashes.add(run_binding["candidate_build_receipt_sha256"])
        namelist_path = run_root / "namelist.input"
        if cloud.sha256(namelist_path) != receipt.get("candidate_namelist_sha256"):
            raise ValueError(f"{arm} namelist differs from its receipt-bound candidate")
        if not re.search(r"(?im)^\s*bl_pbl_physics\s*=\s*11\s*,?\s*$", namelist_path.read_text()):
            raise ValueError(f"{arm} namelist does not bind the inactive vertical-diffusion branch")
        if manifest.get("stable_two_pass_sha256") is not True:
            raise ValueError(f"{arm} raw manifest lacks stable two-pass SHA gate")
        if manifest.get("receipt_sha256") != cloud.sha256(receipt_path):
            raise ValueError(f"{arm} raw manifest does not bind current run receipt")
        if manifest.get("snapshot_count") != 57 or inventory.get("snapshot_count") != 57:
            raise ValueError(f"{arm} native capture inventory count is not the expected 57")
        generated = {row["path"]:row for row in receipt.get("generated_files",[])}
        rows = manifest.get("snapshots",[])
        if len(rows) != 57:
            raise ValueError(f"{arm} raw manifest row count mismatch")
        for row in rows:
            path = run_root / row["path"]
            if not path.is_file() or path.stat().st_size != row["bytes"] or cloud.sha256(path) != row["sha256"]:
                raise ValueError(f"{arm} raw snapshot hash/size changed: {path}")
            if row["path"] not in generated or generated[row["path"]] != row:
                raise ValueError(f"{arm} snapshot disagrees with finalized run receipt: {row['path']}")
            if row["path"].startswith("pr98_geom_"):
                geometry_hashes.setdefault(row["path"],{})[arm] = row["sha256"]
        result[arm] = {"receipt_path":str(receipt_path),"receipt_sha256":cloud.sha256(receipt_path),
                       "manifest_path":str(manifest_path),"manifest_sha256":cloud.sha256(manifest_path),
                       "inventory_path":str(inventory_path),"inventory_sha256":cloud.sha256(inventory_path),
                       "snapshot_count":len(rows),"snapshot_bytes":sum(row["bytes"] for row in rows),
                       "status":receipt["status"],"returncode":receipt["returncode"],
                       "one_step_20s_complete":True,
                       "executed_executable_sha256":receipt["executed_executable_sha256"],
                       "candidate_build_unchanged":receipt["candidate_build_unchanged"],
                       "candidate_input_unchanged":receipt["candidate_input_unchanged"],
                       "changed_staged_inputs":receipt.get("changed_staged_inputs"),
                       "changed_original_inputs":receipt.get("changed_original_inputs"),
                       "source_receipt_sha256":receipt["source_receipt_sha256"],
                       "source_receipt_path":str(source_receipt_path),
                       "source_receipt_hash_matches_preflight":True,
                       "candidate_build_receipt_path":str(candidate_build_receipt),
                       "candidate_build_receipt_sha256":candidate_build["receipt_sha256"],
                       "baseline_c1_receipt_sha256":baseline_receipt_sha,
                       "model_timestamps":receipt.get("model_timestamps"),
                       "candidate_wrfinput_sha256":receipt.get("candidate_wrfinput_sha256")}
    if len(candidate_build_receipt_hashes) != 1:
        raise ValueError("native capture arms do not share one candidate build receipt")
    static_geometry = ("pr98_geom_c1h.bin","pr98_geom_c2h.bin","pr98_geom_msftx_1_235_1_283_.bin",
                       "pr98_geom_msfty_1_235_1_283_.bin","pr98_geom_msfux_1_235_1_283_.bin",
                       "pr98_geom_msfuy_1_235_1_283_.bin","pr98_geom_msfvx_1_235_1_283_.bin",
                       "pr98_geom_msfvx_inv_1_235_1_283_.bin","pr98_geom_msfvy_1_235_1_283_.bin")
    dynamic_mass = ("pr98_geom_mu_1_235_1_283_.bin","pr98_geom_mut_1_235_1_283_.bin",
                    "pr98_geom_muu_1_235_1_283_.bin","pr98_geom_muv_1_235_1_283_.bin")
    return {"schema":"pr98_native_capture_binding_v1","arms":result,
            "source_c1_build_receipt_sha256":source_c1_build_sha,
            "capture_builder_source_path":str(prepare_source),
            "capture_builder_source_sha256":cloud.sha256(prepare_source),
            "geometry_snapshot_sha256":geometry_hashes,
            "static_coordinate_geometry_equal_across_arms":all(
                len(set(geometry_hashes.get(name,{}).values())) == 1 and
                set(geometry_hashes.get(name,{})) == set(roots) for name in static_geometry),
            "dynamic_mass_geometry_equal_across_arms":all(
                len(set(geometry_hashes.get(name,{}).values())) == 1 and
                set(geometry_hashes.get(name,{})) == set(roots) for name in dynamic_mass)}


def increment_metrics(off: np.ndarray, hydro: np.ndarray, coupled: np.ndarray,
                      mask: np.ndarray) -> dict[str, Any]:
    """Report absolute per-arm norms and h/b/net decomposition on one native mask."""
    if any(a.shape != mask.shape for a in (off, hydro, coupled)):
        raise ValueError("native arm arrays and support mask must have identical shape")
    a, hstate, c = (x[mask].astype(np.float64) for x in (off, hydro, coupled))
    if not all(np.isfinite(x).all() for x in (a,hstate,c)):
        raise ValueError("native support values must be finite")
    h, b, n = hstate-a, c-hstate, c-a
    return {"support_values": int(mask.sum()),
            "absolute_by_arm": {arm: summarize(values) for arm, values in
                                (("OFF",a),("HYDRO",hstate),("COUPLED",c))},
            "increments": {"h_H_minus_O": summarize(h), "b_C_minus_H": summarize(b),
                           "net_C_minus_O": summarize(n)},
            "inner_products": {"h_dot_b": float(np.dot(h,b)), "h_squared": float(np.dot(h,h)),
                               "b_squared": float(np.dot(b,b)), "net_squared": float(np.dot(n,n)),
                               "net_squared_identity": float(np.dot(h,h)+2*np.dot(h,b)+np.dot(b,b))},
            "units": "native operator units; equal-cell unweighted L2"}


def analyze(roots: dict[str, Path] = RUNS, composition_path: Path = COMPOSITION) -> dict[str, Any]:
    if set(roots) != {"OFF", "HYDRO", "COUPLED"}:
        raise ValueError("expected OFF, HYDRO, and COUPLED run roots")
    receipts, histories, identities = {}, {}, {}
    for arm, root in roots.items():
        receipts[arm] = json.loads((root / "receipt.json").read_text())
        history, receipt, identity = cloud.verify_run(arm, root)
        if receipt != receipts[arm]:
            raise ValueError(f"{arm} receipt changed during validation")
        histories[arm] = history
        identities[arm] = identity
    validate_receipt_triplet(receipts, expected_executable_sha256=EXECUTABLE_SHA256)
    initial_state = compare_initial_states(roots, receipts)
    all_initial_variables = compare_all_initial_variables(roots, receipts)

    frames: dict[int, dict[str, dict[str, np.ndarray]]] = {}
    native_faces: dict[str, dict[str, np.ndarray]] = {}
    for second in (0, 60):
        frame = second // 60
        expected = (dt.datetime(2026, 8, 16, 13) + dt.timedelta(seconds=second)).strftime("%Y-%m-%d_%H:%M:%S")
        frames[second] = {}
        for arm, history in histories.items():
            timestamp, fields, _ = load_history(history, frame)
            if timestamp != expected:
                raise ValueError(f"{arm} frame at {second}s has timestamp {timestamp}")
            frames[second][arm] = fields
            if second == 0:
                native_faces[arm] = cloud.read_face_winds(history, frame)
    shape = frames[0]["OFF"]["U"].shape
    composition = json.loads(composition_path.read_text())["composed_qc_vertical_influence"]
    masks = cloud.make_masks(composition, shape)
    if int(masks["original_613_native_support"].sum()) != 613:
        raise ValueError("source support must remain the pinned 613 native cells")
    build_provenance_path = CAPTURE_EVIDENCE / "build_provenance.json"
    build_provenance = json.loads(build_provenance_path.read_text())
    if cloud.sha256(ADVANCE_MU_SOURCE) != ADVANCE_MU_SOURCE_SHA256:
        raise ValueError("external advance_mu_t source reference changed")
    noninterference_path = CAPTURE_EVIDENCE / "frozen_c1_noninterference.json"
    noninterference = json.loads(noninterference_path.read_text())
    if any(not row.get("trace_match") or
           not all(item.get("match") for item in row["t1_full_memory_pre_post"].values()) or
           not all(item.get("match") for item in row["t0_history_fields"].values())
           for row in noninterference["arms"].values()):
        raise ValueError("observer noninterference check failed")
    capture_binding = verify_capture_manifests(CAPTURE_RUNS,CAPTURE_EVIDENCE,
                                               build_provenance,noninterference)
    native_capture = analyze_native_capture(CAPTURE_RUNS,masks["original_613_native_support"])
    capture_provenance = {
        "build_provenance_path":str(build_provenance_path),
        "build_provenance_sha256":cloud.sha256(build_provenance_path),
        "build_identity":build_provenance.get("build_identity"),
        "executable_sha256":build_provenance.get("executable_sha256"),
        "intel_profile_sha256":build_provenance.get("compiler_profile_sha256"),
        "observer_source_sha256":build_provenance.get("observer",{}).get("source_sha256"),
        "module_em_generated_source_sha256":next(row["generated_source_sha256"] for row in build_provenance["overrides"] if row["member"] == "module_em.o"),
        "advance_mu_t_source_path":str(ADVANCE_MU_SOURCE),
        "advance_mu_t_source_sha256":ADVANCE_MU_SOURCE_SHA256,
        "advance_mu_t_source_compile_bound":False,
        "noninterference_path":str(noninterference_path),
        "noninterference_sha256":cloud.sha256(noninterference_path),
        "noninterference_scope":noninterference["scope"],
        "all_arms_trace_t0_t1_checks_match":True}

    def diff(pair: str, second: int, name: str) -> np.ndarray:
        left, right = {"H-O": ("OFF", "HYDRO"), "C-H": ("HYDRO", "COUPLED"),
                       "C-O": ("OFF", "COUPLED")}[pair]
        return (frames[second][right][name].astype(np.float64) -
                frames[second][left][name].astype(np.float64))

    fields = ("U", "V")
    correction_rows = {}
    for support, mask in masks.items():
        h = np.concatenate([diff("H-O", 0, name)[mask] for name in fields])
        b = np.concatenate([diff("C-H", 0, name)[mask] for name in fields])
        n = h + b
        correction_rows[support] = {
            "H_minus_O": {"l2": float(np.linalg.norm(h)), "rms": float(np.sqrt(np.mean(h*h)))},
            "C_minus_H": {"l2": float(np.linalg.norm(b)), "rms": float(np.sqrt(np.mean(b*b)))},
            "C_minus_O": {"l2": float(np.linalg.norm(n)), "rms": float(np.sqrt(np.mean(n*n)))},
            "initial_inner_products": {"h_dot_b": float(np.dot(h,b)), "h_squared": float(np.dot(h,h)),
                                       "b_squared": float(np.dot(b,b)), "net_squared_identity": float(np.dot(n,n)),
                                       "net_squared_from_terms": float(np.dot(h,h)+2*np.dot(h,b)+np.dot(b,b))},
            "per_component": {name: pair_metrics(diff("H-O",0,name)[mask],
                                                   diff("C-O",0,name)[mask]) for name in fields}}

    face_rows = {}
    for name in ("U_face", "V_face"):
        face_rows[name] = {}
        for support, mask in masks.items():
            # Face rows are direct native C-grid arrays, measured over the full
            # common active crop; the mass-cell masks do not map one-to-one to faces.
            if support != "full_active_history_domain":
                continue
            arrays = {arm: native_faces[arm][name].astype(np.float64) for arm in roots}
            h_face, b_face = arrays["HYDRO"] - arrays["OFF"], arrays["COUPLED"] - arrays["HYDRO"]
            face_rows[name][support] = {"h_l2": float(np.linalg.norm(h_face)),
                                        "h_rms": float(np.sqrt(np.mean(h_face*h_face))),
                                        "b_l2": float(np.linalg.norm(b_face)),
                                        "b_rms": float(np.sqrt(np.mean(b_face*b_face))),
                                        "h_dot_b": float(np.sum(h_face.astype(np.float64)*b_face.astype(np.float64))),
                                        "net_l2": float(np.linalg.norm(h_face+b_face)),
                                        "n": int(h_face.size), "shape_kji": list(h_face.shape)}

    response = {}
    for second in (0,60):
        response[str(second)] = {}
        for name in ("pressure", "geopotential", "W"):
            rows = {}
            for pair in ("H-O", "C-H", "C-O"):
                values = diff(pair, second, name)[masks["original_613_native_support"]]
                rows[pair] = {"l2": float(np.linalg.norm(values)), "rms": float(np.sqrt(np.mean(values*values))),
                              "max_abs": float(np.max(np.abs(values))), "sum": float(np.sum(values, dtype=np.float64)),
                              "n": int(values.size)}
            response[str(second)][name] = rows
    peak_locations = {}
    for name, axis in (("U", 2), ("V", 1)):
        face_index = initial_state["fields"][name]["COUPLED_minus_HYDRO"]["index_native"]
        k, j, i = face_index
        # NetCDF raw U/V carry one extra face in their staggered direction;
        # active history fields crop the raw outer mass ring on both sides.
        adjacent = ([i - 1, i] if axis == 2 else [j - 1, j])
        cells = [[k, j - 1, mi - 1] for mi in adjacent] if axis == 2 else \
                [[k, mj - 1, i - 1] for mj in adjacent]
        rows = []
        for cell in cells:
            ck, cj, ci = cell
            if not (0 <= ck < shape[0] and 0 <= cj < shape[1] and 0 <= ci < shape[2]):
                raise ValueError(f"wind face neighbor maps outside the active history: {name} {cell}")
            row = {"active_mass_index_kji": cell,
                   "in_original_613_support": bool(masks["original_613_native_support"][ck,cj,ci]),
                   "state_response": {}}
            for second in (0,60):
                row["state_response"][str(second)] = {
                    fld: {pair: float(diff(pair,second,fld)[ck,cj,ci])
                          for pair in ("H-O","C-H","C-O")}
                    for fld in ("pressure","geopotential","W")}
            rows.append(row)
        peak_locations[name] = {"native_face_max_abs_index_kji_zero_based": face_index,
                                "stagger_direction": "i face between adjacent mass cells" if axis == 2 else "j face between adjacent mass cells",
                                "adjacent_mass_cells": rows,
                                "mapping": "Raw input array indices map to active history mass coordinates after the existing one-cell outer-ring crop; neighboring mass cells are reported because a native face has no single mass-cell coordinate."}
    return {"schema": "pr98_native_effect_v1", "physical_approval": "FAIL_OPEN",
            "run_identities": {arm: {"receipt_sha256": identities[arm]["receipt_sha256"],
                                      "history_path": identities[arm]["path"],
                                      "history_sha256": identities[arm]["sha256"],
                                      "wrfinput_sha256": receipts[arm]["candidate_wrfinput_sha256"]}
                               for arm, root in roots.items()},
            "composition": {"path": str(composition_path),
                            "sha256": cloud.sha256(composition_path),
                            "support_values": int(masks["original_613_native_support"].sum()),
                            "columns": int(masks["original_613_native_support"].any(axis=0).sum())},
            "initial_input_state_identity": initial_state,
            "all_stored_HYDRO_COUPLED_wrfinput_comparison": all_initial_variables,
            "initial_wind_peak_same_location_response": peak_locations,
            "support_counts": {name: int(mask.sum()) for name, mask in masks.items()},
            "initial_staggered_wind_corrections_mass_destaggered": correction_rows,
            "initial_native_face_wind_corrections": face_rows,
            "same_location_state_response": response,
            "tendency_capture": {"available": True,
                                 "capture_binding": capture_binding,
                                 "capture_provenance":capture_provenance,
                                 "native_source_arrays": native_capture,
                                 "observed": ["receipt-bound initial and 60-second history states",
                                              "receipt-bound 20-second source-native momentum and dry-mass arrays"],
                                 "missing": ["exhaustive operator decomposition including implicit advection, buoyancy, the inactive vertical-diffusion branch and flux-only dry-mass terms"],
                                 "interpretation": "Native source-form arrays are compared directly at C-grid staggering on equal cell masks. This is not an acceleration/energy diagnostic or force/continuity closure."},
            "skill": "NOT_EVALUATED",
            "limits": ["U and V here are mass-destaggered from native C-grid faces for same-location support comparison.",
                       "State response norms and inner products are descriptive; they do not isolate causal mechanisms.",
                       "No observation operator or independent observed target was used."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
