#!/usr/bin/env python3
"""Seal reviewed pulse diagnostics and a controlled numerical sensitivity forecast."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
B = ROOT / 'docs/evidence/cp02_pulse_path_20261110'
SOURCES = ('tools/cp02_pulse_path.py', 'tests/test_cp02_pulse_path.py',
           'tools/plot_cp02_pulse_path.py')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(name, statuses):
    path = B / name
    require(path.is_file() and not path.is_symlink(), 'missing receipt: ' + name)
    result = json.loads(path.read_text())
    actual = result.get('decision', result.get('status')) if name.startswith('review/') else result.get('status')
    require(actual in statuses, 'incomplete receipt: ' + name)
    return result


def bind(path, expected):
    path = Path(path)
    if not path.is_absolute():
        require('..' not in path.parts, 'unsafe artifact path')
        path = ROOT / path
    require(path.is_file() and not path.is_symlink() and sha(path) == expected,
            'changed artifact: ' + str(path))


def output_receipt(folder):
    receipt = read(folder + '/receipt.json', ('COMPLETE',))
    for name, expected in receipt['outputs'].items():
        bind(B / folder / name, expected)
    return receipt


def verify():
    clean = read('validation/clean_export.json', ('PASS',))
    require(clean['passed'] == clean['expected_tests'] == 514 and clean['exit_code'] == 0
            and clean['source_inputs_unchanged'], '514-test related suite required')
    for name in SOURCES:
        bind(name, clean['overlay_sha256'][name])
    for name, expected in clean['guarded_source_input_sha256'].items():
        bind(name, expected)
    for folder in ('analysis', 'figures', 'evaluation/results', 'evaluation/figures', 'evaluation/hourly_maps'):
        output_receipt(folder)
    policy = read('experiment_policy.json', ('FROZEN_BEFORE_FORECAST_EVALUATION',))
    expected_protection = [{'lead_hour': h, 'threshold_mm': t, 'baseline': 'IMPROVED_BG_FIXED'}
                           for h in range(1, 7) for t in (.1, .5, 1., 2.5, 5., 10.) if h == 1 or t == 5.]
    expected_recovery = [{'lead_hour': h, 'threshold_mm': t, 'baseline': 'ORIGINAL'}
                         for h in range(2, 7) for t in (.1, .5, 1.)]
    require(policy['admission']['protection'] == expected_protection and
            policy['admission']['recovery'] == expected_recovery and
            policy['thresholds_mm'] == [.1, .5, 1., 2.5, 5., 10.] and
            policy['lead_hours'] == [1, 2, 3, 4, 5, 6], 'admission policy changed')
    proof = read('forecast/proof/comparability.json', ('PASS',))
    require(proof['schema'] == 'cp02_pulse_substeps_comparability_v1', 'proof schema differs')
    require(len(proof['control_history_comparison']) == 7 and
            all(r['byte_equal'] for r in proof['control_history_comparison']) and
            proof['candidate_initial_history']['byte_equal'], 'forecast reproduction incomplete')
    bind(B / 'experiment_policy.json', proof['policy']['sha256'])
    bind(B / 'forecast/launch_plan.json', proof['plan']['sha256'])
    control = B / 'forecast/source/CONTROL.f90'
    candidate = B / 'forecast/source/MP10.f90'
    before, after = control.read_text(), candidate.read_text()
    original = 'real, parameter, private :: dtcldcr = 120.'
    require(before.count(original) == 1 and after == before.replace(original, original.replace('120.', '10.')),
            'candidate must change only the intended timestep parameter')
    require(sha(control) == 'c2e90bcc04b0f8fac2224c24124cbac0f5fbf0916ee91f679759e5bbb55bfcc2',
            'PR154 source differs')
    probe = read('forecast/loop_probe_receipt.json', ('PASS',))
    require(probe['compiler_sha256'] == '909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef',
            'loop probe compiler differs')
    bind(B / 'forecast/loop_probe.py', probe['probe_sha256'])
    for case, count, dt in (('CONTROL', 1, 20.), ('MP10', 2, 10.)):
        observed = probe['variants'][case]
        require((observed['loops'], observed['iterations'], observed['dtcld_seconds'],
                 observed['elapsed_microphysics_seconds']) == (count, count, dt, 20.),
                'source-derived schedule differs')
        bind(B / 'forecast/source' / (case + '.f90'), observed['source_sha256'])
    provenance = read('forecast/proof/artifact_manifest.json', ('PASS',))
    for name, expected in provenance['artifacts'].items():
        bind(B / 'forecast/proof' / name, expected['sha256'])
        require((B / 'forecast/proof' / name).stat().st_size == expected['size_bytes'],
                'forecast provenance size differs')
    evaluation = output_receipt('evaluation/results')
    require(evaluation['counts'] == {'categorical': 180, 'continuous': 30, 'constraints': 52,
                                   'transitions': 48, 'bands': 1176, 'weak_detection': 60},
            'evaluation coverage differs')
    verdict = json.loads((B / 'evaluation/results/verdict.json').read_text())
    require(verdict['FIRST_ICE_VELOCITY'] == {'passed_constraints': 21, 'required_constraints': 26},
            'frozen PR154 decision differs')
    require(set(verdict) == {'MP10', 'FIRST_ICE_VELOCITY'} and
            verdict['MP10'] == {'passed_constraints': 22, 'required_constraints': 26}, 'candidate decision scope differs')
    report = ROOT / 'docs/CP02_PULSE_PATH_AND_SUBSTEPS_20261110.md'
    require('FINAL_FORECAST_RESULTS' not in report.read_text(), 'report still a draft')
    for name in ('native_review', 'compact_figures_review', 'forecast_score_review',
                 'report_review', 'report_gallery_review'):
        review = read('review/' + name + '.json', ('PASS', 'PASS_WITH_LIMITATIONS'))
        for path, expected in review.get('inputs', {}).items():
            bind(path, expected)
    for name, decision in (('forecast_prebuild', 'GO_FOR_BUILD_ONLY'),
                           ('forecast_prelaunch', 'GO_FOR_NUMERICAL_SENSITIVITY_LAUNCH')):
        evidence = read('review/' + name + '.json', (decision,))
        for path, expected in evidence.get('inputs', {}).items():
            bind(path, expected)
    replay = read('validation/tree_replay_receipt.json', ('PASS',))
    require(replay['focused_tests_passed'] == 11 and replay['shared_index_unchanged'],
            'focused replay scope/index differs')
    bind(B / 'validation/tree_replay.py', replay['replay_script']['sha256'])
    require({name: len(rows) for name, rows in replay['byte_identical_outputs'].items()} ==
            {'analysis': 5, 'figures': 10, 'native': 4, 'scores': 8,
             'evaluation_figures': 3, 'hourly_maps': 7}, 'replay output inventory differs')
    for name, item in replay['overlay_files'].items():
        bind(name, item['sha256'])
        require((ROOT / name).stat().st_size == item['size_bytes'], 'replay input size differs')
    read('kg/prior_audit.json', ('PASS_PRIOR_435_AND_INDEX_PRESERVED',))
    read('kg/stage_review.json', ('GO',))
    read('kg/publish_receipt.json', ('PUBLISHED_AND_READBACK_PASS',))
    read('kg/postpublish_copy_receipt.json', ('PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK',))
    return {'related_tests': 514, 'new_tests': 11, 'native_points': [19145, 19144, 17804],
            'forecast_control_history_byte_equal': 7, 'candidate_initial_history_byte_equal': True,
            'candidate': 'MP10', 'candidate_verdict': verdict['MP10'],
            'fixed_admission_conditions': 26,
            'sensitivity_scope': 'Complete internal integration sequence; outer dynamics step unchanged.',
            'internal_runtime_loop_timing_observed': False,
            'full_scheme_isolated_state_carry_test_complete': False,
            'global_water_energy_budget_closed': False,
            'portable_replay_scope': replay['scope']}


def artifacts():
    paths = {ROOT / name for name in SOURCES}
    paths.update(ROOT / name for name in ('README.md', 'docs/CURRENT_RESEARCH_STATUS.md',
                                         'docs/CP02_PULSE_PATH_AND_SUBSTEPS_20261110.md'))
    paths.update(p for p in B.rglob('*') if p.is_file() or p.is_symlink())
    paths.update((ROOT / 'graphify-out/2026-11-10-pulse-path').glob('*'))
    paths.update(ROOT / 'graphify-out' / name for name in ('graph.json', 'GRAPH_REPORT.md', 'manifest.json'))
    excluded = {B / 'validation.json', B / 'review/final_index_review.json'}
    rows = []
    for path in sorted(paths):
        if path in excluded or '__pycache__' in path.parts or path.suffix in ('.pyc', '.lock'):
            continue
        require(path.is_file() and not path.is_symlink(), 'unsafe artifact: ' + str(path))
        require(path.stat().st_size < 100 * 1024 ** 2, 'artifact exceeds100MiB')
        with path.open('rb') as stream:
            require(stream.read(4) != b'\x7fELF', 'ELF must remain external')
        rows.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'size_bytes': path.stat().st_size})
    return rows


if __name__ == '__main__':
    out = B / 'validation.json'
    require(not out.exists() and not out.is_symlink(), 'preserve existing manifest')
    checks = verify()
    rows = artifacts()
    out.write_text(json.dumps({'status': 'PASS', 'schema': 'cp02_pulse_path_validation_v1',
                              'checks': checks, 'artifact_count': len(rows), 'artifacts': rows,
                              'excluded_self_referential': ['validation.json', 'review/final_index_review.json']},
                             indent=2) + '\n')
    print(json.dumps({'status': 'PASS', 'artifact_count': len(rows)}))
