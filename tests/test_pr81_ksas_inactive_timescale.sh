#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1
export LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib:${LD_LIBRARY_PATH:-}
source_root=${PR81_NATIVE_SOURCE_ROOT:-/var/tmp/pr61_ccn_origin_20261006/hostcopy}
scratch=${1:-$(mktemp -d /var/tmp/pr81_ksas_timescale_test.XXXXXX)}
if (($# > 0)) && [[ -e "$scratch" ]]; then
  printf 'refusing to reuse test scratch: %s\n' "$scratch" >&2
  exit 2
fi
mkdir -p "$scratch/source/phys" "$scratch/module"
cp "$source_root/phys/module_cu_ksas.F" "$scratch/source/phys/"
cp "$source_root/phys/module_cu_ksas.f90" "$scratch/source/phys/"
(cd "$scratch/source" && patch --fuzz=0 -p1 \
  < "$repo_root/patches/controlled.cu_ksas_inactive_timescale.patch")
[[ $(sha256sum "$scratch/source/phys/module_cu_ksas.f90" | cut -d' ' -f1) == \
  5c54215b5bb90771f0eda1cfc14e0b4df90ba78bc48a0459159567fa38d0aff1 ]]

python3 - "$scratch/source/phys/module_cu_ksas.f90" "$scratch/test.F90" <<'PY'
from pathlib import Path
import sys
source, output = map(Path, sys.argv[1:])
text = source.read_text()
start = text.index('   do i = its,ite\n     if (cnvflg(i)) then\n       if (wc(i) <= 0.)')
end = text.index('   enddo', text.index('     endif', start)) + len('   enddo')
loop = text[start:end]
program = '''program test_ksas_dtconv
  implicit none
  integer :: mode
  character(len=16) :: argument
  call get_command_argument(1, argument)
  read(argument, *) mode
  call evaluate(mode)
contains
  subroutine evaluate(mode)
    implicit none
    integer, intent(in) :: mode
    integer :: i, its, ite
    integer :: ktcon1(1:1), kbcon1(1:1)
    logical :: cnvflg(1:1)
    real :: wc(1:1), zi(1:1,1:2), dtconv(1:1), dtmin, dtmax, tfac, tem
    external :: wrf_error_fatal
    its = 1
    ite = 1
    wc = 0.
    zi(1,:) = [5., 15.]
    ktcon1 = 0
    kbcon1 = 0
    dtconv = 3600.
    dtmin = 3.
    dtmax = 10.
    tfac = 4.
    cnvflg = mode /= 0
    if (mode == 1) then
      wc(1) = 2.
      ktcon1(1) = 2
      kbcon1(1) = 1
    else if (mode == 2) then
      wc(1) = 10.
      tfac = 1.
      ktcon1(1) = 2
      kbcon1(1) = 1
    endif
'''+''.join('  '+line if line.strip() else line for line in loop.splitlines(True))+'''
    select case (mode)
    case (0)
      if (dtconv(1) /= 0.) error stop 1
    case (1)
      if (dtconv(1) /= dtmax) error stop 2
    case (2)
      if (dtconv(1) /= dtmin) error stop 3
    case (3)
      error stop 'active wc=0 did not call WRF fatal'
    end select
  end subroutine evaluate
end program test_ksas_dtconv

subroutine wrf_error_fatal(message)
  implicit none
  character(len=*), intent(in) :: message
  error stop 77
end subroutine wrf_error_fatal
'''
output.write_text(program)
PY

compile_test() {
  local label=$1
  shift
  (cd "$scratch" && "$CLOUD_BAL_FC" -free -qopenmp -convert big_endian "$@" \
    -module "$scratch/module" -I"$scratch/module" \
    "$scratch/test.F90" -o "$scratch/test_$label.exe") \
    > "$scratch/compile_$label.log" 2>&1
  "$scratch/test_$label.exe" 0
  "$scratch/test_$label.exe" 1
  "$scratch/test_$label.exe" 2
  local status=0
  "$scratch/test_$label.exe" 3 > "$scratch/bad_wc_$label.log" 2>&1 || status=$?
  [[ $status -eq 77 ]]
}

compile_test O0 "${CLOUD_BAL_FREE_FLAGS[@]}"
compile_test O2 "${CLOUD_BAL_REPRO_FLAGS[@]}"
printf 'PR81_KSAS_TIMESCALE_TEST_ROOT %s\n' "$scratch"
