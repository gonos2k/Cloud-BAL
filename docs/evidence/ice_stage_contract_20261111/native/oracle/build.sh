#!/usr/bin/env bash
set -euo pipefail
bundle=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$bundle/../../../../.." && pwd)
source "$root/tests/intel_toolchain.sh"
work=$(mktemp -d "$root/../ice-oracle.XXXXXXXX")
cd "$work"
python3 "$bundle/prepare.py" "$bundle/../boundary/boundary.f90" > extraction.log
for opt in O0 O2; do
 if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
 "$CLOUD_BAL_FC" "${flags[@]}" oracle.f90 -o "oracle_$opt" > "build_$opt.log" 2>&1
done
printf 'WORK_DIR %s\n' "$work"
sha256sum oracle.f90 oracle_O0 oracle_O2
