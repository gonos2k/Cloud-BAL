#!/usr/bin/env python3
"""Launch and seal one reviewed 80-second native operation capture."""
import hashlib
import json
import os
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

from operation_events import same_phi_operands

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
RUNTIME = ROOT.parent / 'runtime' / 'native_build' / 'operation_capture'
VARIANT_ROOT = ROOT.parent / 'runtime/native_build/variants'
PROFILE = ROOT / 'tests/intel_toolchain.sh'
MPIRUN = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun')
MPI_ENV = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh')
NETCDF = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel')
TARGET_HISTORY = 'wrfout_d01_2026-08-16_12:00:00'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_plan():
    return json.loads((HERE / 'operation_plan.json').read_text())


def require_freeze():
    if ROOT.name != 'Cloud-BAL' or not (ROOT / 'tests/intel_toolchain.sh').is_file():
        raise ValueError('runner did not resolve the prepared Cloud-BAL worktree')
    if not RUNTIME.is_dir():
        raise ValueError('native operation runtime directory is missing')
    path = HERE / 'operation_freeze.json'
    expected = os.environ.get('GROUPED_OPERATION_FREEZE_SHA')
    if not expected or not path.is_file() or sha(path) != expected:
        raise ValueError('reviewed operation freeze and explicit root GO required')
    freeze = json.loads(path.read_text())
    for name, expected_hash in freeze['frozen_artifacts'].items():
        artifact = Path(name)
        if not artifact.is_file() or sha(artifact) != expected_hash:
            raise ValueError(f'frozen artifact changed: {name}')
    if freeze.get('plan_sha256') != sha(HERE / 'operation_plan.json'):
        raise ValueError('operation plan binding differs')
    plan = load_plan()
    for case in plan['case_schedule'].values():
        receipt = Path(case['case_receipt'])
        if not receipt.is_file() or sha(receipt) != case['case_receipt_sha256']:
            raise ValueError('prepared operation case receipt is missing or changed')
    return freeze


def input_hashes(case):
    receipt = json.loads((case / 'case_receipt.json').read_text())
    hashes = receipt['case_inputs_before']
    if any(sha(case / name) != digest for name, digest in hashes.items()):
        raise ValueError('case input changed before launch')
    return receipt, hashes


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def float_word(word):
    return struct.unpack('<f', bytes.fromhex(word))[0]


def word_float(value):
    return struct.pack('<f', f32(value)).hex()


def vector_word(event, register):
    raw = bytes.fromhex(event[register])
    if len(raw) != 16:
        raise ValueError('GDB did not record a full SIMD register')
    lane = event['lane']
    return raw[4 * lane:4 * lane + 4].hex()


def validate_operation(events, variant):
    target = [event for event in events if event['event'] == 'target_vector_entry']
    operations = [event for event in events if event['event'] == 'instruction']
    if len(target) != 1:
        raise ValueError('missing or duplicated target vector entry')
    expected_order = load_plan()['builds'][variant]['operation_order']
    if [event['instruction'] for event in operations] != expected_order:
        raise ValueError('target instruction order differs from this variant')
    entry = target[0]
    phi_entries = [event for event in events if event['event'] == 'target_phi_entry' and
                   event['sequence'] < entry['sequence']]
    if not phi_entries:
        raise ValueError('target operation has no preceding phi entry')
    phi_entry = phi_entries[-1]
    if not same_phi_operands(phi_entry, entry):
        raise ValueError('target operation operands do not bridge to the same phi entry')
    mapping = entry['operand_slot_mapping']
    slot = {mapping[name]: entry['input_words'][name]
            for name in ('ph', 'ph_next', 'phb', 'phb_next')}
    if set(slot) != {0, 1, 2, 3}:
        raise ValueError('input memory words do not bind all four vector slots')
    slot_names = {mapping[name]: name for name in ('ph', 'ph_next', 'phb', 'phb_next')}
    first_pair = (slot_names[0], slot_names[1])
    second_pair = (slot_names[2], slot_names[3])
    valid_pairs = {('ph_next', 'ph'), ('phb_next', 'phb')}
    if variant == 'GROUPED':
        if first_pair not in valid_pairs or second_pair not in valid_pairs or first_pair == second_pair:
            raise ValueError('grouped machine subtractions do not bind PH and PHB pairs')
    elif (first_pair, second_pair) != (('ph_next', 'ph'), ('phb_next', 'phb')):
        raise ValueError('sham machine operands do not match the original left-associated expression')
    sub1 = word_float(float_word(slot[0]) - float_word(slot[1]))
    if variant == 'GROUPED':
        sub2 = word_float(float_word(slot[2]) - float_word(slot[3]))
        numerator = word_float(float_word(sub1) + float_word(sub2))
        register_after_sub1, register_after_sub2, register_after_add, register_after_div = ('xmm2', 'xmm4', 'xmm4', 'xmm4')
    else:
        add = word_float(float_word(slot[2]) + float_word(sub1))
        sub2 = word_float(float_word(add) - float_word(slot[3]))
        numerator = sub2
        register_after_sub1, register_after_sub2, register_after_add, register_after_div = ('xmm2', 'xmm3', 'xmm3', 'xmm3')
    by_name = {event['instruction']: event for event in operations}
    expected_words = {
        'after_sub1': (register_after_sub1, sub1),
        'after_sub2': (register_after_sub2, sub2 if variant == 'GROUPED' else sub2),
        'after_add': (register_after_add, numerator if variant == 'GROUPED' else add),
    }
    for name, (register, expected) in expected_words.items():
        if vector_word(by_name[name], register) != expected:
            raise ValueError(f'{variant} float32 replay differs at {name}')
    numerator = numerator if variant == 'GROUPED' else sub2
    divisor = float_word(vector_word(by_name['after_div'], 'xmm0'))
    first_division = word_float(float_word(numerator) / divisor)
    if vector_word(by_name['after_div'], register_after_div) != first_division:
        raise ValueError('first vector division differs from binary32 replay')
    if (by_name['store_before']['al_candidate_word'] != by_name['store_after']['stored_al_word'] or
            by_name['store_before']['al_store_target_address'] != entry['al_address'] or
            by_name['store_after']['al_store_target_address'] != entry['al_address']):
        raise ValueError('pre/post AL store words or addresses differ')
    return {'variant': variant, 'input_words': entry['input_words'], 'lane': entry['lane'],
            'operand_slot_mapping': mapping, 'after_sub1_word': sub1,
            'after_sub2_word': sub2, 'numerator_word': numerator,
            'first_division_word': first_division, 'al_candidate_word': by_name['store_before']['al_candidate_word'],
            'stored_al_word': by_name['store_after']['stored_al_word'],
            'al_address': entry['al_address']}


def run(variant, arm):
    if (variant, arm) not in {('OLD_SHAM_RETRY1', 'B1'), ('GROUPED', 'B1'), ('GROUPED', 'DM065')}:
        raise ValueError('unsupported native operation case')
    freeze = require_freeze()
    plan = load_plan()
    case_key = f'{variant}_{arm}'
    case = Path(plan['case_schedule'][case_key]['case_receipt']).parent
    if not case.is_dir():
        raise ValueError('prepared native operation case is missing')
    receipt, before = input_hashes(case)
    expected_exe = receipt['source_executable_sha256']
    if sha(case / 'wrf.exe') != expected_exe:
        raise ValueError('case executable changed')
    profile_hash = sha(PROFILE)
    gdb_path = Path('/usr/bin/gdb')
    if sha(gdb_path) != freeze['gdb_sha256'] or sha(MPIRUN) != freeze['mpirun_sha256']:
        raise ValueError('GDB or MPI launcher differs from frozen binary')
    if profile_hash != freeze['profile_sha256']:
        raise ValueError('pinned Intel profile changed')
    output = case / 'operation_capture'
    output.mkdir(exist_ok=False)
    schedule = plan['case_schedule'][f'{variant}_{arm}']
    cpus = list(schedule['cpus'])
    cpu_list = ','.join(map(str, cpus))
    case_script = plan['builds'][variant]
    env = os.environ.copy()
    env.update({
        'OMP_NUM_THREADS': '1', 'OMP_DYNAMIC': 'FALSE',
        'I_MPI_PIN': '1', 'I_MPI_PIN_DOMAIN': 'core', 'I_MPI_PIN_RESPECT_CPUSET': '1',
        'I_MPI_PIN_PROCESSOR_LIST': cpu_list,
        'GROUPED_OWNER': '5', 'GROUPED_OUTPUT': str(output),
        'GROUPED_GDB_SCRIPT': str(HERE / 'operation_probe.py'),
        'GROUPED_EVENT_MODULE': str(HERE / 'operation_events.py'),
        'GROUPED_EXE_SHA256': expected_exe, 'GROUPED_SYMBOL_BASE': case_script['symbol_base'],
        'GROUPED_PC_JSON': json.dumps(case_script['pc'], sort_keys=True),
        'GROUPED_OPCODE_JSON': json.dumps(case_script['opcode'], sort_keys=True),
        'GROUPED_INDEX_REGISTER': case_script['index_register'],
        'GROUPED_OPERAND_BASES': ','.join(case_script['operand_bases']),
        'GROUPED_OPERATION_ORDER': json.dumps(case_script['operation_order']),
        'GROUPED_VARIANT': variant, 'GROUPED_ARM': arm,
    })
    launcher = ('set -euo pipefail; ulimit -s unlimited; source ' + str(PROFILE) +
                '; source ' + str(MPI_ENV) + ' >/dev/null 2>&1; export NETCDF=' + str(NETCDF) +
                '; export LD_LIBRARY_PATH="$NETCDF/lib:${LD_LIBRARY_PATH:-}"; exec taskset -c ' + cpu_list +
                ' ' + str(MPIRUN) + ' -np 8 /bin/bash ' + str(HERE / 'rank_wrapper.sh'))
    command = ['/bin/bash', '-lc', launcher]
    started = time.time()
    log = case / 'operation_launcher.log'
    with log.open('xb') as stream:
        proc = subprocess.Popen(command, cwd=case, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            code = proc.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            raise TimeoutError('80-second native capture exceeded 30-minute wall limit')
    after = {name: sha(case / name) for name in before}
    if code or after != before:
        raise ValueError('MPI exit or frozen input comparison failed')
    ranks = sorted(case.glob('rsl.out.*'))
    if len(ranks) != 8 or any('SUCCESS COMPLETE WRF' not in path.read_text(errors='replace') for path in ranks):
        raise ValueError('rank success markers missing')
    history = case / TARGET_HISTORY
    source = Path(receipt['source_root']) / TARGET_HISTORY
    if not history.is_file() or sha(history) != sha(source):
        raise ValueError('h00 history does not match corresponding frozen input run')
    require_freeze()
    event_file = output / 'operation_rank5.jsonl'
    events = [json.loads(line) for line in event_file.read_text().splitlines()]
    op_events = [event for event in events if event['event'] == 'instruction']
    operation_result = validate_operation(events, variant)
    result = {
        'schema': 'cp02_grouped_operation_capture_receipt_v1',
        'status': 'PASS_ACTUAL_OPERATION_CAPTURE', 'variant': variant, 'arm': arm,
        'case': str(case), 'case_receipt_sha256': sha(case / 'case_receipt.json'),
        'executable_sha256': sha(case / 'wrf.exe'), 'profile_sha256': profile_hash,
        'argv': command, 'cpus': cpus, 'elapsed_seconds': time.time() - started,
        'launcher_log_sha256': sha(log), 'event_file_sha256': sha(event_file),
        'event_count': len(events), 'instruction_events': len(op_events),
        'operation_result': operation_result,
        'input_hashes_before': before, 'input_hashes_after': after,
        'h00_sha256': sha(history), 'rank_log_count': len(ranks),
        'gdb_log_sha256': sha(output / 'gdb_rank5.log'),
        'source_operation': 'four PH/PHB operands to grouped/left-associated numerator and stored AL lane',
        'freeze_sha256': sha(HERE / 'operation_freeze.json'),
        'capture_identity': {'plan_sha256': freeze['plan_sha256'],
                             'freeze_sha256': sha(HERE / 'operation_freeze.json'),
                             'runner_sha256': sha(HERE / 'run_operation_case.py'),
                             'probe_sha256': sha(HERE / 'operation_probe.py'),
                             'event_helper_sha256': sha(HERE / 'operation_events.py')},
    }
    result_path = case / 'operation_receipt.json'
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': result['status'], 'case': str(case),
                      'receipt_sha256': sha(result_path), 'event_sha256': sha(event_file)}, sort_keys=True))


def revalidate(variant, arm):
    """Replay gates over a preserved successful model/capture run without relaunch."""
    if (variant, arm) not in {('OLD_SHAM_RETRY1', 'B1'), ('GROUPED', 'B1')}:
        raise ValueError('retrospective validation is only for the preserved B1 cases')
    freeze = require_freeze()
    plan = load_plan()
    case = Path(plan['case_schedule'][f'{variant}_{arm}']['case_receipt']).parent
    receipt, before = input_hashes(case)
    event_file = case / 'operation_capture/operation_rank5.jsonl'
    gdb_log = case / 'operation_capture/gdb_rank5.log'
    launcher_log = case / 'operation_launcher.log'
    if not event_file.is_file() or not gdb_log.is_file() or not launcher_log.is_file():
        raise ValueError('preserved capture artifacts are incomplete')
    after = {name: sha(case / name) for name in before}
    if after != before:
        raise ValueError('preserved case inputs changed')
    ranks = sorted(case.glob('rsl.out.*'))
    if len(ranks) != 8 or any('SUCCESS COMPLETE WRF' not in path.read_text(errors='replace') for path in ranks):
        raise ValueError('preserved MPI logs lack eight rank success markers')
    history = case / TARGET_HISTORY
    source_history = Path(receipt['source_root']) / TARGET_HISTORY
    if not history.is_file() or sha(history) != sha(source_history):
        raise ValueError('preserved h00 history differs from source history')
    events = [json.loads(line) for line in event_file.read_text().splitlines()]
    operation_result = validate_operation(events, variant)
    require_freeze()
    capture_identity = plan['preserved_capture_identities'][f'{variant}_{arm}']
    result = {
        'schema': 'cp02_grouped_operation_capture_receipt_v1',
        'status': 'PASS_ACTUAL_OPERATION_CAPTURE', 'validation_mode': 'RETROSPECTIVE_REPLAY_OF_PRESERVED_RUN',
        'variant': variant, 'arm': arm, 'case': str(case),
        'case_receipt_sha256': sha(case / 'case_receipt.json'),
        'executable_sha256': sha(case / 'wrf.exe'),
        'capture_identity': capture_identity,
        'validation_identity': {'plan_sha256': sha(HERE / 'operation_plan.json'),
                                'freeze_sha256': sha(HERE / 'operation_freeze.json'),
                                'runner_sha256': sha(HERE / 'run_operation_case.py')},
        'event_file_sha256': sha(event_file), 'gdb_log_sha256': sha(gdb_log),
        'launcher_log_sha256': sha(launcher_log), 'input_hashes_before': before,
        'input_hashes_after': after, 'h00_sha256': sha(history),
        'rank_log_count': len(ranks), 'rank_success_markers': 8,
        'operation_result': operation_result,
        'original_runner_outcome': 'postrun gate rejected because the validator compared AL/ALB metadata to four PH/PHB vector operands; MPI had exited zero and prior runtime gates passed',
        'original_gdb_event_file_and_executable_were_not_modified': True,
        'freeze_sha256': sha(HERE / 'operation_freeze.json'),
    }
    result_path = case / 'operation_receipt.json'
    with result_path.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': result['status'], 'validation_mode': result['validation_mode'],
                      'case': str(case), 'receipt_sha256': sha(result_path)}, sort_keys=True))


if __name__ == '__main__':
    if len(sys.argv) == 3:
        run(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 4 and sys.argv[1] == '--revalidate':
        revalidate(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit('usage: run_operation_case.py [--revalidate] VARIANT ARM')
