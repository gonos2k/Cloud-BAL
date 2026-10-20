module d1_graupel_adapter
  use iso_fortran_env, only: int32,int64,real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer,parameter :: real128=selected_real_kind(33,4931)
  integer,parameter :: ims=-1,ime=1,kms=1,kme=1,jms=-1,jme=1
  real(real32) :: mut_diff(-1:1,-1:1),xkmhd_diff(-1:1,1:1,-1:1)
  real(real32) :: msfux_diff(-1:2,-1:1),msfuy_diff(-1:2,-1:1)
  real(real32) :: msfvx_inv_diff(-1:1,-1:1),msfvy_diff(-1:1,-1:2)
  real(real32) :: msftx(-1:1,-1:1),msfty(-1:1,-1:1),c1(1:1),c2(1:1)
  real(real32) :: rdx,rdy
contains

  SUBROUTINE graupel_diffusion_point(field,i,k,j,increment,face_coefficients,valid)
    INTEGER,INTENT(IN) :: i,k,j
    REAL(real32),INTENT(IN) :: field(ims:ime,kms:kme,jms:jme)
    REAL(real64),INTENT(OUT) :: increment
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128),INTENT(OUT) :: face_coefficients(4)
    LOGICAL,INTENT(OUT) :: valid
    REAL(real128) :: increment128,mrdx,mrdy,mkrdxm,mkrdxp,mkrdym,mkrdyp
    REAL(real128) :: mut_i,mut_im,mut_ip,mut_jm,mut_jp
    REAL(real128) :: x_i,x_im,x_ip,x_jm,x_jp
    increment=0.0_real64; face_coefficients=0.0_real128; valid=.FALSE.
    IF (i<ims+1.OR.i>ime-1.OR.j<jms+1.OR.j>jme-1.OR.k<kms.OR.k>kme) RETURN
    IF (.NOT.ALL(ieee_is_finite([field(i,k,j),field(i-1,k,j),field(i+1,k,j), &
        field(i,k,j-1),field(i,k,j+1),mut_diff(i,j),mut_diff(i-1,j),mut_diff(i+1,j), &
        mut_diff(i,j-1),mut_diff(i,j+1),xkmhd_diff(i,k,j),xkmhd_diff(i-1,k,j), &
        xkmhd_diff(i+1,k,j),xkmhd_diff(i,k,j-1),xkmhd_diff(i,k,j+1), &
        msfux_diff(i,j),msfuy_diff(i,j),msfux_diff(i+1,j),msfuy_diff(i+1,j), &
        msfvx_inv_diff(i,j),msfvy_diff(i,j),msfvx_inv_diff(i,j+1),msfvy_diff(i,j+1), &
        msftx(i,j),msfty(i,j),c1(k),c2(k),rdx,rdy]))) RETURN
    IF (msfuy_diff(i,j)==0.0.OR.msfuy_diff(i+1,j)==0.0) RETURN
    mut_i=REAL(c1(k),real128)*REAL(mut_diff(i,j),real128)+REAL(c2(k),real128)
    mut_im=REAL(c1(k),real128)*REAL(mut_diff(i-1,j),real128)+REAL(c2(k),real128)
    mut_ip=REAL(c1(k),real128)*REAL(mut_diff(i+1,j),real128)+REAL(c2(k),real128)
    mut_jm=REAL(c1(k),real128)*REAL(mut_diff(i,j-1),real128)+REAL(c2(k),real128)
    mut_jp=REAL(c1(k),real128)*REAL(mut_diff(i,j+1),real128)+REAL(c2(k),real128)
    x_i=REAL(xkmhd_diff(i,k,j),real128); x_im=REAL(xkmhd_diff(i-1,k,j),real128)
    x_ip=REAL(xkmhd_diff(i+1,k,j),real128); x_jm=REAL(xkmhd_diff(i,k,j-1),real128)
    x_jp=REAL(xkmhd_diff(i,k,j+1),real128)
    mkrdxm=(REAL(msfux_diff(i,j),real128)/REAL(msfuy_diff(i,j),real128))* &
      0.5_real128*(x_i+x_im)*0.5_real128*(mut_i+mut_im)*REAL(rdx,real128)
    mkrdxp=(REAL(msfux_diff(i+1,j),real128)/REAL(msfuy_diff(i+1,j),real128))* &
      0.5_real128*(x_ip+x_i)*0.5_real128*(mut_ip+mut_i)*REAL(rdx,real128)
    mrdx=REAL(msftx(i,j),real128)*REAL(msfty(i,j),real128)*REAL(rdx,real128)
    mkrdym=(REAL(msfvy_diff(i,j),real128)*REAL(msfvx_inv_diff(i,j),real128))* &
      0.5_real128*(x_i+x_jm)*0.5_real128*(mut_i+mut_jm)*REAL(rdy,real128)
    mkrdyp=(REAL(msfvy_diff(i,j+1),real128)*REAL(msfvx_inv_diff(i,j+1),real128))* &
      0.5_real128*(x_jp+x_i)*0.5_real128*(mut_jp+mut_i)*REAL(rdy,real128)
    mrdy=REAL(msftx(i,j),real128)*REAL(msfty(i,j),real128)*REAL(rdy,real128)
    face_coefficients=[mrdx*mkrdxp,mrdx*mkrdxm,mrdy*mkrdyp,mrdy*mkrdym]
    IF (.NOT.ALL(ieee_is_finite(face_coefficients))) RETURN
    IF (ANY(face_coefficients<0.0_real128)) RETURN
    increment128= &
      mrdx*(mkrdxp*(REAL(field(i+1,k,j),real128)-REAL(field(i,k,j),real128))- &
            mkrdxm*(REAL(field(i,k,j),real128)-REAL(field(i-1,k,j),real128)))+ &
      mrdy*(mkrdyp*(REAL(field(i,k,j+1),real128)-REAL(field(i,k,j),real128))- &
            mkrdym*(REAL(field(i,k,j),real128)-REAL(field(i,k,j-1),real128)))
    increment=REAL(increment128,real64)
    IF (.NOT.ieee_is_finite(increment)) RETURN
    valid=.TRUE.
  END SUBROUTINE graupel_diffusion_point

  PURE LOGICAL FUNCTION strict_graupel_pair(q,n,minimum_ratio,maximum_ratio)
    REAL(real64),INTENT(IN) :: q,n,minimum_ratio,maximum_ratio
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128) :: q128,n128
    strict_graupel_pair=.FALSE.
    IF (.NOT.ALL(ieee_is_finite([q,n,minimum_ratio,maximum_ratio]))) RETURN
    IF (q<0.0_real64.OR.n<0.0_real64.OR.minimum_ratio<=0.0_real64.OR. &
        maximum_ratio<minimum_ratio) RETURN
    IF (q==0.0_real64.AND.n==0.0_real64) THEN
      strict_graupel_pair=.TRUE.; RETURN
    END IF
    IF (q<=0.0_real64.OR.n<=0.0_real64) RETURN
    q128=REAL(q,real128); n128=REAL(n,real128)
    strict_graupel_pair=q128>=REAL(minimum_ratio,real128)*n128.AND. &
                        q128<=REAL(maximum_ratio,real128)*n128
  END FUNCTION strict_graupel_pair
end module d1_graupel_adapter
