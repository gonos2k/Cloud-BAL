PROGRAM pr67_prepare_model_target_masks
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,int32,int64
  USE netcdf
  USE cloud_bal_state, ONLY: cloud_bal_state_type,STATUS_OK,model_target_level_is_interior
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: state,masked_state
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  INTEGER(int32), ALLOCATABLE :: target_mask(:,:,:),coverage_mask(:,:,:),level(:,:,:)
  LOGICAL, ALLOCATABLE :: target(:,:,:),coverage(:,:,:)
  INTEGER(int64) :: valid_time,target_before,coverage_before,target_after,coverage_after
  INTEGER :: input_status,input_reason,ncid,target_var,coverage_var,nx,ny,nz,k,i,j
  INTEGER :: rc,unit,removed_targets
  CHARACTER(LEN=2048) :: fua,fsf,lw3,vrz,vrt,static_path,time_text,target_path,mask_path

  IF (COMMAND_ARGUMENT_COUNT()/=9) ERROR STOP &
    'usage: pr67-prepare-masks FUA FSF LW3 VRZ VRT STATIC VALID_TIME TARGET MASK_OUTPUT'
  CALL GET_COMMAND_ARGUMENT(1,fua); CALL GET_COMMAND_ARGUMENT(2,fsf)
  CALL GET_COMMAND_ARGUMENT(3,lw3); CALL GET_COMMAND_ARGUMENT(4,vrz)
  CALL GET_COMMAND_ARGUMENT(5,vrt); CALL GET_COMMAND_ARGUMENT(6,static_path)
  CALL GET_COMMAND_ARGUMENT(7,time_text); CALL GET_COMMAND_ARGUMENT(8,target_path)
  CALL GET_COMMAND_ARGUMENT(9,mask_path)
  READ(time_text,*) valid_time
  CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
    TRIM(static_path),valid_time,state,longitude,input_status,input_reason)
  IF (input_status/=STATUS_OK) ERROR STOP 'retained 13 UTC real input reader failed'
  nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
  ALLOCATE(target_mask(nx,ny,nz),coverage_mask(nx,ny,nz),level(nx,ny,1), &
    target(nx,ny,nz),coverage(nx,ny,nz))
  rc=nf90_open(TRIM(target_path),NF90_NOWRITE,ncid)
  IF (rc/=NF90_NOERR) ERROR STOP 'could not open paired model target'
  rc=nf90_inq_varid(ncid,'target_mask',target_var)
  IF (rc/=NF90_NOERR) ERROR STOP 'paired target mask is missing'
  rc=nf90_inq_varid(ncid,'coverage_mask',coverage_var)
  IF (rc/=NF90_NOERR) ERROR STOP 'paired coverage mask is missing'
  DO k=1,nz
    rc=nf90_get_var(ncid,target_var,level,start=[1,1,k],count=[nx,ny,1])
    IF (rc/=NF90_NOERR) ERROR STOP 'could not read target mask level'
    target_mask(:,:,k)=level(:,:,1)
    rc=nf90_get_var(ncid,coverage_var,level,start=[1,1,k],count=[nx,ny,1])
    IF (rc/=NF90_NOERR) ERROR STOP 'could not read coverage mask level'
    coverage_mask(:,:,k)=level(:,:,1)
  END DO
  rc=nf90_close(ncid)
  IF (rc/=NF90_NOERR) ERROR STOP 'could not close paired model target'
  IF (ANY((target_mask/=0_int32) .AND. (target_mask/=1_int32)) .OR. &
      ANY((coverage_mask/=0_int32) .AND. (coverage_mask/=1_int32))) &
    ERROR STOP 'paired model masks are not binary'
  target=target_mask==1_int32; coverage=coverage_mask==1_int32
  target_before=COUNT(target,KIND=int64); coverage_before=COUNT(coverage,KIND=int64)

  ! Restrict paired coverage to this exact reader's atmospheric support.
  coverage=coverage .AND. state%above_ground
  masked_state=state
  masked_state%model_target_coverage=coverage
  removed_targets=0
  DO k=1,nz; DO j=1,ny; DO i=1,nx
    IF (.NOT.target(i,j,k)) CYCLE
    IF (.NOT.model_target_level_is_interior(masked_state,i,j,k)) THEN
      target(i,j,k)=.FALSE.
      removed_targets=removed_targets+1
    END IF
  END DO; END DO; END DO
  target_mask=MERGE(1_int32,0_int32,target)
  coverage_mask=MERGE(1_int32,0_int32,coverage)
  target_after=COUNT(target,KIND=int64); coverage_after=COUNT(coverage,KIND=int64)
  IF (target_before/=892339_int64 .OR. coverage_before/=1150135_int64) &
    ERROR STOP 'source target masks differ from the retained artifact'
  IF (target_before-target_after/=1_int64 .OR. coverage_before-coverage_after/=1_int64 .OR. &
      removed_targets/=1) ERROR STOP 'support filtering changed more than the measured unsupported cells'

  OPEN(NEWUNIT=unit,FILE=TRIM(mask_path),ACCESS='STREAM',FORM='UNFORMATTED',STATUS='REPLACE')
  WRITE(unit) target_mask
  WRITE(unit) coverage_mask
  CLOSE(unit)
  PRINT '(A,I0)', 'source_model_target_cells=',target_before
  PRINT '(A,I0)', 'source_model_coverage_cells=',coverage_before
  PRINT '(A,I0)', 'removed_unsupported_model_target_cells=',removed_targets
  PRINT '(A,I0)', 'derived_model_target_cells=',target_after
  PRINT '(A,I0)', 'derived_model_coverage_cells=',coverage_after
  PRINT '(A)', 'support_derivation=original masks intersected with actual 13Z reader above_ground '// &
    'and existing model_target_level_is_interior'
END PROGRAM pr67_prepare_model_target_masks
