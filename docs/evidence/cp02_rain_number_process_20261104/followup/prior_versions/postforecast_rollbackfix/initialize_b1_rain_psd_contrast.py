#!/usr/bin/env python3
"""Prepare the single declared B1 mass-weighted rain-diameter contrast."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import initialize_b1_rain_psd_prior as prior

POLICY = Path(__file__).resolve().parents[1] / 'docs/evidence/cp02_rain_number_process_20261104/followup/policy.json'
POLICY_SHA256 = 'c9afca77f42c0e3bba6d7f421f1e612a82ddd8912a722414d892918d4773ad7a'
LAMBDA = 5000.0 / 0.65


def prepare(input_path: Path, entry_path: Path, entry_sha256: str, output_path: Path) -> tuple[dict, tuple[int, int]]:
    if prior.file_sha256(POLICY) != POLICY_SHA256:
        raise prior.PriorError('CONTRAST_POLICY_HASH_MISMATCH')
    if os.path.lexists(output_path):
        raise prior.PriorError('OUTPUT_ALREADY_EXISTS')
    fields, attrs = prior._read_input(input_path)
    entry = prior._read_entry_npz(entry_path, entry_sha256)
    candidate, diagnostics = prior.initialize_qnrain(fields['QRAIN'], fields['QNRAIN'],
                                                      entry['DEN_ENTRY'], entry['CALLED'],
                                                      lambda_center=LAMBDA)
    if diagnostics['candidate_cells'] != 200182:
        raise prior.PriorError('ELIGIBLE_CELL_COUNT_MISMATCH')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f'.{output_path.name}.', suffix='.tmp', dir=output_path.parent)
    os.close(fd)
    temporary = Path(name)
    output_identity = None
    try:
        shutil.copy2(input_path, temporary)
        with prior.Dataset(temporary, 'r+') as dataset:
            variable = dataset.variables['QNRAIN']
            variable.set_auto_maskandscale(False)
            variable[:] = candidate
        prior._verify_copy(input_path, temporary, candidate)
        stat = temporary.stat()
        output_identity = (stat.st_dev, stat.st_ino)
        os.link(temporary, output_path)
        diagnostics.update({
            'schema': 'b1_rain_dm065_initialization_v1', 'status': 'PREPARED_CANDIDATE_NOT_RUN',
            'candidate': 'B1_RAIN_NUMBER_DM065', 'policy_path': str(POLICY.resolve()),
            'policy_sha256': POLICY_SHA256, 'initializer_sha256': prior.file_sha256(Path(__file__)),
            'shared_initializer_sha256': prior.file_sha256(Path(prior.__file__)),
            'input_path': str(input_path.resolve()), 'input_sha256': prior.file_sha256(input_path),
            'baseline_density_capture_path': str(entry_path.resolve()),
            'entry_capture_sha256': prior.file_sha256(entry_path),
            'output_path': str(output_path.resolve()), 'output_sha256': prior.file_sha256(output_path),
            'target_field': 'QNRAIN', 'units': attrs['qnrain'].get('units', ''),
            'unchanged_fields_verified': 'all variables except QNRAIN, including QRAIN/QVAPOR/T, all metadata and all global attributes',
            'prior_status': 'DECLARED_RESEARCH_PSD_CONTRAST_NOT_OBSERVED_CALIBRATION',
        })
        return diagnostics, output_identity
    except BaseException:
        if output_identity is not None:
            try:
                stat = output_path.lstat()
                if (stat.st_dev, stat.st_ino) == output_identity:
                    output_path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        temporary.unlink(missing_ok=True)



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--baseline-density-capture', required=True, type=Path)
    parser.add_argument('--baseline-density-capture-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    receipt_identity = output_identity = None
    try:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open('x', encoding='utf-8') as stream:
            stat = os.fstat(stream.fileno())
            receipt_identity = (stat.st_dev, stat.st_ino)
            receipt, output_identity = prepare(args.input, args.baseline_density_capture,
                                               args.baseline_density_capture_sha256, args.output)
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        for path, identity in ((args.output, output_identity), (args.receipt, receipt_identity)):
            if identity is not None:
                try:
                    stat = path.lstat()
                    if (stat.st_dev, stat.st_ino) == identity:
                        path.unlink()
                except FileNotFoundError:
                    pass
        print(f'B1_RAIN_DM065_REJECTED:{error}', file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
