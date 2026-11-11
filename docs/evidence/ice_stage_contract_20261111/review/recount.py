#!/usr/bin/env python3
"""Independently recount the saved whole-column stage and probe evidence."""
from collections import Counter
from math import isfinite
from pathlib import Path

results = Path(__file__).resolve().parents[1] / 'native/full/results'
expected_rows = {
    'WRAPPER': 585, 'ENTRY': 585, 'SLOPE': 585, 'FINAL': 585,
    **{f'PSD{stage}_{position}': 585 for stage in (1, 2, 3) for position in ('PRE', 'POST')},
    'PSD1_ACTIVE': 138, 'PSD2_ACTIVE': 138, 'PSD3_ACTIVE': 43,
}
for opt in ('O0', 'O2'):
    counts = Counter()
    files = sorted((results / f'{opt}_instrumented').glob('*/stages.txt'))
    assert len(files) == 15
    for stages in files:
        original = results / f'{opt}_original' / stages.parent.name / 'terminal.bin'
        assert original.read_bytes() == stages.with_name('terminal.bin').read_bytes()
        for line in stages.read_text().splitlines():
            fields = line.split()
            assert len(fields) == 9
            stage = fields[0]
            values = [float(x) for x in fields[4:]]
            assert all(isfinite(x) for x in values)
            counts[stage] += 1
            if stage in ('ENTRY', 'PSD1_POST', 'PSD2_POST', 'PSD3_POST', 'FINAL') and values[1] > 1e6:
                counts[stage + '_over_cap'] += 1
    assert {name: counts[name] for name in expected_rows} == expected_rows
    assert {name: counts[name + '_over_cap'] for name in ('ENTRY', 'PSD1_POST', 'PSD2_POST', 'PSD3_POST', 'FINAL')} == {
        'ENTRY': 0, 'PSD1_POST': 49, 'PSD2_POST': 49, 'PSD3_POST': 0, 'FINAL': 0,
    }
    print(f'{opt}: 15 original/instrumented terminal comparisons, finite probes, and stage counts pass')
