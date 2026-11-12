from collections import Counter
from hashlib import sha256
from pathlib import Path
import json
from netCDF4 import Dataset, chartostring

root = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
archive = root / 'MODL/KLBG/NE57/DAIO/2026081606'

def digest(path):
    h = sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def grib_stats(path):
    counts = Counter()
    with path.open('rb') as f:
        while head := f.read(16):
            if len(head) != 16 or head[:4] != b'GRIB' or head[7] != 2:
                raise ValueError(f'invalid GRIB2 header: {path}')
            data = f.read(int.from_bytes(head[8:16], 'big') - 16)
            if data[-4:] != b'7777':
                raise ValueError(f'invalid GRIB2 terminator: {path}')
            pos = 0
            ref = None
            while pos < len(data) - 4:
                n = int.from_bytes(data[pos:pos+4], 'big')
                sec = data[pos:pos+n]
                if n < 5 or pos+n > len(data)-4:
                    raise ValueError(f'invalid GRIB2 section: {path}')
                if sec[4] == 1:
                    ref = (int.from_bytes(sec[5:7], 'big'), sec[11], int.from_bytes(sec[12:14], 'big'), *sec[14:19])
                if sec[4] == 4:
                    template = int.from_bytes(sec[7:9], 'big')
                    raw = int.from_bytes(sec[18:22], 'big')
                    lead = -(raw & 0x7fffffff) if raw & 0x80000000 else raw
                    end = (int.from_bytes(sec[34:36], 'big'), *sec[36:41]) if template == 8 else None
                    counts[(ref, template, sec[17], lead, end)] += 1
                pos += n
            if pos != len(data)-4:
                raise ValueError(f'GRIB2 section alignment: {path}')
    return [{'reference': list(ref), 'product_template': template, 'time_unit_code': unit, 'forecast_lead': lead, 'interval_end': end, 'count': count} for (ref, template, unit, lead, end), count in counts.items()]

out = {'archive': str(archive), 'grib_reference_tuple': ['center_code', 'significance_code', 'year', 'month', 'day', 'hour', 'minute', 'second'], 'grib': {}, 'met_em': {}, 'config_sha256': {}}
for kind in ('pres', 'unis'):
    for h in (0, 3, 6):
        p = archive / f'kim_g128_ne57_{kind}_h{h:03}.2026081606.gb2'
        out['grib'][p.name] = {'size': p.stat().st_size, 'sha256': digest(p), 'section_metadata': grib_stats(p)}
for h in (6, 9, 12):
    p = archive / f'met_em.d01.2026-08-16_{h:02}:00:00.nc'
    with Dataset(p) as d:
        out['met_em'][p.name] = {'size': p.stat().st_size, 'sha256': digest(p), 'Times': chartostring(d['Times'][:]).tolist(), 'simulation_start_date': d.SIMULATION_START_DATE, 'title': d.TITLE, 'dimensions': {k: len(v) for k,v in d.dimensions.items()}, 'variables': list(d.variables)}
for s in ['SHEL/klbg_lc05_prep_kim.ksh', 'SHEL/klbg_lc05_prep_mgrd.ksh', 'SHEL/klbg_lc05_prep_tavg.ksh', 'SHEL/klbg_lc05_prep_usst.ksh', 'SHEL/klbg_lc05_prep_oml.ksh', 'SHEL/klbg_lc05_prep_ww3.ksh', 'SHEL/klbg_lc05_init_latb.ksh', 'DABA/namelist/namelist.wps_metgrid']:
    p = root / 'MODL/KLBG/NE57' / s
    out['config_sha256'][s] = digest(p)
print(json.dumps(out, indent=2))
