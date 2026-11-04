from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/package_cp02_failure_gallery.py'
spec = importlib.util.spec_from_file_location('failure_package', SCRIPT)
package = importlib.util.module_from_spec(spec); spec.loader.exec_module(package)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path; evidence = root / 'docs/evidence/cp02_failure_regimes_20261104'
    (evidence / 'figures').mkdir(parents=True); (evidence / 'validation').mkdir()
    pins = {}
    for i in range(28):
        path = evidence / 'figures' / f'{i}.png'; data = b'png' + bytes([i]); path.write_bytes(data); pins[path.name] = hashlib.sha256(data).hexdigest()
    (evidence / 'figures/metadata.json').write_text(json.dumps({'outputs': pins}))
    old = root / 'docs/evidence/cp02_rain_number_process_20261104'; old.mkdir(); (old / 'README.md').write_text('old')
    report = root / 'docs/paper.md'; report.write_text('[gallery](evidence/cp02_failure_regimes_20261104/FIGURES.md) [old](evidence/cp02_rain_number_process_20261104/README.md)')
    (evidence / 'FIGURES.md').write_text('![image](figures/0.png) [table](figures/FULLTABLES.md)')
    (evidence / 'figures/FULLTABLES.md').write_text('# table')
    for name, value in (('ROOT', root), ('EVIDENCE', evidence), ('REPORT', report), ('OUTPUT', evidence / 'offline')): monkeypatch.setattr(package, name, value)
    return evidence


def test_fresh_gallery_replays_and_excludes_prior_archive(fixture):
    first = fixture / 'one'; second = fixture / 'two'
    package.build(first); package.build(second)
    assert (first / 'report_figures.zip').read_bytes() == (second / 'report_figures.zip').read_bytes()
    assert (first / 'receipt.json').read_bytes() == (second / 'receipt.json').read_bytes()
    with zipfile.ZipFile(first / 'report_figures.zip') as archive:
        assert archive.testzip() is None
        assert len([name for name in archive.namelist() if name.endswith('.png')]) == 28
        assert not any('cp02_rain_number_process_20261104' in name for name in archive.namelist())
        assert 'https://github.com/gonos2k/Cloud-BAL/blob/aca6ffe0' in archive.read('docs/paper.md').decode()
    assert not json.loads((first / 'receipt.json').read_text())['omitted_nonbundled_links']
    with pytest.raises(FileExistsError): package.build(first)
    dangling = fixture / 'dangling'; dangling.symlink_to(fixture / 'missing', target_is_directory=True)
    with pytest.raises(FileExistsError): package.build(dangling)


def test_tampered_png_rejected_without_publishing(fixture):
    (fixture / 'figures/0.png').write_bytes(b'changed')
    output = fixture / 'new'
    with pytest.raises(ValueError, match='figure differs from metadata'): package.build(output)
    assert not output.exists() and not list(fixture.glob('.offline-stage-*'))


def test_receipt_failure_cleans_stage_and_preserves_existing(fixture, monkeypatch):
    old = fixture / 'old'; old.mkdir(); (old / 'sentinel').write_bytes(b'keep')
    original = Path.write_text
    def fail_receipt(path, *args, **kwargs):
        if path.name == 'receipt.json': raise OSError('injected receipt failure')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'write_text', fail_receipt)
    output = fixture / 'new'
    with pytest.raises(OSError, match='injected receipt failure'): package.build(output)
    assert not output.exists() and not list(fixture.glob('.offline-stage-*'))
    assert (old / 'sentinel').read_bytes() == b'keep'
