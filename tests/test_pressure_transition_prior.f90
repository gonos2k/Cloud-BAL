PROGRAM test_pressure_transition_prior
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state, ONLY: cloud_bal_state_type,field3d,field2d,stage_result, &
    initialize_cloud_bal_state,initialize_field,configure_pressure_geometry, &
    refresh_dry_air_mass_measure,canonical_states_equal,STATUS_OK,STATUS_FAILED, &
    MODE_OFF,MODE_SHADOW, &
    SOURCE_BACKGROUND_MODEL,SOURCE_ANALYZED_WIND,SOURCE_OUTPUT_ADAPTER, &
    SOURCE_COLUMN_PHYSICS,SOURCE_MANUFACTURED_TEST,SOURCE_DYNAMIC_TARGET,QUALITY_RAW_MISSING,QUALITY_QC_REJECTED, &
    QUALITY_LEGACY_PROVENANCE,QUALITY_BELOW_GROUND_FILLED
  USE cloud_bal_column_physics, ONLY: pressure_analysis_budget,SATURATION_LIQUID, &
    apply_pressure_domain_transition,apply_pressure_hydrostatic_increment, &
    rebase_pressure_transition_prior
  USE cloud_bal_balance_operator, ONLY: apply_localized_balance
  USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_config,cloud_bal_pipeline_result, &
    run_cloud_bal_pipeline,build_compact_balance_beta
  USE cloud_bal_wps_adapter, ONLY: pressure_wps_fields, &
    build_pressure_transition_prior,map_pressure_candidate_to_wps
  IMPLICIT NONE

  INTEGER, PARAMETER :: NX=4,NY=4,NZ=3
  INTEGER(int64), PARAMETER :: VALID_TIME=1788224400_int64
  REAL(real64), PARAMETER :: G=9.80665_real64
  REAL(real64), PARAMETER :: PRESSURE(NZ)=[100000.0_real64,95000.0_real64,90000.0_real64]
  CHARACTER(LEN=*), PARAMETER :: GRID_ID='pressure-transition-prior'
  CHARACTER(LEN=*), PARAMETER :: WIND='GRID_RELATIVE'
  INTEGER :: failures

  failures=0
  CALL test_order(.TRUE.)
  CALL test_order(.FALSE.)
  CALL test_mixed_columns
  CALL test_fully_active_nonactivation
  CALL test_terrain_excluded_positive
  CALL test_pipeline_seed
  CALL test_pipeline_signed_mixed
  IF (failures/=0) THEN
    PRINT '(A,I0)','Pressure transition-prior tests failed: ',failures
    ERROR STOP 1
  END IF
  PRINT '(A)','Pressure transition-prior tests passed'

CONTAINS

  SUBROUTINE check(ok,message)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF (.NOT.ok) THEN
      failures=failures+1
      PRINT '(A)','FAIL: '//TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE test_order(ascending)
    LOGICAL, INTENT(IN) :: ascending
    TYPE(cloud_bal_state_type) :: background,prior,candidate,original
    TYPE(pressure_wps_fields) :: retained,bad_retained
    TYPE(field3d) :: retained_omega,bad_omega
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    REAL(real64) :: requested(NX,NY),no_op(NX,NY)
    INTEGER :: status
    CHARACTER(LEN=64) :: suffix

    IF (ascending) THEN
      suffix='ascending'
    ELSE
      suffix='descending'
    END IF
    CALL make_background(background,status)
    CALL check(status==STATUS_OK,TRIM(suffix)//' background fixture')
    IF (status/=STATUS_OK) RETURN
    ! Immutable donors keep their phase-storage defect; prior cells whose
    ! pressure geometry changes receive a refreshed mass denominator.
    background%grid%dry_air_mass_measure(1,1,2)= &
      background%grid%dry_air_mass_measure(1,1,2)*(1.0_real64+1.0e-9_real64)
    background%grid%dry_air_mass_measure(1,1,3)= &
      background%grid%dry_air_mass_measure(1,1,3)*(1.0_real64+1.0e-9_real64)
    original=background
    CALL make_retained(background,retained,ascending)
    CALL make_retained_omega(retained_omega)
    requested=REAL(background%surface_pressure%value,real64)
    requested(1,1)=100010.0_real64

    CALL build_pressure_transition_prior(background,retained,retained_omega, &
      requested,prior,status)
    CALL check(status==STATUS_OK,TRIM(suffix)//' prior construction')
    IF (status/=STATUS_OK) RETURN
    CALL check(ALL(prior%above_ground(1,1,:)),TRIM(suffix)//' one new center activates')
    CALL check(ALL(prior%above_ground(2,1,:).EQV.background%above_ground(2,1,:)), &
      TRIM(suffix)//' unchanged column domain')
    CALL check(ABS(prior%grid%dry_air_mass_measure(1,1,3)- &
      background%grid%dry_air_mass_measure(1,1,3))<1.0e-12_real64, &
      TRIM(suffix)//' unchanged-geometry dry mass metadata is restored')
    CALL check(prior%grid%dry_air_mass_measure(1,1,2)< &
      background%grid%dry_air_mass_measure(1,1,2), &
      TRIM(suffix)//' repartitioned prior bottom uses new geometry')
    CALL check(canonical_states_equal(background,original),TRIM(suffix)//' immutable donors preserved')
    CALL check(ABS(REAL(prior%surface_pressure%value(1,1),real64)-100010.0_real64)<0.01_real64, &
      TRIM(suffix)//' requested surface pressure stored')
    CALL check(ALL(prior%surface_temperature%value==background%surface_temperature%value) .AND. &
      ALL(prior%surface_vapor%value==background%surface_vapor%value) .AND. &
      ALL(prior%surface_height%value==background%surface_height%value), &
      TRIM(suffix)//' surface T/Q/height remain unchanged')
    CALL check(prior%temperature%value(1,1,1)==315.0_real32 .AND. &
      prior%vapor%value(1,1,1)==0.012_real32 .AND. &
      prior%cloud_water%value(1,1,1)==0.0010_real32 .AND. &
      prior%cloud_ice%value(1,1,1)==0.0005_real32 .AND. &
      prior%rain%value(1,1,1)==0.0002_real32 .AND. &
      prior%snow%value(1,1,1)==0.0001_real32 .AND. &
      prior%graupel%value(1,1,1)==0.00005_real32, &
      TRIM(suffix)//' new thermodynamic fields come from retained WPS')
    CALL check(prior%u%value(1,1,1)==11.0_real32 .AND. &
      prior%v%value(1,1,1)==-7.0_real32 .AND. &
      prior%geopotential%value(1,1,1)==REAL(G*150.0_real64,real32), &
      TRIM(suffix)//' new wind and height come from retained WPS')
    CALL check(prior%omega%value(1,1,1)==4.25_real32 .AND. &
      prior%omega%quality(1,1,1)==retained_omega%quality(1,1,1) .AND. &
      prior%omega%source(1,1,1)==retained_omega%source(1,1,1), &
      TRIM(suffix)//' nonzero new omega retains analyzed provenance')
    CALL check(new_reconstruction_metadata(prior,1,1,1), &
      TRIM(suffix)//' new reconstruction metadata is explicit and legacy')
    CALL check(prior%pressure%valid(1,1,1) .AND. &
      prior%pressure%source(1,1,1)==SOURCE_OUTPUT_ADAPTER, &
      TRIM(suffix)//' new pressure coordinate is valid adapter data')
    CALL check(old_active_unchanged(background,prior,1,1), &
      TRIM(suffix)//' old active cells retain original fields and metadata')
    CALL check(untouched_column_unchanged(background,prior), &
      TRIM(suffix)//' untouched column is unchanged')
    CALL check(prior%obs_support(1,1,1)==0_int32 .AND. &
      prior%hydro_support(1,1,1)==0_int32 .AND. prior%balance_beta(1,1,1)==0.0_real32 .AND. &
      .NOT.prior%omega_target%valid(1,1,1) .AND. &
      .NOT.prior%omega_target_sigma%valid(1,1,1), &
      TRIM(suffix)//' new support and target state is clear')

    CALL apply_pressure_domain_transition(background,prior,candidate,result,budget)
    CALL check(result%status==STATUS_OK,TRIM(suffix)//' prior passes pressure transition')
    IF (result%status==STATUS_OK) THEN
      CALL check(candidate%geopotential%value(1,1,1)>0.0_real32 .AND. &
        candidate%geopotential%value(1,1,2)>candidate%geopotential%value(1,1,1) .AND. &
        candidate%geopotential%value(1,1,3)>candidate%geopotential%value(1,1,2), &
        TRIM(suffix)//' transition output has sane monotone Phi')
      CALL check(IAND(candidate%u%source(1,1,1),SOURCE_COLUMN_PHYSICS)/=0_int32 .AND. &
        IAND(candidate%v%source(1,1,1),SOURCE_COLUMN_PHYSICS)/=0_int32 .AND. &
        IAND(candidate%omega%source(1,1,1),SOURCE_COLUMN_PHYSICS)/=0_int32 .AND. &
        IAND(candidate%u%source(1,1,1),SOURCE_ANALYZED_WIND)==0_int32 .AND. &
        IAND(candidate%v%source(1,1,1),SOURCE_ANALYZED_WIND)==0_int32, &
        TRIM(suffix)//' transition output grants no new wind authority')
    END IF

    no_op=REAL(background%surface_pressure%value,real64)
    CALL build_pressure_transition_prior(background,retained,retained_omega,no_op,prior,status)
    CALL check(status==STATUS_OK .AND. canonical_states_equal(prior,background), &
      TRIM(suffix)//' no-op returns original background')

    bad_omega=retained_omega
    bad_omega%valid(1,1,1)=.FALSE.; bad_omega%quality(1,1,1)=QUALITY_RAW_MISSING
    bad_omega%source(1,1,1)=0_int32
    CALL expect_reject(background,retained,bad_omega,requested,'missing omega')
    bad_omega=retained_omega
    bad_omega%quality(1,1,1)=QUALITY_QC_REJECTED
    CALL expect_reject(background,retained,bad_omega,requested,'raw-QC omega')
    bad_omega=retained_omega; bad_omega%valid_time=VALID_TIME+1_int64
    CALL expect_reject(background,retained,bad_omega,requested,'omega time mismatch')
    bad_omega=retained_omega; bad_omega%unit='m s-1'
    CALL expect_reject(background,retained,bad_omega,requested,'omega unit mismatch')
    bad_omega=retained_omega
    bad_omega%source(1,1,1)=IOR(SOURCE_ANALYZED_WIND,SOURCE_MANUFACTURED_TEST)
    CALL expect_reject(background,retained,bad_omega,requested,'manufactured omega')
    bad_omega%source(1,1,1)=IOR(SOURCE_ANALYZED_WIND,SOURCE_DYNAMIC_TARGET)
    CALL expect_reject(background,retained,bad_omega,requested,'target injected as raw omega')

    bad_retained=retained; bad_retained%wind_coordinate='EARTH_RELATIVE'
    CALL expect_reject(background,bad_retained,retained_omega,requested,'wind frame mismatch')
    bad_retained=retained; bad_retained%p(2)=bad_retained%p(1)
    CALL expect_reject(background,bad_retained,retained_omega,requested,'non-monotone WPS order')
    bad_retained=retained
    IF (ascending) THEN
      bad_retained%p(2)=951.0_real32
    ELSE
      bad_retained%p(2)=949.0_real32
    END IF
    CALL expect_reject(background,bad_retained,retained_omega,requested,'pressure coordinate mismatch')

    requested(1,1)=99990.0_real64
    CALL expect_reject(background,retained,retained_omega,requested,'negative pressure increment')
    requested(1,1)=99999.5_real64
    CALL build_pressure_transition_prior(background,retained,retained_omega,requested,prior,status)
    CALL check(status==STATUS_OK,TRIM(suffix)//' positive nonactivating request is accepted')
    IF (status==STATUS_OK) THEN
      CALL check(ALL(prior%above_ground.EQV.background%above_ground), &
        TRIM(suffix)//' nonactivating request preserves the domain')
      CALL check(ABS(REAL(prior%surface_pressure%value(1,1),real64)-99999.5_real64)<0.01_real64, &
        TRIM(suffix)//' nonactivating request stores PSFC')
    END IF
    requested(1,1)=100101.0_real64
    CALL expect_reject(background,retained,retained_omega,requested,'pressure increment cap')
  END SUBROUTINE test_order

  SUBROUTINE test_mixed_columns
    TYPE(cloud_bal_state_type) :: background,prior,candidate,hydro_reference
    TYPE(pressure_wps_fields) :: retained
    TYPE(field3d) :: retained_omega
    TYPE(stage_result) :: result,hydro_result
    TYPE(pressure_analysis_budget) :: budget,hydro_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY),status
    REAL(real64) :: requested(NX,NY),hydro_request(NX,NY)
    REAL(real64) :: expected_geometry,area

    CALL make_background(background,status)
    CALL check(status==STATUS_OK,'mixed-column background fixture')
    IF (status/=STATUS_OK) RETURN
    CALL set_mixed_authority(background)
    CALL make_retained(background,retained,.FALSE.)
    CALL make_retained_omega(retained_omega)
    requested=REAL(background%surface_pressure%value,real64)
    requested(1,1)=100010.0_real64
    requested(2,1)=99999.5_real64

    CALL build_pressure_transition_prior(background,retained,retained_omega, &
      requested,prior,status)
    CALL check(status==STATUS_OK,'mixed-column constructor accepts one crossing and one nonactivation')
    IF (status/=STATUS_OK) RETURN
    CALL check(ALL(prior%above_ground(1,1,:)) .AND. &
      ALL(prior%above_ground(2,1,:).EQV.background%above_ground(2,1,:)), &
      'mixed constructor activates only the crossing column')
    CALL check(ABS(REAL(prior%surface_pressure%value(1,1),real64)-100010.0_real64)<0.01_real64 .AND. &
      ABS(REAL(prior%surface_pressure%value(2,1),real64)-99999.5_real64)<0.01_real64, &
      'mixed constructor stores both requested PSFC values')
    CALL check(old_active_unchanged(background,prior,2,1) .AND. &
      old_authority_unchanged(background,prior,2,1), &
      'nonactivating prior preserves bottom winds targets and support')
    CALL check(ALL(prior%surface_temperature%value==background%surface_temperature%value) .AND. &
      ALL(prior%surface_vapor%value==background%surface_vapor%value) .AND. &
      ALL(prior%surface_height%value==background%surface_height%value), &
      'mixed constructor preserves surface anchors')
    CALL check(prior%grid%pressure_mass_measure(2,1,2)> &
      background%grid%pressure_mass_measure(2,1,2) .AND. &
      prior%grid%pressure_mass_measure(2,1,3)== &
      background%grid%pressure_mass_measure(2,1,3), &
      'nonactivating prior changes only existing bottom pressure mass')

    CALL apply_pressure_domain_transition(background,prior,candidate,result,budget)
    CALL check(result%status==STATUS_OK,'mixed-column transition succeeds')
    IF (result%status/=STATUS_OK) RETURN
    CALL check(ALL(candidate%above_ground(1,1,:)) .AND. &
      ALL(candidate%above_ground(2,1,:).EQV.background%above_ground(2,1,:)), &
      'mixed transition has one new center and one unchanged domain')
    CALL check(old_authority_unchanged(background,candidate,2,1), &
      'mixed transition preserves nonactivating winds targets and support')
    CALL check(ALL(candidate%surface_temperature%value==background%surface_temperature%value) .AND. &
      ALL(candidate%surface_vapor%value==background%surface_vapor%value) .AND. &
      ALL(candidate%surface_height%value==background%surface_height%value), &
      'mixed transition preserves surface anchors')

    ! The nonactivating column must receive the ordinary surface-anchored
    ! hydrostatic response, not an absolute Phi reset or a second mass donor.
    support=background%above_ground; reference_level=0
    hydro_request=REAL(background%surface_pressure%value,real64)
    hydro_request(2,1)=99999.5_real64
    CALL apply_pressure_hydrostatic_increment(background,background,hydro_reference, &
      hydro_result,support,reference_level,hydro_request,hydro_budget)
    IF (hydro_result%status/=STATUS_OK) PRINT '(A,2(I0,1X))', &
      'mixed hydro reference status/reason: ',hydro_result%status,hydro_result%reason_code
    CALL check(hydro_result%status==STATUS_OK,'nonactivating hydrostatic reference succeeds')
    IF (hydro_result%status==STATUS_OK) THEN
      CALL check(ALL(hydro_reference%pressure%valid.EQV.background%pressure%valid) .AND. &
        ALL(hydro_reference%pressure%quality==background%pressure%quality) .AND. &
        ALL(hydro_reference%pressure%source==background%pressure%source), &
        'hydrostatic geometry refresh preserves masked pressure metadata')
      CALL check(MAXVAL(ABS(REAL(candidate%geopotential%value(2,1,:),real64)- &
        REAL(hydro_reference%geopotential%value(2,1,:),real64)))<1.0e-3_real64, &
        'nonactivating Phi matches surface-pressure hydrostatic response')
    END IF
    area=background%grid%dx(1,1)*background%grid%dy(1,1)
    expected_geometry=area*((100010.0_real64-99999.125_real64)+ &
      (99999.5_real64-99999.125_real64))/G
    CALL check(ABS(budget%geometry_mass_change_kg-expected_geometry)< &
      1.0e-6_real64*MAX(1.0_real64,ABS(expected_geometry)), &
      'mixed transition accounts A*dPS/g once for both columns')
  END SUBROUTINE test_mixed_columns

  SUBROUTINE test_fully_active_nonactivation
    TYPE(cloud_bal_state_type) :: background,prior,candidate
    TYPE(pressure_wps_fields) :: retained
    TYPE(field3d) :: retained_omega
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    REAL(real64) :: requested(NX,NY),expected_geometry
    INTEGER :: status

    CALL make_background(background,status)
    CALL check(status==STATUS_OK,'fully-active nonactivation background fixture')
    IF (status/=STATUS_OK) RETURN
    ! Promote the retained first center before geometry is configured so the
    ! positive request cannot accidentally evaluate a nonexistent k=0 donor.
    CALL mark3(background%pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark3(background%temperature,SOURCE_BACKGROUND_MODEL)
    CALL mark3(background%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL mark3(background%vapor,SOURCE_BACKGROUND_MODEL)
    CALL mark3(background%u,SOURCE_BACKGROUND_MODEL); CALL mark3(background%v,SOURCE_BACKGROUND_MODEL)
    CALL mark3(background%omega,SOURCE_BACKGROUND_MODEL)
    CALL mark3(background%cloud_water,SOURCE_BACKGROUND_MODEL); CALL mark3(background%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL mark3(background%rain,SOURCE_BACKGROUND_MODEL); CALL mark3(background%snow,SOURCE_BACKGROUND_MODEL)
    CALL mark3(background%graupel,SOURCE_BACKGROUND_MODEL)
    background%surface_pressure%value=100050.0_real32
    CALL configure_pressure_geometry(background,status)
    IF (status/=STATUS_OK) THEN
      CALL check(.FALSE.,'fully-active nonactivation geometry fixture')
      RETURN
    END IF
    CALL mask_to_domain(background)
    CALL refresh_dry_air_mass_measure(background,status)
    CALL check(status==STATUS_OK,'fully-active nonactivation mass fixture')
    IF (status/=STATUS_OK) RETURN
    CALL make_retained(background,retained,.FALSE.)
    CALL make_retained_omega(retained_omega)
    requested=REAL(background%surface_pressure%value,real64)
    requested(1,1)=100075.0_real64
    CALL build_pressure_transition_prior(background,retained,retained_omega,requested,prior,status)
    CALL check(status==STATUS_OK,'fully-active positive nonactivation is accepted')
    IF (status/=STATUS_OK) RETURN
    CALL check(ALL(prior%above_ground), 'fully-active nonactivation preserves all centers')
    CALL apply_pressure_domain_transition(background,prior,candidate,result,budget)
    CALL check(result%status==STATUS_OK,'fully-active nonactivation transition succeeds')
    IF (result%status/=STATUS_OK) RETURN
    CALL check(ALL(candidate%above_ground) .AND. &
      ABS(REAL(candidate%surface_pressure%value(1,1),real64)-100075.0_real64)<0.01_real64, &
      'fully-active nonactivation stores PS without a new center')
    CALL check(ALL(candidate%temperature%value==background%temperature%value) .AND. &
      ALL(candidate%vapor%value==background%vapor%value) .AND. &
      ALL(candidate%u%value==background%u%value) .AND. &
      ALL(candidate%v%value==background%v%value) .AND. &
      ALL(candidate%omega%value==background%omega%value), &
      'fully-active nonactivation preserves existing payload and winds')
    expected_geometry=background%grid%dx(1,1)*background%grid%dy(1,1)*25.0_real64/G
    CALL check(ABS(budget%geometry_mass_change_kg-expected_geometry)< &
      1.0e-6_real64*MAX(1.0_real64,ABS(expected_geometry)), &
      'fully-active nonactivation accounts one boundary mass increment')
  END SUBROUTINE test_fully_active_nonactivation

  SUBROUTINE test_terrain_excluded_positive
    TYPE(cloud_bal_state_type) :: background,prior,candidate,rebased
    TYPE(cloud_bal_state_type) :: pipeline_candidate,pipeline_operational
    TYPE(pressure_wps_fields) :: retained
    TYPE(field3d) :: retained_omega
    TYPE(stage_result) :: transition_result
    TYPE(pressure_analysis_budget) :: transition_budget
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: pipeline_result
    LOGICAL :: terrain_domain(NX,NY,NZ),support(NX,NY,NZ),selected_columns(NX,NY)
    INTEGER :: reference_level(NX,NY),status
    REAL(real64) :: requested(NX,NY),terrain_height

    CALL make_background(background,status)
    CALL check(status==STATUS_OK,'terrain-excluded background fixture')
    IF (status/=STATUS_OK) RETURN
    background%surface_pressure%value(1,1)=100060.195_real32
    background%surface_height%value(1,1)=200.0_real32
    CALL mark3(background%pressure,SOURCE_BACKGROUND_MODEL)
    terrain_domain=background%above_ground
    terrain_domain(1,1,1)=.FALSE.
    CALL configure_pressure_geometry(background,status,terrain_domain)
    CALL check(status==STATUS_OK,'terrain-excluded constrained geometry fixture')
    IF (status/=STATUS_OK) RETURN
    CALL mask_to_domain(background)
    CALL refresh_dry_air_mass_measure(background,status)
    CALL check(status==STATUS_OK,'terrain-excluded mass fixture')
    IF (status/=STATUS_OK) RETURN
    terrain_height=REAL(background%surface_height%value(1,1),real64)
    CALL check(REAL(background%surface_pressure%value(1,1),real64)> &
      REAL(background%pressure%value(1,1,1),real64) .AND. &
      .NOT.background%above_ground(1,1,1) .AND. &
      terrain_height>REAL(background%geopotential%value(1,1,1),real64)/G, &
      'terrain excludes the pressure-crossed center')

    CALL make_retained(background,retained,.FALSE.)
    CALL make_retained_omega(retained_omega)
    requested=REAL(background%surface_pressure%value,real64)
    requested(1,1)=100066.2890625_real64
    CALL build_pressure_transition_prior(background,retained,retained_omega, &
      requested,prior,status)
    CALL check(status==STATUS_OK,'terrain-excluded positive prior succeeds')
    IF (status/=STATUS_OK) RETURN
    CALL check(ALL(prior%above_ground.EQV.background%above_ground) .AND. &
      .NOT.prior%above_ground(1,1,1) .AND. &
      ABS(REAL(prior%surface_pressure%value(1,1),real64)-100066.2890625_real64)<0.01_real64, &
      'terrain-excluded prior updates PS without activating the center')
    CALL check(prior%temperature%value(1,1,1)==background%temperature%value(1,1,1) .AND. &
      (prior%temperature%valid(1,1,1).EQV.background%temperature%valid(1,1,1)) .AND. &
      prior%temperature%source(1,1,1)==background%temperature%source(1,1,1), &
      'terrain-excluded prior does not promote excluded-cell payload')

    selected_columns=.FALSE.; selected_columns(1,1)=.TRUE.
    CALL rebase_pressure_transition_prior(background,prior,rebased,status,selected_columns)
    CALL check(status==STATUS_OK .AND. ALL(rebased%above_ground.EQV.background%above_ground) .AND. &
      .NOT.rebased%above_ground(1,1,1) .AND. &
      rebased%surface_pressure%value(1,1)==prior%surface_pressure%value(1,1), &
      'terrain-excluded rebase retains the excluded center and PS')

    CALL apply_pressure_domain_transition(background,prior,candidate,transition_result,transition_budget)
    CALL check(transition_result%status==STATUS_OK .AND. &
      ALL(candidate%above_ground.EQV.background%above_ground) .AND. &
      .NOT.candidate%above_ground(1,1,1) .AND. &
      ABS(REAL(candidate%surface_pressure%value(1,1),real64)-100066.2890625_real64)<0.01_real64, &
      'terrain-excluded transition changes geometry without authority promotion')
    IF (transition_result%status==STATUS_OK) THEN
      CALL check(ABS(transition_budget%geometry_mass_change_kg- &
        background%grid%dx(1,1)*background%grid%dy(1,1)* &
        (REAL(candidate%surface_pressure%value(1,1),real64)- &
         REAL(background%surface_pressure%value(1,1),real64))/G)<1.0e-6_real64, &
        'terrain-excluded transition accounts only the PSFC increment')
      CALL check(candidate%temperature%value(1,1,1)==background%temperature%value(1,1,1) .AND. &
        (candidate%temperature%valid(1,1,1).EQV.background%temperature%valid(1,1,1)) .AND. &
        candidate%temperature%quality(1,1,1)==background%temperature%quality(1,1,1) .AND. &
        candidate%temperature%source(1,1,1)==background%temperature%source(1,1,1) .AND. &
        candidate%vapor%value(1,1,1)==background%vapor%value(1,1,1) .AND. &
        (candidate%vapor%valid(1,1,1).EQV.background%vapor%valid(1,1,1)) .AND. &
        candidate%vapor%quality(1,1,1)==background%vapor%quality(1,1,1) .AND. &
        candidate%vapor%source(1,1,1)==background%vapor%source(1,1,1) .AND. &
        candidate%u%value(1,1,1)==background%u%value(1,1,1) .AND. &
        candidate%v%value(1,1,1)==background%v%value(1,1,1) .AND. &
        candidate%omega%value(1,1,1)==background%omega%value(1,1,1), &
        'terrain-excluded final cell retains original payload authority')
    END IF

    support=background%above_ground; reference_level=0
    config%requested_mode=MODE_SHADOW
    config%maximum_outer_iterations=1
    config%balance%minimum_target_response_ratio=0.0_real64
    CALL run_cloud_bal_pipeline(background,pipeline_candidate,pipeline_operational, &
      pipeline_result,config,geopotential_support= support, &
      geopotential_reference_level=reference_level,requested_surface_pressure=requested, &
      pressure_transition_seed=prior)
    CALL check(pipeline_result%status==STATUS_OK .AND. &
      ALL(pipeline_candidate%above_ground.EQV.background%above_ground) .AND. &
      ABS(REAL(pipeline_candidate%surface_pressure%value(1,1),real64)-100066.2890625_real64)<0.01_real64 .AND. &
      canonical_states_equal(background,pipeline_operational), &
      'terrain-excluded pipeline preserves domain and operational input')
  END SUBROUTINE test_terrain_excluded_positive

  SUBROUTINE test_pipeline_seed
    TYPE(cloud_bal_state_type) :: background,seed,invalid_seed,baseline,baseline_operational
    TYPE(cloud_bal_state_type) :: candidate,operational,rebased,manual_transition,manual_final
    TYPE(pressure_wps_fields) :: retained,retained_reverse
    TYPE(field3d) :: retained_omega
    TYPE(cloud_bal_pipeline_config) :: config,off_config,cap_config
    TYPE(cloud_bal_pipeline_result) :: baseline_result,result,missing_result
    TYPE(cloud_bal_pipeline_result) :: support_result,cap_result,off_result,invalid_result
    TYPE(stage_result) :: transition_result,balance_result
    TYPE(pressure_analysis_budget) :: transition_budget
    LOGICAL :: thermo_active(NX,NY,NZ),geopotential_support(NX,NY,NZ)
    LOGICAL :: baseline_support(NX,NY,NZ)
    INTEGER :: thermo_surface(NX,NY,NZ),reference_level(NX,NY),status
    REAL(real64) :: requested(NX,NY)

    CALL make_background(background,status)
    CALL make_retained(background,retained,.FALSE.)
    CALL make_retained_omega(retained_omega)
    requested=REAL(background%surface_pressure%value,real64)
    requested(1,1)=100010.0_real64
    requested(2,1)=99999.5_real64
    CALL build_pressure_transition_prior(background,retained,retained_omega, &
      requested,seed,status)
    CALL check(status==STATUS_OK,'pipeline seed fixture builds from immutable input')
    IF (status/=STATUS_OK) RETURN

    thermo_active=.FALSE.; thermo_active(1,1,2)=.TRUE.
    thermo_surface=SATURATION_LIQUID
    geopotential_support=.FALSE.
    geopotential_support(1,1,:)=.TRUE.; geopotential_support(2,1,2:)=.TRUE.
    baseline_support=geopotential_support; baseline_support(1,1,1)=.FALSE.
    reference_level=0
    config%requested_mode=MODE_SHADOW
    config%maximum_outer_iterations=1
    config%balance%minimum_target_response_ratio=0.0_real64

    ! This is the ordinary no-pressure baseline. It proves the first stage
    ! really changes the old bottom thermodynamics and Phi.
    CALL run_cloud_bal_pipeline(background,baseline,baseline_operational, &
      baseline_result,config,thermo_active,thermo_surface,1.0_real64, &
      baseline_support,reference_level)
    IF (baseline_result%status/=STATUS_OK) PRINT '(A,6(I0,1X))', &
      'pipeline baseline status/reason/stages: ',baseline_result%status,baseline_result%reason_code, &
      baseline_result%column%status,baseline_result%column%reason_code, &
      baseline_result%geopotential%status,baseline_result%geopotential%reason_code
    CALL check(baseline_result%status==STATUS_OK .AND. &
      ABS(REAL(baseline%temperature%value(1,1,2),real64)- &
        REAL(background%temperature%value(1,1,2),real64))>1.0e-5_real64 .AND. &
      ABS(REAL(baseline%vapor%value(1,1,2),real64)- &
        REAL(background%vapor%value(1,1,2),real64))>1.0e-8_real64, &
      'pipeline seed baseline performs old-bottom thermo update')

    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
      thermo_active,thermo_surface,1.0_real64,baseline_support, &
      reference_level,requested,seed)
    IF (result%status/=STATUS_OK) PRINT '(A,6(I0,1X))', &
      'pipeline seed status/reason/stages: ',result%status,result%reason_code, &
      result%column%status,result%column%reason_code, &
      result%geopotential%status,result%geopotential%reason_code
    CALL check(result%status==STATUS_OK .AND. ANY(result%overall%changed), &
      'pipeline accepts explicit pressure transition seed')
    IF (ALLOCATED(result%pressure_transition_seed)) THEN
      CALL check(canonical_states_equal(result%pressure_transition_seed,seed), &
        'accepted pipeline stores the canonical transition seed')
    ELSE
      CALL check(.FALSE.,'accepted pipeline stores the canonical transition seed')
    END IF
    CALL check(result%geometry_budget%accounted_cells>0_int64 .AND. &
      result%geometry_budget%geometry_mass_change_kg>0.0_real64, &
      'pipeline geometry budget covers post-column transition')
    CALL check(result%geopotential%coverage%required==5_int64 .AND. &
      result%geopotential%coverage%usable==5_int64 .AND. &
      result%geopotential%coverage%excluded==0_int64, &
      'pipeline geometry coverage includes old support and new center')
    CALL check(canonical_states_equal(background,operational), &
      'seeded pipeline leaves operational input unchanged')
    CALL check(ANY(candidate%above_ground(1,1,:)) .AND. &
      ALL(candidate%above_ground(1,1,:)) .AND. &
      ALL(candidate%above_ground(2,1,:).EQV.background%above_ground(2,1,:)), &
      'seeded pipeline publishes exactly one changed domain column')
    CALL check(ABS(REAL(candidate%surface_pressure%value(2,1),real64)-99999.5_real64)<0.01_real64, &
      'seeded pipeline publishes positive nonactivating PSFC')
    CALL check(COUNT(candidate%above_ground .AND. .NOT.background%above_ground)==1, &
      'seeded pipeline activates one new center only')
    CALL check(ABS(REAL(candidate%omega%value(1,1,1),real64))>0.0_real64, &
      'seeded pipeline carries nonzero new omega')
    IF (ALLOCATED(result%geopotential_support)) THEN
      CALL check(ALL(result%geopotential_support(1,1,:)) .AND. &
        ALL(result%geopotential_support(2,1,2:)) .AND. &
        .NOT.result%geopotential_support(2,1,1), &
        'accepted seed extends stored geometry support to its new center')
    ELSE
      CALL check(.FALSE.,'accepted seed extends stored geometry support to its new center')
    END IF
    CALL check(ABS(REAL(candidate%geopotential%value(1,1,2),real64)- &
      REAL(background%geopotential%value(1,1,2),real64))>1.0e-4_real64, &
      'seeded pipeline retains the thermo Phi correction before transition')
    IF (result%status==STATUS_OK) THEN
      CALL make_retained(background,retained_reverse,.TRUE.)
      CALL check_seed_wps_mapping(candidate,retained,.FALSE.)
      CALL check_seed_wps_mapping(candidate,retained_reverse,.TRUE.)
    END IF

    ! Rebase only the newly exposed seed cell onto the no-pressure pipeline
    ! result, then repeat the transition and no-op balance stages explicitly.
    rebased=baseline
    CALL rebase_seed_cell(rebased,seed)
    CALL apply_pressure_domain_transition(baseline,rebased,manual_transition, &
      transition_result,transition_budget)
    CALL check(transition_result%status==STATUS_OK, &
      'manual post-column seed transition succeeds')
    IF (transition_result%status==STATUS_OK) THEN
      CALL build_compact_balance_beta(manual_transition, &
        config%horizontal_support_radius_m,config%pressure_support_radius_pa,status)
      CALL apply_localized_balance(manual_transition,manual_final,balance_result,config%balance)
      CALL check(balance_result%status==STATUS_OK .AND. &
        same_transition_physics(candidate,manual_final), &
        'pipeline seed result matches explicit post-column rebase/transition')
    END IF

    ! Non-OFF mode requires both the pressure request and geometric support.
    CALL run_cloud_bal_pipeline(background,operational,candidate,missing_result,config, &
      thermo_active,thermo_surface,1.0_real64,geopotential_support,reference_level, &
      pressure_transition_seed=seed)
    CALL check(missing_result%status==STATUS_FAILED .AND. &
      canonical_states_equal(background,operational) .AND. &
      canonical_states_equal(background,candidate), &
      'missing pressure request rolls back seeded pipeline')

    geopotential_support=.FALSE.
    CALL run_cloud_bal_pipeline(background,operational,candidate,support_result,config, &
      thermo_active,thermo_surface,1.0_real64,geopotential_support,reference_level, &
      requested,seed)
    CALL check(support_result%status==STATUS_FAILED .AND. &
      canonical_states_equal(background,operational) .AND. &
      canonical_states_equal(background,candidate), &
      'outside-support seed request rolls back')

    cap_config=config; cap_config%maximum_outer_iterations=2
    geopotential_support=.FALSE.
    geopotential_support(1,1,:)=.TRUE.; geopotential_support(2,1,2:)=.TRUE.
    baseline_support=geopotential_support; baseline_support(1,1,1)=.FALSE.
    CALL run_cloud_bal_pipeline(background,operational,candidate,cap_result,cap_config, &
      thermo_active,thermo_surface,1.0_real64,baseline_support,reference_level, &
      requested,seed)
    CALL check(cap_result%status==STATUS_FAILED .AND. &
      canonical_states_equal(background,operational) .AND. &
      canonical_states_equal(background,candidate), &
      'outer-iteration cap rejects seeded pressure geometry')

    ! A malformed canonical seed must fail at its shape/metadata guard, not
    ! dereference a missing payload or partially publish a candidate.
    invalid_seed=seed
    IF (ALLOCATED(invalid_seed%geopotential%value)) DEALLOCATE(invalid_seed%geopotential%value)
    CALL run_cloud_bal_pipeline(background,operational,candidate,invalid_result,config, &
      thermo_active,thermo_surface,1.0_real64,baseline_support,reference_level, &
      requested,invalid_seed)
    CALL check(invalid_result%status==STATUS_FAILED .AND. &
      canonical_states_equal(background,operational) .AND. &
      canonical_states_equal(background,candidate), &
      'deallocated seed geopotential is rejected with rollback')

    off_config=config; off_config%requested_mode=MODE_OFF; off_config%maximum_outer_iterations=0
    CALL run_cloud_bal_pipeline(background,candidate,operational,off_result,off_config, &
      pressure_transition_seed=seed)
    CALL check(off_result%status==STATUS_OK .AND. &
      canonical_states_equal(background,candidate) .AND. &
      canonical_states_equal(background,operational) .AND. &
      .NOT.ALLOCATED(off_result%pressure_transition_seed), &
      'OFF mode ignores a supplied transition seed')
  END SUBROUTINE test_pipeline_seed

  SUBROUTINE test_pipeline_signed_mixed
    TYPE(cloud_bal_state_type) :: background,seed,candidate,operational
    TYPE(cloud_bal_state_type) :: negative_reference,negative_operational,rebased
    TYPE(cloud_bal_state_type) :: rejected_candidate,rejected_operational
    TYPE(pressure_wps_fields) :: retained
    TYPE(field3d) :: retained_omega
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: result,negative_result,rejected_result
    LOGICAL :: thermo_active(NX,NY,NZ),geopotential_support(NX,NY,NZ)
    LOGICAL :: selected_columns(NX,NY)
    INTEGER :: thermo_surface(NX,NY,NZ),reference_level(NX,NY),status
    REAL(real64) :: seed_request(NX,NY),requested(NX,NY),negative_request(NX,NY)
    REAL(real64) :: remove_request(NX,NY)

    CALL make_background(background,status)
    CALL check(status==STATUS_OK,'signed mixed pipeline background fixture')
    IF (status/=STATUS_OK) RETURN
    CALL make_retained(background,retained,.FALSE.)
    CALL make_retained_omega(retained_omega)
    seed_request=REAL(background%surface_pressure%value,real64)
    seed_request(1,1)=100010.0_real64
    CALL build_pressure_transition_prior(background,retained,retained_omega, &
      seed_request,seed,status)
    CALL check(status==STATUS_OK,'signed mixed pipeline seed changes only crossing column')
    IF (status/=STATUS_OK) RETURN
    CALL check(ALL(seed%above_ground(1,1,:)) .AND. &
      ALL(seed%above_ground(2,1,:).EQV.background%above_ground(2,1,:)) .AND. &
      seed%surface_pressure%value(2,1)==background%surface_pressure%value(2,1), &
      'signed mixed seed leaves other column unchanged')

    thermo_active=.FALSE.; thermo_active(1,1,2)=.TRUE.
    thermo_surface=SATURATION_LIQUID
    geopotential_support=.FALSE.
    geopotential_support(1,1,2:)=.TRUE.
    geopotential_support(2,1,2:)=.TRUE.
    reference_level=0
    config%requested_mode=MODE_SHADOW
    config%maximum_outer_iterations=1
    config%balance%minimum_target_response_ratio=0.0_real64

    requested=REAL(background%surface_pressure%value,real64)
    requested(1,1)=100010.0_real64
    requested(2,1)=99990.0_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
      thermo_active,thermo_surface,1.0_real64,geopotential_support,reference_level, &
      requested,seed)
    IF (result%status/=STATUS_OK) PRINT '(A,4(I0,1X))', &
      'signed mixed pipeline status/reason/stages: ',result%status,result%reason_code, &
      result%column%status,result%geopotential%status
    CALL check(result%status==STATUS_OK,'signed mixed pipeline accepts positive/negative request')
    IF (result%status/=STATUS_OK) RETURN
    CALL check(ABS(REAL(candidate%surface_pressure%value(1,1),real64)-100010.0_real64)<0.01_real64 .AND. &
      ABS(REAL(candidate%surface_pressure%value(2,1),real64)-99990.0_real64)<0.01_real64, &
      'signed mixed pipeline publishes both requested PSFC values')
    CALL check(ALL(candidate%above_ground(1,1,:)) .AND. &
      ALL(candidate%above_ground(2,1,:).EQV.background%above_ground(2,1,:)) .AND. &
      COUNT(candidate%above_ground .AND. .NOT.background%above_ground)==1, &
      'signed mixed pipeline activates only the positive column center')
    CALL check(canonical_states_equal(background,operational), &
      'signed mixed pipeline leaves operational input unchanged')
    CALL check(ABS(REAL(candidate%geopotential%value(2,1,2),real64)- &
      REAL(background%geopotential%value(2,1,2),real64))>1.0e-6_real64, &
      'signed mixed pipeline applies the negative column Phi response')

    negative_request=REAL(background%surface_pressure%value,real64)
    negative_request(2,1)=99990.0_real64
    CALL run_cloud_bal_pipeline(background,negative_reference,negative_operational, &
      negative_result,config,thermo_active,thermo_surface,1.0_real64, &
      geopotential_support,reference_level,negative_request)
    CALL check(negative_result%status==STATUS_OK,'ordinary negative hydrostatic reference succeeds')
    IF (negative_result%status==STATUS_OK) THEN
      CALL check(MAXVAL(ABS(REAL(candidate%geopotential%value(2,1,:),real64)- &
        REAL(negative_reference%geopotential%value(2,1,:),real64)))<1.0e-3_real64, &
        'negative column Phi matches ordinary hydrostatic reference')
    END IF

    selected_columns=.FALSE.; selected_columns(1,1)=.TRUE.
    CALL rebase_pressure_transition_prior(background,seed,rebased,status,selected_columns)
    CALL check(status==STATUS_OK .AND. ALL(rebased%above_ground(1,1,:)) .AND. &
      ALL(rebased%above_ground(2,1,:).EQV.background%above_ground(2,1,:)), &
      'rebase optional selected-columns mask localizes the seed')

    remove_request=REAL(seed%surface_pressure%value,real64)
    remove_request(1,1)=99990.0_real64
    CALL run_cloud_bal_pipeline(seed,rejected_candidate,rejected_operational, &
      rejected_result,config,thermo_active,thermo_surface,1.0_real64, &
      seed%above_ground,reference_level,remove_request,seed)
    CALL check(rejected_result%status==STATUS_FAILED .AND. &
      canonical_states_equal(seed,rejected_candidate) .AND. &
      canonical_states_equal(seed,rejected_operational), &
      'negative request removing a seeded center rolls back')
  END SUBROUTINE test_pipeline_signed_mixed

  SUBROUTINE check_seed_wps_mapping(candidate,background,ascending)
    TYPE(cloud_bal_state_type), INTENT(IN) :: candidate
    TYPE(pressure_wps_fields), INTENT(IN) :: background
    LOGICAL, INTENT(IN) :: ascending
    TYPE(pressure_wps_fields) :: mapped
    INTEGER :: status,l,k
    CHARACTER(LEN=32) :: order_name

    IF (ascending) THEN
      order_name='ascending'
      l=NZ
    ELSE
      order_name='descending'
      l=1
    END IF
    CALL map_pressure_candidate_to_wps(candidate,background,mapped,status,WIND)
    CALL check(status==STATUS_OK,'seeded candidate maps to '//TRIM(order_name)//' WPS')
    IF (status/=STATUS_OK) RETURN

    CALL check(mapped%psfc(1,1)==candidate%surface_pressure%value(1,1) .AND. &
      mapped%psfc(2,1)==candidate%surface_pressure%value(2,1), &
      TRIM(order_name)//' WPS PSFC comes from accepted candidate')
    CALL check(mapped%t(1,1,l)==candidate%temperature%value(1,1,1) .AND. &
      mapped%qv(1,1,l)==candidate%vapor%value(1,1,1) .AND. &
      mapped%qc(1,1,l)==candidate%cloud_water%value(1,1,1) .AND. &
      mapped%qi(1,1,l)==candidate%cloud_ice%value(1,1,1) .AND. &
      mapped%qr(1,1,l)==candidate%rain%value(1,1,1) .AND. &
      mapped%qs(1,1,l)==candidate%snow%value(1,1,1) .AND. &
      mapped%qg(1,1,l)==candidate%graupel%value(1,1,1), &
      TRIM(order_name)//' WPS new cell T/Q/5 species')
    CALL check(mapped%u(1,1,l)==candidate%u%value(1,1,1) .AND. &
      mapped%v(1,1,l)==candidate%v%value(1,1,1) .AND. &
      mapped%ht(1,1,l)==REAL(REAL(candidate%geopotential%value(1,1,1),real64)/G,real32), &
      TRIM(order_name)//' WPS new cell wind and Phi-to-HGT')

    ! Canonical surface T/Q/height are mapped as well as pressure-level fields.
    ! Unrelated retained slabs stay exact; unchanged active columns must map
    ! consistently with their canonical candidate values.
    CALL check(ALL(mapped%rh==background%rh) .AND. ALL(mapped%slp==background%slp) .AND. &
      ALL(mapped%skin_temperature==background%skin_temperature) .AND. &
      ALL(mapped%snow_cover==background%snow_cover) .AND. &
      ALL(mapped%u(:,:,NZ+1)==background%u(:,:,NZ+1)) .AND. &
      ALL(mapped%v(:,:,NZ+1)==background%v(:,:,NZ+1)), &
      TRIM(order_name)//' retained unrelated surface slabs')
    DO k=1,NZ
      IF (.NOT.candidate%above_ground(2,1,k)) CYCLE
      IF (ascending) THEN
        l=NZ+1-k
      ELSE
        l=k
      END IF
      CALL check(mapped%t(2,1,l)==candidate%temperature%value(2,1,k) .AND. &
        mapped%qv(2,1,l)==candidate%vapor%value(2,1,k) .AND. &
        mapped%u(2,1,l)==candidate%u%value(2,1,k) .AND. &
        mapped%v(2,1,l)==candidate%v%value(2,1,k), &
        TRIM(order_name)//' untouched column remains candidate-consistent')
    END DO
  END SUBROUTINE check_seed_wps_mapping

  SUBROUTINE rebase_seed_cell(target,seed)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: target
    TYPE(cloud_bal_state_type), INTENT(IN) :: seed
    INTEGER, PARAMETER :: I=1,J=1,K=1
    target%above_ground(I,J,:)=seed%above_ground(I,J,:)
    target%grid%pressure_interface(I,J,:)=seed%grid%pressure_interface(I,J,:)
    target%grid%cell_dp(I,J,:)=seed%grid%cell_dp(I,J,:)
    target%grid%level_spacing_dp(I,J,:)=seed%grid%level_spacing_dp(I,J,:)
    target%grid%pressure_mass_measure(I,J,:)=seed%grid%pressure_mass_measure(I,J,:)
    target%grid%dry_air_mass_measure(I,J,:)=seed%grid%dry_air_mass_measure(I,J,:)
    target%surface_pressure%value(I,J)=seed%surface_pressure%value(I,J)
    target%surface_pressure%valid(I,J)=seed%surface_pressure%valid(I,J)
    target%surface_pressure%quality(I,J)=seed%surface_pressure%quality(I,J)
    target%surface_pressure%source(I,J)=seed%surface_pressure%source(I,J)
    ! The mixed pipeline request also changes PSFC in (2,1) without exposing
    ! a center. Rebase its geometry and surface pressure, but no payload.
    target%above_ground(2,1,:)=seed%above_ground(2,1,:)
    target%grid%pressure_interface(2,1,:)=seed%grid%pressure_interface(2,1,:)
    target%grid%cell_dp(2,1,:)=seed%grid%cell_dp(2,1,:)
    target%grid%level_spacing_dp(2,1,:)=seed%grid%level_spacing_dp(2,1,:)
    target%grid%pressure_mass_measure(2,1,:)=seed%grid%pressure_mass_measure(2,1,:)
    target%grid%dry_air_mass_measure(2,1,:)=seed%grid%dry_air_mass_measure(2,1,:)
    target%surface_pressure%value(2,1)=seed%surface_pressure%value(2,1)
    target%surface_pressure%valid(2,1)=seed%surface_pressure%valid(2,1)
    target%surface_pressure%quality(2,1)=seed%surface_pressure%quality(2,1)
    target%surface_pressure%source(2,1)=seed%surface_pressure%source(2,1)
    target%pressure%valid(I,J,K)=seed%pressure%valid(I,J,K)
    target%pressure%quality(I,J,K)=seed%pressure%quality(I,J,K)
    target%pressure%source(I,J,K)=seed%pressure%source(I,J,K)
    target%temperature%value(I,J,K)=seed%temperature%value(I,J,K)
    target%temperature%valid(I,J,K)=seed%temperature%valid(I,J,K)
    target%temperature%quality(I,J,K)=seed%temperature%quality(I,J,K)
    target%temperature%source(I,J,K)=seed%temperature%source(I,J,K)
    target%vapor%value(I,J,K)=seed%vapor%value(I,J,K)
    target%vapor%valid(I,J,K)=seed%vapor%valid(I,J,K)
    target%vapor%quality(I,J,K)=seed%vapor%quality(I,J,K)
    target%vapor%source(I,J,K)=seed%vapor%source(I,J,K)
    target%u%value(I,J,K)=seed%u%value(I,J,K); target%u%valid(I,J,K)=seed%u%valid(I,J,K)
    target%u%quality(I,J,K)=seed%u%quality(I,J,K); target%u%source(I,J,K)=seed%u%source(I,J,K)
    target%v%value(I,J,K)=seed%v%value(I,J,K); target%v%valid(I,J,K)=seed%v%valid(I,J,K)
    target%v%quality(I,J,K)=seed%v%quality(I,J,K); target%v%source(I,J,K)=seed%v%source(I,J,K)
    target%omega%value(I,J,K)=seed%omega%value(I,J,K); target%omega%valid(I,J,K)=seed%omega%valid(I,J,K)
    target%omega%quality(I,J,K)=seed%omega%quality(I,J,K); target%omega%source(I,J,K)=seed%omega%source(I,J,K)
    target%geopotential%value(I,J,K)=seed%geopotential%value(I,J,K)
    target%geopotential%valid(I,J,K)=seed%geopotential%valid(I,J,K)
    target%geopotential%quality(I,J,K)=seed%geopotential%quality(I,J,K)
    target%geopotential%source(I,J,K)=seed%geopotential%source(I,J,K)
    target%cloud_water%value(I,J,K)=seed%cloud_water%value(I,J,K)
    target%cloud_water%valid(I,J,K)=seed%cloud_water%valid(I,J,K)
    target%cloud_water%quality(I,J,K)=seed%cloud_water%quality(I,J,K)
    target%cloud_water%source(I,J,K)=seed%cloud_water%source(I,J,K)
    target%cloud_ice%value(I,J,K)=seed%cloud_ice%value(I,J,K)
    target%cloud_ice%valid(I,J,K)=seed%cloud_ice%valid(I,J,K)
    target%cloud_ice%quality(I,J,K)=seed%cloud_ice%quality(I,J,K)
    target%cloud_ice%source(I,J,K)=seed%cloud_ice%source(I,J,K)
    target%rain%value(I,J,K)=seed%rain%value(I,J,K)
    target%rain%valid(I,J,K)=seed%rain%valid(I,J,K)
    target%rain%quality(I,J,K)=seed%rain%quality(I,J,K)
    target%rain%source(I,J,K)=seed%rain%source(I,J,K)
    target%snow%value(I,J,K)=seed%snow%value(I,J,K)
    target%snow%valid(I,J,K)=seed%snow%valid(I,J,K)
    target%snow%quality(I,J,K)=seed%snow%quality(I,J,K)
    target%snow%source(I,J,K)=seed%snow%source(I,J,K)
    target%graupel%value(I,J,K)=seed%graupel%value(I,J,K)
    target%graupel%valid(I,J,K)=seed%graupel%valid(I,J,K)
    target%graupel%quality(I,J,K)=seed%graupel%quality(I,J,K)
    target%graupel%source(I,J,K)=seed%graupel%source(I,J,K)
    target%obs_support(I,J,K)=seed%obs_support(I,J,K)
    target%hydro_support(I,J,K)=seed%hydro_support(I,J,K)
    target%balance_beta(I,J,K)=seed%balance_beta(I,J,K)
    target%omega_target%valid(I,J,K)=seed%omega_target%valid(I,J,K)
    target%omega_target%quality(I,J,K)=seed%omega_target%quality(I,J,K)
    target%omega_target%source(I,J,K)=seed%omega_target%source(I,J,K)
    target%omega_target_sigma%valid(I,J,K)=seed%omega_target_sigma%valid(I,J,K)
    target%omega_target_sigma%quality(I,J,K)=seed%omega_target_sigma%quality(I,J,K)
    target%omega_target_sigma%source(I,J,K)=seed%omega_target_sigma%source(I,J,K)
  END SUBROUTINE rebase_seed_cell

  LOGICAL FUNCTION same_transition_physics(left,right)
    TYPE(cloud_bal_state_type), INTENT(IN) :: left,right
    same_transition_physics= &
      ALL(left%pressure%value==right%pressure%value) .AND. &
      ALL(left%surface_pressure%value==right%surface_pressure%value) .AND. &
      ALL(left%temperature%value==right%temperature%value) .AND. &
      ALL(left%vapor%value==right%vapor%value) .AND. &
      ALL(left%u%value==right%u%value) .AND. ALL(left%v%value==right%v%value) .AND. &
      ALL(left%omega%value==right%omega%value) .AND. &
      ALL(left%geopotential%value==right%geopotential%value) .AND. &
      ALL(left%cloud_water%value==right%cloud_water%value) .AND. &
      ALL(left%cloud_ice%value==right%cloud_ice%value) .AND. &
      ALL(left%rain%value==right%rain%value) .AND. ALL(left%snow%value==right%snow%value) .AND. &
      ALL(left%graupel%value==right%graupel%value) .AND. &
      ALL(left%above_ground.EQV.right%above_ground)
  END FUNCTION same_transition_physics

  SUBROUTINE set_mixed_authority(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    state%omega_target%value=0.0_real32; state%omega_target%valid=.FALSE.
    state%omega_target%quality=QUALITY_RAW_MISSING; state%omega_target%source=0_int32
    state%omega_target_sigma%value=0.0_real32; state%omega_target_sigma%valid=.FALSE.
    state%omega_target_sigma%quality=QUALITY_RAW_MISSING
    state%omega_target_sigma%source=0_int32
    state%omega_target%value(2,1,2)=0.5_real32
    state%omega_target%valid(2,1,2)=.TRUE.; state%omega_target%quality(2,1,2)=0_int32
    state%omega_target%source(2,1,2)=IOR(SOURCE_DYNAMIC_TARGET,SOURCE_ANALYZED_WIND)
    state%omega_target_sigma%value(2,1,2)=1.0_real32
    state%omega_target_sigma%valid(2,1,2)=.TRUE.
    state%omega_target_sigma%quality(2,1,2)=0_int32
    state%omega_target_sigma%source(2,1,2)=SOURCE_ANALYZED_WIND
    state%obs_support(2,1,2)=1_int32
    state%hydro_support(2,1,2)=1_int32
    state%balance_beta(2,1,2)=0.25_real32
  END SUBROUTINE set_mixed_authority

  LOGICAL FUNCTION old_authority_unchanged(background,candidate,i,j)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    INTEGER, INTENT(IN) :: i,j
    old_authority_unchanged= &
      ALL(candidate%omega_target%value(i,j,2:)==background%omega_target%value(i,j,2:)) .AND. &
      ALL(candidate%omega_target%valid(i,j,2:).EQV.background%omega_target%valid(i,j,2:)) .AND. &
      ALL(candidate%omega_target%quality(i,j,2:)==background%omega_target%quality(i,j,2:)) .AND. &
      ALL(candidate%omega_target%source(i,j,2:)==background%omega_target%source(i,j,2:)) .AND. &
      ALL(candidate%omega_target_sigma%value(i,j,2:)==background%omega_target_sigma%value(i,j,2:)) .AND. &
      ALL(candidate%omega_target_sigma%valid(i,j,2:).EQV. &
        background%omega_target_sigma%valid(i,j,2:)) .AND. &
      ALL(candidate%omega_target_sigma%quality(i,j,2:)== &
        background%omega_target_sigma%quality(i,j,2:)) .AND. &
      ALL(candidate%omega_target_sigma%source(i,j,2:)== &
        background%omega_target_sigma%source(i,j,2:)) .AND. &
      ALL(candidate%obs_support(i,j,2:)==background%obs_support(i,j,2:)) .AND. &
      ALL(candidate%hydro_support(i,j,2:)==background%hydro_support(i,j,2:)) .AND. &
      ALL(candidate%balance_beta(i,j,2:)==background%balance_beta(i,j,2:))
  END FUNCTION old_authority_unchanged

  SUBROUTINE expect_reject(background,retained,retained_omega,requested,label)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background
    TYPE(pressure_wps_fields), INTENT(IN) :: retained
    TYPE(field3d), INTENT(IN) :: retained_omega
    REAL(real64), INTENT(IN) :: requested(:,:)
    CHARACTER(LEN=*), INTENT(IN) :: label
    TYPE(cloud_bal_state_type) :: prior
    INTEGER :: status
    CALL build_pressure_transition_prior(background,retained,retained_omega,requested,prior,status)
    CALL check(status==STATUS_FAILED,TRIM(label)//' is rejected')
    CALL check(canonical_states_equal(prior,background),TRIM(label)//' rolls back prior output')
  END SUBROUTINE expect_reject

  SUBROUTINE make_background(state,status)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, INTENT(OUT) :: status
    INTEGER :: k
    CALL initialize_cloud_bal_state(state,NX,NY,NZ,VALID_TIME,GRID_ID,status)
    IF (status/=STATUS_OK) RETURN
    state%grid%dx=2000.0_real64; state%grid%dy=2200.0_real64
    DO k=1,NZ
      state%pressure%value(:,:,k)=REAL(PRESSURE(k),real32)
      state%temperature%value(:,:,k)=280.0_real32+REAL(k,real32)
      state%geopotential%value(:,:,k)=REAL(G*REAL(100.0_real64+50.0_real64*REAL(k,real64),real64),real32)
      state%vapor%value(:,:,k)=0.008_real32+0.001_real32*REAL(k,real32)
      state%u%value(:,:,k)=2.0_real32+REAL(k,real32)
      state%v%value(:,:,k)=-1.0_real32-REAL(k,real32)
      state%omega%value(:,:,k)=-1.0_real32+0.5_real32*REAL(k,real32)
      state%cloud_water%value(:,:,k)=0.0002_real32
      state%cloud_ice%value(:,:,k)=0.0003_real32
      state%rain%value(:,:,k)=0.0004_real32
      state%snow%value(:,:,k)=0.0005_real32
      state%graupel%value(:,:,k)=0.0006_real32
    END DO
    CALL mark3(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%u,SOURCE_BACKGROUND_MODEL); CALL mark3(state%v,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%cloud_water,SOURCE_BACKGROUND_MODEL); CALL mark3(state%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%rain,SOURCE_BACKGROUND_MODEL); CALL mark3(state%snow,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%graupel,SOURCE_BACKGROUND_MODEL)
    state%surface_pressure%value=99999.125_real32
    state%surface_temperature%value=290.0_real32
    state%surface_vapor%value=0.006_real32
    state%surface_height%value=100.0_real32
    CALL mark2(state%surface_pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark2(state%surface_temperature,SOURCE_BACKGROUND_MODEL)
    CALL mark2(state%surface_vapor,SOURCE_BACKGROUND_MODEL)
    CALL mark2(state%surface_height,SOURCE_BACKGROUND_MODEL)
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) RETURN
    CALL mask_to_domain(state)
    CALL refresh_dry_air_mass_measure(state,status)
  END SUBROUTINE make_background

  SUBROUTINE make_retained(background,retained,ascending)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background
    TYPE(pressure_wps_fields), INTENT(OUT) :: retained
    LOGICAL, INTENT(IN) :: ascending
    INTEGER :: k,l
    ALLOCATE(retained%p(NZ+1),retained%t(NX,NY,NZ+1),retained%ht(NX,NY,NZ+1), &
      retained%u(NX,NY,NZ+1),retained%v(NX,NY,NZ+1),retained%rh(NX,NY,NZ+1), &
      retained%qv(NX,NY,NZ+1),retained%qc(NX,NY,NZ),retained%qi(NX,NY,NZ), &
      retained%qr(NX,NY,NZ),retained%qs(NX,NY,NZ),retained%qg(NX,NY,NZ), &
      retained%psfc(NX,NY),retained%slp(NX,NY),retained%skin_temperature(NX,NY), &
      retained%snow_cover(NX,NY))
    IF (ascending) THEN
      retained%p=[900.0_real32,950.0_real32,1000.0_real32,2001.0_real32]
    ELSE
      retained%p=[1000.0_real32,950.0_real32,900.0_real32,2001.0_real32]
    END IF
    DO k=1,NZ
      l=k; IF (ascending) l=NZ+1-k
      retained%t(:,:,l)=300.0_real32+10.0_real32*REAL(k,real32)
      retained%ht(:,:,l)=100.0_real32+20.0_real32*REAL(k,real32)
      retained%u(:,:,l)=9.0_real32+REAL(k,real32)
      retained%v(:,:,l)=-5.0_real32-REAL(k,real32)
      retained%qv(:,:,l)=0.010_real32+0.001_real32*REAL(k,real32)
      retained%qc(:,:,l)=0.0010_real32
      retained%qi(:,:,l)=0.0005_real32
      retained%qr(:,:,l)=0.0002_real32
      retained%qs(:,:,l)=0.0001_real32
      retained%qg(:,:,l)=0.00005_real32
    END DO
    ! The newly exposed canonical 100000-Pa center has a distinct complete
    ! WPS payload, proving the builder reads that level and not old state.
    l=1; IF (ascending) l=NZ
    retained%t(1,1,l)=315.0_real32; retained%ht(1,1,l)=150.0_real32
    retained%u(1,1,l)=11.0_real32; retained%v(1,1,l)=-7.0_real32
    retained%qv(1,1,l)=0.012_real32; retained%qc(1,1,l)=0.0010_real32
    retained%qi(1,1,l)=0.0005_real32; retained%qr(1,1,l)=0.0002_real32
    retained%qs(1,1,l)=0.0001_real32; retained%qg(1,1,l)=0.00005_real32
    retained%t(:,:,NZ+1)=333.0_real32; retained%ht(:,:,NZ+1)=999.0_real32
    retained%u(:,:,NZ+1)=30.0_real32; retained%v(:,:,NZ+1)=-30.0_real32
    retained%rh=50.0_real32; retained%qv(:,:,NZ+1)=0.090_real32
    retained%psfc=background%surface_pressure%value; retained%slp=101000.0_real32
    retained%skin_temperature=291.0_real32; retained%snow_cover=0.1_real32
    retained%valid_time=VALID_TIME; retained%grid_id=GRID_ID; retained%wind_coordinate=WIND
  END SUBROUTINE make_retained

  SUBROUTINE make_retained_omega(omega)
    TYPE(field3d), INTENT(OUT) :: omega
    CALL initialize_field(omega,NX,NY,NZ,VALID_TIME,'Pa s-1')
    omega%value=-3.0_real32; omega%valid=.TRUE.; omega%quality=0_int32
    omega%source=SOURCE_ANALYZED_WIND; omega%value(1,1,1)=4.25_real32
  END SUBROUTINE make_retained_omega

  SUBROUTINE mark3(field,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE mark3

  SUBROUTINE mark2(field,source)
    TYPE(field2d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE mark2

  SUBROUTINE mask_to_domain(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    state%temperature%valid=state%above_ground; state%geopotential%valid=state%above_ground
    state%vapor%valid=state%above_ground; state%u%valid=state%above_ground
    state%v%valid=state%above_ground; state%omega%valid=state%above_ground
    state%cloud_water%valid=state%above_ground; state%cloud_ice%valid=state%above_ground
    state%rain%valid=state%above_ground; state%snow%valid=state%above_ground
    state%graupel%valid=state%above_ground
    WHERE (.NOT.state%above_ground)
      state%temperature%quality=QUALITY_RAW_MISSING; state%temperature%source=0_int32
      state%geopotential%quality=QUALITY_RAW_MISSING; state%geopotential%source=0_int32
      state%vapor%quality=QUALITY_RAW_MISSING; state%vapor%source=0_int32
      state%u%quality=QUALITY_RAW_MISSING; state%u%source=0_int32
      state%v%quality=QUALITY_RAW_MISSING; state%v%source=0_int32
      state%omega%quality=QUALITY_RAW_MISSING; state%omega%source=0_int32
      state%cloud_water%quality=QUALITY_RAW_MISSING; state%cloud_water%source=0_int32
      state%cloud_ice%quality=QUALITY_RAW_MISSING; state%cloud_ice%source=0_int32
      state%rain%quality=QUALITY_RAW_MISSING; state%rain%source=0_int32
      state%snow%quality=QUALITY_RAW_MISSING; state%snow%source=0_int32
      state%graupel%quality=QUALITY_RAW_MISSING; state%graupel%source=0_int32
    END WHERE
    WHERE (.NOT.state%above_ground)
      state%pressure%valid=.FALSE.; state%pressure%quality=QUALITY_RAW_MISSING
      state%pressure%source=0_int32
    END WHERE
  END SUBROUTINE mask_to_domain

  LOGICAL FUNCTION new_reconstruction_metadata(state,i,j,k)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j,k
    INTEGER(int32) :: expected
    expected=IOR(SOURCE_OUTPUT_ADAPTER,SOURCE_COLUMN_PHYSICS)
    new_reconstruction_metadata= &
      IAND(state%temperature%quality(i,j,k),QUALITY_LEGACY_PROVENANCE)/=0_int32 .AND. &
      IAND(state%temperature%quality(i,j,k),QUALITY_BELOW_GROUND_FILLED)/=0_int32 .AND. &
      state%temperature%source(i,j,k)==expected .AND. &
      IAND(state%vapor%quality(i,j,k),QUALITY_LEGACY_PROVENANCE)/=0_int32 .AND. &
      IAND(state%vapor%quality(i,j,k),QUALITY_BELOW_GROUND_FILLED)/=0_int32 .AND. &
      state%vapor%source(i,j,k)==expected .AND. &
      IAND(state%u%quality(i,j,k),QUALITY_LEGACY_PROVENANCE)/=0_int32 .AND. &
      IAND(state%u%quality(i,j,k),QUALITY_BELOW_GROUND_FILLED)/=0_int32 .AND. &
      state%u%source(i,j,k)==expected .AND. &
      IAND(state%v%quality(i,j,k),QUALITY_LEGACY_PROVENANCE)/=0_int32 .AND. &
      IAND(state%v%quality(i,j,k),QUALITY_BELOW_GROUND_FILLED)/=0_int32 .AND. &
      state%v%source(i,j,k)==expected .AND. &
      IAND(state%geopotential%quality(i,j,k),QUALITY_LEGACY_PROVENANCE)/=0_int32 .AND. &
      IAND(state%geopotential%quality(i,j,k),QUALITY_BELOW_GROUND_FILLED)/=0_int32 .AND. &
      state%geopotential%source(i,j,k)==expected
  END FUNCTION new_reconstruction_metadata

  LOGICAL FUNCTION old_active_unchanged(background,prior,i,j)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,prior
    INTEGER, INTENT(IN) :: i,j
    old_active_unchanged= &
      ALL(prior%temperature%value(i,j,2:)==background%temperature%value(i,j,2:)) .AND. &
      ALL(prior%vapor%value(i,j,2:)==background%vapor%value(i,j,2:)) .AND. &
      ALL(prior%u%value(i,j,2:)==background%u%value(i,j,2:)) .AND. &
      ALL(prior%v%value(i,j,2:)==background%v%value(i,j,2:)) .AND. &
      ALL(prior%omega%value(i,j,2:)==background%omega%value(i,j,2:)) .AND. &
      ALL(prior%geopotential%value(i,j,2:)==background%geopotential%value(i,j,2:)) .AND. &
      ALL(prior%temperature%valid(i,j,2:).EQV.background%temperature%valid(i,j,2:)) .AND. &
      ALL(prior%temperature%source(i,j,2:)==background%temperature%source(i,j,2:)) .AND. &
      ALL(prior%pressure%valid(i,j,2:).EQV.background%pressure%valid(i,j,2:)) .AND. &
      ALL(prior%pressure%source(i,j,2:)==background%pressure%source(i,j,2:))
  END FUNCTION old_active_unchanged

  LOGICAL FUNCTION untouched_column_unchanged(background,prior)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,prior
    untouched_column_unchanged= &
      ALL(prior%temperature%value(2,1,:)==background%temperature%value(2,1,:)) .AND. &
      ALL(prior%vapor%value(2,1,:)==background%vapor%value(2,1,:)) .AND. &
      ALL(prior%u%value(2,1,:)==background%u%value(2,1,:)) .AND. &
      ALL(prior%v%value(2,1,:)==background%v%value(2,1,:)) .AND. &
      ALL(prior%omega%value(2,1,:)==background%omega%value(2,1,:)) .AND. &
      ALL(prior%geopotential%value(2,1,:)==background%geopotential%value(2,1,:)) .AND. &
      ALL(prior%above_ground(2,1,:).EQV.background%above_ground(2,1,:)) .AND. &
      ALL(prior%grid%pressure_interface(2,1,:)==background%grid%pressure_interface(2,1,:)) .AND. &
      ALL(prior%grid%dry_air_mass_measure(2,1,:)==background%grid%dry_air_mass_measure(2,1,:)) .AND. &
      prior%surface_pressure%value(2,1)==background%surface_pressure%value(2,1)
  END FUNCTION untouched_column_unchanged

END PROGRAM test_pressure_transition_prior
