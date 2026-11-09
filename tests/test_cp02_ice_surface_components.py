import importlib.util
from pathlib import Path
import unittest
import numpy as np

p = Path(__file__).resolve().parents[1]/'tools/cp02_ice_surface_components.py'
spec = importlib.util.spec_from_file_location('surface', p)
surface = importlib.util.module_from_spec(spec)
spec.loader.exec_module(surface)


class SurfaceReplayTests(unittest.TestCase):
    def test_bilinear_and_temporal_order(self):
        a = np.zeros((1,7,2,4)); a[:,1:,0,:] = [1,2,3,8]; a[:,1:,1,:] = [4,3,2,1]
        components,total = surface.replay(a,np.array([.25]),np.array([.75]),1e-6)
        np.testing.assert_allclose(components[0,0], [3.5,2.25])
        self.assertAlmostEqual(total[0,0], 5.75)
        self.assertTrue(np.all(total[0,1:] == 0))

    def test_nonlinear_clamp_is_after_remap(self):
        a = np.ones((1,7,2,4)); a[:,1:,0,:] += [-5e-7, 5e-7, 5e-7, 5e-7]
        component,_ = surface.replay(a,np.array([.5]),np.array([.5]),1e-6)
        self.assertAlmostEqual(component[0,0,0], 2.5e-7)
        self.assertNotAlmostEqual(component[0,0,0], 3.75e-7, places=9)

    def test_invalid_reset_and_weights_fail(self):
        a = np.ones((1,7,2,4)); a[:,3:,0,0] = .5
        with self.assertRaisesRegex(ValueError, 'reset'): surface.replay(a,np.array([.5]),np.array([.5]),1e-6)
        a.fill(1)
        with self.assertRaisesRegex(ValueError, 'weights'): surface.replay(a,np.array([1.1]),np.array([.5]),1e-6)
        a[0,0,1,0] = np.nan
        with self.assertRaisesRegex(ValueError, 'invalid cumulative'): surface.replay(a,np.array([.5]),np.array([.5]),1e-6)

    def test_shape_and_negative_cumulative_fail(self):
        with self.assertRaisesRegex(ValueError, 'shape'): surface.replay(np.zeros((1,6,2,4)),np.array([.5]),np.array([.5]),1e-6)
        a=np.zeros((1,7,2,4)); a[0,0,0,0]=-1
        with self.assertRaisesRegex(ValueError, 'invalid cumulative'): surface.replay(a,np.array([.5]),np.array([.5]),1e-6)

if __name__ == '__main__': unittest.main()
