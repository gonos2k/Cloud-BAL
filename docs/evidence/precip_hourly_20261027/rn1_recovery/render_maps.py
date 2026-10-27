from pathlib import Path
import sys
root=Path('/var/tmp/cloudbal-precip-validation')
sys.path.insert(0,str(root/'tools'))
from plot_hourly_precip_scores import make_first_hour_precipitation_plot
p=root/'docs/evidence/precip_hourly_20261027/rn1_recovery'
for h in range(13,19):
 out=p/f'maps/hour_{h}';out.mkdir(parents=True,exist_ok=False)
 make_first_hour_precipitation_plot(out,p/f'hour_{h}_arrays.npz',f'2026-08-16T{h-1:02d}:00:00Z',f'2026-08-16T{h:02d}:00:00Z','RN1 reference (raw file replay)')
 print('rendered',h,flush=True)
