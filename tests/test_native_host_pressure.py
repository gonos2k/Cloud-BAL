"""Bounded tests for the independent host-pressure diagnostic."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

import netCDF4
import numpy as np


TOOL = Path(__file__).resolve().parents[1] / "tools/check_native_hybrid_geometry.py"
spec = importlib.util.spec_from_file_location("native_geometry", TOOL)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def profile():
    return {
        "pressure": np.array([1000.0, 800.0, 600.0])[:, None, None],
        "temperature": np.full((3, 1, 1), 10.0),
        "vapor": np.full((3, 1, 1), 0.1),
        "height": np.array([0.0, 10.0, 20.0])[:, None, None],
        "terrain": np.array([[0.0]]),
        "average_surface_temperature": np.array([[10.0]]),
        "gravity": 10.0,
        "gas_constant": 100.0,
    }


def _field(dataset, name, dims, units, values):
    variable = dataset.createVariable(name, "f8", dims)
    variable.units = units
    variable[:] = values


def _write_reader_pair(directory):
    metgrid = Path(directory) / "metgrid.nc"
    native_path = Path(directory) / "native.nc"
    timestamp = "2026-09-01_03:00:00"
    pressure = np.array([[[[1000.0]], [[800.0]], [[600.0]]]])
    temperature = np.full((1, 3, 1, 1), 10.0)
    vapor = np.full((1, 3, 1, 1), 0.1)
    height = np.array([[[[0.0]], [[10.0]], [[20.0]]]])
    horizontal = ("Time", "south_north", "west_east")
    vertical = ("Time", "num_metgrid_levels", "south_north", "west_east")

    with netCDF4.Dataset(metgrid, "w") as dataset:
        for name, size in (("Time", 1), ("DateStrLen", len(timestamp)),
                           ("num_metgrid_levels", 3), ("south_north", 1),
                           ("west_east", 1)):
            dataset.createDimension(name, size)
        for flag in ("FLAG_QV", "FLAG_PSFC", "FLAG_SOILHGT", "FLAG_TAVGSFC"):
            setattr(dataset, flag, 1)
        dataset.FLAG_SH = 0
        times = dataset.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[:] = np.asarray(list(timestamp), dtype="S1")[None, :]
        _field(dataset, "PRES", vertical, "", pressure)
        _field(dataset, "TT", vertical, "K", temperature)
        _field(dataset, "QV", vertical, "kg kg{-1}", vapor)
        _field(dataset, "GHT", vertical, "m", height)
        _field(dataset, "PSFC", horizontal, "Pa", np.array([[[1000.0]]]))
        _field(dataset, "SOILHGT", horizontal, "m", np.array([[[0.0]]]))
        _field(dataset, "TAVGSFC", horizontal, "K", np.array([[[10.0]]]))
        _field(dataset, "XLAT_M", horizontal, "degrees latitude", np.array([[[35.0]]]))
        _field(dataset, "XLONG_M", horizontal, "degrees longitude", np.array([[[127.0]]]))

    with netCDF4.Dataset(native_path, "w") as dataset:
        for name, size in (("Time", 1), ("DateStrLen", len(timestamp)),
                           ("south_north", 1), ("west_east", 1)):
            dataset.createDimension(name, size)
        times = dataset.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[:] = np.asarray(list(timestamp), dtype="S1")[None, :]
        _field(dataset, "PSFC", horizontal, "Pa", np.array([[[1000.0]]]))
        _field(dataset, "MU", horizontal, "Pa", np.array([[[1000.0 - 160.0 / 11.0]]]))
        _field(dataset, "MUB", horizontal, "Pa", np.zeros((1, 1, 1)))
        _field(dataset, "HGT", horizontal, "m", np.array([[[0.0]]]))
        _field(dataset, "P_TOP", ("Time",), "Pa", np.array([0.0]))
        _field(dataset, "XLAT", horizontal, "degree_north", np.array([[[35.0]]]))
        _field(dataset, "XLONG", horizontal, "degree_east", np.array([[[127.0]]]))
    return metgrid, native_path


class HostPressureTest(unittest.TestCase):
    def test_literal_column_and_no_top_tail(self):
        result = native.host_pressure(**profile())
        expected_integral = 160.0 / 11.0
        np.testing.assert_allclose(result["native_surface_pressure_pa"], [[1000.0]])
        np.testing.assert_allclose(result["vapor_integral_pa"], [[expected_integral]])
        np.testing.assert_allclose(result["dry_surface_pressure_pa"],
                                   [[1000.0 - expected_integral]])

        case = profile()
        for name in ("pressure", "temperature", "vapor", "height"):
            case[name] = np.concatenate((case[name], case[name][-1:] + (200.0 if name == "height" else 0.0)))
        case["pressure"][-1] = 400.0
        case["height"][-1] = 30.0
        np.testing.assert_allclose(native.host_pressure(**case)["vapor_integral_pa"],
                                   [[210.0 / 11.0]])

    def test_terrain_subterrain_threshold_and_nonuniform_profiles(self):
        case = profile()
        for name in ("pressure", "temperature", "vapor", "height"):
            case[name] = np.repeat(case[name], 3, axis=2)
        case["terrain"] = np.array([[-5.0, 0.0, 5.0]])
        case["average_surface_temperature"] = np.full((1, 3), 10.0)
        result = native.host_pressure(**case)
        expected_ps = 1000.0 * np.exp(np.array([50.0, 0.0, -50.0]) / 1060.8)
        np.testing.assert_allclose(result["native_surface_pressure_pa"], expected_ps[None, :])
        np.testing.assert_allclose(result["vapor_integral_pa"], np.full((1, 3), 160.0 / 11.0))

        case = profile()
        case["pressure"] = np.array([1000.0, 1200.0, 800.0, 600.0])[:, None, None]
        case["temperature"] = np.full((4, 1, 1), 10.0)
        case["vapor"] = np.full((4, 1, 1), 0.1)
        case["height"] = np.array([0.0, -10.0, 10.0, 20.0])[:, None, None]
        np.testing.assert_allclose(native.host_pressure(**case)["vapor_integral_pa"],
                                   [[160.0 / 11.0]])

        case = profile()
        case["height"][:, 0, 0] = [0.0, 0.1, 10.0]
        np.testing.assert_allclose(native.host_pressure(**case)["vapor_integral_pa"],
                                   [[69.3 / 11.0]])

        case = profile()
        case["temperature"][:, 0, 0] = [10.0, 20.0, 40.0]
        case["vapor"][:, 0, 0] = [0.0, 0.2, 0.4]
        case["height"][:, 0, 0] = [0.0, 10.0, 25.0]
        expected = 70.0 / 11.0 + 495.0 / 52.0
        np.testing.assert_allclose(native.host_pressure(**case)["vapor_integral_pa"], [[expected]])

    def test_invalid_inputs_and_active_geometry(self):
        base = profile()
        shape_cases = {
            "pressure": np.ones((3, 1)),
            "temperature": np.ones((2, 1, 1)),
            "vapor": np.ones((3, 1, 2)),
            "height": np.ones((3, 1, 2)),
            "terrain": np.ones((2, 1)),
            "average_surface_temperature": np.ones((1, 2)),
        }
        for name, value in shape_cases.items():
            case = {key: np.array(item, copy=True) if isinstance(item, np.ndarray) else item
                    for key, item in base.items()}
            case[name] = value
            with self.subTest(kind="shape", name=name), self.assertRaises(ValueError):
                native.host_pressure(**case)

        for name in ("pressure", "temperature", "vapor", "height", "terrain",
                     "average_surface_temperature"):
            for value in (np.nan, np.inf):
                case = {key: np.array(item, copy=True) if isinstance(item, np.ndarray) else item
                        for key, item in base.items()}
                case[name].flat[0] = value
                with self.subTest(kind="nonfinite", name=name, value=value), self.assertRaises(ValueError):
                    native.host_pressure(**case)
        for name in ("gravity", "gas_constant"):
            for value in (np.nan, np.inf):
                case = dict(base, **{name: value})
                with self.subTest(kind="nonfinite", name=name, value=value), self.assertRaises(ValueError):
                    native.host_pressure(**case)

        for name in ("gravity", "gas_constant"):
            for value in (0.0, -1.0):
                case = dict(base, **{name: value})
                with self.subTest(kind="nonpositive", name=name, value=value), self.assertRaises(ValueError):
                    native.host_pressure(**case)
        for name in ("pressure", "temperature"):
            for value in (0.0, -1.0):
                case = {key: np.array(item, copy=True) if isinstance(item, np.ndarray) else item
                        for key, item in base.items()}
                case[name].flat[0] = value
                with self.subTest(kind="nonpositive", name=name, value=value), self.assertRaises(ValueError):
                    native.host_pressure(**case)
        for value in (-1.0e-3, 1.0):
            case = {key: np.array(item, copy=True) if isinstance(item, np.ndarray) else item
                    for key, item in base.items()}
            case["vapor"].flat[0] = value
            with self.subTest(kind="vapor-bound", value=value), self.assertRaises(ValueError):
                native.host_pressure(**case)

        case = profile()
        case["height"][:, 0, 0] = [0.0, 10.0, 9.0]
        with self.assertRaises(ValueError):
            native.host_pressure(**case)
        case = profile()
        case["pressure"][:, 0, 0] = [1000.0, 1300.0, 1200.0]
        with self.assertRaises(ValueError):
            native.host_pressure(**case)
        case = profile()
        case["pressure"][:, 0, 0] = [1000.0, 800.0, 800.0]
        with self.assertRaises(ValueError):
            native.host_pressure(**case)

    def test_valid_call_does_not_mutate_inputs(self):
        case = profile()
        before = {key: np.array(value, copy=True) if isinstance(value, np.ndarray) else value
                  for key, value in case.items()}
        native.host_pressure(**case)
        for key, value in before.items():
            if isinstance(value, np.ndarray):
                np.testing.assert_array_equal(case[key], value)
            else:
                self.assertEqual(case[key], value)

    def test_reader_success_and_small_mutations_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            metgrid, native_path = _write_reader_pair(directory)
            report = native.inspect_host_pressure(metgrid, native_path, 10.0, 100.0)
            self.assertEqual(report["host_pressure_result"], "PASS")
            self.assertEqual(report["valid_time"], "2026-09-01_03:00:00")
            self.assertTrue(report["input_unchanged"])

        mutations = ("FLAG_QV", "FLAG_PSFC", "FLAG_SOILHGT", "FLAG_TAVGSFC",
                     "FLAG_SH", "units", "time", "coordinate", "PSFC", "MU")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                metgrid, native_path = _write_reader_pair(directory)
                if mutation.startswith("FLAG_"):
                    with netCDF4.Dataset(metgrid, "a") as dataset:
                        setattr(dataset, mutation, 1 if mutation == "FLAG_SH" else 0)
                elif mutation == "units":
                    with netCDF4.Dataset(metgrid, "a") as dataset:
                        dataset["PSFC"].units = "hPa"
                elif mutation == "time":
                    with netCDF4.Dataset(native_path, "a") as dataset:
                        dataset["Times"][0, 0] = np.asarray("9", dtype="S1")
                elif mutation == "coordinate":
                    with netCDF4.Dataset(native_path, "a") as dataset:
                        dataset["XLAT"][0, 0, 0] = 36.0
                elif mutation == "PSFC":
                    with netCDF4.Dataset(native_path, "a") as dataset:
                        dataset["PSFC"][0, 0, 0] = 1001.0
                else:
                    with netCDF4.Dataset(native_path, "a") as dataset:
                        dataset["MU"][0, 0, 0] += 1.0
                with self.assertRaises(ValueError):
                    native.inspect_host_pressure(metgrid, native_path, 10.0, 100.0)


if __name__ == "__main__":
    unittest.main()
