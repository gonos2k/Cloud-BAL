#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1
manifest=${PR81_NATIVE_MANIFEST:-/var/tmp/pr80_kdm6_radar_contract.nsUNuj/kdm6_radar_contract_native.json}
source_root=${PR81_NATIVE_SOURCE_ROOT:-/var/tmp/pr61_ccn_origin_20261006/hostcopy}
if (($# > 0)); then
  scratch=$1
  if [[ -e "$scratch" ]]; then
    printf 'refusing to reuse build scratch: %s\n' "$scratch" >&2
    exit 2
  fi
else
  scratch=$(mktemp -d /var/tmp/pr81_native_candidate.XXXXXX)
fi
base_archive=$(python3 - "$manifest" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))['build']['archive_path'])
PY
)
[[ $(sha256sum "$base_archive" | cut -d' ' -f1) == 89b4072b37e21b985cf4a10406f16164d20aeb0a76af7be675a4d337c510fe0c ]]
mkdir -p "$scratch/compile" "$scratch/link/main"

members=(module_big_step_utilities_em module_radiation_driver module_ra_rrtmg_lw sf_sfclayrev module_sf_urban module_bl_fogdes module_cu_ksas module_diffusion_em module_small_step_em)
sources=(dyn_em/module_big_step_utilities_em.F phys/module_radiation_driver.F phys/module_ra_rrtmg_lw.F phys/physics_mmm/sf_sfclayrev.F90 phys/module_sf_urban.F phys/module_bl_fogdes.F phys/module_cu_ksas.F dyn_em/module_diffusion_em.F dyn_em/module_small_step_em.F)
generated=(dyn_em/module_big_step_utilities_em.f90 phys/module_radiation_driver.f90 phys/module_ra_rrtmg_lw.f90 phys/physics_mmm/sf_sfclayrev.f90 phys/module_sf_urban.f90 phys/module_bl_fogdes.f90 phys/module_cu_ksas.f90 dyn_em/module_diffusion_em.f90 dyn_em/module_small_step_em.f90)
source_hashes=(27ce690b27b24c80247a5551b48d37fc32fc47470d806cbef1bb859d58edc31c 8a6cbead85cd610d0cea53f71987de82e95d4cd54d6740b9dcaf6995189ab9e9 97950adb65a67ab8bb460cbd2efade8a225e655ba48fd4cc5227569aa9764088 82e2371c9f27274bf3dff04c4aa82f4e30743ea2041462ac7b2bf5a87ae19285 83bdfa95fefe99181d2afbc0b051b707954cbd70ee5a7dba249931cd89716bf2 94d6b4ed3f82c6d7ca9b14107ee07af8ace058dd65f7e07ab5fa0ab8ea1b0ed7 5a100344bc248670b0207732541cb293de2fc95a5794866ada0abee2334a51a2 a7d4570c97e51c635e86a0dbd628c6846457ac5b93d5a7af798b118c7d8d2d54 cabf1a177d50fb0096db79644af20cfe6d75217dbe63ab406a7e29bb54c17634)
generated_hashes=(d8c11bd9b3dd0fd717c14899c53ffe7ca37c4d768128c4dac750429f7fb4bf3a 4547f36be87fb39964696894d44edf01387ad08f35d84e99d47c5137c1e698a5 ee0bd4a482a3e1ea8fda403c5a50d467e0ad49c6503af040a25428f8b1c13a6a 569ed08bf7c3c89de7e78df1108e09941a03d953d67a65148b7b795c7666f365 ed80df4cc2b8d07c2d2b88bce890d948ce986506f1087b05baea2c3e22e09b3d 62360bf90623fa522c3fc62ca651edcacea4112c940d2d7085d0e59abcf26c77 75e146df00fd7f11a0adedbd6f2c95c1745bf3c516c8803653cfb7343a3b9cf6 08cd5ccce479a0de3cdafa280c1f5ce73e0d9066fe0141d2d08b12fb8b450183 a6f4b9243e83e40dd356920d5d92b89fb72233541613eaab197ff3c45b4028d9)
include_flags=(-I"$source_root/main" -I"$source_root/frame" -I"$source_root/inc" -I"$source_root/dyn_em" -I"$source_root/share" -I"$source_root/phys" -I"$source_root/phys/physics_mmm" -I"$source_root/external/esmf_time_f90" -I"$source_root/wrftladj" -I"$source_root/chem")

python3 - "$source_root" "$base_archive" "$scratch" "${sources[@]}" "${generated[@]}" <<'PY'
import hashlib, json, os, sys
source_root, archive, scratch, *paths = sys.argv[1:]
half = len(paths) // 2
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()
snap = {os.path.join(source_root, path): sha(os.path.join(source_root, path))
        for path in paths}
snap[archive] = sha(archive)
json.dump(snap, open(os.path.join(scratch, 'source_pre.json'), 'w'), indent=2)
PY

mkdir -p "$scratch/patchsrc/phys"
cp "$source_root/phys/module_cu_ksas.F" "$scratch/patchsrc/phys/"
cp "$source_root/phys/module_cu_ksas.f90" "$scratch/patchsrc/phys/"
(cd "$scratch/patchsrc" && patch --fuzz=0 -p1 < "$repo_root/patches/controlled.cu_ksas_inactive_timescale.patch")
patched_ksas_source="$scratch/patchsrc/phys/module_cu_ksas.f90"
patched_ksas_hash=$(sha256sum "$patched_ksas_source" | cut -d' ' -f1)
[[ "$patched_ksas_hash" == 5c54215b5bb90771f0eda1cfc14e0b4df90ba78bc48a0459159567fa38d0aff1 ]]

for i in "${!members[@]}"; do
  member=${members[i]}
  source_file=$source_root/${sources[i]}
  generated_file=$source_root/${generated[i]}
  [[ $(sha256sum "$source_file" | cut -d' ' -f1) == "${source_hashes[i]}" ]]
  [[ $(sha256sum "$generated_file" | cut -d' ' -f1) == "${generated_hashes[i]}" ]]
  if [[ $member == module_cu_ksas ]]; then generated_file=$patched_ksas_source; fi
  extra_flags=()
  case "$member" in module_radiation_driver|module_ra_rrtmg_lw) extra_flags=(-real-size 32 -i4);; esac
  compile_argv=("$CLOUD_BAL_FC" -free -qopenmp -convert big_endian "${CLOUD_BAL_FREE_FLAGS[@]}" -no-vec "${extra_flags[@]}" "${include_flags[@]}" -module "$scratch/compile" -I"$scratch/compile" -c "$generated_file" -o "$scratch/compile/$member.o")
  printf '%s\0' "${compile_argv[@]}" > "$scratch/compile/$member.argv.nul"
  (cd "$scratch/compile" && "${compile_argv[@]}") > "$scratch/compile/$member.log" 2>&1
done

cp "$base_archive" "$scratch/link/main/libwrflib_pr81.a"
for member in "${members[@]}"; do
  ar p "$scratch/link/main/libwrflib_pr81.a" "$member.o" > "$scratch/link/main/$member.base.o"
  nm -g --defined-only "$scratch/link/main/$member.base.o" | awk '{print $2, $3}' | sort > "$scratch/link/main/$member.base.symbols"
  nm -g --defined-only "$scratch/compile/$member.o" | awk '{print $2, $3}' | sort > "$scratch/link/main/$member.candidate.symbols"
  diff -u "$scratch/link/main/$member.base.symbols" "$scratch/link/main/$member.candidate.symbols"
  ar d "$scratch/link/main/libwrflib_pr81.a" "$member.o"
  ar q "$scratch/link/main/libwrflib_pr81.a" "$scratch/compile/$member.o"
done
ranlib "$scratch/link/main/libwrflib_pr81.a"
python3 - "$base_archive" "$scratch/link/main/libwrflib_pr81.a" "${members[@]}" <<'PY'
import hashlib, subprocess, sys
base, candidate, *expected = sys.argv[1:]
def hashes(path):
    names = subprocess.check_output(['ar', 't', path], text=True).splitlines()
    return {name: hashlib.sha256(subprocess.check_output(['ar', 'p', path, name])).hexdigest() for name in names}
a, b = hashes(base), hashes(candidate)
changed = sorted(name for name in a if a[name] != b[name])
if a.keys() != b.keys() or changed != sorted(name + '.o' for name in expected):
    raise SystemExit(f'unexpected archive changes: {changed!r}')
PY

link_directory=$(python3 - "$manifest" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))['build']['link_directory'])
PY
)
cp "$link_directory/wrf.o" "$scratch/link/main/wrf.o"
cp "$link_directory/module_wrf_top.o" "$scratch/link/main/module_wrf_top.o"
cd "$scratch/link/main"
mapfile -d '' link_args < <(python3 - "$manifest" "$scratch" <<'PY'
import json, os, sys
manifest, scratch = sys.argv[1:]
build = json.load(open(manifest))['build']
args = []
for arg in build['link_argv']:
    if arg == build['executable_path']:
        arg = os.path.join(scratch, 'wrf_pr81.exe')
    elif arg == build['archive_path'] or arg == 'libwrflib_pr65.a':
        arg = os.path.join(scratch, 'link', 'main', 'libwrflib_pr81.a')
    elif arg == '../main/module_wrf_top.o':
        arg = 'module_wrf_top.o'
    args.append(arg)
with open(os.path.join(scratch, 'link_argv.json'), 'w') as stream:
    json.dump(args, stream, indent=2)
    stream.write('\n')
for arg in args:
    sys.stdout.buffer.write(arg.encode() + b'\0')
PY
)
printf '%s\0' "${link_args[@]}" > "$scratch/link_argv.nul"
"${link_args[@]}" > "$scratch/link.log" 2>&1
python3 - "$manifest" "$scratch" "$source_root" "$base_archive" "$repo_root" "${members[@]}" <<'PY'
import hashlib, json, os, subprocess, sys
manifest, scratch, source_root, base_archive, repo_root, *members = sys.argv[1:]
def sha(path):
    d = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            d.update(chunk)
    return d.hexdigest()
build = json.load(open(manifest))['build']
source_paths = ['dyn_em/module_big_step_utilities_em.F', 'phys/module_radiation_driver.F',
                'phys/module_ra_rrtmg_lw.F', 'phys/physics_mmm/sf_sfclayrev.F90',
                'phys/module_sf_urban.F', 'phys/module_bl_fogdes.F', 'phys/module_cu_ksas.F',
                'dyn_em/module_diffusion_em.F', 'dyn_em/module_small_step_em.F']
generated_paths = [path.rsplit('.', 1)[0] + '.f90' for path in source_paths]
generated_files = [os.path.join(source_root, p) for p in generated_paths]
source_files = [os.path.join(source_root, p) for p in source_paths]
pre = json.load(open(os.path.join(scratch, 'source_pre.json')))
post = {path: sha(path) for path in pre}
if pre != post:
    raise SystemExit('source/generated/base archive changed during candidate build')
compile_argv = {}
for member in members:
    raw = open(os.path.join(scratch, 'compile', member + '.argv.nul'), 'rb').read()
    compile_argv[member] = raw.rstrip(b'\0').decode().split('\0')
link_raw = open(os.path.join(scratch, 'link_argv.nul'), 'rb').read()
effective_link_argv = link_raw.rstrip(b'\0').decode().split('\0')
audit = {'schema':'pr81_native_first_step_build_v2',
         'base_archive_path':base_archive,
         'base_archive_sha256':sha(base_archive),
         'candidate_archive_path':os.path.join(scratch,'link/main/libwrflib_pr81.a'),
         'candidate_archive_sha256':sha(os.path.join(scratch,'link/main/libwrflib_pr81.a')),
         'candidate_executable_path':os.path.join(scratch,'wrf_pr81.exe'),
         'candidate_executable_sha256':sha(os.path.join(scratch,'wrf_pr81.exe')),
         'replaced_members':[m+'.o' for m in members],
         'source_paths':{m:os.path.join(source_root,p) for m,p in zip(members,source_paths)},
         'generated_source_paths':{m:os.path.join(source_root,p) for m,p in zip(members,generated_paths)},
         'patched_ksas_source_path':os.path.join(scratch,'patchsrc/phys/module_cu_ksas.f90'),
         'patched_ksas_source_sha256':sha(os.path.join(scratch,'patchsrc/phys/module_cu_ksas.f90')),
         'ksas_patch_path':os.path.join(repo_root,'patches','controlled.cu_ksas_inactive_timescale.patch'),
         'ksas_patch_sha256':sha(os.path.join(repo_root,'patches','controlled.cu_ksas_inactive_timescale.patch')),
         'source_sha256':{m:sha(os.path.join(source_root,p)) for m,p in zip(members,source_paths)},
         'generated_source_sha256':{m:sha(os.path.join(source_root,p)) for m,p in zip(members,generated_paths)},
         'source_generated_archive_pre_sha256':pre,
         'source_generated_archive_post_sha256':post,
         'baseline_link_argv':build['link_argv'],
         'effective_link_argv':effective_link_argv,
         'link_argv_nul_path':os.path.join(scratch,'link_argv.nul'),
         'link_cwd':os.path.join(scratch,'link','main'),
         'compile_argv':compile_argv,
         'compile_argv_nul_paths':{m:os.path.join(scratch,'compile',m+'.argv.nul') for m in members},
         'compile_cwd':os.path.join(scratch,'compile'),
         'compile_module_output_directory':os.path.join(scratch,'compile'),
         'compile_include_module_directory':os.path.join(scratch,'compile'),
         'object_paths':{m:os.path.join(scratch,'compile',m+'.o') for m in members},
         'object_sha256':{m:sha(os.path.join(scratch,'compile',m+'.o')) for m in members},
         'ifx_version':subprocess.check_output([os.environ['CLOUD_BAL_FC'],'--version'],text=True).splitlines()[0],
         'ifx_path':os.environ['CLOUD_BAL_FC'],
         'ifx_sha256':sha(os.environ['CLOUD_BAL_FC']),
         'input_w_change':False,'fpe_policy_change':False,'scheme_version_change':False}
with open(os.path.join(scratch,'pr81_native_build.json'),'w') as out:
    json.dump(audit,out,indent=2); out.write('\n')
print(audit['candidate_archive_sha256'])
print(audit['candidate_executable_sha256'])
print(os.path.join(scratch,'pr81_native_build.json'))
PY
printf 'PR81_NATIVE_BUILD_ROOT %s\n' "$scratch"
