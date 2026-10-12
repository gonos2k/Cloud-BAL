#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if (($# != 2)); then
  printf 'usage: %s CANDIDATE_EXE NEW_RUN_ROOT\n' "$0" >&2
  exit 2
fi
executable=$1
run_root=$2
if [[ -e "$run_root" || -L "$run_root" ]]; then
  printf 'refusing to reuse run root: %s\n' "$run_root" >&2
  exit 2
fi
input_run=${PR82_NATIVE_INPUT_RUN:-/var/tmp/pr81_native_ksas_smallstep_run1/run}
case_copy=$repo_root/tests/pr81_native_case_copy.py
copy_utility=$repo_root/tools/run_isolated_native.py
case_copy_sha=$(sha256sum "$case_copy" | cut -d' ' -f1)
copy_utility_sha=$(sha256sum "$copy_utility" | cut -d' ' -f1)
PR81_NATIVE_INPUT_RUN=$input_run PR81_NATIVE_EXE=$executable \
  "$repo_root/tests/run_pr81_native_first_step.sh" "$run_root"
python3 - "$repo_root" "$input_run" "$run_root" "$case_copy_sha" "$copy_utility_sha" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
repo, input_run, run_root = map(Path, sys.argv[1:4])
expected = dict(zip((str(repo/'tests/pr81_native_case_copy.py'), str(repo/'tools/run_isolated_native.py')), sys.argv[4:6], strict=True))
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
post = {str(p):sha(p) for p in (repo/'tests/pr81_native_case_copy.py', repo/'tools/run_isolated_native.py')}
if expected != post: raise SystemExit('run helper changed during native execution')
pre_path = run_root/'pr82_run_helpers_pre.json'
with pre_path.open('x') as stream:
    stream.write(json.dumps(expected, indent=2, sort_keys=True) + '\n')
snapshot = json.loads((run_root/'source_snapshot.json').read_text())
if snapshot.get('pre') != snapshot.get('post') or snapshot.get('unchanged') is not True:
    raise SystemExit('input-case snapshot is not unchanged')
raw = run_root/'run/number_basis_rejection.raw'
if not raw.is_file(): raise SystemExit('shared rejection trace missing')
receipt = {'schema':'pr82_native_number_trace_run_v1', 'run_root':str(run_root),
           'input_run':str(input_run), 'copy_helper_sha256':expected[str(repo/'tests/pr81_native_case_copy.py')],
           'copy_utility_sha256':expected[str(repo/'tools/run_isolated_native.py')],
           'source_input_file_count':len(snapshot['pre']),
           'source_snapshot_sha256':sha(run_root/'source_snapshot.json'),
           'source_snapshot_unchanged':True,
           'rejection_trace_path':str(raw),'rejection_trace_sha256':sha(raw),
           'run_status':json.loads((run_root/'run_status.json').read_text()),
           'run_command':json.loads((run_root/'run_command.json').read_text())}
receipt['candidate_executable_sha256'] = receipt['run_command']['candidate_executable_sha256']
receipt['candidate_executable_path'] = receipt['run_command']['candidate_executable_path']
with (run_root/'pr82_native_run.json').open('x') as f: json.dump(receipt, f, indent=2); f.write('\n')
print(run_root/'pr82_native_run.json')
PY
python3 "$repo_root/tests/pr82_native_number_origin.py" \
  "$run_root/run/wrfinput_d01" "$run_root/run/wrfout_d01_2026-08-16_12:00:00" \
  "$run_root/run/kdm6_first_call_pre.raw" "$run_root/run/number_basis_rejection.raw" \
  "$run_root/pr82_native_number_origin.json"
