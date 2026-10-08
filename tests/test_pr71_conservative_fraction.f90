program test_pr71_conservative_fraction
  use pr70_helper, only: kdm6_rain_process_fraction, kdm6_rain_process_state_valid
  implicit none
  real, parameter :: pi=3.14159265, pidnr=(pi*1000.0/6.0)*24.0
  real, parameter :: dmr=3.0, qmin=1.e-12, ncmin=10.0, qcut=1.e-9
  real, parameter :: lambda_min=961.0, lambda_max=35000.0
  real, parameter :: pidnc=(pi*1000.0/6.0), pidni=(pi*500.0/6.0)*6.0
  real, parameter :: dmc=3.0, dmi=3.0
  real, parameter :: lambda_c_min=12000.0, lambda_c_max=500000.0
  real, parameter :: lambda_i_min=9080.0, lambda_i_max=1820000.0
  real :: q_fixed(5),q_process(5),n_fixed(3),n_process(3)
  real :: fraction,next_fraction,q_returned(5),n_returned(3)
  real :: q_next(5),n_next(3),t_fixed,t_process
  integer :: search_status
  logical :: feasible,returned_valid,next_valid

  q_fixed=0.0; q_process=0.0; n_fixed=0.0; n_process=0.0
  q_fixed(3)=2.5142206538930623e-8
  q_process(3)=-2.44809541527502e-8
  n_fixed(3)=q_fixed(3)*5000.0**dmr/pidnr
  n_process(3)=q_process(3)*5000.0**dmr/pidnr
  t_fixed=270.0; t_process=0.0

  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,t_fixed,t_process,.false.,1.0,pidnr,qmin,ncmin,qcut,dmr, &
       lambda_min,lambda_max,100.0,900.0,pidnc,dmc,lambda_c_min,lambda_c_max, &
       pidni,dmi,lambda_i_min,lambda_i_max,fraction,feasible,search_status)
  if (.not.feasible .or. search_status.ne.0) &
       error stop 'one-ULP fixture did not return FEASIBLE'

  next_fraction=nearest(fraction,1.0)
  q_returned=q_fixed+fraction*q_process
  n_returned=n_fixed+fraction*n_process
  q_next=q_fixed+next_fraction*q_process
  n_next=n_fixed+next_fraction*n_process
  call check_state(q_returned,n_returned,returned_valid)
  call check_state(q_next,n_next,next_valid)
  if (.not.returned_valid .or. .not.next_valid) &
       error stop 'direct stored-state predicate rejected an adjacent candidate'
  if (fraction.ne.0.9861627817153931 .or. &
      next_fraction.ne.0.9861628413200378) &
       error stop 'helper result or adjacent float32 value changed'
  if (q_returned(3).ne.q_next(3) .or. &
      q_returned(3).ne.1.000000082740371e-9) &
       error stop 'one-ULP candidates no longer store the same rain mass'

  write(*,'(A,ES24.16)') 'fraction=',fraction
  write(*,'(A,ES24.16)') 'next_fraction=',next_fraction
  write(*,'(A,ES24.16)') 'returned_qr=',q_returned(3)
  write(*,'(A,ES24.16)') 'next_qr=',q_next(3)
  write(*,'(A,L1)') 'returned_direct_predicate=',returned_valid
  write(*,'(A,L1)') 'next_direct_predicate=',next_valid
  print '(A)','PR71 conservative fraction one-ULP test passed'

contains
  subroutine check_state(q,n,valid)
    real,intent(in) :: q(5),n(3)
    logical,intent(out) :: valid
    call kdm6_rain_process_state_valid(q,n,0.0,270.0,1.0,pidnr, &
         qmin,ncmin,qcut,dmr,lambda_min,lambda_max,100.0,900.0, &
         pidnc,dmc,lambda_c_min,lambda_c_max,pidni,dmi, &
         lambda_i_min,lambda_i_max,valid)
  end subroutine check_state
end program test_pr71_conservative_fraction
