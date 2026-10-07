#!/usr/bin/env python3
"""Standalone contract tests for the PR65 NC donor face replay."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr65_nc_donor_replay import float32_half_ulp, flux5, gamma32, validate  # noqa: E402


def capture_rows() -> tuple[str, str]:
    faces = []
    hosts = []
    nc_tendencies: dict[int, float] = {}
    for rk in (1, 2, 3):
        for call, upper_flux in (("QC", 0.0), ("NC", -float(rk))):
            for kind, count in ((("FACE_Y", 13), ("FACE_X", 18), ("FACE_Z", 9)) if rk < 3 else ()):
                payload = [0.0] * count
                if kind == "FACE_Y":
                    payload[-2:] = [1.0, 1.0]
                elif kind == "FACE_X":
                    payload[-2:] = [1.0, 1.0]
                    if call == "NC":
                        payload[2:4] = [0.5, 0.5]
                        payload[4:10] = [1, 2, 4, 8, 16, 32]
                        payload[10:16] = payload[4:10]
                        payload[0] = flux5(payload[4:10], payload[2], 20.0)[0]
                        payload[1] = flux5(payload[10:16], payload[3], 20.0)[0]
                if kind == "FACE_Y" and call == "NC":
                    payload[2:4] = [0.5, 0.5]
                    payload[4:11] = [1, 1, 1, 1, 1, 1, 1]
                    payload[0] = flux5(payload[4:10], payload[2], 20.0)[0]
                    payload[1] = flux5(payload[5:11], payload[3], 20.0)[0]
                else:
                    if kind == "FACE_Y":
                        payload[-2:] = [1.0, 1.0]
                if kind == "FACE_Z":
                    payload[1] = upper_flux
                    payload[3] = 1.0
                    payload[5] = upper_flux
                    payload[6] = 1.0
                    payload[8] = -1.0
                faces.append(
                    f"{kind} {rk} 3 172 76 1 " + " ".join(f"{value:.8g}" for value in payload)
                )
            if call == "NC" and rk < 3:
                y = [line.split() for line in faces[-3:]][0]
                x = [line.split() for line in faces[-3:]][1]
                z = [line.split() for line in faces[-3:]][2]
                yv, xv, zv = [list(map(float, row[6:])) for row in (y, x, z)]
                advect = -(yv[-1] * yv[-2] * (yv[1] - yv[0])) - xv[-1] * xv[-2] * (xv[1] - xv[0]) - zv[8] * (zv[1] - zv[0])
                nc_tendencies[rk] = advect
            else:
                advect = 0.0
            new_value = advect / 95000.0 if rk < 3 else 0.0
            numbers = [
                0.0, 0.0, 0.0, new_value, 0.0, advect, 1.0,
                1.0, 0.0, 0.0, 0.0, 95000.0, 1.0, 95000.0, 95000.0,
            ]
            hosts.append(
                f"HOST {call}_AFTER {rk} 172 76 1 3 3 "
                + " ".join(f"{value:.8g}" for value in numbers)
            )
    return "\n".join(faces) + "\n", "\n".join(hosts) + "\n"


class PR65NCDonorReplayTest(unittest.TestCase):
    def test_reconstructs_target_face_divergence_and_shared_carrier(self) -> None:
        face_text, host_text = capture_rows()
        with tempfile.TemporaryDirectory() as directory:
            face_path = Path(directory) / "faces.raw"
            host_path = Path(directory) / "host.raw"
            face_path.write_text(face_text)
            host_path.write_text(host_text)
            result = validate(face_path, host_path)
        self.assertEqual(result["face_row_count"], 12)
        rk1 = result["tendency_reconstruction"]["rk1"]["nc"]
        self.assertEqual(rk1["z_tendency"], -1.0)
        self.assertEqual(rk1["sum_tendency"], -1.0)
        self.assertTrue(result["completed_host_updates"]["rk1"]["shared_carrier_fields_match"])

    def test_rejects_incomplete_face_capture(self) -> None:
        face_text, host_text = capture_rows()
        with tempfile.TemporaryDirectory() as directory:
            face_path = Path(directory) / "faces.raw"
            host_path = Path(directory) / "host.raw"
            face_path.write_text("\n".join(face_text.splitlines()[:-1]) + "\n")
            host_path.write_text(host_text)
            with self.assertRaisesRegex(ValueError, "six face rows"):
                validate(face_path, host_path)

    def test_rejects_donor_face_time_and_nan_mutations(self) -> None:
        face_text, host_text = capture_rows()
        lines = face_text.splitlines()
        nc_x_index = next(i for i, line in enumerate(lines) if line.startswith("FACE_X 1 3") and i > 2)
        donor_mutation = lines.copy()
        donor_fields = donor_mutation[nc_x_index].split()
        donor_fields[10] = str(float(donor_fields[10]) + 2.0)
        donor_mutation[nc_x_index] = " ".join(donor_fields)
        with tempfile.TemporaryDirectory() as directory:
            face_path = Path(directory) / "faces.raw"
            host_path = Path(directory) / "host.raw"
            host_path.write_text(host_text)
            face_path.write_text("\n".join(donor_mutation) + "\n")
            with self.assertRaisesRegex(ValueError, "donor reconstruction"):
                validate(face_path, host_path)

            face_mutation = lines.copy()
            face_fields = face_mutation[nc_x_index].split()
            face_fields[6] = str(float(face_fields[6]) + 0.25)
            face_mutation[nc_x_index] = " ".join(face_fields)
            face_path.write_text("\n".join(face_mutation) + "\n")
            with self.assertRaisesRegex(ValueError, "donor reconstruction"):
                validate(face_path, host_path)

            nan_mutation = lines.copy()
            nan_fields = nan_mutation[nc_x_index].split()
            nan_fields[6] = "nan"
            nan_mutation[nc_x_index] = " ".join(nan_fields)
            face_path.write_text("\n".join(nan_mutation) + "\n")
            with self.assertRaisesRegex(ValueError, "non-finite"):
                validate(face_path, host_path)

            face_path.write_text(face_text)
            with self.assertRaisesRegex(ValueError, "time_step"):
                validate(face_path, host_path, -20.0)

            host_mutation = host_text.splitlines()
            for stage_name in ("QC_AFTER", "NC_AFTER"):
                after_index = next(i for i, line in enumerate(host_mutation) if line.startswith(f"HOST {stage_name} 1 "))
                host_fields = host_mutation[after_index].split()
                host_fields[20] = "2.0"  # preserve the shared carrier but invalidate the completed NC update
                host_mutation[after_index] = " ".join(host_fields)
            host_path.write_text("\n".join(host_mutation) + "\n")
            with self.assertRaisesRegex(ValueError, "completed update"):
                validate(face_path, host_path)

        donor = [1, 2, 4, 8, 16, 32]
        self.assertNotEqual(flux5(donor, 0.5, 20.0)[0], flux5(donor, 0.5, -20.0)[0])

    def test_subnormal_roundoff_and_finite_extreme_input(self) -> None:
        self.assertEqual(float32_half_ulp(1.0e-45), 2.0**-150)
        face_text, host_text = capture_rows()
        lines = face_text.splitlines()
        nc_x_index = next(i for i, line in enumerate(lines) if line.startswith("FACE_X 1 3") and i > 2)
        extreme_fields = lines[nc_x_index].split()
        extreme_fields[10] = "1e300"
        lines[nc_x_index] = " ".join(extreme_fields)
        with tempfile.TemporaryDirectory() as directory:
            face_path = Path(directory) / "faces.raw"
            host_path = Path(directory) / "host.raw"
            face_path.write_text("\n".join(lines) + "\n")
            host_path.write_text(host_text)
            with self.assertRaisesRegex(ValueError, "face value"):
                validate(face_path, host_path)

    def test_update_bound_includes_cancelling_tendency_operands(self) -> None:
        face_text, host_text = capture_rows()
        face_lines = face_text.splitlines()
        qc_z_index = next(i for i, line in enumerate(face_lines) if line.startswith("FACE_Z 1 3"))
        qc_z_fields = face_lines[qc_z_index].split()
        qc_z_fields[7] = "1e8"  # upper interface flux gives QC advect_tend=1e8
        face_lines[qc_z_index] = " ".join(qc_z_fields)
        host_lines = host_text.splitlines()
        qc_index = next(i for i, line in enumerate(host_lines) if line.startswith("HOST QC_AFTER 1 "))
        fields = host_lines[qc_index].split()
        fields[12] = "-100000000.0"  # sc_tend
        fields[13] = "100000000.0"   # advect_tend
        combined = float(fields[14]) * float(fields[13]) + float(fields[12])
        fields[11] = str(combined / 95000.0)
        host_lines[qc_index] = " ".join(fields)
        with tempfile.TemporaryDirectory() as directory:
            face_path = Path(directory) / "faces.raw"
            host_path = Path(directory) / "host.raw"
            face_path.write_text("\n".join(face_lines) + "\n")
            host_path.write_text("\n".join(host_lines) + "\n")
            result = validate(face_path, host_path)
        row = result["completed_host_updates"]["rk1"]["qc"]
        simple_bound = gamma32(8) * abs(combined) / float(row["den_new"])
        self.assertGreater(float(row["completed_update_binary32_roundoff_bound"]), simple_bound)


if __name__ == "__main__":
    unittest.main()
