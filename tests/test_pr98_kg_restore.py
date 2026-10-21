import hashlib
import importlib.util
import shutil
from pathlib import Path

import pytest


HELPER = Path(__file__).resolve().parents[1] / 'docs/evidence/pr98_native_effect_20261022/kg/update_kg.py'
SPEC = importlib.util.spec_from_file_location('pr98_kg_restore_tested', HELPER)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Guard:
    @staticmethod
    def guard_directory(path):
        assert path.is_dir()

    @staticmethod
    def guard_destination(path):
        if path.is_symlink():
            raise ValueError(f'symlink destination: {path}')
        if path.exists():
            if not path.is_file():
                raise ValueError(f'non-file destination: {path}')

    @staticmethod
    def copy_checked(source, target):
        Guard.guard_destination(source)
        Guard.guard_destination(target)
        shutil.copy2(source, target)
        assert digest(source) == digest(target)


def setup_snapshot(tmp_path, original=b'prior'):
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    destination = snapshot / 'graph.json'
    destination.write_bytes(original)
    backup = tmp_path / 'backup.json'
    backup.write_bytes(original)
    records = {str(snapshot): {'graph.json': {'backup': str(backup), 'sha256': digest(backup)}}}
    return snapshot, destination, backup, records


def test_unchanged_snapshot_keeps_file_mtime(tmp_path):
    snapshot, destination, _, records = setup_snapshot(tmp_path)
    before = destination.stat().st_mtime_ns
    MODULE.restore_changed_snapshots(Guard, records)
    assert destination.stat().st_mtime_ns == before
    assert {item.name for item in snapshot.iterdir()} == {'graph.json'}


def test_changed_snapshot_restores_hash_bound_backup(tmp_path):
    _, destination, backup, records = setup_snapshot(tmp_path)
    destination.write_bytes(b'changed')
    MODULE.restore_changed_snapshots(Guard, records)
    assert digest(destination) == digest(backup)


def test_bad_backup_is_rejected_without_overwriting_destination(tmp_path):
    _, destination, backup, records = setup_snapshot(tmp_path)
    destination.write_bytes(b'changed')
    backup.write_bytes(b'bad backup')
    with pytest.raises(RuntimeError, match='backup drift'):
        MODULE.restore_changed_snapshots(Guard, records)
    assert destination.read_bytes() == b'changed'


def test_unknown_snapshot_member_is_rejected_and_preserved(tmp_path):
    snapshot, _, _, records = setup_snapshot(tmp_path)
    unknown = snapshot / 'concurrent.json'
    unknown.write_bytes(b'preserve')
    with pytest.raises(RuntimeError, match='unknown files preserved'):
        MODULE.restore_changed_snapshots(Guard, records)
    assert unknown.read_bytes() == b'preserve'


def test_identical_rollback_destination_keeps_file_mtime(tmp_path):
    backup = tmp_path / 'backup'
    destination = tmp_path / 'destination'
    backup.write_bytes(b'baseline')
    destination.write_bytes(b'baseline')
    before = destination.stat().st_mtime_ns
    MODULE.restore_backup_if_changed(Guard, backup, destination, digest(backup))
    assert destination.stat().st_mtime_ns == before


def test_bad_rollback_backup_is_rejected(tmp_path):
    backup = tmp_path / 'backup'
    destination = tmp_path / 'destination'
    backup.write_bytes(b'bad')
    destination.write_bytes(b'changed')
    with pytest.raises(RuntimeError, match='backup hash mismatch'):
        MODULE.restore_backup_if_changed(Guard, backup, destination, '0' * 64)
    assert destination.read_bytes() == b'changed'


def test_identical_snapshot_symlink_is_rejected(tmp_path):
    snapshot, destination, _, records = setup_snapshot(tmp_path)
    destination.unlink()
    destination.symlink_to(tmp_path / 'target')
    (tmp_path / 'target').write_bytes(b'prior')
    with pytest.raises(RuntimeError, match='symlink destination'):
        MODULE.restore_changed_snapshots(Guard, records)


def test_identical_rollback_symlink_is_rejected(tmp_path):
    backup = tmp_path / 'backup'
    destination = tmp_path / 'destination'
    target = tmp_path / 'target'
    backup.write_bytes(b'baseline')
    target.write_bytes(b'baseline')
    destination.symlink_to(target)
    with pytest.raises(ValueError, match='symlink destination'):
        MODULE.restore_backup_if_changed(Guard, backup, destination, digest(backup))
