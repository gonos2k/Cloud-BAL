#!/usr/bin/env python3
"""Reject a forged local residual even when its aggregate receipt is updated."""
import shutil
import sys
import tempfile
from pathlib import Path

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import validate_interior_hydrostatic_assessment


def failures(path):
    errors = []
    with netCDF4.Dataset(path) as dataset:
        validate_interior_hydrostatic_assessment(
            dataset, lambda condition, message: errors.append(message) if not condition else None
        )
    return errors


def check(path):
    assert not failures(path), failures(path)
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "mutation.nc"
        for mutation in ("residual", "count", "dtype", "requested", "input", "unassessed",
                         "domain", "source", "declaration", "group", "valid_units",
                         "quality_units", "source_units", "metadata_packing",
                         "manufactured_source", "empty_invalid_mask"):
            shutil.copyfile(path, output)
            with netCDF4.Dataset(output, "r+") as dataset:
                group = dataset.groups["candidate_interior_hydrostatic_v1"]
                assessed = np.asarray(group["assessable"][:]).astype(bool)
                assert assessed.any(), "fixture must contain assessed interior layers"
                index = tuple(np.argwhere(assessed)[0])
                if mutation == "residual":
                    group["residual"][index] += 1.
                    altered = np.asarray(group["residual"][:])[assessed]
                    group.residual_rms_m2_s2 = np.float64(np.sqrt(np.mean(altered ** 2)))
                    group.residual_max_abs_m2_s2 = np.float64(np.max(np.abs(altered)))
                elif mutation == "count":
                    group.assessable_layers = np.int64(group.assessable_layers + 1)
                elif mutation == "dtype":
                    group.requested_layers = np.int32(group.requested_layers)
                elif mutation == "requested":
                    group["requested"][index] = 0
                elif mutation == "input":
                    group["temperature"][index] += 1.
                elif mutation == "domain":
                    group["above_ground"][index] = 0
                elif mutation == "source":
                    group["temperature_source"][index] = 0
                elif mutation.endswith("_units"):
                    group["temperature_" + mutation.removesuffix("_units")].units = "K"
                elif mutation == "metadata_packing":
                    group["temperature_valid"].scale_factor = np.float32(1.)
                elif mutation == "manufactured_source":
                    group["pressure_source"][index] = 1 << 12
                elif mutation == "empty_invalid_mask":
                    for name in ("requested", "assessable", "reason", "residual"):
                        group[name][:] = 0
                    dataset["candidate_diagnostic_requested_mask"][:] = 0
                    for name in ("requested_layers", "assessable_layers", "missing_support_layers",
                                 "nonfinite_layers", "range_layers", "shape_errors", "metadata_errors"):
                        group.setncattr(name, np.int64(0))
                    group.residual_rms_m2_s2 = np.float64(0.)
                    group.residual_max_abs_m2_s2 = np.float64(0.)
                elif mutation == "declaration":
                    dataset.schema_extensions = dataset.schema_extensions.replace(
                        ",candidate_interior_hydrostatic_v1", "")
                elif mutation == "group":
                    dataset.renameGroup("candidate_interior_hydrostatic_v1", "removed_hydrostatic")
                else:
                    group["assessable"][index] = 0
                    group["reason"][index] = 1
                    group["residual"][index] = 0.
                    altered = np.asarray(group["residual"][:])[group["assessable"][:] == 1]
                    group.assessable_layers = np.int64(group.assessable_layers - 1)
                    group.missing_support_layers = np.int64(group.missing_support_layers + 1)
                    group.residual_rms_m2_s2 = np.float64(np.sqrt(np.mean(altered ** 2)))
                    group.residual_max_abs_m2_s2 = np.float64(np.max(np.abs(altered)))
            if mutation == "empty_invalid_mask":
                assert not failures(output), "valid empty assessment must remain accepted"
                with netCDF4.Dataset(output, "r+") as dataset:
                    dataset.groups["candidate_interior_hydrostatic_v1"]["temperature_valid"][:] = 2
            assert failures(output), "accepted forged interior assessment: " + mutation
    print("Interior hydrostatic semantic readback and sixteen mutations passed:", path.name)


if __name__ == "__main__":
    check(Path(sys.argv[1]))
