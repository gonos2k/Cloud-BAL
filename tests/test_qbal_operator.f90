PROGRAM test_qbal_operator
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite, ieee_value, ieee_quiet_nan
  IMPLICIT NONE

  EXTERNAL :: continuity_metrics,continuity_point,leib_sub
  EXTERNAL :: leibp3
  EXTERNAL :: qbal_continuity_row
  EXTERNAL :: qbal_component_check
  EXTERNAL :: geostrophic_residual_metrics
  REAL*8, EXTERNAL :: qbal_row_value
  REAL*8, EXTERNAL :: qbal_divergence_value

  INTEGER, PARAMETER :: nx=6, ny=6, nz=4
  INTEGER :: i, j, k, status, failures
  REAL :: u0(nx,ny,nz), v0(nx,ny,nz), om0(nx,ny,nz)
  REAL :: u1(nx,ny,nz), v1(nx,ny,nz), om1(nx,ny,nz)
  REAL :: ulocal0(nx,ny,nz), vlocal0(nx,ny,nz), omlocal0(nx,ny,nz)
  REAL :: om_background(nx,ny,nz), phi(nx,ny,nz)
  REAL :: erru(nx,ny,nz), tau(nx,ny), lat(nx,ny)
  REAL :: influence(nx,ny,nz), local_influence(nx,ny,nz)
  REAL :: scaled_influence(nx,ny,nz)
  REAL :: bad_tau(nx,ny)
  REAL :: dx(nx,ny), dy(nx,ny), ps(nx,ny), p(nz), dp(nz), bad_dp(nz)
  REAL :: before_rms, after_rms, before_max, after_max, geostrophic_rms
  REAL :: scaled_rms, scaled_max
  REAL :: residual, erf, bnd, pi

  failures = 0
  bnd = 1.0E-30
  pi = ACOS(-1.0)
  dx = 10000.0
  dy = 10000.0
  ps = 101000.0
  p = (/100000.0, 85000.0, 70000.0, 50000.0/)
  dp = (/15000.0, 15000.0, 15000.0, 20000.0/)
  lat = 36.0
  phi = 0.0
  u0 = 0.0
  v0 = 0.0
  om0 = 0.0
  om_background = 0.0
  influence = 1.0

  DO k=1,nz
    DO j=1,ny
      DO i=1,nx
        erru(i,j,k) = 0.8 + 0.05*REAL(i) + 0.03*REAL(j)
        u0(i,j,k) = SIN(2.0*pi*REAL(i-1)/REAL(nx-1))
      END DO
    END DO
  END DO
  DO j=1,ny
    DO i=1,nx
      tau(i,j) = 3.0 + 0.1*REAL(i+j)
    END DO
  END DO
  ! The production projection now freezes exterior correction faces.  Keep
  ! this manufactured forcing in the closed operator range by zeroing its
  ! prescribed outer normal fluxes.
  u0(1,:,:) = 0.0
  u0(nx,:,:) = 0.0
  u1 = u0
  v1 = v0
  om1 = om0

  CALL continuity_metrics(u0,v0,om0,nx,ny,nz,dx,dy,ps,p,dp,influence, &
       before_rms,before_max,status)
  CALL check(status == 1 .AND. before_rms > 0.0, &
       'initial continuity residual should be measurable', failures)
  scaled_influence = 1.0E-3
  CALL continuity_metrics(u0,v0,om0,nx,ny,nz,dx,dy,ps,p,dp, &
       scaled_influence,scaled_rms,scaled_max,status)
  CALL check(status==1 .AND. ABS(scaled_rms-before_rms)<1.0E-12 .AND. &
       ABS(scaled_max-before_max)<1.0E-12, &
       'beta must mask, not attenuate, physical continuity residual',failures)

  erf = 0.01*dx(nx/2,ny/2)
  CALL leib_sub(nx,ny,nz,erf,tau,erru,influence,lat,dx,dy,ps,p,dp, &
       u0,u1,v0,v1,om0,om1,om_background,1,1,status)
  CALL check(status == 1, &
       'flux-form continuity solver should converge', failures)
  CALL continuity_metrics(u1,v1,om1,nx,ny,nz,dx,dy,ps,p,dp,influence, &
       after_rms,after_max,status)
  CALL check(status == 1, &
       'corrected continuity residual should be measurable', failures)
  CALL check(after_rms <= before_rms*(1.0+1.0E-4)+1.0E-10, &
       'continuity correction must not worsen the shared residual', failures)

  local_influence = 0.0
  ! The stored face coefficients use the lower i/j face index.  A one-cell
  ! authority halo supplies the interior faces for this compact 3x3x2 block;
  ! the row mask still begins at (2,2,2), and exterior normal faces stay frozen.
  local_influence(1:4,1:4,2:3) = 1.0
  ulocal0 = 0.0
  vlocal0 = 0.0
  omlocal0 = 0.0
  ulocal0(2,:,2:3) = 1.0
  ulocal0(3,:,2:3) = -1.0
  u1 = ulocal0
  v1 = vlocal0
  om1 = omlocal0
  CALL leib_sub(nx,ny,nz,erf,tau,erru,local_influence,lat,dx,dy, &
       ps,p,dp,ulocal0,u1,vlocal0,v1,omlocal0,om1,om_background, &
       1,1,status)
  CALL check(status == 1, 'localized continuity solve should converge', &
       failures)
  CALL check(MAXVAL(ABS(u1(5:6,:,:)-ulocal0(5:6,:,:)))<TINY(1.0) .AND. &
       MAXVAL(ABS(v1(5:6,:,:)-vlocal0(5:6,:,:)))<TINY(1.0) .AND. &
       MAXVAL(ABS(om1(5:6,:,:)-omlocal0(5:6,:,:)))<TINY(1.0), &
       'increments outside compact support must be exactly zero',failures)

  bad_dp = dp
  bad_dp(2) = 0.0
  CALL continuity_point(u0,v0,om0,nx,ny,nz,dx,dy,bad_dp, &
       2,2,2,residual,status)
  CALL check(status == 0, 'zero pressure thickness must fail', failures)

  bad_tau = tau
  bad_tau(3,3) = 0.0
  u1 = u0
  v1 = v0
  om1 = om0
  CALL leib_sub(nx,ny,nz,erf,bad_tau,erru,influence,lat,dx,dy,ps,p,dp, &
       u0,u1,v0,v1,om0,om1,om_background,1,1,status)
  CALL check(status == 0, 'zero tau must fail without publishing', failures)

  u0(2,1,1) = bnd
  CALL continuity_point(u0,v0,om0,nx,ny,nz,dx,dy,dp, &
       2,2,2,residual,status)
  CALL check(status == 2, &
       'terrain/boundary mask must be skipped, not treated as failure', failures)
  u0(2,1,1) = 0.0

  CALL geostrophic_residual_metrics(phi,v0,v0,nx,ny,nz,lat,dx,dy, &
       ps,p,influence,geostrophic_rms,status)
  CALL check(status == 1 .AND. ABS(geostrophic_rms) < 1.0E-12, &
       'zero state should have zero geostrophic residual', failures)
  DO k=1,nz
    DO j=1,ny
      DO i=1,nx
        phi(i,j,k)=10.0*REAL(i)
      END DO
    END DO
  END DO
  CALL geostrophic_residual_metrics(phi,v0,v0,nx,ny,nz,lat,dx,dy, &
       ps,p,influence,geostrophic_rms,status)
  CALL geostrophic_residual_metrics(phi,v0,v0,nx,ny,nz,lat,dx,dy, &
       ps,p,scaled_influence,scaled_rms,status)
  CALL check(status==1 .AND. ABS(scaled_rms-geostrophic_rms)<1.0E-12, &
       'beta must mask, not attenuate, geostrophic residual',failures)
  phi(2,2,2) = ieee_value(0.0, ieee_quiet_nan)
  CALL geostrophic_residual_metrics(phi,v0,v0,nx,ny,nz,lat,dx,dy, &
       ps,p,influence,geostrophic_rms,status)
  CALL check(status == 0, &
       'non-finite active geostrophic input must fail', failures)
  phi = 0.0
  lat = 0.0
  CALL geostrophic_residual_metrics(phi,v0,v0,nx,ny,nz,lat,dx,dy, &
       ps,p,influence,geostrophic_rms,status)
  CALL check(status == 0, &
       'out-of-range near-zero Coriolis support must fail', failures)

  CALL test_leibp3_scale_guard(failures)
  CALL test_component_detailed_balance(failures)

  IF (failures /= 0) THEN
    PRINT *, 'QBAL operator unit tests failed:', failures
    ERROR STOP 1
  END IF
  PRINT *, 'QBAL operator unit tests passed; continuity RMS ', &
           before_rms, after_rms

CONTAINS

  SUBROUTINE check(condition, message, failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT. condition) THEN
      failures = failures + 1
      PRINT *, 'FAIL: ', TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE test_leibp3_scale_guard(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL*8 :: lambda_ref(nx+1,ny+1,nz+1), lambda_tiny(nx+1,ny+1,nz+1)
    REAL*8 :: rhs_ref(nx+1,ny+1,nz+1), rhs_tiny(nx+1,ny+1,nz+1)
    REAL*8 :: cx_ref(nx,ny,nz), cy_ref(nx,ny,nz), cp_ref(nx,ny,nz)
    REAL*8 :: cx_tiny(nx,ny,nz), cy_tiny(nx,ny,nz), cp_tiny(nx,ny,nz)
    REAL*8 :: target(nx+1,ny+1,nz+1), c(6)
    LOGICAL :: active(nx+1,ny+1,nz+1)
    REAL :: tiny_max, ref_max, max_relative
    REAL :: nan_value
    INTEGER :: scale_status, zero_status, tiny_status, reject_status
    INTEGER :: finite_status
    INTEGER :: ii, jj, kk

    dx = 5061.267
    dy = 5061.267
    dp = (/15000.0, 15000.0, 15000.0, 20000.0/)
    active = .FALSE.
    active(2:nx,2:ny,2:nz) = .TRUE.
    lambda_ref = 0.0D0
    lambda_tiny = 0.0D0
    rhs_ref = 0.0D0
    rhs_tiny = 0.0D0
    cx_ref = 1.0D0
    cy_ref = 1.0D0
    cp_ref = 1.0D0
    cx_ref(1,:,:) = 0.0D0
    cx_ref(nx,:,:) = 0.0D0
    cx_ref(:,ny,:) = 0.0D0
    cx_ref(:,:,nz) = 0.0D0
    cy_ref(:,1,:) = 0.0D0
    cy_ref(:,ny,:) = 0.0D0
    cy_ref(nx,:,:) = 0.0D0
    cy_ref(:,:,nz) = 0.0D0
    cp_ref(:,:,1) = 0.0D0
    cp_ref(:,:,nz) = 0.0D0
    cx_tiny = 1.0D-14*cx_ref
    cy_tiny = 1.0D-14*cy_ref
    cp_tiny = 1.0D-14*cp_ref
    target = 0.0D0
    DO kk=1,nz+1
      DO jj=1,ny+1
        DO ii=1,nx+1
          target(ii,jj,kk) = 7.0D0*REAL(ii) - 3.0D0*REAL(jj) + &
               5.0D0*REAL(kk) + 0.2D0*REAL(ii*jj)
        END DO
      END DO
    END DO
    DO kk=2,nz
      DO jj=2,ny
        DO ii=2,nx
          CALL qbal_continuity_row(cx_ref,cy_ref,cp_ref,nx,ny,nz,dx,dy,dp, &
               ii,jj,kk,c)
          rhs_ref(ii,jj,kk) = qbal_row_value(target,nx,ny,nz,ii,jj,kk,c)
          rhs_tiny(ii,jj,kk) = 1.0D-14*rhs_ref(ii,jj,kk)
        END DO
      END DO
    END DO

    CALL leibp3(lambda_ref,rhs_ref,1,1.0,active,cx_ref,cy_ref,cp_ref, &
         nx,ny,nz,dx,dy,dp,scale_status)
    CALL leibp3(lambda_tiny,rhs_tiny,1,1.0,active,cx_tiny,cy_tiny,cp_tiny, &
         nx,ny,nz,dx,dy,dp,finite_status)
    ref_max = REAL(MAXVAL(ABS(lambda_ref)))
    tiny_max = REAL(MAXVAL(ABS(lambda_tiny)))
    max_relative = 0.0
    DO kk=1,nz+1
      DO jj=1,ny+1
        DO ii=1,nx+1
          max_relative = MAX(max_relative, &
               REAL(ABS(lambda_tiny(ii,jj,kk)-lambda_ref(ii,jj,kk)))/ &
               MAX(REAL(ABS(lambda_ref(ii,jj,kk))),1.0))
        END DO
      END DO
    END DO
    CALL check(scale_status == 2, &
         'unit-scale one-iteration LEIBP3 should reach iteration limit',failures)
    CALL check(finite_status == scale_status .AND. tiny_max > 1.0 .AND. &
         ieee_is_finite(tiny_max) .AND. ieee_is_finite(max_relative) .AND. &
         max_relative < 1.0E-3, &
         'uniformly scaled connected row must remain finite and equivalent',failures)

    active = .FALSE.
    active(3,3,2) = .TRUE.
    cx_tiny = 0.0D0
    cy_tiny = 0.0D0
    cp_tiny = 0.0D0
    rhs_tiny = 0.0D0
    lambda_tiny = 0.0D0
    CALL leibp3(lambda_tiny,rhs_tiny,1,1.0,active,cx_tiny,cy_tiny,cp_tiny, &
         nx,ny,nz,dx,dy,dp,zero_status)
    CALL check(zero_status == 1 .AND. MAXVAL(ABS(lambda_tiny)) == 0.0, &
         'disconnected zero row with zero forcing must remain a solved zero',failures)

    rhs_tiny(3,3,2) = 1.0D-30
    lambda_tiny = 0.0D0
    CALL leibp3(lambda_tiny,rhs_tiny,1,1.0,active,cx_tiny,cy_tiny,cp_tiny, &
         nx,ny,nz,dx,dy,dp,tiny_status)
    CALL check(tiny_status == 0 .AND. MAXVAL(ABS(lambda_tiny)) == 0.0, &
         'disconnected row with any nonzero RHS must fail closed',failures)

    rhs_tiny(3,3,2) = 2.0D-20
    lambda_tiny = 0.0D0
    CALL leibp3(lambda_tiny,rhs_tiny,1,1.0,active,cx_tiny,cy_tiny,cp_tiny, &
         nx,ny,nz,dx,dy,dp,reject_status)
    CALL check(reject_status == 0, &
         'disconnected row with nonzero forcing must still reject',failures)

    active(3,3,2) = .TRUE.
    rhs_tiny = 0.0D0
    nan_value = ieee_value(0.0,ieee_quiet_nan)
    rhs_tiny(3,3,2) = REAL(nan_value,8)
    cx_tiny = 1.0D0
    cy_tiny = 1.0D0
    cp_tiny = 1.0D0
    CALL leibp3(lambda_tiny,rhs_tiny,1,1.0,active,cx_tiny,cy_tiny,cp_tiny, &
         nx,ny,nz,dx,dy,dp,finite_status)
    CALL check(finite_status == 0, &
         'nonfinite forcing must still fail closed',failures)
  END SUBROUTINE test_leibp3_scale_guard

  SUBROUTINE test_component_detailed_balance(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL*8 :: rhs(nx+1,ny+1,nz+1), cx(nx,ny,nz), cy(nx,ny,nz)
    REAL*8 :: cp(nx,ny,nz), epsilons(3), epsilon_value
    LOGICAL :: active(nx+1,ny+1,nz+1)
    REAL :: local_dx(nx,ny), local_dy(nx,ny), local_dp(nz)
    INTEGER :: component_status, ie

    epsilons = (/1.0D0, 1.0D-8, 1.0D-13/)
    local_dx = 1.0
    local_dy = 1.0
    local_dp = 1.0
    DO ie=1,3
      epsilon_value = epsilons(ie)
      active = .FALSE.
      active(2,2,2) = .TRUE.
      active(3,2,2) = .TRUE.
      active(2,3,2) = .TRUE.
      active(3,3,2) = .TRUE.
      cx = 0.0D0
      cy = 0.0D0
      cp = 0.0D0
      ! The production face coefficient is shared by both rows.  A row
      ! metric contrast creates the requested weak one-edge asymmetry.
      local_dx = 1.0
      local_dx(3,3) = 2.0
      cx(2,1,1) = epsilon_value
      cx(2,2,1) = epsilon_value
      cy(1,2,1) = 1.0D0
      cy(2,2,1) = 1.0D0
      rhs = 0.0D0
      rhs(2,2,2) = 1.0D0
      rhs(3,2,2) = -1.0D0
      rhs(2,3,2) = 1.0D0
      rhs(3,3,2) = -1.0D0
      CALL qbal_component_check(rhs,active,cx,cy,cp,nx,ny,nz, &
           local_dx,local_dy,local_dp,component_status)
      CALL check(component_status == 0, &
           'weak nonreversible cycle must remain unresolved', failures)

      ! Restore the weak reverse face to make every edge reversible.  The
      ! same small coefficients must pass the relative edge test.
      local_dx = 1.0
      CALL qbal_component_check(rhs,active,cx,cy,cp,nx,ny,nz, &
           local_dx,local_dy,local_dp,component_status)
      CALL check(component_status == 1, &
           'reversible weak edge must not be falsely rejected', failures)
    END DO
  END SUBROUTINE test_component_detailed_balance

END PROGRAM test_qbal_operator

SUBROUTINE zero3d(values,nx,ny,nz)
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: nx,ny,nz
  REAL, INTENT(OUT) :: values(nx,ny,nz)
  values = 0.0
END SUBROUTINE zero3d

SUBROUTINE move_3d(source,destination,nx,ny,nz)
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: nx,ny,nz
  REAL, INTENT(IN) :: source(nx,ny,nz)
  REAL, INTENT(OUT) :: destination(nx,ny,nz)
  destination = source
END SUBROUTINE move_3d
