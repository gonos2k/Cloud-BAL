#!/usr/bin/env python3
"""Receipt-bound production-source test for warm rain output admission."""
from __future__ import annotations

import hashlib
import gzip
import json
from pathlib import Path
import re
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr90_warm_rain_output import (  # noqa: E402
    C5_KDM6_SOURCE_SHA256,
    add_unreconstructed_rain_output_check,
    extract_warm_process_setup,
    extract_warm_trial_commit,
)

C5_SOURCE = Path("/var/tmp/pr89_native_build_20261019_c5/source/overrides/module_mp_kdm6.F")
D1_EM = Path("/var/tmp/pr90_native_build_diag_20261019/source/overrides/module_em.F")
D1_EM_SHA256 = "090b9329c817f52f0fba45d6d97f93a6bdb35adc5f46cfed0ae198b15401819b"
D2_EVIDENCE = ROOT / "docs/evidence/pr90_rain_roundtrip_20261019/d2"
D2_PACKET = D2_EVIDENCE / "t7_target_packet.json"
D2_PACKET_SHA256 = "931aa8d6990aa32cb40d191dc4c55feb8c04657ea5c947fca36eaa7722706e03"
D2_BUILD_RECEIPT = D2_EVIDENCE / "build_receipt.json"
D2_RUN_RECEIPT = D2_EVIDENCE / "run_receipt.json"
HELPER = ROOT / "tools/pr87_rain_public_store.f90"


def extract_block(source: str, start_pattern: str, end_pattern: str) -> str:
    start = re.search(start_pattern, source, re.I | re.M)
    if not start:
        raise AssertionError(f"missing source block: {start_pattern}")
    end = re.search(end_pattern, source[start.start():], re.I | re.M)
    if not end:
        raise AssertionError(f"unterminated source block: {start_pattern}")
    return source[start.start():start.start() + end.end()]


def core_module(source: str) -> str:
    return extract_block(
        source,
        r"^\s*module\s+cloud_bal_joint_transport\s*$",
        r"^\s*end\s+module\s+cloud_bal_joint_transport\s*$",
    )


def source_bound_fixture(transformed: str) -> str:
    strict_ng = extract_block(
        transformed, r"^\s*pure\s+subroutine\s+kdm6_rain_ng_pair_valid\s*\(",
        r"^\s*end\s+subroutine\s+kdm6_rain_ng_pair_valid\s*$",
    )
    progb = extract_block(
        transformed, r"^\s*pure\s+logical\s+function\s+kdm6_progb_density_pair_valid\s*\(",
        r"^\s*end\s+function\s+kdm6_progb_density_pair_valid\s*$",
    )
    state = extract_block(
        transformed, r"^\s*subroutine\s+kdm6_rain_process_state_valid\s*\(",
        r"^\s*end\s+subroutine\s+kdm6_rain_process_state_valid\s*$",
    )
    output_check = extract_block(
        transformed, r"^\s*logical\s+function\s+kdm6_unreconstructed_rain_output_valid\s*\(",
        r"^\s*end\s+function\s+kdm6_unreconstructed_rain_output_valid\s*$",
    )
    module = f"""module pr90_warm_output_test
  use iso_fortran_env, only: real32,real64,int32
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  real, parameter :: PR85_ICE_NATIVE_INACTIVE_MAX=nearest(1.e-14,-1.0)
contains
{progb}
{strict_ng}
{state}
{output_check}
end module pr90_warm_output_test
"""
    program = r"""program test_pr90_warm_output
  use iso_fortran_env, only: real32,real64,int32
  use pr90_warm_output_test
  implicit none
  real(real32) :: qd1,nd1,qd2_before,qd2_after,rho,pidnr,power,lmin,lmax,qcrmin,nrmin
  real(real32) :: q(5),n(3),qfixed,nfixed,dq,dn,qtrial,ntrial,qgtrial
  real(real32) :: bg,t,qv,bgdelta,qgdelta,tdelta,qvdelta,alpha,bgtrial,ttrial
  real(real32) :: qsave,nsave,bgsave,tsave,qvsave
  real(real64) :: rmin,rmax
  integer :: reason,retry
  logical :: state_ok,output_ok,found

  qd1=transfer(int(z'308D0490',int32),0.0_real32)
  nd1=transfer(int(z'38AB5008',int32),0.0_real32)
  qd2_before=transfer(int(z'308D048E',int32),0.0_real32)
  qd2_after=transfer(int(z'308D0490',int32),0.0_real32)
  rho=transfer(int(z'3F904AFD',int32),0.0_real32)
  pidnr=transfer(int(z'4644597C',int32),0.0_real32)
  power=transfer(int(z'40400000',int32),0.0_real32)
  lmin=transfer(int(z'44704000',int32),0.0_real32)
  lmax=transfer(int(z'4708B800',int32),0.0_real32)
  qcrmin=1.0e-9_real32; nrmin=1.0e-2_real32

  q=[1.0e-4_real32,1.0e-5_real32,qd1,0.0_real32,1.0e-6_real32]
  n=[1.0e-5_real32,1.0e-6_real32,nd1]
  bg=5.0e-9_real32; t=270.0_real32
  call check_state(.true.,.false.,state_ok,reason)
  if (.not.state_ok) error stop 'legacy pair-only gate rejected exact D1 state'
  if (kdm6_unreconstructed_rain_output_valid(qd1,nd1,rho,pidnr,power,lmin,lmax, &
       qcrmin,nrmin)) error stop 'exact D1 endpoint passed the new output check'
  if (.not.kdm6_unreconstructed_rain_output_valid(qd2_before,nd1,rho,pidnr,power,lmin,lmax, &
       qcrmin,nrmin)) error stop 'D2 captured base pair failed the output preview'
  if (kdm6_unreconstructed_rain_output_valid(qd2_after,nd1,rho,pidnr,power,lmin,lmax, &
       qcrmin,nrmin)) error stop 'D2 old warm endpoint passed the output preview'
  rmin=real(rho,8)*real(lmin,8)**real(power,8)/real(pidnr,8)
  rmax=real(rho,8)*real(lmax,8)**real(power,8)/real(pidnr,8)
  call kdm6_rain_ng_pair_valid(qd1,nd1,rmin,rmax,.false.,.false.,output_ok,reason)
  if (output_ok .or. reason /= 6) error stop 'shared strict NG did not reject D1'

  ! Helper feasibility only: a nonzero Q/N increment reaches D1's rejected
  ! endpoint, while a smaller endpoint passes the output preview. This does not
  ! model the production coupled warm packet or its commit block.
  qfixed=qd1*0.99_real32
  nfixed=real(rmin*real(qfixed,8)*1.001d0,real32)
  dq=qd1-qfixed; dn=nd1-nfixed
  qgdelta=1.0e-7_real32; bgdelta=qgdelta/200.0_real32
  tdelta=-1.0_real32; qvdelta=1.0e-3_real32
  qsave=qfixed; nsave=nfixed; bgsave=bg; tsave=270.0_real32; qvsave=0.01_real32
  qtrial=qfixed+dq; ntrial=nfixed+dn
  if (qtrial /= qd1 .or. ntrial /= nd1) error stop 'full packet misses exact D1 endpoint'
  if (kdm6_unreconstructed_rain_output_valid(qtrial,ntrial,rho,pidnr,power,lmin,lmax, &
       qcrmin,nrmin)) error stop 'old full packet endpoint was accepted'
  if (qfixed /= qsave .or. nfixed /= nsave .or. bg /= bgsave .or. &
      t /= tsave .or. qvsave /= 0.01_real32) error stop 'rejected full packet changed base state'
  found=.false.; alpha=1.0_real32
  do retry=0,56
    if (retry > 0) then
      if (retry <= 32) then
        alpha=nearest(alpha,-1.0_real32)
      else
        alpha=0.5_real32*alpha
      endif
    endif
    qtrial=qfixed+alpha*dq
    ntrial=nfixed+alpha*dn
    bgtrial=bg+alpha*bgdelta
    ttrial=t+alpha*tdelta
    qgtrial=q(5)+alpha*qgdelta
    call check_state(.true.,.false.,state_ok,reason,bgarg=bgtrial, &
         temperaturearg=ttrial,qgraupelarg=qgtrial)
    if (state_ok) state_ok=kdm6_unreconstructed_rain_output_valid( &
         qtrial,ntrial,rho,pidnr,power,lmin,lmax,qcrmin,nrmin)
    if (state_ok) then
      found=.true.
      exit
    endif
  enddo
  if (.not.found .or. alpha <= 0.0_real32 .or. alpha >= 1.0_real32) &
    error stop 'warm retry did not retain a smaller positive packet'
  call kdm6_rain_ng_pair_valid(qtrial,ntrial,rmin,rmax,.false.,.false.,output_ok,reason)
  if (.not.output_ok) error stop 'accepted partial packet failed strict NG'
  if (.not.kdm6_unreconstructed_rain_output_valid(qtrial,ntrial,rho,pidnr,power,lmin,lmax, &
       qcrmin,nrmin)) error stop 'accepted partial packet failed public round trip'
  bg=bgtrial; t=ttrial; qv=qvsave+alpha*qvdelta; q(5)=qgtrial
  if (qtrial == qsave .or. ntrial == nsave) &
    error stop 'accepted helper-feasibility endpoint did not retain positive Q/N'

  ! Cutoff/orphan flags and the source-reconstructed active branch remain the
  ! responsibility of the unchanged state validator; the new gate is neutral.
  if (.not.kdm6_unreconstructed_rain_output_valid(0.0_real32,1.0e-5_real32, &
       rho,pidnr,power,lmin,lmax,qcrmin,nrmin)) error stop 'cutoff path was changed'
  call check_state(.true.,.false.,state_ok,reason,qrain=0.0_real32,nrain=1.0e-5_real32)
  if (state_ok) error stop 'orphan rain passed without pending permission'
  call check_state(.true.,.true.,state_ok,reason,qrain=0.0_real32,nrain=1.0e-5_real32)
  if (.not.state_ok) error stop 'pending rain orphan control changed'
  if (.not.kdm6_unreconstructed_rain_output_valid(qd1,nrmin,rho,pidnr,power,lmin,lmax, &
       qcrmin,nrmin)) error stop 'stage-3 active branch was changed'
  print '(a,1x,es12.4,1x,a)', 'PR90_WARM_OUTPUT_HELPER alpha=',alpha,'PASS'

contains
  subroutine check_state(pair_only,allow_orphan,valid,failure,qrain,nrain,bgarg,temperaturearg,qgraupelarg)
    logical, intent(in) :: pair_only,allow_orphan
    logical, intent(out) :: valid
    integer, intent(out) :: failure
    real(real32), intent(in), optional :: qrain,nrain,bgarg,temperaturearg,qgraupelarg
    real(real32) :: qv(5),nv(3)
    real(real32) :: bgvalue,tvalue
    qv=[1.0e-4_real32,1.0e-5_real32,qd1,0.0_real32,1.0e-6_real32]
    nv=[1.0e-5_real32,1.0e-6_real32,nd1]
    bgvalue=bg; tvalue=270.0_real32
    if (present(qrain)) qv(3)=qrain
    if (present(nrain)) nv(3)=nrain
    if (present(qgraupelarg)) qv(5)=qgraupelarg
    if (present(bgarg)) bgvalue=bgarg
    if (present(temperaturearg)) tvalue=temperaturearg
    call kdm6_rain_process_state_valid(qv,nv,bgvalue,tvalue,rho,pidnr, &
         1.0e-12_real32,1.0e-12_real32,qcrmin,power,lmin,lmax,100.0_real32,900.0_real32, &
         523.5988_real32,3.0_real32,12000.0_real32,500000.0_real32, &
         1.0_real32,3.0_real32,1.0_real32,2.0_real32,valid, &
         allow_rain_number_at_zero=allow_orphan,consumer_pair_only=pair_only, &
         failure_reason=failure)
  end subroutine check_state
end program test_pr90_warm_output
"""
    return module + program


def add_d2_production_block(fixture: str, source: str, packet: dict[str, object]) -> str:
    """Insert the captured D2 inputs into the exact transformed warm block."""
    fields = packet["warm_fields"]
    state_before = next(row for row in packet["trace_records"]
                        if row["stage"] == "WARM_BEFORE_COMMIT")["state_hex32"]
    state_after = next(row for row in packet["trace_records"]
                       if row["stage"] == "WARM_AFTER_COMMIT")["state_hex32"]
    rate_fields = fields["postcap_primitive_rates"]
    params = fields["parameters"]
    process_setup = extract_warm_process_setup(source).replace(
        "rain_warm_xlf=xls-xl(i,k)", "rain_warm_xlf=xlf_input"
    )
    trial_commit = extract_warm_trial_commit(source)

    def f32(bits: str) -> str:
        return f"transfer(int(z'{bits}',int32),0.0_real32)"

    def as_hex(group: str, name: str) -> str:
        return fields[group][name]["hex32"]

    rates = ("praut", "pracw", "paacw", "nraut", "nccol", "nracw", "naacw", "prevp",
             "pseml", "pgeml", "psevp", "pgacs", "pgevp", "nrcol", "nseml", "ngeml")
    rate_init = "\n".join(
        f"    {name}(i,k)={f32(rate_fields[f'rate_{idx:02d}']['hex32'])}"
        for idx, name in enumerate(rates, 1)
    )
    sub_start = fixture.rindex("contains\n  subroutine check_state")
    fixture = fixture[:sub_start] + "contains\n" + f"""  subroutine run_d2_packet(pending,final_state)
    logical,intent(in) :: pending
    real(real32),intent(out) :: final_state(13)
    integer,parameter :: i=193,k=4,PROGB_PSD_ACTIVE=1,PROGB_ABSENT=0
    integer :: progb_status(193,4),rain_warm_retry,pr85_warm_ios,pr85_warm_unit,lat,loop
    integer :: rain_warm_search_status
    real(real32) :: dtcld,dry_carrier_density(193,4),cpm(193,4),xl(193,4),xlf_input,rhox(193,4)
    real(real32) :: qci(193,4,2),qrs(193,4,3),nci(193,4,3),nrs(193,4,1)
    real(real32) :: brs(193,4),t(193,4),q(193,4),work2(193,4),bgevp(193,4),bgeml(193,4)
    real(real32) :: rain_q_before(5),rain_n_before(3),rain_bg_before,rain_t_before
    real(real32) :: rain_q_old(5),rain_n_old(3)
    real(real32) :: rain_qv_before,rain_ccn3_before,rain_warm_rate_base(16),rain_warm_rate_trial(16)
    real(real32) :: rain_warm_q_process(5),rain_warm_n_process(3),rain_warm_bg_process
    real(real32) :: rain_warm_t_process,rain_warm_qv_process,rain_warm_xlf,rain_warm_xlwork2
    real(real32) :: rain_warm_q_after(5),rain_warm_n_after(3),rain_warm_bg_after
    real(real32) :: rain_warm_t_after,rain_warm_qv_after,rain_ccn3_after,rain_warm_alpha
    real(real32) :: praut(193,4),pracw(193,4),paacw(193,4),nraut(193,4),nccol(193,4)
    real(real32) :: nracw(193,4),naacw(193,4),prevp(193,4),pseml(193,4),pgeml(193,4)
    real(real32) :: psevp(193,4),pgacs(193,4),pgevp(193,4),nrcol(193,4),nseml(193,4),ngeml(193,4)
    real(real32),parameter :: pidnr=12566.37109375_real32,qmin=1.e-12_real32,ncmin=1.e-12_real32
    real(real32),parameter :: qcrmin=1.e-9_real32,nrmin=1.e-2_real32,dmr=3.0_real32
    real(real32),parameter :: lamdarmin=961.0_real32,lamdarmax=35000.0_real32
    ! Pair-only validation returns before cloud/ice PSD bounds are used; these
    ! remain valid adapter context values.
    real(real32),parameter :: pidnc=523.5988_real32,dmc=3.0_real32
    real(real32),parameter :: lamdacmin=12000.0_real32,lamdacmax=500000.0_real32
    real(real32),parameter :: pidni=1.0_real32,dmi=3.0_real32
    real(real32),parameter :: lamdaimin=9080.0_real32,lamdaimax=1820000.0_real32
    logical :: rain_full_evap_pending(193,4),rain_warm_abort,rain_warm_state_valid
    logical :: rain_warm_rate_noop,rain_warm_state_noop
    rain_full_evap_pending=.false.; rain_full_evap_pending(i,k)=pending
    progb_status=PROGB_ABSENT; pr85_warm_unit=6
    lat=222; loop=1
    dtcld={f32(params['dtcld']['hex32'])}; dry_carrier_density(i,k)={f32(params['rho_dry']['hex32'])}
    cpm(i,k)={f32(params['cpm']['hex32'])}; xl(i,k)={f32(params['xl']['hex32'])}
    xlf_input={f32(params['xlf']['hex32'])}; rhox(i,k)={f32(params['rhox']['hex32'])}
    rain_warm_alpha={f32(params['alpha']['hex32'])}
    rain_q_before(1)={f32(state_before['Qc'])}; rain_q_before(2)={f32(state_before['Qi'])}
    rain_q_before(3)={f32(state_before['Qr'])}; rain_q_before(4)={f32(state_before['Qs'])}
    rain_q_before(5)={f32(state_before['Qg'])}
    rain_n_before(1)={f32(state_before['Nc'])}; rain_n_before(2)={f32(state_before['Ni'])}
    rain_n_before(3)={f32(state_before['Nr'])}
    rain_q_old=[{', '.join(f32(state_after[name]) for name in ('Qc','Qi','Qr','Qs','Qg'))}]
    rain_n_old=[{', '.join(f32(state_after[name]) for name in ('Nc','Ni','Nr'))}]
    rain_bg_before={f32(state_before['Bg'])}; rain_t_before={f32(state_before['T'])}
    rain_qv_before={f32(state_before['Qv'])}; rain_ccn3_before={f32(state_before['Nccn'])}
    qci(i,k,:)=rain_q_before(1:2); qrs(i,k,:)=rain_q_before(3:5)
    nci(i,k,1:2)=rain_n_before(1:2); nrs(i,k,1)=rain_n_before(3)
    nci(i,k,3)=rain_ccn3_before; brs(i,k)=rain_bg_before
    t(i,k)=rain_t_before; q(i,k)=rain_qv_before
{rate_init}
    bgevp=0.0_real32; bgeml=0.0_real32
{process_setup}
    rain_warm_search_status={packet['warm_row_prefix']['search_status']}
    if (.not.kdm6_unreconstructed_rain_output_valid(rain_q_before(3),rain_n_before(3), &
         dry_carrier_density(i,k),pidnr,dmr,lamdarmin,lamdarmax,qcrmin,1.e-2_real32)) &
      error stop 'D2 base rain pair not accepted by output preview'
    call kdm6_rain_process_state_valid(rain_q_old,rain_n_old,{f32(state_after['Bg'])}, &
         {f32(state_after['T'])},dry_carrier_density(i,k),pidnr,qmin,ncmin,qcrmin,dmr, &
         lamdarmin,lamdarmax,100.0_real32,900.0_real32,pidnc,dmc,lamdacmin,lamdacmax, &
         pidni,dmi,lamdaimin,lamdaimax,rain_warm_state_valid, &
         allow_rain_number_at_zero=pending,consumer_pair_only=.true.)
    if (.not.rain_warm_state_valid) error stop 'legacy validator rejected captured D2 full endpoint'
    if (kdm6_unreconstructed_rain_output_valid({f32(state_after['Qr'])}, &
         rain_n_before(3),dry_carrier_density(i,k),pidnr,dmr,lamdarmin,lamdarmax,qcrmin,1.e-2_real32)) &
      error stop 'old D2 full endpoint accepted by output preview'
{trial_commit}
    if (rain_warm_abort) error stop 'D2 production retry aborted'
    if (any(qci(i,k,:) /= rain_warm_q_after(1:2)) .or. any(qrs(i,k,:) /= rain_warm_q_after(3:5)) .or. &
        any(nci(i,k,1:2) /= rain_warm_n_after(1:2)) .or. nrs(i,k,1) /= rain_warm_n_after(3) .or. &
        nci(i,k,3) /= rain_ccn3_after .or. brs(i,k) /= rain_warm_bg_after .or. &
        t(i,k) /= rain_warm_t_after .or. q(i,k) /= rain_warm_qv_after) &
      error stop 'production commit omitted coupled state field'
    if (rain_warm_alpha <= 0.0_real32 .or. rain_warm_alpha >= 1.0_real32) &
      error stop 'production retry did not retain a smaller positive packet'
    if (rain_warm_q_after(3) <= 0.0_real32 .or. rain_warm_n_after(3) <= 0.0_real32) &
      error stop 'production retry lost positive rain pair'
    if (rain_ccn3_after /= rain_ccn3_before) error stop 'pending CCN transfer ran for positive rain mass'
    final_state=[rain_warm_q_after,rain_warm_n_after,rain_warm_bg_after,rain_warm_t_after, &
         rain_warm_qv_after,rain_ccn3_after,rain_warm_alpha]
    write(*,'(a,1x,l1,1x,i0,1x,z8.8,1x,z8.8,1x,z8.8)') 'PR90_D2_PRODUCTION_COMMIT',pending, &
         rain_warm_retry,transfer(rain_warm_q_after(3),0_int32), &
         transfer(rain_warm_n_after(3),0_int32),transfer(rain_warm_alpha,0_int32)
  end subroutine run_d2_packet
""" + fixture[sub_start + len("contains\n"):]
    call_anchor = "  qd1=transfer(int(z'308D0490',int32),0.0_real32)"
    fixture = fixture.replace("  real(real32) :: qd1,nd1,qd2_before,qd2_after,rho,pidnr,power,lmin,lmax,qcrmin,nrmin\n",
                              "  real(real32) :: qd1,nd1,qd2_before,qd2_after,rho,pidnr,power,lmin,lmax,qcrmin,nrmin\n"
                              "  real(real32) :: d2_result_a(13),d2_result_b(13)\n")
    fixture = fixture.replace(call_anchor, "  call run_d2_packet(.false.,d2_result_a)\n"
                              "  call run_d2_packet(.true.,d2_result_b)\n"
                              "  if (any(d2_result_a /= d2_result_b)) error stop 'pending flag changed positive-pair retry'\n"
                              + call_anchor, 1)
    return fixture


def test_pr90_warm_rain_output() -> None:
    assert C5_SOURCE.is_file() and D1_EM.is_file()
    source = C5_SOURCE.read_text()
    assert hashlib.sha256(source.encode()).hexdigest() == C5_KDM6_SOURCE_SHA256
    d1_em = D1_EM.read_text()
    assert hashlib.sha256(d1_em.encode()).hexdigest() == D1_EM_SHA256
    packet = json.loads(D2_PACKET.read_text())
    assert hashlib.sha256(D2_PACKET.read_bytes()).hexdigest() == D2_PACKET_SHA256
    assert packet["parent_physical_source_sha256"] == C5_KDM6_SOURCE_SHA256
    assert packet["run_receipt_status"] == "INCOMPLETE"
    assert hashlib.sha256(D2_RUN_RECEIPT.read_bytes()).hexdigest() == packet["run_receipt_sha256"]
    build_receipt = json.loads(D2_BUILD_RECEIPT.read_text())
    assert hashlib.sha256(D2_BUILD_RECEIPT.read_bytes()).hexdigest() == packet["build_receipt_sha256"]
    compiled_kdm = Path(build_receipt["source_overrides"]["module_mp_kdm6.o"]["staged_path"])
    assert hashlib.sha256(compiled_kdm.read_bytes()).hexdigest() == packet["compiled_kdm_source_sha256"]
    compiled_kdm_text = compiled_kdm.read_text()
    assert re.search(r"\bqcrmin\s*=\s*1\.e-9\b", compiled_kdm_text, re.I)
    assert re.search(r"\bnrmin\s*=\s*1\.e-2\b", compiled_kdm_text, re.I)
    assert build_receipt["executable_sha256"] == packet["candidate_executable_sha256"]
    executable = Path(build_receipt["executable_path"])
    assert hashlib.sha256(executable.read_bytes()).hexdigest() == packet["candidate_executable_sha256"]
    for artifact_name in ("producer_trace", "warm_ledger"):
        artifact = packet["artifacts"][artifact_name]
        compressed = (D2_EVIDENCE / artifact["path"]).read_bytes()
        assert hashlib.sha256(compressed).hexdigest() == artifact["compressed_sha256"]
        assert hashlib.sha256(gzip.decompress(compressed)).hexdigest() == artifact["payload_sha256"]
    assert packet["trace_ledger_crosscheck"]["status"] == "PASS"
    before = next(row for row in packet["trace_records"] if row["stage"] == "WARM_BEFORE_COMMIT")
    old_after = next(row for row in packet["trace_records"] if row["stage"] == "WARM_AFTER_COMMIT")
    assert before["state_hex32"]["Qr"] == "308D048E" and before["state_hex32"]["Nr"] == "38AB5008"
    assert old_after["state_hex32"]["Qr"] == "308D0490" and old_after["state_hex32"]["Nr"] == "38AB5008"
    state_names = {"Qc": "Qc", "Qi": "Qi", "Qr": "Qr", "Qs": "Qs", "Qg": "Qg",
                   "Nc": "Nc", "Ni": "Ni", "Nr": "Nr", "BG": "Bg", "T": "T",
                   "QV": "Qv", "CCN3": "Nccn"}
    for stage, prefix in ((before, "before"), (old_after, "after")):
        for row_name, trace_name in state_names.items():
            group = "q" if row_name in ("Qc", "Qi", "Qr", "Qs", "Qg") else (
                "n" if row_name in ("Nc", "Ni", "Nr") else "bulk"
            )
            assert packet["warm_fields"][f"{group}_{prefix}"][row_name]["hex32"] == \
                stage["state_hex32"][trace_name]
        bulk = packet["warm_fields"][f"bulk_{prefix}"]
        state = stage["state_hex32"]
        assert {name: bulk[name]["hex32"] for name in ("BG", "T", "QV", "CCN3")} == {
            "BG": state["Bg"], "T": state["T"], "QV": state["Qv"], "CCN3": state["Nccn"]
        }
    transformed = add_unreconstructed_rain_output_check(source)
    production_block = extract_warm_trial_commit(transformed)
    process_setup = extract_warm_process_setup(transformed)
    assert "rain_warm_q_process(3)=" in re.sub(r"[\s&]+", "", process_setup).lower()
    assert "rain_warm_n_process(3)=" in re.sub(r"[\s&]+", "", process_setup).lower()
    assert "do rain_warm_retry=0,56" in production_block.lower()
    assert "if(rain_warm_abort)errorstop'kdm6warmnativeendpointsearchfailed'" in re.sub(
        r"[\s&]+", "", production_block
    ).lower()
    for commit in (
        "qrs(i,k,1)=rain_warm_q_after(3)",
        "nrs(i,k,1)=rain_warm_n_after(3)",
        "brs(i,k)=rain_warm_bg_after",
        "t(i,k)=rain_warm_t_after",
        "q(i,k)=rain_warm_qv_after",
        "nci(i,k,3)=rain_ccn3_after",
    ):
        assert commit in re.sub(r"[\s&]+", "", production_block).lower()
    compact = re.sub(r"[\s&]+", "", re.sub(r"!.*$", "", transformed, flags=re.M)).lower()
    assert "consumer_pair_only=.true." in compact
    assert "if(qrs(i,k,1).ge.qcrmin.and.nrs(i,k,1).ge.nrmin)then" in compact
    assert "if(rain_warm_search_status.eq.1.or.rain_warm_retry.gt.0)then" in compact
    assert compact.count("rain_warm_state_valid=kdm6_unreconstructed_rain_output_valid(") == 3
    # The trial check precedes acceptance, after CCN transfer and the existing
    # source validator; the retry and all failure/rollback labels are retained.
    trial_preview = (
        "rain_warm_state_valid=kdm6_unreconstructed_rain_output_valid("
        "rain_warm_q_after(3),rain_warm_n_after(3),dry_carrier_density(i,k),"
        "pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin)"
    )
    base_preview = (
        "rain_warm_state_valid=kdm6_unreconstructed_rain_output_valid("
        "rain_q_before(3),rain_n_before(3),dry_carrier_density(i,k),"
        "pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin)"
    )
    assert compact.count(trial_preview) == 1
    assert compact.count(base_preview) == 2
    trial = compact.index(trial_preview)
    accepted = compact.index("if(rain_warm_state_valid.and.rain_warm_qv_after.ge.0.0.and.")
    assert trial < accepted
    assert compact[trial + len(trial_preview):accepted].strip() == ""
    for anchor in (
        "if(rain_warm_retry.gt.0)thenif(rain_warm_retry.le.32)then",
        "rain_warm_alpha=nearest(rain_warm_alpha,-1.0)",
        "rain_warm_alpha=0.5*rain_warm_alpha",
        "rain_warm_abort=.true.",
        "rain_warm_q_after=rain_q_before",
    ):
        assert anchor in compact

    helper = HELPER.read_text()
    fixture = (
        core_module(d1_em) + "\n" + helper + "\n" +
        source_bound_fixture(transformed)
    )
    fixture = add_d2_production_block(fixture, transformed, packet)
    for optimization in ("O0", "O2"):
        scratch = Path(tempfile.mkdtemp(prefix=f"pr90_warm_output_{optimization}_", dir="/var/tmp"))
        core_end = fixture.index("end module cloud_bal_joint_transport") + len(
            "end module cloud_bal_joint_transport\n"
        )
        helper_start = fixture.index("subroutine pr90_rain_public_store_diagnostic", core_end)
        output_module_start = fixture.index("module pr90_warm_output_test", helper_start)
        (scratch / "core.F90").write_text(fixture[:core_end])
        (scratch / "helper.F90").write_text(fixture[helper_start:output_module_start])
        (scratch / "test.F90").write_text(fixture[output_module_start:])
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            'for unit in core helper test; do "$CLOUD_BAL_FC" "${flags[@]}" -free -fpe0 '
            '-module "$3" -I "$3" -c "$3/$unit.F90" -o "$3/$unit.o" || exit; done && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free -fpe0 -module "$3" -I "$3" '
            '"$3/core.o" "$3/helper.o" "$3/test.o" -o "$3/test.exe" && "$3/test.exe"',
            "pr90-warm-output", str(ROOT), optimization, str(scratch),
        ]
        result = subprocess.run(command, cwd=scratch, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False, timeout=180)
        assert result.returncode == 0, result.stdout
        assert "PR90_WARM_OUTPUT_HELPER" in result.stdout and "PASS" in result.stdout
        commit_lines = re.findall(r"(?m)^PR90_D2_PRODUCTION_COMMIT\s+.*$", result.stdout)
        assert commit_lines == [
            "PR90_D2_PRODUCTION_COMMIT F 34 308D048E 38AB5008 3E7FFFE0",
            "PR90_D2_PRODUCTION_COMMIT T 34 308D048E 38AB5008 3E7FFFE0",
        ]
        warm_rows = re.findall(r"(?m)^WARM\s+193\s+222\s+4\b.*$", result.stdout)
        assert len(warm_rows) == 2
        for row in warm_rows:
            fields = row.split()
            assert fields[4:9] == ["1", "0", "34", "0", "FF"]
            assert fields[15] == "2.4999952316284180E-01"
        print(f"{optimization}: D2 production retry=34 alpha=3E7FFFE0; pending F/T PASS")


if __name__ == "__main__":
    test_pr90_warm_rain_output()
    print("PR90 warm rain output source contract PASS")
