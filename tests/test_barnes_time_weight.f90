program test_barnes_time_weight
  use omp_lib, only: omp_get_num_threads
  implicit none
  integer, parameter :: count=4096
  integer :: index, offset, threads
  integer :: status(count)
  real :: weight(count), expected

  threads=0
  !$omp parallel
  !$omp single
  threads=omp_get_num_threads()
  !$omp end single
  !$omp end parallel
  if (threads /= 38) stop 1

  !$omp parallel do private(offset)
  do index=1,count
    select case(mod(index,4))
    case(0)
      offset=0
    case(1)
      offset=36001
    case(2)
      offset=-36001
    case default
      offset=36000
    end select
    call get_time_wt(100000,100000-offset,weight(index),status(index))
  end do
  !$omp end parallel do

  expected=exp(-100.0)
  do index=1,count
    select case(mod(index,4))
    case(0)
      if (status(index) /= 1 .or. weight(index) /= 1.0) stop 2
    case(1,2)
      if (status(index) /= 0 .or. weight(index) /= 1.0) stop 3
    case default
      if (status(index) /= 1 .or. abs(weight(index)-expected) > tiny(1.0)) stop 4
    end select
  end do
  print *, 'BARNES_TIME_WEIGHT_PARALLEL_PASS',count,threads
end program
