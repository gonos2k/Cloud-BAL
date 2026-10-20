program strict_mean_hex
  use iso_fortran_env, only: real32, real64, int64
  use, intrinsic :: ieee_arithmetic, only: ieee_next_after
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  real(real64), parameter :: q=7.58284774643526457e-9_real64
  real(real64), parameter :: n=1.81027141293785325e6_real64
  real(real64), parameter :: mmin=4.18879052734374980e-15_real64
  real(real64), parameter :: mmax=3.03008574026602271e-10_real64
  real(real32), parameter :: rho=1.08871281147003174_real32
  real(real32) :: stored_q,stored_n
  real(real64) :: ratio,product
  integer(int64) :: qbits,nbits,mbits,rbits,pbits
  integer :: adjustment,stage
  logical :: valid
  ratio=q/n
  product=mmin*n
  qbits=transfer(q,qbits); nbits=transfer(n,nbits); mbits=transfer(mmin,mbits)
  rbits=transfer(ratio,rbits); pbits=transfer(product,pbits)
  write(*,'(a,1x,z16.16)') 'Q64',qbits
  write(*,'(a,1x,z16.16)') 'N64',nbits
  write(*,'(a,1x,z16.16)') 'MMIN64',mbits
  write(*,'(a,1x,z16.16)') 'RATIO64',rbits
  write(*,'(a,1x,z16.16)') 'PRODUCT64',pbits
  write(*,'(a,1x,es26.17)') 'Q_MINUS_PRODUCT',q-product
  write(*,'(a,1x,l1)') 'RATIO_GE_MMIN',ratio>=mmin
  write(*,'(a,1x,z16.16)') 'RATIO_NEXTUP',transfer(ieee_next_after(ratio,huge(ratio)),rbits)
  call joint_moment_store(q,n,rho,mmin,mmax,.true.,stored_q,stored_n,adjustment,valid, &
       allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,failure_stage=stage)
  write(*,'(a,1x,l1,1x,i0,1x,i0)') 'STRICT_STORE_NO_VOLUME',valid,stage,adjustment
contains
  subroutine wrf_error_fatal(message)
    character(len=*), intent(in) :: message
    error stop message
  end subroutine wrf_error_fatal
end program strict_mean_hex
