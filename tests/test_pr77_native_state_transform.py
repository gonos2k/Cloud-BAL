import re
import unittest

from pr77_native_state_transform import transform, transform_host_main


SLOPE_CHECK = "   call validate_kdm6_slope_states(qci,qrs,nrs,nci,brs, &\n"
LOCAL_CHECK = "          call validate_local_species_states(qrs(i,k,1),nrs(i,k,1), &\n"


def kdm6_source():
    slope_checks = "".join(
        SLOPE_CHECK + "        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp)\n"
        for _ in range(7)
    )
    local_checks = "".join(
        LOCAL_CHECK
        + "               qci(i,k,1),nci(i,k,1),qci(i,k,2),nci(i,k,2), &\n"
        + "               qrs(i,k,3),brs(i,k))\n"
        for _ in range(3)
    )
    return (
        "   module module_mp_kdm6\n"
        "   use, intrinsic :: ieee_arithmetic, only : ieee_is_finite\n"
        "   integer, parameter, private :: PROGB_ABSENT = 0\n"
        "   contains\n"
        "   subroutine kdm6(th, q, qc, qr, qi, qs, qg,             &\n"
        "   real :: z_sum\n"
        "   logical :: pr67_trace_this_call\n"
        "   pr67_trace_this_call = .not. pr67_trace_complete\n"
        "   end subroutine kdm6\n"
        "   subroutine adapter()\n"
        "   real :: number_value\n"
        "   logical :: number_valid\n"
        "         call specific_number_to_volume(ni(i,k,j), dry_density(i,k), "
        "number_value, number_valid)\n"
        "   end subroutine adapter\n"
        "   subroutine kdm62d()\n"
        "   idim = ite-its+1\n"
        "   call validate_kdm6_species_states(qci,qrs,nrs,nci,brs)\n"
        + slope_checks
        + local_checks
        + "   end subroutine kdm62d\n"
        "END MODULE module_mp_kdm6\n"
    )


HOST_MAIN = """PROGRAM wrf

   USE module_wrf_top, only : wrf_init, wrf_dfi, wrf_run, wrf_finalize

   IMPLICIT NONE

  CALL wrf_init
  CALL wrf_dfi
  CALL wrf_run
  CALL wrf_finalize

END PROGRAM wrf
"""


class NativeStateTransformTest(unittest.TestCase):
    def test_kdm6_observes_all_state_validators_without_replacing_them(self):
        transformed = transform(kdm6_source())
        self.assertEqual(transformed.count("call validate_kdm6_species_states("), 1)
        self.assertEqual(transformed.count("call validate_kdm6_slope_states("), 7)
        self.assertEqual(transformed.count("call validate_local_species_states("), 3)
        self.assertEqual(transformed.count("call pr77_scan_slope_state("), 7)
        self.assertEqual(transformed.count("call pr77_scan_local_state("), 3)
        self.assertEqual(transformed.count("call pr77_scan_entry_state("), 1)
        self.assertIn("counts(:,4)", transformed)
        self.assertIn("transfer(moment,0)", transformed)
        self.assertIn("pr75_read_fp_state(thread_id)", transformed)
        self.assertIn("file='pr77_native_species.raw'", transformed)
        self.assertIn("'KDM62D_SLOPE_07'", transformed)
        self.assertIn("'KDM62D_LOCAL_03'", transformed)

        slope_sites = re.findall(
            r"call pr77_scan_slope_state\(.*?'(KDM62D_SLOPE_[0-9]{2})'\)\n"
            r"\s*call validate_kdm6_slope_states",
            transformed,
            re.DOTALL,
        )
        local_sites = re.findall(
            r"call pr77_scan_local_state\(.*?'(KDM62D_LOCAL_[0-9]{2})'\)\n"
            r"\s*call validate_local_species_states",
            transformed,
            re.DOTALL,
        )
        self.assertEqual(slope_sites, [f"KDM62D_SLOPE_{i:02d}" for i in range(1, 8)])
        self.assertEqual(local_sites, [f"KDM62D_LOCAL_{i:02d}" for i in range(1, 4)])

    def test_kdm6_observers_precede_the_unchanged_checks(self):
        transformed = transform(kdm6_source())
        self.assertLess(
            transformed.index("call pr77_scan_entry_state("),
            transformed.index("call validate_kdm6_species_states("),
        )
        self.assertLess(
            transformed.index("call pr77_scan_slope_state("),
            transformed.index("call validate_kdm6_slope_states("),
        )
        self.assertLess(
            transformed.index("call pr77_scan_local_state("),
            transformed.index("call validate_local_species_states("),
        )

    def test_kdm6_transform_rejects_missing_validator_site(self):
        with self.assertRaises(ValueError):
            transform(kdm6_source().replace(LOCAL_CHECK, "", 1))

    def test_host_main_sets_main_and_startup_team_before_wrf_init(self):
        transformed = transform_host_main("\n\n" + HOST_MAIN)
        main_policy = transformed.index("call pr77_apply_and_log('MAIN_STARTUP')")
        team_policy = transformed.index("call pr77_apply_and_log('OMP_STARTUP_TEAM')")
        wrf_init = transformed.index("CALL wrf_init")
        self.assertLess(main_policy, team_policy)
        self.assertLess(team_policy, wrf_init)
        self.assertIn("!$omp parallel", transformed)
        self.assertIn("!$omp critical(pr77_host_fp_log)", transformed)
        self.assertIn("FILE='pr77_host_fp.raw'", transformed)
        self.assertEqual(transformed.count("CALL wrf_dfi"), 1)
        self.assertEqual(transformed.count("CALL wrf_run"), 1)
        self.assertEqual(transformed.count("CALL wrf_finalize"), 1)

    def test_host_transform_rejects_ambiguous_startup_call(self):
        with self.assertRaises(ValueError):
            transform_host_main(HOST_MAIN + "  CALL wrf_init\n")


if __name__ == "__main__":
    unittest.main()
