#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source_root=${PR82_KDM6_SOURCE:?set PR82_KDM6_SOURCE to the hash-bound instrumented KDM6 source}
[[ -f "$source_root" ]] || { printf 'instrumented KDM6 source missing: %s\n' "$source_root" >&2; exit 2; }
for opt in O0 O2; do
  scratch=$(mktemp -d "/var/tmp/pr82_number_trace_${opt}.XXXXXX")
  python3 - "$source_root" "$scratch/pr82_number_trace_helpers.f90" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
start = source.index('    pure function number_conversion_error_class(')
end = source.index('    end subroutine log_number_conversion_rejection', start) + len('    end subroutine log_number_conversion_rejection')
helpers = source[start:end]
Path(sys.argv[2]).write_text('module pr82_number_trace_helpers\n  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite\n  use, intrinsic :: iso_c_binding, only: c_int\ncontains\n' + helpers + '\nend module pr82_number_trace_helpers\n')
PY
  flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  if [[ $opt == O2 ]]; then flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
  argv=("$CLOUD_BAL_FC" -free "${flags[@]}" "$scratch/pr82_number_trace_helpers.f90" "$repo_root/tests/pr82_number_trace_helpers.f90" -o "$scratch/test_pr82_number_trace_helpers")
  printf '%s\0' "${argv[@]}" > "$scratch/compile_argv.nul"
  (cd "$scratch" && "${argv[@]}") > "$scratch/compile.log" 2>&1
  (cd "$scratch" && ./test_pr82_number_trace_helpers) > "$scratch/run.log" 2>&1
  rg -q '^PR82_HELPER_PASS$' "$scratch/run.log"
  python3 - "$scratch/number_basis_rejection.raw" <<'PY'
from pathlib import Path
import sys
line = Path(sys.argv[1]).read_text().strip()
fields = line.split(',')
expected = ['NUMBER_BASIS_REJECT','NC','INPUT','17','2','4','0DA24260','0DA24260','00000000','00009FFD','00009FFD','0','0','POSITIVE_TO_ZERO']
if fields != expected:
    raise SystemExit(f'helper trace row mismatch: {fields!r}')
PY
  printf 'PR82_HELPER %s PASS %s\n' "$opt" "$scratch"
done
