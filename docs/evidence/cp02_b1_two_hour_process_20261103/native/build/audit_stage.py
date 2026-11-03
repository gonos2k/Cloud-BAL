import json,hashlib,subprocess
from pathlib import Path
S=Path('/var/tmp/cloudbal-recount-contract'); E=S/'docs/evidence/recount_contract_20261103'; K=E/'kg'; L=K/'selection_lock.json'; B=K/'baseline.json'; R=K/'stage_receipt.json'; M=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50'); r=json.load(open(R)); l=json.load(open(L)); b=json.load(open(B)); stage=Path(r['stage'])
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stats(g):return {'nodes':len(g.get('nodes',[])),'edges':len(g.get('links',g.get('edges',[]))),'communities':len({n.get('community') for n in g.get('nodes',[]) if n.get('community') is not None})}
def integ(g):
 ns={n['id'] for n in g.get('nodes',[]) if 'id'in n}; es=g.get('links',g.get('edges',[])); ps=[(x.get('source'),x.get('target')) for x in es]; from collections import Counter; c=Counter(ps); exact=[json.dumps(x,sort_keys=True,separators=(',',':')) for x in es]
 return {'missing_endpoint_edges':sum(a is None or z is None for a,z in ps),'dangling_endpoint_edges':sum((a is not None and a not in ns)or(z is not None and z not in ns)for a,z in ps),'self_loop_edges':sum(a==z for a,z in ps),'exact_duplicate_edges':len(exact)-len(set(exact)),'same_endpoint_group_count':sum(v>1 for v in c.values())}
assert sha(B)==r['baseline_sha256']==l['baseline_sha256'] and sha(L)==r['selection_lock_sha256']
assert r['status']=='STAGED_ONLY_NO_MAINTAINED_WRITES' and r['maintained_roots_written'] is False and l['status']=='FROZEN' and l['review_status']=='GO'
assert r['snapshot']=='2026-11-03-recount-contract' and l['freeze_id'] in r['stage']
selected=l['selected_source_sha256']; ho=l['hash_only_sha256']; assert len(selected)==3 and len(ho)==34 and set(selected)==set(r['source_extraction_scope'])==set(r['manifest_update_scope'])
assert all(sha(S/p)==h==r['corpora']['Cloud-BAL']['selected_source_sha256'][p] for p,h in selected.items())
assert all(sha(S/p)==h==r['hash_only_sha256'][p] for p,h in ho.items())
snap_count=snap_files=0
for label,root in [('KLAPS50',M),('Cloud-BAL',M/'Cloud-BAL')]:
 br=b['maintained_roots'][label]
 for f,k in [('graph.json','graph_sha256'),('GRAPH_REPORT.md','graph_report_sha256'),('manifest.json','manifest_sha256')]:assert sha(root/'graphify-out'/f)==br[k]
 actual={}
 for d in (root/'graphify-out').iterdir():
  if d.is_dir() and d.name[:4].isdigit():actual[d.name]={p.relative_to(d).as_posix():sha(p) for p in d.rglob('*') if p.is_file()}
 assert actual==br['dated_snapshots']
 snap_count+=len(actual); snap_files+=sum(len(v) for v in actual.values())
 st=subprocess.check_output(['git','-C',str(root),'status','--short'],text=True)
 assert st.splitlines()==br['git_status_exact'] and hashlib.sha256(st.encode()).hexdigest()==br['git_status_raw_sha256']
assert snap_count==230 and snap_count==b['dated_snapshot_count_total']
assert all(sha(M/'wiki'/n)==h for n,h in b['wiki_hashes'].items())
graphs={}; manifest_checks={}; target_hashes={}
for label in ('KLAPS50','Cloud-BAL'):
 root=M if label=='KLAPS50' else M/'Cloud-BAL'; sr=stage/label; old=json.load(open(root/'graphify-out/graph.json')); new=json.load(open(sr/'graphify-out/graph.json')); oldids={n['id'] for n in old['nodes'] if 'id'in n}; newids={n['id'] for n in new['nodes'] if 'id'in n}; assert oldids<=newids
 rec=r['corpora'][label]; assert len(oldids)==rec['prior_node_ids_preserved'] and stats(old)==rec['before'] and stats(new)==rec['after']; ii=integ(new); assert ii==rec['integrity_zero_counts'] and not any(ii.values())
 sd=sr/'graphify-out/2026-11-03-recount-contract'; assert {p.name for p in sd.iterdir()}=={'graph.json','GRAPH_REPORT.md','manifest.json'}
 for f in ('graph.json','GRAPH_REPORT.md','manifest.json'):
  assert sha(sd/f)==rec['snapshot_file_sha256'][f]==sha(sr/'graphify-out'/f); target_hashes[f'{label}:{f}']=sha(sr/'graphify-out'/f)
 prefix='Cloud-BAL/' if label=='KLAPS50' else ''
 for p,h in selected.items(): assert sha(sr/prefix/p)==h
 om=json.load(open(root/'graphify-out/manifest.json')); nm=json.load(open(sr/'graphify-out/manifest.json')); assert set(om)<=set(nm); changed={k for k in set(om)|set(nm) if om.get(k)!=nm.get(k)}; assert changed=={prefix+p for p in selected}; manifest_checks[label]={'changed_keys':sorted(changed),'old_entries_preserved':len(om),'new_entries':len(set(nm)-set(om))}
 for f in ('graph.json','GRAPH_REPORT.md','manifest.json'):target_hashes[f'{label}:active:{f}']=sha(sr/'graphify-out'/f)
 graphs[label]={'before':stats(old),'after':stats(new),'preserved_prior_nodes':len(oldids),'new_node_ids':len(newids-oldids),'integrity':ii,'snapshot_hashes':rec['snapshot_file_sha256']}
for n,h in r['staged_wiki_sha256'].items():assert sha(stage/'wiki'/n)==h;target_hashes['wiki:'+n]=sha(stage/'wiki'/n)
assert len(target_hashes)==17
for lbl in ('KLAPS50','Cloud-BAL'):
 t=(stage/lbl/'graphify-out/GRAPH_REPORT.md').read_text();assert 'Only 3 frozen Python source paths are structurally extracted.' in t and 'no corpus scan or prune occurs.' in t and 'Graph freshness does not establish runtime or scientific validation.' in t
idx=(stage/'wiki/index.md').read_text(); log=(stage/'wiki/log.md').read_text();assert 'Graph freshness does not establish runtime or scientific validation.' in idx and '3 Python files extracted' in log
clean=json.load(open(E/'validation/clean_export_tests.json')); normal=json.load(open(E/'validator/normal_saved_arrays_before_after.json')); c2=json.load(open(E/'c2/validation.json'))
assert clean['status']=='PASS' and clean['exit_code']==0 and '152 passed' in (E/'validation/clean_export_tests.txt').read_text()
assert normal['before_status']==normal['after_status']=='PASS' and normal['before_independently_recounted_rows']==normal['after_independently_recounted_rows'] and normal['same_analysis_receipt_sha256']
assert c2['model_forecast_run_performed'] is False and c2['C2_1h_completion']=='NOT_ACHIEVED' and c2['first_producer_stencil_for_group']=='STILL_NOT_CAPTURED'
assert '모델 trace는 아직 시작하거나 완료하지 않았으며' in (S/'docs/CURRENT_RESEARCH_STATUS.md').read_text()
assert 'Preparation outside this worktree is not a completed or validated model trace.' in (E/'README.md').read_text()
val={'status':'PASS_STAGED_ONLY','snapshot':r['snapshot'],'source_commit':l['source_commit'],'stage_root':str(stage),'stage_receipt_sha256':sha(R),'selection_lock_sha256':sha(L),'baseline_sha256':sha(B),'selected_source_count':len(selected),'selected_source_mismatches':0,'hash_only_count':len(ho),'hash_only_mismatches':0,'maintained_snapshot_count':snap_count,'maintained_snapshot_file_count':snap_files,'prior_snapshot_mismatches':0,'maintained_root_git_dirty_state_exact':True,'maintained_active_graph_files_unchanged':True,'maintained_wiki_mirror_mismatches':0,'staged_target_count':13,'staged_file_hash_checks':len(target_hashes),'staged_target_hash_mismatches':0,'graphs':graphs,'manifest_subset_checks':manifest_checks,'claim_scope_checks':{'152_related_tests_passed':True,'normal_saved_arrays_before_after_identical':True,'C2_local_replays_only_no_forecast':True,'first_producer_stencil_open':True,'phase2_native_trace_planned_not_complete':True,'no_runtime_or_scientific_claim_in_graph_update':True},'extraction_scope':{'selected_python_paths':sorted(selected),'hash_only_paths':len(ho),'manifest_update_selected_keys_only':True,'broad_corpus_scan_or_prune':False,'fortran_cross_file_extraction':'PARTIAL'},'maintained_roots_written':False}
(K/'stage_validation.json').write_text(json.dumps(val,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':'PASS','snapshots':snap_count,'files':snap_files,'targets':13,'graph_deltas':{k:{'nodes':v['after']['nodes']-v['before']['nodes'],'edges':v['after']['edges']-v['before']['edges'],'communities':v['after']['communities']-v['before']['communities']} for k,v in graphs.items()},'stage_validation':str(K/'stage_validation.json')},indent=2))
