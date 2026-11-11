#!/usr/bin/env python3
"""Bind this reviewed change set to the files that will be staged."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path('docs/evidence/moment_feasibility_20261111')
MANIFEST = BUNDLE/'ARTIFACT_MANIFEST.json'
INDEX_REVIEW = BUNDLE/'review/final_index_review.json'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    output = ROOT/MANIFEST
    if output.exists():
        raise FileExistsError(output)
    validation = json.loads((ROOT/BUNDLE/'validation/validation_receipt.json').read_text())
    assert validation['status']=='PASS'
    for name,expected in validation['source_sha256'].items():
        assert sha(ROOT/name)==expected, f'validated input changed: {name}'
    for record in validation['commands'].values():
        assert record['exit_code']==0
        assert sha(ROOT/record['log'])==record['log_sha256']
    review = json.loads((ROOT/BUNDLE/'review/temperature_independent_review.json').read_text())
    assert review['status']=='PASS'
    changed = subprocess.check_output(['git','diff','--name-only','-z','HEAD'],cwd=ROOT).split(b'\0')
    untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=ROOT).split(b'\0')
    paths = {Path(name.decode()) for name in changed+untracked if name}
    paths.update(p.relative_to(ROOT) for p in (ROOT/BUNDLE).rglob('*') if p.is_file())
    paths.discard(MANIFEST);paths.discard(INDEX_REVIEW)
    paths = sorted(p for p in paths if '__pycache__' not in p.parts and p.suffix!='.pyc')
    records = {}
    for name in paths:
        path = ROOT/name
        assert path.is_file() and not path.is_symlink(), f'unsupported artifact: {name}'
        records[str(name)] = {'sha256':sha(path),'bytes':path.stat().st_size,
                              'mode':'100755' if path.stat().st_mode & 0o111 else '100644'}
    receipt = {'status':'PASS','base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
               'artifacts':records,'excluded':[str(MANIFEST),str(INDEX_REVIEW)],
               'scope':'Changed implementation, scientific evidence, reviewed validation, and separately dated graph artifacts. No WRF forecast or actual first-use claim.'}
    with output.open('x') as stream:
        stream.write(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'PASS','artifacts':len(records)}))


if __name__=='__main__':
    main()
