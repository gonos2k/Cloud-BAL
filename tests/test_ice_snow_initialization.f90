PROGRAM test_ice_snow_initialization
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  USE cloud_bal_microphysics_initialization
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: state,output,baseline,repeated
  TYPE(ice_snow_partition) :: proposal,saved
  TYPE(moment_bundle) :: prior,observed
  TYPE(microphysics_completion_policy) :: policy
  REAL(real32) :: density(1,1,2)
  INTEGER :: status,where(4)

  CALL initialize_cloud_bal_state(state,1,1,2,0_int64,'test',status)
  CALL check(status==STATUS_OK,'initialize')
  CALL fill(state%pressure,90000.0_real32)
  CALL fill(state%temperature,260.0_real32)
  CALL fill(state%vapor,0.01_real32)
  CALL fill(state%cloud_water,1.e-6_real32)
  CALL fill(state%cloud_ice,2.e-6_real32)
  CALL fill(state%rain,3.e-6_real32)
  CALL fill(state%snow,0.0_real32)
  CALL fill(state%graupel,4.e-6_real32)
  ALLOCATE(prior%value(1,1,2,5),prior%valid(1,1,2,5),prior%provenance(1,1,2,5))
  prior%valid=.TRUE.; prior%provenance=MOMENT_PRIOR
  prior%value(:,:,:,MOMENT_NC)=1.e-10_real64
  prior%value(:,:,:,MOMENT_NI)=2.e-10_real64
  prior%value(:,:,:,MOMENT_NR)=3.e-10_real64
  prior%value(:,:,:,MOMENT_NN)=55.0_real64
  prior%value(:,:,:,MOMENT_BG)=400.0_real64
  policy%source='test'; policy%density_source='test'
  policy%mass_threshold=1.e-12_real64
  policy%lower=1.e-11_real64; policy%upper=1.e-9_real64
  policy%lower(MOMENT_BG)=100.0_real64; policy%upper(MOMENT_BG)=900.0_real64
  policy%number_cap=1.e10_real64
  density=1.0_real32
  CALL complete_initialization_state(state,baseline,prior,policy,status,density)
  CALL check(status==STATUS_OK,'baseline')
  proposal%cloud_ice=state%cloud_ice; proposal%snow=state%snow
  proposal%ice_number=state%cloud_ice; proposal%ice_number%unit='kg-1 dryair'
  proposal%cloud_ice%valid=.FALSE.; proposal%snow%valid=.FALSE.; proposal%ice_number%valid=.FALSE.
  proposal%cloud_ice%valid(1,1,1)=.TRUE.; proposal%snow%valid(1,1,1)=.TRUE.
  proposal%ice_number%valid(1,1,1)=.TRUE.
  proposal%cloud_ice%value(1,1,1)=1.e-6_real32
  proposal%snow%value(1,1,1)=1.e-6_real32
  proposal%ice_number%value(1,1,1)=5000.0_real32
  proposal%source='independent test proposal'; proposal%provenance=MOMENT_BACKGROUND
  saved=proposal
  observed=prior
  observed%valid=.FALSE.
  observed%valid(1,1,1,MOMENT_NI)=.TRUE.; observed%value(1,1,1,MOMENT_NI)=7000.0_real64
  observed%valid(1,1,1,MOMENT_NN)=.TRUE.; observed%value(1,1,1,MOMENT_NN)=60.0_real64
  observed%provenance=MOMENT_OBSERVED
  CALL complete_ice_snow_initialization(baseline,repeated,proposal,prior,policy,status,density,observed=observed)
  CALL check(status==STATUS_OK .AND. repeated%moments%value(1,1,1,MOMENT_NI)==5000.0_real64 .AND. &
    repeated%moments%value(1,1,1,MOMENT_NN)==60.0_real64,'joint NI and other observed priority')
  CALL complete_ice_snow_initialization(baseline,output,proposal,prior,policy,status,density,where)
  CALL check(status==STATUS_OK,'joint proposal')
  CALL check(output%cloud_ice%value(1,1,1)==1.e-6_real32 .AND. &
    output%snow%value(1,1,1)==1.e-6_real32,'stored masses')
  CALL check(output%moments%value(1,1,1,MOMENT_NI)==5000.0_real64 .AND. &
    output%moments%provenance(1,1,1,MOMENT_NI)==MOMENT_BACKGROUND,'stored NI and provenance')
  CALL check(REAL(output%cloud_ice%value(1,1,1),real64)+REAL(output%snow%value(1,1,1),real64)== &
    REAL(baseline%cloud_ice%value(1,1,1),real64)+REAL(baseline%snow%value(1,1,1),real64), &
    'stored frozen water conservation')
  CALL check(ALL(output%temperature%value==baseline%temperature%value),'frozen enthalpy and temperature')
  CALL check(output%cloud_ice%value(1,1,2)==baseline%cloud_ice%value(1,1,2) .AND. &
    output%snow%value(1,1,2)==baseline%snow%value(1,1,2) .AND. &
    output%moments%value(1,1,2,MOMENT_NI)==baseline%moments%value(1,1,2,MOMENT_NI),'off mask')
  CALL complete_ice_snow_initialization(output,repeated,proposal,prior,policy,status,density)
  CALL check(status==STATUS_OK .AND. ALL(repeated%moments%value==output%moments%value) .AND. &
    ALL(repeated%cloud_ice%value==output%cloud_ice%value),'idempotence')
  proposal%ice_number%value(1,1,1)=1.e20_real32
  CALL reject('invalid NI')
  proposal=saved; proposal%snow%value(1,1,1)=2.e-6_real32
  CALL reject('mass creation')
  proposal=saved; proposal%provenance=MOMENT_ZERO
  CALL reject('unsupported provenance')
  proposal=saved; proposal%source=''
  CALL reject('missing source')
  proposal=saved; proposal%cloud_ice%source(1,1,1)=0
  CALL reject('missing cell source')
  proposal=saved; proposal%ice_number%valid(1,1,1)=.FALSE.
  CALL reject('missing NI')
  proposal=saved; proposal%ice_number%value(1,1,1)=ieee_value(0.0_real32,ieee_quiet_nan)
  CALL reject('NaN NI')
  proposal=saved
  proposal%cloud_ice%valid=.TRUE.; proposal%snow%valid=.TRUE.; proposal%ice_number%valid=.TRUE.
  proposal%cloud_ice%value(1,1,2)=1.e-6_real32; proposal%snow%value(1,1,2)=1.e-6_real32
  proposal%ice_number%value(1,1,2)=1.e20_real32
  CALL reject('second cell atomic rollback')
  CALL check(ALL(where==[1,1,2,MOMENT_NI]),'failure location')
  PRINT *, 'ice snow initialization: PASS'
CONTAINS
  SUBROUTINE fill(field,value)
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: value
    field%value=value; field%valid=.TRUE.; field%quality=0; field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE
  SUBROUTINE check(condition,label)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(*), INTENT(IN) :: label
    IF (.NOT.condition) THEN
      PRINT *, 'FAIL: ',label
      ERROR STOP 1
    END IF
  END SUBROUTINE
  SUBROUTINE reject(label)
    CHARACTER(*), INTENT(IN) :: label
    repeated=output
    CALL complete_ice_snow_initialization(baseline,repeated,proposal,prior,policy,status,density,where)
    CALL check(status==STATUS_FAILED,label)
    CALL check(ALL(repeated%cloud_ice%value==output%cloud_ice%value) .AND. &
      ALL(repeated%snow%value==output%snow%value) .AND. &
      ALL(repeated%moments%value==output%moments%value),'rollback')
  END SUBROUTINE
END PROGRAM
