#!/bin/bash
set -euo pipefail
python docs/evidence/first_hour_zero_rate_20261030/species_scoring/score_species.py \
 --case H_ORIGINAL_QR=/var/tmp/firsthour-runtime-plan-20261030/species_ablation/run_H_ORIGINAL_QR \
 --case H_ORIGINAL_QS=/var/tmp/firsthour-runtime-plan-20261030/species_ablation/run_H_ORIGINAL_QS \
 --preparation /var/tmp/firsthour-runtime-plan-20261030/species_ablation/preparation.json \
 --reference-dir /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/reference \
 --analysis /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300 \
 --odam-dir /NHNHOME/DATA/yhlee_data/ODAM/20260816 \
 --output docs/evidence/first_hour_zero_rate_20261030/species_scoring/results
