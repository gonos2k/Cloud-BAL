#!/usr/bin/env python3
"""Package the five finalized PNGs in a single network-free gallery."""
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_initial_boundaries_20261105'
RECEIPT_PINS = {'figures': '9d64cb201846d8a295a4a090bc660954f42e4b20f7c5487124e302533e1ae7f4', 'mechanism_figures': '04e94fb44a9c401d6dccf08d80cdcf2b378edb6182ee2bec058b7e9e28d128a4'}
PANELS = (
    ('mechanism_figures/rk_mass_coupled_entry.png', '초기 입자수와 RK 갱신'),
    ('mechanism_figures/phi_pressure_thermo_chain.png', '압력·Exner·기온의 실제 계산 경계'),
    ('figures/native_nr_support.png', '호출 영역의 입자수 차이 분포'),
    ('figures/first_entry_counts.png', '초기 입력과 첫 진입 차이 집계'),
    ('figures/first_four_entry_frontier.png', '첫 네 단계의 진입 차이'),
)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    output = BUNDLE / 'gallery'
    if os.path.lexists(output):
        raise FileExistsError(output)
    sources = {}
    for folder in ('figures', 'mechanism_figures'):
        receipt = BUNDLE / folder / 'receipt.json'
        if receipt.is_symlink() or sha(receipt) != RECEIPT_PINS[folder]:
            raise ValueError('Renderer receipt differs from the frozen package input')
        data = json.loads(receipt.read_text())
        sources[str(receipt.relative_to(ROOT))] = sha(receipt)
        if folder == 'figures':
            metadata_path = BUNDLE / folder / 'metadata.json'
            if sha(metadata_path) != data['metadata_sha256']:
                raise ValueError('Baseline figure metadata differs')
            sources[str(metadata_path.relative_to(ROOT))] = sha(metadata_path)
            outputs = json.loads(metadata_path.read_text())['outputs']
        else:
            outputs = data['outputs_sha256']
        for relative, _ in PANELS:
            if not relative.startswith(folder + '/'):
                continue
            path = BUNDLE / relative
            if path.is_symlink() or path.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
                raise ValueError('unsafe or invalid PNG')
            expected = outputs[path.name]
            expected = expected['sha256'] if isinstance(expected, dict) else expected
            if sha(path) != expected:
                raise ValueError('PNG differs from renderer receipt: ' + relative)
            sources[str(path.relative_to(ROOT))] = sha(path)
    stage = Path(tempfile.mkdtemp(prefix='.gallery-', dir=BUNDLE))
    try:
        title = '초기 입자수·압력 전달 경계 그림 모음'
        md = '# ' + title + '\n\n현재 B1 유지 · DM065 미채택 · 새 6시간 성능 결과 없음.\n'
        local_md = md
        page = '<!doctype html><meta charset="utf-8"><title>' + title + '</title><h1>' + title + '</h1>'
        members = {}
        for relative, caption in PANELS:
            name = Path(relative).name
            md += f'\n## {caption}\n\n![{caption}](../{relative})\n'
            local_md += f'\n## {caption}\n\n![{caption}]({name})\n'
            page += f'<h2>{html.escape(caption)}</h2><img loading="lazy" style="max-width:100%" alt="{html.escape(caption)}" src="{name}">'
            members[name] = (BUNDLE / relative).read_bytes()
        members.update({'index.html': page.encode(), 'FIGURES.md': local_md.encode(),
                        'source_manifest.json': (json.dumps(sources, indent=2, sort_keys=True) + '\n').encode()})
        archive = stage / 'all_figures.zip'
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as package:
            for name, raw in sorted(members.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 5, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                package.writestr(info, raw)
        with zipfile.ZipFile(archive) as package:
            if package.testzip() is not None or set(package.namelist()) != set(members):
                raise ValueError('ZIP inventory/CRC differs')
            if any(package.read(name) != raw for name, raw in members.items()):
                raise ValueError('ZIP bytes differ')
        (stage / 'FIGURES.md').write_text(md)
        (stage / 'index.html').write_text(page.replace('src="', 'src="../figures/'))
        # HTML outside the ZIP needs the two mechanism paths as well.
        text = (stage / 'index.html').read_text()
        for relative, _ in PANELS:
            text = text.replace('../figures/' + Path(relative).name, '../' + relative)
        (stage / 'index.html').write_text(text)
        for relative, expected in sources.items():
            if sha(ROOT / relative) != expected:
                raise ValueError('source changed while packaging')
        receipt = {'status': 'PASS', 'producer_sha256': sha(__file__), 'source_sha256': sources,
                   'png_count': 5, 'zip_members': sorted(members),
                   'outputs': {p.name: sha(p) for p in sorted(stage.iterdir())}}
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        if os.path.lexists(output):
            raise FileExistsError(output)
        os.rename(stage, output)
        print(json.dumps({'status': 'PASS', 'png_count': 5, 'zip_sha256': sha(output / 'all_figures.zip')}))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    main()
