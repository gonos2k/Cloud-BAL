! One prepared real face; variances are explicit research scenarios.
program diagnose_qbal_profile_face
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_finite
  use qbal_profile_face, only: fit_edge_transport
  use qbal_sloping_geometry, only: edge_wind_flux, equal_area_point, sloping_column_faces
  use qbal_pressure_flux, only: flux_divergence
  implicit none
  integer :: n,scenarios,unit,j,k,e
  character(1024) :: input,output
  real(real64) :: xy(2,2),ps(2),pt,p_sample(2),sample_wind(2,2),volume(2)
  real(real64) :: parameters(5),lat(2),lon(2),scale(2),theta,east,north
  real(real64) :: cell_xy(2,3,2),cell_ps(3,2),metric(3,5),moment(3,3,5)
  real(real64), allocatable :: p(:),wind(:,:,:),variance(:,:,:),sample_variance(:,:,:)
  real(real64), allocatable :: fitted(:,:,:,:),innovation(:,:,:),flux(:),uncovered(:)
  real(real64), allocatable :: reverse_flux(:),partition_error(:,:),contribution(:,:)
  real(real64), allocatable :: trial(:,:,:),u(:,:),v(:,:),reverse_wind(:,:,:),reverse_variance(:,:,:)
  real(real64) :: reverse_xy(2,2),reverse_ps(2),reverse_sample(2),reverse_obs(2,2),reverse_r(2,2)
  real(real64) :: difference(2,2),missing,baseline,upper,lower,cap,flat_cap(2),one_flux(1)
  integer :: plus(1),minus(1)
  logical :: ok
  call get_command_argument(1,input);call get_command_argument(2,output)
  open(newunit=unit,file=trim(input),status='old',action='read')
  read(unit,*) n,scenarios
  if (n<3.or.n>1000.or.scenarios/=3) error stop 'invalid study dimensions'
  allocate(p(n),wind(n,2,2),variance(n,2,2),sample_variance(2,2,scenarios))
  read(unit,*) parameters,lat,lon
  read(unit,*) ps
  read(unit,*) pt
  read(unit,*) p
  read(unit,*) wind
  read(unit,*) variance
  read(unit,*) p_sample
  read(unit,*) sample_wind
  read(unit,*) sample_variance
  read(unit,*) cell_xy
  read(unit,*) cell_ps
  close(unit)
  ! This driver fixes its research sweep and partition test before looking at flux.
  if (.not.all(ieee_is_finite(variance)).or..not.all(ieee_is_finite(sample_variance))) &
    error stop 'nonfinite study variances'
  if (any(variance/=1._real64).or.any(sample_variance(:,:,1)/=0.25_real64).or. &
      any(sample_variance(:,:,2)/=1._real64).or.any(sample_variance(:,:,3)/=4._real64)) &
    error stop 'unexpected study variance sweep'
  if (.not.all(ieee_is_finite(p_sample)).or..not.all(ieee_is_finite(p))) &
    error stop 'nonfinite study pressure'
  if (minval(p_sample)<=p(2)+1.e-3_real64.or.pt>=p(2)-1.e-3_real64) &
    error stop 'study partition must lie between finite top and both samples'
  do e=1,2
    call equal_area_point(lat(e),lon(e),parameters(1),parameters(2),parameters(3),xy(:,e),scale,ok)
    if (.not.ok) error stop 'invalid endpoint chart'
    theta=parameters(4)*(lon(e)-parameters(5))
    do k=1,n
      east=cos(theta)*wind(k,1,e)+sin(theta)*wind(k,2,e)
      north=-sin(theta)*wind(k,1,e)+cos(theta)*wind(k,2,e)
      wind(k,:,e)=scale*[east,north]
    end do
    east=cos(theta)*sample_wind(1,e)+sin(theta)*sample_wind(2,e)
    north=-sin(theta)*sample_wind(1,e)+cos(theta)*sample_wind(2,e)
    sample_wind(:,e)=scale*[east,north]
    call sloping_column_faces(cell_xy(:,:,e),cell_ps(:,e),pt,metric,moment,volume(e),ok)
    if (.not.ok) error stop 'invalid incident cell'
  end do
  allocate(fitted(n,2,2,scenarios),innovation(2,2,scenarios),flux(scenarios),uncovered(scenarios))
  allocate(reverse_flux(scenarios),partition_error(2,scenarios),contribution(2,scenarios))
  allocate(trial(n,2,2),u(n,2),v(n,2),reverse_wind(n,2,2),reverse_variance(n,2,2))
  u=wind(:,1,:);v=wind(:,2,:)
  call edge_wind_flux(xy,p_sample,pt,p,u,v,baseline,missing,ok)
  if (.not.ok.or.missing/=0._real64) error stop 'unsupported baseline'
  reverse_xy=xy(:,2:1:-1);reverse_ps=ps(2:1:-1);reverse_sample=p_sample(2:1:-1)
  reverse_wind=wind(:,:,2:1:-1);reverse_variance=variance(:,:,2:1:-1)
  reverse_obs=sample_wind(:,2:1:-1)
  plus=1;minus=2
  do j=1,scenarios
    call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind,sample_variance(:,:,j), &
      fitted(:,:,:,j),innovation(:,:,j),flux(j),uncovered(j),ok)
    if (.not.ok) error stop 'unsupported endpoint fit'
    reverse_r=sample_variance(:,2:1:-1,j)
    call fit_edge_transport(reverse_xy,reverse_ps,pt,p,reverse_wind,reverse_variance,reverse_sample, &
      reverse_obs,reverse_r,trial,difference,reverse_flux(j),missing,ok)
    if (.not.ok) error stop 'unsupported reversed fit'
    u=fitted(:,1,:,j);v=fitted(:,2,:,j)
    do k=1,2
      ! Move only the integration partition across a knot; never refit here.
      cap=p(2)+real(2*k-3,real64)*1.e-3_real64
      flat_cap=cap
      call edge_wind_flux(xy,flat_cap,pt,p,u,v,upper,missing,ok)
      if (.not.ok.or.missing/=0._real64) error stop 'unsupported upper partition'
      call edge_wind_flux(xy,p_sample,cap,p,u,v,lower,missing,ok)
      if (.not.ok.or.missing/=0._real64) error stop 'unsupported lower partition'
      partition_error(k,j)=upper+lower-flux(j)
    end do
    ! One stored face is consumed with opposite signs by its two incident cells.
    one_flux=flux(j)
    call flux_divergence(volume,plus,minus,one_flux,contribution(:,j),ok)
    if (.not.ok) error stop 'invalid shared incidence'
  end do
  open(newunit=unit,file=trim(output),status='new',access='stream',form='unformatted')
  write(unit) xy,wind,sample_wind,volume,baseline,flux,reverse_flux,uncovered, &
              partition_error,contribution,fitted,innovation
  close(unit)
end program diagnose_qbal_profile_face
