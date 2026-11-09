#!/usr/bin/env python3
"""Freeze reviewed B1 first-ice-velocity KG inputs and build an isolated stage only."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[4]
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
EVIDENCE = SOURCE / 'docs/evidence/cp02_first_ice_velocity_20261109'
KG = EVIDENCE / 'kg'
BASELINE = KG / 'baseline.json'
SELECTION = KG / 'selection_lock.json'
STAGE_RECEIPT = KG / 'stage_receipt.json'
REVIEW = EVIDENCE / 'review/independent_kg_review.json'
SNAPSHOT = '2026-11-09-first-ice-velocity'
STAGING = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_ice_velocity_20261109/kg_stage')
GRAPHIFY_HOME = Path('/var/tmp/snow-image-cdn-graphify-venv')
GRAPHIFY_CLI = GRAPHIFY_HOME / 'bin/graphify'
STAGE_HELPER = SOURCE / 'docs/evidence/first_hour_zero_rate_20261030/kg/stage_kg.py'
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md',
              'graph-report-cloud-bal.md', 'index.md', 'log.md')
EXPECTED_SNAPSHOT_COUNTS = {'KLAPS50': 124, 'Cloud-BAL': 128}
EXPECTED_SOURCE_PATHS = {'tests/test_cp02_first_ice_velocity.py'}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def git_state(root: Path) -> dict:
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    status = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain=v1', '-z'])
    return {'head': head, 'status_sha256': hashlib.sha256(status).hexdigest(),
            'status_porcelain_v1_z_base64': base64.b64encode(status).decode(),
            'status_entry_count': max(0, len(status.split(b'\0')) - 1)}


def snapshot_inventory(root: Path) -> dict:
    inventory = {}
    graph_root = root / 'graphify-out'
    for folder in sorted(graph_root.iterdir()):
        if folder.is_dir() and folder.name[:4].isdigit():
            inventory[folder.name] = {
                path.relative_to(folder).as_posix(): sha256(path)
                for path in sorted(folder.rglob('*')) if path.is_file() and not path.is_symlink()
                and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.lock')
            }
    return inventory


def current_wiki_hashes() -> dict:
    wiki = MAINTAINED / 'wiki'
    return {name: sha256(wiki / name) for name in WIKI_FILES}


def verify_baseline() -> dict:
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    require(baseline['planned_snapshot_label'] == SNAPSHOT, 'baseline snapshot label differs')
    require(baseline['maintained_roots_written'] is False, 'baseline was not read-only')
    roots = {'KLAPS50': MAINTAINED, 'Cloud-BAL': MAINTAINED / 'Cloud-BAL'}
    for label, root in roots.items():
        record = baseline['maintained_roots'][label]
        require(record['dated_snapshot_count'] == EXPECTED_SNAPSHOT_COUNTS[label],
                f'{label} snapshot count differs from the captured 124/128 inventory')
        require(snapshot_inventory(root) == record['dated_snapshots'],
                f'{label} dated snapshot files changed since baseline')
        require(git_state(root) == record['git_state'],
                f'{label} maintained-root HEAD or dirty state changed since baseline')
        active = {name: sha256(root / 'graphify-out' / name) for name in
                  ('GRAPH_REPORT.md', 'graph.json', 'manifest.json')}
        require(active == record['active_graph_trio_sha256'],
                f'{label} active graph trio changed since baseline')
    require(sum(EXPECTED_SNAPSHOT_COUNTS.values()) == baseline['dated_snapshot_count_total'],
            'baseline count does not equal 252')
    require(current_wiki_hashes() == baseline['wiki_mirror_sha256'],
            'one or more maintained wiki mirrors changed since baseline')
    require(sha256(MAINTAINED / 'AGENTS.md') == baseline['agents_sha256'],
            'maintained AGENTS.md content changed since baseline')
    source_record = baseline['source_worktree']
    require({name: sha256(SOURCE / 'graphify-out' / name) for name in GRAPH_FILES}
            == source_record['active_graph_trio_sha256'],
            'source worktree active graph trio changed since baseline')
    require(subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'],
                                   text=True).strip() == source_record['head'],
            'source worktree HEAD changed since baseline')
    return baseline


def load_review(path: Path) -> tuple[dict, set[str]]:
    require(path.is_file() and not path.is_symlink(), f'independent review missing or unsafe: {path}')
    review = json.loads(path.read_text(encoding='utf-8'))
    require(review.get('status') == 'PASS_SOURCE_AND_EVIDENCE_REVIEW',
            'independent source/evidence review must pass before freezing')
    paths = review.get('selected_source_paths', [])
    selected = set(paths)
    require(paths and len(paths) == len(selected), 'review must select unique source paths')
    require(selected == EXPECTED_SOURCE_PATHS, 'review must select exactly the maintained source/test paths')
    require(all(path.endswith('.py') for path in selected), 'all selected AST paths must be Python files')
    hashes = review.get('selected_source_sha256', {})
    require(set(hashes) == selected, 'review source hashes must bind exactly the selected paths')
    for relative, expected in hashes.items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, f'unsafe path: {relative}')
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(), f'missing or unsafe selected source: {relative}')
        require(sha256(path) == expected, f'review source hash mismatch: {relative}')
    require(review.get('validation_summary') and 'science_open_items' in review,
            'review must record validation summary and actual scientific open items')
    hash_only = review.get('hash_only_sha256', {})
    require(isinstance(hash_only, dict), 'review hash_only_sha256 must be a path-to-hash map')
    dependency = STAGE_HELPER.relative_to(SOURCE).as_posix()
    require(hash_only.get(dependency) == sha256(STAGE_HELPER),
            'review must pin the reused Graphify stage dependency')
    for relative, expected in hash_only.items():
        require('__pycache__' not in Path(relative).parts and Path(relative).suffix not in ('.pyc', '.lock'),
                f'transient file cannot be a frozen evidence pin: {relative}')
        require(relative not in selected, f'path is both extracted and hash-only: {relative}')
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, f'unsafe path: {relative}')
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(), f'missing or unsafe hash-only file: {relative}')
        require(sha256(path) == expected, f'review hash-only hash mismatch: {relative}')
    return review, selected


def validate_lock_review(lock: dict, review: dict) -> None:
    require(set(lock.get('selected_source_sha256', {})) == EXPECTED_SOURCE_PATHS,
            'frozen lock differs from the maintained corpus')
    for key in ('selected_source_sha256', 'hash_only_sha256'):
        require(lock.get(key) == review.get(key), f'frozen {key} differs from the independent review')


def freeze(review_path: Path) -> dict:
    require(not SELECTION.exists() and not SELECTION.is_symlink(), 'preserve an existing selection lock')
    baseline = verify_baseline()
    review, selected = load_review(review_path)
    selected_hashes = {path: sha256(SOURCE / path) for path in sorted(selected)}
    hash_only = review['hash_only_sha256']
    commit = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    freeze_id = hashlib.sha256(json.dumps(
        {'source_commit': commit, 'selected': selected_hashes, 'hash_only': hash_only},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]
    lock = {
        'status': 'FROZEN', 'review_status': 'GO', 'freeze_id': freeze_id,
        'snapshot': SNAPSHOT, 'source_commit': commit,
        'selected_source_sha256': selected_hashes,
        'hash_only_sha256': hash_only,
        'review_sha256': sha256(review_path), 'baseline_sha256': sha256(BASELINE),
        'validation_summary': review['validation_summary'],
        'open_items': review['science_open_items'],
        'maintained_roots_written': False,
        'extraction_limits': [
            'Only the reviewed Python paths are structurally extracted.',
            'Remaining new evidence is hash-only; native source and runtime evidence is not semantically extracted.',
            'Manifest changes are selected-path-only; no corpus scan or prune occurs.',
            'Edges to absent external import targets can be dropped during normal graph merge; raw extraction is retained for review.',
            'Fortran cross-file CALL extraction is partial.',
            'Graph freshness does not establish runtime behavior, physical correctness, conservation, or scientific validation.',
        ],
    }
    require(baseline['source_worktree']['head'] == commit,
            'source HEAD changed during freeze')
    with SELECTION.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(lock, indent=2, sort_keys=True) + '\n')
    return lock


def load_stage_helper():
    spec = importlib.util.spec_from_file_location('first_ice_velocity_graphify_stage', STAGE_HELPER)
    require(spec is not None and spec.loader is not None, f'cannot load stage helper: {STAGE_HELPER}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SOURCE = SOURCE
    module.MAINTAINED = MAINTAINED
    module.SNAPSHOT = SNAPSHOT
    return module


def refresh_staged_report(stage_root: Path, extracted_paths: set[str]) -> None:
    env = os.environ.copy()
    env['PATH'] = f'{GRAPHIFY_HOME / "bin"}:{env.get("PATH", "")}'
    subprocess.run(
        [str(GRAPHIFY_CLI), 'cluster-only', str(stage_root), '--no-viz', '--no-label',
         '--graph', str(stage_root / 'graphify-out/graph.json')],
        cwd=stage_root, env=env, check=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    report = stage_root / 'graphify-out/GRAPH_REPORT.md'
    require(report.is_file(), f'scoped graph report missing: {report}')
    with report.open('a', encoding='utf-8') as stream:
        stream.write(f'\n## {SNAPSHOT} scoped update\n')
        stream.write(f'- Only {len(extracted_paths)} frozen Python sources are structurally extracted.\n')
        stream.write('- Other new evidence is hash-only; no document semantic extraction was performed.\n')
        stream.write('- Manifest updates are selected-path-only; no corpus scan or prune occurs.\n')
        stream.write('- External import edges can be dropped when their target nodes are absent; see raw extraction and review.\n')
        stream.write('- Fortran cross-file CALL extraction is partial; graph freshness is not runtime/scientific validation.\n')


def write_staged_wiki(run: Path, records: dict, lock: dict) -> dict:
    stage_helper = load_stage_helper()
    wiki = run / 'wiki'
    wiki.mkdir()
    for name in WIKI_FILES:
        source = MAINTAINED / 'wiki' / name
        require(source.is_file() and not source.is_symlink(), f'missing wiki mirror: {source}')
        import shutil
        shutil.copy2(source, wiki / name)
    import shutil
    shutil.copy2(run / 'KLAPS50/graphify-out/GRAPH_REPORT.md', wiki / 'graph-report-klaps50.md')
    shutil.copy2(run / 'Cloud-BAL/graphify-out/GRAPH_REPORT.md', wiki / 'graph-report-cloud-bal.md')

    index_path = wiki / 'graph-report.md'
    lines = index_path.read_text(encoding='utf-8').splitlines()
    seen = set()
    for i, line in enumerate(lines):
        for label, directory, mirror in (
            ('KLAPS50', '.', 'graph-report-klaps50'),
            ('Cloud-BAL', 'Cloud-BAL/', 'graph-report-cloud-bal'),
        ):
            if line.startswith(f'| {label} |'):
                stats = records[label]['after']
                lines[i] = (f'| {label} | `{directory}` | {SNAPSHOT} (B1 first-ice-velocity) | '
                            f'{stats["nodes"]} | {stats["edges"]} | {stats["communities"]} | [[{mirror}]] |')
                seen.add(label)
    require(seen == {'KLAPS50', 'Cloud-BAL'}, 'wiki graph-report index must have exactly both corpus rows')
    index_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    page = wiki / 'index.md'
    content = page.read_text(encoding='utf-8')
    start = content.find('## Graph snapshot')
    require(start >= 0, 'wiki index has no Graph snapshot section')
    end = content.find('\n## ', start + 3)
    if end < 0:
        end = len(content)
    section = '## Graph snapshot\n\n' + '\n'.join(
        f'- [[graph-report-{slug}]] — {label}: {SNAPSHOT}; {records[label]["after"]["nodes"]} nodes / '
        f'{records[label]["after"]["edges"]} edges / {records[label]["after"]["communities"]} communities.'
        for label, slug in (('KLAPS50', 'klaps50'), ('Cloud-BAL', 'cloud-bal')))
    section += f'\n- {len(lock["selected_source_sha256"])} reviewed Python paths are extracted; remaining new evidence is hash-only.\n'
    section += '- Graph freshness does not establish runtime or scientific validation.\n'
    content = content[:start] + section + content[end:]
    content, changed = re.subn(r'(?m)^(date_modified:\s*)[^\r\n]+',
                               lambda match: match.group(1) + SNAPSHOT[:10], content, count=1)
    require(changed == 1, 'wiki index frontmatter date_modified is missing or ambiguous')
    page.write_text(content, encoding='utf-8')

    with (wiki / 'log.md').open('a', encoding='utf-8') as stream:
        stream.write(f'\n## [{SNAPSHOT[:10]}] kg-update | B1 first-ice-velocity\n')
        stream.write(f'- Source base `{lock["source_commit"]}`; mode: reviewed selected Python AST extraction in isolated stage.\n')
        for label in ('KLAPS50', 'Cloud-BAL'):
            record = records[label]
            before, after = record['before'], record['after']
            stream.write(f'- {label}: {SNAPSHOT}; {after["nodes"]} nodes / {after["edges"]} edges / '
                         f'{after["communities"]} communities; delta nodes={after["nodes"] - before["nodes"]}, '
                         f'edges={after["edges"] - before["edges"]}, '
                         f'communities={after["communities"] - before["communities"]}.\n')
        stream.write('- Reviewed Python paths extracted; remaining new evidence hash-only; no corpus scan/prune.\n')
        stream.write(f'- Validation: {lock["validation_summary"]}\n- Open items: {lock["open_items"]}\n')
        stream.write('- Structural extraction does not establish runtime or scientific validation.\n')
    return {name: sha256(wiki / name) for name in WIKI_FILES}


def stage(lock_path: Path) -> dict:
    require(not STAGE_RECEIPT.exists() and not STAGE_RECEIPT.is_symlink(),
            'preserve an existing stage receipt')
    import tempfile
    STAGING.mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(STAGING)
    tempfile.tempdir = str(STAGING)
    import graphify
    require(str(Path(graphify.__file__).resolve()).startswith(str(GRAPHIFY_HOME)),
            'use the pinned Graphify venv interpreter')
    require(GRAPHIFY_CLI.is_file(), f'pinned Graphify CLI missing: {GRAPHIFY_CLI}')
    require(subprocess.check_output([str(GRAPHIFY_CLI), '--version'], text=True).strip() ==
            'graphify 0.9.53', 'Graphify must be pinned at 0.9.53')
    baseline = verify_baseline()
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    review, _selected = load_review(REVIEW)
    validate_lock_review(lock, review)
    require(lock.get('status') == 'FROZEN' and lock.get('review_status') == 'GO',
            'selection lock must be frozen with independent GO review')
    require(lock.get('snapshot') == SNAPSHOT, 'selection lock snapshot differs')
    require(lock.get('baseline_sha256') == sha256(BASELINE), 'baseline changed after freeze')
    require(lock.get('review_sha256') == sha256(REVIEW), 'independent review changed after freeze')
    paths = set(lock.get('selected_source_sha256', {}))
    require(paths and all(path.endswith('.py') for path in paths),
            'selection lock must contain reviewed Python paths')
    hash_only = lock.get('hash_only_sha256', {})
    for relative, expected in {**lock['selected_source_sha256'], **hash_only}.items():
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(), f'frozen path missing/unsafe: {relative}')
        require(sha256(path) == expected, f'frozen path changed: {relative}')
    require(subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'],
                                    text=True).strip() == lock['source_commit'],
            'source commit changed after freeze')

    stage_helper = load_stage_helper()
    stage_helper.refresh_staged_report = refresh_staged_report
    stage_helper.write_staged_wiki = write_staged_wiki
    import graphify.extract as graph_extract
    original_extract = graph_extract.extract
    raw_extractions = []

    def record_raw_extraction(*args, **kwargs):
        result = original_extract(*args, **kwargs)
        raw = json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        raw_path = STAGING / ('stage-' + lock['freeze_id']) / f'raw_extraction_{len(raw_extractions) + 1}.json'
        with raw_path.open('xb') as stream:
            stream.write(raw)
        raw_extractions.append({'path': str(raw_path), 'sha256': hashlib.sha256(raw).hexdigest()})
        return result

    graph_extract.extract = record_raw_extraction
    try:
        result = stage_helper.stage_selected(lock, paths, paths, STAGING)
    finally:
        graph_extract.extract = original_extract
    result['raw_extractions'] = raw_extractions
    verify_baseline()
    for relative, expected in {**lock['selected_source_sha256'], **hash_only}.items():
        require(sha256(SOURCE / relative) == expected, f'frozen path changed during stage: {relative}')
    result.update({
        'status': 'STAGED_ONLY_NO_MAINTAINED_WRITES',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'snapshot': SNAPSHOT,
        'baseline_sha256': sha256(BASELINE),
        'selection_lock_sha256': sha256(lock_path),
        'dated_snapshots_preserved': baseline['dated_snapshot_count_total'],
        'source_extraction_scope': sorted(paths),
        'manifest_update_scope': sorted(paths),
        'hash_only_sha256': hash_only,
        'maintained_roots_written': False,
        'extraction_limits': lock['extraction_limits'],
    })
    with STAGE_RECEIPT.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def capture_baseline() -> dict:
    require(not BASELINE.exists(), 'preserve an existing baseline')
    roots = {'KLAPS50': MAINTAINED, 'Cloud-BAL': MAINTAINED / 'Cloud-BAL'}
    records = {}
    for label, root in roots.items():
        inventory = snapshot_inventory(root)
        expected = EXPECTED_SNAPSHOT_COUNTS[label]
        require(len(inventory) == expected, f'{label}: expected {expected} existing snapshots, found {len(inventory)}')
        records[label] = {
            'path': str(root), 'dated_snapshot_count': len(inventory),
            'dated_snapshots': inventory, 'git_state': git_state(root),
            'active_graph_trio_sha256': {name: sha256(root / 'graphify-out' / name) for name in GRAPH_FILES},
        }
    total = sum(EXPECTED_SNAPSHOT_COUNTS.values())
    require(total == 252, 'expected 252 preserved snapshots before first-ice-velocity')
    baseline = {
        'planned_snapshot_label': SNAPSHOT, 'captured_utc': datetime.now(timezone.utc).isoformat(),
        'maintained_roots_written': False, 'dated_snapshot_count_total': total,
        'maintained_roots': records, 'wiki_mirror_sha256': current_wiki_hashes(),
        'agents_sha256': sha256(MAINTAINED / 'AGENTS.md'),
        'source_worktree': {
            'path': str(SOURCE),
            'head': subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
            'git_state_at_capture': git_state(SOURCE),
            'active_graph_trio_sha256': {name: sha256(SOURCE / 'graphify-out' / name) for name in GRAPH_FILES},
        },
    }
    with BASELINE.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(baseline, indent=2, sort_keys=True) + '\n')
    return baseline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='action', required=True)
    subparsers.add_parser('capture-baseline')
    freeze_parser = subparsers.add_parser('freeze')
    freeze_parser.add_argument('--review', type=Path, default=REVIEW)
    stage_parser = subparsers.add_parser('stage')
    stage_parser.add_argument('--lock', type=Path, default=SELECTION)
    stage_parser.add_argument('--stage', action='store_true',
                              help='required explicit parent authorization for isolated staging')
    args = parser.parse_args()
    if args.action == 'capture-baseline':
        result = capture_baseline()
    else:
        verify_baseline()
    if args.action == 'freeze':
        result = freeze(args.review)
    elif args.action == 'stage':
        require(args.stage, 'isolated staging disabled without explicit --stage')
        result = stage(args.lock)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
