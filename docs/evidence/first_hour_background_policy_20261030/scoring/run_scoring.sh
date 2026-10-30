#!/bin/bash
set -euo pipefail
python docs/evidence/first_hour_background_policy_20261030/scoring/score_producer.py \
 --reference-dir /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/reference \
 --analysis /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300 \
 --odam-dir /NHNHOME/DATA/yhlee_data/ODAM/20260816 \
 --output docs/evidence/first_hour_background_policy_20261030/scoring/results
