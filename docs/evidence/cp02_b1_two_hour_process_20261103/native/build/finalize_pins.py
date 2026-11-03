from __future__ import annotations
import difflib,hashlib,json
from pathlib import Path
ROOT=Path('/var/tmp/b1-two-hour-probe-20261103')
ARCHIVE=Path('/var/tmp/firsthour-runtime-plan-20261030/experiment')
OLD=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100')
FIX=Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED')
PROFILE=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/tests/intel_toolchain.sh')
MPI=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun')
MPI_ENV=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh')

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

cells=json.loads((ROOT/'cells.json').read_text())['coordinates']
assert len(cells)==16 and len({(c['j'],c['i']) for c in cells})==16
receipt=json.loads((ROOT/'build_receipt.json').read_text())
source_bijection={}
for arm,arch_name in [('BASE','BASE'),('FIX','FIX')]:
    orig=(ARCHIVE/f'build_{arch_name}'/'module_mp_kdm6.f90').read_text().splitlines()
    patched=(ROOT/'patched'/f'module_mp_kdm6_{arm}.f90').read_text().splitlines()
    opcodes=difflib.SequenceMatcher(a=orig,b=patched,autojunk=False).get_opcodes()
    kinds=[x[0] for x in opcodes]
    assert set(kinds)<= {'equal','insert'} and 'insert' in kinds
    source_bijection[arm]={'archived_source_sha256':sha(ARCHIVE/f'build_{arch_name}'/'module_mp_kdm6.f90'),'instrumented_source_sha256':sha(ROOT/'patched'/f'module_mp_kdm6_{arm}.f90'),'equal_opcodes':kinds.count('equal'),'insert_opcodes':kinds.count('insert'),'deleted_or_replaced_opcodes':0}
source_bijection['patch_sha256']=sha(ROOT/'candidate.patch')
source_bijection['statement']='Every original source line remains byte-identical and in order; all changes are diagnostic insertions.'
(ROOT/'source_math_bijection.json').write_text(json.dumps(source_bijection,indent=2)+'\n')

references={
 'OLD':{'path':str(OLD),'executable_sha256':sha(OLD/'wrf.exe'),'wrfinput_sha256':sha(OLD/'wrfinput_d01'),'wrfbdy_sha256':sha(OLD/'wrfbdy_d01'),'history_sha256':{h:sha(OLD/f'wrfout_d01_2026-08-16_{h}:00:00') for h in (12,13,14)}},
 'FIX':{'path':str(FIX),'executable_sha256':sha(FIX/'wrf.exe'),'wrfinput_sha256':sha(FIX/'wrfinput_d01'),'wrfbdy_sha256':sha(FIX/'wrfbdy_d01'),'history_sha256':{h:sha(FIX/f'wrfout_d01_2026-08-16_{h}:00:00') for h in (12,13,14)}}}
for arm in references.values():
    assert arm['wrfinput_sha256']=='9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
    assert arm['wrfbdy_sha256']=='74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45'
assert references['OLD']['executable_sha256']=='de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168'
assert references['FIX']['executable_sha256']=='68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
(ROOT/'references.json').write_text(json.dumps(references,indent=2)+'\n')

build_env={'profile_path':str(PROFILE),'profile_sha256':sha(PROFILE),'compiler_path':receipt['arms']['BASE']['compile']['argv'][0],'compiler_sha256':sha(receipt['arms']['BASE']['compile']['argv'][0]),'mpi_path':str(MPI),'mpi_sha256':sha(MPI),'mpi_env_path':str(MPI_ENV),'mpi_env_sha256':sha(MPI_ENV),'mpi_version':__import__('subprocess').check_output([str(MPI),'--version'],text=True).splitlines()[0],'old_cpu_set':[32,33,34,35,36,37,38,39],'fix_cpu_set':[40,41,42,43,44,45,46,47],'root_pytest_cpu_set':[64,65,66,67,68,69,70,71],'mpi_ranks':8,'omp_threads':1,'native_launch_authorized':False}
(ROOT/'build_environment.json').write_text(json.dumps(build_env,indent=2)+'\n')

p=ROOT/'pins.json'; data=json.loads(p.read_text()); data['sample_cells']='cells.json SHA256 '+sha(ROOT/'cells.json'); data['base_cpu_set']=[32,33,34,35,36,37,38,39]; data['fix_cpu_set']=[40,41,42,43,44,45,46,47]; data['runner_root']=str(FIX); data['old_reference_root']=str(OLD); data['fix_reference_root']=str(FIX); data['native_launch_authorized']=False; p.write_text(json.dumps(data,indent=2)+'\n')
