#!/usr/bin/env python3
"""Deterministic tests for the fail-closed legacy derived-cloud audit."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "legacy_deriv_safety"
MODULE_PATH = REPO / "tools" / "audit_legacy_deriv_safety.py"
SPEC = importlib.util.spec_from_file_location("legacy_deriv_safety", MODULE_PATH)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class LegacyDerivSafetyTest(unittest.TestCase):
    def test_config_only_off_is_not_source_safety(self) -> None:
        source = (FIXTURES / "config_only_laps_deriv_sub.f").read_text()
        result = AUDIT.analyze_source(source)
        self.assertFalse(result["evaporation_compile_time_off"])
        self.assertEqual(result["cloud_bogus_w_authority"], "NOT_LITERAL_FALSE")

        namelist = AUDIT.parse_deriv_namelist((FIXTURES / "deriv.nl").read_text())
        self.assertEqual(namelist["mode_evap"], 0)
        self.assertEqual(namelist["mode_evap_occurrences"], 1)
        self.assertIs(namelist["l_bogus_radar_w"], False)
        self.assertEqual(namelist["l_bogus_radar_w_occurrences"], 1)

    def test_constant_false_source_is_proved_safe(self) -> None:
        source = (FIXTURES / "safe_laps_deriv_sub.f").read_text()
        result = AUDIT.analyze_source(source)
        self.assertTrue(result["evaporation_compile_time_off"])
        self.assertEqual(
            result["cloud_bogus_w_authority"], "DISABLED_AT_CALL_SITE"
        )
        self.assertTrue(result["radar_bogus_w_compile_time_off"])
        self.assertTrue(result["cloud_bogus_w_compile_time_off"])
        self.assertTrue(result["cloud_output_initialized"])
        self.assertTrue(result["cloud_output_not_normal"])

    def test_focused_deriv_source_is_compile_time_safe(self) -> None:
        source = (REPO / "src/deriv/laps_deriv_sub.f").read_text()
        self.assertTrue(AUDIT.source_is_safe(AUDIT.analyze_source(source)))

    def test_else_arm_of_constant_false_is_not_proved_safe(self) -> None:
        source = """      subroutine x
      if(.false.)then
        continue
      else
        call rfill_evap
      endif
      end
"""
        self.assertFalse(AUDIT.analyze_source(source)["evaporation_compile_time_off"])

    def test_false_literal_inside_expression_is_not_a_safety_guard(self) -> None:
        source = """      subroutine laps_deriv_sub
      if(identity(.false.))then
        call rfill_evap
      endif
      end
"""
        self.assertFalse(AUDIT.analyze_source(source)["evaporation_compile_time_off"])

    def test_patch_noop_requires_literal_cloud_call_authority(self) -> None:
        safe = (FIXTURES / "safe_laps_deriv_sub.f").read_text()
        unsafe = safe.replace(
            "     1 icing,.false.,w_3d,istatus)",
            "     1 icing,l_flag_bogus_w,w_3d,istatus)",
        )
        self.assertFalse(AUDIT.source_is_safe(AUDIT.analyze_source(unsafe)))
        with self.assertRaises(ValueError):
            AUDIT.render_safety_patch(unsafe, "src/deriv/laps_deriv_sub.f")

    def test_every_cloud_call_must_have_one_literal_authority(self) -> None:
        safe = (FIXTURES / "safe_laps_deriv_sub.f").read_text()
        extra_call = """      call get_cloud_deriv(i4time,nx,ny,nz,clouds,cld_hts,
     1 temp,rh,hgt,pres,istat_ref,ref,dx,pcpmask,ibase,itop,
     1 iflag,slwc,cice,thresh,l_type,ctype,l_mvd,mvd,l_ice,
     1 icing,l_flag_bogus_w,w_3d,istatus)
"""
        source = safe.replace(
            "      logical l_evap_radar", extra_call + "      logical l_evap_radar"
        )
        result = AUDIT.analyze_source(source)
        self.assertFalse(result["cloud_bogus_w_compile_time_off"])
        self.assertFalse(AUDIT.source_is_safe(result))

    def test_cloud_argument_position_uses_top_level_commas(self) -> None:
        safe = (FIXTURES / "safe_laps_deriv_sub.f").read_text()
        nested = safe.replace(
            "get_cloud_deriv(i4time,nx,ny,nz",
            "get_cloud_deriv(foo(i4time,nx),ny,nz",
        )
        quoted = safe.replace(
            "get_cloud_deriv(i4time,nx,ny,nz",
            "get_cloud_deriv('i4time,nx',ny,nz",
        )
        hollerith = safe.replace(
            "get_cloud_deriv(i4time,nx,ny,nz",
            "get_cloud_deriv(3Ha,b,ny,nz",
        )
        spaced_hollerith = safe.replace(
            "get_cloud_deriv(i4time,nx,ny,nz",
            "get_cloud_deriv(1 0 Habcdefgh,ij,ny,nz",
        )
        for source in (nested, quoted, hollerith, spaced_hollerith):
            with self.subTest(source=source):
                result = AUDIT.analyze_source(source)
                self.assertFalse(result["cloud_bogus_w_compile_time_off"])
                self.assertFalse(AUDIT.source_is_safe(result))

    def test_unconditional_get_radar_deriv_is_not_disabled(self) -> None:
        source = """      subroutine laps_deriv_sub
      call get_deriv_parms(mode_evap,l_bogus_radar_w,istatus)
      l_evap_radar = .false.
      mode_evap = 0
      l_bogus_radar_w = .false.
      l_flag_bogus_w = .false.
      call get_cloud_deriv(l_flag_bogus_w,istatus)
      call get_radar_deriv(istatus)
      end
"""
        self.assertFalse(
            AUDIT.analyze_source(source)["radar_bogus_w_compile_time_off"]
        )

    def test_elseif_after_false_arm_is_not_inherited_as_false(self) -> None:
        source = """      subroutine laps_deriv_sub
      if(.false.)then
        continue
      elseif(runtime_flag)then
        call rfill_evap
      endif
      end
"""
        self.assertFalse(AUDIT.analyze_source(source)["evaporation_compile_time_off"])

    def test_blank_and_comment_inside_continuation_do_not_break_if_stack(self) -> None:
        source = """      subroutine laps_deriv_sub
      if(runtime_a .and.

! a legal comment between fixed-form continuation records
     1   runtime_b)then
        continue
      endif
      if(.false. .and. l_evap_radar)then
        call rfill_evap
      endif
      end
"""
        self.assertTrue(AUDIT.analyze_source(source)["evaporation_compile_time_off"])

    def test_patch_generator_is_deterministic_and_reviewable(self) -> None:
        source_path = FIXTURES / "config_only_laps_deriv_sub.f"
        source = source_path.read_text()
        first = AUDIT.render_safety_patch(
            source, "src/deriv/laps_deriv_sub.f"
        )
        second = AUDIT.render_safety_patch(
            source, "src/deriv/laps_deriv_sub.f"
        )
        self.assertEqual(first, second)
        self.assertIn("+      l_evap_radar = .false.", first)
        self.assertIn("+      mode_evap = 0", first)
        self.assertIn("+      l_bogus_radar_w = .false.", first)
        self.assertIn("+      l_flag_bogus_w = .false.", first)
        self.assertIn("+      w_3d = r_missing_data", first)
        self.assertIn("+     1 icing,.false.,w_3d,istatus)", first)
        self.assertIn("+      if(.false. .and. l_evap_radar)then", first)
        self.assertIn(
            "+      if(.false.)then",
            first,
        )
        added = [
            line
            for line in first.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        self.assertTrue(added)
        self.assertTrue(all(line == line.rstrip() for line in added))
        self.assertTrue(all(len(line[1:]) <= 72 for line in added))
        self.assertEqual(
            AUDIT.render_safety_patch(
                (FIXTURES / "safe_laps_deriv_sub.f").read_text(),
                "src/deriv/laps_deriv_sub.f",
            ),
            "",
        )

    def test_makefile_job_and_compiler_selection(self) -> None:
        make = AUDIT.parse_makefile(
            (FIXTURES / "Makefile").read_text(),
            Path("laps_deriv_sub.f"),
        )
        self.assertTrue(make["source_selected_once"])
        self.assertEqual(make["executable_name"], "klps_anal_derv.exe")
        self.assertTrue(
            AUDIT.job_selects_binary(
                (FIXTURES / "job.csh").read_text(), make["executable_name"]
            )
        )
        self.assertTrue(
            AUDIT.parse_make_config((FIXTURES / "makefile.inc").read_text())[
                "ifx_selected"
            ]
        )
        self.assertFalse(AUDIT.parse_make_config("FC = ifort\n")["ifx_selected"])
        self.assertFalse(
            AUDIT.parse_make_config("FC = ifx\nCPP = ifort\n")["ifx_selected"]
        )
        self.assertFalse(
            AUDIT.job_selects_binary(
                "# mpiexec ./klps_anal_derv.exe\nmpiexec ./other.exe\n",
                "klps_anal_derv.exe",
            )
        )

    def test_duplicate_namelist_authority_is_rejected(self) -> None:
        result = AUDIT.parse_deriv_namelist(
            "MODE_EVAP=0, MODE_EVAP=1\n"
            "L_BOGUS_RADAR_W=.false., L_BOGUS_RADAR_W=.true.\n"
        )
        self.assertIsNone(result["mode_evap"])
        self.assertIsNone(result["l_bogus_radar_w"])
        self.assertEqual(result["mode_evap_occurrences"], 2)
        self.assertEqual(result["l_bogus_radar_w_occurrences"], 2)

    def test_output_artifacts_never_replace_or_enter_original_tree(self) -> None:
        scratch = REPO / "scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            output = Path(temporary) / "audit.json"
            AUDIT.write_new_file(output, "first\n")
            with self.assertRaises(FileExistsError):
                AUDIT.write_new_file(output, "second\n")
        self.assertTrue(
            AUDIT.output_is_in_protected_original_tree(
                REPO.parent / "ANAL" / "NE57" / "forbidden.patch"
            )
        )
        self.assertFalse(
            AUDIT.output_is_in_protected_original_tree(
                REPO / "scratch" / "allowed.patch"
            )
        )

    @unittest.skipUnless(
        shutil.which("cc") and shutil.which("nm") and shutil.which("objdump"),
        "native binary inspection tools unavailable",
    )
    def test_binary_direct_call_edge_is_fail_closed(self) -> None:
        scratch = REPO / "scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            root = Path(temporary)
            source = root / "fixture.c"
            source.write_text(
                "void rfill_evap_(void) {}\n"
                "void get_radar_deriv_(void) {}\n"
                "void laps_deriv_sub_(void) { rfill_evap_(); get_radar_deriv_(); }\n"
                "int main(void) { laps_deriv_sub_(); return 0; }\n"
            )
            unsafe_binary = root / "unsafe"
            subprocess.run(
                ["cc", "-O0", "-fno-inline", str(source), "-o", str(unsafe_binary)],
                check=True,
            )
            unsafe = AUDIT.binary_call_edge(unsafe_binary)
            self.assertTrue(unsafe["auditable"])
            self.assertTrue(unsafe["direct_rfill_evap_call"])
            self.assertTrue(unsafe["direct_get_radar_deriv_call"])

            source.write_text(
                "void rfill_evap_(void) {}\n"
                "void get_radar_deriv_(void) {}\n"
                "void laps_deriv_sub_(void) {}\n"
                "int main(void) { laps_deriv_sub_(); return 0; }\n"
            )
            safe_binary = root / "safe"
            subprocess.run(
                ["cc", "-O0", "-fno-inline", str(source), "-o", str(safe_binary)],
                check=True,
            )
            safe = AUDIT.binary_call_edge(safe_binary)
            self.assertTrue(safe["auditable"])
            self.assertFalse(safe["direct_rfill_evap_call"])
            self.assertFalse(safe["direct_get_radar_deriv_call"])

    def test_report_blocks_when_only_configuration_is_off(self) -> None:
        parser = AUDIT.build_parser()
        args = parser.parse_args(
            [
                "--source",
                str(FIXTURES / "config_only_laps_deriv_sub.f"),
                "--makefile",
                str(FIXTURES / "Makefile"),
                "--make-config",
                str(FIXTURES / "makefile.inc"),
                "--job-script",
                str(FIXTURES / "job.csh"),
                "--namelist",
                str(FIXTURES / "deriv.nl"),
            ]
        )
        report = AUDIT.run_audit(args)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("source_authority", report["blocked_stages"])
        self.assertIn("binary_legacy_calls", report["blocked_stages"])
        self.assertIn("production_provenance", report["blocked_stages"])
        self.assertEqual(
            report["stages"]["production_provenance"]["status"], "BLOCKED"
        )


if __name__ == "__main__":
    unittest.main()
