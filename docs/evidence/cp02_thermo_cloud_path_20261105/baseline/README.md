# Independent PR147 observation replay

`pr147_observation_replay.csv` rechecks all 279 initial-NR-unchanged false-alarm points, including all positive-weight native corners and all 39 levels. The five new false alarms whose two arms both have zero QR and NR at +1 h are 16606, 17051, 17199, 17792 and 20183. The associated JSON's `id20183_qv_max_level_1based` and `id20183_t_max_level_1based` refer specifically to maximum absolute differences at individual raw corners for QVAPOR and perturbation potential-temperature T. They are not the maxima of bilinear profiles.

`pr147_profile_maxima.csv` separately compares the 39-level saved bilinear QVAPOR, physical temperature and pressure profiles for those five points, and repeats the distinctly named raw-corner maxima. For 20183 both bilinear QVAPOR and physical-temperature maxima occur at level 2; raw-corner QVAPOR and perturbation-T maxima occur at level 4. The raw T variable is not physical temperature.

All values are fixed-location snapshots, not trajectories or causal attributions. A +1 h difference only establishes that the fields differ at that sample, not the time at which the difference first arose. The RH and temperature group medians in the replay receipt are descriptive differences computed from saved float32 summaries.
