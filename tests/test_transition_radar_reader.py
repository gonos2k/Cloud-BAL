#!/usr/bin/env python3
"""Focused schema-gated tests for the radar reconstruction reader."""

from pathlib import Path
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import (  # noqa: E402
    RADAR_RECONSTRUCTION_VARIABLES,
    RADAR_RECONSTRUCTION_CONTRACT,
    SOURCE_PHASE_EVIDENCE,
    read_radar_reconstruction_extension,
)


SHAPE = (2, 1, 1)
EPOCH = 1_725_000_000


def write_fixture(path: Path, *, include_group: bool = True, bad_units: bool = False,
                  omit: str | None = None) -> None:
    with netCDF4.Dataset(path, "w") as dataset:
        for name, length in zip(("z", "y", "x"), SHAPE):
            dataset.createDimension(name, length)
        if not include_group:
            return
        dataset.setncattr("radar_reconstruction_contract", RADAR_RECONSTRUCTION_CONTRACT)
        dataset.setncattr("column_minimum_dbz", np.float64(10.0))
        data = {
            "background_precipitation_phase": np.array([[[1]], [[0]]], dtype=np.int32),
            "background_precipitation_phase_valid": np.array([[[1]], [[0]]], dtype=np.int32),
            "background_precipitation_phase_quality": np.zeros(SHAPE, dtype=np.int32),
            "background_precipitation_phase_source": np.array(
                [[[SOURCE_PHASE_EVIDENCE]], [[0]]], dtype=np.int32
            ),
        }
        for name in RADAR_RECONSTRUCTION_VARIABLES:
            if name == omit:
                continue
            variable = dataset.createVariable(name, "i4", ("z", "y", "x"))
            variable.units = "bad" if bad_units and name.endswith("quality") else "1"
            if name == "background_precipitation_phase":
                variable.valid_time = np.int64(EPOCH)
                variable.code_table = "precipitation_phase_v1"
            variable[:] = data[name]


def read(path: Path, *, schema8: bool, allow_transition: bool = False):
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    with netCDF4.Dataset(path) as dataset:
        result = read_radar_reconstruction_extension(
            dataset,
            SHAPE,
            EPOCH,
            schema8,
            require,
            allow_single_pass_transition=allow_transition,
        )
    return result, failures


def test_schema_gated_radar_reader() -> None:
    with tempfile.TemporaryDirectory(prefix="transition-radar-reader-") as directory:
        root = Path(directory)

        schema8 = root / "schema8.nc"
        write_fixture(schema8)
        (present, clean, phase), failures = read(schema8, schema8=True)
        assert present and clean and not failures
        assert phase["background_precipitation_phase"].shape == SHAPE

        reserved = root / "reserved-schema7.nc"
        write_fixture(reserved)
        (present, clean, _), failures = read(reserved, schema8=False)
        assert not present and not clean
        assert "schema8 radar reconstruction inputs are reserved for schema 8" in failures

        transition = root / "transition-schema7.nc"
        write_fixture(transition)
        (present, clean, _), failures = read(
            transition, schema8=False, allow_transition=True
        )
        assert present and clean and not failures

        malformed = root / "malformed.nc"
        write_fixture(malformed, bad_units=True)
        (present, clean, _), failures = read(
            malformed, schema8=False, allow_transition=True
        )
        assert present and not clean and failures

        missing = root / "missing.nc"
        write_fixture(missing, include_group=False)
        (present, clean, _), failures = read(
            missing, schema8=False, allow_transition=True
        )
        assert not present and not clean
        assert "single-pass transition requires radar reconstruction inputs" in failures


if __name__ == "__main__":
    test_schema_gated_radar_reader()
    print("Transition radar reader tests passed")
