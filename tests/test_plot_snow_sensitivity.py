"""Baseline identity checks for snow sensitivity figure selection and labels."""
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
ANALYSIS = ROOT / "docs/evidence/snow_sensitivity_20261030/analysis"
PLAN = ROOT / "docs/evidence/snow_sensitivity_20261030/selection_plan.json"
SCRIPT = ROOT / "tools/plot_snow_sensitivity.py"
FIGURES = ("snow_alpha_dose_response", "selected_case_csi_comparison",
           "selected_case_hourly_errors", "snow_sensitivity_maps_leads_1_3",
           "snow_sensitivity_maps_leads_4_6")
ASSETS = {f"{figure}.{suffix}" for figure in FIGURES for suffix in ("png", "pdf", "svg")}
sys.path.insert(0, str(ROOT / "tools"))
try:
    import plot_snow_sensitivity as plots
finally:
    sys.path.remove(str(ROOT / "tools"))


class SnowSensitivityFigureUnitTests(unittest.TestCase):
    def test_baseline_only_fallback_keeps_b1_and_korean_reference_labels(self) -> None:
        baseline_fixture = {
            "best_eligible_overall_case": "IMPROVED_BG_FIXED",
            "best_eligible_overall_alpha": 1.0,
        }

        selected = plots.selected_overall_case(baseline_fixture)
        fields = plots.map_fields({}, selected)

        self.assertEqual(selected, "IMPROVED_BG_FIXED")
        self.assertEqual(fields[:3], (
            ("reference", "RN1 분석"),
            ("ORIGINAL", "규준 실험"),
            ("IMPROVED_BG_FIXED", "기존 개선안"),
        ))
        self.assertEqual(len(fields), 3)

    def test_context_only_case_cannot_be_selected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ineligible or unknown"):
            plots.selected_overall_case({
                "best_eligible_overall_case": "CURRENT_HYDRO",
                "best_eligible_overall_alpha": 1.0,
            })

    def test_selected_sensitivity_map_names_family_and_alpha(self) -> None:
        fields = plots.map_fields({}, "IMPROVED_SNOW_050")
        self.assertEqual(len(fields), 4)
        self.assertEqual(fields[0], ("reference", "RN1 분석"))
        self.assertIn("α=0.5", fields[3][1])

    def test_b1_fallback_still_adds_explicit_unselected_exploration_map(self) -> None:
        selection = {"feasibility_failures": {
            "IMPROVED_SNOW_150": ["first_hour_RMSE_at_most_alpha1"]}}
        fields = plots.map_fields({}, "IMPROVED_BG_FIXED", "IMPROVED_SNOW_150", selection)
        self.assertEqual(len(fields), 4)
        self.assertEqual(fields[1], ("ORIGINAL", "규준 실험"))
        self.assertEqual(fields[2], ("IMPROVED_BG_FIXED", "기존 개선안"))
        self.assertIn("탐색 비교 · 미선정", fields[3][1])
        self.assertIn("+1 h RMSE 기준 미통과", fields[3][1])


class SnowSensitivityFigureReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="snow-sensitivity-figures-")
        self.root = Path(self.temp.name)
        self.analysis = self.root / "analysis"
        shutil.copytree(ANALYSIS, self.analysis)
        shutil.copy2(PLAN, self.root / "selection_plan.json")
        receipt_path = self.analysis / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        for index, record in enumerate(receipt["sources"]):
            record["path"] = f"/unavailable/snow-sensitivity-source-{index}"
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def render(self, output: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--analysis-dir", str(self.analysis),
             "--output-dir", str(output)], cwd=ROOT, text=True,
            capture_output=True, check=False,
        )

    def test_cli_replays_portably_and_renders_deterministic_assets(self) -> None:
        receipt = json.loads((self.analysis / "receipt.json").read_text(encoding="utf-8"))
        self.assertTrue(all(not Path(item["path"]).exists() for item in receipt["sources"]))
        output_a, output_b = self.root / "figures-a", self.root / "figures-b"
        output_a.mkdir()
        (output_a / "old.txt").write_text("replaced after successful render", encoding="utf-8")
        backup = output_a.with_name(output_a.name + ".previous")
        backup.mkdir()
        sentinel = backup / "keep.txt"
        sentinel.write_text("preserve unrelated backup", encoding="utf-8")

        first = self.render(output_a)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.render(output_b)
        self.assertEqual(second.returncode, 0, second.stderr)
        manifest = json.loads((output_a / "figure_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "COMPLETE")
        self.assertEqual(manifest["renderer"]["sha256"], self.digest(SCRIPT))
        self.assertIn("does not reopen original host files", manifest["provenance_note"])
        self.assertEqual(manifest["selected_best_case"], "IMPROVED_BG_FIXED")
        self.assertEqual(manifest["exploratory_comparison_case"], "IMPROVED_SNOW_150")
        self.assertIn("first_hour_RMSE_at_most_alpha1",
                      manifest["exploratory_comparison_failed_gates"])
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve unrelated backup")
        hashes = manifest["figure_sha256"]
        self.assertEqual(set(hashes), ASSETS)
        for filename, expected in hashes.items():
            self.assertEqual(self.digest(output_a / filename), expected)
            self.assertEqual(self.digest(output_b / filename), expected)

    def test_sealed_csv_mutation_is_rejected_before_existing_output_changes(self) -> None:
        csv_path = self.analysis / "categorical_scores.csv"
        csv_path.write_bytes(csv_path.read_bytes() + b"\n")
        output = self.root / "preserved"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("existing output remains", encoding="utf-8")
        result = self.render(output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("analysis output hash mismatch", result.stderr)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "existing output remains")
        self.assertEqual(list(output.iterdir()), [sentinel])


if __name__ == "__main__":
    unittest.main()
