import hashlib,json,os,shlex,shutil,subprocess,sys,time
from pathlib import Path
R=Path('/var/tmp/firsthour-runtime-plan-20261030/experiment')
H=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_host_unit_contract_x3bcr8ui')
CASES=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def snap(p):return {str(x.relative_to(p)):sha(x) for x in sorted(p.rglob('*')) if x.is_file() and not x.is_symlink()}
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def run(cmd,cwd,log):
 t=time.time()
 with log.open('wb') as f: p=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT)
 return {'argv':cmd,'exit':p.returncode,'elapsed_seconds':time.time()-t}
def build():
 dest=R/'host'; assert not dest.exists(); shutil.copytree(H/'host',dest,symlinks=True)
 # All referenced compiled inputs follow existing symbolic links read-only; never invoke make.
 source=dest/'phys/module_mp_kdm6.f90'; orig=source.read_text(); marker='''            else\n              prevp(i,k) = min(prevp(i,k),(satdt)/2)'''; assert orig.count(marker)==1
 fsource=(dest/'phys/module_mp_kdm6.F').read_text(); assert fsource.count(marker)==1
 lines=(H/'compile_incremental.log').read_text().splitlines(); cc=next(l for l in lines if l.startswith('time mpif90') and ' -c ' in l and 'module_mp_kdm6.f90' in l); lk=next(l for l in lines if l.startswith('time mpif90') and ' -o wrf.exe ' in l)
 def argv(s):
  s=s.replace('`expr 8 \\* 4`','32').replace(str(H/'host'),str(dest)); a=shlex.split(s); assert a.pop(0)=='time'; assert a.pop(0)=='mpif90'; assert a.pop(0).startswith('-f90='); return a
 baseargs=argv(cc); linkargs=argv(lk); mpif90='/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpif90'; fc=os.environ['CLOUD_BAL_FC']
 input_before=snap(dest); receipt={'host_input_files':input_before,'source_f_sha256':sha(dest/'phys/module_mp_kdm6.F'),'source_f90_sha256':sha(source),'profile_sha256':sha(Path('/var/tmp/cloudbal-first-hour-improvement/tests/intel_toolchain.sh')),'compiler_sha256':sha(Path(fc)),'arms':{}}
 for mode in ('BASE','FIX'):
  d=R/('build_'+mode); d.mkdir(); text=orig if mode=='BASE' else orig.replace(marker,marker.replace('            else','            else if (prevp(i,k).ne.0.) then'))
  (d/'module_mp_kdm6.f90').write_text(text); (d/'module_mp_kdm6.F').write_text(fsource if mode=='BASE' else fsource.replace(marker,marker.replace('            else','            else if (prevp(i,k).ne.0.) then')))
  # Include ./phys modules explicitly and run in new directory, preventing writes to host copy.
  args=[x for x in baseargs if x not in ('module_mp_kdm6.f90','-o','module_mp_kdm6.o')]; args=[str(dest/'dyn_em') if x=='-I../dyn_em' else x for x in args]; args=[('-I'+str(dest/'dyn_em')) if x==str(dest/'dyn_em') else x for x in args]; args += ['-I'+str(dest/'phys'),'-o',str(d/'module_mp_kdm6.o'),str(d/'module_mp_kdm6.f90')]
  c=run([fc]+args,d,d/'compile.log'); assert c['exit']==0, c
  archive=d/'libwrflib.a'; shutil.copy2(dest/'main/libwrflib.a',archive); assert subprocess.check_output(['ar','t',str(archive)],text=True).splitlines().count('module_mp_kdm6.o')==1
  subprocess.run(['ar','r',str(archive),str(d/'module_mp_kdm6.o')],check=True); member=subprocess.check_output(['ar','p',str(archive),'module_mp_kdm6.o']); assert hashlib.sha256(member).hexdigest()==sha(d/'module_mp_kdm6.o')
  la=linkargs.copy(); la[la.index('wrf.exe')]=str(d/'wrf.exe'); la[la.index('libwrflib.a')]=str(archive); la[la.index('wrf.o')]=str(dest/'main/wrf.o'); la[la.index('../main/module_wrf_top.o')]=str(dest/'main/module_wrf_top.o')
  l=run([mpif90,'-f90='+fc]+la,d,d/'link.log'); assert l['exit']==0,l
  receipt['arms'][mode]={'compile':c,'link':l,'source_f':sha(d/'module_mp_kdm6.F'),'source_f90':sha(d/'module_mp_kdm6.f90'),'object':sha(d/'module_mp_kdm6.o'),'archive':sha(archive),'exe':sha(d/'wrf.exe')}
  write(R/'build_receipt.partial.json',receipt)
 assert snap(dest)==input_before, 'scratch host changed'; receipt['host_unchanged']=True; write(R/'build_receipt.json',receipt)
def prepare(label,case,exe):
 d=R/('run_'+label); assert not d.exists(); d.mkdir(); src=CASES/case; before={x.name:sha(x) for x in src.iterdir() if x.is_file() and not x.name.startswith(('wrfout','rsl.')) and x.name not in ('launcher.log','run.exit','namelist.output') and not x.name.endswith('.exe')}
 for name in before: shutil.copy2(src/name,d/name)
 n=(d/'namelist.input').read_text(); import re
 for field,val in [('run_hours','1'),('end_hour','13'),('history_end_s','3600')]:
  n,count=re.subn(r'(?m)^(\s*'+field+r'\s*=\s*)[^,\n]+',lambda m:m.group(1)+val,n); assert count==1,(field,count)
 (d/'namelist.input').write_text(n); shutil.copy2(exe,d/'wrf.exe')
 after={name:sha(src/name) for name in before}; assert before==after
 inputs={x.name:sha(x) for x in d.iterdir() if x.is_file()}; write(d/'inputs.json',{'source':str(src),'source_before':before,'source_after':after,'staged':inputs})
 env=os.environ.copy(); env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE'); start=time.time();
 with (d/'launcher.log').open('wb') as f: p=subprocess.run(['/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun','-np','8',str(d/'wrf.exe')],cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=2400)
 post={name:sha(d/name) for name in inputs}; srcpost={name:sha(src/name) for name in before}; histories=sorted(x.name for x in d.glob('wrfout*')); expected=['wrfout_d01_2026-08-16_12:00:00','wrfout_d01_2026-08-16_13:00:00']; log=(d/'rsl.out.0000').read_text(errors='replace') if (d/'rsl.out.0000').exists() else ''; receipt={'exit':p.returncode,'elapsed_seconds':time.time()-start,'success_marker':'SUCCESS COMPLETE WRF' in log,'histories':histories,'histories_exact':histories==expected,'staged_unchanged':post==inputs,'source_unchanged':srcpost==before,'output_sha256':{x:sha(d/x) for x in histories}}
 write(d/'receipt.json',receipt); assert p.returncode==0 and receipt['success_marker'] and receipt['histories_exact'] and receipt['staged_unchanged'] and receipt['source_unchanged'],receipt
if __name__=='__main__':
 if sys.argv[1]=='build':build()
 else:
  label,case,exe=sys.argv[1:];prepare(label,case,Path(exe))
