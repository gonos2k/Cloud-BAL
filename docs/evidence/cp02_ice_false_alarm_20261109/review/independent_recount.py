#!/usr/bin/env python3
"""Independent Boolean recount from the frozen forecast evaluation arrays."""
import hashlib
import json
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parents[4]
folder = root / 'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results'
b1, prior, new = 'IMPROVED_BG_FIXED', 'CONSERVATIVE_SEDIMENTATION', 'FIRST_ICE_VELOCITY'
inputs = {}
weak = []
for lead in range(1, 7):
    path = folder / f'hour_{lead + 12}_arrays.npz'
    inputs[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    with np.load(path, allow_pickle=False) as data:
        obs = data['reference']
        assert len(obs) == 3688 and np.isfinite(obs).all()
        assert all(np.isfinite(data[c]).all() and data[c].shape == obs.shape for c in (b1, prior, new))
        subset = (obs >= .1) & (obs < 1)
        counts = [int(np.count_nonzero(subset & (data[c] >= .1))) for c in (b1, prior, new)]
        assert counts[0] < counts[2] < counts[1]
        weak.append(counts)
        if lead == 1:
            fa = (obs < 10) & (data[b1] < 10) & (data[new] >= 10)
            ids = sorted(map(int, data['flat_index_yx'][fa]))
            assert ids == [10813, 11571, 11855]
        if lead == 6:
            dry = obs < 5
            old = dry & (data[b1] < 5) & (data[prior] >= 5)
            current = dry & (data[b1] < 5) & (data[new] >= 5)
            masks = [int(np.count_nonzero(x)) for x in (old, current, old & current, current & ~old, old & ~current)]
            assert masks == [102, 91, 65, 26, 37]
            transitions = []
            for case in (prior, b1):
                transitions.append([int(np.count_nonzero(dry & (data[case] < 5) & (data[new] >= 5))),
                                    int(np.count_nonzero(dry & (data[case] >= 5) & (data[new] < 5)))])
            assert transitions == [[48, 50], [91, 32]]
            bins = [int(np.count_nonzero(current & (obs >= lo) & (obs < hi))) for lo, hi in ((0,.1),(.1,1),(1,5))]
            assert bins == [38, 17, 36]
            high_forecast = int(np.count_nonzero(current & (data[new] >= 10)))
            assert high_forecast == 9
print(json.dumps({'status':'PASS','inputs_sha256':inputs,'h6_fixed_masks_old_new_persistent_new_resolved':masks,
                  'h6_full_transitions_prior_then_b1_gained_lost':transitions,
                  'h6_new_cohort_observation_bins':bins,'h1_new_10mm_fa_ids_vs_b1':ids,
                  'h6_new_cohort_forecast_at_least_10mm':high_forecast,
                  'weak_observed_h1_to_h6_detections_b1_prior_new':weak}, indent=2))
