#!/usr/bin/env python3
"""Stage approved bytes and record full metgrid runs; numerical checks are Fortran."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

from verify_qbal_metgrid_reader import LOOKUP_DATE, prepare, sha256, write_json

MET_NAME = f"met_em.d01.{LOOKUP_DATE}.nc"
MUTATIONS = {"time":"met_em exact time mismatch", "geometry":"XLAT_M value mismatch",
             "spacing":"met_em geometry attribute mismatch", "pressure-units":"PRES units mismatch"}
MUTATIONS.update({field:field + " value mismatch" for field in ("TT","UU","VV","QV","GHT","PRES")})


def execute(argv, directory, log):
    result = subprocess.run([str(item) for item in argv], cwd=directory,
                            capture_output=True, text=True, timeout=180)
    output = result.stdout + result.stderr
    (directory / log).write_text(output)
    return result, output


def stage(root, level, case, name, repo):
    directory = root / level / name
    directory.mkdir()
    (directory / "run.cwd").write_text(str(directory) + "\n")
    source = Path(case["path"])
    if sha256(source) != case["sha256"]:
        raise ValueError("approved WPS changed")
    shutil.copyfile(source, directory / f"LAPS:{LOOKUP_DATE}")
    shutil.copyfile(root / level / "geo_em.d01.nc", directory / "geo_em.d01.nc")
    shutil.copyfile(repo / "tests/qbal_metgrid.tbl", directory / "METGRID.TBL")
    (directory / "namelist.wps").write_text(f"""&share
 wrf_core='ARW', max_dom=1,
 start_date='{LOOKUP_DATE}', end_date='{LOOKUP_DATE}',
 interval_seconds=300,
 io_form_geogrid=2, debug_level=100,
/
&geogrid
 parent_id=1, parent_grid_ratio=1, i_parent_start=1, j_parent_start=1,
 e_we=5, e_sn=5, dx=10000., dy=10000.,
 map_proj='lambert', ref_lat=45., ref_lon=127.,
 truelat1=45., truelat2=45., stand_lon=127.,
/
&metgrid
 fg_name='LAPS', io_form_metgrid=2,
 opt_metgrid_tbl_path='./', opt_output_from_metgrid_path='./',
/
""")
    return directory


def run(root, level, repo):
    from netCDF4 import Dataset
    import numpy as np

    cases = [case for case in json.loads((root / "inputs.json").read_text())["cases"]
             if case["name"] in ("O0", "O2")]
    build = root / level
    if sorted(case['name'] for case in cases) != ['O0','O2']:
        raise ValueError('expected two unique base producer inputs')
    bound_files = [build / name for name in ('metgrid.exe','unpatched_metgrid.exe','verify_full.exe','geo_em.d01.nc')]
    bound_files.append(repo / 'tests/qbal_metgrid.tbl')
    binding = {str(path):sha256(path) for path in bound_files}
    write_json(build / 'execution_inputs.json',binding)
    results = []
    for case in cases:
        directory = stage(root, level, case, "producer-" + case["name"], repo)
        result, output = execute([build / "metgrid.exe"], directory, "metgrid.stdout.log")
        met = directory / MET_NAME
        if result.returncode != 0 or not met.is_file():
            raise RuntimeError(f"full metgrid failed: {directory}\n{output}")
        argv = [build / "verify_full.exe", directory / f"LAPS:{LOOKUP_DATE}",
                directory / "geo_em.d01.nc", met]
        checked, log = execute(argv, directory, "verify.log")
        if checked.returncode != 0 or "PASS_SCOPED" not in log:
            raise RuntimeError(f"Fortran output verification failed: {directory}\n{log}")
        if sha256(directory / f"LAPS:{LOOKUP_DATE}") != case["sha256"]:
            raise ValueError("full metgrid input changed")
        results.append({"name":directory.name,"expected_success":True,"matched":True,
                        "metgrid_returncode":result.returncode,"verify_returncode":checked.returncode,
                        "input_sha256":case["sha256"],"output":str(met),"metgrid_argv":[str(build / "metgrid.exe")],"verify_argv":list(map(str,argv))})

    directory = stage(root, level, cases[0], "unpatched-time", repo)
    result, output = execute([build / "unpatched_metgrid.exe"], directory, "metgrid.stdout.log")
    logfile = directory / "metgrid.log"
    if logfile.is_file():
        output += logfile.read_text()
    missing = "Couldn't open file LAPS:2023-05-18_03:33 for input."
    matched = (result.returncode == 0 and missing in output
               and "mandatory field" in output and not list(directory.glob("met_em*")))
    results.append({"name":"unpatched-time", "expected_success":False,"matched":matched,
                    "returncode":result.returncode,"expected_message":missing,"argv":[str(build / "unpatched_metgrid.exe")],
                    "requires_mandatory_field_error_and_no_output":True,"legacy_plain_stop_exit":0})
    if not matched:
        raise RuntimeError(f"unexpected unpatched full metgrid result\n{output}")

    normal = root / level / "producer-O0"
    for name, message in MUTATIONS.items():
        directory = root / level / ("reject-" + name)
        directory.mkdir()
        mutated = directory / MET_NAME
        shutil.copyfile(normal / MET_NAME, mutated)
        with Dataset(mutated, "r+") as data:
            if name == "time":
                data.variables["Times"][0,18] = np.bytes_("1")
            elif name == "pressure-units":
                data.variables['PRES'].units = 'hPa'
            elif name == "spacing":
                data.DX = np.float32(data.DX * 2)
            else:
                variable = data.variables["XLAT_M" if name == "geometry" else name]
                index = (0,) * variable.ndim
                variable[index] = variable[index] + np.float32(1)
        argv = [build / "verify_full.exe", normal / f"LAPS:{LOOKUP_DATE}",
                normal / "geo_em.d01.nc", mutated]
        result, output = execute(argv, directory, "verify.log")
        matched = result.returncode != 0 and "FAIL: " + message in output
        results.append({"name":directory.name,"expected_success":False,"matched":matched,
                        "returncode":result.returncode,"expected_message":"FAIL: " + message,"argv":list(map(str,argv))})
        if not matched:
            raise RuntimeError(f"wrong rejection: {name}\n{output}")
    for name, expected in binding.items():
        if sha256(Path(name)) != expected:
            raise ValueError('execution dependency changed: ' + name)
    for case in cases:
        directory = build / ('producer-' + case['name'])
        if sha256(directory / 'geo_em.d01.nc') != binding[str(build / 'geo_em.d01.nc')]:
            raise ValueError('staged geogrid changed')
        if sha256(directory / 'METGRID.TBL') != binding[str(repo / 'tests/qbal_metgrid.tbl')]:
            raise ValueError('staged table changed')
    write_json(build / "results.json",results)


def finish(root, repo):
    inputs = json.loads((root / "inputs.json").read_text())
    if sha256(Path(inputs["manifest"])) != inputs["manifest_sha256"]:
        raise ValueError("approval manifest changed")
    source = Path(inputs['manifest']).parent
    parent = json.loads(Path(inputs['manifest']).read_text())
    required_cases = {'O0','O2','O0-geometry','O2-geometry'}
    if len(inputs['cases'])!=4 or {case['name'] for case in inputs['cases']}!=required_cases:
        raise ValueError('incomplete prepared inputs')
    for case in inputs['cases']:
        name=case['name']
        if case['original']!=str(source / name / 'wps.out') or case['path']!=str(root / 'inputs' / name / f'LAPS:{LOOKUP_DATE}'):
            raise ValueError('input case identity mismatch')
        if case['sha256']!=parent['artifacts_sha256'][f'{name}/wps.out']:
            raise ValueError('producer artifact identity mismatch')
        for key in ('original','path'):
            if sha256(Path(case[key]))!=case['sha256']:
                raise ValueError('approved input changed')
    results = {level:json.loads((root / level / "results.json").read_text()) for level in ("O0","O2")}
    expected_names = {'producer-O0','producer-O2','unpatched-time'} | {'reject-' + name for name in MUTATIONS}
    for level, group in results.items():
        if len(group)!=len(expected_names) or {item['name'] for item in group}!=expected_names:
            raise ValueError('incomplete full metgrid results')
        build=root / level
        binding=json.loads((build / 'execution_inputs.json').read_text())
        expected_keys={str(build / name) for name in ('metgrid.exe','unpatched_metgrid.exe','verify_full.exe','geo_em.d01.nc')}
        expected_keys.add(str(repo / 'tests/qbal_metgrid.tbl'))
        if set(binding)!=expected_keys:
            raise ValueError('incomplete execution bindings')
        for item in group:
            positive = item['name'].startswith('producer-')
            if not item['matched'] or item['expected_success']!=positive:
                raise ValueError('unresolved full metgrid test')
            if positive:
                if item['metgrid_returncode']!=0 or item['verify_returncode']!=0:
                    raise ValueError('unsuccessful positive execution')
                directory=build / item['name']
                expected_argv=[str(build / 'verify_full.exe'),str(directory / f'LAPS:{LOOKUP_DATE}'),
                               str(directory / 'geo_em.d01.nc'),str(directory / MET_NAME)]
                if item['metgrid_argv']!=[str(build / 'metgrid.exe')] or item['verify_argv']!=expected_argv or item['output']!=str(directory / MET_NAME):
                    raise ValueError('positive execution identity mismatch')
            elif item['name']=='unpatched-time':
                if item['returncode']!=0 or not item['requires_mandatory_field_error_and_no_output'] or item['argv']!=[str(build / 'unpatched_metgrid.exe')]:
                    raise ValueError('unmatched legacy STOP control')
            else:
                normal=build / 'producer-O0'
                expected_argv=[str(build / 'verify_full.exe'),str(normal / f'LAPS:{LOOKUP_DATE}'),
                               str(normal / 'geo_em.d01.nc'),str(build / item['name'] / MET_NAME)]
                if item['returncode']==0 or item['expected_message']!='FAIL: '+MUTATIONS[item['name'][7:]] or item['argv']!=expected_argv:
                    raise ValueError('unsuccessful negative execution')
        time_log=(root / level / 'time-unit.log').read_text()
        if 'MATRIX_PASS cases=24' not in time_log or 'METGRID_TIME_TEST_PASS' not in time_log:
            raise ValueError('missing formatter test evidence')
        for name, expected in json.loads((root / level / 'execution_inputs.json').read_text()).items():
            if sha256(Path(name))!=expected:
                raise ValueError('changed execution dependency')
    write_json(root / "manifest.json",{
        "status":"PASS_SCOPED", "scope":"single-time full serial metgrid on a synthetic inner Lambert C-grid",
        "valid_time":LOOKUP_DATE,"interval_seconds":300,"input":inputs,"results":results,
        "artifacts_sha256":{str(path.relative_to(root)):sha256(path) for path in sorted(root.rglob('*'))
                            if path.is_file() and path.name!='manifest.json'},
        "limitations":["Only base geometry and this five-level synthetic case are consumed by full metgrid.",
                       "A synthetic geogrid and a minimal nearest-neighbor table are used; not operational remapping.",
                       "Single analysis time at a declared 300-second cadence; not a multi-time operational run.",
                       "No real.exe, native omega/W, startup, physical budgets or forecasts."]})
    print("PASS_SCOPED: full metgrid O0/O2")


if __name__ == '__main__':
    command,*args=sys.argv[1:]
    if command=='prepare':
        prepare(Path(args[0]).resolve(),args[1],Path(args[2]).resolve())
    elif command=='run':
        run(Path(args[0]).resolve(),args[1],Path(args[2]).resolve())
    elif command=='finish':
        finish(*(Path(arg).resolve() for arg in args))
    else:
        raise SystemExit('unknown command')
