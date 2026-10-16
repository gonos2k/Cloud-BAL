
program test_v39_ice_cap_order
  use, intrinsic :: iso_fortran_env, only: int32
  implicit none
  real :: q,n,dt,full,raw,result_rate,legacy_rate,sat,sup
  real :: q_before,n_before,raw_saved,capped_saved,q_saved,n_saved
  real :: pidep(1,1),qci(1,1,2),nci(1,1,2),dtcld,satdt,supice,prevp(1,1),pinud(1,1)
  real :: ice_sublimation_raw_pidep(1,1),ice_sublimation_capped_pidep(1,1)
  real :: ice_sublimation_q_before(1,1),ice_sublimation_n_before(1,1)
  real :: rain_q_after(5),rain_n_after(3),pr87_ice_sublimation_n_preclear
  real :: pr87_ice_sublimation_dn,pr87_ice_raw_pidep_before_caps
  logical :: ice_full_sublimation_pending(1,1)
  integer :: ice_sublimation_event_count(1,1),pr87_ice_sublimation_extinctions,i,k,case_id
  integer(int32) :: rate_bits

  q=4.2936549e-15; n=8.823875; dt=20.0; full=-(q/dt)
  do case_id=1,4
    select case(case_id)
    case(1) ! Raw tendency is more negative; first cap approves full removal.
      raw=2.0*full; sat=4.0*full; sup=2.0*full
    case(2) ! Raw tendency is exactly the full-removal rate.
      raw=full; sat=4.0*full; sup=2.0*full
    case(3) ! Thermodynamic cap reduces removal below full extinction.
      raw=2.0*full; sat=full; sup=0.25*full
    case(4) ! Raw tendency remains partial after both caps.
      raw=0.5*full; sat=4.0*full; sup=2.0*full
    end select
    call apply_caps(raw,q,n,dt,sat,sup,result_rate,ice_full_sublimation_pending(1,1), &
         raw_saved,capped_saved,q_saved,n_saved,ice_sublimation_event_count(1,1), &
         rain_n_after(2),pr87_ice_sublimation_dn,pr87_ice_sublimation_extinctions)
    legacy_rate=legacy_caps(raw,q,dt,sat,sup)
    rate_bits=transfer(result_rate,rate_bits)
    if (rate_bits.ne.transfer(legacy_rate,rate_bits)) error stop 'cap rate changed from native formula'
    select case(case_id)
    case(1,2)
      if (.not.ice_full_sublimation_pending(1,1)) error stop 'approved full cap was not marked'
      if (raw_saved.ne.raw .or. capped_saved.ne.full) error stop 'raw/capped ledger mismatch'
      if (q_saved.ne.q .or. n_saved.ne.n) error stop 'pre-cap state ledger mismatch'
      if (ice_sublimation_event_count(1,1).ne.1) error stop 'approved event count mismatch'
      if (rain_n_after(2).ne.n) error stop 'positive QI incorrectly cleared NI'
      call apply_endpoint(0.0,n,.true.,rain_n_after(2),pr87_ice_sublimation_dn, &
           pr87_ice_sublimation_extinctions)
      if (rain_n_after(2).ne.0.0 .or. pr87_ice_sublimation_dn.ne.-n) &
        error stop 'zero-mass full-extinction commit changed'
    case(3,4)
      if (ice_full_sublimation_pending(1,1)) error stop 'non-full capped rate was marked'
      if (ice_sublimation_event_count(1,1).ne.0) error stop 'non-full event was counted'
      if (raw_saved.ne.0.0 .or. capped_saved.ne.0.0) error stop 'unapproved event entered ledger'
    end select
  enddo
  print '(a)', 'PR87 V39 capped sublimation cases PASS'
contains
  real function legacy_caps(r,qin,dtin,satin,supin)
    real,intent(in)::r,qin,dtin,satin,supin
    legacy_caps=max(r,-qin/dtin)
    legacy_caps=max(max(legacy_caps,satin/2.0),supin)
  end function legacy_caps

  subroutine apply_caps(r,qin,nin,dtin,satin,supin,rout,pending,rawout,capout,qout,nout, &
                        events,ncommit,dn,extinctions)
    real,intent(in)::r,qin,nin,dtin,satin,supin
    real,intent(out)::rout,rawout,capout,qout,nout,ncommit,dn
    logical,intent(out)::pending
    integer,intent(out)::events,extinctions
    real::pidep(1,1),qci(1,1,2),nci(1,1,2),dtcld,satdt,supice,prevp(1,1),pinud(1,1)
    real::ice_sublimation_raw_pidep(1,1),ice_sublimation_capped_pidep(1,1)
    real::ice_sublimation_q_before(1,1),ice_sublimation_n_before(1,1)
    real::rain_q_after(5),rain_n_after(3),pr87_ice_sublimation_n_preclear
    real::pr87_ice_sublimation_dn,pr87_ice_raw_pidep_before_caps
    logical::ice_full_sublimation_pending(1,1),rain_full_evap_pending(1,1)
    integer::ice_sublimation_event_count(1,1),pr87_ice_sublimation_extinctions,i,k
    i=1;k=1;dtcld=dtin;satdt=satin;supice=supin;prevp=0.0;pinud=0.0
    pidep(1,1)=r;qci=0.0;nci=0.0;qci(1,1,2)=qin;nci(1,1,2)=nin
    ice_sublimation_raw_pidep=0.0;ice_sublimation_capped_pidep=0.0
    ice_sublimation_q_before=0.0;ice_sublimation_n_before=0.0
    ice_sublimation_event_count=0;ice_full_sublimation_pending=.false.
                  if(pidep(i,k).lt.0.) then



                pr87_ice_raw_pidep_before_caps=pidep(i,k)
                pidep(i,k) = max(pidep(i,k),-(qci(i,k,2))/dtcld)
                pidep(i,k) = max(max(pidep(i,k),(satdt)/2),supice)
                if (pidep(i,k).eq.-(qci(i,k,2))/dtcld) then
                  ice_full_sublimation_pending(i,k) = .true.
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

    if (nci(1,1,2).ne.nin) error stop 'cap fragment changed NI'
    rout=pidep(1,1);pending=ice_full_sublimation_pending(1,1)
    rawout=ice_sublimation_raw_pidep(1,1);capout=ice_sublimation_capped_pidep(1,1)
    qout=ice_sublimation_q_before(1,1);nout=ice_sublimation_n_before(1,1)
    events=ice_sublimation_event_count(1,1)
    rain_q_after=0.0;rain_n_after=0.0;rain_q_after(2)=qin;rain_n_after(2)=nin
    rain_full_evap_pending(1,1)=.false.
                pr87_ice_sublimation_extinctions=0
            pr87_ice_sublimation_n_preclear=rain_n_after(2)
            pr87_ice_sublimation_dn=0.0
            if (ice_full_sublimation_pending(i,k) .and. rain_q_after(2).eq.0.0) then
              if (rain_n_after(2).gt.0.0) then
                pr87_ice_sublimation_extinctions=1
                pr87_ice_sublimation_dn=-rain_n_after(2)
              endif
              rain_n_after(2)=0.0
            endif

    ncommit=rain_n_after(2)
  end subroutine apply_caps

  subroutine apply_endpoint(qin,nin,pending,nout,dnout,extinctions)
    real,intent(in)::qin,nin
    logical,intent(in)::pending
    real,intent(out)::nout,dnout
    integer,intent(out)::extinctions
    real::rain_q_after(5),rain_n_after(3),pr87_ice_sublimation_n_preclear
    real::pr87_ice_sublimation_dn
    logical::ice_full_sublimation_pending(1,1),rain_full_evap_pending(1,1)
    integer::pr87_ice_sublimation_extinctions
    rain_q_after=0.0;rain_n_after=0.0;rain_q_after(2)=qin;rain_n_after(2)=nin
    ice_full_sublimation_pending=.false.;ice_full_sublimation_pending(1,1)=pending
    rain_full_evap_pending=.false.
    i=1;k=1
                pr87_ice_sublimation_extinctions=0
            pr87_ice_sublimation_n_preclear=rain_n_after(2)
            pr87_ice_sublimation_dn=0.0
            if (ice_full_sublimation_pending(i,k) .and. rain_q_after(2).eq.0.0) then
              if (rain_n_after(2).gt.0.0) then
                pr87_ice_sublimation_extinctions=1
                pr87_ice_sublimation_dn=-rain_n_after(2)
              endif
              rain_n_after(2)=0.0
            endif

    nout=rain_n_after(2);dnout=pr87_ice_sublimation_dn
    extinctions=pr87_ice_sublimation_extinctions
  end subroutine apply_endpoint
end program test_v39_ice_cap_order
