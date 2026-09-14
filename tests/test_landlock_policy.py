"""Actual Linux subprocess checks of the explicit filesystem policy."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def child(script, root, expected_exit=0):
    result = subprocess.run(
        [sys.executable, "-c", script, str(TOOLS), str(root)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == expected_exit, (result.returncode, result.stdout, result.stderr)
    return result.stdout + result.stderr


SETUP = """
import errno, hashlib, json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from landlock_policy import restrict_filesystem
from run_bound_executable import bind_executable
root = Path(sys.argv[2])
"""


def test_file_access(root):
    script = SETUP + """
preopened = os.open(root/'outside/secret', os.O_RDONLY)
abi = restrict_filesystem(read_paths=[root/'inputs'], write_dirs=[root/'outputs'])
assert (root/'inputs/value').read_text() == 'input'
assert os.listdir(root/'inputs') == ['value']
(root/'outputs/product').write_text('output')
assert (root/'outputs/product').read_text() == 'output'
(root/'outputs/product').rename(root/'outputs/renamed')
(root/'outputs/renamed').unlink()
denied = 0
for action in (
    lambda: (root/'outside/secret').read_bytes(),
    lambda: os.listdir(root/'outside'),
    lambda: (root/'inputs/value').write_text('changed'),
    lambda: (root/'outside/new').write_text('new'),
    lambda: (root/'outputs/escape').read_bytes(),
    lambda: os.truncate(root/'inputs/value', 0),
    lambda: os.link(root/'outside/secret', root/'outputs/imported'),
):
    try:
        action()
    except PermissionError:
        denied += 1
    except OSError as error:
        assert error.errno == errno.EXDEV
        denied += 1
    else:
        raise AssertionError('undeclared operation succeeded')
# Already-open descriptors are deliberately outside Landlock's path policy.
assert os.read(preopened, 100) == b'outside'
os.close(preopened)
try:
    os.execve('/bin/true', ['true'], {})
except PermissionError:
    denied += 1
else:
    raise AssertionError('undeclared executable launched')
print(json.dumps({'abi': abi, 'denied': denied, 'preopened_fd_caveat_verified': True}))
"""
    result = json.loads(child(script, root))
    assert result['abi'] >= 3 and result['denied'] == 8
    assert (root/'inputs/value').read_text() == 'input'
    assert (root/'outside/secret').read_text() == 'outside'


def test_invalid_policy_is_reversible(root):
    script = SETUP + """
for arguments in (
    dict(read_paths=[Path('/')], write_dirs=[]),
    dict(read_paths=[root/'inputs'], write_dirs=[root]),
    dict(read_paths=[root/'outputs/escape'], write_dirs=[]),
    dict(read_paths=[], write_dirs=[root/'inputs/value']),
    dict(read_paths=[], write_dirs=[], write_files=[root/'outputs']),
):
    before = len(os.listdir('/proc/self/fd'))
    try:
        restrict_filesystem(**arguments)
    except ValueError:
        pass
    else:
        raise AssertionError('invalid policy accepted')
    assert len(os.listdir('/proc/self/fd')) == before
    assert (root/'outside/secret').read_text() == 'outside'
print('invalid policy rejected before restriction without leaked descriptors')
"""
    child(script, root)


def test_existing_aliases_reject(root):
    script = SETUP + """
source = root/'inputs/value'
alias = root/'outputs/alias'
os.link(source, alias)
for arguments in (
    dict(read_paths=[root/'inputs'], write_dirs=[root/'outputs']),
    dict(read_paths=[source], write_dirs=[], write_files=[alias]),
):
    try:
        restrict_filesystem(**arguments)
    except ValueError as error:
        assert 'single-link' in str(error)
    else:
        raise AssertionError('pre-existing hardlink alias accepted')
    assert source.read_text() == 'input'
    assert (root/'outside/secret').read_text() == 'outside'
alias.unlink()
os.link(root/'outside/secret', alias)
for arguments in (
    dict(read_paths=[root/'inputs'], write_dirs=[root/'outputs']),
    dict(read_paths=[], write_dirs=[], write_files=[alias]),
):
    try:
        restrict_filesystem(**arguments)
    except ValueError as error:
        assert 'single-link' in str(error)
    else:
        raise AssertionError('writable alias to undeclared outside file accepted')
    assert (root/'outside/secret').read_text() == 'outside'
alias.unlink()
(root/'inputs/symlink').symlink_to(source)
try:
    restrict_filesystem(read_paths=[root/'inputs'], write_dirs=[root/'outputs'])
except ValueError:
    pass
else:
    raise AssertionError('read tree symlink accepted')
(root/'inputs/symlink').unlink()
print('pre-existing hardlink and read tree symlink aliases rejected')
"""
    child(script, root)


def test_sealed_loader(root):
    # This capability probe uses existing system ELF files, not a Fortran build.
    loader = Path('/lib64/ld-linux-x86-64.so.2').resolve()
    library = Path('/lib/x86_64-linux-gnu/libc.so.6').resolve()
    libraries = root/'runtime'
    libraries.mkdir()
    for source, name in ((loader, 'loader'), (library, 'libc.so.6'), (Path('/bin/true'), 'main')):
        shutil.copyfile(source, libraries/name)
        (libraries/name).chmod(0o500)
    script = SETUP + """
runtime = root/'runtime'
loader = bind_executable(runtime/'loader', hashlib.sha256((runtime/'loader').read_bytes()).hexdigest())
main = bind_executable(runtime/'main', hashlib.sha256((runtime/'main').read_bytes()).hexdigest())
os.set_inheritable(main, True)
restrict_filesystem(read_paths=[runtime], write_dirs=[root/'outputs'])
print('SEALED_LOADER_EXEC_WITHOUT_HOST_READ_ACCESS', flush=True)
os.execve(f'/proc/self/fd/{loader}', ['loader', '--inhibit-cache', '--library-path',
          str(runtime), f'/proc/self/fd/{main}'], {})
"""
    assert 'SEALED_LOADER_EXEC_WITHOUT_HOST_READ_ACCESS' in child(script, root)
    (libraries/'libc.so.6').rename(root/'outside/libc.so.6')
    rejected = child(script, root, expected_exit=127)
    assert 'libc.so.6' in rejected and 'cannot open shared object file' in rejected


def main():
    # /tmp is noexec on the validation host; shared libraries need executable
    # mappings even when the main ELF and loader are sealed memfds.
    with tempfile.TemporaryDirectory(prefix='landlock_policy_', dir=TOOLS.parent/'scratch') as directory:
        root = Path(directory).resolve()
        for name in ('inputs', 'outputs', 'outside'):
            (root/name).mkdir()
        (root/'inputs/value').write_text('input')
        (root/'outside/secret').write_text('outside')
        (root/'outputs/escape').symlink_to(root/'outside/secret')
        test_file_access(root)
        test_invalid_policy_is_reversible(root)
        test_existing_aliases_reject(root)
        test_sealed_loader(root)
    print('Landlock read/write/execute policy tests passed')


if __name__ == '__main__':
    main()
