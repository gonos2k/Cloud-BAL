import json
import math
import os
import struct
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "docs/evidence/cp02_kdm6_controls_20261029/capture_kdm6.gdb"
SELECTION = ROOT / "docs/evidence/cp02_wrf_first_call_20261029/capture/selection.json"


class FakeBreakpoint:
    def __init__(self, *args, **kwargs):
        pass


class FakeInferior:
    pid = 4321

    def read_memory(self, address, count):
        return struct.pack("=f", float("nan"))[:count]


def load_capture_namespace(monkeypatch, tmp_path, *, ranks=8, wait_seconds="0.05"):
    monkeypatch.setenv("CP02_CAPTURE_DIR", str(tmp_path))
    monkeypatch.setenv("CP02_SELECTION_JSON", str(SELECTION))
    monkeypatch.setenv("CP02_EXPECT_RANKS", str(ranks))
    monkeypatch.setenv("CP02_PEER_WAIT_SECONDS", wait_seconds)
    monkeypatch.setenv("PMI_RANK", "0")

    fake_gdb = types.ModuleType("gdb")
    fake_gdb.Breakpoint = FakeBreakpoint
    fake_gdb.error = RuntimeError
    fake_gdb.selected_inferior = lambda: FakeInferior()
    fake_gdb.parse_and_eval = lambda expression: 0x1234
    fake_gdb.execute = lambda *args, **kwargs: "fake backtrace"
    monkeypatch.setitem(sys.modules, "gdb", fake_gdb)

    source = HELPER.read_text(encoding="utf-8")
    python_block = source.split("\npython\n", 1)[1].split("\nend\n", 1)[0]
    namespace = {"__name__": "capture_kdm6_test"}
    exec(compile(python_block, str(HELPER), "exec"), namespace)
    namespace["OUT"] = str(tmp_path)
    namespace["state"].update({
        "rank": "0",
        "pid": 4321,
        "path": str(tmp_path / "capture_rank0_pid4321.json"),
        "record": {"rank": "0", "pid": 4321, "status": "call_1_returned", "calls": []},
    })
    return namespace


def completed_envelope(rank):
    return {
        "rank": str(rank),
        "pid": 5000 + rank,
        "status": "two_calls_returned",
        "calls": [
            {"entry": {"call_number": 1}, "return": {"pc": "0x20c3722"}},
            {"entry": {"call_number": 2}, "return": {"pc": "0x20c3722"}},
        ],
    }


def test_peer_gate_succeeds_only_after_all_eight_two_call_envelopes(monkeypatch, tmp_path):
    namespace = load_capture_namespace(monkeypatch, tmp_path)
    for rank in range(8):
        path = tmp_path / f"capture_rank{rank}_pid{5000 + rank}.json"
        path.write_text(json.dumps(completed_envelope(rank)), encoding="utf-8")

    assert namespace["peer_wait_two_calls"]() is True
    assert not list(tmp_path.glob("*.failed.json"))


def test_peer_failure_marker_fails_local_gate_and_records_failure(monkeypatch, tmp_path):
    namespace = load_capture_namespace(monkeypatch, tmp_path, ranks=2)
    (tmp_path / "capture_rank0_pid5000.json").write_text(
        json.dumps(completed_envelope(0)), encoding="utf-8"
    )
    (tmp_path / "capture_rank1_pid5001.failed.json").write_text(
        json.dumps({"status": "failed_entry", "rank": "1"}), encoding="utf-8"
    )

    assert namespace["peer_wait_two_calls"]() is False
    assert namespace["state"]["record"]["status"] == "failed_peer_capture"
    local_failure = json.loads((tmp_path / "capture_rank0_pid4321.failed.json").read_text())
    assert local_failure["status"] == "failed_peer_capture"


def test_peer_timeout_fails_gate_and_writes_explicit_marker(monkeypatch, tmp_path):
    namespace = load_capture_namespace(monkeypatch, tmp_path, ranks=2, wait_seconds="0.01")
    (tmp_path / "capture_rank0_pid5000.json").write_text(
        json.dumps(completed_envelope(0)), encoding="utf-8"
    )

    assert namespace["peer_wait_two_calls"]() is False
    assert namespace["state"]["record"]["status"] == "failed_peer_wait_timeout"
    local_failure = json.loads((tmp_path / "capture_rank0_pid4321.failed.json").read_text())
    assert local_failure["status"] == "failed_peer_wait_timeout"
    assert "missing_or_incomplete_ranks=1" in local_failure["error"]


def test_nonfinite_array_keeps_raw_bytes_and_serializes_strict_json(monkeypatch, tmp_path):
    namespace = load_capture_namespace(monkeypatch, tmp_path)
    sample = namespace["array_value"](
        0x1000, 0, 0, 0, (0, 0, 0, 0, 0, 0), is_3d=True
    )

    assert sample["raw_hex"] == struct.pack("=f", math.nan).hex()
    assert sample["value_f32"] is None
    assert sample["finite"] is False
    output = tmp_path / "nonfinite.json"
    namespace["atomic_json"](str(output), sample)
    assert json.loads(output.read_text()) == sample
    assert '"value_f32": null' in output.read_text()
