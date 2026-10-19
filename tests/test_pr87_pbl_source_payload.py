from __future__ import annotations

import sys
from pathlib import Path
import subprocess
import tempfile
import re

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
ROOT = Path(__file__).resolve().parents[1]

from pr87_pbl_source_payload import (  # noqa: E402
    PINNED_SHA256,
    _instrument_fragment,
    _instrument_part1,
    _instrument_part2,
    _instrument_pbl_driver,
    _instrument_solve,
    finalize_source_rate_validation,
    _require_hashes,
)

TOOLCHAIN = ROOT / "tests/intel_toolchain.sh"


SOLVE = """SUBROUTINE solve_em
   USE, INTRINSIC :: iso_fortran_env, ONLY: real64
   IMPLICIT NONE
   INTEGER                         :: ij , iteration
CALL first_rk_step_part1(grid)
CALL first_rk_step_part2(grid)
CALL rk_update_joint_moments(state)
END SUBROUTINE solve_em
"""

PART1 = """SUBROUTINE first_rk_step_part1 ( grid                 &
                             , feedback_is_ready                &
                            )
    USE module_state_description
    LOGICAL, INTENT(IN), OPTIONAL :: feedback_is_ready  ! For WRF-CMAQ coupled model, indicates feedback information is available
CALL pbl_driver(grid)
END SUBROUTINE first_rk_step_part1
"""

PBL_DRIVER = """SUBROUTINE pbl_driver(              &
              ,QNORM, fasdas, mp_physics &
!\n! END FASDAS\n!\n                                                                     )
   USE module_model_constants
    REAL , OPTIONAL   ,DIMENSION(ims:ime,kms:kme,jms:jme,num_scalar),INTENT(INOUT)   :: scalar_tend
CALL shinhong(grid)
END SUBROUTINE pbl_driver
"""

PART2 = """SUBROUTINE first_rk_step_part2 (grid &
                             , pr87_source_carrier, pr87_source_step    &
                            )
    USE module_state_description
    INTEGER, INTENT(OUT) :: pr87_source_step
   rk_step = 1
END SUBROUTINE first_rk_step_part2
"""

FRAGMENT = """SUBROUTINE rk_update_joint_moments( &
     pr87_cloud_rain_diffusion_delta,pr87_cloud_rain_diffusion_step)
  USE iso_fortran_env, ONLY: real32,real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  INTEGER,INTENT(IN) :: itimestep,pr87_source_step
  INTEGER,INTENT(IN),OPTIONAL :: pr87_cloud_rain_diffusion_step
  REAL(real64),ALLOCATABLE :: qs64(:,:),ns64(:,:)
  REAL(real64) :: outflow,cfl,maxcfl,source_candidate(2),source_sum64(2)
  REAL(real32) :: source_rate32(2),source_increment32(2),source_endpoint32(2)
  IF (spec_zone/=1.OR.il>ih.OR.jl>jh.OR.kl>kh) &
    CALL wrf_error_fatal('PR85 joint update unsupported domain footprint')
      qs64(cell,p)=REAL(qs(cell,p),real64); ns64(cell,p)=REAL(ns(cell,p),real64)
        source_rate32=[pr87_raw_qsrc(i,k,j,p),pr87_raw_nsrc(i,k,j,p)]
        IF (.NOT.ALL(ieee_is_finite(source_rate32))) &
          CALL wrf_error_fatal('PR87 nonfinite intensive source payload')
        source_candidate=[REAL(q1(i,k,j,qindex(p)),real64), &
                          REAL(n1(i,k,j,nindex(p)),real64)]+REAL(dt,real64)*REAL(source_rate32,real64)
        source_sum64=REAL(dt,real64)*REAL(source_rate32,real64)
        source_increment32=dt*source_rate32
        source_endpoint32=[q1(i,k,j,qindex(p)),n1(i,k,j,nindex(p))]+source_increment32
END SUBROUTINE rk_update_joint_moments
"""


def test_solve_owns_step_local_payload_and_forwards_every_boundary() -> None:
    generated = _instrument_solve(SOLVE)
    allocate = generated.index("ALLOCATE(pr87_pbl_tendency_delta64(ims:ime,kms:kme,jms:jme,4))")
    zero = generated.index("pr87_pbl_tendency_delta64 = 0.0_real64")
    producer = generated.index("CALL first_rk_step_part1")
    consumer = generated.index("CALL rk_update_joint_moments")
    assert allocate < zero < producer < consumer
    assert "pr87_pbl_tendency_step = grid%itimestep" in generated
    assert "pr87_pbl_tendency_phase = 1" in generated
    assert "pr87_pbl_tendency_delta64=pr87_pbl_tendency_delta64" in generated
    assert generated.count(", pr87_pbl_tendency_delta64, pr87_pbl_tendency_step") == 2


def test_part1_pbl_driver_shinhong_route_is_explicit_and_legacy_fields_are_untouched() -> None:
    part1 = _instrument_part1(PART1)
    pbl = _instrument_pbl_driver(PBL_DRIVER)
    assert "pr87_pbl_tendency_delta64(ims:ime,kms:kme,jms:jme,4)" in part1
    assert "PR87_TENDENCY_DELTA64=pr87_pbl_tendency_delta64" in part1
    assert "REAL(real64), INTENT(INOUT) :: pr87_tendency_delta64" in pbl
    assert "PR87_TENDENCY_DELTA64=pr87_tendency_delta64" in pbl
    assert "moist_tend" not in part1
    assert pbl.count(":: scalar_tend") == PBL_DRIVER.count(":: scalar_tend")
    assert "scalar_tend=" not in pbl


def test_part2_checks_payload_epoch_without_modifying_it() -> None:
    generated = _instrument_part2(PART2)
    assert "REAL(real64), INTENT(IN) :: pr87_pbl_tendency_delta64" in generated
    assert "pr87_pbl_tendency_step /= grid%itimestep" in generated
    assert "pr87_pbl_tendency_phase /= 1" in generated
    assert "pr87_pbl_tendency_delta64 =" not in generated


def test_native_uses_weighted_raw_delta_and_later_terms_once() -> None:
    generated = _instrument_fragment(FRAGMENT)
    assert "(REAL(pr87_raw_qsrc(i,k,j,p),real64)+ &" in generated
    assert "pr87_pbl_tendency_delta64(i,k,j,1))*REAL(pr87_source_carrier(i,k,j),real64)+ &" in generated
    assert "pr87_later_qsrc(i,k,j,p)" in generated
    assert "pr87_pbl_tendency_delta64(i,k,j,2))*REAL(pr87_source_carrier(i,k,j),real64)+ &" in generated
    assert "source_rate64=source_rate64+ &" in generated
    assert "source_candidate=[REAL(q1(i,k,j,qindex(p)),real64), &" in generated
    assert "REAL(dt,real64)*source_rate64" in generated
    assert "volume_number_bounds=number_bounds(cell,:,p)" in generated
    assert "pr87_cloud_rain_diffusion_delta(i,k,j,1)" not in generated
    assert "pbl_source_correction_sum(pbl_channel)+pbl_delta" in generated
    assert "pbl_delta=REAL(dt,real64)*pr87_source_carrier(i,k,j)*" in generated
    assert "'PR87_PBL_SOURCE_CORRECTION_RK', &\n       itimestep,rk" in generated
    assert "pbl_carrier_min,pbl_carrier_max" in generated
    assert "pbl_source_correction_l1,pbl_source_correction_max" in generated
    assert "PR87 PBL source carrier mismatch" not in generated
    assert "pr87_pbl_tendency_step/=itimestep" in generated
    assert "pr87_pbl_tendency_phase/=1" in generated


def test_source_pins_are_fail_closed() -> None:
    sources = {name: "source" for name in PINNED_SHA256}
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _require_hashes(sources)


def test_final_source_rate_gate_uses_assigned_real64_payload() -> None:
    transformed = finalize_source_rate_validation(_instrument_fragment(FRAGMENT))
    assert "source_rate32" not in transformed
    assignment = transformed.index("source_rate64=[REAL(pr87_raw_qsrc")
    validation = transformed.index("ieee_is_finite(source_rate64)")
    assert assignment < validation
    assert transformed.count("ieee_is_finite(source_rate64)") == 1
    with pytest.raises(ValueError, match="stale REAL32 source-rate declaration"):
        finalize_source_rate_validation(transformed)


@pytest.mark.parametrize("optimization", ["O0", "O2"])
def test_final_real64_finiteness_gate_rejects_nan_and_infinity(optimization: str) -> None:
    transformed = finalize_source_rate_validation(_instrument_fragment(FRAGMENT))
    match = re.search(
        r"(?m)^        IF \(\.NOT\.ALL\(ieee_is_finite\(source_rate64\)\)\) &\n"
        r"          CALL wrf_error_fatal\('PR87 nonfinite intensive source payload'\)\n",
        transformed,
    )
    assert match is not None
    assert transformed.count(match.group(0)) == 1
    extracted_guard = match.group(0).replace(
        "CALL wrf_error_fatal('PR87 nonfinite intensive source payload')",
        "rejected=.TRUE.",
    )
    program = f"""program test_real64_source_rate_gate
  use, intrinsic :: iso_fortran_env, only: real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite, ieee_value, ieee_quiet_nan, ieee_positive_inf
  implicit none
  real(real64) :: source_rate64(2)
  logical :: rejected
  source_rate64=[1.0_real64,2.0_real64]
  rejected=.FALSE.
{extracted_guard.rstrip()}
  if (rejected) error stop 'finite source rate rejected'
  source_rate64(1)=ieee_value(0.0_real64,ieee_quiet_nan)
  rejected=.FALSE.
{extracted_guard.rstrip()}
  if (.not.rejected) error stop 'NaN source rate accepted'
  source_rate64=[1.0_real64,ieee_value(0.0_real64,ieee_positive_inf)]
  rejected=.FALSE.
{extracted_guard.rstrip()}
  if (.not.rejected) error stop 'infinite source rate accepted'
  print '(a)', 'PR87 REAL64 source-rate gate PASS'
end program test_real64_source_rate_gate
"""
    with tempfile.TemporaryDirectory(
        prefix=f"pr87_source_rate_gate_{optimization}_", dir="/var/tmp"
    ) as tmp:
        scratch = Path(tmp)
        source_path = scratch / "test_real64_source_rate_gate.F90"
        executable = scratch / "test_real64_source_rate_gate.exe"
        source_path.write_text(program)
        flags = "-O0" if optimization == "O0" else "-O2"
        script = f"""
set -euo pipefail
source '{TOOLCHAIN}'
"$CLOUD_BAL_FC" -stand f08 -warn all -check all -fpe0 -traceback {flags} \\
  -fp-model strict -fimf-arch-consistency=true -no-ftz \\
  '{source_path}' -o '{executable}'
'{executable}'
"""
        result = subprocess.run(
            ["bash", "-lc", script], cwd=scratch, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        assert result.returncode == 0, result.stdout
        assert "PR87 REAL64 source-rate gate PASS" in result.stdout
