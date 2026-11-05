program rounding_check
  use, intrinsic :: iso_fortran_env, only: int32, real32
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none

  integer :: unit, ios, row
  integer(int32) :: a_bits, b_bits, c_bits, d_bits
  integer(int32) :: old_bits, grouped_bits
  real(real32) :: a, b, c, d
  real(real32) :: old_step_1, old_step_2, old_value
  real(real32) :: grouped_left, grouped_right, grouped_value

  open(newunit=unit, file='phi_terms.hex', status='old', action='read', iostat=ios)
  if (ios /= 0) error stop 'cannot open phi_terms.hex'

  row = 0
  do
    read(unit, '(Z8,1X,Z8,1X,Z8,1X,Z8)', iostat=ios) a_bits, b_bits, c_bits, d_bits
    if (ios < 0) exit
    if (ios /= 0) error stop 'malformed hexadecimal REAL32 terms'

    row = row + 1
    a = transfer(a_bits, a)
    b = transfer(b_bits, b)
    c = transfer(c_bits, c)
    d = transfer(d_bits, d)
    if (.not. (ieee_is_finite(a) .and. ieee_is_finite(b) .and. &
               ieee_is_finite(c) .and. ieee_is_finite(d))) error stop 'non-finite input'

    ! Preserve each binary32 rounding point in the legacy left-to-right numerator.
    old_step_1 = a - b
    old_step_2 = old_step_1 + c
    old_value = old_step_2 - d

    ! The proposed numerator groups each vertical difference first.
    grouped_left = a - b
    grouped_right = c - d
    grouped_value = grouped_left + grouped_right

    old_bits = transfer(old_value, old_bits)
    grouped_bits = transfer(grouped_value, grouped_bits)
    write(*, '(I0,1X,Z8.8,1X,Z8.8)') row, old_bits, grouped_bits
  end do
  close(unit)
  if (row /= 60) error stop 'expected exactly 60 paired-arm rows'
end program rounding_check
