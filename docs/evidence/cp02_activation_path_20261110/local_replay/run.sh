#!/usr/bin/env bash
set -euo pipefail
bundle=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$bundle/../../../.." && pwd)
source_file="$root/docs/evidence/cp02_mp10_process_20261110/native/source/MP10.f90"
if (( $# )); then set -- "$(realpath "$1")"; fi
work=$(mktemp -d "$root/../activation-replay.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
cd "$work"
python3 "$bundle/prepare.py" "$source_file"
source "$root/tests/intel_toolchain.sh"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" extracted.f90 "$bundle/driver.f90" -o replay
./replay "$@"
