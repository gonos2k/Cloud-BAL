PROGRAM test_pressure_geostrophic_assessment
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  USE cloud_bal_balance_operator
  IMPLICIT NONE

  INTEGER :: failures

  failures=0
  CALL test_linear_phi_rms_and_support(failures)
  CALL test_empty_request_noop(failures)
  CALL test_partial_terrain_stencil_and_rms(failures)
  CALL test_zero_evaluable_partial_stencil_rejection(failures)
  CALL test_partial_terrain_invalid_phi_rejection(failures)
  CALL test_explicit_phi_support_without_target(failures)
  CALL test_equality_repeat_and_wind_authority(failures)
  CALL test_required_phi_metadata_rejection(failures)
  CALL test_phi_nonfinite_rejection(failures)
  CALL test_phi_shape_rejection(failures)
  CALL test_frame_and_geometry_rejection(failures)
  CALL test_surface_pressure_geometry_opt_in(failures)
  CALL test_transition_seed_geometry(failures)
  IF (failures/=0) THEN
    PRINT *,'Pressure geostrophic assessment tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Pressure geostrophic assessment tests passed'

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

  SUBROUTINE make_dry_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, PARAMETER :: nx=4,ny=4,nz=3
    INTEGER(int64), PARAMETER :: valid_time=1788224400_int64
    INTEGER :: status,i,j,k
    REAL(real64) :: phi

    CALL initialize_cloud_bal_state(state,nx,ny,nz,valid_time,'geo-assessment',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization failed'
    state%grid%dx=2048.0_real64
    state%grid%dy=2048.0_real64
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      state%pressure%value(i,j,k)=REAL(95000-15000*(k-1),real32)
      state%temperature%value(i,j,k)=280.0_real32
      state%vapor%value(i,j,k)=0.0_real32
      state%u%value(i,j,k)=10.0_real32
      state%v%value(i,j,k)=-5.0_real32
      state%omega%value(i,j,k)=0.0_real32
      ! The dyadic increments are exactly representable in real32.
      phi=100000.0_real64+512.0_real64*REAL(i-1,real64)- &
          1024.0_real64*REAL(j-1,real64)
      state%geopotential%value(i,j,k)=REAL(phi,real32)
    END DO; END DO; END DO
    CALL mark_valid(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%u,SOURCE_ANALYZED_WIND)
    CALL mark_valid(state%v,SOURCE_ANALYZED_WIND)
    CALL mark_valid(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%geopotential,SOURCE_BACKGROUND_MODEL)

    ! No resolved vertical target is present.  The diagnostic must still work
    ! for beta support and for an explicit geopotential support receipt.
    state%omega_target%valid=.FALSE.
    state%omega_target%quality=0_int32
    state%omega_target%source=0_int32
    state%omega_target_sigma%valid=.FALSE.
    state%omega_target_sigma%quality=0_int32
    state%omega_target_sigma%source=0_int32

    state%surface_pressure%value=100000.0_real32
    state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0_int32; state%surface_temperature%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%latitude%value=45.0_real32
    state%latitude%valid=.TRUE.; state%latitude%quality=0_int32
    state%latitude%source=SOURCE_BACKGROUND_MODEL
    state%omega_top_boundary%value=0.0_real32
    state%omega_bottom_boundary%value=0.0_real32
    state%omega_top_boundary%valid=.TRUE.; state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=0_int32; state%omega_bottom_boundary%quality=0_int32
    state%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    state%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION

    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure geometry initialization failed'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'dry mass initialization failed'
  END SUBROUTINE make_dry_state

  SUBROUTINE mark_valid(field,source_bit)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source_bit
    field%valid=.TRUE.; field%quality=0_int32; field%source=source_bit
  END SUBROUTINE mark_valid

  SUBROUTINE mark_valid_level(field,k,source_bit)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: k
    INTEGER(int32), INTENT(IN) :: source_bit
    field%valid(:,:,k)=.TRUE.
    field%quality(:,:,k)=0_int32
    field%source(:,:,k)=source_bit
  END SUBROUTINE mark_valid_level

  SUBROUTINE expected_halo(seed,support)
    LOGICAL, INTENT(IN) :: seed(:,:,:)
    LOGICAL, INTENT(OUT) :: support(:,:,:)
    INTEGER :: nx,ny,nz,i,j,k

    nx=SIZE(seed,1); ny=SIZE(seed,2); nz=SIZE(seed,3)
    support=.FALSE.
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.seed(i,j,k)) CYCLE
      support(i,j,k)=.TRUE.
      IF (i>1) support(i-1,j,k)=.TRUE.
      IF (i<nx) support(i+1,j,k)=.TRUE.
      IF (j>1) support(i,j-1,k)=.TRUE.
      IF (j<ny) support(i,j+1,k)=.TRUE.
    END DO; END DO; END DO
  END SUBROUTINE expected_halo

  SUBROUTINE expected_terrain_stencil(support,above_ground,stencil)
    LOGICAL, INTENT(IN) :: support(:,:,:),above_ground(:,:,:)
    LOGICAL, INTENT(OUT) :: stencil(:,:,:)
    INTEGER :: nx,ny,nz,i,j,k
    LOGICAL :: x_available,y_available

    nx=SIZE(support,1); ny=SIZE(support,2); nz=SIZE(support,3)
    stencil=.FALSE.
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.support(i,j,k)) CYCLE
      x_available=.FALSE.; y_available=.FALSE.
      IF (i>1) x_available=x_available .OR. above_ground(i-1,j,k)
      IF (i<nx) x_available=x_available .OR. above_ground(i+1,j,k)
      IF (j>1) y_available=y_available .OR. above_ground(i,j-1,k)
      IF (j<ny) y_available=y_available .OR. above_ground(i,j+1,k)
      stencil(i,j,k)=x_available .AND. y_available
    END DO; END DO; END DO
  END SUBROUTINE expected_terrain_stencil

  REAL(real64) FUNCTION independent_geostrophic_rms(state,mask)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    LOGICAL, INTENT(IN) :: mask(:,:,:)
    INTEGER :: nx,ny,nz,i,j,k,ix,jy,n
    REAL(real64) :: f,dphidx,dphidy,ru,rv,total,pi

    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    pi=ACOS(-1.0_real64)
    total=0.0_real64; n=0
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.mask(i,j,k)) CYCLE
      ix=0
      IF (i<nx) THEN
        IF (state%above_ground(i+1,j,k)) ix=i+1
      END IF
      IF (ix==0 .AND. i>1) THEN
        IF (state%above_ground(i-1,j,k)) ix=i-1
      END IF
      jy=0
      IF (j<ny) THEN
        IF (state%above_ground(i,j+1,k)) jy=j+1
      END IF
      IF (jy==0 .AND. j>1) THEN
        IF (state%above_ground(i,j-1,k)) jy=j-1
      END IF
      IF (ix==0 .OR. jy==0) THEN
        independent_geostrophic_rms=HUGE(1.0_real64)
        RETURN
      END IF
      f=1.458423e-4_real64*SIN(REAL(state%latitude%value(i,j),real64)*pi/180.0_real64)
      dphidx=(REAL(state%geopotential%value(ix,j,k),real64)- &
              REAL(state%geopotential%value(i,j,k),real64))/ &
             (REAL(ix-i,real64)*0.5_real64* &
              (state%grid%dx(i,j)+state%grid%dx(ix,j)))
      dphidy=(REAL(state%geopotential%value(i,jy,k),real64)- &
              REAL(state%geopotential%value(i,j,k),real64))/ &
             (REAL(jy-j,real64)*0.5_real64* &
              (state%grid%dy(i,j)+state%grid%dy(i,jy)))
      ru=-f*REAL(state%v%value(i,j,k),real64)+dphidx
      rv= f*REAL(state%u%value(i,j,k),real64)+dphidy
      total=total+ru*ru+rv*rv
      n=n+2
    END DO; END DO; END DO
    IF (n==0) THEN
      independent_geostrophic_rms=0.0_real64
    ELSE
      independent_geostrophic_rms=SQRT(total/REAL(n,real64))
    END IF
  END FUNCTION independent_geostrophic_rms

  SUBROUTINE make_partial_terrain_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    LOGICAL :: terrain_domain(4,4,3)
    INTEGER :: status

    CALL make_dry_state(state)
    ! At level 2, the west shell cell has no usable north/south neighbor;
    ! the other four shell cells remain evaluable.
    state%above_ground=.TRUE.
    state%above_ground(1,1,1:2)=.FALSE.
    state%above_ground(1,3,1:2)=.FALSE.
    state%surface_pressure%value(1,1)=70000.0_real32
    state%surface_pressure%value(1,3)=70000.0_real32
    terrain_domain=state%above_ground
    CALL configure_pressure_geometry(state,status,terrain_domain)
    IF (status/=STATUS_OK) ERROR STOP 'partial terrain geometry initialization failed'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'partial terrain mass initialization failed'
  END SUBROUTINE make_partial_terrain_state

  SUBROUTINE make_single_cell_terrain_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    LOGICAL :: terrain_domain(4,4,3)
    INTEGER :: status

    CALL make_dry_state(state)
    state%above_ground=.FALSE.
    state%above_ground(:,:,3)=.TRUE.
    state%above_ground(2,2,2)=.TRUE.
    state%surface_pressure%value=70000.0_real32
    state%surface_pressure%value(2,2)=85000.0_real32
    terrain_domain=state%above_ground
    CALL configure_pressure_geometry(state,status,terrain_domain)
    IF (status/=STATUS_OK) ERROR STOP 'single-cell terrain geometry initialization failed'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'single-cell terrain mass initialization failed'
  END SUBROUTINE make_single_cell_terrain_state

  REAL(real64) FUNCTION analytic_rms()
    REAL(real64) :: f,ru,rv
    f=1.458423e-4_real64*SIN(45.0_real64*ACOS(-1.0_real64)/180.0_real64)
    ru=5.0_real64*f+0.25_real64
    rv=10.0_real64*f-0.50_real64
    analytic_rms=SQRT(0.5_real64*(ru*ru+rv*rv))
  END FUNCTION analytic_rms

  SUBROUTINE test_empty_request_noop(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3),outputs_ready
    LOGICAL, ALLOCATABLE :: support(:,:,:),stencil(:,:,:)
    REAL(real64) :: before,after
    INTEGER :: status

    CALL make_dry_state(background); candidate=background; request=.FALSE.
    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      support,before,after,status)
    CALL check(status==STATUS_OK .AND. ALLOCATED(support) .AND. &
      COUNT(support)==0 .AND. before==0.0_real64 .AND. after==0.0_real64, &
      'empty strict diagnostic request remains a successful no-op',failures)

    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      support,before,after,status,stencil)
    outputs_ready=ALLOCATED(support) .AND. ALLOCATED(stencil)
    CALL check(status==STATUS_OK .AND. outputs_ready .AND. &
      before==0.0_real64 .AND. after==0.0_real64, &
      'empty optional diagnostic request remains a successful no-op',failures)
    IF (outputs_ready) THEN
      CALL check(COUNT(support)==0 .AND. COUNT(stencil)==0, &
        'empty optional request returns empty support and stencil masks',failures)
    END IF
  END SUBROUTINE test_empty_request_noop

  SUBROUTINE test_partial_terrain_stencil_and_rms(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3),expected_support(4,4,3),expected_stencil(4,4,3)
    LOGICAL, ALLOCATABLE :: strict_support(:,:,:),support(:,:,:),stencil(:,:,:)
    LOGICAL :: outputs_ready
    REAL(real64) :: strict_before,strict_after,before,after
    REAL(real64) :: expected_before,expected_after
    INTEGER :: strict_status,status

    CALL make_partial_terrain_state(background)
    candidate=background
    request=.FALSE.; request(2,2,2)=.TRUE.
    ! The requested center is an allowed Phi change.  The west shell cell is
    ! deliberately outside the optional stencil because it lacks a y neighbor.
    candidate%geopotential%value(2,2,2)= &
      candidate%geopotential%value(2,2,2)+1024.0_real32
    CALL expected_halo(request,expected_support)
    expected_support=expected_support .AND. background%above_ground
    CALL expected_terrain_stencil(expected_support,background%above_ground, &
      expected_stencil)
    expected_before=independent_geostrophic_rms(background,expected_stencil)
    expected_after=independent_geostrophic_rms(candidate,expected_stencil)

    ! The original call contract remains strict: any requested shell cell
    ! without an x/y neighbor rejects the entire assessment.
    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      strict_support,strict_before,strict_after,strict_status)
    CALL check(strict_status==STATUS_FAILED .AND. .NOT.ALLOCATED(strict_support) .AND. &
      strict_before==0.0_real64 .AND. strict_after==0.0_real64, &
      'strict legacy call rejects partial terrain with an unevaluable shell cell',failures)

    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      support,before,after,status,stencil)
    outputs_ready=ALLOCATED(support) .AND. ALLOCATED(stencil)
    CALL check(status==STATUS_OK .AND. outputs_ready, &
      'optional partial-terrain assessment succeeds with evaluable cells',failures)
    IF (outputs_ready) THEN
      CALL check(ALL(support .EQV. expected_support) .AND. &
        ALL(stencil .EQV. expected_stencil), &
        'optional support preserves the full terrain-clipped request shell and filters its stencil',failures)
      CALL check(COUNT(support)==5 .AND. COUNT(stencil)==4 .AND. &
        .NOT.stencil(1,2,2), &
        'partial terrain retains five requested-shell cells but evaluates four',failures)
      CALL check(ABS(before-expected_before)<2.0e-10_real64 .AND. &
        ABS(after-expected_after)<2.0e-10_real64, &
        'partial-terrain RMS matches an independent finite-difference expectation',failures)
    END IF
  END SUBROUTINE test_partial_terrain_stencil_and_rms

  SUBROUTINE test_zero_evaluable_partial_stencil_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3)
    LOGICAL, ALLOCATABLE :: support(:,:,:),stencil(:,:,:)
    REAL(real64) :: before,after
    INTEGER :: status

    CALL make_single_cell_terrain_state(background)
    candidate=background; request=.FALSE.; request(2,2,2)=.TRUE.
    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      support,before,after,status,stencil)
    CALL check(status==STATUS_FAILED .AND. .NOT.ALLOCATED(support) .AND. &
      before==0.0_real64 .AND. after==0.0_real64, &
      'nonempty terrain request with zero evaluable cells is rejected',failures)
    IF (ALLOCATED(stencil)) THEN
      CALL check(.NOT.ANY(stencil), &
        'zero-evaluable request does not publish a false zero-residual stencil',failures)
    END IF
  END SUBROUTINE test_zero_evaluable_partial_stencil_rejection

  SUBROUTINE test_partial_terrain_invalid_phi_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3)
    LOGICAL, ALLOCATABLE :: support(:,:,:),stencil(:,:,:)
    REAL(real64) :: before,after
    INTEGER :: status

    CALL make_partial_terrain_state(background)
    background%geopotential%valid(1,2,2)=.FALSE.
    candidate=background; request=.FALSE.; request(2,2,2)=.TRUE.
    ! The west shell cell is unevaluable geometrically, but malformed Phi
    ! there must still reject the optional assessment.  Both states carry
    ! the same malformed cell, so this tests usability rather than change
    ! authorization.
    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      support,before,after,status,stencil)
    CALL check(status==STATUS_FAILED .AND. .NOT.ALLOCATED(support) .AND. &
      before==0.0_real64 .AND. after==0.0_real64, &
      'invalid geopotential metadata in an unevaluable shell cell is rejected',failures)
  END SUBROUTINE test_partial_terrain_invalid_phi_rejection



  SUBROUTINE test_linear_phi_rms_and_support(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3),expected(4,4,3)
    LOGICAL, ALLOCATABLE :: support(:,:,:)
    REAL(real64) :: before,after
    INTEGER :: status

    CALL make_dry_state(background)
    candidate=background
    request=.FALSE.
    background%balance_beta=0.0_real32
    background%balance_beta(2,2,2)=1.0_real32
    candidate%balance_beta=background%balance_beta
    CALL expected_halo(background%balance_beta>cfg%minimum_beta,expected)
    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request,support,before,after,status)
    CALL check(status==STATUS_OK,'linear-Phi assessment succeeds',failures)
    CALL check(ALLOCATED(support) .AND. ALL(support.EQV.expected), &
      'balance-active support receives a four-neighbor same-level halo',failures)
    CALL check(ABS(before-analytic_rms())<2.0e-10_real64 .AND. &
      ABS(after-before)<2.0e-10_real64, &
      'uniform-wind linear-Phi RMS matches the analytic residual',failures)
  END SUBROUTINE test_linear_phi_rms_and_support

  SUBROUTINE test_explicit_phi_support_without_target(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3),expected(4,4,3)
    LOGICAL, ALLOCATABLE :: support(:,:,:),repeat_support(:,:,:)
    REAL(real64) :: before,after,repeat_before,repeat_after
    INTEGER :: status,repeat_status

    CALL make_dry_state(background)
    candidate=background
    background%balance_beta=0.0_real32
    candidate%balance_beta=0.0_real32
    request=.FALSE.; request(2,2,2)=.TRUE.
    candidate%geopotential%value(2,2,2)=candidate%geopotential%value(2,2,2)+1024.0_real32
    CALL expected_halo(request,expected)
    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request,support,before,after,status)
    CALL check(status==STATUS_OK,'explicit-Phi no-target assessment succeeds',failures)
    CALL check(ALLOCATED(support) .AND. ALL(support.EQV.expected), &
      'explicit Phi support is retained when beta and target are zero',failures)
    CALL check(after>before,'diagnostic permits a geostrophic residual increase',failures)

    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request,repeat_support,repeat_before, &
      repeat_after,repeat_status)
    CALL check(repeat_status==STATUS_OK .AND. ALL(repeat_support.EQV.support) .AND. &
      repeat_before==before .AND. repeat_after==after, &
      'repeated diagnostic call is deterministic',failures)
  END SUBROUTINE test_explicit_phi_support_without_target

  SUBROUTINE test_equality_repeat_and_wind_authority(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,saved_background,saved_candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3),expected(4,4,3)
    LOGICAL, ALLOCATABLE :: support(:,:,:)
    REAL(real64) :: before,after
    INTEGER :: status

    CALL make_dry_state(background)
    candidate=background
    background%balance_beta=0.0_real32
    candidate%balance_beta=0.0_real32
    request=.FALSE.; request(2,2,2)=.TRUE.
    saved_background=background; saved_candidate=candidate
    CALL expected_halo(request,expected)
    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request,support,before,after,status)
    CALL check(status==STATUS_OK .AND. ALL(support.EQV.expected), &
      'unchanged states retain explicit diagnostic support only',failures)
    CALL check(canonical_states_equal(background,saved_background) .AND. &
      canonical_states_equal(candidate,saved_candidate), &
      'assessment does not mutate either input state',failures)
    background%geopotential%value(4,4,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    background%geopotential%valid(4,4,1)=.FALSE.
    candidate=background
    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request,support,before,after,status)
    CALL check(status==STATUS_OK, &
      'unchanged invalid Phi outside diagnostic stencil is preserved',failures)
    candidate%u%value(4,4,1)=150.0_real32
    CALL expect_rejection(background,candidate,cfg,request, &
      'wind changes outside declared balance support cannot be hidden',failures)
    candidate%u%source(4,4,1)=IOR(candidate%u%source(4,4,1),SOURCE_COLUMN_PHYSICS)
    CALL expect_rejection(background,candidate,cfg,request, &
      'simultaneous outside wind value and source changes are rejected',failures)
  END SUBROUTINE test_equality_repeat_and_wind_authority

  SUBROUTINE expect_rejection(background,candidate,cfg,request,message,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(IN) :: request(:,:,:)
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    LOGICAL, ALLOCATABLE :: support(:,:,:)
    REAL(real64) :: before,after
    INTEGER :: status

    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request,support,before,after,status)
    CALL check(status==STATUS_FAILED .AND. .NOT.ALLOCATED(support) .AND. &
      before==0.0_real64 .AND. after==0.0_real64,message,failures)
  END SUBROUTINE expect_rejection

  SUBROUTINE test_required_phi_metadata_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3)

    CALL make_dry_state(background); candidate=background; request=.FALSE.
    candidate%geopotential%valid=.FALSE.
    request(2,2,2)=.TRUE.
    CALL expect_rejection(background,candidate,cfg,request, &
      'missing required geopotential metadata is rejected',failures)
  END SUBROUTINE test_required_phi_metadata_rejection

  SUBROUTINE test_phi_nonfinite_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3)

    CALL make_dry_state(background); candidate=background; request=.FALSE.
    request(2,2,2)=.TRUE.
    candidate%geopotential%value(2,2,2)=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL expect_rejection(background,candidate,cfg,request, &
      'nonfinite geopotential is rejected',failures)
  END SUBROUTINE test_phi_nonfinite_rejection

  SUBROUTINE test_phi_shape_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3)
    LOGICAL :: bad_request(4,4,2)

    CALL make_dry_state(background); candidate=background; request=.FALSE.
    request(2,2,2)=.TRUE.
    DEALLOCATE(candidate%geopotential%value)
    ALLOCATE(candidate%geopotential%value(4,4,2))
    candidate%geopotential%value=0.0_real32
    CALL expect_rejection(background,candidate,cfg,request, &
      'geopotential storage shape mismatch is rejected',failures)

    candidate=background; bad_request=.FALSE.; bad_request(2,2,2)=.TRUE.
    CALL expect_rejection(background,candidate,cfg,bad_request, &
      'geopotential support shape mismatch is rejected',failures)
  END SUBROUTINE test_phi_shape_rejection

  SUBROUTINE test_frame_and_geometry_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3)

    CALL make_dry_state(background); request=.FALSE.; request(2,2,2)=.TRUE.
    candidate=background; candidate%geopotential%unit='unknown'
    CALL expect_rejection(background,candidate,cfg,request, &
      'unknown geopotential frame is rejected',failures)

    candidate=background; candidate%grid%dx(2,2)=candidate%grid%dx(2,2)+1.0_real64
    CALL expect_rejection(background,candidate,cfg,request, &
      'candidate geometry mismatch is rejected',failures)
  END SUBROUTINE test_frame_and_geometry_rejection

  SUBROUTINE test_surface_pressure_geometry_opt_in(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3)
    LOGICAL, ALLOCATABLE :: reference_support(:,:,:),support(:,:,:)
    REAL(real64) :: reference_before,reference_after,before,after
    INTEGER :: status

    CALL make_dry_state(background)
    request=.FALSE.; request(2,2,2)=.TRUE.
    candidate=background
    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      reference_support,reference_before,reference_after,status)
    CALL check(status==STATUS_OK .AND. ALLOCATED(reference_support), &
      'fixed-geometry reference assessment succeeds',failures)

    ! A canonical +20 Pa surface-pressure change has regenerated geometry,
    ! but unchanged pressure centers, spacing, Phi, and winds.
    candidate=background
    candidate%surface_pressure%value=candidate%surface_pressure%value+20.0_real32
    CALL configure_pressure_geometry(candidate,status)
    IF (status/=STATUS_OK) ERROR STOP 'surface-pressure geometry regeneration failed'
    CALL refresh_dry_air_mass_measure(candidate,status)
    IF (status/=STATUS_OK) ERROR STOP 'surface-pressure dry mass regeneration failed'
    CALL check(ANY(candidate%surface_pressure%value/=background%surface_pressure%value) .AND. &
      ANY(candidate%grid%cell_dp/=background%grid%cell_dp) .AND. &
      ALL(candidate%grid%level_spacing_dp==background%grid%level_spacing_dp), &
      'surface-pressure fixture changes only the intended geometry',failures)

    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      support,before,after,status)
    CALL check(status==STATUS_FAILED .AND. .NOT.ALLOCATED(support) .AND. &
      before==0.0_real64 .AND. after==0.0_real64, &
      'surface-pressure geometry remains rejected by the default contract',failures)

    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      support,before,after,status,allow_surface_pressure_geometry=.TRUE.)
    CALL check(status==STATUS_OK .AND. ALLOCATED(support) .AND. &
      ALL(support.EQV.reference_support), &
      'explicit surface-pressure geometry opt-in accepts canonical geometry',failures)
    CALL check(ABS(before-reference_before)<2.0e-10_real64 .AND. &
      ABS(after-reference_after)<2.0e-10_real64, &
      'surface-pressure opt-in preserves horizontal geostrophic residuals',failures)

    candidate=background
    candidate%surface_pressure%value=candidate%surface_pressure%value-20.0_real32
    CALL configure_pressure_geometry(candidate,status)
    IF (status/=STATUS_OK) ERROR STOP 'negative surface-pressure geometry failed'
    CALL refresh_dry_air_mass_measure(candidate,status)
    IF (status/=STATUS_OK) ERROR STOP 'negative surface-pressure mass failed'
    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      support,before,after,status,allow_surface_pressure_geometry=.TRUE.)
    CALL check(status==STATUS_OK .AND. ABS(before-reference_before)<2.0e-10_real64 .AND. &
      ABS(after-reference_after)<2.0e-10_real64, &
      'same-domain negative pressure changes retain existing diagnostic behavior',failures)

    candidate=background
    candidate%pressure%value=candidate%pressure%value+10.0_real32
    CALL configure_pressure_geometry(candidate,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure-center geometry regeneration failed'
    CALL refresh_dry_air_mass_measure(candidate,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure-center dry mass regeneration failed'
    CALL expect_variable_geometry_rejection(background,candidate,cfg,request, &
      'explicit opt-in rejects changed pressure centers',failures)

    candidate=background
    candidate%grid%dx(2,2)=candidate%grid%dx(2,2)+1.0_real64
    CALL configure_pressure_geometry(candidate,status)
    IF (status/=STATUS_OK) ERROR STOP 'grid-spacing geometry regeneration failed'
    CALL refresh_dry_air_mass_measure(candidate,status)
    IF (status/=STATUS_OK) ERROR STOP 'grid-spacing dry mass regeneration failed'
    CALL expect_variable_geometry_rejection(background,candidate,cfg,request, &
      'explicit opt-in rejects changed grid spacing',failures)

    candidate=background
    candidate%grid%cell_dp(2,2,1)=0.0_real64
    CALL expect_variable_geometry_rejection(background,candidate,cfg,request, &
      'explicit opt-in rejects malformed pressure geometry',failures)
  END SUBROUTINE test_surface_pressure_geometry_opt_in

  SUBROUTINE make_transition_geometry_states(original,seed,candidate)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: original,seed,candidate
    LOGICAL :: terrain_domain(4,4,3)
    INTEGER :: status,i,j
    REAL(real64) :: phi

    CALL make_dry_state(original)
    original%surface_pressure%value=94950.0_real32
    original%above_ground(:,:,1)=.FALSE.
    terrain_domain=original%above_ground
    CALL configure_pressure_geometry(original,status,terrain_domain)
    IF (status/=STATUS_OK) ERROR STOP 'transition original geometry failed'
    CALL refresh_dry_air_mass_measure(original,status)
    IF (status/=STATUS_OK) ERROR STOP 'transition original mass failed'
    original%pressure%valid(:,:,1)=.FALSE.
    original%pressure%source(:,:,1)=0_int32

    ! These are represented placeholders in the original subterrain layer.
    original%geopotential%value(:,:,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    original%geopotential%valid(:,:,1)=.FALSE.
    original%geopotential%quality(:,:,1)=0_int32
    original%geopotential%source(:,:,1)=0_int32
    original%u%value(:,:,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    original%u%valid(:,:,1)=.FALSE.
    original%u%quality(:,:,1)=0_int32
    original%u%source(:,:,1)=0_int32
    original%v%value(:,:,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    original%v%valid(:,:,1)=.FALSE.
    original%v%quality(:,:,1)=0_int32
    original%v%source(:,:,1)=0_int32

    seed=original
    CALL mark_valid_level(seed%pressure,1,SOURCE_BACKGROUND_MODEL)
    seed%surface_pressure%value=95025.0_real32
    CALL configure_pressure_geometry(seed,status)
    IF (status/=STATUS_OK) ERROR STOP 'transition seed geometry failed'
    CALL refresh_dry_air_mass_measure(seed,status)
    IF (status/=STATUS_OK) ERROR STOP 'transition seed mass failed'
    DO j=1,4; DO i=1,4
      phi=100000.0_real64+512.0_real64*REAL(i-1,real64)- &
          1024.0_real64*REAL(j-1,real64)
      seed%geopotential%value(i,j,1)=REAL(phi,real32)
      seed%u%value(i,j,1)=10.0_real32
      seed%v%value(i,j,1)=-5.0_real32
    END DO; END DO
    CALL mark_valid_level(seed%geopotential,1,SOURCE_COLUMN_PHYSICS)
    CALL mark_valid_level(seed%u,1,SOURCE_COLUMN_PHYSICS)
    CALL mark_valid_level(seed%v,1,SOURCE_COLUMN_PHYSICS)

    ! The seed is authoritative only for newly active cells. Poison all
    ! retained cells to prove the diagnostic uses the original baseline there.
    seed%geopotential%value(:,:,2:)=ieee_value(0.0_real32,ieee_quiet_nan)
    seed%geopotential%valid(:,:,2:)=.FALSE.
    seed%geopotential%quality(:,:,2:)=0_int32
    seed%geopotential%source(:,:,2:)=0_int32
    seed%u%value(:,:,2:)=ieee_value(0.0_real32,ieee_quiet_nan)
    seed%u%valid(:,:,2:)=.FALSE.
    seed%u%quality(:,:,2:)=0_int32
    seed%u%source(:,:,2:)=0_int32
    seed%v%value(:,:,2:)=ieee_value(0.0_real32,ieee_quiet_nan)
    seed%v%valid(:,:,2:)=.FALSE.
    seed%v%quality(:,:,2:)=0_int32
    seed%v%source(:,:,2:)=0_int32

    candidate=seed
    candidate%pressure%source(:,:,1)=IOR(seed%pressure%source(:,:,1),SOURCE_COLUMN_PHYSICS)
    candidate%geopotential%value(:,:,2:)=original%geopotential%value(:,:,2:)
    candidate%geopotential%valid(:,:,2:)=original%geopotential%valid(:,:,2:)
    candidate%geopotential%quality(:,:,2:)=original%geopotential%quality(:,:,2:)
    candidate%geopotential%source(:,:,2:)=original%geopotential%source(:,:,2:)
    candidate%u%value(:,:,2:)=original%u%value(:,:,2:)
    candidate%u%valid(:,:,2:)=original%u%valid(:,:,2:)
    candidate%u%quality(:,:,2:)=original%u%quality(:,:,2:)
    candidate%u%source(:,:,2:)=original%u%source(:,:,2:)
    candidate%v%value(:,:,2:)=original%v%value(:,:,2:)
    candidate%v%valid(:,:,2:)=original%v%valid(:,:,2:)
    candidate%v%quality(:,:,2:)=original%v%quality(:,:,2:)
    candidate%v%source(:,:,2:)=original%v%source(:,:,2:)
    CALL configure_pressure_geometry(candidate,status)
    IF (status/=STATUS_OK) ERROR STOP 'transition candidate geometry failed'
    CALL refresh_dry_air_mass_measure(candidate,status)
    IF (status/=STATUS_OK) ERROR STOP 'transition candidate mass failed'
  END SUBROUTINE make_transition_geometry_states

  SUBROUTINE expect_transition_rejection(original,candidate,seed,cfg,request,message,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: original,candidate,seed
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(IN) :: request(:,:,:)
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    LOGICAL, ALLOCATABLE :: support(:,:,:),stencil(:,:,:)
    REAL(real64) :: before,after
    INTEGER :: status

    CALL assess_pressure_geostrophic_change(original,candidate,cfg,request, &
      support,before,after,status,stencil,allow_surface_pressure_geometry=.TRUE., &
      transition_seed=seed)
    CALL check(status==STATUS_FAILED .AND. .NOT.ALLOCATED(support) .AND. &
      before==0.0_real64 .AND. after==0.0_real64,message,failures)
  END SUBROUTINE expect_transition_rejection

  SUBROUTINE test_transition_seed_geometry(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: original,seed,candidate
    TYPE(cloud_bal_state_type) :: saved_original,saved_seed,saved_candidate,bad_seed
    TYPE(cloud_bal_state_type) :: changed
    TYPE(balance_operator_config) :: cfg
    LOGICAL :: request(4,4,3),missing_request(4,4,3)
    LOGICAL, ALLOCATABLE :: support(:,:,:),stencil(:,:,:)
    REAL(real64) :: before,after
    INTEGER :: status

    CALL make_transition_geometry_states(original,seed,candidate)
    request=.FALSE.; request(:,:,1:2)=.TRUE.
    saved_original=original; saved_seed=seed; saved_candidate=candidate
    CALL assess_pressure_geostrophic_change(original,candidate,cfg,request, &
      support,before,after,status,stencil,allow_surface_pressure_geometry=.TRUE., &
      transition_seed=seed)
    CALL check(status==STATUS_OK .AND. ALLOCATED(support) .AND. ALLOCATED(stencil), &
      'transition seed assessment accepts one-cell-per-column domain growth',failures)
    IF (status==STATUS_OK .AND. ALLOCATED(support) .AND. ALLOCATED(stencil)) THEN
      CALL check(COUNT(support)==32 .AND. COUNT(stencil)==32 .AND. &
        ALL(support(:,:,1:2)) .AND. ALL(stencil(:,:,1:2)) .AND. &
        .NOT.ANY(support(:,:,3)), &
        'transition support includes the requested added and retained layers',failures)
      CALL check(ABS(before-analytic_rms())<2.0e-10_real64 .AND. &
        ABS(after-analytic_rms())<2.0e-10_real64, &
        'transition RMS uses original retained and seed new-cell linear Phi',failures)
      PRINT '(A,1X,ES24.16,A,1X,ES24.16,A,I0,A,I0,A,I0)', &
        'transition geostrophic RMS before=',before,' after=',after, &
        ' requested=',COUNT(request),' support=',COUNT(support), &
        ' stencil=',COUNT(stencil)
    END IF
    CALL check(canonical_states_equal(original,saved_original) .AND. &
      canonical_states_equal(seed,saved_seed) .AND. &
      canonical_states_equal(candidate,saved_candidate), &
      'transition assessment does not mutate original, seed, or candidate',failures)

    CALL assess_pressure_geostrophic_change(original,candidate,cfg,request, &
      support,before,after,status,stencil,transition_seed=seed)
    CALL check(status==STATUS_FAILED .AND. .NOT.ALLOCATED(support), &
      'transition geometry requires explicit surface-pressure opt-in',failures)

    CALL assess_pressure_geostrophic_change(original,candidate,cfg,request, &
      support,before,after,status,stencil,allow_surface_pressure_geometry=.TRUE.)
    CALL check(status==STATUS_FAILED .AND. .NOT.ALLOCATED(support), &
      'transition geometry requires a transition seed',failures)

    bad_seed=seed
    bad_seed%geopotential%valid(1,1,1)=.FALSE.
    bad_seed%geopotential%quality(1,1,1)=0_int32
    bad_seed%geopotential%source(1,1,1)=0_int32
    bad_seed%geopotential%value(1,1,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL expect_transition_rejection(original,candidate,bad_seed,cfg,request, &
      'missing new-cell seed geopotential is rejected',failures)
    bad_seed=seed
    bad_seed%u%valid(2,2,1)=.FALSE.
    bad_seed%u%quality(2,2,1)=0_int32
    bad_seed%u%source(2,2,1)=0_int32
    CALL expect_transition_rejection(original,candidate,bad_seed,cfg,request, &
      'missing new-cell seed wind is rejected',failures)
    bad_seed=seed
    DEALLOCATE(bad_seed%above_ground)
    CALL expect_transition_rejection(original,candidate,bad_seed,cfg,request, &
      'unallocated seed domain is rejected without indexing it',failures)
    bad_seed=seed
    bad_seed%pressure%source(2,2,1)=SOURCE_ANALYZED_WIND
    CALL expect_transition_rejection(original,candidate,bad_seed,cfg,request, &
      'new-cell pressure provenance must match the seed',failures)
    bad_seed=seed
    bad_seed%u%source(2,2,1)=IOR(SOURCE_COLUMN_PHYSICS,SOURCE_MANUFACTURED_TEST)
    CALL expect_transition_rejection(original,candidate,bad_seed,cfg,request, &
      'manufactured seed wind is not an observational reference',failures)

    changed=candidate
    changed%geopotential%value(2,2,3)=changed%geopotential%value(2,2,3)+256.0_real32
    CALL expect_transition_rejection(original,changed,seed,cfg,request, &
      'retained geopotential changes outside support cannot be hidden',failures)
    changed=candidate
    changed%u%value(2,2,3)=changed%u%value(2,2,3)+1.0_real32
    CALL expect_transition_rejection(original,changed,seed,cfg,request, &
      'retained wind changes outside support cannot be hidden',failures)

    missing_request=.FALSE.; missing_request(1,1,2)=.TRUE.
    CALL expect_transition_rejection(original,candidate,seed,cfg,missing_request, &
      'omitted new-cell geopotential support is rejected',failures)

    changed=candidate
    changed%surface_pressure%value=95025.0_real32+125.0_real32
    CALL configure_pressure_geometry(changed,status)
    IF (status/=STATUS_OK) ERROR STOP 'large transition geometry failed'
    CALL refresh_dry_air_mass_measure(changed,status)
    IF (status/=STATUS_OK) ERROR STOP 'large transition mass failed'
    CALL expect_transition_rejection(original,changed,seed,cfg,request, &
      'surface-pressure transition above 100 Pa is rejected',failures)

    changed=candidate
    changed%surface_pressure%value=94950.0_real32
    CALL configure_pressure_geometry(changed,status)
    IF (status/=STATUS_OK) ERROR STOP 'removal geometry failed'
    CALL refresh_dry_air_mass_measure(changed,status)
    IF (status/=STATUS_OK) ERROR STOP 'removal mass failed'
    CALL expect_transition_rejection(original,changed,seed,cfg,request, &
      'removal of an original or seeded bottom cell is rejected',failures)
  END SUBROUTINE test_transition_seed_geometry

  SUBROUTINE expect_variable_geometry_rejection(background,candidate,cfg,request, &
                                                message,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(balance_operator_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(IN) :: request(:,:,:)
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    LOGICAL, ALLOCATABLE :: support(:,:,:)
    REAL(real64) :: before,after
    INTEGER :: status

    CALL assess_pressure_geostrophic_change(background,candidate,cfg,request, &
      support,before,after,status,allow_surface_pressure_geometry=.TRUE.)
    CALL check(status==STATUS_FAILED .AND. .NOT.ALLOCATED(support) .AND. &
      before==0.0_real64 .AND. after==0.0_real64,message,failures)
  END SUBROUTINE expect_variable_geometry_rejection

END PROGRAM test_pressure_geostrophic_assessment
