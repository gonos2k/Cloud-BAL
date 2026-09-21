! Prepared input and outputs are read-only diagnostic copies, never candidates.
program diagnose_qbal_physical_boundary
  use iso_fortran_env, only: real32,real64,int32,int64
  use qbal_physical_boundary
  implicit none
  integer :: nx,ny,nz,nc,iu,ou,i,j,k,q,near,status,f,c1,c2,face,ios
  character(2048) :: input,output
  real(real64), allocatable :: p(:),dp(:),ps(:,:),dx(:,:),dy(:,:),u(:,:,:),v(:,:,:),w(:,:,:),p0(:,:),p1(:,:)
  real(real64), allocatable :: op(:),spacing(:),h(:),omegas(:),partial(:,:),tendency(:,:),sums(:,:,:),influence(:,:)
  integer(int32), allocatable :: labels(:,:,:),mapping(:,:,:),counts(:,:)
  logical, allocatable :: valid(:)
  real(real64) :: a,b,total,lateral,ends,error,bound
  real(real64), parameter :: sentinel=real(1.e-30_real32,real64)
  integer(int64) :: epochs(2)
  call get_command_argument(1,input); call get_command_argument(2,output)
  open(newunit=iu,file=trim(input),status='old',action='read',access='stream',form='unformatted')
  read(iu) nx,ny,nz,nc
  if(min(nx,ny,nz)<2.or.nc<1) error stop 'invalid prepared dimensions'
  allocate(p(nz),dp(nz),ps(nx,ny),dx(nx,ny),dy(nx,ny),u(nx,ny,nz),v(nx,ny,nz),w(nx,ny,nz), &
           labels(nx,ny,nz),p0(nx,ny),p1(nx,ny))
  read(iu) p,dp,ps,dx,dy,u,v,w,labels,p0,p1,epochs
  read(iu,iostat=ios) a
  if(ios>=0) error stop 'trailing prepared data'
  close(iu)
  allocate(op(nz),spacing(nz-1),h(nz-1),omegas(nz),valid(nz-1),partial(nx,ny),tendency(nx,ny), &
           mapping(nx,ny,6),sums(nx,ny,6),counts(nc,2),influence(nc,2))
  call legacy_pressure_geometry(p,op,spacing,status)
  if(status/=STATUS_OK) error stop 'invalid pressure geometry'
  mapping=0; sums=0; counts=0; influence=0
  do j=1,ny
    do i=1,nx
      call surface_layer(p,ps(i,j),q,partial(i,j),status)
      if(status/=STATUS_OK) error stop 'surface outside diagnostic pressure span'
      near=minloc(abs(op-ps(i,j)),dim=1)
      mapping(i,j,1)=q; mapping(i,j,2)=near
      call pressure_secant(p0(i,j),p1(i,j),epochs(1),epochs(2),.true.,tendency(i,j),status)
      if(status/=STATUS_OK) error stop 'invalid retrospective pressure secant'
      if(i<2.or.j<2) cycle
      h=0; valid=.false.; omegas=w(i,j,:)
      do k=2,nz
        if(labels(i,j,k)>0.and.mapping(i,j,3)==0) mapping(i,j,3)=k
        if(ps(i,j)<p(k)) cycle
        if(any([u(i,j-1,k-1),u(i-1,j-1,k-1),v(i-1,j,k-1),v(i-1,j-1,k-1), &
                w(i,j,k-1),w(i,j,k)]==sentinel)) cycle
        valid(k-1)=.true.
        h(k-1)=(u(i,j-1,k-1)-u(i-1,j-1,k-1))/dx(i,j) &
              +(v(i-1,j,k-1)-v(i-1,j-1,k-1))/dy(i,j)
        if(mapping(i,j,4)==0) mapping(i,j,4)=k
      end do
      mapping(i,j,5)=count(valid)
      do k=1,nz-1
        if(.not.valid(k)) cycle
        if(k==1) then
          mapping(i,j,6)=mapping(i,j,6)+1
        else if(.not.valid(k-1)) then
          mapping(i,j,6)=mapping(i,j,6)+1
        end if
      end do
      call column_telescope(h,omegas,dp(2:),valid,total,lateral,ends,error,bound,status)
      if(status/=STATUS_OK.or.abs(error)>bound) error stop 'legacy telescope failed'
      sums(i,j,:)=[total,lateral,ends,error,bound,real(count(valid),real64)]
      ! Two hypothetical existing-face families, not physical E_s:
      ! 1 nearest omega donor to ps; 2 upper donor of first above-ground level.
      do f=1,2
        face=near
        if(f==2) face=q
        c1=0; c2=0; a=0; b=0
        if(face>=2) then
          c1=labels(i,j,face)
          if(c1>0) a=-dx(i,j) ! z=h*dp cancels the row's dp.
        end if
        if(face<nz) then
          c2=labels(i,j,face+1)
          if(c2>0) b=dx(i,j)
        end if
        if(c1>0.and.c1==c2) then
          if(a+b/=0) error stop 'internal component face failed cancellation'
        else
          if(c1>0) then
            counts(c1,f)=counts(c1,f)+1; influence(c1,f)=influence(c1,f)+abs(a)
          end if
          if(c2>0) then
            counts(c2,f)=counts(c2,f)+1; influence(c2,f)=influence(c2,f)+abs(b)
          end if
        end if
      end do
    end do
  end do
  open(newunit=ou,file=trim(output),status='new',access='stream',form='unformatted')
  write(ou) op,spacing,mapping,partial,tendency,sums,counts,influence
  close(ou)
end program
