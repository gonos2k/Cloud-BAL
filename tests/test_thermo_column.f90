PROGRAM test_thermo_column
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan,ieee_positive_inf
  USE cloud_bal_state, ONLY: STATUS_OK,STATUS_FAILED
  USE cloud_bal_column_physics, ONLY: cloud_thermo_budget,saturation_adjust_column, &
                                      SATURATION_LIQUID,SATURATION_ICE
  IMPLICIT NONE
  INTEGER :: failures

  failures=0
  CALL test_constructed_column(failures)
  CALL test_masking_and_noops(failures)
  CALL test_rejections_and_rollback(failures)
  IF (failures/=0) THEN
    PRINT *,'Thermodynamic column tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Thermodynamic column tests passed'

CONTAINS

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE check_near(actual,expected,atol,rtol,message,failures)
    REAL(real64), INTENT(IN) :: actual,expected,atol,rtol
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    CALL check(ABS(actual-expected)<=atol+rtol*MAX(ABS(actual),ABS(expected)), &
               message,failures)
  END SUBROUTINE check_near

  PURE ELEMENTAL REAL(real64) FUNCTION mixture_cp(vapor,liquid,ice)
    REAL(real64), INTENT(IN) :: vapor,liquid,ice
    mixture_cp=1004.5_real64+1846.4_real64*vapor+4190.0_real64*liquid+ &
      2106.0_real64*ice
  END FUNCTION mixture_cp

  PURE REAL(real64) FUNCTION mixture_enthalpy(temperature,vapor,liquid,ice)
    REAL(real64), INTENT(IN) :: temperature,vapor,liquid,ice
    mixture_enthalpy=mixture_cp(vapor,liquid,ice)*(temperature-273.15_real64)+ &
      2.5e6_real64*vapor-3.5e5_real64*ice
  END FUNCTION mixture_enthalpy

  PURE REAL(real64) FUNCTION temperature_for_final_state(final_temperature, &
      final_vapor,final_liquid,final_ice,initial_vapor,initial_liquid,initial_ice)
    REAL(real64), INTENT(IN) :: final_temperature,final_vapor,final_liquid,final_ice
    REAL(real64), INTENT(IN) :: initial_vapor,initial_liquid,initial_ice
    REAL(real64) :: target_enthalpy,initial_species_enthalpy
    target_enthalpy=mixture_enthalpy(final_temperature,final_vapor,final_liquid,final_ice)
    initial_species_enthalpy=mixture_enthalpy(273.15_real64,initial_vapor, &
      initial_liquid,initial_ice)
    temperature_for_final_state=273.15_real64+(target_enthalpy-initial_species_enthalpy)/ &
      mixture_cp(initial_vapor,initial_liquid,initial_ice)
  END FUNCTION temperature_for_final_state

  PURE ELEMENTAL REAL(real64) FUNCTION phase_enthalpy_change(initial_temperature,dv,dl,di)
    REAL(real64), INTENT(IN) :: initial_temperature,dv,dl,di
    REAL(real64) :: tc
    tc=initial_temperature-273.15_real64
    phase_enthalpy_change=dv*(2.5e6_real64+1846.4_real64*tc)+ &
      dl*(4190.0_real64*tc)+di*(-3.5e5_real64+2106.0_real64*tc)
  END FUNCTION phase_enthalpy_change

  SUBROUTINE check_zero_budget(budget,message,failures)
    TYPE(cloud_thermo_budget), INTENT(IN) :: budget
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    CALL check(budget%vapor_change_kg==0.0_real64 .AND. &
      budget%liquid_change_kg==0.0_real64 .AND. budget%ice_change_kg==0.0_real64 .AND. &
      budget%sensible_heat_change_j==0.0_real64 .AND. &
      budget%latent_heat_change_j==0.0_real64 .AND. budget%water_error_kg==0.0_real64 .AND. &
      budget%enthalpy_error_j==0.0_real64,message,failures)
  END SUBROUTINE check_zero_budget

  PURE LOGICAL FUNCTION same_bits(a,b)
    REAL(real64), INTENT(IN) :: a(:),b(:)
    IF (SIZE(a)/=SIZE(b)) THEN
      same_bits=.FALSE.
    ELSE
      same_bits=ALL(TRANSFER(a,0_int64,SIZE(a))==TRANSFER(b,0_int64,SIZE(b)))
    END IF
  END FUNCTION same_bits

  PURE REAL(real64) FUNCTION liquid_qsat(temperature,pressure)
    REAL(real64), INTENT(IN) :: temperature,pressure
    REAL(real64) :: es,tc
    tc=temperature-273.15_real64
    es=611.20_real64*EXP(17.67_real64*tc/(tc+243.5_real64))
    es=MIN(0.99_real64*pressure,MAX(0.0_real64,es))
    liquid_qsat=0.622_real64*es/(pressure-es)
  END FUNCTION liquid_qsat

  PURE REAL(real64) FUNCTION ice_qsat(temperature,pressure)
    REAL(real64), INTENT(IN) :: temperature,pressure
    REAL(real64) :: es,tc
    tc=temperature-273.15_real64
    es=611.15_real64*EXP(22.452_real64*tc/(temperature-0.55_real64))
    es=MIN(0.99_real64*pressure,MAX(0.0_real64,es))
    ice_qsat=0.622_real64*es/(pressure-es)
  END FUNCTION ice_qsat

  SUBROUTINE make_liquid_case(pressure,dry_mass,temperature,vapor,liquid,ice)
    REAL(real64), INTENT(OUT) :: pressure,dry_mass,temperature,vapor,liquid,ice
    REAL(real64) :: qstar,transfer
    pressure=85000.0_real64; dry_mass=2.0_real64
    qstar=liquid_qsat(310.0_real64,pressure); transfer=0.002_real64
    temperature=temperature_for_final_state(310.0_real64,qstar,transfer,0.0_real64, &
      qstar+transfer,0.0_real64,0.0_real64)
    vapor=qstar+transfer; liquid=0.0_real64; ice=0.0_real64
  END SUBROUTINE make_liquid_case

  SUBROUTINE test_constructed_column(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: p(3),m(3),t(3),v(3),ql(3),qi(3)
    REAL(real64) :: t0(3),v0(3),ql0(3),qi0(3),tstar(3),vstar(3),qlstar(3),qistar(3)
    REAL(real64) :: qstar,transfer,ev,el,ei,esensible,elatent
    LOGICAL :: active(3)
    INTEGER :: surface(3)
    TYPE(cloud_thermo_budget) :: budget
    INTEGER :: status

    p=85000.0_real64; m=(/2.0_real64,3.0_real64,0.5_real64/); active=.TRUE.
    surface=(/SATURATION_LIQUID,SATURATION_LIQUID,SATURATION_ICE/)
    tstar=(/310.0_real64,290.0_real64,250.0_real64/)
    qstar=liquid_qsat(tstar(1),p(1)); transfer=0.002_real64
    t(1)=temperature_for_final_state(tstar(1),qstar,transfer,0.0_real64, &
      qstar+transfer,0.0_real64,0.0_real64)
    v(1)=qstar+transfer; ql(1)=0.0_real64; qi(1)=0.0_real64
    qstar=liquid_qsat(tstar(2),p(2)); transfer=0.002_real64
    t(2)=temperature_for_final_state(tstar(2),qstar,0.05_real64-transfer,0.0_real64, &
      qstar-transfer,0.05_real64,0.0_real64)
    v(2)=qstar-transfer; ql(2)=0.05_real64; qi(2)=0.0_real64
    qstar=ice_qsat(tstar(3),p(3)); transfer=0.5_real64*qstar
    t(3)=temperature_for_final_state(tstar(3),qstar,0.0_real64,0.01_real64-transfer, &
      qstar-transfer,0.0_real64,0.01_real64)
    v(3)=qstar-transfer; ql(3)=0.0_real64; qi(3)=0.01_real64
    t0=t; v0=v; ql0=ql; qi0=qi
    vstar=(/liquid_qsat(310.0_real64,p(1)),liquid_qsat(290.0_real64,p(2)), &
            ice_qsat(250.0_real64,p(3))/)
    qlstar=(/0.002_real64,0.05_real64-0.002_real64,0.0_real64/)
    qistar=(/0.0_real64,0.0_real64,0.01_real64-0.5_real64*vstar(3)/)

    CALL saturation_adjust_column(p,m,active,1.0_real64,t,v,ql,qi,budget,status,surface)
    CALL check(status==STATUS_OK,'constructed liquid/ice column accepted',failures)
    CALL check_near(t(1),tstar(1),1.0e-8_real64,1.0e-12_real64,'liquid condensation temperature',failures)
    CALL check_near(t(2),tstar(2),1.0e-8_real64,1.0e-12_real64,'liquid evaporation temperature',failures)
    CALL check_near(t(3),tstar(3),1.0e-8_real64,1.0e-12_real64,'ice sublimation temperature',failures)
    CALL check(ALL(ABS(v-vstar)<1.0e-11_real64),'independent saturation vapor oracle',failures)
    CALL check(ALL(ABS(ql-qlstar)<1.0e-11_real64),'independent liquid oracle',failures)
    CALL check(ALL(ABS(qi-qistar)<1.0e-11_real64),'independent ice oracle',failures)

    ev=SUM(m*(vstar-v0)); el=SUM(m*(qlstar-ql0)); ei=SUM(m*(qistar-qi0))
    esensible=SUM(m*mixture_cp(vstar,qlstar,qistar)*(tstar-t0))
    elatent=SUM(m*phase_enthalpy_change(t0,vstar-v0,qlstar-ql0,qistar-qi0))
    CALL check_near(budget%vapor_change_kg,ev,1.0e-10_real64,1.0e-12_real64,'vapor budget',failures)
    CALL check_near(budget%liquid_change_kg,el,1.0e-10_real64,1.0e-12_real64,'liquid budget',failures)
    CALL check_near(budget%ice_change_kg,ei,1.0e-10_real64,1.0e-12_real64,'ice budget',failures)
    CALL check_near(budget%sensible_heat_change_j,esensible,1.0e-5_real64,1.0e-12_real64,'sensible budget',failures)
    CALL check_near(budget%latent_heat_change_j,elatent,1.0e-5_real64,1.0e-12_real64,'latent budget',failures)
    CALL check_near(budget%water_error_kg,ev+el+ei,1.0e-10_real64,1.0e-12_real64,'water residual',failures)
    CALL check_near(budget%enthalpy_error_j,esensible+elatent,1.0e-5_real64,1.0e-12_real64,'enthalpy residual',failures)
  END SUBROUTINE test_constructed_column

  SUBROUTINE test_masking_and_noops(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: p(3),m(3),t(3),v(3),ql(3),qi(3),tb(3),vb(3),qlb(3),qib(3)
    REAL(real64) :: pe(0),me(0),te(0),ve(0),qle(0),qie(0)
    LOGICAL :: active(3),ae(0)
    INTEGER :: surface(3),se(0)
    TYPE(cloud_thermo_budget) :: budget
    INTEGER :: status

    p=(/85000.0_real64,ieee_value(0.0_real64,ieee_quiet_nan),85000.0_real64/)
    m=(/2.0_real64,ieee_value(0.0_real64,ieee_positive_inf),0.5_real64/)
    active=(/.TRUE.,.FALSE.,.TRUE./)
    surface=(/SATURATION_LIQUID,99,SATURATION_ICE/)
    CALL make_liquid_case(p(1),m(1),t(1),v(1),ql(1),qi(1))
    v(3)=0.5_real64*ice_qsat(250.0_real64,p(3)); ql(3)=0.0_real64; qi(3)=0.01_real64
    t(3)=temperature_for_final_state(250.0_real64,ice_qsat(250.0_real64,p(3)), &
      0.0_real64,0.01_real64-0.5_real64*ice_qsat(250.0_real64,p(3)), &
      v(3),0.0_real64,qi(3))
    t(2)=ieee_value(0.0_real64,ieee_quiet_nan); v(2)=ieee_value(0.0_real64,ieee_quiet_nan)
    ql(2)=ieee_value(0.0_real64,ieee_positive_inf); qi(2)=ieee_value(0.0_real64,ieee_quiet_nan)
    tb=t; vb=v; qlb=ql; qib=qi
    CALL saturation_adjust_column(p,m,active,1.0_real64,t,v,ql,qi,budget,status,surface)
    CALL check(status==STATUS_OK,'inactive NaNs and infinity are ignored',failures)
    CALL check(same_bits(t(2:2),tb(2:2)) .AND. same_bits(v(2:2),vb(2:2)) .AND. &
      same_bits(ql(2:2),qlb(2:2)) .AND. same_bits(qi(2:2),qib(2:2)), &
      'inactive floating values are bit-preserved',failures)

    t=ieee_value(0.0_real64,ieee_quiet_nan); v=t; ql=t; qi=t; tb=t; vb=v; qlb=ql; qib=qi
    p=ieee_value(0.0_real64,ieee_quiet_nan); m=ieee_value(0.0_real64,ieee_positive_inf); active=.FALSE.
    CALL saturation_adjust_column(p,m,active,0.9_real64,t,v,ql,qi,budget,status,surface)
    CALL check(status==STATUS_OK,'all-inactive column is a no-op',failures)
    CALL check(same_bits(t,tb) .AND. same_bits(v,vb) .AND. same_bits(ql,qlb) .AND. same_bits(qi,qib), &
      'all-inactive values are bit-preserved',failures)
    CALL check_zero_budget(budget,'all-inactive budget is zero',failures)

    CALL saturation_adjust_column(pe,me,ae,0.8_real64,te,ve,qle,qie,budget,status,se)
    CALL check(status==STATUS_OK,'empty column is a no-op',failures)
    CALL check_zero_budget(budget,'empty budget is zero',failures)
  END SUBROUTINE test_masking_and_noops

  SUBROUTINE test_rejections_and_rollback(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: p(2),m(2),t(2),v(2),ql(2),qi(2),tb(2),vb(2),qlb(2),qib(2)
    REAL(real64) :: ps(1),ms(1),ts(1),vs(1),qls(1),qis(1),tsb(1),vsb(1),qlsb(1),qisb(1)
    REAL(real64) :: p3(3),m3(3),t2(2),v3(3),ql3(3),qi3(3),t2b(2),v3b(3),ql3b(3),qi3b(3)
    REAL(real64) :: bad_mass(4),bad_target(3)
    LOGICAL :: active(2),as(1),a3(3)
    INTEGER :: surface(2),ss(1),surface3(3)
    TYPE(cloud_thermo_budget) :: budget
    INTEGER :: status,k

    p=85000.0_real64; m=2.0_real64; active=.TRUE.
    surface=SATURATION_LIQUID; ss=SATURATION_LIQUID; surface3=SATURATION_LIQUID
    CALL make_liquid_case(p(1),m(1),t(1),v(1),ql(1),qi(1))
    t(2)=349.0_real64; v(2)=1.0_real64; ql(2)=0.001_real64; qi(2)=0.0_real64
    tb=t; vb=v; qlb=ql; qib=qi
    CALL saturation_adjust_column(p,m,active,1.0_real64,t,v,ql,qi,budget,status,surface)
    CALL check(status==STATUS_FAILED .AND. same_bits(t,tb) .AND. same_bits(v,vb) .AND. &
      same_bits(ql,qlb) .AND. same_bits(qi,qib),'later failure rolls back earlier cell',failures)
    CALL check_zero_budget(budget,'rollback budget is zero',failures)

    bad_mass=(/0.0_real64,-1.0_real64,ieee_value(0.0_real64,ieee_quiet_nan), &
               ieee_value(0.0_real64,ieee_positive_inf)/)
    DO k=1,4
      CALL make_liquid_case(ps(1),ms(1),ts(1),vs(1),qls(1),qis(1)); ms(1)=bad_mass(k); as=.TRUE.
      tsb=ts; vsb=vs; qlsb=qls; qisb=qis
      CALL saturation_adjust_column(ps,ms,as,1.0_real64,ts,vs,qls,qis,budget,status,ss)
      CALL check(status==STATUS_FAILED .AND. same_bits(ts,tsb) .AND. same_bits(vs,vsb) .AND. &
        same_bits(qls,qlsb) .AND. same_bits(qis,qisb),'invalid active mass is atomic',failures)
      CALL check_zero_budget(budget,'invalid mass budget is zero',failures)
    END DO

    bad_target=(/-0.1_real64,1.1_real64,ieee_value(0.0_real64,ieee_quiet_nan)/)
    DO k=1,3
      CALL make_liquid_case(ps(1),ms(1),ts(1),vs(1),qls(1),qis(1)); as=.TRUE.
      tsb=ts; vsb=vs; qlsb=qls; qisb=qis
      CALL saturation_adjust_column(ps,ms,as,bad_target(k),ts,vs,qls,qis,budget,status,ss)
      CALL check(status==STATUS_FAILED .AND. same_bits(ts,tsb) .AND. same_bits(vs,vsb), &
        'invalid target relative humidity is atomic',failures)
      CALL check_zero_budget(budget,'invalid target budget is zero',failures)
    END DO

    p3=85000.0_real64; m3=2.0_real64; a3=.TRUE.; v3=0.01_real64; ql3=0.0_real64; qi3=0.0_real64
    t2=280.0_real64; t2b=t2; v3b=v3; ql3b=ql3; qi3b=qi3
    CALL saturation_adjust_column(p3,m3,a3,1.0_real64,t2,v3,ql3,qi3,budget,status,surface3)
    CALL check(status==STATUS_FAILED .AND. same_bits(t2,t2b) .AND. same_bits(v3,v3b) .AND. &
      same_bits(ql3,ql3b) .AND. same_bits(qi3,qi3b),'shape mismatch is atomic',failures)
    CALL check_zero_budget(budget,'shape mismatch budget is zero',failures)

    CALL make_liquid_case(ps(1),ms(1),ts(1),vs(1),qls(1),qis(1)); ms(1)=HUGE(1.0_real64); as=.TRUE.
    tsb=ts; vsb=vs; qlsb=qls; qisb=qis
    CALL saturation_adjust_column(ps,ms,as,1.0_real64,ts,vs,qls,qis,budget,status,ss)
    CALL check(status==STATUS_FAILED .AND. same_bits(ts,tsb) .AND. same_bits(vs,vsb) .AND. &
      same_bits(qls,qlsb) .AND. same_bits(qis,qisb),'unsafe weighted overflow is atomic',failures)
    CALL check_zero_budget(budget,'overflow budget is zero',failures)

    ps(1)=85000.0_real64; ms(1)=2.0_real64; as=.TRUE.; ts(1)=280.0_real64; vs(1)=0.0_real64
    qls(1)=1.0e-8_real64; qis(1)=0.0_real64
    CALL saturation_adjust_column(ps,ms,as,1.0_real64,ts,vs,qls,qis,budget,status,ss)
    CALL check(status==STATUS_OK .AND. ts(1)<280.0_real64 .AND. qls(1)==0.0_real64, &
      'true condensate exhaustion is a valid endpoint',failures)
  END SUBROUTINE test_rejections_and_rollback

END PROGRAM test_thermo_column
