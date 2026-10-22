program pr99_native_consumer_driver
  use module_big_step_utilities_em, only: calc_ww_cp
  implicit none
  integer, parameter :: ni=235, nj=283, nk=39, nkf=nk+1
  integer, parameter :: ids=1, ide=ni, jds=1, jde=nj, kds=1, kde=nkf
  integer, parameter :: ims=1, ime=ni, jms=1, jme=nj, kms=1, kme=nkf
  integer, parameter :: its=2, ite=ni-2, jts=2, jte=nj-2, kts=1, kte=nkf
  real :: u(ims:ime,kms:kme,jms:jme), v(ims:ime,kms:kme,jms:jme)
  real :: ww(ims:ime,kms:kme,jms:jme)
  real :: mu(ims:ime,jms:jme), mub(ims:ime,jms:jme)
  real :: msftx(ims:ime,jms:jme), msfty(ims:ime,jms:jme)
  real :: msfux(ims:ime,jms:jme), msfuy(ims:ime,jms:jme)
  real :: msfvx(ims:ime,jms:jme), msfvx_inv(ims:ime,jms:jme)
  real :: msfvy(ims:ime,jms:jme)
  real :: c1h(kms:kme), c2h(kms:kme), dnw(kms:kme)
  real :: rdx, rdy
  integer :: unit

  open(newunit=unit,file='native_consumer_input.bin',status='old', &
       access='stream',form='unformatted',action='read')
  read(unit) u, v, mu, mub, c1h, c2h, dnw, msftx, msfty, &
             msfux, msfuy, msfvx, msfvx_inv, msfvy, rdx, rdy
  close(unit)

  ww = 0.0
  call calc_ww_cp(u,v,mu,mub,c1h,c2h,ww,rdx,rdy,msftx,msfty, &
       msfux,msfuy,msfvx,msfvx_inv,msfvy,dnw, &
       ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
       its,ite,jts,jte,kts,kte)

  open(newunit=unit,file='native_consumer_ww.bin',status='replace', &
       access='stream',form='unformatted',action='write')
  write(unit) ww
  close(unit)
end program pr99_native_consumer_driver
