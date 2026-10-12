PROGRAM test_force_prior_nullspace
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_balance_operator
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: background,input,output
  TYPE(balance_operator_config) :: config
  TYPE(force_prior_diagnostics) :: diagnostics
  LOGICAL :: control(6,6,4),shell(6,6,4),force(6,6,4)
  INTEGER :: i,j,k
  REAL(real64), PARAMETER :: original_rms=1.0e-3_real64,original_max=2.0e-3_real64
  REAL(real64) :: force_roundoff

  CALL make_state(background)
  control=.FALSE.; shell=.TRUE.; force=.FALSE.
  control(2:5,2:5,:)=.TRUE.
  force(2:5,2:5,:)=.TRUE.
  DO k=1,4; DO j=1,6; DO i=1,6
    background%u%value(i,j,k)=REAL(2.0_real64+0.08_real64*i+0.03_real64*j,real32)
    background%v%value(i,j,k)=REAL(-1.0_real64+0.05_real64*i-0.06_real64*j,real32)
  END DO; END DO; END DO
  input=background
  DO k=1,4; DO j=1,6; DO i=1,6
    input%geopotential%value(i,j,k)=REAL(1000.0_real64+ &
      0.01_real64*REAL(i-1,real64)+0.008_real64*REAL(j-1,real64),real32)
  END DO; END DO; END DO
  input%omega%value(3,3,1)=0.1_real32
  CALL apply_background_force_prior_refinement(background,input,output,config, &
    control,shell,force,original_rms,original_max,diagnostics)
  IF (diagnostics%status/=STATUS_OK) THEN
    PRINT *,'force-prior refinement status/reason:',diagnostics%status,diagnostics%reason
    PRINT *,'objectives:',diagnostics%input_objective,diagnostics%candidate_objective
    PRINT *,'forces:',diagnostics%background_force_rms,diagnostics%input_force_rms, &
      diagnostics%candidate_force_rms
    PRINT *,'nullspace:',diagnostics%projected_increment_rms,diagnostics%projected_increment_max
    PRINT *,'continuity:',diagnostics%continuity_candidate_rms,diagnostics%continuity_candidate_max
    ERROR STOP 'force-prior refinement rejected synthetic prior'
  END IF
  IF (diagnostics%backtracking_steps/=0) &
    ERROR STOP 'well-feasible force-prior candidate unexpectedly backtracked'
  IF (.NOT.(diagnostics%candidate_objective<diagnostics%input_objective)) &
    ERROR STOP 'force-prior objective did not improve'
  IF (.NOT.(diagnostics%candidate_normalized_force_rms< &
            diagnostics%input_normalized_force_rms)) &
    ERROR STOP 'force increment did not move toward immutable background reference'
  force_roundoff=64.0_real64*REAL(EPSILON(1.0_real32),real64)* &
    MAX(diagnostics%input_force_rms,diagnostics%background_force_rms)
  IF (diagnostics%candidate_force_rms>diagnostics%input_force_rms+force_roundoff) &
    ERROR STOP 'absolute force mismatch increased'
  IF (diagnostics%background_force_rms<=0.0_real64 .OR. &
      diagnostics%candidate_force_rms<=0.0_real64) &
    ERROR STOP 'nonzero background force reference was not preserved'
  IF (MAXVAL(ABS(output%omega%value-input%omega%value))>0.0_real32 .OR. &
      MAXVAL(ABS(output%temperature%value-input%temperature%value))>0.0_real32 .OR. &
      MAXVAL(ABS(output%vapor%value-input%vapor%value))>0.0_real32 .OR. &
      MAXVAL(ABS(output%geopotential%value-input%geopotential%value))>0.0_real32) &
    ERROR STOP 'force refinement changed a frozen non-wind field'
  IF (diagnostics%continuity_candidate_rms> &
      MAX(config%solver_residual_fraction*original_rms,config%solver_absolute_tolerance) .OR. &
      diagnostics%continuity_candidate_max> &
      MAX(config%solver_residual_fraction*original_max,config%solver_absolute_tolerance)) &
    ERROR STOP 'REAL32 candidate missed frozen original continuity gate'
  IF (diagnostics%maximum_wind_increment>10.0_real64 .OR. &
      diagnostics%maximum_omega_increment>5.0_real64) &
    ERROR STOP 'candidate exceeded immutable increment caps'
  CALL test_nonzero_background_flux()
  CALL test_float32_continuity_backtracking()
  PRINT *,'PASS force-prior nullspace refinement, nonzero background reference, and frozen continuity gate'

CONTAINS

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER :: local_status,ii,jj,kk
    REAL(real64) :: plev
    CALL initialize_cloud_bal_state(state,6,6,4,1788224400_int64,'force-prior-test',local_status)
    IF (local_status/=STATUS_OK) ERROR STOP 'state initialization failed'
    DO jj=1,6; DO ii=1,6
      state%grid%dx(ii,jj)=2000.0_real64
      state%grid%dy(ii,jj)=2000.0_real64
      DO kk=1,4
        plev=95000.0_real64-15000.0_real64*REAL(kk-1,real64)
        state%pressure%value(ii,jj,kk)=REAL(plev,real32)
        state%temperature%value(ii,jj,kk)=280.0_real32
        state%vapor%value(ii,jj,kk)=0.008_real32
        state%u%value(ii,jj,kk)=0.0_real32
        state%v%value(ii,jj,kk)=0.0_real32
        state%omega%value(ii,jj,kk)=0.0_real32
        state%omega_target%value(ii,jj,kk)=0.0_real32
        state%geopotential%value(ii,jj,kk)=1000.0_real32
      END DO
    END DO; END DO
    CALL valid(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL valid(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL valid(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL valid(state%u,SOURCE_ANALYZED_WIND)
    CALL valid(state%v,SOURCE_ANALYZED_WIND)
    CALL valid(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL valid(state%omega_target,SOURCE_ANALYZED_WIND)
    state%omega_target_sigma%value=0.5_real32
    CALL valid(state%omega_target_sigma,SOURCE_ANALYZED_WIND)
    CALL valid(state%geopotential,SOURCE_BACKGROUND_MODEL)
    state%surface_pressure%value=100000.0_real32
    state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0_int32; state%surface_temperature%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%latitude%value=36.0_real32; state%latitude%valid=.TRUE.
    state%latitude%quality=0_int32; state%latitude%source=SOURCE_BACKGROUND_MODEL
    state%omega_top_boundary%value=0.0_real32
    state%omega_bottom_boundary%value=0.0_real32
    state%omega_top_boundary%valid=.TRUE.; state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=0_int32; state%omega_bottom_boundary%quality=0_int32
    state%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    state%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    CALL configure_pressure_geometry(state,local_status)
    IF (local_status/=STATUS_OK) ERROR STOP 'pressure geometry initialization failed'
    state%balance_beta=0.0_real32
    CALL refresh_dry_air_mass_measure(state,local_status)
    IF (local_status/=STATUS_OK) ERROR STOP 'dry-air mass initialization failed'
  END SUBROUTINE make_state

  SUBROUTINE valid(field,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE valid

  SUBROUTINE test_nonzero_background_flux()
    TYPE(cloud_bal_state_type) :: reference,same,wrong,changed_bottom,refined
    TYPE(balance_operator_config) :: cfg
    TYPE(force_prior_diagnostics) :: result
    TYPE(balance_operator_type) :: diagnostic_op
    LOGICAL :: ctl(6,6,4),sh(6,6,4),fm(6,6,4)
    REAL(real64) :: flux(6,6,4)
    INTEGER :: local_status,local_reason
    CALL make_state(reference)
    reference%u%value=0.2_real32
    reference%v%value=-0.1_real32
    reference%omega%value(:,:,2)=0.2_real32
    same=reference
    ctl=.FALSE.; ctl(2:5,2:5,:)=.TRUE.
    sh=.TRUE.; fm=.FALSE.; fm(2:5,2:5,:)=.TRUE.
    CALL build_diagnostic_balance_operator(reference,diagnostic_op,local_status,local_reason)
    IF (local_status/=STATUS_OK) ERROR STOP 'diagnostic operator setup failed'
    CALL state_dry_air_mass_flux_divergence(diagnostic_op,reference,flux,local_status)
    IF (local_status/=STATUS_OK .OR. MAXVAL(ABS(flux))<=0.0_real64) &
      ERROR STOP 'test background must have nonzero dry-air flux divergence'
    CALL apply_background_force_prior_refinement(reference,same,refined,cfg,ctl,sh,fm, &
      0.0_real64,0.0_real64,result)
    IF (result%status/=STATUS_OK .OR. result%input_objective/=0.0_real64 .OR. &
        result%candidate_objective/=0.0_real64) &
      ERROR STOP 'identical nonzero-divergence background must be a valid no-op'
    wrong=same
    wrong%omega%value(3,3,2)=wrong%omega%value(3,3,2)+1.0_real32
    CALL apply_background_force_prior_refinement(reference,wrong,refined,cfg,ctl,sh,fm, &
      0.0_real64,0.0_real64,result)
    IF (result%status/=STATUS_DEGRADED .OR. result%reason/=REASON_GATE) &
      ERROR STOP 'state outside the frozen background dry-flux prior must be rejected'
    changed_bottom=same
    changed_bottom%omega%value(3,3,1)=changed_bottom%omega%value(3,3,1)+0.1_real32
    CALL apply_background_force_prior_refinement(reference,changed_bottom,refined,cfg,ctl,sh,fm, &
      1.0_real64,1.0_real64,result)
    IF (result%status/=STATUS_OK) THEN
      PRINT *,'changed bottom-center omega status/reason:',result%status,result%reason
      ERROR STOP 'frozen boundary flux must permit an analyzed bottom-center omega value'
    END IF
    IF (refined%omega%value(3,3,1)/=changed_bottom%omega%value(3,3,1) .OR. &
        reference%omega_bottom_boundary%value(3,3)/=refined%omega_bottom_boundary%value(3,3)) &
      ERROR STOP 'refinement must preserve changed center omega and the independent fixed boundary flux'
  END SUBROUTINE test_nonzero_background_flux

  SUBROUTINE test_float32_continuity_backtracking()
    TYPE(cloud_bal_state_type) :: reference,trial,first_candidate,refined
    TYPE(balance_operator_config) :: cfg
    TYPE(force_prior_diagnostics) :: first,backtracked
    TYPE(balance_operator_type) :: diagnostic_op
    LOGICAL :: ctl(6,6,4),sh(6,6,4),fm(6,6,4)
    REAL(real64) :: background_flux(6,6,4),input_flux(6,6,4),input_residual(6,6,4)
    REAL(real64) :: input_rms,input_max,rms_limit,max_limit,continuity_limit_rms,continuity_limit_max
    REAL(real64) :: original_gate_rms,original_gate_max
    INTEGER :: local_status,local_reason,ii,jj,kk
    CALL make_state(reference)
    ctl=.FALSE.; ctl(2:5,2:5,:)=.TRUE.
    sh=.TRUE.; fm=.FALSE.; fm(2:5,2:5,:)=.TRUE.
    DO kk=1,4; DO jj=1,6; DO ii=1,6
      reference%u%value(ii,jj,kk)=REAL(2.0_real64+0.08_real64*ii+0.03_real64*jj,real32)
      reference%v%value(ii,jj,kk)=REAL(-1.0_real64+0.05_real64*ii-0.06_real64*jj,real32)
    END DO; END DO; END DO
    trial=reference
    DO kk=1,4; DO jj=1,6; DO ii=1,6
      trial%geopotential%value(ii,jj,kk)=REAL(1000.0_real64+ &
        0.01_real64*REAL(ii-1,real64)+0.008_real64*REAL(jj-1,real64),real32)
    END DO; END DO; END DO
    trial%omega%value(3,3,1)=0.1_real32
    CALL apply_background_force_prior_refinement(reference,trial,first_candidate,cfg,ctl,sh,fm, &
      1.0e-3_real64,2.0e-3_real64,first)
    IF (first%status/=STATUS_OK .OR. first%backtracking_steps/=0) &
      ERROR STOP 'unconstrained analytic force-prior trial did not pass on its first stored state'
    CALL build_diagnostic_balance_operator(trial,diagnostic_op,local_status,local_reason)
    IF (local_status/=STATUS_OK) ERROR STOP 'backtracking test diagnostic operator failed'
    CALL state_dry_air_mass_flux_divergence(diagnostic_op,reference,background_flux,local_status)
    IF (local_status/=STATUS_OK) ERROR STOP 'backtracking test background flux failed'
    CALL state_dry_air_mass_flux_divergence(diagnostic_op,trial,input_flux,local_status)
    IF (local_status/=STATUS_OK) ERROR STOP 'backtracking test input flux failed'
    input_residual=(input_flux-background_flux)/trial%grid%pressure_mass_measure
    CALL masked_norm(sh,input_residual,input_rms,input_max)
    rms_limit=MAX(2.0_real64*MAX(input_rms,first%continuity_candidate_rms),1.0e-8_real64)
    max_limit=MAX(2.0_real64*MAX(input_max,first%continuity_candidate_max),1.0e-8_real64)
    IF (first%continuity_candidate_rms>input_rms) &
      rms_limit=0.5_real64*(first%continuity_candidate_rms+input_rms)
    IF (first%continuity_candidate_max>input_max) &
      max_limit=0.5_real64*(first%continuity_candidate_max+input_max)
    IF (rms_limit>=first%continuity_candidate_rms .AND. &
        max_limit>=first%continuity_candidate_max) &
      ERROR STOP 'synthetic setup did not expose float32 continuity storage error'
    original_gate_rms=rms_limit/2.0e-3_real64
    original_gate_max=max_limit/2.0e-3_real64
    continuity_limit_rms=MAX(2.0e-3_real64*original_gate_rms,1.0e-12_real64)
    continuity_limit_max=MAX(2.0e-3_real64*original_gate_max,1.0e-12_real64)
    CALL apply_background_force_prior_refinement(reference,trial,refined,cfg,ctl,sh,fm, &
      original_gate_rms,original_gate_max,backtracked)
    IF (backtracked%status/=STATUS_OK .OR. backtracked%backtracking_steps<=0) THEN
      PRINT *,'backtracking diagnostics status/reason/steps:',backtracked%status, &
        backtracked%reason,backtracked%backtracking_steps
      PRINT *,'input and candidate RMS:',input_rms,first%continuity_candidate_rms, &
        backtracked%continuity_candidate_rms
      PRINT *,'limits:',continuity_limit_rms,continuity_limit_max
      ERROR STOP 'float32 storage-feasibility case did not accept a strict backtracked trial'
    END IF
    IF (backtracked%continuity_candidate_rms>continuity_limit_rms .OR. &
        backtracked%continuity_candidate_max>continuity_limit_max) &
      ERROR STOP 'stored backtracking candidate violated the unchanged continuity limits'
    IF (backtracked%candidate_objective>=backtracked%input_objective) &
      ERROR STOP 'stored backtracking candidate did not strictly improve the existing force objective'
    IF (backtracked%candidate_force_rms>backtracked%input_force_rms+ &
        64.0_real64*REAL(EPSILON(1.0_real32),real64)* &
        MAX(backtracked%input_force_rms,backtracked%background_force_rms)) &
      ERROR STOP 'stored backtracking candidate increased absolute force beyond its existing allowance'
    IF (backtracked%maximum_wind_increment>MIN(10.0_real64,cfg%maximum_wind_increment)*cfg%increment_headroom .OR. &
        backtracked%maximum_omega_increment>MIN(5.0_real64,cfg%maximum_omega_increment)*cfg%increment_headroom) &
      ERROR STOP 'stored backtracking candidate exceeded existing hard increments'
    IF (backtracked%projected_increment_rms/=first%projected_increment_rms .OR. &
        backtracked%projected_increment_max/=first%projected_increment_max) &
      ERROR STOP 'backtracking changed the accepted analytic continuity-null direction'
    IF (MAXVAL(ABS(refined%omega%value-trial%omega%value))>0.0_real32 .OR. &
        MAXVAL(ABS(refined%temperature%value-trial%temperature%value))>0.0_real32 .OR. &
        MAXVAL(ABS(refined%vapor%value-trial%vapor%value))>0.0_real32 .OR. &
        MAXVAL(ABS(refined%geopotential%value-trial%geopotential%value))>0.0_real32) &
      ERROR STOP 'stored backtracking changed a frozen non-wind field'
    PRINT *,'PASS stored-state continuity backtracking steps:',backtracked%backtracking_steps
  END SUBROUTINE test_float32_continuity_backtracking

  SUBROUTINE masked_norm(mask,values,rms,max_abs)
    LOGICAL,INTENT(IN)::mask(:,:,:)
    REAL(real64),INTENT(IN)::values(:,:,:)
    REAL(real64),INTENT(OUT)::rms,max_abs
    REAL(real64)::sum_squares,value
    INTEGER::ii,jj,kk,sample_count
    sample_count=COUNT(mask)
    IF (sample_count<=0) ERROR STOP 'masked norm requires nonempty support'
    sum_squares=0.0_real64; max_abs=0.0_real64
    DO kk=1,SIZE(values,3); DO jj=1,SIZE(values,2); DO ii=1,SIZE(values,1)
      IF (.NOT.mask(ii,jj,kk)) CYCLE
      value=ABS(values(ii,jj,kk))
      sum_squares=sum_squares+value*value
      max_abs=MAX(max_abs,value)
    END DO; END DO; END DO
    rms=SQRT(sum_squares/REAL(sample_count,real64))
  END SUBROUTINE masked_norm

END PROGRAM test_force_prior_nullspace
