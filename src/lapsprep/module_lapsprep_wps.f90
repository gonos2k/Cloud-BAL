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

MODULE lapsprep_wps

! PURPOSE
! =======
! Module to contain the various output routines needed for lapsprep
! to support initializition of WPS of the WRF model.
!
! SUBROUTINES CONTAINED
! =====================
! output_ungrib_format  - Used to support WRF initializations
! output_ungrib_header  - Writes the ungrib prep headers
! REMARKS
! =======
! 
!
! HISTORY
! =======
! 4 Dec 2000 -- Original -- Brent Shaw
! 10 JUL 2007 -- bellfe KMA/METRI 

  USE setup
  USE laps_static
  USE date_pack
  IMPLICIT NONE

  PRIVATE
  INTEGER, PARAMETER :: gp_version = 5
  REAL, PARAMETER    :: xfcst = 0.
  REAL, PARAMETER    :: earth_radius = 6371.229
  CHARACTER(LEN=32),PARAMETER :: source = &
     'LAPS ANALYSIS                   '
  CHARACTER (LEN=8), PARAMETER:: knownloc='SWCORNER'
  CHARACTER (LEN=24) :: hdate
  INTEGER            :: llflag
  CHARACTER (LEN=9)  :: field
  CHARACTER (LEN=25) :: units
  CHARACTER (LEN=46) :: desc 
  INTEGER, PARAMETER :: output_unit = 78
  REAL, PARAMETER    :: slp_level = 201300.0
  LOGICAL            :: wind_grid_relative

  PUBLIC output_ungrib_format
CONTAINS
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  SUBROUTINE output_ungrib_format(p, t, ht, u, v, rh, slp, psfc, &
                               lwc, rai, sno, ice, pic, snocov,tskin,istatus, &
                               resolved_output_file)

  !  Subroutine of lapsprep that will build a file the
  !  WRFSI "ungrib" format that can be read by hinterp

  IMPLICIT NONE

  ! Arguments
 
  REAL, INTENT(IN)                   :: p(:)        ! Pressure (hPa)
  REAL, INTENT(IN)                   :: t(:,:,:)    ! Temperature (K)
  REAL, INTENT(IN)                   :: ht(:,:,:)   ! Height (m)
  REAL, INTENT(IN)                   :: u(:,:,:)    ! U-wind (m s{-1})
  REAL, INTENT(IN)                   :: v(:,:,:)    ! V-wind (m s{-1})
  REAL, INTENT(IN)                   :: rh(:,:,:)   ! Relative Humidity (%)
  REAL, INTENT(IN)                   :: slp(:,:)    ! Sea-level Pressure (Pa)
  REAL, INTENT(IN)                   :: psfc(:,:)   ! Surface Pressure (Pa)
  REAL, INTENT(IN)                   :: lwc(:,:,:)  ! Cloud liquid (kg/kg)
  REAL, INTENT(IN)                   :: rai(:,:,:)  ! Rain (kg/kg)
  REAL, INTENT(IN)                   :: sno(:,:,:)  ! Snow (kg/kg)
  REAL, INTENT(IN)                   :: ice(:,:,:)  ! Ice (kg/kg)
  REAL, INTENT(IN)                   :: pic(:,:,:)  ! Graupel (kg/kg)
  REAL, INTENT(IN)                   :: snocov(:,:) ! Snow cover (fract)
  REAL, INTENT(IN)                   :: tskin(:,:)  ! Skin temperature
  INTEGER, INTENT(OUT)               :: istatus
  CHARACTER(LEN=*), INTENT(IN), OPTIONAL :: resolved_output_file
  
  ! Local Variables
  
  INTEGER            :: valid_mm, valid_dd
  CHARACTER (LEN=256):: output_file_name
  REAL, ALLOCATABLE  :: d2d(:,:)
  REAL, ALLOCATABLE  :: p_pa(:)
  INTEGER            :: k,yyyyddd,io_status,close_status,alloc_status
  LOGICAL            :: output_open

  istatus = 0
  output_open = .FALSE.
 
  ! Allocate a scratch 2d array
  ALLOCATE (d2d (x,y), STAT=alloc_status)
  IF (alloc_status .NE. 0) RETURN
  ALLOCATE (p_pa (z3+1), STAT=alloc_status)
  IF (alloc_status .NE. 0) GOTO 900
  ! Build the output file name
 
  yyyyddd = valid_yyyy*1000 + valid_jjj
  CALL wrf_date_to_ymd(yyyyddd, valid_yyyy, valid_mm, valid_dd) 
  WRITE(hdate, '(I4.4,"-",I2.2,"-",I2.2,"_",I2.2,":",I2.2,":00.0000")') &
          valid_yyyy, valid_mm, valid_dd, valid_hh, valid_min
! IF (valid_min .EQ. 0) THEN
!   output_file_name = TRIM(output_prefix) // ':' // hdate(1:13)
! ELSE
  IF (PRESENT(resolved_output_file)) THEN
    IF (LEN_TRIM(resolved_output_file)==0) GOTO 900
    output_file_name=TRIM(resolved_output_file)
  ELSE
    output_prefix = TRIM(laps_data_root)// '/lapsprd/lapsprep/wps/LAPS'
    output_file_name = TRIM(output_prefix) // ':' // hdate(1:16)
  END IF
! ENDIF
  ! Resolve all metadata before creating the output file.  A writer must not
  ! invent the coordinate system or leave an empty final-path artifact.
  IF      ( grid_type(1:8)  .EQ. 'mercator'                 ) THEN
    llflag = 1
  ELSE IF ( ( grid_type(1:24) .EQ. 'secant lambert conformal' ) .or. &
           ( grid_type(1:28) .EQ.  'tangential lambert conformal' ) )THEN
    llflag = 3
  ELSE IF ( grid_type(1:19) .EQ. 'polar stereographic'      ) THEN
    llflag = 5
  ELSE
    PRINT '(A,A,A)','Unknown map projection: ',TRIM(grid_type),'.'
    GOTO 900
  END IF
  SELECT CASE (TRIM(wind_coordinate))
    CASE ('GRID_RELATIVE')
      wind_grid_relative=.TRUE.
    CASE ('EARTH_RELATIVE')
      wind_grid_relative=.FALSE.
    CASE DEFAULT
      PRINT '(A,A)','Invalid WIND_COORDINATE: ',TRIM(wind_coordinate)
      GOTO 900
  END SELECT

  !  Open the file for sequential, unformatted output
  OPEN ( FILE   = TRIM(output_file_name)    , &
         UNIT   = output_unit        , &
         FORM   = 'UNFORMATTED' , &
         STATUS = 'REPLACE'     , &
         ACTION = 'WRITE'       , &
         ACCESS = 'SEQUENTIAL', IOSTAT=io_status )
  IF (io_status .NE. 0) GOTO 900
  output_open = .TRUE.

  ! Convert p levels from mb to Pascals

  p_pa = p * 100.

  print*, 'grid_type', grid_type

  PRINT *, 'GRIBPREP VERSION =', gp_version
  PRINT *, 'SOURCE = ', source
  PRINT *, 'HDATE = ',hdate
  PRINT *, 'XFCST = ', xfcst 
  PRINT *, 'NX = ', X
  PRINT *, 'NY = ', Y
  PRINT *, 'IPROJ = ', LLFLAG
  PRINT *, 'KNOWNLOC = ', knownloc
  PRINT *, 'STARTLAT = ',LA1
  PRINT *, 'STARTLON = ',LO1
  PRINT *, 'DX = ', DX
  PRINT *, 'DY = ', DY
  PRINT *, 'XLONC = ', LOV
  PRINT *, 'TRUELAT1 = ', LATIN1
  PRINT *, 'TRUELAT2 = ', LATIN2  

 ! Output temperature
  field = 'TT       '
  units = 'K                        '
  desc  = 'Temperature                                   '                
  PRINT *, 'FIELD = ', field
  PRINT *, 'UNITS = ', units
  PRINT *, 'DESC =  ',desc
  var_t : DO k = 1 , z3 + 1
    IF (( p_pa(k) .GT. 100100).AND.(p_pa(k).LT.200000) ) THEN
      CYCLE var_t
    ENDIF
    d2d = t(:,:,k)
    CALL write_ungrib_header(field,units,desc,p_pa(k),io_status)
    IF (io_status .NE. 0) GOTO 900
    WRITE ( output_unit,IOSTAT=io_status ) d2d
    IF (io_status .NE. 0) GOTO 900
    PRINT '(A,F9.1,A,F5.1,A,F5.1)','Level (Pa):',p_pa(k),' Min: ', &
           MINVAL(d2d),' Max: ', MAXVAL(d2d)
  ENDDO var_t

! var_uv : DO k = 1 , z3 + 1
  ! Do u-component of wind
  field = 'UU       '
  units = 'm s{-1}                  '
  desc = 'U                                             '
  PRINT *, 'FIELD = ', field
  PRINT *, 'UNITS = ', units
  PRINT *, 'DESC =  ',desc
  var_u : DO k = 1 , z3 + 1
    IF ( ( p_pa(k) .GT. 100100 ) .AND. ( p_pa(k) .LT. 200000 ) ) THEN
      CYCLE var_u
!     CYCLE var_uv
    END IF
    d2d = u(:,:,k)
    CALL write_ungrib_header(field,units,desc,p_pa(k),io_status)
    IF (io_status .NE. 0) GOTO 900
    WRITE ( output_unit,IOSTAT=io_status ) d2d
    IF (io_status .NE. 0) GOTO 900
    PRINT '(A,F9.1,A,F5.1,A,F5.1)', 'Level (Pa):', p_pa(k), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)
  ENDDO var_u

  ! Do v-component of wind
  field = 'VV       '
  units = 'm s{-1}                  '
  desc = 'V                                             '
  PRINT *, 'FIELD = ', field
  PRINT *, 'UNITS = ', units
  PRINT *, 'DESC =  ',desc
  var_v : DO k = 1 , z3 + 1
    IF ( ( p_pa(k) .GT. 100100 ) .AND. ( p_pa(k) .LT. 200000 ) ) THEN
      CYCLE var_v
!     CYCLE var_uv
    END IF
    d2d = v(:,:,k)
    CALL write_ungrib_header(field,units,desc,p_pa(k),io_status)
    IF (io_status .NE. 0) GOTO 900
    WRITE ( output_unit,IOSTAT=io_status ) d2d
    IF (io_status .NE. 0) GOTO 900
    PRINT '(A,F9.1,A,F5.1,A,F5.1)', 'Level (Pa):', p_pa(k), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)
  ENDDO var_v
! ENDDO var_uv

  ! Relative Humidity
  field = 'RH       '
  units = '%                        '
  desc  = 'Relative humidity                             '
  PRINT *, 'FIELD = ', field
  PRINT *, 'UNITS = ', units
  PRINT *, 'DESC =  ',desc
  var_rh : DO k = 1 , z3 + 1
    IF ( ( p_pa(k) .GT. 100100 ) .AND. ( p_pa(k) .LT. 200000 ) ) THEN
      CYCLE var_rh
    END IF
    d2d = rh(:,:,k)
    CALL write_ungrib_header(field,units,desc,p_pa(k),io_status)
    IF (io_status .NE. 0) GOTO 900
    WRITE ( output_unit,IOSTAT=io_status ) d2d
    IF (io_status .NE. 0) GOTO 900
    PRINT '(A,F9.1,A,F5.1,A,F5.1)', 'Level (Pa):', p_pa(k), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)
  ENDDO var_rh

  ! Do the heights
  field = 'HGT      '
  units = 'm                        '
  desc  = 'Height                                        '
  PRINT *, 'FIELD = ', field
  PRINT *, 'UNITS = ', units
  PRINT *, 'DESC =  ',desc
  var_ht : DO k = 1 , z3 + 1
    IF ( ( p_pa(k) .GT. 100100 ) .AND. ( p_pa(k) .LT. 200000 ) ) THEN
      CYCLE var_ht
    END IF
    d2d = ht(:,:,k)
    CALL write_ungrib_header(field,units,desc,p_pa(k),io_status)
    IF (io_status .NE. 0) GOTO 900
    WRITE ( output_unit,IOSTAT=io_status ) d2d
    IF (io_status .NE. 0) GOTO 900
    PRINT '(A,F9.1,A,F8.1,A,F8.1)', 'Level (Pa):', p_pa(k), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)
  ENDDO var_ht

  ! Terrain height
  field = 'HGT     '
  units = 'm                        '
  desc  = 'Height of topography                          '
  PRINT *, 'FIELD = ', field
  PRINT *, 'UNITS = ', units
  PRINT *, 'DESC =  ',desc
!!CALL write_ungrib_header(field,units,desc,p_pa(z3+1))
  d2d = ht(:,:,z3+1)
!!WRITE ( output_unit ) d2d
  PRINT '(A,F9.1,A,F9.1,A,F9.1)', 'Level (Pa):', p_pa(z3+1), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)

  ! Skin temperature
  field = 'SKINTEMP '
  units = 'K                        '
  desc  = 'Skin temperature                              '
  PRINT *, 'FIELD = ', field
  PRINT *, 'UNITS = ', units
  PRINT *, 'DESC =  ',desc
  CALL write_ungrib_header(field,units,desc,p_pa(z3+1),io_status)
  IF (io_status .NE. 0) GOTO 900
  WRITE ( output_unit,IOSTAT=io_status ) tskin
  IF (io_status .NE. 0) GOTO 900
  PRINT '(A,F9.1,A,F9.1,A,F9.1)', 'Level (Pa):', p_pa(z3+1), &
       ' Min: ', MINVAL(tskin), ' Max: ', MAXVAL(tskin)

  ! Sea-level Pressure field
  field = 'PMSL     '
  units = 'Pa                       '
  desc  = 'Sea-level pressure                            '
  PRINT *, 'FIELD = ', field
  PRINT *, 'UNITS = ', units
  PRINT *, 'DESC =  ',desc
  CALL write_ungrib_header(field,units,desc,slp_level,io_status)
  IF (io_status .NE. 0) GOTO 900
  WRITE ( output_unit,IOSTAT=io_status ) slp
  IF (io_status .NE. 0) GOTO 900
  PRINT '(A,F9.1,A,F9.1,A,F9.1)', 'Level (Pa):', slp_level, ' Min: ', MINVAL(slp),&
            ' Max: ', MAXVAL(slp)

  ! Surface Pressure field
  field = 'PSFC     '
  units = 'Pa                       '
  desc  = 'Surface pressure                              '
  PRINT *, 'FIELD = ', field
  PRINT *, 'UNITS = ', units
  PRINT *, 'DESC =  ',desc
  CALL write_ungrib_header(field,units,desc,p_pa(z3+1),io_status)
  IF (io_status .NE. 0) GOTO 900
  WRITE ( output_unit,IOSTAT=io_status ) psfc
  IF (io_status .NE. 0) GOTO 900
  PRINT '(A,F9.1,A,F9.1,A,F9.1)', 'Level (Pa):', p_pa(z3+1), ' Min: ', MINVAL(psfc),&
            ' Max: ', MAXVAL(psfc)

  IF (MINVAL(snocov).GE.0) THEN
    ! Water equivalent snow depth
    field = 'SNOWCOVR '
    units = '(DIMENSIONLESS)          '
    desc  = 'Snow cover flag                               '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc
!frl 2008.4.7 start
!   CALL write_ungrib_header(field,units,desc,p_pa(z3+1))
!frl 2008.4.7 end

    ! Conver from fraction to mask using namelist entry snow_thresh

    d2d =  0.
    WHERE(snocov .GE. snow_thresh) d2d = 1.0
!frl 2008.4.7 start
!   WRITE ( output_unit ) d2d
!frl 2008.4.7 end
    PRINT '(A,F9.1,A,F9.2,A,F9.2)', 'Level (Pa):', p_pa(z3+1), &
        ' Min: ', MINVAL(d2d),&
        ' Max: ', MAXVAL(d2d) 

  ENDIF

  ! Get cloud species if this is a hot start
  IF (hotstart) THEN
    field = 'QC       '     ! QLIQUID
    units = 'kg kg{-1}               '
    desc  = 'Cloud liquid water mixing ratio             '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc    
    var_lwc : DO k = 1 , z3
      IF ( ( p_pa(k) .GT. 100100 ) .AND. ( p_pa(k) .LT. 200000 ) ) THEN
        CYCLE var_lwc
      END IF
      d2d = lwc(:,:,k)
      CALL write_ungrib_header(field,units,desc,p_pa(k),io_status)
      IF (io_status .NE. 0) GOTO 900
      WRITE ( output_unit,IOSTAT=io_status ) d2d
      IF (io_status .NE. 0) GOTO 900
      PRINT '(A,F9.1,A,F8.6,A,F8.6)', 'Level (Pa):', p_pa(k), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)
    END DO var_lwc 

  ! surface QC for met.em 
    d2d = 0.0
    field = 'QC       '     ! QLIQUID
    units = 'kg kg{-1}               '
    desc  = 'Cloud liquid water mixing ratio             '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc
    CALL write_ungrib_header(field,units,desc,p_pa(z3+1),io_status)
    IF (io_status .NE. 0) GOTO 900
    WRITE ( output_unit,IOSTAT=io_status ) d2d
    IF (io_status .NE. 0) GOTO 900
    PRINT '(A,F9.1,A,F8.6,A,F8.6)', 'Level (Pa):', p_pa(z3+1), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)

    ! Cloud ice   
    field = 'QI       '     ! QICE
    units = 'kg kg{-1}               '
    desc  = 'Cloud ice mixing ratio                      '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc    
    var_ice: DO k = 1 , z3
      IF ( ( p_pa(k) .GT. 100100 ) .AND. ( p_pa(k) .LT. 200000 ) ) THEN
        CYCLE var_ice
      END IF
      d2d = ice(:,:,k)
      CALL write_ungrib_header(field,units,desc,p_pa(k),io_status)
      IF (io_status .NE. 0) GOTO 900
      WRITE ( output_unit,IOSTAT=io_status ) d2d
      IF (io_status .NE. 0) GOTO 900
      PRINT '(A,F9.1,A,F8.6,A,F8.6)', 'Level (Pa):', p_pa(k), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)
    END DO var_ice

    ! surface QI for met.em 
    d2d = 0.0
    field = 'QI       '     ! QICE
    units = 'kg kg{-1}               '
    desc  = 'Cloud ice mixing ratio             '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc
    CALL write_ungrib_header(field,units,desc,p_pa(z3+1),io_status)
    IF (io_status .NE. 0) GOTO 900
    WRITE ( output_unit,IOSTAT=io_status ) d2d
    IF (io_status .NE. 0) GOTO 900
    PRINT '(A,F9.1,A,F8.6,A,F8.6)', 'Level (Pa):', p_pa(z3+1), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)

    ! Cloud rain
    field = 'QR       '     ! QRAIN
    units = 'kg kg{-1}               '
    desc  = 'Rain water mixing ratio                     '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc    
    var_rai: DO k = 1 , z3
      IF ( ( p_pa(k) .GT. 100100 ) .AND. ( p_pa(k) .LT. 200000 ) ) THEN
        CYCLE var_rai
      END IF
      d2d = rai(:,:,k)
      CALL write_ungrib_header(field,units,desc,p_pa(k),io_status)
      IF (io_status .NE. 0) GOTO 900
      WRITE ( output_unit,IOSTAT=io_status ) d2d
      IF (io_status .NE. 0) GOTO 900
      PRINT '(A,F9.1,A,F8.6,A,F8.6)', 'Level (Pa):', p_pa(k), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)
    END DO var_rai


    ! surface QR for met.em 
    d2d = 0.0
    field = 'QR       '     ! QRAIN
    units = 'kg kg{-1}               '
    desc  = 'Rain water mixing ratio             '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc
    CALL write_ungrib_header(field,units,desc,p_pa(z3+1),io_status)
    IF (io_status .NE. 0) GOTO 900
    WRITE ( output_unit,IOSTAT=io_status ) d2d
    IF (io_status .NE. 0) GOTO 900
    PRINT '(A,F9.1,A,F8.6,A,F8.6)', 'Level (Pa):', p_pa(z3+1), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)

   ! Snow
    field = 'QS       '     ! QSNOW
    units = 'kg kg{-1}               '
    desc  = 'Snow mixing ratio                           '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc    
    var_sno: DO k = 1 , z3
      IF ( ( p_pa(k) .GT. 100100 ) .AND. ( p_pa(k) .LT. 200000 ) ) THEN
        CYCLE var_sno
      END IF
      d2d = sno(:,:,k)
      CALL write_ungrib_header(field,units,desc,p_pa(k),io_status)
      IF (io_status .NE. 0) GOTO 900
      WRITE ( output_unit,IOSTAT=io_status ) d2d
      IF (io_status .NE. 0) GOTO 900
      PRINT '(A,F9.1,A,F8.6,A,F8.6)', 'Level (Pa):', p_pa(k), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)
    END DO var_sno

    ! surface QS for met.em 
    d2d = 0.0
    field = 'QS       '     ! QSNOW
    units = 'kg kg{-1}               '
    desc  = 'Snow mixing ratio             '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc
    CALL write_ungrib_header(field,units,desc,p_pa(z3+1),io_status)
    IF (io_status .NE. 0) GOTO 900
    WRITE ( output_unit,IOSTAT=io_status ) d2d
    IF (io_status .NE. 0) GOTO 900
    PRINT '(A,F9.1,A,F8.6,A,F8.6)', 'Level (Pa):', p_pa(z3+1), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)

    ! Graupel
    field = 'QG       '     ! QGRAUPEL
    units = 'kg kg{-1}               '
    desc  = 'Graupel mixing ratio                        '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc    
    var_pic: DO k = 1 , z3
      IF ( ( p_pa(k) .GT. 100100 ) .AND. ( p_pa(k) .LT. 200000 ) ) THEN
        CYCLE var_pic
      END IF
      d2d = pic(:,:,k)
      CALL write_ungrib_header(field,units,desc,p_pa(k),io_status)
      IF (io_status .NE. 0) GOTO 900
      WRITE ( output_unit,IOSTAT=io_status ) d2d
      IF (io_status .NE. 0) GOTO 900
      PRINT '(A,F9.1,A,F8.6,A,F8.6)', 'Level (Pa):', p_pa(k), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)
    END DO var_pic

    ! surface QG for met.em 
    d2d = 0.0
    field = 'QG       '     ! QGRAUPEL
    units = 'kg kg{-1}               '
    desc  = 'Graupel mixing ratio             '
    PRINT *, 'FIELD = ', field
    PRINT *, 'UNITS = ', units
    PRINT *, 'DESC =  ',desc
    CALL write_ungrib_header(field,units,desc,p_pa(z3+1),io_status)
    IF (io_status .NE. 0) GOTO 900
    WRITE ( output_unit,IOSTAT=io_status ) d2d
    IF (io_status .NE. 0) GOTO 900
    PRINT '(A,F9.1,A,F8.6,A,F8.6)', 'Level (Pa):', p_pa(z3+1), ' Min: ', MINVAL(d2d),&
            ' Max: ', MAXVAL(d2d)

  ENDIF

  CLOSE (output_unit,IOSTAT=close_status)
  output_open = .FALSE.
  IF (close_status .NE. 0) GOTO 900
  istatus = 1

900 CONTINUE
  IF (output_open) CLOSE (output_unit,IOSTAT=close_status)
  IF (ALLOCATED(d2d)) DEALLOCATE (d2d)
  IF (ALLOCATED(p_pa)) DEALLOCATE (p_pa)
  RETURN
  END SUBROUTINE output_ungrib_format
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  SUBROUTINE write_ungrib_header(field,units,desc,level,istatus)
 
  ! Writes the ungrib header given the filed, units, description, and level

  IMPLICIT NONE
  CHARACTER(LEN=9), INTENT(IN)  :: field
  CHARACTER(LEN=25),INTENT(IN)  :: units
  CHARACTER(LEN=46),INTENT(IN)  :: desc
  REAL, INTENT(IN)              :: level
  INTEGER, INTENT(OUT)          :: istatus

  istatus = 0
  
  WRITE ( output_unit,IOSTAT=istatus ) gp_version
  IF (istatus .NE. 0) RETURN
  WRITE ( output_unit,IOSTAT=istatus ) hdate,xfcst,source,field,units,desc,level,x,y,llflag
  IF (istatus .NE. 0) RETURN
  SELECT CASE (llflag)
    CASE(1)
      WRITE ( output_unit,IOSTAT=istatus ) knownloc,la1,lo1,dx,dy,latin1
    CASE(3)
      WRITE ( output_unit,IOSTAT=istatus ) knownloc,la1,lo1,dx,dy,lov,latin1,latin2, earth_radius
    CASE(5)
      WRITE ( output_unit,IOSTAT=istatus ) knownloc,la1,lo1,dx,dy,lov,latin1
    CASE DEFAULT
      istatus = -1
  END SELECT
  IF (istatus .NE. 0) RETURN
!     WRITE ( output_unit ) .FALSE. 
      WRITE ( output_unit,IOSTAT=istatus ) wind_grid_relative

  END SUBROUTINE write_ungrib_header
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
END MODULE lapsprep_wps
  
