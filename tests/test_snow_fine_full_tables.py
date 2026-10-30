"""Positive-path coverage for all 31 cases in the fine-sensitivity tables."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCRIPT = ROOT / 'docs/evidence/snow_fine_20261030'
sys.path.insert(0, str(EVIDENCE_SCRIPT))
try:
    import build_full_score_tables as tables
finally:
    sys.path.remove(str(EVIDENCE_SCRIPT))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def record(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}


class SnowFineFullTableTests(unittest.TestCase):
    def test_complete_31_case_grid_builds_all_42_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / 'docs/evidence/snow_fine_20261030'
            analysis = evidence / 'analysis'
            analysis.mkdir(parents=True)
            prior = root / 'docs/evidence/snow_extension_20261030/analysis'
            prior.mkdir(parents=True)
            prior_receipt_path = prior / 'receipt.json'
            prior_receipt_path.write_text('{}\n', encoding='utf-8')
            plan_path = evidence / 'selection_plan.json'
            plan_path.write_text('{}\n', encoding='utf-8')
            test_builder = evidence / 'build_full_score_tables.py'
            test_builder.write_text(Path(tables.__file__).read_text(encoding='utf-8'), encoding='utf-8')

            cat_fields = ['lead_hour', 'valid_utc', 'window_start_utc', 'window_end_utc',
                          'case', 'threshold_mm', 'valid_obs', 'hit', 'miss', 'false_alarm',
                          'correct_dry', 'CSI', 'ETS', 'POD', 'FAR', 'frequency_bias']
            categorical = []
            for case in tables.EXPECTED_CASES:
                for lead in tables.EXPECTED_LEADS:
                    end_hour = 12 + lead
                    for threshold in tables.EXPECTED_THRESHOLDS:
                        hit, miss, false_alarm = 100, 10, 20
                        expected_random = (hit + miss) * (hit + false_alarm) / tables.POINTS
                        csi = hit / (hit + miss + false_alarm)
                        categorical.append({
                            'lead_hour': str(lead),
                            'valid_utc': f'2026-08-16T{end_hour:02d}:00:00Z',
                            'window_start_utc': f'2026-08-16T{end_hour - 1:02d}:00:00Z',
                            'window_end_utc': f'2026-08-16T{end_hour:02d}:00:00Z',
                            'case': case, 'threshold_mm': str(threshold),
                            'valid_obs': str(tables.POINTS), 'hit': str(hit), 'miss': str(miss),
                            'false_alarm': str(false_alarm), 'correct_dry': str(tables.POINTS - hit - miss - false_alarm),
                            'CSI': str(csi), 'ETS': str((hit - expected_random) / (hit + miss + false_alarm - expected_random)),
                            'POD': str(hit / (hit + miss)), 'FAR': str(false_alarm / (hit + false_alarm)),
                            'frequency_bias': str((hit + false_alarm) / (hit + miss)),
                        })
            cat_path = analysis / 'categorical_scores.csv'
            write_csv(cat_path, cat_fields, categorical)

            cont_fields = ['lead_hour', 'valid_utc', 'window_start_utc', 'window_end_utc',
                           'case', 'valid_obs', 'mean_forecast_mm', 'mean_reference_mm',
                           'MAE_mm', 'RMSE_mm']
            continuous = []
            for case in tables.EXPECTED_CASES:
                for lead in tables.EXPECTED_LEADS:
                    end_hour = 12 + lead
                    continuous.append({
                        'lead_hour': str(lead), 'valid_utc': f'2026-08-16T{end_hour:02d}:00:00Z',
                        'window_start_utc': f'2026-08-16T{end_hour - 1:02d}:00:00Z',
                        'window_end_utc': f'2026-08-16T{end_hour:02d}:00:00Z',
                        'case': case, 'valid_obs': str(tables.POINTS),
                        'mean_forecast_mm': '1.2', 'mean_reference_mm': '1.0',
                        'MAE_mm': '0.8', 'RMSE_mm': '1.4',
                    })
            cont_path = analysis / 'continuous_scores.csv'
            write_csv(cont_path, cont_fields, continuous)

            outputs = {}
            for name in ('categorical_scores.csv', 'continuous_scores.csv',
                         'selection_scores.csv', 'selection.json',
                         *(f'hour_{hour}_arrays.npz' for hour in range(13, 19))):
                path = analysis / name
                if not path.exists():
                    path.write_text('', encoding='utf-8')
                outputs[name] = record(path)
            receipt = {
                'status': 'COMPLETE', 'cases': list(tables.EXPECTED_CASES),
                'eligible_cases': [case for case in tables.EXPECTED_CASES if case != 'CURRENT_HYDRO'],
                'context_only_cases': ['CURRENT_HYDRO'], 'points_per_hour': tables.POINTS,
                'hours_utc': list(range(13, 19)), 'thresholds_mm': list(tables.EXPECTED_THRESHOLDS),
                'row_counts': {'categorical': len(categorical), 'continuous': len(continuous)},
                'analysis_outputs': outputs,
            }
            (analysis / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')

            with patch.object(tables, 'ROOT', root), patch.object(tables, 'EVIDENCE', evidence), \
                    patch.object(tables, 'ANALYSIS', analysis), \
                    patch.object(tables, 'ANALYSIS_RECEIPT', analysis / 'receipt.json'), \
                    patch.object(tables, 'BUILD_RECEIPT', evidence / 'full_tables_receipt.json'), \
                    patch.object(tables, 'REPORT', root / 'docs/SNOW_FINE_FULL_SCORES_20261030.md'), \
                    patch.object(tables, '__file__', test_builder), \
                    patch.object(tables, 'ANALYSIS_RECEIPT_SHA256',
                                 hashlib.sha256((analysis / 'receipt.json').read_bytes()).hexdigest()), \
                    patch.object(tables, 'CATEGORICAL_SHA256', hashlib.sha256(cat_path.read_bytes()).hexdigest()), \
                    patch.object(tables, 'CONTINUOUS_SHA256', hashlib.sha256(cont_path.read_bytes()).hexdigest()), \
                    patch.object(tables, 'PLAN_SHA256', hashlib.sha256(plan_path.read_bytes()).hexdigest()), \
                    patch.object(tables, 'PRIOR_ANALYSIS_RECEIPT_SHA256',
                                 hashlib.sha256(prior_receipt_path.read_bytes()).hexdigest()):
                checked_receipt, checked_cat, checked_cont, _, _ = tables.check_analysis()
                rendered = tables.build_markdown(checked_receipt, checked_cat, checked_cont)
                match = tables.check_markdown_tables(rendered, checked_receipt, checked_cat, checked_cont)
                tables.main()
                self.assertTrue((root / 'docs/SNOW_FINE_FULL_SCORES_20261030.md').is_file())
                self.assertTrue((evidence / 'full_tables_receipt.json').is_file())

            self.assertEqual(len(categorical), 1116)
            self.assertEqual(len(continuous), 186)
            self.assertEqual(match['table_count'], 42)
            self.assertEqual(match['matched_data_cells'], 13_578)
            for case in tables.EXPECTED_CASES:
                self.assertIn(tables.display_case(case), rendered.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
