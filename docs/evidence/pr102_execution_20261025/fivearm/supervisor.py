from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import sys

REPO = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr102_wind_structure_20261025/Cloud-BAL')
RUN = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr102_native_structure640_20261025/STRUCTURED640_RUN')
PREFLIGHT = REPO / 'docs/evidence/pr102_execution_20261025/preflight.json'
GO = Path('/var/tmp/pr102_root_postclosure_go_20261026.json')
TASK = sys.argv[1]
SCRIPTS = {
    'response': (REPO / 'tools/pr102_response.py', '9e30de564c85b5cfdbb8c9141d3f86f68d2958582892c62ad7578c77affe866e'),
    'fivearm': (Path('/var/tmp/pr102_fivearm_history_readback_v2_final_20261025.py'), 'b7ea35ac1ddd6bdc9d1b87ce6cb7ff39e1bac22c8f91f4de6bec32717685a3b1'),
}
SCRIPT, EXPECTED = SCRIPTS[TASK]
OUT = Path('/var/tmp') / ('pr102_postclosed_' + TASK + '_20261026')
OUT.mkdir(exist_ok=False)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

pins = {str(SCRIPT): EXPECTED, str(GO): '1893acf1f6853cc41674a3843f8f3e0103ac6db3c5676b2d909a5d50b54ca5ad',
        str(RUN / 'receipt.json'): '313295e9cbf9e30a12a437c501bf3db2cf25c0e6762ec5d51c31d54ba311d4d6',
        str(PREFLIGHT): 'c58feba119b7c774dc2b37e416bb6a46d49cdadfba104c7ef5c469faf5592dea'}
before = {path: digest(path) for path in pins}
if before != pins:
    raise RuntimeError('postclosure reader authorization/source pin changed')
common = ['--run-root', str(RUN), '--execution-preflight', str(PREFLIGHT)]
tail = ['--output', str(OUT / 'response.json')] if TASK == 'response' else ['--output-dir', str(OUT / 'products')]
command = [sys.executable, str(SCRIPT), *common, *tail]
record = {'status': 'RUNNING', 'command': command, 'cwd': str(OUT),
          'started_at': datetime.datetime.now().astimezone().isoformat(), 'pins_before': before,
          'supervisor_sha256': digest(__file__), 'task': TASK}
(OUT / 'execution.json').write_text(json.dumps(record, indent=2) + '\n')
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MPLCONFIGDIR=str(OUT / 'matplotlib'))
with (OUT / 'run.log').open('xb') as stream:
    child = subprocess.run(command, cwd=OUT, env=env, stdout=stream, stderr=subprocess.STDOUT)
after = {path: digest(path) for path in pins}
record.update(returncode=child.returncode, pins_after=after,
              finished_at=datetime.datetime.now().astimezone().isoformat(),
              status='COMPLETE' if child.returncode == 0 and after == before else 'FAILED',
              products={str(p.relative_to(OUT)): digest(p) for p in OUT.rglob('*') if p.is_file() and p.name != 'execution.json'})
(OUT / 'execution.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({'task': TASK, 'status': record['status'], 'returncode': child.returncode,
                  'execution': str(OUT / 'execution.json'), 'sha256': digest(OUT / 'execution.json')}))
sys.exit(0 if record['status'] == 'COMPLETE' else 1)
