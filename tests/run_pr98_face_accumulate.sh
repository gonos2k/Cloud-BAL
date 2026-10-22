#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 1 ]]; then
  echo "usage: $0 FRESH_EXTERNAL_SCRATCH" >&2
  exit 2
fi
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
scratch=$(realpath -m "$1")
case "$scratch/" in
  "$repo_root/"*) echo "scratch must be outside the checkout: $scratch" >&2; exit 2 ;;
esac
if [[ -e $scratch ]]; then
  echo "scratch must not exist: $scratch" >&2
  exit 2
fi
mkdir -p "$scratch"
source "$repo_root/tests/intel_toolchain.sh"
for profile in audit repro; do
  dir="$scratch/$profile"
  mkdir -p "$dir/mod"
  if [[ $profile == audit ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  "$CLOUD_BAL_FC" "${flags[@]}" -module "$dir/mod" -I"$dir/mod" \
    "$repo_root/tools/pr98_budget_face_observer.f90" \
    "$repo_root/tests/pr98_face_accumulate_test.f90" -o "$dir/accumulate_test.exe"
  "$dir/accumulate_test.exe" | tee "$dir/result.txt"
done
python3 - "$repo_root" "$scratch" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

repo, scratch = map(Path, sys.argv[1:])
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

profiles = {}
for name in ("audit", "repro"):
    directory = scratch / name
    profiles[name] = {
        "executable_path": str((directory / "accumulate_test.exe").resolve()),
        "executable_sha256": sha(directory / "accumulate_test.exe"),
        "output_path": str((directory / "result.txt").resolve()),
        "output_sha256": sha(directory / "result.txt"),
    }
ifx = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx")
manifest = {
    "schema": "pr98_face_accumulator_test_v1",
    "compiler_profile": str((repo / "tests/intel_toolchain.sh").resolve()),
    "compiler_profile_sha256": sha(repo / "tests/intel_toolchain.sh"),
    "pinned_ifx_path": str(ifx.resolve()),
    "pinned_ifx_sha256": sha(ifx),
    "observer_module_path": str((repo / "tools/pr98_budget_face_observer.f90").resolve()),
    "observer_module_sha256": sha(repo / "tools/pr98_budget_face_observer.f90"),
    "test_source_path": str((repo / "tests/pr98_face_accumulate_test.f90").resolve()),
    "test_source_sha256": sha(repo / "tests/pr98_face_accumulate_test.f90"),
    "runner_sha256": sha(repo / "tests/run_pr98_face_accumulate.sh"),
    "exact_reference": "2^60 + 1 - 2^60 = 1",
    "profiles": profiles,
}
(scratch / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY
