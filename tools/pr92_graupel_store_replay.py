#!/usr/bin/env python3
"""Replay PR92 candidate storage through the current source contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src/common/cloud_bal_joint_transport.f90"
MIXTURE_SOURCE = ROOT / "tools/pr87_graupel_cone_mixture.py"
PROFILE = ROOT / "tests/intel_toolchain.sh"
Q64_HEX = "370528AC448AD089"
B64_HEX = "3668384CB70114F1"
QUANTUM = 2.0 ** -149
FORTRAN_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:f90|f)", re.IGNORECASE)
EXECUTABLE_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_helper(source: str, name: str) -> str:
    start = re.search(rf"(?im)^\s*(?:pure\s+)?(?:logical\s+)?(?:subroutine|function)\s+{name}\s*\(", source)
    end = re.search(rf"(?im)^\s*end\s+(?:subroutine|function)\s+{name}\s*(?:\"\"\")?\s*$", source[start.start():]) if start else None
    if not start or not end:
        raise ValueError(f"missing source-form helper {name}")
    return source[start.start():start.start() + end.end()].replace('"""', '').rstrip()


def helper_source() -> tuple[str, str]:
    text = MIXTURE_SOURCE.read_text()
    return extract_helper(text, "strict_graupel_pair"), extract_helper(text, "store_graupel_mixture")


def make_fixture(strict: str, store: str) -> str:
    return f"""module mixture_fixture
  use iso_fortran_env, only: real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
contains
{strict}
{store}
end module mixture_fixture
"""


def make_harness() -> str:
    return f"""program pr92_graupel_store_replay
  use iso_fortran_env, only: int32,int64,real32,real64
  use cloud_bal_joint_transport, only: joint_moment_store
  use mixture_fixture
  implicit none
  real(real64) :: q64,b64,dq,dn,weights(7),refq,refn
  real(real32) :: rho,sq,sb,qt(7),bt(7),storedq,storedb,donorq,donorb
  integer :: adjustment,stage
  logical :: valid
  q64=transfer(int(z'{Q64_HEX}',int64),0.0_real64)
  b64=transfer(int(z'{B64_HEX}',int64),0.0_real64)
  rho=1.0_real32
  call joint_moment_store(q64,b64,rho,100.0_real64,900.0_real64,.true., &
      sq,sb,adjustment,valid,.true.,.true.,strict_mass_ratio=.true.,failure_stage=stage)
  write(*,'(a,1x,l1,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') 'CORE_CANDIDATE',valid,stage,adjustment, &
       transfer(sq,0_int32),transfer(sb,0_int32)

  weights=0.0_real64; qt=0.0_real32; bt=0.0_real32
  refq=0.0_real64; refn=0.0_real64
  call store_graupel_mixture(weights,qt,bt,1.0_real32,100.0_real64,900.0_real64, &
       refq,refn,storedq,storedb,dq,dn,valid)
  write(*,'(a,1x,l1,1x,z8.8,1x,z8.8,1x,2(z16.16,1x))') 'MIXTURE_ABSENT',valid, &
       transfer(storedq,0_int32),transfer(storedb,0_int32),transfer(dq,0_int64),transfer(dn,0_int64)

  donorq=transfer(int(z'00000064',int32),0.0_real32)
  donorb=transfer(int(z'00000001',int32),0.0_real32)
  qt=0.0_real32; bt=0.0_real32; weights=0.0_real64
  qt(1)=donorq; bt(1)=donorb; weights(1)=1.0_real64
  refq=real(donorq,real64); refn=real(donorb,real64)
  call store_graupel_mixture(weights,qt,bt,1.0_real32,100.0_real64,900.0_real64, &
       refq,refn,storedq,storedb,dq,dn,valid)
  write(*,'(a,1x,l1,1x,z8.8,1x,z8.8,1x,2(z16.16,1x))') 'MIXTURE_MIN_POSITIVE',valid, &
       transfer(storedq,0_int32),transfer(storedb,0_int32),transfer(dq,0_int64),transfer(dn,0_int64)

  donorq=transfer(int(z'398DD8E4',int32),0.0_real32)
  donorb=transfer(int(z'34A16400',int32),0.0_real32)
  qt=0.0_real32; bt=0.0_real32; weights=0.0_real64
  qt(1)=donorq; bt(1)=donorb; weights(1)=1.0_real64
  refq=real(donorq,real64); refn=real(donorb,real64)
  call store_graupel_mixture(weights,qt,bt,1.0_real32,100.0_real64,900.0_real64, &
       refq,refn,storedq,storedb,dq,dn,valid)
  write(*,'(a,1x,l1,1x,z8.8,1x,z8.8)') 'MIXTURE_NORMAL',valid, &
       transfer(storedq,0_int32),transfer(storedb,0_int32)
end program pr92_graupel_store_replay
"""


def run_source_profile(profile: str, sources: dict[str, str],
                       executable: str = "replay") -> dict[str, str]:
    """Compile ordered Fortran source strings with the pinned profile in fresh scratch."""
    if profile not in {"O0", "O2"}:
        raise ValueError("profile must be O0 or O2")
    if not sources or any(not isinstance(name, str) or name in {".", ".."} or
                          FORTRAN_BASENAME.fullmatch(name) is None for name in sources):
        raise ValueError("sources must be an ordered mapping of Fortran basenames to source text")
    if not isinstance(executable, str) or executable in {".", ".."} or \
            EXECUTABLE_BASENAME.fullmatch(executable) is None:
        raise ValueError("executable must be a basename")
    scratch = Path(tempfile.mkdtemp(prefix=f"pr92_source_{profile.lower()}_", dir="/var/tmp"))
    module_dir = scratch / "mod"
    module_dir.mkdir()
    objects = []
    for index, (name, source) in enumerate(sources.items()):
        source_path = scratch / name
        object_path = scratch / f"source_{index}.o"
        source_path.write_text(source)
        objects.append(object_path)
    shell = ('source "$1/tests/intel_toolchain.sh" && '
             'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
             'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && ')
    for index, name in enumerate(sources):
        shell += (f'"$CLOUD_BAL_FC" "${{flags[@]}}" -free -module "$3/mod" -I "$3/mod" '
                  f'-c "$3/{name}" -o "$3/source_{index}.o" && ')
    object_args = " ".join(f'"$3/source_{index}.o"' for index in range(len(objects)))
    shell += (f'"$CLOUD_BAL_FC" "${{flags[@]}}" -free -module "$3/mod" -I "$3/mod" '
              f'{object_args} -o "$3/{executable}" && "$3/{executable}"')
    result = subprocess.run(["bash", "-c", shell, "pr92", str(ROOT), profile, str(scratch)],
                            cwd=scratch, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"{profile} source replay failed:\n{result.stdout}")
    return {"profile": profile, "scratch": str(scratch), "stdout": result.stdout.strip(),
            "stdout_sha256": sha256(result.stdout.encode())}


def run_profile(profile: str) -> dict[str, Any]:
    strict, store = helper_source()
    compiled = run_source_profile(profile, {
        "core.f90": CORE.read_text(),
        "mixture.f90": make_fixture(strict, store),
        "harness.f90": make_harness(),
    })
    result_stdout = compiled["stdout"]
    rows = {}
    for line in result_stdout.splitlines():
        fields = line.split()
        if fields and fields[0] in {"CORE_CANDIDATE", "MIXTURE_ABSENT", "MIXTURE_MIN_POSITIVE", "MIXTURE_NORMAL"}:
            rows[fields[0]] = fields[1:]
    if len(rows) != 4:
        raise RuntimeError(f"malformed replay output:\n{result_stdout}")
    return {**compiled, "rows": rows}


def representability() -> dict[str, Any]:
    q = struct.unpack(">d", bytes.fromhex(Q64_HEX))[0]
    b = struct.unpack(">d", bytes.fromhex(B64_HEX))[0]
    q_units, b_units = q / QUANTUM, b / QUANTUM
    # At the least positive REAL32 B quantum, the strict 100:900 cone starts at Q=100 quanta.
    store_q_units, store_b_units = 100, 1
    return {
        "candidate_hex": {"q_real64": Q64_HEX, "b_real64": B64_HEX},
        "candidate": {"q": q, "b": b, "ratio": q / b,
                      "density_label": "diagnostic rho=1.0; actual density pending"},
        "real32_quantum_each_field": QUANTUM,
        "candidate_in_separate_real32_quantum_units": {"q": q_units, "b": b_units},
        "nearest_real32_bits": {"q": "00000055", "b": "00000000"},
        "nearest_pair": {"q_bits": "00000055", "b_bits": "00000000", "strict_cone_valid": False},
        "smallest_positive_joint_cone_pair": {
            "q_bits": f"{store_q_units:08X}", "b_bits": f"{store_b_units:08X}",
            "q": store_q_units * QUANTUM, "b": store_b_units * QUANTUM,
            "ratio": store_q_units / store_b_units,
            "delta_q": (store_q_units - q_units) * QUANTUM,
            "delta_b": (store_b_units - b_units) * QUANTUM,
            "relative_delta_q": (store_q_units * QUANTUM - q) / q,
            "relative_delta_b": (store_b_units * QUANTUM - b) / b,
        },
        "zero_pair": {"q_bits": "00000000", "b_bits": "00000000",
                      "signed_delta_q": -q, "signed_delta_b": -b},
        "fixed_q_positive_b_exists": False,
        "note": "Q and B use separate field values and signed deltas; no shared ice-moment quantum is reused.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {
        "schema": "pr92_graupel_store_replay_v1",
        "source": {"core": str(CORE), "core_sha256": sha256(CORE.read_bytes()),
                   "mixture_generator": str(MIXTURE_SOURCE), "helper_sha256": sha256("\n".join(helper_source()).encode()),
                   "toolchain_profile": str(PROFILE), "toolchain_profile_sha256": sha256(PROFILE.read_bytes())},
        "known_candidate": representability(),
        "donor_mixture": {"status": "unknown; native weights and terms not supplied",
                          "manufactured_contract_cases_only": True},
        "replays": [run_profile("O0"), run_profile("O2")],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
