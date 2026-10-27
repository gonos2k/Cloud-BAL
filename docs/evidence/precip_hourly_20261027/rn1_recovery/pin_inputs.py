#!/usr/bin/env python3
"""Hash the bounded input set for the raw RN1 rescore."""
import hashlib, json
from pathlib import Path
BASE=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914')
ODAM=Path('/NHNHOME/DATA/yhlee_data/ODAM/20260816')
ANAL=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300')
OUT=Path('/var/tmp/rn1-rescore-final-20261027')
paths=[BASE/'compare_six_hour_csi.py', BASE/'reference/inventory.json', BASE/'reference/mask_receipt.json', BASE/'reference/south_korea_land_mask_149x253_uint8_fortran.bin', BASE/'run_contract.md', BASE/'ONE_HOUR_REPRODUCTION.json', ANAL]
paths += [BASE/case/'run'/f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for case in ('off','hydro','liquid') for hour in range(12,19)]
paths += [ODAM/f'DFS_VSRT_GRD_KLPS_ODAM_RN1.20260816{hour:02d}00' for hour in range(13,19)]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
records=[]
for p in paths:
 st=p.stat()
 records.append({'path':str(p),'size':st.st_size,'sha256':sha(p)})
(OUT / ('input_pins_'+__import__('sys').argv[1]+'.json')).write_text(json.dumps({'count':len(records),'inputs':records},indent=2)+'\n')
