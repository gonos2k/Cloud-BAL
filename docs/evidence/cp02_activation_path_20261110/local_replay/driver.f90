program replay
use extracted_activation
implicit none
real :: sw(1,1), q(1,1), qci(1,1,1), nci(1,1,3), t(1,1), den(1,1), xl(1,1), cpm(1,1)
real :: dt, q_initial, qc_initial, initial_total, dwater, pi, denr
real :: input(10), input_dt, expected(5), actual(5)
character(len=256) :: input_file
integer :: unit, status
integer :: method, n, j
integer :: state_bits(5,3)
logical :: floor_after
! sw, NC, NN, q, qc, T, den, xl, cpm, pi, denr are provided on stdin
! via a file argument; second line has observed post NC, NN, q, qc, T.
! Otherwise the defaults are synthetic, not forecast data.
input=[0.1, 1.e7, 1.e8, 0.01, 0.0001, 280., 1., 2.5e6, 1004., 3.1415926536]
denr=1000.
if (command_argument_count() > 0) then
  call get_command_argument(1,input_file)
  open(newunit=unit,file=trim(input_file),status='old',iostat=status)
  if (status /= 0) error stop 'cannot open frozen input'
  read(unit,*) input, denr, input_dt
  read(unit,*) expected
  close(unit)
  sw=input(1); nci=0.; nci(1,1,1)=input(2); nci(1,1,3)=input(3)
  q=input(4); qci=input(5); t=input(6); den=input(7); xl=input(8); cpm=input(9)
  call step(sw,q,qci,nci,t,den,xl,cpm,input_dt,input(10),denr,.false.)
  actual=[nci(1,1,1), nci(1,1,3), q(1,1), qci(1,1,1), t(1,1)]
  if (any(transfer(actual,[0,0,0,0,0]) /= transfer(expected,[0,0,0,0,0]))) &
    error stop 'captured post-activation state does not match bitwise'
  print *, 'captured activation post-state bitwise match: PASS' 
  print *, 'captured input dt (s): ', input_dt
else
  print *, 'synthetic inputs, not a forecast capture'
end if
pi=input(10)
do method=1,3
  sw=input(1); nci=0.; nci(1,1,1)=input(2); nci(1,1,3)=input(3)
  q=input(4); qci=input(5); t=input(6); den=input(7); xl=input(8); cpm=input(9)
  q_initial=q(1,1); qc_initial=qci(1,1,1); initial_total=q_initial+qc_initial
  if (method == 1) then
    n=1; dt=20.
  else
    n=2; dt=10.
  end if
  do j=1,n
    floor_after=method /= 3 .or. j == n
    call step(sw,q,qci,nci,t,den,xl,cpm,dt,pi,denr,floor_after)
  end do
  dwater=(q(1,1)+qci(1,1,1))-initial_total
  write(*,'(a,i0,a,6(es15.7,1x))') 'method=',method,' NN NC QV QC T water_residual=', &
    nci(1,1,3),nci(1,1,1),q(1,1),qci(1,1,1),t(1,1),dwater
  state_bits(:,method)=transfer([nci(1,1,1),nci(1,1,3),q(1,1),qci(1,1,1),t(1,1)],[0,0,0,0,0])
  write(*,'(a,i0,a,5(z8.8,1x))') 'method=',method,' NC NN QV QC T raw32=', state_bits(:,method)
  if (q(1,1)<0. .or. qci(1,1,1)<0. .or. abs(dwater)>2.e-8) error stop 'water check failed'
  if (abs((t(1,1)-input(6))-(q_initial-q(1,1))*xl(1,1)/cpm(1,1))>4.e-5) error stop 'latent heat check failed'
end do
print *, 'method 1 vs 2 bitwise equal:', all(state_bits(:,1)==state_bits(:,2))
print *, 'method 1 vs 3 bitwise equal:', all(state_bits(:,1)==state_bits(:,3))
end program
