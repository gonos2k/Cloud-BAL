PROGRAM test_column_physics
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_column_physics
  IMPLICIT NONE
  INTEGER :: failures

  failures=0
  CALL test_layers(failures)
  CALL test_phase_and_thermodynamics(failures)
  CALL test_flux_ledgers(failures)
  CALL test_column_stage(failures)
  IF (failures/=0) THEN
    PRINT *,'Column physics tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Column physics tests passed'

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

  SUBROUTINE make_state(state,nx,ny,nz)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER :: i,j,k,status
    INTEGER(int64), PARAMETER :: valid_time=1788224400_int64
    CALL initialize_cloud_bal_state(state,nx,ny,nz,valid_time,'column-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state init'
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      state%grid%dx(i,j)=2000.0_real64
      state%grid%dy(i,j)=2200.0_real64
      state%grid%dp(i,j,k)=15000.0_real64
      state%grid%cell_measure(i,j,k)=state%grid%dx(i,j)*state%grid%dy(i,j)* &
                                      state%grid%dp(i,j,k)/9.80665_real64
      state%pressure%value(i,j,k)=REAL(95000-15000*(k-1),real32)
      state%temperature%value(i,j,k)=280.0_real32
      state%vapor%value(i,j,k)=0.008_real32
      state%u%value(i,j,k)=0.0_real32
      state%v%value(i,j,k)=0.0_real32
      state%omega%value(i,j,k)=0.0_real32
      state%cloud_fraction%value(i,j,k)=0.0_real32
      state%cloud_type%value(i,j,k)=0_int32
    END DO; END DO; END DO
    CALL valid_real(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%u,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%v,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_fraction,SOURCE_CLOUD_ANALYSIS)
    state%cloud_type%valid=.TRUE.; state%cloud_type%quality=0
    state%cloud_type%source=SOURCE_CLOUD_ANALYSIS
    state%surface_pressure%value=100000.0_real32
    state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0; state%surface_temperature%quality=0
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE make_state

  SUBROUTINE valid_real(field,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0; field%source=source
  END SUBROUTINE valid_real

  SUBROUTINE test_layers(failures)
    INTEGER, INTENT(INOUT) :: failures
    INTEGER(int32) :: cloud_type(7)
    INTEGER :: phase(7)
    REAL(real32) :: fraction(7)
    LOGICAL :: valid(7)
    INTEGER :: nlayers,bottom(7),top(7),regime(7),status
    cloud_type=(/1,1,3,3,0,4,4/)
    fraction=0.8_real32; valid=.TRUE.
    CALL detect_cloud_sublayers(cloud_type,fraction,valid,0.01_real64,7, &
                                nlayers,bottom,top,regime,status)
    CALL check(status==STATUS_OK .AND. nlayers==3, &
               'regime changes must split connected cloud',failures)
    CALL check(bottom(3)==6 .AND. top(3)==7, &
               'top-boundary layer must close',failures)
    fraction(3:4)=0.0_real32
    CALL detect_cloud_sublayers(cloud_type,fraction,valid,0.01_real64,7, &
                                nlayers,bottom,top,regime,status)
    CALL check(nlayers==2,'zero cloud fraction cannot create an updraft layer',failures)
    fraction=0.8_real32; phase=PHASE_RAIN; phase(4:7)=PHASE_SNOW
    CALL detect_cloud_sublayers(cloud_type,fraction,valid,0.01_real64,7, &
                                nlayers,bottom,top,regime,status,phase)
    CALL check(status==STATUS_OK .AND. nlayers==4, &
               'accepted precipitation-phase changes must split sublayers',failures)
  END SUBROUTINE test_layers

  SUBROUTINE test_phase_and_thermodynamics(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: rain,snow,graupel,total,t,rv,qc,qi,water0,enthalpy0
    INTEGER :: status
    total=0.004_real64
    CALL allocate_precipitation_phase(total,270.0_real64,PHASE_UNKNOWN, &
                                      rain,snow,graupel,status)
    CALL check(status==STATUS_OK .AND. ABS(rain+snow+graupel-total)<1.0e-14_real64, &
               'mixed-phase allocation must close exactly',failures)
    CALL allocate_precipitation_phase(total,270.0_real64,9,rain,snow,graupel,status)
    CALL check(status==STATUS_FAILED,'invalid phase must not coerce to unknown',failures)

    t=280.0_real64; rv=0.002_real64; qc=0.004_real64; qi=0.001_real64
    water0=rv+qc+qi; enthalpy0=moist_enthalpy(t,rv,qi)
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,0.90_real64,status)
    CALL check(status==STATUS_OK,'bounded saturation adjustment',failures)
    CALL check(ABS((rv+qc+qi)-water0)<2.0e-13_real64, &
               'dry-air total water must close',failures)
    CALL check(ABS(moist_enthalpy(t,rv,qi)-enthalpy0)<2.0e-7_real64, &
               'moist enthalpy must close',failures)
    CALL check(t<280.0_real64,'evaporation/sublimation must cool temperature',failures)
    CALL check(dry_air_density(85000.0_real64,280.0_real64,0.01_real64)>0.0_real64, &
               'dry-air density must be physical',failures)
  END SUBROUTINE test_phase_and_thermodynamics

  SUBROUTINE test_flux_ledgers(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(grid_spec) :: grid
    TYPE(column_physics_config) :: cfg
    TYPE(precipitation_flux_ledger) :: ledger
    REAL(real32) :: p(4,4,3),t(4,4,3),qv(4,4,3),u(4,4,3),v(4,4,3),w(4,4,3)
    LOGICAL :: wvalid(4,4,3),observed(4,4,3)
    INTEGER :: phase(4,4,3),status,k
    REAL(real64) :: z(4,4,3),rain(4,4,3),snow(4,4,3),graupel(4,4,3)

    grid%nx=4; grid%ny=4; grid%nz=3; grid%grid_id='transport-test'
    ALLOCATE(grid%dx(4,4),grid%dy(4,4),grid%dp(4,4,3),grid%cell_measure(4,4,3))
    grid%dx=2000.0_real64; grid%dy=2000.0_real64; grid%dp=15000.0_real64
    grid%cell_measure=SPREAD(grid%dx*grid%dy,3,3)*grid%dp/9.80665_real64
    DO k=1,3; p(:,:,k)=REAL(95000-15000*(k-1),real32); END DO
    t=280.0_real32; qv=0.008_real32; u=0.0_real32; v=0.0_real32
    w=0.0_real32; wvalid=.TRUE.; observed=.FALSE.; phase=PHASE_UNKNOWN
    z=0.0_real64; rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64
    observed(2,2,3)=.TRUE.; observed(2,2,2)=.TRUE.
    phase(2,2,3)=PHASE_RAIN; z(2,2,3)=1000.0_real64; rain(2,2,3)=1.0e-4_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg), &
               'blocked-destination flux ledger must close',failures)
    CALL check(ledger%observation_blocked>0.0_real64, &
               'observed destination must be an explicit ledger term',failures)

    observed=.FALSE.; phase=PHASE_UNKNOWN; z=0.0_real64
    rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64
    observed(4,2,3)=.TRUE.; phase(4,2,3)=PHASE_RAIN
    z(4,2,3)=1000.0_real64; rain(4,2,3)=1.0e-4_real64; u=20.0_real32
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg), &
               'domain-exit flux ledger must close',failures)
    CALL check(ledger%boundary_exit>0.0_real64, &
               'domain-exit flux must not disappear',failures)

    observed=.FALSE.; phase=PHASE_UNKNOWN; z=0.0_real64
    rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64; u=0.0_real32
    observed(2,2,3)=.TRUE.; phase(2,2,3)=PHASE_RAIN
    z(2,2,3)=1000.0_real64; rain(2,2,3)=1.0e-4_real64
    w=20.0_real32
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg) .AND. &
               ABS(rain(2,2,2))<=TINY(1.0_real64), &
               'ascent faster than fall speed must not force downward crossing',failures)

    w=-10.0_real32
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg), &
               'strong downdraft relative-flux ledger must close',failures)
  END SUBROUTINE test_flux_ledgers

  SUBROUTINE test_column_stage(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output,repeat_output
    TYPE(stage_result) :: result,repeat_result
    TYPE(column_physics_config) :: cfg
    INTEGER(int32), ALLOCATABLE :: before_bits(:),after_bits(:)

    CALL make_state(input,4,4,4)
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. .NOT.ANY(result%changed), &
               'clear radar-absent state must be exact no-op',failures)

    input%cloud_fraction%value(2,2,:)=0.8_real32
    input%cloud_type%value(2,2,:)=(/1_int32,3_int32,3_int32,1_int32/)
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_OK,'cloud-only column stage',failures)
    CALL check(.NOT.ANY(output%omega_target%valid(2,2,:)), &
               'cloud type alone must not fabricate a mean vertical velocity',failures)
    CALL check(output%obs_support(2,2,2)==1_int32, &
               'cloud analysis still supplies local support',failures)

    CALL make_state(input,4,4,4)
    input%cloud_type%value(2,2,2)=3_int32
    input%cloud_fraction%value(2,2,2)=0.0_real32
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_DEGRADED .AND. .NOT.ANY(result%changed), &
               'cloud type with zero fraction must be rejected as contradictory',failures)

    CALL make_state(input,4,4,4)
    input%cloud_type%value(2,2,2)=99_int32
    input%cloud_fraction%value(2,2,2)=0.8_real32
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_RANGE, &
               'unknown cloud type code must be rejected',failures)

    CALL make_state(input,4,4,4)
    input%radar_reflectivity%valid(2,2,4)=.TRUE.
    input%radar_reflectivity%quality(2,2,4)=0
    input%radar_reflectivity%source(2,2,4)=SOURCE_RADAR_DBZ
    input%radar_reflectivity%value(2,2,4)=30.0_real32
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
               result%numerical%flux_input>0.0_real64, &
               'S-band radar precipitation must create a closed shaft',failures)
    CALL check(result%numerical%ledger_error<=cfg%ledger_absolute_tolerance+ &
               cfg%ledger_relative_tolerance*result%numerical%flux_input, &
               'published radar ledger closure',failures)
    CALL derive_column_physics(input,repeat_output,repeat_result,cfg)
    before_bits=TRANSFER(output%rain%value,[0_int32],SIZE(output%rain%value))
    after_bits=TRANSFER(repeat_output%rain%value,[0_int32],SIZE(repeat_output%rain%value))
    CALL check(ALL(before_bits==after_bits),'radar transport must be deterministic',failures)

    input%omega%valid(2,2,4)=.FALSE.
    input%omega%quality(2,2,4)=QUALITY_RAW_MISSING
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_DEGRADED .AND. .NOT.ANY(result%changed), &
               'missing omega must reject trajectory unchanged',failures)

    CALL make_state(input,4,4,4)
    input%radar_reflectivity%valid(2,2,4)=.TRUE.
    input%radar_reflectivity%quality(2,2,4)=0
    input%radar_reflectivity%source(2,2,4)=SOURCE_RADAR_DBZ
    input%radar_reflectivity%value(2,2,4)=90.0_real32
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_RANGE, &
               'valid out-of-range dBZ must fail, not become absent',failures)

    CALL make_state(input,4,4,4)
    input%radar_reflectivity%valid(2,2,4)=.TRUE.
    input%radar_reflectivity%quality(2,2,4)=0
    input%radar_reflectivity%source(2,2,4)=SOURCE_RADAR_DBZ
    input%radar_reflectivity%value(2,2,4)=30.0_real32
    input%precipitation_phase%valid(2,2,4)=.TRUE.
    input%precipitation_phase%quality(2,2,4)=0
    input%precipitation_phase%source(2,2,4)=SOURCE_CLOUD_ANALYSIS
    input%precipitation_phase%value(2,2,4)=9_int32
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. .NOT.ANY(result%changed), &
               'invalid precipitation phase must reject unchanged',failures)

    input%precipitation_phase%value(2,2,4)=PHASE_UNKNOWN
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
      IAND(output%precipitation_phase%quality(2,2,4), &
           QUALITY_PHASE_UNCERTAIN)/=0_int32, &
      'explicit unknown phase must remain marked uncertain',failures)

    input%precipitation_phase%value(2,2,4)=PHASE_RAIN
    input%rain%unit='kg m-3'
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_METADATA, &
               'mixed hydrometeor mass bases must fail metadata contract',failures)

    CALL make_state(input,4,4,4)
    input%radar_reflectivity%valid(2,2,4)=.TRUE.
    input%radar_reflectivity%quality(2,2,4)=0
    input%radar_reflectivity%source(2,2,4)=SOURCE_RADAR_DBZ
    input%radar_reflectivity%value(2,2,4)=40.0_real32
    input%cloud_fraction%value(2,2,4)=0.8_real32
    input%cloud_type%value(2,2,4)=11_int32
    input%omega%value(2,2,4)=-1.0_real32
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
               .NOT.output%omega_target%valid(2,2,4), &
               'type 11 observed updraft must be protected from loading downdraft',failures)

    CALL make_state(input,4,4,4)
    input%omega%source=IOR(input%omega%source,SOURCE_BALANCE_OPERATOR)
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY, &
      'a balance candidate without observations must not be reused as background',failures)

    CALL make_state(input,4,4,4)
    DEALLOCATE(input%rain%source)
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_METADATA, &
      'an unallocated hydrometeor source mask must reject unchanged',failures)

    CALL make_state(input,4,4,4)
    DEALLOCATE(input%vt_z_mean%source)
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_METADATA, &
      'an unallocated fall-speed source mask must reject unchanged',failures)

    CALL test_radar_background_isolation(failures)
  END SUBROUTINE test_column_stage

  SUBROUTINE test_radar_background_isolation(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output,repeated,updated,fresh
    TYPE(stage_result) :: result,repeat_result,updated_result,fresh_result
    TYPE(column_physics_config) :: cfg
    INTEGER(int32) :: far_bits

    CALL make_state(input,4,4,4)
    input%rain%value(4,4,2)=2.0e-4_real32
    input%rain%valid(4,4,2)=.TRUE.
    input%rain%quality(4,4,2)=QUALITY_LEGACY_PROVENANCE
    input%rain%source(4,4,2)=SOURCE_BACKGROUND_MODEL
    far_bits=TRANSFER(input%rain%value(4,4,2),far_bits)
    input%rain%value(2,2,3)=3.0e-4_real32
    input%rain%valid(2,2,3)=.TRUE.
    input%rain%source(2,2,3)=SOURCE_BACKGROUND_MODEL
    input%rain%value(2,2,4)=7.0e-4_real32
    input%rain%valid(2,2,4)=.TRUE.
    input%rain%quality(2,2,4)=QUALITY_LEGACY_PROVENANCE
    input%rain%source(2,2,4)=SOURCE_BACKGROUND_MODEL
    input%radar_reflectivity%valid(2,2,4)=.TRUE.
    input%radar_reflectivity%quality(2,2,4)=0_int32
    input%radar_reflectivity%source(2,2,4)=SOURCE_RADAR_DBZ
    input%radar_reflectivity%value(2,2,4)=30.0_real32
    fresh=input
    fresh%rain%value(2,2,4)=0.0_real32
    fresh%rain%valid(2,2,4)=.FALSE.
    fresh%rain%quality(2,2,4)=0_int32
    fresh%rain%source(2,2,4)=0_int32
    CALL derive_column_physics(fresh,repeated,repeat_result,cfg)
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_OK,'isolated radar reconstruction',failures)
    CALL check(TRANSFER(output%rain%value(2,2,4),far_bits)== &
               TRANSFER(repeated%rain%value(2,2,4),far_bits) .AND. &
               IAND(output%rain%source(2,2,4),SOURCE_BACKGROUND_MODEL)==0_int32, &
      'observed echo must replace, not add, background precipitation',failures)
    CALL check(TRANSFER(output%rain%value(4,4,2),far_bits)==far_bits .AND. &
      output%rain%valid(4,4,2) .AND. &
      output%rain%quality(4,4,2)==QUALITY_LEGACY_PROVENANCE .AND. &
      output%rain%source(4,4,2)==SOURCE_BACKGROUND_MODEL, &
      'radar must not transport or relabel remote background precipitation',failures)
    CALL check(.NOT.output%rain%valid(1,1,1), &
      'unmodified invalid hydrometeor must not become valid zero',failures)
    CALL check(output%rain%valid(2,2,3) .AND. &
      output%rain%value(2,2,3)>input%rain%value(2,2,3) .AND. &
      IAND(output%rain%source(2,2,3),SOURCE_RADAR_DBZ)/=0_int32 .AND. &
      IAND(output%rain%quality(2,2,3),QUALITY_PHASE_UNCERTAIN)/=0_int32, &
      'radar shaft must add to overlapping pristine background',failures)
    updated=output
    updated%radar_reflectivity%valid=.FALSE.
    CALL derive_column_physics(updated,repeated,updated_result,cfg)
    CALL check(updated_result%status==STATUS_FAILED .AND. &
      updated_result%reason_code==REASON_AUTHORITY, &
      'a radar candidate without observations must not pass as background',failures)
    CALL derive_column_physics(output,repeated,repeat_result,cfg)
    CALL check(repeat_result%status==STATUS_FAILED .AND. &
      repeat_result%reason_code==REASON_AUTHORITY .AND. &
      ALL(TRANSFER(repeated%rain%value,[0_int32],SIZE(repeated%rain%value))== &
          TRANSFER(output%rain%value,[0_int32],SIZE(output%rain%value))) .AND. &
      ALL(repeated%rain%valid.EQV.output%rain%valid) .AND. &
      ALL(repeated%rain%quality==output%rain%quality) .AND. &
      ALL(repeated%rain%source==output%rain%source), &
      'a prior column candidate must not be reused as background',failures)

    updated=input
    updated%radar_reflectivity%value(2,2,4)=35.0_real32
    CALL derive_column_physics(updated,repeated,updated_result,cfg)
    fresh=input
    fresh%radar_reflectivity%value(2,2,4)=35.0_real32
    CALL derive_column_physics(fresh,output,fresh_result,cfg)
    CALL check(updated_result%status==STATUS_OK .AND. fresh_result%status==STATUS_OK .AND. &
      ALL(TRANSFER(repeated%rain%value,[0_int32],SIZE(repeated%rain%value))== &
          TRANSFER(output%rain%value,[0_int32],SIZE(output%rain%value))), &
      'changed radar evidence must be recomputed from pristine background',failures)
  END SUBROUTINE test_radar_background_isolation

END PROGRAM test_column_physics
