"""Small CP01 MP37 auxiliary contract cases; no native runtime or science claim."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from mp37_aux_contract import (  # noqa: E402
    AUX_FIELDS,
    AuthorityEvidence,
    FieldMetadata,
    validate_mp37_auxiliaries,
)


SHAPE = (2, 1, 2)
HASH = "a" * 64
MISSING = object()
EXPECTED_DENOMINATORS = {name: "dry_air" for name in AUX_FIELDS}


def metadata():
    return {
        name: FieldMetadata(
            units="m3 kg-1" if name == "QIB" else "kg-1",
            denominator="dry_air",
            provenance=f"fixture:{name}",
        )
        for name in AUX_FIELDS
    }


def authority():
    return AuthorityEvidence(
        scope="CONSTRUCTED_TEST_ONLY",
        receipt_sha256=HASH,
        source_sha256=HASH,
        producer_sha256=HASH,
    )


def arrays():
    return {
        "QNCCN": np.full(SHAPE, 1.0e6),
        "QNCLOUD": np.full(SHAPE, 2.0e5),
        "QNICE": np.full(SHAPE, 3.0e4),
        "QNRAIN": np.full(SHAPE, 4.0e4),
        "QIB": np.full(SHAPE, 1.0e-8),
    }


class MP37AuxiliaryContractTest(unittest.TestCase):
    def check(
        self,
        values=None,
        declarations=None,
        evidence=MISSING,
        qgraup=None,
        qrain=None,
        qcloud=None,
        qice=None,
    ):
        declared_evidence = authority() if evidence is MISSING else evidence
        return validate_mp37_auxiliaries(
            arrays() if values is None else values,
            metadata() if declarations is None else declarations,
            declared_evidence,
            qgraup=np.full(SHAPE, 1.0e-7) if qgraup is None else qgraup,
            qrain=np.full(SHAPE, 1.0e-7) if qrain is None else qrain,
            qcloud=np.full(SHAPE, 1.0e-7) if qcloud is None else qcloud,
            qice=np.full(SHAPE, 1.0e-7) if qice is None else qice,
            expected_shape=SHAPE,
            expected_denominators=EXPECTED_DENOMINATORS,
        )

    def test_constructed_declared_authority_is_diagnostic_only(self):
        report = self.check()
        self.assertEqual(report["status"], "STRUCTURAL_CONTRACT_VALID")
        self.assertTrue(report["contract_valid"])
        self.assertFalse(report["accepted"])
        self.assertEqual(report["authority_scope"], "CONSTRUCTED_TEST_ONLY")
        self.assertEqual(report["native_authority"], "NONE")
        self.assertEqual(report["authority_verification"], "NOT_PERFORMED")
        self.assertFalse(report["promotion_eligible"])
        self.assertEqual(report["synthesized_fields"], [])

    def test_well_formed_producer_claim_remains_unverified(self):
        report = self.check(evidence=AuthorityEvidence("PRODUCER_BOUND", HASH, HASH, HASH))
        self.assertEqual(report["status"], "STRUCTURAL_CONTRACT_VALID")
        self.assertTrue(report["contract_valid"])
        self.assertFalse(report["accepted"])
        self.assertEqual(report["native_authority"], "NONE")
        self.assertEqual(report["authority_verification"], "NOT_PERFORMED")

    def test_missing_each_auxiliary_rejects(self):
        for name in AUX_FIELDS:
            values = arrays()
            del values[name]
            with self.subTest(name=name):
                report = self.check(values=values)
                self.assertEqual(report["status"], "REJECTED")
                self.assertEqual(report["reason"], f"MISSING_FIELD:{name}")

    def test_unknown_denominator_is_no_authority(self):
        declarations = metadata()
        declarations["QIB"] = FieldMetadata("m3 kg-1", "unbound", "fixture:QIB")
        report = self.check(declarations=declarations)
        self.assertEqual(report, {
            "status": "NO_AUTHORITY",
            "contract_valid": False,
            "accepted": False,
            "reason": "UNKNOWN_DENOMINATOR:QIB",
            "native_authority": "NONE",
            "authority_verification": "NOT_PERFORMED",
            "promotion_eligible": False,
            "science_authority": "NONE",
        })

    def test_arbitrary_provenance_text_does_not_supply_authority(self):
        declarations = metadata()
        declarations["QIB"] = FieldMetadata("m3 kg-1", "dry_air", "trust-me")
        report = self.check(declarations=declarations, evidence=None)
        self.assertEqual(report["status"], "NO_AUTHORITY")
        self.assertEqual(report["reason"], "AUTHORITY_EVIDENCE_MISSING")
        report = self.check(evidence=AuthorityEvidence("PRODUCER_BOUND", "bad", HASH, HASH))
        self.assertEqual(report["status"], "NO_AUTHORITY")
        self.assertEqual(report["reason"], "INVALID_AUTHORITY_HASH:receipt_sha256")

    def test_malformed_shape_and_nonfinite_reject(self):
        values = arrays()
        values["QNICE"] = np.zeros((1, 1, 2))
        report = self.check(values=values)
        self.assertEqual(report["reason"], "MALFORMED_SHAPE:QNICE")
        values = arrays()
        values["QNRAIN"][0, 0, 0] = np.nan
        report = self.check(values=values)
        self.assertEqual(report["reason"], "NONFINITE_FIELD:QNRAIN")

    def test_malformed_denominator_container_is_rejected(self):
        for mapping in ([], "dry_air", 1, False):
            with self.subTest(mapping=mapping):
                report = validate_mp37_auxiliaries(
                    arrays(), metadata(), authority(),
                    qgraup=np.zeros(SHAPE), qrain=np.zeros(SHAPE),
                    qcloud=np.zeros(SHAPE), qice=np.zeros(SHAPE),
                    expected_shape=SHAPE, expected_denominators=mapping,
                )
                self.assertEqual(report["status"], "REJECTED")
                self.assertEqual(report["reason"], "INVALID_EXPECTED_DENOMINATOR_MAPPING")
                self.assertFalse(report["accepted"])

    def test_malformed_payload_is_not_hidden_by_missing_authority(self):
        for gap in ("evidence", "denominator", "metadata"):
            for field, bad_value, reason in (
                ("QNRAIN", np.full(SHAPE, np.nan), "NONFINITE_FIELD:QNRAIN"),
                ("QNICE", MISSING, "MISSING_FIELD:QNICE"),
                ("QGRAUP", np.zeros((1,)), "MALFORMED_SHAPE:QGRAUP"),
                ("QRAIN", np.full(SHAPE, -1.0), "NEGATIVE_FIELD:QRAIN"),
                ("QCLOUD", np.full(SHAPE, np.nan), "NONFINITE_FIELD:QCLOUD"),
                ("QICE", np.full(SHAPE, -1.0), "NEGATIVE_FIELD:QICE"),
                ("QNCCN", np.ma.zeros(SHAPE), "MASKED_FIELD:QNCCN"),
                ("QIB", np.full(SHAPE, 1j), "NONREAL_FIELD:QIB"),
            ):
                with self.subTest(gap=gap, field=field):
                    values = arrays()
                    mass = {
                        "QGRAUP": np.zeros(SHAPE),
                        "QRAIN": np.zeros(SHAPE),
                        "QCLOUD": np.zeros(SHAPE),
                        "QICE": np.zeros(SHAPE),
                    }
                    if field in mass:
                        mass[field] = bad_value
                    elif bad_value is MISSING:
                        del values[field]
                    else:
                        values[field] = bad_value
                    report = validate_mp37_auxiliaries(
                        values, None if gap == "metadata" else metadata(),
                        None if gap == "evidence" else authority(),
                        qgraup=mass["QGRAUP"], qrain=mass["QRAIN"],
                        qcloud=mass["QCLOUD"], qice=mass["QICE"],
                        expected_shape=SHAPE,
                        expected_denominators=None if gap == "denominator"
                        else EXPECTED_DENOMINATORS,
                    )
                    self.assertEqual(report["status"], "REJECTED")
                    self.assertEqual(report["reason"], reason)
                    self.assertFalse(report["accepted"])
                    self.assertFalse(report["contract_valid"])
                    self.assertEqual(report["native_authority"], "NONE")

    def test_nonzero_graupel_with_zero_qib_is_no_authority(self):
        values = arrays()
        values["QIB"][:] = 0.0
        report = self.check(values=values, qgraup=np.full(SHAPE, 1.0e-7))
        self.assertEqual(report["status"], "NO_AUTHORITY")
        self.assertEqual(report["reason"], "QIB_ZERO_WITH_NONZERO_QGRAUP")

    def test_cloud_number_gap_is_checked_per_cell(self):
        values = arrays()
        values["QNCLOUD"][:] = 1.0e-6
        values["QNCLOUD"][0, 0, 1] = 0.0
        cloud = np.zeros(SHAPE)
        cloud[0, 0, 1] = 1.0e-12
        cloud[1, 0, 0] = 1.0e-7
        before = values["QNCLOUD"].copy()
        cloud_before = cloud.copy()
        report = self.check(values=values, qcloud=cloud)
        self.assertEqual(report["status"], "NO_AUTHORITY")
        self.assertEqual(report["reason"], "QNCLOUD_ZERO_WITH_NONZERO_QCLOUD")
        self.assertFalse(report["contract_valid"])
        self.assertFalse(report["accepted"])
        np.testing.assert_array_equal(values["QNCLOUD"], before)
        np.testing.assert_array_equal(cloud, cloud_before)

    def test_ice_number_gap_is_checked_per_cell(self):
        values = arrays()
        values["QNICE"][:] = 1.0e-6
        values["QNICE"][1, 0, 0] = 0.0
        ice = np.zeros(SHAPE)
        ice[1, 0, 0] = 1.0e-12
        ice[0, 0, 1] = 1.0e-7
        before = values["QNICE"].copy()
        ice_before = ice.copy()
        report = self.check(values=values, qice=ice)
        self.assertEqual(report["status"], "NO_AUTHORITY")
        self.assertEqual(report["reason"], "QNICE_ZERO_WITH_NONZERO_QICE")
        self.assertFalse(report["contract_valid"])
        self.assertFalse(report["accepted"])
        np.testing.assert_array_equal(values["QNICE"], before)
        np.testing.assert_array_equal(ice, ice_before)

    def test_heterogeneous_qib_gap_is_not_masked_by_one_positive_cell(self):
        values = arrays()
        values["QIB"][:] = 1.0e-8
        values["QIB"][0, 0, 1] = 0.0
        qgraup = np.zeros(SHAPE)
        qgraup[0, 0, 1] = 1.0e-7
        qgraup[1, 0, 0] = 1.0e-7
        report = self.check(values=values, qgraup=qgraup)
        self.assertEqual(report["status"], "NO_AUTHORITY")
        self.assertEqual(report["reason"], "QIB_ZERO_WITH_NONZERO_QGRAUP")

    def test_complex_arrays_reject_as_nonphysical(self):
        values = arrays()
        values["QNCCN"] = values["QNCCN"].astype(np.complex128)
        values["QNCCN"][0, 0, 0] += 1j
        report = self.check(values=values)
        self.assertEqual(report["status"], "REJECTED")
        self.assertEqual(report["reason"], "NONREAL_FIELD:QNCCN")

    def test_rain_number_gap_is_checked_per_cell(self):
        values = arrays()
        values["QNRAIN"][0, 0, 1] = 0.0
        rain = np.zeros(SHAPE)
        rain[0, 0, 1] = 1.0e-12
        rain[1, 0, 0] = 1.0e-7
        before = values["QNRAIN"].copy()
        report = self.check(values=values, qrain=rain)
        self.assertEqual(report["status"], "NO_AUTHORITY")
        self.assertEqual(report["reason"], "QNRAIN_ZERO_WITH_NONZERO_QRAIN")
        self.assertFalse(report["contract_valid"])
        self.assertFalse(report["accepted"])
        np.testing.assert_array_equal(values["QNRAIN"], before)

    def test_clear_air_zero_rain_number_is_not_filled(self):
        values = arrays()
        values["QNRAIN"][:] = 0.0
        report = self.check(values=values, qrain=np.zeros(SHAPE))
        self.assertTrue(report["contract_valid"])
        self.assertFalse(report["accepted"])
        np.testing.assert_array_equal(values["QNRAIN"], 0.0)

    def test_clear_air_zero_cloud_and_ice_numbers_are_not_filled(self):
        values = arrays()
        values["QNCLOUD"][:] = 0.0
        values["QNICE"][:] = 0.0
        before = {name: value.copy() for name, value in values.items()}
        report = self.check(values=values, qcloud=np.zeros(SHAPE), qice=np.zeros(SHAPE))
        self.assertEqual(report["status"], "STRUCTURAL_CONTRACT_VALID")
        self.assertTrue(report["contract_valid"])
        self.assertFalse(report["accepted"])
        self.assertFalse(report["promotion_eligible"])
        self.assertEqual(report["synthesized_fields"], [])
        for name in AUX_FIELDS:
            np.testing.assert_array_equal(values[name], before[name])

    def test_malformed_rain_mass_is_rejected(self):
        for value, reason in (
            (np.zeros((1,)), "MALFORMED_SHAPE:QRAIN"),
            (np.full(SHAPE, np.nan), "NONFINITE_FIELD:QRAIN"),
            (np.full(SHAPE, -1.0), "NEGATIVE_FIELD:QRAIN"),
            (np.ma.zeros(SHAPE), "MASKED_FIELD:QRAIN"),
        ):
            with self.subTest(reason=reason):
                report = self.check(qrain=value)
                self.assertEqual(report["status"], "REJECTED")
                self.assertEqual(report["reason"], reason)

    def test_malformed_mass_fields_are_rejected_before_declarations(self):
        for mass_name, value, reason in (
            ("QGRAUP", np.zeros((1,)), "MALFORMED_SHAPE:QGRAUP"),
            ("QRAIN", np.full(SHAPE, np.nan), "NONFINITE_FIELD:QRAIN"),
            ("QCLOUD", np.full(SHAPE, -1.0), "NEGATIVE_FIELD:QCLOUD"),
            ("QICE", np.ma.zeros(SHAPE), "MASKED_FIELD:QICE"),
            ("QICE", np.full(SHAPE, 1j), "NONREAL_FIELD:QICE"),
        ):
            for gap in ("evidence", "metadata", "denominator"):
                with self.subTest(mass_name=mass_name, gap=gap):
                    mass = {
                        "QGRAUP": np.zeros(SHAPE),
                        "QRAIN": np.zeros(SHAPE),
                        "QCLOUD": np.zeros(SHAPE),
                        "QICE": np.zeros(SHAPE),
                    }
                    mass[mass_name] = value
                    report = validate_mp37_auxiliaries(
                        arrays(),
                        None if gap == "metadata" else metadata(),
                        None if gap == "evidence" else authority(),
                        qgraup=mass["QGRAUP"],
                        qrain=mass["QRAIN"],
                        qcloud=mass["QCLOUD"],
                        qice=mass["QICE"],
                        expected_shape=SHAPE,
                        expected_denominators=None if gap == "denominator"
                        else EXPECTED_DENOMINATORS,
                    )
                    self.assertEqual(report["status"], "REJECTED")
                    self.assertEqual(report["reason"], reason)
                    self.assertFalse(report["contract_valid"])
                    self.assertFalse(report["accepted"])

    def test_nonreal_mass_is_rejected(self):
        cloud = np.zeros(SHAPE, dtype=np.complex128)
        cloud[0, 0, 0] = 1j
        report = self.check(qcloud=cloud)
        self.assertEqual(report["status"], "REJECTED")
        self.assertEqual(report["reason"], "NONREAL_FIELD:QCLOUD")

    def test_malformed_contract_arguments_do_not_raise(self):
        report = validate_mp37_auxiliaries(
            arrays(), metadata(), authority(), qgraup=np.zeros(SHAPE), qrain=np.zeros(SHAPE),
            qcloud=np.zeros(SHAPE), qice=np.zeros(SHAPE),
            expected_shape=(2, 1), expected_denominators=EXPECTED_DENOMINATORS)
        self.assertEqual(report["status"], "REJECTED")
        self.assertEqual(report["reason"], "INVALID_EXPECTED_SHAPE")
        report = validate_mp37_auxiliaries(
            arrays(), None, authority(), qgraup=np.zeros(SHAPE), qrain=np.zeros(SHAPE),
            qcloud=np.zeros(SHAPE), qice=np.zeros(SHAPE),
            expected_shape=SHAPE, expected_denominators=EXPECTED_DENOMINATORS)
        self.assertEqual(report["status"], "REJECTED")
        self.assertEqual(report["reason"], "INVALID_METADATA_CONTAINER")
        report = validate_mp37_auxiliaries(
            arrays(), metadata(), {"scope": "PRODUCER_BOUND"},
            qgraup=np.zeros(SHAPE), qrain=np.zeros(SHAPE),
            qcloud=np.zeros(SHAPE), qice=np.zeros(SHAPE),
            expected_shape=SHAPE, expected_denominators=EXPECTED_DENOMINATORS)
        self.assertEqual(report["status"], "NO_AUTHORITY")
        self.assertEqual(report["reason"], "AUTHORITY_EVIDENCE_MISSING")
        report = validate_mp37_auxiliaries(
            arrays(), metadata(), authority(), qgraup=np.zeros(SHAPE), qrain=np.zeros(SHAPE),
            qcloud=np.zeros(SHAPE), qice=np.zeros(SHAPE),
            expected_shape=SHAPE, expected_denominators=None)
        self.assertEqual(report["status"], "NO_AUTHORITY")
        self.assertEqual(report["reason"], "EXPECTED_DENOMINATOR_MAPPING_MISSING")

    def test_zero_mass_and_zero_number_needs_declared_authority_but_does_not_fill(self):
        values = arrays()
        values["QNRAIN"][:] = 0.0
        values["QNCLOUD"][:] = 0.0
        values["QNICE"][:] = 0.0
        values["QIB"][:] = 0.0
        before = {name: value.copy() for name, value in values.items()}
        mass = {
            "QGRAUP": np.zeros(SHAPE),
            "QRAIN": np.zeros(SHAPE),
            "QCLOUD": np.zeros(SHAPE),
            "QICE": np.zeros(SHAPE),
        }
        report = self.check(
            values=values,
            qgraup=mass["QGRAUP"],
            qrain=mass["QRAIN"],
            qcloud=mass["QCLOUD"],
            qice=mass["QICE"],
        )
        self.assertEqual(report["status"], "STRUCTURAL_CONTRACT_VALID")
        self.assertTrue(report["contract_valid"])
        self.assertFalse(report["accepted"])
        self.assertFalse(report["promotion_eligible"])
        self.assertEqual(report["synthesized_fields"], [])
        for name in AUX_FIELDS:
            np.testing.assert_array_equal(values[name], before[name])
        for name, value in mass.items():
            np.testing.assert_array_equal(value, 0.0)


if __name__ == "__main__":
    unittest.main()
