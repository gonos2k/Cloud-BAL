"""Validation launcher: deny external research inputs and Intel execution."""
import ctypes
import json
import os
from pathlib import Path
import stat
import sys

root = Path('/var/tmp/pr109_isolated')
lib = ctypes.CDLL(None, use_errno=True)
class Ruleset(ctypes.Structure):
    _fields_ = [('handled_access_fs', ctypes.c_uint64)]
class Rule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('allowed_access', ctypes.c_uint64), ('parent_fd', ctypes.c_int)]
def checked(result):
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return result
abi = checked(lib.syscall(444, 0, 0, 1))
assert abi >= 3
all_access = (1 << 15) - 1
read_exec = (1 << 0) | (1 << 2) | (1 << 3)
fd = checked(lib.syscall(444, ctypes.byref(Ruleset(all_access)), ctypes.sizeof(Ruleset), 0))
paths = [(root, all_access)] + [(Path(p).resolve(), read_exec) for p in ('/usr','/lib','/lib64','/etc','/proc','/dev')]
paths += [(Path('/'), 1 << 3), (Path('/dev/null'), (1 << 1) | (1 << 14))]
for path, access in paths:
    pfd = os.open(path, os.O_PATH | os.O_CLOEXEC)
    if not stat.S_ISDIR(os.fstat(pfd).st_mode):
        access &= (1 << 0) | (1 << 1) | (1 << 2) | (1 << 14)
    checked(lib.syscall(445, fd, 1, ctypes.byref(Rule(access, pfd)), 0))
    os.close(pfd)
checked(lib.prctl(38, 1, 0, 0, 0))
checked(lib.syscall(446, fd, 0))
os.close(fd)
external = '/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh'
compiler = '/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx'
probes = {}
for name, path in [('research', external), ('compiler_read', compiler), ('old_venv', '/var/tmp/pr108_portable_env_20261026/pyvenv.cfg')]:
    try:
        Path(path).read_bytes()
    except PermissionError:
        probes[name] = 'EACCES'
    else:
        raise RuntimeError('external read permitted: ' + path)
pid = os.fork()
if pid == 0:
    try:
        os.execv(compiler, [compiler, '--version'])
    except PermissionError:
        os._exit(73)
    os._exit(74)
_, status = os.waitpid(pid, 0)
assert os.waitstatus_to_exitcode(status) == 73
probes['compiler_execute'] = 'EACCES'
print('CONFINEMENT_PROBES ' + json.dumps({'abi':abi, 'probes':probes}), flush=True)
os.chdir(root / 'Cloud-BAL')
env = {'HOME':str(root/'home'), 'TMPDIR':str(root/'tmp'), 'PATH':str(root/'environment/bin')+':/usr/bin:/bin', 'LANG':'C.UTF-8', 'LC_ALL':'C.UTF-8', 'PYTHON_BIN':str(root/'environment/bin/python'), 'PYTHONNOUSERSITE':'1', 'MPLCONFIGDIR':str(root/'tmp/matplotlib')}
os.execve('/usr/bin/bash', ['bash', *sys.argv[1:]], env)
