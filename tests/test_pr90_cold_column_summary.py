from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr89_cold_process_summary import SUMMARY_HEADER, parse_summary  # noqa: E402
from pr90_cold_column_summary import (  # noqa: E402
    HEADER, TAG, ColumnSummaryError, LAUNCH_REQUEST_SHA256, SOURCE_SHA256, add_column_summary,
    _area_weight_columns, area_weighted_totals, parse_column_summary,
)

SOURCE = Path("/var/tmp/pr89_sources_20261019_c1/module_mp_kdm6.F")


def _extract(source: str, start: str, end: str) -> str:
    return source[source.index(start):source.index(end, source.index(start))]


def _dedent(block: str) -> str:
    return "\n".join(line[12:] if line.startswith("            ") else line
                     for line in block.splitlines())


def _fixture_source() -> str:
    original = SOURCE.read_text(encoding="utf-8")
    assert hashlib.sha256(original.encode()).hexdigest() == SOURCE_SHA256
    source = add_column_summary(original)
    declarations = _extract(source,
        "   integer :: pr89_cold_unit,pr89_cold_ios,pr89_cold_transactions\n",
        "   integer                            :: pr87_reason_unit,pr87_reason_ios\n")
    init = "  pr89_cold_water=0.0d0\n  pr89_cold_transactions=0\n  pr90_cold_water=0.0d0\n  pr90_cold_transactions=0\n"
    collector = _extract(source, "            ! PR89: same-call column water measure",
                         "            if (.false.) then")
    alpha = _extract(source, "              rain_ng_alpha=rain_ng_alpha_initial*rain_composite_gamma\n",
                     "              rain_composite_rate_index=0\n")
    writer = _extract(source, "   write(pr89_cold_unit,'(a,6i10,1p,*(1x,e24.16))'",
                      "   if (pr67_trace_this_call) then\n     close(pr85_psd_unit")
    old_header = "\n".join("    '" + SUMMARY_HEADER[i:i+65] + "'// &"
                           for i in range(0, len(SUMMARY_HEADER), 65))[:-4]
    return f'''program pr90_cold_fixture
  implicit none
  integer, parameter :: its=1,ite=2
  integer :: i,k,pr87_model_timestep,lat,loops
{declarations.rstrip()}
  real :: dry_carrier_density(2,1),delz(2,1)
  real :: rain_ng_q_process(5),rain_aut_q_process(5),rain_q_process_request(5)
  real :: rain_ng_qv_process,rain_aut_qv_process,rain_g_qv_process
  real :: rain_ng_alpha,rain_aut_alpha,rain_process_alpha
  real :: rain_ng_alpha_initial,rain_aut_alpha_initial,rain_g_alpha_initial,rain_composite_gamma
  real :: rain_g_alpha
  integer :: rain_composite_rate_index
  pr87_model_timestep=10; lat=4; loops=1
  open(newunit=pr89_cold_unit,file='pr89_kdm6_cold_summary.raw',status='replace')
''' + f'''{init}
  write(pr89_cold_unit,'(a)') &
{old_header}
  do i=its,ite
    k=1; dry_carrier_density(i,k)=2.0; delz(i,k)=3.0
    rain_ng_q_process=0.0; rain_ng_qv_process=0.0
    rain_aut_q_process=0.0; rain_aut_qv_process=0.0
    rain_q_process_request=0.0; rain_g_qv_process=0.0
    rain_ng_alpha_initial=0.8; rain_aut_alpha_initial=0.5; rain_g_alpha_initial=0.6
    rain_composite_gamma=0.5
{_dedent(alpha).rstrip()}\n    if (i.eq.1) then
      rain_ng_q_process=[-2.0,1.0,0.0,0.0,0.0]
      rain_ng_qv_process=0.5
    else
      rain_ng_q_process=[-1.0,0.0,0.0,0.0,0.0]
      rain_ng_qv_process=0.0
    endif
{_dedent(collector).rstrip()}\n  enddo
{_dedent(writer).rstrip()}\n  close(pr89_cold_unit)
end program pr90_cold_fixture
'''


def test_transform_is_hash_bound_and_keeps_original_summary() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    transformed = add_column_summary(source)
    assert transformed.count("'PR89_KDM6_COLD_SUMMARY'") == 1
    assert "pr89_cold_water(1,pr89_cold_stage,pr89_cold_group)= &" in transformed
    assert "pr90_cold_water(1,pr89_cold_stage,pr89_cold_group,i)= &" in transformed
    assert "pr90_cold_transactions(i)=pr90_cold_transactions(i)+1" in transformed
    with pytest.raises(ColumnSummaryError, match="unexpected KDM6 source hash"):
        add_column_summary(source, "0" * 64)


def test_source_form_column_collector_under_pinned_intel() -> None:
    source = _fixture_source()
    with tempfile.TemporaryDirectory(prefix="pr90_cold_column_", dir="/var/tmp") as scratch:
        root = Path(scratch)
        source_file = root / "fixture.F90"
        source_file.write_text(source, encoding="utf-8")
        results = []
        for opt in ("O0", "O2"):
            build = root / opt
            build.mkdir()
            executable = build / "fixture"
            cmd = ["bash", "-c",
                'source "$1/tests/intel_toolchain.sh" && '
                'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                '"$CLOUD_BAL_FC" "${flags[@]}" "$3" -o "$4" && "$4"',
                "bash", str(ROOT), opt, str(source_file), str(executable)]
            run = subprocess.run(cmd, cwd=build, text=True, capture_output=True)
            assert run.returncode == 0, run.stdout + run.stderr
            results.append((parse_summary(build / "pr89_kdm6_cold_summary.raw"),
                            parse_column_summary(build / "pr90_kdm6_cold_column.raw")))
        for old, new in results:
            assert old["groups"]["NG"]["proposed"]["signed_kg_m2"] == pytest.approx(-9.0)
            assert [(r["i"], r["cell_transactions"]) for r in new["columns"]] == [(1, 1), (2, 1)]
            assert new["columns"][0]["groups"]["NG"]["proposed"]["signed_kg_m2"] == pytest.approx(-3.0)
            assert new["columns"][1]["groups"]["NG"]["proposed"]["signed_kg_m2"] == pytest.approx(-6.0)


def _row(i: int, signed: float) -> dict:
    groups = {g: {s: {"signed_kg_m2": 0.0, "half_l1_kg_m2": 0.0}
                  for s in ("proposed", "applied", "deferred")}
              for g in ("NG", "AUT", "G")}
    groups["NG"]["proposed"] = {"signed_kg_m2": signed, "half_l1_kg_m2": abs(signed)}
    return {"timestep": 1, "lat": 10, "i": i, "loops": 1,
            "cell_transactions": 1, "groups": groups}


def test_private_area_algebra_uses_varying_native_areas() -> None:
    np = __import__("numpy")
    rows = [_row(1, 1.0), _row(2, 2.0)]
    rows[0]["lat"] = 1
    rows[1]["lat"] = 1
    result = _area_weight_columns(rows, dx_m=10.0, dy_m=20.0,
        mapfac_mx=np.array([[1.0, 2.0]]), mapfac_my=np.array([[1.0, 2.0]]), nx=2, ny=1)
    assert result[1]["NG"]["proposed"]["signed_kg"] == pytest.approx(300.0)


def _stage_record(path: Path, *, wrong_bounds: bool = False) -> None:
    import struct
    nx, ny = (6, 4) if wrong_bounds else (5, 4)
    memory = (-4, 10, -4, 9, 1, 40)
    records = []
    for magic, kind, label, i_bounds, j_bounds in (
        (b"PR85PLB1", 2, "POST_PBL_TEND", (1, nx), (1, ny)),
        (b"PR85QND2", 1, "PRE_RK", (2, nx - 1), (2, ny - 1)),
    ):
        its, ite = i_bounds
        jts, jte = j_bounds
        fields = (kind, 1, 0, memory[0], memory[1], memory[2], memory[3],
                  memory[4], memory[5], its, ite, jts, jte, 1, 2)
        cells = (ite - its + 1) * (jte - jts + 1) * 2
        records.append(magic + label.encode().ljust(32, b" ") + struct.pack(">15i", *fields)
                       + b"\0" * (cells * 4 * (5 if kind == 2 else 12)))
    path.write_bytes(b"".join(records))


def _receipt_chain(tmp_path: Path, *, wrong_exe: bool = False,
                   broken_source: bool = False) -> tuple[Path, Path, Path, Path]:
    spec = importlib.util.spec_from_file_location(
        "pr89_history_fixture", ROOT / "tests/test_pr89_paired_history.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    history = tmp_path / "wrfout_d01.nc"
    fixture._history(history, 0.0, 0.0, records=2)
    source_path = tmp_path / "module_mp_kdm6.F"
    source = add_column_summary(SOURCE.read_text(encoding="utf-8"))
    if broken_source:
        source = source.replace("do j = jts,jte", "do j = jts,jte_broken")
    source_path.write_text(source, encoding="utf-8")
    executable = tmp_path / "wrf.exe"
    executable.write_bytes(b"candidate executable")
    build_path = tmp_path / "build.json"
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    build_path.write_text(json.dumps({"status": "PASS_OVERLAY_BUILD",
        "executable_path": str(executable), "executable_sha256": executable_hash,
        "source_overrides": {"module_mp_kdm6.o": {"requested_sha256": source_hash,
            "staged_sha256": source_hash, "staged_path": str(source_path)}}}), encoding="utf-8")
    stage = tmp_path / "pr85_joint_moment_stages.raw"
    _stage_record(stage)
    rsl = tmp_path / "rsl.out.0000"
    rsl.write_text("Ntasks in X 1, ntasks in Y 1\nWRF NUMBER OF TILES = 1\n")
    namelist = tmp_path / "namelist.input"
    namelist.write_text("&domains\n max_dom = 1,\n/\n")
    summary = tmp_path / "pr90_kdm6_cold_column.raw"
    rows = []
    values = [0.0] * 18
    values[0] = values[1] = 1.0
    for lat in (2, 3):
        for i in (2, 3, 4):
            rows.append(" ".join(map(str, [TAG, 1, lat, i, 1, 1, *values])))
    summary.write_text(HEADER + "\nPR90_KDM6_COLD_BLOCK 1 2 2 4\n" + "\n".join(rows[:3]) +
        "\n" + HEADER + "\nPR90_KDM6_COLD_BLOCK 1 3 2 4\n" +
        "\n".join(rows[3:]) + "\n", encoding="utf-8")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    expected = ["2026-08-16_13:00:20", "2026-08-16_13:00:40", "2026-08-16_13:01:00"]
    receipt_path = tmp_path / "run.json"
    build_hash = digest(build_path)
    candidate_namelist_sha = digest(namelist)
    launch_request_sha = LAUNCH_REQUEST_SHA256
    receipt_path.write_text(json.dumps({"status": "COMPLETE", "returncode": 0,
        "final_completed_step": 1,
        "expected_model_timestamps": expected,
        "model_timestamps": [{"timestamp": item} for item in expected],
        "executed_executable_sha256": "0" * 64 if wrong_exe else executable_hash,
        "candidate_build": {"receipt_path": str(build_path), "receipt_sha256": build_hash,
                            "executable_sha256": executable_hash},
        "candidate_namelist_sha256": candidate_namelist_sha,
        "launch_environment": {"status": "CONFIGURED_BY_RUNNER",
            "OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE",
            "launch_request_sha256": launch_request_sha},
        "execution_layout": {"status": "VERIFIED_SINGLE", "single_execution_layout": True,
            "domain_count": 1, "mpi_ranks": 1, "tiles_per_domain": 1, "threads": 1,
            "source_sha256": {"candidate_namelist": candidate_namelist_sha,
                "launch_request": launch_request_sha, "rsl_out_0000_payload": digest(rsl),
                "rsl_out_0000_artifact": digest(rsl)}},
        "generated_files": [{"path": path.name, "sha256": digest(path)}
                            for path in (history, stage, summary, namelist, rsl)]}), encoding="utf-8")
    return receipt_path, history, stage, summary


def test_public_area_join_is_cumulative_per_timestep(tmp_path: Path) -> None:
    receipt, history, stage, summary = _receipt_chain(tmp_path)
    result = area_weighted_totals(summary, run_receipt_path=receipt,
                                  history_path=history, stage_record_path=stage)
    assert result["status"] == "AREA_WEIGHTED_CUMULATIVE"
    assert result["units"] == "kg per model timestep over recorded KDM columns"
    assert result["by_timestep"][1]["NG"]["proposed"]["signed_kg"] == pytest.approx(36.0)
    assert result["by_timestep"][1]["NG"]["proposed"]["half_l1_kg"] == pytest.approx(36.0)
    assert result["coverage_by_timestep"][1] == {
        "status": "FULL", "completed": True, "expected_j": [2, 3], "seen_j": [2, 3],
        "missing_j": [], "expected_columns": 6, "observed_columns": 6}


def test_incomplete_run_marks_partial_spatial_coverage(tmp_path: Path) -> None:
    receipt, history, stage, summary = _receipt_chain(tmp_path)
    text = summary.read_text()
    text = text[:text.index("# PR90_KDM6_COLD_COLUMN", text.index("PR90_KDM6_COLD_COLUMN v1") + 1)]
    summary.write_text(text, encoding="utf-8")
    data = json.loads(receipt.read_text())
    data["status"] = "INCOMPLETE"
    data["returncode"] = 1
    data["final_completed_step"] = 0
    for item in data["generated_files"]:
        if item["path"] == summary.name:
            item["sha256"] = hashlib.sha256(summary.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(data), encoding="utf-8")
    result = area_weighted_totals(summary, run_receipt_path=receipt,
                                  history_path=history, stage_record_path=stage)
    coverage = result["coverage_by_timestep"][1]
    assert coverage["status"] == "PARTIAL"
    assert coverage["completed"] is False
    assert coverage["missing_j"] == [3]


@pytest.mark.parametrize("kwargs,match", [({"wrong_exe": True}, "candidate executable"),
    ({"broken_source": True}, "wrapper j loop")])
def test_area_join_rejects_bad_candidate_chain(tmp_path: Path, kwargs, match) -> None:
    receipt, history, stage, summary = _receipt_chain(tmp_path, **kwargs)
    with pytest.raises(ColumnSummaryError, match=match):
        area_weighted_totals(summary, run_receipt_path=receipt,
                              history_path=history, stage_record_path=stage)


@pytest.mark.parametrize("change", ["status", "single", "launch_hash", "rsl_hash"])
def test_area_join_rejects_unverified_execution_layout(tmp_path: Path, change: str) -> None:
    receipt, history, stage, summary = _receipt_chain(tmp_path)
    data = json.loads(receipt.read_text())
    layout = data["execution_layout"]
    if change == "status":
        layout["status"] = "UNKNOWN"
    elif change == "single":
        layout["single_execution_layout"] = None
    elif change == "launch_hash":
        layout["source_sha256"]["launch_request"] = "f" * 64
    else:
        layout["source_sha256"]["rsl_out_0000_payload"] = "f" * 64
    receipt.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ColumnSummaryError, match="execution layout"):
        area_weighted_totals(summary, run_receipt_path=receipt,
                             history_path=history, stage_record_path=stage)


def test_area_join_rejects_history_grid_mismatch_with_stage_bounds(tmp_path: Path) -> None:
    receipt, history, stage, summary = _receipt_chain(tmp_path)
    _stage_record(stage, wrong_bounds=True)
    data = json.loads(receipt.read_text())
    for item in data["generated_files"]:
        if item["path"] == stage.name:
            item["sha256"] = hashlib.sha256(stage.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(data), encoding="utf-8")
    # The trace's full physical i bound is 1..6, while the receipt-bound history
    # mass grid is 5 columns; no caller-provided mapping can reconcile them.
    with pytest.raises(ColumnSummaryError, match="full physical bounds"):
        area_weighted_totals(summary, run_receipt_path=receipt,
                             history_path=history, stage_record_path=stage)


def test_old_header_and_gzip_are_supported(tmp_path: Path) -> None:
    row = _row(3, 0.5)
    values = [row["groups"][g][s][m] for g in ("NG", "AUT", "G")
              for s in ("proposed", "applied", "deferred")
              for m in ("signed_kg_m2", "half_l1_kg_m2")]
    payload = (HEADER + "\n" + "PR90_KDM6_COLD_BLOCK 1 10 3 3\n"
               + " ".join(map(str, [TAG, 1, 10, 3, 1, 1, *values])) + "\n")
    path = tmp_path / "columns.raw.gz"
    path.write_bytes(gzip.compress(payload.encode()))
    assert parse_column_summary(path)["columns"][0]["i"] == 3


def test_parser_rejects_incomplete_active_i_block(tmp_path: Path) -> None:
    row = _row(3, 0.5)
    values = [row["groups"][g][s][m] for g in ("NG", "AUT", "G")
              for s in ("proposed", "applied", "deferred")
              for m in ("signed_kg_m2", "half_l1_kg_m2")]
    payload = (HEADER + "\nPR90_KDM6_COLD_BLOCK 1 10 3 4\n"
               + " ".join(map(str, [TAG, 1, 10, 3, 1, 1, *values])) + "\n")
    path = tmp_path / "partial.raw"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ColumnSummaryError, match="every active i"):
        parse_column_summary(path)


def test_parser_rejects_header_block_order_errors(tmp_path: Path) -> None:
    path = tmp_path / "order.raw"
    path.write_text(HEADER + "\n" + HEADER + "\n", encoding="utf-8")
    with pytest.raises(ColumnSummaryError, match="header is not followed"):
        parse_column_summary(path)
