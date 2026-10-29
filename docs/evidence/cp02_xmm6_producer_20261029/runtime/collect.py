"""Archive completed diagnostic captures and rehash historical/fresh inputs."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIOR = ROOT / 'docs/evidence/cp02_kdm6_controls_20261029'

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def pin(path):
    return {'path': str(path), 'sha256': digest(path), 'size_bytes': path.stat().st_size}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('arm', choices=['OFF', 'HYDRO', 'LIQUID'])
    parser.add_argument('--prepare', type=Path, default=HERE / 'prepare.json')
    args = parser.parse_args()
    arm = args.arm
    preparation = args.prepare
    prep = json.loads(preparation.read_text())
    scratch = Path(prep['scratch'])
    stage = scratch / arm
    raw = stage / 'capture'
    context = json.loads((stage / 'context.json').read_text())
    files = sorted(raw.glob('raw_*_rank*_pid*.json'))
    records = [json.loads(path.read_text()) for path in files]
    assert len(records) == 8 and {str(r['rank']) for r in records} == {str(n) for n in range(8)}
    assert not list(raw.glob('failed_*.json'))
    assert all(r['status'] == 'all_ranks_settled' for r in records)
    assert all(r['stage_context_sha256'] == digest(stage / 'context.json') for r in records)
    assert all(r['helper_sha256'] == digest(stage / 'capture_preclamp.gdb') for r in records)
    for rank, label in [('1', 'P05_00'), ('3', 'P01_00')]:
        record = next(r for r in records if r['rank'] == rank)
        events = [e for e in record['preclamp_events'] if e['target'] == label]
        assert [(e['role'], e['pc_hex']) for e in events] == [('before_sum', '0x25f4e24'), ('before_clamp', '0x25f4e50'), ('before_store', '0x25f4e58'), ('after_store', '0x25f4e5e')], (rank, label, events)
        assert events[-1]['values']['qrs']['raw_hex'] == events[-1]['scalar_registers']['xmm9']['raw_hex']
    launcher_exit = int((stage / 'launcher.exit').read_text())
    assert launcher_exit == 255, launcher_exit
    checks = []
    for item in prep['arms'][arm]['files']:
        for path in (Path(item['source_path']), Path(item['destination_path'])):
            assert path.stat().st_size == item['size_bytes'] and digest(path) == item['sha256'], str(path)
        checks.append({'name': item['destination_name'], 'sha256': item['sha256'], 'source_and_copy_unchanged': True})
    assert digest(scratch / 'wrf.exe') == prep['binary']['sha256']
    assert digest(Path(prep['binary']['source'])) == prep['binary']['sha256']
    old = json.loads((PRIOR / 'captures' / arm / 'receipt.json').read_text())
    history = stage / 'run/wrfout_d01_2026-08-16_12:00:00'
    assert digest(history) == old['initial_history']['sha256']
    target = HERE.parent / 'captures' / arm
    if target.exists():
        raise RuntimeError('Archive destination exists; preserve prior evidence')
    target.mkdir(parents=True)
    captures = []
    runtime_paths = set()
    for path, record in zip(files, records):
        payload = path.read_bytes()
        output = target / (path.name + '.gz')
        output.write_bytes(gzip.compress(payload, mtime=0))
        captures.append(dict(pin(output), rank=str(record['rank']), pid=record['pid'], uncompressed_sha256=hashlib.sha256(payload).hexdigest(), uncompressed_size_bytes=len(payload)))
        maps = Path(record['proc_maps_file'])
        assert digest(maps) == record['proc_maps_sha256']
        for line in maps.read_text().splitlines():
            fields = line.split(maxsplit=5)
            if len(fields) == 6 and fields[5].startswith('/'):
                runtime_paths.add(fields[5])
    for path in sorted(raw.glob('*.txt')):
        shutil.copy2(path, target / path.name)
    for name in ('context.json', 'capture_preclamp.gdb', 'launch.sh', 'rank_wrapper.sh', 'launcher.txt', 'launcher.exit'):
        shutil.copy2(stage / name, target / name)
    runtime = {path: pin(Path(path)) for path in sorted(runtime_paths) if Path(path).is_file()}
    unavailable = sorted(path for path in runtime_paths if not Path(path).is_file())
    receipt = {'status': 'FIRST_INNER_CAPTURED_INTENTIONAL_STOP', 'forecast_status': 'NOT_COMPLETED',
               'arm': arm, 'launcher_exit': launcher_exit, 'ranks': 8, 'omp_threads': 1,
               'scope': 'First public KDM6 call with pre-sum, pre-clamp, and direct store observations; intentional stop, no forecast completion or process-budget claim.',
               'prepare_receipt_sha256': digest(preparation), 'context': context,
               'context_sha256': digest(stage / 'context.json'),
               'helper_sha256': digest(stage / 'capture_preclamp.gdb'),
               'binary': dict(pin(scratch / 'wrf.exe'), build_id=context['build_id']), 'input_manifest_sha256': prep['copy_manifest_sha256'], 'selection_sha256': digest(scratch / 'selection.json'),
               'input_files_unchanged': len(checks), 'original_input_files_unchanged': len(checks),
               'input_checks': checks, 'initial_history': dict(pin(history), archived_sha256=old['initial_history']['sha256'], byte_identical=True),
               'runtime_mapped_files': runtime, 'unavailable_mappings': unavailable, 'captures': captures}
    (target / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'arm': arm, 'ranks': len(records), 'events': {r['rank']: len(r['write_events']) for r in records}, 'archive': str(target)}))

if __name__ == '__main__':
    main()
