#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"
mkdir -p "$repo_root/scratch"
build_root=$(mktemp -d "$repo_root/scratch/pressure_flux.XXXXXX")
for level in O0 O2; do
  mkdir "$build_root/$level"
  if [[ $level == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  (
    cd "$build_root/$level"
    "$CLOUD_BAL_FC" "${flags[@]}" "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
      "$repo_root/tests/qbal_physical_boundary.f90" "$repo_root/tests/qbal_pressure_flux.f90" \
      "$repo_root/tests/test_qbal_pressure_flux.f90" -o test_flux
    ./test_flux
  )
done
printf 'Pinned Intel O0/O2 evidence: %s\n' "$build_root"
