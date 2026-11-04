from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/package_cp02_failure_gallery.py'
spec = importlib.util.spec_from_file_location('failure_package', SCRIPT)
package = importlib.util.module_from_spec(spec); spec.loader.exec_module(package)


def test_offline_gallery_replays_and_excludes_prior_archive(tmp_path, monkeypatch):
    root = tmp_path; evidence = root / 'docs/evidence/cp02_failure_regimes_20261104'
    (evidence / 'figures').mkdir(parents=True); (evidence / 'validation').mkdir()
    for i in range(28): (evidence / 'figures' / f'{i}.png').write_bytes(b'png' + bytes([i]))
    old = root / 'docs/evidence/cp02_rain_number_process_20261104'; old.mkdir(); (old / 'README.md').write_text('old')
    report = root / 'docs/paper.md'; report.write_text('[gallery](evidence/cp02_failure_regimes_20261104/FIGURES.md) [old](evidence/cp02_rain_number_process_20261104/README.md)')
    (evidence / 'FIGURES.md').write_text('![image](figures/0.png) [table](figures/FULLTABLES.md)')
    (evidence / 'figures/FULLTABLES.md').write_text('# table')
    for name, value in (('ROOT', root), ('EVIDENCE', evidence), ('REPORT', report), ('OUTPUT', evidence / 'bundle.zip'), ('RECEIPT', evidence / 'validation/receipt.json')): monkeypatch.setattr(package, name, value)
    package.build(); first = package.OUTPUT.read_bytes(); package.build(); assert package.OUTPUT.read_bytes() == first
    with zipfile.ZipFile(package.OUTPUT) as archive:
        assert archive.testzip() is None
        assert len([name for name in archive.namelist() if name.endswith('.png')]) == 28
        assert not any('cp02_rain_number_process_20261104' in name for name in archive.namelist())
        assert 'https://github.com/gonos2k/Cloud-BAL/blob/aca6ffe0' in archive.read('docs/paper.md').decode()
    assert not json.loads(package.RECEIPT.read_text())['omitted_nonbundled_links']
