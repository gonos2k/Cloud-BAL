program test_pr87_fogdes_source_contract
  use iso_fortran_env, only: real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use module_bl_fogdes, only: bl_fogdes_qn
  implicit none
  integer, parameter :: ims=1,ime=1,kms=1,kme=2,jms=1,jme=1
  integer, parameter :: ids=1,ide=1,jds=1,jde=1,kds=1,kde=3
  integer, parameter :: its=1,ite=1,jts=1,jte=1,kts=1,kte=2
  real(real32) :: vdfg(ims:ime,jms:jme),qc(ims:ime,kms:kme,jms:jme)
  real(real32) :: qnc(ims:ime,kms:kme,jms:jme),qv(ims:ime,kms:kme,jms:jme)
  real(real32) :: temp(ims:ime,kms:kme,jms:jme),rho(ims:ime,kms:kme,jms:jme)
  real(real32) :: dz(ims:ime,kms:kme,jms:jme),dqc(ims:ime,kms:kme,jms:jme)
  real(real32) :: dqnc(ims:ime,kms:kme,jms:jme)
  real(real32) :: ground_q(ims:ime,jms:jme),ground_n(ims:ime,jms:jme)
  real(real64) :: source_delta(ims:ime,kms:kme,jms:jme,2)
  real(real64), parameter :: pidn=real(523.59881591796875_real32,real64)
  real(real64), parameter :: strict_min=pidn/500000.0_real64**3
  real(real64), parameter :: border_q=2.312475702185084e-7_real64
  real(real64), parameter :: border_n=55206286.56624425_real64
  real(real64) :: legacy_ratio,corrected_ratio,corrected_q,corrected_n
  integer :: k,failures

  failures=0
  vdfg=0.0_real32; qc=1.0e-8_real32; qnc=2387323.5_real32
  qv=0.0_real32; temp=280.0_real32; rho=1.0_real32; dz=1.0_real32

  ! This captured source-stage endpoint divides to the exact lower bound,
  ! while the equivalent linear cone test detects the small negative residual.
  call check(border_q/border_n==strict_min,'division rounds border witness onto bound',failures)
  call check(border_q<strict_min*border_n,'linear cloud cone rejects border witness',failures)

  ! The legacy candidate accepts the literal R32 endpoint under its 8-ULP
  ! band even though its exact source-derived Q/N ratio crosses the lower edge.
  dqc=0.0_real32; dqnc=0.5_real32; source_delta=0.0_real64
  legacy_ratio=real(qc(1,1,1),real64)/ &
       real(qnc(1,1,1)+dqnc(1,1,1),real64)
  call bl_fogdes_qn(vdfg,qc,qnc,qv,temp,1.0_real32,rho,dz,0,dqc,dqnc, &
       ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
       ground_q,ground_n)
  call check(legacy_ratio<strict_min,'legacy R32 endpoint crosses exact lower bound',failures)
  call check(dqnc(1,1,1)==0.5_real32,'legacy tendency expression is retained without sidecar',failures)

  ! The same known-valid source state uses a PBL correction that cancels the
  ! R32 tendency at the actual R64 consumer. The stored tendency remains the
  ! original R32 expression; the sidecar carries its exact residual.
  dqc=0.0_real32; dqnc=0.5_real32; source_delta=0.0_real64
  source_delta(:,:,:,2)=-0.5_real64
  call bl_fogdes_qn(vdfg,qc,qnc,qv,temp,1.0_real32,rho,dz,1,dqc,dqnc, &
       ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
       ground_q,ground_n,cloud_source_delta64=source_delta,source_step=1)
  do k=kts,kte
    corrected_ratio=(real(qc(1,k,1),real64)+real(dqc(1,k,1),real64)+source_delta(1,k,1,1))/ &
        (real(qnc(1,k,1),real64)+real(dqnc(1,k,1),real64)+source_delta(1,k,1,2))
    corrected_q=real(qc(1,k,1),real64)+real(dqc(1,k,1),real64)+source_delta(1,k,1,1)
    corrected_n=real(qnc(1,k,1),real64)+real(dqnc(1,k,1),real64)+source_delta(1,k,1,2)
    call check(ieee_is_finite(dqnc(1,k,1)),'stored R32 tendency remains finite',failures)
    call check(ieee_is_finite(source_delta(1,k,1,2)),'composed source residual remains finite',failures)
    call check(corrected_ratio>=strict_min,'full R64 consumer endpoint is inside exact source bound',failures)
    call check(corrected_q>=strict_min*corrected_n,'accepted endpoint passes linear strict cone',failures)
  enddo
  if (failures/=0) error stop 1
  print '(a)', 'PR87 FogDES explicit PBL-source cases PASS'

contains
  subroutine check(condition,label,failures)
    logical,intent(in) :: condition
    character(*),intent(in) :: label
    integer,intent(inout) :: failures
    if (.not.condition) then
      failures=failures+1
      print '(a)', 'FAIL: '//label
    endif
  end subroutine check
end program test_pr87_fogdes_source_contract

subroutine wrf_error_fatal(message)
  character(*),intent(in) :: message
  print '(a)', trim(message)
  error stop 1
end subroutine wrf_error_fatal
