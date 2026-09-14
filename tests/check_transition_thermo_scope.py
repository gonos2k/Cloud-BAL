#!/usr/bin/env python3
"""Focused thermo-scope checks for the deferred pressure-transition probe."""

from pathlib import Path
import argparse
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validate_shadow_diagnostics as validator  # noqa: E402


THERMO_RESIDUALS = (
    "independent thermo temperature reconstruction",
    "independent thermo species reconstruction",
    "thermo per-cell water closure",
    "thermo per-cell enthalpy closure",
    "thermo final saturation closure",
    "species budget",
    "thermo_sensible_change_j budget",
    "thermo_phase_change_j budget",
    "thermo_water_error_kg budget",
    "thermo_enthalpy_error_j budget",
)


def _probe_inputs(dataset: netCDF4.Dataset) -> dict[str, object]:
    value = lambda name: validator.values(dataset[name])  # noqa: E731
    fields = {
        name: value(name)
        for name in (*validator.FLOAT_UNITS, *(f"{p}_{s}"
                                               for p in ("background", "candidate")
                                               for s in validator.THERMO_FIELDS))
    }
    masks = {name: value(name).astype(bool) for name in validator.MASKS}
    transition = {
        name: value(name)
        for name in validator.PRESSURE_TRANSITION_VARIABLES
    }
    phase_inputs = {
        name: value(name) for name in validator.RADAR_RECONSTRUCTION_VARIABLES
    }
    geometry = {
        name: value(name).astype(np.float64)
        for name in (
            "candidate_pressure_interface",
            "candidate_pressure_mass_measure",
            "candidate_dry_air_mass_measure",
        )
    }
    return {
        "fields": fields,
        "masks": masks,
        "pressure": value("pressure").astype(np.float64),
        "pressure_mass": value("pressure_mass_measure").astype(np.float64),
        "pressure_interface": value("pressure_interface").astype(np.float64),
        "dry_air_mass": value("dry_air_mass_measure").astype(np.float64),
        "geometry": geometry,
        "transition": transition,
        "phase_inputs": phase_inputs,
        "candidate_pressure_mass": geometry["candidate_pressure_mass_measure"],
        "schema7": int(getattr(dataset, "diagnostic_schema_version")) in (7, 8),
    }


def _thermo_call(path: Path, inputs: dict[str, object], replay=None):
    failures: list[str] = []

    def require(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    with netCDF4.Dataset(path) as dataset:
        fields = {name: array.copy() for name, array in inputs["fields"].items()}
        changed = validator.validate_thermo_extension(
            dataset,
            inputs["masks"]["above_ground"],
            inputs["masks"]["radar_no_echo"],
            inputs["pressure"],
            inputs["pressure_mass"],
            inputs["dry_air_mass"],
            fields,
            require,
            inputs["schema7"],
            candidate_pressure_mass=inputs["candidate_pressure_mass"],
            variable_geometry=True,
            transition_replay=replay,
        )
    return changed, failures


def _copy_without(source: Path, target: Path, omitted: str) -> None:
    with netCDF4.Dataset(source) as source_ds, netCDF4.Dataset(
        target, "w", format=source_ds.file_format
    ) as target_ds:
        for name, dimension in source_ds.dimensions.items():
            target_ds.createDimension(name, len(dimension))
        target_ds.setncatts({
            name: source_ds.getncattr(name)
            for name in source_ds.ncattrs()
        })
        for name, variable in source_ds.variables.items():
            if name == omitted:
                continue
            output = target_ds.createVariable(
                name, variable.datatype, variable.dimensions, fill_value=False
            )
            output.setncatts({
                attr: variable.getncattr(attr)
                for attr in variable.ncattrs()
                if attr != "_FillValue"
            })
            output[...] = variable[:]


def _targeted(failures: list[str]) -> list[str]:
    return [failure for failure in failures
            if any(marker in failure for marker in THERMO_RESIDUALS)]


def check(path: Path) -> None:
    with netCDF4.Dataset(path) as dataset:
        inputs = _probe_inputs(dataset)
        replay_failures: list[str] = []

        def require(condition: object, message: str) -> None:
            if not condition:
                replay_failures.append(message)

        replay = validator.build_pressure_transition_replay(
            dataset,
            inputs["fields"],
            inputs["masks"],
            inputs["pressure"],
            inputs["pressure_mass"],
            inputs["pressure_interface"],
            inputs["geometry"],
            inputs["transition"],
            inputs["phase_inputs"],
            require,
        )
        assert replay is not None, replay_failures
        assert not replay_failures, replay_failures
        assert set(replay) == {
            "proposal_species", "proposal_source", "post_temperature", "post_species", "post_mass",
            "post_valid", "candidate_above_ground", "final_mass",
            "final_temperature", "final_species",
        }
        support = validator.values(dataset["thermo_support"]).astype(bool)
        valid = np.all(replay["post_valid"].astype(bool), axis=0)
        active = valid & support & replay["candidate_above_ground"].astype(bool)
        active &= validator.values(dataset["candidate_vapor_valid"]).astype(bool)
        active &= validator.values(dataset["candidate_vapor_source"]) > 0
        cells = np.argwhere(active)
        assert cells.size, "probe has no valid thermo-transition cell"
        cell = tuple(int(index) for index in cells[0])

    with tempfile.TemporaryDirectory(prefix="transition-thermo-scope-") as directory:
        mutated = Path(directory) / "mutated.nc"
        shutil.copyfile(path, mutated)
        with netCDF4.Dataset(mutated, "r+") as dataset:
            dataset["candidate_temperature"][cell] += np.float32(1.0)
            dataset["candidate_vapor"][cell] += np.float32(0.01)

        _, ordinary_mutated_failures = _thermo_call(mutated, inputs)
        _, scoped_failures = _thermo_call(mutated, inputs, replay)
        # The ordinary path compares final fields with the thermo stage.  A
        # post-thermo T/q mutation must hit those targeted residual gates.
        assert _targeted(ordinary_mutated_failures), ordinary_mutated_failures
        # Scope consumes the retained poststate; unrelated full-reader gates
        # remain intentionally out of scope for this test.
        assert not _targeted(scoped_failures), scoped_failures
        assert "independent transition final temperature reconstruction" in scoped_failures
        assert "independent transition final species reconstruction" in scoped_failures

        missing = Path(directory) / "missing.nc"
        _copy_without(path, missing, "candidate_vapor_valid")
        _, failures = _thermo_call(missing, inputs, replay)
        assert any("candidate_vapor_valid variable" in failure for failure in failures)

        source = Path(directory) / "source.nc"
        shutil.copyfile(path, source)
        with netCDF4.Dataset(source, "r+") as dataset:
            dataset["candidate_vapor_source"][cell] = np.int32(0)
        _, failures = _thermo_call(source, inputs, replay)
        assert any("candidate vapor valid metadata usability" in failure
                   for failure in failures), failures

        units = Path(directory) / "units.nc"
        shutil.copyfile(path, units)
        with netCDF4.Dataset(units, "r+") as dataset:
            dataset["candidate_vapor"].units = "kg kg-1"
        _, failures = _thermo_call(units, inputs, replay)
        assert any("candidate_vapor units" in failure for failure in failures), failures

    print("Transition thermo scope checks passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", type=Path)
    check(parser.parse_args().probe)


if __name__ == "__main__":
    main()
