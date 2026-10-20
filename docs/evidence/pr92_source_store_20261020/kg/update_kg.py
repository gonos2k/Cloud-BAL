#!/usr/bin/env python3
"""Selected-source PR92 Graphify/KG overlay; never copies maintained source files."""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
MAINT = ROOT / 'Cloud-BAL'
SOURCE = ROOT / 'scratch/pr92_source_store_20261020/Cloud-BAL'
OUT = MAINT / 'scratch/pr92_source_store_20261020/kg'
BASE = '71b8c1d5dae181c163d04eabac9cf8f80134f417'
PRIOR = MAINT / 'scratch/pr91_host_store_20261020/kg/kg_receipt.json'
PRIOR_SHA = '63ac1b4469a2baaf37c22b0f97e5eed5b5d50f03a18502be23b69ed4f74ba91d'
SNAPSHOT = '2026-10-20-source-store'
HELPER = Path('/var/tmp/pr91_refresh_kg_host_store_20261020.py')
HELPER_SHA = 'a2b4de3e7941e3d0cf2cf8d60ee3956338fe2471df960c1f93c04bcf554ea9cf'
INTEGRATION = 'docs/evidence/pr92_source_store_20261020/integration_manifest.json'
VALIDATION = 'docs/evidence/pr92_source_store_20261020/final_validation.json'
GRAPH_PATHS = frozenset(['docs/PR92_SCIENCE_RESPONSE_20261020.md', 'docs/PR92_SOURCE_STORE_CONTRACT_20261020.md', 'src/common/cloud_bal_joint_transport.f90', 'tests/run_unit_tests.sh', 'tests/test_pr86_time_response.py', 'tests/test_pr91_inactive_ice_store_c14.py', 'tests/test_pr92_bulk_volume_policy.f90', 'tests/test_pr92_graupel_store_replay.py', 'tests/test_pr92_mixture_witness_replay.py', 'tests/test_pr92_qc_vertical_support.py', 'tests/test_pr92_source_replay.py', 'tests/test_pr92_source_store_fixture.py', 'tools/pr86_time_response.py', 'tools/pr91_host_store_trace.py', 'tools/pr92_bulk_volume_store.py', 'tools/pr92_c14_field_scopes.py', 'tools/pr92_diffusion_producer_capture.py', 'tools/pr92_graupel_store_replay.py', 'tools/pr92_mixture_witness_replay.py', 'tools/pr92_qc_vertical_support.py', 'tools/pr92_response_maps.py', 'tools/pr92_source_replay.py', 'tools/pr92_source_store_fixture.py'])


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def load_module(name, path, expected):
    require(digest(path) == expected, f'importer pin changed: {path}')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git(*args):
    return subprocess.check_output(['git', *args], cwd=SOURCE, text=True).strip()


def protected_content(h):
    result = {}
    for relative in ('wiki/hot.md', 'wiki/overview.md'):
        path = ROOT / relative
        h.guard_destination(path)
        result[relative] = digest(path)
    directories = ('.schema', '.schema-proposals', '.research-queue', 'entities', 'concepts',
                   'sources', 'decisions', 'heuristics', 'experiences', 'procedures', 'queries')
    for name in directories:
        relative = f'wiki/{name}'
        path = ROOT / relative
        if path.exists():
            h.guard_directory(path)
            rows = []
            for child in sorted(p for p in path.rglob('*') if p.is_file()):
                h.guard_destination(child)
                rows.append((child.relative_to(ROOT).as_posix(), digest(child)))
            result[relative] = hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()
    return result


def check_evidence(commit, pr_url):
    for relative in (VALIDATION, INTEGRATION):
        committed = subprocess.check_output(['git', 'show', f'{commit}:{relative}'], cwd=SOURCE)
        require(committed == (SOURCE / relative).read_bytes(), f'evidence is not bound to frozen commit: {relative}')
    number = pr_url.rsplit('/', 1)[1]
    pr = json.loads(subprocess.check_output(['gh', 'api', f'repos/gonos2k/Cloud-BAL/pulls/{number}'], text=True))
    require(pr['html_url'] == pr_url and pr['state'] == 'open' and pr['head']['sha'] == commit and
            pr['head']['ref'] == 'fix/pr92-source-graupel-store' and pr['base']['ref'] == 'main',
            'actual PR head/base does not match frozen candidate')
    validation = json.loads((SOURCE / VALIDATION).read_text())
    integration = json.loads((SOURCE / INTEGRATION).read_text())
    require(validation['status'] == 'PASS', 'final source validation is not PASS')
    for relative, expected in validation['source_sha256'].items():
        require(digest(SOURCE / relative) == expected, f'validation source changed: {relative}')
    for row in validation['raw_logs']:
        require(digest(SOURCE / row['path']) == row['sha256'], f'validation log changed: {row["path"]}')
    require(integration['physical_approval'] == 'FAIL_OPEN', 'unexpected physical promotion')
    require(integration['base_commit'] == BASE and integration['candidate_identity'] == 'PR92-C18-bounded' and
            integration['candidate_executable_sha256'] == '32a324d49366487f68ec1e6e687a465ef2533bd9163e2fe09733e83cc2272c16',
            'integration candidate/base differs from reviewed identity')
    require(integration['validation_sha256'] == digest(SOURCE / VALIDATION), 'validation binding changed')
    runtime = []
    for row in integration['closed_runtime_receipts']:
        path = SOURCE / row['path']
        require(digest(path) == row['sha256'], f'closed runtime receipt changed: {path}')
        receipt = json.loads(path.read_text())
        require(not receipt['processing_errors'], 'runtime collector errors')
        require(receipt['candidate_build_unchanged'], 'candidate build changed')
        require(receipt['executed_executable_sha256'] == integration['candidate_executable_sha256'],
                'runtime executable differs from candidate')
        require(receipt['status'] == row['status'] and receipt['returncode'] == row['returncode'] and
                receipt['final_completed_step'] == row['final_completed_step'], 'runtime status differs')
        if receipt['status'] == 'COMPLETE':
            require(receipt['returncode'] == 0 and receipt['final_completed_step'] == 30 and
                    receipt['snapshots']['completed_post_kdm6_timesteps'] == list(range(1, 31)),
                    '600-second completion contract failed')
        runtime.append({**row, 'executed_executable_sha256': receipt['executed_executable_sha256']})
    require({row['arm'] for row in runtime} == {'OFF', 'COUPLED'}, 'paired closed receipts required')
    audits = integration['completed_state_audits']
    require({row['arm'] for row in audits} == {'OFF', 'COUPLED'}, 'paired completed-state audits required')
    for row in audits:
        path = SOURCE / row['path']
        require(digest(path) == row['sha256'], 'completed-state audit changed')
        audit = json.loads(path.read_text())
        receipt = next(item for item in runtime if item['arm'] == row['arm'])
        require(audit['provenance']['receipt_sha256'] == receipt['sha256'] and
                audit['provenance']['candidate_executable_sha256'] == integration['candidate_executable_sha256'],
                'completed-state audit runtime binding changed')
        policy = audit['declared_native_ice_policy_split']
        require(policy == row['declared_policy'] and policy['status'] == 'PASS' and
                policy['strict_state_failure_count'] == 0 and policy['active_outlier_count'] == 0 and
                policy['completed_states'] == 6 * receipt['final_completed_step'],
                'completed-state policy changed')
        require(audit['completed_state_audit']['status'] == row['generic_exact_source_status'],
                'generic audit status changed')
    return {'frozen_source_commit': commit, 'verified_actual_pr_url': pr_url,
            'commit_binding': 'clean checkout, git-show evidence bytes, validated source hashes, actual GitHub PR head',
            'validation_path': VALIDATION, 'validation_sha256': digest(SOURCE / VALIDATION),
            'integration_path': INTEGRATION, 'integration_sha256': digest(SOURCE / INTEGRATION),
            'closed_runtime_receipts': runtime, 'candidate_scientific_gates': integration['candidate_scientific_gates']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--pr-url', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    version = subprocess.check_output(['graphify', '--version'], text=True).strip()
    require(tuple(map(int, re.search(r'(\d+)\.(\d+)\.(\d+)', version).groups())) >= (0, 8, 24),
            'Graphify >= 0.8.24 is required for Fortran')
    require(re.fullmatch(r'https://github.com/gonos2k/Cloud-BAL/pull/\d+', args.pr_url), 'unexpected PR URL')
    require(git('rev-parse', 'HEAD') == args.commit and not git('status', '--porcelain'), 'source must be clean at frozen commit')
    require(digest(PRIOR) == PRIOR_SHA, 'preceding PR91 receipt changed')
    prior = json.loads(PRIOR.read_text())
    h = load_module('pr91_guard_library', HELPER, HELPER_SHA)
    h.SOURCE = SOURCE
    h.OUT = OUT
    for path, expected in prior['prior_immutable_receipts'].items():
        require(digest(path) == expected, f'inherited immutable pin changed: {path}')
    maintained = h.maintained_source_snapshot()
    require(len(maintained) == 627 and canonical(maintained) == prior['maintained_source_snapshot']['before_sha256'],
            'maintained dirty-source inventory changed')
    protected = protected_content(h)
    require(protected == prior['protected_content_before_sha256'], 'protected wiki content changed')
    evidence = check_evidence(args.commit, args.pr_url)
    changed = git('diff', '--name-only', '--diff-filter=ACMRT', BASE, args.commit).splitlines()
    items = []
    for relative in changed:
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(), f'unsupported selected path: {relative}')
        items.append({'path': relative, 'candidate_sha256': digest(path),
                      'maintained_before_sha256': digest(MAINT / relative) if (MAINT / relative).is_file() else None})
    graph_items = [row for row in items if not row['path'].startswith('docs/evidence/') and
                   (row['path'].startswith(('src/', 'tests/', 'tools/')) or
                    row['path'].startswith('docs/PR92_'))]
    require({row['path'] for row in graph_items} == GRAPH_PATHS, 'changed graph-source set differs from frozen reviewed allowlist')
    require(graph_items and all(Path(row['path']).suffix.lower() in ('.f90', '.py', '.sh', '.md') for row in graph_items),
            'unsupported maintained extraction path')
    for label, directory in (('KLAPS50', ROOT), ('Cloud-BAL', MAINT)):
        require(digest(directory / 'graphify-out/graph.json') == prior['corpora'][label]['sha256'], f'{label} baseline graph changed')
        require(not (directory / 'graphify-out' / SNAPSHOT).exists(), 'new dated snapshot already exists')
    for folder, members in prior['automatic_snapshot_preservation'].items():
        folder = Path(folder)
        require({child.name for child in folder.iterdir()} == set(members), 'historical auto snapshot membership changed')
        for name, row in members.items():
            require(digest(folder / name) == row['sha256'], f'historical auto snapshot changed: {folder/name}')
    for members in prior['dated_snapshots'].values():
        for row in members.values():
            require(digest(row['path']) == row['after_sha256'], f'preceding named snapshot changed: {row["path"]}')
    for relative, expected in prior['wiki_sha256'].items():
        require(digest(ROOT / relative) == expected, f'derived wiki baseline changed: {relative}')
    for members in prior['dated_snapshots'].values():
        folder = Path(next(iter(members.values()))['path']).parent
        require({child.name for child in folder.iterdir()} == set(members), 'named historical snapshot membership changed')
    report_rows = (ROOT / 'wiki/graph-report.md').read_text().splitlines()
    for label in ('KLAPS50', 'Cloud-BAL'):
        require(sum(line.startswith(f'| {label} |') for line in report_rows) == 1, 'wiki corpus row missing or duplicated')
    plan = {'source_commit': args.commit, 'base': BASE, 'pr': args.pr_url,
            'selected_paths': items, 'graph_source_paths': [row['path'] for row in graph_items],
            'prior_receipt_sha256': PRIOR_SHA, 'evidence_binding': evidence,
            'maintained_source_sha256': canonical(maintained), 'graphify_version': version}
    if not args.apply:
        print(json.dumps({'status': 'CHECK_ONLY_NO_WRITES', **plan}, indent=2))
        return
    require(not OUT.exists(), 'refuse to overwrite existing KG output')
    OUT.mkdir(parents=True)
    updater = load_module('pr92_selected_graph_updater', h.DELEGATED_UPDATER, h.DELEGATED_UPDATER_SHA256)
    audit = load_module('pr92_selected_graph_auditor', h.DELEGATED_AUDITOR, h.DELEGATED_AUDITOR_SHA256)
    updater.SOURCE = SOURCE
    updater.OUT = OUT
    updater.BASE_COMMIT = BASE
    updater.PR = args.pr_url
    updater.PATHS = tuple(row['path'] for row in graph_items)
    audit.ROOT, audit.MAINTAINED, audit.OUT, audit.PATHS = ROOT, MAINT, OUT, updater.PATHS
    before_graphs = {label: json.loads((directory / 'graphify-out/graph.json').read_text())
                     for label, directory in (('KLAPS50', ROOT), ('Cloud-BAL', MAINT))}
    backups = {}
    automatic = {}
    for label, directory in (('KLAPS50', ROOT), ('Cloud-BAL', MAINT)):
        for relative in updater.GRAPH_FILES:
            path = directory / 'graphify-out' / relative
            h.guard_destination(path, directory)
            backup = OUT / 'backups' / label / relative
            if path.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
            backups[path] = backup if path.exists() else None
        for day in ('2026-10-19', '2026-10-20'):
            folder = directory / 'graphify-out' / day
            if folder.exists():
                automatic[str(folder)] = {}
                for path in folder.iterdir():
                    require(path.is_file() and not path.is_symlink(), 'unsupported automatic snapshot member')
                    if path.is_file():
                        h.guard_destination(path, directory)
                        backup = OUT / 'backups' / label / day / path.relative_to(folder)
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, backup)
                        backups[path] = backup
                        automatic[str(folder)][path.name] = {'backup': str(backup), 'sha256': digest(backup)}
    for relative in updater.WIKI_FILES:
        path = ROOT / 'wiki' / relative
        h.guard_destination(path)
        backup = OUT / 'backups/wiki' / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        backups[path] = backup
    records = {}
    try:
        for label, directory, prefix in (('KLAPS50', ROOT, 'Cloud-BAL'), ('Cloud-BAL', MAINT, '')):
            records[label] = updater.update_graph(label, directory, prefix, graph_items)
            extraction = json.loads((OUT / f'{label.lower().replace("-", "_")}_extraction.json').read_text())
            audit.record_snapshot(label, directory, before_graphs[label], extraction)
        private = audit.verify_private_profile(before_graphs)
        h.restore_automatic_snapshots(automatic)
        limits = ('Selected-source AST/Markdown headings only; no semantic refresh. Cross-file Fortran CALL edges are partial. '
                  'Generated Fortran inside Python strings and archived/compressed evidence are hash-bound, not separately AST-extracted. '
                  'This persistent graph combines earlier snapshots and selected overlays; freshness is navigation evidence, not runtime/scientific approval.')
        for label, directory in (('KLAPS50', ROOT), ('Cloud-BAL', MAINT)):
            path = directory / 'graphify-out/GRAPH_REPORT.md'
            text = path.read_text()
            section = f'## Graph Freshness\n\n- PR92 source `{args.commit}` against `{BASE}`; {len(graph_items)} selected source/doc paths.\n- {limits}\n'
            text, count = re.subn(r'## Graph Freshness\n.*?(?=\n## |\Z)', section, text, flags=re.S)
            require(count == 1, 'derived freshness section missing')
            path.write_text(text)
            records[label]['snapshot'] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            records[label]['delta_communities'] = records[label]['communities'] - prior['corpora'][label]['communities']
            dated = directory / 'graphify-out' / SNAPSHOT
            dated.mkdir()
            for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'):
                shutil.copy2(directory / 'graphify-out' / name, dated / name)
            report_name = 'graph-report-klaps50.md' if label == 'KLAPS50' else 'graph-report-cloud-bal.md'
            shutil.copy2(path, ROOT / 'wiki' / report_name)
            records[label]['dated_snapshot'] = str(dated)
            records[label]['previous_graph_sha256'] = prior['corpora'][label]['sha256']
        index = ROOT / 'wiki/graph-report.md'
        lines = index.read_text().splitlines()
        for n, line in enumerate(lines):
            for label, record in records.items():
                if line.startswith(f'| {label} |'):
                    folder = '.' if label == 'KLAPS50' else 'Cloud-BAL/'
                    mirror = 'graph-report-klaps50' if label == 'KLAPS50' else 'graph-report-cloud-bal'
                    lines[n] = f'| {label} | `{folder}` | {SNAPSHOT} (PR92 selected overlay) | {record["nodes"]} | {record["edges"]} | {record["communities"]} | [[{mirror}]] |'
        index.write_text('\n'.join(lines) + '\n')
        page = ROOT / 'wiki/index.md'
        original = page.read_bytes()
        require(original.count(b'## Graph snapshot') == 1, 'wiki Graph snapshot heading missing or duplicated')
        start = original.index(b'## Graph snapshot')
        end = original.find(b'\n## ', start + 3)
        if end < 0:
            end = len(original)
        section = '## Graph snapshot\n\n' + '\n'.join(
            f'- {label}: {SNAPSHOT}; {r["nodes"]} nodes / {r["edges"]} edges / {r["communities"]} communities; delta [{r["delta_nodes"]}, {r["delta_edges"]}].'
            for label, r in records.items()) + '\n- [[graph-report|Separate corpus reports]] retain extraction limits; navigation freshness does not establish scientific acceptance.\n'
        page.write_bytes(original[:start] + section.encode() + original[end:])
        require(page.read_bytes() == original[:start] + section.encode() + original[end:], 'wiki index bytes changed outside selected section')
        with (ROOT / 'wiki/log.md').open('a') as stream:
            stream.write(f'\n## [2026-10-20] kg-update | PR92 source/store selected overlay\n- PR {args.pr_url}; frozen source `{args.commit}` against `{BASE}`.\n')
            for label, r in records.items():
                stream.write(f'- {label}: {SNAPSHOT}; {r["nodes"]} nodes / {r["edges"]} edges / {r["communities"]} communities; delta [{r["delta_nodes"]}, {r["delta_edges"]}], added/removed IDs {r["added_ids"]}/{r["removed_ids"]}.\n')
            stream.write(f'- {limits}\n- Prior receipt `{PRIOR}` SHA-256 `{PRIOR_SHA}`.\n- Closed runtime/evidence: {json.dumps(evidence, sort_keys=True)}. Physical approval remains FAIL_OPEN.\n')
        h.restore_automatic_snapshots(automatic)
        for members in prior['dated_snapshots'].values():
            folder = Path(next(iter(members.values()))['path']).parent
            require({child.name for child in folder.iterdir()} == set(members), 'prior named snapshot membership changed during apply')
            for row in members.values():
                require(digest(row['path']) == row['after_sha256'], 'prior named snapshot content changed during apply')
        log_path = ROOT / 'wiki/log.md'
        require(log_path.read_bytes().startswith(backups[log_path].read_bytes()), 'wiki log prefix was rewritten')
        require(h.maintained_source_snapshot() == maintained, 'maintained source inventory changed')
        require(protected_content(h) == protected, 'protected wiki content changed')
        require(not git('status', '--porcelain') and git('rev-parse', 'HEAD') == args.commit, 'source changed during KG update')
        for path, expected in prior['prior_immutable_receipts'].items():
            require(digest(path) == expected, f'inherited immutable pin changed: {path}')
        require(digest(PRIOR) == PRIOR_SHA, 'preceding receipt changed')
        result = {'schema': 'pr92_selected_source_graphify_kg_v1', 'status': 'PASS', **plan,
                  'recorded_utc': datetime.now(timezone.utc).isoformat(), 'snapshot': SNAPSHOT,
                  'corpora': records, 'private_profile_preservation': private,
                  'protected_content_before_sha256': protected, 'maintained_source_snapshot': {
                      'entry_count': len(maintained), 'before_sha256': canonical(maintained), 'verified_pre_post_equal': True},
                  'prior_immutable_receipts': prior['prior_immutable_receipts'],
                  'physical_approval': 'FAIL_OPEN', 'limitations': limits,
                  'helper_sha256': digest(__file__), 'prior_guard_helper_sha256': HELPER_SHA,
                  'derived_wiki_files': updater.WIKI_FILES,
                  'wiki_sha256': {f'wiki/{name}': digest(ROOT / 'wiki' / name) for name in updater.WIKI_FILES},
                  'automatic_snapshot_preservation': automatic,
                  'backups': {str(p): str(b) if b else None for p, b in backups.items()}}
        (OUT / 'kg_receipt.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'status': 'PASS', 'receipt': str(OUT / 'kg_receipt.json'), 'corpora': records}, indent=2))
    except BaseException as original_error:
        rollback_errors = []
        for path, backup in backups.items():
            try:
                if backup:
                    shutil.copy2(backup, path)
                    require(digest(path) == digest(backup), f'rollback content differs: {path}')
                elif path.exists():
                    path.unlink()
            except BaseException as error:
                rollback_errors.append(f'{path}: {error}')
        for directory in (ROOT, MAINT):
            dated = directory / 'graphify-out' / SNAPSHOT
            try:
                if dated.exists():
                    shutil.rmtree(dated)
            except BaseException as error:
                rollback_errors.append(f'{dated}: {error}')
        if rollback_errors:
            raise RuntimeError('KG rollback errors: ' + '; '.join(rollback_errors)) from original_error
        raise


if __name__ == '__main__':
    main()
