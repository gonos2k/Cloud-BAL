#!/usr/bin/env python3
"""Compare retained zero-out object and executable text outside link masks."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    manifest_path = here / 'zeroout_section_manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    object_text = (here / 'zeroout_object_text.bin').read_bytes()
    executable_text = (here / 'zeroout_executable_text.bin').read_bytes()
    if manifest['schema'] != 'zeroout_object_link_sections_v1':
        raise ValueError('unexpected manifest schema')
    if len(object_text) != manifest['size_bytes'] or len(executable_text) != manifest['size_bytes']:
        raise ValueError('section length mismatch')
    if sha(object_text) != manifest['object_text_sha256'] or sha(executable_text) != manifest['executable_text_sha256']:
        raise ValueError('section hash mismatch')
    relocations = manifest['relocations']
    allowances = manifest['gotpcrelx_relaxation_allowances']
    expected_relocations = [
        (0xbf, 'R_X86_64_32'), (0xc4, 'R_X86_64_32'),
        (0xd0, 'R_X86_64_PLT32'), (0xe1, 'R_X86_64_REX_GOTPCRELX'),
        (0x42e, 'R_X86_64_32'), (0x433, 'R_X86_64_32'),
        (0x43f, 'R_X86_64_PLT32'), (0x500, 'R_X86_64_REX_GOTPCRELX'),
    ]
    if [(r['offset'], r['type']) for r in relocations] != expected_relocations:
        raise ValueError('unexpected relocation layout')
    if any(r['size'] != 4 for r in relocations):
        raise ValueError('unexpected relocation width')
    if [(r['offset'], r['size']) for r in allowances] != [(0xdf, 2), (0x4fe, 2)]:
        raise ValueError('unexpected linker relaxation mask')
    masked = set()
    for region in relocations + allowances:
        start, size = region['offset'], region['size']
        if start < 0 or start + size > len(object_text):
            raise ValueError('mask outside retained section')
        masked.update(range(start, start + size))
    differences = [i for i, (a, b) in enumerate(zip(object_text, executable_text)) if i not in masked and a != b]
    if differences:
        raise ValueError(f'unmasked bytes differ at {differences[:20]}')
    receipt = {
        'status': 'PASS',
        'section_manifest_sha256': sha(manifest_bytes),
        'script_sha256': sha(Path(__file__).read_bytes()),
        'object_text_sha256': sha(object_text),
        'executable_text_sha256': sha(executable_text),
        'section_size_bytes': len(object_text),
        'masked_bytes': len(masked),
        'unmasked_differences': len(differences),
        'scope': 'Retained section comparison only; masked link bytes and source-to-object provenance remain unverified.',
    }
    with args.receipt.open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
