import hashlib,json,pathlib,shutil,tempfile,shlex
root=pathlib.Path('/var/tmp/cloudbal-cp02-kdm6-controls')
e=root/'docs/evidence/cp02_kdm6_controls_20261029'
m=json.loads((e/'inputs/copy_manifest.json').read_text())
p=json.loads((e/'inputs/provenance.json').read_text())
def sha(p): return hashlib.file_digest(open(p,'rb'),'sha256').hexdigest()
s=pathlib.Path(tempfile.mkdtemp(prefix='cp02-kdm6-controls-20261029-',dir='/var/tmp'))
b=pathlib.Path(p['RUNNING_receipt']['executable'])
assert sha(b)==p['RUNNING_receipt']['executable_sha256']
shutil.copy2(b,s/'wrf.exe')
shutil.copy2(root/'docs/evidence/cp02_wrf_first_call_20261029/capture/selection.json',s/'selection.json')
for arm,a in m['arms'].items():
 d=s/arm; (d/'run').mkdir(parents=True); (d/'capture').mkdir()
 for f in a['copy_files']:
  src=pathlib.Path(f['source_path']); assert sha(src)==f['sha256']; shutil.copy2(src,d/'run'/f['destination_name']); assert sha(d/'run'/f['destination_name'])==f['sha256']
 (d/'rank_wrapper.sh').write_text('#!/bin/bash\nset -euo pipefail\nrank=${PMI_RANK:?}\nexec /usr/bin/gdb --batch -x "$CP02_CAPTURE_SCRIPT" "$CP02_BINARY" > "$CP02_CAPTURE_DIR/gdb_rank${rank}.txt" 2>&1\n')
 (d/'rank_wrapper.sh').chmod(0o755)
 q=shlex.quote
 (d/'launch.sh').write_text(f'''#!/bin/bash
set -euo pipefail
source {q(str(root/'tests/intel_toolchain.sh'))}
export OMP_NUM_THREADS=1
ulimit -s unlimited
export CP02_CAPTURE_DIR={q(str(d/'capture'))}
export CP02_SELECTION_JSON={q(str(s/'selection.json'))}
export CP02_CAPTURE_SCRIPT={q(str(s/'capture_kdm6.gdb'))}
export CP02_BINARY={q(str(s/'wrf.exe'))}
cd {q(str(d/'run'))}
set +e
timeout --kill-after=10 600 mpirun -np 8 {q(str(d/'rank_wrapper.sh'))} > {q(str(d/'launcher.txt'))} 2>&1
rc=$?
printf '%s\\n' "$rc" > {q(str(d/'launcher.exit'))}
exit "$rc"
''')
(s/'source_plan.json').write_text(json.dumps({'source':str(e),'copy_manifest_sha256':sha(e/'inputs/copy_manifest.json')},indent=2)+'\n')
pathlib.Path('/var/tmp/cp02_controls_scratch_path').write_text(str(s))
print(s)
