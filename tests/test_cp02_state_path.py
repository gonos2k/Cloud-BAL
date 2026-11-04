from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/cp02_state_path.py"
EXPECTED_RANK_FIXTURE = Path(__file__).resolve().parent / "fixtures/cp02_state_path/expected_rank_manifest.json"
SPEC = importlib.util.spec_from_file_location("cp02_state_path", SCRIPT)
reader = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = reader
SPEC.loader.exec_module(reader)


def call(step=1, rank=0, call_id=1, *, ilo=1, ihi=2, jlo=1, jhi=1, klo=1, khi=1):
    return reader.Call(step, rank, call_id, ilo, ihi + 1, jlo, jhi + 1, klo, khi,
                       ilo, ihi + 1, jlo, jhi + 1, klo, khi, ilo, ihi, jlo, jhi, klo, khi)


def pack_header(stage, *, rank=0, call_id=1, timestep=1, bounds=(1, 2, 1, 1, 1, 1), fields=1, records=2):
    return reader.HEADER.pack(reader.MAGIC, stage, rank, call_id, timestep, *bounds, 1, 1, 1, fields, records)


def write_call_inventory(root: Path, count=360):
    path = root / "state_calls_rank0.txt"
    row = [1, 0, 1, 1, 3, 1, 2, 1, 2, 1, 3, 1, 2, 1, 2, 1, 2, 1, 1, 1, 1]
    with path.open("w", encoding="ascii") as stream:
        for timestep in range(1, count + 1):
            stream.write(" ".join(map(str, [timestep, *row[1:]])) + " \n")
    for rank in range(1, 8):
        (root / f"state_calls_rank{rank}.txt").write_text("", encoding="ascii")
    return path


def test_header_is_big_endian_and_rejects_bad_magic_or_truncation(tmp_path):
    raw = pack_header(1)
    header = reader.BlockHeader.unpack(raw, tmp_path / "state_entry_rank0.bin", 0)
    assert (header.stage_id, header.rank, header.record_count) == (1, 0, 2)
    assert raw[8:12] == struct.pack(">i", 1)
    assert reader._float_word(np.float32(0.0)) == "0x00000000"
    assert reader._float_word(np.float32(-0.0)) == "0x80000000"
    with pytest.raises(reader.StatePathError, match="invalid CBSP magic"):
        reader.BlockHeader.unpack(b"NOTCBSP!" + raw[8:], tmp_path / "bad.bin", 0)
    with pytest.raises(reader.StatePathError, match="truncated block header"):
        reader.BlockHeader.unpack(raw[:-1], tmp_path / "short.bin", 0)


def test_schema_rejects_wrong_endian_encoding(tmp_path):
    source = json.loads(reader.DEFAULT_SCHEMA.read_text())
    source["encoding"] = "little-endian Intel stream"
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(source))
    with pytest.raises(reader.StatePathError, match="big_endian"):
        reader.load_schema(path)


def test_frozen_schema_and_cohort_pins_reject_changed_labels_or_weights(tmp_path):
    reader.validate_frozen_source_pins(reader.DEFAULT_SCHEMA, reader.DEFAULT_CORNERS)
    wrong_corners = tmp_path / "wrong_weights.csv"
    corner_text = reader.DEFAULT_CORNERS.read_text(encoding="utf-8")
    wrong_corners.write_text(corner_text.replace("0.24629397354739388", "0.24629397354739390", 1), encoding="utf-8")
    with pytest.raises(reader.StatePathError, match="corners SHA-256"):
        reader.validate_frozen_source_pins(reader.DEFAULT_SCHEMA, wrong_corners)

    wrong_schema = tmp_path / "wrong_fields.json"
    schema_text = reader.DEFAULT_SCHEMA.read_text(encoding="utf-8")
    wrong_schema.write_text(schema_text.replace("TH_PUBLIC_RAW", "TH_PUBLIC_ALT", 1), encoding="utf-8")
    with pytest.raises(reader.StatePathError, match="schema SHA-256"):
        reader.validate_frozen_source_pins(wrong_schema, reader.DEFAULT_CORNERS)


def test_real_pinned_expected_rank_manifest_fixture():
    assert EXPECTED_RANK_FIXTURE.stat().st_size == 660
    assert reader.sha256(EXPECTED_RANK_FIXTURE) == reader.EXPECTED_RANK_MANIFEST_SHA256
    manifest = json.loads(EXPECTED_RANK_FIXTURE.read_text(encoding="utf-8"))
    assert manifest["format"] == "CBSP_EXPECTED_RANKS_v1"
    assert manifest["mpi_ranks"] == 8
    assert manifest["expected_rank_ids"] == list(range(8))


def test_text_call_inventory_requires_exact_21_integers_and_full_steps(tmp_path):
    write_call_inventory(tmp_path, count=360)
    calls = reader.read_call_inventory(tmp_path)
    assert len(calls) == 360
    assert calls[(360, 0, 1)].core == (1, 2, 1, 1, 1, 1)

    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "state_calls_rank0.txt").write_text("1 0 1 2\n")
    for rank in range(1, 8):
        (bad / f"state_calls_rank{rank}.txt").write_text("")
    with pytest.raises(reader.StatePathError, match="expected 21"):
        reader.read_call_inventory(bad)

    missing_rank = tmp_path / "missing_rank"
    missing_rank.mkdir()
    for rank in range(7):
        (missing_rank / f"state_calls_rank{rank}.txt").write_text("", encoding="ascii")
    with pytest.raises(reader.StatePathError, match="rank inventory"):
        reader.read_call_inventory(missing_rank)

    missing = tmp_path / "missing"
    missing.mkdir()
    write_call_inventory(missing, count=359)
    with pytest.raises(reader.StatePathError, match="timestep coverage"):
        reader.read_call_inventory(missing)

    quick = tmp_path / "quick"
    quick.mkdir()
    write_call_inventory(quick, count=1)
    calls = reader.read_call_inventory(quick, expected_timesteps=(1,))
    assert set(calls) == {(1, 0, 1)}

    halo = tmp_path / "halo"
    halo.mkdir()
    halo_row = [1, 0, 1, 1, 3, 1, 2, 1, 2, -4, 4, -3, 3, 1, 2, 1, 2, 1, 1, 1, 1]
    (halo / "state_calls_rank0.txt").write_text(" ".join(map(str, halo_row)) + "\n", encoding="ascii")
    for rank in range(1, 8):
        (halo / f"state_calls_rank{rank}.txt").write_text("", encoding="ascii")
    halo_calls = reader.read_call_inventory(halo, expected_timesteps=(1,))
    assert halo_calls[(1, 0, 1)].ims == -4 and halo_calls[(1, 0, 1)].jms == -3

    partition = tmp_path / "partition"
    partition.mkdir()
    partition_row = [1, 0, 1, 1, 236, 1, 283, 1, 40, 111, 240, 1, 283, 1, 40,
                     118, 233, 1, 1, 1, 1]
    (partition / "state_calls_rank0.txt").write_text(" ".join(map(str, partition_row)) + "\n", encoding="ascii")
    for rank in range(1, 8):
        (partition / f"state_calls_rank{rank}.txt").write_text("", encoding="ascii")
    partition_calls = reader.read_call_inventory(partition, expected_timesteps=(1,))
    assert partition_calls[(1, 0, 1)].core[:2] == (118, 233)


def test_global_stage_detects_truncated_payload_and_missing_block(tmp_path):
    root = tmp_path / "OLD"
    root.mkdir()
    inventory = {(1, 0, 1): call()}
    spec = reader.StageSpec(1, "entry", ("X",), False)
    selected = []
    path = root / "state_entry_rank0.bin"
    path.write_bytes(pack_header(1) + np.array([1.0], dtype=">f4").tobytes())
    with pytest.raises(reader.StatePathError, match="truncated entry payload"):
        reader.read_global_stage(root, spec, inventory, selected, (1, 2, 1), tmp_path / "work1")

    path.write_bytes(b"")
    with pytest.raises(reader.StatePathError, match="block inventory mismatch"):
        reader.read_global_stage(root, spec, inventory, selected, (1, 2, 1), tmp_path / "work2")

    values = np.array([1.25, -2.5], dtype=">f4")
    path.write_bytes(pack_header(1) + values.tobytes())
    data, mask, owners, info = reader.read_global_stage(root, spec, inventory, selected, (1, 2, 1), tmp_path / "work3")
    assert mask.tolist() == [True, True]
    assert data[0].tolist() == pytest.approx([1.25, -2.5])
    assert info["owner_cells_by_rank_call"] == {"rank0_call1": 2}

    # The repository replay archive uses deterministic gzip payloads.
    import gzip
    plain = root / "state_entry_rank0.bin"
    compressed = root / "state_entry_rank0.bin.gz"
    compressed.write_bytes(gzip.compress(plain.read_bytes(), compresslevel=9, mtime=0))
    plain.unlink()
    data, mask, owners, _ = reader.read_global_stage(root, spec, inventory, selected, (1, 2, 1), tmp_path / "workgz")
    assert mask.tolist() == [True, True] and data[0].tolist() == pytest.approx([1.25, -2.5])
    plain.write_bytes(compressed.read_bytes())
    with pytest.raises(reader.StatePathError, match="duplicate plain/gzip"):
        reader.validate_runtime_filenames(root)
    plain.unlink()

    compressed.write_bytes(gzip.compress(pack_header(1) + np.array([np.nan, 0.0], dtype=">f4").tobytes(),
                                          compresslevel=9, mtime=0))
    with pytest.raises(reader.StatePathError, match="non-finite physical field"):
        reader.read_global_stage(root, spec, inventory, selected, (1, 2, 1), tmp_path / "work4")


def test_global_stage_rejects_duplicate_cell_owners(tmp_path):
    root = tmp_path / "OLD"
    root.mkdir()
    inventory = {(1, 0, 1): call(), (1, 0, 2): call(call_id=2)}
    path = root / "state_entry_rank0.bin"
    payload = np.array([1.0, 2.0], dtype=">f4").tobytes()
    path.write_bytes(pack_header(1, call_id=1) + payload + pack_header(1, call_id=2) + payload)
    spec = reader.StageSpec(1, "entry", ("X",), False)
    with pytest.raises(reader.StatePathError, match="duplicate owner cell"):
        reader.read_global_stage(root, spec, inventory, [], (1, 2, 1), tmp_path / "work")


def test_global_stage_rejects_unadvertised_extra_float_per_row(tmp_path):
    root = tmp_path / "OLD"
    root.mkdir()
    inventory = {(1, 0, 1): call()}
    # Current schema declares one field and two cells; a stale native row
    # layout with an extra (uninitialized) REAL per cell leaves stray bytes.
    spec = reader.StageSpec(1, "entry", tuple(f"F{n}" for n in range(15)), False)
    path = root / "state_entry_rank0.bin"
    path.write_bytes(pack_header(1, fields=15, records=2) + np.arange(32, dtype=">f4").tobytes())
    with pytest.raises(reader.StatePathError, match="truncated block header|invalid CBSP magic"):
        reader.read_global_stage(root, spec, inventory, [], (1, 2, 1), tmp_path / "work")


def test_global_mask_mismatch_is_rejected_and_signed_zero_is_separate(tmp_path):
    spec = reader.StageSpec(1, "entry", ("X",), False)
    values_old = np.array([[0.0]], dtype=">f4")
    values_fix = np.array([[-0.0]], dtype=">f4")
    with pytest.raises(reader.StatePathError, match="observed call masks differ"):
        reader.compare_global(values_old, values_fix, np.array([True]), np.array([False]), spec, (1, 1, 1))
    rows, summary = reader.compare_global(values_old, values_fix, np.array([True]), np.array([True]), spec, (1, 1, 1))
    assert rows[0]["bitwise_different"] == 1
    assert rows[0]["numeric_different"] == 0
    assert rows[0]["signed_zero_only"] == 1
    assert summary["earliest_global_difference"]["signed_zero_only"] is True
    assert summary["earliest_global_difference"]["old_word"] == "0x00000000"
    assert summary["earliest_global_difference"]["fix_word"] == "0x80000000"

    old = np.asarray([[0.0, 1.0]], dtype=">f4")
    fix = np.asarray([[-0.0, 2.0]], dtype=">f4")
    rows, summary = reader.compare_global(old, fix, np.asarray([True, True]), np.asarray([True, True]),
                                          spec, (1, 2, 1))
    assert summary["earliest_global_bitwise_difference"]["i"] == 1
    assert summary["earliest_global_numeric_difference"]["i"] == 2
    assert json.loads(rows[0]["first_numeric_difference_kji"])["i"] == 2


def test_old_fix_inventory_requires_exact_call_metadata_even_if_keys_match():
    old = {(1, 0, 1): call()}
    fix = {(1, 0, 1): call(ihi=1)}
    with pytest.raises(reader.StatePathError, match="call bounds/metadata differ"):
        reader._calls_equal(old, fix)


def test_selected_row_coverage_rejects_missing_and_duplicate_keys(tmp_path):
    root = tmp_path / "OLD"
    root.mkdir()
    cells = []
    for point_number in range(8):
        for corner_number, corner_name in enumerate(("00", "10", "01", "11")):
            cell_number = point_number * 4 + corner_number
            cells.append({"point_id": f"P{point_number+1:02d}" if point_number < 4 else f"FA{point_number-3:02d}",
                          "corner": corner_name, "i": cell_number + 1, "j": 1, "weight": 0.25})
    # One full horizontal extent, one level, one block for each timestep.
    call_inventory = {(t, 0, 1): call(step=t, ilo=1, ihi=32) for t in range(1, 361)}
    spec = reader.StageSpec(6, "selected_entry", ("X",), True)
    dtype = np.dtype([("i", ">i4"), ("j", ">i4"), ("k", ">i4"), ("values", ">f4", (1,))])
    path = root / "state_selected_entry_rank0.bin"
    with path.open("wb") as stream:
        for t in range(1, 361):
            rows = np.zeros(32, dtype=dtype)
            rows["i"] = np.arange(1, 33)
            rows["j"] = 1
            rows["k"] = 1
            rows["values"] = t
            stream.write(pack_header(6, timestep=t, bounds=(1,32,1,1,1,1), records=32))
            stream.write(rows.tobytes())
    data, occupied, _ = reader.read_selected_stage(root, spec, call_inventory, cells, (1, 32, 1), tmp_path / "selected_work")
    assert occupied.shape == (360, 1, 32) and occupied.all()
    assert float(data[359, 0, 31, 0]) == 360.0

    # Reusing a horizontal corner at a different level is valid and distinct.
    two_level = tmp_path / "TWO_LEVEL"
    two_level.mkdir()
    multi_rows = np.zeros(64, dtype=dtype)
    multi_rows[0:32]["i"] = np.arange(1, 33)
    multi_rows[32:64]["i"] = np.arange(1, 33)
    multi_rows[0:32]["j"] = multi_rows[32:64]["j"] = 1
    multi_rows[0:32]["k"] = 1
    multi_rows[32:64]["k"] = 2
    multi_rows["values"] = 1.0
    with (two_level / "state_selected_entry_rank0.bin").open("wb") as stream:
        for t in range(1, 361):
            stream.write(pack_header(6, timestep=t, bounds=(1,32,1,1,1,2), records=64))
            stream.write(multi_rows.tobytes())
    multi_call_inventory = {(t, 0, 1): call(step=t, ilo=1, ihi=32, klo=1, khi=2) for t in range(1, 361)}
    data, occupied, _ = reader.read_selected_stage(two_level, spec, multi_call_inventory, cells,
                                                   (1, 32, 2), tmp_path / "two_level_work")
    assert occupied.all() and data.shape == (360, 2, 32, 1)

    # Replacing one row with another preserves record_count but violates unique keys.
    bad = tmp_path / "BAD"
    bad.mkdir()
    first_block = pack_header(6, timestep=1, bounds=(1,32,1,1,1,1), records=32)
    rows = np.zeros(32, dtype=dtype)
    rows["i"] = np.arange(1, 33)
    rows["j"] = rows["k"] = 1
    rows[31]["i"] = 1
    rows["values"] = 1.0
    bad_path = bad / "state_selected_entry_rank0.bin"
    with bad_path.open("wb") as stream:
        stream.write(first_block + rows.tobytes())
        for t in range(2, 361):
            good_rows = np.zeros(32, dtype=dtype)
            good_rows["i"] = np.arange(1, 33)
            good_rows["j"] = good_rows["k"] = 1
            good_rows["values"] = t
            stream.write(pack_header(6, timestep=t, bounds=(1,32,1,1,1,1), records=32))
            stream.write(good_rows.tobytes())
    with pytest.raises(reader.StatePathError, match="duplicate selected row"):
        reader.read_selected_stage(bad, spec, call_inventory, cells, (1, 32, 1), tmp_path / "bad_work")

    missing_row = tmp_path / "MISSING_ROW"
    missing_row.mkdir()
    short_header = pack_header(6, timestep=1, bounds=(1,32,1,1,1,1), records=31)
    (missing_row / "state_selected_entry_rank0.bin").write_bytes(short_header + good_rows[:31].tobytes())
    with pytest.raises(reader.StatePathError, match="record_count"):
        reader.read_selected_stage(missing_row, spec, call_inventory, cells, (1, 32, 1), tmp_path / "missing_work")


def test_selected_ledger_checks_entry_within_and_between_call_terms():
    cells = []
    for point_number in range(8):
        for corner_number, corner_name in enumerate(("00", "10", "01", "11")):
            cell_index = point_number * 4 + corner_number
            cells.append({"point_id": f"P{point_number:02d}", "corner": corner_name,
                          "i": cell_index + 1, "j": 1, "weight": 0.25})
    shape = (360, 1, 32, 1)
    old_entry = np.ones(shape, dtype=">f4")
    old_return = np.full(shape, 1.1, dtype=">f4")
    fix_entry = np.full(shape, 3.0, dtype=">f4")
    fix_return = np.full(shape, 4.0, dtype=">f4")
    rows, summary = reader.selected_ledger(old_entry, old_return, fix_entry, fix_return, cells, ("QV",))
    values = {(row["point_id"], row["ledger_component"]): row for row in rows}
    assert values[("P00", "incoming")]["max_abs_difference"] == pytest.approx(2.0)
    assert values[("P00", "within")]["max_abs_difference"] == pytest.approx(0.9, abs=1e-6)
    assert values[("P00", "between")]["max_abs_difference"] == pytest.approx(0.9, abs=1e-6)
    assert summary["max_abs_same_call_ledger_residual"] < 1e-12
    assert "not pure transport" in summary["between_identity"]

    profiles = reader.selected_weighted_profiles(old_entry, old_return, fix_entry, fix_return, cells,
                                                 [f"P{i:02d}" for i in range(8)], ("QV",))
    assert profiles["time"].tolist() == list(range(1, 361))
    assert profiles["point_ids"].tolist() == [f"P{i:02d}" for i in range(8)]
    assert profiles["fields"].tolist() == ["QV"]
    assert profiles["old_entry_weighted"].shape == (360, 1, 8, 1)
    assert profiles["between_delta"].shape == (359, 1, 8, 1)
    assert profiles["D_entry"][0, 0, 0, 0] == pytest.approx(2.0)
    assert profiles["within_delta"][0, 0, 0, 0] == pytest.approx(0.9, abs=1e-6)

    first_rows = reader.selected_point_first_differences(old_entry, old_return, fix_entry, fix_return, cells,
                                                          [f"P{i:02d}" for i in range(8)], ("QV",))
    first = first_rows[0]
    assert first["point_id"] == "P00" and first["field"] == "QV"
    assert first["incoming_timestep"] == 1 and first["incoming_k"] == 1
    assert first["incoming_old_word"] == "0x3f800000"
    assert first["incoming_fix_word"] == "0x40400000"
    assert first["within_timestep"] == 1 and first["within_difference"] == pytest.approx(0.9, abs=1e-6)


def test_selected_first_numeric_difference_is_distinct_from_signed_zero():
    cells = []
    point_ids = [f"P{i:02d}" for i in range(1, 5)] + [f"FA{i:02d}" for i in range(1, 5)]
    for point_number, point_id in enumerate(point_ids):
        for corner_number, corner_name in enumerate(("00", "10", "01", "11")):
            cells.append({"point_id": point_id, "corner": corner_name,
                          "i": point_number * 4 + corner_number + 1, "j": 1, "weight": 0.25})
    shape = (360, 1, 32, 1)
    old_entry = np.zeros(shape, dtype=">f4")
    fix_entry = np.zeros(shape, dtype=">f4")
    old_return = np.zeros(shape, dtype=">f4")
    fix_return = np.zeros(shape, dtype=">f4")
    fix_entry[0, 0, 0, 0] = -0.0
    old_entry[1, 0, 1, 0], fix_entry[1, 0, 1, 0] = 1.0, 2.0
    rows = reader.selected_point_first_differences(old_entry, old_return, fix_entry, fix_return,
                                                   cells, point_ids, ("QV",))
    p01 = rows[0]
    assert p01["incoming_timestep"] == 1 and p01["incoming_numeric_timestep"] == 2
    assert p01["incoming_numeric_old"] == 1.0 and p01["incoming_numeric_fix"] == 2.0


def test_same_call_ledger_uses_scale_aware_gamma8_bound_and_rejects_corruption():
    cells = []
    for point_number in range(8):
        point_id = f"P{point_number:02d}"
        for corner_number, corner_name in enumerate(("00", "10", "01", "11")):
            weight = (0.1, 0.2, 0.3, 0.4)[corner_number] if point_number == 0 else 0.25
            cells.append({"point_id": point_id, "corner": corner_name,
                          "i": point_number * 4 + corner_number + 1, "j": 1, "weight": weight})
    shape = (360, 1, 32, 1)
    old_entry = np.empty(shape, dtype=">f4")
    old_return = np.empty(shape, dtype=">f4")
    fix_entry = np.empty(shape, dtype=">f4")
    fix_return = np.empty(shape, dtype=">f4")
    for ci in range(32):
        old_entry[:, 0, ci, 0] = np.float32(1.0e9 + ci * 64)
        old_return[:, 0, ci, 0] = np.float32(1.0e9 + ci * 64 + 128)
        fix_entry[:, 0, ci, 0] = np.float32(1.0e9 + ci * 64 + 192)
        fix_return[:, 0, ci, 0] = np.float32(1.0e9 + ci * 64 + 320)
    point_ids = [f"P{i:02d}" for i in range(8)]
    profiles = reader.selected_weighted_profiles(old_entry, old_return, fix_entry, fix_return,
                                                 cells, point_ids, ("NN",))
    _, summary = reader.selected_ledger(old_entry, old_return, fix_entry, fix_return,
                                        cells, ("NN",), profiles)
    assert summary["same_call_residual_bound_violation_count"] == 0
    assert summary["same_call_residual_roundoff_model"].startswith("gamma8 bound")

    profiles["within_delta"][0, 0, 0, 0] += 1.0
    _, corrupted = reader.selected_ledger(old_entry, old_return, fix_entry, fix_return,
                                          cells, ("NN",), profiles)
    assert corrupted["same_call_residual_bound_violation_count"] > 0


def test_analyzer_refuses_existing_or_dangling_output_paths(tmp_path):
    old = tmp_path / "OLD"
    fix = tmp_path / "FIX"
    old.mkdir()
    fix.mkdir()
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(reader.StatePathError, match="already exists"):
        reader.analyze_pair(old, fix, reader.DEFAULT_SCHEMA, reader.DEFAULT_CORNERS, existing)
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "absent")
    with pytest.raises(reader.StatePathError, match="already exists"):
        reader.analyze_pair(old, fix, reader.DEFAULT_SCHEMA, reader.DEFAULT_CORNERS, dangling)


def test_deterministic_npz_bytes_and_roundtrip(tmp_path):
    arrays = {"values": np.arange(12, dtype=np.float64).reshape(3, 4),
              "ids": np.asarray(["P01", "FA01"], dtype="U4")}
    one, two = tmp_path / "one.npz", tmp_path / "two.npz"
    reader._write_deterministic_npz(one, **arrays)
    reader._write_deterministic_npz(two, **arrays)
    assert one.read_bytes() == two.read_bytes()
    with np.load(one, allow_pickle=False) as archive:
        np.testing.assert_array_equal(archive["values"], arrays["values"])
        np.testing.assert_array_equal(archive["ids"], arrays["ids"])


def test_selected_archives_split_weighted_profiles_from_lossless_raw_stages(tmp_path):
    metadata = {"time": np.asarray([1, 2], dtype=np.int32),
                "point_ids": np.asarray(["P01"], dtype="U4"),
                "fields": np.asarray(["QV"], dtype="U8"),
                "cell_i": np.asarray([4], dtype=np.int32), "cell_j": np.asarray([5], dtype=np.int32),
                "cell_point_id": np.asarray(["P01"], dtype="U4"),
                "cell_corner": np.asarray(["00"], dtype="U2"), "cell_weight": np.asarray([1.0]),
                "axis_order": np.asarray(["time", "k", "point_or_cell", "field"], dtype="U32")}
    profiles = {**metadata, "D_entry": np.zeros((2, 1, 1, 1)),
                "old_entry_weighted": np.ones((2, 1, 1, 1))}
    selected = {("OLD", 6): np.ones((2, 1, 1, 1), dtype=">f4"),
                ("OLD", 7): np.full((2, 1, 1, 1), 2.0, dtype=">f4"),
                ("FIX", 6): np.full((2, 1, 1, 1), 3.0, dtype=">f4"),
                ("FIX", 7): np.full((2, 1, 1, 1), 4.0, dtype=">f4")}
    paths = reader._write_selected_archives(tmp_path, selected, profiles)
    assert [path.name for path in paths] == ["selected_history.npz", "selected_raw_OLD.npz", "selected_raw_FIX.npz"]
    with np.load(paths[0], allow_pickle=False) as weighted:
        assert "old_entry" not in weighted.files and "D_entry" in weighted.files
    with np.load(paths[1], allow_pickle=False) as old:
        assert set(("entry", "return", "cell_i", "axis_order")) <= set(old.files)
        assert old["entry"].shape == (2, 1, 1, 1) and float(old["return"][0, 0, 0, 0]) == 2.0


def test_global_ownership_export_preserves_called_mask_and_exact_owner_tokens(tmp_path):
    # Flat source order is j,k,i; exported axis order is j,i,k.
    called = np.asarray([True, False, True, True], dtype=np.bool_)
    owners = np.asarray([7, -1, 8, 9], dtype=np.int64)
    arrays = reader._global_ownership_arrays(called, called, owners, owners, (1, 2, 2))
    path = tmp_path / "ownership.npz"
    reader._write_deterministic_npz(path, **arrays)
    with np.load(path, allow_pickle=False) as archive:
        assert archive["called_old"].shape == (1, 2, 2)
        assert archive["called_old"].tolist() == [[[True, True], [False, True]]]
        assert archive["owner_tokens_old"].tolist() == [[[7, 8], [-1, 9]]]
        assert archive["owner_tokens_fix"].tolist() == archive["owner_tokens_old"].tolist()
        assert archive["axis_order"].item() == "j,i,k"


def test_selected_first_step_is_bitwise_bound_to_same_arm_global_checkpoints():
    cells = [{"i": 1, "j": 1}, {"i": 2, "j": 1}]
    global_values = np.asarray([[10, 11, 12, 13], [20, 21, 22, 23]], dtype=">f4")
    selected = np.zeros((360, 2, 2, 2), dtype=">f4")
    for k in range(2):
        for ci in range(2):
            linear = k * 2 + ci
            selected[0, k, ci] = global_values[:, linear]
    reader._verify_selected_global_checkpoint(global_values, selected, cells, (1, 2, 2), "OLD", "selected_entry", "entry")
    selected[0, 1, 1, 0] += 1.0
    with pytest.raises(reader.StatePathError, match="differs bitwise from global entry"):
        reader._verify_selected_global_checkpoint(global_values, selected, cells, (1, 2, 2),
                                                  "OLD", "selected_entry", "entry")


def test_rank_and_archive_manifests_bind_all_eight_ranks_and_arm_inputs(tmp_path, monkeypatch):
    root = tmp_path / "capture"
    old, fix = root / "OLD", root / "FIX"
    old.mkdir(parents=True)
    fix.mkdir()
    schema_path = root / "state_schema.json"
    schema_path.write_text("{}\n", encoding="utf-8")
    expected_path = root / "expected_rank_manifest.json"
    expected = {"format": "CBSP_EXPECTED_RANKS_v1", "mpi_ranks": 8,
                "expected_rank_ids": list(range(8))}
    expected_path.write_text(json.dumps(expected) + "\n", encoding="utf-8")
    expected_sha = hashlib.sha256(expected_path.read_bytes()).hexdigest()
    monkeypatch.setattr(reader, "EXPECTED_RANK_MANIFEST_SHA256", expected_sha)
    arm_records = {}
    archive_records = []
    for arm, arm_root in (("OLD", old), ("FIX", fix)):
        launch = arm_root / "launch_receipt.json"
        launch.write_text("{}\n", encoding="utf-8")
        calls = {}
        for rank in range(8):
            path = arm_root / f"state_calls_rank{rank}.txt"
            path.write_text("", encoding="ascii")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            calls[str(rank)] = {"path": f"{arm}/{path.name}", "sha256": digest,
                                "byte_count": 0, "line_count": 0,
                                "first_timestep": None, "last_timestep": None}
            archive_records.append({"arm": arm, "archive_path": f"{arm}/{path.name}",
                                    "raw_sha256": digest, "raw_bytes": 0, "archive_sha256": digest,
                                    "archive_bytes": 0, "content_type": "CALL_INVENTORY",
                                    "compression": {"format": "none"}})
        launch_digest = hashlib.sha256(launch.read_bytes()).hexdigest()
        arm_records[arm] = {"expected_rank_ids": list(range(8)), "observed_rank_ids": list(range(8)),
                            "launch_receipt": {"path": f"{arm}/launch_receipt.json", "sha256": launch_digest},
                            "inventories": calls}
        archive_records.append({"arm": arm, "archive_path": f"{arm}/launch_receipt.json",
                                "raw_sha256": launch_digest, "raw_bytes": launch.stat().st_size,
                                "archive_sha256": launch_digest, "archive_bytes": launch.stat().st_size,
                                "content_type": "LAUNCH_RECEIPT", "compression": {"format": "none"}})
    observed_path = root / "observed_rank_manifest.json"
    observed = {"format": "CBSP_OBSERVED_RANKS_v1",
                "expected_manifest": {"path": "expected_rank_manifest.json", "sha256": expected_sha},
                "arms": arm_records,
                "checks": {name: True for name in ("all_expected_rank_files_present", "exact_rank_sets",
                    "per_rank_inventory_bytes_equal", "per_rank_inventory_hash_equal", "arm_inventories_identical")}}
    observed_path.write_text(json.dumps(observed) + "\n", encoding="utf-8")
    manifest = {"format": "CBSP_CAPTURE_ARCHIVE_v1",
                "expected_manifest": {"archive_path": "expected_rank_manifest.json", "sha256": expected_sha},
                "observed_manifest": {"archive_path": "observed_rank_manifest.json",
                                      "sha256": hashlib.sha256(observed_path.read_bytes()).hexdigest()},
                "state_schema": {"archive_path": "state_schema.json",
                                 "sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest()},
                "files": archive_records}
    archive_path = root / "capture_archive_manifest.json"
    archive_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    reader.validate_rank_manifests(expected_path, observed_path, {"OLD": old, "FIX": fix})
    reader.validate_capture_archive(archive_path, expected_path, observed_path, schema_path,
                                    {"OLD": old, "FIX": fix})

    (fix / "state_calls_rank7.txt").unlink()
    with pytest.raises(reader.StatePathError, match="rank 7 inventory"):
        reader.validate_rank_manifests(expected_path, observed_path, {"OLD": old, "FIX": fix})
