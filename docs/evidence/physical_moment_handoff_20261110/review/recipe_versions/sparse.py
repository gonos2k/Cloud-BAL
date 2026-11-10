#!/usr/bin/env python3
"""Replay final focused checks from a private Git tree and verify prior unit inputs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[4]
B=Path('docs/evidence/physical_moment_handoff_20261110')


def sha(p):
    with Path(p).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    output=ROOT/B/'validation/tree_replay_receipt.json'
    if output.exists():raise FileExistsError(output)
    work=Path(tempfile.mkdtemp(prefix='git-tree-',dir=ROOT.parent/'validation'))
    def git(*args,env=None):
        return subprocess.check_output(['git',*args],cwd=ROOT,env=env,text=True).strip()
    lock=json.loads((ROOT/B/'kg/selection_lock.json').read_text())
    names=set(lock['selected_source_sha256'])
    names.update(['tests/run_unit_tests.sh','tests/run_initialize_model_moments.sh',
                  'tests/test_tier_exceptions.json','README.md','docs/CURRENT_RESEARCH_STATUS.md',
                  'docs/MODEL_MOMENT_HANDOFF.md','docs/PHYSICAL_MOMENT_INITIALIZATION_20261110.md'])
    names.update(str(p.relative_to(ROOT)) for p in (ROOT/B).rglob('*') if p.is_file()
                 and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.lock')
                 and p.name not in ('tree_replay_receipt.json','validation.json','final_index_review.json'))
    names.update(f'graphify-out/{n}' for n in ('graph.json','GRAPH_REPORT.md','manifest.json'))
    names.update(str(p.relative_to(ROOT)) for p in (ROOT/'graphify-out'/lock['snapshot']).glob('*') if p.is_file())
    before={n:sha(ROOT/n) for n in sorted(names)}
    index=Path(git('rev-parse','--git-path','index'))
    if not index.is_absolute():index=ROOT/index
    index_before=sha(index)
    paths=work/'paths.nul';paths.write_bytes(b''.join(n.encode()+b'\0' for n in sorted(names)))
    env_index=os.environ.copy();env_index['GIT_INDEX_FILE']=str(work/'private.index')
    git('read-tree','HEAD',env=env_index)
    subprocess.run(['git','add','--sparse','-f','--pathspec-from-file='+str(paths),'--pathspec-file-nul'],cwd=ROOT,env=env_index,check=True)
    tree=git('write-tree',env=env_index)
    export=work/'tree';export.mkdir();(work/'validation').mkdir()
    # The old multi-gigabyte forecast bundles are not needed for these checks.
    scopes=['src','tests','tools','patches','config','runtime','schema',str(B),
            'docs/MODEL_MOMENT_HANDOFF.md','docs/PHYSICAL_MOMENT_INITIALIZATION_20261110.md',
            'README.md','docs/CURRENT_RESEARCH_STATUS.md','graphify-out/graph.json',
            'graphify-out/GRAPH_REPORT.md','graphify-out/manifest.json',
            'graphify-out/'+lock['snapshot'],
            'docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90']
    proc=subprocess.Popen(['git','archive','--format=tar',tree,*scopes],cwd=ROOT,stdout=subprocess.PIPE)
    with proc.stdout:unpack=subprocess.run(['tar','-xf','-','-C',str(export)],stdin=proc.stdout)
    assert proc.wait()==0 and unpack.returncode==0
    assert before=={n:sha(export/n) for n in before},'Git-exported artifacts differ'
    unit=json.loads((export/B/'validation/unit_receipt.json').read_text())
    assert len(unit['guarded_sha256'])==1365
    for name,digest in unit['guarded_sha256'].items():assert sha(export/name)==digest,name
    reference=json.loads((export/B/'validation/focused_receipt.json').read_text())
    (export/B/'validation/focused_receipt.json').unlink()
    result=subprocess.run([sys.executable,str(export/B/'validation/run_focused.py')],cwd=export,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    log=work/'focused.log';log.write_text(result.stdout)
    if result.returncode:raise RuntimeError(str(log)+'\n'+result.stdout[-2500:])
    actual=json.loads((export/B/'validation/focused_receipt.json').read_text())
    for field in ('boundary_tests','composed_cases','physics_profiles','source_sha256','exact_figure_outputs'):
        assert reference[field]==actual[field],field
    assert before=={n:sha(ROOT/n) for n in before},'working source changed'
    assert sha(index)==index_before,'shared index changed'
    r={'status':'PASS','tree_sha1':tree,'input_sha256':before,'shared_index_unchanged':True,
       'unit_input_count':1365,'boundary_tests':11,'physical_cases':6,'profiles':['O0','O2'],
       'exact_figure_outputs':actual['exact_figure_outputs'],'export':str(export),
       'log':str(log),'log_sha256':sha(log),'focused_replay_receipt_sha256':sha(export/B/'validation/focused_receipt.json'),
       'scope':'Private Git-tree export; 1365 previously tested unit inputs checked, focused boundary/physical/sign/figure checks rerun. No repeat broad suite, real producer, native first use, or forecast.'}
    output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'status':'PASS','private_tree':tree,'inputs':len(before),'unit_inputs':1365,'boundary_tests':11}))


if __name__=='__main__':main()
