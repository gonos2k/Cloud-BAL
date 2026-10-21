MODULE pr94_hydro_wps_hook
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32,real32,real64
  USE netcdf
  USE cloud_bal_state, ONLY: cloud_bal_state_type,STATUS_OK,validate_canonical_state
  USE cloud_bal_wps_adapter, ONLY: pressure_wps_fields,map_pressure_candidate_to_wps
  USE setup
  USE laps_static
  USE lapsprep_wps, ONLY: output_ungrib_format
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: write_pr94_hydro_wps
CONTAINS
  SUBROUTINE write_pr94_hydro_wps(candidate_path,background,wps_path,witness_path,status)
    CHARACTER(LEN=*), INTENT(IN) :: candidate_path,wps_path,witness_path
    TYPE(cloud_bal_state_type), INTENT(IN) :: background
    INTEGER, INTENT(OUT) :: status
    TYPE(cloud_bal_state_type) :: candidate
    TYPE(pressure_wps_fields) :: host,mapped
    REAL(real32), ALLOCATABLE :: writer_p(:)
    INTEGER :: ncid,code,reason,nx,ny,nz,capture_unit,capture_nx,capture_ny,capture_nz,witness_unit,writer_status
    CHARACTER(LEN=1024) :: root,inventory_path

    status=1
    code=nf90_open(TRIM(candidate_path),NF90_NOWRITE,ncid)
    IF (code/=NF90_NOERR) RETURN
    status=NF90_NOERR
    candidate=background
    CALL load3d(ncid,'candidate_temperature', &
      candidate%temperature%value,candidate%temperature%valid,background%temperature%valid,code)
    CALL load3d(ncid,'candidate_vapor', &
      candidate%vapor%value,candidate%vapor%valid,background%vapor%valid,code)
    CALL load3d(ncid,'candidate_cloud_water', &
      candidate%cloud_water%value,candidate%cloud_water%valid,background%cloud_water%valid,code)
    CALL load3d(ncid,'candidate_cloud_ice', &
      candidate%cloud_ice%value,candidate%cloud_ice%valid,background%cloud_ice%valid,code)
    CALL load3d(ncid,'candidate_rain', &
      candidate%rain%value,candidate%rain%valid,background%rain%valid,code)
    CALL load3d(ncid,'candidate_snow', &
      candidate%snow%value,candidate%snow%valid,background%snow%valid,code)
    CALL load3d(ncid,'candidate_graupel', &
      candidate%graupel%value,candidate%graupel%valid,background%graupel%valid,code)
    CALL load3d(ncid,'candidate_geopotential', &
      candidate%geopotential%value,candidate%geopotential%valid,background%geopotential%valid,code)
    CALL load3d_raw(ncid,'pressure_mass_measure',candidate%grid%pressure_mass_measure,code)
    CALL load3d_raw(ncid,'candidate_dry_air_mass_measure',candidate%grid%dry_air_mass_measure,code)
    CALL load2d(ncid,'candidate_surface_pressure', &
      candidate%surface_pressure%value,candidate%surface_pressure%valid,background%surface_pressure%valid,code)
    CALL load2d(ncid,'candidate_surface_temperature', &
      candidate%surface_temperature%value,candidate%surface_temperature%valid, &
      background%surface_temperature%valid,code)
    CALL load2d(ncid,'candidate_surface_vapor', &
      candidate%surface_vapor%value,candidate%surface_vapor%valid,background%surface_vapor%valid,code)
    CALL load2d(ncid,'candidate_surface_height', &
      candidate%surface_height%value,candidate%surface_height%valid,background%surface_height%valid,code)
    code=nf90_close(ncid)
    IF (code/=NF90_NOERR) RETURN
    CALL validate_canonical_state(candidate,.FALSE.,.TRUE.,code,reason,.TRUE.)
    IF (code/=STATUS_OK) THEN
      WRITE(*,'(A,I0,A,I0)') 'candidate_validation_status=',code,' reason=',reason
      RETURN
    END IF
    nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
    CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_PR82_LAPS_ROOT',root,STATUS=code)
    IF (code/=0 .OR. LEN_TRIM(root)==0) RETURN
    CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_PR82_INVENTORY',inventory_path,STATUS=code)
    IF (code/=0 .OR. LEN_TRIM(inventory_path)==0) RETURN
    CALL get_horiz_grid_spec(TRIM(root))
    IF (x/=nx .OR. y/=ny) RETURN
    z3=nz; wind_coordinate='GRID_RELATIVE'; hotstart=.FALSE.; balance=.FALSE.
    make_sfc_uv=.FALSE.; wps_output_vapor=.TRUE.; lwc2vapor_thresh=0.0
    valid_yyyy=2026; valid_jjj=228; valid_hh=13; valid_min=0
    ALLOCATE(host%p(nz+1),host%t(nx,ny,nz+1),host%ht(nx,ny,nz+1), &
      host%u(nx,ny,nz+1),host%v(nx,ny,nz+1),host%rh(nx,ny,nz+1), &
      host%qv(nx,ny,nz+1),host%qc(nx,ny,nz),host%qi(nx,ny,nz), &
      host%qr(nx,ny,nz),host%qs(nx,ny,nz),host%qg(nx,ny,nz), &
      host%psfc(nx,ny),host%slp(nx,ny),host%skin_temperature(nx,ny),host%snow_cover(nx,ny))
    OPEN(NEWUNIT=capture_unit,FILE=TRIM(inventory_path),STATUS='OLD',FORM='UNFORMATTED', &
      ACCESS='SEQUENTIAL',ACTION='READ',CONVERT='BIG_ENDIAN',IOSTAT=code)
    IF (code/=0) RETURN
    READ(capture_unit,IOSTAT=code) capture_nx,capture_ny,capture_nz
    IF (code==0 .AND. ANY([capture_nx,capture_ny,capture_nz]/=[nx,ny,nz])) code=1
    IF (code==0) READ(capture_unit,IOSTAT=code) host%p,host%t,host%ht,host%u,host%v,host%rh, &
      host%qv,host%qc,host%qr,host%qs,host%qi,host%qg,host%psfc,host%slp, &
      host%skin_temperature,host%snow_cover
    CLOSE(capture_unit)
    IF (code/=0) RETURN
    IF (ANY(host%psfc/=background%surface_pressure%value) .OR. &
        ANY(host%qv(:,:,nz+1)/=background%surface_vapor%value)) RETURN
    host%valid_time=background%pressure%valid_time; host%grid_id=background%grid%grid_id
    host%wind_coordinate='GRID_RELATIVE'
    CALL map_pressure_candidate_to_wps(candidate,host,mapped,code,'GRID_RELATIVE')
    IF (code/=STATUS_OK) THEN
      WRITE(*,'(A,I0)') 'candidate_wps_mapping_status=',code
      RETURN
    END IF
    OPEN(NEWUNIT=witness_unit,FILE=TRIM(witness_path),STATUS='NEW',FORM='UNFORMATTED', &
      ACCESS='SEQUENTIAL',ACTION='WRITE',CONVERT='BIG_ENDIAN',IOSTAT=code)
    IF (code/=0) RETURN
    WRITE(witness_unit,IOSTAT=code) nx,ny,nz
    IF (code==0) WRITE(witness_unit,IOSTAT=code) mapped%p,mapped%t,mapped%ht,mapped%u,mapped%v, &
      mapped%rh,mapped%qv,mapped%qc,mapped%qi,mapped%qr,mapped%qs,mapped%qg, &
      mapped%psfc,mapped%slp,mapped%skin_temperature,mapped%snow_cover
    CLOSE(witness_unit)
    IF (code/=0) RETURN
    ALLOCATE(writer_p(nz+1)); writer_p=mapped%p
    CALL output_ungrib_format(writer_p,mapped%t,mapped%ht,mapped%u,mapped%v,mapped%rh, &
      mapped%slp,mapped%psfc,mapped%qc,mapped%qr,mapped%qs,mapped%qi,mapped%qg, &
      mapped%snow_cover,mapped%skin_temperature,writer_status,TRIM(wps_path), &
      vapor_mixing_ratio=mapped%qv,include_hydrometeors=.TRUE.,include_surface_height=.TRUE., &
      create_new=.TRUE.,valid_second=0)
    IF (writer_status/=1) RETURN
    status=STATUS_OK
  END SUBROUTINE write_pr94_hydro_wps

  SUBROUTINE load3d_raw(ncid,value_name,value,status)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: value_name
    REAL(real64), INTENT(INOUT) :: value(:,:,:)
    INTEGER, INTENT(INOUT) :: status
    INTEGER :: value_id,code
    IF (status/=NF90_NOERR) RETURN
    code=nf90_inq_varid(ncid,TRIM(value_name),value_id)
    IF (code==NF90_NOERR) code=nf90_get_var(ncid,value_id,value)
    IF (code/=NF90_NOERR) status=code
  END SUBROUTINE load3d_raw

  SUBROUTINE load3d(ncid,value_name,value,valid,expected_valid,status)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: value_name
    REAL(real32), INTENT(INOUT) :: value(:,:,:)
    LOGICAL, INTENT(INOUT) :: valid(:,:,:)
    LOGICAL, INTENT(IN) :: expected_valid(:,:,:)
    INTEGER, INTENT(INOUT) :: status
    REAL(real32), ALLOCATABLE :: input(:,:,:)
    INTEGER :: value_id,code
    IF (status/=NF90_NOERR) RETURN
    ALLOCATE(input(SIZE(value,1),SIZE(value,2),SIZE(value,3)))
    code=nf90_inq_varid(ncid,TRIM(value_name),value_id)
    IF (code==NF90_NOERR) code=nf90_get_var(ncid,value_id,input)
    IF (code/=NF90_NOERR) THEN
      status=code
      RETURN
    END IF
    WHERE(expected_valid) value=input
  END SUBROUTINE load3d

  SUBROUTINE load2d(ncid,value_name,value,valid,expected_valid,status)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: value_name
    REAL(real32), INTENT(INOUT) :: value(:,:)
    LOGICAL, INTENT(INOUT) :: valid(:,:)
    LOGICAL, INTENT(IN) :: expected_valid(:,:)
    INTEGER, INTENT(INOUT) :: status
    REAL(real32), ALLOCATABLE :: input(:,:)
    INTEGER :: value_id,code
    IF (status/=NF90_NOERR) RETURN
    ALLOCATE(input(SIZE(value,1),SIZE(value,2)))
    code=nf90_inq_varid(ncid,TRIM(value_name),value_id)
    IF (code==NF90_NOERR) code=nf90_get_var(ncid,value_id,input)
    IF (code/=NF90_NOERR) THEN
      status=code
      RETURN
    END IF
    WHERE(expected_valid) value=input
  END SUBROUTINE load2d
END MODULE pr94_hydro_wps_hook
