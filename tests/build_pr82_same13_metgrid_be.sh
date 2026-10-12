#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
workspace=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
archive=$workspace/Cloud-BAL/scratch/pr22_full_metgrid_20260917/run_final_r2
if [[ $# != 1 ]]; then
  echo 'usage: build_pr82_same13_metgrid_be.sh FRESH_RUN_ROOT' >&2
  exit 2
fi
run=$(realpath -m "$1")
[[ ! -e $run && ! -L $run ]] || { echo 'existing build root rejected' >&2; exit 2; }
. "$repo/tests/intel_toolchain.sh"
unset F_UFMTENDIAN
[[ $(sha256sum "$archive/manifest.json" | cut -d' ' -f1) == \
  7f7685faf9b1749d8773fddd278a319235fa155bafd2ffe9e7c86124820376c1 ]]
python3 - "$archive/manifest.json" "$archive" <<'PY'
import hashlib, json, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text())
root = Path(sys.argv[2])
items = manifest.get("artifacts_sha256", {})
if manifest.get("status") != "PASS_SCOPED" or len(items) != 412:
    raise SystemExit("the retained O2 metgrid build receipt is not complete")
for name, expected in items.items():
    path = root / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"retained O2 metgrid artifact pin failed: {path}")
PY

mkdir -p "$run/source/WPS" "$run/build_tool"
cp -a "$archive/O2/WPS/." "$run/source/WPS/"
patch -R -d "$run/source" -p1 < "$repo/patches/wps_metgrid_exact_time.patch" \
  > "$run/source_restore.log"
(cd "$run/source/WPS" && sha256sum -c "$repo/tests/wps_full_sources.sha256")
cp "$repo/tests/build_qbal_full_metgrid.sh" "$run/build_tool/build_qbal_full_metgrid_be.sh"
python3 - "$run/build_tool/build_qbal_full_metgrid_be.sh" "$repo" <<'PY'
from pathlib import Path
import sys
script = Path(sys.argv[1])
repo = sys.argv[2]
source = script.read_text()
repo_anchor = 'repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)'
checkout_anchor = '[[ $(git -C "$wps" rev-parse HEAD) == 335c76a111f84503e8b963abaf273ea8053645bb ]]'
if source.count(repo_anchor) != 1 or source.count(checkout_anchor) != 1:
    raise SystemExit("pinned builder rewrite anchors are not unique")
source = source.replace(
    repo_anchor,
    f'repo="{repo}"',
)
source = source.replace(
    checkout_anchor,
    '[[ -d $wps/metgrid/src ]] || { echo "restored pinned source files are missing" >&2; exit 2; }',
)
if 'git -C "$wps" rev-parse HEAD' in source:
    raise SystemExit("private builder did not replace the original checkout identity guard")
if source.count('-convert little_endian') != 4:
    raise SystemExit("unexpected endian flags in the retained builder")
source = source.replace('-convert little_endian', '-convert big_endian')
script.write_text(source)
PY
sha256sum "$repo/tests/build_qbal_full_metgrid.sh" \
  "$run/build_tool/build_qbal_full_metgrid_be.sh" \
  "$repo/tests/wps_full_sources.sha256" "$repo/tests/wps_link_inputs.sha256" \
  > "$run/build_recipe.sha256"
sha256sum "$repo/tests/build_pr82_same13_metgrid_be.sh" \
  "$repo/tests/intel_toolchain.sh" "$repo/tests/build_qbal_full_metgrid.sh" \
  "$run/build_tool/build_qbal_full_metgrid_be.sh" \
  "$repo/tests/wps_full_sources.sha256" "$repo/tests/wps_link_inputs.sha256" \
  > "$run/runner_inputs.pre.sha256"
wrf=$workspace/../KIM-meso/KIM_RDPS_MODL_V2026.2
netcdf=$workspace/../KIM-meso/deps/netcdf-intel
bash "$run/build_tool/build_qbal_full_metgrid_be.sh" "$run/source/WPS" \
  "$run/build/O2" O2 "$wrf" "$netcdf" "$repo/patches/wps_metgrid_exact_time.patch"
sha256sum "$run/build/O2/metgrid.exe" > "$run/metgrid.exe.sha256"
sha256sum "$repo/tests/build_pr82_same13_metgrid_be.sh" \
  "$repo/tests/intel_toolchain.sh" "$repo/tests/build_qbal_full_metgrid.sh" \
  "$run/build_tool/build_qbal_full_metgrid_be.sh" \
  "$repo/tests/wps_full_sources.sha256" "$repo/tests/wps_link_inputs.sha256" \
  > "$run/runner_inputs.post.sha256"
cmp "$run/runner_inputs.pre.sha256" "$run/runner_inputs.post.sha256"
sha256sum -c "$run/build_recipe.sha256" > "$run/build_recipe.check.log"
printf 'build_root=%s\nmetgrid_exe=%s\n' "$run" "$run/build/O2/metgrid.exe"
