#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_root/scratch"
test_tmp=$(mktemp -d "$repo_root/scratch/unit_tests.XXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
. "$repo_root/tests/intel_toolchain.sh"
cd "$test_tmp"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/tests/test_canonical_state.f90" \
  -o "$test_tmp/test_canonical_state"

"$test_tmp/test_canonical_state"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/tests/test_column_physics.f90" \
  -o "$test_tmp/test_column_physics"

"$test_tmp/test_column_physics"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/tests/test_balance_operator.f90" \
  -o "$test_tmp/test_balance_operator"

"$test_tmp/test_balance_operator"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/src/common/cloud_bal_pipeline.f90" \
  "$repo_root/tests/test_pipeline.f90" \
  -o "$test_tmp/test_pipeline"

"$test_tmp/test_pipeline"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/src/common/cloud_bal_pipeline.f90" \
  "$repo_root/tests/reproduction_probe.f90" \
  -o "$test_tmp/reproduction_probe"

"$test_tmp/reproduction_probe"

python3 "$repo_root/tests/test_output_transaction.py"
python3 "$repo_root/tests/test_compare_baseline.py"
python3 "$repo_root/tests/test_shadow_validator.py"

mkdir -p "$test_tmp/wps_mod" "$test_tmp/wps_root/lapsprd/lapsprep/wps"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp/wps_mod" -I "$test_tmp/wps_mod" \
  -o "$test_tmp/wps_stubs.o" "$repo_root/tests/wps_module_stubs.f90"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp/wps_mod" -I "$test_tmp/wps_mod" \
  -o "$test_tmp/lapsprep_wps.o" "$repo_root/src/lapsprep/module_lapsprep_wps.f90"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp/wps_mod" -I "$test_tmp/wps_mod" \
  "$repo_root/tests/test_wps_writer_status.f90" \
  "$test_tmp/lapsprep_wps.o" "$test_tmp/wps_stubs.o" \
  -o "$test_tmp/test_wps_writer_status"

"$test_tmp/test_wps_writer_status" "$test_tmp/wps_root"

"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -o "$test_tmp/writeballaps.o" "$repo_root/src/balance/writeballaps.f"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  "$repo_root/tests/test_writeballaps_status.f90" "$test_tmp/writeballaps.o" \
  -o "$test_tmp/test_writeballaps_status"

"$test_tmp/test_writeballaps_status"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/src/common/cloud_bal_field_contracts.f90" \
  "$repo_root/src/common/cloud_bal_moisture.f90" \
  "$repo_root/src/common/cloud_bal_cloud_profiles.f90" \
  "$repo_root/src/common/cloud_bal_localization.f90" \
  "$repo_root/src/common/cloud_bal_radar_downdraft.f90" \
  "$repo_root/src/common/cloud_bal_wind_modes.f90" \
  "$repo_root/tests/test_cloud_bal_core.f90" \
  -o "$test_tmp/test_cloud_bal_core"

"$test_tmp/test_cloud_bal_core"

"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/module_setup.o" "$repo_root/src/lapsprep/module_setup.f90"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/lwc2vapor.o" "$repo_root/src/lapsprep/lwc2vapor.f90"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/ice2vapor.o" "$repo_root/src/lapsprep/ice2vapor.f90"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/vv_lgt_ct.o" "$repo_root/src/lib/vv_lgt_ct.f"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  -I "$repo_root/src/include" -o "$test_tmp/get_cloud_deriv.o" \
  "$repo_root/src/lib/get_cloud_deriv.f"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  -I "$repo_root/src/include" -o "$test_tmp/pcpcnc.o" \
  "$repo_root/src/lib/pcpcnc.f"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  -I "$repo_root/src/include" -o "$test_tmp/laps_deriv_sub.o" \
  "$repo_root/src/deriv/laps_deriv_sub.f"

# The focused tree does not ship the legacy NetCDF include required by the
# whole lapsio.f file.  Extract the COM/wind reader, then link and call both
# the legacy ABI and the independent cloud-omega-status entry point.
awk '
  /^      subroutine get_laps_3d_analysis_data\(/ {capture=1}
  capture && /^cdis/ {exit}
  capture {print}
' "$repo_root/src/lib/bgdata/lapsio.f" > "$test_tmp/lapsio_com_reader.f"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -o "$test_tmp/lapsio_com_reader.o" \
  "$test_tmp/lapsio_com_reader.f"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  "$repo_root/tests/test_lapsio_abi.f90" \
  "$test_tmp/lapsio_com_reader.o" -o "$test_tmp/test_lapsio_abi"
"$test_tmp/test_lapsio_abi"

awk '
  /call get_laps_3d_analysis_data\(/ {reader=1; next}
  reader && /if\(istatus.ne.1\)then/ {checked=1}
  reader && /istatus *= *-1/ {converted=1}
  reader && /call get_laps_2d\(/ {done=1; exit}
  END {if (!done || !checked || !converted) exit 1}
' "$repo_root/src/lib/bgdata/readbgdata.f"
printf '%s\n' 'LAPS 3-D reader status-conversion check passed'

# Extract the production continuity/operator routines so the runtime test uses
# the exact fixed-form implementation without linking the unrelated KLAPS I/O.
awk '
  /^      subroutine leib_sub\(/ {capture=1}
  capture && /^      subroutine analzo\(/ {capture=0}
  capture {print}
  /^      subroutine fthree\(/ {operator=1}
  operator && /^      subroutine leib\(/ {operator=0}
  operator {print}
' "$repo_root/src/balance/qbalpe.f" > "$test_tmp/qbal_operator_core.f"

"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -o "$test_tmp/qbal_operator_core.o" "$test_tmp/qbal_operator_core.f"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  "$repo_root/tests/test_qbal_operator.f90" \
  "$test_tmp/qbal_operator_core.o" -o "$test_tmp/test_qbal_operator"

"$test_tmp/test_qbal_operator"

"$repo_root/tests/run_contract_regressions.sh"
"$repo_root/tests/run_qbal_acceptance_tests.sh"
"$repo_root/tests/run_legacy_shadow_adapter_test.sh"
"$repo_root/tests/run_real_shadow_io_contract_tests.sh"
python3 "$repo_root/tests/test_qbal_real_input_manifest.py"
python3 "$repo_root/tests/test_operational_comparison_prep.py"
python3 "$repo_root/tests/test_operational_shadow_compare.py"
"$repo_root/tests/run_legacy_deriv_safety_audit.sh"
python3 "$repo_root/tests/test_intel_integration_audit.py"
"$repo_root/tests/run_original_upstream_replay_tests.sh"

"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -I "$repo_root/src/include" -module "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/qbalpe.o" \
  "$repo_root/src/balance/qbalpe.f"

"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_72_FLAGS[@]}" \
  -I "$repo_root/src/include" -module "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/qbalpe_72.o" \
  "$repo_root/src/balance/qbalpe.f"

printf '%s\n' 'qbalpe fixed-form 72-column compile check passed'
