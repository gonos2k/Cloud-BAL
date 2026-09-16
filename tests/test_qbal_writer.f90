program test_qbal_writer
  use, intrinsic :: iso_fortran_env, only: int32
  implicit none
  integer, parameter :: nx=6,ny=6,nz=4,i4time=2000000000
  integer(int32) :: dimensions(3)
  integer :: unit,ios,status
  real :: p(nz),u(nx,ny,nz),v(nx,ny,nz),phi(nx,ny,nz),temperature(nx,ny,nz)
  real :: moisture(nx,ny,nz),omega(nx,ny,nz),rh(nx,ny,nz)
  external :: write_bal_laps

  open(newunit=unit,file='candidate.bin',form='unformatted',access='stream', &
       status='old',action='read',convert='little_endian',iostat=ios)
  if(ios/=0) error stop 'candidate open failed'
  read(unit,iostat=ios) dimensions
  if(ios/=0) error stop 'candidate dimensions read failed'
  if(any(dimensions/=[nx,ny,nz])) error stop 'candidate dimensions mismatch'
  read(unit,iostat=ios) p,u,v,phi,temperature,moisture,omega
  if(ios/=0) error stop 'candidate fields read failed'
  close(unit,iostat=ios)
  if(ios/=0) error stop 'candidate close failed'
  if(any(p/=[100000.,90000.,80000.,70000.])) error stop 'candidate pressure mismatch'

  ! Same declared float32 geopotential-to-height conversion as qbalpe.
  phi=phi/9.80665
  ! RH is ancillary fixture metadata, not a test of make_rh thermodynamics.
  rh=50.
  call write_bal_laps(i4time,phi,u,v,temperature,omega,rh,moisture,nx,ny,nz,p,status)
  if(status/=1) error stop 'actual write_bal_laps failed'
  print *, 'Actual write_bal_laps PASS; i4time=',i4time
end program
