import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/cp06a_state_force_flux.py"
SPEC = importlib.util.spec_from_file_location("cp06a_state_force_flux", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_state(path: Path) -> None:
    """Write a compact, nonuniform state/geometry fixture for the production builder."""
    with Dataset(path, "w") as ds:
        ds.createDimension("z", 2)
        ds.createDimension("zi", 3)
        ds.createDimension("y", 2)
        ds.createDimension("x", 2)
        ds.createDimension("latitude", 2)
        ds.grid_dx_m = 3.0
        ds.grid_dy_m = 4.0

        def put(name, dims, value, dtype="f8"):
            ds.createVariable(name, dtype, dims)[:] = value

        shape = (2, 2, 2)
        above = np.ones(shape, dtype=np.int32)
        pressure = np.broadcast_to(np.array([800.0, 400.0])[:, None, None], shape)
        interfaces = np.broadcast_to(np.array([1000.0, 600.0, 200.0])[:, None, None], (3, 2, 2))
        pressure_measure = np.full(shape, 100.0)
        dry_measure = np.full(shape, 80.0)
        cell_dp = np.full(shape, 400.0)
        put("above_ground", ("z", "y", "x"), above, "i4")
        put("pressure", ("z", "y", "x"), pressure)
        put("pressure_interface", ("zi", "y", "x"), interfaces)
        put("pressure_mass_measure", ("z", "y", "x"), pressure_measure)
        put("dry_air_mass_measure", ("z", "y", "x"), dry_measure)
        put("candidate_dry_air_mass_measure", ("z", "y", "x"), dry_measure)
        put("cell_dp", ("z", "y", "x"), cell_dp)
        put("background_u", ("z", "y", "x"), np.array([[[1., 2.], [3., 4.]], [[-1., 1.], [2., -2.]]]))
        put("background_v", ("z", "y", "x"), np.array([[[0.5, -1.], [2., 1.]], [[1., 3.], [-2., 0.5]]]))
        put("background_omega", ("z", "y", "x"), np.array([[[0.2, 0.4], [-0.3, 0.1]], [[-0.1, 0.5], [0.2, -0.4]]]))
        put("candidate_u", ("z", "y", "x"), np.zeros(shape))
        put("candidate_v", ("z", "y", "x"), np.zeros(shape))
        put("candidate_omega", ("z", "y", "x"), np.zeros(shape))
        put("omega_top_boundary", ("y", "x"), np.zeros((2, 2)))
        put("omega_bottom_boundary", ("y", "x"), np.zeros((2, 2)))
        put("omega_top_boundary_valid", ("y", "x"), np.ones((2, 2), dtype=np.int32), "i4")
        put("omega_bottom_boundary_valid", ("y", "x"), np.ones((2, 2), dtype=np.int32), "i4")


def make_staggered_overlap_state(path: Path) -> None:
    with Dataset(path, "w") as ds:
        for name, length in (("z", 2), ("zi", 3), ("y", 1), ("x", 2)):
            ds.createDimension(name, length)
        ds.grid_dx_m = 3.0
        ds.grid_dy_m = 4.0

        def put(name, dims, value, dtype="f8"):
            ds.createVariable(name, dtype, dims)[:] = value

        shape = (2, 1, 2)
        p_i = np.array([[[1000., 950.]], [[700., 650.]], [[400., 350.]]])
        put("above_ground", ("z", "y", "x"), np.ones(shape, dtype=np.int32), "i4")
        put("pressure", ("z", "y", "x"), np.array([[[850., 800.]], [[550., 500.]]]))
        put("pressure_interface", ("zi", "y", "x"), p_i)
        put("pressure_mass_measure", ("z", "y", "x"), np.full(shape, 100.))
        put("dry_air_mass_measure", ("z", "y", "x"), np.full(shape, 80.))
        put("cell_dp", ("z", "y", "x"), np.full(shape, 300.))
        put("background_u", ("z", "y", "x"), np.array([[[1., 3.]], [[2., 4.]]]))
        put("background_v", ("z", "y", "x"), np.zeros(shape))
        put("background_omega", ("z", "y", "x"), np.zeros(shape))
        put("candidate_u", ("z", "y", "x"), np.zeros(shape))
        put("candidate_v", ("z", "y", "x"), np.zeros(shape))
        put("candidate_omega", ("z", "y", "x"), np.zeros(shape))
        put("omega_top_boundary", ("y", "x"), np.zeros((1, 2)))
        put("omega_bottom_boundary", ("y", "x"), np.zeros((1, 2)))
        put("omega_top_boundary_valid", ("y", "x"), np.ones((1, 2), dtype=np.int32), "i4")
        put("omega_bottom_boundary_valid", ("y", "x"), np.ones((1, 2), dtype=np.int32), "i4")


class StateGeometryFluxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.nc"
        make_state(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_actual_builder_face_signs_and_global_boundary_integral(self):
        with Dataset(self.path) as ds:
            result = MODULE.independent_flux(ds, "background")
            self.assertEqual(int(np.count_nonzero(result["cell"])), 8)
            self.assertEqual(result["internal_lateral_face_pair_sum"], 0.0)
            self.assertEqual(result["internal_vertical_face_pair_sum"], 0.0)
            boundary = (np.sum(result["lateral_boundary_flux"]) +
                        np.sum(result["vertical_boundary_flux"]))
            self.assertAlmostEqual(result["global_flux_sum"], boundary, places=12)
            np.testing.assert_allclose(result["dry_fraction"], 0.8, rtol=0, atol=1e-15)
            u = np.asarray(ds.variables["background_u"][:])
            v = np.asarray(ds.variables["background_v"][:])
            omega = np.asarray(ds.variables["background_omega"][:])
            expected = np.zeros((2, 2, 2))
            x_area, y_area, z_area = 4 * 400 / MODULE.GRAVITY, 3 * 400 / MODULE.GRAVITY, 12 / MODULE.GRAVITY
            for k in range(2):
                for y in range(2):
                    flux = x_area * 0.5 * 0.8 * (u[k, y, 0] + u[k, y, 1])
                    expected[k, y, 0] += flux
                    expected[k, y, 1] -= flux
                    expected[k, y, 0] -= x_area * u[k, y, 0] * 0.8
                    expected[k, y, 1] += x_area * u[k, y, 1] * 0.8
                for x in range(2):
                    flux = y_area * 0.5 * 0.8 * (v[k, 0, x] + v[k, 1, x])
                    expected[k, 0, x] += flux
                    expected[k, 1, x] -= flux
                    expected[k, 0, x] -= y_area * v[k, 0, x] * 0.8
                    expected[k, 1, x] += y_area * v[k, 1, x] * 0.8
            vertical_flux = z_area * 0.5 * 0.8 * (omega[0] + omega[1])
            expected[0] -= vertical_flux
            expected[1] += vertical_flux
            np.testing.assert_allclose(result["divergence"], expected, rtol=2e-15, atol=2e-14)

    def test_actual_builder_is_linear_for_fixed_geometry(self):
        with Dataset(self.path, "r+") as ds:
            base_u = np.asarray(ds.variables["background_u"][:])
            base_v = np.asarray(ds.variables["background_v"][:])
            du = np.arange(8, dtype=float).reshape(2, 2, 2) / 7.0 - 0.4
            dv = np.flip(du, axis=1) * -0.3
            base = MODULE.independent_flux(
                ds, "candidate", wind_override=(base_u, base_v))["divergence"]
            delta = MODULE.independent_flux(ds, "candidate", wind_override=(du, dv))["divergence"]
            combined = MODULE.independent_flux(
                ds, "candidate", wind_override=(base_u + du, base_v + dv))["divergence"]
            np.testing.assert_allclose(combined - base, delta, rtol=2e-14, atol=2e-14)

    def test_actual_builder_transpose_matches_volume_metric_duality(self):
        with Dataset(self.path) as ds:
            state = MODULE.independent_flux(ds, "background")
            dual = np.array([[[0.2, -1.0], [0.7, 0.1]],
                             [[-0.4, 0.8], [1.2, -0.3]]])
            adj_u, adj_v, adj_omega = MODULE.independent_flux_adjoint(ds, "background", dual)
            lhs = np.sum(dual * state["divergence"])
            rhs = (np.sum(adj_u * ds.variables["background_u"][:]) +
                   np.sum(adj_v * ds.variables["background_v"][:]) +
                   np.sum(adj_omega * ds.variables["background_omega"][:]))
            self.assertAlmostEqual(lhs, rhs, places=12)

    def test_actual_builder_partitions_staggered_pressure_overlap(self):
        path = Path(self.temp.name) / "staggered.nc"
        make_staggered_overlap_state(path)
        with Dataset(path) as ds:
            result = MODULE.independent_flux(ds, "background")
            expected = np.array([[[-4 * 300 / MODULE.GRAVITY * .8 * 1.0,
                                   4 * 300 / MODULE.GRAVITY * .8 * 3.0]],
                                 [[-4 * 300 / MODULE.GRAVITY * .8 * 2.0,
                                   4 * 300 / MODULE.GRAVITY * .8 * 4.0]]])
            for left_k, right_k, overlap_dp in ((0, 0, 250.0), (1, 0, 50.0), (1, 1, 250.0)):
                face_flux = 4 * overlap_dp / MODULE.GRAVITY * .5 * .8 * (
                    ds.variables["background_u"][left_k, 0, 0] +
                    ds.variables["background_u"][right_k, 0, 1])
                expected[left_k, 0, 0] += face_flux
                expected[right_k, 0, 1] -= face_flux
            np.testing.assert_allclose(result["divergence"], expected, rtol=2e-15, atol=2e-14)
            self.assertEqual(result["internal_lateral_face_pair_sum"], 0.0)

    def test_wind_stream_reader_enforces_header_and_x_fastest_layout(self):
        artifact = Path(self.temp.name) / "retained_wind_v1.bin"
        shape = (2, 2, 2)
        u = np.arange(8, dtype="<f4")
        v = -u
        diagnostics = np.arange(11, dtype="<f8")
        with artifact.open("wb") as stream:
            np.array([1, 2, 2, 2], dtype="<i4").tofile(stream)
            u.tofile(stream)
            v.tofile(stream)
            diagnostics.tofile(stream)
        actual_u, actual_v, actual_diag = MODULE.read_wind_artifact(artifact, shape)
        np.testing.assert_array_equal(actual_u, u.reshape(shape))
        np.testing.assert_array_equal(actual_v, v.reshape(shape))
        np.testing.assert_array_equal(actual_diag, diagnostics)
        artifact.write_bytes(artifact.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "size"):
            MODULE.read_wind_artifact(artifact, shape)


if __name__ == "__main__":
    unittest.main()
