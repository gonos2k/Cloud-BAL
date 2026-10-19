from pathlib import Path
import argparse, gzip, hashlib, json, shlex, shutil, struct, subprocess
import numpy as np
p=argparse.ArgumentParser();p.add_argument('build',type=Path);p.add_argument('capture',type=Path);p.add_argument('output',type=Path);p.add_argument('--lat',type=int,required=True);a=p.parse_args()
root=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr87_two_step_20261016/Cloud-BAL');profile=root/'tests/intel_toolchain.sh'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads(a.build.read_text());a.output.mkdir(exist_ok=False)
source=Path('/var/tmp/pr85_kdm6_fast_replay_v20k7a_20261015a/driver.f90');driver=a.output/'driver.f90';shutil.copy2(source,driver)
raw=gzip.open(a.capture,'rb').read() if a.capture.suffix=='.gz' else a.capture.read_bytes()
assert raw[:8]==b'KDM6TRC1';b=list(struct.unpack('>20i',raw[8:88]));old=b.copy();b[10]=b[11]=b[16]=b[17]=a.lat
nx,nk,nj=old[9]-old[8]+1,old[13]-old[12]+1,old[11]-old[10]+1;cells=nx*nk*nj;jo=a.lat-old[10];offset=108
out=bytearray(raw[:8]+struct.pack('>20i',*b)+raw[88:108])
for n in range(17):
 name=raw[offset:offset+8];offset+=8;v=np.frombuffer(raw,dtype='>f4',count=cells,offset=offset).reshape((nj,nk,nx));offset+=cells*4
 out+=name+v[jo:jo+1].tobytes()
assert raw[offset:offset+8]==b'XLAND   ';offset+=8
v=np.frombuffer(raw,dtype='>f4',count=nx*nj,offset=offset).reshape((nj,nx));out+=b'XLAND   '+v[jo:jo+1].tobytes()
assert offset+nx*nj*4==len(raw);inputfile=a.output/'input_row.raw';inputfile.write_bytes(out)
def run(argv,log):
 r=subprocess.run(['bash','-lc','source '+shlex.quote(str(profile))+'; source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1; export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE; export LD_LIBRARY_PATH=/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib:${LD_LIBRARY_PATH:-}; ulimit -s unlimited; exec "$@"','pr87',*map(str,argv)],cwd=a.output,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (a.output/log).write_bytes(r.stdout);return r.returncode
compiler=Path(build['compiler_path']);obj=a.output/'driver.o';exe=a.output/'replay.exe'
cmd=['bash','-lc','source '+shlex.quote(str(profile))+'; printf "%s\\0" "${CLOUD_BAL_REPRO_FLAGS[@]}"'];flags=[x.decode() for x in subprocess.check_output(cmd).split(b'\0') if x]
recipe=next(row for row in build['compiled_overrides'] if row['member']=='module_mp_kdm6.o')
includes=[x for x in recipe['compile_argv'] if x.startswith('-I')]
argv=[str(compiler),*flags,'-free','-extend-source','-convert','big_endian',*includes,'-module',str(a.output),'-c',str(driver),'-o',str(obj)]
assert run(argv,'compile.log')==0
link=json.loads(Path('/var/tmp/pr87_v14_firstcall_replay_20261016/link_argv.json').read_text());oldroot='/var/tmp/pr87_joint_cycle_build_20261016_v14';newroot=str(a.build.parent)
link=[str(obj) if x.endswith('/driver.o') else x.replace(oldroot,newroot) for x in link]
link[link.index('-o')+1]=str(exe)
link=[x for x in link if x not in ['-O3','-ftz']];fi=link.index('-fp-model');link[fi+1]='strict';link.insert(1,'-no-ftz')
assert run(link,'link.log')==0
rc=run([exe,inputfile],'replay.log')
record={'scope':'One saved actual T3 latitude row; not full host/model execution','source_build_receipt':str(a.build),'source_build_sha256':sha(a.build),'input_capture':str(a.capture),'input_capture_sha256':sha(a.capture),'input_row_sha256':sha(inputfile),'original_header':old,'selected_header':b,'selected_lat':a.lat,'params_bits':raw[88:108].hex(),'driver_original':str(source),'driver_sha256':sha(driver),'compile_argv':argv,'link_argv':link,'executable_sha256':sha(exe),'returncode':rc,'replay_log_sha256':sha(a.output/'replay.log')}
(a.output/'receipt.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'returncode':rc,'output':str(a.output)}))
