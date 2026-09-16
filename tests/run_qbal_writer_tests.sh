#!/usr/bin/env bash
# Actual legacy LAPS writer round-trip for a hash-bound BALCON candidate.
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[[ $# == 1 ]] || { echo 'usage: run_qbal_writer_tests.sh BALCON_SCRATCH_ROOT' >&2; exit 2; }
candidate_root=$(cd "$1" && pwd)
. "$repo_root/tests/intel_toolchain.sh"
workspace_root=$(cd "$repo_root/.." && pwd)
upstream="$workspace_root/klaps-v5.0_"
lib="$upstream/src/lib"
nc_root="$upstream/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install"
cc=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/icx
[[ $(sha256sum "$cc" | cut -d' ' -f1) == 9fe05a4aef59abce8d8f0631964dd0f12932345d0d38fc9e9d6f6af844e94b33 ]]
[[ $(sha256sum "$nc_root/lib/libnetcdf.a" | cut -d' ' -f1) == f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288 ]]
[[ $(sha256sum "$nc_root/bin/ncgen" | cut -d' ' -f1) == b83acc5e06621d9e15c3e92b7c1592ca6fcf5d62593c95d8f87fa76cbcfb549e ]]
export PATH="$nc_root/bin:$PATH"
read -r -a nc_libs <<<"$("$nc_root/bin/nc-config" --libs)"
build_root=$(mktemp -d "$repo_root/scratch/qbal_writer.XXXXXX")
printf 'Writer scratch: %s\n' "$build_root"
sources=("$repo_root/src/balance/writeballaps.f" "$lib/writelapsdata.f"
         "$lib/readlapsdata.f" "$lib/upcase.f" "$lib/downcase.f"
         "$lib/make_fnam_lp.f" "$lib/cv_i4tim_asc_lp.f"
         "$repo_root/tests/qbal_writer_metadata.f")
sha256sum "${sources[@]}" "$lib/rwl_v3.c" "$lib/fort2c_str.c" "$lib/get_dir_length.f" \
  "$nc_root/bin/nc-config" "$repo_root/tests/test_qbal_writer.f90" \
  "$repo_root/tests/verify_qbal_writer.py" "$repo_root/tests/run_qbal_writer_tests.sh" \
  "$repo_root/tools/stage_cp02_metadata.py" \
  "$repo_root/tests/intel_toolchain.sh" "$CLOUD_BAL_FC" "$cc" "$cloud_bal_imf" \
  "$cloud_bal_intlc" "$cloud_bal_setvars" "$nc_root/lib/libnetcdf.a" "$nc_root/bin/ncgen" \
  "$upstream"/src/include/* "$nc_root/include/netcdf.h" \
  "$upstream"/data/cdl/{lw3,lt1,lh3,lq3}.cdl "$candidate_root/manifest.json" \
  "$candidate_root"/{O0,O2}/normal/approved_candidate.bin > "$build_root/inputs.sha256"
python3 - "$candidate_root" "$repo_root" <<'PY'
import hashlib, json, sys
from pathlib import Path
root, repo = map(Path, sys.argv[1:])
m = json.loads((root/'manifest.json').read_text())
for source in m['sources']:
    path = Path(source['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
        raise SystemExit(f'BALCON source changed: {path}')
for level in ['O0', 'O2']:
    rows = [r for r in m['results'] if r['level'] == level and r['variant'] == 'normal']
    if len(rows) != 1 or rows[0]['status'] != 'PASS':
        raise SystemExit('approved normal candidate missing')
    candidate = root/level/'normal/approved_candidate.bin'
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != rows[0]['approved_candidate']['sha256']:
        raise SystemExit('approved candidate hash mismatch')
PY
for level in O0 O2; do
  variant="$build_root/$level"
  mkdir -p "$variant"/out/balance/{lw3,lt1,lh3,lq3} "$variant"/cdl "$variant"/static
  cp "$candidate_root/$level/normal/approved_candidate.bin" "$variant/candidate.bin"
  python3 - "$upstream/data/cdl" "$variant" "$repo_root/tools" <<'PY'
import json, re, sys
from pathlib import Path
import netCDF4
import numpy as np
sys.path.insert(0, sys.argv[3])
from stage_cp02_metadata import _remove_stale_ranges
source, root = map(Path, sys.argv[1:3])
changes = []
for ext in ['lw3','lt1','lh3','lq3']:
    text = (source/(ext+'.cdl')).read_text()
    if ext in ['lt1', 'lh3']:
        # Reuse the reviewed metadata correction in a private fixture only.
        # This does not exercise or claim atomic product publication.
        text, corrections = _remove_stale_ranges(ext+'.cdl', text)
        changes.extend(corrections)
    for dimension, size in [('x',6),('y',6),('z',4)]:
        text, count = re.subn(r'\b'+dimension+r'\s*=\s*\d+', f'{dimension} = {size}', text)
        if count != 1: raise SystemExit('CDL dimension target not unique')
    (root/'cdl'/(ext+'.cdl')).write_text(text)
(root/'metadata_corrections.json').write_text(json.dumps(changes, indent=2)+'\n')
with netCDF4.Dataset(root/'static/static.nest7grid','w',format='NETCDF3_CLASSIC') as ds:
    ds.createDimension('nav',1); ds.createDimension('namelen',132)
    for name, value in {'Dx':10.,'Dy':10.,'La1':45.,'Lo1':127.,'LoV':127.,'Latin1':45.,'Latin2':45.}.items():
        ds.createVariable(name,'f4',('nav',))[:] = value
    for name, value, dims in [('grid_type','lambert conformal',('nav','namelen')),
                              ('origin_name','synthetic BALCON writer fixture',('namelen',))]:
        ds.createVariable(name,'S1',dims)[:] = np.frombuffer(value.encode().ljust(132,b'\0'),dtype='S1')
PY
  (
    cd "$variant"
    fixed_flags=("${CLOUD_BAL_FIXED_72_FLAGS[@]}")
    free_flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
    if [[ $level == O2 ]]; then
      fixed_flags=("${fixed_flags[@]/-O0/-O2}")
      free_flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
    fi
    for source in "${sources[@]}"; do
      "$CLOUD_BAL_FC" -c "${fixed_flags[@]}" -ffunction-sections -fdata-sections \
        -I "$upstream/src/include" "$source"
    done
    # Extract the unchanged string helper, avoiding unrelated file-discovery code.
    awk '/^[[:space:]]*subroutine s_len\(/ {capture=1} capture {print} \
      capture && /^[[:space:]]*end[[:space:]]*$/ {exit}' "$lib/get_dir_length.f" > s_len.f
    "$CLOUD_BAL_FC" -c "${fixed_flags[@]}" s_len.f
    for source in rwl_v3 fort2c_str; do
      "$cc" -c "-$level" -std=gnu89 -ffunction-sections -fdata-sections \
        -DFORTRANUNDERSCORE -DLITTLE -DSWAPBYTE -I "$upstream/src/include" \
        -I "$nc_root/include" "$lib/$source.c"
    done
    "$CLOUD_BAL_FC" "${free_flags[@]}" "$repo_root/tests/test_qbal_writer.f90" \
      ./*.o -Wl,--gc-sections "${nc_libs[@]}" -o test_qbal_writer
    pwd -P > run.cwd
    ./test_qbal_writer > writer.log 2>&1
    python3 "$repo_root/tests/verify_qbal_writer.py" candidate.bin out 2000000000 > readback.json
    python3 - "$repo_root/tests" <<'PY'
import json, shutil, sys
from pathlib import Path
import netCDF4
sys.path.insert(0, sys.argv[1])
from verify_qbal_writer import verify
cases = [
    ('field', 'lw3', 'u3', 'u3: candidate/readback bits differ'),
    ('inventory', 'lw3', 'u3_fcinv', 'u3: incomplete level inventory'),
    ('time', 'lw3', 'valtime', 'lw3: valtime mismatch'),
    ('stale_temperature_range', 'lt1', 't3', 't3: unexpected missing mask'),
]
results = []
for name, extension, variable, expected in cases:
    target = Path('negative')/name
    shutil.copytree('out', target)
    path = next((target/'balance'/extension).glob('*.'+extension))
    with netCDF4.Dataset(path, 'r+') as ds:
        var = ds[variable]
        if name == 'field': var[0,0,0,0] += 1.
        elif name == 'inventory': var[0,0] = 0
        elif name == 'time': var[0] += 1.
        else: var.setncattr('valid_range', [0., 100.])
    try:
        verify(Path('candidate.bin'), target, 2000000000)
    except ValueError as error:
        if str(error) != expected: raise
        results.append({'case': name, 'status': 'REJECTED', 'reason': str(error)})
    else:
        raise SystemExit(f'writer readback control not detected: {name}')
Path('negative_controls.json').write_text(json.dumps(results, indent=2)+'\n')
PY
  ) > "$variant/build.log" 2>&1
  printf 'Actual BALCON writer %s readback PASS\n' "$level"
done
sha256sum -c --strict "$build_root/inputs.sha256" > "$build_root/input_verification.log"
python3 - "$build_root" "$candidate_root/manifest.json" "$cloud_bal_fc_version" <<'PY'
import hashlib, json, sys
from pathlib import Path
import netCDF4, numpy
root = Path(sys.argv[1])
results = []
for level in ['O0', 'O2']:
    variant = root/level
    if Path((variant/'run.cwd').read_text().strip()) != variant.resolve():
        raise SystemExit('writer did not execute in its scratch directory')
    results.append({'level': level, 'readback': json.loads((variant/'readback.json').read_text()),
                    'negative_controls': json.loads((variant/'negative_controls.json').read_text()),
                    'metadata_corrections': json.loads((variant/'metadata_corrections.json').read_text())})
artifacts = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in root.rglob('*') if path.is_file() and path.suffix not in ['.o']}
manifest = {'status': 'PASS_SCOPED', 'compiler': sys.argv[3], 'balcon_manifest': sys.argv[2],
            'reader': {'netCDF4': netCDF4.__version__, 'numpy': numpy.__version__},
            'results': results, 'artifacts_sha256': artifacts,
            'limitations': ['synthetic metadata', 'prescribed ancillary RH=50 percent',
                            'no full main, atomic publication, native or forecast execution']}
(root/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
PY
