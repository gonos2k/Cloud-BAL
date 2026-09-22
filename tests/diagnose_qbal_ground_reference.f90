! Read-only stream driver for the conditional ground-reference model.
program diagnose_qbal_ground_reference
  use iso_fortran_env, only: real64,int64
  use qbal_ground_reference, only: build_ground_reference
  implicit none
  integer :: nn,nz,unit,j,ios,suffix
  integer(int64) :: bytes,expected
  character(1024) :: input,output
  real(real64), allocatable :: p(:),ps(:),p10(:),tv(:),terrain(:),state(:,:,:)
  real(real64), allocatable :: before(:,:),after(:,:),delta(:,:,:),bound(:,:)
  integer, allocatable :: valid(:,:),first(:),eligible(:)
  logical :: supported,ok

  call get_command_argument(1,input)
  call get_command_argument(2,output)
  open(newunit=unit,file=trim(input),status='old',access='stream',form='unformatted')
  read(unit,iostat=ios) nn,nz
  if (ios/=0) error stop 'invalid prepared header'
  if (nn<1.or.nn>1000000.or.nz<2.or.nz>1000) error stop 'invalid dimensions'
  expected=8_int64+8_int64*(nz+4_int64*nn+4_int64*nn*nz)+4_int64*nn*nz
  inquire(unit=unit,size=bytes)
  if (bytes/=expected) error stop 'invalid prepared extent'
  allocate(p(nz),ps(nn),p10(nn),tv(nn),terrain(nn),state(nn,nz,4),valid(nn,nz))
  read(unit,iostat=ios) p,ps,p10,tv,terrain,state,valid
  if (ios/=0) error stop 'invalid prepared payload'
  read(unit,iostat=ios) suffix
  if (ios>=0) error stop 'unexpected prepared suffix'
  close(unit)
  if (any(valid/=0.and.valid/=1)) error stop 'invalid support flag'
  allocate(first(nn),eligible(nn),before(nn,nz),after(nn,nz),delta(3,nn,nz),bound(nn,nz))
  do j=1,nn
    call build_ground_reference(p,ps(j),p10(j),tv(j),terrain(j), &
      state(j,:,1),state(j,:,2),state(j,:,3),state(j,:,4),valid(j,:)==1, &
      before(j,:),after(j,:),delta(:,j,:),bound(j,:),first(j),supported,ok)
    if (.not.ok) error stop 'invalid ground-reference column'
    eligible(j)=merge(1,0,supported)
  end do
  ! Do not open the output until every column has been validated.
  open(newunit=unit,file=trim(output),status='new',access='stream',form='unformatted')
  write(unit) first,eligible,before,after,delta,bound
  close(unit)
end program diagnose_qbal_ground_reference
