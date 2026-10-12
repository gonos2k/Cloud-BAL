#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1
export LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=68
export OMP_DYNAMIC=FALSE
ulimit -s unlimited
printf -v pr77_native_flags '%s\n' "${CLOUD_BAL_FREE_FLAGS[@]}"
export PR76_FP_FLAGS=$pr77_native_flags
work_root=$(mktemp -d /var/tmp/pr77_native_state.XXXXXX)
printf 'WORK_ROOT %s\n' "$work_root"
PYTHONPATH="$repo_root/tests${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest "$repo_root/tests/test_pr77_native_state_transform.py" \
    "$repo_root/tests/test_pr77_native_state_receipt.py"
PYTHONPATH="$repo_root/tests${PYTHONPATH:+:$PYTHONPATH}" \
  python3 "$repo_root/tests/pr77_native_state_run.py" "$work_root"
