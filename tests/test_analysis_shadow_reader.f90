PROGRAM test_analysis_shadow_reader
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE netcdf
  USE cloud_bal_state
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state
  IMPLICIT NONE
  INTEGER, PARAMETER :: NX=235,NY=283,NZ=22
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64,RD_AIR=287.05_real64,EPS=0.622_real64
  REAL(real64), PARAMETER :: TOL_FACTOR=8.0_real64*REAL(EPSILON(1.0_real32),real64)
  TYPE(cloud_bal_state_type) :: state,rejected
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  REAL(real32) :: t_raw(NX,NY,NZ),ht_raw(NX,NY,NZ),q_raw(NX,NY,NZ)
  REAL(real32) :: lwc_raw(NX,NY,NZ),ice_raw(NX,NY,NZ),rai_raw(NX,NY,NZ)
  REAL(real32) :: sno_raw(NX,NY,NZ),pic_raw(NX,NY,NZ),surface_t(NX,NY),surface_p(NX,NY)
  REAL(real64) :: levels(NZ)
  REAL(real32) :: surface_mr(NX,NY),terrain(NX,NY)
  CHARACTER(LEN=1024) :: root,fua,fsf,valid_fua,valid_fsf,lw3,vrz,vrt,static_file
  CHARACTER(LEN=1024) :: lt1,lq3,lwc,lsx,missing_lq3
  CHARACTER(LEN=64) :: mode,payload_kind
  INTEGER(int64), PARAMETER :: VALID_TIME=1786881600_int64
  INTEGER :: status,reason

  IF (COMMAND_ARGUMENT_COUNT()<1 .OR. COMMAND_ARGUMENT_COUNT()>3) ERROR STOP &
    'usage: test_analysis_shadow_reader RUNTIME_ROOT [REJECT_TIME|REJECT_PAYLOAD|OPTIONAL_MR|INACTIVE_HT] [LWC|LSX_PS|LT1_HT]'
  CALL GET_COMMAND_ARGUMENT(1,root)
  mode=''
  IF (COMMAND_ARGUMENT_COUNT()==2) CALL GET_COMMAND_ARGUMENT(2,mode)
  payload_kind=''
  IF (COMMAND_ARGUMENT_COUNT()==3) THEN
    CALL GET_COMMAND_ARGUMENT(2,mode)
    CALL GET_COMMAND_ARGUMENT(3,payload_kind)
  END IF
  fua=TRIM(root)//'/missing.fua'; fsf=TRIM(root)//'/missing.fsf'
  valid_fua=TRIM(root)//'/lapsprd/fua/wrf/2622806000600.fua'
  valid_fsf=TRIM(root)//'/lapsprd/fsf/wrf/2622806000600.fsf'
  lw3=TRIM(root)//'/lapsprd/lw3/262281200.lw3'
  vrz=TRIM(root)//'/lapsprd/vrz/262281200.vrz'
  vrt=TRIM(root)//'/lapsprd/vrt/262281200.vrt'
  static_file=TRIM(root)//'/static/static.nest7grid'
  lt1=TRIM(root)//'/lapsprd/lt1/262281200.lt1'
  lq3=TRIM(root)//'/lapsprd/lq3/262281200.lq3'
  lwc=TRIM(root)//'/lapsprd/lwc/262281200.lwc'
  lsx=TRIM(root)//'/lapsprd/lsx/262281200.lsx'
  missing_lq3=TRIM(root)//'/lapsprd/lq3/not-the-analysis-file.lq3'

  CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
      TRIM(static_file),VALID_TIME,state,longitude,status,reason, &
      lt1_path=TRIM(lt1),lq3_path=TRIM(lq3),lwc_path=TRIM(lwc),lsx_path=TRIM(lsx))
  IF (TRIM(mode)=='REJECT_TIME') THEN
    IF (status==STATUS_OK) ERROR STOP 'direct reader accepted a mismatched analysis reference'
    WRITE(*,'(A,I0,A,I0)') 'direct analysis time rejected status=',status, &
      ' reason=',reason
    STOP
  END IF
  IF (TRIM(mode)=='REJECT_PAYLOAD') THEN
    IF (status==STATUS_OK) ERROR STOP 'direct reader accepted a nonfinite active payload'
    SELECT CASE (TRIM(payload_kind))
    CASE ('LWC')
      ! The hydrometeor assignment path currently reports this early raw
      ! payload failure with its initialized metadata reason.
      IF (reason/=REASON_METADATA) ERROR STOP 'LWC payload returned the wrong rejection reason'
    CASE ('LSX_PS')
      IF (reason/=REASON_REQUIRED_COVERAGE) ERROR STOP &
        'LSX PS payload returned the wrong rejection reason'
    CASE ('LT1_HT')
      IF (status/=STATUS_FAILED .OR. reason/=REASON_REQUIRED_COVERAGE) ERROR STOP &
        'active LT1 HT payload returned the wrong rejection status/reason'
      CALL read3(lt1,'ht',ht_raw)
      CALL read_levels(lw3,levels)
      CALL read2(lsx,'ps',surface_p)
      CALL check_extreme_ht(state,ht_raw,levels,surface_p,.TRUE.)
    CASE DEFAULT
      ERROR STOP 'invalid payload rejection kind'
    END SELECT
    WRITE(*,'(A,A,A,I0,A,I0)') 'direct analysis payload rejected kind=',TRIM(payload_kind), &
      ' status=',status,' reason=',reason
    STOP
  END IF
  IF (status/=STATUS_OK .OR. reason/=REASON_NONE) THEN
    WRITE(*,'(A,I0,A,I0)') 'direct_analysis_status=',status,',reason=',reason
    ERROR STOP 'direct analysis reader rejected case'
  END IF

  IF (TRIM(mode)=='OPTIONAL_MR') THEN
    IF (ANY(state%surface_vapor%valid)) ERROR STOP 'missing MR fabricated valid surface vapor'
    IF (ANY(state%surface_vapor%source/=0_int32)) ERROR STOP 'missing MR fabricated provenance'
    WRITE(*,'(A)') 'direct optional MR absent: STATUS_OK, no valid surface vapor'
    STOP
  END IF

  CALL read3(lt1,'t3',t_raw); CALL read3(lt1,'ht',ht_raw); CALL read3(lq3,'sh',q_raw)
  CALL read_levels(lw3,levels)
  CALL read3(lwc,'lwc',lwc_raw); CALL read3(lwc,'ice',ice_raw)
  CALL read3(lwc,'rai',rai_raw); CALL read3(lwc,'sno',sno_raw); CALL read3(lwc,'pic',pic_raw)
  CALL read2(lsx,'t',surface_t); CALL read2(lsx,'ps',surface_p)
  CALL check_scaled(state%temperature%value,t_raw,state%above_ground,1.0_real64)
  CALL check_scaled(state%geopotential%value,ht_raw,state%above_ground,GRAVITY)
  CALL check_vapor(state,q_raw)
  CALL check_hydro(state%cloud_water%value,lwc_raw,state,t_raw,q_raw,levels)
  CALL check_hydro(state%cloud_ice%value,ice_raw,state,t_raw,q_raw,levels)
  CALL check_hydro(state%rain%value,rai_raw,state,t_raw,q_raw,levels)
  CALL check_hydro(state%snow%value,sno_raw,state,t_raw,q_raw,levels)
  CALL check_hydro(state%graupel%value,pic_raw,state,t_raw,q_raw,levels)
  CALL check_surface(state%surface_temperature%value,state%surface_temperature%valid,surface_t)
  CALL check_surface(state%surface_pressure%value,state%surface_pressure%valid,surface_p)
  CALL check_source3(state%temperature); CALL check_source3(state%geopotential)
  CALL check_source3(state%vapor); CALL check_source3(state%cloud_water)
  CALL check_source3(state%cloud_ice); CALL check_source3(state%rain)
  CALL check_source3(state%snow); CALL check_source3(state%graupel)
  CALL check_source2(state%surface_temperature); CALL check_source2(state%surface_pressure)
  CALL read2(lsx,'mr',surface_mr)
  CALL read2(static_file,'avg',terrain)
  IF (.NOT.ALL(state%surface_vapor%valid) .OR. &
      .NOT.ALL(state%surface_height%valid)) ERROR STOP 'surface boundary coverage missing'
  surface_mr=0.001_real32*surface_mr
  CALL check_surface(state%surface_vapor%value,state%surface_vapor%valid,surface_mr)
  CALL check_surface(state%surface_height%value,state%surface_height%valid,terrain)
  CALL check_source2(state%surface_vapor)
  IF (ANY(state%surface_height%source/=SOURCE_BACKGROUND_MODEL)) &
    ERROR STOP 'terrain provenance mismatch'
  IF (state%surface_vapor%unit/='kg kg-1 dryair' .OR. &
      state%surface_height%unit/='m') ERROR STOP 'surface boundary units mismatch'

  IF (TRIM(mode)=='INACTIVE_HT') THEN
    CALL check_extreme_ht(state,ht_raw,levels,surface_p,.FALSE.)
    WRITE(*,'(A)') 'inactive LT1 HT payload masked with canonical zero/no provenance'
    STOP
  END IF

  CALL read_real_shadow_state(TRIM(valid_fua),TRIM(valid_fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
      TRIM(static_file),VALID_TIME,rejected,longitude,status,reason,lt1_path=TRIM(lt1))
  IF (status==STATUS_OK) ERROR STOP 'partial analysis paths fell back to background files'
  CALL read_real_shadow_state(TRIM(valid_fua),TRIM(valid_fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
      TRIM(static_file),VALID_TIME,rejected,longitude,status,reason, &
      lt1_path=TRIM(lt1),lq3_path=TRIM(missing_lq3),lwc_path=TRIM(lwc),lsx_path=TRIM(lsx))
  IF (status==STATUS_OK) ERROR STOP 'missing lq3 fell back to background files'
  WRITE(*,'(A)') 'Analysis SHADOW reader normalization and all-or-none test passed'

CONTAINS
  SUBROUTINE read3(path,name,data)
    CHARACTER(LEN=*),INTENT(IN) :: path,name
    REAL(real32),INTENT(OUT) :: data(NX,NY,NZ)
    REAL(real32) :: work(NX,NY,NZ,1)
    INTEGER :: ncid,varid,rc
    rc=nf90_open(TRIM(path),NF90_NOWRITE,ncid); IF (rc/=NF90_NOERR) ERROR STOP 'raw open failed'
    rc=nf90_inq_varid(ncid,TRIM(name),varid); IF (rc/=NF90_NOERR) ERROR STOP 'raw variable missing'
    rc=nf90_get_var(ncid,varid,work); IF (rc/=NF90_NOERR) ERROR STOP 'raw read failed'
    rc=nf90_close(ncid); IF (rc/=NF90_NOERR) ERROR STOP 'raw close failed'
    data=work(:,:,:,1)
  END SUBROUTINE read3

  SUBROUTINE read2(path,name,data)
    CHARACTER(LEN=*),INTENT(IN) :: path,name
    REAL(real32),INTENT(OUT) :: data(NX,NY)
    REAL(real32) :: work(NX,NY,1,1)
    INTEGER :: ncid,varid,rc
    rc=nf90_open(TRIM(path),NF90_NOWRITE,ncid); IF (rc/=NF90_NOERR) ERROR STOP 'raw open failed'
    rc=nf90_inq_varid(ncid,TRIM(name),varid); IF (rc/=NF90_NOERR) ERROR STOP 'raw variable missing'
    rc=nf90_get_var(ncid,varid,work); IF (rc/=NF90_NOERR) ERROR STOP 'raw read failed'
    rc=nf90_close(ncid); IF (rc/=NF90_NOERR) ERROR STOP 'raw close failed'
    data=work(:,:,1,1)
  END SUBROUTINE read2

  SUBROUTINE read_levels(path,data)
    CHARACTER(LEN=*),INTENT(IN) :: path
    REAL(real64),INTENT(OUT) :: data(NZ)
    INTEGER :: ncid,varid,rc
    rc=nf90_open(TRIM(path),NF90_NOWRITE,ncid); IF (rc/=NF90_NOERR) ERROR STOP 'raw open failed'
    rc=nf90_inq_varid(ncid,'level',varid); IF (rc/=NF90_NOERR) ERROR STOP 'raw levels missing'
    rc=nf90_get_var(ncid,varid,data); IF (rc/=NF90_NOERR) ERROR STOP 'raw levels read failed'
    rc=nf90_close(ncid); IF (rc/=NF90_NOERR) ERROR STOP 'raw close failed'
  END SUBROUTINE read_levels

  SUBROUTINE check_scaled(actual,raw,domain,scale)
    REAL(real32),INTENT(IN) :: actual(:,:,:),raw(NX,NY,NZ)
    LOGICAL,INTENT(IN) :: domain(NX,NY,NZ)
    REAL(real64),INTENT(IN) :: scale
    INTEGER :: i,j,k,source_k
    REAL(real64) :: expected
    DO k=1,NZ; source_k=NZ+1-k; DO j=1,NY; DO i=1,NX
      IF (.NOT.domain(i,j,k)) CYCLE
      expected=scale*REAL(raw(i,j,source_k),real64)
      IF (ABS(REAL(actual(i,j,k),real64)-expected)>TOL_FACTOR*MAX(ABS(expected),1.0e-12_real64)) &
        ERROR STOP 'reversed normalized field mismatch'
    END DO; END DO; END DO
  END SUBROUTINE check_scaled

  SUBROUTINE check_vapor(s,raw)
    TYPE(cloud_bal_state_type),INTENT(IN) :: s
    REAL(real32),INTENT(IN) :: raw(NX,NY,NZ)
    INTEGER :: i,j,k,source_k
    REAL(real64) :: expected,q
    DO k=1,NZ; source_k=NZ+1-k; DO j=1,NY; DO i=1,NX
      IF (.NOT.s%above_ground(i,j,k)) CYCLE
      q=REAL(raw(i,j,source_k),real64)
      expected=REAL(q/(1.0_real64-q),real32)
      IF (ABS(REAL(s%vapor%value(i,j,k),real64)-expected)>TOL_FACTOR*MAX(ABS(expected),1.0e-12_real64)) &
        ERROR STOP 'specific humidity conversion mismatch'
    END DO; END DO; END DO
  END SUBROUTINE check_vapor

  SUBROUTINE check_hydro(actual,raw,s,t_raw,q_raw,levels)
    REAL(real32),INTENT(IN) :: actual(:,:,:),raw(NX,NY,NZ)
    TYPE(cloud_bal_state_type),INTENT(IN) :: s
    REAL(real32),INTENT(IN) :: t_raw(NX,NY,NZ),q_raw(NX,NY,NZ)
    REAL(real64),INTENT(IN) :: levels(NZ)
    INTEGER :: i,j,k,source_k
    REAL(real64) :: pressure,temperature,vapor,rho,expected
    DO k=1,NZ; source_k=NZ+1-k; DO j=1,NY; DO i=1,NX
      IF (.NOT.s%above_ground(i,j,k)) CYCLE
      pressure=REAL(100.0_real64*levels(source_k),real32)
      temperature=REAL(t_raw(i,j,source_k),real64)
      vapor=REAL(REAL(q_raw(i,j,source_k),real64)/ &
        (1.0_real64-REAL(q_raw(i,j,source_k),real64)),real32)
      rho=pressure/(RD_AIR*temperature*(1.0_real64+vapor/EPS))
      expected=REAL(raw(i,j,source_k),real64)/rho
      IF (ABS(REAL(actual(i,j,k),real64)-expected)>TOL_FACTOR*MAX(ABS(expected),1.0e-12_real64)) &
        ERROR STOP 'hydrometeor density conversion mismatch'
    END DO; END DO; END DO
  END SUBROUTINE check_hydro

  SUBROUTINE check_surface(actual,valid,raw)
    REAL(real32),INTENT(IN) :: actual(:,:),raw(NX,NY)
    LOGICAL,INTENT(IN) :: valid(:,:)
    IF (ANY(valid .AND. ABS(REAL(actual,real64)-REAL(raw,real64))>TOL_FACTOR* &
        MAX(ABS(REAL(raw,real64)),1.0e-12_real64))) &
      ERROR STOP 'surface analysis mismatch'
  END SUBROUTINE check_surface

  SUBROUTINE check_source3(field)
    TYPE(field3d),INTENT(IN) :: field
    IF (ANY(field%valid .AND. IAND(field%source,SOURCE_OUTPUT_ADAPTER)==0_int32)) &
      ERROR STOP 'direct field lacks output-adapter provenance'
  END SUBROUTINE check_source3

  SUBROUTINE check_source2(field)
    TYPE(field2d),INTENT(IN) :: field
    IF (ANY(field%valid .AND. IAND(field%source,SOURCE_OUTPUT_ADAPTER)==0_int32)) &
      ERROR STOP 'direct surface lacks output-adapter provenance'
  END SUBROUTINE check_source2

  SUBROUTINE check_extreme_ht(s,raw,levels,ps,expect_active)
    TYPE(cloud_bal_state_type),INTENT(IN) :: s
    REAL(real32),INTENT(IN) :: raw(NX,NY,NZ),ps(NX,NY)
    REAL(real64),INTENT(IN) :: levels(NZ)
    LOGICAL,INTENT(IN) :: expect_active
    INTEGER :: raw_level,i,j,k,nfound
    LOGICAL :: active
    nfound=0
    DO raw_level=1,NZ; DO j=1,NY; DO i=1,NX
      IF (ABS(raw(i,j,raw_level))/=HUGE(1.0_real32)) CYCLE
      nfound=nfound+1; k=NZ+1-raw_level
      active=100.0_real64*levels(raw_level)<REAL(ps(i,j),real64)
      IF (active .NEQV. expect_active) ERROR STOP 'LT1 HT test selected wrong domain cell'
      IF (expect_active) THEN
        IF (.NOT.s%above_ground(i,j,k)) ERROR STOP 'LT1 HT active cell was not selected'
      ELSE IF (s%geopotential%valid(i,j,k) .OR. s%geopotential%source(i,j,k)/=0_int32 .OR. &
               s%geopotential%value(i,j,k)/=0.0_real32) THEN
        ERROR STOP 'inactive LT1 HT cell retained canonical value or provenance'
      END IF
    END DO; END DO; END DO
    IF (nfound/=1) ERROR STOP 'LT1 HT test did not find exactly one float32 maximum'
  END SUBROUTINE check_extreme_ht
END PROGRAM test_analysis_shadow_reader
