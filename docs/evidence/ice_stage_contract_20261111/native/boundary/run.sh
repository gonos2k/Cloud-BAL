#!/usr/bin/env bash
set -euo pipefail
bundle=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$bundle/../../../../.." && pwd)
work=$(mktemp -d "$root/../ice-boundary.XXXXXXXX")
source "$root/tests/intel_toolchain.sh"
cd "$work"
python3 "$bundle/prepare.py" "$root/docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90" > extraction.log
for opt in O0 O2; do
 if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
 "$CLOUD_BAL_FC" "${flags[@]}" boundary.f90 -o "boundary_$opt" > "build_$opt.log" 2>&1
 "./boundary_$opt" > "run_$opt.log"
done
cmp run_O0.log run_O2.log
printf 'WORK_DIR %s\n' "$work"
sha256sum extraction.log boundary.f90 run_O0.log run_O2.log
