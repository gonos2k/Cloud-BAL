PROGRAM test_balance_operator
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  USE cloud_bal_balance_operator
  IMPLICIT NONE

  INTEGER :: failures
  failures=0
  CALL test_operator_identities(failures)
  CALL test_actual_operator_nullspace(failures)
  CALL test_uniform_flow_compact_support(failures)
  CALL test_geostrophic_boundary_coverage(failures)
  CALL test_stage_transaction(failures)
  CALL test_weighted_operator_reference(failures)
  CALL test_uncertainty_weighted_correction(failures)
  CALL test_missing_target_uncertainty_noop(failures)
  CALL test_malformed_target_uncertainty_rejection(failures)
  CALL test_trust_region(failures)
  CALL test_nonzero_background_residual(failures)
  CALL test_target_authority_by_component(failures)
  CALL test_target_response_gate(failures)
  CALL test_beta_threshold(failures)
  CALL test_los_rejection_diagnostics(failures)
  CALL test_disconnected_support(failures)
  CALL test_boundary_contract_rejection(failures)
  CALL test_copied_boundary_has_no_dynamic_authority(failures)
  CALL test_manufactured_target_is_test_only(failures)
  CALL test_model_dynamic_target_contract(failures)
  CALL test_model_dynamic_bounded_projection(failures)
  CALL test_observational_model_boundary_rejection(failures)
  CALL test_target_metadata_rejection(failures)
  CALL test_pressure_order_rejection(failures)
  CALL test_malformed_dimension_rejection(failures)
  CALL test_small_domain_rejection(failures)
  IF (failures/=0) THEN
    PRINT *,'Balance operator tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Balance operator tests passed'

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

  SUBROUTINE make_balance_state(state,nx,ny,nz)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER :: i,j,k,status
    REAL(real64) :: pressure_step
    INTEGER(int64), PARAMETER :: valid_time=1788224400_int64
    REAL(real64) :: plev

    CALL initialize_cloud_bal_state(state,nx,ny,nz,valid_time,'operator-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state init'
    pressure_step=15000.0_real64
    IF (nz>6) pressure_step=10000.0_real64
    DO j=1,ny; DO i=1,nx
      state%grid%dx(i,j)=1200.0_real64+31.0_real64*i+7.0_real64*j
      state%grid%dy(i,j)=1800.0_real64+13.0_real64*i+29.0_real64*j
      DO k=1,nz
        plev=95000.0_real64-pressure_step*REAL(k-1,real64)
        state%pressure%value(i,j,k)=REAL(plev,real32)
        state%temperature%value(i,j,k)=280.0_real32
        state%vapor%value(i,j,k)=0.008_real32
        state%u%value(i,j,k)=0.0_real32
        state%v%value(i,j,k)=0.0_real32
        state%omega%value(i,j,k)=0.0_real32
        state%omega_target%value(i,j,k)=REAL(0.08_real64* &
          SIN(0.7_real64*i)*COS(0.5_real64*j)*SIN(ACOS(-1.0_real64)* &
          REAL(k,real64)/REAL(nz+1,real64)),real32)
        state%geopotential%value(i,j,k)=1000.0_real32
      END DO
    END DO; END DO
    CALL mark_valid(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%u,SOURCE_ANALYZED_WIND)
    CALL mark_valid(state%v,SOURCE_ANALYZED_WIND)
    CALL mark_valid(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%omega_target,IOR(SOURCE_ANALYZED_WIND, &
      IOR(SOURCE_COLUMN_PHYSICS,SOURCE_DYNAMIC_TARGET)))
    ! Synthetic observational fixture: this is an explicit finite uncertainty,
    ! not a claim that the target is calibrated real-world retrieval data.
    state%omega_target_sigma%value=0.5_real32
    CALL mark_valid(state%omega_target_sigma,SOURCE_ANALYZED_WIND)
    CALL mark_valid(state%geopotential,SOURCE_BACKGROUND_MODEL)
    state%surface_pressure%value=100000.0_real32
    state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0; state%surface_temperature%quality=0
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%latitude%value=36.0_real32; state%latitude%valid=.TRUE.
    state%latitude%quality=0; state%latitude%source=SOURCE_BACKGROUND_MODEL
    state%omega_top_boundary%value=0.0_real32
    state%omega_bottom_boundary%value=0.0_real32
    state%omega_top_boundary%valid=.TRUE.
    state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=0; state%omega_bottom_boundary%quality=0
    state%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    state%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure geometry initialization failed'
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      state%balance_beta(i,j,k)=REAL(0.25_real64+0.75_real64* &
        SIN(ACOS(-1.0_real64)*REAL(i,real64)/REAL(nx+1,real64))**2* &
        SIN(ACOS(-1.0_real64)*REAL(j,real64)/REAL(ny+1,real64))**2,real32)
    END DO; END DO; END DO
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'dry-air mass initialization failed'
  END SUBROUTINE make_balance_state

  SUBROUTINE mark_valid(field,source_bit)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source_bit
    field%valid=.TRUE.; field%quality=0_int32; field%source=source_bit
  END SUBROUTINE mark_valid

  SUBROUTINE test_operator_identities(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64), ALLOCATABLE :: xu(:,:,:),xv(:,:,:),xo(:,:,:),lambda(:,:,:)
    REAL(real64), ALLOCATABLE :: ax(:,:,:),atu(:,:,:),atv(:,:,:),ato(:,:,:)
    REAL(real64), ALLOCATABLE :: gu(:,:,:),gv(:,:,:),go(:,:,:),ag(:,:,:),ll(:,:,:)
    REAL(real64) :: lhs,rhs,error,scale,quad
    INTEGER :: status,reason,i,j,k

    CALL make_balance_state(state,6,5,4)
    CALL build_balance_operator(state,cfg,op,status,reason)
    CALL check(status==STATUS_OK,'operator construction',failures)
    CALL snapshot_balance_operator(op,view,status)
    CALL check(status==STATUS_OK,'operator inspection',failures)
    ALLOCATE(xu(6,5,4),xv(6,5,4),xo(6,5,4),lambda(6,5,4),ax(6,5,4), &
             atu(6,5,4),atv(6,5,4),ato(6,5,4),gu(6,5,4),gv(6,5,4), &
             go(6,5,4),ag(6,5,4),ll(6,5,4))
    DO k=1,4; DO j=1,5; DO i=1,6
      xu(i,j,k)=SIN(0.13_real64*i+0.17_real64*j+0.19_real64*k)
      xv(i,j,k)=COS(0.23_real64*i-0.11_real64*j+0.07_real64*k)
      xo(i,j,k)=0.03_real64*SIN(0.31_real64*i+0.29_real64*k)
      lambda(i,j,k)=COS(0.37_real64*i+0.21_real64*j-0.15_real64*k)
    END DO; END DO; END DO
    CALL apply_continuity_operator(op,xu,xv,xo,ax,status)
    CALL check(status==STATUS_OK,'A application',failures)
    CALL apply_adjoint_metric(op,lambda,atu,atv,ato,status)
    lhs=SUM(view%volume*lambda*ax,MASK=view%cell_active)
    rhs=SUM(atu*xu+atv*xv+ato*xo)
    scale=MAX(ABS(lhs),ABS(rhs),1.0e-30_real64)
    error=ABS(lhs-rhs)/scale
    CALL check(status==STATUS_OK .AND. error<5.0e-13_real64, &
               'metric adjoint identity',failures)

    CALL apply_balance_correction(op,lambda,gu,gv,go,status)
    CALL apply_continuity_operator(op,gu,gv,go,ag,status)
    CALL apply_normal_operator(op,lambda,ll,status)
    scale=MAX(MAXVAL(ABS(ll),MASK=view%cell_active),1.0e-30_real64)
    error=MAXVAL(ABS(ll+ag),MASK=view%cell_active)/scale
    CALL check(error<5.0e-13_real64,'L equals -A G pointwise',failures)
    quad=SUM(view%volume*lambda*ll,MASK=view%cell_active)
    CALL check(quad>=-1.0e-12_real64*MAX(1.0_real64,ABS(quad)), &
               'normal operator must be positive semidefinite',failures)

    xv=0.0_real64; xo=0.0_real64
    CALL apply_continuity_operator(op,xu,xv,xo,ax,status)
    CALL check(MAXVAL(ABS(ax),MASK=view%cell_active)>0.0_real64, &
               'u-axis pattern must contribute',failures)
    xu=0.0_real64; xv=1.0_real64
    CALL apply_continuity_operator(op,xu,xv,xo,ax,status)
    CALL check(MAXVAL(ABS(ax),MASK=view%cell_active)>0.0_real64, &
               'v-axis pattern must contribute',failures)
    xv=0.0_real64; xo=1.0_real64
    CALL apply_continuity_operator(op,xu,xv,xo,ax,status)
    CALL check(MAXVAL(ABS(ax),MASK=view%cell_active)>0.0_real64, &
               'omega-axis pattern must include zero-flux boundaries',failures)
  END SUBROUTINE test_operator_identities

  SUBROUTINE test_actual_operator_nullspace(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64), ALLOCATABLE :: lambda(:,:,:),l_lambda(:,:,:)
    INTEGER :: status,reason,i,j,k,pattern

    CALL make_balance_state(state,6,6,4)
    state%grid%dx=2000.0_real64; state%grid%dy=2000.0_real64
    CALL configure_pressure_geometry(state,status)
    state%balance_beta=1.0_real32
    CALL refresh_dry_air_mass_measure(state,status)
    CALL build_balance_operator(state,cfg,op,status,reason)
    CALL snapshot_balance_operator(op,view,status)
    CALL check(status==STATUS_OK .AND. view%ncomponent==4, &
      'uniform A-grid operator must expose four horizontal parity gauges',failures)
    ALLOCATE(lambda(6,6,4),l_lambda(6,6,4))
    DO pattern=1,3
      DO k=1,4; DO j=1,6; DO i=1,6
        SELECT CASE(pattern)
        CASE(1); lambda(i,j,k)=MERGE(1.0_real64,-1.0_real64,MOD(i,2)==0)
        CASE(2); lambda(i,j,k)=MERGE(1.0_real64,-1.0_real64,MOD(j,2)==0)
        CASE(3); lambda(i,j,k)=MERGE(1.0_real64,-1.0_real64,MOD(i+j,2)==0)
        END SELECT
      END DO; END DO; END DO
      CALL apply_normal_operator(op,lambda,l_lambda,status)
      CALL check(status==STATUS_OK .AND. &
        MAXVAL(ABS(l_lambda),MASK=view%cell_active)<1.0e-14_real64, &
        'checkerboard multiplier must be an explicit normal-operator gauge',failures)
    END DO
  END SUBROUTINE test_actual_operator_nullspace

  SUBROUTINE test_uniform_flow_compact_support(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64), ALLOCATABLE :: residual(:,:,:)
    INTEGER :: status,reason

    CALL make_balance_state(state,6,5,4)
    state%grid%dx=2000.0_real64; state%grid%dy=2000.0_real64
    CALL configure_pressure_geometry(state,status)
    state%u%value=4.0_real32; state%v%value=-3.0_real32
    state%omega%value=0.0_real32
    state%balance_beta=0.0_real32
    state%balance_beta(2:5,2:4,:)=1.0_real32
    CALL refresh_dry_air_mass_measure(state,status)
    CALL build_balance_operator(state,cfg,op,status,reason)
    CALL snapshot_balance_operator(op,view,status)
    ALLOCATE(residual(6,5,4))
    CALL state_continuity_residual(op,state,residual,status)
    CALL check(status==STATUS_OK .AND. &
      MAXVAL(ABS(residual),MASK=view%cell_active)<1.0e-14_real64, &
      'uniform flow must remain divergence free across compact-support edges',failures)
  END SUBROUTINE test_uniform_flow_compact_support

  SUBROUTINE test_geostrophic_boundary_coverage(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    REAL(real64) :: before,after
    INTEGER :: status,reason

    CALL make_balance_state(background,6,5,4)
    CALL build_balance_operator(background,cfg,op,status,reason)
    candidate=background
    candidate%u%value(3,5,2)=5.0_real32
    candidate%v%value(6,3,2)=5.0_real32
    CALL geostrophic_residual(background,op,before,status)
    CALL geostrophic_residual(candidate,op,after,status)
    CALL check(status==STATUS_OK .AND. before==0.0_real64 .AND. after>0.0_real64, &
      'geostrophic diagnostic must include north/east tangential wind',failures)
  END SUBROUTINE test_geostrophic_boundary_coverage

  SUBROUTINE test_stage_transaction(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output,no_source
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg

    CALL make_balance_state(input,6,5,4)
    cfg%required_residual_fraction=0.50_real64
    cfg%minimum_target_response_ratio=0.0_real64
    cfg%maximum_target_response_ratio=100.0_real64
    cfg%geostrophic_absolute_tolerance=0.10_real64
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK,'localized balance stage must converge',failures)
    CALL check(result%numerical%continuity_projected_increment_rms < &
               result%numerical%continuity_proposed_increment_rms+1.0e-12_real64, &
               'full pre-correction continuity residual must decrease',failures)
    CALL check(result%numerical%max_wind_increment<=cfg%maximum_wind_increment, &
               'wind increment gate',failures)
    CALL check(result%numerical%continuity_operator_identity_max<= &
               cfg%solver_absolute_tolerance, &
               'full-state and increment residuals must use one operator',failures)

    no_source=input
    no_source%omega_target%valid=.FALSE.
    no_source%omega_target_sigma%valid=.FALSE.
    no_source%omega_target_sigma%quality=QUALITY_RAW_MISSING
    no_source%omega_target_sigma%source=0_int32
    CALL apply_localized_balance(no_source,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
               ALL(TRANSFER(output%u%value,[0_int32])== &
                   TRANSFER(no_source%u%value,[0_int32])), &
               'no target must be exact no-op',failures)
  END SUBROUTINE test_stage_transaction

  SUBROUTINE test_weighted_operator_reference(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state,tight_state
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op,tight_op
    TYPE(balance_operator_snapshot) :: view
    REAL(real64), ALLOCATABLE :: lambda(:,:,:),atu(:,:,:),atv(:,:,:),atomega(:,:,:)
    REAL(real64), ALLOCATABLE :: du(:,:,:),dv(:,:,:),domega(:,:,:)
    REAL(real64), ALLOCATABLE :: tight_du(:,:,:),tight_dv(:,:,:),tight_domega(:,:,:)
    REAL(real64) :: b_eff,r,expected,error,scale
    INTEGER :: i,j,k,status,reason

    CALL make_balance_state(state,6,5,4)
    CALL build_balance_operator(state,cfg,op,status,reason)
    CALL snapshot_balance_operator(op,view,status)
    ALLOCATE(lambda(6,5,4),atu(6,5,4),atv(6,5,4),atomega(6,5,4), &
             du(6,5,4),dv(6,5,4),domega(6,5,4))
    DO k=1,4; DO j=1,5; DO i=1,6
      lambda(i,j,k)=SIN(0.17_real64*i+0.23_real64*j-0.31_real64*k)
    END DO; END DO; END DO
    CALL apply_adjoint_metric(op,lambda,atu,atv,atomega,status)
    CALL apply_balance_correction(op,lambda,du,dv,domega,status)
    error=0.0_real64; scale=1.0_real64
    DO k=1,4; DO j=1,5; DO i=1,6
      IF (.NOT.view%omega_authorized(i,j,k)) CYCLE
      b_eff=REAL(state%balance_beta(i,j,k),real64)*cfg%kappa_omega
      r=REAL(state%omega_target_sigma%value(i,j,k),real64)**2
      expected=b_eff*r/(b_eff+r)
      error=MAX(error,ABS(domega(i,j,k)+expected*atomega(i,j,k)))
      scale=MAX(scale,ABS(expected*atomega(i,j,k)))
    END DO; END DO; END DO
    CALL check(status==STATUS_OK .AND. error/scale<5.0e-13_real64, &
      'omega correction must use the exact B_eff R/(B_eff+R) posterior weight',failures)

    tight_state=state
    tight_state%omega_target_sigma%value=0.05_real32
    CALL build_balance_operator(tight_state,cfg,tight_op,status,reason)
    ALLOCATE(tight_du(6,5,4),tight_dv(6,5,4),tight_domega(6,5,4))
    CALL apply_balance_correction(tight_op,lambda,tight_du,tight_dv,tight_domega,status)
    CALL check(status==STATUS_OK .AND. MAXVAL(ABS(du-tight_du))<1.0e-13_real64 .AND. &
      MAXVAL(ABS(dv-tight_dv))<1.0e-13_real64, &
      'horizontal corrections must remain unchanged when sigma changes',failures)
  END SUBROUTINE test_weighted_operator_reference

  SUBROUTINE test_uncertainty_weighted_correction(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: base,tight,loose,tight_out,loose_out
    TYPE(stage_result) :: tight_result,loose_result
    TYPE(balance_operator_config) :: cfg
    REAL(real64) :: tight_change,loose_change
    INTEGER :: i,j,k

    CALL make_balance_state(base,6,5,4)
    tight=base; loose=base
    tight%omega_target_sigma%value=0.05_real32
    loose%omega_target_sigma%value=5.0_real32
    cfg%required_residual_fraction=0.50_real64
    cfg%minimum_target_response_ratio=0.0_real64
    cfg%maximum_target_response_ratio=100.0_real64
    cfg%maximum_wind_increment=100.0_real64
    cfg%maximum_omega_increment=100.0_real64
    cfg%minimum_trust_region_fraction=1.0e-8_real64
    cfg%physical_residual_tolerance=1.0_real64
    cfg%maximum_physical_residual=1.0_real64
    cfg%geostrophic_absolute_tolerance=100.0_real64

    CALL apply_localized_balance(tight,tight_out,tight_result,cfg)
    CALL apply_localized_balance(loose,loose_out,loose_result,cfg)
    CALL check(tight_result%status==STATUS_OK .AND. loose_result%status==STATUS_OK, &
      'finite tight and loose target uncertainties must both solve',failures)
    CALL check(tight_result%status==STATUS_OK .AND. loose_result%status==STATUS_OK .AND. &
      tight_result%numerical%continuity_candidate_rms<= &
        tight_result%numerical%continuity_background_rms+cfg%physical_residual_tolerance .AND. &
      loose_result%numerical%continuity_candidate_rms<= &
        loose_result%numerical%continuity_background_rms+cfg%physical_residual_tolerance, &
      'uncertainty-weighted candidates must satisfy continuity gates',failures)
    CALL check(tight_result%status==STATUS_OK .AND. loose_result%status==STATUS_OK .AND. &
      .NOT.ANY(tight_result%changed .AND. .NOT.base%above_ground) .AND. &
      .NOT.ANY(loose_result%changed .AND. .NOT.base%above_ground), &
      'uncertainty-weighted corrections must stay inside physical support',failures)
    tight_change=0.0_real64; loose_change=0.0_real64
    DO k=1,base%grid%nz; DO j=1,base%grid%ny; DO i=1,base%grid%nx
      tight_change=MAX(tight_change,ABS(REAL(tight_out%omega%value(i,j,k),real64)- &
        REAL(base%omega%value(i,j,k),real64)))
      loose_change=MAX(loose_change,ABS(REAL(loose_out%omega%value(i,j,k),real64)- &
        REAL(base%omega%value(i,j,k),real64)))
    END DO; END DO; END DO
    CALL check(tight_result%status==STATUS_OK .AND. loose_result%status==STATUS_OK .AND. &
      tight_change>loose_change+1.0e-7_real64, &
      'tight uncertainty must produce a materially stronger omega correction',failures)
    CALL check(same_field(tight_out%omega_target_sigma,tight%omega_target_sigma) .AND. &
      same_field(loose_out%omega_target_sigma,loose%omega_target_sigma), &
      'balance must preserve target uncertainty metadata',failures)
  END SUBROUTINE test_uncertainty_weighted_correction

  SUBROUTINE test_missing_target_uncertainty_noop(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg

    CALL make_balance_state(input,6,5,4)
    input%omega_target_sigma%valid=.FALSE.
    input%omega_target_sigma%quality=QUALITY_RAW_MISSING
    input%omega_target_sigma%source=0_int32
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
      result%numerical%solver_reason==SOLVER_NOT_RUN .AND. &
      same_field(output%u,input%u) .AND. same_field(output%v,input%v) .AND. &
      same_field(output%omega,input%omega), &
      'missing target uncertainty must make an observational target a no-op',failures)
  END SUBROUTINE test_missing_target_uncertainty_noop

  SUBROUTINE test_malformed_target_uncertainty_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    REAL(real32) :: original_sigma

    CALL make_balance_state(input,6,5,4)
    original_sigma=input%omega_target_sigma%value(3,3,2)
    input%omega_target_sigma%value=0.0_real32
    input%omega_target_sigma%valid=.TRUE.
    input%omega_target_sigma%quality=0_int32
    input%omega_target_sigma%source=SOURCE_ANALYZED_WIND
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
      same_field(output%u,input%u) .AND. same_field(output%v,input%v) .AND. &
      same_field(output%omega,input%omega) .AND. &
      same_field(output%omega_target_sigma,input%omega_target_sigma), &
      'zero valid target uncertainty must reject atomically',failures)

    input%omega_target_sigma%value=original_sigma
    input%omega_target_sigma%value(3,3,2)=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
      same_field(output%u,input%u) .AND. same_field(output%v,input%v) .AND. &
      same_field(output%omega,input%omega) .AND. &
      same_field(output%omega_target_sigma,input%omega_target_sigma), &
      'nonfinite valid target uncertainty must reject atomically',failures)
  END SUBROUTINE test_malformed_target_uncertainty_rejection

  SUBROUTINE test_trust_region(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    REAL(real64) :: accepted_fraction,actual_maximum
    INTEGER :: i,j,k

    CALL make_balance_state(input,6,5,4)
    input%omega_target%value=400.0_real32*input%omega_target%value
    cfg%required_residual_fraction=0.50_real64
    cfg%minimum_target_response_ratio=0.0_real64
    cfg%maximum_target_response_ratio=100.0_real64
    cfg%maximum_wind_increment=0.10_real64
    cfg%maximum_omega_increment=0.05_real64
    cfg%minimum_trust_region_fraction=1.0e-6_real64
    cfg%physical_residual_tolerance=1.0_real64
    cfg%maximum_physical_residual=1.0_real64
    cfg%geostrophic_absolute_tolerance=100.0_real64
    CALL apply_localized_balance(input,output,result,cfg)
    accepted_fraction=result%numerical%trust_region_fraction
    CALL check(result%status==STATUS_OK .AND. accepted_fraction>0.0_real64 .AND. &
               accepted_fraction<1.0_real64, &
               'trust region must scale one linear solution',failures)
    CALL check(result%numerical%max_wind_increment<=cfg%maximum_wind_increment .AND. &
               result%numerical%max_omega_increment<=cfg%maximum_omega_increment, &
               'scaled candidate must satisfy both increment limits',failures)
    CALL check(ALL(TRANSFER(output%omega_target%value,[0_int32], &
                           SIZE(output%omega_target%value))== &
                   TRANSFER(input%omega_target%value,[0_int32], &
                           SIZE(input%omega_target%value))) .AND. &
               ALL(output%omega_target%valid .EQV. input%omega_target%valid) .AND. &
               ALL(output%omega_target%quality==input%omega_target%quality) .AND. &
               ALL(output%omega_target%source==input%omega_target%source), &
               'balance must preserve the requested omega target',failures)
    actual_maximum=0.0_real64
    DO k=1,input%grid%nz; DO j=1,input%grid%ny; DO i=1,input%grid%nx
      actual_maximum=MAX(actual_maximum,HYPOT( &
        REAL(output%u%value(i,j,k)-input%u%value(i,j,k),real64), &
        REAL(output%v%value(i,j,k)-input%v%value(i,j,k),real64)))
    END DO; END DO; END DO
    CALL check(ABS(actual_maximum-result%numerical%max_wind_increment)<1.0e-7_real64, &
               'wind gate and diagnostics must use vector magnitude',failures)

    cfg%minimum_trust_region_fraction=MIN(1.0_real64,accepted_fraction+0.01_real64)
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_DEGRADED .AND. &
               IAND(result%numerical%acceptance_failures,GATE_TARGET_FRACTION)/=0, &
               'trust region below the declared useful fraction must reject',failures)
  END SUBROUTINE test_trust_region

  SUBROUTINE test_nonzero_background_residual(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    INTEGER :: i,j,k

    CALL make_balance_state(input,6,5,4)
    DO k=1,4; DO j=1,5; DO i=1,6
      input%u%value(i,j,k)=REAL(0.4_real64*SIN(0.6_real64*i+0.2_real64*j),real32)
    END DO; END DO; END DO
    cfg%required_residual_fraction=0.50_real64
    cfg%minimum_target_response_ratio=0.0_real64
    cfg%maximum_target_response_ratio=100.0_real64
    cfg%geostrophic_absolute_tolerance=1.0_real64
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK, &
               'target projection must tolerate an unchanged background residual',failures)
    CALL check(result%numerical%continuity_projected_increment_rms<= &
               cfg%required_residual_fraction* &
               result%numerical%continuity_proposed_increment_rms+ &
               cfg%solver_absolute_tolerance, &
               'same increment operator must close the target proposal',failures)
    CALL check(result%numerical%continuity_candidate_rms<= &
               result%numerical%continuity_background_rms+ &
               cfg%physical_residual_tolerance, &
               'candidate physical residual must not exceed background',failures)
  END SUBROUTINE test_nonzero_background_residual

  SUBROUTINE test_target_authority_by_component(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg

    CALL make_balance_state(input,9,7,4)
    input%balance_beta=0.0_real32
    input%balance_beta(2:4,2:4,:)=1.0_real32
    input%balance_beta(6:8,4:6,:)=1.0_real32
    input%omega_target%valid=.FALSE.
    input%omega_target%value=input%omega%value
    input%omega_target%value(3,3,3)=0.08_real32
    input%omega_target%valid(3,3,3)=.TRUE.
    input%omega_target_sigma%valid=.FALSE.
    input%omega_target_sigma%quality=QUALITY_RAW_MISSING
    input%omega_target_sigma%source=0_int32
    input%omega_target_sigma%value(3,3,3)=0.5_real32
    input%omega_target_sigma%valid(3,3,3)=.TRUE.
    input%omega_target_sigma%quality(3,3,3)=0_int32
    input%omega_target_sigma%source(3,3,3)=SOURCE_ANALYZED_WIND
    input%u%value(6:8,4:6,:)=-0.0_real32
    input%v%value(6:8,4:6,:)=-0.0_real32
    input%omega%value(6:8,4:6,:)=-0.0_real32
    cfg%required_residual_fraction=0.50_real64
    cfg%minimum_target_response_ratio=0.0_real64
    cfg%maximum_target_response_ratio=100.0_real64
    cfg%geostrophic_absolute_tolerance=1.0_real64
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK, &
      'authorized component must solve independently',failures)
    CALL check(ALL(TRANSFER(output%u%value(6:8,4:6,:),[0_int32],36)== &
                   TRANSFER(input%u%value(6:8,4:6,:),[0_int32],36)) .AND. &
               ALL(TRANSFER(output%v%value(6:8,4:6,:),[0_int32],36)== &
                   TRANSFER(input%v%value(6:8,4:6,:),[0_int32],36)) .AND. &
               ALL(TRANSFER(output%omega%value(6:8,4:6,:),[0_int32],36)== &
                   TRANSFER(input%omega%value(6:8,4:6,:),[0_int32],36)), &
      'component without a dynamic target must remain bitwise unchanged',failures)
  END SUBROUTINE test_target_authority_by_component

  SUBROUTINE test_target_response_gate(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_config) :: cfg
    REAL(real64), ALLOCATABLE :: target(:,:,:),increment(:,:,:)
    REAL(real64) :: failed_fraction
    INTEGER :: status,reason

    CALL make_balance_state(input,6,5,4)
    CALL build_balance_operator(input,cfg,op,status,reason)
    ALLOCATE(target(6,5,4),increment(6,5,4))
    target=0.01_real64; increment=target
    increment(2:5,2:4,:)=0.0_real64
    failed_fraction=target_response_failure_fraction( &
      op,increment,target,1.0e-12_real64,0.05_real64,1.50_real64)
    CALL check(status==STATUS_OK .AND. failed_fraction>0.0_real64, &
      'cellwise target gate must catch widespread weak-target cancellation',failures)
    increment=0.0025_real64*target
    failed_fraction=target_response_failure_fraction( &
      op,increment,target,1.0e-12_real64,0.05_real64,1.50_real64)
    CALL check(failed_fraction>0.0_real64, &
      'response must be measured against the original requested target',failures)
    increment=2.0_real64*target
    failed_fraction=target_response_failure_fraction( &
      op,increment,target,1.0e-12_real64,0.05_real64,1.50_real64)
    CALL check(failed_fraction>0.0_real64, &
      'cellwise target gate must catch same-sign amplification',failures)
  END SUBROUTINE test_target_response_gate

  SUBROUTINE test_beta_threshold(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    TYPE(stage_result) :: result
    REAL(real32) :: rounded_below,next_above
    INTEGER :: status,reason

    CALL make_balance_state(input,6,5,4)
    input%omega_target%valid=.FALSE.
    input%omega_target%value=input%omega%value
    input%omega_target%value(3,3,2)=0.08_real32
    input%omega_target%valid(3,3,2)=.TRUE.
    input%omega_target_sigma%valid=.FALSE.
    input%omega_target_sigma%quality=QUALITY_RAW_MISSING
    input%omega_target_sigma%source=0_int32
    input%omega_target_sigma%value(3,3,2)=0.5_real32
    input%omega_target_sigma%valid(3,3,2)=.TRUE.
    input%omega_target_sigma%quality(3,3,2)=0_int32
    input%omega_target_sigma%source(3,3,2)=SOURCE_ANALYZED_WIND
    rounded_below=REAL(cfg%minimum_beta,real32)
    next_above=NEAREST(rounded_below,1.0_real32)
    CALL check(.NOT.balance_beta_active(rounded_below,cfg%minimum_beta) .AND. &
               balance_beta_active(next_above,cfg%minimum_beta), &
               'minimum-beta comparison must use one real64 rule',failures)
    input%balance_beta=0.0_real32
    input%balance_beta(3,3,2)=rounded_below
    CALL build_balance_operator(input,cfg,op,status,reason)
    CALL snapshot_balance_operator(op,view,status)
    CALL check(status==STATUS_OK .AND. COUNT(view%cell_active)==0, &
               'rounded-below beta must remain inactive',failures)
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
               result%reason_code==REASON_AUTHORITY, &
      'a resolved target without active localization must not report success',failures)
    ! A pressure increment needs an adjacent active level so that its flux is
    ! closed inside the compact support.
    input%balance_beta(3,3,1:3)=next_above
    CALL build_balance_operator(input,cfg,op,status,reason)
    CALL snapshot_balance_operator(op,view,status)
    CALL check(status==STATUS_OK, &
               'next representable beta must build a valid operator',failures)
    IF (status==STATUS_OK) THEN
      CALL check(COUNT(view%cell_active)==3, &
                 'next representable beta must become active',failures)
    END IF
  END SUBROUTINE test_beta_threshold

  SUBROUTINE test_los_rejection_diagnostics(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,candidate,rejected
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    INTEGER :: location(3),component

    CALL make_balance_state(input,6,5,4)
    input%omega_target%value=400.0_real32*input%omega_target%value
    cfg%required_residual_fraction=0.50_real64
    cfg%minimum_target_response_ratio=0.0_real64
    cfg%maximum_target_response_ratio=100.0_real64
    cfg%maximum_wind_increment=100.0_real64
    cfg%maximum_omega_increment=100.0_real64
    cfg%minimum_trust_region_fraction=1.0e-4_real64
    cfg%physical_residual_tolerance=1.0e-2_real64
    cfg%maximum_physical_residual=1.0e-2_real64
    cfg%geostrophic_absolute_tolerance=100.0_real64
    cfg%minimum_held_out_samples=1
    cfg%minimum_held_out_radars=1
    CALL apply_localized_balance(input,candidate,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
               result%numerical%max_wind_increment>0.10_real64, &
               'LOS fixture requires a resolved horizontal increment',failures)
    IF (MAXVAL(ABS(candidate%u%value))>=MAXVAL(ABS(candidate%v%value))) THEN
      location=MAXLOC(ABS(candidate%u%value)); component=1
    ELSE
      location=MAXLOC(ABS(candidate%v%value)); component=2
    END IF
    CALL add_held_out_los(input,location(1),location(2),location(3),component)
    CALL apply_localized_balance(input,rejected,result,cfg)
    CALL check(result%status==STATUS_DEGRADED .AND. &
               result%reason_code==REASON_GATE .AND. result%los_gate_applied .AND. &
               .NOT.result%los_gate_passed .AND. &
               result%coverage%los_held_out==1 .AND. &
               result%los_rms_candidate>result%los_threshold .AND. &
               result%numerical%solver_iterations>0, &
               'LOS rejection must preserve its audit diagnostics',failures)
    CALL check(ALL(TRANSFER(rejected%u%value,[0_int32],SIZE(rejected%u%value))== &
                   TRANSFER(input%u%value,[0_int32],SIZE(input%u%value))), &
               'LOS rejection must rollback the candidate',failures)
  END SUBROUTINE test_los_rejection_diagnostics

  SUBROUTINE add_held_out_los(state,ii,jj,kk,component)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(IN) :: ii,jj,kk,component
    INTEGER :: nx,ny,nz
    INTEGER(int64) :: valid_time

    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    valid_time=state%pressure%valid_time
    state%radar_los%is_present=.TRUE.; state%radar_los%nradar=1
    state%radar_los%vrad_representation=VRAD_DEALIASED
    CALL initialize_field(state%radar_los%vrad,nx,ny,nz,1,valid_time,'m s-1')
    CALL initialize_field(state%radar_los%nyquist,nx,ny,nz,1,valid_time,'m s-1')
    CALL initialize_field(state%radar_los%sigma_vrad,nx,ny,nz,1,valid_time,'m s-1')
    ALLOCATE(state%radar_los%beam(nx,ny,nz,1,3), &
      state%radar_los%observation_id_hi(nx,ny,nz,1), &
      state%radar_los%observation_id_lo(nx,ny,nz,1), &
      state%radar_los%usage(nx,ny,nz,1),state%radar_los%los_support(nx,ny,nz,1), &
      state%radar_los%radar_id(1),state%radar_los%observation_time(1), &
      state%radar_los%site_lat(1),state%radar_los%site_lon(1), &
      state%radar_los%site_height(1),state%radar_los%wavelength(1), &
      state%radar_los%geometry_condition(nx,ny,nz), &
      state%radar_los%geometry_rank(nx,ny,nz))
    state%radar_los%beam=0.0_real32
    state%radar_los%beam(ii,jj,kk,1,component)=1.0_real32
    state%radar_los%observation_id_hi=0_int64
    state%radar_los%observation_id_lo=0_int64
    state%radar_los%usage=LOS_REJECTED
    state%radar_los%los_support=0_int32
    state%radar_los%observation_id_hi(ii,jj,kk,1)=100_int64
    state%radar_los%observation_id_lo(ii,jj,kk,1)=INT(ii,int64)+INT(nx,int64)*( &
      INT(jj-1,int64)+INT(ny,int64)*INT(kk-1,int64))
    state%radar_los%usage(ii,jj,kk,1)=LOS_HELD_OUT
    state%radar_los%los_support(ii,jj,kk,1)=1_int32
    state%radar_los%radar_id=100_int32
    state%radar_los%observation_time=valid_time
    state%radar_los%site_lat=36.0_real64; state%radar_los%site_lon=128.0_real64
    state%radar_los%site_height=100.0_real64; state%radar_los%wavelength=0.10_real64
    state%radar_los%geometry_condition=1.0_real32
    state%radar_los%geometry_rank=1_int32
    state%radar_los%vrad%value(ii,jj,kk,1)=0.0_real32
    state%radar_los%nyquist%value(ii,jj,kk,1)=15.0_real32
    state%radar_los%sigma_vrad%value(ii,jj,kk,1)=1.0_real32
    state%radar_los%vrad%valid(ii,jj,kk,1)=.TRUE.
    state%radar_los%nyquist%valid(ii,jj,kk,1)=.TRUE.
    state%radar_los%sigma_vrad%valid(ii,jj,kk,1)=.TRUE.
    state%radar_los%vrad%quality(ii,jj,kk,1)=0_int32
    state%radar_los%nyquist%quality(ii,jj,kk,1)=0_int32
    state%radar_los%sigma_vrad%quality(ii,jj,kk,1)=0_int32
    state%radar_los%vrad%source(ii,jj,kk,1)=SOURCE_RADAR_VRAD
    state%radar_los%nyquist%source(ii,jj,kk,1)=SOURCE_RADAR_VRAD
    state%radar_los%sigma_vrad%source(ii,jj,kk,1)=SOURCE_RADAR_VRAD
    state%vt_z_mean%value(ii,jj,kk)=0.0_real32
    state%vt_z_sigma%value(ii,jj,kk)=0.0_real32
    state%vt_z_mean%valid(ii,jj,kk)=.TRUE.
    state%vt_z_sigma%valid(ii,jj,kk)=.TRUE.
    state%vt_z_mean%quality(ii,jj,kk)=0_int32
    state%vt_z_sigma%quality(ii,jj,kk)=0_int32
    state%vt_z_mean%source(ii,jj,kk)=SOURCE_RADAR_VRAD
    state%vt_z_sigma%source(ii,jj,kk)=SOURCE_RADAR_VRAD
  END SUBROUTINE add_held_out_los

  SUBROUTINE test_disconnected_support(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    TYPE(balance_operator_snapshot) :: view
    INTEGER :: status,reason

    CALL make_balance_state(input,6,5,4)
    input%balance_beta=0.0_real32
    input%balance_beta(2,2,:)=1.0_real32
    input%balance_beta(5,4,:)=1.0_real32
    CALL build_balance_operator(input,cfg,op,status,reason)
    CALL snapshot_balance_operator(op,view,status)
    CALL check(status==STATUS_OK .AND. view%ncomponent==2, &
               'separated compact supports must have separate gauges',failures)

    input%balance_beta=0.0_real32
    input%balance_beta(2,2,2)=1.0_real32
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status/=STATUS_OK, &
               'isolated omega target must be rejected',failures)
    CALL check(ALL(TRANSFER(output%omega%value,[0_int32],SIZE(output%omega%value))== &
                   TRANSFER(input%omega%value,[0_int32],SIZE(input%omega%value))), &
               'isolated omega target must remain unchanged',failures)
  END SUBROUTINE test_disconnected_support

  SUBROUTINE test_boundary_contract_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg

    CALL make_balance_state(input,6,5,4)
    input%omega_top_boundary%valid(3,3)=.FALSE.
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
               result%reason_code==REASON_METADATA, &
               'invalid boundary contract must reject unchanged',failures)
    CALL check(ALL(TRANSFER(output%omega%value,[0_int32],SIZE(output%omega%value))== &
                   TRANSFER(input%omega%value,[0_int32],SIZE(input%omega%value))), &
               'boundary rejection must preserve omega',failures)
  END SUBROUTINE test_boundary_contract_rejection

  SUBROUTINE test_copied_boundary_has_no_dynamic_authority(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    INTEGER :: status,reason

    CALL make_balance_state(input,6,5,4)
    input%omega_top_boundary%quality=QUALITY_BOUNDARY_INTERIOR_COPY
    input%omega_bottom_boundary%quality=QUALITY_BOUNDARY_INTERIOR_COPY
    CALL check(.NOT.physical_boundary_contract_valid(input), &
      'interior-copy omega is not a physical boundary condition',failures)
    CALL build_balance_operator(input,cfg,op,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
      'low-level operator build must reject copied dynamic boundaries',failures)
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
               result%reason_code==REASON_AUTHORITY, &
      'dynamic balance must reject diagnostic-only omega boundaries',failures)
    CALL check(ALL(TRANSFER(output%omega%value,[0_int32],SIZE(output%omega%value))== &
                   TRANSFER(input%omega%value,[0_int32],SIZE(input%omega%value))), &
      'boundary authority rejection must preserve omega',failures)

    CALL make_balance_state(input,6,5,4)
    input%omega_top_boundary%source=SOURCE_BACKGROUND_MODEL
    input%omega_bottom_boundary%source=SOURCE_BACKGROUND_MODEL
    CALL check(.NOT.physical_boundary_contract_valid(input), &
      'untagged background omega is not a physical boundary condition',failures)
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
               result%reason_code==REASON_AUTHORITY, &
      'dynamic balance must require positive boundary provenance',failures)
  END SUBROUTINE test_copied_boundary_has_no_dynamic_authority

  SUBROUTINE test_manufactured_target_is_test_only(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    INTEGER(int32), PARAMETER :: target_source = &
      IOR(SOURCE_DYNAMIC_TARGET,SOURCE_MANUFACTURED_TEST)
    INTEGER(int32), PARAMETER :: boundary_source = &
      IOR(SOURCE_BOUNDARY_CONDITION,SOURCE_MANUFACTURED_TEST)

    CALL make_balance_state(input,6,5,4)
    input%omega_target%source=target_source
    input%omega_target_sigma%valid=.FALSE.
    input%omega_target_sigma%quality=QUALITY_RAW_MISSING
    input%omega_target_sigma%source=0_int32
    input%omega_top_boundary%source=boundary_source
    input%omega_bottom_boundary%source=boundary_source
    cfg%required_residual_fraction=0.50_real64
    cfg%minimum_target_response_ratio=0.0_real64
    cfg%maximum_target_response_ratio=100.0_real64
    cfg%physical_residual_tolerance=1.0_real64
    cfg%maximum_physical_residual=1.0_real64
    cfg%geostrophic_absolute_tolerance=100.0_real64

    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
               result%reason_code==REASON_AUTHORITY, &
      'observational mode must reject a manufactured target',failures)
    CALL check(.NOT.physical_boundary_contract_valid(input), &
      'manufactured boundaries are not physical evidence',failures)

    ! A manufactured sigma is equally non-observational and must not enter the
    ! direct observational operator, even with an otherwise valid target.
    input%omega_target%source=IOR(SOURCE_ANALYZED_WIND,SOURCE_DYNAMIC_TARGET)
    input%omega_target_sigma%value=0.5_real32
    input%omega_target_sigma%valid=.TRUE.
    input%omega_target_sigma%quality=0_int32
    input%omega_target_sigma%source=IOR(SOURCE_ANALYZED_WIND,SOURCE_MANUFACTURED_TEST)
    input%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    input%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY .AND. &
               same_field(output%u,input%u) .AND. same_field(output%v,input%v) .AND. &
               same_field(output%omega,input%omega), &
      'observational mode must reject manufactured target uncertainty',failures)

    cfg%target_authority=TARGET_AUTHORITY_MANUFACTURED_TEST
    input%omega_target%source=target_source
    input%omega_target_sigma%valid=.FALSE.
    input%omega_target_sigma%quality=QUALITY_RAW_MISSING
    input%omega_target_sigma%source=0_int32
    input%omega_top_boundary%source=boundary_source
    input%omega_bottom_boundary%source=boundary_source
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
               result%numerical%solver_reason==SOLVER_CONVERGED .AND. &
               ANY(result%changed), &
      'explicit test mode must exercise a nonzero manufactured solve',failures)

    input%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    input%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
               result%reason_code==REASON_AUTHORITY, &
      'manufactured mode must require test-only boundary provenance',failures)

    input%omega_top_boundary%source=boundary_source
    input%omega_bottom_boundary%source=boundary_source
    input%omega_target%source=IOR(target_source,SOURCE_ANALYZED_WIND)
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
               result%reason_code==REASON_AUTHORITY, &
      'manufactured targets must reject mixed observational provenance',failures)
  END SUBROUTINE test_manufactured_target_is_test_only

  SUBROUTINE test_model_dynamic_target_contract(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    INTEGER(int32), PARAMETER :: model_source=IOR( &
      SOURCE_BACKGROUND_MODEL,SOURCE_DYNAMIC_TARGET)

    CALL make_balance_state(input,6,5,7)
    cfg%target_authority=TARGET_AUTHORITY_MODEL_DYNAMICS
    cfg%boundary_increment_contract=BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL
    cfg%required_residual_fraction=0.50_real64
    cfg%minimum_target_response_ratio=0.0_real64
    cfg%maximum_target_response_ratio=100.0_real64
    cfg%physical_residual_tolerance=1.0_real64
    cfg%maximum_physical_residual=1.0_real64
    cfg%geostrophic_absolute_tolerance=100.0_real64
    input%model_target_coverage=.TRUE.
    input%omega_target%value=input%omega%value
    input%omega_target%valid=.FALSE.
    input%omega_target%quality=QUALITY_RAW_MISSING
    input%omega_target%source=0_int32
    input%omega_target%valid(:,:,3:5)=.TRUE.
    input%omega_target%quality(:,:,3:5)=0_int32
    input%omega_target%source(:,:,3:5)=model_source
    ! Model dynamics has no empirical sigma. Invalid sigma payload is ignored.
    input%omega_target_sigma%valid=.FALSE.
    input%omega_target_sigma%quality=QUALITY_RAW_MISSING
    input%omega_target_sigma%source=0_int32
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
               result%numerical%solver_reason==SOLVER_NOT_RUN .AND. &
               .NOT.ANY(result%changed), &
      'zero model target must be resolved without a sigma or solver call',failures)

    input%omega_target%valid=.FALSE.
    input%omega_target%quality=QUALITY_RAW_MISSING
    input%omega_target%source=0_int32
    input%omega_target%valid(3,3,4)=.TRUE.
    input%omega_target%quality(3,3,4)=0_int32
    input%omega_target%source(3,3,4)=model_source
    input%omega_target%value(3,3,4)=0.08_real32
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. ANY(result%changed), &
      'nonzero model target must reach the balance solver',failures)

    input%omega_target%valid=.FALSE.
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY, &
      'missing model target must be rejected without inventing a zero target',failures)

    input%omega_target%value=input%omega%value
    input%omega_target%valid=.FALSE.
    input%omega_target%quality=QUALITY_RAW_MISSING
    input%omega_target%source=0_int32
    input%omega_target%valid(:,:,3:5)=.TRUE.
    input%omega_target%quality(:,:,3:5)=0_int32
    input%omega_target%source(:,:,3:5)=model_source
    input%omega_top_boundary%value=1.0_real32
    input%omega_bottom_boundary%value=-1.0_real32
    input%omega_top_boundary%source=SOURCE_BACKGROUND_MODEL
    input%omega_bottom_boundary%source=SOURCE_BACKGROUND_MODEL
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
      model_boundary_increment_contract_valid(input,output) .AND. &
      ALL(output%omega_top_boundary%value==input%omega_top_boundary%value) .AND. &
      ALL(output%omega_bottom_boundary%value==input%omega_bottom_boundary%value), &
      'model correction must preserve arbitrary valid baseline boundaries',failures)
    input%omega_top_boundary%valid=.FALSE.
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_METADATA, &
      'model target must require a valid baseline boundary payload',failures)
  END SUBROUTINE test_model_dynamic_target_contract

  SUBROUTINE test_model_dynamic_bounded_projection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output,rejected,before
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    INTEGER(int32), PARAMETER :: model_source=IOR( &
      SOURCE_BACKGROUND_MODEL,SOURCE_DYNAMIC_TARGET)
    REAL(real64) :: q,increment,ratio,tolerance,strict_rms,strict_max
    LOGICAL :: response_box_ok
    INTEGER :: i,j,k,status

    CALL make_balance_state(input,6,5,7)
    cfg%target_authority=TARGET_AUTHORITY_MODEL_DYNAMICS
    cfg%boundary_increment_contract=BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL
    cfg%required_residual_fraction=0.50_real64
    cfg%minimum_target_response_ratio=0.05_real64
    cfg%maximum_target_response_ratio=1.50_real64
    cfg%physical_residual_tolerance=1.0_real64
    cfg%maximum_physical_residual=1.0_real64
    cfg%geostrophic_absolute_tolerance=100.0_real64
    input%grid%dx=2000.0_real64
    input%grid%dy=2000.0_real64
    CALL configure_pressure_geometry(input,status)
    CALL refresh_dry_air_mass_measure(input,status)
    input%model_target_coverage=.TRUE.
    ! Use the smooth mixed-sign target made by make_balance_state across the
    ! five covered interior levels.  This gives the closed operator a balanced
    ! domain budget while retaining a representable model response interval.
    input%omega_target%valid=.FALSE.
    input%omega_target%quality=QUALITY_RAW_MISSING
    input%omega_target%source=0_int32
    input%omega_target%valid(:,:,3:5)=.TRUE.
    input%omega_target%quality(:,:,3:5)=0_int32
    input%omega_target%source(:,:,3:5)=model_source
    input%omega_target_sigma%valid=.FALSE.
    input%omega_target_sigma%quality=QUALITY_RAW_MISSING
    input%omega_target_sigma%source=0_int32

    CALL apply_localized_balance(input,output,result,cfg)
    strict_rms=MAX(cfg%solver_residual_fraction* &
      result%numerical%continuity_proposed_increment_rms, &
      cfg%solver_absolute_tolerance)
    strict_max=MAX(cfg%solver_residual_fraction* &
      result%numerical%continuity_proposed_increment_max, &
      cfg%solver_absolute_tolerance)
    response_box_ok=.TRUE.
    DO k=1,input%grid%nz; DO j=1,input%grid%ny; DO i=1,input%grid%nx
      IF (.NOT.input%omega_target%valid(i,j,k)) CYCLE
      q=REAL(input%omega_target%value(i,j,k),real64)- &
        REAL(input%omega%value(i,j,k),real64)
      IF (ABS(q)<=cfg%solver_absolute_tolerance) CYCLE
      increment=REAL(output%omega%value(i,j,k),real64)- &
        REAL(input%omega%value(i,j,k),real64)
      ratio=increment/q
      tolerance=64.0_real64*REAL(EPSILON(1.0_real32),real64)* &
        MAX(1.0_real64,ABS(ratio),cfg%minimum_target_response_ratio, &
            cfg%maximum_target_response_ratio)
      IF (ratio<cfg%minimum_target_response_ratio-tolerance .OR. &
          ratio>cfg%maximum_target_response_ratio+tolerance) &
        response_box_ok=.FALSE.
    END DO; END DO; END DO
    CALL check(result%status==STATUS_OK .AND. response_box_ok .AND. &
      result%numerical%target_response_failure_fraction<= &
        cfg%maximum_target_response_failure_fraction .AND. &
      result%numerical%continuity_projected_increment_rms<=strict_rms .AND. &
      result%numerical%continuity_projected_increment_max<=strict_max, &
      'model bounded projection must close the stored increment inside the original response box',failures)
    CALL check(result%status==STATUS_OK .AND. &
      same_field(output%omega_target,input%omega_target) .AND. &
      ALL(output%model_target_coverage .EQV. input%model_target_coverage) .AND. &
      ALL(output%balance_beta==input%balance_beta), &
      'accepted model projection must preserve target and coverage metadata',failures)

    before=input
    cfg%maximum_omega_increment=1.0e-6_real64
    CALL apply_localized_balance(before,rejected,result,cfg)
    CALL check(result%status/=STATUS_OK .AND. &
      same_field(rejected%u,before%u) .AND. same_field(rejected%v,before%v) .AND. &
      same_field(rejected%omega,before%omega) .AND. &
      same_field(rejected%omega_target,before%omega_target) .AND. &
      ALL(rejected%model_target_coverage .EQV. before%model_target_coverage) .AND. &
      ALL(rejected%balance_beta==before%balance_beta) .AND. &
      ALL(rejected%omega_top_boundary%value==before%omega_top_boundary%value) .AND. &
      ALL(rejected%omega_bottom_boundary%value==before%omega_bottom_boundary%value) .AND. &
      .NOT.ANY(result%changed) .AND. result%numerical%trust_region_fraction==0.0_real64, &
      'infeasible model bounds must rollback the full state, target mask, and trust result',failures)
  END SUBROUTINE test_model_dynamic_bounded_projection

  SUBROUTINE test_observational_model_boundary_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg

    CALL make_balance_state(input,6,5,7)
    cfg%boundary_increment_contract=BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_RANGE .AND. &
      same_field(output%u,input%u) .AND. same_field(output%v,input%v) .AND. &
      same_field(output%omega,input%omega), &
      'observational authority must reject the model-only boundary enum unchanged',failures)
  END SUBROUTINE test_observational_model_boundary_rejection

  SUBROUTINE test_target_metadata_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg

    CALL make_balance_state(input,6,5,4)
    input%omega_target%unit='m s-1'
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. &
               result%reason_code==REASON_METADATA, &
               'omega target unit mismatch must reject unchanged',failures)
  END SUBROUTINE test_target_metadata_rejection

  SUBROUTINE test_pressure_order_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    INTEGER :: status,reason

    CALL make_balance_state(input,6,5,4)
    input%pressure%value(3,3,3)=input%pressure%value(3,3,2)+100.0_real32
    CALL build_balance_operator(input,cfg,op,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_RANGE, &
               'non-monotone pressure must be rejected',failures)
  END SUBROUTINE test_pressure_order_rejection

  SUBROUTINE test_malformed_dimension_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg

    CALL make_balance_state(input,6,5,4)
    input%grid%nx=-1
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. SIZE(result%changed,1)==0, &
               'negative metadata dimension must reject without allocation failure',failures)
  END SUBROUTINE test_malformed_dimension_rejection

  SUBROUTINE test_small_domain_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    CALL make_balance_state(input,3,4,2)
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_SHAPE, &
               'nx<4 must fail unchanged before access',failures)
    input%omega_target%valid=.FALSE.
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_SHAPE, &
               'nx<4 no-target state must fail at the same public boundary',failures)
  END SUBROUTINE test_small_domain_rejection

  LOGICAL FUNCTION same_field(left,right)
    TYPE(field3d), INTENT(IN) :: left,right
    same_field=ALL(TRANSFER(left%value,[0_int32],SIZE(left%value))== &
                   TRANSFER(right%value,[0_int32],SIZE(right%value))) .AND. &
      ALL(left%valid .EQV. right%valid) .AND. &
      ALL(left%quality==right%quality) .AND. ALL(left%source==right%source) .AND. &
      left%valid_time==right%valid_time .AND. left%unit==right%unit
  END FUNCTION same_field

END PROGRAM test_balance_operator
