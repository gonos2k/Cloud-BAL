program c10_zero_endpoint_kernel_probe
  use iso_fortran_env, only: real32, real64, int32, int64
  use pr87_horizontal_diffusion64, only: horizontal_diffusion64
  implicit none
  real(real32) :: q(3,1,3), n(3,1,3), prepared_q(3,1,3), prepared_n(3,1,3)
  real(real32) :: xkmhd(3,1,3), mut(3,3), c1(1), c2(1)
  real(real32) :: one2d(3,3), inv2d(3,3), rdx, rdy
  real(real32) :: before32, after32, coupled32, raw_q32, raw_n32, endpoint_q32, endpoint_n32
  real(real64) :: dq(3,1,3), dn(3,1,3), dpq(3,1,3), dpn(3,1,3)
  real(real64) :: old_dq, old_dn, prepared_dq, prepared_dn
  real(real64) :: later64, precision64, source_delta_q, source_delta_n, qs, ns
  real(real64) :: donor_q, donor_n

  ! Reproduce the source-extracted embedded R128 horizontal_diffusion64
  ! routine on a manufactured 3x3 stencil.  No native failure operands used.
  q=2.0_real32; q(2,1,2)=1.0_real32
  n=16.0_real32; n(2,1,2)=8.0_real32
  prepared_q=0.0_real32; prepared_n=0.0_real32
  xkmhd=scale(1.0_real32,-57)
  mut=1.0_real32; c1=1.0_real32; c2=0.0_real32
  one2d=1.0_real32; inv2d=1.0_real32; rdx=1.0_real32; rdy=1.0_real32

  call horizontal_diffusion64(q,mut,c1,c2,one2d,one2d,inv2d,one2d,one2d,one2d, &
       xkmhd,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,dq)
  call horizontal_diffusion64(n,mut,c1,c2,one2d,one2d,inv2d,one2d,one2d,one2d, &
       xkmhd,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,dn)
  call horizontal_diffusion64(prepared_q,mut,c1,c2,one2d,one2d,inv2d,one2d,one2d,one2d, &
       xkmhd,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,dpq)
  call horizontal_diffusion64(prepared_n,mut,c1,c2,one2d,one2d,inv2d,one2d,one2d,one2d, &
       xkmhd,rdx,rdy,1,3,1,1,1,3,2,2,2,2,1,1,dpn)

  old_dq=dq(2,1,2); old_dn=dn(2,1,2)
  prepared_dq=dpq(2,1,2); prepared_dn=dpn(2,1,2)
  before32=-1.0_real32; coupled32=before32
  after32=real(real(before32,real64)+old_dq,real32)
  raw_q32=-1.0_real32; raw_n32=-8.0_real32
  endpoint_q32=real(real(1.0_real32,real64)+real(raw_q32,real64),real32)
  endpoint_n32=real(real(8.0_real32,real64)+real(raw_n32,real64),real32)

  later64=real(after32,real64)-real(coupled32,real64)
  precision64=(real(before32,real64)+old_dq)-real(after32,real64)
  source_delta_q=prepared_dq-old_dq
  source_delta_n=prepared_dn-old_dn
  qs=(later64+precision64)+source_delta_q
  ns=(later64+8.0_real64*precision64)+source_delta_n
  donor_q=(real(endpoint_q32,real64)+qs)
  donor_n=(real(endpoint_n32,real64)+ns)

  write(*,'(a,1x,z16.16,1x,es24.16)') 'old_diffusion_q',transfer(old_dq,0_int64),old_dq
  write(*,'(a,1x,z16.16,1x,es24.16)') 'old_diffusion_n',transfer(old_dn,0_int64),old_dn
  write(*,'(a,1x,z16.16,1x,es24.16)') 'prepared_diffusion_q',transfer(prepared_dq,0_int64),prepared_dq
  write(*,'(a,1x,z16.16,1x,es24.16)') 'prepared_diffusion_n',transfer(prepared_dn,0_int64),prepared_dn
  write(*,'(a,1x,z8.8,1x,es24.16)') 'after32',transfer(after32,0_int32),after32
  write(*,'(a,1x,z8.8,1x,es24.16)') 'prepared_endpoint_q32',transfer(endpoint_q32,0_int32),endpoint_q32
  write(*,'(a,1x,z8.8,1x,es24.16)') 'prepared_endpoint_n32',transfer(endpoint_n32,0_int32),endpoint_n32
  write(*,'(a,1x,z16.16,1x,es24.16)') 'later64',transfer(later64,0_int64),later64
  write(*,'(a,1x,z16.16,1x,es24.16)') 'precision64',transfer(precision64,0_int64),precision64
  write(*,'(a,1x,z16.16,1x,es24.16)') 'source_delta_q',transfer(source_delta_q,0_int64),source_delta_q
  write(*,'(a,1x,z16.16,1x,es24.16)') 'source_delta_n',transfer(source_delta_n,0_int64),source_delta_n
  write(*,'(a,1x,z16.16,1x,es24.16)') 'qs',transfer(qs,0_int64),qs
  write(*,'(a,1x,z16.16,1x,es24.16)') 'ns',transfer(ns,0_int64),ns
  write(*,'(a,1x,z16.16,1x,es24.16)') 'donor_q',transfer(donor_q,0_int64),donor_q
  write(*,'(a,1x,z16.16,1x,es24.16)') 'donor_n',transfer(donor_n,0_int64),donor_n
  if (old_dq /= scale(1.0_real64,-55)) stop 1
  if (old_dn /= scale(1.0_real64,-52)) stop 2
  if (prepared_dq /= 0.0_real64 .or. prepared_dn /= 0.0_real64) stop 3
  if (after32 /= before32) stop 4
  if (endpoint_q32 /= 0.0_real32 .or. endpoint_n32 /= 0.0_real32) stop 5
  if (qs /= -scale(1.0_real64,-55) .or. ns /= -scale(1.0_real64,-52)) stop 6
  if (donor_q >= 0.0_real64 .or. donor_n >= 0.0_real64) stop 7
  print *, 'C10_ZERO_ENDPOINT_EMBEDDED_R128_PASS'
end program c10_zero_endpoint_kernel_probe
