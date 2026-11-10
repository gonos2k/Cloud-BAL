program probe
  implicit none
   real, parameter :: dtcldcr = 120.
  real :: delt,dtcld,total
  integer :: loops,loop,count
  delt=20.
   loops = max(nint(delt/dtcldcr),1)
   dtcld = delt/loops
   if(delt.le.dtcldcr) dtcld = delt

  count=0
  total=0.
   do loop = 1,loops
    count=count+1
    total=total+dtcld
  enddo
  print *, loops, count, dtcld, total
end program
