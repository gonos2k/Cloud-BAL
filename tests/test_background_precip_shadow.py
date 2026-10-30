import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from netCDF4 import Dataset
import numpy as np

spec = importlib.util.spec_from_file_location('checker', Path(__file__).resolve().parents[1] /
                                              'tools/check_background_precip_shadow.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class BackgroundPrecipitationShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'shadow.nc'
        with Dataset(self.path, 'w') as ds:
            for dim in ('z', 'y', 'x'):
                ds.createDimension(dim, 2)
            ds.precipitation_research_policy = 'retain_background_v1'
            ds.configuration_id = 'real-background-precip-shadow-v1'
            ds.result_authority = 'DIAGNOSTIC_PROPOSAL_ONLY'
            ds.precipitation_transport_effective = 0
            ds.valid_time_epoch = np.int64(1786881600)
            ds.pipeline_status = ds.column_status = ds.balance_status = 20
            ds.acceptance_failures = 0
            for species in ('rain', 'snow', 'graupel', 'phase'):
                for suffix in ('', '_valid', '_quality', '_source'):
                    for state in ('background', 'candidate'):
                        dtype = 'f4' if species != 'phase' and not suffix else 'i4'
                        field = ds.createVariable(f'policy_{state}_{species}{suffix}', dtype, ('z','y','x'))
                        field[:] = 0
                        field.units = '1' if species == 'phase' or suffix else 'kg kg-1 dryair'
                        if not suffix:
                            field.valid_time = np.int64(1786881600)
                            if species == 'phase':
                                field.code_table = 'precipitation_phase_v1'
                if species != 'phase':
                    for state in ('background', 'candidate'):
                        ds.createVariable(f'{state}_{species}', 'f4', ('z','y','x'))[:] = 0
            ds.createVariable('hydro_support','i4',('z','y','x'))[:] = 0
            for name in ('flux_input', 'flux_deposited', 'flux_suspended', 'flux_boundary_exit',
                         'flux_terrain_intercept', 'flux_observation_blocked', 'flux_no_echo_blocked',
                         'flux_microphysical_loss', 'flux_ledger_error', 'candidate_endpoint_enthalpy_change_j',
                         'candidate_endpoint_geometry_mass_change_kg', 'candidate_endpoint_total_mass_error_kg',
                         'candidate_endpoint_max_cell_mass_error_kg', 'candidate_endpoint_dry_air_change_kg',
                         'candidate_endpoint_enthalpy_composition_change_j',
                         'candidate_endpoint_enthalpy_mass_metric_change_j'):
                ds.setncattr(name, 0.0)
            ds.candidate_endpoint_dry_mass_redistribution_kg = np.zeros(6)
            ds.candidate_endpoint_species_change_kg = np.zeros(6)
            ds.candidate_endpoint_mixing_ratio_change_kg = np.zeros(6)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_and_mutations(self):
        self.assertEqual(checker.check(self.path)['status'], 'PASS_SCOPED_BACKGROUND_PRECIPITATION')
        mutations = [('policy_candidate_snow', None), ('candidate_snow', None), ('policy_candidate_rain_source', None),
                     ('policy_candidate_phase_valid', None), ('hydro_support', None),
                     (None, 'flux_input'), (None, 'precipitation_transport_effective'),
                     (None, 'candidate_endpoint_enthalpy_change_j')]
        for var, attr in mutations:
            with self.subTest(var=var, attr=attr):
                with Dataset(self.path, 'r+') as ds:
                    if var:
                        ds[var][0,0,0] = 1
                    else:
                        ds.setncattr(attr, np.nan if 'enthalpy' in attr else 1)
                with self.assertRaises(ValueError):
                    checker.check(self.path)
                with Dataset(self.path, 'r+') as ds:
                    if var:
                        ds[var][0,0,0] = 0
                    else:
                        ds.setncattr(attr, 0)

    def test_changed_file_identity_rejected(self):
        with patch.object(checker, 'sha256', side_effect=('first', 'changed')):
            with self.assertRaisesRegex(ValueError, 'changed while being inspected'):
                checker.check(self.path)


if __name__ == '__main__':
    unittest.main()
