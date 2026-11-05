import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded

render = module('plot_grouped', 'tools/plot_cp02_grouped_forecast.py')
score = module('score_grouped', 'tools/cp02_grouped_forecast.py')


def make_arrays():
    reference = np.resize(np.array([0., .1, .5, 1., 2.5, 5., 10.]), render.POINTS)
    coords = {
        'latitude': np.linspace(33., 39., render.POINTS),
        'longitude': np.linspace(124., 131., render.POINTS),
        'flat_index_yx': np.arange(render.POINTS, dtype=np.int32),
    }
    hourly = {}
    for hour in render.HOURS:
        hourly[hour] = {'reference': reference.copy(), **{k: v.copy() for k, v in coords.items()}}
        for index, case in enumerate(render.CASES):
            hourly[hour][case] = np.roll(reference, index + hour - 12).copy()
    return hourly


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def record(path):
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size_bytes': path.stat().st_size}


def write_analysis(folder: Path):
    folder.mkdir()
    arrays = make_arrays()
    categorical, continuous, contrasts, transitions, gates = score.score(arrays)
    outputs = {}
    for name, rows in (('categorical_scores.csv', categorical), ('continuous_scores.csv', continuous),
                       ('contrasts.csv', contrasts), ('weak_transition_counts.csv', transitions),
                       ('gate_results.csv', gates)):
        path = folder / name
        write_csv(path, rows)
        outputs[name] = record(path)
    (folder / 'winner.json').write_text('{"winner":"C"}\n', encoding='utf-8')
    outputs['winner.json'] = record(folder / 'winner.json')
    for hour, values in arrays.items():
        path = folder / f'hour_{hour}_arrays.npz'
        np.savez_compressed(path, **values)
        outputs[path.name] = record(path)
    source_record = {'path': '/archived-worktree/raw/source.receipt',
                     'sha256': hashlib.sha256(b'fixture input identity').hexdigest(), 'size_bytes': 22}
    plan = score.identity(score.PLAN)
    scorer = score.identity(score.Path(score.__file__))
    receipt = {'schema': 'cp02_grouped_forecast_result_v1', 'status': 'COMPLETE',
               'initial_time_utc': '2026-08-16T12:00:00Z', 'hours_utc': list(render.HOURS),
               'lead_hours': list(render.LEADS), 'points_per_hour': render.POINTS,
               'thresholds_mm': list(render.THRESHOLDS), 'cases': ['A', 'B', 'C', 'D', 'ORIGINAL'],
               'arms': ['A', 'B', 'C', 'D'], 'benchmark': 'ORIGINAL',
               'precipitation_window': 'one-hour increments of RAINC + RAINNC; not cumulative lead totals',
               'rows': {'categorical': 180, 'continuous': 30, 'contrasts': 180,
                        'weak_transitions': 24, 'gates': 52},
               'evaluation_plan': plan, 'scorer': scorer,
               'inputs': [source_record], 'outputs': outputs}
    (folder / 'receipt.json').write_text(json.dumps(receipt, sort_keys=True), encoding='utf-8')
    return receipt


def test_complete_receipt_and_arrays_reconcile_all_score_cells(tmp_path):
    folder = tmp_path / 'analysis'
    write_analysis(folder)
    receipt, arrays, categorical, continuous = render.verify_analysis(folder)
    assert receipt['rows']['categorical'] == 180
    assert len(arrays) == 6 and len(categorical) == 180 and len(continuous) == 30


def test_missing_lead_or_score_coverage_is_rejected(tmp_path):
    folder = tmp_path / 'analysis'
    write_analysis(folder)
    table = folder / 'categorical_scores.csv'
    rows = render.read_csv(table)
    rows.pop()
    write_csv(table, rows)
    receipt_path = folder / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    receipt['outputs']['categorical_scores.csv'] = record(table)
    receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='categorical score table'):
        render.verify_analysis(folder)


def test_bad_input_receipt_hash_is_rejected(tmp_path):
    folder = tmp_path / 'analysis'
    write_analysis(folder)
    receipt_path = folder / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    receipt['inputs'][0]['sha256'] = 'not-a-hash'
    receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='source identity record is malformed'):
        render.verify_analysis(folder)


def test_renderer_accepts_missing_raw_input_paths_but_recounts_local_outputs(tmp_path):
    folder = tmp_path / 'analysis'
    write_analysis(folder)
    receipt, arrays, categorical, continuous = render.verify_analysis(folder)
    assert receipt['inputs'][0]['path'] == '/archived-worktree/raw/source.receipt'
    assert len(arrays) == 6 and len(categorical) == 180 and len(continuous) == 30


def test_local_score_output_hash_mutation_is_rejected(tmp_path):
    folder = tmp_path / 'analysis'
    write_analysis(folder)
    with (folder / 'continuous_scores.csv').open('a', encoding='utf-8') as stream:
        stream.write('tampered\n')
    with pytest.raises(ValueError, match='analysis output hash mismatch'):
        render.verify_analysis(folder)


def test_hourly_npz_wrong_key_or_point_count_is_rejected(tmp_path):
    arrays = make_arrays()
    del arrays[13]['D']
    analysis = tmp_path / 'analysis'
    analysis.mkdir()
    np.savez_compressed(analysis / 'hour_13_arrays.npz', **arrays[13])
    with pytest.raises(ValueError, match='NPZ key set'):
        render.load_arrays(analysis)


def test_korea_boundary_reader_accepts_lines_and_rejects_polygon(tmp_path):
    boundary = tmp_path / 'boundary.geojson'
    boundary.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': [[126., 34.], [127., 35.]]}},
        {'type': 'Feature', 'geometry': {'type': 'MultiLineString', 'coordinates': [[[128., 36.], [129., 37.]]]}},
    ]}), encoding='utf-8')
    assert len(render.read_boundary(boundary)) == 2
    boundary.write_text(json.dumps({'type': 'Polygon', 'coordinates': []}), encoding='utf-8')
    with pytest.raises(ValueError, match='no valid LineString'):
        render.read_boundary(boundary)


def test_shared_map_scales_cover_all_leads_and_delta_pairs():
    arrays = make_arrays()
    absolute, delta = render.map_scales(arrays)
    assert absolute[0] == 0.0 and absolute[1] >= 10.0
    assert delta >= 0.01
    del arrays[18]
    with pytest.raises(ValueError, match='all six lead hours'):
        render.map_scales(arrays)


def test_delta_pair_labels_use_pinned_font_supported_hyphen():
    assert render.PAIR_LABELS[('C', 'A')] == 'C-A'
    assert render.PAIR_LABELS[('D', 'A')] == 'D-A'
    assert all('\N{MINUS SIGN}' not in label for label in render.PAIR_LABELS.values())


def test_weak_rain_boundary_and_symmetric_log_delta_scale_contract():
    assert render.rain_boundaries(115.0) == (0.0, .1, .5, 1.0, 2.5, 5.0, 10.0, 20.0, 50.0, 100.0, 116.0)
    assert render.delta_colorbar_ticks(50.0) == (-50.0, -10.0, -5.0, -1.0, -.5, -.1,
                                                  0.0, .1, .5, 1.0, 5.0, 10.0, 50.0)
    assert [render.format_delta_tick(value) for value in (-50.0, -0.5, 0.0, 0.1, 10.0)] == [
        '-50', '-0.5', '0', '0.1', '10']
    assert ('D', 'B') in render.PAIRS and ('B', 'A') in render.PAIRS
    assert ('D', 'A') in render.PAIRS


def test_process_schematic_is_a_rendered_figure(tmp_path):
    family, font_path = render.korean_font()
    render.font_manager.fontManager.addfont(font_path)
    render.plt.rcParams['font.family'] = render.font_manager.FontProperties(fname=font_path).get_name()
    render.plt.rcParams['axes.unicode_minus'] = False
    name = render.draw_process_schematic(tmp_path)
    image = tmp_path / name
    assert name == render.SCHEMATIC_FILENAME
    assert image.is_file() and image.stat().st_size > 10_000


def test_fixed_timestamp_zip_is_crc_valid_and_portable(tmp_path):
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    source = bundle / 'index.html'
    source.write_text('<html>offline</html>', encoding='utf-8')
    archive_path = bundle / 'figures.zip'
    record = render.package_zip(bundle, archive_path, [source])
    assert record['size_bytes'] > 0
    with zipfile.ZipFile(archive_path) as archive:
        info = archive.getinfo('index.html')
        assert info.date_time == (1980, 1, 1, 0, 0, 0)
        assert archive.read('index.html') == source.read_bytes()


def test_render_refuses_existing_output_without_modifying_it(tmp_path):
    output = tmp_path / 'existing'
    output.mkdir()
    sentinel = output / 'sentinel.txt'
    sentinel.write_text('preserve', encoding='utf-8')
    with pytest.raises(FileExistsError):
        render.render(tmp_path / 'missing-analysis', output)
    assert sentinel.read_text(encoding='utf-8') == 'preserve'
