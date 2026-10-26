#!/usr/bin/env python3
"""Retarget the pinned C2 diagnostic selectors; leave every other byte intact."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import pr92_diffusion_producer_capture as producer
import pr99_group_failure_trace as group

BASE = Path('/var/tmp/pr99_bulk_candidate_native_c2_20261022/source/overrides/module_em.F')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(output):
    original = BASE.read_text()
    targeted = group.retarget_generated_source(original, timestep=39, rk=2)
    targeted = producer.retarget_producer(targeted, timestep=39, rk=1, cells=((2, 219, 13),))
    # Independently enumerate the only five permissible replacements.
    replacements = [
        ('group_failure_enabled=itimestep==32', 'group_failure_enabled=itimestep==39 .AND. rk==2'),
        ('IF (.NOT.feasible .AND. itimestep==32 .AND. pr99_cell>0)',
         'IF (.NOT.feasible .AND. itimestep==39 .AND. rk==2 .AND. pr99_cell>0)'),
        ('IF (itimestep==32 .AND. pr99_cell>0)',
         'IF (itimestep==39 .AND. rk==2 .AND. pr99_cell>0)'),
        (producer._target_declaration(producer.TARGETS),
         producer._target_declaration(((2, 219, 13),))),
        ('IF (all_pair_diffusion_identity(1)==15) THEN',
         'IF (all_pair_diffusion_identity(1)==39.AND.rk_step==1) THEN'),
    ]
    expected = original
    for before, after in replacements:
        if expected.count(before) != 1:
            raise ValueError('nonunique diagnostic replacement')
        expected = expected.replace(before, after, 1)
    if targeted != expected:
        raise ValueError('transformation changed bytes outside the declared selectors')
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'module_em.F'
    source.write_text(targeted)
    diff = output / 'module_em.diff'
    diff.write_text(''.join(difflib.unified_diff(original.splitlines(True), targeted.splitlines(True),
                                               fromfile='C2/module_em.F', tofile='T39/module_em.F')))
    proof = {
        'schema': 'pr107_t39_source_transform_proof_v1',
        'base_source_path': str(BASE), 'base_source_sha256': digest(original.encode()),
        'edited_source_sha256': digest(targeted.encode()),
        'math_source_unchanged': True, 'changed_compiled_members': ['module_em.o'],
        'allowed_replacements': [{'before': a, 'after': b} for a, b in replacements],
        'producer_target': {'timestep': 39, 'rkstep': 1, 'cell_ijk': [2, 219, 13]},
        'group_target': {'timestep': 39, 'rkstep': 2},
        'diff_path': str(diff.resolve()), 'diff_sha256': digest(diff.read_bytes()),
        'helpers': [{'path': str(Path(m.__file__).resolve()),
                     'sha256': digest(Path(m.__file__).read_bytes())} for m in (producer, group)],
        'generator_sha256': digest(Path(__file__).read_bytes()),
    }
    (output / 'proof.json').write_text(json.dumps(proof, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'source': str(source), 'source_sha256': proof['edited_source_sha256'],
                      'proof': str(output / 'proof.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    prepare(parser.parse_args().output.resolve())
