program test_qbal_balcon
  use, intrinsic :: iso_fortran_env, only: int32
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, parameter :: nx=6, ny=6, nz=4, ncell=nx*ny*nz
  real :: to(nx,ny,nz),uo(nx,ny,nz),vo(nx,ny,nz),omo(nx,ny,nz)
  real :: t(nx,ny,nz),u(nx,ny,nz),v(nx,ny,nz),om(nx,ny,nz)
  real :: tb(nx,ny,nz),ub(nx,ny,nz),vb(nx,ny,nz),omb(nx,ny,nz)
  real :: tmp(nx,ny,nz),shs(nx,ny,nz),saved(nx,ny,nz,8),background(nx,ny,nz,4)
  real :: lu(nx,ny,nz),lv(nx,ny,nz),lp(nx,ny,nz),lt(nx,ny,nz),lh(nx,ny,nz),lo(nx,ny,nz)
  real :: dx(nx,ny),dy(nx,ny),lat(nx,ny),ps(nx,ny),p(nz),dp(nz),tau(nx,ny)
  real :: erru(nx,ny,nz),errub(nx,ny,nz),errph(nx,ny,nz),errphb(nx,ny,nz),influence(nx,ny,nz)
  real :: before_rms,before_max,after_rms,after_max,wind_change
  real, parameter :: nonzero_residual_minimum=1.e-8
  real, parameter :: nonzero_wind_minimum=1.e-6
  real, parameter :: synthetic_moisture_minimum=0.
  real, parameter :: synthetic_moisture_maximum=.05
  integer :: k,status,nargs,arg_length,arg_status
  character(len=:), allocatable :: output_path
  logical :: export_requested
  external :: balcon,balstagger,continuity_metrics
  external :: report_qbal_agrid_residual,test_qbal_reverse_output

  nargs=command_argument_count()
  if(nargs>1) error stop 'BALCON export accepts at most one filename'
  export_requested=nargs==1
  if(export_requested)then
    call get_command_argument(1,length=arg_length,status=arg_status)
    if(arg_status/=0.or.arg_length==0) error stop 'BALCON export filename unavailable'
    allocate(character(len=arg_length) :: output_path)
    call get_command_argument(1,value=output_path,status=arg_status)
    if(arg_status/=0.or.len_trim(output_path)==0) error stop 'BALCON export filename is blank'
  endif

  p=[100000.,90000.,80000.,70000.]
  dp=10000.; dx=10000.; dy=10000.; lat=45.; ps=110000.
  tau=1.; erru=1.; errub=1.; errph=1.e-4; errphb=1.e-4; influence=1.
  ! A stronger top forcing exercises the capped omega diagnostic level.
  errph(:,:,nz)=2.e-4
  call prepare()
  call continuity_metrics(uo,vo,omo,nx,ny,nz,dx,dy,ps,p,dp,influence,before_rms,before_max,status)
  if(status/=1) error stop 'BALCON input continuity unavailable'
  call run(200,1.e-6)
  if(status/=1) error stop 'full BALCON valid candidate rejected'
  if(any(.not.ieee_is_finite(t)).or.any(.not.ieee_is_finite(u)).or. &
     any(.not.ieee_is_finite(v)).or.any(.not.ieee_is_finite(om))) error stop 'BALCON nonfinite output'
  call report_accepted_boundary_changes(u,v,om,saved(:,:,:,6),saved(:,:,:,7), &
     saved(:,:,:,8),'BALCON full accepted boundary')
  wind_change=maxval(sqrt((u-saved(:,:,:,6))**2+(v-saved(:,:,:,7))**2))
  if(wind_change<1.e-5) error stop 'BALCON success was a zero increment'
  if(maxval(abs(t-saved(:,:,:,1)))<1.e-3) error stop 'BALCON PHI relaxation did not change candidate'
  call continuity_metrics(u,v,om,nx,ny,nz,dx,dy,ps,p,dp,influence,after_rms,after_max,status)
  if(status/=1) error stop 'BALCON output continuity unavailable'
  if(after_rms>max(.25*before_rms,1.e-10).or.after_max>max(.25*before_max,1.e-10)) &
    error stop 'BALCON accepted candidate violates continuity reduction'
  call unchanged_background()
  call balstagger(lu,lv,lp,lt,lh,lo,u,v,t,tmp,shs,om,nx,ny,nz,p,ps,-1)
  if(any(.not.ieee_is_finite(lu)).or.any(.not.ieee_is_finite(lv)).or. &
     any(.not.ieee_is_finite(lp)).or.any(.not.ieee_is_finite(lt)).or. &
     any(.not.ieee_is_finite(lo))) error stop 'BALCON reverse stagger nonfinite'
  call check_moisture(lh,'BALCON reverse stagger moisture invalid')
  if(maxval(abs(lu))+maxval(abs(lv))<1.e-5) error stop 'BALCON reverse stagger lost increment'
  call report_qbal_agrid_residual(lu,lv,lo,nx,ny,nz,p,dx,dy)
  print *, 'Full BALCON accepted nonzero wind increment: ',wind_change

  call prepare(.true.)
  call continuity_metrics(uo,vo,omo,nx,ny,nz,dx,dy,ps,p,dp,influence,before_rms,before_max,status)
  if(status/=1.or.before_rms<=nonzero_residual_minimum.or. &
     before_max<=nonzero_residual_minimum) error stop 'BALCON localized input residual too small'
  ! Forward averaging gives two opposite 1.e-5 /s cells per layer,
  ! among (nx-1)*(ny-1) continuity cells; all boundary fluxes are zero.
  if(abs(before_max-1.e-5)>1.e-11.or. &
     abs(before_rms-1.e-5*sqrt(2./real((nx-1)*(ny-1))))>1.e-11) &
    error stop 'BALCON manufactured divergence pair mismatch'
  call run(200,1.e-6)
  if(status/=1) error stop 'BALCON localized residual candidate rejected'
  call unchanged_background()
  if(any(.not.ieee_is_finite(t)).or.any(.not.ieee_is_finite(u)).or. &
     any(.not.ieee_is_finite(v)).or.any(.not.ieee_is_finite(om))) error stop 'BALCON localized output nonfinite'
  call report_accepted_boundary_changes(u,v,om,saved(:,:,:,6),saved(:,:,:,7), &
     saved(:,:,:,8),'BALCON localized accepted boundary')
  wind_change=maxval(sqrt((u-saved(:,:,:,6))**2+(v-saved(:,:,:,7))**2))
  if(wind_change<nonzero_wind_minimum) error stop 'BALCON localized success did not change state'
  call continuity_metrics(u,v,om,nx,ny,nz,dx,dy,ps,p,dp,influence,after_rms,after_max,status)
  if(status/=1.or.after_rms>max(.25*before_rms,1.e-10).or. &
     after_max>max(.25*before_max,1.e-10)) error stop 'BALCON localized residual reduction failed'
  call balstagger(lu,lv,lp,lt,lh,lo,u,v,t,tmp,shs,om,nx,ny,nz,p,ps,-1)
  if(any(.not.ieee_is_finite(lu)).or.any(.not.ieee_is_finite(lv)).or. &
     any(.not.ieee_is_finite(lp)).or.any(.not.ieee_is_finite(lt)).or. &
     any(.not.ieee_is_finite(lo))) error stop 'BALCON localized reverse nonfinite'
  call check_moisture(lh,'BALCON localized reverse moisture invalid')
  if(export_requested) call export_reverse_output(output_path)
  call report_qbal_agrid_residual(lu,lv,lo,nx,ny,nz,p,dx,dy)
  print *, 'Full BALCON accepted localized residual reduction: ',before_rms,after_rms

  call prepare()
  ! One relaxation sweep cannot meet this tolerance for the nonzero PHI forcing.
  ! Rejection follows the continuity call and PHI perturbation construction.
  ! This case changes PHI before failure; not every saved field is mutated.
  call run(1,1.e-30)
  if(status/=0) error stop 'BALCON nonconvergent candidate accepted'
  call same_bits(t,saved(:,:,:,1)); call same_bits(u,saved(:,:,:,2))
  call same_bits(v,saved(:,:,:,3)); call same_bits(om,saved(:,:,:,4))
  call same_bits(to,saved(:,:,:,5)); call same_bits(uo,saved(:,:,:,6))
  call same_bits(vo,saved(:,:,:,7)); call same_bits(omo,saved(:,:,:,8))
  call unchanged_background()
  print *, 'Full BALCON late rejection: eight-array bitwise rollback PASS'
  call test_qbal_reverse_output()
contains
  subroutine prepare(localized_residual)
    ! Isothermal hydrostatic PHI gives finite temperatures on reverse staggering.
    logical, intent(in), optional :: localized_residual
    logical :: localized
    localized=.false.
    if(present(localized_residual))localized=localized_residual
    lu=0.; lv=0.; lo=0.; lt=280.; lh=0.001
    if(localized)then
      do k=1,nz
        ! 0.2 m/s exceeds the solver's 0.01 m/s correction scale.
        ! Compact support avoids the forward extrapolation boundaries.
        lu(3,3,k)=.2
      enddo
    endif
    call check_moisture(lh,'BALCON synthetic moisture invalid')
    do k=1,nz
      lp(:,:,k)=287.04*280.*log(p(1)/p(k))
    end do
    call balstagger(lu,lv,lp,lt,lh,lo,ub,vb,tb,tmp,shs,omb,nx,ny,nz,p,ps,1)
    call check_moisture(shs,'BALCON staggered moisture invalid')
    lp=lp+1.
    call balstagger(lu,lv,lp,lt,lh,lo,uo,vo,to,tmp,shs,omo,nx,ny,nz,p,ps,1)
    call check_moisture(shs,'BALCON forced staggered moisture invalid')
    if(localized.and.(maxval(abs(uo(1,:,:)))>1.e-12.or. &
       maxval(abs(uo(nx,:,:)))>1.e-12.or.maxval(abs(vo(:,1,:)))>1.e-12.or. &
       maxval(abs(vo(:,ny,:)))>1.e-12)) error stop 'BALCON localized input touches boundary flux'
    t=to; u=uo; v=vo; om=omo
    saved(:,:,:,1)=t; saved(:,:,:,2)=u; saved(:,:,:,3)=v; saved(:,:,:,4)=om
    saved(:,:,:,5)=to; saved(:,:,:,6)=uo; saved(:,:,:,7)=vo; saved(:,:,:,8)=omo
    background(:,:,:,1)=tb; background(:,:,:,2)=ub
    background(:,:,:,3)=vb; background(:,:,:,4)=omb
  end subroutine
  subroutine run(iterations,tolerance)
    integer, intent(in) :: iterations
    real, intent(in) :: tolerance
    call balcon(to,uo,vo,omo,t,u,v,om,tb,ub,vb,omb,tmp,1.,1.e8,tau, &
      iterations,tolerance,erru,errph,errub,errphb,influence,nx,ny,nz,lat,dx,dy,ps,p,dp,1,status)
  end subroutine
  subroutine unchanged_background()
    call same_bits(tb,background(:,:,:,1)); call same_bits(ub,background(:,:,:,2))
    call same_bits(vb,background(:,:,:,3)); call same_bits(omb,background(:,:,:,4))
  end subroutine
  subroutine same_bits(actual,expected)
    real, intent(in) :: actual(nx,ny,nz),expected(nx,ny,nz)
    if(any(transfer(actual,[0_int32],ncell)/=transfer(expected,[0_int32],ncell))) &
      error stop 'full BALCON changed preserved array bits'
  end subroutine
  subroutine check_moisture(field,message)
    real, intent(in) :: field(nx,ny,nz)
    character(len=*), intent(in) :: message
    if(any(.not.ieee_is_finite(field)).or.any(field<synthetic_moisture_minimum).or. &
       any(field>synthetic_moisture_maximum)) error stop message
  end subroutine
  subroutine export_reverse_output(filename)
    character(len=*), intent(in) :: filename
    integer :: unit,ios
    character(len=256) :: message

    ! Stream snapshot: int32 nx,ny,nz; default-real32 p, lu, lv, lp, lt, lh, lo.
    open(newunit=unit,file=filename,form='unformatted',access='stream',status='new', &
      action='write',convert='little_endian',iostat=ios,iomsg=message)
    if(ios/=0) error stop 'BALCON reverse output open failed'
    write(unit,iostat=ios,iomsg=message) nx,ny,nz,p,lu,lv,lp,lt,lh,lo
    if(ios/=0) error stop 'BALCON reverse output write failed'
    close(unit,iostat=ios,iomsg=message)
    if(ios/=0) error stop 'BALCON reverse output close failed'
  end subroutine
  subroutine report_accepted_boundary_changes(u,v,om,uo_ref,vo_ref,om_ref,label)
    ! The final LEIB_SUB projection may adjust legacy boundary faces. Report
    ! those changes without imposing an unsupported zero-increment contract.
    real, intent(in) :: u(nx,ny,nz),v(nx,ny,nz),om(nx,ny,nz)
    real, intent(in) :: uo_ref(nx,ny,nz),vo_ref(nx,ny,nz),om_ref(nx,ny,nz)
    character(len=*), intent(in) :: label
    real :: u_before,u_after,u_delta,v_before,v_after,v_delta
    real :: om_before,om_after,om_delta

    u_before=max(maxval(abs(uo_ref(1,:,:))),maxval(abs(uo_ref(nx,:,:))))
    u_after=max(maxval(abs(u(1,:,:))),maxval(abs(u(nx,:,:))))
    u_delta=max(maxval(abs(u(1,:,:)-uo_ref(1,:,:))), &
      maxval(abs(u(nx,:,:)-uo_ref(nx,:,:))))
    v_before=max(maxval(abs(vo_ref(:,1,:))),maxval(abs(vo_ref(:,ny,:))))
    v_after=max(maxval(abs(v(:,1,:))),maxval(abs(v(:,ny,:))))
    v_delta=max(maxval(abs(v(:,1,:)-vo_ref(:,1,:))), &
      maxval(abs(v(:,ny,:)-vo_ref(:,ny,:))))
    om_before=max(maxval(abs(om_ref(:,:,1))),maxval(abs(om_ref(:,:,nz))))
    om_after=max(maxval(abs(om(:,:,1))),maxval(abs(om(:,:,nz))))
    om_delta=max(maxval(abs(om(:,:,1)-om_ref(:,:,1))), &
      maxval(abs(om(:,:,nz)-om_ref(:,:,nz))))
    print *,trim(label),' U boundary max input/output/change (m/s): ',u_before,u_after,u_delta
    print *,trim(label),' V boundary max input/output/change (m/s): ',v_before,v_after,v_delta
    print *,trim(label),' OM endpoint max input/output/change (Pa/s): ',om_before,om_after,om_delta
  end subroutine
end program

! Fixture bindings for diagnostic metadata and clocks only. No numerical
! balance, interpolation, acceptance or state-copy routine is replaced.
subroutine get_grid_dim_xy(nx,ny,status)
  implicit none
  integer :: nx,ny,status
  nx=6; ny=6; status=1
end subroutine
subroutine get_r_missing_data(value,status)
  implicit none
  real :: value
  integer :: status
  value=1.e37; status=1
end subroutine
integer function init_timer()
  implicit none
  init_timer=1
end function
integer function ishow_timer()
  implicit none
  ishow_timer=0
end function
