#!/usr/bin/env python3
"""Stage and run baseline/conservative same-B1 six-hour forecasts on private inputs."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import time
import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[5]
BUNDLE = ROOT / 'docs/evidence/cp02_mp10_process_20261110'
RUNTIME = ROOT.parent / 'runtime/forecasts'
MPI = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun')
CASES = {'CONTROL': ('A', 'CONTROL', tuple(range(24, 32))),
         'MP10': ('A', 'MP10', tuple(range(32, 40)))}
SOURCES = {'A': Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED'),
           'B': Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_rain_number_process_20261104/runtime/next_candidate/full')}
SOURCE_RECEIPTS = {'A': ROOT / 'docs/evidence/six_hour_improvement_20261030/runtime/inputs.json',
                   'B': ROOT / 'docs/evidence/cp02_rain_number_process_20261104/followup/runtime/launch_receipt.json'}
HISTORIES = tuple(f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in range(12, 19))
WRAPPER = Path(__file__).with_name('rank_wrapper.sh')
IFX_SHA = '909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef'
ORIGINAL_EXE = '68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
CORE = ('QVAPOR','QCLOUD','QRAIN','QNRAIN','QICE','QSNOW','QGRAUP','T','P','PB','MU','MUB','PH','PHB','RAINC','RAINNC')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def input_map(arm):
    data = json.loads(SOURCE_RECEIPTS[arm].read_text())
    hashes = data['staged'] if arm == 'A' else data['inputs_after']
    require(len(hashes) == 89 and hashes['wrf.exe'] == ORIGINAL_EXE, 'historical input scope differs')
    require(all(Path(n).name == n for n in hashes), 'input names must be basenames')
    return hashes


def verify_inputs(folder, hashes):
    require(all((folder / n).is_file() and sha(folder / n) == h for n, h in hashes.items()), 'input identity differs: ' + str(folder))


def validate_namelist(text):
    for key, value in [('run_hours',6),('run_minutes',0),('run_seconds',0),('end_hour',18),('end_minute',0),('end_second',0),('time_step',20),('history_interval_s',3600),('history_end_s',21600)]:
        found = re.findall(r'^\s*' + key + r'\s*=\s*(\d+)\s*,?\s*$', text, re.M | re.I)
        require(len(found)==1 and int(found[0])==value, 'unexpected six-hour setting ' + key)


def prepare(case, build_receipt):
    arm, variant, cpus = CASES[case]
    source = SOURCES[arm]
    hashes = input_map(arm)
    verify_inputs(source, hashes)
    validate_namelist((source / 'namelist.input').read_text())
    build_receipt = Path(build_receipt).resolve()
    build = json.loads(build_receipt.read_text())
    require(build['status'] == 'PASS' and build['variant'] == variant, 'build has not passed')
    exe = Path(build['executable']['path'])
    require(sha(exe) == build['executable']['sha256'], 'build executable changed')
    require(build.get('inputs_unchanged') is True, 'build inputs were not verified unchanged')
    require(build['compile']['exit_code']==0 and build['link']['exit_code']==0, 'compile or link failed')
    dest = RUNTIME / case
    dest.mkdir(parents=True, exist_ok=False)
    for name in hashes:
        shutil.copy2(exe if name == 'wrf.exe' else source / name, dest / name)
        require(((dest/name).stat().st_dev,(dest/name).stat().st_ino) != ((exe if name=='wrf.exe' else source/name).stat().st_dev,(exe if name=='wrf.exe' else source/name).stat().st_ino), 'shared source inode')
    staged = {n: sha(dest / n) for n in hashes}
    require(all(staged[n] == h for n,h in hashes.items() if n != 'wrf.exe'), 'copy changed a non-executable input')
    require(staged['wrf.exe'] == build['executable']['sha256'], 'private executable differs')
    verify_inputs(source, hashes)
    write_new(dest / 'prepared.json', {'status':'PREPARED','case':case,'arm':arm,'variant':variant,'cpus':cpus,
        'initial_time_utc':'2026-08-16T12:00:00Z','end_time_utc':'2026-08-16T18:00:00Z',
        'source':str(source),'source_hashes':hashes,'inputs':staged,'build_receipt':str(build_receipt),
        'build_receipt_sha256':sha(build_receipt),'runner_sha256':sha(__file__),
        'source_receipt_sha256':sha(SOURCE_RECEIPTS[arm]),'mpi_sha256':sha(MPI),'wrapper_sha256':sha(WRAPPER)})
    print(case, 'PREPARED', flush=True)


def validate_histories(folder):
    names = sorted(p.name for p in folder.glob('wrfout*'))
    require(names == list(HISTORIES), 'seven exact history files required')
    rows = []
    for name in names:
        path = folder / name
        with netCDF4.Dataset(path) as ds:
            ds.set_auto_maskandscale(False)
            times = np.asarray(ds.variables['Times'][:]).tobytes().decode('ascii').rstrip('\0')
            require(times == name.removeprefix('wrfout_d01_'), 'history valid time differs')
            for field in CORE:
                require(field in ds.variables and np.isfinite(np.asarray(ds.variables[field][:])).all(), 'missing/nonfinite core field ' + field)
        rows.append({'path':str(path),'sha256':sha(path),'size_bytes':path.stat().st_size,'valid_utc':times.replace('_','T')+'Z'})
    return rows


def process_identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return {'start_ticks':fields[19],'state':fields[0]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def observe_descendants(pid, seen):
    pending=[pid]; visited=set()
    while pending:
        current=pending.pop()
        if current in visited:
            continue
        visited.add(current)
        identity=process_identity(current)
        if identity is None:
            continue
        seen.setdefault(str(current),identity['start_ticks'])
        try:
            pending.extend(int(x) for x in Path(f'/proc/{current}/task/{current}/children').read_text().split())
        except (FileNotFoundError, ProcessLookupError):
            pass


def surviving_descendants(seen):
    result=[]
    for pid,start in seen.items():
        actual=process_identity(int(pid))
        if actual is not None and actual['start_ticks']==start and actual['state']!='Z':
            result.append(int(pid))
    return result


def stop_owned(process, seen):
    try:
        os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:
        pass
    for pid in surviving_descendants(seen):
        try: os.kill(pid,signal.SIGTERM)
        except ProcessLookupError: pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        for pid in surviving_descendants(seen):
            try: os.kill(pid,signal.SIGKILL)
            except ProcessLookupError: pass
        process.wait(timeout=10)
    deadline=time.monotonic()+5
    while surviving_descendants(seen) and time.monotonic()<deadline:
        time.sleep(.1)
    for pid in surviving_descendants(seen):
        try: os.kill(pid,signal.SIGKILL)
        except ProcessLookupError: pass
    deadline=time.monotonic()+2
    while surviving_descendants(seen) and time.monotonic()<deadline:
        time.sleep(.1)


def run(case):
    dest = RUNTIME / case
    prep = json.loads((dest / 'prepared.json').read_text())
    require(prep['runner_sha256'] == sha(__file__), 'runner changed after preparation')
    require(prep['build_receipt_sha256'] == sha(prep['build_receipt']), 'build receipt changed')
    require(prep['mpi_sha256'] == sha(MPI), 'MPI changed')
    build=json.loads(Path(prep['build_receipt']).read_text())
    for library in build['ldd']['resolved_libraries']:
        require(sha(library['path'])==library['sha256'], 'runtime library changed')
    require(os.environ.get('CLOUD_BAL_FC','').endswith('/ifx') and sha(os.environ['CLOUD_BAL_FC'])==IFX_SHA, 'source pinned Intel profile before launch')
    expected_netcdf = '/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel'
    require(os.environ.get('NETCDF') == expected_netcdf
            and os.environ.get('LD_LIBRARY_PATH', '').startswith(expected_netcdf + '/lib:'),
            'launch must use the pinned NetCDF library prefix')
    resolved = subprocess.run(['ldd', str(dest / 'wrf.exe')], check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
    current_libraries = {}
    for line in resolved.splitlines():
        require('not found' not in line, 'unresolved launch library')
        match = re.search(r'=>\s+(/\S+)|^\s*(/\S+)\s+\(', line)
        if match:
            library = match.group(1) or match.group(2)
            current_libraries[library] = sha(library)
    expected_libraries = {item['path']: item['sha256'] for item in build['ldd']['resolved_libraries']}
    require(current_libraries == expected_libraries, 'launch library resolution differs from the build receipt')
    require(sha(WRAPPER)==prep['wrapper_sha256'], 'rank wrapper changed')
    require(set(prep['cpus']).issubset(os.sched_getaffinity(0)), 'requested CPUs unavailable')
    verify_inputs(dest, prep['inputs']); verify_inputs(Path(prep['source']), prep['source_hashes'])
    require(not (dest / 'launcher.log').exists(), 'refuse reused run directory')
    stack_before=resource.getrlimit(resource.RLIMIT_STACK)
    require(stack_before[1]==resource.RLIM_INFINITY, 'unlimited stack hard limit required by historical WRF environment')
    resource.setrlimit(resource.RLIMIT_STACK,(resource.RLIM_INFINITY,resource.RLIM_INFINITY))
    stack_launch=resource.getrlimit(resource.RLIMIT_STACK)
    cpus = ','.join(map(str, prep['cpus']))
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',I_MPI_PIN='1',I_MPI_PIN_DOMAIN='core',I_MPI_PIN_RESPECT_CPUSET='1',I_MPI_PIN_PROCESSOR_LIST=cpus,GROUPED_CPUS=cpus,GROUPED_PYTHON=sys.executable)
    command = ['taskset','-c',cpus,str(MPI),'-np','8','/bin/bash',str(WRAPPER)]
    start = time.monotonic(); start_utc=datetime.now(timezone.utc).isoformat()
    error = None; code = None; histories = []; seen={}
    with (dest / 'launcher.log').open('xb') as log:
        process = subprocess.Popen(command,cwd=dest,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while True:
                observe_descendants(process.pid,seen)
                try:
                    code=process.wait(timeout=2)
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic()-start>7200:
                        raise TimeoutError('six-hour run exceeded two-hour wall-clock limit')
        except BaseException as exc:
            error=type(exc).__name__+': '+str(exc)
            stop_owned(process,seen)
    survivors=surviving_descendants(seen)
    if survivors:
        stop_owned(process,seen)
        survivors=surviving_descendants(seen)
    write_new(dest/'descendants.json',{'sampling':'approximately every two seconds; short-lived descendants may be missed',
                                     'sampled_pid_start_ticks':seen,'live_after_cleanup':survivors})
    try:
        require(error is None and code == 0 and not survivors, 'model did not complete normally or sampled descendants survive')
        affinity=[json.loads((dest/f'affinity_rank{rank}.json').read_text()) for rank in range(8)]
        require(all(row['rank']==rank and row['cpus']==[prep['cpus'][rank]] for rank,row in enumerate(affinity)), 'rank affinity mismatch')
        logs = sorted(dest.glob('rsl.out.*'))
        require(len(logs) == 8 and all('SUCCESS COMPLETE WRF' in p.read_text(errors='replace') for p in logs), 'eight rank success markers required')
        verify_inputs(dest, prep['inputs']); verify_inputs(Path(prep['source']), prep['source_hashes'])
        histories = validate_histories(dest)
    except Exception as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    receipt = {'schema':'cp02_first_ice_velocity_six_hour_run_v1','status':'PASS' if error is None else 'FAIL',
        'case':case,'initialization':prep['arm'],'variant':prep['variant'],'initial_time_utc':prep['initial_time_utc'],
        'end_time_utc':prep['end_time_utc'],'exit_code':code,'failure':error,'argv':command,'cpus':prep['cpus'],
        'start_utc':start_utc,'end_utc':datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds':time.monotonic()-start,'descendants_sha256':sha(dest/'descendants.json'),'prepared_sha256':sha(dest/'prepared.json'),
        'runner_sha256':sha(__file__),'stack_limit_before':stack_before,'stack_limit_launch':stack_launch,'histories':histories,'inputs_after':{n:sha(dest/n) for n in prep['inputs']}}
    write_new(dest/'run_receipt.json',receipt)
    print(case, receipt['status'], flush=True)
    if error is not None:
        raise RuntimeError(error)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run'))
    parser.add_argument('case',choices=CASES)
    parser.add_argument('--build-receipt')
    args = parser.parse_args()
    if args.action == 'prepare':
        require(args.build_receipt is not None, 'build receipt required')
        prepare(args.case,args.build_receipt)
    else:
        run(args.case)
