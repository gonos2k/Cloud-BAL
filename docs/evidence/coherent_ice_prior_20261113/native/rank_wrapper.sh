#!/usr/bin/env bash
set -euo pipefail
/usr/bin/python3 - <<'PY'
import json,os,resource
from pathlib import Path
rank=int(os.environ['PMI_RANK']);cpus=list(map(int,os.environ['GROUPED_CPUS'].split(',')));actual=sorted(os.sched_getaffinity(0));stack=resource.getrlimit(resource.RLIMIT_STACK)
if stack[0]!=resource.RLIM_INFINITY or actual!=[cpus[rank]]:raise RuntimeError((rank,actual,stack))
Path(f'affinity_rank{rank}.json').write_text(json.dumps({'rank':rank,'cpus':actual,'stack_limits':stack})+'\n')
PY
exec /usr/bin/gdb -q -batch -ex 'set debuginfod enabled off' -ex 'file ./wrf.exe' -ex 'source ../../capture.py' -ex run
