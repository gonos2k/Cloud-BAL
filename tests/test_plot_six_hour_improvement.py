"""Portable, fail-closed and deterministic checks for six-hour figures."""
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
ANALYSIS = ROOT / "docs/evidence/six_hour_improvement_20261030/analysis"
SCRIPT = ROOT / "tools/plot_six_hour_improvement.py"
FIGURES = ("precipitation_maps_leads_1_3", "precipitation_maps_leads_4_6",
           "six_hour_skill_summary")
ASSETS = tuple(f"{name}.{suffix}" for name in FIGURES for suffix in ("png", "pdf", "svg"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SixHourFigureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="six-hour-figures-test-")
        self.root = Path(self.temp.name)
        self.analysis = self.root / "analysis"
        shutil.copytree(ANALYSIS, self.analysis)
        receipt_path = self.analysis / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        for index, record in enumerate(receipt["sources"]):
            record["path"] = f"/unavailable/archived-six-hour-source-{index}"
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        self.output = self.root / "rendered"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_cli_renders_with_unavailable_archived_sources(self) -> None:
        receipt = json.loads((self.analysis / "receipt.json").read_text())
        self.assertTrue(all(not Path(record["path"]).exists() for record in receipt["sources"]))
        self.output.mkdir()
        (self.output / "old-figure.txt").write_text("replace on successful publish", encoding="utf-8")
        preexisting_backup = self.output.with_name(self.output.name + ".previous")
        preexisting_backup.mkdir()
        backup_sentinel = preexisting_backup / "keep.txt"
        backup_sentinel.write_text("unowned sibling must remain untouched", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--analysis-dir", str(self.analysis),
             "--output-dir", str(self.output)], cwd=ROOT, text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.output / "figure_manifest.json").read_text())
        self.assertEqual(manifest["status"], "COMPLETE")
        self.assertEqual(manifest["renderer"]["sha256"], digest(SCRIPT))
        self.assertIn("does not reopen original host source files", manifest["provenance_note"])
        self.assertEqual(backup_sentinel.read_text(encoding="utf-8"),
                         "unowned sibling must remain untouched")
        self.assertEqual(set(manifest["figure_sha256"]), set(ASSETS))
        for filename, expected in manifest["figure_sha256"].items():
            self.assertEqual(digest(self.output / filename), expected)

    def test_changed_csv_is_rejected_before_existing_output_is_touched(self) -> None:
        csv_path = self.analysis / "categorical_scores.csv"
        csv_path.write_bytes(csv_path.read_bytes() + b"\n")
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("existing figures remain intact", encoding="utf-8")
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import plot_six_hour_improvement
            with self.assertRaisesRegex(ValueError, "analysis output hash mismatch"):
                plot_six_hour_improvement.run(self.analysis, self.output)
        finally:
            sys.path.remove(str(ROOT / "tools"))
            sys.modules.pop("plot_six_hour_improvement", None)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "existing figures remain intact")
        self.assertEqual(sorted(path.name for path in self.output.iterdir()), ["keep.txt"])

    def test_all_nine_assets_reproduce_byte_for_byte(self) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import plot_six_hour_improvement
            plot_six_hour_improvement.run(self.analysis, self.root / "first")
            plot_six_hour_improvement.run(self.analysis, self.root / "second")
        finally:
            sys.path.remove(str(ROOT / "tools"))
            sys.modules.pop("plot_six_hour_improvement", None)
        for filename in ASSETS:
            self.assertEqual((self.root / "first" / filename).read_bytes(),
                             (self.root / "second" / filename).read_bytes(), filename)


if __name__ == "__main__":
    unittest.main()
