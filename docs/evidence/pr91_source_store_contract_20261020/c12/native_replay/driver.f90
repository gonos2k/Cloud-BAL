program c12_native_kernel_expression_replay
  use iso_fortran_env, only: int32,int64,real32,real64
  use pr87_horizontal_diffusion64, only: horizontal_diffusion64
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  integer,parameter :: P_QC=1,P_QI=2,P_QNC=3,P_QNI=4
  real(real32) :: q(1:3,1:1,1:3),n(1:3,1:1,1:3)
  real(real32) :: mut(1:3,1:3),xkmhd(1:3,1:1,1:3)
  real(real32) :: c1(1:1),c2(1:1),msfux(1:3,1:3),msfuy(1:3,1:3)
  real(real32) :: msfvx_inv(1:3,1:3),msfvy(1:3,1:3),msftx(1:3,1:3),msfty(1:3,1:3)
  real(real32) :: rdx,rdy,rho,carrier32,newcarrier32,dt32,stored_q,stored_n
  real(real32) :: pr87_all_pair_diffusion_tendency32(1,1,1,8)
  real(real32) :: pr87_coupled_qsrc(1,1,1,2),pr87_coupled_nsrc(1,1,1,2)
  real(real32) :: moist_tend(1,1,1,4),scalar_tend(1,1,1,4)
  real(real64) :: dq(1:3,1:1,1:3),dn(1:3,1:1,1:3)
  real(real64) :: pr87_all_pair_diffusion_nonD64(1,1,1,4),q_rate,n_rate,q_value,n_value
  real(real64) :: carrier,newcarrier,dt,minmass,maxmass,bmin,bmax
  integer :: i,j,k,adjustment,failure_stage
  logical :: valid
  q=0.0_real32;n=0.0_real32;mut=0.0_real32;xkmhd=0.0_real32
  msfux=0.0_real32;msfuy=0.0_real32;msfvx_inv=0.0_real32
  msfvy=0.0_real32;msftx=0.0_real32;msfty=0.0_real32
  i=1;j=1;k=1
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
  ! C11 capture has a zero old Q/N center and the exact stencil used below.
  ! nonD64=0 is deliberately manufactured; C11 did not capture its C12 decomposition operands.
  pr87_all_pair_diffusion_tendency32=0.0_real32
  pr87_coupled_qsrc=0.0_real32;pr87_coupled_nsrc=0.0_real32
  moist_tend=0.0_real32;scalar_tend=0.0_real32;pr87_all_pair_diffusion_nonD64=0.0_real64
                     pr87_all_pair_diffusion_nonD64(1,1,1,1) = &
                       (REAL(moist_tend(1,1,1,P_QC),real64)- &
                        REAL(pr87_all_pair_diffusion_tendency32(1,1,1,5),real64)) + &
                       (REAL(pr87_all_pair_diffusion_tendency32(1,1,1,1),real64)- &
                        REAL(pr87_coupled_qsrc(1,1,1,1),real64))
                   pr87_all_pair_diffusion_nonD64(1,1,1,2) = &
                       (REAL(scalar_tend(1,1,1,P_QNC),real64)- &
                        REAL(pr87_all_pair_diffusion_tendency32(1,1,1,6),real64)) + &
                       (REAL(pr87_all_pair_diffusion_tendency32(1,1,1,2),real64)- &
                        REAL(pr87_coupled_nsrc(1,1,1,1),real64))
                   pr87_all_pair_diffusion_nonD64(1,1,1,3) = &
                       (REAL(moist_tend(1,1,1,P_QI),real64)- &
                        REAL(pr87_all_pair_diffusion_tendency32(1,1,1,7),real64)) + &
                       (REAL(pr87_all_pair_diffusion_tendency32(1,1,1,3),real64)- &
                        REAL(pr87_coupled_qsrc(1,1,1,2),real64))
                   pr87_all_pair_diffusion_nonD64(1,1,1,4) = &
                       (REAL(scalar_tend(1,1,1,P_QNI),real64)- &
                        REAL(pr87_all_pair_diffusion_tendency32(1,1,1,8),real64)) + &
                       (REAL(pr87_all_pair_diffusion_tendency32(1,1,1,4),real64)- &
                        REAL(pr87_coupled_nsrc(1,1,1,2),real64))
  ! C12 source expression: separated nonD plus the complete prepared R128 diffusion rate once.
  q_rate=pr87_all_pair_diffusion_nonD64(1,1,1,1)+dq(2,1,2)
  n_rate=pr87_all_pair_diffusion_nonD64(1,1,1,2)+dn(2,1,2)
  carrier32=transfer(int(z'47BA53F4',int32),0.0_real32)
  newcarrier32=transfer(int(z'47BA40B0',int32),0.0_real32)
  rho=transfer(int(z'3F9945D4',int32),0.0_real32)
  dt32=transfer(int(z'41A00000',int32),0.0_real32)
  carrier=real(carrier32,real64);newcarrier=real(newcarrier32,real64);dt=real(dt32,real64)
  minmass=transfer(int(z'3CF2DD58BFD7689A',int64),0.0_real64)
  maxmass=transfer(int(z'3DF4D2954D1355A3',int64),0.0_real64)
  bmin=transfer(int(z'41ED718CBAEB47A8',int64),0.0_real64)
  bmax=transfer(int(z'42F03FEF587F51E0',int64),0.0_real64)
  q_value=(carrier*0.0_real64+dt*q_rate)/newcarrier
  n_value=(carrier*0.0_real64+dt*n_rate)/newcarrier
  call joint_moment_store(q_value,n_value,rho,minmass,maxmass,.true.,stored_q,stored_n, &
       adjustment,valid,allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       volume_number_bounds=[bmin,bmax],strict_mass_ratio=.true.,failure_stage=failure_stage)
  if (.not.valid.or.failure_stage/=0) stop 1
  write(*,'(a,2(1x,z16.16))') 'D_PREPARED_R128',transfer(dq(2,1,2),0_int64),transfer(dn(2,1,2),0_int64)
  write(*,'(a,2(1x,z16.16))') 'C12_NOND',transfer(pr87_all_pair_diffusion_nonD64(1,1,1,1),0_int64), &
       transfer(pr87_all_pair_diffusion_nonD64(1,1,1,2),0_int64)
  write(*,'(a,2(1x,z16.16))') 'C12_SOURCE_RATES',transfer(q_rate,0_int64),transfer(n_rate,0_int64)
  write(*,'(a,2(1x,z16.16))') 'C12_DONOR_R64',transfer(q_value,0_int64),transfer(n_value,0_int64)
  write(*,'(a,2(1x,z8.8),1x,i0,1x,i0)') 'STRICT_FINAL_STORE',transfer(stored_q,0_int32), &
       transfer(stored_n,0_int32),failure_stage,adjustment
end program c12_native_kernel_expression_replay
