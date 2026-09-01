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
 
  PROGRAM lapsprep   
    !
    ! PURPOSE
    ! =======
    ! Prepares LAPS analysis data for ingest by various NWP model pre-processors.
    ! Currently supports MM5V3 (outputs PREGRID v3 format), WRF (outputs 
    ! gribprep format), and RAMS 4.3 (outputs RALPH2 format).   
    !
    ! ARGUMENTS
    ! =========
    !  LAPS_valid_time   - Optional command line argument of form YYJJJHHMM
    !                      specifying time for which to build output
    !                      If not present, the program will use the latest
    !                      available analysis based on LAPS systime.dat
    !
    ! REMARKS
    ! =======
    !  1. You must set the LAPS_DATA_ROOT environment variable before running.
    !  2. Other program controls in lapsprep.nl
    !
    ! HISTORY
    ! =======
    ! 28 Nov 2000 -- Original -- Brent Shaw 
    !    (based on lapsreader program originally developed by Dave Gill of
    !     NCAR to support MM5)

    ! Module declarations

    USE constants
    USE setup
    USE laps_static
    USE lapsprep_mm5
    USE lapsprep_wrf
    USE lapsprep_wps
    USE lapsprep_rams
    USE lapsprep_netcdf
    USE cloud_bal_field_contracts
    USE cloud_bal_moisture, ONLY: transfer_excess
    USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite

    ! Variable Declarations

    IMPLICIT NONE

    ! Declarations for use of NetCDF library

    INCLUDE "netcdf.inc" 
    INTEGER :: cdfid , rcode
    INTEGER :: zid
    INTEGER :: z 
    INTEGER , DIMENSION(4) :: start , count
    INTEGER , DIMENSION(2) :: startc, countc
    INTEGER :: vid
    CHARACTER (LEN=132) :: dum 

    ! Arrays for data
    REAL , ALLOCATABLE , DIMENSION (:,:,:) :: u , v , t , rh , ht, &   
                                             lwc,rai,sno,pic,ice, sh, mr, w, & 
                                             virtual_t, rho,lcp
    REAL , ALLOCATABLE , DIMENSION (:,:)   :: slp , psfc, snocov, d2d,tskin
    REAL , ALLOCATABLE , DIMENSION (:)     :: p
    REAL , PARAMETER                       :: tiny = 1.0e-30
    
    ! Miscellaneous local variables
                                        
    INTEGER :: out_loop, loop , var_loop , i, j, k, kbot,istatus
    CHARACTER(LEN=256) :: cloud_bal_wps_output
    LOGICAL :: file_present
    REAL    :: rhmod, shmod
    REAL    :: rhadj
    REAL    :: lwc_limit
    REAL    :: hydrometeor_scale
    INTEGER :: transfer_status, species
    TYPE(field_contract) :: hydro_field(5)
    TYPE(field_contract) :: input_field(5,num_ext)
    TYPE(field_contract) :: pressure_field

    ! Some stuff for JAX to handle lga problem
    ! with constant mr above 300
    LOGICAL :: jaxsbn
    REAL  :: weight_top, weight_bot, newsh
    REAL, EXTERNAL ::make_rh 
    INTEGER :: k300
    jaxsbn = .false.
     
    ! Beginning of code

    ! Check for command line argument containing LAPS valid time
    ! (in YYJJJHHMM format).  If not present, use the systime.dat
    ! file to get current time.  Note that on HPUX, argument #1
    ! is the executable name and argument #2 is the first actual
    ! argument, unlike other systems.  There is a corrected kludge
    ! for that here.
    CALL GETARG(1,laps_file_time)
    IF (laps_file_time .EQ. 'lapsprep.') THEN 
      ! Must be an HP!
      CALL GETARG(2,laps_file_time)
      IF (laps_file_time .EQ. '         ') THEN
        CALL get_systime(i4time,laps_file_time,istatus)
      ENDIF
    ELSE IF (laps_file_time .EQ. '         ') THEN  
     CALL get_systime(i4time, laps_file_time, istatus)
    ENDIF
    PRINT *, 'LAPS_FILE_TIME = ', laps_file_time
    READ(laps_file_time, '(I2.2,I3.3,I2.2,I2.2)') valid_yyyy, valid_jjj, &
                                                   valid_hh, valid_min
    IF (valid_yyyy.LT.80) THEN
      valid_yyyy = 2000 + valid_yyyy
    ELSE
      valid_yyyy = 1900 + valid_yyyy
    ENDIF
    PRINT '(2A)', 'Running LAPSPREP using A9_time of: ', laps_file_time
  
    ! Get the LAPS_DATA_ROOT from the environment.  

    CALL GETENV('LAPS_DATA_ROOT', laps_data_root)
    PRINT '(2A)', 'LAPS_DATA_ROOT=',laps_data_root

    !  Get the namelist items (from the setup module).

    CALL read_namelist

    ! Get the static information (projection, dimensions,etc.)
 
    PRINT '(A)', 'Getting horizontal grid specs from static file.'
    CALL get_horiz_grid_spec(laps_data_root)

    ! Now that we have LAPS grid info, set up the hydrometeor scaling
    ! factor, which scales the concentrations of hydormeteors for this
    ! grid spacing.  We assume the values from LAPS are approprate on
    ! a grid with radar scaling (approx. 2km)

    SELECT CASE (TRIM(grid_scale))
      CASE ('NONE')
        hydrometeor_scale = 1.0
      CASE ('LEGACY_2KM')
        hydrometeor_scale = 2./dx  ! dx is in km
      CASE DEFAULT
        PRINT *, 'Unsupported GRID_SCALE: ',TRIM(grid_scale)
        STOP 'invalid_grid_scale'
    END SELECT

    !  Loop through each of the requested extensions for this date.  Each of the
    !  extensions has a couple of the variables that we want.

    PRINT '(A)', 'Starting Loop for each LAPS file'
    file_loop : DO loop = 1 , num_ext
      
      PRINT *, 'Looking for ',ext(loop)
      !  If this is a microphysical species but not doing 
      !  a hotstart, then cycle over this file.

      IF (((TRIM(ext(loop)).EQ.'lwc').OR.(TRIM(ext(loop)).EQ.'lcp')) .AND. &
          (.NOT.hotstart) ) THEN
        CYCLE file_loop
      ENDIF

      !  Build the input file name.   the input file.

      IF ((TRIM(ext(loop)) .NE. 'lw3' ).AND. &
          (TRIM(ext(loop)) .NE. 'lt1' ).AND. &
          (TRIM(ext(loop)) .NE. 'lq3' ).AND. &
          (TRIM(ext(loop)) .NE. 'lh3' )) THEN
        input_laps_file = TRIM(laps_data_root) //'/lapsprd/' // &
            TRIM(ext(loop)) // '/' // laps_file_time // '.' // &
            TRIM(ext(loop))
      ELSE
        IF (balance) THEN
          input_laps_file = TRIM(laps_data_root) //'/lapsprd/balance/' // &
          TRIM(ext(loop)) // '/' // laps_file_time // '.' // &
          TRIM(ext(loop))
        ELSE
          input_laps_file = TRIM(laps_data_root) //'/lapsprd/' // &
              TRIM(ext(loop)) // '/' // laps_file_time // '.' // &
              TRIM(ext(loop)) 
        ENDIF
      ENDIF
      PRINT *, 'Opening: ', input_laps_file

      ! Determine if the file exists

      INQUIRE (FILE=TRIM(input_laps_file), EXIST=file_present)
      IF (.NOT.file_present) THEN
        IF( (ext(loop).EQ.'lt1').OR. &
            (ext(loop).EQ.'lw3').OR. &
            (ext(loop).EQ.'lh3').OR. &
            (ext(loop).EQ.'lsx') ) THEN 
          PRINT '(A)', 'Mandatory file not available:' ,input_laps_file
          STOP 'not_enough_data'
        ELSE IF ( (ext(loop).EQ.'lq3') .OR. &
               (ext(loop).EQ.'lwc') ) THEN
          PRINT '(A)', 'File not available, cannot do hotstart.'
          hotstart = .false.
          CYCLE file_loop
        ELSE IF (ext(loop).EQ.'l1s') THEN
          PRINT '(A)', 'File not available, cannot do snowcover.'
          CYCLE file_loop
        ELSE
          PRINT '(A)', 'File not available, but not mandatory.'
          CYCLE file_loop
        ENDIF
      ENDIF

      ! Open the netcdf file and get the vertical dimension

      cdfid = NCOPN ( TRIM(input_laps_file) , NCNOWRIT , rcode )
      IF (rcode .NE. 0) THEN
        PRINT *, 'NetCDF open failed/status: ',TRIM(input_laps_file),rcode
        STOP 'input_open_failed'
      ENDIF

      zid = NCDID ( cdfid , 'z' , rcode )
      IF (rcode .NE. 0) STOP 'missing_z_dimension'
      CALL NCDINQ ( cdfid , zid , dum , z , rcode )
      IF (rcode .NE. 0 .OR. z .LE. 0) STOP 'invalid_z_dimension'

      IF ( ( ext(loop) .EQ. 'lsx' ) .OR. &
           ( ext(loop) .EQ. 'lm2') ) THEN
         z2 = z
      ELSE
         z3 = z
      END IF
      
      IF ( loop .EQ. 1 ) THEN

      ! ALLOCATE space for all of the variables in this data set.  Note
      ! that some ofthe 3d variables are allocated by z+1 instead of just z, as
      ! we are going to put the surface values into these arrays as well.

        ALLOCATE ( u   ( x , y , z3 + 1 ) )
        ALLOCATE ( v   ( x , y , z3 + 1 ) )
        ALLOCATE ( w   ( x , y , z3 + 1 ) )
        ALLOCATE ( t   ( x , y , z3 + 1 ) )
        ALLOCATE ( rh  ( x , y , z3 + 1 ) )
        ALLOCATE ( ht  ( x , y , z3 + 1 ) )
        ALLOCATE ( slp ( x , y         ) )
        ALLOCATE ( psfc (x , y         ) )
        ALLOCATE ( d2d ( x , y         ) )
        ALLOCATE ( tskin ( x , y       ) )
        ALLOCATE ( p   (         z3 + 1 ) ) 
        ! The following variables are not "mandatory"
        ALLOCATE ( lwc ( x , y , z3 ) ) 
        ALLOCATE ( rai ( x , y , z3 ) ) 
        ALLOCATE ( sno ( x , y , z3 ) ) 
        ALLOCATE ( pic ( x , y , z3 ) ) 
        ALLOCATE ( ice ( x , y , z3 ) )
        ALLOCATE ( snocov ( x , y ) ) 
        ALLOCATE ( lcp ( x , y , z3 ) ) 
        ! The following variables are only used
        ! for converting non-mandatory cloud variables
        ! to mixing ratio values 
        ALLOCATE ( rho ( x , y , z3 ) )
        ALLOCATE ( virtual_t ( x , y , z3 ) )
        ALLOCATE ( sh ( x , y , z3 ) )
        ALLOCATE ( mr ( x , y , z3+1 ) )

        ! Initialize every array before the first read.  Optional physical
        ! arrays use zero only as storage; the field contracts below retain
        ! the distinction between an absent value and a valid physical zero.
        u(:,:,:) = missingflag
        v(:,:,:) = missingflag
        w(:,:,:) = missingflag
        t(:,:,:) = missingflag
        rh(:,:,:) = missingflag
        ht(:,:,:) = missingflag
        sh(:,:,:) = missingflag
        mr(:,:,:) = missingflag
        slp(:,:) = missingflag
        psfc(:,:) = missingflag
        d2d(:,:) = missingflag
        tskin(:,:) = missingflag
        p(:) = missingflag
        lwc(:,:,:) = 0.
        rai(:,:,:) = 0.
        sno(:,:,:) = 0.
        pic(:,:,:) = 0.
        ice(:,:,:) = 0.
        snocov(:,:) = 0.
        lcp(:,:,:) = 0.

        CALL initialize_field_contract(hydro_field(1),'cloud_liquid', &
             laps_file_time,'kg m-3',x,y,z3,SOURCE_CLOUD)
        CALL initialize_field_contract(hydro_field(2),'rain', &
             laps_file_time,'kg m-3',x,y,z3,SOURCE_RADAR_3D)
        CALL initialize_field_contract(hydro_field(3),'snow', &
             laps_file_time,'kg m-3',x,y,z3,SOURCE_RADAR_3D)
        CALL initialize_field_contract(hydro_field(4),'cloud_ice', &
             laps_file_time,'kg m-3',x,y,z3,SOURCE_CLOUD)
        CALL initialize_field_contract(hydro_field(5),'graupel', &
             laps_file_time,'kg m-3',x,y,z3,SOURCE_RADAR_3D)
      END IF

      IF       ( ext(loop) .EQ. 'lh3' ) THEN

        ! Loop over the number of variables for this data file.

        var_lh3 : DO var_loop = 1 , num_cdf_var(loop)

          ! Get the variable ID.

          vid = NCVID ( cdfid , TRIM(cdf_var_name(var_loop,loop)) , rcode )
          start = (/ 1 , 1 , 1 , 1 /)
          count = (/ x , y , z , 1 /)
          CALL NCVGT ( cdfid , vid , start , count , rh , rcode )
          CALL initialize_field_contract(input_field(var_loop,loop),'RH', &
               laps_file_time,'percent',x,y,z,SOURCE_MODEL)
          CALL capture_field_validity(input_field(var_loop,loop),rh,rcode, &
                                      0.0,200.0,missingflag)
          IF (enforce_field_contracts .AND. &
              input_field(var_loop,loop)%status .NE. FIELD_OK) &
            STOP 'invalid_rh_field'

          !  Do this just once for pressure.

          vid = NCVID ( cdfid , 'level' , rcode )

          CALL NCVGT ( cdfid , vid , 1 , z3 , p , rcode )
          IF (rcode .NE. 0) STOP 'pressure_levels_read_failed'
          CALL initialize_field_contract(pressure_field,'LEVEL', &
               laps_file_time,'hPa',z3,1,1,SOURCE_MODEL)
          CALL capture_field_validity(pressure_field,p(1:z3),rcode, &
                                      1.0,1100.0,missingflag)
          IF (pressure_field%status .NE. FIELD_OK) &
            STOP 'invalid_pressure_levels'
          IF (ANY(p(2:z3) .GE. p(1:z3-1))) &
            STOP 'nonmonotonic_pressure_levels'
 
          ! Set the pressure level of the lowest level of our
          ! pressure array as 2001 mb to flag the surface
          p(z3+1) = 2001

        END DO var_lh3 

      ELSE IF ( ext(loop) .EQ. 'lq3' )THEN

        !  Loop over the number of variables for this data file.
        var_lq3 : DO var_loop = 1 , num_cdf_var(loop)

          !  Get the variable ID.

          vid = NCVID ( cdfid , TRIM(cdf_var_name(var_loop,loop)) , rcode )
          start = (/ 1 , 1 , 1 , 1 /)
          count = (/ x , y , z , 1 /)
          CALL NCVGT ( cdfid , vid , start , count , sh , rcode )
          CALL initialize_field_contract(input_field(var_loop,loop),'SH', &
               laps_file_time,'kg kg-1',x,y,z,SOURCE_MODEL)
          CALL capture_field_validity(input_field(var_loop,loop),sh,rcode, &
                                      0.0,0.2,missingflag)
          IF (enforce_field_contracts .AND. &
              input_field(var_loop,loop)%status .NE. FIELD_OK) &
            STOP 'invalid_sh_field'

        END DO var_lq3

      ELSE IF ( ext(loop) .EQ. 'lsx' ) THEN

        !  Loop over the number of variables for this data file.

        var_lsx : DO var_loop = 1 , num_cdf_var(loop)

          !  Get the variable ID.

          vid = NCVID ( cdfid , TRIM(cdf_var_name(var_loop,loop)) , rcode )
          start = (/ 1 , 1 , 1 , 1 /)
          count = (/ x , y , 1 , 1 /)

          IF      ( cdf_var_name(var_loop,loop) .EQ. 'u  ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , u  (1,1,z3+1) , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'U_SFC', &
                 laps_file_time,'m s-1',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop), &
                 u(:,:,z3+1),rcode,-200.0,200.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'v  ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , v  (1,1,z3+1) , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'V_SFC', &
                 laps_file_time,'m s-1',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop), &
                 v(:,:,z3+1),rcode,-200.0,200.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'vv ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , w  (1,1,z3+1) , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'W_SFC', &
                 laps_file_time,'m s-1',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop), &
                 w(:,:,z3+1),rcode,-100.0,100.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 't  ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , t  (1,1,z3+1) , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'T_SFC', &
                 laps_file_time,'K',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop), &
                 t(:,:,z3+1),rcode,150.0,350.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'rh ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , rh (1,1,z3+1) , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'RH_SFC', &
                 laps_file_time,'percent',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop), &
                 rh(:,:,z3+1),rcode,0.0,200.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'mr ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , mr (1,1,z3+1) , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'MR_SFC', &
                 laps_file_time,'g kg-1',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop), &
                 mr(:,:,z3+1),rcode,0.0,100.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'msl' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , slp           , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'MSLP', &
                 laps_file_time,'Pa',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),slp,rcode, &
                                        10000.0,120000.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'ps ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , psfc          , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'PSFC', &
                 laps_file_time,'Pa',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),psfc,rcode, &
                                        10000.0,120000.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'tgd') THEN
            CALL NCVGT ( cdfid , vid , start , count , tskin         , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'TSKIN', &
                 laps_file_time,'K',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),tskin,rcode, &
                                        150.0,350.0,missingflag)
          END IF
          IF (enforce_field_contracts .AND. &
              input_field(var_loop,loop)%status .NE. FIELD_OK) &
            STOP 'invalid_surface_field'

        END DO var_lsx

        ! Convert sfc mixing ratio from g/kg to kg/kg.

        mr(:,:,z3+1)=mr(:,:,z3+1)*0.001

      ELSE IF ( ext(loop) .EQ. 'lm2' ) THEN

        var_l1s : DO var_loop = 1 , num_cdf_var(loop)

          !  Get the variable ID.

          vid = NCVID ( cdfid , TRIM(cdf_var_name(var_loop,loop)) , rcode )
          start = (/ 1 , 1 , 1 , 1 /)
          count = (/ x , y , 1 , 1 /)

          IF      ( cdf_var_name(var_loop,loop) .EQ. 'sc ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , snocov        , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'SNOCOV', &
                 laps_file_time,'1',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),snocov,rcode, &
                                        0.0,1.0,missingflag)
          END IF

        END DO var_l1s                             
        
      ELSE IF ( ext(loop) .EQ. 'lt1' ) THEN

        !  Loop over the number of variables for this data file.

        var_lt1 : DO var_loop = 1 , num_cdf_var(loop)

          !  Get the variable ID.

          vid = NCVID ( cdfid , TRIM(cdf_var_name(var_loop,loop)) , rcode )
          start = (/ 1 , 1 , 1 , 1 /)
          count = (/ x , y , z , 1 /)
          IF      ( cdf_var_name(var_loop,loop) .EQ. 't3 ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , t  , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'T3', &
                 laps_file_time,'K',x,y,z,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),t,rcode, &
                                        150.0,350.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'ht ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , ht , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'HT', &
                 laps_file_time,'m',x,y,z,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),ht,rcode, &
                                        -1000.0,100000.0,missingflag)
          END IF
          IF (enforce_field_contracts .AND. &
              input_field(var_loop,loop)%status .NE. FIELD_OK) &
            STOP 'invalid_lt1_field'

        END DO var_lt1

      ELSE IF ( ext(loop) .EQ. 'lw3' ) THEN

        !  Loop over the number of variables for this data file.

        var_lw3 : DO var_loop = 1 , num_cdf_var(loop)

          !  Get the variable ID.

          vid = NCVID ( cdfid , TRIM(cdf_var_name(var_loop,loop)) , rcode )
          start = (/ 1 , 1 , 1 , 1 /)
          count = (/ x , y , z , 1 /)
          IF      ( cdf_var_name(var_loop,loop) .EQ. 'u3 ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , u , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'U3', &
                 laps_file_time,'m s-1',x,y,z,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),u,rcode, &
                                        -200.0,200.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'v3 ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , v , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'V3', &
                 laps_file_time,'m s-1',x,y,z,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),v,rcode, &
                                        -200.0,200.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'om ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , w , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'OM', &
                 laps_file_time,'Pa s-1',x,y,z,SOURCE_CLOUD)
            CALL capture_field_validity(input_field(var_loop,loop),w,rcode, &
                                        -100.0,100.0,missingflag)
          END IF
          IF (enforce_field_contracts .AND. &
              input_field(var_loop,loop)%status .NE. FIELD_OK) &
            STOP 'invalid_lw3_field'

        END DO var_lw3

      ELSE IF (( ext(loop) .EQ. 'lwc' ).AND.(hotstart)) THEN

        !  Loop over the number of variables for this data file.

        var_lwc1 : DO var_loop = 1 , num_cdf_var(loop)

          !  Get the variable ID.

          vid = NCVID ( cdfid , TRIM(cdf_var_name(var_loop,loop)) , rcode )
          start = (/ 1 , 1 , 1 , 1 /)
          count = (/ x , y , z , 1 /)
          IF      ( cdf_var_name(var_loop,loop) .EQ. 'lwc' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , lwc, rcode )
            CALL capture_field_validity(hydro_field(1),lwc,rcode, &
                                        0.0,100.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'rai' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , rai , rcode )
            CALL capture_field_validity(hydro_field(2),rai,rcode, &
                                        0.0,100.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'sno' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , sno , rcode ) 
            CALL capture_field_validity(hydro_field(3),sno,rcode, &
                                        0.0,100.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'ice' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , ice , rcode ) 
            CALL capture_field_validity(hydro_field(4),ice,rcode, &
                                        0.0,100.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'pic' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , pic , rcode ) 
            CALL capture_field_validity(hydro_field(5),pic,rcode, &
                                        0.0,100.0,missingflag)
          END IF

        END DO var_lwc1    

      ELSE IF (( ext(loop) .EQ. 'lcp' ).AND.(hotstart)) THEN

        !  Loop over the number of variables for this data file.

        var_lvc : DO var_loop = 1 , num_cdf_var(loop)

          !  Get the variable ID.

          vid = NCVID ( cdfid , TRIM(cdf_var_name(var_loop,loop)) , rcode )
          start = (/ 1 , 1 , 1 , 1 /)
          count = (/ x , y , z , 1 /)
          IF      ( cdf_var_name(var_loop,loop) .EQ. 'lcp' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , lcp, rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'LCP', &
                 laps_file_time,'1',x,y,z,SOURCE_CLOUD)
            CALL capture_field_validity(input_field(var_loop,loop),lcp,rcode, &
                                        0.0,1.0,missingflag)
            WHERE (.NOT. input_field(var_loop,loop)%valid) lcp=0.0
            print *, 'Got cloud cover...min/max = ',minval(lcp),maxval(lcp)
          END IF

        END DO var_lvc  

      END IF

    END DO file_loop

    DO loop=1,num_ext
      DO var_loop=1,num_cdf_var(loop)
        IF (ALLOCATED(input_field(var_loop,loop)%valid)) THEN
          PRINT *, 'Input contract ',TRIM(input_field(var_loop,loop)%name), &
                   ' time/dims/units/status/valid = ', &
                   TRIM(input_field(var_loop,loop)%valid_time), &
                   input_field(var_loop,loop)%nx, &
                   input_field(var_loop,loop)%ny, &
                   input_field(var_loop,loop)%nz, &
                   TRIM(input_field(var_loop,loop)%units), &
                   input_field(var_loop,loop)%status, &
                   valid_fraction(input_field(var_loop,loop))
        ENDIF
      ENDDO
    ENDDO

    ! Compute mixing ratio from spec hum.
    ! Fill missing values with sfc value.

    k300 = 0
    do k= 1,z3
      if (p(k) .eq. 300.) k300 = k
    enddo
    if (k300 .eq. 0) THEN
      print *, "Could not find k300!"
      stop
    endif
    do k=1,z3
    do j=1,y
    do i=1,x

      if ((jaxsbn).and.(p(k).LT.300.)) then
           weight_bot = (p(k) - 50) / (250)
           weight_top = 1.0 - weight_bot
           newsh = weight_bot * sh(i,j,k300) + &
                       weight_top * tiny 
               
           newsh = MIN(sh(i,j,k),newsh)
            
           ! Make sure sh does not exceed 
           ! ice saturation value
           CALL saturate_ice_points(t(i,j,k), &
                                    p(k),1.0, &
                                    shmod,rhmod)
           sh(i,j,k) = MIN(shmod, newsh)
           rh(i,j,k) = make_rh(p(k),t(i,j,k)-273.15, &
             sh(i,j,k)*1000., -132.) * 100.
      endif
     
      if (sh(i,j,k) .ge. 0. .and. sh(i,j,k) .lt. 1.) then
        mr(i,j,k)=sh(i,j,k)/(1.-sh(i,j,k))
      else
        mr(i,j,k)=mr(i,j,z3+1)
      endif
!      if (u(i,j,k) .eq. 1.e-30 .or. abs(u(i,j,k)) .gt. 200.) u(i,j,k)=u(i,j,z3+1)
!     if (v(i,j,k) .eq. 1.e-30 .or. abs(v(i,j,k)) .gt. 200.) v(i,j,k)=v(i,j,z3+1)
    enddo
    enddo
    enddo

    !  Set the lowest level of the geopotential height to topographic height

    ht(:,:,z3+1) = topo 

    IF (hotstart) THEN

      ! If this is a hot start, then we need to convert the microphysical
      ! species from mass per volume to mass per mass (mixing ratio).  This
      ! requires that we compute the air density from virtual temperature
      ! and divide each species by the air density.
       
      ! Compute virtual temperature from mixing ratio and temperature
      virtual_t(:,:,:)=( 1. + 0.61*mr(:,:,1:z3))*t(:,:,1:z3)
 
      ! Compute density from virtual temperature and gas constant for dry air
      DO k = 1, z3
        rho(:,:,k) = p(k)*100. / (rdry * virtual_t(:,:,k))
      ENDDO

      ! Apply cell-level validity.  One malformed cell no longer invalidates
      ! an entire species and an absent field remains visible in its contract.
      WHERE (.NOT. hydro_field(1)%valid) lwc = 0.0
      WHERE (.NOT. hydro_field(2)%valid) rai = 0.0
      WHERE (.NOT. hydro_field(3)%valid) sno = 0.0
      WHERE (.NOT. hydro_field(4)%valid) ice = 0.0
      WHERE (.NOT. hydro_field(5)%valid) pic = 0.0

      lwc = MAX(0.0,lwc) * hydrometeor_scale
      rai = MAX(0.0,rai) * hydrometeor_scale
      sno = MAX(0.0,sno) * hydrometeor_scale
      ice = MAX(0.0,ice) * hydrometeor_scale
      pic = MAX(0.0,pic) * hydrometeor_scale

      IF (TRIM(cap_policy) .EQ. 'TRANSFER') THEN
        DO k=1,z3
          DO j=1,y
            DO i=1,x
              CALL transfer_excess(lwc(i,j,k),rai(i,j,k), &
                                   autoconv_lwc2rai,transfer_status)
              IF (transfer_status .NE. 1) STOP 'liquid_transfer_failed'
              CALL transfer_excess(ice(i,j,k),sno(i,j,k), &
                                   autoconv_ice2sno,transfer_status)
              IF (transfer_status .NE. 1) STOP 'ice_transfer_failed'
            ENDDO
          ENDDO
        ENDDO
      ELSE IF (TRIM(cap_policy) .NE. 'KEEP') THEN
        PRINT *, 'Unsupported CAP_POLICY: ',TRIM(cap_policy)
        STOP 'invalid_cap_policy'
      ENDIF

      ! Concentration (kg m-3) to dry-air mixing ratio (kg kg-1).
      DO k=1,z3
        DO j=1,y
          DO i=1,x
            IF (ieee_is_finite(rho(i,j,k)) .AND. rho(i,j,k) .GT. 0.0) THEN
              lwc(i,j,k)=lwc(i,j,k)/rho(i,j,k)
              rai(i,j,k)=rai(i,j,k)/rho(i,j,k)
              sno(i,j,k)=sno(i,j,k)/rho(i,j,k)
              ice(i,j,k)=ice(i,j,k)/rho(i,j,k)
              pic(i,j,k)=pic(i,j,k)/rho(i,j,k)
            ELSE
              lwc(i,j,k)=0.0; rai(i,j,k)=0.0; sno(i,j,k)=0.0
              ice(i,j,k)=0.0; pic(i,j,k)=0.0
              DO species=1,5
                hydro_field(species)%valid(i,j,k)=.FALSE.
              ENDDO
            ENDIF
          ENDDO
        ENDDO
      ENDDO

      IF (TRIM(hydro_mode) .NE. 'CONSERVATIVE') THEN
        PRINT *, 'Unsupported HYDRO_MODE: ',TRIM(hydro_mode)
        STOP 'invalid_hydro_mode'
      ENDIF
      IF (lwc2vapor_thresh .GT. 0.) THEN
        PRINT *, 'Legacy water-only saturation adjustment is disabled.'
        STOP 'canonical_water_enthalpy_adjustment_not_linked'
      ENDIF

      DO species=1,5
        CALL refresh_field_status(hydro_field(species))
        PRINT *, 'Hydrometeor contract ',TRIM(hydro_field(species)%name), &
                 ' status/fraction = ',hydro_field(species)%status, &
                 valid_fraction(hydro_field(species))
      ENDDO
      IF (ANY(.NOT. ieee_is_finite(lwc)) .OR. MINVAL(lwc) .LT. 0.0 .OR. &
          ANY(.NOT. ieee_is_finite(ice)) .OR. MINVAL(ice) .LT. 0.0 .OR. &
          ANY(.NOT. ieee_is_finite(rai)) .OR. MINVAL(rai) .LT. 0.0 .OR. &
          ANY(.NOT. ieee_is_finite(sno)) .OR. MINVAL(sno) .LT. 0.0 .OR. &
          ANY(.NOT. ieee_is_finite(pic)) .OR. MINVAL(pic) .LT. 0.0) THEN
        STOP 'invalid_hydrometeor_output'
      ENDIF

      ! Vapor changes alter virtual temperature and density.  Recompute the
      ! density used by the omega-to-w conversion after all paired transfers.
      virtual_t(:,:,:)=(1.0+0.61*mr(:,:,1:z3))*t(:,:,1:z3)
      DO k=1,z3
        rho(:,:,k)=p(k)*100.0/(rdry*virtual_t(:,:,k))
      ENDDO
      IF (ANY(.NOT. ieee_is_finite(rho)) .OR. MINVAL(rho) .LE. 0.0) THEN
        STOP 'invalid_post_transfer_density'
      ENDIF

      ! Convert 3d omega from Pa/s to m/s, or fill with sfc value if missing.

      do k=1,z3
      do j=1,y
      do i=1,x
        if (w(i,j,k) .eq. 1.e-30 .or. abs(w(i,j,k)) .gt. 100.) then
          w(i,j,k)=w(i,j,z3+1)
        else
          w(i,j,k)=-w(i,j,k)/(rho(i,j,k)*g)
        endif
      enddo
      enddo
      enddo


    ENDIF
  
    ! If make_sfc_uv set, then replace surface winds with 
    ! winds interpolated from the 3D field.
    IF (make_sfc_uv) THEN
      PRINT *, 'Creating surface u/v from 3D field...'
      DO j = 1,y
        DO i = 1,x
          kbot = 0
          get_lowest: DO k = z3,1,-1
            IF (ht(i,j,k) .GT. topo(i,j)) THEN
              kbot = k
              EXIT get_lowest
            ENDIF
          ENDDO get_lowest
          IF (kbot .NE. 0) THEN
            u(i,j,z3+1) = u(i,j,kbot)
            v(i,j,z3+1) = v(i,j,kbot)
          ELSE
            print *, 'Problem finding kbot.'
            STOP
          ENDIF
        ENDDO
      ENDDO
  
    ENDIF

    ! Loop over the each desired output format

    DO out_loop = 1, num_output
      ! Now it is time to output these arrays.  The arrays are ordered
      !  as (x,y,z).  The origin is the southwest corner at the top of the 
      ! atmosphere for the 3d arrays, where the last layer (z3+1) contains    
      ! the surface information.  This is where you would insert a call
      ! to a custom output routine.

      select_output: SELECT CASE (output_format(out_loop))
        CASE ('mm5 ')
          CALL output_pregrid_format(p, t, ht, u, v, rh, slp, &
                            lwc, rai, sno, ice, pic,snocov, tskin)

        CASE ('wrf ')
          CALL output_gribprep_format(p, t, ht, u, v, rh, slp, psfc,&
                             lwc, rai, sno, ice, pic,snocov, tskin)
     
        CASE ('wps ')
          cloud_bal_wps_output=' '
          CALL GETENV('CLOUD_BAL_WPS_OUTPUT',cloud_bal_wps_output)
          IF (LEN_TRIM(cloud_bal_wps_output)>0) THEN
            CALL output_ungrib_format(p,t,ht,u,v,rh,slp,psfc,lwc,rai,sno,ice,pic, &
              snocov,tskin,istatus,TRIM(cloud_bal_wps_output))
          ELSE
            CALL output_ungrib_format(p,t,ht,u,v,rh,slp,psfc,lwc,rai,sno,ice,pic, &
              snocov,tskin,istatus)
          END IF
          IF (istatus .NE. 1) THEN
            PRINT '(A)', 'WPS output failed; LAPSPREP is not complete.'
            STOP 1
          END IF

        CASE ('rams') 
          CALL output_ralph2_format(p,u,v,t,ht,rh,slp,psfc,snocov,tskin)
        CASE ('sfm ')
          PRINT '(A)', 'Support for SFM (RAMS 3b) coming soon...check back later!'

        CASE ('cdf ')
          CALL output_netcdf_format(p,ht,t,mr,u,v,w,slp,psfc,lwc,ice,rai,sno,pic)

        CASE DEFAULT
          PRINT '(2A)', 'Unrecognized output format: ', output_format
          PRINT '(A)', 'Recognized formats include mm5, rams, wrf, sfm, and cdf'

      END SELECT select_output
    ENDDO 
    PRINT '(A)', 'LAPSPREP Complete.'

  END program lapsprep
  
