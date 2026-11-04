from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/package_cp02_rain_number_gallery.py'
spec = importlib.util.spec_from_file_location('rain_package', SCRIPT)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def test_offline_links_and_deterministic_zip(tmp_path, monkeypatch):
    root = tmp_path
    evidence = root / 'docs/evidence/cp02_rain_number_process_20261104'
    (evidence / 'figures').mkdir(parents=True)
    (evidence / 'followup/figures').mkdir(parents=True)
    (evidence / 'validation').mkdir()
    for i in range(11): (evidence / 'figures' / f'{i}.png').write_bytes(b'png' + bytes([i]))
    for i in range(12): (evidence / 'followup/figures' / f'{i}.png').write_bytes(b'png' + bytes([i]))
    report = root / 'docs/paper.md'
    report.write_text('[gallery](evidence/cp02_rain_number_process_20261104/FIGURES.md) [raw](missing.npz)')
    (evidence / 'FIGURES.md').write_text('![image](figures/0.png) [table](followup/figures/FULLSCORES.md)')
    (evidence / 'followup/figures/FULLSCORES.md').write_text('# all rows')
    monkeypatch.setattr(package, 'ROOT', root)
    monkeypatch.setattr(package, 'EVIDENCE', evidence)
    monkeypatch.setattr(package, 'REPORT', report)
    monkeypatch.setattr(package, 'OUTPUT', evidence / 'bundle.zip')
    monkeypatch.setattr(package, 'RECEIPT', evidence / 'validation/receipt.json')
    package.build(); first = package.OUTPUT.read_bytes(); package.build()
    assert package.OUTPUT.read_bytes() == first
    with zipfile.ZipFile(package.OUTPUT) as archive:
        assert archive.testzip() is None
        paper = archive.read('docs/paper.md').decode()
        assert '[gallery](' in paper and '[raw](' not in paper and '오프라인 미포함' in paper
        assert len([name for name in archive.namelist() if name.endswith('.png')]) == 23
    assert json.loads(package.RECEIPT.read_text())['status'] == 'PASS'
