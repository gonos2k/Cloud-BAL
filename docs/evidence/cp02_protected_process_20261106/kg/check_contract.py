#!/usr/bin/env python3
"""Check KG selection-scope mutations without staging or maintained-root writes."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile

KG = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('protected_kg', KG / 'prepare_kg.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
root = helper.SOURCE
scratch_root = root.parent / 'runtime/kg_contract_checks'
scratch_root.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=scratch_root) as temporary:
    temporary = Path(temporary)
    source_hashes = {name: helper.sha256(root / name) for name in sorted(helper.EXPECTED_SOURCE_PATHS)}
    dep = helper.STAGE_HELPER.relative_to(root).as_posix()
    review = {'status': 'PASS_SOURCE_AND_EVIDENCE_REVIEW',
              'selected_source_paths': sorted(source_hashes), 'selected_source_sha256': source_hashes,
              'hash_only_sha256': {dep: helper.sha256(helper.STAGE_HELPER)},
              'validation_summary': 'Contract test only; no source publication.',
              'science_open_items': ['No runtime or scientific conclusions are made by this test.']}
    path = temporary / 'review.json'
    def load(value):
        path.write_text(json.dumps(value))
        return helper.load_review(path)
    load(review)
    lock = {key: copy.deepcopy(review[key]) for key in ('selected_source_sha256', 'hash_only_sha256')}
    helper.validate_lock_review(lock, review)
    outcomes = []
    for label, value in [('omitted_source', copy.deepcopy(review)), ('missing_dependency', copy.deepcopy(review)),
                         ('incorrect_source_hash', copy.deepcopy(review))]:
        if label == 'omitted_source':
            omitted = value['selected_source_paths'].pop()
            value['selected_source_sha256'].pop(omitted)
        elif label == 'missing_dependency':
            value['hash_only_sha256'].clear()
        else:
            value['selected_source_sha256'][next(iter(source_hashes))] = '0' * 64
        try:
            load(value)
        except RuntimeError:
            outcomes.append(label)
        else:
            raise AssertionError(f'accepted {label}')
    for key in ('selected_source_sha256', 'hash_only_sha256'):
        changed = copy.deepcopy(lock)
        changed[key][next(iter(changed[key]))] = '1' * 64
        try:
            helper.validate_lock_review(changed, review)
        except RuntimeError:
            outcomes.append('modified_lock_' + key)
        else:
            raise AssertionError(f'accepted modified lock {key}')
    for name, operation in [('selection_lock', 'freeze'), ('stage_receipt', 'stage')]:
        link = temporary / name
        link.symlink_to(temporary / ('absent_' + name))
        if name == 'selection_lock':
            helper.SELECTION = link
            call = lambda: helper.freeze(path)
        else:
            helper.STAGE_RECEIPT = link
            call = lambda: helper.stage(temporary / 'not_a_lock.json')
        try:
            call()
        except RuntimeError:
            outcomes.append('dangling_' + name)
        else:
            raise AssertionError(f'accepted dangling {name}')
    result = {'status': 'PASS_SCOPE_AND_PRESERVATION_MUTATIONS', 'positive_checks': 2,
              'rejected_mutations': outcomes, 'mutation_count': len(outcomes),
              'prepare_helper_sha256': helper.sha256(KG / 'prepare_kg.py'),
              'maintained_roots_written': False, 'graph_stage_executed': False}
    with (KG / 'contract_regression.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'rejected_mutations': len(outcomes)}))
