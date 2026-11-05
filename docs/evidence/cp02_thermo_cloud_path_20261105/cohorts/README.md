# Thermodynamic and cloud trace cohort

`protocol.json` was frozen before selection and binds the immutable PR146 paired arrays, PR147 initial native-corner states and focus ledger. The independent selector recomputes the events and exact equality of initial QNRAIN at each positive-weight native corner over all 39 levels; it then cross-checks the resulting 15 new false alarms, 12 removed false alarms and six weak hit losses against PR147. The new-false-alarm set contains flat indices 17051 and 20183.

For each weak loss in ascending flat-index order, the selector chooses the nearest unused retained weak hit by great-circle distance; an exact distance tie uses the lower flat index. These are geographic comparators, not physically matched controls. The six distances range from approximately 5.1 to 22.9 km. The stable ID pairs appear in `results/selected_points.csv` through the matched lost-point flat index.

The 39 distinct RN1 points have 156 point-corner rows. Their stencils share 33 corner references, giving 123 unique native cells in `results/unique_global_corners.csv`. `results/point_corners.csv` preserves all four bilinear weights per point and explicit zero-based and Fortran one-based native indices. Deduplication applies only to the native instrumentation cell list, not to point weights. No forecast score, policy, or causal conclusion follows from this cohort.

Reproduce to a fresh output directory:

```sh
python tools/cp02_thermo_cloud_cohorts.py --output /tmp/cp02_thermo_cohort_replay
pytest -q tests/test_cp02_thermo_cloud_cohorts.py
```
