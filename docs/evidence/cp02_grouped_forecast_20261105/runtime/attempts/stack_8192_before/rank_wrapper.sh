#!/usr/bin/env bash
set -euo pipefail
"${GROUPED_PYTHON:?}" - <<'PY'
import json,os
from pathlib import Path
rank=int(os.environ['PMI_RANK']); cpus=[int(x) for x in os.environ['GROUPED_CPUS'].split(',')]
actual=sorted(os.sched_getaffinity(0))
if not 0<=rank<8 or actual!=[cpus[rank]]:
    raise RuntimeError(f'Unexpected rank affinity: {rank}: {actual}')
with Path(f'affinity_rank{rank}.json').open('x') as stream:
    json.dump({'rank':rank,'wrapper_exec_pid':os.getppid(),'cpus':actual},stream)
    stream.write('\n')
PY
exec ./wrf.exe
