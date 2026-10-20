program pr91_source_chain_probe
  use iso_fortran_env, only: real32, real64, int32, int64
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  real(real32) :: qbase32, nbase32, rho, carrier_old32, carrier_new32, dt32
  real(real32) :: q_store, n_store, q_again, n_again
  real(real32) :: q_virtual_store, n_virtual_store, q_virtual_vol, n_virtual_vol
  real(real32) :: q_candidate_store, n_candidate_store
  real(real64) :: qbase, nbase, source_q, source_n, transport_q, transport_n
  real(real64) :: q_virtual, n_virtual, q_candidate, n_candidate, scale
  real(real64) :: min_mass, max_mass, volume_bounds(2), ratio
  real(real64) :: number_volume, lower_number, upper_number
  real(real32) :: number_volume32
  integer :: stage, adjustment, virtual_stage_no_vol, virtual_stage_vol
  integer :: candidate_stage
  logical :: valid, valid_endpoint_vol, valid_virtual_no_vol, valid_virtual_vol
  logical :: valid_candidate

  qbase32 = transfer(int(z'36F6D87B',int32),0.0_real32)
  nbase32 = transfer(int(z'4ED15C91',int32),0.0_real32)
  rho = transfer(int(z'3F8BA750',int32),0.0_real32)
  carrier_old32 = transfer(int(z'47A5D67A',int32),0.0_real32)
  carrier_new32 = transfer(int(z'47A5D3D6',int32),0.0_real32)
  dt32 = transfer(int(z'41A00000',int32),0.0_real32)
  qbase = real(qbase32,real64); nbase = real(nbase32,real64)
  source_q = transfer(int(z'BF380B7C26C0B810',int64),0.0_real64)
  source_n = transfer(int(z'C23464C2D285C708',int64),0.0_real64)
  transport_q = transfer(int(z'BF57EC72025010F6',int64),0.0_real64)
  transport_n = transfer(int(z'C2544A6F664C4821',int64),0.0_real64)
  min_mass = transfer(int(z'3CF2DD58BFD7689A',int64),0.0_real64)
  max_mass = transfer(int(z'3DF4D2954D1355A3',int64),0.0_real64)
  volume_bounds = [transfer(int(z'41EAD3CB1A2DDE23',int64),0.0_real64), &
                   transfer(int(z'42ED9C99864E99CF',int64),0.0_real64)]
  scale = 1.0_real64

  call joint_moment_store(qbase,nbase,rho,min_mass,max_mass,.true., &
      q_store,n_store,adjustment,valid,allow_normal_q_adjustment=.true., &
      strict_mass_ratio=.true.,failure_stage=stage)
  if (.not.valid .or. stage /= 0 .or. adjustment /= 0 .or. &
      transfer(q_store,0_int32) /= int(z'36F6D87B',int32) .or. &
      transfer(n_store,0_int32) /= int(z'4ED15C91',int32)) error stop 1
  write(*,'(a,1x,l1,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') &
      'SOURCE_ENDPOINT_NO_VOLUME',valid,stage,adjustment, &
      transfer(q_store,0_int32),transfer(n_store,0_int32)
  call joint_moment_store(qbase,nbase,rho,min_mass,max_mass,.true., &
      q_again,n_again,adjustment,valid_endpoint_vol,allow_normal_q_adjustment=.true., &
      volume_number_bounds=volume_bounds,strict_mass_ratio=.true.,failure_stage=stage)
  if (.not.valid_endpoint_vol .or. stage /= 0 .or. adjustment /= 0 .or. &
      transfer(q_again,0_int32) /= int(z'36F6D87B',int32) .or. &
      transfer(n_again,0_int32) /= int(z'4ED15C91',int32)) error stop 2
  write(*,'(a,1x,l1,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') &
      'SOURCE_ENDPOINT_WITH_VOLUME',valid_endpoint_vol,stage,adjustment, &
      transfer(q_again,0_int32),transfer(n_again,0_int32)

  ! Existing host ordering: source contribution is applied against old carrier
  ! before air Q/N is formed; transport is not included in this donor state.
  q_virtual = (real(carrier_old32,real64)*real(qbase32,real64) + &
      real(dt32,real64)*source_q) / real(carrier_old32,real64)
  n_virtual = (real(carrier_old32,real64)*real(nbase32,real64) + &
      real(dt32,real64)*source_n) / real(carrier_old32,real64)
  if (transfer(q_virtual,0_int64) /= int(z'3EDE7E442C58A592',int64) .or. &
      transfer(n_virtual,0_int64) /= int(z'41D9DCDE33F1AC42',int64)) error stop 3
  ratio = q_virtual/n_virtual
  number_volume = n_virtual*real(rho,real64)
  lower_number = volume_bounds(1)*q_virtual
  upper_number = volume_bounds(2)*q_virtual
  number_volume32 = real(number_volume,real32)
  write(*,'(a,1x,z16.16,1x,z16.16,1x,es26.17,1x,es26.17,1x,es26.17)') &
      'VIRTUAL_DONOR',transfer(q_virtual,0_int64),transfer(n_virtual,0_int64), &
      ratio,number_volume,upper_number-number_volume
  write(*,'(a,1x,es26.17,1x,es26.17)') 'VIRTUAL_VOLUME_MARGINS', &
      number_volume-lower_number, upper_number-number_volume
  write(*,'(a,1x,es26.17)') 'VIRTUAL_STORED_PRODUCT',real(number_volume32,real64)
  call joint_moment_store(q_virtual,n_virtual,rho,min_mass,max_mass,.true., &
      q_virtual_store,n_virtual_store,adjustment,valid_virtual_no_vol, &
      allow_normal_q_adjustment=.true.,strict_mass_ratio=.true., &
      failure_stage=virtual_stage_no_vol)
  if (valid_virtual_no_vol .or. virtual_stage_no_vol /= 2) error stop 4
  write(*,'(a,1x,l1,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') &
      'VIRTUAL_STORE_NO_VOLUME',valid_virtual_no_vol,virtual_stage_no_vol,adjustment, &
      transfer(q_virtual_store,0_int32),transfer(n_virtual_store,0_int32)
  call joint_moment_store(q_virtual,n_virtual,rho,min_mass,max_mass,.true., &
      q_virtual_vol,n_virtual_vol,adjustment,valid_virtual_vol, &
      allow_normal_q_adjustment=.true.,volume_number_bounds=volume_bounds, &
      strict_mass_ratio=.true.,failure_stage=virtual_stage_vol)
  if (valid_virtual_vol .or. virtual_stage_vol /= 2) error stop 5
  write(*,'(a,1x,l1,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') &
      'VIRTUAL_STORE_WITH_VOLUME',valid_virtual_vol,virtual_stage_vol,adjustment, &
      transfer(q_virtual_vol,0_int32),transfer(n_virtual_vol,0_int32)

  q_candidate = (real(carrier_old32,real64)*real(qbase32,real64) + &
      real(dt32,real64)*(source_q + scale*transport_q)) / real(carrier_new32,real64)
  n_candidate = (real(carrier_old32,real64)*real(nbase32,real64) + &
      real(dt32,real64)*(source_n + scale*transport_n)) / real(carrier_new32,real64)
  if (transfer(q_candidate,0_int64) /= int(z'3EDD0D6CF179BEF8',int64) .or. &
      transfer(n_candidate,0_int64) /= int(z'41D8A40957EA0410',int64)) error stop 91
  call joint_moment_store(q_candidate,n_candidate,rho,min_mass,max_mass,.true., &
      q_candidate_store,n_candidate_store,adjustment,valid_candidate, &
      allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
      volume_number_bounds=volume_bounds,strict_mass_ratio=.false., &
      failure_stage=candidate_stage)
  if (valid_candidate .or. candidate_stage /= 3) error stop 6
  write(*,'(a,1x,z16.16,1x,z16.16,1x,l1,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') &
      'FULL_CANDIDATE',transfer(q_candidate,0_int64),transfer(n_candidate,0_int64), &
      valid_candidate,candidate_stage,adjustment,transfer(q_candidate_store,0_int32), &
      transfer(n_candidate_store,0_int32)
end program pr91_source_chain_probe
