#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
work=$(mktemp -d "$repo/../cloud-bal-rain-proof.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
source "$repo/tests/intel_toolchain.sh"
cd "$work"
python3 "$repo/docs/evidence/physical_moment_handoff_20261110/native/rain_intercept_proof.py" "$repo/docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90"
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" rain_proof.f90 -o rain_proof
./rain_proof
