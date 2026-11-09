import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'plot_cp02_protected_process', ROOT / 'tools/plot_cp02_protected_process.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def scratch_dir():
    p.RUNTIME.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix='plot-protected-test-', dir=p.RUNTIME))


def copy_inputs(destination):
    cohorts = destination / 'cohorts'
    context = destination / 'context'
    shutil.copytree(p.COHORTS, cohorts)
    shutil.copytree(p.CONTEXT, context)
    return cohorts, context


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_rejects_changed_receipt_bound_cohort_csv():
    scratch = scratch_dir()
    try:
        cohorts, context = copy_inputs(scratch)
        with (cohorts / 'categorical_scores.csv').open('ab') as stream:
            stream.write(b'changed\n')
        with pytest.raises(p.PlotInputError, match='hash or size differs'):
            p.load_inputs(cohorts, context)
    finally:
        shutil.rmtree(scratch)


def test_rejects_missing_context_table():
    scratch = scratch_dir()
    try:
        cohorts, context = copy_inputs(scratch)
        (context / 'layer_features.csv').unlink()
        with pytest.raises(p.PlotInputError, match='input is missing'):
            p.load_inputs(cohorts, context)
    finally:
        shutil.rmtree(scratch)


def test_whole_domain_counts_use_observed_weak_mask_and_each_initialization():
    data = p.load_inputs()
    counts = data['weak_hit_counts']
    assert set(counts) == set(p.HOURS)
    assert all(row['n_grid_points'] == 3688 for row in counts.values())
    assert counts[13]['n_weak_observations'] == 880
    assert (counts[13]['pairs']['ORIGINAL_initialization']['before_hits'],
            counts[13]['pairs']['ORIGINAL_initialization']['after_hits']) == (218, 249)
    assert (counts[13]['pairs']['B1_initialization']['before_hits'],
            counts[13]['pairs']['B1_initialization']['after_hits']) == (219, 246)
    assert (counts[14]['pairs']['B1_initialization']['before_hits'],
            counts[14]['pairs']['B1_initialization']['after_hits']) == (238, 230)
    assert (counts[17]['pairs']['B1_initialization']['before_hits'],
            counts[17]['pairs']['B1_initialization']['after_hits']) == (262, 258)


def test_rejects_population_mismatch_even_with_updated_table_hash():
    scratch = scratch_dir()
    try:
        cohorts, context = copy_inputs(scratch)
        role_path = cohorts / 'role_membership.csv'
        with role_path.open(newline='', encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        removed = False
        kept = []
        for row in rows:
            if not removed and row['role'] == 'plus2_OA_weak_loss':
                removed = True
                continue
            kept.append(row)
        assert removed
        with role_path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(kept[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(kept)
        receipt_path = cohorts / 'receipt.json'
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        receipt['outputs']['role_membership.csv'] = digest(role_path)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        with pytest.raises(p.PlotInputError, match='role membership does not match'):
            p.load_inputs(cohorts, context, cohort_receipt_sha256=digest(receipt_path))
    finally:
        shutil.rmtree(scratch)


def test_failed_asset_render_does_not_publish_partial_bundle(monkeypatch):
    scratch = scratch_dir()
    try:
        output, runtime = scratch / 'figures', scratch / 'runtime'

        def fail_after_partial_write(_data, stage):
            (stage / 'partial.png').write_bytes(b'partial')
            raise RuntimeError('synthetic renderer failure')

        monkeypatch.setattr(p, 'write_assets', fail_after_partial_write)
        with pytest.raises(RuntimeError, match='synthetic renderer failure'):
            p.run(output, runtime=runtime)
        assert not output.exists()
        assert list(runtime.iterdir()) == []
    finally:
        shutil.rmtree(scratch)


def test_preserved_replacement_carries_and_binds_prior_attempt(monkeypatch):
    scratch = scratch_dir()
    try:
        output, runtime = scratch / 'figures', scratch / 'runtime'
        archive = p.OUTPUT / 'attempts/before_actual_weak_scope'
        output.mkdir()
        shutil.copytree(archive, output / 'attempts/before_actual_weak_scope')
        (output / 'old-sentinel').write_text('old bundle')

        def fake_assets(_data, stage):
            names = ('whole_domain_weak_hits.png', 'protected_failure_map.png',
                     'qrain_lower_layer_plus1h.png')
            for name in names:
                (stage / name).write_bytes(b'png placeholder')
            return names

        monkeypatch.setattr(p, 'write_assets', fake_assets)
        receipt = p.run(output, runtime=runtime, preserve_attempts=True)
        manifest_hash = digest(archive / 'attempt_manifest.json')
        assert not (output / 'old-sentinel').exists()
        assert digest(output / 'attempts/before_actual_weak_scope/attempt_manifest.json') == manifest_hash
        metadata = json.loads((output / 'metadata.json').read_text(encoding='utf-8'))
        assert metadata['preserved_prior_attempt_manifest_sha256'] == manifest_hash
        assert receipt['status'] == 'PASS'
        assert not list(runtime.glob('.cp02-protected-backup-*'))
    finally:
        shutil.rmtree(scratch)
