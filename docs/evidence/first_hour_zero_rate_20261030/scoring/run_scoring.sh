#!/bin/bash
set -euo pipefail
python docs/evidence/first_hour_zero_rate_20261030/scoring/score_first_hour.py \
  --case SHAM=/var/tmp/firsthour-runtime-plan-20261030/experiment/run_SHAM \
  --case BASE_H=/var/tmp/firsthour-runtime-plan-20261030/experiment/run_BASE_H \
  --case FIX_H=/var/tmp/firsthour-runtime-plan-20261030/experiment/run_FIX_H \
  --case BASE_ORIGINAL=/var/tmp/firsthour-runtime-plan-20261030/experiment/run_BASE_ORIGINAL \
  --case FIX_ORIGINAL=/var/tmp/firsthour-runtime-plan-20261030/experiment/run_FIX_ORIGINAL \
  --build-receipt docs/evidence/first_hour_zero_rate_20261030/runtime/build_receipt.json \
  --reference-dir /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/reference \
  --analysis /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300 \
  --odam-dir /NHNHOME/DATA/yhlee_data/ODAM/20260816 \
  --output docs/evidence/first_hour_zero_rate_20261030/scoring/results
