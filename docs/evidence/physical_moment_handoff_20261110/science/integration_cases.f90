program physical_integration_cases
  use, intrinsic :: iso_fortran_env, only: real32,real64,int64
  use cloud_bal_state
  use cloud_bal_column_physics, only: saturation_adjust_cell, apply_water_phase_transfer, &
    moist_species_enthalpy, SATURATION_LIQUID
  use cloud_bal_microphysics_initialization
  implicit none
  type(cloud_bal_state_type) :: state,out,background
  type(moment_bundle) :: prior
  type(microphysics_completion_policy) :: policy
  real(real64) :: pi,pid(3),lambda(3),t,rv,qc,qi,h0,w0,species(6),delta(6), saved(5)
  real(real32) :: den(1,1,2)
  integer :: status,s

  pi=4.0_real64*atan(1.0_real64)
  pid=[pi*1000.0_real64/6.0_real64,4.0_real64*pi*1000.0_real64,500.0_real64*pi]
  lambda=[1.0e5_real64,2.0e4_real64,1.0e4_real64]
  policy%source='CONTROL KDM6 parameter bounds, denr=1000 kg/m3'
  policy%density_source='manufactured dry density 1 kg/m3'
  policy%number_cap=[5.0e10_real64,1.0e6_real64,5.0e7_real64,2.0e10_real64]
  policy%lower=[pid(1)/(5.e5_real64**3),pid(3)/(1.82e6_real64**3), &
    pid(2)/(3.5e4_real64**3),0.0_real64,100.0_real64]
  policy%upper=[pid(1)/(1.2e4_real64**3),pid(3)/(9.08e3_real64**3), &
    pid(2)/(9.61e2_real64**3),0.0_real64,900.0_real64]
  policy%mass_threshold=[1.e-12_real64,1.e-14_real64,1.e-9_real64,0.0_real64,1.e-9_real64]
  den=1.0_real32
  call initialize_cloud_bal_state(state,1,1,2,0_int64,'integration',status)
  call require(status==STATUS_OK,'state initialized')
  call usable(state%cloud_water); call usable(state%cloud_ice)
  call usable(state%rain); call usable(state%graupel)
  call usable(state%snow); call usable(state%pressure)
  call usable(state%temperature); call usable(state%vapor)
  state%pressure%value=85000.0_real32; state%temperature%value=280.0_real32
  state%vapor%value=0.002_real32
  call allocate_bundle(state%moments); call allocate_bundle(prior)
  prior%valid=.true.; prior%provenance=MOMENT_PRIOR
  prior%value(:,:,:,1)=pid(1)/lambda(1)**3
  prior%value(:,:,:,2)=pid(3)/lambda(2)**3
  prior%value(:,:,:,3)=pid(2)/lambda(3)**3
  prior%value(:,:,:,4)=1.e8_real64
  prior%value(:,:,:,5)=400.0_real64

  ! 1: no observation; retain a fully valid background exactly.
  state%cloud_water%value=1.e-4_real32; state%cloud_ice%value=1.e-4_real32
  state%rain%value=1.e-4_real32; state%graupel%value=1.e-4_real32
  call fill_background()
  background=state
  call complete_initialization_state(state,out,prior,policy,status,den)
  call require(status==STATUS_OK,'background completion')
  call require(all(out%moments%value==background%moments%value) .and. &
    all(out%moments%provenance==MOMENT_BACKGROUND),'no observations preserve valid background moments')
  call require(all(out%cloud_water%value==background%cloud_water%value) .and. &
    all(out%rain%value==background%rain%value),'background mass unchanged')

  ! 2: supersaturated vapor condenses conserving water and enthalpy; then derive NC.
  t=280.0_real64; rv=.02_real64; qc=0.; qi=0.
  species=[rv,qc,qi,0.0_real64,0.0_real64,0.0_real64]
  h0=moist_species_enthalpy(t,species); w0=sum(species)
  call saturation_adjust_cell(85000.0_real64,t,rv,qc,qi,1.0_real64,status,SATURATION_LIQUID)
  species=[rv,qc,qi,0.0_real64,0.0_real64,0.0_real64]
  call require(status==STATUS_OK .and. qc>0.0_real64,'warm cloud condensation')
  call require(abs(sum(species)-w0)<2.e-13_real64 .and. &
    abs(moist_species_enthalpy(t,species)-h0)<2.e-7_real64,'warm cloud water and enthalpy')
  call set_physics(t,species)
  state%moments%valid=.false.
  call complete_initialization_state(state,out,prior,policy,status,den)
  call require(status==STATUS_OK .and. all(out%moments%value(:,:,:,MOMENT_NC)>0), &
    'warm cloud NC prior after saturation')
  call require(all(out%moments%provenance(:,:,:,MOMENT_NC)==MOMENT_PRIOR), 'cloud prior provenance')
  call assert_physics(out,t,species)

  ! 3: rain completion does not alter subsaturated thermodynamics; allowed rain evaporation cools.
  state%cloud_water%value=0.; state%rain%value=1.e-4_real32
  state%temperature%value=280.; state%vapor%value=.002_real32; state%moments%valid=.false.
  call complete_initialization_state(state,out,prior,policy,status,den)
  call require(status==STATUS_OK .and. all(out%moments%value(:,:,:,MOMENT_NR)>0), 'rain prior')
  call require(all(out%vapor%value==state%vapor%value) .and. &
    all(out%temperature%value==state%temperature%value),'rain vapor and temperature unchanged')
  t=280.0_real64; species=[.002_real64,0.0_real64,0.0_real64,1.e-4_real64,0.0_real64,0.0_real64]
  h0=moist_species_enthalpy(t,species); w0=sum(species)
  delta=[1.e-5_real64,0.0_real64,0.0_real64,-1.e-5_real64,0.0_real64,0.0_real64]
  call apply_water_phase_transfer(t,species,delta,status)
  call require(status==STATUS_OK .and. t<280.0_real64 .and. &
    abs(sum(species)-w0)<1.e-14_real64 .and. &
    abs(moist_species_enthalpy(t,species)-h0)<2.e-7_real64,'rain evaporation conserves and cools')
  state=out
  call set_physics(t,species)
  call complete_initialization_state(state,out,prior,policy,status,den)
  call require(status==STATUS_OK,'evaporated rain completion')
  call assert_physics(out,t,species)

  ! 4: positive mass with zero number requires explicit prior; missing prior rolls back.
  state%moments%value=0.; state%moments%valid=.true.; state%moments%provenance=MOMENT_BACKGROUND
  prior%valid(:,:,:,MOMENT_NR)=.false.; out=background
  call complete_initialization_state(state,out,prior,policy,status,den)
  call require(status==STATUS_FAILED .and. all(out%moments%value==background%moments%value), &
    'rain zero number missing prior fails and rolls back')
  prior%valid(:,:,:,MOMENT_NR)=.true.
  call complete_initialization_state(state,out,prior,policy,status,den)
  call require(status==STATUS_OK .and. all(out%moments%value(:,:,:,MOMENT_NR)>0), &
    'rain missing number completed using explicit PSD')

  ! 5: specified graupel melting while mixed liquid and ice remain; derive moments afterward.
  t=274.0_real64
  species=[.004_real64,1.e-4_real64,1.e-4_real64,1.e-4_real64,0.0_real64,1.e-4_real64]
  w0=sum(species); h0=moist_species_enthalpy(t,species)
  delta=[0.0_real64,0.0_real64,0.0_real64,2.e-5_real64,0.0_real64,-2.e-5_real64]
  call apply_water_phase_transfer(t,species,delta,status)
  call require(status==STATUS_OK .and. t<274.0_real64 .and. &
    abs(sum(species)-w0)<1.e-14_real64 .and. &
    abs(moist_species_enthalpy(t,species)-h0)<2.e-7_real64,'mixed phase melt water and enthalpy')
  call set_physics(t,species)
  state%moments%valid=.false.
  call complete_initialization_state(state,out,prior,policy,status,den)
  call require(status==STATUS_OK .and. all(out%moments%valid) .and. &
    all(out%moments%value>0.0_real64),'mixed phase moments complete')
  call assert_physics(out,t,species)
  call require(abs(real(state%graupel%value(1,1,1),real64)/out%moments%value(1,1,1,MOMENT_BG) &
    -400.0_real64)<1.e-8_real64,'graupel density prior')

  ! 6: unknown leaves a completed background; separately supplied clear is a physical transfer.
  state=out; saved=state%moments%value(1,1,1,:)
  call complete_initialization_state(state,out,prior,policy,status,den)
  call require(status==STATUS_OK .and. all(out%moments%value(1,1,1,:)==saved), 'unknown preserves background')
  t=280.0_real64; species=[.005_real64,1.e-4_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64]
  h0=moist_species_enthalpy(t,species); w0=sum(species)
  delta=[1.e-4_real64,-1.e-4_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64]
  call apply_water_phase_transfer(t,species,delta,status)
  call require(status==STATUS_OK .and. abs(sum(species)-w0)<1.e-14_real64 .and. &
    abs(moist_species_enthalpy(t,species)-h0)<2.e-7_real64,'explicit clear transfer conserved')
  call set_physics(t,species)
  call complete_initialization_state(state,out,prior,policy,status,den)
  call require(status==STATUS_OK .and. all(out%moments%value(:,:,:,MOMENT_NC)==0.0_real64) .and. &
    all(out%moments%provenance(:,:,:,MOMENT_NC)==MOMENT_ZERO),'clear cloud has zero NC')
  call assert_physics(out,t,species)
  print '(a)', 'six physical integration cases PASS'
contains
  subroutine require(condition,message)
    logical,intent(in) :: condition
    character(*),intent(in) :: message
    if (.not.condition) then
      print '(2a)', 'FAIL: ',message
      error stop 1
    endif
  end subroutine
  subroutine set_physics(temperature,water)
    real(real64),intent(in) :: temperature,water(6)
    state%temperature%value=real(temperature,real32)
    state%vapor%value=real(water(1),real32); state%cloud_water%value=real(water(2),real32)
    state%cloud_ice%value=real(water(3),real32); state%rain%value=real(water(4),real32)
    state%snow%value=real(water(5),real32); state%graupel%value=real(water(6),real32)
  end subroutine
  subroutine assert_physics(result,temperature,water)
    type(cloud_bal_state_type),intent(in) :: result
    real(real64),intent(in) :: temperature,water(6)
    call require(all(result%temperature%value==real(temperature,real32)) .and. &
      all(result%vapor%value==real(water(1),real32)) .and. &
      all(result%cloud_water%value==real(water(2),real32)) .and. &
      all(result%cloud_ice%value==real(water(3),real32)) .and. &
      all(result%rain%value==real(water(4),real32)) .and. &
      all(result%snow%value==real(water(5),real32)) .and. &
      all(result%graupel%value==real(water(6),real32)),'completion preserves physical result')
  end subroutine
  subroutine usable(field)
    type(field3d),intent(inout) :: field
    field%value=0.; field%valid=.true.; field%source=SOURCE_BACKGROUND_MODEL; field%quality=0
  end subroutine
  subroutine allocate_bundle(bundle)
    type(moment_bundle),intent(inout) :: bundle
    allocate(bundle%value(1,1,2,5),bundle%valid(1,1,2,5),bundle%provenance(1,1,2,5))
    bundle%value=0.; bundle%valid=.false.; bundle%provenance=0
  end subroutine
  subroutine fill_background()
    do s=1,5
      state%moments%value(:,:,:,s)=0.
      if (s<=3) then
        select case(s)
        case(1)
          state%moments%value(:,:,:,s)=real(state%cloud_water%value,real64)/prior%value(:,:,:,s)
        case(2)
          state%moments%value(:,:,:,s)=real(state%cloud_ice%value,real64)/prior%value(:,:,:,s)
        case(3)
          state%moments%value(:,:,:,s)=real(state%rain%value,real64)/prior%value(:,:,:,s)
        end select
      else if (s==MOMENT_NN) then
        state%moments%value(:,:,:,s)=prior%value(:,:,:,s)
      else
        state%moments%value(:,:,:,s)=real(state%graupel%value,real64)/prior%value(:,:,:,s)
      endif
    enddo
    state%moments%valid=.true.; state%moments%provenance=MOMENT_BACKGROUND
  end subroutine
end program
