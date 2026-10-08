program replay_exact_ni_conversion
  use pr73_exact_conversion_helpers
  implicit none
  real :: den, vapor, n_public, rho_d, n_volume
  logical :: valid
  den = 7.716183662E-01
  vapor = 4.646302201E-03
  n_public = 1.356338644E-38
  call moist_to_dry_density(den, vapor, rho_d, valid)
  if (.not. valid) error stop 'dry density invalid'
  call specific_number_to_volume(n_public, rho_d, n_volume, valid)
  write(*,'(A,ES24.16E3)') 'DEN=',den
  write(*,'(A,ES24.16E3)') 'Q=',vapor
  write(*,'(A,ES24.16E3)') 'N_PUBLIC=',n_public
  write(*,'(A,ES24.16E3)') 'RHO_D=',rho_d
  write(*,'(A,ES24.16E3)') 'N_INTERNAL=',n_volume
  write(*,'(A,L1)') 'VALID=',valid
end program replay_exact_ni_conversion
