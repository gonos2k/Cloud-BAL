"""Reproducibility and fail-closed checks for the archived figure renderer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "docs/evidence/first_hour_factorial_20261030/analysis"
SCRIPT = ROOT / "tools/plot_first_hour_factorial.py"
FIGURES = (
    "hour_12_13_paired_precipitation",
    "hour_12_13_skill_factorial",
    "factorial_design_and_metric",
)
ASSETS = tuple(f"{name}.{suffix}" for name in FIGURES for suffix in ("png", "pdf", "svg"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FirstHourFactorialFigureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="first-hour-figures-test-")
        self.root = Path(self.temp.name)
        self.analysis = self.root / "analysis"
        shutil.copytree(ANALYSIS, self.analysis)
        receipt_path = self.analysis / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        for index, record in enumerate(receipt["sources"]):
            record["path"] = f"/unavailable/archived-source-{index}"
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        self.output = self.root / "rendered"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_cli_renders_without_original_host_sources(self) -> None:
        receipt = json.loads((self.analysis / "receipt.json").read_text())
        self.assertTrue(all(not Path(row["path"]).exists() for row in receipt["sources"]))
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--analysis-dir", str(self.analysis),
             "--output-dir", str(self.output)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.output / "figure_manifest.json").read_text())
        self.assertEqual(manifest["status"], "COMPLETE")
        self.assertEqual(manifest["renderer"]["sha256"], digest(SCRIPT))
        self.assertIn("does not reopen original host source files", manifest["provenance_note"])
        for filename, expected in manifest["figure_sha256"].items():
            self.assertEqual(digest(self.output / filename), expected)

    def test_changed_score_csv_is_rejected_and_existing_output_is_preserved(self) -> None:
        output_csv = self.analysis / "continuous_scores.csv"
        output_csv.write_bytes(output_csv.read_bytes() + b"\n")
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("existing figures remain intact", encoding="utf-8")
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import plot_first_hour_factorial
            with self.assertRaisesRegex(ValueError, "analysis output hash mismatch"):
                plot_first_hour_factorial.run(self.analysis, self.output)
        finally:
            sys.path.remove(str(ROOT / "tools"))
            sys.modules.pop("plot_first_hour_factorial", None)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "existing figures remain intact")
        self.assertEqual(sorted(path.name for path in self.output.iterdir()), ["keep.txt"])

    def test_all_nine_assets_reproduce_byte_for_byte(self) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import plot_first_hour_factorial
            plot_first_hour_factorial.run(self.analysis, self.root / "first")
            plot_first_hour_factorial.run(self.analysis, self.root / "second")
        finally:
            sys.path.remove(str(ROOT / "tools"))
            sys.modules.pop("plot_first_hour_factorial", None)
        for filename in ASSETS:
            first = self.root / "first" / filename
            second = self.root / "second" / filename
            self.assertEqual(first.read_bytes(), second.read_bytes(), filename)


if __name__ == "__main__":
    unittest.main()
