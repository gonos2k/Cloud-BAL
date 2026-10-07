#!/usr/bin/env python3
"""Audit PR63 same-call hybrid geometry against public KDM6 captures.

This checks a source-defined geometry identity and artifact binding. It does not
close a physical mass/energy budget or certify scientific initialization.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np

MAGIC = b"PR63GEO2"
STAGES = ("PRE_MICROPHYSICS", "POST_MICROPHYSICS")
ARRAY_NAMES = ("mu1", "mu2", "mub", "c1h", "c2h", "c3f", "c4f", "dnw", "msftx", "msfty")
BOUND_NAMES = ("ims", "ime", "jms", "jme", "kms", "kme", "its", "ite", "jts", "jte", "kts", "kte")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_exact(data: bytes, offset: int, size: int, label: str) -> tuple[bytes, int]:
    end = offset + size
    if size < 0 or end > len(data):
        raise ValueError(f"truncated {label} at byte {offset}")
    return data[offset:end], end


def parse_geometry(data: bytes) -> list[dict[str, Any]]:
    """Parse the two fixed-position, big-endian PR63GEO2 stream records."""
    offset = 0
    records = []
    for expected_stage in STAGES:
        magic, offset = _read_exact(data, offset, len(MAGIC), "magic")
        if magic != MAGIC:
            raise ValueError(f"wrong geometry magic at byte {offset - len(MAGIC)}")
        stage_bytes, offset = _read_exact(data, offset, len(expected_stage), "stage")
        try:
            stage = stage_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("stage is not ASCII") from exc
        if stage != expected_stage:
            raise ValueError(f"expected stage {expected_stage}, found {stage!r}")

        scalar_data, offset = _read_exact(data, offset, 36, "scalar header")
        timestep, rkstep, hybrid, dtm, dt, dx, dy, gravity, p_top = struct.unpack(">3i6f", scalar_data)
        bounds_data, offset = _read_exact(data, offset, 48, "bounds")
        bounds_values = struct.unpack(">12i", bounds_data)
        bounds = dict(zip(BOUND_NAMES, bounds_values, strict=True))
        extent_data, offset = _read_exact(data, offset, 60, "array extents")
        ext = struct.unpack(">15i", extent_data)
        if any(n <= 0 for n in ext):
            raise ValueError("array extents must be positive")

        shapes = (
            ext[0:2], ext[2:4], ext[4:6], (ext[6],), (ext[7],),
            (ext[8],), (ext[9],), (ext[10],), ext[11:13], ext[13:15],
        )
        arrays = {}
        for name, shape in zip(ARRAY_NAMES, shapes, strict=True):
            count = math.prod(shape)
            raw, offset = _read_exact(data, offset, count * 4, name)
            values = np.frombuffer(raw, dtype=">f4").astype(np.float64)
            array = values.reshape(shape, order="F")
            if not np.isfinite(array).all():
                raise ValueError(f"{name} contains nonfinite values")
            arrays[name] = array

        ims, ime = bounds["ims"], bounds["ime"]
        jms, jme = bounds["jms"], bounds["jme"]
        kms, kme = bounds["kms"], bounds["kme"]
        its, ite = bounds["its"], bounds["ite"]
        jts, jte = bounds["jts"], bounds["jte"]
        kts, kte = bounds["kts"], bounds["kte"]
        if not (ims <= ime and jms <= jme and kms <= kme):
            raise ValueError("invalid inclusive memory bounds")
        if not (ims <= its <= ite <= ime and jms <= jts <= jte <= jme and kms <= kts <= kte <= kme):
            raise ValueError("solve_em tile is outside memory bounds")
        horizontal_shape = (ime - ims + 1, jme - jms + 1)
        if any(arrays[name].shape != horizontal_shape for name in ("mu1", "mu2", "mub", "msftx", "msfty")):
            raise ValueError("horizontal array shape disagrees with inclusive memory bounds")
        vertical_shape = (kme - kms + 1,)
        if any(arrays[name].shape != vertical_shape for name in ("c1h", "c2h", "c3f", "c4f", "dnw")):
            raise ValueError("vertical coefficient shape disagrees with inclusive bounds")
        scalars = (dtm, dt, dx, dy, gravity, p_top)
        if timestep < 1 or hybrid < 1 or not all(math.isfinite(x) and x > 0 for x in scalars):
            raise ValueError("invalid timestep, hybrid option, or scalar geometry header")
        records.append({
            "stage": stage, "timestep": timestep, "rkstep": rkstep,
            "hybrid_opt": hybrid, "dtm_s": dtm, "dt_s": dt,
            "dx_m": dx, "dy_m": dy, "gravity_m_s2": gravity,
            "p_top_pa": p_top, "bounds": bounds, "extents": ext,
            "arrays": arrays,
        })
    if offset != len(data):
        raise ValueError(f"unexpected trailing bytes: {len(data) - offset}")
    pre, post = records
    if (pre["timestep"], pre["rkstep"], pre["hybrid_opt"], pre["bounds"], pre["extents"]) != (
        post["timestep"], post["rkstep"], post["hybrid_opt"], post["bounds"], post["extents"]
    ):
        raise ValueError("pre/post geometry headers differ")
    scalar_names = ("dtm_s", "dt_s", "dx_m", "dy_m", "gravity_m_s2", "p_top_pa")
    if any(pre[name] != post[name] for name in scalar_names):
        raise ValueError("pre/post geometry scalar metadata differ")
    for name in ARRAY_NAMES:
        if not np.array_equal(pre["arrays"][name], post["arrays"][name]):
            raise ValueError(f"geometry array changed across microphysics call: {name}")
    return records


def _load_trace_reader():
    path = Path(__file__).with_name("native_kdm6_trace.py")
    spec = importlib.util.spec_from_file_location("cloudbal_native_kdm6_trace", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load KDM6 trace reader at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_dump


def _bound_header_match(geometry: dict[str, Any], kdm: dict[str, Any]) -> None:
    bounds = geometry["bounds"]
    kb = kdm["bounds"]
    for key in ("ims", "ime", "jms", "jme", "kms", "kme", "kts", "kte"):
        if kb[key] != bounds[key]:
            raise ValueError(f"KDM6/geometry bound mismatch: {key}")
    for lo, hi in (("its", "ite"), ("jts", "jte"), ("kts", "kte")):
        if kb[lo] < bounds[lo] or kb[hi] > bounds[hi]:
            raise ValueError(f"KDM6 active tile outside solve_em tile: {lo}/{hi}")
    if kdm["itimestep"] != geometry["timestep"]:
        raise ValueError("KDM6/geometry timestep mismatch")
    # In the selected solve_em source, microphysics_driver receives DT=dtm.
    # KDM6's first-call trace records its incoming DELT argument as dt_s.
    # Bind those two source arguments; geometry dt_s is grid%dt metadata and
    # is not part of this call contract.
    if kdm["params"]["dt_s"] != geometry["dtm_s"]:
        raise ValueError("KDM6/geometry call-duration mismatch: KDM6 DELT != host DT=dtm")
    expected = [kb["ite"] - kb["its"] + 1, kb["jte"] - kb["jts"] + 1, kb["kte"] - kb["kts"] + 1]
    if kdm["active_shape_xyz"] != expected:
        raise ValueError("KDM6 active shape/header mismatch")


def _require_finite_positive(values: np.ndarray, label: str) -> None:
    if not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError(f"{label} must be finite and positive")


def audit(geometry_path: Path, pre_path: Path, post_path: Path, receipt_path: Path,
          expected_executable_sha256: str | None = None,
          layer_tolerance_pa: float = 0.01,
          column_tolerance_pa: float = 0.01) -> dict[str, Any]:
    if (not math.isfinite(layer_tolerance_pa) or layer_tolerance_pa <= 0
            or not math.isfinite(column_tolerance_pa) or column_tolerance_pa <= 0):
        raise ValueError("pressure identity tolerances must be finite and positive")
    run_root = receipt_path.parent
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("returncode") != 0 or receipt.get("input_integrity") != "PASS" or receipt.get("output_isolation") != "PASS":
        raise ValueError("run receipt is not a successful isolated execution")
    output_rows = {row["path"]: row for row in receipt.get("outputs", [])}
    input_rows = {Path(row["path"]).name: row for row in receipt.get("inputs", [])}
    capture_hashes = {}
    for path in (geometry_path, pre_path, post_path):
        try:
            relative = path.resolve().relative_to(run_root.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError(f"capture is outside receipt run root: {path}") from exc
        row = output_rows.get(relative)
        if row is None:
            raise ValueError(f"capture is not a declared output: {relative}")
        if sha256(path) != row.get("sha256") or path.stat().st_nlink != 1:
            raise ValueError(f"capture hash/link does not match receipt: {relative}")
        capture_hashes[relative] = row["sha256"]
    executable = run_root / "wrf.exe"
    exe_row = input_rows.get("wrf.exe")
    if (exe_row is None or Path(exe_row["path"]).resolve() != executable.resolve()
            or exe_row.get("sha256_before") != exe_row.get("sha256_after")
            or executable.stat().st_nlink != 1
            or sha256(executable) != exe_row.get("sha256_before")):
        raise ValueError("receipt does not bind the run-root executable")
    if expected_executable_sha256 and exe_row["sha256_before"] != expected_executable_sha256:
        raise ValueError("executable hash differs from requested identity")

    records = parse_geometry(geometry_path.read_bytes())
    pre_record, post_record = records
    kdm_reader = _load_trace_reader()
    kdm_pre, kdm_post = kdm_reader(pre_path), kdm_reader(post_path)
    if kdm_pre["stage"] != 1 or kdm_post["stage"] != 2:
        raise ValueError("KDM6 trace stages must be pre=1 and post=2")
    if kdm_pre["bounds"] != kdm_post["bounds"] or kdm_pre["params"] != kdm_post["params"]:
        raise ValueError("KDM6 pre/post headers differ")
    _bound_header_match(pre_record, kdm_pre)
    _bound_header_match(post_record, kdm_post)

    b = pre_record["bounds"]
    kb = kdm_pre["bounds"]
    arrays = pre_record["arrays"]
    i0, i1 = kb["its"] - b["ims"], kb["ite"] - b["ims"] + 1
    j0, j1 = kb["jts"] - b["jms"], kb["jte"] - b["jms"] + 1
    mu = arrays["mu2"][i0:i1, j0:j1].T
    mub = arrays["mub"][i0:i1, j0:j1].T
    msftx = arrays["msftx"][i0:i1, j0:j1].T
    msfty = arrays["msfty"][i0:i1, j0:j1].T
    if np.any(msftx <= 0) or np.any(msfty <= 0):
        raise ValueError("nonpositive active map factor")
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        area = pre_record["dx_m"] * pre_record["dy_m"] / (msftx * msfty)
    _require_finite_positive(area, "active map area")
    layers = np.arange(kb["kts"], kb["kte"] + 1) - b["kms"]
    c1, c2 = arrays["c1h"][layers], arrays["c2h"][layers]
    dnw = arrays["dnw"][layers]

    # Source equation: dp_k = -[C1H_k*(MU2+MUB)+C2H_k]*DNW_k.
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        dp = -(c1[:, None, None] * (mu[None, :, :] + mub[None, :, :]) + c2[:, None, None]) * dnw[:, None, None]
    if not np.isfinite(dp).all() or np.any(dp <= 0):
        raise ValueError("nonpositive or nonfinite active hybrid layer thickness")
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        hybrid_mass = dp * area[None, :, :] / pre_record["gravity_m_s2"]
    _require_finite_positive(hybrid_mass, "hybrid dry-mass measure")
    hybrid_mass_total = float(hybrid_mass.sum())
    if not math.isfinite(hybrid_mass_total) or hybrid_mass_total <= 0:
        raise ValueError("hybrid dry-mass total must be finite and positive")

    c3f = arrays["c3f"]
    c4f = arrays["c4f"]
    interfaces = c3f[layers, None, None] * (mu[None, :, :] + mub[None, :, :]) + c4f[layers, None, None] + pre_record["p_top_pa"]
    next_layer = layers + 1
    if np.max(next_layer) >= len(c3f) or np.max(next_layer) >= len(c4f):
        raise ValueError("interface coefficients do not cover active layers")
    interfaces_next = c3f[next_layer, None, None] * (mu[None, :, :] + mub[None, :, :]) + c4f[next_layer, None, None] + pre_record["p_top_pa"]
    ref_dp = interfaces - interfaces_next
    layer_residual = float(np.max(np.abs(dp - ref_dp)))
    column_residual = float(np.max(np.abs(dp.sum(axis=0) - mu - mub)))
    if layer_residual > layer_tolerance_pa or column_residual > column_tolerance_pa:
        raise ValueError("hybrid layer/column pressure identity exceeds tolerance")

    den = kdm_pre["fields"]["DEN"]
    delz = kdm_pre["fields"]["DELZ"]
    dp_kji = np.transpose(dp, (1, 0, 2))
    if den.shape != dp_kji.shape or delz.shape != dp_kji.shape:
        raise ValueError("KDM DEN/DELZ shape does not match active hybrid layers")
    if not np.isfinite(den).all() or not np.isfinite(delz).all() or np.any(den <= 0) or np.any(delz <= 0):
        raise ValueError("KDM DEN/DELZ is nonpositive or nonfinite")
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        den_mass = den * delz * area[:, None, :]
    _require_finite_positive(den_mass, "DEN*DELZ area diagnostic")
    den_mass_total = float(den_mass.sum())
    if not math.isfinite(den_mass_total) or den_mass_total <= 0:
        raise ValueError("DEN*DELZ area diagnostic total must be finite and positive")
    return {
        "schema": "pr63_same_call_geometry_audit_v1",
        "audit_source_sha256": sha256(Path(__file__)),
        "receipt_sha256": sha256(receipt_path),
        "receipt_status": {key: receipt.get(key) for key in ("returncode", "input_integrity", "output_isolation")},
        "executable_sha256": exe_row["sha256_before"],
        "capture_hashes": capture_hashes,
        "geometry_records": [{key: value for key, value in row.items() if key != "arrays"} for row in records],
        "geometry_array_shapes": {key: list(value.shape) for key, value in arrays.items()},
        "geometry_arrays_finite": True,
        "pre_post_geometry_arrays_equal": {name: bool(np.array_equal(records[0]["arrays"][name], records[1]["arrays"][name])) for name in ARRAY_NAMES},
        "kdm6_memory_bounds_match_geometry": True,
        "kdm6_active_tile_within_solve_em_tile": True,
        "kdm6_active_shape_xyz": kdm_pre["active_shape_xyz"],
        "kdm6_timestep": kdm_pre["itimestep"],
        "call_duration_identity": {
            "host_argument": "solve_em dtm passed as microphysics_driver DT",
            "kdm6_argument": "KDM6 delt recorded as trace dt_s",
            "host_dtm_s": pre_record["dtm_s"],
            "kdm6_delt_s": kdm_pre["params"]["dt_s"],
            "matched": True,
            "grid_dt_s_metadata": pre_record["dt_s"],
            "grid_dt_part_of_identity": False,
        },
        "layer_dp_pa_minmax": [float(dp.min()), float(dp.max())],
        "max_layer_to_interface_dp_difference_pa": layer_residual,
        "max_column_dp_to_mu2_mub_difference_pa": column_residual,
        "pressure_identity_tolerances_pa": {"layer": layer_tolerance_pa, "column": column_tolerance_pa},
        "mapped_hybrid_dry_mass_kg": hybrid_mass_total,
        "DEN_DELZ_area_mass_diagnostic_kg": den_mass_total,
        "DEN_DELZ_area_relative_difference_vs_hybrid_mass": float(den_mass_total / hybrid_mass_total - 1.0),
        "source_equations": {
            "layer_pressure": "dp_k = -[C1H_k*(MU2+MUB)+C2H_k]*DNW_k",
            "hybrid_dry_mass": "sum(dp_k*DX*DY/(MSFTX*MSFTY*g))",
            "alternative_diagnostic_only": "sum(DEN*DELZ*DX*DY/(MSFTX*MSFTY)); not a closed mass budget",
        },
        "identity_bound_interpretation": "The 0.01 Pa defaults are fixed numerical research-audit bounds for these recorded geometry identities. They are not physical tolerances, a proof of floating-point error bounds, or a criterion for scientific closure.",
        "units_and_limits": "Units are inferred from source equations; PR63GEO2 has no unit strings. This checks same-call geometry consistency only. DEN*DELZ area mass is diagnostic and is not forced to match hybrid mass. One-rank/tile/timestep capture only; no source/boundary budget or physical approval.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry", type=Path)
    parser.add_argument("kdm_pre", type=Path)
    parser.add_argument("kdm_post", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--expected-executable-sha256")
    parser.add_argument("--layer-tolerance-pa", type=float, default=0.01,
                        help="positive finite numerical research-audit bound in Pa (not a physical tolerance)")
    parser.add_argument("--column-tolerance-pa", type=float, default=0.01,
                        help="positive finite numerical research-audit bound in Pa (not a physical tolerance)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.geometry, args.kdm_pre, args.kdm_post, args.receipt,
                   args.expected_executable_sha256, args.layer_tolerance_pa,
                   args.column_tolerance_pa)
    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
