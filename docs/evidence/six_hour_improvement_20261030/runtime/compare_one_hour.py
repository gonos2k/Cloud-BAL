#!/usr/bin/env python3
"""Compare the six-hour run's 13 UTC state against the prior one-hour run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np


SCRATCH = Path("/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED")
PRIOR = Path("/var/tmp/firsthour-runtime-plan-20261030/producer_pair/forecast/run_POLICY_BG")
EVIDENCE = Path(__file__).resolve().parent
FIELDS = ("RAINC", "RAINNC", "RAINSH", "T2", "Q2", "U10", "V10", "QRAIN", "QSNOW", "QGRAUP")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    name = "wrfout_d01_2026-08-16_13:00:00"
    current = SCRATCH / name
    prior = PRIOR / name
    current_sha, prior_sha = sha256(current), sha256(prior)
    report = {
        "time": "2026-08-16_13:00:00",
        "current_path": str(current),
        "prior_one_hour_path": str(prior),
        "current_sha256": current_sha,
        "prior_one_hour_sha256": prior_sha,
        "whole_file_exact": current_sha == prior_sha,
        "fields": {},
    }
    with netCDF4.Dataset(current) as new_ds, netCDF4.Dataset(prior) as old_ds:
        current_times = netCDF4.chartostring(new_ds["Times"][:]).tolist()
        prior_times = netCDF4.chartostring(old_ds["Times"][:]).tolist()
        assert current_times == ["2026-08-16_13:00:00"]
        assert prior_times == current_times
        report["fields"]["Times"] = {"exact": True, "value": current_times}
        for name in FIELDS:
            if name not in new_ds.variables or name not in old_ds.variables:
                report["fields"][name] = {"available": False}
                continue
            new_values = np.asarray(new_ds[name][:])
            old_values = np.asarray(old_ds[name][:])
            assert new_values.shape == old_values.shape, name
            exact = bool(np.array_equal(new_values, old_values))
            difference = np.abs(new_values.astype(np.float64) - old_values.astype(np.float64))
            report["fields"][name] = {
                "available": True,
                "shape": list(new_values.shape),
                "exact": exact,
                "unequal_values": int(np.count_nonzero(new_values != old_values)),
                "max_absolute_difference": float(np.max(difference)) if difference.size else 0.0,
            }
    report["comparison"] = "exact byte-for-byte" if report["whole_file_exact"] else "selected-field comparison"
    path = EVIDENCE / "one_hour_comparison.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
