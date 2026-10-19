"""Intel caller regression extracted from the frozen full V42 KDM6 source."""
from __future__ import annotations

import gzip
import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_GZ = ROOT / "docs/evidence/pr87_two_step_v42_20261016/module_mp_kdm6.F.gz"
SOURCE_SHA256 = "bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a"
RESULT_RE = re.compile(r"^RESULT\s+(\d+)\s+(\d+)\s+([0-9.E+-]+)\s+([0-9.E+-]+)\s+([0-9.E+-]+)\s+([0-9.E+-]+)$")


def _extract_once(source: str, start: str, end: str, label: str) -> str:
    if source.count(start) != 1:
        raise AssertionError(f"pinned source extraction anchor drifted: {label}")
    begin = source.index(start)
    if end not in source[begin:]:
        raise AssertionError(f"pinned source extraction end anchor missing: {label}")
    finish = source.index(end, begin)
    if finish <= begin:
        raise AssertionError(f"invalid pinned source extraction order: {label}")
    return source[begin:finish]


def _pinned_source() -> str:
    source = gzip.decompress(SOURCE_GZ.read_bytes()).decode("utf-8")
    actual = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if actual != SOURCE_SHA256:
        raise AssertionError(f"frozen V42 source hash mismatch: {actual}")
    return source


def _caller_blocks(source: str) -> tuple[str, str, str, str]:
    inner = _extract_once(
        source,
        "          pr87_rain_qrate(kts:kte) = 0.0d0\n",
        "        k = kte\n",
        "rain Q/N helper call gate",
    )
    top = _extract_once(
        source,
        "        k = kte\n        do i = its, ite\n",
        "       do k = kte_in-1,kts,-1\n",
        "top fall/falln sweep",
    )
    lower = _extract_once(
        source,
        "       do k = kte_in-1,kts,-1\n",
        "        do k = kts, kte\n          do i = its, ite\n          qrs_tmp",
        "lower fall/falln sweep",
    )
    interface = _extract_once(
        source,
        "   interface\n      subroutine pr85_kdm6_paired_sediment_column(",
        "   end interface\n",
        "paired helper interface",
    )
    return inner, top, lower, interface + "   end interface\n"


def _harness(source: str) -> str:
    inner, top, lower, interface = _caller_blocks(source)
    # These values make the last column inactive on n=2, while columns 1 and 2
    # still have distinct helper rates and must add them to their own falls.
    declarations = """\
program rain_flux_caller
  implicit none
  integer, parameter :: its=1, ite=3, kts=1, kte=3, kte_in=3
  integer, parameter :: PR87_SED_RAIN=3
  integer :: i,k,n,lat,pr87_rain_unit,mstepmax,pr87_model_timestep
  integer :: mstep(its:ite)
  real :: dtcld,qcrmin,nrmin,pidnr,dmr,lamdarmin,lamdarmax
  real :: dend(its:ite,kts:kte),delz(its:ite,kts:kte)
  real :: qrs(its:ite,kts:kte,1:3),nrs(its:ite,kts:kte,1)
  double precision :: mass_velocity_rate(its:ite,kts:kte,1:4)
  double precision :: number_velocity_rate(its:ite,kts:kte,1)
  real :: qrs_tmp(its:ite,kts:kte,1:3)
  real :: falk(its:ite,kts:kte,1:4),falkn(its:ite,kts:kte,1)
  real :: falkb(its:ite,kts:kte),fall(its:ite,kts:kte,1:4)
  real :: falln(its:ite,kts:kte,1),fallb(its:ite,kts:kte)
  real :: dqs(its:ite,kts:kte+1)
  double precision :: pr87_rain_qrate(kts:kte),pr87_rain_nrate(kts:kte)
  logical :: pr87_rain_valid
"""
    stub = """\
subroutine pr85_kdm6_paired_sediment_column(kts,kte,cell_i,lat,substep,dt,mstep, &
     dry_density,delz,mass_rate,second_rate,qstate,second_state,mode,q_active_min, &
     second_active_min,density_min,density_max,approved_q_rate,approved_second_rate, &
     budget_unit,trace,valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)
  implicit none
  integer,intent(in) :: kts,kte,cell_i,lat,substep,mstep,budget_unit,mode
  real,intent(in) :: dt,dry_density(kts:kte),delz(kts:kte)
  double precision,intent(in) :: mass_rate(kts:kte),second_rate(kts:kte)
  real,intent(inout) :: qstate(kts:kte),second_state(kts:kte)
  real,intent(in) :: q_active_min,second_active_min,density_min,density_max
  double precision,intent(out) :: approved_q_rate(kts:kte),approved_second_rate(kts:kte)
  logical,intent(in) :: trace
  logical,intent(out) :: valid
  real,intent(in) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max
  integer :: k
  do k=kts,kte
    approved_q_rate(k)=dble(cell_i*100+substep*10+k)
    approved_second_rate(k)=dble(cell_i*1000+substep*100+k)
  enddo
  valid=.true.
end subroutine pr85_kdm6_paired_sediment_column
"""
    return (
        declarations + interface + "\n"
        "  lat=2; pr87_rain_unit=99; dtcld=20.0\n"
        "  qcrmin=1.e-9; nrmin=1.e-9; pidnr=1.0; dmr=3.0\n"
        "  lamdarmin=1.0; lamdarmax=2.0\n"
        "  mstep=[2,2,1]; mstepmax=maxval(mstep)\n"
        "  dend=1.0; delz=1.0; qrs=0.0; nrs=0.0\n"
        "  mass_velocity_rate=0.0; number_velocity_rate=0.0\n"
        "  falk=0.0; falkn=0.0; falkb=0.0; fall=0.0; falln=0.0; fallb=0.0; dqs=0.0\n"
        "  do n=1,mstepmax\n"
        "    do i=its,ite\n" + inner +
        top + lower +
        "  enddo\n"
        "  do i=its,ite\n"
        "    do k=kts,kte\n"
        "      write(*,'(a,2(1x,i0),4(1x,es24.16))') 'RESULT',i,k, &\n"
        "        falk(i,k,1),falkn(i,k,1),fall(i,k,1),falln(i,k,1)\n"
        "    enddo\n"
        "  enddo\n"
        "end program rain_flux_caller\n" + stub
    )


def _results(stdout: str) -> dict[tuple[int, int], tuple[float, float, float, float]]:
    rows = {}
    for line in stdout.splitlines():
        match = RESULT_RE.match(line.strip())
        if match:
            i, k, *values = match.groups()
            rows[(int(i), int(k))] = tuple(map(float, values))
    if len(rows) != 9:
        raise AssertionError(f"caller harness emitted {len(rows)} result rows, expected 9\n{stdout}")
    return rows


def _expected() -> dict[tuple[int, int], tuple[float, float, float, float]]:
    expected = {}
    for i, mstep in enumerate((2, 2, 1), start=1):
        for k in range(1, 4):
            qrates = [i * 100 + n * 10 + k for n in range(1, mstep + 1)]
            nrates = [i * 1000 + n * 100 + k for n in range(1, mstep + 1)]
            expected[(i, k)] = (float(qrates[-1]), float(nrates[-1]),
                                float(sum(qrates)), float(sum(nrates)))
    return expected


def _run_intel_case(sources: dict[str, str], optimization: str) -> dict[str, dict]:
    script_path = ROOT / "tests/intel_toolchain.sh"
    with tempfile.TemporaryDirectory(prefix=f"pr87_rain_caller_{optimization}_", dir="/var/tmp") as directory:
        scratch = Path(directory)
        for name, source in sources.items():
            (scratch / f"{name}.f90").write_text(source, encoding="utf-8")
        bash = f"""\
set -euo pipefail
source {script_path}
if [[ {optimization} == O0 ]]; then
  flags=("${{CLOUD_BAL_FREE_FLAGS[@]}}")
else
  flags=("${{CLOUD_BAL_REPRO_FLAGS[@]}}")
fi
for name in old fixed; do
  "$CLOUD_BAL_FC" "${{flags[@]}}" "$name.f90" -o "$name.exe"
  ./$name.exe > "$name.out"
done
cat old.out
printf '%s\\n' '--- FIXED ---'
cat fixed.out
"""
        completed = subprocess.run(["bash", "-c", bash], cwd=scratch, text=True,
                                   capture_output=True, check=False)
        if completed.returncode:
            raise AssertionError(f"pinned Intel caller build failed ({optimization}):\n"
                                 f"{completed.stdout}\n{completed.stderr}")
        old_text, fixed_text = completed.stdout.split("--- FIXED ---\n", 1)
        return {"old": _results(old_text), "fixed": _results(fixed_text)}


def test_frozen_and_transformed_caller_blocks_with_heterogeneous_rates():
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import pr87_rain_flux_cache as cache

    original = _pinned_source()
    transformed, receipt = cache.transform_source(original)
    assert receipt["input_sha256"] == SOURCE_SHA256
    sources = {"old": _harness(original), "fixed": _harness(transformed)}
    expected = _expected()

    for optimization in ("O0", "O2"):
        actual = _run_intel_case(sources, optimization)
        assert actual["fixed"] == pytest.approx(expected)
        assert actual["old"] != pytest.approx(expected)

