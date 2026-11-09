#!/usr/bin/env python3
"""Read-only verification of the frozen pre-update maintained KG baseline."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[4]
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
BASELINE = SOURCE / 'docs/evidence/cp02_sedimentation_conservation_20261109/kg/baseline.json'
STAMP = '2026-11-09-sedimentation-conservation'
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md', 'graph-report-cloud-bal.md', 'index.md', 'log.md')
EXPECTED_COUNTS = {'KLAPS50': 123, 'Cloud-BAL': 127}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def git_head(root: Path) -> str:
    return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()


def git_status(root: Path) -> bytes:
    return subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain=v1', '-z'])


def inventory(root: Path) -> dict:
    result = {}
    graph_root = root / 'graphify-out'
    for folder in sorted(graph_root.iterdir()):
        if folder.is_dir() and folder.name[:4].isdigit():
            result[folder.name] = {
                path.relative_to(folder).as_posix(): sha256(path)
                for path in sorted(folder.rglob('*'))
                if path.is_file() and not path.is_symlink()
                and '__pycache__' not in path.parts
                and path.suffix not in ('.pyc', '.lock')
            }
    return result


def main() -> None:
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    assert baseline['status'] == 'READ_ONLY_BASELINE_CAPTURED'
    assert baseline['planned_snapshot_label'] == STAMP
    assert baseline['maintained_roots_written'] is False
    assert baseline['dated_snapshot_count_total'] == sum(EXPECTED_COUNTS.values()) == 250
    assert STAMP not in baseline['maintained_roots']['Cloud-BAL']['dated_snapshots']
    roots = {'KLAPS50': MAINTAINED, 'Cloud-BAL': MAINTAINED / 'Cloud-BAL'}
    for label, root in roots.items():
        record = baseline['maintained_roots'][label]
        status = git_status(root)
        assert record['dated_snapshot_count'] == EXPECTED_COUNTS[label]
        assert len(record['dated_snapshots']) == EXPECTED_COUNTS[label]
        assert inventory(root) == record['dated_snapshots'], f'{label} dated snapshots changed'
        assert git_head(root) == record['git_state']['head'], f'{label} HEAD changed'
        assert hashlib.sha256(status).hexdigest() == record['git_state']['status_sha256'], f'{label} dirty state changed'
        assert len(status.split(b'\0')) - 1 == record['git_state']['status_entry_count'], f'{label} status count changed'
        active = {name: sha256(root / 'graphify-out' / name) for name in GRAPH_FILES}
        assert active == record['active_graph_trio_sha256'], f'{label} active graph trio changed'
    wiki = {name: sha256(MAINTAINED / 'wiki' / name) for name in WIKI_FILES}
    assert wiki == baseline['wiki_mirror_sha256'], 'maintained wiki mirrors changed'
    assert sha256(MAINTAINED / 'AGENTS.md') == baseline['agents_sha256'], 'maintained instructions changed'
    source_record = baseline['source_worktree']
    assert git_head(SOURCE) == source_record['head'], 'source worktree HEAD changed'
    source_graph = SOURCE / 'graphify-out'
    assert {name: sha256(source_graph / name) for name in GRAPH_FILES} == source_record['active_graph_trio_sha256'], 'source active graph trio changed'
    print(json.dumps({'status': 'PASS_BASELINE_UNCHANGED', 'snapshot_counts': EXPECTED_COUNTS,
                      'total': 250, 'maintained_roots_written': False}, indent=2))


if __name__ == '__main__':
    main()
