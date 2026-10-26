from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr92_diffusion_producer_capture", ROOT / "tools/pr92_diffusion_producer_capture.py")
assert SPEC and SPEC.loader
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)
legacy_source = subprocess.run(
    ["git", "show", "HEAD:tools/pr92_diffusion_producer_capture.py"],
    check=True, capture_output=True, text=True).stdout
legacy_namespace: dict[str, object] = {}
exec(compile(legacy_source, "legacy_pr92_diffusion_producer_capture.py", "exec"),
     legacy_namespace)


SOURCE = ("   LOGICAL :: pr87_diff_specified, pr87_capture_rain_diffusion\n"
          "           IF (PRESENT(all_pair_diffusion_tendency32).AND.pr87_diff_channel<=4) THEN\n")


class DiffusionProducerCaptureTests(unittest.TestCase):
    def test_default_selection_preserves_t15_targets_and_rk1(self) -> None:
        transformed = capture.transform_producer(SOURCE)
        legacy = legacy_namespace["transform_producer"](SOURCE)
        self.assertEqual(legacy, transformed)
        self.assertIn("pr92_targets(3,12)", transformed)
        self.assertIn("[3,12])", transformed)
        self.assertIn("all_pair_diffusion_identity(1)==15) THEN", transformed)
        self.assertIn("2,218,13", transformed)
        self.assertNotIn("2,219,13", transformed)

    def test_default_transform_matches_legacy_on_pinned_c14_source(self) -> None:
        source = (ROOT / "docs/evidence/pr91_source_store_contract_20261020/c14/module_em.F").read_text()
        legacy = legacy_namespace["transform_producer"](source)
        self.assertEqual(legacy, capture.transform_producer(source))

    def test_explicit_t39_rk1_cell_selection(self) -> None:
        transformed = capture.transform_producer(
            SOURCE, timestep=39, rk=1, cells=((2, 219, 13),))
        self.assertIn("pr92_targets(3,1)", transformed)
        self.assertIn("2,219,13", transformed)
        self.assertNotIn("2,218,13", transformed)
        self.assertIn("all_pair_diffusion_identity(1)==39.AND.rk_step==1", transformed)

    def test_wrong_timestep_rk_and_cell_are_excluded_by_selection(self) -> None:
        transformed = capture.transform_producer(
            SOURCE, timestep=39, rk=1, cells=((2, 219, 13),))
        guard = "all_pair_diffusion_identity(1)==39.AND.rk_step==1"
        self.assertIn(guard, transformed)
        self.assertNotIn("all_pair_diffusion_identity(1)==15", transformed)
        self.assertIn("2,219,13", transformed)
        self.assertNotIn("2,220,13", transformed)

    def test_invalid_selection_is_rejected(self) -> None:
        for kwargs in ({"timestep": 0}, {"rk": 0}, {"rk": 4},
                       {"cells": ((2, 219),)},
                       {"cells": ((2, 219, 13), (2, 219, 13))}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                capture.transform_producer(SOURCE, **kwargs)

    def test_retarget_replaces_one_legacy_capture_selection(self) -> None:
        legacy = legacy_namespace["transform_producer"](SOURCE)
        transformed = capture.retarget_producer(
            legacy, timestep=39, rk=1, cells=((2, 219, 13),))
        self.assertIn("pr92_targets(3,1)", transformed)
        self.assertIn("2,219,13", transformed)
        self.assertIn("all_pair_diffusion_identity(1)==39.AND.rk_step==1", transformed)
        with self.assertRaisesRegex(ValueError, "legacy producer capture block"):
            capture.retarget_producer(transformed, timestep=40, rk=1,
                                      cells=((2, 219, 13),))


if __name__ == "__main__":
    unittest.main()
