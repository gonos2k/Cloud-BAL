#!/usr/bin/env bash
set -euo pipefail
repo_root=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr77_native_state_20261012/Cloud-BAL
workspace_root=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
export CLOUD_BAL_WORKSPACE_ROOT=$workspace_root
export CLOUD_BAL_TEST_SCRATCH_ROOT=/var/tmp
source "$repo_root/tests/intel_toolchain.sh"
test_tmp=$(mktemp -d /var/tmp/pr77_unit_tail.XXXXXX)
printf 'UNIT_TAIL_SCRATCH %s\n' "$test_tmp"
cd "$test_tmp"
nf_config=$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config
read -r -a stage_nf_flags <<<"$("$nf_config" --fflags)"
for module in cloud_bal_state cloud_bal_grid_geometry cloud_bal_column_physics cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_localization cloud_bal_wind_modes; do
  "$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" "${stage_nf_flags[@]}" -module "$test_tmp" -I "$test_tmp" "$repo_root/src/common/$module.f90" -o "$test_tmp/$module.o"
done
bash "$repo_root/tests/run_upstream_temperature_status.sh"
bash "$repo_root/tests/run_upstream_surface_status.sh"
bash "$repo_root/tests/run_surface_observation_reader.sh"
bash "$repo_root/tests/run_previous_surface_qc.sh"
bash "$repo_root/tests/run_upstream_humidity_status.sh"
bash "$repo_root/tests/run_upstream_derived_status.sh"
bash "$repo_root/tests/run_get_cloud_deriv_lightning_status.sh"
bash "$repo_root/tests/run_upstream_cloud_status.sh"
bash "$repo_root/tests/run_upstream_wind_status.sh"

# Real full-main compilation now includes the canonical stage adapter API.
# Compile its actual dependency modules; never remove the main's USE/call.
bash "$repo_root/tests/run_cloud_bal_stage_payload.sh"
nf_config="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
read -r -a stage_nf_flags <<<"$("$nf_config" --fflags)"
"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FREE_FLAGS[@]}" \
  "${stage_nf_flags[@]}" -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_stage_payload.f90" \
  "$repo_root/src/common/cloud_bal_stage_context.f90" \
  "$repo_root/src/common/cloud_bal_balance_adapter.f90"

"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_FLAGS[@]}" \
  -I "$repo_root/src/include" -module "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/qbalpe.o" \
  "$repo_root/src/balance/qbalpe.f"

"$CLOUD_BAL_FC" -c "${CLOUD_BAL_FIXED_72_FLAGS[@]}" \
  -I "$repo_root/src/include" -module "$test_tmp" -I "$test_tmp" \
  -o "$test_tmp/qbalpe_72.o" \
  "$repo_root/src/balance/qbalpe.f"

printf '%s\n' 'qbalpe fixed-form 72-column compile check passed'
