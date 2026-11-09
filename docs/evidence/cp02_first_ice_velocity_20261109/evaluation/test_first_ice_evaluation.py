import json
from pathlib import Path
import sys
import numpy as np
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate as e


def cohort():
    arrays={}
    for h in e.HOURS:
        obs=np.zeros(3688); obs[:5]=[.2,.7,1.,5.,10.]
        base=obs.copy(); candidate=obs.copy(); candidate[:4]=[0,.7,1.,0]; candidate[5]=.2
        arrays[h]={'reference':obs,'latitude':np.arange(3688,dtype=float),'longitude':np.arange(3688,dtype=float),'flat_index_yx':np.arange(3688),e.ORIGINAL:base.copy(),e.B1:base.copy(),e.CONS:base.copy(),e.NEW:candidate}
    return arrays


def test_scores_constraints_and_observed_transitions():
    cat,continuous,checks,transitions=e.score(cohort())
    assert (len(cat),len(continuous),len(checks),len(transitions)) == (144,24,52,48)
    row=next(x for x in cat if x['lead_hour']==1 and x['case']==e.NEW and x['threshold_mm']==.1)
    assert (row['hit'],row['miss'],row['false_alarm'])==(3,2,1)
    weak=next(x for x in transitions if x['lead_hour']==2 and x['baseline']==e.B1 and x['observation_subset']=='weak_observed')
    assert (weak['n_observed_subset'],weak['forecast_gained'],weak['forecast_lost'],weak['forecast_both_at_or_above']) == (2,0,1,1)
    dry=next(x for x in transitions if x['lead_hour']==2 and x['baseline']==e.CONS and x['observation_subset']=='dry_observed')
    assert (dry['forecast_gained'],dry['forecast_lost'])==(1,0)
    assert len([x for x in checks if x['candidate']==e.NEW and x['goal']=='preserve_current_B1'])==11
    assert len([x for x in checks if x['candidate']==e.NEW and x['goal']=='recover_low_threshold_vs_ORIGINAL'])==15
    assert not next(x for x in checks if x['candidate']==e.NEW and x['lead_hour']==1 and x['threshold_mm']==.1)['satisfied']


def test_point_identity_cannot_change():
    arrays=cohort(); arrays[14]['latitude'][0] += 1
    with pytest.raises(ValueError,match='cohort changed'): e.score(arrays)


def test_sealed_arrays_reject_tampering(tmp_path):
    arrays=cohort(); hashes={}
    for h,v in arrays.items():
        path=tmp_path/f'hour_{h}_arrays.npz'; np.savez_compressed(path,**v); hashes[path.name]=e.identity(path)['sha256']
    (tmp_path/'receipt.json').write_text(json.dumps({'status':'COMPLETE','outputs':hashes}))
    assert len(e.read_arrays(tmp_path))==6
    with (tmp_path/'hour_14_arrays.npz').open('ab') as f: f.write(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'): e.read_arrays(tmp_path)


def test_atomic_publish_does_not_replace_existing(tmp_path):
    stage=tmp_path/'stage'; target=tmp_path/'result'; stage.mkdir(); target.mkdir()
    (target/'keep').write_text('unchanged')
    with pytest.raises(FileExistsError): e.publish_new(stage,target)
    assert stage.is_dir() and (target/'keep').read_text()=='unchanged'
