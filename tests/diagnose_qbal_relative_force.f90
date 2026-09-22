! Read-only common-pressure relative geopotential and horizontal force.
program diagnose_qbal_relative_force
  use iso_fortran_env, only: real64,int64
  use ieee_arithmetic, only: ieee_is_finite,ieee_value,ieee_quiet_nan
  use qbal_sloping_geometry, only: equal_area_point
  use qbal_relative_pressure_force, only: build_relative_geopotential,triangle_pressure_force
  implicit none
  integer :: nn,nz,nt,ref,unit,j,k,t,c,indices(3)
  integer(int64) :: bytes,expected
  character(1024) :: input,output
  real(real64), parameter :: g0=9.80665_real64
  real(real64) :: parameters(3),nan,scale(2),latc,det,edge_size,condition,coefficient(2,3)
  real(real64) :: vertices(2,3),nodes(3),grad(2),accel(2),local_scale
  real(real64), allocatable :: p(:),lat(:),lon(:),ps(:),layers(:,:,:),xy(:,:),evaluation_latitude(:)
  real(real64), allocatable :: phi(:,:,:),phi_bound(:,:),gradient(:,:,:,:),force(:,:,:,:),force_bound(:,:)
  real(real64), allocatable :: dz(:,:),trial(:,:)
  integer, allocatable :: valid(:,:),supported(:,:),tri(:,:),reachable(:,:),triangle_support(:,:)
  logical, allocatable :: local_valid(:),local_layers(:),connected(:)
  logical :: ok
  call get_command_argument(1,input)
  call get_command_argument(2,output)
  open(newunit=unit,file=trim(input),status='old',form='unformatted',access='stream')
  read(unit) nn,nz,nt,ref
  if (nn<3.or.nn>1000000.or.nz<2.or.nz>1000.or.nt<1.or.nt>2000000) error stop 'invalid dimensions'
  if (ref<1.or.ref>nz) error stop 'invalid reference'
  inquire(unit=unit,size=bytes)
  expected=16_int64+8_int64*(3+nz+3_int64*nn+4_int64*nn*(nz-1))+ &
    4_int64*(int(nn,int64)*nz+int(nn,int64)*(nz-1)+3_int64*nt)
  if (bytes/=expected) error stop 'invalid stream extent'
  allocate(p(nz),lat(nn),lon(nn),ps(nn),layers(4,nn,nz-1),valid(nn,nz),supported(nn,nz-1),tri(3,nt))
  read(unit) parameters,p,lat,lon,ps,layers,valid,supported,tri
  close(unit)
  if (.not.all(ieee_is_finite(p)).or..not.all(ieee_is_finite(ps))) error stop 'invalid pressure'
  if (any(p<100).or.any(p>120000).or.any(p(:nz-1)<=p(2:))) error stop 'invalid pressure grid'
  if (any(ps<=p(nz)).or.any(ps>120000)) error stop 'invalid PS'
  if (any(valid/=0.and.valid/=1).or.any(supported/=0.and.supported/=1)) error stop 'invalid support flags'
  if (any(supported/=valid(:,:nz-1)*valid(:,2:))) error stop 'inconsistent layer support'
  do k=1,nz
    if (any(valid(:,k)==1.and.p(k)>ps)) error stop 'underground support'
  end do
  if (any(tri<1).or.any(tri>nn)) error stop 'invalid triangle index'
  nan=ieee_value(0._real64,ieee_quiet_nan)
  allocate(xy(2,nn),evaluation_latitude(nt),phi(3,nn,nz),phi_bound(nn,nz), &
    gradient(2,3,nt,nz),force(2,3,nt,nz),force_bound(nt,nz),reachable(nn,nz),triangle_support(nt,nz), &
    dz(3,nz-1),trial(3,nz),local_valid(nz),local_layers(nz-1),connected(nz))
  phi=nan;phi_bound=nan;gradient=nan;force=nan;force_bound=nan;reachable=0;triangle_support=0
  do j=1,nn
    call equal_area_point(lat(j),lon(j),parameters(1),parameters(2),parameters(3),xy(:,j),scale,ok)
    if (.not.ok) error stop 'invalid chart coordinate'
    dz=layers(:3,j,:);local_valid=valid(j,:)==1;local_layers=supported(j,:)==1
    do k=1,nz-1
      if (.not.local_layers(k)) cycle
      if (.not.all(ieee_is_finite(layers(:,j,k)))) error stop 'invalid supported layer'
      if (layers(4,j,k)<0) error stop 'negative arithmetic bound'
      if (abs(sum(dz(:2,k))-dz(3,k))>layers(4,j,k)) error stop 'input attribution closure'
    end do
    if (.not.local_valid(ref)) cycle
    call build_relative_geopotential(dz,local_valid,local_layers,ref,trial,connected,ok)
    if (.not.ok) error stop 'relative integration failed'
    phi(:,j,:)=trial;reachable(j,:)=merge(1,0,connected)
    if (.not.connected(ref)) cycle
    phi_bound(j,ref)=0
    do k=ref-1,1,-1
      if (.not.connected(k)) exit
      phi_bound(j,k)=phi_bound(j,k+1)+g0*layers(4,j,k)+64*epsilon(1._real64)* &
        (sum(abs(trial(:,k)))+sum(abs(trial(:,k+1)))+g0*sum(abs(dz(:,k))))
    end do
    do k=ref+1,nz
      if (.not.connected(k)) exit
      phi_bound(j,k)=phi_bound(j,k-1)+g0*layers(4,j,k-1)+64*epsilon(1._real64)* &
        (sum(abs(trial(:,k)))+sum(abs(trial(:,k-1)))+g0*sum(abs(dz(:,k-1))))
    end do
  end do
  do t=1,nt
    indices=tri(:,t);vertices=xy(:,indices)
    latc=sin(parameters(1))+sum(vertices(2,:))/3*cos(parameters(1))/parameters(3)
    if (.not.ieee_is_finite(latc).or.abs(latc)>=1) error stop 'invalid triangle latitude'
    latc=asin(latc);evaluation_latitude(t)=latc
    nodes=0
    call triangle_pressure_force(vertices,nodes,latc,parameters(1),grad,accel,ok)
    if (.not.ok) error stop 'invalid triangle geometry'
    det=(vertices(1,2)-vertices(1,1))*(vertices(2,3)-vertices(2,1))- &
        (vertices(1,3)-vertices(1,1))*(vertices(2,2)-vertices(2,1))
    coefficient(1,:)=[vertices(2,2)-vertices(2,3),vertices(2,3)-vertices(2,1),vertices(2,1)-vertices(2,2)]/det
    coefficient(2,:)=[vertices(1,3)-vertices(1,2),vertices(1,1)-vertices(1,3),vertices(1,2)-vertices(1,1)]/det
    scale=[cos(parameters(1))/cos(latc),cos(latc)/cos(parameters(1))]
    edge_size=maxval(abs(vertices-spread(vertices(:,1),2,3)))
    condition=1+maxval(abs(vertices))/edge_size
    do k=1,nz
      if (.not.all(reachable(indices,k)==1)) cycle
      do c=1,3
        nodes=phi(c,indices,k)
        call triangle_pressure_force(vertices,nodes,latc,parameters(1),grad,accel,ok)
        if (.not.ok) error stop 'pressure force failed'
        gradient(:,c,t,k)=grad;force(:,c,t,k)=accel
      end do
      local_scale=sum(abs(phi(:,indices,k)))
      force_bound(t,k)=maxval(scale)*maxval(sum(abs(coefficient),dim=2))* &
        (maxval(phi_bound(indices,k))+256*epsilon(1._real64)*condition*local_scale)
      if (.not.ieee_is_finite(force_bound(t,k))) error stop 'invalid force bound'
      if (any(abs(force(:,1,t,k)+force(:,2,t,k)-force(:,3,t,k))>force_bound(t,k))) &
        error stop 'force attribution closure'
      triangle_support(t,k)=1
    end do
  end do
  open(newunit=unit,file=trim(output),status='new',form='unformatted',access='stream')
  write(unit) reachable,triangle_support,xy,evaluation_latitude,phi,phi_bound,gradient,force,force_bound
  close(unit)
end program
