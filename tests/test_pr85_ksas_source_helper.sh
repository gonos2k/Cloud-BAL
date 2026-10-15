#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
scratch=$(mktemp -d /var/tmp/pr85_ksas_source_helper_20261015_XXXXXX)
python3 - "$repo_root/patches/pr85_ksas_paired_source_prior.patch" "$scratch/source_helper.f90" <<'PY'
from pathlib import Path
import sys
patch_lines = Path(sys.argv[1]).read_text().splitlines()
start = next(i for i, line in enumerate(patch_lines)
             if line.startswith('+  SUBROUTINE pr85_apply_ksas_source('))
end = next(i for i, line in enumerate(patch_lines[start:], start)
           if line == '+  END SUBROUTINE pr85_apply_ksas_source')
helper_lines = []
for line in patch_lines[start:end + 1]:
    if not line.startswith('+'):
        raise SystemExit('helper body contains a non-added patch line')
    helper_lines.append(line[1:])
Path(sys.argv[2]).write_text('\n'.join(helper_lines) + '\n')
PY
cat > "$scratch/source_helper_driver.f90" <<'EOF_DRIVER'
program test_pr85_ksas_source_helper
  use, intrinsic :: ieee_arithmetic
  implicit none
  real :: qrate, qbase, nbase, mbar, ntend, nrate, effective_mbar
  integer :: status
  interface
    subroutine pr85_apply_ksas_source(qrate,qbase,nbase,mbar,ntend,nrate,effective_mbar,status)
      real, intent(in) :: qrate,qbase,nbase,mbar
      real, intent(inout) :: ntend
      real, intent(out) :: nrate,effective_mbar
      integer, intent(out) :: status
    end subroutine pr85_apply_ksas_source
  end interface

  qrate=2.0e-7; qbase=0.0; nbase=0.0; mbar=1.0e-12; ntend=3.0e5
  call pr85_apply_ksas_source(qrate,qbase,nbase,mbar,ntend,nrate,effective_mbar,status)
  if (status /= 0 .or. abs(nrate-2.0e5) > 1.0 .or. abs(ntend-5.0e5) > 1.0) error stop 1
  if (effective_mbar /= mbar) error stop 2

  qrate=-0.2; qbase=1.0; nbase=1.0e12; mbar=1.0e-12; ntend=5.0e11
  call pr85_apply_ksas_source(qrate,qbase,nbase,mbar,ntend,nrate,effective_mbar,status)
  if (status /= 0 .or. abs(nrate+2.0e11) > 1.0e5 .or. abs(ntend-3.0e11) > 1.0e5) error stop 3
  if (abs(effective_mbar-1.0e-12) > 1.0e-18) error stop 4

  qrate=-0.1; qbase=0.0; nbase=0.0; mbar=1.0e-12; ntend=0.0
  call pr85_apply_ksas_source(qrate,qbase,nbase,mbar,ntend,nrate,effective_mbar,status)
  if (status /= 2 .or. ntend /= 0.0) error stop 5

  qrate=1.0; qbase=0.0; nbase=0.0; mbar=1.0e-40; ntend=0.0
  call pr85_apply_ksas_source(qrate,qbase,nbase,mbar,ntend,nrate,effective_mbar,status)
  if (status /= 3 .or. ntend /= 0.0) error stop 6

  qrate=1.0e-20; qbase=0.0; nbase=0.0; mbar=1.0e-12; ntend=1.0e8
  call pr85_apply_ksas_source(qrate,qbase,nbase,mbar,ntend,nrate,effective_mbar,status)
  if (status /= 0 .or. nrate <= 0.0 .or. ntend /= 1.0e8) error stop 7

  qrate=1.0e-30; qbase=0.0; nbase=0.0; mbar=1.0e20; ntend=0.0
  call pr85_apply_ksas_source(qrate,qbase,nbase,mbar,ntend,nrate,effective_mbar,status)
  if (status /= 4 .or. ntend /= 0.0) error stop 8

  qrate=ieee_value(0.0,ieee_quiet_nan); qbase=0.0; nbase=0.0; mbar=1.0e-12; ntend=0.0
  call pr85_apply_ksas_source(qrate,qbase,nbase,mbar,ntend,nrate,effective_mbar,status)
  if (status /= 1 .or. ntend /= 0.0) error stop 9

  print '(a)', 'PR85 KSAS paired-source helper PASS'
end program test_pr85_ksas_source_helper
EOF_DRIVER
(
  cd "$scratch"
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
    "$scratch/source_helper.f90" "$scratch/source_helper_driver.f90" \
    -o "$scratch/test_pr85_ksas_source_helper"
  ./test_pr85_ksas_source_helper | tee "$scratch/run.log"
)
python3 - "$repo_root" "$scratch" "$CLOUD_BAL_FC" <<'PY_RECEIPT'
import hashlib
import json
from pathlib import Path
import sys
repo = Path(sys.argv[1])
scratch = Path(sys.argv[2])
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
receipt = {
    "schema": "pr85_ksas_source_helper_test_v1",
    "status": "PASS",
    "test_script": "tests/test_pr85_ksas_source_helper.sh",
    "test_script_sha256": sha(repo / "tests/test_pr85_ksas_source_helper.sh"),
    "source_attribution_patch_sha256": sha(repo / "patches/pr85_source_attribution_part2.patch"),
    "source_packet_patch_sha256": sha(repo / "patches/pr85_ksas_paired_source_prior.patch"),
    "source_policy_sha256": sha(repo / "docs/PR85_KSAS_SOURCE_PSD_POLICY_20261015.json"),
    "extracted_helper_sha256": sha(scratch / "source_helper.f90"),
    "driver_sha256": sha(scratch / "source_helper_driver.f90"),
    "run_log_sha256": sha(scratch / "run.log"),
    "scratch": str(scratch),
    "compiler": sys.argv[3],
    "compiler_profile": "tests/intel_toolchain.sh pinned ifx 2026.0",
    "compiler_profile_sha256": sha(repo / "tests/intel_toolchain.sh"),
    "flags": ["-stand", "f08", "-warn", "all", "-check", "all", "-fpe0", "-traceback", "-O0", "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz"],
    "cases": ["positive source with independent existing tendency", "proportional sink from pre-source N/Q", "reject absent-pair negative sink", "reject REAL32 overflow", "accept additive source whose REAL32 sum rounds away", "reject REAL32 source-number underflow", "reject NaN input"],
    "native_model_run": False
}
(scratch / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(f"PR85 source-helper receipt: {scratch / 'receipt.json'}")
PY_RECEIPT
