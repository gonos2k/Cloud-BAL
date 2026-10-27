!dis   
!dis    Open Source License/Disclaimer, Forecast Systems Laboratory
!dis    NOAA/OAR/FSL, 325 Broadway Boulder, CO 80305
!dis    
!dis    This software is distributed under the Open Source Definition,
!dis    which may be found at http://www.opensource.org/osd.html.
!dis    
!dis    In particular, redistribution and use in source and binary forms,
!dis    with or without modification, are permitted provided that the
!dis    following conditions are met:
!dis    
!dis    - Redistributions of source code must retain this notice, this
!dis    list of conditions and the following disclaimer.
!dis    
!dis    - Redistributions in binary form must provide access to this
!dis    notice, this list of conditions and the following disclaimer, and
!dis    the underlying source code.
!dis    
!dis    - All modifications to this software must be clearly documented,
!dis    and are solely the responsibility of the agent making the
!dis    modifications.
!dis    
!dis    - If significant modifications or enhancements are made to this
!dis    software, the FSL Software Policy Manager
!dis    (softwaremgr@fsl.noaa.gov) should be notified.
!dis    
!dis    THIS SOFTWARE AND ITS DOCUMENTATION ARE IN THE PUBLIC DOMAIN
!dis    AND ARE FURNISHED "AS IS."  THE AUTHORS, THE UNITED STATES
!dis    GOVERNMENT, ITS INSTRUMENTALITIES, OFFICERS, EMPLOYEES, AND
!dis    AGENTS MAKE NO WARRANTY, EXPRESS OR IMPLIED, AS TO THE USEFULNESS
!dis    OF THE SOFTWARE AND DOCUMENTATION FOR ANY PURPOSE.  THEY ASSUME
!dis    NO RESPONSIBILITY (1) FOR THE USE OF THE SOFTWARE AND
!dis    DOCUMENTATION; OR (2) TO PROVIDE TECHNICAL SUPPORT TO USERS.
!dis   
!dis 

MODULE laps_static

  USE netcdf, ONLY: NF90_MAX_NAME, NF90_MAX_VAR_DIMS, NF90_NOERR, NF90_NOWRITE, &
      NF90_OPEN, NF90_CLOSE, NF90_INQ_DIMID, NF90_INQUIRE_DIMENSION, NF90_INQ_VARID, &
      NF90_INQUIRE_VARIABLE, NF90_GET_VAR, NF90_INQUIRE_ATTRIBUTE, NF90_GET_ATT, &
      NF90_STRERROR, NF90_CHAR, NF90_FLOAT, NF90_BYTE, NF90_SHORT, NF90_INT, &
      NF90_DOUBLE, NF90_ENOTATT, NF90_FILL_FLOAT
  USE, INTRINSIC :: IEEE_ARITHMETIC, ONLY: IEEE_IS_FINITE
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: x,y,z2,z3,la1,lo1,la2,lo2,dx,dy,lov,latin1,latin2,topo,lats,lons,grid_type
  PUBLIC :: get_horiz_grid_spec
  INTEGER                     :: x              ! X-dimension of grid
  INTEGER                     :: y              ! Y-dimension of grid
  INTEGER                     :: z2             ! Z-dimension of 2-d grids
  INTEGER                     :: z3             ! Z-dimension of 3-d press
  REAL                        :: la1            ! SW Corner Lat
  REAL                        :: lo1            ! SE Corner Lon
  REAL                        :: la2            ! NE Corner Lat
  REAL                        :: lo2            ! NE Corner Lon
  REAL                        :: dx             ! X-direction grid spacing
  REAL                        :: dy             ! Y-direction grid spacing
  REAL                        :: lov            ! Orientation Longitude
  REAL                        :: latin1         ! Standard Lat 1
  REAL                        :: latin2         ! Standard Lat 2
  REAL, ALLOCATABLE           :: topo(:,:)      ! LAPS Topographic height
  REAL, ALLOCATABLE           :: lats(:,:)      ! LAPS Latitude Array
  REAL, ALLOCATABLE           :: lons(:,:)      ! LAPS Longitude Array
  CHARACTER (LEN=132)         :: grid_type      ! Map projection type

CONTAINS

  SUBROUTINE get_horiz_grid_spec(laps_data_root)
    IMPLICIT NONE
    CHARACTER (LEN=*), INTENT(IN) :: laps_data_root
    CHARACTER (LEN=256) :: static_file
    CHARACTER (LEN=NF90_MAX_NAME) :: dim_name
    INTEGER :: ncid,status,xid,yid,vid,rank,xtype,natts
    INTEGER :: var_dims(NF90_MAX_VAR_DIMS),grid_len,grid_count
    INTEGER :: startc(2),countc(2),start(4),count(4)

    static_file = TRIM(laps_data_root)//'/static/static.nest7grid'
    status = NF90_OPEN(TRIM(static_file),NF90_NOWRITE,ncid)
    CALL require_status(status,'open static file')

    status = NF90_INQ_DIMID(ncid,'x',xid)
    CALL require_status(status,'find x dimension',ncid)
    status = NF90_INQ_DIMID(ncid,'y',yid)
    CALL require_status(status,'find y dimension',ncid)
    status = NF90_INQUIRE_DIMENSION(ncid,xid,dim_name,x)
    CALL require_status(status,'read x dimension',ncid)
    status = NF90_INQUIRE_DIMENSION(ncid,yid,dim_name,y)
    CALL require_status(status,'read y dimension',ncid)
    IF (x <= 0 .OR. y <= 0) CALL static_error('x/y dimensions must be positive',ncid)

    status = NF90_INQ_VARID(ncid,'grid_type',vid)
    CALL require_status(status,'find grid_type',ncid)
    status = NF90_INQUIRE_VARIABLE(ncid,vid,xtype=xtype,ndims=rank,dimids=var_dims,natts=natts)
    CALL require_status(status,'inspect grid_type',ncid)
    IF (xtype /= NF90_CHAR .OR. rank /= 2) CALL static_error('grid_type must be rank-2 character data',ncid)
    status = NF90_INQUIRE_DIMENSION(ncid,var_dims(1),dim_name,grid_len)
    CALL require_status(status,'inspect grid_type length',ncid)
    status = NF90_INQUIRE_DIMENSION(ncid,var_dims(2),dim_name,grid_count)
    CALL require_status(status,'inspect grid_type count',ncid)
    IF (grid_len <= 0 .OR. grid_len > LEN(grid_type) .OR. grid_count /= 1) &
      CALL static_error('grid_type must fit one 132-character value',ncid)
    grid_type = ' '
    startc = (/1,1/)
    countc = (/grid_len,1/)
    status = NF90_GET_VAR(ncid,vid,grid_type,start=startc,count=countc)
    CALL require_status(status,'read grid_type',ncid)

    ALLOCATE(lats(x,y),lons(x,y))
    status = NF90_INQ_VARID(ncid,'lat',vid)
    CALL require_status(status,'find lat',ncid)
    CALL require_float_grid(ncid,vid,'lat',xid,yid,x,y)
    start = (/1,1,1,1/)
    count = (/x,y,1,1/)
    status = NF90_GET_VAR(ncid,vid,lats,start=start,count=count)
    CALL require_status(status,'read lat',ncid)
    CALL require_valid_values(ncid,vid,'lat',lats)
    CALL require_coordinates(lats,'latitude',ncid)

    status = NF90_INQ_VARID(ncid,'lon',vid)
    CALL require_status(status,'find lon',ncid)
    CALL require_float_grid(ncid,vid,'lon',xid,yid,x,y)
    status = NF90_GET_VAR(ncid,vid,lons,start=start,count=count)
    CALL require_status(status,'read lon',ncid)
    CALL require_valid_values(ncid,vid,'lon',lons)
    CALL require_coordinates(lons,'longitude',ncid)
    la1 = lats(1,1)
    lo1 = lons(1,1)
    la2 = lats(x,y)
    lo2 = lons(x,y)
    IF (lo1 .gt. 180) lo1 = lo1 - 360.
    IF (lo2 .gt. 180) lo2 = lo2 - 360.
    IF (la1 .gt. 270) la1 = la1 - 360.
    IF (la2 .gt. 270) la2 = la2 - 360.
    PRINT '(A,2F10.2)', 'SW Corner Lat/Lon = ', la1, lo1
    PRINT '(A,2F10.2)', 'NE Corner Lat/Lon = ', la2, lo2

    status = NF90_INQ_VARID(ncid,'Dx',vid)
    CALL require_status(status,'find Dx',ncid)
    CALL require_float_scalar(ncid,vid,'Dx')
    status = NF90_GET_VAR(ncid,vid,dx)
    CALL require_status(status,'read Dx',ncid)
    CALL require_valid_values(ncid,vid,'Dx',RESHAPE((/dx/),(/1,1/)))
    CALL require_positive_finite(dx,'Dx',ncid)
    dx = dx / 1000
    CALL require_positive_finite(dx,'Dx in km',ncid)

    status = NF90_INQ_VARID(ncid,'Dy',vid)
    CALL require_status(status,'find Dy',ncid)
    CALL require_float_scalar(ncid,vid,'Dy')
    status = NF90_GET_VAR(ncid,vid,dy)
    CALL require_status(status,'read Dy',ncid)
    CALL require_valid_values(ncid,vid,'Dy',RESHAPE((/dy/),(/1,1/)))
    CALL require_positive_finite(dy,'Dy',ncid)
    dy = dy / 1000
    CALL require_positive_finite(dy,'Dy in km',ncid)

    status = NF90_INQ_VARID(ncid,'LoV',vid)
    CALL require_status(status,'find LoV',ncid)
    CALL require_float_scalar(ncid,vid,'LoV')
    status = NF90_GET_VAR(ncid,vid,lov)
    CALL require_status(status,'read LoV',ncid)
    CALL require_valid_values(ncid,vid,'LoV',RESHAPE((/lov/),(/1,1/)))
    IF (lov < -180.0 .OR. lov > 360.0) &
      CALL static_error('LoV must be a longitude in [-180,360]',ncid)
    IF (lov .GT. 180) lov = lov - 360
    IF (ABS(lov) > 180.0) CALL static_error('LoV must be a longitude in [-180,180]',ncid)

    status = NF90_INQ_VARID(ncid,'Latin1',vid)
    CALL require_status(status,'find Latin1',ncid)
    CALL require_float_scalar(ncid,vid,'Latin1')
    status = NF90_GET_VAR(ncid,vid,latin1)
    CALL require_status(status,'read Latin1',ncid)
    CALL require_valid_values(ncid,vid,'Latin1',RESHAPE((/latin1/),(/1,1/)))
    CALL require_latitude_parameter(latin1,'Latin1',ncid)

    status = NF90_INQ_VARID(ncid,'Latin2',vid)
    CALL require_status(status,'find Latin2',ncid)
    CALL require_float_scalar(ncid,vid,'Latin2')
    status = NF90_GET_VAR(ncid,vid,latin2)
    CALL require_status(status,'read Latin2',ncid)
    CALL require_valid_values(ncid,vid,'Latin2',RESHAPE((/latin2/),(/1,1/)))
    IF (grid_type(1:24) == 'secant lambert conformal' .OR. &
        grid_type(1:28) == 'tangential lambert conformal') &
      CALL require_latitude_parameter(latin2,'Latin2',ncid)

    ALLOCATE(topo(x,y))
    status = NF90_INQ_VARID(ncid,'avg',vid)
    CALL require_status(status,'find avg',ncid)
    CALL require_float_grid(ncid,vid,'avg',xid,yid,x,y)
    status = NF90_GET_VAR(ncid,vid,topo,start=start,count=count)
    CALL require_status(status,'read avg',ncid)
    CALL require_valid_values(ncid,vid,'avg',topo)
    status = NF90_CLOSE(ncid)
    CALL require_status(status,'close static file')
  END SUBROUTINE get_horiz_grid_spec

  SUBROUTINE require_status(status,operation,ncid)
    IMPLICIT NONE
    INTEGER, INTENT(IN) :: status
    CHARACTER(LEN=*), INTENT(IN) :: operation
    INTEGER, INTENT(IN), OPTIONAL :: ncid
    IF (status == NF90_NOERR) RETURN
    IF (PRESENT(ncid)) THEN
      CALL static_error(TRIM(operation)//': '//TRIM(NF90_STRERROR(status)),ncid)
    ELSE
      CALL static_error(TRIM(operation)//': '//TRIM(NF90_STRERROR(status)))
    END IF
  END SUBROUTINE require_status

  SUBROUTINE static_error(message,ncid)
    IMPLICIT NONE
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(IN), OPTIONAL :: ncid
    INTEGER :: close_status
    WRITE(*,'(A)') 'laps_static: '//TRIM(message)
    IF (PRESENT(ncid)) close_status = NF90_CLOSE(ncid)
    STOP 1
  END SUBROUTINE static_error

  SUBROUTINE require_float_scalar(ncid,vid,name)
    IMPLICIT NONE
    INTEGER, INTENT(IN) :: ncid,vid
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER :: status,xtype,rank,natts,dimids(NF90_MAX_VAR_DIMS),length
    CHARACTER(LEN=NF90_MAX_NAME) :: dim_name
    status = NF90_INQUIRE_VARIABLE(ncid,vid,xtype=xtype,ndims=rank,dimids=dimids,natts=natts)
    CALL require_status(status,'inspect '//TRIM(name),ncid)
    IF (xtype /= NF90_FLOAT .OR. rank /= 1) CALL static_error(TRIM(name)//' must be a one-element REAL32 variable',ncid)
    status = NF90_INQUIRE_DIMENSION(ncid,dimids(1),dim_name,length)
    CALL require_status(status,'inspect '//TRIM(name)//' length',ncid)
    IF (length /= 1) CALL static_error(TRIM(name)//' must have length one',ncid)
  END SUBROUTINE require_float_scalar

  SUBROUTINE require_float_grid(ncid,vid,name,xid,yid,nx,ny)
    IMPLICIT NONE
    INTEGER, INTENT(IN) :: ncid,vid,xid,yid,nx,ny
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER :: status,xtype,rank,natts,dimids(NF90_MAX_VAR_DIMS),length
    CHARACTER(LEN=NF90_MAX_NAME) :: dim_name
    status = NF90_INQUIRE_VARIABLE(ncid,vid,xtype=xtype,ndims=rank,dimids=dimids,natts=natts)
    CALL require_status(status,'inspect '//TRIM(name),ncid)
    IF (xtype /= NF90_FLOAT .OR. rank /= 4) CALL static_error(TRIM(name)//' must be a rank-4 REAL32 array',ncid)
    IF (dimids(1) /= xid .OR. dimids(2) /= yid) CALL static_error(TRIM(name)//' must use dimensions x,y first',ncid)
    status = NF90_INQUIRE_DIMENSION(ncid,dimids(1),dim_name,length)
    CALL require_status(status,'inspect '//TRIM(name)//' x length',ncid)
    IF (length /= nx) CALL static_error(TRIM(name)//' x length does not match x',ncid)
    status = NF90_INQUIRE_DIMENSION(ncid,dimids(2),dim_name,length)
    CALL require_status(status,'inspect '//TRIM(name)//' y length',ncid)
    IF (length /= ny) CALL static_error(TRIM(name)//' y length does not match y',ncid)
    status = NF90_INQUIRE_DIMENSION(ncid,dimids(3),dim_name,length)
    CALL require_status(status,'inspect '//TRIM(name)//' z length',ncid)
    IF (length /= 1) CALL static_error(TRIM(name)//' z dimension must be one',ncid)
    status = NF90_INQUIRE_DIMENSION(ncid,dimids(4),dim_name,length)
    CALL require_status(status,'inspect '//TRIM(name)//' record length',ncid)
    IF (length /= 1) CALL static_error(TRIM(name)//' record dimension must be one',ncid)
  END SUBROUTINE require_float_grid

  SUBROUTINE require_valid_values(ncid,vid,name,values)
    IMPLICIT NONE
    INTEGER, INTENT(IN) :: ncid,vid
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL, INTENT(IN) :: values(:,:)
    INTEGER :: status,i,j,xtype,length
    CHARACTER(LEN=NF90_MAX_NAME), PARAMETER :: attributes(2) = &
      [CHARACTER(LEN=NF90_MAX_NAME) :: '_FillValue','missing_value']
    DOUBLE PRECISION, ALLOCATABLE :: sentinels(:)

    IF (.NOT.ALL(IEEE_IS_FINITE(values))) CALL static_error(TRIM(name)//' contains nonfinite values',ncid)
    IF (ANY(values == NF90_FILL_FLOAT)) CALL static_error(TRIM(name)//' contains default fill values',ncid)

    DO i=1,SIZE(attributes)
      status = NF90_INQUIRE_ATTRIBUTE(ncid,vid,TRIM(attributes(i)),xtype=xtype,len=length)
      IF (status == NF90_ENOTATT) CYCLE
      CALL require_status(status,'inspect '//TRIM(name)//' '//TRIM(attributes(i)),ncid)
      IF (.NOT.is_numeric_type(xtype) .OR. length <= 0) &
        CALL static_error(TRIM(name)//' has malformed '//TRIM(attributes(i))//' attribute',ncid)
      IF (attributes(i) == '_FillValue' .AND. (xtype /= NF90_FLOAT .OR. length /= 1)) &
        CALL static_error(TRIM(name)//' has malformed _FillValue attribute',ncid)
      ALLOCATE(sentinels(length))
      status = NF90_GET_ATT(ncid,vid,TRIM(attributes(i)),sentinels)
      CALL require_status(status,'read '//TRIM(name)//' '//TRIM(attributes(i)),ncid)
      DO j=1,length
        IF (IEEE_IS_FINITE(sentinels(j))) THEN
          IF (ANY(DBLE(values) == sentinels(j))) &
            CALL static_error(TRIM(name)//' contains declared '//TRIM(attributes(i))//' sentinel',ncid)
        END IF
      END DO
      DEALLOCATE(sentinels)
    END DO
  END SUBROUTINE require_valid_values

  LOGICAL FUNCTION is_numeric_type(xtype)
    IMPLICIT NONE
    INTEGER, INTENT(IN) :: xtype
    is_numeric_type = xtype == NF90_BYTE .OR. xtype == NF90_SHORT .OR. &
      xtype == NF90_INT .OR. xtype == NF90_FLOAT .OR. xtype == NF90_DOUBLE
  END FUNCTION is_numeric_type

  SUBROUTINE require_coordinates(values,name,ncid)
    IMPLICIT NONE
    REAL, INTENT(IN) :: values(:,:)
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER, INTENT(IN) :: ncid
    REAL :: normalized
    INTEGER :: i,j
    DO j=1,SIZE(values,2)
      DO i=1,SIZE(values,1)
        normalized = values(i,j)
        IF (name == 'longitude') THEN
          IF (normalized < -180.0 .OR. normalized > 360.0) &
            CALL static_error('longitude coordinate outside [-180,360]',ncid)
          IF (normalized > 180.0) normalized = normalized - 360.0
        ELSE
          IF (normalized < -90.0 .OR. normalized > 360.0) &
            CALL static_error('latitude coordinate outside [-90,360]',ncid)
          IF (normalized > 270.0) normalized = normalized - 360.0
        END IF
        IF (name == 'latitude') THEN
          IF (normalized < -90.0 .OR. normalized > 90.0) &
            CALL static_error('latitude coordinate outside [-90,90]',ncid)
        ELSE
          IF (normalized < -180.0 .OR. normalized > 180.0) &
            CALL static_error('longitude coordinate outside [-180,180] after normalization',ncid)
        END IF
      END DO
    END DO
  END SUBROUTINE require_coordinates

  SUBROUTINE require_latitude_parameter(value,name,ncid)
    IMPLICIT NONE
    REAL, INTENT(IN) :: value
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER, INTENT(IN) :: ncid
    IF (value < -90.0 .OR. value > 90.0) &
      CALL static_error(TRIM(name)//' must be a latitude in [-90,90]',ncid)
  END SUBROUTINE require_latitude_parameter

  SUBROUTINE require_positive_finite(value,name,ncid)
    IMPLICIT NONE
    REAL, INTENT(IN) :: value
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER, INTENT(IN) :: ncid
    IF (.NOT.IEEE_IS_FINITE(value)) CALL static_error(TRIM(name)//' must be finite and positive',ncid)
    IF (value <= 0.0 .OR. value > HUGE(value)) CALL static_error(TRIM(name)//' must be finite and positive',ncid)
  END SUBROUTINE require_positive_finite

END MODULE laps_static
