PROGRAM test_qbal_operator
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  IMPLICIT NONE

  EXTERNAL :: continuity_metrics,continuity_point,leib_sub
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
