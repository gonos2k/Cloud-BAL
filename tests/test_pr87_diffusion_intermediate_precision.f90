PROGRAM test_pr87_diffusion_intermediate_precision
  USE iso_fortran_env, ONLY: real32,real64
  USE pr87_horizontal_diffusion64_baseline, ONLY: horizontal_diffusion64_baseline
  USE pr87_horizontal_diffusion64, ONLY: horizontal_diffusion64
  USE cloud_bal_joint_transport, ONLY: joint_moment_store
  IMPLICIT NONE
  INTEGER,PARAMETER :: ims=153,ime=155,kms=17,kme=17,jms=76,jme=78
  REAL(real32) :: q(ims:ime,kms:kme,jms:jme),b(ims:ime,kms:kme,jms:jme)
  REAL(real32) :: mut(ims:ime,jms:jme),c1(kms:kme),c2(kms:kme)
  REAL(real32) :: msfux(ims:ime,jms:jme),msfuy(ims:ime,jms:jme)
  REAL(real32) :: msfvx_inv(ims:ime,jms:jme),msfvy(ims:ime,jms:jme)
  REAL(real32) :: msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme)
  REAL(real32) :: xkmhd(ims:ime,kms:kme,jms:jme)
  REAL(real64) :: q64(ims:ime,kms:kme,jms:jme),b64(ims:ime,kms:kme,jms:jme)
  REAL(real64) :: q128(ims:ime,kms:kme,jms:jme),b128(ims:ime,kms:kme,jms:jme)
  REAL(real64) :: qcandidate,b_candidate
  REAL(real32) :: qstored,bstored,donor_b
  INTEGER :: exponent,adjustment,failures
  LOGICAL :: valid

  CALL captured_case_inputs(q,b,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy,msftx,msfty,xkmhd)
  CALL horizontal_diffusion64_baseline(q,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,1.99999994947575033e-4_real32,1.99999994947575033e-4_real32, &
       ims,ime,kms,kme,jms,jme,154,154,77,77,17,17,q64)
  CALL horizontal_diffusion64_baseline(b,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,1.99999994947575033e-4_real32,1.99999994947575033e-4_real32, &
       ims,ime,kms,kme,jms,jme,154,154,77,77,17,17,b64)
  CALL horizontal_diffusion64(q,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,1.99999994947575033e-4_real32,1.99999994947575033e-4_real32, &
       ims,ime,kms,kme,jms,jme,154,154,77,77,17,17,q128)
  CALL horizontal_diffusion64(b,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,1.99999994947575033e-4_real32,1.99999994947575033e-4_real32, &
       ims,ime,kms,kme,jms,jme,154,154,77,77,17,17,b128)

  CALL check(q(155,17,77)/b(155,17,77)==900.0_real32, &
       'captured nonzero donor is exactly on the strict 900 upper-density boundary')
  CALL check(q64(154,17,77)-900.0_real64*b64(154,17,77)>0.0_real64, &
       'current REAL64 evaluation reproduces captured upper-bound crossing')
  CALL check(q128(154,17,77)-900.0_real64*b128(154,17,77)<=0.0_real64, &
       'REAL128 intermediates keep this captured stencil at or below the upper bound')
  qcandidate=(6.66666650772094727_real64*q64(154,17,77))/93593.875_real64
  b_candidate=(6.66666650772094727_real64*b64(154,17,77))/93593.875_real64
  CALL joint_moment_store(qcandidate,b_candidate,1.0_real32,100.0_real64,900.0_real64, &
       .TRUE.,qstored,bstored,adjustment,valid,allow_normal_q_adjustment=.TRUE., &
       strict_mass_ratio=.TRUE.)
  CALL check(.NOT.valid, 'current REAL64 full candidate fails the unchanged strict G store')
  qcandidate=(6.66666650772094727_real64*q128(154,17,77))/93593.875_real64
  b_candidate=(6.66666650772094727_real64*b128(154,17,77))/93593.875_real64
  CALL joint_moment_store(qcandidate,b_candidate,1.0_real32,100.0_real64,900.0_real64, &
       .TRUE.,qstored,bstored,adjustment,valid,allow_normal_q_adjustment=.TRUE., &
       strict_mass_ratio=.TRUE.)
  CALL check(valid, 'REAL128 full candidate passes the unchanged strict G store')
  PRINT '(A,1P,4E26.17)', 'PR87_CAPTURED_CASE_PASS ',q64(154,17,77),b64(154,17,77), &
       q128(154,17,77),b128(154,17,77)

  ! Manufactured one-face stencils use exact R32 Q=900*B inputs at the same
  ! captured geometry, across several scales. No source terms or base pair.
  failures=0
  DO exponent=-15,-39,-2
    q=0.0_real32; b=0.0_real32
    donor_b=SCALE(1.0_real32,exponent)
    b(155,17,77)=donor_b
    q(155,17,77)=900.0_real32*donor_b
    CALL horizontal_diffusion64_baseline(q,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
         msftx,msfty,xkmhd,1.99999994947575033e-4_real32,1.99999994947575033e-4_real32, &
         ims,ime,kms,kme,jms,jme,154,154,77,77,17,17,q64)
    CALL horizontal_diffusion64_baseline(b,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
         msftx,msfty,xkmhd,1.99999994947575033e-4_real32,1.99999994947575033e-4_real32, &
         ims,ime,kms,kme,jms,jme,154,154,77,77,17,17,b64)
    CALL horizontal_diffusion64(q,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
         msftx,msfty,xkmhd,1.99999994947575033e-4_real32,1.99999994947575033e-4_real32, &
         ims,ime,kms,kme,jms,jme,154,154,77,77,17,17,q128)
    CALL horizontal_diffusion64(b,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
         msftx,msfty,xkmhd,1.99999994947575033e-4_real32,1.99999994947575033e-4_real32, &
         ims,ime,kms,kme,jms,jme,154,154,77,77,17,17,b128)
    CALL check(q(155,17,77)/b(155,17,77)==900.0_real32, &
         'manufactured inputs remain exactly on the upper bound')
    CALL check(q128(154,17,77)-900.0_real64*b128(154,17,77)<=0.0_real64, &
         'manufactured REAL128 tendency stays within the strict upper bound')
    failures=failures+1
  END DO
  CALL check(failures==13, 'all thirteen manufactured exact-bound scales were exercised')

  CALL test_weighted_conservation()
  PRINT *, 'PR87_DIFFUSION_INTERMEDIATE_PRECISION_PASS'

CONTAINS

  SUBROUTINE check(ok,label)
    LOGICAL,INTENT(IN) :: ok
    CHARACTER(*),INTENT(IN) :: label
    IF (.NOT.ok) THEN
      PRINT *, 'FAIL: ',label
      ERROR STOP 1
    END IF
  END SUBROUTINE check

  SUBROUTINE captured_case_inputs(qin,bin,mu,coef1,coef2,sux,suy,vxinv,svy,tx,ty,xk)
    REAL(real32),INTENT(OUT) :: qin(ims:ime,kms:kme,jms:jme),bin(ims:ime,kms:kme,jms:jme)
    REAL(real32),INTENT(OUT) :: mu(ims:ime,jms:jme),coef1(kms:kme),coef2(kms:kme)
    REAL(real32),INTENT(OUT) :: sux(ims:ime,jms:jme),suy(ims:ime,jms:jme)
    REAL(real32),INTENT(OUT) :: vxinv(ims:ime,jms:jme),svy(ims:ime,jms:jme)
    REAL(real32),INTENT(OUT) :: tx(ims:ime,jms:jme),ty(ims:ime,jms:jme)
    REAL(real32),INTENT(OUT) :: xk(ims:ime,kms:kme,jms:jme)
    qin=0.0_real32; bin=0.0_real32; xk=0.0_real32; mu=0.0_real32
    qin(155,17,77)=2.27489067583519500e-6_real32
    bin(155,17,77)=2.52765630648355000e-9_real32
    mu(154,77)=9.4035796875e4_real32; mu(153,77)=9.4547171875e4_real32
    mu(155,77)=9.25721875e4_real32; mu(154,76)=9.40074765625e4_real32
    mu(154,78)=9.4330875e4_real32
    coef1(17)=1.45831656455993652_real32; coef2(17)=-4.354007421875e4_real32
    xk(154,17,77)=1.3652811279296875e3_real32; xk(153,17,77)=1.6500545654296875e3_real32
    xk(155,17,77)=6.58880859375e2_real32; xk(154,17,76)=2.15112451171875e3_real32
    xk(154,17,78)=1.2780965576171875e3_real32
    sux(153,77)=.98169100284576416_real32; sux(154,77)=.98169440031051636_real32
    sux(155,77)=.98169785737991333_real32; suy(153,77)=.98169100284576416_real32
    suy(154,77)=.98169440031051636_real32; suy(155,77)=.98169785737991333_real32
    vxinv(154,77)=1.01857459545135498_real32; vxinv(154,78)=1.01871562004089355_real32
    svy(154,77)=.98176413774490356_real32; svy(154,78)=.98162817955017090_real32
    tx(154,77)=.98169612884521484_real32; ty(154,77)=.98169612884521484_real32
  END SUBROUTINE captured_case_inputs

  SUBROUTINE test_weighted_conservation()
    INTEGER,PARAMETER :: ai=0,bi=6,ak=1,bk=1,aj=0,bj=6
    REAL(real32) :: f(ai:bi,ak:bk,aj:bj),mu(ai:bi,aj:bj),coef1(ak:bk),coef2(ak:bk)
    REAL(real32) :: sux(ai:bi,aj:bj),suy(ai:bi,aj:bj),vxinv(ai:bi,aj:bj),svy(ai:bi,aj:bj)
    REAL(real32) :: tx(ai:bi,aj:bj),ty(ai:bi,aj:bj),xk(ai:bi,ak:bk,aj:bj)
    REAL(real64) :: oldrate(ai:bi,ak:bk,aj:bj),newrate(ai:bi,ak:bk,aj:bj)
    REAL(real64) :: oldsum,oldscale,newsum,newscale
    INTEGER :: ii,jj
    DO jj=aj,bj
      DO ii=ai,bi
        mu(ii,jj)=5000.0_real32+12.0_real32*REAL(2*ii+3*jj,real32)
        sux(ii,jj)=.9_real32+.01_real32*REAL(ii,real32)
        suy(ii,jj)=.95_real32+.007_real32*REAL(jj,real32)
        vxinv(ii,jj)=1.01_real32+.003_real32*REAL(jj,real32)
        svy(ii,jj)=.96_real32+.004_real32*REAL(ii,real32)
        tx(ii,jj)=.97_real32+.002_real32*REAL(ii+jj,real32)
        ty(ii,jj)=.98_real32+.001_real32*REAL(2*ii-jj,real32)
        xk(ii,1,jj)=200.0_real32+3.0_real32*REAL(ii*ii+jj,real32)
      END DO
    END DO
    coef1(1)=1.25_real32; coef2(1)=-2000.0_real32
    f=0.0_real32
    DO jj=2,6
      DO ii=2,6
        f(ii,1,jj)=REAL(1+ii+2*jj+MOD(ii*jj,3),real32)*2.0_real32**(-24)
      END DO
    END DO
    DO jj=2,6
      f(1,1,jj)=f(2,1,jj); f(0,1,jj)=f(2,1,jj)
      f(6,1,jj)=f(5,1,jj); f(5,1,jj)=f(5,1,jj)
    END DO
    DO ii=0,6
      f(ii,1,0)=f(ii,1,2); f(ii,1,1)=f(ii,1,2)
      f(ii,1,6)=f(ii,1,5)
    END DO
    CALL horizontal_diffusion64_baseline(f,mu,coef1,coef2,sux,suy,vxinv,svy,tx,ty,xk, &
         .0002_real32,.0002_real32,ai,bi,ak,bk,aj,bj,2,5,2,5,1,1,oldrate)
    CALL horizontal_diffusion64(f,mu,coef1,coef2,sux,suy,vxinv,svy,tx,ty,xk, &
         .0002_real32,.0002_real32,ai,bi,ak,bk,aj,bj,2,5,2,5,1,1,newrate)
    oldsum=0.0_real64; oldscale=0.0_real64; newsum=0.0_real64; newscale=0.0_real64
    DO jj=2,5
      DO ii=2,5
        oldsum=oldsum+oldrate(ii,1,jj)/(REAL(tx(ii,jj),real64)*REAL(ty(ii,jj),real64))
        oldscale=oldscale+ABS(oldrate(ii,1,jj)/(REAL(tx(ii,jj),real64)*REAL(ty(ii,jj),real64)))
        newsum=newsum+newrate(ii,1,jj)/(REAL(tx(ii,jj),real64)*REAL(ty(ii,jj),real64))
        newscale=newscale+ABS(newrate(ii,1,jj)/(REAL(tx(ii,jj),real64)*REAL(ty(ii,jj),real64)))
      END DO
    END DO
    CALL check(ABS(oldsum)<=128.0_real64*EPSILON(1.0_real64)*oldscale, &
         'R64 baseline respects the closed-face conservation envelope')
    CALL check(ABS(newsum)<=128.0_real64*EPSILON(1.0_real64)*newscale, &
         'REAL128 evaluation respects the same closed-face conservation envelope')
    CALL check(ABS(newsum)<=ABS(oldsum), &
         'REAL128 result does not increase the measured weighted residual for this fixture')
    PRINT '(A,1P,4E26.17)', 'PR87_WEIGHTED_SUMS ',oldsum,oldscale,newsum,newscale
  END SUBROUTINE test_weighted_conservation

END PROGRAM test_pr87_diffusion_intermediate_precision
