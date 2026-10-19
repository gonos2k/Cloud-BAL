from __future__ import annotations

import hashlib
import gzip
from pathlib import Path
import sys
import tempfile
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
V44_SOURCE = ROOT / "docs/evidence/pr87_followup_20261019/source/v44/module_mp_kdm6.F.gz"
V44_SHA256 = "769cf33f7e6d59d46e2b31ec973a7d44cecce0b505fc18b0890b5b2a4ef2464f"
sys.path.insert(0, str(ROOT / "tools"))

from pr89_cold_process_summary import (  # noqa: E402
    SUMMARY_HEADER,
    SummaryError,
    add_cold_summary,
    parse_summary,
    inspect_current_ledger,
)


def _summary_row(*, transactions: int = 2, raw_rows: int = 0) -> str:
    values = [float(i) for i in range(1, 19)]
    return " ".join([
        "PR89_KDM6_COLD_SUMMARY", "10", "4", "2", str(transactions),
        str(raw_rows), str(transactions - raw_rows), *map(str, values),
    ])


def _transformed_v44() -> str:
    source = gzip.decompress(V44_SOURCE.read_bytes()).decode()
    assert hashlib.sha256(source.encode()).hexdigest() == V44_SHA256
    return add_cold_summary(source, V44_SHA256)


def _extract(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def test_source_transform_is_hash_guarded_and_targets_actual_source_forms() -> None:
    source = gzip.decompress(V44_SOURCE.read_bytes()).decode()
    transformed = add_cold_summary(source, V44_SHA256)

    assert "pr89_cold_weight=DBLE(dry_carrier_density(i,k))*DBLE(delz(i,k))" in transformed
    assert "raw_cell_rows,unrecorded_transactions" in transformed
    assert "kg m-2 SUM_COLUMNS" in transformed
    assert "pr89_cold_water" in transformed
    with pytest.raises(SummaryError, match="unexpected KDM6 source hash"):
        add_cold_summary(source, "0" * 64)


def test_transformed_accumulator_and_writer_under_pinned_intel() -> None:
    source = _transformed_v44()
    declarations = _extract(
        source,
        "   integer :: pr89_cold_unit,pr89_cold_ios,pr89_cold_transactions\n",
        "   real(kind=8) :: pr89_cold_signed,pr89_cold_half_l1\n",
    ) + "   real(kind=8) :: pr89_cold_signed,pr89_cold_half_l1\n"
    init_end = "   if (pr89_cold_ios.ne.0) error stop 'PR89 cold summary header failed'\n"
    initialization = _extract(source, "   pr89_cold_water=0.0d0\n", init_end) + init_end
    collector = _extract(source, "            ! PR89: same-call column water measure", "            if (.false.) then")
    alpha_assignment = _extract(
        source,
        "              rain_ng_alpha=rain_ng_alpha_initial*rain_composite_gamma\n",
        "              rain_composite_rate_index=0\n",
    )
    writer_end = "   if (pr89_cold_ios.ne.0) error stop 'PR89 cold summary close failed'\n"
    writer = _extract(source, "   write(pr89_cold_unit,'(a,6i10,1p,*(1x,e24.16))'", writer_end) + writer_end
    dedented = lambda block: "\n".join(line[12:] if line.startswith("            ") else line
                                           for line in block.splitlines())
    fixture = f"""program pr89_cold_fixture
  implicit none
{declarations.rstrip()}
  integer :: i,k,pr87_model_timestep,lat,loops
  real :: dry_carrier_density(2,1),delz(2,1)
  real :: rain_ng_q_process(5),rain_aut_q_process(5),rain_q_process_request(5)
  real :: rain_ng_qv_process,rain_ng_alpha,rain_aut_alpha,rain_process_alpha
  real :: rain_g_qv_process,rain_g_alpha,rain_composite_gamma
  real :: rain_ng_alpha_initial,rain_aut_alpha_initial,rain_g_alpha_initial
  pr87_model_timestep=10; lat=4; loops=2
{dedented(initialization)}
  do i=1,2
    k=1
    dry_carrier_density(i,k)=2.0
    delz(i,k)=3.0
    rain_ng_q_process=0.0; rain_ng_qv_process=0.0
    rain_aut_q_process=0.0; rain_q_process_request=0.0; rain_g_qv_process=0.0
    rain_ng_alpha_initial=0.8
    rain_aut_alpha_initial=0.5
    rain_g_alpha_initial=0.6
    rain_composite_gamma=0.5
{dedented(alpha_assignment)}
    if (i.eq.1) then
      rain_ng_q_process=[-2.0,1.0,0.0,0.0,0.0]
      rain_ng_qv_process=0.5
      rain_aut_q_process=[-1.0,2.0,0.0,0.0,0.0]
      rain_q_process_request=[-3.0,0.0,0.0,0.0,1.0]
      rain_g_qv_process=-0.5
    endif
{dedented(collector)}
  enddo
{dedented(writer)}
end program pr89_cold_fixture
"""
    rows = []
    with tempfile.TemporaryDirectory(prefix="pr89_cold_summary_", dir="/var/tmp") as scratch:
        scratch_root = Path(scratch)
        source_file = scratch_root / "cold_summary_fixture.F90"
        source_file.write_text(fixture, encoding="utf-8")
        for optimization in ("O0", "O2"):
            build = scratch_root / optimization
            build.mkdir()
            executable = build / "cold_summary_fixture"
            command = [
                "bash", "-c",
                'source "$1/tests/intel_toolchain.sh" && '
                'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                '"$CLOUD_BAL_FC" "${flags[@]}" "$3" -o "$4" && "$4"',
                "bash", str(ROOT), optimization, str(source_file), str(executable),
            ]
            completed = subprocess.run(command, cwd=build, text=True, capture_output=True)
            assert completed.returncode == 0, completed.stdout + completed.stderr
            summary_file = build / "pr89_kdm6_cold_summary.raw"
            rows.append(parse_summary(summary_file))

    for result in rows:
        assert result["call_records"] == 1
        assert result["cell_transactions"] == 2
        assert result["raw_cell_rows"] == 0
        assert result["unrecorded_transactions"] == 2
        assert result["groups"]["NG"]["proposed"]["signed_kg_m2"] == pytest.approx(-3.0)
        assert result["groups"]["NG"]["proposed"]["half_l1_kg_m2"] == pytest.approx(10.5)
        assert result["groups"]["NG"]["applied"]["signed_kg_m2"] == pytest.approx(-1.2)
        assert result["groups"]["NG"]["applied"]["half_l1_kg_m2"] == pytest.approx(4.2)
        assert result["groups"]["NG"]["deferred"]["signed_kg_m2"] == pytest.approx(-1.8)
        assert result["groups"]["NG"]["deferred"]["half_l1_kg_m2"] == pytest.approx(6.3)
        assert result["groups"]["AUT"]["proposed"]["signed_kg_m2"] == pytest.approx(6.0)
        assert result["groups"]["AUT"]["proposed"]["half_l1_kg_m2"] == pytest.approx(9.0)
        assert result["groups"]["AUT"]["applied"]["signed_kg_m2"] == pytest.approx(1.5)
        assert result["groups"]["AUT"]["applied"]["half_l1_kg_m2"] == pytest.approx(2.25)
        assert result["groups"]["AUT"]["deferred"]["signed_kg_m2"] == pytest.approx(4.5)
        assert result["groups"]["AUT"]["deferred"]["half_l1_kg_m2"] == pytest.approx(6.75)
        assert result["groups"]["G"]["proposed"]["signed_kg_m2"] == pytest.approx(-15.0)
        assert result["groups"]["G"]["proposed"]["half_l1_kg_m2"] == pytest.approx(13.5)
        assert result["groups"]["G"]["applied"]["signed_kg_m2"] == pytest.approx(-4.5)
        assert result["groups"]["G"]["applied"]["half_l1_kg_m2"] == pytest.approx(4.05)
        assert result["groups"]["G"]["deferred"]["signed_kg_m2"] == pytest.approx(-10.5)
        assert result["groups"]["G"]["deferred"]["half_l1_kg_m2"] == pytest.approx(9.45)


def test_header_only_current_ledger_is_not_evaluated(tmp_path: Path) -> None:
    ledger = tmp_path / "pr85_kdm6_cold_budget.raw"
    ledger.write_text(
        "# PR85_KDM6_COLD fields: i,lat,k,loop; current source header only\n",
        encoding="utf-8",
    )

    result = inspect_current_ledger(ledger)

    assert result["status"] == "NOT_EVALUATED"
    assert result["ledger_header_records"] == 1
    assert result["ledger_data_records"] == 0
    assert result["call_records"] == 0


def test_summary_reports_calls_counts_and_group_metrics(tmp_path: Path) -> None:
    path = tmp_path / "pr89_kdm6_cold_summary.raw"
    path.write_text(
        SUMMARY_HEADER + "\n"
        + _summary_row() + "\n",
        encoding="utf-8",
    )

    result = parse_summary(path)

    assert result["status"] == "EVALUATED"
    assert result["call_records"] == 1
    assert result["timesteps"] == [10]
    assert result["cell_transactions"] == 2
    assert result["raw_cell_rows"] == 0
    assert result["unrecorded_transactions"] == 2
    assert result["groups"]["NG"]["proposed"]["signed_kg_m2"] == 1.0
    assert result["groups"]["NG"]["proposed"]["half_l1_kg_m2"] == 2.0
    assert result["weight_units"] == "kg m-2 SUM_COLUMNS; no grid-area/global kg"


def test_gzip_summary_and_legacy_ledger_roundtrip(tmp_path: Path) -> None:
    summary = tmp_path / "pr89_kdm6_cold_summary.raw.gz"
    summary.write_bytes(gzip.compress((SUMMARY_HEADER + "\n" + _summary_row() + "\n").encode()))
    parsed_summary = parse_summary(summary)
    assert parsed_summary["call_records"] == 1
    assert parsed_summary["cell_transactions"] == 2

    ledger = tmp_path / "pr85_kdm6_cold_budget.raw.gz"
    ledger.write_bytes(gzip.compress(
        b"# PR85_KDM6_COLD fields: current schema\n"))
    parsed_ledger = inspect_current_ledger(ledger)
    assert parsed_ledger["status"] == "NOT_EVALUATED"
    assert parsed_ledger["ledger_header_records"] == 1


def test_summary_rejects_inconsistent_unrecorded_count(tmp_path: Path) -> None:
    path = tmp_path / "pr89_kdm6_cold_summary.raw"
    fields = _summary_row().split()
    fields[6] = "0"
    path.write_text(
        SUMMARY_HEADER + "\n"
        + " ".join(fields) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SummaryError, match="row and unrecorded counts disagree"):
        parse_summary(path)


def test_summary_rejects_header_without_its_call_row(tmp_path: Path) -> None:
    path = tmp_path / "pr89_kdm6_cold_summary.raw"
    path.write_text(SUMMARY_HEADER + "\n", encoding="utf-8")

    with pytest.raises(SummaryError, match="header/data record counts disagree"):
        parse_summary(path)


def test_summary_rejects_truncated_gzip_stream(tmp_path: Path) -> None:
    path = tmp_path / "pr89_kdm6_cold_summary.raw.gz"
    payload = SUMMARY_HEADER + "\n" + _summary_row() + "\n"
    path.write_bytes(gzip.compress(payload.encode())[:-8])

    with pytest.raises(SummaryError, match="cannot read summary text"):
        parse_summary(path)


def test_current_cell_rows_are_counted_without_replaying_historical_data(tmp_path: Path) -> None:
    ledger = tmp_path / "pr85_kdm6_cold_budget.raw"
    numeric = " ".join("0" for _ in range(207))
    ledger.write_text(
        "# PR85_KDM6_COLD fields: current schema\n"
        f"PR85_KDM6_COLD 1 2 3 1 0 0 0 0 F {numeric}\n",
        encoding="utf-8",
    )

    result = inspect_current_ledger(ledger)

    assert result["status"] == "CELL_RECORDS_PRESENT"
    assert result["ledger_header_records"] == 1
    assert result["ledger_data_records"] == 1
