#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1
source_root=${PR82_KDM6_SOURCE_ROOT:-/var/tmp/pr80_kdm6_radar_contract.nsUNuj/compile}
base_build=${PR82_BASE_BUILD:-/var/tmp/pr81_native_ksas_smallstep_build1}
if (($# != 1)); then
  printf 'usage: %s NEW_SCRATCH_DIRECTORY\n' "$0" >&2
  exit 2
fi
scratch=$1
if [[ -e "$scratch" || -L "$scratch" ]]; then
  printf 'refusing to reuse build scratch: %s\n' "$scratch" >&2
  exit 2
fi
source_file=$source_root/module_mp_kdm6.F
base_archive=$base_build/link/main/libwrflib_pr81.a
[[ -f $source_file && -f $base_archive ]]
base_audit=$base_build/pr81_native_build.json
[[ $(sha256sum "$base_audit" | cut -d' ' -f1) == 131451b41a38660754e78e655b158a6946a4a071640d55159ce14734c133327a ]]
[[ $(sha256sum "$source_file" | cut -d' ' -f1) == a5e8ce7a05d147b05556aa7521c22c0991812711fe675409feec889e43a761e7 ]]
[[ $(sha256sum "$base_archive" | cut -d' ' -f1) == ac1366ac4574e2667196cac3c960907db52aedce6dfa137178d7254fa5eb37dd ]]
mkdir -p "$scratch/compile" "$scratch/link/main" "$scratch/patchsrc"
python3 - "$source_file" "$base_archive" "$base_build" "$scratch/build_inputs_pre.json" "$repo_root" <<'PY2'
import hashlib, json, os, subprocess, sys
source, archive, base, out, repo = sys.argv[1:]
sys.path.insert(0, os.path.join(repo,'tools'))
from archive_member_hashes import archive_member_hashes
def sha_bytes(data): return hashlib.sha256(data).hexdigest()
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()
paths = [source, archive, os.path.join(base,'pr81_native_build.json'),
         os.path.join(repo,'tools/archive_member_hashes.py'),
         os.path.join(repo,'tests/build_pr82_native_number_trace_candidate.sh'),
         os.path.join(repo,'tests/intel_toolchain.sh'),
         os.environ['CLOUD_BAL_FC'],
         os.path.join(repo,'patches/pr82_number_conversion_rejection_trace.patch'),
         os.path.join(base,'wrf_pr81.exe'), os.path.join(base,'link/main/wrf.o'),
         os.path.join(base,'link/main/module_wrf_top.o')]
for directory in [os.path.dirname(source),
                  '/var/tmp/pr61_ccn_origin_20261006/hostcopy/phys',
                  '/var/tmp/pr61_ccn_origin_20261006/hostcopy/frame']:
    paths.extend(str(p) for p in sorted(__import__('pathlib').Path(directory).glob('*.mod')))
pre = {p:sha(p) for p in paths}
metadata = json.load(open(os.path.join(base,'pr81_native_build.json')))
for arg in metadata['effective_link_argv']:
    if os.path.isabs(arg) and os.path.isfile(arg) and arg.endswith(('.a','.o')):
        pre[arg] = sha(arg)
pre['archive_member_sha256'] = archive_member_hashes(__import__('pathlib').Path(archive))
json.dump(pre,open(out,'w'),indent=2)
with open(out,'a') as f: f.write('\n')
PY2
cp "$source_file" "$scratch/patchsrc/module_mp_kdm6.F"
(cd "$scratch/patchsrc" && patch --fuzz=0 -p1 < "$repo_root/patches/pr82_number_conversion_rejection_trace.patch")
patched_source=$scratch/patchsrc/module_mp_kdm6.F
compile_argv=("$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" -fpp -qopenmp -convert big_endian \
  -I"$scratch/compile" -I"$source_root" -I/var/tmp/pr61_ccn_origin_20261006/hostcopy/phys \
  -I/var/tmp/pr61_ccn_origin_20261006/hostcopy/frame -free -c "$patched_source" \
  -o "$scratch/compile/module_mp_kdm6.o")
printf '%s\0' "${compile_argv[@]}" > "$scratch/compile_argv.nul"
(cd "$scratch/compile" && "${compile_argv[@]}") > "$scratch/compile.log" 2>&1
cp "$base_archive" "$scratch/link/main/libwrflib_pr82.a"
ar p "$scratch/link/main/libwrflib_pr82.a" module_mp_kdm6.o > "$scratch/link/main/module_mp_kdm6.base.o"
nm -g --defined-only "$scratch/link/main/module_mp_kdm6.base.o" | awk '{print $2, $3}' | sort > "$scratch/link/main/base.symbols"
nm -g --defined-only "$scratch/compile/module_mp_kdm6.o" | awk '{print $2, $3}' | sort > "$scratch/link/main/candidate.symbols"
python3 - "$scratch/link/main/base.symbols" "$scratch/link/main/candidate.symbols" <<'PY2'
from pathlib import Path
import sys
base = set(Path(sys.argv[1]).read_text().splitlines())
candidate = set(Path(sys.argv[2]).read_text().splitlines())
extra = candidate - base
expected = {
    'T module_mp_kdm6kdm6_mp_log_number_conversion_rejection_',
    'T module_mp_kdm6kdm6_mp_number_conversion_error_class_',
}
if not base <= candidate or extra != expected:
    raise SystemExit(f'unexpected KDM6 symbols: {sorted(extra)!r}')
PY2
ar d "$scratch/link/main/libwrflib_pr82.a" module_mp_kdm6.o
ar q "$scratch/link/main/libwrflib_pr82.a" "$scratch/compile/module_mp_kdm6.o"
ranlib "$scratch/link/main/libwrflib_pr82.a"
python3 - "$base_archive" "$scratch/link/main/libwrflib_pr82.a" "$repo_root" <<'PY'
from pathlib import Path
import sys
sys.path.insert(0,str(Path(sys.argv[3])/'tools'))
from archive_member_hashes import archive_member_hashes
base,candidate = [archive_member_hashes(Path(p)) for p in sys.argv[1:3]]
name='module_mp_kdm6.o'
if sum(n==name for n,_ in base)!=1 or sum(n==name for n,_ in candidate)!=1:
    raise SystemExit('expected exactly one KDM6 archive member')
if [row for row in base if row[0]!=name] != [row for row in candidate if row[0]!=name]:
    raise SystemExit('non-KDM6 archive member occurrences changed')
if next(h for n,h in base if n==name)==next(h for n,h in candidate if n==name):
    raise SystemExit('KDM6 archive member did not change')
PY

cp "$base_build/link/main/wrf.o" "$scratch/link/main/wrf.o"
cp "$base_build/link/main/module_wrf_top.o" "$scratch/link/main/module_wrf_top.o"
python3 - "$base_build/pr81_native_build.json" "$scratch" <<'PY'
import json, os, sys
base = json.load(open(sys.argv[1]))
root = sys.argv[2]
args = list(base['effective_link_argv'])
for key in ('candidate_executable_path','candidate_archive_path'):
    if args.count(base[key]) != 1:
        raise SystemExit(f'expected exactly one link replacement for {key}')
for i, arg in enumerate(args):
    if arg == base['candidate_executable_path']:
        args[i] = os.path.join(root, 'wrf_pr82.exe')
    elif arg == base['candidate_archive_path']:
        args[i] = os.path.join(root, 'link/main/libwrflib_pr82.a')
args[args.index('wrf.o')] = 'wrf.o'
args[args.index('module_wrf_top.o')] = 'module_wrf_top.o'
open(os.path.join(root, 'link_argv.nul'), 'wb').write(b'\0'.join(x.encode() for x in args) + b'\0')
json.dump(args, open(os.path.join(root, 'link_argv.json'), 'w'), indent=2)
with open(os.path.join(root, 'link_argv.json'), 'a') as f: f.write('\n')
PY
mapfile -d '' link_argv < "$scratch/link_argv.nul"
(cd "$scratch/link/main" && "${link_argv[@]}") > "$scratch/link.log" 2>&1
python3 - "$repo_root" "$source_file" "$patched_source" "$base_archive" "$base_build" "$scratch" <<'PY'
import hashlib, json, os, subprocess, sys
repo, source, patched, archive, base, scratch = sys.argv[1:]
sys.path.insert(0, os.path.join(repo,'tools'))
from archive_member_hashes import archive_member_hashes
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()
base_build = json.load(open(os.path.join(base, 'pr81_native_build.json')))
pre = json.load(open(os.path.join(scratch,'build_inputs_pre.json')))
source_after = {p: sha(p) for p in pre if p != 'archive_member_sha256'}
source_after['archive_member_sha256'] = archive_member_hashes(__import__('pathlib').Path(archive))
source_after=json.loads(json.dumps(source_after))
if pre != source_after: raise SystemExit('source/generated/base archive/external replacement inputs changed during candidate build')
obj = os.path.join(scratch,'compile/module_mp_kdm6.o')
arc = os.path.join(scratch,'link/main/libwrflib_pr82.a')
exe = os.path.join(scratch,'wrf_pr82.exe')
compile_args = open(os.path.join(scratch,'compile_argv.nul'),'rb').read().rstrip(b'\0').decode().split('\0')
link_args = open(os.path.join(scratch,'link_argv.nul'),'rb').read().rstrip(b'\0').decode().split('\0')
audit = {'schema':'pr82_native_number_trace_build_v1','source_path':source,'source_sha256':sha(source),
         'patched_source_path':patched,'patched_source_sha256':sha(patched),'patch_path':os.path.join(repo,'patches/pr82_number_conversion_rejection_trace.patch'),
         'patch_sha256':sha(os.path.join(repo,'patches/pr82_number_conversion_rejection_trace.patch')),
         'base_archive_path':archive,'base_archive_sha256':sha(archive),'base_executable_path':base_build['candidate_executable_path'],
         'base_executable_sha256':base_build['candidate_executable_sha256'],'candidate_object_path':obj,'candidate_object_sha256':sha(obj),
         'candidate_archive_path':arc,'candidate_archive_sha256':sha(arc),'candidate_executable_path':exe,'candidate_executable_sha256':sha(exe),
         'base_build_audit_path':os.path.join(base,'pr81_native_build.json'),
         'base_build_audit_sha256':sha(os.path.join(base,'pr81_native_build.json')),
         'archive_occurrence_comparison':'ordered name/hash rows; duplicates preserved; only unique KDM6 excluded',
         'link_replacement_counts':{'executable':1,'archive':1},
         'changed_archive_members':['module_mp_kdm6.o'],'compile_argv':compile_args,'compile_argv_nul_path':os.path.join(scratch,'compile_argv.nul'),
         'compile_cwd':os.path.join(scratch,'compile'),'link_argv':link_args,'link_argv_nul_path':os.path.join(scratch,'link_argv.nul'),
         'link_cwd':os.path.join(scratch,'link/main'),'ifx_path':os.environ['CLOUD_BAL_FC'],
         'ifx_sha256':sha(os.environ['CLOUD_BAL_FC']),'ifx_version':subprocess.check_output([os.environ['CLOUD_BAL_FC'],'--version'],text=True).splitlines()[0],
         'base_inputs_pre_sha256':pre,'base_inputs_post_sha256':source_after}
json.dump(audit,open(os.path.join(scratch,'pr82_native_build.json'),'w'),indent=2)
with open(os.path.join(scratch,'pr82_native_build.json'),'a') as f: f.write('\n')
print(audit['candidate_executable_sha256'])
print(os.path.join(scratch,'pr82_native_build.json'))
PY
printf 'PR82_NATIVE_BUILD_ROOT %s\n' "$scratch"
