#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh \
  >/dev/null 2>&1

input_run=${PR81_NATIVE_INPUT_RUN:-/var/tmp/pr80_kdm6_radar_contract.nsUNuj/run}
executable=${PR81_NATIVE_EXE:?set PR81_NATIVE_EXE to the executable under investigation}
run_root=${1:-$(mktemp -d /var/tmp/pr81_native_first_step.XXXXXX)}
run_dir="$run_root/run"
[[ -x "$executable" ]] || { printf 'candidate executable missing: %s\n' "$executable" >&2; exit 2; }
mkdir -p "$run_root"
snapshot_path="$run_root/source_snapshot.json"
python3 "$repo_root/tests/pr81_native_case_copy.py" \
  "$input_run" "$executable" "$run_dir" "$snapshot_path"

export OMP_NUM_THREADS=1
export OMP_DYNAMIC=FALSE
export LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:${LD_LIBRARY_PATH:-}
ulimit -s unlimited

gdb_argv=(gdb --batch --quiet -x "$repo_root/tests/pr81_native_first_step.gdb" \
  --args "$run_dir/wrf.exe")
printf '%s\0' "$run_dir/wrf.exe" > "$run_root/native_run_argv.nul"
printf '%s\0' "${gdb_argv[@]}" > "$run_root/gdb_argv.nul"
python3 - "$run_root" "$run_dir" "$executable" <<'PY'
import hashlib, json, os, sys
root, run_dir, executable = sys.argv[1:]
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()
json.dump({'native_run_argv_nul_path':os.path.join(root,'native_run_argv.nul'),
           'gdb_argv_nul_path':os.path.join(root,'gdb_argv.nul'),
           'working_directory':run_dir,'candidate_executable_path':executable,
           'candidate_executable_sha256':sha(executable)},
          open(os.path.join(root,'run_command.json'),'w'),indent=2)
with open(os.path.join(root,'run_command.json'),'a') as out: out.write('\n')
PY

gdb_status=0
(cd "$run_dir" && "${gdb_argv[@]}") > "$run_root/gdb.log" 2>&1 || gdb_status=$?
python3 - "$input_run" "$snapshot_path" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

source, snapshot_path = map(Path, sys.argv[1:])
def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
pre = json.loads(snapshot_path.read_text())['pre']
post = {path.name: sha256(path) for path in sorted(source.iterdir()) if path.is_file()}
snapshot_path.write_text(json.dumps({'pre': pre, 'post': post,
                                     'unchanged': pre == post}, indent=2) + '\n')
if pre != post:
    raise SystemExit('source case changed during the native replay')
PY
python3 - "$run_root" "$gdb_status" <<'PY'
import hashlib, json, sys
from pathlib import Path
root, gdb_status = Path(sys.argv[1]), int(sys.argv[2])
log = (root / 'gdb.log').read_text(errors='replace')
rsl_path = root / 'run' / 'rsl.error.0000'
rsl = rsl_path.read_text(errors='replace') if rsl_path.exists() else ''
if '=== FIRST FLOATING-POINT TRAP ===' in log:
    outcome = 'sigfpe'
elif 'KDM6 invalid NC number basis input' in rsl:
    outcome = 'kdm6_input_error_stop'
elif '[Inferior 1 ' in log and 'exited normally' in log:
    outcome = 'normal_exit'
else:
    outcome = 'other_or_incomplete'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
json.dump({'outcome':outcome,'gdb_status':gdb_status,
           'gdb_log_sha256':sha(root/'gdb.log'),
           'rsl_error_path':str(rsl_path),'rsl_error_sha256':sha(rsl_path)},
          open(root/'run_status.json','w'),indent=2)
with open(root/'run_status.json','a') as out: out.write('\n')
PY

printf 'PR81_NATIVE_RUN_ROOT %s\n' "$run_root"
printf 'PR81_NATIVE_GDB_LOG %s/gdb.log\n' "$run_root"
printf 'PR81_NATIVE_RSL_ERROR %s/rsl.error.0000\n' "$run_dir"
printf 'PR81_NATIVE_SOURCE_SNAPSHOT %s\n' "$snapshot_path"
printf 'PR81_NATIVE_RUN_COMMAND %s/run_command.json\n' "$run_root"
printf 'PR81_NATIVE_RUN_STATUS %s/run_status.json\n' "$run_root"
exit "$gdb_status"
