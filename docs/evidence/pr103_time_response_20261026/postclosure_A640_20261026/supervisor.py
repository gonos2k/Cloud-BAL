from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

WORK = Path('/var/tmp/pr103_sixarm_history_postprocess_v2_20261026')
PRODUCTS = WORK / 'products'
PLOTS = PRODUCTS / 'plots'
REPO = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr103_amplitude_control_20261026/Cloud-BAL')
TOOLS = REPO / 'tools'
sys.path.insert(0, str(TOOLS))
import pr103_history_response as reader
import pr103_time_response as time_response
import pr86_compare_response as history
import pr101_projected_c2_response as pr101
import pr102_response as pr102
import pr86_time_response as runner

A_RUN = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr103_amplitude20_capture_20261026/AMPLITUDE640_RUN')
A_RUN_RECEIPT_SHA256 = '76792551d703e5e05af778b39482269dcb09ed16b83a5780514e920fcd1e5296'
READER_SHA256 = 'f1e68d5d381d4168820aeb8e3f089bcb1443caa883cccc5f6b44c77a88506a62'
TIME_RESPONSE_SHA256 = '49df07b2a9feaf7cd0783d23c0f3da2b4d284648087c670efaed9ecb871d2f20'
PLOTTER_PATH = TOOLS / 'pr103_history_response_plot.py'
PLOTTER_SHA256 = '00ccda5f208089398e0c6815d607962afd4e414cfc996e400478ead434ac6b1d'
ANALYZER_PATH = TOOLS / 'pr103_history_response.py'
EXPECTED_BASELINE = {'readback': reader.FIVEARM_READBACK_SHA256,
                    'execution': reader.FIVEARM_EXECUTION_SHA256,
                    'publication': reader.FIVEARM_PUBLICATION_SHA256,
                    'response': reader.FIVEARM_RESPONSE_SHA256}

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def add(path_set: set[Path], value) -> None:
    if value:
        path_set.add(Path(value).resolve())

def make_pins() -> tuple[dict[str, str], dict]:
    if digest(A_RUN / 'receipt.json') != A_RUN_RECEIPT_SHA256:
        raise RuntimeError('closed A640 receipt hash changed')
    if digest(ANALYZER_PATH) != READER_SHA256 or digest(Path(time_response.__file__)) != TIME_RESPONSE_SHA256:
        raise RuntimeError('reviewed history-analysis code hash changed')
    if digest(PLOTTER_PATH) != PLOTTER_SHA256:
        raise RuntimeError('reviewed plotter hash changed')
    for name, expected in EXPECTED_BASELINE.items():
        path = {'readback': reader.FIVEARM_READBACK, 'execution': reader.FIVEARM_EXECUTION,
                'publication': reader.FIVEARM_PUBLICATION, 'response': reader.FIVEARM_RESPONSE}[name]
        if digest(path) != expected:
            raise RuntimeError(f'frozen five-arm {name} hash changed')

    fivearm = reader._read_fivearm()
    pr102_preflight, reference_receipts, _ = reader._closed_cohort()
    a_receipt, _, a_gate, _ = reader._closed_a_run(A_RUN)
    roots = {**reader.RUN_ROOTS, 'A': A_RUN}
    receipts = {**reference_receipts, 'A': a_receipt}
    paths: set[Path] = set()
    for path in (reader.FIVEARM_READBACK, reader.FIVEARM_EXECUTION,
                 reader.FIVEARM_PUBLICATION, reader.FIVEARM_RESPONSE,
                 reader.PR102_PREFLIGHT, pr102.native.COMPOSITION,
                 time_response.A_CANDIDATE_PATH, time_response.A_PROPOSAL_PATH,
                 A_RUN / 'receipt.json', A_RUN / 'preflight.json',
                 Path(a_gate['path']), ANALYZER_PATH, Path(time_response.__file__),
                 PLOTTER_PATH, Path(history.__file__), Path(pr101.__file__),
                 Path(pr102.__file__), Path(pr102.cloud.__file__), Path(runner.__file__),
                 Path(__file__).resolve(),
                 Path(json.loads(reader.FIVEARM_EXECUTION.read_text())['command'][1])):
        add(paths, path)
    for arm, receipt in receipts.items():
        root = roots[arm]
        add(paths, root / 'receipt.json')
        add(paths, root / 'preflight.json')
        for row in receipt.get('generated_files', []):
            if Path(row.get('path', '')).name.startswith('wrfout_d01_'):
                add(paths, root / 'run' / row['path'])
        build = receipt.get('candidate_build')
        if isinstance(build, dict):
            for key in ('receipt_path', 'executable_path', 'profile_path'):
                add(paths, build.get(key))
    for row in pr102_preflight.get('evidence_artifacts', []):
        add(paths, row['path'])
    for row in a_gate.get('evidence_artifacts', []):
        add(paths, row['path'])
    pins = {str(path): digest(path) for path in sorted(paths)}
    if pins[str((A_RUN / 'receipt.json').resolve())] != A_RUN_RECEIPT_SHA256:
        raise RuntimeError('A640 closed receipt differs from reviewed identity')
    if pins[str(ANALYZER_PATH.resolve())] != READER_SHA256:
        raise RuntimeError('analysis source changed during pin capture')
    return pins, {'fivearm_status': fivearm['status'], 'control_arms': sorted(reference_receipts),
                  'a_gate_evidence_count': len(a_gate.get('evidence_artifacts', [])),
                  'pr102_evidence_count': len(pr102_preflight.get('evidence_artifacts', [])),
                  'history_paths': {arm: [r['path'] for r in receipt.get('generated_files', [])
                                           if Path(r.get('path', '')).name.startswith('wrfout_d01_')]
                                    for arm, receipt in receipts.items()}}

def summarize(response: dict) -> dict:
    arms = ('N', 'A')
    rows = []
    for field in ('pressure', 'Phi', 'W', 'QC'):
        for region in ('support', 'buffer'):
            n = response['metrics'][field]['N'][region]
            a = response['metrics'][field]['A'][region]
            rows.append({'field': field, 'region': region,
                         'I_N_0_600': n['I_0_600'], 'I_A_0_600': a['I_0_600'],
                         'I_N_over_I_A': n['I_0_600'] / a['I_0_600'] if a['I_0_600'] else None,
                         'N_first_segment_mean_square': n['I_0_60'],
                         'A_first_segment_mean_square': a['I_0_60'],
                         'N_first_endpoints': [n['endpoint_0s'], n['endpoint_60s']],
                         'A_first_endpoints': [a['endpoint_0s'], a['endpoint_60s']],
                         'N_saved_maximum': n['saved_maximum'],
                         'N_saved_maximum_times_seconds': n['saved_maximum_times_seconds'],
                         'A_saved_maximum': a['saved_maximum'],
                         'A_saved_maximum_times_seconds': a['saved_maximum_times_seconds'],
                         'N_at_600s': n['saved_values'][-1], 'A_at_600s': a['saved_values'][-1]})
    pairs = []
    for pair in ('A_minus_P', 'A_minus_N', 'A_minus_H'):
        for field in ('pressure', 'Phi', 'W', 'QC'):
            for region in ('support', 'buffer'):
                metric = response['explicit_paired_metrics'][pair][field][region]
                pairs.append({'pair': pair, 'field': field, 'region': region,
                              'I_0_600': metric['I_0_600'],
                              'I_0_60': metric['I_0_60'],
                              'saved_maximum': metric['saved_maximum'],
                              'saved_maximum_times_seconds': metric['saved_maximum_times_seconds'],
                              'endpoint_0s': metric['endpoint_0s'],
                              'endpoint_60s': metric['endpoint_60s'],
                              'at_600s': metric['saved_values'][-1]})
    return {'schema': 'pr103_sixarm_summary_v1', 'status': 'DESCRIPTIVE_ONLY',
            'times_seconds': response['times_seconds'], 'NA_integral_rows': rows,
            'direct_paired_array_rows': pairs, 'physical_approval': 'FAIL_OPEN',
            'observation_skill': 'NOT_EVALUATED',
            'interpretation': 'Ratios and saved-time responses are descriptive. The 0–60s segment contains two saved snapshots; no high-frequency claim. N and A may differ across early, integrated, peak, and final summaries; no ordering is imposed.'}

def write_summary(summary: dict) -> None:
    (PRODUCTS / 'allsavedtime_summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    lines = ['# PR103 six-arm saved-history summary', '',
             'Descriptive fixed-mask history only; no observation-skill claim or energy interpretation.',
             'The 0–60s segment has two saved snapshots only. No 640s history extrapolation is used.',
             'N/A is the raw ratio of the reported fixed-schedule mean-square integrals; no ordering is imposed.', '',
             '## N and A comparisons', '',
             '| Field | Mask | I_N 0–600 | I_A 0–600 | N/A | I_N 0–60 | I_A 0–60 | N max (s) | A max (s) | N 600s | A 600s |',
             '|---|---|---:|---:|---:|---:|---:|---|---|---:|---:|']
    for row in summary['NA_integral_rows']:
        lines.append(f"| {row['field']} | {row['region']} | {row['I_N_0_600']:.8g} | {row['I_A_0_600']:.8g} | {row['I_N_over_I_A']:.8g} | {row['N_first_segment_mean_square']:.8g} | {row['A_first_segment_mean_square']:.8g} | {row['N_saved_maximum_times_seconds']} | {row['A_saved_maximum_times_seconds']} | {row['N_at_600s']:.8g} | {row['A_at_600s']:.8g} |")
    lines.extend(['', '## Direct paired-array comparisons', '',
                  'Each pair RMS is computed from actual paired history arrays; it is not derived from arm−OFF RMS.', '',
                  '| Pair | Field | Mask | I 0–600 | I 0–60 | Saved max (s) | 0s | 60s | 600s |',
                  '|---|---|---|---:|---:|---|---:|---:|---:|'])
    for row in summary['direct_paired_array_rows']:
        lines.append(f"| {row['pair']} | {row['field']} | {row['region']} | {row['I_0_600']:.8g} | {row['I_0_60']:.8g} | {row['saved_maximum']:.8g} ({row['saved_maximum_times_seconds']}) | {row['endpoint_0s']:.8g} | {row['endpoint_60s']:.8g} | {row['at_600s']:.8g} |")
    (PRODUCTS / 'allsavedtime_summary.md').write_text('\n'.join(lines) + '\n')

def main() -> int:
    if PRODUCTS.exists():
        raise RuntimeError('products path already exists')
    PRODUCTS.mkdir()
    analyzer_argv = [sys.executable, str(ANALYZER_PATH), '--a-run-root', str(A_RUN),
                     '--output-dir', str(PRODUCTS / 'analysis')]
    plotter_argv = [sys.executable, str(PLOTTER_PATH), '--input',
                    str(PRODUCTS / 'analysis' / 'allsavedtime_response.json'),
                    '--output-dir', str(PLOTS)]
    pins_before, checked = make_pins()
    record = {'schema': 'pr103_sixarm_postprocess_supervisor_v1', 'status': 'RUNNING',
              'started_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'work_dir': str(WORK), 'commands': [analyzer_argv, plotter_argv],
              'cwd': str(WORK), 'analysis_source_sha256': READER_SHA256,
              'time_response_sha256': TIME_RESPONSE_SHA256, 'plotter_sha256': PLOTTER_SHA256,
              'A640_receipt_sha256': A_RUN_RECEIPT_SHA256,
              'preflight_counts': checked, 'pins_before': pins_before}
    execution = WORK / 'execution.json'
    with execution.open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1',
               OMP_NUM_THREADS='1', OMP_DYNAMIC='FALSE')
    with (WORK / 'analysis.log').open('xb') as stream:
        analysis = subprocess.run(analyzer_argv, cwd=WORK, env=env, stdout=stream,
                                  stderr=subprocess.STDOUT, check=False)
    plot = None
    if analysis.returncode == 0:
        result = json.loads((PRODUCTS / 'analysis' / 'allsavedtime_response.json').read_text())
        write_summary(summarize(result))
        with (WORK / 'plot.log').open('xb') as stream:
            plot = subprocess.run(plotter_argv, cwd=WORK, env=env, stdout=stream,
                                  stderr=subprocess.STDOUT, check=False)
    pins_after = {path: digest(Path(path)) for path in pins_before}
    internal = {}
    internal_path = PRODUCTS / 'analysis' / 'execution_receipt.json'
    if internal_path.is_file():
        internal = json.loads(internal_path.read_text())
    record.update({'finished_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                   'analysis_returncode': analysis.returncode,
                   'plot_returncode': None if plot is None else plot.returncode,
                   'internal_analysis_status': internal.get('status'),
                   'pins_after': pins_after,
                   'pins_unchanged': pins_before == pins_after,
                   'status': 'COMPLETE' if analysis.returncode == 0 and plot is not None
                   and plot.returncode == 0 and internal.get('status') == 'COMPLETE'
                   and pins_before == pins_after else 'FAILED',
                   'products': {str(path.relative_to(WORK)): {'sha256': digest(path), 'bytes': path.stat().st_size}
                                for path in PRODUCTS.rglob('*') if path.is_file()}})
    with execution.open('w') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'status': record['status'], 'execution': str(execution),
                      'execution_sha256': digest(execution), 'analysis_returncode': analysis.returncode,
                      'plot_returncode': None if plot is None else plot.returncode,
                      'pin_count': len(pins_before), 'pins_unchanged': pins_before == pins_after}, sort_keys=True))
    return 0 if record['status'] == 'COMPLETE' else 1

if __name__ == '__main__':
    raise SystemExit(main())
