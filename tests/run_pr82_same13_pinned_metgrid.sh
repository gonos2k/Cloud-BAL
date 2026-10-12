#!/usr/bin/env bash
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
workspace=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
if [[ $# != 3 ]]; then
  echo 'usage: run_pr82_same13_pinned_metgrid.sh CANDIDATE_WPS SAME13_INPUT_DIR RUN_ROOT' >&2
  exit 2
fi
candidate=$(realpath -e "$1")
same13=$(realpath -e "$2")
run=$(realpath -m "$3")
[[ ! -e $run && ! -L $run ]] || { echo 'existing run root rejected' >&2; exit 2; }
[[ $(sha256sum "$candidate" | cut -d' ' -f1) == ${CLOUD_BAL_PR82_WPS_SHA256:?set pinned actual candidate WPS SHA256} ]]

. "$repo/tests/intel_toolchain.sh"
unset F_UFMTENDIAN
archive=$workspace/Cloud-BAL/scratch/pr22_full_metgrid_20260917/run_final_r2
manifest_sha=7f7685faf9b1749d8773fddd278a319235fa155bafd2ffe9e7c86124820376c1
[[ $(sha256sum "$archive/manifest.json" | cut -d' ' -f1) == "$manifest_sha" ]]
python3 - "$archive/manifest.json" "$archive" <<'PY'
import hashlib, json, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text())
root = Path(sys.argv[2])
if manifest.get("status") != "PASS_SCOPED":
    raise SystemExit("retained Intel metgrid manifest is not passing")
artifacts = manifest.get("artifacts_sha256", {})
if len(artifacts) != 412:
    raise SystemExit(f"expected 412 retained artifact pins, found {len(artifacts)}")
for name, expected in artifacts.items():
    path = root / name
    if not path.is_file():
        raise SystemExit(f"missing pinned Intel metgrid artifact: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise SystemExit(f"retained Intel metgrid artifact changed: {path}")
PY
exe=$(realpath -e "${CLOUD_BAL_PR82_METGRID_EXE:?set the pinned Intel big-endian metgrid executable}")
expected_metgrid_sha=${CLOUD_BAL_PR82_METGRID_SHA256:?set the pinned Intel big-endian metgrid SHA256}
[[ $(sha256sum "$exe" | cut -d' ' -f1) == "$expected_metgrid_sha" ]]
table=$workspace/MODL/KLFS/NE57/DABA/METGRID.TBL.ARW.OML.KWW
[[ $(sha256sum "$table" | cut -d' ' -f1) == 44f1a43af35441957d0bef3a6220831aad1cf56ebc765d64d08e20f439a63b44 ]]
[[ -f $same13/namelist.wps && -f $same13/geo_em.d01.nc ]]
mkdir "$run"
cp -L "$same13/namelist.wps" "$same13/OML" "$same13/SST" "$same13/TAVGSFC" "$run/"
for source_name in KLBG RCHA SOIM SOIT; do
  cp -L "$same13/$source_name:2026-08-16_13:00" "$run/$source_name:2026-08-16_13"
done
python3 "$repo/tests/pr82_convert_geogrid_classic.py" \
  "$same13/geo_em.d01.nc" "$run/geo_em.d01.nc" > "$run/geogrid_conversion.log"
cp "$candidate" "$run/LAPS:2026-08-16_13"
cp "$exe" "$run/metgrid.exe"
resolved_table=$(realpath -e "$run/../../../MODL/KLFS/NE57/DABA/METGRID.TBL")
[[ $resolved_table == "$table" ]]
sha256sum "$candidate" "$same13/namelist.wps" "$same13/geo_em.d01.nc" \
  "$same13/KLBG:2026-08-16_13:00" "$same13/OML" \
  "$same13/RCHA:2026-08-16_13:00" "$same13/SOIM:2026-08-16_13:00" \
  "$same13/SOIT:2026-08-16_13:00" "$same13/SST" "$same13/TAVGSFC" \
  "$table" "$exe" "$run/geo_em.d01.nc" \
  "$run/LAPS:2026-08-16_13" "$run/KLBG:2026-08-16_13" \
  "$run/RCHA:2026-08-16_13" "$run/SOIM:2026-08-16_13" "$run/SOIT:2026-08-16_13" \
  > "$run/inputs.pre.sha256"
(cd "$run" && ./metgrid.exe > metgrid.log 2>&1)
rg -q 'Successful completion of metgrid' "$run/metgrid.log"
output=$run/met_em.d01.2026-08-16_13:00:00.nc
[[ -s $output ]]
sha256sum "$candidate" "$same13/namelist.wps" "$same13/geo_em.d01.nc" \
  "$same13/KLBG:2026-08-16_13:00" "$same13/OML" \
  "$same13/RCHA:2026-08-16_13:00" "$same13/SOIM:2026-08-16_13:00" \
  "$same13/SOIT:2026-08-16_13:00" "$same13/SST" "$same13/TAVGSFC" \
  "$table" "$exe" "$run/geo_em.d01.nc" \
  "$run/LAPS:2026-08-16_13" "$run/KLBG:2026-08-16_13" \
  "$run/RCHA:2026-08-16_13" "$run/SOIM:2026-08-16_13" "$run/SOIT:2026-08-16_13" \
  > "$run/inputs.post.sha256"
cmp "$run/inputs.pre.sha256" "$run/inputs.post.sha256"
python3 "$repo/tests/pr82_same13_metgrid_readback.py" "$candidate" \
  "$run/geo_em.d01.nc" "$output" "$run/readback.json"
printf 'metgrid_run=%s\nmetgrid_output=%s\n' "$run" "$output"
