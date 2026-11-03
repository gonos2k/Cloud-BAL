from __future__ import annotations
import hashlib, json, shutil, subprocess, time
from pathlib import Path

ROOT=Path('/var/tmp/b1-two-hour-probe-20261103')
ARCHIVE=Path('/var/tmp/firsthour-runtime-plan-20261030/experiment')
HOST=ARCHIVE/'host'
RECEIPT=json.loads((ARCHIVE/'build_receipt.json').read_text())
ARMS={'BASE':'BASE','FIX':'FIX'}

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def run(argv: list[str], cwd: Path, log_path: Path) -> dict:
    start=time.time()
    with log_path.open('xb') as log:
        proc=subprocess.run(argv,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=False)
    return {'argv':argv,'exit':proc.returncode,'elapsed_seconds':time.time()-start,'log_sha256':sha(log_path)}

def main() -> None:
    assert Path(__import__('os').environ['CLOUD_BAL_FC']).resolve()==Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx')
    source_hashes={arm:sha(ROOT/'patched'/f'module_mp_kdm6_{arm}.f90') for arm in ARMS}
    link_inputs={}
    for arm in ARMS:
        for arg in RECEIPT['arms'][arm]['link']['argv']:
            path=Path(arg)
            if path.suffix in ('.o','.a') and path.is_file(): link_inputs[str(path)]=sha(path)
    receipt={'source_tree':str(ARCHIVE),'host_library_sha256':sha(HOST/'main/libwrflib.a'),'link_inputs_sha256_before':link_inputs,'instrumented_source_sha256':source_hashes,'arms':{}}
    for arm in ARMS:
        src=ROOT/'patched'/f'module_mp_kdm6_{arm}.f90'
        build=ROOT/'build'/arm
        build.mkdir(parents=True,exist_ok=False)
        shutil.copy2(src,build/'module_mp_kdm6.f90')
        comp=list(RECEIPT['arms'][arm]['compile']['argv'])
        comp[comp.index('-o')+1]=str(build/'module_mp_kdm6.o')
        comp[-1]=str(build/'module_mp_kdm6.f90')
        comp_run=run(comp,build,build/'compile.log')
        assert comp_run['exit']==0,(arm,comp_run)
        archive=build/'libwrflib.a'
        shutil.copy2(HOST/'main/libwrflib.a',archive)
        members=subprocess.check_output(['ar','t',str(archive)],text=True).splitlines()
        assert members.count('module_mp_kdm6.o')==1
        subprocess.run(['ar','r',str(archive),str(build/'module_mp_kdm6.o')],check=True,cwd=build)
        object_member=subprocess.check_output(['ar','p',str(archive),'module_mp_kdm6.o'])
        member_hash=hashlib.sha256(object_member).hexdigest()
        assert member_hash==sha(build/'module_mp_kdm6.o')
        link=list(RECEIPT['arms'][arm]['link']['argv'])
        link[link.index('-o')+1]=str(build/'wrf.exe')
        link[link.index(str(ARCHIVE/f'build_{arm}'/'libwrflib.a'))]=str(archive)
        link_run=run(link,build,build/'link.log')
        assert link_run['exit']==0,(arm,link_run)
        receipt['arms'][arm]={'compile':comp_run,'link':link_run,'object_sha256':sha(build/'module_mp_kdm6.o'),'archive_sha256':sha(archive),'archive_member_sha256':member_hash,'executable_sha256':sha(build/'wrf.exe'),'module_sha256':sha(build/'module_mp_kdm6.mod')}
        (ROOT/'build_receipt.partial.json').write_text(json.dumps(receipt,indent=2)+'\n')
    assert sha(HOST/'main/libwrflib.a')==receipt['host_library_sha256']
    receipt['link_inputs_sha256_after']={path:sha(Path(path)) for path in link_inputs}
    assert receipt['link_inputs_sha256_after']==receipt['link_inputs_sha256_before']
    receipt['host_library_unchanged']=True
    receipt['all_link_inputs_unchanged']=True
    (ROOT/'build_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    main()
