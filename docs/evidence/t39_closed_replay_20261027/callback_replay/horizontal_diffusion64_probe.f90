MODULE pr87_horizontal_diffusion64
  USE iso_fortran_env, ONLY: real32, real64, real128
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: horizontal_diffusion64

CONTAINS

  SUBROUTINE horizontal_diffusion64(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
                                    msftx,msfty,xkmhd,rdx,rdy, &
                                    ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh,increment,exact128)
    INTEGER,INTENT(IN) :: ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh
    REAL(real32),INTENT(IN) :: field(ims:ime,kms:kme,jms:jme)
    REAL(real32),INTENT(IN) :: xkmhd(ims:ime,kms:kme,jms:jme)
    REAL(real32),INTENT(IN) :: mut(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: c1(kms:kme),c2(kms:kme)
    REAL(real32),INTENT(IN) :: msfux(ims:ime,jms:jme),msfuy(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: msfvx_inv(ims:ime,jms:jme),msfvy(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: rdx,rdy
    REAL(real64),INTENT(OUT) :: increment(ims:ime,kms:kme,jms:jme)
    REAL(real128),INTENT(OUT) :: exact128(ims:ime,kms:kme,jms:jme)
    REAL(real128) :: increment128
    INTEGER :: i,j,k
    REAL(real128) :: mrdx,mrdy,mkrdxm,mkrdxp,mkrdym,mkrdyp
    REAL(real128) :: mut_i,mut_im,mut_ip,mut_jm,mut_jp
    REAL(real128) :: x_i,x_im,x_ip,x_jm,x_jp

    increment=0.0_real64
    exact128=0.0_real128
    IF (il>ih.OR.jl>jh.OR.kl>kh) RETURN
    IF (il<ims+1.OR.ih>ime-1.OR.jl<jms+1.OR.jh>jme-1.OR.kl<kms.OR.kh>kme) &
      ERROR STOP 'horizontal_diffusion64 active bounds exceed stencil storage'

    DO j=jl,jh
      DO k=kl,kh
        DO i=il,ih
          mut_i=REAL(c1(k),real128)*REAL(mut(i,j),real128)+REAL(c2(k),real128)
          mut_im=REAL(c1(k),real128)*REAL(mut(i-1,j),real128)+REAL(c2(k),real128)
          mut_ip=REAL(c1(k),real128)*REAL(mut(i+1,j),real128)+REAL(c2(k),real128)
          mut_jm=REAL(c1(k),real128)*REAL(mut(i,j-1),real128)+REAL(c2(k),real128)
          mut_jp=REAL(c1(k),real128)*REAL(mut(i,j+1),real128)+REAL(c2(k),real128)
          x_i=REAL(xkmhd(i,k,j),real128)
          x_im=REAL(xkmhd(i-1,k,j),real128)
          x_ip=REAL(xkmhd(i+1,k,j),real128)
          x_jm=REAL(xkmhd(i,k,j-1),real128)
          x_jp=REAL(xkmhd(i,k,j+1),real128)

! This is the `name='m'` face stencil in horizontal_diffusion.
          mkrdxm=(REAL(msfux(i,j),real128)/REAL(msfuy(i,j),real128))* &
            0.5_real128*(x_i+x_im)*0.5_real128*(mut_i+mut_im)*REAL(rdx,real128)
          mkrdxp=(REAL(msfux(i+1,j),real128)/REAL(msfuy(i+1,j),real128))* &
            0.5_real128*(x_ip+x_i)*0.5_real128*(mut_ip+mut_i)*REAL(rdx,real128)
          mrdx=REAL(msftx(i,j),real128)*REAL(msfty(i,j),real128)*REAL(rdx,real128)
          mkrdym=(REAL(msfvy(i,j),real128)*REAL(msfvx_inv(i,j),real128))* &
            0.5_real128*(x_i+x_jm)*0.5_real128*(mut_i+mut_jm)*REAL(rdy,real128)
          mkrdyp=(REAL(msfvy(i,j+1),real128)*REAL(msfvx_inv(i,j+1),real128))* &
            0.5_real128*(x_jp+x_i)*0.5_real128*(mut_jp+mut_i)*REAL(rdy,real128)
          mrdy=REAL(msftx(i,j),real128)*REAL(msfty(i,j),real128)*REAL(rdy,real128)

          increment128= &
            mrdx*(mkrdxp*(REAL(field(i+1,k,j),real128)-REAL(field(i,k,j),real128))- &
                  mkrdxm*(REAL(field(i,k,j),real128)-REAL(field(i-1,k,j),real128)))+ &
            mrdy*(mkrdyp*(REAL(field(i,k,j+1),real128)-REAL(field(i,k,j),real128))- &
                  mkrdym*(REAL(field(i,k,j),real128)-REAL(field(i,k,j-1),real128)))
          exact128(i,k,j)=increment128
          increment(i,k,j)=REAL(increment128,real64)
        END DO
      END DO
    END DO
  END SUBROUTINE horizontal_diffusion64

END MODULE pr87_horizontal_diffusion64
