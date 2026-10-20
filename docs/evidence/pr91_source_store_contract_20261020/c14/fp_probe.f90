program probe
  use iso_fortran_env, only: int32,int64,real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_get_underflow_mode
  implicit none
  real(real32) :: nearest_q, transfer_q
  real(real64) :: quantum64, converted_nearest, converted_transfer
  integer(int64) :: nearest64_bits, transfer64_bits
  logical :: gradual_mode
  call ieee_get_underflow_mode(gradual_mode)
  nearest_q=nearest(0.0_real32,1.0_real32)
  transfer_q=transfer(1_int32,0.0_real32)
  quantum64=scale(1.0_real64,-149)
  converted_nearest=real(nearest_q,real64)
  converted_transfer=real(transfer_q,real64)
  nearest64_bits=transfer(converted_nearest,0_int64)
  transfer64_bits=transfer(converted_transfer,0_int64)
  write(*,'(a,1x,l1)') 'IEEE_UNDERFLOW_MODE',gradual_mode
  write(*,'(a,1x,z8.8)') 'NEAREST_R32_BITS',transfer(nearest_q,0_int32)
  write(*,'(a,1x,z16.16)') 'CAST_NEAREST_R64_BITS',nearest64_bits
  write(*,'(a,1x,z8.8)') 'TRANSFER_R32_BITS',transfer(transfer_q,0_int32)
  write(*,'(a,1x,z16.16)') 'CAST_TRANSFER_R64_BITS',transfer64_bits
  write(*,'(a,1x,z16.16)') 'SCALE_R64_QUANTUM_BITS',transfer(quantum64,0_int64)
end program probe
