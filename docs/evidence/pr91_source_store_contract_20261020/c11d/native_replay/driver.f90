program c11d_replay
  use iso_fortran_env, only: int32,int64,real32,real64
  use pr87_horizontal_diffusion64, only: horizontal_diffusion64
  implicit none
  real(real32) :: q(1:3,1:1,1:3), n(1:3,1:1,1:3)
  real(real32) :: mut(1:3,1:3), xkmhd(1:3,1:1,1:3)
  real(real32) :: c1(1:1),c2(1:1),msfux(1:3,1:3),msfuy(1:3,1:3)
  real(real32) :: msfvx_inv(1:3,1:3),msfvy(1:3,1:3),msftx(1:3,1:3),msfty(1:3,1:3)
  real(real32) :: rdx,rdy
  real(real64) :: dq(1:3,1:1,1:3),dn(1:3,1:1,1:3),qs,ns,qdonor,ndonor
  real(real64) :: qsrc,dq_later,dqold,dqnew,nsrc,dn_later,dnold,dnnew,carrier,dt
  integer :: i,j,k
  q=0.0_real32; n=0.0_real32; mut=0.0_real32; xkmhd=0.0_real32
  msfux=0.0_real32; msfuy=0.0_real32; msfvx_inv=0.0_real32
  msfvy=0.0_real32; msftx=0.0_real32; msfty=0.0_real32
  i=2; j=2; k=1
  q(2,1,3)=transfer(int(z'18CC802B',int32),0.0_real32)
  n(2,1,3)=transfer(int(z'2E74C69C',int32),0.0_real32)
  xkmhd(1,1,1)=transfer(int(z'44AECEBA',int32),0.0_real32)
  xkmhd(2,1,1)=transfer(int(z'441808C9',int32),0.0_real32)
  xkmhd(3,1,1)=transfer(int(z'00000000',int32),0.0_real32)
  xkmhd(1,1,2)=transfer(int(z'44BCE6E3',int32),0.0_real32)
  xkmhd(2,1,2)=transfer(int(z'444E74FF',int32),0.0_real32)
  xkmhd(3,1,2)=transfer(int(z'00000000',int32),0.0_real32)
  xkmhd(1,1,3)=transfer(int(z'449A32C7',int32),0.0_real32)
  xkmhd(2,1,3)=transfer(int(z'44A9F136',int32),0.0_real32)
  xkmhd(3,1,3)=transfer(int(z'00000000',int32),0.0_real32)
  mut(1,1)=transfer(int(z'47BA560F',int32),0.0_real32)
  mut(2,1)=transfer(int(z'47BA5C02',int32),0.0_real32)
  mut(3,1)=transfer(int(z'47B9FC3D',int32),0.0_real32)
  mut(1,2)=transfer(int(z'47BA54F1',int32),0.0_real32)
  mut(2,2)=transfer(int(z'47BA4EF6',int32),0.0_real32)
  mut(3,2)=transfer(int(z'47B9AA80',int32),0.0_real32)
  mut(1,3)=transfer(int(z'47BA44FD',int32),0.0_real32)
  mut(2,3)=transfer(int(z'47B9C1C8',int32),0.0_real32)
  mut(3,3)=transfer(int(z'47B929FB',int32),0.0_real32)
  c1(1)=transfer(int(z'3F81B972',int32),0.0_real32)
  c2(1)=transfer(int(z'C49FFA66',int32),0.0_real32)
  msfux(2,2)=transfer(int(z'3F7C0127',int32),0.0_real32)
  msfux(3,2)=transfer(int(z'3F7C01ED',int32),0.0_real32)
  msfuy(2,2)=transfer(int(z'3F7C0127',int32),0.0_real32)
  msfuy(3,2)=transfer(int(z'3F7C01ED',int32),0.0_real32)
  msfvx_inv(2,1)=transfer(int(z'3F81FFEB',int32),0.0_real32)
  msfvx_inv(2,2)=transfer(int(z'3F8204DE',int32),0.0_real32)
  msfvx_inv(2,3)=transfer(int(z'3F8209CD',int32),0.0_real32)
  msfvy(2,1)=transfer(int(z'3F7C0FEA',int32),0.0_real32)
  msfvy(2,2)=transfer(int(z'3F7C0652',int32),0.0_real32)
  msfvy(2,3)=transfer(int(z'3F7BFCC2',int32),0.0_real32)
  msftx(2,2)=transfer(int(z'3F7C0189',int32),0.0_real32)
  msfty(2,2)=transfer(int(z'3F7C0189',int32),0.0_real32)
  rdx=transfer(int(z'3951B717',int32),0.0_real32)
  rdy=transfer(int(z'3951B717',int32),0.0_real32)
  call horizontal_diffusion64(q,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy,msftx,msfty, &
       xkmhd,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,dq)
  call horizontal_diffusion64(n,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy,msftx,msfty, &
       xkmhd,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,dn)
  qsrc=transfer(int(z'3EAA8DB720000000',int64),0.0_real64)
  dq_later=transfer(int(z'BD3107FF59800000',int64),0.0_real64)
  dqold=transfer(int(z'3EAA8DB6FDF0014D',int64),0.0_real64)
  dqnew=dq(2,1,2)
  nsrc=transfer(int(z'41255E0620000000',int64),0.0_real64)
  dn_later=transfer(int(z'BFB2973641800000',int64),0.0_real64)
  dnold=transfer(int(z'41255E05FAD1937D',int64),0.0_real64)
  dnnew=dn(2,1,2)
  carrier=real(transfer(int(z'47BA53F4',int32),0.0_real32),real64)
  dt=real(transfer(int(z'41A00000',int32),0.0_real32),real64)
  qs=qsrc+ dq_later
  qs=qs+(dqnew-dqold)
  ns=nsrc+dn_later
  ns=ns+(dnnew-dnold)
  qdonor=(carrier*0.0_real64+dt*qs)/carrier
  ndonor=(carrier*0.0_real64+dt*ns)/carrier
  write(*,'(a,2(1x,z16.16))') 'D_PREPARED',transfer(dqnew,0_int64),transfer(dnnew,0_int64)
  write(*,'(a,2(1x,z16.16))') 'SOURCE_PLUS_DELTA',transfer(qsrc+dq_later,0_int64),transfer(nsrc+dn_later,0_int64)
  write(*,'(a,2(1x,z16.16))') 'D_PREPARED_MINUS_OLD',transfer(dqnew-dqold,0_int64),transfer(dnnew-dnold,0_int64)
  write(*,'(a,2(1x,z16.16))') 'FINAL_QS_NS',transfer(qs,0_int64),transfer(ns,0_int64)
  write(*,'(a,2(1x,z16.16))') 'DONOR_QN',transfer(qdonor,0_int64),transfer(ndonor,0_int64)
  write(*,'(a,2(1x,es26.17))') 'DONOR_QN_DEC',qdonor,ndonor
end program c11d_replay
