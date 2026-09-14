#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo/tests/intel_toolchain.sh"
work=$(mktemp -d "$repo/scratch/barnes_time_weight.XXXXXX")
printf '%s\n' "$work"
cd "$work"
source_file="$repo/src/upstream/wind_openmp/barnes_multivariate.f90"
sha256sum "$source_file" "$repo/tests/test_barnes_time_weight.f90" \
  "$repo/tests/run_barnes_time_weight.sh" "$repo/tests/intel_toolchain.sh" > inputs.sha256
# Compile the exact standalone source routine, without substituting its logic.
python3 - "$source_file" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]).read_bytes()
marker=b'      subroutine get_time_wt('
assert source.count(marker)==1
Path('get_time_wt.f90').write_bytes(source[source.index(marker):])
PY
export OMP_NUM_THREADS=38 OMP_DYNAMIC=false OMP_STACKSIZE=128M
ulimit -s unlimited
for opt in O0 O2; do
  checks=()
  [[ $opt != O0 ]] || checks=(-check all)
  "$CLOUD_BAL_FC" -"$opt" -g -traceback "${checks[@]}" -fp-model strict -no-ftz \
    -qopenmp get_time_wt.f90 "$repo/tests/test_barnes_time_weight.f90" -o "test_$opt"
  timeout 60 "./test_$opt" > "$opt.log" 2>&1
  python3 - "$opt.log" <<'PY'
from pathlib import Path
import sys
lines=Path(sys.argv[1]).read_text().splitlines()
message='Error, check times in get_time_wt'
assert sum(line.strip()==message for line in lines)==2048
assert len(lines)==2049
assert 'BARNES_TIME_WEIGHT_PARALLEL_PASS' in lines[-1]
print(sys.argv[1]+': 2048 complete diagnostics; 4096 status/weight checks; 38 threads PASS')
PY
done
sha256sum -c inputs.sha256
