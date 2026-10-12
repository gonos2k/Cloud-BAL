PROGRAM test_thermo_density_prior
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  USE cloud_bal_column_physics
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: background,proposal,output,restored,bad
  TYPE(thermodynamic_density_prior_config) :: config
  TYPE(stage_result) :: stage
  TYPE(pressure_analysis_budget) :: budget
  LOGICAL :: support(3,1,2),saturated(3,1,2)
  INTEGER :: surface(3,1,2),status,i
  REAL(real64) :: a0,ab,a1,water0(6),water1(6),hb,ha,expected_h,expected_water(6),p,t

  CALL make_state(background)
  proposal=background
  proposal%temperature%value(:,1,1)=282.0_real32
  proposal%cloud_water%value(2,1,1)=0.0_real32
  p=85000.0_real64; t=282.0_real64
  proposal%vapor%value(1:2,1,1)=REAL(qsat(t,p),real32)
  CALL refresh_dry_air_mass_measure(proposal,status)
  IF (status/=STATUS_OK) ERROR STOP 'proposal mass'
  proposal%grid%dry_air_mass_measure(1,1,2)=proposal%grid%dry_air_mass_measure(1,1,2)*(1.0_real64+1.0e-8_real64)
  support=.FALSE.; support(:,1,1)=.TRUE.
  saturated=.FALSE.; saturated(1:2,1,1)=.TRUE.; surface=SATURATION_LIQUID
  config%enabled=.TRUE.; config%background_weight=0.5_real64
  config%max_temperature_increment=5.0_real64; config%max_vapor_increment=0.005_real64
  CALL apply_thermodynamic_density_prior(background,proposal,output,stage,config, &
    support,saturated,surface,1.0_real64,budget)
  IF (stage%status/=STATUS_OK) ERROR STOP 'joint prior failed'
  IF (ANY(output%grid%dry_air_mass_measure(:,:,2)/=proposal%grid%dry_air_mass_measure(:,:,2))) &
    ERROR STOP 'unselected dry-mass carrier changed'
  expected_h=0.0_real64; expected_water=0.0_real64
  DO i=1,3
    water0=water(proposal,i); water1=water(output,i)
    a0=alpha(proposal,i); ab=alpha(background,i); a1=alpha(output,i)
    IF (ABS(a1-0.5_real64*(a0+ab))>1.0e-6_real64*ABS(ab)) ERROR STOP 'independent alpha target'
    IF (i<=2) THEN
      p=REAL(output%pressure%value(i,1,1),real64); t=REAL(output%temperature%value(i,1,1),real64)
      IF (ABS(water1(1)-qsat(t,p))>2.0e-7_real64) ERROR STOP 'active saturation boundary'
    ELSE
      IF (water1(1)/=water0(1)) ERROR STOP 'vapor outside thermo mask changed'
    END IF
    hb=enthalpy(REAL(proposal%temperature%value(i,1,1),real64),water0)
    ha=enthalpy(REAL(output%temperature%value(i,1,1),real64),water1)
    expected_h=expected_h+output%grid%dry_air_mass_measure(i,1,1)*ha- &
      proposal%grid%dry_air_mass_measure(i,1,1)*hb
    expected_water=expected_water+output%grid%dry_air_mass_measure(i,1,1)*water1- &
      proposal%grid%dry_air_mass_measure(i,1,1)*water0
  END DO
  IF (ABS(budget%enthalpy_change_j-expected_h)>1.0e-4_real64) ERROR STOP 'independent enthalpy ledger'
  IF (MAXVAL(ABS(budget%species_change_kg-expected_water))>1.0e-8_real64) ERROR STOP 'independent water ledger'
  restored=output
  restored%temperature=proposal%temperature; restored%vapor=proposal%vapor
  restored%grid%dry_air_mass_measure=proposal%grid%dry_air_mass_measure
  IF (.NOT.canonical_states_equal(restored,proposal)) ERROR STOP 'condensates observations geometry immutable'
  IF (output%cloud_water%value(2,1,1)/=0.0_real32) ERROR STOP 'empty reservoir filled'
  IF (output%vapor%value(2,1,1)>=proposal%vapor%value(2,1,1)) ERROR STOP 'inactive reservoir vapor analysis'
  config%background_weight=0.0_real64
  CALL apply_thermodynamic_density_prior(background,proposal,output,stage,config, &
    support,saturated,surface,1.0_real64,budget)
  IF (stage%status/=STATUS_OK .OR. .NOT.canonical_states_equal(proposal,output)) ERROR STOP 'zero weight identity'
  config%background_weight=0.5_real64; config%max_temperature_increment=1.0e-6_real64
  CALL apply_thermodynamic_density_prior(background,proposal,output,stage,config, &
    support,saturated,surface,1.0_real64,budget)
  IF (stage%status==STATUS_OK .OR. .NOT.canonical_states_equal(output,proposal)) ERROR STOP 'cap rollback'
  IF (budget%enthalpy_change_j/=0.0_real64 .OR. ANY(budget%species_change_kg/=0.0_real64)) ERROR STOP 'rollback ledger'
  config%max_temperature_increment=5.0_real64
  bad=background; bad%cloud_water%valid(1,1,1)=.FALSE.
  CALL apply_thermodynamic_density_prior(bad,proposal,output,stage,config, &
    support,saturated,surface,1.0_real64,budget)
  IF (stage%status==STATUS_OK .OR. .NOT.canonical_states_equal(output,proposal)) ERROR STOP 'missing input rollback'
  config%background_weight=ieee_value(0.0_real64,ieee_quiet_nan)
  CALL apply_thermodynamic_density_prior(background,proposal,output,stage,config, &
    support,saturated,surface,1.0_real64,budget)
  IF (stage%status==STATUS_OK .OR. .NOT.canonical_states_equal(output,proposal)) ERROR STOP 'nonfinite prior rollback'
  PRINT *, 'Thermodynamic density-prior tests passed'
CONTAINS
  PURE REAL(real64) FUNCTION qsat(t,p)
    REAL(real64), INTENT(IN) :: t,p
    REAL(real64) :: es
    es=611.2_real64*EXP(17.67_real64*(t-273.15_real64)/(t-29.65_real64))
    qsat=0.622_real64*es/(p-es)
  END FUNCTION
  FUNCTION water(s,i) RESULT(w)
    TYPE(cloud_bal_state_type), INTENT(IN) :: s
    INTEGER, INTENT(IN) :: i
    REAL(real64) :: w(6)
    w=REAL([s%vapor%value(i,1,1),s%cloud_water%value(i,1,1),s%cloud_ice%value(i,1,1), &
      s%rain%value(i,1,1),s%snow%value(i,1,1),s%graupel%value(i,1,1)],real64)
  END FUNCTION
  REAL(real64) FUNCTION alpha(s,i)
    TYPE(cloud_bal_state_type), INTENT(IN) :: s
    INTEGER, INTENT(IN) :: i
    REAL(real64) :: w(6)
    w=water(s,i)
    alpha=287.05_real64*REAL(s%temperature%value(i,1,1),real64)*(1.0_real64+w(1)/0.622_real64)/(1.0_real64+SUM(w))
  END FUNCTION
  PURE REAL(real64) FUNCTION enthalpy(t,w)
    REAL(real64), INTENT(IN) :: t,w(6)
    enthalpy=(1004.5_real64+SUM(w*[1846.4_real64,4190.0_real64,2106.0_real64, &
      4190.0_real64,2106.0_real64,2106.0_real64]))*(t-273.15_real64)+ &
      SUM(w*[2.5e6_real64,0.0_real64,-3.5e5_real64,0.0_real64,-3.5e5_real64,-3.5e5_real64])
  END FUNCTION

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER(int64), PARAMETER :: vt=1788224400_int64
    INTEGER :: i,j,k,status,reason
    CALL initialize_cloud_bal_state(state,3,1,2,vt,'pressure-thermo-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization failed'
    state%grid%dx=2000.0_real64; state%grid%dy=2200.0_real64
    DO k=1,2; DO j=1,1; DO i=1,3
      state%pressure%value(i,j,k)=REAL(MERGE(85000.0_real64,65000.0_real64,k==1),real32)
      state%temperature%value(i,j,k)=280.0_real32; state%vapor%value(i,j,k)=0.008_real32
      state%u%value(i,j,k)=2.0_real32; state%v%value(i,j,k)=-1.0_real32
      state%omega%value(i,j,k)=0.2_real32; state%omega_target%value(i,j,k)=0.3_real32
      state%geopotential%value(i,j,k)=100.0_real32; state%cloud_fraction%value(i,j,k)=0.2_real32
      state%radar_reflectivity%value(i,j,k)=10.0_real32; state%cloud_type%value(i,j,k)=1_int32
      state%precipitation_phase%value(i,j,k)=1_int32; state%lightning_support%value(i,j,k)=1_int32
      state%vt_z_mean%value(i,j,k)=0.5_real32; state%vt_z_sigma%value(i,j,k)=0.1_real32
      CALL set_water(state,i,j,k,0.003_real64,0.001_real64,0.002_real64,0.001_real64,0.001_real64)
    END DO; END DO; END DO
    CALL valid_real(state%pressure,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vapor,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%u,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%v,SOURCE_ANALYZED_WIND); CALL valid_real(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%omega_target,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_fraction,SOURCE_CLOUD_ANALYSIS); CALL valid_real(state%radar_reflectivity,SOURCE_RADAR_DBZ)
    CALL valid_integer(state%cloud_type,SOURCE_CLOUD_ANALYSIS); CALL valid_integer(state%precipitation_phase,SOURCE_BACKGROUND_MODEL)
    CALL valid_integer(state%lightning_support,SOURCE_BACKGROUND_MODEL); CALL valid_real(state%vt_z_mean,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vt_z_sigma,SOURCE_BACKGROUND_MODEL)
    state%surface_pressure%value=100000.0_real32; state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.; state%surface_pressure%quality=0_int32
    state%surface_temperature%quality=0_int32; state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL; state%obs_support=1_int32; state%hydro_support=1_int32
    state%balance_beta=0.35_real32
    CALL configure_pressure_geometry(state,status); IF (status/=STATUS_OK) ERROR STOP 'geometry failed'
    CALL refresh_dry_air_mass_measure(state,status); IF (status/=STATUS_OK) ERROR STOP 'mass failed'
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) ERROR STOP 'fixture is not canonical'
  END SUBROUTINE make_state

  SUBROUTINE set_water(state,i,j,k,liquid,ice,rain,snow,graupel)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64), INTENT(IN) :: liquid,ice,rain,snow,graupel
    state%cloud_water%value(i,j,k)=REAL(liquid,real32); state%cloud_ice%value(i,j,k)=REAL(ice,real32)
    state%rain%value(i,j,k)=REAL(rain,real32); state%snow%value(i,j,k)=REAL(snow,real32)
    state%graupel%value(i,j,k)=REAL(graupel,real32)
    state%cloud_water%valid(i,j,k)=.TRUE.; state%cloud_ice%valid(i,j,k)=.TRUE.; state%rain%valid(i,j,k)=.TRUE.
    state%snow%valid(i,j,k)=.TRUE.; state%graupel%valid(i,j,k)=.TRUE.; state%cloud_water%quality(i,j,k)=0_int32
    state%cloud_ice%quality(i,j,k)=0_int32; state%rain%quality(i,j,k)=0_int32; state%snow%quality(i,j,k)=0_int32
    state%graupel%quality(i,j,k)=0_int32; state%cloud_water%source(i,j,k)=SOURCE_BACKGROUND_MODEL
    state%cloud_ice%source(i,j,k)=SOURCE_BACKGROUND_MODEL; state%rain%source(i,j,k)=SOURCE_BACKGROUND_MODEL
    state%snow%source(i,j,k)=SOURCE_BACKGROUND_MODEL; state%graupel%source(i,j,k)=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE set_water

  SUBROUTINE valid_real(field,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE valid_real

  SUBROUTINE valid_integer(field,source)
    TYPE(integer_field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE valid_integer
END PROGRAM test_thermo_density_prior
