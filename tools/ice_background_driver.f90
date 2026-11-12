! Binary stream adapter for the common ice/snow background proposal.
! Arrays are float32 or int32 in Fortran (x,y,z) order.
PROGRAM ice_background_driver
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32,int64,real32,iostat_end
  USE cloud_bal_state, ONLY: cloud_bal_state_type,field3d,initialize_cloud_bal_state, &
    SOURCE_BACKGROUND_MODEL,MOMENT_BACKGROUND,STATUS_OK
  USE cloud_bal_microphysics_initialization, ONLY: ice_snow_partition, &
    microphysics_completion_policy,propose_ice_snow_from_background
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: state
  TYPE(ice_snow_partition) :: background,proposal
  TYPE(microphysics_completion_policy) :: policy
  INTEGER(int32) :: dims(3),status32,location32(4)
  INTEGER(int64) :: valid_time
  INTEGER :: nx,ny,nz,status,location(4),ios,unit_in,unit_out
  INTEGER(int32), ALLOCATABLE :: mask(:,:,:)
  REAL(real32), ALLOCATABLE :: density(:,:,:)
  LOGICAL, ALLOCATABLE :: selected(:,:,:)
  CHARACTER(64) :: grid_id
  CHARACTER(256) :: background_source
  CHARACTER(4096) :: input_path,output_path
  CHARACTER :: trailing_byte

  IF (command_argument_count()/=2) STOP 2
  CALL get_command_argument(1,input_path)
  CALL get_command_argument(2,output_path)
  OPEN(newunit=unit_in,file=TRIM(input_path),access='stream',form='unformatted',status='old',iostat=ios)
  IF (ios/=0) STOP 3
  READ(unit_in,iostat=ios) dims,valid_time,grid_id,background_source
  IF (ios/=0) STOP 4
  IF (ANY(dims<=0) .OR. dims(3)<2) STOP 4
  nx=dims(1); ny=dims(2); nz=dims(3)
  CALL initialize_cloud_bal_state(state,nx,ny,nz,valid_time,grid_id,status)
  IF (status/=STATUS_OK) STOP 5
  ALLOCATE(mask(nx,ny,nz),selected(nx,ny,nz),density(nx,ny,nz))
  background%cloud_ice=state%cloud_ice
  background%snow=state%snow
  background%ice_number=state%cloud_ice
  background%ice_number%unit='kg-1 dryair'
  background%source=background_source
  background%provenance=MOMENT_BACKGROUND
  READ(unit_in,iostat=ios) state%cloud_ice%value,state%snow%value, &
    background%cloud_ice%value,background%snow%value,background%ice_number%value,density,mask, &
    policy%mass_threshold,policy%lower,policy%upper,policy%number_cap
  IF (ios/=0) STOP 6
  READ(unit_in,iostat=ios) trailing_byte
  IF (ios/=iostat_end) STOP 7
  CLOSE(unit_in)
  IF (ANY(mask/=0 .AND. mask/=1)) STOP 8
  selected=mask==1
  CALL activate(state%cloud_ice)
  CALL activate(state%snow)
  CALL activate(background%cloud_ice)
  CALL activate(background%snow)
  CALL activate(background%ice_number)
  policy%source='explicit stream policy'
  policy%density_source='explicit stream native density'
  location=0
  CALL propose_ice_snow_from_background(state,background,grid_id,selected,proposal,policy,density,status,location)
  status32=INT(status,int32)
  location32=INT(location,int32)
  OPEN(newunit=unit_out,file=TRIM(output_path),access='stream',form='unformatted',status='new',iostat=ios)
  IF (ios/=0) STOP 9
  WRITE(unit_out,iostat=ios) status32,location32
  IF (ios/=0) STOP 10
  IF (status==STATUS_OK) THEN
    WRITE(unit_out,iostat=ios) proposal%cloud_ice%value,proposal%snow%value,proposal%ice_number%value
    IF (ios/=0) STOP 11
  END IF
  CLOSE(unit_out,iostat=ios)
  IF (ios/=0) STOP 12
CONTAINS
  SUBROUTINE activate(field)
    TYPE(field3d), INTENT(INOUT) :: field
    field%valid=.TRUE.
    field%quality=0
    field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE activate
END PROGRAM ice_background_driver
