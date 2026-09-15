program test_qbal_nonlin_caller
  use, intrinsic :: iso_fortran_env, only: int32
  implicit none
  real :: to(4,4,4),uo(4,4,4),vo(4,4,4),omo(4,4,4)
  real :: t(4,4,4),u(4,4,4),v(4,4,4),om(4,4,4)
  real :: tb(4,4,4),ub(4,4,4),vb(4,4,4),omb(4,4,4)
  real :: nu(4,4,4),nv(4,4,4),saved(4,4,4,8),dp(4),p(4)
  integer :: k,status
  external :: caller_fragment

  p=[100000.,90000.,85000.,70000.]
  dp(1)=0.
  dp(2:4)=p(1:3)-p(2:4)
  tb=300.
  do k=1,4
    ub(:,:,k)=1.e-4*p(k)
    vb(:,:,k)=-2.e-4*p(k)
  end do
  omb=0.5
  call prepare()
  ! The real caller must subtract U/V backgrounds but pass total OM.
  call run()
  if(status/=1) error stop 'caller valid status'
  if(any(uo/=0.).or.any(vo/=0.)) error stop 'caller perturbations'
  if(any(nu/=0.).or.any(nv/=0.)) error stop 'caller zero perturbation'
  if(any(om/=omb)) error stop 'caller changed total omega'

  call prepare()
  om=omo
  call run()
  if(status/=1) error stop 'caller nonzero omega status'
  if(abs(nu(2,2,2)-2.5e-5)>1.e-9) error stop 'caller delta omega U'
  if(abs(nv(2,2,2)+5.e-5)>1.e-9) error stop 'caller delta omega V'
  if(any(om/=omo)) error stop 'caller changed nonzero total omega'

  call prepare()
  uo=uo+1.
  vo=vo+2.
  ! Equal missing donors must fail, even though their difference is zero.
  om(3,3,3)=1.e37
  omb(3,3,3)=1.e37
  saved(:,:,:,1)=t; saved(:,:,:,2)=u
  saved(:,:,:,3)=v; saved(:,:,:,4)=om
  saved(:,:,:,5)=to; saved(:,:,:,6)=uo
  saved(:,:,:,7)=vo; saved(:,:,:,8)=omo
  call run()
  if(status/=0) error stop 'caller missing donor accepted'
  call same_bits(t,saved(:,:,:,1))
  call same_bits(u,saved(:,:,:,2))
  call same_bits(v,saved(:,:,:,3))
  call same_bits(om,saved(:,:,:,4))
  call same_bits(to,saved(:,:,:,5))
  call same_bits(uo,saved(:,:,:,6))
  call same_bits(vo,saved(:,:,:,7))
  call same_bits(omo,saved(:,:,:,8))
  print *, 'QBAL caller fragments: perturbation and eight-array rollback PASS'
contains
  subroutine prepare()
    to=tb
    uo=ub
    vo=vb
    omo=0.75
    t=301.
    u=11.
    v=12.
    om=omb
  end subroutine
  subroutine run()
    call caller_fragment(to,uo,vo,omo,t,u,v,om,tb,ub,vb,omb,dp,nu,nv,status)
  end subroutine
  subroutine same_bits(actual,expected)
    real,intent(in) :: actual(4,4,4),expected(4,4,4)
    if(any(transfer(actual,[0_int32],64)/=transfer(expected,[0_int32],64))) &
      error stop 'caller rollback changed bits'
  end subroutine
end program
