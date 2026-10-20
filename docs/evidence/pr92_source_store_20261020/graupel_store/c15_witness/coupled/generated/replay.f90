program replay_c15_mixture_witness
  use iso_fortran_env, only: int32,int64,real32,real64
  use witness_data
  use c15_mixture_adapter
  implicit none
  real(real64) :: weights_local(7),minimum_ratio,maximum_ratio,reference_q,reference_b,delta_q,delta_b
  real(real64) :: candidate_q,candidate_b
  real(real32) :: qterms(7),bterms(7),denominator,stored_q,stored_b
  integer(int32) :: terms_local(14),inputs32(8)
  integer(int64) :: values_local(11),words64(6),candidate_q_bits,candidate_b_bits
  integer :: row,j,adjust
  logical :: valid,candidate_strict,stored_strict
  do row=1,size(coords,2)
    terms_local=terms(:,row); inputs32=values32(:,row); values_local=values64(:,row)
    do j=1,7
      weights_local(j)=transfer(weights(j,row),0.0_real64)
      qterms(j)=transfer(terms_local(j),qterms(j)); bterms(j)=transfer(terms_local(7+j),bterms(j))
    end do
    candidate_q=transfer(values_local(1),candidate_q); candidate_b=transfer(values_local(2),candidate_b)
    reference_q=candidate_q; reference_b=candidate_b
    delta_q=0.0_real64; delta_b=0.0_real64
    minimum_ratio=transfer(values_local(9),minimum_ratio); maximum_ratio=transfer(values_local(10),maximum_ratio)
    denominator=transfer(inputs32(5),denominator)
    candidate_q_bits=values_local(1); candidate_b_bits=values_local(2)
    candidate_strict=strict_graupel_pair(candidate_q,candidate_b,minimum_ratio,maximum_ratio)
    call store_graupel_mixture(weights_local,qterms,bterms,denominator,minimum_ratio,maximum_ratio, &
      reference_q,reference_b,stored_q,stored_b,delta_q,delta_b,valid)
    stored_strict=.false.
    if (valid) stored_strict=strict_graupel_pair(real(stored_q,real64),real(stored_b,real64), &
      minimum_ratio,maximum_ratio)
    words64=[transfer(delta_q,words64(1)),transfer(delta_b,words64(2)), &
      transfer(candidate_q_bits,words64(3)),transfer(candidate_b_bits,words64(4)), &
      values_local(3),values_local(4)]
    write(*,'(A,1X,I0,3(1X,L1),2(1X,Z8.8),6(1X,Z16.16))') 'MIXTURE_REPLAY',row,valid, &
      candidate_strict,stored_strict,transfer(stored_q,0_int32),transfer(stored_b,0_int32),words64
  end do
end program replay_c15_mixture_witness
