#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build_dir=$(mktemp -d "$repo_dir/.test-build.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
. "$repo_dir/tests/intel_toolchain.sh"
cd "$build_dir"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$build_dir" -I "$build_dir" \
  "$repo_dir/src/common/cloud_bal_field_contracts.f90" \
  "$repo_dir/src/common/cloud_bal_moisture.f90" \
  "$repo_dir/src/common/cloud_bal_cloud_profiles.f90" \
  "$repo_dir/src/common/cloud_bal_localization.f90" \
  "$repo_dir/src/common/cloud_bal_radar_downdraft.f90" \
  "$repo_dir/src/common/cloud_bal_wind_modes.f90" \
  "$repo_dir/tests/test_cloud_bal_core.f90" \
  -o "$build_dir/test_cloud_bal_core"

"$build_dir/test_cloud_bal_core"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -I "$repo_dir/src/include" -I "$build_dir" -syntax-only \
  "$repo_dir/src/balance/qbalpe.f"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -I "$build_dir" -syntax-only \
  "$repo_dir/src/lib/pcpcnc.f" \
  "$repo_dir/src/lib/vv_lgt_ct.f"

if ! grep -Fq 'if(.false. .and. l_evap_radar)then' \
  "$repo_dir/src/deriv/laps_deriv_sub.f"; then
  echo 'FAIL: dormant radar evaporation is not compile-time locked OFF' >&2
  exit 1
fi

echo 'Cloud-BAL source gates: PASS'
