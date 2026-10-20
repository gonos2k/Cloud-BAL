#!/usr/bin/env python3
"""Recreate the bounded C14 area and same-time history response summary."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import timedelta
from pathlib import Path

import netCDF4
import numpy as np

EXPECTED_EXECUTABLE_SHA256 = "5581e1be3febd54409304ccf7cbe305830a75968858075bf0d95f68b48d812be"
EXPECTED_RECEIPT_SHA256 = {
    "OFF": "f6a2e40d65c76e4e9abd0dfb1fc26f0c5da3abe4327a5d23829e4a66f34b540a",
    "COUPLED": "9bd0a867987896dc9c6551bbc964e8fd1d2d759cb865827af81346b782a40e48",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--off-run-root", type=Path, required=True,
                        help="closed C14 OFF run root containing receipt.json and run/")
    parser.add_argument("--coupled-run-root", type=Path, required=True,
                        help="closed C14 COUPLED run root containing receipt.json and run/")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="new, empty destination outside the archived evidence directory")
    args = parser.parse_args()

    repo = args.repo_root.resolve(strict=True)
    output = args.output_dir.resolve()
    if output.exists():
        raise SystemExit(f"output directory already exists; choose a fresh destination: {output}")
    output.mkdir(parents=True)
    sys.path.insert(0, str(repo))
    cold = load_module("pr90_cold_column_summary", repo / "tools/pr90_cold_column_summary.py")
    native = load_module("pr87_native_history", repo / "tools/pr87_native_history.py")
    paired = load_module("pr89_paired_history", repo / "tools/pr89_paired_history.py")

    roots = {"OFF": args.off_run_root.resolve(strict=True),
             "COUPLED": args.coupled_run_root.resolve(strict=True)}
    receipts = {}
    for arm, run_root in roots.items():
        receipt_path = run_root / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if sha256(receipt_path) != EXPECTED_RECEIPT_SHA256[arm]:
            raise ValueError(f"{arm} receipt hash is not the pinned closed C14 receipt")
        if (receipt.get("arm") != arm or receipt.get("status") != "COMPLETE"
                or receipt.get("returncode") != 0 or receipt.get("final_completed_step") != 12
                or receipt.get("executed_executable_sha256") != EXPECTED_EXECUTABLE_SHA256):
            raise ValueError(f"{arm} receipt does not match the closed C14 execution identity")
        receipts[arm] = receipt

    area = {}
    indices, windows = {}, {}
    history_paths = {}
    for arm, run_root in roots.items():
        run = run_root / "run"
        receipt = run_root / "receipt.json"
        history = run / "wrfout_d01_2026-08-16_13:00:00"
        cold_summary = run / "pr90_kdm6_cold_column.raw.gz"
        stages = run / "pr85_joint_moment_stages.raw.gz"
        area[arm] = cold.area_weighted_totals(
            cold_summary, run_receipt_path=receipt, history_path=history,
            stage_record_path=stages)
        index, grid = native._file_index([history])
        times = sorted(index)
        windows[arm] = native._receipt_window(
            receipt, [history], times, endpoint_seconds=240,
            interval_seconds=60, allow_incomplete=False)
        indices[arm] = (index, grid)
        history_paths[arm] = history

    for arm, totals in area.items():
        if totals["run_status"] != "COMPLETE" or totals["final_completed_step"] != 12:
            raise ValueError(f"{arm} area join is not complete through 12 model steps")
        if any(not row["completed"] or row["status"] != "FULL"
               for row in totals["coverage_by_timestep"].values()):
            raise ValueError(f"{arm} area join lacks full coverage for a completed step")

    activity_totals = {}
    for arm, totals in area.items():
        activity_totals[arm] = {}
        for group in ("NG", "AUT", "G"):
            activity_totals[arm][group] = {}
            for stage in ("proposed", "applied", "deferred"):
                activity_totals[arm][group][stage] = {
                    metric: float(sum(totals["by_timestep"][step][group][stage][metric]
                                      for step in range(1, 13)))
                    for metric in ("signed_kg", "half_l1_kg")
                }
            proposed = activity_totals[arm][group]["proposed"]["half_l1_kg"]
            deferred = activity_totals[arm][group]["deferred"]["half_l1_kg"]
            activity_totals[arm][group]["deferred_fraction_of_proposed_half_l1"] = (
                deferred / proposed if proposed else None)

    paired._verify_static_geometry(history_paths["OFF"], history_paths["COUPLED"])
    off_times = sorted(indices["OFF"][0])
    snapshots = [off_times[0] + timedelta(seconds=seconds)
                 for seconds in (0, 60, 120, 180, 240)]
    state_rows, inventory_rows = [], []
    for when in snapshots:
        state, inventory = {}, {}
        for arm in ("OFF", "COUPLED"):
            record_path, record = indices[arm][0][when]
            with netCDF4.Dataset(record_path) as dataset:
                dataset.set_auto_mask(False)
                dx, dy = float(dataset.DX), float(dataset.DY)
                mass, _ = native._dry_mass(
                    dataset, record, native.EXPECTED_GRAVITY_M_S2, dx, dy)
                state[arm] = {
                    "P+PB": native._finite(dataset, "P", record)
                    + native._finite(dataset, "PB", record),
                    "PH+PHB_interface": native._finite(dataset, "PH", record)
                    + native._finite(dataset, "PHB", record),
                    "W_native_faces": native._finite(dataset, "W", record),
                }
                interior = np.zeros(mass.shape[-2:], dtype=bool)
                interior[1:-1, 1:-1] = True
                inventory[arm] = {}
                for species in ("QCLOUD", "QICE", "QSNOW", "QGRAUP"):
                    water = native._finite(dataset, species, record)
                    if water.shape != mass.shape:
                        raise ValueError(f"{arm} {species} shape differs from hybrid dry mass")
                    extensive = water * mass
                    inventory[arm][species] = {
                        "all_native_kg": float(np.sum(extensive, dtype=np.float64)),
                        "interior_kg": float(np.sum(extensive[:, interior], dtype=np.float64)),
                    }
                inventory[arm]["cloud_ice_snow_graupel_total"] = {
                    key: float(sum(inventory[arm][species][key]
                                   for species in ("QCLOUD", "QICE", "QSNOW", "QGRAUP")))
                    for key in ("all_native_kg", "interior_kg")
                }

        field_differences = {}
        for name in state["OFF"]:
            if state["OFF"][name].shape != state["COUPLED"][name].shape:
                raise ValueError(f"OFF and COUPLED {name} shapes differ")
            delta = state["COUPLED"][name] - state["OFF"][name]
            field_differences[name] = {
                "shape": list(delta.shape),
                "mean_abs_difference": float(np.mean(np.abs(delta), dtype=np.float64)),
                "max_abs_difference": float(np.max(np.abs(delta))),
                "signed_mean_difference": float(np.mean(delta, dtype=np.float64)),
            }
        state_rows.append({
            "elapsed_seconds": int((when - snapshots[0]).total_seconds()),
            "fields_COUPLED_minus_OFF": field_differences,
        })
        inventory_rows.append({
            "elapsed_seconds": int((when - snapshots[0]).total_seconds()),
            "COUPLED_minus_OFF_kg": {
                species: {scope: inventory["COUPLED"][species][scope]
                          - inventory["OFF"][species][scope]
                          for scope in ("all_native_kg", "interior_kg")}
                for species in inventory["OFF"]
            },
            "by_arm_kg": inventory,
        })

    run_identity = {}
    for arm, run_root in roots.items():
        receipt_path = run_root / "receipt.json"
        receipt = receipts[arm]
        run_identity[arm] = {
            "receipt_path": str(receipt_path),
            "receipt_sha256": sha256(receipt_path),
            "status": receipt["status"],
            "returncode": receipt["returncode"],
            "completed_steps": receipt["final_completed_step"],
            "executable_sha256": receipt["executed_executable_sha256"],
            "candidate_wrfinput_sha256": receipt["candidate_wrfinput_sha256"],
            "candidate_wrfbdy_sha256": receipt["candidate_wrfbdy_sha256"],
            "candidate_namelist_sha256": receipt["candidate_namelist_sha256"],
            "history_window": windows[arm],
        }

    result = {
        "schema": "pr91_c14_current_response_summary_v1",
        "physical_approval": False,
        "scope": ("C14 candidate OFF and COUPLED analysis arms; both receipts are COMPLETE "
                  "through 240 seconds. Each arm is bound to its corresponding frozen candidate "
                  "inputs; differing OFF/COUPLED wrfinput hashes are expected for these analysis "
                  "arms. Cold activity covers twelve receipt-completed model timesteps. Same-time "
                  "history snapshots at 0/60/120/180/240 seconds are a descriptive matched response "
                  "under C14; they do not establish observational skill, a pure-model causal effect, "
                  "or full-field treatment attribution."),
        "run_identity": run_identity,
        "cold_activity_area_weighted": area,
        "cold_activity_totals_completed_steps_1_to_12": activity_totals,
        "history_same_time_snapshots": {
            "times_elapsed_seconds": [0, 60, 120, 180, 240],
            "comparison": ("Descriptive matched COUPLED-minus-OFF response under C14; pressure=P+PB "
                           "at mass points, geopotential=PH+PHB at native interfaces, W at native "
                           "vertical faces; no interpolation or causal attribution. Differing "
                           "OFF/COUPLED wrfinput hashes are expected for these analysis arms, and "
                           "each arm is bound to its corresponding frozen candidate inputs. "
                           "Cloud/ice/snow/graupel inventories use the existing hybrid dry mass "
                           "calculated separately from each arm’s history at each snapshot time and "
                           "are reported over all native cells and interior cells. These diagnostics "
                           "do not establish observational skill, a pure-model causal effect, or "
                           "full-field treatment attribution."),
            "state_fields": state_rows,
            "hydrometeor_inventories": inventory_rows,
        },
    }
    summary_path = output / "summary.json"
    cold_path = output / "cold_area_weighted.json"
    summary_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cold_path.write_text(json.dumps(area, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    source_files = [repo / f"tools/{name}" for name in (
        "pr90_cold_column_summary.py", "pr87_native_history.py", "pr89_paired_history.py")]
    manifest = {
        "schema": "pr91_c14_current_response_reproduction_v1",
        "run_roots": {arm: str(path) for arm, path in roots.items()},
        "run_receipts": {arm: {"path": str(path / "receipt.json"),
                                "sha256": run_identity[arm]["receipt_sha256"]}
                         for arm, path in roots.items()},
        "reused_source_pins": {str(path.relative_to(repo)): sha256(path)
                               for path in source_files},
        "driver_sha256": sha256(Path(__file__).resolve()),
        "outputs": {path.name: sha256(path) for path in (summary_path, cold_path)},
    }
    (output / "reproduction_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote C14 response summary and manifest under {output}")


if __name__ == "__main__":
    main()
