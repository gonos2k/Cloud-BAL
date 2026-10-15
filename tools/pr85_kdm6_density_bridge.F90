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
