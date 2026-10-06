#!/usr/bin/env python3
"""Focused parser tests for PR63 native transition receipts."""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr63_transition_replay as replay


STAGES = ["PRE_RK", "RK_STAGE_END", "RK_STAGE_END", "RK_STAGE_END",
          "PRE_MOIST_PREP", "POST_MOIST_PREP", "PRE_MICROPHYSICS",
          "POST_MICROPHYSICS"]


def mask_bytes(*, qmin: float = 1e-15, last_value: int = 0,
               wrong_last_stage: bool = False,
               wrong_last_rk: bool = False) -> bytes:
    result = bytearray()
    bounds = (1, 3, 1, 3, 1, 1, 1, 3, 1, 3, 1, 1)
    for index, stage in enumerate(STAGES):
        if wrong_last_stage and index == len(STAGES) - 1:
            stage = "EXTRA_POST"
        result.extend(replay.MASK_MAGIC)
        result.extend(stage.encode("ascii").ljust(32, b" "))
        rkstep = (0 if index == 0 else index if index <= 3 else 4)
        if wrong_last_rk and index == 7:
            rkstep = 3
        result.extend(struct.pack(">14i", 1, rkstep, *bounds))
        result.extend(struct.pack(">f", qmin))
        values = np.zeros((3, 1, 3), dtype=">i4")
        if index == len(STAGES) - 1:
            values[1, 0, 1] = last_value
        result.extend(values.tobytes(order="C"))
    return bytes(result)


def fake_dump(*, timestep: int = 1, stage: int = 1) -> dict:
    bounds = {"ids": 1, "ide": 3, "jds": 1, "jde": 3,
              "kds": 1, "kde": 1, "ims": 1, "ime": 3,
              "jms": 1, "jme": 3, "kms": 1, "kme": 1,
              "its": 2, "ite": 2, "jts": 2, "jte": 2,
              "kts": 1, "kte": 1}
    fields = {name: np.zeros((1, 1, 1), dtype=np.float32)
              for name in ("QC", "NC", "QG", "BG")}
    return {"itimestep": timestep, "stage": stage, "bounds": bounds,
            "params": (20., 1., 1., 1., 1.),
            "fields": fields}


class TransitionReplayTests(unittest.TestCase):
    def test_reads_valid_header_and_mask_bits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.bin"
            path.write_bytes(mask_bytes(last_value=5))
            records = replay.read_masks(path)
        self.assertEqual(len(records), 8)
        self.assertEqual(records[-1]["stage"], "POST_MICROPHYSICS")
        self.assertEqual(int(records[-1]["mask"][1, 0, 1]), 5)

    def test_rejects_truncated_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.bin"
            path.write_bytes(replay.MASK_MAGIC)
            with self.assertRaisesRegex(ValueError, "truncated mask header"):
                replay.read_masks(path)

    def test_rejects_nonfinite_or_nonpositive_qmin(self) -> None:
        for qmin in (0.0, float("inf"), float("nan")):
            with self.subTest(qmin=qmin), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "mask.bin"
                path.write_bytes(mask_bytes(qmin=qmin))
                with self.assertRaisesRegex(ValueError, "invalid runtime qmin"):
                    replay.read_masks(path)

    def test_rejects_unsupported_mask_bits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.bin"
            path.write_bytes(mask_bytes(last_value=8))
            with self.assertRaisesRegex(ValueError, "unsupported bits"):
                replay.read_masks(path)

    def test_rejects_missing_or_duplicate_stage_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.bin"
            path.write_bytes(mask_bytes(wrong_last_stage=True))
            with self.assertRaisesRegex(ValueError, "unexpected, duplicate, or missing"):
                replay.read_masks(path)

    def test_rejects_transition_and_native_timestep_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            masks = directory / "mask.bin"
            pre, post = directory / "pre.raw", directory / "post.raw"
            masks.write_bytes(mask_bytes())
            pre.write_bytes(b"pre")
            post.write_bytes(b"post")
            with patch.object(replay, "read_dump", side_effect=[fake_dump(timestep=2),
                                                                  fake_dump(timestep=2, stage=2)]):
                with self.assertRaisesRegex(ValueError, "transition and KDM6 call timesteps differ"):
                    replay.summarize(masks, pre, post)

    def test_rejects_wrong_kdm6_pre_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            masks = directory / "mask.bin"
            pre, post = directory / "pre.raw", directory / "post.raw"
            masks.write_bytes(mask_bytes())
            pre.write_bytes(b"pre")
            post.write_bytes(b"post")
            with patch.object(replay, "read_dump", side_effect=[fake_dump(stage=2),
                                                                  fake_dump(stage=2)]):
                with self.assertRaisesRegex(ValueError, "stages must be pre=1 and post=2"):
                    replay.summarize(masks, pre, post)

    def test_rejects_wrong_post_timestep(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            masks = directory / "mask.bin"
            pre, post = directory / "pre.raw", directory / "post.raw"
            masks.write_bytes(mask_bytes())
            pre.write_bytes(b"pre")
            post.write_bytes(b"post")
            with patch.object(replay, "read_dump", side_effect=[fake_dump(stage=1),
                                                                  fake_dump(timestep=2, stage=2)]):
                with self.assertRaisesRegex(ValueError, "KDM6 pre/post timesteps differ"):
                    replay.summarize(masks, pre, post)

    def test_rejects_wrong_rk_stage_indices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.bin"
            path.write_bytes(mask_bytes(wrong_last_rk=True))
            with self.assertRaisesRegex(ValueError, "unexpected RK-stage indices"):
                replay.read_masks(path)

    def test_rejects_mask_that_does_not_cover_kdm6_active_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            masks = directory / "mask.bin"
            pre, post = directory / "pre.raw", directory / "post.raw"
            masks.write_bytes(mask_bytes())
            pre.write_bytes(b"pre")
            post.write_bytes(b"post")
            uncovered = fake_dump(stage=1)
            uncovered["bounds"]["ite"] = 4
            post_uncovered = fake_dump(stage=2)
            post_uncovered["bounds"]["ite"] = 4
            with patch.object(replay, "read_dump", side_effect=[uncovered, post_uncovered]):
                with self.assertRaisesRegex(ValueError, "KDM6 active i window is not fully covered"):
                    replay.summarize(masks, pre, post)


if __name__ == "__main__":
    unittest.main()
