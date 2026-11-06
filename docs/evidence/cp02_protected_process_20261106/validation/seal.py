#!/usr/bin/env python3
"""Seal the completed, reviewed protected-process evidence without recursive hashes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_protected_process_20261106'
BASE = '8e8208672092c2f4169fe617bc3b4d9f379e69ae'
TOOLS = ('cp02_b1_failure_context', 'cp02_protected_process_cohorts',
         'cp02_protected_process_capture', 'cp02_protected_process_summary',
         'plot_cp02_protected_process', 'plot_cp02_protected_process_native')


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read(name: str, status: str | None = None) -> dict:
    path = BUNDLE / name
    require(path.is_file() and not path.is_symlink(), f'missing or unsafe receipt: {name}')
    result = json.loads(path.read_text())
    require(status is None or result.get('status') == status, f'unexpected status: {name}')
    return result


def verify() -> dict:
    clean = read('validation/clean_export.json', 'PASS')
    require(clean.get('passed') == 456 and clean.get('exit_code') == 0
            and clean.get('source_inputs_unchanged') is True,
            'expected immutable 456-test clean-export pass')
    guarded = clean.get('guarded_source_input_sha256', {})
    selected = {f'{directory}/{prefix}{name}.py'
                for name in TOOLS for directory, prefix in (('tools', ''), ('tests', 'test_'))}
    require(selected <= set(guarded), 'clean export does not bind all twelve source/test paths')
    for name, expected in guarded.items():
        require(sha(ROOT / name) == expected, f'tested source/input changed: {name}')
    reproduction = read('validation/reproduction.json', 'PASS')
    require(reproduction.get('byte_identical_artifact_count') == 26
            and reproduction.get('surface_recount', {}).get('rows') == 1500
            and reproduction.get('combined_gallery_verified') is True,
            'portable replay coverage differs')
    require(reproduction.get('reproducer_sha256') == sha(BUNDLE / 'validation/reproduce.py'),
            'reproduction helper changed after replay')
    reproduced = reproduction.get('artifacts', [])
    require(len(reproduced) == 26 and len({row['artifact'] for row in reproduced}) == 26,
            'reproduction artifact inventory differs')
    for row in reproduced:
        relative = Path(row['artifact'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe replay artifact path')
        path = ROOT / relative
        require(path.is_file() and not path.is_symlink()
                and path.stat().st_size == row['size_bytes'] and sha(path) == row['sha256'],
                f'replayed artifact changed: {relative}')
    surface = reproduction['surface_recount']
    surface_dir = BUNDLE / 'science/surface/validated'
    require(surface.get('byte_identical') is True, 'surface table replay was not byte-identical')
    require(surface.get('recounter_sha256') == sha(BUNDLE / 'science/surface/portable_recount_surface.py'),
            'portable surface recounter changed after replay')
    table = read('tables/receipt.json', 'PASS_INDEPENDENT_OLD_FIX_RECOUNT')
    require(table.get('generator_sha256') == sha(BUNDLE / 'tables/generate_tables.py'),
            'full score generator changed after replay')
    for key, name in (('packet_sha256', 'surface_reconciliation_packet.npz'),
                      ('packet_receipt_sha256', 'surface_reconciliation_packet_receipt.json'),
                      ('reference_csv_sha256', 'point_hourly_surface_components.csv')):
        require(surface.get(key) == sha(surface_dir / name), f'replayed surface input changed: {name}')
    prior = read('validation/prior_evidence_after_kg_audit.json', 'PASS')
    require(prior.get('artifact_count') == 225, 'prior225 audit incomplete')
    require(len(prior.get('artifacts', [])) == 225, 'prior225 artifact inventory incomplete')
    for row in prior['artifacts']:
        path = ROOT / row['verified_path']
        require(path.is_file() and not path.is_symlink()
                and path.stat().st_size == row['size_bytes'] and sha(path) == row['sha256'],
                f'preserved prior evidence changed: {row["verified_path"]}')

    package = read('native/compact/package_receipt.json', 'EXACT_SOURCE_CHANNEL_SUBSET_VERIFIED')
    require(package.get('channel_count') == 130 and package.get('channels_per_arm') == 65,
            'portable channel coverage differs from 130')
    require(package.get('total_channel_bytes') == 820732670, 'core-channel byte count differs')
    require(len(package.get('channels', [])) == 130, 'portable channel inventory incomplete')
    seen = set()
    for row in package['channels']:
        relative = Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts
                and row['path'] not in seen, 'unsafe or duplicate compact channel path')
        seen.add(row['path'])
        path = BUNDLE / 'native/compact' / relative
        require(path.is_file() and not path.is_symlink()
                and path.stat().st_size == row['size_bytes'] and sha(path) == row['sha256'],
                f'compact channel bytes differ: {relative}')
    codec = sha(ROOT / 'tools/cp02_protected_process_capture.py')
    for arm in ('OLD', 'FIX'):
        capture = read(f'native/compact/{arm}/capture_receipt.json', 'FULL_CAPTURE_STREAMS_VALIDATED')
        require(capture.get('arm') == arm, 'capture arm mismatch')
        # All current compact receipts must bind the reviewed final codec.
        require(capture.get('tool_sha256') == codec, f'{arm}: capture does not bind the current collector')
        require(package['source_capture_receipt_sha256'][arm]
                == sha(BUNDLE / f'native/compact/{arm}/capture_receipt.json'), 'capture/package binding differs')

    summary = read('native/analysis/summary/summary_receipt.json', 'CONTIGUOUS_PROCESS_COMPARISON_VALIDATED')
    require((summary.get('rows'), summary.get('nominal_rate_rows'), summary.get('group_profile_rows'))
            == (70200, 35100, 7020), 'summary table coverage differs')
    require(summary.get('collector_receipt_sha256') == package['source_capture_receipt_sha256'],
            'summary does not bind the final captures')
    for name, identity in summary['outputs'].items():
        path = BUNDLE / 'native/analysis/summary' / name
        require(path.stat().st_size == identity['size_bytes'] and sha(path) == identity['sha256'],
                f'summary output differs: {name}')
    report = read('review/terra_science_review.json', 'PASS_FINAL_REPORT_SCIENCE_REVIEW')
    require('docs/CP02_PROTECTED_PROCESS_20261106.md' in report.get('reviewed_artifacts', {}),
            'science review does not bind the paper')
    for name, expected in report['reviewed_artifacts'].items():
        require(sha(ROOT / name) == expected, f'science-reviewed artifact changed: {name}')
    read('kg/stage_review.json', 'GO')
    read('kg/publish_receipt.json', 'PUBLISHED_AND_READBACK_PASS')
    read('kg/postpublish_copy_receipt.json', 'PASS_ACTIVE_WORKTREE_AND_WIKI_READBACK')

    gallery = read('gallery_receipt.json', 'PASS_INLINE_AND_OFFLINE_GALLERY')
    archive = BUNDLE / gallery['archive']['path']
    require(sha(archive) == gallery['archive']['sha256'], 'gallery archive bytes differ')
    with zipfile.ZipFile(archive) as package_file:
        require(package_file.testzip() is None and set(package_file.namelist()) == set(gallery['members']),
                'gallery inventory or CRC differs')
        for name, identity in gallery['members'].items():
            require(sha(BUNDLE / name) == identity['sha256']
                    and hashlib.sha256(package_file.read(name)).hexdigest() == identity['sha256'],
                    f'gallery member bytes differ: {name}')
    return {'clean_export_tests': 456, 'portable_channel_count': 130,
            'summary_rows': 70200, 'portable_reproduction_artifacts': 26,
            'surface_recount_rows': 1500, 'prior_artifacts': 225,
            'figures': 4, 'candidate_adopted': False, 'retained_configuration': 'B1'}


def artifacts() -> list[Path]:
    paths = {ROOT / 'README.md', ROOT / 'docs/CURRENT_RESEARCH_STATUS.md',
             ROOT / 'docs/CP02_PROTECTED_PROCESS_20261106.md'}
    for tool in TOOLS:
        paths.add(ROOT / 'tools' / f'{tool}.py')
        paths.add(ROOT / 'tests' / f'test_{tool}.py')
    paths.update(path for path in BUNDLE.rglob('*') if path.is_file() or path.is_symlink())
    paths.update((ROOT / 'graphify-out' / '2026-11-06-protected-process').glob('*'))
    paths.update(ROOT / 'graphify-out' / name for name in ('graph.json', 'manifest.json', 'GRAPH_REPORT.md'))
    excluded = {BUNDLE / 'validation.json', BUNDLE / 'validation/final_index_review.json'}
    result = []
    for path in sorted(paths):
        if path in excluded or '__pycache__' in path.parts or path.suffix in ('.pyc', '.lock'):
            continue
        require(path.is_file() and not path.is_symlink(), f'unsafe artifact: {path}')
        require(path.stat().st_size < 100 * 1024**2, f'artifact exceeds 100 MiB: {path}')
        with path.open('rb') as stream:
            require(stream.read(4) != b'\x7fELF', f'executable binary must remain external: {path}')
        result.append(path)
    return result


def main() -> None:
    output = BUNDLE / 'validation.json'
    require(not output.exists() and not output.is_symlink(), 'preserve existing validation.json before regeneration')
    checks = verify()
    rows = [{'path': str(path.relative_to(ROOT)), 'size_bytes': path.stat().st_size,
             'sha256': sha(path)} for path in artifacts()]
    result = {'schema': 'cp02_protected_process_validation_v1',
              'status': 'PASS_COMPLETED_PROTECTED_PROCESS_BATCH', 'base_commit': BASE,
              'checks': checks, 'artifact_count': len(rows), 'artifacts': rows,
              'scope': 'Same-B1 OLD/FIX five-hour process diagnosis, not a newly improved forecast.',
              'exclusions': ['This manifest and final index review avoid recursive hashes.',
                             'Transient bytecode and locks; external raw streams, ELF and full history archives.'],
              'limits': ['No column/domain water or energy budget closure is claimed.',
                         'Between-call changes are not identified as pure transport.',
                         'No new candidate or forecast improvement is adopted; the fixed26 criteria remain.',
                         'One case and spatially dependent diagnostic groups do not establish independent forecast skill.']}
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(f'PASS: sealed {len(rows)} artifacts')


if __name__ == '__main__':
    main()
