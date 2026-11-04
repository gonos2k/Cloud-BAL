#!/usr/bin/env python3
"""Build a deterministic offline report and figure bundle with local links resolved."""
from __future__ import annotations

import hashlib
import json
import argparse
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/cp02_failure_regimes_20261104'
REPORT = ROOT / 'docs/CP02_FAILURE_REGIMES_20261104.md'
OUTPUT = EVIDENCE / 'offline'
LINK = re.compile(r'(!?)\[([^\]]*)\]\(([^)]+)\)')
MAX_TEXT_BYTES = 2_000_000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(output: Path | None = None):
    output = Path(output) if output is not None else OUTPUT
    if os.path.lexists(output):
        raise FileExistsError(f'output already exists: {output}')
    figures = sorted((EVIDENCE / 'figures').glob('*.png'))
    if len(figures) != 28:
        raise ValueError('expected exactly 28 final figures')
    metadata_path = EVIDENCE / 'figures/metadata.json'
    metadata_bytes = metadata_path.read_bytes(); figure_meta = json.loads(metadata_bytes)
    pins = figure_meta.get('outputs', {})
    for figure in figures:
        if figure.is_symlink() or sha(figure.read_bytes()) != pins.get(figure.name):
            raise ValueError(f'figure differs from metadata: {figure.name}')
    paths = [REPORT, EVIDENCE / 'FIGURES.md', EVIDENCE / 'figures/FULLTABLES.md', *figures]
    if any(not p.is_file() for p in paths):
        raise ValueError('report, gallery, scores or figure is missing')
    selected = {p.resolve() for p in paths}
    pending = [p for p in selected if p.suffix.lower() == '.md']
    transformed = {}
    source_hashes = {}
    omitted = []
    while pending:
        path = pending.pop()
        if path in transformed:
            continue
        raw = path.read_bytes(); source_hashes[path] = sha(raw); text = raw.decode('utf-8')
        def resolve(match):
            marker, label, target = match.groups()
            target = target.strip().split(' ', 1)[0].strip('<>')
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                return match.group(0)
            candidate = (path.parent / unquote(url.path)).resolve()
            old_evidence = ROOT / 'docs/evidence/cp02_rain_number_process_20261104'
            if candidate.is_relative_to(old_evidence):
                external = 'https://github.com/gonos2k/Cloud-BAL/blob/aca6ffe0b9aa1705a20586bab4ab4b1fbe126b17/' + str(candidate.relative_to(ROOT))
                return marker + '[' + label + '](' + external + ')'
            try:
                candidate.relative_to(ROOT)
            except ValueError:
                omitted.append({'source': str(path.relative_to(ROOT)), 'target': target})
                return label + ' (오프라인 미포함)'
            mutable = any(candidate.is_relative_to(EVIDENCE / name) for name in ('validation', 'kg'))
            allowed = candidate in selected or (candidate.is_relative_to(EVIDENCE) and not mutable and candidate.is_file() and candidate.stat().st_size <= MAX_TEXT_BYTES and candidate.suffix.lower() in ('.md', '.csv', '.json'))
            if not allowed:
                omitted.append({'source': str(path.relative_to(ROOT)), 'target': target})
                return label + ' (오프라인 미포함)'
            if candidate not in selected:
                selected.add(candidate)
                if candidate.suffix.lower() == '.md': pending.append(candidate)
            return match.group(0)
        transformed[path] = LINK.sub(resolve, text).encode('utf-8')
    entries = {str(p.relative_to(ROOT)): transformed[p] if p in transformed else p.read_bytes() for p in selected}
    source_hashes.update({p: sha(entries[str(p.relative_to(ROOT))]) for p in selected if p not in transformed})
    for path, content in transformed.items():
        for match in LINK.finditer(content.decode('utf-8')):
            url = urlsplit(match.group(3).strip().split(' ', 1)[0].strip('<>'))
            if not url.scheme and not url.netloc and url.path:
                target = (path.parent / unquote(url.path)).resolve()
                if str(target.relative_to(ROOT)) not in entries:
                    raise ValueError(f'unresolved packaged link in {path}: {match.group(3)}')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=output.parent, prefix='.offline-stage-'))
    try:
        archive_path = stage / 'report_figures.zip'
        with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        with zipfile.ZipFile(archive_path) as archive:
            if archive.testzip() is not None or set(archive.namelist()) != set(entries):
                raise ValueError('offline archive integrity failed')
            if any(sha(archive.read(name)) != sha(data) for name, data in entries.items()):
                raise ValueError('offline archive member differs')
        for path in selected:
            if sha(path.read_bytes()) != source_hashes[path]:
                raise ValueError(f'input changed while packaging: {path}')
        if metadata_path.read_bytes() != metadata_bytes:
            raise ValueError('figure metadata changed while packaging')
        receipt = {'status': 'PASS', 'archive_sha256': sha(archive_path.read_bytes()), 'members': {name: sha(data) for name, data in sorted(entries.items())}, 'png_count': len(figures), 'figure_metadata_sha256': sha(metadata_bytes), 'omitted_nonbundled_links': omitted, 'external_urls_remain_online': True, 'builder_sha256': sha(Path(__file__).read_bytes())}
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if os.path.lexists(output):
            raise FileExistsError(f'output already exists: {output}')
        stage.rename(output)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    print(f'{len(entries)} members, {len(figures)} PNGs, {len(omitted)} nonbundled local links')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    build(parser.parse_args().output)
