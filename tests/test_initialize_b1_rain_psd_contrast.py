import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('dm065_initializer', ROOT / 'tools/initialize_b1_rain_psd_contrast.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_receipt_write_failure_removes_owned_partial_and_output(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.write_text('original')
    output, receipt = tmp_path / 'candidate', tmp_path / 'receipt.json'
    def prepare(input_path, entry, entry_sha, output_path):
        output_path.write_text('candidate')
        stat = output_path.stat()
        return {'value': 1}, (stat.st_dev, stat.st_ino)
    def fail_dump(value, stream, **kwargs):
        stream.write('{"partial":')
        raise OSError('injected receipt write failure')
    monkeypatch.setattr(module, 'prepare', prepare)
    monkeypatch.setattr(module.json, 'dump', fail_dump)
    monkeypatch.setattr(sys, 'argv', ['contrast', '--input', str(source), '--baseline-density-capture', str(source),
                                      '--baseline-density-capture-sha256', 'a' * 64,
                                      '--output', str(output), '--receipt', str(receipt)])
    assert module.main() == 2
    assert source.read_text() == 'original'
    assert not output.exists() and not receipt.exists()


def test_preexisting_receipt_and_candidate_are_preserved(tmp_path, monkeypatch):
    source, output, receipt = tmp_path / 'source', tmp_path / 'candidate', tmp_path / 'receipt.json'
    source.write_text('source')
    output.write_text('existing candidate')
    receipt.write_text('existing receipt')
    monkeypatch.setattr(sys, 'argv', ['contrast', '--input', str(source), '--baseline-density-capture', str(source),
                                      '--baseline-density-capture-sha256', 'a' * 64,
                                      '--output', str(output), '--receipt', str(receipt)])
    assert module.main() == 2
    assert output.read_text() == 'existing candidate'
    assert receipt.read_text() == 'existing receipt'


def test_receipt_failure_does_not_delete_replaced_output(tmp_path, monkeypatch):
    source, output, receipt = tmp_path / 'source', tmp_path / 'candidate', tmp_path / 'receipt.json'
    source.write_text('original')
    def prepare(input_path, entry, entry_sha, output_path):
        output_path.write_text('owned')
        stat = output_path.stat()
        return {'value': 1}, (stat.st_dev, stat.st_ino)
    def fail_dump(value, stream, **kwargs):
        # Preserve old inode while installing another file, avoiding inode reuse.
        output.rename(tmp_path / 'old-owned')
        output.write_text('other writer')
        stream.write('{partial')
        raise OSError('injected failure')
    monkeypatch.setattr(module, 'prepare', prepare)
    monkeypatch.setattr(module.json, 'dump', fail_dump)
    monkeypatch.setattr(sys, 'argv', ['contrast', '--input', str(source), '--baseline-density-capture', str(source),
                                      '--baseline-density-capture-sha256', 'a' * 64,
                                      '--output', str(output), '--receipt', str(receipt)])
    assert module.main() == 2
    assert output.read_text() == 'other writer'
    assert not receipt.exists()


def test_existing_output_leaves_no_new_receipt(tmp_path, monkeypatch):
    source, output, receipt = tmp_path / 'source', tmp_path / 'candidate', tmp_path / 'receipt.json'
    source.write_text('source')
    output.write_text('existing candidate')
    monkeypatch.setattr(sys, 'argv', ['contrast', '--input', str(source), '--baseline-density-capture', str(source),
                                      '--baseline-density-capture-sha256', 'a' * 64,
                                      '--output', str(output), '--receipt', str(receipt)])
    assert module.main() == 2
    assert output.read_text() == 'existing candidate'
    assert not receipt.exists()


def test_receipt_type_error_and_interrupt_cleanup_then_reraise(tmp_path, monkeypatch):
    import pytest
    source = tmp_path / 'source'
    source.write_text('original')
    for error in (TypeError('injected'), KeyboardInterrupt()):
        output, receipt = tmp_path / 'candidate', tmp_path / 'receipt.json'
        def prepare(input_path, entry, entry_sha, output_path):
            output_path.write_text('candidate')
            stat = output_path.stat()
            return {'value': 1}, (stat.st_dev, stat.st_ino)
        def fail_dump(value, stream, **kwargs):
            stream.write('{partial')
            raise error
        monkeypatch.setattr(module, 'prepare', prepare)
        monkeypatch.setattr(module.json, 'dump', fail_dump)
        monkeypatch.setattr(sys, 'argv', ['contrast', '--input', str(source), '--baseline-density-capture', str(source),
                                          '--baseline-density-capture-sha256', 'a' * 64,
                                          '--output', str(output), '--receipt', str(receipt)])
        with pytest.raises(type(error)):
            module.main()
        assert source.read_text() == 'original'
        assert not output.exists() and not receipt.exists()
