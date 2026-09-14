"""Independent small hybrid-column constants and read-only input rejection."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import netCDF4
import numpy as np

TOOL = Path(__file__).resolve().parents[1] / 'tools/check_native_hybrid_geometry.py'
spec = importlib.util.spec_from_file_location('native_geometry', TOOL)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def fixture():
    # p0-pt=100; eta=(1,.75,.25,0), B=(1,.5,0,0).
    # Two distinct terrain columns and map metrics; literal independent answers below.
    return dict(mu=np.array([[-5., 5.]]), mub=np.array([[85., 95.]]),
                c1h=np.array([2., 1., 0.]), c2h=np.array([-100., 0., 100.]),
                dnw=np.array([-.25, -.5, -.25]), c3f=np.array([1., .5, 0., 0.]),
                c4f=np.array([0., 25., 25., 0.]), znw=np.array([1., .75, .25, 0.]),
                p_top=20., dx=2., dy=3., mapx=np.array([[1., 2.]]),
                mapy=np.array([[1., 1.]]), gravity=10.)


def write_fixture(path):
    f = fixture()
    with netCDF4.Dataset(path, 'w') as d:
        for name, size in [('Time', 1), ('bottom_top', 3), ('bottom_top_stag', 4),
                           ('south_north', 1), ('west_east', 2)]:
            d.createDimension(name, size)
        d.HYBRID_OPT = 2; d.GRIDTYPE = 'C'; d.DX = 2.; d.DY = 3.
        d.TITLE = 'SYNTHETIC HYBRID ORACLE'; d.START_DATE = '2000-01-01_00:00:00'
        for key, value in f.items():
            if key in ('dx', 'dy', 'gravity'):
                continue
            name = {'mapx': 'MAPFAC_MX', 'mapy': 'MAPFAC_MY'}.get(key, key.upper())
            dims = ('Time', 'south_north', 'west_east')
            if key in ('c1h', 'c2h', 'dnw'): dims = ('Time', 'bottom_top')
            if key in ('c3f', 'c4f', 'znw'): dims = ('Time', 'bottom_top_stag')
            if key == 'p_top': dims = ('Time',)
            var = d.createVariable(name, 'f4', dims)
            var.units = ('Pa' if key in ('mu', 'mub', 'c2h', 'c4f', 'p_top')
                         else 'Dimensionless' if key in ('c1h', 'c3f') else '')
            var[0] = value


WATER_SPECIES = ('QVAPOR', 'QCLOUD', 'QICE', 'QRAIN', 'QSNOW', 'QGRAUP')
PAIR_TIME = '2000-01-01_00:00:00'


def species_values(*, vapor=.02, cloud=.01, ice=0., rain=0., snow=0., graupel=0.):
    values = (vapor, cloud, ice, rain, snow, graupel)
    return {name: np.full((3, 1, 2), value, dtype=np.float64)
            for name, value in zip(WATER_SPECIES, values)}


def write_native_pair_file(path, *, species=None, times=PAIR_TIME,
                           xlat=None, xlong=None, omit_species=()):
    """Write one complete, same-grid native comparison fixture."""
    write_fixture(path)
    species = species or species_values()
    xlat = np.asarray(xlat if xlat is not None else [[[35., 35.1]]], dtype=np.float64)
    xlong = np.asarray(xlong if xlong is not None else [[[127., 127.1]]], dtype=np.float64)
    with netCDF4.Dataset(path, 'a') as d:
        d.createDimension('DateStrLen', len(times))
        time_var = d.createVariable('Times', 'S1', ('Time', 'DateStrLen'))
        time_var[:] = np.asarray(list(times), dtype='S1')[None, :]
        for name, units, values in (('XLAT', 'degree_north', xlat),
                                    ('XLONG', 'degree_east', xlong)):
            var = d.createVariable(name, 'f4', ('Time', 'south_north', 'west_east'))
            var.units = units
            var[:] = values
        dims = ('Time', 'bottom_top', 'south_north', 'west_east')
        for name in WATER_SPECIES:
            if name in omit_species:
                continue
            var = d.createVariable(name, 'f4', dims)
            var.units = 'kg kg-1'
            var[:] = np.asarray(species[name], dtype=np.float32)[None, ...]


def write_native_pair(baseline, candidate, *, baseline_species=None,
                      candidate_species=None, baseline_times=PAIR_TIME,
                      candidate_times=PAIR_TIME, baseline_xlat=None,
                      candidate_xlat=None, baseline_xlong=None,
                      candidate_xlong=None, baseline_omit_species=(),
                      candidate_omit_species=()):
    write_native_pair_file(
        baseline, species=baseline_species, times=baseline_times,
        xlat=baseline_xlat, xlong=baseline_xlong,
        omit_species=baseline_omit_species)
    write_native_pair_file(
        candidate, species=candidate_species, times=candidate_times,
        xlat=candidate_xlat, xlong=candidate_xlong,
        omit_species=candidate_omit_species)


def _set_times(path, value):
    with netCDF4.Dataset(path, 'a') as dataset:
        dataset['Times'][:] = np.asarray(list(value), dtype='S1')[None, :]


def _mask_time(path):
    with netCDF4.Dataset(path, 'a') as dataset:
        dataset['Times'][0, 0] = np.ma.masked


def _set_units(path, name, value):
    with netCDF4.Dataset(path, 'a') as dataset:
        dataset[name].units = value


def _set_global(path, name, value):
    with netCDF4.Dataset(path, 'a') as dataset:
        setattr(dataset, name, value)


def _mutate_coordinate(path, name):
    with netCDF4.Dataset(path, 'a') as dataset:
        dataset[name][0, 0, 0] += .1


def _mutate_field(path, name):
    with netCDF4.Dataset(path, 'a') as dataset:
        dataset[name][0, 0, 0] += .1


def _mutate_species(path, value):
    with netCDF4.Dataset(path, 'a') as dataset:
        dataset['QVAPOR'][0, 0, 0, 0] = value


class HybridOracleTest(unittest.TestCase):
    def test_literal_columns_and_asymmetric_impulse(self):
        result = native.hybrid_geometry(**fixture())
        np.testing.assert_allclose(result['dp_pa'][:, 0], [[15, 25], [40, 50], [25, 25]], rtol=0, atol=1e-10)
        np.testing.assert_allclose(result['interface_pa'][:, 0], [[100, 120], [85, 95], [45, 45], [20, 20]], rtol=0, atol=1e-10)
        np.testing.assert_allclose(result['dry_mass_kg'][:, 0], [[9, 7.5], [24, 15], [15, 7.5]], rtol=0, atol=1e-10)
        f = fixture(); f['mu'][0, 1] += 4
        changed = native.hybrid_geometry(**f)['dry_mass_kg'] - result['dry_mass_kg']
        np.testing.assert_allclose(changed[:, 0], [[0, .6], [0, .6], [0, 0]], rtol=0, atol=1e-10)

    def test_moist_dry_mass_conventions_are_not_interchangeable(self):
        mass = native.hybrid_geometry(**fixture())['dry_mass_kg']
        # Native dry mass stays 78 kg; internal phase transfer preserves total water.
        rv, rc = .02, .01
        self.assertAlmostEqual(float(mass.sum()), 78)
        self.assertAlmostEqual(float((mass * (rv + rc)).sum()), 2.34)
        self.assertAlmostEqual(float((mass * ((rv + .005) + (rc - .005))).sum()), 2.34)
        # External +.01 dry mixing-ratio increment belongs in A_Q, not dry mass.
        self.assertAlmostEqual(float((mass * .01).sum()), .78)
        self.assertLess(float((mass / (1 + rv + rc)).sum()), 78)

    def test_reject_bad_arrays(self):
        for name in fixture():
            for invalid in (np.nan, np.inf):
                f = fixture(); a = np.array(f[name], copy=True); a.flat[0] = invalid; f[name] = a
                with self.subTest(name=name, invalid=invalid), self.assertRaises(ValueError):
                    native.hybrid_geometry(**f)
        changes = [('dnw', np.array([.25, -.5, -.25])), ('znw', np.array([1., .8, .25, 0.])),
                   ('c1h', np.array([2.1, 1., 0.])), ('c4f', np.array([0., 25., 25., 2.])),
                   ('c2h', np.zeros(2)), ('mapx', np.zeros((1, 2))), ('mapy', np.ones((2, 1))),
                   ('mu', np.full((1, 2), -200)), ('gravity', 0), ('dx', -1),
                   ('mub', np.ma.array([[85., 95.]], mask=[[True, False]]))]
        for name, value in changes:
            f = fixture(); f[name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                native.hybrid_geometry(**f)

    def test_netcdf_readonly_and_rejections(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'fixture.nc'; write_fixture(path)
            before = native.digest(path)
            report = native.inspect(path, 10.)
            self.assertEqual(before, native.digest(path))
            self.assertTrue(report['input_unchanged'])
            self.assertFalse(report['promotion_eligible'])
            self.assertEqual(report['native_authority'], 'NONE')
            self.assertEqual(report['diagnostic_dry_mass_sum_kg'], 78.)
            for name, attribute, value, restore in [('MU', 'units', 'hPa', 'Pa'),
                                                   (None, 'HYBRID_OPT', 1, 2)]:
                with netCDF4.Dataset(path, 'a') as d:
                    setattr(d if name is None else d[name], attribute, value)
                with self.assertRaises(ValueError): native.inspect(path, 10.)
                with netCDF4.Dataset(path, 'a') as d:
                    setattr(d if name is None else d[name], attribute, restore)
            with netCDF4.Dataset(path, 'a') as d: d['MU'][0, 0, 0] = np.ma.masked
            with self.assertRaises(ValueError): native.inspect(path, 10.)

    def test_compare_nochange_reports_literal_species_masses(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / 'baseline.nc'
            candidate = Path(temp) / 'candidate.nc'
            write_native_pair(baseline, candidate)
            report = native.compare(baseline, candidate, 10.)

        self.assertAlmostEqual(report['dry_mass_change_kg'], 0., places=7)
        self.assertFalse(report['conservation_assessed'])
        self.assertFalse(report['promotion_eligible'])
        self.assertEqual(set(report['water_by_species']), set(WATER_SPECIES))
        expected = {
            'QVAPOR': 1.56,
            'QCLOUD': .78,
            'QICE': 0.,
            'QRAIN': 0.,
            'QSNOW': 0.,
            'QGRAUP': 0.,
        }
        for name, entry in report['water_by_species'].items():
            with self.subTest(species=name):
                self.assertAlmostEqual(entry['baseline_kg'], expected[name], places=6)
                self.assertAlmostEqual(entry['candidate_kg'], expected[name], places=6)
                self.assertAlmostEqual(entry['change_kg'], 0., places=6)
                self.assertAlmostEqual(entry['composition_change_kg'], 0., places=6)
                self.assertAlmostEqual(entry['mass_metric_change_kg'], 0., places=6)

    def test_compare_vapor_transfer_cancels_at_fixed_mass(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / 'baseline.nc'
            candidate = Path(temp) / 'candidate.nc'
            write_native_pair(
                baseline, candidate,
                baseline_species=species_values(vapor=.02, cloud=.01),
                candidate_species=species_values(vapor=.015, cloud=.015),
            )
            report = native.compare(baseline, candidate, 10.)

        self.assertAlmostEqual(report['dry_mass_change_kg'], 0., places=7)
        vapor = report['water_by_species']['QVAPOR']
        cloud = report['water_by_species']['QCLOUD']
        self.assertAlmostEqual(vapor['baseline_kg'], 1.56, places=6)
        self.assertAlmostEqual(vapor['candidate_kg'], 1.17, places=6)
        self.assertAlmostEqual(vapor['change_kg'], -.39, places=6)
        self.assertAlmostEqual(vapor['composition_change_kg'], -.39, places=6)
        self.assertAlmostEqual(vapor['mass_metric_change_kg'], 0., places=6)
        self.assertAlmostEqual(cloud['baseline_kg'], .78, places=6)
        self.assertAlmostEqual(cloud['candidate_kg'], 1.17, places=6)
        self.assertAlmostEqual(cloud['change_kg'], .39, places=6)
        self.assertAlmostEqual(cloud['composition_change_kg'], .39, places=6)
        self.assertAlmostEqual(cloud['mass_metric_change_kg'], 0., places=6)
        self.assertAlmostEqual(
            sum(entry['change_kg'] for entry in report['water_by_species'].values()),
            0., places=6)

    def test_compare_decomposes_mass_change_and_species_change(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / 'baseline.nc'
            candidate = Path(temp) / 'candidate.nc'
            write_native_pair(
                baseline, candidate,
                candidate_species=species_values(vapor=.03, cloud=.01),
            )
            with netCDF4.Dataset(candidate, 'a') as dataset:
                dataset['MU'][0, 0, 1] += 4.
            report = native.compare(baseline, candidate, 10.)

        self.assertAlmostEqual(report['dry_mass_change_kg'], 1.2, places=6)
        vapor = report['water_by_species']['QVAPOR']
        self.assertAlmostEqual(vapor['baseline_kg'], 1.56, places=6)
        self.assertAlmostEqual(vapor['candidate_kg'], 2.376, places=6)
        self.assertAlmostEqual(vapor['change_kg'], .816, places=6)
        self.assertAlmostEqual(vapor['composition_change_kg'], .78, places=6)
        self.assertAlmostEqual(vapor['mass_metric_change_kg'], .036, places=6)
        self.assertAlmostEqual(
            vapor['change_kg'],
            vapor['composition_change_kg'] + vapor['mass_metric_change_kg'],
            places=6)

    def test_compare_rejects_time_coordinate_and_metric_mismatch(self):
        mutations = {
            'time value': lambda path: _set_times(path, '2000-01-01_00:00:01'),
            'XLAT value': lambda path: _mutate_coordinate(path, 'XLAT'),
            'XLONG value': lambda path: _mutate_coordinate(path, 'XLONG'),
            'XLAT units': lambda path: _set_units(path, 'XLAT', 'degrees_north'),
            'XLONG units': lambda path: _set_units(path, 'XLONG', 'degrees_eastward'),
            'DX': lambda path: _set_global(path, 'DX', 2.1),
            'DY': lambda path: _set_global(path, 'DY', 3.1),
            'MAPFAC_MX': lambda path: _mutate_field(path, 'MAPFAC_MX'),
            'MAPFAC_MY': lambda path: _mutate_field(path, 'MAPFAC_MY'),
        }
        for label, mutation in mutations.items():
            with self.subTest(mismatch=label), tempfile.TemporaryDirectory() as temp:
                baseline = Path(temp) / 'baseline.nc'
                candidate = Path(temp) / 'candidate.nc'
                write_native_pair(baseline, candidate)
                mutation(candidate)
                with self.assertRaises(ValueError):
                    native.compare(baseline, candidate, 10.)

    def test_compare_rejects_malformed_or_masked_identical_times(self):
        cases = {
            'malformed': lambda baseline, candidate: (
                _set_times(baseline, 'X' * 19),
                _set_times(candidate, 'X' * 19)),
            'masked': lambda baseline, candidate: (
                _mask_time(baseline), _mask_time(candidate)),
        }
        for label, mutation in cases.items():
            with self.subTest(time_contract=label), tempfile.TemporaryDirectory() as temp:
                baseline = Path(temp) / 'baseline.nc'
                candidate = Path(temp) / 'candidate.nc'
                write_native_pair(baseline, candidate)
                mutation(baseline, candidate)
                with self.assertRaises(ValueError):
                    native.compare(baseline, candidate, 10.)

    def test_compare_rejects_missing_and_invalid_species(self):
        cases = {
            'missing': lambda path: None,
            'units': lambda path: _set_units(path, 'QVAPOR', 'kg kg-1 moistair'),
            'masked': lambda path: _mutate_species(path, np.ma.masked),
            'negative': lambda path: _mutate_species(path, -.01),
            'nonfinite': lambda path: _mutate_species(path, np.nan),
        }
        for label, mutation in cases.items():
            with self.subTest(species_contract=label), tempfile.TemporaryDirectory() as temp:
                baseline = Path(temp) / 'baseline.nc'
                candidate = Path(temp) / 'candidate.nc'
                if label == 'missing':
                    write_native_pair(
                        baseline, candidate, candidate_omit_species=('QRAIN',))
                else:
                    write_native_pair(baseline, candidate)
                    mutation(candidate)
                # Missing variables surface as an indexing error in the NetCDF API;
                # all present-but-invalid fields are ValueError rejections.
                with self.assertRaises((ValueError, KeyError, IndexError)):
                    native.compare(baseline, candidate, 10.)


if __name__ == '__main__':
    unittest.main()
