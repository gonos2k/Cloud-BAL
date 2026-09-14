PROGRAM test_source_host_pressure_request
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite,ieee_value,ieee_quiet_nan
  USE cloud_bal_state, ONLY: STATUS_OK
  USE cloud_bal_wps_adapter, ONLY: pressure_wps_fields,build_source_host_pressure_request, &
    evaluate_source_host_pressure_residual,host_vapor_pressure_column
  IMPLICIT NONE
  INTEGER, PARAMETER :: NX=2,NY=1,NZ=3
  INTEGER(int64), PARAMETER :: VALID_TIME=1788233520_int64
  REAL(real64), PARAMETER :: RD=287.0_real64,G=9.81_real64,CAP=100.0_real64
  REAL(real64), PARAMETER :: EOS_RD=287.05_real64,EOS_G=9.80665_real64
  TYPE(pressure_wps_fields) :: background,candidate,bad,crossing_background,crossing_candidate
  LOGICAL :: selected(NX,NY)
  REAL(real64) :: request(NX,NY),before(NX,NY),bad_request(1,1)
  INTEGER :: status,failed(2),failures

  failures=0; CALL make_fixture(background); candidate=background
  selected=.FALSE.; selected(1,1)=.TRUE.
  request=0.0_real64; request(1,1)=REAL(background%psfc(1,1),real64); request(2,1)=12345.0_real64
  CALL build_source_host_pressure_request(background,background,selected,RD,G,CAP,request,status,failed)
  CALL check(status==STATUS_OK,'same-input request succeeds',failures)
  CALL check(request(1,1)==REAL(background%psfc(1,1),real64) .AND. &
    request(2,1)==REAL(background%psfc(2,1),real64),'no-op and default request are exact',failures)
  CALL check(ALL(failed==0),'successful request reports no failed column',failures)

  candidate%t(1,1,1:4)=candidate%t(1,1,1:4)+[2.0_real32,4.0_real32,6.0_real32,3.0_real32]
  candidate%qv(1,1,1:4)=candidate%qv(1,1,1:4)+[0.001_real32,0.002_real32,0.003_real32,0.002_real32]
  candidate%qc(1,1,:)=candidate%qc(1,1,:)+0.00030_real32
  candidate%qi(1,1,:)=candidate%qi(1,1,:)+0.00010_real32
  candidate%ht(1,1,1:3)=candidate%ht(1,1,1:3)+[20.0_real32,12.0_real32,6.0_real32]
  request=0.0_real64; request(1,1)=REAL(background%psfc(1,1),real64); request(2,1)=-77.0_real64
  CALL build_source_host_pressure_request(background,candidate,selected,RD,G,CAP,request,status,failed)
  CALL check(status==STATUS_OK,'changed source column succeeds',failures)
  CALL check(ieee_is_finite(request(1,1)) .AND. ABS(request(1,1)-REAL(background%psfc(1,1),real64))>1.0e-8_real64, &
    'nonzero thermodynamic change produces a request',failures)
  CALL check(request(2,1)==REAL(background%psfc(2,1),real64),'unselected source column keeps default',failures)
  CALL check(failed(1)==0 .AND. failed(2)==0,'changed request reports no failed column',failures)
  CALL check_closure(background,candidate,1,request(1,1),failures)

  before=request; bad=candidate; bad%qv(1,1,2)=ieee_value(0.0_real32,ieee_quiet_nan)
  CALL build_source_host_pressure_request(background,bad,selected,RD,G,CAP,request,status,failed)
  CALL check(status/=STATUS_OK,'nonfinite selected input rejects',failures)
  CALL check(ALL(request==before),'nonfinite rejection is atomic',failures)

  request=before; before=request
  CALL build_source_host_pressure_request(background,candidate,selected,RD,G,1.0e-3_real64,request,status,failed)
  CALL check(status/=STATUS_OK .AND. failed(1)==1 .AND. failed(2)==1,'increment cap rejects selected column',failures)
  CALL check(ALL(request==before),'cap rejection is atomic',failures)

  crossing_background=background; crossing_candidate=background
  crossing_background%psfc(1,1)=95050.0_real32; crossing_candidate%psfc(1,1)=95050.0_real32
  crossing_candidate%qv(1,1,:)=0.0_real32
  request=before
  CALL build_source_host_pressure_request(crossing_background,crossing_candidate,selected,RD,G,1000.0_real64,request,status,failed)
  CALL check(status/=STATUS_OK,'pressure-level crossing rejects',failures)
  CALL check(ALL(request==before),'pressure-level crossing rejection is atomic',failures)
  request=before; bad=candidate; bad%p(1)=940.0_real32
  CALL build_source_host_pressure_request(background,bad,selected,RD,G,CAP,request,status,failed)
  CALL check(status/=STATUS_OK,'pressure-level mismatch rejects',failures)
  CALL check(ALL(request==before),'pressure mismatch rejection is atomic',failures)
  request=before; bad=candidate; bad%wind_coordinate='EARTH_RELATIVE'
  CALL build_source_host_pressure_request(background,bad,selected,RD,G,CAP,request,status,failed)
  CALL check(status/=STATUS_OK,'frame mismatch rejects',failures)
  CALL check(ALL(request==before),'frame rejection is atomic',failures)
  request=before; bad=candidate; bad%valid_time=VALID_TIME+1_int64
  CALL build_source_host_pressure_request(background,bad,selected,RD,G,CAP,request,status,failed)
  CALL check(status/=STATUS_OK,'time mismatch rejects',failures)
  CALL check(ALL(request==before),'time rejection is atomic',failures)

  bad_request=123.0_real64
  CALL build_source_host_pressure_request(background,candidate,selected,RD,G,CAP,bad_request,status,failed)
  CALL check(status/=STATUS_OK .AND. bad_request(1,1)==123.0_real64,'request shape rejection is atomic',failures)

  ! A real-data failure occurs just below a pressure center. Use matching
  ! input grids here, so rejection exercises the bounded solve, not metadata.
  bad=background; bad%psfc=94999.125_real32
  candidate=bad; candidate%qv(1,1,:)=candidate%qv(1,1,:)+0.002_real32
  request=-17.0_real64; before=request
  CALL build_source_host_pressure_request(bad,candidate,selected,RD,G,1000.0_real64,request,status,failed)
  CALL check(status/=STATUS_OK .AND. ALL(failed==[1,1]) .AND. ALL(request==before), &
    'same-grid near-center moisture change cannot silently expose a pressure level',failures)

  CALL residual_evaluator_tests(failures)
  IF (failures/=0) ERROR STOP 'source-host pressure request tests failed'
  PRINT '(A)','Source-host pressure request tests passed'

CONTAINS
  SUBROUTINE make_fixture(w)
    TYPE(pressure_wps_fields), INTENT(OUT) :: w
    ALLOCATE(w%p(4),w%t(NX,NY,4),w%ht(NX,NY,4),w%u(NX,NY,4),w%v(NX,NY,4),w%rh(NX,NY,4),w%qv(NX,NY,4), &
      w%qc(NX,NY,3),w%qi(NX,NY,3),w%qr(NX,NY,3),w%qs(NX,NY,3),w%qg(NX,NY,3),w%psfc(NX,NY),w%slp(NX,NY), &
      w%skin_temperature(NX,NY),w%snow_cover(NX,NY))
    w%p=[650.0_real32,800.0_real32,950.0_real32,2001.0_real32]
    w%t=0.0_real32; w%t(1,1,:)=[250.0,260.0,270.0,280.0]; w%t(2,1,:)=w%t(1,1,:)+1.0
    w%ht=0.0_real32; w%ht(1,1,:)=[2500.0,1600.0,700.0,100.0]; w%ht(2,1,:)=w%ht(1,1,:)
    w%qv=0.0_real32; w%qv(1,1,:)=[0.002,0.004,0.006,0.008]; w%qv(2,1,:)=w%qv(1,1,:)
    w%u=1.0; w%v=-2.0; w%rh=55.0; w%qc=0.0002; w%qi=0.0001; w%qr=0.0001; w%qs=0.0001; w%qg=0.0001
    w%psfc=100000.0; w%slp=101000.0; w%skin_temperature=280.0; w%snow_cover=0.0
    w%valid_time=VALID_TIME; w%grid_id='source-host-fixture'; w%wind_coordinate='GRID_RELATIVE'
  END SUBROUTINE make_fixture

  SUBROUTINE check_closure(bg,ca,column,ps,failures)
    TYPE(pressure_wps_fields), INTENT(IN) :: bg,ca
    INTEGER, INTENT(IN) :: column
    REAL(real64), INTENT(IN) :: ps
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pb(4),pc(4),tb(4),tc(4),qb(4),qc(4),zb(4),zc(4),trial(4)
    REAL(real64) :: target,integral,alpha_s,alpha_l,response,eps
    eps=0.622_real64
    pb=[REAL(bg%psfc(column,1),real64),REAL(bg%p(3),real64)*100.0_real64, &
      REAL(bg%p(2),real64)*100.0_real64,REAL(bg%p(1),real64)*100.0_real64]
    pc=[REAL(ca%psfc(column,1),real64),REAL(ca%p(3),real64)*100.0_real64, &
      REAL(ca%p(2),real64)*100.0_real64,REAL(ca%p(1),real64)*100.0_real64]
    tb=[bg%t(column,1,4),bg%t(column,1,3),bg%t(column,1,2),bg%t(column,1,1)]
    tc=[ca%t(column,1,4),ca%t(column,1,3),ca%t(column,1,2),ca%t(column,1,1)]
    qb=[bg%qv(column,1,4),bg%qv(column,1,3),bg%qv(column,1,2),bg%qv(column,1,1)]
    qc=[ca%qv(column,1,4),ca%qv(column,1,3),ca%qv(column,1,2),ca%qv(column,1,1)]
    zb=[bg%ht(column,1,4),bg%ht(column,1,3),bg%ht(column,1,2),bg%ht(column,1,1)]
    zc=[ca%ht(column,1,4),ca%ht(column,1,3),ca%ht(column,1,2),ca%ht(column,1,1)]
    target=pb(1)-vapor_integral(pb,tb,qb,zb)
    alpha_s=EOS_RD*tc(1)*(1.0_real64+qc(1)/eps)/(1.0_real64+qc(1))
    alpha_l=EOS_RD*tc(2)*(1.0_real64+qc(2)/eps)/(1.0_real64+qc(2)+ca%qc(column,1,3)+ca%qi(column,1,3)+ &
      ca%qr(column,1,3)+ca%qs(column,1,3)+ca%qg(column,1,3))
    response=0.5_real64*(alpha_s+alpha_l)/EOS_G; pc(1)=ps
    trial=zc+response*LOG(ps/REAL(ca%psfc(column,1),real64)); trial(1)=zc(1)
    integral=vapor_integral(pc,tc,qc,trial)
    CALL check(ABS(ps-integral-target)<=1.0e-7_real64,'independent full-mixture target closure',failures)
  END SUBROUTINE check_closure

  SUBROUTINE residual_evaluator_tests(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(pressure_wps_fields) :: background,candidate,bad,reversed_background,reversed_candidate
    LOGICAL :: selected(NX,NY),none_selected(NX,NY),bad_selected(1,1)
    REAL(real64) :: residual(NX,NY),before(NX,NY),expected
    REAL(real64) :: bad_residual(1,1)
    INTEGER :: status

    CALL make_fixture(background)
    background%p(3)=1000.0_real32
    background%psfc(1,1)=99999.125_real32
    candidate=background
    candidate%t(1,1,1:4)=candidate%t(1,1,1:4)+[2.0_real32,4.0_real32,6.0_real32,3.0_real32]
    candidate%qv(1,1,1:4)=candidate%qv(1,1,1:4)+[0.001_real32,0.002_real32,0.003_real32,0.002_real32]
    candidate%qc(1,1,:)=candidate%qc(1,1,:)+0.00030_real32
    candidate%qi(1,1,:)=candidate%qi(1,1,:)+0.00010_real32
    candidate%ht(1,1,1:3)=candidate%ht(1,1,1:3)+[20.0_real32,12.0_real32,6.0_real32]
    candidate%psfc(1,1)=100010.0_real32
    selected=.FALSE.; selected(1,1)=.TRUE.; none_selected=.FALSE.

    residual=123.0_real64
    CALL evaluate_source_host_pressure_residual(background,background,selected,RD,G,residual,status)
    CALL check(status==STATUS_OK .AND. ALL(residual==0.0_real64), &
      'equal WPS states produce zero selected and unselected residuals',failures)

    CALL expected_residual(background,candidate,1,1,RD,G,expected)
    residual=123.0_real64
    CALL evaluate_source_host_pressure_residual(background,candidate,selected,RD,G,residual,status)
    CALL check(status==STATUS_OK .AND. ABS(residual(1,1)-expected)< &
      1.0e-7_real64*MAX(1.0_real64,ABS(expected)) .AND. residual(2,1)==0.0_real64, &
      'changed PS/Q/HGT residual matches direct column reference and mask',failures)

    residual=123.0_real64
    CALL evaluate_source_host_pressure_residual(background,candidate,none_selected,RD,G,residual,status)
    CALL check(status==STATUS_OK .AND. ALL(residual==0.0_real64), &
      'all-false selection is a zero residual no-op',failures)

    CALL reverse_inventory(background,reversed_background)
    CALL reverse_inventory(candidate,reversed_candidate)
    residual=123.0_real64
    CALL evaluate_source_host_pressure_residual(reversed_background,reversed_candidate, &
      selected,RD,G,residual,status)
    CALL check(status==STATUS_OK .AND. ABS(residual(1,1)-expected)< &
      1.0e-7_real64*MAX(1.0_real64,ABS(expected)) .AND. residual(2,1)==0.0_real64, &
      'changed residual matches direct reference under the opposite WPS pressure ordering',failures)

    before=123.0_real64; bad=candidate; bad%p(1)=bad%p(1)-1.0_real32
    CALL evaluate_source_host_pressure_residual(background,bad,selected,RD,G,before,status)
    CALL check(status/=STATUS_OK .AND. ALL(before==123.0_real64), &
      'pressure mismatch rejects atomically',failures)
    before=123.0_real64; bad=candidate; bad%valid_time=VALID_TIME+1_int64
    CALL evaluate_source_host_pressure_residual(background,bad,selected,RD,G,before,status)
    CALL check(status/=STATUS_OK .AND. ALL(before==123.0_real64), &
      'time mismatch rejects atomically',failures)
    before=123.0_real64; bad=candidate; bad%wind_coordinate='EARTH_RELATIVE'
    CALL evaluate_source_host_pressure_residual(background,bad,selected,RD,G,before,status)
    CALL check(status/=STATUS_OK .AND. ALL(before==123.0_real64), &
      'frame mismatch rejects atomically',failures)
    before=123.0_real64; bad=candidate; bad%ht(1,1,NZ+1)=bad%ht(1,1,NZ+1)+1.0_real32
    CALL evaluate_source_host_pressure_residual(background,bad,selected,RD,G,before,status)
    CALL check(status/=STATUS_OK .AND. ALL(before==123.0_real64), &
      'terrain mismatch rejects atomically',failures)

    bad_selected=.TRUE.; bad_residual=456.0_real64
    CALL evaluate_source_host_pressure_residual(background,candidate,bad_selected,RD,G,bad_residual,status)
    CALL check(status/=STATUS_OK .AND. bad_residual(1,1)==456.0_real64, &
      'selection shape mismatch rejects atomically',failures)
  END SUBROUTINE residual_evaluator_tests

  SUBROUTINE expected_residual(background,candidate,i,j,gas_constant,gravity,value)
    TYPE(pressure_wps_fields), INTENT(IN) :: background,candidate
    INTEGER, INTENT(IN) :: i,j
    REAL(real64), INTENT(IN) :: gas_constant,gravity
    REAL(real64), INTENT(OUT) :: value
    REAL(real64) :: pb(4),pc(4),tb(4),tc(4),qb(4),qc(4),zb(4),zc(4)
    REAL(real64) :: background_integral,candidate_integral
    LOGICAL :: ok
    CALL host_column(background,i,j,pb,tb,qb,zb)
    CALL host_column(candidate,i,j,pc,tc,qc,zc)
    CALL host_vapor_pressure_column(pb,tb,qb,zb,gas_constant,gravity,background_integral,ok)
    IF (.NOT.ok) THEN; value=HUGE(value); RETURN; END IF
    CALL host_vapor_pressure_column(pc,tc,qc,zc,gas_constant,gravity,candidate_integral,ok)
    IF (.NOT.ok) THEN; value=HUGE(value); RETURN; END IF
    value=(REAL(candidate%psfc(i,j),real64)-candidate_integral)- &
      (REAL(background%psfc(i,j),real64)-background_integral)
  END SUBROUTINE expected_residual

  SUBROUTINE host_column(fields,i,j,p,t,q,z)
    TYPE(pressure_wps_fields), INTENT(IN) :: fields
    INTEGER, INTENT(IN) :: i,j
    REAL(real64), INTENT(OUT) :: p(4),t(4),q(4),z(4)
    INTEGER :: k
    p(1)=REAL(fields%psfc(i,j),real64); t(1)=fields%t(i,j,4)
    q(1)=fields%qv(i,j,4); z(1)=fields%ht(i,j,4)
    DO k=1,3
      p(k+1)=100.0_real64*REAL(fields%p(k),real64)
      t(k+1)=fields%t(i,j,k); q(k+1)=fields%qv(i,j,k); z(k+1)=fields%ht(i,j,k)
    END DO
  END SUBROUTINE host_column

  SUBROUTINE reverse_inventory(input,output)
    TYPE(pressure_wps_fields), INTENT(IN) :: input
    TYPE(pressure_wps_fields), INTENT(OUT) :: output
    output=input
    output%p(1:NZ)=input%p(NZ:1:-1)
    output%t(:,:,1:NZ)=input%t(:,:,NZ:1:-1); output%ht(:,:,1:NZ)=input%ht(:,:,NZ:1:-1)
    output%u(:,:,1:NZ)=input%u(:,:,NZ:1:-1); output%v(:,:,1:NZ)=input%v(:,:,NZ:1:-1)
    output%rh(:,:,1:NZ)=input%rh(:,:,NZ:1:-1); output%qv(:,:,1:NZ)=input%qv(:,:,NZ:1:-1)
    output%qc=input%qc(:,:,NZ:1:-1); output%qi=input%qi(:,:,NZ:1:-1)
    output%qr=input%qr(:,:,NZ:1:-1); output%qs=input%qs(:,:,NZ:1:-1); output%qg=input%qg(:,:,NZ:1:-1)
  END SUBROUTINE reverse_inventory

  PURE FUNCTION vapor_integral(p,t,q,z) RESULT(total)
    REAL(real64), INTENT(IN) :: p(:),t(:),q(:),z(:)
    REAL(real64) :: total,qbar,rhobar
    INTEGER :: k
    total=0.0_real64
    DO k=1,SIZE(p)-1
      qbar=0.5_real64*(q(k)+q(k+1)); rhobar=0.5_real64*(p(k)/(RD*t(k))+p(k+1)/(RD*t(k+1)))
      total=total+G*qbar/(1.0_real64+qbar)*rhobar*(z(k+1)-z(k))
    END DO
  END FUNCTION vapor_integral

  SUBROUTINE check(ok,label,n)
    LOGICAL, INTENT(IN) :: ok; CHARACTER(*), INTENT(IN) :: label; INTEGER, INTENT(INOUT) :: n
    IF (.NOT.ok) THEN; n=n+1; PRINT '(A)','FAIL: '//TRIM(label); END IF
  END SUBROUTINE check
END PROGRAM test_source_host_pressure_request
