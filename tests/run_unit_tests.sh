#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_root/scratch"
test_tmp=$(mktemp -d "$repo_root/scratch/unit_tests.XXXXXX")
trap 'rm -rf "$test_tmp"' EXIT
. "$repo_root/tests/intel_toolchain.sh"
cd "$test_tmp"
# This C bridge regression requires the pinned Intel/local ncgen profile.
python3 "$repo_root/tests/test_ncgen_bridge.py"
pressure_transition_fixture="$test_tmp/pressure_transition_remap_fixture.txt"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/tests/test_canonical_state.f90" \
  -o "$test_tmp/test_canonical_state"

"$test_tmp/test_canonical_state"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/tests/test_pressure_geometry_oracle.f90" \
  -o "$test_tmp/test_pressure_geometry_oracle"

"$test_tmp/test_pressure_geometry_oracle"

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/tests/test_pressure_partial_face_oracle.f90" \
  -o "$test_tmp/test_pressure_partial_face_oracle"

"$test_tmp/test_pressure_partial_face_oracle"

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
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/tests/test_thermo_column.f90" \
  -o "$test_tmp/test_thermo_column"

"$test_tmp/test_thermo_column"

for hydrostatic_build in checked optimized; do
  saturation_fixture="$test_tmp/saturation_reference_${hydrostatic_build}.txt"
  surface_transition_fixture="$test_tmp/surface_transition_${hydrostatic_build}.txt"
  hydrostatic_flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  if [[ "$hydrostatic_build" == optimized ]]; then
    hydrostatic_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  for hydrostatic_test in test_saturation_reference test_hydrostatic_increment test_pressure_hydrostatic_state \
      test_pressure_geometry_budget test_pressure_column_remap test_pressure_domain_budget \
      test_pressure_domain_transition; do
    "$CLOUD_BAL_FC" "${hydrostatic_flags[@]}" \
      -module "$test_tmp" -I "$test_tmp" \
      "$repo_root/src/common/cloud_bal_state.f90" \
      "$repo_root/src/common/cloud_bal_column_physics.f90" \
      "$repo_root/tests/$hydrostatic_test.f90" -o "$test_tmp/$hydrostatic_test"
    if [[ "$hydrostatic_test" == test_saturation_reference ]]; then
      "$test_tmp/$hydrostatic_test" "$saturation_fixture"
      python3 "$repo_root/tests/check_saturation_reference.py" "$saturation_fixture"
    elif [[ "$hydrostatic_test" == test_pressure_domain_transition ]]; then
      "$test_tmp/$hydrostatic_test" "$surface_transition_fixture"
      python3 "$repo_root/tests/check_surface_pressure_reference.py" --require-geopotential "$surface_transition_fixture"
      python3 "$repo_root/tests/test_pressure_state_replay.py" "$surface_transition_fixture"
    elif [[ "$hydrostatic_test" == test_pressure_column_remap ]]; then
      "$test_tmp/$hydrostatic_test" "$pressure_transition_fixture"
      [[ -s "$pressure_transition_fixture" ]]
      python3 "$repo_root/tests/test_pressure_transition_reference.py" \
        "$pressure_transition_fixture"
    else
      "$test_tmp/$hydrostatic_test"
    fi
  done
  "$CLOUD_BAL_FC" "${hydrostatic_flags[@]}" \
    -module "$test_tmp" -I "$test_tmp" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
    "$repo_root/src/common/cloud_bal_balance_operator.f90" \
    "$repo_root/tests/test_pressure_geostrophic_assessment.f90" \
    -o "$test_tmp/test_pressure_geostrophic_assessment"
  "$test_tmp/test_pressure_geostrophic_assessment"
done

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_column_physics.f90" \
  "$repo_root/tests/test_pressure_thermo_state.f90" \
  -o "$test_tmp/test_pressure_thermo_state"

"$test_tmp/test_pressure_thermo_state"

for phase_test in test_water_phase_transfer test_pressure_phase_transfer; do
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
    -module "$test_tmp" -I "$test_tmp" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_column_physics.f90" \
    "$repo_root/tests/$phase_test.f90" -o "$test_tmp/$phase_test"
  "$test_tmp/$phase_test"
done

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp" -I "$test_tmp" \
  "$repo_root/src/common/cloud_bal_state.f90" \
  "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
  "$repo_root/src/common/cloud_bal_balance_operator.f90" \
  "$repo_root/tests/test_balance_operator.f90" \
  -o "$test_tmp/test_balance_operator"

"$test_tmp/test_balance_operator"

for profile in checked optimized; do
  partial_flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  if [[ $profile == optimized ]]; then
    partial_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  "$CLOUD_BAL_FC" "${partial_flags[@]}" \
    -module "$test_tmp" -I "$test_tmp" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
    "$repo_root/src/common/cloud_bal_balance_operator.f90" \
    "$repo_root/tests/test_balance_partial_faces.f90" \
    -o "$test_tmp/test_balance_partial_faces"
  "$test_tmp/test_balance_partial_faces"
done

for pipeline_test in test_pipeline test_prebalance_wind reproduction_probe; do
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
    -module "$test_tmp" -I "$test_tmp" \
    "$repo_root/src/common/cloud_bal_state.f90" \
    "$repo_root/src/common/cloud_bal_column_physics.f90" \
    "$repo_root/src/common/cloud_bal_grid_geometry.f90" \
    "$repo_root/src/common/cloud_bal_balance_operator.f90" \
    "$repo_root/src/common/cloud_bal_pipeline.f90" \
    "$repo_root/tests/$pipeline_test.f90" -o "$test_tmp/$pipeline_test"
  "$test_tmp/$pipeline_test"
done

python3 "$repo_root/tests/test_output_transaction.py"
python3 "$repo_root/tests/test_compare_baseline.py"
python3 "$repo_root/tests/test_native_hybrid_geometry.py"
python3 "$repo_root/tests/test_native_host_pressure.py"
python3 "$repo_root/tests/test_shadow_validator.py"
python3 "$repo_root/tests/test_real_manufactured_balance_generation.py"

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

"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
  -module "$test_tmp/wps_mod" -I "$test_tmp/wps_mod" \
  "$repo_root/tests/test_wps_vapor.f90" \
  "$test_tmp/lapsprep_wps.o" "$test_tmp/wps_stubs.o" \
  -o "$test_tmp/test_wps_vapor"
"$test_tmp/test_wps_vapor" "$test_tmp/wps_root"
python3 "$repo_root/tests/check_wps_vapor.py" "$test_tmp/wps_root"
bash "$repo_root/tests/run_pressure_wps_mapping.sh"
bash "$repo_root/tests/run_lapsprep_vapor.sh"

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
bash "$repo_root/tests/run_qbal_nonlin_tests.sh"
"$repo_root/tests/run_legacy_shadow_adapter_test.sh"
bash "$repo_root/tests/run_pressure_radar_reference.sh"
"$repo_root/tests/run_real_shadow_io_contract_tests.sh"
python3 "$repo_root/tests/test_qbal_real_input_manifest.py"
python3 "$repo_root/tests/test_lt1_candidate.py"
python3 "$repo_root/tests/test_lsx_candidate.py"
python3 "$repo_root/tests/test_operational_comparison_prep.py"
python3 "$repo_root/tests/test_operational_shadow_compare.py"
"$repo_root/tests/run_legacy_deriv_safety_audit.sh"
python3 "$repo_root/tests/test_intel_integration_audit.py"
"$repo_root/tests/run_original_upstream_replay_tests.sh"
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
nf_config="$repo_root/../klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
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
