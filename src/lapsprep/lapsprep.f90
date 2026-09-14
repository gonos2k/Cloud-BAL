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

    USE cloud_bal_stage_context, ONLY: stage_context,read_stage_context
    USE cloud_bal_lapsprep_adapter, ONLY: cloud_bal_lapsprep_entry
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
    USE, INTRINSIC :: iso_fortran_env, ONLY: int64,real32,real64
    USE cloud_bal_state, ONLY: cloud_bal_state_type,field3d,STATUS_OK,MODE_OFF,canonical_states_equal
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_config,cloud_bal_pipeline_result, &
      restore_pre_balance_winds
    USE cloud_bal_pressure_analysis, ONLY: run_pressure_analysis_shadow
    USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state,write_shadow_diagnostics, &
      read_model_omega_increment
    USE cloud_bal_balance_operator, ONLY: balance_operator_type, &
      build_balance_operator,state_continuity_residual
    USE cloud_bal_wps_adapter, ONLY: pressure_wps_fields,map_pressure_candidate_to_wps, &
      build_pressure_transition_prior,evaluate_source_host_pressure_residual
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
                                             rho,lcp
    REAL , ALLOCATABLE , DIMENSION (:,:)   :: slp , psfc, snocov, d2d,tskin
    REAL , ALLOCATABLE , DIMENSION (:)     :: p
    REAL , PARAMETER                       :: tiny = 1.0e-30
    REAL , PARAMETER                       :: dry_vapor_gas_ratio = 0.622
    
    ! Miscellaneous local variables
                                        
    INTEGER :: out_loop, loop , var_loop , i, j, k, kbot,istatus
    CHARACTER(LEN=256) :: cloud_bal_wps_output
    CHARACTER(LEN=64) :: shadow_experiment
    INTEGER :: environment_status,environment_length
    TYPE(stage_context) :: stage_transport_context
    INTEGER :: stage_reason
    LOGICAL :: stage_enabled
    LOGICAL :: file_present, wps_only
    LOGICAL :: specific_humidity_ready=.FALSE., surface_mixing_ratio_ready=.FALSE.
    LOGICAL :: temperature_ready=.FALSE., surface_temperature_ready=.FALSE.
    LOGICAL :: surface_pressure_ready=.FALSE.
    LOGICAL, ALLOCATABLE :: subterrain_sh_fill(:,:,:)
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

    CALL GET_ENVIRONMENT_VARIABLE('LAPS_DATA_ROOT',laps_data_root,STATUS=environment_status)
    IF (environment_status/=0 .OR. LEN_TRIM(laps_data_root)==0) THEN
      PRINT '(A)', 'LAPS_DATA_ROOT is missing, empty, or too long.'
      STOP 1
    END IF
    PRINT '(2A)', 'LAPS_DATA_ROOT=',laps_data_root

    !  Get the namelist items (from the setup module).

    CALL read_namelist
    wps_only=ALL(output_format(1:num_output)=='wps ')
    shadow_experiment=''
    CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_SHADOW_EXPERIMENT',shadow_experiment, &
      LENGTH=environment_length,STATUS=environment_status)
    IF (environment_status/=0 .AND. environment_status/=1) STOP 1
    CALL read_stage_context('lapsprep','OFF',stage_transport_context,stage_enabled,istatus,stage_reason)
    IF (istatus/=STATUS_OK) STOP 1
    IF (stage_enabled) THEN
      IF (LEN_TRIM(shadow_experiment)>0) THEN
        PRINT *, 'Stage transport cannot be mixed with a SHADOW experiment'
        STOP 1
      END IF
      IF (TRIM(laps_data_root)/=TRIM(stage_transport_context%source_root) .OR. &
          laps_file_time/=stage_transport_context%stamp) STOP 1
      shadow_experiment='OFF'
    END IF
    IF (LEN_TRIM(shadow_experiment)>0) THEN
      SELECT CASE (TRIM(shadow_experiment))
        CASE ('OFF','HYDRO','MODEL_DYNAMICS','LIQUID_RADAR_RH1','LIQUID_RADAR_RH1_PHI','LIQUID_RADAR_RH1_SURFACE_PHI', &
              'LIQUID_RADAR_RH1_SURFACE_PHI_HOST_PSFC')
        CASE DEFAULT
          PRINT *, 'Invalid CLOUD_BAL_SHADOW_EXPERIMENT'
          STOP 1
      END SELECT
      IF (.NOT.wps_only .OR. num_output/=1 .OR. &
          (TRIM(shadow_experiment)/='OFF' .AND. .NOT.wps_output_vapor) .OR. &
          hotstart .OR. balance .OR. make_sfc_uv .OR. lwc2vapor_thresh/=0.0 .OR. &
          TRIM(wind_coordinate)/='GRID_RELATIVE') THEN
        PRINT *, 'SHADOW requires WPS-only/QV and unmodified legacy inputs'
        STOP 1
      END IF
      CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_WPS_OUTPUT',cloud_bal_wps_output, &
        LENGTH=environment_length,STATUS=environment_status)
      IF (environment_status/=0 .OR. LEN_TRIM(cloud_bal_wps_output)==0) THEN
        PRINT *, 'SHADOW requires an explicit separate WPS output path'
        STOP 1
      END IF
      INQUIRE(FILE=TRIM(cloud_bal_wps_output),EXIST=file_present)
      IF (file_present) THEN
        PRINT *, 'SHADOW output already exists'
        STOP 1
      END IF
      INQUIRE(FILE=TRIM(cloud_bal_wps_output)//'.shadow.nc',EXIST=file_present)
      IF (file_present) THEN
        PRINT *, 'SHADOW diagnostic already exists'
        STOP 1
      END IF
    END IF

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
        ALLOCATE ( sh ( x , y , z3 ) )
        ALLOCATE ( subterrain_sh_fill(x,y,z3) )
        subterrain_sh_fill=.FALSE.
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
          CALL capture_field_validity(input_field(var_loop,loop),rh(:,:,1:z),rcode, &
                                      0.0,200.0,missingflag)
          IF (enforce_field_contracts .AND. &
              input_field(var_loop,loop)%status .NE. FIELD_OK) THEN
            PRINT *, 'invalid_rh_field'
            STOP 1
          END IF

          !  Do this just once for pressure.

          vid = NCVID ( cdfid , 'level' , rcode )

          CALL NCVGT ( cdfid , vid , 1 , z3 , p , rcode )
          IF (rcode .NE. 0) THEN
            PRINT *, 'pressure_levels_read_failed'
            STOP 1
          END IF
          CALL initialize_field_contract(pressure_field,'LEVEL', &
               laps_file_time,'hPa',z3,1,1,SOURCE_MODEL)
          CALL capture_field_validity(pressure_field,p(1:z3),rcode, &
                                      1.0,1100.0,missingflag)
          IF (pressure_field%status .NE. FIELD_OK) THEN
            PRINT *, 'invalid_pressure_levels'
            STOP 1
          END IF
          ! Original producers use ascending pressure; retain either strict
          ! ordering with its arrays, rather than reversing coordinates alone.
          IF (.NOT.(ALL(p(2:z3)>p(1:z3-1)) .OR. &
                    ALL(p(2:z3)<p(1:z3-1)))) THEN
            PRINT *, 'nonmonotonic_pressure_levels'
            STOP 1
          END IF
 
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
          specific_humidity_ready=input_field(var_loop,loop)%status==FIELD_OK
          ! WPS needs a rectangular inventory, including underground slabs.
          ! Retain raw validity; only explicit missing SH below a valid PSFC
          ! may use the existing surface extrapolation. Malformed values fail.
          IF (wps_only .AND. rcode==0 .AND. &
              surface_pressure_ready .AND. surface_mixing_ratio_ready) THEN
            DO k=1,z3; DO j=1,y; DO i=1,x
              IF (.NOT.ieee_is_finite(sh(i,j,k))) CYCLE
              subterrain_sh_fill(i,j,k)=ABS(sh(i,j,k))==missingflag .AND. &
                                       p(k)*100.0>psfc(i,j)
            END DO; END DO; END DO
            specific_humidity_ready=ALL(input_field(var_loop,loop)%valid .OR. &
                                        subterrain_sh_fill)
          END IF
          IF ((enforce_field_contracts .OR. wps_only) .AND. .NOT.specific_humidity_ready) THEN
            PRINT *, 'invalid_sh_field'
            STOP 1
          END IF

        END DO var_lq3

      ELSE IF ( ext(loop) .EQ. 'lsx' ) THEN

        !  Loop over the number of variables for this data file.

        var_lsx : DO var_loop = 1 , num_cdf_var(loop)

          ! WPS has no vertical-velocity slab; do not require an unused input.
          IF (wps_only .AND. cdf_var_name(var_loop,loop)=='vv ') CYCLE var_lsx

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
            surface_temperature_ready=input_field(var_loop,loop)%status==FIELD_OK
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
            surface_mixing_ratio_ready=input_field(var_loop,loop)%status==FIELD_OK
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
            surface_pressure_ready=input_field(var_loop,loop)%status==FIELD_OK
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'tgd') THEN
            CALL NCVGT ( cdfid , vid , start , count , tskin         , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'TSKIN', &
                 laps_file_time,'K',x,y,1,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),tskin,rcode, &
                                        150.0,350.0,missingflag)
          END IF
          IF (enforce_field_contracts .AND. &
              input_field(var_loop,loop)%status .NE. FIELD_OK) THEN
            PRINT *, 'invalid_surface_field: ',TRIM(cdf_var_name(var_loop,loop))
            STOP 1
          END IF

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
            CALL capture_field_validity(input_field(var_loop,loop),t(:,:,1:z),rcode, &
                                        150.0,350.0,missingflag)
            temperature_ready=input_field(var_loop,loop)%status==FIELD_OK
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'ht ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , ht , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'HT', &
                 laps_file_time,'m',x,y,z,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),ht(:,:,1:z),rcode, &
                                        -1000.0,100000.0,missingflag)
          END IF
          IF (enforce_field_contracts .AND. &
              input_field(var_loop,loop)%status .NE. FIELD_OK) THEN
            PRINT *, 'invalid_lt1_field: ',TRIM(cdf_var_name(var_loop,loop))
            STOP 1
          END IF

        END DO var_lt1

      ELSE IF ( ext(loop) .EQ. 'lw3' ) THEN

        !  Loop over the number of variables for this data file.

        var_lw3 : DO var_loop = 1 , num_cdf_var(loop)

          IF (wps_only .AND. cdf_var_name(var_loop,loop)=='om ') CYCLE var_lw3

          !  Get the variable ID.

          vid = NCVID ( cdfid , TRIM(cdf_var_name(var_loop,loop)) , rcode )
          start = (/ 1 , 1 , 1 , 1 /)
          count = (/ x , y , z , 1 /)
          IF      ( cdf_var_name(var_loop,loop) .EQ. 'u3 ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , u , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'U3', &
                 laps_file_time,'m s-1',x,y,z,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),u(:,:,1:z),rcode, &
                                        -200.0,200.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'v3 ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , v , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'V3', &
                 laps_file_time,'m s-1',x,y,z,SOURCE_MODEL)
            CALL capture_field_validity(input_field(var_loop,loop),v(:,:,1:z),rcode, &
                                        -200.0,200.0,missingflag)
          ELSE IF ( cdf_var_name(var_loop,loop) .EQ. 'om ' ) THEN
            CALL NCVGT ( cdfid , vid , start , count , w , rcode )
            CALL initialize_field_contract(input_field(var_loop,loop),'OM', &
                 laps_file_time,'Pa s-1',x,y,z,SOURCE_CLOUD)
            CALL capture_field_validity(input_field(var_loop,loop),w(:,:,1:z),rcode, &
                                        -100.0,100.0,missingflag)
          END IF
          IF (enforce_field_contracts .AND. &
              input_field(var_loop,loop)%status .NE. FIELD_OK) THEN
            PRINT *, 'invalid_lw3_field: ',TRIM(cdf_var_name(var_loop,loop))
            STOP 1
          END IF

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

    ! Direct QV output must not turn a missing analysis into a surface fallback.
    ! These read/coverage checks apply even if legacy enforcement is disabled.
    IF (wps_output_vapor) THEN
      IF (.NOT.(specific_humidity_ready .AND. surface_mixing_ratio_ready .AND. &
                temperature_ready .AND. surface_temperature_ready .AND. &
                surface_pressure_ready)) THEN
        PRINT *, 'WPS QV requires complete SH, MR_SFC, T3, and T_SFC inputs.'
        STOP 1
      END IF
    END IF

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

      IF (subterrain_sh_fill(i,j,k)) THEN
        mr(i,j,k)=mr(i,j,z3+1)
        CYCLE
      END IF

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
        IF (wps_output_vapor) THEN
          PRINT *, 'Invalid pressure-level SH cannot be replaced for WPS QV.'
          STOP 1
        END IF
        mr(i,j,k)=mr(i,j,z3+1)
      endif
!      if (u(i,j,k) .eq. 1.e-30 .or. abs(u(i,j,k)) .gt. 200.) u(i,j,k)=u(i,j,z3+1)
!     if (v(i,j,k) .eq. 1.e-30 .or. abs(v(i,j,k)) .gt. 200.) v(i,j,k)=v(i,j,z3+1)
    enddo
    enddo
    enddo
    IF (wps_only .AND. wps_output_vapor) &
      PRINT '(A,I0)', 'WPS below-ground SH surface extrapolation cells=',SUM(MERGE(1,0,subterrain_sh_fill))

    !  Set the lowest level of the geopotential height to topographic height

    ht(:,:,z3+1) = topo 

    IF (hotstart) THEN

      ! If this is a hot start, then we need to convert the microphysical
      ! species from kg/m3 to kg/kg DRY AIR, as required by QV and the native
      ! species convention. Moist-gas density would give a different denominator.
      IF (ANY(.NOT.ieee_is_finite(t(:,:,1:z3))) .OR. &
          ANY(.NOT.ieee_is_finite(mr(:,:,1:z3))) .OR. &
          ANY(.NOT.ieee_is_finite(p(1:z3)))) THEN
        PRINT *, 'Invalid hot-start pressure, temperature or vapor.'
        STOP 1
      END IF
      IF (ANY(t(:,:,1:z3)<=0.0) .OR. ANY(mr(:,:,1:z3)<0.0) .OR. &
          ANY(p(1:z3)<=0.0)) THEN
        PRINT *, 'Invalid hot-start pressure, temperature or vapor.'
        STOP 1
      END IF
      ! p = rho_d * Rd * T * (1 + rv / epsilon); rv is kg vapor/kg dry air.
      DO k = 1, z3
        rho(:,:,k) = p(k)*100. / &
          (rdry*t(:,:,k)*(1.0+mr(:,:,k)/dry_vapor_gas_ratio))
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

      ! Recompute MOIST-GAS density after transfers for the existing hydrostatic
      ! omega-to-w approximation. This is not the dry denominator used above,
      ! nor a full condensate-loaded pressure-coordinate conversion.
      DO k=1,z3
        rho(:,:,k)=p(k)*100.0*(1.0+mr(:,:,k))/ &
          (rdry*t(:,:,k)*(1.0+mr(:,:,k)/dry_vapor_gas_ratio))
      ENDDO
      IF (ANY(.NOT. ieee_is_finite(rho)) .OR. MINVAL(rho) .LE. 0.0) THEN
        STOP 'invalid_post_transfer_density'
      ENDIF

      ! Convert 3d omega from Pa/s to m/s, or fill with sfc value if missing.

      IF (.NOT.wps_only) THEN
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
      END IF


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
              IF (kbot==0) THEN
                kbot=k
              ELSE IF (p(k)>p(kbot)) THEN
                kbot=k
              END IF
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
      ! as (x,y,z), starting at the southwest corner. Pressure levels retain
      ! their input ordering; the last layer (z3+1) contains the
      ! surface information. This is where you would insert a call
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
          CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_WPS_OUTPUT',cloud_bal_wps_output,STATUS=environment_status)
          IF (environment_status/=0 .AND. environment_status/=1) THEN
            PRINT '(A)', 'CLOUD_BAL_WPS_OUTPUT could not be read without truncation.'
            STOP 1
          END IF
          IF (LEN_TRIM(shadow_experiment)>0) CALL prepare_shadow_wps
          IF (LEN_TRIM(shadow_experiment)>0 .AND. TRIM(shadow_experiment)/='OFF') THEN
            CALL output_ungrib_format(p,t,ht,u,v,rh,slp,psfc,lwc,rai,sno,ice,pic, &
              snocov,tskin,istatus,TRIM(cloud_bal_wps_output), &
              vapor_mixing_ratio=mr,include_hydrometeors=.TRUE.,include_surface_height=.TRUE.,create_new=.TRUE.)
          ELSE IF (wps_output_vapor) THEN
            IF (LEN_TRIM(cloud_bal_wps_output)>0) THEN
              CALL output_ungrib_format(p,t,ht,u,v,rh,slp,psfc,lwc,rai,sno,ice,pic, &
                snocov,tskin,istatus,TRIM(cloud_bal_wps_output),vapor_mixing_ratio=mr)
            ELSE
              CALL output_ungrib_format(p,t,ht,u,v,rh,slp,psfc,lwc,rai,sno,ice,pic, &
                snocov,tskin,istatus,vapor_mixing_ratio=mr)
            END IF
          ELSE IF (LEN_TRIM(cloud_bal_wps_output)>0) THEN
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

  CONTAINS

    SUBROUTINE prepare_shadow_wps
      TYPE(cloud_bal_state_type) :: original,candidate,operational,transition_seed,pre_balance
      TYPE(field3d), ALLOCATABLE :: retained_omega
      TYPE(cloud_bal_pipeline_config) :: config
      TYPE(cloud_bal_pipeline_result) :: result
      TYPE(pressure_wps_fields) :: background,mapped,baseline_mapped
      TYPE(balance_operator_type) :: op
      REAL(real32), ALLOCATABLE :: longitude(:,:)
      REAL(real64), ALLOCATABLE :: before(:,:,:),after(:,:,:)
      REAL(real64), ALLOCATABLE :: pressure_request(:,:),pressure_residual(:,:),pressure_tolerance(:,:)
      REAL(real64), ALLOCATABLE :: previous_pressure(:,:)
      LOGICAL, ALLOCATABLE :: pressure_columns(:,:)
      LOGICAL :: pressure_converged
      INTEGER(int64) :: epoch
      INTEGER :: status,reason,legacy_time,pressure_iteration,failed_column(2)
      CHARACTER(LEN=512) :: product_root,model_target_path

      ! The clock helper returns seconds since 1960; canonical time is Unix.
      CALL i4time_fname_lp(laps_file_time,legacy_time,status)
      IF (status/=1) STOP 1
      epoch=INT(legacy_time,int64)-315619200_int64
      product_root=TRIM(laps_data_root)//'/lapsprd/'
      CALL read_real_shadow_state('','', &
        TRIM(product_root)//'lw3/'//laps_file_time//'.lw3', &
        TRIM(product_root)//'vrz/'//laps_file_time//'.vrz', &
        TRIM(product_root)//'vrt/'//laps_file_time//'.vrt', &
        TRIM(laps_data_root)//'/static/static.nest7grid',epoch, &
        original,longitude,status,reason, &
        lt1_path=TRIM(product_root)//'lt1/'//laps_file_time//'.lt1', &
        lq3_path=TRIM(product_root)//'lq3/'//laps_file_time//'.lq3', &
        lwc_path=TRIM(product_root)//'lwc/'//laps_file_time//'.lwc', &
        lsx_path=TRIM(product_root)//'lsx/'//laps_file_time//'.lsx',retained_omega=retained_omega, &
        lcp_path=TRIM(product_root)//'lcp/'//laps_file_time//'.lcp', &
        lty_path=TRIM(product_root)//'lty/'//laps_file_time//'.lty')
      IF (status/=STATUS_OK) THEN
        PRINT *, 'SHADOW pressure reader rejected input: ',reason
        STOP 1
      END IF
      IF (stage_enabled) THEN
        CALL cloud_bal_lapsprep_entry(stage_transport_context,original,longitude,status,reason)
        IF (status/=STATUS_OK) STOP 1
      END IF
      IF (x/=original%grid%nx .OR. y/=original%grid%ny .OR. z3/=original%grid%nz) STOP 1
      IF (ANY(lats/=original%latitude%value) .OR. ANY(lons/=longitude)) STOP 1
      IF (TRIM(shadow_experiment)=='MODEL_DYNAMICS') THEN
        model_target_path=''
        CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_MODEL_TARGET',model_target_path,STATUS=status)
        IF (status/=0 .OR. LEN_TRIM(model_target_path)==0) THEN
          PRINT *, 'MODEL_DYNAMICS requires an explicit paired model response'
          STOP 1
        END IF
        CALL read_model_omega_increment(TRIM(model_target_path),original,longitude,status)
        IF (status/=STATUS_OK) THEN
          PRINT *, 'MODEL_DYNAMICS response does not match the analysis contract'
          STOP 1
        END IF
      END IF
      ! Retain the actual host slabs, including its explicit underground fills.
      background%p=p; background%t=t; background%ht=ht
      background%u=u; background%v=v; background%rh=rh; background%qv=mr
      background%qc=lwc; background%qi=ice; background%qr=rai
      background%qs=sno; background%qg=pic
      background%psfc=psfc; background%slp=slp
      background%skin_temperature=tskin; background%snow_cover=snocov
      background%valid_time=epoch; background%grid_id=original%grid%grid_id
      background%wind_coordinate=wind_coordinate
      IF (TRIM(shadow_experiment)=='LIQUID_RADAR_RH1_SURFACE_PHI_HOST_PSFC') THEN
        ! A bounded source-grid coupled pressure solve, not native conservation.
        ! Use the SAME canonical OFF background and retained host slabs. The
        ! normal METGRID interpolation still runs after this WPS writer.
        CALL map_pressure_candidate_to_wps(original,background,baseline_mapped,status,wind_coordinate)
        IF (status/=STATUS_OK) STOP 1
        CALL run_pressure_analysis_shadow(original,candidate,operational,result, &
          config,'LIQUID_RADAR_RH1_SURFACE_PHI',status,single_pass=.TRUE.)
        IF (status/=STATUS_OK) STOP 1
        CALL map_pressure_candidate_to_wps(candidate,background,mapped,status,wind_coordinate)
        IF (status/=STATUS_OK) STOP 1
        ALLOCATE(pressure_request(x,y),pressure_columns(x,y), &
          pressure_residual(x,y),pressure_tolerance(x,y),previous_pressure(x,y))
        previous_pressure=0.0_real64
        pressure_request=REAL(original%surface_pressure%value,real64)
        pressure_columns=.FALSE.
        IF (ALLOCATED(result%geopotential_support)) &
          pressure_columns=ANY(result%geopotential_support,DIM=3)
        IF (ANY(pressure_columns)) THEN
          ! Unit-slope fixed-point steps use the actual remapped profile at
          ! every trial. No fixed-q approximation can certify the final state.
          pressure_converged=.FALSE.
          DO pressure_iteration=1,12
            pressure_residual=0.0_real64
            CALL evaluate_source_host_pressure_residual(baseline_mapped,mapped,pressure_columns, &
              287.0_real64,9.81_real64,pressure_residual,status)
            IF (status/=STATUS_OK) STOP 1
            pressure_tolerance=2.0_real64*REAL(SPACING(mapped%psfc),real64)+ &
              128.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(REAL(mapped%psfc,real64)))
            PRINT *, 'source_host_pressure_iteration_residual=',pressure_iteration,MAXVAL(ABS(pressure_residual))
            IF (ALL(ABS(pressure_residual)<=pressure_tolerance)) THEN
              pressure_converged=.TRUE.
              EXIT
            END IF
            IF (pressure_iteration==12) EXIT
            pressure_request=REAL(original%surface_pressure%value,real64)
            WHERE (pressure_columns)
              pressure_request=REAL(mapped%psfc,real64)-pressure_residual
            END WHERE
            IF (ANY(.NOT.ieee_is_finite(pressure_request)) .OR. &
                ANY(pressure_request<100.0_real64) .OR. ANY(pressure_request>120000.0_real64) .OR. &
                ANY(ABS(pressure_request-REAL(original%surface_pressure%value,real64))>100.0_real64)) THEN
              PRINT *, 'Source-grid host pressure solve exceeded its 100 Pa request bound'
              STOP 1
            END IF
            pressure_request=REAL(REAL(pressure_request,real32),real64)
            IF (ALL(pressure_request==REAL(mapped%psfc,real64))) THEN
              PRINT *, 'Source-grid host pressure solve stagnated at stored precision'
              STOP 1
            END IF
            IF (ALL(pressure_request==previous_pressure)) THEN
              PRINT *, 'Source-grid host pressure solve entered a stored two-cycle'
              STOP 1
            END IF
            previous_pressure=REAL(mapped%psfc,real64)
            CALL build_pressure_transition_prior(original,background,retained_omega, &
              MAX(pressure_request,REAL(original%surface_pressure%value,real64)),transition_seed,status,failed_column)
            IF (status/=STATUS_OK) THEN
              PRINT *, 'Host pressure prior rejected at column ',failed_column
              IF (ALL(failed_column>0)) PRINT *, 'Host pressure original/request Pa: ', &
                original%surface_pressure%value(failed_column(1),failed_column(2)), &
                pressure_request(failed_column(1),failed_column(2))
              STOP 1
            END IF
            ! Each trial starts from the SAME immutable input. Negative
            ! same-domain requests use the existing hydrostatic stage; positive
            ! requests use the explicit conservative seed and transition.
            CALL run_pressure_analysis_shadow(original,candidate,operational,result, &
              config,'LIQUID_RADAR_RH1_SURFACE_PHI',status, &
              requested_surface_pressure=pressure_request,single_pass=.TRUE., &
              pressure_transition_seed=transition_seed)
            IF (status/=STATUS_OK) THEN
              PRINT *, 'Host pressure pipeline rejected trial: ',pressure_iteration,result%reason_code
              STOP 1
            END IF
            CALL map_pressure_candidate_to_wps(candidate,background,mapped,status,wind_coordinate)
            IF (status/=STATUS_OK) STOP 1
          END DO
          IF (.NOT.pressure_converged) THEN
            PRINT *, 'Source-grid host pressure solve did not converge'
            STOP 1
          END IF
          PRINT *, 'pressure_request_experiment=SOURCE_GRID_HOST_COUPLED_RESEARCH_NOT_NATIVE_CONSERVATION'
          PRINT *, 'pressure_request_host_Rd_g_cap=',287.0_real64,9.81_real64,100.0_real64
          PRINT *, 'pressure_request_max_abs_pa=', &
            MAXVAL(ABS(pressure_request-REAL(original%surface_pressure%value,real64)))
          PRINT *, 'source_host_final_pressure_residual_max_abs_pa=',MAXVAL(ABS(pressure_residual))
        ELSE
          PRINT *, 'pressure_request_experiment=NO_OBSERVATIONAL_CONSTRAINT'
        END IF
      ELSE
        CALL run_pressure_analysis_shadow(original,candidate,operational,result, &
          config,TRIM(shadow_experiment),status)
        IF (status/=STATUS_OK) STOP 1
        IF (config%requested_mode==MODE_OFF) THEN
          IF (.NOT.canonical_states_equal(original,candidate) .OR. &
              .NOT.canonical_states_equal(original,operational)) STOP 1
          ! OFF validates the real canonical path, then retains every host slab.
          ! Mapping even an unchanged canonical state would round heights and
          ! introduce condensates that ordinary cold initialization never read.
          PRINT *, 'OFF canonical identity verified; host fields retained'
          RETURN
        END IF
        CALL map_pressure_candidate_to_wps(candidate,background,mapped,status,wind_coordinate)
        IF (status/=STATUS_OK) THEN
          PRINT *, 'SHADOW candidate-to-WPS mapping failed'
          STOP 1
        END IF
      END IF
      IF (status/=STATUS_OK) STOP 1
      IF (config%requested_mode/=MODE_OFF) THEN
        CALL build_balance_operator(candidate,config%balance,op,status,reason)
        IF (status/=STATUS_OK) STOP 1
        ALLOCATE(before(x,y,z3),after(x,y,z3))
        IF (ALLOCATED(result%pressure_transition_seed)) THEN
          CALL restore_pre_balance_winds(candidate,original,pre_balance,status, &
            transition_seed=result%pressure_transition_seed)
        ELSE
          CALL restore_pre_balance_winds(candidate,original,pre_balance,status)
        END IF
        IF (status/=STATUS_OK) STOP 1
        CALL state_continuity_residual(op,pre_balance,before,status)
        IF (status/=STATUS_OK) STOP 1
        CALL state_continuity_residual(op,candidate,after,status)
        IF (status/=STATUS_OK) STOP 1
        CALL write_shadow_diagnostics(TRIM(cloud_bal_wps_output)//'.shadow.nc', &
          original,candidate,longitude,result,config,before,after,status,operational, &
          pressure_analysis_candidate=ALLOCATED(result%geopotential_support))
        IF (status/=STATUS_OK) STOP 1
      END IF
      ! Assign only to this process's WPS arrays after all candidate checks.
      t=mapped%t; ht=mapped%ht; u=mapped%u; v=mapped%v; mr=mapped%qv
      lwc=mapped%qc; ice=mapped%qi; rai=mapped%qr; sno=mapped%qs; pic=mapped%qg
      psfc=mapped%psfc
      PRINT *, 'SHADOW WPS mapping complete; research only, not native/science approval'
    END SUBROUTINE prepare_shadow_wps

  END program lapsprep
  
