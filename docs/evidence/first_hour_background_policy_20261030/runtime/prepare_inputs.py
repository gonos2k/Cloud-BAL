from pathlib import Path
import os,hashlib,json,shutil
R=Path('/var/tmp/firsthour-runtime-plan-20261030/producer_pair'); src=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8/init_HYDRO/input')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def inventory(p):
 out={}
 for x in sorted(p.rglob('*')):
  if x.is_symlink(): raise RuntimeError('unexpected input symlink: '+str(x))
  if x.is_file():out[str(x.relative_to(p))]=sha(x)
  elif not x.is_dir(): raise RuntimeError('unsupported input file type: '+str(x))
 return out
before=inventory(src);assert len(before)==114,len(before); expected='cd22bc8cd6054ef274ad96abd3f2da548910dd9e2760f09b553be9997efeeb07';assert before['static/lapsprep.nl']==expected
for mode in ['HYDRO','HYDRO_BACKGROUND_PRECIP']:
 d=R/('run_'+mode);assert not d.exists();d.mkdir();shutil.copytree(src,d/'input',symlinks=False);(d/'work').mkdir();after=inventory(d/'input');assert after==before
 (d/'preparation.json').write_text(json.dumps({'mode':mode,'source':str(src),'source_before':before,'staged_before':after,'input_count':len(after)},indent=2)+'\n')
after=inventory(src);assert before==after
(R/'input_preparation.json').write_text(json.dumps({'source':str(src),'input_count':len(before),'source_before':before,'source_after':after,'source_unchanged':True,'modes':['HYDRO','HYDRO_BACKGROUND_PRECIP'],'scope':'posthistorical reference sealed before this paired launch, not proof of historical unsealed inputs'},indent=2)+'\n')
print('input preparation PASS, both modes, 114 files')
