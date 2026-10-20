program c10_cancellation_probe
  use iso_fortran_env, only: real32, real64, int32, int64
  implicit none
  real(real32) :: t_before32, t_after32, coupled_before32, prepared_endpoint32
  real(real64) :: old_diffusion64, prepared_diffusion64
  real(real64) :: later_residual64, delta_precision64, source_diff_delta64
  real(real64) :: qs64, old_carrier64, dt64, donor64

  ! Manufactured cancellation case only; these are not native failure operands.
  t_before32 = 1.0_real32
  t_after32 = 0.0_real32
  coupled_before32 = t_before32
  prepared_endpoint32 = t_after32
  old_diffusion64 = scale(1.0_real64, -54)
  prepared_diffusion64 = 0.0_real64
  old_carrier64 = 1.0_real64
  dt64 = 1.0_real64

  ! These expressions follow the producer residual, precision correction,
  ! prepared-minus-old diffusion delta, and donor construction in C10.
  later_residual64 = real(t_after32,real64) - real(coupled_before32,real64)
  delta_precision64 = (real(t_before32,real64) + old_diffusion64) - real(t_after32,real64)
  source_diff_delta64 = prepared_diffusion64 - old_diffusion64
  qs64 = later_residual64 + delta_precision64
  qs64 = qs64 + source_diff_delta64
  donor64 = (old_carrier64 * real(prepared_endpoint32,real64) + dt64 * qs64) / old_carrier64

  write(*,'(a,1x,z16.16,1x,es24.16)') 'later_residual64', transfer(later_residual64,0_int64), later_residual64
  write(*,'(a,1x,z16.16,1x,es24.16)') 'delta_precision64', transfer(delta_precision64,0_int64), delta_precision64
  write(*,'(a,1x,z16.16,1x,es24.16)') 'source_diff_delta64', transfer(source_diff_delta64,0_int64), source_diff_delta64
  write(*,'(a,1x,z8.8,1x,es24.16)') 'prepared_endpoint32', transfer(prepared_endpoint32,0_int32), prepared_endpoint32
  write(*,'(a,1x,z16.16,1x,es24.16)') 'qs64_actual', transfer(qs64,0_int64), qs64
  write(*,'(a,1x,z16.16,1x,es24.16)') 'donor64_actual', transfer(donor64,0_int64), donor64
  if (qs64 /= -scale(1.0_real64,-54)) stop 1
  if (donor64 /= -scale(1.0_real64,-54)) stop 2
  print *, 'C10_MANUFACTURED_CANCELLATION_PASS'
end program c10_cancellation_probe
