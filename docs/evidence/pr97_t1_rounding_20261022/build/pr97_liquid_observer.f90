! Diagnostic-only same-call liquid transfer account. No model state is changed.
module pr97_liquid_observer
  use, intrinsic :: iso_fortran_env, only: real32, real64, int64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  private
  public :: liquid_begin, liquid_record, liquid_end, store_error
  real(real64), allocatable :: totals(:,:), compensation(:,:), maxima(:)
  integer(int64), allocatable :: counts(:,:)
contains
  pure subroutine two_sum(a,b,s,e)
    real(real64), intent(in) :: a,b
    real(real64), intent(out) :: s,e
    real(real64) :: back
    s=a+b
    back=s-a
    e=(a-(s-back))+(b-back)
  end subroutine

  pure real(real64) function store_error(before,extent,after) result(error)
    real(real32), intent(in) :: before,extent,after
    real(real64) :: exact_high,exact_low,delta,tail,high,low
    ! The two_sum low part retains transfers below binary64's local spacing.
    call two_sum(real(before,real64),real(extent,real64),exact_high,exact_low)
    call two_sum(real(after,real64),-exact_high,delta,tail)
    call two_sum(delta,-exact_low,high,low)
    error=high+(low+tail)
  end function

  subroutine liquid_begin(its,ite)
    integer, intent(in) :: its,ite
    if (allocated(totals)) deallocate(totals,compensation,maxima,counts)
    allocate(totals(10,its:ite),compensation(10,its:ite),maxima(its:ite),counts(6,its:ite))
    totals=0; compensation=0; maxima=0; counts=0
  end subroutine

  subroutine add(i,n,value)
    integer, intent(in) :: i,n
    real(real64), intent(in) :: value
    real(real64) :: s,e
    call two_sum(totals(n,i),value,s,e)
    totals(n,i)=s
    compensation(n,i)=compensation(n,i)+e
  end subroutine

  subroutine liquid_record(i,kind,qbefore,cbefore,extent,qafter,cafter,den,delz)
    integer, intent(in) :: i,kind ! 1 activation, 2 full evaporation, 3 general branch
    real(real32), intent(in) :: qbefore,cbefore,extent,qafter,cafter,den,delz
    real(real64) :: weight,eq,ec,error
    integer :: direction
    if (extent==0.0_real32) return
    if (.not.all(ieee_is_finite([qbefore,cbefore,extent,qafter,cafter,den,delz]))) &
      error stop 'PR97 nonfinite liquid account operand'
    if (min(qbefore,cbefore,qafter,cafter)<0 .or. den<=0 .or. delz<=0) &
      error stop 'PR97 invalid liquid account operand'
    weight=real(den,real64)*real(delz,real64)
    eq=store_error(qbefore,-extent,qafter)
    ec=store_error(cbefore,extent,cafter)
    if (kind==2) then
      if (extent/=-cbefore .or. cafter/=0) error stop 'PR97 invalid full evaporation extent'
    endif
    error=eq+ec
    direction=kind
    if (kind==3 .and. extent>0) direction=4
    counts(direction,i)=counts(direction,i)+1
    ! A clipped (rather than rounded) target is reported separately, never hidden.
    if (real(qbefore,real64)-real(extent,real64)<0 .or. &
        real(cbefore,real64)+real(extent,real64)<0) counts(5,i)=counts(5,i)+1
    counts(6,i)=counts(6,i)+1
    call add(i,1,eq*weight)
    call add(i,2,ec*weight)
    call add(i,3,abs(error)*weight)
    call add(i,4,real(extent,real64)*weight)
    call add(i,5,abs(real(extent,real64))*weight)
    call add(i,6,real(extent,real64)*weight*merge(1.0_real64,0.0_real64,kind==1))
    call add(i,7,real(extent,real64)*weight*merge(1.0_real64,0.0_real64,kind==2))
    call add(i,8,real(extent,real64)*weight*merge(1.0_real64,0.0_real64,kind==3.and.extent<0))
    call add(i,9,real(extent,real64)*weight*merge(1.0_real64,0.0_real64,kind==3.and.extent>0))
    call add(i,10,abs(eq)*weight+abs(ec)*weight)
    maxima(i)=max(maxima(i),abs(error)*weight)
  end subroutine

  subroutine liquid_end(lat,its,ite)
    integer, intent(in) :: lat,its,ite
    integer :: u,ios,i
    open(newunit=u,file='pr97_liquid_columns.raw',status='unknown',position='append', &
         action='write',iostat=ios)
    if (ios/=0) error stop 'PR97 column account open failed'
    do i=its,ite
      write(u,'(a,2i8,6(1x,i12),11(1x,es26.17e3))',iostat=ios) &
        'LIQCOL',i,lat,counts(:,i),totals(:,i)+compensation(:,i),maxima(i)
      if (ios/=0) error stop 'PR97 column account write failed'
    enddo
    close(u,iostat=ios)
    if (ios/=0) error stop 'PR97 column account close failed'
  end subroutine
end module
