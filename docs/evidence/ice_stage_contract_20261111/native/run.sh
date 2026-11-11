#!/usr/bin/env bash
set -euo pipefail
bundle=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$bundle/../../../.." && pwd)
work=$(mktemp -d "$root/../ice-fixed.XXXXXXXX")
source "$root/tests/intel_toolchain.sh"
cd "$work"
python3 "$bundle/prepare.py" "$root/docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90" > source.log
python3 - "$bundle/../cases/profiles.json" <<'PY'
import json,sys
j=json.load(open(sys.argv[1])); f=open('inputs.txt','w'); meta=[]
for case in j['cases']:
 p=case['profiles']
 for k in range(len(p['den'])):
  for v in ['QNICE','NI_nominal_maximum_mass_kg-1','NI_fixed_50um_kg-1']:
   f.write(f"{p['den'][k]:.17g} {p['QICE'][k]:.17g} {p[v][k]:.17g} 1e-15\n")
   meta.append({'case':case['roles'],'k':k+1,'variant':v})
json.dump(meta,open('metadata.json','w'),indent=2)
PY
for opt in O0 O2; do
 if [[ $opt == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi
 "$CLOUD_BAL_FC" "${flags[@]}" extracted.f90 -o "fixed_$opt" > "build_$opt.log" 2>&1
 "./fixed_$opt" < inputs.txt > "output_$opt.txt"
done
printf 'WORK_DIR %s\n' "$work"
sha256sum source.log extracted.f90 inputs.txt metadata.json output_O*.txt
