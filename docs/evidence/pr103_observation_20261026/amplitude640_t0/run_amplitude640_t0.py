#!/usr/bin/env python3
"""Bounded PR103 AMPLITUDE 640-second run T0 observation sidecar runner."""
from __future__ import annotations
import hashlib
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr103_amplitude_control_20261026/Cloud-BAL')
ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee')
A_RUN = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr103_amplitude20_capture_20261026/AMPLITUDE640_RUN')
A_RECEIPT = A_RUN / 'receipt.json'
A_PREFLIGHT = A_RUN / 'preflight.json'
A_HISTORY = A_RUN / 'run/wrfout_d01_2026-08-16_13:00:00'
O_HISTORY = ROOT / 'pr99_c2_matched640_20261022/OFF/run/wrfout_d01_2026-08-16_13:00:00'
OUTPUT = Path('/var/tmp/pr103_observation_amplitude640_t0_20261026/amplitude640_t0_input_consistency.json')
EXPECTED = {
    'a_receipt': '76792551d703e5e05af778b39482269dcb09ed16b83a5780514e920fcd1e5296',
    'a_preflight': 'b3d137c91ab90ee89cc25b3b8bf709d622f7b819f71a048f51f1527f06005b0b',
    'a_history': '67ec6197a5f1aed9e90f56c49d5af34e9f685167f7ac2427884b9bcdef8707a4',
    'o_history': 'e9a6ec6ca8af2f99b3ee4a9fedab13b42a4997a2ab6f68ac08e897117766470f',
    'observation': 'b70ee7a758bf2d27b938ff346e3fc4c40c4c79be22f746d0f0cb0cf2ce03b9fd',
    'comparator': 'fa7b890909368f5218c3b91a7aa31d95754703860f2151016f19912ab99a3144',
    'finite_helper': 'd6feb0e5fd5d53a60d7256a7b3c4faaa3c7f2488b799af25278aec7529c28a71',
    'upstream_binding': '08b03eaf46c7b19e055af0da3585ee630c9578f8338910c91519ae9a90ef86e5',
    'fivearm_readback': 'd10f124bed615f0546594266971db263d6ba7db48ae3ee210e985f4c8c7db6b2',
    'wrf_projection_source': '0c777e66ffbb0602479cadcc0ab484769a140c4cb2b3e9a8f757597086f0c76b',
    'a20_sidecar': '5bbd205b4e7d49ed425ddcda433872e2fe128937e8c5c4d28be39f374f56dd14',
    'a20_runner': '457b5fda867a28019c4ace61aed8f50993bd6059d2dc0fb1fb5c2728dd08b3e5',
    'a20_run_receipt': '67c148c22e4b812192547108e7f6ddf476ac3ee18c922de39b3512e968efaf3e',
    'fivearm_v2_sidecar': '1813cf577e1030ac8c20b1651c1a857c6dd938092bb662d41278d94ddda7bf8c',
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location('pr103_surface_temperature_observation', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    comparator_path = REPO / 'tools/pr103_surface_temperature_observation.py'
    finite_path = REPO / 'tools/pr87_native_history.py'
    upstream_path = REPO / 'tests/original_upstream_replay_20260816.json'
    fivearm_path = REPO / 'docs/evidence/pr102_execution_20261025/fivearm/fivearm_history_readback.json'
    lso_path = ROOT / 'KLAPS50/ANAL/NE57/DAOU/00/lapsprd/lso/262281300.lso'
    wrf_source = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS/wrf_v4_8_kfarms_work/WRF-v4.8.0/share/module_llxy.F')
    sources = {k: ROOT / 'KLAPS50/klaps-v5.0_' / k for k in (
        'src/lib/gridconv.f', 'src/lib/modules/module_map_utils.f90',
        'src/lib/modules/module_wrf_netcdf.f90', 'src/lib/bgdata/wrf/module_wrf_lga.f90',
        'src/lib/read_surface_obs.f', 'src/include/lso_formats.inc', 'src/include/surface_obs.inc')}
    module = load_module(comparator_path)
    pin_paths = {
        'a_receipt': A_RECEIPT, 'a_preflight': A_PREFLIGHT,
        'a_history': A_HISTORY, 'o_history': O_HISTORY,
        'observation': lso_path, 'comparator': comparator_path,
        'finite_helper': finite_path, 'upstream_binding': upstream_path,
        'fivearm_readback': fivearm_path, 'wrf_projection_source': wrf_source,
        'a20_sidecar': REPO / 'docs/evidence/pr103_observation_20261026/amplitude_t0/amplitude_t0_input_consistency.json',
        'a20_runner': REPO / 'docs/evidence/pr103_observation_20261026/amplitude_t0/run_amplitude_t0.py',
        'a20_run_receipt': REPO / 'docs/evidence/pr103_observation_20261026/amplitude_t0/run_receipt.json',
        'fivearm_v2_sidecar': REPO / 'docs/evidence/pr103_observation_20261026/surface_temperature_input_consistency_v2.json',
        **{f'source:{k}': v for k, v in sources.items()},
    }
    before = {k: sha256(v) for k, v in pin_paths.items()}
    for key, expected in EXPECTED.items():
        if before[key] != expected:
            raise SystemExit(f'{key} pin mismatch: got {before[key]} expected {expected}')
    for relative, expected in module.SOURCE_PINS.items():
        key = f'source:{relative}'
        if before[key] != expected:
            raise SystemExit(f'authoritative source pin mismatch for {relative}')
    if before['observation'] != module.LSO_SHA256 or module.FINITE_HELPER_SHA256 != EXPECTED['finite_helper']:
        raise SystemExit('frozen comparator authority pins disagree')
    if before['wrf_projection_source'] != module.WRF_LLXY_SHA256:
        raise SystemExit('WRF projection source pin disagrees with frozen comparator')

    receipt = json.loads(A_RECEIPT.read_text())
    preflight = json.loads(A_PREFLIGHT.read_text())
    if (receipt.get('arm') != 'AMPLITUDE' or receipt.get('status') != 'COMPLETE'
            or receipt.get('returncode') != 0 or receipt.get('processing_errors') != []):
        raise SystemExit('A640 run receipt is not a clean COMPLETE rc=0 closure')
    if (receipt.get('timestep_count') != 32 or receipt.get('final_completed_step') != 32
            or receipt.get('maximum_seen_timestep') != 32):
        raise SystemExit('A640 receipt is not exactly 32 completed steps')
    expected_times = [(dt.datetime(2026, 8, 16, 13, 0, 0) + dt.timedelta(seconds=20 * step)).strftime('%Y-%m-%d_%H:%M:%S') for step in range(1, 33)]
    if [row.get('timestamp') for row in receipt.get('model_timestamps', [])] != expected_times:
        raise SystemExit('A640 closed timestep schedule mismatch')
    if (receipt.get('earliest_fatal') is not None or receipt.get('fatal_lines')
            or receipt.get('changed_staged_inputs') or receipt.get('changed_original_inputs')
            or receipt.get('duplicate_post_kdm6_timesteps')
            or receipt.get('candidate_build_unchanged') is not True
            or receipt.get('candidate_input_unchanged') is not True):
        raise SystemExit('A640 receipt records fatal, mutation, duplicate, or binding errors')
    if receipt.get('executed_executable_sha256') != '387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a':
        raise SystemExit('A640 executed executable is not the pinned base C2 executable')
    candidate = receipt['candidate_input_binding']['artifacts']['candidate']
    if candidate.get('sha256') != '9038d0a26896a630b7048091a97a2c0055b26934513392195eb8e609626e74e2':
        raise SystemExit('A640 candidate identity mismatch')
    entry = next((x for x in receipt['generated_files'] if x.get('path') == A_HISTORY.name), None)
    if not entry or entry.get('sha256') != EXPECTED['a_history'] or entry.get('bytes') != A_HISTORY.stat().st_size:
        raise SystemExit('A640 generated T0 history is not bound by its closed receipt')
    if (preflight.get('arm') != 'AMPLITUDE' or preflight.get('duration_seconds') != 640
            or preflight.get('expected_timesteps') != 32
            or preflight.get('candidate_wrfinput_sha256') != candidate['sha256']
            or preflight.get('candidate_wrfbdy_sha256') != '885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7'
            or preflight.get('candidate_namelist_sha256') != '58c194b8846d25a6c7cbfedac1477fbf65fcc1a12705c8cb11851096ee7d2fc8'
            or preflight.get('executable_sha256') != '9642a471acd39320efca247a55104da9369ef93d8735e60a0d266bf20332b943'):
        raise SystemExit('A640 preflight does not identify the pinned 640s candidate/base-C2 configuration')

    observations, lso_counts = module.read_lso(lso_path)
    a_attrs, a_t2, a_lat, a_lon = module.model_metadata(A_HISTORY)
    o_attrs, o_t2, o_lat, o_lon = module.model_metadata(O_HISTORY)
    if a_attrs != o_attrs or not (module.np.array_equal(a_lat, o_lat) and module.np.array_equal(a_lon, o_lon)):
        raise SystemExit('A640 and O mass-grid projection/coordinates differ')
    projection = {'lat1': a_attrs['lat1'], 'lon1': a_attrs['lon1'],
                  'stdlon': a_attrs['STAND_LON'], 'truelat1': a_attrs['TRUELAT1'],
                  'truelat2': a_attrs['TRUELAT2'], 'dx': a_attrs['DX'], 'dy': a_attrs['DY']}
    rows_a, metrics_a = module.compare(observations, a_t2, projection)
    rows_o, metrics_o = module.compare(observations, o_t2, projection)
    if len(rows_a) != 765 or len(rows_o) != 765:
        raise SystemExit('A640/O comparison did not use the established 765 valid 13Z LSO rows')
    if [r['station_id'] for r in rows_a] != [r['station_id'] for r in rows_o]:
        raise SystemExit('A640/O matched station sets differ')
    same_t2 = bool(module.np.array_equal(a_t2, o_t2))
    changed = int(module.np.count_nonzero(a_t2 != o_t2))
    max_delta = float(module.np.max(module.np.abs(a_t2 - o_t2)))
    after = {k: sha256(v) for k, v in pin_paths.items()}
    if before != after:
        raise SystemExit('an input/source pin changed during A640 comparison')
    result = {
        'schema': 'pr103_amplitude_t0_observation_input_consistency_v1',
        'scope': 'AMPLITUDE 640-second closed run; exact generated T0 history only; no later forecast valid time and not independent forecast skill',
        'operation': 'apply unchanged PR103 13Z LSO/T2 same-cycle comparator to A640 generated T0 and pinned O T0',
        'closure': {'run_receipt_path': str(A_RECEIPT), 'run_receipt_sha256': before['a_receipt'],
                    'preflight_path': str(A_PREFLIGHT), 'preflight_sha256': before['a_preflight'],
                    'arm': receipt['arm'], 'status': receipt['status'], 'returncode': receipt['returncode'],
                    'processing_errors': receipt['processing_errors'], 'completed_steps': receipt['final_completed_step'],
                    'run_timestamp_first': receipt['model_timestamps'][0]['timestamp'],
                    'run_timestamp_last': receipt['model_timestamps'][-1]['timestamp'],
                    'T0_history_valid_time_utc': '2026-08-16T13:00:00Z', 'candidate_sha256': candidate['sha256'],
                    'executed_executable_sha256': receipt['executed_executable_sha256'],
                    'history_path': str(A_HISTORY), 'history_sha256': before['a_history'],
                    'history_bytes': A_HISTORY.stat().st_size},
        'observation': {'path': str(lso_path), 'sha256': before['observation'],
                        'valid_time_utc': '2026-08-16T13:00:00Z', 'units': 'degF',
                        'records': lso_counts['parsed_records'], 'matched_records': len(rows_a),
                        'source_badflag_degF': module.LSO_BADFLAG_F},
        'operator': {'comparator_path': str(comparator_path), 'comparator_sha256': before['comparator'],
                     'operator_label': 'source-faithful diagnostic adapter; not a registered assimilation H',
                     'residual': 'H(X)-Y = WRF T2 (K -> degC) minus station air temperature (degF -> degC)'},
        'arms': {
            'A640_T0': {'history_sha256': before['a_history'], 'field': 'T2', 'units': 'K',
                    'metrics': metrics_a},
            'O': {'history_sha256': before['o_history'], 'field': 'T2', 'units': 'K',
                  'metrics': metrics_o},
        },
        'A640_T0_T2_vs_O_T0_T2': {'bitwise_equal': same_t2, 'changed_cells': changed, 'max_abs_delta_k': max_delta},
        'limits': ['closed 640-second run but T0 history only; no later forecast valid time',
                   'same-cycle input consistency only; no independent skill or physical approval',
                   'raw residuals only; no sigma/covariance or new QC rule'],
        'pins_before_after': {k: {'before': before[k], 'after': after[k], 'unchanged': before[k] == after[k]} for k in before},
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'output': str(OUTPUT), 'metrics_A640_T0': metrics_a,
                      'metrics_O': metrics_o, 'A640_T0_T2_vs_O_T0_T2': result['A640_T0_T2_vs_O_T0_T2'],
                      'pin_count': len(before), 'pins_unchanged': before == after}, indent=2))

if __name__ == '__main__':
    main()
