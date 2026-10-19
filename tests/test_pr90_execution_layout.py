from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr86_time_response as runner  # noqa: E402


def _preflight(stage: Path, *, max_dom: int = 1, launch: bool = True) -> dict:
    namelist = stage / "namelist.input"
    namelist.write_text(f"&domains\n max_dom = {max_dom},\n/\n", encoding="utf-8")
    result = {"candidate_namelist_sha256": runner.sha256(namelist)}
    if launch:
        result["launch_environment"] = {
            **runner.LAUNCH_ENVIRONMENT, "status": "CONFIGURED_BY_RUNNER",
            "launch_request_sha256": runner.LAUNCH_ENVIRONMENT_SHA256}
    return result


def _receipt_for(path: Path) -> dict:
    return {"generated_files": [{"path": path.name, "sha256": runner.sha256(path)}]}


def _layout(tmp_path: Path, rsl: str, *, max_dom: int = 1,
            launch: bool = True) -> dict:
    stage = tmp_path / "run"
    stage.mkdir()
    preflight = _preflight(stage, max_dom=max_dom, launch=launch)
    path = stage / "rsl.out.0000"
    path.write_text(rsl, encoding="utf-8")
    return runner._execution_layout(preflight, stage, _receipt_for(path))


def _rsl(tasks_x: int = 1, tasks_y: int = 1, tiles: int = 1) -> str:
    return (f" Ntasks in X {tasks_x} , ntasks in Y {tasks_y}\n"
            f" WRF NUMBER OF TILES = {tiles}\n")


def test_single_execution_layout_is_bound_to_namelist_launch_and_rsl(tmp_path: Path) -> None:
    result = _layout(tmp_path, _rsl())
    assert result["status"] == "VERIFIED_SINGLE"
    assert result["single_execution_layout"] is True
    assert (result["domain_count"], result["mpi_rank_count"], result["tiles_per_domain"],
            result["configured_omp_threads"], result["mpi_ranks"], result["threads"]) == (1, 1, 1, 1, 1, 1)
    assert set(result["source_sha256"]) == {
        "candidate_namelist", "launch_request", "rsl_out_0000_payload", "rsl_out_0000_artifact"}


@pytest.mark.parametrize("rsl", ["", _rsl() + " Ntasks in X 2 , ntasks in Y 1\n"])
def test_absent_or_contradictory_rsl_layout_is_unknown(tmp_path: Path, rsl: str) -> None:
    result = _layout(tmp_path, rsl)
    assert result["status"] == "UNKNOWN"
    assert result["single_execution_layout"] is None


@pytest.mark.parametrize("tasks_x,tasks_y,tiles", [(2, 1, 1), (1, 1, 4)])
def test_multiple_ranks_or_tiles_cannot_claim_single_layout(
        tmp_path: Path, tasks_x: int, tasks_y: int, tiles: int) -> None:
    result = _layout(tmp_path, _rsl(tasks_x, tasks_y, tiles))
    assert result["status"] == "KNOWN_MULTIPLE"
    assert result["single_execution_layout"] is False


def test_unsupported_multidomain_namelist_is_unknown(tmp_path: Path) -> None:
    result = _layout(tmp_path, _rsl(), max_dom=2)
    assert result["status"] == "UNKNOWN"
    assert result["single_execution_layout"] is None
    assert "max_dom=2" in result["reason"]


def test_old_preflight_without_launch_environment_is_unknown(tmp_path: Path) -> None:
    result = _layout(tmp_path, _rsl(), launch=False)
    assert result["status"] == "UNKNOWN"
    assert result["single_execution_layout"] is None
    assert "launch request" in result["reason"]


def test_gzip_rsl_is_parsed_and_payload_hash_is_reported(tmp_path: Path) -> None:
    import gzip

    stage = tmp_path / "run"
    stage.mkdir()
    preflight = _preflight(stage)
    payload = _rsl().encode()
    path = stage / "rsl.out.0000.gz"
    path.write_bytes(gzip.compress(payload))
    receipt = {"compressed_outputs": [{"compressed_path": path.name,
        "compressed_sha256": runner.sha256(path),
        "sha256": hashlib.sha256(payload).hexdigest()}]}
    result = runner._execution_layout(preflight, stage, receipt)
    assert result["status"] == "VERIFIED_SINGLE"
    assert result["source_sha256"]["rsl_out_0000_payload"] == hashlib.sha256(payload).hexdigest()
