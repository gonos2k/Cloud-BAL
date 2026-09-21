#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"
mkdir -p "$repo_root/scratch"
build_root=$(mktemp -d "$repo_root/scratch/physical_boundary.XXXXXX")
awk '
  tolower($0) ~ /^[[:space:]]*subroutine balstagger\(/ {capture=1}
  capture && /^[[:space:]]*subroutine savemxmninfo\(/ {exit}
  capture {print}
' "$repo_root/src/balance/qbalpe.f" > "$build_root/balstagger.f"
awk '
  /real\*8 function qbal_divergence_value/ {capture=1}
  capture {print}
  capture && /^[[:space:]]*end[[:space:]]*$/ {exit}
' "$repo_root/src/balance/qbalpe.f" >> "$build_root/balstagger.f"
test -s "$build_root/balstagger.f"
for level in O0 O2; do
  mkdir "$build_root/$level"
  if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  fixed=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
  if [[ $level == O2 ]]; then
    fixed=(); skip=0
    for flag in "${CLOUD_BAL_FIXED_72_FLAGS[@]}"; do
      if ((skip)); then skip=0; continue; fi
      if [[ $flag == -check ]]; then skip=1; continue; fi
      fixed+=("${flag/-O0/-O2}")
    done
  fi
  (
    cd "$build_root/$level"
    "$CLOUD_BAL_FC" "${fixed[@]}" -c "$build_root/balstagger.f" -o balstagger.o
    "$CLOUD_BAL_FC" "${flags[@]}" "$repo_root/tests/qbal_physical_boundary.f90" \
      "$repo_root/tests/test_qbal_physical_boundary.f90" balstagger.o -o test_boundary
    ./test_boundary
  )
done
printf 'Pinned Intel O0/O2 evidence: %s\n' "$build_root"
