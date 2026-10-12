#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh \
  >/dev/null 2>&1

state_case=/var/tmp/pr77_native_state.dOaJQD/host_startup_plus_kdm6_gradual
executable=${NATIVE_CONTROLLED_EXE:-/var/tmp/native-controlled-build/wrf.exe}
if (($# > 0)); then
  run_root=$1
  if [[ -e "$run_root" || -L "$run_root" ]]; then
    printf 'refusing to reuse controlled run root: %s\n' "$run_root" >&2
    exit 2
  fi
else
  run_root=$(mktemp -d /var/tmp/native-controlled-replay.XXXXXX)
fi
receipt="$repo_root/docs/evidence/pr77_native_state_20261012.json"
mkdir -p "$run_root"

python3 - "$state_case/run" "$executable" "$run_root" "$receipt" "$repo_root" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

source, executable, run_root, receipt, repo = map(Path, sys.argv[1:])
sys.path.insert(0, str(repo / 'tools'))
from run_isolated_native import copy_detached_input
source_before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in source.iterdir() if path.is_file()}
expected = json.loads(receipt.read_text())['profiles'][
    'host_startup_plus_kdm6_gradual']['inputs']['before']
mutable = {'wrf.exe', 'candidate_run.log', 'namelist.output',
           'pr77_native_species.raw', 'pr77_host_fp.raw',
           'pr76_thread_entry.raw', 'pr76_target_call.raw',
           'pr75_native_fp.raw', 'kdm6_first_call_pre.raw',
           'kdm6_first_call_post.raw', 'pr67_kdm6_process.raw',
           'pr69_water.raw'}
for mode in ('gradual', 'ftz_daz'):
    target = run_root / f'run_{mode}'
    target.mkdir(exist_ok=False)
    for original in source.iterdir():
        if (not original.is_file() or original.name in mutable
                or original.name.startswith(('rsl.', 'wrfout', 'wrfrst'))):
            continue
        copy_detached_input(original, target / original.name)
    copy_detached_input(executable, target / 'wrf.exe')
    for name, digest in expected.items():
        actual = hashlib.sha256((target / name).read_bytes()).hexdigest()
        if actual != digest:
            raise SystemExit(f'{mode}: pinned input mismatch: {name}')
source_after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source.iterdir() if path.is_file()}
if source_after != source_before:
    raise SystemExit('source case changed while preparing controlled replays')
with (run_root / 'source_snapshot.json').open('x') as stream:
    stream.write(json.dumps({'pre': source_before}, indent=2) + '\n')
PY

export OMP_NUM_THREADS=1
export OMP_DYNAMIC=FALSE
export LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:$LD_LIBRARY_PATH
ulimit -s unlimited

gdb_status=0
for mode in gradual ftz_daz; do
  run_dir="$run_root/run_$mode"
  gdb_profile=$mode
  if [[ $mode == ftz_daz ]]; then
    gdb_profile=ftz-daz
  fi
  (cd "$run_dir" && gdb --batch --quiet \
    -x "$repo_root/tests/native-controlled-20261012/gdb-$gdb_profile.gdb" \
    --args "$run_dir/wrf.exe") > "$run_dir/gdb.log" 2>&1 || gdb_status=$?
done

python3 - "$state_case/run" "$run_root/source_snapshot.json" <<'PY'
import hashlib, json, sys
from pathlib import Path
source, record = map(Path, sys.argv[1:])
pre = json.loads(record.read_text())['pre']
post = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source.iterdir() if path.is_file()}
record.write_text(json.dumps({'pre': pre, 'post': post, 'unchanged': pre == post}, indent=2) + '\n')
if pre != post:
    raise SystemExit('source case changed during controlled replay')
PY

printf 'NATIVE_CONTROLLED_RUN_ROOT %s\n' "$run_root"
exit "$gdb_status"
