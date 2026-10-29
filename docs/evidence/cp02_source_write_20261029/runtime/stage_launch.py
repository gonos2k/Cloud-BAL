"""Freeze capture inputs and prepare an Intel MPI diagnostic launch, without running it."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('arm', choices=['OFF', 'HYDRO', 'LIQUID'])
    parser.add_argument('--prepare', type=Path, default=HERE / 'prepare.json')
    args = parser.parse_args()
    preparation = args.prepare
    record = json.loads(preparation.read_text())
    scratch = Path(record['scratch'])
    stage = scratch / args.arm
    helper = ROOT / 'docs/evidence/cp02_source_write_20261029/capture_plan/capture_source.gdb'
    frozen = stage / 'capture_preclamp.gdb'
    if frozen.exists():
        raise RuntimeError('Stage already frozen; use a fresh preparation for a retry')
    shutil.copy2(helper, frozen)
    profile = ROOT / 'tests/intel_toolchain.sh'
    context = {'stage_id': args.arm.lower() + '_first_inner', 'arm': args.arm,
               'binary_sha256': record['binary']['sha256'],
               'build_id': '8baf18e56c6a582ccc7a27fb4d1653ad18fb8810',
               'selection_sha256': record['selection_sha256'],
               'helper_sha256': digest(frozen), 'expected_ranks': 8,
               'run_receipt_sha256': digest(preparation),
               'intel_profile': {'path': str(profile), 'sha256': digest(profile)},
               'scope': 'Original historical executable, first KDM6 only; pre-sum, pre-clamp and pre-store capture; intentional diagnostic stop.'}
    context_path = stage / 'context.json'
    context_path.write_text(json.dumps(context, indent=2) + '\n')
    wrapper = stage / 'rank_wrapper.sh'
    wrapper.write_text('#!/bin/bash\nset -euo pipefail\nexec /usr/bin/gdb --batch -x "$CP02_CAPTURE_SCRIPT" "$CP02_BINARY" > "$CP02_CAPTURE_DIR/gdb_rank${PMI_RANK}.txt" 2>&1\n')
    wrapper.chmod(0o755)
    exports = {'OMP_NUM_THREADS': '1', 'CP02_CAPTURE_DIR': str(stage / 'capture'),
               'CP02_SELECTION_JSON': str(scratch / 'selection.json'),
               'CP02_CAPTURE_SCRIPT': str(frozen), 'CP02_BINARY': str(scratch / 'wrf.exe'),
               'CP02_STAGE_CONTEXT_JSON': str(context_path),
               'CP02_EXPECTED_SCRIPT_SHA256': digest(frozen),
               'CP02_PEER_WAIT_SECONDS': '500'}
    lines = ['#!/bin/bash', 'set -euo pipefail', 'source ' + shlex.quote(str(profile)),
             'ulimit -s unlimited']
    lines.extend('export ' + key + '=' + shlex.quote(value) for key, value in exports.items())
    lines.extend(['cd ' + shlex.quote(str(stage / 'run')), 'set +e',
                  'timeout --kill-after=10 600 mpirun -np 8 ' + shlex.quote(str(wrapper)) + ' > ' + shlex.quote(str(stage / 'launcher.txt')) + ' 2>&1',
                  'rc=$?', 'printf \'%s\\n\' "$rc" > ' + shlex.quote(str(stage / 'launcher.exit')), 'exit "$rc"'])
    launch = stage / 'launch.sh'
    launch.write_text('\n'.join(lines) + '\n')
    launch.chmod(0o755)
    print(launch)

if __name__ == '__main__':
    main()
