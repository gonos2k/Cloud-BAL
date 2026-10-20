#!/usr/bin/env python3
"""Guarded selected-path Graphify/KG update for PR91 host-store diagnostics.
External scratch utility; apply remains fail-closed until root supplies reviewed pins and closed records."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, importlib.util, json, os, re, shutil, stat, subprocess, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
MAINT=ROOT/'Cloud-BAL'
SOURCE=ROOT/'scratch/pr91_host_store_20261020/Cloud-BAL'
OUT=MAINT/'scratch/pr91_host_store_20261020/kg'
BASE='3a896be3d381909f0cc61d1c0896b329b98d5aea'
PRIOR=MAINT/'scratch/pr90_rain_roundtrip_20261019/kg_receipt.json'
PRIOR_SHA='42ed1de1e363f9eb2a8a584b3ed52de3487ee95157d3b15717b0748f9e50040a'
PRIOR_ALIAS=None
DRAFT_REVIEW_COMMIT='eadc7ccf2d9fddddd6fcfac77174190363ac3f32'  # Current pushed source commit; final publication commit is still open.
DRAFT_PR_URL='https://github.com/gonos2k/Cloud-BAL/pull/91'
DRAFT_GRAPH_SOURCE_PATHS=frozenset({
    'docs/PR91_HISTORY_RESPONSE_20261020.md',
    'docs/PR91_HOST_STORE_CONTRACT_20261020.md',
    'docs/PR91_SCIENCE_SOURCE_GAPS_20261020.md',
    'src/common/cloud_bal_joint_transport.f90',
    'tests/test_joint_qnb_transport.f90',
    'tests/test_pr90_rain_final_psd.py',
    'tests/test_pr91_fogdes_store_contract.py',
    'tests/test_pr91_history_response.py',
    'tests/test_pr91_host_store_replay.py',
    'tests/test_pr91_host_store_trace.py',
    'tests/test_pr91_inactive_ice_store_c14.py',
    'tests/test_pr91_source_first_diffusion.py',
    'tests/test_pr91_source_first_diffusion_c11.py',
    'tests/test_pr91_source_store_contract.py',
    'tools/pr91_fogdes_store_contract.py',
    'tools/pr91_history_response.py',
    'tools/pr91_host_store_replay.py',
    'tools/pr91_host_store_trace.py',
    'tools/pr91_inactive_ice_store_c14.py',
    'tools/pr91_source_first_diffusion.py',
    'tools/pr91_source_first_diffusion_c11.py',
    'tools/pr91_source_store_contract.py',
    'tools/pr91_virtual_donor_capture.py',
})  # Draft-only maintained source/code/docs allowlist; regenerate against final publication commit.
APPROVED_SELECTED_PATHS=frozenset(['docs/PR91_HISTORY_RESPONSE_20261020.md',
 'docs/PR91_HOST_STORE_CONTRACT_20261020.md',
 'docs/PR91_SCIENCE_SOURCE_GAPS_20261020.md',
 'docs/evidence/pr91_history_response_20261020/README.md',
 'docs/evidence/pr91_history_response_20261020/SHA256SUMS',
 'docs/evidence/pr91_history_response_20261020/maps/c7_geopotential_transient_maps.png',
 'docs/evidence/pr91_history_response_20261020/maps/c7_pressure_transient_maps.png',
 'docs/evidence/pr91_history_response_20261020/maps/c7_vertical_velocity_transient_maps.png',
 'docs/evidence/pr91_history_response_20261020/native_continuity_feasibility.json',
 'docs/evidence/pr91_history_response_20261020/response.json',
 'docs/evidence/pr91_host_store_20261020/authored_whitespace_check.json',
 'docs/evidence/pr91_host_store_20261020/core_affected_graph_query.txt',
 'docs/evidence/pr91_host_store_20261020/core_graph_guidance.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/audit_prefix.py',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/capture.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/closed_run.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/diagnostic_identity.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/fallback_events.txt',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/pr91_actual_store_failures.raw',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/pr91_actual_store_failures.raw.gz',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/producer_endpoint_store_probe_o0_o2.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/receipt.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/rk3_targeted_margin_summary.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/source_chain_probe.f90',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/source_chain_probe_o0.txt',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/source_chain_probe_o2.txt',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/source_endpoint_virtual_donor_chain.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/sources.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/step9_prefix.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_d3/store_replay_o0_o2.json',
 'docs/evidence/pr91_host_store_20261020/diagnostic_team_review.md',
 'docs/evidence/pr91_host_store_20261020/final_c13_validation/root_receipt.json',
 'docs/evidence/pr91_host_store_20261020/final_c14/source_pins.json',
 'docs/evidence/pr91_host_store_20261020/final_validation.json',
 'docs/evidence/pr91_host_store_20261020/graph_guidance.json',
 'docs/evidence/pr91_host_store_20261020/investigation_history.md',
 'docs/evidence/pr91_host_store_20261020/pr91_integration_manifest.json',
 'docs/evidence/pr91_host_store_20261020/pr91_integration_validation_summary.json',
 'docs/evidence/pr91_host_store_20261020/raw_log_publication_presence.json',
 'docs/evidence/pr91_host_store_20261020/replay_provenance/d3_bound_replay.json',
 'docs/evidence/pr91_host_store_20261020/replay_provenance/manifest.json',
 'docs/evidence/pr91_host_store_20261020/replay_provenance/shared_instrumenter_regression.json',
 'docs/evidence/pr91_host_store_20261020/reviews/prepr_gate_review_v1.md',
 'docs/evidence/pr91_host_store_20261020/reviews/source_team_review.md',
 'docs/evidence/pr91_host_store_20261020/validation/README.md',
 'docs/evidence/pr91_host_store_20261020/validation/SHA256SUMS',
 'docs/evidence/pr91_host_store_20261020/validation/artifacts.json',
 'docs/evidence/pr91_host_store_20261020/validation/final_i/cloud_bal_joint_transport.f90',
 'docs/evidence/pr91_host_store_20261020/validation/final_i/module_em.F',
 'docs/evidence/pr91_host_store_20261020/validation/final_i/original_c7_core.f90',
 'docs/evidence/pr91_host_store_20261020/validation/final_i/pr91_actual_store_failures.raw',
 'docs/evidence/pr91_host_store_20261020/validation/final_i/pr91_host_store_trace.py',
 'docs/evidence/pr91_host_store_20261020/validation/final_i/test_joint_qnb_transport.f90',
 'docs/evidence/pr91_host_store_20261020/validation/final_i/test_pr91_host_store_trace.py',
 'docs/evidence/pr91_host_store_20261020/validation/final_i/writer.f90',
 'docs/evidence/pr91_host_store_20261020/validation/native_d3/module_em.compile.log',
 'docs/evidence/pr91_host_store_20261020/validation/native_d3/pr87_native_overlay_build.json',
 'docs/evidence/pr91_host_store_20261020/validation/prefix_step9.json',
 'docs/evidence/pr91_science_sources_20261020/admission_proxy_area_weighted.json',
 'docs/evidence/pr91_science_sources_20261020/c10_independent_review.md',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/exact_rational_result.json',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/historical_consistent_positive_endpoint/exact_rational_result.json',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/historical_consistent_positive_endpoint/ifx_o0_o2.log',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/historical_consistent_positive_endpoint/review.md',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/historical_consistent_positive_endpoint/roundoff_probe.f90',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/historical_consistent_positive_endpoint/run_command.txt',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/historical_independent_endpoints/README.md',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/historical_independent_endpoints/exact_rational_result.json',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/historical_independent_endpoints/ifx_o0_o2.log',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/historical_independent_endpoints/roundoff_probe.f90',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/ifx_o0_o2.log',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/pr87_embedded_r128_kernel.f90',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/review.md',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/roundoff_probe.f90',
 'docs/evidence/pr91_science_sources_20261020/c10_roundoff_probe/run_command.txt',
 'docs/evidence/pr91_science_sources_20261020/c11_capture_arithmetic/README.md',
 'docs/evidence/pr91_science_sources_20261020/c11_capture_arithmetic/c11_capture_arithmetic.json',
 'docs/evidence/pr91_science_sources_20261020/c12_source_stage_mean_check.json',
 'docs/evidence/pr91_science_sources_20261020/c13_ice_underflow_review/README.md',
 'docs/evidence/pr91_science_sources_20261020/c13_ice_underflow_review/c13_off_live_identity.json',
 'docs/evidence/pr91_science_sources_20261020/c13_ice_underflow_review/c13_off_rsl_context.txt',
 'docs/evidence/pr91_science_sources_20261020/c13_ice_underflow_review/c13_off_t9_rk2_pair2_full_row.txt',
 'docs/evidence/pr91_science_sources_20261020/c13_source_correction_row/README.md',
 'docs/evidence/pr91_science_sources_20261020/c13_source_correction_row/c12_coupled_identity.json',
 'docs/evidence/pr91_science_sources_20261020/c13_source_correction_row/c13_coupled_live_identity.json',
 'docs/evidence/pr91_science_sources_20261020/c13_source_correction_row/comparison.json',
 'docs/evidence/pr91_science_sources_20261020/c13_source_correction_row/matched_rows.txt',
 'docs/evidence/pr91_science_sources_20261020/c13_strict_mean_trial/README.md',
 'docs/evidence/pr91_science_sources_20261020/c13_strict_mean_trial/ifx_o0.log',
 'docs/evidence/pr91_science_sources_20261020/c13_strict_mean_trial/ifx_o2.log',
 'docs/evidence/pr91_science_sources_20261020/c13_strict_mean_trial/manifest.json',
 'docs/evidence/pr91_science_sources_20261020/c13_strict_mean_trial/strict_mean_hex.f90',
 'docs/evidence/pr91_science_sources_20261020/c14_current_response/cold_area_weighted.json',
 'docs/evidence/pr91_science_sources_20261020/c14_current_response/current_candidate_note.md',
 'docs/evidence/pr91_science_sources_20261020/c14_current_response/guarded_reproduction_check.json',
 'docs/evidence/pr91_science_sources_20261020/c14_current_response/guarded_reproduction_manifest.json',
 'docs/evidence/pr91_science_sources_20261020/c14_current_response/independent_review.md',
 'docs/evidence/pr91_science_sources_20261020/c14_current_response/reproduce_summary.py',
 'docs/evidence/pr91_science_sources_20261020/c14_current_response/reproduction_README.md',
 'docs/evidence/pr91_science_sources_20261020/c14_current_response/summary.json',
 'docs/evidence/pr91_science_sources_20261020/c14_t15_source_identity/independent_review.md',
 'docs/evidence/pr91_science_sources_20261020/c14_t15_source_identity/source_event.json',
 'docs/evidence/pr91_science_sources_20261020/c14_t15_source_identity/source_event.md',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/README.md',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/focused_command.sh',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/joint_transport_o0.log',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/joint_transport_o0_combined.log',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/joint_transport_o2.log',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/joint_transport_o2_combined.log',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/joint_transport_recheck_command.sh',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/pytest.log',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/source_first_recheck_command.sh',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/source_first_test_rerun.log',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/source_pins.json',
 'docs/evidence/pr91_science_sources_20261020/final_c12_validation/toolchain.txt',
 'docs/evidence/pr91_science_sources_20261020/final_c13_validation/README.md',
 'docs/evidence/pr91_science_sources_20261020/final_c13_validation/final_positive_flux_two_cases.log',
 'docs/evidence/pr91_science_sources_20261020/final_c13_validation/focused_command.sh',
 'docs/evidence/pr91_science_sources_20261020/final_c13_validation/pre_fix_baseline/README.md',
 'docs/evidence/pr91_science_sources_20261020/final_c13_validation/pre_fix_baseline/command.log',
 'docs/evidence/pr91_science_sources_20261020/final_c13_validation/pre_fix_baseline/focused_command.sh',
 'docs/evidence/pr91_science_sources_20261020/final_c13_validation/pre_fix_baseline/pytest.log',
 'docs/evidence/pr91_science_sources_20261020/final_c13_validation/pre_fix_baseline/toolchain.txt',
 'docs/evidence/pr91_science_sources_20261020/final_c13_validation/source_pins.json',
 'docs/evidence/pr91_science_sources_20261020/final_c13_validation/superseding_two_cases.sh',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/README.md',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/attempt_01_failure.json',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/attempt_01_pytest.log',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/final_validation_pre_portable_binding.json',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/focused_command.sh',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/independent_source_review.md',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/portable_binding_review.md',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/portable_commit_check.json',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/pytest.log',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/source_pins.json',
 'docs/evidence/pr91_science_sources_20261020/final_c14_validation/toolchain.txt',
 'docs/evidence/pr91_science_sources_20261020/focused_regression.json',
 'docs/evidence/pr91_science_sources_20261020/focused_regression.log',
 'docs/evidence/pr91_science_sources_20261020/focused_regression_c10.json',
 'docs/evidence/pr91_science_sources_20261020/focused_regression_c10.log',
 'docs/evidence/pr91_science_sources_20261020/focused_regression_c10_command.txt',
 'docs/evidence/pr91_science_sources_20261020/focused_regression_command.txt',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/direct_interp_288.json',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/independent_review.md',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/laps_qc_horizontal_rows.json',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/METGRID.TBL',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/README.md',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/SHA256SUMS',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/commands.sh',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/enumerate_target_support.f90',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/extract_laps.f90',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/grid_rows_288.f90',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/grid_rows_288.out',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/grid_rows_288_wrong_radius.f90',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/grid_rows_288_wrong_radius.out',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/inverse_support_rows.txt',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/make_grid_coords.py',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/make_targets.py',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/manifest.json',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/operator_source/interp_module.F',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/operator_source/llxy_module.F',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/operator_source/module_map_utils.F',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/operator_source/process_domain_module.F',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/operator_source/read_met_module.F',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/pressures.txt',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/qc_headers.txt',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/qc_levels.txt.gz',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/rebuild_footprint.py',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/replay_build.log',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/scan.log',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/bitarray_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/bitarray_module.o',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/cio.o',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/constants_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/datatype_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/date_pack.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/gridinfo_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/input_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/interp_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/interp_option_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/list_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/llxy_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/map_utils.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/met_data_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/minheap_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/misc_definitions_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/module_debug.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/module_debug.o',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/module_internal_header_util.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/module_mergesort.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/mpas_mesh.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/output_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/parallel_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/parallel_module.o',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/process_domain_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/queue_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/queue_module.o',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/read_met_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/remapper.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/rotate_winds_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/scan_input.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/storage_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/stringutil.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/target_mesh.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/wrf_debug__genmod.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/wrf_error_fatal3__genmod.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/wrf_error_fatal__genmod.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/wrf_message__genmod.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/support_objects/write_met_module.mod',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/target_grid_234x282.txt',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/target_grid_234x282.txt.gz',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/targets_288.txt',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/toolchain/intel_toolchain.sh',
 'docs/evidence/pr91_science_sources_20261020/horizontal_replay/replay_18level/validity_summary.txt',
 'docs/evidence/pr91_science_sources_20261020/joint_qnb_transport.log',
 'docs/evidence/pr91_science_sources_20261020/publication_review.md',
 'docs/evidence/pr91_science_sources_20261020/source_audit.json',
 'docs/evidence/pr91_science_sources_20261020/support_lookup.json',
 'docs/evidence/pr91_science_sources_20261020/support_operator_lookup.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/README.md',
 'docs/evidence/pr91_source_store_contract_20261020/c10/SHA256SUMS',
 'docs/evidence/pr91_source_store_contract_20261020/c10/c9_failed_runs/COUPLED_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/c9_failed_runs/COUPLED_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/c9_failed_runs/OFF_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/c9_failed_runs/OFF_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/c9_failed_runs/pr85_joint_source_failure.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c10/c9_failed_runs/summary.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/coupled_joint_transport_budget.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c10/coupled_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/coupled_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/coupled_rsl.error.0000.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c10/coupled_source_diffusion.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c10/evidence_manifest.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/focused_test.log',
 'docs/evidence/pr91_source_store_contract_20261020/c10/intel_toolchain.sh',
 'docs/evidence/pr91_source_store_contract_20261020/c10/module_em.F',
 'docs/evidence/pr91_source_store_contract_20261020/c10/module_em.compile.log',
 'docs/evidence/pr91_source_store_contract_20261020/c10/native_overlay_build.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/off_joint_transport_budget.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c10/off_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/off_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/off_rsl.error.0000.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c10/off_source_diffusion.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c10/overrides.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/pr87_horizontal_diffusion64.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c10/pr91_source_first_diffusion.py',
 'docs/evidence/pr91_source_store_contract_20261020/c10/solve_em.F',
 'docs/evidence/pr91_source_store_contract_20261020/c10/solve_em.compile.log',
 'docs/evidence/pr91_source_store_contract_20261020/c10/sources.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/t2_fixture/classification.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10/t2_fixture/cloud_bal_joint_transport.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c10/t2_fixture/driver.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c10/t2_fixture/o0.out',
 'docs/evidence/pr91_source_store_contract_20261020/c10/t2_fixture/o2.out',
 'docs/evidence/pr91_source_store_contract_20261020/c10/test_pr91_source_first_diffusion.py',
 'docs/evidence/pr91_source_store_contract_20261020/c10_independent_review.md',
 'docs/evidence/pr91_source_store_contract_20261020/c10_live_run_identity.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10_t20_completed_prefix_audit.json',
 'docs/evidence/pr91_source_store_contract_20261020/c10_t20_completed_prefix_audit.md',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/README.md',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/SHA256SUMS',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/attempts.json',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/c11d_off_live_identity.json',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/c11d_off_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/focused_test_c11.py',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/module_em_c11d.F',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/native_build_stdout_c11d.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/native_overlay_build_c11d.json',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/native_replay/README.md',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/native_replay/SHA256SUMS',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/native_replay/driver.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/native_replay/kernel_c10_embedded.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/native_replay/manifest.json',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/native_replay/replay_output.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/native_replay/replay_output_O0.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/overrides_c11d.json',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/pr85_joint_source_failure_c11d_off.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/prefix_comparison.json',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/solve_em_c10.F',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/source_transform_c11.py',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/sources_c11d.json',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/writer_fixture/driver.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/writer_fixture/kernel.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/writer_fixture/manifest.json',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/writer_fixture/pr85_joint_source_failure_O0.raw',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/writer_fixture/pr85_joint_source_failure_O2.raw',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/writer_fixture/stdout_O0.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c11d/writer_fixture/stdout_O2.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c12/README.md',
 'docs/evidence/pr91_source_store_contract_20261020/c12/SHA256SUMS',
 'docs/evidence/pr91_source_store_contract_20261020/c12/generated/module_em.F',
 'docs/evidence/pr91_source_store_contract_20261020/c12/generated/solve_em.F',
 'docs/evidence/pr91_source_store_contract_20261020/c12/independent_review.md',
 'docs/evidence/pr91_source_store_contract_20261020/c12/inputs/solve_em_c7.F',
 'docs/evidence/pr91_source_store_contract_20261020/c12/manifest.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/native_replay/README.md',
 'docs/evidence/pr91_source_store_contract_20261020/c12/native_replay/SHA256SUMS',
 'docs/evidence/pr91_source_store_contract_20261020/c12/native_replay/c12_nond_expression.f90.inc',
 'docs/evidence/pr91_source_store_contract_20261020/c12/native_replay/cloud_bal_joint_transport.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c12/native_replay/commands.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c12/native_replay/driver.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c12/native_replay/kernel_c10_embedded.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c12/native_replay/manifest.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/native_replay/output_O0.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c12/native_replay/output_O2.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/closed_audit.py',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/closed_runtime_audit.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/coupled_joint_transport_budget.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/coupled_live_identity.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/coupled_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/coupled_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/coupled_rsl.error.0000.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/coupled_source_diffusion.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/coupled_source_failure.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/native_overlay_build.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/off_joint_transport_budget.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/off_live_identity.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/off_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/off_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/off_rsl.error.0000.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/off_source_diffusion.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c12/runtime/off_source_failure.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c12/t3_source_replay/README.md',
 'docs/evidence/pr91_source_store_contract_20261020/c12/t3_source_replay/captured_failure.raw',
 'docs/evidence/pr91_source_store_contract_20261020/c12/t3_source_replay/cloud_bal_joint_transport.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c12/t3_source_replay/driver.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c12/t3_source_replay/manifest.json',
 'docs/evidence/pr91_source_store_contract_20261020/c12/t3_source_replay/output_O0.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c12/t3_source_replay/output_O2.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c12/t3_source_replay/run.sh',
 'docs/evidence/pr91_source_store_contract_20261020/c12/transform/pr91_source_first_diffusion.py',
 'docs/evidence/pr91_source_store_contract_20261020/c12/transform/pr91_source_first_diffusion_c11.py',
 'docs/evidence/pr91_source_store_contract_20261020/c12/transform/pr91_virtual_donor_capture.py',
 'docs/evidence/pr91_source_store_contract_20261020/c12/validation/focused_tests.log',
 'docs/evidence/pr91_source_store_contract_20261020/c12/validation/intel_toolchain.sh',
 'docs/evidence/pr91_source_store_contract_20261020/c12/validation/test_pr91_source_first_diffusion.py',
 'docs/evidence/pr91_source_store_contract_20261020/c12/validation/test_pr91_source_first_diffusion_c11.py',
 'docs/evidence/pr91_source_store_contract_20261020/c12_independent_review.md',
 'docs/evidence/pr91_source_store_contract_20261020/c13/README.md',
 'docs/evidence/pr91_source_store_contract_20261020/c13/SHA256SUMS',
 'docs/evidence/pr91_source_store_contract_20261020/c13/generated/module_bl_fogdes.F',
 'docs/evidence/pr91_source_store_contract_20261020/c13/independent_review.md',
 'docs/evidence/pr91_source_store_contract_20261020/c13/inputs/cloud_bal_joint_transport.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c13/inputs/module_bl_fogdes_c12.F',
 'docs/evidence/pr91_source_store_contract_20261020/c13/manifest.json',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/closed_audit.py',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/closed_runtime_audit.json',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/coupled_live_identity.json',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/coupled_pr85_joint_source_diffusion.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/coupled_pr85_joint_source_failure.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/coupled_pr85_joint_transport_budget.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/coupled_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/coupled_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/coupled_rsl.error.0000.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/native_overlay_build.json',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/off_live_identity.json',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/off_pr85_joint_source_diffusion.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/off_pr85_joint_source_failure.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/off_pr85_joint_transport_budget.raw.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/off_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/off_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c13/runtime/off_rsl.error.0000.gz',
 'docs/evidence/pr91_source_store_contract_20261020/c13/transform/pr91_fogdes_store_contract.py',
 'docs/evidence/pr91_source_store_contract_20261020/c13/validation/focused_test.log',
 'docs/evidence/pr91_source_store_contract_20261020/c13/validation/test_pr91_fogdes_store_contract.py',
 'docs/evidence/pr91_source_store_contract_20261020/c14/README.md',
 'docs/evidence/pr91_source_store_contract_20261020/c14/SHA256SUMS',
 'docs/evidence/pr91_source_store_contract_20261020/c14/build_binding.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/build_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/cloud_bal_joint_transport.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c14/core_consumer_symbols.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/dedup_byte_comparison.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/focused_test.log',
 'docs/evidence/pr91_source_store_contract_20261020/c14/fp_probe.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c14/fp_probe_O0.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c14/fp_probe_O2.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c14/inputs/module_bl_fogdes_c12.F',
 'docs/evidence/pr91_source_store_contract_20261020/c14/inputs/module_em_c12.F',
 'docs/evidence/pr91_source_store_contract_20261020/c14/manifest.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/module_bl_fogdes.F',
 'docs/evidence/pr91_source_store_contract_20261020/c14/module_em.F',
 'docs/evidence/pr91_source_store_contract_20261020/c14/original_c7_core.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c14/pr91_host_store_trace.py',
 'docs/evidence/pr91_source_store_contract_20261020/c14/pr91_inactive_ice_store_c14.py',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/README.md',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/closed_audit.py',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/closed_runtime_audit.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/coupled_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/coupled_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/coverage_selector_attempt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/independent_review.md',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/off_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/off_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/runtime_summary.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/README.md',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/closed_audit_600.py',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/closed_runtime_audit_600.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/completion_partition_600.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/coupled_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/coupled_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/failure_context_600.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/off_preflight.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/off_receipt.json',
 'docs/evidence/pr91_source_store_contract_20261020/c14/solve_em.F',
 'docs/evidence/pr91_source_store_contract_20261020/c14/test_joint_qnb_transport.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c14/test_pr91_host_store_trace.py',
 'docs/evidence/pr91_source_store_contract_20261020/c14/test_pr91_inactive_ice_store_c14.py',
 'docs/evidence/pr91_source_store_contract_20261020/c9/SHA256SUMS',
 'docs/evidence/pr91_source_store_contract_20261020/c9/c8_final_generator_verification.json',
 'docs/evidence/pr91_source_store_contract_20261020/c9/c8_original_sources.json',
 'docs/evidence/pr91_source_store_contract_20261020/c9/focused_test.log',
 'docs/evidence/pr91_source_store_contract_20261020/c9/focused_test_command.json',
 'docs/evidence/pr91_source_store_contract_20261020/c9/intel_compiler.txt',
 'docs/evidence/pr91_source_store_contract_20261020/c9/intel_toolchain.sh',
 'docs/evidence/pr91_source_store_contract_20261020/c9/module_em.compile.log',
 'docs/evidence/pr91_source_store_contract_20261020/c9/module_em_c9.F',
 'docs/evidence/pr91_source_store_contract_20261020/c9/native_overlay_build.json',
 'docs/evidence/pr91_source_store_contract_20261020/c9/overrides.json',
 'docs/evidence/pr91_source_store_contract_20261020/c9/pr87_horizontal_diffusion64.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c9/pr91_source_first_diffusion.py',
 'docs/evidence/pr91_source_store_contract_20261020/c9/solve_em.compile.log',
 'docs/evidence/pr91_source_store_contract_20261020/c9/solve_em_c9.F',
 'docs/evidence/pr91_source_store_contract_20261020/c9/source_causal_flow.md',
 'docs/evidence/pr91_source_store_contract_20261020/c9/source_prepared_diffusion_driver.f90',
 'docs/evidence/pr91_source_store_contract_20261020/c9/sources.json',
 'docs/evidence/pr91_source_store_contract_20261020/c9/test_pr91_source_first_diffusion.py',
 'docs/evidence/pr91_source_store_contract_20261020/c9_live_run_identity.json',
 'docs/evidence/pr91_source_store_contract_20261020/c9_t20_completed_prefix_audit.json',
 'docs/evidence/pr91_source_store_contract_20261020/c9_t20_completed_prefix_audit.md',
 'docs/evidence/pr91_source_store_contract_20261020/source_first_diffusion_review.md',
 'docs/evidence/pr91_source_store_contract_20261020/source_store_contract_review.md',
 'src/common/cloud_bal_joint_transport.f90',
 'tests/test_joint_qnb_transport.f90',
 'tests/test_pr90_rain_final_psd.py',
 'tests/test_pr91_fogdes_store_contract.py',
 'tests/test_pr91_history_response.py',
 'tests/test_pr91_host_store_replay.py',
 'tests/test_pr91_host_store_trace.py',
 'tests/test_pr91_inactive_ice_store_c14.py',
 'tests/test_pr91_source_first_diffusion.py',
 'tests/test_pr91_source_first_diffusion_c11.py',
 'tests/test_pr91_source_store_contract.py',
 'tools/pr91_fogdes_store_contract.py',
 'tools/pr91_history_response.py',
 'tools/pr91_host_store_replay.py',
 'tools/pr91_host_store_trace.py',
 'tools/pr91_inactive_ice_store_c14.py',
 'tools/pr91_source_first_diffusion.py',
 'tools/pr91_source_first_diffusion_c11.py',
 'tools/pr91_source_store_contract.py',
 'tools/pr91_virtual_donor_capture.py'])
GRAPH_SOURCE_PATHS=frozenset(['docs/PR91_HISTORY_RESPONSE_20261020.md',
 'docs/PR91_HOST_STORE_CONTRACT_20261020.md',
 'docs/PR91_SCIENCE_SOURCE_GAPS_20261020.md',
 'src/common/cloud_bal_joint_transport.f90',
 'tests/test_joint_qnb_transport.f90',
 'tests/test_pr90_rain_final_psd.py',
 'tests/test_pr91_fogdes_store_contract.py',
 'tests/test_pr91_history_response.py',
 'tests/test_pr91_host_store_replay.py',
 'tests/test_pr91_host_store_trace.py',
 'tests/test_pr91_inactive_ice_store_c14.py',
 'tests/test_pr91_source_first_diffusion.py',
 'tests/test_pr91_source_first_diffusion_c11.py',
 'tests/test_pr91_source_store_contract.py',
 'tools/pr91_fogdes_store_contract.py',
 'tools/pr91_history_response.py',
 'tools/pr91_host_store_replay.py',
 'tools/pr91_host_store_trace.py',
 'tools/pr91_inactive_ice_store_c14.py',
 'tools/pr91_source_first_diffusion.py',
 'tools/pr91_source_first_diffusion_c11.py',
 'tools/pr91_source_store_contract.py',
 'tools/pr91_virtual_donor_capture.py'])

OLD_AUDIT=MAINT/'scratch/pr59_team_audit_20261006'
OLD_PUBLISH=MAINT/'scratch/pr59_publish_kg_20261002'
DELEGATED_UPDATER=OLD_PUBLISH/'update.py'
DELEGATED_UPDATER_SHA256='7c626b398f44a4013a607e2a5ae932528d2caaf41e37a479366aa80e0b146aa0'
DELEGATED_AUDITOR=OLD_AUDIT/'update_kg.py'
DELEGATED_AUDITOR_SHA256='bfe6242618e8ca1b60ab1304221d1fd215476d7f23281b69e48963611c0b76e1'
INTEGRATION_PATH='docs/evidence/pr91_host_store_20261020/pr91_integration_manifest.json'
VALIDATION_PATH='docs/evidence/pr91_host_store_20261020/final_validation.json'
VALIDATION_SHA256='093e746ec981b9b3d51b1f49ea1e52d4d58d8512d21631f08fabcdb31e5a40c9'  # Portable 63-test C14 receipt; final commit binding remains external.
VALIDATION_SCHEMA='pr91_final_intel_validation_v1'
VALIDATION_TEST_COUNT=63
VALIDATION_SOURCE_ALIASES={
    '/var/tmp/pr91_native_build_c14_20261020/pr87_native_overlay_build.json':'docs/evidence/pr91_source_store_contract_20261020/c14/build_receipt.json',
    '/var/tmp/pr91_sources_c10_20261020/module_em.F':'docs/evidence/pr91_source_store_contract_20261020/c10/module_em.F',
    '/var/tmp/pr91_sources_c11_20261020d/module_em.F':'docs/evidence/pr91_source_store_contract_20261020/c11d/module_em_c11d.F',
    '/var/tmp/pr91_sources_c12c_20261020/solve_em.F':'docs/evidence/pr91_source_store_contract_20261020/c12/generated/solve_em.F',
    '/var/tmp/pr91_sources_c14_20261020/module_em.F':'docs/evidence/pr91_source_store_contract_20261020/c14/module_em.F',
}
VALIDATION_SOURCE_PATHS=frozenset({
    'docs/evidence/pr91_host_store_20261020/final_c13_validation/root_receipt.json',
    'docs/evidence/pr91_host_store_20261020/final_c14/source_pins.json',
    'docs/evidence/pr91_host_store_20261020/validation/final_i/original_c7_core.f90',
    'docs/evidence/pr91_science_sources_20261020/final_c14_validation/focused_command.sh',
    'docs/evidence/pr91_science_sources_20261020/final_c14_validation/independent_source_review.md',
    'docs/evidence/pr91_science_sources_20261020/final_c14_validation/pytest.log',
    'docs/evidence/pr91_science_sources_20261020/final_c14_validation/toolchain.txt',
    'docs/evidence/pr91_source_store_contract_20261020/c10/module_em.F',
    'docs/evidence/pr91_source_store_contract_20261020/c11d/module_em_c11d.F',
    'docs/evidence/pr91_source_store_contract_20261020/c12/generated/module_em.F',
    'docs/evidence/pr91_source_store_contract_20261020/c12/generated/solve_em.F',
    'docs/evidence/pr91_source_store_contract_20261020/c13/generated/module_bl_fogdes.F',
    'docs/evidence/pr91_source_store_contract_20261020/c14/build_receipt.json',
    'docs/evidence/pr91_source_store_contract_20261020/c14/module_em.F',
    'src/common/cloud_bal_joint_transport.f90',
    'tests/intel_toolchain.sh',
    'tests/test_joint_qnb_transport.f90',
    'tests/test_pr85_kdm6_warm_process.py',
    'tests/test_pr87_cloud_public_store.py',
    'tests/test_pr87_qn_density_storage.py',
    'tests/test_pr87_rain_density_storage.py',
    'tests/test_pr87_rain_public_store.py',
    'tests/test_pr87_rain_storage_contract.py',
    'tests/test_pr87_rain_volume_store.py',
    'tests/test_pr87_source_storage_failures.py',
    'tests/test_pr90_joint_store_reason.py',
    'tests/test_pr90_rain_failure_replay.py',
    'tests/test_pr90_rain_final_psd.py',
    'tests/test_pr90_rain_producer_trace.py',
    'tests/test_pr90_rain_public_roundtrip.py',
    'tests/test_pr90_warm_rain_output.py',
    'tests/test_pr91_fogdes_store_contract.py',
    'tests/test_pr91_history_response.py',
    'tests/test_pr91_host_store_replay.py',
    'tests/test_pr91_host_store_trace.py',
    'tests/test_pr91_inactive_ice_store_c14.py',
    'tests/test_pr91_source_first_diffusion.py',
    'tests/test_pr91_source_first_diffusion_c11.py',
    'tests/test_pr91_source_store_contract.py',
    'tools/pr87_horizontal_diffusion64.f90',
    'tools/pr87_kdm6_ng_base_diag.py',
    'tools/pr87_rain_density_storage.py',
    'tools/pr87_rain_storage_contract.py',
    'tools/pr87_source_storage_failures.py',
    'tools/pr90_prepare_native_roundtrip.py',
    'tools/pr90_rain_failure_replay.py',
    'tools/pr90_rain_final_psd.py',
    'tools/pr90_rain_producer_trace.py',
    'tools/pr90_warm_rain_output.py',
    'tools/pr91_fogdes_store_contract.py',
    'tools/pr91_history_response.py',
    'tools/pr91_host_store_replay.py',
    'tools/pr91_host_store_trace.py',
    'tools/pr91_inactive_ice_store_c14.py',
    'tools/pr91_source_first_diffusion.py',
    'tools/pr91_source_first_diffusion_c11.py',
    'tools/pr91_source_store_contract.py',
})  # Exact normalized 57-path C14 source pin set.
VALIDATION_UNCHANGED_SOURCE_PATHS=frozenset({
    'tests/intel_toolchain.sh',
    'tests/test_pr85_kdm6_warm_process.py',
    'tests/test_pr87_cloud_public_store.py',
    'tests/test_pr87_qn_density_storage.py',
    'tests/test_pr87_rain_density_storage.py',
    'tests/test_pr87_rain_public_store.py',
    'tests/test_pr87_rain_storage_contract.py',
    'tests/test_pr87_rain_volume_store.py',
    'tests/test_pr87_source_storage_failures.py',
    'tests/test_pr90_joint_store_reason.py',
    'tests/test_pr90_rain_failure_replay.py',
    'tests/test_pr90_rain_producer_trace.py',
    'tests/test_pr90_rain_public_roundtrip.py',
    'tests/test_pr90_warm_rain_output.py',
    'tools/pr87_horizontal_diffusion64.f90',
    'tools/pr87_kdm6_ng_base_diag.py',
    'tools/pr87_rain_density_storage.py',
    'tools/pr87_rain_storage_contract.py',
    'tools/pr87_source_storage_failures.py',
    'tools/pr90_prepare_native_roundtrip.py',
    'tools/pr90_rain_failure_replay.py',
    'tools/pr90_rain_final_psd.py',
    'tools/pr90_rain_producer_trace.py',
    'tools/pr90_warm_rain_output.py',
})
INTEL_PROFILE_SHA256='5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4'
INTEGRATION_SHA256='647afbc1c1199149d4a07051d18e9fb315d6bd9583ad4febd1846e9a51a78ac8'
EXPECTED_COMMIT='d34c6db9279275efe41af449dc9bda95975ea493'
EXPECTED_PR_URL=DRAFT_PR_URL  # Actual draft PR URL; source/evidence/runtime readiness remains false.
INTEGRATION_SCHEMA='pr91_host_store_integration_v1'
PRIOR_SNAPSHOT='2026-10-19-rain-roundtrip'
SNAPSHOT='2026-10-20-host-store'
MAINTAINED_SOURCE_SHA256='0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f'
ALLOWLIST_FROZEN=True
PR=EXPECTED_PR_URL
INHERITED_OPEN_GATES={'initial_shock_and_forecast': 'OPEN: initial response characterization and matched longer-time response not '
                               'scientifically approved.',
 'joint_absence': 'C7 T180 same-event weighted signed changes accounted descriptively; final budget remains OPEN.',
 'local_cold_activity': 'C14 area-weighted cold summary is descriptive; large AUT/G deferral justification '
                        'remains OPEN.',
 'matched_history': 'C7 T0/T60/T120/T180 history remains descriptive 27-column support; not a general forecast '
                    'conclusion.',
 'native_mass_wind': 'OPEN: physical face-flux continuity and momentum validation.',
 'number_budget': 'OPEN: final raw number cap is not generally logged; only local boundary event evidence is '
                  'available.',
 'observation_support': 'QC horizontal source component COMPLETE for 16 target columns, 36 nonzero source links, '
                        'and 288/288 matches over 18 pressure levels. Other field-specific horizontal transfer '
                        'and real.exe pressure-to-native-eta influence remain OPEN.',
 'source_event': 'C14 T15 pair-4 source/diffusion identity event is localized by bounded evidence; upstream '
                 'physical/numerical cause remains OPEN.',
 'water_and_energy': 'OPEN: host/hybrid carrier and boundary-process closure; no water/energy budget approval.'}
HELPER=Path(__file__).resolve()
GRAPHIFY_PY=Path('/home/korea_keun/.local/share/uv/tools/graphifyy/bin/python3')
GRAPHIFY_CLI=Path('/home/korea_keun/.local/share/uv/tools/graphifyy/bin/graphify')

# Runtime pins remain fail-closed until root freezes paired 240s and 600s
# outcomes, receipts, and executable identity. Diagnostics never substitute.
RUNTIME_FREEZE_READY=True
EXPECTED_RUNTIMES={'240': {'arms': {'COUPLED': {'final_completed_step': 12,
                              'receipt_path': 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/coupled_receipt.json',
                              'receipt_sha256': '9bd0a867987896dc9c6551bbc964e8fd1d2d759cb865827af81346b782a40e48',
                              'returncode': 0,
                              'status': 'COMPLETE',
                              'timestep_count': 12},
                  'OFF': {'final_completed_step': 12,
                          'receipt_path': 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime/off_receipt.json',
                          'receipt_sha256': 'f6a2e40d65c76e4e9abd0dfb1fc26f0c5da3abe4327a5d23829e4a66f34b540a',
                          'returncode': 0,
                          'status': 'COMPLETE',
                          'timestep_count': 12}},
         'executed_executable_sha256': '5581e1be3febd54409304ccf7cbe305830a75968858075bf0d95f68b48d812be',
         'requested_duration_seconds': 240,
         'run_identity': 'PR87 selected-object native candidate',
         'status': 'COMPLETE',
         'timestep_seconds': 20},
 '600': {'arms': {'COUPLED': {'final_completed_step': 14,
                              'receipt_path': 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/coupled_receipt.json',
                              'receipt_sha256': 'cae066b8f8c6c3ff9f5254c397cbe243f031ba3171d4eecb59fcf057f8c0468d',
                              'returncode': 1,
                              'status': 'INCOMPLETE',
                              'timestep_count': 14},
                  'OFF': {'final_completed_step': 14,
                          'receipt_path': 'docs/evidence/pr91_source_store_contract_20261020/c14/runtime600/off_receipt.json',
                          'receipt_sha256': '797be5e60fb0e5983f3d977413db958d6d2fc151b50b58a3627d82ecbe78607f',
                          'returncode': 1,
                          'status': 'INCOMPLETE',
                          'timestep_count': 14}},
         'executed_executable_sha256': '5581e1be3febd54409304ccf7cbe305830a75968858075bf0d95f68b48d812be',
         'requested_duration_seconds': 600,
         'run_identity': 'PR87 selected-object native candidate',
         'status': 'INCOMPLETE',
         'timestep_seconds': 20}}

def sha_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def sha(p:Path)->str:return sha_bytes(p.read_bytes())
def git(*args,cwd=SOURCE):return subprocess.check_output(['git',*args],cwd=cwd,text=True).rstrip()
def fail(msg):raise RuntimeError('guard failed: '+msg)
def regular_file(path:Path):
    if not stat.S_ISREG(path.lstat().st_mode):fail(f'non-regular selected artifact: {path}')
def reject_symlink_ancestors(path:Path):
    for part in (path,*path.parents):
        if part.is_symlink():fail(f'symlinked output component: {part}')

def guard_destination(path:Path,root:Path=ROOT):
    reject_symlink_ancestors(path)
    if not path.resolve().is_relative_to(root.resolve()):
        fail(f'destination escapes expected root {root}: {path}')
    if path.exists():regular_file(path)

def guard_directory(path:Path,root:Path=ROOT):
    reject_symlink_ancestors(path)
    if not path.resolve().is_relative_to(root.resolve()):
        fail(f'directory escapes expected root {root}: {path}')
    if not path.is_dir():fail(f'expected directory: {path}')

def delegated_importer_bindings()->dict:
    bindings={}
    for label,path,expected in (
        ('updater',DELEGATED_UPDATER,DELEGATED_UPDATER_SHA256),
        ('auditor',DELEGATED_AUDITOR,DELEGATED_AUDITOR_SHA256),
    ):
        guard_destination(path,MAINT);regular_file(path)
        actual=sha(path)
        if actual!=expected:fail(f'delegated {label} source SHA drift: {path}')
        bindings[label]={'path':str(path),'sha256':actual}
    return bindings

def validate_closed_runtime(runtime:dict,executable:str)->dict:
    if not RUNTIME_FREEZE_READY:
        fail('freeze exact paired 240-second and 600-second runtime outcomes, executable, and receipt hashes first')
    if 'TODO_' in json.dumps(EXPECTED_RUNTIMES,sort_keys=True):
        fail('closed runtime literals still contain TODO values')
    if not isinstance(EXPECTED_RUNTIMES, dict) or set(EXPECTED_RUNTIMES)!={'240','600'}:
        fail('root must freeze exact 240-second and 600-second closed runtime literals')
    windows=runtime.get('windows')
    if not isinstance(windows,dict) or set(windows)!=set(EXPECTED_RUNTIMES):
        fail('manifest must include exactly the frozen 240-second and 600-second runtime windows')
    closed_windows={}
    window_statuses=[]
    for duration_key in ('240','600'):
        expected=EXPECTED_RUNTIMES[duration_key]
        window=windows[duration_key]
        duration=expected.get('requested_duration_seconds')
        timestep=expected.get('timestep_seconds')
        if duration!=int(duration_key) or timestep!=20 or duration%timestep:
            fail(f'frozen {duration_key}-second window must bind its duration and 20-second timestep')
        if expected.get('status')=='NOT_RUN':
            reason='NOT_RUN because the paired 240-second window closed INCOMPLETE'
            if duration_key!='600' or EXPECTED_RUNTIMES['240'].get('status')!='INCOMPLETE':
                fail('NOT_RUN is allowed only for 600 seconds after a closed INCOMPLETE 240-second window')
            if expected.get('not_run_reason')!=reason or window.get('not_run_reason')!=reason:
                fail('600-second NOT_RUN must state the exact closed-240 failure reason')
            if window.get('status')!='NOT_RUN' or window.get('requested_duration_seconds')!=duration or \
                    window.get('timestep_seconds')!=timestep or 'arms' in window:
                fail('600-second NOT_RUN window must have duration/timestep and no execution arms')
            decision=expected.get('decision_receipt')
            decision_ref=window.get('decision_receipt')
            if not isinstance(decision,dict) or not isinstance(decision_ref,dict) or \
                    decision_ref.get('path')!=decision.get('path') or \
                    decision_ref.get('sha256')!=decision.get('sha256') or \
                    not re.fullmatch(r'[0-9a-f]{64}',str(decision.get('sha256',''))):
                fail('600-second NOT_RUN must bind its frozen decision receipt path and SHA')
            closed_windows[duration_key]={
                'requested_duration_seconds':duration,'timestep_seconds':timestep,
                'expected_timesteps':duration//timestep,'status':'NOT_RUN',
                'not_run_reason':reason,'decision_receipt':dict(decision)}
            window_statuses.append('NOT_RUN')
            continue
        if expected.get('executed_executable_sha256')!=executable:
            fail(f'frozen {duration_key}-second executable differs from the bound native build')
        for key in ('run_identity','requested_duration_seconds','timestep_seconds','status'):
            if window.get(key)!=expected.get(key):
                fail(f'{duration_key}-second manifest {key} differs from frozen closed receipt')
        expected_arms=expected.get('arms')
        arms=window.get('arms')
        if not isinstance(expected_arms,dict) or set(expected_arms)!={'OFF','COUPLED'} or \
                not isinstance(arms,dict) or set(arms)!={'OFF','COUPLED'}:
            fail(f'frozen {duration_key}-second window must include exact OFF and COUPLED outcomes')
        statuses={}
        steps=duration//timestep
        for arm,expected_row in expected_arms.items():
            row=arms[arm]
            if row.get('status')!=expected_row['status']:
                fail(f'{duration_key}-second {arm} manifest status differs from frozen closed receipt')
            if type(row.get('returncode')) is not int or row['returncode']!=expected_row['returncode']:
                fail(f'{duration_key}-second {arm} manifest returncode differs from frozen closed receipt')
            if row.get('final_completed_step')!=expected_row['final_completed_step']:
                fail(f'{duration_key}-second {arm} manifest final step differs from frozen closed receipt')
            if row.get('final_completed_step') is not None and type(row.get('final_completed_step')) is not int:
                fail(f'{duration_key}-second {arm} final step must be an integer or null')
            if row.get('timestep_count')!=expected_row['timestep_count']:
                fail(f'{duration_key}-second {arm} manifest timestep count differs from frozen closed receipt')
            if type(row.get('timestep_count')) is not int:
                fail(f'{duration_key}-second {arm} timestep count must be an integer')
            receipt_ref=row.get('receipt')
            if not isinstance(receipt_ref,dict) or receipt_ref.get('path')!=expected_row['receipt_path']:
                fail(f'{duration_key}-second {arm} receipt path differs from frozen closed receipt')
            if receipt_ref.get('sha256')!=expected_row['receipt_sha256']:
                fail(f'{duration_key}-second {arm} receipt SHA differs from frozen closed receipt')
            status=expected_row['status']
            if status not in ('COMPLETE','INCOMPLETE'):
                fail(f'{duration_key}-second {arm} frozen status must be COMPLETE or INCOMPLETE')
            if type(expected_row['returncode']) is not int:
                fail(f'{duration_key}-second {arm} frozen returncode must be an integer')
            step=expected_row['final_completed_step']
            if step is not None and (type(step) is not int or not 0<=step<=steps):
                fail(f'{duration_key}-second {arm} final step must be null or within its window')
            if type(expected_row['timestep_count']) is not int or not 0<=expected_row['timestep_count']<=steps:
                fail(f'{duration_key}-second {arm} timestep count must be within its window')
            statuses[arm]=status
        aggregate='COMPLETE' if set(statuses.values())=={'COMPLETE'} else 'INCOMPLETE'
        if expected.get('status')!=aggregate or window.get('status')!=aggregate:
            fail(f'{duration_key}-second aggregate status must match its two frozen arm outcomes')
        window_statuses.append(aggregate)
        closed_windows[duration_key]={
            'requested_duration_seconds':duration,'timestep_seconds':timestep,
            'expected_timesteps':steps,'run_identity':expected['run_identity'],
            'status':aggregate,'executed_executable_sha256':executable,
            'arms':{arm:dict(expected_arms[arm]) for arm in ('OFF','COUPLED')}}
    aggregate='COMPLETE' if set(window_statuses)=={'COMPLETE'} else 'INCOMPLETE'
    if runtime.get('status')!=aggregate:
        fail('overall runtime status must match both frozen duration windows')
    return {'status':aggregate,'windows':closed_windows}

def expected_model_timestamps(duration_seconds:int,timestep_seconds:int=20)->list[str]:
    start=datetime(2026,8,16,13)
    return [(start+timedelta(seconds=timestep_seconds*step)).strftime('%Y-%m-%d_%H:%M:%S')
            for step in range(1,duration_seconds//timestep_seconds+1)]

def validate_runtime_receipt(arm:str,receipt:dict,expected:dict,window:dict,executable:str)->None:
    for key in ('status','returncode','timestep_count','final_completed_step'):
        if receipt.get(key)!=expected[key]:fail(f'{arm} receipt {key} differs from frozen final outcome')
    if receipt.get('arm')!=arm:fail(f'{arm} receipt arm identity mismatch')
    duration=window['requested_duration_seconds']
    timestep=window['timestep_seconds']
    steps=window['expected_timesteps']
    if receipt.get('run_identity')!=window['run_identity']:
        fail(f'{arm} receipt run identity differs from frozen final outcome')
    if receipt.get('executed_executable_sha256')!=executable or \
            receipt.get('expected_executed_executable_sha256')!=executable:
        fail(f'{arm} receipt executable differs from frozen candidate build')
    if receipt.get('candidate_build_unchanged') is not True:
        fail(f'{arm} receipt does not certify an unchanged candidate build')
    if receipt.get('source_receipt_unchanged') not in (None,True):
        fail(f'{arm} receipt reports a changed source receipt')
    source_receipt_sha=receipt.get('source_receipt_sha256')
    if not isinstance(source_receipt_sha,str) or not re.fullmatch(r'[0-9a-f]{64}',source_receipt_sha):
        fail(f'{arm} receipt does not bind its input source receipt SHA')
    if receipt.get('changed_staged_inputs') or receipt.get('changed_original_inputs'):
        fail(f'{arm} receipt records changed staged/original inputs')
    expected_times=expected_model_timestamps(duration,timestep)
    if receipt.get('expected_model_timestamps')!=expected_times:
        fail(f'{arm} receipt does not bind the complete {duration}-second timestamp schedule')
    actual=receipt.get('model_timestamps')
    if not isinstance(actual,list) or len(actual)!=expected['timestep_count']:
        fail(f'{arm} receipt timestamp count differs from frozen final outcome')
    actual_times=[row.get('timestamp') for row in actual if isinstance(row,dict)]
    if len(actual_times)!=len(actual) or any(value not in expected_times for value in actual_times):
        fail(f'{arm} receipt contains timestamps outside the {duration}-second schedule')
    actual_positions=[expected_times.index(value) for value in actual_times]
    if actual_positions!=sorted(set(actual_positions)):
        fail(f'{arm} receipt timestamps are duplicated or out of schedule order')
    if actual_times!=expected_times[:expected['timestep_count']]:
        fail(f'{arm} receipt timestamps are not the completed schedule prefix')
    completed=expected['final_completed_step']
    count=expected['timestep_count']
    if (count==0 and completed not in (None,0)) or (count>0 and completed!=count):
        fail(f'{arm} receipt final completed step does not match its timestep count')
    if expected['status']=='COMPLETE':
        if receipt['returncode']!=0 or expected['timestep_count']!=steps or expected['final_completed_step']!=steps:
            fail(f'{arm} COMPLETE status requires rc=0 and {steps} completed timesteps')
        if actual_times!=expected_times:fail(f'{arm} COMPLETE receipt does not contain all {steps} timestamps')
    elif receipt.get('status')!='INCOMPLETE':
        fail(f'{arm} closed unsuccessful run must remain explicitly INCOMPLETE')

def copy_checked(source:Path,target:Path):
    guard_destination(source)
    guard_destination(target)
    source_hash=sha(source)
    shutil.copy2(source,target)
    regular_file(target)
    if sha(source)!=source_hash or sha(target)!=source_hash:
        fail(f'copy verification failed: {source} -> {target}')

def restore_automatic_snapshots(snapshots):
    errors=[]
    for directory,members in snapshots.items():
        previous=Path(directory)
        try:guard_directory(previous)
        except BaseException as error:
            errors.append(f'{previous}: {error}')
            continue
        for name,record in members.items():
            try:
                backup=Path(record['backup'])
                if sha(backup)!=record['sha256']:fail('prior automatic snapshot backup drift')
                copy_checked(backup,previous/name)
                if sha(previous/name)!=record['sha256']:fail('prior snapshot content changed')
            except BaseException as error:
                errors.append(f'{previous/name}: {error}')
        # Unknown concurrent members are preserved; they require explicit review.
        try:
            if {p.name for p in previous.iterdir()}!=set(members):
                fail('prior snapshot membership changed; unknown files preserved')
        except BaseException as error:
            errors.append(f'{previous}: {error}')
    if errors:raise RuntimeError('automatic snapshot restore errors: '+'; '.join(errors))


def snapshot_path(path:Path,root:Path)->dict:
    relative=path.relative_to(root).as_posix()
    info=path.lstat()
    if stat.S_ISLNK(info.st_mode):
        return {'kind':'symlink','target':os.readlink(path)}
    if not stat.S_ISREG(info.st_mode):
        fail(f'non-regular active maintained path: {path}')
    return {'kind':'file','sha256':sha(path)}

def maintained_source_snapshot()->dict:
    """Hash active source/docs/config and tracked root files without traversing scratch trees."""
    allowed_wiki={"wiki/graph-report.md","wiki/graph-report-klaps50.md","wiki/graph-report-cloud-bal.md","wiki/index.md","wiki/log.md"}
    result={}
    for root in (ROOT,MAINT):
        root_git_dir=Path(git('rev-parse','--show-toplevel',cwd=root)).resolve()
        if not root.resolve().is_relative_to(root_git_dir):fail(f'maintained path escapes its Git root: {root}')
        for dirname in ('src','tests','docs','config'):
            base=root/dirname
            if not base.exists() and not base.is_symlink():continue
            if base.is_symlink():
                result[f'{root.name}/{dirname}']=snapshot_path(base,root)
                continue
            for current,dirs,files in os.walk(base,followlinks=False):
                current_path=Path(current)
                for name in list(dirs):
                    child=current_path/name
                    if name in {'scratch','worktrees','.git','graphify-out'}:
                        dirs.remove(name)
                        continue
                    if child.is_symlink():
                        result[f'{root.name}/{child.relative_to(root).as_posix()}']=snapshot_path(child,root)
                        dirs.remove(name)
                for name in files:
                    child=current_path/name
                    rel=child.relative_to(root).as_posix()
                    if root==ROOT and rel in allowed_wiki:continue
                    if child.is_symlink() or child.is_file():
                        result[f'{root.name}/{rel}']=snapshot_path(child,root)
        root_prefix=root.resolve().relative_to(root_git_dir).as_posix()
        # Include immediate tracked root files only; never recurse into scratch/worktrees.
        for child in root.iterdir():
            if not (child.is_file() or child.is_symlink()):continue
            rel=child.relative_to(root).as_posix()
            tracked_path=f'{root_prefix}/{rel}' if root_prefix!='.' else rel
            tracked=subprocess.run(['git','ls-files','--cached','--error-unmatch','--',tracked_path],cwd=root_git_dir,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            if tracked.returncode==0:
                result[f'{root.name}/{rel}']=snapshot_path(child,root)
    for path in sorted((p for p in MAINT.glob('wiki/*') if p.is_file() or p.is_symlink())):
        rel=path.relative_to(MAINT).as_posix()
        if rel in allowed_wiki:continue
        result[f'Cloud-BAL/{rel}']=snapshot_path(path,MAINT)
    return result

def show(commit,path):return subprocess.check_output(['git','show',f'{commit}:{path}'],cwd=SOURCE)

def make_plan(commit:str):
    os.environ['TZ']='Asia/Seoul'; time.tzset()
    if date.today().isoformat()!='2026-10-20':fail('dated snapshot day differs from declared session day')
    if not ALLOWLIST_FROZEN or not isinstance(APPROVED_SELECTED_PATHS, frozenset) or 'TODO_' in EXPECTED_COMMIT or 'TODO_' in EXPECTED_PR_URL:
        fail('freeze the reviewed literal allowlist, source commit, and actual PR URL before check-only/apply')
    if not re.fullmatch(r'https://github\.com/gonos2k/Cloud-BAL/pull/[1-9][0-9]*',EXPECTED_PR_URL):fail('frozen actual PR URL format mismatch')
    if commit!=EXPECTED_COMMIT:fail('requested commit differs from the reviewed frozen commit literal')
    if not isinstance(APPROVED_SELECTED_PATHS, frozenset) or not APPROVED_SELECTED_PATHS:
        fail('root must freeze the exact committed source allowlist')
    if not isinstance(GRAPH_SOURCE_PATHS, frozenset) or not GRAPH_SOURCE_PATHS:
        fail('root must freeze the narrow graph source allowlist')
    if not GRAPH_SOURCE_PATHS <= APPROVED_SELECTED_PATHS:
        fail('graph source allowlist must be a subset of the committed source allowlist')
    if any(path.startswith('docs/evidence/') for path in GRAPH_SOURCE_PATHS):
        fail('generated evidence artifacts are hash-only and excluded from Graphify source extraction')
    if any(path.startswith(('scratch/', 'graphify-out/', 'wiki/')) for path in GRAPH_SOURCE_PATHS):
        fail('scratch, graph outputs, and wiki files are not candidate source paths')
    if importlib.metadata.version('graphifyy')!='0.9.53':fail('Graphify package must be exactly 0.9.53')
    if Path(sys.executable).resolve()!=GRAPHIFY_PY.resolve():fail('run through pinned Graphify Python')
    if Path(shutil.which('graphify') or '').resolve()!=GRAPHIFY_CLI.resolve():fail('pinned Graphify CLI must be first on PATH')
    if git('rev-parse','HEAD')!=commit:fail('candidate HEAD differs from requested frozen SHA')
    if git('status','--porcelain'):fail('candidate source worktree is not clean')
    subprocess.run(['git','merge-base','--is-ancestor',BASE,commit],cwd=SOURCE,check=True)
    changed=git('diff','--name-status','--find-renames',BASE,commit).splitlines(); items=[]
    for row in changed:
        fields=row.split('\t')
        if len(fields)!=2 or fields[0] not in ('A','M'):fail(f'unsupported selected path change: {row}')
        status,rel=fields
        if rel not in APPROVED_SELECTED_PATHS:fail(f'unreviewed path cannot enter selected extraction: {rel}')
        candidate=SOURCE/rel; reject_symlink_ancestors(candidate)
        if not candidate.resolve().is_relative_to(SOURCE.resolve()):fail(f'selected candidate escapes source root: {candidate}')
        regular_file(candidate)
        maintained=MAINT/rel; guard_destination(maintained,MAINT)
        from graphify.extract import _get_extractor
        oldbytes=subprocess.run(['git','show',f'{BASE}:{rel}'],cwd=SOURCE,capture_output=True,check=False)
        extraction_kind=('AST_OR_MARKDOWN_HEADING' if _get_extractor(candidate) is not None else 'NON_EXTRACTABLE_HASH_ONLY')
        if rel not in GRAPH_SOURCE_PATHS:
            extraction_kind='HASH_ONLY_EXCLUDED_FROM_GRAPH'
        items.append({'path':rel,'change':status,'base_sha256':sha_bytes(oldbytes.stdout) if oldbytes.returncode==0 else None,
          'candidate_sha256':sha(candidate),'maintained_before_sha256':sha(maintained) if maintained.is_file() else None,
          'graphify_extraction':extraction_kind})
    if not items or {x['path'] for x in items}!=set(APPROVED_SELECTED_PATHS):fail('frozen selected paths must exactly equal the complete base-to-commit diff')
    if not GRAPH_SOURCE_PATHS <= {x['path'] for x in items}:fail('graph source allowlist has paths outside the final diff')
    if {x['path'] for x in items if x['graphify_extraction']!='HASH_ONLY_EXCLUDED_FROM_GRAPH'}!=set(GRAPH_SOURCE_PATHS):
        fail('graph extraction set differs from the frozen maintained source allowlist')
    guard_destination(PRIOR)
    if sha(PRIOR)!=PRIOR_SHA:fail('preceding PR90 receipt hash drift')
    prior=json.loads(PRIOR.read_text())
    if prior.get('frozen_source_commit')!='60b02162e4f94a15db1b08cbe8a6ccd0ed9f0042':fail('preceding PR90 source identity mismatch')
    if prior.get('graphify_version')!='graphify 0.9.53':fail('preceding receipt Graphify version mismatch')
    current=maintained_source_snapshot()
    current_digest=sha_bytes(json.dumps(current,sort_keys=True,separators=(',',':')).encode())
    expected_inventory=prior.get('maintained_source_snapshot',{})
    if len(current)!=627 or expected_inventory.get('entry_count')!=627:fail('maintained source inventory must remain 627 entries')
    if current_digest!=MAINTAINED_SOURCE_SHA256:fail('maintained source inventory differs from pinned 627-entry digest')
    if current_digest!=expected_inventory.get('before_sha256'):fail('maintained source inventory differs from preceding receipt')
    expected_graphs={}
    for label in ('KLAPS50','Cloud-BAL'):
        record=prior.get('corpora',{}).get(label,{})
        if any(record.get(k)!=v for k,v in {'snapshot':'2026-10-19T12:23:50+00:00'}.items()):fail(f'{label} preceding graph snapshot identity mismatch')
        directory=ROOT if label=='KLAPS50' else MAINT
        live=directory/'graphify-out/graph.json'; guard_destination(live,directory)
        if sha(live)!=record.get('sha256'):fail(f'{label} live graph differs from latest PR90 baseline')
        for name in ('graph.json','GRAPH_REPORT.md','manifest.json'):
            artifact=directory/'graphify-out'/PRIOR_SNAPSHOT/name; guard_destination(artifact,directory)
            snapshot_record=prior.get('dated_snapshots',{}).get(label,{}).get(name,{})
            if not snapshot_record.get('after_sha256') or sha(artifact)!=snapshot_record['after_sha256']:
                fail(f'{label} latest dated PR90 snapshot drift: {name}')
            live_artifact=directory/'graphify-out'/name; guard_destination(live_artifact,directory)
            if sha(live_artifact)!=snapshot_record['after_sha256']:fail(f'{label} live derived graph artifact drift: {name}')
        next_snapshot=directory/'graphify-out'/SNAPSHOT; reject_symlink_ancestors(next_snapshot)
        if next_snapshot.exists():fail(f'{label} new dated snapshot already exists')
        expected_graphs[label]=record
    for rel,digest in prior.get('wiki_sha256',{}).items():
        path=ROOT/rel; guard_destination(path)
        if sha(path)!=digest:fail(f'wiki differs from latest PR90 receipt: {rel}')
    prior['corpora']=expected_graphs
    immutable={PRIOR:PRIOR_SHA,HELPER:sha(HELPER)}
    for label,files in prior.get('dated_snapshots',{}).items():
        for name,record in files.items():
            path=Path(record['path']); guard_destination(path)
            if sha(path)!=record['after_sha256']:fail(f'previous dated snapshot drift: {label}/{name}')
            immutable[path]=record['after_sha256']
    for path,digest in prior.get('prior_immutable_receipts',{}).items():
        p=Path(path); guard_destination(p,Path('/var/tmp') if p.is_relative_to(Path('/var/tmp')) else ROOT)
        if sha(p)!=digest:fail(f'previous immutable evidence drift: {path}')
        immutable[p]=digest
    if len(prior.get('prior_immutable_receipts',{}))!=189:fail('preceding PR90 receipt chain pin count mismatch')
    prior['_maintained_snapshot_digest']=current_digest
    delegated=delegated_importer_bindings()
    return items,prior,immutable,delegated

INHERITED_ACCEPTANCE_GATES=[
    "Whole host/thread FP policy beyond the selected single-thread cold start",
    "Joint Q/N/B validity during subsequent evolution beyond the declared latest validated window",
    "PBL DEL versus native dry-carrier global budget connection",
    "Physical justification and broader validation of conditional freezing and transient QG/BG admission",
    "Water and energy closure",
    "Physical small-ice inactive-to-active transitions and native count reconstruction",
]
OPEN_SAME_CANDIDATE_INTEGRATION_CONDITIONS=[
    'QC-only horizontal source component complete: 16 targets, 36 links, 288/288 matches over 18 pressure levels; other field-specific horizontal transfer and real.exe native-eta influence remain open',
    "Independently justify observation/background covariance and validate observation fit",
    "Same-carrier dry-mass, water, and energy closure",
    "Spatial mass-wind compatibility at cells and shared faces after native initialization",
    "Physical compatibility after WPS/metgrid/real handoff",
    "Fixed-setting 10/30/60-minute response and independent observation signal preservation",
]

def validate_bound_log(path:Path,digest:str,selected:set[str])->None:
    """Require a nonempty raw log selected in the commit and matching its receipt hash."""
    reject_symlink_ancestors(path)
    regular_file(path)
    try:
        relative=path.resolve(strict=True).relative_to(SOURCE.resolve()).as_posix()
    except (OSError,ValueError):
        fail(f'validation log escapes the candidate source root: {path}')
    if relative not in selected:
        fail(f'validation log is not in the frozen committed allowlist: {relative}')
    if path.stat().st_size<=0:
        fail(f'validation log is empty: {relative}')
    if sha(path)!=digest:
        fail(f'validation log hash mismatch: {relative}')

def validation_summary(document:dict,items:list[dict],commit:str)->str:
    if document.get('schema')!=VALIDATION_SCHEMA:fail('focused validation schema mismatch')
    if document.get('status')!='PASS':fail('focused validation receipt must record PASS')
    if type(document.get('test_count')) is not int or document['test_count']!=VALIDATION_TEST_COUNT:
        fail(f'focused validation must record exactly {VALIDATION_TEST_COUNT} passing tests')
    if document.get('compiler_profile')!='tests/intel_toolchain.sh':fail('focused validation must bind the pinned Intel profile')
    if document.get('compiler_profile_sha256')!=INTEL_PROFILE_SHA256:fail('pinned Intel profile hash mismatch')
    pins=document.get('source_hashes')
    if not isinstance(VALIDATION_SOURCE_PATHS,frozenset) or not isinstance(pins,dict) or set(pins)!=VALIDATION_SOURCE_PATHS:
        fail('focused validation source pin set mismatch')
    selected={item['path'] for item in items}
    aliases=document.get('source_hash_aliases')
    if not isinstance(aliases,dict) or set(aliases)!=set(VALIDATION_SOURCE_ALIASES):
        fail('external source alias metadata does not match the frozen archive mapping')
    for external,archive in VALIDATION_SOURCE_ALIASES.items():
        record=aliases.get(external)
        if not isinstance(record,dict) or record.get('path')!=archive or record.get('sha256')!=pins.get(archive):
            fail(f'external source alias does not bind its exact archived bytes: {external}')
    for relative,digest in pins.items():
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            fail(f'portable validation source path required: {relative}')
        path=SOURCE/relative; reject_symlink_ancestors(path); regular_file(path)
        if sha(path)!=digest:fail(f'focused validation source hash drift: {relative}')
        if relative in selected:
            if sha_bytes(show(commit,relative))!=digest:fail(f'focused validation source does not match frozen commit: {relative}')
        elif relative in VALIDATION_UNCHANGED_SOURCE_PATHS:
            try: base_digest=sha_bytes(show(BASE,relative))
            except subprocess.CalledProcessError: fail(f'unchanged validation dependency missing from base: {relative}')
            if base_digest!=digest or sha_bytes(show(commit,relative))!=digest:
                fail(f'unchanged validation dependency differs between base, final commit, and receipt: {relative}')
        else:
            fail(f'validation source is neither selected nor an explicitly frozen unchanged dependency: {relative}')
    if document.get('physical_approval') is not False:fail('focused validation must not claim physical approval')
    logs=document.get('logs')
    if not isinstance(logs,list) or not logs:fail('focused validation must bind at least one nonempty log record')
    seen=set()
    for record in logs:
        if not isinstance(record,dict):fail('validation log record must be an object')
        relative=record.get('path')
        digest=record.get('sha256')
        if not isinstance(relative,str) or relative in seen:fail('validation log paths must be unique strings')
        if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest):fail(f'invalid validation log hash: {relative}')
        validate_bound_log(SOURCE/relative,digest,selected)
        if sha_bytes(show(commit,relative))!=digest:fail(f'validation log does not match frozen commit: {relative}')
        seen.add(relative)
    return f"{document['test_count']} focused validation tests PASS under pinned Intel profile; {len(logs)} committed logs hash-bound; physical approval remains false."

def load_validation_receipt(argument:str|None,items:list[dict],commit:str):
    relative=Path(argument or VALIDATION_PATH)
    if relative.is_absolute() or '..' in relative.parts:fail('validation path must remain inside candidate source root')
    rel=relative.as_posix(); source=SOURCE/relative
    if rel not in {x['path'] for x in items}:fail('focused validation receipt must be selected in frozen source diff')
    regular_file(source); digest=sha(source)
    if digest!=VALIDATION_SHA256:fail('focused Intel validation receipt SHA differs from frozen literal')
    if sha_bytes(subprocess.check_output(['git','show',f'{commit}:{rel}'],cwd=SOURCE))!=digest:fail('validation receipt differs from frozen commit')
    document=json.loads(source.read_text(encoding='utf-8'))
    summary=validation_summary(document,items,commit)
    return {'path':rel,'sha256':digest,'source_commit':commit,'summary':summary,'document':document}


def load_integration_receipt(items:list[dict],commit:str)->dict:
    source=SOURCE/INTEGRATION_PATH
    if INTEGRATION_PATH not in {x['path'] for x in items}:fail('integration manifest must be in frozen selected diff')
    regular_file(source); digest=sha(source)
    if digest!=INTEGRATION_SHA256:fail('integration manifest SHA differs from frozen literal')
    if sha_bytes(subprocess.check_output(['git','show',f'{commit}:{INTEGRATION_PATH}'],cwd=SOURCE))!=digest:fail('manifest differs from frozen commit')
    document=json.loads(source.read_text(encoding='utf-8'))
    if document.get('schema')!=INTEGRATION_SCHEMA:fail('PR91 integration manifest schema mismatch')
    if document.get('base_commit')!=BASE:fail('integration manifest base commit mismatch')
    embedded_commit=document.get('source_commit',document.get('frozen_source_commit'))
    if embedded_commit is not None and embedded_commit!=commit:fail('integration manifest source commit mismatch')
    if document.get('physical_approval')!='FAIL_OPEN':fail('integration physical approval must remain FAIL_OPEN')
    validation=document.get('validation')
    if not isinstance(validation,dict) or validation.get('status')!='PASS' or validation.get('sha256')!=VALIDATION_SHA256:
        fail('manifest must bind the passing focused validation receipt SHA')
    def bound_json(record,label):
        if not isinstance(record,dict):fail(f'missing bound {label} artifact')
        relative=record.get('path','')
        if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
            fail(f'invalid bound {label} path')
        if relative not in {item['path'] for item in items}:fail(f'unselected bound {label} path')
        path=SOURCE/relative; reject_symlink_ancestors(path); regular_file(path)
        digest=sha(path)
        if digest!=record.get('sha256') or sha_bytes(show(commit,relative))!=digest:
            fail(f'bound {label} hash drift')
        return json.loads(path.read_text())
    build=bound_json(document.get('native_build'),'native build')
    if build.get('status')!='PASS_OVERLAY_BUILD' or build.get('full_clean_build') is not False:
        fail('native build must remain a passing partial-host overlay')
    executable=build.get('executable_sha256')
    if not isinstance(executable,str) or not re.fullmatch(r'[0-9a-f]{64}',executable):
        fail('invalid bound executable hash')
    runtime=document.get('latest_actual_host')
    if not isinstance(runtime,dict):
        fail('manifest must record explicit native host runtime windows')
    closed_runtime=validate_closed_runtime(runtime,executable)
    windows=runtime['windows']
    for duration_key in EXPECTED_RUNTIMES:
        runtime_window=windows[duration_key]
        closed_window=closed_runtime['windows'][duration_key]
        if closed_window['status']=='NOT_RUN':
            decision=bound_json(runtime_window.get('decision_receipt'),'600-second NOT_RUN decision')
            if decision.get('status')!='NOT_RUN' or \
                    decision.get('reason')!=closed_window['not_run_reason'] or \
                    decision.get('blocked_by_window')!='240' or \
                    decision.get('blocked_by_status')!='INCOMPLETE' or \
                    decision.get('requested_duration_seconds')!=600 or \
                    decision.get('timestep_seconds')!=20:
                fail('600-second NOT_RUN decision receipt does not bind the closed 240-second failure')
            continue
        arms=runtime_window['arms']
        for arm,row in arms.items():
            if not isinstance(row,dict) or not isinstance(row.get('status'),str) or not row['status'].strip():
                fail(f'invalid native status for {duration_key}-second {arm}')
            if type(row.get('returncode')) is not int or (row.get('final_completed_step') is not None and
                                                          type(row.get('final_completed_step')) is not int):
                fail(f'invalid native returncode/completed step for {duration_key}-second {arm}')
            if row['final_completed_step'] is not None and row['final_completed_step']<0:
                fail(f'negative completed step for {duration_key}-second {arm}')
            receipt=bound_json(row.get('receipt'),f'{duration_key}-second {arm} native receipt')
            for key in ('status','returncode','final_completed_step'):
                if receipt.get(key)!=row[key]:fail(f'{duration_key}-second {arm} native receipt {key} mismatch')
            if receipt.get('arm')!=arm or receipt.get('executed_executable_sha256')!=executable:
                fail(f'{duration_key}-second native arm/executable mismatch')
            if receipt.get('candidate_build_unchanged') is not True:
                fail(f'{duration_key}-second {arm} candidate build changed')
            if receipt.get('changed_staged_inputs') or receipt.get('changed_original_inputs'):
                fail(f'{duration_key}-second {arm} native input integrity failed')
            validate_runtime_receipt(arm,receipt,closed_window['arms'][arm],closed_window,executable)
    gates=document.get('candidate_scientific_gates')
    if not isinstance(gates,dict) or not gates:fail('manifest must retain explicit candidate scientific gates')
    if any(not isinstance(value,str) or not value.strip() for value in gates.values()):
        fail('candidate scientific gate statuses must be nonempty strings')
    return {'path':INTEGRATION_PATH,'sha256':digest,'source_commit':commit,
            'document':document,'closed_runtime':closed_runtime}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--commit',required=True,help='exact clean frozen source commit SHA')
    ap.add_argument('--pr-url',default=None,help='frozen actual PR URL; required for every mode')
    ap.add_argument('--validation-receipt',default=VALIDATION_PATH,help='frozen changed Intel validation receipt path')
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only',action='store_true',help='read-only guard/preflight; never updates graphs/wiki')
    mode.add_argument('--apply',action='store_true',help='perform Graphify update and derived wiki sync')
    args=ap.parse_args()
    global PR
    PR=args.pr_url or PR
    if args.pr_url and args.pr_url!=EXPECTED_PR_URL:
        fail('--pr-url differs from frozen actual PR URL')
    if not args.pr_url or args.pr_url!=EXPECTED_PR_URL:fail('check-only and apply require the frozen actual PR URL via --pr-url')
    items,prior,immutable,delegated_pins=make_plan(args.commit)
    maintained_snapshot_verified=False
    maintained_before=maintained_source_snapshot()
    maintained_before_digest=sha_bytes(json.dumps(maintained_before,sort_keys=True,separators=(',',':')).encode())
    previous_source_snapshot=prior.get('maintained_source_snapshot',{})
    if len(maintained_before)!=627 or previous_source_snapshot.get('entry_count')!=627:
        fail('maintained source inventory must remain at the preceding PR90-bound 627 entries')
    if maintained_before_digest!=MAINTAINED_SOURCE_SHA256:
        fail('maintained source inventory differs from pinned 627-entry digest')
    if maintained_before_digest!=previous_source_snapshot.get('before_sha256'):
        fail('maintained source inventory differs from the exact preceding PR90-bound snapshot')
    validation=load_validation_receipt(args.validation_receipt,items,args.commit)
    integration=load_integration_receipt(items,args.commit)
    native_binding=integration
    pending_candidate_gates=integration['document'].get('candidate_scientific_gates',{'cold_summary':'NOT_EVALUATED'})
    if args.check_only:
        print(json.dumps({'ready':True,'mode':'CHECK_ONLY_NO_WRITES','source':str(SOURCE),'commit':args.commit,'base':BASE,
          'selected_paths':items,'non_extractable_paths':[x['path'] for x in items if x['graphify_extraction']=='NON_EXTRACTABLE_HASH_ONLY'],'previous_receipt_sha256':PRIOR_SHA,
          'baseline_graphs':{k:{x:prior['corpora'][k][x] for x in ('snapshot','nodes','edges','communities','sha256')} for k in ('KLAPS50','Cloud-BAL')},
          'validation_receipt':validation,'native_receipt_binding':native_binding,'closed_runtime':native_binding['closed_runtime'],
          'graph_source_allowlist':sorted(GRAPH_SOURCE_PATHS),'hash_only_selected_paths':[x['path'] for x in items if x['graphify_extraction']=='HASH_ONLY_EXCLUDED_FROM_GRAPH'],
          'delegated_importer_pins':delegated_pins,'candidate_scientific_gates':pending_candidate_gates,
          'maintained_source_snapshot':{'entry_count':len(maintained_before),'symlink_entries':sum(v.get('kind')=='symlink' for v in maintained_before.values()),'before_sha256':maintained_before_digest,'sha256':maintained_before_digest,'verified_pre_post_equal':False},'new_output_path':str(OUT),'output_exists':OUT.exists()},indent=2));return
    # This output directory may contain only this external helper before the run.
    reject_symlink_ancestors(OUT)
    if OUT.exists() and (not OUT.is_dir() or any(OUT.iterdir())):
        fail('PR91 KG output directory exists and is not empty; refuses overwrite')
    protected={}
    for rel in ('wiki/hot.md','wiki/overview.md'):
        p=ROOT/rel
        guard_destination(p)
        protected[rel]=sha(p)
    protected_dirs=('wiki/.schema','wiki/.schema-proposals','wiki/.research-queue','wiki/entities','wiki/concepts','wiki/sources','wiki/decisions',
      'wiki/heuristics','wiki/experiences','wiki/procedures','wiki/queries')
    for rel in protected_dirs:
        p=ROOT/rel
        if p.exists():
            guard_directory(p)
            files=sorted(x for x in p.rglob('*') if x.is_file())
            for f in files:guard_destination(f)
            entries=[(f.relative_to(ROOT).as_posix(),sha(f)) for f in files]
            protected[rel]=sha_bytes(json.dumps(entries,separators=(',',':')).encode())
    if protected!=prior.get('protected_content_before_sha256'):
        fail('protected wiki content differs from the preceding PR90 receipt')
    OUT.mkdir(parents=True,exist_ok=True)
    if delegated_importer_bindings()!=delegated_pins:
        fail('delegated Graphify/KG updater sources changed after planning')
    sys.path.insert(0,str(OLD_PUBLISH))
    updater_spec=importlib.util.spec_from_file_location('pr59_publish_update',DELEGATED_UPDATER)
    graph_update=importlib.util.module_from_spec(updater_spec)
    sys.modules[updater_spec.name]=graph_update
    updater_spec.loader.exec_module(graph_update)
    graph_update.SOURCE=SOURCE;graph_update.OUT=OUT;graph_update.BASE_COMMIT=BASE;graph_update.PR=PR
    graph_items=[x for x in items if x['path'] in GRAPH_SOURCE_PATHS]
    graph_update.PATHS=tuple(x['path'] for x in graph_items)
    spec=importlib.util.spec_from_file_location('pr59_audit_util',DELEGATED_AUDITOR)
    audit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=audit;spec.loader.exec_module(audit)
    audit.ROOT=ROOT;audit.MAINTAINED=MAINT;audit.OUT=OUT;audit.PATHS=tuple(x['path'] for x in graph_items)
    # Guard every destination the delegated Graphify/writer batch may create.
    for directory in (ROOT,MAINT):
        for rel in graph_update.GRAPH_FILES:
            guard_destination(directory/'graphify-out'/rel,directory)
        for name in ('graph.json','GRAPH_REPORT.md','manifest.json'):
            guard_destination(directory/'graphify-out'/SNAPSHOT/name,directory)
    for rel in graph_update.WIKI_FILES:guard_destination(ROOT/'wiki'/rel)
    before={label:json.loads((directory/'graphify-out/graph.json').read_text()) for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT))}
    # Back up every graph/report/manifest and allowed wiki artifact before mutation.
    baseline_presence={}
    rollback_backup_sha256={}
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        for rel in graph_update.GRAPH_FILES:
            p=directory/'graphify-out'/rel
            baseline_presence[str(p)]=p.exists()
            if p.exists():
                regular_file(p)
                target=OUT/'backups'/label/rel;target.parent.mkdir(parents=True,exist_ok=True);copy_checked(p,target)
                rollback_backup_sha256[str(target)]=sha(target)
    for rel in graph_update.WIKI_FILES:
        p=ROOT/'wiki'/rel
        baseline_presence[str(p)]=p.exists()
        if p.exists():
            regular_file(p)
            target=OUT/'backups/wiki'/rel;target.parent.mkdir(parents=True,exist_ok=True);copy_checked(p,target)
            rollback_backup_sha256[str(target)]=sha(target)
    dated_names=('graph.json','GRAPH_REPORT.md','manifest.json')
    dated_before={}
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        dated_before[label]={}
        for name in dated_names:
            p=directory/'graphify-out'/SNAPSHOT/name
            target=OUT/'backups'/label/f'dated_{SNAPSHOT}'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            existed=p.exists()
            if existed:
                copy_checked(p,target)
                rollback_backup_sha256[str(target)]=sha(target)
            dated_before[label][name]={'path':str(p),'before_sha256':sha(p) if existed else None,'backup_path':str(target),'existed_before':existed}
    automatic_snapshot_backups={}
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        previous=directory/'graphify-out/2026-10-19'
        if not previous.exists():
            continue
        guard_directory(previous,directory)
        members={}
        for original in sorted(previous.iterdir()):
            guard_destination(original,directory)
            backup=OUT/'backups'/label/'prior_auto_2026-10-19'/original.name
            backup.parent.mkdir(parents=True,exist_ok=True)
            copy_checked(original,backup)
            members[original.name]={'backup':str(backup),'sha256':sha(backup)}
        automatic_snapshot_backups[str(previous)]=members
    sync={'base_commit':BASE,'frozen_commit':args.commit,'paths':items}
    source_sync_path=OUT/'source_sync.json'
    guard_destination(source_sync_path)
    source_sync_path.write_text(json.dumps(sync,indent=2)+'\n')
    try:
        records={'KLAPS50':graph_update.update_graph('KLAPS50',ROOT,'Cloud-BAL',graph_items),
                 'Cloud-BAL':graph_update.update_graph('Cloud-BAL',MAINT,'',graph_items)}
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            ext=json.loads((OUT/f'{label.lower().replace("-","_")}_extraction.json').read_text())
            audit.record_snapshot(label,directory,before[label],ext)
        # Preserve every old date-directory member, including hidden labels/analysis.
        restore_automatic_snapshots(automatic_snapshot_backups)
        private=audit.verify_private_profile(before)
        if private['Cloud-BAL']['nodes']!=134 or private['Cloud-BAL']['incident_links']!=133 or not private['Cloud-BAL']['unchanged'] or private['KLAPS50']['nodes']!=0:
            fail('private profile preservation guard failed')
        if git('rev-parse','HEAD')!=args.commit or git('status','--porcelain'):fail('source checkout changed during graph build')
        for x in items:
            if sha(SOURCE/x['path'])!=x['candidate_sha256']:fail(f'candidate source changed during build: {x["path"]}')
            p=MAINT/x['path'];guard_destination(p,MAINT);after=sha(p) if p.is_file() else None
            if after!=x['maintained_before_sha256']:fail(f'maintained source path changed: {x["path"]}')
        for label,r in records.items():
            r['previous_graph_sha256']=prior['corpora'][label]['sha256']
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            report_path=directory/'graphify-out/GRAPH_REPORT.md'
            guard_destination(report_path,directory)
            old_report=report_path.read_text()
            new_section=(f"## Graph Freshness\n\n"
                f"- Selected candidate overlay: `{args.commit}` against `{BASE}`; "
                f"{len(items)} committed changed paths hash-bound; {len(graph_items)} allowlisted maintained source/doc paths passed to Graphify; evidence excluded/hash-only.\n"
                f"- Remaining selected artifacts, including generated evidence, are hash-bound only and are not parsed.\n"
                f"- Snapshot: {records[label]['snapshot']}. Maintained checkout HEAD is a separate base, "
                f"not the source identity of this selected extraction.\n"
                f"- The persistent graph combines earlier corpus snapshots and selected overlays. "
                f"This is not a full extraction of the candidate tree.\n"
                f"- AST/Markdown headings only; cross-file Fortran CALL extraction is partial. "
                f"Freshness is navigation evidence, not runtime/scientific validation.\n"
                f"- External source trees and runtime artifacts outside the selected repository paths are not represented.\n")
            new_report,count=re.subn(r"## Graph Freshness\n.*?(?=\n## |\Z)",new_section,old_report,flags=re.S)
            if count!=1:fail(f'{label} derived freshness section missing or duplicated')
            report_path.write_text(new_report)
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            for name in dated_names:
                source=directory/'graphify-out'/name
                target=directory/'graphify-out'/SNAPSHOT/name
                guard_destination(target,directory)
                target.parent.mkdir(parents=True,exist_ok=True)
                copy_checked(source,target)
                dated_before[label][name]['after_sha256']=sha(target)
                if sha(source)!=sha(target):fail(f'{label} final dated copy differs: {name}')
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            records[label]['snapshot']=datetime.fromtimestamp((directory/'graphify-out/GRAPH_REPORT.md').stat().st_mtime,timezone.utc).isoformat()
        copy_checked(ROOT/'graphify-out/GRAPH_REPORT.md',ROOT/'wiki/graph-report-klaps50.md')
        copy_checked(MAINT/'graphify-out/GRAPH_REPORT.md',ROOT/'wiki/graph-report-cloud-bal.md')
        idx=ROOT/'wiki/graph-report.md';lines=idx.read_text().splitlines()
        for i,line in enumerate(lines):
            for label,r in records.items():
                if line.startswith(f'| {label} |'):
                    folder='.' if label=='KLAPS50' else 'Cloud-BAL/';mirror='graph-report-klaps50' if label=='KLAPS50' else 'graph-report-cloud-bal'
                    lines[i]=f"| {label} | `{folder}` | {r['snapshot']} (PR91 host-store candidate overlay) | {r['nodes']} | {r['edges']} | {r['communities']} | [[{mirror}]] |"
        guard_destination(idx)
        idx.write_text('\n'.join(lines)+'\n')
        page=ROOT/'wiki/index.md';before_bytes=page.read_bytes();before_text=before_bytes.decode('utf-8');start=before_text.index('## Graph snapshot');end=before_text.find('\n## ',start+3);has_tail=end>=0
        if not has_tail:end=len(before_text)
        start_byte=len(before_text[:start].encode('utf-8'));end_byte=len(before_text[:end].encode('utf-8'))
        section='## Graph snapshot\n\n'
        for label,r in records.items():
            section+=(f"- {label}: {r['snapshot']}; {r['nodes']} nodes / {r['edges']} edges / {r['communities']} communities; "
              f"PR91 host-store overlay delta [{r['delta_nodes']}, {r['delta_edges']}].\n")
        section+='- [[graph-report|Separate corpus reports]] retain extraction limits. Graph freshness is navigation evidence only, not runtime or scientific validation.\n'
        final_text=before_text[:start]+section+before_text[end:]
        final_bytes=final_text.encode('utf-8')
        if before_bytes[:start_byte]!=final_bytes[:start_byte]:fail('index prefix bytes changed outside Graph snapshot section')
        if before_bytes[end_byte:]!=final_bytes[start_byte+len(section.encode('utf-8')):]:fail('index suffix bytes changed outside Graph snapshot section')
        guard_destination(page)
        page.write_bytes(final_bytes)
        written_bytes=page.read_bytes()
        if written_bytes!=final_bytes:fail('index final bytes differ after Graph snapshot write')
        if written_bytes[:start_byte]!=before_bytes[:start_byte]:fail('written index prefix bytes changed outside Graph snapshot section')
        if written_bytes[start_byte+len(section.encode('utf-8')):]!=before_bytes[end_byte:]:fail('written index suffix bytes changed outside Graph snapshot section')
        stamp=datetime.now(timezone.utc)
        log=ROOT/'wiki/log.md'
        entry=f"\n## [{stamp.strftime('%Y-%m-%d')}] kg-update | PR91 host-store selected-path overlay ({stamp.strftime('%H:%M UTC')})\n"
        entry+=f"- PR {PR}; frozen source commit `{args.commit}` against `{BASE}`. {len(items)} committed changed paths were hash-captured; {len(graph_items)} allowlisted paths were structurally extracted, and all other selected records (including evidence) are hash-only. Maintained source files were not copied or replaced.\n"
        for label,r in records.items():
            entry+=(f"- {label} snapshot {r['snapshot']}: {r['nodes']} nodes / {r['edges']} edges / {r['communities']} communities; "
              f"PR91 host-store overlay delta [{r['delta_nodes']}, {r['delta_edges']}], added/removed IDs {r['added_ids']}/{r['removed_ids']}; "
              f"previous graph SHA-256 `{r['previous_graph_sha256']}`.\n")
        entry+='- Cloud-BAL private profile remains 134 nodes / 133 incident links; KLAPS50 carries zero nodes from this private source. Graph integrity diagnostics passed.\n'
        entry+='- Graphify 0.9.53 selected-source AST/Markdown-heading extraction and separate `cluster-only --no-viz --no-label`; no semantic refresh. Generated Fortran inside Python strings and compressed sources is not separately Fortran-AST extracted. Cross-file Fortran CALL extraction is partial; corpora overlap and counts are separate.\n'
        entry+=f"- Graph freshness is navigation-only; selected-source AST/Markdown headings have no semantic refresh, and cross-file Fortran CALL extraction is partial. Physical approval carries forward `{prior['physical_approval']}`.\n"
        entry+=f"- Durable preceding PR90 KG receipt: `{PRIOR.relative_to(ROOT)}` (SHA-256 `{PRIOR_SHA}`); its immutable prior-receipt chain remains pinned.\n"
        if validation:
            entry+=f"- Validation evidence: {validation['summary']} Receipt `{validation['path']}` SHA-256 `{validation['sha256']}` at `{args.commit}`.\n"
        else:
            entry+='- No separate CP06A authority receipt is supplied; runtime and scientific statuses are bound below from the integration receipt.\n'
        entry+=f"- Overall physical approval remains `{prior['physical_approval']}`. PR91 host-store and scientific status fields are taken from the bound final integration receipt; graph freshness does not establish runtime or scientific acceptance.\n"
        entry+=f"- PR91 integration statuses are bound from `{INTEGRATION_PATH}` (SHA-256 `{integration['sha256']}`); graph freshness establishes no physical or scientific acceptance.\n"
        current=integration['document']
        runtime=current['latest_actual_host']
        windows=runtime.get('windows',{})
        window_status={duration:{'status':row.get('status'),
          'arms':{arm:{key:arm_row.get(key) for key in ('status','returncode','final_completed_step')}
                  for arm,arm_row in row.get('arms',{}).items()}}
          for duration,row in windows.items()}
        runtime_status=runtime.get('status','STATUS_RECORDED')
        entry+=f"- Runtime status: `{runtime_status}`; per-window arm statuses {json.dumps(window_status,sort_keys=True)}.\n"
        entry+=f"- Candidate scientific gates remain separate from runtime status: {json.dumps(current['candidate_scientific_gates'],sort_keys=True)}; physical approval stays FAIL_OPEN.\n"
        validation_status=current.get('validation',{}).get('status',validation['document'].get('status','STATUS_RECORDED'))
        entry+=f"- Focused validation status: `{validation_status}`. No model physics acceptance is inferred from graph freshness.\n"
        guard_destination(log)
        with log.open('a') as f:f.write(entry)
        for rel,expected in protected.items():
            p=ROOT/rel
            if p.is_file():
                guard_destination(p)
                if sha(p)!=expected:fail(f'protected wiki file changed: {rel}')
            else:
                guard_directory(p)
                files=sorted(x for x in p.rglob('*') if x.is_file())
                for q in files:guard_destination(q)
                rows=[(q.relative_to(ROOT).as_posix(),sha(q)) for q in files]
                if sha_bytes(json.dumps(rows,separators=(',',':')).encode())!=expected:fail(f'protected wiki directory changed: {rel}')
        maintained_after=maintained_source_snapshot()
        if maintained_after!=maintained_before:fail('maintained non-graph source, wiki content, profile, or prior receipt changed during Graphify refresh')
        maintained_snapshot_verified=True
        for p,h in immutable.items():
            if p!=HELPER:guard_destination(p,Path('/var/tmp') if p.parent==Path('/var/tmp') else ROOT)
            if sha(p)!=h:fail(f'prior immutable receipt changed: {p}')
        receipt={
          'schema':'pr91_host_store_selected_path_graphify_kg_receipt_v1','dated_snapshot_day':'2026-10-20','dated_snapshot_timezone':'Asia/Seoul (session day)','recorded_utc':datetime.now(timezone.utc).isoformat(),
          'pr':PR,'base_commit':BASE,'frozen_source_commit':args.commit,'source_path':str(SOURCE),'selected_path_count':len(items),'graph_source_path_count':len(graph_items),
          'selected_paths':items,'graph_source_allowlist':sorted(GRAPH_SOURCE_PATHS),'hash_only_selected_paths':[x['path'] for x in items if x['graphify_extraction']=='HASH_ONLY_EXCLUDED_FROM_GRAPH'],'non_extractable_selected_paths':[x['path'] for x in items if x['graphify_extraction']=='NON_EXTRACTABLE_HASH_ONLY'],'source_sync_sha256':sha(OUT/'source_sync.json'),
          'maintained_source_snapshot':{'verified_pre_post_equal':maintained_snapshot_verified,
            'entry_count':len(maintained_before),'symlink_entries':sum(v.get('kind')=='symlink' for v in maintained_before.values()),'before_sha256':maintained_before_digest,
            'scope':'active src/, tests/, docs/, config/ in KLAPS50 and Cloud-BAL; immediate tracked root files; remaining wiki content is separately protected by page/directory hashes',
            'excluded':'scratch/worktrees, .git, graphify-out, and the five intentionally refreshed derived wiki files (three graph reports, index.md, log.md)'},
          'previous_pr90_kg_receipt_sha256':PRIOR_SHA,
          'previous_pr90_kg_receipt_path':str(PRIOR),
          'previous_pr90_source_commit':prior['frozen_source_commit'],
          'previous_physical_approval':prior['physical_approval'],
          'physical_approval':prior['physical_approval'],
          'remaining_scientific_gates':prior.get('remaining_scientific_gates',[]),
          'inherited_open_physical_gates':INHERITED_OPEN_GATES,
          'remaining_acceptance_gates':INHERITED_ACCEPTANCE_GATES,
          'same_candidate_integration_conditions_open':OPEN_SAME_CANDIDATE_INTEGRATION_CONDITIONS,
          'validation_receipt_binding':validation,
          'native_receipt_binding':native_binding,
          'closed_runtime_binding':native_binding['closed_runtime'],
          'delegated_importer_pins':delegated_pins,
          'candidate_scientific_gates':pending_candidate_gates,
          'graphify_version':subprocess.check_output(['graphify','--version'],text=True).strip(),'python_executable':sys.executable,
          'mode':'guarded selected-path overlay extraction/build_merge, cluster-only, derived wiki sync',
          'extraction':'Graphify AST and Markdown headings only; no semantic/LLM refresh; unsupported/binary selected files are hash-bound but not parsed',
          'corpora':records,'private_profile_preservation':private,
          'dated_snapshots':dated_before,'dated_snapshot_directory':SNAPSHOT,
          'automatic_snapshot_preservation':automatic_snapshot_backups,'baseline_artifact_presence':baseline_presence,
          'rollback_backup_sha256':rollback_backup_sha256,'protected_content_before_sha256':protected,
          'wiki':{'updated':['graph-report.md','graph-report-klaps50.md','graph-report-cloud-bal.md','index.md#Graph-snapshot','log.md (append-only)'],
            'protected_unchanged':list(protected),'schema_and_content_pages_touched':False},
          'prior_immutable_receipts':{str(p):h for p,h in immutable.items()},
          'limitations':['Graph counts are separate for overlapping KLAPS50 and Cloud-BAL corpora.','Markdown semantic extraction was not performed; Markdown contributes heading structure only.',
            'Fortran cross-file CALL extraction is partial.','Generated Fortran inside Python strings and compressed source artifacts is hash-bound, not separately Fortran-AST extracted.','External source trees and runtime artifacts outside selected repository paths are not represented.',
            'Candidate overlay graphs and freshness are structural navigation evidence, not runtime or scientific validation.',
            'Non-extractable or binary selected paths are recorded by SHA-256 and passed to the pinned Graphify extractor, which returns no extractor for their suffix; their contents are not parsed.',
            'Evidence artifacts outside the maintained source allowlist are hash-only; the PR90 receipt chain remains immutable. Structural freshness does not establish runtime or scientific acceptance.']}
        receipt['wiki_sha256']={rel:sha(ROOT/rel) for rel in ('wiki/graph-report.md','wiki/graph-report-klaps50.md','wiki/graph-report-cloud-bal.md','wiki/index.md','wiki/log.md')}
        rp=OUT/'kg_receipt.json';guard_destination(rp);rp.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        print(json.dumps({'receipt':str(rp),'receipt_sha256':sha(rp),'corpora':records,'private_profile':private},indent=2))
    except BaseException as original_error:
        rollback_errors=[]
        def attempt_restore(label,operation):
            try:operation()
            except BaseException as error:
                rollback_errors.append(f'{label}: {type(error).__name__}: {error}')

        def restore_artifact(backup,target,existed_before):
            if existed_before:
                if not backup.exists():fail(f'rollback backup missing: {backup}')
                if sha(backup)!=rollback_backup_sha256[str(backup)]:
                    fail(f'rollback backup changed: {backup}')
                copy_checked(backup,target)
            elif target.exists():
                guard_destination(target);target.unlink()

        attempt_restore('prior automatic snapshots',
                        lambda:restore_automatic_snapshots(automatic_snapshot_backups))
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            for rel in graph_update.GRAPH_FILES:
                backup=OUT/'backups'/label/rel;target=directory/'graphify-out'/rel
                attempt_restore(str(target),lambda b=backup,t=target:
                    restore_artifact(b,t,baseline_presence[str(t)]))
            for name in dated_names:
                backup=OUT/'backups'/label/f'dated_{SNAPSHOT}'/name
                target=directory/'graphify-out'/SNAPSHOT/name
                existed=dated_before[label][name]['existed_before']
                attempt_restore(str(target),lambda b=backup,t=target,e=existed:
                    restore_artifact(b,t,e))
            new_snapshot=directory/'graphify-out'/SNAPSHOT
            def remove_empty_snapshot(path=new_snapshot,root=directory):
                if path.exists():
                    guard_directory(path,root)
                    if not any(path.iterdir()):path.rmdir()
            # Unexpected concurrent files remain untouched; restoration continues.
            attempt_restore(str(new_snapshot),remove_empty_snapshot)
        for rel in graph_update.WIKI_FILES:
            backup=OUT/'backups/wiki'/rel;target=ROOT/'wiki'/rel
            attempt_restore(str(target),lambda b=backup,t=target:
                restore_artifact(b,t,baseline_presence[str(t)]))

        def verify_restored_sources():
            if maintained_source_snapshot()!=maintained_before:
                fail('rollback did not preserve maintained source/wiki/profile content')
            if git('rev-parse','HEAD')!=args.commit or git('status','--porcelain'):
                fail('candidate source worktree changed during failed graph build')
            for selected in items:
                if sha(SOURCE/selected['path'])!=selected['candidate_sha256']:
                    fail(f'candidate source bytes changed: {selected["path"]}')
        attempt_restore('source preservation',verify_restored_sources)
        for pinned_path,pinned_sha in immutable.items():
            def verify_immutable(path=pinned_path,digest=pinned_sha):
                if sha(path)!=digest:fail(f'rollback changed an immutable prior pin: {path}')
            attempt_restore(str(pinned_path),verify_immutable)
        if rollback_errors:
            raise RuntimeError('KG update failed; rollback also reported: '+'; '.join(rollback_errors)) from original_error
        raise

if __name__=='__main__':main()
