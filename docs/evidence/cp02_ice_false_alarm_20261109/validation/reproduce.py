#!/usr/bin/env python3
"""Replay sealed point/corner arrays without original external WRF histories."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

BUNDLE=Path('docs/evidence/cp02_ice_false_alarm_20261109')
PRIOR=Path('docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results')


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def replay(root,parent):
    b=root/BUNDLE;checked=[];commands=[]
    with tempfile.TemporaryDirectory(prefix='ice-fa-replay-',dir=parent) as tmp:
        scratch=Path(tmp);env={**os.environ,'TMPDIR':str(scratch),'MPLCONFIGDIR':str(scratch/'mpl'),'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
        def run(args):
            cmd=[sys.executable,'-B',*map(str,args)];p=subprocess.run(cmd,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            commands.append({'argv':cmd,'exit_code':p.returncode,'output':p.stdout})
            if p.returncode:raise RuntimeError(p.stdout)
            return p.stdout
        def equal(path,target):
            if sha(path)!=sha(target):raise ValueError('portable output differs: '+str(target))
            checked.append({'path':str(target.relative_to(root)),'sha256':sha(target),'size_bytes':target.stat().st_size})
        run(['tools/cp02_ice_false_alarm.py','--results',root/PRIOR,'--output',scratch/'cohorts'])
        for name in ('membership.csv','point_paths.csv','lead_bins.csv','summary.json'):equal(scratch/'cohorts'/name,b/'cohorts'/name)
        run(['tools/cp02_ice_surface_components.py','--replay',b/'surface/native/native_corners.npz','--output',scratch/'surface'])
        for name in ('native_corners.npz','hourly_points.csv','group_means.csv'):equal(scratch/'surface'/name,b/'surface/native'/name)
        run(['tools/plot_cp02_ice_false_alarm.py','--bundle',b,'--output',scratch/'figures'])
        figures=sorted((scratch/'figures').glob('*.png'))
        if len(figures)!=4:raise ValueError('must replay all four new figures')
        for p in figures:equal(p,b/'figures'/p.name)
        recount=run([BUNDLE/'review/independent_recount.py']);(scratch/'recount.json').write_text(recount)
        equal(scratch/'recount.json',b/'review/independent_recount.json')
        if len(checked)!=12:raise ValueError('portable artifact coverage must equal12')
        log=run(['-m','pytest','-q','--basetemp',scratch/'pytest','tests/test_cp02_ice_false_alarm.py','tests/test_cp02_ice_surface_components.py'])
        match=re.search(r'(\d+) passed',log)
        if not match or int(match.group(1))!=9:raise ValueError('all nine new tests required')
        gallery=json.loads((b/'gallery_receipt.json').read_text())
        if sha(b/'all_figures.zip')!=gallery['outputs']['all_figures.zip']['sha256']:raise ValueError('gallery archive changed')
        with zipfile.ZipFile(b/'all_figures.zip') as archive:
            if archive.testzip() is not None or set(archive.namelist())!=set(gallery['members']):raise ValueError('ZIP inventory or CRC differs')
            for name,record in gallery['members'].items():
                if sha(root/name)!=record['sha256'] or hashlib.sha256(archive.read(name)).hexdigest()!=record['sha256']:raise ValueError('ZIP member changed: '+name)
    return {'status':'PASS','byte_identical_count':12,'portable_tests_passed':9,'gallery_pngs':16,'artifacts':checked,'commands':commands,'limits':['No new WRF forecast; corner and point arrays are replayed.','Path-bearing receipts differ across roots and are hash checked separately.','Pinned Intel tests were run in the related exported suite; new tests are Python diagnostic cases.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--temporary-parent',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    if os.path.lexists(a.receipt):raise FileExistsError(a.receipt)
    result=replay(a.root.resolve(),a.temporary_parent.resolve());result['reproducer_sha256']=sha(Path(__file__))
    with a.receipt.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':'PASS','byte_identical_count':12,'portable_tests_passed':9}))
