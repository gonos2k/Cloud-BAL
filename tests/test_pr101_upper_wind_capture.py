from pathlib import Path
import hashlib
import json
import sys
import unittest
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/var/tmp/pr99-c2-source.2n00oy19/module_em.F")
sys.path.insert(0, str(ROOT / "tools"))
from pr101_upper_wind_capture import C2_MODULE_EM_SHA256, transform  # noqa: E402
from pr101_upper_wind_build_plan import BASE_RECEIPT, make_plan  # noqa: E402


def c2_build_assets_available():
    try:
        receipt = json.loads(BASE_RECEIPT.read_text())
        sources = [Path(row["requested_path"]) for member, row in receipt["source_overrides"].items()
                   if member != "module_em.o"]
        sources.append(Path(receipt["extra_observer"]["requested_source_path"]))
        return SOURCE.is_file() and all(path.is_file() for path in sources)
    except (OSError, KeyError, json.JSONDecodeError):
        return False


class UpperWindCaptureTransformTest(unittest.TestCase):

    def test_rejects_sources_without_exact_call_anchors(self):
        helper = (ROOT / "tools/pr101_upper_wind_capture.F90").read_text()
        with self.assertRaisesRegex(ValueError, "MODULE module_em"):
            transform("MODULE other\n", helper)

    def test_rejects_double_application(self):
        helper = (ROOT / "tools/pr101_upper_wind_capture.F90").read_text()
        with self.assertRaisesRegex(ValueError, "already has"):
            transform("MODULE pr101_upper_wind_capture\n", helper)



if __name__ == "__main__":
    unittest.main()
