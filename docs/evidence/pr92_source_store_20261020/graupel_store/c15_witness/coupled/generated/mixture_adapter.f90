module c15_mixture_adapter
  use iso_fortran_env, only: int32,int64,real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer,parameter :: real128=selected_real_kind(33,4931)
contains

  PURE LOGICAL FUNCTION strict_graupel_pair(q,n,minimum_ratio,maximum_ratio)
    REAL(real64),INTENT(IN) :: q,n,minimum_ratio,maximum_ratio
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128) :: q128,n128
    strict_graupel_pair=.FALSE.
    IF (.NOT.ALL(ieee_is_finite([q,n,minimum_ratio,maximum_ratio]))) RETURN
    IF (q<0.0_real64.OR.n<0.0_real64.OR.minimum_ratio<=0.0_real64.OR. &
        maximum_ratio<minimum_ratio) RETURN
    IF (q==0.0_real64.AND.n==0.0_real64) THEN
      strict_graupel_pair=.TRUE.; RETURN
    END IF
    IF (q<=0.0_real64.OR.n<=0.0_real64) RETURN
    q128=REAL(q,real128); n128=REAL(n,real128)
    strict_graupel_pair=q128>=REAL(minimum_ratio,real128)*n128.AND. &
                        q128<=REAL(maximum_ratio,real128)*n128
  END FUNCTION strict_graupel_pair

  SUBROUTINE store_graupel_mixture(weights,q_terms,n_terms,denominator,minimum_ratio, &
      maximum_ratio,reference_q,reference_n,stored_q,stored_n,delta_q,delta_n,valid)
    REAL(real64),INTENT(IN) :: weights(7),minimum_ratio,maximum_ratio,reference_q,reference_n
    REAL(real32),INTENT(IN) :: q_terms(7),n_terms(7),denominator
    REAL(real32),INTENT(OUT) :: stored_q,stored_n
    REAL(real64),INTENT(OUT) :: delta_q,delta_n
    LOGICAL,INTENT(OUT) :: valid
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128) :: qsum,nsum,qvalue,nvalue,qcheck,ncheck
    INTEGER :: term,attempt
    stored_q=-1.0_real32; stored_n=-1.0_real32
    delta_q=0.0_real64; delta_n=0.0_real64; valid=.FALSE.
    IF (.NOT.ALL(ieee_is_finite(weights))) RETURN
    IF (ANY(weights<0.0_real64)) RETURN
    IF (.NOT.ALL(ieee_is_finite(q_terms))) RETURN
    IF (.NOT.ALL(ieee_is_finite(n_terms))) RETURN
    IF (.NOT.ieee_is_finite(denominator)) RETURN
    IF (denominator<=0.0_real32) RETURN
    IF (.NOT.ieee_is_finite(reference_q).OR..NOT.ieee_is_finite(reference_n)) RETURN
    qsum=0.0_real128; nsum=0.0_real128
    DO term=1,7
      IF (weights(term)==0.0_real64) CYCLE
      IF (.NOT.strict_graupel_pair(REAL(q_terms(term),real64),REAL(n_terms(term),real64), &
                                   minimum_ratio,maximum_ratio)) RETURN
      qsum=qsum+REAL(weights(term),real128)*REAL(q_terms(term),real128)
      nsum=nsum+REAL(weights(term),real128)*REAL(n_terms(term),real128)
    END DO
    qvalue=qsum/REAL(denominator,real128); nvalue=nsum/REAL(denominator,real128)
    IF (.NOT.ieee_is_finite(qvalue).OR..NOT.ieee_is_finite(nvalue)) RETURN
    IF (qvalue>REAL(HUGE(0.0_real32),real128).OR.nvalue>REAL(HUGE(0.0_real32),real128)) RETURN
    stored_q=REAL(qvalue,real32); stored_n=REAL(nvalue,real32)
    IF (.NOT.ieee_is_finite(stored_q).OR..NOT.ieee_is_finite(stored_n)) RETURN
    DO attempt=1,4
      IF (strict_graupel_pair(REAL(stored_q,real64),REAL(stored_n,real64), &
                              minimum_ratio,maximum_ratio)) EXIT
      qcheck=REAL(stored_q,real128); ncheck=REAL(stored_n,real128)
      IF (stored_q<=0.0_real32.OR.stored_n<=0.0_real32) RETURN
      IF (qcheck<REAL(minimum_ratio,real128)*ncheck) THEN
        stored_q=NEAREST(stored_q,1.0_real32)
      ELSE IF (qcheck>REAL(maximum_ratio,real128)*ncheck) THEN
        stored_q=NEAREST(stored_q,-1.0_real32)
      ELSE
        RETURN
      END IF
    END DO
    IF (.NOT.strict_graupel_pair(REAL(stored_q,real64),REAL(stored_n,real64), &
                                 minimum_ratio,maximum_ratio)) RETURN
    delta_q=REAL(denominator,real64)*(REAL(stored_q,real64)-reference_q)
    delta_n=REAL(denominator,real64)*(REAL(stored_n,real64)-reference_n)
    IF (.NOT.ALL(ieee_is_finite([delta_q,delta_n]))) RETURN
    valid=.TRUE.
  END SUBROUTINE store_graupel_mixture
end module c15_mixture_adapter
