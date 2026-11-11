! Complete dry-air specific hydrometeor moments without changing analyzed water.
! The caller supplies scheme-specific bounds and independently sourced priors.
MODULE cloud_bal_microphysics_initialization
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32, real64, int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_state, ONLY: cloud_bal_state_type, field3d, moment_bundle, &
    MOMENT_NC, MOMENT_NI, MOMENT_NR, MOMENT_NN, MOMENT_BG, &
    MOMENT_OBSERVED, MOMENT_BACKGROUND, MOMENT_PRIOR, MOMENT_ZERO, &
    STATUS_OK, STATUS_DEGRADED, STATUS_FAILED, cell_is_usable, moment_bundle_present
  IMPLICIT NONE
  PRIVATE

  ! Bounds are on q/N (kg/particle) for NC, NI, NR and q/BG (kg/m3)
  ! for BG. Thresholds are explicit scheme/source declarations in kg/kg dry air.
  TYPE, PUBLIC :: microphysics_completion_policy
    CHARACTER(LEN=256) :: source = ''
    CHARACTER(LEN=256) :: density_source = ''
    REAL(real64) :: number_cap(4) = 0.0_real64
    REAL(real64) :: mass_threshold(5) = 0.0_real64
    REAL(real64) :: lower(5) = 0.0_real64
    REAL(real64) :: upper(5) = 0.0_real64
  END TYPE microphysics_completion_policy
  INTEGER, PARAMETER, PUBLIC :: MOMENT_FAILURE_OTHER=1, MOMENT_FAILURE_EMPTY_ANALYTICAL_INTERVAL=2, &
    MOMENT_FAILURE_CANDIDATE=3
  PUBLIC :: complete_microphysics, complete_initialization_state

CONTAINS

  ! Entirely absent bundles mean no candidates; partially allocated bundles
  ! are invalid. Only the selected prior is validated; unused alternatives are ignored.
  ! state and moments must be distinct actual objects, as must all inputs
  ! and the output bundle. The state wrapper below offers a single-state copy.
  SUBROUTINE complete_microphysics(state,moments,prior,policy,status,native_den,observed,failed_location, &
      failure_reason,feasible_interval)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(moment_bundle), INTENT(INOUT) :: moments
    TYPE(moment_bundle), INTENT(IN) :: prior
    TYPE(microphysics_completion_policy), INTENT(IN) :: policy
    INTEGER, INTENT(OUT) :: status
    REAL(real32), INTENT(IN) :: native_den(:,:,:)
    TYPE(moment_bundle), INTENT(IN), OPTIONAL :: observed
    INTEGER, INTENT(OUT), OPTIONAL :: failed_location(4)
    INTEGER, INTENT(OUT), OPTIONAL :: failure_reason
    REAL(real64), INTENT(OUT), OPTIONAL :: feasible_interval(2)
    TYPE(moment_bundle) :: result
    INTEGER :: shape4(4), i,j,k,s
    REAL(real64) :: mass, candidate, interval(2)
    LOGICAL :: found, unresolved, has_prior, has_observed, prior_valid, empty_interval

    status=STATUS_FAILED
    IF (PRESENT(failure_reason)) failure_reason=MOMENT_FAILURE_OTHER
    IF (PRESENT(feasible_interval)) feasible_interval=0.0_real64
    IF (PRESENT(failed_location)) failed_location=0
    shape4=[state%grid%nx,state%grid%ny,state%grid%nz,5]
    IF (ANY(shape4<=0)) RETURN
    IF (moment_bundle_present(moments)) THEN
      IF (.NOT.bundle_shape(moments,shape4)) RETURN
    END IF
    has_prior=moment_bundle_present(prior)
    IF (has_prior) THEN
      IF (.NOT.bundle_shape(prior,shape4)) RETURN
    END IF
    has_observed=.FALSE.
    IF (PRESENT(observed)) THEN
      has_observed=moment_bundle_present(observed)
      IF (has_observed) THEN
        IF (.NOT.bundle_shape(observed,shape4)) RETURN
      END IF
    END IF
    IF (.NOT.policy_valid(policy)) RETURN
    IF (ANY(SHAPE(native_den)/=shape4(1:3))) RETURN
    IF (.NOT.ALL(ieee_is_finite(native_den))) RETURN
    IF (ANY(native_den<=0.0_real32)) RETURN
    IF (.NOT.mass_field_valid(state%cloud_water,shape4(1:3),state%pressure%valid_time)) RETURN
    IF (.NOT.mass_field_valid(state%cloud_ice,shape4(1:3),state%pressure%valid_time)) RETURN
    IF (.NOT.mass_field_valid(state%rain,shape4(1:3),state%pressure%valid_time)) RETURN
    IF (.NOT.mass_field_valid(state%graupel,shape4(1:3),state%pressure%valid_time)) RETURN

    IF (moment_bundle_present(moments)) THEN
      result=moments
    ELSE
      ALLOCATE(result%value(shape4(1),shape4(2),shape4(3),shape4(4)), &
               result%valid(shape4(1),shape4(2),shape4(3),shape4(4)), &
               result%provenance(shape4(1),shape4(2),shape4(3),shape4(4)))
      result%value=0.0_real64
      result%valid=.FALSE.
      result%provenance=0
    END IF
    unresolved=.FALSE.
    DO k=1,shape4(3)
      DO j=1,shape4(2)
        DO i=1,shape4(1)
          DO s=1,5
            IF (PRESENT(failed_location)) failed_location=[i,j,k,s]
            IF (PRESENT(feasible_interval)) feasible_interval=0.0_real64
            empty_interval=.FALSE.
            IF (s==MOMENT_NN) THEN
              mass=0.0_real64
            ELSE
              SELECT CASE(s)
              CASE(MOMENT_NC)
                mass=REAL(state%cloud_water%value(i,j,k),real64)
              CASE(MOMENT_NI)
                mass=REAL(state%cloud_ice%value(i,j,k),real64)
              CASE(MOMENT_NR)
                mass=REAL(state%rain%value(i,j,k),real64)
              CASE(MOMENT_BG)
                mass=REAL(state%graupel%value(i,j,k),real64)
              END SELECT
            END IF
            ! This analytical interval uses the exact cap/density. Native REAL32
            ! rounding can admit a boundary candidate even when it is empty;
            ! therefore use it to classify failure, not to reject candidates.
            IF (s<=MOMENT_NR .AND. mass>0.0_real64) THEN
              IF (mass>=policy%mass_threshold(s)) THEN
                interval(1)=bounded_ratio(mass,policy%upper(s))
                interval(2)=MIN(bounded_ratio(mass,policy%lower(s)), &
                  bounded_ratio(policy%number_cap(s),REAL(native_den(i,j,k),real64)))
                IF (PRESENT(feasible_interval)) feasible_interval=interval
                empty_interval=interval_is_empty(interval,mass,policy%upper(s),policy%number_cap(s), &
                  REAL(native_den(i,j,k),real64))
              END IF
            END IF
            found=.FALSE.
            IF (has_observed) THEN
              IF (observed%valid(i,j,k,s)) THEN
                IF (observed%provenance(i,j,k,s)/=MOMENT_OBSERVED) RETURN
                candidate=observed%value(i,j,k,s)
                IF (admissible(candidate,mass,s,policy,native_den(i,j,k))) THEN
                  result%value(i,j,k,s)=candidate
                  result%valid(i,j,k,s)=.TRUE.
                  result%provenance(i,j,k,s)=MOMENT_OBSERVED
                  found=.TRUE.
                END IF
              END IF
            END IF
            IF (.NOT.found .AND. result%valid(i,j,k,s)) THEN
              IF (result%provenance(i,j,k,s)/=MOMENT_OBSERVED .AND. &
                  result%provenance(i,j,k,s)/=MOMENT_BACKGROUND .AND. &
                  result%provenance(i,j,k,s)/=MOMENT_PRIOR .AND. &
                  result%provenance(i,j,k,s)/=MOMENT_ZERO) RETURN
              IF (admissible(result%value(i,j,k,s),mass,s,policy,native_den(i,j,k))) found=.TRUE.
            END IF
            IF (found) CYCLE
            result%valid(i,j,k,s)=.FALSE.
            IF (s/=MOMENT_NN .AND. mass==0.0_real64) THEN
              result%value(i,j,k,s)=0.0_real64
              result%valid(i,j,k,s)=.TRUE.
              result%provenance(i,j,k,s)=MOMENT_ZERO
              CYCLE
            END IF
            prior_valid=.FALSE.
            IF (has_prior) prior_valid=prior%valid(i,j,k,s)
            IF (prior_valid) THEN
              IF (PRESENT(failure_reason)) THEN
                failure_reason=MOMENT_FAILURE_CANDIDATE
                IF (empty_interval) failure_reason=MOMENT_FAILURE_EMPTY_ANALYTICAL_INTERVAL
              END IF
              IF (prior%provenance(i,j,k,s)/=MOMENT_OBSERVED .AND. &
                  prior%provenance(i,j,k,s)/=MOMENT_PRIOR) RETURN
              candidate=prior%value(i,j,k,s)
              IF (.NOT.ieee_is_finite(candidate)) RETURN
              IF (candidate<0.0_real64) RETURN
              IF (s/=MOMENT_NN) THEN
                IF (candidate<policy%lower(s) .OR. candidate>policy%upper(s)) RETURN
                IF (.NOT.safe_ratio(mass,candidate)) RETURN
                candidate=mass/candidate
              END IF
              IF (.NOT.admissible(candidate,mass,s,policy,native_den(i,j,k))) RETURN
              result%value(i,j,k,s)=candidate
              result%valid(i,j,k,s)=.TRUE.
              result%provenance(i,j,k,s)=prior%provenance(i,j,k,s)
              IF (PRESENT(failure_reason)) failure_reason=MOMENT_FAILURE_OTHER
            ELSE IF (s==MOMENT_NN .OR. mass>=policy%mass_threshold(s)) THEN
              IF (PRESENT(failure_reason) .AND. empty_interval) failure_reason=MOMENT_FAILURE_EMPTY_ANALYTICAL_INTERVAL
              RETURN
            ELSE
              unresolved=.TRUE.
            END IF
          END DO
        END DO
      END DO
    END DO
    moments=result
    status=STATUS_OK
    IF (unresolved) status=STATUS_DEGRADED
    IF (PRESENT(failed_location)) failed_location=0
    IF (PRESENT(failure_reason)) failure_reason=0
    IF (PRESENT(feasible_interval)) feasible_interval=0.0_real64
  END SUBROUTINE complete_microphysics

  ! Input and output must be distinct actual variables. The output is committed
  ! only after completion succeeds; a failed operation leaves it untouched.
  SUBROUTINE complete_initialization_state(state,output,prior,policy,status,native_den,observed,failed_location, &
      failure_reason,feasible_interval)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: output
    TYPE(moment_bundle), INTENT(IN) :: prior
    TYPE(microphysics_completion_policy), INTENT(IN) :: policy
    INTEGER, INTENT(OUT) :: status
    REAL(real32), INTENT(IN) :: native_den(:,:,:)
    TYPE(moment_bundle), INTENT(IN), OPTIONAL :: observed
    INTEGER, INTENT(OUT), OPTIONAL :: failed_location(4)
    INTEGER, INTENT(OUT), OPTIONAL :: failure_reason
    REAL(real64), INTENT(OUT), OPTIONAL :: feasible_interval(2)
    TYPE(cloud_bal_state_type) :: candidate
    INTEGER :: shape3(3)
    INTEGER(int64) :: valid_time

    status=STATUS_FAILED
    IF (PRESENT(failure_reason)) failure_reason=MOMENT_FAILURE_OTHER
    IF (PRESENT(feasible_interval)) feasible_interval=0.0_real64
    IF (PRESENT(failed_location)) failed_location=0
    shape3=[state%grid%nx,state%grid%ny,state%grid%nz]
    IF (ANY(shape3<=0)) RETURN
    valid_time=state%pressure%valid_time
    IF (.NOT.field_valid(state%pressure,shape3,valid_time,'Pa',100.0_real32,120000.0_real32)) RETURN
    IF (.NOT.field_valid(state%temperature,shape3,valid_time,'K',150.0_real32,350.0_real32)) RETURN
    IF (.NOT.field_valid(state%vapor,shape3,valid_time,'kg kg-1 dryair',0.0_real32,0.2_real32)) RETURN
    IF (.NOT.mass_field_valid(state%snow,shape3,valid_time)) RETURN
    candidate=state
    CALL complete_microphysics(state,candidate%moments,prior,policy,status,native_den,observed,failed_location, &
      failure_reason,feasible_interval)
    IF (status/=STATUS_FAILED) output=candidate
  END SUBROUTINE complete_initialization_state

  LOGICAL FUNCTION bundle_shape(bundle,shape4)
    TYPE(moment_bundle), INTENT(IN) :: bundle
    INTEGER, INTENT(IN) :: shape4(4)
    bundle_shape=.FALSE.
    IF (.NOT.ALLOCATED(bundle%value) .OR. .NOT.ALLOCATED(bundle%valid) .OR. &
        .NOT.ALLOCATED(bundle%provenance)) RETURN
    IF (ANY(SHAPE(bundle%value)/=shape4) .OR. ANY(SHAPE(bundle%valid)/=shape4) .OR. &
        ANY(SHAPE(bundle%provenance)/=shape4)) RETURN
    bundle_shape=.TRUE.
  END FUNCTION bundle_shape

  LOGICAL FUNCTION policy_valid(policy)
    TYPE(microphysics_completion_policy), INTENT(IN) :: policy
    INTEGER :: s
    policy_valid=.FALSE.
    IF (LEN_TRIM(policy%source)==0 .OR. LEN_TRIM(policy%density_source)==0) RETURN
    IF (.NOT.ALL(ieee_is_finite(policy%number_cap))) RETURN
    IF (ANY(policy%number_cap<=0.0_real64)) RETURN
    DO s=1,5
      IF (s==MOMENT_NN) CYCLE
      IF (.NOT.ieee_is_finite(policy%mass_threshold(s)) .OR. &
          .NOT.ieee_is_finite(policy%lower(s)) .OR. .NOT.ieee_is_finite(policy%upper(s))) RETURN
      IF (policy%mass_threshold(s)<0.0_real64 .OR. policy%lower(s)<=0.0_real64 .OR. &
          policy%upper(s)<policy%lower(s)) RETURN
    END DO
    policy_valid=.TRUE.
  END FUNCTION policy_valid

  LOGICAL FUNCTION mass_field_valid(field,shape3,valid_time)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: shape3(3)
    INTEGER(int64), INTENT(IN) :: valid_time
    mass_field_valid=field_valid(field,shape3,valid_time,'kg kg-1 dryair',0.0_real32,HUGE(0.0_real32))
  END FUNCTION mass_field_valid

  LOGICAL FUNCTION field_valid(field,shape3,valid_time,unit,lower,upper)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: shape3(3)
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=*), INTENT(IN) :: unit
    REAL(real32), INTENT(IN) :: lower,upper
    field_valid=.FALSE.
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) RETURN
    IF (ANY(SHAPE(field%value)/=shape3) .OR. ANY(SHAPE(field%valid)/=shape3) .OR. &
        ANY(SHAPE(field%quality)/=shape3) .OR. ANY(SHAPE(field%source)/=shape3)) RETURN
    IF (field%unit/=unit .OR. field%valid_time/=valid_time) RETURN
    IF (.NOT.ALL(cell_is_usable(field%valid,field%quality,field%source))) RETURN
    IF (.NOT.ALL(ieee_is_finite(field%value))) RETURN
    IF (ANY(field%value<lower) .OR. ANY(field%value>upper)) RETURN
    field_valid=.TRUE.
  END FUNCTION field_valid

  LOGICAL FUNCTION safe_ratio(numerator,denominator)
    REAL(real64), INTENT(IN) :: numerator,denominator
    REAL(real64) :: exponent
    safe_ratio=.FALSE.
    IF (numerator<=0.0_real64 .OR. denominator<=0.0_real64) RETURN
    exponent=LOG(numerator)-LOG(denominator)
    IF (exponent>=LOG(HUGE(numerator)) .OR. exponent<=LOG(TINY(numerator))) RETURN
    safe_ratio=.TRUE.
  END FUNCTION safe_ratio

  ! Saturation keeps interval diagnostics representable without floating-point traps.
  REAL(real64) FUNCTION bounded_ratio(numerator,denominator) RESULT(value)
    REAL(real64), INTENT(IN) :: numerator,denominator
    REAL(real64) :: exponent
    exponent=LOG(numerator)-LOG(denominator)
    IF (exponent>=LOG(HUGE(value))) THEN
      value=HUGE(value)
    ELSE IF (exponent<=LOG(TINY(value))) THEN
      value=0.0_real64
    ELSE
      value=numerator/denominator
    END IF
  END FUNCTION bounded_ratio

  LOGICAL FUNCTION interval_is_empty(interval,mass,upper,cap,density)
    REAL(real64), INTENT(IN) :: interval(2),mass,upper,cap,density
    interval_is_empty=interval(1)>interval(2)
    ! When both bounds saturate, compare their logarithms to avoid treating
    ! two unrepresentable, unequal ratios as an equal interval.
    IF (interval(1)==interval(2) .AND. &
        (interval(1)==0.0_real64 .OR. interval(1)==HUGE(0.0_real64))) THEN
      interval_is_empty=LOG(mass)-LOG(upper)>LOG(cap)-LOG(density)
    END IF
  END FUNCTION interval_is_empty

  ! Check the values actually read by a REAL32 native model. Reject a candidate
  ! before conversion when it would overflow or underflow; never clip a prior.
  LOGICAL FUNCTION admissible(value,mass,s,policy,density)
    REAL(real64), INTENT(IN) :: value,mass
    INTEGER, INTENT(IN) :: s
    TYPE(microphysics_completion_policy), INTENT(IN) :: policy
    REAL(real32), INTENT(IN) :: density
    REAL(real64) :: mean, stored, product
    REAL(real32) :: native_value, native_number
    admissible=.FALSE.
    IF (.NOT.ieee_is_finite(value)) RETURN
    IF (value<0.0_real64 .OR. value>REAL(HUGE(0.0_real32),real64)) RETURN
    IF (value>0.0_real64 .AND. value<REAL(TINY(0.0_real32),real64)) RETURN
    native_value=REAL(value,real32)
    stored=REAL(native_value,real64)
    IF (s<=MOMENT_NN .AND. stored>0.0_real64) THEN
      product=stored*REAL(density,real64)
      IF (product>REAL(HUGE(0.0_real32),real64) .OR. &
          product<REAL(TINY(0.0_real32),real64)) RETURN
      native_number=native_value*density
      IF (REAL(native_number,real64)>policy%number_cap(s)) RETURN
    END IF
    IF (s==MOMENT_NN) THEN
      admissible=.TRUE.
      RETURN
    END IF
    IF (mass==0.0_real64) THEN
      admissible=stored==0.0_real64
      RETURN
    END IF
    IF (.NOT.safe_ratio(mass,stored)) RETURN
    mean=mass/stored
    admissible=mean>=policy%lower(s) .AND. mean<=policy%upper(s)
  END FUNCTION admissible
END MODULE cloud_bal_microphysics_initialization
