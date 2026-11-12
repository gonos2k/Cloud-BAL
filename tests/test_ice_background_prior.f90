PROGRAM test_ice_background_prior
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  USE cloud_bal_microphysics_initialization
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: state
  TYPE(ice_snow_partition) :: bg,original,proposal,saved
  TYPE(microphysics_completion_policy) :: policy
  REAL(real32) :: den(1,1,2)
  LOGICAL :: selected(1,1,2)
  INTEGER :: status,where(4)
  CALL initialize_cloud_bal_state(state,1,1,2,42_int64,'synthetic-grid',status)
  CALL check(status==STATUS_OK,'initialize')
  CALL fill(state%cloud_ice,2.e-6_real32)
  CALL fill(state%snow,2.e-6_real32)
  bg%cloud_ice=state%cloud_ice; bg%snow=state%snow; bg%ice_number=state%cloud_ice
  bg%cloud_ice%value=1.e-6_real32; bg%snow%value=3.e-6_real32
  bg%ice_number%unit='kg-1 dryair'; bg%ice_number%value=10000.0_real32
  bg%source='synthetic independent background'; bg%provenance=MOMENT_BACKGROUND
  original=bg
  policy%source='synthetic'; policy%density_source='synthetic'
  policy%mass_threshold=1.e-12_real64; policy%lower=1.e-11_real64; policy%upper=1.e-9_real64
  policy%lower(MOMENT_BG)=100.0_real64; policy%upper(MOMENT_BG)=900.0_real64
  policy%number_cap=1.e10_real64; den=1.0_real32; selected=.TRUE.
  CALL produce()
  CALL check(status==STATUS_OK .AND. ALL(where==0),'mixed background')
  CALL check(ALL(proposal%cloud_ice%value==1.e-6_real32) .AND. &
    ALL(proposal%snow%value==3.e-6_real32) .AND. ALL(proposal%ice_number%value==10000.0_real32), &
    'fraction and mean mass')
  CALL check(ALL(bg%cloud_ice%value==original%cloud_ice%value),'input unchanged')
  saved=proposal
  state%cloud_ice%value=4.e-6_real32; state%snow%value=4.e-6_real32
  CALL produce()
  CALL check(status==STATUS_OK .AND. ALL(proposal%cloud_ice%value==2.e-6_real32) .AND. &
    ALL(proposal%ice_number%value==20000.0_real32),'scaled target')
  bg=original; bg%snow%value=1.e-23_real32
  CALL produce()
  CALL check(status==STATUS_OK .AND. ALL(proposal%snow%value>0.0_real32) .AND. &
    ALL(proposal%snow%value<1.e-22_real32),'small positive snow fraction')
  bg=original; bg%cloud_ice%value=0.0_real32; bg%ice_number%value=0.0_real32
  CALL produce()
  CALL check(status==STATUS_OK .AND. ALL(proposal%cloud_ice%value==0.0_real32) .AND. &
    ALL(proposal%snow%value==8.e-6_real32) .AND. ALL(proposal%ice_number%value==0.0_real32),'all snow')
  bg=original; bg%snow%value=0.0_real32
  CALL produce()
  CALL check(status==STATUS_OK .AND. ALL(proposal%snow%value==0.0_real32),'all ice')
  state%cloud_ice%value=0.0_real32; state%snow%value=0.0_real32
  bg=original
  CALL produce()
  CALL check(status==STATUS_OK .AND. ALL(proposal%cloud_ice%value==0.0_real32) .AND. &
    ALL(proposal%ice_number%value==0.0_real32),'zero target with positive background')
  bg=original; bg%cloud_ice%value=0.0_real32; bg%snow%value=0.0_real32; bg%ice_number%value=0.0_real32
  CALL produce()
  CALL check(status==STATUS_OK .AND. ALL(proposal%ice_number%value==0.0_real32),'zero target and background')
  bg=original; bg%ice_number%value(1,1,2)=0.0_real32
  CALL reject('zero NI with ice even at zero target')
  bg=original; bg%ice_number%value(1,1,2)=1.e9_real32
  CALL reject('invalid background mean at zero target')
  bg=original; bg%cloud_ice%value(1,1,2)=0.0_real32
  CALL reject('positive NI with zero ice')
  state%cloud_ice%value=2.e-6_real32; state%snow%value=2.e-6_real32
  bg=original; bg%cloud_ice%value(1,1,2)=0.0_real32; bg%snow%value(1,1,2)=0.0_real32
  bg%ice_number%value(1,1,2)=0.0_real32
  CALL reject('unsupported new frozen mass')
  bg=original; bg%ice_number%value(1,1,2)=ieee_value(0.0_real32,ieee_quiet_nan)
  CALL reject('nonfinite NI')
  bg=original; bg%ice_number%valid(1,1,2)=.FALSE.
  CALL reject('missing NI')
  bg=original; bg%ice_number%value(1,1,2)=1.e9_real32
  CALL reject('infeasible NI')
  bg=original; bg%cloud_ice%value(1,1,2)=TINY(0.0_real32); bg%snow%value(1,1,2)=1.0_real32
  bg%ice_number%value(1,1,2)=TINY(0.0_real32)/1.e-10_real32
  CALL reject('unrepresentable positive ice')
  bg=original; policy%number_cap(MOMENT_NI)=1.0_real64
  CALL reject('number cap')
  policy%number_cap=1.e10_real64
  bg=original; bg%ice_number%valid_time=43_int64
  CALL reject('time mismatch',.FALSE.)
  bg=original; bg%source=''
  CALL reject('missing authority',.FALSE.)
  bg=original; bg%provenance=MOMENT_PRIOR
  CALL reject('background provenance required',.FALSE.)
  bg=original; bg%snow%unit='kg m-3'
  CALL reject('dry air units required',.FALSE.)
  bg=original; selected(1,1,2)=.FALSE.; bg%ice_number%valid(1,1,2)=.FALSE.
  CALL produce()
  CALL check(status==STATUS_OK .AND. .NOT.proposal%ice_number%valid(1,1,2) .AND. &
    proposal%ice_number%valid(1,1,1),'selection mask')
  saved=proposal
  CALL propose_ice_snow_from_background(state,bg,'wrong-grid',selected,proposal,policy,den,status,where)
  CALL check(status==STATUS_FAILED .AND. ALL(proposal%ice_number%value==saved%ice_number%value),'grid mismatch')
  PRINT *, 'synthetic ice background prior: PASS'
CONTAINS
  SUBROUTINE fill(field,value)
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: value
    field%value=value; field%valid=.TRUE.; field%quality=0; field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE
  SUBROUTINE check(condition,label)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(*), INTENT(IN) :: label
    IF (.NOT.condition) THEN
      PRINT *, 'FAIL: ',label
      ERROR STOP 1
    END IF
  END SUBROUTINE
  SUBROUTINE produce()
    CALL propose_ice_snow_from_background(state,bg,'synthetic-grid',selected,proposal,policy,den,status,where)
  END SUBROUTINE
  SUBROUTINE reject(label,cell_failure)
    CHARACTER(*), INTENT(IN) :: label
    LOGICAL, INTENT(IN), OPTIONAL :: cell_failure
    LOGICAL :: check_cell
    check_cell=.TRUE.
    IF (PRESENT(cell_failure)) check_cell=cell_failure
    proposal=saved
    CALL produce()
    CALL check(status==STATUS_FAILED,label)
    CALL check(ALL(proposal%cloud_ice%value==saved%cloud_ice%value) .AND. &
      ALL(proposal%snow%value==saved%snow%value) .AND. &
      ALL(proposal%ice_number%value==saved%ice_number%value),'atomic rollback')
    IF (check_cell) CALL check(where(4)==MOMENT_NI,'failure location')
  END SUBROUTINE
END PROGRAM
