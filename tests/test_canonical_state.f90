PROGRAM test_canonical_state
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan,ieee_positive_inf
  USE cloud_bal_state
  IMPLICIT NONE

  INTEGER :: failures
  failures=0
  CALL test_contract(failures)
  CALL test_optional_surface_contract(failures)
  CALL test_observational_target_sigma_contract(failures)
  CALL test_domain_and_mass_contract(failures)
  CALL test_pressure_cell_geometry(failures)
  CALL test_vertical_conversion(failures)
  CALL test_exact_gas_eos(failures)
  CALL test_los_contract(failures)
  IF (failures/=0) THEN
    PRINT *,'Canonical state tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Canonical state tests passed'

CONTAINS

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE make_valid_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER :: status
    INTEGER(int64), PARAMETER :: analysis_time=1788224400_int64

    CALL initialize_cloud_bal_state(state,4,5,3,analysis_time,'NE57-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization failed'
    state%grid%dx=2000.0_real64
    state%grid%dy=2500.0_real64
    CALL fill_real_field(state%pressure,80000.0_real32,SOURCE_BACKGROUND_MODEL)
    state%pressure%value(:,:,1)=95000.0_real32
    state%pressure%value(:,:,2)=80000.0_real32
    state%pressure%value(:,:,3)=60000.0_real32
    CALL fill_real_field(state%temperature,280.0_real32,SOURCE_BACKGROUND_MODEL)
    CALL fill_real_field(state%vapor,0.008_real32,SOURCE_BACKGROUND_MODEL)
    CALL fill_real_field(state%u,5.0_real32,SOURCE_ANALYZED_WIND)
    CALL fill_real_field(state%v,-2.0_real32,SOURCE_ANALYZED_WIND)
    CALL fill_real_field(state%omega,0.0_real32,SOURCE_BACKGROUND_MODEL)
    CALL fill_surface_field(state%surface_pressure,100000.0_real32)
    CALL fill_surface_field(state%surface_temperature,290.0_real32)
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure geometry initialization failed'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'dry-air mass initialization failed'
  END SUBROUTINE make_valid_state

  SUBROUTINE fill_real_field(field,value,source)
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: value
    INTEGER(int32), INTENT(IN) :: source
    field%value=value
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=source
  END SUBROUTINE fill_real_field

  SUBROUTINE fill_surface_field(field,value)
    TYPE(field2d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: value
    field%value=value
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE fill_surface_field

  SUBROUTINE set_observational_pair(state,sigma_source,sigma_quality,sigma_value)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER(int32), INTENT(IN) :: sigma_source,sigma_quality
    REAL(real32), INTENT(IN) :: sigma_value
    INTEGER, PARAMETER :: i=2,j=2,k=2
    INTEGER(int32), PARAMETER :: target_source=IOR(SOURCE_DYNAMIC_TARGET, &
                                                     SOURCE_ANALYZED_WIND)

    state%omega_target%value(i,j,k)=0.5_real32
    state%omega_target%valid(i,j,k)=.TRUE.
    state%omega_target%quality(i,j,k)=0_int32
    state%omega_target%source(i,j,k)=target_source
    state%omega_target_sigma%value(i,j,k)=sigma_value
    state%omega_target_sigma%valid(i,j,k)=.TRUE.
    state%omega_target_sigma%quality(i,j,k)=sigma_quality
    state%omega_target_sigma%source(i,j,k)=sigma_source
  END SUBROUTINE set_observational_pair

  SUBROUTINE test_observational_target_sigma_contract(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state,state_copy,state_bad
    LOGICAL, ALLOCATABLE :: authority(:,:,:),resolved(:,:,:)
    INTEGER :: status,reason
    INTEGER(int32), PARAMETER :: target_source=IOR(SOURCE_DYNAMIC_TARGET, &
                                                    SOURCE_ANALYZED_WIND)
    INTEGER(int32), PARAMETER :: other_evidence=IOR(SOURCE_DYNAMIC_TARGET, &
                                                     SOURCE_CONVENTIONAL_OBS)

    ! A missing sigma is a permitted observational no-op, not a failed state.
    CALL make_valid_state(state)
    resolved=observational_target_is_resolved(state)
    CALL check(ALL(SHAPE(resolved)==(/4,5,3/)) .AND. .NOT.ANY(resolved), &
      'missing omega-target sigma must produce a correctly shaped no-op mask',failures)
    CALL check(omega_target_sigma_contract_valid(state), &
      'missing omega-target sigma must satisfy the canonical optional contract',failures)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_OK,'missing sigma must not globally fail canonical validation',failures)

    ! A finite positive sigma with matching evidence resolves the target.  There
    ! is deliberately no arbitrary upper bound on a valid one-sigma error.
    CALL make_valid_state(state)
    CALL set_observational_pair(state,target_source,0_int32,1.0_real32)
    authority=observational_target_has_authority(state)
    resolved=observational_target_is_resolved(state)
    CALL check(COUNT(authority)==1 .AND. authority(2,2,2) .AND. COUNT(resolved)==1 .AND. &
      resolved(2,2,2), &
      'matching positive sigma must authorize and resolve exactly one target cell',failures)
    CALL check(omega_target_sigma_contract_valid(state), &
      'positive finite sigma must satisfy the canonical contract',failures)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_OK,'positive sigma state must validate canonically',failures)
    state%omega_target%value(2,2,2)=0.0_real32
    authority=observational_target_has_authority(state)
    resolved=observational_target_is_resolved(state)
    CALL check(COUNT(authority)==1 .AND. COUNT(resolved)==0, &
      'authority mask must retain a target even when its innovation is unresolved',failures)
    state%omega_target%value(2,2,2)=0.5_real32
    state%omega_target_sigma%value(2,2,2)=HUGE(1.0_real32)
    authority=observational_target_has_authority(state)
    resolved=observational_target_is_resolved(state)
    CALL check(omega_target_sigma_contract_valid(state) .AND. COUNT(authority)==1 .AND. &
      COUNT(resolved)==1, &
      'very large finite sigma must remain valid without an arbitrary upper bound',failures)

    CALL make_valid_state(state)
    CALL set_observational_pair(state,SOURCE_ANALYZED_WIND,0_int32,1.0_real32)
    CALL check(COUNT(observational_target_has_authority(state))==1 .AND. &
      COUNT(observational_target_is_resolved(state))==1, &
      'a sigma may carry the target evidence without inventing independent authority',failures)

    ! Sigma provenance must share real dynamic evidence with the target.  A
    ! different evidence bit, or manufactured provenance, is not authority.
    CALL make_valid_state(state)
    CALL set_observational_pair(state,other_evidence,0_int32,1.0_real32)
    resolved=observational_target_is_resolved(state)
    CALL check(omega_target_sigma_contract_valid(state) .AND. .NOT.ANY(resolved), &
      'sigma with no common dynamic evidence must be a no-op',failures)
    CALL make_valid_state(state)
    CALL set_observational_pair(state,IOR(target_source,SOURCE_MANUFACTURED_TEST), &
      0_int32,1.0_real32)
    resolved=observational_target_is_resolved(state)
    CALL check(omega_target_sigma_contract_valid(state) .AND. .NOT.ANY(resolved), &
      'manufactured sigma provenance must never create observational authority',failures)
    CALL make_valid_state(state)
    CALL set_observational_pair(state,target_source,QUALITY_GEOMETRY_POOR,1.0_real32)
    resolved=observational_target_is_resolved(state)
    CALL check(omega_target_sigma_contract_valid(state) .AND. .NOT.ANY(resolved), &
      'dynamically excluded sigma quality must be a no-op',failures)

    ! Valid sigma values are strictly positive and finite; invalid values fail
    ! the state contract and are safely excluded from the resolved mask.
    CALL make_valid_state(state)
    CALL set_observational_pair(state,target_source,0_int32,0.0_real32)
    resolved=observational_target_is_resolved(state)
    CALL check(.NOT.omega_target_sigma_contract_valid(state) .AND. .NOT.ANY(resolved), &
      'zero sigma must fail closed',failures)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED,'zero sigma must fail canonical validation',failures)

    CALL make_valid_state(state)
    CALL set_observational_pair(state,target_source,QUALITY_QC_REJECTED,1.0_real32)
    resolved=observational_target_is_resolved(state)
    CALL check(.NOT.omega_target_sigma_contract_valid(state) .AND. .NOT.ANY(resolved), &
      'an unusable valid sigma must fail closed',failures)

    CALL make_valid_state(state)
    CALL set_observational_pair(state,target_source,0_int32, &
      ieee_value(0.0_real32,ieee_quiet_nan))
    resolved=observational_target_is_resolved(state)
    CALL check(.NOT.omega_target_sigma_contract_valid(state) .AND. .NOT.ANY(resolved), &
      'NaN sigma must fail closed without NaN arithmetic in the mask',failures)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED,'NaN sigma must fail canonical validation',failures)

    CALL make_valid_state(state)
    CALL set_observational_pair(state,target_source,0_int32,1.0_real32)
    state%omega_target_sigma%unit='m s-1'
    resolved=observational_target_is_resolved(state)
    CALL check(.NOT.omega_target_sigma_contract_valid(state) .AND. .NOT.ANY(resolved), &
      'wrong sigma units must fail before observational application',failures)
    state%omega_target_sigma%unit='Pa s-1'
    state%omega_target_sigma%valid_time=state%pressure%valid_time+1_int64
    resolved=observational_target_is_resolved(state)
    CALL check(.NOT.omega_target_sigma_contract_valid(state) .AND. .NOT.ANY(resolved), &
      'sigma valid-time mismatch must fail before observational application',failures)

    CALL make_valid_state(state)
    CALL set_observational_pair(state,target_source,0_int32,1.0_real32)
    state%above_ground(2,2,2)=.FALSE.
    resolved=observational_target_is_resolved(state)
    CALL check(.NOT.omega_target_sigma_contract_valid(state) .AND. .NOT.ANY(resolved), &
      'valid below-ground sigma must fail the domain contract',failures)

    CALL make_valid_state(state)
    state%omega_target_sigma%source(1,1,1)=ISHFT(1_int32,20)
    resolved=observational_target_is_resolved(state)
    CALL check(.NOT.omega_target_sigma_contract_valid(state) .AND. .NOT.ANY(resolved), &
      'unknown sigma source bits must fail even when sigma is missing',failures)

    ! The public mask must fail safely when sigma storage is incomplete.
    state_bad=state
    DEALLOCATE(state_bad%omega_target_sigma%value)
    resolved=observational_target_is_resolved(state_bad)
    CALL check(ALL(SHAPE(resolved)==(/4,5,3/)) .AND. .NOT.ANY(resolved), &
      'malformed sigma storage must return an all-false mask safely',failures)

    ! Sigma is part of canonical identity, including when all targets are absent.
    CALL make_valid_state(state)
    state_copy=state
    CALL check(canonical_states_equal(state,state_copy), &
      'canonical copies must include identical sigma metadata',failures)
    state_copy%omega_target_sigma%source(1,1,1)=SOURCE_BACKGROUND_MODEL
    CALL check(.NOT.canonical_states_equal(state,state_copy), &
      'canonical identity must detect sigma provenance changes',failures)
  END SUBROUTINE test_observational_target_sigma_contract

  SUBROUTINE test_contract(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state,read_state
    TYPE(canonical_input_spec) :: spec
    TYPE(stage_result) :: result
    INTEGER :: status,reason

    CALL make_valid_state(state)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
               'complete canonical state must validate',failures)

    state%vapor%valid(1,1,1)=.FALSE.
    state%vapor%quality(1,1,1)=QUALITY_RAW_MISSING
    CALL refresh_dry_air_mass_measure(state,status)
    CALL check(status==STATUS_FAILED, &
               'dry-air mass requires usable vapor in every physical cell',failures)
    state%vapor%valid(1,1,1)=.TRUE.
    state%vapor%quality(1,1,1)=0_int32
    CALL refresh_dry_air_mass_measure(state,status)

    state%pressure%unit='hPa'
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_SHAPE, &
               'wrong canonical unit must fail before use',failures)
    state%pressure%unit='Pa'

    state%temperature%value(2,2,2)=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_NONFINITE, &
               'valid NaN must fail',failures)
    state%temperature%value(2,2,2)=280.0_real32

    ALLOCATE(spec%supplied_state)
    spec%supplied_state=state
    CALL read_canonical_state(spec,read_state,result)
    CALL check(result%status==STATUS_OK,'validated read must succeed',failures)
    spec%supplied_state%u%value=99.0_real32
    CALL check(ALL(TRANSFER(read_state%u%value,[0_int32],SIZE(read_state%u%value))== &
                   TRANSFER(5.0_real32,0_int32)), &
               'read must deep-copy the supplied state',failures)
  END SUBROUTINE test_contract

  SUBROUTINE test_optional_surface_contract(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state,state_copy
    INTEGER :: status,reason

    CALL make_valid_state(state)
    CALL check(ALLOCATED(state%surface_vapor%value) .AND. &
      ALLOCATED(state%surface_vapor%valid) .AND. &
      ALLOCATED(state%surface_vapor%quality) .AND. &
      ALLOCATED(state%surface_vapor%source) .AND. &
      ALL(.NOT.state%surface_vapor%valid) .AND. &
      ALL(state%surface_vapor%quality==QUALITY_RAW_MISSING) .AND. &
      ALL(state%surface_vapor%source==0_int32) .AND. &
      state%surface_vapor%unit=='kg kg-1 dryair' .AND. &
      state%surface_vapor%valid_time==state%pressure%valid_time, &
      'surface vapor must initialize as an invalid canonical field',failures)
    CALL check(ALLOCATED(state%surface_height%value) .AND. &
      ALL(.NOT.state%surface_height%valid) .AND. &
      ALL(state%surface_height%quality==QUALITY_RAW_MISSING) .AND. &
      ALL(state%surface_height%source==0_int32) .AND. &
      state%surface_height%unit=='m' .AND. &
      state%surface_height%valid_time==state%pressure%valid_time, &
      'surface height must initialize with standard invalid metadata',failures)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.TRUE.)
    CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
      'legacy states with absent optional boundary coverage must validate',failures)

    state%surface_vapor%value(1,1)=0.01_real32
    state%surface_vapor%valid(1,1)=.TRUE.
    state%surface_vapor%quality(1,1)=0_int32
    state%surface_vapor%source(1,1)=SOURCE_BACKGROUND_MODEL
    state%surface_height%value(2,2)=100.0_real32
    state%surface_height%valid(2,2)=.TRUE.
    state%surface_height%quality(2,2)=0_int32
    state%surface_height%source(2,2)=SOURCE_BACKGROUND_MODEL
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.TRUE.)
    CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
      'partial optional boundary coverage must remain STATUS_OK',failures)

    state_copy=state
    CALL check(canonical_states_equal(state,state_copy), &
      'canonical equality must include identical optional boundary fields',failures)
    state_copy%surface_vapor%valid_time=state%pressure%valid_time+1_int64
    CALL check(.NOT.canonical_states_equal(state,state_copy), &
      'canonical equality must detect optional boundary metadata changes',failures)
    state_copy=state
    state_copy%surface_height%value(2,2)=101.0_real32
    CALL check(.NOT.canonical_states_equal(state,state_copy), &
      'canonical equality must detect optional boundary value changes',failures)

    CALL make_valid_state(state)
    state%surface_vapor%unit='g kg-1'
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.TRUE.)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_SHAPE, &
      'optional surface vapor metadata must be canonical when allocated',failures)

    CALL make_valid_state(state)
    state%surface_vapor%valid(1,1)=.TRUE.
    state%surface_vapor%quality(1,1)=0_int32
    state%surface_vapor%source(1,1)=SOURCE_BACKGROUND_MODEL
    state%surface_vapor%value(1,1)=-0.001_real32
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.TRUE.)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_RANGE, &
      'negative optional surface vapor must be rejected',failures)
    state%surface_vapor%value(1,1)=0.101_real32
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.TRUE.)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_RANGE, &
      'optional surface vapor above 0.1 must be rejected',failures)

    CALL make_valid_state(state)
    state%surface_height%valid(1,1)=.TRUE.
    state%surface_height%quality(1,1)=0_int32
    state%surface_height%source(1,1)=SOURCE_BACKGROUND_MODEL
    state%surface_height%value(1,1)=-501.0_real32
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.TRUE.)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_RANGE, &
      'optional surface height below -500 must be rejected',failures)
    state%surface_height%value(1,1)=9001.0_real32
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.TRUE.)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_RANGE, &
      'optional surface height above 9000 must be rejected',failures)

    CALL make_valid_state(state)
    state%surface_vapor%value=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.TRUE.)
    CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
      'NaNs retained in invalid optional surface cells must not trap validation',failures)

    CALL make_valid_state(state)
    DEALLOCATE(state%surface_height%quality)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.TRUE.)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_SHAPE, &
      'partially allocated optional surface metadata must be rejected',failures)
  END SUBROUTINE test_optional_surface_contract

  SUBROUTINE test_domain_and_mass_contract(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state
    REAL(real64) :: expected
    INTEGER :: status,reason

    CALL make_valid_state(state)
    state%rain%value(2,2,2)=0.002_real32
    state%rain%valid(2,2,2)=.TRUE.
    state%rain%quality(2,2,2)=0_int32
    state%rain%source(2,2,2)=SOURCE_BACKGROUND_MODEL
    CALL refresh_dry_air_mass_measure(state,status)
    expected=state%grid%pressure_mass_measure(2,2,2)/(1.0_real64+0.010_real64)
    CALL check(status==STATUS_OK .AND. &
      ABS(state%grid%dry_air_mass_measure(2,2,2)-expected)<= &
      2.0e-7_real64*expected, &
      'dry-air mass must use represented total-water mixing ratio',failures)

    state%surface_pressure%value(1,1)=90000.0_real32
    CALL configure_pressure_geometry(state,status)
    CALL check(status==STATUS_OK .AND. .NOT.state%above_ground(1,1,1), &
      'surface pressure must define the terrain domain independently',failures)
    CALL invalidate_cell(state%pressure,1,1,1)
    CALL invalidate_cell(state%temperature,1,1,1)
    CALL invalidate_cell(state%vapor,1,1,1)
    CALL invalidate_cell(state%u,1,1,1)
    CALL invalidate_cell(state%v,1,1,1)
    CALL invalidate_cell(state%omega,1,1,1)
    CALL refresh_dry_air_mass_measure(state,status)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_OK .AND. &
      state%grid%dry_air_mass_measure(1,1,1)==0.0_real64 .AND. &
      state%grid%pressure_mass_measure(1,1,1)==0.0_real64, &
      'below-ground cells must carry no physical cell mass',failures)

    state%balance_beta(1,1,1)=1.0_real32
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED, &
      'support must never enter the below-ground domain',failures)

    CALL make_valid_state(state)
    state%above_ground(1,1,2)=.FALSE.
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED, &
      'above-ground domain must be vertically contiguous',failures)

    CALL make_valid_state(state)
    state%u%source(1,1,1)=0_int32
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_METADATA, &
      'valid data without provenance must fail',failures)
    CALL make_valid_state(state)
    state%u%quality(1,1,1)=QUALITY_QC_REJECTED
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_METADATA, &
               'valid QC-rejected data must fail',failures)
    CALL make_valid_state(state)
    state%u%source(1,1,1)=ISHFT(1_int32,20)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_METADATA, &
               'unknown source bits must fail closed',failures)
    CALL make_valid_state(state)
    state%u%quality(1,1,1)=ISHFT(1_int32,20)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_METADATA, &
               'unknown quality bits must fail closed',failures)
    CALL check(.NOT.dynamic_target_has_authority(.TRUE.,0_int32, &
      IOR(SOURCE_CLOUD_ANALYSIS,SOURCE_DYNAMIC_TARGET)), &
      'a dynamic bit without independent wind evidence has no authority',failures)
    CALL check(.NOT.dynamic_target_has_authority(.TRUE.,0_int32, &
      IOR(SOURCE_ANALYZED_WIND,IOR(SOURCE_DYNAMIC_TARGET, &
          SOURCE_MANUFACTURED_TEST))), &
      'manufactured evidence must never enter observational authority',failures)
    CALL check(manufactured_target_has_test_authority(.TRUE.,0_int32, &
      IOR(SOURCE_DYNAMIC_TARGET,SOURCE_MANUFACTURED_TEST)), &
      'the exact manufactured source pair grants test-only authority',failures)
    CALL check(.NOT.manufactured_target_has_test_authority(.TRUE.,0_int32, &
      IOR(SOURCE_ANALYZED_WIND,IOR(SOURCE_DYNAMIC_TARGET, &
          SOURCE_MANUFACTURED_TEST))), &
      'test authority must reject mixed observational provenance',failures)

    CALL make_valid_state(state)
    DEALLOCATE(state%above_ground)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_SHAPE, &
      'missing domain mask must fail before field indexing',failures)
  END SUBROUTINE test_domain_and_mass_contract

  SUBROUTINE test_pressure_cell_geometry(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state,boundary_state
    INTEGER :: status
    REAL(real64) :: expected_mass
    LOGICAL :: terrain_domain(1,1,3)

    CALL initialize_cloud_bal_state(state,1,1,3,1788224400_int64, &
                                    'cut-cell-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'cut-cell state initialization failed'
    state%grid%dx=2000.0_real64
    state%grid%dy=3000.0_real64
    state%pressure%value(1,1,:)=[100000.0_real32,95000.0_real32,90000.0_real32]
    state%pressure%valid=.TRUE.
    state%pressure%quality=0_int32
    state%pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_pressure%value(1,1)=95500.0_real32
    state%surface_pressure%valid=.TRUE.
    state%surface_pressure%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    CALL configure_pressure_geometry(state,status)
    expected_mass=2000.0_real64*3000.0_real64*3000.0_real64/9.80665_real64

    CALL check(status==STATUS_OK,'surface cut-cell geometry must configure',failures)
    CALL check(ALL(state%grid%dry_air_mass_measure==0.0_real64) .AND. &
               .NOT.pressure_geometry_is_valid(state), &
      'unrefreshed dry-air mass must fail closed',failures)
    CALL check(.NOT.state%above_ground(1,1,1) .AND. &
               ALL(state%above_ground(1,1,2:3)), &
      'pressure-center domain must exclude the sub-surface center',failures)
    CALL check(ABS(state%grid%pressure_interface(1,1,2)-95500.0_real64)<1.0e-12_real64 &
               .AND. ABS(state%grid%pressure_interface(1,1,3)-92500.0_real64)< &
               1.0e-12_real64, &
      'surface and midpoint interfaces must bound the first active cell',failures)
    CALL check(ABS(state%grid%cell_dp(1,1,2)-3000.0_real64)<1.0e-12_real64 .AND. &
               ABS(state%grid%level_spacing_dp(1,1,2)-5000.0_real64)<1.0e-12_real64, &
      'cell thickness must remain distinct from center spacing',failures)
    CALL check(state%grid%cell_dp(1,1,1)==0.0_real64 .AND. &
               state%grid%pressure_mass_measure(1,1,1)==0.0_real64 .AND. &
               ABS(state%grid%pressure_mass_measure(1,1,2)-expected_mass)<= &
               1.0e-12_real64*expected_mass, &
      'pressure mass must use only the surface-truncated control volume',failures)

    state%surface_pressure%value(1,1)=99000.0_real32
    CALL configure_pressure_geometry(state,status)
    CALL check(status==STATUS_OK .AND. &
               ABS(state%grid%pressure_interface(1,1,2)-99000.0_real64)< &
               1.0e-12_real64 .AND. &
               ABS(state%grid%cell_dp(1,1,2)-6500.0_real64)<1.0e-12_real64, &
      'first active cell must extend to surface pressure without a mass gap',failures)

    state%surface_pressure%value(1,1)=100000.0_real32
    CALL configure_pressure_geometry(state,status)
    CALL check(status==STATUS_OK .AND. state%above_ground(1,1,1) .AND. &
               ABS(state%grid%cell_dp(1,1,1)-2500.0_real64)<1.0e-12_real64, &
      'a pressure center on the surface must retain its upper half cell',failures)

    terrain_domain=.TRUE.
    terrain_domain(1,1,1)=.FALSE.
    CALL configure_pressure_geometry(state,status,terrain_domain)
    CALL check(status==STATUS_OK .AND. .NOT.state%above_ground(1,1,1) .AND. &
               ALL(state%above_ground(1,1,2:3)) .AND. &
               ABS(state%grid%cell_dp(1,1,2)-7500.0_real64)<1.0e-12_real64, &
      'terrain constraint must clip the lower center and recompute its cell', &
      failures)

    state%surface_pressure%value(1,1)=91000.0_real32
    terrain_domain=.TRUE.
    CALL configure_pressure_geometry(state,status,terrain_domain)
    CALL check(status==STATUS_OK .AND. COUNT(state%above_ground)==1 .AND. &
               state%above_ground(1,1,3) .AND. &
               ABS(state%grid%cell_dp(1,1,3)-3500.0_real64)<1.0e-12_real64, &
      'one resolved surface-cut pressure cell must be representable',failures)

    expected_mass=state%grid%cell_dp(1,1,1)
    state%surface_pressure%unit='hPa'
    CALL configure_pressure_geometry(state,status)
    CALL check(status==STATUS_FAILED .AND. &
               state%grid%cell_dp(1,1,1)==expected_mass, &
      'failed pressure configuration must leave published geometry unchanged',failures)

    CALL initialize_cloud_bal_state(boundary_state,1,1,3,1788224400_int64, &
                                    'minimum-pressure-test',status)
    boundary_state%grid%dx=2000.0_real64
    boundary_state%grid%dy=3000.0_real64
    boundary_state%pressure%value(1,1,:)=[300.0_real32,200.0_real32, &
                                          REAL(MIN_PRESSURE_PA,real32)]
    boundary_state%pressure%valid=.TRUE.
    boundary_state%pressure%quality=0_int32
    boundary_state%pressure%source=SOURCE_BACKGROUND_MODEL
    boundary_state%surface_pressure%value=300.0_real32
    boundary_state%surface_pressure%valid=.TRUE.
    boundary_state%surface_pressure%quality=0_int32
    boundary_state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    CALL configure_pressure_geometry(boundary_state,status)
    CALL check(status==STATUS_OK, &
      'canonical minimum pressure must configure consistently',failures)
    boundary_state%pressure%value(1,1,3)=REAL(MIN_PRESSURE_PA-1.0_real64,real32)
    CALL configure_pressure_geometry(boundary_state,status)
    CALL check(status==STATUS_FAILED, &
      'pressure below the canonical minimum must fail at construction',failures)
  END SUBROUTINE test_pressure_cell_geometry

  SUBROUTINE invalidate_cell(field,i,j,k)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: i,j,k
    field%valid(i,j,k)=.FALSE.
    field%quality(i,j,k)=QUALITY_RAW_MISSING
    field%source(i,j,k)=0_int32
  END SUBROUTINE invalidate_cell

  SUBROUTINE test_vertical_conversion(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: omega(2,1,1),pressure(2,1,1),temperature(2,1,1)
    REAL(real32) :: vapor(2,1,1),w(2,1,1),roundtrip(2,1,1)
    LOGICAL :: valid(2,1,1),w_valid(2,1,1),omega_valid(2,1,1)
    INTEGER :: status

    omega(:,1,1)=(/-1.0_real32,1.5_real32/)
    pressure=85000.0_real32; temperature=280.0_real32; vapor=0.01_real32
    valid=.TRUE.
    CALL omega_to_w(omega,pressure,temperature,vapor,valid,w,w_valid,status)
    CALL check(status==STATUS_OK .AND. ALL(w_valid), &
               'omega to w conversion must succeed',failures)
    CALL check(w(1,1,1)>0.0_real32 .AND. w(2,1,1)<0.0_real32, &
               'omega and geometric w signs must oppose',failures)
    CALL w_to_omega(w,pressure,temperature,vapor,w_valid,roundtrip,omega_valid,status)
    CALL check(status==STATUS_OK .AND. &
               MAXVAL(ABS(roundtrip-omega))<2.0e-6_real32, &
               'local rho*g conversion must round trip',failures)

    pressure(1,1,1)=0.0_real32
    CALL omega_to_w(omega,pressure,temperature,vapor,valid,w,w_valid,status)
    CALL check(status==STATUS_FAILED,'nonphysical pressure must fail',failures)
  END SUBROUTINE test_vertical_conversion

  SUBROUTINE test_exact_gas_eos(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64), PARAMETER :: rd=287.05_real64, eps=0.622_real64
    REAL(real64), PARAMETER :: grav=9.80665_real64
    REAL(real64), PARAMETER :: p=90000.0_real64, temp=280.0_real64
    REAL(real64), PARAMETER :: rv_dry=0.0_real64, rv_typical=0.01_real64
    REAL(real64), PARAMETER :: rv_extreme=0.2_real64
    REAL(real64) :: rho_d,rho_g,expected_d,expected_g,nan64,inf64,huge64
    REAL(real64) :: fixed_w(3),expected_omega(3)
    REAL(real32) :: omega(3,1,1),pressure(3,1,1),temperature(3,1,1)
    REAL(real32) :: vapor(3,1,1),w(3,1,1),target_w(3,1,1),converted_omega(3,1,1)
    LOGICAL :: valid(3,1,1),w_valid(3,1,1),omega_valid(3,1,1)
    INTEGER :: status

    ! Independent gas EOS: vapor is a dry-air mixing ratio and condensate is absent.
    expected_d=p/(rd*temp*(1.0_real64+rv_typical/eps))
    expected_g=expected_d*(1.0_real64+rv_typical)
    rho_d=dry_air_density(p,temp,rv_typical)
    rho_g=moist_gas_density(p,temp,rv_typical)
    CALL check(ABS(rho_d-expected_d)<=1.0e-13_real64*expected_d .AND. &
               ABS(rho_g-expected_g)<=1.0e-13_real64*expected_g .AND. &
               rho_g>rho_d,'dry and moist densities must use the exact gas EOS',failures)

    expected_d=120000.0_real64/(rd*350.0_real64*(1.0_real64+rv_extreme/eps))
    expected_g=expected_d*(1.0_real64+rv_extreme)
    CALL check(ABS(dry_air_density(120000.0_real64,350.0_real64,rv_extreme)-expected_d) &
               <=1.0e-13_real64*expected_d .AND. &
               ABS(moist_gas_density(120000.0_real64,350.0_real64,rv_extreme)-expected_g) &
               <=1.0e-13_real64*expected_g, &
      'canonical EOS bounds must include the extreme mixing ratio',failures)
    CALL check(dry_air_density(p,temp,rv_dry)>0.0_real64 .AND. &
               moist_gas_density(p,temp,rv_dry)==dry_air_density(p,temp,rv_dry), &
      'dry canonical vapor must reduce to the dry-gas density',failures)

    omega(:,1,1)=[-1.0_real32,1.5_real32,-20.0_real32]
    pressure(:,1,1)=REAL(p,real32); temperature(:,1,1)=REAL(temp,real32)
    vapor(:,1,1)=[REAL(rv_dry,real32),REAL(rv_typical,real32),REAL(rv_extreme,real32)]
    valid=.TRUE.
    CALL omega_to_w(omega,pressure,temperature,vapor,valid,w,w_valid,status)
    CALL check(status==STATUS_OK .AND. ALL(w_valid), &
      'exact EOS omega-to-w conversion must succeed',failures)
    expected_d=p/(rd*temp*(1.0_real64+rv_dry/eps))
    expected_g=expected_d*(1.0_real64+rv_dry)
    CALL check(ABS(REAL(w(1,1,1),real64)-1.0_real64/(expected_g*grav))<=4.0e-7_real64, &
      'dry absolute w must match the independent EOS value',failures)
    expected_d=p/(rd*temp*(1.0_real64+rv_typical/eps))
    expected_g=expected_d*(1.0_real64+rv_typical)
    CALL check(ABS(REAL(w(2,1,1),real64)+1.5_real64/(expected_g*grav))<=4.0e-7_real64, &
      'typical-moist absolute w must match the independent EOS value',failures)
    expected_d=p/(rd*temp*(1.0_real64+rv_extreme/eps))
    expected_g=expected_d*(1.0_real64+rv_extreme)
    CALL check(ABS(REAL(w(3,1,1),real64)-20.0_real64/(expected_g*grav))<=4.0e-6_real64, &
      'extreme-moist absolute w must match the independent EOS value',failures)

    fixed_w=[0.5_real64,-2.0_real64,3.25_real64]
    expected_omega=-fixed_w*grav*p/(rd*temp)* &
      (1.0_real64+REAL(vapor(:,1,1),real64))/ &
      (1.0_real64+REAL(vapor(:,1,1),real64)/eps)
    target_w(:,1,1)=REAL(fixed_w,real32)
    CALL w_to_omega(target_w,pressure,temperature,vapor,valid,converted_omega,omega_valid,status)
    CALL check(status==STATUS_OK .AND. ALL(omega_valid) .AND. &
               MAXVAL(ABS(REAL(converted_omega(:,1,1),real64)-expected_omega))<=4.0e-6_real64, &
      'absolute w-to-omega values must match the independent EOS',failures)

    nan64=ieee_value(0.0_real64,ieee_quiet_nan)
    inf64=ieee_value(0.0_real64,ieee_positive_inf)
    huge64=HUGE(1.0_real64)
    CALL check(moist_gas_density(nan64,temp,rv_typical)==-1.0_real64 .AND. &
               moist_gas_density(inf64,temp,rv_typical)==-1.0_real64 .AND. &
               moist_gas_density(huge64,temp,rv_typical)==-1.0_real64 .AND. &
               dry_air_density(nan64,temp,rv_typical)==-1.0_real64 .AND. &
               dry_air_density(inf64,temp,rv_typical)==-1.0_real64 .AND. &
               dry_air_density(huge64,temp,rv_typical)==-1.0_real64 .AND. &
               moist_gas_density(p,nan64,rv_typical)==-1.0_real64 .AND. &
               moist_gas_density(p,inf64,rv_typical)==-1.0_real64 .AND. &
               moist_gas_density(p,temp,nan64)==-1.0_real64 .AND. &
               moist_gas_density(p,temp,inf64)==-1.0_real64 .AND. &
               moist_gas_density(p,temp,huge64)==-1.0_real64, &
      'nonfinite and huge canonical EOS inputs must fail closed',failures)
    CALL check(moist_gas_density(99.0_real64,temp,rv_typical)==-1.0_real64 .AND. &
               moist_gas_density(120001.0_real64,temp,rv_typical)==-1.0_real64 .AND. &
               moist_gas_density(p,149.0_real64,rv_typical)==-1.0_real64 .AND. &
               moist_gas_density(p,351.0_real64,rv_typical)==-1.0_real64 .AND. &
               moist_gas_density(p,temp,-1.0e-6_real64)==-1.0_real64 .AND. &
               moist_gas_density(p,temp,0.200001_real64)==-1.0_real64, &
      'out-of-domain canonical EOS inputs must fail closed',failures)

    valid(2,1,1)=.FALSE.; omega(2,1,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    pressure(2,1,1)=ieee_value(0.0_real32,ieee_positive_inf)
    temperature(2,1,1)=HUGE(1.0_real32)
    vapor(2,1,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL omega_to_w(omega,pressure,temperature,vapor,valid,w,w_valid,status)
    CALL check(status==STATUS_OK .AND. w_valid(1,1,1) .AND. .NOT.w_valid(2,1,1) .AND. &
               w_valid(3,1,1) .AND. w(2,1,1)==0.0_real32, &
      'inactive missing cells must not be evaluated by omega-to-w',failures)
  END SUBROUTINE test_exact_gas_eos

  SUBROUTINE test_los_contract(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state
    INTEGER :: status,reason,nx,ny,nz,nr,i,j,k
    INTEGER(int64) :: valid_time

    CALL make_valid_state(state)
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    valid_time=state%pressure%valid_time
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_OK,'absent LOS record must be exact OK',failures)

    ALLOCATE(state%radar_los%beam(nx,ny,nz,1,3))
    state%radar_los%beam=0.0_real32
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_FAILED, &
               'absent LOS record with allocated payload must fail',failures)
    DEALLOCATE(state%radar_los%beam)

    nr=1
    state%radar_los%is_present=.TRUE.; state%radar_los%nradar=nr
    state%radar_los%vrad_representation=VRAD_DEALIASED
    CALL initialize_field(state%radar_los%vrad,nx,ny,nz,nr,valid_time,'m s-1')
    CALL initialize_field(state%radar_los%nyquist,nx,ny,nz,nr,valid_time,'m s-1')
    CALL initialize_field(state%radar_los%sigma_vrad,nx,ny,nz,nr,valid_time,'m s-1')
    state%radar_los%vrad%value=3.0_real32
    state%radar_los%nyquist%value=15.0_real32
    state%radar_los%sigma_vrad%value=1.0_real32
    state%radar_los%vrad%valid=.TRUE.; state%radar_los%nyquist%valid=.TRUE.
    state%radar_los%sigma_vrad%valid=.TRUE.
    state%radar_los%vrad%quality=0; state%radar_los%nyquist%quality=0
    state%radar_los%sigma_vrad%quality=0
    state%radar_los%vrad%source=SOURCE_RADAR_VRAD
    state%radar_los%nyquist%source=SOURCE_RADAR_VRAD
    state%radar_los%sigma_vrad%source=SOURCE_RADAR_VRAD
    ALLOCATE(state%radar_los%beam(nx,ny,nz,nr,3), &
             state%radar_los%observation_id_hi(nx,ny,nz,nr), &
             state%radar_los%observation_id_lo(nx,ny,nz,nr), &
             state%radar_los%usage(nx,ny,nz,nr), &
             state%radar_los%los_support(nx,ny,nz,nr), &
             state%radar_los%radar_id(nr),state%radar_los%observation_time(nr), &
             state%radar_los%site_lat(nr),state%radar_los%site_lon(nr), &
             state%radar_los%site_height(nr),state%radar_los%wavelength(nr), &
             state%radar_los%geometry_condition(nx,ny,nz), &
             state%radar_los%geometry_rank(nx,ny,nz))
    state%radar_los%beam=0.0_real32; state%radar_los%beam(:,:,:,:,1)=1.0_real32
    state%radar_los%observation_id_hi=0_int64
    state%radar_los%observation_id_lo=0_int64
    state%radar_los%usage=LOS_HELD_OUT
    state%radar_los%los_support=1_int32
    state%radar_los%radar_id=100_int32
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      state%radar_los%observation_id_hi(i,j,k,1)=100_int64
      state%radar_los%observation_id_lo(i,j,k,1)=INT(i,int64)+INT(nx,int64)*( &
        INT(j-1,int64)+INT(ny,int64)*INT(k-1,int64))
    END DO; END DO; END DO
    state%radar_los%observation_time=valid_time
    state%radar_los%site_lat=36.0_real64; state%radar_los%site_lon=128.0_real64
    state%radar_los%site_height=100.0_real64; state%radar_los%wavelength=0.10_real64
    state%radar_los%geometry_condition=1.0_real32
    state%radar_los%geometry_rank=1_int32
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_OK,'complete post-QC LOS record must pass',failures)

    state%radar_los%observation_id_lo(1,1,1,1)= &
      state%radar_los%observation_id_lo(2,1,1,1)
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_RADAR_CONTRACT, &
               'non-unique canonical LOS identity must fail',failures)
    state%radar_los%observation_id_lo(1,1,1,1)=1_int64

    state%radar_los%vrad_representation=VRAD_FOLDED
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_FAILED, &
               'folded LOS data must fail the dealiased contract',failures)
    state%radar_los%vrad_representation=VRAD_DEALIASED

    state%radar_los%nyquist%source(1,1,1,1)=SOURCE_BACKGROUND_MODEL
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_RADAR_CONTRACT, &
               'Nyquist provenance must be radar LOS',failures)
    state%radar_los%nyquist%source(1,1,1,1)=SOURCE_RADAR_VRAD

    state%radar_los%nyquist%value(1,1,1,1)=-1.0_real32
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_RANGE, &
               'bad Nyquist metadata must fail LOS contract',failures)
  END SUBROUTINE test_los_contract

END PROGRAM test_canonical_state
