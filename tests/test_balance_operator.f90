PROGRAM test_balance_operator
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_balance_operator
  IMPLICIT NONE

  INTEGER :: failures
  failures=0
  CALL test_operator_identities(failures)
  CALL test_stage_transaction(failures)
  CALL test_nonzero_background_residual(failures)
  CALL test_disconnected_support(failures)
  CALL test_boundary_contract_rejection(failures)
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
    INTEGER(int64), PARAMETER :: valid_time=1788224400_int64
    REAL(real64) :: plev

    CALL initialize_cloud_bal_state(state,nx,ny,nz,valid_time,'operator-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state init'
    DO j=1,ny; DO i=1,nx
      state%grid%dx(i,j)=1200.0_real64+31.0_real64*i+7.0_real64*j
      state%grid%dy(i,j)=1800.0_real64+13.0_real64*i+29.0_real64*j
      DO k=1,nz
        state%grid%dp(i,j,k)=7000.0_real64+600.0_real64*k+5.0_real64*i
        state%grid%cell_measure(i,j,k)=state%grid%dx(i,j)*state%grid%dy(i,j)* &
                                       state%grid%dp(i,j,k)/9.80665_real64
        plev=95000.0_real64-15000.0_real64*REAL(k-1,real64)
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
    CALL mark_valid(state%omega_target,SOURCE_COLUMN_PHYSICS)
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
    state%omega_top_boundary%source=SOURCE_BACKGROUND_MODEL
    state%omega_bottom_boundary%source=SOURCE_BACKGROUND_MODEL
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      state%balance_beta(i,j,k)=REAL(0.25_real64+0.75_real64* &
        SIN(ACOS(-1.0_real64)*REAL(i,real64)/REAL(nx+1,real64))**2* &
        SIN(ACOS(-1.0_real64)*REAL(j,real64)/REAL(ny+1,real64))**2,real32)
    END DO; END DO; END DO
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
    REAL(real64), ALLOCATABLE :: xu(:,:,:),xv(:,:,:),xo(:,:,:),lambda(:,:,:)
    REAL(real64), ALLOCATABLE :: ax(:,:,:),atu(:,:,:),atv(:,:,:),ato(:,:,:)
    REAL(real64), ALLOCATABLE :: gu(:,:,:),gv(:,:,:),go(:,:,:),ag(:,:,:),ll(:,:,:)
    REAL(real64) :: lhs,rhs,error,scale,quad
    INTEGER :: status,reason,i,j,k

    CALL make_balance_state(state,6,5,4)
    CALL build_balance_operator(state,cfg,op,status,reason)
    CALL check(status==STATUS_OK,'operator construction',failures)
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
    lhs=SUM(op%volume*lambda*ax,MASK=op%cell_active)
    rhs=SUM(atu*xu+atv*xv+ato*xo)
    scale=MAX(ABS(lhs),ABS(rhs),1.0e-30_real64)
    error=ABS(lhs-rhs)/scale
    CALL check(status==STATUS_OK .AND. error<5.0e-13_real64, &
               'metric adjoint identity',failures)

    CALL apply_balance_correction(op,lambda,gu,gv,go,status)
    CALL apply_continuity_operator(op,gu,gv,go,ag,status)
    CALL apply_normal_operator(op,lambda,ll,status)
    scale=MAX(MAXVAL(ABS(ll),MASK=op%cell_active),1.0e-30_real64)
    error=MAXVAL(ABS(ll+ag),MASK=op%cell_active)/scale
    CALL check(error<5.0e-13_real64,'L equals -A G pointwise',failures)
    quad=SUM(op%volume*lambda*ll,MASK=op%cell_active)
    CALL check(quad>=-1.0e-12_real64*MAX(1.0_real64,ABS(quad)), &
               'normal operator must be positive semidefinite',failures)

    xv=0.0_real64; xo=0.0_real64
    CALL apply_continuity_operator(op,xu,xv,xo,ax,status)
    CALL check(MAXVAL(ABS(ax),MASK=op%cell_active)>0.0_real64, &
               'u-axis pattern must contribute',failures)
    xu=0.0_real64; xv=1.0_real64
    CALL apply_continuity_operator(op,xu,xv,xo,ax,status)
    CALL check(MAXVAL(ABS(ax),MASK=op%cell_active)>0.0_real64, &
               'v-axis pattern must contribute',failures)
    xv=0.0_real64; xo=1.0_real64
    CALL apply_continuity_operator(op,xu,xv,xo,ax,status)
    CALL check(MAXVAL(ABS(ax),MASK=op%cell_active)>0.0_real64, &
               'omega-axis pattern must include zero-flux boundaries',failures)
  END SUBROUTINE test_operator_identities

  SUBROUTINE test_stage_transaction(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output,no_source
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg

    CALL make_balance_state(input,6,5,4)
    cfg%required_residual_fraction=0.50_real64
    cfg%maximum_target_cancellation_fraction=2.0_real64
    cfg%momentum_absolute_tolerance=0.10_real64
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK,'localized balance stage must converge',failures)
    CALL check(result%numerical%continuity_final_rms < &
               result%numerical%continuity_forced_rms+1.0e-12_real64, &
               'full pre-correction continuity residual must decrease',failures)
    CALL check(result%numerical%max_wind_increment<=cfg%maximum_wind_increment, &
               'wind increment gate',failures)

    no_source=input
    no_source%omega_target%valid=.FALSE.
    CALL apply_localized_balance(no_source,output,result,cfg)
    CALL check(result%status==STATUS_OK .AND. &
               ALL(TRANSFER(output%u%value,[0_int32])== &
                   TRANSFER(no_source%u%value,[0_int32])), &
               'no target must be exact no-op',failures)
  END SUBROUTINE test_stage_transaction

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
    cfg%maximum_target_cancellation_fraction=2.0_real64
    cfg%momentum_absolute_tolerance=1.0_real64
    CALL apply_localized_balance(input,output,result,cfg)
    CALL check(result%status==STATUS_OK, &
               'nonzero background residual must be part of the solve',failures)
    CALL check(result%numerical%continuity_final_rms<= &
               cfg%required_residual_fraction* &
               result%numerical%continuity_forced_rms+cfg%solver_absolute_tolerance, &
               'same operator must reduce full forced residual',failures)
  END SUBROUTINE test_nonzero_background_residual

  SUBROUTINE test_disconnected_support(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,output
    TYPE(stage_result) :: result
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    INTEGER :: status,reason

    CALL make_balance_state(input,6,5,4)
    input%balance_beta=0.0_real32
    input%balance_beta(2,2,:)=1.0_real32
    input%balance_beta(5,4,:)=1.0_real32
    CALL build_balance_operator(input,cfg,op,status,reason)
    CALL check(status==STATUS_OK .AND. op%ncomponent==2, &
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
  END SUBROUTINE test_small_domain_rejection

END PROGRAM test_balance_operator
