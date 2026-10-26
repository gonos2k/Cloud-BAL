program pr103_gdtost_oracle
  implicit none
  integer, parameter :: nx = 8, ny = 8
  real :: field(nx, ny), value
  integer :: i, j

  do j = 1, ny
    do i = 1, nx
      field(i, j) = 7.0 + 3.0 * real(i) + 2.0 * real(j)
    end do
  end do

  call gdtost(field, nx, ny, 3.5, 3.25, value, 0)
  print '(A,ES24.16)', 'fractional=', value
  call gdtost(field, nx, ny, 3.0, 3.0, value, 0)
  print '(A,ES24.16)', 'integral=', value
end program
