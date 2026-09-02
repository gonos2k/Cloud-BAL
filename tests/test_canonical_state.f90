PROGRAM test_canonical_state
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  IMPLICIT NONE

  INTEGER :: failures
  failures=0
  CALL test_contract(failures)
  CALL test_domain_and_mass_contract(failures)
  CALL test_pressure_cell_geometry(failures)
  CALL test_vertical_conversion(failures)
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
