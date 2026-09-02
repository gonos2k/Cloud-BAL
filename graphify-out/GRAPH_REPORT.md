# Graph Report - Cloud-BAL  (2026-09-02)

## Corpus Check
- 79 files · ~114,560 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 805 nodes · 1243 edges · 76 communities (57 shown, 19 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 10 edges (avg confidence: 0.74)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `088a996f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]

## God Nodes (most connected - your core abstractions)
1. `cloud_bal_state` - 56 edges
2. `cloud_bal_balance_operator` - 46 edges
3. `cloud_bal_column_physics` - 41 edges
4. `cloud_bal_real_netcdf` - 31 edges
5. `balance_operator_type` - 27 edges
6. `test_balance_operator` - 25 edges
7. `cloud_bal_radar_downdraft` - 21 edges
8. `make_balance_state()` - 20 edges
9. `test_pipeline` - 19 edges
10. `TransactionError` - 19 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `Dataset`  [INFERRED]
  tests/test_compare_baseline.py → tools/plot_shadow_comparison.py
- `accepted()` --calls--> `canonical_omega_target_cells()`  [INFERRED]
  tests/test_shadow_validator.py → tools/validate_shadow_diagnostics.py
- `main()` --calls--> `comparison_files()`  [INFERRED]
  tests/test_compare_baseline.py → tools/compare_baseline.py
- `main()` --calls--> `numeric_summary()`  [INFERRED]
  tests/test_compare_baseline.py → tools/compare_baseline.py
- `main()` --calls--> `read_wps()`  [INFERRED]
  tests/test_compare_baseline.py → tools/compare_baseline.py

## Import Cycles
- None detected.

## Communities (76 total, 19 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (45): canonical_input_spec, canonical_vertical_order_valid(), cloud_bal_state, cloud_bal_state_type, commit_candidate(), coverage_summary, dry_air_mass_measure_consistent(), field2d (+37 more)

### Community 1 - "Community 1"
Cohesion: 0.10
Nodes (47): add_node(), apply_adjoint_metric(), apply_balance_correction(), apply_continuity_operator(), apply_localized_balance(), apply_normal_operator(), apply_normal_operator_work(), balance_operator_config (+39 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (37): account_bottom_flux(), add_loading_downdraft(), allocate_precipitation_phase(), build_cloud_targets(), cloud_bal_column_physics, column_changed_mask(), column_config_valid(), column_physics_config (+29 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (42): Adversarial-review acceptance checklist, Canonical units and schema, Changes, Changes, Changes, Changes, Changes, Changes (+34 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (27): assign_reversed_core(), assign_specific_humidity(), assign_surface(), close_file(), cloud_bal_real_netcdf, mark_real_field(), open_case_file(), open_static_file() (+19 more)

### Community 5 - "Community 5"
Cohesion: 0.18
Nodes (25): OutputTransaction, expect_rejected(), main(), write_products(), _current(), _current_id(), _fsync_directory(), _identifier() (+17 more)

### Community 6 - "Community 6"
Cohesion: 0.17
Nodes (27): add_held_out_los(), check(), cloud_bal_balance_operator, cloud_bal_state, cloud_bal_state_type, field3d, iso_fortran_env, make_balance_state() (+19 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (22): integer_field3d, add_radar_cell(), cloud_bal_column_physics, cloud_bal_pipeline, cloud_bal_state, cloud_bal_state_type, field2d, field3d (+14 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (24): 1.1 Missing values and source status are destroyed, 1.2 Balance strength is hard-coded and not tied to data quality, 1.3 Hydrometeor initialization is not mass conservative, 1.4 Background use is all-or-nothing, 1. Consolidated problems, 2. Data contract introduced before physics changes, 3.1 Safe first policy: missing-only fallback, 3.2 Confidence blend after the fallback is validated (+16 more)

### Community 9 - "Community 9"
Cohesion: 0.14
Nodes (12): build_observed_mask(), cloud_bal_radar_downdraft, config_is_valid(), couple_radar_precipitation(), diagnose_bounded_downdraft(), fill_lower_gaps(), maximum_valid_w_change(), radar_downdraft_config (+4 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (19): add_radar_cell(), core_value_differences(), cloud_bal_balance_operator, cloud_bal_pipeline, cloud_bal_pipeline_config, cloud_bal_pipeline_result, cloud_bal_state, cloud_bal_state_type (+11 more)

### Community 11 - "Community 11"
Cohesion: 0.21
Nodes (17): RuntimeError, field_records(), main(), record(), comparison_files(), digest(), files_under(), looks_like_wps() (+9 more)

### Community 12 - "Community 12"
Cohesion: 0.20
Nodes (17): check(), cloud_bal_state, cloud_bal_state_type, field2d, field3d, ieee_arithmetic, iso_fortran_env, fill_real_field() (+9 more)

### Community 13 - "Community 13"
Cohesion: 0.35
Nodes (16): Axes, Dataset, Figure, add_map(), array(), horizontal_figure(), main(), precipitation() (+8 more)

### Community 14 - "Community 14"
Cohesion: 0.21
Nodes (16): cloud_bal_cloud_profiles, cloud_bal_localization, cloud_bal_radar_downdraft, cloud_bal_wind_modes, check(), check_close(), cloud_bal_field_contracts, cloud_bal_moisture (+8 more)

### Community 15 - "Community 15"
Cohesion: 0.23
Nodes (15): check(), cloud_bal_column_physics, cloud_bal_state, cloud_bal_state_type, field3d, iso_fortran_env, make_state(), test_column_physics (+7 more)

### Community 16 - "Community 16"
Cohesion: 0.15
Nodes (21): dtype, accepted(), canonical_omega_target_cells(), changed_bits(), continuity_increment(), continuity_state(), is_signed_int32(), main() (+13 more)

### Community 17 - "Community 17"
Cohesion: 0.17
Nodes (6): analzo(), continuity_metrics(), continuity_point(), leib_sub(), qbalpe_main, ieee_arithmetic

### Community 18 - "Community 18"
Cohesion: 0.14
Nodes (14): 10. Rollout, 11. Physical basis, 1. Problem statement, 2. Sign and unit conventions, 3. Legacy radar code retained as design evidence, 4.1 Status of the empirical cloud vertical velocity, 4. Coupled analysis sequence, 5. Precipitation trajectory and hydrometeor alignment (+6 more)

### Community 19 - "Community 19"
Cohesion: 0.40
Nodes (13): Namespace, contained_input(), expected_epoch(), forbidden_reason(), inspect_netcdf(), main(), normalize_units(), parse_args() (+5 more)

### Community 20 - "Community 20"
Cohesion: 0.15
Nodes (12): constants, lapsprep, lapsprep_mm5, lapsprep_netcdf, lapsprep_rams, lapsprep_wrf, cloud_bal_field_contracts, cloud_bal_moisture (+4 more)

### Community 21 - "Community 21"
Cohesion: 0.15
Nodes (4): cpt_pcp_type_3d(), for, given, nowrad_virga_correction()

### Community 22 - "Community 22"
Cohesion: 0.41
Nodes (11): inspect_case(), inspect_radar(), main(), ndarray, Path, Variable, sha256(), site_from_comment() (+3 more)

### Community 23 - "Community 23"
Cohesion: 0.32
Nodes (10): capture_field_validity_1d(), capture_field_validity_2d(), capture_field_validity_3d(), cloud_bal_field_contracts, contract_metadata_ok(), field_contract, initialize_field_contract(), refresh_field_status() (+2 more)

### Community 24 - "Community 24"
Cohesion: 0.23
Nodes (11): build_compact_balance_beta(), cloud_bal_pipeline, cloud_bal_pipeline_config, cloud_bal_pipeline_result, run_cloud_bal_pipeline(), cloud_bal_balance_operator, cloud_bal_column_physics, cloud_bal_state (+3 more)

### Community 25 - "Community 25"
Cohesion: 0.20
Nodes (8): cloud_bal_real_netcdf, core_value_differences(), cloud_bal_balance_operator, cloud_bal_pipeline, cloud_bal_state, cloud_bal_state_type, iso_fortran_env, real_shadow_driver

### Community 26 - "Community 26"
Cohesion: 0.25
Nodes (4): Cloud-BAL, Data flow, Deliberate exclusions, Repository layout

### Community 27 - "Community 27"
Cohesion: 0.25
Nodes (7): 1. Direct QBAL read closure, 2. Original producer chain needed to recreate the direct inputs, 3. Candidate radar extension, 4. Prepared cases and current readiness, 5. Deterministic background selection, 6. Forbidden inputs and fail-closed gates, QBAL real-input contract

### Community 29 - "Community 29"
Cohesion: 0.33
Nodes (6): date_pack, lapsprep_wps, output_ungrib_format(), write_ungrib_header(), laps_static, setup

### Community 30 - "Community 30"
Cohesion: 0.29
Nodes (6): Cloud-BAL implementation report, Decision, Implemented focused candidate, Integration blockers, Preserved comparison baseline, Verification completed

### Community 31 - "Community 31"
Cohesion: 0.29
Nodes (6): Cloud-BAL 단일 승인 체크리스트, P0 체크리스트, 단일 계약, 레이더 시선속도 판정, 실제자료 전수 증거, 운영 승격 전에 반드시 남은 시험

### Community 32 - "Community 32"
Cohesion: 0.29
Nodes (7): 1. 운형과 연직속도, 2. S-band 반사도와 시선속도, 3. 기울어진 강수 구조와 fall-flux 재구성, 4. 국지 질량-바람 projection, 5. 파동과 동역학적 안전성, Cloud-BAL 과학적 기초와 구현 경계, 결론

### Community 33 - "Community 33"
Cohesion: 0.43
Nodes (4): read_multiradar_3dref(), read_nowrad_3dref(), read_radar_3dref(), read_vrz_3dref()

### Community 34 - "Community 34"
Cohesion: 0.52
Nodes (6): run_isolation_gate.sh script, check_baseline_contract(), check_candidate_contract(), hash_live_inputs(), inventory_baseline(), inventory_live_tree()

### Community 36 - "Community 36"
Cohesion: 0.33
Nodes (4): test_writeballaps_status, write_laps_data(), writer_failure_control, writer_failure_control

### Community 37 - "Community 37"
Cohesion: 0.40
Nodes (4): build_multilayer_w_profile(), cloud_bal_cloud_profiles, detect_cloud_layers(), ieee_arithmetic

### Community 38 - "Community 38"
Cohesion: 0.53
Nodes (5): parse_wx_pcp(), parse_wx_string(), put_laps_3d_multi(), put_laps_multi_3d_append(), sao_precip_correction()

### Community 39 - "Community 39"
Cohesion: 0.33
Nodes (5): Baseline review, Current operational behavior, Initial test matrix, Priority defects, Required acceptance gates

### Community 41 - "Community 41"
Cohesion: 0.50
Nodes (3): get_laps_3d_analysis_data(), get_laps_3d_analysis_data_ex(), get_laps_3d_analysis_data_ex

### Community 44 - "Community 44"
Cohesion: 0.70
Nodes (4): run_real_shadow_cases.sh script, pin_build_file(), verify_build_files(), verify_input()

### Community 45 - "Community 45"
Cohesion: 0.40
Nodes (3): date_pack, laps_static, setup

### Community 47 - "Community 47"
Cohesion: 0.67
Nodes (3): cpt_concentration(), cpt_fall_velocity(), ieee_arithmetic

### Community 48 - "Community 48"
Cohesion: 0.50
Nodes (3): lapsprep_wps, setup, test_wps_writer_status

## Knowledge Gaps
- **202 isolated node(s):** `qbalpe_main`, `iso_fortran_env`, `ieee_arithmetic`, `cloud_bal_state`, `ieee_arithmetic` (+197 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Cloud-BAL improvement plan` connect `Community 8` to `Community 26`?**
  _High betweenness centrality (0.005) - this node is a cross-community bridge._
- **Why does `numeric_summary()` connect `Community 11` to `Community 13`?**
  _High betweenness centrality (0.004) - this node is a cross-community bridge._
- **What connects `qbalpe_main`, `iso_fortran_env`, `ieee_arithmetic` to the rest of the system?**
  _215 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06203007518796992 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.10459183673469388 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.08599033816425121 - nodes in this community are weakly interconnected._
- **Should `Community 3` be split into smaller, more focused modules?**
  _Cohesion score 0.046511627906976744 - nodes in this community are weakly interconnected._