# Graph Report - Cloud-BAL  (2026-09-02)

## Corpus Check
- 114 files · ~153,996 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1283 nodes · 2648 edges · 93 communities (60 shown, 17 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 55 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `539addde`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- cloud_bal_state_type
- cloud_bal_state
- cloud_bal_real_netcdf
- cloud_bal_legacy_shadow_adapter
- cloud_bal_balance_operator
- prepare_operational_comparison.py
- audit_intel_integration.py
- intel_toolchain.sh
- TransactionError
- Cloud-BAL pipeline simplification and remediation plan
- Path
- original_upstream_replay.py
- audit_legacy_deriv_safety.py
- compare_operational_shadow.py
- check_qbal_real_inputs.py
- test_balance_operator
- Cloud-BAL improvement plan
- validate_shadow_diagnostics.py
- cloud_bal_radar_downdraft
- LegacyDerivSafetyTest
- test_operational_comparison_prep.py
- plot_shadow_comparison.py
- test_cloud_bal_core
- qbalpe.f
- test_balance_omega_authority
- test_canonical_state
- test_column_physics
- ReplayPlannerTest
- Radar-precipitation downdraft and localized mass-wind balance
- lapsprep
- get_cloud_deriv.f
- test_missing_phase_continuity
- cloud_bal_field_contracts
- test_state_atomic_refresh
- real_shadow_driver
- test_nonuniform_localization
- README.md
- QBAL real-input contract
- lapsprep_wps
- Cloud-BAL implementation report
- Operational-original versus SHADOW comparison contract
- Cloud-BAL 단일 승인 체크리스트
- Cloud-BAL 과학적 기초와 구현 경계
- cloud_bal_grid_geometry
- cloud_bal_localization
- cloud_bal_moisture
- radar_reflectivity_io.f
- run_isolation_gate.sh
- test_lapsio_abi.f90
- test_writeballaps_status.f90
- Baseline review
- Legacy derived-cloud production safety audit
- cloud_bal_cloud_profiles
- cloud_deriv_subs.f
- test_qbal_operator.f90
- Original KLAPS upstream replay harness
- lapsio.f
- test_qbal_acceptance
- test_real_shadow_reader
- wps_module_stubs.f90
- Intel-only integration readiness audit
- cloud_bal_wind_modes
- pcpcnc.f
- test_wps_writer_status
- laps_cloud_sub.f
- rfill_evap.f
- ice2vapor
- lwc2vapor
- laps_static
- setup
- run_original_upstream_replay_tests.sh
- run_legacy_deriv_safety_audit.sh
- run_radar_velocity_audit.sh
- run_real_input_inventory.sh
- run_transaction_gate.sh
- 5. Conservative hydrometeor allocation
- 1. Consolidated problems

## God Nodes (most connected - your core abstractions)
1. `cloud_bal_state_type` - 78 edges
2. `cloud_bal_state` - 76 edges
3. `cloud_bal_real_netcdf` - 54 edges
4. `cloud_bal_balance_operator` - 49 edges
5. `cloud_bal_column_physics` - 43 edges
6. `cloud_bal_legacy_shadow_adapter` - 37 edges
7. `field3d` - 37 edges
8. `balance_operator_type` - 28 edges
9. `ContractError` - 27 edges
10. `test_balance_operator` - 26 edges

## Surprising Connections (you probably didn't know these)
- `initialize_pipeline_state()` --references--> `cloud_bal_state_type`  [EXTRACTED]
  tests/test_nonuniform_localization.f90 → src/common/cloud_bal_state.f90
- `expect_not_ready()` --calls--> `prepare()`  [INFERRED]
  tests/test_operational_comparison_prep.py → tools/prepare_operational_comparison.py
- `main()` --calls--> `prepare()`  [INFERRED]
  tests/test_operational_comparison_prep.py → tools/prepare_operational_comparison.py
- `accepted()` --calls--> `canonical_omega_target_cells()`  [INFERRED]
  tests/test_shadow_validator.py → tools/validate_shadow_diagnostics.py
- `permissive_config()` --references--> `balance_operator_config`  [EXTRACTED]
  tests/test_balance_omega_authority.f90 → src/common/cloud_bal_balance_operator.f90

## Import Cycles
- None detected.

## Communities (93 total, 17 thin omitted)

### Community 0 - "cloud_bal_state_type"
Cohesion: 0.06
Nodes (79): account_bottom_flux(), add_loading_downdraft(), allocate_precipitation_phase(), bounded_terminal_speed(), build_cloud_targets(), cloud_bal_column_physics, cloud_regime(), column_changed_mask() (+71 more)

### Community 1 - "cloud_bal_state"
Cohesion: 0.06
Nodes (76): copy_real2(), integer3_absent(), integer3_metadata_ok(), integer3_shape_ok(), real2_metadata_ok(), real2_shape_ok(), canonical_input_spec, canonical_states_equal() (+68 more)

### Community 2 - "cloud_bal_real_netcdf"
Cohesion: 0.05
Nodes (79): netcdf, initialize_rejection(), build_compact_balance_beta(), cloud_bal_pipeline, cloud_bal_pipeline_config, cloud_bal_pipeline_result, cloud_bal_balance_operator, cloud_bal_column_physics (+71 more)

### Community 3 - "cloud_bal_legacy_shadow_adapter"
Cohesion: 0.07
Nodes (50): cloud_bal_legacy_shadow_adapter, cloud_bal_legacy_shadow_adapter, copy_domain(), copy_integer3(), copy_real3(), copy_specific_humidity(), direct_closure_valid(), distance_unit_scale() (+42 more)

### Community 4 - "cloud_bal_balance_operator"
Cohesion: 0.12
Nodes (49): add_node(), apply_adjoint_metric(), apply_balance_correction(), apply_continuity_operator(), apply_localized_balance(), apply_normal_operator(), apply_normal_operator_work(), balance_beta_active() (+41 more)

### Community 5 - "prepare_operational_comparison.py"
Cohesion: 0.16
Nodes (46): Artifact, base_report(), bundle_metadata(), canonical_time(), contains_bigfile(), contains_symlink_component(), ContractError, decode_times() (+38 more)

### Community 6 - "audit_intel_integration.py"
Cohesion: 0.18
Nodes (34): active_make_lines(), active_shell_lines(), adapter_is_on_link_path(), add_finding(), artifact_valid(), audit(), copied_tree_link_plan(), dependency_ready() (+26 more)

### Community 7 - "intel_toolchain.sh"
Cohesion: 0.08
Nodes (22): intel_toolchain.sh script, cloud_bal_current_evidence(), cloud_bal_output_under(), cloud_bal_require_clean_source(), output_safety.sh script, build_and_run(), run_contract_regressions.sh script, run_intel_integration_audit.sh script (+14 more)

### Community 8 - "TransactionError"
Cohesion: 0.18
Nodes (25): expect_rejected(), main(), write_products(), _current(), _current_id(), _fsync_directory(), _identifier(), _inside() (+17 more)

### Community 9 - "Cloud-BAL pipeline simplification and remediation plan"
Cohesion: 0.05
Nodes (42): Adversarial-review acceptance checklist, Canonical units and schema, Changes, Changes, Changes, Changes, Changes, Changes (+34 more)

### Community 10 - "Path"
Cohesion: 0.19
Nodes (8): blocked_command_result(), command_result(), digest(), IntegrationFixture, IntelIntegrationAuditTest, non_ifx_command_result(), Path, snapshot()

### Community 11 - "original_upstream_replay.py"
Cohesion: 0.18
Nodes (31): audit_declared_file(), canonical_sha256(), contained_directory(), contained_regular(), forbidden_input(), hash_tree(), immutable_copy(), intel_binary() (+23 more)

### Community 12 - "audit_legacy_deriv_safety.py"
Cohesion: 0.15
Nodes (30): ArgumentParser, analyze_source(), binary_call_edge(), build_parser(), _call_arguments(), _compact(), _condition_is_constant_false(), fixed_form_statements() (+22 more)

### Community 13 - "compare_operational_shadow.py"
Cohesion: 0.11
Nodes (45): field_records(), main(), record(), inspect_case(), inspect_radar(), main(), ndarray, Path (+37 more)

### Community 14 - "check_qbal_real_inputs.py"
Cohesion: 0.15
Nodes (28): main(), make_manifest(), Path, test_pre_qbal_generation_manifest_contract(), write_manifest(), contained_input(), expected_epoch(), forbidden_metadata_reason() (+20 more)

### Community 15 - "test_balance_operator"
Cohesion: 0.18
Nodes (26): add_held_out_los(), check(), cloud_bal_balance_operator, cloud_bal_state, iso_fortran_env, make_balance_state(), mark_valid(), test_actual_operator_nullspace() (+18 more)

### Community 16 - "Cloud-BAL improvement plan"
Cohesion: 0.15
Nodes (13): 2. Data contract introduced before physics changes, 3.1 Safe first policy: missing-only fallback, 3.2 Confidence blend after the fallback is validated, 3. Background and omega fusion, 4.1 Preserve the legacy solver as a candidate generator, 4.2 Correct the control parameters, 4.3 Acceptance gate, 4. Bounded mass-wind balance (+5 more)

### Community 17 - "validate_shadow_diagnostics.py"
Cohesion: 0.16
Nodes (21): dtype, accepted(), canonical_omega_target_cells(), changed_bits(), continuity_increment(), continuity_state(), is_signed_int32(), main() (+13 more)

### Community 18 - "cloud_bal_radar_downdraft"
Cohesion: 0.20
Nodes (21): build_observed_mask(), cloud_bal_radar_downdraft, config_is_valid(), couple_radar_precipitation(), diagnose_bounded_downdraft(), cloud_bal_moisture, ieee_arithmetic, fill_lower_gaps() (+13 more)

### Community 20 - "test_operational_comparison_prep.py"
Cohesion: 0.32
Nodes (17): artifact(), expect_not_ready(), main(), make_netcdf_triad(), make_wps_triad(), met_em(), pair(), Path (+9 more)

### Community 21 - "plot_shadow_comparison.py"
Cohesion: 0.34
Nodes (16): Axes, Figure, add_map(), array(), horizontal_figure(), main(), precipitation(), Dataset (+8 more)

### Community 22 - "test_cloud_bal_core"
Cohesion: 0.21
Nodes (16): cloud_bal_cloud_profiles, cloud_bal_radar_downdraft, cloud_bal_wind_modes, check(), check_close(), cloud_bal_field_contracts, cloud_bal_localization, cloud_bal_moisture (+8 more)

### Community 23 - "qbalpe.f"
Cohesion: 0.21
Nodes (13): analzo(), balcon(), continuity_metrics(), continuity_point(), diagnose(), ieee_arithmetic, geostrophic_residual_metrics(), initmxmn() (+5 more)

### Community 24 - "test_balance_omega_authority"
Cohesion: 0.31
Nodes (15): authorize_target(), check(), cloud_bal_balance_operator, cloud_bal_state, iso_fortran_env, make_state(), mark_valid(), permissive_config() (+7 more)

### Community 25 - "test_canonical_state"
Cohesion: 0.23
Nodes (15): check(), cloud_bal_state, ieee_arithmetic, iso_fortran_env, fill_real_field(), fill_surface_field(), invalidate_cell(), make_valid_state() (+7 more)

### Community 26 - "test_column_physics"
Cohesion: 0.25
Nodes (14): check(), cloud_bal_column_physics, cloud_bal_state, ieee_arithmetic, iso_fortran_env, make_state(), test_column_physics, test_column_stage() (+6 more)

### Community 27 - "ReplayPlannerTest"
Cohesion: 0.33
Nodes (4): Path, ReplayPlannerTest, sha256(), write_vrt()

### Community 28 - "Radar-precipitation downdraft and localized mass-wind balance"
Cohesion: 0.14
Nodes (14): 10. Rollout, 11. Physical basis, 1. Problem statement, 2. Sign and unit conventions, 3. Legacy radar code retained as design evidence, 4.1 Status of the empirical cloud vertical velocity, 4. Coupled analysis sequence, 5. Precipitation trajectory and hydrometeor alignment (+6 more)

### Community 29 - "lapsprep"
Cohesion: 0.15
Nodes (12): constants, lapsprep_mm5, lapsprep_netcdf, lapsprep_rams, lapsprep_wrf, cloud_bal_field_contracts, cloud_bal_moisture, ieee_arithmetic (+4 more)

### Community 30 - "get_cloud_deriv.f"
Cohesion: 0.15
Nodes (4): cpt_pcp_type_3d(), for, given, nowrad_virga_correction()

### Community 31 - "test_missing_phase_continuity"
Cohesion: 0.23
Nodes (12): check(), evaluate_fallback(), cloud_bal_column_physics, cloud_bal_state, ieee_arithmetic, iso_fortran_env, test_explicit_phase_unchanged(), test_finite_range_guards() (+4 more)

### Community 32 - "cloud_bal_field_contracts"
Cohesion: 0.36
Nodes (11): capture_field_validity_1d(), capture_field_validity_2d(), capture_field_validity_3d(), cloud_bal_field_contracts, contract_metadata_ok(), ieee_arithmetic, field_contract, initialize_field_contract() (+3 more)

### Community 34 - "test_state_atomic_refresh"
Cohesion: 0.31
Nodes (10): check(), cloud_bal_state, ieee_arithmetic, iso_fortran_env, make_refresh_state(), test_late_failure_is_atomic(), test_state_atomic_refresh, test_usable_contract() (+2 more)

### Community 35 - "real_shadow_driver"
Cohesion: 0.25
Nodes (8): core_value_differences(), cloud_bal_balance_operator, cloud_bal_pipeline, cloud_bal_real_netcdf, cloud_bal_state, iso_fortran_env, real_shadow_driver, real_value_differences()

### Community 36 - "test_nonuniform_localization"
Cohesion: 0.22
Nodes (7): cloud_bal_grid_geometry, cloud_bal_localization, cloud_bal_pipeline, cloud_bal_state, iso_fortran_env, initialize_pipeline_state(), test_nonuniform_localization

### Community 37 - "README.md"
Cohesion: 0.25
Nodes (4): Cloud-BAL, Data flow, Deliberate exclusions, Repository layout

### Community 38 - "QBAL real-input contract"
Cohesion: 0.25
Nodes (7): 1. Direct QBAL read closure, 2. Original producer chain needed to recreate the direct inputs, 3. Candidate radar extension, 4. Prepared cases and current readiness, 5. Deterministic background selection, 6. Forbidden inputs and fail-closed gates, QBAL real-input contract

### Community 39 - "lapsprep_wps"
Cohesion: 0.33
Nodes (6): date_pack, laps_static, setup, lapsprep_wps, output_ungrib_format(), write_ungrib_header()

### Community 40 - "Cloud-BAL implementation report"
Cohesion: 0.29
Nodes (6): Cloud-BAL implementation report, Decision, Implemented focused candidate, Integration blockers, Preserved comparison baseline, Verification completed

### Community 41 - "Operational-original versus SHADOW comparison contract"
Cohesion: 0.29
Nodes (6): Current 2026-08-16 inventory limitation, Invocation and outputs, Manifest example, Operational-original versus SHADOW comparison contract, Purpose, Readiness gates

### Community 42 - "Cloud-BAL 단일 승인 체크리스트"
Cohesion: 0.25
Nodes (8): Cloud-BAL 단일 승인 체크리스트, P0 체크리스트, 단일 계약, 레이더 시선속도 판정, 실제자료 전수 증거, 운영 승격 전에 반드시 남은 시험, 최종 목표와 현재 판정, 현업 KLAPS 대조 결과

### Community 43 - "Cloud-BAL 과학적 기초와 구현 경계"
Cohesion: 0.25
Nodes (7): 1. 운형과 연직속도, 2. S-band 반사도와 시선속도, 3. 기울어진 강수 구조와 fall-flux 재구성, 4. 국지 질량-바람 projection, 5. 파동과 동역학적 안전성, Cloud-BAL 과학적 기초와 구현 경계, 결론

### Community 44 - "cloud_bal_grid_geometry"
Cohesion: 0.33
Nodes (5): cloud_bal_grid_geometry, cumulative_horizontal_distance_r32(), cumulative_horizontal_distance_r64(), ieee_arithmetic, iso_fortran_env

### Community 45 - "cloud_bal_localization"
Cohesion: 0.33
Nodes (6): build_compact_influence_3d(), cloud_bal_localization, cloud_bal_grid_geometry, ieee_arithmetic, iso_fortran_env, wendland_c2()

### Community 47 - "radar_reflectivity_io.f"
Cohesion: 0.43
Nodes (4): read_multiradar_3dref(), read_nowrad_3dref(), read_radar_3dref(), read_vrz_3dref()

### Community 48 - "run_isolation_gate.sh"
Cohesion: 0.52
Nodes (6): check_baseline_contract(), check_candidate_contract(), hash_live_inputs(), inventory_baseline(), inventory_live_tree(), run_isolation_gate.sh script

### Community 50 - "test_writeballaps_status.f90"
Cohesion: 0.33
Nodes (4): test_writeballaps_status, write_laps_data(), writer_failure_control, writer_failure_control

### Community 51 - "Baseline review"
Cohesion: 0.33
Nodes (5): Baseline review, Current operational behavior, Initial test matrix, Priority defects, Required acceptance gates

### Community 52 - "Legacy derived-cloud production safety audit"
Cohesion: 0.33
Nodes (5): CLI, Contract, Current audit, Legacy derived-cloud production safety audit, Review-only patch

### Community 53 - "cloud_bal_cloud_profiles"
Cohesion: 0.47
Nodes (5): build_multilayer_w_profile(), cloud_bal_cloud_profiles, detect_cloud_layers(), ieee_arithmetic, scale_aware_cloud_amplitude()

### Community 54 - "cloud_deriv_subs.f"
Cohesion: 0.53
Nodes (5): parse_wx_pcp(), parse_wx_string(), put_laps_3d_multi(), put_laps_multi_3d_append(), sao_precip_correction()

### Community 56 - "Original KLAPS upstream replay harness"
Cohesion: 0.40
Nodes (4): Command, Current deterministic blockers, Original KLAPS upstream replay harness, Test

### Community 57 - "lapsio.f"
Cohesion: 0.50
Nodes (3): get_laps_3d_analysis_data_ex, get_laps_3d_analysis_data(), get_laps_3d_analysis_data_ex()

### Community 59 - "test_real_shadow_reader"
Cohesion: 0.40
Nodes (4): cloud_bal_real_netcdf, cloud_bal_state, iso_fortran_env, test_real_shadow_reader

### Community 60 - "wps_module_stubs.f90"
Cohesion: 0.40
Nodes (3): date_pack, laps_static, setup

### Community 61 - "Intel-only integration readiness audit"
Cohesion: 0.50
Nodes (3): Contract, Intel-only integration readiness audit, Smallest safe full-link probe

### Community 63 - "pcpcnc.f"
Cohesion: 0.67
Nodes (3): cpt_concentration(), cpt_fall_velocity(), ieee_arithmetic

### Community 64 - "test_wps_writer_status"
Cohesion: 0.50
Nodes (3): lapsprep_wps, setup, test_wps_writer_status

### Community 95 - "5. Conservative hydrometeor allocation"
Cohesion: 0.33
Nodes (6): 5.1 Cell-level validation, 5.2 Remove implicit mass sinks and sources, 5.3 Grid scaling and cloud fraction, 5.4 Phase allocation, 5.5 Order of operations, 5. Conservative hydrometeor allocation

### Community 96 - "1. Consolidated problems"
Cohesion: 0.40
Nodes (5): 1.1 Missing values and source status are destroyed, 1.2 Balance strength is hard-coded and not tied to data quality, 1.3 Hydrometeor initialization is not mass conservative, 1.4 Background use is all-or-nothing, 1. Consolidated problems

## Knowledge Gaps
- **244 isolated node(s):** `qbalpe_main`, `iso_fortran_env`, `ieee_arithmetic`, `cloud_bal_state`, `ieee_arithmetic` (+239 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 416 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `cloud_bal_state_type` connect `cloud_bal_state_type` to `cloud_bal_state`, `cloud_bal_real_netcdf`, `cloud_bal_legacy_shadow_adapter`, `cloud_bal_balance_operator`, `real_shadow_driver`, `test_nonuniform_localization`, `test_state_atomic_refresh`, `test_balance_operator`, `test_balance_omega_authority`, `test_canonical_state`, `test_column_physics`?**
  _High betweenness centrality (0.094) - this node is a cross-community bridge._
- **Why does `field3d` connect `cloud_bal_real_netcdf` to `cloud_bal_state_type`, `cloud_bal_state`, `cloud_bal_legacy_shadow_adapter`, `cloud_bal_balance_operator`, `test_balance_operator`, `test_balance_omega_authority`, `test_canonical_state`, `test_column_physics`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `cloud_bal_state` connect `cloud_bal_state` to `cloud_bal_state_type`, `cloud_bal_real_netcdf`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **What connects `qbalpe_main`, `iso_fortran_env`, `ieee_arithmetic` to the rest of the system?**
  _244 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `cloud_bal_state_type` be split into smaller, more focused modules?**
  _Cohesion score 0.05553923009109609 - nodes in this community are weakly interconnected._
- **Should `cloud_bal_state` be split into smaller, more focused modules?**
  _Cohesion score 0.05949367088607595 - nodes in this community are weakly interconnected._
- **Should `cloud_bal_real_netcdf` be split into smaller, more focused modules?**
  _Cohesion score 0.053776079929473995 - nodes in this community are weakly interconnected._