"""Independent boundary-flux oracle for the declared native dry-mass weight.

The KIM advance_mu_t divergence carries MAPFAC_MX*MAPFAC_MY. Face
fluxes below already contain their native face metrics; this test does not
reconstruct velocities or certify a native timestep.
"""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_native_hybrid_geometry import hybrid_geometry


class NativeMassMetricTest(unittest.TestCase):
    def test_asymmetric_boundary_flux_and_internal_face_cancellation(self):
        dx, dy, gravity = 2., 3., 10.
        mapx = np.array([[1., 2., 4.], [2., 1., 2.]])
        mapy = np.array([[2., 1., 1.], [2., 4., 1.]])
        # Shared internal faces appear with opposite signs in adjacent cells.
        flux_u = np.array([[1., 7., -3., 5.], [2., -4., 9., 6.]])
        flux_v = np.array([[3., 1., 2.], [8., -5., 4.], [7., 4., 3.]])
        divergence = mapx * mapy * (
            np.diff(flux_u, axis=1) / dx + np.diff(flux_v, axis=0) / dy)
        # Independent exterior-only sum: east-west=8, north-south=8.
        boundary_mass_rate = -(dy * 8. + dx * 8.) / gravity
        fields = dict(mu=np.zeros((2, 3)), mub=np.full((2, 3), 100.),
                      c1h=np.ones(2), c2h=np.zeros(2),
                      dnw=np.array([-.5, -.5]), c3f=np.array([1., .5, 0.]),
                      c4f=np.zeros(3), znw=np.array([1., .5, 0.]),
                      p_top=20., dx=dx, dy=dy, mapx=mapx, mapy=mapy,
                      gravity=gravity)
        before = hybrid_geometry(**fields)
        dt = .125
        fields["mu"] = -dt * divergence
        after = hybrid_geometry(**fields)
        mass_rate = (after["dry_mass_kg"] - before["dry_mass_kg"]).sum() / dt
        self.assertAlmostEqual(float(mass_rate), boundary_mass_rate, places=12)
        # The active physics AREA2D=dx*dy is detectably the wrong weight here.
        wrong_rate = float((-dx * dy * divergence / gravity).sum())
        self.assertGreater(abs(wrong_rate - boundary_mass_rate), 1.)
        # Interior face changes cannot alter the exterior-only mass budget.
        flux_u[0, 1] += 11.
        flux_v[1, 2] -= 13.
        changed_divergence = mapx * mapy * (
            np.diff(flux_u, axis=1) / dx + np.diff(flux_v, axis=0) / dy)
        weighted_rate = float((-before["area_m2"] * changed_divergence / gravity).sum())
        self.assertAlmostEqual(weighted_rate, boundary_mass_rate, places=12)


if __name__ == "__main__":
    unittest.main()
