! Exact localized continuity projection on the canonical LAPS A grid.
!
! The matrix is never assembled from a second formula.  S maps A-grid
! component values to oriented faces, D takes the finite-volume divergence,
! A=D*S, G=-K*A^T*M, and L=-A*G.  The same procedures are used by the solver,
! the published increment, and the final residual diagnostics.
MODULE cloud_bal_balance_operator
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_state
  IMPLICIT NONE
  PRIVATE
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64

  TYPE, PUBLIC :: balance_operator_config
    REAL(real64) :: kappa_u = 16.0_real64
    REAL(real64) :: kappa_v = 16.0_real64
    REAL(real64) :: kappa_omega = 0.25_real64
    REAL(real64) :: minimum_beta = 1.0e-6_real64
    REAL(real64) :: solver_relative_tolerance = 1.0e-8_real64
    REAL(real64) :: solver_absolute_tolerance = 1.0e-12_real64
    REAL(real64) :: compatibility_relative_tolerance = 1.0e-11_real64
    REAL(real64) :: compatibility_absolute_tolerance = 1.0e-14_real64
    INTEGER :: maximum_iterations = 800
    INTEGER :: attenuation_attempts = 8
    REAL(real64) :: attenuation_factor = 0.5_real64
    REAL(real64) :: required_residual_fraction = 0.25_real64
    REAL(real64) :: maximum_wind_increment = 10.0_real64
    REAL(real64) :: maximum_omega_increment = 5.0_real64
    REAL(real64) :: maximum_target_cancellation_fraction = 0.80_real64
    REAL(real64) :: momentum_relative_tolerance = 0.05_real64
    REAL(real64) :: momentum_absolute_tolerance = 1.0e-3_real64
  END TYPE balance_operator_config

  TYPE, PUBLIC :: balance_operator_type
    INTEGER :: nx=0,ny=0,nz=0
    REAL(real64), ALLOCATABLE :: volume(:,:,:)
    REAL(real64), ALLOCATABLE :: dx(:,:),dy(:,:),dp(:,:,:)
    REAL(real64), ALLOCATABLE :: pressure(:,:,:)
    REAL(real64), ALLOCATABLE :: ku(:,:,:),kv(:,:,:),ko(:,:,:)
    LOGICAL, ALLOCATABLE :: cell_active(:,:,:)
    LOGICAL, ALLOCATABLE :: xface_active(:,:,:)
    LOGICAL, ALLOCATABLE :: yface_active(:,:,:)
    LOGICAL, ALLOCATABLE :: pface_active(:,:,:)
    REAL(real64), ALLOCATABLE :: xface_area(:,:,:),yface_area(:,:,:)
    REAL(real64), ALLOCATABLE :: pface_area(:,:,:)
    REAL(real64), ALLOCATABLE :: xleft_weight(:,:,:),xright_weight(:,:,:)
    REAL(real64), ALLOCATABLE :: yleft_weight(:,:,:),yright_weight(:,:,:)
    REAL(real64), ALLOCATABLE :: pleft_weight(:,:,:),pright_weight(:,:,:)
    INTEGER, ALLOCATABLE :: component(:,:,:)
    INTEGER :: ncomponent=0
  END TYPE balance_operator_type

  PUBLIC :: build_balance_operator
  PUBLIC :: apply_continuity_operator
  PUBLIC :: apply_adjoint_metric
  PUBLIC :: apply_balance_correction
  PUBLIC :: apply_normal_operator
  PUBLIC :: apply_localized_balance
  PUBLIC :: continuity_norms

CONTAINS

  SUBROUTINE build_balance_operator(state,config,op,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(balance_operator_config), INTENT(IN) :: config
    TYPE(balance_operator_type), INTENT(OUT) :: op
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: nx,ny,nz,i,j,k
    REAL(real64) :: denom,orientation,level_delta,reference_orientation,scale
    LOGICAL :: reference_set

    status=STATUS_FAILED; reason=REASON_SHAPE
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    IF (nx<4 .OR. ny<4 .OR. nz<2) RETURN
    IF (.NOT.config_valid(config)) THEN; reason=REASON_RANGE; RETURN; END IF
    IF (.NOT.operator_input_shapes_valid(state)) RETURN
    IF (.NOT.boundary_contract_valid(state)) THEN; reason=REASON_METADATA; RETURN; END IF
    IF (ANY(.NOT.ieee_is_finite(state%grid%dx)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%dy)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%dp)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%cell_measure)) .OR. &
        ANY(state%grid%dx<=0.0_real64) .OR. ANY(state%grid%dy<=0.0_real64) .OR. &
        ANY(state%grid%dp<=0.0_real64) .OR. &
        ANY(state%grid%cell_measure<=0.0_real64)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    reference_orientation=0.0_real64; reference_set=.FALSE.
    DO j=1,ny; DO i=1,nx
      orientation=REAL(state%pressure%value(i,j,1),real64)- &
                  REAL(state%pressure%value(i,j,2),real64)
      scale=MAX(ABS(REAL(state%pressure%value(i,j,1),real64)), &
                ABS(REAL(state%pressure%value(i,j,2),real64)),1.0_real64)
      IF (.NOT.ieee_is_finite(orientation) .OR. &
          ABS(orientation)<=EPSILON(1.0_real64)*scale) THEN
        reason=REASON_RANGE; RETURN
      END IF
      IF (.NOT.reference_set) THEN
        reference_orientation=orientation; reference_set=.TRUE.
      END IF
      IF (orientation*reference_orientation<=0.0_real64) THEN
        reason=REASON_RANGE; RETURN
      END IF
      DO k=2,nz-1
        level_delta=REAL(state%pressure%value(i,j,k),real64)- &
                    REAL(state%pressure%value(i,j,k+1),real64)
        scale=MAX(ABS(REAL(state%pressure%value(i,j,k),real64)), &
                  ABS(REAL(state%pressure%value(i,j,k+1),real64)),1.0_real64)
        IF (.NOT.ieee_is_finite(level_delta) .OR. &
            ABS(level_delta)<=EPSILON(1.0_real64)*scale .OR. &
            orientation*level_delta<=0.0_real64) THEN
          reason=REASON_RANGE; RETURN
        END IF
      END DO
    END DO; END DO

    op%nx=nx; op%ny=ny; op%nz=nz
    ALLOCATE(op%volume(nx,ny,nz),op%dx(nx,ny),op%dy(nx,ny), &
             op%dp(nx,ny,nz),op%pressure(nx,ny,nz), &
             op%ku(nx,ny,nz),op%kv(nx,ny,nz),op%ko(nx,ny,nz), &
             op%cell_active(nx,ny,nz),op%component(nx,ny,nz))
    ALLOCATE(op%xface_active(nx-1,ny,nz),op%xface_area(nx-1,ny,nz), &
             op%xleft_weight(nx-1,ny,nz),op%xright_weight(nx-1,ny,nz))
    ALLOCATE(op%yface_active(nx,ny-1,nz),op%yface_area(nx,ny-1,nz), &
             op%yleft_weight(nx,ny-1,nz),op%yright_weight(nx,ny-1,nz))
    ALLOCATE(op%pface_active(nx,ny,nz-1),op%pface_area(nx,ny,nz-1), &
             op%pleft_weight(nx,ny,nz-1),op%pright_weight(nx,ny,nz-1))
    op%volume=state%grid%cell_measure
    op%dx=state%grid%dx; op%dy=state%grid%dy; op%dp=state%grid%dp
    op%pressure=REAL(state%pressure%value,real64)
    op%cell_active=state%pressure%valid .AND. state%u%valid .AND. &
                   state%v%valid .AND. state%omega%valid .AND. &
                   REAL(state%balance_beta,real64)>=config%minimum_beta
    IF (ANY(op%cell_active .AND. &
        (.NOT.ieee_is_finite(state%pressure%value) .OR. &
         .NOT.ieee_is_finite(state%u%value) .OR. &
         .NOT.ieee_is_finite(state%v%value) .OR. &
         .NOT.ieee_is_finite(state%omega%value) .OR. &
         (state%omega_target%valid .AND. &
          .NOT.ieee_is_finite(state%omega_target%value))))) THEN
      reason=REASON_NONFINITE; RETURN
    END IF
    op%ku=0.0_real64; op%kv=0.0_real64; op%ko=0.0_real64
    WHERE(op%cell_active)
      op%ku=REAL(state%balance_beta,real64)*config%kappa_u
      op%kv=REAL(state%balance_beta,real64)*config%kappa_v
      op%ko=REAL(state%balance_beta,real64)*config%kappa_omega
    END WHERE

    DO k=1,nz; DO j=1,ny; DO i=1,nx-1
      denom=op%dx(i,j)+op%dx(i+1,j)
      op%xleft_weight(i,j,k)=op%dx(i+1,j)/denom
      op%xright_weight(i,j,k)=op%dx(i,j)/denom
      op%xface_area(i,j,k)=0.5_real64*(op%dy(i,j)+op%dy(i+1,j))* &
                           0.5_real64*(op%dp(i,j,k)+op%dp(i+1,j,k))/GRAVITY
      op%xface_active(i,j,k)=op%cell_active(i,j,k) .AND. &
                             op%cell_active(i+1,j,k) .AND. &
                             op%ku(i,j,k)>0.0_real64 .AND. &
                             op%ku(i+1,j,k)>0.0_real64
    END DO; END DO; END DO
    DO k=1,nz; DO j=1,ny-1; DO i=1,nx
      denom=op%dy(i,j)+op%dy(i,j+1)
      op%yleft_weight(i,j,k)=op%dy(i,j+1)/denom
      op%yright_weight(i,j,k)=op%dy(i,j)/denom
      op%yface_area(i,j,k)=0.5_real64*(op%dx(i,j)+op%dx(i,j+1))* &
                           0.5_real64*(op%dp(i,j,k)+op%dp(i,j+1,k))/GRAVITY
      op%yface_active(i,j,k)=op%cell_active(i,j,k) .AND. &
                             op%cell_active(i,j+1,k) .AND. &
                             op%kv(i,j,k)>0.0_real64 .AND. &
                             op%kv(i,j+1,k)>0.0_real64
    END DO; END DO; END DO
    DO k=1,nz-1; DO j=1,ny; DO i=1,nx
      denom=op%dp(i,j,k)+op%dp(i,j,k+1)
      op%pleft_weight(i,j,k)=op%dp(i,j,k+1)/denom
      op%pright_weight(i,j,k)=op%dp(i,j,k)/denom
      op%pface_area(i,j,k)=op%dx(i,j)*op%dy(i,j)/GRAVITY
      op%pface_active(i,j,k)=op%cell_active(i,j,k) .AND. &
                             op%cell_active(i,j,k+1) .AND. &
                             op%ko(i,j,k)>0.0_real64 .AND. &
                             op%ko(i,j,k+1)>0.0_real64
      IF (op%pface_active(i,j,k)) THEN
        IF (ABS(op%pressure(i,j,k)-op%pressure(i,j,k+1))<= &
            EPSILON(1.0_real64)*MAX(ABS(op%pressure(i,j,k)), &
                                    ABS(op%pressure(i,j,k+1)))) THEN
          reason=REASON_RANGE; RETURN
        END IF
      END IF
    END DO; END DO; END DO
    CALL label_components(op)
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE build_balance_operator

  SUBROUTINE apply_continuity_operator(op,u,v,omega,residual,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: u(:,:,:),v(:,:,:),omega(:,:,:)
    REAL(real64), INTENT(OUT) :: residual(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,low,high
    REAL(real64) :: flux

    residual=0.0_real64; status=STATUS_FAILED
    IF (.NOT.operator_array_shapes_valid(op,u,v,omega,residual)) RETURN
    IF (ANY(op%cell_active .AND. (.NOT.ieee_is_finite(u) .OR. &
        .NOT.ieee_is_finite(v) .OR. .NOT.ieee_is_finite(omega)))) RETURN
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx-1
      IF (.NOT.op%xface_active(i,j,k)) CYCLE
      flux=op%xface_area(i,j,k)*(op%xleft_weight(i,j,k)*u(i,j,k)+ &
                                 op%xright_weight(i,j,k)*u(i+1,j,k))
      residual(i,j,k)=residual(i,j,k)+flux/op%volume(i,j,k)
      residual(i+1,j,k)=residual(i+1,j,k)-flux/op%volume(i+1,j,k)
    END DO; END DO; END DO
    DO k=1,op%nz; DO j=1,op%ny-1; DO i=1,op%nx
      IF (.NOT.op%yface_active(i,j,k)) CYCLE
      flux=op%yface_area(i,j,k)*(op%yleft_weight(i,j,k)*v(i,j,k)+ &
                                 op%yright_weight(i,j,k)*v(i,j+1,k))
      residual(i,j,k)=residual(i,j,k)+flux/op%volume(i,j,k)
      residual(i,j+1,k)=residual(i,j+1,k)-flux/op%volume(i,j+1,k)
    END DO; END DO; END DO
    DO k=1,op%nz-1; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.op%pface_active(i,j,k)) CYCLE
      flux=op%pface_area(i,j,k)*(op%pleft_weight(i,j,k)*omega(i,j,k)+ &
                                 op%pright_weight(i,j,k)*omega(i,j,k+1))
      IF (op%pressure(i,j,k)<op%pressure(i,j,k+1)) THEN
        low=k; high=k+1
      ELSE
        low=k+1; high=k
      END IF
      residual(i,j,low)=residual(i,j,low)+flux/op%volume(i,j,low)
      residual(i,j,high)=residual(i,j,high)-flux/op%volume(i,j,high)
    END DO; END DO; END DO
    WHERE(.NOT.op%cell_active) residual=0.0_real64
    IF (ANY(.NOT.ieee_is_finite(residual))) RETURN
    status=STATUS_OK
  END SUBROUTINE apply_continuity_operator

  SUBROUTINE apply_adjoint_metric(op,lambda,atu,atv,atomega,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: lambda(:,:,:)
    REAL(real64), INTENT(OUT) :: atu(:,:,:),atv(:,:,:),atomega(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,low,high
    REAL(real64) :: contribution

    atu=0.0_real64; atv=0.0_real64; atomega=0.0_real64
    status=STATUS_FAILED
    IF (.NOT.four_shapes_match(op,lambda,atu,atv,atomega)) RETURN
    IF (ANY(op%cell_active .AND. .NOT.ieee_is_finite(lambda))) RETURN
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx-1
      IF (.NOT.op%xface_active(i,j,k)) CYCLE
      contribution=op%xface_area(i,j,k)*(lambda(i,j,k)-lambda(i+1,j,k))
      atu(i,j,k)=atu(i,j,k)+op%xleft_weight(i,j,k)*contribution
      atu(i+1,j,k)=atu(i+1,j,k)+op%xright_weight(i,j,k)*contribution
    END DO; END DO; END DO
    DO k=1,op%nz; DO j=1,op%ny-1; DO i=1,op%nx
      IF (.NOT.op%yface_active(i,j,k)) CYCLE
      contribution=op%yface_area(i,j,k)*(lambda(i,j,k)-lambda(i,j+1,k))
      atv(i,j,k)=atv(i,j,k)+op%yleft_weight(i,j,k)*contribution
      atv(i,j+1,k)=atv(i,j+1,k)+op%yright_weight(i,j,k)*contribution
    END DO; END DO; END DO
    DO k=1,op%nz-1; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.op%pface_active(i,j,k)) CYCLE
      IF (op%pressure(i,j,k)<op%pressure(i,j,k+1)) THEN
        low=k; high=k+1
      ELSE
        low=k+1; high=k
      END IF
      contribution=op%pface_area(i,j,k)*(lambda(i,j,low)-lambda(i,j,high))
      atomega(i,j,k)=atomega(i,j,k)+op%pleft_weight(i,j,k)*contribution
      atomega(i,j,k+1)=atomega(i,j,k+1)+op%pright_weight(i,j,k)*contribution
    END DO; END DO; END DO
    IF (ANY(.NOT.ieee_is_finite(atu)) .OR. ANY(.NOT.ieee_is_finite(atv)) .OR. &
        ANY(.NOT.ieee_is_finite(atomega))) RETURN
    status=STATUS_OK
  END SUBROUTINE apply_adjoint_metric

  SUBROUTINE apply_balance_correction(op,lambda,du,dv,domega,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: lambda(:,:,:)
    REAL(real64), INTENT(OUT) :: du(:,:,:),dv(:,:,:),domega(:,:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), ALLOCATABLE :: atu(:,:,:),atv(:,:,:),ato(:,:,:)

    status=STATUS_FAILED
    ALLOCATE(atu(op%nx,op%ny,op%nz),atv(op%nx,op%ny,op%nz), &
             ato(op%nx,op%ny,op%nz))
    CALL apply_adjoint_metric(op,lambda,atu,atv,ato,status)
    IF (status/=STATUS_OK) RETURN
    du=-op%ku*atu; dv=-op%kv*atv; domega=-op%ko*ato
    WHERE(.NOT.op%cell_active)
      du=0.0_real64; dv=0.0_real64; domega=0.0_real64
    END WHERE
    IF (ANY(.NOT.ieee_is_finite(du)) .OR. ANY(.NOT.ieee_is_finite(dv)) .OR. &
        ANY(.NOT.ieee_is_finite(domega))) THEN
      status=STATUS_FAILED; RETURN
    END IF
    status=STATUS_OK
  END SUBROUTINE apply_balance_correction

  SUBROUTINE apply_normal_operator(op,lambda,l_lambda,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: lambda(:,:,:)
    REAL(real64), INTENT(OUT) :: l_lambda(:,:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), ALLOCATABLE :: du(:,:,:),dv(:,:,:),domega(:,:,:)

    status=STATUS_FAILED
    ALLOCATE(du(op%nx,op%ny,op%nz),dv(op%nx,op%ny,op%nz), &
             domega(op%nx,op%ny,op%nz))
    CALL apply_balance_correction(op,lambda,du,dv,domega,status)
    IF (status/=STATUS_OK) RETURN
    CALL apply_continuity_operator(op,du,dv,domega,l_lambda,status)
    IF (status==STATUS_OK) l_lambda=-l_lambda
  END SUBROUTINE apply_normal_operator

  SUBROUTINE apply_localized_balance(state_in,state_out,result,config)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    TYPE(stage_result), INTENT(OUT) :: result
    TYPE(balance_operator_config), INTENT(IN), OPTIONAL :: config
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    TYPE(cloud_bal_state_type) :: candidate
    TYPE(stage_result) :: candidate_result
    REAL(real64), ALLOCATABLE :: qomega(:,:,:),b(:,:,:),lambda(:,:,:)
    REAL(real64), ALLOCATABLE :: du(:,:,:),dv(:,:,:),do_corr(:,:,:)
    REAL(real64), ALLOCATABLE :: r_background(:,:,:),r_forced(:,:,:),r_final(:,:,:)
    REAL(real64) :: alpha,rb_rms,rb_max,rf_rms,rf_max
    REAL(real64) :: rforced_rms,rforced_max
    REAL(real64) :: mom_background,mom_forced,mom_final,maxwind,maxomega
    REAL(real64) :: target_scale,cancel_fraction
    INTEGER :: status,reason,attempt,iterations
    LOGICAL :: accepted

    IF (PRESENT(config)) cfg=config
    CALL validate_canonical_state(state_in,.FALSE.,.FALSE.,status,reason)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    IF (.NOT.ANY(state_in%omega_target%valid .AND. &
                 state_in%balance_beta>REAL(cfg%minimum_beta,real32))) THEN
      state_out=state_in
      CALL initialize_stage_result(result,state_in%grid%nx,state_in%grid%ny, &
                                   state_in%grid%nz,STATUS_OK,REASON_NONE)
      RETURN
    END IF
    CALL validate_momentum_inputs(state_in,status,reason)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    CALL build_balance_operator(state_in,cfg,op,status,reason)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    ALLOCATE(qomega(op%nx,op%ny,op%nz),b(op%nx,op%ny,op%nz), &
             lambda(op%nx,op%ny,op%nz),du(op%nx,op%ny,op%nz), &
             dv(op%nx,op%ny,op%nz),do_corr(op%nx,op%ny,op%nz), &
             r_background(op%nx,op%ny,op%nz),r_forced(op%nx,op%ny,op%nz), &
             r_final(op%nx,op%ny,op%nz))
    CALL state_continuity_residual(op,state_in,r_background,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    CALL momentum_residual(state_in,op,mom_background,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF

    accepted=.FALSE.; alpha=1.0_real64
    DO attempt=1,cfg%attenuation_attempts
      qomega=0.0_real64
      WHERE(op%cell_active .AND. state_in%omega_target%valid)
        qomega=alpha*(REAL(state_in%omega_target%value,real64)- &
                      REAL(state_in%omega%value,real64))
      END WHERE
      IF (MAXVAL(ABS(qomega))<=cfg%solver_absolute_tolerance) THEN
        state_out=state_in
        CALL initialize_stage_result(result,op%nx,op%ny,op%nz,STATUS_OK,REASON_NONE)
        RETURN
      END IF
      IF (.NOT.omega_target_observable(op,qomega,cfg%solver_absolute_tolerance)) THEN
        reason=REASON_GATE
        EXIT
      END IF
      CALL apply_continuity_operator(op,0.0_real64*qomega,0.0_real64*qomega, &
                                     qomega,b,status)
      IF (status/=STATUS_OK) EXIT
      r_forced=r_background+b
      b=r_forced
      IF (.NOT.compatibility_ok(op,b,cfg)) THEN
        reason=REASON_SOLVER; EXIT
      END IF
      CALL solve_normal_equation(op,b,cfg,lambda,iterations,status)
      IF (status/=STATUS_OK) THEN
        reason=REASON_SOLVER
        alpha=alpha*cfg%attenuation_factor
        CYCLE
      END IF
      CALL apply_balance_correction(op,lambda,du,dv,do_corr,status)
      IF (status/=STATUS_OK) THEN; reason=REASON_NONFINITE; EXIT; END IF
      CALL continuity_norms(op,r_background,rb_rms,rb_max)
      CALL continuity_norms(op,r_forced,rforced_rms,rforced_max)
      candidate=state_in
      candidate%u%value=REAL(REAL(state_in%u%value,real64)+du,real32)
      candidate%v%value=REAL(REAL(state_in%v%value,real64)+dv,real32)
      candidate%omega%value=REAL(REAL(state_in%omega%value,real64)+qomega+do_corr,real32)
      WHERE(op%cell_active)
        candidate%u%source=IOR(candidate%u%source,SOURCE_BALANCE_OPERATOR)
        candidate%v%source=IOR(candidate%v%source,SOURCE_BALANCE_OPERATOR)
        candidate%omega%source=IOR(candidate%omega%source,SOURCE_BALANCE_OPERATOR)
      END WHERE
      CALL state_continuity_residual(op,candidate,r_final,status)
      IF (status/=STATUS_OK) THEN; reason=REASON_NONFINITE; EXIT; END IF
      ! Every numerical gate is recomputed from the actual real32 candidate,
      ! not from the higher-precision work arrays that are never published.
      du=REAL(candidate%u%value,real64)-REAL(state_in%u%value,real64)
      dv=REAL(candidate%v%value,real64)-REAL(state_in%v%value,real64)
      do_corr=REAL(candidate%omega%value,real64)- &
              REAL(state_in%omega%value,real64)-qomega
      CALL continuity_norms(op,r_final,rf_rms,rf_max)
      maxwind=MAX(MAXVAL(ABS(du)),MAXVAL(ABS(dv)))
      maxomega=MAXVAL(ABS(qomega+do_corr))
      target_scale=MAX(MAXVAL(ABS(qomega)),cfg%solver_absolute_tolerance)
      cancel_fraction=MAXVAL(ABS(do_corr),MASK=ABS(qomega)> &
        cfg%solver_absolute_tolerance)/target_scale
      CALL momentum_residual(candidate,op,mom_final,status)
      IF (status/=STATUS_OK) THEN; reason=REASON_NONFINITE; EXIT; END IF
      mom_forced=mom_background
      accepted=rf_rms<=MAX(cfg%required_residual_fraction*rforced_rms, &
                           cfg%solver_absolute_tolerance) .AND. &
               rf_max<=MAX(cfg%required_residual_fraction*rforced_max, &
                           cfg%solver_absolute_tolerance) .AND. &
               maxwind<=cfg%maximum_wind_increment .AND. &
               maxomega<=cfg%maximum_omega_increment .AND. &
               target_cancellation_ok(op,do_corr,qomega, &
                 cfg%maximum_target_cancellation_fraction, &
                 cfg%solver_absolute_tolerance) .AND. &
               mom_final<=mom_background*(1.0_real64+cfg%momentum_relative_tolerance)+ &
                          cfg%momentum_absolute_tolerance .AND. &
               outside_support_zero(op,du,dv,qomega+do_corr)
      IF (accepted) EXIT
      alpha=alpha*cfg%attenuation_factor
    END DO

    IF (.NOT.accepted) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_DEGRADED,REASON_GATE)
      RETURN
    END IF
    CALL initialize_stage_result(candidate_result,op%nx,op%ny,op%nz, &
                                 STATUS_OK,REASON_NONE)
    candidate_result%changed=op%cell_active .AND. &
      (ABS(du)+ABS(dv)+ABS(qomega+do_corr)>0.0_real64)
    candidate_result%numerical%solver_iterations=iterations
    candidate_result%numerical%continuity_background_rms=rb_rms
    candidate_result%numerical%continuity_forced_rms=rforced_rms
    candidate_result%numerical%continuity_final_rms=rf_rms
    candidate_result%numerical%momentum_background_rms=mom_background
    candidate_result%numerical%momentum_forced_rms=mom_forced
    candidate_result%numerical%momentum_final_rms=mom_final
    candidate_result%numerical%max_wind_increment=maxwind
    candidate_result%numerical%max_omega_increment=maxomega
    ! These are finite-difference diagnostics, not a Helmholtz decomposition.
    ! They therefore have no authority to accept or reject a candidate.
    CALL increment_mode_metrics(op,du,dv,candidate_result%numerical%divergent_rms, &
                                candidate_result%numerical%rotational_rms)
    CALL evaluate_los_gate(state_in,candidate,candidate_result,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_DEGRADED,REASON_GATE)
      RETURN
    END IF
    CALL commit_candidate(state_in,candidate,candidate_result,state_out,result)
  END SUBROUTINE apply_localized_balance

  SUBROUTINE solve_normal_equation(op,b,cfg,lambda,iterations,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: b(:,:,:)
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    REAL(real64), INTENT(OUT) :: lambda(:,:,:)
    INTEGER, INTENT(OUT) :: iterations,status
    REAL(real64), ALLOCATABLE :: r(:,:,:),p(:,:,:),lp(:,:,:)
    REAL(real64) :: rho,rho_new,denom,alpha,beta,b_rms,b_max,r_rms,r_max
    INTEGER :: operator_status

    ALLOCATE(r(op%nx,op%ny,op%nz),p(op%nx,op%ny,op%nz), &
             lp(op%nx,op%ny,op%nz))
    lambda=0.0_real64; r=b; iterations=0; status=STATUS_FAILED
    CALL remove_component_means(op,r)
    p=r
    CALL continuity_norms(op,b,b_rms,b_max)
    rho=weighted_dot(op,r,r)
    IF (rho<=cfg%solver_absolute_tolerance**2*active_volume(op)) THEN
      status=STATUS_OK; RETURN
    END IF
    DO iterations=1,cfg%maximum_iterations
      CALL apply_normal_operator(op,p,lp,operator_status)
      IF (operator_status/=STATUS_OK) RETURN
      denom=weighted_dot(op,p,lp)
      IF (.NOT.ieee_is_finite(denom) .OR. denom<=0.0_real64) RETURN
      alpha=rho/denom
      lambda=lambda+alpha*p
      CALL remove_component_means(op,lambda)
      r=r-alpha*lp
      CALL remove_component_means(op,r)
      CALL continuity_norms(op,r,r_rms,r_max)
      IF (r_rms<=MAX(cfg%solver_relative_tolerance*b_rms, &
                     cfg%solver_absolute_tolerance) .AND. &
          r_max<=MAX(cfg%solver_relative_tolerance*b_max, &
                     cfg%solver_absolute_tolerance)) THEN
        CALL apply_normal_operator(op,lambda,lp,operator_status)
        IF (operator_status/=STATUS_OK) RETURN
        r=b-lp
        CALL remove_component_means(op,r)
        CALL continuity_norms(op,r,r_rms,r_max)
        IF (r_rms<=MAX(cfg%solver_relative_tolerance*b_rms, &
                       cfg%solver_absolute_tolerance) .AND. &
            r_max<=MAX(cfg%solver_relative_tolerance*b_max, &
                       cfg%solver_absolute_tolerance)) status=STATUS_OK
        RETURN
      END IF
      rho_new=weighted_dot(op,r,r)
      IF (.NOT.ieee_is_finite(rho_new) .OR. rho_new<0.0_real64) RETURN
      beta=rho_new/rho
      p=r+beta*p
      rho=rho_new
    END DO
  END SUBROUTINE solve_normal_equation

  SUBROUTINE continuity_norms(op,residual,rms_value,max_value)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: residual(:,:,:)
    REAL(real64), INTENT(OUT) :: rms_value,max_value
    INTEGER :: count_active
    count_active=COUNT(op%cell_active)
    IF (count_active<=0) THEN
      rms_value=0.0_real64; max_value=0.0_real64; RETURN
    END IF
    ! Acceptance diagnostics are physical, unweighted norms.  The volume
    ! metric remains private to the adjoint, compatibility and CG products.
    rms_value=SQRT(MAX(0.0_real64, &
      SUM(residual*residual,MASK=op%cell_active)/REAL(count_active,real64)))
    max_value=MAXVAL(ABS(residual),MASK=op%cell_active)
  END SUBROUTINE continuity_norms

  SUBROUTINE state_continuity_residual(op,state,residual,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    REAL(real64), INTENT(OUT) :: residual(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k_top,k_bottom
    REAL(real64) :: area,flux
    CALL apply_continuity_operator(op,REAL(state%u%value,real64), &
      REAL(state%v%value,real64),REAL(state%omega%value,real64),residual,status)
    IF (status/=STATUS_OK) RETURN
    DO j=1,op%ny; DO i=1,op%nx
      IF (op%pressure(i,j,1)<op%pressure(i,j,op%nz)) THEN
        k_top=1; k_bottom=op%nz
      ELSE
        k_top=op%nz; k_bottom=1
      END IF
      area=op%dx(i,j)*op%dy(i,j)/GRAVITY
      IF (op%cell_active(i,j,k_top) .AND. state%omega_top_boundary%valid(i,j)) THEN
        flux=area*REAL(state%omega_top_boundary%value(i,j),real64)
        residual(i,j,k_top)=residual(i,j,k_top)-flux/op%volume(i,j,k_top)
      END IF
      IF (op%cell_active(i,j,k_bottom) .AND. state%omega_bottom_boundary%valid(i,j)) THEN
        flux=area*REAL(state%omega_bottom_boundary%value(i,j),real64)
        residual(i,j,k_bottom)=residual(i,j,k_bottom)+flux/op%volume(i,j,k_bottom)
      END IF
    END DO; END DO
    IF (ANY(op%cell_active .AND. .NOT.ieee_is_finite(residual))) status=STATUS_FAILED
  END SUBROUTINE state_continuity_residual

  SUBROUTINE momentum_residual(state,op,rms_value,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(OUT) :: rms_value
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,n
    REAL(real64) :: f,dphidx,dphidy,ru,rv,total,pi
    status=STATUS_FAILED; rms_value=0.0_real64; total=0.0_real64; n=0
    pi=ACOS(-1.0_real64)
    DO k=1,op%nz; DO j=1,op%ny-1; DO i=1,op%nx-1
      IF (.NOT.(op%cell_active(i,j,k) .AND. op%cell_active(i+1,j,k) .AND. &
                op%cell_active(i,j+1,k))) CYCLE
      IF (.NOT.(state%geopotential%valid(i,j,k) .AND. &
                state%geopotential%valid(i+1,j,k) .AND. &
                state%geopotential%valid(i,j+1,k) .AND. &
                state%latitude%valid(i,j))) RETURN
      f=1.458423e-4_real64*SIN(REAL(state%latitude%value(i,j),real64)*pi/180.0_real64)
      IF (ABS(f)<1.0e-6_real64) CYCLE
      dphidx=(REAL(state%geopotential%value(i+1,j,k),real64)- &
              REAL(state%geopotential%value(i,j,k),real64))/ &
             (0.5_real64*(op%dx(i,j)+op%dx(i+1,j)))
      dphidy=(REAL(state%geopotential%value(i,j+1,k),real64)- &
              REAL(state%geopotential%value(i,j,k),real64))/ &
             (0.5_real64*(op%dy(i,j)+op%dy(i,j+1)))
      ru=-f*REAL(state%v%value(i,j,k),real64)+dphidx
      rv= f*REAL(state%u%value(i,j,k),real64)+dphidy
      IF (.NOT.ieee_is_finite(ru) .OR. .NOT.ieee_is_finite(rv)) RETURN
      total=total+ru*ru+rv*rv; n=n+2
    END DO; END DO; END DO
    IF (n==0) RETURN
    rms_value=SQRT(total/REAL(n,real64)); status=STATUS_OK
  END SUBROUTINE momentum_residual

  SUBROUTINE validate_momentum_inputs(state,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: nx,ny,nz
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    status=STATUS_FAILED; reason=REASON_SHAPE
    IF (.NOT.ALLOCATED(state%geopotential%value) .OR. &
        .NOT.ALLOCATED(state%geopotential%valid) .OR. &
        .NOT.ALLOCATED(state%latitude%value) .OR. &
        .NOT.ALLOCATED(state%latitude%valid)) RETURN
    IF (ANY(SHAPE(state%geopotential%value)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%latitude%value)/=(/nx,ny/))) RETURN
    IF (TRIM(state%geopotential%unit)/='m2 s-2' .OR. &
        TRIM(state%latitude%unit)/='degree_north') THEN
      reason=REASON_METADATA; RETURN
    END IF
    IF (COUNT(state%geopotential%valid)==0 .OR. COUNT(state%latitude%valid)==0) THEN
      reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    IF (ANY(state%geopotential%valid .AND. &
            .NOT.ieee_is_finite(state%geopotential%value)) .OR. &
        ANY(state%latitude%valid .AND. &
            (.NOT.ieee_is_finite(state%latitude%value) .OR. &
             ABS(state%latitude%value)>90.0_real32))) THEN
      reason=REASON_NONFINITE; RETURN
    END IF
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE validate_momentum_inputs

  SUBROUTINE increment_mode_metrics(op,du,dv,divergent_rms,rotational_rms)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: du(:,:,:),dv(:,:,:)
    REAL(real64), INTENT(OUT) :: divergent_rms,rotational_rms
    INTEGER :: i,j,k,n
    REAL(real64) :: div,curl,sum_div,sum_rot
    sum_div=0.0_real64; sum_rot=0.0_real64; n=0
    DO k=1,op%nz; DO j=2,op%ny-1; DO i=2,op%nx-1
      IF (.NOT.(op%cell_active(i,j,k) .AND. op%cell_active(i+1,j,k) .AND. &
                op%cell_active(i-1,j,k) .AND. op%cell_active(i,j+1,k) .AND. &
                op%cell_active(i,j-1,k))) CYCLE
      div=(du(i+1,j,k)-du(i-1,j,k))/(op%dx(i,j)+op%dx(i-1,j))+ &
          (dv(i,j+1,k)-dv(i,j-1,k))/(op%dy(i,j)+op%dy(i,j-1))
      curl=(dv(i+1,j,k)-dv(i-1,j,k))/(op%dx(i,j)+op%dx(i-1,j))- &
           (du(i,j+1,k)-du(i,j-1,k))/(op%dy(i,j)+op%dy(i,j-1))
      sum_div=sum_div+div*div; sum_rot=sum_rot+curl*curl; n=n+1
    END DO; END DO; END DO
    IF (n>0) THEN
      divergent_rms=SQRT(sum_div/REAL(n,real64))
      rotational_rms=SQRT(sum_rot/REAL(n,real64))
    ELSE
      divergent_rms=0.0_real64; rotational_rms=0.0_real64
    END IF
  END SUBROUTINE increment_mode_metrics

  SUBROUTINE evaluate_los_gate(input,candidate,result,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,candidate
    TYPE(stage_result), INTENT(INOUT) :: result
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,r,nheld
    REAL(real64) :: predicted_in,predicted_out,res_in,res_out,weight
    REAL(real64) :: sum_in,sum_out,sum_weight,vt,sigma_vt,beam_vertical,sigma2
    REAL(real32), ALLOCATABLE :: win(:,:,:),wout(:,:,:)
    LOGICAL, ALLOCATABLE :: valid_in(:,:,:),valid_out(:,:,:)
    INTEGER :: conversion_status

    status=STATUS_OK
    IF (.NOT.input%radar_los%is_present) RETURN
    ALLOCATE(win(input%grid%nx,input%grid%ny,input%grid%nz), &
             wout(input%grid%nx,input%grid%ny,input%grid%nz), &
             valid_in(input%grid%nx,input%grid%ny,input%grid%nz), &
             valid_out(input%grid%nx,input%grid%ny,input%grid%nz))
    CALL omega_to_w(input%omega%value,input%pressure%value,input%temperature%value, &
      input%vapor%value,input%omega%valid .AND. input%pressure%valid .AND. &
      input%temperature%valid .AND. input%vapor%valid,win,valid_in,conversion_status)
    IF (conversion_status/=STATUS_OK) THEN; status=STATUS_FAILED; RETURN; END IF
    CALL omega_to_w(candidate%omega%value,candidate%pressure%value, &
      candidate%temperature%value,candidate%vapor%value, &
      candidate%omega%valid .AND. candidate%pressure%valid .AND. &
      candidate%temperature%valid .AND. candidate%vapor%valid, &
      wout,valid_out,conversion_status)
    IF (conversion_status/=STATUS_OK) THEN; status=STATUS_FAILED; RETURN; END IF
    sum_in=0.0_real64; sum_out=0.0_real64; sum_weight=0.0_real64; nheld=0
    DO r=1,input%radar_los%nradar; DO k=1,input%grid%nz
      DO j=1,input%grid%ny; DO i=1,input%grid%nx
        IF (input%radar_los%usage(i,j,k,r)/=LOS_HELD_OUT .OR. &
            input%radar_los%los_support(i,j,k,r)/=1 .OR. &
            .NOT.input%radar_los%vrad%valid(i,j,k,r) .OR. &
            .NOT.input%radar_los%nyquist%valid(i,j,k,r) .OR. &
            .NOT.input%radar_los%sigma_vrad%valid(i,j,k,r) .OR. &
            IAND(input%radar_los%vrad%quality(i,j,k,r), &
              IOR(QUALITY_RAW_MISSING,IOR(QUALITY_QC_REJECTED, &
                  QUALITY_TIME_MISMATCH)))/=0_int32 .OR. &
            .NOT.input%vt_z_mean%valid(i,j,k) .OR. &
            .NOT.input%vt_z_sigma%valid(i,j,k) .OR. &
            IAND(input%vt_z_mean%quality(i,j,k), &
              IOR(QUALITY_PHASE_UNCERTAIN,QUALITY_BRIGHT_BAND_OR_MIXED))/=0 .OR. &
            .NOT.valid_in(i,j,k) .OR. .NOT.valid_out(i,j,k)) CYCLE
        vt=REAL(input%vt_z_mean%value(i,j,k),real64)
        sigma_vt=REAL(input%vt_z_sigma%value(i,j,k),real64)
        beam_vertical=REAL(input%radar_los%beam(i,j,k,r,3),real64)
        predicted_in=REAL(input%radar_los%beam(i,j,k,r,1),real64)* &
                     REAL(input%u%value(i,j,k),real64)+ &
                     REAL(input%radar_los%beam(i,j,k,r,2),real64)* &
                     REAL(input%v%value(i,j,k),real64)+ &
                     REAL(input%radar_los%beam(i,j,k,r,3),real64)*(REAL(win(i,j,k),real64)-vt)
        predicted_out=REAL(input%radar_los%beam(i,j,k,r,1),real64)* &
                      REAL(candidate%u%value(i,j,k),real64)+ &
                      REAL(input%radar_los%beam(i,j,k,r,2),real64)* &
                      REAL(candidate%v%value(i,j,k),real64)+ &
                      REAL(input%radar_los%beam(i,j,k,r,3),real64)*(REAL(wout(i,j,k),real64)-vt)
        res_in=REAL(input%radar_los%vrad%value(i,j,k,r),real64)-predicted_in
        res_out=REAL(input%radar_los%vrad%value(i,j,k,r),real64)-predicted_out
        sigma2=REAL(input%radar_los%sigma_vrad%value(i,j,k,r),real64)**2+ &
               beam_vertical**2*sigma_vt**2
        weight=1.0_real64/MAX(sigma2,0.25_real64)
        sum_in=sum_in+weight*res_in*res_in; sum_out=sum_out+weight*res_out*res_out
        sum_weight=sum_weight+weight; nheld=nheld+1
      END DO; END DO
    END DO; END DO
    result%coverage%los_held_out=nheld
    IF (nheld==0) RETURN
    result%los_gate_applied=.TRUE.
    result%los_rms_input=SQRT(sum_in/sum_weight)
    result%los_rms_candidate=SQRT(sum_out/sum_weight)
    result%los_threshold=result%los_rms_input+0.10_real64
    result%los_gate_passed=result%los_rms_candidate<=result%los_threshold
    IF (.NOT.result%los_gate_passed) status=STATUS_DEGRADED
  END SUBROUTINE evaluate_los_gate

  SUBROUTINE label_components(op)
    TYPE(balance_operator_type), INTENT(INOUT) :: op
    INTEGER, ALLOCATABLE :: qi(:),qj(:),qk(:)
    INTEGER :: i,j,k,head,tail,ci,cj,ck,label
    ALLOCATE(qi(op%nx*op%ny*op%nz),qj(op%nx*op%ny*op%nz), &
             qk(op%nx*op%ny*op%nz))
    op%component=0; label=0
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.op%cell_active(i,j,k) .OR. op%component(i,j,k)/=0) CYCLE
      label=label+1; head=1; tail=1
      qi(1)=i; qj(1)=j; qk(1)=k; op%component(i,j,k)=label
      DO WHILE(head<=tail)
        ci=qi(head); cj=qj(head); ck=qk(head); head=head+1
        CALL enqueue_neighbor(ci-1,cj,ck,ci>1 .AND. &
             op%xface_active(MAX(1,ci-1),cj,ck),label,op,qi,qj,qk,tail)
        CALL enqueue_neighbor(ci+1,cj,ck,ci<op%nx .AND. &
             op%xface_active(MIN(op%nx-1,ci),cj,ck),label,op,qi,qj,qk,tail)
        CALL enqueue_neighbor(ci,cj-1,ck,cj>1 .AND. &
             op%yface_active(ci,MAX(1,cj-1),ck),label,op,qi,qj,qk,tail)
        CALL enqueue_neighbor(ci,cj+1,ck,cj<op%ny .AND. &
             op%yface_active(ci,MIN(op%ny-1,cj),ck),label,op,qi,qj,qk,tail)
        CALL enqueue_neighbor(ci,cj,ck-1,ck>1 .AND. &
             op%pface_active(ci,cj,MAX(1,ck-1)),label,op,qi,qj,qk,tail)
        CALL enqueue_neighbor(ci,cj,ck+1,ck<op%nz .AND. &
             op%pface_active(ci,cj,MIN(op%nz-1,ck)),label,op,qi,qj,qk,tail)
      END DO
    END DO; END DO; END DO
    op%ncomponent=label
  END SUBROUTINE label_components

  SUBROUTINE enqueue_neighbor(i,j,k,connected,label,op,qi,qj,qk,tail)
    INTEGER, INTENT(IN) :: i,j,k,label
    LOGICAL, INTENT(IN) :: connected
    TYPE(balance_operator_type), INTENT(INOUT) :: op
    INTEGER, INTENT(INOUT) :: qi(:),qj(:),qk(:),tail
    IF (.NOT.connected) RETURN
    IF (i<1 .OR. i>op%nx .OR. j<1 .OR. j>op%ny .OR. k<1 .OR. k>op%nz) RETURN
    IF (.NOT.op%cell_active(i,j,k) .OR. op%component(i,j,k)/=0) RETURN
    tail=tail+1; qi(tail)=i; qj(tail)=j; qk(tail)=k
    op%component(i,j,k)=label
  END SUBROUTINE enqueue_neighbor

  LOGICAL FUNCTION compatibility_ok(op,b,cfg)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: b(:,:,:)
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    INTEGER :: component
    REAL(real64) :: total,scale
    compatibility_ok=.FALSE.
    DO component=1,op%ncomponent
      total=SUM(op%volume*b,MASK=op%component==component)
      scale=SUM(op%volume*ABS(b),MASK=op%component==component)
      IF (ABS(total)>cfg%compatibility_absolute_tolerance+ &
                    cfg%compatibility_relative_tolerance*scale) RETURN
    END DO
    compatibility_ok=.TRUE.
  END FUNCTION compatibility_ok

  SUBROUTINE remove_component_means(op,array)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(INOUT) :: array(:,:,:)
    INTEGER :: component
    REAL(real64) :: measure,mean_value
    DO component=1,op%ncomponent
      measure=SUM(op%volume,MASK=op%component==component)
      IF (measure<=0.0_real64) CYCLE
      mean_value=SUM(op%volume*array,MASK=op%component==component)/measure
      WHERE(op%component==component) array=array-mean_value
    END DO
    WHERE(.NOT.op%cell_active) array=0.0_real64
  END SUBROUTINE remove_component_means

  PURE REAL(real64) FUNCTION weighted_dot(op,a,b)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: a(:,:,:),b(:,:,:)
    weighted_dot=SUM(op%volume*a*b,MASK=op%cell_active)
  END FUNCTION weighted_dot

  PURE REAL(real64) FUNCTION weighted_square_sum(op,a)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: a(:,:,:)
    weighted_square_sum=SUM(op%volume*a*a,MASK=op%cell_active)
  END FUNCTION weighted_square_sum

  PURE REAL(real64) FUNCTION active_volume(op)
    TYPE(balance_operator_type), INTENT(IN) :: op
    active_volume=SUM(op%volume,MASK=op%cell_active)
  END FUNCTION active_volume

  PURE LOGICAL FUNCTION outside_support_zero(op,du,dv,domega)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: du(:,:,:),dv(:,:,:),domega(:,:,:)
    outside_support_zero= &
      .NOT.ANY((.NOT.op%cell_active) .AND. (du>0.0_real64 .OR. du<0.0_real64)) .AND. &
      .NOT.ANY((.NOT.op%cell_active) .AND. (dv>0.0_real64 .OR. dv<0.0_real64)) .AND. &
      .NOT.ANY((.NOT.op%cell_active) .AND. &
               (domega>0.0_real64 .OR. domega<0.0_real64))
  END FUNCTION outside_support_zero

  PURE LOGICAL FUNCTION target_cancellation_ok(op,correction,target,fraction,floor_value)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: correction(:,:,:),target(:,:,:)
    REAL(real64), INTENT(IN) :: fraction,floor_value
    LOGICAL, ALLOCATABLE :: constrained(:,:,:)
    target_cancellation_ok=.FALSE.
    IF (ANY(SHAPE(correction)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(target)/=(/op%nx,op%ny,op%nz/))) RETURN
    ALLOCATE(constrained(op%nx,op%ny,op%nz))
    constrained=op%cell_active .AND. ABS(target)>floor_value
    IF (.NOT.ANY(constrained)) RETURN
    target_cancellation_ok=.NOT.ANY(constrained .AND. &
      ABS(correction)>fraction*MAX(ABS(target),floor_value))
  END FUNCTION target_cancellation_ok

  PURE LOGICAL FUNCTION omega_target_observable(op,qomega,tolerance)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: qomega(:,:,:),tolerance
    INTEGER :: i,j,k
    LOGICAL :: connected
    omega_target_observable=.FALSE.
    IF (ANY(SHAPE(qomega)/=(/op%nx,op%ny,op%nz/))) RETURN
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (ABS(qomega(i,j,k))<=tolerance) CYCLE
      connected=(k>1 .AND. op%pface_active(i,j,MAX(1,k-1))) .OR. &
                (k<op%nz .AND. op%pface_active(i,j,MIN(op%nz-1,k)))
      IF (.NOT.connected) RETURN
    END DO; END DO; END DO
    omega_target_observable=.TRUE.
  END FUNCTION omega_target_observable

  PURE LOGICAL FUNCTION operator_input_shapes_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: nx,ny,nz
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    operator_input_shapes_valid=.FALSE.
    IF (.NOT.ALLOCATED(state%pressure%value) .OR. .NOT.ALLOCATED(state%pressure%valid) .OR. &
        .NOT.ALLOCATED(state%u%value) .OR. .NOT.ALLOCATED(state%u%valid) .OR. &
        .NOT.ALLOCATED(state%v%value) .OR. .NOT.ALLOCATED(state%v%valid) .OR. &
        .NOT.ALLOCATED(state%omega%value) .OR. .NOT.ALLOCATED(state%omega%valid) .OR. &
        .NOT.ALLOCATED(state%omega_target%value) .OR. &
        .NOT.ALLOCATED(state%omega_target%valid) .OR. &
        .NOT.ALLOCATED(state%balance_beta)) RETURN
    IF (ANY(SHAPE(state%pressure%value)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%u%value)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%v%value)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%omega%value)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%omega_target%value)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%balance_beta)/=(/nx,ny,nz/))) RETURN
    operator_input_shapes_valid=.TRUE.
  END FUNCTION operator_input_shapes_valid

  PURE LOGICAL FUNCTION boundary_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: target(2)
    target=(/state%grid%nx,state%grid%ny/)
    boundary_contract_valid=.FALSE.
    IF (.NOT.ALLOCATED(state%omega_top_boundary%value) .OR. &
        .NOT.ALLOCATED(state%omega_top_boundary%valid) .OR. &
        .NOT.ALLOCATED(state%omega_top_boundary%quality) .OR. &
        .NOT.ALLOCATED(state%omega_top_boundary%source) .OR. &
        .NOT.ALLOCATED(state%omega_bottom_boundary%value) .OR. &
        .NOT.ALLOCATED(state%omega_bottom_boundary%valid) .OR. &
        .NOT.ALLOCATED(state%omega_bottom_boundary%quality) .OR. &
        .NOT.ALLOCATED(state%omega_bottom_boundary%source)) RETURN
    IF (ANY(SHAPE(state%omega_top_boundary%value)/=target) .OR. &
        ANY(SHAPE(state%omega_top_boundary%valid)/=target) .OR. &
        ANY(SHAPE(state%omega_top_boundary%quality)/=target) .OR. &
        ANY(SHAPE(state%omega_top_boundary%source)/=target) .OR. &
        ANY(SHAPE(state%omega_bottom_boundary%value)/=target) .OR. &
        ANY(SHAPE(state%omega_bottom_boundary%valid)/=target) .OR. &
        ANY(SHAPE(state%omega_bottom_boundary%quality)/=target) .OR. &
        ANY(SHAPE(state%omega_bottom_boundary%source)/=target)) RETURN
    boundary_contract_valid=TRIM(state%omega_top_boundary%unit)=='Pa s-1' .AND. &
      TRIM(state%omega_bottom_boundary%unit)=='Pa s-1' .AND. &
      state%omega_top_boundary%valid_time==state%pressure%valid_time .AND. &
      state%omega_bottom_boundary%valid_time==state%pressure%valid_time .AND. &
      ALL(state%omega_top_boundary%valid) .AND. &
      ALL(state%omega_bottom_boundary%valid) .AND. &
      ALL(state%omega_top_boundary%quality>=0_int32) .AND. &
      ALL(state%omega_bottom_boundary%quality>=0_int32) .AND. &
      ALL(state%omega_top_boundary%source>0_int32) .AND. &
      ALL(state%omega_bottom_boundary%source>0_int32) .AND. &
      .NOT.ANY(.NOT.ieee_is_finite(state%omega_top_boundary%value)) .AND. &
      .NOT.ANY(.NOT.ieee_is_finite(state%omega_bottom_boundary%value))
  END FUNCTION boundary_contract_valid

  PURE LOGICAL FUNCTION operator_array_shapes_valid(op,u,v,omega,residual)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: u(:,:,:),v(:,:,:),omega(:,:,:),residual(:,:,:)
    INTEGER :: target(3)
    target=(/op%nx,op%ny,op%nz/)
    operator_array_shapes_valid=ALL(SHAPE(u)==target) .AND. ALL(SHAPE(v)==target) .AND. &
      ALL(SHAPE(omega)==target) .AND. ALL(SHAPE(residual)==target)
  END FUNCTION operator_array_shapes_valid

  PURE LOGICAL FUNCTION four_shapes_match(op,a,b,c,d)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: a(:,:,:),b(:,:,:),c(:,:,:),d(:,:,:)
    INTEGER :: target(3)
    target=(/op%nx,op%ny,op%nz/)
    four_shapes_match=ALL(SHAPE(a)==target) .AND. ALL(SHAPE(b)==target) .AND. &
                      ALL(SHAPE(c)==target) .AND. ALL(SHAPE(d)==target)
  END FUNCTION four_shapes_match

  PURE LOGICAL FUNCTION config_valid(config)
    TYPE(balance_operator_config), INTENT(IN) :: config
    config_valid=ieee_is_finite(config%kappa_u) .AND. config%kappa_u>0.0_real64 .AND. &
      ieee_is_finite(config%kappa_v) .AND. config%kappa_v>0.0_real64 .AND. &
      ieee_is_finite(config%kappa_omega) .AND. config%kappa_omega>0.0_real64 .AND. &
      ieee_is_finite(config%minimum_beta) .AND. config%minimum_beta>0.0_real64 .AND. &
      config%minimum_beta<1.0_real64 .AND. &
      ieee_is_finite(config%solver_relative_tolerance) .AND. &
      config%solver_relative_tolerance>0.0_real64 .AND. &
      ieee_is_finite(config%solver_absolute_tolerance) .AND. &
      config%solver_absolute_tolerance>0.0_real64 .AND. &
      ieee_is_finite(config%compatibility_relative_tolerance) .AND. &
      config%compatibility_relative_tolerance>=0.0_real64 .AND. &
      ieee_is_finite(config%compatibility_absolute_tolerance) .AND. &
      config%compatibility_absolute_tolerance>=0.0_real64 .AND. &
      config%maximum_iterations>0 .AND. &
      config%attenuation_attempts>0 .AND. config%attenuation_factor>0.0_real64 .AND. &
      config%attenuation_factor<1.0_real64 .AND. &
      config%required_residual_fraction>0.0_real64 .AND. &
      config%required_residual_fraction<1.0_real64 .AND. &
      ieee_is_finite(config%maximum_wind_increment) .AND. &
      config%maximum_wind_increment>0.0_real64 .AND. &
      ieee_is_finite(config%maximum_omega_increment) .AND. &
      config%maximum_omega_increment>0.0_real64 .AND. &
      ieee_is_finite(config%maximum_target_cancellation_fraction) .AND. &
      config%maximum_target_cancellation_fraction>=0.0_real64 .AND. &
      ieee_is_finite(config%momentum_relative_tolerance) .AND. &
      config%momentum_relative_tolerance>=0.0_real64 .AND. &
      ieee_is_finite(config%momentum_absolute_tolerance) .AND. &
      config%momentum_absolute_tolerance>=0.0_real64
  END FUNCTION config_valid

END MODULE cloud_bal_balance_operator
