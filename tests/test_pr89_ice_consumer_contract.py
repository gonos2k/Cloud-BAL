#!/usr/bin/env python3
"""Source-derived regression for the transient ICE storage contract."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pr89_ice_consumer_contract import (  # noqa: E402
    ICE_LIMIT_EXPRESSION,
    JOINT_TRANSPORT_SHA256,
    V50_MODULE_EM_SHA256,
    connect_ice_consumer,
)
from pr89_process_consumer_contract import (  # noqa: E402
    DEFAULT_KDM6_SOURCE,
    KDM6_SOURCE_SHA256,
    extract_actual_consumer,
)


V50_SOURCE = Path("/var/tmp/pr87_followup_sources_20261019_v50/module_em_pr85.F")
C5_SOURCE = Path("/var/tmp/pr89_sources_20261019_c5/module_em_pr89.F")
C5_SOURCE_SHA256 = "0d3b1fe91a01c747a2339487695d82c7109ad4df3da5cbc561ca338c1fecf91d"
CURRENT_TRANSPORT_SHA256 = "c8ecedde5cc8f9adedf6cf082054596ca1c0d6a3565d152c73d730c00cd678f3"


def _host_ice_store_call(transformed: str) -> str:
    start = transformed.index("SUBROUTINE certify_graupel_storage(")
    end = transformed.index("END SUBROUTINE certify_graupel_storage", start)
    certifier = transformed[start:end]
    match = re.search(
        r"CALL joint_moment_store\(value_q,value_n,drydensity\(c\),minmass\(p\),maxmass\(p\), &\n"
        r"\s+\.TRUE\.,stored_q,stored_n,adjustment,store_valid, &\n"
        r"\s+allow_normal_q_adjustment=\.TRUE\.,allow_joint_quantum_absence=\.TRUE\., &\n"
        r"\s+inactive_mass_limit=REAL\(NEAREST\(1\.e-14,-1\.0\),real64\)\)",
        certifier,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise AssertionError("actual transformed pair-2 certifier store call is missing")
    return match.group(0)


def _regression_source() -> tuple[str, str]:
    native = V50_SOURCE.read_text()
    assert hashlib.sha256(native.encode()).hexdigest() == V50_MODULE_EM_SHA256
    common = (ROOT / "src/common/cloud_bal_joint_transport.f90").read_text()
    assert hashlib.sha256(common.encode()).hexdigest() == CURRENT_TRANSPORT_SHA256
    # Reproduce the historical transform with its frozen input; exercise its
    # unchanged host call against the current maintained implementation below.
    c5_source = C5_SOURCE.read_text()
    assert hashlib.sha256(c5_source.encode()).hexdigest() == C5_SOURCE_SHA256
    module_end = "end module cloud_bal_joint_transport\n"
    frozen_common = c5_source[:c5_source.index(module_end) + len(module_end)]
    assert hashlib.sha256(frozen_common.encode()).hexdigest() == JOINT_TRANSPORT_SHA256
    transformed = connect_ice_consumer(native, frozen_common)
    assert "inactive_mass_limits=[0.0_real64," + ICE_LIMIT_EXPRESSION in transformed
    assert transformed.startswith(frozen_common.rstrip() + "\n\n")
    transformed_host = transformed[len(frozen_common.rstrip()) + 2 :]
    assert transformed_host.count("inactive_mass_limit=") == 5
    assert "inactive_mass_limit=MERGE(" in transformed_host
    host_call = _host_ice_store_call(transformed)

    kdm6 = DEFAULT_KDM6_SOURCE.read_text()
    assert hashlib.sha256(kdm6.encode()).hexdigest() == KDM6_SOURCE_SHA256
    consumer = extract_actual_consumer(kdm6)
    driver = f"""program pr89_t5_ice_consumer
 use iso_fortran_env, only: int32,int64,real32,real64
 use cloud_bal_joint_transport, only: joint_moment_store,joint_moment_is_valid64,joint_qnb_update
 use pr89_actual_consumer, only: PR85_ICE_NATIVE_INACTIVE_MAX,kdm6_rain_process_state_valid
 implicit none
 real(real32) :: stored_q,stored_n,drydensity(1),q(5),n(3)
 real(real64) :: value_q,value_n,minmass(4),maxmass(4),ice_limit
 real(real32) :: qb(1,4),nb(1,4),qs(1,4),ns(1,4),qsrc(1,4),nsrc(1,4)
 real(real32) :: qt(1,4),nt(1,4),oldcarrier(1),newcarrier(1),dt
 real(real64) :: qsrc64(1,4),nsrc64(1,4),qt64(1,4),nt64(1,4)
 real(real64) :: theta,rejected_q(4),rejected_n(4),delta_q(4),delta_n(4),ice_limits(4)
 integer :: adjustments(4)
 integer :: adjustment,p,c,reason
 logical :: store_valid,consumer_valid
 p=2; c=1
 ! Only rounded full-state rho was retained; REAL32 conversion is an adapter,
 ! not claimed as the exact RK1 density bits.
 drydensity(1)=0.1140736_real32
 minmass=[1.0e-7_real64,2.6055879053180625e-16_real64,1.0e-7_real64,100.0_real64]
 maxmass=[1.0e-5_real64,2.0982747187893314e-9_real64,1.0e-5_real64,900.0_real64]
 ice_limit=real(PR85_ICE_NATIVE_INACTIVE_MAX,real64)
 qb=0.0_real32; nb=0.0_real32; qs=qb; ns=nb
 qsrc=0.0_real32; nsrc=0.0_real32; qt=0.0_real32; nt=0.0_real32
 qsrc64=0.0_real64; nsrc64=0.0_real64; qt64=0.0_real64; nt64=0.0_real64
 oldcarrier=95000.0_real32; newcarrier=95000.0_real32
 dt=transfer(int(z'40D55555',int32),0.0_real32)
 qsrc64(1,2)=transfer(int(z'3C5BE7A593E8188A',int64),0.0_real64)
 nsrc64(1,2)=transfer(int(z'3F9D0AF50F3AFDC3',int64),0.0_real64)
 ice_limits=[0.0_real64,ice_limit,0.0_real64,0.0_real64]
 call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,oldcarrier,newcarrier,drydensity,dt, &
      minmass,maxmass,theta,rejected_q,rejected_n,store_valid,joint_constrained_storage=.true., &
      storage_delta_q=delta_q,storage_delta_n=delta_n,storage_adjustments=adjustments, &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64)
 if (store_valid .or. any(qs/=qb) .or. any(ns/=nb)) &
      error stop 'default joint candidate accepted T5 strict ICE state'
 call joint_qnb_update(qb,nb,qs,ns,qsrc,nsrc,qt,nt,oldcarrier,newcarrier,drydensity,dt, &
      minmass,maxmass,theta,rejected_q,rejected_n,store_valid,joint_constrained_storage=.true., &
      storage_delta_q=delta_q,storage_delta_n=delta_n,storage_adjustments=adjustments, &
      q_source_rate64=qsrc64,n_source_rate64=nsrc64,q_transport_rate64=qt64, &
      n_transport_rate64=nt64,inactive_mass_limits=ice_limits)
 if (.not.store_valid .or. theta/=1.0_real64) &
      error stop 'opt-in joint candidate rejected T5 ICE state'
 value_q=(real(oldcarrier(1),real64)*real(qb(1,2),real64)+ &
          real(dt,real64)*qsrc64(1,2))/real(newcarrier(1),real64)
 value_n=(real(oldcarrier(1),real64)*real(nb(1,2),real64)+ &
          real(dt,real64)*nsrc64(1,2))/real(newcarrier(1),real64)
 if (transfer(value_q,0_int64)/=int(z'3B800AB83227AC6B',int64) .or. &
     transfer(value_n,0_int64)/=int(z'3EC0B22FF0418A72',int64)) &
      error stop 'source-derived REAL64 candidate differs from captured T5 payload'
 if (qs(1,2)/=real(value_q,real32) .or. ns(1,2)/=real(value_n,real32)) &
      error stop 'joint candidate endpoint differs from T5 source-derived R32 values'
 {host_call}
 if (.not.store_valid .or. adjustment/=0 .or. stored_q/=real(value_q,real32) .or. &
     stored_n/=real(value_n,real32)) error stop 'host certifier failed to store T5 ICE endpoint'
 if (joint_moment_is_valid64(value_q,value_n,drydensity(1),minmass(2),maxmass(2))) &
     error stop 'default strict joint predicate accepted T5 ICE endpoint'
 q=0.0_real32; n=0.0_real32
 q(2)=stored_q; n(2)=stored_n
 call kdm6_rain_process_state_valid(q,n,0.0_real32,265.0_real32,drydensity(1), &
      8.0e6_real32,0.1_real32,1.0e-8_real32,1.0e-8_real32,3.0_real32, &
      1.0e2_real32,1.0e7_real32,1.0e2_real32,1.0e7_real32, &
      8.0e6_real32,3.0_real32,1.0e2_real32,1.0e7_real32, &
      8.0e6_real32,3.0_real32,1.0e2_real32,1.0e7_real32,consumer_valid, &
      allow_rain_number_at_zero=.false.,ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
      failure_reason=reason,ice_sublimation_pending=.false.)
 if (.not.consumer_valid .or. reason/=0) error stop 'actual full NG consumer rejected stored T5 ICE endpoint'
 if (ice_limit/=real(nearest(1.0e-14_real32,-1.0_real32),real64)) &
     error stop 'host and native ICE transient thresholds differ'
 print '(a)', 'T5_HOST_STORE_ACTUAL_FULL_NG PASS'
end program pr89_t5_ice_consumer
"""
    return common + "\n" + consumer + "\n" + driver, transformed


def test_actual_host_store_flows_into_actual_full_ng_consumer() -> None:
    generated, transformed = _regression_source()
    compiled_common = generated[:generated.index("end module cloud_bal_joint_transport\n") + len("end module cloud_bal_joint_transport\n")]
    assert hashlib.sha256(compiled_common.encode()).hexdigest() == CURRENT_TRANSPORT_SHA256
    assert "inactive_mass_limit=REAL(NEAREST(1.e-14,-1.0),real64)" in generated
    assert "kdm6_rain_process_state_valid(q,n" in generated
    for optimization in ("O0", "O2"):
        scratch = Path(tempfile.mkdtemp(prefix=f"pr89_ice_consumer_{optimization}_", dir="/var/tmp"))
        source = scratch / "pr89_ice_consumer.F90"
        executable = scratch / "pr89_ice_consumer.exe"
        source.write_text(generated)
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" -o "$4" && "$4"',
            "pr89-ice-contract-test", str(ROOT), optimization, str(source), str(executable),
        ]
        result = subprocess.run(
            command, cwd=scratch, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        assert result.returncode == 0, result.stdout
        assert "T5_HOST_STORE_ACTUAL_FULL_NG PASS" in result.stdout
        print(f"{optimization}: {result.stdout.strip()}")
    print("v50_module_em_sha256=" + V50_MODULE_EM_SHA256)
    print("transformed_module_em_sha256=" + hashlib.sha256(transformed.encode()).hexdigest())


if __name__ == "__main__":
    test_actual_host_store_flows_into_actual_full_ng_consumer()
    print("PR89 ICE consumer contract PASS")
