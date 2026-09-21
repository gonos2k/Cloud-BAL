#!/usr/bin/env python3
"""Bind actual static/LSX/LW3 files to a declared sloping pressure mesh."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from netCDF4 import Dataset
from diagnose_qbal_boundary import read_snapshot


TIME_UNITS = "seconds since (1970-1-1 00:00:00.0)"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_product_time(nc, expected_epoch, product_name="product"):
    """Validate and return a product's exact integer valid time.

    This follows the existing LAPSPREP input-time contract.  In particular,
    the value is checked before conversion to ``int`` so fractional seconds
    cannot be silently truncated.
    """
    label = f"{product_name} valtime"
    if "valtime" not in nc.variables:
        raise ValueError(f"{label}: missing variable")
    var = nc.variables["valtime"]
    if var.dtype != np.dtype("float64") or var.ndim != 1:
        raise ValueError(f"{label}: scalar double required")
    if var.dimensions != ("record",):
        raise ValueError(f"{label}: record dimension required")
    if "record" not in nc.dimensions or len(nc.dimensions["record"]) != 1:
        raise ValueError(f"{label}: single record required")
    units = getattr(var, "units", None)
    if units is None:
        raise ValueError(f"{label}: missing units")
    if not isinstance(units, str) or units.rstrip() != TIME_UNITS:
        raise ValueError(f"{label}: invalid units")

    var.set_auto_maskandscale(False)
    values = np.asarray(var[:], dtype=np.float64)
    if values.shape != (1,):
        raise ValueError(f"{label}: single record required")
    value = float(values[0])
    if not np.isfinite(value):
        raise ValueError(f"{label}: nonfinite")
    if value != np.rint(value):
        raise ValueError(f"{label}: fractional seconds")

    for attribute_name in ("_FillValue", "missing_value"):
        if attribute_name not in var.ncattrs():
            continue
        attribute = np.asarray(var.getncattr(attribute_name))
        if attribute.shape != () or attribute.dtype != np.dtype("float64"):
            raise ValueError(f"{label}: invalid missing attribute")
        missing = float(attribute)
        if np.isfinite(missing) and value == missing:
            raise ValueError(f"{label}: missing value")

    epoch = int(value)
    if epoch != expected_epoch:
        raise ValueError(f"{product_name} time mismatch")
    return epoch


def field(nc, name):
    var = nc[name]
    values = np.asarray(var[:], dtype=np.float64).squeeze()
    if not np.isfinite(values).all() or np.any(values == var._FillValue):
        raise ValueError(f"invalid {name}")
    if np.any(values < var.valid_range[0]) or np.any(values > var.valid_range[1]):
        raise ValueError(f"{name} outside declared range")
    return values


def nav(nc):
    return {key: np.asarray(nc[key][:]).tolist()
            for key in ("Nx", "Ny", "La1", "Lo1", "LoV", "Latin1", "Latin2")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "static", "lsx", "lw3", "frame-evidence", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--radius-m", type=float, required=True)
    parser.add_argument("--epoch", type=int, required=True)
    args = parser.parse_args()
    files = {name: getattr(args, name).resolve() for name in
             ("snapshot", "static", "lsx", "lw3", "frame_evidence")}
    pins = {name: sha(path) for name, path in files.items()}
    # Explicit source binding, not an inferred frame from variable names.
    evidence = files["frame_evidence"].read_text().lower().replace(" ", "")
    if any(f"parameter({flag}=.true.)" not in evidence
           for flag in ("l_grid_north", "l_grid_north_anal", "l_grid_north_out")):
        raise ValueError("this replay requires the producer's grid-north output source contract")
    snapshot = read_snapshot(files["snapshot"])
    with Dataset(files["static"]) as nc:
        nc.set_auto_maskandscale(False)
        lat, lon, navigation = field(nc, "lat"), field(nc, "lon"), nav(nc)
    with Dataset(files["lsx"]) as nc:
        nc.set_auto_maskandscale(False)
        validate_product_time(nc, args.epoch, "LSX")
        if nav(nc) != navigation:
            raise ValueError("LSX time/navigation mismatch")
        if nc["ps"].units != "pascals":
            raise ValueError("LSX pressure units mismatch")
        ps = field(nc, "ps")
    with Dataset(files["lw3"]) as nc:
        nc.set_auto_maskandscale(False)
        validate_product_time(nc, args.epoch, "LW3")
        if nav(nc) != navigation:
            raise ValueError("LW3 time/navigation mismatch")
        if nc["level"].units != "hectopascals":
            raise ValueError("LW3 pressure units mismatch")
        if any(nc[n].units.strip() != "meters / second" for n in ("u3", "v3")):
            raise ValueError("LW3 velocity units mismatch")
        pressure = np.asarray(nc["level"][:], dtype=float)[::-1] * 100
        u, v = field(nc, "u3")[::-1], field(nc, "v3")[::-1]
    if not np.array_equal(ps.T, snapshot.ps) or not np.array_equal(pressure, snapshot.p):
        raise ValueError("pressure/surface does not match pinned legacy case")
    ny, nx = ps.shape
    if lat.shape != ps.shape or lon.shape != ps.shape or u.shape != (len(pressure), ny, nx) or v.shape != u.shape:
        raise ValueError("input shapes differ")
    node = np.arange(nx * ny).reshape(ny, nx)
    triangles = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a, b, c, d = node[j, i], node[j, i+1], node[j+1, i+1], node[j+1, i]
            triangles.extend(((a, b, c), (a, c, d)))
    triangles = np.asarray(triangles, dtype=np.int32)
    edges, lookup, incidence = [], {}, []
    for triangle in triangles:
        row = []
        for a, b in zip(triangle, np.roll(triangle, -1)):
            key = (min(a, b), max(a, b))
            if key not in lookup:
                lookup[key] = len(edges) + 1
                edges.append(key)
            row.append(lookup[key] if a < b else -lookup[key])
        incidence.append(row)
    edges, incidence = np.asarray(edges, dtype=np.int32), np.asarray(incidence, dtype=np.int32)
    phi1, phi2 = [np.deg2rad(navigation[name][0]) for name in ("Latin1", "Latin2")]
    if not (0 < phi1 < phi2 < np.pi/2) or not np.isfinite(args.radius_m) or not 0 < args.radius_m <= 1.e8:
        raise ValueError("unsupported secant projection or sphere radius")
    if np.any(pressure <= 0) or np.any(np.diff(pressure) >= 0):
        raise ValueError("pressure levels must decrease strictly")
    cone = np.log(np.cos(phi1)/np.cos(phi2)) / np.log(np.tan(np.pi/4+phi2/2)/np.tan(np.pi/4+phi1/2))
    orientation = np.deg2rad(navigation["LoV"][0])
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=False)
    parameters = np.array([np.deg2rad(38.), orientation, args.radius_m, cone, orientation], dtype="<f8")
    prepared = output / "prepared.bin"
    with prepared.open("wb") as stream:
        stream.write(np.array([nx*ny, len(pressure), len(triangles), len(edges)], dtype="<i4").tobytes())
        stream.write(parameters.tobytes())
        for value in (np.deg2rad(lat), np.deg2rad(lon), ps, pressure,
                      u.reshape(len(pressure), -1).T, v.reshape(len(pressure), -1).T):
            stream.write(np.asarray(value, dtype="<f8").tobytes())
        for value in (triangles+1, edges+1, incidence):
            stream.write(np.asarray(value, dtype="<i4").tobytes())
    repo = Path(__file__).resolve().parents[1]
    sources = ["qbal_physical_boundary.f90", "qbal_pressure_flux.f90", "qbal_sloping_geometry.f90",
               "diagnose_qbal_sloping_faces.f90"]
    script = output / "run.sh"
    script.write_text('''#!/usr/bin/env bash
set -euo pipefail
repo=$1
out=$2
. "$repo/tests/intel_toolchain.sh"
for level in O0 O2; do
  mkdir "$out/$level"
  if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  (
    cd "$out/$level"
    "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian \\
      "$repo/tests/qbal_physical_boundary.f90" "$repo/tests/qbal_pressure_flux.f90" \\
      "$repo/tests/qbal_sloping_geometry.f90" "$repo/tests/diagnose_qbal_sloping_faces.f90" -o diagnose
    ./diagnose "$out/prepared.bin" result.bin > result.txt
  )
done

''')
    with (output / "intel.log").open("w") as log:
        subprocess.run(["bash", str(script), str(repo), str(output)], stdout=log, stderr=subprocess.STDOUT, check=True)
    raw = np.fromfile(output / "O0/result.bin", dtype="<f8")
    counts = [2*nx*ny, len(edges), len(edges), len(triangles), 2*len(triangles), len(triangles)]
    arrays = np.split(raw, np.cumsum(counts)[:-1])
    if len(raw) != sum(counts):
        raise ValueError("output extent mismatch")
    xy = arrays[0].reshape(-1, 2)
    other = np.fromfile(output / "O2/result.bin", dtype="<f8")
    if other.shape != raw.shape or not np.isfinite(other).all() or not np.isfinite(raw).all():
        raise ValueError("invalid optimization replay output")
    other_arrays = np.split(other, np.cumsum(counts)[:-1])
    eps = np.finfo(float).eps
    edge_xy = xy[edges]
    metric_size = np.abs(edge_xy[:, 1]-edge_xy[:, 0]).sum(axis=1)
    speed = np.hypot(u, v).max(axis=0).ravel()
    scale = np.maximum(np.cos(parameters[0])/np.cos(np.deg2rad(lat)),
                       np.cos(np.deg2rad(lat))/np.cos(parameters[0])).ravel()
    flux_scale = metric_size * (speed*scale)[edges].max(axis=1) * (ps.ravel()[edges].max(axis=1)-pressure[-1])
    flux_bound = 256*eps*(len(pressure)+1)*flux_scale
    if np.any(np.abs(arrays[1]-other_arrays[1]) > flux_bound):
        raise ValueError("wind transport optimization difference exceeds arithmetic scale")
    if not np.allclose(arrays[0], other_arrays[0], rtol=0, atol=256*eps*args.radius_m):
        raise ValueError("chart coordinates differ beyond arithmetic scale")
    if not np.allclose(arrays[2], other_arrays[2], rtol=0, atol=256*eps*ps.max()):
        raise ValueError("uncovered intervals differ beyond arithmetic scale")
    if not np.allclose(arrays[3], other_arrays[3], rtol=256*eps, atol=0):
        raise ValueError("cell volumes differ beyond arithmetic scale")
    if np.max(other_arrays[4]) > 128*eps:
        raise ValueError("O2 cell closure failed")
    quads = np.stack([node[:-1, :-1].ravel(), node[:-1, 1:].ravel(),
                      node[1:, 1:].ravel(), node[1:, :-1].ravel()], axis=1)
    quad_xy = xy[quads]
    turns = np.roll(quad_xy, -1, axis=1)-quad_xy
    if np.any(np.cross(turns, np.roll(turns, -1, axis=1)) <= 0):
        raise ValueError("nonconvex/degenerate horizontal quad")
    coords = xy[triangles]
    area = np.abs(np.cross(coords[:, 1]-coords[:, 0], coords[:, 2]-coords[:, 0]))/2
    lateral_bound = (flux_bound[np.abs(incidence)-1].sum(axis=1) +
                     256*eps*flux_scale[np.abs(incidence)-1].sum(axis=1))/area
    if np.any(np.abs(arrays[5]-other_arrays[5]) > lateral_bound):
        raise ValueError("partial lateral transport differs beyond arithmetic scale")
    np.savez(output / "arrays.npz", xy=xy, edge_flux=arrays[1], uncovered=arrays[2],
             volume=arrays[3], closure=arrays[4].reshape(-1, 2), partial_lateral=arrays[5],
             triangles=triangles, edges=edges, incidence=incidence)
    assert all(sha(files[name]) == value for name, value in pins.items()), "input changed"
    report = {"status": "RECONSTRUCTED_GEOMETRY_AND_CONDITIONAL_COVERED_TRANSPORT", "input_sha256": pins,
              "input_paths": {name: str(path) for name, path in files.items()},
              "source_sha256": {name: sha(repo/"tests"/name) for name in sources+[Path(__file__).name, "intel_toolchain.sh", "diagnose_qbal_boundary.py"]},
              "prepared_sha256": sha(prepared), "result_sha256": {level: sha(output/level/"result.bin") for level in ("O0", "O2")},
              "intel_O0_O2_identical": bool(np.array_equal(raw, other)),
              "intel_O0_O2_arithmetic_comparison": "PASS_SCOPED",
              "maximum_O0_O2_flux_difference": float(np.max(np.abs(arrays[1]-other_arrays[1]))),
              "radius_m": args.radius_m,
              "wind_frame": "CONDITIONAL: Lambert grid north per producer parameter; LW3 lacks frame metadata and writer comment conflicts; historical executable identity not revalidated",
              "summary": (output/"O0/result.txt").read_text(),
              "complete_physical_residual": None, "production_authority": False,
              "limits": ["Piecewise planar PS in an equal-area spherical chart, not native geometry.",
                         "Full triangular columns between grid centers; no new vertical layer mesh or state remap.",
                         "Only jointly above-ground pressure wind samples; uncovered near-surface flux remains unknown.",
                         "No surface velocity, pressure tendency, top omega, covariance, correction or balance candidate inferred."]}
    (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(report["summary"])


if __name__ == "__main__":
    main()
