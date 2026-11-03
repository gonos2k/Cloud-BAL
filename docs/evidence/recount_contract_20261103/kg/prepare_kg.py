#!/usr/bin/env python3
"""Freeze and stage the recount-contract graph update; never publish it."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[4]
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
EVIDENCE = SOURCE / 'docs/evidence/recount_contract_20261103'
KG = EVIDENCE / 'kg'
BASELINE = KG / 'baseline.json'
SELECTION = KG / 'selection_lock.json'
STAGE_RECEIPT = KG / 'stage_receipt.json'
SNAPSHOT = '2026-11-03-recount-contract'
STAGING = Path('/var/tmp/cloudbal_recount_contract_kg_20261103')
GRAPHIFY_HELPER = SOURCE / 'docs/evidence/snow_sensitivity_20261030/kg/stage_kg.py'
GRAPHIFY_CLI = Path(sys.executable).absolute().parent / 'graphify'
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md',
              'graph-report-cloud-bal.md', 'index.md', 'log.md')
REQUIRED_PATHS = {
    'tools/recount_cp02_weak_strong_balance.py',
    'tests/test_recount_cp02_weak_strong_balance.py',
    'docs/evidence/recount_contract_20261103/kg/prepare_kg.py',
}
EXTRA_HASH_ONLY_PATHS = {
    'README.md',
    'docs/CURRENT_RESEARCH_STATUS.md',
}
EXCLUDED_HASH_ONLY_PATHS = {'validation.json', 'review/final_team_review.json'}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def hash_only_paths() -> set[str]:
    paths = set(EXTRA_HASH_ONLY_PATHS)
    for path in EVIDENCE.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(EVIDENCE).as_posix()
        if relative.startswith('kg/') or relative in EXCLUDED_HASH_ONLY_PATHS:
            continue
        require(path.suffix != '.py',
                f'new Python source must be added to the extraction scope: {relative}')
        paths.add(path.relative_to(SOURCE).as_posix())
    return paths


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
    require(baseline['dated_snapshot_count_total'] == 230,
            'expected the read-only 230-snapshot baseline')
    expected_counts = {'KLAPS50': 113, 'Cloud-BAL': 117}
    for label, root in (('KLAPS50', MAINTAINED),
                        ('Cloud-BAL', MAINTAINED / 'Cloud-BAL')):
        record = baseline['maintained_roots'][label]
        require(len(record['dated_snapshots']) == expected_counts[label],
                f'{label} baseline snapshot count changed')
        for name, key in (('graph.json', 'graph_sha256'),
                          ('GRAPH_REPORT.md', 'graph_report_sha256'),
                          ('manifest.json', 'manifest_sha256')):
            require(sha256(root / 'graphify-out' / name) == record[key],
                    f'{label} active {name} changed since baseline')
        require(snapshot_inventory(root) == record['dated_snapshots'],
                f'{label} dated snapshots changed since baseline')
        status = subprocess.check_output(
            ['git', '-C', str(root), 'status', '--short'], text=True)
        require(status.splitlines() == record['git_status_exact'],
                f'{label} exact dirty state changed since baseline')
        require(hashlib.sha256(status.encode()).hexdigest() ==
                record['git_status_raw_sha256'],
                f'{label} dirty-state bytes changed since baseline')
    wiki = MAINTAINED / 'wiki'
    require({name: sha256(wiki / name) for name in WIKI_FILES} ==
            baseline['wiki_hashes'], 'one or more maintained wiki mirrors changed')


def load_stage_helper():
    spec = importlib.util.spec_from_file_location('recount_contract_graphify_stage',
                                                  GRAPHIFY_HELPER)
    require(spec is not None and spec.loader is not None,
            f'cannot load the reviewed Graphify stage helper: {GRAPHIFY_HELPER}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SOURCE = SOURCE
    module.MAINTAINED = MAINTAINED
    module.SNAPSHOT = SNAPSHOT
    return module


def refresh_staged_report(stage_root: Path, extracted_paths: set[str]) -> None:
    subprocess.run(
        [str(GRAPHIFY_CLI), 'cluster-only', str(stage_root), '--no-viz', '--no-label',
         '--graph', str(stage_root / 'graphify-out/graph.json')],
        cwd=stage_root, check=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    report = stage_root / 'graphify-out/GRAPH_REPORT.md'
    with report.open('a') as stream:
        stream.write(f'\n## {SNAPSHOT} scoped update\n')
        stream.write(f'- Only {len(extracted_paths)} frozen Python source paths are structurally extracted.\n')
        stream.write('- Manifest updates are selected-path-only; no corpus scan or prune occurs.\n')
        stream.write('- Final non-code evidence is hash-bound only; no document content is extracted.\n')
        stream.write('- Fortran cross-file call extraction is partial.\n')
        stream.write('- Graph freshness does not establish runtime or scientific validation.\n')


def write_staged_wiki(run: Path, records: dict, lock: dict) -> dict:
    wiki = run / 'wiki'
    wiki.mkdir()
    for name in WIKI_FILES:
        (wiki / name).write_bytes((MAINTAINED / 'wiki' / name).read_bytes())
    for label, name in (('KLAPS50', 'graph-report-klaps50.md'),
                        ('Cloud-BAL', 'graph-report-cloud-bal.md')):
        source = run / label / 'graphify-out/GRAPH_REPORT.md'
        (wiki / name).write_bytes(source.read_bytes())

    report_index = wiki / 'graph-report.md'
    lines = report_index.read_text().splitlines()
    seen = set()
    for index, line in enumerate(lines):
        for label, directory, mirror in (
            ('KLAPS50', '.', 'graph-report-klaps50'),
            ('Cloud-BAL', 'Cloud-BAL/', 'graph-report-cloud-bal'),
        ):
            if line.startswith(f'| {label} |'):
                stats = records[label]['after']
                lines[index] = (
                    f'| {label} | `{directory}` | {SNAPSHOT} (recount contract) | '
                    f'{stats["nodes"]} | {stats["edges"]} | {stats["communities"]} | [[{mirror}]] |')
                seen.add(label)
    require(seen == {'KLAPS50', 'Cloud-BAL'},
            'wiki graph-report index lacks a maintained corpus row')
    report_index.write_text('\n'.join(lines) + '\n')

    index = wiki / 'index.md'
    content = index.read_text()
    start = content.find('## Graph snapshot')
    require(start >= 0, 'wiki index has no Graph snapshot section')
    end = content.find('\n## ', start + 3)
    if end < 0:
        end = len(content)
    section = '## Graph snapshot\n\n' + '\n'.join(
        f'- {label}: {SNAPSHOT}; {records[label]["after"]["nodes"]} nodes / '
        f'{records[label]["after"]["edges"]} edges / '
        f'{records[label]["after"]["communities"]} communities.'
        for label in ('KLAPS50', 'Cloud-BAL'))
    section += f'\n- Only {len(REQUIRED_PATHS)} frozen Python files are extracted; other new evidence is hash-bound only.\n'
    section += '- Graph freshness does not establish runtime or scientific validation.\n'
    content = content[:start] + section + content[end:]
    import re
    content, count = re.subn(r'(?m)^(date_modified:\s*)[^\r\n]+',
                             lambda match: match.group(1) + SNAPSHOT[:10],
                             content, count=1)
    require(count == 1, 'wiki index date_modified is missing or ambiguous')
    index.write_text(content)

    with (wiki / 'log.md').open('a') as stream:
        stream.write(f'\n## [{SNAPSHOT[:10]}] kg-update | recount contract\n')
        stream.write(f'- Source base `{lock["source_commit"]}`; selected Python AST extraction.\n')
        for label in ('KLAPS50', 'Cloud-BAL'):
            before, after = records[label]['before'], records[label]['after']
            stream.write(f'- {label}: {SNAPSHOT}; {after["nodes"]} nodes / '
                         f'{after["edges"]} edges / {after["communities"]} communities; '
                         f'delta nodes={after["nodes"] - before["nodes"]}, '
                         f'edges={after["edges"] - before["edges"]}.\n')
        stream.write(f'- {len(REQUIRED_PATHS)} Python files extracted; manifest update selected-path-only.\n')
        stream.write(f'- Validation: {lock["validation_summary"]}\n')
        stream.write(f'- Open items: {lock["open_items"]}\n')
        stream.write('- Fortran cross-file extraction is partial; graph freshness is not runtime or scientific validation.\n')
    return {name: sha256(wiki / name) for name in WIKI_FILES}


def freeze(review_path: Path) -> dict:
    require(not SELECTION.exists(), 'preserve an existing selection lock')
    review = json.loads(review_path.read_text())
    require(review.get('status') == 'PASS_SOURCE_AND_EVIDENCE_REVIEW',
            'independent source/evidence review must pass before freeze')
    selected = {}
    for relative in sorted(REQUIRED_PATHS):
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(),
                f'missing or unsafe selected Python source: {relative}')
        selected[relative] = sha256(path)
    require(review.get('source_hashes', {}).get('tools/recount_cp02_weak_strong_balance.py') ==
            selected['tools/recount_cp02_weak_strong_balance.py'],
            'review does not bind the current recount source')
    require(review.get('source_hashes', {}).get('tests/test_recount_cp02_weak_strong_balance.py') ==
            selected['tests/test_recount_cp02_weak_strong_balance.py'],
            'review does not bind the current recount test')
    require(review.get('source_hashes', {}).get(
        'docs/evidence/recount_contract_20261103/kg/prepare_kg.py') ==
            selected['docs/evidence/recount_contract_20261103/kg/prepare_kg.py'],
            'review does not bind the current KG staging helper')
    hash_only = {}
    for relative in sorted(hash_only_paths()):
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(),
                f'missing or unsafe hash-only evidence: {relative}')
        hash_only[relative] = sha256(path)
    status_receipt = json.loads((EVIDENCE / 'status/source_hashes.json').read_text())
    require(all(sha256(SOURCE / item['path']) == item['sha256']
                for item in status_receipt['source_files']),
            'status source hash receipt is stale')
    baseline = json.loads(BASELINE.read_text())
    verify_baseline(baseline)
    commit = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'],
                                     text=True).strip()
    freeze_id = hashlib.sha256(json.dumps(
        {'source_commit': commit, 'selected': selected, 'hash_only': hash_only},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]
    lock = {
        'status': 'FROZEN', 'review_status': 'GO', 'freeze_id': freeze_id,
        'snapshot': SNAPSHOT, 'source_commit': commit,
        'selected_source_sha256': selected, 'hash_only_sha256': hash_only,
        'review_sha256': sha256(review_path), 'baseline_sha256': sha256(BASELINE),
        'validation_summary': 'Six focused recount tests pass; independent review and source/evidence hash checks pass.',
        'open_items': 'No rain-number writer or initializer is validated; C2 producer stencil, RN1 coverage, independent cases, and full water/energy budgets remain open.',
        'maintained_roots_written': False,
        'consolidated_validation_note': 'Root creates validation.json after KG readback to avoid a self-hash cycle; it is not part of this prepublication lock.',
    }
    SELECTION.write_text(json.dumps(lock, indent=2, sort_keys=True) + '\n')
    return lock


def stage(lock_path: Path) -> dict:
    import graphify
    require(str(Path(graphify.__file__).resolve()).startswith(
        '/var/tmp/snow-image-cdn-graphify-venv/'),
        'use the pinned /var/tmp/snow-image-cdn-graphify-venv interpreter')
    require(GRAPHIFY_CLI.is_file(), 'the pinned Graphify CLI is missing from the venv')
    require(subprocess.check_output([str(GRAPHIFY_CLI), '--version'], text=True).strip() ==
            'graphify 0.9.53', 'Graphify must remain pinned at 0.9.53')
    lock = json.loads(lock_path.read_text())
    require(lock.get('status') == 'FROZEN' and lock.get('review_status') == 'GO',
            'selection lock is not frozen and reviewed')
    require(lock.get('snapshot') == SNAPSHOT and lock.get('freeze_id'),
            'selection lock snapshot identity is incorrect')
    require(lock.get('baseline_sha256') == sha256(BASELINE),
            'maintained-root baseline changed after freeze')
    require(lock.get('review_sha256') ==
            sha256(EVIDENCE / 'review/independent_review.json'),
            'independent source/evidence review changed after freeze')
    require(set(lock.get('selected_source_sha256', {})) == REQUIRED_PATHS,
            'selected Python source paths differ from the exact reviewed scope')
    require(set(lock.get('hash_only_sha256', {})) == hash_only_paths(),
            'hash-only evidence paths differ from the exact reviewed scope')
    require(lock.get('source_commit') == subprocess.check_output(
        ['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
        'source commit changed after freeze')
    for relative, expected in lock['selected_source_sha256'].items():
        require(sha256(SOURCE / relative) == expected,
                f'selected source hash changed: {relative}')
    for relative, expected in lock['hash_only_sha256'].items():
        require(sha256(SOURCE / relative) == expected,
                f'hash-only evidence changed: {relative}')
    baseline = json.loads(BASELINE.read_text())
    verify_baseline(baseline)
    module = load_stage_helper()
    module.refresh_staged_report = refresh_staged_report
    module.write_staged_wiki = write_staged_wiki
    result = module.stage_selected(lock, REQUIRED_PATHS, REQUIRED_PATHS, STAGING)
    for relative, expected in lock['selected_source_sha256'].items():
        require(sha256(SOURCE / relative) == expected,
                f'selected source changed during stage: {relative}')
    for relative, expected in lock['hash_only_sha256'].items():
        require(sha256(SOURCE / relative) == expected,
                f'hash-only evidence changed during stage: {relative}')
    verify_baseline(baseline)
    result.update({
        'status': 'STAGED_ONLY_NO_MAINTAINED_WRITES',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'snapshot': SNAPSHOT,
        'baseline_sha256': sha256(BASELINE),
        'selection_lock_sha256': sha256(lock_path),
        'dated_snapshots_preserved': 230,
        'source_extraction_scope': sorted(REQUIRED_PATHS),
        'manifest_update_scope': sorted(REQUIRED_PATHS),
        'hash_only_sha256': lock['hash_only_sha256'],
        'extraction_limits': [
            'Only the two recount source/test files and this scoped KG helper are structurally extracted.',
            'Other new evidence is hash-bound only; no document content is extracted.',
            'Manifest updates are selected-path-only; no corpus scan or prune occurs.',
            'Fortran cross-file CALL extraction is partial.',
            'Graph freshness does not establish runtime behavior, physical assumptions, or scientific approval.',
        ],
        'maintained_roots_written': False,
    })
    STAGE_RECEIPT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'stage'))
    parser.add_argument('--review', type=Path, default=EVIDENCE / 'review/independent_review.json')
    parser.add_argument('--lock', type=Path, default=SELECTION)
    parser.add_argument('--stage', action='store_true',
                        help='required explicit confirmation for isolated stage generation')
    args = parser.parse_args()
    baseline = json.loads(BASELINE.read_text())
    verify_baseline(baseline)
    if args.action == 'freeze':
        result = freeze(args.review)
    else:
        require(args.stage, 'staging is disabled without explicit --stage')
        result = stage(args.lock)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
