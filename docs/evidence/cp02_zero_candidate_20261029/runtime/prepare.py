"""Copy the pinned historical inputs into fresh scratch, never modifying originals."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
PRIOR = ROOT / 'docs/evidence/cp02_kdm6_controls_20261029'

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=EVIDENCE / 'prepare.json')
    output = parser.parse_args().output
    if output.exists():
        raise RuntimeError('Preparation receipt already exists')
    manifest_path = PRIOR / 'inputs/copy_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    scratch = Path(tempfile.mkdtemp(prefix='cp02-zero-candidate-20261029-', dir='/var/tmp'))
    receipt = {'scratch': str(scratch), 'copy_manifest_sha256': digest(manifest_path), 'arms': {}}
    binary = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_host_unit_contract_x3bcr8ui/host/main/wrf.exe')
    expected = 'de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168'
    assert digest(binary) == expected
    shutil.copy2(binary, scratch / 'wrf.exe')
    assert digest(scratch / 'wrf.exe') == expected
    receipt['binary'] = {'source': str(binary), 'sha256': expected, 'size_bytes': binary.stat().st_size}
    shutil.copy2(PRIOR / 'selection.json', scratch / 'selection.json')
    receipt['selection_sha256'] = digest(scratch / 'selection.json')
    for arm, info in manifest['arms'].items():
        run = scratch / arm / 'run'
        run.mkdir(parents=True)
        (scratch / arm / 'capture').mkdir()
        files = []
        for item in info['copy_files']:
            source = Path(item['source_path'])
            assert source.stat().st_size == item['size_bytes'] and digest(source) == item['sha256'], str(source)
            target = run / item['destination_name']
            shutil.copy2(source, target)
            assert digest(target) == item['sha256']
            files.append(dict(item, destination_path=str(target)))
        receipt['arms'][arm] = {'files': files, 'file_count': len(files)}
    if output.exists():
        raise RuntimeError('Do not overwrite prior preparation receipt')
    output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(scratch)

if __name__ == '__main__':
    main()
