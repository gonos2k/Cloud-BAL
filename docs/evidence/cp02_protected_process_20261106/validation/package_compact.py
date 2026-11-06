#!/usr/bin/env python3
"""Retain exact source NPZs needed for portable scientific summary replay."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import uuid

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_protected_process_20261106'
CORE = {f'state_{stage}_{field}' for stage in ('entry', 'return') for field in ('QV', 'QC', 'QR', 'TK')}
CORE |= {f'phase8_minus_phase6_{field}' for field in ('QV', 'QC', 'QR', 'TK')}
CORE |= {f'phase12_minus_phase11_{field}' for field in ('QV', 'QC', 'TK')}
CORE |= {'sedimentation_net_QR', 'phase05_prevp', 'phase05_praut', 'phase05_pracw', 'phase06_dtcld'}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(source, output):
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    stage = output.with_name('.' + output.name + '.staging-' + uuid.uuid4().hex)
    stage.mkdir(parents=True)
    records, capture_receipts = [], {}
    try:
        for arm in ('OLD', 'FIX'):
            source_arm = source / arm
            receipt_path = source_arm / 'capture_receipt.json'
            receipt = json.loads(receipt_path.read_text())
            if receipt.get('status') != 'FULL_CAPTURE_STREAMS_VALIDATED' or receipt.get('arm') != arm:
                raise ValueError('full source capture receipt is required')
            expected = {(name, hour) for name in CORE for hour in (1, 2, 5)}
            expected |= {('surface_rain_cumulative', hour) for hour in range(1, 6)}
            chosen = [row for row in receipt['outputs']
                      if (row.get('channel'), (row['actual_start'] + 179) // 180) in expected]
            keys = [(row['channel'], (row['actual_start'] + 179) // 180) for row in chosen]
            if len(keys) != 65 or len(set(keys)) != len(keys) or set(keys) != expected:
                raise ValueError('required portable channel selection differs from 65 files per arm')
            target_arm = stage / arm
            target_arm.mkdir()
            shutil.copyfile(receipt_path, target_arm / 'capture_receipt.json')
            capture_receipts[arm] = sha(receipt_path)
            for row in chosen:
                relative = Path(row['path'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('unsafe source channel path')
                original = source_arm / relative
                if original.is_symlink() or original.stat().st_size != row['size_bytes'] or sha(original) != row['sha256']:
                    raise ValueError(f'source channel identity differs: {original}')
                if row['size_bytes'] >= 100 * 1024 * 1024:
                    raise ValueError('portable channel exceeds repository file-size ceiling')
                destination = target_arm / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, destination)
                if sha(destination) != row['sha256']:
                    raise ValueError('portable channel copy differs')
                records.append({**row, 'path': f'{arm}/{relative.as_posix()}'})
        result = {'status': 'EXACT_SOURCE_CHANNEL_SUBSET_VERIFIED', 'source': str(source.resolve()),
                  'channels_per_arm': 65, 'channel_count': len(records),
                  'source_capture_receipt_sha256': capture_receipts,
                  'total_channel_bytes': sum(row['size_bytes'] for row in records), 'channels': records,
                  'scope': 'Exact original NPZ files, including native and point values; no numerical rewriting.',
                  'limits': ['Only channels required for fixed-level summary replay and surface endpoints are copied.',
                             'The full binary-stream replay and complete WRF history comparisons require the external raw archive.',
                             'Verbatim capture receipts also list unused outputs that remain in the external capture archive.']}
        (stage / 'package_receipt.json').write_text(json.dumps(result, indent=2) + '\n')
        stage.rename(output)
        return result
    except BaseException:
        shutil.rmtree(stage)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=BUNDLE / 'native/compact')
    args = parser.parse_args()
    result = package(args.source, args.output)
    print(json.dumps({key: result[key] for key in ('status', 'channel_count', 'total_channel_bytes')}))
