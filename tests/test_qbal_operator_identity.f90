PROGRAM test_qbal_operator_identity
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE

  EXTERNAL :: continuity_point, leib_sub
  REAL*8, EXTERNAL :: qbal_divergence_value
  EXTERNAL :: qbal_continuity_setup, qbal_multiplier_increment
  EXTERNAL :: qbal_continuity_row, qbal_linear_residual, leibp3
  EXTERNAL :: qbal_component_check
  REAL*8, EXTERNAL :: qbal_row_value

  INTEGER, PARAMETER :: nx=6, ny=6, nz=5
  REAL, PARAMETER :: bnd=1.0E-30
  REAL :: u(nx,ny,nz), v(nx,ny,nz), w(nx,ny,nz)
  REAL :: erru(nx,ny,nz), tau(nx,ny), beta(nx,ny,nz)
  REAL :: dx(nx,ny), dy(nx,ny), ps(nx,ny), p(nz), dp(nz)
  REAL*8 :: cx(nx,ny,nz), cy(nx,ny,nz), cp(nx,ny,nz)
  REAL*8 :: rhs(nx+1,ny+1,nz+1)
  LOGICAL :: active(nx+1,ny+1,nz+1)
  INTEGER :: failures

  failures = 0
  CALL initialize_inputs()
  CALL test_setup_and_masks(failures)
  CALL test_active_edge_mobility(failures)
  CALL test_operator_identity(failures)
  CALL test_variable_metric_solve(failures)
  CALL test_component_preflight(failures)
  CALL test_read_only_residual(failures)
  CALL test_incompatible_rollback(failures)

  IF (failures /= 0) THEN
    PRINT *, 'QBAL independent operator tests failed:', failures
    ERROR STOP 1
  END IF
  PRINT *, 'QBAL independent operator identity tests passed'

CONTAINS

  SUBROUTINE initialize_inputs()
    INTEGER :: i, j, k

    p = (/100000.0, 85000.0, 70000.0, 55000.0, 40000.0/)
    dp = (/12000.0, 13000.0, 14000.0, 15000.0, 16000.0/)
    DO j=1,ny
      DO i=1,nx
        dx(i,j) = 6000.0 + 19.0*REAL(i) + 7.0*REAL(j)
        dy(i,j) = 7000.0 + 11.0*REAL(i) + 23.0*REAL(j)
        ps(i,j) = 102000.0
        tau(i,j) = 1.2 + 0.07*REAL(i) + 0.03*REAL(j)
      END DO
    END DO
    ! Two inactive portions make compact support and terrain adjacency visible.
    ps(3,4) = 60000.0
    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          beta(i,j,k) = 0.22 + 0.017*REAL(i) + 0.013*REAL(j) + &
               0.009*REAL(k)
          erru(i,j,k) = 0.65 + 0.031*REAL(i) + 0.021*REAL(j) + &
               0.014*REAL(k)
          u(i,j,k) = 3.0 + 0.17*REAL(i) - 0.08*REAL(j) + 0.03*REAL(k)
          v(i,j,k) = -2.0 + 0.11*REAL(i) + 0.14*REAL(j) - 0.05*REAL(k)
          w(i,j,k) = 0.3 + 0.05*REAL(i) - 0.04*REAL(j) + 0.02*REAL(k)
        END DO
      END DO
    END DO
    ! This stored u face masks two neighboring multiplier rows.
    u(2,2,2) = bnd
  END SUBROUTINE initialize_inputs

  SUBROUTINE test_setup_and_masks(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL :: residual
    REAL*8 :: rhs_base(nx+1,ny+1,nz+1), rhs_alt(nx+1,ny+1,nz+1)
    REAL*8 :: cx_base(nx,ny,nz), cy_base(nx,ny,nz), cp_base(nx,ny,nz)
    REAL*8 :: cx_alt(nx,ny,nz), cy_alt(nx,ny,nz), cp_alt(nx,ny,nz)
    REAL*8 :: lambda_face(nx+1,ny+1,nz+1)
    REAL :: du(nx,ny,nz), dv(nx,ny,nz), dw(nx,ny,nz)
    REAL :: beta_alt(nx,ny,nz), tau_alt(nx,ny)
    LOGICAL :: active_base(nx+1,ny+1,nz+1), active_alt(nx+1,ny+1,nz+1)
    REAL*8 :: expected, ci, cj, actual, scale
    INTEGER :: i, j, k, point_status, status

    CALL qbal_continuity_setup(u,v,w,erru,tau,beta,nx,ny,nz,dx,dy,ps,p,dp, &
         active,cx,cy,cp,rhs,status)
    CALL check(status == 1, 'continuity setup should accept finite inputs', &
         failures)
    active_base = active
    rhs_base = rhs
    cx_base = cx
    cy_base = cy
    cp_base = cp

    lambda_face = 0.0D0
    DO k=1,nz+1
      DO j=1,ny+1
        DO i=1,nx+1
          lambda_face(i,j,k) = 0.13D0*DBLE(i) - 0.07D0*DBLE(j) + &
               0.11D0*DBLE(k)
        END DO
      END DO
    END DO
    CALL qbal_multiplier_increment(lambda_face,cx,cy,cp,nx,ny,nz,du,dv,dw)
    CALL check_forbidden_faces(active,cx,cy,cp,du,dv,dw,failures)

    DO k=2,nz
      DO j=2,ny
        DO i=2,nx
          CALL continuity_point(u,v,w,nx,ny,nz,dx,dy,dp,i,j,k, &
               residual,point_status)
          IF (ps(i,j) >= p(k) .AND. beta(i,j,k) > 0.0 .AND. &
               point_status == 1) THEN
            CALL check(active(i,j,k), 'valid pressure row must be active', &
                 failures)
            CALL check(ABS(rhs(i,j,k)+qbal_divergence_value(u,v,w,nx,ny,nz, &
                 dx,dy,dp,i,j,k)) < 1.0D-12, &
                 'RHS must be the unweighted continuity divergence',failures)
          ELSE
            CALL check(.NOT.active(i,j,k), &
                 'terrain, sentinel, and zero-authority rows must be inactive', &
                 failures)
            CALL check(rhs(i,j,k) == 0.0D0, &
                 'inactive rows must have zero RHS', failures)
          END IF
        END DO
      END DO
    END DO

    ! All exterior normal faces are frozen.  Unused array planes are also zero.
    CALL check(MAXVAL(ABS(cx(1,:,:))) == 0.0D0 .AND. &
         MAXVAL(ABS(cx(nx,:,:))) == 0.0D0 .AND. &
         MAXVAL(ABS(cx(:,ny,:))) == 0.0D0 .AND. &
         MAXVAL(ABS(cx(:,:,nz))) == 0.0D0, &
         'west/east/top-unused u faces must remain frozen', failures)
    CALL check(MAXVAL(ABS(cy(:,1,:))) == 0.0D0 .AND. &
         MAXVAL(ABS(cy(:,ny,:))) == 0.0D0 .AND. &
         MAXVAL(ABS(cy(nx,:,:))) == 0.0D0 .AND. &
         MAXVAL(ABS(cy(:,:,nz))) == 0.0D0, &
         'south/north/top-unused v faces must remain frozen', failures)
    CALL check(MAXVAL(ABS(cp(:,:,1))) == 0.0D0 .AND. &
         MAXVAL(ABS(cp(:,:,nz))) == 0.0D0, &
         'bottom and top omega faces must remain frozen', failures)

    ! A face joining an inactive compact component is impermeable.
    CALL check(cx(3,3,2) == 0.0D0 .AND. cx(2,2,2) == 0.0D0, &
         'terrain and sentinel faces must have zero correction coefficient', &
         failures)

    ! Verify the variable-coefficient harmonic face calculation at a supported
    ! interior face, including its local dx metric.
    i = 4; j = 2; k = 2
    ci = 0.5D0*DBLE(beta(i,j+1,k+1))/DBLE(erru(i,j+1,k+1))
    cj = 0.5D0*DBLE(beta(i+1,j+1,k+1))/DBLE(erru(i+1,j+1,k+1))
    expected = harmonic(ci,cj)/DBLE(dx(i,j))
    actual = cx(i,j,k)
    scale = MAX(ABS(expected),1.0D-30)
    CALL check(active(i,j+1,k+1) .AND. active(i+1,j+1,k+1), &
         'selected variable-coefficient face must have active endpoints', &
         failures)
    CALL check(ABS(actual-expected) < 2.0D-14*scale, &
         'u face must use variable beta/erru harmonic weighting and dx', &
         failures)
    expected = 0.5D0*DBLE(beta(i,j,k))/ &
         (DBLE(tau(i,j))*DBLE(dp(k+1)))
    CALL check(ABS(cp(i,j,k)-expected) < 2.0D-14*MAX(ABS(expected),1.0D-30), &
         'interior omega face must use variable beta/tau/dp', failures)
    CALL check(cp(i,j,nz) == 0.0D0, 'top omega correction must be zero', &
         failures)

    ! Changing authority and tau changes coefficients but leaves the physical
    ! forcing unchanged.  This catches the old beta-weighted RHS regression.
    beta_alt = 0.25
    tau_alt = 17.0
    CALL qbal_continuity_setup(u,v,w,erru,tau_alt,beta_alt,nx,ny,nz,dx,dy, &
         ps,p,dp,active_alt,cx_alt,cy_alt,cp_alt,rhs_alt,status)
    CALL check(status == 1, 'alternate finite setup should succeed', failures)
    CALL check(ALL(active_alt .EQV. active_base), &
         'positive beta changes must preserve the active row mask', failures)
    CALL check(MAXVAL(ABS(rhs_alt-rhs_base)) == 0.0D0, &
         'RHS must not change when beta and tau change', failures)
    CALL check(ABS(cx_alt(i,j,k)-cx_base(i,j,k)) > 1.0D-12 .AND. &
         ABS(cp_alt(i,j,k)-cp_base(i,j,k)) > 1.0D-12, &
         'variable beta and tau must affect coefficients', failures)

    beta_alt = beta
    beta_alt(5,5,3) = 0.0
    CALL qbal_continuity_setup(u,v,w,erru,tau,beta_alt,nx,ny,nz,dx,dy,ps,p, &
         dp,active_alt,cx_alt,cy_alt,cp_alt,rhs_alt,status)
    CALL check(status == 1 .AND. .NOT.active_alt(5,5,3) .AND. &
         rhs_alt(5,5,3) == 0.0D0, &
         'zero beta must remove its row and forcing', failures)
  END SUBROUTINE test_setup_and_masks

  SUBROUTINE test_active_edge_mobility(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL :: ue(nx,ny,nz), ve(nx,ny,nz), we(nx,ny,nz)
    REAL :: erre(nx,ny,nz), taue(nx,ny), betae(nx,ny,nz)
    REAL :: dxe(nx,ny), dye(nx,ny), p_se(nx,ny), dpe(nz), p_e(nz)
    REAL*8 :: cxe(nx,ny,nz), cye(nx,ny,nz), cpe(nx,ny,nz)
    REAL*8 :: rhse(nx+1,ny+1,nz+1), sol_e(nx+1,ny+1,nz+1)
    REAL*8 :: rmsres, maxres
    LOGICAL :: active_e(nx+1,ny+1,nz+1)
    INTEGER :: status, location(3)

    ue = 0.0
    ve = 0.0
    we = 0.0
    erre = 1.0
    taue = 1.0
    dxe = 1.0
    dye = 1.0
    p_se = 102000.0
    p_e = p
    dpe = 1.0

    ! Exactly two active rows joined in X.  The old stored-face lookup sees
    ! beta(2,2,2) and beta(3,2,2), both zero; the incident rows are (2,3,3)
    ! and (3,3,3), which must provide the positive mobility.
    betae = 0.0
    betae(2,3,3) = 0.8
    betae(3,3,3) = 0.7
    CALL qbal_continuity_setup(ue,ve,we,erre,taue,betae,nx,ny,nz,dxe,dye, &
         p_se,p_e,dpe,active_e,cxe,cye,cpe,rhse,status)
    CALL check(status == 1 .AND. COUNT(active_e) == 2 .AND. &
         active_e(2,3,3) .AND. active_e(3,3,3), &
         'X compact fixture must contain exactly two active rows', failures)
    CALL check(betae(2,2,2) == 0.0 .AND. betae(3,2,2) == 0.0, &
         'X compact fixture must zero the old shifted beta locations', failures)
    CALL check(cxe(2,2,2) > 0.0D0 .AND. COUNT(cxe > 0.0D0) == 1 .AND. &
         COUNT(cye > 0.0D0) == 0 .AND. COUNT(cpe > 0.0D0) == 0, &
         'X active pair must have exactly one positive connecting face', failures)

    ! Equal metrics make this nonzero two-row forcing compatible.
    rhse = 0.0D0
    rhse(2,3,3) = -1.0D0
    rhse(3,3,3) = 1.0D0
    sol_e = 0.0D0
    CALL leibp3(sol_e,rhse,200,1.0,active_e,cxe,cye,cpe,nx,ny,nz, &
         dxe,dye,dpe,status)
    CALL qbal_linear_residual(sol_e,rhse,active_e,cxe,cye,cpe,nx,ny,nz, &
         dxe,dye,dpe,rmsres,maxres,location)
    CALL check(status == 1 .AND. maxres <= 1.0D-10 .AND. &
         MAXVAL(ABS(sol_e)) > 1.0D-8, &
         'X compact pair must support a nonzero compatible manufactured solve', &
         failures)

    ! Exactly two active rows joined in Y.  The old lookup sees beta(2,2,2)
    ! and beta(2,3,2), both zero; the incident rows are (3,2,3) and (3,3,3).
    betae = 0.0
    betae(3,2,3) = 0.8
    betae(3,3,3) = 0.7
    CALL qbal_continuity_setup(ue,ve,we,erre,taue,betae,nx,ny,nz,dxe,dye, &
         p_se,p_e,dpe,active_e,cxe,cye,cpe,rhse,status)
    CALL check(status == 1 .AND. COUNT(active_e) == 2 .AND. &
         active_e(3,2,3) .AND. active_e(3,3,3), &
         'Y compact fixture must contain exactly two active rows', failures)
    CALL check(betae(2,2,2) == 0.0 .AND. betae(2,3,2) == 0.0, &
         'Y compact fixture must zero the old shifted beta locations', failures)
    CALL check(cye(2,2,2) > 0.0D0 .AND. COUNT(cye > 0.0D0) == 1 .AND. &
         COUNT(cxe > 0.0D0) == 0 .AND. COUNT(cpe > 0.0D0) == 0, &
         'Y active pair must have exactly one positive connecting face', failures)

    ! Equal metrics make this nonzero two-row forcing compatible.
    rhse = 0.0D0
    rhse(3,2,3) = -1.0D0
    rhse(3,3,3) = 1.0D0
    sol_e = 0.0D0
    CALL leibp3(sol_e,rhse,200,1.0,active_e,cxe,cye,cpe,nx,ny,nz, &
         dxe,dye,dpe,status)
    CALL qbal_linear_residual(sol_e,rhse,active_e,cxe,cye,cpe,nx,ny,nz, &
         dxe,dye,dpe,rmsres,maxres,location)
    CALL check(status == 1 .AND. maxres <= 1.0D-10 .AND. &
         MAXVAL(ABS(sol_e)) > 1.0D-8, &
         'Y compact pair must support a nonzero compatible manufactured solve', &
         failures)
  END SUBROUTINE test_active_edge_mobility

  SUBROUTINE check_forbidden_faces(row_active,cx_faces,cy_faces,cp_faces, &
       du,dv,dw,failures)
    LOGICAL, INTENT(IN) :: row_active(nx+1,ny+1,nz+1)
    REAL*8, INTENT(IN) :: cx_faces(nx,ny,nz), cy_faces(nx,ny,nz)
    REAL*8, INTENT(IN) :: cp_faces(nx,ny,nz)
    REAL, INTENT(IN) :: du(nx,ny,nz), dv(nx,ny,nz), dw(nx,ny,nz)
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: i, j, k
    INTEGER :: exterior_count(3), support_count(3), sentinel_count(3)
    LOGICAL :: left_active, right_active, inside, forbidden, sentinel

    exterior_count = 0
    support_count = 0
    sentinel_count = 0

    ! Infer each x-face's two incident pressure rows from its stored-face
    ! placement.  A face is forbidden when either row is outside the domain,
    ! inactive, or its stored wind is the terrain sentinel.
    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          left_active = row_active(i,j+1,k+1)
          right_active = row_active(i+1,j+1,k+1)
          inside = i >= 2 .AND. i < nx .AND. j >= 1 .AND. j < ny .AND. &
               k >= 1 .AND. k < nz
          sentinel = u(i,j,k) == bnd
          forbidden = (.NOT.inside) .OR. &
               (.NOT.(left_active .AND. right_active)) .OR. sentinel
          IF (forbidden) THEN
            CALL check(cx_faces(i,j,k) == 0.0D0 .AND. du(i,j,k) == 0.0, &
                 'forbidden u face must have zero coefficient and increment', &
                 failures)
            IF (.NOT.inside) exterior_count(1) = exterior_count(1)+1
            IF (inside .AND. .NOT.(left_active .AND. right_active)) &
                 support_count(1) = support_count(1)+1
            IF (sentinel) sentinel_count(1) = sentinel_count(1)+1
          END IF
        END DO
      END DO
    END DO

    ! A y-face joins rows (i+1,j,k+1) and (i+1,j+1,k+1).
    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          left_active = row_active(i+1,j,k+1)
          right_active = row_active(i+1,j+1,k+1)
          inside = i >= 1 .AND. i < nx .AND. j >= 2 .AND. j < ny .AND. &
               k >= 1 .AND. k < nz
          sentinel = v(i,j,k) == bnd
          forbidden = (.NOT.inside) .OR. &
               (.NOT.(left_active .AND. right_active)) .OR. sentinel
          IF (forbidden) THEN
            CALL check(cy_faces(i,j,k) == 0.0D0 .AND. dv(i,j,k) == 0.0, &
                 'forbidden v face must have zero coefficient and increment', &
                 failures)
            IF (.NOT.inside) exterior_count(2) = exterior_count(2)+1
            IF (inside .AND. .NOT.(left_active .AND. right_active)) &
                 support_count(2) = support_count(2)+1
            IF (sentinel) sentinel_count(2) = sentinel_count(2)+1
          END IF
        END DO
      END DO
    END DO

    ! A vertical omega face joins rows (i,j,k) and (i,j,k+1).
    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          left_active = row_active(i,j,k)
          right_active = row_active(i,j,k+1)
          inside = i >= 2 .AND. i <= nx .AND. j >= 2 .AND. j <= ny .AND. &
               k >= 2 .AND. k < nz
          sentinel = w(i,j,k) == bnd
          forbidden = (.NOT.inside) .OR. &
               (.NOT.(left_active .AND. right_active)) .OR. sentinel
          IF (forbidden) THEN
            CALL check(cp_faces(i,j,k) == 0.0D0 .AND. dw(i,j,k) == 0.0, &
                 'forbidden omega face must have zero coefficient and increment', &
                 failures)
            IF (.NOT.inside) exterior_count(3) = exterior_count(3)+1
            IF (inside .AND. .NOT.(left_active .AND. right_active)) &
                 support_count(3) = support_count(3)+1
            IF (sentinel) sentinel_count(3) = sentinel_count(3)+1
          END IF
        END DO
      END DO
    END DO

    CALL check(MINVAL(exterior_count) > 0, &
         'every face orientation must exercise an exterior boundary', failures)
    CALL check(MINVAL(support_count) > 0, &
         'every face orientation must exercise support/terrain exclusion', &
         failures)
    CALL check(SUM(sentinel_count) > 0, &
         'the sentinel fixture must exercise a forbidden stored face', failures)
  END SUBROUTINE check_forbidden_faces

  SUBROUTINE test_operator_identity(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL*8 :: cx_id(nx,ny,nz), cy_id(nx,ny,nz), cp_id(nx,ny,nz)
    REAL*8 :: sol(nx+1,ny+1,nz+1), c(6), row, manual, divergence
    REAL :: du(nx,ny,nz), dv(nx,ny,nz), dw(nx,ny,nz)
    REAL*8 :: mapping_error, row_error, coefficient_error
    INTEGER :: i, j, k

    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          cx_id(i,j,k) = 0.10D0 + 0.003D0*DBLE(i) + &
               0.005D0*DBLE(j) + 0.007D0*DBLE(k)
          cy_id(i,j,k) = 0.12D0 + 0.004D0*DBLE(i) + &
               0.002D0*DBLE(j) + 0.006D0*DBLE(k)
          cp_id(i,j,k) = 0.14D0 + 0.002D0*DBLE(i) + &
               0.004D0*DBLE(j) + 0.003D0*DBLE(k)
        END DO
      END DO
    END DO
    DO k=1,nz+1
      DO j=1,ny+1
        DO i=1,nx+1
          sol(i,j,k) = 0.4D0 + 0.031D0*DBLE(i) - 0.017D0*DBLE(j) + &
               0.043D0*DBLE(k) + 0.001D0*DBLE(i*j)
        END DO
      END DO
    END DO

    CALL qbal_multiplier_increment(sol,cx_id,cy_id,cp_id,nx,ny,nz,du,dv,dw)
    mapping_error = 0.0D0
    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          mapping_error = MAX(mapping_error, &
               ABS(DBLE(du(i,j,k))-cx_id(i,j,k)* &
               (sol(i+1,j+1,k+1)-sol(i,j+1,k+1))))
          mapping_error = MAX(mapping_error, &
               ABS(DBLE(dv(i,j,k))-cy_id(i,j,k)* &
               (sol(i+1,j+1,k+1)-sol(i+1,j,k+1))))
          mapping_error = MAX(mapping_error, &
               ABS(DBLE(dw(i,j,k))-cp_id(i,j,k)* &
               (sol(i,j,k)-sol(i,j,k+1))))
        END DO
      END DO
    END DO
    CALL check(mapping_error < 2.0D-7, &
         'real8 multiplier faces must map to real4 increments', failures)

    coefficient_error = 0.0D0
    row_error = 0.0D0
    DO k=2,nz
      DO j=2,ny
        DO i=2,nx
          CALL qbal_continuity_row(cx_id,cy_id,cp_id,nx,ny,nz,dx,dy,dp, &
               i,j,k,c)
          coefficient_error = MAX(coefficient_error,ABS(c(1)- &
               cx_id(i,j-1,k-1)/DBLE(dx(i,j))))
          coefficient_error = MAX(coefficient_error,ABS(c(2)- &
               cx_id(i-1,j-1,k-1)/DBLE(dx(i,j))))
          coefficient_error = MAX(coefficient_error,ABS(c(3)- &
               cy_id(i-1,j,k-1)/DBLE(dy(i,j))))
          coefficient_error = MAX(coefficient_error,ABS(c(4)- &
               cy_id(i-1,j-1,k-1)/DBLE(dy(i,j))))
          coefficient_error = MAX(coefficient_error,ABS(c(5)- &
               cp_id(i,j,k)/DBLE(dp(k))))
          coefficient_error = MAX(coefficient_error,ABS(c(6)- &
               cp_id(i,j,k-1)/DBLE(dp(k))))
          row = qbal_row_value(sol,nx,ny,nz,i,j,k,c)
          manual = c(1)*(sol(i+1,j,k)-sol(i,j,k)) + &
               c(2)*(sol(i-1,j,k)-sol(i,j,k)) + &
               c(3)*(sol(i,j+1,k)-sol(i,j,k)) + &
               c(4)*(sol(i,j-1,k)-sol(i,j,k)) + &
               c(5)*(sol(i,j,k+1)-sol(i,j,k)) + &
               c(6)*(sol(i,j,k-1)-sol(i,j,k))
          row_error = MAX(row_error,ABS(row-manual))
          divergence = (DBLE(du(i,j-1,k-1))-DBLE(du(i-1,j-1,k-1)))/ &
               DBLE(dx(i,j)) + (DBLE(dv(i-1,j,k-1))- &
               DBLE(dv(i-1,j-1,k-1)))/DBLE(dy(i,j)) + &
               (DBLE(dw(i,j,k-1))-DBLE(dw(i,j,k)))/DBLE(dp(k))
          row_error = MAX(row_error,ABS(divergence-row))
        END DO
      END DO
    END DO
    CALL check(coefficient_error < 1.0D-18, &
         'continuity row must expose all six scaled face coefficients', &
         failures)
    CALL check(row_error < 2.0D-7, &
         'D applied to multiplier face increments must equal row value', &
         failures)
  END SUBROUTINE test_operator_identity

  SUBROUTINE test_variable_metric_solve(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL :: um(nx,ny,nz), vm(nx,ny,nz), wm(nx,ny,nz)
    REAL :: errm(nx,ny,nz), taum(nx,ny), betam(nx,ny,nz)
    REAL :: dxm(nx,ny), dym(nx,ny), psm(nx,ny), dpm(nz)
    REAL*8 :: cxm(nx,ny,nz), cym(nx,ny,nz), cpm(nx,ny,nz)
    REAL*8 :: rhs_m(nx+1,ny+1,nz+1), sol_m(nx+1,ny+1,nz+1)
    REAL*8 :: lambda_m(nx+1,ny+1,nz+1), c(6)
    REAL*8 :: rmsres, maxres
    LOGICAL :: active_m(nx+1,ny+1,nz+1)
    INTEGER :: i, j, k, status, location(3)

    um = 0.0
    vm = 0.0
    wm = 0.0
    errm = 0.0
    taum = 0.0
    betam = 0.0
    psm = 102000.0
    psm(3,4) = 60000.0
    DO j=1,ny
      DO i=1,nx
        ! dx==dy is deliberately spatially variable but separable, so the
        ! closed D G block has a positive reversible left-null weight.
        dxm(i,j) = 5200.0*(1.0+0.018*REAL(i))*(1.0+0.011*REAL(j))
        dym(i,j) = dxm(i,j)
        taum(i,j) = 1.1 + 0.05*REAL(i) + 0.02*REAL(j)
      END DO
    END DO
    dpm = (/11000.0, 12500.0, 14300.0, 16100.0, 18000.0/)
    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          errm(i,j,k) = 0.6 + 0.02*REAL(i) + 0.015*REAL(j) + &
               0.01*REAL(k)
          betam(i,j,k) = 0.25 + 0.008*REAL(i) + 0.006*REAL(j) + &
               0.004*REAL(k)
        END DO
      END DO
    END DO

    CALL qbal_continuity_setup(um,vm,wm,errm,taum,betam,nx,ny,nz,dxm,dym, &
         psm,p,dpm,active_m,cxm,cym,cpm,rhs_m,status)
    CALL check(status == 1, 'variable metric setup should succeed', failures)
    lambda_m = 0.0D0
    DO k=1,nz+1
      DO j=1,ny+1
        DO i=1,nx+1
          lambda_m(i,j,k) = 0.07D0*DBLE(i) - 0.04D0*DBLE(j) + &
               0.09D0*DBLE(k) + 0.002D0*DBLE(i*j*k)
        END DO
      END DO
    END DO
    ! Manufacture RHS directly from the same real8 A=D G operator.  This
    ! avoids float32 storage rounding and tests the true linear residual.
    rhs_m = 0.0D0
    DO k=2,nz
      DO j=2,ny
        DO i=2,nx
          IF (.NOT.active_m(i,j,k)) CYCLE
          CALL qbal_continuity_row(cxm,cym,cpm,nx,ny,nz,dxm,dym,dpm, &
               i,j,k,c)
          rhs_m(i,j,k) = qbal_row_value(lambda_m,nx,ny,nz,i,j,k,c)
        END DO
      END DO
    END DO
    sol_m = 0.0D0
    CALL leibp3(sol_m,rhs_m,200,1.0,active_m,cxm,cym,cpm,nx,ny,nz, &
         dxm,dym,dpm,status)
    CALL check(status == 1, &
         'variable beta and dx==dy/dp manufactured solve should converge', &
         failures)
    CALL qbal_linear_residual(sol_m,rhs_m,active_m,cxm,cym,cpm,nx,ny,nz, &
         dxm,dym,dpm,rmsres,maxres,location)
    CALL check(ieee_is_finite(rmsres) .AND. ieee_is_finite(maxres) .AND. &
         maxres <= 1.0D-10 .AND. MAXVAL(ABS(sol_m)) > 1.0D-8, &
         'variable metric solve must produce nonzero lambda with true residual <=1e-10', &
         failures)
  END SUBROUTINE test_variable_metric_solve

  SUBROUTINE test_component_preflight(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL*8 :: cx_c(nx,ny,nz), cy_c(nx,ny,nz), cp_c(nx,ny,nz)
    REAL*8 :: rhs_c(nx+1,ny+1,nz+1), rhs_bad(nx+1,ny+1,nz+1)
    REAL*8 :: sol_c(nx+1,ny+1,nz+1), sol_before(nx+1,ny+1,nz+1)
    REAL*8 :: rhs_before(nx+1,ny+1,nz+1)
    REAL*8 :: cx_before(nx,ny,nz), cy_before(nx,ny,nz), cp_before(nx,ny,nz)
    LOGICAL :: active_c(nx+1,ny+1,nz+1), active_before(nx+1,ny+1,nz+1)
    REAL :: dx_c(nx,ny), dy_c(nx,ny), dp_c(nz)
    REAL*8 :: c(6)
    INTEGER :: i, j, k, status

    ! A constant-metric closed block has a certified positive left null vector.
    ! The setup tests above retain fully variable metrics independently.
    cx_c = 0.0D0
    cy_c = 0.0D0
    cp_c = 0.0D0
    cx_c(2:nx-1,1:ny-1,1:nz-1) = 1.0D0
    cy_c(1:nx-1,2:ny-1,1:nz-1) = 1.0D0
    cp_c(2:nx,2:ny,2:nz-1) = 1.0D0
    active_c = .FALSE.
    active_c(2:nx,2:ny,2:nz) = .TRUE.
    dx_c = 1.0
    dy_c = 1.0
    dp_c = 1.0
    sol_c = 0.0D0
    DO k=1,nz+1
      DO j=1,ny+1
        DO i=1,nx+1
          sol_c(i,j,k) = 0.21D0*DBLE(i) - 0.13D0*DBLE(j) + &
               0.17D0*DBLE(k) + 0.003D0*DBLE(i*j*k)
        END DO
      END DO
    END DO
    rhs_c = 0.0D0
    DO k=2,nz
      DO j=2,ny
        DO i=2,nx
          CALL qbal_continuity_row(cx_c,cy_c,cp_c,nx,ny,nz,dx_c,dy_c,dp_c, &
               i,j,k,c)
          rhs_c(i,j,k) = qbal_row_value(sol_c,nx,ny,nz,i,j,k,c)
        END DO
      END DO
    END DO

    rhs_before = rhs_c
    cx_before = cx_c
    cy_before = cy_c
    cp_before = cp_c
    active_before = active_c
    CALL qbal_component_check(rhs_c,active_c,cx_c,cy_c,cp_c,nx,ny,nz, &
         dx_c,dy_c,dp_c,status)
    CALL check(status == 1, &
         'compatible closed divergence pair must pass component preflight', &
         failures)
    CALL check(ALL(rhs_c == rhs_before) .AND. ALL(cx_c == cx_before) .AND. &
         ALL(cy_c == cy_before) .AND. ALL(cp_c == cp_before) .AND. &
         ALL(active_c .EQV. active_before), &
         'component preflight must leave RHS, coefficients, and active mask unchanged', &
         failures)

    rhs_bad = rhs_c
    rhs_bad(3,3,3) = rhs_bad(3,3,3) + 0.25D0
    sol_before = sol_c
    rhs_before = rhs_bad
    cx_before = cx_c
    cy_before = cy_c
    cp_before = cp_c
    active_before = active_c
    CALL qbal_component_check(rhs_bad,active_c,cx_c,cy_c,cp_c,nx,ny,nz, &
         dx_c,dy_c,dp_c,status)
    CALL check(status == 0, &
         'closed component with an unbalanced RHS must be rejected', failures)
    CALL check(ALL(rhs_bad == rhs_before) .AND. ALL(sol_c == sol_before) .AND. &
         ALL(cx_c == cx_before) .AND. ALL(cy_c == cy_before) .AND. &
         ALL(cp_c == cp_before) .AND. ALL(active_c .EQV. active_before), &
         'incompatible component preflight must not mutate state', failures)

    ! leibp3 repeats this check before its first relaxation update.  Verify the
    ! public failure path preserves lambda as well as all operator inputs.
    sol_c = sol_before
    rhs_before = rhs_bad
    cx_before = cx_c
    cy_before = cy_c
    cp_before = cp_c
    active_before = active_c
    CALL leibp3(sol_c,rhs_bad,4,1.0,active_c,cx_c,cy_c,cp_c,nx,ny,nz, &
         dx_c,dy_c,dp_c,status)
    CALL check(status == 0 .AND. ALL(sol_c == sol_before), &
         'leibp3 must reject incompatible closed RHS without lambda mutation', &
         failures)
    CALL check(ALL(rhs_bad == rhs_before) .AND. ALL(cx_c == cx_before) .AND. &
         ALL(cy_c == cy_before) .AND. ALL(cp_c == cp_before) .AND. &
         ALL(active_c .EQV. active_before), &
         'leibp3 preflight failure must preserve RHS, coefficients, and mask', &
         failures)
  END SUBROUTINE test_component_preflight

  SUBROUTINE test_read_only_residual(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL*8 :: cx_id(nx,ny,nz), cy_id(nx,ny,nz), cp_id(nx,ny,nz)
    REAL*8 :: sol(nx+1,ny+1,nz+1), rhs_id(nx+1,ny+1,nz+1)
    REAL*8 :: sol_before(nx+1,ny+1,nz+1), rhs_before(nx+1,ny+1,nz+1)
    REAL*8 :: cx_before(nx,ny,nz), cy_before(nx,ny,nz), cp_before(nx,ny,nz)
    LOGICAL :: active_id(nx+1,ny+1,nz+1), active_before(nx+1,ny+1,nz+1)
    REAL*8 :: expected_rms, expected_max, sumres, r, c(6)
    REAL*8 :: rmsres, maxres
    INTEGER :: expected_location(3), location(3), i, j, k, n

    CALL fill_identity_arrays(cx_id,cy_id,cp_id,sol)
    active_id = .FALSE.
    active_id(2:nx,2:ny,2:nz) = .TRUE.
    active_id(3,3,3) = .FALSE.
    rhs_id = 0.0D0
    rhs_id(4,4,4) = 0.07D0
    sol(1,1,1) = -99.0D0
    sol(nx+1,ny+1,nz+1) = 77.0D0

    expected_max = 0.0D0
    expected_location = 0
    sumres = 0.0D0
    n = 0
    DO k=2,nz
      DO j=2,ny
        DO i=2,nx
          IF (.NOT.active_id(i,j,k)) CYCLE
          CALL qbal_continuity_row(cx_id,cy_id,cp_id,nx,ny,nz,dx,dy,dp, &
               i,j,k,c)
          r = qbal_row_value(sol,nx,ny,nz,i,j,k,c)-rhs_id(i,j,k)
          sumres = sumres+r*r
          n = n+1
          IF (ABS(r) > expected_max) THEN
            expected_max = ABS(r)
            expected_location = (/i,j,k/)
          END IF
        END DO
      END DO
    END DO
    expected_rms = SQRT(sumres/DBLE(n))

    sol_before = sol
    rhs_before = rhs_id
    cx_before = cx_id
    cy_before = cy_id
    cp_before = cp_id
    active_before = active_id
    CALL qbal_linear_residual(sol,rhs_id,active_id,cx_id,cy_id,cp_id, &
         nx,ny,nz,dx,dy,dp,rmsres,maxres,location)
    CALL check(ABS(rmsres-expected_rms) < 1.0D-14 .AND. &
         ABS(maxres-expected_max) < 1.0D-14 .AND. &
         ALL(location == expected_location), &
         'linear residual diagnostic must report the true RMS/max/location', &
         failures)
    CALL check(ALL(sol == sol_before) .AND. ALL(rhs_id == rhs_before) .AND. &
         ALL(cx_id == cx_before) .AND. ALL(cy_id == cy_before) .AND. &
         ALL(cp_id == cp_before) .AND. ALL(active_id .EQV. active_before), &
         'linear residual diagnostic must be read-only, including ghosts', &
         failures)
    CALL check(ieee_is_finite(rmsres) .AND. ieee_is_finite(maxres), &
         'linear residual diagnostic must remain finite', failures)
  END SUBROUTINE test_read_only_residual

  SUBROUTINE test_incompatible_rollback(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL*8 :: sol(nx+1,ny+1,nz+1), before(nx+1,ny+1,nz+1)
    REAL*8 :: rhs_id(nx+1,ny+1,nz+1)
    REAL*8 :: cx_id(nx,ny,nz), cy_id(nx,ny,nz), cp_id(nx,ny,nz)
    LOGICAL :: active_id(nx+1,ny+1,nz+1)
    REAL :: dx_bad(nx,ny), dy_bad(nx,ny), dp_bad(nz)
    REAL :: tau_bad(nx,ny), erru_bad(nx,ny,nz), influence_bad(nx,ny,nz)
    REAL :: lat_bad(nx,ny), ps_bad(nx,ny), p_bad(nz)
    REAL :: uo_bad(nx,ny,nz), vo_bad(nx,ny,nz), wo_bad(nx,ny,nz)
    REAL :: u_bad(nx,ny,nz), v_bad(nx,ny,nz), w_bad(nx,ny,nz)
    REAL :: omega_background(nx,ny,nz)
    REAL :: omega_before(nx,ny,nz)
    INTEGER :: status

    sol = 0.0D0
    sol(1,1,1) = -13.0D0
    sol(nx+1,ny+1,nz+1) = 29.0D0
    before = sol
    rhs_id = 0.0D0
    rhs_id(3,3,3) = 3.0D-5
    cx_id = 0.0D0
    cy_id = 0.0D0
    cp_id = 0.0D0
    active_id = .FALSE.
    active_id(3,3,3) = .TRUE.
    dx_bad = dx
    dy_bad = dy
    dp_bad = dp
    CALL leibp3(sol,rhs_id,4,1.0,active_id,cx_id,cy_id,cp_id, &
         nx,ny,nz,dx_bad,dy_bad,dp_bad,status)
    CALL check(status == 0 .AND. ALL(sol == before), &
         'incompatible zero row must reject before changing lambda', failures)

    ! A positive authority mask with no valid pressure rows is an invalid
    ! projection request.  leib_sub must reject it while preserving every
    ! output field exactly.
    dx_bad = 1.0
    dy_bad = 1.0
    dp_bad = 1.0
    tau_bad = 2.0
    erru_bad = 1.0
    influence_bad = 0.25
    lat_bad = 36.0
    ps_bad = 1000.0
    p_bad = p
    uo_bad = 2.0
    vo_bad = -3.0
    wo_bad = 4.0
    u_bad = uo_bad
    v_bad = vo_bad
    w_bad = wo_bad
    omega_background = 0.0
    omega_before = omega_background
    CALL leib_sub(nx,ny,nz,0.01,tau_bad,erru_bad,influence_bad,lat_bad, &
         dx_bad,dy_bad,ps_bad,p_bad,dp_bad,uo_bad,u_bad,vo_bad,v_bad, &
         wo_bad,w_bad,omega_background,1,1,status)
    CALL check(status == 0 .AND. ALL(u_bad == uo_bad) .AND. &
         ALL(v_bad == vo_bad) .AND. ALL(w_bad == wo_bad) .AND. &
         ALL(omega_background == omega_before) .AND. ALL(uo_bad == 2.0) .AND. &
         ALL(vo_bad == -3.0) .AND. ALL(wo_bad == 4.0), &
         'positive authority with all rows terrain must reject and roll back', &
         failures)

  END SUBROUTINE test_incompatible_rollback

  SUBROUTINE fill_identity_arrays(cx_id,cy_id,cp_id,sol)
    REAL*8, INTENT(OUT) :: cx_id(nx,ny,nz), cy_id(nx,ny,nz), cp_id(nx,ny,nz)
    REAL*8, INTENT(OUT) :: sol(nx+1,ny+1,nz+1)
    INTEGER :: i, j, k

    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          cx_id(i,j,k) = 0.10D0 + 0.003D0*DBLE(i) + &
               0.005D0*DBLE(j) + 0.007D0*DBLE(k)
          cy_id(i,j,k) = 0.12D0 + 0.004D0*DBLE(i) + &
               0.002D0*DBLE(j) + 0.006D0*DBLE(k)
          cp_id(i,j,k) = 0.14D0 + 0.002D0*DBLE(i) + &
               0.004D0*DBLE(j) + 0.003D0*DBLE(k)
        END DO
      END DO
    END DO
    DO k=1,nz+1
      DO j=1,ny+1
        DO i=1,nx+1
          sol(i,j,k) = 0.4D0 + 0.031D0*DBLE(i) - 0.017D0*DBLE(j) + &
               0.043D0*DBLE(k) + 0.001D0*DBLE(i*j)
        END DO
      END DO
    END DO
  END SUBROUTINE fill_identity_arrays

  REAL*8 FUNCTION harmonic(a,b)
    REAL*8, INTENT(IN) :: a,b
    harmonic = 0.0D0
    IF (MIN(a,b) > 0.0D0) THEN
      harmonic = 2.0D0*MIN(a,b)/(1.0D0+MIN(a,b)/MAX(a,b))
    END IF
  END FUNCTION harmonic

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures = failures + 1
      PRINT *, 'FAIL: ', TRIM(message)
    END IF
  END SUBROUTINE check

END PROGRAM test_qbal_operator_identity
