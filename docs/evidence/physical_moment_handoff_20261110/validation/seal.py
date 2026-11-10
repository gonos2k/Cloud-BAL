#!/usr/bin/env python3
"""Verify and seal reviewed artifacts; graph freshness is not science validation."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/physical_moment_handoff_20261110'
STAMP = '2026-11-10-physical-moment-handoff'
PROFILE = '5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4'
NATIVE_INPUT = '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def bind(path, digest):
    path = Path(path)
    if not path.is_absolute():
        require('..' not in path.parts, 'unsafe relative path')
        path = ROOT / path
    require(path.is_file() and not path.is_symlink() and sha(path) == digest,
            'missing or changed: ' + str(path))


def read(name, status=None):
    obj = json.loads((BUNDLE / name).read_text())
    if status is not None:
        require(obj.get('status') == status, 'bad receipt status: ' + name)
    return obj


def static_checks():
    unit = read('validation/unit_receipt.json', 'PASS')
    require(unit['exit_code'] == 0 and unit['source_inputs_unchanged'] is True and
            len(unit['guarded_sha256']) == 1365, 'broad unit test scope differs')
    require(set(unit['unused_new_boundary_overlay_paths']) == {
        'tests/test_initialize_model_moments.py', 'tests/test_tier_exceptions.json',
        'tools/initialize_model_moments.py'}, 'broad test overlay exclusions differ')
    bind('tests/intel_toolchain.sh', unit['profile_sha256'])
    require(unit['profile_sha256'] == PROFILE, 'compiler profile differs')
    bind('tests/run_unit_tests.sh', unit['entry_sha256'])
    bind(BUNDLE / 'validation/unit_tests.log', unit['log_sha256'])
    for path, digest in unit['guarded_sha256'].items():
        bind(path, digest)

    focused = read('validation/focused_receipt.json', 'PASS')
    require((focused['boundary_tests'], focused['composed_cases'], focused['physics_profiles']) ==
            (11, 6, ['O0', 'O2']), 'focused test scope differs')
    require(focused['profile_sha256'] == PROFILE and len(focused['source_sha256']) == 17,
            'focused profile or source coverage differs')
    for path, digest in focused['source_sha256'].items():
        bind(path, digest)
    require(set(focused['commands']) == {'boundary', 'physics', 'rain_consumer', 'figures'},
            'focused command set differs')
    for cmd in focused['commands'].values():
        require(cmd['exit_code'] == 0, 'focused command failed')
        bind(cmd['log'], cmd['log_sha256'])
    require(set(focused['exact_figure_outputs']) == {
        '01_initialization_path.png', '02_rain_psd_freedom.png', 'rain_psd_family.csv'},
        'figure reproduction scope differs')
    for name, digest in focused['exact_figure_outputs'].items():
        bind(BUNDLE / 'figures' / name, digest)

    actual = BUNDLE / 'native/actual_real'
    inventory = read('native/actual_real/bundle_manifest.json')
    require(len(inventory['files']) == 16, 'actual-real artifact coverage differs')
    for name, item in inventory['files'].items():
        path = actual / name
        bind(path, item['sha256'])
        require(path.stat().st_size == item['bytes'], 'actual-real artifact size differs')
    plan = read('native/actual_real/plan_v2.json')
    native_manifest = read('native/actual_real/manifest_v2.json')
    require(len(plan['inputs']) == 91 and len(native_manifest['inputs']) == 91 and
            native_manifest['stage'] == 'fresh_real_before_model_launch', 'real producer scope differs')
    require('location=[1, 228, 13, 2]' in (actual / 'completion_v3.stdout').read_text(),
            'native rejection location differs')
    recount = read('native/actual_real/ice_cap_recount.json')
    require(recount['source_sha256'] == NATIVE_INPUT and recount['mask_count'] == 106128 and
            recount['all_native_ni_zero'] is True and recount['failed_fortran_ijk_slot'] == [1, 228, 13, 2],
            'native file-state recount differs')
    bind(ROOT.parent / 'native_probe_20261110/preflight_v3/wrfinput_d01', NATIVE_INPUT)
    probe_dir = ROOT.parent / 'native_probe_20261110'
    proof = read('native/actual_real_publication_check.json')
    require(set(proof['paths']) == {str(probe_dir / 'completed.nc'), str(probe_dir / 'receipt.json')} and
            all(item == {'lstat': 'absent', 'dangling_symlink': False}
                for item in proof['paths'].values()) and len(proof['bound_artifacts']) == 3 and
            proof['actual_first_use'].startswith('UNRUN:'), 'native no-publication review differs')
    for path, item in proof['bound_artifacts'].items():
        bind(path, item['sha256'])
        require(Path(path).stat().st_size == item['bytes'], 'native proof artifact size differs')
    require(not (probe_dir / 'completed.nc').exists() and not (probe_dir / 'completed.nc').is_symlink() and
            not (probe_dir / 'receipt.json').exists() and not (probe_dir / 'receipt.json').is_symlink(),
            'unexpected native completed output or receipt')

    lock = read('kg/selection_lock.json', 'FROZEN')
    require(lock['snapshot'] == STAMP and lock['review_status'] == 'GO' and
            len(lock['selected_source_sha256']) == 12 and len(lock['hash_only_sha256']) == 12,
            'KG selection scope differs')
    for mapping in ('selected_source_sha256', 'hash_only_sha256'):
        for path, digest in lock[mapping].items():
            bind(path, digest)
    for path, digest in lock['selected_source_sha256'].items():
        require(focused['source_sha256'].get(path, unit['guarded_sha256'].get(path)) == digest,
                'selected source lacks test evidence: ' + path)
    stage = read('kg/stage_receipt.json', 'STAGED_ONLY_NO_MAINTAINED_WRITES')
    review = read('kg/stage_review.json', 'GO')
    bind(BUNDLE / 'kg/selection_lock.json', stage['selection_lock_sha256'])
    bind(BUNDLE / 'kg/selection_lock.json', review['selection_lock_sha256'])
    bind(BUNDLE / 'kg/stage_receipt.json', review['stage_receipt_sha256'])
    require(stage['selected_source_sha256'] == lock['selected_source_sha256'] and
            review['prior_snapshot_count'] == 264 and review['selected_sources'] == 12 and
            review['failures'] == [] and len(review['checks']) >= 35 and all(review['checks'].values()),
            'KG stage review differs')
    require(set(stage['corpora']) == {'KLAPS50', 'Cloud-BAL'}, 'KG corpus scope differs')
    for name, corpus in stage['corpora'].items():
        require(corpus['after']['nodes'] >= corpus['before']['nodes'] and
                len(corpus['removed_selected_node_ids']) == 2 and
                all('tests_test_real_shadow_io_contract_f90_cloud_bal_' in x
                    for x in corpus['removed_selected_node_ids']) and
                set(corpus['integrity_zero_counts']) == {
                    'dangling_endpoint_edges', 'exact_duplicate_edges', 'missing_endpoint_edges',
                    'same_endpoint_group_count', 'self_loop_edges'} and
                all(v == 0 for v in corpus['integrity_zero_counts'].values()),
                'KG selected import or integrity differs: ' + name)

    science = read('review/final_science_review.json', 'PASS')
    require(science['figure_csv_rows'] == 181 and science['recount']['count'] == 106128 and
            science['recount']['source_sha256'] == NATIVE_INPUT, 'science review scope differs')
    for path, digest in science['inputs_sha256'].items():
        bind(path, digest)
    gallery = read('gallery_receipt.json', 'PASS')
    require(gallery['figures'] == 2 and len(gallery['members']) == 29 and
            gallery['zip_crc'] == 'PASS' and gallery['local_links'] == 'PASS', 'gallery scope differs')
    bind('docs/PHYSICAL_MOMENT_INITIALIZATION_20261110.md', gallery['report_sha256'])
    bind(BUNDLE / 'FIGURES.md', gallery['gallery_sha256'])
    bind(BUNDLE / 'report_figures.zip', gallery['archive_sha256'])
    bind(BUNDLE / 'validation/package_figures.py', gallery['generator_sha256'])
    with zipfile.ZipFile(BUNDLE / 'report_figures.zip') as archive:
        require(archive.testzip() is None and set(archive.namelist()) == set(gallery['members']),
                'gallery ZIP differs')
        for path, item in gallery['members'].items():
            bind(path, item['sha256'])
            data = archive.read(path)
            require(len(data) == item['size_bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'],
                    'gallery member differs: ' + path)
    prior = read('kg/prior_audit.json', 'PASS_PRIOR_3058_AND_FINAL_INDEX')
    require(prior['artifact_count'] == 3058 and len(prior['aliases']) == 5 and
            prior['maintained_roots_written'] is False, 'prior evidence scope differs')
    for path, digest in prior['aliases'].items():
        alias = BUNDLE / 'kg/prior_aliases' / path
        bind(alias, digest)
    return lock


def final_checks(lock, postpublication_only=False):
    publication = read('kg/publish_receipt.json', 'PUBLISHED_AND_READBACK_PASS')
    require(publication['snapshot'] == STAMP and
            (publication['prior_snapshot_count'], publication['new_maintained_snapshot_count']) == (264, 266) and
            len(publication['targets']) == 28, 'KG publication scope differs')
    bind(BUNDLE / 'kg/stage_review.json', publication['stage_review_sha256'])
    bind(BUNDLE / 'kg/selection_lock.json', publication['selection_lock_sha256'])
    published = {item['path']: item['sha256'] for item in publication['targets']}
    require(len(published) == 28, 'duplicate publication target')
    for path, digest in published.items():
        bind(path, digest)
    copied = read('kg/source_copy_receipt.json', 'COPIED_AND_READBACK_PASS')
    bind(BUNDLE / 'kg/publish_receipt.json', copied['publish_receipt_sha256'])
    require(copied['snapshot'] == STAMP and len(copied['targets']) == 11, 'source copy scope differs')
    copied_targets = {item['path']: item['sha256'] for item in copied['targets']}
    require(len(copied_targets) == 11 and all(published.get(k) == v for k, v in copied_targets.items()),
            'source copy and publication differ')
    for path, digest in copied_targets.items():
        bind(path, digest)
    prior = read('validation/prior_after_kg_audit.json', 'PASS')
    require((prior['artifact_count'], prior['alias_count'], prior['new_snapshot_count']) ==
            (3058, 5, 266) and set(prior['changed_current_paths']) == {
                'README.md', 'docs/CURRENT_RESEARCH_STATUS.md', 'graphify-out/graph.json',
                'graphify-out/GRAPH_REPORT.md', 'graphify-out/manifest.json'},
            'postpublication prior audit scope differs')
    bind('docs/evidence/cp02_activation_path_20261110/validation.json', prior['prior_manifest_sha256'])
    bind('docs/evidence/cp02_activation_path_20261110/review/final_index_review.json',
         prior['prior_final_index_review_sha256'])
    bind(BUNDLE / 'kg/prior_audit.json', prior['prior_audit_sha256'])
    bind(BUNDLE / 'kg/publish_receipt.json', prior['publish_receipt_sha256'])
    independent = read('kg/postpublish_independent_review.json', 'GO')
    require(independent['failures'] == [] and independent['prior_artifact_failures'] == [] and
            (independent['prior_snapshot_count'], independent['prior_artifact_count'],
             independent['prior_alias_count'], independent['frozen_source_count'],
             independent['hash_only_count'], independent['maintained_file_targets'],
             independent['worktree_copy_targets']) == (264, 3058, 5, 12, 12, 17, 11) and
            sum(independent['current_snapshot_counts'].values()) == 266 and
            len(independent['checks']) >= 14 and all(independent['checks'].values()),
            'independent publication review scope differs')
    bind(BUNDLE / 'kg/publish_receipt.json', independent['publish_receipt_sha256'])
    bind(BUNDLE / 'kg/source_copy_receipt.json', independent['source_copy_receipt_sha256'])
    bind(BUNDLE / 'kg/selection_lock.json', independent['selection_lock_sha256'])
    amendment = read('review/recipe_amendment.json', 'PASS')
    require(amendment['original_recipe'] == str((BUNDLE / 'review/recipe_versions/initial.py').relative_to(ROOT)) and
            amendment['current_recipe'] == str((BUNDLE / 'validation/tree_replay.py').relative_to(ROOT)) and
            amendment['sparse_attempt_recipe'] == str((BUNDLE / 'review/recipe_versions/sparse.py').relative_to(ROOT)) and
            amendment['original_sha256'] == independent['tree_replay_recipe_sha256'] and
            amendment['reference_source_count'] == 17 and
            set(amendment['metadata_sha256']) == {
                str((BUNDLE / 'native/actual_real_publication_check.json').relative_to(ROOT)),
                str((BUNDLE / 'native/real_probe_rejection.md').relative_to(ROOT))} and
            amendment['only_new_metadata'] == [
                str((BUNDLE / 'native/actual_real_publication_check.json').relative_to(ROOT))],
            'recipe amendment scope differs')
    for path_key, hash_key in (('original_recipe', 'original_sha256'),
                               ('current_recipe', 'current_sha256'),
                               ('sparse_attempt_recipe', 'sparse_attempt_sha256')):
        bind(amendment[path_key], amendment[hash_key])
    bind(BUNDLE / 'kg/postpublish_independent_review.json', amendment['postpublish_review_sha256'])
    bind(BUNDLE / 'validation/focused_receipt.json', amendment['reference_focused_receipt_sha256'])
    for path, digest in amendment['metadata_sha256'].items():
        bind(path, digest)
    session = read('kg/session_completion.json', 'COMPLETE_MAINTENANCE_WITH_OPEN_SCIENTIFIC_ITEMS')
    require(session['snapshot'] == STAMP and session['preserved_prior_snapshots'] == 264 and
            session['published_maintained_snapshot_count'] == 266 and
            session['prior_manifest_artifacts_preserved'] == 3058 and
            session['selected_source_sha256'] == lock['selected_source_sha256'] and
            session['hash_only_pin_count'] == 12 and len(session['open_items']) >= 4,
            'session completion scope differs')
    bind(BUNDLE / 'kg/publish_receipt.json', session['publish_receipt_sha256'])
    bind(BUNDLE / 'kg/source_copy_receipt.json', session['source_copy_receipt_sha256'])
    bind(BUNDLE / 'kg/postpublish_independent_review.json', session['postpublish_review_sha256'])
    if postpublication_only:
        return
    replay = read('validation/tree_replay_receipt.json', 'PASS')
    require((replay['unit_input_count'], replay['boundary_tests'], replay['physical_cases'],
             replay['profiles']) == (1365, 11, 6, ['O0', 'O2'])
            and replay['shared_index_unchanged'] is True, 'tree replay scope differs')
    require(replay['exact_figure_outputs'] == read('validation/focused_receipt.json')['exact_figure_outputs'],
            'tree replay figure reproduction differs')
    require(isinstance(replay['input_sha256'], dict) and set(lock['selected_source_sha256']).issubset(replay['input_sha256']),
            'tree replay input coverage differs')
    for path, digest in replay['input_sha256'].items():
        bind(path, digest)
    bind(replay['log'], replay['log_sha256'])
    final_review = read('review/final_review.json', 'PASS')
    require(isinstance(final_review.get('inputs'), dict) and len(final_review['inputs']) >= 12,
            'final review input scope differs')
    for path, digest in final_review['inputs'].items():
        bind(path, digest)



def artifacts(lock):
    names = set(lock['selected_source_sha256']) | {
        'tests/run_unit_tests.sh', 'tests/run_initialize_model_moments.sh',
        'tests/test_tier_exceptions.json', 'README.md', 'docs/CURRENT_RESEARCH_STATUS.md',
        'docs/PHYSICAL_MOMENT_INITIALIZATION_20261110.md', 'docs/MODEL_MOMENT_HANDOFF.md'}
    paths = {ROOT / name for name in names}
    paths.update(p for p in BUNDLE.rglob('*') if p.is_file() or p.is_symlink())
    snapshot = ROOT / 'graphify-out' / STAMP
    require(snapshot.is_dir(), 'dated Cloud-BAL graph missing')
    paths.update(snapshot / name for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'))
    paths.update(ROOT / 'graphify-out' / name for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'))
    excluded = {BUNDLE / 'validation.json', BUNDLE / 'review/final_index_review.json'}
    rows = []
    for path in sorted(paths):
        if path in excluded or '__pycache__' in path.parts or path.suffix in ('.pyc', '.lock'):
            continue
        require(path.is_file() and not path.is_symlink(), 'unsafe artifact: ' + str(path))
        require(path.stat().st_size < 100 * 1024**2, 'artifact exceeds size limit: ' + str(path))
        with path.open('rb') as stream:
            require(stream.read(4) != b'\x7fELF', 'binary executable belongs outside bundle')
        rows.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'size_bytes': path.stat().st_size})
    require(len(rows) > 40, 'artifact scope is unexpectedly small')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-static', action='store_true', help='read-only prepublication checks')
    parser.add_argument('--check-postpublication', action='store_true', help='read-only postpublication checks')
    args = parser.parse_args()
    lock = static_checks()
    if args.check_static:
        print('PASS_STATIC_PREPUBLICATION')
        return
    if args.check_postpublication:
        final_checks(lock, postpublication_only=True)
        print('PASS_POSTPUBLICATION')
        return
    final_checks(lock)
    output = BUNDLE / 'validation.json'
    require(not output.exists() and not output.is_symlink(), 'preserve existing manifest')
    rows = artifacts(lock)
    with output.open('x') as stream:
        json.dump({'status': 'PASS', 'schema': 'physical_moment_handoff_validation_v1',
                   'checks': {'boundary_tests': 11, 'physical_cases': 6,
                              'physical_profiles': ['O0', 'O2'], 'actual_cap_count': 106128,
                              'actual_first_use_verified': False, 'native_input_published': False,
                              'figures': 2, 'zip_members': 29, 'selected_sources': 12,
                              'prior_artifacts': 3058, 'maintained_snapshots': 266,
                              'scope': 'Fixture, source and rejection evidence only; no first-use or forecast validation.'},
                   'artifact_count': len(rows), 'artifacts': rows,
                   'excluded_self_referential': ['validation.json', 'review/final_index_review.json']},
                  stream, indent=2)
        stream.write('\n')
    print('PASS', len(rows))


if __name__ == '__main__':
    main()
