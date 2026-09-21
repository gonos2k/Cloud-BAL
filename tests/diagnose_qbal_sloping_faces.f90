program diagnose_qbal_sloping_faces
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_finite
  use qbal_sloping_geometry
  implicit none
  integer :: nn,nz,nt,ne,unit,i,k,t,e,q,a,b,ids(3),nmissing
  integer, allocatable :: tri(:,:),edges(:,:),incidence(:,:)
  real(real64), allocatable :: lat(:),lon(:),ps(:),p(:),u(:,:),v(:,:),xy(:,:),scales(:,:)
  real(real64), allocatable :: edge_u(:,:),edge_v(:,:)
  real(real64) :: cell_xy(2,3),cell_ps(3),edge_xy(2,2),edge_ps(2)
  real(real64), allocatable :: edge_metric(:,:)
  real(real64) :: shared_error,expected_metric(3),comparison_scale(3)
  real(real64), allocatable :: flux(:),missing(:),volumes(:),ratios(:,:),lateral(:)
  real(real64) :: lat0,lon0,radius,cone,orientation,theta,ue,vn,m(3,5),mom(3,3,5),volume
  real(real64) :: metric_scale(3),moment_scale(3,3),identity(3,3),area
  logical :: ok
  character(1024) :: input,output
  ! Only the validated prepared stream is accepted, not a general data reader.
  call get_command_argument(1,input);call get_command_argument(2,output)
  open(newunit=unit,file=trim(input),access='stream',form='unformatted',status='old')
  read(unit) nn,nz,nt,ne
  if (min(nn,nz,nt,ne)<1) error stop 'invalid prepared dimensions'
  allocate(lat(nn),lon(nn),ps(nn),p(nz),u(nz,nn),v(nz,nn),xy(2,nn),scales(2,nn))
  allocate(edge_u(nz,2),edge_v(nz,2),edge_metric(3,ne))
  allocate(tri(3,nt),edges(2,ne),incidence(3,nt),flux(ne),missing(ne),volumes(nt),ratios(2,nt),lateral(nt))
  read(unit) lat0,lon0,radius,cone,orientation
  read(unit) lat,lon,ps,p,u,v,tri,edges,incidence
  close(unit)
  do i=1,nn
    call equal_area_point(lat(i),lon(i),lat0,lon0,radius,xy(:,i),scales(:,i),ok)
    if (.not.ok) error stop 'invalid chart point'
    ! cone=0 means supplied earth-relative winds; otherwise Lambert grid axes.
    theta=cone*(lon(i)-orientation)
    do k=1,nz
      ue=cos(theta)*u(k,i)+sin(theta)*v(k,i)
      vn=-sin(theta)*u(k,i)+cos(theta)*v(k,i)
      u(k,i)=scales(1,i)*ue;v(k,i)=scales(2,i)*vn
    end do
  end do
  nmissing=0;shared_error=0
  do e=1,ne
    a=edges(1,e);b=edges(2,e)
    edge_metric(:,e)=[xy(2,b)-xy(2,a),xy(1,a)-xy(1,b),0._real64]*((ps(a)+ps(b))/2-p(nz))
    ! Use only physical above-ground samples at BOTH edge endpoints.
    q=0
    do k=1,nz-1
      if (p(k)<=min(ps(a),ps(b))) then
        q=k;exit
      end if
    end do
    if (q==0) error stop 'no two-level joint wind coverage'
    edge_xy=xy(:,[a,b]);edge_ps=ps([a,b]);edge_u=u(:,[a,b]);edge_v=v(:,[a,b])
    call edge_wind_flux(edge_xy,edge_ps,p(nz),p(q:), &
                       edge_u(q:,:),edge_v(q:,:),flux(e),missing(e),ok)
    if (.not.ok) error stop 'invalid edge transport'
    if (missing(e)>0) nmissing=nmissing+1
  end do
  do t=1,nt
    ids=tri(:,t)
    cell_xy=xy(:,ids);cell_ps=ps(ids)
    call sloping_column_faces(cell_xy,cell_ps,p(nz),m,mom,volume,ok)
    if (.not.ok) error stop 'invalid sloping cell'
    volumes(t)=volume
    identity=0
    do i=1,3
      identity(i,i)=volume
    end do
    metric_scale=sum(abs(m),dim=2)
    moment_scale=sum(abs(mom),dim=3)+abs(identity)
    where (metric_scale==0) metric_scale=1
    where (moment_scale==0) moment_scale=1
    ratios(1,t)=maxval(abs(sum(m,dim=2))/metric_scale)
    ratios(2,t)=maxval(abs(sum(mom,dim=3)-identity)/moment_scale)
    if (maxval(ratios(:,t))>128*epsilon(volume)) error stop 'cell geometry does not close'
    area=abs(m(3,1));lateral(t)=0
    do i=1,3
      e=incidence(i,t)
      expected_metric=sign(1._real64,real(e,real64))*edge_metric(:,abs(e))
      ! Include coordinate subtraction before cancellation, not just the final
      ! metric component (an almost axis-aligned edge can have tiny dy).
      a=edges(1,abs(e));b=edges(2,abs(e))
      comparison_scale=[abs(xy(2,a))+abs(xy(2,b))+2*abs(cell_xy(2,1)), &
                        abs(xy(1,a))+abs(xy(1,b))+2*abs(cell_xy(1,1)),0._real64] &
                       *(ps(a)+ps(b)+2*p(nz))
      comparison_scale=comparison_scale+abs(m(:,i+2))+abs(expected_metric)
      where (comparison_scale==0) comparison_scale=1
      shared_error=max(shared_error,maxval(abs(m(:,i+2)-expected_metric)/comparison_scale))
      if (shared_error>128*epsilon(volume)) error stop 'shared metric/incidence mismatch'
      lateral(t)=lateral(t)+sign(1._real64,real(e,real64))*flux(abs(e))
    end do
    lateral(t)=lateral(t)/area
  end do
  open(newunit=unit,file=trim(output),access='stream',form='unformatted',status='new')
  write(unit) xy,flux,missing,volumes,ratios,lateral
  close(unit)
  print '(a,i0)', 'triangular_columns=',nt
  print '(a,i0)', 'shared_or_outer_edges=',ne
  print '(a,i0)', 'edges_with_uncovered_surface_strip=',nmissing
  print '(a,es24.16)', 'maximum_shared_metric_arithmetic_ratio=',shared_error
  print '(a,es24.16)', 'maximum_constant_metric_relative_error=',maxval(ratios(1,:))
  print '(a,es24.16)', 'maximum_affine_moment_relative_error=',maxval(ratios(2,:))
  print '(a,es24.16)', 'maximum_uncovered_pressure_integral_pa=',maxval(missing)
  print '(a,es24.16)', 'maximum_covered_side_flux_m2_pa_per_s=',maxval(abs(flux))
  print '(a,es24.16)', 'maximum_partial_lateral_transport_pa_per_s=',maxval(abs(lateral))
end program
