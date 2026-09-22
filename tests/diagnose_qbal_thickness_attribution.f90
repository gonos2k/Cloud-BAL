! Read-only paired-state layer diagnostic; no geometry or state correction.
program diagnose_qbal_thickness_attribution
  use iso_fortran_env, only: real64, int64
  use ieee_arithmetic, only: ieee_is_finite, ieee_value, ieee_quiet_nan
  use qbal_thickness_attribution, only: thickness_change
  implicit none
  integer :: nn,nz,unit,j,k,ios
  integer(int64) :: bytes
  character(1024) :: input,output
  real(real64), allocatable :: p(:),ps(:),state(:,:,:),layer(:,:,:),column(:,:)
  integer, allocatable :: valid(:,:),supported(:,:)
  real(real64) :: values(9),nan,pair(2,5)
  logical :: ok

  call get_command_argument(1,input)
  call get_command_argument(2,output)
  open(newunit=unit,file=trim(input),status='old',access='stream',form='unformatted')
  read(unit) nn,nz
  if (nn<1.or.nn>1000000.or.nz<2.or.nz>1000) error stop 'invalid dimensions'
  inquire(unit=unit,size=bytes)
  if (bytes/=8_int64+8_int64*(nz+nn+5_int64*nn*nz)+4_int64*nn*nz) &
    error stop 'invalid prepared extent'
  allocate(p(nz),ps(nn),state(nn,nz,5),valid(nn,nz))
  read(unit) p,ps,state,valid
  read(unit,iostat=ios) j
  if (ios>=0) error stop 'unexpected prepared suffix'
  close(unit)
  if (.not.all(ieee_is_finite(p)).or..not.all(ieee_is_finite(ps))) error stop 'invalid pressure'
  if (any(p<100).or.any(p>120000).or.any(ps<100).or.any(ps>120000)) error stop 'pressure outside range'
  if (any(p<=0).or.any(p(:nz-1)<=p(2:)).or.any(ps<=p(nz))) error stop 'invalid pressure ordering'
  if (any(valid/=0.and.valid/=1)) error stop 'invalid support flag'
  do k=1,nz
    if (any(valid(:,k)==1.and.p(k)>ps)) error stop 'underground support flag'
  end do
  nan=ieee_value(0._real64,ieee_quiet_nan)
  allocate(layer(9,nn,nz-1),column(9,nn),supported(nn,nz-1))
  layer=nan;column=nan;supported=0
  do j=1,nn
    do k=1,nz-1
      if (valid(j,k)==0.or.valid(j,k+1)==0) cycle
      pair=state(j,k:k+1,:)
      call thickness_change(p(k),p(k+1),pair(:,1),pair(:,2), &
        pair(:,3),pair(:,4),values(1),values(2),values(3),values(4), &
        values(5),values(6),ok)
      if (.not.ok) error stop 'invalid supported thermodynamic layer'
      if (.not.all(ieee_is_finite(state(j,k:k+1,5)))) error stop 'invalid supported HT'
      values(7)=state(j,k+1,5)-state(j,k,5)-values(1)
      values(8)=state(j,k+1,5)-state(j,k,5)-values(2)
      values(9)=values(3)+values(4)-values(5)
      if (abs(values(9))>values(6)) error stop 'symmetric attribution does not close'
      if (abs((values(8)-values(7))+values(5))>values(6)) error stop 'HT difference does not close'
      layer(:,j,k)=values
      supported(j,k)=1
    end do
    if (any(supported(j,:)==1)) then
      column(:,j)=0
      do k=1,nz-1
        if (supported(j,k)==1) column(:,j)=column(:,j)+layer(:,j,k)
      end do
    end if
  end do
  ! These are sums over matched layers, NOT surface-to-top completed columns.
  open(newunit=unit,file=trim(output),status='new',access='stream',form='unformatted')
  write(unit) supported,layer,column
  close(unit)
end program diagnose_qbal_thickness_attribution
