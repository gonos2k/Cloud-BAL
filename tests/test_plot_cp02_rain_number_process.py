from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import subprocess
import sys
import zipfile

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/plot_cp02_rain_number_process.py"
SPEC = importlib.util.spec_from_file_location("rain_plot", SCRIPT)
plot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(plot)


def test_series_retains_distinct_leads_and_cases():
    data = plot.load_series(plot.COHORTS / "point_transitions.csv")
    assert len(data) == 9
    assert data["P01"]["reference"][1] == pytest.approx(.2)
    assert data["P01"]["B1"][1] < .1 <= data["P01"]["B1_RAIN_NUMBER_PRIOR"][1]
    assert data["P01"]["B1_RAIN_NUMBER_PRIOR"][2] < .1 <= data["P01"]["B1"][2]
    assert data["FA03"]["reference"][1] < 5 <= data["FA03"]["B1_RAIN_NUMBER_PRIOR"][1]
    assert data["FA03"]["B1"][1] < 5
    assert all(np.isfinite(series).all() and len(series) == 6 for point in data.values() for series in point.values())


def test_series_rejects_duplicate_and_inconsistent_rows(tmp_path):
    source = plot.COHORTS / "point_transitions.csv"
    with source.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    target = tmp_path / "input.csv"
    def write():
        with target.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    original = dict(rows[0]); rows[0] = dict(rows[1]); write()
    with pytest.raises(ValueError, match="duplicated"):
        plot.load_series(target)
    rows[0] = original; rows[0]["reference_mm"] = "999"; write()
    with pytest.raises(ValueError, match="inconsistent"):
        plot.load_series(target)


def test_deterministic_offline_gallery(tmp_path):
    dirs = [tmp_path / "one", tmp_path / "two"]
    for folder in dirs:
        result = subprocess.run([sys.executable, str(SCRIPT), "--output", str(folder)], capture_output=True, text=True, check=True)
        assert not result.stderr
    files = {p.name for p in dirs[0].iterdir()}
    assert files == {"hourly_amounts.png", "hourly_differences_from_b1.png", "gamma_prior.png", "threshold_examples_1.png", "threshold_examples_2.png", "rain_components.png", "gallery.md", "metadata.json", "offline_gallery.zip"}
    assert all((dirs[0] / name).read_bytes() == (dirs[1] / name).read_bytes() for name in files)
    with zipfile.ZipFile(dirs[0] / "offline_gallery.zip") as bundle:
        assert set(bundle.namelist()) == files - {"offline_gallery.zip"}
        assert all(not name.startswith("/") for name in bundle.namelist())


def test_component_differences_retain_cumulus_and_non_cumulus():
    series = plot.load_series(plot.COHORTS / "point_transitions.csv")
    components = plot.load_components(plot.COMPONENTS, series)
    assert components["H3_L1"][2, 0] == pytest.approx(-.0146136, abs=1e-6)
    assert components["H3_L1"][2, 1] == pytest.approx(-.592535, abs=1e-6)
    for values in components.values():
        np.testing.assert_allclose(values[:, 0] + values[:, 1], values[:, 2], atol=1e-12)


def test_final_cond_component_uses_single_precision_before_weighting():
    baseline = np.zeros((2, 2, 1, 1, 4, 11), dtype=np.float32)
    prior = baseline.copy()
    baseline[0, :, 0, :, :, 7] = np.array([.1, .2, .3, .4], dtype=np.float32)
    prior[0, :, 0, :, :, 7] = np.array([.2, .4, .6, .8], dtype=np.float32)
    baseline[0, :, 0, :, :, 8] = prior[0, :, 0, :, :, 8] = 20
    index = np.array([[0, 1, 2, 3]])
    weights = np.array([[.1, .2, .3, .4]])
    result = plot.final_cond_vapor(prior, baseline, index, weights)
    p = -np.multiply(prior[0, :, 0, :, :, 7], prior[0, :, 0, :, :, 8], dtype=np.float32)
    b = -np.multiply(baseline[0, :, 0, :, :, 7], baseline[0, :, 0, :, :, 8], dtype=np.float32)
    expected = np.einsum("slc,c->sl", p.astype(float) - b.astype(float), weights[0])
    np.testing.assert_array_equal(result[..., 0], expected)
    with pytest.raises(ValueError, match="dimensions"):
        plot.final_cond_vapor(prior[:, :, :0], baseline[:, :, :0], index, weights)


def test_process_panel_draws_signed_values(tmp_path):
    plot.configure_font()
    data = np.zeros((3, 39)); data[0, 0] = -1; data[-1, -1] = 1
    panels = [(f"test {i}", "kg/kg", data, 1.) for i in range(6)]
    path = tmp_path / "point.png"
    plot.plot_process_point("P01", panels, path)
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_process_history_shapes_and_time_extent(tmp_path):
    points = np.array(["P01", "FA03", "H3_L01", "H3_L05", "H3_FA01"])
    shape = (540, 39, len(points))
    zeros = np.zeros((*shape, 1), dtype=np.float32)
    np.savez_compressed(tmp_path / "point_history.npz", points=points,
        corner_indices=np.tile(np.arange(4), (5, 1)), corner_weights=np.full((5, 4), .25),
        sedimentation=zeros, sedimentation_fields=["qrs1"], components=zeros,
        component_fields=["prevp_qv_component"], return_difference=np.repeat(zeros, 2, axis=-1),
        between_call=np.repeat(zeros[:-1], 2, axis=-1), state_fields=["QR", "TK"])
    final = np.zeros((2, 540, 1, 39, 4, 11), dtype=np.float32)
    for case in ("B1", "NR_PRIOR"):
        source = tmp_path / f"selected_{case}.npz"
        np.savez_compressed(source, final_cond=final)
        plot.parts.pack(source, tmp_path / f"selected_{case}_parts")
        source.unlink()
    panels = plot.process_panels(tmp_path)
    assert list(panels) == list(points)
    assert [data.shape for _, _, data, _ in panels["P01"]] == [(540, 39)] * 4 + [(539, 39), (540, 39)]

    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "hourly_amounts.png"
    sentinel.write_bytes(b"existing output")
    part = next((tmp_path / "selected_B1_parts").glob("*.npz"))
    original = part.read_bytes()
    for damaged in (original + b"tampered", None):
        if damaged is None:
            part.unlink()
        else:
            part.write_bytes(damaged)
        result = subprocess.run([sys.executable, str(SCRIPT), "--process-input", str(tmp_path), "--output", str(output)], capture_output=True)
        assert result.returncode != 0
        assert list(output.iterdir()) == [sentinel]
        assert sentinel.read_bytes() == b"existing output"
