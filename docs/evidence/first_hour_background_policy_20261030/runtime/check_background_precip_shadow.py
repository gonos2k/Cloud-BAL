#!/usr/bin/env python3
"""Check a retained-precipitation diagnostic; this is not the general SHADOW validator."""
import argparse
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def check(path):
    before_sha256 = sha256(path)
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_mask(False)
        def require(ok, reason):
            if not ok:
                raise ValueError(reason)
        require(getattr(ds, 'precipitation_research_policy', '') == 'retain_background_v1', 'policy')
        require(getattr(ds, 'configuration_id', '') in
                ('real-background-precip-shadow-v1', 'pressure-background-precip-shadow-v1'), 'configuration')
        require(getattr(ds, 'result_authority', '') == 'DIAGNOSTIC_PROPOSAL_ONLY', 'authority')
        require(getattr(ds, 'precipitation_transport_effective', None) == 0, 'effective transport')
        require(all(getattr(ds, n, None) == 20 for n in ('pipeline_status', 'column_status', 'balance_status')),
                'stage status')
        require(getattr(ds, 'acceptance_failures', None) == 0, 'acceptance')
        for species in ('rain', 'snow', 'graupel', 'phase'):
            for suffix in ('', '_valid', '_quality', '_source'):
                a, b = (f'policy_{prefix}_{species}{suffix}' for prefix in ('background', 'candidate'))
                require(a in ds.variables and b in ds.variables, f'missing {a} or {b}')
                left, right = ds[a], ds[b]
                require(left.dimensions == right.dimensions == ('z', 'y', 'x'), f'{a} dimensions')
                require(left.dtype == right.dtype, f'{a} type')
                require(getattr(left, 'units', None) == getattr(right, 'units', None) != None, f'{a} units')
                if not suffix:
                    require(getattr(left, 'valid_time', None) == getattr(right, 'valid_time', None) != None,
                            f'{a} valid time')
                    require(left.valid_time == getattr(ds, 'valid_time_epoch', None), f'{a} product time')
                    if species == 'phase':
                        require(getattr(left, 'code_table', None) == getattr(right, 'code_table', None)
                                == 'precipitation_phase_v1', f'{a} code table')
                x, y = np.asarray(left[:]), np.asarray(right[:])
                require(x.tobytes() == y.tobytes(), f'changed {species}{suffix}')
                if np.issubdtype(x.dtype, np.floating):
                    require(np.isfinite(x).all(), f'nonfinite {species}')
                if suffix == '_valid':
                    require(np.isin(x, (0, 1)).all(), f'invalid {species} mask')
                if species != 'phase':
                    for prefix, data in (('background', x), ('candidate', y)):
                        canonical = f'{prefix}_{species}{suffix}'
                        if not suffix or canonical in ds.variables:
                            require(canonical in ds.variables, f'missing {canonical}')
                            require(np.asarray(ds[canonical][:]).tobytes() == data.tobytes(),
                                    f'policy sidecar differs from {canonical}')
        require('hydro_support' in ds.variables and not np.any(ds['hydro_support'][:]), 'radar hydrometeor support')
        names = ('flux_input', 'flux_deposited', 'flux_suspended', 'flux_boundary_exit',
                 'flux_terrain_intercept', 'flux_observation_blocked', 'flux_no_echo_blocked',
                 'flux_microphysical_loss', 'flux_ledger_error')
        require(all(float(getattr(ds, name)) == 0.0 for name in names), 'radar flux ledger')
        # These are stored endpoint bookkeeping terms, not a full-model budget.
        budget = ('candidate_endpoint_enthalpy_change_j', 'candidate_endpoint_geometry_mass_change_kg',
                  'candidate_endpoint_total_mass_error_kg', 'candidate_endpoint_max_cell_mass_error_kg',
                  'candidate_endpoint_dry_mass_redistribution_kg', 'candidate_endpoint_species_change_kg',
                  'candidate_endpoint_mixing_ratio_change_kg', 'candidate_endpoint_dry_air_change_kg',
                  'candidate_endpoint_enthalpy_composition_change_j',
                  'candidate_endpoint_enthalpy_mass_metric_change_j')
        for name in budget:
            require(name in ds.ncattrs() and np.isfinite(np.asarray(getattr(ds, name))).all(), f'nonfinite {name}')
        configuration_id = ds.configuration_id
        policy = ds.precipitation_research_policy
    after_sha256 = sha256(path)
    if before_sha256 != after_sha256:
        raise ValueError('shadow changed while being inspected')
    return {'status': 'PASS_SCOPED_BACKGROUND_PRECIPITATION', 'shadow_sha256': after_sha256,
            'configuration_id': configuration_id, 'policy': policy,
            'scope': 'canonical precipitation and phase sidecar identity, no radar flux, finite endpoint terms; '
                     'not source/build provenance, forecast validation, or operational conservation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('shadow', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.shadow), indent=2))


if __name__ == '__main__':
    main()
