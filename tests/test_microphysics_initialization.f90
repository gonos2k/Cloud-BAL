PROGRAM test_microphysics_initialization
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32, real64, int32, int64
  USE cloud_bal_state
  USE cloud_bal_microphysics_initialization
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: state, output, background
  TYPE(moment_bundle) :: prior, before, observed, absent, partial
  TYPE(microphysics_completion_policy) :: policy
  REAL(real32) :: density(1,1,2)
  INTEGER :: status, failed_location(4)

  CALL initialize_cloud_bal_state(state,1,1,2,0_int64,'test',status)
  IF (status/=STATUS_OK) ERROR STOP 'initialize'
  CALL mass(state%pressure,90000.0_real32)
  CALL mass(state%temperature,280.0_real32)
  CALL mass(state%vapor,0.01_real32)
  CALL mass(state%snow,0.0_real32)
  CALL mass(state%cloud_water,1.e-6_real32)
  CALL mass(state%cloud_ice,2.e-6_real32)
  CALL mass(state%rain,3.e-6_real32)
  CALL mass(state%graupel,4.e-6_real32)
  CALL allocate_bundle(prior)
  CALL allocate_bundle(observed)
  prior%valid=.TRUE.
  prior%provenance=MOMENT_PRIOR
  prior%value(:,:,:,MOMENT_NC)=1.e-10_real64
  prior%value(:,:,:,MOMENT_NI)=2.e-10_real64
  prior%value(:,:,:,MOMENT_NR)=3.e-10_real64
  prior%value(:,:,:,MOMENT_NN)=55.0_real64
  prior%value(:,:,:,MOMENT_BG)=400.0_real64
  policy%source='test source'; policy%density_source='test dry density'
  policy%mass_threshold=1.e-12_real64
  policy%lower=1.e-11_real64; policy%upper=1.e-9_real64
  policy%lower(MOMENT_BG)=100.0_real64; policy%upper(MOMENT_BG)=900.0_real64
  policy%number_cap=1.e10_real64
  density=1.0_real32
  output=state
  CALL complete_initialization_state(state,output,prior,policy,status,density)
  CALL check(status==STATUS_OK,'prior completion')
  CALL check(ALL(output%moments%valid),'completed fields')
  CALL check(ALL(output%moments%provenance==MOMENT_PRIOR),'prior provenance')
  CALL check(output%moments%value(1,1,1,MOMENT_NN)==55.0_real64,'NN has explicit value')
  CALL check(ALL(output%cloud_water%value==state%cloud_water%value),'water unchanged')
  CALL check(ALL(output%temperature%value==state%temperature%value),'temperature unchanged')
  CALL check(ALL(output%pressure%value==state%pressure%value),'pressure unchanged')
  CALL check(.NOT.moment_bundle_present(state%moments),'default input moments absent')
  background=output
  before=output%moments
  CALL complete_initialization_state(background,output,absent,policy,status,density,absent,failed_location)
  CALL check(status==STATUS_OK,'absent prior and observed with valid background')
  CALL check(ALL(failed_location==0),'success clears failure location')
  CALL check(moment_bundles_equal(output%moments,before),'background preserved exactly')
  ALLOCATE(partial%value(1,1,2,5))
  failed_location=9
  CALL complete_initialization_state(background,output,partial,policy,status,density,failed_location=failed_location)
  CALL check(status==STATUS_FAILED,'partial prior rejected')
  CALL check(ALL(failed_location==0),'structural failure has no location')
  CALL check(moment_bundles_equal(output%moments,before),'partial prior rollback')
  CALL complete_initialization_state(background,output,prior,policy,status,density,partial)
  CALL check(status==STATUS_FAILED,'partial observed rejected')
  CALL check(moment_bundles_equal(output%moments,before),'partial observed rollback')
  CALL complete_initialization_state(state,output,absent,policy,status,density,failed_location=failed_location)
  CALL check(status==STATUS_FAILED,'absent background and prior need explicit prior')
  CALL check(ALL(failed_location==[1,1,1,MOMENT_NC]),'failure identifies missing cell and slot')
  CALL check(moment_bundles_equal(output%moments,before),'absent prior failure rollback')

  DEALLOCATE(background%moments%valid)
  CALL complete_initialization_state(background,output,prior,policy,status,density)
  CALL check(status==STATUS_FAILED,'partial background rejected')
  CALL check(moment_bundles_equal(output%moments,before),'partial background rollback')

  ! The canonical wrapper requires the whole analyzed thermal/water state.
  state%temperature%valid(1,1,1)=.FALSE.
  before=output%moments
  CALL complete_initialization_state(state,output,prior,policy,status,density)
  CALL check(status==STATUS_FAILED,'missing temperature rejected')
  CALL check(ALL(output%moments%value==before%value),'state wrapper rollback')
  state%temperature%valid=.TRUE.
  state%snow%valid_time=1_int64
  CALL complete_initialization_state(state,output,prior,policy,status,density)
  CALL check(status==STATUS_FAILED,'snow time mismatch rejected')
  state%snow%valid_time=0_int64

  before=output%moments
  CALL complete_microphysics(state,output%moments,prior,policy,status,density)
  CALL check(status==STATUS_OK,'repeat completion')
  CALL check(ALL(output%moments%value==before%value),'idempotent values')
  CALL check(ALL(output%moments%provenance==before%provenance),'idempotent provenance')
  prior%value(1,1,1,MOMENT_NN)=-1.0_real64
  CALL complete_microphysics(state,output%moments,prior,policy,status,density)
  CALL check(status==STATUS_OK,'unused invalid prior ignored')
  prior%value(1,1,1,MOMENT_NN)=55.0_real64

  ! An inadmissible observation falls back to the admissible background.
  output%moments%provenance=MOMENT_BACKGROUND
  observed%valid(1,1,1,MOMENT_NC)=.TRUE.
  observed%provenance(1,1,1,MOMENT_NC)=MOMENT_OBSERVED
  observed%value(1,1,1,MOMENT_NC)=1.0_real64
  before=output%moments
  CALL complete_microphysics(state,output%moments,prior,policy,status,density,observed)
  CALL check(status==STATUS_OK,'inadmissible observation fallback')
  CALL check(output%moments%value(1,1,1,MOMENT_NC)==before%value(1,1,1,MOMENT_NC), &
    'preserve admissible background')
  observed%value(1,1,1,MOMENT_NC)=before%value(1,1,1,MOMENT_NC)*2.0_real64
  CALL complete_microphysics(state,output%moments,prior,policy,status,density,observed)
  CALL check(status==STATUS_OK,'admissible observation')
  CALL check(output%moments%provenance(1,1,1,MOMENT_NC)==MOMENT_OBSERVED,'observed priority')
  ! A missing significant moment requires a declared prior, atomically.
  output%moments%valid(1,1,2,MOMENT_NN)=.FALSE.
  prior%valid(1,1,2,MOMENT_NN)=.FALSE.
  before=output%moments
  CALL complete_microphysics(state,output%moments,prior,policy,status,density)
  CALL check(status==STATUS_FAILED,'missing NN rejected')
  CALL check(ALL(output%moments%value==before%value) .AND. &
    ALL(output%moments%valid .EQV. before%valid),'failure atomic')
  prior%valid(1,1,2,MOMENT_NN)=.TRUE.
  density=0.0_real32
  CALL complete_microphysics(state,output%moments,prior,policy,status,density)
  CALL check(status==STATUS_FAILED,'density required')
  density=1.0_real32
  prior%value(1,1,2,MOMENT_NN)=-1.0_real64
  CALL complete_microphysics(state,output%moments,prior,policy,status,density)
  CALL check(status==STATUS_FAILED,'invalid prior rejected')
  ! Native caps apply to rounded REAL32 numbers, including NN; no floor is added.
  prior%value(1,1,2,MOMENT_NN)=55.0_real64
  policy%number_cap(MOMENT_NN)=54.0_real64
  CALL complete_microphysics(state,output%moments,prior,policy,status,density)
  CALL check(status==STATUS_FAILED,'NN native cap rejected')
  CALL check(ALL(output%moments%value==before%value),'cap failure atomic')
  policy%number_cap(MOMENT_NN)=1.e10_real64
  prior%value(1,1,2,MOMENT_NN)=0.0_real64
  CALL complete_microphysics(state,output%moments,prior,policy,status,density)
  CALL check(status==STATUS_OK,'explicit zero NN accepted')
  CALL check(output%moments%value(1,1,2,MOMENT_NN)==0.0_real64,'no NN floor')
  ! A subthreshold positive mass stays unresolved when no prior is supplied.
  CALL mass(state%cloud_water,1.e-13_real32)
  output%moments%valid(:,:,:,MOMENT_NC)=.FALSE.
  prior%valid(:,:,:,MOMENT_NC)=.FALSE.
  failed_location=9
  CALL complete_microphysics(state,output%moments,prior,policy,status,density,failed_location=failed_location)
  CALL check(status==STATUS_DEGRADED,'subthreshold mass remains unresolved')
  CALL check(ALL(failed_location==0),'degraded completion clears failure location')
  CALL check(.NOT.ANY(output%moments%valid(:,:,:,MOMENT_NC)),'no fabricated zero')
  ! The policy threshold is inclusive.
  policy%mass_threshold(MOMENT_NC)=REAL(state%cloud_water%value(1,1,1),real64)
  before=output%moments
  CALL complete_microphysics(state,output%moments,prior,policy,status,density)
  CALL check(status==STATUS_FAILED,'threshold equality requires prior')
  CALL check(ALL(output%moments%valid .EQV. before%valid),'threshold failure atomic')
  CALL mass(state%cloud_water,0.0_real32)
  CALL complete_microphysics(state,output%moments,prior,policy,status,density)
  CALL check(status==STATUS_OK,'known zero mass')
  CALL check(ALL(output%moments%value(:,:,:,MOMENT_NC)==0.0_real64) .AND. &
    ALL(output%moments%provenance(:,:,:,MOMENT_NC)==MOMENT_ZERO),'zero provenance')
  ! The PSD bound must use the REAL32 value that the native model receives.
  CALL mass(state%cloud_water,1.e-6_real32)
  output%moments%valid(:,:,:,MOMENT_NC)=.TRUE.
  output%moments%value(:,:,:,MOMENT_NC)=1.0_real64-1.e-9_real64
  output%moments%provenance(:,:,:,MOMENT_NC)=MOMENT_BACKGROUND
  policy%mass_threshold(MOMENT_NC)=0.0_real64
  policy%lower(MOMENT_NC)=REAL(state%cloud_water%value(1,1,1),real64)*(1.0_real64+5.e-10_real64)
  policy%upper(MOMENT_NC)=2.0_real64*policy%lower(MOMENT_NC)
  before=output%moments
  CALL complete_microphysics(state,output%moments,prior,policy,status,density)
  CALL check(status==STATUS_FAILED,'native rounded value violates PSD bound')
  CALL check(ALL(output%moments%value==before%value),'rounding failure atomic')
  PRINT *, 'microphysics initialization tests passed'
CONTAINS
  SUBROUTINE check(condition,label)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(*), INTENT(IN) :: label
    IF (.NOT.condition) THEN
      PRINT *, 'FAIL: ',label
      ERROR STOP 1
    END IF
  END SUBROUTINE
  SUBROUTINE mass(field,value)
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: value
    field%value=value; field%valid=.TRUE.; field%quality=0_int32
    field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE
  SUBROUTINE allocate_bundle(bundle)
    TYPE(moment_bundle), INTENT(INOUT) :: bundle
    ALLOCATE(bundle%value(1,1,2,5),bundle%valid(1,1,2,5),bundle%provenance(1,1,2,5))
    bundle%value=0.0_real64; bundle%valid=.FALSE.; bundle%provenance=0
  END SUBROUTINE
END PROGRAM
