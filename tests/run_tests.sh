#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_dir/scratch"
build_dir=$(mktemp -d "$repo_dir/scratch/source_tests.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
. "$repo_dir/tests/intel_toolchain.sh"
cd "$build_dir"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$build_dir" -I "$build_dir" \
  "$repo_dir/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_dir/src/common/cloud_bal_field_contracts.f90" \
  "$repo_dir/src/common/cloud_bal_moisture.f90" \
  "$repo_dir/src/common/cloud_bal_cloud_profiles.f90" \
  "$repo_dir/src/common/cloud_bal_localization.f90" \
  "$repo_dir/src/common/cloud_bal_radar_downdraft.f90" \
  "$repo_dir/src/common/cloud_bal_wind_modes.f90" \
  "$repo_dir/tests/test_cloud_bal_core.f90" \
  -o "$build_dir/test_cloud_bal_core"

"$build_dir/test_cloud_bal_core"

# The real QBAL main imports its state-carrying OFF adapter even in a syntax
# check. Compile the actual modules rather than hiding that production call.
nf_config="$repo_dir/../klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
read -r -a stage_nf_flags <<<"$("$nf_config" --fflags)"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
  "${stage_nf_flags[@]}" -module "$build_dir" -I "$build_dir" \
  "$repo_dir/src/common/cloud_bal_state.f90" \
  "$repo_dir/src/common/cloud_bal_column_physics.f90" \
  "$repo_dir/src/common/cloud_bal_balance_operator.f90" \
  "$repo_dir/src/common/cloud_bal_pipeline.f90" \
  "$repo_dir/src/common/cloud_bal_stage_payload.f90" \
  "$repo_dir/src/common/cloud_bal_stage_context.f90" \
  "$repo_dir/src/common/cloud_bal_balance_adapter.f90"

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
if ! grep -Fq '.false.,w_3d,istatus)' \
  "$repo_dir/src/deriv/laps_deriv_sub.f" || \
   ! grep -Fq 'w_3d = r_missing_data' "$repo_dir/src/deriv/laps_deriv_sub.f" || \
   ! grep -Fq 'if(.false. .and. l_bogus_radar_w)' \
  "$repo_dir/src/deriv/laps_deriv_sub.f" || \
   ! grep -Fq 'j_status(n_lco) = sys_no_data' \
  "$repo_dir/src/deriv/laps_deriv_sub.f"; then
  echo 'FAIL: disabled cloud/radar W can still claim valid COM authority' >&2
  exit 1
fi

echo 'Cloud-BAL source gates: PASS'
