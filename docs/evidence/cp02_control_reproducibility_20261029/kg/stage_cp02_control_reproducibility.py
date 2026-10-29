from __future__ import annotations
import hashlib, importlib.util, json, re, shutil, subprocess, sys
import graphify
from graphify.dedup import deduplicate_entities
from pathlib import Path

SOURCE = Path('/var/tmp/cloudbal-cp02-capture-evidence')
ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
MAINT = ROOT / 'Cloud-BAL'
STAGE = Path('/var/tmp/cp02_reproducibility_kg_20261029')
KG_DIR = Path('/var/tmp/cloudbal-cp02-capture-evidence/docs/evidence/cp02_control_reproducibility_20261029/kg')
RECEIPT_PATH = KG_DIR / 'stage_receipt.json'
BASELINE_PATH = KG_DIR / 'baseline.json'
SELECTION_PATH = KG_DIR / 'selection_lock.json'
DATE = '2026-10-29'
SNAPSHOT = DATE + '-cp02-reproducibility'
SOURCE_COMMIT = '8c278b643c5fa2b663f32d2b68d0f59e0301a989'
SELECTED_PATHS = (
 'tools/cp02_control_density_comparison.py',
 'tests/test_cp02_control_density_comparison.py',
 'tests/test_cp02_density_evidence.py',
)
WIKI_FILES = ('graph-report.md','graph-report-klaps50.md','graph-report-cloud-bal.md','index.md','log.md')
POST_STAGE_EXCLUDED_PATHS = (
 'docs/evidence/cp02_control_reproducibility_20261029/kg/',
 'docs/evidence/cp02_control_reproducibility_20261029/validation.json',
)


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def load_json(path: Path): return json.loads(path.read_text())
def write_json(path: Path, value): path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
def require(condition, message):
 if not condition: raise RuntimeError(message)

def load_module(name, path):
 spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader
 module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module); return module

def current_snapshot_inventory(root: Path):
 result={}
 for folder in sorted((root/'graphify-out').iterdir()):
  if folder.is_dir() and folder.name[:4].isdigit():
   result[folder.name]={p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()}
 return result

def baseline_check(label, root, baseline):
 b=baseline['maintained_roots'][label]; gd=root/'graphify-out'
 require(sha(gd/'graph.json')==b['graph_sha256'],f'{label} maintained graph baseline changed')
 require(current_snapshot_inventory(root)==b['dated_snapshots'],f'{label} dated snapshots changed')
 require(subprocess.check_output(['git','-C',str(root),'status','--short'],text=True).splitlines()==b['git_status_exact'],f'{label} maintained dirty status changed')

def copy_graph_layer(src: Path, dst: Path):
 dst.mkdir(parents=True)
 for item in sorted(src.iterdir()):
  if item.is_dir(): continue
  require(item.is_file() and not item.is_symlink(),f'unsupported graphify layer member {item}')
  if item.name == '.rebuild.lock': continue
  shutil.copy2(item,dst/item.name)

def main():
 require('/.local/share/uv/tools/graphifyy/' in str(Path(sys.executable).resolve()) or '/.local/share/uv/tools/graphifyy/' in str(Path(graphify.__file__).resolve()), 'run with the pinned Graphify uv-tool interpreter')
 graphify_version=subprocess.check_output(['graphify','--version'],text=True).strip()
 require(graphify_version == 'graphify 0.9.53', 'Graphify must remain pinned at 0.9.53')
 baseline=load_json(BASELINE_PATH)
 frozen=load_json(SELECTION_PATH)
 require(frozen.get('status') == 'FROZEN' and bool(frozen.get('freeze_id')), 'selection lock is not explicitly frozen')
 require(frozen.get('review_status') == 'GO', 'three-path independent science/test review is not GO')
 require(frozen.get('source_commit') == SOURCE_COMMIT, 'selection lock source base mismatch')
 EXPECTED=frozen.get('selected_source_sha256', {})
 require(set(EXPECTED) == set(SELECTED_PATHS), 'frozen selection must contain exactly the three scoped Python paths')
 for path, expected_hash in EXPECTED.items():
  require((SOURCE/path).is_file() and sha(SOURCE/path) == expected_hash, f'frozen source hash mismatch: {path}')
 for label,root in [('KLAPS50',ROOT),('Cloud-BAL',MAINT)]: baseline_check(label,root,baseline)
 require(not STAGE.exists(),f'stage path already exists: {STAGE}')
 STAGE.mkdir()
 roots={'KLAPS50':STAGE/'KLAPS50','Cloud-BAL':STAGE/'Cloud-BAL'}
 for label,root in [('KLAPS50',ROOT),('Cloud-BAL',MAINT)]:
  (roots[label]/'graphify-out').parent.mkdir(parents=True)
  copy_graph_layer(root/'graphify-out',roots[label]/'graphify-out')
 (STAGE/'wiki').mkdir()
 for name in WIKI_FILES: shutil.copy2(ROOT/'wiki'/name,STAGE/'wiki'/name)

 updater=load_module('cp02_background_contract_scoped_updater',MAINT/'scratch/pr59_publish_kg_20261002/update.py')
 updater.SOURCE=SOURCE; updater.OUT=STAGE/'update_work'; updater.BASE_COMMIT=SOURCE_COMMIT; updater.PR='CP02 control reproducibility snapshot 2026-10-29'
 updater.OUT.mkdir()
 items=[{'path':p,'sha256':h} for p,h in EXPECTED.items()]
 old_graphs={label:load_json(roots[label]/'graphify-out/graph.json') for label in roots}
 records={}
 for label,prefix in [('KLAPS50','Cloud-BAL'),('Cloud-BAL','')]:
  records[label]=updater.update_graph(label,roots[label],prefix,items)
  old=old_graphs[label]
  new=load_json(roots[label]/'graphify-out/graph.json')
  records[label]['base_nodes']=len(old['nodes']); records[label]['base_edges']=len(old.get('links',old.get('edges',[])))
  records[label]['communities_added_removed_or_merged']=abs(records[label]['communities']-len({n.get('community') for n in old['nodes']}))
  records[label]['source_root']=str(ROOT if label=='KLAPS50' else MAINT)
  records[label]['selected_paths']=([f'Cloud-BAL/{p}' for p in EXPECTED] if label=='KLAPS50' else list(EXPECTED))
  records[label]['selected_hashes']=dict(EXPECTED)
  records[label]['snapshot']=SNAPSHOT

 # Add precise source-selection and extraction caveat to each Graphify report.
 extraction_limits=('Only the three frozen Python paths (the CP02 control density comparison and focused tests) were structurally extracted; .gitignore, logs, documents, data, manifests, and other nonselected changed files are SHA-256-bound only. This structural graph describes source relationships and does not validate runtime behavior, background data, physical assumptions, or scientific approval. Fortran cross-file CALL extraction is partial. Graph freshness does not establish runtime or scientific validation.')
 for label in ('KLAPS50','Cloud-BAL'):
  report=roots[label]/'graphify-out/GRAPH_REPORT.md'
  content=report.read_text()
  section=(f'## Graph Freshness\n\n- Source base `{SOURCE_COMMIT}`; CP02 control reproducibility; three selected Python paths, SHA-256 pinned.\n'
           f'- {extraction_limits}\n')
  content=re.sub(r'(?m)^## Graph Freshness[ \t]*\n.*?(?=^## |\Z)',lambda _:section,content,flags=re.S) if re.search(r'(?m)^## Graph Freshness[ \t]*\n',content) else content.rstrip()+'\n\n'+section
  report.write_text(content)
  shutil.copy2(report,STAGE/'wiki'/('graph-report-klaps50.md' if label=='KLAPS50' else 'graph-report-cloud-bal.md'))
  gd=roots[label]/'graphify-out'
  snap=gd/SNAPSHOT; snap.mkdir()
  for name in ('graph.json','GRAPH_REPORT.md','manifest.json'): shutil.copy2(gd/name,snap/name)
  records[label].update({'graph_sha256':sha(gd/'graph.json'),'report_sha256':sha(report),'manifest_sha256':sha(gd/'manifest.json'),'snapshot_file_hashes':{n:sha(snap/n) for n in ('graph.json','GRAPH_REPORT.md','manifest.json')}})

 graph_index=STAGE/'wiki/graph-report.md'; lines=graph_index.read_text().splitlines()
 for i,line in enumerate(lines):
  for label in ('KLAPS50','Cloud-BAL'):
   if line.startswith(f'| {label} |'):
    r=records[label]; directory='.' if label=='KLAPS50' else 'Cloud-BAL/'; mirror='graph-report-klaps50' if label=='KLAPS50' else 'graph-report-cloud-bal'
    lines[i]=(f"| {label} | `{directory}` | {SNAPSHOT} (CP02 control reproducibility)  | {r['nodes']} | {r['edges']} | {r['communities']} | [[{mirror}]] |")
 graph_index.write_text('\n'.join(lines)+'\n')
 index=STAGE/'wiki/index.md'; raw=index.read_text(); start=raw.index('## Graph snapshot'); end=raw.find('\n## ',start+3); end=len(raw) if end<0 else end
 section='## Graph snapshot\n\n'+'\n'.join(f"- {label}: {SNAPSHOT}; {records[label]['nodes']} nodes / {records[label]['edges']} edges / {records[label]['communities']} communities." for label in ('KLAPS50','Cloud-BAL'))+'\n- Separate corpus reports retain extraction limits; graph freshness is not scientific validation.\n'
 raw=raw[:start]+section+raw[end:]; raw,count=re.subn(r'(?m)^(date_modified:\s*)[^\r\n]+',lambda m:m.group(1)+DATE,raw,count=1); require(count==1,'wiki index date_modified missing/ambiguous'); index.write_text(raw)
 log=STAGE/'wiki/log.md'; entry=f'\n## [{DATE}] kg-update | CP02 control reproducibility\n- Source base `{SOURCE_COMMIT}`; source dir `{SOURCE}`; mode: scoped Graphify AST extraction + build_merge + cluster-only (3 selected paths per corpus).\n'
 for label in ('KLAPS50','Cloud-BAL'):
  r=records[label]; entry+=f"- {label}: {SNAPSHOT}; {r['nodes']} nodes / {r['edges']} edges / {r['communities']} communities; delta nodes={r['delta_nodes']}, edges={r['delta_edges']}.\n"
 entry+=f'- Selected three frozen Python paths; .gitignore, logs, documents, data, manifests, and other nonselected changes hash-bound only. {extraction_limits}\n'
 log.open('a').write(entry)

 for label in ('KLAPS50','Cloud-BAL'):
  graph_path=roots[label]/'graphify-out/graph.json'
  diagnostic=json.loads(subprocess.check_output(['graphify','diagnose','multigraph','--graph',str(graph_path),'--json'],text=True))
  summary=diagnostic['summary']
  zero_checks={name:summary[name] for name in ('missing_endpoint_edges','dangling_endpoint_edges','self_loop_edges','exact_duplicate_edges','same_endpoint_group_count')}
  require(all(value==0 for value in zero_checks.values()),f'{label} staged graph diagnostics are not clean')
  records[label]['diagnostic_summary']=summary
  records[label]['diagnostic_verified_zero_counts']=zero_checks
 for label,root in [('KLAPS50',ROOT),('Cloud-BAL',MAINT)]: baseline_check(label,root,baseline)
 require(subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip() == SOURCE_COMMIT, 'source HEAD changed from graph-selection base')
 require(sum(len(c['dated_snapshots']) for c in baseline['maintained_roots'].values()) == 188, 'baseline dated snapshot count is not 188')
 changed=set(subprocess.check_output(['git','-C',str(SOURCE),'diff','--name-only','HEAD'],text=True).splitlines()) | set(subprocess.check_output(['git','-C',str(SOURCE),'ls-files','--others','--exclude-standard'],text=True).splitlines())
 require(not any(path.startswith('graphify-out/') for path in changed), 'isolated source graphify-out changes must be cleaned before staging')
 selected=set(EXPECTED)
 require(selected <= changed, 'selected code paths are not all in the frozen source change set')
 hash_only=sorted(path for path in changed-selected if not any(path == excluded or (excluded.endswith('/') and path.startswith(excluded)) for excluded in POST_STAGE_EXCLUDED_PATHS))
 hash_only_hashes={p:sha(SOURCE/p) for p in hash_only if (SOURCE/p).is_file()}
 receipt={'status':'STAGED_ONLY_NO_MAINTAINED_WRITES','graphify_version':graphify_version,'source_commit':SOURCE_COMMIT,'source_root':str(SOURCE),'source_base_commit':SOURCE_COMMIT,'snapshot':SNAPSHOT,'final_freeze_id':frozen.get('freeze_id'),'selected_code_paths':list(EXPECTED),'selected_source_sha256':EXPECTED,'hash_only_changed_paths':hash_only,'hash_only_changed_sha256':hash_only_hashes,'post_stage_excluded_paths':list(POST_STAGE_EXCLUDED_PATHS),'post_stage_exclusion_reason':'The final validation receipt and derived KG subtree are explicitly excluded because they are finalized after graph staging; every other nonselected changed file is SHA-256-bound.','corpora':records,'extraction_limits':extraction_limits,'preservation_verified':{'KLAPS50':'graph hash, full dated-snapshot inventory and maintained git status unchanged','Cloud-BAL':'graph hash, full dated-snapshot inventory and maintained git status unchanged'},'staged_wiki_files':list(WIKI_FILES)}
 write_json(RECEIPT_PATH,receipt)
 written=load_json(RECEIPT_PATH)
 require(written.get('status') == 'STAGED_ONLY_NO_MAINTAINED_WRITES' and written.get('snapshot') == SNAPSHOT, 'stage receipt status/snapshot schema mismatch')
 require(set(written.get('selected_source_sha256', {})) == set(SELECTED_PATHS), 'stage receipt selected-source schema mismatch')
 require(set(written.get('corpora', {})) == {'KLAPS50', 'Cloud-BAL'}, 'stage receipt corpus schema mismatch')
 for label, record in written['corpora'].items():
  require(set(record.get('snapshot_file_hashes', {})) == {'graph.json', 'GRAPH_REPORT.md', 'manifest.json'}, f'{label} stage receipt snapshot hash schema mismatch')
  require(set(record.get('diagnostic_verified_zero_counts', {})) == set(zero_checks), f'{label} stage receipt diagnostic schema mismatch')
  require(all(value == 0 for value in record['diagnostic_verified_zero_counts'].values()), f'{label} stage receipt diagnostic values mismatch')
  require(record.get('selected_hashes') == written['selected_source_sha256'], f'{label} stage receipt selected hashes mismatch')
 print(json.dumps(written,indent=2))

if __name__=='__main__': main()
