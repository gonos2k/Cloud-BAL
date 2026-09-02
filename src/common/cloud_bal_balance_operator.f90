! Local projection of a proposed increment on the canonical LAPS A grid.
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
  ! A zero science threshold still must not authorize real32 arithmetic nulls.
  REAL(real64), PARAMETER :: FACE_RESPONSE_ROUNDOFF = &
    64.0_real64*REAL(EPSILON(1.0_real32),real64)

  TYPE, PUBLIC :: balance_operator_config
    REAL(real64) :: kappa_u = 16.0_real64
    REAL(real64) :: kappa_v = 16.0_real64
    REAL(real64) :: kappa_omega = 0.25_real64
    REAL(real64) :: minimum_beta = 1.0e-3_real64
    REAL(real64) :: solver_residual_fraction = 2.0e-3_real64
    REAL(real64) :: solver_absolute_tolerance = 1.0e-12_real64
    REAL(real64) :: compatibility_relative_tolerance = 1.0e-11_real64
    REAL(real64) :: compatibility_absolute_tolerance = 1.0e-14_real64
    INTEGER :: maximum_iterations = 800
    INTEGER :: residual_refresh_interval = 50
    REAL(real64) :: required_residual_fraction = 0.25_real64
    REAL(real64) :: physical_residual_tolerance = 1.0e-7_real64
    REAL(real64) :: maximum_physical_residual = 1.0e-3_real64
    REAL(real64) :: maximum_wind_increment = 10.0_real64
    REAL(real64) :: maximum_omega_increment = 5.0_real64
    REAL(real64) :: minimum_target_response_ratio = 0.05_real64
    REAL(real64) :: maximum_target_response_ratio = 1.50_real64
    REAL(real64) :: minimum_trust_region_fraction = 0.05_real64
    REAL(real64) :: increment_headroom = 0.95_real64
    REAL(real64) :: geostrophic_relative_tolerance = 0.05_real64
    REAL(real64) :: geostrophic_absolute_tolerance = 1.0e-3_real64
    INTEGER :: minimum_held_out_samples = 20
    INTEGER :: minimum_held_out_radars = 2
  END TYPE balance_operator_config

  TYPE, PUBLIC :: balance_operator_type
    INTEGER :: nx=0,ny=0,nz=0
    REAL(real64), ALLOCATABLE :: volume(:,:,:)
    REAL(real64), ALLOCATABLE :: dx(:,:),dy(:,:),dp(:,:,:)
    REAL(real64), ALLOCATABLE :: ku(:,:,:),kv(:,:,:),ko(:,:,:)
    LOGICAL, ALLOCATABLE :: cell_usable(:,:,:)
    LOGICAL, ALLOCATABLE :: cell_active(:,:,:)
    LOGICAL, ALLOCATABLE :: omega_authorized(:,:,:)
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
  PUBLIC :: balance_beta_active
  PUBLIC :: state_continuity_residual
  PUBLIC :: target_response_failure_fraction
  PUBLIC :: geostrophic_residual

CONTAINS

  SUBROUTINE build_balance_operator(state,config,op,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(balance_operator_config), INTENT(IN) :: config
    TYPE(balance_operator_type), INTENT(OUT) :: op
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: nx,ny,nz,i,j,k
    REAL(real64) :: denom

    status=STATUS_FAILED; reason=REASON_SHAPE
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    IF (nx<4 .OR. ny<4 .OR. nz<2) RETURN
    IF (.NOT.config_valid(config)) THEN; reason=REASON_RANGE; RETURN; END IF
    IF (.NOT.operator_input_shapes_valid(state)) RETURN
    IF (.NOT.boundary_contract_valid(state)) THEN; reason=REASON_METADATA; RETURN; END IF
    IF (ANY(.NOT.ieee_is_finite(state%grid%dx)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%dy)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%dp)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%pressure_mass_measure)) .OR. &
        ANY(state%grid%dx<=0.0_real64) .OR. ANY(state%grid%dy<=0.0_real64) .OR. &
        ANY(state%grid%dp<=0.0_real64) .OR. &
        ANY(state%grid%pressure_mass_measure<=0.0_real64)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    DO k=1,nz-1
      IF (ANY(state%pressure%value(:,:,k)<=state%pressure%value(:,:,k+1))) THEN
        reason=REASON_RANGE; RETURN
      END IF
    END DO

    op%nx=nx; op%ny=ny; op%nz=nz
    ALLOCATE(op%volume(nx,ny,nz),op%dx(nx,ny),op%dy(nx,ny), &
             op%dp(nx,ny,nz), &
             op%ku(nx,ny,nz),op%kv(nx,ny,nz),op%ko(nx,ny,nz), &
             op%cell_usable(nx,ny,nz),op%cell_active(nx,ny,nz), &
             op%omega_authorized(nx,ny,nz), &
             op%component(nx,ny,nz))
    ALLOCATE(op%xface_active(nx-1,ny,nz),op%xface_area(nx-1,ny,nz), &
             op%xleft_weight(nx-1,ny,nz),op%xright_weight(nx-1,ny,nz))
    ALLOCATE(op%yface_active(nx,ny-1,nz),op%yface_area(nx,ny-1,nz), &
             op%yleft_weight(nx,ny-1,nz),op%yright_weight(nx,ny-1,nz))
    ALLOCATE(op%pface_active(nx,ny,nz-1),op%pface_area(nx,ny,nz-1), &
             op%pleft_weight(nx,ny,nz-1),op%pright_weight(nx,ny,nz-1))
    op%volume=state%grid%pressure_mass_measure
    op%dx=state%grid%dx; op%dy=state%grid%dy; op%dp=state%grid%dp
    op%cell_usable=state%above_ground .AND. &
      cell_is_usable(state%pressure%valid,state%pressure%quality,state%pressure%source) .AND. &
      cell_is_usable(state%u%valid,state%u%quality,state%u%source) .AND. &
      cell_is_usable(state%v%valid,state%v%quality,state%v%source) .AND. &
      cell_is_usable(state%omega%valid,state%omega%quality,state%omega%source)
    op%cell_active=op%cell_usable .AND. &
                   balance_beta_active(state%balance_beta,config%minimum_beta)
    op%omega_authorized=op%cell_active .AND. dynamic_target_is_resolved( &
      state%omega_target%value,state%omega%value,state%omega_target%valid, &
      state%omega_target%quality,state%omega_target%source)
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
    END WHERE
    WHERE(op%omega_authorized)
      op%ko=REAL(state%balance_beta,real64)*config%kappa_omega
    END WHERE
    ! The background flux through the compact-support boundary is fixed.
    ! Therefore the normal component of the increment is zero there.
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (i==1 .OR. i==nx) THEN
        op%ku(i,j,k)=0.0_real64
      ELSE IF (.NOT.(op%cell_active(i-1,j,k) .AND. &
                     op%cell_active(i+1,j,k))) THEN
        op%ku(i,j,k)=0.0_real64
      END IF
      IF (j==1 .OR. j==ny) THEN
        op%kv(i,j,k)=0.0_real64
      ELSE IF (.NOT.(op%cell_active(i,j-1,k) .AND. &
                     op%cell_active(i,j+1,k))) THEN
        op%kv(i,j,k)=0.0_real64
      END IF
    END DO; END DO; END DO

    DO k=1,nz; DO j=1,ny; DO i=1,nx-1
      denom=op%dx(i,j)+op%dx(i+1,j)
      op%xleft_weight(i,j,k)=op%dx(i+1,j)/denom
      op%xright_weight(i,j,k)=op%dx(i,j)/denom
      op%xface_area(i,j,k)=0.5_real64*(op%dy(i,j)+op%dy(i+1,j))* &
                           0.5_real64*(op%dp(i,j,k)+op%dp(i+1,j,k))/GRAVITY
      op%xface_active(i,j,k)=op%cell_active(i,j,k) .AND. &
                             op%cell_active(i+1,j,k) .AND. &
                             (op%ku(i,j,k)>0.0_real64 .OR. &
                              op%ku(i+1,j,k)>0.0_real64)
    END DO; END DO; END DO
    DO k=1,nz; DO j=1,ny-1; DO i=1,nx
      denom=op%dy(i,j)+op%dy(i,j+1)
      op%yleft_weight(i,j,k)=op%dy(i,j+1)/denom
      op%yright_weight(i,j,k)=op%dy(i,j)/denom
      op%yface_area(i,j,k)=0.5_real64*(op%dx(i,j)+op%dx(i,j+1))* &
                           0.5_real64*(op%dp(i,j,k)+op%dp(i,j+1,k))/GRAVITY
      op%yface_active(i,j,k)=op%cell_active(i,j,k) .AND. &
                             op%cell_active(i,j+1,k) .AND. &
                             (op%kv(i,j,k)>0.0_real64 .OR. &
                              op%kv(i,j+1,k)>0.0_real64)
    END DO; END DO; END DO
    DO k=1,nz-1; DO j=1,ny; DO i=1,nx
      denom=op%dp(i,j,k)+op%dp(i,j,k+1)
      op%pleft_weight(i,j,k)=op%dp(i,j,k+1)/denom
      op%pright_weight(i,j,k)=op%dp(i,j,k)/denom
      op%pface_area(i,j,k)=op%dx(i,j)*op%dy(i,j)/GRAVITY
      op%pface_active(i,j,k)=op%cell_active(i,j,k) .AND. &
                             op%cell_active(i,j,k+1) .AND. &
                             (op%ko(i,j,k)>0.0_real64 .OR. &
                              op%ko(i,j,k+1)>0.0_real64)
      IF (op%pface_active(i,j,k)) THEN
        IF (ABS(REAL(state%pressure%value(i,j,k),real64)- &
                   REAL(state%pressure%value(i,j,k+1),real64))<= &
            EPSILON(1.0_real64)*MAX(ABS(REAL(state%pressure%value(i,j,k),real64)), &
                                    ABS(REAL(state%pressure%value(i,j,k+1),real64)))) THEN
          reason=REASON_RANGE; RETURN
        END IF
      END IF
    END DO; END DO; END DO
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.pressure_increment_is_closed(op,i,j,k)) op%ko(i,j,k)=0.0_real64
    END DO; END DO; END DO
    CALL label_components(op)
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE build_balance_operator

  PURE LOGICAL FUNCTION pressure_increment_is_closed(op,i,j,k)
    TYPE(balance_operator_type), INTENT(IN) :: op
    INTEGER, INTENT(IN) :: i,j,k
    LOGICAL :: has_face
    pressure_increment_is_closed=.FALSE.; has_face=.FALSE.
    IF (k>1) THEN
      IF (op%cell_usable(i,j,k-1)) THEN
        IF (.NOT.op%pface_active(i,j,k-1)) RETURN
        has_face=.TRUE.
      END IF
    END IF
    IF (k<op%nz) THEN
      IF (op%cell_usable(i,j,k+1)) THEN
        IF (.NOT.op%pface_active(i,j,k)) RETURN
        has_face=.TRUE.
      END IF
    END IF
    pressure_increment_is_closed=has_face
  END FUNCTION pressure_increment_is_closed

  SUBROUTINE apply_continuity_operator(op,u,v,omega,residual,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: u(:,:,:),v(:,:,:),omega(:,:,:)
    REAL(real64), INTENT(OUT) :: residual(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k
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
      residual(i,j,k+1)=residual(i,j,k+1)+flux/op%volume(i,j,k+1)
      residual(i,j,k)=residual(i,j,k)-flux/op%volume(i,j,k)
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
    INTEGER :: i,j,k
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
      contribution=op%pface_area(i,j,k)*(lambda(i,j,k+1)-lambda(i,j,k))
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
    status=STATUS_FAILED
    CALL apply_adjoint_metric(op,lambda,du,dv,domega,status)
    IF (status/=STATUS_OK) RETURN
    du=-op%ku*du; dv=-op%kv*dv; domega=-op%ko*domega
    ! Horizontal winds may respond throughout the localized support.  Omega is
    ! a different authority: it may change only at an explicit dynamic target.
    WHERE(.NOT.op%omega_authorized) domega=0.0_real64
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
    CALL apply_normal_operator_work(op,lambda,l_lambda,du,dv,domega,status)
  END SUBROUTINE apply_normal_operator

  SUBROUTINE apply_normal_operator_work(op,lambda,l_lambda,du,dv,domega,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: lambda(:,:,:)
    REAL(real64), INTENT(OUT) :: l_lambda(:,:,:),du(:,:,:),dv(:,:,:),domega(:,:,:)
    INTEGER, INTENT(OUT) :: status

    CALL apply_balance_correction(op,lambda,du,dv,domega,status)
    IF (status/=STATUS_OK) RETURN
    CALL apply_continuity_operator(op,du,dv,domega,l_lambda,status)
    IF (status==STATUS_OK) l_lambda=-l_lambda
  END SUBROUTINE apply_normal_operator_work

  SUBROUTINE apply_localized_balance(state_in,state_out,result,config)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    TYPE(stage_result), INTENT(OUT) :: result
    TYPE(balance_operator_config), INTENT(IN), OPTIONAL :: config
    TYPE(balance_operator_config) :: cfg
    TYPE(balance_operator_type) :: op
    TYPE(cloud_bal_state_type) :: candidate
    TYPE(stage_result) :: candidate_result
    REAL(real64), ALLOCATABLE :: q_requested(:,:,:),qomega(:,:,:),b(:,:,:),lambda(:,:,:)
    REAL(real64), ALLOCATABLE :: du(:,:,:),dv(:,:,:),do_corr(:,:,:),domega(:,:,:)
    REAL(real64), ALLOCATABLE :: r_background(:,:,:),r_proposed(:,:,:)
    REAL(real64), ALLOCATABLE :: r_projected(:,:,:),r_candidate(:,:,:)
    LOGICAL, ALLOCATABLE :: modified(:,:,:)
    REAL(real64) :: rb_rms,rb_max,rp_rms,rp_max,ri_rms,ri_max,rc_rms,rc_max
    REAL(real64) :: geo_background,geo_candidate,maxwind,maxomega
    REAL(real64) :: solver_rms,solver_max,target_fraction,target_response_failure
    REAL(real64) :: raw_maxwind,raw_maxomega,operator_identity_max
    INTEGER :: status,reason,iterations,solver_reason
    LOGICAL :: accepted

    IF (PRESENT(config)) cfg=config
    ! Surface thermodynamic fields are not inputs to this pressure-coordinate solve.
    CALL validate_canonical_state(state_in,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    IF (.NOT.ANY(dynamic_target_is_resolved(state_in%omega_target%value, &
                 state_in%omega%value,state_in%omega_target%valid, &
                 state_in%omega_target%quality,state_in%omega_target%source) .AND. &
                 balance_beta_active(state_in%balance_beta,cfg%minimum_beta))) THEN
      state_out=state_in
      CALL initialize_stage_result(result,state_in%grid%nx,state_in%grid%ny, &
                                   state_in%grid%nz,STATUS_OK,REASON_NONE)
      RETURN
    END IF
    CALL validate_geostrophic_inputs(state_in,status,reason)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    CALL build_balance_operator(state_in,cfg,op,status,reason)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    ALLOCATE(q_requested(op%nx,op%ny,op%nz),qomega(op%nx,op%ny,op%nz), &
             b(op%nx,op%ny,op%nz), &
             lambda(op%nx,op%ny,op%nz),du(op%nx,op%ny,op%nz), &
             dv(op%nx,op%ny,op%nz),do_corr(op%nx,op%ny,op%nz), &
             domega(op%nx,op%ny,op%nz), &
             r_background(op%nx,op%ny,op%nz),r_proposed(op%nx,op%ny,op%nz), &
             r_projected(op%nx,op%ny,op%nz),r_candidate(op%nx,op%ny,op%nz), &
             modified(op%nx,op%ny,op%nz))
    CALL state_continuity_residual(op,state_in,r_background,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    CALL geostrophic_residual(state_in,op,geo_background,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF

    q_requested=0.0_real64
    WHERE(op%omega_authorized)
      q_requested=REAL(state_in%omega_target%value,real64)- &
             REAL(state_in%omega%value,real64)
    END WHERE
    IF (MAXVAL(ABS(q_requested))<=cfg%solver_absolute_tolerance) THEN
      state_out=state_in
      CALL initialize_stage_result(result,op%nx,op%ny,op%nz,STATUS_OK,REASON_NONE)
      RETURN
    END IF
    IF (.NOT.omega_target_is_observable( &
        op,q_requested,cfg%solver_absolute_tolerance, &
        cfg%minimum_target_response_ratio)) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_DEGRADED,REASON_GATE)
      RETURN
    END IF
    du=0.0_real64; dv=0.0_real64
    CALL apply_continuity_operator(op,du,dv,q_requested,r_proposed,status)
    IF (status/=STATUS_OK .OR. .NOT.compatibility_ok(op,r_proposed,cfg)) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_SOLVER)
      result%numerical%solver_reason=SOLVER_INCOMPATIBLE_RHS
      RETURN
    END IF
    b=r_proposed
    CALL solve_normal_equation(op,b,cfg,lambda,du,dv,do_corr,iterations,status, &
                               solver_reason,solver_rms,solver_max)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_SOLVER)
      CALL continuity_norms(op,r_proposed,rp_rms,rp_max)
      result%numerical%solver_reason=solver_reason
      result%numerical%solver_iterations=iterations
      result%numerical%continuity_proposed_increment_rms=rp_rms
      result%numerical%continuity_proposed_increment_max=rp_max
      result%numerical%continuity_projected_increment_rms=solver_rms
      result%numerical%continuity_projected_increment_max=solver_max
      RETURN
    END IF
    CALL apply_balance_correction(op,lambda,du,dv,do_corr,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      result%numerical%solver_reason=SOLVER_CORRECTION_FAILED
      result%numerical%solver_iterations=iterations
      RETURN
    END IF
    CALL increment_maxima(op,du,dv,q_requested,do_corr,raw_maxwind,raw_maxomega)
    target_fraction=trust_region_fraction(cfg,raw_maxwind,raw_maxomega)
    qomega=target_fraction*q_requested
    du=target_fraction*du
    dv=target_fraction*dv
    do_corr=target_fraction*do_corr
    r_proposed=target_fraction*r_proposed
    CALL make_candidate(state_in,op,qomega,candidate,du,dv,do_corr,domega, &
                        modified,maxwind,maxomega)
    CALL validate_canonical_state(candidate,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    CALL apply_continuity_operator(op,du,dv,domega,r_projected,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    CALL state_continuity_residual(op,candidate,r_candidate,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    CALL continuity_norms(op,r_background,rb_rms,rb_max)
    CALL continuity_norms(op,r_proposed,rp_rms,rp_max)
    CALL continuity_norms(op,r_projected,ri_rms,ri_max)
    CALL continuity_norms(op,r_candidate,rc_rms,rc_max)
    operator_identity_max=MAXVAL(ABS(r_candidate-r_background-r_projected), &
                                 MASK=op%cell_active)
    CALL geostrophic_residual(candidate,op,geo_candidate,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    CALL initialize_stage_result(candidate_result,op%nx,op%ny,op%nz, &
                                 STATUS_OK,REASON_NONE)
    candidate_result%numerical%solver_iterations=iterations
    candidate_result%numerical%solver_reason=solver_reason
    candidate_result%numerical%continuity_background_rms=rb_rms
    candidate_result%numerical%continuity_background_max=rb_max
    candidate_result%numerical%continuity_proposed_increment_rms=rp_rms
    candidate_result%numerical%continuity_proposed_increment_max=rp_max
    candidate_result%numerical%continuity_projected_increment_rms=ri_rms
    candidate_result%numerical%continuity_projected_increment_max=ri_max
    candidate_result%numerical%continuity_candidate_rms=rc_rms
    candidate_result%numerical%continuity_candidate_max=rc_max
    candidate_result%numerical%continuity_operator_identity_max=operator_identity_max
    candidate_result%numerical%geostrophic_background_rms=geo_background
    candidate_result%numerical%geostrophic_candidate_rms=geo_candidate
    candidate_result%numerical%max_wind_increment=maxwind
    candidate_result%numerical%max_omega_increment=maxomega
    candidate_result%numerical%trust_region_fraction=target_fraction
    candidate_result%numerical%unscaled_max_wind_increment=raw_maxwind
    candidate_result%numerical%unscaled_max_omega_increment=raw_maxomega
    target_response_failure=target_response_failure_fraction(op,domega,q_requested, &
      cfg%solver_absolute_tolerance,cfg%minimum_target_response_ratio, &
      cfg%maximum_target_response_ratio)
    candidate_result%numerical%target_response_failure_fraction= &
      target_response_failure
    CALL increment_mode_metrics(op,du,dv,candidate_result%numerical%divergent_rms, &
                                candidate_result%numerical%rotational_rms)
    candidate_result%changed=modified

    CALL evaluate_candidate_gates(op,cfg,du,dv,domega, &
      rb_rms,rb_max,rp_rms,rp_max,ri_rms,ri_max,rc_rms,rc_max, &
      geo_background,geo_candidate,maxwind,maxomega, &
      target_fraction,target_response_failure,operator_identity_max, &
      candidate_result%numerical%acceptance_failures)
    accepted=candidate_result%numerical%acceptance_failures==0_int32

    IF (.NOT.accepted) THEN
      state_out=state_in
      result=candidate_result
      result%status=STATUS_DEGRADED
      result%reason_code=REASON_GATE
      RETURN
    END IF
    ! These are finite-difference diagnostics, not a Helmholtz decomposition.
    ! They therefore have no authority to accept or reject a candidate.
    CALL evaluate_los_gate(state_in,candidate,candidate_result,cfg,status)
    IF (status/=STATUS_OK) THEN
      state_out=state_in
      result=candidate_result
      result%status=STATUS_DEGRADED
      result%reason_code=REASON_GATE
      RETURN
    END IF
    CALL commit_candidate(state_in,candidate,candidate_result,state_out,result)
  END SUBROUTINE apply_localized_balance

  SUBROUTINE make_candidate(input,op,target,candidate,du,dv,domega_correction, &
                            domega,modified,max_wind,max_omega)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: target(:,:,:)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: candidate
    REAL(real64), INTENT(INOUT) :: du(:,:,:),dv(:,:,:),domega_correction(:,:,:)
    REAL(real64), INTENT(OUT) :: domega(:,:,:)
    LOGICAL, INTENT(OUT) :: modified(:,:,:)
    REAL(real64), INTENT(OUT) :: max_wind,max_omega
    INTEGER :: i,j,k

    candidate=input
    max_wind=0.0_real64
    max_omega=0.0_real64
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.op%cell_active(i,j,k)) THEN
        du(i,j,k)=0.0_real64; dv(i,j,k)=0.0_real64
        domega(i,j,k)=0.0_real64; domega_correction(i,j,k)=0.0_real64
        modified(i,j,k)=.FALSE.
        CYCLE
      END IF
      ! omega_target remains the requested pseudo-observation.  The accepted
      ! fraction belongs to the balance result, not to a rewritten target.
      IF (du(i,j,k)/=0.0_real64) &
        candidate%u%value(i,j,k)=REAL(REAL(input%u%value(i,j,k),real64)+ &
                                      du(i,j,k),real32)
      IF (dv(i,j,k)/=0.0_real64) &
        candidate%v%value(i,j,k)=REAL(REAL(input%v%value(i,j,k),real64)+ &
                                      dv(i,j,k),real32)
      IF (op%omega_authorized(i,j,k)) THEN
        domega(i,j,k)=target(i,j,k)+domega_correction(i,j,k)
      ELSE
        domega(i,j,k)=0.0_real64
        domega_correction(i,j,k)=0.0_real64
      END IF
      IF (domega(i,j,k)/=0.0_real64) &
        candidate%omega%value(i,j,k)=REAL(REAL(input%omega%value(i,j,k),real64)+ &
                                           domega(i,j,k),real32)

      ! Diagnostics use exactly the rounded values that would be published.
      du(i,j,k)=REAL(candidate%u%value(i,j,k),real64)- &
                REAL(input%u%value(i,j,k),real64)
      dv(i,j,k)=REAL(candidate%v%value(i,j,k),real64)- &
                REAL(input%v%value(i,j,k),real64)
      domega(i,j,k)=REAL(candidate%omega%value(i,j,k),real64)- &
                    REAL(input%omega%value(i,j,k),real64)
      domega_correction(i,j,k)=domega(i,j,k)-target(i,j,k)
      modified(i,j,k)=du(i,j,k)/=0.0_real64 .OR. dv(i,j,k)/=0.0_real64 .OR. &
                      domega(i,j,k)/=0.0_real64
      IF (du(i,j,k)/=0.0_real64) THEN
        candidate%u%source(i,j,k)=IOR(candidate%u%source(i,j,k), &
                                      SOURCE_BALANCE_OPERATOR)
      END IF
      IF (dv(i,j,k)/=0.0_real64) THEN
        candidate%v%source(i,j,k)=IOR(candidate%v%source(i,j,k), &
                                      SOURCE_BALANCE_OPERATOR)
      END IF
      IF (domega(i,j,k)/=0.0_real64) THEN
        candidate%omega%source(i,j,k)=IOR(candidate%omega%source(i,j,k), &
                                          SOURCE_BALANCE_OPERATOR)
      END IF
      max_wind=MAX(max_wind,HYPOT(du(i,j,k),dv(i,j,k)))
      max_omega=MAX(max_omega,ABS(domega(i,j,k)))
    END DO; END DO; END DO
  END SUBROUTINE make_candidate

  SUBROUTINE evaluate_candidate_gates(op,cfg,du,dv,domega, &
                                      rb_rms,rb_max,rp_rms,rp_max, &
                                      ri_rms,ri_max,rc_rms,rc_max,geo_background, &
                                      geo_candidate,max_wind,max_omega, &
                                      target_fraction,response_failure_fraction, &
                                      operator_identity_max,failures)
    TYPE(balance_operator_type), INTENT(IN) :: op
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    REAL(real64), INTENT(IN) :: du(:,:,:),dv(:,:,:),domega(:,:,:)
    REAL(real64), INTENT(IN) :: rb_rms,rb_max,rp_rms,rp_max,ri_rms,ri_max
    REAL(real64), INTENT(IN) :: rc_rms,rc_max,geo_background,geo_candidate
    REAL(real64), INTENT(IN) :: max_wind,max_omega
    REAL(real64), INTENT(IN) :: target_fraction,response_failure_fraction
    REAL(real64), INTENT(IN) :: operator_identity_max
    INTEGER(int32), INTENT(OUT) :: failures

    failures=0_int32
    IF (ri_rms>MAX(cfg%required_residual_fraction*rp_rms, &
                  cfg%solver_absolute_tolerance)) &
      failures=IOR(failures,GATE_INCREMENT_RMS)
    IF (ri_max>MAX(cfg%required_residual_fraction*rp_max, &
                  cfg%solver_absolute_tolerance)) &
      failures=IOR(failures,GATE_INCREMENT_MAX)
    IF (rc_rms>physical_residual_limit(rb_rms,cfg)) &
      failures=IOR(failures,GATE_PHYSICAL_RMS)
    IF (rc_max>physical_residual_limit(rb_max,cfg)) &
      failures=IOR(failures,GATE_PHYSICAL_MAX)
    IF (max_wind>cfg%maximum_wind_increment) &
      failures=IOR(failures,GATE_WIND_INCREMENT)
    IF (max_omega>cfg%maximum_omega_increment) &
      failures=IOR(failures,GATE_OMEGA_INCREMENT)
    IF (response_failure_fraction>0.0_real64) &
      failures=IOR(failures,GATE_TARGET_RESPONSE)
    IF (target_fraction<cfg%minimum_trust_region_fraction) &
      failures=IOR(failures,GATE_TARGET_FRACTION)
    IF (operator_identity_max>cfg%solver_absolute_tolerance) &
      failures=IOR(failures,GATE_OPERATOR_IDENTITY)
    IF (geo_candidate>geo_background*(1.0_real64+ &
        cfg%geostrophic_relative_tolerance)+cfg%geostrophic_absolute_tolerance) &
      failures=IOR(failures,GATE_GEOSTROPHIC)
    IF (.NOT.outside_support_zero(op,du,dv,domega)) &
      failures=IOR(failures,GATE_OUTSIDE_SUPPORT)
  END SUBROUTINE evaluate_candidate_gates

  SUBROUTINE increment_maxima(op,du,dv,target,correction,max_wind,max_omega)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: du(:,:,:),dv(:,:,:),target(:,:,:),correction(:,:,:)
    REAL(real64), INTENT(OUT) :: max_wind,max_omega
    INTEGER :: i,j,k
    max_wind=0.0_real64; max_omega=0.0_real64
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.op%cell_active(i,j,k)) CYCLE
      max_wind=MAX(max_wind,HYPOT(du(i,j,k),dv(i,j,k)))
      max_omega=MAX(max_omega,ABS(target(i,j,k)+correction(i,j,k)))
    END DO; END DO; END DO
  END SUBROUTINE increment_maxima

  PURE REAL(real64) FUNCTION trust_region_fraction(cfg,max_wind,max_omega)
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    REAL(real64), INTENT(IN) :: max_wind,max_omega
    trust_region_fraction=1.0_real64
    IF (max_wind>0.0_real64) trust_region_fraction=MIN(trust_region_fraction, &
      cfg%increment_headroom*cfg%maximum_wind_increment/max_wind)
    IF (max_omega>0.0_real64) trust_region_fraction=MIN(trust_region_fraction, &
      cfg%increment_headroom*cfg%maximum_omega_increment/max_omega)
  END FUNCTION trust_region_fraction

  PURE REAL(real64) FUNCTION physical_residual_limit(background,cfg)
    REAL(real64), INTENT(IN) :: background
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    physical_residual_limit=MIN(background+cfg%physical_residual_tolerance, &
                                cfg%maximum_physical_residual)
  END FUNCTION physical_residual_limit

  PURE ELEMENTAL LOGICAL FUNCTION balance_beta_active(beta,minimum_beta)
    REAL(real32), INTENT(IN) :: beta
    REAL(real64), INTENT(IN) :: minimum_beta
    balance_beta_active=REAL(beta,real64)> &
      REAL(REAL(minimum_beta,real32),real64)
  END FUNCTION balance_beta_active

  ! Conjugate Residual minimizes the same continuity residual used by the
  ! acceptance gate.  Periodic true-residual refreshes prevent recursive
  ! roundoff from masquerading as convergence on the singular Neumann system.
  SUBROUTINE solve_normal_equation(op,b,cfg,lambda,work_u,work_v,work_o,iterations, &
                                   status,failure_reason,final_rms,final_max)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: b(:,:,:)
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    REAL(real64), INTENT(OUT) :: lambda(:,:,:)
    REAL(real64), INTENT(INOUT) :: work_u(:,:,:),work_v(:,:,:),work_o(:,:,:)
    INTEGER, INTENT(OUT) :: iterations,status,failure_reason
    REAL(real64), INTENT(OUT) :: final_rms,final_max
    REAL(real64), ALLOCATABLE :: r(:,:,:),p(:,:,:),lp(:,:,:),lr(:,:,:)
    REAL(real64) :: numerator,denom,alpha,beta,b_rms,b_max,r_rms,r_max
    INTEGER :: operator_status

    ALLOCATE(r(op%nx,op%ny,op%nz),p(op%nx,op%ny,op%nz), &
             lp(op%nx,op%ny,op%nz),lr(op%nx,op%ny,op%nz))
    lambda=0.0_real64; r=b; iterations=0; status=STATUS_FAILED
    failure_reason=SOLVER_BREAKDOWN
    CALL continuity_norms(op,b,b_rms,b_max)
    final_rms=b_rms; final_max=b_max
    IF (b_rms<=cfg%solver_absolute_tolerance .AND. &
        b_max<=cfg%solver_absolute_tolerance) THEN
      status=STATUS_OK; failure_reason=SOLVER_NOT_RUN; RETURN
    END IF
    CALL remove_component_means(op,r)
    p=r
    CALL apply_normal_operator_work(op,p,lp,work_u,work_v,work_o,operator_status)
    IF (operator_status/=STATUS_OK) RETURN
    DO iterations=1,cfg%maximum_iterations
      numerator=weighted_dot(op,r,lp)
      denom=weighted_dot(op,lp,lp)
      IF (.NOT.ieee_is_finite(numerator) .OR. numerator<=0.0_real64 .OR. &
          .NOT.ieee_is_finite(denom) .OR. denom<=0.0_real64) RETURN
      alpha=numerator/denom
      IF (.NOT.ieee_is_finite(alpha)) RETURN
      lambda=lambda+alpha*p
      CALL remove_component_means(op,lambda)
      r=r-alpha*lp
      CALL remove_component_means(op,r)
      CALL continuity_norms(op,r,r_rms,r_max)
      final_rms=r_rms
      final_max=r_max
      IF (solver_residual_converged(r_rms,r_max,b_rms,b_max,cfg)) THEN
        CALL refresh_true_residual(op,b,lambda,r,lr,work_u,work_v,work_o, &
                                   r_rms,r_max,operator_status)
        IF (operator_status/=STATUS_OK) RETURN
        final_rms=r_rms; final_max=r_max
        IF (solver_residual_converged(r_rms,r_max,b_rms,b_max,cfg)) THEN
          status=STATUS_OK; failure_reason=SOLVER_CONVERGED; RETURN
        END IF
        p=r
        CALL apply_normal_operator_work(op,p,lp,work_u,work_v,work_o,operator_status)
        IF (operator_status/=STATUS_OK) RETURN
        CYCLE
      END IF
      IF (MOD(iterations,cfg%residual_refresh_interval)==0) THEN
        CALL refresh_true_residual(op,b,lambda,r,lr,work_u,work_v,work_o, &
                                   r_rms,r_max,operator_status)
        IF (operator_status/=STATUS_OK) RETURN
        final_rms=r_rms; final_max=r_max
        IF (solver_residual_converged(r_rms,r_max,b_rms,b_max,cfg)) THEN
          status=STATUS_OK; failure_reason=SOLVER_CONVERGED; RETURN
        END IF
        p=r
        CALL apply_normal_operator_work(op,p,lp,work_u,work_v,work_o,operator_status)
        IF (operator_status/=STATUS_OK) RETURN
        CYCLE
      END IF
      CALL apply_normal_operator_work(op,r,lr,work_u,work_v,work_o,operator_status)
      IF (operator_status/=STATUS_OK) RETURN
      beta=weighted_dot(op,lr,lp)/denom
      IF (.NOT.ieee_is_finite(beta)) RETURN
      p=r-beta*p
      lp=lr-beta*lp
      CALL remove_component_means(op,p)
    END DO
    iterations=cfg%maximum_iterations
    CALL refresh_true_residual(op,b,lambda,r,lr,work_u,work_v,work_o, &
                               final_rms,final_max,operator_status)
    IF (operator_status/=STATUS_OK) RETURN
    IF (solver_residual_converged(final_rms,final_max,b_rms,b_max,cfg)) THEN
      status=STATUS_OK; failure_reason=SOLVER_CONVERGED
    ELSE
      failure_reason=SOLVER_ITERATION_LIMIT
    END IF
  END SUBROUTINE solve_normal_equation

  SUBROUTINE refresh_true_residual(op,b,lambda,residual,l_lambda,work_u,work_v, &
                                   work_o,rms_value,max_value,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: b(:,:,:),lambda(:,:,:)
    REAL(real64), INTENT(OUT) :: residual(:,:,:),l_lambda(:,:,:)
    REAL(real64), INTENT(INOUT) :: work_u(:,:,:),work_v(:,:,:),work_o(:,:,:)
    REAL(real64), INTENT(OUT) :: rms_value,max_value
    INTEGER, INTENT(OUT) :: status

    CALL apply_normal_operator_work(op,lambda,l_lambda,work_u,work_v,work_o,status)
    IF (status/=STATUS_OK) RETURN
    residual=b-l_lambda
    CALL continuity_norms(op,residual,rms_value,max_value)
    CALL remove_component_means(op,residual)
  END SUBROUTINE refresh_true_residual

  PURE LOGICAL FUNCTION solver_residual_converged(rms_value,max_value, &
                                                   initial_rms,initial_max,cfg)
    REAL(real64), INTENT(IN) :: rms_value,max_value,initial_rms,initial_max
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    solver_residual_converged= &
      rms_value<=MAX(cfg%solver_residual_fraction*initial_rms, &
                     cfg%solver_absolute_tolerance) .AND. &
      max_value<=MAX(cfg%solver_residual_fraction*initial_max, &
                     cfg%solver_absolute_tolerance)
  END FUNCTION solver_residual_converged

  SUBROUTINE continuity_norms(op,residual,rms_value,max_value)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: residual(:,:,:)
    REAL(real64), INTENT(OUT) :: rms_value,max_value
    INTEGER :: i,j,k,count_active
    REAL(real64) :: sum_squares,value,term,limit
    rms_value=HUGE(1.0_real64); max_value=HUGE(1.0_real64)
    IF (.NOT.diagnostic_operator_shapes_valid(op)) RETURN
    IF (ANY(SHAPE(residual)/=(/op%nx,op%ny,op%nz/))) RETURN
    count_active=0
    sum_squares=0.0_real64
    max_value=0.0_real64
    limit=SQRT(HUGE(1.0_real64)/2.0_real64)
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.op%cell_active(i,j,k)) CYCLE
      value=ABS(residual(i,j,k))
      IF (.NOT.ieee_is_finite(value) .OR. value>limit) THEN
        rms_value=HUGE(1.0_real64); max_value=HUGE(1.0_real64); RETURN
      END IF
      term=value*value
      IF (term>HUGE(1.0_real64)-sum_squares) THEN
        rms_value=HUGE(1.0_real64); max_value=HUGE(1.0_real64); RETURN
      END IF
      count_active=count_active+1
      sum_squares=sum_squares+term
      max_value=MAX(max_value,value)
    END DO; END DO; END DO
    IF (count_active<=0) THEN
      rms_value=0.0_real64; max_value=0.0_real64; RETURN
    END IF
    ! Acceptance diagnostics are physical, unweighted norms.  The volume
    ! metric remains private to the adjoint, compatibility and CG products.
    rms_value=SQRT(MAX(0.0_real64,sum_squares/REAL(count_active,real64)))
  END SUBROUTINE continuity_norms

  SUBROUTINE state_continuity_residual(op,state,residual,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    REAL(real64), INTENT(OUT) :: residual(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,k_top,k_bottom
    REAL(real64) :: area,flux

    residual=0.0_real64; status=STATUS_FAILED
    IF (.NOT.diagnostic_operator_shapes_valid(op)) RETURN
    IF (ANY(SHAPE(residual)/=(/op%nx,op%ny,op%nz/))) RETURN
    IF (.NOT.field_storage_shape_valid(state%u,op%nx,op%ny,op%nz) .OR. &
        .NOT.field_storage_shape_valid(state%v,op%nx,op%ny,op%nz) .OR. &
        .NOT.field_storage_shape_valid(state%omega,op%nx,op%ny,op%nz)) RETURN
    IF (.NOT.boundary_contract_valid(state)) RETURN
    IF (ANY(op%cell_usable .AND. (.NOT.ieee_is_finite(state%u%value) .OR. &
        .NOT.ieee_is_finite(state%v%value) .OR. &
        .NOT.ieee_is_finite(state%omega%value)))) RETURN
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx-1
      IF (.NOT.(op%cell_usable(i,j,k) .AND. op%cell_usable(i+1,j,k))) CYCLE
      flux=op%xface_area(i,j,k)*(op%xleft_weight(i,j,k)* &
        REAL(state%u%value(i,j,k),real64)+op%xright_weight(i,j,k)* &
        REAL(state%u%value(i+1,j,k),real64))
      IF (op%cell_active(i,j,k)) &
        residual(i,j,k)=residual(i,j,k)+flux/op%volume(i,j,k)
      IF (op%cell_active(i+1,j,k)) &
        residual(i+1,j,k)=residual(i+1,j,k)-flux/op%volume(i+1,j,k)
    END DO; END DO; END DO
    DO k=1,op%nz; DO j=1,op%ny-1; DO i=1,op%nx
      IF (.NOT.(op%cell_usable(i,j,k) .AND. op%cell_usable(i,j+1,k))) CYCLE
      flux=op%yface_area(i,j,k)*(op%yleft_weight(i,j,k)* &
        REAL(state%v%value(i,j,k),real64)+op%yright_weight(i,j,k)* &
        REAL(state%v%value(i,j+1,k),real64))
      IF (op%cell_active(i,j,k)) &
        residual(i,j,k)=residual(i,j,k)+flux/op%volume(i,j,k)
      IF (op%cell_active(i,j+1,k)) &
        residual(i,j+1,k)=residual(i,j+1,k)-flux/op%volume(i,j+1,k)
    END DO; END DO; END DO
    DO k=1,op%nz-1; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.(op%cell_usable(i,j,k) .AND. op%cell_usable(i,j,k+1))) CYCLE
      flux=op%pface_area(i,j,k)*(op%pleft_weight(i,j,k)* &
        REAL(state%omega%value(i,j,k),real64)+op%pright_weight(i,j,k)* &
        REAL(state%omega%value(i,j,k+1),real64))
      IF (op%cell_active(i,j,k+1)) &
        residual(i,j,k+1)=residual(i,j,k+1)+flux/op%volume(i,j,k+1)
      IF (op%cell_active(i,j,k)) &
        residual(i,j,k)=residual(i,j,k)-flux/op%volume(i,j,k)
    END DO; END DO; END DO
    ! Zero-gradient lateral boundary flux makes a uniform through-flow exactly
    ! divergence free.  Support-edge faces above use the immutable full state.
    DO k=1,op%nz; DO j=1,op%ny
      IF (op%cell_active(1,j,k)) THEN
        area=op%dy(1,j)*op%dp(1,j,k)/GRAVITY
        residual(1,j,k)=residual(1,j,k)-area* &
          REAL(state%u%value(1,j,k),real64)/op%volume(1,j,k)
      END IF
      IF (op%cell_active(op%nx,j,k)) THEN
        area=op%dy(op%nx,j)*op%dp(op%nx,j,k)/GRAVITY
        residual(op%nx,j,k)=residual(op%nx,j,k)+area* &
          REAL(state%u%value(op%nx,j,k),real64)/op%volume(op%nx,j,k)
      END IF
    END DO; END DO
    DO k=1,op%nz; DO i=1,op%nx
      IF (op%cell_active(i,1,k)) THEN
        area=op%dx(i,1)*op%dp(i,1,k)/GRAVITY
        residual(i,1,k)=residual(i,1,k)-area* &
          REAL(state%v%value(i,1,k),real64)/op%volume(i,1,k)
      END IF
      IF (op%cell_active(i,op%ny,k)) THEN
        area=op%dx(i,op%ny)*op%dp(i,op%ny,k)/GRAVITY
        residual(i,op%ny,k)=residual(i,op%ny,k)+area* &
          REAL(state%v%value(i,op%ny,k),real64)/op%volume(i,op%ny,k)
      END IF
    END DO; END DO
    DO j=1,op%ny; DO i=1,op%nx
      k_bottom=0; k_top=0
      DO k=1,op%nz
        IF (.NOT.op%cell_usable(i,j,k)) CYCLE
        IF (k_bottom==0) k_bottom=k
        k_top=k
      END DO
      IF (k_bottom==0) CYCLE
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
    WHERE(.NOT.op%cell_active) residual=0.0_real64
    IF (ANY(op%cell_active .AND. .NOT.ieee_is_finite(residual))) RETURN
    status=STATUS_OK
  END SUBROUTINE state_continuity_residual

  SUBROUTINE geostrophic_residual(state,op,rms_value,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(OUT) :: rms_value
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,ix,jy,n,validation_status,reason
    REAL(real64) :: f,dphidx,dphidy,ru,rv,total,pi,term,limit
    status=STATUS_FAILED; rms_value=0.0_real64; total=0.0_real64; n=0
    IF (.NOT.diagnostic_operator_shapes_valid(op)) RETURN
    IF (.NOT.field_storage_shape_valid(state%u,op%nx,op%ny,op%nz) .OR. &
        .NOT.field_storage_shape_valid(state%v,op%nx,op%ny,op%nz)) RETURN
    CALL validate_geostrophic_inputs(state,validation_status,reason)
    IF (validation_status/=STATUS_OK) RETURN
    pi=ACOS(-1.0_real64)
    limit=SQRT(HUGE(1.0_real64)/4.0_real64)
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.op%cell_active(i,j,k)) CYCLE
      ix=0
      IF (i<op%nx) THEN
        IF (op%cell_usable(i+1,j,k)) ix=i+1
      END IF
      IF (ix==0 .AND. i>1) THEN
        IF (op%cell_usable(i-1,j,k)) ix=i-1
      END IF
      IF (ix==0) RETURN
      jy=0
      IF (j<op%ny) THEN
        IF (op%cell_usable(i,j+1,k)) jy=j+1
      END IF
      IF (jy==0 .AND. j>1) THEN
        IF (op%cell_usable(i,j-1,k)) jy=j-1
      END IF
      IF (jy==0) RETURN
      IF (.NOT.(cell_is_usable(state%geopotential%valid(i,j,k), &
                state%geopotential%quality(i,j,k),state%geopotential%source(i,j,k)) .AND. &
                cell_is_usable(state%geopotential%valid(ix,j,k), &
                state%geopotential%quality(ix,j,k),state%geopotential%source(ix,j,k)) .AND. &
                cell_is_usable(state%geopotential%valid(i,jy,k), &
                state%geopotential%quality(i,jy,k),state%geopotential%source(i,jy,k)) .AND. &
                cell_is_usable(state%latitude%valid(i,j),state%latitude%quality(i,j), &
                state%latitude%source(i,j)))) RETURN
      f=1.458423e-4_real64*SIN(REAL(state%latitude%value(i,j),real64)*pi/180.0_real64)
      dphidx=(REAL(state%geopotential%value(ix,j,k),real64)- &
              REAL(state%geopotential%value(i,j,k),real64))/ &
             (REAL(ix-i,real64)*0.5_real64*(op%dx(i,j)+op%dx(ix,j)))
      dphidy=(REAL(state%geopotential%value(i,jy,k),real64)- &
              REAL(state%geopotential%value(i,j,k),real64))/ &
             (REAL(jy-j,real64)*0.5_real64*(op%dy(i,j)+op%dy(i,jy)))
      ru=-f*REAL(state%v%value(i,j,k),real64)+dphidx
      rv= f*REAL(state%u%value(i,j,k),real64)+dphidy
      IF (.NOT.ieee_is_finite(ru) .OR. .NOT.ieee_is_finite(rv)) RETURN
      IF (ABS(ru)>limit .OR. ABS(rv)>limit) RETURN
      term=ru*ru+rv*rv
      IF (.NOT.ieee_is_finite(term) .OR. term>HUGE(1.0_real64)-total) RETURN
      total=total+term; n=n+2
    END DO; END DO; END DO
    IF (n==0) RETURN
    rms_value=SQRT(total/REAL(n,real64))
    IF (.NOT.ieee_is_finite(rms_value)) RETURN
    status=STATUS_OK
  END SUBROUTINE geostrophic_residual

  SUBROUTINE validate_geostrophic_inputs(state,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: nx,ny,nz
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    status=STATUS_FAILED; reason=REASON_SHAPE
    IF (.NOT.ALLOCATED(state%geopotential%value) .OR. &
        .NOT.ALLOCATED(state%geopotential%valid) .OR. &
        .NOT.ALLOCATED(state%geopotential%quality) .OR. &
        .NOT.ALLOCATED(state%geopotential%source) .OR. &
        .NOT.ALLOCATED(state%latitude%value) .OR. &
        .NOT.ALLOCATED(state%latitude%valid) .OR. &
        .NOT.ALLOCATED(state%latitude%quality) .OR. &
        .NOT.ALLOCATED(state%latitude%source)) RETURN
    IF (ANY(SHAPE(state%geopotential%value)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%geopotential%valid)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%geopotential%quality)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%geopotential%source)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%latitude%value)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(state%latitude%valid)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(state%latitude%quality)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(state%latitude%source)/=(/nx,ny/))) RETURN
    IF (TRIM(state%geopotential%unit)/='m2 s-2' .OR. &
        TRIM(state%latitude%unit)/='degree_north' .OR. &
        state%geopotential%valid_time/=state%pressure%valid_time .OR. &
        state%latitude%valid_time/=state%pressure%valid_time) THEN
      reason=REASON_METADATA; RETURN
    END IF
    IF (COUNT(cell_is_usable(state%geopotential%valid,state%geopotential%quality, &
        state%geopotential%source))==0 .OR. &
        COUNT(cell_is_usable(state%latitude%valid,state%latitude%quality, &
        state%latitude%source))==0) THEN
      reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    IF (ANY(state%geopotential%valid .AND. .NOT.cell_is_usable( &
        state%geopotential%valid,state%geopotential%quality,state%geopotential%source)) .OR. &
        ANY(state%latitude%valid .AND. .NOT.cell_is_usable(state%latitude%valid, &
        state%latitude%quality,state%latitude%source))) THEN
      reason=REASON_METADATA; RETURN
    END IF
    IF (ANY(state%geopotential%valid .AND. &
            .NOT.ieee_is_finite(state%geopotential%value)) .OR. &
        ANY(state%latitude%valid .AND. &
            (.NOT.ieee_is_finite(state%latitude%value) .OR. &
             ABS(state%latitude%value)>90.0_real32))) THEN
      reason=REASON_NONFINITE; RETURN
    END IF
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE validate_geostrophic_inputs

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

  SUBROUTINE evaluate_los_gate(input,candidate,result,cfg,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,candidate
    TYPE(stage_result), INTENT(INOUT) :: result
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,r,nheld,ndeclared,nradar_held
    REAL(real64) :: predicted_in,predicted_out,res_in,res_out,weight
    REAL(real64) :: sum_in,sum_out,sum_weight,vt,sigma_vt,beam_vertical,sigma2
    REAL(real32), ALLOCATABLE :: win(:,:,:),wout(:,:,:)
    LOGICAL, ALLOCATABLE :: valid_in(:,:,:),valid_out(:,:,:)
    LOGICAL, ALLOCATABLE :: radar_seen(:)
    INTEGER :: conversion_status

    status=STATUS_OK
    IF (.NOT.input%radar_los%is_present) RETURN
    ndeclared=COUNT(input%radar_los%usage==LOS_HELD_OUT .AND. &
                    input%radar_los%los_support==1_int32)
    IF (ndeclared==0) RETURN
    ALLOCATE(win(input%grid%nx,input%grid%ny,input%grid%nz), &
             wout(input%grid%nx,input%grid%ny,input%grid%nz), &
             valid_in(input%grid%nx,input%grid%ny,input%grid%nz), &
             valid_out(input%grid%nx,input%grid%ny,input%grid%nz), &
             radar_seen(input%radar_los%nradar))
    radar_seen=.FALSE.
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
            .NOT.cell_is_usable(input%radar_los%vrad%valid(i,j,k,r), &
              input%radar_los%vrad%quality(i,j,k,r), &
              input%radar_los%vrad%source(i,j,k,r)) .OR. &
            .NOT.cell_is_usable(input%radar_los%nyquist%valid(i,j,k,r), &
              input%radar_los%nyquist%quality(i,j,k,r), &
              input%radar_los%nyquist%source(i,j,k,r)) .OR. &
            .NOT.cell_is_usable(input%radar_los%sigma_vrad%valid(i,j,k,r), &
              input%radar_los%sigma_vrad%quality(i,j,k,r), &
              input%radar_los%sigma_vrad%source(i,j,k,r)) .OR. &
            .NOT.cell_is_usable(input%vt_z_mean%valid(i,j,k), &
              input%vt_z_mean%quality(i,j,k),input%vt_z_mean%source(i,j,k)) .OR. &
            .NOT.cell_is_usable(input%vt_z_sigma%valid(i,j,k), &
              input%vt_z_sigma%quality(i,j,k),input%vt_z_sigma%source(i,j,k)) .OR. &
            IAND(input%vt_z_mean%quality(i,j,k), &
              IOR(QUALITY_FALL_SPEED_UNCERTAIN, &
                IOR(QUALITY_PHASE_UNCERTAIN,QUALITY_BRIGHT_BAND_OR_MIXED)))/=0 .OR. &
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
        sum_weight=sum_weight+weight; nheld=nheld+1; radar_seen(r)=.TRUE.
      END DO; END DO
    END DO; END DO
    result%coverage%los_held_out=nheld
    result%los_gate_applied=.TRUE.
    nradar_held=COUNT(radar_seen)
    IF (nheld<cfg%minimum_held_out_samples .OR. &
        nradar_held<cfg%minimum_held_out_radars) THEN
      result%los_gate_passed=.FALSE.
      status=STATUS_DEGRADED
      RETURN
    END IF
    result%los_rms_input=SQRT(sum_in/sum_weight)
    result%los_rms_candidate=SQRT(sum_out/sum_weight)
    result%los_threshold=result%los_rms_input+0.10_real64
    result%los_gate_passed=result%los_rms_candidate<=result%los_threshold
    IF (.NOT.result%los_gate_passed) status=STATUS_DEGRADED
  END SUBROUTINE evaluate_los_gate

  SUBROUTINE label_components(op)
    TYPE(balance_operator_type), INTENT(INOUT) :: op
    INTEGER, ALLOCATABLE :: parent(:),rank(:),root_label(:)
    INTEGER :: nodes(3),i,j,k,n,total,root,label
    REAL(real64) :: coefficient(3),center

    total=op%nx*op%ny*op%nz
    ALLOCATE(parent(total),rank(total),root_label(total))
    parent=0; rank=0; root_label=0
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (op%cell_active(i,j,k)) THEN
        root=linear_index(op,i,j,k)
        parent(root)=root
      END IF
    END DO; END DO; END DO

    ! Two residual cells are connected only when an actual A-grid degree of
    ! freedom has a nonzero coefficient in both rows of L=A*K*A^T*M.
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (op%ku(i,j,k)>0.0_real64) THEN
        n=0; center=0.0_real64
        IF (i>1) THEN
          IF (op%xface_active(i-1,j,k)) THEN
            CALL add_node(nodes,coefficient,n,linear_index(op,i-1,j,k), &
              op%xface_area(i-1,j,k)*op%xright_weight(i-1,j,k)/ &
              op%volume(i-1,j,k))
            center=center-op%xface_area(i-1,j,k)*op%xright_weight(i-1,j,k)/ &
                          op%volume(i,j,k)
          END IF
        END IF
        IF (i<op%nx) THEN
          IF (op%xface_active(i,j,k)) THEN
            center=center+op%xface_area(i,j,k)*op%xleft_weight(i,j,k)/ &
                          op%volume(i,j,k)
            CALL add_node(nodes,coefficient,n,linear_index(op,i+1,j,k), &
              -op%xface_area(i,j,k)*op%xleft_weight(i,j,k)/op%volume(i+1,j,k))
          END IF
        END IF
        CALL add_node(nodes,coefficient,n,linear_index(op,i,j,k),center)
        CALL connect_stencil(parent,rank,nodes,coefficient,n)
      END IF

      IF (op%kv(i,j,k)>0.0_real64) THEN
        n=0; center=0.0_real64
        IF (j>1) THEN
          IF (op%yface_active(i,j-1,k)) THEN
            CALL add_node(nodes,coefficient,n,linear_index(op,i,j-1,k), &
              op%yface_area(i,j-1,k)*op%yright_weight(i,j-1,k)/ &
              op%volume(i,j-1,k))
            center=center-op%yface_area(i,j-1,k)*op%yright_weight(i,j-1,k)/ &
                          op%volume(i,j,k)
          END IF
        END IF
        IF (j<op%ny) THEN
          IF (op%yface_active(i,j,k)) THEN
            center=center+op%yface_area(i,j,k)*op%yleft_weight(i,j,k)/ &
                          op%volume(i,j,k)
            CALL add_node(nodes,coefficient,n,linear_index(op,i,j+1,k), &
              -op%yface_area(i,j,k)*op%yleft_weight(i,j,k)/op%volume(i,j+1,k))
          END IF
        END IF
        CALL add_node(nodes,coefficient,n,linear_index(op,i,j,k),center)
        CALL connect_stencil(parent,rank,nodes,coefficient,n)
      END IF

      IF (op%ko(i,j,k)>0.0_real64) THEN
        n=0; center=0.0_real64
        IF (k>1) THEN
          IF (op%pface_active(i,j,k-1)) THEN
            CALL add_node(nodes,coefficient,n,linear_index(op,i,j,k-1), &
              -op%pface_area(i,j,k-1)*op%pright_weight(i,j,k-1)/ &
              op%volume(i,j,k-1))
            center=center+op%pface_area(i,j,k-1)*op%pright_weight(i,j,k-1)/ &
                          op%volume(i,j,k)
          END IF
        END IF
        IF (k<op%nz) THEN
          IF (op%pface_active(i,j,k)) THEN
            center=center-op%pface_area(i,j,k)*op%pleft_weight(i,j,k)/ &
                          op%volume(i,j,k)
            CALL add_node(nodes,coefficient,n,linear_index(op,i,j,k+1), &
              op%pface_area(i,j,k)*op%pleft_weight(i,j,k)/op%volume(i,j,k+1))
          END IF
        END IF
        CALL add_node(nodes,coefficient,n,linear_index(op,i,j,k),center)
        CALL connect_stencil(parent,rank,nodes,coefficient,n)
      END IF
    END DO; END DO; END DO

    op%component=0; label=0
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.op%cell_active(i,j,k)) CYCLE
      CALL find_root(parent,linear_index(op,i,j,k),root)
      IF (root_label(root)==0) THEN
        label=label+1
        root_label(root)=label
      END IF
      op%component(i,j,k)=root_label(root)
    END DO; END DO; END DO
    op%ncomponent=label
  END SUBROUTINE label_components

  PURE INTEGER FUNCTION linear_index(op,i,j,k)
    TYPE(balance_operator_type), INTENT(IN) :: op
    INTEGER, INTENT(IN) :: i,j,k
    linear_index=i+op%nx*((j-1)+op%ny*(k-1))
  END FUNCTION linear_index

  SUBROUTINE add_node(nodes,coefficient,n,node,value)
    INTEGER, INTENT(INOUT) :: nodes(3),n
    REAL(real64), INTENT(INOUT) :: coefficient(3)
    INTEGER, INTENT(IN) :: node
    REAL(real64), INTENT(IN) :: value
    IF (value==0.0_real64) RETURN
    n=n+1
    nodes(n)=node
    coefficient(n)=value
  END SUBROUTINE add_node

  SUBROUTINE connect_stencil(parent,rank,nodes,coefficient,n)
    INTEGER, INTENT(INOUT) :: parent(:),rank(:)
    INTEGER, INTENT(IN) :: nodes(3),n
    REAL(real64), INTENT(IN) :: coefficient(3)
    INTEGER :: first,m
    first=0
    DO m=1,n
      IF (coefficient(m)==0.0_real64) CYCLE
      IF (first==0) THEN
        first=nodes(m)
      ELSE
        CALL union_nodes(parent,rank,first,nodes(m))
      END IF
    END DO
  END SUBROUTINE connect_stencil

  SUBROUTINE union_nodes(parent,rank,left,right)
    INTEGER, INTENT(INOUT) :: parent(:),rank(:)
    INTEGER, INTENT(IN) :: left,right
    INTEGER :: left_root,right_root
    CALL find_root(parent,left,left_root)
    CALL find_root(parent,right,right_root)
    IF (left_root==right_root) RETURN
    IF (rank(left_root)<rank(right_root)) THEN
      parent(left_root)=right_root
    ELSE
      parent(right_root)=left_root
      IF (rank(left_root)==rank(right_root)) rank(left_root)=rank(left_root)+1
    END IF
  END SUBROUTINE union_nodes

  SUBROUTINE find_root(parent,node,root)
    INTEGER, INTENT(INOUT) :: parent(:)
    INTEGER, INTENT(IN) :: node
    INTEGER, INTENT(OUT) :: root
    INTEGER :: current,next
    root=node
    DO WHILE(parent(root)/=root)
      root=parent(root)
    END DO
    current=node
    DO WHILE(parent(current)/=current)
      next=parent(current)
      parent(current)=root
      current=next
    END DO
  END SUBROUTINE find_root

  LOGICAL FUNCTION compatibility_ok(op,b,cfg)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: b(:,:,:)
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    INTEGER :: component,i,j,k
    REAL(real64), ALLOCATABLE :: total(:),scale(:)
    compatibility_ok=.FALSE.
    ALLOCATE(total(op%ncomponent),scale(op%ncomponent))
    total=0.0_real64
    scale=0.0_real64
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      component=op%component(i,j,k)
      IF (component<=0) CYCLE
      total(component)=total(component)+op%volume(i,j,k)*b(i,j,k)
      scale(component)=scale(component)+op%volume(i,j,k)*ABS(b(i,j,k))
    END DO; END DO; END DO
    DO component=1,op%ncomponent
      IF (ABS(total(component))>cfg%compatibility_absolute_tolerance+ &
          cfg%compatibility_relative_tolerance*scale(component)) RETURN
    END DO
    compatibility_ok=.TRUE.
  END FUNCTION compatibility_ok

  SUBROUTINE remove_component_means(op,array)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(INOUT) :: array(:,:,:)
    INTEGER :: component,i,j,k
    REAL(real64), ALLOCATABLE :: measure(:),mean_value(:)
    ALLOCATE(measure(op%ncomponent),mean_value(op%ncomponent))
    measure=0.0_real64
    mean_value=0.0_real64
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      component=op%component(i,j,k)
      IF (component<=0) CYCLE
      measure(component)=measure(component)+op%volume(i,j,k)
      mean_value(component)=mean_value(component)+op%volume(i,j,k)*array(i,j,k)
    END DO; END DO; END DO
    DO component=1,op%ncomponent
      IF (measure(component)>0.0_real64) &
        mean_value(component)=mean_value(component)/measure(component)
    END DO
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      component=op%component(i,j,k)
      IF (component>0) THEN
        array(i,j,k)=array(i,j,k)-mean_value(component)
      ELSE
        array(i,j,k)=0.0_real64
      END IF
    END DO; END DO; END DO
  END SUBROUTINE remove_component_means

  PURE REAL(real64) FUNCTION weighted_dot(op,a,b)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: a(:,:,:),b(:,:,:)
    INTEGER :: i,j,k
    weighted_dot=0.0_real64
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (op%cell_active(i,j,k)) &
        weighted_dot=weighted_dot+op%volume(i,j,k)*a(i,j,k)*b(i,j,k)
    END DO; END DO; END DO
  END FUNCTION weighted_dot

  PURE LOGICAL FUNCTION outside_support_zero(op,du,dv,domega)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: du(:,:,:),dv(:,:,:),domega(:,:,:)
    INTEGER :: i,j,k
    outside_support_zero=.FALSE.
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (op%cell_active(i,j,k)) CYCLE
      IF (du(i,j,k)/=0.0_real64 .OR. dv(i,j,k)/=0.0_real64 .OR. &
          domega(i,j,k)/=0.0_real64) RETURN
    END DO; END DO; END DO
    outside_support_zero=.TRUE.
  END FUNCTION outside_support_zero

  PURE REAL(real64) FUNCTION target_response_failure_fraction( &
      op,increment,target,floor_value,minimum_ratio,maximum_ratio)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: increment(:,:,:),target(:,:,:),floor_value
    REAL(real64), INTENT(IN) :: minimum_ratio,maximum_ratio
    INTEGER :: i,j,k,n,failed
    REAL(real64) :: ratio,tolerance
    target_response_failure_fraction=1.0_real64
    IF (ANY(SHAPE(increment)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(target)/=(/op%nx,op%ny,op%nz/))) RETURN
    n=0; failed=0
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.op%cell_active(i,j,k) .OR. ABS(target(i,j,k))<=floor_value) CYCLE
      n=n+1
      ratio=increment(i,j,k)/target(i,j,k)
      tolerance=64.0_real64*REAL(EPSILON(1.0_real32),real64)* &
                MAX(1.0_real64,ABS(ratio),ABS(minimum_ratio),ABS(maximum_ratio))
      IF (ratio<minimum_ratio-tolerance .OR. ratio>maximum_ratio+tolerance) &
        failed=failed+1
    END DO; END DO; END DO
    target_response_failure_fraction=0.0_real64
    IF (n>0) target_response_failure_fraction=REAL(failed,real64)/REAL(n,real64)
  END FUNCTION target_response_failure_fraction

  PURE LOGICAL FUNCTION omega_target_is_observable( &
      op,target,tolerance,minimum_face_response)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: target(:,:,:),tolerance,minimum_face_response
    INTEGER :: i,j,k
    REAL(real64) :: face_value,face_energy,target_energy
    LOGICAL :: connected,has_target

    omega_target_is_observable=.FALSE.; has_target=.FALSE.
    IF (ANY(SHAPE(target)/=(/op%nx,op%ny,op%nz/))) RETURN
    IF (ANY(.NOT.ieee_is_finite(target)) .OR. &
        .NOT.ieee_is_finite(minimum_face_response) .OR. &
        minimum_face_response<0.0_real64) RETURN
    IF (ANY(ABS(target)>tolerance .AND. .NOT.op%omega_authorized)) RETURN

    DO j=1,op%ny; DO i=1,op%nx
      target_energy=SUM(target(i,j,:)*target(i,j,:))
      IF (target_energy<=tolerance*tolerance) CYCLE
      has_target=.TRUE.; face_energy=0.0_real64
      DO k=1,op%nz
        IF (ABS(target(i,j,k))<=tolerance) CYCLE
        connected=.FALSE.
        IF (k>1) connected=op%pface_active(i,j,k-1)
        IF (k<op%nz) connected=connected .OR. op%pface_active(i,j,k)
        IF (.NOT.connected) RETURN
      END DO
      DO k=1,op%nz-1
        IF (.NOT.op%pface_active(i,j,k)) CYCLE
        face_value=op%pleft_weight(i,j,k)*target(i,j,k)+ &
                   op%pright_weight(i,j,k)*target(i,j,k+1)
        face_energy=face_energy+face_value*face_value
      END DO
      IF (SQRT(face_energy/target_energy)< &
          MAX(minimum_face_response,FACE_RESPONSE_ROUNDOFF)) RETURN
    END DO; END DO
    omega_target_is_observable=has_target
  END FUNCTION omega_target_is_observable

  PURE LOGICAL FUNCTION operator_input_shapes_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: nx,ny,nz
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    operator_input_shapes_valid=.FALSE.
    IF (.NOT.ALLOCATED(state%grid%dx) .OR. .NOT.ALLOCATED(state%grid%dy) .OR. &
        .NOT.ALLOCATED(state%grid%dp) .OR. &
        .NOT.ALLOCATED(state%grid%pressure_mass_measure) .OR. &
        .NOT.ALLOCATED(state%above_ground) .OR. &
        .NOT.ALLOCATED(state%balance_beta)) RETURN
    IF (ANY(SHAPE(state%grid%dx)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(state%grid%dy)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(state%grid%dp)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%grid%pressure_mass_measure)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%above_ground)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%balance_beta)/=(/nx,ny,nz/))) RETURN
    IF (.NOT.field_storage_shape_valid(state%pressure,nx,ny,nz)) RETURN
    IF (.NOT.field_storage_shape_valid(state%u,nx,ny,nz)) RETURN
    IF (.NOT.field_storage_shape_valid(state%v,nx,ny,nz)) RETURN
    IF (.NOT.field_storage_shape_valid(state%omega,nx,ny,nz)) RETURN
    IF (.NOT.field_storage_shape_valid(state%omega_target,nx,ny,nz)) RETURN
    operator_input_shapes_valid=.TRUE.
  END FUNCTION operator_input_shapes_valid

  PURE LOGICAL FUNCTION diagnostic_operator_shapes_valid(op)
    TYPE(balance_operator_type), INTENT(IN) :: op
    diagnostic_operator_shapes_valid=.FALSE.
    IF (op%nx<2 .OR. op%ny<2 .OR. op%nz<2) RETURN
    IF (.NOT.ALLOCATED(op%volume) .OR. .NOT.ALLOCATED(op%dx) .OR. &
        .NOT.ALLOCATED(op%dy) .OR. .NOT.ALLOCATED(op%dp) .OR. &
        .NOT.ALLOCATED(op%cell_usable) .OR. .NOT.ALLOCATED(op%cell_active) .OR. &
        .NOT.ALLOCATED(op%xface_area) .OR. .NOT.ALLOCATED(op%xleft_weight) .OR. &
        .NOT.ALLOCATED(op%xright_weight) .OR. .NOT.ALLOCATED(op%yface_area) .OR. &
        .NOT.ALLOCATED(op%yleft_weight) .OR. .NOT.ALLOCATED(op%yright_weight) .OR. &
        .NOT.ALLOCATED(op%pface_area) .OR. .NOT.ALLOCATED(op%pleft_weight) .OR. &
        .NOT.ALLOCATED(op%pright_weight)) RETURN
    IF (ANY(SHAPE(op%volume)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%dx)/=(/op%nx,op%ny/)) .OR. &
        ANY(SHAPE(op%dy)/=(/op%nx,op%ny/)) .OR. &
        ANY(SHAPE(op%dp)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%cell_usable)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%cell_active)/=(/op%nx,op%ny,op%nz/))) RETURN
    IF (ANY(SHAPE(op%xface_area)/=(/op%nx-1,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%xleft_weight)/=(/op%nx-1,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%xright_weight)/=(/op%nx-1,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%yface_area)/=(/op%nx,op%ny-1,op%nz/)) .OR. &
        ANY(SHAPE(op%yleft_weight)/=(/op%nx,op%ny-1,op%nz/)) .OR. &
        ANY(SHAPE(op%yright_weight)/=(/op%nx,op%ny-1,op%nz/))) RETURN
    IF (ANY(SHAPE(op%pface_area)/=(/op%nx,op%ny,op%nz-1/)) .OR. &
        ANY(SHAPE(op%pleft_weight)/=(/op%nx,op%ny,op%nz-1/)) .OR. &
        ANY(SHAPE(op%pright_weight)/=(/op%nx,op%ny,op%nz-1/))) RETURN
    diagnostic_operator_shapes_valid=.TRUE.
  END FUNCTION diagnostic_operator_shapes_valid

  PURE LOGICAL FUNCTION field_storage_shape_valid(field,nx,ny,nz)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER :: expected(3)
    field_storage_shape_valid=.FALSE.; expected=(/nx,ny,nz/)
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) RETURN
    field_storage_shape_valid=ALL(SHAPE(field%value)==expected) .AND. &
      ALL(SHAPE(field%valid)==expected) .AND. &
      ALL(SHAPE(field%quality)==expected) .AND. ALL(SHAPE(field%source)==expected)
  END FUNCTION field_storage_shape_valid

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
      ALL(cell_is_usable(state%omega_top_boundary%valid, &
        state%omega_top_boundary%quality,state%omega_top_boundary%source)) .AND. &
      ALL(cell_is_usable(state%omega_bottom_boundary%valid, &
        state%omega_bottom_boundary%quality,state%omega_bottom_boundary%source)) .AND. &
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
      ieee_is_finite(config%solver_residual_fraction) .AND. &
      config%solver_residual_fraction>0.0_real64 .AND. &
      config%solver_residual_fraction<config%required_residual_fraction .AND. &
      ieee_is_finite(config%solver_absolute_tolerance) .AND. &
      config%solver_absolute_tolerance>0.0_real64 .AND. &
      ieee_is_finite(config%compatibility_relative_tolerance) .AND. &
      config%compatibility_relative_tolerance>=0.0_real64 .AND. &
      ieee_is_finite(config%compatibility_absolute_tolerance) .AND. &
      config%compatibility_absolute_tolerance>=0.0_real64 .AND. &
      config%maximum_iterations>0 .AND. &
      config%residual_refresh_interval>0 .AND. &
      config%required_residual_fraction>0.0_real64 .AND. &
      config%required_residual_fraction<1.0_real64 .AND. &
      ieee_is_finite(config%physical_residual_tolerance) .AND. &
      config%physical_residual_tolerance>=0.0_real64 .AND. &
      ieee_is_finite(config%maximum_physical_residual) .AND. &
      config%maximum_physical_residual>0.0_real64 .AND. &
      ieee_is_finite(config%maximum_wind_increment) .AND. &
      config%maximum_wind_increment>0.0_real64 .AND. &
      ieee_is_finite(config%maximum_omega_increment) .AND. &
      config%maximum_omega_increment>0.0_real64 .AND. &
      ieee_is_finite(config%minimum_target_response_ratio) .AND. &
      config%minimum_target_response_ratio>=0.0_real64 .AND. &
      ieee_is_finite(config%maximum_target_response_ratio) .AND. &
      config%maximum_target_response_ratio>=config%minimum_target_response_ratio .AND. &
      ieee_is_finite(config%minimum_trust_region_fraction) .AND. &
      config%minimum_trust_region_fraction>0.0_real64 .AND. &
      config%minimum_trust_region_fraction<=1.0_real64 .AND. &
      ieee_is_finite(config%increment_headroom) .AND. &
      config%increment_headroom>0.0_real64 .AND. config%increment_headroom<=1.0_real64 .AND. &
      ieee_is_finite(config%geostrophic_relative_tolerance) .AND. &
      config%geostrophic_relative_tolerance>=0.0_real64 .AND. &
      ieee_is_finite(config%geostrophic_absolute_tolerance) .AND. &
      config%geostrophic_absolute_tolerance>=0.0_real64 .AND. &
      config%minimum_held_out_samples>0 .AND. config%minimum_held_out_radars>0
  END FUNCTION config_valid

END MODULE cloud_bal_balance_operator
