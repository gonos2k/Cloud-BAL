program p
 use iso_fortran_env,only:real32,real64
 use, intrinsic::ieee_arithmetic
 use cloud_bal_joint_transport
 implicit none
 real(real32)::q,n,r
 integer::a
 logical::v
 r=ieee_value(0.0_real32,ieee_quiet_nan)
 call joint_moment_store(400.0_real64,1.0_real64,r,100.0_real64,900.0_real64, &
 .true.,q,n,a,v,strict_mass_ratio=.true.)
 if(v) error stop 'accepted'
 print *,'PASS invalid density rejected'
end program
