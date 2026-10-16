#!/usr/bin/env python3
"""Compare matched frozen-physics histories; response norms are not skill scores."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import netCDF4
import numpy as np

from pr86_water_budget import load_call_measure, sha256

START = dt.datetime(2026, 8, 16, 13)
SCALARS = ("QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP",
           "QNCLOUD", "QNICE", "QNRAIN", "QIB", "T")
UNITS = {**{n: "kg/kg dry" for n in SCALARS[:6]},
         **{n: "number/kg dry" for n in SCALARS[6:9]}, "QIB": "m3/kg dry",
         "T": "K perturbation potential temperature", "pressure": "Pa",
         "geopotential": "m2/s2", "U": "m/s", "V": "m/s", "W": "m/s"}


def response_norm(off: np.ndarray, coupled: np.ndarray) -> dict:
    if off.shape != coupled.shape or not np.isfinite(off).all() or not np.isfinite(coupled).all():
        raise ValueError("response arrays must share finite support")
    delta = coupled.astype(np.float64) - off.astype(np.float64)
    return {"rms": float(np.sqrt(np.mean(delta * delta))),
            "mean": float(np.mean(delta)), "max_abs": float(np.max(np.abs(delta))),
            "off_rms": float(np.sqrt(np.mean(off.astype(np.float64) ** 2))),
            "coupled_rms": float(np.sqrt(np.mean(coupled.astype(np.float64) ** 2)))}


def compare_first_call(off_root: Path, coupled_root: Path) -> dict:
    """Compare captured call boundaries without inventing host history fields."""
    calls = {"OFF": load_call_measure(off_root), "COUPLED": load_call_measure(coupled_root)}
    if any(call["arm"] != arm for arm, call in calls.items()):
        raise ValueError("first-call arms do not match their declared roles")
    units = {**{n: "kg/kg dry" for n in ("Q", "QC", "QI", "QR", "QS", "QG")},
             **{n: "number/kg dry" for n in ("NC", "NI", "NR")},
             "BG": "m3/kg dry", "P": "Pa", "T": "K"}
    records = []
    for stage in ("pre", "post"):
        fields = {arm: dict(call[stage]["fields"]) for arm, call in calls.items()}
        for field in fields.values():
            field["T"] = field["TH"].astype(np.float64) * field["PII"].astype(np.float64)
        records.append({"stage": f"{stage.upper()}_KDM6", "timestep": 1,
                        "fields": {n: {"unit": unit, **response_norm(fields["OFF"][n], fields["COUPLED"][n])}
                                   for n, unit in units.items()}})
    return {"schema": "pr86_matched_first_call_response_v1", "physical_approval": "FAIL_OPEN",
            "scope": "Unweighted active-grid COUPLED minus OFF at first KDM6 boundaries, not a time-zero retention ratio or host final-step state.",
            "identities": {arm: call["identities"] for arm, call in calls.items()}, "records": records,
            "unavailable": ["U", "V", "W", "geopotential", "independent observation fit",
                            "transport-only diffusion", "full energy closure"]}


def history_coverage(off_times: set[str], coupled_times: set[str]) -> dict:
    expected = {(START + dt.timedelta(seconds=s)).strftime("%Y-%m-%d_%H:%M:%S")
                for s in range(0, 601, 60)}
    missing = {"OFF": sorted(expected - off_times), "COUPLED": sorted(expected - coupled_times)}
    unexpected = {"OFF": sorted(off_times - expected), "COUPLED": sorted(coupled_times - expected)}
    return {"expected_timestamps": sorted(expected), "missing_timestamps": missing,
            "unexpected_timestamps": unexpected,
            "complete": not any(missing.values()) and not any(unexpected.values())}


def history_index(root: Path) -> tuple[dict, dict]:
    index, identities = {}, {}
    for path in sorted(root.glob("wrfout_d01_*")):
        before = sha256(path)
        with netCDF4.Dataset(path) as ds:
            times = netCDF4.chartostring(ds["Times"][:]).tolist()
        if not times or not path.name.endswith(times[0]):
            raise ValueError("history filename must identify its first stored time")
        for frame, timestamp in enumerate(times):
            if timestamp in index:
                raise ValueError(f"duplicate history timestamp {timestamp}")
            index[timestamp] = (path, frame)
        identities[str(path)] = {"sha256": before, "timestamps": times}
    return index, identities


def load_history(path: Path, frame: int = 0) -> tuple[str, dict, dict]:
    """Read the same active footprint as the PR85 first-call audit."""
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_mask(False)
        times = netCDF4.chartostring(ds["Times"][:]).tolist()
        if not 0 <= frame < len(times):
            raise ValueError("history frame outside stored times")
        time = times[frame]
        # Full mass-grid shape is j=282,k=39,i=234; exclude the outer ring.
        shape = ds["QVAPOR"].shape
        if shape != (len(times), 39, 282, 234):
            raise ValueError(f"unexpected frozen-domain history shape {shape}")
        fields = {n: np.asarray(ds[n][frame, :, 1:-1, 1:-1], dtype=np.float64) for n in SCALARS}
        fields["pressure"] = (ds["P"][frame, :, 1:-1, 1:-1].astype(np.float64) +
                              ds["PB"][frame, :, 1:-1, 1:-1].astype(np.float64))
        phi = (ds["PH"][frame, :, 1:-1, 1:-1].astype(np.float64) +
               ds["PHB"][frame, :, 1:-1, 1:-1].astype(np.float64))
        fields["geopotential"] = 0.5 * (phi[:-1] + phi[1:])
        u = np.asarray(ds["U"][frame, :, 1:-1, 1:-1], dtype=np.float64)
        v = np.asarray(ds["V"][frame, :, 1:-1, 1:-1], dtype=np.float64)
        w = np.asarray(ds["W"][frame, :, 1:-1, 1:-1], dtype=np.float64)
        fields["U"], fields["V"], fields["W"] = (0.5 * (u[..., :-1] + u[..., 1:]),
                                                   0.5 * (v[:, :-1] + v[:, 1:]),
                                                   0.5 * (w[:-1] + w[1:]))
        extras = {}
        for name in ("RAINNC", "RAINC", "REFL_10CM"):
            if name in ds.variables:
                values = np.asarray(ds[name][frame], dtype=np.float64)
                extras[name] = {"finite": int(np.isfinite(values).sum()),
                                "nonfinite": int((~np.isfinite(values)).sum()),
                                "min": float(np.nanmin(values)), "max": float(np.nanmax(values))}
    if any(a.shape != (39, 280, 232) for a in fields.values()):
        raise ValueError("destaggered histories do not share the active footprint")
    return time, fields, {"path": str(path), "frame": frame, "extra_output_stats": extras}


def compare(off_root: Path, coupled_root: Path) -> dict:
    off_index, off_files = history_index(off_root)
    coupled_index, coupled_files = history_index(coupled_root)
    coverage = history_coverage(set(off_index), set(coupled_index))
    times = sorted(set(off_index) & set(coupled_index))
    rows, initial, artifacts = [], {}, []
    for timestamp in times:
        t0, off, a0 = load_history(*off_index[timestamp])
        t1, coupled, a1 = load_history(*coupled_index[timestamp])
        if t0 != t1 or t0 != timestamp:
            raise ValueError("history filename/time mismatch between arms")
        seconds = (dt.datetime.strptime(t0, "%Y-%m-%d_%H:%M:%S") - START).total_seconds()
        if seconds < 0 or seconds > 600 or seconds % 60 != 0:
            raise ValueError("history outside declared ten-minute window")
        stats = {key: {"unit": UNITS[key], **response_norm(off[key], coupled[key])} for key in UNITS}
        if seconds == 0:
            initial = {key: value["rms"] for key, value in stats.items()}
        if not initial:
            raise ValueError("initial matched histories required before response ratios")
        for key, value in stats.items():
            value["response_rms_over_initial_analysis_rms"] = (
                value["rms"] / initial[key] if initial[key] else None)
        rows.append({"timestamp": t0, "model_seconds": seconds, "fields": stats})
        artifacts.append({"OFF": a0, "COUPLED": a1})
    for path, identity in {**off_files, **coupled_files}.items():
        if sha256(Path(path)) != identity["sha256"]:
            raise ValueError(f"history changed while reading: {path}")
    return {"schema": "pr86_matched_history_response_v1", "physical_approval": "FAIL_OPEN",
            "status": "TEN_MINUTE_HISTORY_AVAILABLE" if coverage["complete"]
                      else "INCOMPLETE_HISTORY_WINDOW",
            "records": rows, "artifacts": artifacts, "history_coverage": coverage,
            "file_identities": {"OFF": off_files, "COUPLED": coupled_files},
            "scope": "Eulerian unweighted active-grid OFF/COUPLED response norms, not an independent observation comparison or transport-only diffusion measurement.",
            "limits": ["A ratio need not stay near one: advection and nonlinear dynamics evolve the analysis response.",
                       "A zero initial analysis norm gives no retention denominator and is reported as null.",
                       "These norms do not certify force balance, continuity, water/energy closure, or forecast improvement.",
                       "T is stored perturbation potential temperature, not a reconstructed physical temperature.",
                       "Twenty-second pressure/wind histories are not invented if the one-minute history cadence omits them."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off-root", type=Path, required=True)
    parser.add_argument("--coupled-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-call", action="store_true", help="compare frozen v17 call dumps instead of histories")
    args = parser.parse_args()
    evaluate = compare_first_call if args.first_call else compare
    args.output.write_text(json.dumps(evaluate(args.off_root, args.coupled_root), indent=2,
                                      allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
