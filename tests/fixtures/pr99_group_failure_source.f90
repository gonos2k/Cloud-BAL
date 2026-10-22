module fixture
  subroutine joint_qnb_update(q_base,n_base,q_stage,n_stage,q_source,n_source,q_transport,n_transport, &
                              carrier_old,carrier_new,dry_density,dt,min_particle_mass,max_particle_mass,theta, &
                              rejected_q,rejected_n,feasible,bulk_volume_quantum_storage,bulk_volume_absences, &
                              bulk_volume_delta,diagnostic_stage,diagnostic_candidate,diagnostic_stored, &
                              diagnostic_adjustment, diagnostic_scale, diagnostic_cells)
    integer, intent(in), optional :: diagnostic_cells(:)
    logical :: use_bulk_volume_absence
    integer, allocatable :: local_inactive_q_quantum_adjustments(:)
    real(real64) :: failure_q64, failure_n64
    feasible = .false.
    if (present(diagnostic_stage)) diagnostic_stage = 0
    allocate(q_candidate(ncells,npairs), n_candidate(ncells,npairs))
    if (use_joint_storage) then
      call form_candidate(1.0_real64)
      if (.not. candidate_is_feasible()) return
    end if
            if (.not. storage_valid) then
              q_candidate(i,p) = -1.0_real32
    logical function candidate_is_feasible()
      candidate_is_feasible = .false.
          if (.not.pair_valid) return
            if (.not. volume_number_stored_contract_valid(q_candidate(i,p),n_candidate(i,p), &
                    dry_density(i),cell_volume_bounds)) return
      candidate_is_feasible = .true.
    end function candidate_is_feasible
  end subroutine joint_qnb_update
  SUBROUTINE evaluate_joint_candidate()
    INTEGER :: pr91_stage(6,4),pr91_adjustment(6,4),pr91_cells(6)
    CALL joint_qnb_update(qb,nb,qc,nc,qs,ns,qa,na,oldcarrier,newcarrier,drydensity, &
                         diagnostic_scale=pr91_scale, diagnostic_cells=pr91_cells)
    IF (.NOT.feasible) CALL write_pr91_actual_store_failures( &
    IF (.NOT.feasible) CALL try_graupel_mixture_trial()
  END SUBROUTINE evaluate_joint_candidate
  SUBROUTINE try_graupel_mixture_trial()
end module fixture
