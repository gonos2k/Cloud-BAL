#!/usr/bin/env python3
"""Physical-volume first-call accounting of the frozen PR85 v17 experiment.

The local KDM6 measure rho_dry * DELZ * map area is used throughout. It is
not substituted for the uncaptured same-call host hybrid-pressure measure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np

from native_kdm6_trace import read_dump
from pr67_kdm6_process_budget import parse_process_capture

WATER = ("Q", "QC", "QI", "QR", "QS", "QG")
ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/evidence/pr85_integration_20261015.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bound_file(path: Path, expected: str) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"not a regular capture: {path}")
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"baseline hash mismatch: {path}")
    return {"path": str(path), "sha256": actual, "bytes": path.stat().st_size}


def load_call_measure(run_root: Path) -> dict:
    """Load immutable first-call fields; arrays use active (j,k,i) order."""
    baseline = json.loads(BASELINE.read_text())
    matches = [(arm, row) for arm, row in baseline["latest_actual_host"]["arms"].items()
               if Path(row["run_receipt_path"]).parent.resolve() == run_root.resolve()]
    if len(matches) != 1:
        raise ValueError("run is not one of the frozen v17 arms")
    arm, declared = matches[0]
    receipt_path = run_root / "pr83_same13_native_initialization.json"
    identities = {"baseline": {"path": str(BASELINE), "sha256": sha256(BASELINE)},
                  "receipt": bound_file(receipt_path, declared["run_receipt_sha256"])}
    receipt = json.loads(receipt_path.read_text())
    if receipt["run_isolation"]["returncode"] != 0 or receipt["first_step_gate"] != "PASS":
        raise ValueError("baseline first step did not pass")
    dumps = []
    for name in ("kdm6_first_call_pre.raw", "kdm6_first_call_post.raw"):
        path = run_root / name
        identities[name] = bound_file(path, receipt["native_trace_outputs"][name]["sha256"])
        dumps.append(read_dump(path))
        if dumps[-1]["sha256"] != identities[name]["sha256"]:
            raise ValueError(f"capture changed while loading: {path}")
    pre, post = dumps
    if (pre["stage"], post["stage"], pre["itimestep"], post["itimestep"]) != (1, 2, 1, 1):
        raise ValueError("expected the first pre/post KDM6 call")
    if pre["bounds"] != post["bounds"] or pre["params"] != post["params"]:
        raise ValueError("pre/post call headers differ")
    b = pre["bounds"]
    for name in ("DEN", "DELZ"):
        a, z = pre["fields"][name], post["fields"][name]
        if not np.array_equal(a, z) or not np.isfinite(a).all() or np.any(a <= 0):
            raise ValueError(f"nonpositive or changing fixed-call {name}")
    wrfo = run_root / "wrfout_d01_2026-08-16_13:00:00"
    identities["initial_wrfo"] = bound_file(wrfo, receipt["initial_wrfo_sha256"])
    # WRF mass-grid i/j are one-based. Static map metrics survive the call;
    # initial MU is deliberately not used as a same-call mass observation.
    ys, xs = slice(b["jts"] - 1, b["jte"]), slice(b["its"] - 1, b["ite"])
    with netCDF4.Dataset(wrfo) as ds:
        ds.set_auto_mask(False)
        mx = np.asarray(ds["MAPFAC_MX"][0, ys, xs], dtype=np.float64)
        my = np.asarray(ds["MAPFAC_MY"][0, ys, xs], dtype=np.float64)
        dx, dy = float(ds.DX), float(ds.DY)
        lat = np.asarray(ds["XLAT"][0, ys, xs], dtype=np.float64)
        lon = np.asarray(ds["XLONG"][0, ys, xs], dtype=np.float64)
    if not (np.isfinite(mx).all() and np.isfinite(my).all() and
            np.all(mx > 0) and np.all(my > 0) and
            np.isfinite([dx, dy]).all() and dx > 0 and dy > 0):
        raise ValueError("invalid map metrics")
    area = dx * dy / (mx * my)
    if not np.isfinite(area).all() or np.any(area <= 0):
        raise ValueError("invalid physical cell area")
    rho = pre["fields"]["DEN"].astype(np.float64)
    dz = pre["fields"]["DELZ"].astype(np.float64)
    if area.shape != (rho.shape[0], rho.shape[2]):
        raise ValueError("map area and active cell bounds disagree")
    volume = dz * area[:, None, :]
    mass = rho * volume
    return {"arm": arm, "run_root": run_root, "pre": pre, "post": post,
            "area_ji": area, "delz_jki": dz, "rho_dry_jki": rho,
            "volume_jki": volume, "dry_mass_jki": mass, "bounds": b,
            "latitude_ji": lat, "longitude_ji": lon, "identities": identities,
            "receipt": receipt}


def cell_slot(bounds: dict, i: int, j: int, k: int) -> tuple[int, int, int]:
    if not (bounds["its"] <= i <= bounds["ite"] and
            bounds["jts"] <= j <= bounds["jte"] and bounds["kts"] <= k <= bounds["kte"]):
        raise ValueError(f"ledger coordinate outside captured domain: {(i,j,k)}")
    return j - bounds["jts"], k - bounds["kts"], i - bounds["its"]


def weighted_change(before: np.ndarray, after: np.ndarray, weight: np.ndarray) -> float:
    if before.shape != after.shape or before.shape != weight.shape:
        raise ValueError("weighted-change shapes differ")
    if not all(np.isfinite(x).all() for x in (before, after, weight)) or np.any(weight <= 0):
        raise ValueError("invalid weighted-change operands")
    return float(np.sum((after.astype(np.float64) - before.astype(np.float64)) * weight,
                        dtype=np.float64))


def analyze(run_root: Path, map_path: Path) -> dict:
    call = load_call_measure(run_root)
    pre, post, mass = call["pre"], call["post"], call["dry_mass_jki"]
    species = {}
    moments = {}
    for name in ("NC", "NI", "NR", "NN", "BG"):
        a, z = pre["fields"][name], post["fields"][name]
        moments[name] = {"unit": "m3" if name == "BG" else "particle count",
                         "before": float(np.sum(a.astype(np.float64) * mass)),
                         "after": float(np.sum(z.astype(np.float64) * mass)),
                         "delta": weighted_change(a, z, mass)}
    water_delta_map = np.zeros(mass.shape, dtype=np.float64)
    for name in WATER:
        a, z = pre["fields"][name], post["fields"][name]
        delta = (z.astype(np.float64) - a.astype(np.float64)) * mass
        water_delta_map += delta
        species[name] = {"before_kg": float(np.sum(a.astype(np.float64) * mass)),
                         "after_kg": float(np.sum(z.astype(np.float64) * mass)),
                         "cellwise_delta_kg": float(np.sum(delta))}
    process_path = run_root / "pr67_kdm6_process.raw"
    call["identities"][process_path.name] = bound_file(
        process_path, call["receipt"]["native_trace_outputs"][process_path.name]["sha256"])
    records = parse_process_capture(process_path)
    b = call["bounds"]
    ends = [r for r in records if r["stage"] == 2]
    if [r["lat"] for r in ends] != list(range(b["jts"], b["jte"] + 1)):
        raise ValueError("process rows do not cover the public call")
    precipitation = np.zeros((4, mass.shape[0], mass.shape[2]), dtype=np.float64)
    for row in ends:
        j = row["lat"] - b["jts"]
        if (row["its"], row["ite"], row["kts"], row["kte"]) != (
                b["its"], b["ite"], b["kts"], b["kte"]):
            raise ValueError("process bounds differ from public call")
        # Original rainncv update: fall*DELZ/DENR*dt*1000 mm.
        # Convert mm to kg/m2 using that same DENR/1000, once only.
        depth_mm = (row["fall"] * row["delz"][None, :] / row["denr"] *
                    row["dtcld"] * 1000.0)
        precipitation[:, j, :] = (depth_mm * (row["denr"] / 1000.0) *
                                    call["area_ji"][j][None, :])
    cutoff_map = np.zeros_like(mass)
    transition_map = np.zeros_like(mass)
    counts = {}
    for name, tag, target in (("pr85_kdm6_cutoff_budget.raw", "PR85_KDM6_CUTOFF", cutoff_map),
                              ("pr85_ice_transition_branch.raw", "PR85_ICE_TRANSITION", transition_map)):
        path = run_root / name
        call["identities"][name] = bound_file(path, call["receipt"]["native_trace_outputs"][name]["sha256"])
        n = 0
        with path.open() as stream:
            for line in stream:
                t = line.split()
                if not t or t[0] != tag:
                    continue
                i, j, k = map(int, t[1:4]); slot = cell_slot(b, i, j, k)
                if tag == "PR85_KDM6_CUTOFF":
                    if len(t) != 33:
                        raise ValueError("cutoff column contract changed")
                    v = np.asarray(t[6:-2], dtype=np.float64)
                    if not np.isfinite(v).all() or v[0] != call["rho_dry_jki"][slot]:
                        raise ValueError("cutoff density or values do not match call")
                    # rho,qmin,qcrmin,Qbefore5,Qafter5,Nbefore3,Nafter3,
                    # Bbefore,Bafter,Tbefore,Tafter,QVbefore,QVafter.
                    if v[21] != v[22] or v[23] != v[24]:
                        raise ValueError("cutoff changed T or vapor; cannot classify as recorded cleanup")
                    dq = float(np.sum(v[8:13] - v[3:8]))
                else:
                    if len(t) != 18:
                        raise ValueError("transition column contract changed")
                    v = np.asarray(t[5:], dtype=np.float64)
                    if not np.isfinite(v).all():
                        raise ValueError("nonfinite transition")
                    dq = (v[10] - v[4]) + (v[11] - v[5])
                target[slot] += dq * mass[slot]
                n += 1
        counts[name] = n
    dw = float(np.sum(water_delta_map))
    bottom = float(np.sum(precipitation))
    cleanup, transition = float(np.sum(cutoff_map)), float(np.sum(transition_map))
    residual = dw + bottom - cleanup - transition
    # Maps preserve actual i/j support; vertical changes are column integrated.
    map_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(map_path, latitude=call["latitude_ji"], longitude=call["longitude_ji"],
                        water_delta_kg=np.sum(water_delta_map, axis=1),
                        bottom_outflow_kg=np.sum(precipitation, axis=0),
                        cutoff_delta_kg=np.sum(cutoff_map, axis=1),
                        transition_storage_delta_kg=np.sum(transition_map, axis=1))
    return {"schema": "pr86_first_call_water_v1", "arm": call["arm"],
            "status": "ACCOUNTED_PARTIAL_BUDGET_OPEN", "physical_approval": "FAIL_OPEN",
            "measure": "fixed-call dry DEN * DELZ * DX*DY/(MAPFAC_MX*MAPFAC_MY)",
            "same_call_host_hybrid_measure": "NOT_CAPTURED_NOT_SUBSTITUTED",
            "active_shape_jki": list(mass.shape), "timestep": 1,
            "call_seconds": pre["params"]["dt_s"], "species": species,
            "public_moment_inventories": moments,
            "water_delta_kg": dw, "bottom_outflow_kg": bottom,
            "bottom_species_outflow_kg": dict(zip(("rain", "snow", "graupel", "ice"),
                                                  np.sum(precipitation, axis=(1, 2)).tolist())),
            "delta_plus_outflow_kg": dw + bottom, "cutoff_delta_kg": cleanup,
            "ice_to_snow_storage_delta_kg": transition,
            "residual_after_recorded_numerical_terms_kg": residual,
            "residual_over_bottom_outflow": residual / bottom if bottom else None,
            "ledger_rows": counts, "identities": call["identities"],
            "map": {"path": str(map_path), "sha256": sha256(map_path)},
            "missing_terms": ["other stored process-rounding and count/volume closure terms",
                              "same-call host hybrid dry mass and boundary reconciliation",
                              "complete thermodynamic/precipitation energy budget"],
            "notes": ["No analysis increment is added to this physical-time call budget.",
                      "Snow/graupel precipitation subsets are not added to total rainncv.",
                      "Recorded cleanup is numerical condensate removal, not phase transfer."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.run_root, args.map)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
