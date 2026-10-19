program test_pr87_qn_density_storage
  use iso_fortran_env, only: real32
  implicit none
  integer, parameter :: ims=1,ime=2,kms=1,kme=1,jms=1,jme=1
  real(real32) :: al(ims:ime,kms:kme,jms:jme),alb(ims:ime,kms:kme,jms:jme)
  real(real32) :: qc(ims:ime,kms:kme,jms:jme),nc(ims:ime,kms:kme,jms:jme)
  real(real32) :: qr(ims:ime,kms:kme,jms:jme),nr(ims:ime,kms:kme,jms:jme)
  real(real32) :: qc_before(ims:ime,kms:kme,jms:jme)
  real(real32) :: qr_before(ims:ime,kms:kme,jms:jme)
  real(real32) :: nc_before(ims:ime,kms:kme,jms:jme)
  real(real32) :: nr_before(ims:ime,kms:kme,jms:jme)
  logical :: valid
  external :: pr87_qn_density_store

  ! One shared non-unit density and source-derived cloud/rain intervals.
  al=0.0_real32
  alb=1.0_real32/0.5744202733039856_real32
  qc=0.0_real32; nc=0.0_real32; qr=0.0_real32; nr=0.0_real32
  qc(1,1,1)=1.0000000272452012e-27_real32
  nc(1,1,1)=2.387324008184394e-13_real32
  qr(1,1,1)=5.0788977190574514e-11_real32
  nr(1,1,1)=0.1732860952615738_real32
  nc_before=nc; nr_before=nr

  call pr87_qn_density_store(1,1,ims,ime,kms,kme,jms,jme, &
       1,2,1,1,1,1,al,alb,qc,nc,qr,nr, &
       523.59881591796875_real32,3.0_real32,12000.0_real32,500000.0_real32, &
       12566.37109375_real32,3.0_real32,961.0_real32,35000.0_real32,valid)
  if (.not.valid) error stop 'valid cloud/rain tile rejected'
  if (qc(1,1,1)<=1.0000000272452012e-27_real32) &
    error stop 'cloud strict-volume crossing did not adjust Q'
  if (qr(1,1,1)<=5.0788977190574514e-11_real32) &
    error stop 'rain strict-volume crossing did not adjust Q'
  if (any(nc/=nc_before) .or. any(nr/=nr_before)) &
    error stop 'two-species transaction changed NC or NR'

  ! Reject a later rain pair after cloud has already staged. Neither Q array
  ! may commit when one of the two species fails.
  qr(2,1,1)=-1.0_real32
  qc_before=qc; qr_before=qr; nc_before=nc; nr_before=nr
  call pr87_qn_density_store(1,2,ims,ime,kms,kme,jms,jme, &
       1,2,1,1,1,1,al,alb,qc,nc,qr,nr, &
       523.59881591796875_real32,3.0_real32,12000.0_real32,500000.0_real32, &
       12566.37109375_real32,3.0_real32,961.0_real32,35000.0_real32,valid)
  if (valid) error stop 'invalid rain pair accepted'
  if (any(qc/=qc_before) .or. any(qr/=qr_before)) &
    error stop 'failed cloud/rain transaction partially committed Q'
  if (any(nc/=nc_before) .or. any(nr/=nr_before)) &
    error stop 'failed cloud/rain transaction changed NC or NR'

  write(*,'(a)') 'PASS cloud/rain staged Q commit and tile rollback'
end program test_pr87_qn_density_storage

subroutine wrf_error_fatal(message)
  implicit none
  character(len=*), intent(in) :: message
  write(*,'(a)') trim(message)
  error stop 'unexpected WRF fatal in two-species density-store test'
end subroutine wrf_error_fatal
