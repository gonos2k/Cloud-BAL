PROGRAM test_pressure_hydrostatic_state
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state, ONLY: cloud_bal_state_type,stage_result, &
    STATUS_OK,STATUS_FAILED,QUALITY_RAW_MISSING,SOURCE_BACKGROUND_MODEL, &
    SOURCE_CLOUD_ANALYSIS,SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS, &
    SOURCE_DYNAMIC_TARGET,initialize_cloud_bal_state,configure_pressure_geometry, &
    refresh_dry_air_mass_measure,validate_canonical_state,canonical_states_equal
  USE cloud_bal_column_physics, ONLY: water_phase_budget,pressure_analysis_budget, &
    apply_pressure_phase_transfer,apply_pressure_hydrostatic_increment
  IMPLICIT NONE

  INTEGER, PARAMETER :: NX=2,NY=1,NZ=3
  INTEGER(int64), PARAMETER :: VALID_TIME=1788224400_int64
  REAL(real64), PARAMETER :: RD_AIR=287.05_real64,EPSILON_WATER=0.622_real64
  REAL(real64), PARAMETER :: PRESSURE_LEVELS(NZ)=[95000.0_real64,80000.0_real64,65000.0_real64]
  INTEGER :: failures

  failures=0
  CALL test_heating_phase_chain
  CALL test_support_outside_identity
  CALL test_boundary_anchor
  CALL test_surface_anchor_nonzero
  CALL test_surface_anchor_missing_boundary
  CALL test_surface_anchor_terrain_changed
  CALL test_positive_anchor_legacy_unchanged
  CALL test_surface_pressure_geometry_transaction
  CALL test_surface_pressure_preserves_rounded_geometry
  CALL test_surface_pressure_missing_pair
  CALL test_surface_pressure_outside_support
  CALL test_surface_pressure_crossing_level
  CALL test_surface_anchor_below_terrain
  CALL test_empty_support
  CALL test_missing_field
  CALL test_nan_field
  CALL test_pressure_mismatch
  CALL test_metadata_mismatch
  CALL test_support_truncation
  CALL test_repeat_rejected

  IF (failures/=0) THEN
    PRINT *,'Pressure hydrostatic-state tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Pressure hydrostatic-state tests passed'

CONTAINS

  SUBROUTINE check(ok,message)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF (.NOT.ok) THEN
      failures=failures+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE test_heating_phase_chain
    TYPE(cloud_bal_state_type) :: background,proposal,candidate
    TYPE(stage_result) :: phase_result,result
    TYPE(water_phase_budget) :: phase_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY),i,j,k
    REAL(real32) :: expected
    REAL(real64) :: expected_sum,stored_sum

    CALL make_state(background)
    support=.TRUE.; reference_level=1
    CALL make_phase_proposal(background,proposal,support,phase_result,phase_budget)
    CALL check(phase_result%status==STATUS_OK,'phase chain fixture is accepted')
    candidate=background
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_OK,'heating/phase proposal is hydrostatic-valid')
    CALL check(ANY(result%changed),'positive phase change produces a geopotential change')
    CALL check_only_phi(proposal,candidate,'hydrostatic stage changes only Phi')
    expected_sum=0.0_real64; stored_sum=0.0_real64
    DO j=1,NY; DO i=1,NX
      DO k=1,NZ
        expected=expected_phi(background,proposal,i,j,k)
        CALL check(real32_bits(candidate%geopotential%value(i,j,k))==real32_bits(expected), &
          'stored Phi equals float32 hydrostatic result')
        expected_sum=expected_sum+REAL(expected,real64)
        stored_sum=stored_sum+REAL(candidate%geopotential%value(i,j,k),real64)
        CALL check(result%changed(i,j,k) .EQV. &
          (real32_bits(candidate%geopotential%value(i,j,k))/= &
           real32_bits(proposal%geopotential%value(i,j,k))), &
          'changed mask is exactly the stored Phi-difference mask')
        IF (k==1) CALL check(real32_bits(candidate%geopotential%value(i,j,k))== &
          real32_bits(proposal%geopotential%value(i,j,k)),'lowest center is fixed anchor')
        IF (k>1) CALL check(candidate%geopotential%value(i,j,k)> &
          proposal%geopotential%value(i,j,k),'phase heating raises upper Phi')
      END DO
    END DO; END DO
    CALL check(stored_sum==expected_sum,'stored Phi sum matches float32 expected sum')
    CALL check_phi_sources(proposal,candidate,result%changed,'only changed Phi gets column source')
  END SUBROUTINE test_heating_phase_chain

  SUBROUTINE test_support_outside_identity
    TYPE(cloud_bal_state_type) :: background,proposal,candidate
    TYPE(stage_result) :: phase_result,result
    TYPE(water_phase_budget) :: phase_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)

    CALL make_state(background)
    support=.FALSE.; support(1,1,:)=.TRUE.; reference_level=1
    CALL make_phase_proposal(background,proposal,support,phase_result,phase_budget)
    CALL check(phase_result%status==STATUS_OK,'selected-column phase fixture is accepted')
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_OK,'selected column succeeds with untouched column')
    CALL check(result%changed(1,1,2) .AND. .NOT.result%changed(2,1,2), &
      'changed mask excludes the unselected column')
    CALL check_state_except_phi(proposal,candidate,'unselected column state is identical')
    CALL check(ALL(real32_bits(candidate%geopotential%value(2,1,:))== &
      real32_bits(proposal%geopotential%value(2,1,:))),'unselected column Phi is identical')
  END SUBROUTINE test_support_outside_identity

  SUBROUTINE test_boundary_anchor
    TYPE(cloud_bal_state_type) :: background,proposal,candidate
    TYPE(stage_result) :: phase_result,result
    TYPE(water_phase_budget) :: phase_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)

    CALL make_state(background)
    support=.TRUE.; reference_level=1
    CALL make_phase_proposal(background,proposal,support,phase_result,phase_budget)
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_OK,'explicit boundary anchor is accepted')
    CALL check(.NOT.ANY(result%changed(:,:,1)),'lowest represented centers never change')
    CALL check(ALL(candidate%geopotential%value(:,:,1)==proposal%geopotential%value(:,:,1)), &
      'baseline lowest center remains bitwise fixed')

    reference_level=2
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'wrong boundary anchor is rejected')
    CALL check(canonical_states_equal(candidate,proposal),'wrong anchor rolls back proposal')
  END SUBROUTINE test_boundary_anchor

  SUBROUTINE test_surface_anchor_nonzero
    TYPE(cloud_bal_state_type) :: background,proposal,candidate
    TYPE(stage_result) :: phase_result,result
    TYPE(water_phase_budget) :: phase_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)
    REAL(real64) :: center_before,center_after,surface_before,surface_after
    REAL(real64) :: surface_delta,expected_bottom
    REAL(real64) :: water_before(6),water_after(6),surface_water(6)

    CALL make_state(background)
    CALL set_surface_boundary(background,0.006_real32,290.0_real32,0.0_real32)
    support=.TRUE.; reference_level=0
    CALL make_phase_proposal(background,proposal,support,phase_result,phase_budget)
    proposal%surface_temperature%value=300.0_real32
    proposal%surface_vapor%value=0.010_real32
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_OK,'surface anchor accepts complete boundary state')
    CALL check(result%changed(1,1,1),'surface anchor changes the lowest center')
    CALL check(candidate%geopotential%value(1,1,1)/=proposal%geopotential%value(1,1,1), &
      'surface anchor distinguishes new nonzero lowest increment from old zero anchor')

    water_before=species(background,1,1,1)
    water_after=species(proposal,1,1,1)
    surface_water=0.0_real64
    surface_water(1)=REAL(background%surface_vapor%value(1,1),real64)
    surface_before=air_volume_factor(REAL(background%surface_temperature%value(1,1),real64), &
      surface_water)
    surface_water=0.0_real64
    surface_water(1)=REAL(proposal%surface_vapor%value(1,1),real64)
    surface_after=air_volume_factor(REAL(proposal%surface_temperature%value(1,1),real64), &
      surface_water)
    center_before=air_volume_factor(REAL(background%temperature%value(1,1,1),real64),water_before)
    center_after=air_volume_factor(REAL(proposal%temperature%value(1,1,1),real64),water_after)
    surface_delta=0.5_real64*(surface_after+center_after)* &
      LOG(REAL(proposal%surface_pressure%value(1,1),real64)/ &
          REAL(proposal%pressure%value(1,1,1),real64))- &
      0.5_real64*(surface_before+center_before)* &
      LOG(REAL(background%surface_pressure%value(1,1),real64)/ &
          REAL(background%pressure%value(1,1,1),real64))
    expected_bottom=REAL(proposal%geopotential%value(1,1,1),real64)+surface_delta
    CALL check(real32_bits(candidate%geopotential%value(1,1,1))== &
      real32_bits(REAL(expected_bottom,real32)), &
      'surface anchor lowest center matches analytic boundary trapezoid')
  END SUBROUTINE test_surface_anchor_nonzero

  SUBROUTINE test_surface_anchor_missing_boundary
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: phase_result,result
    TYPE(water_phase_budget) :: phase_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)

    CALL make_state(background)
    CALL set_surface_boundary(background,0.006_real32,290.0_real32,0.0_real32)
    support=.TRUE.; reference_level=0
    CALL make_phase_proposal(background,proposal,support,phase_result,phase_budget)
    proposal%surface_vapor%valid(1,1)=.FALSE.
    proposal%surface_vapor%quality(1,1)=QUALITY_RAW_MISSING
    proposal%surface_vapor%source(1,1)=0_int32
    before=proposal
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'missing surface boundary rejects surface anchor')
    CALL check(canonical_states_equal(candidate,before),'missing surface boundary rolls back')
  END SUBROUTINE test_surface_anchor_missing_boundary

  SUBROUTINE test_surface_anchor_terrain_changed
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: phase_result,result
    TYPE(water_phase_budget) :: phase_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)

    CALL make_state(background)
    CALL set_surface_boundary(background,0.006_real32,290.0_real32,0.0_real32)
    support=.TRUE.; reference_level=0
    CALL make_phase_proposal(background,proposal,support,phase_result,phase_budget)
    proposal%surface_height%value=1.0_real32
    before=proposal
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'changed terrain rejects surface anchor')
    CALL check(canonical_states_equal(candidate,before),'changed terrain rolls back')
  END SUBROUTINE test_surface_anchor_terrain_changed

  SUBROUTINE test_positive_anchor_legacy_unchanged
    TYPE(cloud_bal_state_type) :: background,proposal,candidate
    TYPE(stage_result) :: phase_result,result
    TYPE(water_phase_budget) :: phase_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)

    CALL make_state(background)
    CALL set_surface_boundary(background,0.006_real32,290.0_real32,0.0_real32)
    support=.TRUE.; reference_level=1
    CALL make_phase_proposal(background,proposal,support,phase_result,phase_budget)
    proposal%surface_temperature%value=300.0_real32
    proposal%surface_vapor%value=0.010_real32
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_OK,'positive reference retains legacy anchor')
    CALL check(ALL(candidate%geopotential%value(:,:,1)==proposal%geopotential%value(:,:,1)), &
      'positive reference keeps lowest center exactly unchanged')
  END SUBROUTINE test_positive_anchor_legacy_unchanged

  SUBROUTINE test_surface_pressure_geometry_transaction
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,expected
    TYPE(cloud_bal_state_type) :: background_before,proposal_before
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY),status
    REAL(real64) :: requested_surface_pressure(NX,NY)
    REAL(real64) :: expected_surface_delta,expected_first_phi
    REAL(real64) :: surface_water(6),center_water(6)
    REAL(real64) :: before_alpha_surface,before_alpha_center
    REAL(real64) :: after_alpha_surface,after_alpha_center
    REAL(real64) :: expected_geometry_mass

    CALL make_state(background)
    CALL set_surface_boundary(background,0.006_real32,290.0_real32,0.0_real32)
    proposal=background
    background_before=background; proposal_before=proposal
    requested_surface_pressure=REAL(proposal%surface_pressure%value,real64)
    requested_surface_pressure(1,1)=requested_surface_pressure(1,1)+20.0_real64
    support=.TRUE.; reference_level=0

    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level,requested_surface_pressure, budget)
    CALL check(result%status==STATUS_OK,'full-support surface pressure request succeeds')
    CALL check(canonical_states_equal(background,background_before) .AND. &
      canonical_states_equal(proposal,proposal_before),'surface pressure transaction preserves inputs')
    CALL check(candidate%surface_pressure%value(1,1)== &
      REAL(requested_surface_pressure(1,1),real32) .AND. &
      candidate%surface_pressure%value(2,1)==proposal%surface_pressure%value(2,1), &
      'surface pressure stores requested values in float32 and leaves other columns unchanged')
    CALL check(ALL(candidate%above_ground .EQV. proposal%above_ground), &
      'surface pressure request preserves pressure-level classification')
    CALL check(ALL(candidate%temperature%value==proposal%temperature%value) .AND. &
      ALL(candidate%vapor%value==proposal%vapor%value) .AND. &
      ALL(candidate%cloud_water%value==proposal%cloud_water%value) .AND. &
      ALL(candidate%cloud_ice%value==proposal%cloud_ice%value) .AND. &
      ALL(candidate%rain%value==proposal%rain%value) .AND. &
      ALL(candidate%snow%value==proposal%snow%value) .AND. &
      ALL(candidate%graupel%value==proposal%graupel%value), &
      'surface pressure geometry update preserves temperature and species')

    expected=proposal
    expected%surface_pressure%value=REAL(requested_surface_pressure,real32)
    CALL configure_pressure_geometry(expected,status,proposal%above_ground)
    CALL check(status==STATUS_OK,'expected requested pressure geometry configures')
    CALL refresh_dry_air_mass_measure(expected,status)
    CALL check(status==STATUS_OK,'expected requested dry-air mass refreshes')
    CALL check(ALL(candidate%grid%cell_dp==expected%grid%cell_dp) .AND. &
      ALL(candidate%grid%pressure_mass_measure==expected%grid%pressure_mass_measure) .AND. &
      ALL(candidate%grid%dry_air_mass_measure==expected%grid%dry_air_mass_measure), &
      'candidate publishes refreshed pressure and dry-mass geometry')
    CALL check(ALL(candidate%grid%cell_dp(2,1,:)==proposal%grid%cell_dp(2,1,:)) .AND. &
      ALL(candidate%grid%pressure_mass_measure(2,1,:)==proposal%grid%pressure_mass_measure(2,1,:)) .AND. &
      ALL(candidate%grid%dry_air_mass_measure(2,1,:)==proposal%grid%dry_air_mass_measure(2,1,:)), &
      'unchanged second column retains all geometry measures')

    surface_water=0.0_real64; center_water=species(proposal,1,1,1)
    surface_water(1)=REAL(proposal%surface_vapor%value(1,1),real64)
    before_alpha_surface=air_volume_factor(REAL(background%surface_temperature%value(1,1),real64), &
      surface_water)
    before_alpha_center=air_volume_factor(REAL(background%temperature%value(1,1,1),real64), &
      center_water)
    after_alpha_surface=air_volume_factor(REAL(proposal%surface_temperature%value(1,1),real64), &
      surface_water)
    after_alpha_center=air_volume_factor(REAL(proposal%temperature%value(1,1,1),real64), &
      center_water)
    expected_surface_delta=0.5_real64*(after_alpha_surface+after_alpha_center)* &
      LOG(requested_surface_pressure(1,1)/REAL(proposal%pressure%value(1,1,1),real64))- &
      0.5_real64*(before_alpha_surface+before_alpha_center)* &
      LOG(REAL(proposal%surface_pressure%value(1,1),real64)/ &
          REAL(proposal%pressure%value(1,1,1),real64))
    expected_first_phi=REAL(proposal%geopotential%value(1,1,1),real64)+expected_surface_delta
    CALL check(candidate%geopotential%value(1,1,1)>proposal%geopotential%value(1,1,1) .AND. &
      real32_bits(candidate%geopotential%value(1,1,1))==real32_bits(REAL(expected_first_phi,real32)), &
      'positive first Phi matches the surface-anchor hydrostatic kernel')

    expected_geometry_mass=background%grid%dx(1,1)*background%grid%dy(1,1)*20.0_real64/9.80665_real64
    CALL check(ABS(budget%geometry_mass_change_kg-expected_geometry_mass)<=1.0e-5_real64, &
      'pressure ledger geometry mass is A times 20 Pa divided by g')
    CALL check(budget%accounted_cells==6_int64 .AND. &
      ABS(budget%total_mass_error_kg)<=1.0e-5_real64 .AND. &
      budget%incomplete_background_cells==0_int64 .AND. &
      budget%incomplete_candidate_cells==0_int64, &
      'pressure ledger accounts proposal to new state and closes')
  END SUBROUTINE test_surface_pressure_geometry_transaction

  SUBROUTINE test_surface_pressure_preserves_rounded_geometry
    TYPE(cloud_bal_state_type) :: background,proposal,candidate
    TYPE(cloud_bal_state_type) :: background_before,proposal_before
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY),status,reason
    REAL(real64) :: requested_surface_pressure(NX,NY)

    CALL make_state(background)
    CALL set_surface_boundary(background,0.006_real32,290.0_real32,0.0_real32)
    ! Keep a valid-but-rounded metric perturbation in the untouched column.
    ! The transaction must not normalize it as a side effect of configuring
    ! the changed column.
    background%grid%pressure_interface(2,1,1)= &
      NEAREST(background%grid%pressure_interface(2,1,1),1.0_real64)
    background%grid%cell_dp(2,1,1)= &
      NEAREST(background%grid%cell_dp(2,1,1),1.0_real64)
    background%grid%level_spacing_dp(2,1,1)= &
      NEAREST(background%grid%level_spacing_dp(2,1,1),1.0_real64)
    background%grid%pressure_mass_measure(2,1,1)= &
      NEAREST(background%grid%pressure_mass_measure(2,1,1),1.0_real64)
    background%grid%dry_air_mass_measure(2,1,1)= &
      NEAREST(background%grid%dry_air_mass_measure(2,1,1),1.0_real64)
    proposal=background
    CALL validate_canonical_state(proposal,.FALSE.,.FALSE.,status,reason,.FALSE.)
    CALL check(status==STATUS_OK,'rounded untouched-column geometry remains canonical')
    background_before=background; proposal_before=proposal
    requested_surface_pressure=REAL(proposal%surface_pressure%value,real64)
    requested_surface_pressure(1,1)=requested_surface_pressure(1,1)+20.0_real64
    support=.TRUE.; reference_level=0

    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level,requested_surface_pressure,budget)
    CALL check(result%status==STATUS_OK,'surface pressure update accepts rounded untouched geometry')
    CALL check(canonical_states_equal(background,background_before) .AND. &
      canonical_states_equal(proposal,proposal_before), &
      'rounded-geometry transaction preserves both inputs')
    CALL check(real64_bits_equal(candidate%grid%pressure_interface(2,1,:), &
      proposal%grid%pressure_interface(2,1,:)) .AND. &
      real64_bits_equal(candidate%grid%cell_dp(2,1,:),proposal%grid%cell_dp(2,1,:)) .AND. &
      real64_bits_equal(candidate%grid%level_spacing_dp(2,1,:), &
        proposal%grid%level_spacing_dp(2,1,:)) .AND. &
      real64_bits_equal(candidate%grid%pressure_mass_measure(2,1,:), &
        proposal%grid%pressure_mass_measure(2,1,:)) .AND. &
      real64_bits_equal(candidate%grid%dry_air_mass_measure(2,1,:), &
        proposal%grid%dry_air_mass_measure(2,1,:)), &
      'unchanged second column retains all five geometry and dry-mass arrays bitwise')
  END SUBROUTINE test_surface_pressure_preserves_rounded_geometry

  SUBROUTINE test_surface_anchor_below_terrain
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: result
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY),status,reason

    CALL make_state(background)
    CALL set_surface_boundary(background,0.006_real32,290.0_real32,10.0_real32)
    proposal=background
    proposal%surface_temperature%value(1,1)=150.0_real32
    proposal%temperature%value(1,1,:)=150.0_real32
    CALL validate_canonical_state(proposal,.FALSE.,.FALSE.,status,reason,.FALSE.)
    CALL check(status==STATUS_OK,'strongly cooled shallow-terrain fixture is canonical')
    before=proposal; support=.TRUE.; reference_level=0

    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'no-PS surface anchor below terrain is rejected')
    CALL check(canonical_states_equal(candidate,before), &
      'below-terrain surface anchor rolls back the original proposal')
  END SUBROUTINE test_surface_anchor_below_terrain

  SUBROUTINE test_surface_pressure_missing_pair
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)
    REAL(real64) :: requested_surface_pressure(NX,NY)

    CALL make_state(background)
    CALL set_surface_boundary(background,0.006_real32,290.0_real32,0.0_real32)
    proposal=background; before=proposal
    requested_surface_pressure=REAL(proposal%surface_pressure%value,real64)
    requested_surface_pressure(1,1)=requested_surface_pressure(1,1)+20.0_real64
    support=.TRUE.; reference_level=0
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level,requested_surface_pressure)
    CALL check(result%status==STATUS_FAILED .AND. canonical_states_equal(candidate,before), &
      'surface pressure request without paired budget is rejected transactionally')

    budget=pressure_analysis_budget()
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level,geometry_budget=budget)
    CALL check(result%status==STATUS_FAILED .AND. canonical_states_equal(candidate,before) .AND. &
      pressure_budget_zero(budget), &
      'surface pressure budget without paired request is rejected with zero budget')
  END SUBROUTINE test_surface_pressure_missing_pair

  SUBROUTINE test_surface_pressure_outside_support
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)
    REAL(real64) :: requested_surface_pressure(NX,NY)

    CALL make_state(background)
    CALL set_surface_boundary(background,0.006_real32,290.0_real32,0.0_real32)
    proposal=background; before=proposal
    requested_surface_pressure=REAL(proposal%surface_pressure%value,real64)
    requested_surface_pressure(1,1)=requested_surface_pressure(1,1)+20.0_real64
    support=.TRUE.; support(1,1,1)=.FALSE.; reference_level=0
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level,requested_surface_pressure,budget)
    CALL check(result%status==STATUS_FAILED .AND. canonical_states_equal(candidate,before) .AND. &
      pressure_budget_zero(budget), &
      'surface pressure request outside support is rejected with zero budget')
  END SUBROUTINE test_surface_pressure_outside_support

  SUBROUTINE test_surface_pressure_crossing_level
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: result
    TYPE(pressure_analysis_budget) :: budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)
    REAL(real64) :: requested_surface_pressure(NX,NY)

    CALL make_state(background)
    CALL set_surface_boundary(background,0.006_real32,290.0_real32,0.0_real32)
    proposal=background; before=proposal
    requested_surface_pressure=REAL(proposal%surface_pressure%value,real64)
    requested_surface_pressure(1,1)=94000.0_real64
    support=.TRUE.; reference_level=0
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level,requested_surface_pressure,budget)
    CALL check(result%status==STATUS_FAILED .AND. canonical_states_equal(candidate,before) .AND. &
      pressure_budget_zero(budget), &
      'surface pressure crossing a pressure-level classification is rejected')
  END SUBROUTINE test_surface_pressure_crossing_level

  SUBROUTINE test_empty_support
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: result
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)

    CALL make_state(background); proposal=background
    CALL make_missing_field(proposal%rain,1,1,1)
    CALL make_missing_field(proposal%rain,2,1,3)
    CALL refresh_state(proposal)
    before=proposal; support=.FALSE.; reference_level=1
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_OK,'empty support is a valid no-op')
    CALL check(.NOT.ANY(result%changed),'empty support has no changed cells')
    CALL check(canonical_states_equal(candidate,before),'empty support preserves proposal exactly')
  END SUBROUTINE test_empty_support

  SUBROUTINE test_missing_field
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: phase_result,result
    TYPE(water_phase_budget) :: phase_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)

    CALL make_state(background); support=.TRUE.; reference_level=1
    CALL make_phase_proposal(background,proposal,support,phase_result,phase_budget)
    CALL make_missing_field(proposal%rain,1,1,2)
    CALL refresh_state(proposal)
    before=proposal
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'selected missing condensate rejects')
    CALL check(.NOT.ANY(result%changed),'missing condensate has no changes')
    CALL check(canonical_states_equal(candidate,before),'missing condensate rolls back')
  END SUBROUTINE test_missing_field

  SUBROUTINE test_nan_field
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: result
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)

    CALL make_state(background); proposal=background
    proposal%temperature%value(1,1,2)=ieee_value(0.0_real32,ieee_quiet_nan)
    before=proposal; support=.TRUE.; reference_level=1
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'NaN selected temperature rejects')
    CALL check(.NOT.ANY(result%changed),'NaN input has no changes')
    CALL check(real32_bits(candidate%temperature%value(1,1,2))== &
      real32_bits(before%temperature%value(1,1,2)) .AND. &
      real32_bits(candidate%geopotential%value(1,1,2))== &
      real32_bits(before%geopotential%value(1,1,2)),'NaN input rolls back proposal')
  END SUBROUTINE test_nan_field

  SUBROUTINE test_pressure_mismatch
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: result
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY),status

    CALL make_state(background); proposal=background
    proposal%pressure%value(1,1,2)=proposal%pressure%value(1,1,2)-100.0_real32
    CALL configure_pressure_geometry(proposal,status)
    CALL check(status==STATUS_OK,'pressure-mismatch fixture geometry is canonical')
    CALL refresh_state(proposal)
    before=proposal; support=.TRUE.; reference_level=1
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'pressure mismatch rejects')
    CALL check(canonical_states_equal(candidate,before),'pressure mismatch rolls back proposal')
    support=.FALSE.
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'empty support cannot bypass fixed pressure geometry')
    CALL check(canonical_states_equal(candidate,before),'empty pressure mismatch preserves proposal')
  END SUBROUTINE test_pressure_mismatch

  SUBROUTINE test_metadata_mismatch
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: result
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)

    CALL make_state(background); proposal=background
    CALL shift_metadata_time(proposal,VALID_TIME+1_int64)
    before=proposal; support=.TRUE.; reference_level=1
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'selected metadata mismatch rejects')
    CALL check(canonical_states_equal(candidate,before),'metadata mismatch rolls back proposal')
    proposal=background
    proposal%geopotential%source(1,1,1)=IOR(SOURCE_BACKGROUND_MODEL,SOURCE_COLUMN_PHYSICS)
    before=proposal
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'equal Phi cannot conceal changed reference provenance')
    CALL check(canonical_states_equal(candidate,before),'reference provenance mismatch preserves proposal')
  END SUBROUTINE test_metadata_mismatch

  SUBROUTINE test_support_truncation
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,before
    TYPE(stage_result) :: phase_result,result
    TYPE(water_phase_budget) :: phase_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)

    CALL make_state(background); support=.TRUE.; reference_level=1
    CALL make_phase_proposal(background,proposal,support,phase_result,phase_budget)
    support=.FALSE.; support(:,1,1)=.TRUE.
    before=proposal
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_FAILED,'nonzero increment outside support rejects')
    CALL check(canonical_states_equal(candidate,before),'support truncation rolls back all cells')
  END SUBROUTINE test_support_truncation

  SUBROUTINE test_repeat_rejected
    TYPE(cloud_bal_state_type) :: background,proposal,candidate,repeated
    TYPE(stage_result) :: phase_result,result,repeated_result
    TYPE(water_phase_budget) :: phase_budget
    LOGICAL :: support(NX,NY,NZ)
    INTEGER :: reference_level(NX,NY)
    TYPE(cloud_bal_state_type) :: before

    CALL make_state(background); support=.TRUE.; reference_level=1
    CALL make_phase_proposal(background,proposal,support,phase_result,phase_budget)
    CALL apply_pressure_hydrostatic_increment(background,proposal,candidate,result, &
      support,reference_level)
    CALL check(result%status==STATUS_OK,'first hydrostatic correction succeeds')
    before=candidate
    CALL apply_pressure_hydrostatic_increment(background,candidate,repeated,repeated_result, &
      support,reference_level)
    CALL check(repeated_result%status==STATUS_FAILED,'repeated correction is rejected')
    CALL check(canonical_states_equal(repeated,before),'repeated correction has no double change')
  END SUBROUTINE test_repeat_rejected

  SUBROUTINE make_phase_proposal(background,proposal,support,result,budget)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background
    TYPE(cloud_bal_state_type), INTENT(OUT) :: proposal
    LOGICAL, INTENT(IN) :: support(:,:,:)
    TYPE(stage_result), INTENT(OUT) :: result
    TYPE(water_phase_budget), INTENT(OUT) :: budget
    REAL(real64) :: delta(NX,NY,NZ,6)

    delta=0.0_real64
    WHERE (support)
      delta(:,:,:,1)=-1.0e-3_real64
      delta(:,:,:,2)= 1.0e-3_real64
    END WHERE
    CALL apply_pressure_phase_transfer(background,proposal,result,support,delta,budget)
  END SUBROUTINE make_phase_proposal

  PURE REAL(real64) FUNCTION air_volume_factor(temperature,water)
    REAL(real64), INTENT(IN) :: temperature,water(6)
    air_volume_factor=RD_AIR*temperature*(1.0_real64+water(1)/EPSILON_WATER)/ &
      (1.0_real64+SUM(water))
  END FUNCTION air_volume_factor

  SUBROUTINE set_surface_boundary(state,vapor,temperature,height)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    REAL(real32), INTENT(IN) :: vapor,temperature,height

    state%surface_pressure%value=100000.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_pressure%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%value=temperature
    state%surface_temperature%valid=.TRUE.; state%surface_temperature%quality=0_int32
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%surface_vapor%value=vapor
    state%surface_vapor%valid=.TRUE.; state%surface_vapor%quality=0_int32
    state%surface_vapor%source=SOURCE_BACKGROUND_MODEL
    state%surface_height%value=height
    state%surface_height%valid=.TRUE.; state%surface_height%quality=0_int32
    state%surface_height%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE set_surface_boundary

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER :: status,reason,i,j,k

    CALL initialize_cloud_bal_state(state,NX,NY,NZ,VALID_TIME, &
      'pressure-hydrostatic-state',status)
    IF (status/=STATUS_OK) ERROR STOP 'hydrostatic fixture initialization failed'
    state%grid%dx=2000.0_real64; state%grid%dy=2200.0_real64
    state%surface_pressure%value=100000.0_real32
    state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0_int32; state%surface_temperature%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    DO k=1,NZ; DO j=1,NY; DO i=1,NX
      state%pressure%value(i,j,k)=REAL(PRESSURE_LEVELS(k),real32)
      state%temperature%value(i,j,k)=REAL(278.0_real64-2.0_real64*REAL(k-1,real64),real32)
      state%vapor%value(i,j,k)=0.008_real32
      state%u%value(i,j,k)=2.0_real32; state%v%value(i,j,k)=-1.0_real32
      state%omega%value(i,j,k)=0.2_real32; state%omega_target%value(i,j,k)=0.3_real32
      state%omega_target_sigma%value(i,j,k)=1.0_real32
      state%geopotential%value(i,j,k)=REAL(100.0_real64+20.0_real64*REAL(k-1,real64),real32)
      state%cloud_fraction%value(i,j,k)=0.2_real32; state%radar_reflectivity%value(i,j,k)=10.0_real32
      state%cloud_type%value(i,j,k)=1_int32; state%precipitation_phase%value(i,j,k)=1_int32
      state%lightning_support%value(i,j,k)=1_int32
      state%vt_z_mean%value(i,j,k)=0.5_real32; state%vt_z_sigma%value(i,j,k)=0.1_real32
      state%cloud_water%value(i,j,k)=0.003_real32; state%cloud_ice%value(i,j,k)=0.001_real32
      state%rain%value(i,j,k)=0.002_real32; state%snow%value(i,j,k)=0.001_real32
      state%graupel%value(i,j,k)=0.001_real32
    END DO; END DO; END DO
    CALL valid_real(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%u,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%v,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%omega_target,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%omega_target_sigma,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_fraction,SOURCE_CLOUD_ANALYSIS)
    CALL valid_real(state%radar_reflectivity,SOURCE_RADAR_DBZ)
    CALL valid_integer(state%cloud_type,SOURCE_CLOUD_ANALYSIS)
    CALL valid_integer(state%precipitation_phase,SOURCE_CLOUD_ANALYSIS)
    CALL valid_integer(state%lightning_support,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_water,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%rain,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%snow,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%graupel,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vt_z_mean,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vt_z_sigma,SOURCE_BACKGROUND_MODEL)
    state%above_ground=.TRUE.; state%obs_support=0_int32; state%hydro_support=0_int32
    state%balance_beta=0.0_real32
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'hydrostatic fixture geometry failed'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'hydrostatic fixture mass failed'
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) ERROR STOP 'hydrostatic fixture is not canonical'
  END SUBROUTINE make_state

  SUBROUTINE refresh_state(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER :: status
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'hydrostatic modified fixture mass failed'
  END SUBROUTINE refresh_state

  SUBROUTINE shift_metadata_time(state,new_time)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER(int64), INTENT(IN) :: new_time
    state%pressure%valid_time=new_time
    state%temperature%valid_time=new_time; state%vapor%valid_time=new_time
    state%u%valid_time=new_time; state%v%valid_time=new_time
    state%omega%valid_time=new_time; state%omega_target%valid_time=new_time
    state%omega_target_sigma%valid_time=new_time; state%geopotential%valid_time=new_time
    state%cloud_fraction%valid_time=new_time; state%radar_reflectivity%valid_time=new_time
    state%cloud_water%valid_time=new_time; state%cloud_ice%valid_time=new_time
    state%rain%valid_time=new_time; state%snow%valid_time=new_time
    state%graupel%valid_time=new_time; state%vt_z_mean%valid_time=new_time
    state%vt_z_sigma%valid_time=new_time
    state%cloud_type%valid_time=new_time; state%precipitation_phase%valid_time=new_time
    state%lightning_support%valid_time=new_time
    state%surface_pressure%valid_time=new_time; state%surface_temperature%valid_time=new_time
  END SUBROUTINE shift_metadata_time

  SUBROUTINE valid_real(field,source)
    USE cloud_bal_state, ONLY: field3d
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE valid_real

  SUBROUTINE valid_integer(field,source)
    USE cloud_bal_state, ONLY: integer_field3d
    TYPE(integer_field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE valid_integer

  SUBROUTINE make_missing_field(field,i,j,k)
    USE cloud_bal_state, ONLY: field3d
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: i,j,k
    field%valid(i,j,k)=.FALSE.; field%quality(i,j,k)=QUALITY_RAW_MISSING
    field%source(i,j,k)=0_int32
  END SUBROUTINE make_missing_field

  REAL(real32) FUNCTION expected_phi(background,proposal,i,j,k)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,proposal
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64) :: pressure(NZ),tb(NZ),ta(NZ),wb(6,NZ),wa(6,NZ),delta(NZ)
    INTEGER :: level,status
    DO level=1,NZ
      pressure(level)=REAL(background%pressure%value(i,j,level),real64)
      tb(level)=REAL(background%temperature%value(i,j,level),real64)
      ta(level)=REAL(proposal%temperature%value(i,j,level),real64)
      wb(:,level)=species(background,i,j,level)
      wa(:,level)=species(proposal,i,j,level)
    END DO
    delta=0.0_real64
    CALL hydrostatic_oracle(pressure,tb,wb,ta,wa,delta,status)
    IF (status/=STATUS_OK) ERROR STOP 'hydrostatic oracle failed'
    expected_phi=REAL(REAL(proposal%geopotential%value(i,j,k),real64)+delta(k),real32)
  END FUNCTION expected_phi

  SUBROUTINE hydrostatic_oracle(pressure,tb,wb,ta,wa,delta,status)
    REAL(real64), INTENT(IN) :: pressure(:),tb(:),wb(:,:),ta(:),wa(:,:)
    REAL(real64), INTENT(OUT) :: delta(:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64) :: alpha_before(NZ),alpha_after(NZ)
    INTEGER :: k
    status=STATUS_FAILED; delta=0.0_real64
    IF (SIZE(pressure)/=NZ .OR. SIZE(tb)/=NZ .OR. SIZE(ta)/=NZ .OR. &
        ANY(SHAPE(wb)/=[6,NZ]) .OR. ANY(SHAPE(wa)/=[6,NZ])) RETURN
    DO k=1,NZ
      alpha_before(k)=RD_AIR*tb(k)*(1.0_real64+wb(1,k)/EPSILON_WATER)/ &
        (1.0_real64+SUM(wb(:,k)))
      alpha_after(k)=RD_AIR*ta(k)*(1.0_real64+wa(1,k)/EPSILON_WATER)/ &
        (1.0_real64+SUM(wa(:,k)))
    END DO
    delta(1)=0.0_real64
    DO k=2,NZ
      delta(k)=delta(k-1)+0.5_real64*((alpha_after(k-1)-alpha_before(k-1))+ &
        (alpha_after(k)-alpha_before(k)))*LOG(pressure(k-1)/pressure(k))
    END DO
    status=STATUS_OK
  END SUBROUTINE hydrostatic_oracle

  PURE FUNCTION species(state,i,j,k) RESULT(values)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64) :: values(6)
    values=[REAL(state%vapor%value(i,j,k),real64),REAL(state%cloud_water%value(i,j,k),real64), &
      REAL(state%cloud_ice%value(i,j,k),real64),REAL(state%rain%value(i,j,k),real64), &
      REAL(state%snow%value(i,j,k),real64),REAL(state%graupel%value(i,j,k),real64)]
  END FUNCTION species

  SUBROUTINE check_only_phi(before,after,message)
    TYPE(cloud_bal_state_type), INTENT(IN) :: before,after
    CHARACTER(LEN=*), INTENT(IN) :: message
    TYPE(cloud_bal_state_type) :: expected
    expected=before; expected%geopotential=after%geopotential
    CALL check(canonical_states_equal(expected,after),message)
  END SUBROUTINE check_only_phi

  SUBROUTINE check_state_except_phi(before,after,message)
    TYPE(cloud_bal_state_type), INTENT(IN) :: before,after
    CHARACTER(LEN=*), INTENT(IN) :: message
    TYPE(cloud_bal_state_type) :: left,right
    left=before; right=after
    left%geopotential=right%geopotential
    CALL check(canonical_states_equal(left,right),message)
  END SUBROUTINE check_state_except_phi

  SUBROUTINE check_phi_sources(before,after,changed,message)
    TYPE(cloud_bal_state_type), INTENT(IN) :: before,after
    LOGICAL, INTENT(IN) :: changed(:,:,:)
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER :: i,j,k
    DO k=1,NZ; DO j=1,NY; DO i=1,NX
      IF (changed(i,j,k)) THEN
        CALL check(after%geopotential%source(i,j,k)== &
          IOR(before%geopotential%source(i,j,k),SOURCE_COLUMN_PHYSICS),message)
        CALL check(IAND(after%geopotential%source(i,j,k),SOURCE_DYNAMIC_TARGET)==0_int32, &
          'hydrostatic Phi does not grant dynamic authority')
      ELSE
        CALL check(after%geopotential%source(i,j,k)==before%geopotential%source(i,j,k), &
          'unchanged Phi source is preserved')
      END IF
    END DO; END DO; END DO
  END SUBROUTINE check_phi_sources

  PURE LOGICAL FUNCTION pressure_budget_zero(budget)
    TYPE(pressure_analysis_budget), INTENT(IN) :: budget
    pressure_budget_zero=ALL(budget%species_change_kg==0.0_real64) .AND. &
      ALL(budget%mixing_ratio_change_kg==0.0_real64) .AND. &
      ALL(budget%dry_mass_redistribution_kg==0.0_real64) .AND. &
      budget%dry_air_change_kg==0.0_real64 .AND. budget%enthalpy_change_j==0.0_real64 .AND. &
      budget%geometry_mass_change_kg==0.0_real64 .AND. &
      budget%enthalpy_composition_change_j==0.0_real64 .AND. &
      budget%enthalpy_mass_metric_change_j==0.0_real64 .AND. &
      budget%total_mass_error_kg==0.0_real64 .AND. budget%max_cell_mass_error_kg==0.0_real64 .AND. &
      budget%accounted_cells==0_int64 .AND. budget%incomplete_background_cells==0_int64 .AND. &
      budget%incomplete_candidate_cells==0_int64
  END FUNCTION pressure_budget_zero

  PURE LOGICAL FUNCTION real64_bits_equal(left,right)
    REAL(real64), INTENT(IN) :: left(:),right(:)
    INTEGER(int64) :: left_bits(SIZE(left)),right_bits(SIZE(right))
    real64_bits_equal=.FALSE.
    IF (SIZE(left)/=SIZE(right)) RETURN
    left_bits=TRANSFER(left,left_bits)
    right_bits=TRANSFER(right,right_bits)
    real64_bits_equal=ALL(left_bits==right_bits)
  END FUNCTION real64_bits_equal

  PURE ELEMENTAL INTEGER(int32) FUNCTION real32_bits(value)
    REAL(real32), INTENT(IN) :: value
    real32_bits=TRANSFER(value,real32_bits)
  END FUNCTION real32_bits

END PROGRAM test_pressure_hydrostatic_state
