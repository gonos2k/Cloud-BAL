#!/usr/bin/env python3
"""Freeze, stage, and publish a scoped weak/strong balance KG update.

The commands are implemented but are gated by a frozen source lock, exact
maintained-root baseline, staged validation, and a reviewer GO receipt. The
helper never scans or prunes either maintained corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path('/var/tmp/cloudbal-weak-strong')
MAINTAINED = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
EVIDENCE = SOURCE / 'docs/evidence/weak_strong_balance_20261030'
KG = EVIDENCE / 'kg'
SNAPSHOT = '2026-10-30-weak-strong-balance'
GRAPHIFY_ENV = Path('/var/tmp/snow-image-cdn-graphify-venv')
STAGING = Path('/var/tmp/cloudbal_weak_strong_kg_20261030')
BASELINE = KG / 'baseline.json'
SELECTION = KG / 'selection_lock.json'
STAGE_RECEIPT = KG / 'stage_receipt.json'
STAGE_VALIDATION = KG / 'stage_validation.json'
STAGE_REVIEW_TEMPLATE = KG / 'stage_review_template.json'
STAGE_REVIEW = KG / 'stage_review.json'
PUBLISH_RECEIPT = KG / 'publish_receipt.json'
GRAPH_FILES = ('graph.json', 'GRAPH_REPORT.md', 'manifest.json')
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md',
              'graph-report-cloud-bal.md', 'index.md', 'log.md')
EXPECTED_SNAPSHOTS = {'KLAPS50': 112, 'Cloud-BAL': 116}

# Exactly 17 Python sources: 4 runtime, 3 tools, 4 tests, 2 builders,
# 3 independent review/recount scripts, and this KG helper.
REQUIRED_PATHS = {
    'docs/evidence/weak_strong_balance_20261030/runtime/prepare_cases.py',
    'docs/evidence/weak_strong_balance_20261030/runtime/run_case.py',
    'docs/evidence/weak_strong_balance_20261030/runtime/run_all.py',
    'docs/evidence/weak_strong_balance_20261030/runtime/finalize_batch.py',
    'tools/initial_precip_gate.py',
    'tools/cp02_weak_strong_balance.py',
    'tools/plot_weak_strong_balance.py',
    'tests/test_initial_precip_gate.py',
    'tests/test_cp02_weak_strong_balance.py',
    'tests/test_weak_strong_balance_report.py',
    'tests/test_recount_cp02_weak_strong_balance.py',
    'docs/evidence/weak_strong_balance_20261030/build_report.py',
    'docs/evidence/weak_strong_balance_20261030/build_full_score_tables.py',
    'docs/evidence/weak_strong_balance_20261030/review/prior_tradeoff_audit.py',
    'docs/evidence/weak_strong_balance_20261030/review/prior_observed_band_audit.py',
    'tools/recount_cp02_weak_strong_balance.py',
    'docs/evidence/weak_strong_balance_20261030/kg/prepare_kg.py',
}
REQUIRED_FINAL_ARTIFACTS = {
    'docs/WEAK_STRONG_BALANCE_REPORT_20261030.md',
    'docs/WEAK_STRONG_BALANCE_FULL_SCORES_20261030.md',
    'docs/WEAK_STRONG_BALANCE_FIGURES_20261030.md',
    'docs/WEAK_STRONG_BALANCE_PROGRESS_20261030.md',
    'docs/evidence/weak_strong_balance_20261030/report_receipt.json',
    'docs/evidence/weak_strong_balance_20261030/full_tables_receipt.json',
    'docs/evidence/weak_strong_balance_20261030/figures_doc_receipt.json',
    'docs/evidence/weak_strong_balance_20261030/review/asset_batch_review_final.json',
    'docs/evidence/weak_strong_balance_20261030/review/final_analysis_review_final.json',
    'docs/evidence/weak_strong_balance_20261030/review/scorer_version_reconciliation_final.json',
    'docs/evidence/weak_strong_balance_20261030/validation/root_visual_review.json',
    'docs/evidence/weak_strong_balance_20261030/validation/package_figures.json',
    'docs/evidence/weak_strong_balance_20261030/validation/clean_export_tests.json',
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def graphify_stage_module():
    path = SOURCE / 'docs/evidence/snow_sensitivity_20261030/kg/stage_kg.py'
    spec = importlib.util.spec_from_file_location('weak_strong_graphify_stage', path)
    require(spec is not None and spec.loader is not None,
            f'cannot load known Graphify staging implementation: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SOURCE = SOURCE
    module.MAINTAINED = MAINTAINED
    module.SNAPSHOT = SNAPSHOT
    module.REQUIRED_PATHS = set(REQUIRED_PATHS)
    return module


def roots() -> dict[str, Path]:
    return {'KLAPS50': MAINTAINED, 'Cloud-BAL': MAINTAINED / 'Cloud-BAL'}


def snapshot_inventory(root: Path) -> dict:
    inventory = {}
    for folder in sorted((root / 'graphify-out').iterdir()):
        if folder.is_dir() and folder.name[:4].isdigit():
            inventory[folder.name] = {
                path.relative_to(folder).as_posix(): sha256(path)
                for path in sorted(folder.rglob('*')) if path.is_file()
            }
    return inventory


def capture_baseline() -> dict:
    records = {}
    for label, root in roots().items():
        snapshots = snapshot_inventory(root)
        require(len(snapshots) == EXPECTED_SNAPSHOTS[label],
                f'{label} expected {EXPECTED_SNAPSHOTS[label]} dated snapshots; '
                f'found {len(snapshots)}')
        status = subprocess.check_output(
            ['git', '-C', str(root), 'status', '--short'], text=True)
        records[label] = {
            'root': str(root),
            'graph_sha256': sha256(root / 'graphify-out/graph.json'),
            'graph_report_sha256': sha256(root / 'graphify-out/GRAPH_REPORT.md'),
            'manifest_sha256': sha256(root / 'graphify-out/manifest.json'),
            'dated_snapshots': snapshots,
            'git_status_exact': status.splitlines(),
            'git_status_raw_sha256': hashlib.sha256(status.encode()).hexdigest(),
        }
    total = sum(len(record['dated_snapshots']) for record in records.values())
    require(total == 228, f'expected 228 existing dated snapshots, found {total}')
    wiki = MAINTAINED / 'wiki'
    return {
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'snapshot': SNAPSHOT,
        'dated_snapshot_count_total': total,
        'maintained_roots': records,
        'wiki_hashes': {name: sha256(wiki / name) for name in WIKI_FILES},
        'maintained_roots_written': False,
    }


def verify_baseline(baseline: dict) -> None:
    require(baseline.get('dated_snapshot_count_total') == 228,
            'baseline must preserve all 228 prior dated snapshots')
    for label, root in roots().items():
        record = baseline['maintained_roots'][label]
        for name, key in (('graph.json', 'graph_sha256'),
                          ('GRAPH_REPORT.md', 'graph_report_sha256'),
                          ('manifest.json', 'manifest_sha256')):
            require(sha256(root / 'graphify-out' / name) == record[key],
                    f'{label} active {name} changed since baseline')
        require(snapshot_inventory(root) == record['dated_snapshots'],
                f'{label} dated snapshots changed since baseline')
        require(len(record['dated_snapshots']) == EXPECTED_SNAPSHOTS[label],
                f'{label} baseline snapshot count is incorrect')
        status = subprocess.check_output(
            ['git', '-C', str(root), 'status', '--short'], text=True)
        require(status.splitlines() == record['git_status_exact'],
                f'{label} exact dirty state changed since baseline')
        require(hashlib.sha256(status.encode()).hexdigest() ==
                record['git_status_raw_sha256'],
                f'{label} dirty-state bytes changed since baseline')
    wiki = MAINTAINED / 'wiki'
    require({name: sha256(wiki / name) for name in WIKI_FILES} ==
            baseline['wiki_hashes'], 'one or more of the five wiki mirrors changed')


def load_selection(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(),
            'frozen selection lock is missing or unsafe')
    lock = json.loads(path.read_text())
    require(lock.get('status') == 'FROZEN' and lock.get('review_status') == 'GO',
            'selection lock must be frozen with review_status GO')
    require(lock.get('snapshot') == SNAPSHOT and lock.get('freeze_id'),
            'selection lock must identify this dated snapshot and freeze_id')
    require(set(lock.get('selected_source_sha256', {})) == REQUIRED_PATHS,
            'selection lock must bind exactly the 17 required Python sources')
    head = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'],
                                   text=True).strip()
    require(lock.get('source_commit') == head,
            'selection lock source commit differs from the source worktree')
    for relative, expected in lock['selected_source_sha256'].items():
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink() and sha256(path) == expected,
                f'frozen source hash mismatch: {relative}')
    for relative, expected in lock.get('hash_only_sha256', {}).items():
        path = evidence_path(relative)
        require(path.is_file() and not path.is_symlink() and sha256(path) == expected,
                f'frozen hash-only evidence changed: {relative}')
    require(REQUIRED_FINAL_ARTIFACTS <= set(lock.get('hash_only_sha256', {})),
            'frozen hash-only list omits a required final report, receipt, or review')
    require(lock.get('validation_summary') and lock.get('open_items'),
            'selection lock must record validation summary and open items')
    return lock


def evidence_path(relative: str) -> Path:
    if relative.startswith('external:'):
        return Path(relative.removeprefix('external:'))
    path = Path(relative)
    return path if path.is_absolute() else SOURCE / path


def candidate_hash_only_paths(external_zip: Path | None = None) -> list[Path]:
    files = {path.resolve() for path in (EVIDENCE / 'analysis').rglob('*')
             if path.is_file() and not path.is_symlink()}
    files.update(path.resolve() for path in (EVIDENCE / 'review').rglob('*')
                 if path.is_file() and not path.is_symlink()
                 and path.suffix != '.py')
    files.update(path.resolve() for path in (EVIDENCE / 'runtime').rglob('*')
                 if path.is_file() and not path.is_symlink()
                 and path.suffix != '.py' and '__pycache__' not in path.parts)
    for name in ('selection_plan.json', 'README.md'):
        path = EVIDENCE / name
        if path.is_file() and not path.is_symlink():
            files.add(path.resolve())
    # These finalized top-level deliverables and builder/package receipts live
    # outside the recursively inventoried analysis/runtime/review directories.
    # Keep the list explicit so later evidence elsewhere in the repository is
    # never swept into this scoped hash-only inventory.
    explicit_artifacts = (
        SOURCE / 'docs/WEAK_STRONG_BALANCE_REPORT_20261030.md',
        SOURCE / 'docs/WEAK_STRONG_BALANCE_FULL_SCORES_20261030.md',
        SOURCE / 'docs/WEAK_STRONG_BALANCE_FIGURES_20261030.md',
        SOURCE / 'docs/WEAK_STRONG_BALANCE_PROGRESS_20261030.md',
        EVIDENCE / 'report_receipt.json',
        EVIDENCE / 'full_tables_receipt.json',
        EVIDENCE / 'figures_doc_receipt.json',
        EVIDENCE / 'review/asset_batch_review_final.json',
        EVIDENCE / 'review/final_analysis_review_final.json',
        EVIDENCE / 'review/scorer_version_reconciliation_final.json',
        EVIDENCE / 'validation/root_visual_review.json',
        EVIDENCE / 'validation/package_figures.json',
        EVIDENCE / 'validation/clean_export_tests.json',
    )
    for path in explicit_artifacts:
        if path.is_file() and not path.is_symlink():
            files.add(path.resolve())
    history = KG / 'source_hash_history.json'
    if history.is_file() and not history.is_symlink():
        files.add(history.resolve())
    # Include final graphics and reports wherever the report builder places them.
    for path in EVIDENCE.rglob('*'):
        if (path.is_file() and not path.is_symlink()
                and path.suffix.lower() in {'.png', '.md', '.html'}
                and 'kg' not in path.relative_to(EVIDENCE).parts):
            files.add(path.resolve())
    if external_zip is not None:
        zip_path = external_zip.resolve()
        require(zip_path.is_file() and zip_path.suffix.lower() == '.zip',
                f'external evidence archive is missing or not a ZIP: {zip_path}')
        files.add(zip_path)
    return sorted(files)


def inspect_inventory(external_zip: Path | None = None) -> dict:
    baseline = capture_baseline()
    source_hashes = {}
    for relative in REQUIRED_PATHS:
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(),
                f'missing or unsafe Python source: {relative}')
        source_hashes[relative] = sha256(path)
    hash_only = {}
    for path in candidate_hash_only_paths(external_zip):
        try:
            relative = path.relative_to(SOURCE).as_posix()
        except ValueError:
            relative = f'external:{path}'
        hash_only[relative] = sha256(path)
    return {
        'status': 'INSPECTED_ONLY_NOT_FROZEN',
        'snapshot': SNAPSHOT,
        'source_paths_structurally_extracted': dict(sorted(source_hashes.items())),
        'source_path_count': len(source_hashes),
        'candidate_hash_only_sha256': dict(sorted(hash_only.items())),
        'candidate_hash_only_count': len(hash_only),
        'maintained_baseline_readback': baseline,
        'graphify': {
            'required_version': '0.9.53',
            'environment': str(GRAPHIFY_ENV),
            'rapidfuzz_available': True,
        },
        'extraction_limits': [
            'Only the 17 listed Python files are structurally extracted.',
            'Maps, histories, score arrays, prior audits, receipts, figures, Markdown, and external ZIP evidence are hash-only.',
            'External ZIP evidence must be added by exact path once the final archive exists.',
            'No full corpus scan, stale-file prune, or Fortran structural extraction.',
            'Graph freshness does not establish runtime or scientific validation.',
        ],
        'write_performed': False,
    }


def require_graphify_profile() -> None:
    prefix = Path(sys.prefix).resolve()
    require(prefix == GRAPHIFY_ENV.resolve(),
            f'use the pinned Graphify environment: {GRAPHIFY_ENV}')
    version = subprocess.check_output(['graphify', '--version'], text=True).strip()
    require(version == 'graphify 0.9.53',
            f'Graphify 0.9.53 required, found {version!r}')
    rapidfuzz = subprocess.check_output(
        [sys.executable, '-c',
         'import rapidfuzz; print(rapidfuzz.__version__)'], text=True).strip()
    require(bool(rapidfuzz), 'rapidfuzz is required in the pinned environment')


def rewrite_staged_narrative(stage_root: Path) -> None:
    report = stage_root / 'graphify-out/GRAPH_REPORT.md'
    text = report.read_text()
    text = text.replace('snow sensitivity', 'weak/strong balance')
    text += (
        '\n## weak/strong balance scoped update\n'
        '- Exactly 17 frozen Python sources are structurally extracted; all other evidence is hash-only.\n'
        '- The six gated/equal-mass cases modify initial QSNOW only; the two crossed diagnostic cases preserve their native inputs.\n'
        '- Prior 228 dated snapshots are retained; manifest updates are selected-path-only without corpus scanning or pruning.\n'
        '- Graph freshness does not establish model correctness or scientific validity.\n'
        '- Fortran cross-file CALL extraction is partial.\n'
    )
    report.write_text(text)


def staged_targets(receipt: dict) -> list[dict]:
    run = Path(receipt['stage'])
    targets = []
    for label, root in roots().items():
        graph = run / label / 'graphify-out'
        for name in GRAPH_FILES:
            targets.append({
                'source': graph / name,
                'destination': root / 'graphify-out' / name,
                'kind': 'file',
                'sha256': receipt['corpora'][label]['snapshot_file_sha256'][name],
            })
        targets.append({
            'source': graph / SNAPSHOT,
            'destination': root / 'graphify-out' / SNAPSHOT,
            'kind': 'directory',
            'files': receipt['corpora'][label]['snapshot_file_sha256'],
        })
    for name, expected in receipt['staged_wiki_sha256'].items():
        targets.append({
            'source': run / 'wiki' / name,
            'destination': MAINTAINED / 'wiki' / name,
            'kind': 'file', 'sha256': expected,
        })
    return targets


def hash_target(target: dict) -> None:
    if target['kind'] == 'file':
        require(sha256(target['source']) == target['sha256'],
                f'staged file hash mismatch: {target["source"]}')
    else:
        for name, expected in target['files'].items():
            require(sha256(target['source'] / name) == expected,
                    f'staged snapshot hash mismatch: {target["source"] / name}')


def validate_stage(lock: dict, result: dict) -> dict:
    targets = staged_targets(result)
    for target in targets:
        hash_target(target)
    for label in ('KLAPS50', 'Cloud-BAL'):
        record = result['corpora'][label]
        require(record['selected_source_sha256'] == lock['selected_source_sha256'],
                f'{label} staged source binding differs from lock')
        require(all(value == 0 for value in record['integrity_zero_counts'].values()),
                f'{label} staged graph integrity failed')
        require(record['before']['nodes'] <= record['after']['nodes'],
                f'{label} node count unexpectedly decreased')
    return {
        'status': 'PASS_STAGED_ONLY',
        'review_status': 'PENDING_INDEPENDENT_GO',
        'selection_lock_sha256': sha256(SELECTION),
        'stage_receipt_sha256': sha256(STAGE_RECEIPT),
        'staged_target_count': len(targets),
        'staged_targets': [
            {'path': str(target['source']), 'kind': target['kind'],
             'sha256': target.get('sha256'), 'files': target.get('files')}
            for target in targets
        ],
        'prior_snapshot_count': 228,
        'maintained_roots_written': False,
        'checks': ['selection and hash-only pins', 'graph integrity',
                   'all staged graph/wiki readbacks', '17-source exact scope'],
    }


def stage_update() -> dict:
    require_graphify_profile()
    require(BASELINE.is_file(), 'capture the root baseline before staging')
    baseline = json.loads(BASELINE.read_text())
    verify_baseline(baseline)
    lock = load_selection(SELECTION)
    paths = set(REQUIRED_PATHS)
    stage = graphify_stage_module()
    result = stage.stage_selected(lock, paths, paths, STAGING)
    for label in ('KLAPS50', 'Cloud-BAL'):
        rewrite_staged_narrative(Path(result['stage']) / label)
        graph = Path(result['stage']) / label / 'graphify-out'
        snapshot = graph / SNAPSHOT
        for name in GRAPH_FILES:
            shutil.copy2(graph / name, snapshot / name)
        result['corpora'][label]['snapshot_file_sha256'] = {
            name: sha256(snapshot / name) for name in GRAPH_FILES
        }
    # Mirror the revised corpus reports into the three report pages.
    wiki = Path(result['stage']) / 'wiki'
    shutil.copy2(Path(result['stage']) / 'KLAPS50/graphify-out/GRAPH_REPORT.md',
                 wiki / 'graph-report-klaps50.md')
    shutil.copy2(Path(result['stage']) / 'Cloud-BAL/graphify-out/GRAPH_REPORT.md',
                 wiki / 'graph-report-cloud-bal.md')
    for name in WIKI_FILES:
        text = (wiki / name).read_text().replace('snow sensitivity', 'weak/strong balance')
        (wiki / name).write_text(text)
    result['staged_wiki_sha256'] = {name: sha256(wiki / name) for name in WIKI_FILES}
    verify_baseline(baseline)
    load_selection(SELECTION)
    receipt = {
        **result,
        'status': 'STAGED_ONLY_NO_MAINTAINED_WRITES',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'snapshot': SNAPSHOT,
        'baseline_sha256': sha256(BASELINE),
        'selection_lock_sha256': sha256(SELECTION),
        'dated_snapshots_preserved': 228,
        'source_extraction_scope': sorted(paths),
        'manifest_update_scope': sorted(paths),
        'hash_only_sha256': lock.get('hash_only_sha256', {}),
        'graphify_version': '0.9.53',
        'extraction_limits': [
            'Only 17 frozen Python files are structurally extracted.',
            'All histories, maps, metrics, audits, receipts, figures, Markdown, and ZIP archives are hash-only.',
            'Manifest updates are selected-path-only; no full corpus scan or pruning occurs.',
            'Graph freshness does not establish runtime or scientific validity.',
            'Fortran cross-file CALL extraction is partial.',
        ],
    }
    STAGE_RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    validation = validate_stage(lock, receipt)
    STAGE_VALIDATION.write_text(json.dumps(validation, indent=2, sort_keys=True) + '\n')
    review_template = {
        'status': 'PENDING_REVIEW',
        'review_status': 'PENDING',
        'stage_receipt_sha256': sha256(STAGE_RECEIPT),
        'stage_validation_sha256': sha256(STAGE_VALIDATION),
        'reviewer': None,
        'findings': [],
    }
    STAGE_REVIEW_TEMPLATE.write_text(
        json.dumps(review_template, indent=2, sort_keys=True) + '\n')
    return receipt


def status_path(line: str) -> str:
    return line[3:] if len(line) >= 4 else line


def unrelated_status(label: str, lines: list[str]) -> list[str]:
    allowed = {'graphify-out/graph.json', 'graphify-out/GRAPH_REPORT.md',
                'graphify-out/manifest.json', f'graphify-out/{SNAPSHOT}'}
    if label == 'KLAPS50':
        allowed.update(f'wiki/{name}' for name in WIKI_FILES)
    prefix = 'Cloud-BAL/' if label == 'KLAPS50' else ''
    unrelated = []
    for line in lines:
        path = status_path(line)
        relative = path[len(prefix):] if prefix and path.startswith(prefix) else path
        if relative not in allowed and not any(relative.startswith(item + '/')
                                               for item in allowed):
            unrelated.append(line)
    return unrelated


def publish_targets(targets: list[dict], backup_root: Path, baseline: dict,
                    stage_module) -> None:
    require(not backup_root.exists(), f'preserve existing backup: {backup_root}')
    backup_root.mkdir(parents=True)
    backups = []
    temporaries = []
    try:
        for index, target in enumerate(targets):
            source, destination = target['source'], target['destination']
            require(not destination.is_symlink(), f'refuse symlink target: {destination}')
            destination.parent.mkdir(parents=True, exist_ok=True)
            existed = destination.exists()
            backup = backup_root / f'{index:02d}-{destination.name}'
            if existed:
                if target['kind'] == 'directory':
                    shutil.copytree(destination, backup)
                else:
                    shutil.copy2(destination, backup)
            backups.append((destination, backup, existed, target['kind']))
            temporary = destination.with_name(
                f'.{destination.name}.weak-strong-{uuid.uuid4().hex}.tmp')
            temporaries.append(temporary)
            if target['kind'] == 'directory':
                shutil.copytree(source, temporary)
            else:
                shutil.copy2(source, temporary)
            temporary.replace(destination)
        for target in targets:
            if target['kind'] == 'file':
                require(sha256(target['destination']) == target['sha256'],
                        f'published file readback mismatch: {target["destination"]}')
            else:
                for name, expected in target['files'].items():
                    require(sha256(target['destination'] / name) == expected,
                            f'published snapshot readback mismatch: {target["destination"] / name}')
        for label, root in roots().items():
            current = snapshot_inventory(root)
            prior = baseline['maintained_roots'][label]['dated_snapshots']
            require({name: current[name] for name in prior} == prior,
                    f'{label} prior dated snapshots changed during publish')
            status = subprocess.check_output(
                ['git', '-C', str(root), 'status', '--short'], text=True).splitlines()
            before = baseline['maintained_roots'][label]['git_status_exact']
            require(unrelated_status(label, status) == unrelated_status(label, before),
                    f'{label} unrelated dirty-state paths changed during publish')
        require(sum(len(snapshot_inventory(root)) for root in roots().values()) == 230,
                'published result must add exactly one dated snapshot per corpus')
    except Exception:
        for temporary in temporaries:
            if temporary.exists():
                if temporary.is_dir():
                    shutil.rmtree(temporary)
                else:
                    temporary.unlink()
        for destination, backup, existed, kind in reversed(backups):
            if destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            if existed:
                temporary = destination.with_name(
                    f'.{destination.name}.weak-strong-rollback-{uuid.uuid4().hex}.tmp')
                if kind == 'directory':
                    shutil.copytree(backup, temporary)
                else:
                    shutil.copy2(backup, temporary)
                temporary.replace(destination)
        raise


def publish_update(go_file: Path) -> dict:
    require(BASELINE.is_file() and STAGE_RECEIPT.is_file() and
            STAGE_VALIDATION.is_file() and SELECTION.is_file(),
            'baseline, frozen selection, stage receipt, and validation are required')
    baseline = json.loads(BASELINE.read_text())
    receipt = json.loads(STAGE_RECEIPT.read_text())
    validation = json.loads(STAGE_VALIDATION.read_text())
    lock = load_selection(SELECTION)
    require(go_file.is_file() and not go_file.is_symlink(),
            'review GO file is missing or unsafe')
    approval = json.loads(go_file.read_text())
    require(approval.get('status') == 'GO' and approval.get('review_status') == 'GO',
            'publication requires reviewer status=GO and review_status=GO')
    require(approval.get('stage_receipt_sha256') == sha256(STAGE_RECEIPT) and
            approval.get('stage_validation_sha256') == sha256(STAGE_VALIDATION),
            'review GO must bind exact stage receipt and validation')
    require(validation.get('status') == 'PASS_STAGED_ONLY' and
            validation.get('stage_receipt_sha256') == sha256(STAGE_RECEIPT),
            'stage validation is missing or does not bind the receipt')
    require(receipt.get('status') == 'STAGED_ONLY_NO_MAINTAINED_WRITES' and
            receipt.get('dated_snapshots_preserved') == 228,
            'stage receipt is not a validated 228-snapshot isolated stage')
    require(receipt.get('selection_lock_sha256') == sha256(SELECTION) and
            receipt.get('baseline_sha256') == sha256(BASELINE),
            'frozen source or maintained baseline changed after staging')
    require(receipt.get('source_extraction_scope') == sorted(REQUIRED_PATHS) and
            receipt.get('manifest_update_scope') == sorted(REQUIRED_PATHS),
            'stage does not use the exact 17-source scope')
    require(receipt.get('hash_only_sha256') == lock.get('hash_only_sha256', {}),
            'hash-only evidence set changed after staging')
    for relative, expected in lock.get('hash_only_sha256', {}).items():
        path = evidence_path(relative)
        require(path.is_file() and sha256(path) == expected,
                f'hash-only evidence changed: {relative}')
    targets = staged_targets(receipt)
    for target in targets:
        hash_target(target)
    verify_baseline(baseline)
    for root in roots().values():
        require(not (root / 'graphify-out' / SNAPSHOT).exists(),
                f'target snapshot already exists: {root / "graphify-out" / SNAPSHOT}')
    stage_module = graphify_stage_module()
    backup = STAGING / f'publish-backup-{lock["freeze_id"]}'
    publish_targets(targets, backup, baseline, stage_module)
    result = {
        'status': 'PUBLISHED_AND_READBACK_PASS',
        'review_status': 'GO',
        'approval_sha256': sha256(go_file),
        'stage_receipt_sha256': sha256(STAGE_RECEIPT),
        'stage_validation_sha256': sha256(STAGE_VALIDATION),
        'selection_lock_sha256': sha256(SELECTION),
        'snapshot': SNAPSHOT,
        'prior_dated_snapshots_preserved': 228,
        'published_snapshot_count': 230,
        'rollback_backup': str(backup),
        'targets': [
            {'path': str(target['destination']), 'kind': target['kind'],
             'sha256': target.get('sha256'), 'files': target.get('files')}
            for target in targets
        ],
    }
    PUBLISH_RECEIPT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'baseline', 'stage', 'publish'))
    parser.add_argument('--go-file', type=Path, default=STAGE_REVIEW)
    parser.add_argument('--external-zip', type=Path,
                        help='exact finalized evidence ZIP to include in a read-only inventory')
    args = parser.parse_args()
    if args.action == 'inspect':
        result = inspect_inventory(args.external_zip)
    elif args.action == 'baseline':
        require(not BASELINE.exists(), 'preserve existing baseline; do not overwrite')
        result = capture_baseline()
        BASELINE.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        result = {'status': 'BASELINE_CAPTURED_READ_ONLY', 'baseline_sha256': sha256(BASELINE),
                  'dated_snapshot_count_total': result['dated_snapshot_count_total']}
    elif args.action == 'stage':
        result = stage_update()
    else:
        result = publish_update(args.go_file)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
