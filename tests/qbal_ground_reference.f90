! Conditional ground reference; no retained HT or production state is changed.
module qbal_ground_reference
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_finite, ieee_value, ieee_quiet_nan
  use qbal_thickness_attribution, only: thickness_change
  implicit none
  private
  real(real64), parameter :: RD=287.05_real64, G0=9.80665_real64
  public :: build_ground_reference
contains
  ! The common constant-Tv surface strip ends at the first regular level.
  ! It is consumed only within the declared p10..PS pressure bracket.
  ! Regular layers reuse the PR41 endpoint-Tv operator; the junction may
  ! have a Tv jump. This piecewise prior is not an observed full profile.
  ! ok distinguishes malformed inputs from valid but unsupported columns.
  subroutine build_ground_reference(p,ps,p10,tv_surface,terrain,ta,qa,tf,qf, &
                                     valid,before,after,delta,bound,first,eligible,ok)
    real(real64), intent(in) :: p(:),ps,p10,tv_surface,terrain
    real(real64), intent(in) :: ta(:),qa(:),tf(:),qf(:)
    logical, intent(in) :: valid(:)
    real(real64), intent(out) :: before(:),after(:),delta(:,:),bound(:)
    integer, intent(out) :: first
    logical, intent(out) :: eligible,ok
    real(real64) :: trial_before(size(p)),trial_after(size(p))
    real(real64) :: trial_delta(3,size(p)),trial_bound(size(p))
    real(real64) :: nan,ground,partial,za,zf,dt,dq,dz,layer_bound,pair(2,4)
    integer :: n,k,start
    logical :: layer_ok

    nan=ieee_value(0._real64,ieee_quiet_nan)
    before=nan;after=nan;delta=nan;bound=nan
    first=0;eligible=.false.;ok=.false.
    n=size(p)
    if (n<2) return
    if (size(ta)/=n.or.size(qa)/=n.or.size(tf)/=n.or.size(qf)/=n) return
    if (size(valid)/=n.or.size(before)/=n.or.size(after)/=n.or.size(bound)/=n) return
    if (size(delta,1)/=3.or.size(delta,2)/=n) return
    if (.not.all(ieee_is_finite(p))) return
    if (any(p<100._real64).or.any(p>120000._real64)) return
    if (any(p(:n-1)<=p(2:))) return
    if (.not.all(ieee_is_finite([ps,p10,tv_surface,terrain]))) return
    if (ps<100._real64.or.ps>120000._real64.or.p10<=0._real64.or.p10>ps) return
    if (tv_surface<100._real64.or.tv_surface>1000._real64.or.abs(terrain)>1.e6_real64) return
    do k=1,n
      if (.not.valid(k)) cycle
      if (p(k)>ps) return
      if (.not.all(ieee_is_finite([ta(k),qa(k),tf(k),qf(k)]))) return
      if (min(ta(k),tf(k))<100._real64.or.max(ta(k),tf(k))>500._real64) return
      if (min(qa(k),qf(k))<0._real64.or.max(qa(k),qf(k))>=1._real64) return
    end do

    start=0
    do k=1,n
      if (p(k)>ps) cycle
      start=k
      exit
    end do
    ! Missing support does not authorize bridging or extending the prior.
    ok=.true.
    if (start==0) return
    if (p(start)<p10) return
    if (.not.all(valid(start:n))) return
    ok=.false.
    trial_before=nan;trial_after=nan;trial_delta=nan;trial_bound=nan
    ground=G0*terrain
    partial=RD*tv_surface*log(ps/p(start))
    trial_before(start)=ground+partial
    trial_after(start)=trial_before(start)
    trial_delta(:,start)=0._real64
    ! PS/p can round before LOG when the partial layer is very thin.
    ! Retain Rd*Tv, not only the already-small logarithmic product.
    trial_bound(start)=128._real64*epsilon(1._real64)* &
      (abs(ground)+RD*tv_surface+abs(partial))
    do k=start,n-1
      pair(:,1)=ta(k:k+1);pair(:,2)=qa(k:k+1)
      pair(:,3)=tf(k:k+1);pair(:,4)=qf(k:k+1)
      call thickness_change(p(k),p(k+1),pair(:,1),pair(:,2),pair(:,3),pair(:,4), &
                            za,zf,dt,dq,dz,layer_bound,layer_ok)
      if (.not.layer_ok) return
      trial_before(k+1)=trial_before(k)+G0*za
      trial_after(k+1)=trial_after(k)+G0*zf
      trial_delta(:,k+1)=trial_delta(:,k)+G0*[dt,dq,dz]
      trial_bound(k+1)=trial_bound(k)+G0*layer_bound+ &
        64._real64*epsilon(1._real64)*(abs(trial_before(k+1))+abs(trial_after(k+1)))
    end do
    if (.not.all(ieee_is_finite(trial_before(start:n))).or. &
        .not.all(ieee_is_finite(trial_after(start:n))).or. &
        .not.all(ieee_is_finite(trial_delta(:,start:n))).or. &
        .not.all(ieee_is_finite(trial_bound(start:n)))) return
    do k=start,n
      if (abs(trial_after(k)-trial_before(k)-trial_delta(3,k))>trial_bound(k)) return
      if (abs(sum(trial_delta(1:2,k))-trial_delta(3,k))>trial_bound(k)) return
    end do
    before=trial_before;after=trial_after;delta=trial_delta;bound=trial_bound
    first=start;eligible=.true.;ok=.true.
  end subroutine build_ground_reference
end module qbal_ground_reference
