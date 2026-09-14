#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"
test_tmp=$(mktemp -d "$repo_root/scratch/pressure_wps_mapping.XXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
# Resolve modules only in this fresh build directory, not in the caller's tree.
cd "$test_tmp"

for optimization in O0 O2; do
  case_dir="$test_tmp/$optimization"
  mkdir -p "$case_dir"
  test_flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  if [[ $optimization == O2 ]]; then
    test_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  "$CLOUD_BAL_FC" "${test_flags[@]}" \
    -module "$case_dir" -I "$case_dir" \
    "$repo_root/tests/wps_module_stubs.f90" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_wps_adapter.f90" \
    "$repo_root/src/lapsprep/module_lapsprep_wps.f90" \
    "$repo_root/tests/test_pressure_wps_mapping.f90" \
    -o "$case_dir/test_mapping"
  "$case_dir/test_mapping" "$case_dir"
  python3 "$repo_root/tests/check_pressure_wps_mapping.py" "$case_dir"
  "$CLOUD_BAL_FC" "${test_flags[@]}" \
    -module "$case_dir" -I "$case_dir" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_wps_adapter.f90" \
    "$repo_root/tests/test_host_vapor_pressure.f90" \
    -o "$case_dir/test_host_vapor"
  "$case_dir/test_host_vapor"
  "$CLOUD_BAL_FC" "${test_flags[@]}" \
    -module "$case_dir" -I "$case_dir" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_wps_adapter.f90" \
    "$repo_root/tests/test_source_host_pressure_request.f90" \
    -o "$case_dir/test_source_host_pressure_request"
  "$case_dir/test_source_host_pressure_request"
  "$CLOUD_BAL_FC" "${test_flags[@]}" \
    -module "$case_dir" -I "$case_dir" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
    "$repo_root/src/common/cloud_bal_column_physics.f90" \
    "$repo_root/src/common/cloud_bal_balance_operator.f90" \
    "$repo_root/src/common/cloud_bal_wps_adapter.f90" \
    "$repo_root/src/common/cloud_bal_pipeline.f90" \
    "$repo_root/tests/test_pressure_transition_prior.f90" \
    -o "$case_dir/test_pressure_transition_prior"
  "$case_dir/test_pressure_transition_prior"
done
