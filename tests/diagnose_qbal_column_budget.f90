program diagnose_qbal_column_budget
  use iso_fortran_env, only: real64,int64
  use ieee_arithmetic, only: ieee_value,ieee_quiet_nan
  use qbal_column_budget
  use qbal_sloping_geometry, only: sloping_column_faces
  implicit none
  integer :: nn,nt,ne,unit,t,ids(3),faces(3),directions(3)
  integer(int64) :: t0,t1
  integer, allocatable :: tri(:,:),incidence(:,:),top_valid(:)
  real(real64), allocatable :: xy(:,:),ps0(:),ps1(:),ps(:),omega_top(:),covered(:),uncovered(:),terms(:,:)
  real(real64) :: pt,cell_xy(2,3),p0(3),p1(3),pc(3),ground,rate,bound,area,top,side(3),missing(3)
  real(real64) :: m(3,5),moment(3,3,5),volume,subtotal,residual,nan
  logical :: ok,complete,top_known,missing_known(3)
  character(1024) :: input,output
  call get_command_argument(1,input);call get_command_argument(2,output)
  open(newunit=unit,file=trim(input),access='stream',form='unformatted',status='old')
  read(unit) nn,nt,ne,t0,t1,pt
  if (min(nn,nt,ne)<1) error stop 'invalid prepared extent'
  allocate(xy(2,nn),ps0(nn),ps1(nn),ps(nn),omega_top(nn),top_valid(nn),tri(3,nt),incidence(3,nt))
  allocate(covered(ne),uncovered(ne),terms(8,nt))
  read(unit) xy,ps0,ps1,ps,omega_top,top_valid,tri,incidence,covered,uncovered
  close(unit)
  nan=ieee_value(0._real64,ieee_quiet_nan)
  do t=1,nt
    ids=tri(:,t);faces=abs(incidence(:,t));directions=sign(1,incidence(:,t))
    cell_xy=xy(:,ids);p0=ps0(ids);p1=ps1(ids);pc=ps(ids)
    call surface_pressure_flux(cell_xy,p0,p1,pt,t0,t1,.true.,ground,rate,bound,ok)
    if (.not.ok) error stop 'surface flux / volume rate does not close'
    call sloping_column_faces(cell_xy,pc,pt,m,moment,volume,ok)
    if (.not.ok) error stop 'invalid central geometry'
    area=m(3,1)
    top_known=all(top_valid(ids)==1);top=nan
    if (top_known) top=area*sum(omega_top(ids))/3
    side=covered(faces);missing=nan;missing_known=uncovered(faces)==0
    where (missing_known) missing=0
    call column_flux_budget(ground,side,missing,directions,missing_known,top,top_known, &
                            subtotal,residual,complete,ok)
    if (.not.ok) error stop 'invalid column flux terms'
    ! Integrated terms retain m2 Pa/s; area allows separate Pa/s diagnostics.
    terms(:,t)=[area,ground,rate,bound,sum(directions*side),top,subtotal,residual]
  end do
  open(newunit=unit,file=trim(output),access='stream',form='unformatted',status='new')
  write(unit) terms
  close(unit)
  print '(a,i0)', 'columns=',nt
  print '(a,es24.16)', 'maximum_surface_flux_pa_per_s=',maxval(abs(terms(2,:)/terms(1,:)))
  print '(a,es24.16)', 'maximum_volume_rate_difference=',maxval(abs(terms(2,:)-terms(3,:)))
end program
