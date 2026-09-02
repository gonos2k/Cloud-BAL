#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_root/scratch"
test_tmp=$(mktemp -d "$repo_root/scratch/legacy_shadow_adapter.XXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
. "$repo_root/tests/intel_toolchain.sh"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/src/common/cloud_bal_pipeline.f90" \
  "$repo_root/src/common/cloud_bal_legacy_shadow_adapter.f90" \
  "$repo_root/tests/test_legacy_shadow_adapter.f90" \
  -o "$test_tmp/test_legacy_shadow_adapter"

"$test_tmp/test_legacy_shadow_adapter"
