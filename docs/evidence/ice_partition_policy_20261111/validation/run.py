#!/usr/bin/env python3
"""Rebuild focused native tests from frozen inputs in fresh scratch."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[4]
BUNDLE=Path('docs/evidence/ice_partition_policy_20261111')
PATHS=['src/common/cloud_bal_state.f90','src/common/cloud_bal_microphysics_initialization.f90',
       'tools/model_moment_driver.f90','tools/initialize_model_moments.py',
       'tests/test_microphysics_initialization.f90','tests/test_ice_snow_initialization.f90',
       'tests/test_initialize_model_moments.py','tests/intel_toolchain.sh',
       'tests/run_ice_snow_initialization.sh','tests/run_initialize_model_moments.sh','tests/run_unit_tests.sh',
       'tools/plot_ice_partition_handoff.py',
       'docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90',
       str(BUNDLE/'native/file_values.json'),str(BUNDLE/'native/capturedsmallrecords/rank3.jsonl'),
       str(BUNDLE/'native/capturedsmallrecords/rank7.jsonl'),str(BUNDLE/'validation/run.py')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    frozen=Path(tempfile.mkdtemp(prefix='frozen-',dir=ROOT.parent/'validation'))
    source=frozen/'source'
    pins={name:sha(ROOT/name) for name in PATHS}
    for name in PATHS:
        target=source/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,target)
        assert sha(target)==pins[name]
    output=ROOT/BUNDLE/'validation'
    commands={}
    for profile in ('O0','O2'):
        work=frozen/profile
        work.mkdir()
        flags='CLOUD_BAL_FREE_FLAGS' if profile=='O0' else 'CLOUD_BAL_REPRO_FLAGS'
        script=f'''set -euo pipefail
source "{source}/tests/intel_toolchain.sh"
cd "{work}"
for name in test_microphysics_initialization test_ice_snow_initialization; do
 "$CLOUD_BAL_FC" "${{{flags}[@]}}" "{source}/src/common/cloud_bal_state.f90" "{source}/src/common/cloud_bal_microphysics_initialization.f90" "{source}/tests/$name.f90" -o "$name"
 "./$name"
done
"$CLOUD_BAL_FC" "${{{flags}[@]}}" "{source}/src/common/cloud_bal_state.f90" "{source}/src/common/cloud_bal_microphysics_initialization.f90" "{source}/tools/model_moment_driver.f90" -o model_moment_driver
MODEL_MOMENT_DRIVER="{work}/model_moment_driver" python3 -m unittest discover -s "{source}/tests" -p test_initialize_model_moments.py
'''
        script_path=work/'run.sh'
        script_path.write_text(script)
        log=output/(profile+'.log')
        started=time.monotonic()
        with log.open('xb') as stream:
            process=subprocess.run(['bash',str(script_path)],cwd=source,stdout=stream,stderr=subprocess.STDOUT,
                                   env={**os.environ,'TMPDIR':str(ROOT.parent/'runtime/tmp')})
        commands[profile]={'exit_code':process.returncode,'log':str(log.relative_to(ROOT)),
                           'log_sha256':sha(log),'seconds':time.monotonic()-started,'scratch_script':str(script_path)}
        if process.returncode:
            raise RuntimeError(f'{profile} validation failed; see {log}')
    plots=frozen/'plots'
    subprocess.run(['python3','tools/plot_ice_partition_handoff.py',str(BUNDLE/'native'),str(plots)],cwd=source,check=True)
    reproduced={}
    for name in ('native_handoff.csv','native_handoff.png'):
        expected=ROOT/BUNDLE/'figures'/name
        assert sha(plots/name)==sha(expected)
        reproduced[name]=sha(expected)
    for name,digest in pins.items():
        assert sha(ROOT/name)==digest,name
    receipt={'status':'PASS','source_sha256':pins,'commands':commands,'scratch':str(frozen),
             'optimizations':['O0','O2'],'python_tests_per_optimization':19,
             'checks':['existing common completion','new atomic QI/QS/NI completion','final file and corruption/rollback cases'],
             'reproduced':reproduced,
             'scope':'Frozen-source common/adapter fixtures and deterministic selected historical native plot; not a new initialized WRF input or forecast test.'}
    with (output/'focused_receipt.json').open('x') as stream:
        json.dump(receipt,stream,indent=2);stream.write('\n')
    print(json.dumps({'status':'PASS','scratch':str(frozen),'python_tests_per_optimization':19}))


if __name__=='__main__':
    main()
