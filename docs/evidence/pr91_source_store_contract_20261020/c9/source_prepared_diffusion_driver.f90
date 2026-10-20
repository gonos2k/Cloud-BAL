
program test_source_prepared_diffusion
  use iso_fortran_env, only: real32, real64
  use pr87_horizontal_diffusion64, only: horizontal_diffusion64
  implicit none
  real(real32) :: oldq(1:10,1:1,1:3), oldn(1:10,1:1,1:3)
  real(real32) :: preparedq(1:10,1:1,1:3), preparedn(1:10,1:1,1:3)
  real(real32) :: mut(1:10,1:3), c1(1:1), c2(1:1)
  real(real32) :: ux(1:10,1:3), uy(1:10,1:3), vxinv(1:10,1:3), vy(1:10,1:3)
  real(real32) :: tx(1:10,1:3), ty(1:10,1:3), xkmhd(1:10,1:1,1:3)
  real(real32) :: qb(1,2),nb(1,2)
  real(real64) :: oldcarrier(1),qs64(1,2),ns64(1,2),source_sum64(2),dt
  real(real64) :: doldq(1:10,1:1,1:3), doldn(1:10,1:1,1:3)
  real(real64) :: dnewq(1:10,1:1,1:3), dnewn(1:10,1:1,1:3)
  real(real64) :: stale, corrected
  integer :: cell,p
  oldq=100.0_real32; oldn=1.0_real32
  preparedq=100.0_real32; preparedn=1.0_real32
  oldq(5,1,2)=900.0_real32
  mut=1.0_real32; c1=1.0_real32; c2=0.0_real32
  ux=1.0_real32; uy=1.0_real32; vxinv=1.0_real32; vy=1.0_real32
  tx=1.0_real32; ty=1.0_real32; xkmhd=1.0_real32
  dt=1.0_real64
  call horizontal_diffusion64(oldq,mut,c1,c2,ux,uy,vxinv,vy,tx,ty,xkmhd, &
       1.0_real32,0.0_real32,1,10,1,1,1,3,2,9,2,2,1,1,doldq)
  call horizontal_diffusion64(oldn,mut,c1,c2,ux,uy,vxinv,vy,tx,ty,xkmhd, &
       1.0_real32,0.0_real32,1,10,1,1,1,3,2,9,2,2,1,1,doldn)
  call horizontal_diffusion64(preparedq,mut,c1,c2,ux,uy,vxinv,vy,tx,ty,xkmhd, &
       1.0_real32,0.0_real32,1,10,1,1,1,3,2,9,2,2,1,1,dnewq)
  call horizontal_diffusion64(preparedn,mut,c1,c2,ux,uy,vxinv,vy,tx,ty,xkmhd, &
       1.0_real32,0.0_real32,1,10,1,1,1,3,2,9,2,2,1,1,dnewn)
  if (preparedq(5,1,2)/=100.0_real32 .or. preparedn(5,1,2)/=1.0_real32) stop 1
  stale=real(preparedq(5,1,2),real64)+dt*doldq(5,1,2)
  corrected=real(preparedq(5,1,2),real64)+dt*(doldq(5,1,2)+(dnewq(5,1,2)-doldq(5,1,2)))
  if (stale>=100.0_real64 .or. corrected/=100.0_real64) stop 2
  if (abs(sum(doldq(2:9,1,2))-0.0_real64)>1.0e-12_real64) stop 3
  if (any(preparedq([1,10],1,2)/=oldq([1,10],1,2))) stop 4
  if (any(dnewq(2:9,1,2)/=0.0_real64) .or. any(dnewn(2:9,1,2)/=0.0_real64)) stop 5
  qb(1,1)=100.0_real32; nb(1,1)=1.0_real32; oldcarrier(1)=1.0_real64
  qs64(1,1)=dnewq(5,1,2); ns64(1,1)=dnewn(5,1,2); cell=1; p=1
  ! C9 donor formula is inserted from the production transform below.
  source_sum64=(REAL(oldcarrier(cell),real64)*REAL([qb(cell,p),nb(cell,p)],real64)+ &
  REAL(dt,real64)*[qs64(cell,p),ns64(cell,p)])/REAL(oldcarrier(cell),real64)
  if (source_sum64(1)/=100.0_real64.or.source_sum64(2)/=1.0_real64) stop 6
  if (.not.cache_presence_ok(.true.,.true.,.true.)) stop 7
  if (.not.cache_presence_ok()) stop 8
  if (cache_presence_ok(.true.)) stop 9
  print *, 'PR91_SOURCE_PREPARED_DIFFUSION_PASS',doldq(5,1,2),doldq(6,1,2)
contains
  logical function cache_presence_ok(old_cache,bounds,valid)
    logical,optional,intent(in) :: old_cache,bounds,valid
    cache_presence_ok=.NOT.((PRESENT(old_cache) .NEQV. PRESENT(bounds)).OR. &
         (PRESENT(old_cache) .NEQV. PRESENT(valid)))
  end function cache_presence_ok
end program test_source_prepared_diffusion
