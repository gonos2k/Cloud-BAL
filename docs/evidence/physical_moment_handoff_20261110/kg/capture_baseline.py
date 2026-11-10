#!/usr/bin/env python3
"""Capture read-only graph and maintained-root state for the physical moment handoff update."""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[4]
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
STAMP = '2026-11-10-physical-moment-handoff'
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md', 'graph-report-cloud-bal.md', 'index.md', 'log.md')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def git_state(root: Path) -> dict:
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    status = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain=v1', '-z'])
    return {
        'head': head,
        'status_sha256': hashlib.sha256(status).hexdigest(),
        'status_porcelain_v1_z_base64': base64.b64encode(status).decode('ascii'),
        'status_entry_count': max(0, len(status.split(b'\0')) - 1),
    }


def graph_counts(path: Path) -> dict:
    graph = json.loads(path.read_text(encoding='utf-8'))
    nodes = graph.get('nodes', [])
    links = graph.get('links', graph.get('edges', []))
    communities = {node.get('community') for node in nodes if node.get('community') is not None}
    return {'nodes': len(nodes), 'edges': len(links), 'communities': len(communities)}


def dated_inventory(root: Path) -> dict:
    graph_root = root / 'graphify-out'
    inventory = {}
    for folder in sorted(graph_root.iterdir()):
        if folder.is_dir() and folder.name[:4].isdigit():
            inventory[folder.name] = {
                path.relative_to(folder).as_posix(): sha256(path)
                for path in sorted(folder.rglob('*'))
                if path.is_file() and not path.is_symlink()
                and '__pycache__' not in path.parts
                and path.suffix not in ('.pyc', '.lock')
            }
    return inventory


def maintained_record(root: Path) -> dict:
    graph_root = root / 'graphify-out'
    graph = json.loads((graph_root / 'graph.json').read_text(encoding='utf-8'))
    return {
        'git_state': git_state(root),
        'dated_snapshots': dated_inventory(root),
        'dated_snapshot_count': len(dated_inventory(root)),
        'active_graph_trio_sha256': {name: sha256(graph_root / name) for name in GRAPH_FILES},
        'active_graph_counts': graph_counts(graph_root / 'graph.json'),
        'built_at_commit': graph.get('built_at_commit'),
    }


def main() -> None:
    roots = {'KLAPS50': MAINTAINED, 'Cloud-BAL': MAINTAINED / 'Cloud-BAL'}
    records = {label: maintained_record(root) for label, root in roots.items()}
    source_graph = SOURCE / 'graphify-out'
    source = {
        'head': subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
        'git_state': git_state(SOURCE),
        'active_graph_trio_sha256': {name: sha256(source_graph / name) for name in GRAPH_FILES},
        'active_graph_counts': graph_counts(source_graph / 'graph.json'),
    }
    result = {
        'status': 'READ_ONLY_BASELINE_CAPTURED',
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'planned_snapshot_label': STAMP,
        'maintained_roots_written': False,
        'maintained_roots': records,
        'dated_snapshot_count_total': sum(row['dated_snapshot_count'] for row in records.values()),
        'wiki_mirror_sha256': {name: sha256(MAINTAINED / 'wiki' / name) for name in WIKI_FILES},
        'agents_sha256': sha256(MAINTAINED / 'AGENTS.md'),
        'source_worktree': source,
        'limitations': [
            'This is a read-only inventory of the pre-update maintained graph state.',
            'The source worktree HEAD is the PR follow-up base; maintained roots can lag it.',
            'Graph snapshots do not validate runtime behavior or scientific correctness.',
        ],
    }
    target = SOURCE / 'docs/evidence/physical_moment_handoff_20261110/kg/baseline.json'
    with target.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({
        'status': result['status'],
        'snapshot_counts': {label: row['dated_snapshot_count'] for label, row in records.items()},
        'total': result['dated_snapshot_count_total'],
        'source_head': source['head'],
        'maintained_heads': {label: row['git_state']['head'] for label, row in records.items()},
        'source_graph': source['active_graph_counts'],
    }, indent=2))


if __name__ == '__main__':
    main()
