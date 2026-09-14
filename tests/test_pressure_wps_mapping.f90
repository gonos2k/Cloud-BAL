PROGRAM test_pressure_wps_mapping
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state, ONLY: cloud_bal_state_type,field3d,field2d,STATUS_OK,STATUS_FAILED, &
       SOURCE_BACKGROUND_MODEL,SOURCE_ANALYZED_WIND,SOURCE_CLOUD_ANALYSIS, &
       SOURCE_COLUMN_PHYSICS,SOURCE_MANUFACTURED_TEST,initialize_cloud_bal_state, &
       configure_pressure_geometry,refresh_dry_air_mass_measure,canonical_states_equal,validate_canonical_state
  USE cloud_bal_wps_adapter, ONLY: pressure_wps_fields,map_pressure_candidate_to_wps
  USE setup, ONLY: valid_yyyy,valid_jjj,valid_hh,valid_min,hotstart,wind_coordinate,snow_thresh
  USE laps_static, ONLY: x,y,z3,grid_type
  USE lapsprep_wps, ONLY: output_ungrib_format
  IMPLICIT NONE

  INTEGER, PARAMETER :: NX=3,NY=2,NZ=3
  INTEGER, PARAMETER :: HIGH_NX=2,HIGH_NY=1,HIGH_NZ=22
  INTEGER(int64), PARAMETER :: VALID_TIME=1788233520_int64
  REAL(real32), PARAMETER :: P_CANON(NZ)=[95000.0_real32,80000.0_real32,65000.0_real32]
  REAL(real32), PARAMETER :: HIGH_P(HIGH_NZ)=[110000.0_real32,105000.0_real32,100000.0_real32,95000.0_real32, &
    90000.0_real32,85000.0_real32,80000.0_real32,75000.0_real32,70000.0_real32,65000.0_real32, &
    60000.0_real32,55000.0_real32,50000.0_real32,45000.0_real32,40000.0_real32,35000.0_real32, &
    30000.0_real32,25000.0_real32,20000.0_real32,15000.0_real32,10000.0_real32,5000.0_real32]
  CHARACTER(LEN=64), PARAMETER :: GRID_ID='pressure-wps-fixture'
  CHARACTER(LEN=16), PARAMETER :: WIND='GRID_RELATIVE'
  TYPE(cloud_bal_state_type) :: background,candidate,before_background,before_candidate
  TYPE(pressure_wps_fields) :: wps_background,mapped,mapped_before
  INTEGER :: status,failures
  CHARACTER(LEN=512) :: root

  CALL get_command_argument(1,root)
  IF (LEN_TRIM(root)==0) ERROR STOP 'test root is required'
  failures=0
  CALL make_canonical(background,status)
  CALL check(status==STATUS_OK,'canonical background fixture initializes',failures)
  candidate=background
  CALL overlay_candidate(candidate,status)
  CALL check(status==STATUS_OK,'canonical candidate fixture initializes',failures)
  CALL make_wps_background(background,wps_background,status)
  CALL check(status==STATUS_OK,'WPS background fixture initializes',failures)
  before_background=background; before_candidate=candidate

  CALL map_pressure_candidate_to_wps(candidate,wps_background,mapped,status,WIND)
  CALL check(status==STATUS_OK,'valid pressure candidate maps to WPS',failures)
  IF (status==STATUS_OK) THEN
    CALL check_mapping(mapped,wps_background,candidate,failures)
    mapped_before=mapped
    CALL write_wps_files(mapped,wps_background,TRIM(root),failures)
    CALL write_surface_height_files(mapped,TRIM(root),failures)
    CALL check_descending(candidate,wps_background,mapped,TRIM(root),failures)
  END IF
  CALL check(canonical_states_equal(background,before_background),'mapper preserves background state',failures)
  CALL check(canonical_states_equal(candidate,before_candidate),'mapper preserves candidate state',failures)
  IF (status==STATUS_OK) THEN
    CALL surface_boundary_cases(candidate,wps_background,mapped_before,failures)
    CALL rejection_cases(candidate,wps_background,mapped_before,failures)
  END IF
  IF (status==STATUS_OK) CALL high_level_fixture(TRIM(root),failures)

  IF (failures/=0) THEN
    PRINT '(A,I0)','Pressure/WPS mapping tests failed: ',failures
    ERROR STOP 1
  END IF
  PRINT '(A)','Pressure/WPS mapping tests passed'

CONTAINS

  SUBROUTINE check_descending(state,bg,ascending,dir,n,prefix)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(pressure_wps_fields), INTENT(IN) :: bg,ascending
    CHARACTER(*), INTENT(IN) :: dir
    INTEGER, INTENT(INOUT) :: n
    CHARACTER(*), INTENT(IN), OPTIONAL :: prefix
    TYPE(pressure_wps_fields) :: reversed,out
    INTEGER :: s,nlevels
    CHARACTER(LEN=512) :: output_file
    nlevels=SIZE(bg%p)-1
    reversed=bg
    reversed%p(1:nlevels)=bg%p(nlevels:1:-1)
    reversed%t(:,:,1:nlevels)=bg%t(:,:,nlevels:1:-1); reversed%ht(:,:,1:nlevels)=bg%ht(:,:,nlevels:1:-1)
    reversed%u(:,:,1:nlevels)=bg%u(:,:,nlevels:1:-1); reversed%v(:,:,1:nlevels)=bg%v(:,:,nlevels:1:-1)
    reversed%rh(:,:,1:nlevels)=bg%rh(:,:,nlevels:1:-1); reversed%qv(:,:,1:nlevels)=bg%qv(:,:,nlevels:1:-1)
    reversed%qc=bg%qc(:,:,nlevels:1:-1); reversed%qi=bg%qi(:,:,nlevels:1:-1)
    reversed%qr=bg%qr(:,:,nlevels:1:-1); reversed%qs=bg%qs(:,:,nlevels:1:-1); reversed%qg=bg%qg(:,:,nlevels:1:-1)
    CALL map_pressure_candidate_to_wps(state,reversed,out,s,WIND)
    CALL check(s==STATUS_OK,'descending pressure inventory maps',n)
    IF (s/=STATUS_OK) RETURN
    CALL check(ALL(out%t(:,:,1:nlevels)==ascending%t(:,:,nlevels:1:-1)), 'pressure order changes no physical value',n)
    IF (PRESENT(prefix)) THEN
      output_file=TRIM(dir)//'/'//TRIM(prefix)//'descending.wps'
    ELSE
      output_file=TRIM(dir)//'/pressure_descending.wps'
    END IF
    CALL output_ungrib_format(out%p,out%t,out%ht,out%u,out%v,out%rh,out%slp,out%psfc, &
      out%qc,out%qr,out%qs,out%qi,out%qg,out%snow_cover,out%skin_temperature,s, &
      resolved_output_file=TRIM(output_file),vapor_mixing_ratio=out%qv)
    CALL check(s==1,'descending WPS file written',n)
  END SUBROUTINE check_descending

  SUBROUTINE check(ok,message,n)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: n
    IF (.NOT.ok) THEN
      n=n+1; PRINT '(A)','FAIL: '//TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE make_canonical(state,status)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,local
    CALL initialize_cloud_bal_state(state,NX,NY,NZ,VALID_TIME,GRID_ID,status)
    IF (status/=STATUS_OK) RETURN
    state%grid%dx=2000.0_real64; state%grid%dy=3000.0_real64
    DO k=1,NZ
      state%pressure%value(:,:,k)=P_CANON(k)
      DO j=1,NY; DO i=1,NX
        state%temperature%value(i,j,k)=250.0_real32+2*i+3*j+4*k
        state%geopotential%value(i,j,k)=100.0_real32+11*i+17*j+23*k
        state%vapor%value(i,j,k)=0.001_real32+0.0001_real32*i+0.0002_real32*j+0.0003_real32*k
        state%u%value(i,j,k)=-7.0_real32+1.5_real32*i+2.5_real32*j+0.7_real32*k
        state%v%value(i,j,k)=4.0_real32-0.8_real32*i+1.7_real32*j-0.6_real32*k
        state%cloud_water%value(i,j,k)=0.00010_real32+0.00001_real32*i+0.00002_real32*j+0.00003_real32*k
        state%cloud_ice%value(i,j,k)=0.00020_real32+0.00001_real32*i+0.00002_real32*j+0.00004_real32*k
        state%rain%value(i,j,k)=0.00030_real32+0.00001_real32*i+0.00003_real32*j+0.00002_real32*k
        state%snow%value(i,j,k)=0.00040_real32+0.00002_real32*i+0.00001_real32*j+0.00003_real32*k
        state%graupel%value(i,j,k)=0.00050_real32+0.00003_real32*i+0.00002_real32*j+0.00001_real32*k
      END DO; END DO
    END DO
    CALL mark3(state%pressure,SOURCE_BACKGROUND_MODEL); CALL mark3(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%geopotential,SOURCE_BACKGROUND_MODEL); CALL mark3(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%u,SOURCE_BACKGROUND_MODEL); CALL mark3(state%v,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%cloud_water,SOURCE_CLOUD_ANALYSIS); CALL mark3(state%cloud_ice,SOURCE_CLOUD_ANALYSIS)
    CALL mark3(state%rain,SOURCE_CLOUD_ANALYSIS); CALL mark3(state%snow,SOURCE_CLOUD_ANALYSIS)
    CALL mark3(state%graupel,SOURCE_CLOUD_ANALYSIS)
    state%omega%value=0.0_real32; CALL mark3(state%omega,SOURCE_BACKGROUND_MODEL)
    state%surface_pressure%value=100000.0_real32; state%surface_pressure%value(2,1)=90000.0_real32
    state%surface_temperature%value=278.0_real32; state%surface_temperature%value(1,1)=281.0_real32
    CALL mark2(state%surface_pressure,SOURCE_BACKGROUND_MODEL); CALL mark2(state%surface_temperature,SOURCE_BACKGROUND_MODEL)
    CALL configure_pressure_geometry(state,local)
    IF (local/=STATUS_OK) THEN; status=local; RETURN; END IF
    CALL mask_below_ground(state)
    CALL refresh_dry_air_mass_measure(state,status)
  END SUBROUTINE make_canonical

  SUBROUTINE overlay_candidate(state,status)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,local
    DO k=1,NZ; DO j=1,NY; DO i=1,NX
      IF (state%above_ground(i,j,k)) THEN
        state%temperature%value(i,j,k)=275.0_real32+13*i+7*j+5*k
        state%geopotential%value(i,j,k)=500.0_real32+31*i+19*j+29*k
        state%vapor%value(i,j,k)=0.006_real32+0.0004_real32*i+0.0007_real32*j+0.0009_real32*k
        state%u%value(i,j,k)=21.0_real32+2*i+3*j+0.4_real32*k
        state%v%value(i,j,k)=-16.0_real32+i-2*j+0.8_real32*k
        state%cloud_water%value(i,j,k)=0.00110_real32+0.00011_real32*i+0.00012_real32*j+0.00013_real32*k
        state%cloud_ice%value(i,j,k)=0.00120_real32+0.00011_real32*i+0.00012_real32*j+0.00014_real32*k
        state%rain%value(i,j,k)=0.00130_real32+0.00011_real32*i+0.00013_real32*j+0.00012_real32*k
        state%snow%value(i,j,k)=0.00140_real32+0.00012_real32*i+0.00011_real32*j+0.00013_real32*k
        state%graupel%value(i,j,k)=0.00150_real32+0.00013_real32*i+0.00012_real32*j+0.00011_real32*k
      ELSE
        state%temperature%value(i,j,k)=-901.0_real32; state%geopotential%value(i,j,k)=-902.0_real32
        state%vapor%value(i,j,k)=0.00902_real32; state%u%value(i,j,k)=-903.0_real32; state%v%value(i,j,k)=-904.0_real32
        state%cloud_water%value(i,j,k)=0.00905_real32; state%cloud_ice%value(i,j,k)=0.00906_real32
        state%rain%value(i,j,k)=0.00907_real32; state%snow%value(i,j,k)=0.00908_real32; state%graupel%value(i,j,k)=0.00909_real32
      END IF
    END DO; END DO; END DO
    CALL mark3(state%temperature,SOURCE_CLOUD_ANALYSIS); CALL mark3(state%geopotential,SOURCE_COLUMN_PHYSICS)
    CALL mark3(state%vapor,SOURCE_CLOUD_ANALYSIS); CALL mark3(state%u,SOURCE_ANALYZED_WIND); CALL mark3(state%v,SOURCE_ANALYZED_WIND)
    CALL mark3(state%cloud_water,SOURCE_CLOUD_ANALYSIS); CALL mark3(state%cloud_ice,SOURCE_CLOUD_ANALYSIS)
    CALL mark3(state%rain,SOURCE_CLOUD_ANALYSIS); CALL mark3(state%snow,SOURCE_CLOUD_ANALYSIS)
    CALL mark3(state%graupel,SOURCE_CLOUD_ANALYSIS)
    state%surface_pressure%value=100700.0_real32; state%surface_pressure%value(2,1)=90000.0_real32
    state%surface_temperature%value=279.0_real32; state%surface_temperature%value(1,1)=283.0_real32
    CALL mark2(state%surface_pressure,SOURCE_CLOUD_ANALYSIS); CALL mark2(state%surface_temperature,SOURCE_CLOUD_ANALYSIS)
    CALL configure_pressure_geometry(state,local)
    IF (local/=STATUS_OK) THEN; status=local; RETURN; END IF
    CALL mask_below_ground(state)
    CALL refresh_dry_air_mass_measure(state,status)
  END SUBROUTINE overlay_candidate

  SUBROUTINE mark3(field,source)
    TYPE(field3d), INTENT(INOUT) :: field; INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE mark3
  SUBROUTINE mark2(field,source)
    TYPE(field2d), INTENT(INOUT) :: field; INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE mark2

  SUBROUTINE mask_below_ground(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    state%temperature%valid=state%above_ground
    state%geopotential%valid=state%above_ground
    state%vapor%valid=state%above_ground
    state%u%valid=state%above_ground; state%v%valid=state%above_ground
    state%omega%valid=state%above_ground
    state%cloud_water%valid=state%above_ground; state%cloud_ice%valid=state%above_ground
    state%rain%valid=state%above_ground; state%snow%valid=state%above_ground
    state%graupel%valid=state%above_ground
  END SUBROUTINE mask_below_ground

  SUBROUTINE make_wps_background(state,wps,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(pressure_wps_fields), INTENT(OUT) :: wps
    INTEGER, INTENT(OUT) :: status
    INTEGER :: k,ks
    status=STATUS_FAILED
    ALLOCATE(wps%p(NZ+1),wps%t(NX,NY,NZ+1),wps%ht(NX,NY,NZ+1),wps%u(NX,NY,NZ+1),wps%v(NX,NY,NZ+1), &
      wps%rh(NX,NY,NZ+1),wps%qv(NX,NY,NZ+1),wps%qc(NX,NY,NZ),wps%qi(NX,NY,NZ),wps%qr(NX,NY,NZ), &
      wps%qs(NX,NY,NZ),wps%qg(NX,NY,NZ),wps%psfc(NX,NY),wps%slp(NX,NY),wps%skin_temperature(NX,NY),wps%snow_cover(NX,NY))
    wps%p=[650.0_real32,800.0_real32,950.0_real32,2001.0_real32]
    DO k=1,NZ; ks=NZ-k+1
      wps%t(:,:,k)=state%temperature%value(:,:,ks); wps%ht(:,:,k)=state%geopotential%value(:,:,ks)/9.80665_real32
      wps%u(:,:,k)=state%u%value(:,:,ks); wps%v(:,:,k)=state%v%value(:,:,ks); wps%qv(:,:,k)=state%vapor%value(:,:,ks)
      wps%qc(:,:,k)=state%cloud_water%value(:,:,ks); wps%qi(:,:,k)=state%cloud_ice%value(:,:,ks)
      wps%qr(:,:,k)=state%rain%value(:,:,ks); wps%qs(:,:,k)=state%snow%value(:,:,ks); wps%qg(:,:,k)=state%graupel%value(:,:,ks)
    END DO
    wps%t(:,:,NZ+1)=state%surface_temperature%value; wps%ht(:,:,NZ+1)=100.0_real32
    wps%u(:,:,NZ+1)=3.0_real32; wps%v(:,:,NZ+1)=-4.0_real32; wps%qv(:,:,NZ+1)=0.004_real32
    wps%rh=55.0_real32; wps%psfc=state%surface_pressure%value; wps%slp=101000.0_real32
    wps%skin_temperature=290.0_real32; wps%snow_cover=0.25_real32
    wps%valid_time=VALID_TIME; wps%grid_id=GRID_ID; wps%wind_coordinate=WIND; status=STATUS_OK
  END SUBROUTINE make_wps_background

  SUBROUTINE check_mapping(wps,bg,state,n)
    TYPE(pressure_wps_fields), INTENT(IN) :: wps,bg
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(INOUT) :: n
    INTEGER :: i,j,k,ks
    CALL check(wps%p(NZ+1)==2001.0_real32,'2001 hPa surface marker retained',n)
    CALL check(wps%valid_time==VALID_TIME .AND. TRIM(wps%grid_id)==GRID_ID,'time/grid metadata retained',n)
    CALL check(TRIM(wps%wind_coordinate)==WIND,'wind coordinate is explicit',n)
    CALL check(wps%psfc(2,1)==90000.0_real32,'subterrain PSFC maps exactly',n)
    CALL check(ALL(wps%slp==bg%slp) .AND. ALL(wps%rh==bg%rh),'SLP and RH preserved exactly',n)
    CALL check(ALL(wps%u(:,:,NZ+1)==bg%u(:,:,NZ+1)) .AND. ALL(wps%v(:,:,NZ+1)==bg%v(:,:,NZ+1)), &
      'surface winds preserved exactly',n)
    CALL check(ALL(wps%qv(:,:,NZ+1)==bg%qv(:,:,NZ+1)),'surface vapor preserved exactly',n)
    CALL check(ALL(wps%ht(:,:,NZ+1)==bg%ht(:,:,NZ+1)),'surface height preserved exactly',n)
    CALL check(ALL(wps%skin_temperature==bg%skin_temperature) .AND. ALL(wps%snow_cover==bg%snow_cover), &
      'skin and snow slabs preserved exactly',n)
    DO k=1,NZ; ks=NZ-k+1
      CALL check(wps%p(k)==P_CANON(ks)/100.0_real32,'pressure coordinates map explicitly',n)
      DO j=1,NY; DO i=1,NX
        IF (state%above_ground(i,j,ks)) THEN
          CALL check(wps%t(i,j,k)==state%temperature%value(i,j,ks),'above-ground T overlay',n)
          CALL check(wps%u(i,j,k)==state%u%value(i,j,ks) .AND. wps%v(i,j,k)==state%v%value(i,j,ks),'above-ground wind overlay',n)
          CALL check(wps%qv(i,j,k)==state%vapor%value(i,j,ks),'above-ground QV overlay',n)
        ELSE
          CALL check(wps%t(i,j,k)==bg%t(i,j,k) .AND. wps%u(i,j,k)==bg%u(i,j,k),'below-ground values retained',n)
        END IF
      END DO; END DO
    END DO
  END SUBROUTINE check_mapping

  SUBROUTINE surface_boundary_cases(candidate,bg,good,n)
    TYPE(cloud_bal_state_type), INTENT(IN) :: candidate
    TYPE(pressure_wps_fields), INTENT(IN) :: bg,good
    INTEGER, INTENT(INOUT) :: n
    TYPE(cloud_bal_state_type) :: c
    TYPE(pressure_wps_fields) :: out
    REAL(real32) :: vapor_values(NX,NY),height_values(NX,NY)
    INTEGER :: i,j,s

    ! Optional boundary fields are invalid by default, so the pre-existing
    ! WPS surface slabs remain untouched.
    c=candidate
    c%surface_vapor%valid=.FALSE.; c%surface_height%valid=.FALSE.
    out=good
    CALL map_pressure_candidate_to_wps(c,bg,out,s,WIND)
    CALL check(s==STATUS_OK,'invalid optional surface fields are accepted',n)
    IF (s==STATUS_OK) THEN
      CALL check(ALL(out%qv(:,:,NZ+1)==bg%qv(:,:,NZ+1)) .AND. &
        ALL(out%ht(:,:,NZ+1)==bg%ht(:,:,NZ+1)), &
        'invalid optional surface fields retain background slabs',n)
    END IF

    DO j=1,NY; DO i=1,NX
      vapor_values(i,j)=0.020_real32+0.001_real32*REAL(i+2*j,real32)
      height_values(i,j)=400.0_real32+10.0_real32*REAL(i+3*j,real32)
    END DO; END DO

    ! An asymmetric case proves vapor overlays independently while height
    ! remains a retained background slab.
    c=candidate
    c%surface_vapor%value=vapor_values; c%surface_vapor%valid=.TRUE.
    c%surface_vapor%quality=0_int32; c%surface_vapor%source=SOURCE_BACKGROUND_MODEL
    c%surface_height%valid=.FALSE.
    out=good
    CALL map_pressure_candidate_to_wps(c,bg,out,s,WIND)
    CALL check(s==STATUS_OK,'valid surface vapor overlays independently',n)
    IF (s==STATUS_OK) THEN
      CALL check(ALL(out%qv(:,:,NZ+1)==vapor_values) .AND. &
        ALL(out%ht(:,:,NZ+1)==bg%ht(:,:,NZ+1)), &
        'asymmetric surface overlay preserves invalid height background',n)
    END IF

    ! Validity is cell-wise for both optional fields: invalid cells must not
    ! import even finite payload values from the candidate.
    c=candidate
    c%surface_vapor%value=vapor_values; c%surface_height%value=height_values
    c%surface_vapor%valid=.FALSE.; c%surface_height%valid=.FALSE.
    c%surface_vapor%valid(1,1)=.TRUE.; c%surface_vapor%valid(NX,NY)=.TRUE.
    c%surface_height%valid(2,1)=.TRUE.; c%surface_height%valid(NX,NY)=.TRUE.
    c%surface_vapor%quality=0_int32; c%surface_vapor%source=SOURCE_BACKGROUND_MODEL
    c%surface_height%quality=0_int32; c%surface_height%source=SOURCE_BACKGROUND_MODEL
    out=good
    CALL map_pressure_candidate_to_wps(c,bg,out,s,WIND)
    CALL check(s==STATUS_OK,'partially valid optional surface fields map',n)
    IF (s==STATUS_OK) THEN
      DO j=1,NY; DO i=1,NX
        IF (c%surface_vapor%valid(i,j)) THEN
          CALL check(out%qv(i,j,NZ+1)==vapor_values(i,j), &
            'valid surface vapor cell overlays',n)
        ELSE
          CALL check(out%qv(i,j,NZ+1)==bg%qv(i,j,NZ+1), &
            'invalid surface vapor cell retains background',n)
        END IF
        IF (c%surface_height%valid(i,j)) THEN
          CALL check(out%ht(i,j,NZ+1)==height_values(i,j), &
            'valid surface height cell overlays',n)
        ELSE
          CALL check(out%ht(i,j,NZ+1)==bg%ht(i,j,NZ+1), &
            'invalid surface height cell retains background',n)
        END IF
      END DO; END DO
    END IF
  END SUBROUTINE surface_boundary_cases

  SUBROUTINE rejection_cases(candidate,bg,good,n)
    TYPE(cloud_bal_state_type), INTENT(IN) :: candidate
    TYPE(pressure_wps_fields), INTENT(IN) :: bg,good
    INTEGER, INTENT(INOUT) :: n
    TYPE(cloud_bal_state_type) :: c,original
    TYPE(pressure_wps_fields) :: out,bad_bg
    INTEGER :: s
    original=candidate
    c=original; c%vapor%valid(1,1,1)=.FALSE.; CALL reject(c,bg,good,'missing QV validity',n)
    c=original; c%vapor%value(1,1,2)=ieee_value(0.0_real32,ieee_quiet_nan); CALL reject(c,bg,good,'NaN QV',n)
    c=original; c%vapor%value(1,1,2)=-0.25_real32; CALL reject(c,bg,good,'negative QV',n)
    c=original; c%pressure%value(1,1,2)=80001.0_real32; CALL reject(c,bg,good,'incompatible pressure',n)
    c=original; c%temperature%valid_time=VALID_TIME+1; CALL reject(c,bg,good,'incompatible time',n)
    c=original; c%grid%grid_id='other-grid'; CALL reject(c,bg,good,'incompatible grid',n)
    c=original; c%temperature%unit='degC'; CALL reject(c,bg,good,'invalid unit metadata',n)
    c=original; c%temperature%source=IOR(c%temperature%source,SOURCE_MANUFACTURED_TEST)
    CALL reject(c,bg,good,'manufactured source',n)
    c=original
    c%surface_vapor%valid=.TRUE.; c%surface_vapor%quality=0_int32
    c%surface_vapor%source=SOURCE_MANUFACTURED_TEST
    CALL reject(c,bg,good,'manufactured surface vapor source',n)
    c=original
    c%surface_height%valid=.TRUE.; c%surface_height%quality=0_int32
    c%surface_height%source=SOURCE_MANUFACTURED_TEST
    CALL reject(c,bg,good,'manufactured surface height source',n)
    c=original; c%u%valid(1,1,1)=.FALSE.; CALL reject(c,bg,good,'degraded wind coverage',n)
    c=original; c%temperature%value(2,1,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    c%geopotential%value(2,1,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    out=good; CALL map_pressure_candidate_to_wps(c,bg,out,s,WIND)
    CALL check(s==STATUS_OK,'unused below-ground NaNs retain explicit fill',n)
    IF (s==STATUS_OK) CALL check(ALL(out%t==good%t) .AND. ALL(out%ht==good%ht), &
      'unused missing values never enter WPS slabs',n)
    bad_bg=bg; bad_bg%p(3)=940.0_real32; out=good
    CALL map_pressure_candidate_to_wps(original,bad_bg,out,s,WIND)
    CALL check(s==STATUS_FAILED,'nearby but distinct pressure level rejected',n)
    bad_bg=bg; bad_bg%p(3)=1050.0_real32; out=good
    CALL map_pressure_candidate_to_wps(original,bad_bg,out,s,WIND)
    CALL check(s==STATUS_FAILED,'writer-skipped pressure level rejected',n)
    bad_bg=bg; DEALLOCATE(bad_bg%qv); out=good
    CALL map_pressure_candidate_to_wps(original,bad_bg,out,s,WIND)
    CALL check(s==STATUS_FAILED,'missing surface QV array rejected atomically',n)
    bad_bg=bg; bad_bg%rh(1,1,NZ+1)=150.0_real32; out=good
    CALL map_pressure_candidate_to_wps(original,bad_bg,out,s,WIND)
    CALL check(s==STATUS_OK,'producer-supported supersaturated RH retained',n)
    IF (s==STATUS_OK) CALL check(ALL(out%rh==bad_bg%rh),'RH is not clipped or recomputed',n)
    bad_bg%rh(1,1,NZ+1)=201.0_real32
    CALL map_pressure_candidate_to_wps(original,bad_bg,out,s,WIND)
    CALL check(s==STATUS_FAILED,'RH outside producer contract rejected',n)
    out=good; CALL map_pressure_candidate_to_wps(original,bg,out,s,'BAD-WIND')
    CALL check(s==STATUS_FAILED,'incompatible wind frame rejected',n)
    CALL check(canonical_states_equal(original,candidate),'rejection cases preserve candidate input',n)
  END SUBROUTINE rejection_cases

  SUBROUTINE high_level_fixture(dir,n)
    CHARACTER(*), INTENT(IN) :: dir
    INTEGER, INTENT(INOUT) :: n
    TYPE(cloud_bal_state_type) :: c,bad
    TYPE(pressure_wps_fields) :: bg,out
    INTEGER :: k,l,s,trial,reason
    REAL(real32), PARAMETER :: ps_cases(3)=[105000.0_real32,106000.0_real32,110000.0_real32]
    CALL initialize_cloud_bal_state(c,HIGH_NX,HIGH_NY,HIGH_NZ,VALID_TIME,GRID_ID,s)
    CALL check(s==STATUS_OK,'22-level state initializes',n)
    IF (s/=STATUS_OK) RETURN
    c%grid%dx=2000.0_real64; c%grid%dy=3000.0_real64
    DO k=1,HIGH_NZ
      c%pressure%value(:,:,k)=HIGH_P(k)
      c%temperature%value(:,:,k)=270.0_real32+REAL(k,real32)
      c%geopotential%value(:,:,k)=1000.0_real32*REAL(k,real32)
    END DO
    c%vapor%value=0.002_real32; c%u%value=5.0_real32; c%v%value=-2.0_real32
    CALL mark3(c%pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark3(c%temperature,SOURCE_BACKGROUND_MODEL); CALL mark3(c%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL mark3(c%vapor,SOURCE_BACKGROUND_MODEL); CALL mark3(c%u,SOURCE_BACKGROUND_MODEL)
    CALL mark3(c%v,SOURCE_BACKGROUND_MODEL); CALL mark3(c%omega,SOURCE_BACKGROUND_MODEL)
    CALL mark3(c%cloud_water,SOURCE_BACKGROUND_MODEL); CALL mark3(c%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL mark3(c%rain,SOURCE_BACKGROUND_MODEL); CALL mark3(c%snow,SOURCE_BACKGROUND_MODEL)
    CALL mark3(c%graupel,SOURCE_BACKGROUND_MODEL)
    c%surface_pressure%value=100000.0_real32; c%surface_temperature%value=280.0_real32
    CALL mark2(c%surface_pressure,SOURCE_BACKGROUND_MODEL); CALL mark2(c%surface_temperature,SOURCE_BACKGROUND_MODEL)
    CALL configure_pressure_geometry(c,s)
    CALL check(s==STATUS_OK,'22-level geometry configures',n)
    IF (s/=STATUS_OK) RETURN
    CALL mask_below_ground(c); CALL refresh_dry_air_mass_measure(c,s)
    CALL check(s==STATUS_OK,'22-level dry mass refreshes',n)
    IF (s/=STATUS_OK) RETURN
    ALLOCATE(bg%p(23),bg%t(2,1,23),bg%ht(2,1,23),bg%u(2,1,23),bg%v(2,1,23), &
      bg%rh(2,1,23),bg%qv(2,1,23),bg%qc(2,1,22),bg%qi(2,1,22), &
      bg%qr(2,1,22),bg%qs(2,1,22),bg%qg(2,1,22),bg%psfc(2,1),bg%slp(2,1), &
      bg%skin_temperature(2,1),bg%snow_cover(2,1))
    bg%p(1:22)=HIGH_P(22:1:-1)/100.0_real32; bg%p(23)=2001.0_real32
    bg%t=260.0_real32; bg%ht=100.0_real32; bg%u=1.0_real32; bg%v=2.0_real32
    bg%rh=55.0_real32; bg%qv=0.001_real32
    bg%qc=0.0_real32; bg%qi=0.0_real32; bg%qr=0.0_real32; bg%qs=0.0_real32; bg%qg=0.0_real32
    bg%psfc=100000.0_real32; bg%slp=101000.0_real32
    bg%skin_temperature=280.0_real32; bg%snow_cover=0.0_real32
    bg%valid_time=VALID_TIME; bg%grid_id=GRID_ID; bg%wind_coordinate=WIND
    CALL map_pressure_candidate_to_wps(c,bg,out,s,WIND)
    CALL check(s==STATUS_OK,'22-level inventory maps with inactive 1050/1100 levels',n)
    IF (s/=STATUS_OK) RETURN
    CALL check(SIZE(out%p)==23 .AND. ALL(out%p==bg%p),'mapping retains complete pressure inventory',n)
    CALL check(ALL(out%t(:,:,21:22)==bg%t(:,:,21:22)), 'skipped inactive fills remain unchanged',n)
    DO l=1,20
      k=23-l
      CALL check(ALL(out%t(:,:,l)==c%temperature%value(:,:,k)), 'all represented levels are mapped',n)
    END DO
    x=2; y=1; z3=22
    CALL output_ungrib_format(out%p,out%t,out%ht,out%u,out%v,out%rh,out%slp,out%psfc, &
      out%qc,out%qr,out%qs,out%qi,out%qg,out%snow_cover,out%skin_temperature,s, &
      resolved_output_file=TRIM(dir)//'/pressure_full22.wps',vapor_mixing_ratio=out%qv)
    CALL check(s==1,'22-level inventory reaches actual writer',n)
    CALL check_descending(c,bg,out,dir,n,'pressure_full22_')
    DO trial=1,SIZE(ps_cases)
      bad=c; bad%surface_pressure%value(2,1)=ps_cases(trial)
      CALL configure_pressure_geometry(bad,s)
      CALL check(s==STATUS_OK,'active high-pressure geometry configures',n)
      IF (s/=STATUS_OK) CYCLE
      CALL mask_below_ground(bad); CALL refresh_dry_air_mass_measure(bad,s)
      CALL check(s==STATUS_OK,'active high-pressure mass refreshes',n)
      IF (s/=STATUS_OK) CYCLE
      CALL check(bad%above_ground(2,1,2), '1050 hPa cell is genuinely represented',n)
      CALL validate_canonical_state(bad,.FALSE.,.TRUE.,s,reason,.TRUE.)
      CALL check(s==STATUS_OK,'high-pressure rejection input is otherwise canonical',n)
      IF (s/=STATUS_OK) CYCLE
      CALL reject(bad,bg,out,'represented writer-skipped level',n)
    END DO
  END SUBROUTINE high_level_fixture

  SUBROUTINE reject(c,bg,good,label,n)
    TYPE(cloud_bal_state_type), INTENT(IN) :: c
    TYPE(pressure_wps_fields), INTENT(IN) :: bg,good
    CHARACTER(*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: n
    TYPE(pressure_wps_fields) :: out
    INTEGER :: s
    out=good; CALL map_pressure_candidate_to_wps(c,bg,out,s,WIND)
    CALL check(s==STATUS_FAILED,'atomic reject: '//TRIM(label),n)
    CALL check(ALL(out%p==good%p) .AND. ALL(out%t==good%t) .AND. &
      ALL(out%ht==good%ht) .AND. ALL(out%u==good%u) .AND. ALL(out%v==good%v) .AND. &
      ALL(out%rh==good%rh) .AND. ALL(out%qv==good%qv) .AND. &
      ALL(out%qc==good%qc) .AND. ALL(out%qi==good%qi) .AND. ALL(out%qr==good%qr) .AND. &
      ALL(out%qs==good%qs) .AND. ALL(out%qg==good%qg) .AND. ALL(out%psfc==good%psfc) .AND. &
      ALL(out%slp==good%slp) .AND. ALL(out%skin_temperature==good%skin_temperature) .AND. &
      ALL(out%snow_cover==good%snow_cover) .AND. out%valid_time==good%valid_time .AND. &
      out%grid_id==good%grid_id .AND. out%wind_coordinate==good%wind_coordinate, &
      'rejection preserves existing output inventory: '//TRIM(label),n)
  END SUBROUTINE reject

  SUBROUTINE write_wps_files(mapped,bg,dir,n)
    TYPE(pressure_wps_fields), INTENT(IN) :: mapped,bg
    CHARACTER(*), INTENT(IN) :: dir
    INTEGER, INTENT(INOUT) :: n
    INTEGER :: s
    x=NX; y=NY; z3=NZ; hotstart=.TRUE.; wind_coordinate=WIND; grid_type='mercator'
    valid_yyyy=2026; valid_jjj=244; valid_hh=3; valid_min=32; snow_thresh=0.5
    CALL output_ungrib_format(mapped%p,mapped%t,mapped%ht,mapped%u,mapped%v,mapped%rh,mapped%slp,mapped%psfc, &
      mapped%qc,mapped%qr,mapped%qs,mapped%qi,mapped%qg,mapped%snow_cover,mapped%skin_temperature,s, &
      resolved_output_file=TRIM(dir)//'/pressure_candidate.wps',vapor_mixing_ratio=mapped%qv)
    CALL check(s==1,'candidate WPS output succeeds',n)
    CALL output_ungrib_format(bg%p,bg%t,bg%ht,bg%u,bg%v,bg%rh,bg%slp,bg%psfc,bg%qc,bg%qr,bg%qs,bg%qi,bg%qg, &
      bg%snow_cover,bg%skin_temperature,s,resolved_output_file=TRIM(dir)//'/pressure_background.wps',vapor_mixing_ratio=bg%qv)
    CALL check(s==1,'background WPS output succeeds',n)
  END SUBROUTINE write_wps_files

  SUBROUTINE write_surface_height_files(mapped,dir,n)
    TYPE(pressure_wps_fields), INTENT(IN) :: mapped
    CHARACTER(*), INTENT(IN) :: dir
    INTEGER, INTENT(INOUT) :: n
    TYPE(pressure_wps_fields) :: surface
    REAL(real32), ALLOCATABLE :: bad_shape(:,:,:),bad_nan(:,:,:)
    INTEGER :: i,j

    surface=mapped
    DO j=1,NY; DO i=1,NX
      surface%ht(i,j,NZ+1)=100.0_real32+10.0_real32*REAL(i,real32)+REAL(j,real32)
    END DO; END DO
    CALL write_surface_height_attempt(surface,surface%ht,TRIM(dir)//'/pressure_surface_height.wps', &
      .TRUE.,'explicit surface height output',n)

    ALLOCATE(bad_shape(NX,NY,NZ),bad_nan(NX,NY,NZ+1))
    bad_shape=0.0_real32
    CALL write_surface_height_attempt(surface,bad_shape,TRIM(dir)//'/pressure_surface_height_bad_shape.wps', &
      .FALSE.,'surface height shape rejection before writer',n)
    bad_nan=surface%ht
    bad_nan(1,1,NZ+1)=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL write_surface_height_attempt(surface,bad_nan,TRIM(dir)//'/pressure_surface_height_nan.wps', &
      .FALSE.,'NaN surface height rejection before writer',n)
  END SUBROUTINE write_surface_height_files

  SUBROUTINE write_surface_height_attempt(data,height,path,expect_success,label,n)
    TYPE(pressure_wps_fields), INTENT(IN) :: data
    REAL(real32), INTENT(IN) :: height(:,:,:)
    CHARACTER(*), INTENT(IN) :: path,label
    LOGICAL, INTENT(IN) :: expect_success
    INTEGER, INTENT(INOUT) :: n
    INTEGER :: s
    LOGICAL :: exists
    CALL output_ungrib_format(data%p,data%t,height,data%u,data%v,data%rh,data%slp,data%psfc, &
      data%qc,data%qr,data%qs,data%qi,data%qg,data%snow_cover,data%skin_temperature,s, &
      resolved_output_file=TRIM(path),vapor_mixing_ratio=data%qv,include_surface_height=.TRUE.)
    CALL check((s==1) .EQV. expect_success,TRIM(label)//' status',n)
    INQUIRE(FILE=TRIM(path),EXIST=exists)
    CALL check(exists .EQV. expect_success,TRIM(label)//' file publication',n)
  END SUBROUTINE write_surface_height_attempt

END PROGRAM test_pressure_wps_mapping
