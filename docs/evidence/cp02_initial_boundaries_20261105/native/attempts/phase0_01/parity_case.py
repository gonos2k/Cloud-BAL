#!/usr/bin/env python3
"""Prepare and run bounded all-rank GDB parity probes; explicit GO required."""
import hashlib
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[5]
BUNDLE=ROOT/'docs/evidence/cp02_initial_boundaries_20261105'
RUNTIME=ROOT.parent/'runtime'
ATTEMPT=os.environ.get('CP05_ATTEMPT','')
if not re.fullmatch(r'[A-Za-z0-9_]{1,32}',ATTEMPT):
    raise ValueError('unique CP05_ATTEMPT is required')
PRIOR=ROOT.parent.parent/'b1_thermo_cloud_path_20261105/runtime/full'
B1=Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED')
DM=ROOT.parent.parent/'b1_rain_number_process_20261104/runtime/next_candidate/full'
CORNERS=ROOT/'docs/evidence/cp02_thermo_cloud_path_20261105/cohorts/results/unique_global_corners.csv'
PREVIOUS=ROOT/'docs/evidence/cp02_thermo_cloud_path_20261105'
PRIOR_MANIFEST=PREVIOUS/'analysis/input_manifest.json'
PRIOR_GLOBAL=PREVIOUS/'native/runs/external_global_streams.json'
EXE_SHA='68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
INPUT_SHA={'B1':'9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5',
           'DM065':'e6ed0750f88cb36e2600fd38c05e75513e8267dca72d9ee095cd5340a24ed175'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def selected_prefix(path, blocks=4):
    result=bytearray()
    with path.open('rb') as stream:
        for _ in range(blocks):
            header=stream.read(68)
            if len(header)!=68 or header[:8]!=b'CBSP0001':raise ValueError('bad selected baseline header')
            values=struct.unpack('>15i',header[8:])
            count=values[-1]; fields=values[-2]
            if fields!=16:raise ValueError('wrong selected field count')
            payload=stream.read(count*(12+4*fields))
            if len(payload)!=count*(12+4*fields):raise ValueError('truncated selected baseline')
            result.extend(header);result.extend(payload)
    return bytes(result)


def require_freeze():
    path = BUNDLE/'native/gdb/parity_freeze.json'
    expected = os.environ.get('CP05_GO_FREEZE_SHA')
    if not expected or not path.is_file() or sha(path) != expected:
        raise ValueError('reviewed parity freeze and explicit GO identity required')
    frozen = json.loads(path.read_text())
    required = [BUNDLE/'native/gdb/parity_probe.py', BUNDLE/'native/gdb/rank_wrapper.sh',
                BUNDLE/'native/gdb/parity_case.py', BUNDLE/'native/gdb_capture_proposal.json',
                BUNDLE/'native/source_lineage.json', BUNDLE/'native/gdb/test_parity_layout.py',
                ROOT/'tests/intel_toolchain.sh', CORNERS, PRIOR_MANIFEST, PRIOR_GLOBAL,
                Path('/usr/bin/gdb'), Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun'),
                B1/'wrf.exe', B1/'wrfinput_d01', DM/'wrfinput_d01']
    if set(frozen['sha256']) != {str(p.resolve()) for p in required}:
        raise ValueError('freeze inventory differs')
    if any(sha(path) != digest for path,digest in frozen['sha256'].items()):
        raise ValueError('frozen parity artifact changed')


def require_runtime_profile(executable):
    compiler = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx')
    libraries = {
        Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libimf.so'): '31f0ab1dcce74417de63e5c6876b5bb078c15efea4c49ca9afc233abbe80fda8',
        Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libintlc.so.5'): '2722b7aba08edf1d37c45b8f90070c87b499404b0888bd1b4150f34e123ef120',
        compiler: '909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef',
        Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/lib/libmpifort.so.12'): 'dd756ea87a74afd860dd5e7a936a3b774591f97fe931b7af94080689859d2b34',
        Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/lib/libmpi.so.12'): '5abc6334a074f2ca24a966669aaf70c8907fe2d9414389698737c36bbf8cabdd',
    }
    if Path(os.environ.get('CLOUD_BAL_FC','/nonexistent')).resolve() != compiler:
        raise ValueError('source the pinned Intel toolchain before running')
    if any(sha(path)!=expected for path,expected in libraries.items()):
        raise ValueError('pinned compiler or runtime library changed')
    directories = os.environ.get('LD_LIBRARY_PATH','').split(':')
    if str(compiler.parent.parent/'lib') not in directories or '/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel/lib' not in directories:
        raise ValueError('pinned Intel and NetCDF runtime directories required')
    resolved = subprocess.check_output(['ldd',str(executable)],text=True)
    for name, path in [('libimf.so','/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libimf.so'),
                       ('libintlc.so.5','/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libintlc.so.5'),
                       ('libmpifort.so.12','/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/lib/libmpifort.so.12'),
                       ('libmpi.so.12','/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/lib/libmpi.so.12')]:
        if not re.search(r'(?m)^\s*'+re.escape(name)+r'\s*=>\s*'+re.escape(path)+r'\s',resolved):
            raise ValueError('dynamic library resolution differs: '+name)
    if 'not found' in resolved:
        raise ValueError('unresolved shared library')
    return {str(path): digest for path,digest in libraries.items()}


def prepare(arm):
    source=B1 if arm=='B1' else DM
    source_receipt=json.loads((source/('receipt.json' if arm=='B1' else 'case_receipt.json')).read_text())
    source_hashes=source_receipt['staged_sha256_after' if arm=='B1' else 'inputs']
    if len(source_hashes)!=89 or any(sha(source/n)!=h for n,h in source_hashes.items()):raise ValueError('source inputs changed')
    if sha(source/'wrf.exe')!=EXE_SHA or sha(source/'wrfinput_d01')!=INPUT_SHA[arm]:raise ValueError('wrong input or executable')
    dest=RUNTIME/'gdb_parity'/ATTEMPT/arm
    dest.mkdir(parents=True,exist_ok=False)
    for name in source_hashes:shutil.copy2(source/name,dest/name)
    path=dest/'namelist.input';text=path.read_text()
    for key,value in [('run_hours','0'),('run_minutes','1'),('run_seconds','20'),('end_hour','12'),('end_minute','1'),('end_second','20'),('history_end_s','80')]:
        text,n=re.subn(r'(?m)^(\s*'+key+r'\s*=\s*)[^,\n]+',lambda m:m.group(1)+value,text)
        if n!=1:raise ValueError('bad namelist control '+key)
    path.write_text(text)
    if not re.search(r'(?m)^\s*time_step\s*=\s*20\s*,?\s*$',text):raise ValueError('wrong timestep')
    before={n:sha(dest/n) for n in source_hashes}
    (dest/'case_receipt.json').write_text(json.dumps({'source':str(source),'source_hashes':source_hashes,'inputs':before},indent=2)+'\n')


def observe_descendants(root_pid, seen):
    current = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            fields = (path/'stat').read_text().rsplit(')',1)[1].split()
            current[int(path.name)] = (int(fields[1]),int(fields[2]),int(fields[19]))
        except (OSError, ValueError, IndexError):
            continue
    parents = {root_pid} | {pid for pid,(group,start) in seen.items()
                            if pid in current and current[pid][2] == start}
    changed = True
    while changed:
        new = {pid for pid,(ppid,group,start) in current.items() if ppid in parents} - parents
        changed = bool(new); parents.update(new)
    for pid in parents - {root_pid}:
        if pid in current:
            _,group,start = current[pid]; seen[pid] = (group,start)


def terminate_group(process, seen):
    def send(pid, sig):
        try:
            os.kill(pid,sig)
        except ProcessLookupError:
            pass
    try:
        os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:
        pass
    for pid,(group,start) in seen.items():
        try:
            fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
            if group != process.pid and int(fields[19]) == start:
                send(pid,signal.SIGTERM)
        except (OSError,ValueError,IndexError):
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:
        pass
    for pid,(group,start) in seen.items():
        try:
            fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
            if group != process.pid and int(fields[19]) == start:
                send(pid,signal.SIGKILL)
        except (OSError,ValueError,IndexError):
            pass
    process.wait()


def run(arm):
    dest=RUNTIME/'gdb_parity'/ATTEMPT/arm
    inputs=json.loads((dest/'case_receipt.json').read_text())['inputs']
    if any(sha(dest/n)!=h for n,h in inputs.items()):raise ValueError('prepared inputs changed')
    output=dest/'gdb_capture';output.mkdir(exist_ok=False)
    cpus=range(48,56) if arm=='B1' else range(56,64)
    env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',I_MPI_PIN='1',I_MPI_PIN_DOMAIN='core',I_MPI_PIN_RESPECT_CPUSET='1',I_MPI_PIN_PROCESSOR_LIST=','.join(map(str,cpus)),CP05_OUTPUT=str(output),CP05_CORNERS=str(CORNERS),CP05_SCRIPT=str(BUNDLE/'native/gdb/parity_probe.py'))
    cmd=['taskset','-c',','.join(map(str,cpus)),'/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun','-np','8','/bin/bash',str(BUNDLE/'native/gdb/rank_wrapper.sh')]
    profile=require_runtime_profile(dest/'wrf.exe')
    start=time.time()
    with (dest/'launcher.log').open('xb') as log:
        process=subprocess.Popen(cmd,cwd=dest,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        seen={}
        try:
            while True:
                observe_descendants(process.pid,seen)
                try:
                    exit_code=process.wait(timeout=2)
                    break
                except subprocess.TimeoutExpired:
                    if time.time()-start > 1800:
                        raise TimeoutError('bounded MPI timeout')
        except BaseException:
            terminate_group(process,seen)
            (dest/'observed_descendants.json').write_text(json.dumps({'sampling':'approximately every 2 seconds; short-lived descendants may be missed','process_group':process.pid,'pids':seen},indent=2)+'\n')
            raise
        (dest/'observed_descendants.json').write_text(json.dumps({'sampling':'approximately every 2 seconds; short-lived descendants may be missed','process_group':process.pid,'pids':seen},indent=2)+'\n')
    after={n:sha(dest/n) for n in inputs}
    if exit_code or after!=inputs:
        terminate_group(process,seen)
        raise ValueError('MPI failed or staged inputs changed')
    logs=''.join(p.read_text(errors='replace') for p in dest.glob('rsl.out.*'))
    if 'SUCCESS COMPLETE WRF' not in logs:raise ValueError('WRF success marker absent')
    history=dest/'wrfout_d01_2026-08-16_12:00:00';ref=(B1 if arm=='B1' else DM)/history.name
    if not history.is_file() or sha(history)!=sha(ref):raise ValueError('h00 history parity failed')
    previous=json.loads(PRIOR_MANIFEST.read_text())
    global_inventory=json.loads(PRIOR_GLOBAL.read_text())
    previous_hashes={x['path']:x['sha256'] for x in previous['arms'][arm]}
    previous_hashes.update({x['path']:x['sha256'] for x in global_inventory['arms'][arm]})
    comparisons=[]
    for rank in range(8):
        for stage in ('entry','return'):
            old=PRIOR/arm/f'state_{"entry" if stage=="entry" else "wrapper_return"}_rank{rank}.bin'
            new=output/f'global_{stage}_rank{rank}.bin'
            if sha(old)!=previous_hashes[str(old.resolve())] or sha(new)!=sha(old):raise ValueError(f'global parity failed {arm}/{rank}/{stage}')
            comparisons.append({'rank':rank,'stage':stage,'global_sha256':sha(new)})
            old=PRIOR/arm/f'state_selected_{stage}_rank{rank}.bin'
            new=output/f'selected_{stage}_rank{rank}.bin'
            if sha(old)!=previous_hashes[str(old.resolve())] or new.read_bytes()!=selected_prefix(old):raise ValueError(f'selected parity failed {arm}/{rank}/{stage}')
            comparisons[-1]['selected_sha256']=sha(new)
    require_freeze()
    if require_runtime_profile(dest/'wrf.exe')!=profile:raise ValueError('runtime profile changed')
    source=B1 if arm=='B1' else DM
    original=json.loads((dest/'case_receipt.json').read_text())['source_hashes']
    if any(sha(source/n)!=h for n,h in original.items()):raise ValueError('source inputs changed')
    result={'status':'PASS','arm':arm,'argv':cmd,'elapsed_seconds':time.time()-start,'runtime_profile_sha256':profile,
            'observed_descendants_sha256':sha(dest/'observed_descendants.json'),
            'sampled_escaped_process_groups':{str(pid):group for pid,(group,start) in seen.items() if group != process.pid},
            'inputs_after':after,'h00_sha256':sha(history),'rank_stage_comparisons':comparisons}
    (dest/'parity_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(arm,'PASS',flush=True)


if __name__=='__main__':
    require_freeze()
    action,arm=sys.argv[1:]
    if arm not in ('B1','DM065'):raise ValueError('invalid arm')
    dest=RUNTIME/'gdb_parity'/ATTEMPT/arm
    prior_case=dest.exists()
    prior_capture=(dest/'gdb_capture').exists()
    try:
        {'prepare':prepare,'run':run}[action](arm)
    except BaseException as exc:
        dest=RUNTIME/'gdb_parity'/ATTEMPT/arm
        if dest.is_dir() and ((action == 'prepare' and not prior_case) or (action == 'run' and not prior_capture)):
            failure=dest/'failed_attempt.json'
            if not failure.exists():
                failure.write_text(json.dumps({'status':'FAILED_OR_INTERRUPTED','action':action,'error_type':type(exc).__name__,'error':str(exc)},indent=2)+'\n')
        raise
