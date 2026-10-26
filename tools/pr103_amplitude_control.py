#!/usr/bin/env python3
"""Construct the PR103 amplitude-matched uniform PROJECTED control."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import sys

import netCDF4
import numpy as np

import pr94_cloud_response as cloud
import pr87_native_history as history
import pr99_native_projection as projection
import pr102_native_wind_candidate as pr102
import pr102_response as pr102_response


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/evidence/pr103_amplitude_control_20261026/policy.json"
POLICY_SHA256 = "32b916bb6789eeb83ba83798e639f48da73c6001444660d8113ed3c09d947696"
COMPOSITION = pr102.COMPOSITION
EXPECTED_NATIVE_LEVELS = pr102.EXPECTED_NATIVE_LEVELS


@dataclass(frozen=True)
class AmplitudeControl:
    scale: float
    ideal: np.ndarray
    stored: np.ndarray
    target_norm: float
    ideal_norm: float
    stored_norm: float
    storage_bound: float
    arithmetic_bound: float
    norm_evaluation_bound: float
    continuous_reference_error_bound: float | None


def _half_ulp_bound(values: np.ndarray) -> float:
    """L2 round-to-nearest REAL32 envelope for a finite REAL64 array."""
    rounded = values.astype(np.float32)
    if not np.isfinite(rounded).all():
        raise ValueError("amplitude control overflows REAL32")
    above = np.nextafter(rounded, np.float32(np.inf), dtype=np.float32)
    below = np.nextafter(rounded, np.float32(-np.inf), dtype=np.float32)
    ulp = np.maximum(np.abs(above.astype(np.float64) - rounded),
                     np.abs(rounded.astype(np.float64) - below))
    bound = float(np.linalg.norm(0.5 * ulp.astype(np.float64)))
    if not np.isfinite(bound):
        raise ValueError("REAL32 half-ULP bound is not finite")
    return bound


def build_amplitude_control(hydro: np.ndarray, projected: np.ndarray,
                            structured: np.ndarray, free: np.ndarray,
                            continuous_projected: np.ndarray | None = None
                            ) -> AmplitudeControl:
    """Scale actual stored P−H to the actual stored N−H global norm.

    Arrays may be native U/V faces concatenated by the caller. All input arrays
    must be finite REAL32 readbacks. One scalar applies on all free faces; the
    returned `ideal` is the REAL64 formula before its single REAL32 cast.
    """
    arrays = [np.asarray(value) for value in (hydro, projected, structured)]
    h, p, n = [value.astype(np.float64) for value in arrays]
    mask = np.asarray(free, dtype=bool)
    if (h.shape != p.shape or h.shape != n.shape or mask.shape != h.shape or
            any(value.dtype != np.dtype("float32") for value in arrays)):
        raise ValueError("H, P, N must be same-shape REAL32 arrays with a matching free mask")
    if not all(np.isfinite(value).all() for value in (h, p, n)):
        raise ValueError("H, P, N must be finite")
    if not mask.any():
        raise ValueError("amplitude control has no free faces")

    p_delta = (p - h)[mask]
    n_delta = (n - h)[mask]
    p_norm = float(np.linalg.norm(p_delta))
    target_norm = float(np.linalg.norm(n_delta))
    if not np.isfinite([p_norm, target_norm]).all() or p_norm == 0 or target_norm == 0:
        raise ValueError("stored P−H and N−H norms must be finite and nonzero")
    scale = target_norm / p_norm

    ideal = h.copy()
    ideal[mask] = h[mask] + scale * p_delta
    unit_roundoff = np.finfo(np.float64).eps / 2
    gamma4 = (4 * unit_roundoff) / (1 - 4 * unit_roundoff)
    arithmetic_bound = float(np.linalg.norm(
        gamma4 * (np.abs(h[mask]) + abs(scale) *
                  (np.abs(p[mask]) + np.abs(h[mask])))))
    stored = ideal.astype(np.float32)
    if not np.isfinite(stored).all():
        raise ValueError("amplitude control overflows REAL32")
    storage_bound = _half_ulp_bound(ideal[mask])
    stored_norm = float(np.linalg.norm((stored.astype(np.float64) - h)[mask]))
    norm_scale = max(target_norm, float(np.linalg.norm((ideal - h)[mask])), stored_norm)
    unit_roundoff = np.finfo(np.float64).eps / 2
    difference_bound = unit_roundoff * (
        np.linalg.norm(np.abs(stored.astype(np.float64)[mask]) + np.abs(h[mask])) +
        np.linalg.norm(np.abs(n[mask]) + np.abs(h[mask])) +
        np.linalg.norm(np.abs(p[mask]) + np.abs(h[mask])))
    norm_evaluation_bound = (difference_bound + 2 * unit_roundoff *
                             (4 * int(mask.sum()) + 8) * norm_scale +
                             unit_roundoff * target_norm)

    continuous_error_bound = None
    if continuous_projected is not None:
        p_cont = np.asarray(continuous_projected, dtype=np.float64)
        if p_cont.shape != h.shape or not np.isfinite(p_cont).all():
            raise ValueError("continuous PR99 reconstruction must be finite and match native shape")
        reconstruction_error = float(np.linalg.norm((p - p_cont)[mask]))
        reconstruction_arithmetic_bound = unit_roundoff * float(np.linalg.norm(
            np.abs(p[mask]) + np.abs(p_cont[mask])))
        continuous_error_bound = (scale * reconstruction_error + storage_bound + arithmetic_bound +
                                  norm_evaluation_bound + scale * reconstruction_arithmetic_bound)
        if not np.isfinite(continuous_error_bound):
            raise ValueError("continuous-reference error bound is not finite")

    if not np.isfinite([storage_bound, arithmetic_bound, norm_evaluation_bound,
                        stored_norm]).all():
        raise ValueError("amplitude-control storage or arithmetic bound is not finite")

    return AmplitudeControl(scale, ideal, stored, target_norm,
                            float(np.linalg.norm((ideal - h)[mask])), stored_norm,
                            storage_bound, arithmetic_bound, norm_evaluation_bound,
                            continuous_error_bound)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": _sha256(path)}


def _read_wind(ds, name: str) -> np.ndarray:
    return history._finite(ds, name, 0)


def _free_increment(u: np.ndarray, v: np.ndarray, base_u: np.ndarray,
                    base_v: np.ndarray, u2: np.ndarray, v2: np.ndarray) -> np.ndarray:
    return np.concatenate([
        np.r_[(u[k].astype(np.float64) - base_u[k])[u2],
              (v[k].astype(np.float64) - base_v[k])[v2]]
        for k in range(u.shape[0])])


def _verify_pr102_receipt(receipt_path: Path, structured: Path,
                          pr99_receipt: Path) -> dict:
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get("schema") != "pr102_wind_structure_proposal_v1" or
            receipt.get("status") != "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_SOURCE_CAPTURE" or
            receipt.get("role") != "COUPLED"):
        raise ValueError("expected the archived PR102 STRUCTURED proposal receipt")
    candidate = receipt.get("candidate", {})
    if not structured.is_file() or _sha256(structured) != candidate.get("sha256"):
        raise ValueError("PR102 candidate hash does not bind the declared structured input")
    projection_receipt = receipt.get("pr99_projection_receipt", {})
    if (Path(projection_receipt.get("path", "")).resolve() != pr99_receipt.resolve() or
            not pr99_receipt.is_file() or _sha256(pr99_receipt) != projection_receipt.get("sha256")):
        raise ValueError("PR102 proposal does not bind the declared PR99 receipt")
    return receipt


def propose(hydro: Path, coupled: Path, original_p: Path, structured: Path,
            pr99_receipt: Path, pr102_receipt: Path, structured_run_receipt: Path,
            execution_preflight_path: Path, constants_receipt: Path, boundary: Path,
            output: Path) -> dict:
    """Build one uniform-scaling control and a source-bound proposal receipt."""
    sidecar = output.with_suffix(".proposal.json")
    if output.exists() or sidecar.exists():
        raise FileExistsError(output)
    if not POLICY.is_file() or _sha256(POLICY) != POLICY_SHA256:
        raise ValueError("frozen PR103 amplitude-control policy hash mismatch")
    pr99 = pr102._verify_pr99_receipt(pr99_receipt, hydro, coupled,
                                      original_p, boundary)
    _verify_pr102_receipt(pr102_receipt, structured, pr99_receipt)
    execution_preflight = json.loads(execution_preflight_path.read_text())
    run_receipt, run_preflight = pr102_response._closed_structured_run(
        structured_run_receipt.parent, execution_preflight)
    if (run_receipt.get("arm") != "STRUCTURED" or
            run_receipt.get("candidate_wrfinput_sha256") != _sha256(structured) or
            run_receipt.get("candidate_input_binding", {}).get("receipt_sha256") !=
            _sha256(pr102_receipt) or run_preflight.get("duration_seconds") != 640 or
            run_receipt.get("executed_executable_sha256") !=
            pr102_response.preflight.EXPECTED_EXECUTABLE or
            run_receipt.get("candidate_wrfbdy_sha256") !=
            pr102_response.preflight.EXPECTED_BOUNDARY):
        raise ValueError("closed PR102 STRUCTURED run does not bind the declared N input")
    gravity, gravity_identity = history._constants(constants_receipt)
    pinned = [hydro, coupled, original_p, structured, pr99_receipt,
              pr102_receipt, structured_run_receipt, execution_preflight_path,
              constants_receipt, boundary, POLICY, COMPOSITION,
              Path(__file__).resolve(), Path(pr102.__file__).resolve(),
              Path(projection.__file__).resolve(), Path(cloud.__file__).resolve(),
              Path(history.__file__).resolve(), Path(pr102_response.__file__).resolve(),
              Path(pr99["_composition_source_binding"]["path"])]
    source_hashes = {str(path.resolve()): _sha256(path) for path in pinned}

    with netCDF4.Dataset(hydro) as h, netCDF4.Dataset(coupled) as c, \
            netCDF4.Dataset(original_p) as p, netCDF4.Dataset(structured) as n:
        for ds in (h, c, p, n):
            ds.set_auto_mask(False)
        pr102.verify_only_wind_changed(original_p, hydro)
        pr102.verify_only_wind_changed(coupled, original_p)
        pr102.verify_only_wind_changed(structured, original_p)
        hu, hv = (_read_wind(h, name) for name in ("U", "V"))
        cu, cv = (_read_wind(c, name) for name in ("U", "V"))
        pu, pv = (_read_wind(p, name) for name in ("U", "V"))
        nu, nv = (_read_wind(n, name) for name in ("U", "V"))
        if any(ds[name].dtype != np.dtype("float32") for ds in (h, c, p, n)
               for name in ("U", "V")):
            raise ValueError("H/P/N native U/V must be REAL32")
        if (hu.shape != pu.shape or cu.shape != hu.shape or nu.shape != hu.shape or
                hv.shape != pv.shape or cv.shape != hv.shape or nv.shape != hv.shape):
            raise ValueError("H/P/N native U/V shapes differ")
        nz, ny, nxu = hu.shape
        if nz != EXPECTED_NATIVE_LEVELS:
            raise ValueError("native levels differ from the frozen PR102 support")
        composition = json.loads(COMPOSITION.read_text())
        composed = composition["composed_qc_vertical_influence"]
        support = cloud.make_masks(composed, (nz, ny - 2, hv.shape[2] - 2))
        columns = np.zeros((ny, hv.shape[2]), dtype=bool)
        columns[1:-1, 1:-1] = support["fixed_5_cell_chebyshev_buffer"].any(axis=0)
        u2, v2 = projection.control_faces(columns)
        native_support = support["original_613_native_support"]
        pr99_data = json.loads(pr99_receipt.read_text())
        if (native_support.sum() != pr102.EXPECTED_SUPPORT_LEVELS or
                native_support.any(axis=0).sum() != pr102.EXPECTED_SUPPORT_COLUMNS or
                columns.sum() != pr102.EXPECTED_BUFFER_COLUMNS or
                u2.sum() + v2.sum() != pr102.EXPECTED_FREE_FACES_PER_LAYER or
                pr99_data.get("fixed_columns") != int(columns.sum()) or
                pr99_data.get("free_faces_per_layer") != int(u2.sum() + v2.sum()) or
                len(pr99_data.get("layers", [])) != nz):
            raise ValueError("derived support differs from receipt-bound PR99/PR102 control")
        if not np.array_equal(pu[:, ~u2], hu[:, ~u2]) or not np.array_equal(pv[:, ~v2], hv[:, ~v2]):
            raise ValueError("stored P differs from H outside the inherited free faces")
        if not np.array_equal(nu[:, ~u2], hu[:, ~u2]) or not np.array_equal(nv[:, ~v2], hv[:, ~v2]):
            raise ValueError("stored N differs from H outside the inherited free faces")
        free_u, free_v = np.broadcast_to(u2, hu.shape), np.broadcast_to(v2, hv.shape)
        raw_u, raw_v = cu.astype(np.float64) - hu, cv.astype(np.float64) - hv
        if np.any(raw_u[:, ~u2]) or np.any(raw_v[:, ~v2]):
            raise ValueError("COUPLED−HYDRO differs outside the inherited free faces")
        geometry = pr102._geometry(h, free_u, free_v, gravity)
        roughness_matrix, _, _, edge_groups = pr102._roughness_matrix(free_u, free_v, geometry)

        projected_layers = []
        layer_matrices = []
        layer_reports = []
        for k in range(nz):
            matrix = projection.divergence_matrix(columns,
                                                   *projection.face_coefficients(h, k))
            increment = np.r_[raw_u[k][u2], raw_v[k][v2]]
            projected_increment, report = projection.project_increment(matrix, increment)
            base = np.r_[hu[k][u2], hv[k][v2]]
            reconstructed = (base + projected_increment).astype(np.float32)
            expected = np.r_[pu[k][u2], pv[k][v2]].astype(np.float32)
            if reconstructed.tobytes() != expected.tobytes():
                raise ValueError("PR99 continuous reconstruction does not match stored P")
            layer_matrices.append(matrix)
            projected_layers.append(projected_increment)
            layer_reports.append(report)

        hfree = np.concatenate([hu[:, u2].ravel(), hv[:, v2].ravel()])
        pfree = np.concatenate([pu[:, u2].ravel(), pv[:, v2].ravel()])
        nfree = np.concatenate([nu[:, u2].ravel(), nv[:, v2].ravel()])
        continuous_u = np.concatenate([
            hu[k][u2] + projected_layers[k][:int(u2.sum())] for k in range(nz)])
        continuous_v = np.concatenate([
            hv[k][v2] + projected_layers[k][int(u2.sum()):] for k in range(nz)])
        continuous_pfree = np.concatenate([continuous_u, continuous_v])
        n_u = int(u2.sum())
        free_vector = np.ones(hfree.shape, dtype=bool)
        control = build_amplitude_control(hfree.astype(np.float32), pfree.astype(np.float32),
                                          nfree.astype(np.float32), free_vector,
                                          continuous_pfree)
        stored_u, stored_v = hu.copy(), hv.copy()
        stored_u[:, u2] = control.stored[:nz * n_u].reshape(nz, n_u)
        stored_v[:, v2] = control.stored[nz * n_u:].reshape(nz, int(v2.sum()))

        raw = np.concatenate([np.r_[raw_u[k][u2], raw_v[k][v2]] for k in range(nz)])
        projected = np.concatenate(projected_layers)
        delta = float(np.linalg.norm(raw - projected))
        candidate_delta = np.concatenate([
            np.r_[(stored_u[k].astype(np.float64) - hu[k])[u2],
                  (stored_v[k].astype(np.float64) - hv[k])[v2]]
            for k in range(nz)])
        stored_distance = float(np.linalg.norm(candidate_delta - projected))
        if not 0 < delta < np.linalg.norm(projected) or stored_distance > delta:
            raise ValueError("amplitude control violates the inherited PR99 displacement budget")
        if abs(control.stored_norm - control.target_norm) > (
                control.storage_bound + control.arithmetic_bound + control.norm_evaluation_bound):
            raise ValueError("REAL32 readback misses the predeclared amplitude-match bound")
        continuous_increment = control.scale * projected
        p_increment = _free_increment(pu, pv, hu, hv, u2, v2)
        n_increment = _free_increment(nu, nv, hu, hv, u2, v2)
        roughness_p = pr102._roughness_report(roughness_matrix, p_increment, edge_groups)
        roughness_n = pr102._roughness_report(roughness_matrix, n_increment, edge_groups)
        roughness_scaled_p = {key: control.scale ** 2 * value
                              for key, value in roughness_p.items()}
        continuous_residuals = [float(np.linalg.norm(layer_matrices[k] @
                                  continuous_increment[k * len(projected_layers[k]):
                                                      (k + 1) * len(projected_layers[k])]))
                                for k in range(nz)]
        if any(residual > float(layer_reports[k]["continuous_solver_limit"])
               for k, residual in enumerate(continuous_residuals)):
            raise ValueError("amplitude control exceeds the inherited PR99 continuous layer gate")

    try:
        shutil.copy2(original_p, output)
        with netCDF4.Dataset(output, "r+") as ds:
            ds["U"][0], ds["V"][0] = stored_u, stored_v
        pr102.verify_only_wind_changed(output, original_p)
        with netCDF4.Dataset(output) as ds:
            ds.set_auto_mask(False)
            actual_u, actual_v = _read_wind(ds, "U"), _read_wind(ds, "V")
            actual_increment = _free_increment(actual_u, actual_v, hu, hv, u2, v2)
            actual_norm = float(np.linalg.norm(actual_increment))
            actual_distance = float(np.linalg.norm(actual_increment - projected))
            actual_continuous_error = float(np.linalg.norm(actual_increment - continuous_increment))
            stored_layer_residuals = [
                float(np.linalg.norm(layer_matrices[k] @ np.r_[
                    (actual_u[k].astype(np.float64) - hu[k])[u2],
                    (actual_v[k].astype(np.float64) - hv[k])[v2]]))
                for k in range(nz)]
            if abs(actual_norm - control.target_norm) > (
                    control.storage_bound + control.arithmetic_bound +
                    control.norm_evaluation_bound):
                raise ValueError("candidate readback misses the frozen amplitude-match bound")
            if actual_distance > delta:
                raise ValueError("candidate readback exceeds the inherited PR99 budget")
            if actual_continuous_error > control.continuous_reference_error_bound:
                raise ValueError("stored control exceeds the predeclared continuous-reference error bound")
            roughness_a = pr102._roughness_report(roughness_matrix, actual_increment, edge_groups)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    for path_text, digest in source_hashes.items():
        if _sha256(Path(path_text)) != digest:
            output.unlink(missing_ok=True)
            raise ValueError(f"source artifact changed during proposal: {path_text}")
    return {
        "schema": "pr103_amplitude_control_proposal_v1",
        "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_SOURCE_CAPTURE",
        "role": "AMPLITUDE_MATCHED_CONTROL",
        "candidate": _artifact(output), "reference_hydro": _artifact(hydro),
        "reference_coupled": _artifact(coupled), "original_p": _artifact(original_p),
        "parent_sha256": _sha256(original_p),
        "reference_structured": _artifact(structured), "boundary": _artifact(boundary),
        "generator": _artifact(Path(__file__).resolve()),
        "policy": _artifact(POLICY), "composition": _artifact(COMPOSITION),
        "pr99_projection_receipt": _artifact(pr99_receipt),
        "pr102_structured_receipt": _artifact(pr102_receipt),
        "pr102_structured_run_receipt": _artifact(structured_run_receipt),
        "pr102_structured_run_preflight": _artifact(structured_run_receipt.parent / "preflight.json"),
        "pr102_execution_preflight": _artifact(execution_preflight_path),
        "source_pin_hashes": source_hashes,
        "composition_sha256": _sha256(COMPOSITION),
        "gravity": gravity_identity,
        "change_contract": {"changed_variables": ["U", "V"],
                            "non_target_variables_identical": True},
        "metrics": {
            "scale": control.scale, "stored_target_norm": control.target_norm,
            "ideal_from_stored_p_norm": control.ideal_norm,
            "stored_readback_norm": actual_norm,
            "readback_norm_error_bound": control.storage_bound + control.arithmetic_bound + control.norm_evaluation_bound,
            "half_ulp_storage_bound": control.storage_bound,
            "arithmetic_bound": control.arithmetic_bound,
            "norm_evaluation_bound": control.norm_evaluation_bound,
            "continuous_pr99_reference_error_bound": control.continuous_reference_error_bound,
            "stored_to_continuous_pr99_reference_distance": actual_continuous_error,
            "continuous_pr99_reference_norm": float(np.linalg.norm(continuous_increment)),
            "continuous_pr99_layer_residual_l2": continuous_residuals,
            "stored_readback_layer_residual_l2": stored_layer_residuals,
            "geometric_roughness_of_p_minus_h": roughness_p,
            "geometric_roughness_of_n_minus_h": roughness_n,
            "geometric_roughness_of_a_minus_h": roughness_a,
            "ideal_s_squared_roughness_of_p_minus_h": roughness_scaled_p,
            "stored_distance_to_pr99_projection": actual_distance,
            "pr99_additional_change_budget": delta,
            "continuous_pr99_projection_layers": layer_reports},
        "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("hydro", "coupled", "original-p", "structured",
                 "pr99-receipt", "pr102-receipt", "structured-run-receipt",
                 "execution-preflight", "constants-receipt", "boundary", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    report = propose(args.hydro, args.coupled, args.original_p, args.structured,
                     args.pr99_receipt, args.pr102_receipt,
                     args.structured_run_receipt, args.execution_preflight,
                     args.constants_receipt, args.boundary, args.output)
    sidecar = args.output.with_suffix(".proposal.json")
    sidecar_created = False
    try:
        with sidecar.open("x") as stream:
            sidecar_created = True
            stream.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    except Exception:
        args.output.unlink(missing_ok=True)
        if sidecar_created:
            sidecar.unlink(missing_ok=True)
        raise
    print(json.dumps({"status": report["status"], "candidate_sha256": report["candidate"]["sha256"],
                      "scale": report["metrics"]["scale"]}, indent=2))


if __name__ == "__main__":
    main()
