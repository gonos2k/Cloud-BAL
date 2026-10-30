#!/usr/bin/env python3
"""Record completed WRF runs and their seven independently read history times."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import netCDF4
import numpy as np


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def collect(root, arm):
    original = arm == "ORIGINAL"
    label = "OFF_RETRY" if arm == "OFF" else arm
    directory = root / ("original" if original else f"forecast_{label}")
    metadata = root / ("original_run_metadata.txt" if original else f"{label}.run_metadata.txt")
    manifest = root / ("original_inputs.sha256" if original else f"{label}.inputs.sha256")
    meta = dict(line.split("=", 1) for line in metadata.read_text().splitlines())
    if meta.get("exit") != "0" or "end_utc" not in meta:
        raise ValueError(f"{arm} did not complete successfully: {meta}")
    checked = subprocess.run(["sha256sum", "-c", str(manifest)], cwd=directory,
                             text=True, capture_output=True, check=True)
    if not original:
        full_manifest = root / f"{label}.all_inputs.sha256"
        full_inventory_timing = "BEFORE_LAUNCH"
    else:
        full_manifest = root / "original.inflight_inputs.sha256"
        full_inventory_timing = "DURING_RUN"
    full_checked = subprocess.run(["sha256sum", "-c", str(full_manifest)], cwd=directory,
                                  text=True, capture_output=True, check=True)
    log = directory / "rsl.out.0000"
    if "SUCCESS COMPLETE WRF" not in log.read_text(errors="replace"):
        raise ValueError(f"{arm} lacks WRF success marker")
    histories = []
    for hour in range(12, 19):
        stamp = f"2026-08-16_{hour:02d}:00:00"
        path = directory / f"wrfout_d01_{stamp}"
        with netCDF4.Dataset(path) as ds:
            times = netCDF4.chartostring(ds["Times"][:]).tolist()
            if times != [stamp]:
                raise ValueError(f"{arm} history times differ at {path}: {times}")
            for field in ("RAINC", "RAINNC", "RAINSH", "XLAT", "XLONG"):
                values = ds[field][:]
                if np.ma.is_masked(values) or not np.isfinite(values).all():
                    raise ValueError(f"{arm} invalid {field} at {stamp}")
        histories.append({"path": str(path), "time": stamp, "sha256": digest(path),
                          "size_bytes": path.stat().st_size})
    subprocess.run(["sha256sum", "-c", str(manifest)], cwd=directory,
                   text=True, capture_output=True, check=True)
    subprocess.run(["sha256sum", "-c", str(full_manifest)], cwd=directory,
                   text=True, capture_output=True, check=True)
    return {"status": "COMPLETE", "metadata": meta, "input_checks": checked.stdout.splitlines(),
            "input_manifest_sha256": digest(manifest), "log_sha256": digest(log),
            "full_input_inventory_timing": full_inventory_timing,
            "full_input_manifest_sha256": digest(full_manifest),
            "full_input_checks": full_checked.stdout.splitlines(),
            "launcher_log_sha256": digest(directory / "launcher.log"), "histories": histories}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    arms = ("ORIGINAL", "OFF", "HYDRO", "LIQUID_RADAR_RH1")
    result = {"scope": "fresh 12–18 UTC forecasts, current Cloud-BAL initializations with historical WRF host",
              "arms": {arm: collect(args.root, arm) for arm in arms}}
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
