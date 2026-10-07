#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python_bin=${PYTHON_BIN:-python3}

for test_name in carrier_budget_replay completed_qc_audit rain_process_trace; do
  "$python_bin" "$repo_root/tests/test_pr68_${test_name}.py"
done

# This source-bound research check requires the retained PR67 generated source.
# Its runner verifies that identity and builds in fresh /var/tmp directories.
bash "$repo_root/tests/run_pr68_velocity_contract.sh"
printf '%s\n' 'PR68 focused parser/replay and Intel velocity contract checks passed'
