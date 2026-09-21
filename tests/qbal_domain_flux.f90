! Research-only global flux aggregation.  Internal shared faces cancel exactly.
module qbal_domain_flux
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_finite, ieee_quiet_nan, ieee_value
  implicit none
  private
  public :: domain_flux_budget

contains

  ! Aggregate a triangular mesh into its external budget.
  !
  ! incidence(slot,cell) stores a signed edge id.  The edge fluxes use the
  ! corresponding positive orientation, so a valid internal edge occurs twice
  ! with opposite signs.  covered is the known part of every edge flux and
  ! missing is an optional unresolved correction for the uncovered interval.
  ! Unknown missing values on internal edges are omitted because that shared
  ! value cancels from the domain sum.  Unknown missing values on boundary
  ! edges remain external unknowns and make residual NaN.
  !
  ! The column equation is
  !   surface + sum(sign * (covered + missing)) - top.
  ! subtotal contains only terms supported by the supplied data.  residual is
  ! equal to subtotal only when every external term is known.  The optional
  ! counters are useful for diagnostics and do not alter the result.
  subroutine domain_flux_budget(incidence,surface,covered,missing,missing_known,top,top_known, &
                                subtotal,residual,complete,boundary_unknown_count,orientation_ok,ok, &
                                internal_unknown_count,top_unknown_count)
    integer, intent(in) :: incidence(:,:)
    real(real64), intent(in) :: surface(:),covered(:),missing(:),top(:)
    logical, intent(in) :: missing_known(:),top_known(:)
    real(real64), intent(out) :: subtotal,residual
    logical, intent(out) :: complete,orientation_ok,ok
    integer, intent(out) :: boundary_unknown_count
    integer, intent(out), optional :: internal_unknown_count,top_unknown_count
    integer, allocatable :: occurrence_count(:),owner(:,:),edge_sign(:,:)
    integer :: nc,ne,cell,slot,edge,sign_value,k
    integer :: internal_unknown,boundary_unknown,unknown_top
    real(real64) :: nan_value,sum_value,correction

    nan_value=ieee_value(0._real64,ieee_quiet_nan)
    subtotal=nan_value
    residual=nan_value
    complete=.false.
    orientation_ok=.false.
    ok=.false.
    boundary_unknown_count=0
    boundary_unknown=0
    internal_unknown=0
    unknown_top=0
    if (present(internal_unknown_count)) internal_unknown_count=0
    if (present(top_unknown_count)) top_unknown_count=0

    nc=size(surface)
    ne=size(covered)
    if (nc<1 .or. ne<1) return
    if (size(incidence,1)/=3 .or. size(incidence,2)/=nc) return
    if (size(missing)/=ne .or. size(missing_known)/=ne) return
    if (size(top)/=nc .or. size(top_known)/=nc) return
    if (.not.all(ieee_is_finite(surface))) return
    if (.not.all(ieee_is_finite(covered))) return
    if (any(missing_known.and..not.ieee_is_finite(missing))) return
    if (any(top_known.and..not.ieee_is_finite(top))) return
    if (any(abs(surface)>1.e100_real64)) return
    if (any(abs(covered)>1.e100_real64)) return
    do edge=1,ne
      if (missing_known(edge)) then
        if (abs(missing(edge))>1.e100_real64) return
      end if
    end do
    do cell=1,nc
      if (top_known(cell)) then
        if (abs(top(cell))>1.e100_real64) return
      end if
    end do

    allocate(occurrence_count(ne),owner(2,ne),edge_sign(2,ne))
    occurrence_count=0
    owner=0
    edge_sign=0

    ! Gather edge incidence and reject malformed local connectivity early.
    do cell=1,nc
      do slot=1,3
        if (incidence(slot,cell)==0) return
        if (incidence(slot,cell)>ne .or. incidence(slot,cell)<-ne) return
        edge=abs(incidence(slot,cell))
        if (occurrence_count(edge)>=2) return
        do k=1,occurrence_count(edge)
          if (owner(k,edge)==cell) return
        end do
        occurrence_count(edge)=occurrence_count(edge)+1
        k=occurrence_count(edge)
        owner(k,edge)=cell
        sign_value=merge(1,-1,incidence(slot,cell)>0)
        edge_sign(k,edge)=sign_value
      end do
    end do

    ! Every edge is either one external face or one shared internal face.
    do edge=1,ne
      select case (occurrence_count(edge))
      case (1)
        if (.not.missing_known(edge)) boundary_unknown=boundary_unknown+1
      case (2)
        if (owner(1,edge)==owner(2,edge)) return
        if (edge_sign(1,edge)+edge_sign(2,edge)/=0) return
        if (.not.missing_known(edge)) internal_unknown=internal_unknown+1
      case default
        return
      end select
    end do
    orientation_ok=.true.
    boundary_unknown_count=boundary_unknown
    if (present(internal_unknown_count)) internal_unknown_count=internal_unknown
    unknown_top=count(.not.top_known)
    if (present(top_unknown_count)) top_unknown_count=unknown_top

    ! Sum only external terms.  Skipping shared edges makes cancellation exact
    ! and avoids manufacturing a residual from roundoff in paired incidences.
    ! Kahan accumulation keeps the reported global subtotal stable when the
    ! caller supplies a large real mesh and leaves the arithmetic scale clear.
    sum_value=0._real64
    correction=0._real64
    do cell=1,nc
      call add_term(surface(cell))
    end do
    do cell=1,nc
      if (top_known(cell)) call add_term(-top(cell))
    end do
    do edge=1,ne
      if (occurrence_count(edge)/=1) cycle
      call add_term(real(edge_sign(1,edge),real64)*covered(edge))
      if (missing_known(edge)) call add_term(real(edge_sign(1,edge),real64)*missing(edge))
    end do
    subtotal=sum_value

    complete=(boundary_unknown==0 .and. unknown_top==0)
    if (complete) residual=subtotal
    ok=.true.
  contains
    subroutine add_term(value)
      real(real64), intent(in) :: value
      real(real64) :: compensated,updated
      compensated=value-correction
      updated=sum_value+compensated
      correction=(updated-sum_value)-compensated
      sum_value=updated
    end subroutine add_term
  end subroutine domain_flux_budget

end module qbal_domain_flux
