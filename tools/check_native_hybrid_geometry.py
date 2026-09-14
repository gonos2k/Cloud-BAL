#!/usr/bin/env python3
"""Read-only WRF hybrid dry-pressure diagnostic, never a native-state adapter.

Equations and scope: docs/CP01_EXECUTION_RECORD_20260907.md.
Gravity is explicit because the modified host binary's constants are unverified.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np

ABS_PA = 0.05
REL_PA = 2e-6
ETA_ATOL = 2e-7


def finite(value, name):
    if np.any(np.ma.getmaskarray(value)):
        raise ValueError(f"{name}: masked input")
    result = np.asarray(value, dtype=np.float64)
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name}: nonfinite input")
    return result


def hybrid_geometry(*, mu, mub, c1h, c2h, dnw, c3f, c4f, znw,
                    p_top, dx, dy, mapx, mapy, gravity):
    """Return dry layer pressure and diagnostic mass; inputs are bottom-to-top."""
    values = {name: finite(value, name) for name, value in locals().items()}
    mu, mub = values['mu'], values['mub']
    if mu.ndim != 2 or not mu.size or mub.shape != mu.shape:
        raise ValueError('MU/MUB: nonempty matching 2-D arrays required')
    n = values['dnw'].size
    if n < 2:
        raise ValueError('at least two layers required')
    for name in ('c1h', 'c2h', 'dnw'):
        if values[name].shape != (n,):
            raise ValueError(f'{name}: layer shape')
    for name in ('c3f', 'c4f', 'znw'):
        if values[name].shape != (n + 1,):
            raise ValueError(f'{name}: interface shape')
    for name in ('p_top', 'dx', 'dy', 'gravity'):
        if values[name].shape != () or values[name] <= 0:
            raise ValueError(f'{name}: positive scalar required')
    for name in ('mapx', 'mapy'):
        if values[name].shape != mu.shape or np.any(values[name] <= 0):
            raise ValueError(f'{name}: positive matching map array required')
    eta, step = values['znw'], values['dnw']
    if (abs(eta[0] - 1) > ETA_ATOL or abs(eta[-1]) > ETA_ATOL
            or np.any(np.diff(eta) >= 0) or np.any(step >= 0)
            or not np.allclose(step, np.diff(eta), atol=ETA_ATOL, rtol=0)):
        raise ValueError('eta/DNW: order, endpoints or spacing mismatch')
    total = mu + mub
    if np.any(total <= 0):
        raise ValueError('MU+MUB: nonpositive dry column pressure')
    expand = lambda a: values[a][:, None, None]
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        dp = -(expand('c1h') * total + expand('c2h')) * expand('dnw')
        interface = expand('c3f') * total + expand('c4f') + values['p_top']
        reference_dp = interface[:-1] - interface[1:]
        column = dp.sum(axis=0, dtype=np.float64)
        tolerance = ABS_PA + REL_PA * np.maximum(total + values['p_top'], 1)
        if np.any(dp <= 0) or np.any(reference_dp <= 0):
            raise ValueError('nonpositive dry layer pressure')
        checks = (np.abs(dp - reference_dp), np.abs(column - total),
                  np.abs(interface[0] - total - values['p_top']),
                  np.abs(interface[-1] - values['p_top']))
        if any(np.any(error > tolerance) for error in checks):
            raise ValueError('hybrid coefficient/interface/column closure mismatch')
        area = values['dx'] * values['dy'] / (values['mapx'] * values['mapy'])
        mass = area * dp / values['gravity']
    if not np.all(np.isfinite(mass)) or np.any(mass <= 0):
        raise ValueError('invalid diagnostic dry mass')
    return {'dp_pa': dp, 'interface_pa': interface, 'area_m2': area,
            'dry_mass_kg': mass,
            'layer_closure_max_pa': float(checks[0].max()),
            'column_closure_max_pa': float(checks[1].max())}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_geometry(ds, gravity):
    """Read the existing strict geometry contract from an open native file."""
    if ds.getncattr('HYBRID_OPT') != 2 or ds.getncattr('GRIDTYPE') != 'C':
        raise ValueError('only hybrid=2, C-grid diagnostic supported')
    if len(ds.dimensions['Time']) != 1:
        raise ValueError('exactly one Time record required')
    fields = {}
    for name in ('MU', 'MUB', 'C1H', 'C2H', 'DNW', 'C3F', 'C4F',
                 'ZNW', 'P_TOP', 'MAPFAC_MX', 'MAPFAC_MY'):
        var = ds.variables[name]
        dims = ('Time', 'south_north', 'west_east')
        units = ''
        if name in ('C1H', 'C2H', 'DNW'):
            dims = ('Time', 'bottom_top')
        if name in ('C3F', 'C4F', 'ZNW'):
            dims = ('Time', 'bottom_top_stag')
        if name == 'P_TOP':
            dims = ('Time',)
        if name in ('MU', 'MUB', 'C2H', 'C4F', 'P_TOP'):
            units = 'Pa'
        if name in ('C1H', 'C3F'):
            units = 'Dimensionless'
        if var.dimensions != dims or getattr(var, 'units', None) != units:
            raise ValueError(f'{name}: dimensions/units mismatch')
        fields[name.lower()] = var[0]
    fields['mapx'] = fields.pop('mapfac_mx')
    fields['mapy'] = fields.pop('mapfac_my')
    result = hybrid_geometry(**fields, dx=ds.DX, dy=ds.DY, gravity=gravity)
    return fields, result


def inspect(path, gravity):
    before = digest(path)
    with netCDF4.Dataset(path, 'r') as ds:
        _, result = read_geometry(ds, gravity)
        report = {'title': ds.TITLE, 'start_date': ds.START_DATE,
                  'shape_zyx': list(result['dp_pa'].shape),
                  'layer_closure_max_pa': result['layer_closure_max_pa'],
                  'column_closure_max_pa': result['column_closure_max_pa'],
                  'dry_layer_dp_range_pa': [float(result['dp_pa'].min()), float(result['dp_pa'].max())],
                  'diagnostic_dry_mass_sum_kg': float(result['dry_mass_kg'].sum()),
                  'area_range_m2': [float(result['area_m2'].min()), float(result['area_m2'].max())]}
    after = digest(path)
    if before != after:
        raise ValueError('input changed during inspection')
    report.update(input_path=str(path.resolve()), input_sha256=before,
                  input_unchanged=True, gravity_assumption_m_s2=gravity,
                  absolute_tolerance_pa=ABS_PA, relative_tolerance=REL_PA,
                  eta_absolute_tolerance=ETA_ATOL, artifact_class='DIAGNOSTIC',
                  geometry_contract='WRF_UPSTREAM_HYBRID2_ALGEBRA_ONLY',
                  geometry_result='PASS', native_authority='NONE', science_authority='NONE',
                  promotion_eligible=False, host_binary_equivalence='UNVERIFIED')
    return report


WATER_SPECIES = ('QVAPOR', 'QCLOUD', 'QICE', 'QRAIN', 'QSNOW', 'QGRAUP')


def host_pressure(pressure, temperature, vapor, height, terrain,
                  average_surface_temperature, gravity, gas_constant):
    """Replay sfcprs2 + integ_moist on the metgrid grid, not the analysis grid.

    This explicit profile uses dry QV, TAVGSFC and source terrain. The vapor
    integral uses source PSFC; only sfcprs2 uses the destination terrain.
    It is a float64 independent equation check, not bitwise host emulation.
    """
    p, t, q, z = [finite(v, name) for v, name in zip(
        (pressure, temperature, vapor, height), ('pressure', 'temperature', 'vapor', 'height'))]
    ter = finite(terrain, 'terrain')
    avg = finite(average_surface_temperature, 'average_surface_temperature')
    if (p.ndim != 3 or p.shape[0] < 3 or not p.size
            or any(v.shape != p.shape for v in (t, q, z))
            or ter.shape != p.shape[1:] or avg.shape != ter.shape):
        raise ValueError('host pressure: incompatible nonempty surface-first arrays')
    for value, name in ((gravity, 'gravity'), (gas_constant, 'gas_constant')):
        scalar = finite(value, name)
        if scalar.shape != () or scalar <= 0:
            raise ValueError(f'{name}: positive scalar required')
    if (np.any(p <= 0) or np.any(t <= 0) or np.any(avg <= 0)
            or np.any(q < 0) or np.any(q >= 1)
            or np.any(np.diff(p[1:], axis=0) >= 0)):
        raise ValueError('host pressure: invalid thermodynamics or pressure ordering')
    active = p[1:] < p[0]
    if not np.all(np.any(active, axis=0)):
        raise ValueError('host pressure: no above-ground pressure level')
    integral = np.zeros_like(p[0])

    def layer(pa, pb, ta, tb, qa, qb, dz):
        qbar = (qa + qb) * .5
        return gravity * qbar / (1 + qbar) * .5 * (pa / (gas_constant * ta)
                                                  + pb / (gas_constant * tb)) * dz

    with np.errstate(over='raise', invalid='raise', divide='raise'):
        # Sum from top down, independently of the production Fortran helper.
        for k in range(p.shape[0] - 2, 0, -1):
            selected = active[k - 1]
            dz = z[k + 1] - z[k]
            if np.any(selected & (dz <= 0)):
                raise ValueError('host pressure: non-increasing active height')
            integral[selected] += layer(p[k], p[k + 1], t[k], t[k + 1],
                                        q[k], q[k + 1], dz)[selected]
        first = np.argmax(active, axis=0)[None, :, :] + 1
        bottom = [np.take_along_axis(v, first, axis=0)[0] for v in (p, t, q, z)]
        dz = bottom[3] - z[0]
        integral += np.where(dz > .1, layer(p[0], bottom[0], t[0], bottom[1],
                                           q[0], bottom[2], dz), 0.)
        ps = p[0] * np.exp(gravity * (z[0] - ter)
                          / (gas_constant * avg * (1 + .608 * q[0])))
        dry = ps - integral
    if np.any(dry <= 0) or not np.all(np.isfinite(dry)):
        raise ValueError('host pressure: invalid dry surface pressure')
    return dict(native_surface_pressure_pa=ps, vapor_integral_pa=integral,
                dry_surface_pressure_pa=dry)


def inspect_host_pressure(metgrid, native, gravity, gas_constant):
    """Compare predicted host pressure with the actual final native arrays.

    Exact horizontal coordinates are required. No crop, inverse interpolation,
    source-grid pressure correction or conservation approval is inferred.
    """
    paths = (metgrid, native)
    before = [digest(path) for path in paths]
    with netCDF4.Dataset(metgrid) as m, netCDF4.Dataset(native) as n:
        horizontal = ('Time', 'south_north', 'west_east')
        vertical = ('Time', 'num_metgrid_levels', 'south_north', 'west_east')
        for ds, fields in ((m, {'PRES': (vertical, ''), 'TT': (vertical, 'K'),
                                'QV': (vertical, 'kg kg{-1}'), 'GHT': (vertical, 'm'),
                                'PSFC': (horizontal, 'Pa'), 'SOILHGT': (horizontal, 'm'),
                                'TAVGSFC': (horizontal, 'K'),
                                'XLAT_M': (horizontal, 'degrees latitude'),
                                'XLONG_M': (horizontal, 'degrees longitude')}),
                           (n, {'PSFC': (horizontal, 'Pa'), 'MU': (horizontal, 'Pa'),
                                'MUB': (horizontal, 'Pa'), 'HGT': (horizontal, 'm'),
                                'P_TOP': (('Time',), 'Pa'),
                                'XLAT': (horizontal, 'degree_north'),
                                'XLONG': (horizontal, 'degree_east')})):
            for name, (dims, units) in fields.items():
                if ds[name].dimensions != dims or getattr(ds[name], 'units', None) != units:
                    raise ValueError(f'{name}: host pressure dimensions/units mismatch')
        for flag in ('FLAG_QV', 'FLAG_PSFC', 'FLAG_SOILHGT', 'FLAG_TAVGSFC'):
            if getattr(m, flag, 0) != 1:
                raise ValueError(f'{flag}: required host profile input')
        if getattr(m, 'FLAG_SH', 0) == 1:
            raise ValueError('FLAG_SH overrides the supported direct-QV branch')
        if (len(m.dimensions['Time']) != 1 or len(n.dimensions['Time']) != 1
                or np.any(np.ma.getmaskarray(m['Times'][:]))
                or np.any(np.ma.getmaskarray(n['Times'][:]))
                or not np.array_equal(m['Times'][:], n['Times'][:])):
            raise ValueError('host pressure: paired time mismatch')
        timestamp = str(netCDF4.chartostring(m['Times'][:])[0])
        datetime.strptime(timestamp, '%Y-%m-%d_%H:%M:%S')
        for a, b in (('XLAT_M', 'XLAT'), ('XLONG_M', 'XLONG')):
            if not np.array_equal(finite(m[a][0], a), finite(n[b][0], b)):
                raise ValueError('host pressure: metgrid/native coordinates differ')
        p, t, q, z = [finite(m[name][0], name).copy() for name in ('PRES', 'TT', 'QV', 'GHT')]
        # real replaces these two surface slabs before calling integ_moist.
        p[0] = finite(m['PSFC'][0], 'PSFC')
        z[0] = finite(m['SOILHGT'][0], 'SOILHGT')
        predicted = host_pressure(p, t, q, z, finite(n['HGT'][0], 'HGT'),
                                  m['TAVGSFC'][0], gravity, gas_constant)
        actual_ps = finite(n['PSFC'][0], 'native PSFC')
        actual_dry = (finite(n['MU'][0], 'MU') + finite(n['MUB'][0], 'MUB')
                      + finite(n['P_TOP'][0], 'P_TOP'))
        if actual_ps.shape != p.shape[1:] or actual_dry.shape != actual_ps.shape:
            raise ValueError('host pressure: native pressure shape mismatch')
        ps_error = actual_ps - predicted['native_surface_pressure_pa']
        dry_error = actual_dry - predicted['dry_surface_pressure_pa']
        # This checks stored float32 pressure, not forecast or mass conservation.
        if np.any(np.abs(ps_error) > ABS_PA) or np.any(np.abs(dry_error) > ABS_PA):
            raise ValueError(f'host pressure mismatch: PSFC={np.max(np.abs(ps_error)):.6g} Pa, '
                             f'dry={np.max(np.abs(dry_error)):.6g} Pa')
        report = dict(host_pressure_result='PASS',
                      host_pressure_scope='SFCPRS2_TAVGSFC_DIRECT_QV_INTEG_MOIST',
                      host_profile_assumed=True,
                      horizontal_mapping='EXACT_METGRID_NATIVE_COORDINATES',
                      valid_time=timestamp,
                      shape_yx=list(actual_ps.shape),
                      surface_pressure_error_max_pa=float(np.max(np.abs(ps_error))),
                      dry_surface_pressure_error_max_pa=float(np.max(np.abs(dry_error))),
                      vapor_integral_range_pa=[float(predicted['vapor_integral_pa'].min()),
                                               float(predicted['vapor_integral_pa'].max())],
                      gas_constant_assumption_j_kg_k=gas_constant,
                      gravity_assumption_m_s2=gravity, absolute_tolerance_pa=ABS_PA,
                      conservation_assessed=False, promotion_eligible=False,
                      artifact_class='DIAGNOSTIC', host_binary_equivalence='UNVERIFIED')
    if before != [digest(path) for path in paths]:
        raise ValueError('host pressure input changed during inspection')
    report.update(metgrid_sha256=before[0], native_sha256=before[1], input_unchanged=True)
    return report


def compare(baseline, candidate, gravity):
    """Separate composition and mass-metric changes; never certify conservation.

    This is a same-grid native comparison, not an analysis-to-native remapper.
    For each species: m_c q_c - m_b q_b = m_b (q_c-q_b) + (m_c-m_b) q_c.
    No external analysis increment or boundary flux is inferred from this identity.
    """
    before = [digest(path) for path in (baseline, candidate)]
    with netCDF4.Dataset(baseline) as b, netCDF4.Dataset(candidate) as c:
        bg, bm = read_geometry(b, gravity)
        cg, cm = read_geometry(c, gravity)
        for name in bg:
            if name not in ('mu', 'mub') and not np.array_equal(bg[name], cg[name]):
                raise ValueError(f'{name}: paired geometry mismatch')
        if b.DX != c.DX or b.DY != c.DY:
            raise ValueError('DX/DY: paired geometry mismatch')
        if (np.any(np.ma.getmaskarray(b['Times'][:])) or
                np.any(np.ma.getmaskarray(c['Times'][:])) or
                b['Times'].dimensions != ('Time', 'DateStrLen') or
                c['Times'].dimensions != ('Time', 'DateStrLen') or
                not np.array_equal(b['Times'][:], c['Times'][:])):
            raise ValueError('Times: paired time mismatch')
        timestamp = str(netCDF4.chartostring(b['Times'][:])[0])
        datetime.strptime(timestamp, '%Y-%m-%d_%H:%M:%S')
        horizontal = ('Time', 'south_north', 'west_east')
        for name, units in (('XLAT', 'degree_north'), ('XLONG', 'degree_east')):
            for ds in (b, c):
                if ds[name].dimensions != horizontal or ds[name].units != units:
                    raise ValueError(f'{name}: dimensions/units mismatch')
            if not np.array_equal(finite(b[name][:], name), finite(c[name][:], name)):
                raise ValueError(f'{name}: paired coordinate mismatch')
        mb, mc = bm['dry_mass_kg'], cm['dry_mass_kg']
        if mb.shape != mc.shape:
            raise ValueError('paired native shape mismatch')
        dm = mc - mb
        species = {}
        for name in WATER_SPECIES:
            values = []
            for ds in (b, c):
                var = ds[name]
                if (var.dimensions != ('Time', 'bottom_top', 'south_north', 'west_east')
                        or var.units.strip() != 'kg kg-1'):
                    raise ValueError(f'{name}: dimensions/units mismatch')
                q = finite(var[0], name)
                if q.shape != mb.shape or np.any(q < 0) or np.any(q >= 1):
                    raise ValueError(f'{name}: invalid dry mixing ratio')
                values.append(q)
            qb, qc = values
            with np.errstate(over='raise', invalid='raise'):
                composition = float(np.sum(mb * (qc - qb), dtype=np.float64))
                metric = float(np.sum(dm * qc, dtype=np.float64))
                change = float(np.sum(mc * qc - mb * qb, dtype=np.float64))
                species[name] = dict(baseline_kg=float(np.sum(mb * qb)),
                                     candidate_kg=float(np.sum(mc * qc)),
                                     change_kg=change,
                                     composition_change_kg=composition,
                                     mass_metric_change_kg=metric)
        report = dict(dry_mass_change_kg=float(np.sum(dm)),
                      water_by_species=species, conservation_assessed=False,
                      valid_time=timestamp,
                      water_change_kg=sum(s['change_kg'] for s in species.values()),
                      promotion_eligible=False, artifact_class='DIAGNOSTIC',
                      comparison_scope='SAME_GRID_NATIVE_MASS_WATER_DIFFERENCE',
                      gravity_assumption_m_s2=gravity)
    after = [digest(path) for path in (baseline, candidate)]
    if before != after:
        raise ValueError('paired input changed during inspection')
    report.update(baseline_sha256=before[0], candidate_sha256=before[1],
                  input_unchanged=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--gravity', required=True, type=float)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--baseline', type=Path,
                        help='compare native dry mass and water on the same grid/time')
    mode.add_argument('--metgrid', type=Path,
                      help='replay the direct-QV/TAVGSFC sfcprs2 host pressure profile')
    parser.add_argument('--gas-constant', type=float,
                        help='explicit host Rd; required with --metgrid')
    args = parser.parse_args()
    if (args.metgrid is not None) != (args.gas_constant is not None):
        parser.error('--metgrid and --gas-constant must be supplied together')
    try:
        if args.metgrid:
            report = inspect_host_pressure(args.metgrid, args.input, args.gravity, args.gas_constant)
        else:
            report = (compare(args.baseline, args.input, args.gravity) if args.baseline
                      else inspect(args.input, args.gravity))
        print(json.dumps(report, indent=2, allow_nan=False))
    except (ValueError, KeyError, IndexError, AttributeError, OSError, FloatingPointError) as error:
        parser.exit(1, f'DIAGNOSTIC REJECT: {error}\n')
