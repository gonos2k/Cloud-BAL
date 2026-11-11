PROGRAM test_phase_initialization_chain
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: moist_species_enthalpy
  USE cloud_bal_phase_moments
  USE cloud_bal_microphysics_initialization
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: state,output
  TYPE(moment_bundle) :: prior
  TYPE(microphysics_completion_policy) :: policy
  REAL(real64) :: species(6),before(6),t,t_before,nn,nc,bg
  REAL(real32) :: density(1,1,2)
  INTEGER :: status

  CALL initialize_cloud_bal_state(state,1,1,2,0_int64,'phase-chain',status)
  IF (status/=STATUS_OK) ERROR STOP 'initialize state'
  CALL field(state%pressure,90000.0_real32)
  CALL field(state%temperature,280.0_real32)
  CALL field(state%vapor,0.01_real32)
  CALL field(state%cloud_water,0.0_real32)
  CALL field(state%cloud_ice,0.0_real32)
  CALL field(state%rain,0.0_real32)
  CALL field(state%snow,0.0_real32)
  CALL field(state%graupel,0.0_real32)
  ALLOCATE(state%moments%value(1,1,2,5),state%moments%valid(1,1,2,5), &
           state%moments%provenance(1,1,2,5))
  state%moments%value=0.0_real64; state%moments%valid=.TRUE.
  state%moments%provenance=MOMENT_BACKGROUND
  ALLOCATE(prior%value(1,1,2,5),prior%valid(1,1,2,5),prior%provenance(1,1,2,5))
  prior%value=0.0_real64; prior%valid=.FALSE.; prior%provenance=MOMENT_PRIOR
  policy%source='manufactured'; policy%density_source='manufactured'
  policy%mass_threshold=1.e-12_real64; policy%lower=1.e-12_real64; policy%upper=1.e-3_real64
  policy%lower(MOMENT_BG)=100.0_real64; policy%upper(MOMENT_BG)=900.0_real64
  policy%number_cap=1.e10_real64; density=1.0_real32

  species=[0.01_real64,0.001_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64]
  before=species; t=280.0_real64; t_before=t; nn=20.0_real64; nc=80.0_real64
  CALL evaporate_cloud_completely(t,species,nn,nc,status)
  IF (status/=STATUS_OK) ERROR STOP 'evaporation'
  CALL budgets(before,species,t_before,t)
  CALL put_phase(state,t,species)
  state%moments%value(1,1,:,MOMENT_NC)=nc
  state%moments%value(1,1,:,MOMENT_NN)=nn
  output=state
  CALL complete_initialization_state(state,output,prior,policy,status,density)
  IF (status/=STATUS_OK) ERROR STOP 'evaporation completion'
  IF (output%moments%value(1,1,1,MOMENT_NC)/=0.0_real64 .OR. &
      output%moments%value(1,1,1,MOMENT_NN)/=100.0_real64) ERROR STOP 'evaporation moment chain'

  species=[0.01_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64,0.002_real64]
  before=species; t=280.0_real64; t_before=t; bg=0.00001_real64
  CALL melt_graupel_proportionally(t,species,bg,0.0005_real64,status)
  IF (status/=STATUS_OK) ERROR STOP 'melt'
  CALL budgets(before,species,t_before,t)
  CALL put_phase(state,t,species)
  state%moments%value(1,1,:,MOMENT_BG)=bg
  state%moments%valid(1,1,:,MOMENT_NR)=.FALSE.
  prior%valid(1,1,:,MOMENT_NR)=.TRUE.
  prior%value(1,1,:,MOMENT_NR)=1.e-7_real64 ! Declared kg per rain particle.
  output=state
  CALL complete_initialization_state(state,output,prior,policy,status,density)
  IF (status/=STATUS_OK) ERROR STOP 'melt completion'
  IF (output%moments%value(1,1,1,MOMENT_BG)/=bg) ERROR STOP 'BG was not retained'
  IF (output%moments%provenance(1,1,1,MOMENT_NR)/=MOMENT_PRIOR .OR. &
      output%moments%value(1,1,1,MOMENT_NR)<=0.0_real64) ERROR STOP 'rain prior completion'
  IF (ABS(output%moments%value(1,1,1,MOMENT_NR)- &
      REAL(state%rain%value(1,1,1),real64)/1.e-7_real64)>1.e-9_real64) ERROR STOP 'rain prior value'
  PRINT *, 'phase to initialization chain: PASS'
CONTAINS
  SUBROUTINE field(f,x)
    TYPE(field3d), INTENT(INOUT) :: f
    REAL(real32), INTENT(IN) :: x
    f%value=x; f%valid=.TRUE.; f%quality=0_int32; f%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE
  SUBROUTINE put_phase(s,temp,q)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: s
    REAL(real64), INTENT(IN) :: temp,q(6)
    s%temperature%value=REAL(temp,real32); s%vapor%value=REAL(q(1),real32)
    s%cloud_water%value=REAL(q(2),real32); s%cloud_ice%value=REAL(q(3),real32)
    s%rain%value=REAL(q(4),real32); s%snow%value=REAL(q(5),real32); s%graupel%value=REAL(q(6),real32)
  END SUBROUTINE
  SUBROUTINE budgets(old,new,old_t,new_t)
    REAL(real64), INTENT(IN) :: old(6),new(6),old_t,new_t
    REAL(real64) :: h0,h1
    IF (ABS(SUM(new)-SUM(old))>1.e-17_real64) ERROR STOP 'water budget'
    h0=moist_species_enthalpy(old_t,old); h1=moist_species_enthalpy(new_t,new)
    IF (ABS(h1-h0)>1.e-8_real64) ERROR STOP 'enthalpy budget'
    IF (new_t>=old_t) ERROR STOP 'cooling sign'
  END SUBROUTINE
END PROGRAM test_phase_initialization_chain
