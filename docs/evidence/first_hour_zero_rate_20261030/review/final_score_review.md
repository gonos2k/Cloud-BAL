# Independent score review — 2026-10-30

Independently recalculated all 30 categorical rows, 5 continuous rows and 12 paired-transition rows directly from the saved paired arrays, using inclusive thresholds and separate NumPy expressions. H/M/F/correct-dry and transition counts matched exactly; CSI, ETS, POD, FAR, frequency bias, forecast/reference means, ME, MAE and RMSE agreed to 1e-12. The six thresholds are 0.1, 0.5, 1, 2.5, 5 and 10 mm per hour, with 3,688 common points.

For HYDRO, FIX increases CSI at 0.1, 0.5, 1, 2.5 and 10 mm, but decreases it at 5 mm from 0.21401 to 0.20472. ME changes from -0.06177 to -0.05313 mm, MAE from 1.13293 to 1.12042 mm, and RMSE from 4.11029 to 4.09169 mm. At 0.1 mm, 89 hit gains and 10 losses accompany 35 false-alarm gains and 7 losses.

For ORIGINAL, FIX increases CSI at all six thresholds. ME changes from +0.00971 to +0.02443 mm, MAE from 1.11420 to 1.10039 mm, and RMSE from 4.06229 to 4.04446 mm. At 0.1 mm, 88 hit gains and 7 losses accompany 37 false-alarm gains and 2 losses; the signed mean bias moves farther from zero. SHAM, BASE_H and BASE_ORIGINAL reproduce their pinned archived hourly arrays exactly.

These are paired counterfactual changes for one case and a processed RN1 reference without a resolved coverage bitmap or temporal representativeness; they do not establish general improvement or whole-model water/energy closure. The isolated fragment and captured operands establish a mechanism that can create evaporation from a zero rate; the experiment estimates the effect of changing that branch, rather than proving the sole cause of the original forecast deterioration.
