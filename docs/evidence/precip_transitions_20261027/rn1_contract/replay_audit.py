#!/usr/bin/env python3
"""Replay bounded CP02 RN1 artifact and actual runtime-path checks."""
from __future__ import annotations

import hashlib
from pathlib import Path

RN1_ROOT = Path('/NHNHOME/DATA/yhlee_data/ODAM/20260816')
PRODUCER = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/klaps-v5.0_/dfsd/ODAM/klps_lc05_dfsd_odam.f')
EXPECTED_PRODUCER_SHA256 = 'f0088086ee3db6fe7ef7aa8faa2e9d4bc9fedd282f9c3b67fdd56bf9f5ecce16'
KL05_ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
DAOU = KL05_ROOT / 'ANAL/NE57/DAOU/DFSD/20260816'
LOG_CANDIDATES = [
    KL05_ROOT / 'ANAL/NE57/DAIO/LOGO',
    KL05_ROOT / 'ANAL/NE57/LOGO',
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    print('RN1 canonical file audit')
    for hour in range(13, 19):
        path = RN1_ROOT / f'DFS_VSRT_GRD_KLPS_ODAM_RN1.20260816{hour:02d}00'
        if not path.is_file():
            print(f'MISSING {path}')
            continue
        raw = path.read_bytes()
        header = raw.splitlines()[0].decode('ascii', 'replace')
        expected = f'20260816{hour:02d}+000hour'
        print(f'{path.name} bytes={len(raw)} sha256={hashlib.sha256(raw).hexdigest()} header_match={header.startswith(expected)} header={header}')

    actual = sha256(PRODUCER) if PRODUCER.is_file() else None
    print('Producer source pin')
    print(f'{PRODUCER} sha256={actual or "MISSING"} expected={EXPECTED_PRODUCER_SHA256} match={actual == EXPECTED_PRODUCER_SHA256}')

    print('Wrapper runtime rain-input candidates (actual DAOU path; no files opened for writing)')
    print(f'DAOU_ROOT {"PRESENT" if DAOU.is_dir() else "ABSENT"} {DAOU}')
    if DAOU.is_dir():
        for hour in range(13, 19):
            current = DAOU / f'anal_rain_20260816{hour:02d}00.gdat'
            previous = DAOU / f'anal_rain_20260816{hour - 1:02d}00.gdat'
            print(f'UTC {hour:02d}: same_hour={current.is_file()} previous_hour={previous.is_file()}')
        print(f'RN1_outputs_here={len(list(DAOU.glob("DFS_VSRT_GRD_KLPS_ODAM_RN1.20260816*")))}')
        print(f'KLAPS_analysis_files_here={len(list(DAOU.glob("klps_lc05_anal_20260816_*")))}')

    print('KL05LOGO candidates (wrapper derives ANLTIM from anal.tim and writes per-hour log beneath it)')
    for root in LOG_CANDIDATES:
        print(f'{"PRESENT" if root.is_dir() else "ABSENT"} {root}')
        if root.is_dir():
            for pattern in ('anal.tim', '20260816*/klps_dfsd_odam_log.20260816*'):
                print(f'  pattern={pattern} matches={len(list(root.glob(pattern)))}')

    print('Environment utility candidates')
    for path in (Path('/home/korea_keun/jobs/NE57/UTIL/ENVI/kl05_src'), Path('/home/yhlee/jobs/NE57/UTIL/ENVI/kl05_src'), KL05_ROOT / 'ANAL/NE57/UTIL/ENVI/kl05_src'):
        print(f'{"PRESENT" if path.is_file() else "ABSENT"} {path}')
    print('Unsearched: other KL05DAOU/KL05LOGO roots, runtime accounts, and archive trees not listed in the evidence receipt.')


if __name__ == '__main__':
    main()
