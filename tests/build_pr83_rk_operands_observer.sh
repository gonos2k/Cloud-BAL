#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1

if (($# != 1)); then
  printf 'usage: %s NEW_SCRATCH_DIRECTORY\n' "$0" >&2
  exit 2
fi
scratch=$1
if [[ -e $scratch || -L $scratch ]]; then
  printf 'refusing to reuse build scratch: %s\n' "$scratch" >&2
  exit 2
fi

source_file=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/dyn_em/module_em.F
base_build=/var/tmp/pr82_native_stage_trace_build1
base_archive=$base_build/link/main/libwrflib_pr82.a
base_executable=$base_build/wrf_pr82_stage.exe
solve_source=/var/tmp/pr64_qc_channel_20261007/source/solve_em_pr64_qc_channel.f90
patch_file=$repo_root/patches/pr83_rk_operands_trace.patch
[[ $(sha256sum "$source_file" | cut -d' ' -f1) == 7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7 ]]
[[ $(sha256sum "$base_archive" | cut -d' ' -f1) == a5f68566172d1f7d69aad988c3b1ac239ab91689d79d46cce1a6b94e6a810fc5 ]]
[[ $(sha256sum "$base_executable" | cut -d' ' -f1) == d1d2cce0a60e180066a9abfe923f7dcb3d79a8993c3cb45438b28f3fb741c003 ]]
[[ $(sha256sum "$solve_source" | cut -d' ' -f1) == 72aa50d495fa13d58029189f643fba218c819f8d0911c5138997124d6e99459b ]]
mkdir -p "$scratch/compile" "$scratch/link/main" "$scratch/source/dyn_em"
printf '%s\0' "${CLOUD_BAL_REPRO_FLAGS[@]}" > "$scratch/profile_flags.nul"

# Freeze direct compiler/linker dependencies before patching, compiling, or linking.
python3 - "$base_build" "$scratch" "$source_file" "$base_archive" "$base_executable" \
  "$solve_source" "$patch_file" "$repo_root" "$CLOUD_BAL_FC" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
base, root, source, archive, executable, solve, patch, repo, compiler = sys.argv[1:]
base, root = Path(base), Path(root)
sys.path.insert(0, str(Path(repo)/'tools'))
from archive_member_hashes import archive_member_hashes
def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()
compile_receipt=base/'compile_argv.nul'
link_receipt=base/'link_argv.nul'
if not compile_receipt.is_file() or not link_receipt.is_file():
    raise SystemExit('PR82 compile/link argv receipts are required')
base_compile=[x.decode() for x in compile_receipt.read_bytes().split(b'\0') if x]
base_link=[x.decode() for x in link_receipt.read_bytes().split(b'\0') if x]
if not base_compile or Path(base_compile[0]) != Path(compiler):
    raise SystemExit('base compile argv does not use pinned ifx')
if any(arg.startswith('-D') for arg in base_compile):
    raise SystemExit('base compile argv contains unreviewed macro definitions')
paths={str(Path(p)) for p in [source,solve,archive,executable,patch,compile_receipt,link_receipt,
    Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/configure.wrf'),
    base/'link/main/wrf.o',base/'link/main/module_wrf_top.o',Path(compiler),
    Path(base_link[0]),Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh'),
    Path(repo)/'tests/intel_toolchain.sh',Path(repo)/'tests/build_pr83_rk_operands_observer.sh',
    Path(repo)/'tools/archive_member_hashes.py',root/'profile_flags.nul']}
include_dirs=[]
i=0
while i < len(base_compile):
    arg=base_compile[i]
    if arg == '-I' and i+1 < len(base_compile):
        include_dirs.append(Path(base_compile[i+1])); i+=2; continue
    if arg.startswith('-I') and len(arg)>2:
        include_dirs.append(Path(arg[2:]))
    i+=1
include_dirs.append(Path(source).parent)
for directory in dict.fromkeys(include_dirs):
    if directory.is_dir():
        paths.update(str(p) for p in sorted(directory.glob('*.mod')))
for item in base_link:
    p=Path(item)
    if p.is_absolute() and p.is_file() and p.suffix in ('.a','.o'):
        paths.add(str(p))
pre={p:sha(p) for p in sorted(paths)}
pre['archive_member_sha256']=[list(row) for row in archive_member_hashes(Path(archive))]
pre['base_compile_argv_sha256']=sha(compile_receipt)
pre['base_link_argv_sha256']=sha(link_receipt)
configure=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/configure.wrf').read_text()
if 'NATIVE_RWORDSIZE = 4' not in configure or 'RWORDSIZE       =       $(NATIVE_RWORDSIZE)' not in configure:
    raise SystemExit('pinned configure.wrf does not declare the expected 4-byte real size')
pre['source_form_audit']={'preprocessor_directive_count':sum(1 for line in Path(source).read_text(errors='replace').splitlines() if line.lstrip().startswith('#')),
                          'base_compile_macro_definitions':False,'observer_compile_source_form':'-free',
                          'include_directory_count':len(include_dirs),
                          'module_files_hashed':sum(1 for p in paths if p.endswith('.mod')),
                          'configure_real_size_bytes':4}
(root/'build_inputs_pre.json').write_text(json.dumps(pre,indent=2)+'\n')
PY

cp "$source_file" "$scratch/source/dyn_em/module_em.F"
(cd "$scratch/source" && patch --fuzz=0 -p1 < "$patch_file")
cp "$base_build/link/main/wrf.o" "$scratch/link/main/wrf.o"
cp "$base_build/link/main/module_wrf_top.o" "$scratch/link/main/module_wrf_top.o"

python3 - "$base_build" "$scratch" "$source_file" "$base_archive" "$base_executable" \
  "$solve_source" "$patch_file" "$repo_root" "$CLOUD_BAL_FC" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

base, root, source, archive, executable, solve, patch, repo, compiler = sys.argv[1:]
base, root = Path(base), Path(root)
archive, executable = Path(archive), Path(executable)
scratch_archive = root / 'link/main/libwrflib_pr83.a'
scratch_exe = root / 'wrf_pr83_rk_operands.exe'

def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()

def sha(path):
    return sha_bytes(Path(path).read_bytes())

base_args = [item.decode() for item in (base / 'compile_argv.nul').read_bytes().split(b'\0') if item]
include_args = [item for item in base_args if item.startswith('-I')]
if not include_args:
    raise SystemExit('base PR82 compile receipt has no include paths')
profile_flags = [item.decode() for item in (root/'profile_flags.nul').read_bytes().split(b'\0') if item]
compile_args = [compiler, *profile_flags, '-c', '-free', '-fpp', '-qopenmp', '-convert', 'big_endian',
                '-real-size', '32', '-i4', *include_args, '-I'+str(root/'compile'),
                str(root/'source/dyn_em/module_em.F'), '-o', str(root/'compile/module_em.o')]
(root / 'compile_argv.nul').write_bytes(b'\0'.join(x.encode() for x in compile_args) + b'\0')
(root / 'compile_argv.json').write_text(json.dumps(compile_args, indent=2) + '\n')
with (root / 'compile.log').open('wb') as output:
    subprocess.run(compile_args, cwd=root/'compile', stdout=output, stderr=subprocess.STDOUT, check=True)

archive_args = [item.decode() for item in (base/'link_argv.nul').read_bytes().split(b'\0') if item]
matches_archive = [i for i,x in enumerate(archive_args) if x == str(archive)]
matches_exe = [i for i,x in enumerate(archive_args) if x == str(executable)]
matches_wrf = [i for i,x in enumerate(archive_args) if x == 'wrf.o']
matches_top = [i for i,x in enumerate(archive_args) if x == 'module_wrf_top.o']
if len(matches_archive) != 1 or len(matches_exe) != 1 or len(matches_wrf) != 1 or len(matches_top) != 1:
    raise SystemExit('base PR82 link command must contain each candidate replacement exactly once')
link_args = list(archive_args)
link_args[matches_archive[0]] = str(scratch_archive)
link_args[matches_exe[0]] = str(scratch_exe)
link_args = [str(root/'link/main/wrf.o') if x == 'wrf.o' else x for x in link_args]
link_args = [str(root/'link/main/module_wrf_top.o') if x == 'module_wrf_top.o' else x for x in link_args]
(root/'link_argv.nul').write_bytes(b'\0'.join(x.encode() for x in link_args) + b'\0')
(root/'link_argv.json').write_text(json.dumps(link_args, indent=2) + '\n')

base_rows = subprocess.check_output(['ar','t',str(archive)], text=True).splitlines()
if base_rows.count('module_em.o') != 1:
    raise SystemExit('expected one module_em.o in PR82 archive')
sys.path.insert(0, os.path.join(repo,'tools'))
from archive_member_hashes import archive_member_hashes
base_occurrences=archive_member_hashes(archive)
base_target_slots=[i for i,(name,_) in enumerate(base_occurrences) if name=='module_em.o']
if base_target_slots != [337]:
    raise SystemExit(f'expected unique module_em.o at original zero-based slot 337, got {base_target_slots!r}')
base_member = subprocess.check_output(['ar','p',str(archive),'module_em.o'])
(root/'base_module_em.o').write_bytes(base_member)
subprocess.run(['cp',str(archive),str(scratch_archive)],check=True)
subprocess.run(['ar','r',str(scratch_archive),str(root/'compile/module_em.o')],check=True)
subprocess.run(['ranlib',str(scratch_archive)],check=True)
candidate_rows = subprocess.check_output(['ar','t',str(scratch_archive)], text=True).splitlines()
if candidate_rows.count('module_em.o') != 1 or [x for x in base_rows if x!='module_em.o'] != [x for x in candidate_rows if x!='module_em.o']:
    raise SystemExit('ordered archive members changed outside module_em.o')
candidate_occurrences=archive_member_hashes(scratch_archive)
if [row for row in base_occurrences if row[0]!='module_em.o'] != [row for row in candidate_occurrences if row[0]!='module_em.o']:
    raise SystemExit('ordered archive member name/hash occurrences changed outside module_em.o')
candidate_target_slots=[i for i,(name,_) in enumerate(candidate_occurrences) if name=='module_em.o']
if candidate_target_slots != base_target_slots:
    raise SystemExit('module_em.o was not replaced in its original archive slot')
if next(h for n,h in base_occurrences if n=='module_em.o') == next(h for n,h in candidate_occurrences if n=='module_em.o'):
    raise SystemExit('module_em.o replacement did not change archive member bytes')

with (root/'link.log').open('wb') as output:
    subprocess.run(link_args, cwd=root/'link/main', stdout=output, stderr=subprocess.STDOUT, check=True)

sys.path.insert(0, os.path.join(repo,'tools'))
from archive_member_hashes import archive_member_hashes
pre=json.load(open(root/'build_inputs_pre.json'))
post={p:sha(p) for p in pre if p not in ('archive_member_sha256','base_compile_argv_sha256',
                                            'base_link_argv_sha256','source_form_audit')}
post['archive_member_sha256']=[list(row) for row in archive_member_hashes(archive)]
post['base_compile_argv_sha256']=sha(base/'compile_argv.nul')
post['base_link_argv_sha256']=sha(base/'link_argv.nul')
post['source_form_audit']=pre['source_form_audit']
if post != pre:
    raise SystemExit('protected source/config/module/object/archive/argv dependency changed during build')
receipt={'schema':'pr83_rk_operands_observer_build_v1',
 'source_path':str(Path(source)), 'source_sha256':sha(source),
 'patched_source_path':str(root/'source/dyn_em/module_em.F'), 'patched_source_sha256':sha(root/'source/dyn_em/module_em.F'),
 'patch_path':str(Path(patch)), 'patch_sha256':sha(patch),
 'base_archive_path':str(archive), 'base_archive_sha256':sha(archive),
 'base_executable_sha256':sha(executable), 'base_module_em_object_sha256':sha_bytes(base_member),
 'candidate_object_path':str(root/'compile/module_em.o'), 'candidate_object_sha256':sha(root/'compile/module_em.o'),
 'candidate_archive_path':str(scratch_archive), 'candidate_archive_sha256':sha(scratch_archive),
 'candidate_executable_path':str(scratch_exe), 'candidate_executable_sha256':sha(scratch_exe),
 'changed_archive_member':['module_em.o'], 'non_target_archive_member_order_preserved':True,
 'archive_occurrence_comparison':'full ordered name/hash rows with duplicate occurrences retained; exactly one module_em.o body hash changed in place',
 'module_em_archive_slot_zero_based':base_target_slots[0],
 'module_em_archive_slot_one_based':base_target_slots[0]+1,
 'ifx_real_size_option':['-real-size','32'],
 'ifx_real_size_semantics':'ifx help lists -real-size <size>; compile receipt uses the valid paired option and binds WRF RWORDSIZE=4 configure.wrf',
 'base_compile_argv_sha256':sha(base/'compile_argv.nul'),
 'base_link_argv_sha256':sha(base/'link_argv.nul'),
 'pre_build_dependency_snapshot_path':str(root/'build_inputs_pre.json'),
 'pre_build_dependency_snapshot_sha256':sha(root/'build_inputs_pre.json'),
 'compile_argv':compile_args, 'link_argv':link_args,
 'compiler_path':compiler, 'compiler_sha256':sha(compiler),
 'compiler_version':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
 'protected_inputs_pre_post_sha256':{'pre':pre,'post':post}}
(root/'pr83_rk_operands_observer_build.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(scratch_exe)
print(root/'pr83_rk_operands_observer_build.json')
PY
