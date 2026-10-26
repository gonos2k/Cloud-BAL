program pr103_gdtost_oracle
  implicit none
  integer, parameter :: nx = 8, ny = 8
  real :: field(nx, ny), value
  integer :: i, j
  real, parameter :: missingflag = 1.0e37

  do j = 1, ny
    do i = 1, nx
      field(i, j) = 7.0 + 3.0 * real(i) + 2.0 * real(j)
    end do
  end do

  call gdtost(field, nx, ny, 3.5, 3.25, value, 0)
  print '(A,ES24.16)', 'fractional=', value
  call gdtost(field, nx, ny, 3.0, 3.0, value, 0)
  print '(A,ES24.16)', 'integral=', value

  do j = 1, ny
    do i = 1, nx
      field(i, j) = real(i * i + 2 * j * j + 3 * i * j - 4 * i + 5 * j + 7)
    end do
  end do
  call gdtost(field, nx, ny, 4.5, 3.25, value, 0)
  print '(A,ES24.16)', 'quadratic_mixed=', value

  field(2, :) = missingflag
  call gdtost(field, nx, ny, 3.5, 3.25, value, 0)
  print '(A,ES24.16)', 'missing_outer_stencil=', value

  field = 2.0
  field(4, 4) = missingflag
  call gdtost(field, nx, ny, 4.5, 4.5, value, 0)
  print '(A,ES24.16)', 'missing_inner_stencil=', value

  field = 1.0
  call gdtost(field, nx, ny, 1.5, 4.5, value, 0)
  print '(A,ES24.16)', 'near_edge_source_kernel=', value
end program
