"""Native MP37 NetCDF reader contract tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import netCDF4
import numpy as np


TOOLS = Path(__file__).resolve().parents[1] / "tools"
TOOL = TOOLS / "check_native_mp37_aux.py"
sys.path.insert(0, str(TOOLS))
from cloud_bal_transaction import OutputTransaction, _current  # noqa: E402
from mp37_aux_contract import AuthorityEvidence, FieldMetadata  # noqa: E402
spec = importlib.util.spec_from_file_location("native_mp37_aux", TOOL)
native = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = native
spec.loader.exec_module(native)


AUX_FIELDS = ("QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB")
MASS_FIELDS = ("QGRAUP", "QRAIN", "QCLOUD", "QICE")
ALL_FIELDS = AUX_FIELDS + MASS_FIELDS
DIMS = ("Time", "bottom_top", "south_north", "west_east")
DIMENSION_SIZES = {"Time": 1, "bottom_top": 1, "south_north": 1,
                   "west_east": 2}
DATA_SHAPE = tuple(DIMENSION_SIZES[name] for name in DIMS)


def _write_native(
    path: Path,
    *,
    mp_physics: int | None = 37,
    missing: str | None = None,
    masked: str | None = None,
    invalid: tuple[str, str] | None = None,
    malformed: str | None = None,
    dimension_sizes: dict[str, int] | None = None,
    units: bool = False,
) -> None:
    sizes = dict(DIMENSION_SIZES)
    if dimension_sizes:
        sizes.update(dimension_sizes)

    with netCDF4.Dataset(path, "w") as dataset:
        for name in DIMS:
            dataset.createDimension(name, sizes[name])
        if mp_physics is not None:
            dataset.MP_PHYSICS = np.int32(mp_physics)

        for name in ALL_FIELDS:
            if name == missing:
                continue
            dimensions = DIMS
            if name == malformed:
                dimensions = ("Time", "south_north", "bottom_top", "west_east")
            dtype = "f8"
            if invalid and invalid == (name, "nonreal"):
                dtype = "S1"
            fill_value = -999.0 if name == masked else None
            variable = dataset.createVariable(
                name, dtype, dimensions, fill_value=fill_value
            )
            if units:
                variable.units = "m(3) kg(-1)" if name == "QIB" else "kg(-1)"
            shape = tuple(sizes[dimension] for dimension in dimensions)
            if dtype == "S1":
                values = np.full(shape, b"x", dtype="S1")
            else:
                values = np.full(shape, 1.0e-8, dtype=np.float64)
            if name in MASS_FIELDS:
                values[...] = 1.0e-7
            if invalid and invalid[0] == name:
                if invalid[1] == "nan":
                    values.flat[0] = np.nan
                elif invalid[1] == "negative":
                    values.flat[0] = -1.0
            if name == masked:
                values.flat[0] = -999.0
            variable[:] = values


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_cli(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), str(path)],
        cwd=TOOL.parents[1],
        check=False,
        capture_output=True,
        text=True,
    )


def _declaration(path: Path, *, scope: str = "CONSTRUCTED_TEST_ONLY",
                 input_sha256: str | None = None,
                 expected_denominators: dict[str, str] | None = None,
                 metadata: dict[str, FieldMetadata] | None = None,
                 authority: AuthorityEvidence | None = None,
                 ) -> native.NativeAuxiliaryDeclaration:
    return native.NativeAuxiliaryDeclaration(
        input_sha256=_sha256(path) if input_sha256 is None else input_sha256,
        metadata=(
            {
                name: FieldMetadata(
                    units="m3 kg-1" if name == "QIB" else "kg-1",
                    denominator="dry_air",
                    provenance=f"fixture:{name}",
                )
                for name in AUX_FIELDS
            } if metadata is None else metadata
        ),
        expected_denominators=(
            {name: "dry_air" for name in AUX_FIELDS}
            if expected_denominators is None else expected_denominators
        ),
        authority=(
            AuthorityEvidence(scope, "a" * 64, "b" * 64, "c" * 64)
            if authority is None else authority
        ),
    )


def _commit_prior_generation(root: Path) -> bytes:
    transaction = OutputTransaction(root, "prior")
    transaction.begin(
        ["accepted/native.txt"],
        source_commit="a" * 40,
        configuration="test",
        valid_time=1,
    )
    transaction.resolve_output("accepted/native.txt").write_bytes(b"prior")
    transaction.commit()
    return (transaction.generation / "MANIFEST.json").read_bytes()


class NativeMP37AuxiliaryReaderTest(unittest.TestCase):
    def test_complete_payload_is_read_only_and_has_pair_gap_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfinput_d01.nc"
            _write_native(path, units=True)
            with netCDF4.Dataset(path, "r+") as dataset:
                dataset["QNCLOUD"][0, 0, 0, 1] = 0.0
                dataset["QNICE"][:] = 0.0
            before = path.read_bytes()
            digest = _sha256(path)

            report = native.inspect_native_mp37(path)

            self.assertEqual(report["status"], "NO_AUTHORITY")
            self.assertEqual(report["reason"], "EXPECTED_DENOMINATOR_MAPPING_MISSING")
            self.assertFalse(report["accepted"])
            self.assertEqual(report["native_authority"], "NONE")
            self.assertEqual(report["expected_shape"], [1, 1, 2])
            self.assertEqual(report["pair_gap_counts"], {
                "QGRAUP": 0,
                "QRAIN": 0,
                "QCLOUD": 1,
                "QICE": 2,
            })
            self.assertEqual(report["input_sha256"], digest)
            self.assertTrue(report["input_unchanged"])
            self.assertTrue(report["inspection_only"])
            self.assertEqual(path.read_bytes(), before)

    def test_missing_mp_physics_is_no_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing_physics.nc"
            _write_native(path, mp_physics=None)

            report = native.inspect_native_mp37(path)

            self.assertEqual(report["status"], "NO_AUTHORITY")
            self.assertEqual(report["reason"], "MISSING_MP_PHYSICS")
            self.assertFalse(report["accepted"])
            self.assertEqual(report["native_authority"], "NONE")

    def test_unsupported_mp_physics_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsupported_physics.nc"
            _write_native(path, mp_physics=8)
            before = path.read_bytes()

            report = native.inspect_native_mp37(path)

            self.assertEqual(report["status"], "REJECTED")
            self.assertEqual(report["reason"], "UNSUPPORTED_MP_PHYSICS")
            self.assertFalse(report["accepted"])
            self.assertEqual(report["input_sha256"], hashlib.sha256(before).hexdigest())
            self.assertEqual(path.read_bytes(), before)

    def test_masked_fill_rejects_the_named_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "masked.nc"
            _write_native(path, masked="QNCLOUD")

            report = native.inspect_native_mp37(path)

            self.assertEqual(report["status"], "REJECTED")
            self.assertEqual(report["reason"], "MASKED_FIELD:QNCLOUD")
            self.assertFalse(report["accepted"])

    def test_missing_field_rejects_the_named_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.nc"
            _write_native(path, missing="QICE")

            report = native.inspect_native_mp37(path)

            self.assertEqual(report["status"], "REJECTED")
            self.assertEqual(report["reason"], "MISSING_FIELD:QICE")
            self.assertFalse(report["accepted"])

    def test_malformed_field_dimensions_reject_the_named_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "layout.nc"
            _write_native(path, malformed="QNCCN")

            report = native.inspect_native_mp37(path)

            self.assertEqual(report["status"], "REJECTED")
            self.assertEqual(report["reason"], "MALFORMED_DIMENSIONS:QNCCN")
            self.assertFalse(report["accepted"])

    def test_nonpositive_axis_size_rejects_in_shared_shape_validator(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zero_axis.nc"
            _write_native(path, dimension_sizes={"bottom_top": 0})

            report = native.inspect_native_mp37(path)

            self.assertEqual(report["status"], "REJECTED")
            self.assertEqual(report["reason"], "INVALID_EXPECTED_SHAPE")
            self.assertFalse(report["accepted"])

    def test_physical_values_delegate_to_existing_validator(self):
        cases = (
            ("nan", "NONFINITE_FIELD:QNRAIN"),
            ("negative", "NEGATIVE_FIELD:QICE"),
            ("nonreal", "NONREAL_FIELD:QIB"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for kind, expected_reason in cases:
                with self.subTest(kind=kind):
                    path = Path(directory) / f"{kind}.nc"
                    field = expected_reason.rsplit(":", 1)[1]
                    _write_native(path, invalid=(field, kind))

                    report = native.inspect_native_mp37(path)

                    self.assertEqual(report["status"], "REJECTED")
                    self.assertEqual(report["reason"], expected_reason)
                    self.assertFalse(report["accepted"])

    def test_constructed_declaration_publishes_diagnostic_receipt_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "wrfinput_d01.nc"
            publication = root / "publication"
            _write_native(path, units=True)
            declaration = _declaration(path)

            report = native.inspect_native_mp37(path, declaration=declaration)

            self.assertEqual(report["status"], "STRUCTURAL_CONTRACT_VALID")
            self.assertTrue(report["contract_valid"])
            self.assertFalse(report["accepted"])
            self.assertEqual(report["authority_scope"], "CONSTRUCTED_TEST_ONLY")
            self.assertEqual(report["evidence_status"], "SYNTAX_ONLY_UNVERIFIED")
            self.assertFalse(report["native_promotion"])
            self.assertEqual(report["launch_authority"], "NONE")

            manifest = native.run_native_preflight(
                path,
                publication_root=publication,
                transaction_id="constructed",
                source_commit="a" * 40,
                configuration="cp01-test",
                declaration=declaration,
            )
            self.assertEqual(
                [item["path"] for item in manifest["products"]],
                ["preflight/native_mp37.json"],
            )
            receipt = json.loads(
                (_current(publication) / "preflight/native_mp37.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["receipt_scope"], "CONSTRUCTED_TEST_ONLY")
            self.assertEqual(receipt["publication_filesystem_preflight"]["status"], "PASS")
            self.assertFalse(receipt["native_promotion"])
            self.assertEqual(receipt["launch_authority"], "NONE")
            self.assertEqual(receipt["evidence_status"], "SYNTAX_ONLY_UNVERIFIED")
            self.assertFalse((publication / "LAUNCH_ALLOWED").exists())

    def test_declaration_input_hash_is_required_and_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfinput_d01.nc"
            _write_native(path)

            unknown = native.inspect_native_mp37(
                path, declaration=_declaration(path, input_sha256="")
            )
            self.assertEqual(unknown["status"], "REJECTED")
            self.assertEqual(unknown["reason"], "DECLARATION_INPUT_SHA256_UNKNOWN")

            mismatch = native.inspect_native_mp37(
                path, declaration=_declaration(path, input_sha256="a" * 64)
            )
            self.assertEqual(mismatch["status"], "REJECTED")
            self.assertEqual(mismatch["reason"], "DECLARATION_INPUT_SHA256_MISMATCH")

    def test_malformed_values_precede_missing_hash_or_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfinput_d01.nc"
            _write_native(path, invalid=("QCLOUD", "nan"), units=True)

            missing_hash = native.inspect_native_mp37(
                path, declaration=_declaration(path, input_sha256="")
            )
            self.assertEqual(missing_hash["status"], "REJECTED")
            self.assertEqual(missing_hash["reason"], "NONFINITE_FIELD:QCLOUD")

            wrong_profile = native.inspect_native_mp37(
                path,
                declaration=_declaration(
                    path,
                    expected_denominators={name: "moist_air" for name in AUX_FIELDS},
                ),
            )
            self.assertEqual(wrong_profile["status"], "REJECTED")
            self.assertEqual(wrong_profile["reason"], "NONFINITE_FIELD:QCLOUD")

    def test_missing_or_mismatched_declarations_remain_no_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfinput_d01.nc"
            _write_native(path, units=True)

            missing = native.inspect_native_mp37(
                path, declaration=_declaration(path, expected_denominators={})
            )
            self.assertEqual(missing["status"], "NO_AUTHORITY")
            self.assertEqual(
                missing["reason"], "INCOMPLETE_EXPECTED_DENOMINATOR_MAPPING"
            )

            metadata = {
                name: FieldMetadata(
                    units="m3 kg-1" if name == "QIB" else "kg-1",
                    denominator="dry_air",
                    provenance=f"fixture:{name}",
                )
                for name in AUX_FIELDS
            }
            metadata["QIB"] = FieldMetadata(
                units="m3 kg-1", denominator="moist_air", provenance="fixture:QIB"
            )
            mismatched = native.inspect_native_mp37(
                path, declaration=_declaration(path, metadata=metadata)
            )
            self.assertEqual(mismatched["status"], "NO_AUTHORITY")
            self.assertEqual(mismatched["reason"], "DENOMINATOR_MISMATCH:QIB")

            moist_metadata = {
                name: FieldMetadata(
                    units="m3 kg-1" if name == "QIB" else "kg-1",
                    denominator="moist_air",
                    provenance=f"fixture:{name}",
                )
                for name in AUX_FIELDS
            }
            self.assertEqual(
                native.inspect_native_mp37(
                    path,
                    declaration=_declaration(
                        path,
                        expected_denominators={
                            name: "moist_air" for name in AUX_FIELDS
                        },
                        metadata=moist_metadata,
                    ),
                )["reason"],
                "DECLARATION_DENOMINATOR_PROFILE_MISMATCH",
            )

    def test_declared_units_must_match_serialized_units(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfinput_d01.nc"
            _write_native(path, units=True)
            with netCDF4.Dataset(path, "r+") as dataset:
                dataset["QIB"].units = "kg-1"

            report = native.inspect_native_mp37(
                path, declaration=_declaration(path)
            )
            self.assertEqual(report["status"], "REJECTED")
            self.assertEqual(report["reason"], "UNITS_ATTRIBUTE_MISMATCH:QIB")

    def test_filesystem_rejection_precedes_diagnostic_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "wrfinput_d01.nc"
            publication = root / "publication"
            _write_native(path, units=True)
            declaration = _declaration(path)
            with mock.patch.object(native, "preflight_publication_filesystem", side_effect=RuntimeError("unsupported filesystem")):
                with self.assertRaisesRegex(RuntimeError, "unsupported filesystem"):
                    native.run_native_preflight(
                        path, publication_root=publication, transaction_id="constructed",
                        source_commit="a" * 40, configuration="cp02-test",
                        declaration=declaration,
                    )
            self.assertEqual(list(publication.iterdir()), [])

    def test_producer_bound_syntax_does_not_authorize_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "wrfinput_d01.nc"
            publication = root / "publication"
            _write_native(path, units=True)
            declaration = _declaration(path, scope="PRODUCER_BOUND")

            report = native.inspect_native_mp37(path, declaration=declaration)
            self.assertEqual(report["status"], "STRUCTURAL_CONTRACT_VALID")
            self.assertEqual(report["evidence_status"], "SYNTAX_ONLY_UNVERIFIED")
            self.assertFalse(report["promotion_eligible"])

            with self.assertRaises(native.NativePreflightRejected) as rejected:
                native.run_native_preflight(
                    path,
                    publication_root=publication,
                    transaction_id="producer-bound",
                    source_commit="a" * 40,
                    configuration="cp01-test",
                    declaration=declaration,
                )
            self.assertEqual(rejected.exception.report["status"], "NO_AUTHORITY")
            self.assertEqual(
                rejected.exception.report["reason"], "NATIVE_AUTHORITY_NOT_VERIFIED"
            )
            self.assertFalse(publication.exists())

    def test_actual_no_authority_rejects_before_transaction_and_preserves_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "wrfinput_d01.nc"
            publication = root / "publication"
            _write_native(path)
            prior_manifest = _commit_prior_generation(publication)
            current_target = (publication / "current").readlink()

            with self.assertRaises(native.NativePreflightRejected) as rejected:
                native.run_native_preflight(
                    path,
                    publication_root=publication,
                    transaction_id="actual-no-authority",
                    source_commit="a" * 40,
                    configuration="cp01-test",
                )

            self.assertEqual(rejected.exception.report["status"], "NO_AUTHORITY")
            self.assertEqual(
                rejected.exception.report["reason"],
                "EXPECTED_DENOMINATOR_MAPPING_MISSING",
            )
            self.assertEqual((publication / "current").readlink(), current_target)
            self.assertEqual(
                (publication / "generations" / "prior" / "MANIFEST.json")
                .read_bytes(),
                prior_manifest,
            )
            self.assertEqual(
                sorted(path.name for path in (publication / "generations").iterdir()),
                ["prior"],
            )
            self.assertFalse((publication / "LAUNCH_ALLOWED").exists())

    def test_cli_emits_json_status_and_does_not_create_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            no_authority = root / "complete.nc"
            rejected = root / "bad.nc"
            _write_native(no_authority)
            _write_native(rejected, missing="QGRAUP")
            no_authority_before = no_authority.read_bytes()
            rejected_before = rejected.read_bytes()
            names_before = sorted(path.name for path in root.iterdir())

            no_authority_run = _run_cli(no_authority)
            rejected_run = _run_cli(rejected)

            self.assertEqual(no_authority_run.returncode, 3)
            self.assertEqual(rejected_run.returncode, 2)
            no_authority_report = json.loads(no_authority_run.stdout)
            rejected_report = json.loads(rejected_run.stdout)
            self.assertEqual(no_authority_report["status"], "NO_AUTHORITY")
            self.assertEqual(
                no_authority_report["reason"],
                "EXPECTED_DENOMINATOR_MAPPING_MISSING",
            )
            self.assertEqual(rejected_report["status"], "REJECTED")
            self.assertEqual(rejected_report["reason"], "MISSING_FIELD:QGRAUP")
            self.assertEqual(no_authority_report["input_sha256"],
                             hashlib.sha256(no_authority_before).hexdigest())
            self.assertEqual(rejected_report["input_sha256"],
                             hashlib.sha256(rejected_before).hexdigest())
            self.assertEqual(sorted(path.name for path in root.iterdir()), names_before)
            self.assertEqual(no_authority.read_bytes(), no_authority_before)
            self.assertEqual(rejected.read_bytes(), rejected_before)

    def test_malformed_data_precedes_missing_physics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad_unbound.nc"
            _write_native(path, mp_physics=None, invalid=("QCLOUD", "nan"))
            report = native.inspect_native_mp37(path)
            self.assertEqual(report["status"], "REJECTED")
            self.assertEqual(report["reason"], "NONFINITE_FIELD:QCLOUD")

    def test_ambiguous_or_empty_time_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for count in (0, 2):
                with self.subTest(count=count):
                    path = Path(directory) / f"time_{count}.nc"
                    _write_native(path, dimension_sizes={"Time": count})
                    report = native.inspect_native_mp37(path)
                    self.assertEqual(report["status"], "REJECTED")
                    self.assertEqual(report["reason"], "INVALID_TIME_DIMENSION")

    def test_unreadable_native_input_returns_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            corrupt = Path(directory) / "corrupt.nc"
            corrupt.write_bytes(b"not a NetCDF file")
            for path in (corrupt, Path(directory) / "missing.nc"):
                with self.subTest(path=path):
                    report = native.inspect_native_mp37(path)
                    self.assertEqual(report["status"], "REJECTED")
                    self.assertEqual(report["reason"], "NATIVE_INPUT_READ_ERROR")
                    self.assertFalse(report["accepted"])
                    self.assertTrue(report["inspection_only"])


if __name__ == "__main__":
    unittest.main()
