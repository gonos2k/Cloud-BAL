"""Map C14 arm differences and follow fixed native-grid peak locations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4
import numpy as np

from pr92_c14_field_scopes import FIELDS, TIMES, paired, receipt_identity, scopes, sha256


def analyze(off_path: Path, coupled_path: Path, off_receipt: Path,
            coupled_receipt: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    identities = {"OFF": receipt_identity(off_receipt, off_path, "OFF"),
                  "COUPLED": receipt_identity(coupled_receipt, coupled_path, "COUPLED")}
    geometry = paired._verify_static_geometry(off_path, coupled_path)
    off_times, grid = paired._records(off_path)
    coupled_times, other_grid = paired._records(coupled_path)
    paired._pair_geometry(grid, other_grid)
    times = sorted(off_times)
    if times != sorted(coupled_times) or not times:
        raise ValueError("paired history times differ")
    elapsed = [int((time - times[0]).total_seconds()) for time in times]
    if tuple(elapsed) != TIMES:
        raise ValueError(f"unexpected C14 history schedule: {elapsed}")
    with netCDF4.Dataset(off_path) as off, netCDF4.Dataset(coupled_path) as coupled:
        off.set_auto_mask(False); coupled.set_auto_mask(False)
        support = np.zeros(grid["shape"], dtype=bool)
        for name in paired.native.WATER:
            support |= np.any(np.asarray(off.variables[name][0]) !=
                              np.asarray(coupled.variables[name][0]), axis=0)
        latitude = np.asarray(off.variables["XLAT"][0], dtype=np.float64)
        longitude = np.asarray(off.variables["XLONG"][0], dtype=np.float64)
    if support.sum() != 27:
        raise ValueError("frozen C14 descriptive support changed")
    masks = scopes(support)
    deltas = {label: {} for label in FIELDS}
    for seconds, time in zip(elapsed, times):
        a = paired._load_snapshot(off_path, off_times, time, grid, 9.8100004196167)
        b = paired._load_snapshot(coupled_path, coupled_times, time, other_grid, 9.8100004196167)
        for label, (field, _) in FIELDS.items():
            deltas[label][seconds] = b[field] - a[field]
    output.mkdir(parents=True)
    results = {}
    for label, (_, units) in FIELDS.items():
        values = deltas[label]
        # The union includes each time's whole-grid maximum; the subsequent
        # trajectories keep exactly that native (k,j,i), including its level.
        locations = sorted({np.unravel_index(np.abs(a).argmax(), a.shape)
                            for a in values.values() if np.any(a)})
        tracks = []
        for k, j, i in locations:
            tracks.append({"native_ijk_one_based": [int(i + 1), int(j + 1), int(k + 1)],
                           "stored_level_location": ("lowest" if k == 0 else
                                                     "highest" if k == values[0].shape[0] - 1 else "interior"),
                           "latitude": float(latitude[j, i]), "longitude": float(longitude[j, i]),
                           "descriptive_scopes": [name for name, mask in masks.items() if mask[j, i]],
                           "delta_at_elapsed_seconds": {str(t): float(a[k, j, i]) for t, a in values.items()}})
        vmax = max(float(np.abs(a).max()) for a in values.values()) or 1.0
        fig, axes = plt.subplots(2, len(TIMES), figsize=(20, 7), constrained_layout=True)
        for col, seconds in enumerate(TIMES):
            a = values[seconds]
            projection = np.take_along_axis(a, np.abs(a).argmax(axis=0)[None], axis=0)[0]
            for row in range(2):
                ax = axes[row, col]
                im = ax.pcolormesh(longitude, latitude, projection, cmap="RdBu_r",
                                   vmin=-vmax, vmax=vmax, shading="auto")
                ax.set_title(f"{seconds}s: {'domain' if row == 0 else 'fixed view'}", fontsize=11)
                if row:
                    ax.set_xlim(longitude[support].min() - .75, longitude[support].max() + .75)
                    ax.set_ylim(latitude[support].min() - .75, latitude[support].max() + .75)
                ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
        fig.colorbar(im, ax=axes, label=units, shrink=.8)
        fig.suptitle(f"C14 COUPLED minus OFF: {label}; signed value at column max |difference|", fontsize=12)
        path = output / f"c14_{label}_maps.png"
        fig.savefig(path, dpi=130); plt.close(fig)
        results[label] = {"units": units, "fixed_native_location_tracks": tracks,
                          "max_abs_by_stored_level_scope": {
                              str(t): {"all_levels": float(np.abs(a).max()),
                                       "lowest_and_highest_levels": float(np.abs(a[[0, -1]]).max()),
                                       "interior_levels": float(np.abs(a[1:-1]).max())}
                              for t, a in values.items()},
                          "maps": {"path": path.name, "sha256": sha256(path)},
                          "map_definition": "Signed delta at each column's largest absolute native-level delta; level may differ between columns and times."}
    result = {"schema": "pr92_c14_fixed_location_response_v1", "physical_approval": False,
              "run_identity": identities, "static_geometry_check": geometry,
              "elapsed_seconds": elapsed, "fields": results,
              "limits": ["Locations are outcome-selected descriptive peaks, not observation support.",
                         "A fixed native grid point and level is not a material parcel or fixed altitude.",
                         "Upper maps cover the domain; lower maps use the fixed T0 response-support box plus 0.75 degrees.",
                         "These are paired state differences, not force, continuity, water or energy closure."]}
    (output / "fixed_location_response.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("off-history", "coupled-history", "off-receipt", "coupled-receipt", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    analyze(args.off_history, args.coupled_history, args.off_receipt, args.coupled_receipt, args.output)


if __name__ == "__main__":
    main()
