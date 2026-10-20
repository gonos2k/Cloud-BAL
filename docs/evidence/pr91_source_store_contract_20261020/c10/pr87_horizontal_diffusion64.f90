MODULE pr87_horizontal_diffusion64
  USE iso_fortran_env, ONLY: real32, real64
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: horizontal_diffusion64

CONTAINS

  SUBROUTINE horizontal_diffusion64(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
                                    msftx,msfty,xkmhd,rdx,rdy, &
                                    ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh,increment)
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
    INTEGER :: i,j,k
    REAL(real64) :: mrdx,mrdy,mkrdxm,mkrdxp,mkrdym,mkrdyp
    REAL(real64) :: mut_i,mut_im,mut_ip,mut_jm,mut_jp
    REAL(real64) :: x_i,x_im,x_ip,x_jm,x_jp

    increment=0.0_real64
    IF (il>ih.OR.jl>jh.OR.kl>kh) RETURN
    IF (il<ims+1.OR.ih>ime-1.OR.jl<jms+1.OR.jh>jme-1.OR.kl<kms.OR.kh>kme) &
      ERROR STOP 'horizontal_diffusion64 active bounds exceed stencil storage'

    DO j=jl,jh
      DO k=kl,kh
        DO i=il,ih
          mut_i=REAL(c1(k),real64)*REAL(mut(i,j),real64)+REAL(c2(k),real64)
          mut_im=REAL(c1(k),real64)*REAL(mut(i-1,j),real64)+REAL(c2(k),real64)
          mut_ip=REAL(c1(k),real64)*REAL(mut(i+1,j),real64)+REAL(c2(k),real64)
          mut_jm=REAL(c1(k),real64)*REAL(mut(i,j-1),real64)+REAL(c2(k),real64)
          mut_jp=REAL(c1(k),real64)*REAL(mut(i,j+1),real64)+REAL(c2(k),real64)
          x_i=REAL(xkmhd(i,k,j),real64)
          x_im=REAL(xkmhd(i-1,k,j),real64)
          x_ip=REAL(xkmhd(i+1,k,j),real64)
          x_jm=REAL(xkmhd(i,k,j-1),real64)
          x_jp=REAL(xkmhd(i,k,j+1),real64)

          ! This is the `name='m'` face stencil in horizontal_diffusion.
          mkrdxm=(REAL(msfux(i,j),real64)/REAL(msfuy(i,j),real64))* &
            0.5_real64*(x_i+x_im)*0.5_real64*(mut_i+mut_im)*REAL(rdx,real64)
          mkrdxp=(REAL(msfux(i+1,j),real64)/REAL(msfuy(i+1,j),real64))* &
            0.5_real64*(x_ip+x_i)*0.5_real64*(mut_ip+mut_i)*REAL(rdx,real64)
          mrdx=REAL(msftx(i,j),real64)*REAL(msfty(i,j),real64)*REAL(rdx,real64)
          mkrdym=(REAL(msfvy(i,j),real64)*REAL(msfvx_inv(i,j),real64))* &
            0.5_real64*(x_i+x_jm)*0.5_real64*(mut_i+mut_jm)*REAL(rdy,real64)
          mkrdyp=(REAL(msfvy(i,j+1),real64)*REAL(msfvx_inv(i,j+1),real64))* &
            0.5_real64*(x_jp+x_i)*0.5_real64*(mut_jp+mut_i)*REAL(rdy,real64)
          mrdy=REAL(msftx(i,j),real64)*REAL(msfty(i,j),real64)*REAL(rdy,real64)

          increment(i,k,j)= &
            mrdx*(mkrdxp*(REAL(field(i+1,k,j),real64)-REAL(field(i,k,j),real64))- &
                  mkrdxm*(REAL(field(i,k,j),real64)-REAL(field(i-1,k,j),real64)))+ &
            mrdy*(mkrdyp*(REAL(field(i,k,j+1),real64)-REAL(field(i,k,j),real64))- &
                  mkrdym*(REAL(field(i,k,j),real64)-REAL(field(i,k,j-1),real64)))
        END DO
      END DO
    END DO
  END SUBROUTINE horizontal_diffusion64

END MODULE pr87_horizontal_diffusion64
