! Prepared-input research replay. No production state or boundary is modified.
program diagnose_qbal_lower_transport
  use iso_fortran_env, only: real64,int64
  use ieee_arithmetic, only: ieee_value,ieee_quiet_nan,ieee_is_finite
  use qbal_sloping_geometry
  use qbal_column_budget
  use qbal_lower_transport
  use qbal_domain_flux
  use qbal_surface_thermo
  implicit none
  integer :: nn,nz,nt,ne,unit,i,j,k,e,t,a,b,q,ids(3),external_unknown,internal_unknown,cell_signs(3)
  integer, allocatable :: tri(:,:),edges(:,:),incidence(:,:),mapped(:,:)
  integer(int64) :: times(3)
  real(real64), allocatable :: lat(:),lon(:),terrain(:),ps(:,:),p(:),height(:,:,:)
  real(real64), allocatable :: u(:,:,:),v(:,:,:),us(:,:),vs(:,:),omega(:,:)
  real(real64), allocatable :: xy(:,:),scales(:,:),p10(:,:),covered(:,:),lower(:,:),missing(:,:)
  real(real64), allocatable :: area(:),surface(:),top(:,:),known(:),residual(:),volume_rate(:),bound(:)
  real(real64) :: parameters(5),theta,ue,vn,cap,wind0(2,2),wind1(2,2),nan,m(3,5),mom(3,3,5),volume
  real(real64) :: edge_mean(3),zero(3),top_mean,subtotal,cell_residual
  real(real64) :: edge_xy(2,2),edge_ps(2),edge_p10(2),cell_xy(2,3),cell_ps(3,3)
  real(real64), allocatable :: edge_u(:,:),edge_v(:,:)
  real(real64), allocatable :: transport_mean(:),top_average(:),unknown_flux(:)
  logical, allocatable :: unknown_mask(:),top_mask(:)
  real(real64) :: domain_subtotal,domain_residual
  logical :: ok,complete,orientation_ok,cell_missing_known(3)
  character(1024) :: input,output,pressure_model,audit_mode
  real(real64), allocatable :: surface_t(:,:),surface_r(:,:),profile_t(:,:,:),profile_r(:,:,:)
  real(real64), allocatable :: thermo(:,:,:),layer_defect(:,:,:),tv_profile(:)
  logical :: thermodynamic,cap_audit
  real(real64), allocatable :: cap_diagnostics(:,:,:)
  real(real64) :: wind_next(2,2),shifted_pressure(2),jump
  integer :: transition
  real(real64) :: tv0,dheight,dtemperature,old_pressure
  call get_command_argument(1,input);call get_command_argument(2,output)
  call get_command_argument(3,pressure_model)
  thermodynamic=trim(pressure_model)=='surface-thermo'
  call get_command_argument(4,audit_mode)
  cap_audit=trim(audit_mode)=='cap-audit'
  if (len_trim(audit_mode)>0.and..not.cap_audit) error stop 'unknown profile audit'
  if (cap_audit.and..not.thermodynamic) error stop 'cap audit requires thermodynamic prior'
  if (len_trim(pressure_model)>0.and..not.thermodynamic) error stop 'unknown pressure model'
  open(newunit=unit,file=trim(input),access='stream',form='unformatted',status='old')
  read(unit) nn,nz,nt,ne,times,parameters
  if (min(nn,nz,nt,ne)<1) error stop 'invalid dimensions'
  if (times(2)-times(1)/=times(3)-times(2).or.times(2)<=times(1)) error stop 'unequal time samples'
  allocate(lat(nn),lon(nn),terrain(nn),ps(nn,3),p(nz),height(nz,nn,3),u(nz,nn,3),v(nz,nn,3))
  allocate(us(nn,3),vs(nn,3),omega(nn,3),tri(3,nt),edges(2,ne),incidence(3,nt))
  read(unit) lat,lon,terrain,p,ps,height,u,v,us,vs,omega,tri,edges,incidence
  if (thermodynamic) then
    allocate(surface_t(nn,3),surface_r(nn,3),profile_t(nz,nn,3),profile_r(nz,nn,3))
    read(unit) surface_t,surface_r,profile_t,profile_r
    allocate(thermo(5,nn,3),layer_defect(nz-1,nn,3),tv_profile(nz))
    thermo=ieee_value(0._real64,ieee_quiet_nan);layer_defect=thermo(1,1,1)
  end if
  close(unit)
  allocate(edge_u(nz,2),edge_v(nz,2))
  allocate(xy(2,nn),scales(2,nn),p10(nn,3),mapped(nn,3),covered(ne,3),lower(ne,3),missing(ne,3))
  allocate(area(nt),surface(nt),top(nt,3),known(nt),residual(nt),volume_rate(nt),bound(nt))
  nan=ieee_value(0._real64,ieee_quiet_nan);p10=nan;lower=nan;mapped=0
  if (cap_audit) then
    allocate(cap_diagnostics(5,ne,3));cap_diagnostics=nan
  end if
  do i=1,nn
    call equal_area_point(lat(i),lon(i),parameters(1),parameters(2),parameters(3),xy(:,i),scales(:,i),ok)
    if (.not.ok) error stop 'invalid coordinates'
    theta=parameters(4)*(lon(i)-parameters(5))
    do j=1,3
      do k=1,nz
        ue=cos(theta)*u(k,i,j)+sin(theta)*v(k,i,j)
        vn=-sin(theta)*u(k,i,j)+cos(theta)*v(k,i,j)
        u(k,i,j)=scales(1,i)*ue;v(k,i,j)=scales(2,i)*vn
      end do
      ue=cos(theta)*us(i,j)+sin(theta)*vs(i,j)
      vn=-sin(theta)*us(i,j)+cos(theta)*vs(i,j)
      us(i,j)=scales(1,i)*ue;vs(i,j)=scales(2,i)*vn
      call pressure_at_height(ps(i,j),terrain(i),p,height(:,i,j),10._real64,p10(i,j),ok)
      if (thermodynamic) then
        old_pressure=p10(i,j)
        call thermodynamic_sample_pressure(ps(i,j),surface_t(i,j),surface_r(i,j),10._real64, &
                                           p10(i,j),tv0,dheight,dtemperature,ok)
        thermo(1:4,i,j)=[tv0,dheight,dtemperature,old_pressure]
        if (ok) then
          ! Diagnostic height residuals do not alter the thin-layer prior.
          tv_profile=nan
          do k=1,nz
            if (p(k)>=ps(i,j)) cycle
            call virtual_temperature_from_mixing(p(k),profile_t(k,i,j),profile_r(k,i,j),tv_profile(k),complete)
          end do
          do k=1,nz
            if (p(k)>=ps(i,j)) cycle
            call hydrostatic_height_defect(ps(i,j),p(k),terrain(i),height(k,i,j),tv0,tv_profile(k), &
                                           thermo(5,i,j),complete)
            exit
          end do
          do k=1,nz-1
            if (p(k)>=ps(i,j)) cycle
            call hydrostatic_height_defect(p(k),p(k+1),height(k,i,j),height(k+1,i,j), &
                                           tv_profile(k),tv_profile(k+1),layer_defect(k,i,j),complete)
          end do
        end if
      end if
      if (ok) mapped(i,j)=1
    end do
  end do
  do j=1,3
    do e=1,ne
      a=edges(1,e);b=edges(2,e)
      cap=min(ps(a,j),ps(b,j))
      if (all(mapped([a,b],j)==1)) cap=minval(p10([a,b],j))
      q=0
      do k=1,nz-1
        if (p(k)<=cap) then
          q=k;exit
        end if
      end do
      if (q==0) error stop 'no supported upper profile'
      edge_xy=xy(:,[a,b]);edge_ps=ps([a,b],j)
      edge_u=u(:,[a,b],j);edge_v=v(:,[a,b],j)
      call edge_wind_flux(edge_xy,edge_ps,p(nz),p(q:), &
                         edge_u(q:,:),edge_v(q:,:),covered(e,j),missing(e,j),ok)
      if (.not.ok) error stop 'invalid covered flux'
      if (.not.all(mapped([a,b],j)==1)) cycle
      wind0(1,:)=us([a,b],j);wind0(2,:)=vs([a,b],j)
      wind1(1,:)=u(q,[a,b],j);wind1(2,:)=v(q,[a,b],j)
      edge_p10=p10([a,b],j)
      call lower_strip_flux(edge_xy,edge_p10,p(q),wind0,wind1,lower(e,j),ok)
      if (.not.ok) error stop 'invalid lower strip'
      missing(e,j)=sum(ps([a,b],j)-p10([a,b],j))/2
      if (cap_audit) then
        ! Current cap crossing from below in pressure, translating sample pressures
        ! by the same amount while holding all winds fixed. Not a time tendency.
        transition=q
        shifted_pressure=edge_p10+(p(transition)-minval(edge_p10))
        where (edge_p10==minval(edge_p10)) shifted_pressure=p(transition)
        wind1(1,:)=u(transition,[a,b],j);wind1(2,:)=v(transition,[a,b],j)
        wind_next(1,:)=u(transition+1,[a,b],j);wind_next(2,:)=v(transition+1,[a,b],j)
        call cap_switch_jump(edge_xy,shifted_pressure,p(transition),p(transition+1), &
                             wind0,wind1,wind_next,jump,ok)
        if (.not.ok) error stop 'invalid cap-limit audit'
        cap_diagnostics(:,e,j)=[real(q,real64),p(transition)-minval(edge_p10),jump, &
                                maxval(abs(wind1(1,:)-wind0(1,:))), &
                                maxval(abs(wind1(2,:)-wind0(2,:)))]
      end if
    end do
  end do
  do t=1,nt
    ids=tri(:,t);cell_xy=xy(:,ids);cell_ps=ps(ids,:)
    call surface_pressure_flux(cell_xy,cell_ps(:,1),cell_ps(:,3),p(nz),times(1),times(3),.true., &
                               surface(t),volume_rate(t),bound(t),ok)
    if (.not.ok) error stop 'surface volume identity'
    call sloping_column_faces(cell_xy,cell_ps(:,2),p(nz),m,mom,volume,ok)
    if (.not.ok) error stop 'invalid triangle'
    area(t)=m(3,1)
    do j=1,3
      top(t,j)=area(t)*sum(omega(ids,j))/3
    end do
    do i=1,3
      e=abs(incidence(i,t));edge_mean(i)=0
      do j=1,3
        subtotal=covered(e,j)
        if (all(mapped(edges(:,e),j)==1)) subtotal=subtotal+lower(e,j)
        k=1
        if (j==2) k=4
        edge_mean(i)=edge_mean(i)+k*subtotal/6
      end do
    end do
    top_mean=(top(t,1)+4*top(t,2)+top(t,3))/6
    zero=nan;cell_signs=sign(1,incidence(:,t));cell_missing_known=.false.
    call column_flux_budget(surface(t),edge_mean,zero,cell_signs, &
                            cell_missing_known,top_mean,.true., &
                            known(t),cell_residual,complete,ok)
    if (.not.ok.or.complete) error stop 'invalid incomplete column'
    residual(t)=cell_residual
  end do
  allocate(transport_mean(ne),top_average(nt),unknown_flux(ne),unknown_mask(ne),top_mask(nt))
  transport_mean=0;unknown_flux=nan;unknown_mask=.false.;top_mask=.true.
  do j=1,3
    k=1
    if (j==2) k=4
    do e=1,ne
      subtotal=covered(e,j)
      if (all(mapped(edges(:,e),j)==1)) subtotal=subtotal+lower(e,j)
      transport_mean(e)=transport_mean(e)+k*subtotal/6
    end do
  end do
  top_average=(top(:,1)+4*top(:,2)+top(:,3))/6
  call domain_flux_budget(incidence,surface,transport_mean,unknown_flux,unknown_mask,top_average,top_mask, &
                          domain_subtotal,domain_residual,complete,external_unknown,orientation_ok,ok, &
                          internal_unknown)
  if (.not.ok.or..not.orientation_ok.or.complete) error stop 'invalid incomplete domain'
  open(newunit=unit,file=trim(output),access='stream',form='unformatted',status='new')
  write(unit) xy,p10,covered,lower,missing,area,surface,volume_rate,bound,top,known,residual,mapped
  write(unit) domain_subtotal,domain_residual,external_unknown,internal_unknown
  if (thermodynamic) write(unit) thermo,layer_defect
  if (cap_audit) write(unit) cap_diagnostics
  close(unit)
end program
