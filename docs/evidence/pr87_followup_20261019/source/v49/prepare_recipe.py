from pathlib import Path
import sys,json,hashlib
repo=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr87_two_step_20261016/Cloud-BAL')
sys.path.insert(0,str(repo/'tools'))
from pr87_graupel_cone_mixture import extend_graupel_cone_mixture, extend_graupel_cone_solve_em
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
parent=Path('/var/tmp/pr87_followup_sources_20261019_v44/sources.json')
d=json.loads(parent.read_text());out=Path('/var/tmp/pr87_followup_sources_20261019_v49');out.mkdir(exist_ok=False)
original=Path(d['source_overrides']['module_em.o']);em=out/'module_em_pr85.F';em.write_text(extend_graupel_cone_mixture(original.read_text()))
solve_original=Path(d['source_overrides']['solve_em.o']);solve=out/'solve_em.F';solve.write_text(extend_graupel_cone_solve_em(solve_original.read_text()))
ov=dict(d['source_overrides']);ov['module_em.o']=str(em);ov['solve_em.o']=str(solve)
(out/'overrides.json').write_text(json.dumps(ov,indent=2)+'\n')
manifest={'schema':'pr87_small_graupel_sources_v2','identity':'V49: V44 plus certified common-source mixtures and joint fallback orchestration','parent_baseline':'V44','parent_manifest':str(parent),'parent_manifest_sha256':sha(parent),'source_overrides':ov,'source_sha256':{member:sha(Path(path)) for member,path in ov.items()},'transforms':{**d['transforms'],'pr87_graupel_cone_mixture.py':sha(repo/'tools/pr87_graupel_cone_mixture.py')},'candidate_source_sha256':d['candidate_source_sha256'],'candidate_module_em_sha256':sha(em),'physics_changed':True,'public_input_policy_changed':False,'scope':'selected-object research partialhost, same initial inputs/FP; no scientific acceptance'}
(out/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'source_manifest':str(out/'sources.json'),'module_em_sha256':sha(em)}))
