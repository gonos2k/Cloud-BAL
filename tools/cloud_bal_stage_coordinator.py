#!/usr/bin/env python3
"""Evidence-only stage launch: detach expected input bytes before confined exec.

The caller owns the expected hashes and stage semantics. This is not a complete
publisher, source discovery mechanism, or dynamic-target authority grant.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import resource
import stat
import sys
import time

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from cloud_bal_transaction import _snapshot_product_at
from run_bound_executable import bind_executable, _read_only_flags, _read_all, _source_changed
from run_detached_runtime import stage_runtime, inspect_bound_loader, exec_detached_runtime


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_verified_file(path: Path, expected: str) -> bytes:
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        raise ValueError('expected SHA256 must be an owned lowercase digest')
    if path.resolve(strict=True) != path:
        raise ValueError(f'expected canonical regular file: {path}')
    fd = os.open(path, _read_only_flags())
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f'expected regular file: {path}')
        data = _read_all(fd)
        if _source_changed(before, os.fstat(fd)):
            raise ValueError(f'file changed during read: {path}')
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f'hash mismatch: {path}')
        return data
    finally:
        os.close(fd)


def verify_file(path: Path, expected: str) -> None:
    read_verified_file(path, expected)


def detach_inputs(source: Path, target: Path, expected: dict[str, str]) -> dict:
    if source.resolve(strict=True) != source or not expected:
        raise ValueError('source must be canonical; declared input inventory cannot be empty')
    target.mkdir(mode=0o700)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    source_fd, target_fd = os.open(source, flags), os.open(target, flags)
    try:
        for relative, expected_hash in sorted(expected.items()):
            _snapshot_product_at(source_fd, target_fd, relative)
            verify_file(target / relative, expected_hash)
    finally:
        os.close(source_fd)
        os.close(target_fd)
    return {relative: digest(target / relative) for relative in sorted(expected)}


def verify_build(build: dict) -> dict:
    """Verify owned manifest pins AND the files recorded in the source manifest."""
    manifests = {name: read_verified_file(Path(build[name + '_manifest']), build[name + '_sha256'])
                 for name in ('inputs', 'runtime')}
    entries = {}
    for line in manifests['inputs'].decode('utf-8').splitlines():
        expected, separator, filename = line.partition('  ')
        if not separator:
            raise ValueError('unsupported build input manifest line')
        source = Path(filename)
        verify_file(source, expected)
        entries[str(source)] = expected
    verify_file(Path(build['executable']), build['executable_sha256'])
    return entries


def _reap_descendants(closure_timeout):
    deadline=time.monotonic()+closure_timeout
    reaped=[]; signaled=set()
    while True:
        try:
            pid,status=os.waitpid(-1,os.WNOHANG)
        except ChildProcessError:
            return {'status':'ECHILD','reaped':reaped,'signaled':sorted(signaled)}
        if pid:
            reaped.append({'pid':pid,'exit_code':os.waitstatus_to_exitcode(status)})
            continue
        children=Path(f'/proc/self/task/{os.getpid()}/children').read_text().split()
        for text in children:
            child=int(text)
            try:
                pidfd=os.pidfd_open(child)
            except ProcessLookupError:
                continue
            try:
                signal.pidfd_send_signal(pidfd,signal.SIGKILL)
                signaled.add(child)
            except ProcessLookupError:
                pass
            finally:
                os.close(pidfd)
        if time.monotonic()>=deadline:
            return {'status':'TIMEOUT','reaped':reaped,'signaled':sorted(signaled)}
        time.sleep(0.01)


def _supervise_launch(root,run,timeout,closure_timeout=5):
    """A successful return requires the private subreaper to prove ECHILD.

    Unexpected supervisor death/timeouts fail closed; they never certify child
    closure. Each launch uses a fresh supervisor, so unrelated caller children
    remain owned and waitable by the caller.
    """
    path=root/'lifetime.json';started=time.monotonic()
    supervisor=os.fork()
    if supervisor==0:
        try:
            os.setsid()
            signal.signal(signal.SIGCHLD,signal.SIG_DFL)
            libc=ctypes.CDLL(None,use_errno=True)
            if libc.prctl(36,1,0,0,0)!=0:
                raise OSError(ctypes.get_errno(),'PR_SET_CHILD_SUBREAPER failed')
            leader=os.fork()
            if leader==0:
                try:
                    run()
                    os._exit(0)
                except BaseException:
                    os._exit(126)
            timed_out=False;leader_exit=None
            while True:
                done,status=os.waitpid(leader,os.WNOHANG)
                if done:
                    leader_exit=os.waitstatus_to_exitcode(status)
                    break
                if time.monotonic()-started>=timeout:
                    timed_out=True
                    os.kill(leader,signal.SIGKILL)
                    break
                time.sleep(0.01)
            closure=_reap_descendants(closure_timeout)
            if leader_exit is None:
                leader_exit=next((r['exit_code'] for r in closure['reaped'] if r['pid']==leader),None)
            receipt={'supervisor_pid':os.getpid(),'leader_pid':leader,'leader_exit_code':leader_exit,
                     'leader_timeout':timed_out,'closure':closure,
                     'exit_code':126 if closure['status']!='ECHILD' else 124 if timed_out else leader_exit}
            with path.open('x') as output:
                json.dump(receipt,output,indent=2);output.write('\n');output.flush();os.fsync(output.fileno())
            os._exit(0)
        except BaseException:
            os._exit(126)
    while True:
        done,status=os.waitpid(supervisor,os.WNOHANG)
        if done:
            break
        if time.monotonic()-started>=timeout+closure_timeout+5:
            os.kill(supervisor,signal.SIGKILL)
            _,status=os.waitpid(supervisor,0)
            return {'exit_code':126,'supervisor_exit_code':os.waitstatus_to_exitcode(status),
                    'closure':{'status':'SUPERVISOR_TIMEOUT'},'leader_exit_code':None}
        time.sleep(0.01)
    supervisor_exit=os.waitstatus_to_exitcode(status)
    if supervisor_exit!=0 or not path.exists():
        return {'exit_code':126,'supervisor_exit_code':supervisor_exit,
                'closure':{'status':'SUPERVISOR_FAILED'},'leader_exit_code':None}
    receipt=json.loads(path.read_text())
    receipt['supervisor_exit_code']=supervisor_exit
    return receipt


def launch_stage(root: Path, build: dict, source: Path, inputs: dict[str, str],
                 environment: dict[str, str], context_text: str, timeout: int,
                 arguments: tuple[str, ...] = ()) -> dict:
    """Run one terminated stage; inputs cannot overlap the writable output tree.

    Context must use the returned conventional paths root/inputs, root/output,
    and root/context.nml. The caller binds stage identities to these manifests.
    No inherited Cloud-BAL options or dynamic-loader environment are authority.
    """
    if timeout <= 0 or timeout > 600:
        raise ValueError('declare a finite stage timeout of at most 600 seconds')
    root.mkdir(mode=0o700)
    source_pins = verify_build(build)
    detached = detach_inputs(source, root / 'inputs', inputs)
    (root / 'output').mkdir(mode=0o700)
    context = root / 'context.nml'
    context.write_text(context_text)
    runtime_manifest = root / 'runtime.manifest.sha256'
    runtime_manifest.write_bytes(read_verified_file(Path(build['runtime_manifest']), build['runtime_sha256']))
    runtime = stage_runtime(runtime_manifest, root)
    executable_fd = bind_executable(Path(build['executable']), build['executable_sha256'])
    loader_fd = bind_executable(runtime.loader.snapshot, runtime.loader.sha256)
    loader = inspect_bound_loader(runtime, executable_fd, loader_fd)
    receipt = {'status': 'RUNNING', 'authority': 'EVIDENCE_ONLY_NO_DYNAMIC_AUTHORITY',
               'timeout_seconds': timeout, 'build': build, 'source_pins': source_pins,
               'coordinator_source_sha256': digest(Path(__file__).resolve()),
               'helper_source_observed_sha256': {str(TOOLS / name): digest(TOOLS / name)
                   for name in ('cloud_bal_transaction.py','run_bound_executable.py',
                                'run_detached_runtime.py','landlock_policy.py')},
               'detached_inputs': detached, 'context_sha256': digest(context),
               'environment': environment, 'arguments': list(arguments), 'stack_limit': 'unlimited', 'stdin': 'empty /dev/null descriptor',
               'loader_list': loader.stdout,
               'runtime': [{'path': str(x.snapshot), 'sha256': x.sha256} for x in runtime.entries]}
    receipt_path = root / 'launch_receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    started = time.monotonic()

    def execute_producer():
        try:
            os.setsid()
            resource.setrlimit(resource.RLIMIT_STACK, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
            nullfd = os.open('/dev/null', os.O_RDONLY)
            os.dup2(nullfd, 0)
            os.close(nullfd)
            logfd = os.open(root / 'stage.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.dup2(logfd, 1)
            os.dup2(logfd, 2)
            os.chdir(root / 'output')
            os.environ.clear()
            os.environ.update(environment)
            exec_detached_runtime(runtime, executable_fd, loader_fd, build['executable'], arguments,
                read_paths=[root / 'inputs', context, runtime.root],
                write_dirs=[root / 'output'])
        except BaseException as error:
            print(f'VERIFIED_LAUNCH_FAILED: {error}', file=sys.stderr, flush=True)
            raise

    lifetime = _supervise_launch(root, execute_producer, timeout)
    os.close(executable_fd)
    os.close(loader_fd)
    receipt.update(status='TERMINATED' if lifetime['closure']['status']=='ECHILD' else 'CHILD_CLOSURE_FAILURE',
                   exit_code=lifetime['exit_code'], lifetime=lifetime,
                   elapsed_seconds=time.monotonic() - started)
    if lifetime.get('leader_timeout'):
        receipt['status'] = 'TIMEOUT'
    receipt['input_post_hashes'] = {name: digest(root / 'inputs' / name) for name in inputs}
    if receipt['input_post_hashes'] != detached:
        receipt['status'] = 'INPUT_MUTATION_FAILURE'
        receipt['exit_code'] = 126
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
