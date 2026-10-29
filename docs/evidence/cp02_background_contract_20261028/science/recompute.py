#!/usr/bin/env python3
"""Read-only audit of archived CP02 radar/background artifacts; no model replay."""
from __future__ import annotations
import csv, gzip, hashlib, importlib.util, json, math, struct, sys
from collections import Counter
from pathlib import Path
import netCDF4
import numpy as np

BASE = Path('/var/tmp/cloudbal-cp02-background-contract')
CAPTURE = BASE / 'docs/evidence/cp02_radar_inputs_20261028/hydro_capture.json.gz'
PROFILES = BASE / 'docs/evidence/cp02_radar_inputs_20261028/analysis/profiles.csv'
BG_CSV = BASE / 'docs/evidence/cp02_initial_species_20261027/final/shadow/shadow_species_profiles.csv'
LINEAGE = BASE / 'docs/evidence/cp02_initial_species_20261027/historical_lineage.json'
SEARCH_COLUMN = BASE / 'docs/evidence/cp02_call_boundary_20261028/column_source_search.json'
SEARCH_LAPSPREP = BASE / 'docs/evidence/cp02_call_boundary_20261028/lapsprep_source_search.json'
SEARCH_PIPELINE = BASE / 'docs/evidence/wps_off_readback_20261028/source_search.json'
SHADOW = Path('/var/tmp/cp02-binary-boundary-20261028/hydro_baseline_unlimited/HYDRO.wps.shadow.nc')
PAYLOAD = Path('/var/tmp/cp02-binary-boundary-20261028/input/payload.nc')
NPZ = Path('/var/tmp/rn1-rescore-final-20261027/hour_13_arrays.npz')
OUT = Path('/var/tmp/cp02-background-science-20261028')


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def real(raw: str, width: int) -> float:
    return struct.unpack('<d' if width == 8 else '<f', bytes.fromhex(raw))[0]


def integer(raw: str) -> int:
    return struct.unpack('<i', bytes.fromhex(raw))[0]


def capture_stage(capture: dict, name: str) -> dict:
    return next(r for r in capture['records'] if r['stage'] == name)


def indexed_values(stage: dict, field: str, width: int) -> dict[tuple[int, int, int], float]:
    out = {}
    for p in stage['arrays'][field]['points']:
        i, j = p['fortran_i'], p['fortran_j']
        for level in p['levels']:
            k = level['fortran_k']
            out[(i, j, k)] = real(level['raw_bytes_le_hex'], width)
    return out


def local_by_key(capture: dict, stage_name: str, field: str) -> dict[tuple[int, int, int], float]:
    out = {}
    for r in capture['radar_local_records']:
        if r['stage'] == stage_name and field in r['values']:
            out[(r['fortran_i'], r['fortran_j'], r['fortran_k'])] = real(r['values'][field]['raw_bytes_le_hex'], 8)
    return out


def radar_array(capture: dict, field: str) -> dict[tuple[int, int, int], int | float | bool]:
    stage = capture_stage(capture, 'diagnose_radar_cells_post')
    v = stage['radar']['inputs'][field]
    out = {}
    width = 8 if 'REAL*8' in v['type'] else 4
    for p in v['points']:
        for level in p['levels']:
            key = (p['fortran_i'], p['fortran_j'], level['fortran_k'])
            raw = level['raw_bytes_le_hex']
            if 'LOGICAL' in v['type']:
                out[key] = integer(raw) != 0
            elif 'INTEGER' in v['type']:
                out[key] = integer(raw)
            else:
                out[key] = real(raw, width)
    return out


def main() -> None:
    capture = json.loads(gzip.open(CAPTURE, 'rt', encoding='utf-8').read())
    profile_rows = list(csv.DictReader(PROFILES.open(newline='', encoding='utf-8')))
    assert len(profile_rows) == 440
    post = capture_stage(capture, 'publish_hydrometeor_candidate_post')
    cand_r = indexed_values(post, 'rain', 8)
    cand_s = indexed_values(post, 'snow', 8)
    zlin = radar_array(capture, 'zlinear')
    radar_obs = radar_array(capture, 'radar_observed')
    phase = radar_array(capture, 'phase')
    rho = local_by_key(capture, 'density_return', 'rho_d')
    total = local_by_key(capture, 'phase_allocation_return', 'total')
    cfg = capture_stage(capture, 'derive_arguments')['config']
    refmass = real(cfg['fields']['reference_mass_concentration']['raw_bytes_le_hex'], 8)

    strata = []
    csv_diff = Counter()
    unobs = []
    formula_errors = []
    candidate_rounding_diffs = []
    with netCDF4.Dataset(PAYLOAD) as pds, netCDF4.Dataset(SHADOW) as sds:
        payload_rain = np.asarray(pds['rain'][0])
        payload_snow = np.asarray(pds['snow'][0])
        payload_valid = np.asarray(pds['radar_reflectivity_valid'][0])
        payload_quality = np.asarray(pds['radar_reflectivity_quality'][0])
        shadow_rain = np.asarray(sds['background_rain'][:])
        shadow_snow = np.asarray(sds['background_snow'][:])
        shadow_candidate_rain = np.asarray(sds['candidate_rain'][:])
        shadow_candidate_snow = np.asarray(sds['candidate_snow'][:])
    for row in profile_rows:
        key = (int(row['fortran_i']), int(row['fortran_j']), int(row['fortran_k']))
        i, j, k = key
        raw = (k - 1, j - 1, i - 1)
        q = int(row['actual_observation.radar_reflectivity.quality'])
        ph = int(phase[key])
        valid = int(row['actual_observation.radar_reflectivity.valid'] == 'True')
        # Decode background from the full NetCDF arrays, not the profile analyzer.
        br = float(payload_rain[raw])
        bs = float(payload_snow[raw])
        pvalid = int(payload_valid[raw])
        pq = int(payload_quality[raw])
        sr = float(shadow_rain[k-1, j-1, i-1])
        ss = float(shadow_snow[k-1, j-1, i-1])
        assert (br, bs) == (sr, ss)
        assert (valid, q) == (pvalid, pq)
        assert ph == int(row['diagnose_radar_cells_post.phase'])
        assert bool(valid) == bool(radar_obs[key])
        assert key in cand_r and key in cand_s
        cr_work, cs_work = cand_r[key], cand_s[key]
        cr = float(shadow_candidate_rain[k-1, j-1, i-1])
        cs = float(shadow_candidate_snow[k-1, j-1, i-1])
        candidate_rounding_diffs.extend((abs(cr - cr_work), abs(cs - cs_work)))
        for csvname, expected in [('background_rain', br), ('background_snow', bs),
                                  ('publish_hydrometeor_candidate_post.rain', cr_work),
                                  ('publish_hydrometeor_candidate_post.snow', cs_work)]:
            if float(row[csvname]) != expected:
                csv_diff[csvname] += 1
        if not valid:
            unobs.append((br, bs, cr, cs))
        if valid and ph in (1, 2) and q in (0, 32):
            species = 'rain' if ph == 1 else 'snow'
            b, c = (br, cr) if species == 'rain' else (bs, cs)
            g = next((x for x in strata if (x['species'], x['quality']) == (species, q)), None)
            if g is None:
                g = {'species': species, 'quality': q, 'count': 0, 'sum_background': 0.0,
                     'sum_candidate_real32_shadow': 0.0, 'sum_candidate_real64_work': 0.0}
                strata.append(g)
            g['count'] += 1
            g['sum_background'] += b
            g['sum_candidate_real32_shadow'] += c
            g['sum_candidate_real64_work'] += cr_work if species == 'rain' else cs_work
        if key in rho and key in total:
            pred = refmass * (zlin[key] / 1000.0) ** 0.55 / rho[key]
            formula_errors.append(total[key] - pred)

    for g in strata:
        g['candidate_background_sum_ratio_real32_shadow'] = g['sum_candidate_real32_shadow'] / g['sum_background']
        g['candidate_background_sum_ratio_real64_work'] = g['sum_candidate_real64_work'] / g['sum_background']
    strata.sort(key=lambda x: (x['species'], x['quality']))

    # Full-grid overlap of invalid reflectivity and positive archived background,
    # and candidate/background equality at those cells.
    with netCDF4.Dataset(PAYLOAD) as pds, netCDF4.Dataset(SHADOW) as sds:
        valid = np.asarray(pds['radar_reflectivity_valid'][0], dtype=bool)
        bg_r = shadow_rain
        bg_s = shadow_snow
        ca_r = shadow_candidate_rain
        ca_s = shadow_candidate_snow
        above = np.asarray(sds['above_ground'][:], dtype=bool)
        lat = np.asarray(sds['latitude'][:])
        lon = np.asarray(sds['longitude'][:])
        assert np.array_equal(np.asarray(sds['radar_valid'][:], dtype=bool), valid)
        full_radar_valid_cells = int(np.count_nonzero(valid))
        assert np.array_equal(np.asarray(pds['rain'][0]), bg_r)
        assert np.array_equal(np.asarray(pds['snow'][0]), bg_s)
        full = {}
        for name, bg, cand in [('rain', bg_r, ca_r), ('snow', bg_s, ca_s)]:
            overlap = (~valid) & (bg > 0)
            overlap_ag = overlap & above
            cand_overlap = (~valid) & (cand > 0)
            full[name] = {
                'all_grid_positive_background_cells': int(np.count_nonzero(bg > 0)),
                'radar_invalid_positive_background_cells': int(np.count_nonzero(overlap)),
                'radar_invalid_positive_background_above_ground_cells': int(np.count_nonzero(overlap_ag)),
                'radar_invalid_positive_candidate_cells': int(np.count_nonzero(cand_overlap)),
                'radar_invalid_overlap_cells_where_candidate_equals_background': int(np.count_nonzero(overlap & (cand == bg))),
            }
        # Shortlist representative observed-invalid/background-positive native cells.
        invalid_rain = np.argwhere((~valid) & (bg_r > 0) & above)
        invalid_snow = np.argwhere((~valid) & (bg_s > 0) & above)
        examples = []
        for species, idxs, bg in [('rain', invalid_rain, bg_r), ('snow', invalid_snow, bg_s)]:
            for z, y, x in idxs[:4]:
                examples.append({'species': species, 'z_index_0based': int(z), 'y_index_0based': int(y), 'x_index_0based': int(x),
                                 'latitude': float(lat[y, x]), 'longitude': float(lon[y, x]),
                                 'background_kg_kg_dryair': float(bg[z, y, x]), 'candidate_kg_kg_dryair': float(ca_r[z,y,x] if species=='rain' else ca_s[z,y,x]),
                                 'reflectivity_valid': bool(valid[z,y,x]), 'above_ground': bool(above[z,y,x])})

    # Preserve score-transition counts, but do not join them to native fields:
    # the complete WRF bilinear stencil for all 3,688 points is not in this bundle.
    npz = np.load(NPZ)
    ref = np.asarray(npz['reference']); off = np.asarray(npz['OFF'])
    hydro = np.asarray(npz['HYDRO']); liquid = np.asarray(npz['LIQUID'])
    categories = {
        'hydro_kept_hit': (ref >= 5) & (off >= 5) & (hydro >= 5),
        'hydro_removed_false_alarm': (ref < 5) & (off >= 5) & (hydro < 5),
        'hydro_lost_hit': (ref >= 5) & (off >= 5) & (hydro < 5),
        'liquid_kept_hit': (ref >= 5) & (off >= 5) & (liquid >= 5),
        'liquid_removed_false_alarm': (ref < 5) & (off >= 5) & (liquid < 5),
        'liquid_lost_hit': (ref >= 5) & (off >= 5) & (liquid < 5),
    }
    scored = {name: int(mask.sum()) for name, mask in categories.items()}

    evidence_paths = [Path(__file__), CAPTURE, PROFILES, BG_CSV, LINEAGE, SEARCH_COLUMN, SEARCH_LAPSPREP, SEARCH_PIPELINE, SHADOW, PAYLOAD, NPZ]
    out = {
        'schema': 'cp02_background_science_audit_v1',
        'status': 'PASS_SCOPED_ARCHIVED_ARTIFACTS',
        'method': 'standalone gzip/JSON raw-byte decoding plus NetCDF4/CSV/NPZ reads; no capture analyzer, replay, forecast, source rebuild, or file mutation',
        'provenance': {str(p): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in evidence_paths},
        'capture': {'schema': capture['schema'], 'status': capture['status'], 'arm': capture['arm'], 'records': len(capture['records']),
                    'local_records': len(capture['radar_local_records']),
                    'candidate_decoding': 'REAL*8 little-endian work arrays at publish_hydrometeor_candidate_post; final candidate values separately read as REAL*32 from shadow NetCDF',
                    'observed_true_false_equal_payload_reflectivity_valid_all_440': True},
        'csv_crosscheck': {'rows': len(profile_rows), 'raw_capture_and_netcdf_vs_preserved_csv_differences': dict(csv_diff)},
        'quality_phase_candidate_background': {'scope': '190 actual valid reflectivity cells; phase is the archived binary diagnose output code; q is archived payload reflectivity-quality integer; ratio = sum(candidate species)/sum(background species)', 'strata': strata},
        'unobserved_selected_sample': {'count': len(unobs), 'all_background_rain_snow_and_candidate_rain_snow_zero': all(all(x == 0 for x in r) for r in unobs),
                                       'interpretation': 'preservation is untested at these 250 cells because both endpoints are zero'},
        'background_generation_evidence': {'payload_to_shadow_background_rain_snow_exact_full_array_equality': True,
                                           'units': {'payload_rain_snow': ['kg kg-1 dryair'], 'shadow_background_rain_snow': ['kg kg-1 dryair']},
                                           'historical_lineage_claim': 'archived lineage says LAPSPREP read radar 3-D hydrometeor concentration in kg m-3, applied validity/negative clipping and hydrometeor_scale, then divided by dry-air rho to form mixing ratio; options record CAP_POLICY=TRANSFER, rain/snow fraction=1, GRID_SCALE=NONE',
                                           'source_exactness': 'build pins: LAPSPREP f69735e8…749579, column physics f7d640bb…f14e17d, pipeline 188a2e1b…6f2b478. Bounded searches found no exact LAPSPREP or column-physics source; 14 exact-content pipeline copies exist, but no copy is bound to the CP02 link step. Pipeline has no matching git revision among 23 checked. Do not substitute current source for missing historical source.',
                                           'background_conversion_coefficients_density': 'the retained lineage names hydrometeor_scale and division by dry-air density, but the exact old LAPSPREP source is absent and the archived payload begins at kg/kg; no exact conversion coefficient or source expression is established from these files.'},
        'candidate_real32_vs_work_array': {'cells': len(candidate_rounding_diffs)//2, 'max_abs_species_rounding_delta_kg_kg': max(candidate_rounding_diffs), 'scope': 'REAL*32 final shadow storage minus captured REAL*64 publish work array'},
        'allocator_formula_fit': {'n': len(formula_errors), 'captured_config_reference_mass_concentration': refmass,
                                  'captured_rho_d_min_max_kg_m3': [min(rho.values()), max(rho.values())],
                                  'tested_relation': 'captured_total == reference_mass_concentration * (captured_zlinear/1000)**0.55 / captured_rho_d',
                                  'max_absolute_residual': max(map(abs, formula_errors)), 'all_residuals_exact_float64_zero': all(x == 0.0 for x in formula_errors),
                                  'interpretation': 'numerical identity over archived 190 allocator calls; coefficient is a captured binary runtime config value. Exponent and /1000 form are empirically supported by outputs, not source-level historical proof.'},
        'full_grid_radar_invalid_positive_background': {'scope': '22x283x235 native payload/shadow cells; this is a reflectivity validity mask (radar_reflectivity_valid=0), not a certified actual_observed=false reconstruction; positive means archived payload/background species >0',
                                                        'radar_valid_cells': full_radar_valid_cells,
                                                        'radar_invalid_cells': int(valid.size - full_radar_valid_cells),
                                                        'grid_cells': int(valid.size),
                                                        'by_species': full, 'shortlist': examples},
        '3688_first_hour_score_transitions': {'scope': 'existing archived 13 UTC array NPZ; threshold 5 mm; no forecast rerun', 'counts': scored,
                                               'native_source_crosswalk': 'not performed: full 3,688-point WRF bilinear stencils are not preserved in this bundle; the 20-point lost-hit stencil is only a subset'},
        'limitations': ['The 250 observed-false selected profile rows all have zero background and candidate rain/snow; they cannot test preservation.',
                        'Full-domain invalid-mask cells with positive background are inventoried, and the existing 3,688-point arrays provide hit/false-alarm transition counts. A full native-source footprint crosswalk is unavailable because the 3,688-point WRF bilinear stencils are not preserved; no overlap is claimed.',
                        'The lineage identifies candidate source operations and units but does not prove the first differing operation or exact historical source equation. Exact LAPSPREP and column-physics source bytes remain unresolved; pipeline content has 14 archived exact-hash copies but no copy-to-binary binding.',
                        'This is an artifact-level numerical audit, not physical validation, whole-column water budget, or forecast-causality test.']
    }
    (OUT / 'results.json').write_text(json.dumps(out, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': out['status'], 'strata': strata, 'formula': out['allocator_formula_fit'], 'full_grid': out['full_grid_radar_invalid_positive_background']['by_species'], 'score_transitions': scored}, indent=2))

if __name__ == '__main__':
    main()
