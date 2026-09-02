#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_root/scratch"
test_tmp=$(mktemp -d "$repo_root/scratch/contract_regressions.XXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
. "$repo_root/tests/intel_toolchain.sh"

build_and_run() {
  local name=$1
  shift
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
    -module "$test_tmp" -I "$test_tmp" "$@" \
    -o "$test_tmp/$name"
  "$test_tmp/$name"
}

build_and_run test_state_atomic_refresh \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/tests/test_state_atomic_refresh.f90"

build_and_run test_missing_phase_continuity \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/tests/test_missing_phase_continuity.f90"

build_and_run test_balance_omega_authority \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/tests/test_balance_omega_authority.f90"

build_and_run test_nonuniform_localization \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/src/common/cloud_bal_pipeline.f90" \
  "$repo_root/src/common/cloud_bal_localization.f90" \
  "$repo_root/tests/test_nonuniform_localization.f90"
