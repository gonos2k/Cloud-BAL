#!/usr/bin/env python3
"""Compile and run the pinned KDM6 ice-size transition expressions with Intel ifx."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/var/tmp/pr84_ice_entry_guard_final_1efgtcsn/compile/module_mp_kdm6.F")
PROFILE = ROOT / "tests/intel_toolchain.sh"
SOURCE_SHA256 = "f7fb216c82822162c30148829f207deeee5900e46e01ad9082ac58c802a181d9"
SOURCE_FORM_SHA256 = "06a985ba7f85268fbf6dab5b76adfe2c32f080807744aded8e27c1b5bb825f3c"
PIDNI = 1570.79638671875


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_line(source: str, pattern: str, *, last: bool = False) -> str:
    matches = [line for line in source.splitlines() if pattern in line]
    if not matches or (len(matches) != 1 and not last):
        raise SystemExit(f"expected one source line containing {pattern!r}, found {len(matches)}")
    return matches[-1] if last else matches[0]


def source_block(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin) + len(end)
    return source[begin:finish]


def run(argv: list[str], cwd: Path, log: Path) -> str:
    command = " ".join(shlex.quote(arg) for arg in argv)
    completed = subprocess.run(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; exec {command}"],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log.write_text(completed.stdout)
    if completed.returncode:
        raise SystemExit(completed.stdout)
    return completed.stdout


def make_driver(source: str) -> str:
    # These are the exact KDM6 statements: PSD slope, ice sedimentation, mean
    # diameter, and the existing ice-to-snow transfer branch.
    lamdai = source_line(source, "lamdai(x,y,z)= exp(log(((pidni*z)/(x*y)))*(1./dmi))")
    slope = source_block(
        source,
        "           rslope(i,k,4) =max(min(1./lamdai(qci(i,k),den(i,k),nci(i,k)),1./lamdaimin), &",
        "                          1./lamdaimax)",
    )
    sediment = source_block(
        source,
        "             dqi(i,k) = min(falk(i,k,4)*dtcld/dend(i,k),qci(i,k,2))",
        "             qci(i,k,2) = max(qci(i,k,2)-dqi(i,k)+dqi(i,k+1),0.)",
    )
    diameter = source_line(
        source, "          avedia(i,k,3) = rslope(i,k,4)*((g4pmi/g1pmi)**(.3333333))", last=True
    )
    transition = source_block(
        source,
        "        if (qci(i,k,2).ge. qmin .and.t(i,k).lt.273.15) then",
        "        end if\n        end if",
    )
    return f'''program pr85_ice_transition_regression
  implicit none
  real, parameter :: pidni={PIDNI:.17g}, dmi=3.0, lamdaimin=9.08e3, lamdaimax=1.82e6
  real, parameter :: qmin=1.0e-14
  integer :: failures
  failures=0
  call exercise(9080.0, .true., 'lambda_min')
  call exercise(9085.5, .true., 'inside reachable interval')
  call exercise(9085.61, .false., 'above reachable endpoint')
  if (failures /= 0) error stop 1
  print '(a)', 'PR85 source-form ice transition cases PASS'
contains
  subroutine exercise(lambda_target, should_transfer, label)
    real, intent(in) :: lambda_target
    logical, intent(in) :: should_transfer
    character(len=*), intent(in) :: label
    real :: qci(1,2,2), nci(1,2,2), qrs(1,2,3), rslope(1,2,4), avedia(1,2,3)
    real :: den(1,2), falk(1,2,4), falkn(1,2,2), falln(1,2,2), dend(1,2), delz(1,2)
    real :: dqi(1,2), dni(1,2), dtcld, t(1,2), g4pmi, g1pmi
    real :: qi_before, qs_before, ni_before, diameter_um
    integer :: i,k
    i=1; k=1; dtcld=1.0; qci=0.0; nci=0.0; qrs=0.0
    den=1.0; falk=0.0; falkn=0.0; falln=0.0; dend=1.0; delz=1.0
    t=260.0; g1pmi=1.0; g4pmi=6.0
    qci(i,k,2)=1.0e-3
    nci(i,k,2)=qci(i,k,2)*lambda_target**3/pidni
    qrs(i,k,2)=2.0e-4
    ! Sedimentation is active before the transition: remove 10% of each ice moment.
    falk(i,k,4)=0.1*qci(i,k,2); falkn(i,k,2)=0.1*nci(i,k,2)
    falk(i,k+1,4)=0.0; falkn(i,k+1,2)=0.0
    dqi=0.0; dni=0.0
    {sediment}
    qi_before=qci(i,k,2); qs_before=qrs(i,k,2); ni_before=nci(i,k,2)

    ! slope_kdm6 uses rank-2 QI/NI arrays for this same ice category.
    call source_slope(qci(:,:,2),nci(:,:,2),den,rslope,pidni)
    {diameter}
    diameter_um=avedia(i,k,3)*1.0e6
    {transition}
    if (abs(qi_before-9.0e-4)>2.0e-7 .or. abs(qs_before-2.0e-4)>1.0e-8 .or. &
        abs(ni_before-0.9*(1.0e-3*lambda_target**3/pidni))>max(1.0e-7,abs(ni_before)*2.0e-6)) then
      print '(a,3(es15.7,1x))', 'FAIL sedimentation before transition: ',qi_before,qs_before,ni_before
      failures=failures+1
    endif
    if (should_transfer) then
      if (diameter_um < 200.0 .or. qci(i,k,2)/=0.0 .or. nci(i,k,2)/=0.0 .or. &
          abs(qrs(i,k,2)-(qs_before+qi_before))>1.0e-8) then
        print '(a,a,a,es15.7)', 'FAIL transfer ',label,' diameter_um=',diameter_um
        failures=failures+1
      endif
    else
      if (diameter_um >= 200.0 .or. qci(i,k,2)/=qi_before .or. nci(i,k,2)/=ni_before .or. &
          qrs(i,k,2)/=qs_before) then
        print '(a,a,a,es15.7)', 'FAIL no-transfer ',label,' diameter_um=',diameter_um
        failures=failures+1
      endif
    endif
    print '(a,a,a,es15.7,a,3(es15.7,1x),a,3(es15.7,1x))', &
      'CASE ',label,' diameter_um=',diameter_um,' before(QI,QS,NI)=',qi_before,qs_before,ni_before, &
      ' after(QI,QS,NI)=',qci(i,k,2),qrs(i,k,2),nci(i,k,2)
  end subroutine exercise
  subroutine source_slope(qci,nci,den,rslope,pidni)
    real, intent(in) :: qci(:,:),nci(:,:),den(:,:),pidni
    real, intent(out) :: rslope(:,:,:)
    real, parameter :: dmi=3.0,lamdaimin=9.08e3,lamdaimax=1.82e6
    real :: lamdai,x,y,z
    integer :: i,k
    {lamdai}
    i=1; k=1; x=den(i,k); y=qci(i,k); z=nci(i,k)
    {slope}
  end subroutine source_slope
end program
'''


def main() -> None:
    fixture_value = os.environ.get("PR85_ICE_TRANSITION_FIXTURE")
    source_hash = SOURCE_SHA256
    fixture_path = Path(fixture_value).resolve(strict=True) if fixture_value else None
    if fixture_path is not None:
        if sha(fixture_path) != SOURCE_FORM_SHA256:
            raise SystemExit(f"pinned KDM6 source-form fixture SHA mismatch: {fixture_path}")
        driver_bytes = fixture_path.read_bytes()
    else:
        source_bytes = SOURCE.read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        if source_hash != SOURCE_SHA256:
            raise SystemExit(f"pinned KDM6 source SHA mismatch: {source_hash}")
        driver_bytes = make_driver(source_bytes.decode("latin-1")).encode()
        if hashlib.sha256(driver_bytes).hexdigest() != SOURCE_FORM_SHA256:
            raise SystemExit("extracted KDM6 source-form fixture differs from its pinned bytes")
    scratch = Path(tempfile.mkdtemp(prefix="pr85_ice_transition_", dir="/var/tmp"))
    source_dir = scratch / "source"
    source_dir.mkdir()
    driver = source_dir / "pr85_source_form_driver.F90"
    driver.write_bytes(driver_bytes)
    ifx = subprocess.check_output(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; printf %s \"$CLOUD_BAL_FC\""], text=True
    ).strip()
    results = {}
    for opt in ("-O0", "-O2"):
        build = scratch / opt[1:]
        build.mkdir()
        exe = build / "pr85_ice_transition.exe"
        argv = [ifx, "-stand", "f08", "-warn", "all", "-fpe0", "-traceback",
                opt, "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz",
                *(["-check", "all"] if opt == "-O0" else []), str(driver), "-o", str(exe)]
        compile_output = run(argv, build, build / "compile.log")
        output = run([str(exe)], build, build / "run.log")
        if "PR85 source-form ice transition cases PASS" not in output:
            raise SystemExit(f"source-form transition regression failed at {opt}: {output}")
        results[opt] = {
            "argv": argv,
            "argv_nul_sha256": hashlib.sha256(b"\0".join(os.fsencode(x) for x in argv) + b"\0").hexdigest(),
            "executable_sha256": sha(exe),
            "compile_stdout": compile_output,
            "stdout": output,
        }
    receipt = {
        "schema": "pr85_kdm6_ice_transition_source_form_o0_o2_v1",
        "scratch": str(scratch),
        "runtime_model_call": False,
        "source_path": str(SOURCE),
        "source_sha256": source_hash,
        "source_form_fixture_path": str(fixture_path) if fixture_path else None,
        "source_form_fixture_sha256": sha(driver),
        "generated_driver_sha256": sha(driver),
        "compiler_profile": str(PROFILE),
        "compiler_profile_sha256": sha(PROFILE),
        "compiler": ifx,
        "source_constants": {"pidni_real32": PIDNI, "dmi": 3.0, "lambda_min_m-1": 9080.0,
                             "lambda_max_m-1": 1820000.0, "mui": 0.0},
        "results": results,
    }
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
