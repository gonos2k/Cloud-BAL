PROGRAM test_legacy_shadow_adapter
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
  USE cloud_bal_legacy_shadow_adapter
  IMPLICIT NONE

  TYPE(legacy_pre_qbal_arrays) :: legacy,original,call_snapshot
  TYPE(legacy_shadow_config) :: config
  TYPE(cloud_bal_state_type) :: candidate
  TYPE(cloud_bal_pipeline_result) :: result
  INTEGER :: failures
  REAL(real32), PARAMETER :: GRAVITY=9.80665_real32

  failures=0

  CALL make_valid_legacy(legacy)
  original=legacy
  CALL run_legacy_pre_qbal_shadow(legacy,candidate,result)
  CALL check(result%status==STATUS_OK,'valid closure must run in SHADOW',failures)
  CALL check(result%requested_mode==MODE_SHADOW,'adapter must force SHADOW',failures)
  CALL check(same_legacy_bits(legacy,original), &
             'successful call changed caller arrays',failures)
  CALL check(ABS(candidate%pressure%value(1,1,1)-90000.0_real32)<0.01_real32 .AND. &
             ABS(candidate%pressure%value(1,1,3)-50000.0_real32)<0.01_real32, &
             'top-to-bottom pressure was not normalized',failures)
  CALL check(candidate%grid%dx(1,1)==2000.0_real64 .AND. &
             candidate%grid%dy(1,1)==2200.0_real64, &
             'grid distance unit was not normalized',failures)
  CALL check(ABS(candidate%vapor%value(1,1,1)- &
             0.010_real32/(1.0_real32-0.010_real32))<1.0e-7_real32, &
             'specific humidity was not converted to dry-air mixing ratio',failures)
  CALL check(ABS(candidate%geopotential%value(1,1,1)- &
             1000.0_real32*GRAVITY)<0.02_real32, &
             'height was not converted to geopotential',failures)

  legacy=original
  CALL add_terrain_mask(legacy,1,1,3)
  legacy%omega%value(1,1,2)=0.25_real32
  call_snapshot=legacy
  CALL run_legacy_pre_qbal_shadow(legacy,candidate,result)
  CALL check(result%status==STATUS_OK .AND. &
             .NOT.candidate%above_ground(1,1,1) .AND. &
             ALL(candidate%above_ground(1,1,2:3)) .AND. &
             .NOT.candidate%u%valid(1,1,1) .AND. &
             candidate%pressure%value(1,1,1)==90000.0_real32 .AND. &
             candidate%omega_bottom_boundary%value(1,1)==0.25_real32 .AND. &
             IAND(candidate%omega_top_boundary%quality(1,1), &
                   QUALITY_BOUNDARY_INTERIOR_COPY)/=0_int32 .AND. &
             IAND(candidate%omega_bottom_boundary%quality(1,1), &
                   QUALITY_BOUNDARY_INTERIOR_COPY)/=0_int32, &
             'terrain mask or lower boundary was not normalized',failures)
  CALL check(same_legacy_bits(legacy,call_snapshot), &
             'terrain normalization changed caller arrays',failures)

  legacy=original
  legacy%cloud_omega%value(2,2,2)=0.2_real32
  call_snapshot=legacy
  CALL run_legacy_pre_qbal_shadow(legacy,candidate,result)
  CALL check(result%status==STATUS_OK .AND. &
             candidate%omega_target%value(2,2,2)==0.2_real32 .AND. &
             .NOT.ANY(candidate%balance_beta>0.0_real32) .AND. &
             ALL(candidate%omega%value==reverse_levels(legacy%omega%value)), &
             'legacy cloud COM gained unsupported wind authority',failures)
  CALL check(same_legacy_bits(legacy,call_snapshot), &
             'cloud COM SHADOW call changed operational arrays',failures)

  legacy=original
  legacy%closure_bits=IEOR(legacy%closure_bits,CLOSURE_CLOUD_FORCING)
  call_snapshot=legacy
  CALL run_legacy_pre_qbal_shadow(legacy,candidate,result)
  CALL check(result%status==STATUS_FAILED .AND. &
             result%reason_code==REASON_REQUIRED_COVERAGE, &
             'missing direct QBAL closure was accepted',failures)
  CALL check(same_legacy_bits(legacy,call_snapshot), &
             'closure rejection changed caller arrays',failures)

  legacy=legacy_pre_qbal_arrays()
  legacy%analysis_time=original%analysis_time
  legacy%grid_id=original%grid_id
  legacy%closure_manifest_sha256=original%closure_manifest_sha256
  legacy%closure_bits=CLOSURE_REQUIRED_BITS
  CALL run_legacy_pre_qbal_shadow(legacy,candidate,result)
  CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_SHAPE, &
             'unallocated legacy arrays did not fail closed',failures)

  legacy=original
  legacy%u%source(2,2,2)=0_int32
  CALL assert_metadata_rejection(legacy,'source=0',failures)

  legacy=original
  legacy%u%quality(2,2,2)=QUALITY_QC_REJECTED
  CALL assert_metadata_rejection(legacy,'QC-rejected cell',failures)

  legacy=original
  legacy%u%valid_time=legacy%analysis_time-60_int64
  CALL assert_metadata_rejection(legacy,'time mismatch',failures)

  legacy=original
  legacy%cloud_analysis_declared=.TRUE.
  CALL set_cloud_cell(legacy,2,2,2,.FALSE.)
  call_snapshot=legacy
  CALL run_legacy_pre_qbal_shadow(legacy,candidate,result)
  CALL check(result%status==STATUS_FAILED .AND. &
             result%reason_code==REASON_RADAR_CONTRACT, &
             'unpaired cloud metadata was accepted',failures)
  CALL check(same_legacy_bits(legacy,call_snapshot), &
             'cloud ambiguity rejection changed operational arrays',failures)

  legacy=original
  legacy%radar_reflectivity%valid(2,2,2)=.TRUE.
  legacy%radar_reflectivity%quality(2,2,2)=0_int32
  legacy%radar_reflectivity%source(2,2,2)=SOURCE_RADAR_DBZ
  legacy%radar_reflectivity%value(2,2,2)=30.0_real32
  call_snapshot=legacy
  CALL run_legacy_pre_qbal_shadow(legacy,candidate,result)
  CALL check(result%status==STATUS_FAILED .AND. &
             result%reason_code==REASON_RADAR_CONTRACT, &
             'undeclared radar data was accepted',failures)
  CALL check(same_legacy_bits(legacy,call_snapshot), &
             'radar ambiguity rejection changed operational arrays',failures)

  legacy=original
  legacy%cloud_analysis_declared=.TRUE.
  CALL set_cloud_cell(legacy,2,2,2,.TRUE.)
  call_snapshot=legacy
  CALL run_legacy_pre_qbal_shadow(legacy,candidate,result)
  CALL check(result%status==STATUS_DEGRADED .AND. &
             result%reason_code==REASON_REQUIRED_COVERAGE, &
             'cloud contradiction must return DEGRADED',failures)
  CALL check(candidate%cloud_fraction%value(2,2,2)==0.0_real32 .AND. &
             candidate%cloud_type%value(2,2,2)==1_int32 .AND. &
             ALL(candidate%u%value==reverse_levels(legacy%u%value)), &
             'DEGRADED result leaked a partial candidate',failures)
  CALL check(same_legacy_bits(legacy,call_snapshot), &
             'DEGRADED call changed operational arrays',failures)

  legacy=original
  legacy%radar_analysis_declared=.TRUE.
  CALL set_radar_cell(legacy,2,2,2,99_int32)
  call_snapshot=legacy
  CALL run_legacy_pre_qbal_shadow(legacy,candidate,result)
  CALL check(result%status==STATUS_FAILED .AND. &
             result%reason_code==REASON_RANGE, &
             'invalid precipitation phase must fail',failures)
  CALL check(same_legacy_bits(legacy,call_snapshot), &
             'phase-range rejection changed operational arrays',failures)

  legacy=original
  config=legacy_shadow_config()
  config%column%radar_wavelength_m=-1.0_real64
  call_snapshot=legacy
  CALL run_legacy_pre_qbal_shadow(legacy,candidate,result,config)
  CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_RANGE, &
             'invalid pipeline configuration did not fail',failures)
  CALL check(ALL(candidate%u%value==reverse_levels(legacy%u%value)) .AND. &
             ALL(candidate%omega%value==reverse_levels(legacy%omega%value)), &
             'FAILED pipeline result leaked a partial candidate',failures)
  CALL check(same_legacy_bits(legacy,call_snapshot), &
             'FAILED pipeline call changed operational arrays',failures)

  IF (failures/=0) THEN
    PRINT *,'Legacy SHADOW adapter tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Legacy pre-QBAL SHADOW adapter tests passed'

CONTAINS

  SUBROUTINE make_valid_legacy(input)
    TYPE(legacy_pre_qbal_arrays), INTENT(OUT) :: input
    INTEGER, PARAMETER :: NX=4,NY=4,NZ=3
    INTEGER :: k
    INTEGER(int64), PARAMETER :: ANALYSIS_TIME=1788224400_int64

    input%analysis_time=ANALYSIS_TIME
    input%grid_id='legacy-adapter-test'
    input%closure_manifest_sha256=REPEAT('a',64)
    input%closure_bits=CLOSURE_REQUIRED_BITS
    input%vertical_order=LEGACY_TOP_TO_BOTTOM
    input%wind_coordinate=LEGACY_WIND_GRID_RELATIVE
    input%grid_spacing_unit='km'
    ALLOCATE(input%dx(NX,NY),input%dy(NX,NY),input%above_ground(NX,NY,NZ))
    input%dx=2.0_real64; input%dy=2.2_real64
    input%above_ground=.TRUE.

    CALL initialize_field(input%pressure,NX,NY,NZ,ANALYSIS_TIME,'hPa')
    CALL initialize_field(input%temperature,NX,NY,NZ,ANALYSIS_TIME,'K')
    CALL initialize_field(input%specific_humidity,NX,NY,NZ,ANALYSIS_TIME,'kg/kg')
    CALL initialize_field(input%u,NX,NY,NZ,ANALYSIS_TIME,'m s-1')
    CALL initialize_field(input%v,NX,NY,NZ,ANALYSIS_TIME,'m s-1')
    CALL initialize_field(input%omega,NX,NY,NZ,ANALYSIS_TIME,'Pa s-1')
    CALL initialize_field(input%geopotential_height,NX,NY,NZ,ANALYSIS_TIME,'m')
    CALL initialize_field(input%cloud_omega,NX,NY,NZ,ANALYSIS_TIME,'Pa s-1')
    CALL initialize_field(input%cloud_fraction,NX,NY,NZ,ANALYSIS_TIME,'1')
    CALL initialize_integer_field(input%cloud_type,NX,NY,NZ,ANALYSIS_TIME, &
                                  'cloud_type_v1')
    CALL initialize_field(input%radar_reflectivity,NX,NY,NZ,ANALYSIS_TIME,'dBZ')
    CALL initialize_integer_field(input%precipitation_phase,NX,NY,NZ,ANALYSIS_TIME, &
                                  'precipitation_phase_v1')
    CALL initialize_field(input%surface_pressure,NX,NY,ANALYSIS_TIME,'hPa')
    CALL initialize_field(input%latitude,NX,NY,ANALYSIS_TIME,'degree_north')

    DO k=1,NZ
      input%pressure%value(:,:,k)=REAL(300+200*k,real32)
      input%temperature%value(:,:,k)=REAL(250+10*k,real32)
      input%specific_humidity%value(:,:,k)=0.004_real32+0.002_real32*REAL(k,real32)
      input%u%value(:,:,k)=REAL(k,real32)
      input%v%value(:,:,k)=-REAL(k,real32)
      input%omega%value(:,:,k)=0.0_real32
      input%geopotential_height%value(:,:,k)=REAL(7000-2000*k,real32)
      input%cloud_omega%value(:,:,k)=0.0_real32
    END DO
    CALL mark_required3(input%pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark_required3(input%temperature,SOURCE_CONVENTIONAL_OBS)
    CALL mark_required3(input%specific_humidity,SOURCE_CONVENTIONAL_OBS)
    CALL mark_required3(input%u,SOURCE_ANALYZED_WIND)
    CALL mark_required3(input%v,SOURCE_ANALYZED_WIND)
    CALL mark_required3(input%omega,SOURCE_ANALYZED_WIND)
    CALL mark_required3(input%geopotential_height,SOURCE_CONVENTIONAL_OBS)
    CALL mark_required3(input%cloud_omega,SOURCE_CLOUD_ANALYSIS)
    input%surface_pressure%value=1000.0_real32
    input%surface_pressure%valid=.TRUE.
    input%surface_pressure%quality=0_int32
    input%surface_pressure%source=SOURCE_CONVENTIONAL_OBS
    input%latitude%value=36.0_real32
    input%latitude%valid=.TRUE.
    input%latitude%quality=0_int32
    input%latitude%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE make_valid_legacy

  SUBROUTINE mark_required3(field,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE mark_required3

  SUBROUTINE set_cloud_cell(input,i,j,k,paired)
    TYPE(legacy_pre_qbal_arrays), INTENT(INOUT) :: input
    INTEGER, INTENT(IN) :: i,j,k
    LOGICAL, INTENT(IN) :: paired
    input%cloud_fraction%valid(i,j,k)=.TRUE.
    input%cloud_fraction%quality(i,j,k)=0_int32
    input%cloud_fraction%source(i,j,k)=SOURCE_CLOUD_ANALYSIS
    input%cloud_fraction%value(i,j,k)=0.0_real32
    IF (paired) THEN
      input%cloud_type%valid(i,j,k)=.TRUE.
      input%cloud_type%quality(i,j,k)=0_int32
      input%cloud_type%source(i,j,k)=SOURCE_CLOUD_ANALYSIS
      input%cloud_type%value(i,j,k)=1_int32
    END IF
  END SUBROUTINE set_cloud_cell

  SUBROUTINE add_terrain_mask(input,i,j,k)
    TYPE(legacy_pre_qbal_arrays), INTENT(INOUT) :: input
    INTEGER, INTENT(IN) :: i,j,k
    input%above_ground(i,j,k)=.FALSE.
    input%surface_pressure%value(i,j)=input%pressure%value(i,j,k)-50.0_real32
    CALL invalidate_real(input%pressure,i,j,k)
    CALL invalidate_real(input%temperature,i,j,k)
    CALL invalidate_real(input%specific_humidity,i,j,k)
    CALL invalidate_real(input%u,i,j,k)
    CALL invalidate_real(input%v,i,j,k)
    CALL invalidate_real(input%omega,i,j,k)
    CALL invalidate_real(input%geopotential_height,i,j,k)
    CALL invalidate_real(input%cloud_omega,i,j,k)
  END SUBROUTINE add_terrain_mask

  SUBROUTINE invalidate_real(field,i,j,k)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: i,j,k
    field%valid(i,j,k)=.FALSE.
    field%quality(i,j,k)=QUALITY_RAW_MISSING
    field%source(i,j,k)=0_int32
  END SUBROUTINE invalidate_real

  SUBROUTINE set_radar_cell(input,i,j,k,phase)
    TYPE(legacy_pre_qbal_arrays), INTENT(INOUT) :: input
    INTEGER, INTENT(IN) :: i,j,k
    INTEGER(int32), INTENT(IN) :: phase
    input%radar_reflectivity%valid(i,j,k)=.TRUE.
    input%radar_reflectivity%quality(i,j,k)=0_int32
    input%radar_reflectivity%source(i,j,k)=SOURCE_RADAR_DBZ
    input%radar_reflectivity%value(i,j,k)=30.0_real32
    input%precipitation_phase%valid(i,j,k)=.TRUE.
    input%precipitation_phase%quality(i,j,k)=0_int32
    input%precipitation_phase%source(i,j,k)=SOURCE_RADAR_DBZ
    input%precipitation_phase%value(i,j,k)=phase
  END SUBROUTINE set_radar_cell

  SUBROUTINE assert_metadata_rejection(input,label,count)
    TYPE(legacy_pre_qbal_arrays), INTENT(IN) :: input
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: count
    TYPE(legacy_pre_qbal_arrays) :: before
    TYPE(cloud_bal_state_type) :: rejected
    TYPE(cloud_bal_pipeline_result) :: rejected_result
    before=input
    CALL run_legacy_pre_qbal_shadow(input,rejected,rejected_result)
    CALL check(rejected_result%status==STATUS_FAILED .AND. &
               rejected_result%reason_code==REASON_METADATA, &
               TRIM(label)//' was accepted',count)
    CALL check(same_legacy_bits(input,before), &
               TRIM(label)//' rejection changed caller arrays',count)
  END SUBROUTINE assert_metadata_rejection

  SUBROUTINE check(condition,message,count)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: count
    IF (.NOT.condition) THEN
      count=count+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  PURE FUNCTION reverse_levels(value) RESULT(reversed)
    REAL(real32), INTENT(IN) :: value(:,:,:)
    REAL(real32) :: reversed(SIZE(value,1),SIZE(value,2),SIZE(value,3))
    INTEGER :: k
    DO k=1,SIZE(value,3)
      reversed(:,:,k)=value(:,:,SIZE(value,3)+1-k)
    END DO
  END FUNCTION reverse_levels

  PURE LOGICAL FUNCTION same_legacy_bits(left,right)
    TYPE(legacy_pre_qbal_arrays), INTENT(IN) :: left,right
    same_legacy_bits=left%analysis_time==right%analysis_time .AND. &
      left%grid_id==right%grid_id .AND. &
      left%closure_manifest_sha256==right%closure_manifest_sha256 .AND. &
      left%closure_bits==right%closure_bits .AND. &
      left%vertical_order==right%vertical_order .AND. &
      left%wind_coordinate==right%wind_coordinate .AND. &
      left%grid_spacing_unit==right%grid_spacing_unit .AND. &
      (left%cloud_analysis_declared.EQV.right%cloud_analysis_declared) .AND. &
      (left%radar_analysis_declared.EQV.right%radar_analysis_declared) .AND. &
      same_real64_bits2(left%dx,right%dx) .AND. &
      same_real64_bits2(left%dy,right%dy) .AND. &
      ALL(left%above_ground.EQV.right%above_ground) .AND. &
      same_field3(left%pressure,right%pressure) .AND. &
      same_field3(left%temperature,right%temperature) .AND. &
      same_field3(left%specific_humidity,right%specific_humidity) .AND. &
      same_field3(left%u,right%u) .AND. same_field3(left%v,right%v) .AND. &
      same_field3(left%omega,right%omega) .AND. &
      same_field3(left%geopotential_height,right%geopotential_height) .AND. &
      same_field3(left%cloud_omega,right%cloud_omega) .AND. &
      same_field3(left%cloud_fraction,right%cloud_fraction) .AND. &
      same_integer3(left%cloud_type,right%cloud_type) .AND. &
      same_field3(left%radar_reflectivity,right%radar_reflectivity) .AND. &
      same_integer3(left%precipitation_phase,right%precipitation_phase) .AND. &
      same_field2(left%surface_pressure,right%surface_pressure) .AND. &
      same_field2(left%latitude,right%latitude)
  END FUNCTION same_legacy_bits

  PURE LOGICAL FUNCTION same_field3(left,right)
    TYPE(field3d), INTENT(IN) :: left,right
    same_field3=same_real32_bits3(left%value,right%value) .AND. &
      ALL(left%valid.EQV.right%valid) .AND. &
      ALL(left%quality==right%quality) .AND. ALL(left%source==right%source) .AND. &
      left%valid_time==right%valid_time .AND. left%unit==right%unit
  END FUNCTION same_field3

  PURE LOGICAL FUNCTION same_field2(left,right)
    TYPE(field2d), INTENT(IN) :: left,right
    same_field2=same_real32_bits2(left%value,right%value) .AND. &
      ALL(left%valid.EQV.right%valid) .AND. &
      ALL(left%quality==right%quality) .AND. ALL(left%source==right%source) .AND. &
      left%valid_time==right%valid_time .AND. left%unit==right%unit
  END FUNCTION same_field2

  PURE LOGICAL FUNCTION same_integer3(left,right)
    TYPE(integer_field3d), INTENT(IN) :: left,right
    same_integer3=ALL(left%value==right%value) .AND. &
      ALL(left%valid.EQV.right%valid) .AND. &
      ALL(left%quality==right%quality) .AND. ALL(left%source==right%source) .AND. &
      left%valid_time==right%valid_time .AND. left%code_table==right%code_table
  END FUNCTION same_integer3

  PURE LOGICAL FUNCTION same_real32_bits3(left,right)
    REAL(real32), INTENT(IN) :: left(:,:,:),right(:,:,:)
    same_real32_bits3=ALL(SHAPE(left)==SHAPE(right))
    IF (.NOT.same_real32_bits3) RETURN
    same_real32_bits3=ALL(TRANSFER(left,0_int32,SIZE(left))== &
                          TRANSFER(right,0_int32,SIZE(right)))
  END FUNCTION same_real32_bits3

  PURE LOGICAL FUNCTION same_real32_bits2(left,right)
    REAL(real32), INTENT(IN) :: left(:,:),right(:,:)
    same_real32_bits2=ALL(SHAPE(left)==SHAPE(right))
    IF (.NOT.same_real32_bits2) RETURN
    same_real32_bits2=ALL(TRANSFER(left,0_int32,SIZE(left))== &
                          TRANSFER(right,0_int32,SIZE(right)))
  END FUNCTION same_real32_bits2

  PURE LOGICAL FUNCTION same_real64_bits2(left,right)
    REAL(real64), INTENT(IN) :: left(:,:),right(:,:)
    same_real64_bits2=ALL(SHAPE(left)==SHAPE(right))
    IF (.NOT.same_real64_bits2) RETURN
    same_real64_bits2=ALL(TRANSFER(left,0_int64,SIZE(left))== &
                          TRANSFER(right,0_int64,SIZE(right)))
  END FUNCTION same_real64_bits2

END PROGRAM test_legacy_shadow_adapter
