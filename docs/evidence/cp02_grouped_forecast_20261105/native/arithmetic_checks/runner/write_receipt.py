#!/usr/bin/env python3
"""Bind arithmetic inputs, pinned Intel builds, outputs, and validation status."""
from __future__ import annotations

import hashlib
import json
import subprocess
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(sys.argv[1]).resolve()
STATUSES = [int(value) for value in sys.argv[2:7]]
BUNDLE = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[6]
PROFILE = REPO / 'tests/intel_toolchain.sh'
SETVARS = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh')
IFX = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx')
PINNED_LIBRARIES = [
    Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libimf.so'),
    Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libintlc.so.5'),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record_file(path: Path) -> dict:
    if not path.is_file():
        return {'path': str(path), 'exists': False}
    return {'path': str(path), 'exists': True, 'bytes': path.stat().st_size, 'sha256': sha256(path)}


def parse_key_values(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        key, sep, value = line.partition('=')
        if sep:
            result[key] = value
    return result


def runtime_libraries(executable: Path, label: str) -> dict:
    proc = subprocess.run(['ldd', str(executable)], text=True, capture_output=True)
    output_path = BUNDLE / 'logs' / f'ldd_{label}.txt'
    output_path.write_text(proc.stdout + proc.stderr, encoding='utf-8')
    paths = set()
    for line in (proc.stdout + proc.stderr).splitlines():
        match = re.search(r'=>\s+(/[^\s]+)', line)
        if match:
            path = Path(match.group(1))
            if path.is_file():
                paths.add(path.resolve())
        elif line.lstrip().startswith('/'):
            path = Path(line.strip().split()[0])
            if path.is_file():
                paths.add(path.resolve())
    return {
        'ldd_status': proc.returncode,
        'ldd_output': record_file(output_path),
        'resolved_libraries': [record_file(path) for path in sorted(paths)],
    }


provenance = json.loads((BUNDLE / 'inputs/input_provenance.json').read_text(encoding='utf-8'))
toolchain = parse_key_values(RUN / 'toolchain.txt')
source_head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
status_names = ('o0_compile', 'o2_compile', 'o0_run', 'o2_run', 'validate')
status_map = dict(zip(status_names, STATUSES))
summary_path = BUNDLE / 'results/arithmetic_summary.json'
summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.is_file() else None
executables = {
    'O0': RUN / 'rounding_check_o0',
    'O2': RUN / 'rounding_check_o2',
}
libs = {label: runtime_libraries(path, label) for label, path in executables.items() if path.is_file()}
all_pass = all(code == 0 for code in STATUSES) and summary is not None and summary.get('status') == 'PASS'
receipt = {
    'schema': 'cp02_grouped_forecast_arithmetic_check_v1',
    'status': 'PASS' if all_pass else 'FAIL',
    'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'REAL32 unit comparison of source-order old and grouped four-term numerator only',
    'source_expression': provenance['source_expression'],
    'grouped_expression': provenance['grouped_expression'],
    'row_count': 60,
    'pair_count': 30,
    'target_pair_counts': {'p20183': 15, 'p17051': 15},
    'statuses': status_map,
    'validation_summary': summary,
    'inputs': {
        'analysis_json': [record_file(Path(path)) for path in provenance['analyses']],
        'sourcepin': [record_file(Path(path)) for path in provenance['sourcepin']],
        'normalized_terms': record_file(BUNDLE / 'inputs/phi_terms.hex'),
        'row_provenance': record_file(BUNDLE / 'inputs/phi_rows.json'),
        'input_provenance': record_file(BUNDLE / 'inputs/input_provenance.json'),
    },
    'sources': {
        'fortran': record_file(BUNDLE / 'source/rounding_check.f90'),
        'input_extractor': record_file(BUNDLE / 'runner/extract_inputs.py'),
        'validator': record_file(BUNDLE / 'runner/validate_results.py'),
        'runner': record_file(BUNDLE / 'runner/run_checks.sh'),
        'receipt_writer': record_file(BUNDLE / 'runner/write_receipt.py'),
    },
    'compiler': {
        'path': toolchain.get('compiler'),
        'version': toolchain.get('compiler_version'),
        'sha256': toolchain.get('ifx_sha256'),
        'profile': record_file(PROFILE),
        'environment_script': record_file(SETVARS),
        'pinned_libraries': [record_file(path) for path in PINNED_LIBRARIES],
        'o0_flags': toolchain.get('free_flags', '').split(),
        'o2_flags': toolchain.get('repro_flags', '').split(),
        'dynamic_link_readbacks': libs,
    },
    'executables': {label: record_file(path) for label, path in executables.items()},
    'logs': {
        name: record_file(BUNDLE / 'logs' / name)
        for name in ('toolchain.txt', 'compile_o0.log', 'compile_o2.log', 'o0.stdout', 'o0.stderr',
                     'o2.stdout', 'o2.stderr', 'validation.log', 'status.txt', 'ldd_O0.txt', 'ldd_O2.txt')
    },
    'outputs': {
        'arithmetic_results': record_file(BUNDLE / 'results/arithmetic_results.csv'),
        'arithmetic_summary': record_file(summary_path),
    },
    'source_worktree_head': source_head,
    'commands': {
        'o0_compile': [toolchain.get('compiler'), *toolchain.get('free_flags', '').split(),
                       str(RUN / 'rounding_check.f90'), '-o', str(executables['O0'])],
        'o2_compile': [toolchain.get('compiler'), *toolchain.get('repro_flags', '').split(),
                       str(RUN / 'rounding_check.f90'), '-o', str(executables['O2'])],
        'o0_run': [str(executables['O0'])], 'o2_run': [str(executables['O2'])],
        'validation': ['python3', '-B', str(BUNDLE / 'runner/validate_results.py')],
    },
    'scratch_inputs': {
        'fortran_source_copy': record_file(RUN / 'rounding_check.f90'),
        'hex_terms_copy': record_file(RUN / 'phi_terms.hex'),
    },
    'fresh_scratch': str(RUN),
    'limitations': [
        'This unit validates IEEE binary32 arithmetic for the captured four input terms under pinned IFX O0/O2 strict profiles.',
        'It does not prove compiled WRF instruction ordering or a forecast outcome; the native owner must establish those separately.',
        'No physical mass budget or model conservation claim is made.',
        'Interarm deltas are descriptive differences between captured B1 and DM065 values, not acceptance thresholds.',
    ],
}
receipt_path = BUNDLE / 'receipts/arithmetic_validation.json'
receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(f'{receipt["status"]}: {receipt_path}')
