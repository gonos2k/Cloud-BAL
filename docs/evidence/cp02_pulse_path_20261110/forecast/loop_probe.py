#!/usr/bin/env python3
"""Compile exact KDM6 loop scheduling statements with the pinned Intel compiler."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUNTIME = ROOT.parent / 'runtime' / 'loop_probe'


def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    RUNTIME.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('build', HERE/'build.py')
    build = importlib.util.module_from_spec(spec); spec.loader.exec_module(build)
    env, compiler, version = build.load_profile()
    outputs = {}
    for variant, expected_count, expected_dt in (('CONTROL',1,20.),('MP10',2,10.)):
        source = HERE/'source'/f'{variant}.f90'
        text = source.read_text()
        parameter = next(line for line in text.splitlines() if 'parameter, private :: dtcldcr =' in line).replace(', private', '')
        begin=text.index('   loops = max(nint(delt/dtcldcr),1)')
        end=text.index('   do loop = 1,loops',begin)
        schedule=text[begin:end]
        program=('program probe\n  implicit none\n'+parameter+'\n  real :: delt,dtcld,total\n  integer :: loops,loop,count\n'
                 '  delt=20.\n'+schedule+'  count=0\n  total=0.\n   do loop = 1,loops\n'
                 '    count=count+1\n    total=total+dtcld\n  enddo\n'
                 '  print *, loops, count, dtcld, total\nend program\n')
        work=RUNTIME/variant; work.mkdir()
        src=work/'probe.f90'; src.write_text(program)
        exe=work/'probe'; command=[compiler,'-O2','-fp-model','strict','-real-size','32','-i4',str(src),'-o',str(exe)]
        compiled=subprocess.run(command,cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        if compiled.returncode: raise RuntimeError(compiled.stdout)
        result=subprocess.run([str(exe)],cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,check=True)
        values=result.stdout.split()
        if len(values)!=4 or int(values[0])!=expected_count or int(values[1])!=expected_count or float(values[2])!=expected_dt or float(values[3])!=20.:
            raise ValueError('unexpected loop schedule: '+result.stdout)
        outputs[variant]={'source_sha256':sha(source),'probe_source_sha256':sha(src),'command':command,
                          'stdout':result.stdout.strip(),'loops':int(values[0]),'iterations':int(values[1]),
                          'dtcld_seconds':float(values[2]),'elapsed_microphysics_seconds':float(values[3])}
    result={'status':'PASS','compiler':compiler,'compiler_sha256':sha(Path(compiler)),'compiler_version':version,
            'probe_sha256':sha(Path(__file__)),'variants':outputs,
            'scope':'Native executable built from exact source scheduling statements; not an instrumented KDM6 forecast invocation.'}
    (HERE/'loop_probe_receipt.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__': main()
