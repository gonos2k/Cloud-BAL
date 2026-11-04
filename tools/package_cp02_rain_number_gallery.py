#!/usr/bin/env python3
"""Build a deterministic offline report and figure bundle with local links resolved."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/cp02_rain_number_process_20261104'
REPORT = ROOT / 'docs/CP02_RAIN_NUMBER_PROCESS_20261104.md'
OUTPUT = EVIDENCE / 'offline_report_figures.zip'
RECEIPT = EVIDENCE / 'validation/offline_bundle.json'
LINK = re.compile(r'(!?)\[([^\]]*)\]\(([^)]+)\)')
MAX_TEXT_BYTES = 2_000_000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build():
    figures = sorted((EVIDENCE / 'figures').glob('*.png')) + sorted((EVIDENCE / 'followup/figures').glob('*.png'))
    if len(figures) != 23:
        raise ValueError('expected exactly 23 final figures')
    paths = [REPORT, EVIDENCE / 'FIGURES.md', EVIDENCE / 'followup/figures/FULLSCORES.md', *figures]
    if any(not p.is_file() for p in paths):
        raise ValueError('report, gallery, scores or figure is missing')
    selected = {p.resolve() for p in paths}
    pending = [p for p in selected if p.suffix.lower() == '.md']
    transformed = {}
    omitted = []
    while pending:
        path = pending.pop()
        if path in transformed:
            continue
        text = path.read_text(encoding='utf-8')
        def resolve(match):
            marker, label, target = match.groups()
            target = target.strip().split(' ', 1)[0].strip('<>')
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                return match.group(0)
            candidate = (path.parent / unquote(url.path)).resolve()
            try:
                candidate.relative_to(ROOT)
            except ValueError:
                omitted.append({'source': str(path.relative_to(ROOT)), 'target': target})
                return label + ' (오프라인 미포함)'
            mutable = any(candidate.is_relative_to(EVIDENCE / name) for name in ('validation', 'kg'))
            allowed = candidate in selected or (not mutable and candidate.is_file() and candidate.stat().st_size <= MAX_TEXT_BYTES and candidate.suffix.lower() in ('.md', '.csv', '.json'))
            if not allowed:
                omitted.append({'source': str(path.relative_to(ROOT)), 'target': target})
                return label + ' (오프라인 미포함)'
            if candidate not in selected:
                selected.add(candidate)
                if candidate.suffix.lower() == '.md': pending.append(candidate)
            return match.group(0)
        transformed[path] = LINK.sub(resolve, text).encode('utf-8')
    entries = {str(p.relative_to(ROOT)): transformed[p] if p in transformed else p.read_bytes() for p in selected}
    for path, content in transformed.items():
        for match in LINK.finditer(content.decode('utf-8')):
            url = urlsplit(match.group(3).strip().split(' ', 1)[0].strip('<>'))
            if not url.scheme and not url.netloc and url.path:
                target = (path.parent / unquote(url.path)).resolve()
                if str(target.relative_to(ROOT)) not in entries:
                    raise ValueError(f'unresolved packaged link in {path}: {match.group(3)}')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=OUTPUT.parent, prefix='.offline-', suffix='.zip', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None or set(archive.namelist()) != set(entries):
                raise ValueError('offline archive integrity failed')
            if any(sha(archive.read(name)) != sha(data) for name, data in entries.items()):
                raise ValueError('offline archive member differs')
        temporary.replace(OUTPUT)
    finally:
        temporary.unlink(missing_ok=True)
    receipt = {'status': 'PASS', 'archive_sha256': sha(OUTPUT.read_bytes()), 'members': {name: sha(data) for name, data in sorted(entries.items())}, 'png_count': len(figures), 'omitted_nonbundled_links': omitted, 'external_urls_remain_online': True, 'builder_sha256': sha(Path(__file__).read_bytes())}
    RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{len(entries)} members, {len(figures)} PNGs, {len(omitted)} nonbundled local links')


if __name__ == '__main__':
    build()
