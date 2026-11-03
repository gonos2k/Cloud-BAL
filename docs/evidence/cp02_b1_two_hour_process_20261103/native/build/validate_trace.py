from __future__ import annotations
import argparse,json
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path('/var/tmp/b1-two-hour-probe-20261103')
PHASES={'ENTRY_RAW':23,'ENTRY_CLAMPED':23,'SATURATION':16,'SATDT':13,'PREVP_FORMULA':15,'PREVP_RAW':12,'PREVP_QR_CAP':9,'PREVP_SAT_CAP':9,'PROCESS_RATES':24,'PRE_UPDATE':25,'LATENT_INPUT':14,'POST_STEP':23,'SURFACE_RETURN':9,'SNOW_RETURN':7,'GRAUPEL_RETURN':7}

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=('OLD','FIX'),required=True)
    args=parser.parse_args()
    plan=json.loads((ROOT/'case_plan.json').read_text())
    case=Path(plan['case_receipts'][args.case]['path'])
    targets={(int(c['j']),int(c['i'])) for c in json.loads((ROOT/'cells.json').read_text())['coordinates']}
    phase_count=Counter(); owner=defaultdict(set); entry=defaultdict(list); identities=Counter(); timesteps=defaultdict(set)
    files=sorted(case.glob('kdm6_trace_rank*.bits'))
    assert files, f'no trace files in {case}'
    for path in files:
        rank_from_name=int(path.stem.split('rank',1)[1])
        pending=None
        for line_number,line in enumerate(path.read_text().splitlines(),1):
            parts=line.split()
            if not parts: continue
            if parts[0] in PHASES:
                if pending is not None:
                    assert len(pending)==PHASES[pending[0]],(path,line_number,'wrapped previous record incomplete',pending[0],len(pending),PHASES[pending[0]])
                pending=parts
            elif pending is not None:
                pending.extend(parts)
            else:
                raise AssertionError(f'{path}:{line_number}: unrecognized trace continuation {parts[:2]}')
            if pending is not None and len(pending)==PHASES[pending[0]]:
                phase=pending[0]
                vals=list(map(int,pending[1:]))
                rank,call_id,itimestep=vals[:3]
                assert rank==rank_from_name,(path,line_number,rank,rank_from_name)
                assert 1<=itimestep<=360,(phase,itimestep)
                phase_count[phase]+=1
                if phase in ('ENTRY_RAW','ENTRY_CLAMPED','SATURATION','SATDT','PREVP_FORMULA','PREVP_RAW','PREVP_QR_CAP','PREVP_SAT_CAP','PROCESS_RATES','PRE_UPDATE','LATENT_INPUT','POST_STEP'):
                    loop,j,i,k=vals[3:7]
                    assert (j,i) in targets,(phase,j,i)
                    identities[(phase,rank,call_id,itimestep,loop,j,i,k)]+=1
                    timesteps[(j,i)].add(itimestep)
                    if phase=='ENTRY_RAW':
                        owner[(j,i)].add(rank)
                        entry[(rank,call_id,itimestep,j,i)].append(k)
                elif phase in ('SURFACE_RETURN','SNOW_RETURN','GRAUPEL_RETURN'):
                    j,i=vals[3:5]
                    assert (j,i) in targets,(phase,j,i)
                    identities[(phase,rank,call_id,itimestep,j,i)]+=1
                    if phase=='SURFACE_RETURN': timesteps[(j,i)].add(itimestep)
                pending=None
        assert pending is None,(path,'trailing incomplete record',pending)
    assert len(owner)==len(targets),(len(owner),len(targets),'missing trace cells')
    for cell in targets:
        assert len(owner[cell])==1,(cell,owner[cell],'duplicate MPI tile ownership')
        assert timesteps[cell]==set(range(1,361)),(cell,min(timesteps[cell]),max(timesteps[cell]),len(timesteps[cell]))
    for key,levels in entry.items():
        assert len(levels)==39 and len(set(levels))==39,(key,levels,'expected 39 unique vertical levels')
    duplicates=[(k,n) for k,n in identities.items() if n!=1]
    assert not duplicates,duplicates[:10]
    result={'status':'PASS','case':args.case,'trace_files':[p.name for p in files],'selected_cells':len(targets),'owner_rank_by_cell':{f'{j},{i}':next(iter(owner[(j,i)])) for j,i in sorted(targets)},'entry_call_groups':len(entry),'expected_levels_per_cell_call':39,'itimestep_range':[1,360],'phase_counts':dict(sorted(phase_count.items())),'duplicate_identity_count':len(duplicates),'number_words':'All real values are logged by TRANSFER to signed int32 decimal words; n0r is signed int64.'}
    (case/'trace_validation.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__': main()
