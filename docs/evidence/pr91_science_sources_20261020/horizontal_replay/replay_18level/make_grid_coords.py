from pathlib import Path
from netCDF4 import Dataset
import numpy as np
bundle=Path(__file__).resolve().parent
path='/var/tmp/pr82_same13_real_candidate.final20261012/met_em.d01.2026-08-16_13:00:00.nc'
with Dataset(path) as ds:
    lat=np.asarray(ds['XLAT_M'][0],dtype=np.float32)
    lon=np.asarray(ds['XLONG_M'][0],dtype=np.float32)
with (bundle/'target_grid_234x282.txt').open('w') as f:
    for j in range(lat.shape[0]):
        for i in range(lat.shape[1]):
            f.write(f'{i} {j} {lat[j,i]:.9g} {lon[j,i]:.9g}\n')
print('target_grid_points',lat.size,'shape_yx',lat.shape)
