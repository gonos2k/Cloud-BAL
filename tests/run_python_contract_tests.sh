#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python_bin=${PYTHON_BIN:-python3}

cd "$repo_root"

tests=(
  tests/test_cp02_metadata_staging.py
  tests/test_compare_baseline.py
  tests/test_intel_integration_audit.py
  tests/test_native_hybrid_geometry.py
  tests/test_native_mass_metric.py
  tests/test_native_host_pressure.py
  tests/test_mp37_aux_contract.py
  tests/test_hydrometeor_moments.py
  tests/test_initialize_native_moments.py
  tests/test_native_ccn_stage_trace.py
  tests/test_native_mp37_aux.py
  tests/test_native_kdm6_trace.py
  tests/test_native_kdm6_call_geometry.py
  tests/test_pr63_transition_replay.py
  tests/test_pr64_qc_channel_replay.py
  tests/test_pr65_nc_donor_replay.py
  tests/test_pr65_pbl_operator_replay.py
  tests/test_pr65_pbl_domain_metrics.py
  tests/test_pr65_samecall_budget_audit.py
  tests/test_pr63_paired_bg_volume.py
  tests/test_operational_comparison_prep.py
  tests/test_operational_shadow_compare.py
  tests/test_output_transaction.py
  tests/test_transaction_recovery.py
  tests/test_publication_filesystem.py
  tests/test_bound_executable.py
  tests/test_bound_runtime.py
  tests/test_pin_link_inputs.py
  tests/test_pin_compiler_inputs.py
  tests/test_e01_completion_gate.py
  tests/test_landlock_policy.py
  tests/test_detached_runtime.py
  tests/test_cloud_bal_stage_coordinator.py
  tests/test_qbal_real_input_manifest.py
  tests/test_lco_evidence.py
  tests/test_real_manufactured_balance_generation.py
  tests/test_shadow_validator.py
  tests/test_cloud_provenance_receipt.py
  tests/test_candidate_endpoint_roundoff.py
  tests/test_run_isolated_native.py
  tests/test_pressure_transition_payload.py
  tests/test_pressure_transition_reference.py
  tests/test_thermo_output_certificate.py
  tests/test_pressure_cell_geometry.py
  tests/test_pressure_continuity_oracle.py
  tests/test_verify_shadow_wps_pair_lambert.py
  tests/test_pressure_geometry_budget.py
  tests/test_pressure_state_replay.py
  tests/test_transition_geopotential_reference.py
  tests/test_transition_geostrophic_scope.py
  tests/test_transition_radar_reader.py
  tests/test_transition_state_validator.py
  tests/test_transition_geometry_ledger.py
  tests/test_thermo_stage_budget.py
  tests/test_transition_geometry_reference.py
  tests/test_radar_proposal_replay.py
  tests/test_surface_boundary_validator.py
)

for test_path in "${tests[@]}"; do
  echo "Running $test_path"
  "$python_bin" "$repo_root/$test_path"
done

echo "Portable Python contract tests passed"
