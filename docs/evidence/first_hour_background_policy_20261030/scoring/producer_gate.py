"""Fail-closed verification of the sealed producer pair (no model execution)."""
import hashlib
import json
from pathlib import Path

ROOT=Path('/var/tmp/firsthour-runtime-plan-20261030/producer_pair')
EXECUTABLE='86f0b26bba6ca27a9b09d16617ab291bb86fdd46dc4c677697a2213fa00cba6d'
CHECKER='17ee6d5e23925e34b9fdc881d3e1c81a27ef60f832cb4702b8dd0247a0825abd'
BUILD='6888d79adb8b684c3883cbbcac937ee76cc304e51fe42848a34013630a8b75bd'
NATIVE_AUDIT='201790f68f37f38c4e2df8dd967bf1c6e85766a30c22578b715305867bb1dfe9'
WPS_REPLAY='b0ce622b15323297fb7634c7858617c8de302617e5338ceb92d58dbd73bff1e7'
SOURCE={'src/common/cloud_bal_column_physics.f90':'0c2cdbf4379814a2fa720ad387591c9396c9a959eb0cf383132bda910bd66ecf',
        'src/common/cloud_bal_pressure_analysis.f90':'3959566091c36ea59f1dafa5eea04ea3125c7989f8c1f9f49fd9ab0b91d81807',
        'src/common/cloud_bal_real_netcdf.f90':'4c73b8cabce3fd8c0a6af235f54733ea7cc339455aabf0d677062534bfa6336b',
        'src/lapsprep/lapsprep.f90':'5191fcf222485a7db0ea5784a93d6774a92e46ef99e4dce8a940a0e6b1646eaf'}
MODES={'HYDRO':{'producer':'612a53c1fd14331031d67764720fa9602ff82e830c95d11f7f1545d765a5f461',
                'native':'d9608456e6adf219f05697058d05998326a3fd64d4b488291078cf4c8df900ab',
                'wps':'d7d8adfd3589cce46a4cee82b0f125a31e8232b3102d271959bcdefeed4dae0e',
                'input':'7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126'},
       'HYDRO_BACKGROUND_PRECIP':{'producer':'1e419ad83a3fbaa28f56d152a8d6b76235abd41279fbf5b2197c6ade83e5f8eb',
                'native':'98ccbd08cd355f32c2d5b09a24b1a76af92c51911c5f328948d52ae057fc4577',
                'wps':'ab0406fc71ec7c62cf63d7240bbfc36ee133902639b538472f52fedb5d720fb6',
                'input':'9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'}}


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def pinned(path,sha,records):
    if digest(path)!=sha:raise ValueError(f'identity mismatch: {path}')
    records[str(path)]=sha


def checked_json(path,sha,records):
    pinned(path,sha,records)
    return json.loads(path.read_text())


def validate():
    records={};build=checked_json(ROOT/'build_receipt.json',BUILD,records)
    if (build.get('status')!='BUILD_AND_LINK_PASS_NOT_TRACED' or build.get('executable_sha256')!=EXECUTABLE
        or build.get('checker_sha256')!=CHECKER):raise ValueError('producer build receipt invalid')
    pinned(Path(build['executable']),EXECUTABLE,records);pinned(Path(build['checker']),CHECKER,records)
    for name,sha in SOURCE.items():pinned(ROOT/'export'/name,sha,records)
    for name,sha in build['build_files'].items():pinned(Path(build['build_dir'])/name,sha,records)
    audit=checked_json(ROOT/'independent_native_shadow_audit.json',NATIVE_AUDIT,records)
    replay=checked_json(ROOT/'wps_hydrometeor_replay.json',WPS_REPLAY,records)
    if (audit.get('status')!='PASS_SCOPED' or audit.get('baseline_bitwise_matches_historical') is not True
        or audit['checker']['status']!='PASS_SCOPED_BACKGROUND_PRECIPITATION'
        or replay.get('status')!='PASS_WPS_HYDROMETEOR_REPLAY'):raise ValueError('scoped producer audit invalid')
    prep=json.loads((ROOT/'input_preparation.json').read_text());input_before=None
    if prep.get('input_count')!=114 or prep.get('source_unchanged') is not True or prep['source_before']!=prep['source_after']:raise ValueError('producer inputs invalid')
    for mode,expected in MODES.items():
        rd=ROOT/('run_'+mode);nd=ROOT/('native_'+mode)
        pr=checked_json(rd/'receipt.json',expected['producer'],records);nr=checked_json(nd/'receipt.json',expected['native'],records)
        if (pr.get('mode')!=mode or pr.get('exit')!=0 or pr.get('input_count')!=114
            or pr.get('executable_sha256')!=EXECUTABLE or pr.get('staged_unchanged') is not True or pr.get('source_unchanged') is not True
            or pr.get('input_hashes_before')!=pr.get('input_hashes_after') or pr.get('input_hashes_before')!=prep['source_before'] or set(pr.get('build_manifest_postchecks',{}))!={'inputs.sha256','runtime.sha256','executable.sha256'}
            or not all(pr['build_manifest_postchecks'].values()) or pr['output_sha256']['output.wps']!=expected['wps']):raise ValueError(f'{mode}: producer receipt invalid')
        if input_before is None:input_before=pr['input_hashes_before']
        elif input_before!=pr['input_hashes_before']:raise ValueError('producer input copies differ')
        for filename,sha in pr['input_hashes_before'].items():
            path=Path(filename)
            if path.is_absolute() or '..' in path.parts:raise ValueError('unsafe input path')
            pinned(rd/'input'/path,sha,records)
        for filename,sha in pr['output_sha256'].items():pinned(rd/filename,sha,records)
        if (nr.get('mode')!=mode or nr['metgrid']['exit']!=0 or nr['real']['exit']!=0
            or any(nr.get(k) is not True for k in ('metgrid_inputs_unchanged','real_inputs_unchanged','source_unchanged'))
            or nr['source_before']!=nr['source_after'] or nr['producer_receipt_sha256']!=expected['producer']
            or nr['producer_wps_sha256']!=expected['wps'] or nr['wrfinput_sha256']!=expected['input']):raise ValueError(f'{mode}: native receipt invalid')
        pinned(nd/'real/wrfinput_d01',expected['input'],records)
    return records
