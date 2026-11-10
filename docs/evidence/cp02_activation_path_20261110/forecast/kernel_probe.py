#!/usr/bin/env python3
"""Compile exact extracted scheduling and clamp fragments for three 20 s policies."""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
import importlib.util

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PARENT=ROOT/'docs/evidence/cp02_pulse_path_20261110/forecast/source/MP10.f90'
CONTROL=ROOT/'docs/evidence/cp02_pulse_path_20261110/forecast/source/CONTROL.f90'
CANDIDATE=HERE/'source/MP10_NN_END.f90'

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=PARENT.read_text();c=CANDIDATE.read_text();ctrl=CONTROL.read_text()
    if sha(PARENT)!='4604dc031d618a6feeb43a72a7cfabc656abf7f3e4eb591b0c7724f7e490f586' or sha(CONTROL)!='c2e90bcc04b0f8fac2224c24124cbac0f5fbf0916ee91f679759e5bbb55bfcc2' or sha(CANDIDATE)!=json.loads((HERE/'source/source_receipt.json').read_text())['candidate_sha256']:raise ValueError('source identity differs')
    a='   loops = max(nint(delt/dtcldcr),1)\n';b='   if(delt.le.dtcldcr) dtcld = delt\n';floor='nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)';block='''            if (loop == loops) then
              nci(i,k,3) = min(max(nci(i,k,3),1.e8),2.e10)
            else
              nci(i,k,3) = min(nci(i,k,3),2.e10)
            endif'''
    if any(t not in p for t in (a,b,floor)) or c.count(block)!=1 or 'dtcldcr = 120.' not in ctrl or 'dtcldcr = 10.' not in p:raise ValueError('source extraction anchor differs')
    sched=a+'   dtcld = delt/loops\n'+b
    exact_floor=floor.replace('nci(i,k,3)','nn')
    exact_candidate=block.replace('nci(i,k,3)','nn')
    program=f'''program policy_probe
implicit none
integer :: policy, trial, loops, loop, lower_count, upper_count
real :: nn, delt, dtcldcr, dtcld, first_after, entry_before, entry_after
 do policy=1,3
  do trial=1,2
   delt=20.
   if (policy == 1) then
    dtcldcr=120.
   else
    dtcldcr=10.
   endif
{sched}
   nn=0.5e8
   if (trial == 2) nn=3.e10
   entry_before=nn
   {exact_floor}
   entry_after=nn
   lower_count=0
   upper_count=0
   do loop=1,loops
    if (trial == 1) nn=nn-2.e7
    if (trial == 2) nn=2.1e10
    if (policy == 3) then
     if (loop == loops) lower_count=lower_count+1
     upper_count=upper_count+1
{exact_candidate}
    else
     lower_count=lower_count+1
     upper_count=upper_count+1
     {exact_floor}
    endif
    if (loop == 1) first_after=nn
   enddo
   write(*,'(5(i0,1x),5(es24.16,1x))') policy,trial,loops,lower_count,upper_count,dtcld,first_after,nn,entry_before,entry_after
  enddo
 enddo
end program policy_probe
'''
    temp=Path(tempfile.mkdtemp(prefix='nn-end-kernel-',dir=ROOT.parent/'runtime/nn_end'));src=temp/'probe.f90';src.write_text(program)
    spec=importlib.util.spec_from_file_location('nn_end_build',HERE/'build.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);env,compiler,version=module.load_profile();exe=temp/'probe.exe'
    flags=['-O2','-fp-model','strict','-fimf-arch-consistency=true','-no-ftz','-fpe0','-FR'];build=subprocess.run([compiler,*flags,str(src),'-o',str(exe)],cwd=temp,env=env,capture_output=True,text=True);(temp/'build.log').write_text(build.stdout+build.stderr)
    if build.returncode:raise RuntimeError('kernel compile failed')
    run=subprocess.run([str(exe)],cwd=temp,env=env,capture_output=True,text=True,check=True);(temp/'run.log').write_text(run.stdout);rows=[]
    for line in run.stdout.splitlines():
        x=line.split();rows.append({'policy':int(x[0]),'trial':int(x[1]),'loops':int(x[2]),'lower_count':int(x[3]),'upper_count':int(x[4]),'dt':float(x[5]),'first_nn':float(x[6]),'final_nn':float(x[7]),'entry_before':float(x[8]),'entry_after':float(x[9])})
    if len(rows)!=6:raise ValueError('kernel missing rows')
    for r in rows:
        expected=(1,1,1,20.) if r['policy']==1 else ((2,2,2,10.) if r['policy']==2 else (2,1,2,10.))
        if (r['loops'],r['lower_count'],r['upper_count'],r['dt'])!=expected:raise ValueError('timing mismatch')
        if r['trial']==1 and r['policy']==3 and r['first_nn']!=8.e7:raise ValueError('intermediate floor applied')
        if r['trial']==1 and (r['entry_before']!=0.5e8 or r['entry_after']!=1.e8):raise ValueError('entry lower bound failed')
        if r['trial']==2 and (r['entry_before']<=2.e10 or r['entry_after']!=2.e10):raise ValueError('entry upper bound failed')
        if r['trial']==2 and (r['first_nn']!=2.e10 or r['final_nn']!=2.e10):raise ValueError('upper cap failed')
        if r['trial']==1 and r['final_nn']!=1.e8:raise ValueError('final floor failed')
    result={'status':'PASS','method':'exact source schedule and two clamp expressions compiled as reduced native kernel; synthetic NN perturbations; not a full KDM6 replay','compiler':version,'compiler_sha256':sha(Path(compiler)),'flags':flags,'program_sha256':sha(src),'build_log_sha256':sha(temp/'build.log'),'run_log_sha256':sha(temp/'run.log'),'workdir':str(temp),'parent_sha256':sha(PARENT),'control_sha256':sha(CONTROL),'candidate_sha256':sha(CANDIDATE),'rows':rows}
    (HERE/'proof/kernel_probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
