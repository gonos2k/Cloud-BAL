# PR104 reader evidence

This folder records bounded checks for the explicit-time observation reader. It contains no WRF history arrays or station-level temperatures.

## PR103 regression

`reader_regression.json` pins the baseline PR103 v2 output and the reproduced output. The check reran:

```sh
python tools/pr103_surface_temperature_observation.py --output /tmp/pr103_regression_pr104.json
```

The five arm metric maps and all 765 matched station rows were identical to the v2 evidence. The JSON contains the baseline/output/source hashes and canonical summary hashes.

## Model-only operator diagnostic

`model_only_13z10_operator_check.py` is a read-only, pinned reproduction command:

```sh
python docs/evidence/pr104_validtime_observation_20261026/reader/model_only_13z10_operator_check.py \
  > docs/evidence/pr104_validtime_observation_20261026/reader/model_only_13z10_operator_check.json
```

It applies the PR103 station mapping and interpolation to the exact 13:10 history record from the closed N/A 640-second runs, at the 803 locations in the 14Z LSO file. The observation temperatures are not used in arithmetic. Result: 803 paired locations, no stencil exclusions, nonzero `H(XN)-H(XA)` signal, RMS 0.028147911089433403 °C and maximum absolute difference 0.2840157245936439 °C. These are model-only operator diagnostics; they are not observation residuals or forecast-skill results.

The LSO and history paths, record indices, and SHA-256 pins are recorded in the JSON result. The 14Z comparison requires closed H/A/N 14Z history records and is not included here.
