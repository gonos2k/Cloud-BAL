#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh \
  >/dev/null 2>&1

state_case=/var/tmp/pr77_native_state.dOaJQD/host_startup_plus_kdm6_gradual
executable=${NATIVE_CONTROLLED_EXE:-/var/tmp/native-controlled-build/wrf.exe}
run_root=${1:-$(mktemp -d /var/tmp/native-controlled-replay.XXXXXX)}
receipt="$repo_root/docs/evidence/pr77_native_state_20261012.json"
mkdir -p "$run_root"

python3 - "$state_case/run" "$executable" "$run_root" "$receipt" <<'PY'
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

source, executable, run_root, receipt = map(Path, sys.argv[1:])
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
        os.link(original, target / original.name)
    shutil.copy2(executable, target / 'wrf.exe')
    for name, digest in expected.items():
        actual = hashlib.sha256((target / name).read_bytes()).hexdigest()
        if actual != digest:
            raise SystemExit(f'{mode}: pinned input mismatch: {name}')
PY

export OMP_NUM_THREADS=1
export OMP_DYNAMIC=FALSE
export LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:$LD_LIBRARY_PATH
ulimit -s unlimited

for mode in gradual ftz_daz; do
  run_dir="$run_root/run_$mode"
  gdb_profile=$mode
  if [[ $mode == ftz_daz ]]; then
    gdb_profile=ftz-daz
  fi
  (cd "$run_dir" && gdb --batch --quiet \
    -x "$repo_root/tests/native-controlled-20261012/gdb-$gdb_profile.gdb" \
    --args "$run_dir/wrf.exe") > "$run_dir/gdb.log" 2>&1
done

printf 'NATIVE_CONTROLLED_RUN_ROOT %s\n' "$run_root"
