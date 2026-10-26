import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr103_amplitude20_postclosure import rename_native_roles
import pr103_amplitude20_postclosure as postclosure


def test_native_increment_labels_preserve_contrast_roles():
    raw = {"increments": {"h_H_minus_O": [1.0], "b_C_minus_H": [2.0],
                          "net_C_minus_O": [3.0]}}
    assert rename_native_roles(raw, "P") == {
        "increments": {"P_minus_H": [1.0], "A_minus_P": [2.0], "A_minus_H": [3.0]}}
    assert rename_native_roles(raw, "N") == {
        "increments": {"N_minus_H": [1.0], "A_minus_N": [2.0], "A_minus_H": [3.0]}}


def test_close_pair_writes_receipts_after_all_analysis(tmp_path, monkeypatch):
    baseline_root, capture_root = tmp_path / "baseline", tmp_path / "capture"
    for root in (baseline_root, capture_root):
        (root / "run").mkdir(parents=True)
        for name in ("receipt.json", "preflight.json", "launch_provenance.json"):
            (root / name).write_text("{}\n")
    shared = {"candidate_wrfinput_sha256": postclosure.A_INPUT_SHA256,
              "candidate_wrfbdy_sha256": postclosure.BOUNDARY_SHA256,
              "candidate_namelist_sha256": postclosure.NAMELIST_SHA256,
              "expected_model_timestamps": ["t0", "t1"],
              "launch_environment": {}, "candidate_build": {}}
    overlay = tmp_path / "overlay.json"
    overlay.write_text(json.dumps({"executable_sha256": "diag"}))
    baseline_build, diagnostic_build = tmp_path / "base-build.json", tmp_path / "diag-build.json"
    baseline_build.write_text("{}\n")
    diagnostic_build.write_text(json.dumps({
        "diagnostic_build_receipt_sha256": postclosure.DIAGNOSTIC_BUILD_SHA256,
        "schema": "pr102_c2_native_capture_build_v1", "status": "PASS_C2_CAPTURE_OVERLAY",
        "base_c2_executable_sha256": postclosure.BASE_C2_SHA256,
        "executable_sha256": postclosure.DIAGNOSTIC_SHA256}))
    base_receipt = dict(shared, candidate_build={"receipt_sha256": postclosure.BASE_BUILD_SHA256,
                                                  "receipt_path": str(baseline_build)})
    diag_receipt = dict(shared, candidate_build={"receipt_sha256": postclosure.DIAGNOSTIC_BUILD_SHA256,
                                                  "receipt_path": str(overlay)},
                        diagnostic_build_receipt_sha256=postclosure.CAPTURE_BUILD_SHA256,
                        diagnostic_executable_sha256=postclosure.DIAGNOSTIC_SHA256)
    monkeypatch.setattr(postclosure, "run_receipt", lambda root, control: base_receipt if control else diag_receipt)
    (diagnostic_build).write_text(json.dumps({
        "diagnostic_build_receipt_sha256": postclosure.DIAGNOSTIC_BUILD_SHA256,
        "schema": "pr102_c2_native_capture_build_v1", "status": "PASS_C2_CAPTURE_OVERLAY",
        "base_c2_executable_sha256": postclosure.BASE_C2_SHA256,
        "executable_sha256": postclosure.DIAGNOSTIC_SHA256}))
    # The pinned build's embedded overlay digest must match the actual overlay.
    build_data = json.loads(diagnostic_build.read_text())
    build_data["diagnostic_build_receipt_sha256"] = postclosure.capture.sha256(overlay)
    build_data["executable_sha256"] = "diag"
    diagnostic_build.write_text(json.dumps(build_data))
    monkeypatch.setattr(postclosure, "CAPTURE_BUILD_PATH", diagnostic_build)
    monkeypatch.setattr(postclosure, "CAPTURE_BUILD_SHA256", postclosure.capture.sha256(diagnostic_build))
    monkeypatch.setattr(postclosure, "DIAGNOSTIC_BUILD_SHA256", postclosure.capture.sha256(overlay))
    monkeypatch.setattr(postclosure, "DIAGNOSTIC_SHA256", "diag")
    monkeypatch.setattr(postclosure, "closed_run_artifacts", lambda root, receipt: [postclosure.pin(root / n)
                  for n in ("receipt.json", "preflight.json", "launch_provenance.json")])
    srcdir = tmp_path / "diag_sources"
    srcdir.mkdir()
    source_rows = []
    for index in range(57):
        item = srcdir / f"pr98_{index:02}.bin"
        item.write_bytes(b"x")
        source_rows.append(postclosure.pin(item))
    monkeypatch.setattr(postclosure.capture, "receipt_bound_source_outputs", lambda root, receipt: source_rows)
    control_file, diagnostic_file, trace = (tmp_path / n for n in ("control.nc", "diagnostic.nc", "trace.gz"))
    for path in (control_file, diagnostic_file, trace):
        path.write_bytes(b"x")
    monkeypatch.setattr(postclosure.capture, "compare_t0", lambda *args: {
        "fields": {str(n): {"equal": True} for n in range(30)},
        "control_file": postclosure.pin(control_file), "diagnostic_file": postclosure.pin(diagnostic_file)})
    monkeypatch.setattr(postclosure.capture, "compare_first20", lambda *args: {"equal": True})
    monkeypatch.setattr(postclosure.capture, "compare_t1_post", lambda *args: {
        "fields": {str(n): {"equal": True} for n in range(18)},
        "control_compressed": postclosure.pin(trace), "diagnostic_compressed": postclosure.pin(trace)})
    monkeypatch.setattr(postclosure.capture, "verify_output", lambda *args, **kwargs: trace)
    capture_roots = {}
    for label in ("h", "p", "n"):
        path = tmp_path / f"{label}.json"
        path.write_text("{}\n")
        root = tmp_path / f"{label}_sources"
        root.mkdir()
        files = []
        for index in range(57):
            item = root / f"pr98_{index:02}.bin"
            item.write_bytes(b"x")
            files.append(postclosure.pin(item))
        capture_roots[path] = (root, {"artifacts": files})
    monkeypatch.setattr(postclosure, "source_root", lambda path, expected: capture_roots[path])
    monkeypatch.setattr(postclosure, "loaded_local_sources", lambda: [postclosure.pin(Path(__file__))])
    def native_report(*args):
        assert isinstance(args[-1], dict)
        return {"status": "DESCRIPTIVE_ONLY", "source_capture_receipts": {"A": {}}}
    monkeypatch.setattr(postclosure, "first_native_response", native_report)
    out = tmp_path / "out"
    result = postclosure.close_pair(baseline_root, capture_root, out,
                                    hydro_capture=tmp_path / "h.json",
                                    projected_capture=tmp_path / "p.json",
                                    structured_capture=tmp_path / "n.json")
    assert result["status"] == "PASS_CAPTURE_NONINTERFERENCE"
    source_receipt = json.loads((out / "amplitude_source_capture.json").read_text())
    native = json.loads((out / "first_native_response.json").read_text())
    assert native["source_capture_receipts"]["A"]["sha256"] == postclosure.capture.sha256(
        out / "amplitude_source_capture.json")
