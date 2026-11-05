import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (ROOT / "docs/evidence/cp02_grouped_forecast_20261105/runtime/compare_sham.py")
SPEC = importlib.util.spec_from_file_location("compare_sham", MODULE_PATH)
compare_sham = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare_sham)


def fixture_run(tmp_path, monkeypatch):
    folder = tmp_path / "SHAM_A"
    folder.mkdir()
    hashes = {f"input_{index}": f"{index:064x}" for index in range(88)}
    hashes["wrf.exe"] = compare_sham.OLD_EXE_SHA256
    monkeypatch.setattr(compare_sham, "source_hashes", lambda arm, root: hashes)
    names = compare_sham.HISTORY_NAMES
    baseline = {}
    for name in names:
        data = folder / name
        data.write_bytes(name.encode())
        valid_time = name.removeprefix("wrfout_d01_")
        baseline[name] = {"sha256": compare_sham.sha256(data), "valid_time": valid_time}
    monkeypatch.setattr(compare_sham, "history_baseline", lambda arm, root: baseline)
    monkeypatch.setattr(compare_sham, "check_history", lambda path, valid_time: {
        "name": path.name, "sha256": compare_sham.sha256(path), "size_bytes": path.stat().st_size,
        "valid_time": valid_time, "precip_fields": list(compare_sham.PRECIP_FIELDS)})
    build_path = tmp_path / "build.json"
    rebuilt_exe = "a18b5bcacf287531b5fb9366be0ff0e2fd13911c4f44b0a739ab9e565f678308"
    build = {"status": "PASS", "variant": "OLD_SHAM", "inputs_unchanged": True,
             "compile": {"exit_code": 0}, "link": {"exit_code": 0},
             "source": {"sha256": "d8c11bd9b3dd0fd717c14899c53ffe7ca37c4d768128c4dac750429f7fb4bf3a"},
             "object": {"sha256": compare_sham.OLD_TARGET_OBJECT_SHA256},
             "archive_member_sha256": compare_sham.OLD_TARGET_OBJECT_SHA256,
             "executable": {"sha256": rebuilt_exe}}
    build_path.write_text(json.dumps(build))
    staged = dict(hashes)
    staged["wrf.exe"] = rebuilt_exe
    prepared = {"case": "SHAM_A", "variant": "OLD_SHAM", "initial_time_utc": "2026-08-16T12:00:00Z",
                "end_time_utc": "2026-08-16T18:00:00Z", "source_hashes": hashes, "inputs": staged,
                "build_receipt": str(build_path), "build_receipt_sha256": compare_sham.sha256(build_path),
                "runner_sha256": compare_sham.sha256(MODULE_PATH.with_name("forecast.py")),
                "wrapper_sha256": compare_sham.sha256(MODULE_PATH.with_name("rank_wrapper.sh"))}
    (folder / "prepared.json").write_text(json.dumps(prepared))
    rows = [{"path": str(folder / name), "sha256": baseline[name]["sha256"],
             "size_bytes": (folder / name).stat().st_size,
             "valid_utc": baseline[name]["valid_time"].replace("_", "T") + "Z"} for name in names]
    run = {"schema": "cp02_grouped_six_hour_run_v1", "status": "PASS", "exit_code": 0, "failure": None,
           "case": "SHAM_A", "initialization": "A", "initial_time_utc": prepared["initial_time_utc"],
           "end_time_utc": prepared["end_time_utc"], "cpus": list(range(8)),
           "start_utc": "2026-11-05T12:00:00+00:00", "end_utc": "2026-11-05T12:10:00+00:00",
           "elapsed_seconds": 600, "runner_sha256": prepared["runner_sha256"],
           "inputs_after": staged, "histories": rows}
    (folder / "run_receipt.json").write_text(json.dumps(run))
    return folder, build_path


def test_verify_run_accepts_only_complete_exact_control(tmp_path, monkeypatch):
    folder, _ = fixture_run(tmp_path, monkeypatch)
    identity, details = compare_sham.verify_run("A", folder, ROOT)
    assert identity["sha256"]
    assert details["input_count"] == 89
    assert len(details["histories"]) == 7


def test_verify_run_rejects_changed_history_bytes(tmp_path, monkeypatch):
    folder, _ = fixture_run(tmp_path, monkeypatch)
    history = folder / compare_sham.HISTORY_NAMES[3]
    history.write_bytes(b"mutated")
    with pytest.raises(ValueError, match="bytes differ"):
        compare_sham.verify_run("A", folder, ROOT)


def test_verify_run_rejects_wrong_oldsum_executable(tmp_path, monkeypatch):
    folder, build_path = fixture_run(tmp_path, monkeypatch)
    build = json.loads(build_path.read_text())
    build["object"]["sha256"] = "0" * 64
    build_path.write_text(json.dumps(build))
    prepared = json.loads((folder / "prepared.json").read_text())
    prepared["build_receipt_sha256"] = compare_sham.sha256(build_path)
    (folder / "prepared.json").write_text(json.dumps(prepared))
    with pytest.raises(ValueError, match="target object differs"):
        compare_sham.verify_run("A", folder, ROOT)
