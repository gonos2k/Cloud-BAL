#!/usr/bin/env python3
"""Compile the exact generated ice producers with the freezing consumer."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RAW_SOURCE = Path(os.environ.get(
    "PR93_C18_SOURCE", "/var/tmp/pr90_sources_c7_20261019/module_mp_kdm6.F"
))


def extracted_blocks(source: str) -> list[str]:
    activations = (
        r"^          if\(qci\(i,k,2\) \.ge\. 1\.e-14 \) then$",
        r"^          if\(qci\(i,k,2\)\.ge\. 1\.e-14 \) then$",
        r"^          if\(qci\(i,k,2\)\.ge\. qmin \.and\. nci\(i,k,2\) \.ge\. ncmin \) then$",
    )
    result = []
    for activation in activations:
        match = re.search(activation + r".*?^          endif", source, re.M | re.S)
        if match is None:
            raise AssertionError(f"missing raw ice producer block: {activation}")
        result.append(match.group())
    return result


def extract_procedure(source: str, name: str, end_name: str | None = None) -> str:
    end_name = end_name or name
    match = re.search(
        rf"(?ims)^\s*{name}\b.*?^\s*END (?:SUBROUTINE|FUNCTION) {end_name}\s*$", source
    )
    if match is None:
        raise AssertionError(f"could not extract {name}")
    return match.group().strip()


def extract_psd_bound_helper() -> str:
    patch = (ROOT / "patches/pr85_kdm6_ice_sedimentation.patch").read_text()
    lines = patch.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("+SUBROUTINE pr85_kdm6_psd_bound_number("))
    helper: list[str] = []
    for line in lines[start:]:
        if not line.startswith("+"):
            break
        helper.append(line[1:])
        if line == "+END SUBROUTINE pr85_kdm6_psd_bound_number":
            break
    result = "\n".join(helper)
    if not result.endswith("END SUBROUTINE pr85_kdm6_psd_bound_number"):
        raise AssertionError("could not extract existing PSD boundary helper")
    return result


def module_source(blocks: list[str], procedures: list[str], psd_helper: str) -> str:
    producer_template = """  SUBROUTINE producer_{number}(q,n,rho)
    REAL :: q,n,rho
    REAL :: qci(1,1,2),nci(1,1,2),dry_carrier_density(1,1)
    REAL :: pidni,dmi,lamdaimin,lamdaimax,lamdi_tmp(1,1),n0i(1,1),g1pmi,mui
    REAL :: pr85_psd_before,pr85_psd_directed,pr85_psd_legacy
    REAL(8) :: pr85_psd_exact_min,pr85_psd_exact_max,qmin,ncmin
    INTEGER :: i,k,lat,pr85_psd_unit
    LOGICAL :: pr85_psd_native_available,pr67_trace_this_call
    LOGICAL :: pr85_psd_valid,pr93_ice_pair_valid,pr93_ice_direct_repair
    REAL(8) :: pr93_ice_mean,pr93_ice_min,pr93_ice_max
    REAL, PARAMETER :: PR85_ICE_NATIVE_INACTIVE_MAX=NEAREST(1.e-14,-1.0)
    LOGICAL, EXTERNAL :: pr93_kdm6_pair_in_cone
    EXTERNAL :: pr85_kdm6_psd_bound_number
    i=1; k=1; lat=1; pr85_psd_unit=6
    pidni=1570.7964; dmi=3.0; lamdaimin=9080.0; lamdaimax=1820000.0
    g1pmi=1.0; mui=0.0; qmin=1.e-20_8; ncmin=0.0_8
    dry_carrier_density(1,1)=rho
    qci=0.0; nci=0.0
    qci(1,1,2)=q; nci(1,1,2)=n
    pr85_psd_native_available=.FALSE.; pr67_trace_this_call=.FALSE.
{block}
    n=nci(1,1,2)
  END SUBROUTINE producer_{number}
"""
    producers = "\n".join(
        producer_template.format(number=index + 1, block=block)
        for index, block in enumerate(blocks)
    )
    return """MODULE pr93_active_ice_contract_harness
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_joint_transport, ONLY: joint_moment_store
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: producer_1,producer_2,producer_3,test_packets
CONTAINS
""" + "\n".join(procedures[3:]) + "\n" + procedures[2] + "\n" + producers + "\nEND MODULE\n" + "\n".join(procedures[:2]) + "\n" + psd_helper + "\n"


def test_pr93_active_ice_contract() -> None:
    scratch = Path(tempfile.mkdtemp(prefix="pr93_active_ice_", dir="/var/tmp"))
    generated_path = scratch / "module_mp_kdm6.F"
    manifest_path = scratch / "source_manifest.json"
    generate = subprocess.run(
        ["python3", str(ROOT / "tools/pr93_active_ice_contract.py"),
         "--source", str(RAW_SOURCE), "--output", str(generated_path),
         "--manifest", str(manifest_path)],
        cwd=scratch, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False,
    )
    assert generate.returncode == 0, generate.stdout
    raw = RAW_SOURCE.read_text()
    generated = generated_path.read_text()
    before = extracted_blocks(raw)
    after = extracted_blocks(generated)
    assert len(before) == len(after) == 3
    for old, new in zip(before, after, strict=True):
        old_activation = old.splitlines()[0]
        assert new.splitlines()[0] == old_activation
        assert old.count("call pr85_kdm6_psd_bound_number") == 2
        assert new.count("call pr85_kdm6_psd_bound_number") == 2
        assert old.count("n0i(i,k) =") == new.count("n0i(i,k) =")
        assert new.count("pr85_psd_native_available, &") == 2
    assert "PR85_ICE_NATIVE_INACTIVE_MAX = NEAREST(1.e-14,-1.0)" in generated

    helper_source = (ROOT / "tools/pr85_kdm6_freezing_packet.F90").read_text()
    predicate = extract_procedure(generated, "PURE LOGICAL FUNCTION pr93_kdm6_pair_in_cone", "pr93_kdm6_pair_in_cone")
    packet = extract_procedure(generated, "SUBROUTINE pr85_kdm6_freezing_packet", "pr85_kdm6_freezing_packet")
    to_volume = extract_procedure(raw, "PURE ELEMENTAL SUBROUTINE specific_number_to_volume", "specific_number_to_volume")
    to_specific = extract_procedure(raw, "PURE ELEMENTAL SUBROUTINE volume_number_to_specific", "volume_number_to_specific")
    assert "8.0_real64" in predicate
    assert "pr93_kdm6_pair_in_cone" in packet
    assert "ice_transient_mass_limit" in helper_source
    psd_helper = extract_psd_bound_helper()
    test_packets = """  SUBROUTINE test_packets()
    REAL(real32) :: qca,nca,qia,nia
    REAL(real64) :: ma,na,theta,cmin,cmax,imin,imax
    LOGICAL :: base_valid,accepted,valid
    EXTERNAL :: pr85_kdm6_freezing_packet
    REAL(real32) :: rho,qc,nc,qi,ni
    REAL(real32) :: repaired_n_volume,host_ice_n_specific,roundtrip_ice_n_volume
    REAL(real32) :: stored_n_specific,stored_n_volume,qstored,nstored
    REAL(real64) :: volume_bounds(2),adapter_n_specific64
    INTEGER :: adjustment,store_stage
    rho=0.53602171_real32; qc=1.35057935e-5_real32; nc=42574184.0_real32
    qi=2.43850627e-6_real32; ni=622.93670654296875_real32
    cmin=523.59881591796875_real64/(500000.0_real64**3)
    cmax=523.59881591796875_real64/(12000.0_real64**3)
    imin=1570.79638671875_real64/(1820000.0_real64**3)
    imax=1570.79638671875_real64/(9080.0_real64**3)
    repaired_n_volume=ni
    ! Native ICE export writes REAL32 Nspec; the next KDM6 call converts it
    ! back to REAL32 Nvol before the same freezing consumer sees the pair.
    CALL volume_number_to_specific(repaired_n_volume,rho,host_ice_n_specific,valid)
    IF (.NOT.valid) ERROR STOP 'native ICE export conversion failed'
    CALL specific_number_to_volume(host_ice_n_specific,rho,roundtrip_ice_n_volume,valid)
    IF (.NOT.valid) ERROR STOP 'native ICE reentry conversion failed'
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,roundtrip_ice_n_volume,rho, &
      DBLE(NEAREST(1.e-14,-1.0)),2.1296498102647661e-13_real64, &
      0.50349597749963093_real64,cmin,cmax,imin,imax, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. accepted .OR. theta/=0.0_real64 .OR. &
        qca/=qc .OR. nca/=nc .OR. qia/=qi .OR. nia/=roundtrip_ice_n_volume .OR. &
        ma/=0.0_real64 .OR. na/=0.0_real64) &
      ERROR STOP 'native ICE R32 host roundtrip must defer fixed packet'
    PRINT '(a)', 'PR93 native ICE R32 export/reentry/freezing tiny packet PASS'

    ! Separate common-core R64 storage contract; this is not the native ICE
    ! export path above.
    adapter_n_specific64=DBLE(repaired_n_volume)/DBLE(rho)
    volume_bounds=[DBLE(rho)*9080.0_real64**3/1570.79638671875_real64, &
                   DBLE(rho)*1820000.0_real64**3/1570.79638671875_real64]
    CALL joint_moment_store(DBLE(qi),adapter_n_specific64,rho, &
      imin,imax,.TRUE., &
      qstored,nstored,adjustment,valid,allow_normal_q_adjustment=.TRUE., &
      volume_number_bounds=volume_bounds,strict_mass_ratio=.TRUE., &
      allow_joint_quantum_absence=.TRUE.,failure_stage=store_stage)
    IF (.NOT.valid) THEN
      PRINT *, 'joint store failure stage',store_stage
      ERROR STOP 'public to internal joint store failed'
    ENDIF
    stored_n_specific=nstored
    CALL specific_number_to_volume(stored_n_specific,rho,stored_n_volume,valid)
    IF (.NOT.valid) ERROR STOP 'stored specific to volume conversion failed'
    qi=qstored; ni=stored_n_volume
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,DBLE(NEAREST(1.e-14,-1.0)), &
      2.1296498102647661e-13_real64,0.50349597749963093_real64, &
      cmin,cmax,imin,imax,qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. accepted .OR. theta/=0.0_real64 .OR. &
        qca/=qc .OR. nca/=nc .OR. qia/=qi .OR. nia/=ni .OR. ma/=0.0_real64 .OR. na/=0.0_real64) &
      ERROR STOP 'valid repaired producer state must defer fixed packet'
    PRINT '(a)', 'PR93 separate common-core R64 store/reconsume check PASS'
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,DBLE(NEAREST(1.e-14,-1.0)), &
      0.0_real64,0.0_real64,cmin,cmax,imin,imax,qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. .NOT.accepted .OR. theta/=0.0_real64 .OR. &
        qca/=qc .OR. nca/=nc .OR. qia/=qi .OR. nia/=ni) ERROR STOP 'zero packet contract'
    rho=0.7_real32; qc=1.e-4_real32; nc=1.e6_real32; qi=1.e-5_real32; ni=1.e5_real32
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,0.0_real64,1.e-6_real64,1.e3_real64, &
      1.e-16_real64,1.e-8_real64,1.e-16_real64,1.e-8_real64, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. .NOT.accepted .OR. theta/=1.0_real64) ERROR STOP 'full packet contract'
    qi=REAL(NEAREST(1.e-14,-1.0),real32); ni=1.e7_real32
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,DBLE(NEAREST(1.e-14,-1.0)), &
      0.0_real64,0.0_real64,1.e-16_real64,1.e-8_real64,imin,imax, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (.NOT.base_valid .OR. .NOT.accepted) ERROR STOP 'native inactive cutoff changed'
    ni=0.0_real32
    CALL pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,DBLE(NEAREST(1.e-14,-1.0)), &
      0.0_real64,0.0_real64,1.e-16_real64,1.e-8_real64,imin,imax, &
      qca,nca,qia,nia,ma,na,theta,base_valid,accepted)
    IF (base_valid .OR. accepted) ERROR STOP 'inactive orphan must reject'
  END SUBROUTINE test_packets
"""
    all_procedures = [predicate, packet, test_packets, to_volume, to_specific]
    source = module_source(after, all_procedures, psd_helper)
    driver = """PROGRAM test_pr93_active_ice_contract
  USE pr93_active_ice_contract_harness
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32
  IMPLICIT NONE
  REAL :: n
  REAL :: rho
  CHARACTER(len=16) :: mode
  CALL GET_COMMAND_ARGUMENT(1,mode)
  rho=0.5360217094421387
  IF (TRIM(mode)=='orphan') THEN
    n=0.0
    CALL producer_1(2.4385062715737149e-6,n,rho)
    ERROR STOP 'active orphan was not rejected'
  ENDIF
  n=622.93597412109375
  CALL producer_1(2.4385062715737149e-6,n,rho)
  IF (TRANSFER(n,0) /= INT(Z'441BBBF3')) ERROR STOP 'stage1 directed donor mismatch'
  n=622.93597412109375
  CALL producer_2(2.4385062715737149e-6,n,rho)
  IF (TRANSFER(n,0) /= INT(Z'441BBBF3')) ERROR STOP 'stage2 directed donor mismatch'
  n=622.93597412109375
  CALL producer_3(2.4385062715737149e-6,n,rho)
  IF (TRANSFER(n,0) /= INT(Z'441BBBF3')) ERROR STOP 'stage3 directed donor mismatch'
  CALL test_packets()
  PRINT '(a)', 'PR93 active ice contract cases PASS'
END PROGRAM test_pr93_active_ice_contract
"""
    generated_fortran = source + driver
    fixture = scratch / "test_pr93_active_ice_contract.F90"
    fixture.write_text(generated_fortran)
    optimization_logs = []
    for optimization in ("O0", "O2"):
        build = scratch / optimization
        build.mkdir()
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" >/dev/null && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$1/src/common/cloud_bal_joint_transport.f90" "$3" -o "$4/contract.exe" && '
            '"$4/contract.exe"',
            "pr93-active-ice-contract", str(ROOT), optimization, str(fixture), str(build),
        ]
        result = subprocess.run(command, cwd=build, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        assert "PR93 active ice contract cases PASS" in result.stdout
        orphan = subprocess.run(
            ["bash", "-c", 'source "$1/tests/intel_toolchain.sh" >/dev/null && "$2" orphan',
             "pr93-active-ice-orphan", str(ROOT), str(build / "contract.exe")],
            cwd=build, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False)
        assert orphan.returncode != 0
        assert "PR93 invalid active ice PSD input" in orphan.stdout, orphan.stdout
        print(f"{optimization}: {result.stdout.strip()}")
        optimization_logs.append(f"{optimization}: PASS\n{result.stdout.strip()}\n")
    manifest = __import__("json").loads(manifest_path.read_text())
    tool_sha = hashlib.sha256((ROOT / "tools/pr93_active_ice_contract.py").read_bytes()).hexdigest()
    fixture_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    receipt_dir = ROOT / "docs/evidence/pr93_active_ice_20261020/activeicevalidation"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = (
        f"source={RAW_SOURCE}\nsource_sha256={manifest['source_sha256']}\n"
        f"generated_source={generated_path}\ngenerated_source_sha256={manifest['output_sha256']}\n"
        f"generator_sha256={tool_sha}\nfixture={fixture}\nfixture_sha256={fixture_sha}\n"
        + "".join(optimization_logs)
    )
    (receipt_dir / "contract_o0_o2.txt").write_text(receipt)
    print("generated_source_sha256=" + manifest["output_sha256"])
    print("generator_sha256=" + tool_sha)
    print("fixture_sha256=" + fixture_sha)
    print("receipt=" + str(receipt_dir / "contract_o0_o2.txt"))


if __name__ == "__main__":
    test_pr93_active_ice_contract()
    print("PR93 active ice contract test PASS")
