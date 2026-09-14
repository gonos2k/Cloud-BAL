#!/usr/bin/env python3
"""Check the existing 24-hour TAVGSFC producer against its actual inputs."""
from datetime import datetime, timedelta
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_baseline import read_wps


def check(output: Path, background: Path, start: datetime) -> None:
    records = read_wps(output)
    # WPS constants use the original producer's timeless header. The explicit
    # input window below, not that header, identifies the averaging period.
    assert set(records) == {("TAVGSFC", 200100.0, "0000-00-00_00:00:00")}
    units, shape, actual, metadata = next(iter(records.values()))
    assert units == "K" and shape == (235, 283)
    assert np.isfinite(actual).all()
    samples = []
    for hour in range(0, 24, 3):
        time = start + timedelta(hours=hour)
        source = read_wps(background / ("KLBG:" + time.strftime("%Y-%m-%d_%H:%M")))
        key = ("T", 200100.0, time.strftime("%Y-%m-%d_%H:%M:%S"))
        source_units, source_shape, values, source_metadata = source[key]
        assert source_units == units and source_shape == shape
        assert source_metadata == metadata
        assert np.isfinite(values).all() and np.all((values > 150) & (values < 350))
        samples.append(values)

    samples = np.stack(samples)
    expected = samples.mean(axis=0, dtype=np.float64)
    # Standard float32 accumulation bound; no result-derived tuning.
    epsilon = np.finfo(np.float32).eps
    gamma = len(samples) * epsilon / (1.0 - len(samples) * epsilon)
    tolerance = gamma * np.mean(np.abs(samples), axis=0) + epsilon * np.abs(expected)
    assert np.all(np.abs(actual - expected) <= tolerance), "incorrect surface mean"
    damaged = actual.copy()
    damaged[0] += 1.0
    assert not np.all(np.abs(damaged - expected) <= tolerance), "ineffective mean check"
    print(f"PASS TAVGSFC: 8 actual surface fields, 66505 cells, "
          f"max error {np.max(np.abs(actual - expected)):.9g} K; +1 K mutation rejected")


if __name__ == "__main__":
    check(Path(sys.argv[1]), Path(sys.argv[2]), datetime.fromisoformat(sys.argv[3]))
