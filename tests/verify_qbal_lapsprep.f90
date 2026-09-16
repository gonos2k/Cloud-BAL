PROGRAM verify_qbal_lapsprep
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32, int64, real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE netcdf, ONLY: nf90_open,nf90_close,nf90_nowrite,nf90_noerr,nf90_float, &
    nf90_inq_varid,nf90_inquire_variable,nf90_get_var,nf90_get_att,nf90_enotatt, &
    nf90_inq_dimid,nf90_inquire_dimension
  IMPLICIT NONE
  INTEGER, PARAMETER :: nx=6, ny=6, nz=4, nout=nz+1
  INTEGER(int64), PARAMETER :: candidate_size=12_int64+4_int64*(nz+6*nx*ny*nz)
  INTEGER(int64), PARAMETER :: reader_size=12_int64+4_int64*(nout+6*nx*ny*nout)
  INTEGER(int32), PARAMETER :: dimensions3(3)=[6_int32,6_int32,4_int32]
  INTEGER(int32), PARAMETER :: dimensions5(3)=[6_int32,6_int32,5_int32]
  REAL :: candidate_p(nz),u(nx,ny,nz),v(nx,ny,nz),phi(nx,ny,nz)
  REAL :: temperature(nx,ny,nz),q(nx,ny,nz),omega(nx,ny,nz)
  REAL :: pressure(nout),ht(nx,ny,nout),t(nx,ny,nout),mr(nx,ny,nout)
  REAL :: reader_u(nx,ny,nout),reader_v(nx,ny,nout),reader_omega(nx,ny,nout)
  REAL :: expected_ht(nx,ny,nout),expected_t(nx,ny,nout),expected_mr(nx,ny,nout)
  REAL :: expected_u(nx,ny,nout),expected_v(nx,ny,nout),expected_omega(nx,ny,nout)
  REAL :: expected_geometry(8)
  CHARACTER(4096) :: candidate_file,reader_file,wps_file,static_file
  INTEGER :: k,source
  IF (COMMAND_ARGUMENT_COUNT() /= 4) CALL fail('usage: candidate.bin reader_state.bin wps.out static.nest7grid')
  CALL GET_COMMAND_ARGUMENT(1,candidate_file)
  CALL GET_COMMAND_ARGUMENT(2,reader_file)
  CALL GET_COMMAND_ARGUMENT(3,wps_file)
  CALL GET_COMMAND_ARGUMENT(4,static_file)
  CALL read_source_geometry(TRIM(static_file),expected_geometry)
  CALL read_candidate(TRIM(candidate_file),candidate_p,u,v,phi,temperature,q,omega)
  expected_ht=0.0; expected_t=0.0; expected_mr=0.0
  expected_u=0.0; expected_v=0.0; expected_omega=0.0
  DO k=1,nz
    source=nz-k+1
    expected_ht(:,:,k)=phi(:,:,source)/9.80665
    expected_t(:,:,k)=temperature(:,:,source)
    expected_mr(:,:,k)=q(:,:,source)/(1.0-q(:,:,source))
    expected_u(:,:,k)=u(:,:,source)
    expected_v(:,:,k)=v(:,:,source)
    expected_omega(:,:,k)=omega(:,:,source)
  END DO
  expected_ht(:,:,nout)=0.0; expected_t(:,:,nout)=280.0; expected_mr(:,:,nout)=8.0/1000.0
  expected_u(:,:,nout)=2.0; expected_v(:,:,nout)=-2.0; expected_omega(:,:,nout)=0.0
  CALL read_reader(TRIM(reader_file),pressure,ht,t,mr,reader_u,reader_v,reader_omega)
  CALL check_vector(pressure,[700.0,800.0,900.0,1000.0,2001.0],'reader pressure')
  CALL check_vector(RESHAPE(ht,[SIZE(ht)]),RESHAPE(expected_ht,[SIZE(ht)]),'reader ht')
  CALL check_vector(RESHAPE(t,[SIZE(t)]),RESHAPE(expected_t,[SIZE(t)]),'reader t')
  CALL check_vector(RESHAPE(mr,[SIZE(mr)]),RESHAPE(expected_mr,[SIZE(mr)]),'reader mr')
  CALL check_vector(RESHAPE(reader_u,[SIZE(reader_u)]),RESHAPE(expected_u,[SIZE(reader_u)]),'reader u')
  CALL check_vector(RESHAPE(reader_v,[SIZE(reader_v)]),RESHAPE(expected_v,[SIZE(reader_v)]),'reader v')
  CALL check_vector(RESHAPE(reader_omega,[SIZE(reader_omega)]), &
                    RESHAPE(expected_omega,[SIZE(reader_omega)]),'reader omega')
  CALL check_wps(TRIM(wps_file),expected_ht,expected_t,expected_mr,expected_u,expected_v)
  WRITE(*,'(A)') 'PASS_SCOPED'
CONTAINS
  SUBROUTINE fail(message)
    CHARACTER(*), INTENT(IN) :: message
    WRITE(*,'(A)') 'FAIL: '//TRIM(message)
    ERROR STOP 1
  END SUBROUTINE fail
  LOGICAL FUNCTION same_bits(a,b)
    REAL, INTENT(IN) :: a,b
    INTEGER(int32) :: ia,ib
    ia=TRANSFER(a,ia)
    ib=TRANSFER(b,ib)
    same_bits=(ia == ib)
  END FUNCTION same_bits
  SUBROUTINE check_vector(actual,expected,label)
    REAL, INTENT(IN) :: actual(:),expected(:)
    CHARACTER(*), INTENT(IN) :: label
    INTEGER :: i
    DO i=1,SIZE(actual)
      IF (.NOT.ieee_is_finite(actual(i)) .OR. .NOT.ieee_is_finite(expected(i))) &
        CALL fail(TRIM(label)//': nonfinite')
      IF (.NOT.same_bits(actual(i),expected(i))) CALL fail(TRIM(label)//': bits differ')
    END DO
  END SUBROUTINE check_vector
  SUBROUTINE read_source_geometry(name,geometry)
    CHARACTER(*), INTENT(IN) :: name
    REAL, INTENT(OUT) :: geometry(8)
    CHARACTER(6), PARAMETER :: variables(7)=[character(6) :: 'lat','lon','Dx','Dy','LoV','Latin1','Latin2']
    CHARACTER(13), PARAMETER :: missing_attributes(2)=[character(13) :: '_FillValue','missing_value']
    INTEGER :: ncid,vid,status,xtype,rank,i,j,dimid,length
    INTEGER :: start(4)
    REAL(real64) :: missing
    CHARACTER(132) :: projection

    status=nf90_open(name,nf90_nowrite,ncid)
    IF (status /= nf90_noerr) CALL fail('source static open failed')
    status=nf90_inq_dimid(ncid,'x',dimid)
    IF (status == nf90_noerr) status=nf90_inquire_dimension(ncid,dimid,len=length)
    IF (status /= nf90_noerr) CALL fail('source static x dimension missing')
    IF (length /= nx) CALL fail('source static x dimension mismatch')
    status=nf90_inq_dimid(ncid,'y',dimid)
    IF (status == nf90_noerr) status=nf90_inquire_dimension(ncid,dimid,len=length)
    IF (status /= nf90_noerr) CALL fail('source static y dimension missing')
    IF (length /= ny) CALL fail('source static y dimension mismatch')
    status=nf90_inq_varid(ncid,'grid_type',vid)
    IF (status == nf90_noerr) status=nf90_get_var(ncid,vid,projection)
    IF (status /= nf90_noerr) CALL fail('source static projection read failed')
    IF (TRIM(projection) /= 'secant lambert conformal') CALL fail('source static projection unsupported')
    start=1
    DO i=1,SIZE(variables)
      status=nf90_inq_varid(ncid,TRIM(variables(i)),vid)
      IF (status == nf90_noerr) status=nf90_inquire_variable(ncid,vid,xtype=xtype,ndims=rank)
      IF (status /= nf90_noerr) CALL fail('source static variable missing: '//TRIM(variables(i)))
      IF (xtype /= nf90_float .OR. rank < 1 .OR. rank > 4) CALL fail('source static layout mismatch')
      status=nf90_get_var(ncid,vid,geometry(i),start=start(:rank))
      IF (status /= nf90_noerr) CALL fail('source static value read failed')
      IF (.NOT.ieee_is_finite(geometry(i))) CALL fail('source geometry: nonfinite')
      DO j=1,SIZE(missing_attributes)
        status=nf90_get_att(ncid,vid,TRIM(missing_attributes(j)),missing)
        IF (status == nf90_noerr) THEN
          IF (ieee_is_finite(missing)) THEN
            IF (REAL(geometry(i),real64) == missing) CALL fail('source geometry: missing value')
          END IF
        ELSE IF (status /= nf90_enotatt) THEN
          CALL fail('source geometry: invalid missing attribute')
        END IF
      END DO
    END DO
    status=nf90_close(ncid)
    IF (status /= nf90_noerr) CALL fail('source static close failed')
    ! Static navigation is in degrees and meters; WPS spacing/radius is in km.
    IF (geometry(1) > 270.) geometry(1)=geometry(1)-360.
    IF (geometry(2) > 180.) geometry(2)=geometry(2)-360.
    geometry(3:4)=geometry(3:4)/1000.
    IF (geometry(5) > 180.) geometry(5)=geometry(5)-360.
    geometry(8)=6371.229  ! Declared Earth radius in the maintained WPS writer.
    IF (ANY(geometry(3:4) <= 0.)) CALL fail('source geometry: nonpositive scale')
  END SUBROUTINE read_source_geometry
  SUBROUTINE read_candidate(name,p,u,v,phi,temp,moisture,om)
    CHARACTER(*), INTENT(IN) :: name
    REAL, INTENT(OUT) :: p(:),u(:,:,:),v(:,:,:),phi(:,:,:),temp(:,:,:),moisture(:,:,:),om(:,:,:)
    INTEGER(int32) :: dimensions(3)
    INTEGER(int64) :: file_size
    INTEGER :: unit,ios
    LOGICAL :: exists
    INQUIRE(FILE=name,EXIST=exists,SIZE=file_size)
    IF (.NOT.exists .OR. file_size /= candidate_size) CALL fail('candidate file size mismatch')
    OPEN(NEWUNIT=unit,FILE=name,FORM='UNFORMATTED',ACCESS='STREAM',STATUS='OLD', &
         ACTION='READ',CONVERT='LITTLE_ENDIAN',IOSTAT=ios)
    IF (ios /= 0) CALL fail('candidate open failed')
    READ(unit,IOSTAT=ios) dimensions
    IF (ios /= 0 .OR. ANY(dimensions /= dimensions3)) CALL fail('candidate dimensions mismatch')
    READ(unit,IOSTAT=ios) p,u,v,phi,temp,moisture,om
    IF (ios /= 0) CALL fail('candidate fields read failed')
    CLOSE(unit,IOSTAT=ios)
    IF (ios /= 0) CALL fail('candidate close failed')
    CALL check_vector(p,[100000.0,90000.0,80000.0,70000.0],'candidate pressure')
  END SUBROUTINE read_candidate
  SUBROUTINE read_reader(name,p,ht,t,mr,u,v,om)
    CHARACTER(*), INTENT(IN) :: name
    REAL, INTENT(OUT) :: p(:),ht(:,:,:),t(:,:,:),mr(:,:,:),u(:,:,:),v(:,:,:),om(:,:,:)
    INTEGER(int32) :: dimensions(3)
    INTEGER(int64) :: file_size
    INTEGER :: unit,ios
    LOGICAL :: exists
    INQUIRE(FILE=name,EXIST=exists,SIZE=file_size)
    IF (.NOT.exists .OR. file_size /= reader_size) CALL fail('reader state file size mismatch')
    OPEN(NEWUNIT=unit,FILE=name,FORM='UNFORMATTED',ACCESS='STREAM',STATUS='OLD', &
         ACTION='READ',CONVERT='LITTLE_ENDIAN',IOSTAT=ios)
    IF (ios /= 0) CALL fail('reader state open failed')
    READ(unit,IOSTAT=ios) dimensions
    IF (ios /= 0 .OR. ANY(dimensions /= dimensions5)) CALL fail('reader state dimensions mismatch')
    READ(unit,IOSTAT=ios) p,ht,t,mr,u,v,om
    IF (ios /= 0) CALL fail('reader state fields read failed')
    CLOSE(unit,IOSTAT=ios)
    IF (ios /= 0) CALL fail('reader state close failed')
  END SUBROUTINE read_reader
  INTEGER FUNCTION selected_field(name)
    CHARACTER(*), INTENT(IN) :: name
    SELECT CASE (TRIM(name))
    CASE ('UU'); selected_field=1
    CASE ('VV'); selected_field=2
    CASE ('TT'); selected_field=3
    CASE ('HGT'); selected_field=4
    CASE ('QV'); selected_field=5
    CASE DEFAULT; selected_field=0
    END SELECT
  END FUNCTION selected_field
  SUBROUTINE check_wps(name,expected_ht,expected_t,expected_mr,expected_u,expected_v)
    CHARACTER(*), INTENT(IN) :: name
    REAL, INTENT(IN) :: expected_ht(:,:,:),expected_t(:,:,:),expected_mr(:,:,:)
    REAL, INTENT(IN) :: expected_u(:,:,:),expected_v(:,:,:)
    REAL, PARAMETER :: levels(5)=[70000.0,80000.0,90000.0,100000.0,200100.0]
    CHARACTER(24), PARAMETER :: expected_time='2023-05-18_03:33:20.0000'
    CHARACTER(4), PARAMETER :: names(5)=(/'UU  ','VV  ','TT  ','HGT ','QV  '/)
    CHARACTER(25), PARAMETER :: units_expected(5)=[character(25) :: 'm s{-1}','m s{-1}','K','m','kg kg{-1}']
    LOGICAL :: seen(5,5),exists
    CHARACTER(24) :: hdate
    CHARACTER(32) :: source_name
    CHARACTER(9) :: field
    CHARACTER(25) :: units
    CHARACTER(46) :: description
    CHARACTER(8) :: knownloc
    REAL :: xfcst,level,la1,lo1,dx,dy,lov,latin1,latin2,earth_radius
    REAL :: slab(nx,ny)
    INTEGER(int32) :: wind_raw
    INTEGER :: unit,ios,version,nx_file,ny_file,llflag,wind_field
    INTEGER :: i,level_index
    INTEGER :: detect_unit
    CHARACTER(4) :: marker
    CHARACTER(13) :: byte_order
    CHARACTER(80) :: label,level_text
    seen=.FALSE.
    INQUIRE(FILE=name,EXIST=exists)
    IF (.NOT.exists) CALL fail('WPS file missing')
    OPEN(NEWUNIT=detect_unit,FILE=name,FORM='UNFORMATTED',ACCESS='STREAM',STATUS='OLD', &
         ACTION='READ',IOSTAT=ios)
    IF (ios /= 0) CALL fail('WPS open failed')
    READ(detect_unit,IOSTAT=ios) marker
    CLOSE(detect_unit)
    IF (ios /= 0) CALL fail('WPS record marker read failed')
    IF (IACHAR(marker(1:1)) == 0 .AND. IACHAR(marker(2:2)) == 0 .AND. &
        IACHAR(marker(3:3)) == 0 .AND. IACHAR(marker(4:4)) == 4) THEN
      byte_order='BIG_ENDIAN'
    ELSE IF (IACHAR(marker(1:1)) == 4 .AND. IACHAR(marker(2:2)) == 0 .AND. &
             IACHAR(marker(3:3)) == 0 .AND. IACHAR(marker(4:4)) == 0) THEN
      byte_order='LITTLE_ENDIAN'
    ELSE
      CALL fail('WPS record marker invalid')
    END IF
    OPEN(NEWUNIT=unit,FILE=name,FORM='UNFORMATTED',ACCESS='SEQUENTIAL',STATUS='OLD', &
         ACTION='READ',CONVERT=TRIM(byte_order),IOSTAT=ios)
    IF (ios /= 0) CALL fail('WPS open failed')
    DO
      READ(unit,IOSTAT=ios) version
      IF (ios < 0) EXIT
      IF (ios /= 0 .OR. version /= 5) CALL fail('WPS version mismatch')
      READ(unit,IOSTAT=ios) hdate,xfcst,source_name,field,units,description,level, &
        nx_file,ny_file,llflag
      IF (ios /= 0) CALL fail('WPS metadata read failed')
      CALL check_vector([xfcst],[0.],'WPS XFCST')
      IF (hdate /= expected_time) CALL fail('WPS time mismatch')
      IF (nx_file /= nx .OR. ny_file /= ny) CALL fail('WPS shape mismatch')
      IF (llflag /= 3) CALL fail('WPS projection mismatch')
      READ(unit,IOSTAT=ios) knownloc,la1,lo1,dx,dy,lov,latin1,latin2,earth_radius
      IF (ios /= 0) CALL fail('WPS projection read failed')
      IF (knownloc /= 'SWCORNER') CALL fail('WPS KNOWNLOC mismatch')
      IF (.NOT.ALL(ieee_is_finite([la1,lo1,dx,dy,lov,latin1,latin2,earth_radius]))) &
        CALL fail('WPS geometry: nonfinite')
      IF (dx <= 0. .OR. dy <= 0. .OR. earth_radius <= 0.) CALL fail('WPS geometry: nonpositive scale')
      CALL check_vector([la1,lo1,dx,dy,lov,latin1,latin2,earth_radius],expected_geometry,'WPS geometry')
      READ(unit,IOSTAT=ios) wind_raw
      IF (ios /= 0) CALL fail('WPS wind metadata read failed')
      IF (wind_raw /= -1 .AND. wind_raw /= 0 .AND. wind_raw /= 1) &
        CALL fail('WPS wind metadata invalid')
      READ(unit,IOSTAT=ios) slab
      IF (ios /= 0) CALL fail('WPS slab read failed')
      IF (TRIM(field) == 'W' .OR. TRIM(field) == 'WW' .OR. TRIM(field) == 'OM' .OR. &
          TRIM(field) == 'OMEGA') CALL fail('unexpected WPS omega field')
      wind_field=selected_field(field)
      IF (wind_field == 0) CYCLE
      IF (wind_raw == 0) CALL fail('WPS '//TRIM(field)//': wind basis mismatch')
      IF (TRIM(units) /= TRIM(units_expected(wind_field))) &
        CALL fail('WPS '//TRIM(field)//': metadata mismatch')
      level_index=0
      DO i=1,5
        IF (same_bits(level,levels(i))) level_index=i
      END DO
      IF (level_index == 0) CALL fail('WPS '//TRIM(field)//': pressure inventory mismatch')
      IF (seen(wind_field,level_index)) CALL fail('WPS '//TRIM(field)//': duplicate record')
      seen(wind_field,level_index)=.TRUE.
      WRITE(level_text,'(F6.1)') levels(level_index)/100.0
      label='WPS '//TRIM(field)//' '//ADJUSTL(level_text)
      SELECT CASE (wind_field)
      CASE (1); CALL check_vector(RESHAPE(slab,[SIZE(slab)]), &
          RESHAPE(expected_u(:,:,level_index),[SIZE(slab)]),label)
      CASE (2); CALL check_vector(RESHAPE(slab,[SIZE(slab)]), &
          RESHAPE(expected_v(:,:,level_index),[SIZE(slab)]),label)
      CASE (3); CALL check_vector(RESHAPE(slab,[SIZE(slab)]), &
          RESHAPE(expected_t(:,:,level_index),[SIZE(slab)]),label)
      CASE (4); CALL check_vector(RESHAPE(slab,[SIZE(slab)]), &
          RESHAPE(expected_ht(:,:,level_index),[SIZE(slab)]),label)
      CASE (5); CALL check_vector(RESHAPE(slab,[SIZE(slab)]), &
          RESHAPE(expected_mr(:,:,level_index),[SIZE(slab)]),label)
      END SELECT
    END DO
    CLOSE(unit,IOSTAT=ios)
    IF (ios /= 0) CALL fail('WPS close failed')
    DO wind_field=1,5
      DO level_index=1,5
        IF (.NOT.seen(wind_field,level_index)) &
          CALL fail('WPS '//TRIM(names(wind_field))//': pressure inventory mismatch')
      END DO
    END DO
  END SUBROUTINE check_wps
END PROGRAM verify_qbal_lapsprep
