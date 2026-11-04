#!/usr/bin/env python3
"""Freeze and stage the scoped B1 state-path KG update; never publish."""
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
EVIDENCE = SOURCE / 'docs/evidence/cp02_state_path_20261104'
KG = EVIDENCE / 'kg'
BASELINE = KG / 'baseline.json'
INITIAL_CHECK = KG / 'baseline_check_initial.json'
SELECTION = KG / 'selection_lock.json'
STAGE_RECEIPT = KG / 'stage_receipt.json'
SNAPSHOT = '2026-11-04-b1-state-path'
STAGING = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_state_path_20261104/kg_stage')
GRAPHIFY_HOME = Path('/var/tmp/snow-image-cdn-graphify-venv')
GRAPHIFY_CLI = GRAPHIFY_HOME / 'bin/graphify'
GRAPHIFY_HELPER = SOURCE / 'docs/evidence/snow_sensitivity_20261030/kg/stage_kg.py'
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md',
              'graph-report-cloud-bal.md', 'index.md', 'log.md')
REQUIRED_PATHS = {
    'tools/cp02_state_path.py',
    'tests/test_cp02_state_path.py',
    'tools/cp02_state_path_cohorts.py',
    'tests/test_cp02_state_path_cohorts.py',
    'tools/plot_cp02_state_path.py',
    'tests/test_plot_cp02_state_path.py',
    'tools/plot_cp02_state_path_native.py',
    'tests/test_plot_cp02_state_path_native.py',
    'tools/plot_cp02_rain_number_evaluation.py',
    'tests/test_plot_cp02_rain_number_evaluation.py',
    'tests/test_cp02_state_path_figure_renderers.py',
    'tools/recount_cp02_weak_strong_balance.py',
    'tests/test_recount_cp02_weak_strong_balance.py',
    'tools/initialize_b1_rain_psd_prior.py',
    'tests/test_initialize_b1_rain_psd_prior.py',
    'tools/cp02_rain_number_evaluation.py',
    'tests/test_cp02_rain_number_evaluation.py',
    'docs/evidence/cp02_state_path_20261104/native/extend_state_patch.py',
    'docs/evidence/cp02_state_path_20261104/kg/prepare_kg.py',
}
EXTRA_HASH_ONLY_PATHS = {
    'docs/CP02_STATE_PATH_AND_RAIN_NUMBER_20261104.md',
    'README.md',
    'docs/CURRENT_RESEARCH_STATUS.md',
}
EXCLUDED_HASH_ONLY = {
    'kg/',
    'validation.json',
    'review/final_team_review.json',
    'review/independent_kg_review.json',
    'review/final_independent_review.json',
    'review/final_kg_manifest.json',
}


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
    return {'head': head, 'porcelain_v1_z_sha256': hashlib.sha256(status).hexdigest(),
            'porcelain_entry_count': max(0, len(status.split(b'\0')) - 1)}


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
    require(baseline['dated_snapshot_count_total'] == 234,
            'expected the preserved initial 234-snapshot baseline')
    require(baseline.get('planned_snapshot_label') == SNAPSHOT,
            'baseline snapshot label differs from the planned state-path snapshot')
    require(baseline.get('maintained_roots_written') is False,
            'baseline must be a read-only capture')
    expected_counts = {'KLAPS50': 115, 'Cloud-BAL': 119}
    roots = (('KLAPS50', MAINTAINED), ('Cloud-BAL', MAINTAINED / 'Cloud-BAL'))
    for label, root in roots:
        record = baseline['maintained_roots'][label]
        require(record['dated_snapshot_count'] == expected_counts[label],
                f'{label} baseline snapshot count changed')
        require(SNAPSHOT not in record['dated_snapshots'],
                f'{label} planned second-batch snapshot already exists in baseline')
        require(snapshot_inventory(root) == record['dated_snapshots'],
                f'{label} dated snapshot inventory changed after baseline capture')
        require(git_state(root) == record['git_state'],
                f'{label} HEAD or exact dirty-state bytes changed after baseline capture')
        graph = root / 'graphify-out'
        active = {name: sha256(graph / name) for name in
                  ('GRAPH_REPORT.md', 'graph.json', 'manifest.json')}
        require(active == record['active_graph_trio_sha256'],
                f'{label} active graph trio changed after baseline capture')
    require(sum(record['dated_snapshot_count'] for record in baseline['maintained_roots'].values()) == 234,
            'corpus snapshot counts do not sum to 234')
    wiki = MAINTAINED / 'wiki'
    require({name: sha256(wiki / name) for name in WIKI_FILES} == baseline['wiki_mirror_sha256'],
            'one or more maintained wiki mirrors changed after baseline capture')


def hash_only_paths() -> set[str]:
    paths = set(EXTRA_HASH_ONLY_PATHS)
    for path in EVIDENCE.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        relative_evidence = path.relative_to(EVIDENCE).as_posix()
        if any(relative_evidence == prefix.rstrip('/') or relative_evidence.startswith(prefix)
               for prefix in EXCLUDED_HASH_ONLY):
            continue
        relative_source = path.relative_to(SOURCE).as_posix()
        if relative_source in REQUIRED_PATHS:
            continue
        paths.add(relative_source)
    return paths


def load_stage_helper():
    spec = importlib.util.spec_from_file_location('b1_state_path_graphify_stage', GRAPHIFY_HELPER)
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
        cwd=stage_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    report = stage_root / 'graphify-out/GRAPH_REPORT.md'
    require(report.is_file(), f'scoped graph report was not generated: {report}')
    with report.open('a', encoding='utf-8') as stream:
        stream.write(f'\n## {SNAPSHOT} scoped update\n')
        stream.write(f'- Only {len(extracted_paths)} frozen Python sources are structurally extracted.\n')
        stream.write('- Other new evidence, including native source copies and compressed traces, is hash-bound only.\n')
        stream.write('- Manifest updates are selected-path-only; no corpus scan or prune occurs.\n')
        stream.write('- Fortran cross-file CALL extraction is partial.\n')
        stream.write('- Graph freshness does not establish runtime or scientific validation.\n')


def write_staged_wiki(run: Path, records: dict, lock: dict) -> dict:
    wiki = run / 'wiki'
    wiki.mkdir()
    for name in WIKI_FILES:
        (wiki / name).write_bytes((MAINTAINED / 'wiki' / name).read_bytes())
    for label, mirror in (('KLAPS50', 'graph-report-klaps50.md'),
                          ('Cloud-BAL', 'graph-report-cloud-bal.md')):
        (wiki / mirror).write_bytes((run / label / 'graphify-out/GRAPH_REPORT.md').read_bytes())

    report_index = wiki / 'graph-report.md'
    lines, seen = report_index.read_text().splitlines(), set()
    for index, line in enumerate(lines):
        for label, directory, mirror in (
            ('KLAPS50', '.', 'graph-report-klaps50'),
            ('Cloud-BAL', 'Cloud-BAL/', 'graph-report-cloud-bal'),
        ):
            if line.startswith(f'| {label} |'):
                stats = records[label]['after']
                lines[index] = (f'| {label} | `{directory}` | {SNAPSHOT} (B1 state path) | '
                                f'{stats["nodes"]} | {stats["edges"]} | {stats["communities"]} | [[{mirror}]] |')
                seen.add(label)
    require(seen == {'KLAPS50', 'Cloud-BAL'}, 'wiki report index lacks a maintained corpus row')
    report_index.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    index = wiki / 'index.md'
    content = index.read_text(encoding='utf-8')
    start = content.find('## Graph snapshot')
    require(start >= 0, 'wiki index has no Graph snapshot section')
    end = content.find('\n## ', start + 3)
    if end < 0:
        end = len(content)
    section = '## Graph snapshot\n\n' + '\n'.join(
        f'- {label}: {SNAPSHOT}; {records[label]["after"]["nodes"]} nodes / '
        f'{records[label]["after"]["edges"]} edges / {records[label]["after"]["communities"]} communities.'
        for label in ('KLAPS50', 'Cloud-BAL'))
    section += f'\n- Only {len(REQUIRED_PATHS)} selected Python sources are extracted; native source and runtime receipts are hash-only.\n'
    section += '- Graph freshness does not establish runtime or scientific validation.\n'
    content = content[:start] + section + content[end:]
    import re
    content, count = re.subn(r'(?m)^(date_modified:\s*)[^\r\n]+',
                             lambda match: match.group(1) + SNAPSHOT[:10], content, count=1)
    require(count == 1, 'wiki index date_modified is missing or ambiguous')
    index.write_text(content, encoding='utf-8')

    with (wiki / 'log.md').open('a', encoding='utf-8') as stream:
        stream.write(f'\n## [{SNAPSHOT[:10]}] kg-update | B1 state path\n')
        stream.write(f'- Source base `{lock["source_commit"]}`; selected Python AST extraction.\n')
        for label in ('KLAPS50', 'Cloud-BAL'):
            before, after = records[label]['before'], records[label]['after']
            stream.write(f'- {label}: {SNAPSHOT}; {after["nodes"]} nodes / {after["edges"]} edges / '
                         f'{after["communities"]} communities; delta nodes={after["nodes"] - before["nodes"]}, '
                         f'edges={after["edges"] - before["edges"]}.\n')
        stream.write(f'- {len(REQUIRED_PATHS)} Python sources extracted; selected-path manifest update only.\n')
        stream.write(f'- Validation: {lock["validation_summary"]}\n')
        stream.write(f'- Open items: {lock["open_items"]}\n')
        stream.write('- Fortran cross-file extraction is partial; graph freshness is not runtime/scientific validation.\n')
    return {name: sha256(wiki / name) for name in WIKI_FILES}


def freeze(review_path: Path) -> dict:
    require(not SELECTION.exists(), 'preserve an existing selection lock')
    review = json.loads(review_path.read_text(encoding='utf-8'))
    require(review.get('status') == 'PASS_SOURCE_AND_EVIDENCE_REVIEW',
            'independent source/evidence review must pass before freeze')
    selected = {}
    for relative in sorted(REQUIRED_PATHS):
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(), f'missing or unsafe selected source: {relative}')
        selected[relative] = sha256(path)
    require(review.get('source_hashes') == selected,
            'independent review must bind exactly the selected Python source paths')
    hash_only = {}
    for relative in sorted(hash_only_paths()):
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(), f'missing or unsafe hash-only path: {relative}')
        hash_only[relative] = sha256(path)
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    verify_baseline(baseline)
    initial_check = json.loads(INITIAL_CHECK.read_text(encoding='utf-8'))
    require(initial_check.get('status') == 'PASS' and
            initial_check.get('checked_snapshot_count') == 234 and
            initial_check.get('baseline_sha256') == sha256(BASELINE),
            'captured initial baseline check is not PASS or does not bind this baseline')
    require(hashlib.sha256(BASELINE.read_bytes()).hexdigest() ==
            'cd49f188f8852e5da9feb69ec7669864c0a598b683065b6152eb7bfb7b0ede91',
            'baseline file changed from preserved scratch capture')
    commit = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    freeze_id = hashlib.sha256(json.dumps(
        {'source_commit': commit, 'selected': selected, 'hash_only': hash_only},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]
    lock = {
        'status': 'FROZEN', 'review_status': 'GO', 'freeze_id': freeze_id,
        'snapshot': SNAPSHOT, 'source_commit': commit,
        'selected_source_sha256': selected, 'hash_only_sha256': hash_only,
        'review_sha256': sha256(review_path), 'baseline_sha256': sha256(BASELINE),
        'initial_baseline_check_sha256': sha256(INITIAL_CHECK),
        'validation_summary': review.get('validation_summary', 'Reviewed by an independent agent.'),
        'open_items': review.get('open_items', 'See independent source/evidence review.'),
        'maintained_roots_written': False,
        'raw_trace_policy': 'Fortran patches, runtime receipts, binaries, and compressed traces are SHA256-bound only; no raw runtime content is extracted into Graphify.',
        'consolidated_validation_note': 'Root writes the final aggregate validation after KG readback; it is excluded to avoid a self-hash cycle.',
    }
    SELECTION.write_text(json.dumps(lock, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return lock


def stage(lock_path: Path) -> dict:
    import graphify
    require(str(Path(graphify.__file__).resolve()).startswith(str(GRAPHIFY_HOME)),
            'use the pinned Graphify venv interpreter')
    require(GRAPHIFY_CLI.is_file(), 'pinned Graphify CLI is missing')
    require(subprocess.check_output([str(GRAPHIFY_CLI), '--version'], text=True).strip() ==
            'graphify 0.9.53', 'Graphify must remain pinned to 0.9.53')
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    require(lock.get('status') == 'FROZEN' and lock.get('review_status') == 'GO',
            'selection lock is not frozen and reviewed')
    require(lock.get('snapshot') == SNAPSHOT and bool(lock.get('freeze_id')),
            'selection lock snapshot identity is incorrect')
    require(lock.get('baseline_sha256') == sha256(BASELINE), 'baseline changed after freeze')
    require(lock.get('review_sha256') == sha256(EVIDENCE / 'review/independent_analysis_review.json'),
            'independent source/evidence review changed after freeze')
    require(set(lock.get('selected_source_sha256', {})) == REQUIRED_PATHS,
            'selected source scope differs from the exact reviewed paths')
    require(set(lock.get('hash_only_sha256', {})) == hash_only_paths(),
            'hash-only inventory changed after freeze')
    require(lock.get('source_commit') == subprocess.check_output(
        ['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
        'source commit changed after freeze')
    for relative, expected in {**lock['selected_source_sha256'], **lock['hash_only_sha256']}.items():
        require(sha256(SOURCE / relative) == expected, f'frozen path changed: {relative}')
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    verify_baseline(baseline)
    module = load_stage_helper()
    module.refresh_staged_report = refresh_staged_report
    module.write_staged_wiki = write_staged_wiki
    result = module.stage_selected(lock, REQUIRED_PATHS, REQUIRED_PATHS, STAGING)
    for relative, expected in {**lock['selected_source_sha256'], **lock['hash_only_sha256']}.items():
        require(sha256(SOURCE / relative) == expected, f'frozen path changed during stage: {relative}')
    verify_baseline(baseline)
    result.update({
        'status': 'STAGED_ONLY_NO_MAINTAINED_WRITES',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'snapshot': SNAPSHOT,
        'baseline_sha256': sha256(BASELINE),
        'selection_lock_sha256': sha256(lock_path),
        'dated_snapshots_preserved': 234,
        'source_extraction_scope': sorted(REQUIRED_PATHS),
        'manifest_update_scope': sorted(REQUIRED_PATHS),
        'hash_only_sha256': lock['hash_only_sha256'],
        'extraction_limits': [
            'Only the selected Python tools, their tests, the patch generator, and this KG helper are structurally extracted.',
            'All other new evidence, including native source copies and compressed traces, is hash-only.',
            'Manifest updates are selected-path-only; no corpus scan or prune occurs.',
            'Fortran cross-file CALL extraction is partial.',
            'Graph freshness does not establish runtime behavior, physical assumptions, or scientific approval.',
        ],
        'maintained_roots_written': False,
    })
    STAGE_RECEIPT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'stage'))
    parser.add_argument('--review', type=Path,
                        default=EVIDENCE / 'review/independent_analysis_review.json')
    parser.add_argument('--lock', type=Path, default=SELECTION)
    parser.add_argument('--stage', action='store_true',
                        help='required explicit permission from root for isolated staging')
    args = parser.parse_args()
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    verify_baseline(baseline)
    if args.action == 'freeze':
        result = freeze(args.review)
    else:
        require(args.stage, 'staging is disabled without explicit --stage')
        result = stage(args.lock)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
