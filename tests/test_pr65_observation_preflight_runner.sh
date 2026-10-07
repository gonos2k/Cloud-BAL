#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/run_pr65_observation_joint_preflight.sh"

test_root=$(mktemp -d)
trap 'rm -rf "$test_root"' EXIT

if run_logged_command "$test_root/program.log" bash -c \
  'printf "program stdout\n"; printf "program stderr\n" >&2; exit 7'; then
  program_status=0
else
  program_status=$?
fi
test "$program_status" -eq 7
grep -Fxq 'program stdout' "$test_root/program.log"
grep -Fxq 'program stderr' "$test_root/program.log"

tee() {
  cat >/dev/null
  return 23
}
if run_logged_command "$test_root/capture.log" bash -c 'printf "program completed\n"'; then
  capture_status=0
else
  capture_status=$?
fi
unset -f tee
test "$capture_status" -eq 125

printf '%s\n' 'PR65 preflight runner failure handling passed'
