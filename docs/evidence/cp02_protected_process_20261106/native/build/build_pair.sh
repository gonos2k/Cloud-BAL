#!/usr/bin/env bash
set -euo pipefail
cloud_bal_root=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_protected_process_20261106/Cloud-BAL
source "$cloud_bal_root/tests/intel_toolchain.sh"
exec python3 -B "$(dirname "$0")/build_pair.py" "$@"
