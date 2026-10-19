PROGRAM test_pr87_horizontal_diffusion64
  USE iso_fortran_env, ONLY: real32,real64
  USE ieee_arithmetic, ONLY: ieee_is_finite
  USE pr87_horizontal_diffusion64, ONLY: horizontal_diffusion64
  IMPLICIT NONE
  INTEGER,PARAMETER :: ims=0,ime=6,kms=0,kme=2,jms=0,jme=6
  INTEGER,PARAMETER :: il=2,ih=4,jl=2,jh=4,kl=1,kh=1
  REAL(real32) :: field(ims:ime,kms:kme,jms:jme),mut(ims:ime,jms:jme)
  REAL(real32) :: c1(kms:kme),c2(kms:kme),msfux(ims:ime,jms:jme),msfuy(ims:ime,jms:jme)
  REAL(real32) :: msfvx_inv(ims:ime,jms:jme),msfvy(ims:ime,jms:jme)
  REAL(real32) :: msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme)
  REAL(real32) :: xkmhd(ims:ime,kms:kme,jms:jme),field_n(ims:ime,kms:kme,jms:jme)
  REAL(real64) :: increment(ims:ime,kms:kme,jms:jme),increment_n(ims:ime,kms:kme,jms:jme)
  REAL(real64) :: expected,weighted_sum,weighted_scale,area
  REAL(real64) :: dq64,dn64,dq_correction,dn_correction,q_cont,n_cont,q_min_mass
  REAL(real32) :: q_before,n_before,q_diff32,n_diff32,q_after32,n_after32
  INTEGER :: i,j,k

  DO j=jms,jme
    DO i=ims,ime
      mut(i,j)=0.25_real32+0.015625_real32*REAL(i,real32)+0.0078125_real32*REAL(j,real32)
      msfux(i,j)=1.0_real32+0.03125_real32*REAL(i,real32)
      msfuy(i,j)=1.25_real32+0.015625_real32*REAL(j,real32)
      msfvx_inv(i,j)=0.75_real32+0.0078125_real32*REAL(i+j,real32)
      msfvy(i,j)=1.125_real32+0.015625_real32*REAL(j,real32)
      msftx(i,j)=0.875_real32+0.015625_real32*REAL(i,real32)
      msfty(i,j)=1.0625_real32+0.0078125_real32*REAL(j,real32)
      DO k=kms,kme
        xkmhd(i,k,j)=0.125_real32+0.0078125_real32*REAL(i,real32)+ &
                     0.00390625_real32*REAL(j,real32)+0.015625_real32*REAL(k,real32)
        field(i,k,j)=REAL(i*i+2*j+k,real32)/16.0_real32
      END DO
    END DO
  END DO
  c1=[0.5_real32,0.625_real32,0.75_real32]
  c2=[0.25_real32,0.1875_real32,0.125_real32]

  ! The helper evaluates only the requested m-cell box and leaves all other
  ! cells zero, including unused vertical levels.
  CALL horizontal_diffusion64(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32, &
       ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh,increment)
  IF (ANY(.NOT.ieee_is_finite(increment))) ERROR STOP 'nonfinite R64 diffusion increment'
  IF (ANY(increment(ims:il-1,:,:)/=0.0_real64).OR. &
      ANY(increment(ih+1:ime,:,:)/=0.0_real64).OR. &
      ANY(increment(:,kms:kl-1,:)/=0.0_real64).OR. &
      ANY(increment(:,kh+1:kme,:)/=0.0_real64).OR. &
      ANY(increment(:,:,jms:jl-1)/=0.0_real64).OR. &
      ANY(increment(:,:,jh+1:jme)/=0.0_real64)) ERROR STOP 'increment escaped active bounds'
  expected=reference_cell(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32,3,1,3)
  IF (increment(3,1,3)/=expected) ERROR STOP 'nonuniform face coefficient mapping mismatch'

  ! Zero and constant fields have exactly zero conservative-flux increment.
  field=0.0_real32
  CALL horizontal_diffusion64(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32, &
       ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh,increment)
  IF (ANY(increment/=0.0_real64)) ERROR STOP 'zero field produced diffusion'
  field=3.25_real32
  CALL horizontal_diffusion64(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32, &
       ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh,increment)
  IF (ANY(increment/=0.0_real64)) ERROR STOP 'constant field produced diffusion'

  ! With zero boundary-normal gradients, the internal face terms cancel in
  ! the area-weighted sum, even with nonuniform face metrics and coefficients.
  DO j=jms,jme
    DO i=ims,ime
      field(i,1,j)=REAL(MAX(il,MIN(ih,i))**2+2*MAX(jl,MIN(jh,j)),real32)/16.0_real32
    END DO
  END DO
  CALL horizontal_diffusion64(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32, &
       ims,ime,kms,kme,jms,jme,il,ih,jl,jh,1,1,increment)
  weighted_sum=0.0_real64; weighted_scale=0.0_real64
  DO j=jl,jh
    DO i=il,ih
      area=REAL(msftx(i,j),real64)*REAL(msfty(i,j),real64)
      weighted_sum=weighted_sum+increment(i,1,j)/area
      weighted_scale=weighted_scale+ABS(increment(i,1,j)/area)
    END DO
  END DO
  IF (ABS(weighted_sum)>128.0_real64*EPSILON(1.0_real64)*weighted_scale) &
    ERROR STOP 'closed internal diffusion faces did not cancel'

  ! Q and N fields related by an exact power of two receive the same
  ! REAL64 face weights and therefore preserve their shared mixing ratio.
  field_n=8.0_real32*field
  CALL horizontal_diffusion64(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32, &
       ims,ime,kms,kme,jms,jme,il,ih,jl,jh,1,1,increment)
  CALL horizontal_diffusion64(field_n,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32, &
       ims,ime,kms,kme,jms,jme,il,ih,jl,jh,1,1,increment_n)
  IF (ANY(increment_n/=8.0_real64*increment)) ERROR STOP 'dyadic Q/N diffusion mix diverged'

  ! The float32 accumulator can cross a strict lower rain bound even when
  ! the same REAL32 face inputs evaluated in REAL64 remain inside it. The
  ! correction exactly replaces the old accumulated R32 increment.
  DO j=jms,jme
    DO i=ims,ime
      DO k=kms,kme
        field(i,k,j)=REAL(i*i+2*j+k,real32)/16.0_real32*3.9e-4_real32
        field_n(i,k,j)=REAL(i+2*j+3*k,real32)/16.0_real32*5000.0_real32
      END DO
    END DO
  END DO
  CALL horizontal_diffusion64(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32, &
       ims,ime,kms,kme,jms,jme,il,ih,jl,jh,1,1,increment)
  CALL horizontal_diffusion64(field_n,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32, &
       ims,ime,kms,kme,jms,jme,il,ih,jl,jh,1,1,increment_n)
  dq64=increment(3,1,3); dn64=increment_n(3,1,3)
  q_diff32=reference_increment32(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32,3,1,3)
  n_diff32=reference_increment32(field_n,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
       msftx,msfty,xkmhd,0.125_real32,0.0625_real32,3,1,3)
  q_before=1.0_real32; n_before=1000000.0_real32
  q_after32=q_before+q_diff32; n_after32=n_before+n_diff32
  q_cont=REAL(q_before,real64)+dq64
  n_cont=REAL(n_before,real64)+dn64
  q_min_mass=1.0e-6_real64
  IF (q_cont/n_cont<q_min_mass) ERROR STOP 'REAL64 diffusion candidate missed strict lower bound'
  IF (REAL(q_after32,real64)/REAL(n_after32,real64)>=q_min_mass) &
    ERROR STOP 'R32 diffusion accumulator did not cross the strict lower bound'
  dq_correction=q_cont-REAL(q_after32,real64)
  dn_correction=n_cont-REAL(n_after32,real64)
  IF (REAL(q_after32,real64)+dq_correction/=q_cont.OR. &
      REAL(n_after32,real64)+dn_correction/=n_cont) &
    ERROR STOP 'precision correction did not reconstruct the REAL64 tendency'

  WRITE(*,'(A,1X,ES25.17E3,1X,ES25.17E3,1X,ES25.17E3,1X,ES25.17E3)') &
    'PR87_DIFFUSION64_PASS',weighted_sum,weighted_scale,q_cont/n_cont, &
    REAL(q_after32,real64)/REAL(n_after32,real64)

CONTAINS

  REAL(real64) FUNCTION reference_cell(f,m,coef1,coef2,sux,suy,vxinv,svy,tx,ty,xk,dx,dy,ii,kk,jj)
    REAL(real32),INTENT(IN) :: f(ims:ime,kms:kme,jms:jme),m(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: coef1(kms:kme),coef2(kms:kme)
    REAL(real32),INTENT(IN) :: sux(ims:ime,jms:jme),suy(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: vxinv(ims:ime,jms:jme),svy(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: tx(ims:ime,jms:jme),ty(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: xk(ims:ime,kms:kme,jms:jme),dx,dy
    INTEGER,INTENT(IN) :: ii,kk,jj
    REAL(real64) :: mu0,mum,mup,mujm,mujp,x0,xm,xp,xjm,xjp
    REAL(real64) :: dxx,dyy,fxm,fxp,fym,fyp,area_x,area_y
    mu0=REAL(coef1(kk),real64)*REAL(m(ii,jj),real64)+REAL(coef2(kk),real64)
    mum=REAL(coef1(kk),real64)*REAL(m(ii-1,jj),real64)+REAL(coef2(kk),real64)
    mup=REAL(coef1(kk),real64)*REAL(m(ii+1,jj),real64)+REAL(coef2(kk),real64)
    mujm=REAL(coef1(kk),real64)*REAL(m(ii,jj-1),real64)+REAL(coef2(kk),real64)
    mujp=REAL(coef1(kk),real64)*REAL(m(ii,jj+1),real64)+REAL(coef2(kk),real64)
    x0=REAL(xk(ii,kk,jj),real64); xm=REAL(xk(ii-1,kk,jj),real64)
    xp=REAL(xk(ii+1,kk,jj),real64); xjm=REAL(xk(ii,kk,jj-1),real64)
    xjp=REAL(xk(ii,kk,jj+1),real64)
    fxm=(REAL(sux(ii,jj),real64)/REAL(suy(ii,jj),real64))* &
      0.5_real64*(x0+xm)*0.5_real64*(mu0+mum)*REAL(dx,real64)
    fxp=(REAL(sux(ii+1,jj),real64)/REAL(suy(ii+1,jj),real64))* &
      0.5_real64*(xp+x0)*0.5_real64*(mup+mu0)*REAL(dx,real64)
    fym=(REAL(svy(ii,jj),real64)*REAL(vxinv(ii,jj),real64))* &
      0.5_real64*(x0+xjm)*0.5_real64*(mu0+mujm)*REAL(dy,real64)
    fyp=(REAL(svy(ii,jj+1),real64)*REAL(vxinv(ii,jj+1),real64))* &
      0.5_real64*(xjp+x0)*0.5_real64*(mujp+mu0)*REAL(dy,real64)
    area_x=REAL(tx(ii,jj),real64)*REAL(ty(ii,jj),real64)*REAL(dx,real64)
    area_y=REAL(tx(ii,jj),real64)*REAL(ty(ii,jj),real64)*REAL(dy,real64)
    dxx=area_x*(fxp*(REAL(f(ii+1,kk,jj),real64)-REAL(f(ii,kk,jj),real64))- &
                fxm*(REAL(f(ii,kk,jj),real64)-REAL(f(ii-1,kk,jj),real64)))
    dyy=area_y*(fyp*(REAL(f(ii,kk,jj+1),real64)-REAL(f(ii,kk,jj),real64))- &
                fym*(REAL(f(ii,kk,jj),real64)-REAL(f(ii,kk,jj-1),real64)))
    reference_cell=dxx+dyy
  END FUNCTION reference_cell

  REAL(real32) FUNCTION reference_increment32(f,m,coef1,coef2,sux,suy,vxinv,svy,tx,ty,xk,dx,dy,ii,kk,jj)
    REAL(real32),INTENT(IN) :: f(ims:ime,kms:kme,jms:jme),m(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: coef1(kms:kme),coef2(kms:kme)
    REAL(real32),INTENT(IN) :: sux(ims:ime,jms:jme),suy(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: vxinv(ims:ime,jms:jme),svy(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: tx(ims:ime,jms:jme),ty(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: xk(ims:ime,kms:kme,jms:jme),dx,dy
    INTEGER,INTENT(IN) :: ii,kk,jj
    REAL(real32) :: mkrdxm,mkrdxp,mrdx,mkrdym,mkrdyp,mrdy
    mkrdxm=(sux(ii,jj)/suy(ii,jj))*0.5_real32*(xk(ii,kk,jj)+xk(ii-1,kk,jj))* &
      0.5_real32*((coef1(kk)*m(ii,jj)+coef2(kk))+(coef1(kk)*m(ii-1,jj)+coef2(kk)))*dx
    mkrdxp=(sux(ii+1,jj)/suy(ii+1,jj))*0.5_real32*(xk(ii+1,kk,jj)+xk(ii,kk,jj))* &
      0.5_real32*((coef1(kk)*m(ii+1,jj)+coef2(kk))+(coef1(kk)*m(ii,jj)+coef2(kk)))*dx
    mrdx=tx(ii,jj)*ty(ii,jj)*dx
    mkrdym=(svy(ii,jj)*vxinv(ii,jj))*0.5_real32*(xk(ii,kk,jj)+xk(ii,kk,jj-1))* &
      0.5_real32*((coef1(kk)*m(ii,jj)+coef2(kk))+(coef1(kk)*m(ii,jj-1)+coef2(kk)))*dy
    mkrdyp=(svy(ii,jj+1)*vxinv(ii,jj+1))*0.5_real32*(xk(ii,kk,jj+1)+xk(ii,kk,jj))* &
      0.5_real32*((coef1(kk)*m(ii,jj+1)+coef2(kk))+(coef1(kk)*m(ii,jj)+coef2(kk)))*dy
    mrdy=tx(ii,jj)*ty(ii,jj)*dy
    reference_increment32=mrdx*(mkrdxp*(f(ii+1,kk,jj)-f(ii,kk,jj))- &
      mkrdxm*(f(ii,kk,jj)-f(ii-1,kk,jj)))+ &
      mrdy*(mkrdyp*(f(ii,kk,jj+1)-f(ii,kk,jj))-mkrdym*(f(ii,kk,jj)-f(ii,kk,jj-1)))
  END FUNCTION reference_increment32

END PROGRAM test_pr87_horizontal_diffusion64
