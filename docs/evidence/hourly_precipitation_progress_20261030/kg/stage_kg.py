#!/usr/bin/env python3
"""Prepare isolated, frozen-path-only hourly precipitation progress graph updates."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path('/var/tmp/cloudbal-hourly-progress')
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
EVIDENCE = SOURCE / 'docs/evidence/hourly_precipitation_progress_20261030/kg'
BASELINE = EVIDENCE / 'baseline.json'
SELECTION = EVIDENCE / 'selection_lock.json'
STAGING = Path('/var/tmp/hourly_precipitation_progress_kg_20261030/final-graphify-uv')
SNAPSHOT = '2026-10-30-hourly-precipitation-progress'
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
# The reviewed extraction scope; staging still requires a frozen lock and GO.
REQUIRED_PATHS = {
    'tools/plot_hourly_forecast_distribution.py',
    'tools/plot_precipitation_concept_diagrams.py',
    'tests/test_hourly_forecast_distribution.py',
    'docs/build_hourly_progress_report.py',
}  # Frozen scope must be verified before staging.


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(root), *args])


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def snapshot_inventory(root: Path) -> dict:
    inventory = {}
    for folder in sorted((root / 'graphify-out').iterdir()):
        if folder.is_dir() and folder.name[:4].isdigit():
            inventory[folder.name] = {
                path.relative_to(folder).as_posix(): sha256(path)
                for path in sorted(folder.rglob('*')) if path.is_file()
            }
    return inventory


def verify_baseline(baseline: dict) -> None:
    require(baseline['dated_snapshot_count_total'] == 206,
            'expected the frozen 206 dated-snapshot baseline')
    roots = (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL'))
    for label, root in roots:
        record = baseline['maintained_roots'][label]
        require(sha256(root / 'graphify-out/graph.json') == record['graph_sha256'],
                f'{label} maintained graph changed after baseline capture')
        require(sha256(root / 'graphify-out/manifest.json') == record['manifest_sha256'],
                f'{label} maintained manifest changed after baseline capture')
        require(sha256(root / 'graphify-out/GRAPH_REPORT.md') ==
                record['graph_report_sha256'],
                f'{label} maintained graph report changed after baseline capture')
        require(snapshot_inventory(root) == record['dated_snapshots'],
                f'{label} dated snapshot inventory changed after baseline capture')
        status = git(root, 'status', '--short').decode('utf-8')
        require(status.splitlines() == record['git_status_exact'],
                f'{label} dirty state changed after baseline capture')
        require(hashlib.sha256(status.encode('utf-8')).hexdigest() == record['git_status_raw_sha256'],
                f'{label} exact dirty-state bytes changed after baseline capture')
    wiki = MAINTAINED / 'wiki'
    current_wiki = {
        path.name: sha256(path) for path in sorted(wiki.iterdir())
        if path.is_file() and (path.name.startswith('graph-report') or
                               path.name in {'index.md', 'log.md'})
    }
    require(current_wiki == baseline['wiki_hashes'], 'maintained wiki changed after baseline capture')


def load_selection(path: Path, expected_paths: set[str]) -> dict:
    require(path.is_file() and not path.is_symlink(), 'frozen selection lock is missing or unsafe')
    lock = json.loads(path.read_text())
    require(lock.get('status') == 'FROZEN', 'selection lock must be explicitly FROZEN')
    require(lock.get('review_status') == 'GO', 'selection lock review must be GO')
    require(bool(lock.get('freeze_id')), 'selection lock must include a freeze_id')
    require(lock.get('snapshot') == SNAPSHOT, 'frozen lock must name the hourly precipitation progress snapshot')
    hashes = lock.get('selected_source_sha256', {})
    require(set(hashes) == expected_paths,
            f'frozen selected paths must equal {sorted(expected_paths)}')
    require(lock.get('source_commit') == git(SOURCE, 'rev-parse', 'HEAD').decode().strip(),
            'selection lock source commit differs from this source worktree')
    for relative, expected in hashes.items():
        source = SOURCE / relative
        require(source.is_file() and not source.is_symlink(),
                f'frozen source is missing or unsafe: {relative}')
        require(sha256(source) == expected, f'frozen source hash changed: {relative}')
    require(lock.get('validation_summary') and lock.get('open_items'),
            'freeze must record final validation and open items for the staged wiki log')
    for relative, expected in lock.get('hash_only_sha256', {}).items():
        source = SOURCE / relative
        require(source.is_file() and not source.is_symlink(),
                f'hash-only source is missing or unsafe: {relative}')
        require(sha256(source) == expected, f'hash-only source hash changed: {relative}')
    return lock


def copy_graph_layer(source: Path, target: Path) -> None:
    target.mkdir(parents=True)
    for item in sorted(source.iterdir()):
        if item.is_dir():
            continue
        require(item.is_file() and not item.is_symlink(), f'unsupported graph layer member: {item}')
        if item.name != '.rebuild.lock':
            shutil.copy2(item, target / item.name)


def update_manifest_subset(manifest_path: Path, selected: list[tuple[Path, str]],
                           scan_corpus: list[Path] | None = None) -> None:
    """Update only selected rows and retain every untouched manifest row."""
    require(scan_corpus is None, 'subset update must not scan or prune the corpus')
    from graphify.detect import _md5_file

    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    original = json.loads(json.dumps(manifest))
    selected_keys = {key for _, key in selected}
    for source_path, manifest_key in selected:
        source_path = source_path.resolve()
        previous = manifest.get(manifest_key, {})
        if isinstance(previous, (int, float)):
            previous = {'mtime': previous, 'ast_hash': '', 'semantic_hash': ''}
        elif isinstance(previous, dict) and 'hash' in previous and 'ast_hash' not in previous:
            previous = {'mtime': previous.get('mtime', 0), 'ast_hash': previous['hash'],
                        'semantic_hash': ''}
        ast_hash = _md5_file(source_path)
        manifest[manifest_key] = {
            'mtime': source_path.stat().st_mtime,
            'ast_hash': ast_hash,
            'semantic_hash': previous.get('semantic_hash', '')
            if ast_hash == previous.get('ast_hash', '') else '',
        }
    require(set(original) <= set(manifest), 'subset manifest update dropped existing rows')
    for key, entry in original.items():
        if key not in selected_keys:
            require(manifest[key] == entry, f'subset manifest update changed untouched row: {key}')
    for source_path, manifest_key in selected:
        require(manifest_key in manifest, f'selected path is missing from manifest: {manifest_key}')
        require(manifest[manifest_key]['ast_hash'] == _md5_file(source_path),
                f'selected manifest hash mismatch: {manifest_key}')
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def graph_stats(graph: dict) -> dict:
    nodes = graph.get('nodes', [])
    return {
        'nodes': len(nodes),
        'edges': len(graph.get('links', graph.get('edges', []))),
        'communities': len({n.get('community') for n in nodes if n.get('community') is not None}),
    }


def graph_integrity(graph: dict) -> dict:
    node_list = graph.get('nodes', [])
    nodes = {node['id'] for node in node_list if 'id' in node}
    links = graph.get('links', graph.get('edges', []))
    endpoints = [(link.get('source'), link.get('target')) for link in links]
    endpoint_counts: dict[tuple, int] = {}
    exact_edges = set()
    exact_duplicates = 0
    for link, (source, target) in zip(links, endpoints):
        endpoint_counts[(source, target)] = endpoint_counts.get((source, target), 0) + 1
        encoded = json.dumps(link, sort_keys=True, separators=(',', ':'))
        if encoded in exact_edges:
            exact_duplicates += 1
        exact_edges.add(encoded)
    return {
        'missing_endpoint_edges': sum(source is None or target is None
                                      for source, target in endpoints),
        'dangling_endpoint_edges': sum(
            (source is not None and source not in nodes) or
            (target is not None and target not in nodes)
            for source, target in endpoints),
        'self_loop_edges': sum(source == target for source, target in endpoints),
        'exact_duplicate_edges': exact_duplicates,
        'same_endpoint_group_count': sum(count > 1 for count in endpoint_counts.values()),
    }


def refresh_staged_report(stage_root: Path, extracted_paths: set[str]) -> None:
    subprocess.run(
        ['graphify', 'cluster-only', str(stage_root), '--no-viz', '--no-label',
         '--graph', str(stage_root / 'graphify-out/graph.json')],
        cwd=stage_root, check=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    report = stage_root / 'graphify-out/GRAPH_REPORT.md'
    require(report.is_file(), f'scoped graph report was not generated: {report}')
    with report.open('a') as stream:
        stream.write('\n## hourly precipitation progress scoped update\n')
        stream.write(f'- Only {len(extracted_paths)} frozen Python source paths are structurally extracted.\n')
        stream.write('- Manifest updates are selected-path-only with scan_corpus=None; no corpus scan or prune occurs.\n')
        stream.write('- Report and figure evidence is hash-bound only; document/image semantics are not extracted.\n')
        stream.write('- Graph structure does not validate runtime behavior, physical assumptions, or scientific approval.\n')
        stream.write('- Fortran cross-file CALL extraction is partial.\n')


def write_staged_wiki(run: Path, records: dict, lock: dict) -> dict:
    source_commit = lock['source_commit']
    wiki = run / 'wiki'
    wiki.mkdir()
    for name in ('graph-report.md', 'graph-report-klaps50.md',
                 'graph-report-cloud-bal.md', 'index.md', 'log.md'):
        shutil.copy2(MAINTAINED / 'wiki' / name, wiki / name)
    shutil.copy2(run / 'KLAPS50/graphify-out/GRAPH_REPORT.md',
                 wiki / 'graph-report-klaps50.md')
    shutil.copy2(run / 'Cloud-BAL/graphify-out/GRAPH_REPORT.md',
                 wiki / 'graph-report-cloud-bal.md')

    index = wiki / 'graph-report.md'
    lines = index.read_text().splitlines()
    seen = set()
    for i, line in enumerate(lines):
        for label, directory, mirror in (
            ('KLAPS50', '.', 'graph-report-klaps50'),
            ('Cloud-BAL', 'Cloud-BAL/', 'graph-report-cloud-bal'),
        ):
            if line.startswith(f'| {label} |'):
                stats = records[label]['after']
                lines[i] = (f'| {label} | `{directory}` | {SNAPSHOT} (hourly precipitation progress) | '
                            f'{stats["nodes"]} | {stats["edges"]} | {stats["communities"]} | [[{mirror}]] |')
                seen.add(label)
    require(seen == {'KLAPS50', 'Cloud-BAL'}, 'graph-report index lacks a maintained corpus row')
    index.write_text('\n'.join(lines) + '\n')

    page = wiki / 'index.md'
    content = page.read_text()
    start = content.find('## Graph snapshot')
    require(start >= 0, 'wiki index has no Graph snapshot section')
    end = content.find('\n## ', start + 3)
    if end < 0:
        end = len(content)
    section = '## Graph snapshot\n\n' + '\n'.join(
        f'- {label}: {SNAPSHOT}; {records[label]["after"]["nodes"]} nodes / '
        f'{records[label]["after"]["edges"]} edges / {records[label]["after"]["communities"]} communities.'
        for label in ('KLAPS50', 'Cloud-BAL')
    ) + f'\n- Only {len(records["KLAPS50"]["selected_manifest_keys"])} frozen Python source paths are extracted; report and figure evidence is hash-bound only; document/image semantics are not extracted.\n'
    section += '- Graph freshness does not establish runtime or scientific validation.\n'
    content = content[:start] + section + content[end:]
    import re
    content, count = re.subn(r'(?m)^(date_modified:\s*)[^\r\n]+',
                             lambda match: match.group(1) + SNAPSHOT[:10], content, count=1)
    require(count == 1, 'wiki index date_modified is missing or ambiguous')
    page.write_text(content)

    with (wiki / 'log.md').open('a') as stream:
        stream.write(f'\n## [{SNAPSHOT[:10]}] kg-update | hourly precipitation progress\n')
        stream.write(f'- Source base `{source_commit}`; mode: selected Python AST extraction and staged merge.\n')
        for label in ('KLAPS50', 'Cloud-BAL'):
            record = records[label]
            before, after = record['before'], record['after']
            stream.write(f'- {label}: {SNAPSHOT}; {after["nodes"]} nodes / {after["edges"]} edges / '
                         f'{after["communities"]} communities; delta nodes={after["nodes"] - before["nodes"]}, '
                         f'edges={after["edges"] - before["edges"]}.\n')
        stream.write(f'- {len(records["KLAPS50"]["selected_manifest_keys"])} frozen Python paths structurally extracted; manifest update was selected-path-only with scan_corpus=None.\n')
        stream.write('- Report and figure evidence is hash-bound only; document/image semantics are not extracted.\n')
        stream.write(f'- Validation: {lock["validation_summary"]}\n')
        stream.write(f'- Open items: {lock["open_items"]}\n')
        stream.write('- Structural extraction does not establish runtime, physical, or scientific validity; '
                     'Fortran cross-file CALL extraction is partial.\n')
    return {name: sha256(wiki / name) for name in (
        'graph-report.md', 'graph-report-klaps50.md', 'graph-report-cloud-bal.md',
        'index.md', 'log.md')}


def stage_selected(lock: dict, extracted_paths: set[str], manifest_paths: set[str],
                   output: Path) -> dict:
    from graphify.build import build_merge
    from graphify.export import to_json
    from graphify.extract import extract

    run = output / f'stage-{lock["freeze_id"]}'
    require(not run.exists(), f'refuse to overwrite existing stage: {run}')
    run.mkdir(parents=True)
    roots = {'KLAPS50': run / 'KLAPS50', 'Cloud-BAL': run / 'Cloud-BAL'}
    maintained = {'KLAPS50': MAINTAINED, 'Cloud-BAL': MAINTAINED / 'Cloud-BAL'}
    for label in roots:
        copy_graph_layer(maintained[label] / 'graphify-out', roots[label] / 'graphify-out')

    records = {}
    for label in ('KLAPS50', 'Cloud-BAL'):
        stage_root = roots[label]
        graph_path = stage_root / 'graphify-out/graph.json'
        old_graph = json.loads(graph_path.read_text())
        old_node_ids = {node['id'] for node in old_graph.get('nodes', []) if 'id' in node}
        prefix = 'Cloud-BAL/' if label == 'KLAPS50' else ''
        staged_files = []
        manifest_rows = []
        for relative in sorted(extracted_paths):
            source_file = SOURCE / relative
            staged_file = stage_root / prefix / relative
            staged_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, staged_file)
            staged_files.append(staged_file)
        for relative in sorted(manifest_paths):
            source_file = SOURCE / relative
            manifest_rows.append((source_file, prefix + relative))
        extracted = extract(staged_files, cache_root=stage_root, parallel=False)
        merged = build_merge([extracted], graph_path=graph_path, root=stage_root,
                             directed=old_graph.get('directed', False), dedup=False)
        communities: dict[int, list[str]] = {}
        next_id = max((int(n.get('community', 0)) for n in old_graph.get('nodes', [])), default=0) + 1
        for node, attrs in merged.nodes(data=True):
            community = attrs.get('community')
            if community is None:
                community = next_id
                next_id += 1
            communities.setdefault(community, []).append(node)
        require(to_json(merged, communities, str(graph_path)), f'Graphify merge failed for {label}')
        new_graph = json.loads(graph_path.read_text())
        new_node_ids = {node['id'] for node in new_graph.get('nodes', []) if 'id' in node}
        require(old_node_ids <= new_node_ids, f'{label} graph update removed prior node IDs')
        update_manifest_subset(stage_root / 'graphify-out/manifest.json', manifest_rows,
                               scan_corpus=None)
        refresh_staged_report(stage_root, extracted_paths)
        new_graph = json.loads(graph_path.read_text())
        integrity = graph_integrity(new_graph)
        require(all(value == 0 for value in integrity.values()),
                f'{label} staged graph integrity failed: {integrity}')
        snapshot_dir = stage_root / 'graphify-out' / SNAPSHOT
        snapshot_dir.mkdir()
        for filename in GRAPH_FILES:
            shutil.copy2(stage_root / 'graphify-out' / filename, snapshot_dir / filename)
        records[label] = {
            'before': graph_stats(old_graph),
            'after': graph_stats(new_graph),
            'prior_node_ids_preserved': len(old_node_ids),
            'selected_manifest_keys': [key for _, key in manifest_rows],
            'selected_source_sha256': lock['selected_source_sha256'],
            'snapshot_file_sha256': {
                filename: sha256(snapshot_dir / filename) for filename in GRAPH_FILES
            },
            'integrity_zero_counts': integrity,
        }
    wiki_hashes = write_staged_wiki(run, records, lock)
    return {'stage': str(run), 'corpora': records, 'staged_wiki_sha256': wiki_hashes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--lock', type=Path, default=SELECTION)
    parser.add_argument('--stage', action='store_true',
                        help='run selected-path extraction after explicit freeze')
    parser.add_argument('--paths', nargs='*', default=[],
                        help='the exact frozen hourly precipitation progress paths, relative to the source worktree')
    args = parser.parse_args()

    import graphify
    require('/.local/share/uv/tools/graphifyy/' in str(Path(sys.executable).resolve()) or
            '/.local/share/uv/tools/graphifyy/' in str(Path(graphify.__file__).resolve()),
            'run staging with the pinned Graphify uv-tool interpreter')
    require(subprocess.check_output(['graphify', '--version'], text=True).strip() ==
            'graphify 0.9.53', 'Graphify must remain pinned at 0.9.53')
    baseline = json.loads(BASELINE.read_text())
    verify_baseline(baseline)
    require(args.stage, 'baseline verified; extraction is disabled until --stage after source freeze')
    new_paths = set(args.paths)
    require(bool(REQUIRED_PATHS), 'final source scope is not yet set')
    require(new_paths == REQUIRED_PATHS,
            f'provide exactly the frozen Python paths: {sorted(REQUIRED_PATHS)}')
    expected_paths = new_paths
    lock = load_selection(args.lock, expected_paths)
    result = stage_selected(lock, new_paths, expected_paths, STAGING)
    # Ensure evidence files stayed bound and maintained roots remained untouched.
    load_selection(args.lock, expected_paths)
    verify_baseline(baseline)
    result.update({
        'status': 'STAGED_ONLY_NO_MAINTAINED_WRITES',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'baseline_sha256': sha256(BASELINE),
        'selection_lock_sha256': sha256(args.lock),
        'dated_snapshots_preserved': 206,
        'source_extraction_scope': sorted(new_paths),
        'manifest_update_scope': sorted(expected_paths),
        'hash_only_sha256': lock.get('hash_only_sha256', {}),
        'extraction_limits': [
            'Only selected Python files are structurally extracted; report and figure evidence is hash-bound only; document/image semantics are not extracted.',
            'Manifest update is selected-path-only with scan_corpus=None; no corpus scan or prune occurs.',
            'Only the explicit hash-only evidence list is bound; document/image semantics are not extracted.',
            'Graph freshness does not establish runtime behavior, physical assumptions, or scientific approval.',
            'Fortran cross-file CALL extraction is partial.',
        ],
    })
    receipt = EVIDENCE / 'stage_receipt.json'
    receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
