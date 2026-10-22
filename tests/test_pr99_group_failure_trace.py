from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr99_group_failure_trace as trace  # noqa: E402
import pr99_group_failure_capture as capture  # noqa: E402


class GroupFailureTraceTest(unittest.TestCase):
    def test_fixture_captures_first_group_predicate_before_retry(self):
        fixture = ROOT / "tests/fixtures/pr99_group_failure_source.f90"
        source = fixture.read_text()
        transformed = trace.transform(source, expected_sha256=trace.sha256(source))

        self.assertIn("call record_group_failure(i,p,1)", transformed)
        self.assertIn("call record_group_failure(i,p,2)", transformed)
        self.assertIn("group_failure_store_stage", transformed)
        self.assertIn("group_failure_candidate64", transformed)
        self.assertIn("HEX64_CANDIDATE", transformed)
        self.assertIn("HEX32_CARRIERS_DT", transformed)
        self.assertIn("HEX64_NUMBER_BOUNDS", transformed)
        self.assertIn("OPT_bulk_volume_quantum_storage", transformed)
        self.assertIn("HEX64_INACTIVE_MASS_LIMIT", transformed)
        self.assertIn("MERGE('SOURCE_FIRST','BASELINE    ',source_first)", transformed)
        self.assertIn("group_failure_enabled=itimestep==32", transformed)
        capture = transformed.index("CALL write_pr99_group_failure(")
        retry = transformed.index("IF (.NOT.feasible) CALL try_graupel_mixture_trial()")
        self.assertLess(capture, retry)
        post_retry = transformed.index("CALL write_pr99_group_retry_result(")
        self.assertGreater(post_retry, retry)
        self.assertIn("write_pr99_group_retry_result(pr99_cell,pr99_pair,pr99_predicate,feasible)",
                      transformed)

    def test_transform_rejects_unpinned_source(self):
        source = (ROOT / "tests/fixtures/pr99_group_failure_source.f90").read_text()
        with self.assertRaisesRegex(ValueError, "source hash mismatch"):
            trace.transform(source)

    def test_capture_parser_binds_exact_bits_and_post_retry_result(self):
        fixture = ROOT / "tests/fixtures/pr99_group_failure_capture.raw"
        result = capture.parse_capture(fixture)
        event = result["events"][0]
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(event["classification"], "store_rejection")
        self.assertFalse(event["store_succeeded"])
        self.assertTrue(event["post_graupel_mixture_feasible"])
        self.assertIn("host-wide ANY(source_first_pair)", event["attempt_scope"])
        self.assertIn("later outer RK3", event["post_graupel_mixture_scope"])
        self.assertEqual(event["hex"]["HEX64_CANDIDATE"],
                         ["3F50624DE0000000", "408F400000000000"])
        with tempfile.TemporaryDirectory(prefix="pr99-source-first-capture-") as tmp:
            path = Path(tmp) / "source_first.raw"
            source_first_rows = fixture.read_text().replace("BASELINE", "SOURCE_FIRST")
            source_first_rows = source_first_rows.replace(
                "OPT_source_first_fallback F", "OPT_source_first_fallback T")
            path.write_text(source_first_rows)
            source_first = capture.parse_capture(path)["events"][0]
        self.assertEqual(source_first["attempt"], "SOURCE_FIRST")
        self.assertTrue(source_first["post_graupel_mixture_feasible"])

    @unittest.skipUnless(Path("/var/tmp/pr96_native_build_c1_20261021/source/overrides/module_em.F").is_file(),
                         "receipt-pinned C1 source is unavailable")
    def test_scalar_replay_recomputes_candidate_and_exact_store_result_at_o0_o2(self):
        from pr99_group_failure_scalar_replay import replay

        result = replay(ROOT / "tests/fixtures/pr99_group_failure_capture.raw")
        self.assertEqual(result["capture_event_count"], 1)
        self.assertEqual(result["selected_event_index"], 0)
        self.assertEqual([row["optimization"] for row in result["runs"]], ["FREE", "REPRO"])
        for row in result["runs"]:
            self.assertEqual(row["candidate_hex"], ["3F50624DE0000000", "408F400000000000"])
            self.assertEqual(row["store_failure_stage"], 2)
            self.assertEqual(row["group_predicate_input_hex"], ["BF800000", "BF800000"])
            self.assertFalse(row["valid"])
            self.assertTrue(row["group_predicate_reached"])
            self.assertEqual(row["replayed_group_predicate"], 1)
            self.assertEqual(row["valid"], row["captured_store_succeeded"])
            self.assertTrue(row["compiler_sha256"])
            self.assertTrue(row["profile_sha256"])
            self.assertIn("-no-ftz", row["profile_flags"])

    def test_capture_parser_rejects_interleaved_post_retry_result(self):
        contents = (ROOT / "tests/fixtures/pr99_group_failure_capture.raw").read_text()
        post_row = "PR99_GROUP_POST_RETRY_V1 test-run 32 2 17 4 1 T\n"
        intervening = "PR99_GROUP_FAILURE_V1 other-run BASELINE 32 2 18 4 8 10 3 1 2 F\n"
        with tempfile.TemporaryDirectory(prefix="pr99-group-capture-interleaved-") as tmp:
            path = Path(tmp) / "interleaved.raw"
            path.write_text(contents.replace(post_row, intervening + post_row, 1))
            with self.assertRaisesRegex(ValueError, "interleaved PR99 post-retry"):
                capture.parse_capture(path)

    def test_capture_parser_rejects_incomplete_exact_bit_payload(self):
        with tempfile.TemporaryDirectory(prefix="pr99-group-capture-") as tmp:
            path = Path(tmp) / "incomplete.raw"
            path.write_text("PR99_GROUP_FAILURE_V1 run BASELINE 32 2 17 4 8 9 3 1 2 F\n")
            with self.assertRaisesRegex(ValueError, "incomplete PR99 exact-bit payload"):
                capture.parse_capture(path)

    def test_capture_parser_rejects_unknown_rows_and_malformed_booleans(self):
        contents = (ROOT / "tests/fixtures/pr99_group_failure_capture.raw").read_text()
        cases = (
            (contents.replace("CELLS_AND_PAIRS", "UNEXPECTED_ROW\nCELLS_AND_PAIRS", 1),
             "unknown PR99 row"),
            (contents.replace("OPT_joint_constrained_storage T", "OPT_joint_constrained_storage maybe", 1),
             "invalid boolean token"),
            (contents.replace("PR99_GROUP_POST_RETRY_V1 test-run 32 2 17 4 1 T",
                              "PR99_GROUP_POST_RETRY_V1 test-run 32 2 17 4 1 maybe", 1),
             "invalid boolean token"),
        )
        with tempfile.TemporaryDirectory(prefix="pr99-group-capture-strict-") as tmp:
            path = Path(tmp) / "malformed.raw"
            for malformed, error in cases:
                with self.subTest(error=error):
                    path.write_text(malformed)
                    with self.assertRaisesRegex(ValueError, error):
                        capture.parse_capture(path)

    def test_capture_parser_rejects_store_stage_boolean_disagreement(self):
        contents = (ROOT / "tests/fixtures/pr99_group_failure_capture.raw").read_text()
        inconsistent = contents.replace(
            "PR99_GROUP_FAILURE_V1 test-run BASELINE 32 2 17 4 8 9 3 1 2 F",
            "PR99_GROUP_FAILURE_V1 test-run BASELINE 32 2 17 4 8 9 3 1 0 F", 1)
        with tempfile.TemporaryDirectory(prefix="pr99-group-store-consistency-") as tmp:
            path = Path(tmp) / "inconsistent.raw"
            path.write_text(inconsistent)
            with self.assertRaisesRegex(ValueError, "inconsistent PR99 store status/stage"):
                capture.parse_capture(path)

    def test_capture_parser_rejects_pair_option_or_volume_bound_mismatch(self):
        contents = (ROOT / "tests/fixtures/pr99_group_failure_capture.raw").read_text()
        cases = (
            (contents.replace("OPT_strict_mass_pair T", "OPT_strict_mass_pair F", 1),
             "inconsistent PR99 pair options"),
            (contents.replace("HEX64_NUMBER_BOUNDS 0000000000000000 0000000000000000",
                              "HEX64_NUMBER_BOUNDS 3FF0000000000000 4000000000000000", 1),
             "unexpected PR99 volume bounds"),
        )
        with tempfile.TemporaryDirectory(prefix="pr99-group-options-") as tmp:
            path = Path(tmp) / "inconsistent.raw"
            for content, expected in cases:
                with self.subTest(expected=expected):
                    path.write_text(content)
                    with self.assertRaisesRegex(ValueError, expected):
                        capture.parse_capture(path)

    def test_decimal_bound_rendering_is_not_the_validation_source(self):
        contents = (ROOT / "tests/fixtures/pr99_group_failure_capture.raw").read_text()
        readable_only_change = contents.replace("R64_NUMBER_BOUNDS 0.0 0.0",
                                                "R64_NUMBER_BOUNDS 100.0 200.0", 1)
        with tempfile.TemporaryDirectory(prefix="pr99-group-decimal-bounds-") as tmp:
            path = Path(tmp) / "readable-mismatch.raw"
            path.write_text(readable_only_change)
            event = capture.parse_capture(path)["events"][0]
        self.assertEqual(event["number_bounds_r64"], [0.0, 0.0])

    def test_capture_parser_reports_missing_post_status_before_renaming(self):
        contents = (ROOT / "tests/fixtures/pr99_group_failure_capture.raw").read_text()
        incomplete = "\n".join(
            line for line in contents.splitlines()
            if not line.startswith("PR99_GROUP_POST_RETRY_V1")) + "\n"
        with tempfile.TemporaryDirectory(prefix="pr99-group-no-post-status-") as tmp:
            path = Path(tmp) / "missing-post.raw"
            path.write_text(incomplete)
            with self.assertRaisesRegex(ValueError, "missing its post-graupel-mixture status"):
                capture.parse_capture(path)

    @unittest.skipUnless(Path("/var/tmp/pr96_native_build_c1_20261021/source/overrides/module_em.F").is_file(),
                         "receipt-pinned C1 source is unavailable")
    def test_pinned_ifx_core_records_failure_and_preserves_rollback(self):
        original = Path("/var/tmp/pr96_native_build_c1_20261021/source/overrides/module_em.F")
        transformed = trace.transform(original.read_text())
        module_end = transformed.index("end module cloud_bal_joint_transport") + len(
            "end module cloud_bal_joint_transport")
        module = transformed[:module_end] + "\n"
        harness = ROOT / "tests/test_pr99_group_failure_core.f90"
        profile = ROOT / "tests/intel_toolchain.sh"
        for flag_set in ("FREE", "REPRO"):
            with self.subTest(flag_set=flag_set), tempfile.TemporaryDirectory(
                    prefix=f"pr99-group-failure-{flag_set.lower()}-", dir="/var/tmp") as tmp:
                scratch = Path(tmp)
                (scratch / "core.f90").write_text(module)
                (scratch / "driver.f90").write_bytes(harness.read_bytes())
                exe = scratch / "group_failure.exe"
                build = subprocess.run(
                    ["bash", "-c",
                     'source "$1"; if [[ $3 == FREE ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                     'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi; '
                     '"$CLOUD_BAL_FC" "${flags[@]}" -free core.f90 driver.f90 '
                     '-module "$PWD" -o "$2"',
                     "pr99-group-failure-core", str(profile), str(exe), flag_set],
                    cwd=scratch, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    check=False)
                self.assertEqual(build.returncode, 0, build.stdout)
                run = subprocess.run(
                    ["bash", "-c", 'source "$1" && exec "$2"',
                     "pr99-group-failure-core", str(profile), str(exe)],
                    cwd=scratch, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    check=False)
                self.assertEqual(run.returncode, 0, run.stdout)
                self.assertIn("PR99_GROUP_FAILURE_CORE_PASS", run.stdout)


if __name__ == "__main__":
    unittest.main()
