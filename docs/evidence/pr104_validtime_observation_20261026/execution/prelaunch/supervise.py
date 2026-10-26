"""Run the three reviewed, frozen C2 time contracts once and record closure."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
BUNDLE = Path('/var/tmp/pr104_runner_bundle_20261026')
PREP = Path('/var/tmp/pr104_validtime_preparation_20261026')
ARMS = ('HYDRO', 'AMPLITUDE', 'STRUCTURED')


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


def run_one(arm, prepared, pins):
    kwargs = prepared['kwargs']
    command = ['/usr/bin/python', str(BUNDLE / 'tools/pr86_time_response.py'),
               '--arm', arm, '--duration-seconds', '3600', '--output', kwargs['out'], '--execute']
    options = {'candidate_build_path': '--candidate-build',
               'disk_reference_receipt_path': '--disk-reference-receipt',
               'hydro_input_receipt_path': '--hydro-input-receipt',
               'wind_structure_input_receipt_path': '--wind-structure-input-receipt',
               'amplitude_control_input_receipt_path': '--amplitude-control-input-receipt',
               'pr102_preflight_path': '--pr102-preflight',
               'pr103_preflight_path': '--pr103-preflight',
               'shared_time_contract_path': '--shared-time-contract'}
    for key, option in options.items():
        if key in kwargs:
            command.extend([option, kwargs[key]])
    record = {'schema': 'pr104_forecast_supervision_v1', 'arm': arm, 'status': 'RUNNING',
              'started_utc': now(), 'argv': command, 'cwd': str(BUNDLE),
              'requested_seconds': 3600, 'expected_steps': 180,
              'field_outputs_inspected_while_running': False, 'source_pins_before': pins}
    path = HERE / f'{arm.lower()}_supervision.json'
    save(path, record)
    env = {**os.environ, 'OMP_NUM_THREADS': '1', 'OMP_DYNAMIC': 'FALSE',
           'OPENBLAS_NUM_THREADS': '1'}
    with (HERE / f'{arm.lower()}.stdout').open('wb') as stdout, \
            (HERE / f'{arm.lower()}.stderr').open('wb') as stderr:
        process = subprocess.Popen(command, cwd=BUNDLE, env=env, stdout=stdout,
                                   stderr=stderr, start_new_session=True)
        record.update(pid=process.pid, pgid=process.pid)
        save(path, record)
        record['cli_returncode'] = process.wait()
    record['closed_utc'] = now()
    record['source_pins_after'] = {name: sha(name) if Path(name).is_file() else None for name in pins}
    record['changed_source_pins'] = [name for name in pins
                                    if pins[name] != record['source_pins_after'][name]]
    receipt = Path(kwargs['out']) / 'receipt.json'
    if receipt.exists():
        result = json.loads(receipt.read_text())
        record['closed_receipt'] = {'path': str(receipt), 'sha256': sha(receipt)}
        record['model_status'] = result.get('status')
        record['model_returncode'] = result.get('returncode')
        record['completed_steps'] = result.get('timestep_count')
        record['final_completed_step'] = result.get('final_completed_step')
        record['requested_forecast_complete'] = (
            record['cli_returncode'] == 0 and result.get('arm') == arm
            and result.get('status') == 'COMPLETE'
            and result.get('returncode') == 0 and result.get('final_completed_step') == 180
            and result.get('timestep_count') == 180 and not record['changed_source_pins'])
    else:
        record['requested_forecast_complete'] = False
        record['missing_closed_receipt'] = True
    record['status'] = 'CLOSED'
    save(path, record)
    return record


def main():
    go_path = HERE / 'root_go.json'
    go = json.loads(go_path.read_text())
    if go['decision'] != 'GO' or go.get('launch_authorized') is not True:
        raise RuntimeError('No reviewed root GO')
    pins = go['source_pins']
    if any(sha(name) != digest for name, digest in pins.items()):
        raise RuntimeError('Prelaunch source pin changed')
    preparations = {arm: json.loads((PREP / f'{arm.lower()}_prepare.json').read_text()) for arm in ARMS}
    if any(Path(row['kwargs']['out']).exists() for row in preparations.values()):
        raise RuntimeError('Fresh arm outputs required; no duplicate run allowed')
    required = sum(row['prepared']['disk_guard']['required_free_bytes'] for row in preparations.values())
    if shutil.disk_usage(Path(preparations['HYDRO']['kwargs']['out']).parent).free < required:
        raise RuntimeError('Combined target filesystem disk guard failed')
    save(HERE / 'launch.json', {'schema': 'pr104_cohort_launch_v1', 'started_utc': now(),
                              'root_go': {'path': str(go_path), 'sha256': sha(go_path)},
                              'combined_required_free_bytes': required,
                              'physical_approval': 'FAIL_OPEN', 'observation_skill': 'NOT_EVALUATED'})
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda arm: run_one(arm, preparations[arm], pins), ARMS))
    save(HERE / 'cohort_closed.json', {'schema': 'pr104_cohort_closed_v1', 'closed_utc': now(),
                                     'all_requested_forecasts_complete': all(
                                         row['requested_forecast_complete'] for row in results),
                                     'arms': results})


if __name__ == '__main__':
    main()
