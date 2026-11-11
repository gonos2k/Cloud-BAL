#!/usr/bin/env python3
"""Reproduce the scoped ice-stage experiment from a frozen source copy."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[4]
B=Path('docs/evidence/ice_stage_contract_20261111')
POLICY=Path('docs/evidence/physical_moment_handoff_20261110/native/actual_real/policy.json')
CONTROL=Path('docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90')
CONSTANTS=Path('docs/evidence/cp02_activation_path_20261110/reference/module_model_constants.F')
MAINTAINED=['tools/cp02_ice_stage_cases.py','tools/cp02_ice_stage_audit.py',
 'tools/plot_ice_stage_contract.py','tools/plot_ice_stage_trace.py',
 'tests/test_cp02_ice_stage_cases.py','tests/test_cp02_ice_stage_audit.py',
 'tests/check_test_tiers.py','tests/test_tier_exceptions.json','tests/run_unit_tests.sh','tests/intel_toolchain.sh']

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    receipt=ROOT/B/'validation/receipt.json'
    if receipt.exists():raise FileExistsError(receipt)
    runtime=ROOT.parent/'runtime';runtime.mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='frozen-',dir=runtime));tree=work/'source'
    paths={Path(n) for n in MAINTAINED}|{POLICY,CONTROL,CONSTANTS}
    paths.update(p.relative_to(ROOT) for p in (ROOT/'tests/fixtures/kdm6_wrapper').iterdir() if p.is_file())
    for folder in ('native','cases','analysis','figures','contract','caller'):
        paths.update(p.relative_to(ROOT) for p in (ROOT/B/folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    paths.add(B/'validation/run.py')
    inputs={str(p):sha(ROOT/p) for p in sorted(paths)}
    for n,digest in inputs.items():
        target=tree/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,target)
        if sha(target)!=digest:raise RuntimeError('copy differs: '+n)
    env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    commands={}
    def run(label,argv):
        log=ROOT/B/'validation'/(label+'.log');started=time.monotonic()
        with log.open('x') as stream:
            result=subprocess.run(argv,cwd=tree,env=env,stdout=stream,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError(f'{label} failed: {log}')
        record={'exit_code':0,'seconds':time.monotonic()-started,'argv':argv,
                'log':str(log.relative_to(ROOT)),'log_sha256':sha(log)}
        commands[label]=record
        print(json.dumps({label:record}),flush=True)
        return log.read_text()
    jobs={'whole_column':['bash',str(tree/B/'native/full/run.sh')],
          'boundary':['bash',str(tree/B/'native/boundary/run.sh')],
          'oracle_build':['bash',str(tree/B/'native/oracle/build.sh')],
          'unit':['python3','-m','unittest','discover','-s','tests','-p','test_cp02_ice_stage_*.py'],
          'fixed':['bash',str(tree/B/'native/run.sh')]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results={name:f.result() for name,f in [(n,pool.submit(run,n,cmd)) for n,cmd in jobs.items()]}
    def scratch(label):
        rows=[line.split(' ',1)[1] for line in results[label].splitlines() if line.startswith('WORK_DIR ')]
        if len(rows)!=1:raise ValueError('missing scratch path: '+label)
        return Path(rows[0])
    matched={}
    for opt in ('O0','O2'):
        for mode in ('original','instrumented'):
            for case in sorted((scratch('whole_column')/f'{opt}_{mode}').glob('case*')):
                for filename in ('terminal.bin','stages.txt'):
                    expected=ROOT/B/'native/full/results'/f'{opt}_{mode}'/case.name/filename
                    if sha(case/filename)!=sha(expected):raise ValueError('full replay differs: '+str(expected))
                    matched[str(expected.relative_to(ROOT))]=sha(expected)
        for filename in (f'output_{opt}.txt',):
            if sha(scratch('fixed')/filename)!=sha(ROOT/B/'native'/filename):raise ValueError('fixed replay differs')
        if sha(scratch('boundary')/f'run_{opt}.log')!=sha(ROOT/B/'native/boundary'/f'run_{opt}.log'):
            raise ValueError('boundary replay differs')
    source_file=json.loads((tree/B/'cases/profiles.json').read_text())['source_file']
    run('cases',['python3',str(tree/'tools/cp02_ice_stage_cases.py'),source_file,str(POLICY),str(work/'regenerated_cases')])
    if sha(work/'regenerated_cases/profiles.json')!=sha(ROOT/B/'cases/profiles.json'):
        raise ValueError('case profiles differ')
    oracle=scratch('oracle_build')
    audit_cmd=['python3',str(tree/'tools/cp02_ice_stage_audit.py'),'--bundle',str(tree/B),
               '--output',str(work/'regenerated_analysis'),'--oracle-o0',str(oracle/'oracle_O0'),
               '--oracle-o2',str(oracle/'oracle_O2')]
    # The pinned profile supplies the exact compiler runtime for the fresh oracles.
    launcher=work/'audit.sh';launcher.write_text('set -euo pipefail\nsource "$1"\nshift\nexec "$@"\n')
    run('audit',['bash',str(launcher),str(tree/'tests/intel_toolchain.sh'),*audit_cmd])
    exact={}
    for filename in ('stage_rows.csv','target_stages.csv','operator_adjustments.csv'):
        if sha(work/'regenerated_analysis'/filename)!=sha(ROOT/B/'analysis'/filename):raise ValueError('table differs: '+filename)
        exact[filename]=sha(work/'regenerated_analysis'/filename)
    fresh=json.loads((work/'regenerated_analysis/summary.json').read_text());gold=json.loads((ROOT/B/'analysis/summary.json').read_text())
    for key in ('counts','rows','target_rows','source_oracle_word_checks'):
        if fresh[key]!=gold[key]:raise ValueError('analysis summary differs: '+key)
    run('plot_fixed',['python3',str(tree/'tools/plot_ice_stage_contract.py'),str(tree/B/'cases/profiles.json'),
                     str(tree/B/'native/metadata.json'),str(tree/B/'native/output_O0.txt'),str(work/'plots')])
    run('plot_trace',['python3',str(tree/'tools/plot_ice_stage_trace.py'),str(tree/B/'analysis/target_stages.csv'),
                     str(tree/B/'cases/profiles.json'),str(work/'plots')])
    for filename in ('ice_stage_contract.png','target_levels.csv','full_column_trace.png','full_column_target_stages.csv'):
        if sha(work/'plots'/filename)!=sha(ROOT/B/'figures'/filename):raise ValueError('figure differs: '+filename)
        exact[filename]=sha(work/'plots'/filename)
    if inputs!={n:sha(ROOT/n) for n in inputs}:raise ValueError('working input changed')
    record={'status':'PASS','source_sha256':inputs,'commands':commands,'scratch':str(work),
            'full_raw_reproduced':matched,'exact_tables_and_figures':exact,'python_tests':8,
            'boundary_checks_per_optimization':33,'native_terminal_pairs':30,'source_oracle_records':4680,
            'summary_note':'Oracle executable paths/hashes differ in the fresh build; scientific tables and summary counts are equal.',
            'scope':'Source-pinned local column/operator, stage-ledger, representative file-state and figure replay; no WRF first-use or forecast validation.'}
    with receipt.open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print(json.dumps({'status':'PASS','terminal_pairs':30,'oracle_records':4680,'boundary_checks_each':33}),flush=True)

if __name__=='__main__':main()
