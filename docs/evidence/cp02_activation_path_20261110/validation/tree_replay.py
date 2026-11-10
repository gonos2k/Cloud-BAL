#!/usr/bin/env python3
"""Replay the final task in a private Git tree without rerunning WRF."""
import argparse,csv,hashlib,importlib.util,json,math,os,re,shutil,struct,subprocess,sys,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
BUNDLE=Path('docs/evidence/cp02_activation_path_20261110')
REPORT=Path('docs/CP02_ACTIVATION_PATH_20261110.md')
BASE='8fe0892ec1a6a0c3f1ca35b23fd5cc289c400803'
TESTS=['tests/test_cp02_activation_path.py','tests/test_cp02_weak_activation.py',str(BUNDLE/'evaluation/test_nn_frequency_evaluation.py')]
SOURCES=['tools/cp02_activation_path.py','tools/cp02_weak_activation.py','tools/plot_cp02_activation_path.py',*TESTS,'README.md','docs/CURRENT_RESEARCH_STATUS.md',str(REPORT)]
EXTERNAL=[Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf'),Path('/usr/local/lib/python3.12/dist-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf')]

def identity(path):
    path=Path(path)
    with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'sha256':digest,'size_bytes':path.stat().st_size}

def git(*args,env=None):return subprocess.check_output(['git',*args],cwd=ROOT,env=env,text=True).strip()

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module

def worker(kind,tree,out):
    sys.path.insert(0,str(tree/'tools'));bundle=tree/BUNDLE;out.mkdir(parents=True,exist_ok=False)
    if kind=='score':
        import numpy as np
        e=load(bundle/'evaluation/evaluate.py','replay_evaluation');policy=e.load_policy();baseline=e.frozen_arrays(policy);arrays={}
        published=bundle/'evaluation/results';receipt=json.loads((published/'receipt.json').read_text())
        for hour in e.HOURS:
            path=published/f'hour_{hour}_arrays.npz'
            if identity(path)['sha256']!=receipt['outputs'][path.name]:raise ValueError('published candidate array hash differs')
            with np.load(path,allow_pickle=False) as data:arrays[hour]={k:data[k].copy() for k in data.files}
            for key,old in baseline[hour].items():
                new=arrays[hour][key]
                if (old.shape,old.dtype.str,old.tobytes())!=(new.shape,new.dtype.str,new.tobytes()):raise ValueError('prior array bits differ: '+key)
            np.savez_compressed(out/path.name,**arrays[hour])
        categorical,continuous,gates,weak,transition=e.score(arrays,policy);e.compare_prior(categorical,continuous)
        for name,rows in (('categorical_scores.csv',categorical),('continuous_scores.csv',continuous),('admission_constraints.csv',gates),('weak_bands.csv',weak),('false_alarm_transitions.csv',transition)):e.write_csv(out/name,rows)
        passed=sum(x['satisfied'] for x in gates)
        (out/'verdict.json').write_text(json.dumps({'passed':passed,'required':26,'all_gates_pass':passed==26,'selection':'B1 remains selected pending all gates and independent validation','open_items':['domain budget','independent case']},indent=2)+'\n')
        print('PASS six published candidate arrays, prior raw array bits and 26 gates')
    elif kind=='local':
        cases=[('synthetic',None),('control_nonbinding','control_sample'),('mp10_nonbinding','mp10_sample'),('mp10_binding','binding_input')];variants={1:'20_once',2:'10_eachfloor',3:'10_endonly'};fields=('NC','NN','QV','QC','T');rows=[];local=bundle/'local_replay'
        for label,name in cases:
            cmd=['bash',str(local/'run.sh')]+([str(local/(name+'.txt'))] if name else [])
            result=subprocess.run(cmd,cwd=tree,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(out/(label+'.log')).write_text(result.stdout)
            if name and 'captured activation post-state bitwise match: PASS' not in result.stdout:raise ValueError('missing captured post-state check')
            matches=re.findall(r'method=(\d) NC NN QV QC T raw32=\s*((?:[0-9A-F]{8}\s*){5})',result.stdout)
            if [int(m[0]) for m in matches]!=[1,2,3]:raise ValueError('missing local methods')
            for method,payload in matches:
                words=payload.split();values=[struct.unpack('>f',bytes.fromhex(word))[0] for word in words]
                if not all(map(math.isfinite,values)):raise ValueError('nonfinite local result')
                row={'input':label,'variant':variants[int(method)]}
                for field,value,word in zip(fields,values,words):row[field]=repr(value);row[field+'_bits']=word.lower()
                rows.append(row)
        columns=['input','variant']+[entry for field in fields for entry in (field,field+'_bits')]
        with (out/'comparisons.csv').open('w',newline='') as stream:w=csv.DictWriter(stream,fieldnames=columns,lineterminator='\n');w.writeheader();w.writerows(rows)
        if len(rows)!=12:raise ValueError('local row count differs')
        print('PASS four extracted native kernel cases, twelve float32 rows')
    elif kind=='portable':
        local=bundle/'local_replay';m=load(local/'portable_recount.py','portable_recount')
        for name in ('native_floor_proof.json','actual_loop2_contrast.json'):shutil.copyfile(local/name,out/name)
        m.HERE=out;m.NATIVE=bundle/'native';m.main()
        old=json.loads((local/'portable_recount_receipt.json').read_text());new=json.loads((out/'portable_recount_receipt.json').read_text())
        for key in ('status','native_key','loop1_words','loop2_words','phases'):
            if old[key]!=new[key]:raise ValueError('portable recount differs: '+key)
    else:raise ValueError('unknown worker')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path);ap.add_argument('--scratch',type=Path);ap.add_argument('--go',action='store_true');ap.add_argument('--paths-file',type=Path);ap.add_argument('--worker',choices=('score','local','portable'));ap.add_argument('--worker-output',type=Path);args=ap.parse_args()
    if args.worker:
        if not args.worker_output:ap.error('--worker-output required')
        worker(args.worker,ROOT,args.worker_output);return
    if not args.go or not args.output or not args.scratch:ap.error('replay requires --go, --output and --scratch')
    output=args.output.resolve()
    if os.path.lexists(output):raise FileExistsError(output)
    args.scratch.mkdir(parents=True,exist_ok=True);work=Path(tempfile.mkdtemp(prefix='activation-tree-replay-',dir=args.scratch.resolve()));export=work/'tree';export.mkdir();tmp=work/'tmp';tmp.mkdir();logs=work/'logs';logs.mkdir()
    head=git('rev-parse','HEAD')
    if head!=BASE:raise ValueError('source HEAD differs')
    names=set(SOURCES)
    for path in (ROOT/BUNDLE).rglob('*'):
        rel=path.relative_to(ROOT/BUNDLE)
        if '__pycache__' in rel.parts or path.suffix in ('.pyc','.lock') or not path.is_file() or path.is_symlink():continue
        if rel.parts[0]=='validation' and path.name.startswith('tree_replay_'):continue
        names.add(str(path.relative_to(ROOT)))
    if args.paths_file:
        for line in args.paths_file.read_text().splitlines():
            if line.strip():names.add(line.strip())
    names=sorted(names)
    for name in names:
        path=ROOT/name
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.is_file() or path.is_symlink():raise ValueError('invalid overlay '+name)
    script=Path(__file__).resolve();before={n:identity(ROOT/n) for n in names};externals={str(p):identity(p) for p in EXTERNAL};index=Path(git('rev-parse','--git-path','index'));index=index if index.is_absolute() else ROOT/index;index_before=identity(index) if index.exists() else None
    env_index=os.environ.copy();env_index['GIT_INDEX_FILE']=str(work/'private.index');git('read-tree',head,env=env_index);subprocess.run(['git','add','-f','--',*names],cwd=ROOT,env=env_index,check=True);tree=git('write-tree',env=env_index)
    archive=subprocess.Popen(['git','archive','--format=tar',tree],cwd=ROOT,stdout=subprocess.PIPE)
    with archive.stdout:unpack=subprocess.run(['tar','-xf','-','-C',str(export)],stdin=archive.stdout)
    if archive.wait() or unpack.returncode:raise RuntimeError('Git export failed')
    if before!={n:identity(export/n) for n in names}:raise ValueError('private tree export differs')
    profile=export/'tests/intel_toolchain.sh';configured=subprocess.run(['bash','-c','set -e; source "$1"; env -0','profile',str(profile)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE);env={k.decode():v.decode(errors='surrogateescape') for x in configured.stdout.split(b'\0') if x for k,v in [x.split(b'=',1)]}
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS'):env[key]='1'
    mpl=tmp/'mplconfig';mpl.mkdir();env.update(PYTHONDONTWRITEBYTECODE='1',MPLCONFIGDIR=str(mpl),TMPDIR=str(tmp),PYTHONPATH=str(export/'tools'))
    intel=Path(env['CLOUD_BAL_FC']).resolve()
    if identity(intel)['sha256']!='909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef':raise ValueError('pinned IFX compiler differs')
    out=work/'outputs';out.mkdir();official=export/BUNDLE;py=sys.executable;commands={}
    def run(label,cmd):
        start=time.monotonic();result=subprocess.run(cmd,cwd=export,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);log=logs/(label+'.log');log.write_text(result.stdout)
        if result.returncode:raise RuntimeError(f'{label} failed; see {log}:\n{result.stdout[-3000:]}')
        commands[label]={'argv':cmd,'exit_code':result.returncode,'seconds':round(time.monotonic()-start,3),'log':str(log),'log_identity':identity(log),'tail':result.stdout[-500:]}
    def compare(label,expected,actual,names):
        checks[label]={}
        for name in sorted(names):
            a,b=identity(expected/name),identity(actual/name)
            if a!=b:raise ValueError('byte mismatch: '+label+'/'+name)
            checks[label][name]=a
    checks={};own=export/BUNDLE/'validation/tree_replay.py'
    run('historical',[py,'tools/cp02_activation_path.py',str(out/'analysis')]);compare('historical',official/'analysis',out/'analysis',['native_loops.csv','paired_weighted.csv'])
    run('weak',[py,'tools/cp02_weak_activation.py','--output',str(out/'weak_analysis')]);weak_names=list(json.loads((official/'weak_analysis/receipt.json').read_text())['outputs']);compare('weak',official/'weak_analysis',out/'weak_analysis',weak_names)
    run('figures',[py,'tools/plot_cp02_activation_path.py','--weak',str(official/'weak_analysis'),'--output',str(out/'figures')]);figure_names=list(json.loads((official/'figures/receipt.json').read_text())['outputs']);compare('figures',official/'figures',out/'figures',figure_names)
    run('local',[py,str(own),'--worker','local','--worker-output',str(out/'local')]);compare('local',official/'local_replay/results',out/'local',['comparisons.csv'])
    run('portable',[py,str(own),'--worker','portable','--worker-output',str(out/'portable')])
    run('scores',[py,str(own),'--worker','score','--worker-output',str(out/'scores')]);score_names=[f'hour_{h}_arrays.npz' for h in range(13,19)]+['categorical_scores.csv','continuous_scores.csv','admission_constraints.csv','weak_bands.csv','false_alarm_transitions.csv','verdict.json'];compare('scores',official/'evaluation/results',out/'scores',score_names)
    run('evaluation_figures',[py,str(official/'evaluation/plot.py'),'--results',str(official/'evaluation/results'),'--output',str(out/'evaluation_figures')]);eval_figures=list(json.loads((official/'evaluation/figures/receipt.json').read_text())['outputs']);compare('evaluation_figures',official/'evaluation/figures',out/'evaluation_figures',eval_figures)
    run('evaluation_supplement',[py,str(official/'evaluation/plot_supplement.py'),'--results',str(official/'evaluation/results'),'--output',str(out/'evaluation_supplement')]);supplement_names=list(json.loads((official/'evaluation/supplementary_figures/receipt.json').read_text())['outputs']);compare('evaluation_supplement',official/'evaluation/supplementary_figures',out/'evaluation_supplement',supplement_names)
    run('full_table',[py,str(official/'evaluation/full_table.py')]);compare('full_table',ROOT/BUNDLE/'evaluation',official/'evaluation',['FULL_SCORES.md'])
    run('tests',[py,'-m','pytest','-q',*TESTS]);match=re.search(r'(\d+) passed',commands['tests']['tail'])
    if not match or int(match.group(1))!=16:raise ValueError('expected 16 focused tests')
    if before!={n:identity(ROOT/n) for n in names} or externals!={p:identity(p) for p in externals} or (identity(index) if index.exists() else None)!=index_before:raise ValueError('source, external input or shared index changed')
    result={'status':'PASS','base_commit':head,'tree_sha1':tree,'git_index':'private temporary index','overlay_files':before,'scratch':str(work),'export_path':str(export),'external_pinned_inputs':externals,'shared_index_unchanged':True,'profile':identity(profile),'ifx':identity(intel),'commands':commands,'byte_identical_outputs':checks,'focused_tests_passed':16,'scope':'Historical and new packed capture analyses, 110-word probe recount, four extracted source kernels, plots and scores replayed from published candidate hourly arrays. No raw capture extraction, candidate WRF forecast rerun or scientific validation claim. Path-bearing receipts are excluded from byte comparisons.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'status':'PASS','tree_sha1':tree,'overlay_files':len(names),'compared_outputs':sum(map(len,checks.values())),'tests':16,'scratch':str(work)}))
if __name__=='__main__':main()
