#!/usr/bin/env bash
set -euo pipefail
ulimit -c 0
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_root/tests/intel_toolchain.sh"
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1
export LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=68
ulimit -s unlimited
work_root=$(mktemp -d /var/tmp/pr74_shinhong_qni_driver.XXXXXX)
printf 'WORK_ROOT %s\n' "$work_root"
printf -v cloud_bal_o0_flags '%s\n' "${CLOUD_BAL_FREE_FLAGS[@]}"
printf -v cloud_bal_o2_flags '%s\n' "${CLOUD_BAL_REPRO_FLAGS[@]}"
python3 - "$repo_root" "$work_root" "$CLOUD_BAL_FC" "$cloud_bal_o0_flags" "$cloud_bal_o2_flags" <<'PY'
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
repo,work,compiler=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
profile_flags={'O0':sys.argv[4].splitlines(),'O2':sys.argv[5].splitlines()}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
receipt=repo/'docs/evidence/pr73_native_first_violation_20261008_attempt2/native_receipt.json'
base=json.loads(receipt.read_text())
if sha(receipt)!='5be57e83f5ebe8e7124e4f9d5bb7ab527bdf4ae495ff19a9b1bd4e532a10a355': raise SystemExit('PR73 native receipt changed')
base_archive=Path(base['build_artifacts']['archive_path'])
if sha(base_archive)!=base['build_artifacts']['archive_sha256_after']: raise SystemExit('captured partialhost archive hash changed')
base_link=Path(base['build_artifacts']['archive_path']).parent
host=Path('/var/tmp/pr61_ccn_origin_20261006/hostcopy')
maintained=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/phys')
for path,digest in [(maintained/'module_pbl_driver.F','90336e30296991fb397ffde87649a4bd20eaa2b7dc6e90639b043810c8420b56'),(maintained/'module_bl_shinhong.F','99f44dbeb5e586b96be14424b8ab27c9986ffbd81f007f41fb8528d8ea466d56')]:
 if not path.is_file() or sha(path)!=digest: raise SystemExit(f'maintained read-only host source is missing or changed: {path}')
shinhong=Path('/var/tmp/pr73_pbl_research/source_after/module_bl_shinhong_pr65.F')
driver=repo/'docs/evidence/pr74_actual_driver_instrumented.F'
if sha(shinhong)!='5fbe821bb3b82e406fee459e5b2d745156ea1a030b5f0ecd2c7191025f296553': raise SystemExit('retained PR73 Shinhong source changed')
if sha(driver)!='342378285d929d06aa88b3c47b27c906bac05e560244162e4f946481ea4bd322': raise SystemExit('PR74 instrumented selected driver source changed')
if sha(Path('/var/tmp/pr73_pbl_research/source_after/module_pbl_driver_pr65.F'))!='5044fb264edd6be7ec7b9218602c7629a389eab87814f9e3dff18d1e68b1a232': raise SystemExit('retained PR73 driver source changed')
incs=[host/'dyn_em',host/'external/esmf_time_f90',host/'main',host/'external/io_netcdf',
 host/'external/io_int',host/'frame',host/'share',host/'phys',host/'wrftladj',host/'chem',host/'inc']
include_args=['-I.']+['-I'+str(p) for p in incs]
profiles={}
for opt in ('O0','O2'):
 case=work/opt; comp=case/'compile'; link=case/'build/link/main'; run=case/'run'
 comp.mkdir(parents=True); shutil.copytree(base_link,link,copy_function=shutil.copy2,dirs_exist_ok=True); run.mkdir()
 shutil.copy2(shinhong,comp/'module_bl_shinhong.F'); shutil.copy2(driver,comp/'module_pbl_driver.F')
 flags=profile_flags[opt]
 common=[compiler,*flags,'-free','-fpp',*include_args]
 commands=[common+['-c','module_bl_shinhong.F'],
           common+['-DEM_CORE=1','-DWRFPLUS=0','-DWRF_CHEM=0','-c','module_pbl_driver.F']]
 with (comp/'compile.log').open('wb') as log:
  for cmd in commands: subprocess.run(cmd,cwd=comp,check=True,stdout=log,stderr=subprocess.STDOUT)
 archive=link/'libwrflib_pr65.a'; old_archive_sha=sha(archive)
 objects=[comp/'module_bl_shinhong.o',comp/'module_pbl_driver.o']
 subprocess.run(['/usr/bin/ar','r',str(archive),*[str(x) for x in objects]],check=True,cwd=link)
 members=subprocess.run(['/usr/bin/ar','t',str(archive)],check=True,cwd=link,text=True,capture_output=True).stdout.splitlines()
 member_hashes={}
 for name,obj in zip(('module_bl_shinhong.o','module_pbl_driver.o'),objects):
  if members.count(name)!=1: raise SystemExit(f'archive replacement count mismatch: {name}')
  data=subprocess.run(['/usr/bin/ar','p',str(archive),name],check=True,cwd=link,stdout=subprocess.PIPE).stdout
  if hashlib.sha256(data).hexdigest()!=sha(obj): raise SystemExit(f'archive replacement bytes differ: {name}')
  member_hashes[name]=sha(obj)
 argv=list(base['build_artifacts']['link_argv']); argv[2]=str(case/'wrf.exe')
 argv=[str(archive) if item==base['build_artifacts']['archive_path'] else item for item in argv]
 with (link/'pr74_link.log').open('wb') as log: subprocess.run(argv,cwd=link,check=True,stdout=log,stderr=subprocess.STDOUT)
 inputs=[e for e in base['input_hashes_before_after'] if Path(e['path']).name!='wrf.exe']
 before={}
 for entry in inputs:
  src=Path(entry['path']); name=src.name
  if sha(src)!=entry['sha256_before']: raise SystemExit(f'baseline input changed: {name}')
  shutil.copy2(src,run/name); before[name]=sha(run/name)
 shutil.copy2(case/'wrf.exe',run/'wrf.exe')
 with (run/'candidate_run.log').open('wb') as log:
  try: result=subprocess.run([str(run/'wrf.exe')],cwd=run,stdout=log,stderr=subprocess.STDOUT,timeout=900)
  except subprocess.TimeoutExpired: result=None
 raw=run/'pr74_qni_driver.raw'; pre=run/'kdm6_first_call_pre.raw'
 after={name:sha(run/name) for name in before}
 profiles[opt]={'compiler_flags':flags,'compile_argv':commands,
  'source_sha256':{'shinhong':sha(comp/'module_bl_shinhong.F'),'driver':sha(comp/'module_pbl_driver.F')},
  'object_sha256':member_hashes,'archive_sha256_before':old_archive_sha,'archive_sha256_after':sha(archive),
  'executable_sha256':sha(case/'wrf.exe'),'run_exit_status':result.returncode if result else 'TIMEOUT_900S',
  'input_count':len(before),'input_hashes_unchanged':before==after,
  'driver_capture_path':str(raw),'driver_capture_sha256':sha(raw) if raw.is_file() else None,
  'first_call_pretrace_path':str(pre),'first_call_pretrace_sha256':sha(pre) if pre.is_file() else None,
  'candidate_run_log_sha256':sha(run/'candidate_run.log'),
  'rsl_error_sha256':sha(run/'rsl.error.0000') if (run/'rsl.error.0000').is_file() else None,
  'rsl_error_tail':(run/'rsl.error.0000').read_text(errors='replace')[-2500:] if (run/'rsl.error.0000').is_file() else None,
  'rsl_out_sha256':sha(run/'rsl.out.0000') if (run/'rsl.out.0000').is_file() else None,
  'first_kdm6_status':'KDM6 invalid NI number basis input' if 'KDM6 invalid NI number basis input' in (run/'rsl.error.0000').read_text(errors='replace') else None,
  'postcall_outputs':{n:(run/n).exists() for n in ['pr67_kdm6_process.raw','pr69_water.raw','kdm6_first_call_post.raw','wrfout_d01_2026-08-16_12:00:20']},
  'work_dir':str(case)}
 print(opt,'RUN_EXIT',profiles[opt]['run_exit_status'],'DRIVER_CAPTURE',profiles[opt]['driver_capture_sha256'])
output=work/'receipt.json'
output.write_text(json.dumps({'schema':'pr74_actual_shinhong_qni_driver_replay_v1',
 'classification':'actual selected partialhost pbl_driver Shinhong branch; research objects rebuilt with pinned Intel; native failures are retained',
 'compiler':compiler,'compiler_version':subprocess.run([compiler,'--version'],check=True,text=True,capture_output=True).stdout.splitlines()[0],
 'external_prerequisites':{'retained_PR73_source':str(shinhong),'sha256':sha(shinhong),'retained_PR73_partialhost_receipt':str(receipt),'sha256_receipt':sha(receipt),'captured_archive':str(base_archive),'sha256_archive':sha(base_archive),'read_only_host_sources':{'pbl_driver':str(maintained/'module_pbl_driver.F'),'sha256':sha(maintained/'module_pbl_driver.F'),'shinhong':str(maintained/'module_bl_shinhong.F'),'sha256_shinhong':sha(maintained/'module_bl_shinhong.F')}},
 'profiles':profiles,'work_root':str(work)},indent=2,sort_keys=True)+'\n')
print('REPLAY_RECEIPT',output)
PY
