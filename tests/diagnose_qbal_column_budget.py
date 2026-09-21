#!/usr/bin/env python3
"""Retrospective surface-volume connection; unresolved fluxes stay explicit."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from netCDF4 import Dataset
from diagnose_qbal_sloping_faces import field, nav, sha, validate_product_time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    common = ("snapshot", "static", "lsx", "lw3", "frame-evidence")
    for name in common + ("lsx-before", "lsx-after", "output-dir"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--lco", type=Path)
    parser.add_argument("--top-source", choices=("lco", "lw3"), required=True)
    parser.add_argument("--epoch", type=int, required=True)
    parser.add_argument("--interval-seconds", type=int, required=True)
    parser.add_argument("--radius-m", type=float, required=True)
    parser.add_argument("--retrospective", action="store_true", required=True)
    args = parser.parse_args()
    if args.top_source == "lco" and args.lco is None:
        parser.error("--top-source lco requires --lco")
    if args.top_source == "lw3" and args.lco is not None:
        parser.error("--lco is not used with --top-source lw3")
    if args.interval_seconds <= 0:
        raise ValueError("positive centered interval required")
    repo = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    files = {name.replace("-", "_"): getattr(args, name.replace("-", "_")).resolve()
             for name in common + ("lsx-before", "lsx-after") + (("lco",) if args.top_source == "lco" else ())}
    pins = {name: sha(path) for name, path in files.items()}
    with Dataset(files["lsx"]) as nc:
        nc.set_auto_maskandscale(False)
        validate_product_time(nc, args.epoch, "central input")
        navigation, center = nav(nc), field(nc, "ps")
    pair = []
    epochs = [args.epoch-args.interval_seconds, args.epoch+args.interval_seconds]
    for name, epoch in zip(("lsx_before", "lsx_after"), epochs):
        with Dataset(files[name]) as nc:
            nc.set_auto_maskandscale(False)
            validate_product_time(nc, epoch, name)
            if nav(nc) != navigation or nc["ps"].units != "pascals":
                raise ValueError("surface time pair geometry/units mismatch")
            value = field(nc, "ps")
            if value.shape != center.shape:
                raise ValueError("surface time pair shape mismatch")
            pair.append(value)
    # Explicit file-field alternatives, neither an authorized top boundary.
    # Missing samples stay NaN; finite top pressure never implies zero flux.
    top_variable, top_units = {"lco": ("com", "Pascals / second"),
                               "lw3": ("om", "pascals / second")}[args.top_source]
    with Dataset(files[args.top_source]) as nc:
        nc.set_auto_maskandscale(False)
        validate_product_time(nc, args.epoch, "central input")
        if nav(nc) != navigation or nc["level"].units != "hectopascals":
            raise ValueError("top source geometry/pressure units mismatch")
        levels = np.asarray(nc["level"][:], dtype=float)*100
        with Dataset(files["lw3"]) as winds:
            pressure = np.asarray(winds["level"][:], dtype=float)*100
        if not np.array_equal(levels, pressure) or not np.isfinite(levels).all():
            raise ValueError("top source/LW3 pressure levels differ")
        pt = float(levels.min())
        if np.count_nonzero(levels == pt) != 1:
            raise ValueError("ambiguous finite top")
        var = nc[top_variable]
        if var.units != top_units or var.shape != (1, len(levels), *center.shape):
            raise ValueError("top omega units/shape mismatch")
        top = np.asarray(var[0, np.argmin(levels)], dtype=float)
        valid = np.isfinite(top) & (top != var._FillValue)
        valid &= (top >= var.valid_range[0]) & (top <= var.valid_range[1])
        if "missing_value" in var.ncattrs():
            valid &= top != var.missing_value
        top = np.where(valid, top, np.nan)
    command = [sys.executable, str(repo/"tests/diagnose_qbal_sloping_faces.py")]
    for name in common:
        command += ["--"+name, str(files[name.replace("-", "_")])]
    command += ["--epoch", str(args.epoch), "--radius-m", str(args.radius_m),
                "--output-dir", str(output/"sloping")]
    with (output/"sloping.log").open("w") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    with np.load(output/"sloping/arrays.npz") as arrays:
        xy, tri, incidence, covered, uncovered = [arrays[name] for name in
            ("xy", "triangles", "incidence", "edge_flux", "uncovered")]
    nn, nt, ne = len(xy), len(tri), len(covered)
    prepared = output/"prepared.bin"
    with prepared.open("wb") as stream:
        stream.write(np.array([nn, nt, ne], dtype="<i4").tobytes())
        stream.write(np.array(epochs, dtype="<i8").tobytes())
        stream.write(np.array([pt], dtype="<f8").tobytes())
        for value in (xy, pair[0], pair[1], center, top):
            stream.write(np.asarray(value, dtype="<f8").tobytes())
        for value in (valid, tri+1, incidence):
            stream.write(np.asarray(value, dtype="<i4").tobytes())
        for value in (covered, uncovered):
            stream.write(np.asarray(value, dtype="<f8").tobytes())
    sources = ["qbal_physical_boundary.f90", "qbal_pressure_flux.f90", "qbal_sloping_geometry.f90",
               "qbal_column_budget.f90", "diagnose_qbal_column_budget.f90"]
    script = output/"run.sh"
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
      "$repo/tests/qbal_sloping_geometry.f90" "$repo/tests/qbal_column_budget.f90" \\
      "$repo/tests/diagnose_qbal_column_budget.f90" -o diagnose
    ./diagnose "$out/prepared.bin" result.bin > result.txt
  )
done
''')
    with (output/"intel.log").open("w") as log:
        subprocess.run(["bash", str(script), str(repo), str(output)], stdout=log, stderr=subprocess.STDOUT, check=True)
    results = [np.fromfile(output/level/"result.bin", dtype="<f8").reshape(-1, 8)
               for level in ("O0", "O2")]
    top_known = np.all(valid.ravel()[tri], axis=1)
    complete = top_known & np.all(uncovered[np.abs(incidence)-1] == 0, axis=1)
    for value in results:
        if value.shape != (nt, 8) or not np.isfinite(value[:, :5]).all() or not np.isfinite(value[:, 6]).all():
            raise ValueError("invalid computed column terms")
        if not np.array_equal(np.isfinite(value[:, 5]), top_known) or not np.array_equal(np.isfinite(value[:, 7]), complete):
            raise ValueError("unknown term or incomplete residual was filled")
        if np.any(np.abs(value[:, 1]-value[:, 2]) > value[:, 3]):
            raise ValueError("surface flux / volume rate mismatch")
    # Compare flux arithmetic on uncancelled incident terms, including the
    # separate volume-subtraction allowance; never scale by the subtotal.
    scale = (abs(results[0][:, 1]) + abs(covered[np.abs(incidence)-1]).sum(axis=1)
             + np.nan_to_num(abs(results[0][:, 5]), nan=0.0))
    allowance = 512*np.finfo(float).eps*scale + results[0][:, 3] + results[1][:, 3]
    if not np.allclose(results[0][:, 0], results[1][:, 0], rtol=256*np.finfo(float).eps, atol=0):
        raise ValueError("optimization area mismatch")
    for column in (1, 2, 4, 5, 6, 7):
        known = np.isfinite(results[0][:, column])
        if np.any(abs(results[0][known, column]-results[1][known, column]) > allowance[known]):
            raise ValueError("optimization flux mismatch")
    value = results[0]
    np.savez(output/"terms.npz", area=value[:, 0], surface=value[:, 1], volume_rate=value[:, 2],
             arithmetic_bound=value[:, 3], covered_sides=value[:, 4], top=value[:, 5],
             known_subtotal=value[:, 6], residual=value[:, 7], top_known=top_known, complete=complete)
    if any(sha(files[name]) != h for name, h in pins.items()):
        raise ValueError("input changed during replay")
    report = {"status": "RETROSPECTIVE_SURFACE_VOLUME_CONNECTED / INCOMPLETE_COLUMN_FLUX",
              "input_sha256": pins, "input_paths": {k: str(v) for k, v in files.items()},
              "epochs": epochs, "central_epoch": args.epoch, "top_pressure_pa": pt,
              "time_mean": "Retrospective two-sided secant; not instantaneous or available at central analysis time.",
              "transport_sampling": "Central-time samples combined with interval-mean surface tendency; temporal representation remains unresolved.",
              "top_source": args.top_source, "top_variable": top_variable,
              "top_role": "Conditional file-field integral only; not an authorized physical boundary.",
              "columns": nt, "top_valid_nodes": int(valid.sum()), "top_known_columns": int(top_known.sum()),
              "complete_columns": int(complete.sum()), "maximum_surface_pa_per_s": float(np.max(abs(value[:, 1]/value[:, 0]))),
              "maximum_volume_rate_difference": float(np.max(abs(value[:, 1]-value[:, 2]))),
              "maximum_known_subtotal_pa_per_s": float(np.max(abs(value[:, 6]/value[:, 0]))),
              "complete_physical_residual": None, "production_authority": False,
              "source_sha256": {n: sha(repo/"tests"/n) for n in sources+[Path(__file__).name, "intel_toolchain.sh"]},
              "artifact_sha256": {n: sha(output/n) for n in ["prepared.bin", "terms.npz", "sloping/report.json", "O0/result.bin", "O2/result.bin"]}}
    (output/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("input_paths", "input_sha256", "source_sha256", "artifact_sha256")}, indent=2))


if __name__ == "__main__":
    main()
