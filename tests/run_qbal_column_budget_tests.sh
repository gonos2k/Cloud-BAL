#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo/tests/intel_toolchain.sh"
mkdir -p "$repo/scratch"
build=$(mktemp -d "$repo/scratch/column_budget.XXXXXX")
for level in O0 O2; do
  mkdir "$build/$level"
  if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  (
    cd "$build/$level"
    "$CLOUD_BAL_FC" "${flags[@]}" "$repo/tests/qbal_physical_boundary.f90" \
      "$repo/tests/qbal_pressure_flux.f90" "$repo/tests/qbal_sloping_geometry.f90" \
      "$repo/tests/qbal_column_budget.f90" "$repo/tests/test_qbal_column_budget.f90" -o test_geometry
    ./test_geometry
  )
done
printf 'Pinned Intel O0/O2 evidence: %s\n' "$build"
