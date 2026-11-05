from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import resource
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SCRIPT = ROOT / 'docs/evidence/cp02_grouped_forecast_20261105/runtime/forecast.py'
WRAPPER = RUNTIME_SCRIPT.with_name('rank_wrapper.sh')
SPEC = importlib.util.spec_from_file_location('grouped_forecast_runtime', RUNTIME_SCRIPT)
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def six_hour_namelist() -> str:
    return '\n'.join((
        'run_hours = 6,', 'run_minutes = 0,', 'run_seconds = 0,',
        'end_hour = 18,', 'end_minute = 0,', 'end_second = 0,',
        'time_step = 20,', 'history_interval_s = 3600,', 'history_end_s = 21600,',
    ))


def make_prepare_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    source = tmp_path / 'source'
    source.mkdir()
    names = ['wrf.exe', 'namelist.input'] + [f'input_{i:02d}.dat' for i in range(87)]
    (source / 'namelist.input').write_text(six_hour_namelist(), encoding='ascii')
    (source / 'wrf.exe').write_bytes(b'old-sham-executable-fixture')
    for name in names:
        path = source / name
        if not path.exists():
            path.write_bytes(name.encode('ascii'))
    hashes = {name: digest(source / name) for name in names}
    receipt = tmp_path / 'inputs.json'
    receipt.write_text(json.dumps({'staged': hashes}), encoding='utf-8')
    build = tmp_path / 'build.json'
    build.write_text(json.dumps({
        'status': 'PASS', 'variant': 'OLD_SHAM',
        'executable': {'path': str(source / 'wrf.exe'), 'sha256': hashes['wrf.exe']},
        'inputs_unchanged': True,
        'compile': {'exit_code': 0}, 'link': {'exit_code': 0},
    }), encoding='utf-8')
    monkeypatch.setitem(runtime.SOURCES, 'A', source)
    monkeypatch.setitem(runtime.SOURCE_RECEIPTS, 'A', receipt)
    monkeypatch.setattr(runtime, 'RUNTIME', tmp_path / 'private_runtime')
    monkeypatch.setattr(runtime, 'ORIGINAL_EXE', hashes['wrf.exe'])
    monkeypatch.setattr(runtime, 'MPI', source / 'mpirun')
    (source / 'mpirun').write_bytes(b'mpi-fixture')
    monkeypatch.setattr(runtime, 'WRAPPER', source / 'rank_wrapper.sh')
    (source / 'rank_wrapper.sh').write_bytes(b'wrapper-fixture')
    return source, build


def test_six_hour_namelist_contract_rejects_wrong_or_duplicate_settings():
    runtime.validate_namelist(six_hour_namelist())
    with pytest.raises(ValueError, match='run_hours'):
        runtime.validate_namelist(six_hour_namelist().replace('run_hours = 6', 'run_hours = 5'))
    with pytest.raises(ValueError, match='run_hours'):
        runtime.validate_namelist(six_hour_namelist() + '\nrun_hours = 6,')


def test_prepare_copies_private_89_input_set_and_refuses_reuse(tmp_path, monkeypatch):
    source, build = make_prepare_inputs(tmp_path, monkeypatch)
    runtime.prepare('SHAM_A', build)
    dest = runtime.RUNTIME / 'SHAM_A'
    prepared = json.loads((dest / 'prepared.json').read_text())
    assert prepared['status'] == 'PREPARED'
    assert len(prepared['inputs']) == 89
    assert prepared['cpus'] == list(range(8))
    assert all((dest / name).stat().st_ino != (source / name).stat().st_ino for name in prepared['inputs'])
    assert all(digest(dest / name) == expected for name, expected in prepared['inputs'].items())
    prepared_hash = digest(dest / 'prepared.json')
    with pytest.raises(FileExistsError):
        runtime.prepare('SHAM_A', build)
    assert digest(dest / 'prepared.json') == prepared_hash


def make_run_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, launcher: bool):
    case = 'SHAM_A'
    source = tmp_path / 'source'
    dest = tmp_path / 'runtime' / case
    source.mkdir()
    dest.mkdir(parents=True)
    executable = tmp_path / 'ifx'
    executable.write_bytes(b'pinned-ifx-fixture')
    mpi = tmp_path / 'mpirun'
    mpi.write_bytes(b'mpi-fixture')
    wrapper = tmp_path / 'rank_wrapper.sh'
    wrapper.write_bytes(b'wrapper-fixture')
    (source / 'input.dat').write_bytes(b'source-input')
    (dest / 'input.dat').write_bytes(b'source-input')
    input_hash = digest(dest / 'input.dat')
    build = tmp_path / 'build.json'
    build.write_text(json.dumps({'ldd': {'resolved_libraries': []}}), encoding='utf-8')
    if launcher:
        (dest / 'launcher.log').write_text('existing bytes\n', encoding='ascii')
    prep = {
        'runner_sha256': digest(RUNTIME_SCRIPT),
        'build_receipt': str(build), 'build_receipt_sha256': digest(build),
        'mpi_sha256': digest(mpi), 'wrapper_sha256': digest(wrapper),
        'cpus': list(range(8)), 'inputs': {'input.dat': input_hash},
        'source': str(source), 'source_hashes': {'input.dat': input_hash},
    }
    (dest / 'prepared.json').write_text(json.dumps(prep), encoding='utf-8')
    monkeypatch.setattr(runtime, 'RUNTIME', tmp_path / 'runtime')
    monkeypatch.setattr(runtime, 'MPI', mpi)
    monkeypatch.setattr(runtime, 'WRAPPER', wrapper)
    monkeypatch.setattr(runtime, 'IFX_SHA', digest(executable))
    monkeypatch.setattr(runtime.os, 'sched_getaffinity', lambda _pid: set(range(64)))
    monkeypatch.setenv('CLOUD_BAL_FC', str(executable))
    return dest


def test_run_refuses_existing_launcher_without_mutating_case(tmp_path, monkeypatch):
    dest = make_run_case(tmp_path, monkeypatch, launcher=True)
    with pytest.raises(ValueError, match='refuse reused run directory'):
        runtime.run('SHAM_A')
    assert (dest / 'launcher.log').read_text(encoding='ascii') == 'existing bytes\n'
    assert not (dest / 'run_receipt.json').exists()


def test_run_refuses_limited_hard_stack_before_launch(tmp_path, monkeypatch):
    dest = make_run_case(tmp_path, monkeypatch, launcher=False)
    monkeypatch.setattr(runtime.resource, 'getrlimit', lambda _resource: (8192, 8192))
    monkeypatch.setattr(runtime.resource, 'setrlimit', lambda *_args: pytest.fail('must reject before changing limits'))
    with pytest.raises(ValueError, match='unlimited stack hard limit required'):
        runtime.run('SHAM_A')
    assert not (dest / 'launcher.log').exists()
    assert not (dest / 'run_receipt.json').exists()


def test_rank_wrapper_checks_rank_affinity_before_executable():
    cpu = min(os.sched_getaffinity(0))

    def set_unlimited_stack():
        resource.setrlimit(resource.RLIMIT_STACK, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
    env = os.environ.copy()
    env.update(GROUPED_PYTHON=sys.executable, GROUPED_CPUS=str(cpu), PMI_RANK='0')
    with tempfile.TemporaryDirectory(prefix='.test_rank_wrapper_', dir=ROOT) as temporary:
        tmp = Path(temporary)
        executable = tmp / 'wrf.exe'
        executable.write_text('#!/bin/sh\nprintf ran > model_started\n', encoding='ascii')
        executable.chmod(0o755)
        good = subprocess.run(
            ['taskset', '-c', str(cpu), '/bin/bash', str(WRAPPER)],
            cwd=tmp, env=env, text=True, capture_output=True, check=False, preexec_fn=set_unlimited_stack,
        )
        assert good.returncode == 0, good.stderr
        affinity = json.loads((tmp / 'affinity_rank0.json').read_text())
        assert affinity['cpus'] == [cpu]
        assert affinity['stack_limits'] == [resource.RLIM_INFINITY, resource.RLIM_INFINITY]
        assert (tmp / 'model_started').read_text() == 'ran'

        failed_dir = tmp / 'bad_rank'
        failed_dir.mkdir()
        (failed_dir / 'wrf.exe').write_text('#!/bin/sh\nprintf ran > model_started\n', encoding='ascii')
        (failed_dir / 'wrf.exe').chmod(0o755)
        env['PMI_RANK'] = '8'
        bad = subprocess.run(
            ['taskset', '-c', str(cpu), '/bin/bash', str(WRAPPER)],
            cwd=failed_dir, env=env, text=True, capture_output=True, check=False, preexec_fn=set_unlimited_stack,
        )
        assert bad.returncode != 0
        assert not (failed_dir / 'model_started').exists()
        assert not (failed_dir / 'affinity_rank8.json').exists()
