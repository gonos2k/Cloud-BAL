import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from cp02_sedimentation_conservation import replay


def two_layer():
    pre = np.zeros((2, 22), dtype=np.float32)
    post = np.zeros((2, 27), dtype=np.float32)
    pre[:, 10:12] = 1, 100
    pre[:, 12] = 20
    pre[1, 5] = .001
    post[:, :22] = pre
    post[1, 22] = np.float32(.001) * np.float32(3.75) / np.float32(100)
    post[:, 17] = post[:, 22]
    post[1, 5] = np.float32(pre[1, 5] - post[1, 22] * np.float32(20))
    post[0, 5] = min(np.float32(post[1, 22] * np.float32(20)), post[1, 5])
    return pre, post


def test_two_layer_updated_upper_loses_half_column():
    pre, post = two_layer()
    raw, received, removal, receipt, stored, boundary, nominal, gap, rounding = replay(pre, post, 5, 17, 22, True)
    assert raw[0] > post[1, 5]
    assert received[0] == post[1, 5]
    assert removal[0] == pytest.approx(.075)
    assert receipt[0] == pytest.approx(.025)
    assert gap[0] == pytest.approx(.05)
    assert stored == pytest.approx(-.05)
    assert boundary == nominal == 0
    assert abs(rounding) < 1e-8


def test_rejects_mutated_post_and_nonfinite():
    pre, post = two_layer()
    post[0, 5] = np.nextafter(post[0, 5], np.float32(1))
    with pytest.raises(ValueError, match='POST replay mismatch'):
        replay(pre, post, 5, 17, 22, True)
    pre[0, 10] = np.nan
    with pytest.raises(ValueError, match='invalid'):
        replay(pre, post, 5, 17, 22, True)


def test_number_column_uses_thickness_without_density():
    pre, post = two_layer()
    pre[:, 8], post[:, 8] = pre[:, 5], post[:, 5]
    post[:, 25], post[:, 20] = post[:, 22], post[:, 17]
    pre[:, 10] = post[:, 10] = (5, 7)
    *_, gap, rounding = replay(pre, post, 8, 20, 25, False)
    assert gap[0] == pytest.approx(.05)
    assert abs(rounding) < 1e-8


@pytest.mark.parametrize('arm', ['OLD', 'FIX'])
def test_portable_p01_raw_frames(arm):
    import cp02_protected_process_capture as cap
    import cp02_sedimentation_conservation as audit
    root = Path(__file__).resolve().parents[1]
    subset = root / 'docs/evidence/cp02_sedimentation_conservation_20261109/audit/raw_subset' / arm / 'cp04_t000328-000330_rank3.bin'
    schema, _, _ = cap.load_contract()
    counts = {int(p): len(spec['fields']) for p, spec in schema['phases'].items()}
    seen = set()
    for frame, records in cap.iter_process_frames(subset, counts, 3):
        for i in (140, 141):
            subset_records = [r for r in records if r.i == i and r.phase in (9, 10)]
            assert subset_records
            msteps = {r.mstep for r in subset_records}
            assert len(msteps) == 1
            index = {(r.substep, r.k, r.phase): r.values for r in subset_records}
            for n in range(1, msteps.pop() + 1):
                pre = np.stack([index[n, k, 9] for k in range(1, 40)])
                post = np.stack([index[n, k, 10] for k in range(1, 40)])
                for _, state, fall, flux, mass in audit.SPECIES:
                    audit.replay(pre, post, state, fall, flux, mass)
            seen.add((frame.j, i))
    assert seen == {(79, 140), (79, 141), (80, 140), (80, 141)}


def test_failed_audit_preserves_existing_result(tmp_path, monkeypatch):
    import cp02_sedimentation_conservation as audit
    result = tmp_path / 'OLD'
    result.mkdir()
    (result / 'receipt').write_text('existing')
    with pytest.raises(FileExistsError):
        audit.run(tmp_path, 'OLD', tmp_path, tmp_path)
    assert (result / 'receipt').read_text() == 'existing'
    result.rename(tmp_path / 'saved')
    def fail(case, arm, launch, stage):
        (stage / 'partial').write_text('partial')
        raise ValueError('bad input')
    monkeypatch.setattr(audit, '_run', fail)
    with pytest.raises(ValueError, match='bad input'):
        audit.run(tmp_path, 'OLD', tmp_path, tmp_path)
    assert not (tmp_path / 'OLD').exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ['saved']


def test_rejects_dangling_output_symlink(tmp_path):
    import cp02_sedimentation_conservation as audit
    result = tmp_path / 'OLD'
    result.symlink_to(tmp_path / 'missing', target_is_directory=True)
    with pytest.raises(FileExistsError):
        audit.run(tmp_path, 'OLD', tmp_path, tmp_path)
    assert result.is_symlink()


def test_role_aggregation_deduplicates_native_columns(tmp_path):
    import csv
    import gzip
    import cp02_sedimentation_conservation as audit
    import cp02_protected_process_capture as capture
    cohort = capture.Cohort([(1, 1)], ['C'], ['P', 'Q'], np.array([[0], [0]]),
                            np.array([[1.], [1.]]), {'P': ['shared'], 'Q': ['shared']})
    source = tmp_path / 'substeps.csv.gz'
    fields = ['i', 'j', 'step', 'species', 'unit', 'limiter_events', 'transfer_gap',
              'column_change', 'ground_fall_increment', 'nominal_ground_flux', 'rounding_residual']
    with gzip.open(source, 'wt', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(dict(i=1, j=1, step=721, species='rain', unit='kg_m-2', limiter_events=1,
                             transfer_gap=2, column_change=-5, ground_fall_increment=3,
                             nominal_ground_flux=3, rounding_residual=0))
    out = tmp_path / 'roles.csv'
    audit.summarize_roles(source, cohort, out)
    with out.open(newline='') as stream:
        rows = {row['group']: row for row in csv.DictReader(stream)}
    assert float(rows['shared']['transfer_gap']) == 2
    assert float(rows['role_point_sum/shared']['transfer_gap']) == 4
    assert float(rows['h5/shared']['transfer_gap']) == 2
    assert float(rows['shared']['actual_bottom_removal']) == 3


def test_raw_frame_to_atomic_role_publication(tmp_path, monkeypatch):
    import csv
    import gzip
    from collections import defaultdict
    from types import SimpleNamespace
    import cp02_protected_process_capture as capture
    import cp02_sedimentation_conservation as audit
    schema, cohort, _ = capture.load_contract()
    counts = {int(p): len(spec['fields']) for p, spec in schema['phases'].items()}
    root = Path(__file__).resolve().parents[1]
    raw = root / 'docs/evidence/cp02_sedimentation_conservation_20261109/audit/raw_subset/OLD/cp04_t000328-000330_rank3.bin'
    frames = list(capture.iter_process_frames(raw, counts, 3))
    assert {f.j for f, _ in frames} == {79, 80}
    rank = np.full((900, 39, len(cohort.cells)), 3, dtype=np.int16)
    calls = np.full((900, 39, len(cohort.cells)), frames[0][0].call_id, dtype=np.int32)
    inventory = SimpleNamespace(owners_rank=rank, owners_call=calls)
    def reduce_fixture(case, arm, launch, stage):
        with gzip.open(stage / 'OLD_substeps.csv.gz', 'wt', newline='') as sub, gzip.open(stage / 'OLD_events.csv.gz', 'wt', newline='') as ev:
            writer, events = csv.writer(sub), csv.writer(ev)
            writer.writerow(('step', 'rank', 'call', 'i', 'j', 'substep', 'mstep', 'species', 'unit',
                             'limiter_events', 'transfer_gap', 'column_change', 'ground_fall_increment',
                             'nominal_ground_flux', 'rounding_residual'))
            totals = defaultdict(lambda: defaultdict(float))
            for frame, records in frames:
                assert frame.call_id == frames[0][0].call_id
                audit.audit_frame(frame, records, cohort, inventory, writer, events, totals,
                                  {(140, 79), (141, 79), (140, 80), (141, 80)})
            assert totals['rain']['substeps'] > 0
    monkeypatch.setattr(audit, '_run', reduce_fixture)
    audit.run(tmp_path, 'OLD', tmp_path, tmp_path)
    with (tmp_path / 'OLD/OLD_roles.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert any(r['group'] == 'point/RN1_10942' and r['species'] == 'rain' for r in rows)
    assert any(r['group'] == 'plus2_OA_weak_loss' and r['species'] == 'rain' for r in rows)
    assert not list(tmp_path.glob('.OLD-*'))


def test_bottom_outflow_cap_is_not_storage_rounding():
    pre = np.zeros((2, 22), dtype=np.float32)
    post = np.zeros((2, 27), dtype=np.float32)
    pre[:, 10:12] = 1, 100
    pre[:, 12] = 20
    pre[0, 5] = .001
    post[:, :22] = pre
    post[0, 5] = 0
    post[0, 17] = post[0, 22] = .0001
    *_, stored, boundary, nominal, gap, rounding = replay(pre, post, 5, 17, 22, True)
    assert stored == pytest.approx(-.1)
    assert boundary == pytest.approx(.2)
    assert nominal == pytest.approx(.2)
    assert gap[0] == 0
    assert abs(rounding) < 1e-8
