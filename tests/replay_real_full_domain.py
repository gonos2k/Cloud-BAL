#!/usr/bin/env python3
"""Stage existing real-data assets and execute metgrid/real; never fabricate fields."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

MANIFEST_SHA = '2e6fc227f588eac48ebde0976f2a70d5e36157154bcf5b7177c9f969a861e831'
MET = 'met_em.d01.2026-08-16_13:00:00.nc'
MET_SHA = 'bdd5484c916f7b5ec7281b1a2ff41340e33936e87fce059d70052a3d40b1c885'
WRF_SHA = 'f0ccee31f6f7214c9d7b5ccf19e0ae55d9fe43751e0fcffbcaedfc6080a052e1'
BASE = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee')
MPI = BASE / 'local/mpi/2021.18/bin/mpirun'
METGRID = BASE / 'KLAPS50/MODL/KLFS/NE57/EXET/klfs_lc05_prep_mgrd.e'
REAL = BASE / 'KIM-meso/KIM_RDPS_MODL_V2026.2/main/real.exe'
TABLE = BASE / 'KLAPS50/MODL/KLFS/NE57/DABA/METGRID.TBL.ARW.OML.KWW'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check(inputs):
    for name, expected in inputs.items():
        if digest(name) != expected:
            raise ValueError(f'input hash mismatch: {name}')


def execute(argv, cwd, name):
    with (cwd / f'{name}.stdout.log').open('w') as log:
        result = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=log,
                                stderr=subprocess.STDOUT, timeout=1800)
    if result.returncode:
        raise RuntimeError(f'{name} failed: {result.returncode}; see {cwd}')
    return dict(argv=list(map(str, argv)), cwd=str(cwd), returncode=result.returncode)


def main():
    stage, run, repo = map(Path, sys.argv[1:])
    manifest = stage / 'input_manifest.sha256'
    if digest(manifest) != MANIFEST_SHA:
        raise ValueError('unrecognized prepared input manifest')
    inputs = {name:checksum for checksum, name in
              (line.split(None, 1) for line in manifest.read_text().splitlines())}
    inputs[str(TABLE)] = '44f1a43af35441957d0bef3a6220831aad1cf56ebc765d64d08e20f439a63b44'
    provenance = {
        str(BASE / 'KLAPS50/Cloud-BAL/scratch/actual_thermo_root_run.SuqsSJ/lapsprep.log'):
            'a2c948de8c4c833738551d47f7b9eb54cd21d20c433a49e011e63597bba7a246',
        str(BASE / 'KLAPS50/Cloud-BAL/scratch/cp01_exact_replay_review._eta4b0x/actual_validation.json'):
            'd392c67005a39932733d6d6181da1226f309359d7df55a6716d65bda602ea3fe'}
    check(provenance)
    check(inputs)
    reference = {str(stage / MET):MET_SHA, str(stage / 'real/wrfinput_d01'):WRF_SHA}
    check(reference)
    run.mkdir(parents=True, exist_ok=False)
    native = run / 'real'
    native.mkdir()
    for original, target in ((stage, run), (stage / 'real', native)):
        for link in original.iterdir():
            if not link.is_symlink() or link.name == MET:
                continue
            source = link.resolve(strict=True)
            if str(source) not in inputs:
                raise ValueError(f'unbound input link: {link}')
            (target / link.name).symlink_to(source)
    # The only namelist change is relocating the immutable table to this stage.
    wps = (stage / 'namelist.wps').read_text()
    old = "opt_metgrid_tbl_path = '../../../MODL/KLFS/NE57/DABA'"
    if wps.count(old) != 1:
        raise ValueError('unexpected prepared table path')
    (run / 'namelist.wps').write_text(wps.replace(old, "opt_metgrid_tbl_path = './'"))
    (run / 'METGRID.TBL').symlink_to(TABLE)
    shutil.copyfile(stage / 'real/namelist.input', native / 'namelist.input')
    (native / MET).symlink_to(run / MET)
    staged = {str(path):digest(path) for folder in (run,native)
              for path in folder.iterdir() if path.is_file()}
    # This link does not exist until metgrid finishes and is deliberately excluded.
    sources = {str(repo / 'tests' / name):digest(repo / 'tests' / name) for name in
               ('run_real_full_domain.sh','replay_real_full_domain.py','verify_real_full_domain.f90','intel_toolchain.sh')}
    (run / 'inputs.json').write_text(json.dumps(dict(original=inputs,staged=staged,
                                                   reference=reference,sources=sources,analysis_provenance=provenance),indent=2)+'\n')
    launches = []
    for binary, directory, name in ((METGRID,run,'metgrid'), (REAL,native,'real')):
        check(inputs); check(staged); check(sources)
        launches.append(execute([MPI,'-n','1',binary], directory, name))
        output = run / MET if name == 'metgrid' else native / 'wrfinput_d01'
        if not output.is_file():
            raise RuntimeError(f'{name} returned without output')
    check(inputs); check(staged); check(sources); check(reference); check(provenance)
    outputs = {str(run / MET):digest(run / MET),
               str(native / 'wrfinput_d01'):digest(native / 'wrfinput_d01')}
    replay_equal = list(outputs.values()) == [MET_SHA,WRF_SHA]
    receipt = dict(status='PASS_SCOPED' if replay_equal else 'REVIEW_REQUIRED',
        scope='full-domain real-data metgrid and real replay; not native consumed or physics validation',
        valid_time='2026-08-16_13:00:00',mass_shape=[234,282],metgrid_levels=21,native_levels=39,
        synthetic_inputs=False,subdomain=False,prepared_manifest_sha256=MANIFEST_SHA,
        inputs_unchanged=True,effective_input_count=len(inputs),analysis_provenance_sha256=provenance,
        selected_metgrid_table=dict(path=str(TABLE),sha256=inputs[str(TABLE)]),
        analysis_recomputed=False,balance_enabled=False,omega_increment_applied=False,
        prebuilt_executables=True,launches=launches,
        outputs_sha256=outputs,reference_byte_identity=replay_equal,
        artifacts_sha256={str(path):digest(path) for path in run.rglob('*')
                          if path.is_file() and not path.is_symlink()})
    (run / 'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if not replay_equal:
        raise RuntimeError('output differs from prepared reference; inspect full-field comparison')
    print('PASS_SCOPED: full real-data domain replay; native consumption remains open')


if __name__ == '__main__':
    main()
