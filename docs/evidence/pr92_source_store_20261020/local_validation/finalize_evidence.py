#!/usr/bin/env python3
"""Freeze compact PR92 evidence only after the paired runtime receipts close."""
import ast
import gzip
import hashlib
import json
import shutil
from decimal import Decimal
from pathlib import Path

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr92_source_store_20261020/Cloud-BAL')
EVIDENCE = ROOT / 'docs/evidence/pr92_source_store_20261020'
EXE_SHA = '32a324d49366487f68ec1e6e687a465ef2533bd9163e2fe09733e83cc2272c16'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')


def graph_paths():
    tree = ast.parse(Path('/var/tmp/pr92_refresh_kg_source_store_20261020.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'GRAPH_PATHS' for t in node.targets):
            return ast.literal_eval(node.value.args[0])
    raise ValueError('missing reviewed source allowlist')


def freeze_runtime(arm):
    source = Path('/var/tmp') / f'pr92_{arm}_600s_c18_20261020'
    receipt_path = source / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if receipt['status'] not in ('COMPLETE', 'INCOMPLETE') or receipt['processing_errors']:
        raise ValueError(f'{arm}: receipt not closed cleanly')
    if receipt['executed_executable_sha256'] != EXE_SHA or not receipt['candidate_build_unchanged']:
        raise ValueError(f'{arm}: executable/build mismatch')
    if receipt['changed_staged_inputs'] or receipt['changed_original_inputs']:
        raise ValueError(f'{arm}: inputs changed')
    destination = EVIDENCE / 'c18' / arm.lower()
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('receipt.json', 'launch_provenance.json', 'preflight.json'):
        shutil.copy2(source / name, destination / name)
    ledger = source / 'run/pr87_joint_storage.raw.gz'
    if not ledger.exists():
        raise ValueError(f'{arm}: collector has not finalized storage ledger')
    rows = []
    with gzip.open(ledger, 'rt') as stream:
        for line in stream:
            values = line.split()
            if values and values[0] == 'BULK_VOLUME_ABSENCE':
                if len(values) != 6:
                    raise ValueError('malformed bulk-volume ledger row')
                rows.append({'step': int(values[1]), 'rk': int(values[2]),
                             'count': int(values[3]), 'delta_Q': values[4], 'delta_B': values[5]})
    completed = int(receipt['final_completed_step'] or 0)
    expected = [(step, rk) for step in range(1, completed + 1) for rk in (1, 2, 3)]
    actual = [(r['step'], r['rk']) for r in rows]
    suffix = actual[len(expected):]
    allowed_partial = [(completed + 1, rk) for rk in (1, 2, 3)]
    cadence_valid = (actual[:len(expected)] == expected and len(set(actual)) == len(actual))
    if receipt['status'] == 'COMPLETE':
        cadence_valid = cadence_valid and actual == expected
    else:
        cadence_valid = cadence_valid and len(suffix) <= 3 and suffix == allowed_partial[:len(suffix)]
        if suffix:
            cadence_valid = cadence_valid and receipt['maximum_seen_timestep'] == completed + 1
    if not cadence_valid:
        raise ValueError(f'{arm}: storage ledger cadence mismatch')
    for row in rows:
        dq, db = Decimal(row['delta_Q']), Decimal(row['delta_B'])
        if row['count'] == 0 and (dq != 0 or db != 0):
            raise ValueError(f'{arm}: zero-count bulk ledger has a delta')
        if row['count'] > 0 and not (dq < 0 and db < 0):
            raise ValueError(f'{arm}: joint-absence loss must be negative in both channels')
    summary = {'arm': arm, 'ledger_sha256': sha(ledger), 'rows': rows,
               'event_count': sum(r['count'] for r in rows),
               'per_event_intensive_policy_contract': {'e_Q': 'stored_Q - candidate_Q, kg/kg dry', 'e_B': 'stored_B - candidate_B, m3/kg dry', 'Q_bound': 'abs(e_Q) < rho_max*eta_B/2', 'B_bound': 'abs(e_B) < eta_B/2', 'verification': 'enforced by source predicate and pinned Intel fixture, not checked from this aggregate ledger'},
               'ledger_quantity': 'each delta_Q/delta_B is an RK-row sum of newcarrier*e_Q or newcarrier*e_B',
               'extensive_bound_rule': 'per-event bounds scale by that event positive newcarrier; this aggregate does not retain event carriers and cannot verify an extensive bound',
               'signed_delta_Q': str(sum((Decimal(r['delta_Q']) for r in rows), Decimal(0))),
               'signed_delta_B': str(sum((Decimal(r['delta_B']) for r in rows), Decimal(0))),
               'units': 'separate coupled pressure-coordinate Q and B; not kg or final endpoint loss',
               'scope': 'committed code-5 events only; ordinary rounding remains in the total storage ledger'}
    write_json(destination / 'bulk_volume_summary.json', summary)
    return {'arm': arm, 'path': (destination / 'receipt.json').relative_to(ROOT).as_posix(),
            'sha256': sha(destination / 'receipt.json'), 'status': receipt['status'],
            'returncode': receipt['returncode'], 'final_completed_step': receipt['final_completed_step'],
            'input_sha256': receipt['candidate_wrfinput_sha256'],
            'boundary_sha256': receipt['candidate_wrfbdy_sha256'],
            'preflight_sha256': sha(destination / 'preflight.json'),
            'launch_provenance_sha256': sha(destination / 'launch_provenance.json')}


def main():
    canonical = json.loads((EVIDENCE / 'local_validation/c18_canonical_validation.json').read_text())
    if not (canonical['status'] == 'PASS' and canonical['exit_code'] == 0 and
            canonical['all_frozen_file_hashes_unchanged'] and
            canonical['core_sha256'] == sha(ROOT / 'src/common/cloud_bal_joint_transport.f90') and
            canonical['fixture_sha256'] == sha(ROOT / 'tests/test_pr92_bulk_volume_policy.f90')):
        raise ValueError('current core/fixture is not bound to the passed canonical snapshot')
    if '40 passed' not in (EVIDENCE / 'local_validation/c18_new_focused.log').read_text():
        raise ValueError('current focused Python suite is not passed')
    binding = json.loads((EVIDENCE / 'local_validation/c18_generated_source_binding.json').read_text())
    if binding['status'] != 'PASS' or binding['executable_sha256'] != EXE_SHA:
        raise ValueError('current generator/build binding mismatch')
    for relative, expected in binding['source_sha256'].items():
        if sha(ROOT / relative) != expected:
            raise ValueError(f'generator binding changed: {relative}')
    runtime = [freeze_runtime(arm) for arm in ('OFF', 'COUPLED')]
    state_audits = []
    for run in runtime:
        path = EVIDENCE / 'c18/closed_runtime_20261020' / f"{run['arm'].lower()}_closed_runtime_summary.json"
        audit = json.loads(path.read_text())
        policy = audit['declared_native_ice_policy_split']
        provenance = audit['provenance']
        if (audit['runtime_status'] != run['status'] or
                audit['final_completed_step'] != run['final_completed_step'] or
                audit['processing_errors'] or provenance['receipt_sha256'] != run['sha256'] or
                provenance['candidate_executable_sha256'] != EXE_SHA or
                provenance['module_em_sha256'] != binding['generated_source_sha256']):
            raise ValueError(f"{run['arm']}: closed state audit is not bound to this runtime")
        if (policy['status'] != 'PASS' or policy['active_outlier_count'] != 0 or
                policy['strict_state_failure_count'] != 0 or
                policy['completed_states'] != 6 * run['final_completed_step']):
            raise ValueError(f"{run['arm']}: declared completed-state policy did not pass")
        state_audits.append({'arm': run['arm'], 'path': path.relative_to(ROOT).as_posix(),
                             'sha256': sha(path), 'generic_exact_source_status': audit['completed_state_audit']['status'],
                             'declared_policy': policy,
                             'scope': 'Completed cloud/rain/graupel strict source contract; ice uses declared inactive cutoff and 8-ULP active gate. Generic audit is retained separately.'})
    paths = graph_paths() + ['tests/intel_toolchain.sh',
                            'docs/evidence/pr92_source_store_20261020/c18/module_em.F',
                            'docs/evidence/pr92_source_store_20261020/graupel_store/witness/module_em_c15.F']
    paths += ['docs/evidence/pr92_source_store_20261020/c15/module_em.F',
              'docs/evidence/pr92_source_store_20261020/c16/module_em.F',
              'docs/evidence/pr92_source_store_20261020/c17/module_em.F',
              'docs/evidence/pr92_source_store_20261020/c17/core.f90',
              'docs/evidence/pr92_source_store_20261020/c17/generator.py',
              'docs/evidence/pr92_source_store_20261020/c17/instrumenter.py',
              'docs/evidence/pr92_source_store_20261020/c15/generator.py',
              'docs/evidence/pr92_source_store_20261020/c16/generator.py',
              'docs/evidence/pr92_source_store_20261020/graupel_store/policy_core_reviewed.f90',
              'docs/evidence/pr92_source_store_20261020/graupel_store/module_em_d1.F',
              'docs/evidence/pr92_source_store_20261020/historical_c14/cloud_bal_joint_transport.f90']
    logs = sorted((EVIDENCE / 'local_validation').rglob('*.log'))
    logs += [EVIDENCE / 'local_validation/canonical_snapshot_combined.log.gz',
             EVIDENCE / 'local_validation/c16_canonical_combined.log.gz',
             EVIDENCE / 'local_validation/c18_canonical_combined.log.gz']
    validation = {'schema': 'pr92_final_source_validation_v1', 'status': 'PASS',
                  'source_sha256': {p: sha(ROOT / p) for p in sorted(paths)},
                  'raw_logs': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p)} for p in logs],
                  'gates': {'current_core_and_policy': 'pinned Intel O0/O2 PASS',
                            'canonical_frozen_6372_file_snapshot': 'C18 exit 0, all hashes unchanged; see c18_canonical_validation.json',
                            'new_python_focused': '40 PASS', 'default_off_regressions': '14 PASS',
                            'historical_c14': '5 PASS'},
                  'limits': 'Canonical snapshot excludes new PR92 Python tools, tested separately; no full clean WRF build or scientific approval.'}
    write_json(EVIDENCE / 'final_validation.json', validation)
    integration = {'schema': 'pr92_source_store_integration_v1',
                   'base_commit': '71b8c1d5dae181c163d04eabac9cf8f80134f417',
                   'candidate_identity': 'PR92-C18-bounded', 'candidate_executable_sha256': EXE_SHA,
                   'validation_sha256': sha(EVIDENCE / 'final_validation.json'),
                   'closed_runtime_receipts': runtime, 'completed_state_audits': state_audits, 'physical_approval': 'FAIL_OPEN',
                   'candidate_scientific_gates': {'water_energy_closure': 'OPEN',
                                                  'native_mass_wind_balance': 'OPEN',
                                                  'independent_observation_agreement': 'OPEN',
                                                  'reduced_initialization_shock': 'OPEN'},
                   'research_layout': 'selected-object pinned Intel partial-host; 1 domain/rank/thread/tile',
                   'science_evidence_identity': 'C14 response maps; C16 history is byte-identical through T240 only; selected QC vertical source-form replay. C17 closed audit is separately bound; C18 audit is separately bound after closed receipt review.'}
    write_json(EVIDENCE / 'integration_manifest.json', integration)
    print(json.dumps({'runtime': runtime, 'validation_sha256': integration['validation_sha256']}, indent=2))


if __name__ == '__main__':
    main()
