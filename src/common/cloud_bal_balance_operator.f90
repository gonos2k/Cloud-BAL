! Local projection of a proposed increment on the canonical LAPS A grid.
!
! The matrix is never assembled from a second formula.  S maps A-grid
! component values to oriented faces, D takes the finite-volume divergence,
! A=D*S, G=-K*A^T*M, and L=-A*G.  The same procedures are used by the solver,
! the published increment, and the final residual diagnostics.
MODULE cloud_bal_balance_operator
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite,ieee_next_after
  USE cloud_bal_state
  USE cloud_bal_grid_geometry, ONLY: pressure_face_segment,partition_pressure_face
  IMPLICIT NONE
  PRIVATE
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64
  ! A zero science threshold still must not authorize real32 arithmetic nulls.
  REAL(real64), PARAMETER :: FACE_RESPONSE_ROUNDOFF = &
    64.0_real64*REAL(EPSILON(1.0_real32),real64)
  INTEGER, PARAMETER, PUBLIC :: TARGET_AUTHORITY_OBSERVATIONAL = 0
  INTEGER, PARAMETER, PUBLIC :: TARGET_AUTHORITY_MANUFACTURED_TEST = 1
  INTEGER, PARAMETER, PUBLIC :: TARGET_AUTHORITY_MODEL_DYNAMICS = 2
  INTEGER, PARAMETER, PUBLIC :: BOUNDARY_INCREMENT_BASELINE_FIXED = 0
  INTEGER, PARAMETER, PUBLIC :: BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL = 1

  TYPE, PUBLIC :: balance_operator_config
    INTEGER :: target_authority = TARGET_AUTHORITY_OBSERVATIONAL
    INTEGER :: boundary_increment_contract = BOUNDARY_INCREMENT_BASELINE_FIXED
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
    REAL(real64) :: maximum_target_response_failure_fraction = 0.0_real64
    REAL(real64) :: minimum_trust_region_fraction = 0.05_real64
    REAL(real64) :: increment_headroom = 0.95_real64
    REAL(real64) :: geostrophic_relative_tolerance = 0.05_real64
    REAL(real64) :: geostrophic_absolute_tolerance = 1.0e-3_real64
    INTEGER :: minimum_held_out_samples = 20
    INTEGER :: minimum_held_out_radars = 2
  END TYPE balance_operator_config

  TYPE, PUBLIC :: balance_operator_type
    PRIVATE
    INTEGER :: nx=0,ny=0,nz=0
    LOGICAL, PRIVATE :: physical_boundary_authorized=.FALSE.
    REAL(real64), ALLOCATABLE :: volume(:,:,:)
    REAL(real64), ALLOCATABLE :: dx(:,:),dy(:,:),cell_dp(:,:,:)
    REAL(real64), ALLOCATABLE :: ku(:,:,:),kv(:,:,:),ko(:,:,:)
    LOGICAL, ALLOCATABLE :: cell_usable(:,:,:)
    LOGICAL, ALLOCATABLE :: cell_active(:,:,:)
    LOGICAL, ALLOCATABLE :: omega_authorized(:,:,:)
    LOGICAL, ALLOCATABLE :: xseg_active(:),yseg_active(:)
    INTEGER, ALLOCATABLE :: xface_start(:,:),xface_count(:,:)
    INTEGER, ALLOCATABLE :: yface_start(:,:),yface_count(:,:)
    INTEGER, ALLOCATABLE :: xseg_left(:),xseg_right(:)
    INTEGER, ALLOCATABLE :: yseg_left(:),yseg_right(:)
    REAL(real64), ALLOCATABLE :: xseg_area(:),yseg_area(:)
    LOGICAL, ALLOCATABLE :: pface_active(:,:,:)
    REAL(real64), ALLOCATABLE :: pface_area(:,:,:)
    REAL(real64), ALLOCATABLE :: xleft_weight(:,:,:),xright_weight(:,:,:)
    REAL(real64), ALLOCATABLE :: yleft_weight(:,:,:),yright_weight(:,:,:)
    REAL(real64), ALLOCATABLE :: pleft_weight(:,:,:),pright_weight(:,:,:)
    INTEGER, ALLOCATABLE :: component(:,:,:)
    INTEGER :: ncomponent=0
  END TYPE balance_operator_type

  ! Read-only copy for tests and diagnostics.  Mutating this view can never
  ! alter the sealed operator used by a correction.
  TYPE, PUBLIC :: balance_operator_snapshot
    INTEGER :: ncomponent=0
    REAL(real64), ALLOCATABLE :: volume(:,:,:)
    LOGICAL, ALLOCATABLE :: cell_active(:,:,:)
    LOGICAL, ALLOCATABLE :: omega_authorized(:,:,:)
  END TYPE balance_operator_snapshot

  PUBLIC :: build_balance_operator
  PUBLIC :: apply_continuity_operator
  PUBLIC :: apply_adjoint_metric
  PUBLIC :: apply_balance_correction
  PUBLIC :: apply_normal_operator
  PUBLIC :: apply_localized_balance
  PUBLIC :: continuity_norms
  PUBLIC :: balance_beta_active
  PUBLIC :: state_continuity_residual
  PUBLIC :: state_dry_air_mass_flux_divergence
  PUBLIC :: target_response_failure_fraction
  PUBLIC :: geostrophic_residual
  PUBLIC :: assess_pressure_geostrophic_change
  PUBLIC :: boundary_contract_valid
  PUBLIC :: physical_boundary_contract_valid
  PUBLIC :: manufactured_boundary_contract_valid
  PUBLIC :: model_boundary_increment_contract_valid
  PUBLIC :: snapshot_balance_operator
  PUBLIC :: target_is_resolved

CONTAINS

  SUBROUTINE snapshot_balance_operator(op,snapshot,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    TYPE(balance_operator_snapshot), INTENT(OUT) :: snapshot
    INTEGER, INTENT(OUT) :: status
    status=STATUS_FAILED
    IF (.NOT.diagnostic_operator_shapes_valid(op)) RETURN
    snapshot%ncomponent=op%ncomponent
    snapshot%volume=op%volume
    snapshot%cell_active=op%cell_active
    snapshot%omega_authorized=op%omega_authorized
    status=STATUS_OK
  END SUBROUTINE snapshot_balance_operator

  SUBROUTINE build_balance_operator(state,config,op,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(balance_operator_config), INTENT(IN) :: config
    TYPE(balance_operator_type), INTENT(OUT) :: op
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: nx,ny,nz,i,j,k
    REAL(real64) :: denom,gain,posterior
    LOGICAL, ALLOCATABLE :: resolved(:,:,:)

    status=STATUS_FAILED; reason=REASON_SHAPE
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    IF (nx<4 .OR. ny<4 .OR. nz<2) RETURN
    IF (.NOT.config_valid(config)) THEN; reason=REASON_RANGE; RETURN; END IF
    IF (.NOT.operator_input_shapes_valid(state)) RETURN
    IF (.NOT.omega_target_sigma_contract_valid(state)) THEN
      reason=REASON_METADATA; RETURN
    END IF
    IF (config%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS .AND. &
        .NOT.model_target_coverage_contract_valid(state)) THEN
      reason=REASON_METADATA
      RETURN
    END IF
    IF (config%target_authority==TARGET_AUTHORITY_OBSERVATIONAL .AND. &
        (ANY(IAND(state%omega_target%source,SOURCE_MANUFACTURED_TEST)/=0_int32) .OR. &
         ANY(IAND(state%omega_target_sigma%source,SOURCE_MANUFACTURED_TEST)/=0_int32))) THEN
      reason=REASON_AUTHORITY
      RETURN
    END IF
    IF (config%target_authority==TARGET_AUTHORITY_MANUFACTURED_TEST .AND. &
        ANY(state%omega_target%valid .AND. &
            .NOT.manufactured_target_has_test_authority( &
              state%omega_target%valid,state%omega_target%quality, &
              state%omega_target%source))) THEN
      reason=REASON_AUTHORITY
      RETURN
    END IF
    IF (ANY(.NOT.ieee_is_finite(state%balance_beta)) .OR. &
        ANY(state%balance_beta<0.0_real32) .OR. &
        ANY(state%balance_beta>1.0_real32)) THEN
      reason=REASON_RANGE
      RETURN
    END IF
    DO k=1,nz-1
      IF (ANY(state%pressure%value(:,:,k)<=state%pressure%value(:,:,k+1))) THEN
        reason=REASON_RANGE
        RETURN
      END IF
    END DO
    IF (.NOT.pressure_geometry_is_valid(state)) THEN
      reason=REASON_METADATA
      RETURN
    END IF
    IF (.NOT.boundary_contract_valid(state)) THEN; reason=REASON_METADATA; RETURN; END IF
    IF (config%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      ALLOCATE(resolved(nx,ny,nz))
      resolved=target_is_resolved(state,config%target_authority)
      DO k=1,nz; DO j=1,ny; DO i=1,nx
        IF (resolved(i,j,k) .AND. &
            .NOT.model_target_level_is_interior(state,i,j,k)) THEN
          reason=REASON_AUTHORITY
          RETURN
        END IF
      END DO; END DO; END DO
    END IF
    IF (ANY(target_is_resolved(state,config%target_authority) .AND. &
            balance_beta_active(state%balance_beta,config%minimum_beta)) .AND. &
        .NOT.target_boundary_contract_valid(state,config%target_authority)) THEN
      reason=REASON_AUTHORITY
      RETURN
    END IF
    IF (ANY(.NOT.ieee_is_finite(state%grid%dx)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%dy)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%cell_dp)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%pressure_mass_measure)) .OR. &
        ANY(state%grid%dx<=0.0_real64) .OR. ANY(state%grid%dy<=0.0_real64) .OR. &
        ANY(state%above_ground .AND. state%grid%cell_dp<=0.0_real64) .OR. &
        ANY(state%above_ground .AND. state%grid%pressure_mass_measure<=0.0_real64)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    op%nx=nx; op%ny=ny; op%nz=nz
    op%physical_boundary_authorized= &
      target_boundary_contract_valid(state,config%target_authority)
    ALLOCATE(op%volume(nx,ny,nz),op%dx(nx,ny),op%dy(nx,ny), &
             op%cell_dp(nx,ny,nz), &
             op%ku(nx,ny,nz),op%kv(nx,ny,nz),op%ko(nx,ny,nz), &
             op%cell_usable(nx,ny,nz),op%cell_active(nx,ny,nz), &
             op%omega_authorized(nx,ny,nz), &
             op%component(nx,ny,nz))
    ALLOCATE(op%xleft_weight(nx-1,ny,nz),op%xright_weight(nx-1,ny,nz))
    ALLOCATE(op%yleft_weight(nx,ny-1,nz),op%yright_weight(nx,ny-1,nz))
    ALLOCATE(op%pface_active(nx,ny,nz-1),op%pface_area(nx,ny,nz-1), &
             op%pleft_weight(nx,ny,nz-1),op%pright_weight(nx,ny,nz-1))
    op%volume=state%grid%pressure_mass_measure
    op%dx=state%grid%dx; op%dy=state%grid%dy
    op%cell_dp=state%grid%cell_dp
    op%cell_usable=state%above_ground .AND. &
      cell_is_usable(state%pressure%valid,state%pressure%quality,state%pressure%source) .AND. &
      cell_is_usable(state%u%valid,state%u%quality,state%u%source) .AND. &
      cell_is_usable(state%v%valid,state%v%quality,state%v%source) .AND. &
      cell_is_usable(state%omega%valid,state%omega%quality,state%omega%source)
    op%cell_active=op%cell_usable .AND. &
                   balance_beta_active(state%balance_beta,config%minimum_beta)
    IF (config%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      op%cell_active=op%cell_active .AND. state%model_target_coverage
    END IF
    op%omega_authorized=op%cell_active .AND. target_is_resolved(state,config%target_authority)
    IF (config%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      DO k=1,nz; DO j=1,ny; DO i=1,nx
        IF (.NOT.model_target_level_is_interior(state,i,j,k)) &
          op%omega_authorized(i,j,k)=.FALSE.
      END DO; END DO; END DO
    END IF
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
    IF (config%target_authority==TARGET_AUTHORITY_OBSERVATIONAL) THEN
      DO k=1,nz; DO j=1,ny; DO i=1,nx
        IF (.NOT.op%omega_authorized(i,j,k)) CYCLE
        CALL target_error_weight(op%ko(i,j,k), &
          REAL(state%omega_target_sigma%value(i,j,k),real64),gain,posterior)
        op%ko(i,j,k)=posterior
      END DO; END DO; END DO
    END IF
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
    END DO; END DO; END DO
    DO k=1,nz; DO j=1,ny-1; DO i=1,nx
      denom=op%dy(i,j)+op%dy(i,j+1)
      op%yleft_weight(i,j,k)=op%dy(i,j+1)/denom
      op%yright_weight(i,j,k)=op%dy(i,j)/denom
    END DO; END DO; END DO
    CALL build_lateral_segments(state,op,status,reason)
    IF (status/=STATUS_OK) RETURN
    DO k=1,nz-1; DO j=1,ny; DO i=1,nx
      denom=REAL(state%pressure%value(i,j,k),real64)- &
        REAL(state%pressure%value(i,j,k+1),real64)
      IF (denom<=0.0_real64) THEN
        reason=REASON_RANGE; RETURN
      END IF
      op%pleft_weight(i,j,k)=0.5_real64
      op%pright_weight(i,j,k)=0.5_real64
      IF (op%cell_usable(i,j,k) .AND. op%cell_usable(i,j,k+1)) THEN
        op%pleft_weight(i,j,k)=(state%grid%pressure_interface(i,j,k+1)- &
          REAL(state%pressure%value(i,j,k+1),real64))/denom
        op%pright_weight(i,j,k)=1.0_real64-op%pleft_weight(i,j,k)
        IF (op%pleft_weight(i,j,k)<0.0_real64 .OR. &
            op%pleft_weight(i,j,k)>1.0_real64) THEN
          reason=REASON_RANGE; RETURN
        END IF
      END IF
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
    IF (ANY(op%omega_authorized .AND. op%ko<=0.0_real64)) THEN
      reason=REASON_AUTHORITY
      RETURN
    END IF
    IF (.NOT.lateral_segments_valid(op)) THEN
      reason=REASON_RANGE
      RETURN
    END IF
    CALL label_components(op)
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE build_balance_operator

  SUBROUTINE build_lateral_segments(state,op,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(balance_operator_type), INTENT(INOUT) :: op
    INTEGER, INTENT(OUT) :: status,reason
    TYPE(pressure_face_segment), ALLOCATABLE :: segments(:)
    INTEGER :: i,j,s,offset,nsegments
    LOGICAL :: ok
    REAL(real64) :: area

    status=STATUS_FAILED; reason=REASON_RANGE
    ALLOCATE(op%xface_start(op%nx-1,op%ny),op%xface_count(op%nx-1,op%ny))
    ALLOCATE(op%yface_start(op%nx,op%ny-1),op%yface_count(op%nx,op%ny-1))

    nsegments=0
    DO j=1,op%ny; DO i=1,op%nx-1
      CALL partition_pressure_face(state%grid%pressure_interface(i,j,:), &
        state%grid%pressure_interface(i+1,j,:),segments,ok)
      IF (.NOT.ok) RETURN
      op%xface_start(i,j)=nsegments+1
      op%xface_count(i,j)=COUNT(segments%pressure_thickness>0.0_real64)
      nsegments=nsegments+op%xface_count(i,j)
    END DO; END DO
    ALLOCATE(op%xseg_left(nsegments),op%xseg_right(nsegments), &
             op%xseg_area(nsegments),op%xseg_active(nsegments))
    DO j=1,op%ny; DO i=1,op%nx-1
      CALL partition_pressure_face(state%grid%pressure_interface(i,j,:), &
        state%grid%pressure_interface(i+1,j,:),segments,ok)
      IF (.NOT.ok) RETURN
      offset=op%xface_start(i,j)-1
      s=0
      DO WHILE (s<SIZE(segments))
        s=s+1
        IF (segments(s)%pressure_thickness<=0.0_real64) CYCLE
        offset=offset+1
        area=0.5_real64*(op%dy(i,j)+op%dy(i+1,j))* &
             segments(s)%pressure_thickness/GRAVITY
        IF (.NOT.ieee_is_finite(area) .OR. area<=0.0_real64) RETURN
        op%xseg_left(offset)=segments(s)%left_level
        op%xseg_right(offset)=segments(s)%right_level
        op%xseg_area(offset)=area
      END DO
    END DO; END DO

    nsegments=0
    DO j=1,op%ny-1; DO i=1,op%nx
      CALL partition_pressure_face(state%grid%pressure_interface(i,j,:), &
        state%grid%pressure_interface(i,j+1,:),segments,ok)
      IF (.NOT.ok) RETURN
      op%yface_start(i,j)=nsegments+1
      op%yface_count(i,j)=COUNT(segments%pressure_thickness>0.0_real64)
      nsegments=nsegments+op%yface_count(i,j)
    END DO; END DO
    ALLOCATE(op%yseg_left(nsegments),op%yseg_right(nsegments), &
             op%yseg_area(nsegments),op%yseg_active(nsegments))
    DO j=1,op%ny-1; DO i=1,op%nx
      CALL partition_pressure_face(state%grid%pressure_interface(i,j,:), &
        state%grid%pressure_interface(i,j+1,:),segments,ok)
      IF (.NOT.ok) RETURN
      offset=op%yface_start(i,j)-1
      s=0
      DO WHILE (s<SIZE(segments))
        s=s+1
        IF (segments(s)%pressure_thickness<=0.0_real64) CYCLE
        offset=offset+1
        area=0.5_real64*(op%dx(i,j)+op%dx(i,j+1))* &
             segments(s)%pressure_thickness/GRAVITY
        IF (.NOT.ieee_is_finite(area) .OR. area<=0.0_real64) RETURN
        op%yseg_left(offset)=segments(s)%left_level
        op%yseg_right(offset)=segments(s)%right_level
        op%yseg_area(offset)=area
      END DO
    END DO; END DO

    CALL restrict_lateral_support(op)
    DO j=1,op%ny; DO i=1,op%nx-1
      DO s=op%xface_start(i,j),op%xface_start(i,j)+op%xface_count(i,j)-1
        op%xseg_active(s)=op%cell_active(i,j,op%xseg_left(s)) .AND. &
          op%cell_active(i+1,j,op%xseg_right(s)) .AND. &
          (op%ku(i,j,op%xseg_left(s))>0.0_real64 .OR. &
           op%ku(i+1,j,op%xseg_right(s))>0.0_real64)
      END DO
    END DO; END DO
    DO j=1,op%ny-1; DO i=1,op%nx
      DO s=op%yface_start(i,j),op%yface_start(i,j)+op%yface_count(i,j)-1
        op%yseg_active(s)=op%cell_active(i,j,op%yseg_left(s)) .AND. &
          op%cell_active(i,j+1,op%yseg_right(s)) .AND. &
          (op%kv(i,j,op%yseg_left(s))>0.0_real64 .OR. &
           op%kv(i,j+1,op%yseg_right(s))>0.0_real64)
      END DO
    END DO; END DO
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE build_lateral_segments

  SUBROUTINE restrict_lateral_support(op)
    TYPE(balance_operator_type), INTENT(INOUT) :: op
    INTEGER :: i,j,s,left_level,right_level

    DO j=1,op%ny; DO i=1,op%nx-1
      DO s=op%xface_start(i,j),op%xface_start(i,j)+op%xface_count(i,j)-1
        left_level=op%xseg_left(s); right_level=op%xseg_right(s)
        IF (op%cell_active(i,j,left_level) .AND. &
            .NOT.(op%cell_active(i+1,j,right_level) .AND. &
                  op%cell_usable(i+1,j,right_level))) &
          op%ku(i,j,left_level)=0.0_real64
        IF (op%cell_active(i+1,j,right_level) .AND. &
            .NOT.(op%cell_active(i,j,left_level) .AND. &
                  op%cell_usable(i,j,left_level))) &
          op%ku(i+1,j,right_level)=0.0_real64
      END DO
    END DO; END DO
    DO j=1,op%ny-1; DO i=1,op%nx
      DO s=op%yface_start(i,j),op%yface_start(i,j)+op%yface_count(i,j)-1
        left_level=op%yseg_left(s); right_level=op%yseg_right(s)
        IF (op%cell_active(i,j,left_level) .AND. &
            .NOT.(op%cell_active(i,j+1,right_level) .AND. &
                  op%cell_usable(i,j+1,right_level))) &
          op%kv(i,j,left_level)=0.0_real64
        IF (op%cell_active(i,j+1,right_level) .AND. &
            .NOT.(op%cell_active(i,j,left_level) .AND. &
                  op%cell_usable(i,j,left_level))) &
          op%kv(i,j+1,right_level)=0.0_real64
      END DO
    END DO; END DO
  END SUBROUTINE restrict_lateral_support

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
    INTEGER :: i,j,k,s,left_level,right_level
    REAL(real64) :: flux

    residual=0.0_real64; status=STATUS_FAILED
    IF (.NOT.diagnostic_operator_shapes_valid(op)) RETURN
    IF (.NOT.operator_array_shapes_valid(op,u,v,omega,residual)) RETURN
    IF (ANY(op%cell_active .AND. (.NOT.ieee_is_finite(u) .OR. &
        .NOT.ieee_is_finite(v) .OR. .NOT.ieee_is_finite(omega)))) RETURN
    DO j=1,op%ny; DO i=1,op%nx-1
      DO s=op%xface_start(i,j),op%xface_start(i,j)+op%xface_count(i,j)-1
        IF (.NOT.op%xseg_active(s)) CYCLE
        left_level=op%xseg_left(s); right_level=op%xseg_right(s)
        flux=op%xseg_area(s)*(op%xleft_weight(i,j,left_level)*u(i,j,left_level)+ &
          op%xright_weight(i,j,right_level)*u(i+1,j,right_level))
        residual(i,j,left_level)=residual(i,j,left_level)+ &
          flux/op%volume(i,j,left_level)
        residual(i+1,j,right_level)=residual(i+1,j,right_level)- &
          flux/op%volume(i+1,j,right_level)
      END DO
    END DO; END DO
    DO j=1,op%ny-1; DO i=1,op%nx
      DO s=op%yface_start(i,j),op%yface_start(i,j)+op%yface_count(i,j)-1
        IF (.NOT.op%yseg_active(s)) CYCLE
        left_level=op%yseg_left(s); right_level=op%yseg_right(s)
        flux=op%yseg_area(s)*(op%yleft_weight(i,j,left_level)*v(i,j,left_level)+ &
          op%yright_weight(i,j,right_level)*v(i,j+1,right_level))
        residual(i,j,left_level)=residual(i,j,left_level)+ &
          flux/op%volume(i,j,left_level)
        residual(i,j+1,right_level)=residual(i,j+1,right_level)- &
          flux/op%volume(i,j+1,right_level)
      END DO
    END DO; END DO
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
    INTEGER :: i,j,k,s,left_level,right_level
    REAL(real64) :: contribution

    atu=0.0_real64; atv=0.0_real64; atomega=0.0_real64
    status=STATUS_FAILED
    IF (.NOT.diagnostic_operator_shapes_valid(op)) RETURN
    IF (.NOT.four_shapes_match(op,lambda,atu,atv,atomega)) RETURN
    IF (ANY(op%cell_active .AND. .NOT.ieee_is_finite(lambda))) RETURN
    DO j=1,op%ny; DO i=1,op%nx-1
      DO s=op%xface_start(i,j),op%xface_start(i,j)+op%xface_count(i,j)-1
        IF (.NOT.op%xseg_active(s)) CYCLE
        left_level=op%xseg_left(s); right_level=op%xseg_right(s)
        contribution=op%xseg_area(s)*(lambda(i,j,left_level)- &
          lambda(i+1,j,right_level))
        atu(i,j,left_level)=atu(i,j,left_level)+ &
          op%xleft_weight(i,j,left_level)*contribution
        atu(i+1,j,right_level)=atu(i+1,j,right_level)+ &
          op%xright_weight(i,j,right_level)*contribution
      END DO
    END DO; END DO
    DO j=1,op%ny-1; DO i=1,op%nx
      DO s=op%yface_start(i,j),op%yface_start(i,j)+op%yface_count(i,j)-1
        IF (.NOT.op%yseg_active(s)) CYCLE
        left_level=op%yseg_left(s); right_level=op%yseg_right(s)
        contribution=op%yseg_area(s)*(lambda(i,j,left_level)- &
          lambda(i,j+1,right_level))
        atv(i,j,left_level)=atv(i,j,left_level)+ &
          op%yleft_weight(i,j,left_level)*contribution
        atv(i,j+1,right_level)=atv(i,j+1,right_level)+ &
          op%yright_weight(i,j,right_level)*contribution
      END DO
    END DO; END DO
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
    du=0.0_real64; dv=0.0_real64; domega=0.0_real64
    status=STATUS_FAILED
    IF (.NOT.op%physical_boundary_authorized) RETURN
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

    l_lambda=0.0_real64; status=STATUS_FAILED
    IF (.NOT.diagnostic_operator_shapes_valid(op)) RETURN
    IF (.NOT.four_shapes_match(op,lambda,l_lambda,l_lambda,l_lambda)) RETURN
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
    REAL(real64) :: raw_maxwind,raw_maxomega,operator_identity_max,gain,posterior
    INTEGER :: status,reason,iterations,solver_reason,i,j,k
    LOGICAL :: accepted,has_resolved_target

    IF (PRESENT(config)) cfg=config
    ! Surface thermodynamic fields are not inputs to this pressure-coordinate solve.
    CALL validate_canonical_state(state_in,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    IF (.NOT.config_valid(cfg)) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_RANGE)
      RETURN
    END IF
    IF (cfg%target_authority==TARGET_AUTHORITY_OBSERVATIONAL .AND. &
        (ANY(IAND(state_in%omega_target%source,SOURCE_MANUFACTURED_TEST)/=0_int32) .OR. &
         ANY(IAND(state_in%omega_target_sigma%source,SOURCE_MANUFACTURED_TEST)/=0_int32))) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_AUTHORITY)
      RETURN
    END IF
    IF (cfg%target_authority==TARGET_AUTHORITY_OBSERVATIONAL .AND. &
        (ANY(IAND(state_in%omega_top_boundary%source, &
                  SOURCE_MANUFACTURED_TEST)/=0_int32) .OR. &
         ANY(IAND(state_in%omega_bottom_boundary%source, &
                  SOURCE_MANUFACTURED_TEST)/=0_int32))) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_AUTHORITY)
      RETURN
    END IF
    IF (cfg%target_authority==TARGET_AUTHORITY_MANUFACTURED_TEST .AND. &
        ANY(state_in%omega_target%valid .AND. &
            .NOT.manufactured_target_has_test_authority( &
              state_in%omega_target%valid,state_in%omega_target%quality, &
              state_in%omega_target%source))) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_AUTHORITY)
      RETURN
    END IF
    IF (state_in%grid%nx<4 .OR. state_in%grid%ny<4 .OR. &
        state_in%grid%nz<2) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_SHAPE)
      RETURN
    END IF
    has_resolved_target=ANY(target_is_resolved(state_in,cfg%target_authority))
    IF (.NOT.has_resolved_target) THEN
      IF (cfg%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_AUTHORITY)
        RETURN
      END IF
      state_out=state_in
      CALL initialize_stage_result(result,state_in%grid%nx,state_in%grid%ny, &
                                   state_in%grid%nz,STATUS_OK,REASON_NONE)
      RETURN
    END IF
    IF (.NOT.ANY(target_is_resolved(state_in,cfg%target_authority) .AND. &
                 balance_beta_active(state_in%balance_beta,cfg%minimum_beta))) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_AUTHORITY)
      RETURN
    END IF
    IF (boundary_contract_valid(state_in) .AND. &
        .NOT.target_boundary_contract_valid(state_in,cfg%target_authority)) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_AUTHORITY)
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
    IF (cfg%target_authority==TARGET_AUTHORITY_OBSERVATIONAL) THEN
      DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
        IF (.NOT.op%omega_authorized(i,j,k)) CYCLE
        CALL target_error_weight(REAL(state_in%balance_beta(i,j,k),real64)*cfg%kappa_omega, &
          REAL(state_in%omega_target_sigma%value(i,j,k),real64),gain,posterior)
        q_requested(i,j,k)=gain*q_requested(i,j,k)
      END DO; END DO; END DO
    END IF
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
    IF (cfg%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      CALL apply_bounded_model_projection(state_in,op,cfg,q_requested,qomega, &
        r_proposed,candidate,du,dv,do_corr,domega,modified, &
        maxwind,maxomega,iterations,status,reason)
      IF (status/=STATUS_OK) THEN
        CALL reject_candidate(state_in,state_out,result,status,reason)
        RETURN
      END IF
    END IF
    IF (cfg%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS .AND. &
        .NOT.model_boundary_increment_contract_valid(state_in,candidate)) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_AUTHORITY)
      RETURN
    END IF
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
    ! Only this stage can publish the candidate after every balance gate passes.
    state_out=candidate
    result=candidate_result
  END SUBROUTINE apply_localized_balance

  ! Model-authority candidates are projected in the same operator used by the
  ! initial solve.  This private path works only on a local copy and commits
  ! the rounded fields after strict closure and target-response checks pass.
  SUBROUTINE apply_bounded_model_projection(input,op,cfg,q_requested,qomega, &
      r_proposed,candidate,du,dv,do_corr,domega,modified, &
      maxwind,maxomega,total_iterations,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input
    TYPE(balance_operator_type), INTENT(IN) :: op
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    REAL(real64), INTENT(IN) :: q_requested(:,:,:),qomega(:,:,:)
    REAL(real64), INTENT(IN) :: r_proposed(:,:,:)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: candidate
    REAL(real64), INTENT(INOUT) :: du(:,:,:),dv(:,:,:),do_corr(:,:,:),domega(:,:,:)
    LOGICAL, INTENT(INOUT) :: modified(:,:,:)
    REAL(real64), INTENT(INOUT) :: maxwind,maxomega
    INTEGER, INTENT(INOUT) :: total_iterations
    INTEGER, INTENT(OUT) :: status,reason
    TYPE(cloud_bal_state_type) :: trial
    REAL(real64), ALLOCATABLE :: x_u(:,:,:),x_v(:,:,:),x_o(:,:,:)
    REAL(real64), ALLOCATABLE :: desired_u(:,:,:),desired_v(:,:,:),desired_o(:,:,:)
    REAL(real64), ALLOCATABLE :: lambda(:,:,:),work_u(:,:,:),work_v(:,:,:),work_o(:,:,:)
    REAL(real64), ALLOCATABLE :: residual(:,:,:),zero(:,:,:)
    REAL(real64), ALLOCATABLE :: trial_domega(:,:,:)
    LOGICAL, ALLOCATABLE :: trial_modified(:,:,:)
    REAL(real64) :: reference_rms,reference_max,strict_rms,strict_max
    REAL(real64) :: final_rms,final_max,response_failure,trial_maxwind,trial_maxomega
    TYPE(balance_operator_config) :: projection_cfg
    INTEGER :: cycle,projection_iterations,solver_status,solver_reason
    INTEGER :: local_status,local_reason,remaining_iterations,used_iterations
    LOGICAL :: representable

    status=STATUS_FAILED; reason=REASON_GATE
    IF (.NOT.diagnostic_operator_shapes_valid(op)) RETURN
    IF (.NOT.operator_array_shapes_valid(op,du,dv,domega,r_proposed) .OR. &
        .NOT.four_shapes_match(op,q_requested,qomega,r_proposed,du) .OR. &
        ANY(SHAPE(do_corr)/=SHAPE(du)) .OR. ANY(SHAPE(modified)/=SHAPE(du))) RETURN
    CALL continuity_norms(op,r_proposed,reference_rms,reference_max)
    IF (.NOT.ieee_is_finite(reference_rms) .OR. .NOT.ieee_is_finite(reference_max)) RETURN
    strict_rms=MAX(cfg%solver_residual_fraction*reference_rms, &
                   cfg%solver_absolute_tolerance)
    strict_max=MAX(cfg%solver_residual_fraction*reference_max, &
                   cfg%solver_absolute_tolerance)
    IF (.NOT.ieee_is_finite(strict_rms) .OR. .NOT.ieee_is_finite(strict_max)) RETURN
    IF (total_iterations<0 .OR. total_iterations>cfg%maximum_iterations) THEN
      reason=REASON_SOLVER; RETURN
    END IF
    used_iterations=total_iterations

    ALLOCATE(x_u(op%nx,op%ny,op%nz),x_v(op%nx,op%ny,op%nz),x_o(op%nx,op%ny,op%nz), &
      desired_u(op%nx,op%ny,op%nz),desired_v(op%nx,op%ny,op%nz), &
      desired_o(op%nx,op%ny,op%nz),lambda(op%nx,op%ny,op%nz), &
      work_u(op%nx,op%ny,op%nz),work_v(op%nx,op%ny,op%nz), &
      work_o(op%nx,op%ny,op%nz),residual(op%nx,op%ny,op%nz), &
      zero(op%nx,op%ny,op%nz), &
      trial_domega(op%nx,op%ny,op%nz),trial_modified(op%nx,op%ny,op%nz))
    zero=0.0_real64
    x_u=du; x_v=dv; x_o=domega

    DO cycle=1,20
      CALL apply_continuity_operator(op,x_u,x_v,x_o,residual,local_status)
      IF (local_status/=STATUS_OK) THEN; reason=REASON_NONFINITE; RETURN; END IF
      CALL continuity_norms(op,residual,final_rms,final_max)
      IF (.NOT.ieee_is_finite(final_rms) .OR. .NOT.ieee_is_finite(final_max)) THEN
        reason=REASON_NONFINITE; RETURN
      END IF
      IF (final_rms<=strict_rms .AND. final_max<=strict_max) THEN
        desired_u=x_u; desired_v=x_v; desired_o=x_o
      ELSE
        remaining_iterations=cfg%maximum_iterations-used_iterations
        IF (remaining_iterations<=0) THEN; reason=REASON_SOLVER; RETURN; END IF
        projection_cfg=cfg
        projection_cfg%maximum_iterations=remaining_iterations
        CALL solve_normal_equation(op,residual,projection_cfg,lambda,work_u,work_v,work_o, &
          projection_iterations,solver_status,solver_reason,final_rms,final_max, &
          reference_rms,reference_max)
        used_iterations=used_iterations+projection_iterations
        IF (solver_status/=STATUS_OK) THEN
          reason=REASON_SOLVER; RETURN
        END IF
        CALL apply_balance_correction(op,lambda,desired_u,desired_v,desired_o,local_status)
        IF (local_status/=STATUS_OK) THEN; reason=REASON_NONFINITE; RETURN; END IF
        desired_u=x_u+desired_u
        desired_v=x_v+desired_v
        desired_o=x_o+desired_o
      END IF
      CALL project_model_increment(input,op,q_requested,desired_u,desired_v,desired_o,cfg, &
        representable)
      IF (.NOT.representable) THEN; reason=REASON_GATE; RETURN; END IF
      CALL make_candidate(input,op,zero,trial,desired_u,desired_v,desired_o,trial_domega, &
        trial_modified,trial_maxwind,trial_maxomega)
      CALL validate_canonical_state(trial,.FALSE.,.FALSE.,local_status,local_reason,.FALSE.)
      IF (local_status/=STATUS_OK) THEN; reason=local_reason; RETURN; END IF
      CALL apply_continuity_operator(op,desired_u,desired_v,trial_domega,residual,local_status)
      IF (local_status/=STATUS_OK) THEN; reason=REASON_NONFINITE; RETURN; END IF
      CALL continuity_norms(op,residual,final_rms,final_max)
      response_failure=target_response_failure_fraction(op,trial_domega,q_requested, &
        cfg%solver_absolute_tolerance,cfg%minimum_target_response_ratio, &
        cfg%maximum_target_response_ratio)
      IF (final_rms<=strict_rms .AND. final_max<=strict_max .AND. &
          response_failure<=cfg%maximum_target_response_failure_fraction) THEN
        candidate=trial
        du=desired_u; dv=desired_v; domega=trial_domega
        do_corr=domega-qomega
        modified=trial_modified
        maxwind=trial_maxwind; maxomega=trial_maxomega
        total_iterations=used_iterations
        status=STATUS_OK; reason=REASON_NONE
        RETURN
      END IF
      x_u=desired_u; x_v=desired_v; x_o=trial_domega
    END DO
    status=STATUS_DEGRADED; reason=REASON_GATE
  END SUBROUTINE apply_bounded_model_projection

  SUBROUTINE project_model_increment(state,op,q_requested,desired_u,desired_v,desired_o,cfg,ok)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: q_requested(:,:,:)
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    REAL(real64), INTENT(INOUT) :: desired_u(:,:,:),desired_v(:,:,:),desired_o(:,:,:)
    LOGICAL, INTENT(OUT) :: ok
    INTEGER :: i,j,k
    LOGICAL :: local_ok
    REAL(real64) :: stored_value

    ok=.FALSE.
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.op%cell_active(i,j,k)) CYCLE
      CALL round_model_increment(state%u%value(i,j,k),desired_u(i,j,k),stored_value,local_ok)
      IF (.NOT.local_ok) RETURN
      desired_u(i,j,k)=stored_value
      CALL round_model_increment(state%v%value(i,j,k),desired_v(i,j,k),stored_value,local_ok)
      IF (.NOT.local_ok) RETURN
      desired_v(i,j,k)=stored_value
      IF (op%omega_authorized(i,j,k)) THEN
        CALL box_model_increment(state%omega%value(i,j,k),desired_o(i,j,k), &
          q_requested(i,j,k),cfg,stored_value,local_ok)
        IF (.NOT.local_ok) RETURN
        desired_o(i,j,k)=stored_value
      END IF
    END DO; END DO; END DO
    ok=.TRUE.
  END SUBROUTINE project_model_increment

  SUBROUTINE round_model_increment(base,desired,increment,ok)
    REAL(real32), INTENT(IN) :: base
    REAL(real64), INTENT(IN) :: desired
    REAL(real64), INTENT(OUT) :: increment
    LOGICAL, INTENT(OUT) :: ok
    REAL(real32) :: stored
    REAL(real64) :: base64
    ok=.FALSE.; increment=0.0_real64
    base64=REAL(base,real64)
    IF (.NOT.ieee_is_finite(base64) .OR. .NOT.ieee_is_finite(desired)) RETURN
    stored=REAL(base64+desired,real32)
    IF (.NOT.ieee_is_finite(stored)) RETURN
    increment=REAL(stored,real64)-base64
    ok=ieee_is_finite(increment)
  END SUBROUTINE round_model_increment

  SUBROUTINE box_model_increment(base,desired,q,cfg,increment,ok)
    REAL(real32), INTENT(IN) :: base
    REAL(real64), INTENT(IN) :: desired,q
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    REAL(real64), INTENT(OUT) :: increment
    LOGICAL, INTENT(OUT) :: ok
    REAL(real64) :: base64,lo,hi,stored64
    REAL(real32) :: stored,stored_lo,stored_hi
    REAL(real32), PARAMETER :: positive_infinity=HUGE(1.0_real32)
    ok=.FALSE.; increment=0.0_real64
    base64=REAL(base,real64)
    IF (.NOT.ieee_is_finite(base64) .OR. .NOT.ieee_is_finite(desired) .OR. &
        .NOT.ieee_is_finite(q)) RETURN
    lo=MIN(cfg%minimum_target_response_ratio*q,cfg%maximum_target_response_ratio*q)
    hi=MAX(cfg%minimum_target_response_ratio*q,cfg%maximum_target_response_ratio*q)
    lo=MAX(lo,-cfg%maximum_omega_increment)
    hi=MIN(hi,cfg%maximum_omega_increment)
    IF (.NOT.ieee_is_finite(lo) .OR. .NOT.ieee_is_finite(hi) .OR. lo>hi) RETURN
    stored_lo=REAL(base64+lo,real32); stored_hi=REAL(base64+hi,real32)
    IF (.NOT.ieee_is_finite(stored_lo) .OR. .NOT.ieee_is_finite(stored_hi)) RETURN
    IF (REAL(stored_lo,real64)-base64<lo) &
      stored_lo=ieee_next_after(stored_lo,positive_infinity)
    IF (REAL(stored_hi,real64)-base64>hi) &
      stored_hi=ieee_next_after(stored_hi,-positive_infinity)
    IF (.NOT.ieee_is_finite(stored_lo) .OR. .NOT.ieee_is_finite(stored_hi) .OR. &
        stored_lo>stored_hi) RETURN
    stored=REAL(base64+desired,real32)
    IF (.NOT.ieee_is_finite(stored)) RETURN
    IF (stored<stored_lo) stored=stored_lo
    IF (stored>stored_hi) stored=stored_hi
    stored64=REAL(stored,real64)-base64
    IF (.NOT.ieee_is_finite(stored64) .OR. stored64<lo .OR. stored64>hi) RETURN
    increment=stored64; ok=.TRUE.
  END SUBROUTINE box_model_increment

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
    IF (rc_rms>physical_residual_limit(rb_rms,cfg, &
          cfg%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS)) &
      failures=IOR(failures,GATE_PHYSICAL_RMS)
    IF (rc_max>physical_residual_limit(rb_max,cfg, &
          cfg%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS)) &
      failures=IOR(failures,GATE_PHYSICAL_MAX)
    IF (max_wind>cfg%maximum_wind_increment) &
      failures=IOR(failures,GATE_WIND_INCREMENT)
    IF (max_omega>cfg%maximum_omega_increment) &
      failures=IOR(failures,GATE_OMEGA_INCREMENT)
    IF (response_failure_fraction>cfg%maximum_target_response_failure_fraction) &
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

  PURE REAL(real64) FUNCTION physical_residual_limit(background,cfg,model_dynamics)
    REAL(real64), INTENT(IN) :: background
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(IN), OPTIONAL :: model_dynamics
    IF (PRESENT(model_dynamics) .AND. model_dynamics) THEN
      ! Model authority checks the candidate against the unchanged background
      ! plus the configured tolerance.  The absolute residual remains a
      ! diagnostic and is not labeled physical continuity closure.
      physical_residual_limit=background+cfg%physical_residual_tolerance
    ELSE
      physical_residual_limit=MIN(background+cfg%physical_residual_tolerance, &
                                  cfg%maximum_physical_residual)
    END IF
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
                                   status,failure_reason,final_rms,final_max, &
                                   reference_rms,reference_max)
    TYPE(balance_operator_type), INTENT(IN) :: op
    REAL(real64), INTENT(IN) :: b(:,:,:)
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    REAL(real64), INTENT(OUT) :: lambda(:,:,:)
    REAL(real64), INTENT(INOUT) :: work_u(:,:,:),work_v(:,:,:),work_o(:,:,:)
    INTEGER, INTENT(OUT) :: iterations,status,failure_reason
    REAL(real64), INTENT(OUT) :: final_rms,final_max
    REAL(real64), INTENT(IN), OPTIONAL :: reference_rms,reference_max
    REAL(real64), ALLOCATABLE :: r(:,:,:),p(:,:,:),lp(:,:,:),lr(:,:,:)
    REAL(real64) :: numerator,denom,alpha,beta,b_rms,b_max,r_rms,r_max
    REAL(real64) :: convergence_rms,convergence_max
    INTEGER :: operator_status

    ALLOCATE(r(op%nx,op%ny,op%nz),p(op%nx,op%ny,op%nz), &
             lp(op%nx,op%ny,op%nz),lr(op%nx,op%ny,op%nz))
    lambda=0.0_real64; r=b; iterations=0; status=STATUS_FAILED
    failure_reason=SOLVER_BREAKDOWN
    CALL continuity_norms(op,b,b_rms,b_max)
    final_rms=b_rms; final_max=b_max
    convergence_rms=b_rms; convergence_max=b_max
    IF (PRESENT(reference_rms) .OR. PRESENT(reference_max)) THEN
      IF (.NOT.(PRESENT(reference_rms) .AND. PRESENT(reference_max))) RETURN
      IF (.NOT.ieee_is_finite(reference_rms) .OR. .NOT.ieee_is_finite(reference_max) .OR. &
          reference_rms<0.0_real64 .OR. reference_max<0.0_real64) RETURN
      convergence_rms=reference_rms; convergence_max=reference_max
    END IF
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
      IF (solver_residual_converged(r_rms,r_max,convergence_rms,convergence_max,cfg)) THEN
        CALL refresh_true_residual(op,b,lambda,r,lr,work_u,work_v,work_o, &
                                   r_rms,r_max,operator_status)
        IF (operator_status/=STATUS_OK) RETURN
        final_rms=r_rms; final_max=r_max
        IF (solver_residual_converged(r_rms,r_max,convergence_rms,convergence_max,cfg)) THEN
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
        IF (solver_residual_converged(r_rms,r_max,convergence_rms,convergence_max,cfg)) THEN
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
    IF (solver_residual_converged(final_rms,final_max,convergence_rms,convergence_max,cfg)) THEN
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
    CALL remove_component_means(op,residual)
    CALL continuity_norms(op,residual,rms_value,max_value)
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

  SUBROUTINE state_dry_air_mass_flux_divergence(op,state,divergence,status)
    TYPE(balance_operator_type), INTENT(IN) :: op
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    REAL(real64), INTENT(OUT) :: divergence(:,:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), ALLOCATABLE :: fraction(:,:,:)
    INTEGER :: reason

    ! D F_d in kg/s for represented water, NOT dot(m_d)+D F_d or an analysis increment.
    ! Dry air follows the carrier velocity, without particle sedimentation.
    ! Keep the pressure-coordinate operator metric and its projection intact.
    divergence=0.0_real64; status=STATUS_FAILED
    IF (.NOT.diagnostic_operator_shapes_valid(op)) RETURN
    IF (ANY(SHAPE(divergence)/=(/op%nx,op%ny,op%nz/))) RETURN
    IF (state%grid%nx/=op%nx .OR. state%grid%ny/=op%ny .OR. state%grid%nz/=op%nz) RETURN
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) RETURN
    status=STATUS_FAILED
    IF (ANY(state%grid%pressure_mass_measure/=op%volume)) RETURN
    IF (ANY(state%grid%dx/=op%dx) .OR. ANY(state%grid%dy/=op%dy) .OR. &
        ANY(state%grid%cell_dp/=op%cell_dp)) RETURN
    ALLOCATE(fraction(op%nx,op%ny,op%nz))
    fraction=0.0_real64
    WHERE(state%above_ground)
      fraction=state%grid%dry_air_mass_measure/state%grid%pressure_mass_measure
    END WHERE
    CALL state_continuity_residual(op,state,divergence,status,fraction)
    IF (status/=STATUS_OK) THEN
      divergence=0.0_real64
      RETURN
    END IF
    divergence=divergence*op%volume
    IF (ANY(.NOT.ieee_is_finite(divergence))) THEN
      divergence=0.0_real64; status=STATUS_FAILED
    END IF
  END SUBROUTINE state_dry_air_mass_flux_divergence

  SUBROUTINE state_continuity_residual(op,state,residual,status,dry_air_fraction)
    TYPE(balance_operator_type), INTENT(IN) :: op
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    REAL(real64), INTENT(OUT) :: residual(:,:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), INTENT(IN), OPTIONAL :: dry_air_fraction(:,:,:)
    INTEGER :: i,j,k,s,k_top,k_bottom,left_level,right_level
    REAL(real64) :: area,flux,left_fraction,right_fraction

    residual=0.0_real64; status=STATUS_FAILED
    IF (.NOT.diagnostic_operator_shapes_valid(op)) RETURN
    IF (ANY(SHAPE(residual)/=(/op%nx,op%ny,op%nz/))) RETURN
    IF (PRESENT(dry_air_fraction)) THEN
      IF (ANY(SHAPE(dry_air_fraction)/=(/op%nx,op%ny,op%nz/))) RETURN
      IF (ANY(.NOT.ieee_is_finite(dry_air_fraction))) RETURN
      IF (ANY(dry_air_fraction<0.0_real64) .OR. ANY(dry_air_fraction>1.0_real64)) RETURN
    END IF
    IF (.NOT.field_storage_shape_valid(state%u,op%nx,op%ny,op%nz) .OR. &
        .NOT.field_storage_shape_valid(state%v,op%nx,op%ny,op%nz) .OR. &
        .NOT.field_storage_shape_valid(state%omega,op%nx,op%ny,op%nz)) RETURN
    IF (.NOT.boundary_contract_valid(state)) RETURN
    IF (ANY(op%cell_usable .AND. (.NOT.ieee_is_finite(state%u%value) .OR. &
        .NOT.ieee_is_finite(state%v%value) .OR. &
        .NOT.ieee_is_finite(state%omega%value)))) RETURN
    DO j=1,op%ny; DO i=1,op%nx-1
      DO s=op%xface_start(i,j),op%xface_start(i,j)+op%xface_count(i,j)-1
        left_level=op%xseg_left(s); right_level=op%xseg_right(s)
        IF (.NOT.(op%cell_usable(i,j,left_level) .AND. &
                  op%cell_usable(i+1,j,right_level))) CYCLE
        left_fraction=1.0_real64; right_fraction=1.0_real64
        IF (PRESENT(dry_air_fraction)) THEN
          left_fraction=dry_air_fraction(i,j,left_level)
          right_fraction=dry_air_fraction(i+1,j,right_level)
        END IF
        flux=op%xseg_area(s)*(op%xleft_weight(i,j,left_level)* &
          REAL(state%u%value(i,j,left_level),real64)*left_fraction+ &
          op%xright_weight(i,j,right_level)* &
          REAL(state%u%value(i+1,j,right_level),real64)*right_fraction)
        IF (op%cell_active(i,j,left_level)) &
          residual(i,j,left_level)=residual(i,j,left_level)+ &
            flux/op%volume(i,j,left_level)
        IF (op%cell_active(i+1,j,right_level)) &
          residual(i+1,j,right_level)=residual(i+1,j,right_level)- &
            flux/op%volume(i+1,j,right_level)
      END DO
    END DO; END DO
    DO j=1,op%ny-1; DO i=1,op%nx
      DO s=op%yface_start(i,j),op%yface_start(i,j)+op%yface_count(i,j)-1
        left_level=op%yseg_left(s); right_level=op%yseg_right(s)
        IF (.NOT.(op%cell_usable(i,j,left_level) .AND. &
                  op%cell_usable(i,j+1,right_level))) CYCLE
        left_fraction=1.0_real64; right_fraction=1.0_real64
        IF (PRESENT(dry_air_fraction)) THEN
          left_fraction=dry_air_fraction(i,j,left_level)
          right_fraction=dry_air_fraction(i,j+1,right_level)
        END IF
        flux=op%yseg_area(s)*(op%yleft_weight(i,j,left_level)* &
          REAL(state%v%value(i,j,left_level),real64)*left_fraction+ &
          op%yright_weight(i,j,right_level)* &
          REAL(state%v%value(i,j+1,right_level),real64)*right_fraction)
        IF (op%cell_active(i,j,left_level)) &
          residual(i,j,left_level)=residual(i,j,left_level)+ &
            flux/op%volume(i,j,left_level)
        IF (op%cell_active(i,j+1,right_level)) &
          residual(i,j+1,right_level)=residual(i,j+1,right_level)- &
            flux/op%volume(i,j+1,right_level)
      END DO
    END DO; END DO
    DO k=1,op%nz-1; DO j=1,op%ny; DO i=1,op%nx
      IF (.NOT.(op%cell_usable(i,j,k) .AND. op%cell_usable(i,j,k+1))) CYCLE
      left_fraction=1.0_real64; right_fraction=1.0_real64
      IF (PRESENT(dry_air_fraction)) THEN
        left_fraction=dry_air_fraction(i,j,k)
        right_fraction=dry_air_fraction(i,j,k+1)
      END IF
      flux=op%pface_area(i,j,k)*(op%pleft_weight(i,j,k)* &
        REAL(state%omega%value(i,j,k),real64)*left_fraction+op%pright_weight(i,j,k)* &
        REAL(state%omega%value(i,j,k+1),real64)*right_fraction)
      IF (op%cell_active(i,j,k+1)) &
        residual(i,j,k+1)=residual(i,j,k+1)+flux/op%volume(i,j,k+1)
      IF (op%cell_active(i,j,k)) &
        residual(i,j,k)=residual(i,j,k)-flux/op%volume(i,j,k)
    END DO; END DO; END DO
    ! Zero-gradient lateral boundary flux makes a uniform through-flow exactly
    ! divergence free.  Support-edge faces above use the immutable full state.
    ! Dry-fraction mode also extrapolates boundary composition from the nearest
    ! cell. This explicit donor assumption is not observed boundary composition.
    DO k=1,op%nz; DO j=1,op%ny
      IF (op%cell_active(1,j,k)) THEN
        area=op%dy(1,j)*op%cell_dp(1,j,k)/GRAVITY
        IF (PRESENT(dry_air_fraction)) area=area*dry_air_fraction(1,j,k)
        residual(1,j,k)=residual(1,j,k)-area* &
          REAL(state%u%value(1,j,k),real64)/op%volume(1,j,k)
      END IF
      IF (op%cell_active(op%nx,j,k)) THEN
        area=op%dy(op%nx,j)*op%cell_dp(op%nx,j,k)/GRAVITY
        IF (PRESENT(dry_air_fraction)) area=area*dry_air_fraction(op%nx,j,k)
        residual(op%nx,j,k)=residual(op%nx,j,k)+area* &
          REAL(state%u%value(op%nx,j,k),real64)/op%volume(op%nx,j,k)
      END IF
    END DO; END DO
    DO k=1,op%nz; DO i=1,op%nx
      IF (op%cell_active(i,1,k)) THEN
        area=op%dx(i,1)*op%cell_dp(i,1,k)/GRAVITY
        IF (PRESENT(dry_air_fraction)) area=area*dry_air_fraction(i,1,k)
        residual(i,1,k)=residual(i,1,k)-area* &
          REAL(state%v%value(i,1,k),real64)/op%volume(i,1,k)
      END IF
      IF (op%cell_active(i,op%ny,k)) THEN
        area=op%dx(i,op%ny)*op%cell_dp(i,op%ny,k)/GRAVITY
        IF (PRESENT(dry_air_fraction)) area=area*dry_air_fraction(i,op%ny,k)
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
        IF (PRESENT(dry_air_fraction)) flux=flux*dry_air_fraction(i,j,k_top)
        residual(i,j,k_top)=residual(i,j,k_top)-flux/op%volume(i,j,k_top)
      END IF
      IF (op%cell_active(i,j,k_bottom) .AND. state%omega_bottom_boundary%valid(i,j)) THEN
        flux=area*REAL(state%omega_bottom_boundary%value(i,j),real64)
        IF (PRESENT(dry_air_fraction)) flux=flux*dry_air_fraction(i,j,k_bottom)
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

  ! Diagnostic-only original/final pressure assessment.  This intentionally
  ! does not use the balance acceptance gate: it reports the same residual
  ! on one bounded support for the immutable input and final candidate.
  SUBROUTINE assess_pressure_geostrophic_change(background,candidate,config, &
                                                geopotential_support,support, &
                                                before_rms,after_rms,status,stencil_support, &
                                                allow_surface_pressure_geometry,transition_seed)
    TYPE(cloud_bal_state_type), INTENT(IN), TARGET :: background
    TYPE(cloud_bal_state_type), INTENT(IN) :: candidate
    TYPE(balance_operator_config), INTENT(IN) :: config
    LOGICAL, INTENT(IN) :: geopotential_support(:,:,:)
    LOGICAL, ALLOCATABLE, INTENT(OUT) :: support(:,:,:)
    REAL(real64), INTENT(OUT) :: before_rms,after_rms
    INTEGER, INTENT(OUT) :: status
    LOGICAL, ALLOCATABLE, INTENT(OUT), OPTIONAL :: stencil_support(:,:,:)
    LOGICAL, INTENT(IN), OPTIONAL :: allow_surface_pressure_geometry
    TYPE(cloud_bal_state_type), INTENT(IN), OPTIONAL :: transition_seed
    TYPE(balance_operator_type) :: op
    TYPE(cloud_bal_state_type), TARGET :: diagnostic_baseline
    TYPE(cloud_bal_state_type), POINTER :: diagnostic_reference
    INTEGER :: nx,ny,nz,state_status,state_reason,reason,i,j,k
    LOGICAL, ALLOCATABLE :: base_support(:,:,:),support_work(:,:,:),new_cells(:,:,:)
    LOGICAL, ALLOCATABLE :: wind_change_allowed(:,:,:)
    LOGICAL :: x_available,y_available,variable_geometry

    before_rms=0.0_real64
    after_rms=0.0_real64
    status=STATUS_FAILED
    nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
    IF (nx<1 .OR. ny<1 .OR. nz<2) RETURN
    IF (candidate%grid%nx/=nx .OR. candidate%grid%ny/=ny .OR. &
        candidate%grid%nz/=nz) RETURN
    IF (ANY(SHAPE(geopotential_support)/=(/nx,ny,nz/))) RETURN
    variable_geometry=.FALSE.
    IF (PRESENT(allow_surface_pressure_geometry)) &
      variable_geometry=allow_surface_pressure_geometry
    IF (PRESENT(transition_seed) .AND. .NOT.variable_geometry) RETURN

    CALL validate_canonical_state(background,.FALSE.,.FALSE.,state_status, &
                                  state_reason,.FALSE.)
    IF (state_status/=STATUS_OK) RETURN
    CALL validate_canonical_state(candidate,.FALSE.,.FALSE.,state_status, &
                                  state_reason,.FALSE.)
    IF (state_status/=STATUS_OK) RETURN
    ALLOCATE(new_cells(nx,ny,nz)); new_cells=.FALSE.
    IF (variable_geometry .AND. ANY(background%above_ground .NEQV. candidate%above_ground)) THEN
      IF (.NOT.pressure_geostrophic_transition_identity(background,candidate, &
                                                        new_cells)) RETURN
    ELSE
      IF (.NOT.pressure_geostrophic_fixed_identity(background,candidate, &
                                                    allow_surface_pressure_geometry)) RETURN
    END IF
    IF (ANY(new_cells)) THEN
      IF (.NOT.PRESENT(transition_seed)) RETURN
      IF (.NOT.transition_seed_selected_fields_valid(candidate, &
                                                     transition_seed,new_cells)) RETURN
    END IF
    IF (.NOT.config_valid(config)) RETURN
    IF (ANY(geopotential_support .AND. .NOT.candidate%above_ground)) RETURN
    IF (ANY(new_cells .AND. .NOT.geopotential_support)) RETURN

    ! The candidate operator supplies the canonical geometry and usability;
    ! only its diagnostic cell mask is changed below.
    CALL build_balance_operator(candidate,config,op,state_status,reason)
    IF (state_status/=STATUS_OK) RETURN
    ALLOCATE(wind_change_allowed(nx,ny,nz))
    wind_change_allowed=op%cell_active .OR. new_cells
    IF (field3d_changes_outside(background%u,candidate%u,wind_change_allowed) .OR. &
        field3d_changes_outside(background%v,candidate%v,wind_change_allowed)) RETURN
    IF (ALLOCATED(background%geopotential%value) .OR. &
        ALLOCATED(candidate%geopotential%value)) THEN
      IF (field3d_changes_outside(background%geopotential,candidate%geopotential, &
                                   geopotential_support)) RETURN
    END IF
    IF (ANY(new_cells .AND. .NOT.op%cell_active)) THEN
      IF (.NOT.transition_seed_new_winds_match(candidate,transition_seed, &
          new_cells .AND. .NOT.op%cell_active)) RETURN
    END IF

    ALLOCATE(base_support(nx,ny,nz))
    ALLOCATE(support_work(nx,ny,nz)); support_work=.FALSE.
    base_support=op%cell_active .OR. geopotential_support
    support_work=base_support
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.base_support(i,j,k)) CYCLE
      IF (i>1) support_work(i-1,j,k)=.TRUE.
      IF (i<nx) support_work(i+1,j,k)=.TRUE.
      IF (j>1) support_work(i,j-1,k)=.TRUE.
      IF (j<ny) support_work(i,j+1,k)=.TRUE.
    END DO; END DO; END DO
    support_work=support_work .AND. candidate%above_ground

    ! An empty diagnostic domain is a valid no-op.  In particular, do not
    ! turn geostrophic_residual's zero-sample failure into a false error.
    IF (.NOT.ANY(support_work)) THEN
      ALLOCATE(support(nx,ny,nz)); support=.FALSE.
      IF (PRESENT(stencil_support)) THEN
        ALLOCATE(stencil_support(nx,ny,nz)); stencil_support=.FALSE.
      END IF
      status=STATUS_OK
      RETURN
    END IF
    CALL validate_geostrophic_inputs(background,state_status,state_reason)
    IF (state_status/=STATUS_OK) RETURN
    CALL validate_geostrophic_inputs(candidate,state_status,state_reason)
    IF (state_status/=STATUS_OK) RETURN

    diagnostic_reference=>background
    IF (ANY(new_cells)) THEN
      ! Keep the candidate geometry and domain, but restore the immutable
      ! diagnostic fields from the original state on retained cells.  A seed
      ! is consulted only at newly represented centers; retained seed payload
      ! is deliberately opaque to this diagnostic.
      diagnostic_baseline=candidate
      diagnostic_baseline%geopotential=background%geopotential
      diagnostic_baseline%u=background%u
      diagnostic_baseline%v=background%v
      WHERE(new_cells)
        diagnostic_baseline%geopotential%value=transition_seed%geopotential%value
        diagnostic_baseline%geopotential%valid=transition_seed%geopotential%valid
        diagnostic_baseline%geopotential%quality=transition_seed%geopotential%quality
        diagnostic_baseline%geopotential%source=transition_seed%geopotential%source
        diagnostic_baseline%u%value=transition_seed%u%value
        diagnostic_baseline%u%valid=transition_seed%u%valid
        diagnostic_baseline%u%quality=transition_seed%u%quality
        diagnostic_baseline%u%source=transition_seed%u%source
        diagnostic_baseline%v%value=transition_seed%v%value
        diagnostic_baseline%v%valid=transition_seed%v%valid
        diagnostic_baseline%v%quality=transition_seed%v%quality
        diagnostic_baseline%v%source=transition_seed%v%source
      END WHERE
      diagnostic_reference=>diagnostic_baseline
    END IF
    IF (.NOT.pressure_geostrophic_center_winds_valid(diagnostic_reference,candidate, &
                                                     support_work)) RETURN
    ! Coverage is geometric, never permission to hide malformed requested data.
    IF (ANY(support_work .AND. .NOT.cell_is_usable(diagnostic_reference%geopotential%valid, &
        diagnostic_reference%geopotential%quality,diagnostic_reference%geopotential%source)) .OR. &
        ANY(support_work .AND. .NOT.cell_is_usable(candidate%geopotential%valid, &
        candidate%geopotential%quality,candidate%geopotential%source))) RETURN
    DO j=1,ny; DO i=1,nx
      IF (ANY(support_work(i,j,:)) .AND. .NOT.cell_is_usable(background%latitude%valid(i,j), &
          background%latitude%quality(i,j),background%latitude%source(i,j))) RETURN
    END DO; END DO

    ! This local operator is not used by the solver; changing only the
    ! diagnostic mask keeps the residual implementation and geometry shared.
    op%cell_active=support_work
    IF (PRESENT(stencil_support)) THEN
      ! Preserve the requested footprint. Only missing geometric neighbors
      ! can be unevaluable; malformed represented inputs still fail above.
      ALLOCATE(stencil_support(nx,ny,nz)); stencil_support=support_work
      DO k=1,nz; DO j=1,ny; DO i=1,nx
        IF (.NOT.support_work(i,j,k)) CYCLE
        x_available=.FALSE.; y_available=.FALSE.
        IF (i>1) x_available=x_available .OR. candidate%above_ground(i-1,j,k)
        IF (i<nx) x_available=x_available .OR. candidate%above_ground(i+1,j,k)
        IF (j>1) y_available=y_available .OR. candidate%above_ground(i,j-1,k)
        IF (j<ny) y_available=y_available .OR. candidate%above_ground(i,j+1,k)
        stencil_support(i,j,k)=x_available .AND. y_available
      END DO; END DO; END DO
      ! No samples is unavailable, not a zero-residual measurement.
      IF (.NOT.ANY(stencil_support)) THEN
        DEALLOCATE(stencil_support)
        RETURN
      END IF
      op%cell_active=stencil_support
    END IF
    CALL geostrophic_residual(diagnostic_reference,op,before_rms,state_status)
    IF (state_status/=STATUS_OK) THEN
      before_rms=0.0_real64
      after_rms=0.0_real64
      IF (PRESENT(stencil_support)) THEN
        IF (ALLOCATED(stencil_support)) DEALLOCATE(stencil_support)
      END IF
      RETURN
    END IF
    CALL geostrophic_residual(candidate,op,after_rms,state_status)
    IF (state_status/=STATUS_OK) THEN
      before_rms=0.0_real64
      after_rms=0.0_real64
      IF (PRESENT(stencil_support)) THEN
        IF (ALLOCATED(stencil_support)) DEALLOCATE(stencil_support)
      END IF
      RETURN
    END IF
    ALLOCATE(support(nx,ny,nz)); support=support_work
    status=STATUS_OK
  END SUBROUTINE assess_pressure_geostrophic_change

  LOGICAL FUNCTION pressure_geostrophic_transition_identity(left,right,new_cells)
    TYPE(cloud_bal_state_type), INTENT(IN) :: left,right
    LOGICAL, INTENT(OUT) :: new_cells(:,:,:)
    INTEGER :: nx,ny,nz,i,j,k,left_bottom,right_bottom
    REAL(real64) :: left_surface_pressure,right_surface_pressure

    pressure_geostrophic_transition_identity=.FALSE.
    new_cells=.FALSE.
    nx=left%grid%nx; ny=left%grid%ny; nz=left%grid%nz
    IF (right%grid%nx/=nx .OR. right%grid%ny/=ny .OR. right%grid%nz/=nz) RETURN
    IF (ANY(SHAPE(new_cells)/=(/nx,ny,nz/))) RETURN
    IF (left%schema_version/=right%schema_version .OR. &
        TRIM(left%grid%grid_id)/=TRIM(right%grid%grid_id)) RETURN
    ! The caller has already validated both canonical states and their storage.
    ! This private check covers only identities across the domain transition.
    IF (left%pressure%valid_time/=right%pressure%valid_time .OR. &
        TRIM(left%pressure%unit)/=TRIM(right%pressure%unit)) RETURN
    IF (ANY(left%grid%dx/=right%grid%dx) .OR. ANY(left%grid%dy/=right%grid%dy) .OR. &
        ANY(left%grid%level_spacing_dp/=right%grid%level_spacing_dp)) RETURN
    IF (ALLOCATED(left%latitude%value) .OR. ALLOCATED(right%latitude%value) .OR. &
        ALLOCATED(left%latitude%valid) .OR. ALLOCATED(right%latitude%valid) .OR. &
        ALLOCATED(left%latitude%quality) .OR. ALLOCATED(right%latitude%quality) .OR. &
        ALLOCATED(left%latitude%source) .OR. ALLOCATED(right%latitude%source)) THEN
      IF (.NOT.field2d_identity_equal(left%latitude,right%latitude)) RETURN
    END IF

    DO j=1,ny; DO i=1,nx
      left_bottom=FINDLOC(left%above_ground(i,j,:),.TRUE.,DIM=1)
      right_bottom=FINDLOC(right%above_ground(i,j,:),.TRUE.,DIM=1)
      IF (left_bottom<1 .OR. right_bottom<1) RETURN
      IF (left_bottom<right_bottom .OR. left_bottom-right_bottom>1) RETURN
      IF (right_bottom==left_bottom-1) THEN
        left_surface_pressure=REAL(left%surface_pressure%value(i,j),real64)
        right_surface_pressure=REAL(right%surface_pressure%value(i,j),real64)
        IF (right_surface_pressure<=left_surface_pressure .OR. &
            right_surface_pressure-left_surface_pressure>100.0_real64) RETURN
        new_cells(i,j,right_bottom)=.TRUE.
      END IF
    END DO; END DO
    IF (ANY(left%above_ground .AND. .NOT.right%above_ground)) RETURN

    ! Pressure centers are shared even when candidate surface pressure changes
    ! cell thickness.  Only newly represented cells may receive new pressure
    ! metadata; inactive retained metadata remains part of the identity.
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (TRANSFER(left%pressure%value(i,j,k),0_int32)/= &
          TRANSFER(right%pressure%value(i,j,k),0_int32)) RETURN
      IF (new_cells(i,j,k)) CYCLE
      IF ((left%pressure%valid(i,j,k).NEQV.right%pressure%valid(i,j,k)) .OR. &
          left%pressure%quality(i,j,k)/=right%pressure%quality(i,j,k) .OR. &
          left%pressure%source(i,j,k)/=right%pressure%source(i,j,k)) RETURN
    END DO; END DO; END DO
    pressure_geostrophic_transition_identity=.TRUE.
  END FUNCTION pressure_geostrophic_transition_identity

  LOGICAL FUNCTION transition_seed_selected_fields_valid(candidate,seed,new_cells)
    TYPE(cloud_bal_state_type), INTENT(IN) :: candidate,seed
    LOGICAL, INTENT(IN) :: new_cells(:,:,:)
    INTEGER :: nx,ny,nz,i,j,k

    transition_seed_selected_fields_valid=.FALSE.
    nx=candidate%grid%nx; ny=candidate%grid%ny; nz=candidate%grid%nz
    IF (seed%schema_version/=candidate%schema_version .OR. &
        seed%grid%nx/=nx .OR. seed%grid%ny/=ny .OR. seed%grid%nz/=nz .OR. &
        TRIM(seed%grid%grid_id)/=TRIM(candidate%grid%grid_id)) RETURN
    IF (.NOT.ALLOCATED(seed%above_ground)) RETURN
    IF (ANY(SHAPE(seed%above_ground)/=(/nx,ny,nz/)) .OR. &
        ANY(seed%above_ground .NEQV.candidate%above_ground)) RETURN
    IF (.NOT.ALLOCATED(seed%grid%dx) .OR. .NOT.ALLOCATED(seed%grid%dy) .OR. &
        .NOT.ALLOCATED(seed%grid%level_spacing_dp)) RETURN
    IF (ANY(SHAPE(seed%grid%dx)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(seed%grid%dy)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(seed%grid%level_spacing_dp)/=(/nx,ny,nz-1/))) RETURN
    IF (ANY(seed%grid%dx/=candidate%grid%dx) .OR. &
        ANY(seed%grid%dy/=candidate%grid%dy) .OR. &
        ANY(seed%grid%level_spacing_dp/=candidate%grid%level_spacing_dp)) RETURN
    IF (.NOT.field3d_shape_metadata_ok(seed%pressure,nx,ny,nz, &
                                       candidate%pressure%valid_time,'Pa') .OR. &
        .NOT.field3d_shape_metadata_ok(seed%geopotential,nx,ny,nz, &
                                       candidate%pressure%valid_time,'m2 s-2') .OR. &
        .NOT.field3d_shape_metadata_ok(seed%u,nx,ny,nz, &
                                       candidate%pressure%valid_time,'m s-1') .OR. &
        .NOT.field3d_shape_metadata_ok(seed%v,nx,ny,nz, &
                                       candidate%pressure%valid_time,'m s-1')) RETURN
    IF (.NOT.field2d_identity_equal(seed%latitude,candidate%latitude)) RETURN
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.new_cells(i,j,k)) CYCLE
      IF (.NOT.cell_is_usable(seed%pressure%valid(i,j,k),seed%pressure%quality(i,j,k), &
                              seed%pressure%source(i,j,k)) .OR. &
          .NOT.ieee_is_finite(seed%pressure%value(i,j,k))) RETURN
      IF (TRANSFER(seed%pressure%value(i,j,k),0_int32)/= &
          TRANSFER(candidate%pressure%value(i,j,k),0_int32)) RETURN
      IF ((seed%pressure%valid(i,j,k).NEQV.candidate%pressure%valid(i,j,k)) .OR. &
          seed%pressure%quality(i,j,k)/=candidate%pressure%quality(i,j,k) .OR. &
          IOR(seed%pressure%source(i,j,k),SOURCE_COLUMN_PHYSICS)/= &
            candidate%pressure%source(i,j,k)) RETURN
      IF (.NOT.cell_is_usable(seed%geopotential%valid(i,j,k), &
          seed%geopotential%quality(i,j,k),seed%geopotential%source(i,j,k)) .OR. &
          .NOT.ieee_is_finite(seed%geopotential%value(i,j,k)) .OR. &
          .NOT.cell_is_usable(seed%u%valid(i,j,k),seed%u%quality(i,j,k), &
                              seed%u%source(i,j,k)) .OR. &
          .NOT.ieee_is_finite(seed%u%value(i,j,k)) .OR. &
          .NOT.cell_is_usable(seed%v%valid(i,j,k),seed%v%quality(i,j,k), &
                              seed%v%source(i,j,k)) .OR. &
          .NOT.ieee_is_finite(seed%v%value(i,j,k))) RETURN
      IF (IAND(IOR(seed%geopotential%source(i,j,k), &
          IOR(seed%u%source(i,j,k),seed%v%source(i,j,k))),SOURCE_MANUFACTURED_TEST)/=0) RETURN
      IF (ABS(seed%u%value(i,j,k))>200.0_real32 .OR. &
          ABS(seed%v%value(i,j,k))>200.0_real32) RETURN
    END DO; END DO; END DO
    transition_seed_selected_fields_valid=.TRUE.
  END FUNCTION transition_seed_selected_fields_valid

  LOGICAL FUNCTION transition_seed_new_winds_match(candidate,seed,required)
    TYPE(cloud_bal_state_type), INTENT(IN) :: candidate,seed
    LOGICAL, INTENT(IN) :: required(:,:,:)
    INTEGER :: i,j,k
    transition_seed_new_winds_match=.FALSE.
    IF (.NOT.field3d_shape_metadata_ok(seed%u,candidate%grid%nx,candidate%grid%ny, &
        candidate%grid%nz,candidate%pressure%valid_time,'m s-1') .OR. &
        .NOT.field3d_shape_metadata_ok(seed%v,candidate%grid%nx,candidate%grid%ny, &
        candidate%grid%nz,candidate%pressure%valid_time,'m s-1')) RETURN
    IF (ANY(SHAPE(required)/=(/candidate%grid%nx,candidate%grid%ny,candidate%grid%nz/))) RETURN
    DO k=1,SIZE(required,3); DO j=1,SIZE(required,2); DO i=1,SIZE(required,1)
      IF (.NOT.required(i,j,k)) CYCLE
      IF (TRANSFER(seed%u%value(i,j,k),0_int32)/= &
          TRANSFER(candidate%u%value(i,j,k),0_int32) .OR. &
          TRANSFER(seed%v%value(i,j,k),0_int32)/= &
          TRANSFER(candidate%v%value(i,j,k),0_int32)) RETURN
    END DO; END DO; END DO
    transition_seed_new_winds_match=.TRUE.
  END FUNCTION transition_seed_new_winds_match

  LOGICAL FUNCTION field3d_changes_outside(left,right,allowed)
    TYPE(field3d), INTENT(IN) :: left,right
    LOGICAL, INTENT(IN) :: allowed(:,:,:)
    INTEGER :: i,j,k
    field3d_changes_outside=.FALSE.
    IF (.NOT.allocated(left%value) .OR. .NOT.allocated(right%value) .OR. &
        .NOT.allocated(left%valid) .OR. .NOT.allocated(right%valid) .OR. &
        .NOT.allocated(left%quality) .OR. .NOT.allocated(right%quality) .OR. &
        .NOT.allocated(left%source) .OR. .NOT.allocated(right%source)) THEN
      field3d_changes_outside=.TRUE.
      RETURN
    END IF
    IF (ANY(SHAPE(left%value)/=SHAPE(right%value)) .OR. &
        ANY(SHAPE(left%valid)/=SHAPE(right%valid)) .OR. &
        ANY(SHAPE(left%quality)/=SHAPE(right%quality)) .OR. &
        ANY(SHAPE(left%source)/=SHAPE(right%source)) .OR. &
        ANY(SHAPE(allowed)/=SHAPE(left%value))) THEN
      field3d_changes_outside=.TRUE.
      RETURN
    END IF
    DO k=1,SIZE(left%value,3); DO j=1,SIZE(left%value,2); DO i=1,SIZE(left%value,1)
      IF (allowed(i,j,k)) CYCLE
      IF (TRANSFER(left%value(i,j,k),0_int32)/=TRANSFER(right%value(i,j,k),0_int32) .OR. &
          (left%valid(i,j,k).NEQV.right%valid(i,j,k)) .OR. &
          left%quality(i,j,k)/=right%quality(i,j,k) .OR. &
          left%source(i,j,k)/=right%source(i,j,k)) THEN
        field3d_changes_outside=.TRUE.
        RETURN
      END IF
    END DO; END DO; END DO
  END FUNCTION field3d_changes_outside

  LOGICAL FUNCTION pressure_geostrophic_fixed_identity(left,right,allow_surface_pressure_geometry)
    TYPE(cloud_bal_state_type), INTENT(IN) :: left,right
    LOGICAL, INTENT(IN), OPTIONAL :: allow_surface_pressure_geometry
    LOGICAL :: variable_geometry
    pressure_geostrophic_fixed_identity=.FALSE.
    variable_geometry=.FALSE.
    IF (PRESENT(allow_surface_pressure_geometry)) variable_geometry=allow_surface_pressure_geometry
    IF (left%schema_version/=right%schema_version .OR. &
        left%grid%nx/=right%grid%nx .OR. left%grid%ny/=right%grid%ny .OR. &
        left%grid%nz/=right%grid%nz .OR. left%grid%grid_id/=right%grid%grid_id) RETURN
    IF (.NOT.allocated(left%above_ground) .OR. &
        .NOT.allocated(right%above_ground) .OR. &
        ANY(SHAPE(left%above_ground)/=SHAPE(right%above_ground)) .OR. &
        ANY(left%above_ground .NEQV. right%above_ground)) RETURN
    IF (.NOT.field3d_identity_equal(left%pressure,right%pressure)) RETURN
    IF (.NOT.variable_geometry) THEN
      IF (.NOT.field2d_identity_equal(left%surface_pressure,right%surface_pressure)) RETURN
    END IF
    IF (ALLOCATED(left%latitude%value) .OR. ALLOCATED(right%latitude%value) .OR. &
        ALLOCATED(left%latitude%valid) .OR. ALLOCATED(right%latitude%valid) .OR. &
        ALLOCATED(left%latitude%quality) .OR. ALLOCATED(right%latitude%quality) .OR. &
        ALLOCATED(left%latitude%source) .OR. ALLOCATED(right%latitude%source)) THEN
      IF (.NOT.field2d_identity_equal(left%latitude,right%latitude)) RETURN
    END IF
    IF (.NOT.allocated(left%grid%dx) .OR. .NOT.allocated(right%grid%dx) .OR. &
        .NOT.allocated(left%grid%dy) .OR. .NOT.allocated(right%grid%dy) .OR. &
        .NOT.allocated(left%grid%pressure_interface) .OR. &
        .NOT.allocated(right%grid%pressure_interface) .OR. &
        .NOT.allocated(left%grid%cell_dp) .OR. .NOT.allocated(right%grid%cell_dp) .OR. &
        .NOT.allocated(left%grid%level_spacing_dp) .OR. &
        .NOT.allocated(right%grid%level_spacing_dp) .OR. &
        .NOT.allocated(left%grid%pressure_mass_measure) .OR. &
        .NOT.allocated(right%grid%pressure_mass_measure)) RETURN
    IF (ANY(SHAPE(left%grid%dx)/=SHAPE(right%grid%dx)) .OR. &
        ANY(SHAPE(left%grid%dy)/=SHAPE(right%grid%dy)) .OR. &
        ANY(SHAPE(left%grid%pressure_interface)/= &
            SHAPE(right%grid%pressure_interface)) .OR. &
        ANY(SHAPE(left%grid%cell_dp)/=SHAPE(right%grid%cell_dp)) .OR. &
        ANY(SHAPE(left%grid%level_spacing_dp)/= &
            SHAPE(right%grid%level_spacing_dp)) .OR. &
        ANY(SHAPE(left%grid%pressure_mass_measure)/= &
            SHAPE(right%grid%pressure_mass_measure))) RETURN
    ! This diagnostic uses horizontal Phi gradients at unchanged pressure
    ! centers, not cell thickness or a mass-weighted norm. Canonical validation
    ! above still applies independently to both pressure geometries.
    IF (variable_geometry) THEN
      pressure_geostrophic_fixed_identity= &
        ALL(left%grid%dx==right%grid%dx) .AND. ALL(left%grid%dy==right%grid%dy) .AND. &
        ALL(left%grid%level_spacing_dp==right%grid%level_spacing_dp)
      RETURN
    END IF
    pressure_geostrophic_fixed_identity= &
      ALL(left%grid%dx==right%grid%dx) .AND. ALL(left%grid%dy==right%grid%dy) .AND. &
      ALL(left%grid%pressure_interface==right%grid%pressure_interface) .AND. &
      ALL(left%grid%cell_dp==right%grid%cell_dp) .AND. &
      ALL(left%grid%level_spacing_dp==right%grid%level_spacing_dp) .AND. &
      ALL(left%grid%pressure_mass_measure==right%grid%pressure_mass_measure)
  END FUNCTION pressure_geostrophic_fixed_identity

  LOGICAL FUNCTION field3d_identity_equal(left,right)
    TYPE(field3d), INTENT(IN) :: left,right
    field3d_identity_equal=.FALSE.
    IF (left%valid_time/=right%valid_time .OR. left%unit/=right%unit) RETURN
    IF (.NOT.allocated(left%value) .OR. .NOT.allocated(right%value) .OR. &
        .NOT.allocated(left%valid) .OR. .NOT.allocated(right%valid) .OR. &
        .NOT.allocated(left%quality) .OR. .NOT.allocated(right%quality) .OR. &
        .NOT.allocated(left%source) .OR. .NOT.allocated(right%source)) RETURN
    IF (ANY(SHAPE(left%value)/=SHAPE(right%value)) .OR. &
        ANY(SHAPE(left%valid)/=SHAPE(right%valid)) .OR. &
        ANY(SHAPE(left%quality)/=SHAPE(right%quality)) .OR. &
        ANY(SHAPE(left%source)/=SHAPE(right%source))) RETURN
    field3d_identity_equal=ALL(left%value==right%value) .AND. &
      ALL(left%valid .EQV. right%valid) .AND. &
      ALL(left%quality==right%quality) .AND. ALL(left%source==right%source)
  END FUNCTION field3d_identity_equal

  LOGICAL FUNCTION field2d_identity_equal(left,right)
    TYPE(field2d), INTENT(IN) :: left,right
    field2d_identity_equal=.FALSE.
    IF (left%valid_time/=right%valid_time .OR. left%unit/=right%unit) RETURN
    IF (.NOT.allocated(left%value) .OR. .NOT.allocated(right%value) .OR. &
        .NOT.allocated(left%valid) .OR. .NOT.allocated(right%valid) .OR. &
        .NOT.allocated(left%quality) .OR. .NOT.allocated(right%quality) .OR. &
        .NOT.allocated(left%source) .OR. .NOT.allocated(right%source)) RETURN
    IF (ANY(SHAPE(left%value)/=SHAPE(right%value)) .OR. &
        ANY(SHAPE(left%valid)/=SHAPE(right%valid)) .OR. &
        ANY(SHAPE(left%quality)/=SHAPE(right%quality)) .OR. &
        ANY(SHAPE(left%source)/=SHAPE(right%source))) RETURN
    field2d_identity_equal=ALL(left%value==right%value) .AND. &
      ALL(left%valid .EQV. right%valid) .AND. &
      ALL(left%quality==right%quality) .AND. ALL(left%source==right%source)
  END FUNCTION field2d_identity_equal

  LOGICAL FUNCTION pressure_geostrophic_center_winds_valid(background,candidate, &
                                                            support)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    LOGICAL, INTENT(IN) :: support(:,:,:)
    INTEGER :: i,j,k
    pressure_geostrophic_center_winds_valid=.FALSE.
    DO k=1,SIZE(support,3); DO j=1,SIZE(support,2); DO i=1,SIZE(support,1)
      IF (.NOT.support(i,j,k)) CYCLE
      IF (.NOT.(cell_is_usable(background%u%valid(i,j,k), &
          background%u%quality(i,j,k),background%u%source(i,j,k)) .AND. &
          cell_is_usable(background%v%valid(i,j,k), &
          background%v%quality(i,j,k),background%v%source(i,j,k)) .AND. &
          cell_is_usable(candidate%u%valid(i,j,k), &
          candidate%u%quality(i,j,k),candidate%u%source(i,j,k)) .AND. &
          cell_is_usable(candidate%v%valid(i,j,k), &
          candidate%v%quality(i,j,k),candidate%v%source(i,j,k)))) RETURN
    END DO; END DO; END DO
    pressure_geostrophic_center_winds_valid=.TRUE.
  END FUNCTION pressure_geostrophic_center_winds_valid

  SUBROUTINE validate_geostrophic_inputs(state,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: nx,ny,nz,i,j,k
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
        ANY(state%latitude%valid .AND. .NOT.ieee_is_finite(state%latitude%value))) THEN
      reason=REASON_NONFINITE; RETURN
    END IF
    ! Skip invalid cells before comparisons without a full-grid temporary.
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.state%geopotential%valid(i,j,k)) CYCLE
      IF (state%geopotential%value(i,j,k)<-10000.0_real32 .OR. &
          state%geopotential%value(i,j,k)>500000.0_real32) THEN
        reason=REASON_RANGE; RETURN
      END IF
    END DO; END DO; END DO
    DO j=1,ny; DO i=1,nx
      IF (.NOT.state%latitude%valid(i,j)) CYCLE
      IF (ABS(state%latitude%value(i,j))>90.0_real32) THEN
        reason=REASON_RANGE; RETURN
      END IF
    END DO; END DO
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
    INTEGER, ALLOCATABLE :: nodes(:)
    REAL(real64), ALLOCATABLE :: coefficient(:),coefficient_scale(:)
    INTEGER :: i,j,k,s,n,total,root,label,left_level,right_level

    total=op%nx*op%ny*op%nz
    ALLOCATE(parent(total),rank(total),root_label(total))
    ! At most nz rows in each adjacent column, plus the source cell itself.
    ALLOCATE(nodes(2*op%nz+1),coefficient(2*op%nz+1),coefficient_scale(2*op%nz+1))
    parent=0; rank=0; root_label=0
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (op%cell_active(i,j,k)) THEN
        root=linear_index(op,i,j,k)
        parent(root)=root
      END IF
    END DO; END DO; END DO

    ! Two residual cells are connected only when an actual A-grid degree of
    ! freedom has a nonzero coefficient in both rows of L=A*K*A^T*M.  A
    ! single horizontal degree of freedom can touch several cross-level
    ! segments, so duplicate row entries are accumulated before unioning.
    DO k=1,op%nz; DO j=1,op%ny; DO i=1,op%nx
      IF (op%ku(i,j,k)>0.0_real64) THEN
        n=0
        IF (i>1) THEN
          DO s=op%xface_start(i-1,j),op%xface_start(i-1,j)+ &
                op%xface_count(i-1,j)-1
            IF (.NOT.op%xseg_active(s) .OR. op%xseg_right(s)/=k) CYCLE
            left_level=op%xseg_left(s)
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i-1,j,left_level), &
               op%xseg_area(s)*op%xright_weight(i-1,j,k)/ &
               op%volume(i-1,j,left_level))
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i,j,k), &
              -op%xseg_area(s)*op%xright_weight(i-1,j,k)/op%volume(i,j,k))
          END DO
        END IF
        IF (i<op%nx) THEN
          DO s=op%xface_start(i,j),op%xface_start(i,j)+op%xface_count(i,j)-1
            IF (.NOT.op%xseg_active(s) .OR. op%xseg_left(s)/=k) CYCLE
            right_level=op%xseg_right(s)
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i,j,k), &
               op%xseg_area(s)*op%xleft_weight(i,j,k)/op%volume(i,j,k))
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i+1,j,right_level), &
              -op%xseg_area(s)*op%xleft_weight(i,j,k)/ &
               op%volume(i+1,j,right_level))
          END DO
        END IF
        CALL connect_stencil(parent,rank,nodes,coefficient,coefficient_scale,n)
      END IF

      IF (op%kv(i,j,k)>0.0_real64) THEN
        n=0
        IF (j>1) THEN
          DO s=op%yface_start(i,j-1),op%yface_start(i,j-1)+ &
                op%yface_count(i,j-1)-1
            IF (.NOT.op%yseg_active(s) .OR. op%yseg_right(s)/=k) CYCLE
            left_level=op%yseg_left(s)
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i,j-1,left_level), &
               op%yseg_area(s)*op%yright_weight(i,j-1,k)/ &
               op%volume(i,j-1,left_level))
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i,j,k), &
              -op%yseg_area(s)*op%yright_weight(i,j-1,k)/op%volume(i,j,k))
          END DO
        END IF
        IF (j<op%ny) THEN
          DO s=op%yface_start(i,j),op%yface_start(i,j)+op%yface_count(i,j)-1
            IF (.NOT.op%yseg_active(s) .OR. op%yseg_left(s)/=k) CYCLE
            right_level=op%yseg_right(s)
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i,j,k), &
               op%yseg_area(s)*op%yleft_weight(i,j,k)/op%volume(i,j,k))
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i,j+1,right_level), &
              -op%yseg_area(s)*op%yleft_weight(i,j,k)/ &
               op%volume(i,j+1,right_level))
          END DO
        END IF
        CALL connect_stencil(parent,rank,nodes,coefficient,coefficient_scale,n)
      END IF

      IF (op%ko(i,j,k)>0.0_real64) THEN
        n=0
        IF (k>1) THEN
          IF (op%pface_active(i,j,k-1)) THEN
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i,j,k-1), &
              -op%pface_area(i,j,k-1)*op%pright_weight(i,j,k-1)/ &
               op%volume(i,j,k-1))
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i,j,k), &
               op%pface_area(i,j,k-1)*op%pright_weight(i,j,k-1)/ &
               op%volume(i,j,k))
          END IF
        END IF
        IF (k<op%nz) THEN
          IF (op%pface_active(i,j,k)) THEN
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i,j,k), &
               -op%pface_area(i,j,k)*op%pleft_weight(i,j,k)/ &
               op%volume(i,j,k))
            CALL append_node(nodes,coefficient,coefficient_scale,n,linear_index(op,i,j,k+1), &
               op%pface_area(i,j,k)*op%pleft_weight(i,j,k)/op%volume(i,j,k+1))
          END IF
        END IF
        CALL connect_stencil(parent,rank,nodes,coefficient,coefficient_scale,n)
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

  SUBROUTINE append_node(nodes,coefficient,coefficient_scale,n,node,value)
    INTEGER, INTENT(INOUT) :: nodes(:)
    REAL(real64), INTENT(INOUT) :: coefficient(:),coefficient_scale(:)
    INTEGER, INTENT(INOUT) :: n
    INTEGER, INTENT(IN) :: node
    REAL(real64), INTENT(IN) :: value
    INTEGER :: m
    IF (value==0.0_real64) RETURN
    DO m=1,n
      IF (nodes(m)==node) THEN
        coefficient(m)=coefficient(m)+value
        coefficient_scale(m)=coefficient_scale(m)+ABS(value)
        RETURN
      END IF
    END DO
    n=n+1
    nodes(n)=node
    coefficient(n)=value
    coefficient_scale(n)=ABS(value)
  END SUBROUTINE append_node

  SUBROUTINE connect_stencil(parent,rank,nodes,coefficient,coefficient_scale,n)
    INTEGER, INTENT(INOUT) :: parent(:),rank(:)
    INTEGER, INTENT(IN) :: nodes(:),n
    REAL(real64), INTENT(IN) :: coefficient(:),coefficient_scale(:)
    INTEGER :: first,m
    first=0
    DO m=1,n
      ! Splitting one face into segments must not connect parity components
      ! solely through roundoff in a cancelling row sum.  This scale is local
      ! to that row's accumulated terms, not a target-response tolerance.
      IF (ABS(coefficient(m))<=64.0_real64*EPSILON(1.0_real64)*coefficient_scale(m)) CYCLE
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
    IF (.NOT.ieee_is_finite(floor_value) .OR. floor_value<0.0_real64 .OR. &
        .NOT.ieee_is_finite(minimum_ratio) .OR. &
        .NOT.ieee_is_finite(maximum_ratio) .OR. &
        maximum_ratio<minimum_ratio .OR. &
        ANY(op%cell_active .AND. (.NOT.ieee_is_finite(increment) .OR. &
                                  .NOT.ieee_is_finite(target)))) RETURN
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
        .NOT.ALLOCATED(state%grid%pressure_interface) .OR. &
        .NOT.ALLOCATED(state%grid%cell_dp) .OR. &
        .NOT.ALLOCATED(state%grid%level_spacing_dp) .OR. &
        .NOT.ALLOCATED(state%grid%pressure_mass_measure) .OR. &
        .NOT.ALLOCATED(state%above_ground) .OR. &
        .NOT.ALLOCATED(state%balance_beta)) RETURN
    IF (ANY(SHAPE(state%grid%dx)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(state%grid%dy)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(state%grid%pressure_interface)/=(/nx,ny,nz+1/)) .OR. &
        ANY(SHAPE(state%grid%cell_dp)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%grid%level_spacing_dp)/=(/nx,ny,nz-1/)) .OR. &
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
        .NOT.ALLOCATED(op%dy) .OR. .NOT.ALLOCATED(op%cell_dp) .OR. &
        .NOT.ALLOCATED(op%cell_usable) .OR. .NOT.ALLOCATED(op%cell_active) .OR. &
        .NOT.ALLOCATED(op%ku) .OR. .NOT.ALLOCATED(op%kv) .OR. &
        .NOT.ALLOCATED(op%ko) .OR. .NOT.ALLOCATED(op%omega_authorized) .OR. &
        .NOT.ALLOCATED(op%pface_active) .OR. &
        .NOT.ALLOCATED(op%xface_start) .OR. .NOT.ALLOCATED(op%xface_count) .OR. &
        .NOT.ALLOCATED(op%yface_start) .OR. .NOT.ALLOCATED(op%yface_count) .OR. &
        .NOT.ALLOCATED(op%xseg_left) .OR. .NOT.ALLOCATED(op%xseg_right) .OR. &
        .NOT.ALLOCATED(op%xseg_area) .OR. .NOT.ALLOCATED(op%xseg_active) .OR. &
        .NOT.ALLOCATED(op%yseg_left) .OR. .NOT.ALLOCATED(op%yseg_right) .OR. &
        .NOT.ALLOCATED(op%yseg_area) .OR. .NOT.ALLOCATED(op%yseg_active) .OR. &
        .NOT.ALLOCATED(op%xleft_weight) .OR. .NOT.ALLOCATED(op%xright_weight) .OR. &
        .NOT.ALLOCATED(op%yleft_weight) .OR. .NOT.ALLOCATED(op%yright_weight) .OR. &
        .NOT.ALLOCATED(op%pface_area) .OR. .NOT.ALLOCATED(op%pleft_weight) .OR. &
        .NOT.ALLOCATED(op%pright_weight)) RETURN
    IF (ANY(SHAPE(op%volume)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%dx)/=(/op%nx,op%ny/)) .OR. &
        ANY(SHAPE(op%dy)/=(/op%nx,op%ny/)) .OR. &
        ANY(SHAPE(op%cell_dp)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%cell_usable)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%cell_active)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%ku)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%kv)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%ko)/=(/op%nx,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%omega_authorized)/=(/op%nx,op%ny,op%nz/))) RETURN
    IF (ANY(SHAPE(op%xface_start)/=(/op%nx-1,op%ny/)) .OR. &
        ANY(SHAPE(op%xface_count)/=(/op%nx-1,op%ny/)) .OR. &
        ANY(SHAPE(op%yface_start)/=(/op%nx,op%ny-1/)) .OR. &
        ANY(SHAPE(op%yface_count)/=(/op%nx,op%ny-1/)) .OR. &
        ANY(SHAPE(op%xleft_weight)/=(/op%nx-1,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%xright_weight)/=(/op%nx-1,op%ny,op%nz/)) .OR. &
        ANY(SHAPE(op%yleft_weight)/=(/op%nx,op%ny-1,op%nz/)) .OR. &
        ANY(SHAPE(op%yright_weight)/=(/op%nx,op%ny-1,op%nz/))) RETURN
    IF (SIZE(op%xseg_left)/=SIZE(op%xseg_right) .OR. &
        SIZE(op%xseg_left)/=SIZE(op%xseg_area) .OR. &
        SIZE(op%xseg_left)/=SIZE(op%xseg_active) .OR. &
        SIZE(op%yseg_left)/=SIZE(op%yseg_right) .OR. &
        SIZE(op%yseg_left)/=SIZE(op%yseg_area) .OR. &
        SIZE(op%yseg_left)/=SIZE(op%yseg_active)) RETURN
    IF (ANY(SHAPE(op%pface_area)/=(/op%nx,op%ny,op%nz-1/)) .OR. &
        ANY(SHAPE(op%pface_active)/=(/op%nx,op%ny,op%nz-1/)) .OR. &
        ANY(SHAPE(op%pleft_weight)/=(/op%nx,op%ny,op%nz-1/)) .OR. &
        ANY(SHAPE(op%pright_weight)/=(/op%nx,op%ny,op%nz-1/))) RETURN
    diagnostic_operator_shapes_valid=.TRUE.
  END FUNCTION diagnostic_operator_shapes_valid

  ! Contents are checked once at construction; the PRIVATE arrays are immutable
  ! during the solve.  Per-application validation above checks only shapes.
  PURE LOGICAL FUNCTION lateral_segments_valid(op)
    TYPE(balance_operator_type), INTENT(IN) :: op
    INTEGER :: i,j
    lateral_segments_valid=.FALSE.
    IF (ANY(op%xface_start<1) .OR. ANY(op%xface_count<0) .OR. &
        ANY(op%yface_start<1) .OR. ANY(op%yface_count<0)) RETURN
    IF (ANY(op%xseg_left<1) .OR. ANY(op%xseg_left>op%nz) .OR. &
        ANY(op%xseg_right<1) .OR. ANY(op%xseg_right>op%nz) .OR. &
        ANY(op%yseg_left<1) .OR. ANY(op%yseg_left>op%nz) .OR. &
        ANY(op%yseg_right<1) .OR. ANY(op%yseg_right>op%nz) .OR. &
        ANY(op%xseg_area<=0.0_real64) .OR. ANY(op%yseg_area<=0.0_real64)) RETURN
    DO j=1,op%ny; DO i=1,op%nx-1
      IF (op%xface_start(i,j)+op%xface_count(i,j)-1>SIZE(op%xseg_left)) RETURN
    END DO; END DO
    DO j=1,op%ny-1; DO i=1,op%nx
      IF (op%yface_start(i,j)+op%yface_count(i,j)-1>SIZE(op%yseg_left)) RETURN
    END DO; END DO
    lateral_segments_valid=.TRUE.
  END FUNCTION lateral_segments_valid

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

  PURE LOGICAL FUNCTION physical_boundary_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    physical_boundary_contract_valid=boundary_contract_valid(state)
    IF (.NOT.physical_boundary_contract_valid) RETURN
    physical_boundary_contract_valid= &
      ALL(state%omega_top_boundary%quality==0_int32) .AND. &
      ALL(state%omega_bottom_boundary%quality==0_int32) .AND. &
      ALL(state%omega_top_boundary%source==SOURCE_BOUNDARY_CONDITION) .AND. &
      ALL(state%omega_bottom_boundary%source==SOURCE_BOUNDARY_CONDITION)
  END FUNCTION physical_boundary_contract_valid

  PURE LOGICAL FUNCTION model_boundary_increment_contract_valid(state_in,state_out)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in,state_out
    model_boundary_increment_contract_valid=.FALSE.
    IF (.NOT.boundary_contract_valid(state_in) .OR. &
        .NOT.boundary_contract_valid(state_out)) RETURN
    IF (state_in%omega_top_boundary%valid_time/= &
        state_out%omega_top_boundary%valid_time .OR. &
        state_in%omega_bottom_boundary%valid_time/= &
        state_out%omega_bottom_boundary%valid_time .OR. &
        state_in%omega_top_boundary%unit/=state_out%omega_top_boundary%unit .OR. &
        state_in%omega_bottom_boundary%unit/=state_out%omega_bottom_boundary%unit) RETURN
    model_boundary_increment_contract_valid= &
      ALL(state_in%omega_top_boundary%value==state_out%omega_top_boundary%value) .AND. &
      ALL(state_in%omega_bottom_boundary%value==state_out%omega_bottom_boundary%value) .AND. &
      ALL(state_in%omega_top_boundary%valid .EQV. state_out%omega_top_boundary%valid) .AND. &
      ALL(state_in%omega_bottom_boundary%valid .EQV. state_out%omega_bottom_boundary%valid) .AND. &
      ALL(state_in%omega_top_boundary%quality==state_out%omega_top_boundary%quality) .AND. &
      ALL(state_in%omega_bottom_boundary%quality==state_out%omega_bottom_boundary%quality) .AND. &
      ALL(state_in%omega_top_boundary%source==state_out%omega_top_boundary%source) .AND. &
      ALL(state_in%omega_bottom_boundary%source==state_out%omega_bottom_boundary%source)
  END FUNCTION model_boundary_increment_contract_valid

  PURE LOGICAL FUNCTION manufactured_boundary_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER(int32), PARAMETER :: expected_source = &
      IOR(SOURCE_BOUNDARY_CONDITION,SOURCE_MANUFACTURED_TEST)
    manufactured_boundary_contract_valid=boundary_contract_valid(state)
    IF (.NOT.manufactured_boundary_contract_valid) RETURN
    manufactured_boundary_contract_valid= &
      ALL(state%omega_top_boundary%quality==0_int32) .AND. &
      ALL(state%omega_bottom_boundary%quality==0_int32) .AND. &
      ALL(state%omega_top_boundary%value==0.0_real32) .AND. &
      ALL(state%omega_top_boundary%source==expected_source) .AND. &
      ALL(state%omega_bottom_boundary%source==expected_source)
  END FUNCTION manufactured_boundary_contract_valid

  PURE LOGICAL FUNCTION target_boundary_contract_valid(state,authority)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: authority
    SELECT CASE(authority)
    CASE(TARGET_AUTHORITY_OBSERVATIONAL)
      target_boundary_contract_valid=physical_boundary_contract_valid(state)
    CASE(TARGET_AUTHORITY_MANUFACTURED_TEST)
      target_boundary_contract_valid=manufactured_boundary_contract_valid(state)
    CASE(TARGET_AUTHORITY_MODEL_DYNAMICS)
      ! The model driver supplies an absolute interior target. Its correction
      ! preserves the existing baseline boundary values through the separate
      ! homogeneous increment contract; it never promotes an interior copy to
      ! SOURCE_BOUNDARY_CONDITION authority.
      target_boundary_contract_valid=boundary_contract_valid(state)
    CASE DEFAULT
      target_boundary_contract_valid=.FALSE.
    END SELECT
  END FUNCTION target_boundary_contract_valid

  PURE FUNCTION target_is_resolved(state,authority) RESULT(resolved)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: authority
    LOGICAL :: resolved(state%grid%nx,state%grid%ny,state%grid%nz)
    SELECT CASE(authority)
    CASE(TARGET_AUTHORITY_OBSERVATIONAL)
      resolved=observational_target_is_resolved(state)
    CASE(TARGET_AUTHORITY_MANUFACTURED_TEST)
      resolved=manufactured_target_is_resolved(state%omega_target%value, &
        state%omega%value,state%omega_target%valid, &
        state%omega_target%quality,state%omega_target%source)
    CASE(TARGET_AUTHORITY_MODEL_DYNAMICS)
      resolved=model_dynamic_target_is_resolved(state%omega_target%value, &
        state%omega_target%valid,state%omega_target%quality, &
        state%omega_target%source)
    CASE DEFAULT
      resolved=.FALSE.
    END SELECT
  END FUNCTION target_is_resolved

  PURE SUBROUTINE target_error_weight(background_variance,sigma,gain,posterior)
    REAL(real64), INTENT(IN) :: background_variance,sigma
    REAL(real64), INTENT(OUT) :: gain,posterior
    REAL(real64) :: observation_variance,ratio
    ! Complete the square in delta^2/B + (delta-innovation)^2/R.
    ! B includes the support taper; R is diagonal and sigma is one standard
    ! deviation. Branching avoids overflow in B+R or an extreme R/B ratio.
    observation_variance=sigma*sigma
    IF (background_variance>=observation_variance) THEN
      ratio=observation_variance/background_variance
      gain=1.0_real64/(1.0_real64+ratio)
      posterior=observation_variance/(1.0_real64+ratio)
    ELSE
      ratio=background_variance/observation_variance
      gain=ratio/(1.0_real64+ratio)
      posterior=background_variance/(1.0_real64+ratio)
    END IF
  END SUBROUTINE target_error_weight

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
    config_valid=(config%target_authority==TARGET_AUTHORITY_OBSERVATIONAL .OR. &
      config%target_authority==TARGET_AUTHORITY_MANUFACTURED_TEST .OR. &
      config%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) .AND. &
      (config%boundary_increment_contract==BOUNDARY_INCREMENT_BASELINE_FIXED .OR. &
       config%boundary_increment_contract==BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL) .AND. &
      ((config%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) .EQV. &
       (config%boundary_increment_contract==BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL)) .AND. &
      ieee_is_finite(config%kappa_u) .AND. config%kappa_u>0.0_real64 .AND. &
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
      ieee_is_finite(config%maximum_target_response_failure_fraction) .AND. &
      config%maximum_target_response_failure_fraction>=0.0_real64 .AND. &
      config%maximum_target_response_failure_fraction<=1.0_real64 .AND. &
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
