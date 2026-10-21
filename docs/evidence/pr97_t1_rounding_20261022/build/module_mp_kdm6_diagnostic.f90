
   module module_mp_kdm6


   use module_mp_radar
   use pr97_liquid_observer, only: liquid_begin,liquid_record,liquid_end
   use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
   use, intrinsic :: iso_c_binding, only : c_int
   use module_model_constants, only : RE_QC_BG, RE_QI_BG, RE_QS_BG
   interface
      function pr75_read_fp_state(thread_id) bind(C, name='pr75_read_fp_state') result(mxcsr)
        import :: c_int
        integer(c_int) :: thread_id
        integer(c_int) :: mxcsr
      end function pr75_read_fp_state
   function pr76_apply_gradual(after, thread_id) bind(C, name='pr76_apply_gradual') result(mxcsr)
     import :: c_int
     integer(c_int) :: after, thread_id
     integer(c_int) :: mxcsr
   end function pr76_apply_gradual
   end interface
   integer, parameter, private :: PROGB_ABSENT = 0
   integer, parameter, private :: PROGB_TRANSIENT = 1
   integer, parameter, private :: PROGB_PSD_ACTIVE = 2
   integer, parameter, private :: PROGB_UNSUPPORTED = 3
   integer, parameter, private :: PR85_SED_ICE = 1
   integer, parameter, private :: PR85_SED_GRAUPEL = 2
! Native ice PSD reconstruction is skipped below the 1.e-14 REAL32 gate.
   real, parameter, private :: PR85_ICE_NATIVE_INACTIVE_MAX = NEAREST(1.e-14,-1.0)
   integer, parameter, private :: SPECIES_ABSENT = 0
   integer, parameter, private :: SPECIES_MASS_ONLY = 1
   integer, parameter, private :: SPECIES_NUMBER_ONLY = 2
   integer, parameter, private :: SPECIES_ACTIVE = 3
   integer, parameter, private :: SPECIES_INVALID = 4










































   real, parameter, private :: dtcldcr = 120.

   real, parameter, private :: n0s     = 2.e6

   real, parameter, private :: n0smax  =  1.e11
   real, parameter, private :: dens    = 100.0
   real, parameter, private :: deni    = 500.0
   real, parameter, private :: alpha   = .12
   real, parameter, private :: avtr    = 841.9
   real, parameter, private :: bvtr    = 0.8
   real, parameter, private :: fvtr    = 0. 
   real, parameter, private :: mur     = 1.
   real, parameter, private :: avts    = 11.72
   real, parameter, private :: bvts    = 0.41
   real, parameter, private :: mus = 0.
   real, parameter, private :: mug = 0.
   real, parameter, private :: dms = 3.
   real, parameter, private :: dmg = 3.

   real, parameter, private :: avti    = 2710. 
   real, parameter, private :: bvti    = 1.0 
   real, parameter, private :: lamdacmax = 5.e5
   real, parameter, private :: lamdacmin = 1.2e4  
   real, parameter, private :: lamdarmax = 3.5e4  
   real, parameter, private :: lamdarmin = 9.61e2 
   real, parameter, private :: lamdasmax = 1.8e5  
   real, parameter, private :: lamdaimax = 1.82e6 
   real, parameter, private :: lamdaimin = 9.08e3   
   real, parameter, private :: r0      = .8e-5


   real, parameter, private :: peaut   = .40
   real, parameter, private :: xncr    = 3.e8
   real, parameter, private :: xncr0   = 5.e7
   real, parameter, private :: xncr1   = 5.e8
   real, parameter, private :: xmyu    = 1.718e-5
   real, parameter, private :: dicon   = 11.9
   real, parameter, private :: dimax   = 500.e-6
   real, parameter, private :: pfrz1   = 100.
   real, parameter, private :: pfrz2   = 0.66
   real, parameter, private :: qcrmin  = 1.e-9
   real, parameter, private :: pr85_brs_min = 1.e-15


   real, parameter, private :: nrmin   = 1.e-2
   real, parameter, private :: nrmax   = 5.e7
   real, parameter, private :: ncmax   = 5.e10 

   real, parameter, private :: eacrc   = 1.0
   real, parameter, private :: eacic   = 1.0
   real, parameter, private :: eacsc   = 1.0
   real, parameter, private :: eacgc   = 1.0
   real, parameter, private :: eacri   = 1.0
   real, parameter, private :: eacir   = 1.0
   real, parameter, private :: eacsr   = 1.0
   real, parameter, private :: eacgr   = 1.0
   real, parameter, private :: eacrs   = 1.0
   real, parameter, private :: qs0     = 6.e-4
   real, parameter, private :: satmax  = 1.0048
   real, parameter, private :: actk    = 0.6
   real, parameter, private :: actr    = 1.5
   real, parameter, private :: ncrk1   = 3.03e3
   real, parameter, private :: ncrk2   = 2.59e15
   real, parameter, private :: eccbrk   = 1. 
   real, parameter, private :: di100   = 1.e-4
   real, parameter, private :: di150   = 1.5e-4
   real, parameter, private :: di50   = 0.5e-4
   real, parameter, private :: di600   = 6.e-4
   real, parameter, private :: di200   = 2.e-4
   real, parameter, private :: di2000  = 2000.e-6
   real, parameter, private :: di60    = 60.e-6  
   real, parameter, private :: di82    = 82.e-6
   real, parameter, private :: di15    = 15.e-6
   real, parameter, private :: Rispl    = 5.e-6 
   real, parameter, private :: Rinud    = 10.e-6 
   real, parameter, private :: di125    = 125.e-6 
   real, parameter, private :: muc = 2.
   real, parameter, private :: dmc = 3.
   real, parameter, private :: dmr = 3.
   real, parameter, private :: dmi = 3.0
   real, parameter, private :: mui = 0.  
   real, parameter, private :: evq = 3.29
   real, parameter, private :: fvq = 0.16 

   double precision, save ::  rslopermmax,rslopesmmax,rslopegmmax,rslopecmmax,rslopeimmax
   real,save  ::              rslopec2max,rslopec3max,rslopecdmax, &
                              rsloperdmax,rslopesdmax,rslopegdmax, &
                              rsloperbmax,rslopesbmax,             &
                              rsloper2max,rslopes2max,rslopeg2max, &
                              rsloper3max,rslopes3max,rslopeg3max, &
                              rslopei3max,rslopeidmax,rslopeibmax,rslopei2max
   real, save ::                                                               &
             mur1,g1pmr,mur2,g2pmr,mur3,g3pmr,mur4,g4pmr,mur7,g7pmr,           &
             muc1,g1pmc,muc3,g3pmc,muc4,g4pmc,muc6,g6pmc,muc9,g9pmc,           &
             mus1,g1pms,mus2,g2pms,mus3,g3pms,                                 &
             mug1,g1pmg,mug2,g2pmg,mug3,g3pmg,                                 &
             cmc, cmr,cmi,axni, bxni,                                          &
             cms,                                                              &
             qc0,qc1,qck1,pidnc,bvtr1,bvtr2,bvtr3,bvtr4,bvtr5,                 &
             bvtr6,bvtr7, bvtr2o5,bvtr3o5, brmur1,                             &
             drmur1, drmur2, drmur3,drbrmur1, drbrmur3,                        &
             dsmus1, dsmus2, dsmus3,dsbsmus1,                        &
             dgmug1,g1pdgmg,                                                   &
             g1pbr,g2pbr,g3pbr,g4pbr,g5pbr,g6pbr,g7pbr,g1pbrmr,                &
             g1pdrmr,g2pdrmr,g3pdrmr,g3pbrmr, g1pdrbrmr, g3pdrbrmr,g1p2drmr,   &
             g1pdsms,g2pdsms,g3pdsms,g1pdsbsms,g1p2dcomuc1,g1pdcomuc1,&
             g5pbro2,g7pbro2,pi,                                               &
             pvtr,pvtrn,eacrr,pidnr,                                           &
             precr1,precr2,xmmax,roqimax,bvts1,bvts2,                          &
             bvts3,bvts4,g1pbs,g3pbs,g4pbs,g5pbso2,                            &
             pvts,precs1,precs2,pidn0s,xlv1,pacrc,                             &
             pacrg,precg1,                          &
             n0g,deng,lamdagmax,                                     &
             rslopecmax,rslopermax,rslopesmax,rslopegmax,rslopeimax,           &
             g1pmi,mui1,xam_c,xbm_c,xmu_c,xam_i,      &
             xbm_i, xmu_i
  real, save :: pvtin, g1pbimi, bimui1, g1pdimi,g2pdimi,g3pdimi,                     &
                dimui1, dimui2, dimui3, pidni,pvti,g1pdibimi,                        &
                dibimui1,mui2,mui3,mui4,mui5,bvti3,g3pbi,g2pmi,g3pmi,g4pmi,g5pmi

  real   :: Nid 
  real   :: Nic 
  real   :: ratios 
  real   :: ele1, ele2
  real,save   :: Minud  
  real,save   :: Miaut  
  real,save   :: Mispl  
  real :: fmul 
  real :: qi0 
  real, parameter, private :: Rcn = 0.1e-6 
  real, parameter, private :: F1S= 0.66 
  real, parameter, private :: F2S =0.44 

    private :: pr84_ice_entry_ceiling
    private :: kdm6_progb_density_pair_valid
    private :: kdm6_rain_ng_pair_valid
    private :: kdm6_refresh_graupel_intercept

    contains

    pure logical function kdm6_progb_density_pair_valid(q,b,rho_min,rho_max)
      real, intent(in) :: q,b,rho_min,rho_max
      real(kind=8) :: density

      kdm6_progb_density_pair_valid=.false.
      if (.not.all(ieee_is_finite([q,b,rho_min,rho_max]))) return
      if (rho_min.le.0.0 .or. rho_max.lt.rho_min) return
      if (q.eq.0.0 .and. b.eq.0.0) then
        kdm6_progb_density_pair_valid=.true.
        return
      endif
      if (q.le.0.0 .or. b.le.0.0) return
      density=real(q,8)/real(b,8)
      kdm6_progb_density_pair_valid=ieee_is_finite(density) .and. &
           density.ge.real(rho_min,8) .and. density.le.real(rho_max,8)
    end function kdm6_progb_density_pair_valid

    pure subroutine kdm6_refresh_graupel_intercept(status,n0g,g1pmg,slope_mu,n0go,valid)
      integer, intent(in) :: status
      real, intent(in) :: n0g,g1pmg
      real(kind=8), intent(in) :: slope_mu
      real, intent(out) :: n0go
      logical, intent(out) :: valid
      real(kind=8) :: ratio64,intercept64
      real :: ratio32

      n0go=0.0
      valid=.false.
      if (status.eq.PROGB_ABSENT) then
        valid=.true.
        return
      endif
      if (status.ne.PROGB_PSD_ACTIVE) return
      if (.not.ieee_is_finite(n0g) .or. .not.ieee_is_finite(g1pmg) .or. &
          .not.ieee_is_finite(slope_mu)) return
      if (n0g.le.0.0 .or. g1pmg.le.0.0 .or. slope_mu.le.0.0d0) return
      ratio64=real(n0g,8)/real(g1pmg,8)
      if (.not.ieee_is_finite(ratio64) .or. ratio64.gt.real(huge(0.0),8)) return
      ratio32=real(ratio64)
      if (.not.ieee_is_finite(ratio32) .or. ratio32.le.0.0) return
      if (slope_mu.le.real(ratio32,8)/real(huge(0.0),8)) return
      intercept64=real(ratio32,8)/slope_mu
      if (.not.ieee_is_finite(intercept64) .or. intercept64.le.0.0d0 .or. &
          intercept64.gt.real(huge(0.0),8)) return
      n0go=real(intercept64)
      valid=ieee_is_finite(n0go) .and. n0go.gt.0.0
      if (.not.valid) n0go=0.0
    end subroutine kdm6_refresh_graupel_intercept

! PR84_KDM6_ICE_ENTRY_CEILING_BEGIN
    pure subroutine pr84_ice_entry_ceiling(qice, dry_density, lambda_min, shape_exponent, &
                                           pidni_value, upper_limit, valid, public_minimum_out)
      use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
      real, intent(in) :: qice, dry_density, lambda_min, shape_exponent, pidni_value
      real, intent(out) :: upper_limit
      logical, intent(out) :: valid
      real, optional, intent(out) :: public_minimum_out
      real :: minimum_internal, minimum_public, roundtrip_internal, previous_public
      double precision :: minimum_internal_exact, minimum_public_exact
      integer :: step

      upper_limit = 0.0
      valid = .false.
      if (present(public_minimum_out)) public_minimum_out = 0.0
      if (.not. all(ieee_is_finite([qice, dry_density, lambda_min, shape_exponent, pidni_value]))) return
      if (qice < 0.0 .or. dry_density <= 0.0 .or. lambda_min <= 0.0 .or. &
          shape_exponent <= 0.0 .or. pidni_value <= 0.0) return

      minimum_public_exact = dble(qice) * dble(lambda_min)**dble(shape_exponent) / dble(pidni_value)
      minimum_internal_exact = dble(dry_density) * minimum_public_exact
      if (.not. ieee_is_finite(minimum_public_exact) .or. &
          .not. ieee_is_finite(minimum_internal_exact) .or. &
          minimum_public_exact < 0.0d0 .or. minimum_internal_exact < 0.0d0 .or. &
          minimum_public_exact > dble(huge(upper_limit)) .or. &
          minimum_internal_exact > dble(huge(upper_limit))) return

      minimum_internal = real(minimum_internal_exact)
      if (dble(minimum_internal) < minimum_internal_exact) then
        if (minimum_internal >= huge(minimum_internal)) return
        minimum_internal = nearest(minimum_internal, 1.0)
      endif
      if (.not. ieee_is_finite(minimum_internal)) return

      minimum_public = real(minimum_public_exact)
      if (dble(minimum_public) < minimum_public_exact) then
        if (minimum_public >= huge(minimum_public)) return
        minimum_public = nearest(minimum_public, 1.0)
      endif
      if (.not. ieee_is_finite(minimum_public)) return

! Find the smallest stored REAL32 public N that meets both source PSD bounds.
      do step = 1, 8
        roundtrip_internal = minimum_public * dry_density
        if (.not. ieee_is_finite(roundtrip_internal)) return
        if (roundtrip_internal >= minimum_internal) exit
        if (minimum_public >= huge(minimum_public)) return
        previous_public = nearest(minimum_public, 1.0)
        if (previous_public <= minimum_public .or. .not. ieee_is_finite(previous_public)) return
        minimum_public = previous_public
      enddo
      if (step > 8) return
      roundtrip_internal = minimum_public * dry_density
      if (.not. ieee_is_finite(roundtrip_internal) .or. roundtrip_internal < minimum_internal) return
      do step = 1, 8
        if (minimum_public <= 0.0) exit
        previous_public = nearest(minimum_public, -1.0)
        if (previous_public < 0.0 .or. dble(previous_public) < minimum_public_exact) exit
        if (.not. ieee_is_finite(previous_public)) return
        if (previous_public * dry_density < minimum_internal) exit
        minimum_public = previous_public
      enddo
      roundtrip_internal = minimum_public * dry_density
      if (.not. ieee_is_finite(roundtrip_internal) .or. &
          dble(minimum_public) < minimum_public_exact .or. roundtrip_internal < minimum_internal) return

      if (present(public_minimum_out)) public_minimum_out = minimum_public
      upper_limit = max(1.0e6, roundtrip_internal)
      valid = ieee_is_finite(upper_limit)
    end subroutine pr84_ice_entry_ceiling
! PR84_KDM6_ICE_ENTRY_CEILING_END

    pure integer function classify_species_state(mass, number) result(state)
      real, intent(in) :: mass, number
      if (.not.ieee_is_finite(mass) .or. .not.ieee_is_finite(number)) then
        state = SPECIES_INVALID
      elseif (mass < 0.0 .or. number < 0.0) then
        state = SPECIES_INVALID
      elseif (mass == 0.0 .and. number == 0.0) then
        state = SPECIES_ABSENT
      elseif (mass > 0.0 .and. number == 0.0) then
        state = SPECIES_MASS_ONLY
      elseif (mass == 0.0 .and. number > 0.0) then
        state = SPECIES_NUMBER_ONLY
      else
        state = SPECIES_ACTIVE
      endif
    end function classify_species_state

    subroutine validate_kdm6_species_states(qci, qrs, nrs, nci, brs)
      real, intent(in) :: qci(:,:,:), qrs(:,:,:), nrs(:,:,:), nci(:,:,:), brs(:,:)
      integer :: i, k, state
      do k=1,size(qrs,2)
        do i=1,size(qrs,1)
          state=classify_species_state(qrs(i,k,1),nrs(i,k,1))
          call require_paired_state(state)
          state=classify_species_state(qci(i,k,1),nci(i,k,1))
          call require_paired_state(state)
          state=classify_species_state(qci(i,k,2),nci(i,k,2))
          call require_paired_state(state)
          state=classify_species_state(qrs(i,k,3),brs(i,k))
          call require_paired_state(state)
        enddo
      enddo
    end subroutine validate_kdm6_species_states

    subroutine validate_kdm6_slope_states(qci_current, qrs_current, nrs_current, &
                                            nci_current, brs, qrs, nrs, qci, nci)
      real, intent(in) :: qci_current(:,:,:), qrs_current(:,:,:), nrs_current(:,:,:)
      real, intent(in) :: nci_current(:,:,:), brs(:,:), qrs(:,:,:), nrs(:,:), qci(:,:), nci(:,:)
      integer :: i, k
      do k=1,size(qrs,2)
        do i=1,size(qrs,1)
          call require_paired_state(classify_species_state(qrs_current(i,k,1),nrs_current(i,k,1)))
          call require_paired_state(classify_species_state(qci_current(i,k,1),nci_current(i,k,1)))
          call require_paired_state(classify_species_state(qci_current(i,k,2),nci_current(i,k,2)))
          call require_paired_state(classify_species_state(qrs_current(i,k,3),brs(i,k)))
          call require_paired_state(classify_species_state(qrs(i,k,1),nrs(i,k)))
          call require_paired_state(classify_species_state(qci(i,k),nci(i,k)))
          call require_paired_state(classify_species_state(qrs(i,k,3),brs(i,k)))
        enddo
      enddo
    end subroutine validate_kdm6_slope_states

    subroutine validate_local_species_states(qr, nr, qc, nc, qi, ni, qg, bg)
      real, intent(in) :: qr, nr, qc, nc, qi, ni, qg, bg
      call require_paired_state(classify_species_state(qr,nr))
      call require_paired_state(classify_species_state(qc,nc))
      call require_paired_state(classify_species_state(qi,ni))
      call require_paired_state(classify_species_state(qg,bg))
    end subroutine validate_local_species_states

    subroutine require_paired_state(state)
      integer, intent(in) :: state
      select case(state)
      case(SPECIES_ABSENT,SPECIES_ACTIVE)
        return
      case(SPECIES_MASS_ONLY)
        error stop 'KDM6 unsupported positive mass without number/volume state'
      case(SPECIES_NUMBER_ONLY)
        error stop 'KDM6 orphan number/volume state without positive mass'
      case default
        error stop 'KDM6 invalid nonfinite or negative species state'
      end select
    end subroutine require_paired_state
! PR71_STEP_COUNT_CONTRACT_BEGIN
    pure subroutine checked_substep_count(rate, timestep, count, valid)
      double precision, intent(in) :: rate
      real, intent(in) :: timestep
      integer, intent(out) :: count
      logical, intent(out) :: valid
      double precision :: dt64, scaled_argument

      count = 0
      valid = .false.
      if (.not. ieee_is_finite(rate)) return
      if (.not. ieee_is_finite(timestep)) return
      if (timestep <= 0.0) return
      dt64 = real(timestep, kind=kind(rate))
      if (dt64 > 1.0d0) then
        if (abs(rate) > huge(rate) / dt64) return
      end if
      scaled_argument = rate * dt64 + 0.5d0
      if (.not. (scaled_argument < real(huge(count), kind=kind(rate)) + 0.5d0)) return
      if (.not. (scaled_argument > real(-huge(count) - 1, kind=kind(rate)) - 0.5d0)) return

! Keep the original expression and minimum-one rule on valid inputs.
      count = max(nint(rate * timestep + .5), 1)
      valid = .true.
    end subroutine checked_substep_count
! PR71_STEP_COUNT_CONTRACT_END

    pure elemental subroutine moist_to_dry_density(total_density, vapor_mixing_ratio, dry_density, valid)
      real, intent(in) :: total_density, vapor_mixing_ratio
      real, intent(out) :: dry_density
      logical, intent(out) :: valid
      dry_density = 0.0
      valid = .false.
      if (.not. ieee_is_finite(total_density) .or. .not. ieee_is_finite(vapor_mixing_ratio)) return
      if (total_density <= 0.0 .or. vapor_mixing_ratio < 0.0) return
      dry_density = total_density / (1.0 + vapor_mixing_ratio)
      valid = ieee_is_finite(dry_density) .and. dry_density > 0.0
    end subroutine moist_to_dry_density

    pure elemental subroutine dry_to_gas_density(dry_density, vapor_mixing_ratio, &
                                                  gas_density, valid)
      real, intent(in) :: dry_density, vapor_mixing_ratio
      real, intent(out) :: gas_density
      logical, intent(out) :: valid
      double precision :: gas_density64

      gas_density = 0.0
      valid = .false.
      if (.not. ieee_is_finite(dry_density) .or. .not. ieee_is_finite(vapor_mixing_ratio)) return
      if (dry_density <= 0.0 .or. vapor_mixing_ratio < 0.0) return
      gas_density64 = real(dry_density,kind=kind(gas_density64)) * &
                      (1.0d0 + real(vapor_mixing_ratio,kind=kind(gas_density64)))
      if (.not. ieee_is_finite(gas_density64)) return
      if (gas_density64 <= 0.0d0 .or. &
          gas_density64 > real(huge(gas_density),kind=kind(gas_density64))) return
      gas_density = real(gas_density64)
      valid = ieee_is_finite(gas_density) .and. gas_density > 0.0
    end subroutine dry_to_gas_density

    pure elemental subroutine specific_number_to_volume(number_per_kg, dry_density, number_per_m3, valid)
      real, intent(in) :: number_per_kg, dry_density
      real, intent(out) :: number_per_m3
      logical, intent(out) :: valid
      number_per_m3 = 0.0
      valid = .false.
      if (.not. ieee_is_finite(number_per_kg) .or. .not. ieee_is_finite(dry_density)) return
      if (number_per_kg < 0.0 .or. dry_density <= 0.0) return
      if (dry_density > 1.0) then
        if (number_per_kg > huge(number_per_kg) / dry_density) return
      end if
      number_per_m3 = number_per_kg * dry_density
      valid = ieee_is_finite(number_per_m3)
      if (number_per_kg > 0.0 .and. number_per_m3 == 0.0) valid = .false.
    end subroutine specific_number_to_volume

    pure elemental subroutine volume_number_to_specific(number_per_m3, dry_density, number_per_kg, valid)
      real, intent(in) :: number_per_m3, dry_density
      real, intent(out) :: number_per_kg
      logical, intent(out) :: valid
      number_per_kg = 0.0
      valid = .false.
      if (.not. ieee_is_finite(number_per_m3) .or. .not. ieee_is_finite(dry_density)) return
      if (number_per_m3 < 0.0 .or. dry_density <= 0.0) return
      if (dry_density < 1.0) then
        if (number_per_m3 > huge(number_per_m3) * dry_density) return
      end if
      number_per_kg = number_per_m3 / dry_density
      valid = ieee_is_finite(number_per_kg)
      if (number_per_m3 > 0.0 .and. number_per_kg == 0.0) valid = .false.
    end subroutine volume_number_to_specific

    subroutine kdm6_mass_volume_rate(mass_rate,density,volume_rate,feasible)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: mass_rate,density
      real, intent(out) :: volume_rate
      logical, intent(out) :: feasible

      volume_rate=0.0
      feasible=.false.
      if (.not.all(ieee_is_finite([mass_rate,density]))) return
      if (mass_rate.eq.0.0) then
        feasible=.true.
        return
      endif
      if (density.le.0.0) return
      volume_rate=mass_rate/density
      feasible=ieee_is_finite(volume_rate)
      if (.not.feasible) volume_rate=0.0
    end subroutine kdm6_mass_volume_rate

    subroutine kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
         bg_fixed,bg_process,t_fixed,t_process,rain_cleanup_pending,density,pidnr,qmin,ncmin, &
         qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc, &
         lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max, &
         fraction,feasible,search_status,vapor_fixed,vapor_process,consumer_pair_only, &
         ice_transient_mass_limit,ice_sublimation_pending)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: q_fixed(5),q_process(5),n_fixed(3),n_process(3)
      real, intent(in) :: bg_fixed,bg_process,t_fixed,t_process,density,pidnr
      logical, intent(in) :: rain_cleanup_pending
      real, intent(in) :: qmin,ncmin,qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max
      real, intent(in) :: pidnc,dmc,lambda_c_min,lambda_c_max
      real, intent(in) :: pidni,dmi,lambda_i_min,lambda_i_max
      real, intent(out) :: fraction
      logical, intent(out) :: feasible
      integer, intent(out) :: search_status
      real, intent(in), optional :: vapor_fixed,vapor_process
      logical, intent(in), optional :: consumer_pair_only
      real, intent(in), optional :: ice_transient_mass_limit
      logical, intent(in), optional :: ice_sublimation_pending
! 0=FEASIBLE, 1=NO_FEASIBLE_STEP, 2=SEARCH_FAILURE.
      integer, parameter :: feasible_status=0,no_step_status=1,search_failure_status=2
      real(kind=8) :: breaks(16),lower,upper,alpha,midpoint,best
      real(kind=8) :: valid_alpha,invalid_alpha,bracket_midpoint,probe_alpha
      real(kind=8) :: midpoint_invalid_alpha,upper_invalid_alpha
      real(kind=8) :: rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max
      real(kind=8) :: ice_transient_limit
      real(kind=8) :: q0(5),dq(5),n0(3),dn(3),bg0,dbg,qv0,dqv
      real :: q_trial(5),n_trial(3),bg_trial,t_trial,qv_trial,trial
      integer :: count_breaks,i,j,walks
      logical :: interval_valid,step_valid,search_failed,interval_mid_valid
      logical :: interval_lower_valid,midpoint_tested_invalid,probe_valid
      logical :: pair_only,ice_sublimation_pending_value

      feasible=.false.
      fraction=0.0
      search_status=search_failure_status
      pair_only=.false.
      if (present(consumer_pair_only)) pair_only=consumer_pair_only
      ice_sublimation_pending_value=.false.
      if (present(ice_sublimation_pending)) &
        ice_sublimation_pending_value=ice_sublimation_pending
      if (.not.all(ieee_is_finite([q_fixed,q_process,n_fixed,n_process, &
          bg_fixed,bg_process,t_fixed,t_process,density,pidnr,pidnc,pidni, &
          qmin,ncmin,qcrmin,dmr,dmc,dmi,lambda_min,lambda_max, &
          lambda_c_min,lambda_c_max,lambda_i_min,lambda_i_max,rho_min,rho_max]))) return
      if (density.le.0.0 .or. pidnr.le.0.0 .or. pidnc.le.0.0 .or. pidni.le.0.0 .or. &
          lambda_min.le.0.0 .or. lambda_max.lt.lambda_min .or. &
          lambda_c_min.le.0.0 .or. lambda_c_max.lt.lambda_c_min .or. &
          lambda_i_min.le.0.0 .or. lambda_i_max.lt.lambda_i_min .or. &
          rho_min.le.0.0 .or. rho_max.lt.rho_min .or. &
          qmin.lt.0.0 .or. ncmin.lt.0.0 .or. qcrmin.lt.0.0 .or. &
          dmr.le.0.0 .or. dmc.le.0.0 .or. dmi.le.0.0 .or. &
          dmr.gt.8.0 .or. dmc.gt.8.0 .or. dmi.gt.8.0) return
      if (present(vapor_fixed) .neqv. present(vapor_process)) return
      ice_transient_limit=0.0d0
      if (present(ice_transient_mass_limit)) then
        if (.not.ieee_is_finite(ice_transient_mass_limit) .or. &
            ice_transient_mass_limit.lt.0.0 .or. &
            ice_transient_mass_limit.gt.PR85_ICE_NATIVE_INACTIVE_MAX) return
        ice_transient_limit=real(ice_transient_mass_limit,8)
      endif
      qv0=0.0d0; dqv=0.0d0
      if (present(vapor_fixed)) then
        if (.not.all(ieee_is_finite([vapor_fixed,vapor_process]))) return
        if (vapor_fixed.lt.0.0) return
        qv0=real(vapor_fixed,8); dqv=real(vapor_process,8)
      endif

      rain_min=real(density,8)*real(lambda_min,8)**real(dmr,8)/real(pidnr,8)
      rain_max=real(density,8)*real(lambda_max,8)**real(dmr,8)/real(pidnr,8)
      cloud_min=real(density,8)*real(lambda_c_min,8)**real(dmc,8)/real(pidnc,8)
      cloud_max=real(density,8)*real(lambda_c_max,8)**real(dmc,8)/real(pidnc,8)
      ice_min=real(density,8)*real(lambda_i_min,8)**real(dmi,8)/real(pidni,8)
      ice_max=real(density,8)*real(lambda_i_max,8)**real(dmi,8)/real(pidni,8)
      if (.not.all(ieee_is_finite([rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max]))) return
      if (rain_min.le.0.0d0 .or. cloud_min.le.0.0d0 .or. ice_min.le.0.0d0) return
      if (max(rain_max,cloud_max,ice_max).gt.real(huge(0.0),8)) return
      q0=real(q_fixed,8); dq=real(q_process,8)
      n0=real(n_fixed,8); dn=real(n_process,8)
      bg0=real(bg_fixed,8); dbg=real(bg_process,8)

      count_breaks=2
      search_failed=.false.
      breaks(1)=0.0d0; breaks(2)=1.0d0
      do i=1,5
        call add_breakpoint(q0(i),dq(i),0.0d0)
      enddo
      do i=1,3
        call add_breakpoint(n0(i),dn(i),0.0d0)
      enddo
      if (present(ice_transient_mass_limit)) &
        call add_breakpoint(q0(2),dq(2),ice_transient_limit)
      call add_breakpoint(real(t_fixed,8),real(t_process,8),0.0d0)
      if (present(vapor_fixed)) call add_breakpoint(qv0,dqv,0.0d0)
      call add_breakpoint(q0(5),dq(5),real(qcrmin,8))
      call add_breakpoint(bg0,dbg,real(1.0e-15,8))
      call sort_breakpoints()

      best=0.0d0
      do i=1,count_breaks
        alpha=breaks(i)
        if (alpha.le.0.0d0) cycle
        trial=real(alpha)
        call validate_trial(trial,step_valid)
        if (step_valid) best=max(best,real(trial,8))
      enddo

      do i=count_breaks-1,1,-1
        lower=breaks(i); upper=breaks(i+1)
        if (upper.le.lower) cycle
        midpoint=lower+(upper-lower)/2.0d0
        call interval_constraints(midpoint,lower,upper,interval_valid)
        if (.not.interval_valid) cycle
        if (.not.pair_only) then
          if (no_storable_rain_interval(lower,upper)) cycle
        endif
        interval_mid_valid=.false.
        interval_lower_valid=.false.
        midpoint_tested_invalid=.false.
        midpoint=lower+(upper-lower)/2.0d0
        trial=real(midpoint)
        alpha=real(trial,8)
        if (trial.gt.0.0 .and. alpha.ge.lower .and. alpha.le.upper) then
          call validate_trial(trial,step_valid)
          if (step_valid) then
            best=max(best,real(trial,8))
            valid_alpha=real(trial,8)
            interval_mid_valid=.true.
          else
            midpoint_invalid_alpha=real(trial,8)
            midpoint_tested_invalid=.true.
          endif
        endif
        trial=real(lower)
        alpha=real(trial,8)
        if (trial.gt.0.0 .and. alpha.ge.lower .and. alpha.le.upper) then
          call validate_trial(trial,step_valid)
          if (step_valid) then
            best=max(best,real(trial,8))
            interval_lower_valid=.true.
            if (.not.interval_mid_valid) valid_alpha=real(trial,8)
          endif
        endif
        trial=real(upper)
        alpha=real(trial,8)
        if (alpha.gt.upper) then
          trial=nearest(trial,-1.0)
          alpha=real(trial,8)
        endif
        if (alpha.lt.lower) cycle
        walks=0
        do
          if (trial.le.0.0) exit
          call validate_trial(trial,step_valid)
          if (step_valid) then
            best=max(best,real(trial,8))
            exit
          endif
          if (real(trial,8).le.lower) exit
          if (walks.ge.32) then
            search_failed=.true.
            upper_invalid_alpha=real(trial,8)
            if (interval_mid_valid) then
              invalid_alpha=upper_invalid_alpha
              call refine_valid_interval(valid_alpha,invalid_alpha)
            else
              if (interval_lower_valid) then
                if (midpoint_tested_invalid) then
                  invalid_alpha=midpoint_invalid_alpha
                else
                  invalid_alpha=upper_invalid_alpha
                endif
                call refine_valid_interval(valid_alpha,invalid_alpha)
              else
! Stored REAL32 rounding may reject the interval midpoint even
! when smaller positive fractions still preserve a valid state.
! Probe toward the lower edge; any refinement starts from a
! trial that passed the exact stored-state validator.
                probe_valid=.false.
                if (midpoint_tested_invalid) then
                  probe_alpha=midpoint_invalid_alpha
                else
                  probe_alpha=upper_invalid_alpha
                endif
                invalid_alpha=probe_alpha
                do j=1,32
                  probe_alpha=lower+(probe_alpha-lower)/2.0d0
                  trial=real(probe_alpha)
                  alpha=real(trial,8)
                  if (trial.le.0.0 .or. alpha.le.lower .or. alpha.ge.invalid_alpha) exit
                  call validate_trial(trial,step_valid)
                  if (step_valid) then
                    valid_alpha=alpha
                    best=max(best,alpha)
                    probe_valid=.true.
                    exit
                  endif
                  invalid_alpha=alpha
                enddo
                if (.not.probe_valid) then
                  trial=nearest(real(lower),1.0)
                  alpha=real(trial,8)
                  if (trial.gt.0.0 .and. alpha.gt.lower .and. alpha.lt.upper) then
                    call validate_trial(trial,step_valid)
                    if (step_valid) then
                      valid_alpha=alpha
                      best=max(best,alpha)
                      probe_valid=.true.
                    endif
                  endif
                endif
                if (probe_valid) call refine_valid_interval(valid_alpha,invalid_alpha)
              endif
            endif
            exit
          endif
          trial=nearest(trial,-1.0)
          walks=walks+1
        enddo
      enddo

      if (search_failed .and. best.le.0.0d0) then
        search_status=search_failure_status
        return
      endif
      if (best.le.0.0d0) then
        search_status=no_step_status
        return
      endif
      fraction=real(best)
      call validate_trial(fraction,step_valid)
      if (.not.step_valid) then
        fraction=0.0
        search_status=search_failure_status
        return
      endif
      feasible=.true.
      search_status=feasible_status

    contains
      subroutine refine_valid_interval(valid,invalid)
        real(kind=8), intent(inout) :: valid,invalid
        real(kind=8) :: candidate
        integer :: refinement
        do refinement=1,32
          bracket_midpoint=valid+(invalid-valid)/2.0d0
          trial=real(bracket_midpoint)
          candidate=real(trial,8)
          if (candidate.le.valid .or. candidate.ge.invalid) exit
          call validate_trial(trial,step_valid)
          if (step_valid) then
            valid=candidate
            best=max(best,candidate)
          else
            invalid=candidate
          endif
        enddo
      end subroutine refine_valid_interval

      subroutine add_breakpoint(initial,slope,cutoff)
        real(kind=8), intent(in) :: initial,slope,cutoff
        real(kind=8) :: root
        if (slope.eq.0.0d0) return
        root=(cutoff-initial)/slope
        if (.not.ieee_is_finite(root)) then
          search_failed=.true.
          return
        endif
        if (root.gt.0.0d0 .and. root.lt.1.0d0 .and. count_breaks.lt.size(breaks)) then
          count_breaks=count_breaks+1
          breaks(count_breaks)=root
        endif
      end subroutine add_breakpoint

      subroutine sort_breakpoints()
        real(kind=8) :: value
        integer :: left,right
        do left=2,count_breaks
          value=breaks(left); right=left-1
          do while (right.ge.1)
            if (breaks(right).le.value) exit
            breaks(right+1)=breaks(right); right=right-1
          enddo
          breaks(right+1)=value
        enddo
        j=1
        do left=2,count_breaks
          if (breaks(left).eq.breaks(j)) cycle
          j=j+1; breaks(j)=breaks(left)
        enddo
        count_breaks=j
      end subroutine sort_breakpoints

      logical function no_storable_rain_interval(lo,hi)
        real(kind=8), intent(in) :: lo,hi
        real :: alpha_first,alpha_last,q_first,q_last,n_first,n_last
        real(kind=8) :: q_min_store,q_max_store,n_min_store,n_max_store
        real(kind=8) :: lower_number,upper_number

        no_storable_rain_interval=.false.
        if (.not.all(ieee_is_finite([lo,hi]))) return
        if (lo.gt.hi) return
        alpha_first=real(lo)
        if (.not.ieee_is_finite(alpha_first)) return
        if (real(alpha_first,8).lt.lo) alpha_first=nearest(alpha_first,1.0)
        alpha_last=real(hi)
        if (.not.ieee_is_finite(alpha_last)) return
        if (real(alpha_last,8).gt.hi) alpha_last=nearest(alpha_last,-1.0)
        if (.not.all(ieee_is_finite([alpha_first,alpha_last]))) return
        if (real(alpha_first,8).gt.hi .or. real(alpha_last,8).lt.lo .or. &
            alpha_first.gt.alpha_last) then
          no_storable_rain_interval=.true.
          return
        endif

! Rounded affine endpoint extrema enclose all stored REAL32 Q/N here.
! Requiring positive Q excludes exact absence from this rejection proof.
        q_first=q_fixed(3)+alpha_first*q_process(3)
        q_last=q_fixed(3)+alpha_last*q_process(3)
        n_first=n_fixed(3)+alpha_first*n_process(3)
        n_last=n_fixed(3)+alpha_last*n_process(3)
        if (.not.all(ieee_is_finite([q_first,q_last,n_first,n_last]))) return
        q_min_store=real(min(q_first,q_last),8)
        q_max_store=real(max(q_first,q_last),8)
        n_min_store=real(min(n_first,n_last),8)
        n_max_store=real(max(n_first,n_last),8)
        if (.not.all(ieee_is_finite([q_min_store,q_max_store,n_min_store,n_max_store]))) return
        if (q_min_store.le.0.0d0) return
        lower_number=rain_min*q_min_store
        upper_number=rain_max*q_max_store
        if (.not.all(ieee_is_finite([lower_number,upper_number]))) return
        no_storable_rain_interval=n_min_store.gt.upper_number .or. &
                                  n_max_store.lt.lower_number
      end function no_storable_rain_interval

      subroutine interval_constraints(sample,lo,hi,valid_interval)
        real(kind=8), intent(in) :: sample
        real(kind=8), intent(inout) :: lo,hi
        logical, intent(out) :: valid_interval
        real(kind=8) :: qm(5),nm(3),bm
        integer :: m
        logical :: rain_active,cloud_active,ice_active
        qm=q0+sample*dq; nm=n0+sample*dn; bm=bg0+sample*dbg
        valid_interval=.true.
        do m=1,5
          call clip(q0(m),dq(m),lo,hi,valid_interval)
        enddo
        do m=1,3
          call clip(n0(m),dn(m),lo,hi,valid_interval)
        enddo
        call clip(bg0,dbg,lo,hi,valid_interval)
        call clip(real(t_fixed,8),real(t_process,8),lo,hi,valid_interval)
        if (present(vapor_fixed)) call clip(qv0,dqv,lo,hi,valid_interval)
        if (.not.valid_interval) return

        if (pair_only) then
          do m=1,3
            if (qm(m).gt.0.0d0 .and. nm(m).gt.0.0d0) then
              call clip(q0(m),dq(m),lo,hi,valid_interval)
              call clip(n0(m),dn(m),lo,hi,valid_interval)
            elseif (m.eq.2 .and. qm(m).eq.0.0d0 .and. nm(m).gt.0.0d0 .and. &
                    ice_sublimation_pending_value) then
              call clip(q0(m),dq(m),lo,hi,valid_interval)
              call clip(-q0(m),-dq(m),lo,hi,valid_interval)
            elseif (m.eq.3 .and. qm(m).eq.0.0d0 .and. nm(m).gt.0.0d0 .and. &
                    rain_cleanup_pending) then
              call clip(q0(m),dq(m),lo,hi,valid_interval)
              call clip(n0(m),dn(m),lo,hi,valid_interval)
            elseif (qm(m).eq.0.0d0 .and. nm(m).eq.0.0d0) then
              call clip(q0(m),dq(m),lo,hi,valid_interval)
              call clip(-q0(m),-dq(m),lo,hi,valid_interval)
              call clip(n0(m),dn(m),lo,hi,valid_interval)
              call clip(-n0(m),-dn(m),lo,hi,valid_interval)
            else
              valid_interval=.false.
            endif
          enddo
          call clip(q0(4),dq(4),lo,hi,valid_interval)
          if (qm(5).gt.0.0d0 .and. bm.gt.0.0d0) then
            call clip(q0(5),dq(5),lo,hi,valid_interval)
            call clip(bg0-q0(5)/real(rho_max,8),dbg-dq(5)/real(rho_max,8),lo,hi,valid_interval)
            call clip(q0(5)/real(rho_min,8)-bg0,dq(5)/real(rho_min,8)-dbg,lo,hi,valid_interval)
          elseif (qm(5).eq.0.0d0 .and. bm.eq.0.0d0) then
            call clip(q0(5),dq(5),lo,hi,valid_interval)
            call clip(-q0(5),-dq(5),lo,hi,valid_interval)
            call clip(bg0,dbg,lo,hi,valid_interval)
            call clip(-bg0,-dbg,lo,hi,valid_interval)
          else
            valid_interval=.false.
          endif
          if (lo.gt.hi) valid_interval=.false.
          if (.not.ieee_is_finite(bm)) valid_interval=.false.
          return
        endif

        if (qm(3).gt.0.0d0 .and. nm(3).gt.0.0d0) then
          call clip(q0(3),dq(3),lo,hi,valid_interval)
          call clip(n0(3)-rain_min*q0(3),dn(3)-rain_min*dq(3),lo,hi,valid_interval)
          call clip(rain_max*q0(3)-n0(3),rain_max*dq(3)-dn(3),lo,hi,valid_interval)
        elseif (qm(3).eq.0.0d0) then
          call clip(q0(3),dq(3),lo,hi,valid_interval)
          call clip(-q0(3),-dq(3),lo,hi,valid_interval)
          if (.not.rain_cleanup_pending) then
            call clip(n0(3),dn(3),lo,hi,valid_interval)
            call clip(-n0(3),-dn(3),lo,hi,valid_interval)
          endif
        else
          valid_interval=.false.
        endif
        cloud_active=qm(1).gt.0.0d0 .and. nm(1).gt.0.0d0
        if (cloud_active) then
          call clip(q0(1),dq(1),lo,hi,valid_interval)
          call clip(n0(1),dn(1),lo,hi,valid_interval)
          call clip(n0(1)-cloud_min*q0(1),dn(1)-cloud_min*dq(1),lo,hi,valid_interval)
          call clip(cloud_max*q0(1)-n0(1),cloud_max*dq(1)-dn(1),lo,hi,valid_interval)
        elseif (qm(1).eq.0.0d0 .and. nm(1).eq.0.0d0) then
          call clip(q0(1),dq(1),lo,hi,valid_interval)
          call clip(-q0(1),-dq(1),lo,hi,valid_interval)
          call clip(n0(1),dn(1),lo,hi,valid_interval)
          call clip(-n0(1),-dn(1),lo,hi,valid_interval)
        else
          valid_interval=.false.
        endif
        ice_active=qm(2).gt.0.0d0 .and. nm(2).gt.0.0d0
        if (ice_active) then
          call clip(q0(2),dq(2),lo,hi,valid_interval)
          call clip(n0(2),dn(2),lo,hi,valid_interval)
          if (.not.present(ice_transient_mass_limit) .or. &
              qm(2).gt.ice_transient_limit) then
            call clip(n0(2)-ice_min*q0(2),dn(2)-ice_min*dq(2),lo,hi,valid_interval)
            call clip(ice_max*q0(2)-n0(2),ice_max*dq(2)-dn(2),lo,hi,valid_interval)
          endif
        elseif (qm(2).eq.0.0d0 .and. nm(2).gt.0.0d0 .and. &
                ice_sublimation_pending_value) then
          call clip(q0(2),dq(2),lo,hi,valid_interval)
          call clip(-q0(2),-dq(2),lo,hi,valid_interval)
        elseif (qm(2).eq.0.0d0 .and. nm(2).eq.0.0d0) then
          call clip(q0(2),dq(2),lo,hi,valid_interval)
          call clip(-q0(2),-dq(2),lo,hi,valid_interval)
          call clip(n0(2),dn(2),lo,hi,valid_interval)
          call clip(-n0(2),-dn(2),lo,hi,valid_interval)
        else
          valid_interval=.false.
        endif
        do m=4,5
          if (qm(m).gt.0.0d0) then
            call clip(q0(m),dq(m),lo,hi,valid_interval)
          elseif (qm(m).eq.0.0d0) then
            call clip(q0(m),dq(m),lo,hi,valid_interval)
            call clip(-q0(m),-dq(m),lo,hi,valid_interval)
          else
            valid_interval=.false.
          endif
        enddo
        call clip(bg0-q0(5)/real(rho_max,8),dbg-dq(5)/real(rho_max,8),lo,hi,valid_interval)
        call clip(q0(5)/real(rho_min,8)-bg0,dq(5)/real(rho_min,8)-dbg,lo,hi,valid_interval)
        if (lo.gt.hi) valid_interval=.false.
        if (.not.ieee_is_finite(bm)) valid_interval=.false.
      end subroutine interval_constraints

      subroutine clip(initial,slope,lo,hi,valid_interval)
        real(kind=8), intent(in) :: initial,slope
        real(kind=8), intent(inout) :: lo,hi
        logical, intent(inout) :: valid_interval
        real(kind=8) :: boundary
        if (.not.valid_interval) return
        if (slope.eq.0.0d0) then
          if (initial.lt.0.0d0) valid_interval=.false.
        elseif (slope.gt.0.0d0) then
          boundary=-initial/slope
          if (.not.ieee_is_finite(boundary)) search_failed=.true.
          lo=max(lo,boundary)
        else
          boundary=-initial/slope
          if (.not.ieee_is_finite(boundary)) search_failed=.true.
          hi=min(hi,boundary)
        endif
        if (.not.ieee_is_finite(lo) .or. .not.ieee_is_finite(hi)) then
          valid_interval=.false.
          search_failed=.true.
        endif
        if (lo.gt.hi) valid_interval=.false.
      end subroutine clip

      subroutine validate_trial(a,is_valid)
        real, intent(in) :: a
        logical, intent(out) :: is_valid
        integer :: m
        q_trial=q_fixed+a*q_process
        n_trial=n_fixed+a*n_process
        bg_trial=bg_fixed+a*bg_process
        t_trial=t_fixed+a*t_process
        if (present(vapor_fixed)) qv_trial=vapor_fixed+a*vapor_process
        is_valid=all(ieee_is_finite([q_trial,n_trial,bg_trial,t_trial]))
        if (present(vapor_fixed)) is_valid=is_valid.and.ieee_is_finite(qv_trial)
        if (.not.is_valid) return
        if (any(q_trial.lt.0.0) .or. any(n_trial.lt.0.0) .or. bg_trial.lt.0.0) then
          is_valid=.false.; return
        endif
        if (present(vapor_fixed)) then
          if (qv_trial.lt.0.0) then
            is_valid=.false.; return
          endif
        endif
        if (t_trial.le.0.0) then
          is_valid=.false.
          return
        endif
        call kdm6_rain_process_state_valid(q_trial,n_trial,bg_trial,t_trial,density,pidnr, &
             qmin,ncmin,qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max, &
             pidnc,dmc,lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min, &
             lambda_i_max,is_valid,rain_cleanup_pending,pair_only, &
             ice_transient_mass_limit, &
             ice_sublimation_pending=ice_sublimation_pending_value)
      end subroutine validate_trial
    end subroutine kdm6_rain_process_fraction

    pure subroutine kdm6_rain_ng_pair_valid(q,n,rain_min,rain_max, &
         allow_argument_present,allow_number_at_zero,valid,failure_reason)
      implicit none
      real, intent(in) :: q,n
      real(kind=8), intent(in) :: rain_min,rain_max
      logical, intent(in) :: allow_argument_present,allow_number_at_zero
      logical, intent(out) :: valid
      integer, intent(out) :: failure_reason
      valid=.false.
      failure_reason=0
      if (.not.ieee_is_finite(q) .or. .not.ieee_is_finite(n) .or. &
          .not.ieee_is_finite(rain_min) .or. .not.ieee_is_finite(rain_max)) then
        failure_reason=1
        return
      endif
      if (q.lt.0.0 .or. n.lt.0.0) then
        failure_reason=2
        return
      endif
      if (q.eq.0.0) then
        if (n.ne.0.0) then
          if (.not.allow_argument_present) then
            failure_reason=3
            return
          endif
          if (.not.allow_number_at_zero) then
            failure_reason=3
            return
          endif
        endif
      elseif (q.le.0.0 .or. n.le.0.0) then
        failure_reason=3
        return
      elseif (real(n,8).lt.rain_min*q .or. real(n,8).gt.rain_max*q) then
        failure_reason=6
        return
      endif
      valid=.true.
    end subroutine kdm6_rain_ng_pair_valid

    logical function kdm6_unreconstructed_rain_output_valid(q,n,density,pidnr,power, &
          lambda_min,lambda_max,qcrmin,nrmin)
      use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
      use iso_fortran_env, only : real32,real64
      implicit none
      real(real32), intent(in) :: q,n,density,pidnr,power,lambda_min,lambda_max
      real(real32), intent(in) :: qcrmin,nrmin
      real(real32) :: q_public,n_specific,q_restored,nvol_restored
      real(real64) :: delta_q,delta_n,delta_q_back,delta_nvol_back
      real(real64) :: rain_min,rain_max
      real(real64) :: diagnostic(12)
      integer :: adjustment,adjustment_back,stage,core_stage,consumer_reason
      character(len=32) :: reason
      logical :: store_valid,restore_valid,consumer_valid
      interface
        subroutine pr90_rain_public_store_diagnostic(q_internal,nvol_internal,dry_density, &
             pidnr,power,lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n, &
             adjustment,failure_reason,diagnostic,stage,core_stage)
          use iso_fortran_env, only : real32,real64
          real(real32), intent(in) :: q_internal,nvol_internal,dry_density,pidnr,power
          real(real32), intent(in) :: lambda_min,lambda_max
          real(real32), intent(out) :: q_public,n_specific
          logical, intent(out) :: valid
          real(real64), intent(out) :: delta_q,delta_n,diagnostic(12)
          integer, intent(out) :: adjustment,stage,core_stage
          character(len=*), intent(out) :: failure_reason
        end subroutine pr90_rain_public_store_diagnostic
        subroutine pr87_number_volume_store(q_specific,n_specific,dry_density,pidnr,power, &
             lambda_min,lambda_max,q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
          use iso_fortran_env, only : real32,real64
          real(real32), intent(in) :: q_specific,n_specific,dry_density,pidnr,power
          real(real32), intent(in) :: lambda_min,lambda_max
          real(real32), intent(out) :: q_stored,n_volume
          logical, intent(out) :: valid
          real(real64), intent(out) :: delta_q,delta_nvolume
          integer, intent(out) :: adjustment
        end subroutine pr87_number_volume_store
      end interface

      kdm6_unreconstructed_rain_output_valid=.false.
      if (.not.all(ieee_is_finite([q,n,density,pidnr,power,lambda_min,lambda_max, &
                                   qcrmin,nrmin]))) return
      if (q.lt.0.0_real32 .or. n.lt.0.0_real32 .or. density.le.0.0_real32 .or. &
          pidnr.le.0.0_real32 .or. power.le.0.0_real32 .or. power.gt.8.0_real32 .or. &
          lambda_min.le.0.0_real32 .or. lambda_max.lt.lambda_min .or. &
          qcrmin.lt.0.0_real32 .or. nrmin.lt.0.0_real32) return

! The caller's original state validator owns cutoff, zero-pair, and pending rules.
! Stage-3 can reconstruct only when both source cutoffs are active.
      kdm6_unreconstructed_rain_output_valid=.true.
      if (q.le.qcrmin .or. n.ge.nrmin) return
      if (q.le.0.0_real32 .or. n.le.0.0_real32) then
        kdm6_unreconstructed_rain_output_valid=.false.
        return
      endif

      call pr90_rain_public_store_diagnostic(q,n,density,pidnr,power,lambda_min, &
           lambda_max,q_public,n_specific,store_valid,delta_q,delta_n,adjustment, &
           reason,diagnostic,stage,core_stage)
      if (.not.store_valid) then
        kdm6_unreconstructed_rain_output_valid=.false.
        return
      endif
      call pr87_number_volume_store(q_public,n_specific,density,pidnr,power, &
           lambda_min,lambda_max,q_restored,nvol_restored,restore_valid,delta_q_back, &
           delta_nvol_back,adjustment_back)
      if (.not.restore_valid) then
        kdm6_unreconstructed_rain_output_valid=.false.
        return
      endif
      rain_min=real(density,real64)*real(lambda_min,real64)**real(power,real64)/real(pidnr,real64)
      rain_max=real(density,real64)*real(lambda_max,real64)**real(power,real64)/real(pidnr,real64)
      if (.not.all(ieee_is_finite([rain_min,rain_max]))) then
        kdm6_unreconstructed_rain_output_valid=.false.
        return
      endif
      call kdm6_rain_ng_pair_valid(q_restored,nvol_restored,rain_min,rain_max, &
           .false.,.false.,consumer_valid,consumer_reason)
      kdm6_unreconstructed_rain_output_valid=consumer_valid
    end function kdm6_unreconstructed_rain_output_valid

subroutine kdm6_rain_process_state_valid(q,n,bg,temperature,density,pidnr,qmin,ncmin, &
         qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc, &
         lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,valid, &
         allow_rain_number_at_zero,consumer_pair_only,ice_transient_mass_limit, &
         failure_reason,ice_sublimation_pending)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: q(5),n(3),bg,temperature,density,pidnr,qmin,ncmin,qcrmin,dmr
      real, intent(in) :: lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc
      real, intent(in) :: lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max
      logical, intent(out) :: valid
      logical, intent(in), optional :: allow_rain_number_at_zero
      logical, intent(in), optional :: consumer_pair_only
      real, intent(in), optional :: ice_transient_mass_limit
      integer, intent(out), optional :: failure_reason
      logical, intent(in), optional :: ice_sublimation_pending
      real(kind=8) :: rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max,ice_transient_limit
      logical :: pair_only,ice_pending,rain_pair_allowed,rain_pair_valid_result
      integer :: rain_reason

      valid=.false.
      if (present(failure_reason)) failure_reason=0
      if (.not.all(ieee_is_finite([q,n,bg,temperature,density,pidnr,qmin,ncmin,qcrmin,dmr, &
          lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc,lambda_c_min, &
          lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max]))) then
        if (present(failure_reason)) failure_reason=1
        return
      endif
      if (density.le.0.0 .or. pidnr.le.0.0 .or. pidnc.le.0.0 .or. pidni.le.0.0 .or. &
          qmin.lt.0.0 .or. qcrmin.lt.0.0 .or. lambda_min.le.0.0 .or. &
          lambda_max.lt.lambda_min .or. lambda_c_min.le.0.0 .or. &
          lambda_c_max.lt.lambda_c_min .or. lambda_i_min.le.0.0 .or. &
          lambda_i_max.lt.lambda_i_min .or. rho_min.le.0.0 .or. rho_max.lt.rho_min .or. &
          dmr.le.0.0 .or. dmc.le.0.0 .or. dmi.le.0.0 .or. &
          dmr.gt.8.0 .or. dmc.gt.8.0 .or. dmi.gt.8.0) then
        if (present(failure_reason)) failure_reason=1
        return
      endif
      ice_transient_limit=0.0d0
      if (present(ice_transient_mass_limit)) then
        if (.not.ieee_is_finite(ice_transient_mass_limit) .or. &
            ice_transient_mass_limit.lt.0.0 .or. ice_transient_mass_limit.gt.PR85_ICE_NATIVE_INACTIVE_MAX) then
          if (present(failure_reason)) failure_reason=1
          return
        endif
        ice_transient_limit=real(ice_transient_mass_limit,8)
      endif
      if (temperature.le.0.0) then
        if (present(failure_reason)) failure_reason=8
        return
      endif
      if (any(q.lt.0.0) .or. any(n.lt.0.0) .or. bg.lt.0.0) then
        if (present(failure_reason)) failure_reason=2
        return
      endif
      pair_only=.false.
      if (present(consumer_pair_only)) pair_only=consumer_pair_only
      ice_pending=.false.
      if (present(ice_sublimation_pending)) ice_pending=ice_sublimation_pending
      if (pair_only) then
        if (q(1).eq.0.0) then
          if (n(1).ne.0.0) then
            if (present(failure_reason)) failure_reason=3
            return
          endif
        elseif (n(1).le.0.0) then
          if (present(failure_reason)) failure_reason=3
          return
        endif
        if (q(2).eq.0.0) then
          if (n(2).ne.0.0 .and. .not.ice_pending) then
            if (present(failure_reason)) failure_reason=3
            return
          endif
        elseif (n(2).le.0.0) then
          if (present(failure_reason)) failure_reason=3
          return
        endif
        if (q(3).eq.0.0) then
          if (n(3).ne.0.0) then
            if (.not.present(allow_rain_number_at_zero)) then
              if (present(failure_reason)) failure_reason=3
              return
            endif
            if (.not.allow_rain_number_at_zero) then
              if (present(failure_reason)) failure_reason=3
              return
            endif
          endif
        elseif (n(3).le.0.0) then
          if (present(failure_reason)) failure_reason=3
          return
        endif
        if (.not.kdm6_progb_density_pair_valid(q(5),bg,rho_min,rho_max)) then
          if (present(failure_reason)) failure_reason=9
          return
        endif
        valid=.true.
        return
      endif
      rain_min=real(density,8)*real(lambda_min,8)**real(dmr,8)/real(pidnr,8)
      rain_max=real(density,8)*real(lambda_max,8)**real(dmr,8)/real(pidnr,8)
      cloud_min=real(density,8)*real(lambda_c_min,8)**real(dmc,8)/real(pidnc,8)
      cloud_max=real(density,8)*real(lambda_c_max,8)**real(dmc,8)/real(pidnc,8)
      ice_min=real(density,8)*real(lambda_i_min,8)**real(dmi,8)/real(pidni,8)
      ice_max=real(density,8)*real(lambda_i_max,8)**real(dmi,8)/real(pidni,8)
      if (.not.all(ieee_is_finite([rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max]))) then
        if (present(failure_reason)) failure_reason=1
        return
      endif
      if (max(rain_max,cloud_max,ice_max).gt.real(huge(0.0),8)) then
        if (present(failure_reason)) failure_reason=1
        return
      endif
      if (q(1).eq.0.0) then
        if (n(1).ne.0.0) then
          if (present(failure_reason)) failure_reason=3
          return
        endif
      elseif (q(1).le.0.0 .or. n(1).le.0.0) then
        if (present(failure_reason)) failure_reason=3
        return
      elseif (real(n(1),8).lt.cloud_min*q(1) .or. real(n(1),8).gt.cloud_max*q(1)) then
        if (present(failure_reason)) failure_reason=5
        return
      endif
      if (q(2).eq.0.0) then
        if (n(2).ne.0.0 .and. .not.ice_pending) then
          if (present(failure_reason)) failure_reason=3
          return
        endif
      elseif (q(2).le.0.0 .or. n(2).le.0.0) then
        if (present(failure_reason)) failure_reason=3
        return
      elseif (q(2).gt.ice_transient_limit) then
        call kdm6_ice_ng_pair_contract(q(2),n(2),density,pidni,dmi, &
             lambda_i_min,lambda_i_max,rain_pair_valid_result,ice_min,ice_max)
        if (.not.rain_pair_valid_result) then
          if (present(failure_reason)) failure_reason=7
          return
        endif
      endif
      rain_pair_allowed=.false.
      if (present(allow_rain_number_at_zero)) &
          rain_pair_allowed=allow_rain_number_at_zero
      call kdm6_rain_ng_pair_valid(q(3),n(3),rain_min,rain_max, &
           present(allow_rain_number_at_zero),rain_pair_allowed, &
           rain_pair_valid_result,rain_reason)
      if (.not.rain_pair_valid_result) then
        if (present(failure_reason)) failure_reason=rain_reason
        return
      endif
      if (q(4).lt.0.0 .or. q(5).lt.0.0) then
        if (present(failure_reason)) failure_reason=2
        return
      endif
        if (.not.kdm6_progb_density_pair_valid(q(5),bg,rho_min,rho_max)) then
          if (present(failure_reason)) failure_reason=9
          return
        endif
      valid=.true.
      if (present(failure_reason)) failure_reason=0
    end subroutine kdm6_rain_process_state_valid
pure subroutine kdm6_ice_ng_pair_contract(q,n,density,pidni,dmi,lambda_min,lambda_max,valid,n_min,n_max)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: q,n,density,pidni,dmi,lambda_min,lambda_max
      logical, intent(out) :: valid
      real(kind=8), intent(out) :: n_min,n_max
      valid=.false.
      n_min=0.0d0
      n_max=0.0d0
      if (.not.all(ieee_is_finite([q,n,density,pidni,dmi,lambda_min,lambda_max]))) return
      if (density.le.0.0 .or. pidni.le.0.0 .or. dmi.le.0.0 .or. dmi.gt.8.0 .or. &
          lambda_min.le.0.0 .or. lambda_max.lt.lambda_min) return
      if (q.eq.0.0 .and. n.eq.0.0) then
        valid=.true.
        return
      endif
      if (q.le.0.0 .or. n.le.0.0) return
      n_min=(real(density,8)*real(lambda_min,8)**real(dmi,8)/real(pidni,8))*real(q,8)
      n_max=(real(density,8)*real(lambda_max,8)**real(dmi,8)/real(pidni,8))*real(q,8)
      valid=ieee_is_finite(n_min) .and. ieee_is_finite(n_max) .and. &
          real(n,8).ge.n_min .and. real(n,8).le.n_max
    end subroutine kdm6_ice_ng_pair_contract

    subroutine constrain_process_margin(margin_initial,margin_process, &
         alpha_min,alpha_max,feasible)
      implicit none
      real, intent(in) :: margin_initial,margin_process
      real, intent(inout) :: alpha_min,alpha_max
      logical, intent(inout) :: feasible
      real :: boundary

      if (.not.feasible) return
      if (margin_process.eq.0.0) then
        if (margin_initial.lt.0.0) feasible=.false.
      elseif (margin_process.gt.0.0) then
        boundary=-margin_initial/margin_process
        alpha_min=max(alpha_min,boundary)
      else
        boundary=-margin_initial/margin_process
        alpha_max=min(alpha_max,boundary)
      endif
    end subroutine constrain_process_margin

    real function kdm6_shared_pair_fraction(mass_rate_start,mass_rate_limited, &
         number_rate_start,number_rate_limited)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: mass_rate_start,mass_rate_limited
      real, intent(in) :: number_rate_start,number_rate_limited
      kdm6_shared_pair_fraction=1.0
      if (.not.all(ieee_is_finite([mass_rate_start,mass_rate_limited, &
          number_rate_start,number_rate_limited]))) then
        error stop 'KDM6 paired process limiter received a nonfinite rate'
      endif
      if (mass_rate_start.lt.0.0 .or. mass_rate_limited.lt.0.0 .or. &
          number_rate_start.lt.0.0 .or. number_rate_limited.lt.0.0 .or. &
          mass_rate_limited.gt.mass_rate_start .or. &
          number_rate_limited.gt.number_rate_start) then
        error stop 'KDM6 paired process limiter changed a nonnegative rate inconsistently'
      endif
      if (mass_rate_start.gt.0.0) then
        kdm6_shared_pair_fraction=min(kdm6_shared_pair_fraction, &
             mass_rate_limited/mass_rate_start)
      endif
      if (number_rate_start.gt.0.0) then
        kdm6_shared_pair_fraction=min(kdm6_shared_pair_fraction, &
             number_rate_limited/number_rate_start)
      endif
    end function kdm6_shared_pair_fraction


! Host DEN is dry-air density. Number moments and KDM6 inventories use it directly.
    subroutine kdm6(th, q, qc, qr, qi, qs, qg,             &
                    nn, nc, ni, nr, bg, diag_rhog,         &
                    den, pii, p, delz,                     &
                    delt,g, cpd, cpv, ccn0, rd, rv, t0c,   &
                    ep1, ep2, qmin,                        &
                    xls, xlv0, xlf0, den0, denr,           &
                    scale_h,                               & 
                    qnn_land_mult,                         &
                    qnn_sea_mult,                          &
                    ncmin_land,                            & 
                    ncmin_sea,                             & 
                    cliq,cice,psat,                        &
                    xland,                                 &
                    rain, rainncv,                         &
                    snow, snowncv,                         &
                    sr,                                    &
                    refl_10cm, diagflag, do_radar_ref,     &
                    graupel, graupelncv,                   &
                    itimestep,                             &
                    has_reqc, has_reqi, has_reqs,          &  
                    re_cloud, re_ice,   re_snow,           &  
                    ids,ide, jds,jde, kds,kde,             &
                    ims,ime, jms,jme, kms,kme,             &
                    its,ite, jts,jte, kts,kte              &
                    )

   implicit none

   integer                                   , intent(in   ) :: itimestep
   integer                                   , intent(in   ) ::                &
                                                    ids,ide, jds,jde, kds,kde, &
                                                    ims,ime, jms,jme, kms,kme, &
                                                    its,ite, jts,jte, kts,kte
   real                                      , intent(in   ) :: delt, g, ccn0, &
                                                                rd, rv, t0c,   &
                                                                cpd, cpv,      &
                                                                den0, qmin,    &
                                                                ep1, ep2, xls, &
                                                                xlv0, xlf0,    &
                                                               cliq, cice,    &
                                                               psat, denr,    &
                                                               scale_h,       & 
                                                                qnn_land_mult, &
                                                                qnn_sea_mult,  &
                                                               ncmin_land,    & 
                                                               ncmin_sea  
   real, dimension(ims:ime,jms:jme)          , intent(in   ) :: xland
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(in   ) :: den
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(in   ) :: pii
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(in   ) :: p
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(in   ) :: delz
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: th
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: q
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: qc
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: qi
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: qr
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: qs
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: qg
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: nn
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: nc
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: ni
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: nr
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: bg
   real, dimension(ims:ime,kms:kme,jms:jme)  , intent(inout) :: diag_rhog
   real, dimension(ims:ime,jms:jme)          , intent(inout) :: rain
   real, dimension(ims:ime,jms:jme)          , intent(inout) :: rainncv
   real, dimension(ims:ime,jms:jme)          , intent(inout) :: sr
   real, dimension(ims:ime,jms:jme), optional, intent(inout) :: snow
   real, dimension(ims:ime,jms:jme), optional, intent(inout) :: snowncv
   real, dimension(ims:ime,jms:jme), optional, intent(inout) :: graupel
   real, dimension(ims:ime,jms:jme), optional, intent(inout) :: graupelncv




   integer                                 , intent(in   ) :: has_reqc
   integer                                 , intent(in   ) :: has_reqi
   integer                                 , intent(in   ) :: has_reqs
   real, dimension(ims:ime,kms:kme,jms:jme), intent(inout) :: re_cloud
   real, dimension(ims:ime,kms:kme,jms:jme), intent(inout) :: re_ice
   real, dimension(ims:ime,kms:kme,jms:jme), intent(inout) :: re_snow



   real, dimension(ims:ime,kms:kme,jms:jme), intent(inout) :: refl_10cm
   logical                       , optional, intent(in   ) :: diagflag
   integer                       , optional, intent(in   ) :: do_radar_ref



   real, dimension(its:ite,kts:kte)   :: t
   real, dimension(its:ite,kts:kte,2) :: qci
   real, dimension(its:ite,kts:kte,3) :: nrs,nci
   real, dimension(its:ite,kts:kte,3) :: qrs
   real, dimension(its:ite,kts:kte)   :: n0so, n0go
   integer                            :: i,j,k
   logical, save :: pr67_trace_complete = .false.
   logical :: pr67_trace_this_call
   real, dimension(its:ite,kts:kte) :: brs
   real, dimension(its:ite,kts:kte) :: rhox
   integer, dimension(its:ite,kts:kte) :: progb_status
   real, dimension(its:ite,kts:kte) :: cmg



   real, dimension(kts:kte) :: qv1d 
   real, dimension(kts:kte) :: t1d
   real, dimension(kts:kte) :: p1d
   real, dimension(kts:kte) :: qr1d
   real, dimension(kts:kte) :: nr1d
   real, dimension(kts:kte) :: qs1d
   real, dimension(kts:kte) :: qg1d
   real, dimension(kts:kte) :: n0so1d, n0go1d
   real, dimension(kts:kte) :: dBZ
   real, dimension(kts:kte) :: cmg1d



   real, dimension(kts:kte) :: qc1d, nc1d, den1d
   real, dimension(kts:kte) :: qi1d, ni1d
   real, dimension(kts:kte) :: re_qc, re_qi, re_qs
   real, dimension(ims:ime,kms:kme) :: dry_density
   real :: number_value
   real :: pr87_rain_q_public,pr87_rain_n_public
   double precision :: pr87_rain_store_dq,pr87_rain_store_dn,pr87_rain_roundtrip_dn
   integer :: pr87_rain_store_adjustment,pr87_rain_store_unit,pr87_rain_store_ios
   external :: pr87_number_public_store
   integer(c_int) :: pr75_thread_before, pr75_thread_after
   integer(c_int) :: pr75_mxcsr_before, pr75_mxcsr_after
   integer :: pr75_unit, pr75_open_status
   integer :: pr76_target_unit, pr76_target_status
   logical :: number_valid

   real :: z_sum
   integer(c_int) :: pr76_mxcsr_before, pr76_mxcsr_after, pr76_thread_id
   integer :: pr76_unit, pr76_open_status

   pr76_mxcsr_before = pr76_apply_gradual(pr76_mxcsr_after, pr76_thread_id)
   open(newunit=pr76_unit, file='pr76_thread_entry.raw', status='unknown', &
        position='append', action='write', iostat=pr76_open_status)
   if (pr76_open_status == 0) then
     write(pr76_unit,'(A,2(",",Z8.8),",",I0)') 'KDM6_ENTRY', &
          pr76_mxcsr_before, pr76_mxcsr_after, pr76_thread_id
     close(pr76_unit)
   endif
   if (pidnr/=12566.37109375.or.dmr/=3.0.or. &
       lamdarmin/=961.0.or.lamdarmax/=35000.0) &
     error stop 'PR87 grouped/native rain coefficient identity mismatch'
   if (.not.all(ieee_is_finite([pidnc,dmc,lamdacmin,lamdacmax]))) &
     error stop 'PR87 nonfinite cloud coefficient identity'
   if (pidnc/=523.59881591796875.or.dmc/=3.0.or. &
       lamdacmin/=12000.0.or.lamdacmax/=500000.0) &
     error stop 'PR87 grouped/native cloud coefficient identity mismatch'
   pr67_trace_this_call = .not. pr67_trace_complete
   if (itimestep == 3) then
     call kdm6_trace_dump(1,itimestep,ids,ide,jds,jde,kds,kde, &
          ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
          delt,ccn0,scale_h,qnn_land_mult,qnn_sea_mult, &
          th,pii,den,p,delz,q,qc,qr,qi,qs,qg,nn,nc,ni,nr,bg,diag_rhog,xland)
   endif
   if (pr67_trace_this_call) then
     call kdm6_trace_dump(1,itimestep,ids,ide,jds,jde,kds,kde, &
          ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
          delt,ccn0,scale_h,qnn_land_mult,qnn_sea_mult, &
          th,pii,den,p,delz,q,qc,qr,qi,qs,qg,nn,nc,ni,nr,bg,diag_rhog,xland)
   endif

   if (itimestep .eq. 1) then 

     do j = jms,jme
       do i = ims,ime
         z_sum=0.0
         do k = kms,kme    
           z_sum = z_sum + delz(i,k,j)
           if (xland(i,j)==1) then
             if (scale_h > 0.) then
               nn(i,k,j) = ccn0*qnn_land_mult*exp(-z_sum/scale_h)
             else
               nn(i,k,j) = ccn0*qnn_land_mult
             endif
           else
             if (scale_h > 0.) then
               nn(i,k,j) = ccn0*qnn_sea_mult*exp(-z_sum/scale_h)
             else
               nn(i,k,j) = ccn0*qnn_sea_mult
             endif
           endif


         enddo
       enddo
     enddo
   endif

   do j = jts,jte
     do k = kts,kte
       do i = its,ite
         t(i,k) = th(i,k,j)*pii(i,k,j)
         if (.not. ieee_is_finite(den(i,k,j)) .or. .not. ieee_is_finite(q(i,k,j))) &
           error stop 'KDM6 invalid dry-density input'
         if (den(i,k,j) <= 0.0 .or. q(i,k,j) < 0.0) error stop 'KDM6 invalid dry-density input'
! The host contract supplies dry-air density here; retain it exactly.
         dry_density(i,k) = den(i,k,j)
         qci(i,k,1) = qc(i,k,j)
         qci(i,k,2) = qi(i,k,j)
         qrs(i,k,1) = qr(i,k,j)
         qrs(i,k,2) = qs(i,k,j)
         qrs(i,k,3) = qg(i,k,j)

         call specific_number_to_volume(nc(i,k,j), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NC number basis input'

         nci(i,k,1) = number_value

         pr75_mxcsr_before = pr75_read_fp_state(pr75_thread_before)
         call specific_number_to_volume(ni(i,k,j), dry_density(i,k), number_value, number_valid)
         pr75_mxcsr_after = pr75_read_fp_state(pr75_thread_after)
         if (i == 211 .and. j == 2 .and. k == 15) then
           open(newunit=pr76_target_unit, file='pr76_target_call.raw', status='unknown', &
                position='append', action='write', iostat=pr76_target_status)
           if (pr76_target_status == 0) then
             write(pr76_target_unit,'(A,3(",",I0),3(",",ES24.16E3),",",L1)') &
                  'TARGET_CALL', i, j, k, ni(i,k,j), dry_density(i,k), number_value, number_valid
             write(pr76_target_unit,'(A,4(",",Z8.8))') 'TARGET_BITS', &
                  pr75_mxcsr_before, pr75_mxcsr_after, transfer(ni(i,k,j),0), &
                  transfer(dry_density(i,k),0)
             write(pr76_target_unit,'(A,",",Z8.8)') 'RESULT_BITS', transfer(number_value,0)
             write(pr76_target_unit,'(A,",",I0,",",I0)') 'THREAD_IDS', &
                  pr75_thread_before, pr75_thread_after
             close(pr76_target_unit)
           endif
         endif
         if (.not. number_valid) then
           open(newunit=pr75_unit, file='pr75_native_fp.raw', status='unknown', &
                position='append', action='write', iostat=pr75_open_status)
           if (pr75_open_status == 0) then
             write(pr75_unit,'(A,",",I0,",",I0,",",I0,",",ES24.16E3,",",ES24.16E3,",",ES24.16E3,",",L1)') &
                  'NI_ADAPTER_FAILURE', i, j, k, ni(i,k,j), dry_density(i,k), number_value, &
                  number_valid
             write(pr75_unit,'(A,6(",",Z8.8))') &
                  'BITS_AND_STATE', pr75_mxcsr_before, pr75_mxcsr_after, &
                  transfer(ni(i,k,j),0), transfer(dry_density(i,k),0), &
                  transfer(number_value,0), pr75_thread_before
             write(pr75_unit,'(A,",",I0)') 'THREAD_AFTER', pr75_thread_after
             close(pr75_unit)
           endif
         endif
         if (.not. number_valid) error stop 'KDM6 invalid NI number basis input'

         nci(i,k,2) = number_value

         call specific_number_to_volume(nn(i,k,j), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NN number basis input'

         nci(i,k,3) = number_value

         call specific_number_to_volume(nr(i,k,j), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NR number basis input'

         nrs(i,k,1) = number_value
         nrs(i,k,2) = 0. 
         nrs(i,k,3) = 0. 
         brs(i,k) = bg(i,k,j)
       enddo
     enddo   
     
     
     
     
     call kdm62D(t, q(ims,kms,j), qci, qrs, nci, nrs, brs, rhox, cmg  &
                ,den(ims,kms,j)                               &
                ,p(ims,kms,j), delz(ims,kms,j)                &
                ,delt,g, cpd, cpv, ccn0, rd, rv, t0c          &
                ,ep1, ep2, qmin                               &
                ,xls, xlv0, xlf0, den0, denr                  &
                ,cliq,cice,psat                               &
                ,j                                            &
                ,itimestep                                   &
                ,xland(ims,j)                                 &
                ,ncmin_land, ncmin_sea                        & 
                ,rain(ims,j),rainncv(ims,j)                   &
                ,sr(ims,j)                                    &
                ,ids,ide, jds,jde, kds,kde                    &
                ,ims,ime, jms,jme, kms,kme                    &
                ,its,ite, jts,jte, kts,kte,n0so,n0go          &
                ,snow(ims,j),snowncv(ims,j)                &
                ,graupel(ims,j),graupelncv(ims,j)          &
                ,pr67_trace_this_call                         &
                ,progb_status                                 &
                )

     open(newunit=pr87_rain_store_unit,file='pr87_qn_public_store.raw', &
          status='unknown',position='append',action='write',iostat=pr87_rain_store_ios)
     if (pr87_rain_store_ios/=0) error stop 'PR87 rain public-store ledger open failed'
     do k = kts,kte
       do i = its,ite
         th(i,k,j) = t(i,k)/pii(i,k,j)
         qc(i,k,j) = qci(i,k,1)
         qi(i,k,j) = qci(i,k,2)
         qr(i,k,j) = qrs(i,k,1)
         qs(i,k,j) = qrs(i,k,2)
         qg(i,k,j) = qrs(i,k,3)

         call volume_number_to_specific(nrs(i,k,1), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NR number basis output'
! Quantize the completed pair, before its first public host store.
         call pr87_number_public_store(qrs(i,k,1),nrs(i,k,1),dry_density(i,k), &
              pidnr,dmr,lamdarmin,lamdarmax,pr87_rain_q_public,pr87_rain_n_public, &
              number_valid,pr87_rain_store_dq,pr87_rain_store_dn,pr87_rain_store_adjustment)
         if (.not.number_valid) then
           write(*,*) 'PR87_RAIN_PUBLIC_STORE_REJECT',itimestep,j,i,k, &
                qrs(i,k,1),nrs(i,k,1),dry_density(i,k)
           flush(6)
           error stop 'PR87 invalid continuous or unrepresentable rain public pair'
         endif
         pr87_rain_roundtrip_dn=DBLE(pr87_rain_n_public*dry_density(i,k))-DBLE(nrs(i,k,1))
         if (pr87_rain_store_adjustment/=0.or.pr87_rain_n_public/=number_value) then
           write(pr87_rain_store_unit,'(a,5i10,1p,10es25.16)',iostat=pr87_rain_store_ios) &
                'PR87_RAIN_PUBLIC_STORE',itimestep,j,i,k,pr87_rain_store_adjustment, &
                DBLE(qrs(i,k,1)),DBLE(nrs(i,k,1)),DBLE(number_value), &
                DBLE(pr87_rain_q_public),DBLE(pr87_rain_n_public), &
                DBLE(dry_density(i,k)),DBLE(delz(i,k,j)),pr87_rain_store_dq, &
                pr87_rain_store_dn,pr87_rain_roundtrip_dn
           if (pr87_rain_store_ios/=0) error stop 'PR87 rain public-store ledger write failed'
         endif
         qr(i,k,j)=pr87_rain_q_public
         number_value=pr87_rain_n_public

         nr(i,k,j) = number_value

         call volume_number_to_specific(nci(i,k,1), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NC number basis output'
         call pr87_number_public_store(qci(i,k,1),nci(i,k,1),dry_density(i,k), &
              pidnc,dmc,lamdacmin,lamdacmax,pr87_rain_q_public,pr87_rain_n_public, &
              number_valid,pr87_rain_store_dq,pr87_rain_store_dn,pr87_rain_store_adjustment)
         if (.not.number_valid) then
           write(*,*) 'PR87_CLOUD_PUBLIC_STORE_REJECT',itimestep,j,i,k, &
                qci(i,k,1),nci(i,k,1),dry_density(i,k)
           flush(6)
           error stop 'PR87 invalid continuous or unrepresentable cloud public pair'
         endif
         pr87_rain_roundtrip_dn=DBLE(pr87_rain_n_public*dry_density(i,k))-DBLE(nci(i,k,1))
         if (pr87_rain_store_adjustment/=0.or.pr87_rain_n_public/=number_value) then
           write(pr87_rain_store_unit,'(a,5i10,1p,10es25.16)',iostat=pr87_rain_store_ios) &
                'PR87_CLOUD_PUBLIC_STORE',itimestep,j,i,k,pr87_rain_store_adjustment, &
                DBLE(qci(i,k,1)),DBLE(nci(i,k,1)),DBLE(number_value), &
                DBLE(pr87_rain_q_public),DBLE(pr87_rain_n_public), &
                DBLE(dry_density(i,k)),DBLE(delz(i,k,j)),pr87_rain_store_dq, &
                pr87_rain_store_dn,pr87_rain_roundtrip_dn
           if (pr87_rain_store_ios/=0) error stop 'PR87 cloud public-store ledger write failed'
         endif
         qc(i,k,j)=pr87_rain_q_public
         number_value=pr87_rain_n_public

         nc(i,k,j) = number_value

         call volume_number_to_specific(nci(i,k,2), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NI number basis output'

         ni(i,k,j) = number_value

         call volume_number_to_specific(nci(i,k,3), dry_density(i,k), number_value, number_valid)
         if (.not. number_valid) error stop 'KDM6 invalid NN number basis output'

         nn(i,k,j) = number_value
         bg(i,k,j) = brs(i,k)
         if (progb_status(i,k) == PROGB_PSD_ACTIVE) then
           diag_rhog(i,k,j) = rhox(i,k)
         else if (progb_status(i,k) == PROGB_ABSENT) then
           diag_rhog(i,k,j) = 0.0
         else
           error stop 'KDM6 invalid ProgB status at return'
         endif
       enddo
     enddo

     close(pr87_rain_store_unit)

     if ( present (diagflag) ) then
       if (diagflag .and. do_radar_ref == 1) then
         do i = its,ite
           do k = kts,kte
             t1d(k)  = th(i,k,j)*pii(i,k,j)
             p1d(k)  = p(i,k,j)
             qv1d(k) = q(i,k,j)
             qr1d(k) = qr(i,k,j)
             nr1d(k) = nr(i,k,j)
             qs1d(k) = qs(i,k,j)
             n0so1d(k) = n0so(i,k)
             n0go1d(k) = n0go(i,k)
             qg1d(k) = qg(i,k,j)
             if (progb_status(i,k) == PROGB_PSD_ACTIVE) then
               cmg1d(k) = cmg(i,k)
             else if (progb_status(i,k) == PROGB_ABSENT) then
               cmg1d(k) = 0.0
             else
               error stop 'KDM6 invalid ProgB status at return'
             endif
           enddo
           call refl10cm_kdm6 (qv1d, qr1d, nr1d, qs1d, qg1d, n0so1d,&
                              n0go1d, t1d, p1d, dBZ, kts, kte, i, j, cmg1d)
           do k = kts, kte
             refl_10cm(i,k,j) = max(-35., dBZ(k))
           enddo
         enddo
       endif
     endif



     if (has_reqc.ne.0 .and. has_reqi.ne.0 .and. has_reqs.ne.0) then
       do i = its,ite
         do k = kts,kte
           re_qc(k) = RE_QC_BG
           re_qi(k) = RE_QI_BG
           re_qs(k) = RE_QS_BG

           t1d(k)  = th(i,k,j)*pii(i,k,j)
           den1d(k)= dry_density(i,k)
           qc1d(k) = qc(i,k,j)
           qi1d(k) = qi(i,k,j)
           qs1d(k) = qs(i,k,j)
           nc1d(k) = nci(i,k,1)/dry_density(i,k)
           ni1d(k) = nci(i,k,2)/dry_density(i,k)
         enddo

         call effectRad_kdm6(t1d, qc1d, nc1d, qi1d, ni1d, qs1d, den1d,   &
                             qmin, t0c, re_qc, re_qi, re_qs,       &
                             kts, kte, i, j)

         do k = kts,kte
           re_cloud(i,k,j) = max(RE_QC_BG,  min(re_qc(k),  50.e-6))
           re_ice(i,k,j)   = max(RE_QI_BG, min(re_qi(k), 125.e-6))
           re_snow(i,k,j)  = max(RE_QS_BG,   min(re_qs(k), 999.e-6))
         enddo
       enddo
     endif
   enddo        

   if (pr67_trace_this_call) then
     call kdm6_trace_dump(2,itimestep,ids,ide,jds,jde,kds,kde, &
          ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
          delt,ccn0,scale_h,qnn_land_mult,qnn_sea_mult, &
          th,pii,den,p,delz,q,qc,qr,qi,qs,qg,nn,nc,ni,nr,bg,diag_rhog,xland)
     pr67_trace_complete = .true.
   endif

   end subroutine kdm6

   subroutine pr87_report_graupel_consumer(site,timestep,lat,its,ite,kts,kte,qrs,bg,status)
     implicit none
     integer,intent(in) :: site,timestep,lat,its,ite,kts,kte
     real,intent(in) :: qrs(its:ite,kts:kte,3),bg(its:ite,kts:kte)
     integer,intent(in) :: status(its:ite,kts:kte)
     integer :: i,k
     do k=kts,kte
       do i=its,ite
         if (status(i,k)==PROGB_ABSENT.or.status(i,k)==PROGB_PSD_ACTIVE) cycle
         write(*,'(a,6(1x,i0),2(1x,es26.17),2(1x,z8.8))') &
              'PR87_G_CONSUMER_FAILURE',timestep,site,lat,i,k,status(i,k), &
              dble(qrs(i,k,3)),dble(bg(i,k)),transfer(qrs(i,k,3),0),transfer(bg(i,k),0)
         flush(6)
         return
       enddo
     enddo
   end subroutine pr87_report_graupel_consumer

   subroutine kdm6_trace_dump(stage,itimestep,ids,ide,jds,jde,kds,kde, &
          ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
          delt,ccn0,scale_h,qnn_land_mult,qnn_sea_mult, &
          th,pii,den,p,delz,q,qc,qr,qi,qs,qg,nn,nc,ni,nr,bg,diag_rhog,xland)
     implicit none
     integer,intent(in) :: stage,itimestep,ids,ide,jds,jde,kds,kde
     integer,intent(in) :: ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte
     real,intent(in) :: delt,ccn0,scale_h,qnn_land_mult,qnn_sea_mult
     real,intent(in) :: th(ims:ime,kms:kme,jms:jme),pii(ims:ime,kms:kme,jms:jme)
     real,intent(in) :: den(ims:ime,kms:kme,jms:jme),p(ims:ime,kms:kme,jms:jme)
     real,intent(in) :: delz(ims:ime,kms:kme,jms:jme),q(ims:ime,kms:kme,jms:jme)
     real,intent(in) :: qc(ims:ime,kms:kme,jms:jme),qr(ims:ime,kms:kme,jms:jme)
     real,intent(in) :: qi(ims:ime,kms:kme,jms:jme),qs(ims:ime,kms:kme,jms:jme)
     real,intent(in) :: qg(ims:ime,kms:kme,jms:jme),nn(ims:ime,kms:kme,jms:jme)
     real,intent(in) :: nc(ims:ime,kms:kme,jms:jme),ni(ims:ime,kms:kme,jms:jme)
     real,intent(in) :: nr(ims:ime,kms:kme,jms:jme),bg(ims:ime,kms:kme,jms:jme)
     real,intent(in) :: diag_rhog(ims:ime,kms:kme,jms:jme),xland(ims:ime,jms:jme)
     integer :: u
     character(len=32) :: path
     if (stage == 1) then
       path='kdm6_first_call_pre.raw'
       if (itimestep == 3) path='kdm6_third_call_pre.raw'
     else
       path='kdm6_first_call_post.raw'
     endif
     open(newunit=u,file=trim(path),access='stream',form='unformatted', &
          status='replace',action='write')
     write(u) 'KDM6TRC1'
     write(u) stage,itimestep,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &
               its,ite,jts,jte,kts,kte
     write(u) delt,ccn0,scale_h,qnn_land_mult,qnn_sea_mult
     write(u) 'TH      '; write(u) th
     write(u) 'PII     '; write(u) pii
     write(u) 'DEN     '; write(u) den
     write(u) 'P       '; write(u) p
     write(u) 'DELZ    '; write(u) delz
     write(u) 'Q       '; write(u) q
     write(u) 'QC      '; write(u) qc
     write(u) 'QR      '; write(u) qr
     write(u) 'QI      '; write(u) qi
     write(u) 'QS      '; write(u) qs
     write(u) 'QG      '; write(u) qg
     write(u) 'NN      '; write(u) nn
     write(u) 'NC      '; write(u) nc
     write(u) 'NI      '; write(u) ni
     write(u) 'NR      '; write(u) nr
     write(u) 'BG      '; write(u) bg
     write(u) 'DIAGRHOG'; write(u) diag_rhog
     write(u) 'XLAND   '; write(u) xland
     close(u)
   end subroutine kdm6_trace_dump




   subroutine kdm62D(t, q, qci, qrs, nci, nrs                     &
                   ,brs, rhox, cmg, den, p, delz                  &
                   ,delt,g, cpd, cpv, ccn0, rd, rv, t0c           &
                   ,ep1, ep2, qmin                                &
                   ,xls, xlv0, xlf0, den0, denr                   &
                   ,cliq,cice,psat                                &
                   ,lat                                           &
                   ,pr87_model_timestep                           &
                   ,slmsk                                         &
                   ,ncmin_land, ncmin_sea                         & 
                   ,rain,rainncv                                  &
                   ,sr                                            &
                   ,ids,ide, jds,jde, kds,kde                     &
                   ,ims,ime, jms,jme, kms,kme                     &
                   ,its,ite, jts,jte, kts,kte, n0so, n0go         &
                   ,snow,snowncv                                  &
                   ,graupel,graupelncv                            &
                   ,pr67_trace_this_call                            &
                   ,progb_status                                    &
                    )

    implicit none
   real :: cloud_evap_extent
   logical :: full_cloud_evap
   real :: pr97_q_before,pr97_c_before,pr97_extent


























































































   integer                                , intent(in   ) ::                  &
                                                   ids,ide, jds,jde, kds,kde, &
                                                   ims,ime, jms,jme, kms,kme, &
                                                   its,ite, jts,jte, kts,kte
   integer                                , intent(in   ) :: lat
   integer                                , intent(in   ) :: pr87_model_timestep
   logical                                , intent(in   ) :: pr67_trace_this_call
   real                                   , intent(in   ) :: delt
   real                                   , intent(in   ) :: g, cpd, cpv, t0c, &
                                                             den0, rd, rv,     &
                                                             ep1, ep2, qmin,   &
                                                             xls, xlv0, xlf0,  &
                                                             cliq, cice, psat, &
                                                             denr,             &
                                                             ncmin_land, ncmin_sea 
   real                                   , intent(in   ) :: ccn0
   real, dimension(ims:ime)               , intent(in   ) :: slmsk
   real, dimension(ims:ime,kms:kme)       , intent(in   ) :: p
   real, dimension(ims:ime,kms:kme)       , intent(in   ) :: delz
   real, dimension(ims:ime,kms:kme)       , intent(in   ) :: den
   real, dimension(its:ite,kts:kte)       , intent(inout) :: t
   real, dimension(its:ite,kts:kte,2)     , intent(inout) :: qci
   real, dimension(its:ite,kts:kte,3)     , intent(inout) :: qrs
   real, dimension(its:ite,kts:kte,3)     , intent(inout) :: nrs,nci
   real, dimension(its:ite,kts:kte)       , intent(inout) :: brs
   real, dimension(its:ite,kts:kte)       , intent(out) :: rhox
   integer, dimension(its:ite,kts:kte)   , intent(out) :: progb_status
   real, dimension(ims:ime,kms:kme)       , intent(inout) :: q
   real, dimension(ims:ime)               , intent(inout) :: rain
   real, dimension(ims:ime)               , intent(inout) :: rainncv
   real, dimension(ims:ime)               , intent(inout) :: sr
   real, dimension(ims:ime), optional     , intent(inout) :: snow
   real, dimension(ims:ime), optional     , intent(inout) :: snowncv
   real, dimension(ims:ime), optional     , intent(inout) :: graupel
   real, dimension(ims:ime), optional     , intent(inout) :: graupelncv




   real, dimension(its:ite,kts:kte) ::bvtg,rslopegbmax,dgbgmug1,  &
                                      bvtg1,bvtg2,bvtg3,bvtg4,g1pdgbgmg, &
                                      g1pbg,g3pbg,g4pbg,g5pbgo2
   real, dimension(its:ite,kts:kte) :: cmg,pidn0g
   real, dimension(its:ite,kts:kte) :: avtg,pvtg,precg2
   real, dimension(its:ite,kts:kte)   :: dend
   real, dimension(its:ite,kts:kte)   :: qcr
   real, dimension(its:ite,kts:kte)   :: sw
   real, dimension(its:ite,kts:kte,2) :: rh
   real, dimension(its:ite,kts:kte,3) :: qs
   real , dimension(its:ite,kts:kte,4) :: rslope, rslope2, rslope3, rslopeb,rsloped
   double precision, dimension(its:ite,kts:kte,4) :: rslopemu
   real, dimension(its:ite,kts:kte,4) :: falk, fall
   real, dimension(its:ite,kts:kte) :: falkb, fallb
   real, dimension(its:ite,kts:kte)   :: dbs,dbg
   double precision, dimension(its:ite,kts:kte,4) :: work1
   double precision, dimension(its:ite,kts:kte,4) :: terminal_velocity_mass
   double precision, dimension(its:ite,kts:kte,4) :: mass_velocity_rate
   real, dimension(its:ite,kts:kte)   :: qci_tmp
   real, dimension(its:ite,kts:kte,3) :: qrs_tmp
   real, dimension(its:ite,kts:kte,3) :: avedia
   real, dimension(its:ite,kts:kte,2) :: sigma
   real, dimension(its:ite,kts:kte)   :: rslopec,rslopec2,rslopec3,rslopecd
   double precision, dimension(its:ite,kts:kte)   :: rslopecmu
   double precision, dimension(its:ite,kts:kte)   :: n0r, n0c, n0i
   real, dimension(its:ite,kts:kte)   :: n0so, n0go
   real, dimension(its:ite,kts:kte,2)   :: falln, falkn
   double precision, dimension(its:ite,kts:kte,2)   :: workn
   double precision, dimension(its:ite,kts:kte,2) :: terminal_velocity_number
   double precision, dimension(its:ite,kts:kte,2) :: number_velocity_rate
   double precision :: step_rate
   real, dimension(its:ite,kts:kte)   :: worka, workr
   real, dimension(its:ite,kts:kte)   :: den_tmp, delz_tmp, dry_carrier_density
   real, dimension(its:ite,kts:kte) :: gas_density
   logical :: carrier_valid, step_count_valid, ice_entry_ceiling_valid, pr85_ice_valid
   logical :: pr85_g_valid
   integer, parameter :: PR87_SED_RAIN = 3
   logical :: pr87_rain_valid
   logical :: graupel_cache_valid
   real :: ice_entry_number_ceiling, ice_entry_public_minimum
   real, dimension(its:ite,kts:kte) :: nrs_tmp,nci_tmp
   real, dimension(its:ite,kts:kte)   :: lamdr_tmp, lamdc_tmp, lamdi_tmp
   real, dimension(its:ite,kts:kte)   :: falkc, work1c, work2c
   real, dimension(its:ite,kts:kte)   :: dqr,dnr
   real, dimension(its:ite,kts:kte)   :: dqi,dni
   real, dimension(its:ite,kts:kte)   :: dqs,dqg
   real, dimension(its:ite,kts:kte)   :: pcact, psaut, pgaut, pgacs,        &
                                      pigen, pcond, paacw,pracw, prevp,     &
                                      praci, piacr, pracs,                  &
                                      psacr, pseml, pgacr, pgeml, praut,    &
                                      pgmlt, psmlt, pgaci, pgacw, pgdep,    &
                                      psaci, psacw, psdep, psevp, pgevp,    &
                                      pidep,pinud,pmulcs, pmulcg, pmulrs, pmulrg
   real, dimension(its:ite,kts:kte)   :: ncevp, ncact,                      &
                                      ngeml, nseml, nccol, nrcol, nracw,    &
                                      nraut, niacr, nsacr, ngacr, nsacw,    &
                                      naacw, ngacw, nraci, nsaci, ngaci,    &
                                      nracs, ninud, nsaut, nisub,           &
                                      nmulcs, nmulcg, nmulrs, nmulrg

   real, dimension(its:ite,kts:kte)   :: braci,biacr,bracs,bsacr,           &
                                        bgacr,baacw,bsacw,bgacw,bgacs,bgaci,&
                                        bsaut,bsaci,bsdep,bgdep,bgaut,      &
                                        bsevp,bseml,bgevp,bgeml

   real, dimension(its:ite,kts:kte)   :: piacw, niacw
   real, dimension(its:ite,kts:kte)   :: xl, cpm, work2, denfac, xni, n0sfac,  &
                                         qsum
   real, dimension(its:ite,kts:kte)   :: denqrs1, denqrs2, denqrs3
   real, dimension(its:ite,kts:kte)   :: denqr1, denncr3, denqci
   real, dimension(its:ite)           :: delqrs1, delqrs2, delqrs3, delncr3
   real, dimension(its:ite)           :: delqi
   real, dimension(its:ite)           :: tstepsnow, tstepgraup
   integer :: pr67_unit, pr85_ice_unit, pr85_ice_ios
   integer :: pr85_g_unit, pr85_g_ios
   integer :: pr87_rain_unit, pr87_rain_ios
   integer :: pr85_melt_unit, pr85_melt_ios, pr85_trace_unit, pr85_trace_ios
   integer :: pr85_melt_route, pr85_freeze_unit, pr85_freeze_ios
   integer :: pr85_rf_unit, pr85_rf_ios
   double precision, dimension(kts:kte) :: pr85_ice_qrate, pr85_ice_nrate
   double precision, dimension(kts:kte) :: pr87_rain_qrate, pr87_rain_nrate
   double precision, dimension(kts:kte) :: pr85_g_qrate, pr85_g_brate
   double precision :: pr85_freeze_mass_request, pr85_freeze_number_request
   double precision :: pr85_freeze_mass_approved, pr85_freeze_number_approved
   double precision :: pr85_freeze_fraction, pr85_freeze_t_candidate
   real :: pr85_freeze_t_before, pr85_freeze_t_after
   real :: pr85_freeze_qc_before, pr85_freeze_nc_before
   real :: pr85_freeze_qi_before, pr85_freeze_ni_before
   real :: pr85_freeze_qc_after, pr85_freeze_nc_after
   real :: pr85_freeze_qi_after, pr85_freeze_ni_after
   logical :: pr85_freeze_base_valid, pr85_freeze_accepted
   logical :: pr85_freeze_ice_transient_base
   double precision :: pr85_rf_mass_request,pr85_rf_number_request,pr85_rf_volume_request
   double precision :: pr85_rf_mass_approved,pr85_rf_number_approved,pr85_rf_volume_approved
   double precision :: pr85_rf_fraction,pr85_rf_t_candidate
   real :: pr85_rf_qr_before,pr85_rf_nr_before,pr85_rf_qg_before,pr85_rf_bg_before
   real :: pr85_rf_t_before,pr85_rf_qr_after,pr85_rf_nr_after,pr85_rf_qg_after,pr85_rf_bg_after
   real :: pr85_rf_t_after
   logical :: pr85_rf_base_valid,pr85_rf_accepted
   double precision :: pr85_melt_number_request, pr85_melt_mass_request
   double precision :: pr85_melt_number_actual, pr85_melt_mass_actual
   double precision :: pr85_melt_number_residual, pr85_melt_mass_residual
   double precision :: pr85_melt_qc_delta, pr85_melt_nc_delta
   double precision :: pr85_melt_qr_delta, pr85_melt_nr_delta
   real :: pr85_melt_q_before, pr85_melt_t_before, pr85_melt_mean_mass
   real :: pr85_melt_qc_before, pr85_melt_nc_before, pr85_melt_qr_before
   real :: pr85_melt_nr_before, pr85_melt_qc_after, pr85_melt_nc_after
   real :: pr85_melt_qr_after, pr85_melt_nr_after, pr85_melt_requested_q
   real :: pr85_melt_qs_after, pr85_melt_t_after
   double precision :: pr85_melt_qs_candidate, pr85_melt_t_candidate
   real :: pr85_trace_qi, pr85_trace_qs, pr85_trace_ni, pr85_trace_diameter
   real :: pr85_trace_t_before
   double precision :: pr85_trace_removed_qi, pr85_trace_snow_gain
   logical :: pr85_melt_accepted
   interface
      subroutine pr85_kdm6_paired_sediment_column(kts,kte,cell_i,lat,substep,dt,mstep, &
           dry_density,delz,mass_rate,second_rate,qstate,second_state,mode,q_active_min, &
           second_active_min,density_min,density_max,approved_q_rate,approved_second_rate, &
           budget_unit,trace,valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)
         integer, intent(in) :: kts,kte,cell_i,lat,substep,mstep,budget_unit
         real, intent(in) :: dt,dry_density(kts:kte),delz(kts:kte)
         double precision, intent(in) :: mass_rate(kts:kte),second_rate(kts:kte)
         real, intent(inout) :: qstate(kts:kte),second_state(kts:kte)
         integer, intent(in) :: mode
         real, intent(in) :: q_active_min,second_active_min,density_min,density_max
         double precision, intent(out) :: approved_q_rate(kts:kte),approved_second_rate(kts:kte)
         logical, intent(in) :: trace
         logical, intent(out) :: valid
         real, intent(in) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max
      end subroutine pr85_kdm6_paired_sediment_column
   end interface
   external :: pr85_kdm6_subthreshold_melt
   external :: pr85_kdm6_freezing_packet
   external :: pr85_kdm6_rain_freezing_packet
   real(kind=8) :: pr89_rf_gamma
   real(kind=8) :: pr89_rf_rain_min,pr89_rf_rain_max
   integer :: pr89_rf_attempt,pr89_rf_failure_reason
   logical :: pr89_rf_next_valid
   external :: pr85_kdm6_psd_bound_number
   real                               :: gfac, sfac
   real, dimension(its:ite,kts:kte)   :: difa
   double precision   :: pinuc,ninuc




   integer                            :: kte_in



   real,    dimension(its:ite)        :: tvec1
   integer, dimension(its:ite)        :: mnstep, numndt
   integer, dimension(its:ite)        :: mstep, numdt
   integer, dimension(its:ite)        :: mstep_i, numdt_i
   logical, dimension(its:ite)        :: flgcld
   logical, dimension(its:ite,kts:kte) :: rain_full_evap_pending
   logical, dimension(its:ite,kts:kte) :: ice_full_sublimation_pending
   integer, dimension(its:ite,kts:kte) :: ice_extinction_cause
   real, dimension(its:ite,kts:kte) :: ice_sublimation_raw_pidep
   real, dimension(its:ite,kts:kte) :: ice_sublimation_capped_pidep
   real, dimension(its:ite,kts:kte) :: ice_sublimation_q_before,ice_sublimation_n_before
   integer, dimension(its:ite,kts:kte) :: ice_sublimation_event_count
   real :: pr87_ice_raw_pidep_before_caps
   real                               :: temp
   real                               :: holdc, holdci
   real, dimension(its:ite,kts:kte)   :: vt2g
   double precision                   :: coeres, acrfac, vt2r, vt2s,vt2i,      &
                                         pfrzdtr, nfrzdtr, pfrzdtc, nfrzdtc 
   real                               :: factor, source, value, supice,xlwork2
   real                               :: rain_bg_fixed,rain_bg_process
   real                               :: rain_t_fixed,rain_t_process
   real                               :: rain_process_alpha,rain_aut_alpha
   real, dimension(5)                 :: rain_aut_q_process,rain_q_process_request
   real, dimension(5)                 :: rain_ng_q_process,rain_g_q_process
   real, dimension(3)                 :: rain_aut_n_process,rain_n_process_request
   real, dimension(3)                 :: rain_ng_n_process,rain_g_n_process
   real, dimension(5)                 :: rain_q_before,rain_ng_aut_q_fixed
   real, dimension(3)                 :: rain_n_before,rain_ng_aut_n_fixed
   real                               :: rain_bg_before,rain_t_before,rain_qv_before
   real                               :: rain_ng_aut_bg_fixed,rain_ng_aut_t_fixed,rain_ng_aut_qv_fixed
   real                               :: rain_ng_alpha,rain_g_alpha
   real                               :: rain_ng_bg_process,rain_g_bg_process
   real                               :: rain_ng_t_process,rain_g_t_process
   real                               :: rain_ng_qv_process,rain_g_qv_process
   real                               :: rain_qv_stage,rain_qv_after
   real                               :: rain_bg_after,rain_t_after,rain_ccn3_after
   real                               :: rain_ccn3_before,rain_n_ccn_transfer
   real, dimension(5)                 :: rain_q_after
   real, dimension(3)                 :: rain_n_after
   real                               :: rain_bg_process_request,rain_t_process_request
   real                               :: rain_pgdep_bg_rate,rain_pracs_bg_rate
   real                               :: rain_pgaci_bg_rate,rain_paacw_bg_rate
   real                               :: rain_piacr_bg_rate,rain_praci_bg_rate
   real                               :: rain_psacr_bg_rate,rain_pgacr_bg_rate
   logical                            :: rain_bg_rates_feasible,rain_bg_rate_valid
   real, dimension(5)                  :: rain_q_fixed,rain_q_process
   real, dimension(3)                  :: rain_n_fixed,rain_n_process
   real, dimension(5)                  :: rain_warm_q_process,rain_warm_q_after
   real, dimension(3)                  :: rain_warm_n_process,rain_warm_n_after
   real, dimension(16)                 :: rain_warm_rate_base,rain_warm_rate_trial
   real                               :: rain_warm_bg_process,rain_warm_t_process
   real                               :: rain_warm_qv_process,rain_warm_alpha
   real                               :: rain_warm_bg_after,rain_warm_t_after,rain_warm_qv_after
   real                               :: rain_warm_xlf,rain_warm_xlwork2
   integer                            :: rain_warm_retry
   logical                            :: rain_warm_feasible,rain_warm_state_valid
   logical                            :: rain_warm_rate_noop,rain_warm_state_noop
   logical                            :: rain_warm_abort
   integer                            :: pr85_warm_unit,pr85_warm_ios,rain_warm_search_status
   real, dimension(its:ite,kts:kte,10) :: rain_pair_rate_start
   real, dimension(41) :: rain_composite_rate_base
   real :: rain_ng_alpha_initial,rain_aut_alpha_initial,rain_g_alpha_initial
   real :: rain_composite_gamma
   integer :: rain_composite_retry,rain_composite_rate_index
   integer :: pr87_ice_sublimation_extinctions,pr87_ice_sublimation_unit
   integer :: pr87_ice_sublimation_ios
   real :: pr87_ice_sublimation_n_preclear,pr87_ice_sublimation_dn
   logical :: rain_composite_valid
   real :: pr87_gmelt_q_fixed(5),pr87_gmelt_q_process(5),pr87_gmelt_q_after(5)
   real :: pr87_gmelt_n_fixed(3),pr87_gmelt_n_process(3),pr87_gmelt_n_after(3)
   real :: pr87_gmelt_bg_fixed,pr87_gmelt_bg_process,pr87_gmelt_bg_after
   real :: pr87_gmelt_t_fixed,pr87_gmelt_t_process,pr87_gmelt_t_after,pr87_gmelt_alpha
   real :: pr87_gmelt_t_ratio,pr87_gmelt_gfac_product
   double precision :: pr87_gmelt_bg_delta64,pr87_gmelt_rate64
   double precision :: pr87_gmelt_mass_residual,pr87_gmelt_volume_residual
   double precision :: pr87_gmelt_number_residual,pr87_gmelt_temperature_residual
   logical :: pr87_gmelt_feasible,pr87_gmelt_endpoint_valid,pr87_gmelt_base_valid
   integer :: pr87_gmelt_search_status,pr87_gmelt_failure_reason
   integer :: pr87_gmelt_unit,pr87_gmelt_ios
   logical                            :: rain_process_feasible,rain_stored_state_feasible
   logical                            :: rain_composite_stored_noop
   logical                            :: rain_aut_feasible,rain_aut_base_valid
   logical                            :: rain_ng_feasible,rain_ng_base_valid
   integer                            :: rain_process_search_status,rain_aut_search_status
   integer                            :: rain_ng_search_status
   integer                            :: pr85_cold_unit,pr85_cold_ios
   integer :: pr89_cold_unit,pr89_cold_ios,pr89_cold_transactions
   integer :: pr89_cold_group,pr89_cold_stage
   real(kind=8) :: pr89_cold_water(2,3,3),pr89_cold_weight
   integer :: pr90_cold_i,pr90_cold_unit,pr90_cold_ios
   integer :: pr90_cold_transactions(its:ite)
   real(kind=8) :: pr90_cold_water(2,3,3,its:ite)
   real(kind=8) :: pr89_cold_q(5),pr89_cold_qv,pr89_cold_alpha,pr89_cold_scale
   real(kind=8) :: pr89_cold_signed,pr89_cold_half_l1
   integer                            :: pr87_reason_unit,pr87_reason_ios
   integer                            :: pr87_aut_reason,pr87_aut_vapor_reason
   integer                            :: pr87_g_reason,pr87_g_vapor_reason
   logical                            :: pr87_aut_endpoint_valid,pr87_g_endpoint_valid
   real                               :: pr87_endpoint_qv,pr87_mass_specific
   integer                            :: pr85_psd_unit,pr85_psd_ios
   integer                            :: pr85_cutoff_unit,pr85_cutoff_ios
   integer                            :: pr85_cutoff_mask,pr85_cutoff_status_before
   real, dimension(5)                  :: pr85_cutoff_q_before,pr85_cutoff_q_after
   real, dimension(3)                  :: pr85_cutoff_n_before,pr85_cutoff_n_after
   real                               :: pr85_cutoff_bg_before,pr85_cutoff_bg_after
   real                               :: pr85_cutoff_t_before,pr85_cutoff_t_after
   real                               :: pr85_cutoff_qv_before,pr85_cutoff_qv_after
   real                               :: pr85_psd_legacy,pr85_psd_directed,pr85_psd_before
   real(8)                            :: pr85_psd_exact_min,pr85_psd_exact_max
   logical                            :: pr85_psd_valid,pr85_psd_native_available
   logical :: pr93_ice_pair_valid,pr93_ice_ng_valid,pr93_ice_direct_repair
   integer :: pr93_ice_k,pr93_ice_ios
   logical, external :: pr93_kdm6_pair_in_cone
   real(8) :: pr93_ice_min,pr93_ice_max
   real(8) :: pr93_ice_ng_min,pr93_ice_ng_max

   real                               :: cpmcal, xlcal, lamdac, diffus, &
                                         viscos, xka, venfac, conden, diffac,  &
                                         x, y, z, a, b, c, d, e,               &
                                         ndt, qdt, holdrr, holdrs, holdrg,     &
                                         supcol, supcolt, pvt, supsat,         &
                                         dtcld, xmi, eacsi, satdt, qimax,      &
                                         diameter, xni0, roqi0,                &
                                         fallsum, fallsum_qsi, fallsum_qg,     &
                                         egs, eacgi, coecol,                   &
                                         taucon, lencon, lenconcr,             &
                                         xlf,                                  &
                                         alpha1,alpha2, delta2, delta3

   integer                            :: i, j, k, mstepmax,mstepmax_i,         &
                                         iprt, latd, lond, loop, loops, ifsat, &
                                         n, idim, kdim



   real                               :: dldti, xb, xai, tr, xbi, xa, hvap,    &
                                         cvap, hsub, dldt, ttp




   real,parameter                      :: fac_evap = 1.0

   real                                :: ncmin





   cpmcal(x) = cpd*(1.-max(x,qmin))+max(x,qmin)*cpv
   xlcal(x) = xlv0-xlv1*(x-t0c)








   lamdac(x,y,z)= exp(log(((pidnc*z)/(x*y)))*(1./dmc))




   diffus(x,y) = 8.794e-5 * exp(log(x)*(1.81)) / y   
   viscos(x,y) = 1.496e-6 * (x*sqrt(x)) /(x+120.)/y  
   xka(x,y)    = 1.414e3*viscos(x,y)*y
   diffac(a,b,c,d,e) = d*a*a/(xka(c,d)*rv*c*c)+1./(e*diffus(c,b))
   venfac(a,b,c) = exp(log((viscos(b,c)/diffus(b,a)))*((.3333333)))            &
                   /sqrt(viscos(b,c))*sqrt(sqrt(den0/c))
   conden(a,b,c,d,e) = (max(b,qmin)-c)/(1.+d*d/(rv*e)*c/(a*a))

   idim = ite-its+1
   kdim = kte-kts+1

   kte_in = kte
   call liquid_begin(its,ite)
   call pr77_scan_entry_state(qci,qrs,nrs,nci,brs,its,ite,kts,kte,lat)
   call validate_kdm6_species_states(qci,qrs,nrs,nci,brs)
   do k = kts, kte
     do i = its, ite
       qci(i,k,1) = max(qci(i,k,1),0.0)
       qrs(i,k,1) = max(qrs(i,k,1),0.0)
       qci(i,k,2) = max(qci(i,k,2),0.0)
       qrs(i,k,2) = max(qrs(i,k,2),0.0)
       qrs(i,k,3) = max(qrs(i,k,3),0.0)
       nrs(i,k,1) = max(nrs(i,k,1),0.0)
       nrs(i,k,2) = max(nrs(i,k,2),0.0)
       nrs(i,k,3) = max(nrs(i,k,3),0.0)
       nci(i,k,1) = max(nci(i,k,1),0.0)
       nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)


! ProgB supplies density only when its status is active.
       brs(i,k) = max(brs(i,k),0.0)
     enddo
   enddo

! PR85 density bridge: DEN is dry-air density; gas density is reconstructed with Q.
   do k = kts,kte
     do i = its,ite
       call dry_to_gas_density(den(i,k), q(i,k), gas_density(i,k), carrier_valid)
       if (.not. carrier_valid) error stop 'KDM6 invalid dry-to-gas density conversion'
       dry_carrier_density(i,k) = den(i,k)
       call pr84_ice_entry_ceiling(qci(i,k,2), dry_carrier_density(i,k), lamdaimin, &
                                   dmi, pidni, ice_entry_number_ceiling, ice_entry_ceiling_valid, &
                                   ice_entry_public_minimum)
       if (.not. ice_entry_ceiling_valid) error stop 'KDM6 invalid ice entry number ceiling'
       nci(i,k,2) = min(max(nci(i,k,2),0.0), ice_entry_number_ceiling)
       dend(i,k) = dry_carrier_density(i,k)
     enddo
   enddo



   do i = its,ite
     if(slmsk(i).eq.2) then 
        ncmin = ncmin_sea
     else
       ncmin = ncmin_land
     endif
   enddo








   do k = kts,kte_in
     do i = its,ite
       cpm(i,k) = cpmcal(q(i,k))
       xl(i,k) = xlcal(t(i,k))
     enddo
   enddo

   qcr(:,:) = 0.0
   do i = its,ite
     if(slmsk(i).eq.2) then      
       qcr(i,:) = qc0
     else
       qcr(i,:) = qc1
     endif
   enddo

   do k = kts,kte
     do i = its,ite
       delz_tmp(i,k) = delz(i,k)
       den_tmp(i,k) = dry_carrier_density(i,k)
     enddo
   enddo



   do i = its,ite
     rainncv(i) = 0.
     if(present(snowncv) .and. present(snow)) snowncv(i) = 0.
     if(present (graupelncv) .and. present(graupel)) graupelncv(i) = 0.
     sr(i) = 0.



     tstepsnow(i) = 0.
     tstepgraup(i) = 0.
   enddo



   loops = max(nint(delt/dtcldcr),1)
   dtcld = delt/loops
   if(delt.le.dtcldcr) dtcld = delt
   pr89_cold_water=0.0d0
   pr90_cold_water=0.0d0
   pr90_cold_transactions=0
   pr89_cold_transactions=0
   open(newunit=pr89_cold_unit,file='pr89_kdm6_cold_summary.raw', &
        form='formatted',status='unknown',position='append',action='write', &
        iostat=pr89_cold_ios)
   if (pr89_cold_ios.ne.0) error stop 'PR89 cold summary open failed'
   write(pr89_cold_unit,'(a)',iostat=pr89_cold_ios) &
        '# PR89_KDM6_COLD_SUMMARY v1 step,lat,loops,cell_transactions,raw_cell_rows,unrecorded_transactions; '// &
        'group-major NG,AUT,G; stage-major proposed,applied,deferred; each stage signed,half-L1; '// &
        'units kg m-2 SUM_COLUMNS; weight=DEN*DELZ; half-L1=0.5*sum(abs(Q(5)),abs(QV))*DEN*DELZ; '// &
        'diagnostic request activity, not reaction throughput; no grid-area/global kg'
   if (pr89_cold_ios.ne.0) error stop 'PR89 cold summary header failed'

   open(newunit=pr85_cold_unit,file='pr85_kdm6_cold_budget.raw', &
        form='formatted',status='unknown',position='append',action='write', &
        iostat=pr85_cold_ios)
   if (pr85_cold_ios.ne.0) error stop 'PR85 cold budget open failed'
   write(pr85_cold_unit,'(a)',iostat=pr85_cold_ios) &
        '# PR85_KDM6_COLD fields: i,lat,k,loop,ngSearchStatus,autSearchStatus,gSearchStatus,compositeRetry,storedNoop; '// &
        'then dtcld,rhoDry,compositeGamma,scaledRates(41) REAL32,alphaNG,alphaAUT,alphaG; '// &
        'Qbefore(5),QafterNG_AUT(5),QGrequest(5),Qafter(5); Nbefore(3),NafterNG_AUT(3),NGrequest(3),Nafter(3); '// &
        'BGbefore,BGafterNG_AUT,BGrequest,BGafter; Tbefore,TafterNG_AUT,TGrequest,Tafter; '// &
        'QVbefore,QVafterNG_AUT,QVGrequest,QVafter; CCN3before,CCN3transfer,CCN3after; '// &
        'NG proposal/approved/withheld: Q(5),N(3),BG,T,QV; AUT proposal/approved/withheld: Q(5),N(3),BG,T,QV; '// &
        'G proposal/approved/withheld: Q(5),N(3),BG,T,QV; '// &
        'stored-minus-approved R32 residuals Q(5),N(3),CCN3,BG,T,QV; Q kg/kgdry, N #/m3, B m3/kgdry, QV kg/kgdry, T K'
   if (pr85_cold_ios.ne.0) error stop 'PR85 cold budget header failed'
   if (pr67_trace_this_call) then
     open(newunit=pr87_reason_unit,file='pr87_admission_reason.raw', &
          form='formatted',status='unknown',position='append',action='write', &
          iostat=pr87_reason_ios)
     if (pr87_reason_ios.ne.0) error stop 'PR87 admission reason open failed'
     write(pr87_reason_unit,'(a)',iostat=pr87_reason_ios) &
          '# PR87_ADMISSION group,i,lat,k,loop,status,endpoint_reason,vapor_reason,full_evap_pending,pre_composite_alpha,'// &
          'mass_activity_kg_per_kgdry,rhoDry_kg_m3,DELZ_m; endpoint_reason codes: '// &
          '0 VALID,1 BADINPUT,2 DONORNEGATIVE,3 ORPHAN,4 CUTOFF,5 PSDCLOUD,6 RAIN,7 ICE,'// &
          '8 TEMPERATURE,9 BULKDENSITY; vapor_reason 10=NEGATIVE_OR_NONFINITE_VAPOR; '// &
          'first failed FULL-proposal endpoint check, not a unique active-bound certificate; '// &
          'mass is half-L1 Q+QV proxy'
     if (pr87_reason_ios.ne.0) error stop 'PR87 admission reason header failed'
   endif
   open(newunit=pr85_warm_unit,file='pr85_kdm6_warm_budget.raw', &
        form='formatted',status='unknown',position='append',action='write', &
        iostat=pr85_warm_ios)
   if (pr85_warm_ios.ne.0) error stop 'PR85 warm budget open failed'
   write(pr85_warm_unit,'(a)',iostat=pr85_warm_ios) &
        '# PR85_KDM6_WARM i,lat,k,loop,searchStatus,retry,progbStatus,rateNoop,stateNoop; '// &
        'retry 0=full helper fraction,1-32=adjacent REAL32 steps downward,33-56=halving; '// &
        'dtcld,rhoDry,cpm,xl,xlf,rhox,alpha; '// &
        'postcapPrimitiveRates(16),scaledREAL32PrimitiveRates(16); '// &
        'Qbefore(5),Qafter(5),Nbefore(3),Nafter(3),BGbefore,BGafter,Tbefore,Tafter,QVbefore,QVafter,CCN3before,CCN3after; '// &
        'requestedPostcapQ(5),requestedPostcapN(3),requestedBG,T,QV; '// &
        'admittedAlphaQ(5),N(3),BG,T,QV; storedDeltaQ(5),N(3),BG,T,QV; '// &
        'storedMinusAdmittedQ(5),N(3),BG,T,QV; units Q/QV kg/kgdry, N #/m3, B m3/kgdry, T K, rates per second'
   if (pr85_warm_ios.ne.0) error stop 'PR85 warm budget header failed'
   open(newunit=pr85_cutoff_unit,file='pr85_kdm6_cutoff_budget.raw', &
        form='formatted',status='unknown',position='append',action='write', &
        iostat=pr85_cutoff_ios)
   if (pr85_cutoff_ios.ne.0) error stop 'PR85 cutoff budget open failed'
   write(pr85_cutoff_unit,'(a)',iostat=pr85_cutoff_ios) &
        '# PR85_KDM6_CUTOFF row order: i,lat,k,loop,thresholdMask; '// &
        'rhoDry,qmin,qcrmin; '// &
        'Qbefore(5),Qafter(5),Nbefore(3),Nafter(3),Bbefore,Bafter,Tbefore,Tafter,QVbefore,QVafter; '// &
        'progbBefore,progbAfter; thresholdMask bits 1=QC,2=QI,4=QR,8=QS,16=QG when at/below cutoff; '// &
        'Q kg/kgdry, N #/m3, B m3/kgdry, rho kg/m3, T K, QV kg/kgdry; '// &
        'rows only when the existing qmin/qcrmin cleanup changes Q/N/B state'
   if (pr85_cutoff_ios.ne.0) error stop 'PR85 cutoff budget header failed'
   pr85_psd_unit=-1
     open(newunit=pr85_psd_unit,file='pr85_kdm6_psd_boundary.raw', &
          form='formatted',status='unknown',position='append',action='write', &
          iostat=pr85_psd_ios)
     if (pr85_psd_ios.ne.0) error stop 'PR85 PSD boundary ledger open failed'
     write(pr85_psd_unit,'(a)',iostat=pr85_psd_ios) &
          '# PR85_KDM6_PSD_BOUNDARY species,stage,i,lat,k,side,Q,rhoDry,lambdaMin,lambdaMax,Nbefore,Nnative,Ndirected; '// &
          'nativeDelta,storageCorrection,exactNmin,exactNmax,legacyAvailable; '// &
          'Q kg/kgdry, rho kg/m3, lambda m-1, N #/m3; unavailable native numeric fields are zero'
     if (pr85_psd_ios.ne.0) error stop 'PR85 PSD boundary ledger header failed'
   write(pr85_psd_unit,'(a,2i10)',iostat=pr85_psd_ios) &
        '# PR90_KDM6_PSD_BOUNDARY_CONTEXT timestep,lat',pr87_model_timestep,lat
   if (pr85_psd_ios.ne.0) error stop 'PR90 PSD boundary context failed'

   do loop = 1,loops

     if (pr67_trace_this_call) then
       open(newunit=pr85_trace_unit,file='pr85_ice_transition_branch.raw', &
            form='formatted',status='unknown',position='append',action='write', &
            iostat=pr85_trace_ios)
       if (pr85_trace_ios.ne.0) error stop 'PR85 transition trace open failed'
       write(pr85_trace_unit,'(a)',iostat=pr85_trace_ios) &
            '# PR85_ICE_TRANSITION: rows follow a per-loop KDM6 reach marker; '// &
            'event fields i,lat,k,loop,dtcld,Tbefore,Tafter,Dm,preQI,preQS,preNI,executedQI,removedQI, '// &
            'storedSnowGain,postQI,postQS,postNI'
       if (pr85_trace_ios.ne.0) error stop 'PR85 transition trace header failed'
       write(pr85_trace_unit,'(a,6i8,1p,1es24.16)',iostat=pr85_trace_ios) &
            'PR85_ICE_TRANSITION_LOOP',loop,lat,its,ite,kts,kte,dtcld
       if (pr85_trace_ios.ne.0) error stop 'PR85 transition loop marker failed'
     endif

     do i = its,ite
       mstep(i) = 1
       mstep_i(i) = 1
       mnstep(i) = 1
       flgcld(i) = .true.
     enddo

     do k = kts, kte
       call vsrec( tvec1(its), gas_density(its,k), ite-its+1)
       do i = its, ite
         tvec1(i) = tvec1(i)*den0
       enddo
       call vssqrt( denfac(its,k), tvec1(its), ite-its+1)
     enddo





     hsub = xls
     hvap = xlv0
     cvap = cpv
     ttp = t0c+0.01
     dldt = cvap-cliq
     xa = -dldt/rv
     xb = xa+hvap/(rv*ttp)
     dldti = cvap-cice
     xai = -dldti/rv
     xbi = xai+hsub/(rv*ttp)

     do k = kts,kte_in
       do i = its,ite
         tr = ttp/t(i,k)
         qs(i,k,1) = psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
         qs(i,k,1) = min(qs(i,k,1),0.99*p(i,k))
         qs(i,k,1) = ep2*qs(i,k,1)/(p(i,k)-qs(i,k,1))
         qs(i,k,1) = max(qs(i,k,1),qmin)
         rh(i,k,1) = max(q(i,k)/qs(i,k,1),qmin)
         sw(i,k) = (rh(i,k,1)-1.)*100.
         tr=ttp/t(i,k)
         if(t(i,k).lt.ttp) then
           qs(i,k,2) = psat*exp(log(tr)*(xai))*exp(xbi*(1.-tr))
         else
           qs(i,k,2) = psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
         endif
         qs(i,k,2) = min(qs(i,k,2),0.99*p(i,k))
         qs(i,k,2) = ep2*qs(i,k,2)/(p(i,k)-qs(i,k,2))
         qs(i,k,2) = max(qs(i,k,2),qmin)
         rh(i,k,2) = max(q(i,k)/qs(i,k,2),qmin)
       enddo
     enddo





      do k = kts, kte
        do i = its, ite
          bvtg(i,k) =0.
          rslopegbmax(i,k) =0.
          dgbgmug1(i,k) =0.
          bvtg1(i,k) =0.
          bvtg2(i,k) =0.
          bvtg3(i,k) =0.
          bvtg4(i,k) =0.
          g1pdgbgmg(i,k) =0.
          g1pbg(i,k) =0.
          g3pbg(i,k) =0.
          g4pbg(i,k) =0.
          g5pbgo2(i,k) =0.
          cmg(i,k) =0.
          pidn0g(i,k) =0.
          avtg(i,k) =0.
          pvtg(i,k) =0.
          precg2(i,k) =0.
          rhox(i,k) =0.
          biacr(i,k) =0.
          baacw(i,k) =0.
          bsacr(i,k) =0.
          braci(i,k) =0.
          bracs(i,k) =0.
          bsaci(i,k) =0.
          bsaut(i,k) =0.
          bgaci(i,k) =0.
          bgacr(i,k) =0.
          bgacs(i,k) =0.
          bgaut(i,k) =0.
          bgdep(i,k) =0.
          bsdep(i,k) =0.
          bsevp(i,k) =0.
          bseml(i,k) =0.
          bgevp(i,k) =0.
          bgeml(i,k) =0.
          prevp(i,k) = 0.
          rain_full_evap_pending(i,k) = .false.
          ice_full_sublimation_pending(i,k) = .false.
          ice_extinction_cause(i,k) = 0
          ice_sublimation_raw_pidep(i,k) = 0.0
          ice_sublimation_capped_pidep(i,k) = 0.0
          ice_sublimation_q_before(i,k) = 0.0
          ice_sublimation_n_before(i,k) = 0.0
          ice_sublimation_event_count(i,k) = 0
          psdep(i,k) = 0.
          pgdep(i,k) = 0.
          praut(i,k) = 0.
          psaut(i,k) = 0.
          nsaut(i,k) = 0.
          pgaut(i,k) = 0.
          pracw(i,k) = 0.
          praci(i,k) = 0.
          piacr(i,k) = 0.
          psaci(i,k) = 0.
          psacw(i,k) = 0.
          pracs(i,k) = 0.
          psacr(i,k) = 0.
          pgacw(i,k) = 0.
          paacw(i,k) = 0.
          pgaci(i,k) = 0.
          pgacr(i,k) = 0.
          pgacs(i,k) = 0.
          pigen(i,k) = 0.
          pidep(i,k) = 0.
          nisub(i,k) = 0.
          niacw(i,k) = 0.
          piacw(i,k) = 0.
          pcond(i,k) = 0.
          psmlt(i,k) = 0.
          pgmlt(i,k) = 0.
          pseml(i,k) = 0.
          pgeml(i,k) = 0.
          psevp(i,k) = 0.
          pgevp(i,k) = 0.
          pcact(i,k) = 0.
          falk(i,k,1) = 0.
          falk(i,k,2) = 0.
          falk(i,k,3) = 0.
          fall(i,k,1) = 0.
          fall(i,k,2) = 0.
          fall(i,k,3) = 0.
          falkc(i,k) = 0.
          falln(i,k,1) =0.
          falln(i,k,2) =0.
          falkn(i,k,1) =0.
          falkn(i,k,2) =0.
          falkb(i,k) = 0.
          fallb(i,k) = 0.
          xni(i,k) = 1.e3
          nsacw(i,k) = 0.
          ngacw(i,k) = 0.
          naacw(i,k) = 0.
          niacr(i,k) = 0.
          nsacr(i,k) = 0.
          ngacr(i,k) = 0.
          nseml(i,k) = 0.
          ngeml(i,k) = 0.
          nracw(i,k) = 0.
          nccol(i,k) = 0.
          nrcol(i,k) = 0.
          ncact(i,k) = 0.
          nraut(i,k) = 0.
          ncevp(i,k) = 0.
          falk(i,k,4) = 0.
          fall(i,k,4) = 0.
          pmulcs(i,k) =0.
          pmulcg(i,k) =0.
          pmulrs(i,k) =0.
          pmulrg(i,k) =0.
          nmulcs(i,k) =0.
          nmulcg(i,k) =0.
          nmulrs(i,k) =0.
          nmulrg(i,k) =0.
          nraci(i,k) = 0.
          nsaci(i,k) = 0.
          ngaci(i,k) = 0.
          nracs(i,k) = 0.
          ninud(i,k) = 0.
          pinud(i,k) = 0.
        enddo
      enddo

      do k = kts, kte
        do i = its, ite
          if(qci(i,k,1).le.qmin .or. nci(i,k,1).le.ncmin ) then
            rslopec(i,k) = rslopecmax
            rslopec2(i,k) = rslopec2max
            rslopec3(i,k) = rslopec3max
            rslopecmu(i,k) = rslopecmmax
            rslopecd(i,k) = rslopecdmax  
          else
            rslopec(i,k) = 1./lamdac(qci(i,k,1),dry_carrier_density(i,k),nci(i,k,1))
            rslopec2(i,k) = (rslopec(i,k))*rslopec(i,k)
            rslopec3(i,k) = (rslopec2(i,k))*rslopec(i,k)
            rslopecmu(i,k) =DBLE(rslopec(i,k))**muc
            rslopecd(i,k) = (rslopec(i,k))**dmc
          endif
        enddo
      enddo




      do k = kts, kte
        do i = its, ite
          qrs_tmp(i,k,1) = qrs(i,k,1)
          qrs_tmp(i,k,2) = qrs(i,k,2)
          qrs_tmp(i,k,3) = qrs(i,k,3)
          qci_tmp(i,k) = qci(i,k,2)
          nci_tmp(i,k) = nci(i,k,2)
          nrs_tmp(i,k) = nrs(i,k,1)
        enddo
      enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)
   call pr87_report_graupel_consumer(1,pr87_model_timestep,lat, &
        its,ite,kts,kte,qrs_tmp,brs,progb_status)


   call pr77_scan_slope_state(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp,its,ite,kts,kte,lat, &
        'KDM62D_SLOPE_01')
   call validate_kdm6_slope_states(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp)
   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,terminal_velocity_mass,terminal_velocity_number,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax,progb_status)
   call kdm6_velocity_rates(terminal_velocity_mass,terminal_velocity_number, &
                            delz,mass_velocity_rate,number_velocity_rate, &
                            ims,ime,kms,kme,its,ite,kts,kte)




      mstepmax = 1
      mstepmax_i = 1
      numdt = 1
      numdt_i = 1
      do k = kte, kts, -1
        do i = its, ite
          step_rate = max(mass_velocity_rate(i,k,1),number_velocity_rate(i,k,1), &
                          mass_velocity_rate(i,k,2),mass_velocity_rate(i,k,3))
          call checked_substep_count(step_rate, dtcld, numdt(i), step_count_valid)
          if (.not. step_count_valid) then
            write(*,*) 'PR71_STEP_COUNT_REJECT i,k,rate,dt=', i, k, step_rate, dtcld
            error stop 'invalid PR71 KDM6 substep count'
          endif
          step_rate = max(mass_velocity_rate(i,k,4),number_velocity_rate(i,k,2))
          call checked_substep_count(step_rate, dtcld, numdt_i(i), step_count_valid)
          if (.not. step_count_valid) then
            write(*,*) 'PR71_STEP_COUNT_REJECT_ICE i,k,rate,dt=', i, k, step_rate, dtcld
            error stop 'invalid PR71 KDM6 ice substep count'
          endif
          if(numdt(i).ge.mstep(i)) mstep(i) = numdt(i)
          if(numdt_i(i).ge.mstep_i(i)) mstep_i(i) = numdt_i(i)
        enddo
      enddo

      do i = its, ite
        if(mstepmax.le.mstep(i)) mstepmax = mstep(i)
        if(mstepmax_i.le.mstep_i(i)) mstepmax_i = mstep_i(i)
      enddo

      pr87_rain_unit = 0
      pr87_rain_ios = 0
      open(newunit=pr87_rain_unit,file='pr87_rain_sedimentation_budget.raw', &
           form='formatted',status='unknown',position='append',action='write',iostat=pr87_rain_ios)
      if (pr87_rain_ios /= 0) error stop 'PR87 rain sedimentation ledger open failed'
      write(pr87_rain_unit,'(a)',iostat=pr87_rain_ios) &
        '# PR87_RAIN_CALL: model_timestep,wrapper_j,dtcld; PR87_RAIN_SED rows follow'
      if (pr87_rain_ios /= 0) error stop 'PR87 rain sedimentation ledger header failed'
      write(pr87_rain_unit,'(a,2i10,1p,e24.16)',iostat=pr87_rain_ios) &
        'PR87_RAIN_CALL',pr87_model_timestep,lat,dtcld
      if (pr87_rain_ios /= 0) error stop 'PR87 rain sedimentation ledger metadata failed'
      pr85_g_unit = 0
      pr85_g_ios = 0
      if (pr67_trace_this_call) then
        open(newunit=pr85_g_unit,file='pr85_graupel_sedimentation_budget.raw', &
             form='formatted',status='unknown',position='append',action='write',iostat=pr85_g_ios)
        if (pr85_g_ios /= 0) error stop 'PR85 graupel sedimentation ledger open failed'
        write(pr85_g_unit,'(a)',iostat=pr85_g_ios) &
          '# PR85_G_SED: i,lat,substep,nlevels; proposed/approved/withheld Q kg m-2, B m3 m-2; '// &
          'ground sink Q/B; stored delta Q/B on local dend*delz basis; R32 residual Q/B'
        if (pr85_g_ios /= 0) error stop 'PR85 graupel sedimentation ledger header failed'
      endif
      do n = 1, mstepmax
        do i = its, ite
          pr85_g_qrate(kts:kte) = 0.0d0
          pr85_g_brate(kts:kte) = 0.0d0
          if (n.le.mstep(i)) then
            call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep(i), &
                 dend(i,kts:kte),delz(i,kts:kte),mass_velocity_rate(i,kts:kte,3), &
                 mass_velocity_rate(i,kts:kte,3),qrs(i,kts:kte,3),brs(i,kts:kte), &
                 PR85_SED_GRAUPEL,qcrmin,pr85_brs_min,100.0,900.0, &
                 pr85_g_qrate(kts:kte),pr85_g_brate(kts:kte), &
                 pr85_g_unit,pr67_trace_this_call,pr85_g_valid,0.0,0.0,0.0,0.0)
            if (.not.pr85_g_valid) error stop 'PR85 graupel sedimentation packet rejected'
            do k = kts, kte
              falk(i,k,3) = REAL(pr85_g_qrate(k))
              falkb(i,k) = REAL(pr85_g_brate(k))
            enddo
          endif
          pr87_rain_qrate(kts:kte) = 0.0d0
          pr87_rain_nrate(kts:kte) = 0.0d0
          if (n.le.mstep(i)) then
            call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep(i), &
                 dend(i,kts:kte),delz(i,kts:kte),mass_velocity_rate(i,kts:kte,1), &
                 number_velocity_rate(i,kts:kte,1),qrs(i,kts:kte,1),nrs(i,kts:kte,1), &
                 PR87_SED_RAIN,qcrmin,nrmin,0.0,0.0, &
                 pr87_rain_qrate(kts:kte),pr87_rain_nrate(kts:kte), &
                 pr87_rain_unit,.true.,pr87_rain_valid, &
                 pidnr,dmr,lamdarmin,lamdarmax)
            if (.not.pr87_rain_valid) then
              write(pr87_rain_unit,'(a,5i10,1p,7e24.16)') &
                'PR87_RAIN_FAIL',pr87_model_timestep,i,lat,n,mstep(i), &
                dtcld,pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin
              do k=kts,kte
                write(pr87_rain_unit,'(a,i10,1p,6e24.16)') &
                  'PR87_RAIN_FAIL_LEVEL',k,qrs(i,k,1),nrs(i,k,1),dend(i,k), &
                  delz(i,k),mass_velocity_rate(i,k,1),number_velocity_rate(i,k,1)
              enddo
              flush(pr87_rain_unit)
              error stop 'PR87 rain sedimentation packet rejected'
            endif
            do k = kts, kte
              falk(i,k,1) = REAL(pr87_rain_qrate(k))
              falkn(i,k,1) = REAL(pr87_rain_nrate(k))
            enddo
          endif
        enddo
        k = kte
        do i = its, ite
         if(n.le.mstep(i)) then
           fall(i,k,1) = fall(i,k,1)+falk(i,k,1)
           falln(i,k,1) = falln(i,k,1)+falkn(i,k,1)
           fallb(i,k) = fallb(i,k)+falkb(i,k)
           falk(i,k,2) = dend(i,k)*qrs(i,k,2)*mass_velocity_rate(i,k,2)/mstep(i)
           fall(i,k,2) = fall(i,k,2)+falk(i,k,2)
           qrs(i,k,2) = max(qrs(i,k,2)-falk(i,k,2)*dtcld/dend(i,k),0.)
           fall(i,k,3) = fall(i,k,3)+falk(i,k,3)
         endif
       enddo

       do k = kte_in-1,kts,-1
         do i = its,ite
           if(n.le.mstep(i)) then
             fall(i,k,1) = fall(i,k,1)+falk(i,k,1)
             falln(i,k,1) = falln(i,k,1)+falkn(i,k,1)
             fallb(i,k) = fallb(i,k)+falkb(i,k)
             falk(i,k,2) = dend(i,k)*qrs(i,k,2)*mass_velocity_rate(i,k,2)/mstep(i)
             fall(i,k,2) = fall(i,k,2)+falk(i,k,2)
             dqs(i,k) = min(falk(i,k,2)*dtcld/dend(i,k),qrs(i,k,2))
             dqs(i,k+1) = min(falk(i,k+1,2)*delz(i,k+1)/delz(i,k)              &
                          *dtcld/dend(i,k),qrs(i,k+1,2))
             qrs(i,k,2) = max(qrs(i,k,2)-dqs(i,k)+dqs(i,k+1),0.)
             fall(i,k,3) = fall(i,k,3)+falk(i,k,3)
            endif
          enddo
        enddo

        do k = kts, kte
          do i = its, ite
          qrs_tmp(i,k,1) = qrs(i,k,1)
          qrs_tmp(i,k,2) = qrs(i,k,2)
          qrs_tmp(i,k,3) = qrs(i,k,3)
          qci_tmp(i,k) = qci(i,k,2)
          nci_tmp(i,k) = nci(i,k,2)
          nrs_tmp(i,k) = nrs(i,k,1)
          enddo
        enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)
   call pr87_report_graupel_consumer(2,pr87_model_timestep,lat, &
        its,ite,kts,kte,qrs_tmp,brs,progb_status)


   call pr77_scan_slope_state(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp,its,ite,kts,kte,lat, &
        'KDM62D_SLOPE_02')
   call validate_kdm6_slope_states(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp)
   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,terminal_velocity_mass,terminal_velocity_number,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax,progb_status)
   call kdm6_velocity_rates(terminal_velocity_mass,terminal_velocity_number, &
                            delz,mass_velocity_rate,number_velocity_rate, &
                            ims,ime,kms,kme,its,ite,kts,kte)


      enddo
      close(pr87_rain_unit,iostat=pr87_rain_ios)
      if (pr87_rain_ios /= 0) &
        error stop 'PR87 rain sedimentation ledger close failed'
      if (pr67_trace_this_call) close(pr85_g_unit,iostat=pr85_g_ios)
      if (pr67_trace_this_call .and. pr85_g_ios /= 0) &
        error stop 'PR85 graupel sedimentation ledger close failed'


      if (pr67_trace_this_call) then
        open(newunit=pr67_unit,file='pr67_kdm6_process.raw', &
             access='stream',form='unformatted',status='unknown',position='append')
        write(pr67_unit) 'PR67P001'
        write(pr67_unit) 0,lat,its,ite,kts,kte,dtcld
        write(pr67_unit) mass_velocity_rate(its:ite,kts:kte,4)
        write(pr67_unit) delz(its:ite,kts:kte)
        write(pr67_unit) dend(its:ite,kts:kte)
        write(pr67_unit) qci(its:ite,kts:kte,2)
        close(pr67_unit)
      endif
      pr85_ice_unit = 0
      pr85_ice_ios = 0
      if (pr67_trace_this_call) then
        open(newunit=pr85_ice_unit,file='pr85_ice_sedimentation_budget.raw', &
             form='formatted',status='unknown',position='append',action='write',iostat=pr85_ice_ios)
        if (pr85_ice_ios /= 0) error stop 'PR85 ice sedimentation ledger open failed'
        write(pr85_ice_unit,'(a)',iostat=pr85_ice_ios) &
          '# PR85_ICE_SED: cell_i,lat,substep,nlevels; proposed/approved/withheld Q kg m-2, N # m-2; '// &
          'ground sink Q/N; stored delta Q/N on local dend*delz basis; R32 residual Q/N'
        if (pr85_ice_ios /= 0) error stop 'PR85 ice sedimentation ledger header failed'
      endif
      do n = 1, mstepmax_i
        do i = its, ite
          if (n.le.mstep_i(i)) then
            if (pr87_model_timestep.eq.24 .and. lat.eq.247 .and. i.eq.230) then
              do pr93_ice_k=kts,kte
                write(pr85_psd_unit,'(a,7i8,3(1x,z8.8),1p,4e25.16e3)',iostat=pr93_ice_ios) &
                     'PR93_ICE_SED_BEFORE',pr87_model_timestep,i,lat,loop,n,mstep_i(i),pr93_ice_k, &
                     transfer(qci(i,pr93_ice_k,2),0),transfer(nci(i,pr93_ice_k,2),0), &
                     transfer(dend(i,pr93_ice_k),0),DBLE(delz(i,pr93_ice_k)), &
                     mass_velocity_rate(i,pr93_ice_k,4),number_velocity_rate(i,pr93_ice_k,2),DBLE(dtcld)
                if (pr93_ice_ios.ne.0) error stop 'PR93 ice column capture failed'
              enddo
            endif
            call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep_i(i), &
                 dend(i,kts:kte),delz(i,kts:kte),mass_velocity_rate(i,kts:kte,4), &
                 number_velocity_rate(i,kts:kte,2),qci(i,kts:kte,2),nci(i,kts:kte,2), &
                 PR85_SED_ICE,0.0,0.0,0.0,0.0,pr85_ice_qrate,pr85_ice_nrate, &
                 pr85_ice_unit,pr67_trace_this_call,pr85_ice_valid,0.0,0.0,0.0,0.0)
            if (.not.pr85_ice_valid) error stop 'PR85 ice sedimentation packet rejected'
            if (pr87_model_timestep.eq.24 .and. lat.eq.247 .and. i.eq.230) then
              do pr93_ice_k=kts,kte
                write(pr85_psd_unit,'(a,7i8,3(1x,z8.8),1p,4e25.16e3)',iostat=pr93_ice_ios) &
                     'PR93_ICE_SED_AFTER',pr87_model_timestep,i,lat,loop,n,mstep_i(i),pr93_ice_k, &
                     transfer(qci(i,pr93_ice_k,2),0),transfer(nci(i,pr93_ice_k,2),0), &
                     transfer(dend(i,pr93_ice_k),0),DBLE(delz(i,pr93_ice_k)), &
                     mass_velocity_rate(i,pr93_ice_k,4),number_velocity_rate(i,pr93_ice_k,2),DBLE(dtcld)
                if (pr93_ice_ios.ne.0) error stop 'PR93 ice column capture failed'
              enddo
            endif

            do k = kts, kte
              falk(i,k,4) = REAL(pr85_ice_qrate(k))
              falkn(i,k,2) = REAL(pr85_ice_nrate(k))
              fall(i,k,4) = fall(i,k,4)+falk(i,k,4)
              falln(i,k,2) = falln(i,k,2)+falkn(i,k,2)
            enddo
          endif
        enddo

        if (pr67_trace_this_call .and. n .eq. 1) then
          open(newunit=pr67_unit,file='pr67_kdm6_process.raw', &
               access='stream',form='unformatted',status='unknown',position='append')
          write(pr67_unit) 'PR67P001'
          write(pr67_unit) 1,lat,its,ite,kts,kte,dtcld
          write(pr67_unit) qci(its:ite,kts:kte,2)
          write(pr67_unit) falk(its:ite,kts:kte,4)
          write(pr67_unit) fall(its:ite,kts:kte,4)
          close(pr67_unit)
        endif
        do k = kts, kte
          do i = its, ite
            qrs_tmp(i,k,1) = qrs(i,k,1)
            qrs_tmp(i,k,2) = qrs(i,k,2)
            qrs_tmp(i,k,3) = qrs(i,k,3)
            qci_tmp(i,k) = qci(i,k,2)
            nci_tmp(i,k) = nci(i,k,2)
            nrs_tmp(i,k) = nrs(i,k,1)
          enddo
        enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)
   call pr87_report_graupel_consumer(3,pr87_model_timestep,lat, &
        its,ite,kts,kte,qrs_tmp,brs,progb_status)


   call pr77_scan_slope_state(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp,its,ite,kts,kte,lat, &
        'KDM62D_SLOPE_03')
   call validate_kdm6_slope_states(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp)
   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,terminal_velocity_mass,terminal_velocity_number,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax,progb_status)
   call kdm6_velocity_rates(terminal_velocity_mass,terminal_velocity_number, &
                            delz,mass_velocity_rate,number_velocity_rate, &
                            ims,ime,kms,kme,its,ite,kts,kte)


      enddo 
      if (pr67_trace_this_call) close(pr85_ice_unit,iostat=pr85_ice_ios)
      if (pr67_trace_this_call .and. pr85_ice_ios /= 0) &
        error stop 'PR85 ice sedimentation ledger close failed'

      do k = kte, kts, -1
        do i = its, ite
          supcol = t0c-t(i,k)
          if(supcol.lt.0.) xlf = xlf0
          n0so(i,k) = (n0s)/g1pms/(rslopemu(i,k,2)) 
          if (progb_status(i,k) == PROGB_PSD_ACTIVE) then
            n0go(i,k) = (n0g)/g1pmg/(rslopemu(i,k,3))
          else
            n0go(i,k) = 0.0
          endif
          n0sfac(i,k) = max(min(exp(alpha*supcol),n0smax/n0s),1.)
          if(t(i,k).gt.t0c) then




            work2(i,k) = venfac(p(i,k),t(i,k),gas_density(i,k))
            if(qrs(i,k,2).gt.0.) then

              coeres = (rslope2(i,k,2))*sqrt(rslope(i,k,2)*rslopeb(i,k,2))          &
                       *rslopemu(i,k,2)
              psmlt(i,k) =(xka(t(i,k),gas_density(i,k)))/xlf*(t0c-t(i,k))*n0sfac(i,k)       &
                         *pi/2.*((precs1)*n0so(i,k)*rslope2(i,k,2)*rslopemu(i,k,2)  &
                         +(precs2)*n0so(i,k)*work2(i,k)*coeres)/dry_carrier_density(i,k)
              psmlt(i,k) = min(max(psmlt(i,k)*dtcld,-qrs(i,k,2)),0.)




              if (psmlt(i,k).lt.0.) then
                pr85_melt_q_before = qrs(i,k,2)
                pr85_melt_t_before = t(i,k)
                pr85_melt_qc_before = qci(i,k,1)
                pr85_melt_nc_before = nci(i,k,1)
                pr85_melt_qr_before = qrs(i,k,1)
                pr85_melt_nr_before = nrs(i,k,1)
                pr85_melt_requested_q = -psmlt(i,k)
                pr85_melt_mean_mass = cms*(g1pdsms/g1pms)*rsloped(i,k,2)
                pr85_melt_route = 2
                pr85_melt_accepted = .TRUE.
                if (qrs(i,k,2).gt.qcrmin) then
! Preserve the native active-snow mass, number, and heat updates.
                  sfac = (rslope(i,k,2))*n0so(i,k)*n0sfac(i,k)/qrs(i,k,2)
                  nrs(i,k,1) = nrs(i,k,1) - sfac*psmlt(i,k)
                  pr85_melt_number_request = -DBLE(sfac)*DBLE(psmlt(i,k))
                  qrs(i,k,2) = qrs(i,k,2) + psmlt(i,k)
                  qrs(i,k,1) = qrs(i,k,1) - psmlt(i,k)
                  t(i,k) = t(i,k) + xlf/cpm(i,k)*psmlt(i,k)
                else
                  call pr85_kdm6_subthreshold_melt(qci(i,k,1),nci(i,k,1), &
                       qrs(i,k,1),nrs(i,k,1),dry_carrier_density(i,k),delz(i,k), &
                       pr85_melt_requested_q,pr85_melt_mean_mass, &
                       pidnc/lamdacmax**dmc,pidnc/lamdacmin**dmc, &
                       pidnr/lamdarmax**dmr,pidnr/lamdarmin**dmr, &
                       pr85_melt_qc_after,pr85_melt_nc_after, &
                       pr85_melt_qr_after,pr85_melt_nr_after, &
                       pr85_melt_number_request,pr85_melt_route,pr85_melt_accepted)
                  if (pr85_melt_accepted .and. pr85_melt_route.ne.0) then
                    if (.not.ieee_is_finite(pr85_melt_t_before) .or. &
                        .not.ieee_is_finite(xlf) .or. .not.ieee_is_finite(cpm(i,k)) .or. &
                        cpm(i,k).le.0.0) then
                      pr85_melt_accepted=.false.
                    else
                      pr85_melt_qs_candidate=DBLE(qrs(i,k,2))+DBLE(psmlt(i,k))
                      pr85_melt_t_candidate=DBLE(pr85_melt_t_before)+ &
                          (DBLE(xlf)/DBLE(cpm(i,k)))*DBLE(psmlt(i,k))
                      if (.not.ieee_is_finite(pr85_melt_qs_candidate) .or. &
                          pr85_melt_qs_candidate.lt.0.0d0 .or. &
                          pr85_melt_qs_candidate.gt.DBLE(HUGE(0.0)) .or. &
                          .not.ieee_is_finite(pr85_melt_t_candidate) .or. &
                          pr85_melt_t_candidate.le.0.0d0 .or. &
                          pr85_melt_t_candidate.gt.DBLE(HUGE(0.0))) then
                        pr85_melt_accepted=.false.
                      else
                        pr85_melt_qs_after=REAL(pr85_melt_qs_candidate)
                        pr85_melt_t_after=REAL(pr85_melt_t_candidate)
                        if (.not.ieee_is_finite(pr85_melt_qs_after) .or. &
                            .not.ieee_is_finite(pr85_melt_t_after) .or. &
                            pr85_melt_qs_after.lt.0.0 .or. &
                            pr85_melt_qs_after.ge.pr85_melt_q_before .or. &
                            pr85_melt_t_after.le.0.0) pr85_melt_accepted=.false.
                      endif
                    endif
                    if (pr85_melt_accepted) then
                      qci(i,k,1) = pr85_melt_qc_after
                      nci(i,k,1) = pr85_melt_nc_after
                      qrs(i,k,1) = pr85_melt_qr_after
                      nrs(i,k,1) = pr85_melt_nr_after
                      qrs(i,k,2) = pr85_melt_qs_after
                      t(i,k) = pr85_melt_t_after
                    else
                      pr85_melt_route = 0
                      pr85_melt_qc_after=pr85_melt_qc_before
                      pr85_melt_nc_after=pr85_melt_nc_before
                      pr85_melt_qr_after=pr85_melt_qr_before
                      pr85_melt_nr_after=pr85_melt_nr_before
                      pr85_melt_qs_after=pr85_melt_q_before
                      pr85_melt_t_after=pr85_melt_t_before
                    endif
                  else
                    pr85_melt_route = 0
                    pr85_melt_qs_after=pr85_melt_q_before
                    pr85_melt_t_after=pr85_melt_t_before
                  endif
                endif
                if (pr67_trace_this_call) then
                  pr85_melt_mass_request = DBLE(dry_carrier_density(i,k))* &
                       DBLE(delz(i,k))*DBLE(pr85_melt_requested_q)
                  pr85_melt_qc_delta = DBLE(qci(i,k,1))-DBLE(pr85_melt_qc_before)
                  pr85_melt_nc_delta = DBLE(nci(i,k,1))-DBLE(pr85_melt_nc_before)
                  pr85_melt_qr_delta = DBLE(qrs(i,k,1))-DBLE(pr85_melt_qr_before)
                  pr85_melt_nr_delta = DBLE(nrs(i,k,1))-DBLE(pr85_melt_nr_before)
                  pr85_melt_mass_actual = DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))* &
                       (pr85_melt_qc_delta+pr85_melt_qr_delta)
                  pr85_melt_number_actual = DBLE(delz(i,k))* &
                       (pr85_melt_nc_delta+pr85_melt_nr_delta)
                  pr85_melt_mass_residual = pr85_melt_mass_actual-pr85_melt_mass_request
                  pr85_melt_number_residual = pr85_melt_number_actual- &
                       pr85_melt_number_request*DBLE(delz(i,k))
                  open(newunit=pr85_melt_unit,file='pr85_kdm6_melt_budget.raw', &
                       form='formatted',status='unknown',position='append',action='write', &
                       iostat=pr85_melt_ios)
                  if (pr85_melt_ios.ne.0) error stop 'PR85 melt ledger open failed'
                  write(pr85_melt_unit,'(a)',iostat=pr85_melt_ios) &
                       '# PR85_MELT: i,lat,k,loop,route; dtcld,T before/after; Qs before/after kg/kg-dry; '// &
                       'source mean kg/particle; proposed mass kg/m2, number #/m2; '// &
                       'stored dQC,dNC,dQR,dNR; actual minus proposed mass/number; accepted flag'
                  if (pr85_melt_ios.ne.0) error stop 'PR85 melt ledger header failed'
                  write(pr85_melt_unit,'(a,5i8,1p,14es24.16,1x,l1)',iostat=pr85_melt_ios) &
                       'PR85_MELT',i,lat,k,loop,pr85_melt_route,dtcld,pr85_melt_t_before, &
                       t(i,k),pr85_melt_q_before,qrs(i,k,2),pr85_melt_mean_mass, &
                       pr85_melt_mass_request,pr85_melt_number_request*DBLE(delz(i,k)), &
                       pr85_melt_qc_delta,pr85_melt_nc_delta,pr85_melt_qr_delta, &
                       pr85_melt_nr_delta,pr85_melt_mass_residual,pr85_melt_number_residual, &
                       pr85_melt_accepted
                  if (pr85_melt_ios.ne.0) error stop 'PR85 melt ledger write failed'
                  close(pr85_melt_unit,iostat=pr85_melt_ios)
                  if (pr85_melt_ios.ne.0) error stop 'PR85 melt ledger close failed'
                endif
                if (.not.pr85_melt_accepted .or. pr85_melt_route.eq.0) &
                  error stop 'PR85 positive snowmelt has no supported liquid pair'
              endif
            endif




            if(progb_status(i,k)==PROGB_PSD_ACTIVE .and. qrs(i,k,3).gt.0.) then
              coeres = (rslope2(i,k,3))*sqrt(rslope(i,k,3)*rslopeb(i,k,3))           &
                       *rslopemu(i,k,3)
              pgmlt(i,k) = (xka(t(i,k),gas_density(i,k)))/xlf*(t0c-t(i,k))                   &
                           *pi/2.*((precg1)*n0go(i,k)*rslope2(i,k,3)*rslopemu(i,k,3) &
                           +(precg2(i,k))*n0go(i,k)*work2(i,k)*coeres)/dry_carrier_density(i,k)
              pgmlt(i,k) = min(max(pgmlt(i,k)*dtcld,-qrs(i,k,3)),0.)
              if (progb_status(i,k) /= PROGB_PSD_ACTIVE) &
                error stop 'ProgB status invalid for melting volume'

              if (pgmlt(i,k) .lt. 0.0) then
                if (.not.ieee_is_finite(qrs(i,k,3))) &
                  error stop 'KDM6 graupel melt donor mass is nonfinite'
                if (qrs(i,k,3).le.0.0) &
                  error stop 'KDM6 graupel melt donor mass is invalid'
                if (.not.ieee_is_finite(brs(i,k))) &
                  error stop 'KDM6 graupel melt volume operands are invalid'
                if (.not.ieee_is_finite(pgmlt(i,k))) &
                  error stop 'KDM6 graupel melt volume operands are invalid'
                pr87_gmelt_q_fixed=[qci(i,k,1),qci(i,k,2),qrs(i,k,1),qrs(i,k,2),qrs(i,k,3)]
                pr87_gmelt_n_fixed=[nci(i,k,1),nci(i,k,2),nrs(i,k,1)]
                pr87_gmelt_bg_fixed=brs(i,k)
                pr87_gmelt_t_fixed=t(i,k)
                pr87_gmelt_q_process=0.0
                pr87_gmelt_n_process=0.0
                pr87_gmelt_q_process(3)=-pgmlt(i,k)
                pr87_gmelt_q_process(5)=pgmlt(i,k)
                if (qrs(i,k,3) .gt. qcrmin) then
                  if (.not.ieee_is_finite(rslope(i,k,3))) &
                    error stop 'KDM6 graupel melt number factor is nonfinite'
                  if (.not.ieee_is_finite(n0go(i,k))) &
                    error stop 'KDM6 graupel melt number factor is nonfinite'
                  pr87_gmelt_rate64=DBLE(rslope(i,k,3))*DBLE(n0go(i,k))
                  if (.not.ieee_is_finite(pr87_gmelt_rate64)) &
                    error stop 'KDM6 graupel melt number factor is nonfinite'
                  if (ABS(pr87_gmelt_rate64).gt.DBLE(HUGE(0.0))) &
                    error stop 'KDM6 graupel melt number factor overflow'
                  pr87_gmelt_gfac_product=REAL(pr87_gmelt_rate64)
                  if (.not.ieee_is_finite(qrs(i,k,3))) &
                    error stop 'KDM6 graupel melt donor mass is nonfinite'
                  if (qrs(i,k,3).le.0.0) &
                    error stop 'KDM6 graupel melt donor mass is invalid'
                  pr87_gmelt_rate64=DBLE(pr87_gmelt_gfac_product)/DBLE(qrs(i,k,3))
                  if (.not.ieee_is_finite(pr87_gmelt_rate64)) &
                    error stop 'KDM6 graupel melt number factor is nonfinite'
                  if (ABS(pr87_gmelt_rate64).gt.DBLE(HUGE(0.0))) &
                    error stop 'KDM6 graupel melt number factor overflow'
                  gfac=REAL(pr87_gmelt_rate64)
                  pr87_gmelt_rate64=-DBLE(gfac)*DBLE(pgmlt(i,k))
                  if (.not.ieee_is_finite(pr87_gmelt_rate64)) &
                    error stop 'KDM6 graupel melt number rate is nonfinite'
                  if (ABS(pr87_gmelt_rate64).gt.DBLE(HUGE(0.0))) &
                    error stop 'KDM6 graupel melt number rate overflow'
                  pr87_gmelt_n_process(3)=REAL(pr87_gmelt_rate64)
                endif
                if (pgmlt(i,k) .eq. -qrs(i,k,3)) then
                  pr87_gmelt_bg_process=-brs(i,k)
                else
                  pr87_gmelt_bg_delta64=DBLE(pgmlt(i,k))*DBLE(brs(i,k))/DBLE(qrs(i,k,3))
                  if (.not.ieee_is_finite(pr87_gmelt_bg_delta64)) &
                    error stop 'KDM6 graupel melt volume rate is nonfinite'
                  if (ABS(pr87_gmelt_bg_delta64).gt.DBLE(HUGE(0.0))) &
                    error stop 'KDM6 graupel melt volume rate overflow'
                  pr87_gmelt_bg_process=REAL(pr87_gmelt_bg_delta64)
                endif
                if (.not.ieee_is_finite(xlf)) &
                  error stop 'KDM6 graupel melt heat capacity is invalid'
                if (.not.ieee_is_finite(cpm(i,k))) &
                  error stop 'KDM6 graupel melt heat capacity is invalid'
                if (cpm(i,k).le.0.0) &
                  error stop 'KDM6 graupel melt heat capacity is invalid'
                pr87_gmelt_rate64=DBLE(xlf)/DBLE(cpm(i,k))
                if (.not.ieee_is_finite(pr87_gmelt_rate64)) &
                  error stop 'KDM6 graupel melt temperature ratio is nonfinite'
                if (ABS(pr87_gmelt_rate64).gt.DBLE(HUGE(0.0))) &
                  error stop 'KDM6 graupel melt temperature ratio overflow'
                pr87_gmelt_t_ratio=REAL(pr87_gmelt_rate64)
                pr87_gmelt_rate64=DBLE(pr87_gmelt_t_ratio)*DBLE(pgmlt(i,k))
                if (.not.ieee_is_finite(pr87_gmelt_rate64)) &
                  error stop 'KDM6 graupel melt temperature rate is nonfinite'
                if (ABS(pr87_gmelt_rate64).gt.DBLE(HUGE(0.0))) &
                  error stop 'KDM6 graupel melt temperature rate overflow'
                pr87_gmelt_t_process=REAL(pr87_gmelt_rate64)

                call kdm6_rain_process_fraction(pr87_gmelt_q_fixed,pr87_gmelt_q_process, &
                     pr87_gmelt_n_fixed,pr87_gmelt_n_process,pr87_gmelt_bg_fixed, &
                     pr87_gmelt_bg_process,pr87_gmelt_t_fixed,pr87_gmelt_t_process, &
                     .FALSE.,dry_carrier_density(i,k),pidnr,qmin,ncmin, &
                     qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &
                     lamdacmax,pidni,dmi,lamdaimin,lamdaimax,pr87_gmelt_alpha, &
                     pr87_gmelt_feasible,pr87_gmelt_search_status, &
                     consumer_pair_only=.TRUE., &
                     ice_sublimation_pending=.FALSE.)
                if (.not.pr87_gmelt_feasible) then
                  if (pr87_gmelt_search_status .eq. 1) then
                    call kdm6_rain_process_state_valid(pr87_gmelt_q_fixed, &
                         pr87_gmelt_n_fixed,pr87_gmelt_bg_fixed,pr87_gmelt_t_fixed, &
                         dry_carrier_density(i,k),pidnr,qmin,ncmin,qcrmin,dmr, &
                         lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &
                         lamdacmax,pidni,dmi,lamdaimin,lamdaimax, &
                         pr87_gmelt_base_valid,.FALSE., &
                         consumer_pair_only=.TRUE., &
                         ice_sublimation_pending=.FALSE.)
                    if (.not.pr87_gmelt_base_valid) &
                      error stop 'KDM6 graupel melt has invalid base state'
                    pr87_gmelt_alpha=0.0
                  else
                    error stop 'KDM6 graupel melt fraction search failed'
                  endif
                endif

                pr87_gmelt_q_after=pr87_gmelt_q_fixed+pr87_gmelt_alpha*pr87_gmelt_q_process
                pr87_gmelt_n_after=pr87_gmelt_n_fixed+pr87_gmelt_alpha*pr87_gmelt_n_process
                pr87_gmelt_bg_after=pr87_gmelt_bg_fixed+ &
                     pr87_gmelt_alpha*pr87_gmelt_bg_process
                pr87_gmelt_t_after=pr87_gmelt_t_fixed+pr87_gmelt_alpha*pr87_gmelt_t_process
                call kdm6_rain_process_state_valid(pr87_gmelt_q_after,pr87_gmelt_n_after, &
                     pr87_gmelt_bg_after,pr87_gmelt_t_after,dry_carrier_density(i,k),pidnr, &
                     qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc, &
                     lamdacmin,lamdacmax,pidni,dmi,lamdaimin,lamdaimax, &
                     pr87_gmelt_endpoint_valid,.FALSE., &
                     consumer_pair_only=.TRUE., &
                     ice_sublimation_pending=.FALSE., &
                     failure_reason=pr87_gmelt_failure_reason)
                if (.not.pr87_gmelt_endpoint_valid) &
                  error stop 'KDM6 graupel melt candidate failed stored-state validation'

                pr87_gmelt_mass_residual= &
                     DBLE(pr87_gmelt_q_after(5))-DBLE(pr87_gmelt_q_fixed(5))+ &
                     DBLE(pr87_gmelt_q_after(3))-DBLE(pr87_gmelt_q_fixed(3))
                pr87_gmelt_volume_residual= &
                     DBLE(pr87_gmelt_bg_after)-DBLE(pr87_gmelt_bg_fixed)- &
                     DBLE(pr87_gmelt_alpha)*DBLE(pr87_gmelt_bg_process)
                pr87_gmelt_number_residual= &
                     DBLE(pr87_gmelt_n_after(3))-DBLE(pr87_gmelt_n_fixed(3))- &
                     DBLE(pr87_gmelt_alpha)*DBLE(pr87_gmelt_n_process(3))
                pr87_gmelt_temperature_residual= &
                     DBLE(pr87_gmelt_t_after)-DBLE(pr87_gmelt_t_fixed)- &
                     DBLE(pr87_gmelt_alpha)*DBLE(pr87_gmelt_t_process)
                pr87_gmelt_unit=0
                pr87_gmelt_ios=0
                open(newunit=pr87_gmelt_unit,file='pr87_graupel_melt.raw', &
                     form='formatted',status='unknown',position='append',action='write', &
                     iostat=pr87_gmelt_ios)
                if (pr87_gmelt_ios.ne.0) error stop 'PR87 graupel melt ledger open failed'
                write(pr87_gmelt_unit,'(a)',iostat=pr87_gmelt_ios) &
                     '# PR87_GRAUPEL_MELT: i,lat,k,loop,search_status,feasible; '// &
                     'alpha,dt; QG before/proposed/approved/after; BG before/proposed/approved/after; '// &
                     'QR before/proposed/approved/after; NR before/proposed/approved/after; '// &
                     'T before/proposed/approved/after; signed storage residuals: kg/kg-dry,m3/kg-dry,#/m3,K'
                if (pr87_gmelt_ios.ne.0) error stop 'PR87 graupel melt ledger header failed'
                write(pr87_gmelt_unit,'(a,5i8,l1,1p,26e24.16)',iostat=pr87_gmelt_ios) &
                     'PR87_GRAUPEL_MELT',i,lat,k,loop,pr87_gmelt_search_status, &
                     pr87_gmelt_feasible,pr87_gmelt_alpha,dtcld, &
                     pr87_gmelt_q_fixed(5),pr87_gmelt_q_process(5), &
                     pr87_gmelt_alpha*pr87_gmelt_q_process(5),pr87_gmelt_q_after(5), &
                     pr87_gmelt_bg_fixed,pr87_gmelt_bg_process, &
                     pr87_gmelt_alpha*pr87_gmelt_bg_process,pr87_gmelt_bg_after, &
                     pr87_gmelt_q_fixed(3),pr87_gmelt_q_process(3), &
                     pr87_gmelt_alpha*pr87_gmelt_q_process(3),pr87_gmelt_q_after(3), &
                     pr87_gmelt_n_fixed(3),pr87_gmelt_n_process(3), &
                     pr87_gmelt_alpha*pr87_gmelt_n_process(3),pr87_gmelt_n_after(3), &
                     pr87_gmelt_t_fixed,pr87_gmelt_t_process, &
                     pr87_gmelt_alpha*pr87_gmelt_t_process,pr87_gmelt_t_after, &
                     pr87_gmelt_mass_residual,pr87_gmelt_volume_residual, &
                     pr87_gmelt_number_residual,pr87_gmelt_temperature_residual
                if (pr87_gmelt_ios.ne.0) error stop 'PR87 graupel melt ledger write failed'
                close(pr87_gmelt_unit,iostat=pr87_gmelt_ios)
                if (pr87_gmelt_ios.ne.0) error stop 'PR87 graupel melt ledger close failed'

                if (pr87_gmelt_alpha .gt. 0.0) then
                  qrs(i,k,3)=pr87_gmelt_q_after(5)
                  qrs(i,k,1)=pr87_gmelt_q_after(3)
                  nrs(i,k,1)=pr87_gmelt_n_after(3)
                  brs(i,k)=pr87_gmelt_bg_after
                  t(i,k)=pr87_gmelt_t_after
                endif
              endif
            endif






              if(qci(i,k,2).gt.0) then
                  qci(i,k,1) = qci(i,k,1) + qci(i,k,2)
                  nci(i,k,1) = nci(i,k,1) + nci(i,k,2)
            t(i,k) = t(i,k) - xlf/cpm(i,k)*qci(i,k,2)
            qci(i,k,2) = 0.
            nci(i,k,2) = 0.
           endif
          endif  
        enddo
      enddo



      do i = its, ite
        fallsum = fall(i,kts,1)+fall(i,kts,2)+fall(i,kts,3)+fall(i,kts,4)
        fallsum_qsi = fall(i,kts,2)+fall(i,kts,4)
        fallsum_qg = fall(i,kts,3)
        if(fallsum.gt.0.) then
          rainncv(i) = fallsum*delz(i,kts)/denr*dtcld*1000. + rainncv(i)
          rain(i) = fallsum*delz(i,kts)/denr*dtcld*1000. + rain(i)
        endif
        If(fallsum_qsi.gt.0.) then
          tstepsnow(i) = fallsum_qsi*delz(i,kts)/denr*dtcld*1000. + tstepsnow(i)
          IF( PRESENT (snowncv) .AND. PRESENT (snow)) THEN
            snowncv(i) = fallsum_qsi*delz(i,kts)/denr*dtcld*1000. + snowncv(i)     
            snow(i) = fallsum_qsi*delz(i,kts)/denr*dtcld*1000. + snow(i)
          ENDIF
        ENDIF
        IF(fallsum_qg.gt.0.) then
          tstepgraup(i) = fallsum_qg*delz(i,kts)/denr*dtcld*1000.              &
                            + tstepgraup(i)
          IF( PRESENT (graupelncv) .AND. PRESENT (graupel)) THEN
            graupelncv(i) = fallsum_qg*delz(i,kts)/denr*dtcld*1000.            &  
                            + graupelncv(i)
            graupel(i) = fallsum_qg*delz(i,kts)/denr*dtcld*1000. + graupel(i)
          ENDIF
        ENDIF
        IF ( PRESENT (snowncv)) THEN
          if(fallsum.gt.0.)sr(i)=(snowncv(i) + graupelncv(i))/(rainncv(i)+1.e-12)
        ELSE
          if(fallsum.gt.0.)sr(i)=(tstepsnow(i) + tstepgraup(i))/(rainncv(i)+1.e-12)
        ENDIF
      enddo

      if (pr67_trace_this_call) then
        open(newunit=pr67_unit,file='pr67_kdm6_process.raw', &
             access='stream',form='unformatted',status='unknown',position='append')
        write(pr67_unit) 'PR67P001'
        write(pr67_unit) 2,lat,its,ite,kts,kte,dtcld,denr
        write(pr67_unit) fall(its:ite,kts,1:4)
        write(pr67_unit) delz(its:ite,kts)
        write(pr67_unit) gas_density(its:ite,kts)
        write(pr67_unit) rainncv(its:ite)
        write(pr67_unit) present(snowncv),present(graupelncv)
        if (present(snowncv)) write(pr67_unit) snowncv(its:ite)
        if (present(graupelncv)) write(pr67_unit) graupelncv(its:ite)
        close(pr67_unit)
      endif

      do k = kts, kte
        do i = its, ite
          qrs_tmp(i,k,1) = qrs(i,k,1)
          qrs_tmp(i,k,2) = qrs(i,k,2)
          qrs_tmp(i,k,3) = qrs(i,k,3)
          qci_tmp(i,k) = qci(i,k,2)
          nci_tmp(i,k) = nci(i,k,2)
          nrs_tmp(i,k) = nrs(i,k,1)
        enddo
      enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)
   call pr87_report_graupel_consumer(4,pr87_model_timestep,lat, &
        its,ite,kts,kte,qrs_tmp,brs,progb_status)


   call pr77_scan_slope_state(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp,its,ite,kts,kte,lat, &
        'KDM62D_SLOPE_04')
   call validate_kdm6_slope_states(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp)
   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,terminal_velocity_mass,terminal_velocity_number,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax,progb_status)

      do k = kts, kte
        do i = its, ite
          supcol = t0c-t(i,k)
          xlf = xls-xl(i,k)
          if(supcol.lt.0.) xlf = xlf0




          if(supcol.gt.40. .and. qci(i,k,1).gt.0.) then
            qci(i,k,2) = qci(i,k,2) + qci(i,k,1)
            nci(i,k,2) = nci(i,k,2) + nci(i,k,1)




            t(i,k) = t(i,k) + xlf/cpm(i,k)*qci(i,k,1)
            qci(i,k,1) = 0.
            nci(i,k,1) = 0.
          endif

          if(qci(i,k,1).le.qmin .or. nci(i,k,1).le.ncmin ) then
            rslopecmu(i,k) = rslopecmmax
            rslopec(i,k) = rslopecmax
            rslopec2(i,k) = rslopec2max
            rslopec3(i,k) = rslopec3max
            rslopecd(i,k) = rslopecdmax  
          else
            rslopec(i,k) = 1./lamdac(qci(i,k,1),dry_carrier_density(i,k),nci(i,k,1))
            rslopec2(i,k) = (rslopec(i,k))*rslopec(i,k)
            rslopec3(i,k) = (rslopec2(i,k))*rslopec(i,k)
            rslopecmu(i,k) = DBLE(rslopec(i,k))**muc
            rslopecd(i,k) = (rslopec(i,k))**dmc
          endif
          call pr77_scan_local_state(qrs(i,k,1),nrs(i,k,1), &
               qci(i,k,1),nci(i,k,1),qci(i,k,2),nci(i,k,2), &
               qrs(i,k,3),brs(i,k),i,k,lat,'KDM62D_LOCAL_01')
          call validate_local_species_states(qrs(i,k,1),nrs(i,k,1), &
               qci(i,k,1),nci(i,k,1),qci(i,k,2),nci(i,k,2), &
               qrs(i,k,3),brs(i,k))
          n0r(i,k) = 0.0
          n0c(i,k) = 0.0
          n0i(i,k) = 0.0
          if (classify_species_state(qrs(i,k,1),nrs(i,k,1)) == SPECIES_ACTIVE) &
            n0r(i,k) = nrs(i,k,1)/(rslope(i,k,1)*rslopemu(i,k,1)*g1pmr)
          if (classify_species_state(qci(i,k,1),nci(i,k,1)) == SPECIES_ACTIVE) &
            n0c(i,k) = (muc+1)*nci(i,k,1)/(rslopec(i,k)*rslopecmu(i,k))
          if (classify_species_state(qci(i,k,2),nci(i,k,2)) == SPECIES_ACTIVE) &
            n0i(i,k) = nci(i,k,2)/(rslope(i,k,4)*rslopemu(i,k,4)*g1pmi) 

          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then
            lamdr_tmp(i,k) = exp(log((((pidnr)*nrs(i,k,1))                       &
                         /(dry_carrier_density(i,k)*qrs(i,k,1))))*(1./dmr))
            n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            if(lamdr_tmp(i,k) .le. lamdarmin) then
              lamdr_tmp(i,k) = lamdarmin
              pr85_psd_before = nrs(i,k,1)
              call pr85_kdm6_psd_bound_number(qrs(i,k,1),dry_carrier_density(i,k),lamdr_tmp(i,k), &
                   lamdarmin,lamdarmax,pidnr,dmr,1, &
                   'rain','stage1',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nrs(i,k,1) = pr85_psd_directed
              n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            elseif(lamdr_tmp(i,k) .ge. lamdarmax) then
              lamdr_tmp(i,k) = lamdarmax
              pr85_psd_before = nrs(i,k,1)
              call pr85_kdm6_psd_bound_number(qrs(i,k,1),dry_carrier_density(i,k),lamdr_tmp(i,k), &
                   lamdarmin,lamdarmax,pidnr,dmr,2, &
                   'rain','stage1',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nrs(i,k,1) = pr85_psd_directed
              n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            endif
          endif
          if(qci(i,k,1).ge.qmin .and. nci(i,k,1) .ge. ncmin ) then
            lamdc_tmp(i,k) = exp(log((((pidnc)*nci(i,k,1))                       &
                         /(dry_carrier_density(i,k)*qci(i,k,1))))*(1./dmc))
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            if(lamdc_tmp(i,k) .le. lamdacmin) then
              lamdc_tmp(i,k) = lamdacmin
              pr85_psd_before = nci(i,k,1)
              call pr85_kdm6_psd_bound_number(qci(i,k,1),dry_carrier_density(i,k),lamdc_tmp(i,k), &
                   lamdacmin,lamdacmax,pidnc,dmc,1, &
                   'cloud','stage1',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,1) = pr85_psd_directed
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            elseif(lamdc_tmp(i,k) .ge. lamdacmax) then
              lamdc_tmp(i,k) = lamdacmax
              pr85_psd_before = nci(i,k,1)
              call pr85_kdm6_psd_bound_number(qci(i,k,1),dry_carrier_density(i,k),lamdc_tmp(i,k), &
                   lamdacmin,lamdacmax,pidnc,dmc,2, &
                   'cloud','stage1',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,1) = pr85_psd_directed
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            endif
          endif
          if(qci(i,k,2) .ge. 1.e-14 ) then
            if (.not.all(ieee_is_finite([qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k)])) .or. nci(i,k,2).le.0.0 .or. &
                 dry_carrier_density(i,k).le.0.0) &
              error stop 'PR93 invalid active ice PSD input'
            lamdi_tmp(i,k) = exp(log((((pidni)*nci(i,k,2))                       &
                         /(dry_carrier_density(i,k)*qci(i,k,2))))*(1./dmi))
            n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            pr93_ice_min=DBLE(pidni)/(DBLE(lamdaimax)**DBLE(dmi))
            pr93_ice_max=DBLE(pidni)/(DBLE(lamdaimin)**DBLE(dmi))
            pr93_ice_pair_valid=pr93_kdm6_pair_in_cone(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pr93_ice_min,pr93_ice_max)
            if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX &
                 .and. nci(i,k,2).gt.0.0) pr93_ice_pair_valid=.true.
            call kdm6_ice_ng_pair_contract(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pidni,dmi,lamdaimin,lamdaimax, &
                 pr93_ice_ng_valid,pr93_ice_ng_min,pr93_ice_ng_max)
            if (qci(i,k,2).gt.0.0 .and. &
                qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX .and. nci(i,k,2).gt.0.0) &
              pr93_ice_ng_valid=.true.
            pr93_ice_direct_repair=lamdi_tmp(i,k).gt.lamdaimin .and. &
                 lamdi_tmp(i,k).lt.lamdaimax .and. &
                 (.not.pr93_ice_pair_valid .or. .not.pr93_ice_ng_valid)
            if(lamdi_tmp(i,k) .le. lamdaimin .or. &
                 (qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. &
                  .not.pr93_ice_ng_valid .and. DBLE(nci(i,k,2)).lt.pr93_ice_ng_min)) then
              lamdi_tmp(i,k) = lamdaimin
              pr85_psd_before = nci(i,k,2)
              call pr85_kdm6_psd_bound_number(qci(i,k,2),dry_carrier_density(i,k),lamdi_tmp(i,k), &
                   lamdaimin,lamdaimax,pidni,dmi,1, &
                   'ice','stage1',i,lat,k,pr85_psd_before,pr85_psd_native_available, &
                   (pr67_trace_this_call.or.pr93_ice_direct_repair), &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,2) = pr85_psd_directed
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            elseif(lamdi_tmp(i,k) .ge. lamdaimax .or. &
                 (qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. &
                  .not.pr93_ice_ng_valid .and. DBLE(nci(i,k,2)).gt.pr93_ice_ng_max)) then
              lamdi_tmp(i,k) = lamdaimax
              pr85_psd_before = nci(i,k,2)
              call pr85_kdm6_psd_bound_number(qci(i,k,2),dry_carrier_density(i,k),lamdi_tmp(i,k), &
                   lamdaimin,lamdaimax,pidni,dmi,2, &
                   'ice','stage1',i,lat,k,pr85_psd_before,pr85_psd_native_available, &
                   (pr67_trace_this_call.or.pr93_ice_direct_repair), &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,2) = pr85_psd_directed
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            endif
            pr93_ice_pair_valid=pr93_kdm6_pair_in_cone(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pr93_ice_min,pr93_ice_max)
            if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX &
                 .and. nci(i,k,2).gt.0.0) pr93_ice_pair_valid=.true.
            call kdm6_ice_ng_pair_contract(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pidni,dmi,lamdaimin,lamdaimax, &
                 pr93_ice_ng_valid,pr93_ice_ng_min,pr93_ice_ng_max)
            if (.not.pr93_ice_pair_valid .or. &
                (qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. .not.pr93_ice_ng_valid)) &
              error stop 'PR93 ice PSD output failed consumer contract'
          endif




          if(supcol.gt.2. .and. qci(i,k,1).gt.qmin) then  
            supcolt=min(supcol,70.)
            Nic = exp(-2.80+0.262*(supcolt))*1000 
            ele1 = 7.37*t(i,k)/(288.*10.*p(i,k))/100 
            ele2 = 4.*pi*1.38E-23/(6.*pi*Rcn) 
            
            difa(i,k) = ele2*t(i,k)*(1.+ele1/Rcn)/(viscos(t(i,k),gas_density(i,k))*gas_density(i,k))
            pinuc = min((cmc)*difa(i,k)*2.*pi*Nic*n0c(i,k)/dry_carrier_density(i,k)/(muc+1) &
                *g4pmc*rslopecmu(i,k)*rslopec3(i,k)*rslopec2(i,k)*dtcld,qci(i,k,1))




            ninuc = 0.0d0
            if (nci(i,k,1) .gt. 0.0) then
              ninuc = min((difa(i,k))*2.*pi*Nic*n0c(i,k)/(muc+1) &
                      *g1pmc*rslopecmu(i,k)*rslopec2(i,k)*dtcld,nci(i,k,1))
            endif
            if (pinuc.ne.0.0d0 .or. ninuc.ne.0.0d0) then
              pr85_freeze_ice_transient_base = qci(i,k,2).gt.0.0 .and. &
                  qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX
              pr85_freeze_t_before = t(i,k)
              pr85_freeze_qc_before = qci(i,k,1)
              pr85_freeze_nc_before = nci(i,k,1)
              pr85_freeze_qi_before = qci(i,k,2)
              pr85_freeze_ni_before = nci(i,k,2)
              pr85_freeze_mass_request = pinuc
              pr85_freeze_number_request = ninuc
              call pr85_kdm6_freezing_packet(qci(i,k,1),nci(i,k,1), &
                   qci(i,k,2),nci(i,k,2),dry_carrier_density(i,k), &
                   DBLE(PR85_ICE_NATIVE_INACTIVE_MAX), &
                   pr85_freeze_mass_request,pr85_freeze_number_request, &
                   DBLE(pidnc)/(DBLE(lamdacmax)**DBLE(dmc)), &
                   DBLE(pidnc)/(DBLE(lamdacmin)**DBLE(dmc)), &
                   DBLE(pidni)/(DBLE(lamdaimax)**DBLE(dmi)), &
                   DBLE(pidni)/(DBLE(lamdaimin)**DBLE(dmi)), &
                   pr85_freeze_qc_after,pr85_freeze_nc_after, &
                   pr85_freeze_qi_after,pr85_freeze_ni_after, &
                   pr85_freeze_mass_approved,pr85_freeze_number_approved, &
                   pr85_freeze_fraction,pr85_freeze_base_valid,pr85_freeze_accepted)
              if (pr85_freeze_accepted) then
                if (.not.ieee_is_finite(pr85_freeze_t_before) .or. &
                    .not.ieee_is_finite(xlf) .or. .not.ieee_is_finite(cpm(i,k)) .or. &
                    cpm(i,k).le.0.0) then
                  pr85_freeze_accepted=.false.
                  pr85_freeze_base_valid=.false.
                else
                  pr85_freeze_t_candidate=DBLE(pr85_freeze_t_before)+ &
                      (DBLE(xlf)/DBLE(cpm(i,k)))*pr85_freeze_mass_approved
                  if (.not.ieee_is_finite(pr85_freeze_t_candidate) .or. &
                      pr85_freeze_t_candidate.le.0.0d0 .or. &
                      pr85_freeze_t_candidate.gt.DBLE(HUGE(0.0))) then
                    pr85_freeze_accepted=.false.
                    pr85_freeze_base_valid=.false.
                  else
                    pr85_freeze_t_after=REAL(pr85_freeze_t_candidate)
                    if (.not.ieee_is_finite(pr85_freeze_t_after) .or. &
                        pr85_freeze_t_after.le.0.0) then
                      pr85_freeze_accepted=.false.
                      pr85_freeze_base_valid=.false.
                    else
                      qci(i,k,1)=pr85_freeze_qc_after
                      nci(i,k,1)=pr85_freeze_nc_after
                      qci(i,k,2)=pr85_freeze_qi_after
                      nci(i,k,2)=pr85_freeze_ni_after
                      t(i,k)=pr85_freeze_t_after
                    endif
                  endif
                endif
                if (.not.pr85_freeze_accepted) then
                  pr85_freeze_fraction=0.0d0
                  pr85_freeze_mass_approved=0.0d0
                  pr85_freeze_number_approved=0.0d0
                  pr85_freeze_qc_after=pr85_freeze_qc_before
                  pr85_freeze_nc_after=pr85_freeze_nc_before
                  pr85_freeze_qi_after=pr85_freeze_qi_before
                  pr85_freeze_ni_after=pr85_freeze_ni_before
                  pr85_freeze_t_after=pr85_freeze_t_before
                endif
              else
                pr85_freeze_t_after=pr85_freeze_t_before
              endif
              open(newunit=pr85_freeze_unit,file='pr85_kdm6_freezing_budget.raw', &
                   status='unknown',position='append',action='write',iostat=pr85_freeze_ios)
              if (pr85_freeze_ios.ne.0) error stop 'PR85 freezing ledger open failed'
              write(pr85_freeze_unit,'(a,3i8,1x,3l1,1p,25e24.16)',iostat=pr85_freeze_ios) &
                   'PINU',i,lat,k,pr85_freeze_accepted,pr85_freeze_base_valid, &
                   pr85_freeze_ice_transient_base,pr85_freeze_fraction, &
                   pr85_freeze_mass_request,pr85_freeze_number_request, &
                   pr85_freeze_mass_approved,pr85_freeze_number_approved, &
                   pr85_freeze_mass_request-pr85_freeze_mass_approved, &
                   pr85_freeze_number_request-pr85_freeze_number_approved, &
                   DBLE(pr85_freeze_qc_before),DBLE(pr85_freeze_nc_before), &
                   DBLE(pr85_freeze_qi_before),DBLE(pr85_freeze_ni_before), &
                   DBLE(qci(i,k,1)),DBLE(nci(i,k,1)),DBLE(qci(i,k,2)),DBLE(nci(i,k,2)), &
                   DBLE(pr85_freeze_t_before),DBLE(t(i,k)), &
                   DBLE(dry_carrier_density(i,k))*(DBLE(pr85_freeze_qc_before)-DBLE(qci(i,k,1))), &
                   DBLE(dry_carrier_density(i,k))*(DBLE(qci(i,k,2))-DBLE(pr85_freeze_qi_before)), &
                   DBLE(dry_carrier_density(i,k))*((DBLE(qci(i,k,2))-DBLE(pr85_freeze_qi_before))- &
                       (DBLE(pr85_freeze_qc_before)-DBLE(qci(i,k,1)))), &
                   DBLE(pr85_freeze_nc_before)-DBLE(nci(i,k,1)), &
                   DBLE(nci(i,k,2))-DBLE(pr85_freeze_ni_before), &
                   (DBLE(nci(i,k,2))-DBLE(pr85_freeze_ni_before))- &
                       (DBLE(pr85_freeze_nc_before)-DBLE(nci(i,k,1))), &
                   DBLE(dry_carrier_density(i,k)),DBLE(qmin)
              if (pr85_freeze_ios.ne.0) error stop 'PR85 freezing ledger write failed'
              close(pr85_freeze_unit,iostat=pr85_freeze_ios)
              if (pr85_freeze_ios.ne.0) error stop 'PR85 freezing ledger close failed'
              if (.not.pr85_freeze_base_valid) &
                   error stop 'PR85 invalid cloud-ice freezing packet base'
            endif
          endif




          if(supcol.gt.0. .and. qci(i,k,1).gt.qmin) then
            supcolt=min(supcol,70.)
            pfrzdtc = min((cmc)*cmc*pfrz1*n0c(i,k)/dry_carrier_density(i,k)/denr/(muc+1)       &
                    *(exp(pfrz2*supcolt)-1.)*g1p2dcomuc1*rslopecmu(i,k)        &
                    *rslopecd(i,k)*rslopecd(i,k)*rslopec(i,k)*dtcld            &  
                
                
                     ,qci(i,k,1))




            nfrzdtc = 0.0
            if(nci(i,k,1).gt.0.0) then
              nfrzdtc = min((cmc)*pfrz1*n0c(i,k)/denr/(muc+1)        &
                       *(exp(pfrz2*supcolt)-1.)*g1pdcomuc1*rslopecmu(i,k)       &
                       *rslopec(i,k)*rslopecd(i,k)*dtcld,nci(i,k,1))
            endif
            if (pfrzdtc.ne.0.0 .or. nfrzdtc.ne.0.0) then
              pr85_freeze_ice_transient_base = qci(i,k,2).gt.0.0 .and. &
                  qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX
              pr85_freeze_t_before = t(i,k)
              pr85_freeze_qc_before = qci(i,k,1)
              pr85_freeze_nc_before = nci(i,k,1)
              pr85_freeze_qi_before = qci(i,k,2)
              pr85_freeze_ni_before = nci(i,k,2)
              pr85_freeze_mass_request = DBLE(pfrzdtc)
              pr85_freeze_number_request = DBLE(nfrzdtc)
              call pr85_kdm6_freezing_packet(qci(i,k,1),nci(i,k,1), &
                   qci(i,k,2),nci(i,k,2),dry_carrier_density(i,k), &
                   DBLE(PR85_ICE_NATIVE_INACTIVE_MAX), &
                   pr85_freeze_mass_request,pr85_freeze_number_request, &
                   DBLE(pidnc)/(DBLE(lamdacmax)**DBLE(dmc)), &
                   DBLE(pidnc)/(DBLE(lamdacmin)**DBLE(dmc)), &
                   DBLE(pidni)/(DBLE(lamdaimax)**DBLE(dmi)), &
                   DBLE(pidni)/(DBLE(lamdaimin)**DBLE(dmi)), &
                   pr85_freeze_qc_after,pr85_freeze_nc_after, &
                   pr85_freeze_qi_after,pr85_freeze_ni_after, &
                   pr85_freeze_mass_approved,pr85_freeze_number_approved, &
                   pr85_freeze_fraction,pr85_freeze_base_valid,pr85_freeze_accepted)
              if (pr85_freeze_accepted) then
                if (.not.ieee_is_finite(pr85_freeze_t_before) .or. &
                    .not.ieee_is_finite(xlf) .or. .not.ieee_is_finite(cpm(i,k)) .or. &
                    cpm(i,k).le.0.0) then
                  pr85_freeze_accepted=.false.
                  pr85_freeze_base_valid=.false.
                else
                  pr85_freeze_t_candidate=DBLE(pr85_freeze_t_before)+ &
                      (DBLE(xlf)/DBLE(cpm(i,k)))*pr85_freeze_mass_approved
                  if (.not.ieee_is_finite(pr85_freeze_t_candidate) .or. &
                      pr85_freeze_t_candidate.le.0.0d0 .or. &
                      pr85_freeze_t_candidate.gt.DBLE(HUGE(0.0))) then
                    pr85_freeze_accepted=.false.
                    pr85_freeze_base_valid=.false.
                  else
                    pr85_freeze_t_after=REAL(pr85_freeze_t_candidate)
                    if (.not.ieee_is_finite(pr85_freeze_t_after) .or. &
                        pr85_freeze_t_after.le.0.0) then
                      pr85_freeze_accepted=.false.
                      pr85_freeze_base_valid=.false.
                    else
                      qci(i,k,1)=pr85_freeze_qc_after
                      nci(i,k,1)=pr85_freeze_nc_after
                      qci(i,k,2)=pr85_freeze_qi_after
                      nci(i,k,2)=pr85_freeze_ni_after
                      t(i,k)=pr85_freeze_t_after
                    endif
                  endif
                endif
                if (.not.pr85_freeze_accepted) then
                  pr85_freeze_fraction=0.0d0
                  pr85_freeze_mass_approved=0.0d0
                  pr85_freeze_number_approved=0.0d0
                  pr85_freeze_qc_after=pr85_freeze_qc_before
                  pr85_freeze_nc_after=pr85_freeze_nc_before
                  pr85_freeze_qi_after=pr85_freeze_qi_before
                  pr85_freeze_ni_after=pr85_freeze_ni_before
                  pr85_freeze_t_after=pr85_freeze_t_before
                endif
              else
                pr85_freeze_t_after=pr85_freeze_t_before
              endif
              open(newunit=pr85_freeze_unit,file='pr85_kdm6_freezing_budget.raw', &
                   status='unknown',position='append',action='write',iostat=pr85_freeze_ios)
              if (pr85_freeze_ios.ne.0) error stop 'PR85 freezing ledger open failed'
              write(pr85_freeze_unit,'(a,3i8,1x,3l1,1p,25e24.16)',iostat=pr85_freeze_ios) &
                   'PFRZ',i,lat,k,pr85_freeze_accepted,pr85_freeze_base_valid, &
                   pr85_freeze_ice_transient_base,pr85_freeze_fraction, &
                   pr85_freeze_mass_request,pr85_freeze_number_request, &
                   pr85_freeze_mass_approved,pr85_freeze_number_approved, &
                   pr85_freeze_mass_request-pr85_freeze_mass_approved, &
                   pr85_freeze_number_request-pr85_freeze_number_approved, &
                   DBLE(pr85_freeze_qc_before),DBLE(pr85_freeze_nc_before), &
                   DBLE(pr85_freeze_qi_before),DBLE(pr85_freeze_ni_before), &
                   DBLE(qci(i,k,1)),DBLE(nci(i,k,1)),DBLE(qci(i,k,2)),DBLE(nci(i,k,2)), &
                   DBLE(pr85_freeze_t_before),DBLE(t(i,k)), &
                   DBLE(dry_carrier_density(i,k))*(DBLE(pr85_freeze_qc_before)-DBLE(qci(i,k,1))), &
                   DBLE(dry_carrier_density(i,k))*(DBLE(qci(i,k,2))-DBLE(pr85_freeze_qi_before)), &
                   DBLE(dry_carrier_density(i,k))*((DBLE(qci(i,k,2))-DBLE(pr85_freeze_qi_before))- &
                       (DBLE(pr85_freeze_qc_before)-DBLE(qci(i,k,1)))), &
                   DBLE(pr85_freeze_nc_before)-DBLE(nci(i,k,1)), &
                   DBLE(nci(i,k,2))-DBLE(pr85_freeze_ni_before), &
                   (DBLE(nci(i,k,2))-DBLE(pr85_freeze_ni_before))- &
                       (DBLE(pr85_freeze_nc_before)-DBLE(nci(i,k,1))), &
                   DBLE(dry_carrier_density(i,k)),DBLE(qmin)
              if (pr85_freeze_ios.ne.0) error stop 'PR85 freezing ledger write failed'
              close(pr85_freeze_unit,iostat=pr85_freeze_ios)
              if (pr85_freeze_ios.ne.0) error stop 'PR85 freezing ledger close failed'
              if (.not.pr85_freeze_base_valid) &
                   error stop 'PR85 invalid cloud-ice freezing packet base'
            endif
          endif




          if(supcol.gt.0. .and. qrs(i,k,1).gt.0.) then
            supcolt=min(supcol,70.)
            pfrzdtr = min((cmr)*cmr*pfrz1*n0r(i,k)/dry_carrier_density(i,k)/denr          &
                  *(exp(pfrz2*supcolt)-1.)*rsloped(i,k,1)*rsloped(i,k,1)       & 
                  *rslopemu(i,k,1)*rslope(i,k,1)*g1p2drmr*dtcld,qrs(i,k,1))        




            nfrzdtr = 0.0
            if(nrs(i,k,1).gt.nrmin) then
              nfrzdtr = min((cmr)/denr*pfrz1*n0r(i,k)*(exp(pfrz2*supcolt)-1.)     &
                       *g1pdrmr*rslope(i,k,1)*rsloped(i,k,1)*rslopemu(i,k,1) &
                       *dtcld, nrs(i,k,1))
            endif
            if (pfrzdtr.ne.0.0 .or. nfrzdtr.ne.0.0) then
              pr85_rf_qr_before=qrs(i,k,1)
              pr85_rf_nr_before=nrs(i,k,1)
              pr85_rf_qg_before=qrs(i,k,3)
              pr85_rf_bg_before=brs(i,k)
              pr85_rf_t_before=t(i,k)
              pr85_rf_mass_request=DBLE(pfrzdtr)
              pr85_rf_number_request=DBLE(nfrzdtr)
              pr85_rf_volume_request=DBLE(pfrzdtr)/DBLE(denr)
              pr89_rf_rain_min=DBLE(dry_carrier_density(i,k))* &
                   (DBLE(lamdarmin)**DBLE(dmr))/DBLE(pidnr)
              pr89_rf_rain_max=DBLE(dry_carrier_density(i,k))* &
                   (DBLE(lamdarmax)**DBLE(dmr))/DBLE(pidnr)
              call kdm6_rain_ng_pair_valid(pr85_rf_qr_before,pr85_rf_nr_before, &
                   pr89_rf_rain_min,pr89_rf_rain_max,.true., &
                   rain_full_evap_pending(i,k),pr89_rf_next_valid,pr89_rf_failure_reason)
              if (pr89_rf_next_valid) then
                pr89_rf_next_valid=kdm6_progb_density_pair_valid( &
                     pr85_rf_qg_before,pr85_rf_bg_before,100.0,900.0)
                if (.not.pr89_rf_next_valid) pr89_rf_failure_reason=9
              endif
              if (pr89_rf_next_valid) then
                if (.not.ieee_is_finite(pr85_rf_t_before)) then
                  pr89_rf_next_valid=.false.
                  pr89_rf_failure_reason=8
                elseif (pr85_rf_t_before.le.0.0) then
                  pr89_rf_next_valid=.false.
                  pr89_rf_failure_reason=8
                endif
              endif
              pr85_rf_base_valid=pr89_rf_next_valid
              pr85_rf_accepted=.false.
              pr85_rf_fraction=0.0d0
              pr85_rf_mass_approved=0.0d0
              pr85_rf_number_approved=0.0d0
              pr85_rf_volume_approved=0.0d0
              pr85_rf_qr_after=pr85_rf_qr_before
              pr85_rf_nr_after=pr85_rf_nr_before
              pr85_rf_qg_after=pr85_rf_qg_before
              pr85_rf_bg_after=pr85_rf_bg_before
              pr85_rf_t_after=pr85_rf_t_before
              if (pr85_rf_base_valid) then
                pr89_rf_gamma=1.0d0
                do pr89_rf_attempt=0,48
                  call pr85_kdm6_rain_freezing_packet( &
                       pr85_rf_qr_before,pr85_rf_nr_before,pr85_rf_qg_before, &
                       pr85_rf_bg_before,dry_carrier_density(i,k), &
                       pr89_rf_gamma*pr85_rf_mass_request, &
                       pr89_rf_gamma*pr85_rf_number_request, &
                       pr89_rf_gamma*pr85_rf_volume_request, &
                       DBLE(pidnr)/(DBLE(lamdarmax)**DBLE(dmr)), &
                       DBLE(pidnr)/(DBLE(lamdarmin)**DBLE(dmr)),100.0d0,900.0d0, &
                       pr85_rf_qr_after,pr85_rf_nr_after,pr85_rf_qg_after,pr85_rf_bg_after, &
                       pr85_rf_mass_approved,pr85_rf_number_approved, &
                       pr85_rf_volume_approved,pr85_rf_fraction, &
                       pr85_rf_base_valid,pr85_rf_accepted)
                  if (.not.pr85_rf_base_valid) exit
                  if (pr85_rf_accepted) then
                    if (.not.ieee_is_finite(pr85_rf_t_before)) then
                      pr85_rf_accepted=.false.
                      pr89_rf_failure_reason=8
                    elseif (.not.ieee_is_finite(xlf)) then
                      pr85_rf_accepted=.false.
                    elseif (.not.ieee_is_finite(cpm(i,k))) then
                      pr85_rf_accepted=.false.
                    elseif (cpm(i,k).le.0.0) then
                      pr85_rf_accepted=.false.
                    else
                      pr85_rf_t_candidate=DBLE(pr85_rf_t_before)+ &
                           (DBLE(xlf)/DBLE(cpm(i,k)))*pr85_rf_mass_approved
                      if (.not.ieee_is_finite(pr85_rf_t_candidate)) then
                        pr85_rf_accepted=.false.
                      elseif (pr85_rf_t_candidate.le.0.0d0) then
                        pr85_rf_accepted=.false.
                      elseif (pr85_rf_t_candidate.gt.DBLE(HUGE(0.0))) then
                        pr85_rf_accepted=.false.
                      else
                        pr85_rf_t_after=REAL(pr85_rf_t_candidate)
                        if (.not.ieee_is_finite(pr85_rf_t_after)) then
                          pr85_rf_accepted=.false.
                        elseif (pr85_rf_t_after.le.0.0) then
                          pr85_rf_accepted=.false.
                        else
                          call kdm6_rain_ng_pair_valid(pr85_rf_qr_after,pr85_rf_nr_after, &
                               pr89_rf_rain_min,pr89_rf_rain_max,.true., &
                               rain_full_evap_pending(i,k),pr89_rf_next_valid, &
                               pr89_rf_failure_reason)
                          if (pr89_rf_next_valid) then
                            pr89_rf_next_valid=kdm6_progb_density_pair_valid( &
                                 pr85_rf_qg_after,pr85_rf_bg_after,100.0,900.0)
                            if (.not.pr89_rf_next_valid) pr89_rf_failure_reason=9
                          endif
                          if (pr89_rf_next_valid) then
                            pr85_rf_fraction=pr89_rf_gamma*pr85_rf_fraction
                            pr85_rf_accepted=.true.
                            exit
                          endif
                        endif
                      endif
                      pr85_rf_accepted=.false.
                    endif
                  endif
                  pr89_rf_gamma=0.5d0*pr89_rf_gamma
                enddo
              endif
              if (pr85_rf_accepted) then
                qrs(i,k,1)=pr85_rf_qr_after
                nrs(i,k,1)=pr85_rf_nr_after
                qrs(i,k,3)=pr85_rf_qg_after
                brs(i,k)=pr85_rf_bg_after
                t(i,k)=pr85_rf_t_after
              else
                pr85_rf_fraction=0.0d0
                pr85_rf_mass_approved=0.0d0
                pr85_rf_number_approved=0.0d0
                pr85_rf_volume_approved=0.0d0
                pr85_rf_qr_after=pr85_rf_qr_before
                pr85_rf_nr_after=pr85_rf_nr_before
                pr85_rf_qg_after=pr85_rf_qg_before
                pr85_rf_bg_after=pr85_rf_bg_before
                pr85_rf_t_after=pr85_rf_t_before
              endif
              open(newunit=pr85_rf_unit,file='pr85_rain_freezing_budget.raw', &
                   form='formatted',status='unknown',position='append',action='write',iostat=pr85_rf_ios)
              if (pr85_rf_ios.ne.0) error stop 'PR85 rain-freezing ledger open failed'
              write(pr85_rf_unit,'(a)',iostat=pr85_rf_ios) &
                   '# PR85_RAIN_FREEZE: i,lat,k,loop,accepted,base_valid,theta; proposed/approved/withheld '// &
                   'dQR kg/kg-dry, dNR #/m3, dBG m3/kg-dry; before/after QR,NR,QG,BG; T K; '// &
                   'actual rain/graupel mass kg/m3 and residual; actual/approved number and volume '// &
                   'deltas; final graupel density kg/m3'
              if (pr85_rf_ios.ne.0) error stop 'PR85 rain-freezing ledger header failed'
              write(pr85_rf_unit,'(a,4i8,1x,2l1,1p,28e24.16)',iostat=pr85_rf_ios) &
                   'PR85_RAIN_FREEZE',i,lat,k,loop,pr85_rf_accepted,pr85_rf_base_valid,pr85_rf_fraction, &
                   pr85_rf_mass_request,pr85_rf_number_request,pr85_rf_volume_request, &
                   pr85_rf_mass_approved,pr85_rf_number_approved,pr85_rf_volume_approved, &
                   pr85_rf_mass_request-pr85_rf_mass_approved, &
                   pr85_rf_number_request-pr85_rf_number_approved, &
                   pr85_rf_volume_request-pr85_rf_volume_approved, &
                   DBLE(pr85_rf_qr_before),DBLE(pr85_rf_nr_before), &
                   DBLE(pr85_rf_qg_before),DBLE(pr85_rf_bg_before), &
                   DBLE(qrs(i,k,1)),DBLE(nrs(i,k,1)),DBLE(qrs(i,k,3)),DBLE(brs(i,k)), &
                   DBLE(pr85_rf_t_before),DBLE(t(i,k)), &
                   DBLE(dry_carrier_density(i,k))*(DBLE(pr85_rf_qr_before)-DBLE(qrs(i,k,1))), &
                   DBLE(dry_carrier_density(i,k))*(DBLE(qrs(i,k,3))-DBLE(pr85_rf_qg_before)), &
                   DBLE(dry_carrier_density(i,k))*((DBLE(pr85_rf_qr_before)+DBLE(pr85_rf_qg_before))- &
                       (DBLE(qrs(i,k,1))+DBLE(qrs(i,k,3)))), &
                   DBLE(pr85_rf_nr_before)-DBLE(nrs(i,k,1)), &
                   (DBLE(pr85_rf_nr_before)-DBLE(nrs(i,k,1)))-pr85_rf_number_approved, &
                   DBLE(brs(i,k))-DBLE(pr85_rf_bg_before), &
                   (DBLE(brs(i,k))-DBLE(pr85_rf_bg_before))-pr85_rf_volume_approved, &
                   DBLE(qrs(i,k,3))/MAX(DBLE(brs(i,k)),TINY(1.0d0))
              if (pr85_rf_ios.ne.0) error stop 'PR85 rain-freezing ledger write failed'
              close(pr85_rf_unit,iostat=pr85_rf_ios)
              if (pr85_rf_ios.ne.0) error stop 'PR85 rain-freezing ledger close failed'
              if (.not.pr85_rf_base_valid) &
                   error stop 'PR85 invalid rain-graupel freezing base'
            endif
          endif
        enddo
      enddo

      do k = kts, kte
        do i = its, ite
          nrs(i,k,1) = max(nrs(i,k,1),0.0)
          nci(i,k,1) = max(nci(i,k,1),0.0)
          nci(i,k,2) = max(nci(i,k,2),0.0)
        enddo
      enddo




      do k = kts, kte
        do i = its, ite
          qrs_tmp(i,k,1) = qrs(i,k,1)
          qrs_tmp(i,k,2) = qrs(i,k,2)
          qrs_tmp(i,k,3) = qrs(i,k,3)
          qci_tmp(i,k) = qci(i,k,2)
          nci_tmp(i,k) = nci(i,k,2)
          nrs_tmp(i,k) = nrs(i,k,1)
        enddo
      enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)
   call pr87_report_graupel_consumer(5,pr87_model_timestep,lat, &
        its,ite,kts,kte,qrs_tmp,brs,progb_status)


   call pr77_scan_slope_state(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp,its,ite,kts,kte,lat, &
        'KDM62D_SLOPE_05')
   call validate_kdm6_slope_states(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp)
   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,terminal_velocity_mass,terminal_velocity_number,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax,progb_status)

      do k = kts, kte
        do i = its, ite





          if(qci(i,k,1).le.qmin .or. nci(i,k,1).le.ncmin) then
            rslopec(i,k) = rslopecmax
            rslopec2(i,k) = rslopec2max
            rslopec3(i,k) = rslopec3max
            rslopecmu(i,k) = rslopecmmax
            rslopecd(i,k) = rslopecdmax 
          else
            rslopec(i,k) = 1./lamdac(qci(i,k,1),dry_carrier_density(i,k),nci(i,k,1))
            rslopec2(i,k) = (rslopec(i,k))*rslopec(i,k)
            rslopec3(i,k) = (rslopec2(i,k))*rslopec(i,k)
            rslopecmu(i,k) = DBLE(rslopec(i,k))**muc
            rslopecd(i,k) = (rslopec(i,k))**dmc
          endif


          call pr77_scan_local_state(qrs(i,k,1),nrs(i,k,1), &
               qci(i,k,1),nci(i,k,1),qci(i,k,2),nci(i,k,2), &
               qrs(i,k,3),brs(i,k),i,k,lat,'KDM62D_LOCAL_02')
          call validate_local_species_states(qrs(i,k,1),nrs(i,k,1), &
               qci(i,k,1),nci(i,k,1),qci(i,k,2),nci(i,k,2), &
               qrs(i,k,3),brs(i,k))
          n0r(i,k) = 0.0
          n0c(i,k) = 0.0
          n0i(i,k) = 0.0
          if (classify_species_state(qrs(i,k,1),nrs(i,k,1)) == SPECIES_ACTIVE) &
            n0r(i,k) = nrs(i,k,1)/(rslope(i,k,1)*rslopemu(i,k,1)*g1pmr)
          if (classify_species_state(qci(i,k,1),nci(i,k,1)) == SPECIES_ACTIVE) &
            n0c(i,k) = (muc+1)*nci(i,k,1)/(rslopec(i,k)*rslopecmu(i,k))
          if (classify_species_state(qci(i,k,2),nci(i,k,2)) == SPECIES_ACTIVE) &
            n0i(i,k) = nci(i,k,2)/(rslope(i,k,4)*rslopemu(i,k,4)*g1pmi)
          n0so(i,k) = (n0s)/g1pms/(rslopemu(i,k,2))
          if (progb_status(i,k) == PROGB_PSD_ACTIVE) then
            n0go(i,k) = (n0g)/g1pmg/(rslopemu(i,k,3))
          else
            n0go(i,k) = 0.0
          endif
          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then
            lamdr_tmp(i,k) = exp(log((((pidnr)*nrs(i,k,1))                       &
                         /(dry_carrier_density(i,k)*qrs(i,k,1))))*(1./dmr))
            n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            if(lamdr_tmp(i,k) .le. lamdarmin) then
              lamdr_tmp(i,k) = lamdarmin
              pr85_psd_before = nrs(i,k,1)
              call pr85_kdm6_psd_bound_number(qrs(i,k,1),dry_carrier_density(i,k),lamdr_tmp(i,k), &
                   lamdarmin,lamdarmax,pidnr,dmr,1, &
                   'rain','stage2',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nrs(i,k,1) = pr85_psd_directed
              n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            elseif(lamdr_tmp(i,k) .ge. lamdarmax) then
              lamdr_tmp(i,k) = lamdarmax
              pr85_psd_before = nrs(i,k,1)
              call pr85_kdm6_psd_bound_number(qrs(i,k,1),dry_carrier_density(i,k),lamdr_tmp(i,k), &
                   lamdarmin,lamdarmax,pidnr,dmr,2, &
                   'rain','stage2',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nrs(i,k,1) = pr85_psd_directed
              n0r(i,k) = (1./g1pmr)*DBLE(nrs(i,k,1))*lamdr_tmp(i,k)**(mur+1)
            endif
          endif
          if(qci(i,k,1).ge.qmin .and. nci(i,k,1) .ge. ncmin ) then
            lamdc_tmp(i,k) = exp(log((((pidnc)*nci(i,k,1))                       &
                         /(dry_carrier_density(i,k)*qci(i,k,1))))*(1./dmc))
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            if(lamdc_tmp(i,k) .le. lamdacmin) then
              lamdc_tmp(i,k) = lamdacmin
              pr85_psd_before = nci(i,k,1)
              call pr85_kdm6_psd_bound_number(qci(i,k,1),dry_carrier_density(i,k),lamdc_tmp(i,k), &
                   lamdacmin,lamdacmax,pidnc,dmc,1, &
                   'cloud','stage2',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,1) = pr85_psd_directed
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            elseif(lamdc_tmp(i,k) .ge. lamdacmax) then
              lamdc_tmp(i,k) = lamdacmax
              pr85_psd_before = nci(i,k,1)
              call pr85_kdm6_psd_bound_number(qci(i,k,1),dry_carrier_density(i,k),lamdc_tmp(i,k), &
                   lamdacmin,lamdacmax,pidnc,dmc,2, &
                   'cloud','stage2',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,1) = pr85_psd_directed
              n0c(i,k) = (muc+1)*DBLE(nci(i,k,1))*lamdc_tmp(i,k)**(muc+1)
            endif
          endif
          if(qci(i,k,2).ge. 1.e-14 ) then
            if (.not.all(ieee_is_finite([qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k)])) .or. nci(i,k,2).le.0.0 .or. &
                 dry_carrier_density(i,k).le.0.0) &
              error stop 'PR93 invalid active ice PSD input'
            lamdi_tmp(i,k) = exp(log((((pidni)*nci(i,k,2))                       &
                         /(dry_carrier_density(i,k)*qci(i,k,2))))*(1./dmi))
            n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            pr93_ice_min=DBLE(pidni)/(DBLE(lamdaimax)**DBLE(dmi))
            pr93_ice_max=DBLE(pidni)/(DBLE(lamdaimin)**DBLE(dmi))
            pr93_ice_pair_valid=pr93_kdm6_pair_in_cone(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pr93_ice_min,pr93_ice_max)
            if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX &
                 .and. nci(i,k,2).gt.0.0) pr93_ice_pair_valid=.true.
            call kdm6_ice_ng_pair_contract(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pidni,dmi,lamdaimin,lamdaimax, &
                 pr93_ice_ng_valid,pr93_ice_ng_min,pr93_ice_ng_max)
            if (qci(i,k,2).gt.0.0 .and. &
                qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX .and. nci(i,k,2).gt.0.0) &
              pr93_ice_ng_valid=.true.
            pr93_ice_direct_repair=lamdi_tmp(i,k).gt.lamdaimin .and. &
                 lamdi_tmp(i,k).lt.lamdaimax .and. &
                 (.not.pr93_ice_pair_valid .or. .not.pr93_ice_ng_valid)
            if(lamdi_tmp(i,k) .le. lamdaimin .or. &
                 (qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. &
                  .not.pr93_ice_ng_valid .and. DBLE(nci(i,k,2)).lt.pr93_ice_ng_min)) then
              lamdi_tmp(i,k) = lamdaimin
              pr85_psd_before = nci(i,k,2)
              call pr85_kdm6_psd_bound_number(qci(i,k,2),dry_carrier_density(i,k),lamdi_tmp(i,k), &
                   lamdaimin,lamdaimax,pidni,dmi,1, &
                   'ice','stage2',i,lat,k,pr85_psd_before,pr85_psd_native_available, &
                   (pr67_trace_this_call.or.pr93_ice_direct_repair), &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,2) = pr85_psd_directed
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            elseif(lamdi_tmp(i,k) .ge. lamdaimax .or. &
                 (qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. &
                  .not.pr93_ice_ng_valid .and. DBLE(nci(i,k,2)).gt.pr93_ice_ng_max)) then
              lamdi_tmp(i,k) = lamdaimax
              pr85_psd_before = nci(i,k,2)
              call pr85_kdm6_psd_bound_number(qci(i,k,2),dry_carrier_density(i,k),lamdi_tmp(i,k), &
                   lamdaimin,lamdaimax,pidni,dmi,2, &
                   'ice','stage2',i,lat,k,pr85_psd_before,pr85_psd_native_available, &
                   (pr67_trace_this_call.or.pr93_ice_direct_repair), &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,2) = pr85_psd_directed
              n0i(i,k) = (1./g1pmi)*DBLE(nci(i,k,2))*lamdi_tmp(i,k)**(mui+1)
            endif
            pr93_ice_pair_valid=pr93_kdm6_pair_in_cone(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pr93_ice_min,pr93_ice_max)
            if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX &
                 .and. nci(i,k,2).gt.0.0) pr93_ice_pair_valid=.true.
            call kdm6_ice_ng_pair_contract(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pidni,dmi,lamdaimin,lamdaimax, &
                 pr93_ice_ng_valid,pr93_ice_ng_min,pr93_ice_ng_max)
            if (.not.pr93_ice_pair_valid .or. &
                (qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. .not.pr93_ice_ng_valid)) &
              error stop 'PR93 ice PSD output failed consumer contract'
          endif




          avedia(i,k,1) = rslopec(i,k)*(g3pmc)**(1./3.)
          avedia(i,k,2) = rslope(i,k,1)*((g4pmr/g1pmr)**(.3333333))
          avedia(i,k,3) = rslope(i,k,4)*((g4pmi/g1pmi)**(.3333333))
          sigma(i,k,1) = rslopec(i,k)*(g6pmc-g3pmc*g3pmc)**(1./6.)
        enddo
      enddo

      do k = kts, kte
        do i = its, ite
          work1(i,k,1) = diffac(xl(i,k),p(i,k),t(i,k),dry_carrier_density(i,k),qs(i,k,1))
          work1(i,k,2) = diffac(xls,p(i,k),t(i,k),dry_carrier_density(i,k),qs(i,k,2))
          work2(i,k) = venfac(p(i,k),t(i,k),gas_density(i,k))
        enddo
      enddo









      do k = kts, kte
        do i = its, ite
          supsat = max(q(i,k),qmin)-qs(i,k,1)
          satdt = supsat/dtcld






         lencon  = 2.7e-2*dry_carrier_density(i,k)*qci(i,k,1)*(1.e20/16.*avedia(i,k,1) &
                  *(sigma(i,k,1)**3)-0.4)
         lenconcr = max(1.2*lencon, qcrmin)
         if(qci(i,k,1).gt.qcr(i,k) .and. nci(i,k,1).gt.ncmin) then
           praut(i,k) = (qck1)*qci(i,k,1)**(7./3.)*nci(i,k,1)**(-1./3.)
           praut(i,k) = min(praut(i,k),qci(i,k,1)/dtcld)




           nraut(i,k) = (3.5e9)*dry_carrier_density(i,k)*praut(i,k)
           if(qrs(i,k,1).gt.lenconcr)                                           &
           nraut(i,k) = nrs(i,k,1)/qrs(i,k,1)*praut(i,k)
           nraut(i,k) = min(nraut(i,k),nci(i,k,1)/dtcld)
         endif






          if(qrs(i,k,1).ge.lenconcr) then
            if(avedia(i,k,2).ge.di100) then
              nracw(i,k) = min((ncrk1)*nci(i,k,1)*nrs(i,k,1)                          &
                         *((rslopec3(i,k))*g3pmc +(rslope3(i,k,1))*(g4pmr/g1pmr))     &
                         ,nci(i,k,1)/dtcld)
              pracw(i,k) = min(((cmc)/dry_carrier_density(i,k))*ncrk1*nci(i,k,1)                      &
                         *nrs(i,k,1)*rslopec3(i,k)*((rslopec3(i,k))*g6pmc             &
                         +(rslope3(i,k,1))*g3pmc*(g4pmr/g1pmr)),qci(i,k,1)/dtcld)
            else
              nracw(i,k) = min((ncrk2)*nci(i,k,1)*nrs(i,k,1)                          &
                         *((rslopec3(i,k))*rslopec3(i,k)*g6pmc                        &
                         +(rslope3(i,k,1))*rslope3(i,k,1))*(g7pmr/g1pmr)              &
                         ,nci(i,k,1)/dtcld)
              pracw(i,k) = min(((cmc)/dry_carrier_density(i,k))*ncrk2*nci(i,k,1)                      &
                         *nrs(i,k,1)*rslopec3(i,k)*((rslopec3(i,k))*rslopec3(i,k)     &
                         *g9pmc+(rslope3(i,k,1))*rslope3(i,k,1)*g3pmc*(g7pmr/g1pmr))  &
                         ,qci(i,k,1)/dtcld)
            endif
          endif 




          if(avedia(i,k,1).ge.di100) then

            nccol(i,k) = (ncrk1)*nci(i,k,1)*nci(i,k,1)*rslopec3(i,k)     &
                         *g3pmc
          else
            nccol(i,k) = (ncrk2)*nci(i,k,1)*nci(i,k,1)*rslopec3(i,k)        &
                         *rslopec3(i,k)*g6pmc
          endif




          if(qrs(i,k,1).ge.lenconcr) then
            if(avedia(i,k,2).lt.di100) then

              nrcol(i,k) = (ncrk2)*nrs(i,k,1)*nrs(i,k,1)*rslope3(i,k,1) &
                          *rslope3(i,k,1)*(g7pmr/g1pmr)
            elseif(avedia(i,k,2).ge.di100 .and. avedia(i,k,2).lt.di600) then
              nrcol(i,k) = (ncrk1)*nrs(i,k,1)*nrs(i,k,1)*rslope3(i,k,1)&
                          *(g4pmr/g1pmr)
            elseif(avedia(i,k,2).ge.di600 .and. avedia(i,k,2).lt.di2000) then
              coecol = (-2.5e3)*eccbrk*(avedia(i,k,2)-di600)
              nrcol(i,k) = (exp(coecol))*ncrk1*nrs(i,k,1)*nrs(i,k,1) &
                         *rslope3(i,k,1)*(g4pmr/g1pmr)
            else
              nrcol(i,k) = (0.)
            endif
          endif




          if(qrs(i,k,1).gt.0.) then
            coeres = (rslope2(i,k,1))*sqrt(rslope(i,k,1)*rslopeb(i,k,1))&
                     *rslopemu(i,k,1)
            prevp(i,k) = ((rh(i,k,1)-1.))*n0r(i,k)*(precr1*rslope2(i,k,1)&
                        *rslopemu(i,k,1)+(precr2)*work2(i,k)*coeres)/work1(i,k,1)

            prevp(i,k) = fac_evap*prevp(i,k) 

            if(prevp(i,k).lt.0.) then
              prevp(i,k) = max(prevp(i,k),-(qrs(i,k,1))/dtcld)
              prevp(i,k) = max(prevp(i,k),(satdt)/2)




              if(prevp(i,k).eq.-qrs(i,k,1)/dtcld) then
                rain_full_evap_pending(i,k) = .true.
              endif
            else
              prevp(i,k) = min(prevp(i,k),(satdt)/2)
            endif
          endif
        enddo
      enddo














      do k = kts, kte
        do i = its, ite
          supcol = t0c-t(i,k)
          n0sfac(i,k) = max(min(exp(alpha*supcol),n0smax/n0s),1.)
          supsat = max(q(i,k),qmin)-qs(i,k,2)
          satdt = supsat/dtcld
          ifsat = 0

          eacsi = exp(0.07*(-supcol))
          vt2i=DBLE(pvti)*rslopeb(i,k,4)*denfac(i,k)
          vt2r=DBLE(pvtr)*rslopeb(i,k,1)*denfac(i,k)
          vt2s=DBLE(pvts)*rslopeb(i,k,2)*denfac(i,k)
          if (progb_status(i,k) == PROGB_PSD_ACTIVE) then
            vt2g(i,k)=DBLE(pvtg(i,k))*rslopeb(i,k,3)*denfac(i,k)
          else
            vt2g(i,k)=0.0
          endif
          qsum(i,k) = max((qrs(i,k,2)+qrs(i,k,3)),1.e-15)
          if(supcol.gt.0.) then




          if(qci(i,k,2).gt.qmin .and. qrs(i,k,1).gt.qcrmin) then

              acrfac=(g3pmr)*rslopemu(i,k,1)*rslope3(i,k,1)*g1pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope(i,k,4)&
              +(2.)*g2pmr*rslopemu(i,k,1)*rslope2(i,k,1)*g2pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope2(i,k,4)&
              +(g1pmr)*rslopemu(i,k,1)*rslope(i,k,1)*g3pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope3(i,k,4)

                praci(i,k)=(pi)*cmi*n0i(i,k)*n0r(i,k)*abs(vt2r-vt2i)/(4*dry_carrier_density(i,k))*acrfac*eacri

                
                praci(i,k) =praci(i,k)*min(max(0.0,qrs(i,k,1)/qci(i,k,2)),1.)**2
                praci(i,k) = min(praci(i,k),(qci(i,k,2))/dtcld)






             acrfac=(g3pmi)*rslopemu(i,k,4)*rslope3(i,k,4)*g1pdrmr*rsloped(i,k,1)*rslopemu(i,k,1)*rslope(i,k,1)&
              +(2.)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)*g2pdrmr*rsloped(i,k,1)*rslopemu(i,k,1)*rslope2(i,k,1)&
              +(g1pmi)*rslopemu(i,k,4)*rslope(i,k,4)*g3pdrmr*rsloped(i,k,1)*rslopemu(i,k,1)*rslope3(i,k,1)

                piacr(i,k)=(pi)*cmr*n0i(i,k)*n0r(i,k)*abs(vt2i-vt2r)/(4*dry_carrier_density(i,k))*acrfac*eacir

              
              piacr(i,k) = piacr(i,k)*min(max(0.0,qci(i,k,2)/qrs(i,k,1)),1.)**2
              piacr(i,k) = min(piacr(i,k),(qrs(i,k,1))/dtcld)
        endif




            if(qrs(i,k,2).gt.qcrmin .and. qci(i,k,2).gt.qmin) then
               acrfac=(g3pms)*rslopemu(i,k,2)*rslope3(i,k,2)*g1pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope(i,k,4)&
                     +(2.)*g2pms*rslopemu(i,k,2)*rslope2(i,k,2)*g2pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope2(i,k,4)&
                     +(g1pms)*rslopemu(i,k,2)*rslope(i,k,2)*g3pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope3(i,k,4)

                psaci(i,k)=(pi)*cmi*n0i(i,k)*n0so(i,k)*n0sfac(i,k)*abs(vt2s-vt2i)/(4*dry_carrier_density(i,k))*acrfac*eacsi
                psaci(i,k)=psaci(i,k)*min(max(0.0,qrs(i,k,2)/qci(i,k,2)),1.)**2
                psaci(i,k) = min(psaci(i,k),qci(i,k,2)/dtcld)
            endif




            if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt.qcrmin .and. qci(i,k,2).gt.qmin) then
              eacgi = exp(0.07*(-supcol))
                acrfac=(g3pmg)*rslopemu(i,k,3)*rslope3(i,k,3)*g1pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope(i,k,4)&
                     +(2.)*g2pmg*rslopemu(i,k,3)*rslope2(i,k,3)*g2pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope2(i,k,4)&
                     +(g1pmg)*rslopemu(i,k,3)*rslope(i,k,3)*g3pdimi*rsloped(i,k,4)*rslopemu(i,k,4)*rslope3(i,k,4)

                pgaci(i,k)=(pi)*cmi*n0i(i,k)*n0go(i,k)*abs(vt2g(i,k)-vt2i)/(4*dry_carrier_density(i,k))*acrfac*eacgi
                pgaci(i,k)=pgaci(i,k)*min(max(0.0,qrs(i,k,3)/qci(i,k,2)),1.)**2
                pgaci(i,k) = min(pgaci(i,k),qci(i,k,2)/dtcld)
            endif
         endif





          if(supcol.gt.0. .and. nci(i,k,2).gt.ncmin) then
          if(nrs(i,k,1).gt.nrmin) then
               acrfac=(g3pmr)*rslopemu(i,k,1)*rslope3(i,k,1)*g1pmi*rslopemu(i,k,4)*rslope(i,k,4)&
                     +(2.)*g2pmr*rslopemu(i,k,1)*rslope2(i,k,1)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)&
                     +(g1pmr)*rslopemu(i,k,1)*rslope(i,k,1)*g3pmi*rslopemu(i,k,4)*rslope3(i,k,4)

                nraci(i,k) =(pi)*n0i(i,k)*n0r(i,k)*eacri*abs(vt2r-vt2i)*acrfac/4.
                nraci(i,k)=nraci(i,k)*min(max(0.0,(qrs(i,k,1))/qci(i,k,2)),1.)**2
                nraci(i,k) = min(nraci(i,k),nci(i,k,2)/dtcld)




               acrfac=(g3pmi)*rslopemu(i,k,4)*rslope3(i,k,4)*g1pmr*rslopemu(i,k,1)*rslope(i,k,1)&
                     +(2.)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)*g2pmr*rslopemu(i,k,1)*rslope2(i,k,1)&
                     +(g1pmi)*rslopemu(i,k,4)*rslope(i,k,4)*g3pmr*rslopemu(i,k,1)*rslope3(i,k,1)

              niacr(i,k)=(pi)*n0i(i,k)*n0r(i,k)*eacir*abs(vt2i-vt2r)*acrfac/4.
              niacr(i,k) = niacr(i,k)*min(max(0.0,qci(i,k,2)/qrs(i,k,1)),1.)**2
              niacr(i,k) = min(niacr(i,k),nrs(i,k,1)/dtcld)
            endif





              if(qrs(i,k,2).gt.qcrmin) then
               acrfac=(g3pms)*rslopemu(i,k,2)*rslope3(i,k,2)*g1pmi*rslopemu(i,k,4)*rslope(i,k,4)&
                     +(2.)*g2pms*rslopemu(i,k,2)*rslope2(i,k,2)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)&
                     +(g1pms)*rslopemu(i,k,2)*rslope(i,k,2)*g3pmi*rslopemu(i,k,4)*rslope3(i,k,4)

                nsaci(i,k)=(pi)*n0i(i,k)*n0s*n0sfac(i,k)*eacsi*abs(vt2s-vt2i)*acrfac/4.
                nsaci(i,k)=nsaci(i,k)*min(max(0.0,(qrs(i,k,2))/qci(i,k,2)),1.)**2
                nsaci(i,k) = min(nsaci(i,k),nci(i,k,2)/dtcld)
              endif




             if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt.qcrmin) then
               eacgi = exp(0.07*(-supcol))
               acrfac=(g3pmg)*rslopemu(i,k,3)*rslope3(i,k,3)*g1pmi*rslopemu(i,k,4)*rslope(i,k,4)&
                     +(2.)*g2pmg*rslopemu(i,k,3)*rslope2(i,k,3)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)&
                     +(g1pmg)*rslopemu(i,k,3)*rslope(i,k,3)*g3pmi*rslopemu(i,k,4)*rslope3(i,k,4)

               ngaci(i,k)=(pi)*n0i(i,k)*n0g*eacgi*abs(vt2g(i,k)-vt2i)*acrfac/4.
               ngaci(i,k)=ngaci(i,k)*min(max(0.0,(qrs(i,k,3))/qci(i,k,2)),1.)**2
               ngaci(i,k) = min(ngaci(i,k),nci(i,k,2)/dtcld)
           endif
         endif




          if(qrs(i,k,2).gt.qcrmin .and. qci(i,k,1).gt.qmin) then

             psacw(i,k) = min((rslope3(i,k,2))*rslopeb(i,k,2)*rslopemu(i,k,2)    &
                         *pi*n0so(i,k)*n0sfac(i,k)*avts*g3pbs*.25*eacsc              &
              
                        *min(max(0.0,qrs(i,k,2)/qci(i,k,1)),1.)**2             &
                        *qci(i,k,1)*denfac(i,k),qci(i,k,1)/dtcld)
          endif




         if(qrs(i,k,2).gt.qcrmin .and. nci(i,k,1).gt.ncmin) then

           nsacw(i,k) = min((pi)*avts*.25*eacsc*n0so(i,k)*n0sfac(i,k)*n0c(i,k)/(muc+1)  &
                       *g3pbs*rslope3(i,k,2)*rslopeb(i,k,2)*rslopemu(i,k,2)     &
                       *rslopec(i,k)*rslopecmu(i,k)     &
              
                       *min(max(0.0,qrs(i,k,2)/qci(i,k,1)),1.)**2              &
                       *denfac(i,k),nci(i,k,1)/dtcld)
         endif




          if(progb_status(i,k)==PROGB_PSD_ACTIVE .and. qrs(i,k,3).gt.qcrmin .and. qci(i,k,1).gt.qmin) then

             pgacw(i,k) = min((rslope3(i,k,3))*rslopeb(i,k,3)*rslopemu(i,k,3)    &
                         *qci(i,k,1)*pi*n0go(i,k)*avtg(i,k)*g3pbg(i,k)*.25*eacgc&
              
                        *min(max(0.0,qrs(i,k,3)/qci(i,k,1)),1.)**2             &
                        *denfac(i,k),qci(i,k,1)/dtcld)
          endif




          if(progb_status(i,k)==PROGB_PSD_ACTIVE .and. qrs(i,k,3).gt.qcrmin .and. nci(i,k,1).gt.ncmin) then
           ngacw(i,k) = min((pi)*avtg(i,k)*.25*eacgc*n0go(i,k)*n0c(i,k)/(muc+1)&
                       *g3pbg(i,k)*rslope3(i,k,3)*rslopeb(i,k,3)*rslopemu(i,k,3)&
                       *rslopec(i,k)*rslopecmu(i,k)     &
              
                        *min(max(0.0,qrs(i,k,3)/qci(i,k,1)),1.)**2             &
                        *denfac(i,k),nci(i,k,1)/dtcld)
          endif




          if(qsum(i,k) .gt. 1.e-15 ) then
            paacw(i,k) = (qrs(i,k,2)*psacw(i,k)+qrs(i,k,3)*pgacw(i,k))/(qsum(i,k))




            naacw(i,k) = (qrs(i,k,2)*nsacw(i,k)+qrs(i,k,3)*ngacw(i,k))/(qsum(i,k))
          endif      




         if(supcol.gt.0. .and. qci(i,k,2).gt.qcrmin) then

           if(qci(i,k,1).gt.qmin .and. avedia(i,k,3).GE.di50) then
             piacw(i,k) = min(rslope3(i,k,4)*rslopeb(i,k,4)*rslopemu(i,k,4)    &
                         *pi*n0i(i,k)*avti*g3pbi*.25*eacic              &
              
                        *min(max(0.0,qci(i,k,2)/qci(i,k,1)),1.)**2             &
                        *qci(i,k,1)*denfac(i,k),qci(i,k,1)/dtcld)
           endif




          if(nci(i,k,1).gt.ncmin .and. avedia(i,k,3).GE. di50) then
             niacw(i,k) = min(pi*avti*.25*eacic*n0i(i,k)*n0c(i,k)/(muc+1)&
                       *g3pbi*rslope3(i,k,4)*rslopeb(i,k,4)*rslopemu(i,k,4)&
                       *rslopec(i,k)*rslopecmu(i,k)     &
              
                       *min(max(0.0,qci(i,k,2)/qci(i,k,1)),1.)**2              &
                       *denfac(i,k),nci(i,k,1)/dtcld)
          endif
        endif




          if(qrs(i,k,2).gt.qcrmin .and. qrs(i,k,1).gt.qcrmin) then
            if(supcol.gt.0) then



            acrfac = (g3pmr)*g1pdsms*rslope3(i,k,1)*rslopemu(i,k,1)        &
                     *rsloped(i,k,2)*rslopemu(i,k,2)*rslope(i,k,2)             &
                     +(2.)*g2pmr*g2pdsms*rslope2(i,k,1)*rslopemu(i,k,1)&
                     *rsloped(i,k,2)*rslopemu(i,k,2)*rslope2(i,k,2)            &
                     +(g1pmr)*g3pdsms*rslope(i,k,1)*rslopemu(i,k,1)&
                     *rsloped(i,k,2)*rslopemu(i,k,2)*rslope3(i,k,2)


              pracs(i,k) =(pi)*cms*n0so(i,k)*n0sfac(i,k)*n0r(i,k)*abs(vt2r-vt2s)&
                        /(4*dry_carrier_density(i,k))*acrfac*eacrs
              
              pracs(i,k) =pracs(i,k)*min(max(0.0,(qrs(i,k,1))/qrs(i,k,2)),1.)**2
              pracs(i,k) = min(pracs(i,k),(qrs(i,k,2))/dtcld)
            endif
























            acrfac = (g3pms)*g1pdrmr*rslope3(i,k,2)*rslopemu(i,k,2) &
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope(i,k,1)             &
                     +(2.)*g2pms*g2pdrmr*rslope2(i,k,2)*rslopemu(i,k,2)&
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope2(i,k,1)            &
                     +(g1pms)*g3pdrmr*rslope(i,k,2)*rslopemu(i,k,2)      &
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope3(i,k,1)
            psacr(i,k) = (pi)*cmr*n0r(i,k)*n0so(i,k)*n0sfac(i,k)*abs(vt2s-vt2r)&
                        /(4*dry_carrier_density(i,k))*acrfac*eacsr
              
            psacr(i,k) = psacr(i,k)*min(max(0.0,(qrs(i,k,2))/qrs(i,k,1)),1.)**2
            psacr(i,k) = min(psacr(i,k),(qrs(i,k,1))/dtcld)
          endif
          if(qrs(i,k,2).gt.qcrmin .and. nrs(i,k,1).gt.nrmin) then







            acrfac = (g3pms)*g1pmr*rslope3(i,k,2)*rslopemu(i,k,2)&
                     *rslope(i,k,1)*rslopemu(i,k,1)                            &
                    +(2.)*g2pms*g2pmr*rslope2(i,k,2)*rslopemu(i,k,2)&
                     *rslope2(i,k,1)*rslopemu(i,k,1)                           &
                    +(g1pms)*g3pmr*rslope(i,k,2)*rslopemu(i,k,2)&
                     *rslope3(i,k,1)*rslopemu(i,k,1)
            nsacr(i,k) =(pi)/4.*n0r(i,k)*n0so(i,k)*n0sfac(i,k)*abs(vt2s-vt2r)        &
                        *acrfac*eacsr
              
            nsacr(i,k) = nsacr(i,k)*min(max(0.0,qrs(i,k,2)/qrs(i,k,1)),1.)**2
            nsacr(i,k) = min(nsacr(i,k),nrs(i,k,1)/dtcld)
          endif




          if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt.qcrmin .and. qrs(i,k,1).gt.qcrmin) then



            acrfac = (g3pmg)*g1pdrmr*rslope3(i,k,3)*rslopemu(i,k,3)     &
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope(i,k,1)             &
                     +(2.)*g2pmg*g2pdrmr*rslope2(i,k,3)*rslopemu(i,k,3)&
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope2(i,k,1)            &
                     +(g1pmg)*g3pdrmr*rslope(i,k,3)*rslopemu(i,k,3)&
                     *rsloped(i,k,1)*rslopemu(i,k,1)*rslope3(i,k,1)
            pgacr(i,k) = (pi)*cmr*n0r(i,k)*n0go(i,k)*abs(vt2g(i,k)-vt2r)     &
                        /(4*dry_carrier_density(i,k))*acrfac*eacgr


              
            pgacr(i,k) =pgacr(i,k)*min(max(0.0,(qrs(i,k,3))/qrs(i,k,1)),1.)**2
            pgacr(i,k) = min(pgacr(i,k),(qrs(i,k,1))/dtcld)
          endif




          if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt.qcrmin .and. nrs(i,k,1).gt.nrmin) then

            acrfac = (g3pmg)*g1pmr*rslope3(i,k,3)*rslopemu(i,k,3)&
                     *rslope(i,k,1)*rslopemu(i,k,1)                            &
                    +(2.)*g2pmg*g2pmr*rslope2(i,k,3)*rslopemu(i,k,3)&
                     *rslope2(i,k,1)*rslopemu(i,k,1)                           &
                    +(g1pmg)*g3pmr*rslope(i,k,3)*rslopemu(i,k,3)&
                     *rslope3(i,k,1)*rslopemu(i,k,1)
            ngacr(i,k)=(pi)/4.*n0r(i,k)*n0go(i,k)*abs(vt2g(i,k)-vt2r)*acrfac*eacgr
              
            ngacr(i,k) = ngacr(i,k)*min(max(0.0,qrs(i,k,3)/qrs(i,k,1)),1.)**2
            ngacr(i,k) = min(ngacr(i,k),nrs(i,k,1)/dtcld)
          endif






         Mispl = 4./3.*pi*deni*(Rispl)**3 

         IF (qrs(i,k,2).GE.0.1E-3) THEN
         IF (qci(i,k,1).GE.0.5E-3.OR.qrs(i,k,1).GE.0.1E-3) THEN
         IF (paacw(i,k).GT.0..OR.psacr(i,k).GT.0.) THEN
            IF (t(i,k).LT.270.16 .AND. t(i,k).GT.265.16) THEN

               IF (t(i,k).GT.270.16) THEN
                  fmul = 0.
               ELSE IF (t(i,k).LE.270.16.AND.t(i,k).GT.268.16)  THEN
                  fmul = (270.16-t(i,k))/2.
               ELSE IF (t(i,k).GE.265.16.AND.t(i,k).LE.268.16)   THEN
                  fmul = (t(i,k)-265.16)/3.
               ELSE IF (t(i,k).LT.265.16) THEN
                  fmul= 0.
               END IF





               IF (paacw(i,k).GT.0.) THEN
                  nmulcs(i,k) = 35.E4*paacw(i,k)*fmul*1000. 
                  pmulcs(i,k) = nmulcs(i,k)*Mispl



                  pmulcs(i,k) = MIN(pmulcs(i,k),paacw(i,k))
                  paacw(i,k) = paacw(i,k)-pmulcs(i,k)
                  nmulcs(i,k) = nmulcs(i,k)*dry_carrier_density(i,k)

               END IF



               IF (psacr(i,k).GT.0.) THEN
                   nmulrs(i,k) = 35.E4*psacr(i,k)*fmul*1000.
                   pmulrs(i,k) = nmulrs(i,k)*Mispl




                   pmulrs(i,k) = MIN(pmulrs(i,k),psacr(i,k))
                   psacr(i,k) = psacr(i,k)-pmulrs(i,k)
                   nmulrs(i,k) = nmulrs(i,k)*dry_carrier_density(i,k)

               END IF

            END IF
         END IF
         END IF
         END IF

         IF (qrs(i,k,3).GE.0.1E-3) THEN
         IF (qci(i,k,1).GE.0.5E-3.OR.qrs(i,k,1).GE.0.1E-3) THEN
         IF (paacw(i,k).GT.0..OR.pgacr(i,k).GT.0.) THEN
            IF (t(i,k).LT.270.16 .AND. t(i,k).GT.265.16) THEN

               IF (t(i,k).GT.270.16) THEN
                  fmul = 0.
               ELSE IF (t(i,k).LE.270.16.AND.t(i,k).GT.268.16)  THEN
                  fmul = (270.16-t(i,k))/2.
               ELSE IF (t(i,k).GE.265.16.AND.t(i,k).LE.268.16)   THEN
                  fmul = (t(i,k)-265.16)/3.
               ELSE IF (t(i,k).LT.265.16) THEN
                  fmul = 0.
               END IF





               IF (paacw(i,k).GT.0.) THEN
                  nmulcg(i,k) = 35.E4*paacw(i,k)*fmul*1000.
                  pmulcg(i,k) = nmulcg(i,k)*Mispl




                  pmulcg(i,k) = MIN(pmulcg(i,k),paacw(i,k))
                  paacw(i,k) = paacw(i,k)-pmulcg(i,k)
                  nmulcg(i,k) = nmulcg(i,k)*dry_carrier_density(i,k)

               END IF




               IF (pgacr(i,k).GT.0.) THEN
                   nmulrg(i,k) = 35.E4*pgacr(i,k)*fmul*1000.
                   pmulrg(i,k) = nmulrg(i,k)*Mispl




                   pmulrg(i,k) = MIN(pmulrg(i,k),pgacr(i,k))
                   pgacr(i,k) = pgacr(i,k)-pmulrg(i,k)
                   nmulrg(i,k) = nmulrg(i,k)*dry_carrier_density(i,k)

               END IF              
              END IF
           END IF
           END IF
           END IF





          if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt.qcrmin .and. qrs(i,k,2).gt.qcrmin) then
            pgacs(i,k) = 0. 
          endif
          if(supcol.le.0) then
            xlf = xlf0




            if(qrs(i,k,2).gt.0.)                                               & 
              pseml(i,k) = min(max((cliq)*supcol*(paacw(i,k)+psacr(i,k)) &
                          /xlf,-(qrs(i,k,2))/dtcld),0.)




              if  (qrs(i,k,2).gt.qcrmin) then
                sfac = (rslope(i,k,2))*n0so(i,k)*n0sfac(i,k)/qrs(i,k,2)
                nseml(i,k) = -sfac*pseml(i,k)
              endif




            if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt.0.)                                               &
              pgeml(i,k) = min(max((cliq)*supcol*(paacw(i,k)+pgacr(i,k))/xlf &
                          ,-(qrs(i,k,3))/dtcld),0.)




              if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt.qcrmin) then
                gfac = (rslope(i,k,3))*n0go(i,k)/qrs(i,k,3)
                ngeml(i,k) = -gfac*pgeml(i,k)
              endif
          endif






          if( (supcol.gt.8 .and. supsat .gt. 0.) .or. &
              (rh(i,k,2) .gt. 1.08) )then
              supice = satdt-prevp(i,k)
              Minud = 4./3.*pi*deni*(Rinud)**3 

              Nid =0.005*exp(0.304*(supcol))*1000. 




              Nid = max(min(Nid,500.e3),0.) 
              if (Nid.GT.nci(i,k,2)) then
                ninud(i,k) = ((Nid)-(nci(i,k,2)))/dtcld
                pinud(i,k) = ninud(i,k)/dry_carrier_density(i,k)*Minud
                pinud(i,k) = min(min(pinud(i,k),(satdt)/2),supice)
                ninud(i,k) = pinud(i,k)*dry_carrier_density(i,k)/Minud
              endif
             if(abs(prevp(i,k)+pinud(i,k)).ge.abs(satdt)) ifsat = 1     
           endif

          if(supcol.gt.0) then




            if(qci(i,k,2).gt.0. .and. ifsat.ne.1) then
              pidep(i,k)=(4.)*n0i(i,k)*g2pmi*rslopemu(i,k,4)*rslope2(i,k,4)*(rh(i,k,2)-1.) &
                        /work1(i,k,2)
              supice = satdt-prevp(i,k)-pinud(i,k)

              if(pidep(i,k).lt.0.) then



                pr87_ice_raw_pidep_before_caps=pidep(i,k)
                pidep(i,k) = max(pidep(i,k),-(qci(i,k,2))/dtcld)
                pidep(i,k) = max(max(pidep(i,k),(satdt)/2),supice)
                if (pidep(i,k).eq.-(qci(i,k,2))/dtcld) then
                  ice_full_sublimation_pending(i,k) = .true.
                  ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),1)
                  ice_sublimation_raw_pidep(i,k) = pr87_ice_raw_pidep_before_caps
                  ice_sublimation_q_before(i,k) = qci(i,k,2)
                  ice_sublimation_n_before(i,k) = nci(i,k,2)
                  ice_sublimation_event_count(i,k) = &
                       ice_sublimation_event_count(i,k) + 1
                  ice_sublimation_capped_pidep(i,k) = pidep(i,k)
                endif
              else
                pidep(i,k) = min(min(pidep(i,k),(satdt)/2),supice)
              endif
              if(abs(prevp(i,k)+pinud(i,k)+pidep(i,k)).ge.abs(satdt)) ifsat = 1
            endif




            if(qrs(i,k,2).gt.0. .and. ifsat.ne.1) then

              coeres = (rslope2(i,k,2))*sqrt(rslope(i,k,2)*rslopeb(i,k,2)) &
                      *rslopemu(i,k,2)
              psdep(i,k) =(rh(i,k,2)-1.)*n0sfac(i,k)*((precs1)*n0so(i,k)*rslope2(i,k,2)   &
                        *rslopemu(i,k,2) +(precs2)*n0so(i,k)*work2(i,k)*coeres)/work1(i,k,2)
              supice = satdt-prevp(i,k)-pinud(i,k)-pidep(i,k)
              if(psdep(i,k).lt.0.) then
                psdep(i,k) = max(psdep(i,k),-(qrs(i,k,2))/dtcld)
                psdep(i,k) = max(max(psdep(i,k),(satdt)/2),supice)
              else
                psdep(i,k) = min(min(psdep(i,k),(satdt)/2),supice)
              endif
              if(abs(prevp(i,k)+pinud(i,k)+pidep(i,k)+psdep(i,k)).ge.abs(satdt)) ifsat = 1
            endif




            if(progb_status(i,k)==PROGB_PSD_ACTIVE .and. qrs(i,k,3).gt.0. .and. ifsat.ne.1) then

              coeres = (rslope2(i,k,3))*sqrt(rslope(i,k,3)*rslopeb(i,k,3)) &
                      *rslopemu(i,k,3)
              pgdep(i,k) =(rh(i,k,2)-1.)*((precg1)*n0go(i,k)*rslope2(i,k,3)*rslopemu(i,k,3)&
                          +(precg2(i,k))*n0go(i,k)*work2(i,k)*coeres)/work1(i,k,2)
              supice = satdt-prevp(i,k)-pinud(i,k)-pidep(i,k)-psdep(i,k)
              if(pgdep(i,k).lt.0.) then
                pgdep(i,k) = max(pgdep(i,k),-(qrs(i,k,3))/dtcld)
                pgdep(i,k) = max(max(pgdep(i,k),(satdt)/2),supice)
              else
                pgdep(i,k) = min(min(pgdep(i,k),(satdt)/2),supice)
              endif
              if(abs(prevp(i,k)+pinud(i,k)+pidep(i,k)+psdep(i,k)+pgdep(i,k)).ge.          &
                abs(satdt)) ifsat = 1
            endif




            if(qci(i,k,2).gt.0. .and. nci(i,k,2).gt.0) then

              IF (t(i,k).GT.255.66) THEN
                qi0 = 0.4632*10**(-6.0-0.0413*(-supcol))*gas_density(i,k)
              ELSE 
                qi0 = 0.2316*10**(-4.0+0.0519*(-supcol))*gas_density(i,k)
              END IF
              alpha1= 0.005*exp(0.025*(-supcol)) 
              Miaut= pi*deni*(di125)**3/6.  
              psaut(i,k) = min(max(0.,alpha1*(qci(i,k,2)-qi0)),qci(i,k,2)/dtcld)
              nsaut(i,k) = min((psaut(i,k))*dry_carrier_density(i,k)/Miaut,nci(i,k,2)/dtcld)  
            endif









          endif





          if(supcol.lt.0.) then
            if(qrs(i,k,2).gt.0. .and. rh(i,k,1).lt.1.) then
              coeres = (rslope2(i,k,2))*sqrt(rslope(i,k,2)*rslopeb(i,k,2))  &
                      *rslopemu(i,k,2)
              psevp(i,k) =(rh(i,k,1)-1.)*n0sfac(i,k)*((precs1)*n0so(i,k)*rslope2(i,k,2)   &
                        *rslopemu(i,k,2)+(precs2)*n0so(i,k)*work2(i,k)*coeres)/work1(i,k,1)
              psevp(i,k) = min(max(psevp(i,k),-(qrs(i,k,2))/dtcld),0.)
            endif




            if(progb_status(i,k)==PROGB_PSD_ACTIVE .and. qrs(i,k,3).gt.0. .and. rh(i,k,1).lt.1.) then
              coeres = (rslope2(i,k,3))*sqrt(rslope(i,k,3)*rslopeb(i,k,3))  &
                      *rslopemu(i,k,3)
              pgevp(i,k) =(rh(i,k,1)-1.)*((precg1)*n0go(i,k)*rslope2(i,k,3)        &
                      *rslopemu(i,k,3)+(precg2(i,k))*n0go(i,k)*work2(i,k)*coeres)/work1(i,k,1)
              pgevp(i,k) = min(max(pgevp(i,k),-(qrs(i,k,3))/dtcld),0.)
            endif
          endif
        enddo
      enddo




      do k = kts, kte
        do i = its, ite

          rain_pair_rate_start(i,k,1)=praut(i,k)
          rain_pair_rate_start(i,k,2)=nraut(i,k)
          rain_pair_rate_start(i,k,3)=praci(i,k)
          rain_pair_rate_start(i,k,4)=nraci(i,k)
          rain_pair_rate_start(i,k,5)=piacr(i,k)
          rain_pair_rate_start(i,k,6)=niacr(i,k)
          rain_pair_rate_start(i,k,7)=psacr(i,k)
          rain_pair_rate_start(i,k,8)=nsacr(i,k)
          rain_pair_rate_start(i,k,9)=pgacr(i,k)
          rain_pair_rate_start(i,k,10)=ngacr(i,k)

          delta2=0.
          delta3=0.
          if(qrs(i,k,1).lt.1.e-4 .and. qrs(i,k,2).lt.1.e-4) delta2=1.
          if(qrs(i,k,1).lt.1.e-4) delta3=1.
          if(t(i,k).le.t0c) then



            value = max(qmin,qci(i,k,1))
            source = (praut(i,k)+pracw(i,k)+paacw(i,k)+paacw(i,k)+piacw(i,k)        &
                    +pmulcs(i,k)+pmulcg(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              praut(i,k) = praut(i,k)*factor
              pracw(i,k) = pracw(i,k)*factor
              paacw(i,k) = paacw(i,k)*factor
              piacw(i,k) = piacw(i,k)*factor
              pmulcs(i,k) = pmulcs(i,k)*factor
              pmulcg(i,k) = pmulcg(i,k)*factor
            endif



            value = max(qmin,qci(i,k,2))
            source = (psaut(i,k)-pinud(i,k)-pidep(i,k)+praci(i,k)+psaci(i,k)   &
             +pgaci(i,k)-pmulcs(i,k)-pmulrs(i,k)-pmulcg(i,k)-pmulrg(i,k)-piacw(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              psaut(i,k) = psaut(i,k)*factor
              pinud(i,k) = pinud(i,k)*factor
              pidep(i,k) = pidep(i,k)*factor
              praci(i,k) = praci(i,k)*factor
              psaci(i,k) = psaci(i,k)*factor
              pgaci(i,k) = pgaci(i,k)*factor
              piacw(i,k) = piacw(i,k)*factor
              pmulcs(i,k) = pmulcs(i,k)*factor
              pmulrs(i,k) = pmulrs(i,k)*factor
              pmulcg(i,k) = pmulcg(i,k)*factor
              pmulrg(i,k) = pmulrg(i,k)*factor
            endif



            value = max(qmin,qrs(i,k,1))
            source = (-praut(i,k)-prevp(i,k)-pracw(i,k)+piacr(i,k)             &
                    +psacr(i,k)+pgacr(i,k)+pmulrs(i,k)+pmulrg(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              praut(i,k) = praut(i,k)*factor
              prevp(i,k) = prevp(i,k)*factor
              pracw(i,k) = pracw(i,k)*factor
              piacr(i,k) = piacr(i,k)*factor
              psacr(i,k) = psacr(i,k)*factor
              pgacr(i,k) = pgacr(i,k)*factor
              pmulrs(i,k) = pmulrs(i,k)*factor
              pmulrg(i,k) = pmulrg(i,k)*factor
            endif



            value = max(qmin,qrs(i,k,2))
            source = -(psdep(i,k)+psaut(i,k)-pgaut(i,k)+paacw(i,k)             &
                     +piacr(i,k)*delta3+praci(i,k)*delta3                      &
                     -pracs(i,k)*(1.-delta2)+psacr(i,k)*delta2                 &
                     +psaci(i,k)-pgacs(i,k) )*dtcld
            if (source.gt.value) then
              factor = value/source
              psdep(i,k) = psdep(i,k)*factor
              psaut(i,k) = psaut(i,k)*factor
              pgaut(i,k) = pgaut(i,k)*factor
              paacw(i,k) = paacw(i,k)*factor
              piacr(i,k) = piacr(i,k)*factor
              praci(i,k) = praci(i,k)*factor
              psaci(i,k) = psaci(i,k)*factor
              pracs(i,k) = pracs(i,k)*factor
              psacr(i,k) = psacr(i,k)*factor
              pgacs(i,k) = pgacs(i,k)*factor
            endif



            value = max(qmin,qrs(i,k,3))
            source = -(pgdep(i,k)+pgaut(i,k)                                   &
                     +piacr(i,k)*(1.-delta3)+praci(i,k)*(1.-delta3)            &
                     +psacr(i,k)*(1.-delta2)+pracs(i,k)*(1.-delta2)            &
                     +pgaci(i,k)+paacw(i,k)+pgacr(i,k)+pgacs(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              pgdep(i,k) = pgdep(i,k)*factor
              pgaut(i,k) = pgaut(i,k)*factor
              piacr(i,k) = piacr(i,k)*factor
              praci(i,k) = praci(i,k)*factor
              psacr(i,k) = psacr(i,k)*factor
              pracs(i,k) = pracs(i,k)*factor
              paacw(i,k) = paacw(i,k)*factor
              pgaci(i,k) = pgaci(i,k)*factor
              pgacr(i,k) = pgacr(i,k)*factor
              pgacs(i,k) = pgacs(i,k)*factor
            endif



            value = max(ncmin,nci(i,k,1))
            source = (nraut(i,k)+nccol(i,k)+nracw(i,k)                         &
                    +niacw(i,k)+naacw(i,k)+naacw(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              nraut(i,k) = nraut(i,k)*factor
              nccol(i,k) = nccol(i,k)*factor
              nracw(i,k) = nracw(i,k)*factor
              naacw(i,k) = naacw(i,k)*factor
              niacw(i,k) = niacw(i,k)*factor
            endif



            value = max(ncmin,nci(i,k,2))
            source = (nraci(i,k)+nsaci(i,k)+ngaci(i,k)+niacr(i,k)+nsaut(i,k)        &
              -nmulcs(i,k)-nmulcg(i,k)-nmulrs(i,k)-nmulrg(i,k)-ninud(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              nraci(i,k) = nraci(i,k)*factor
              nsaci(i,k) = nsaci(i,k)*factor
              ngaci(i,k) = ngaci(i,k)*factor
              niacr(i,k) = niacr(i,k)*factor
              nsaut(i,k) = nsaut(i,k)*factor
              ninud(i,k) = ninud(i,k)*factor
              nmulcs(i,k) = nmulcs(i,k)*factor
              nmulcg(i,k) = nmulcg(i,k)*factor
              nmulrs(i,k) = nmulrs(i,k)*factor
              nmulrg(i,k) = nmulrg(i,k)*factor
            endif



            factor=kdm6_shared_pair_fraction(rain_pair_rate_start(i,k,1),praut(i,k), &
                 rain_pair_rate_start(i,k,2),nraut(i,k))
            praut(i,k)=rain_pair_rate_start(i,k,1)*factor
            nraut(i,k)=rain_pair_rate_start(i,k,2)*factor
            factor=kdm6_shared_pair_fraction(rain_pair_rate_start(i,k,3),praci(i,k), &
                 rain_pair_rate_start(i,k,4),nraci(i,k))
            praci(i,k)=rain_pair_rate_start(i,k,3)*factor
            nraci(i,k)=rain_pair_rate_start(i,k,4)*factor
            factor=kdm6_shared_pair_fraction(rain_pair_rate_start(i,k,5),piacr(i,k), &
                 rain_pair_rate_start(i,k,6),niacr(i,k))
            piacr(i,k)=rain_pair_rate_start(i,k,5)*factor
            niacr(i,k)=rain_pair_rate_start(i,k,6)*factor
            factor=kdm6_shared_pair_fraction(rain_pair_rate_start(i,k,7),psacr(i,k), &
                 rain_pair_rate_start(i,k,8),nsacr(i,k))
            psacr(i,k)=rain_pair_rate_start(i,k,7)*factor
            nsacr(i,k)=rain_pair_rate_start(i,k,8)*factor
            factor=kdm6_shared_pair_fraction(rain_pair_rate_start(i,k,9),pgacr(i,k), &
                 rain_pair_rate_start(i,k,10),ngacr(i,k))
            pgacr(i,k)=rain_pair_rate_start(i,k,9)*factor
            ngacr(i,k)=rain_pair_rate_start(i,k,10)*factor

            rain_q_before=[qci(i,k,1),qci(i,k,2),qrs(i,k,1),qrs(i,k,2),qrs(i,k,3)]
            rain_n_before=[nci(i,k,1),nci(i,k,2),nrs(i,k,1)]
            rain_bg_before=brs(i,k)
            rain_t_before=t(i,k)
            rain_qv_before=q(i,k)
            rain_ccn3_before=nci(i,k,3)
            rain_n_ccn_transfer=0.0
            rain_ng_q_process(1)=-(pracw(i,k)+piacw(i,k)+pmulcs(i,k)+pmulcg(i,k))*dtcld
            rain_ng_q_process(2)=(-psaut(i,k)-psaci(i,k)+pinud(i,k)+pidep(i,k) &
                 +piacw(i,k)+pmulcs(i,k)+pmulcg(i,k)+pmulrs(i,k)+pmulrg(i,k))*dtcld
            rain_ng_q_process(3)=(pracw(i,k)+prevp(i,k)-pmulrs(i,k)-pmulrg(i,k))*dtcld
            rain_ng_q_process(4)=(psdep(i,k)+psaut(i,k)+psaci(i,k))*dtcld
            rain_ng_q_process(5)=0.0
            if (ieee_is_finite(rain_q_before(2))) then
              if (rain_q_before(2).gt.0.0) then
                if (ieee_is_finite(rain_ng_q_process(2))) then
                  if (rain_ng_q_process(2).lt.0.0) then
                    if (rain_ng_q_process(2).le.-rain_q_before(2)) then
                      ice_full_sublimation_pending(i,k)=.true.
                      ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),2)
                    endif
                  endif
                endif
              endif
            endif
            rain_ng_n_process(1)=(-nccol(i,k)-nracw(i,k)-niacw(i,k))*dtcld
            rain_ng_n_process(2)=(-nsaci(i,k)+ninud(i,k)+nmulcs(i,k)+nmulcg(i,k) &
                 +nmulrs(i,k)+nmulrg(i,k)-nsaut(i,k))*dtcld
            rain_ng_n_process(3)=-nrcol(i,k)*dtcld
            rain_ng_bg_process=0.0
            rain_ng_qv_process=-(prevp(i,k)+psdep(i,k)+pidep(i,k)+pinud(i,k))*dtcld
            xlf=xls-xl(i,k)
            rain_ng_t_process=(xls*(psdep(i,k)+pidep(i,k)+pinud(i,k)) &
                 +xl(i,k)*prevp(i,k)+xlf*(piacw(i,k)+pmulcs(i,k)+pmulcg(i,k) &
                 +pmulrs(i,k)+pmulrg(i,k)))*dtcld/cpm(i,k)

            rain_q_fixed=rain_q_before
            rain_n_fixed=rain_n_before
            rain_bg_fixed=rain_bg_before
            rain_t_fixed=rain_t_before
            call kdm6_rain_process_fraction(rain_q_fixed,rain_ng_q_process, &
                 rain_n_fixed,rain_ng_n_process,rain_bg_fixed,rain_ng_bg_process, &
                 rain_t_fixed,rain_ng_t_process,rain_full_evap_pending(i,k), &
                 dry_carrier_density(i,k),pidnr,qmin,ncmin,qcrmin,dmr, &
                 lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &
                 lamdacmax,pidni,dmi,lamdaimin,lamdaimax,rain_ng_alpha, &
                 rain_ng_feasible,rain_ng_search_status,rain_qv_before,rain_ng_qv_process, &
                 ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
                 ice_sublimation_pending=ice_full_sublimation_pending(i,k))
            if (.not.rain_ng_feasible) then
              if (rain_ng_search_status.eq.1) then
                call kdm6_rain_process_state_valid(rain_q_fixed,rain_n_fixed, &
                     rain_bg_fixed,rain_t_fixed,dry_carrier_density(i,k),pidnr, &
                     qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0, &
                     pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi,lamdaimin, &
                     lamdaimax,rain_ng_base_valid,rain_full_evap_pending(i,k), &
                     ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
                     ice_sublimation_pending=ice_full_sublimation_pending(i,k))
                if (.not.rain_ng_base_valid .or. rain_qv_before.lt.0.0 .or. &
                    .not.ieee_is_finite(rain_qv_before)) then
                  write(*,*) 'PR87_NG_BASE_FAIL_META',pr87_model_timestep,lat,i,k,loop,n, &
                       rain_ng_search_status,rain_full_evap_pending(i,k),rain_ng_base_valid
                  write(*,*) 'PR87_NG_BASE_FAIL_STATE',rain_q_fixed,rain_n_fixed, &
                       rain_bg_fixed,rain_t_fixed,rain_qv_before,dry_carrier_density(i,k)
                  write(*,'(a,12(1x,z8.8))') 'PR87_NG_BASE_FAIL_STATE_HEX', &
                       transfer([rain_q_fixed,rain_n_fixed,rain_bg_fixed,rain_t_fixed, &
                       rain_qv_before,dry_carrier_density(i,k)],[0],12)
                  write(*,*) 'PR87_NG_BASE_FAIL_QPROC',rain_ng_q_process
                  write(*,*) 'PR87_NG_BASE_FAIL_NPROC',rain_ng_n_process
                  write(*,*) 'PR87_NG_BASE_FAIL_BGTVPROC',rain_ng_bg_process, &
                       rain_ng_t_process,rain_ng_qv_process
                  write(*,*) 'PR87_NG_BASE_FAIL_LIMITS',pidnr,qmin,ncmin,qcrmin,dmr, &
                       lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &
                       lamdacmax,pidni,dmi,lamdaimin,lamdaimax
                  flush(6)
                  error stop 'KDM6 invalid base before nongraupel admission'
                endif
                rain_ng_alpha=0.0
              else
                error stop 'KDM6 nongraupel admission search failed'
              endif
            endif
            rain_q_fixed=rain_q_before+rain_ng_alpha*rain_ng_q_process
            rain_n_fixed=rain_n_before+rain_ng_alpha*rain_ng_n_process
            rain_bg_fixed=rain_bg_before+rain_ng_alpha*rain_ng_bg_process
            rain_t_fixed=rain_t_before+rain_ng_alpha*rain_ng_t_process
            rain_qv_stage=rain_qv_before+rain_ng_alpha*rain_ng_qv_process
            if (.not.ieee_is_finite(rain_qv_stage) .or. rain_qv_stage.lt.0.0) &
              error stop 'KDM6 invalid stored vapor after nongraupel admission'

            rain_bg_rates_feasible=.true.
            if (progb_status(i,k) == PROGB_PSD_ACTIVE) then
              call kdm6_mass_volume_rate(pgdep(i,k),rhox(i,k), &
                   rain_pgdep_bg_rate,rain_bg_rate_valid)
            else if (progb_status(i,k) == PROGB_ABSENT .and. &
                     pgdep(i,k) == 0.0) then
              rain_pgdep_bg_rate = 0.0
              rain_bg_rate_valid = .true.
            else
              rain_pgdep_bg_rate = 0.0
              rain_bg_rate_valid = .false.
            endif
            rain_bg_rates_feasible=rain_bg_rates_feasible.and.rain_bg_rate_valid
            call kdm6_mass_volume_rate(pracs(i,k),dens, &
                 rain_pracs_bg_rate,rain_bg_rate_valid)
            rain_bg_rates_feasible=rain_bg_rates_feasible.and.rain_bg_rate_valid
            call kdm6_mass_volume_rate(pgaci(i,k),deni, &
                 rain_pgaci_bg_rate,rain_bg_rate_valid)
            rain_bg_rates_feasible=rain_bg_rates_feasible.and.rain_bg_rate_valid
            call kdm6_mass_volume_rate(paacw(i,k),denr, &
                 rain_paacw_bg_rate,rain_bg_rate_valid)
            rain_bg_rates_feasible=rain_bg_rates_feasible.and.rain_bg_rate_valid
            call kdm6_mass_volume_rate(piacr(i,k),denr, &
                 rain_piacr_bg_rate,rain_bg_rate_valid)
            rain_bg_rates_feasible=rain_bg_rates_feasible.and.rain_bg_rate_valid
            call kdm6_mass_volume_rate(praci(i,k),deni, &
                 rain_praci_bg_rate,rain_bg_rate_valid)
            rain_bg_rates_feasible=rain_bg_rates_feasible.and.rain_bg_rate_valid
            call kdm6_mass_volume_rate(psacr(i,k),denr, &
                 rain_psacr_bg_rate,rain_bg_rate_valid)
            rain_bg_rates_feasible=rain_bg_rates_feasible.and.rain_bg_rate_valid
            call kdm6_mass_volume_rate(pgacr(i,k),denr, &
                 rain_pgacr_bg_rate,rain_bg_rate_valid)
            rain_bg_rates_feasible=rain_bg_rates_feasible.and.rain_bg_rate_valid
            rain_bg_fixed=rain_bg_before
            rain_g_bg_process=(rain_pgdep_bg_rate+rain_pgaci_bg_rate &
                 +rain_pracs_bg_rate*(1.-delta2)+rain_paacw_bg_rate &
                 +rain_piacr_bg_rate*(1.-delta3)+rain_praci_bg_rate*(1.-delta3) &
                 +rain_psacr_bg_rate*(1.-delta2)+rain_pgacr_bg_rate)*dtcld
            rain_t_fixed=rain_t_before+rain_ng_alpha*rain_ng_t_process
            rain_g_t_process=(xls*pgdep(i,k)+xlf*(2.*paacw(i,k)+piacr(i,k) &
                 +psacr(i,k)+pgacr(i,k)))*dtcld/cpm(i,k)

            if (pgaut(i,k).ne.0.0 .or. pgacs(i,k).ne.0.0) &
              error stop 'KDM6 unsupported graupel mass source without volume partner'

            rain_g_q_process(1)=-2.*paacw(i,k)*dtcld
            rain_g_q_process(2)=-(praci(i,k)+pgaci(i,k))*dtcld
            rain_g_q_process(3)=-(piacr(i,k)+psacr(i,k)+pgacr(i,k))*dtcld
            rain_g_q_process(4)=(paacw(i,k)-pgaut(i,k)-pgacs(i,k) &
                 +piacr(i,k)*delta3+praci(i,k)*delta3+psacr(i,k)*delta2 &
                 -pracs(i,k)*(1.-delta2))*dtcld
            rain_g_q_process(5)=(pgdep(i,k)+pgaut(i,k)+pgaci(i,k)+pgacs(i,k) &
                 +piacr(i,k)*(1.-delta3)+praci(i,k)*(1.-delta3) &
                 +psacr(i,k)*(1.-delta2)+pracs(i,k)*(1.-delta2) &
                 +paacw(i,k)+pgacr(i,k))*dtcld
            rain_g_n_process(1)=-2.*naacw(i,k)*dtcld
            rain_g_n_process(2)=-(nraci(i,k)+niacr(i,k)+ngaci(i,k))*dtcld
            rain_g_n_process(3)=-(nraci(i,k)+niacr(i,k)+nsacr(i,k)+ngacr(i,k))*dtcld
            rain_g_qv_process=-pgdep(i,k)*dtcld

            rain_aut_q_process=0.0
            rain_aut_n_process=0.0
            rain_aut_q_process(1)=-praut(i,k)*dtcld
            rain_aut_q_process(3)= praut(i,k)*dtcld
            rain_aut_n_process(1)=-nraut(i,k)*dtcld
            rain_aut_n_process(3)= nraut(i,k)*dtcld
            pr87_aut_reason=0
            pr87_aut_vapor_reason=0
            if (pr67_trace_this_call) then
              call kdm6_rain_process_state_valid( &
                   rain_q_fixed+rain_aut_q_process,rain_n_fixed+rain_aut_n_process, &
                   rain_bg_fixed,rain_t_fixed,dry_carrier_density(i,k),pidnr, &
                   qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0, &
                   pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi,lamdaimin, &
                   lamdaimax,pr87_aut_endpoint_valid,rain_full_evap_pending(i,k), &
                   ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
                   failure_reason=pr87_aut_reason, &
                   ice_sublimation_pending=ice_full_sublimation_pending(i,k))
              pr87_endpoint_qv=rain_qv_stage
              if (.not.ieee_is_finite(pr87_endpoint_qv) .or. pr87_endpoint_qv.lt.0.0) &
                   pr87_aut_vapor_reason=10
            endif
            call kdm6_rain_process_fraction(rain_q_fixed,rain_aut_q_process, &
                 rain_n_fixed,rain_aut_n_process,rain_bg_fixed,0.0, &
                 rain_t_fixed,0.0,rain_full_evap_pending(i,k), &
                 dry_carrier_density(i,k),pidnr,qmin,ncmin,qcrmin,dmr, &
                 lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &
                 lamdacmax,pidni,dmi,lamdaimin,lamdaimax,rain_aut_alpha, &
                 rain_aut_feasible,rain_aut_search_status,rain_qv_stage,0.0, &
                 ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
                 ice_sublimation_pending=ice_full_sublimation_pending(i,k))
            if (.not.rain_aut_feasible) then
              if (rain_aut_search_status.eq.1) then
                call kdm6_rain_process_state_valid(rain_q_fixed,rain_n_fixed, &
                     rain_bg_fixed,rain_t_fixed,dry_carrier_density(i,k),pidnr, &
                     qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0, &
                     pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi,lamdaimin, &
                     lamdaimax,rain_aut_base_valid,rain_full_evap_pending(i,k), &
                     ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
                     ice_sublimation_pending=ice_full_sublimation_pending(i,k))
                if (.not.rain_aut_base_valid) &
                  error stop 'KDM6 invalid base before rain autoconversion'
                rain_aut_alpha=0.0
              else
                error stop 'KDM6 rain autoconversion admission search failed'
              endif
            endif
            if (pr67_trace_this_call .and. rain_aut_alpha.lt.1.0 .and. &
                (any(rain_aut_q_process.ne.0.0) .or. any(rain_aut_n_process.ne.0.0))) then
              pr87_mass_specific=0.5*sum(abs(rain_aut_q_process))
              write(pr87_reason_unit,'(a,1x,a,8(1x,i0),1p,4(1x,es24.16))',iostat=pr87_reason_ios) &
                   'PR87_ADMISSION','AUT',i,lat,k,loop,rain_aut_search_status, &
                   pr87_aut_reason,pr87_aut_vapor_reason, &
                   merge(1,0,rain_full_evap_pending(i,k)),rain_aut_alpha, &
                   pr87_mass_specific,dry_carrier_density(i,k),delz(i,k)
              if (pr87_reason_ios.ne.0) error stop 'PR87 AUT reason write failed'
            endif
            praut(i,k)=praut(i,k)*rain_aut_alpha
            nraut(i,k)=nraut(i,k)*rain_aut_alpha
            rain_q_fixed=rain_q_fixed+rain_aut_alpha*rain_aut_q_process
            rain_n_fixed=rain_n_fixed+rain_aut_alpha*rain_aut_n_process
            rain_qv_stage=rain_qv_stage+rain_aut_alpha*0.0
            if (ieee_is_finite(rain_q_fixed(2))) then
              if (rain_q_fixed(2).gt.0.0) then
                if (ieee_is_finite(rain_g_q_process(2))) then
                  if (rain_g_q_process(2).lt.0.0) then
                    if (rain_g_q_process(2).le.-rain_q_fixed(2)) then
                      ice_full_sublimation_pending(i,k)=.true.
                      ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),4)
                    endif
                  endif
                endif
              endif
            endif
            rain_ng_aut_q_fixed=rain_q_fixed
            rain_ng_aut_n_fixed=rain_n_fixed
            rain_ng_aut_bg_fixed=rain_bg_fixed
            rain_ng_aut_t_fixed=rain_t_fixed
            rain_ng_aut_qv_fixed=rain_qv_stage
            rain_q_process_request=rain_g_q_process
            rain_n_process_request=rain_g_n_process
            rain_bg_process_request=rain_g_bg_process
            rain_t_process_request=rain_g_t_process
            if (rain_bg_rates_feasible) then
              pr87_g_reason=0
              pr87_g_vapor_reason=0
              if (pr67_trace_this_call) then
                call kdm6_rain_process_state_valid( &
                     rain_q_fixed+rain_g_q_process,rain_n_fixed+rain_g_n_process, &
                     rain_bg_fixed+rain_g_bg_process,rain_t_fixed+rain_g_t_process, &
                     dry_carrier_density(i,k),pidnr,qmin,ncmin,qcrmin,dmr, &
                     lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &
                     lamdacmax,pidni,dmi,lamdaimin,lamdaimax, &
                     pr87_g_endpoint_valid,rain_full_evap_pending(i,k), &
                     ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
                     failure_reason=pr87_g_reason, &
                     ice_sublimation_pending=ice_full_sublimation_pending(i,k))
                pr87_endpoint_qv=rain_qv_stage+rain_g_qv_process
                if (.not.ieee_is_finite(pr87_endpoint_qv) .or. pr87_endpoint_qv.lt.0.0) &
                     pr87_g_vapor_reason=10
              endif
              call kdm6_rain_process_fraction(rain_q_fixed,rain_g_q_process, &
                   rain_n_fixed,rain_g_n_process,rain_bg_fixed,rain_g_bg_process, &
                   rain_t_fixed,rain_g_t_process,rain_full_evap_pending(i,k), &
                   dry_carrier_density(i,k),pidnr,qmin,ncmin, &
                   qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc, &
                   lamdacmin,lamdacmax,pidni,dmi,lamdaimin,lamdaimax, &
                   rain_g_alpha,rain_process_feasible,rain_process_search_status, &
                   rain_qv_stage,rain_g_qv_process, &
                   ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
                   ice_sublimation_pending=ice_full_sublimation_pending(i,k))
            else
              factor=0.0
              rain_g_alpha=0.0
              rain_process_feasible=.false.
              rain_process_search_status=2
            endif
            if (.not.rain_process_feasible .and. rain_bg_rates_feasible .and. &
                rain_process_search_status.eq.1) then
              call kdm6_rain_process_state_valid(rain_q_fixed,rain_n_fixed, &
                   rain_bg_fixed,rain_t_fixed,dry_carrier_density(i,k),pidnr, &
                   qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0, &
                   pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi,lamdaimin, &
                   lamdaimax,rain_aut_base_valid,rain_full_evap_pending(i,k), &
                   ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
                   ice_sublimation_pending=ice_full_sublimation_pending(i,k))
              if (rain_aut_base_valid .and. ieee_is_finite(rain_qv_stage) .and. &
                  rain_qv_stage.ge.0.0) then
                factor=0.0
                rain_g_alpha=0.0
                rain_process_feasible=.true.
                write(*,*) 'KDM6 cold process deferred at alpha=0, cell/loop',i,k,loop, &
                     ' Qprocess=',rain_q_process_request, &
                     ' Nprocess=',rain_n_process_request, &
                     ' BG/Tprocess=',rain_bg_process_request,rain_t_process_request
              endif
            endif
            if (pr67_trace_this_call .and. rain_bg_rates_feasible .and. &
                rain_g_alpha.lt.1.0 .and. &
                (any(rain_g_q_process.ne.0.0) .or. any(rain_g_n_process.ne.0.0) .or. &
                 rain_g_bg_process.ne.0.0 .or. rain_g_t_process.ne.0.0 .or. &
                 rain_g_qv_process.ne.0.0)) then
              pr87_mass_specific=0.5*(sum(abs(rain_g_q_process))+abs(rain_g_qv_process))
              write(pr87_reason_unit,'(a,1x,a,8(1x,i0),1p,4(1x,es24.16))',iostat=pr87_reason_ios) &
                   'PR87_ADMISSION','G',i,lat,k,loop,rain_process_search_status, &
                   pr87_g_reason,pr87_g_vapor_reason, &
                   merge(1,0,rain_full_evap_pending(i,k)),rain_g_alpha, &
                   pr87_mass_specific,dry_carrier_density(i,k),delz(i,k)
              if (pr87_reason_ios.ne.0) error stop 'PR87 G reason write failed'
            endif
            if (.not.rain_process_feasible) then
              write(*,'(a,9(1x,i0))') 'PR87_GSEARCH_FAIL_META', &
                   pr87_model_timestep,lat,i,k,loop,n,rain_process_search_status, &
                   merge(1,0,rain_full_evap_pending(i,k)), &
                   merge(1,0,ice_full_sublimation_pending(i,k))
              write(*,'(a,26(1x,es26.17))') 'PR87_GSEARCH_FAIL_STATE', &
                   real(rain_q_fixed,8),real(rain_g_q_process,8), &
                   real(rain_n_fixed,8),real(rain_g_n_process,8), &
                   real(rain_bg_fixed,8),real(rain_g_bg_process,8), &
                   real(rain_t_fixed,8),real(rain_g_t_process,8), &
                   real(dry_carrier_density(i,k),8),real(pidnr,8),real(qmin,8), &
                   real(ncmin,8),real(qcrmin,8),real(dmr,8)
              write(*,'(a,16(1x,es26.17))') 'PR87_GSEARCH_FAIL_CONFIG', &
                   real(lamdarmin,8),real(lamdarmax,8),100.0_8,900.0_8, &
                   real(pidnc,8),real(dmc,8),real(lamdacmin,8),real(lamdacmax,8), &
                   real(pidni,8),real(dmi,8),real(lamdaimin,8),real(lamdaimax,8), &
                   real(rain_qv_stage,8),real(rain_g_qv_process,8), &
                   real(PR85_ICE_NATIVE_INACTIVE_MAX,8),real(rain_g_alpha,8)
              flush(6)
              if (.not.rain_bg_rates_feasible) then
                write(*,*) 'KDM6 cold process status=UNSUPPORTED_VOLUME_RATE at cell',i,k
              elseif (rain_process_search_status.eq.1) then
                write(*,*) 'KDM6 cold process status=NO_FEASIBLE_STEP at cell',i,k
              else
                write(*,*) 'KDM6 cold process status=SEARCH_FAILURE at cell',i,k
              endif
              write(*,*) 'KDM6 cold process rejected at cell',i,k, &
                   ' Qfixed/Qproc=',rain_q_fixed,rain_q_process, &
                   ' Nfixed/Nproc=',rain_n_fixed,rain_n_process, &
                   ' BGfixed/BGproc=',rain_bg_fixed,rain_bg_process, &
                   ' BGinput/massRates/rho_status=',brs(i,k),pgdep(i,k), &
                   progb_status(i,k), &
                   pracs(i,k),dens,pgaci(i,k),deni,paacw(i,k),denr, &
                   ' BGpartnerVolumeRates=',rain_pgdep_bg_rate, &
                   rain_pracs_bg_rate,rain_pgaci_bg_rate,rain_paacw_bg_rate, &
                   ' staleBGpartners=',bracs(i,k),bgaci(i,k),baacw(i,k), &
                   ' Tfixed/Tproc=',rain_t_fixed,rain_t_process, &
                   ' alpha=',factor
              error stop 'KDM6 cold rain process rejected an infeasible moment state'
            endif
            factor=rain_g_alpha
            rain_process_alpha=rain_g_alpha
            rain_q_process=rain_g_q_process
            rain_n_process=rain_g_n_process
            rain_bg_process=rain_g_bg_process
            rain_t_process=rain_g_t_process
            pracw(i,k)=pracw(i,k)*rain_ng_alpha
            piacw(i,k)=piacw(i,k)*rain_ng_alpha
            pmulcs(i,k)=pmulcs(i,k)*rain_ng_alpha
            pmulcg(i,k)=pmulcg(i,k)*rain_ng_alpha
            pmulrs(i,k)=pmulrs(i,k)*rain_ng_alpha
            pmulrg(i,k)=pmulrg(i,k)*rain_ng_alpha
            prevp(i,k)=prevp(i,k)*rain_ng_alpha
            psdep(i,k)=psdep(i,k)*rain_ng_alpha
            pidep(i,k)=pidep(i,k)*rain_ng_alpha
            pinud(i,k)=pinud(i,k)*rain_ng_alpha
            psaut(i,k)=psaut(i,k)*rain_ng_alpha
            psaci(i,k)=psaci(i,k)*rain_ng_alpha
            nccol(i,k)=nccol(i,k)*rain_ng_alpha
            nracw(i,k)=nracw(i,k)*rain_ng_alpha
            niacw(i,k)=niacw(i,k)*rain_ng_alpha
            ninud(i,k)=ninud(i,k)*rain_ng_alpha
            nmulcs(i,k)=nmulcs(i,k)*rain_ng_alpha
            nmulcg(i,k)=nmulcg(i,k)*rain_ng_alpha
            nmulrs(i,k)=nmulrs(i,k)*rain_ng_alpha
            nmulrg(i,k)=nmulrg(i,k)*rain_ng_alpha
            nsaci(i,k)=nsaci(i,k)*rain_ng_alpha
            nsaut(i,k)=nsaut(i,k)*rain_ng_alpha
            nrcol(i,k)=nrcol(i,k)*rain_ng_alpha
            paacw(i,k) = paacw(i,k)*factor
            naacw(i,k) = naacw(i,k)*factor
            pracs(i,k) = pracs(i,k)*factor
            praci(i,k) = praci(i,k)*factor
            piacr(i,k) = piacr(i,k)*factor
            psacr(i,k) = psacr(i,k)*factor
            pgacr(i,k) = pgacr(i,k)*factor
            pgdep(i,k) = pgdep(i,k)*factor
            pgaci(i,k) = pgaci(i,k)*factor
            pgaut(i,k) = pgaut(i,k)*factor
            pgacs(i,k) = pgacs(i,k)*factor
            nraci(i,k) = nraci(i,k)*factor
            niacr(i,k) = niacr(i,k)*factor
            nsacr(i,k) = nsacr(i,k)*factor
            ngacr(i,k) = ngacr(i,k)*factor
            ngaci(i,k) = ngaci(i,k)*factor
            rain_ng_alpha_initial=rain_ng_alpha
            rain_aut_alpha_initial=rain_aut_alpha
            rain_g_alpha_initial=rain_g_alpha
            rain_composite_rate_base=[ &
                 pracw(i,k), piacw(i,k), pmulcs(i,k), pmulcg(i,k), pmulrs(i,k), &
                 pmulrg(i,k), prevp(i,k), psdep(i,k), pidep(i,k), pinud(i,k), &
                 psaut(i,k), psaci(i,k), nccol(i,k), nracw(i,k), niacw(i,k), &
                 ninud(i,k), nmulcs(i,k), nmulcg(i,k), nmulrs(i,k), nmulrg(i,k), &
                 nsaci(i,k), nsaut(i,k), nrcol(i,k), praut(i,k), nraut(i,k), &
                 paacw(i,k), naacw(i,k), pracs(i,k), praci(i,k), piacr(i,k), &
                 psacr(i,k), pgacr(i,k), pgdep(i,k), pgaci(i,k), pgaut(i,k), &
                 pgacs(i,k), nraci(i,k), niacr(i,k), nsacr(i,k), ngacr(i,k), &
                 ngaci(i,k) ]
            rain_composite_gamma=1.0
            do rain_composite_retry=0,24
              rain_ng_alpha=rain_ng_alpha_initial*rain_composite_gamma
              rain_aut_alpha=rain_aut_alpha_initial*rain_composite_gamma
              rain_g_alpha=rain_g_alpha_initial*rain_composite_gamma
              rain_process_alpha=rain_g_alpha
              rain_composite_rate_index=0
              rain_composite_rate_index=rain_composite_rate_index+1
              pracw(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              piacw(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pmulcs(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pmulcg(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pmulrs(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pmulrg(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              prevp(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              psdep(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pidep(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pinud(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              psaut(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              psaci(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nccol(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nracw(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              niacw(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              ninud(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nmulcs(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nmulcg(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nmulrs(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nmulrg(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nsaci(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nsaut(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nrcol(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              praut(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nraut(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              paacw(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              naacw(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pracs(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              praci(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              piacr(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              psacr(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pgacr(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pgdep(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pgaci(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pgaut(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              pgacs(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nraci(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              niacr(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              nsacr(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              ngacr(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              rain_composite_rate_index=rain_composite_rate_index+1
              ngaci(i,k)=rain_composite_rate_base(rain_composite_rate_index)*rain_composite_gamma
              call kdm6_mass_volume_rate(pgdep(i,k),rhox(i,k), &
                   rain_pgdep_bg_rate,rain_bg_rate_valid)
              if (.not.rain_bg_rate_valid) error stop 'KDM6 invalid scaled graupel deposition volume'
              biacr(i,k)=piacr(i,k)*(1.-delta3)/denr
              baacw(i,k)=paacw(i,k)/denr
              bsacr(i,k)=psacr(i,k)*(1.-delta2)/denr
              braci(i,k)=praci(i,k)*(1.-delta3)/deni
              bracs(i,k)=pracs(i,k)*(1.-delta2)/dens
              bgaci(i,k)=pgaci(i,k)/deni
              bgacr(i,k)=pgacr(i,k)/denr
              bsdep(i,k)=psdep(i,k)/dens
              rain_composite_valid=.true.
              rain_ng_aut_q_fixed=rain_q_before+rain_ng_alpha*rain_ng_q_process
              rain_ng_aut_n_fixed=rain_n_before+rain_ng_alpha*rain_ng_n_process
              rain_ng_aut_bg_fixed=rain_bg_before+rain_ng_alpha*rain_ng_bg_process
              rain_ng_aut_t_fixed=rain_t_before+rain_ng_alpha*rain_ng_t_process
              rain_ng_aut_qv_fixed=rain_qv_before+rain_ng_alpha*rain_ng_qv_process
              rain_ng_aut_q_fixed=rain_ng_aut_q_fixed+rain_aut_alpha*rain_aut_q_process
              rain_ng_aut_n_fixed=rain_ng_aut_n_fixed+rain_aut_alpha*rain_aut_n_process
              rain_ng_aut_qv_fixed=rain_ng_aut_qv_fixed+rain_aut_alpha*0.0
              rain_qv_stage=rain_ng_aut_qv_fixed

! Build the exact native-order REAL32 transaction in local values first.
! No cloud/rain/ice/snow/graupel, number, vapor, heat, or volume state is
! committed until the complete candidate passes all paired-state checks.
            work2(i,k)=-(prevp(i,k)+psdep(i,k)+pgdep(i,k)+pinud(i,k)+pidep(i,k))
            rain_qv_after=q(i,k)+work2(i,k)*dtcld
            rain_q_after(1)=qci(i,k,1)-(praut(i,k)+pracw(i,k)+piacw(i,k) &
                          +paacw(i,k)+paacw(i,k)+pmulcs(i,k)+pmulcg(i,k))*dtcld
            rain_n_after(1)=nci(i,k,1)+(-nraut(i,k)-nccol(i,k)-nracw(i,k) &
                          -niacw(i,k)-naacw(i,k)-naacw(i,k))*dtcld
            rain_q_after(3)=qrs(i,k,1)+(praut(i,k)+pracw(i,k)+prevp(i,k) &
                           -piacr(i,k)-pgacr(i,k)-psacr(i,k)-pmulrs(i,k)-pmulrg(i,k))*dtcld
            rain_n_after(3)=nrs(i,k,1)+(nraut(i,k)-nrcol(i,k)-niacr(i,k) &
                           -nraci(i,k)-nsacr(i,k)-ngacr(i,k))*dtcld
            rain_q_after(2)=qci(i,k,2)-(psaut(i,k)+praci(i,k)+psaci(i,k)+pgaci(i,k) &
                           -pinud(i,k)-pidep(i,k)-piacw(i,k)-pmulcs(i,k)-pmulcg(i,k) &
                           -pmulrs(i,k)-pmulrg(i,k))*dtcld
            rain_n_after(2)=nci(i,k,2)+(-nraci(i,k)-nsaci(i,k)-ngaci(i,k)-niacr(i,k) &
                           +ninud(i,k)+nmulcs(i,k)+nmulcg(i,k)+nmulrs(i,k)+nmulrg(i,k) &
                           -nsaut(i,k))*dtcld
            rain_q_after(4)=qrs(i,k,2)+(psdep(i,k)+psaut(i,k)+paacw(i,k)-pgaut(i,k) &
                           +piacr(i,k)*delta3+praci(i,k)*delta3+psaci(i,k)-pgacs(i,k) &
                           -pracs(i,k)*(1.-delta2)+psacr(i,k)*delta2)*dtcld
            rain_q_after(5)=qrs(i,k,3)+(pgdep(i,k)+pgaut(i,k)+piacr(i,k)*(1.-delta3) &
                           +praci(i,k)*(1.-delta3)+psacr(i,k)*(1.-delta2) &
                           +pracs(i,k)*(1.-delta2)+pgaci(i,k)+paacw(i,k)+pgacr(i,k) &
                           +pgacs(i,k))*dtcld
            rain_bg_after=brs(i,k)+(rain_pgdep_bg_rate+biacr(i,k)+braci(i,k) &
                           +bsacr(i,k)+bracs(i,k)+bgaci(i,k)+baacw(i,k)+bgacr(i,k))*dtcld
            xlf=xls-xl(i,k)
            xlwork2=-xls*(psdep(i,k)+pgdep(i,k)+pidep(i,k)+pinud(i,k)) &
                    -xl(i,k)*prevp(i,k)-xlf*(piacr(i,k)+paacw(i,k)+pmulcs(i,k) &
                    +pmulcg(i,k)+pmulrs(i,k)+pmulrg(i,k)+piacw(i,k)+paacw(i,k) &
                    +pgacr(i,k)+psacr(i,k))
            if (.not.ieee_is_finite(cpm(i,k)) .or. cpm(i,k).le.0.0) &
              error stop 'KDM6 cold transaction has invalid heat capacity'
            rain_t_after=t(i,k)-xlwork2/cpm(i,k)*dtcld
            rain_ccn3_after=rain_ccn3_before
            rain_n_ccn_transfer=0.0
            rain_composite_valid=all(ieee_is_finite([rain_qv_after,rain_q_after, &
                 rain_n_after,rain_bg_after,rain_t_after,rain_ccn3_after]))
            if (rain_composite_valid) then
              rain_composite_valid=rain_qv_after.ge.0.0 .and. all(rain_q_after.ge.0.0) &
                   .and. all(rain_n_after.ge.0.0) .and. rain_bg_after.ge.0.0 &
                   .and. rain_t_after.gt.0.0 .and. rain_ccn3_after.ge.0.0
            endif
! Move orphan rain number only when REAL32 mass is exactly exhausted;
! positive subthreshold rain keeps its paired number moment.
            pr87_ice_sublimation_extinctions=0
            pr87_ice_sublimation_n_preclear=rain_n_after(2)
            pr87_ice_sublimation_dn=0.0
            if (rain_composite_valid) then
              if (ieee_is_finite(rain_n_after(2))) then
                if (rain_n_after(2).ge.0.0) then
                  if (ice_full_sublimation_pending(i,k) .and. &
                      rain_q_after(2).eq.0.0) then
                    if (rain_n_after(2).gt.0.0) then
                      pr87_ice_sublimation_extinctions=1
                      pr87_ice_sublimation_dn=-rain_n_after(2)
                    endif
                    rain_n_after(2)=0.0
                  endif
                endif
              endif
            endif
            if (rain_full_evap_pending(i,k) .and. rain_q_after(3).eq.0.0) then
              rain_n_ccn_transfer=rain_n_after(3)
              rain_ccn3_after=rain_ccn3_after+rain_n_ccn_transfer
              rain_n_after(3)=0.0
              if (.not.ieee_is_finite(rain_ccn3_after)) rain_composite_valid=.false.
            endif
            if (rain_composite_valid) then
              call kdm6_rain_process_state_valid(rain_q_after,rain_n_after,rain_bg_after, &
                   rain_t_after,dry_carrier_density(i,k),pidnr,qmin,ncmin,qcrmin,dmr, &
                   lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin,lamdacmax, &
                   pidni,dmi,lamdaimin,lamdaimax,rain_stored_state_feasible, &
                   rain_full_evap_pending(i,k),ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)
              rain_composite_valid=rain_stored_state_feasible
            endif
            if (rain_composite_valid) exit
            if (rain_composite_retry.eq.24) &
              error stop 'KDM6 composite backtracking exhausted without valid state'
            if (rain_composite_retry.eq.23) then
              rain_composite_gamma=0.0
            else
              rain_composite_gamma=0.5*rain_composite_gamma
            endif
            enddo
            if (ice_full_sublimation_pending(i,k) .and. ice_extinction_cause(i,k).gt.1) then
              open(newunit=pr87_ice_sublimation_unit, &
                   file='pr87_ice_extinction.raw',form='formatted', &
                   status='unknown',position='append',action='write', &
                   iostat=pr87_ice_sublimation_ios)
              if (pr87_ice_sublimation_ios.ne.0) &
                error stop 'PR87 ice-extinction ledger open failed'
              write(pr87_ice_sublimation_unit,'(a)',iostat=pr87_ice_sublimation_ios) &
                   '# PR87_ICE_EXTINCTION step,i,lat,k,loop,n_sed,cause_bits,'// &
                   'Qbefore[kg/kg],Nbefore[m-3],Qafter[kg/kg],Nafter[m-3],'// &
                   'Npreclear[m-3],dN[m-3],raw_pidep[kg/kg/s],capped_pidep[kg/kg/s],'// &
                   'alphaNG,alphaAUT,alphaG,gammaComposite,retry,extinctions'
              if (pr87_ice_sublimation_ios.ne.0) &
                error stop 'PR87 ice-extinction ledger header failed'
              write(pr87_ice_sublimation_unit,'(a,7i9,1p,12e24.16,0p,2i9)', &
                   iostat=pr87_ice_sublimation_ios) 'PR87_ICE_EXTINCTION', &
                   pr87_model_timestep,i,lat,k,loop,n,ice_extinction_cause(i,k), &
                   rain_q_before(2),rain_n_before(2),rain_q_after(2),rain_n_after(2), &
                   pr87_ice_sublimation_n_preclear,pr87_ice_sublimation_dn, &
                   ice_sublimation_raw_pidep(i,k),ice_sublimation_capped_pidep(i,k), &
                   rain_ng_alpha,rain_aut_alpha,rain_g_alpha,rain_composite_gamma, &
                   rain_composite_retry,pr87_ice_sublimation_extinctions
              if (pr87_ice_sublimation_ios.ne.0) &
                error stop 'PR87 ice-extinction ledger write failed'
              close(pr87_ice_sublimation_unit,iostat=pr87_ice_sublimation_ios)
              if (pr87_ice_sublimation_ios.ne.0) &
                error stop 'PR87 ice-extinction ledger close failed'
            endif
            factor=rain_g_alpha
            rain_composite_stored_noop=( &
                 (rain_ng_alpha.gt.0.0 .and. &
                  (any(rain_ng_q_process.ne.0.0) .or. any(rain_ng_n_process.ne.0.0) .or. &
                   rain_ng_bg_process.ne.0.0 .or. rain_ng_t_process.ne.0.0 .or. &
                   rain_ng_qv_process.ne.0.0)) .or. &
                 (rain_aut_alpha.gt.0.0 .and. &
                  (any(rain_aut_q_process.ne.0.0) .or. any(rain_aut_n_process.ne.0.0))) .or. &
                 (rain_g_alpha.gt.0.0 .and. &
                  (any(rain_q_process_request.ne.0.0) .or. any(rain_n_process_request.ne.0.0) .or. &
                   rain_bg_process_request.ne.0.0 .or. rain_t_process_request.ne.0.0 .or. &
                   rain_g_qv_process.ne.0.0))) .and. &
                 all(rain_composite_rate_base*rain_composite_gamma.eq.0.0)

! Commit the validated REAL32 transaction atomically.
            q(i,k)=rain_qv_after
            qci(i,k,1)=rain_q_after(1)
            qci(i,k,2)=rain_q_after(2)
            qrs(i,k,1)=rain_q_after(3)
            qrs(i,k,2)=rain_q_after(4)
            qrs(i,k,3)=rain_q_after(5)
            nci(i,k,1)=rain_n_after(1)
            nci(i,k,2)=rain_n_after(2)
            nrs(i,k,1)=rain_n_after(3)
            nci(i,k,3)=rain_ccn3_after
            brs(i,k)=rain_bg_after
            t(i,k)=rain_t_after

            call kdm6_rain_process_state_valid(rain_q_after,rain_n_after,brs(i,k), &
                 t(i,k),dry_carrier_density(i,k),pidnr,qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax, &
                 100.0,900.0,pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi, &
                 lamdaimin,lamdaimax,rain_stored_state_feasible, &
                 ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)
            if (.not.rain_stored_state_feasible) then
              write(*,*) 'KDM6 stored cold endpoint status=INVALID_STORED_STATE at cell',i,k, &
                   ' accepted alpha=',rain_process_alpha, &
                   ' Q=',rain_q_after,' N=',rain_n_after, &
                   ' BG=',brs(i,k),' T=',t(i,k)
              error stop 'KDM6 rejected an invalid stored process endpoint'
            endif
            if (ice_full_sublimation_pending(i,k) .and. ice_extinction_cause(i,k).le.1) then
              open(newunit=pr87_ice_sublimation_unit, &
                   file='pr87_ice_sublimation_pending.raw',form='formatted', &
                   status='unknown',position='append',action='write', &
                   iostat=pr87_ice_sublimation_ios)
              if (pr87_ice_sublimation_ios.ne.0) &
                error stop 'PR87 ice-sublimation ledger open failed'
              write(pr87_ice_sublimation_unit,'(a)',iostat=pr87_ice_sublimation_ios) &
                   '# PR87_ICE_SUBLIMATION step,i,lat,k,loop,n_sed,events,'// &
                   'raw_pidep[kg/kg/s],capped_pidep[kg/kg/s],Qbefore[kg/kg],Nbefore[m-3],'// &
                   'Qafter[kg/kg],Nafter[m-3],Ncandidate_preclear[m-3],dN_extinction[m-3],'// &
                   'alphaNG,alphaAUT,alphaG,gammaComposite,retry,extinctions'
              if (pr87_ice_sublimation_ios.ne.0) &
                error stop 'PR87 ice-sublimation ledger header failed'
              write(pr87_ice_sublimation_unit,'(a,7i9,1p,12e24.16,0p,2i9)', &
                   iostat=pr87_ice_sublimation_ios) 'PR87_ICE_SUBLIMATION', &
                   pr87_model_timestep,i,lat,k,loop,n, &
                   ice_sublimation_event_count(i,k), &
                   ice_sublimation_raw_pidep(i,k),ice_sublimation_capped_pidep(i,k), &
                   ice_sublimation_q_before(i,k),ice_sublimation_n_before(i,k), &
                   rain_q_after(2),rain_n_after(2), &
                   pr87_ice_sublimation_n_preclear,pr87_ice_sublimation_dn, &
                   rain_ng_alpha,rain_aut_alpha, &
                   rain_g_alpha,rain_composite_gamma,rain_composite_retry, &
                   pr87_ice_sublimation_extinctions
              if (pr87_ice_sublimation_ios.ne.0) &
                error stop 'PR87 ice-sublimation ledger write failed'
              close(pr87_ice_sublimation_unit,iostat=pr87_ice_sublimation_ios)
              if (pr87_ice_sublimation_ios.ne.0) &
                error stop 'PR87 ice-sublimation ledger close failed'
              ice_full_sublimation_pending(i,k)=.false.
              ice_sublimation_event_count(i,k)=0
            endif
            if (ice_full_sublimation_pending(i,k) .and. ice_extinction_cause(i,k).gt.1) then
              ice_full_sublimation_pending(i,k)=.false.
              ice_extinction_cause(i,k)=0
              ice_sublimation_event_count(i,k)=0
            endif
! PR89: same-call column water measure, DEN*DELZ (kg m-2).
! KDM62D has no horizontal area argument; do not claim grid-area totals.
            pr89_cold_weight=DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))
            pr89_cold_transactions=pr89_cold_transactions+1
            pr90_cold_transactions(i)=pr90_cold_transactions(i)+1
            do pr89_cold_group=1,3
              select case(pr89_cold_group)
              case(1)
                pr89_cold_q=DBLE(rain_ng_q_process)
                pr89_cold_qv=DBLE(rain_ng_qv_process)
                pr89_cold_alpha=DBLE(rain_ng_alpha)
              case(2)
                pr89_cold_q=DBLE(rain_aut_q_process)
                pr89_cold_qv=0.0d0
                pr89_cold_alpha=DBLE(rain_aut_alpha)
              case(3)
                pr89_cold_q=DBLE(rain_q_process_request)
                pr89_cold_qv=DBLE(rain_g_qv_process)
                pr89_cold_alpha=DBLE(rain_process_alpha)
              end select
              do pr89_cold_stage=1,3
                select case(pr89_cold_stage)
                case(1)
                  pr89_cold_scale=1.0d0
                case(2)
                  pr89_cold_scale=pr89_cold_alpha
                case(3)
                  pr89_cold_scale=1.0d0-pr89_cold_alpha
                end select
                pr89_cold_signed=(SUM(pr89_cold_q)+pr89_cold_qv)*pr89_cold_scale
                pr89_cold_half_l1=0.5d0*(SUM(ABS(pr89_cold_q))+ABS(pr89_cold_qv))* &
                     ABS(pr89_cold_scale)
                pr89_cold_water(1,pr89_cold_stage,pr89_cold_group)= &
                     pr89_cold_water(1,pr89_cold_stage,pr89_cold_group)+ &
                     pr89_cold_signed*pr89_cold_weight
                pr89_cold_water(2,pr89_cold_stage,pr89_cold_group)= &
                     pr89_cold_water(2,pr89_cold_stage,pr89_cold_group)+ &
                     pr89_cold_half_l1*pr89_cold_weight
                pr90_cold_water(1,pr89_cold_stage,pr89_cold_group,i)= &
                     pr90_cold_water(1,pr89_cold_stage,pr89_cold_group,i)+ &
                     pr89_cold_signed*pr89_cold_weight
                pr90_cold_water(2,pr89_cold_stage,pr89_cold_group,i)= &
                     pr90_cold_water(2,pr89_cold_stage,pr89_cold_group,i)+ &
                     pr89_cold_half_l1*pr89_cold_weight
              enddo
            enddo
            if (.false.) then
            write(pr85_cold_unit,'(a,8i8,1x,l1,1p,*(1x,e24.16))',iostat=pr85_cold_ios) &
                 'PR85_KDM6_COLD',i,lat,k,loop,rain_ng_search_status, &
                 rain_aut_search_status,rain_process_search_status,rain_composite_retry, &
                 rain_composite_stored_noop,dtcld,dry_carrier_density(i,k),rain_composite_gamma, &
                 rain_composite_rate_base*rain_composite_gamma, &
                 rain_ng_alpha,rain_aut_alpha,rain_process_alpha, &
                 rain_q_before,rain_ng_aut_q_fixed,rain_q_process_request,rain_q_after, &
                 rain_n_before,rain_ng_aut_n_fixed,rain_n_process_request,rain_n_after, &
                 rain_bg_before,rain_ng_aut_bg_fixed,rain_bg_process_request,brs(i,k), &
                 rain_t_before,rain_ng_aut_t_fixed,rain_t_process_request,t(i,k), &
                 rain_qv_before,rain_ng_aut_qv_fixed,rain_g_qv_process,rain_qv_after, &
                 rain_ccn3_before,rain_n_ccn_transfer,rain_ccn3_after, &
                 rain_ng_q_process,rain_ng_alpha*rain_ng_q_process, &
                 (1.0-rain_ng_alpha)*rain_ng_q_process, &
                 rain_ng_n_process,rain_ng_alpha*rain_ng_n_process, &
                 (1.0-rain_ng_alpha)*rain_ng_n_process, &
                 rain_ng_bg_process,rain_ng_alpha*rain_ng_bg_process, &
                 (1.0-rain_ng_alpha)*rain_ng_bg_process, &
                 rain_ng_t_process,rain_ng_alpha*rain_ng_t_process, &
                 (1.0-rain_ng_alpha)*rain_ng_t_process, &
                 rain_ng_qv_process,rain_ng_alpha*rain_ng_qv_process, &
                 (1.0-rain_ng_alpha)*rain_ng_qv_process, &
                 rain_aut_q_process,rain_aut_alpha*rain_aut_q_process, &
                 (1.0-rain_aut_alpha)*rain_aut_q_process, &
                 rain_aut_n_process,rain_aut_alpha*rain_aut_n_process, &
                 (1.0-rain_aut_alpha)*rain_aut_n_process, &
                 0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0, &
                 rain_q_process_request,rain_g_alpha*rain_q_process_request, &
                 (1.0-rain_g_alpha)*rain_q_process_request, &
                 rain_n_process_request,rain_g_alpha*rain_n_process_request, &
                 (1.0-rain_g_alpha)*rain_n_process_request, &
                 rain_bg_process_request,rain_g_alpha*rain_bg_process_request, &
                 (1.0-rain_g_alpha)*rain_bg_process_request, &
                 rain_t_process_request,rain_g_alpha*rain_t_process_request, &
                 (1.0-rain_g_alpha)*rain_t_process_request, &
                 rain_g_qv_process,rain_g_alpha*rain_g_qv_process, &
                 (1.0-rain_g_alpha)*rain_g_qv_process, &
                 DBLE(qci(i,k,1))-(DBLE(rain_q_before(1))+DBLE(rain_ng_alpha)*DBLE(rain_ng_q_process(1)) &
                    +DBLE(rain_aut_alpha)*DBLE(rain_aut_q_process(1)) &
                    +DBLE(rain_g_alpha)*DBLE(rain_q_process_request(1))), &
                 DBLE(qci(i,k,2))-(DBLE(rain_q_before(2))+DBLE(rain_ng_alpha)*DBLE(rain_ng_q_process(2)) &
                    +DBLE(rain_aut_alpha)*DBLE(rain_aut_q_process(2)) &
                    +DBLE(rain_g_alpha)*DBLE(rain_q_process_request(2))), &
                 DBLE(qrs(i,k,1))-(DBLE(rain_q_before(3))+DBLE(rain_ng_alpha)*DBLE(rain_ng_q_process(3)) &
                    +DBLE(rain_aut_alpha)*DBLE(rain_aut_q_process(3)) &
                    +DBLE(rain_g_alpha)*DBLE(rain_q_process_request(3))), &
                 DBLE(qrs(i,k,2))-(DBLE(rain_q_before(4))+DBLE(rain_ng_alpha)*DBLE(rain_ng_q_process(4)) &
                    +DBLE(rain_aut_alpha)*DBLE(rain_aut_q_process(4)) &
                    +DBLE(rain_g_alpha)*DBLE(rain_q_process_request(4))), &
                 DBLE(qrs(i,k,3))-(DBLE(rain_q_before(5))+DBLE(rain_ng_alpha)*DBLE(rain_ng_q_process(5)) &
                    +DBLE(rain_aut_alpha)*DBLE(rain_aut_q_process(5)) &
                    +DBLE(rain_g_alpha)*DBLE(rain_q_process_request(5))), &
                 DBLE(nci(i,k,1))-(DBLE(rain_n_before(1))+DBLE(rain_ng_alpha)*DBLE(rain_ng_n_process(1)) &
                    +DBLE(rain_aut_alpha)*DBLE(rain_aut_n_process(1)) &
                    +DBLE(rain_g_alpha)*DBLE(rain_n_process_request(1))), &
                 DBLE(nci(i,k,2))-(DBLE(rain_n_before(2))+DBLE(rain_ng_alpha)*DBLE(rain_ng_n_process(2)) &
                    +DBLE(rain_aut_alpha)*DBLE(rain_aut_n_process(2)) &
                    +DBLE(rain_g_alpha)*DBLE(rain_n_process_request(2))), &
                 DBLE(nrs(i,k,1))-(DBLE(rain_n_before(3))+DBLE(rain_ng_alpha)*DBLE(rain_ng_n_process(3)) &
                    +DBLE(rain_aut_alpha)*DBLE(rain_aut_n_process(3)) &
                    +DBLE(rain_g_alpha)*DBLE(rain_n_process_request(3))-DBLE(rain_n_ccn_transfer)), &
                 DBLE(nci(i,k,3))-(DBLE(rain_ccn3_before)+DBLE(rain_n_ccn_transfer)), &
                 DBLE(brs(i,k))-(DBLE(rain_bg_before)+DBLE(rain_g_alpha)*DBLE(rain_bg_process_request)), &
                 DBLE(t(i,k))-(DBLE(rain_t_before)+DBLE(rain_ng_alpha)*DBLE(rain_ng_t_process) &
                    +DBLE(rain_g_alpha)*DBLE(rain_t_process_request)), &
                 DBLE(q(i,k))-(DBLE(rain_qv_before)+DBLE(rain_ng_alpha)*DBLE(rain_ng_qv_process) &
                    +DBLE(rain_g_alpha)*DBLE(rain_g_qv_process))
            if (pr85_cold_ios.ne.0) error stop 'PR85 cold budget write failed'
            endif

          else



            value = max(qmin,qci(i,k,1))
            source= (praut(i,k)+pracw(i,k)+paacw(i,k)+paacw(i,k))              &
                   *dtcld
            if (source.gt.value) then
              factor = value/source
              praut(i,k) = praut(i,k)*factor
              pracw(i,k) = pracw(i,k)*factor
              paacw(i,k) = paacw(i,k)*factor
            endif



            value = max(qmin,qrs(i,k,1))
            source = (-paacw(i,k)-praut(i,k)+pseml(i,k)+pgeml(i,k)             &
                     -pracw(i,k)-paacw(i,k)-prevp(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              praut(i,k) = praut(i,k)*factor
              prevp(i,k) = prevp(i,k)*factor
              pracw(i,k) = pracw(i,k)*factor
              paacw(i,k) = paacw(i,k)*factor
              pseml(i,k) = pseml(i,k)*factor
              pgeml(i,k) = pgeml(i,k)*factor
            endif



            value = max(qcrmin,qrs(i,k,2))
            source=(pgacs(i,k)-pseml(i,k)-psevp(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              pgacs(i,k) = pgacs(i,k)*factor
              psevp(i,k) = psevp(i,k)*factor
              pseml(i,k) = pseml(i,k)*factor
            endif



            value = max(qcrmin,qrs(i,k,3))
            source=-(pgacs(i,k)+pgevp(i,k)+pgeml(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              pgacs(i,k) = pgacs(i,k)*factor
              pgevp(i,k) = pgevp(i,k)*factor
              pgeml(i,k) = pgeml(i,k)*factor
            endif



            value = max(ncmin,nci(i,k,1))
            source = (+nraut(i,k)+nccol(i,k)+nracw(i,k)+naacw(i,k)             &
                     +naacw(i,k))*dtcld
            if (source.gt.value) then
              factor = value/source
              nraut(i,k) = nraut(i,k)*factor
              nccol(i,k) = nccol(i,k)*factor
              nracw(i,k) = nracw(i,k)*factor
              naacw(i,k) = naacw(i,k)*factor
            endif



            value = max(nrmin,nrs(i,k,1))
            source = (-nraut(i,k)+nrcol(i,k)-nseml(i,k)-ngeml(i,k)             &
                      )*dtcld
            if (source.gt.value) then
              factor = value/source
              nraut(i,k) = nraut(i,k)*factor
              nrcol(i,k) = nrcol(i,k)*factor
              nseml(i,k) = nseml(i,k)*factor
              ngeml(i,k) = ngeml(i,k)*factor
            endif

            work2(i,k)=-(prevp(i,k)+psevp(i,k)+pgevp(i,k))



            if (progb_status(i,k) == PROGB_PSD_ACTIVE) then
              bgevp(i,k)=pgevp(i,k)/rhox(i,k)
              bgeml(i,k)=pgeml(i,k)/rhox(i,k)
            else if (progb_status(i,k) == PROGB_ABSENT .and. &
                     pgevp(i,k) == 0.0 .and. pgeml(i,k) == 0.0) then
              bgevp(i,k)=0.0
              bgeml(i,k)=0.0
            else
              error stop 'ProgB status invalid for volume conversion'
            endif
            if (pgacs(i,k).ne.0.0) &
              error stop 'KDM6 unsupported warm graupel source without volume partner'

            rain_q_before=[qci(i,k,1),qci(i,k,2),qrs(i,k,1),qrs(i,k,2),qrs(i,k,3)]
            rain_n_before=[nci(i,k,1),nci(i,k,2),nrs(i,k,1)]
            rain_bg_before=brs(i,k)
            rain_t_before=t(i,k)
            rain_qv_before=q(i,k)
            rain_ccn3_before=nci(i,k,3)
            rain_warm_rate_base=[praut(i,k),pracw(i,k),paacw(i,k),nraut(i,k), &
                 nccol(i,k),nracw(i,k),naacw(i,k),prevp(i,k),pseml(i,k), &
                 pgeml(i,k),psevp(i,k),pgacs(i,k),pgevp(i,k),nrcol(i,k), &
                 nseml(i,k),ngeml(i,k)]
            rain_warm_q_process(1)=-(rain_warm_rate_base(1)+rain_warm_rate_base(2) &
                 +rain_warm_rate_base(3)+rain_warm_rate_base(3))*dtcld
            rain_warm_q_process(2)=0.0
            rain_warm_q_process(3)=(rain_warm_rate_base(1)+rain_warm_rate_base(2) &
                 +rain_warm_rate_base(8)+rain_warm_rate_base(3)+rain_warm_rate_base(3) &
                 -rain_warm_rate_base(9)-rain_warm_rate_base(10))*dtcld
            rain_warm_q_process(4)=(rain_warm_rate_base(11)-rain_warm_rate_base(12) &
                 +rain_warm_rate_base(9))*dtcld
            rain_warm_q_process(5)=(rain_warm_rate_base(12)+rain_warm_rate_base(13) &
                 +rain_warm_rate_base(10))*dtcld
            rain_warm_n_process(1)=-(rain_warm_rate_base(4)+rain_warm_rate_base(5) &
                 +rain_warm_rate_base(6)+rain_warm_rate_base(7)+rain_warm_rate_base(7))*dtcld
            rain_warm_n_process(2)=0.0
            rain_warm_n_process(3)=(rain_warm_rate_base(4)-rain_warm_rate_base(14) &
                 +rain_warm_rate_base(15)+rain_warm_rate_base(16))*dtcld
            rain_warm_bg_process=(bgevp(i,k)+bgeml(i,k))*dtcld
            rain_warm_xlf=xls-xl(i,k)
            rain_warm_xlwork2=-xl(i,k)*(rain_warm_rate_base(8)+rain_warm_rate_base(11) &
                 +rain_warm_rate_base(13))-rain_warm_xlf*(rain_warm_rate_base(9) &
                 +rain_warm_rate_base(10))
            rain_warm_t_process=-rain_warm_xlwork2/cpm(i,k)*dtcld
            rain_warm_qv_process=work2(i,k)*dtcld

            call kdm6_rain_process_fraction(rain_q_before,rain_warm_q_process, &
                 rain_n_before,rain_warm_n_process,rain_bg_before,rain_warm_bg_process, &
                 rain_t_before,rain_warm_t_process,rain_full_evap_pending(i,k), &
                 dry_carrier_density(i,k),pidnr,qmin,ncmin,qcrmin,dmr, &
                 lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &
                 lamdacmax,pidni,dmi,lamdaimin,lamdaimax,rain_warm_alpha, &
                 rain_warm_feasible,rain_warm_search_status,rain_qv_before, &
                 rain_warm_qv_process,consumer_pair_only=.true.)
            if (.not.rain_warm_feasible) then
              if (rain_warm_search_status.ne.1) &
                error stop 'KDM6 warm process admission search failed'
              call kdm6_rain_process_state_valid(rain_q_before,rain_n_before, &
                   rain_bg_before,rain_t_before,dry_carrier_density(i,k),pidnr, &
                   qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0, &
                   pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi,lamdaimin, &
                   lamdaimax,rain_warm_state_valid,rain_full_evap_pending(i,k),.true.)
              if (rain_warm_state_valid) &
                rain_warm_state_valid=kdm6_unreconstructed_rain_output_valid( &
                     rain_q_before(3),rain_n_before(3),dry_carrier_density(i,k), &
                     pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin)
              if (.not.rain_warm_state_valid .or. rain_qv_before.lt.0.0 .or. &
                  .not.ieee_is_finite(rain_qv_before)) &
                error stop 'KDM6 invalid base before warm process admission'
              rain_warm_alpha=0.0
            endif

            rain_warm_abort=.false.
            rain_warm_state_valid=.false.
            do rain_warm_retry=0,56
              if (rain_warm_retry.gt.0) then
                if (rain_warm_retry.le.32) then
                  rain_warm_alpha=nearest(rain_warm_alpha,-1.0)
                else
                  rain_warm_alpha=0.5*rain_warm_alpha
                endif
              endif
              if (rain_warm_alpha.le.0.0 .and. &
                  .not.(rain_warm_retry.eq.0 .and. rain_warm_search_status.eq.1)) exit
              rain_warm_rate_trial=rain_warm_alpha*rain_warm_rate_base
              rain_warm_q_after(1)=rain_q_before(1)-(rain_warm_rate_trial(1) &
                   +rain_warm_rate_trial(2)+rain_warm_rate_trial(3) &
                   +rain_warm_rate_trial(3))*dtcld
              rain_warm_q_after(2)=rain_q_before(2)
              rain_warm_q_after(3)=rain_q_before(3)+(rain_warm_rate_trial(1) &
                   +rain_warm_rate_trial(2)+rain_warm_rate_trial(8) &
                   +rain_warm_rate_trial(3)+rain_warm_rate_trial(3) &
                   -rain_warm_rate_trial(9)-rain_warm_rate_trial(10))*dtcld
              rain_warm_q_after(4)=rain_q_before(4)+(rain_warm_rate_trial(11) &
                   -rain_warm_rate_trial(12)+rain_warm_rate_trial(9))*dtcld
              rain_warm_q_after(5)=rain_q_before(5)+(rain_warm_rate_trial(12) &
                   +rain_warm_rate_trial(13)+rain_warm_rate_trial(10))*dtcld
              rain_warm_n_after(1)=rain_n_before(1)-(rain_warm_rate_trial(4) &
                   +rain_warm_rate_trial(5)+rain_warm_rate_trial(6) &
                   +rain_warm_rate_trial(7)+rain_warm_rate_trial(7))*dtcld
              rain_warm_n_after(2)=rain_n_before(2)
              rain_warm_n_after(3)=rain_n_before(3)+(rain_warm_rate_trial(4) &
                   -rain_warm_rate_trial(14)+rain_warm_rate_trial(15) &
                   +rain_warm_rate_trial(16))*dtcld
              if (progb_status(i,k) == PROGB_PSD_ACTIVE) then
                rain_warm_bg_after=rain_bg_before+(rain_warm_rate_trial(13)/rhox(i,k) &
                     +rain_warm_rate_trial(10)/rhox(i,k))*dtcld
              else
                rain_warm_bg_after=rain_bg_before
              endif
              rain_warm_xlwork2=-xl(i,k)*(rain_warm_rate_trial(8) &
                   +rain_warm_rate_trial(11)+rain_warm_rate_trial(13)) &
                   -rain_warm_xlf*(rain_warm_rate_trial(9)+rain_warm_rate_trial(10))
              rain_warm_t_after=rain_t_before-rain_warm_xlwork2/cpm(i,k)*dtcld
              work2(i,k)=-(rain_warm_rate_trial(8)+rain_warm_rate_trial(11) &
                   +rain_warm_rate_trial(13))
              rain_warm_qv_after=rain_qv_before+work2(i,k)*dtcld
              rain_ccn3_after=rain_ccn3_before
              if (rain_full_evap_pending(i,k) .and. rain_warm_q_after(3).eq.0.0) then
                rain_ccn3_after=rain_ccn3_after+rain_warm_n_after(3)
                rain_warm_n_after(3)=0.0
              endif
              rain_warm_state_valid=all(ieee_is_finite([rain_warm_q_after, &
                   rain_warm_n_after,rain_warm_bg_after,rain_warm_t_after, &
                   rain_warm_qv_after,rain_ccn3_after]))
              if (rain_warm_state_valid) then
                call kdm6_rain_process_state_valid(rain_warm_q_after,rain_warm_n_after, &
                     rain_warm_bg_after,rain_warm_t_after,dry_carrier_density(i,k),pidnr, &
                     qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0, &
                     pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi,lamdaimin, &
                     lamdaimax,rain_warm_state_valid,rain_full_evap_pending(i,k),.true.)
              endif
              if (rain_warm_state_valid) &
                rain_warm_state_valid=kdm6_unreconstructed_rain_output_valid( &
                     rain_warm_q_after(3),rain_warm_n_after(3),dry_carrier_density(i,k), &
                     pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin)
              if (rain_warm_state_valid .and. rain_warm_qv_after.ge.0.0 .and. &
                  rain_ccn3_after.ge.0.0) exit
              rain_warm_state_valid=.false.
            enddo
            if (.not.rain_warm_state_valid) then
              call kdm6_rain_process_state_valid(rain_q_before,rain_n_before, &
                   rain_bg_before,rain_t_before,dry_carrier_density(i,k),pidnr, &
                   qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0, &
                   pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi,lamdaimin, &
                   lamdaimax,rain_warm_state_valid,rain_full_evap_pending(i,k),.true.)
              if (rain_warm_state_valid) &
                rain_warm_state_valid=kdm6_unreconstructed_rain_output_valid( &
                     rain_q_before(3),rain_n_before(3),dry_carrier_density(i,k), &
                     pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin)
              if (.not.rain_warm_state_valid .or. rain_qv_before.lt.0.0 .or. &
                  .not.ieee_is_finite(rain_qv_before) .or. rain_ccn3_before.lt.0.0) &
                error stop 'KDM6 warm process has no valid stored endpoint'
              rain_warm_alpha=0.0
              rain_warm_rate_trial=0.0
              rain_warm_q_after=rain_q_before
              rain_warm_n_after=rain_n_before
              rain_warm_bg_after=rain_bg_before
              rain_warm_t_after=rain_t_before
              rain_warm_qv_after=rain_qv_before
              rain_ccn3_after=rain_ccn3_before
              rain_warm_search_status=2
              rain_warm_abort=.true.
            endif
            if (rain_warm_abort .and. rain_warm_retry.gt.56) rain_warm_retry=56
            rain_warm_rate_noop=all(rain_warm_rate_trial.eq.0.0)
            rain_warm_state_noop=all(rain_warm_q_after.eq.rain_q_before) .and. &
                 all(rain_warm_n_after.eq.rain_n_before) .and. &
                 rain_warm_bg_after.eq.rain_bg_before .and. &
                 rain_warm_t_after.eq.rain_t_before .and. &
                 rain_warm_qv_after.eq.rain_qv_before .and. &
                 rain_ccn3_after.eq.rain_ccn3_before
! Existing full v17 ledgers remain the reference.
! Sparse PR87 NO_POSITIVE_WARM_STEP trace: status 1 only.
            if (rain_warm_search_status.eq.1 .or. rain_warm_retry.gt.0) then
            write(pr85_warm_unit,'(a,7i8,1x,2l1,1p,*(1x,e24.16))',iostat=pr85_warm_ios) &
                 'WARM',i,lat,k,loop,rain_warm_search_status,rain_warm_retry, &
                 progb_status(i,k),rain_warm_rate_noop,rain_warm_state_noop, &
                 dtcld,dry_carrier_density(i,k),cpm(i,k),xl(i,k),rain_warm_xlf, &
                 rhox(i,k),rain_warm_alpha,rain_warm_rate_base,rain_warm_rate_trial, &
                 rain_q_before,rain_warm_q_after,rain_n_before,rain_warm_n_after, &
                 rain_bg_before,rain_warm_bg_after,rain_t_before,rain_warm_t_after, &
                 rain_qv_before,rain_warm_qv_after,rain_ccn3_before,rain_ccn3_after, &
                 rain_warm_q_process,rain_warm_n_process,rain_warm_bg_process, &
                 rain_warm_t_process,rain_warm_qv_process, &
                 rain_warm_alpha*rain_warm_q_process, &
                 rain_warm_alpha*rain_warm_n_process, &
                 rain_warm_alpha*rain_warm_bg_process, &
                 rain_warm_alpha*rain_warm_t_process, &
                 rain_warm_alpha*rain_warm_qv_process, &
                 real(rain_warm_q_after,8)-real(rain_q_before,8), &
                 real(rain_warm_n_after,8)-real(rain_n_before,8), &
                 real(rain_warm_bg_after,8)-real(rain_bg_before,8), &
                 real(rain_warm_t_after,8)-real(rain_t_before,8), &
                 real(rain_warm_qv_after,8)-real(rain_qv_before,8), &
                 (real(rain_warm_q_after,8)-real(rain_q_before,8)) &
                    -real(rain_warm_alpha,8)*real(rain_warm_q_process,8), &
                 (real(rain_warm_n_after,8)-real(rain_n_before,8)) &
                    -real(rain_warm_alpha,8)*real(rain_warm_n_process,8), &
                 (real(rain_warm_bg_after,8)-real(rain_bg_before,8)) &
                    -real(rain_warm_alpha,8)*real(rain_warm_bg_process,8), &
                 (real(rain_warm_t_after,8)-real(rain_t_before,8)) &
                    -real(rain_warm_alpha,8)*real(rain_warm_t_process,8), &
                 (real(rain_warm_qv_after,8)-real(rain_qv_before,8)) &
                    -real(rain_warm_alpha,8)*real(rain_warm_qv_process,8)
            if (pr85_warm_ios.ne.0) error stop 'PR85 warm budget write failed'
            endif
            if (rain_warm_abort) error stop 'KDM6 warm native endpoint search failed'
            praut(i,k)=rain_warm_rate_trial(1)
            pracw(i,k)=rain_warm_rate_trial(2)
            paacw(i,k)=rain_warm_rate_trial(3)
            nraut(i,k)=rain_warm_rate_trial(4)
            nccol(i,k)=rain_warm_rate_trial(5)
            nracw(i,k)=rain_warm_rate_trial(6)
            naacw(i,k)=rain_warm_rate_trial(7)
            prevp(i,k)=rain_warm_rate_trial(8)
            pseml(i,k)=rain_warm_rate_trial(9)
            pgeml(i,k)=rain_warm_rate_trial(10)
            psevp(i,k)=rain_warm_rate_trial(11)
            pgacs(i,k)=rain_warm_rate_trial(12)
            pgevp(i,k)=rain_warm_rate_trial(13)
            nrcol(i,k)=rain_warm_rate_trial(14)
            nseml(i,k)=rain_warm_rate_trial(15)
            ngeml(i,k)=rain_warm_rate_trial(16)
            qci(i,k,1)=rain_warm_q_after(1)
            qci(i,k,2)=rain_warm_q_after(2)
            qrs(i,k,1)=rain_warm_q_after(3)
            qrs(i,k,2)=rain_warm_q_after(4)
            qrs(i,k,3)=rain_warm_q_after(5)
            nci(i,k,1)=rain_warm_n_after(1)
            nci(i,k,2)=rain_warm_n_after(2)
            nrs(i,k,1)=rain_warm_n_after(3)
            nci(i,k,3)=rain_ccn3_after
            brs(i,k)=rain_warm_bg_after
            t(i,k)=rain_warm_t_after
            q(i,k)=rain_warm_qv_after
            work2(i,k)=-(prevp(i,k)+psevp(i,k)+pgevp(i,k))
            if (progb_status(i,k) == PROGB_PSD_ACTIVE) then
              bgevp(i,k)=pgevp(i,k)/rhox(i,k)
              bgeml(i,k)=pgeml(i,k)/rhox(i,k)
            else
              bgevp(i,k)=0.0
              bgeml(i,k)=0.0
            endif
          endif
        enddo
      enddo

     do k = kts,kte
       do i = its,ite
         qrs_tmp(i,k,1) = qrs(i,k,1)
         qrs_tmp(i,k,2) = qrs(i,k,2)
         qrs_tmp(i,k,3) = qrs(i,k,3)
         qci_tmp(i,k) = qci(i,k,2)
         nci_tmp(i,k) = nci(i,k,2)
         nrs_tmp(i,k) = nrs(i,k,1)
! The next ProgB call initializes density and status.
       enddo
     enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)
   call pr87_report_graupel_consumer(6,pr87_model_timestep,lat, &
        its,ite,kts,kte,qrs_tmp,brs,progb_status)


   call pr77_scan_slope_state(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp,its,ite,kts,kte,lat, &
        'KDM62D_SLOPE_06')
   call validate_kdm6_slope_states(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp)
   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,terminal_velocity_mass,terminal_velocity_number,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax,progb_status)

      do k = kts, kte
        do i = its, ite




          if(qci(i,k,1).le.qmin .or. nci(i,k,1).le.ncmin ) then
            rslopecmu(i,k) = rslopecmmax
            rslopec(i,k) = rslopecmax
            rslopec2(i,k) = rslopec2max
            rslopec3(i,k) = rslopec3max
          else
            rslopec(i,k) = 1./lamdac(qci(i,k,1),dry_carrier_density(i,k),nci(i,k,1))
            rslopec2(i,k) = (rslopec(i,k))*rslopec(i,k)
            rslopec3(i,k) = (rslopec2(i,k))*rslopec(i,k)
            rslopecmu(i,k) = DBLE(rslopec(i,k))**muc
            rslopecd(i,k) = (rslopec(i,k))**dmc
          endif

          avedia(i,k,1) = rslopec(i,k)*(g3pmc)**(1./3.)
          avedia(i,k,2) = rslope(i,k,1)*((g4pmr/g1pmr)**(.3333333))
          avedia(i,k,3) = rslope(i,k,4)*((g4pmi/g1pmi)**(.3333333))




        if (qci(i,k,2).ge. qmin .and.t(i,k).lt.273.15) then
        if (avedia(i,k,3).ge. 200.e-6) then
           pr85_trace_qi = qci(i,k,2)
           pr85_trace_qs = qrs(i,k,2)
           pr85_trace_t_before = t(i,k)
           pr85_trace_ni = nci(i,k,2)
           pr85_trace_diameter = avedia(i,k,3)
           qrs(i,k,2) = qrs(i,k,2) + qci(i,k,2)
           qci(i,k,2) = 0.
           nci(i,k,2) = 0.
           if (pr67_trace_this_call) then
             pr85_trace_removed_qi = dble(pr85_trace_qi)-dble(qci(i,k,2))
             pr85_trace_snow_gain = dble(qrs(i,k,2))-dble(pr85_trace_qs)
             write(pr85_trace_unit,'(a,4i8,1p,13es24.16)',iostat=pr85_trace_ios) &
                  'PR85_ICE_TRANSITION',i,lat,k,loop,dtcld,pr85_trace_t_before,t(i,k), &
                  pr85_trace_diameter,pr85_trace_qi,pr85_trace_qs,pr85_trace_ni, &
                  pr85_trace_qi,pr85_trace_removed_qi,pr85_trace_snow_gain,qci(i,k,2), &
                  qrs(i,k,2),nci(i,k,2)
             if (pr85_trace_ios.ne.0) error stop 'PR85 transition trace write failed'
           endif
        end if
        end if
       enddo
      enddo





      hsub = xls
      hvap = xlv0
      cvap = cpv
      ttp=t0c+0.01
      dldt=cvap-cliq
      xa=-dldt/rv
      xb=xa+hvap/(rv*ttp)
      dldti=cvap-cice
      xai=-dldti/rv
      xbi=xai+hsub/(rv*ttp)
      do k = kts, kte
        do i = its, ite
          tr=ttp/t(i,k)
          qs(i,k,1)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
          qs(i,k,1) = min(qs(i,k,1),0.99*p(i,k))
          qs(i,k,1) = ep2 * qs(i,k,1) / (p(i,k) - qs(i,k,1))
          qs(i,k,1) = max(qs(i,k,1),qmin)
          tr=ttp/t(i,k)
          if(t(i,k).lt.ttp) then
            qs(i,k,2)=psat*exp(log(tr)*(xai))*exp(xbi*(1.-tr))
          else
            qs(i,k,2)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
          endif
          qs(i,k,2) = min(qs(i,k,2),0.99*p(i,k))
          qs(i,k,2) = ep2 * qs(i,k,2) / (p(i,k) - qs(i,k,2))
          qs(i,k,2) = max(qs(i,k,2),qmin)
          rh(i,k,1) = max(q(i,k) / qs(i,k,1),qmin)
          sw(i,k) = (rh(i,k,1)-1.)*100.
        enddo
      enddo

     do k = kts,kte_in
       do i = its,ite
         qrs_tmp(i,k,1) = qrs(i,k,1)
         qrs_tmp(i,k,2) = qrs(i,k,2)
         qrs_tmp(i,k,3) = qrs(i,k,3)
         qci_tmp(i,k) = qci(i,k,2)
         nci_tmp(i,k) = nci(i,k,2)
         nrs_tmp(i,k)   = nrs(i,k,1)
       enddo
     enddo

   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin          &
                   ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2 &
                   ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax      &
                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)
   call pr87_report_graupel_consumer(7,pr87_model_timestep,lat, &
        its,ite,kts,kte,qrs_tmp,brs,progb_status)


   call pr77_scan_slope_state(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp,its,ite,kts,kte,lat, &
        'KDM62D_SLOPE_07')
   call validate_kdm6_slope_states(qci,qrs,nrs,nci,brs, &
        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp)
   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &
                   rslopeb,rslope2,rslope3,rslopemu,rsloped,terminal_velocity_mass,terminal_velocity_number,its, &
                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax,progb_status)

      do k = kts, kte
        do i = its, ite




          avedia(i,k,2) = rslope(i,k,1)*((g4pmr/g1pmr)**(.3333333))




          if(avedia(i,k,2).le.di82) then
            nci(i,k,1) = nci(i,k,1)+nrs(i,k,1)
            nrs(i,k,1) = 0.




            qci(i,k,1) = qci(i,k,1)+qrs(i,k,1)
            qrs(i,k,1) = 0.
          endif
        enddo
      enddo

      do k = kts, kte
        do i = its, ite





           if(sw(i,k).gt.0.) then

            ncact(i,k) = max(0.,((nci(i,k,3)+nci(i,k,1))                       &
                       *min(1.,(sw(i,k)/0.48)**actk) - nci(i,k,1)))/dtcld
            ncact(i,k) =min(ncact(i,k),max(nci(i,k,3),0.)/dtcld)
            pcact(i,k) = min(4.*pi*denr*(actr*1.E-6)**3*ncact(i,k)/            &
                         (3.*dry_carrier_density(i,k)),max(q(i,k),0.)/dtcld)
            pr97_q_before=q(i,k)
            pr97_c_before=qci(i,k,1)
            pr97_extent=pcact(i,k)*dtcld
            q(i,k) = max(q(i,k)-pcact(i,k)*dtcld,0.)
            qci(i,k,1) = max(qci(i,k,1)+pcact(i,k)*dtcld,0.)
            call liquid_record(i,1,pr97_q_before,pr97_c_before,pr97_extent, &
              q(i,k),qci(i,k,1),den(i,k),delz(i,k))
            nci(i,k,3) = max(nci(i,k,3)-ncact(i,k)*dtcld,0.)
            nci(i,k,1) = max(nci(i,k,1)+ncact(i,k)*dtcld,0.)
            t(i,k) = t(i,k)+pcact(i,k)*xl(i,k)/cpm(i,k)*dtcld
          endif  






          tr=ttp/t(i,k)
          qs(i,k,1)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
          qs(i,k,1) = min(qs(i,k,1),0.99*p(i,k))
          qs(i,k,1) = ep2 * qs(i,k,1) / (p(i,k) - qs(i,k,1))
          qs(i,k,1) = max(qs(i,k,1),qmin)
          work1(i,k,1) = conden(t(i,k),q(i,k),qs(i,k,1),xl(i,k),cpm(i,k))
          work2(i,k) = qci(i,k,1)+work1(i,k,1)
          pcond(i,k) = min(max(work1(i,k,1)/dtcld,0.),max(q(i,k),0.)/dtcld)
          if(qci(i,k,1).gt.0. .and. work1(i,k,1).lt.0.)                        & 
            pcond(i,k) = max(work1(i,k,1),-qci(i,k,1))/dtcld




          pr97_q_before=q(i,k)
          pr97_c_before=qci(i,k,1)
          pr97_extent=pcond(i,k)*dtcld
          full_cloud_evap = .false.
          if(pcond(i,k).eq.-qci(i,k,1)/dtcld) then
            cloud_evap_extent = qci(i,k,1)
            nci(i,k,3) = nci(i,k,3)+nci(i,k,1)
            nci(i,k,1) = 0.
            if(cloud_evap_extent.gt.0.) full_cloud_evap = .true.
          endif
          if(full_cloud_evap) then
            q(i,k) = q(i,k)+cloud_evap_extent
            qci(i,k,1) = 0.
            t(i,k) = t(i,k)-cloud_evap_extent*xl(i,k)/cpm(i,k)
          else
            q(i,k) = q(i,k)-pcond(i,k)*dtcld
            qci(i,k,1) = max(qci(i,k,1)+pcond(i,k)*dtcld,0.)
            t(i,k) = t(i,k)+pcond(i,k)*xl(i,k)/cpm(i,k)*dtcld
          endif
          if(full_cloud_evap) pr97_extent=-cloud_evap_extent
          call liquid_record(i,merge(2,3,full_cloud_evap), &
            pr97_q_before,pr97_c_before,pr97_extent, &
            q(i,k),qci(i,k,1),den(i,k),delz(i,k))
        enddo
      enddo



      do k = kts, kte
        do i = its, ite

           pr85_cutoff_q_before=[qci(i,k,1),qci(i,k,2),qrs(i,k,1),qrs(i,k,2),qrs(i,k,3)]
           pr85_cutoff_n_before=[nci(i,k,1),nci(i,k,2),nrs(i,k,1)]
           pr85_cutoff_bg_before=brs(i,k)
           pr85_cutoff_t_before=t(i,k)
           pr85_cutoff_qv_before=q(i,k)
           pr85_cutoff_status_before=progb_status(i,k)
           pr85_cutoff_mask=0
           if(qci(i,k,1).le.qmin) pr85_cutoff_mask=pr85_cutoff_mask+1
           if(qci(i,k,2).le.qmin) pr85_cutoff_mask=pr85_cutoff_mask+2
           if(qrs(i,k,1).le.qcrmin) pr85_cutoff_mask=pr85_cutoff_mask+4
           if(qrs(i,k,2).le.qcrmin) pr85_cutoff_mask=pr85_cutoff_mask+8
           if(qrs(i,k,3).le.qcrmin) pr85_cutoff_mask=pr85_cutoff_mask+16

           if(qci(i,k,1).le.qmin)then
              qci(i,k,1) = 0.0
              nci(i,k,1) = 0.0
           endif
           if(qci(i,k,2).le.qmin)then
              qci(i,k,2) = 0.0
              nci(i,k,2) = 0.0
           endif
           if(qrs(i,k,1).le.qcrmin)then
              qrs(i,k,1) = 0.0
              nrs(i,k,1) = 0.0
           endif
           if(qrs(i,k,2).le.qcrmin)then
              qrs(i,k,2) = 0.0
           endif
           if(qrs(i,k,3).le.qcrmin)then
              qrs(i,k,3) = 0.0
              brs(i,k) = 0.0
              progb_status(i,k) = PROGB_ABSENT
              n0go(i,k) = 0.0
              rhox(i,k) = 0.0
              cmg(i,k) = 0.0
              pidn0g(i,k) = 0.0
              avtg(i,k) = 0.0
              pvtg(i,k) = 0.0
              precg2(i,k) = 0.0
              bvtg(i,k) = 0.0
              bvtg1(i,k) = 0.0
              bvtg2(i,k) = 0.0
              bvtg3(i,k) = 0.0
              bvtg4(i,k) = 0.0
              rslopegbmax(i,k) = 0.0
              g1pbg(i,k) = 0.0
              g3pbg(i,k) = 0.0
              g4pbg(i,k) = 0.0
              g5pbgo2(i,k) = 0.0
              g1pdgbgmg(i,k) = 0.0
              dgbgmug1(i,k) = 0.0
           endif

           pr85_cutoff_q_after=[qci(i,k,1),qci(i,k,2),qrs(i,k,1),qrs(i,k,2),qrs(i,k,3)]
           pr85_cutoff_n_after=[nci(i,k,1),nci(i,k,2),nrs(i,k,1)]
           pr85_cutoff_bg_after=brs(i,k)
           pr85_cutoff_t_after=t(i,k)
           pr85_cutoff_qv_after=q(i,k)
           if (any(pr85_cutoff_q_after.ne.pr85_cutoff_q_before) .or. &
               any(pr85_cutoff_n_after.ne.pr85_cutoff_n_before) .or. &
               pr85_cutoff_bg_after.ne.pr85_cutoff_bg_before) then
             write(pr85_cutoff_unit,'(a,5i8,1p,25es24.16,2i8)',iostat=pr85_cutoff_ios) &
                  'PR85_KDM6_CUTOFF',i,lat,k,loop,pr85_cutoff_mask, &
                  dry_carrier_density(i,k),qmin,qcrmin, &
                  pr85_cutoff_q_before,pr85_cutoff_q_after, &
                  pr85_cutoff_n_before,pr85_cutoff_n_after, &
                  pr85_cutoff_bg_before,pr85_cutoff_bg_after, &
                  pr85_cutoff_t_before,pr85_cutoff_t_after, &
                  pr85_cutoff_qv_before,pr85_cutoff_qv_after, &
                  pr85_cutoff_status_before,progb_status(i,k)
             if (pr85_cutoff_ios.ne.0) error stop 'PR85 cutoff budget write failed'
           endif



          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then
            lamdr_tmp(i,k) = exp(log((((pidnr)*nrs(i,k,1))                       &
                         /(dry_carrier_density(i,k)*qrs(i,k,1))))*(1./dmr))
            if(lamdr_tmp(i,k) .le. lamdarmin) then
              lamdr_tmp(i,k) = lamdarmin
              pr85_psd_before = nrs(i,k,1)
              call pr85_kdm6_psd_bound_number(qrs(i,k,1),dry_carrier_density(i,k),lamdr_tmp(i,k), &
                   lamdarmin,lamdarmax,pidnr,dmr,1, &
                   'rain','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nrs(i,k,1) = pr85_psd_directed
            elseif(lamdr_tmp(i,k) .ge. lamdarmax) then
              lamdr_tmp(i,k) = lamdarmax 
              pr85_psd_before = nrs(i,k,1)
              call pr85_kdm6_psd_bound_number(qrs(i,k,1),dry_carrier_density(i,k),lamdr_tmp(i,k), &
                   lamdarmin,lamdarmax,pidnr,dmr,2, &
                   'rain','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nrs(i,k,1) = pr85_psd_directed
            endif
          endif
          if(qci(i,k,1).ge.qmin .and. nci(i,k,1) .ge. ncmin ) then
            lamdc_tmp(i,k) = exp(log((((pidnc)*nci(i,k,1))                       &
                         /(dry_carrier_density(i,k)*qci(i,k,1))))*(1./dmc))
            if(lamdc_tmp(i,k) .le. lamdacmin) then
              lamdc_tmp(i,k) = lamdacmin
              pr85_psd_before = nci(i,k,1)
              call pr85_kdm6_psd_bound_number(qci(i,k,1),dry_carrier_density(i,k),lamdc_tmp(i,k), &
                   lamdacmin,lamdacmax,pidnc,dmc,1, &
                   'cloud','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,1) = pr85_psd_directed
            elseif(lamdc_tmp(i,k) .ge. lamdacmax) then
              lamdc_tmp(i,k) = lamdacmax
              pr85_psd_before = nci(i,k,1)
              call pr85_kdm6_psd_bound_number(qci(i,k,1),dry_carrier_density(i,k),lamdc_tmp(i,k), &
                   lamdacmin,lamdacmax,pidnc,dmc,2, &
                   'cloud','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available,pr67_trace_this_call, &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,1) = pr85_psd_directed
            endif
          endif
          call pr77_scan_local_state(qrs(i,k,1),nrs(i,k,1), &
               qci(i,k,1),nci(i,k,1),qci(i,k,2),nci(i,k,2), &
               qrs(i,k,3),brs(i,k),i,k,lat,'KDM62D_LOCAL_03')
          call validate_local_species_states(qrs(i,k,1),nrs(i,k,1), &
               qci(i,k,1),nci(i,k,1),qci(i,k,2),nci(i,k,2), &
               qrs(i,k,3),brs(i,k))
          if(qci(i,k,2).ge. qmin .and. nci(i,k,2) .ge. ncmin ) then
            if (.not.all(ieee_is_finite([qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k)])) .or. nci(i,k,2).le.0.0 .or. &
                 dry_carrier_density(i,k).le.0.0) &
              error stop 'PR93 invalid active ice PSD input'
            lamdi_tmp(i,k) = exp(log((((pidni)*nci(i,k,2))                       &
                         /(dry_carrier_density(i,k)*qci(i,k,2))))*(1./dmi))
            pr93_ice_min=DBLE(pidni)/(DBLE(lamdaimax)**DBLE(dmi))
            pr93_ice_max=DBLE(pidni)/(DBLE(lamdaimin)**DBLE(dmi))
            pr93_ice_pair_valid=pr93_kdm6_pair_in_cone(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pr93_ice_min,pr93_ice_max)
            if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX &
                 .and. nci(i,k,2).gt.0.0) pr93_ice_pair_valid=.true.
            call kdm6_ice_ng_pair_contract(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pidni,dmi,lamdaimin,lamdaimax, &
                 pr93_ice_ng_valid,pr93_ice_ng_min,pr93_ice_ng_max)
            if (qci(i,k,2).gt.0.0 .and. &
                qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX .and. nci(i,k,2).gt.0.0) &
              pr93_ice_ng_valid=.true.
            pr93_ice_direct_repair=lamdi_tmp(i,k).gt.lamdaimin .and. &
                 lamdi_tmp(i,k).lt.lamdaimax .and. &
                 (.not.pr93_ice_pair_valid .or. .not.pr93_ice_ng_valid)
            if(lamdi_tmp(i,k) .le. lamdaimin .or. &
                 (qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. &
                  .not.pr93_ice_ng_valid .and. DBLE(nci(i,k,2)).lt.pr93_ice_ng_min)) then
              lamdi_tmp(i,k) = lamdaimin
              pr85_psd_before = nci(i,k,2)
              call pr85_kdm6_psd_bound_number(qci(i,k,2),dry_carrier_density(i,k),lamdi_tmp(i,k), &
                   lamdaimin,lamdaimax,pidni,dmi,1, &
                   'ice','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available, &
                   (pr67_trace_this_call.or.pr93_ice_direct_repair), &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,2) = pr85_psd_directed
            elseif(lamdi_tmp(i,k) .ge. lamdaimax .or. &
                 (qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. &
                  .not.pr93_ice_ng_valid .and. DBLE(nci(i,k,2)).gt.pr93_ice_ng_max)) then
              lamdi_tmp(i,k) = lamdaimax
              pr85_psd_before = nci(i,k,2)
              call pr85_kdm6_psd_bound_number(qci(i,k,2),dry_carrier_density(i,k),lamdi_tmp(i,k), &
                   lamdaimin,lamdaimax,pidni,dmi,2, &
                   'ice','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available, &
                   (pr67_trace_this_call.or.pr93_ice_direct_repair), &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 PSD boundary number invalid'
              nci(i,k,2) = pr85_psd_directed
            endif
            pr93_ice_pair_valid=pr93_kdm6_pair_in_cone(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pr93_ice_min,pr93_ice_max)
            if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX &
                 .and. nci(i,k,2).gt.0.0) pr93_ice_pair_valid=.true.
            call kdm6_ice_ng_pair_contract(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pidni,dmi,lamdaimin,lamdaimax, &
                 pr93_ice_ng_valid,pr93_ice_ng_min,pr93_ice_ng_max)
            if (.not.pr93_ice_pair_valid .or. &
                (qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. .not.pr93_ice_ng_valid)) &
              error stop 'PR93 ice PSD output failed consumer contract'
          endif
            nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)
            if( nrs(i,k,1).gt.nrmax ) then
              lamdr_tmp(i,k) = lamdarmax
              nrs(i,k,1) = dry_carrier_density(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr
            endif
            if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1).ge.nrmin) then
            pr85_psd_exact_min=(DBLE(dry_carrier_density(i,k))*DBLE(lamdarmin)**3) &
                 /DBLE(pidnr)*DBLE(qrs(i,k,1))
            pr85_psd_exact_max=(DBLE(dry_carrier_density(i,k))*DBLE(lamdarmax)**3) &
                 /DBLE(pidnr)*DBLE(qrs(i,k,1))
            if (DBLE(nrs(i,k,1)).lt.pr85_psd_exact_min) then
              lamdr_tmp(i,k)=lamdarmin
              pr85_psd_before=nrs(i,k,1)
              call pr85_kdm6_psd_bound_number(qrs(i,k,1),dry_carrier_density(i,k),lamdarmin, &
                   lamdarmin,lamdarmax,pidnr,dmr,1, &
                   'rain','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available,.true., &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 exact PSD lower number invalid'
              nrs(i,k,1)=pr85_psd_directed
            elseif (DBLE(nrs(i,k,1)).gt.pr85_psd_exact_max) then
              lamdr_tmp(i,k)=lamdarmax
              pr85_psd_before=nrs(i,k,1)
              call pr85_kdm6_psd_bound_number(qrs(i,k,1),dry_carrier_density(i,k),lamdarmax, &
                   lamdarmin,lamdarmax,pidnr,dmr,2, &
                   'rain','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available,.true., &
                   pr85_psd_unit,pr85_psd_legacy,pr85_psd_directed, &
                   pr85_psd_exact_min,pr85_psd_exact_max,pr85_psd_valid)
              if (.not.pr85_psd_valid) error stop 'KDM6 exact PSD upper number invalid'
              nrs(i,k,1)=pr85_psd_directed
            endif
            endif
            if( nci(i,k,1).gt.ncmax ) then
              lamdc_tmp(i,k) = lamdacmax
              nci(i,k,1) = dry_carrier_density(i,k)*qci(i,k,1)*lamdc_tmp(i,k)**dmc/pidnc
            endif
            call kdm6_refresh_graupel_intercept(progb_status(i,k),n0g,g1pmg, &
                 rslopemu(i,k,3),n0go(i,k),graupel_cache_valid)
            if (.not.graupel_cache_valid) error stop 'KDM6 final graupel intercept cache invalid'
        enddo
      enddo 
      if (pr67_trace_this_call) then
        close(pr85_trace_unit,iostat=pr85_trace_ios)
        if (pr85_trace_ios.ne.0) error stop 'PR85 transition trace close failed'
      endif
   enddo
   write(pr89_cold_unit,'(a,6i10,1p,*(1x,e24.16))',iostat=pr89_cold_ios) &
        'PR89_KDM6_COLD_SUMMARY',pr87_model_timestep,lat,loops, &
        pr89_cold_transactions,0,pr89_cold_transactions,pr89_cold_water
   if (pr89_cold_ios.ne.0) error stop 'PR89 cold summary write failed'
   close(pr89_cold_unit,iostat=pr89_cold_ios)
   open(newunit=pr90_cold_unit,file='pr90_kdm6_cold_column.raw', &
        form='formatted',status='unknown',position='append',action='write', &
        iostat=pr90_cold_ios)
   if (pr90_cold_ios.ne.0) error stop 'PR90 cold column open failed'
   write(pr90_cold_unit,'(a)',iostat=pr90_cold_ios) &
        '# PR90_KDM6_COLD_COLUMN v1 step,lat,i,loops,cell_transactions; '// &
        'group-major NG,AUT,G; stage-major proposed,applied,deferred; '// &
        'each stage signed,half-L1; units kg m-2 per column (vertical sum); '// &
        'weight=DEN*DELZ; diagnostic request activity, not reaction throughput'
   if (pr90_cold_ios.ne.0) error stop 'PR90 cold column header failed'
   write(pr90_cold_unit,'(a,4i10)',iostat=pr90_cold_ios) &
        'PR90_KDM6_COLD_BLOCK',pr87_model_timestep,lat,its,ite
   if (pr90_cold_ios.ne.0) error stop 'PR90 cold column block failed'
   do pr90_cold_i=its,ite
     write(pr90_cold_unit,'(a,5i10,1p,*(1x,e24.16))',iostat=pr90_cold_ios) &
          'PR90_KDM6_COLD_COLUMN',pr87_model_timestep,lat,pr90_cold_i,loops, &
          pr90_cold_transactions(pr90_cold_i),pr90_cold_water(:,:,:,pr90_cold_i)
     if (pr90_cold_ios.ne.0) error stop 'PR90 cold column write failed'
   enddo
   close(pr90_cold_unit,iostat=pr90_cold_ios)
   if (pr90_cold_ios.ne.0) error stop 'PR90 cold column close failed'
   if (pr89_cold_ios.ne.0) error stop 'PR89 cold summary close failed'
     close(pr85_psd_unit,iostat=pr85_psd_ios)
     if (pr85_psd_ios.ne.0) error stop 'PR85 PSD boundary ledger close failed'
   close(pr85_cold_unit,iostat=pr85_cold_ios)
   if (pr85_cold_ios.ne.0) error stop 'PR85 cold budget close failed'
   if (pr67_trace_this_call) then
     close(pr87_reason_unit,iostat=pr87_reason_ios)
     if (pr87_reason_ios.ne.0) error stop 'PR87 admission reason close failed'
   endif
   close(pr85_warm_unit,iostat=pr85_warm_ios)
   if (pr85_warm_ios.ne.0) error stop 'PR85 warm budget close failed'
   close(pr85_cutoff_unit,iostat=pr85_cutoff_ios)
   if (pr85_cutoff_ios.ne.0) error stop 'PR85 cutoff budget close failed'

   call liquid_end(lat,its,ite)
   end subroutine kdm62d

        REAL FUNCTION GAMMLN(x)


      IMPLICIT NONE
      REAL :: x
      DOUBLE PRECISION, PARAMETER:: STP = 2.5066282746310005D0
      DOUBLE PRECISION, DIMENSION(6), PARAMETER:: &
               COF = (/76.18009172947146D0, -86.50532032941677D0, &
                       24.01409824083091D0, -1.231739572450155D0, &
                      .1208650973866179D-2, -.5395239384953D-5/)
      DOUBLE PRECISION:: SER,TMP,XX,Y
      INTEGER:: J

      XX=x
      Y=XX
      TMP=XX+5.5D0
      TMP=(XX+0.5D0)*LOG(TMP)-TMP
      SER=1.000000000190015D0
      DO 11 J=1,6
        Y=Y+1.D0
        SER=SER+COF(J)/Y
11    CONTINUE
      GAMMLN=TMP+LOG(STP*SER/XX)
      END FUNCTION GAMMLN


      REAL function rgmma(x)
      IMPLICIT NONE
      REAL :: x

      rgmma = EXP(GAMMLN(x))

      END FUNCTION rgmma

   real function fpvs(t,ice,rd,rv,cvap,cliq,cice,hvap,hsub,psat,t0c)

   implicit none

      REAL t,rd,rv,cvap,cliq,cice,hvap,hsub,psat,t0c,dldt,xa,xb,dldti,         &
           xai,xbi,ttp,tr
      INTEGER ice

      ttp=t0c+0.01
      dldt=cvap-cliq
      xa=-dldt/rv
      xb=xa+hvap/(rv*ttp)
      dldti=cvap-cice
      xai=-dldti/rv
      xbi=xai+hsub/(rv*ttp)
      tr=ttp/t
      if(t.lt.ttp .and. ice.eq.1) then
        fpvs=psat*(tr**xai)*exp(xbi*(1.-tr))
      else
        fpvs=psat*(tr**xa)*exp(xb*(1.-tr))
      endif

      END FUNCTION fpvs

  SUBROUTINE kdm6init(den0,denr,dens,cl,cpv, ccn0, hail_opt, allowed_to_read) 

  IMPLICIT NONE


   REAL, INTENT(IN) :: den0,denr,dens,cl,cpv,ccn0
   INTEGER, INTENT(IN) :: hail_opt  
   LOGICAL, INTENT(IN) :: allowed_to_read
 


      IF (hail_opt .eq. 1) THEN 
         n0g       = 4.e4
         deng      = 700.
         lamdagmax = 2.e4
      ELSE 
         n0g       = 4.e6
         deng      = 500
         lamdagmax = 1.8e5 
        
      ENDIF

   pi = 4.*atan(1.)
   xlv1 = cl-cpv

   qc0  = 4./3.*pi*denr*r0**3.*xncr0/den0
   qc1  = 4./3.*pi*denr*r0**3.*xncr1/den0
   qck1 = .104*9.8*peaut/(denr)**(1./3.)/xmyu*den0**(4./3.) 

   bvtr1 = 1.+bvtr
   bvtr2 = 2.+bvtr
   bvtr3 = 3.+bvtr
   bvtr4 = 4.+bvtr
   bvtr5 = 5.+bvtr
   bvtr6 = 6.+bvtr
   bvtr7 = 7.+bvtr
   bvtr2o5 = 2.5+.5*bvtr
   bvtr3o5 = 2.5+.5*bvtr+mur
   drmur1 = 1.+dmr + mur
   drmur2 = 2.+dmr + mur
   drmur3 = 3.+dmr + mur
   drbrmur1 = 1.+dmr + bvtr + mur
   drbrmur3 = 3.+dmr + bvtr + mur
   brmur1 = 1.+ bvtr + mur

   cmc = pi*denr/6.
   cmr = pi*denr/6.
   cms = pi*dens/6.
   cmi = pi*deni/6.
   muc1 = 1+1/(muc+1)
   muc3 = 1+3/(muc+1)
   muc4 = 1+4/(muc+1)
   muc6 = 1+6/(muc+1)
   muc9 = 1+9/(muc+1)
   g1p2dcomuc1=rgmma(1.+2*dmc/(muc+1.))
   g1pdcomuc1=rgmma(1.+dmc/(muc+1.))
   mur7 = 7.+ mur
   mur4 = 4.+ mur
   mur3 = 3.+ mur
   mur2 = 2.+ mur
   mur1 = 1.+ mur
   g1pmc = rgmma(muc1)
   g3pmc = rgmma(muc3)
   g4pmc = rgmma(muc4)
   g6pmc = rgmma(muc6)
   g9pmc = rgmma(muc9)
   g7pmr = rgmma(mur7)
   g4pmr = rgmma(mur4)
   g3pmr = rgmma(mur3)
   g2pmr = rgmma(mur2)
   g1pmr = rgmma(mur1)
   mus3 = 3.+ mus
   mus2 = 2.+ mus
   mus1 = 1.+ mus
   g3pms = rgmma(mus3)
   g2pms = rgmma(mus2)
   if (mus .eq. 0) then
      g1pms = 1. 
   else
      g1pms = rgmma(mus1)
   endif
   mug3 = 3.+ mug
   mug2 = 2.+ mug
   mug1 = 1.+ mug
   dsbsmus1 = 1.+dms + bvts + mus
   g3pmg = rgmma(mug3)
   g2pmg = rgmma(mug2)
   if (mug .eq. 0) then
      g1pmg = 1.
   else
      g1pmg = rgmma(mug1)
   endif


   pidnc = cmc*rgmma(1.+dmc/(muc+1.))
   g1pdrmr = rgmma(drmur1)
   g2pdrmr = rgmma(drmur2)
   g3pdrmr = rgmma(drmur3)
   g3pbrmr = rgmma(bvtr3+mur)
   g3pdrbrmr=rgmma(drbrmur3)
   g1pdrbrmr=rgmma(drbrmur1)
   g1pbrmr=rgmma(brmur1)

   g1pbr = rgmma(bvtr1)
   g2pbr = rgmma(bvtr2)
   g3pbr = rgmma(bvtr3)
   g4pbr = rgmma(bvtr4)            
   g5pbr = rgmma(bvtr5)
   g6pbr = rgmma(bvtr6)
   g7pbr = rgmma(bvtr7)
   g5pbro2 = rgmma(bvtr2o5) 
   g7pbro2 = rgmma(bvtr3o5)
   g1p2drmr = rgmma(drmur1+dmr)

   pvtr = avtr*g1pdrbrmr/g1pdrmr

   pvtrn = avtr*g1pbrmr/g1pmr
   eacrr = 1.0


   precr1 = 2.*pi*0.78*g2pmr
   precr2 = 2.*pi*.31*avtr**.5*g7pbro2


   pidnr =  cmr*g1pdrmr/g1pmr


   xmmax = (dimax/dicon)**2
   roqimax = 2.08e22*dimax**8

   mui1 = 1. + mui
   mui2 = 2. + mui
   mui3 = 3. + mui
   mui4 = 4. + mui
   mui5 = 5. + mui
   g1pmi = rgmma(mui1)
   g2pmi = rgmma(mui2)
   g3pmi = rgmma(mui3)
   g4pmi = rgmma(mui4)
   g5pmi = rgmma(mui5)
   dibimui1 = 1.+dmi + bvti + mui       
   bimui1 = 1.+ bvti + mui      
   dimui1 = 1.+dmi + mui
   dimui2 = 2.+dmi + mui
   dimui3 = 3.+dmi + mui
   g1pbimi =rgmma(bimui1)
   g1pdibimi=rgmma(dibimui1)
   g1pdimi = rgmma(dimui1)
   g2pdimi = rgmma(dimui2)
   g3pdimi = rgmma(dimui3)
   pvti = avti*g1pdibimi/g1pdimi
   pvtin = avti*g1pbimi/g1pmi
   pidni = cmi*g1pdimi/g1pmi

   dsmus1 = 1.+dms + mus
   dsmus2 = 2.+dms + mus
   dsmus3 = 3.+dms + mus
   g1pdsms = rgmma(dsmus1)
   g2pdsms = rgmma(dsmus2)
   g3pdsms = rgmma(dsmus3)
   g1pdsbsms=rgmma(dsbsmus1)
   bvts1 = 1.+bvts
   bvts2 = 2.5+.5*bvts+mus
   bvti3 = 3.+bvti+mui
   g3pbi = rgmma(bvti3)
   bvts3 = 3.+bvts+mus
   bvts4 = 4.+bvts
   g1pbs = rgmma(bvts1)    
   g3pbs = rgmma(bvts3)
   g4pbs = rgmma(bvts4)    
   g5pbso2 = rgmma(bvts2)

   pvts = avts*g1pdsbsms/g1pdsms


   precs1 = 4.*.65*g2pms
   precs2 = 4.*.44*avts**.5*g5pbso2

   pidn0s =  cms*n0s*g1pdsms/g1pms



   dgmug1 = 1.+dmg + mug
   g1pdgmg = rgmma(dgmug1)
   precg1 = 4.*.78*g2pmg

   rslopecmax = 1./lamdacmax
   rslopermax = 1./lamdarmax
   rslopesmax = 1./lamdasmax
   rslopegmax = 1./lamdagmax
   rslopeimax = 1./lamdaimax
   rslopecmmax = DBLE(rslopecmax) ** muc
   rslopermmax = DBLE(rslopermax) ** mur
   if (mus .ne. 0) then
   rslopesmmax = DBLE(rslopesmax) ** mus
   else
   rslopesmmax = 1.
   endif
   if (mug .ne. 0) then
   rslopegmmax = DBLE(rslopegmax) ** mug
   else
   rslopegmmax = 1. 
   endif
   if (mui .ne. 0) then
   rslopeimmax = DBLE(rslopeimax) ** mui
   else
   rslopeimmax = 1.
   endif





   rsloperbmax = rslopermax ** bvtr
   rslopesbmax = rslopesmax ** bvts
   rsloperdmax = (rslopermax) ** dmr
   rslopesdmax = (rslopesmax) ** dms
   rslopegdmax = (rslopegmax) ** dmg
   rslopec2max = (rslopecmax) * rslopecmax
   rslopecdmax = (rslopecmax) ** dmc
   rsloper2max = (rslopermax) * rslopermax
   rslopes2max = (rslopesmax) * rslopesmax
   rslopeg2max = (rslopegmax) * rslopegmax
   rslopec3max = (rslopec2max) * rslopecmax
   rsloper3max = (rsloper2max) * rslopermax
   rslopes3max = (rslopes2max) * rslopesmax
   rslopeg3max = (rslopeg2max) * rslopegmax
   rslopeibmax = rslopeimax ** bvti
   rslopeidmax = (rslopeimax) ** dmi
   rslopei2max = (rslopeimax) * rslopeimax
   rslopei3max = (rslopei2max) * rslopeimax




   xam_c = cmc
   xbm_c = dmc
   xmu_c = muc
   xam_r = cmr 
   xbm_r = dmr 
   xmu_r = mur 
   xam_s = cms 
   xbm_s = dms 
   xmu_s = mus 
   xbm_g = dmg 
   xmu_g = mug 
   xam_i = cmi
   xbm_i = dmi
   xmu_i = mui
   call radar_init_variable_graupel


  END SUBROUTINE kdm6init

   SUBROUTINE ProgB_param(brs,qrs,rhox,its,ite,jts,jte,kts,kte,qcrmin             &
                         ,dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2&
                         ,bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax     &
                         ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)
  use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
  implicit none
  integer           :: i,k,sy, its,ite, jts,jte, kts,kte
  real, intent(in)  ::qcrmin,dmg,mug,pi
  real, intent(in)  ::g1pdgmg,g1pmg,n0g
  real, intent(in)  ::rslopegmax
  REAL, DIMENSION( its:ite , kts:kte,3), INTENT(IN) :: qrs
  REAL, DIMENSION( its:ite , kts:kte), INTENT(INOUT):: brs   
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: rhox    
  INTEGER, DIMENSION( its:ite , kts:kte),INTENT(OUT) :: progb_status
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: cmg,pidn0g
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: avtg,pvtg,precg2
  REAL, DIMENSION( its:ite , kts:kte),INTENT(OUT)   :: bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,&
                                                       g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1
  REAL ::tmp1,tmp2
  DOUBLE PRECISION :: raw_density
  real,dimension(9) :: Tbl,aTbl,bTbl
  real, parameter   :: rho_min = 100.      
  real, parameter   :: rho_max = 900.      
  real, parameter   :: rho_mid = 400.      

 
  data Tbl /    100.,   200.,   300.,   400.,   500.,   600.,   700., 800., 900./   
  data aTbl   /  54.9153,   74.2262,   88.8313,  101.0411, 111.7359,  121.3625, 130.1841,  138.3714, 146.0422 / 
  data bTbl   / 0.5446,    0.5375,    0.5339,    0.5316, 0.5299,    0.5286, 0.5275,    0.5266, 0.5258 / 
 

      do k = kts, kte
        do i = its, ite
          rhox(i,k) = 0.0
          cmg(i,k) = 0.0
          pidn0g(i,k) = 0.0
          avtg(i,k) = 0.0
          pvtg(i,k) = 0.0
          precg2(i,k) = 0.0
          bvtg(i,k) = 0.0
          bvtg1(i,k) = 0.0
          bvtg2(i,k) = 0.0
          bvtg3(i,k) = 0.0
          bvtg4(i,k) = 0.0
          rslopegbmax(i,k) = 0.0
          g1pbg(i,k) = 0.0
          g3pbg(i,k) = 0.0
          g4pbg(i,k) = 0.0
          g5pbgo2(i,k) = 0.0
          g1pdgbgmg(i,k) = 0.0
          dgbgmug1(i,k) = 0.0
          progb_status(i,k) = PROGB_UNSUPPORTED
          if (.not. ieee_is_finite(qrs(i,k,3)) .or. &
              .not. ieee_is_finite(brs(i,k))) cycle
          if (qrs(i,k,3) == 0.0 .and. brs(i,k) == 0.0) then
            progb_status(i,k) = PROGB_ABSENT
            cycle
          endif
          if (.not.kdm6_progb_density_pair_valid(qrs(i,k,3),brs(i,k), &
              rho_min,rho_max)) cycle
          raw_density = dble(qrs(i,k,3))/dble(brs(i,k))
          rhox(i,k) = qrs(i,k,3)/brs(i,k)
          cmg(i,k) = pi*rhox(i,k)/6
          if (.not. ieee_is_finite(cmg(i,k)) .or. cmg(i,k) <= 0.0) cycle
          pidn0g(i,k) = cmg(i,k)*n0g*g1pdgmg/g1pmg
         if (cmg(i,k).gt. 0) then
          if (rhox(i,k).ge. Tbl(1) .and. rhox(i,k).lt.Tbl(9)) then
                  do sy = 1,8
                   if (Tbl(sy).le. rhox(i,k) .and. Tbl(sy+1).gt.rhox(i,k)) then
                   tmp2 = 1./(Tbl(sy+1)-Tbl(sy))
                   avtg(i,k)=aTbl(sy)+(rhox(i,k)-Tbl(sy))*(aTbl(sy+1)-aTbl(sy))*tmp2
                   bvtg(i,k)=bTbl(sy)+(rhox(i,k)-Tbl(sy))*(bTbl(sy+1)-bTbl(sy))*tmp2
                   bvtg1(i,k) = 1.+bvtg(i,k)
                   bvtg2(i,k) = 2.5+.5*bvtg(i,k)+mug
                   bvtg3(i,k) = 3.+bvtg(i,k)+mug
                   bvtg4(i,k) = 4.+bvtg(i,k)
                   dgbgmug1(i,k) = 1.+dmg + bvtg(i,k) + mug
                   g1pbg(i,k) = rgmma(bvtg1(i,k))
                   g3pbg(i,k) = rgmma(bvtg3(i,k))
                   g4pbg(i,k) = rgmma(bvtg4(i,k))
                   g5pbgo2(i,k) = rgmma(bvtg2(i,k))
                   g1pdgbgmg(i,k)=rgmma(dgbgmug1(i,k))
                   rslopegbmax(i,k) = rslopegmax ** bvtg(i,k)
                   pvtg(i,k) = avtg(i,k)*g1pdgbgmg(i,k)/g1pdgmg
                   precg2(i,k) = 4.*.31*avtg(i,k)**.5*g5pbgo2(i,k)
                   exit
                   endif
                  enddo
         else if (rhox(i,k).eq. Tbl(9)) then
                   avtg(i,k)=aTbl(9)
                   bvtg(i,k)=bTbl(9)
                   bvtg1(i,k) = 1.+bvtg(i,k)
                   bvtg2(i,k) = 2.5+.5*bvtg(i,k)+mug
                   bvtg3(i,k) = 3.+bvtg(i,k)+mug
                   bvtg4(i,k) = 4.+bvtg(i,k)
                   dgbgmug1(i,k) = 1.+dmg + bvtg(i,k) + mug
                   g1pbg(i,k) = rgmma(bvtg1(i,k))
                   g3pbg(i,k) = rgmma(bvtg3(i,k))
                   g4pbg(i,k) = rgmma(bvtg4(i,k))
                   g5pbgo2(i,k) = rgmma(bvtg2(i,k))
                   g1pdgbgmg(i,k)=rgmma(dgbgmug1(i,k))
                   rslopegbmax(i,k) = rslopegmax ** bvtg(i,k)
                   pvtg(i,k) = avtg(i,k)*g1pdgbgmg(i,k)/g1pdgmg
                   precg2(i,k) = 4.*.31*avtg(i,k)**.5*g5pbgo2(i,k)
         endif
       endif
          if (.not. ieee_is_finite(rhox(i,k)) .or. &
              .not. ieee_is_finite(cmg(i,k)) .or. &
              .not. ieee_is_finite(pidn0g(i,k)) .or. &
              .not. ieee_is_finite(avtg(i,k)) .or. &
              .not. ieee_is_finite(pvtg(i,k)) .or. &
              .not. ieee_is_finite(precg2(i,k)) .or. &
              .not. ieee_is_finite(bvtg(i,k)) .or. &
              .not. ieee_is_finite(bvtg1(i,k)) .or. &
              .not. ieee_is_finite(bvtg2(i,k)) .or. &
              .not. ieee_is_finite(bvtg3(i,k)) .or. &
              .not. ieee_is_finite(bvtg4(i,k)) .or. &
              .not. ieee_is_finite(rslopegbmax(i,k)) .or. &
              .not. ieee_is_finite(g1pbg(i,k)) .or. &
              .not. ieee_is_finite(g3pbg(i,k)) .or. &
              .not. ieee_is_finite(g4pbg(i,k)) .or. &
              .not. ieee_is_finite(g5pbgo2(i,k)) .or. &
              .not. ieee_is_finite(g1pdgbgmg(i,k)) .or. &
              .not. ieee_is_finite(dgbgmug1(i,k))) then
            rhox(i,k) = 0.0
            cmg(i,k) = 0.0
            pidn0g(i,k) = 0.0
            avtg(i,k) = 0.0
            pvtg(i,k) = 0.0
            precg2(i,k) = 0.0
            bvtg(i,k) = 0.0
            bvtg1(i,k) = 0.0
            bvtg2(i,k) = 0.0
            bvtg3(i,k) = 0.0
            bvtg4(i,k) = 0.0
            rslopegbmax(i,k) = 0.0
            g1pbg(i,k) = 0.0
            g3pbg(i,k) = 0.0
            g4pbg(i,k) = 0.0
            g5pbgo2(i,k) = 0.0
            g1pdgbgmg(i,k) = 0.0
            dgbgmug1(i,k) = 0.0
            cycle
          endif
          progb_status(i,k) = PROGB_PSD_ACTIVE
        enddo
      enddo
  END subroutine ProgB_param

      subroutine slope_kdm6(qrs,qci,nrs,nci,den,denfac,t,rslope,rslopeb,rslope2,rslope3, &
                            rslopemu,rsloped,vt,vtn,its,ite,kts,kte,qmin,pidn0g,         &
                            pvtg,bvtg,rslopegbmax,progb_status)
  IMPLICIT NONE
  INTEGER       ::               its,ite, jts,jte, kts,kte
  INTEGER, DIMENSION(its:ite,kts:kte), INTENT(IN) :: progb_status


  REAL, DIMENSION( its:ite , kts:kte,3) ::   qrs                                 
  REAL, DIMENSION( its:ite , kts:kte) ::   qci
  REAL, DIMENSION( its:ite , kts:kte) :: nci,nrs
  REAL, DIMENSION( its:ite , kts:kte,4) ::                            rslope,  &
                                                                      rslopeb, &
                                                                      rsloped, &
                                                                      rslope2, &
                                                                      rslope3

 
  DOUBLE PRECISION, DIMENSION( its:ite , kts:kte,4) ::            vt,rslopemu
  DOUBLE PRECISION, DIMENSION( its:ite , kts:kte,2) ::                   vtn
  REAL, DIMENSION( its:ite , kts:kte) ::                                       &  
                                                                          den, &
                                                                       denfac, &
                                                                       t,n0sfac

  REAL, INTENT(IN) :: qmin
  REAL, PARAMETER  :: t0c = 273.15
  REAL       ::  lamdas, lamdag, x, y, z, supcol
  REAL       ::  lamdar,lamdai
  integer :: i, j, k
  REAL, DIMENSION(its:ite,kts:kte), intent(in)::pidn0g
  REAL, DIMENSION(its:ite,kts:kte), intent(in)::pvtg
  REAL, DIMENSION(its:ite,kts:kte), intent(in)::bvtg,rslopegbmax








      lamdar(x,y,z)= exp(log(((pidnr*z)/(x*y)))*(1./dmr)) 

      lamdas(x,y,z)= exp(log(((pidn0s*z)/(x*y)))*(1./(dms+1)))

      lamdag(x,y)= exp(log(((pidn0g(i,k))/(x*y)))*(1./(dmg+1)))

      lamdai(x,y,z)= exp(log(((pidni*z)/(x*y)))*(1./dmi))

      do k = kts, kte
        do i = its, ite
          if (progb_status(i,k) == PROGB_TRANSIENT) &
            error stop 'ProgB transient PSD state rejected'
          if (progb_status(i,k) == PROGB_UNSUPPORTED) &
            error stop 'ProgB unsupported PSD state rejected'
          if (progb_status(i,k) /= PROGB_ABSENT .and. &
              progb_status(i,k) /= PROGB_PSD_ACTIVE) &
            error stop 'ProgB invalid output status'
          supcol = t0c-t(i,k)



          n0sfac(i,k) = max(min(exp(alpha*supcol),n0smax/n0s),1.)
          if(qrs(i,k,1).le.qcrmin .or. nrs(i,k).le.nrmin ) then
            rslope(i,k,1) = rslopermax
            rslopeb(i,k,1) = rsloperbmax
            rslopemu(i,k,1) = rslopermmax
            rsloped(i,k,1) = rsloperdmax
            rslope2(i,k,1) = rsloper2max
            rslope3(i,k,1) = rsloper3max
          else
            rslope(i,k,1) = min(1./lamdar(qrs(i,k,1),den(i,k),nrs(i,k)),1.e-3)
            rslopeb(i,k,1) = (rslope(i,k,1))**bvtr
            rslopemu(i,k,1) = DBLE(rslope(i,k,1))**mur
            rsloped(i,k,1) = (rslope(i,k,1))**dmr
            rslope2(i,k,1) = (rslope(i,k,1))*rslope(i,k,1)
            rslope3(i,k,1) = (rslope2(i,k,1))*rslope(i,k,1)
          endif
          if(qrs(i,k,2).le.qcrmin) then
            rslope(i,k,2) = rslopesmax
            rslopeb(i,k,2) = rslopesbmax
            rslopemu(i,k,2) = rslopesmmax
            rsloped(i,k,2) = rslopesdmax
            rslope2(i,k,2) = rslopes2max
            rslope3(i,k,2) = rslopes3max
          else
            rslope(i,k,2) = 1./lamdas(qrs(i,k,2),den(i,k),n0sfac(i,k))
            rslopeb(i,k,2) = (rslope(i,k,2))**bvts
            rslopemu(i,k,2) = DBLE(rslope(i,k,2))**mus
            rsloped(i,k,2) = (rslope(i,k,2))**dms
            rslope2(i,k,2) = (rslope(i,k,2))*rslope(i,k,2)
            rslope3(i,k,2) = (rslope2(i,k,2))*rslope(i,k,2)
          endif
          if (progb_status(i,k) == PROGB_ABSENT) then
            rslope(i,k,3) = 0.0
            rslopeb(i,k,3) = 0.0
            rslopemu(i,k,3) = 0.0
            rsloped(i,k,3) = 0.0
            rslope2(i,k,3) = 0.0
            rslope3(i,k,3) = 0.0
          else
            if(qrs(i,k,3).le.qcrmin) then
            rslope(i,k,3) = rslopegmax
            rslopeb(i,k,3) = rslopegbmax(i,k)
            rslopemu(i,k,3) = rslopegmmax
            rsloped(i,k,3) = rslopegdmax
            rslope2(i,k,3) = rslopeg2max
            rslope3(i,k,3) = rslopeg3max
          else
            rslope(i,k,3) = 1./lamdag(qrs(i,k,3),den(i,k))
            rslopeb(i,k,3) = (rslope(i,k,3))**bvtg(i,k)
            rslopemu(i,k,3) = DBLE(rslope(i,k,3))**mug
            rsloped(i,k,3) = (rslope(i,k,3))**dmg
            rslope2(i,k,3) = (rslope(i,k,3))*rslope(i,k,3)
            rslope3(i,k,3) = (rslope2(i,k,3))*rslope(i,k,3)
          endif
          endif
          if(qci(i,k) .le. qmin) then  
            rslope(i,k,4) = rslopeimax
            rslopeb(i,k,4) = rslopeibmax
            rslopemu(i,k,4) = rslopeimmax
            rsloped(i,k,4) = rslopeidmax
            rslope2(i,k,4) = rslopei2max
            rslope3(i,k,4) = rslopei3max
          else
           rslope(i,k,4) =max(min(1./lamdai(qci(i,k),den(i,k),nci(i,k)),1./lamdaimin), &
                          1./lamdaimax)
            rslopeb(i,k,4) = (rslope(i,k,4))**bvti
            rslopemu(i,k,4) = DBLE(rslope(i,k,4))**mui
            rsloped(i,k,4) = (rslope(i,k,4))**dmi
            rslope2(i,k,4) = (rslope(i,k,4))*rslope(i,k,4)
            rslope3(i,k,4) = (rslope2(i,k,4))*rslope(i,k,4)
            endif
          vt(i,k,1) = DBLE(pvtr)*rslopeb(i,k,1)*denfac(i,k)
          vt(i,k,2) = DBLE(pvts)*rslopeb(i,k,2)*denfac(i,k)
          if (progb_status(i,k) == PROGB_PSD_ACTIVE) then
            vt(i,k,3) = DBLE(pvtg(i,k))*rslopeb(i,k,3)*denfac(i,k)
          else
            vt(i,k,3) = 0.0
          endif
          vt(i,k,4) = DBLE(pvti)*rslopeb(i,k,4)*denfac(i,k)
          vtn(i,k,1) = DBLE(pvtrn)*rslopeb(i,k,1)*denfac(i,k)
          vtn(i,k,2) = DBLE(pvtin)*rslopeb(i,k,4)*denfac(i,k) 
          if(qrs(i,k,1).le.0.0) vt(i,k,1) = 0.0 
          if(qrs(i,k,2).le.0.0) vt(i,k,2) = 0.0
          if(qrs(i,k,3).le.0.0) vt(i,k,3) = 0.0
          if(qci(i,k).le.0.0) vt(i,k,4) = 0.0
          if(nrs(i,k).le.0.0) vtn(i,k,1) = 0.0 
          if(nci(i,k).le.0.0) vtn(i,k,2) = 0.0 
        enddo
      enddo
  END subroutine slope_kdm6

      subroutine kdm6_velocity_rates(vt,vtn,delz,mass_rate,number_rate, &
                                     ims,ime,kms,kme,its,ite,kts,kte)
        implicit none
        integer, intent(in) :: ims,ime,kms,kme,its,ite,kts,kte
        double precision, intent(in) :: vt(its:ite,kts:kte,4)
        double precision, intent(in) :: vtn(its:ite,kts:kte,2)
        real, intent(in) :: delz(ims:ime,kms:kme)
        double precision, intent(out) :: mass_rate(its:ite,kts:kte,4)
        double precision, intent(out) :: number_rate(its:ite,kts:kte,2)
        integer :: i,k

        do k = kts, kte
          do i = its, ite
            mass_rate(i,k,:) = vt(i,k,:)/delz(i,k)
            number_rate(i,k,:) = vtn(i,k,:)/delz(i,k)
          enddo
        enddo
      end subroutine kdm6_velocity_rates

      subroutine slope_rain(qrs,nrs,den,denfac,t,rslope,rslopeb,rslope2,rslope3,   &
                            rsloped,rslopemu,vt,vtn,its,ite,kts,kte)
  IMPLICIT NONE
  INTEGER       ::               its,ite, jts,jte, kts,kte
  REAL, DIMENSION( its:ite , kts:kte) ::                                  qrs, &
                                                                          den, &
                                                                       denfac, &
                                                                            t
  DOUBLE PRECISION, DIMENSION( its:ite , kts:kte) ::          vt,vtn,rslopemu
  REAL, DIMENSION( its:ite , kts:kte) ::                                  nrs, &
                                                                       rslope, &
                                                                      rslopeb, &
                                                                      rsloped, &
                                                                      rslope2, &
                                                                      rslope3
  REAL, PARAMETER  :: t0c = 273.15
  REAL, DIMENSION( its:ite , kts:kte ) ::                                      &
                                                                       n0sfac
  REAL       ::  x, y, z, supcol
  REAL       ::  lamdar, xd, yd, zd
  integer :: i, j, k




      lamdar(xd,yd,zd)= exp(log(((pidnr*zd)/(xd*yd)))*(1./dmr))

      do k = kts, kte
        do i = its, ite
          if(qrs(i,k).le.qcrmin .or. nrs(i,k).le.nrmin) then
            rslope(i,k) = rslopermax
            rslopeb(i,k) = rsloperbmax
            rslopemu(i,k) = rslopermmax
            rslope2(i,k) = rsloper2max
            rslope3(i,k) = rsloper3max
          else
            rslope(i,k) = min(1./lamdar(qrs(i,k),den(i,k),nrs(i,k)),1.e-3)
            rslopeb(i,k) = (rslope(i,k))**bvtr
            rslopemu(i,k) = DBLE(rslope(i,k))**mur
            rsloped(i,k) = (rslope(i,k))**dmr
            rslope2(i,k) = (rslope(i,k))*rslope(i,k)
            rslope3(i,k) = (rslope2(i,k))*rslope(i,k)
          endif
          vt(i,k) = DBLE(pvtr)*rslopeb(i,k)*denfac(i,k)
          vtn(i,k) = DBLE(pvtrn)*rslopeb(i,k)*denfac(i,k)
          if(qrs(i,k).le.0.0) vt(i,k) = 0.0
          if(nrs(i,k).le.0.0) vtn(i,k) = 0.0 
        enddo
      enddo
  END subroutine slope_rain

      SUBROUTINE nislfv_rain_plmr(im,km,denl,denfacl,tkl,dzl,wwl,rql,rnl,precip,dt,id,iter,rid)






















      implicit none
      integer  im,km,id
      real  dt
      real  dzl(im,km),wwl(im,km),rql(im,km),rnl(im,km),precip(im)
      real  denl(im,km),denfacl(im,km),tkl(im,km)

      integer  i,k,n,m,kk,kb,kt,iter,rid
      real  tl,tl2,qql,dql,qqd
      real  th,th2,qqh,dqh
      real  zsum,qsum,dim,dip,c1,con1,fa1,fa2
      real  allold, allnew, zz, dzamin, cflmax, decfl
      real  dz(km), ww(km), qq(km), wd(km), was(km)
      real  den(km), denfac(km), tk(km)
      real  wi(km+1), zi(km+1), za(km+1)
      real  qn(km), qr(km), qr2(km)
      real tmp(km),tmp1(km),tmp2(km),tmp3(km),tmp4(km),nr(km)
      double precision wa(km),wa2(km), tmp5(km)
      real  dza(km+1), qa(km+1), qmi(km+1), qpi(km+1)

      precip(:) = 0.0

      i_loop : do i=1,im

      dz(:) = dzl(i,:)
      qq(:) = rql(i,:)
      nr(:) = rnl(i,:)
      if(rid .eq. 1) nr(:) = rnl(i,:)/denl(i,:)
      ww(:) = wwl(i,:)
      den(:) = denl(i,:)
      denfac(:) = denfacl(i,:)
      tk(:) = tkl(i,:)

      allold = 0.0
      do k=1,km
        allold = allold + qq(k)
      enddo
      if(allold.le.0.0) then
        cycle i_loop
      endif


      zi(1)=0.0
      do k=1,km
        zi(k+1) = zi(k)+dz(k)
      enddo


      wd(:) = ww(:)
      n=1
 100  continue


      wi(1) = ww(1)
      wi(km+1) = ww(km)
      do k=2,km
        wi(k) = (ww(k)*dz(k-1)+ww(k-1)*dz(k))/(dz(k-1)+dz(k))
      enddo

      fa1 = 9./16.
      fa2 = 1./16.
      wi(1) = ww(1)
      wi(2) = 0.5*(ww(2)+ww(1))
      do k=3,km-1
        wi(k) = fa1*(ww(k)+ww(k-1))-fa2*(ww(k+1)+ww(k-2))
      enddo
      wi(km) = 0.5*(ww(km)+ww(km-1))
      wi(km+1) = ww(km)


      do k=2,km
        if( ww(k).eq.0.0 ) wi(k)=ww(k-1)
      enddo


      con1 = 0.05
      do k=km,1,-1
        decfl = (wi(k+1)-wi(k))*dt/dz(k)
        if( decfl .gt. con1 ) then
          wi(k) = wi(k+1) - con1*dz(k)/dt
        endif
      enddo

      do k=1,km+1
        za(k) = zi(k) - wi(k)*dt
      enddo

      do k=1,km
        dza(k) = za(k+1)-za(k)
      enddo
      dza(km+1) = zi(km+1) - za(km+1)


      do k=1,km
        qa(k) = qq(k)*dz(k)/dza(k)
        qr(k) = qa(k)/den(k)
        if(rid .eq. 1) qr(k) = qa(K)
      enddo
      qa(km+1) = 0.0




      if( n.le.iter ) then
        if(rid.eq.1) then
        call slope_rain(qr,nr,den,denfac,tk,tmp,tmp1,tmp2,tmp3,tmp4,tmp5,wa,wa2,1,1,1,km)
        else
        call slope_rain(qr,nr,den,denfac,tk,tmp,tmp1,tmp2,tmp3,tmp4,tmp5,wa,wa2,1,1,1,km)
        endif
        if(rid.eq.1) wa(:) = wa2(:)
        if( n.ge.2 ) wa(1:km)=0.5*(wa(1:km)+was(1:km))
        do k=1,km




          ww(k) = 0.5* ( wd(k)+wa(k) )
        enddo
        was(:) = wa(:)
        n=n+1
        go to 100
      endif


      do k=2,km
        dip=(qa(k+1)-qa(k))/(dza(k+1)+dza(k))
        dim=(qa(k)-qa(k-1))/(dza(k-1)+dza(k))
        if( dip*dim.le.0.0 ) then
          qmi(k)=qa(k)
          qpi(k)=qa(k)
        else
          qpi(k)=qa(k)+0.5*(dip+dim)*dza(k)
          qmi(k)=2.0*qa(k)-qpi(k)
          if( qpi(k).lt.0.0 .or. qmi(k).lt.0.0 ) then
            qpi(k) = qa(k)
            qmi(k) = qa(k)
          endif
        endif
      enddo
      qpi(1)=qa(1)
      qmi(1)=qa(1)
      qmi(km+1)=qa(km+1)
      qpi(km+1)=qa(km+1)


      qn = 0.0
      kb=1
      kt=1
      intp : do k=1,km
             kb=max(kb-1,1)
             kt=max(kt-1,1)

             if( zi(k).ge.za(km+1) ) then
               exit intp
             else
               find_kb : do kk=kb,km
                         if( zi(k).le.za(kk+1) ) then
                           kb = kk
                           exit find_kb
                         else
                           cycle find_kb
                         endif
               enddo find_kb
               find_kt : do kk=kt,km
                         if( zi(k+1).le.za(kk) ) then
                           kt = kk
                           exit find_kt
                         else
                           cycle find_kt
                         endif
               enddo find_kt
               kt = kt - 1

               if( kt.eq.kb ) then
                 tl=(zi(k)-za(kb))/dza(kb)
                 th=(zi(k+1)-za(kb))/dza(kb)
                 tl2=tl*tl
                 th2=th*th
                 qqd=0.5*(qpi(kb)-qmi(kb))
                 qqh=qqd*th2+qmi(kb)*th
                 qql=qqd*tl2+qmi(kb)*tl
                 qn(k) = (qqh-qql)/(th-tl)
               else if( kt.gt.kb ) then
                 tl=(zi(k)-za(kb))/dza(kb)
                 tl2=tl*tl
                 qqd=0.5*(qpi(kb)-qmi(kb))
                 qql=qqd*tl2+qmi(kb)*tl
                 dql = qa(kb)-qql
                 zsum  = (1.-tl)*dza(kb)
                 qsum  = dql*dza(kb)
                 if( kt-kb.gt.1 ) then
                 do m=kb+1,kt-1
                   zsum = zsum + dza(m)
                   qsum = qsum + qa(m) * dza(m)
                 enddo
                 endif
                 th=(zi(k+1)-za(kt))/dza(kt)
                 th2=th*th
                 qqd=0.5*(qpi(kt)-qmi(kt))
                 dqh=qqd*th2+qmi(kt)*th
                 zsum  = zsum + th*dza(kt)
                 qsum  = qsum + dqh*dza(kt)
                 qn(k) = qsum/zsum
               endif
               cycle intp
             endif

       enddo intp


      sum_precip: do k=1,km
                    if( za(k).lt.0.0 .and. za(k+1).lt.0.0 ) then
                      precip(i) = precip(i) + qa(k)*dza(k)
                      cycle sum_precip
                    else if ( za(k).lt.0.0 .and. za(k+1).ge.0.0 ) then
                      precip(i) = precip(i) + qa(k)*(0.0-za(k))
                      exit sum_precip
                    endif
                    exit sum_precip
      enddo sum_precip


      rql(i,:) = qn(:)     


      enddo i_loop         

  END SUBROUTINE nislfv_rain_plmr


      subroutine refl10cm_kdm6 (qv1d, qr1d, nr1d, qs1d, qg1d, n0so1d,            &
                       n0go1d, t1d, p1d, dBZ, kts, kte, ii, jj,xam_g)
      IMPLICIT NONE
      REAL, DIMENSION(kts:kte), INTENT(IN):: xam_g

      INTEGER, INTENT(IN):: kts, kte, ii, jj
      REAL, DIMENSION(kts:kte), INTENT(IN)::                            &
                      qv1d, qr1d, nr1d, qs1d, qg1d, t1d, p1d
      real, DIMENSION(kts:kte), INTENT(IN)::  n0so1d, n0go1d
      REAL, DIMENSION(kts:kte), INTENT(INOUT):: dBZ


      REAL, DIMENSION(kts:kte):: temp, pres, qv, rho
      REAL, DIMENSION(kts:kte):: rr, nr, rs, rg
      REAL:: temp_C

      DOUBLE PRECISION, DIMENSION(kts:kte):: ilamr, ilams, ilamg
      DOUBLE PRECISION, DIMENSION(kts:kte):: N0_r, N0_s, N0_g
      DOUBLE PRECISION:: lamr, lams, lamg
      LOGICAL, DIMENSION(kts:kte):: L_qr, L_qs, L_qg

      REAL, DIMENSION(kts:kte):: ze_rain, ze_snow, ze_graupel
      DOUBLE PRECISION:: fmelt_s, fmelt_g

      INTEGER:: i, k, k_0, kbot, n
      LOGICAL:: melti

      DOUBLE PRECISION:: cback, x, eta, f_d
      REAL, PARAMETER:: R=287.



      do k = kts, kte
         dBZ(k) = -35.0
      enddo




      do k = kts, kte
         temp(k) = t1d(k)
         temp_C = min(-0.001, temp(K)-273.15)
         qv(k) = MAX(1.E-10, qv1d(k))
         pres(k) = p1d(k)
         rho(k) = 0.622*pres(k)/(R*temp(k)*(qv(k)+0.622))

         if (qr1d(k) .gt. 1.E-9) then
            rr(k) = qr1d(k)*rho(k)
            nr(k) = nr1d(k)*rho(k)
            lamr = (xam_r*xcrg(3)*xorg2*nr(k)/rr(k))**xobmr
            ilamr(k) = 1./lamr
            N0_r(k) = nr(k)*xorg2*lamr**xcre(2)
            L_qr(k) = .true.
         else
            rr(k) = 1.E-12
            nr(k) = 1.E-12
            L_qr(k) = .false.
         endif

         if (qs1d(k) .gt. 1.E-9) then
            rs(k) = qs1d(k)*rho(k)
            N0_s(k) = min(n0smax, n0so1d(k)*exp(-alpha*temp_C))
            lams = (xam_s*xcsg(3)*N0_s(k)/rs(k)/xcsg(2))**(1./xcse(1))

            ilams(k) = 1./lams
            L_qs(k) = .true.
         else
            rs(k) = 1.E-12
            L_qs(k) = .false.
         endif

         if (qg1d(k) .gt. 1.E-9) then
            rg(k) = qg1d(k)*rho(k)
            N0_g(k) = n0go1d(k)

            lamg = (xam_g(k)*xcgg(3)*N0_g(k)/rg(k)/xcgg(2))**(1./xcge(1))
            ilamg(k) = 1./lamg
            L_qg(k) = .true.
         else
            rg(k) = 1.E-12
            L_qg(k) = .false.
         endif
      enddo




      melti = .false.
      k_0 = kts
      do k = kte-1, kts, -1
         if ( (temp(k).gt.273.15) .and. L_qr(k)                         &
                                  .and. (L_qs(k+1).or.L_qg(k+1)) ) then
            k_0 = MAX(k+1, k_0)
            melti=.true.
            goto 195
         endif
      enddo
 195  continue







      do k = kts, kte
         ze_rain(k) = 1.e-22
         ze_snow(k) = 1.e-22
         ze_graupel(k) = 1.e-22
         if (L_qr(k)) ze_rain(k) = N0_r(k)*xcrg(4)*ilamr(k)**xcre(4)
         if (L_qs(k)) ze_snow(k) = (0.176/0.93) * (6.0/PI)*(6.0/PI)     &
                                 * (xam_s/900.0)*(xam_s/900.0)          &
                                 * N0_s(k)*xcsg(4)*ilams(k)**xcse(4)
         if (L_qg(k)) ze_graupel(k) = (0.176/0.93) * (6.0/PI)*(6.0/PI)  &
                                    * (xam_g(k)/900.0)*(xam_g(k)/900.0)       &
                                    * N0_g(k)*xcgg(4)*ilamg(k)**xcge(4)
      enddo










      if (melti .and. k_0.ge.kts+1) then
       do k = k_0-1, kts, -1


          if (L_qs(k) .and. L_qs(k_0) ) then
           fmelt_s = MAX(0.005d0, MIN(1.0d0-rs(k)/rs(k_0), 0.99d0))
           eta = 0.d0
           lams = 1./ilams(k)
           do n = 1, nrbins
              x = xam_s * xxDs(n)**xbm_s
              call rayleigh_soak_wetgraupel (x,DBLE(xocms),DBLE(xobms), &
                    fmelt_s, melt_outside_s, m_w_0, m_i_0, lamda_radar, &
                    CBACK, mixingrulestring_s, matrixstring_s,          &
                    inclusionstring_s, hoststring_s,                    &
                    hostmatrixstring_s, hostinclusionstring_s)
              f_d = N0_s(k)*xxDs(n)**xmu_s * DEXP(-lams*xxDs(n))
              eta = eta + f_d * CBACK * simpson(n) * xdts(n)
           enddo
           ze_snow(k) = SNGL(lamda4 / (pi5 * K_w) * eta)
          endif




          if (L_qg(k) .and. L_qg(k_0) ) then
           fmelt_g = MAX(0.005d0, MIN(1.0d0-rg(k)/rg(k_0), 0.99d0))
           eta = 0.d0
           lamg = 1./ilamg(k)
           do n = 1, nrbins
              x = xam_g(k) * xxDg(n)**xbm_g
              call rayleigh_soak_wetgraupel (x,DBLE((1./xam_g(k))**xobmg),DBLE(xobmg), &
                    fmelt_g, melt_outside_g, m_w_0, m_i_0, lamda_radar, &
                    CBACK, mixingrulestring_g, matrixstring_g,          &
                    inclusionstring_g, hoststring_g,                    &
                    hostmatrixstring_g, hostinclusionstring_g)
              f_d = N0_g(k)*xxDg(n)**xmu_g * DEXP(-lamg*xxDg(n))
              eta = eta + f_d * CBACK * simpson(n) * xdtg(n)
           enddo
           ze_graupel(k) = SNGL(lamda4 / (pi5 * K_w) * eta)
          endif

       enddo
      endif

      do k = kte, kts, -1
         dBZ(k) = 10.*log10((ze_rain(k)+ze_snow(k)+ze_graupel(k))*1.d18)
      enddo


      end subroutine refl10cm_kdm6



     subroutine effectRad_kdm6 (t, qc, nc, qi, ni, qs, rho, qmin, t0c,    &
                                re_qc, re_qi, re_qs, kts, kte, ii, jj)










      implicit none


      integer, intent(in) :: kts, kte, ii, jj
      real, intent(in) :: qmin
      real, intent(in) :: t0c
      real, dimension( kts:kte ), intent(in)::  t
      real, dimension( kts:kte ), intent(in)::  qc
      real, dimension( kts:kte ), intent(in)::  nc
      real, dimension( kts:kte ), intent(in)::  ni
      real, dimension( kts:kte ), intent(in)::  qi
      real, dimension( kts:kte ), intent(in)::  qs
      real, dimension( kts:kte ), intent(in)::  rho
      real, dimension( kts:kte ), intent(inout):: re_qc
      real, dimension( kts:kte ), intent(inout):: re_qi
      real, dimension( kts:kte ), intent(inout):: re_qs

      integer:: i,k
      integer :: inu_c
      real, dimension( kts:kte ):: rqc
      real, dimension( kts:kte ):: rnc
      real, dimension( kts:kte ):: rqi
      real, dimension( kts:kte ):: rni
      real, dimension( kts:kte ):: rqs
      real :: cdm2, cdm3, idm3, idm4
      real :: temp
      real :: supcol, n0sfac, lamdas
      real :: diai      
      double precision :: lamc, lamco
      double precision :: lami, lamio
      logical :: has_qc, has_qi, has_qs

      real, parameter :: R1 = 1.E-12
      real, parameter :: R2 = 1.E-6
      real, parameter :: pi = 3.1415926536
      real, parameter :: bm_r = 3.0
      real, parameter :: obmr = 1.0/bm_r


      has_qc = .false.
      has_qi = .false.
      has_qs = .false.

      cdm2 = rgmma(2./(xmu_c+1.)+1.)
      cdm3 = rgmma(3./(xmu_c+1.)+1.)
      idm3 = rgmma(3.+xmu_i)
      idm4 = rgmma(4.+xmu_i)
      do k=kts,kte
        
        rqc(k) = max(R1, qc(k)*rho(k))
        rnc(k) = max(R2, nc(k)*rho(k))
        if (rqc(k).gt.R1 .and. rnc(k).gt.R2) has_qc = .true.
        
        rqi(k) = max(R1, qi(k)*rho(k))
        rni(k) = max(R2, ni(k)*rho(k))
        if (rqi(k).gt.R1 .and. rni(k).gt.R2) has_qi = .true.
        
        rqs(k) = max(R1, qs(k)*rho(k))
        if (rqs(k).gt.R1) has_qs = .true.
      enddo

      if (has_qc) then
        do k=kts,kte
          if (rqc(k).le.R1 .or. rnc(k).le.R2) CYCLE

          lamc = (pidnc*rnc(k)/rqc(k))**(1./xbm_r)
          lamco =  lamc*2*cdm2/cdm3
          re_qc(k) =  max(2.51e-6,min(sngl(1.0d0/lamco),50.e-6))
        enddo
      endif

      if (has_qi) then
        do k=kts,kte
          if (rqi(k).le.R1 .or. rni(k).le.R2) CYCLE
           lami = (pidni*rni(k)/rqi(k))**(1./xbm_i) 
           lamio = lami*2*idm4/idm3
           re_qi(k) = max(10.01e-6,min(sngl(1.0d0/lamio),125.e-6))
        enddo
      endif

      if (has_qs) then
        do k=kts,kte
          if (rqs(k).le.R1) CYCLE
          supcol = t0c-t(k)
          n0sfac = max(min(exp(alpha*supcol),n0smax/n0s),1.)

          lamdas = exp(log((pidn0s*n0sfac/rqs(k)))*(1./(xbm_s+1))) 
          re_qs(k) = max(25.e-6,min(0.5*(1./lamdas),999.e-6))
        enddo
      endif

      end subroutine effectRad_kdm6


    subroutine pr77_scan_entry_state(qci,qrs,nrs,nci,brs,its,ite,kts,kte,lat)
      real, intent(in) :: qci(:,:,:),qrs(:,:,:),nrs(:,:,:),nci(:,:,:),brs(:,:)
      integer, intent(in) :: its,ite,kts,kte,lat
      integer :: i,k,counts(5,4),unit,ios
      counts=0
      do k=1,size(qrs,2)
        do i=1,size(qrs,1)
          call pr77_count_state(qrs(i,k,1),nrs(i,k,1),counts(:,1), &
               'rain',its+i-1,kts+k-1,lat,'KDM62D_ENTRY')
          call pr77_count_state(qci(i,k,1),nci(i,k,1),counts(:,2), &
               'cloud',its+i-1,kts+k-1,lat,'KDM62D_ENTRY')
          call pr77_count_state(qci(i,k,2),nci(i,k,2),counts(:,3), &
               'ice',its+i-1,kts+k-1,lat,'KDM62D_ENTRY')
          call pr77_count_state(qrs(i,k,3),brs(i,k),counts(:,4), &
               'graupel',its+i-1,kts+k-1,lat,'KDM62D_ENTRY')
        enddo
      enddo
!$omp critical(pr77_species_log)
      open(newunit=unit,file='pr77_native_species.raw', &
           status='unknown',position='append',action='write',iostat=ios)
      if (ios == 0) then
        write(unit,'(A,5(",",I0),20(",",I0))') 'PR77_COUNTS', &
             lat,its,ite,kts,kte,counts(:,1),counts(:,2),counts(:,3),counts(:,4)
        close(unit)
      endif
!$omp end critical(pr77_species_log)
    end subroutine pr77_scan_entry_state

    subroutine pr77_scan_slope_state(qci_current,qrs_current,nrs_current,nci_current, &
        brs,qrs,nrs,qci,nci,its,ite,kts,kte,lat,stage)
      real, intent(in) :: qci_current(:,:,:),qrs_current(:,:,:),nrs_current(:,:,:)
      real, intent(in) :: nci_current(:,:,:),brs(:,:),qrs(:,:,:),nrs(:,:),qci(:,:),nci(:,:)
      integer, intent(in) :: its,ite,kts,kte,lat
      character(len=*), intent(in) :: stage
      integer :: i,k
      do k=1,size(qrs,2)
        do i=1,size(qrs,1)
          call pr77_record_first(qrs_current(i,k,1),nrs_current(i,k,1), &
               'rain',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qci_current(i,k,1),nci_current(i,k,1), &
               'cloud',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qci_current(i,k,2),nci_current(i,k,2), &
               'ice',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qrs_current(i,k,3),brs(i,k), &
               'graupel',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qrs(i,k,1),nrs(i,k), &
               'rain_candidate',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qci(i,k),nci(i,k), &
               'ice_candidate',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qrs(i,k,3),brs(i,k), &
               'graupel_candidate',its+i-1,kts+k-1,lat,stage)
        enddo
      enddo
    end subroutine pr77_scan_slope_state

    subroutine pr77_scan_local_state(qr,nr,qc,nc,qi,ni,qg,bg,i,k,lat,stage)
      real, intent(in) :: qr,nr,qc,nc,qi,ni,qg,bg
      integer, intent(in) :: i,k,lat
      character(len=*), intent(in) :: stage
      call pr77_record_first(qr,nr,'rain',i,k,lat,stage)
      call pr77_record_first(qc,nc,'cloud',i,k,lat,stage)
      call pr77_record_first(qi,ni,'ice',i,k,lat,stage)
      call pr77_record_first(qg,bg,'graupel',i,k,lat,stage)
    end subroutine pr77_scan_local_state

    subroutine pr77_count_state(mass,moment,counts,species,i,k,lat,stage)
      real, intent(in) :: mass,moment
      integer, intent(inout) :: counts(5)
      character(len=*), intent(in) :: species,stage
      integer, intent(in) :: i,k,lat
      integer :: state
      state=classify_species_state(mass,moment)
      counts(state+1)=counts(state+1)+1
      call pr77_record_first(mass,moment,species,i,k,lat,stage)
    end subroutine pr77_count_state

    subroutine pr77_record_first(mass,moment,species,i,k,lat,stage)
      real, intent(in) :: mass,moment
      character(len=*), intent(in) :: species,stage
      integer, intent(in) :: i,k,lat
      integer, save :: written=0
      integer :: state,unit,ios,thread_id
      integer(c_int) :: mxcsr
      state=classify_species_state(mass,moment)
      if (state == SPECIES_ABSENT .or. state == SPECIES_ACTIVE) return
!$omp critical(pr77_species_log)
      if (written == 0) then
        mxcsr=pr75_read_fp_state(thread_id)
        open(newunit=unit,file='pr77_native_species.raw',status='unknown', &
             position='append',action='write',iostat=ios)
        if (ios == 0) then
          write(unit,'(A,",",A,",",A,5(",",I0),2(",",ES24.16E3), &
               3(",",Z8.8))') 'PR77_FIRST',trim(stage),trim(species), &
               state,i,lat,k,thread_id,mass,moment,transfer(mass,0), &
               transfer(moment,0),mxcsr
          close(unit)
          written=1
        endif
      endif
!$omp end critical(pr77_species_log)
    end subroutine pr77_record_first

END MODULE module_mp_kdm6

SUBROUTINE pr85_kdm6_paired_sediment_column(kts,kte,cell_i,lat,substep,dt,mstep, &
dry_density,delz,mass_rate,second_rate,qstate,second_state,mode,q_active_min, &
second_active_min,density_min,density_max,approved_q_rate,approved_second_rate, &
budget_unit,trace,valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)
USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
INTEGER, INTENT(IN) :: kts,kte,cell_i,lat,substep,mstep,budget_unit
INTEGER, PARAMETER :: PR85_SED_ICE=1, PR85_SED_GRAUPEL=2, PR87_SED_RAIN=3
REAL(real32), INTENT(IN) :: dt,dry_density(kts:kte),delz(kts:kte)
REAL(real64), INTENT(IN) :: mass_rate(kts:kte),second_rate(kts:kte)
REAL(real32), INTENT(INOUT) :: qstate(kts:kte),second_state(kts:kte)
INTEGER, INTENT(IN) :: mode
REAL(real32), INTENT(IN) :: q_active_min,second_active_min,density_min,density_max
REAL(real64), INTENT(OUT) :: approved_q_rate(kts:kte),approved_second_rate(kts:kte)
LOGICAL, INTENT(IN) :: trace
LOGICAL, INTENT(OUT) :: valid
REAL(real32), INTENT(IN) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max

REAL(real32) :: qwork(kts:kte),nwork(kts:kte),second_carrier(kts:kte)
REAL(real32) :: qd_store,nd_store,qr_store,nr_store
REAL(real64) :: qproposal(kts:kte),nproposal(kts:kte)
REAL(real64) :: rain_n_min(kts:kte),rain_n_max(kts:kte)
REAL(real64) :: theta,dt64
REAL(real64) :: proposed_q_sum,proposed_n_sum,approved_q_sum,approved_n_sum
REAL(real64) :: ground_q,ground_n,ground_approved_q,ground_approved_n
REAL(real64) :: stored_delta_q,stored_delta_n,residual_q,residual_n
REAL(real64) :: qd_inventory,nd_inventory
INTEGER :: k,iteration,io_status,nlevels
LOGICAL :: candidate_valid,full_empty_unpaired

valid=.FALSE.
approved_q_rate=0.0_real64
approved_second_rate=0.0_real64
IF (mode/=PR85_SED_ICE .AND. mode/=PR85_SED_GRAUPEL .AND. mode/=PR87_SED_RAIN) RETURN
IF (mode==PR85_SED_GRAUPEL) THEN
  IF (.NOT.ALL(ieee_is_finite([q_active_min,second_active_min,density_min,density_max]))) RETURN
  IF (q_active_min<0.0_real32 .OR. second_active_min<0.0_real32 .OR. &
      density_min<=0.0_real32 .OR. density_max<=density_min) RETURN
ENDIF
IF (mode==PR87_SED_RAIN) THEN
  IF (.NOT.ALL(ieee_is_finite([rain_pidn,rain_power,rain_lambda_min,rain_lambda_max]))) RETURN
  IF (rain_pidn<=0.0_real32 .OR. rain_power<=0.0_real32 .OR. rain_power>8.0_real32 .OR. &
      rain_lambda_min<=0.0_real32 .OR. rain_lambda_max<rain_lambda_min) RETURN
! Match NG's d<=8 domain and keep both lambda**d powers in normal R32 range.
  IF (REAL(rain_power,real64)*LOG(REAL(rain_lambda_min,real64))< &
      LOG(REAL(TINY(0.0_real32),real64)) .OR. &
      REAL(rain_power,real64)*LOG(REAL(rain_lambda_max,real64))> &
      LOG(REAL(HUGE(0.0_real32),real64)) ) RETURN
ENDIF
IF (kts>kte .OR. mstep<1 .OR. .NOT.ieee_is_finite(dt) .OR. dt<=0.0_real32) RETURN
nlevels=kte-kts+1
dt64=REAL(dt,real64)
IF (.NOT.ALL(ieee_is_finite(dry_density)) .OR. .NOT.ALL(ieee_is_finite(delz)) .OR. &
.NOT.ALL(ieee_is_finite(mass_rate)) .OR. .NOT.ALL(ieee_is_finite(second_rate)) .OR. &
.NOT.ALL(ieee_is_finite(qstate)) .OR. .NOT.ALL(ieee_is_finite(second_state))) RETURN
IF (ANY(dry_density<=0.0_real32) .OR. ANY(delz<=0.0_real32) .OR. &
ANY(mass_rate<0.0_real64) .OR. ANY(second_rate<0.0_real64)) RETURN
DO k=kts,kte
  second_carrier(k)=1.0_real32
  IF (mode==PR85_SED_GRAUPEL) second_carrier(k)=dry_density(k)
  IF (.NOT.ieee_is_finite(second_carrier(k)) .OR. second_carrier(k)<=0.0_real32) RETURN
  IF (mode==PR87_SED_RAIN) THEN
    rain_n_min(k)=REAL(dry_density(k),real64)* &
         REAL(rain_lambda_min,real64)**REAL(rain_power,real64)/REAL(rain_pidn,real64)
    rain_n_max(k)=REAL(dry_density(k),real64)* &
         REAL(rain_lambda_max,real64)**REAL(rain_power,real64)/REAL(rain_pidn,real64)
    IF (.NOT.ALL(ieee_is_finite([rain_n_min(k),rain_n_max(k)])) .OR. &
        rain_n_min(k)<=0.0_real64 .OR. &
        rain_n_max(k)<rain_n_min(k) .OR. &
        rain_n_max(k)>REAL(HUGE(0.0_real32),real64)) RETURN
    IF (.NOT.rain_state_valid32(qstate(k),second_state(k),rain_n_min(k),rain_n_max(k))) RETURN
  ELSE IF (mode==PR85_SED_GRAUPEL) THEN
    IF (.NOT.graupel_state_valid(qstate(k),second_state(k),density_min,density_max)) RETURN
  ELSE
    IF (.NOT.paired(qstate(k),second_state(k))) RETURN
  ENDIF
ENDDO

qwork=qstate
nwork=second_state
proposed_q_sum=0.0_real64
proposed_n_sum=0.0_real64
approved_q_sum=0.0_real64
approved_n_sum=0.0_real64
ground_q=0.0_real64
ground_n=0.0_real64
ground_approved_q=0.0_real64
ground_approved_n=0.0_real64
qproposal=0.0_real64
nproposal=0.0_real64
! The source passes V/DELZ rates (s-1); multiplying by DELZ below forms
! column packets in kg m-2 and mode-specific second-moment area units.
DO k=kts,kte
qproposal(k)=REAL(dry_density(k),real64)*REAL(qstate(k),real64)*mass_rate(k)* &
REAL(delz(k),real64)*dt64/REAL(mstep,real64)
nproposal(k)=REAL(second_state(k),real64)*second_rate(k)* &
REAL(second_carrier(k),real64)*REAL(delz(k),real64)*dt64/REAL(mstep,real64)
IF (.NOT.ieee_is_finite(qproposal(k)) .OR. .NOT.ieee_is_finite(nproposal(k)) .OR. &
qproposal(k)<0.0_real64 .OR. nproposal(k)<0.0_real64) RETURN
proposed_q_sum=proposed_q_sum+qproposal(k)
proposed_n_sum=proposed_n_sum+nproposal(k)
ENDDO

! Flux proposals are frozen from each level's current R32 state. G faces
! follow the native top-down sweep; ice retains its established bottom-up order.
IF (mode==PR85_SED_GRAUPEL .OR. mode==PR87_SED_RAIN) THEN
  DO k=kte-1,kts,-1
    CALL commit_face(k+1,k,.TRUE.)
    IF (.NOT.candidate_valid) RETURN
  ENDDO
  CALL commit_face(kts,0,.FALSE.)
  IF (.NOT.candidate_valid) RETURN
ELSE
  CALL commit_face(kts,0,.FALSE.)
  IF (.NOT.candidate_valid) RETURN
  DO k=kts,kte-1
    CALL commit_face(k+1,k,.TRUE.)
    IF (.NOT.candidate_valid) RETURN
  ENDDO
ENDIF

stored_delta_q=0.0_real64
stored_delta_n=0.0_real64
DO k=kts,kte
qd_inventory=REAL(dry_density(k),real64)*REAL(delz(k),real64)
nd_inventory=REAL(second_carrier(k),real64)*REAL(delz(k),real64)
stored_delta_q=stored_delta_q+(REAL(qwork(k),real64)-REAL(qstate(k),real64))*qd_inventory
stored_delta_n=stored_delta_n+(REAL(nwork(k),real64)-REAL(second_state(k),real64))*nd_inventory
ENDDO
residual_q=stored_delta_q+ground_approved_q
residual_n=stored_delta_n+ground_approved_n
IF (.NOT.ALL(ieee_is_finite([stored_delta_q,stored_delta_n,residual_q,residual_n]))) RETURN

IF (trace) THEN
IF (mode==PR85_SED_GRAUPEL) THEN
  WRITE(budget_unit,'(a,4i8,1p,12es24.16)',IOSTAT=io_status) &
  'PR85_G_SED',cell_i,lat,substep,nlevels,proposed_q_sum,approved_q_sum, &
  proposed_q_sum-approved_q_sum,proposed_n_sum,approved_n_sum, &
  proposed_n_sum-approved_n_sum,ground_approved_q,ground_approved_n,stored_delta_q,stored_delta_n, &
  residual_q,residual_n
ELSE IF (mode==PR87_SED_RAIN) THEN
  WRITE(budget_unit,'(a,4i8,1p,12es24.16)',IOSTAT=io_status) &
  'PR87_RAIN_SED',cell_i,lat,substep,nlevels,proposed_q_sum,approved_q_sum, &
  proposed_q_sum-approved_q_sum,proposed_n_sum,approved_n_sum, &
  proposed_n_sum-approved_n_sum,ground_approved_q,ground_approved_n,stored_delta_q,stored_delta_n, &
  residual_q,residual_n
  IF (io_status/=0) ERROR STOP 'PR87 paired rain sedimentation ledger write failed'
ELSE
WRITE(budget_unit,'(a,4i8,1p,12es24.16)',IOSTAT=io_status) &
'PR85_ICE_SED',cell_i,lat,substep,nlevels,proposed_q_sum,approved_q_sum, &
proposed_q_sum-approved_q_sum,proposed_n_sum,approved_n_sum, &
proposed_n_sum-approved_n_sum,ground_approved_q,ground_approved_n,stored_delta_q,stored_delta_n, &
residual_q,residual_n
ENDIF
IF (io_status/=0) ERROR STOP 'PR85 paired sedimentation ledger write failed'
ENDIF
qstate=qwork
second_state=nwork
valid=.TRUE.

CONTAINS

PURE LOGICAL FUNCTION paired(q,n)
REAL(real32), INTENT(IN) :: q,n
paired=.FALSE.
IF (.NOT.ieee_is_finite(q) .OR. .NOT.ieee_is_finite(n)) RETURN
IF (q<0.0_real32 .OR. n<0.0_real32) RETURN
paired=(q==0.0_real32 .AND. n==0.0_real32) .OR. &
(q>0.0_real32 .AND. n>0.0_real32)
END FUNCTION paired

PURE LOGICAL FUNCTION graupel_state_valid(q,b,rhomin,rhomax)
REAL(real32), INTENT(IN) :: q,b,rhomin,rhomax
REAL(real64) :: density
graupel_state_valid=.FALSE.
IF (.NOT.ieee_is_finite(q) .OR. .NOT.ieee_is_finite(b)) RETURN
IF (q<0.0_real32 .OR. b<0.0_real32) RETURN
IF (q==0.0_real32 .AND. b==0.0_real32) THEN
  graupel_state_valid=.TRUE.; RETURN
ENDIF
IF (q<=0.0_real32 .OR. b<=0.0_real32) RETURN
density=REAL(q,real64)/REAL(b,real64)
graupel_state_valid=ieee_is_finite(density) .AND. &
  density>=REAL(rhomin,real64) .AND. density<=REAL(rhomax,real64)
END FUNCTION graupel_state_valid

PURE LOGICAL FUNCTION rain_state_valid32(q,n,n_min,n_max)
REAL(real32), INTENT(IN) :: q,n
REAL(real64), INTENT(IN) :: n_min,n_max
rain_state_valid32=.FALSE.
IF (.NOT.ieee_is_finite(q) .OR. .NOT.ieee_is_finite(n) .OR. &
    .NOT.ALL(ieee_is_finite([n_min,n_max]))) RETURN
IF (q<0.0_real32 .OR. n<0.0_real32 .OR. n_min<=0.0_real64 .OR. n_max<n_min) RETURN
IF (.NOT.paired(q,n)) RETURN
IF (q==0.0_real32 .AND. n==0.0_real32) THEN
  rain_state_valid32=.TRUE.; RETURN
ENDIF
! NG admission uses these strict R64 count bounds; do not add a storage tolerance.
  rain_state_valid32=REAL(n,real64)>=n_min*REAL(q,real64) .AND. &
  REAL(n,real64)<=n_max*REAL(q,real64)
END FUNCTION rain_state_valid32

PURE LOGICAL FUNCTION rain_state_valid64(q,n,n_min,n_max)
REAL(real64), INTENT(IN) :: q,n,n_min,n_max
rain_state_valid64=.FALSE.
IF (.NOT.ALL(ieee_is_finite([q,n,n_min,n_max]))) RETURN
IF (q<0.0_real64 .OR. n<0.0_real64 .OR. n_min<=0.0_real64 .OR. n_max<n_min) RETURN
IF ((q==0.0_real64) .NEQV. (n==0.0_real64)) RETURN
IF (q==0.0_real64 .AND. n==0.0_real64) THEN
  rain_state_valid64=.TRUE.; RETURN
ENDIF
rain_state_valid64=n>=n_min*q .AND. n<=n_max*q
END FUNCTION rain_state_valid64

SUBROUTINE add_partition_point(points,count,base,change,target)
REAL(real64), INTENT(INOUT) :: points(16)
INTEGER, INTENT(INOUT) :: count
REAL(real64), INTENT(IN) :: base,change,target
REAL(real64) :: root
IF (.NOT.ieee_is_finite(base) .OR. .NOT.ieee_is_finite(change) .OR. &
    .NOT.ieee_is_finite(target) .OR. change==0.0_real64) RETURN
root=(target-base)/change
IF (.NOT.ieee_is_finite(root) .OR. root<=0.0_real64 .OR. root>=1.0_real64) RETURN
IF (count>=SIZE(points)) RETURN
count=count+1
points(count)=root
END SUBROUTINE add_partition_point

SUBROUTINE search_graupel_partitions(donor,receiver,pq,pn,has_receiver,factor,qd,nd,qr,nr,ok)
INTEGER, INTENT(IN) :: donor,receiver
REAL(real64), INTENT(IN) :: pq,pn
LOGICAL, INTENT(IN) :: has_receiver
REAL(real64), INTENT(OUT) :: factor
REAL(real32), INTENT(OUT) :: qd,nd,qr,nr
LOGICAL, INTENT(OUT) :: ok
REAL(real64) :: points(16),qchange(2),bchange(2),qbase(2),bbase(2)
REAL(real64) :: qden,bden,left,right,trials(3),trial
REAL(real32) :: qt,nt,rt,st
INTEGER :: count,endpoint,index,j
LOGICAL :: trial_ok,unpaired
points=0.0_real64; count=2; points(1)=0.0_real64; points(2)=1.0_real64
qden=REAL(dry_density(donor),real64)*REAL(delz(donor),real64)
bden=REAL(second_carrier(donor),real64)*REAL(delz(donor),real64)
CALL safe_ratio(pq,qden,qchange(1),trial_ok)
IF (.NOT.trial_ok) THEN
  factor=0.0_real64; qd=qwork(donor); nd=nwork(donor); qr=0.; nr=0.; ok=.FALSE.; RETURN
ENDIF
CALL safe_ratio(pn,bden,bchange(1),trial_ok)
IF (.NOT.trial_ok) THEN
  factor=0.0_real64; qd=qwork(donor); nd=nwork(donor); qr=0.; nr=0.; ok=.FALSE.; RETURN
ENDIF
qbase(1)=REAL(qwork(donor),real64); bbase(1)=REAL(nwork(donor),real64)
IF (has_receiver) THEN
  qden=REAL(dry_density(receiver),real64)*REAL(delz(receiver),real64)
  bden=REAL(second_carrier(receiver),real64)*REAL(delz(receiver),real64)
  CALL safe_ratio(pq,qden,qchange(2),trial_ok)
  IF (.NOT.trial_ok) THEN
    factor=0.0_real64; qd=qwork(donor); nd=nwork(donor); qr=qwork(receiver); nr=nwork(receiver); ok=.FALSE.; RETURN
  ENDIF
  CALL safe_ratio(pn,bden,bchange(2),trial_ok)
  IF (.NOT.trial_ok) THEN
    factor=0.0_real64; qd=qwork(donor); nd=nwork(donor); qr=qwork(receiver); nr=nwork(receiver); ok=.FALSE.; RETURN
  ENDIF
  qbase(2)=REAL(qwork(receiver),real64); bbase(2)=REAL(nwork(receiver),real64)
ENDIF
DO endpoint=1,1+MERGE(1,0,has_receiver)
  IF (endpoint==1) THEN
    qchange(endpoint)=-qchange(endpoint); bchange(endpoint)=-bchange(endpoint)
  ENDIF
  CALL add_partition_point(points,count,qbase(endpoint),qchange(endpoint),REAL(q_active_min,real64))
  CALL add_partition_point(points,count,bbase(endpoint),bchange(endpoint),REAL(second_active_min,real64))
  CALL add_partition_point(points,count,qbase(endpoint)-REAL(density_min,real64)*bbase(endpoint), &
       qchange(endpoint)-REAL(density_min,real64)*bchange(endpoint),0.0_real64)
  CALL add_partition_point(points,count,qbase(endpoint)-REAL(density_max,real64)*bbase(endpoint), &
       qchange(endpoint)-REAL(density_max,real64)*bchange(endpoint),0.0_real64)
  IF (endpoint==1) THEN
    qchange(endpoint)=-qchange(endpoint); bchange(endpoint)=-bchange(endpoint)
  ENDIF
ENDDO
DO index=2,count
  trial=points(index); j=index-1
  DO WHILE (j>=1)
    IF (points(j)<=trial) EXIT
    points(j+1)=points(j); j=j-1
  ENDDO
  points(j+1)=trial
ENDDO
DO index=count-1,1,-1
  left=points(index); right=points(index+1)
  IF (right<=left) CYCLE
  trials(1)=0.75_real64*left+0.25_real64*right
  trials(2)=0.5_real64*(left+right)
  trials(3)=0.25_real64*left+0.75_real64*right
  DO j=1,3
    trial=trials(j)
    IF (trial<=0.0_real64 .OR. trial>=1.0_real64) CYCLE
    CALL candidate(donor,receiver,pq,pn,trial,has_receiver,qt,nt,rt,st,trial_ok,unpaired)
    IF (trial_ok) THEN
      factor=trial; qd=qt; nd=nt; qr=rt; nr=st; ok=.TRUE.; RETURN
    ENDIF
  ENDDO
ENDDO
CALL candidate(donor,receiver,pq,pn,0.0_real64,has_receiver,qd,nd,qr,nr,ok,unpaired)
IF (ok) factor=0.0_real64
END SUBROUTINE search_graupel_partitions

SUBROUTINE commit_face(donor,receiver,has_receiver)
INTEGER, INTENT(IN) :: donor,receiver
LOGICAL, INTENT(IN) :: has_receiver
REAL(real64) :: pq,pn,theta_local
REAL(real32) :: qd,nd,qr,nr
LOGICAL :: accepted,unpaired
pq=qproposal(donor); pn=nproposal(donor)
CALL approve_packet(donor,receiver,pq,pn,has_receiver,theta_local,qd,nd,qr,nr,accepted,unpaired)
IF (.NOT.accepted .AND. mode==PR85_SED_GRAUPEL) THEN
  CALL search_graupel_partitions(donor,receiver,pq,pn,has_receiver,theta_local,qd,nd,qr,nr,accepted)
ELSE IF (.NOT.accepted .AND. unpaired) THEN
  theta_local=0.0_real64; accepted=.TRUE.
  qd=qwork(donor); nd=nwork(donor); qr=0.; nr=0.
  IF (has_receiver) THEN
    qr=qwork(receiver); nr=nwork(receiver)
  ENDIF
ELSE IF (.NOT.accepted) THEN
  CALL backtrack_packet(donor,receiver,pq,pn,has_receiver,theta_local,qd,nd,qr,nr,accepted)
ENDIF
candidate_valid=accepted
IF (.NOT.accepted) RETURN
qwork(donor)=qd; nwork(donor)=nd
approved_q_sum=approved_q_sum+theta_local*pq
approved_n_sum=approved_n_sum+theta_local*pn
approved_q_rate(donor)=theta_local*pq/(dt64*REAL(delz(donor),real64))
approved_second_rate(donor)=theta_local*pn/(dt64*REAL(delz(donor),real64))
IF (has_receiver) THEN
  qwork(receiver)=qr; nwork(receiver)=nr
ELSE
  ground_approved_q=ground_approved_q+theta_local*pq
  ground_approved_n=ground_approved_n+theta_local*pn
ENDIF
END SUBROUTINE commit_face

SUBROUTINE candidate(donor,receiver,pq,pn,factor,has_receiver,qd,nd,qr,nr,ok,empty_receiver_unpaired)
INTEGER, INTENT(IN) :: donor,receiver
REAL(real64), INTENT(IN) :: pq,pn,factor
LOGICAL, INTENT(IN) :: has_receiver
REAL(real32), INTENT(OUT) :: qd,nd,qr,nr
LOGICAL, INTENT(OUT) :: ok,empty_receiver_unpaired
REAL(real64) :: qden,nden,qd64,nd64,qr64,nr64,qchange,nchange,r32max
REAL(real64) :: donor_q_den,donor_n_den,receiver_q_den,receiver_n_den
REAL(real64) :: packet_q,packet_n,donor_q_loss,donor_n_loss,receiver_q_gain,receiver_n_gain
REAL(real64) :: donor_q_tol,donor_n_tol,receiver_q_tol,receiver_n_tol
LOGICAL :: ratio_valid
qd=qwork(donor); nd=nwork(donor)
qr=0.0_real32; nr=0.0_real32
IF (has_receiver) THEN
  qr=qwork(receiver); nr=nwork(receiver)
ENDIF
ok=.FALSE.; empty_receiver_unpaired=.FALSE.
r32max=REAL(HUGE(0.0_real32),real64)
qden=REAL(dry_density(donor),real64)*REAL(delz(donor),real64)
nden=REAL(second_carrier(donor),real64)*REAL(delz(donor),real64)
donor_q_den=qden; donor_n_den=nden
CALL safe_ratio(factor*pq,qden,qchange,ratio_valid)
IF (.NOT.ratio_valid) RETURN
CALL safe_ratio(factor*pn,nden,nchange,ratio_valid)
IF (.NOT.ratio_valid) RETURN
qd64=REAL(qwork(donor),real64)-qchange
nd64=REAL(nwork(donor),real64)-nchange
IF (.NOT.ieee_is_finite(qd64) .OR. .NOT.ieee_is_finite(nd64)) RETURN
IF (qd64<0.0_real64 .OR. nd64<0.0_real64) RETURN
IF (ABS(qd64)>r32max .OR. ABS(nd64)>r32max) RETURN
IF (has_receiver) THEN
qden=REAL(dry_density(receiver),real64)*REAL(delz(receiver),real64)
nden=REAL(second_carrier(receiver),real64)*REAL(delz(receiver),real64)
  receiver_q_den=qden; receiver_n_den=nden
  CALL safe_ratio(factor*pq,qden,qchange,ratio_valid)
  IF (.NOT.ratio_valid) RETURN
  CALL safe_ratio(factor*pn,nden,nchange,ratio_valid)
  IF (.NOT.ratio_valid) RETURN
  IF (qchange>HUGE(0.0_real64)-REAL(qwork(receiver),real64) .OR. &
      nchange>HUGE(0.0_real64)-REAL(nwork(receiver),real64)) RETURN
  qr64=REAL(qwork(receiver),real64)+qchange
  nr64=REAL(nwork(receiver),real64)+nchange
  IF (.NOT.ieee_is_finite(qr64) .OR. .NOT.ieee_is_finite(nr64)) RETURN
  IF (ABS(qr64)>r32max .OR. ABS(nr64)>r32max) RETURN
ENDIF
qd=REAL(qd64,real32); nd=REAL(nd64,real32)
IF (has_receiver) THEN
  qr=REAL(qr64,real32); nr=REAL(nr64,real32)
  IF (qwork(receiver)==0.0_real32 .AND. nwork(receiver)==0.0_real32) &
    empty_receiver_unpaired=(qr>0.0_real32 .NEQV. nr>0.0_real32)
ENDIF
IF (mode==PR85_SED_GRAUPEL) THEN
  IF (.NOT.graupel_state_valid(qd,nd,density_min,density_max)) RETURN
  IF (has_receiver) THEN
    IF (.NOT.graupel_state_valid(qr,nr,density_min,density_max)) RETURN
  ENDIF
ELSE IF (mode==PR87_SED_RAIN) THEN
  IF (.NOT.rain_state_valid64(qd64,nd64,rain_n_min(donor),rain_n_max(donor))) RETURN
  IF (has_receiver) THEN
    IF (.NOT.rain_state_valid64(qr64,nr64,rain_n_min(receiver),rain_n_max(receiver))) RETURN
  ENDIF
  IF (.NOT.rain_state_valid32(qd,nd,rain_n_min(donor),rain_n_max(donor))) RETURN
  IF (has_receiver) THEN
    IF (.NOT.rain_state_valid32(qr,nr,rain_n_min(receiver),rain_n_max(receiver))) RETURN
  ENDIF
ELSE
  IF (.NOT.paired(qd,nd)) RETURN
  IF (has_receiver) THEN
    IF (.NOT.paired(qr,nr)) RETURN
  ENDIF
ENDIF
IF (factor>0.0_real64 .AND. pq>0.0_real64) THEN
  packet_q=factor*pq
  donor_q_loss=(REAL(qwork(donor),real64)-REAL(qd,real64))*donor_q_den
  donor_q_tol=0.5_real64*REAL(ulp32(qd),real64)*donor_q_den + &
              32.0_real64*EPSILON(1.0_real64)*MAX(packet_q,ABS(donor_q_loss))
  IF (donor_q_loss<=0.0_real64 .OR. ABS(donor_q_loss-packet_q)>donor_q_tol) RETURN
  IF (has_receiver) THEN
    receiver_q_gain=(REAL(qr,real64)-REAL(qwork(receiver),real64))*receiver_q_den
    receiver_q_tol=0.5_real64*REAL(ulp32(qr),real64)*receiver_q_den + &
                   32.0_real64*EPSILON(1.0_real64)*MAX(packet_q,ABS(receiver_q_gain))
    IF (receiver_q_gain<=0.0_real64 .OR. ABS(receiver_q_gain-packet_q)>receiver_q_tol) RETURN
  ENDIF
ENDIF
IF (factor>0.0_real64 .AND. pn>0.0_real64) THEN
  packet_n=factor*pn
  donor_n_loss=(REAL(nwork(donor),real64)-REAL(nd,real64))*donor_n_den
  donor_n_tol=0.5_real64*REAL(ulp32(nd),real64)*donor_n_den + &
              32.0_real64*EPSILON(1.0_real64)*MAX(packet_n,ABS(donor_n_loss))
  IF (donor_n_loss<=0.0_real64 .OR. ABS(donor_n_loss-packet_n)>donor_n_tol) RETURN
  IF (has_receiver) THEN
    receiver_n_gain=(REAL(nr,real64)-REAL(nwork(receiver),real64))*receiver_n_den
    receiver_n_tol=0.5_real64*REAL(ulp32(nr),real64)*receiver_n_den + &
                   32.0_real64*EPSILON(1.0_real64)*MAX(packet_n,ABS(receiver_n_gain))
    IF (receiver_n_gain<=0.0_real64 .OR. ABS(receiver_n_gain-packet_n)>receiver_n_tol) RETURN
  ENDIF
ENDIF
IF (mode==PR85_SED_GRAUPEL) THEN
  ok=graupel_state_valid(qd,nd,density_min,density_max)
  IF (has_receiver) ok=ok .AND. graupel_state_valid(qr,nr,density_min,density_max)
ELSE IF (mode==PR87_SED_RAIN) THEN
  ok=rain_state_valid32(qd,nd,rain_n_min(donor),rain_n_max(donor))
  IF (has_receiver) ok=ok .AND. rain_state_valid32(qr,nr,rain_n_min(receiver),rain_n_max(receiver))
ELSE
  ok=paired(qd,nd)
  IF (has_receiver) ok=ok .AND. paired(qr,nr)
ENDIF
END SUBROUTINE candidate

PURE REAL(real32) FUNCTION ulp32(value)
REAL(real32), INTENT(IN) :: value
REAL(real32) :: above,below,up_gap,down_gap
ulp32=NEAREST(0.0_real32,1.0_real32)
IF (value==HUGE(0.0_real32)) THEN
  below=NEAREST(value,-1.0_real32)
  ulp32=value-below
  RETURN
ENDIF
above=NEAREST(value,1.0_real32)
below=NEAREST(value,-1.0_real32)
up_gap=above-value
down_gap=value-below
ulp32=MAX(up_gap,down_gap)
END FUNCTION ulp32

PURE SUBROUTINE safe_ratio(numerator,denominator,ratio,ok)
REAL(real64), INTENT(IN) :: numerator,denominator
REAL(real64), INTENT(OUT) :: ratio
LOGICAL, INTENT(OUT) :: ok
ratio=0.0_real64; ok=.FALSE.
IF (.NOT.ieee_is_finite(numerator) .OR. .NOT.ieee_is_finite(denominator)) RETURN
IF (numerator<0.0_real64 .OR. denominator<=0.0_real64) RETURN
IF (denominator<1.0_real64) THEN
  IF (numerator>HUGE(0.0_real64)*denominator) RETURN
ENDIF
ratio=numerator/denominator
ok=ieee_is_finite(ratio)
END SUBROUTINE safe_ratio

SUBROUTINE approve_packet(donor,receiver,pq,pn,has_receiver,factor,qd,nd,qr,nr,ok,empty_receiver_unpaired)
INTEGER, INTENT(IN) :: donor,receiver
REAL(real64), INTENT(IN) :: pq,pn
LOGICAL, INTENT(IN) :: has_receiver
REAL(real64), INTENT(OUT) :: factor
REAL(real32), INTENT(OUT) :: qd,nd,qr,nr
LOGICAL, INTENT(OUT) :: ok,empty_receiver_unpaired
factor=1.0_real64
CALL candidate(donor,receiver,pq,pn,factor,has_receiver,qd,nd,qr,nr,ok,empty_receiver_unpaired)
END SUBROUTINE approve_packet

SUBROUTINE backtrack_packet(donor,receiver,pq,pn,has_receiver,factor,qd,nd,qr,nr,ok)
INTEGER, INTENT(IN) :: donor,receiver
REAL(real64), INTENT(IN) :: pq,pn
LOGICAL, INTENT(IN) :: has_receiver
REAL(real64), INTENT(OUT) :: factor
REAL(real32), INTENT(OUT) :: qd,nd,qr,nr
LOGICAL, INTENT(OUT) :: ok
REAL(real64) :: lower,upper,middle
REAL(real32) :: qdt,ndt,qrt,nrt
LOGICAL :: trial_ok,empty_receiver_unpaired
lower=0.0_real64; upper=1.0_real64
qd=qwork(donor); nd=nwork(donor)
qr=0.0_real32; nr=0.0_real32
IF (has_receiver) THEN
qr=qwork(receiver); nr=nwork(receiver)
ENDIF
IF (mode==PR85_SED_GRAUPEL) THEN
  CALL search_graupel_partitions(donor,receiver,pq,pn,has_receiver,factor,qd,nd,qr,nr,ok)
  RETURN
ENDIF
factor=0.0_real64; ok=.TRUE.
DO iteration=1,64
middle=0.5_real64*(lower+upper)
CALL candidate(donor,receiver,pq,pn,middle,has_receiver,qdt,ndt,qrt,nrt, &
trial_ok,empty_receiver_unpaired)
IF (trial_ok) THEN
lower=middle; qd=qdt; nd=ndt; qr=qrt; nr=nrt
ELSE
upper=middle
ENDIF
ENDDO
factor=lower
IF (factor>0.0_real64 .AND. qd==qwork(donor) .AND. nd==nwork(donor)) THEN
IF (.NOT.has_receiver) THEN
factor=0.0_real64
ELSE IF (qr==qwork(receiver) .AND. nr==nwork(receiver)) THEN
factor=0.0_real64
ENDIF
ENDIF
END SUBROUTINE backtrack_packet

END SUBROUTINE pr85_kdm6_paired_sediment_column
SUBROUTINE pr85_kdm6_subthreshold_melt(qcloud,ncloud,qrain,nrain,dry_density, &
delz,qmelt,snow_mean_mass,cloud_min,cloud_max,rain_min,rain_max, &
qcloud_after,ncloud_after,qrain_after,nrain_after,number_requested, &
route,accepted)
USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
REAL(real32), INTENT(IN) :: qcloud,ncloud,qrain,nrain,dry_density,delz,qmelt
REAL(real32), INTENT(IN) :: snow_mean_mass,cloud_min,cloud_max,rain_min,rain_max
REAL(real32), INTENT(OUT) :: qcloud_after,ncloud_after,qrain_after,nrain_after
REAL(real64), INTENT(OUT) :: number_requested
INTEGER, INTENT(OUT) :: route
LOGICAL, INTENT(OUT) :: accepted

REAL(real64) :: source_mass,source_number
REAL(real64) :: mean_mass,r32max
REAL(real32) :: qstored,nstored
LOGICAL :: source_fits_cloud,source_fits_rain

qcloud_after=qcloud
ncloud_after=ncloud
qrain_after=qrain
nrain_after=nrain
number_requested=0.0_real64
route=0
accepted=.FALSE.
IF (.NOT.ALL(ieee_is_finite([qcloud,ncloud,qrain,nrain,dry_density,delz,qmelt, &
    snow_mean_mass,cloud_min,cloud_max,rain_min,rain_max]))) RETURN
IF (MIN(qcloud,ncloud,qrain,nrain)<0.0_real32 .OR. dry_density<=0.0_real32 .OR. &
    delz<=0.0_real32 .OR. qmelt<0.0_real32 .OR. snow_mean_mass<=0.0_real32 .OR. &
    cloud_min<=0.0_real32 .OR. cloud_max<cloud_min .OR. rain_min<=0.0_real32 .OR. &
    rain_max<rain_min) RETURN
IF (.NOT.paired(qcloud,ncloud) .OR. .NOT.paired(qrain,nrain)) RETURN
IF (qmelt==0.0_real32) THEN
  accepted=.TRUE.
  RETURN
ENDIF

source_mass=REAL(snow_mean_mass,real64)
source_number=REAL(dry_density,real64)*REAL(qmelt,real64)/source_mass
IF (.NOT.ieee_is_finite(source_number) .OR. source_number<=0.0_real64) RETURN
number_requested=source_number
source_fits_cloud=snow_mean_mass>=cloud_min .AND. snow_mean_mass<=cloud_max
source_fits_rain=snow_mean_mass>=rain_min .AND. snow_mean_mass<=rain_max
r32max=REAL(HUGE(0.0_real32),real64)

IF (source_fits_cloud) THEN
  CALL try_category(qcloud,ncloud,cloud_min,cloud_max,ok=accepted, &
       qstored=qstored,nstored=nstored)
  IF (accepted) THEN
    route=1
    qcloud_after=qstored
    ncloud_after=nstored
    RETURN
  ENDIF
ENDIF
IF (source_fits_rain) THEN
  CALL try_category(qrain,nrain,rain_min,rain_max,ok=accepted, &
       qstored=qstored,nstored=nstored)
  IF (accepted) THEN
    route=2
    qrain_after=qstored
    nrain_after=nstored
    RETURN
  ENDIF
ENDIF
route=0
accepted=.FALSE.

CONTAINS

SUBROUTINE try_category(qold,nold,mean_min,mean_max,ok,qstored,nstored)
REAL(real32), INTENT(IN) :: qold,nold,mean_min,mean_max
LOGICAL, INTENT(OUT) :: ok
REAL(real32), INTENT(OUT) :: qstored,nstored
REAL(real64) :: qtrial,ntrial
qstored=qold
nstored=nold
ok=.FALSE.
qtrial=REAL(qold,real64)+REAL(qmelt,real64)
ntrial=REAL(nold,real64)+source_number
IF (.NOT.ieee_is_finite(qtrial) .OR. .NOT.ieee_is_finite(ntrial)) RETURN
IF (qtrial<=0.0_real64 .OR. ntrial<=0.0_real64 .OR. &
    qtrial>r32max .OR. ntrial>r32max) RETURN
mean_mass=REAL(dry_density,real64)*qtrial/ntrial
IF (.NOT.ieee_is_finite(mean_mass) .OR. &
    mean_mass<REAL(mean_min,real64) .OR. mean_mass>REAL(mean_max,real64)) RETURN
qstored=REAL(qtrial,real32)
nstored=REAL(ntrial,real32)
IF (.NOT.ieee_is_finite(qstored) .OR. .NOT.ieee_is_finite(nstored)) RETURN
IF (.NOT.paired(qstored,nstored)) RETURN
mean_mass=REAL(dry_density,real64)*REAL(qstored,real64)/REAL(nstored,real64)
IF (.NOT.ieee_is_finite(mean_mass) .OR. &
    mean_mass<REAL(mean_min,real64) .OR. mean_mass>REAL(mean_max,real64)) RETURN
ok=.TRUE.
END SUBROUTINE try_category

PURE LOGICAL FUNCTION paired(q,n)
REAL(real32), INTENT(IN) :: q,n
paired=(q==0.0_real32 .AND. n==0.0_real32) .OR. &
       (q>0.0_real32 .AND. n>0.0_real32)
END FUNCTION paired

END SUBROUTINE pr85_kdm6_subthreshold_melt

PURE LOGICAL FUNCTION pr93_kdm6_pair_in_cone(q,n,rho,mmin,mmax)
USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
REAL(real32), INTENT(IN) :: q,n,rho
REAL(real64), INTENT(IN) :: mmin,mmax
REAL(real64) :: mean_mass,lo_tol,hi_tol
pr93_kdm6_pair_in_cone=.FALSE.
IF (q==0.0_real32 .AND. n==0.0_real32) THEN
  pr93_kdm6_pair_in_cone=.TRUE.
  RETURN
ENDIF
IF (q<=0.0_real32 .OR. n<=0.0_real32) RETURN
mean_mass=REAL(rho,real64)*REAL(q,real64)/REAL(n,real64)
lo_tol=8.0_real64*REAL(SPACING(REAL(mmin,real32)),real64)
hi_tol=8.0_real64*REAL(SPACING(REAL(mmax,real32)),real64)
pr93_kdm6_pair_in_cone=ieee_is_finite(mean_mass) .AND. &
        mean_mass>=mmin-lo_tol .AND. mean_mass<=mmax+hi_tol
END FUNCTION pr93_kdm6_pair_in_cone

SUBROUTINE pr85_kdm6_freezing_packet(qcloud,ncloud,qice,nice,dry_density,ice_transient_mass_limit, &
mass_requested,number_requested,cloud_min,cloud_max,ice_min,ice_max, &
qcloud_after,ncloud_after,qice_after,nice_after,mass_approved, &
number_approved,fraction,base_valid,accepted)
USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
REAL(real32), INTENT(IN) :: qcloud,ncloud,qice,nice,dry_density
REAL(real64), INTENT(IN) :: ice_transient_mass_limit
REAL(real64), INTENT(IN) :: mass_requested,number_requested
REAL(real64), INTENT(IN) :: cloud_min,cloud_max,ice_min,ice_max
REAL(real32), INTENT(OUT) :: qcloud_after,ncloud_after,qice_after,nice_after
REAL(real64), INTENT(OUT) :: mass_approved,number_approved,fraction
LOGICAL, INTENT(OUT) :: base_valid,accepted
LOGICAL, EXTERNAL :: pr93_kdm6_pair_in_cone

REAL(real64) :: theta
REAL(real32) :: qct,nct,qit,nit
LOGICAL :: feasible,found
INTEGER :: attempt

qcloud_after=qcloud
ncloud_after=ncloud
qice_after=qice
nice_after=nice
mass_approved=0.0_real64
number_approved=0.0_real64
fraction=0.0_real64
base_valid=.FALSE.
accepted=.FALSE.
IF (.NOT.ALL(ieee_is_finite([qcloud,ncloud,qice,nice,dry_density]))) RETURN
IF (.NOT.ieee_is_finite(ice_transient_mass_limit)) RETURN
IF (.NOT.ALL(ieee_is_finite([mass_requested,number_requested,cloud_min,cloud_max, &
    ice_min,ice_max]))) RETURN
IF (MIN(qcloud,ncloud,qice,nice)<0.0_real32 .OR. dry_density<=0.0_real32 .OR. &
    ice_transient_mass_limit<0.0_real64 .OR. &
    mass_requested<0.0_real64 .OR. number_requested<0.0_real64 .OR. &
    cloud_min<=0.0_real64 .OR. cloud_max<cloud_min .OR. &
    ice_min<=0.0_real64 .OR. ice_max<ice_min) RETURN
IF (MIN(cloud_min,ice_min)<REAL(TINY(0.0_real32),real64) .OR. &
    MAX(cloud_max,ice_max)>REAL(HUGE(0.0_real32),real64)) RETURN
IF (.NOT.paired(qcloud,ncloud) .OR. .NOT.paired(qice,nice)) RETURN
IF (.NOT.pr93_kdm6_pair_in_cone(qcloud,ncloud,dry_density,cloud_min,cloud_max)) RETURN
IF (qice>0.0_real32 .AND. REAL(qice,real64)<=ice_transient_mass_limit) THEN
! Native KDM6 skips ice PSD reconstruction below the 1.e-14 mass gate.
! Admit only that source-bounded base category;
! candidate endpoints still pass the strict ice cone below.
ELSE
  IF (.NOT.pr93_kdm6_pair_in_cone(qice,nice,dry_density,ice_min,ice_max)) RETURN
ENDIF
base_valid=.TRUE.
IF (mass_requested==0.0_real64 .AND. number_requested==0.0_real64) THEN
  accepted=.TRUE.
  RETURN
ENDIF
IF (mass_requested<=0.0_real64 .OR. number_requested<=0.0_real64) RETURN

! Full source proposal is preferred. If storage/PSD constraints require it,
! deterministic halving seeks a representable paired fraction.
theta=1.0_real64
found=.FALSE.
DO attempt=0,48
  CALL candidate(theta,qct,nct,qit,nit,feasible)
  IF (feasible) THEN
    found=.TRUE.
    EXIT
  ENDIF
  theta=theta*0.5_real64
ENDDO
IF (.NOT.found) RETURN
qcloud_after=qct
ncloud_after=nct
qice_after=qit
nice_after=nit
fraction=theta
mass_approved=theta*mass_requested
number_approved=theta*number_requested
accepted=.TRUE.

CONTAINS

SUBROUTINE candidate(scale,qco,nco,qio,nio,ok)
REAL(real64), INTENT(IN) :: scale
REAL(real32), INTENT(OUT) :: qco,nco,qio,nio
LOGICAL, INTENT(OUT) :: ok
REAL(real64) :: qcd,ncd,qid,nid,r32max,mass_amount,number_amount
qco=qcloud; nco=ncloud; qio=qice; nio=nice
ok=.FALSE.
r32max=REAL(HUGE(0.0_real32),real64)
qcd=REAL(qcloud,real64)-scale*mass_requested
ncd=REAL(ncloud,real64)-scale*number_requested
qid=REAL(qice,real64)+scale*mass_requested
nid=REAL(nice,real64)+scale*number_requested
IF (.NOT.ALL(ieee_is_finite([qcd,ncd,qid,nid]))) RETURN
IF (MIN(qcd,ncd,qid,nid)<0.0_real64 .OR. MAX(qcd,ncd,qid,nid)>r32max) RETURN
qco=REAL(qcd,real32); nco=REAL(ncd,real32)
qio=REAL(qid,real32); nio=REAL(nid,real32)
IF (.NOT.ALL(ieee_is_finite([qco,nco,qio,nio]))) RETURN
IF (.NOT.paired(qco,nco) .OR. .NOT.paired(qio,nio)) RETURN
! A positive packet must be stored on both sides for each moment.
IF (qco>=qcloud .OR. nco>=ncloud .OR. qio<=qice .OR. nio<=nice) RETURN
mass_amount=scale*mass_requested
number_amount=scale*number_requested
IF (.NOT.change_matches_packet(REAL(qcloud,real64)-REAL(qco,real64), &
    mass_amount,qco)) RETURN
IF (.NOT.change_matches_packet(REAL(qio,real64)-REAL(qice,real64), &
    mass_amount,qio)) RETURN
IF (.NOT.change_matches_packet(REAL(ncloud,real64)-REAL(nco,real64), &
    number_amount,nco)) RETURN
IF (.NOT.change_matches_packet(REAL(nio,real64)-REAL(nice,real64), &
    number_amount,nio)) RETURN
IF (.NOT.pr93_kdm6_pair_in_cone(qco,nco,dry_density,cloud_min,cloud_max) .OR. &
    .NOT.pr93_kdm6_pair_in_cone(qio,nio,dry_density,ice_min,ice_max)) RETURN
ok=.TRUE.
END SUBROUTINE candidate

PURE LOGICAL FUNCTION change_matches_packet(actual,requested,new_value)
REAL(real64), INTENT(IN) :: actual,requested
REAL(real32), INTENT(IN) :: new_value
REAL(real64) :: tolerance
! The old REAL32 endpoint is exact in REAL64; only the new stored endpoint
! rounds, so use half an ULP at the new endpoint.
tolerance=0.5_real64*endpoint_ulp(new_value)+ &
          32.0_real64*EPSILON(0.0_real64)* &
          MAX(ABS(actual),ABS(requested),ABS(REAL(new_value,real64)))
change_matches_packet=ABS(actual-requested)<=tolerance
END FUNCTION change_matches_packet

PURE REAL(real64) FUNCTION endpoint_ulp(value)
REAL(real32), INTENT(IN) :: value
REAL(real32) :: next_value
IF (value<TINY(0.0_real32)) THEN
  next_value=NEAREST(value,1.0_real32)
  endpoint_ulp=REAL(next_value,real64)-REAL(value,real64)
ELSE
  endpoint_ulp=REAL(SPACING(value),real64)
ENDIF
END FUNCTION endpoint_ulp

PURE LOGICAL FUNCTION paired(q,n)
REAL(real32), INTENT(IN) :: q,n
paired=(q==0.0_real32 .AND. n==0.0_real32) .OR. &
       (q>0.0_real32 .AND. n>0.0_real32)
END FUNCTION paired



END SUBROUTINE pr85_kdm6_freezing_packet

SUBROUTINE pr85_kdm6_rain_freezing_packet(qrain,nrain,qgraupel,vgraupel, &
dry_density,mass_requested,number_requested,volume_requested, &
rain_min,rain_max,graupel_density_min,graupel_density_max, &
qrain_after,nrain_after,qgraupel_after,vgraupel_after, &
mass_approved,number_approved,volume_approved,fraction,base_valid,accepted)
USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
REAL(real32), INTENT(IN) :: qrain,nrain,qgraupel,vgraupel,dry_density
REAL(real64), INTENT(IN) :: mass_requested,number_requested,volume_requested
REAL(real64), INTENT(IN) :: rain_min,rain_max,graupel_density_min,graupel_density_max
REAL(real32), INTENT(OUT) :: qrain_after,nrain_after,qgraupel_after,vgraupel_after
REAL(real64), INTENT(OUT) :: mass_approved,number_approved,volume_approved,fraction
LOGICAL, INTENT(OUT) :: base_valid,accepted
REAL(real64) :: theta
REAL(real32) :: qrt,nrt,qgt,vgt
LOGICAL :: feasible,found
INTEGER :: attempt

qrain_after=qrain; nrain_after=nrain
qgraupel_after=qgraupel; vgraupel_after=vgraupel
mass_approved=0.0_real64; number_approved=0.0_real64
volume_approved=0.0_real64; fraction=0.0_real64
base_valid=.FALSE.; accepted=.FALSE.
IF (.NOT.ALL(ieee_is_finite([qrain,nrain,qgraupel,vgraupel,dry_density]))) RETURN
IF (.NOT.ALL(ieee_is_finite([mass_requested,number_requested,volume_requested, &
    rain_min,rain_max,graupel_density_min,graupel_density_max]))) RETURN
IF (MIN(qrain,nrain,qgraupel,vgraupel)<0.0_real32 .OR. dry_density<=0.0_real32) RETURN
IF (MIN(mass_requested,number_requested,volume_requested)<0.0_real64) RETURN
IF (rain_min<=0.0_real64 .OR. rain_max<rain_min .OR. &
    graupel_density_min<=0.0_real64 .OR. graupel_density_max<graupel_density_min) RETURN
IF (MIN(rain_min,graupel_density_min)<REAL(TINY(0.0_real32),real64) .OR. &
    MAX(rain_max,graupel_density_max)>REAL(HUGE(0.0_real32),real64)) RETURN
IF (.NOT.paired(qrain,nrain) .OR. .NOT.paired(qgraupel,vgraupel)) RETURN
IF (.NOT.rain_cone(qrain,nrain,dry_density,rain_min,rain_max) .OR. &
    .NOT.graupel_cone(qgraupel,vgraupel,graupel_density_min,graupel_density_max)) RETURN
base_valid=.TRUE.
IF (mass_requested==0.0_real64 .AND. number_requested==0.0_real64 .AND. &
    volume_requested==0.0_real64) THEN
  accepted=.TRUE.
  RETURN
ENDIF
! This source process is one coupled mass/number/volume packet. A missing
! moment proposal cannot be repaired with a floor or a post-process remap.
IF (mass_requested<=0.0_real64 .OR. number_requested<=0.0_real64 .OR. &
    volume_requested<=0.0_real64) RETURN

theta=1.0_real64
found=.FALSE.
DO attempt=0,48
  CALL candidate(theta,qrt,nrt,qgt,vgt,feasible)
  IF (feasible) THEN
    found=.TRUE.
    EXIT
  ENDIF
  theta=theta*0.5_real64
ENDDO
IF (.NOT.found) RETURN
qrain_after=qrt; nrain_after=nrt
qgraupel_after=qgt; vgraupel_after=vgt
fraction=theta
mass_approved=theta*mass_requested
number_approved=theta*number_requested
volume_approved=theta*volume_requested
accepted=.TRUE.

CONTAINS

SUBROUTINE candidate(scale,qro,nro,qgo,vgo,ok)
REAL(real64), INTENT(IN) :: scale
REAL(real32), INTENT(OUT) :: qro,nro,qgo,vgo
LOGICAL, INTENT(OUT) :: ok
REAL(real64) :: qr64,nr64,qg64,vg64,r32max
qro=qrain; nro=nrain; qgo=qgraupel; vgo=vgraupel
ok=.FALSE.
r32max=REAL(HUGE(0.0_real32),real64)
qr64=REAL(qrain,real64)-scale*mass_requested
nr64=REAL(nrain,real64)-scale*number_requested
qg64=REAL(qgraupel,real64)+scale*mass_requested
vg64=REAL(vgraupel,real64)+scale*volume_requested
IF (.NOT.ALL(ieee_is_finite([qr64,nr64,qg64,vg64]))) RETURN
IF (MIN(qr64,nr64,qg64,vg64)<0.0_real64 .OR. &
    MAX(qr64,nr64,qg64,vg64)>r32max) RETURN
qro=REAL(qr64,real32); nro=REAL(nr64,real32)
qgo=REAL(qg64,real32); vgo=REAL(vg64,real32)
IF (.NOT.ALL(ieee_is_finite([qro,nro,qgo,vgo]))) RETURN
IF (.NOT.paired(qro,nro) .OR. .NOT.paired(qgo,vgo)) RETURN
! Do not approve a transfer unless all four source/receiver changes are stored.
IF (qro>=qrain .OR. nro>=nrain .OR. qgo<=qgraupel .OR. vgo<=vgraupel) RETURN
IF (.NOT.change_matches(REAL(qrain,real64)-REAL(qro,real64), &
    scale*mass_requested,qro)) RETURN
IF (.NOT.change_matches(REAL(nrain,real64)-REAL(nro,real64), &
    scale*number_requested,nro)) RETURN
IF (.NOT.change_matches(REAL(qgo,real64)-REAL(qgraupel,real64), &
    scale*mass_requested,qgo)) RETURN
IF (.NOT.change_matches(REAL(vgo,real64)-REAL(vgraupel,real64), &
    scale*volume_requested,vgo)) RETURN
IF (.NOT.rain_cone(qro,nro,dry_density,rain_min,rain_max) .OR. &
    .NOT.graupel_cone(qgo,vgo,graupel_density_min,graupel_density_max)) RETURN
ok=.TRUE.
END SUBROUTINE candidate

PURE LOGICAL FUNCTION change_matches(actual,requested,new_value)
REAL(real64), INTENT(IN) :: actual,requested
REAL(real32), INTENT(IN) :: new_value
REAL(real64) :: tolerance
! The old REAL32 endpoint is exact in REAL64. Only the new stored endpoint
! rounds, so the storage allowance is half an ULP at that endpoint.
tolerance=0.5_real64*endpoint_ulp(new_value)+32.0_real64*EPSILON(0.0_real64)* &
          MAX(ABS(actual),ABS(requested),ABS(REAL(new_value,real64)))
change_matches=ABS(actual-requested)<=tolerance
END FUNCTION change_matches

PURE REAL(real64) FUNCTION endpoint_ulp(value)
REAL(real32), INTENT(IN) :: value
REAL(real32) :: next_value
IF (value>=HUGE(value)) THEN
  endpoint_ulp=REAL(SPACING(value),real64)
ELSEIF (value<TINY(value)) THEN
  next_value=NEAREST(value,1.0_real32)
  endpoint_ulp=REAL(next_value,real64)-REAL(value,real64)
ELSE
  endpoint_ulp=REAL(SPACING(value),real64)
ENDIF
END FUNCTION endpoint_ulp

PURE LOGICAL FUNCTION paired(q,n)
REAL(real32), INTENT(IN) :: q,n
paired=(q==0.0_real32 .AND. n==0.0_real32) .OR. &
       (q>0.0_real32 .AND. n>0.0_real32)
END FUNCTION paired

PURE LOGICAL FUNCTION rain_cone(q,n,rho,mmin,mmax)
REAL(real32), INTENT(IN) :: q,n,rho
REAL(real64), INTENT(IN) :: mmin,mmax
REAL(real64) :: mean_mass,lo_tol,hi_tol
rain_cone=.FALSE.
IF (q==0.0_real32 .AND. n==0.0_real32) THEN
  rain_cone=.TRUE.; RETURN
ENDIF
IF (q<=0.0_real32 .OR. n<=0.0_real32) RETURN
mean_mass=REAL(rho,real64)*REAL(q,real64)/REAL(n,real64)
lo_tol=8.0_real64*REAL(SPACING(REAL(mmin,real32)),real64)
hi_tol=8.0_real64*REAL(SPACING(REAL(mmax,real32)),real64)
rain_cone=ieee_is_finite(mean_mass) .AND. mean_mass>=mmin-lo_tol .AND. mean_mass<=mmax+hi_tol
END FUNCTION rain_cone

PURE LOGICAL FUNCTION graupel_cone(q,v,rho_min,rho_max)
REAL(real32), INTENT(IN) :: q,v
REAL(real64), INTENT(IN) :: rho_min,rho_max
REAL(real64) :: density
graupel_cone=.FALSE.
IF (q==0.0_real32 .AND. v==0.0_real32) THEN
  graupel_cone=.TRUE.; RETURN
ENDIF
IF (q<=0.0_real32 .OR. v<=0.0_real32) RETURN
density=REAL(q,real64)/REAL(v,real64)
! ProgB_param tests QG/BG against exact [100,900] bounds; match that
! consumer predicate so an admitted endpoint cannot fail on the next call.
graupel_cone=ieee_is_finite(density) .AND. &
             density>=rho_min .AND. density<=rho_max
END FUNCTION graupel_cone

END SUBROUTINE pr85_kdm6_rain_freezing_packet


SUBROUTINE pr85_kdm6_psd_bound_number(q,rho,lambda,lambda_min,lambda_max,pid,exponent,side, &
species,stage,cell_i,lat,k,number_before,legacy_available,trace,ledger_unit,native_number,directed_number, &
exact_min,exact_max,valid)
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
REAL, INTENT(IN) :: q,rho,lambda,lambda_min,lambda_max,pid,exponent,number_before
INTEGER, INTENT(IN) :: side,cell_i,lat,k,ledger_unit
CHARACTER(*), INTENT(IN) :: species,stage
LOGICAL, INTENT(OUT) :: legacy_available
LOGICAL, INTENT(IN) :: trace
REAL, INTENT(OUT) :: native_number,directed_number
REAL(8), INTENT(OUT) :: exact_min,exact_max
LOGICAL, INTENT(OUT) :: valid
REAL(8) :: q64,rho64,lambda64,lmin64,lmax64,pid64,exp64
REAL(8) :: native_product,native_power,native_predivide,native_exact
REAL(8) :: huge32_safe,storage_correction,native_delta
REAL :: rounded_bound
INTEGER :: io_status

valid=.FALSE.
legacy_available=.FALSE.
native_number=number_before
directed_number=number_before
exact_min=0.0D0
exact_max=0.0D0
IF (.NOT.ALL(ieee_is_finite([q,rho,lambda,lambda_min,lambda_max,pid,exponent,number_before]))) RETURN
IF (q<=0.0 .OR. rho<=0.0 .OR. lambda<=0.0 .OR. lambda_min<=0.0 .OR. &
    lambda_max<lambda_min .OR. pid<=0.0 .OR. exponent/=3.0 .OR. (side/=1 .AND. side/=2)) RETURN
IF (side==1 .AND. lambda/=lambda_min) RETURN
IF (side==2 .AND. lambda/=lambda_max) RETURN
q64=DBLE(q); rho64=DBLE(rho); lambda64=DBLE(lambda)
lmin64=DBLE(lambda_min); lmax64=DBLE(lambda_max); pid64=DBLE(pid); exp64=DBLE(exponent)
! This operation order matches state_valid's R64 lambda-bound predicate.
exact_min=(rho64*lmin64**3)/pid64*q64
exact_max=(rho64*lmax64**3)/pid64*q64
IF (.NOT.ALL(ieee_is_finite([exact_min,exact_max]))) RETURN
IF (exact_min<=0.0D0 .OR. exact_max<exact_min) RETURN
IF (exact_min>DBLE(HUGE(1.0)) .OR. exact_max>DBLE(HUGE(1.0))) RETURN
rounded_bound=REAL(MERGE(exact_min,exact_max,side==1))
IF (.NOT.ieee_is_finite(rounded_bound) .OR. rounded_bound<=0.0) RETURN
IF (side==1) THEN
  IF (DBLE(rounded_bound)<exact_min) rounded_bound=NEAREST(rounded_bound,1.0)
ELSE
  IF (DBLE(rounded_bound)>exact_max) rounded_bound=NEAREST(rounded_bound,-1.0)
ENDIF
IF (.NOT.ieee_is_finite(rounded_bound) .OR. rounded_bound<=0.0) RETURN
IF (DBLE(rounded_bound)<exact_min .OR. DBLE(rounded_bound)>exact_max) RETURN
! Preflight every REAL32 intermediate in the legacy source formula before evaluating it.
! If this reset cannot be represented by the existing REAL32 expression, fail closed.
native_product=rho64*q64
native_power=lambda64**exp64
native_predivide=native_product*native_power
native_exact=native_predivide/pid64
huge32_safe=DBLE(NEAREST(HUGE(1.0),-1.0))
directed_number=rounded_bound
IF (ALL(ieee_is_finite([native_product,native_power,native_predivide,native_exact])) .AND. &
    native_product<=huge32_safe .AND. native_power<=huge32_safe .AND. &
    native_predivide<=huge32_safe .AND. native_exact<=huge32_safe) THEN
  native_number=rho*q*lambda**exponent/pid
  legacy_available=.TRUE.
  storage_correction=DBLE(directed_number)-DBLE(native_number)
  native_delta=DBLE(native_number)-DBLE(number_before)
ELSE
  native_number=0.0
  storage_correction=0.0D0
  native_delta=0.0D0
ENDIF
valid=.TRUE.
IF (trace) THEN
  WRITE(ledger_unit,'(A,",",A,",",A,4(",",I0),1P,11(",",ES24.16E3),",",L1)',IOSTAT=io_status) &
       'PR85_KDM6_PSD_BOUNDARY',species,stage,cell_i,lat,k,side, &
       q,rho,lambda_min,lambda_max,number_before,native_number,directed_number, &
       native_delta,storage_correction,exact_min,exact_max,legacy_available
  IF (io_status/=0) ERROR STOP 'PR85 PSD boundary ledger write failed'
ENDIF
END SUBROUTINE pr85_kdm6_psd_bound_number
