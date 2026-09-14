PROGRAM test_column_physics
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan,ieee_positive_inf
  USE cloud_bal_state
  USE cloud_bal_column_physics
  IMPLICIT NONE
  INTEGER :: failures

  failures=0
  CALL test_layers(failures)
  CALL test_phase_and_thermodynamics(failures)
  CALL test_thermo_interior_root(failures)
  CALL test_thermo_rejection_and_exhaustion(failures)
  CALL test_thermo_primary_reservoir(failures)
  CALL test_explicit_surface_policy(failures)
  CALL test_flux_ledgers(failures)
  CALL test_column_stage(failures)
  CALL test_column_thermo_integration(failures)
  CALL test_column_evaluation_state(failures)
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

  PURE REAL(real64) FUNCTION mixture_cp(vapor,liquid,ice)
    REAL(real64), INTENT(IN) :: vapor,liquid,ice
    mixture_cp=1004.5_real64+1846.4_real64*vapor+4190.0_real64*liquid+ &
      2106.0_real64*ice
  END FUNCTION mixture_cp

  PURE REAL(real64) FUNCTION mixture_enthalpy(temperature,vapor,liquid,ice)
    REAL(real64), INTENT(IN) :: temperature,vapor,liquid,ice
    mixture_enthalpy=mixture_cp(vapor,liquid,ice)*(temperature-273.15_real64)+ &
      2.5e6_real64*vapor-3.5e5_real64*ice
  END FUNCTION mixture_enthalpy

  PURE REAL(real64) FUNCTION temperature_for_final_state(final_temperature, &
      final_vapor,final_liquid,final_ice,initial_vapor,initial_liquid,initial_ice)
    REAL(real64), INTENT(IN) :: final_temperature,final_vapor,final_liquid,final_ice
    REAL(real64), INTENT(IN) :: initial_vapor,initial_liquid,initial_ice
    REAL(real64) :: target_enthalpy,initial_species_enthalpy
    target_enthalpy=mixture_enthalpy(final_temperature,final_vapor,final_liquid,final_ice)
    initial_species_enthalpy=mixture_enthalpy(273.15_real64,initial_vapor, &
      initial_liquid,initial_ice)
    temperature_for_final_state=273.15_real64+(target_enthalpy-initial_species_enthalpy)/ &
      mixture_cp(initial_vapor,initial_liquid,initial_ice)
  END FUNCTION temperature_for_final_state

  PURE REAL(real64) FUNCTION phase_enthalpy_change(initial_temperature,dv,dl,di)
    REAL(real64), INTENT(IN) :: initial_temperature,dv,dl,di
    REAL(real64) :: tc
    tc=initial_temperature-273.15_real64
    phase_enthalpy_change=dv*(2.5e6_real64+1846.4_real64*tc)+ &
      dl*(4190.0_real64*tc)+di*(-3.5e5_real64+2106.0_real64*tc)
  END FUNCTION phase_enthalpy_change

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
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure geometry initialization failed'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'dry-air mass initialization failed'
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
    REAL(real64) :: t0,rv0,qc0,qi0
    INTEGER :: status
    total=0.004_real64
    CALL allocate_precipitation_phase(total,270.0_real64,PHASE_UNKNOWN, &
                                      rain,snow,graupel,status)
    CALL check(status==STATUS_OK .AND. ABS(rain+snow+graupel-total)<1.0e-14_real64, &
               'mixed-phase allocation must close exactly',failures)
    total=terminal_velocity(PHASE_RAIN,MIN_PRESSURE_PA,280.0_real64,20.0_real64,status)
    CALL check(status==STATUS_OK .AND. total>0.0_real64, &
               'canonical minimum pressure must be accepted consistently',failures)
    total=terminal_velocity(PHASE_RAIN,MIN_PRESSURE_PA-1.0_real64, &
                            280.0_real64,20.0_real64,status)
    CALL check(status==STATUS_FAILED, &
               'pressure below the canonical minimum must fail',failures)
    CALL allocate_precipitation_phase(total,270.0_real64,9,rain,snow,graupel,status)
    CALL check(status==STATUS_FAILED,'invalid phase must not coerce to unknown',failures)

    t=280.0_real64; rv=0.002_real64; qc=0.004_real64; qi=0.001_real64
    water0=rv+qc+qi; enthalpy0=mixture_enthalpy(t,rv,qc,qi)
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,0.90_real64,status,SATURATION_LIQUID)
    CALL check(status==STATUS_OK,'bounded saturation adjustment',failures)
    CALL check(ABS((rv+qc+qi)-water0)<2.0e-13_real64, &
               'dry-air total water must close',failures)
    CALL check(ABS(mixture_enthalpy(t,rv,qc,qi)-enthalpy0)<2.0e-7_real64, &
               'mixture enthalpy must close',failures)
    CALL check(t<280.0_real64,'evaporation/sublimation must cool temperature',failures)

    t=280.0_real64; rv=0.020_real64; qc=0.0_real64; qi=0.0_real64
    water0=rv; enthalpy0=mixture_enthalpy(t,rv,qc,qi)
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status,SATURATION_LIQUID)
    CALL check(status==STATUS_OK .AND. qc>0.0_real64 .AND. rv<0.020_real64 .AND. &
               t>280.0_real64, &
               'supersaturation must condense and warm',failures)
    CALL check(ABS((rv+qc+qi)-water0)<2.0e-13_real64 .AND. &
               ABS(mixture_enthalpy(t,rv,qc,qi)-enthalpy0)<2.0e-7_real64, &
               'condensation must conserve water and mixture enthalpy',failures)

    ! This state needs condensation warming beyond the accepted 350 K limit;
    ! its inputs remain inside the canonical vapor and hydrometeor bounds.
    t=349.0_real64; rv=0.01_real64; qc=0.02_real64; qi=0.0_real64
    CALL check(temperature_for_final_state(t,rv,qc,qi,0.0_real64,qc+rv,qi)>350.0_real64, &
               'zero-RH mixture equilibrium would exceed the temperature bound',failures)
    t0=t; rv0=rv; qc0=qc; qi0=qi
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,0.0_real64,status,SATURATION_LIQUID)
    CALL check(status==STATUS_FAILED .AND. t==t0 .AND. rv==rv0 .AND. &
               qc==qc0 .AND. qi==qi0, &
               'failed saturation adjustment must be atomic',failures)
    CALL check(dry_air_density(85000.0_real64,280.0_real64,0.01_real64)>0.0_real64, &
               'dry-air density must be physical',failures)
  END SUBROUTINE test_phase_and_thermodynamics

  SUBROUTINE test_thermo_interior_root(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: t,rv,qc,qi,expected_t,expected_v,transfer,es,water0,h0
    INTEGER :: status
    ! Construct known equilibria using an independent full-mixture enthalpy
    ! oracle, rather than any production thermodynamic helper.
    expected_t=310.0_real64
    es=611.20_real64*EXP(17.67_real64*(expected_t-273.15_real64)/(expected_t-29.65_real64))
    expected_v=0.622_real64*es/(85000.0_real64-es)
    transfer=0.01_real64
    t=temperature_for_final_state(expected_t,expected_v,transfer,0.0_real64, &
      expected_v+transfer,0.0_real64,0.0_real64)
    rv=expected_v+transfer; qc=0.0_real64; qi=0.0_real64
    water0=rv; h0=mixture_enthalpy(t,rv,qc,qi)
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status,SATURATION_LIQUID)
    CALL check(status==STATUS_OK,'interior root despite hot all-condensed endpoint',failures)
    CALL check(ABS(t-expected_t)<1.0e-8_real64 .AND. ABS(rv-expected_v)<1.0e-11_real64 .AND. &
               ABS(qc-transfer)<1.0e-11_real64,'recover constructed liquid equilibrium',failures)
    CALL check(ABS(rv+qc+qi-water0)<2.0e-13_real64 .AND. &
               ABS(mixture_enthalpy(t,rv,qc,qi)-h0)<2.0e-7_real64, &
               'constructed equilibrium water and enthalpy',failures)

    expected_t=290.0_real64
    es=611.20_real64*EXP(17.67_real64*(expected_t-273.15_real64)/(expected_t-29.65_real64))
    expected_v=0.622_real64*es/(85000.0_real64-es)
    transfer=0.01_real64
    t=temperature_for_final_state(expected_t,expected_v,0.2_real64-transfer,0.0_real64, &
      expected_v-transfer,0.2_real64,0.0_real64)
    rv=expected_v-transfer; qc=0.2_real64; qi=0.0_real64
    water0=rv+qc; h0=mixture_enthalpy(t,rv,qc,qi)
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status,SATURATION_LIQUID)
    CALL check(status==STATUS_OK .AND. ABS(t-expected_t)<1.0e-8_real64 .AND. &
               ABS(rv-expected_v)<1.0e-11_real64 .AND. ABS(qc-0.19_real64)<1.0e-11_real64, &
               'interior evaporation root despite cold endpoint',failures)
    CALL check(ABS(rv+qc+qi-water0)<2.0e-13_real64 .AND. &
               ABS(mixture_enthalpy(t,rv,qc,qi)-h0)<2.0e-7_real64, &
               'evaporation oracle water and enthalpy',failures)

    ! Numerical adversary, not a meteorological state: a large unused
    ! reservoir must not relax the accuracy of the small phase transfer.
    t=temperature_for_final_state(expected_t,expected_v,1.0e6_real64-transfer,0.0_real64, &
      expected_v-transfer,1.0e6_real64,0.0_real64)
    rv=expected_v-transfer; qc=1.0e6_real64; qi=0.0_real64
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status,SATURATION_LIQUID)
    CALL check(status==STATUS_OK .AND. ABS(t-expected_t)<1.0e-8_real64 .AND. &
               ABS(rv-expected_v)<1.0e-11_real64, &
               'root accuracy must depend on feasible transfer, not unused reservoir',failures)

    expected_t=250.0_real64
    es=611.15_real64*EXP(22.452_real64*(expected_t-273.15_real64)/(expected_t-0.55_real64))
    expected_v=0.622_real64*es/(85000.0_real64-es)
    transfer=0.5_real64*expected_v
    t=temperature_for_final_state(expected_t,expected_v,0.0_real64,0.2_real64-transfer, &
      expected_v-transfer,0.0_real64,0.2_real64)
    rv=expected_v-transfer; qc=0.0_real64; qi=0.2_real64
    water0=rv+qi; h0=mixture_enthalpy(t,rv,qc,qi)
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status,SATURATION_ICE)
    CALL check(status==STATUS_OK .AND. ABS(t-expected_t)<1.0e-8_real64 .AND. &
               ABS(rv-expected_v)<1.0e-11_real64 .AND. ABS(qi-(0.2_real64-transfer))<1.0e-11_real64, &
               'interior sublimation root despite cold endpoint',failures)
    CALL check(ABS(rv+qc+qi-water0)<2.0e-13_real64 .AND. &
               ABS(mixture_enthalpy(t,rv,qc,qi)-h0)<2.0e-7_real64, &
               'sublimation oracle water and enthalpy',failures)

    ! Preserve the old rejection fixture as a feasible-root regression.
    ! A large reservoir does not require evaporating/sublimating all of it.
    t=280.0_real64; rv=0.002_real64; qc=0.001_real64; qi=0.2_real64
    water0=rv+qc+qi; h0=mixture_enthalpy(t,rv,qc,qi)
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status,SATURATION_LIQUID)
    CALL check(status==STATUS_OK .AND. t<280.0_real64 .AND. qi>0.0_real64, &
               'large ice reservoir must not force an unphysical full depletion',failures)
    CALL check(ABS(rv+qc+qi-water0)<2.0e-13_real64 .AND. &
               ABS(mixture_enthalpy(t,rv,qc,qi)-h0)<2.0e-7_real64, &
               'mixed reservoir water and mixture enthalpy',failures)
  END SUBROUTINE test_thermo_interior_root

  SUBROUTINE test_thermo_rejection_and_exhaustion(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: x(6),before(6),bad(3),hydro_limit
    INTEGER :: field,kind,status
    bad=(/ieee_value(0.0_real64,ieee_quiet_nan), &
           ieee_value(0.0_real64,ieee_positive_inf),HUGE(1.0_real64)/)
    DO kind=1,3
      DO field=1,6
        x=(/85000.0_real64,280.0_real64,0.002_real64,0.004_real64,0.001_real64,1.0_real64/)
        x(field)=bad(kind); before=x
        CALL saturation_adjust_cell(x(1),x(2),x(3),x(4),x(5),x(6),status,SATURATION_LIQUID)
        CALL check(status==STATUS_FAILED .AND. &
                   ALL(TRANSFER(x,[0_int64],6)==TRANSFER(before,[0_int64],6)), &
                   'invalid thermo input rejected without trap or mutation',failures)
      END DO
    END DO
    x=(/85000.0_real64,280.0_real64,REAL(0.2_real32,real64)+1.0e-10_real64, &
      0.0_real64,0.0_real64,1.0_real64/)
    before=x
    CALL saturation_adjust_cell(x(1),x(2),x(3),x(4),x(5),x(6),status,SATURATION_LIQUID)
    CALL check(status==STATUS_FAILED .AND. ALL(TRANSFER(x,[0_int64],6)== &
      TRANSFER(before,[0_int64],6)), &
      'scalar vapor above canonical 0.2 cap is rejected atomically',failures)
    hydro_limit=REAL(HUGE(1.0_real32),real64)
    x=(/85000.0_real64,280.0_real64,0.002_real64,hydro_limit*(1.0_real64+1.0e-6_real64), &
      0.001_real64,1.0_real64/)
    before=x
    CALL saturation_adjust_cell(x(1),x(2),x(3),x(4),x(5),x(6),status,SATURATION_LIQUID)
    CALL check(status==STATUS_FAILED .AND. ALL(TRANSFER(x,[0_int64],6)== &
      TRANSFER(before,[0_int64],6)), &
      'scalar hydrometeor above float32 maximum is rejected atomically',failures)
    x=(/85000.0_real64,150.0_real64,0.0_real64,0.1_real64,0.0_real64,1.0_real64/)
    before=x
    CALL saturation_adjust_cell(x(1),x(2),x(3),x(4),x(5),x(6),status,SATURATION_ICE)
    CALL check(status==STATUS_OK .AND. ALL(x==before), &
               'explicit ice no-reservoir endpoint is a bounded no-op',failures)
    x=(/85000.0_real64,280.0_real64,0.0_real64,1.0e-8_real64,0.0_real64,1.0_real64/)
    CALL saturation_adjust_cell(x(1),x(2),x(3),x(4),x(5),x(6),status,SATURATION_LIQUID)
    CALL check(status==STATUS_OK .AND. ABS(x(3)-1.0e-8_real64)<1.0e-20_real64 .AND. &
               x(4)==0.0_real64 .AND. x(2)<280.0_real64, &
               'true condensate exhaustion remains a valid dry endpoint',failures)
  END SUBROUTINE test_thermo_rejection_and_exhaustion

  SUBROUTINE test_thermo_primary_reservoir(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: t,rv,qc,qi,es,qs,first(4),water0,h0
    INTEGER :: case_id,status,surface
    ! Mixed reservoirs with no freezing crossing: the designated primary
    ! phase reaches its target without a roundoff-driven secondary pass.
    DO case_id=1,2
      IF (case_id==1) THEN
        t=255.0_real64; rv=0.0021_real64; qc=0.0021_real64; qi=0.0001_real64
        surface=SATURATION_ICE
      ELSE
        t=274.0_real64; rv=0.0041_real64; qc=0.0001_real64; qi=0.0001_real64
        surface=SATURATION_LIQUID
      END IF
      water0=rv+qc+qi; h0=mixture_enthalpy(t,rv,qc,qi)
      CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,0.8_real64,status,surface)
      CALL check(status==STATUS_OK,'mixed primary-reservoir adjustment succeeds',failures)
      IF (case_id==1) THEN
        es=611.15_real64*EXP(22.452_real64*(t-273.15_real64)/(t-0.55_real64))
        CALL check(t<273.15_real64 .AND. qc==0.0021_real64, &
          'cold primary root leaves the liquid reservoir unchanged',failures)
      ELSE
        es=611.20_real64*EXP(17.67_real64*(t-273.15_real64)/(t-29.65_real64))
        CALL check(t>273.15_real64 .AND. qi==0.0001_real64, &
          'warm primary root leaves the ice reservoir unchanged',failures)
      END IF
      qs=0.622_real64*es/(85000.0_real64-es)
      CALL check(ABS(rv-0.8_real64*qs)<1.0e-11_real64, &
        'primary saturation target survives the cell transaction',failures)
      CALL check(ABS(rv+qc+qi-water0)<2.0e-13_real64 .AND. &
        ABS(mixture_enthalpy(t,rv,qc,qi)-h0)<2.0e-7_real64, &
        'mixed primary solve preserves water and mixture enthalpy',failures)
      first=[t,rv,qc,qi]
      CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,0.8_real64,status,surface)
      CALL check(status==STATUS_OK .AND. ABS(t-first(1))<1.0e-8_real64 .AND. &
        MAXVAL(ABS([rv,qc,qi]-first(2:4)))<1.0e-11_real64, &
        'same-branch mixed primary solve is repeat-stable',failures)
    END DO
  END SUBROUTINE test_thermo_primary_reservoir

  SUBROUTINE test_explicit_surface_policy(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: t,rv,qc,qi,t0,rv0,qc0,qi0,expected_t,expected_v,transfer
    REAL(real64) :: es,water0,h0
    INTEGER :: status,case_id

    ! Liquid is an explicit surface and may cross the nominal freezing point
    ! in either direction.  The first case evaporates while cooling through
    ! freezing; the second condenses while warming through freezing.
    DO case_id=1,2
      IF (case_id==1) THEN
        expected_t=268.5_real64
      ELSE
        expected_t=275.0_real64
      END IF
      transfer=0.0020_real64
      es=611.20_real64*EXP(17.67_real64*(expected_t-273.15_real64)/ &
          (expected_t-29.65_real64))
      expected_v=0.622_real64*es/(85000.0_real64-es)
      IF (case_id==1) THEN
        t=temperature_for_final_state(expected_t,expected_v,0.010_real64-transfer,0.0_real64, &
          expected_v-transfer,0.010_real64,0.0_real64)
        rv=expected_v-transfer; qc=0.010_real64
      ELSE
        t=temperature_for_final_state(expected_t,expected_v,transfer,0.0_real64, &
          expected_v+transfer,0.0_real64,0.0_real64)
        rv=expected_v+transfer; qc=0.0_real64
      END IF
      qi=0.0_real64
      CALL check((case_id==1 .AND. t>273.15_real64) .OR. (case_id==2 .AND. t<273.15_real64), &
                 'liquid crossing starts on the opposite side of freezing',failures)
      water0=rv+qc+qi; h0=mixture_enthalpy(t,rv,qc,qi)
      CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status, &
                                  SATURATION_LIQUID)
      CALL check(status==STATUS_OK .AND. ((case_id==1 .AND. t<273.15_real64) .OR. &
                  (case_id==2 .AND. t>273.15_real64)), &
                 'liquid surface permits a freezing-point crossing',failures)
      CALL check(ABS(t-expected_t)<1.0e-8_real64 .AND. ABS(rv-expected_v)<1.0e-11_real64, &
                 'liquid crossing reaches its liquid saturation root',failures)
      CALL check(ABS(rv+qc+qi-water0)<2.0e-13_real64 .AND. &
                  ABS(mixture_enthalpy(t,rv,qc,qi)-h0)<2.0e-7_real64, &
                  'liquid crossing conserves water and mixture enthalpy',failures)
      t0=t; rv0=rv; qc0=qc; qi0=qi
      CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status, &
                                  SATURATION_LIQUID)
      CALL check(status==STATUS_OK .AND. ABS(t-t0)<1.0e-8_real64 .AND. &
                  ABS(rv-rv0)<1.0e-11_real64 .AND. ABS(qc-qc0)<1.0e-11_real64 .AND. &
                  qi==qi0,'repeated liquid crossing is stable',failures)
    END DO

    ! Selecting liquid does not silently consume an ice reservoir when liquid
    ! condensate is absent; a separate explicit ice operation is required.
    t=280.0_real64; rv=0.001_real64; qc=0.0_real64; qi=0.010_real64
    t0=t; rv0=rv; qc0=qc; qi0=qi
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status, &
                                SATURATION_LIQUID)
    CALL check(status==STATUS_OK .AND. t==t0 .AND. rv==rv0 .AND. qc==qc0 .AND. qi==qi0, &
               'missing liquid reservoir has no secondary ice pass',failures)

    ! Conversely, an ice surface with no ice reservoir does not fall back to
    ! an available liquid reservoir.
    t=250.0_real64; rv=1.0e-4_real64; qc=0.010_real64; qi=0.0_real64
    t0=t; rv0=rv; qc0=qc; qi0=qi
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status, &
                                SATURATION_ICE)
    CALL check(status==STATUS_OK .AND. t==t0 .AND. rv==rv0 .AND. qc==qc0 .AND. qi==qi0, &
               'missing ice reservoir has no secondary liquid pass',failures)

    t=280.0_real64; rv=0.002_real64; qc=0.004_real64; qi=0.001_real64
    t0=t; rv0=rv; qc0=qc; qi0=qi
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status,99)
    CALL check(status==STATUS_FAILED .AND. t==t0 .AND. rv==rv0 .AND. qc==qc0 .AND. qi==qi0, &
               'unknown saturation surface is rejected atomically',failures)

    t=280.0_real64; rv=0.002_real64; qc=0.004_real64; qi=0.001_real64
    t0=t; rv0=rv; qc0=qc; qi0=qi
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status,SATURATION_ICE)
    CALL check(status==STATUS_FAILED .AND. t==t0 .AND. rv==rv0 .AND. qc==qc0 .AND. qi==qi0, &
               'warm ice input rejects before any crossing',failures)

    ! Even a cold input may not select an ice root whose physical solution is
    ! above freezing; the bounded root must fail without committing a state.
    expected_t=275.0_real64
    transfer=0.0010_real64
    es=611.15_real64*EXP(22.452_real64*(expected_t-273.15_real64)/ &
        (expected_t-0.55_real64))
    expected_v=0.622_real64*es/(85000.0_real64-es)
    t=temperature_for_final_state(expected_t,expected_v,0.0_real64,0.001_real64+transfer, &
      expected_v+transfer,0.0_real64,0.001_real64)
    rv=expected_v+transfer; qc=0.0_real64; qi=0.001_real64
    water0=rv+qi
    CALL check(t<273.15_real64 .AND. t>150.0_real64 .AND. rv>=0.0_real64 .AND. qi>=0.0_real64 .AND. &
               ABS(water0-(expected_v+0.001_real64+transfer))<2.0e-13_real64, &
               'cold ice crossing fixture has a physical root construction',failures)
    t0=t; rv0=rv; qc0=qc; qi0=qi
    CALL saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status, &
                                SATURATION_ICE)
    CALL check(status==STATUS_FAILED .AND. t==t0 .AND. rv==rv0 .AND. qc==qc0 .AND. qi==qi0, &
               'cold ice root above freezing fails atomically',failures)
  END SUBROUTINE test_explicit_surface_policy

  SUBROUTINE test_flux_ledgers(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(grid_spec) :: grid
    TYPE(column_physics_config) :: cfg
    TYPE(precipitation_flux_ledger) :: ledger
    REAL(real32) :: p(4,4,3),t(4,4,3),qv(4,4,3),u(4,4,3),v(4,4,3),w(4,4,3)
    LOGICAL :: wvalid(4,4,3),domain(4,4,3),observed(4,4,3),no_echo(4,4,3)
    INTEGER :: phase(4,4,3),phase_before(4,4,3),status,k
    REAL(real64) :: z(4,4,3),rain(4,4,3),snow(4,4,3),graupel(4,4,3)
    REAL(real64) :: z_before(4,4,3),rain_before(4,4,3)
    REAL(real64) :: snow_before(4,4,3),graupel_before(4,4,3)
    REAL(real64) :: rv64,rho_d_upper,rho_d_lower,rho_g_upper,dz,vt_upper,vt_lower
    REAL(real64) :: displacement,expected_rain

    grid%nx=4; grid%ny=4; grid%nz=3; grid%grid_id='transport-test'
    ALLOCATE(grid%dx(4,4),grid%dy(4,4),grid%pressure_interface(4,4,4), &
             grid%cell_dp(4,4,3),grid%level_spacing_dp(4,4,2), &
             grid%pressure_mass_measure(4,4,3),grid%dry_air_mass_measure(4,4,3))
    grid%dx=2000.0_real64; grid%dy=2000.0_real64
    grid%pressure_interface(:,:,1)=102500.0_real64
    grid%pressure_interface(:,:,2)=87500.0_real64
    grid%pressure_interface(:,:,3)=72500.0_real64
    grid%pressure_interface(:,:,4)=57500.0_real64
    grid%cell_dp=15000.0_real64; grid%level_spacing_dp=15000.0_real64
    grid%pressure_mass_measure=SPREAD(grid%dx*grid%dy,3,3)*grid%cell_dp/9.80665_real64
    grid%dry_air_mass_measure=grid%pressure_mass_measure/(1.0_real64+0.008_real64)
    DO k=1,3; p(:,:,k)=REAL(95000-15000*(k-1),real32); END DO
    t=280.0_real32; qv=0.008_real32; u=0.0_real32; v=0.0_real32
    w=0.0_real32; wvalid=.TRUE.; domain=.TRUE.; observed=.FALSE.; no_echo=.FALSE.
    phase=PHASE_UNKNOWN
    z=0.0_real64; rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64

    phase(1,1,1)=PHASE_FREEZING_RAIN
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg), &
               'zero-mass freezing-rain metadata must be a no-op',failures)
    phase(1,1,1)=PHASE_SLEET
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg), &
               'zero-mass sleet metadata must be a no-op',failures)
    phase=PHASE_UNKNOWN

    observed(2,2,3)=.TRUE.; observed(2,2,2)=.TRUE.
    phase(2,2,3)=PHASE_RAIN; z(2,2,3)=1000.0_real64; rain(2,2,3)=1.0e-4_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg), &
               'blocked-destination flux ledger must close',failures)
    CALL check(ledger%observation_blocked>0.0_real64, &
               'observed destination must be an explicit ledger term',failures)

    observed=.FALSE.; no_echo=.FALSE.; phase=PHASE_UNKNOWN; z=0.0_real64
    rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64
    observed(2,2,3)=.TRUE.; no_echo(2,2,2)=.TRUE.
    phase(2,2,3)=PHASE_RAIN; z(2,2,3)=1000.0_real64; rain(2,2,3)=1.0e-4_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg) .AND. &
               ledger%no_echo_blocked>0.0_real64 .AND. &
               ledger%observation_blocked==0.0_real64 .AND. &
               rain(2,2,2)==0.0_real64, &
      'explicit no-echo must hard-block shaft deposition in a separate ledger',failures)

    observed=.FALSE.; no_echo=.FALSE.; phase=PHASE_UNKNOWN; z=0.0_real64
    rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64
    no_echo(2,2,3)=.TRUE.; rain(2,2,3)=1.0e-4_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED .AND. rain(2,2,3)==1.0e-4_real64, &
      'no-echo cells cannot originate precipitation and failure is atomic',failures)

    observed=.FALSE.; no_echo=.FALSE.; phase=PHASE_UNKNOWN; z=0.0_real64
    rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64
    observed(2,2,3)=.TRUE.
    phase(2,2,3)=PHASE_RAIN; z(2,2,3)=1000.0_real64; rain(2,2,3)=1.0e-4_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg) .AND. &
               ledger%no_echo_blocked==0.0_real64 .AND. rain(2,2,2)>0.0_real64, &
      'radar-missing destination must remain distinct and accept deposition',failures)

    observed=.FALSE.; no_echo=.FALSE.; phase=PHASE_UNKNOWN; z=0.0_real64
    rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64
    observed(4,2,3)=.TRUE.; phase(4,2,3)=PHASE_RAIN
    z(4,2,3)=1000.0_real64; rain(4,2,3)=1.0e-4_real64; u=20.0_real32
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg), &
               'domain-exit flux ledger must close',failures)
    CALL check(ledger%boundary_exit>0.0_real64, &
               'domain-exit flux must not disappear',failures)

    observed=.FALSE.; phase=PHASE_UNKNOWN; z=0.0_real64
    rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64; u=0.0_real32
    observed(2,2,3)=.TRUE.; phase(2,2,3)=PHASE_RAIN
    z(2,2,3)=1000.0_real64; rain(2,2,3)=1.0e-4_real64
    w=20.0_real32
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg) .AND. &
               ABS(rain(2,2,2))<=TINY(1.0_real64), &
               'ascent faster than fall speed must not force downward crossing',failures)

    w=-10.0_real32
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg), &
               'strong downdraft relative-flux ledger must close',failures)

    w=0.0_real32; wvalid=.TRUE.; domain=.TRUE.; observed=.FALSE.
    phase=PHASE_UNKNOWN; z=0.0_real64
    rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64
    observed(2,2,3)=.TRUE.; phase(2,2,3)=PHASE_RAIN
    z(2,2,3)=1000.0_real64; rain(2,2,3)=1.0e-4_real64
    domain(:,:,1:2)=.FALSE.; wvalid(:,:,1:2)=.FALSE.; u=10.0_real32
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg) .AND. &
               ledger%terrain_intercept>0.0_real64 .AND. &
               ledger%maximum_required_substeps==1, &
      'terrain intercept must use the clipped interface distance and conserve flux', &
      failures)

    domain=.TRUE.; wvalid=.TRUE.; observed=.FALSE.; phase=PHASE_UNKNOWN; u=0.0_real32
    z=0.0_real64; rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64
    rain(2,2,3)=-1.0e-4_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED, &
               'negative hydrometeor input must fail before transport',failures)

    rain=0.0_real64; rain(2,2,3)=1.0e-4_real64
    z(2,2,3)=1000.0_real64; observed(2,2,3)=.TRUE.; phase(2,2,3)=PHASE_RAIN
    grid%dx(2,2)=2500.0_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED, &
               'nonuniform trajectory grid must fail until physical transport exists',failures)

    grid%dx=2000.0_real64
    cfg%maximum_horizontal_substep=0.0_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'invalid transport config must fail',failures)
    cfg%maximum_horizontal_substep=0.75_real64
    cfg%maximum_horizontal_substep=HUGE(1.0_real64)
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'overflowing transport config must fail',failures)
    cfg%maximum_horizontal_substep=0.75_real64
    cfg%minimum_dbz=-101.0_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'dBZ config must match terminal-speed range',failures)
    cfg%minimum_dbz=0.0_real64
    cfg%maximum_transport_substeps=HUGE(1)
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'transport work bound must be finite',failures)
    cfg%maximum_transport_substeps=64
    cfg%ledger_relative_tolerance=HUGE(1.0_real64)
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'relative ledger gate cannot be disabled',failures)
    cfg%ledger_relative_tolerance=1.0e-11_real64
    cfg%ledger_absolute_tolerance=HUGE(1.0_real64)
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'absolute ledger gate cannot be disabled',failures)
    cfg%ledger_absolute_tolerance=1.0e-13_real64

    domain(2,2,3)=.FALSE.
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED, &
               'below-ground source hydrometeor must fail',failures)
    domain=.TRUE.; u=0.0_real32
    snow(2,2,3)=rain(2,2,3)
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED, &
               'explicit phase and hydrometeor species must agree',failures)
    snow=0.0_real64
    phase(2,2,3)=PHASE_FREEZING_RAIN
    snow(2,2,3)=rain(2,2,3); rain(2,2,3)=0.0_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED, &
               'freezing-rain phase cannot carry snow',failures)
    phase(2,2,3)=PHASE_SLEET
    rain(2,2,3)=snow(2,2,3); snow=0.0_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'sleet phase cannot carry rain',failures)
    rain=0.0_real64; snow=0.0_real64; graupel(2,2,3)=1.0e-4_real64
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED, &
               'sleet phase requires both snow and graupel',failures)
    phase(2,2,3)=PHASE_FREEZING_RAIN
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED, &
               'freezing-rain phase requires both rain and graupel',failures)
    graupel=0.0_real64; rain(2,2,3)=1.0e-4_real64
    phase(2,2,3)=PHASE_RAIN

    cfg%maximum_dbz=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'non-finite transport config must fail',failures)
    cfg%maximum_dbz=80.0_real64

    p(2,2,3)=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'non-finite transport input must fail',failures)
    p(2,2,3)=65000.0_real32

    p(:,:,1)=60000.0_real32; p(:,:,2)=80000.0_real32
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'reversed pressure order must fail',failures)
    DO k=1,3; p(:,:,k)=REAL(95000-15000*(k-1),real32); END DO

    wvalid=.TRUE.; wvalid(2,2,1)=.FALSE.
    phase_before=phase; z_before=z; rain_before=rain
    snow_before=snow; graupel_before=graupel
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED .AND. ALL(phase==phase_before) .AND. &
               ALL(z==z_before) .AND. ALL(rain==rain_before) .AND. &
               ALL(snow==snow_before) .AND. ALL(graupel==graupel_before), &
               'failed transport must leave caller arrays unchanged',failures)
    wvalid=.TRUE.

    ! Independent EOS/trajectory oracle: gas density sets pressure distance;
    ! dry density converts species flux. A moist case separates the two bases.
    cfg=column_physics_config()
    grid%dx=2000.0_real64; grid%dy=2000.0_real64
    domain=.TRUE.; wvalid=.TRUE.; observed=.FALSE.; no_echo=.FALSE.
    phase=PHASE_UNKNOWN; rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64; z=0.0_real64
    t=280.0_real32; qv=0.1_real32; v=0.0_real32; w=0.0_real32
    rv64=REAL(qv(2,2,3),real64)
    rho_d_upper=65000.0_real64/(287.05_real64*280.0_real64*(1.0_real64+rv64/0.622_real64))
    rho_d_lower=80000.0_real64/(287.05_real64*280.0_real64*(1.0_real64+rv64/0.622_real64))
    rho_g_upper=rho_d_upper*(1.0_real64+rv64)
    dz=15000.0_real64/(rho_g_upper*9.80665_real64)
    vt_upper=terminal_velocity(PHASE_RAIN,65000.0_real64,280.0_real64,30.0_real64,status)
    CALL check(status==STATUS_OK,'trajectory oracle upper terminal velocity',failures)
    vt_lower=terminal_velocity(PHASE_RAIN,80000.0_real64,280.0_real64,30.0_real64,status)
    CALL check(status==STATUS_OK,'trajectory oracle lower terminal velocity',failures)
    u=REAL(0.25_real64*2000.0_real64*vt_upper/dz,real32)
    displacement=REAL(u(2,2,3),real64)*dz/(vt_upper*2000.0_real64)
    observed(2,2,3)=.TRUE.; phase(2,2,3)=PHASE_RAIN
    z(2,2,3)=1000.0_real64; rain(2,2,3)=1.0e-4_real64
    expected_rain=rho_d_upper*1.0e-4_real64*vt_upper*displacement/(rho_d_lower*vt_lower)
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_OK .AND. flux_ledger_closes(ledger,cfg), &
      'moist-gas trajectory retains dry-basis flux closure',failures)
    CALL check(ABS(rain(3,2,2)-expected_rain)<1.0e-13_real64, &
      'trajectory uses gas density while destination mass uses dry density',failures)

    DEALLOCATE(grid%cell_dp)
    CALL transport_precipitation_flux(grid,p,t,qv,u,v,w,wvalid,domain,observed,phase,z, &
                                      rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check(status==STATUS_FAILED,'malformed transport dp must fail',failures)
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
    input%cloud_fraction%value(2,2,2)=0.8_real32
    input%cloud_type%value(2,2,2)=1_int32
    input%cloud_fraction%valid(1,1,1)=.FALSE.
    input%cloud_fraction%quality(1,1,1)=QUALITY_RAW_MISSING
    input%cloud_fraction%source(1,1,1)=0_int32
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. output%obs_support(2,2,2)==1_int32, &
               'a missing optional cloud mate must exclude only its cell',failures)

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
    CALL check(.NOT.ANY(((input%rain%value/=output%rain%value) .OR. &
                         (input%snow%value/=output%snow%value) .OR. &
                         (input%graupel%value/=output%graupel%value)) .AND. &
                        .NOT.result%changed), &
               'column changed mask must cover every hydrometeor change',failures)
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
    input%radar_reflectivity%quality(2,2,4)=0_int32
    input%radar_reflectivity%source(2,2,4)= &
      IOR(SOURCE_RADAR_DBZ,SOURCE_ANALYZED_WIND)
    input%radar_reflectivity%value(2,2,4)=RADAR_NO_ECHO_DBZ
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
               result%reason_code==REASON_RADAR_CONTRACT .AND. &
               .NOT.ANY(result%changed), &
      'ambiguous invalid radar provenance must not become a transport destination', &
      failures)

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

    CALL make_state(input,4,4,4)
    input%radar_reflectivity%valid(2,2,4)=.TRUE.
    input%radar_reflectivity%quality(2,2,4)=0_int32
    input%radar_reflectivity%source(2,2,4)=SOURCE_RADAR_DBZ
    input%radar_reflectivity%value(2,2,4)=80.0_real32
    cfg%reference_mass_concentration=1.0_real64
    cfg%precipitation_loading_efficiency=1.0_real64
    cfg%maximum_downdraft_ms=200.0_real64
    cfg%maximum_downdraft_innovation_ms=200.0_real64
    CALL derive_column_physics(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_RANGE .AND. &
      .NOT.ANY(result%changed) .AND. ALL(output%omega_target%valid .EQV. &
      input%omega_target%valid) .AND. ALL(output%rain%value==input%rain%value), &
      'out-of-contract column target must rollback before commit',failures)
    cfg=column_physics_config()

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
    CALL test_transported_loading_has_no_wind_authority(failures)
  END SUBROUTINE test_column_stage

  SUBROUTINE test_column_thermo_integration(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,baseline,expected,output
    TYPE(stage_result) :: base_result,expected_result,thermo_result
    TYPE(column_physics_config) :: cfg
    TYPE(water_phase_budget) :: budget,expected_budget
    LOGICAL :: active(2,2,3)
    INTEGER :: surface(2,2,3),status
    REAL(real64) :: expected_vt,final_t,final_v,final_rho,final_dz,qprecip
    REAL(real64) :: loading_energy,expected_w,expected_omega

    ! A valid water column without thermo arguments remains an exact no-op.
    CALL make_state(input,2,2,3)
    CALL valid_real(input%cloud_water,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%rain,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%snow,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%graupel,SOURCE_BACKGROUND_MODEL)
    input%cloud_water%value(1,1,2)=0.002_real32
    CALL refresh_dry_air_mass_measure(input,status)
    CALL derive_column_physics(input,output,thermo_result,cfg)
    CALL check(thermo_result%status==STATUS_OK .AND. .NOT.ANY(thermo_result%changed) .AND. &
      canonical_states_equal(output,input),'absent thermo must not be inferred from cloud water',failures)

    ! Compare the coupled route with the standalone saturation of its exact
    ! no-thermo proposal, including the final fall-speed diagnostic.
    CALL make_state(input,2,2,3)
    CALL valid_real(input%cloud_water,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%rain,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%snow,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%graupel,SOURCE_BACKGROUND_MODEL)
    input%cloud_water%value(1,1,2)=0.002_real32
    input%radar_reflectivity%valid(1,1,2)=.TRUE.
    input%radar_reflectivity%quality(1,1,2)=0_int32
    input%radar_reflectivity%source(1,1,2)=SOURCE_RADAR_DBZ
    input%radar_reflectivity%value(1,1,2)=30.0_real32
    input%precipitation_phase%valid(1,1,2)=.TRUE.
    input%precipitation_phase%quality(1,1,2)=0_int32
    input%precipitation_phase%source(1,1,2)=SOURCE_RADAR_DBZ
    input%precipitation_phase%value(1,1,2)=PHASE_RAIN
    CALL refresh_dry_air_mass_measure(input,status)
    active=.FALSE.; active(1,1,2)=.TRUE.; surface=SATURATION_LIQUID
    CALL derive_column_physics(input,baseline,base_result,cfg)
    CALL saturation_adjust_pressure_state(baseline,expected,expected_result,active, &
      1.0_real64,expected_budget,surface)
    CALL derive_column_physics(input,output,thermo_result,cfg,thermo_active=active, &
      thermo_surface=surface,target_rh=1.0_real64,thermo_budget=budget)
    CALL check(base_result%status==STATUS_OK .AND. expected_result%status==STATUS_OK .AND. &
      thermo_result%status==STATUS_OK,'explicit thermo radar route succeeds',failures)
    CALL check(ABS(REAL(output%temperature%value(1,1,2),real64)- &
      REAL(expected%temperature%value(1,1,2),real64))<5.0e-5_real64 .AND. &
      ABS(REAL(output%vapor%value(1,1,2),real64)- &
      REAL(expected%vapor%value(1,1,2),real64))<5.0e-7_real64, &
      'thermo route matches standalone saturation of hydrometeor proposal',failures)
    CALL check(ABS(budget%species_change_kg(1))>1.0e-4_real64 .AND. &
      ABS(budget%species_change_kg(2))>1.0e-4_real64, &
      'explicit cloud-water exchange is nonzero',failures)
    CALL check(ABS(budget%water_error_kg-SUM(budget%species_change_kg))<=1.0e-12_real64, &
      'explicit cloud-water exchange budget closes',failures)
    CALL check(ALL(output%rain%value==expected%rain%value) .AND. &
      ALL(output%snow%value==expected%snow%value) .AND. &
      ALL(output%graupel%value==expected%graupel%value), &
      'thermo route does not duplicate standalone precipitation',failures)
    expected_vt=terminal_velocity(PHASE_RAIN,80000.0_real64, &
      REAL(output%temperature%value(1,1,2),real64),30.0_real64,status)
    CALL check(status==STATUS_OK .AND. output%vt_z_mean%valid(1,1,2) .AND. &
      ABS(REAL(output%vt_z_mean%value(1,1,2),real64)-expected_vt)<5.0e-5_real64 .AND. &
      IAND(output%vt_z_mean%quality(1,1,2),QUALITY_FALL_SPEED_UNCERTAIN)/=0_int32, &
      'fall speed uses final temperature with uncertainty provenance',failures)
    final_t=REAL(output%temperature%value(1,1,2),real64)
    final_v=REAL(output%vapor%value(1,1,2),real64)
    final_rho=(80000.0_real64/(287.05_real64*final_t* &
      (1.0_real64+final_v/0.622_real64)))*(1.0_real64+final_v)
    final_dz=input%grid%cell_dp(1,1,2)/(final_rho*9.80665_real64)
    qprecip=REAL(output%rain%value(1,1,2)+output%snow%value(1,1,2)+ &
      output%graupel%value(1,1,2),real64)
    loading_energy=9.80665_real64*cfg%precipitation_loading_efficiency*qprecip*final_dz
    expected_w=-MIN(cfg%maximum_downdraft_ms,SQRT(MAX(0.0_real64,2.0_real64*loading_energy)))
    expected_w=MIN(0.0_real64,MAX(-cfg%maximum_downdraft_innovation_ms,expected_w))
    expected_omega=-final_rho*9.80665_real64*expected_w
    CALL check(output%omega_target%valid(1,1,2) .AND. &
      ABS(REAL(output%omega_target%value(1,1,2),real64)-expected_omega)<5.0e-5_real64, &
      'loading target uses final gas density and precipitation',failures)
    CALL check(IAND(output%omega_target%source(1,1,2),SOURCE_DYNAMIC_TARGET)==0_int32 .AND. &
      .NOT.dynamic_target_has_authority(output%omega_target%valid(1,1,2), &
      output%omega_target%quality(1,1,2),output%omega_target%source(1,1,2)), &
      'thermo diagnostics cannot grant dynamic target authority',failures)
    CALL check(.NOT.output%omega_target_sigma%valid(1,1,2), &
      'uncalibrated column diagnostics cannot fabricate target uncertainty',failures)
    CALL derive_column_physics(output,expected,expected_result,cfg,thermo_active=active, &
      thermo_surface=surface,target_rh=1.0_real64,thermo_budget=budget)
    CALL check(expected_result%status==STATUS_FAILED .AND. &
      expected_result%reason_code==REASON_AUTHORITY .AND. canonical_states_equal(expected,output), &
      'thermo route preserves the pristine-background guard',failures)

    ! An empty explicit mask is also a no-op; a partial optional tuple rejects.
    active=.FALSE.; surface=SATURATION_LIQUID
    CALL derive_column_physics(input,output,thermo_result,cfg,thermo_active=active, &
      thermo_surface=surface,target_rh=1.0_real64,thermo_budget=budget)
    CALL check(thermo_result%status==STATUS_OK .AND. canonical_states_equal(output,baseline), &
      'empty thermo mask has no implicit adjustment',failures)
    CALL check(ALL(budget%species_change_kg==0.0_real64) .AND. &
      budget%sensible_change_j==0.0_real64 .AND. budget%phase_change_j==0.0_real64 .AND. &
      budget%water_error_kg==0.0_real64 .AND. budget%enthalpy_error_j==0.0_real64, &
      'empty thermo mask has zero budget',failures)
    CALL derive_column_physics(input,output,thermo_result,cfg,thermo_active=active)
    CALL check(thermo_result%status==STATUS_FAILED .AND. canonical_states_equal(output,input), &
      'partial thermo optional tuple rejects atomically',failures)

    ! A later bad ICE cell must roll back the earlier valid liquid adjustment,
    ! including the radar proposal and all budget terms.
    CALL make_state(input,2,2,3)
    CALL valid_real(input%cloud_water,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%rain,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%snow,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(input%graupel,SOURCE_BACKGROUND_MODEL)
    input%cloud_water%value(1,1,2)=0.002_real32
    input%cloud_water%value(2,1,2)=0.002_real32
    input%radar_reflectivity%valid(1,1,2)=.TRUE.
    input%radar_reflectivity%quality(1,1,2)=0_int32
    input%radar_reflectivity%source(1,1,2)=SOURCE_RADAR_DBZ
    input%radar_reflectivity%value(1,1,2)=30.0_real32
    CALL refresh_dry_air_mass_measure(input,status)
    active=.FALSE.; active(1,1,2)=.TRUE.; active(2,1,2)=.TRUE.
    surface=SATURATION_LIQUID; surface(2,1,2)=SATURATION_ICE
    CALL derive_column_physics(input,output,thermo_result,cfg,thermo_active=active, &
      thermo_surface=surface,target_rh=1.0_real64,thermo_budget=budget)
    CALL check(thermo_result%status==STATUS_FAILED .AND. canonical_states_equal(output,input), &
      'late bad ICE thermo cell rolls back the whole column',failures)
    CALL check(ALL(budget%species_change_kg==0.0_real64) .AND. &
      budget%sensible_change_j==0.0_real64 .AND. budget%phase_change_j==0.0_real64 .AND. &
      budget%water_error_kg==0.0_real64 .AND. budget%enthalpy_error_j==0.0_real64, &
      'late thermo rejection returns zero budget',failures)
  END SUBROUTINE test_column_thermo_integration

  SUBROUTINE test_transported_loading_has_no_wind_authority(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: base,extended,base_out,extended_out
    TYPE(stage_result) :: base_result,extended_result
    TYPE(column_physics_config) :: cfg
    INTEGER(int32) :: base_bits,extended_bits

    CALL make_state(base,4,4,4)
    base%u%value=10.5_real32
    base%radar_reflectivity%valid(2,2,2)=.TRUE.
    base%radar_reflectivity%quality(2,2,2)=0_int32
    base%radar_reflectivity%source(2,2,2)=SOURCE_RADAR_DBZ
    base%radar_reflectivity%value(2,2,2)=30.0_real32
    base%precipitation_phase%valid(2,2,2)=.TRUE.
    base%precipitation_phase%quality(2,2,2)=0_int32
    base%precipitation_phase%source(2,2,2)=SOURCE_RADAR_DBZ
    base%precipitation_phase%value(2,2,2)=PHASE_RAIN
    extended=base
    extended%radar_reflectivity%valid(1,2,4)=.TRUE.
    extended%radar_reflectivity%quality(1,2,4)=0_int32
    extended%radar_reflectivity%source(1,2,4)=SOURCE_RADAR_DBZ
    extended%radar_reflectivity%value(1,2,4)=30.0_real32
    extended%precipitation_phase%valid(1,2,4)=.TRUE.
    extended%precipitation_phase%quality(1,2,4)=0_int32
    extended%precipitation_phase%source(1,2,4)=SOURCE_RADAR_DBZ
    extended%precipitation_phase%value(1,2,4)=PHASE_RAIN

    CALL derive_column_physics(base,base_out,base_result,cfg)
    CALL derive_column_physics(extended,extended_out,extended_result,cfg)
    CALL check(base_result%status==STATUS_OK .AND. extended_result%status==STATUS_OK, &
      'transported-loading authority fixture must run',failures)
    CALL check(extended_out%rain%value(2,2,3)>base_out%rain%value(2,2,3), &
      'fixture must transport a remote echo into the direct-echo column',failures)
    base_bits=TRANSFER(base_out%omega_target%value(2,2,2),base_bits)
    extended_bits=TRANSFER(extended_out%omega_target%value(2,2,2),extended_bits)
    CALL check(base_out%omega_target%valid(2,2,2) .AND. &
      extended_out%omega_target%valid(2,2,2) .AND. base_bits==extended_bits, &
      'transported hydrometeors cannot amplify a direct-echo wind target',failures)
    CALL check(.NOT.dynamic_target_has_authority(base_out%omega_target%valid(2,2,2), &
      base_out%omega_target%quality(2,2,2),base_out%omega_target%source(2,2,2)), &
      'uncalibrated loading target cannot obtain dynamic authority',failures)

    base%omega_target%value(2,2,2)=-0.25_real32
    base%omega_target%valid(2,2,2)=.TRUE.
    base%omega_target%quality(2,2,2)=0_int32
    base%omega_target%source(2,2,2)=IOR(SOURCE_CONVENTIONAL_OBS,SOURCE_DYNAMIC_TARGET)
    ! Synthetic observational target: explicit finite uncertainty with the
    ! target evidence; this is not a calibrated retrieval-error claim.
    base%omega_target_sigma%value(2,2,2)=0.5_real32
    base%omega_target_sigma%valid(2,2,2)=.TRUE.
    base%omega_target_sigma%quality(2,2,2)=0_int32
    base%omega_target_sigma%source(2,2,2)=base%omega_target%source(2,2,2)
    CALL derive_column_physics(base,base_out,base_result,cfg)
    CALL check(base_result%status==STATUS_OK .AND. &
      base_out%omega_target%value(2,2,2)==base%omega_target%value(2,2,2) .AND. &
      base_out%omega_target%source(2,2,2)==base%omega_target%source(2,2,2) .AND. &
      base_out%omega_target_sigma%valid(2,2,2) .AND. &
      base_out%omega_target_sigma%value(2,2,2)==base%omega_target_sigma%value(2,2,2) .AND. &
      base_out%omega_target_sigma%source(2,2,2)==base%omega_target_sigma%source(2,2,2), &
      'radar loading must preserve a collocated authoritative target',failures)
  END SUBROUTINE test_transported_loading_has_no_wind_authority

  SUBROUTINE test_radar_background_isolation(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output,repeated,updated,fresh
    TYPE(stage_result) :: result,repeat_result,updated_result,fresh_result
    TYPE(column_physics_config) :: cfg
    INTEGER(int32) :: far_bits
    INTEGER :: status

    CALL make_state(input,4,4,4)
    input%rain%value(4,4,2)=2.0e-4_real32
    input%rain%valid(4,4,2)=.TRUE.
    input%rain%quality(4,4,2)=QUALITY_LEGACY_PROVENANCE
    input%rain%source(4,4,2)=SOURCE_BACKGROUND_MODEL
    far_bits=TRANSFER(input%rain%value(4,4,2),far_bits)
    input%rain%value(2,2,3)=3.0e-4_real32
    input%rain%valid(2,2,3)=.TRUE.
    input%rain%quality(2,2,3)=0_int32
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
    CALL refresh_dry_air_mass_measure(fresh,status)
    IF (status/=STATUS_OK) ERROR STOP 'fresh dry-air mass refresh failed'
    CALL refresh_dry_air_mass_measure(input,status)
    IF (status/=STATUS_OK) ERROR STOP 'input dry-air mass refresh failed'
    CALL derive_column_physics(fresh,repeated,repeat_result,cfg)
    CALL derive_column_physics(input,output,result,cfg)
    IF (result%status/=STATUS_OK) PRINT *,'radar reconstruction status/reason:', &
      result%status,result%reason_code
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
    updated%radar_reflectivity%value=0.0_real32
    updated%radar_reflectivity%quality=QUALITY_RAW_MISSING
    updated%radar_reflectivity%source=0_int32
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

  SUBROUTINE test_column_evaluation_state(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,evaluation,background_output,evaluation_output
    TYPE(cloud_bal_state_type) :: warm_output,invalid_output,descendant,fresh_output
    TYPE(stage_result) :: background_result,evaluation_result,warm_result
    TYPE(stage_result) :: invalid_result,descendant_result,fresh_result
    TYPE(column_physics_config) :: cfg
    TYPE(pressure_analysis_budget) :: background_budget,evaluation_budget
    TYPE(pressure_analysis_budget) :: warm_budget,descendant_budget,fresh_budget
    REAL(real64) :: rho_d,zlinear,expected_rain
    INTEGER :: status

    CALL make_state(input,4,4,4)
    input%rain%value(2,2,3)=3.0e-4_real32
    input%rain%valid(2,2,3)=.TRUE.
    input%rain%quality(2,2,3)=0_int32
    input%rain%source(2,2,3)=SOURCE_BACKGROUND_MODEL
    input%radar_reflectivity%valid(2,2,4)=.TRUE.
    input%radar_reflectivity%quality(2,2,4)=0_int32
    input%radar_reflectivity%source(2,2,4)=SOURCE_RADAR_DBZ
    input%radar_reflectivity%value(2,2,4)=30.0_real32
    input%precipitation_phase%valid(2,2,4)=.TRUE.
    input%precipitation_phase%quality(2,2,4)=0_int32
    input%precipitation_phase%source(2,2,4)=SOURCE_RADAR_DBZ
    input%precipitation_phase%value(2,2,4)=PHASE_RAIN
    CALL refresh_dry_air_mass_measure(input,status)
    IF (status/=STATUS_OK) ERROR STOP 'evaluation fixture dry-air refresh failed'

    ! Supplying the canonical background as the evaluation state is exact.
    CALL derive_column_physics(input,background_output,background_result,cfg, &
      analysis_budget=background_budget)
    CALL derive_column_physics(input,evaluation_output,evaluation_result,cfg, &
      analysis_budget=evaluation_budget,evaluation_state=input)
    CALL check(background_result%status==evaluation_result%status .AND. &
      background_result%reason_code==evaluation_result%reason_code .AND. &
      canonical_states_equal(background_output,evaluation_output) .AND. &
      ALL(background_result%changed.EQV.evaluation_result%changed) .AND. &
      ALL(background_budget%species_change_kg==evaluation_budget%species_change_kg) .AND. &
      ALL(background_budget%mixing_ratio_change_kg==evaluation_budget%mixing_ratio_change_kg) .AND. &
      ALL(background_budget%dry_mass_redistribution_kg==evaluation_budget%dry_mass_redistribution_kg) .AND. &
      background_budget%dry_air_change_kg==evaluation_budget%dry_air_change_kg .AND. &
      background_budget%enthalpy_change_j==evaluation_budget%enthalpy_change_j .AND. &
      background_budget%total_mass_error_kg==evaluation_budget%total_mass_error_kg .AND. &
      background_budget%max_cell_mass_error_kg==evaluation_budget%max_cell_mass_error_kg .AND. &
      background_budget%accounted_cells==evaluation_budget%accounted_cells .AND. &
      background_budget%incomplete_background_cells==evaluation_budget%incomplete_background_cells .AND. &
      background_budget%incomplete_candidate_cells==evaluation_budget%incomplete_candidate_cells, &
      'background evaluation state is exactly equivalent to omission',failures)

    ! Retrieval uses the trial thermodynamics, while the published candidate
    ! retains the pristine background thermodynamics and observations.
    evaluation=input
    evaluation%temperature%value=300.0_real32
    evaluation%vapor%value=0.002_real32
    CALL refresh_dry_air_mass_measure(evaluation,status)
    IF (status/=STATUS_OK) ERROR STOP 'warm evaluation dry-air refresh failed'
    CALL derive_column_physics(input,warm_output,warm_result,cfg, &
      analysis_budget=warm_budget,evaluation_state=evaluation)
    rho_d=REAL(input%pressure%value(2,2,4),real64)/(287.05_real64*300.0_real64* &
      (1.0_real64+0.002_real64/0.622_real64))
    zlinear=10.0_real64**(0.1_real64*30.0_real64)
    expected_rain=cfg%reference_mass_concentration*(zlinear/1000.0_real64)**0.55_real64/rho_d
    CALL check(warm_result%status==STATUS_OK .AND. &
      ABS(REAL(warm_output%rain%value(2,2,4),real64)-expected_rain)<2.0e-10_real64 .AND. &
      ABS(REAL(warm_output%rain%value(2,2,4),real64)- &
          REAL(background_output%rain%value(2,2,4),real64))>1.0e-8_real64, &
      'trial temperature and vapor independently set radar rain density',failures)
    CALL check(ALL(warm_output%temperature%value==input%temperature%value) .AND. &
      ALL(warm_output%vapor%value==input%vapor%value) .AND. &
      ALL(warm_output%temperature%source==input%temperature%source) .AND. &
      ALL(warm_output%vapor%source==input%vapor%source) .AND. &
      ALL(warm_output%radar_reflectivity%value==input%radar_reflectivity%value) .AND. &
      ALL(warm_output%radar_reflectivity%source==input%radar_reflectivity%source), &
      'evaluation coefficients cannot rewrite background state or observations',failures)

    ! Radar observations, pressure values, and horizontal geometry are part of
    ! the immutable canonical tuple and must reject atomically when changed.
    evaluation=input
    evaluation%radar_reflectivity%value(2,2,4)=35.0_real32
    CALL derive_column_physics(input,invalid_output,invalid_result,cfg, &
      evaluation_state=evaluation)
    CALL check(invalid_result%status==STATUS_FAILED .AND. &
      invalid_result%reason_code==REASON_METADATA .AND. canonical_states_equal(invalid_output,input), &
      'different radar observations reject and preserve the background',failures)

    evaluation=input
    evaluation%pressure%value(2,2,4)=49000.0_real32
    CALL configure_pressure_geometry(evaluation,status)
    CALL refresh_dry_air_mass_measure(evaluation,status)
    CALL derive_column_physics(input,invalid_output,invalid_result,cfg, &
      evaluation_state=evaluation)
    CALL check(invalid_result%status==STATUS_FAILED .AND. &
      invalid_result%reason_code==REASON_METADATA .AND. canonical_states_equal(invalid_output,input), &
      'different pressure geometry rejects and preserves the background',failures)

    evaluation=input
    evaluation%grid%dx=2100.0_real64
    CALL configure_pressure_geometry(evaluation,status)
    CALL refresh_dry_air_mass_measure(evaluation,status)
    CALL derive_column_physics(input,invalid_output,invalid_result,cfg, &
      evaluation_state=evaluation)
    CALL check(invalid_result%status==STATUS_FAILED .AND. &
      invalid_result%reason_code==REASON_METADATA .AND. canonical_states_equal(invalid_output,input), &
      'different horizontal geometry rejects and preserves the background',failures)

    ! A previous candidate is a legal evaluation state, but its precipitation
    ! and diagnostics must not become a second background increment.
    CALL derive_column_physics(input,descendant,descendant_result,cfg, &
      analysis_budget=descendant_budget,evaluation_state=background_output)
    CALL derive_column_physics(input,fresh_output,fresh_result,cfg, &
      analysis_budget=fresh_budget)
    CALL check(descendant_result%status==STATUS_OK .AND. fresh_result%status==STATUS_OK .AND. &
      canonical_states_equal(descendant,fresh_output) .AND. &
      ALL(descendant%rain%value==fresh_output%rain%value) .AND. &
      ALL(descendant_budget%species_change_kg==fresh_budget%species_change_kg) .AND. &
      ALL(descendant_budget%mixing_ratio_change_kg==fresh_budget%mixing_ratio_change_kg) .AND. &
      ALL(descendant_budget%dry_mass_redistribution_kg==fresh_budget%dry_mass_redistribution_kg) .AND. &
      descendant_budget%dry_air_change_kg==fresh_budget%dry_air_change_kg .AND. &
      descendant_budget%enthalpy_change_j==fresh_budget%enthalpy_change_j .AND. &
      descendant_budget%total_mass_error_kg==fresh_budget%total_mass_error_kg .AND. &
      descendant_budget%max_cell_mass_error_kg==fresh_budget%max_cell_mass_error_kg .AND. &
      descendant_budget%accounted_cells==fresh_budget%accounted_cells .AND. &
      descendant_budget%incomplete_background_cells==fresh_budget%incomplete_background_cells .AND. &
      descendant_budget%incomplete_candidate_cells==fresh_budget%incomplete_candidate_cells, &
      'prior candidate evaluation does not repeat precipitation or budget increments',failures)
  END SUBROUTINE test_column_evaluation_state

END PROGRAM test_column_physics
