import unittest

from pr77_native_state_run import check_startup_policy


class StartupPolicyReceiptTest(unittest.TestCase):
    def test_main_and_unique_complete_team_preserve_other_bits(self):
        trace = ('PR77_HOST_FP,MAIN_STARTUP,00009FFD,00001FBD,11\n'
                 'PR77_HOST_FP,OMP_STARTUP_TEAM,00001FBD,00001FBD,11\n'
                 'PR77_HOST_FP,OMP_STARTUP_TEAM,00009FC0,00001F80,12\n')
        self.assertEqual(check_startup_policy(trace, 2)['startup_team_threads'], [11, 12])

    def test_rejects_missing_duplicate_or_unrelated_bit_changes(self):
        main = 'PR77_HOST_FP,MAIN_STARTUP,00009FFD,00001FBD,11\n'
        worker = 'PR77_HOST_FP,OMP_STARTUP_TEAM,00009FFD,00001FBD,11\n'
        for trace in (main, main + worker, main + worker + worker,
                      (main + worker + worker.replace(',11', ',12')).replace('00001FBD', '00001F80'),
                      main + 'garbage\n'):
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                check_startup_policy(trace, 2)


if __name__ == '__main__':
    unittest.main()
