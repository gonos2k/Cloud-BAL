"""Build a source-form rain-freezing to NG-consumer admission regression."""
from __future__ import annotations

import hashlib
import gzip
import re
import struct
from pathlib import Path


KDM6_SOURCE_SHA256 = "769cf33f7e6d59d46e2b31ec973a7d44cecce0b505fc18b0890b5b2a4ef2464f"
DEFAULT_KDM6_SOURCE = Path(
    "/var/tmp/pr87_followup_sources_20261019_v44/module_mp_kdm6.F"
)
T4_LEDGER_PATH = Path(
    "/var/tmp/pr87_followup_OFF_600s_v50_20261019/run/pr85_rain_freezing_budget.raw.gz"
)
T4_LEDGER_SHA256 = "b08e5104e51d0f5ecb21e94f39086093005b5f90f2266a5f2baea4ab8b935cb8"
T4_FAILURE_STATE = (
    "36CCE783 328B8E77 2EA445FC 33A266F0 300669B5 "
    "4B847172 46897685 3E2702A7 2B19B507 4384C1BD 3F23D06F"
)
PR89_DECLARATIONS = """   real(kind=8) :: pr89_rf_gamma
   real(kind=8) :: pr89_rf_rain_min,pr89_rf_rain_max
   integer :: pr89_rf_attempt,pr89_rf_failure_reason
   logical :: pr89_rf_next_valid
"""


def actual_t4_event() -> dict[str, float]:
    """Read and validate the unique recorded T4 freezing event used by the harness."""
    ledger = T4_LEDGER_PATH.read_bytes()
    digest = hashlib.sha256(ledger).hexdigest()
    if digest != T4_LEDGER_SHA256:
        raise ValueError(f"unexpected pinned T4 ledger hash: {digest}")
    rows = []
    for line in gzip.decompress(ledger).decode().splitlines():
        fields = line.split()
        if (len(fields) >= 26 and fields[0] == "PR85_RAIN_FREEZE" and
                fields[1:6] == ["26", "115", "18", "1", "TT"]):
            rows.append(fields)
    if len(rows) != 1:
        raise ValueError(f"expected one actual T4 packet ledger row, found {len(rows)}")
    row = rows[0]
    values = [float(value) for value in row[7:]]
    if float(row[6]) != 1.0:
        raise ValueError("T4 packet was not recorded with theta 1")
    event = {
        "mass": values[0], "number": values[1], "volume": values[2],
        "qr_before": values[9], "nr_before": values[10],
        "qg_before": values[11], "bg_before": values[12],
        "qr_after": values[13], "nr_after": values[14],
        "qg_after": values[15], "bg_after": values[16],
        "temperature": values[17], "temperature_after": values[18],
    }
    expected_after = ("2EA445FC", "3E2702A7", "300669B5", "2B19B507")
    for name, expected in zip(("qr_after", "nr_after", "qg_after", "bg_after"), expected_after):
        bits = struct.unpack("<I", struct.pack("<f", event[name]))[0]
        if bits != int(expected, 16):
            raise ValueError(f"T4 ledger {name} bits changed: {bits:08X}")
    return event


def _fortran_real64(value: float) -> str:
    return f"{value:.17e}_real64"


def connect_freezing_consumer(source: str) -> str:
    """Gate every staged rain-freezing endpoint with the actual next NG predicate."""
    digest = hashlib.sha256(source.encode()).hexdigest()
    if digest != KDM6_SOURCE_SHA256:
        raise ValueError(f"unexpected pinned KDM6 source hash: {digest}")
    if "pr89_rf_next_valid" in source:
        raise ValueError("PR89 next-consumer admission is already installed")

    declaration_anchor = "   external :: pr85_kdm6_rain_freezing_packet\n"
    if source.count(declaration_anchor) != 1:
        raise ValueError("pinned rain-freezing helper declaration anchor is missing or ambiguous")
    transformed = source.replace(
        declaration_anchor,
        declaration_anchor + PR89_DECLARATIONS,
        1,
    )

    private_anchor = "    private :: kdm6_progb_density_pair_valid\n"
    if transformed.count(private_anchor) != 1:
        raise ValueError("pinned NG predicate visibility anchor is missing or ambiguous")
    transformed = transformed.replace(
        private_anchor,
        private_anchor + "    private :: kdm6_rain_ng_pair_valid\n",
        1,
    )
    validator_start = transformed.index("subroutine kdm6_rain_process_state_valid(")
    validator_end = transformed.index("end subroutine kdm6_rain_process_state_valid", validator_start)
    validator = transformed[validator_start:validator_end]
    rain_branch = """      if (q(3).eq.0.0) then
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
      elseif (q(3).le.0.0 .or. n(3).le.0.0) then
        if (present(failure_reason)) failure_reason=3
        return
      elseif (real(n(3),8).lt.rain_min*q(3) .or. real(n(3),8).gt.rain_max*q(3)) then
        if (present(failure_reason)) failure_reason=6
        return
      endif
"""
    if validator.count(rain_branch) != 1:
        raise ValueError("strict NG rain-pair branch is missing or ambiguous")
    validator = validator.replace(
        rain_branch,
        """      rain_pair_allowed=.false.
      if (present(allow_rain_number_at_zero)) &
          rain_pair_allowed=allow_rain_number_at_zero
      call kdm6_rain_ng_pair_valid(q(3),n(3),rain_min,rain_max, &
           present(allow_rain_number_at_zero),rain_pair_allowed, &
           rain_pair_valid_result,rain_reason)
      if (.not.rain_pair_valid_result) then
        if (present(failure_reason)) failure_reason=rain_reason
        return
      endif
""",
        1,
    )
    declaration = "      logical :: pair_only,ice_pending\n"
    if validator.count(declaration) != 1:
        raise ValueError("NG rain-pair local declaration anchor is missing or ambiguous")
    validator = validator.replace(
        declaration,
        "      logical :: pair_only,ice_pending,rain_pair_allowed,rain_pair_valid_result\n"
        "      integer :: rain_reason\n",
        1,
    )
    transformed = transformed[:validator_start] + validator + transformed[validator_end:]
    shared_helper = """    pure subroutine kdm6_rain_ng_pair_valid(q,n,rain_min,rain_max, &
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

"""
    validator_anchor = "subroutine kdm6_rain_process_state_valid("
    if transformed.count(validator_anchor) != 1:
        raise ValueError("strict NG state validator insertion anchor is missing or ambiguous")
    transformed = transformed.replace(validator_anchor, shared_helper + validator_anchor, 1)

    block_start = "              pr85_rf_qr_before=qrs(i,k,1)\n"
    block_end = "              open(newunit=pr85_rf_unit,file='pr85_rain_freezing_budget.raw', &"
    if transformed.count(block_start) != 1 or transformed.count(block_end) != 1:
        raise ValueError("pinned rain-freezing candidate block is missing or ambiguous")
    start = transformed.index(block_start)
    end = transformed.index(block_end, start)
    if end <= start:
        raise ValueError("pinned rain-freezing candidate block order changed")
    transformed = transformed[:start] + _NEXT_CONSUMER_BLOCK + transformed[end:]
    return transformed


_NEXT_CONSUMER_BLOCK = """              pr85_rf_qr_before=qrs(i,k,1)
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
"""


def _procedure(source: str, start_pattern: str, end_pattern: str) -> str:
    starts = list(re.finditer(start_pattern, source, flags=re.IGNORECASE | re.MULTILINE))
    if len(starts) != 1:
        raise ValueError(f"expected one source procedure for {start_pattern!r}, found {len(starts)}")
    start = starts[0].start()
    end = re.search(end_pattern, source[starts[0].end() :], flags=re.IGNORECASE | re.MULTILINE)
    if end is None:
        raise ValueError(f"source procedure end missing for {start_pattern!r}")
    return source[start : starts[0].end() + end.end()]


def extract_actual_consumer(source: str) -> str:
    """Extract actual NG procedures after hash-pinned PR89 predicate factoring."""
    digest = hashlib.sha256(source.encode()).hexdigest()
    if digest == KDM6_SOURCE_SHA256:
        source = connect_freezing_consumer(source)
    elif "subroutine kdm6_rain_ng_pair_valid" not in source:
        raise ValueError(f"unexpected KDM6 consumer source hash: {digest}")

    density = _procedure(
        source,
        r"^\s*pure\s+logical\s+function\s+kdm6_progb_density_pair_valid\s*\(",
        r"^\s*end\s+function\s+kdm6_progb_density_pair_valid\s*$",
    )
    rain_pair = _procedure(
        source,
        r"^\s*pure\s+subroutine\s+kdm6_rain_ng_pair_valid\s*\(",
        r"^\s*end\s+subroutine\s+kdm6_rain_ng_pair_valid\s*$",
    )
    validator = _procedure(
        source,
        r"^\s*subroutine\s+kdm6_rain_process_state_valid\s*\(",
        r"^\s*end\s+subroutine\s+kdm6_rain_process_state_valid\s*$",
    )
    return f"""module pr89_actual_consumer
 use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
 implicit none
 real, parameter :: PR85_ICE_NATIVE_INACTIVE_MAX = nearest(1.e-14,-1.0)
contains
{density}
{rain_pair}
{validator}
end module pr89_actual_consumer
"""


def regression_source(actual_source: str, helper_source: str) -> str:
    """Compose the transformed native call block with the pinned consumer/helper."""
    transformed = connect_freezing_consumer(actual_source)
    consumer = extract_actual_consumer(transformed)
    start = transformed.index("              pr85_rf_qr_before=qrs(i,k,1)\n")
    end = transformed.index(
        "              open(newunit=pr85_rf_unit,file='pr85_rain_freezing_budget.raw', &",
        start,
    )
    block = transformed[start:end]
    return consumer + "\n" + helper_source + "\n" + _block_regression(block, actual_t4_event())


def _block_regression(block: str, event: dict[str, float]) -> str:
    source = f"""program pr89_t4_consumer_regression
 use, intrinsic :: iso_fortran_env, only: real32,real64,int32
 use, intrinsic :: ieee_arithmetic, only: ieee_is_finite,ieee_value,ieee_quiet_nan
 use pr89_actual_consumer, only: PR85_ICE_NATIVE_INACTIVE_MAX, &
      kdm6_rain_ng_pair_valid,kdm6_progb_density_pair_valid, &
      kdm6_rain_process_state_valid
 implicit none
 real(real32) :: q(5),n(3),qout(5),nout(3),qbad(5),nbad(3),bg,t,rho,bgout,tout,bgbad,tbad
 real(real64) :: mass,nrequest
 logical :: accepted,base_valid,valid
 real(real64) :: fraction
 integer :: reason

 q=[bits('36CCE783'),bits('328B8E77'), &
    REAL(T4_QR_BEFORE,real32),bits('33A266F0'), &
    REAL(T4_QG_BEFORE,real32)]
 n=[bits('4B847172'),bits('46897685'), &
    REAL(T4_NR_BEFORE,real32)]
 bg=REAL(T4_BG_BEFORE,real32)
 t=bits('4384C1BD'); rho=bits('3F23D06F')
 mass=T4_MASS
 nrequest=T4_NUMBER
 write(*,'(a)') 'T4_SOURCE_CONTEXT timestep=4 cell=(26,115,18) loop=1 state='// &
      '36CCE783 328B8E77 2EA445FC 33A266F0 300669B5 4B847172 '// &
      '46897685 3E2702A7 2B19B507 4384C1BD 3F23D06F'
 write(*,'(a,2(1x,es24.16))') 'T4_INTEGRATED_PRIMITIVES',mass,nrequest
 call run_source_block(q,n,bg,t,rho,mass,nrequest,accepted,base_valid,fraction, &
                       qout,nout,bgout,tout,reason)
 if (accepted .or. .not.base_valid .or. fraction/=0.0_real64) &
      error stop 'T4 packet was not explicitly deferred'
 if (qout(3)/=q(3) .or. nout(3)/=n(3) .or. qout(5)/=q(5) .or. &
     bgout/=bg .or. tout/=bits('4384C1BD')) &
      error stop 'T4 deferral failed full-state rollback'
 if (reason/=6) error stop 'T4 source trial did not report strict NG reason 6'
 write(*,'(a,i0)') 'T4_EXPLICIT_DEFERRAL next_reason=',reason
 write(*,'(a)') 'T4_TRANSACTION_ROLLBACK QR NR QG BG T approved=0'

 ! Zero proposals are a valid no-op and preserve all stored source fields.
 q(3)=1.0e-4_real32; n(3)=120.0_real32; q(5)=1.0e-4_real32
 bg=1.25e-7_real32; t=265.0_real32; rho=1.2_real32
 call run_source_block(q,n,bg,t,rho,0.0_real64,0.0_real64,accepted,base_valid, &
      fraction,qout,nout,bgout,tout,reason)
 if (.not.accepted .or. .not.base_valid .or. fraction/=0.0_real64) &
      error stop 'zero packet semantics changed'
 if (any(qout/=q) .or. any(nout/=n)) error stop 'zero packet changed moments'

 ! A separate interior state commits a complete, nonzero packet.
 call run_source_block(q,n,bg,t,rho,1.0e-8_real64,1.2e-2_real64,accepted, &
      base_valid,fraction,qout,nout,bgout,tout,reason)
 if (.not.accepted .or. .not.base_valid .or. fraction<=0.0_real64) &
      error stop 'valid nonzero packet was not committed'
 call validate_state(qout,nout,bgout,tout,rho,valid,reason)
 if (.not.valid .or. reason/=0) error stop 'valid committed endpoint failed next NG predicate'
 write(*,'(a)') 'VALID_NONZERO_PACKET_NEXT_NG PASS'
 qbad=qout; nbad=nout
 qbad(1)=1.0e-4_real32; nbad(1)=1.0_real32
 call validate_state(qbad,nbad,bgout,tout,rho,valid,reason)
 if (valid .or. reason/=5) error stop 'invalid cloud state was hidden after rain-pair pass'
 qbad=qout; nbad=nout; bgbad=qbad(5)/1000.0_real32
 call validate_state(qbad,nbad,bgbad,tout,rho,valid,reason)
 if (valid .or. reason/=9) error stop 'invalid graupel density was hidden after rain-pair pass'
 call run_source_block(qout,nout,bgbad,tout,rho,0.0_real64,0.0_real64,accepted, &
      base_valid,fraction,qbad,nbad,bgout,tbad,reason)
 if (accepted .or. base_valid .or. reason/=9) &
      error stop 'source admission hid reason 9 for a valid rain and invalid G pair'
 write(*,'(a)') 'VALID_RAIN_INVALID_G rejected reason=9'

 ! An invalid initial state is exposed as an invalid base, never relabeled no-op.
 t=0.0_real32
 call run_source_block(q,n,bg,t,rho,0.0_real64,0.0_real64,accepted,base_valid, &
      fraction,qout,nout,bgout,tout,reason)
 if (accepted .or. base_valid .or. reason/=8) error stop 'invalid base was hidden'
 write(*,'(a,i0)') 'WRONG_BASE_NEXT_NG_REASON ',reason
 t=ieee_value(t,ieee_quiet_nan)
 call run_source_block(q,n,bg,t,rho,0.0_real64,0.0_real64,accepted,base_valid, &
      fraction,qout,nout,bgout,tout,reason)
 if (accepted .or. base_valid .or. reason/=8) error stop 'nonfinite thermal base was hidden'
 write(*,'(a)') 'NONFINITE_THERMAL_BASE safely rejected'
 write(*,'(a)') 'PR89 transformed source block cases PASS'
contains
 function bits(hex) result(value)
   character(len=8),intent(in) :: hex
   real(real32) :: value
   integer(int32) :: word
   read(hex,'(z8)') word
   value=transfer(word,0.0_real32)
 end function bits

 subroutine validate_state(qstate,nstate,bgstate,temp,density,ok,why)
   real(real32),intent(in) :: qstate(5),nstate(3),bgstate,temp,density
   logical,intent(out) :: ok
   integer,intent(out) :: why
   call kdm6_rain_process_state_valid(qstate,nstate,bgstate,temp,density, &
       12566.37109375,1.0000000036274937e-15,10.0,9.9999997171806854e-10,3.0, &
       961.0,35000.0,100.0,900.0,523.5988,3.0,12000.0,500000.0, &
       1570.796,3.0,9080.0,1820000.0,ok,.false., &
       ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
       failure_reason=why,ice_sublimation_pending=.false.)
 end subroutine validate_state

 subroutine run_source_block(qin,nin,bgin,tin,rhoin,prequest,nrequest,ok,baseok,theta, &
       qresult,nresult,bgresult,tresult,why)
   real(real32),intent(in) :: qin(5),nin(3),bgin,tin,rhoin
   real(real64),intent(in) :: prequest,nrequest
   logical,intent(out) :: ok,baseok
   real(real64),intent(out) :: theta
   real(real32),intent(out) :: qresult(5),nresult(3),bgresult,tresult
   integer,intent(out) :: why
   integer :: i,k
   real(real32) :: qci(1,1,2),nci(1,1,3),qrs(1,1,3),nrs(1,1,3),brs(1,1),t(1,1)
   real(real32) :: dry_carrier_density(1,1),cpm(1,1),denr,xlf
   real(real64) :: pfrzdtr,nfrzdtr
   real(real32) :: pidnr,qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax
   real(real32) :: pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi,lamdaimin,lamdaimax
   logical :: rain_full_evap_pending(1,1),ice_full_sublimation_pending(1,1)
   real(real64) :: pr85_rf_mass_request,pr85_rf_number_request,pr85_rf_volume_request
   real(real64) :: pr85_rf_mass_approved,pr85_rf_number_approved,pr85_rf_volume_approved
   real(real64) :: pr85_rf_fraction,pr85_rf_t_candidate
   real(real64) :: pr89_rf_rain_min,pr89_rf_rain_max
   real(real32) :: pr85_rf_qr_before,pr85_rf_nr_before,pr85_rf_qg_before,pr85_rf_bg_before
   real(real32) :: pr85_rf_t_before,pr85_rf_qr_after,pr85_rf_nr_after,pr85_rf_qg_after
   real(real32) :: pr85_rf_bg_after,pr85_rf_t_after
   logical :: pr85_rf_base_valid,pr85_rf_accepted
   real(real64) :: pr89_rf_gamma
   integer :: pr89_rf_attempt,pr89_rf_failure_reason
   logical :: pr89_rf_next_valid
   external :: pr85_kdm6_rain_freezing_packet
   i=1; k=1
   qci(1,1,:) = qin(1:2); nci(1,1,:) = [nin(1:2),0.0_real32]
   qrs(1,1,:) = [qin(3),qin(4),qin(5)]
   nrs(1,1,:) = [nin(3),0.0_real32,0.0_real32]
   brs=bgin; t=tin; dry_carrier_density=rhoin
   pfrzdtr=prequest; nfrzdtr=nrequest; denr=1000.0_real32
   xlf=333700.0_real32; cpm=1004.0_real32
   pidnr=12566.37109375; qmin=1.0000000036274937e-15; ncmin=10.0
   qcrmin=9.9999997171806854e-10; dmr=3.0; lamdarmin=961.0; lamdarmax=35000.0
   pidnc=523.5988; dmc=3.0; lamdacmin=12000.0; lamdacmax=500000.0
   pidni=1570.796; dmi=3.0; lamdaimin=9080.0; lamdaimax=1820000.0
   rain_full_evap_pending=.false.; ice_full_sublimation_pending=.false.
{block}
   ok=pr85_rf_accepted; baseok=pr85_rf_base_valid; theta=pr85_rf_fraction
   qresult=[qci(1,1,1),qci(1,1,2),qrs(1,1,1),qrs(1,1,2),qrs(1,1,3)]
   nresult=[nci(1,1,1),nci(1,1,2),nrs(1,1,1)]
   bgresult=brs(1,1); tresult=t(1,1); why=pr89_rf_failure_reason
 end subroutine run_source_block
end program pr89_t4_consumer_regression
"""
    replacements = {
        "T4_QR_BEFORE": _fortran_real64(event["qr_before"]),
        "T4_NR_BEFORE": _fortran_real64(event["nr_before"]),
        "T4_QG_BEFORE": _fortran_real64(event["qg_before"]),
        "T4_BG_BEFORE": _fortran_real64(event["bg_before"]),
        "T4_MASS": _fortran_real64(event["mass"]),
        "T4_NUMBER": _fortran_real64(event["number"]),
    }
    for marker, value in replacements.items():
        source = source.replace(marker, value)
    return source
