PROGRAM test_qbal_operator
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite, ieee_value, ieee_quiet_nan
  IMPLICIT NONE

  EXTERNAL :: continuity_metrics,continuity_point,leib_sub
  EXTERNAL :: leibp3
  EXTERNAL :: geostrophic_residual_metrics

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
  local_influence(2:4,2:4,2:3) = 1.0
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
    REAL :: sol_ref(nx+1,ny+1,nz+1), sol_tiny(nx+1,ny+1,nz+1)
    REAL :: force_ref(nx+1,ny+1,nz+1), force_tiny(nx+1,ny+1,nz+1)
    REAL :: htest(nx+1,ny+1,nz+1)
    REAL :: influence_ref(nx,ny,nz), influence_tiny(nx,ny,nz)
    REAL :: tiny_max, ref_max, max_relative
    REAL :: nan_value
    INTEGER :: scale_status, zero_status, tiny_status, reject_status
    INTEGER :: finite_status
    INTEGER :: ii, jj, kk

    dx = 5061.267
    dy = 5061.267
    ps = 101000.0
    p = (/100000.0, 85000.0, 70000.0, 50000.0/)
    dp = (/15000.0, 15000.0, 15000.0, 20000.0/)
    erru = 0.5917161
    tau = 0.5787722
    sol_ref = 0.0
    sol_tiny = 0.0
    force_ref = 0.0
    force_tiny = 0.0
    htest = 0.0
    influence_ref = 1.0
    influence_tiny = 1.0E-14
    force_ref(3,3,2) = 1.0
    force_tiny(3,3,2) = 1.0E-14

    CALL leibp3(sol_ref,force_ref,1,1.0,htest,erru,tau,influence_ref, &
         nx,ny,nz,dx,dy,ps,p,dp,scale_status)
    CALL leibp3(sol_tiny,force_tiny,1,1.0,htest,erru,tau,influence_tiny, &
         nx,ny,nz,dx,dy,ps,p,dp,finite_status)
    ref_max = MAXVAL(ABS(sol_ref))
    tiny_max = MAXVAL(ABS(sol_tiny))
    max_relative = 0.0
    DO kk=1,nz+1
      DO jj=1,ny+1
        DO ii=1,nx+1
          max_relative = MAX(max_relative, &
               ABS(sol_tiny(ii,jj,kk)-sol_ref(ii,jj,kk))/ &
               MAX(ABS(sol_ref(ii,jj,kk)),1.0))
        END DO
      END DO
    END DO
    CALL check(scale_status == 2, &
         'unit-scale one-iteration LEIBP3 should reach iteration limit',failures)
    CALL check(finite_status == scale_status .AND. tiny_max > 1.0 .AND. &
         ieee_is_finite(tiny_max) .AND. ieee_is_finite(max_relative) .AND. &
         max_relative < 1.0E-3, &
         'uniformly scaled connected row must remain finite and equivalent',failures)

    sol_tiny = 0.0
    force_tiny = 0.0
    influence_tiny = 0.0
    CALL leibp3(sol_tiny,force_tiny,1,1.0,htest,erru,tau,influence_tiny, &
         nx,ny,nz,dx,dy,ps,p,dp,zero_status)
    CALL check(zero_status == 1 .AND. MAXVAL(ABS(sol_tiny)) == 0.0, &
         'disconnected zero row with zero forcing must remain a solved zero',failures)

    force_tiny(3,3,2) = 1.0E-30
    sol_tiny = 0.0
    CALL leibp3(sol_tiny,force_tiny,1,1.0,htest,erru,tau,influence_tiny, &
         nx,ny,nz,dx,dy,ps,p,dp,tiny_status)
    CALL check(tiny_status == 0 .AND. MAXVAL(ABS(sol_tiny)) == 0.0, &
         'disconnected row with any nonzero RHS must fail closed',failures)

    force_tiny(3,3,2) = 2.0E-20
    sol_tiny = 0.0
    CALL leibp3(sol_tiny,force_tiny,1,1.0,htest,erru,tau,influence_tiny, &
         nx,ny,nz,dx,dy,ps,p,dp,reject_status)
    CALL check(reject_status == 0, &
         'disconnected row with nonzero forcing must still reject',failures)

    influence_tiny = 1.0
    force_tiny = 0.0
    nan_value = ieee_value(0.0,ieee_quiet_nan)
    force_tiny(3,3,2) = nan_value
    CALL leibp3(sol_tiny,force_tiny,1,1.0,htest,erru,tau,influence_tiny, &
         nx,ny,nz,dx,dy,ps,p,dp,finite_status)
    CALL check(finite_status == 0, &
         'nonfinite forcing must still fail closed',failures)
  END SUBROUTINE test_leibp3_scale_guard

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
