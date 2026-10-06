#!/usr/bin/env python3
"""Focused structural and content checks for optional cloud provenance."""

from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import (  # noqa: E402
    CLOUD_ANALYSIS_ATTRIBUTES,
    CLOUD_ANALYSIS_CONTRACT,
    CLOUD_ANALYSIS_FIELDS,
    CLOUD_ANALYSIS_MASK_ENCODING,
    CLOUD_ANALYSIS_VARIABLES,
    SOURCE_CLOUD_ANALYSIS,
    SOURCE_RADAR_DBZ,
    SOURCE_MANUFACTURED_TEST,
    validate_cloud_analysis_provenance,
)


SHAPE = (2, 1, 1)
EPOCH = 1_725_000_000


def write_fixture(path: Path, *, present: bool = True, wrong_fraction_type: bool = False,
                  wrong_dimensions: bool = False, cloud_values_valid: bool = True,
                  phase_cloud_evidence: bool | None = None,
                  omit: str | None = None) -> None:
    with netCDF4.Dataset(path, "w") as dataset:
        for name, length in zip(("z", "y", "x"), SHAPE):
            dataset.createDimension(name, length)
        dataset.setncattr("valid_time_epoch", np.int64(EPOCH))
        dataset.setncattr("cloud_analysis_present", np.int32(present))
        if not present:
            return
        dataset.setncattr("cloud_analysis_contract", CLOUD_ANALYSIS_CONTRACT)
        dataset.setncattr("cloud_analysis_mask_encoding", CLOUD_ANALYSIS_MASK_ENCODING)
        above = dataset.createVariable("above_ground", "i4", ("z", "y", "x"))
        above.units = "1"
        above[:] = np.ones(SHAPE, dtype=np.int32)

        if phase_cloud_evidence is not None:
            phase_data = {
                "background_precipitation_phase": np.full(
                    SHAPE, 1 if phase_cloud_evidence else 0, dtype=np.int32
                ),
                "background_precipitation_phase_valid": np.ones(SHAPE, dtype=np.int32),
                "background_precipitation_phase_quality": np.zeros(SHAPE, dtype=np.int32),
                "background_precipitation_phase_source": np.full(
                    SHAPE, SOURCE_CLOUD_ANALYSIS if phase_cloud_evidence else SOURCE_RADAR_DBZ,
                    dtype=np.int32,
                ),
            }
            for name, value in phase_data.items():
                variable = dataset.createVariable(name, "i4", ("z", "y", "x"))
                variable.units = "1"
                variable[:] = value

        for field, (dtype, _units, code_table) in CLOUD_ANALYSIS_FIELDS.items():
            for suffix in ("", "_valid", "_quality", "_source"):
                name = field + suffix
                if name == omit:
                    continue
                dimensions = ("x", "y", "z") if wrong_dimensions and name == field else (
                    "z", "y", "x"
                )
                variable_type = (
                    "f8" if wrong_fraction_type and field.endswith("fraction") and suffix == ""
                    else "f4" if dtype == np.dtype(np.float32) and suffix == ""
                    else "i4"
                )
                variable = dataset.createVariable(name, variable_type, dimensions)
                variable.units = "1"
                if suffix == "":
                    variable.valid_time = np.int64(EPOCH)
                    if code_table is not None:
                        variable.code_table = code_table
                elif suffix == "_valid":
                    variable.mask_encoding = "0=invalid,1=valid"
                elif suffix == "_quality":
                    variable.mask_encoding = "canonical_quality_bits_v1"
                else:
                    variable.mask_encoding = "canonical_source_bits_v1"

                value = (
                    np.full(SHAPE, 0.5, dtype=np.float32)
                    if field.endswith("fraction") and suffix == ""
                    else np.full(SHAPE, 1, dtype=np.int32)
                    if field.endswith("type") and suffix == ""
                    else np.full(SHAPE, int(cloud_values_valid), dtype=np.int32)
                    if suffix == "_valid"
                    else np.zeros(SHAPE, dtype=np.int32)
                    if suffix == "_quality"
                    else np.full(
                        SHAPE,
                        SOURCE_CLOUD_ANALYSIS if cloud_values_valid else 0,
                        dtype=np.int32,
                    )
                )
                variable[:] = np.transpose(value, (2, 1, 0)) if dimensions != ("z", "y", "x") else value


def validate(path: Path) -> tuple[bool, bool, list[str]]:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    with netCDF4.Dataset(path) as dataset:
        present, clean = validate_cloud_analysis_provenance(dataset, require)
    return present, clean, failures


def test_cloud_provenance_receipt() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-provenance-receipt-") as directory:
        root = Path(directory)
        absent = root / "absent.nc"
        write_fixture(absent, present=False)
        assert validate(absent) == (False, True, [])

        valid = root / "present.nc"
        write_fixture(valid)
        assert validate(valid) == (True, True, [])

        phase_evidence = root / "phase-evidence.nc"
        write_fixture(phase_evidence, cloud_values_valid=False, phase_cloud_evidence=True)
        assert validate(phase_evidence) == (True, True, [])

        known_source = root / "known-source.nc"
        shutil.copyfile(valid, known_source)
        with netCDF4.Dataset(known_source, "r+") as dataset:
            dataset["background_cloud_fraction_source"][:] = SOURCE_RADAR_DBZ
        assert validate(known_source) == (True, True, [])

        unsupported = root / "unsupported-present.nc"
        write_fixture(unsupported, cloud_values_valid=False, phase_cloud_evidence=False)
        present, clean, failures = validate(unsupported)
        assert present and not clean and failures

        malformed_builders = (
            ("wrong value dtype", {"wrong_fraction_type": True}),
            ("wrong dimensions", {"wrong_dimensions": True}),
        )
        for index, (label, options) in enumerate(malformed_builders):
            path = root / f"malformed-{index}.nc"
            write_fixture(path, **options)
            present, clean, failures = validate(path)
            assert present and not clean and failures, label

        mutations = (
            ("flag", "attribute", "cloud_analysis_present", np.int32(0)),
            ("flag dtype", "attribute", "cloud_analysis_present", np.float32(1)),
            ("contract", "attribute", "cloud_analysis_contract", "wrong_contract"),
            ("mask contract", "attribute", "cloud_analysis_mask_encoding", "wrong"),
            ("value units", "variable_attr", "background_cloud_fraction", ("units", "kg kg-1")),
            ("field time", "variable_attr", "background_cloud_fraction", ("valid_time", np.int64(EPOCH + 1))),
            ("code table", "variable_attr", "background_cloud_type", ("code_table", "wrong")),
            ("valid encoding", "variable_attr", "background_cloud_type_valid", ("mask_encoding", "wrong")),
            ("unknown source bit", "cell", "background_cloud_fraction_source", np.int32(1 << 20)),
            ("manufactured fraction", "cell", "background_cloud_fraction_source", np.int32(SOURCE_MANUFACTURED_TEST)),
            ("manufactured type", "cell", "background_cloud_type_source", np.int32(SOURCE_MANUFACTURED_TEST)),
            ("unknown quality bit", "cell", "background_cloud_type_quality", np.int32(1 << 20)),
            ("invalid valid mask", "cell", "background_cloud_fraction_valid", np.int32(2)),
            ("fraction range", "cell", "background_cloud_fraction", np.float32(1.1)),
            ("type range", "cell", "background_cloud_type", np.int32(12)),
        )
        for index, (label, kind, name, payload) in enumerate(mutations):
            path = root / f"mutation-{index}.nc"
            shutil.copyfile(valid, path)
            with netCDF4.Dataset(path, "r+") as dataset:
                if kind == "attribute":
                    dataset.setncattr(name, payload)
                elif kind == "variable_attr":
                    attribute, value = payload
                    dataset[name].setncattr(attribute, value)
                else:
                    dataset[name][0, 0, 0] = payload
            present, clean, failures = validate(path)
            assert present and not clean and failures, label

        missing = root / "missing-field.nc"
        write_fixture(missing, omit=CLOUD_ANALYSIS_VARIABLES[-1])
        present, clean, failures = validate(missing)
        assert present and not clean and failures
        manufactured_phase = root / "manufactured-phase.nc"
        shutil.copyfile(phase_evidence, manufactured_phase)
        with netCDF4.Dataset(manufactured_phase, "r+") as dataset:
            dataset["background_precipitation_phase_source"][:] = (
                SOURCE_CLOUD_ANALYSIS | SOURCE_MANUFACTURED_TEST
            )
        present, clean, failures = validate(manufactured_phase)
        assert present and not clean and failures
        assert set(CLOUD_ANALYSIS_ATTRIBUTES) == {
            "cloud_analysis_contract", "cloud_analysis_mask_encoding"
        }


if __name__ == "__main__":
    test_cloud_provenance_receipt()
    print("Cloud provenance receipt tests passed")
