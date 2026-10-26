from pathlib import Path
import struct
import sys
import tempfile
import unittest
import copy

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr101_upper_wind_fortran_replay import (  # noqa: E402
    DIFFUSION_SOURCE, _paired_records, extract_routine, generate,
)
from pr101_upper_wind_replay import MAGIC, VERSION, Record, compare, factor_separation, replay_face  # noqa: E402


def record(component: str) -> Record:
    face_i, face_j = (136, 16) if component == "u" else (135, 17)
    bounds = dict(ids=1, ide=234, jds=1, jde=282, kds=1, kde=40,
                  ims=-4, ime=240, jms=-4, jme=288, kms=1, kme=40,
                  its=1, ite=234, jts=1, jte=282, kts=1, kte=39)
    flags = dict(open_xs=False, open_xe=False, open_ys=False, open_ye=False,
                 specified=False, nested=False, periodic_x=False, polar=False)
    x = Record(component, 1, 1, 20, face_i, face_j, bounds, 1, 4, 0, flags,
               np.float32(0), np.float32(1), np.float32(1))
    x.c1 = {k: np.float32(0) for k in (37, 38, 39)}
    x.c2 = {k: np.float32(1) for k in (37, 38, 39)}
    x.tendency = {k: np.float32(1) for k in (37, 38, 39)}
    for k in (37, 38, 39):
        for j in range(face_j-1, face_j+2):
            for i in range(face_i-1, face_i+2):
                x.values[i,k,j] = np.float32(i*i + 2*j*j)
                x.xkmhd[i,k,j] = np.float32(1)
    for j in range(face_j-1, face_j+2):
        for i in range(face_i-1, face_i+2):
            x.metrics[i,j] = dict.fromkeys(
                ("mut", "msfux", "msfuy", "msfvx", "msfvx_inv", "msfvy", "msftx", "msfty"),
                np.float32(1))
    return x


def write_record(stream, x: Record, phase: int, tendency: float) -> None:
    b = x.bounds
    header = [MAGIC, VERSION, 1 if x.component == "u" else 2, phase, x.rk_step,
              x.time_step, x.face_i, x.face_j,
              *(b[n] for n in ("ids","ide","jds","jde","kds","kde","ims","ime",
                               "jms","jme","kms","kme","its","ite","jts","jte","kts","kte")),
              x.diff_opt, x.km_opt, x.diff_6th_opt]
    stream.write(struct.pack(">29i", *header))
    stream.write(struct.pack(">8i", *(int(x.flags[n]) for n in
        ("open_xs","open_xe","open_ys","open_ye","specified","nested","periodic_x","polar"))))
    stream.write(struct.pack(">3f", x.khdif, x.rdx, x.rdy))
    for k in (37,38,39):
        stream.write(struct.pack(">2f", x.c1[k], x.c2[k]))
        for j in range(x.face_j-1,x.face_j+2):
            for i in range(x.face_i-1,x.face_i+2):
                stream.write(struct.pack(">2f", x.values[i,k,j], x.xkmhd[i,k,j]))
        stream.write(struct.pack(">f", tendency))
    for j in range(x.face_j-1,x.face_j+2):
        for i in range(x.face_i-1,x.face_i+2):
            m = x.metrics[i,j]
            stream.write(struct.pack(">2i8f", i,j,*(m[n] for n in
                ("mut","msfux","msfuy","msfvx","msfvx_inv","msfvy","msftx","msfty"))))


class UpperWindReplayTest(unittest.TestCase):
    def test_unit_coefficient_quadratic_field_has_known_laplacian(self):
        for component in ("u", "v"):
            with self.subTest(component=component):
                self.assertEqual(float(replay_face(record(component), 1)[39]), 7.0)

    def test_inactive_boundary_face_is_rejected(self):
        x = record("v")
        x.flags["open_ys"] = True
        x.bounds["jds"] = x.face_j
        x.bounds["jts"] = x.face_j
        with self.assertRaisesRegex(ValueError, "outside the native diffusion loop"):
            replay_face(x, 1)



    def test_source_driver_rejects_changed_pre_post_operands(self):
        x, after = record("u"), record("u")
        after.values[136, 39, 16] = np.float32(123)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pr101_upper_wind.raw"
            with path.open("wb") as stream:
                write_record(stream, x, 1, 1)
                write_record(stream, after, 2, 7)
            with self.assertRaisesRegex(ValueError, "operands changed"):
                _paired_records(path)

    def test_source_driver_rejects_nonfinite_capture_operands(self):
        x = record("u")
        x.values[136, 39, 16] = np.float32(np.nan)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pr101_upper_wind.raw"
            with path.open("wb") as stream:
                write_record(stream, x, 1, 1)
                write_record(stream, x, 2, 7)
            with self.assertRaisesRegex(ValueError, "non-finite operand"):
                _paired_records(path)

    def test_source_driver_requires_one_bounds_contract_across_events(self):
        first, second = record("u"), record("u")
        second.time_step = 21
        second.bounds["its"] = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pr101_upper_wind.raw"
            with path.open("wb") as stream:
                write_record(stream, first, 1, 1)
                write_record(stream, first, 2, 7)
                write_record(stream, second, 1, 1)
                write_record(stream, second, 2, 7)
            with self.assertRaisesRegex(ValueError, "different domain or tile bounds"):
                _paired_records(path)

    def test_factor_separation_reports_field_coefficient_and_interaction(self):
        hydro, projected = record("u"), record("u")
        for k in (37,38,39):
            for key in hydro.values:
                projected.values[key] = np.float32(2 * hydro.values[key])
                projected.xkmhd[key] = np.float32(2 * hydro.xkmhd[key])
        with tempfile.TemporaryDirectory() as directory:
            hpath, ppath = Path(directory)/"h.raw", Path(directory)/"p.raw"
            for path, rec in ((hpath,hydro),(ppath,projected)):
                with path.open("wb") as stream:
                    write_record(stream, rec, 1, 0)
                    write_record(stream, rec, 2, 0)
            result = factor_separation(ppath,hpath)
        row = result["faces"][0]["levels"][0]
        self.assertAlmostEqual(row["field_effect_at_H_coeff"], 6)
        self.assertAlmostEqual(row["coefficient_effect_at_H_field"], 6)
        self.assertAlmostEqual(row["field_coefficient_interaction"], 6)
        self.assertAlmostEqual(row["total_P_minus_H"], 18)


if __name__ == "__main__":
    unittest.main()
