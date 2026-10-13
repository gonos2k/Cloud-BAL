MODULE pr83_off_candidate_wps_hook
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32,int64,real32,real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE netcdf
  USE cloud_bal_state, ONLY: cloud_bal_state_type,STATUS_OK,validate_canonical_state
  USE cloud_bal_wps_adapter, ONLY: pressure_wps_fields,map_pressure_candidate_to_wps
  USE setup
  USE laps_static
  USE lapsprep_wps, ONLY: output_ungrib_format
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: write_pr83_off_candidate_wps
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64
CONTAINS
  SUBROUTINE write_pr83_off_candidate_wps(background,candidate,output_path,witness_path,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    CHARACTER(LEN=*), INTENT(IN) :: output_path,witness_path
    INTEGER, INTENT(OUT) :: status
    TYPE(pressure_wps_fields) :: host,mapped
    REAL(real32), ALLOCATABLE :: writer_p(:)
    INTEGER :: nx,ny,nz,code,reason,writer_status,canonical_status,capture_unit,capture_nx,capture_ny,capture_nz,witness_unit
    CHARACTER(LEN=1024) :: root,inventory_path

    status=1; nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
    IF (candidate%pressure%valid_time/=background%pressure%valid_time .OR. &
        candidate%grid%grid_id/=background%grid%grid_id) RETURN
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
    IF (ANY(host%psfc/=background%surface_pressure%value)) RETURN
    IF (ANY(host%qv(:,:,nz+1)/=background%surface_vapor%value)) RETURN
    host%valid_time=background%pressure%valid_time; host%grid_id=background%grid%grid_id
    host%wind_coordinate='GRID_RELATIVE'
    PRINT *, 'PR82 host finite t/ht/u/v/rh/qv/qc/qi/qr/qs/qg=', &
      ALL(ieee_is_finite(host%t)),ALL(ieee_is_finite(host%ht)), &
      ALL(ieee_is_finite(host%u)),ALL(ieee_is_finite(host%v)), &
      ALL(ieee_is_finite(host%rh)),ALL(ieee_is_finite(host%qv)), &
      ALL(ieee_is_finite(host%qc)),ALL(ieee_is_finite(host%qi)), &
      ALL(ieee_is_finite(host%qr)),ALL(ieee_is_finite(host%qs)),ALL(ieee_is_finite(host%qg))
    PRINT *, 'PR82 host finite psfc/slp/skin/snow=',ALL(ieee_is_finite(host%psfc)), &
      ALL(ieee_is_finite(host%slp)),ALL(ieee_is_finite(host%skin_temperature)), &
      ALL(ieee_is_finite(host%snow_cover))
    CALL validate_canonical_state(candidate,.FALSE.,.TRUE.,canonical_status,reason,.TRUE.)
    PRINT *, 'PR82 candidate validation status/reason=',canonical_status,reason
    PRINT *, 'PR82 candidate time/grid=',candidate%pressure%valid_time,TRIM(candidate%grid%grid_id)
    PRINT *, 'PR82 host pressure levels hPa=',host%p(1:nz)
    PRINT *, 'PR82 candidate pressure endpoints Pa=',candidate%pressure%value(1,1,1), &
      candidate%pressure%value(1,1,nz)
    PRINT *, 'PR82 host pressure marker=',host%p(nz+1)
    PRINT *, 'PR82 candidate valid count P/T/qv=',COUNT(candidate%pressure%valid), &
      COUNT(candidate%temperature%valid),COUNT(candidate%vapor%valid)
    CALL map_pressure_candidate_to_wps(candidate,host,mapped,code,'GRID_RELATIVE')
    IF (code/=STATUS_OK) THEN
      PRINT *, 'PR82 candidate-to-WPS mapper status=',code
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
      mapped%snow_cover,mapped%skin_temperature,writer_status,TRIM(output_path), &
      vapor_mixing_ratio=mapped%qv,include_hydrometeors=.TRUE.,include_surface_height=.TRUE., &
      create_new=.TRUE.,valid_second=0)
    IF (writer_status/=1) RETURN
    status=STATUS_OK
  END SUBROUTINE write_pr83_off_candidate_wps

END MODULE pr83_off_candidate_wps_hook
