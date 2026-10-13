#!/usr/bin/env python3
"""Test the byte-extracted PR84 helper with pinned ifx at O0 and O2."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/var/tmp/pr80_kdm6_radar_contract.nsUNuj/compile/module_mp_kdm6.F")
PROFILE = ROOT / "tests/intel_toolchain.sh"
PATCH = ROOT / "patches/pr84_ice_entry_psd_guard.patch"
EXPECTED_SOURCE = "a5e8ce7a05d147b05556aa7521c22c0991812711fe675409feec889e43a761e7"
PIDNI = 1570.79638671875
LAMBDA_MIN = 9080.0


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv: list[str], cwd: Path, log: Path) -> str:
    quoted = " ".join(shlex.quote(x) for x in argv)
    result = subprocess.run(["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; exec {quoted}"],
                            cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text(result.stdout)
    if result.returncode:
        raise SystemExit(result.stdout)
    return result.stdout


def main() -> None:
    if sha(SOURCE) != EXPECTED_SOURCE:
        raise SystemExit("pinned KDM6 source SHA mismatch")
    ifx = subprocess.check_output(["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; printf %s \"$CLOUD_BAL_FC\""]
                                  , text=True).strip()
    scratch = Path(tempfile.mkdtemp(prefix="pr84_ice_guard_o0_o2_", dir="/var/tmp"))
    srcdir = scratch / "source"
    srcdir.mkdir()
    patched = srcdir / "module_mp_kdm6.F"
    patched.write_bytes(SOURCE.read_bytes())
    subprocess.run(["patch", "-d", str(srcdir), "-p2", "-i", str(PATCH)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    source_hash = sha(patched)
    body = patched.read_text().split("    ! PR84_KDM6_ICE_ENTRY_CEILING_BEGIN\n", 1)[1].split(
        "    ! PR84_KDM6_ICE_ENTRY_CEILING_END", 1)[0]
    module = srcdir / "pr84_exact_extracted_helper.F90"
    module.write_text("module pr84_probe_module\n  implicit none\ncontains\n" + body + "end module\n")
    driver = srcdir / "pr84_helper_probe_driver.F90"
    driver.write_text(f'''program pr84_helper_probe_driver
  use, intrinsic :: ieee_arithmetic, only : ieee_value, ieee_quiet_nan
  use pr84_probe_module, only : pr84_ice_entry_ceiling
  implicit none
  real :: cap, rho, lam, shape, pidni, qn
  logical :: ok
  integer :: failures
  failures = 0
  lam = {LAMBDA_MIN:.1f}; pidni = {PIDNI:.17g}; shape = 3.0
  rho = 0.6824867725372314
  call pr84_ice_entry_ceiling(0.0,rho,lam,shape,pidni,cap,ok)
  call check(ok .and. transfer(cap,0)==int(z'49742400'),'zero QI')
  call pr84_ice_entry_ceiling(1.0e-4,rho,lam,shape,pidni,cap,ok)
  call check(ok .and. transfer(cap,0)==int(z'49742400'),'low-IWC cap')
  call pr84_ice_entry_ceiling(0.0033685904927551746,rho,lam,shape,pidni,cap,ok,qn)
  call check(ok .and. transfer(qn,0)==int(z'49C3F90E'),'high-cell public minimum')
  call check(ok .and. transfer(cap,0)==int(z'4985BFB7'),'high-cell entry ceiling')
  call pr84_ice_entry_ceiling(0.0007856728043407202,0.4555096924304962,lam,shape,pidni,cap,ok,qn)
  call check(ok .and. transfer(qn,0)==int(z'48B6D4B2'),'one-ULP roundtrip advance')
  call check(ok .and. transfer(cap,0)==int(z'49742400'),'one-ULP keeps low-IWC ceiling')
  call pr84_ice_entry_ceiling(1.0e-3,0.0,lam,shape,pidni,cap,ok)
  call check(.not.ok .and. cap==0.0,'zero density fails closed')
  call pr84_ice_entry_ceiling(ieee_value(0.0,ieee_quiet_nan),rho,lam,shape,pidni,cap,ok)
  call check(.not.ok .and. cap==0.0,'NaN QI fails closed')
  call pr84_ice_entry_ceiling(1.0e30,rho,lam,shape,pidni,cap,ok)
  call check(.not.ok .and. cap==0.0,'REAL32 overflow fails closed')
  call pr84_ice_entry_ceiling(1.0e-3,ieee_value(0.0,ieee_quiet_nan),lam,shape,pidni,cap,ok)
  call check(.not.ok .and. cap==0.0,'NaN density fails closed')
  if (failures /= 0) error stop 1
  print '(a)','PR84 helper cases PASS'
contains
  subroutine check(condition,label)
    logical,intent(in)::condition
    character(len=*),intent(in)::label
    if(.not.condition) then
      failures=failures+1
      print '(a)','FAIL: '//label
    endif
  end subroutine
end program
''')
    results = {}
    for opt in ("-O0", "-O2"):
        out = scratch / opt[1:]
        out.mkdir()
        exe = out / "probe.exe"
        argv = [ifx, "-stand", "f08", "-warn", "all", "-check", "all", "-fpe0", "-traceback",
                opt, "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz",
                str(module), str(driver), "-o", str(exe)]
        run(argv, out, out / "compile.log")
        output = run([str(exe)], out, out / "run.log")
        if "PR84 helper cases PASS" not in output:
            raise SystemExit(f"helper probe failed at {opt}: {output}")
        results[opt] = {"argv": argv, "argv_nul_sha256": hashlib.sha256(
            b"\0".join(os.fsencode(x) for x in argv)+b"\0").hexdigest(),
            "executable_sha256": sha(exe), "stdout": output}
    receipt = {"schema":"pr84_native_ice_guard_o0_o2_probe_v1", "scratch":str(scratch),
               "model_run":False, "source_path":str(SOURCE), "source_sha256":EXPECTED_SOURCE,
               "patch_sha256":sha(PATCH), "patched_source_sha256":source_hash,
               "extracted_helper_module_sha256":sha(module), "driver_sha256":sha(driver),
               "compiler":ifx, "profile":str(PROFILE), "profile_sha256":sha(PROFILE),
               "native_parameters":{"pidni_real32":PIDNI,"pidni_bits":"0x44C4597C",
                                    "lambda_min_real32":LAMBDA_MIN,"lambda_min_bits":"0x460DE000"},
               "results":results}
    (scratch/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt,indent=2))


if __name__ == "__main__":
    main()
