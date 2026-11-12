#!/usr/bin/env python3
"""Freeze first-call audit inputs and reproduce its tests, replay, ledgers and figures."""
import csv, hashlib, json, os, shutil, subprocess, sys, traceback
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[3]
HERE = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else ROOT.parent / 'validation_final'
if len(sys.argv) > 2:
 raise SystemExit('usage: run.py [new-workspace-output-directory]')
if HERE.is_relative_to(ROOT) or not HERE.is_relative_to(ROOT.parent):
 raise SystemExit('output must be under the workspace scratch parent and outside the source checkout')
HERE.mkdir(parents=True, exist_ok=False)
if any((HERE / p).exists() for p in ('freeze', 'work', 'logs', 'receipt.json')):
 raise SystemExit('validation destination already contains an attempt; select a new output directory')
REL = Path('docs/evidence/first_call_water_budget_20261112')
FREEZE = HERE / 'freeze' / 'Cloud-BAL'
WORK = HERE / 'work'
LOGS = HERE / 'logs'
SOURCE = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_activation_path_20261110/Cloud-BAL/docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90')
SOURCE_SHA = 'f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595'
FILES = [
 'tools/cp02_first_call_water_budget.py', 'tools/plot_first_call_water_budget.py',
 'tests/test_cp02_first_call_water_budget.py', 'tests/run_unit_tests.sh', 'tests/intel_toolchain.sh',
 'tests/fixtures/kdm6_wrapper/module_wrf_error.F', 'tests/fixtures/kdm6_wrapper/module_model_constants.F',
 'tests/fixtures/kdm6_wrapper/libmassv.F', 'tests/fixtures/kdm6_wrapper/wrf_debug_stub.f90',
 'docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90',
 'docs/evidence/ice_stage_contract_20261111/native/full/module_mp_radar.F',
 *[str(REL / p) for p in [
   'native/capturedsmallrecords/rank3.jsonl.gz', 'native/receipt.json',
   'replay/driver.f90', 'replay/input.py', 'replay/prepare.py', 'replay/compare.py', 'replay/run.sh',
   'replay/receipt.json', 'replay/results/cp04_t000001-000003_rank3.bin', 'replay/results/cp04_schema.json',
   'science/independent_column_ledger.py', 'science/independent_sediment_ledger.py',
   'science/column_ledger.json', 'science/sediment_ledger.json', 'science/stage_telescope.csv',
   'analysis/column_ledger.json', 'analysis/column_ledger.csv',
   'figures/provenance.json', 'figures/column_water.png', 'figures/stage_ledger.png']]
]
FILES.append(str(REL / 'validation/run.py'))

def sha(path):
 return hashlib.sha256(path.read_bytes()).hexdigest()

def run(label, args, env, stdout_file=None):
 with (LOGS / (label + '.log')).open('wb') as log:
  log.write(('cwd: '+str(FREEZE)+'\ncommand: '+repr(args)+'\n').encode()); log.flush()
  if stdout_file:
   with stdout_file.open('wb') as result:
    subprocess.run(args, cwd=FREEZE, env=env, stdout=result, stderr=log, check=True)
  else:
   subprocess.run(args, cwd=FREEZE, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
 commands.append({'label':label,'argv':[str(x) for x in args], 'log':str((LOGS/(label+'.log')).relative_to(HERE))})

def same(actual, expected):
 if actual.read_bytes() != expected.read_bytes(): raise ValueError(f'mismatch: {actual} versus {expected}')
 checks.append({'actual':str(actual.relative_to(HERE)), 'expected':str(expected.relative_to(HERE)), 'sha256':sha(actual)})

commands=[]; checks=[]; receipt={'status':'FAIL','source_sha256':SOURCE_SHA}
try:
 FREEZE.mkdir(parents=True); WORK.mkdir(); LOGS.mkdir()
 if sha(SOURCE) != SOURCE_SHA: raise ValueError('external replay source is not pinned CONTROL')
 original = {p:sha(ROOT/p) for p in FILES}
 for p in FILES:
  dest=FREEZE/p; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/p,dest)
 before={p:sha(FREEZE/p) for p in FILES}
 if original != before or before['docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90'] != SOURCE_SHA: raise ValueError('freeze verification failed')
 env=os.environ.copy(); env.update({'TMPDIR':str(WORK),'MPLCONFIGDIR':str(WORK/'mplconfig'),'PYTHONDONTWRITEBYTECODE':'1','MPLBACKEND':'Agg'})
 rel=FREEZE/REL; cap=rel/'native/capturedsmallrecords/rank3.jsonl.gz'; native=rel/'native/receipt.json'; source=FREEZE/'docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90'
 run('python_tests',[sys.executable,'tests/test_cp02_first_call_water_budget.py','-v'],env)
 run('intel_replay',['bash',str(rel/'replay/run.sh')],env)
 runs=list((HERE/'freeze').glob('first-row-replay.*'))
 if len(runs)!=1: raise ValueError(f'expected one fresh replay directory; got {runs}')
 replay=runs[0]
 for opt in ('O0','O2'):
  result=json.loads((replay/f'{opt}_comparison.json').read_text())
  if not result['native_word_match'] or len(result['fields'])!=29: raise ValueError(f'{opt} terminal mismatch')
  for mode in ('original','instrumented'):
   if sha(replay/f'{opt}_{mode}/terminal.bin') != '2227c80481669992a206d0f2a4c8123abf08fe1e90e6b3fedf368f48686abf81': raise ValueError(f'{opt} {mode} terminal SHA mismatch')
  same(replay/f'{opt}_instrumented/cp04_t000001-000003_rank3.bin',rel/'replay/results/cp04_t000001-000003_rank3.bin')
 run('wrapper_ledger',[sys.executable,'tools/cp02_first_call_water_budget.py',str(cap),str(WORK/'analysis'),'--row-j','72','--native-receipt',str(native),'--source',str(source)],env)
 for name in ('column_ledger.json','column_ledger.csv'): same(WORK/'analysis'/name,rel/'analysis'/name)
 run('independent_columns',[sys.executable,str(rel/'science/independent_column_ledger.py'),str(cap)],env,WORK/'independent_columns.json')
 same(WORK/'independent_columns.json',rel/'science/column_ledger.json')
 run('independent_stages',[sys.executable,str(rel/'science/independent_sediment_ledger.py'),str(cap),str(replay/'O2_instrumented/cp04_t000001-000003_rank3.bin')],env,WORK/'independent_stages.json')
 same(WORK/'independent_stages.json',rel/'science/sediment_ledger.json')
 data=json.loads((WORK/'independent_stages.json').read_text()); keys=('qv','qc','qi','qr','qs','qg')
 with (WORK/'stage_telescope.csv').open('w',newline='') as stream:
  writer=csv.writer(stream); writer.writerow(('i','j','stage',*[f'delta_{k}_kg_m2' for k in keys],'delta_total_kg_m2'))
  for row in data['telescopes']: writer.writerow((row['i'],row['j'],row['stage'],*(row['species_change_kg_m2'][k] for k in keys),row['total_change_kg_m2']))
 same(WORK/'stage_telescope.csv',rel/'science/stage_telescope.csv')
 run('figures',[sys.executable,'tools/plot_first_call_water_budget.py',str(WORK/'analysis/column_ledger.json'),str(WORK/'independent_stages.json'),str(WORK/'figures')],env)
 for name in ('column_water.png','stage_ledger.png'): same(WORK/'figures'/name,rel/'figures'/name)
 expected=json.loads((rel/'figures/provenance.json').read_text()); actual=json.loads((WORK/'figures/provenance.json').read_text())
 if expected['png_sha256'] != actual['png_sha256'] or expected['scope'] != actual['scope'] or sorted(expected['source_sha256'].values()) != sorted(actual['source_sha256'].values()): raise ValueError('figure provenance content mismatch')
 after={p:sha(FREEZE/p) for p in FILES}; original_after={p:sha(ROOT/p) for p in FILES}
 if before!=after or original!=original_after or sha(SOURCE)!=SOURCE_SHA: raise ValueError('input changed during validation')
 receipt.update({'status':'PASS','freeze_sha256_before':before,'freeze_sha256_after':after,'original_sha256_before':original,'original_sha256_after':original_after,'external_replay_source':str(SOURCE),'external_replay_source_sha256_before':SOURCE_SHA,'external_replay_source_sha256_after':sha(SOURCE),'commands':commands,'exact_comparisons':checks,'figure_provenance':'content hashes and scope match; absolute path keys differ by frozen work directory', 'native_history':'Previously recorded scoped 80-second native history equality; not rerun here. See frozen native/receipt.json.', 'replay_scratch':str(replay.relative_to(HERE))})
except Exception as exc:
 receipt.update({'error':repr(exc),'traceback':traceback.format_exc(),'commands':commands,'exact_comparisons':checks})
finally:
 (HERE/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 if receipt['status'] == 'PASS':
  shutil.copy2(HERE/'receipt.json',SCRIPT_DIR/'receipt.json')
  shutil.copytree(HERE/'logs',SCRIPT_DIR/'logs')
print(json.dumps({'status':receipt['status'],'error':receipt.get('error')}))
if receipt['status']!='PASS': sys.exit(1)
