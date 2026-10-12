#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
scratch_root=${CLOUD_BAL_TEST_SCRATCH_ROOT:-/var/tmp}
mkdir -p "$scratch_root"
test_tmp=$(mktemp -d "$scratch_root/force_prior_nullspace.XXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
. "$repo_root/tests/intel_toolchain.sh"
cd "$test_tmp"

for profile in checked optimized; do
  if [[ $profile == checked ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  "$CLOUD_BAL_FC" "${flags[@]}" -module "$test_tmp" -I "$test_tmp" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
    "$repo_root/src/common/cloud_bal_balance_operator.f90" \
    "$repo_root/tests/test_force_prior_nullspace.f90" \
    -o "$test_tmp/test_force_prior_nullspace"
  "$test_tmp/test_force_prior_nullspace"
done
