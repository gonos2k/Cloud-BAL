! Stream adapter for the common moment kernel. All arrays are x,y,z in
! Fortran order; five-field arrays append the moment slot as the last axis.
PROGRAM model_moment_driver
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32,int64,real32,real64
  USE cloud_bal_state, ONLY: cloud_bal_state_type, field3d, moment_bundle, &
    initialize_cloud_bal_state, SOURCE_BACKGROUND_MODEL, SOURCE_OUTPUT_ADAPTER, STATUS_OK
  USE cloud_bal_microphysics_initialization, ONLY: microphysics_completion_policy, complete_initialization_state, &
    ice_snow_partition, complete_ice_snow_initialization
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: state, output
  TYPE(moment_bundle) :: background,prior,observed
  TYPE(microphysics_completion_policy) :: policy
  TYPE(ice_snow_partition) :: partition
  INTEGER(int32) :: dims(3), status32, use_theta_m, failed_location(4)
  INTEGER :: nx,ny,nz,status,ios,unit_in,unit_out
  INTEGER :: failure_reason
  REAL(real64) :: feasible_interval(2)
  INTEGER(int32), ALLOCATABLE :: valid(:,:,:,:)
  REAL(real32), ALLOCATABLE :: density(:,:,:), pb(:,:,:), theta(:,:,:)
  CHARACTER(4096) :: input_path, output_path, partition_path
  LOGICAL :: has_partition
  INTEGER(int32) :: partition_dims(3)
  INTEGER(int32), ALLOCATABLE :: partition_mask(:,:,:)

  IF (command_argument_count()/=2 .AND. command_argument_count()/=3) STOP 2
  has_partition=command_argument_count()==3
  CALL get_command_argument(1,input_path)
  CALL get_command_argument(2,output_path)
  OPEN(newunit=unit_in,file=TRIM(input_path),access='stream',form='unformatted',status='old',iostat=ios)
  IF (ios/=0) STOP 3
  READ(unit_in,iostat=ios) dims
  IF (ios/=0 .OR. ANY(dims<=0) .OR. dims(3)<2) STOP 4
  nx=dims(1); ny=dims(2); nz=dims(3)
  CALL initialize_cloud_bal_state(state,nx,ny,nz,0_int64,'native',status)
  IF (status/=STATUS_OK) STOP 5
  ALLOCATE(density(nx,ny,nz),pb(nx,ny,nz),theta(nx,ny,nz),valid(nx,ny,nz,5))
  CALL setup_bundle(background); CALL setup_bundle(prior); CALL setup_bundle(observed)
  READ(unit_in,iostat=ios) state%cloud_water%value,state%cloud_ice%value, &
    state%rain%value,state%graupel%value,state%snow%value,density, &
    state%pressure%value,pb,theta,state%vapor%value,use_theta_m
  IF (ios/=0) STOP 6
  CALL activate(state%cloud_water); CALL activate(state%cloud_ice)
  CALL activate(state%rain); CALL activate(state%graupel); CALL activate(state%snow)
  IF (use_theta_m/=0 .AND. use_theta_m/=1) STOP 11
  state%pressure%value=state%pressure%value+pb
  theta=theta+300.0_real32
  ! NetCDF T is perturbation dry potential temperature for both settings.
  state%temperature%value=theta*(state%pressure%value/100000.0_real32)**(287.0_real32/1004.5_real32)
  CALL activate(state%pressure); CALL activate(state%temperature); CALL activate(state%vapor)
  CALL read_bundle(background); CALL read_bundle(prior); CALL read_bundle(observed)
  READ(unit_in,iostat=ios) policy%mass_threshold,policy%lower,policy%upper,policy%number_cap
  IF (ios/=0) STOP 7
  CLOSE(unit_in)
  policy%source='caller-declared source-bound policy'
  policy%density_source='caller-provided file-state proxy'
  state%moments=background
  IF (has_partition) THEN
    CALL get_command_argument(3,partition_path)
    OPEN(newunit=unit_in,file=TRIM(partition_path),access='stream',form='unformatted',status='old',iostat=ios)
    IF (ios/=0) STOP 12
    partition%cloud_ice=state%cloud_ice
    partition%snow=state%snow
    partition%ice_number=state%cloud_ice
    partition%ice_number%unit='kg-1 dryair'
    ALLOCATE(partition_mask(nx,ny,nz))
    READ(unit_in,iostat=ios) partition_dims
    IF (ios/=0) STOP 13
    IF (ANY(partition_dims/=dims)) STOP 13
    READ(unit_in,iostat=ios) partition%cloud_ice%value,partition%snow%value, &
      partition%ice_number%value,partition_mask,partition%provenance,partition%source
    IF (ios/=0) STOP 14
    CLOSE(unit_in)
    IF (ANY(partition_mask<0) .OR. ANY(partition_mask>1)) STOP 15
    CALL activate(partition%cloud_ice); CALL activate(partition%snow); CALL activate(partition%ice_number)
    partition%cloud_ice%valid=partition_mask==1
    partition%snow%valid=partition_mask==1
    partition%ice_number%valid=partition_mask==1
    partition%cloud_ice%source=SOURCE_OUTPUT_ADAPTER
    partition%snow%source=SOURCE_OUTPUT_ADAPTER
    partition%ice_number%source=SOURCE_OUTPUT_ADAPTER
    CALL complete_ice_snow_initialization(state,output,partition,prior,policy,status,density, &
      failed_location=failed_location,failure_reason=failure_reason,feasible_interval=feasible_interval,observed=observed)
  ELSE
    CALL complete_initialization_state(state,output,prior,policy,status,density,observed,failed_location, &
      failure_reason=failure_reason,feasible_interval=feasible_interval)
  END IF
  IF (status==STATUS_OK) background=output%moments
  OPEN(newunit=unit_out,file=TRIM(output_path),access='stream',form='unformatted',status='new',iostat=ios)
  IF (ios/=0) STOP 8
  status32=status
  valid=MERGE(1_int32,0_int32,background%valid)
  WRITE(unit_out,iostat=ios) status32,failed_location,background%value,valid,background%provenance, &
    MINVAL(state%temperature%value),MAXVAL(state%temperature%value),INT(failure_reason,int32),feasible_interval
  IF (ios/=0) STOP 9
  IF (has_partition) THEN
    IF (status==STATUS_OK) THEN
      WRITE(unit_out,iostat=ios) output%cloud_ice%value,output%snow%value
    ELSE
      WRITE(unit_out,iostat=ios) state%cloud_ice%value,state%snow%value
    END IF
    IF (ios/=0) STOP 16
  END IF
  CLOSE(unit_out)
CONTAINS
  SUBROUTINE setup_bundle(bundle)
    TYPE(moment_bundle), INTENT(INOUT) :: bundle
    ALLOCATE(bundle%value(nx,ny,nz,5),bundle%valid(nx,ny,nz,5),bundle%provenance(nx,ny,nz,5))
  END SUBROUTINE
  SUBROUTINE read_bundle(bundle)
    TYPE(moment_bundle), INTENT(INOUT) :: bundle
    READ(unit_in,iostat=ios) bundle%value,valid,bundle%provenance
    IF (ios/=0 .OR. ANY(valid<0) .OR. ANY(valid>1)) STOP 10
    bundle%valid=valid==1
  END SUBROUTINE
  SUBROUTINE activate(field)
    TYPE(field3d), INTENT(INOUT) :: field
    field%valid=.TRUE.; field%quality=0; field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE
END PROGRAM model_moment_driver
