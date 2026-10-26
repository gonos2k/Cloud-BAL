#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python_bin=${PYTHON_BIN:-python3}
python_bin=$(command -v "$python_bin")
PATH="$(dirname "$python_bin"):$PATH"
export PATH
test_tier=${TEST_TIER:-portable}

cd "$repo_root"
mkdir -p scratch
"$python_bin" tests/check_test_tiers.py --tier "$test_tier"

test_list=$(mktemp)
trap 'rm -f "$test_list"' EXIT
"$python_bin" tests/check_test_tiers.py --tier "$test_tier" --list > "$test_list"
mapfile -t tests < "$test_list"
if ((${#tests[@]} == 0)); then
  echo "No tests registered for tier '$test_tier'" >&2
  exit 2
fi

passed_tests=0
skipped_tests=0
run_output=$(mktemp)
trap 'rm -f "$test_list" "$run_output"' EXIT
for test_path in "${tests[@]}"; do
  echo "Running $test_path"
  if "$python_bin" "$repo_root/tests/run_python_test.py" "$repo_root/$test_path" > "$run_output" 2>&1; then
    cat "$run_output"
    if grep -q '^TIER_RESULT: SKIP ' "$run_output"; then
      ((skipped_tests += 1))
    else
      ((passed_tests += 1))
    fi
  else
    test_status=$?
    cat "$run_output" >&2
    exit "$test_status"
  fi
done

if ((passed_tests == 0)); then
  echo "Tier '$test_tier' has no passing Python tests: 0 passed, $skipped_tests skipped" >&2
  exit 1
fi

if [[ "$test_tier" == portable ]]; then
  echo "Running tests/test_pr65_observation_preflight_runner.sh"
  bash "$repo_root/tests/test_pr65_observation_preflight_runner.sh"
  echo "PASS tests/test_pr65_observation_preflight_runner.sh"
  ((passed_tests += 1))
  echo "Running tests/run_shell_transaction_recovery.sh"
  bash "$repo_root/tests/run_shell_transaction_recovery.sh"
  echo "PASS tests/run_shell_transaction_recovery.sh"
  ((passed_tests += 1))
fi

echo "Tier '$test_tier' passed: $passed_tests tests passed, $skipped_tests skipped"
