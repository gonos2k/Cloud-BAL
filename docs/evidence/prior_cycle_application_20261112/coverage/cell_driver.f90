! Diagnostic only: independent common producer call for each preselected cell.
program cell_driver
 use iso_fortran_env, only: int32,int64,real32,iostat_end
 use cloud_bal_state, only: cloud_bal_state_type,field3d,initialize_cloud_bal_state, &
   SOURCE_BACKGROUND_MODEL,MOMENT_BACKGROUND,STATUS_OK
 use cloud_bal_microphysics_initialization, only: ice_snow_partition,microphysics_completion_policy, &
   propose_ice_snow_from_background
 implicit none
 type(cloud_bal_state_type) :: state
 type(ice_snow_partition) :: bg,proposal
 type(microphysics_completion_policy) :: policy
 integer(int32) :: dims(3)
 integer(int64) :: t
 integer :: nx,ny,nz,i,j,k,s,loc(4),ios,uin,uout
 integer(int32), allocatable :: mask(:,:,:),result(:,:,:)
 real(real32), allocatable :: aqi(:,:,:),aqs(:,:,:),bqi(:,:,:),bqs(:,:,:),bni(:,:,:),den(:,:,:),oqi(:,:,:),oqs(:,:,:),oni(:,:,:)
 real(real32) :: cell_den(1,1,2)
 logical :: selected(1,1,2)
 character(64) :: grid
 character(256) :: source
 character(4096) :: input,output
 character :: tail
 if (command_argument_count()/=2) stop 2
 call get_command_argument(1,input);call get_command_argument(2,output)
 open(newunit=uin,file=trim(input),access='stream',form='unformatted',status='old',iostat=ios)
 if (ios/=0) stop 3
 read(uin,iostat=ios) dims,t,grid,source
 if (ios/=0 .or. any(dims<=0) .or. dims(3)<2) stop 4
 nx=dims(1);ny=dims(2);nz=dims(3)
 allocate(aqi(nx,ny,nz),aqs(nx,ny,nz),bqi(nx,ny,nz),bqs(nx,ny,nz),bni(nx,ny,nz),den(nx,ny,nz), &
 mask(nx,ny,nz),result(nx,ny,nz),oqi(nx,ny,nz),oqs(nx,ny,nz),oni(nx,ny,nz))
 read(uin,iostat=ios) aqi,aqs,bqi,bqs,bni,den,mask,policy%mass_threshold,policy%lower,policy%upper,policy%number_cap
 if (ios/=0) stop 5
 read(uin,iostat=ios) tail
 if (ios/=iostat_end) stop 6
 close(uin)
 if (any(mask/=0 .and. mask/=1)) stop 7
 call initialize_cloud_bal_state(state,1,1,2,t,grid,s)
 if (s/=STATUS_OK) stop 8
 bg%cloud_ice=state%cloud_ice; bg%snow=state%snow; bg%ice_number=state%cloud_ice
 bg%ice_number%unit='kg-1 dryair';bg%source=source;bg%provenance=MOMENT_BACKGROUND
 call activate(state%cloud_ice);call activate(state%snow)
 call activate(bg%cloud_ice);call activate(bg%snow);call activate(bg%ice_number)
 policy%source='explicit stream policy';policy%density_source='explicit stream native density'
 selected=.false.;selected(1,1,1)=.true.;result=-1;oqi=0;oqs=0;oni=0
 do k=1,nz
  do j=1,ny
   do i=1,nx
    if (mask(i,j,k)/=1) cycle
    state%cloud_ice%value=aqi(i,j,k);state%snow%value=aqs(i,j,k)
    bg%cloud_ice%value=bqi(i,j,k);bg%snow%value=bqs(i,j,k);bg%ice_number%value=bni(i,j,k)
    cell_den=den(i,j,k);loc=0
    call propose_ice_snow_from_background(state,bg,grid,selected,proposal,policy,cell_den,s,loc)
    result(i,j,k)=int(s,int32)
    if (s==STATUS_OK) then
     oqi(i,j,k)=proposal%cloud_ice%value(1,1,1)
     oqs(i,j,k)=proposal%snow%value(1,1,1)
     oni(i,j,k)=proposal%ice_number%value(1,1,1)
    end if
   end do
  end do
 end do
 open(newunit=uout,file=trim(output),access='stream',form='unformatted',status='new',iostat=ios)
 if (ios/=0) stop 9
 write(uout,iostat=ios) result,oqi,oqs,oni
 if (ios/=0) stop 10
 close(uout)
contains
 subroutine activate(field)
  type(field3d),intent(inout) :: field
  field%valid=.true.;field%quality=0;field%source=SOURCE_BACKGROUND_MODEL
 end subroutine
end program
