#!/usr/bin/env python3
"""Conditional endpoint-profile transport on an input-selected real face.

Reuses a hash-pinned PR39 prepared replay. All fitting, wind conversion and
transport calculations run in Fortran under the pinned Intel O0/O2 profiles.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import numpy as np

from audit_qbal_profile_domain import audit_domain, read_prepared, sha256


def write_face(path, case, arrays, record):
    """Select existing data only; declare sensitivity variances before fitting."""
    edge = record["edge_index_zero_based"]
    nodes = np.asarray(record["node_indices_zero_based"])
    q = record["cap_knot_index_zero_based_by_time"][1]
    p = case["pressure"][q:]
    if len(p) < 3 or np.min(arrays["p10"][1, nodes]) <= p[1] + 0.001 or p[-1] >= p[1] - 0.001:
        raise ValueError("study partition must lie between finite top and both samples")
    raw_wind = np.stack((case["u"][1, nodes, q:].T, case["v"][1, nodes, q:].T), axis=1)
    raw_sample = np.stack((case["surface_u"][1, nodes], case["surface_v"][1, nodes]))
    incidence = case["incidence"]
    plus = np.flatnonzero(np.any(incidence == edge + 1, axis=1))
    minus = np.flatnonzero(np.any(incidence == -(edge + 1), axis=1))
    if len(plus) != 1 or len(minus) != 1 or plus[0] == minus[0]:
        raise ValueError("selected face must have two distinct opposite incident cells")
    triangles = case["triangles"][[plus[0], minus[0]]]
    ratios = np.array([0.25, 1.0, 4.0])
    variance = np.ones_like(raw_wind)
    sample_variance = np.broadcast_to(ratios, (2, 2, 3)).copy()
    values = [
        np.r_[case["parameters"], case["lat"][nodes], case["lon"][nodes]],
        case["ps"][1, nodes], p[-1], p, raw_wind, variance, arrays["p10"][1, nodes],
        raw_sample, sample_variance, arrays["xy"][triangles].transpose(2, 1, 0),
        case["ps"][1, triangles].T,
    ]
    with path.open("w") as stream:
        stream.write(f"{len(p)} {len(ratios)}\n")
        for value in values:
            stream.write(" ".join(format(float(x), ".17g") for x in np.asarray(value).ravel(order="F")) + "\n")
    return p, nodes, ratios


def read_result(path, n, scenarios):
    shapes = {
        "xy": (2, 2), "chart_wind": (n, 2, 2), "chart_sample": (2, 2), "volume": (2,),
        "baseline": (1,), "flux": (scenarios,), "reverse_flux": (scenarios,),
        "uncovered": (scenarios,), "partition_error": (2, scenarios),
        "shared_contribution": (2, scenarios), "fitted": (n, 2, 2, scenarios),
        "innovation": (2, 2, scenarios),
    }
    result = {}
    with path.open("rb") as stream:
        for name, shape in shapes.items():
            count = int(np.prod(shape))
            value = np.fromfile(stream, dtype="<f8", count=count)
            if value.size != count or not np.isfinite(value).all():
                raise ValueError(f"invalid {name} output")
            result[name] = value.reshape(shape, order="F")
        if stream.read(1):
            raise ValueError("unexpected output suffix")
    return result


def check_wind_roundtrip(result, case, nodes, q):
    """Independent diagnostic inverse; the forward transform runs in Fortran."""
    phi0, _, _, cone, orientation = case["parameters"]
    scale = np.cos(phi0) / np.cos(case["lat"][nodes])
    rotation = np.exp(1j * cone * (case["lon"][nodes] - orientation))
    maximum = 0.0
    for chart, raw in (
        (result["chart_wind"], case["u"][1, nodes, q:].T + 1j * case["v"][1, nodes, q:].T),
        (result["chart_sample"], case["surface_u"][1, nodes] + 1j * case["surface_v"][1, nodes]),
    ):
        restored = (chart[..., 0, :] / scale + 1j * chart[..., 1, :] * scale) * rotation
        np.testing.assert_allclose(restored, raw, rtol=2e-13, atol=2e-13)
        maximum = max(maximum, float(np.abs(restored - raw).max()))
    return maximum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True, help="PR39 final prepared replay directory")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_dir.resolve()
    prior_report = source / "report.json"
    provenance = json.loads(prior_report.read_text())
    inputs = {name: source / name for name in ("prepared.bin", "arrays.npz", "report.json")}
    pins = {name: sha256(path) for name, path in inputs.items()}
    for name in ("prepared.bin", "arrays.npz"):
        if pins[name] != provenance["artifact_sha256"][name]:
            raise ValueError(f"PR39 artifact hash mismatch: {name}")
    if not provenance.get("height_mapping_physical_status", "").startswith("CONDITIONAL_THIN_LAYER_PRIOR:"):
        raise ValueError("thermodynamic prior replay required")

    domain, inventory = audit_domain(inputs["arrays.npz"], inputs["prepared.bin"])
    if domain["selection_fallback_to_lowest_strict"]:
        raise ValueError("this study requires the explicit 0-10 m height bracket at both endpoints")
    record = domain["selected_preferred_13_internal"]
    case = read_prepared(inputs["prepared.bin"])
    arrays = np.load(inputs["arrays.npz"], allow_pickle=False)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "domain.json").write_text(json.dumps(domain, indent=2, allow_nan=False) + "\n")
    np.savez_compressed(out / "domain.npz", **inventory)
    p, nodes, ratios = write_face(out / "face.txt", case, arrays, record)

    repo = Path(__file__).resolve().parents[1]
    sources = ["qbal_physical_boundary.f90", "qbal_pressure_flux.f90", "qbal_sloping_geometry.f90",
               "qbal_profile_reconstruction.f90", "qbal_profile_face.f90", "diagnose_qbal_profile_face.f90"]
    source_paths = [repo / "tests" / name for name in sources]
    source_paths += [Path(__file__).resolve(), repo / "tests/audit_qbal_profile_domain.py", repo / "tests/intel_toolchain.sh"]
    source_pins = {str(path.relative_to(repo)): sha256(path) for path in source_paths}
    script = out / "run.sh"
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
 "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian "${@:3}" -o diagnose
 ./diagnose "$out/face.txt" result.bin
 )
done
''')
    with (out / "intel.log").open("w") as log:
        subprocess.run(["bash", str(script), str(repo), str(out),
                        *[str(repo / "tests" / name) for name in sources]],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    first, second = [read_result(out / level / "result.bin", len(p), len(ratios)) for level in ("O0", "O2")]
    length_scale = float(np.abs(first["xy"][:, 1] - first["xy"][:, 0]).sum())
    speed_scale = max(float(np.abs(first["fitted"]).max()), float(np.abs(second["fitted"]).max()),
                      float(np.abs(first["chart_wind"]).max()), 1.0)
    # Pre-cancellation transport scale; not a physical residual tolerance.
    tolerance = 2048 * np.finfo(float).eps * (len(p) + 1) * length_scale * p[0] * speed_scale
    for result in (first, second):
        check_wind_roundtrip(result, case, nodes, record["cap_knot_index_zero_based_by_time"][1])
        if np.any(np.abs(result["flux"] + result["reverse_flux"]) > tolerance):
            raise ValueError("face reversal failed")
        if np.any(np.abs(result["partition_error"]) > tolerance):
            raise ValueError("fixed-profile cap additivity failed")
        shared = result["volume"] @ result["shared_contribution"]
        if np.any(np.abs(shared) > tolerance):
            raise ValueError("shared-face weighted cancellation failed")
        if np.any(result["uncovered"] <= 0):
            raise ValueError("expected unresolved 0-10 m pressure interval")
    transport_fields = ("baseline", "flux", "reverse_flux", "partition_error")
    for name in first:
        allowance = tolerance if name in transport_fields else (
            2048 * np.finfo(float).eps * max(float(np.abs(first[name]).max()), 1.0))
        if np.any(np.abs(first[name] - second[name]) > allowance):
            raise ValueError(f"O0/O2 arithmetic difference: {name}")
    np.testing.assert_allclose(first["xy"].T, arrays["xy"][nodes], rtol=2e-13, atol=1e-7)
    for name, path in inputs.items():
        if sha256(path) != pins[name]:
            raise ValueError("input changed during replay")
    for name, pin in source_pins.items():
        if sha256(repo / name) != pin:
            raise ValueError("source changed during replay")
    np.savez(out / "result.npz", **first)
    report = {
        "status": "PASS_SCOPED / CONDITIONAL_ENDPOINT_PROFILE_TRANSPORT",
        "selection": record, "domain_counts": domain["counts"],
        "time": int(case["times"][1]), "time_contract": "single 13 UTC sample; not a time-mean budget",
        "fixed_knots_Pa": p.tolist(), "background_variance_chart_units": 1.0,
        "sample_variance_chart_units": ratios.tolist(), "calibrated_covariance": None,
        "wind_transform_check": "inverse chart metric and complex inverse rotation recover original raw endpoint winds",
        "covariance_contract": "independent scalar diagonal research objectives; no LSX/LW3 cross-covariance calibration",
        "baseline_transport_m2_Pa_per_s": float(first["baseline"][0]),
        "fitted_transport_m2_Pa_per_s": first["flux"].tolist(),
        "sample_innovation_chart_m_per_s": first["innovation"].tolist(),
        "max_knot_change_chart_m_per_s": np.abs(first["fitted"] - first["chart_wind"][..., None]).max(axis=(0, 1, 2)).tolist(),
        "missing_pressure_span_Pa": first["uncovered"].tolist(),
        "max_partition_arithmetic_error": float(np.abs(first["partition_error"]).max()),
        "max_reversal_arithmetic_error": float(np.abs(first["flux"] + first["reverse_flux"]).max()),
        "max_shared_arithmetic_error": float(np.abs(first["volume"] @ first["shared_contribution"]).max()),
        "arithmetic_allowance_m2_Pa_per_s": tolerance,
        "physical_column_residual": None, "physical_domain_residual": None, "production_authority": False,
        "prior_domain_status": "PS-domain and HT bracket checks only; common height datum and actual error model remain unverified",
        "frame_status": domain["frame_chart_context"]["wind_frame_status"],
        "input_paths": {name: str(path) for name, path in inputs.items()}, "input_sha256": pins,
        "upstream_raw_input_sha256": provenance["input_sha256"], "source_sha256": source_pins,
        "artifact_sha256": {name: sha256(out / name) for name in ("face.txt", "domain.json", "domain.npz", "result.npz")},
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
