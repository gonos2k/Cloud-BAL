#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 3 ]]; then
  echo "usage: $0 FRESH_SCRATCH PREPARED_PR97_SOURCE DIAG_LINK_ARGV_JSON" >&2
  exit 2
fi
scratch=$(realpath -m "$1")
prepared_source=$(realpath "$2")
link_argv_json=$(realpath "$3")
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
case "$scratch/" in
  "$repo_root/"*) echo "build scratch must be outside the checkout: $scratch" >&2; exit 2 ;;
esac
if [[ -e $scratch ]]; then
  echo "build scratch must not exist: $scratch" >&2
  exit 2
fi
mkdir -p "$scratch/mod" "$scratch/obj" "$scratch/link"
source tests/intel_toolchain.sh
profile=${PR98_BUILD_PROFILE:-repro}
case "$profile" in
  audit) compiler_flags=("${CLOUD_BAL_FREE_FLAGS[@]}") ;;
  repro) compiler_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}") ;;
  *) echo "PR98_BUILD_PROFILE must be audit or repro" >&2; exit 2 ;;
esac
base=/var/tmp/pr97_t1_20261022
pr98_mpiifx=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpiifx
cp "$base/diag_compile"/*.mod "$scratch/mod/"
cp "$base/compile/driver.o" "$scratch/obj/driver.o"
"$CLOUD_BAL_FC" "${compiler_flags[@]}" -convert big_endian \
  -module "$scratch/mod" -I"$scratch/mod" -c tools/pr98_budget_face_observer.f90 \
  -o "$scratch/obj/pr98_budget_face_observer.o"
"$CLOUD_BAL_FC" "${compiler_flags[@]}" -convert big_endian \
  -module "$scratch/mod" -I"$scratch/mod" -I"$base/diag_compile" \
  -I"$base/compile" \
  -I"/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS/wrf_v4_8_kfarms_work/WRF-v4.8.0/phys" \
  -I"/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS/wrf_v4_8_kfarms_work/WRF-v4.8.0/frame" \
  -I"/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS/wrf_v4_8_kfarms_work/WRF-v4.8.0/inc" \
  -c "$prepared_source" -o "$scratch/obj/module_mp_kdm6_diagnostic.link.o"
objcopy --redefine-sym \
  radar_init_variable_graupel_=module_mp_radar_mp_radar_init_variable_graupel_ \
  "$scratch/obj/module_mp_kdm6_diagnostic.link.o"
PR98_BUILD_SCRATCH="$scratch" PR98_LINK_ARGV_JSON="$link_argv_json" \
PR98_PROFILE="$profile" PR98_PINNED_IFX="$CLOUD_BAL_FC" PR98_MPIIFX="$pr98_mpiifx" \
PR98_PREPARED_SOURCE="$prepared_source" \
PR98_OBSERVER_SOURCE="$repo_root/tools/pr98_budget_face_observer.f90" python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

scratch = Path(os.environ["PR98_BUILD_SCRATCH"])
argv = json.loads(Path(os.environ["PR98_LINK_ARGV_JSON"]).read_text())
expected_mpiifx = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpiifx")
if Path(argv[0]).resolve() != expected_mpiifx.resolve():
    raise SystemExit("diagnostic link recipe does not use the pinned Intel MPI wrapper")
if Path(os.environ["PR98_PINNED_IFX"]).resolve() != Path(
        "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx").resolve() or \
        Path(shutil.which("ifx")).resolve() != Path(os.environ["PR98_PINNED_IFX"]).resolve():
    raise SystemExit("tests/intel_toolchain.sh did not select the pinned Intel ifx")
old_obj = "/var/tmp/pr97_t1_20261022/diag_compile/module_mp_kdm6_diagnostic.link.o"
index = argv.index(old_obj)
argv[index] = str(scratch / "obj/module_mp_kdm6_diagnostic.link.o")
argv.insert(index + 1, str(scratch / "obj/pr98_budget_face_observer.o"))
output_index = argv.index("-o") + 1
argv[output_index] = str(scratch / "link/pr98_face_replay.exe")
log = (scratch / "link/link.log").open("wb")
try:
    subprocess.run(argv, check=True, stdout=log, stderr=subprocess.STDOUT)
finally:
    log.close()
(scratch / "link/link_argv.json").write_text(json.dumps(argv, indent=2) + "\n")
show = subprocess.run([str(expected_mpiifx), "-show", "-c", os.environ["PR98_PREPARED_SOURCE"]],
                      check=True, capture_output=True, text=True).stdout.strip()
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
manifest = {
    "schema": "pr98_face_observer_build_v1",
    "compile_profile": os.environ["PR98_PROFILE"],
    "pinned_ifx_path": os.environ["PR98_PINNED_IFX"],
    "pinned_ifx_sha256": sha(os.environ["PR98_PINNED_IFX"]),
    "pinned_mpiifx_path": str(expected_mpiifx.resolve()),
    "pinned_mpiifx_sha256": sha(expected_mpiifx),
    "mpiifx_show": show,
    "prepared_source_path": os.environ["PR98_PREPARED_SOURCE"],
    "prepared_source_sha256": sha(os.environ["PR98_PREPARED_SOURCE"]),
    "observer_source_sha256": sha(os.environ["PR98_OBSERVER_SOURCE"]),
    "link_argv_json_sha256": sha(os.environ["PR98_LINK_ARGV_JSON"]),
    "linked_executable_path": str(scratch / "link/pr98_face_replay.exe"),
    "linked_executable_sha256": sha(scratch / "link/pr98_face_replay.exe"),
}
(scratch / "link/build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY
