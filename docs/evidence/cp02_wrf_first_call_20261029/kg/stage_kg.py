#!/usr/bin/env python3
"""Build an isolated, frozen-path-only CP02 WRF first-call KG stage."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path('/var/tmp/cloudbal-cp02-wrf-first-call')
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
BASELINE = SOURCE / 'docs/evidence/cp02_wrf_first_call_20261029/kg/baseline.json'
EXPECTED_PATHS = {
    'tools/cp02_wrf_first_call.py',
    'tests/test_cp02_wrf_first_call.py',
}
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md', 'graph-report-cloud-bal.md', 'index.md', 'log.md')
DIAGNOSTIC_ZERO_KEYS = (
    'missing_endpoint_edges',
    'dangling_endpoint_edges',
    'self_loop_edges',
    'exact_duplicate_edges',
    'same_endpoint_group_count',
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).rstrip('\n')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def snapshot_inventory(root: Path) -> dict:
    result = {}
    for folder in sorted((root / 'graphify-out').iterdir()):
        if folder.is_dir() and folder.name[:4].isdigit():
            result[folder.name] = {
                path.name: sha256(path)
                for path in sorted(folder.iterdir())
                if path.is_file()
            }
    return result


def verify_maintained_baseline(baseline: dict) -> None:
    require(baseline['dated_snapshot_count_total'] == 190, 'expected the frozen 190-snapshot baseline')
    roots = (
        ('KLAPS50', MAINTAINED),
        ('Cloud-BAL', MAINTAINED / 'Cloud-BAL'),
    )
    for name, root in roots:
        prior = baseline['maintained_roots'][name]
        require(sha256(root / 'graphify-out/graph.json') == prior['graph_sha256'],
                f'{name} maintained graph differs from the prepared baseline')
        require(snapshot_inventory(root) == prior['dated_snapshots'],
                f'{name} dated snapshot inventory changed after baseline capture')
        require(git(root, 'status', '--short').splitlines() == prior['git_status_exact'],
                f'{name} maintained-root dirty state changed after baseline capture')


def load_frozen_selection(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), 'frozen selection lock is missing or unsafe')
    lock = json.loads(path.read_text())
    require(lock.get('status') == 'FROZEN', 'selection lock must be explicitly FROZEN')
    require(lock.get('review_status') == 'GO', 'selection lock review must be GO')
    require(bool(lock.get('freeze_id')), 'selection lock must include a freeze_id')
    hashes = lock.get('selected_source_sha256', {})
    require(set(hashes) == EXPECTED_PATHS,
            f'frozen selected paths must equal {sorted(EXPECTED_PATHS)}')
    require(lock.get('source_commit') == git(SOURCE, 'rev-parse', 'HEAD'),
            'selection lock source commit differs from the source worktree HEAD')
    for relative, expected in hashes.items():
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(), f'selected source is missing or unsafe: {relative}')
        require(sha256(path) == expected, f'frozen selected-source hash changed: {relative}')
    return lock


def copy_graph_layer(source: Path, target: Path) -> None:
    target.mkdir(parents=True)
    for item in sorted(source.iterdir()):
        if item.is_dir():
            continue
        require(item.is_file() and not item.is_symlink(), f'unsupported Graphify layer member: {item}')
        if item.name == '.rebuild.lock':
            continue
        shutil.copy2(item, target / item.name)


def graph_stats(graph: dict) -> dict:
    return {
        'nodes': len(graph.get('nodes', [])),
        'edges': len(graph.get('links', graph.get('edges', []))),
        'communities': len({node.get('community') for node in graph.get('nodes', [])
                            if node.get('community') is not None}),
    }


def extract_selected(label: str, stage_root: Path, source_prefix: str,
                     selected: list[dict], output: Path) -> dict:
    from graphify.build import build_merge
    from graphify.detect import save_manifest
    from graphify.export import to_json
    from graphify.extract import extract

    graph_path = stage_root / 'graphify-out/graph.json'
    old_graph = json.loads(graph_path.read_text())
    staged_paths = []
    for item in selected:
        relative = Path(item['path'])
        source_path = SOURCE / relative
        staged_path = stage_root / source_prefix / relative
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, staged_path)
        staged_paths.append(staged_path)

    # This direct AST call is deliberately limited to the two frozen Python paths.
    extraction = extract(staged_paths, cache_root=stage_root, parallel=False)
    (output / f'{label.lower().replace("-", "_")}_extraction.json').write_text(
        json.dumps(extraction, indent=2, sort_keys=True) + '\n')
    merged = build_merge(
        [extraction], graph_path=graph_path, root=stage_root,
        directed=old_graph.get('directed', False), dedup=False,
    )
    communities: dict[int, list[str]] = {}
    next_id = max((int(node.get('community', 0)) for node in old_graph.get('nodes', [])), default=0) + 1
    for node, attributes in merged.nodes(data=True):
        community = attributes.get('community')
        if community is None:
            community = next_id
            next_id += 1
        communities.setdefault(community, []).append(node)
    require(to_json(merged, communities, str(graph_path)), f'Graphify merge failed for {label}')

    manifest_path = stage_root / 'graphify-out/manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    corpus_paths = set(manifest.get('files', {}))
    corpus_paths.update(str(path.relative_to(stage_root)) for path in staged_paths)
    save_manifest(
        {'code': [str(path) for path in staged_paths]},
        root=stage_root,
        kind='ast',
        scan_corpus={str(stage_root / path) for path in corpus_paths},
    )
    return {
        'before': graph_stats(old_graph),
        'extraction_nodes': len(extraction.get('nodes', [])),
        'extraction_edges': len(extraction.get('edges', [])),
    }


def cluster_and_diagnose(label: str, root: Path, output: Path) -> dict:
    graph_path = root / 'graphify-out/graph.json'
    log_path = output / f'{label.lower().replace("-", "_")}_cluster.log'
    with log_path.open('w') as stream:
        subprocess.run(
            ['graphify', 'cluster-only', str(root), '--no-viz', '--no-label', '--graph', str(graph_path)],
            cwd=root, stdout=stream, stderr=subprocess.STDOUT, check=True,
        )
    diagnostic = json.loads(subprocess.check_output(
        ['graphify', 'diagnose', 'multigraph', '--graph', str(graph_path), '--json'],
        cwd=root, text=True,
    ))
    summary = diagnostic['summary']
    zero_counts = {key: summary.get(key) for key in DIAGNOSTIC_ZERO_KEYS}
    require(all(value == 0 for value in zero_counts.values()),
            f'{label} Graphify diagnostic reported nonzero integrity counts: {zero_counts}')
    (output / f'{label.lower().replace("-", "_")}_diagnose.json').write_text(
        json.dumps(diagnostic, indent=2, sort_keys=True) + '\n')
    graph = json.loads(graph_path.read_text())
    return {'stats': graph_stats(graph), 'integrity_zero_counts': zero_counts}


def update_report(root: Path, source_commit: str, selected: list[dict], limits: str) -> None:
    report = root / 'graphify-out/GRAPH_REPORT.md'
    content = report.read_text()
    selected_text = ', '.join(f'`{item["path"]}`' for item in selected)
    section = (
        '## Graph Freshness\n\n'
        f'- Source base `{source_commit}`; CP02 WRF first-call; selected Python paths: {selected_text}.\n'
        f'- {limits}\n'
    )
    pattern = r'(?m)^## Graph Freshness[ \t]*\n.*?(?=^## |\Z)'
    if re.search(pattern, content, flags=re.S):
        content = re.sub(pattern, lambda _: section, content, count=1, flags=re.S)
    else:
        content = content.rstrip() + '\n\n' + section
    report.write_text(content)


def write_wiki(stage_root: Path, stage_maint: Path, output: Path,
               lock: dict, records: dict, source_commit: str) -> str:
    wiki = output / 'wiki'
    wiki.mkdir()
    for name in WIKI_FILES:
        shutil.copy2(MAINTAINED / 'wiki' / name, wiki / name)

    limits = (
        'Only the two frozen Python paths are structurally extracted. Evidence plots, extraction scripts, '
        'the report, and other changed files are SHA-256-bound only. This structural graph does not '
        'validate runtime behavior, physical assumptions, or scientific approval. Fortran cross-file '
        'CALL extraction is partial; graph freshness does not establish runtime or scientific validation.'
    )
    for label, root in (('KLAPS50', stage_root), ('Cloud-BAL', stage_maint)):
        update_report(root, source_commit, lock['selected_source_sha256_items'], limits)
        record = records[label]
        record['report_sha256'] = sha256(root / 'graphify-out/GRAPH_REPORT.md')
        record['graph_sha256'] = sha256(root / 'graphify-out/graph.json')
        record['manifest_sha256'] = sha256(root / 'graphify-out/manifest.json')
        report_mirror = 'graph-report-klaps50.md' if label == 'KLAPS50' else 'graph-report-cloud-bal.md'
        shutil.copy2(root / 'graphify-out/GRAPH_REPORT.md', wiki / report_mirror)
        snapshot = root / 'graphify-out' / lock['snapshot']
        snapshot.mkdir()
        for name in GRAPH_FILES:
            shutil.copy2(root / 'graphify-out' / name, snapshot / name)
        record['snapshot_file_hashes'] = {name: sha256(snapshot / name) for name in GRAPH_FILES}

    index = wiki / 'graph-report.md'
    lines = index.read_text().splitlines()
    seen = set()
    for i, line in enumerate(lines):
        for label, directory, mirror in (
            ('KLAPS50', '.', 'graph-report-klaps50'),
            ('Cloud-BAL', 'Cloud-BAL/', 'graph-report-cloud-bal'),
        ):
            if line.startswith(f'| {label} |'):
                record = records[label]
                stat = record['stats']
                lines[i] = (f'| {label} | `{directory}` | {lock["snapshot"]} (CP02 WRF first-call) | '
                            f'{stat["nodes"]} | {stat["edges"]} | {stat["communities"]} | [[{mirror}]] |')
                seen.add(label)
    require(seen == {'KLAPS50', 'Cloud-BAL'}, 'wiki graph index does not contain both maintained corpora')
    index.write_text('\n'.join(lines) + '\n')

    page = wiki / 'index.md'
    content = page.read_text()
    start = content.find('## Graph snapshot')
    require(start >= 0, 'wiki index has no Graph snapshot section')
    end = content.find('\n## ', start + 3)
    if end < 0:
        end = len(content)
    section = '## Graph snapshot\n\n' + '\n'.join(
        f'- {label}: {lock["snapshot"]}; {records[label]["stats"]["nodes"]} nodes / '
        f'{records[label]["stats"]["edges"]} edges / {records[label]["stats"]["communities"]} communities.'
        for label in ('KLAPS50', 'Cloud-BAL')
    ) + '\n- Separate corpus reports retain extraction limits; graph freshness is not scientific validation.\n'
    content = content[:start] + section + content[end:]
    content, count = re.subn(r'(?m)^(date_modified:\s*)[^\r\n]+',
                             lambda match: match.group(1) + lock['snapshot'][:10], content, count=1)
    require(count == 1, 'wiki index date_modified is missing or ambiguous')
    page.write_text(content)

    with (wiki / 'log.md').open('a') as stream:
        stream.write(f'\n## [{lock["snapshot"][:10]}] kg-update | CP02 WRF first-call\n')
        stream.write(f'- Source base `{source_commit}`; mode: selected Python AST extraction and staged merge.\n')
        for label in ('KLAPS50', 'Cloud-BAL'):
            record = records[label]
            stat = record['stats']
            before = record['before']
            stream.write(
                f'- {label}: {lock["snapshot"]}; {stat["nodes"]} nodes / {stat["edges"]} edges / '
                f'{stat["communities"]} communities; delta nodes={stat["nodes"] - before["nodes"]}, '
                f'edges={stat["edges"] - before["edges"]}.\n'
            )
        stream.write(f'- {limits}\n')
    return limits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--lock', type=Path, default=SOURCE / 'docs/evidence/cp02_wrf_first_call_20261029/kg/selection_lock.json')
    parser.add_argument('--out', type=Path, default=Path('/var/tmp/cp02_wrf_first_call_kg_20261029'))
    args = parser.parse_args()
    require(subprocess.check_output(['graphify', '--version'], text=True).strip() == 'graphify 0.9.53',
            'the staged update requires pinned Graphify 0.9.53')
    baseline = json.loads(BASELINE.read_text())
    verify_maintained_baseline(baseline)
    require(not subprocess.check_output(['git', '-C', str(SOURCE), 'diff', '--name-only', 'HEAD', '--', 'graphify-out'], text=True).strip(),
            'unintended full-worktree Graphify refresh must be restored to HEAD before selective staging')
    lock = load_frozen_selection(args.lock)
    lock['selected_source_sha256_items'] = [
        {'path': path, 'sha256': lock['selected_source_sha256'][path]}
        for path in sorted(EXPECTED_PATHS)
    ]
    snapshot = lock.get('snapshot')
    require(isinstance(snapshot, str) and snapshot.startswith('2026-10-29-cp02-wrf-first-call'),
            'frozen lock snapshot must use the CP02 WRF-first-call dated name')
    run = args.out.resolve() / f'stage-{lock["freeze_id"]}'
    require(not run.exists(), f'refuse to overwrite existing stage output: {run}')
    run.mkdir(parents=True)
    stage_roots = {'KLAPS50': run / 'KLAPS50', 'Cloud-BAL': run / 'Cloud-BAL'}
    for label, maintained in (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')):
        (stage_roots[label] / 'graphify-out').parent.mkdir(parents=True)
        copy_graph_layer(maintained / 'graphify-out', stage_roots[label] / 'graphify-out')

    records = {}
    selected_items = lock['selected_source_sha256_items']
    for label, prefix in (('KLAPS50', 'Cloud-BAL'), ('Cloud-BAL', '')):
        records[label] = extract_selected(label, stage_roots[label], prefix, selected_items, run)
    for label in ('KLAPS50', 'Cloud-BAL'):
        result = cluster_and_diagnose(label, stage_roots[label], run)
        records[label].update(result)
    limits = write_wiki(stage_roots['KLAPS50'], stage_roots['Cloud-BAL'], run,
                        lock, records, lock['source_commit'])

    # Recheck source selection and maintained roots after the isolated build.
    for path, expected in lock['selected_source_sha256'].items():
        require(sha256(SOURCE / path) == expected, f'frozen source changed during staging: {path}')
    verify_maintained_baseline(baseline)
    for label, root in stage_roots.items():
        graph = json.loads((root / 'graphify-out/graph.json').read_text())
        record = records[label]
        record['snapshot'] = lock['snapshot']
        record['snapshot_file_hashes'] = {
            name: sha256(root / 'graphify-out' / lock['snapshot'] / name)
            for name in GRAPH_FILES
        }
        require(graph_stats(graph) == record['stats'], f'{label} staged graph stats differ from receipt')

    receipt = {
        'schema': 'cp02_wrf_first_call_kg_stage_v1',
        'status': 'STAGED_ONLY_NO_MAINTAINED_WRITES',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'graphify_version': 'graphify 0.9.53',
        'source_root': str(SOURCE),
        'source_commit': lock['source_commit'],
        'freeze_id': lock['freeze_id'],
        'baseline_sha256': sha256(BASELINE),
        'selection_lock_sha256': sha256(args.lock),
        'selected_source_sha256': lock['selected_source_sha256'],
        'hash_only_sha256': lock.get('hash_only_sha256', {}),
        'snapshot': lock['snapshot'],
        'preserved_baseline_snapshot_count': baseline['dated_snapshot_count_total'],
        'maintained_roots_verified_unchanged': True,
        'corpora': records,
        'staged_wiki_sha256': {
            name: sha256(run / 'wiki' / name)
            for name in WIKI_FILES
        },
        'extraction_limits': limits,
        'staging_directory': str(run),
    }
    receipt['stage_sha256'] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    receipt_path = SOURCE / 'docs/evidence/cp02_wrf_first_call_20261029/kg/stage_receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': receipt['status'], 'stage': str(run),
                      'receipt': str(receipt_path), 'corpora': records}, indent=2))


if __name__ == '__main__':
    main()
