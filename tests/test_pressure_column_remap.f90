! Independent pressure-column remap oracle.  Species are mixing ratios;
! remapping is performed on dry mass and species mass, not on q alone.
PROGRAM test_pressure_column_remap
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan,ieee_positive_inf
  USE cloud_bal_state, ONLY: STATUS_OK,STATUS_FAILED
  USE cloud_bal_column_physics, ONLY: remap_pressure_column
  IMPLICIT NONE

  INTEGER :: failures
  CHARACTER(LEN=512) :: fixture_path
  REAL(real64), PARAMETER :: T0=273.15_real64,CPD=1004.5_real64
  REAL(real64), PARAMETER :: CP(6)=[1846.4_real64,4190.0_real64,2106.0_real64, &
                                     4190.0_real64,2106.0_real64,2106.0_real64]
  REAL(real64), PARAMETER :: H0(6)=[2.5e6_real64,0.0_real64,-3.5e5_real64, &
                                    0.0_real64,-3.5e5_real64,-3.5e5_real64]

  failures=0
  CALL test_identity(failures)
  CALL test_split_merge_and_enthalpy(failures)
  CALL test_pressure_mass_consistency(failures)
  CALL test_actual_center_partition(failures)
  CALL test_float32_storage_regression(failures)
  CALL test_float32_storage_identity(failures)
  CALL test_rejections_are_atomic(failures)
  CALL GET_COMMAND_ARGUMENT(1,fixture_path)
  IF (LEN_TRIM(fixture_path)>0) CALL emit_transition_fixture(TRIM(fixture_path),failures)
  IF (failures/=0) THEN
    PRINT *, 'Pressure-column remap tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *, 'Pressure-column remap tests passed'

CONTAINS

  SUBROUTINE check(condition,message,n)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: n
    IF (.NOT.condition) THEN
      n=n+1
      PRINT *, 'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE check_near(actual,expected,tol,message,n)
    REAL(real64), INTENT(IN) :: actual,expected,tol
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: n
    CALL check(ABS(actual-expected)<=tol*MAX(1.0_real64,ABS(expected)),message,n)
  END SUBROUTINE check_near

  PURE REAL(real64) FUNCTION mixture_cp(q)
    REAL(real64), INTENT(IN) :: q(:)
    mixture_cp=CPD+DOT_PRODUCT(CP,q)
  END FUNCTION mixture_cp

  PURE REAL(real64) FUNCTION reduced_enthalpy(temperature,q)
    REAL(real64), INTENT(IN) :: temperature,q(:)
    reduced_enthalpy=mixture_cp(q)*(temperature-T0)+DOT_PRODUCT(H0,q)
  END FUNCTION reduced_enthalpy

  ! Piecewise-constant, pressure-overlap oracle.  The production routine is
  ! deliberately not called for any intermediate quantity here.
  SUBROUTINE oracle(old_i,old_m,old_t,old_q,new_i,new_m,new_t,new_q)
    REAL(real64), INTENT(IN) :: old_i(:),old_m(:),old_t(:),old_q(:,:),new_i(:)
    REAL(real64), INTENT(OUT) :: new_m(:),new_t(:),new_q(:,:)
    REAL(real64) :: overlap,fraction,dm,energy
    REAL(real64) :: species_mass(SIZE(new_q,1))
    INTEGER :: j,k

    DO k=1,SIZE(new_m)
      new_m(k)=0.0_real64; species_mass=0.0_real64; energy=0.0_real64
      DO j=1,SIZE(old_m)
        overlap=MIN(new_i(k),old_i(j))-MAX(new_i(k+1),old_i(j+1))
        IF (overlap>0.0_real64) THEN
          fraction=overlap/(old_i(j)-old_i(j+1)); dm=old_m(j)*fraction
          new_m(k)=new_m(k)+dm
          species_mass=species_mass+dm*old_q(:,j)
          energy=energy+dm*reduced_enthalpy(old_t(j),old_q(:,j))
        END IF
      END DO
      new_q(:,k)=species_mass/new_m(k)
      new_t(k)=T0+(energy/new_m(k)-DOT_PRODUCT(H0,new_q(:,k)))/mixture_cp(new_q(:,k))
    END DO
  END SUBROUTINE oracle

  PURE LOGICAL FUNCTION same_bits_1d(a,b)
    REAL(real64), INTENT(IN) :: a(:),b(:)
    IF (SIZE(a)/=SIZE(b)) THEN
      same_bits_1d=.FALSE.
    ELSE
      same_bits_1d=ALL(TRANSFER(a,0_int64,SIZE(a))==TRANSFER(b,0_int64,SIZE(b)))
    END IF
  END FUNCTION same_bits_1d

  PURE LOGICAL FUNCTION same_bits_2d(a,b)
    REAL(real64), INTENT(IN) :: a(:,:),b(:,:)
    IF (SIZE(a)/=SIZE(b)) THEN
      same_bits_2d=.FALSE.
    ELSE
      same_bits_2d=ALL(TRANSFER(a,0_int64,SIZE(a))==TRANSFER(b,0_int64,SIZE(b)))
    END IF
  END FUNCTION same_bits_2d

  SUBROUTINE test_identity(n)
    INTEGER, INTENT(INOUT) :: n
    REAL(real64) :: oi(4),om(3),ot(3),oq(6,3),ni(4),nm(3),nt(3),nq(6,3)
    INTEGER :: status

    oi=[100000.0_real64,93000.0_real64,87000.0_real64,80000.0_real64]
    om=[2.0_real64,3.0_real64,4.0_real64]; ot=[260.0_real64,275.0_real64,290.0_real64]
    oq=0.0_real64; oq(:,1)=[.02,.003,.001,.001,.001,.001]
    oq(:,2)=[.01,.004,.002,.001,.001,.002]; oq(:,3)=[.03,.002,.001,.002,.001,.001]
    ni=oi; nm=-11.0_real64; nt=-12.0_real64; nq=-13.0_real64
    CALL remap_pressure_column(oi,om,ot,oq,ni,nm,nt,nq,status)
    CALL check(status==STATUS_OK,'identity remap accepted',n)
    CALL check(same_bits_1d(ni,oi) .AND. same_bits_1d(nm,om) .AND. same_bits_1d(nt,ot) .AND. &
               same_bits_2d(nq,oq),'identity remap is bitwise exact',n)
  END SUBROUTINE test_identity

  SUBROUTINE test_split_merge_and_enthalpy(n)
    INTEGER, INTENT(INOUT) :: n
    REAL(real64) :: oi(4),om(3),ot(3),oq(6,3),ni(5),nm(4),nt(4),nq(6,4)
    REAL(real64) :: em(4),et(4),eq(6,4),naive,old_energy,new_energy
    INTEGER :: status,k,s

    oi=[100000.0_real64,92000.0_real64,84000.0_real64,78000.0_real64]
    om=[2.0_real64,5.0_real64,3.0_real64]; ot=[255.0_real64,320.0_real64,280.0_real64]
    oq(:,1)=[.020,.003,.001,.001,.001,.001]
    oq(:,2)=[.010,.004,.002,.001,.001,.002]
    oq(:,3)=[.030,.002,.001,.002,.001,.001]
    ni=[100000.0_real64,96000.0_real64,88000.0_real64,82000.0_real64,78000.0_real64]
    CALL oracle(oi,om,ot,oq,ni,em,et,eq)
    nm=-1.0_real64; nt=-2.0_real64; nq=-3.0_real64
    CALL remap_pressure_column(oi,om,ot,oq,ni,nm,nt,nq,status)
    CALL check(status==STATUS_OK,'wet split-and-merge remap accepted',n)
    DO k=1,4
      CALL check_near(nm(k),em(k),1.0e-12_real64,'split/merge dry mass oracle',n)
      CALL check_near(nt(k),et(k),1.0e-12_real64,'split/merge thermal oracle',n)
      DO s=1,6
        CALL check_near(nq(s,k),eq(s,k),1.0e-12_real64,'split/merge species oracle',n)
      END DO
    END DO
    ! Equal pressure overlaps do not imply equal dry masses. Even a dry-mass
    ! weighted temperature misses the distinct mixture heat capacities.
    naive=(om(1)*ot(1)+om(2)*ot(2))/(om(1)+om(2))
    CALL check(ABS(nt(2)-naive)>1.0e-3_real64,'thermal weighting differs from dry-mass T average',n)
    CALL check_near(SUM(nm),SUM(om),1.0e-12_real64,'column dry mass closes',n)
    DO s=1,6
      CALL check_near(SUM(nm*nq(s,:)),SUM(om*oq(s,:)),1.0e-12_real64,'species mass closes',n)
    END DO
    old_energy=0.0_real64; new_energy=0.0_real64
    DO k=1,3
      old_energy=old_energy+om(k)*reduced_enthalpy(ot(k),oq(:,k))
    END DO
    DO k=1,4
      new_energy=new_energy+nm(k)*reduced_enthalpy(nt(k),nq(:,k))
    END DO
    CALL check_near(new_energy,old_energy,1.0e-12_real64,'column reduced enthalpy closes',n)
  END SUBROUTINE test_split_merge_and_enthalpy

  SUBROUTINE test_pressure_mass_consistency(n)
    INTEGER, INTENT(INOUT) :: n
    REAL(real64) :: oi(3),om(2),ot(2),oq(6,2),ni(4),nm(3),nt(3),nq(6,3)
    REAL(real64), PARAMETER :: area=1.7e5_real64,gravity=9.80665_real64
    REAL(real64) :: dp
    INTEGER :: k,status

    oi=[100000.0_real64,95000.0_real64,90000.0_real64]; ot=[270.0_real64,285.0_real64]
    oq(:,1)=[.012,.002,.002,.001,.001,.002]
    oq(:,2)=[.004,.004,.001,.002,.003,.001] ! different total water and heat capacity
    om=area*(oi(:2)-oi(2:))/(gravity*(1.0_real64+SUM(oq,1)))
    ni=[100000.0_real64,97500.0_real64,92500.0_real64,90000.0_real64]
    CALL remap_pressure_column(oi,om,ot,oq,ni,nm,nt,nq,status)
    CALL check(status==STATUS_OK,'pressure-mass remap accepted',n)
    DO k=1,3
      dp=ni(k)-ni(k+1)
      CALL check_near(nm(k)*(1.0_real64+SUM(nq(:,k)))*gravity/dp,area,1.0e-12_real64, &
                      'total pressure mass matches A*dp/g/(1+sumr)',n)
    END DO
  END SUBROUTINE test_pressure_mass_consistency

  SUBROUTINE test_actual_center_partition(n)
    INTEGER, INTENT(INOUT) :: n
    REAL(real64) :: oi(3),om(2),ot(2),oq(6,2),ni(4),nm(3),nt(3),nq(6,3)
    INTEGER :: status

    oi=[99999.125_real64,92500.0_real64,87500.0_real64]
    om=[7.0_real64,4.0_real64]; ot=[281.0_real64,294.0_real64]
    oq(:,1)=[.018,.004,.002,.001,.001,.001]; oq(:,2)=[.006,.003,.003,.002,.001,.002]
    ni=[99999.125_real64,97500.0_real64,92500.0_real64,87500.0_real64]
    CALL remap_pressure_column(oi,om,ot,oq,ni,nm,nt,nq,status)
    CALL check(status==STATUS_OK,'actual near-center partition accepted',n)
    CALL check_near(nm(1),om(1)*(2499.125_real64)/(7499.125_real64),1.0e-12_real64, &
                    'near-center split dry mass',n)
    CALL check(same_bits_1d(nm(3:3),om(2:2)) .AND. same_bits_1d(nt(3:3),ot(2:2)) .AND. &
               same_bits_1d(nq(:,3),oq(:,2)),'untouched upper layer is bitwise exact',n)
  END SUBROUTINE test_actual_center_partition

  ! Scalar simulation of canonical storage: pressure mass is independently
  ! formed as A*dp/g, while q and T are round-cast to real32 before refresh's
  ! md=pressure_mass/(1+sum stored six-species q).  This does not claim that
  ! a full cloud_bal_state transaction is exercised here.
  SUBROUTINE test_float32_storage_regression(n)
    INTEGER, INTENT(INOUT) :: n
    REAL(real64) :: oi(3),om(2),ot(2),oq(6,2),ni(4),nm(3),nt(3),nq(6,3)
    REAL(real64) :: em(3),et(3),eq(6,3),old_pressure_mass(2),pressure_mass(3),reference_mass(3),stored_mass(3)
    REAL(real64) :: stored_q(6,3),stored_t(3),species_ref(6),species_stored(6)
    REAL(real32) :: stored_q32(6,3),stored_t32(3)
    REAL(real64), PARAMETER :: area=173456.75_real64,gravity=9.80665_real64
    REAL(real64), PARAMETER :: u32=0.5_real64*EPSILON(1.0_real32)
    REAL(real64) :: d,ds,q_error,t_error,md_bound,species_bound(6),dh_bound,energy_bound
    REAL(real64) :: h_ref,energy_ref,energy_stored,slack,max_md_diff,max_md_bound
    REAL(real64) :: max_species_diff,max_species_bound,max_energy_diff,max_energy_bound
    INTEGER :: status,k

    oi=[100000.0_real64,92000.0_real64,84000.0_real64]
    ot=[255.1234567_real64,320.7654321_real64]
    oq(:,1)=[.01327193_real64,.00234117_real64,.00071329_real64,.00121731_real64, &
             .00038127_real64,.00062919_real64]
    oq(:,2)=oq(:,1)
    old_pressure_mass=area*(oi(:2)-oi(2:))/(gravity)
    om=old_pressure_mass/(1.0_real64+SUM(oq,1))
    ni=[100000.0_real64,96000.0_real64,88000.0_real64,84000.0_real64]
    CALL oracle(oi,om,ot,oq,ni,em,et,eq)
    CALL remap_pressure_column(oi,om,ot,oq,ni,nm,nt,nq,status)
    CALL check(status==STATUS_OK,'float32-storage remap accepted',n)
    CALL check(ALL(ABS(nm-em)<=128.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(em))) .AND. &
               ALL(ABS(nt-et)<=128.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(et))) .AND. &
               ALL(ABS(nq-eq)<=128.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(eq))), &
               'storage fixture agrees with independent remap oracle',n)

    ! The canonical cast is applied to the actual production remap result;
    ! the independent oracle above remains a separate correctness check.
    stored_q32=REAL(nq,real32); stored_q=REAL(stored_q32,real64)
    stored_t32=REAL(nt,real32); stored_t=REAL(stored_t32,real64)
    pressure_mass=area*(ni(:3)-ni(2:))/(gravity)
    reference_mass=pressure_mass/(1.0_real64+SUM(nq,1))
    stored_mass=pressure_mass/(1.0_real64+SUM(stored_q,1))
    max_md_diff=0.0_real64; max_md_bound=0.0_real64
    max_species_diff=0.0_real64; max_species_bound=0.0_real64
    max_energy_diff=0.0_real64; max_energy_bound=0.0_real64
    DO k=1,3
      CALL check_near(nm(k),reference_mass(k),128.0_real64*EPSILON(1.0_real64), &
                      'independent pressure-mass reference',n)
      d=1.0_real64+SUM(nq(:,k)); ds=1.0_real64+SUM(stored_q(:,k))
      q_error=u32*SUM(ABS(nq(:,k))); t_error=u32*ABS(nt(k))
      md_bound=pressure_mass(k)*q_error/(d*ds)
      species_bound=pressure_mass(k)*(u32*ABS(nq(:,k))/ds+ABS(nq(:,k))*q_error/(d*ds))
      CALL check(ABS(stored_mass(k)-reference_mass(k))<=md_bound+ &
                 64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(reference_mass(k))), &
                 'dry-mass storage analytic bound',n)
      CALL check(ALL(ABS(stored_q(:,k)-nq(:,k))<=u32*ABS(nq(:,k))+ &
                     64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(nq(:,k)))), &
                 'six-species real32 roundcast bound',n)
      CALL check(ABS(stored_t(k)-nt(k))<=t_error+ &
                 64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(nt(k))), &
                 'temperature real32 roundcast bound',n)
      species_ref=reference_mass(k)*nq(:,k); species_stored=stored_mass(k)*stored_q(:,k)
      CALL check(ALL(ABS(species_stored-species_ref)<=species_bound+ &
                     64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(species_ref))), &
                 'six-species extensive storage bound',n)
      h_ref=reduced_enthalpy(nt(k),nq(:,k)); energy_ref=reference_mass(k)*h_ref
      energy_stored=stored_mass(k)*reduced_enthalpy(stored_t(k),stored_q(:,k))
      dh_bound=mixture_cp(stored_q(:,k))*t_error+ABS(nt(k)-T0)* &
                SUM(ABS(CP)*ABS(stored_q(:,k)-nq(:,k)))+SUM(ABS(H0)*ABS(stored_q(:,k)-nq(:,k)))
      energy_bound=ABS(stored_mass(k))*dh_bound+ABS(h_ref)*md_bound
      slack=64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(energy_ref),ABS(energy_stored))
      CALL check(ABS(energy_stored-energy_ref)<=energy_bound+slack, &
                 'reduced-enthalpy storage roundoff bound',n)
      max_md_diff=MAX(max_md_diff,ABS(stored_mass(k)-reference_mass(k))); max_md_bound=MAX(max_md_bound,md_bound)
      max_species_diff=MAX(max_species_diff,MAXVAL(ABS(species_stored-species_ref)))
      max_species_bound=MAX(max_species_bound,MAXVAL(species_bound))
      max_energy_diff=MAX(max_energy_diff,ABS(energy_stored-energy_ref)); max_energy_bound=MAX(max_energy_bound,energy_bound)
    END DO
    CALL check(MAXVAL(ABS(stored_q-nq))>0.25_real64*u32*MAXVAL(ABS(nq)), &
               'species storage rounding is nonzero and measurable',n)
    CALL check(MAXVAL(ABS(stored_t-nt))>0.10_real64*u32*MAXVAL(ABS(nt)), &
               'temperature storage rounding is nonzero and measurable',n)
    CALL check(max_md_diff>0.10_real64*max_md_bound,'dry-mass storage difference is nonzero',n)
    CALL check(max_species_diff>0.10_real64*max_species_bound,'species-mass storage difference is nonzero',n)
    CALL check(max_energy_diff>0.0_real64 .AND. max_energy_diff<=max_energy_bound+ &
               64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,max_energy_diff), &
               'enthalpy storage difference is nonzero and bounded',n)
  END SUBROUTINE test_float32_storage_regression

  SUBROUTINE test_float32_storage_identity(n)
    INTEGER, INTENT(INOUT) :: n
    REAL(real64) :: oi(2),om(1),ot(1),oq(6,1),ni(2),nm(1),nt(1),nq(6,1),pressure_mass(1),stored_m(1)
    REAL(real64) :: stored_q(6,1),stored_t(1)
    REAL(real32) :: stored_q32(6,1),stored_t32(1)
    REAL(real64), PARAMETER :: area=173456.75_real64,gravity=9.80665_real64
    INTEGER :: status

    oi=[100000.0_real64,90000.0_real64]; ni=oi; ot=[280.0_real64]
    oq(:,1)=[1.0_real64/1024.0_real64,2.0_real64/1024.0_real64,4.0_real64/1024.0_real64, &
             8.0_real64/1024.0_real64,16.0_real64/1024.0_real64,32.0_real64/1024.0_real64]
    pressure_mass=area*(oi(1)-oi(2))/gravity; om=pressure_mass/(1.0_real64+SUM(oq,1))
    nm=-1.0_real64; nt=-2.0_real64; nq=-3.0_real64
    CALL remap_pressure_column(oi,om,ot,oq,ni,nm,nt,nq,status)
    stored_q32=REAL(nq,real32); stored_q=REAL(stored_q32,real64)
    stored_t32=REAL(nt,real32); stored_t=REAL(stored_t32,real64)
    stored_m=pressure_mass/(1.0_real64+SUM(stored_q,1))
    CALL check(status==STATUS_OK,'rounding-free identity remap accepted',n)
    CALL check(same_bits_1d(stored_m,nm) .AND. same_bits_1d(stored_t,nt) .AND. &
               same_bits_1d(stored_q(:,1),nq(:,1)), &
               'exactly representable identity survives canonical storage bitwise',n)
  END SUBROUTINE test_float32_storage_identity

  SUBROUTINE expect_reject(oi,om,ot,oq,ni_in,message,n)
    REAL(real64), INTENT(IN) :: oi(:),om(:),ot(:),oq(:,:),ni_in(:)
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: n
    REAL(real64) :: ni(SIZE(ni_in)),nm( SIZE(ni_in)-1),nt(SIZE(ni_in)-1)
    REAL(real64) :: nq(6,SIZE(ni_in)-1),bi(SIZE(ni_in)),bm(SIZE(ni_in)-1)
    REAL(real64) :: bt(SIZE(ni_in)-1),bq(6,SIZE(ni_in)-1)
    INTEGER :: status

    ni=ni_in; nm=-101.0_real64; nt=-102.0_real64; nq=-103.0_real64
    bi=ni; bm=nm; bt=nt; bq=nq
    CALL remap_pressure_column(oi,om,ot,oq,ni,nm,nt,nq,status)
    CALL check(status==STATUS_FAILED,message//' status',n)
    CALL check(same_bits_1d(ni,bi) .AND. same_bits_1d(nm,bm) .AND. same_bits_1d(nt,bt) .AND. &
               same_bits_2d(nq,bq),message//' atomic rollback',n)
  END SUBROUTINE expect_reject

  SUBROUTINE test_rejections_are_atomic(n)
    INTEGER, INTENT(INOUT) :: n
    REAL(real64) :: oi(4),om(3),ot(3),oq(6,3),ni(4),bad_i(4),bad_m(3),bad_t(2),bad_q(6,3)
    REAL(real64) :: short_m(2),short_t(2),short_q(6,2),short_m_before(2),short_t_before(2)
    REAL(real64) :: short_q_before(6,2),short_i(4),short_i_before(4)
    INTEGER :: status

    oi=[100000.0_real64,93000.0_real64,87000.0_real64,80000.0_real64]
    om=[2.0_real64,3.0_real64,4.0_real64]; ot=[260.0_real64,275.0_real64,290.0_real64]
    oq=0.0_real64; oq(:,1)=[.02,.003,.001,.001,.001,.001]
    oq(:,2)=[.01,.004,.002,.001,.001,.002]; oq(:,3)=[.03,.002,.001,.002,.001,.001]
    ni=oi
    bad_i=oi; bad_i(2)=ieee_value(0.0_real64,ieee_positive_inf)
    CALL expect_reject(bad_i,om,ot,oq,ni,'nonfinite interface rejects',n)
    bad_m=om; bad_m(2)=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL expect_reject(oi,bad_m,ot,oq,ni,'nonfinite mass rejects',n)
    bad_i=[100000.0_real64,90000.0_real64,95000.0_real64,80000.0_real64]
    CALL expect_reject(bad_i,om,ot,oq,ni,'reversed interface rejects',n)
    bad_i=[100000.0_real64,93000.0_real64,93000.0_real64,80000.0_real64]
    CALL expect_reject(bad_i,om,ot,oq,ni,'duplicate interface rejects',n)
    bad_i=ni; bad_i(1)=100001.0_real64
    CALL expect_reject(oi,om,ot,oq,bad_i,'unequal endpoints reject',n)
    bad_t=ot(:2); bad_q=oq
    CALL expect_reject(oi,om,bad_t,bad_q,ni,'malformed input shape rejects',n)
    short_i=ni; short_m=-201.0_real64; short_t=-202.0_real64; short_q=-203.0_real64
    short_i_before=short_i; short_m_before=short_m; short_t_before=short_t; short_q_before=short_q
    CALL remap_pressure_column(oi,om,ot,oq,short_i,short_m,short_t,short_q,status)
    CALL check(status==STATUS_FAILED,'malformed output shape rejects',n)
    CALL check(same_bits_1d(short_i,short_i_before) .AND. same_bits_1d(short_m,short_m_before) .AND. &
               same_bits_1d(short_t,short_t_before) .AND. same_bits_2d(short_q,short_q_before), &
               'malformed output shape is atomic',n)
  END SUBROUTINE test_rejections_are_atomic

  SUBROUTINE emit_transition_fixture(path,n)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER, INTENT(INOUT) :: n
    REAL(real64) :: old_i(4),old_m(3),old_t(3),old_q(6,3)
    REAL(real64) :: new_i(5),new_m(4),new_t(4),new_q(6,4)
    INTEGER :: status,unit,ios

    ! The first donor is an explicit thin boundary strip. The first
    ! destination receives that strip plus the next donor, while interior
    ! interfaces split and merge the remaining donors. Keep this compact case
    ! independent of the tests above as a stable cross-language contract.
    old_i=[100050.0_real64,100000.0_real64,95000.0_real64,90000.0_real64]
    old_m=[0.125_real64,5.50_real64,3.25_real64]
    old_t=[252.75_real64,319.25_real64,281.50_real64]
    old_q(:,1)=[.021_real64,.0035_real64,.0012_real64,.0011_real64,.0007_real64,.0013_real64]
    old_q(:,2)=[.009_real64,.0045_real64,.0025_real64,.0014_real64,.0011_real64,.0022_real64]
    old_q(:,3)=[.028_real64,.0022_real64,.0011_real64,.0023_real64,.0008_real64,.0017_real64]
    new_i=[100050.0_real64,98750.0_real64,96000.0_real64,93000.0_real64,90000.0_real64]
    CALL remap_pressure_column(old_i,old_m,old_t,old_q,new_i,new_m,new_t,new_q,status)
    CALL check(status==STATUS_OK,'fixture asymmetric remap accepted',n)
    IF (status/=STATUS_OK) RETURN
    OPEN(NEWUNIT=unit,FILE=TRIM(path),STATUS='REPLACE',ACTION='WRITE',IOSTAT=ios)
    IF (ios/=0) THEN
      CALL check(.FALSE.,'fixture open succeeded',n)
      RETURN
    END IF
    WRITE(unit,'(A)') 'PRESSURE_TRANSITION_REMAP_FIXTURE_V1'
    CALL write_vector(unit,'OLD_INTERFACES',old_i)
    CALL write_vector(unit,'OLD_DRY_MASS',old_m)
    CALL write_vector(unit,'OLD_TEMPERATURE',old_t)
    CALL write_matrix(unit,'OLD_SPECIES',old_q)
    CALL write_vector(unit,'NEW_INTERFACES',new_i)
    CALL write_vector(unit,'RESULT_DRY_MASS',new_m)
    CALL write_vector(unit,'RESULT_TEMPERATURE',new_t)
    CALL write_matrix(unit,'RESULT_SPECIES',new_q)
    WRITE(unit,'(A)') 'END'
    CLOSE(unit,IOSTAT=ios)
    CALL check(ios==0,'fixture close succeeded',n)
  END SUBROUTINE emit_transition_fixture

  SUBROUTINE write_vector(unit,label,values)
    INTEGER, INTENT(IN) :: unit
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL(real64), INTENT(IN) :: values(:)
    INTEGER :: k
    WRITE(unit,'(A,1X,I0)') TRIM(label),SIZE(values)
    DO k=1,SIZE(values)
      WRITE(unit,'(ES24.16E3)') values(k)
    END DO
  END SUBROUTINE write_vector

  SUBROUTINE write_matrix(unit,label,values)
    INTEGER, INTENT(IN) :: unit
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL(real64), INTENT(IN) :: values(:,:)
    INTEGER :: i,j
    WRITE(unit,'(A,1X,I0,1X,I0)') TRIM(label),SIZE(values,1),SIZE(values,2)
    DO i=1,SIZE(values,1)
      DO j=1,SIZE(values,2)
        WRITE(unit,'(ES24.16E3)') values(i,j)
      END DO
    END DO
  END SUBROUTINE write_matrix

END PROGRAM test_pressure_column_remap
