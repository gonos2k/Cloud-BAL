#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_root/scratch"
test_tmp=$(mktemp -d "$repo_root/scratch/thermo-constraint.XXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
. "$repo_root/tests/intel_toolchain.sh"

for profile in checked optimized; do
  flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  if [[ $profile == optimized ]]; then
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  build_dir="$test_tmp/$profile"
  mkdir -p "$build_dir"
  cd "$build_dir"
  "$CLOUD_BAL_FC" "${flags[@]}" -module "$build_dir" -I "$build_dir" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_column_physics.f90" \
    "$repo_root/tests/test_thermodynamic_constraints.f90" \
    -o "$build_dir/test_thermodynamic_constraints"
  "$build_dir/test_thermodynamic_constraints"
  "$CLOUD_BAL_FC" "${flags[@]}" -module "$build_dir" -I "$build_dir" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_column_physics.f90" \
    "$repo_root/tests/test_hydrostatic_increment.f90" \
    -o "$build_dir/test_hydrostatic_increment"
  "$build_dir/test_hydrostatic_increment"
done
