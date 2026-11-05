#!/usr/bin/env python3
"""Extract paired four-term REAL32 inputs from frozen phi reanalysis artifacts."""
from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
BUNDLE = Path(__file__).resolve().parents[1]
INPUTS = BUNDLE / 'inputs'
OLD_ANALYSIS = ROOT / 'docs/evidence/cp02_initial_boundaries_20261105/science'
OLD_SOURCE = ROOT / 'docs/evidence/cp02_initial_boundaries_20261105/native/sourcepins/module_big_step_utilities_em.f90'
TERMS = ('ph_next', 'ph', 'phb_next', 'phb')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite_word(word: str) -> bool:
    value = struct.unpack('<f', bytes.fromhex(word))[0]
    return math.isfinite(value)


def main() -> None:
    rows = []
    inputs = {}
    for target in ('p20183', 'p17051'):
        path = OLD_ANALYSIS / f'phi_{target}' / 'analysis.json'
        inputs[str(path)] = sha256(path)
        data = json.loads(path.read_text(encoding='utf-8'))
        arm_calls = {
            arm: {call['entry_sequence']: call for call in data['arms'][arm]['calls']}
            for arm in ('B1', 'DM065')
        }
        pairs = data['paired_phi']
        if len(pairs) != 15:
            raise SystemExit(f'{target}: expected exactly 15 paired phi calls, found {len(pairs)}')
        for pair_index, pair in enumerate(pairs, 1):
            for arm, sequence_key in (('B1', 'B1_entry_sequence'), ('DM065', 'DM065_entry_sequence')):
                sequence = pair[sequence_key]
                call = arm_calls[arm].get(sequence)
                if call is None:
                    raise SystemExit(f'{target} pair {pair_index}: missing {arm} call {sequence}')
                fields = call['entry_fields_raw']
                words = [fields[name].lower() for name in TERMS]
                if any(len(word) != 8 or not finite_word(word) for word in words):
                    raise SystemExit(f'{target} pair {pair_index} {arm}: invalid/non-finite binary32 words')
                rows.append({
                    'row': len(rows) + 1,
                    'target': target,
                    'pair': pair_index,
                    'arm': arm,
                    'entry_sequence': sequence,
                    'kdm_entered': call['kdm_entered'],
                    'kdm_completed': call['kdm_completed'],
                    'a_ph_next_hex': words[0],
                    'b_ph_hex': words[1],
                    'c_phb_next_hex': words[2],
                    'd_phb_hex': words[3],
                })
    if len(rows) != 60:
        raise SystemExit(f'expected 60 arm rows (30 B1/DM065 pairs), found {len(rows)}')
    INPUTS.mkdir(parents=True, exist_ok=True)
    with (INPUTS / 'phi_terms.hex').open('x', encoding='ascii') as stream:
        for row in rows:
            raw_words = [row[key] for key in (
                'a_ph_next_hex', 'b_ph_hex', 'c_phb_next_hex', 'd_phb_hex')]
            int_words = [int.from_bytes(bytes.fromhex(word), 'little') for word in raw_words]
            stream.write(' '.join(f'{word:08X}' for word in int_words) + '\n')
    with (INPUTS / 'phi_rows.json').open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(rows, indent=2) + '\n')
    with (INPUTS / 'input_provenance.json').open('x', encoding='utf-8') as stream:
        stream.write(json.dumps({
            'source_expression': '(ph(k+1)-ph(k)+phb(k+1)-phb(k))',
            'grouped_expression': '((ph(k+1)-ph(k))+(phb(k+1)-phb(k)))',
            'term_order': list(TERMS),
            'analyses': inputs,
            'sourcepin': {str(OLD_SOURCE): sha256(OLD_SOURCE)},
            'paired_calls_per_target': 15,
            'arm_rows': len(rows),
            'finite_binary32_words': True,
            'analysis_words_are_little_endian_byte_hex': True,
            'phi_terms_hex_uses_big_endian_z8_integer_spelling': True,
        }, indent=2) + '\n')
    print(f'captured {len(rows)} finite REAL32 arm rows from 30 paired phi calls')


if __name__ == '__main__':
    main()
