#!/usr/bin/env bash
set -euo pipefail

pr98_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=tests/intel_toolchain.sh
source "$pr98_root/tests/intel_toolchain.sh"
export LD_LIBRARY_PATH="/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export OMP_NUM_THREADS=1
ulimit -s unlimited
exec python3 "$pr98_root/tools/pr98_replay.py" "$@"
