module pr85_kdm6_density_bridge_fixture
  use, intrinsic :: ieee_arithmetic, only : ieee_value, ieee_quiet_nan, ieee_positive_inf, &
                                           ieee_negative_inf, ieee_is_finite
  implicit none
contains
  pure elemental subroutine dry_to_gas_density(dry_density, vapor_mixing_ratio, &
                                                gas_density, valid)
    real, intent(in) :: dry_density, vapor_mixing_ratio
    real, intent(out) :: gas_density
    logical, intent(out) :: valid
    double precision :: gas_density64

    gas_density = 0.0
    valid = .false.
    if (.not. ieee_is_finite(dry_density) .or. .not. ieee_is_finite(vapor_mixing_ratio)) return
    if (dry_density <= 0.0 .or. vapor_mixing_ratio < 0.0) return
    gas_density64 = real(dry_density,kind=kind(gas_density64)) * &
                    (1.0d0 + real(vapor_mixing_ratio,kind=kind(gas_density64)))
    if (.not. ieee_is_finite(gas_density64)) return
    if (gas_density64 <= 0.0d0 .or. &
        gas_density64 > real(huge(gas_density),kind=kind(gas_density64))) return
    gas_density = real(gas_density64)
    valid = ieee_is_finite(gas_density) .and. gas_density > 0.0
  end subroutine dry_to_gas_density
end module pr85_kdm6_density_bridge_fixture

program test_pr85_kdm6_density_bridge
  use, intrinsic :: ieee_arithmetic, only : ieee_value, ieee_quiet_nan, ieee_positive_inf, &
                                           ieee_negative_inf
  use pr85_kdm6_density_bridge_fixture, only : dry_to_gas_density
  implicit none
  real :: rho_dry, qv, rho_gas
  logical :: valid

  rho_dry = 0.7
  qv = 0.01
  call dry_to_gas_density(rho_dry, qv, rho_gas, valid)
  if (.not. valid) error stop 'valid dry density rejected'
  if (transfer(rho_dry,0) /= transfer(0.7,0)) error stop 'dry carrier changed'
  if (abs(rho_gas - 0.707) > 2.0e-7) error stop 'gas density reconstruction incorrect'

  call expect_invalid(0.0, 0.01, 'zero dry density')
  call expect_invalid(-0.7, 0.01, 'negative dry density')
  call expect_invalid(ieee_value(0.7,ieee_quiet_nan), 0.01, 'NaN dry density')
  call expect_invalid(ieee_value(0.7,ieee_positive_inf), 0.01, 'infinite dry density')
  call expect_invalid(0.7, -0.01, 'negative vapor')
  call expect_invalid(0.7, ieee_value(0.01,ieee_quiet_nan), 'NaN vapor')
  call expect_invalid(0.7, ieee_value(0.01,ieee_positive_inf), 'infinite vapor')
  call expect_invalid(0.7, ieee_value(0.01,ieee_negative_inf), 'negative infinite vapor')
  call expect_invalid(huge(0.7), huge(0.7), 'gas density overflow')

  print '(a)', 'CASE dry carrier preserved and gas density reconstructed in R64'
  print '(a)', 'CASE invalid density inputs and R32 overflow rejected'
contains
  subroutine expect_invalid(dry, vapor, label)
    real, intent(in) :: dry, vapor
    character(len=*), intent(in) :: label
    real :: reconstructed
    logical :: accepted
    call dry_to_gas_density(dry, vapor, reconstructed, accepted)
    if (accepted) then
      print '(a)', trim(label)
      error stop 'invalid density accepted'
    endif
  end subroutine expect_invalid
end program test_pr85_kdm6_density_bridge
