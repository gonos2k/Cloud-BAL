! Small, deterministic fixtures for an independent precipitation-transport
! reference.  This test deliberately calls the public transport kernel only;
! it does not construct a canonical state or exercise the column driver.
!
! File format (whitespace separated, version 1):
!   CASE name nx ny nz
!   CONFIG maximum_horizontal_substep maximum_transport_substeps minimum_relative_fall_speed
!   GRID i j dx dy psfc
!   INTERFACE i j k p_bottom p_top cell_dp
!   SPACING i j k level_spacing_dp
!   CELL i j k p T rv u v w domain observed no_echo phase Z rain snow graupel
!   RESULT name status max_substeps input deposited suspended boundary terrain observed no_echo loss
!   OUT i j k phase Z rain snow graupel
!   ENDCASE
!
! The input file contains the GRID/INTERFACE/SPACING/CELL records.  The output
! file contains RESULT/OUT records.  A Python checker can therefore implement
! the trajectory and bilinear scatter independently without linking Fortran.
PROGRAM test_pressure_radar_reference
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32
  USE cloud_bal_state
  USE cloud_bal_column_physics
  IMPLICIT NONE

  INTEGER, PARAMETER :: CASE_TILT=1, CASE_MULTI=2, CASE_SOURCE_SUSPEND=3
  INTEGER, PARAMETER :: CASE_DEST_SUSPEND=4, CASE_OBS_BLOCK=5
  INTEGER, PARAMETER :: CASE_NOECHO_BLOCK=6, CASE_BOUNDARY=7
  INTEGER, PARAMETER :: CASE_TERRAIN=8, CASE_VARYING_METRIC=9
  INTEGER, PARAMETER :: CASE_SUBSTEPS=10, CASE_BAD_SOURCE=11
  INTEGER, PARAMETER :: CASE_BAD_TERRAIN_SOURCE=12
  INTEGER, PARAMETER :: CASE_CROSSING=13, CASE_SUBSTEPS_FINE=14
  CHARACTER(LEN=512) :: input_path,output_path
  INTEGER :: input_unit,output_unit,status

  CALL GET_COMMAND_ARGUMENT(1,input_path)
  CALL GET_COMMAND_ARGUMENT(2,output_path)
  IF (LEN_TRIM(input_path)==0) input_path='radar_reference_input.txt'
  IF (LEN_TRIM(output_path)==0) output_path='radar_reference_output.txt'
  OPEN(NEWUNIT=input_unit,FILE=TRIM(input_path),STATUS='NEW',ACTION='WRITE',IOSTAT=status)
  IF (status/=0) ERROR STOP 'open input fixture'
  OPEN(NEWUNIT=output_unit,FILE=TRIM(output_path),STATUS='NEW',ACTION='WRITE',IOSTAT=status)
  IF (status/=0) ERROR STOP 'open output fixture'

  WRITE(input_unit,*) 'FORMAT CLOUD_BAL_RADAR_REFERENCE_V1'
  WRITE(output_unit,*) 'FORMAT CLOUD_BAL_RADAR_REFERENCE_V1'
  CALL run_case('tilt_shear',4,3,4,CASE_TILT,input_unit,output_unit)
  CALL run_case('multilevel_multispecies',3,2,4,CASE_MULTI,input_unit,output_unit)
  CALL run_case('source_suspension',1,1,3,CASE_SOURCE_SUSPEND,input_unit,output_unit)
  CALL run_case('destination_suspension',1,1,3,CASE_DEST_SUSPEND,input_unit,output_unit)
  CALL run_case('observed_destination_block',2,1,3,CASE_OBS_BLOCK,input_unit,output_unit)
  CALL run_case('noecho_destination_block',2,1,3,CASE_NOECHO_BLOCK,input_unit,output_unit)
  CALL run_case('boundary_exit',3,1,3,CASE_BOUNDARY,input_unit,output_unit)
  CALL run_case('terrain_intercept',1,1,3,CASE_TERRAIN,input_unit,output_unit)
  CALL run_case('varying_dxdy_rejected',3,2,3,CASE_VARYING_METRIC,input_unit,output_unit)
  ! The larger fixture leaves the analytic endpoint interior, so the full
  ! bilinear footprint and both horizontal centroids are observable.
  CALL run_case('horizontal_substeps',5,4,3,CASE_SUBSTEPS,input_unit,output_unit)
  CALL run_case('horizontal_substeps_fine',5,4,3,CASE_SUBSTEPS_FINE,input_unit,output_unit)
  CALL run_case('crossing_sources',5,1,3,CASE_CROSSING,input_unit,output_unit)
  CALL run_case('invalid_noecho_source',1,1,3,CASE_BAD_SOURCE,input_unit,output_unit)
  CALL run_case('invalid_below_ground_source',1,1,3,CASE_BAD_TERRAIN_SOURCE,input_unit,output_unit)
  CLOSE(input_unit)
  CLOSE(output_unit)
  WRITE(*,'(A)') 'PRESSURE RADAR REFERENCE FIXTURES PASS'
  WRITE(*,'(A)') '  valid cases: 11; explicit atomic rejections: 3'
  WRITE(*,'(A)') '  independent input/output artifacts written'

CONTAINS

  SUBROUTINE run_case(name,nx,ny,nz,case_id,input_unit,output_unit)
    CHARACTER(*), INTENT(IN) :: name
    INTEGER, INTENT(IN) :: nx,ny,nz,case_id,input_unit,output_unit
    TYPE(grid_spec) :: grid
    TYPE(column_physics_config) :: cfg
    TYPE(precipitation_flux_ledger) :: ledger
    REAL(real32), ALLOCATABLE :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:)
    REAL(real32), ALLOCATABLE :: u(:,:,:),v(:,:,:),w(:,:,:)
    LOGICAL, ALLOCATABLE :: w_valid(:,:,:),domain(:,:,:),observed(:,:,:),no_echo(:,:,:)
    INTEGER, ALLOCATABLE :: phase(:,:,:),phase_before(:,:,:)
    REAL(real64), ALLOCATABLE :: zlinear(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    REAL(real64), ALLOCATABLE :: z_before(:,:,:),rain_before(:,:,:),snow_before(:,:,:)
    REAL(real64), ALLOCATABLE :: graupel_before(:,:,:)
    INTEGER :: status

    ALLOCATE(pressure(nx,ny,nz),temperature(nx,ny,nz),vapor(nx,ny,nz), &
             u(nx,ny,nz),v(nx,ny,nz),w(nx,ny,nz),w_valid(nx,ny,nz), &
             domain(nx,ny,nz),observed(nx,ny,nz),no_echo(nx,ny,nz), &
             phase(nx,ny,nz),zlinear(nx,ny,nz),rain(nx,ny,nz), &
             snow(nx,ny,nz),graupel(nx,ny,nz),phase_before(nx,ny,nz), &
             z_before(nx,ny,nz),rain_before(nx,ny,nz),snow_before(nx,ny,nz), &
             graupel_before(nx,ny,nz))
    cfg=column_physics_config()
    CALL initialize_fixture(grid,pressure,temperature,vapor,u,v,w,w_valid,domain, &
      observed,no_echo,phase,zlinear,rain,snow,graupel,nx,ny,nz,case_id,name)
    IF (case_id==CASE_SUBSTEPS_FINE) cfg%maximum_horizontal_substep=0.50_real64
    CALL write_input_case(input_unit,name,grid,cfg,pressure,temperature,vapor,u,v,w, &
      domain,observed,no_echo,phase,zlinear,rain,snow,graupel)
    phase_before=phase; z_before=zlinear; rain_before=rain; snow_before=snow
    graupel_before=graupel
    CALL transport_precipitation_flux(grid,pressure,temperature,vapor,u,v,w,w_valid, &
      domain,observed,phase,zlinear,rain,snow,graupel,cfg,ledger,status,no_echo)
    CALL check_case(case_id,status,ledger,cfg,phase,phase_before,zlinear,z_before, &
      rain,rain_before,snow,snow_before,graupel,graupel_before)
    CALL write_output_case(output_unit,name,status,ledger,phase,zlinear,rain,snow,graupel)
    DEALLOCATE(pressure,temperature,vapor,u,v,w,w_valid,domain,observed,no_echo,phase, &
      zlinear,rain,snow,graupel,phase_before,z_before,rain_before,snow_before,graupel_before)
  END SUBROUTINE run_case

  SUBROUTINE initialize_fixture(grid,pressure,temperature,vapor,u,v,w,w_valid,domain, &
      observed,no_echo,phase,zlinear,rain,snow,graupel,nx,ny,nz,case_id,name)
    TYPE(grid_spec), INTENT(OUT) :: grid
    REAL(real32), INTENT(OUT) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:)
    REAL(real32), INTENT(OUT) :: u(:,:,:),v(:,:,:),w(:,:,:)
    LOGICAL, INTENT(OUT) :: w_valid(:,:,:),domain(:,:,:),observed(:,:,:),no_echo(:,:,:)
    INTEGER, INTENT(OUT) :: phase(:,:,:)
    REAL(real64), INTENT(OUT) :: zlinear(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    INTEGER, INTENT(IN) :: nx,ny,nz,case_id
    CHARACTER(*), INTENT(IN) :: name
    INTEGER :: i,j,k,vt_status
    REAL(real64) :: vt,source_dt,source_dz

    CALL allocate_grid(grid,nx,ny,nz,name)
    DO j=1,ny; DO i=1,nx
      grid%dx(i,j)=2000.0_real64
      grid%dy(i,j)=2000.0_real64
      IF (case_id==CASE_VARYING_METRIC) THEN
        grid%dx(i,j)=1800.0_real64+100.0_real64*REAL(i,real64)+50.0_real64*REAL(j,real64)
        grid%dy(i,j)=2100.0_real64+80.0_real64*REAL(i,real64)+70.0_real64*REAL(j,real64)
      END IF
      grid%pressure_interface(i,j,1)=102500.0_real64
      DO k=2,nz+1
        grid%pressure_interface(i,j,k)=102500.0_real64-15000.0_real64*REAL(k-1,real64)
      END DO
      grid%cell_dp(i,j,:)=15000.0_real64
      grid%level_spacing_dp(i,j,:)=15000.0_real64
      grid%pressure_mass_measure(i,j,:)=grid%dx(i,j)*grid%dy(i,j)* &
        grid%cell_dp(i,j,:)/9.80665_real64
      grid%dry_air_mass_measure(i,j,:)=grid%pressure_mass_measure(i,j,:)/1.01_real64
    END DO; END DO

    DO k=1,nz
      pressure(:,:,k)=REAL(95000.0_real64-15000.0_real64*REAL(k-1,real64),real32)
    END DO
    temperature=280.0_real32; vapor=0.008_real32
    u=0.0_real32; v=0.0_real32; w=0.0_real32
    w_valid=.TRUE.; domain=.TRUE.; observed=.FALSE.; no_echo=.FALSE.
    phase=PHASE_UNKNOWN; zlinear=0.0_real64; rain=0.0_real64
    snow=0.0_real64; graupel=0.0_real64

    SELECT CASE(case_id)
    CASE(CASE_TILT)
      DO k=1,nz; DO j=1,ny; DO i=1,nx
        u(i,j,k)=REAL(1.2_real64+0.35_real64*REAL(i,real64)+ &
          0.20_real64*REAL(k,real64),real32)
        v(i,j,k)=REAL(-0.4_real64+0.25_real64*REAL(j,real64)- &
          0.12_real64*REAL(k,real64),real32)
      END DO; END DO; END DO
      CALL set_rain_source(2,2,4,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      CALL set_snow_source(1,1,3,observed,phase,zlinear,snow,4000.0_real64,8.0e-5_real64)
    CASE(CASE_MULTI)
      CALL set_rain_source(1,1,4,observed,phase,zlinear,rain,800.0_real64,1.0e-4_real64)
      CALL set_snow_source(3,2,3,observed,phase,zlinear,snow,2000.0_real64,8.0e-5_real64)
      CALL set_graupel_source(2,1,2,observed,phase,zlinear,graupel,3000.0_real64,6.0e-5_real64)
    CASE(CASE_SOURCE_SUSPEND)
      CALL set_rain_source(1,1,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      vt=terminal_velocity(PHASE_RAIN,REAL(pressure(1,1,3),real64), &
        REAL(temperature(1,1,3),real64),30.0_real64,vt_status)
      CALL require(vt_status==STATUS_OK,'source suspension terminal velocity')
      w(1,1,3)=REAL(vt-0.10_real64,real32)
    CASE(CASE_DEST_SUSPEND)
      CALL set_rain_source(1,1,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      vt=terminal_velocity(PHASE_RAIN,REAL(pressure(1,1,2),real64), &
        REAL(temperature(1,1,2),real64),30.0_real64,vt_status)
      CALL require(vt_status==STATUS_OK,'destination suspension terminal velocity')
      w(1,1,2)=REAL(vt-0.10_real64,real32)
    CASE(CASE_OBS_BLOCK)
      CALL set_rain_source(1,1,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      observed(1,1,2)=.TRUE.
    CASE(CASE_NOECHO_BLOCK)
      CALL set_rain_source(1,1,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      no_echo(1,1,2)=.TRUE.
    CASE(CASE_BOUNDARY)
      CALL set_rain_source(2,1,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      ! Half of the endpoint footprint exits the right boundary; the retained
      ! half is observation-blocked so no descendant reaches account_bottom_flux.
      observed(3,1,2)=.TRUE.
      source_dz=source_layer_distance(2,1,3,grid,pressure,temperature,vapor)
      source_dt=source_dz/terminal_velocity(PHASE_RAIN,65000.0_real64,280.0_real64,30.0_real64,vt_status)
      CALL require(vt_status==STATUS_OK,'boundary terminal velocity')
      u(2,1,3)=REAL(1.5_real64*grid%dx(2,1)/source_dt,real32)
    CASE(CASE_TERRAIN)
      domain(:,:,1:2)=.FALSE.
      ! Keep the exported pressure geometry canonical for the clipped column:
      ! inactive cells have zero control-volume thickness and the first active
      ! cell starts at PSFC.  The transport kernel only needs the active
      ! source-to-interface distance for this terrain-intercept fixture.
      grid%pressure_interface(:,:,2)=grid%pressure_interface(:,:,1)
      grid%pressure_interface(:,:,3)=grid%pressure_interface(:,:,1)
      grid%cell_dp(:,:,1:2)=0.0_real64
      grid%cell_dp(:,:,3)=grid%pressure_interface(:,:,3)-grid%pressure_interface(:,:,4)
      grid%pressure_mass_measure(:,:,1:2)=0.0_real64
      grid%dry_air_mass_measure(:,:,1:2)=0.0_real64
      grid%pressure_mass_measure(:,:,3)=grid%dx*grid%dy*grid%cell_dp(:,:,3)/9.80665_real64
      grid%dry_air_mass_measure(:,:,3)=grid%pressure_mass_measure(:,:,3)/1.01_real64
      CALL set_rain_source(1,1,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
    CASE(CASE_VARYING_METRIC)
      CALL set_rain_source(2,1,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      source_dz=source_layer_distance(2,1,3,grid,pressure,temperature,vapor)
      source_dt=source_dz/terminal_velocity(PHASE_RAIN,65000.0_real64,280.0_real64,30.0_real64,vt_status)
      CALL require(vt_status==STATUS_OK,'varying metric terminal velocity')
      u(2,1,3)=REAL(0.45_real64*grid%dx(2,1)/source_dt,real32)
      v(2,1,3)=REAL(0.35_real64*grid%dy(2,1)/source_dt,real32)
    CASE(CASE_SUBSTEPS)
      CALL set_rain_source(2,2,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      source_dz=source_layer_distance(2,2,3,grid,pressure,temperature,vapor)
      source_dt=source_dz/terminal_velocity(PHASE_RAIN,65000.0_real64,280.0_real64,30.0_real64,vt_status)
      CALL require(vt_status==STATUS_OK,'substep terminal velocity')
      ! Uniform level wind: empty receiving cells still have the same wind.
      ! The centroid report distinguishes this from an actual shear-induced stop.
      u(:,:,3)=REAL(2.0_real64*grid%dx(2,2)/source_dt,real32)
      v(:,:,3)=REAL(1.4_real64*grid%dy(2,2)/source_dt,real32)
    CASE(CASE_SUBSTEPS_FINE)
      CALL set_rain_source(2,2,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      source_dz=source_layer_distance(2,2,3,grid,pressure,temperature,vapor)
      source_dt=source_dz/terminal_velocity(PHASE_RAIN,65000.0_real64,280.0_real64,30.0_real64,vt_status)
      CALL require(vt_status==STATUS_OK,'fine substep terminal velocity')
      u(:,:,3)=REAL(2.0_real64*grid%dx(2,2)/source_dt,real32)
      v(:,:,3)=REAL(1.4_real64*grid%dy(2,2)/source_dt,real32)
    CASE(CASE_CROSSING)
      CALL set_rain_source(2,1,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      ! Both sources are rain so the regression exercises same-phase
      ! superposition; distinct reflectivity values preserve source identity.
      CALL set_rain_source(4,1,3,observed,phase,zlinear,rain,4000.0_real64,8.0e-5_real64)
      source_dz=source_layer_distance(2,1,3,grid,pressure,temperature,vapor)
      source_dt=source_dz/terminal_velocity(PHASE_RAIN,65000.0_real64,280.0_real64,30.0_real64,vt_status)
      CALL require(vt_status==STATUS_OK,'crossing rain terminal velocity')
      u(2,1,3)=REAL(1.6_real64*grid%dx(2,1)/source_dt,real32)
      source_dz=source_layer_distance(4,1,3,grid,pressure,temperature,vapor)
      source_dt=source_dz/terminal_velocity(PHASE_RAIN,65000.0_real64,280.0_real64, &
        10.0_real64*LOG10(4000.0_real64),vt_status)
      CALL require(vt_status==STATUS_OK,'crossing snow terminal velocity')
      u(4,1,3)=REAL(-1.6_real64*grid%dx(4,1)/source_dt,real32)
    CASE(CASE_BAD_SOURCE)
      CALL set_rain_source(1,1,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
      no_echo(1,1,3)=.TRUE.
    CASE(CASE_BAD_TERRAIN_SOURCE)
      domain(1,1,3)=.FALSE.
      CALL set_rain_source(1,1,3,observed,phase,zlinear,rain,1000.0_real64,1.0e-4_real64)
    CASE DEFAULT
      CALL require(.FALSE.,'unknown radar reference case')
    END SELECT
  END SUBROUTINE initialize_fixture

  SUBROUTINE allocate_grid(grid,nx,ny,nz,name)
    TYPE(grid_spec), INTENT(OUT) :: grid
    INTEGER, INTENT(IN) :: nx,ny,nz
    CHARACTER(*), INTENT(IN) :: name
    grid%nx=nx; grid%ny=ny; grid%nz=nz; grid%grid_id=name
    ALLOCATE(grid%dx(nx,ny),grid%dy(nx,ny),grid%pressure_interface(nx,ny,nz+1), &
      grid%cell_dp(nx,ny,nz),grid%level_spacing_dp(nx,ny,nz-1), &
      grid%pressure_mass_measure(nx,ny,nz),grid%dry_air_mass_measure(nx,ny,nz))
  END SUBROUTINE allocate_grid

  REAL(real64) FUNCTION source_layer_distance(i,j,k,grid,pressure,temperature,vapor)
    INTEGER, INTENT(IN) :: i,j,k
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real32), INTENT(IN) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:)
    REAL(real64) :: rho_g
    rho_g=REAL(pressure(i,j,k),real64)*(1.0_real64+REAL(vapor(i,j,k),real64))/ &
      (287.05_real64*REAL(temperature(i,j,k),real64)* &
      (1.0_real64+REAL(vapor(i,j,k),real64)/0.622_real64))
    source_layer_distance=grid%level_spacing_dp(i,j,k-1)/(rho_g*9.80665_real64)
  END FUNCTION source_layer_distance

  SUBROUTINE set_rain_source(i,j,k,observed,phase,zlinear,rain,zvalue,qvalue)
    INTEGER, INTENT(IN) :: i,j,k
    LOGICAL, INTENT(INOUT) :: observed(:,:,:)
    INTEGER, INTENT(INOUT) :: phase(:,:,:)
    REAL(real64), INTENT(INOUT) :: zlinear(:,:,:),rain(:,:,:)
    REAL(real64), INTENT(IN) :: zvalue,qvalue
    observed(i,j,k)=.TRUE.; phase(i,j,k)=PHASE_RAIN
    zlinear(i,j,k)=zvalue; rain(i,j,k)=qvalue
  END SUBROUTINE set_rain_source

  SUBROUTINE set_snow_source(i,j,k,observed,phase,zlinear,snow,zvalue,qvalue)
    INTEGER, INTENT(IN) :: i,j,k
    LOGICAL, INTENT(INOUT) :: observed(:,:,:)
    INTEGER, INTENT(INOUT) :: phase(:,:,:)
    REAL(real64), INTENT(INOUT) :: zlinear(:,:,:),snow(:,:,:)
    REAL(real64), INTENT(IN) :: zvalue,qvalue
    observed(i,j,k)=.TRUE.; phase(i,j,k)=PHASE_SNOW
    zlinear(i,j,k)=zvalue; snow(i,j,k)=qvalue
  END SUBROUTINE set_snow_source

  SUBROUTINE set_graupel_source(i,j,k,observed,phase,zlinear,graupel,zvalue,qvalue)
    INTEGER, INTENT(IN) :: i,j,k
    LOGICAL, INTENT(INOUT) :: observed(:,:,:)
    INTEGER, INTENT(INOUT) :: phase(:,:,:)
    REAL(real64), INTENT(INOUT) :: zlinear(:,:,:),graupel(:,:,:)
    REAL(real64), INTENT(IN) :: zvalue,qvalue
    observed(i,j,k)=.TRUE.; phase(i,j,k)=PHASE_GRAUPEL
    zlinear(i,j,k)=zvalue; graupel(i,j,k)=qvalue
  END SUBROUTINE set_graupel_source

  SUBROUTINE write_input_case(unit,name,grid,cfg,pressure,temperature,vapor,u,v,w, &
      domain,observed,no_echo,phase,zlinear,rain,snow,graupel)
    INTEGER, INTENT(IN) :: unit
    CHARACTER(*), INTENT(IN) :: name
    TYPE(grid_spec), INTENT(IN) :: grid
    TYPE(column_physics_config), INTENT(IN) :: cfg
    REAL(real32), INTENT(IN) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:),u(:,:,:),v(:,:,:),w(:,:,:)
    LOGICAL, INTENT(IN) :: domain(:,:,:),observed(:,:,:),no_echo(:,:,:)
    INTEGER, INTENT(IN) :: phase(:,:,:)
    REAL(real64), INTENT(IN) :: zlinear(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    INTEGER :: i,j,k
    WRITE(unit,'(A,1X,3(I0,1X))') 'CASE '//TRIM(name),grid%nx,grid%ny,grid%nz
    WRITE(unit,'(A,1X,ES24.16,1X,I0,1X,ES24.16)') 'CONFIG', &
      cfg%maximum_horizontal_substep,cfg%maximum_transport_substeps, &
      cfg%minimum_relative_fall_speed
    DO j=1,grid%ny; DO i=1,grid%nx
      WRITE(unit,'(A,1X,2(I0,1X),3(ES24.16,1X))') 'GRID',i,j,grid%dx(i,j), &
        grid%dy(i,j),grid%pressure_interface(i,j,1)
      DO k=1,grid%nz
        WRITE(unit,'(A,1X,3(I0,1X),3(ES24.16,1X))') 'INTERFACE',i,j,k, &
          grid%pressure_interface(i,j,k), &
          grid%pressure_interface(i,j,k+1),grid%cell_dp(i,j,k)
      END DO
      DO k=1,grid%nz-1
        WRITE(unit,'(A,1X,3(I0,1X),ES24.16)') 'SPACING',i,j,k,grid%level_spacing_dp(i,j,k)
      END DO
    END DO; END DO
    DO k=1,grid%nz; DO j=1,grid%ny; DO i=1,grid%nx
      WRITE(unit,'(A,1X,3(I0,1X),6(ES24.16,1X),3(L1,1X),I0,1X,4(ES24.16,1X))') &
        'CELL',i,j,k,pressure(i,j,k),temperature(i,j,k),vapor(i,j,k), &
        u(i,j,k),v(i,j,k),w(i,j,k),domain(i,j,k),observed(i,j,k),no_echo(i,j,k), &
        phase(i,j,k),zlinear(i,j,k),rain(i,j,k),snow(i,j,k),graupel(i,j,k)
    END DO; END DO; END DO
  END SUBROUTINE write_input_case

  SUBROUTINE write_output_case(unit,name,status,ledger,phase,zlinear,rain,snow,graupel)
    INTEGER, INTENT(IN) :: unit,status
    CHARACTER(*), INTENT(IN) :: name
    TYPE(precipitation_flux_ledger), INTENT(IN) :: ledger
    INTEGER, INTENT(IN) :: phase(:,:,:)
    REAL(real64), INTENT(IN) :: zlinear(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    INTEGER :: i,j,k
    WRITE(unit,'(A,1X,2(I0,1X),8(ES24.16,1X))') 'RESULT '//TRIM(name),status, &
      ledger%maximum_required_substeps,ledger%input, &
      ledger%deposited,ledger%suspended,ledger%boundary_exit,ledger%terrain_intercept, &
      ledger%observation_blocked,ledger%no_echo_blocked,ledger%microphysical_loss
    DO k=1,SIZE(phase,3); DO j=1,SIZE(phase,2); DO i=1,SIZE(phase,1)
      WRITE(unit,'(A,1X,4(I0,1X),4(ES24.16,1X))') 'OUT',i,j,k,phase(i,j,k), &
        zlinear(i,j,k),rain(i,j,k),snow(i,j,k),graupel(i,j,k)
    END DO; END DO; END DO
    WRITE(unit,*) 'ENDCASE'
  END SUBROUTINE write_output_case

  SUBROUTINE check_case(case_id,status,ledger,cfg,phase,phase_before,zlinear,z_before, &
      rain,rain_before,snow,snow_before,graupel,graupel_before)
    INTEGER, INTENT(IN) :: case_id,status
    TYPE(precipitation_flux_ledger), INTENT(IN) :: ledger
    TYPE(column_physics_config), INTENT(IN) :: cfg
    INTEGER, INTENT(IN) :: phase(:,:,:),phase_before(:,:,:)
    REAL(real64), INTENT(IN) :: zlinear(:,:,:),z_before(:,:,:),rain(:,:,:),rain_before(:,:,:)
    REAL(real64), INTENT(IN) :: snow(:,:,:),snow_before(:,:,:),graupel(:,:,:),graupel_before(:,:,:)
    LOGICAL :: rejected
    rejected=case_id==CASE_BAD_SOURCE .OR. case_id==CASE_BAD_TERRAIN_SOURCE .OR. &
      case_id==CASE_VARYING_METRIC
    IF (rejected) THEN
      CALL require(status==STATUS_FAILED,'invalid fixture must fail')
      CALL require(ALL(phase==phase_before) .AND. ALL(zlinear==z_before) .AND. &
        ALL(rain==rain_before) .AND. ALL(snow==snow_before) .AND. &
        ALL(graupel==graupel_before),'invalid fixture must be atomic')
      RETURN
    END IF
    CALL require(status==STATUS_OK,'valid fixture status')
    CALL require(flux_ledger_closes(ledger,cfg),'fixture ledger closure')
    SELECT CASE(case_id)
    CASE(CASE_TILT)
      CALL require(ledger%deposited>0.0_real64,'tilt/shear deposition')
      CALL require(ledger%maximum_required_substeps>0,'tilt/shear substep accounting')
    CASE(CASE_MULTI)
      CALL require(ledger%deposited>0.0_real64,'multi-level deposition')
      CALL require(SUM(rain)+SUM(snow)+SUM(graupel)>0.0_real64,'multi-species output')
    CASE(CASE_SOURCE_SUSPEND)
      CALL require(ledger%input>0.0_real64 .AND. ledger%suspended>0.0_real64 .AND. &
        ledger%deposited==0.0_real64,'source suspension')
    CASE(CASE_DEST_SUSPEND)
      CALL require(ledger%input>0.0_real64 .AND. ledger%suspended>0.0_real64 .AND. &
        ledger%deposited==0.0_real64,'destination suspension')
    CASE(CASE_OBS_BLOCK)
      CALL require(ledger%observation_blocked>0.0_real64 .AND. ledger%deposited==0.0_real64, &
        'observed destination block')
    CASE(CASE_NOECHO_BLOCK)
      CALL require(ledger%no_echo_blocked>0.0_real64 .AND. ledger%deposited==0.0_real64, &
        'no-echo destination block')
    CASE(CASE_BOUNDARY)
      CALL require(ledger%boundary_exit>0.0_real64,'boundary exit')
      CALL require(ledger%maximum_required_substeps>1,'boundary substeps')
    CASE(CASE_TERRAIN)
      CALL require(ledger%terrain_intercept>0.0_real64,'terrain intercept')
    CASE(CASE_VARYING_METRIC)
      CALL require(ledger%deposited>0.0_real64,'varying dx/dy deposition')
    CASE(CASE_SUBSTEPS)
      CALL require(ledger%deposited>0.0_real64 .AND. ledger%maximum_required_substeps>1, &
        'horizontal substeps')
    CASE(CASE_SUBSTEPS_FINE)
      CALL require(ledger%deposited>0.0_real64 .AND. ledger%maximum_required_substeps==4, &
        'fine horizontal substeps')
    CASE(CASE_CROSSING)
      CALL require(ledger%deposited>0.0_real64 .AND. ledger%maximum_required_substeps==3, &
        'crossing source substeps')
    END SELECT
  END SUBROUTINE check_case

  SUBROUTINE require(condition,label)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(*), INTENT(IN) :: label
    IF (.NOT.condition) THEN
      WRITE(*,*) 'FAIL:',TRIM(label)
      ERROR STOP 1
    END IF
  END SUBROUTINE require

END PROGRAM test_pressure_radar_reference
