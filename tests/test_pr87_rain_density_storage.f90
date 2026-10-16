program test_pr87_rain_density_storage
  use iso_fortran_env, only: real32,real64
  implicit none
  integer, parameter :: ims=1,ime=4,kms=1,kme=2,jms=1,jme=4
  real(real32) :: al(ims:ime,kms:kme,jms:jme),alb(ims:ime,kms:kme,jms:jme)
  real(real32) :: qr(ims:ime,kms:kme,jms:jme),nr(ims:ime,kms:kme,jms:jme)
  real(real32) :: before(ims:ime,kms:kme,jms:jme),nr_before(ims:ime,kms:kme,jms:jme)
  real(real32) :: target_rho
  logical :: valid
  external :: pr87_rain_density_store

  target_rho=0.5744202733039856_real32
  al=0.0_real32
  alb=1.0_real32/target_rho
  qr=0.0_real32
  nr=0.0_real32
  qr(2,1,2)=5.0788977190574514e-11_real32
  nr(2,1,2)=0.1732860952615738_real32
  qr(3,1,2)=qr(2,1,2)
  nr(3,1,2)=nr(2,1,2)
  nr_before=nr

  call pr87_rain_density_store(1,1,ims,ime,kms,kme,jms,jme, &
       2,3,2,2,1,1,al,alb,qr,nr, &
       12566.37109375_real32,3.0_real32,961.0_real32,35000.0_real32,valid)
  if (.not.valid) error stop 'valid tile transaction was rejected'
  if (qr(2,1,2)==5.0788977190574514e-11_real32 .or. &
      qr(3,1,2)==5.0788977190574514e-11_real32) &
    error stop 'strict-volume crossing did not adjust Q'
  if (any(nr/=nr_before)) error stop 'tile transaction changed public N'

  ! A later-cell rejection must leave every Q in the tile at its pre-call value.
  qr(3,1,2)=-1.0_real32
  before=qr
  call pr87_rain_density_store(1,2,ims,ime,kms,kme,jms,jme, &
       2,3,2,2,1,1,al,alb,qr,nr, &
       12566.37109375_real32,3.0_real32,961.0_real32,35000.0_real32,valid)
  if (valid) error stop 'invalid tile transaction was accepted'
  if (any(qr/=before)) error stop 'failed tile transaction partially changed Q'
  if (any(nr/=nr_before)) error stop 'failed tile transaction changed public N'
  write(*,'(a)') 'PASS rain-density tile transaction, Q-only commit, and rejection rollback'
end program test_pr87_rain_density_storage

subroutine wrf_error_fatal(message)
  implicit none
  character(len=*), intent(in) :: message
  write(*,'(a)') trim(message)
  error stop 'unexpected WRF fatal in focused density-store test'
end subroutine wrf_error_fatal
