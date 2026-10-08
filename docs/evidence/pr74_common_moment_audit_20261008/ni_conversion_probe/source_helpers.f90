module pr73_exact_conversion_helpers
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
contains
    pure elemental subroutine moist_to_dry_density(total_density, vapor_mixing_ratio, dry_density, valid)
      real, intent(in) :: total_density, vapor_mixing_ratio
      real, intent(out) :: dry_density
      logical, intent(out) :: valid
      dry_density = 0.0
      valid = .false.
      if (.not. ieee_is_finite(total_density) .or. .not. ieee_is_finite(vapor_mixing_ratio)) return
      if (total_density <= 0.0 .or. vapor_mixing_ratio < 0.0) return
      dry_density = total_density / (1.0 + vapor_mixing_ratio)
      valid = ieee_is_finite(dry_density) .and. dry_density > 0.0
    end subroutine moist_to_dry_density

    pure elemental subroutine specific_number_to_volume(number_per_kg, dry_density, number_per_m3, valid)
      real, intent(in) :: number_per_kg, dry_density
      real, intent(out) :: number_per_m3
      logical, intent(out) :: valid
      number_per_m3 = 0.0
      valid = .false.
      if (.not. ieee_is_finite(number_per_kg) .or. .not. ieee_is_finite(dry_density)) return
      if (number_per_kg < 0.0 .or. dry_density <= 0.0) return
      if (dry_density > 1.0) then
        if (number_per_kg > huge(number_per_kg) / dry_density) return
      end if
      number_per_m3 = number_per_kg * dry_density
      valid = ieee_is_finite(number_per_m3)
      if (number_per_kg > 0.0 .and. number_per_m3 == 0.0) valid = .false.
    end subroutine specific_number_to_volume
end module pr73_exact_conversion_helpers
