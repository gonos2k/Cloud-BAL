program benchmark
 use iso_fortran_env, only: real32,real64
 use pr87_horizontal_diffusion64_baseline, only: horizontal_diffusion64_baseline
 use pr87_horizontal_diffusion64, only: horizontal_diffusion64
 implicit none
 integer,parameter :: ims=1,ime=66,kms=1,kme=39,jms=1,jme=66
 integer,parameter :: nrep=12
 real(real32),allocatable :: f(:,:,:),x(:,:,:),mut(:,:),c1(:),c2(:),ux(:,:),uy(:,:),vx(:,:),vy(:,:),tx(:,:),ty(:,:)
 real(real64),allocatable :: d64(:,:,:),d128(:,:,:)
 integer :: i,j,k,r,c0,c1tick,rate
 real(real64) :: t64,t128,sink
 allocate(f(ims:ime,kms:kme,jms:jme),x(ims:ime,kms:kme,jms:jme),mut(ims:ime,jms:jme))
 allocate(c1(kms:kme),c2(kms:kme),ux(ims:ime,jms:jme),uy(ims:ime,jms:jme))
 allocate(vx(ims:ime,jms:jme),vy(ims:ime,jms:jme),tx(ims:ime,jms:jme),ty(ims:ime,jms:jme))
 allocate(d64(ims:ime,kms:kme,jms:jme),d128(ims:ime,kms:kme,jms:jme))
 do j=jms,jme
   do i=ims,ime
     mut(i,j)=90000._real32+real(3*i+5*j,real32)
     ux(i,j)=.9_real32+.0001_real32*real(i,real32)
     uy(i,j)=.95_real32+.0001_real32*real(j,real32)
     vx(i,j)=1.01_real32+.00003_real32*real(j,real32)
     vy(i,j)=.96_real32+.00004_real32*real(i,real32)
     tx(i,j)=.97_real32+.00002_real32*real(i+j,real32)
     ty(i,j)=.98_real32+.00001_real32*real(2*i-j,real32)
     do k=kms,kme
       f(i,k,j)=real(mod(13*i+7*j+3*k,101),real32)*1.e-8_real32
       x(i,k,j)=100._real32+real(mod(5*i+11*j+7*k,47),real32)
     end do
   end do
 end do
 c1=1.25_real32; c2=-35000._real32
 sink=0._real64
 call system_clock(count_rate=rate)
 call system_clock(c0)
 do r=1,nrep
   call horizontal_diffusion64_baseline(f,mut,c1,c2,ux,uy,vx,vy,tx,ty,x, &
      2.e-4_real32,2.e-4_real32,ims,ime,kms,kme,jms,jme,2,65,2,65,kms,kme,d64)
   sink=sink+sum(d64)
 end do
 call system_clock(c1tick)
 t64=real(c1tick-c0,real64)/real(rate,real64)
 call system_clock(c0)
 do r=1,nrep
   call horizontal_diffusion64(f,mut,c1,c2,ux,uy,vx,vy,tx,ty,x, &
      2.e-4_real32,2.e-4_real32,ims,ime,kms,kme,jms,jme,2,65,2,65,kms,kme,d128)
   sink=sink+sum(d128)
 end do
 call system_clock(c1tick)
 t128=real(c1tick-c0,real64)/real(rate,real64)
 print '(A,I0,A,ES12.4,A,ES12.4,A,F8.3,A,ES14.5)', &
   'BENCH cells=64x64x39 repeats=',nrep,' R64_s=',t64,' R128_s=',t128, &
   ' ratio=',t128/t64,' sink=',sink
end program benchmark
