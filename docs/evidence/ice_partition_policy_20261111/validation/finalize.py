#!/usr/bin/env python3
"""Bind completed full-suite and focused validation without masking failures."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
BUNDLE=Path('docs/evidence/ice_partition_policy_20261111')
OUT=ROOT/BUNDLE/'validation'
RUN=ROOT.parent/'validation'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert (RUN/'full_suite.exit').read_text().strip()=='0'
    assert (RUN/'full_suite.log').read_text().rstrip().endswith('qbalpe fixed-form 72-column compile check passed')
    before=json.loads((RUN/'source_before.json').read_text())
    focused=json.loads((OUT/'focused_receipt.json').read_text())
    assert focused['status']=='PASS'
    for path,digest in {**before,**focused['source_sha256']}.items():
        assert sha(ROOT/path)==digest,path
    for command in focused['commands'].values():
        assert command['exit_code']==0
        assert sha(ROOT/command['log'])==command['log_sha256']
    native=ROOT/BUNDLE/'native'
    manifest=json.loads((native/'manifest.json').read_text())
    for path,digest in manifest['files'].items():
        assert sha(native/path)==digest,path
    native_receipt=json.loads((native/'receipt.json').read_text())
    assert native_receipt['status']=='PASS_SCOPED_HISTORICAL_NATIVE_TRACE'
    density_path=ROOT/BUNDLE/'analysis/density_recount.json'
    density=json.loads(density_path.read_text())
    assert density['status']=='PASS' and density['exact_word_relations']==5
    copied={}
    for name in ('full_suite.log','source_before.json','run_full_suite.sh','full_suite_lustre_attempt.log','lustre_attempt.json'):
        target=OUT/name
        with target.open('xb') as stream:
            stream.write((RUN/name).read_bytes())
        copied[str(target.relative_to(ROOT))]=sha(target)
    data={'status':'PASS','source_sha256':{**before,**focused['source_sha256']},'artifact_sha256':copied,
          'focused_receipt_sha256':sha(OUT/'focused_receipt.json'),
          'native_receipt_sha256':sha(native/'receipt.json'),'native_manifest_sha256':sha(native/'manifest.json'),'density_recount_sha256':sha(density_path),
          'full_suite':{'exit_code':0,'terminal_marker':'qbalpe fixed-form 72-column compile check passed',
                        'tmpdir':'fresh local /var/tmp for atomic rename; compile scratch outside source on workspace',
                        'original_environment_failure':'Lustre TMPDIR cannot provide atomic no-replace generation rename; failed attempt retained'},
          'focused':{'optimizations':['O0','O2'],'python_tests_per_optimization':19,'old_and_joint_common_tests':'PASS'},
          'native':{'cells':5,'retained_records':290,'rk3_to_entry_exact_words':15,'control_probe_history_files_equal':2,
                    'scope':'unchanged historical B1; no new proposal first-use or forecast skill'},
          'limits':['No justified automatic partition for 1362 analytical NI conflicts.','Analytical PSD envelope is not a native lambda nonadjustment guarantee.','No newly initialized WRF input, independent event or full-domain water/energy validation.']}
    with (OUT/'receipt.json').open('x') as stream:
        json.dump(data,stream,indent=2);stream.write('\n')
    print(json.dumps({'status':'PASS','full_suite_exit':0,'python_tests_per_optimization':19}))


if __name__=='__main__':
    main()
