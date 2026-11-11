#!/usr/bin/env python3
"""Attach completed regression evidence to the unpublished derived wiki stage."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
KG=Path(__file__).resolve().parent
BUNDLE=KG.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    validation=BUNDLE/'validation/receipt.json'
    assert json.loads(validation.read_text())['status']=='PASS'
    path=KG/'stage_receipt.json'
    original=path.read_bytes()
    receipt=json.loads(original)
    assert receipt['status']=='STAGED_ONLY_NO_MAINTAINED_WRITES'
    assert not (KG/'stage_review.json').exists() and not (KG/'publish_receipt.json').exists()
    lock=json.loads((KG/'selection_lock.json').read_text())
    for name,digest in {**lock['selected_source_sha256'],**lock['hash_only_sha256']}.items():
        assert sha(ROOT/name)==digest,name
    stage=Path(receipt['stage'])
    log=stage/'wiki/log.md'
    assert sha(log)==receipt['staged_wiki_sha256']['log.md']
    with (KG/'stage_receipt_initial.json').open('xb') as stream:
        stream.write(original)
    with log.open('a') as stream:
        stream.write('\n### Completed ice-partition validation before publication\n\n')
        stream.write('- Full pinned Intel unit suite: exit 0 through the fixed-form 72-column compile marker.\n')
        stream.write('- Focused O0/O2 joint/old completion and 19 file-adapter tests per optimization passed.\n')
        stream.write(f'- Final validation receipt SHA-256: `{sha(validation)}`. The earlier staging-pending note is superseded.\n')
        stream.write('- New-proposal first WRF use, physical treatment of 1,362 analytical conflicts and forecast generalization remain open.\n')
    receipt['staged_wiki_sha256']['log.md']=sha(log)
    receipt['validation_completed_before_publication_sha256']=sha(validation)
    receipt['initial_stage_receipt_sha256']=hashlib.sha256(original).hexdigest()
    path.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    result={'status':'PASS','initial_stage_receipt_sha256':sha(KG/'stage_receipt_initial.json'),
            'stage_receipt_sha256':sha(path),'validation_receipt_sha256':sha(validation),
            'changed_derived_file':'wiki/log.md','scope':'No graph or selected source change; no maintained writes.'}
    with (KG/'stage_completion_validation.json').open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print('PASS: final validation attached to isolated wiki stage')


if __name__=='__main__':
    main()
