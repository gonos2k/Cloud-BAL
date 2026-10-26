from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import check_test_tiers


def run_wrapper(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "tests/run_python_test.py"), str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_silent_module_with_no_collected_tests_is_rejected(tmp_path: Path) -> None:
    module = tmp_path / "test_silent.py"
    module.write_text("if __name__ == '__main__':\n    pass\n", encoding="utf-8")
    result = run_wrapper(module)
    assert result.returncode != 0
    assert "No pytest cases executed" in result.stderr


def test_all_skipped_pytest_cases_are_reported_as_skip(tmp_path: Path) -> None:
    module = tmp_path / "test_skipped.py"
    module.write_text(
        "import pytest\n@pytest.mark.skip(reason='external evidence')\n"
        "def test_external_evidence(): pass\n",
        encoding="utf-8",
    )
    result = run_wrapper(module)
    assert result.returncode == 0
    assert "TIER_RESULT: SKIP" in result.stdout
    assert "all 1 pytest cases skipped" in result.stdout


def test_failing_pytest_case_propagates_failure(tmp_path: Path) -> None:
    module = tmp_path / "test_failure.py"
    module.write_text("def test_failure():\n    assert False\n", encoding="utf-8")
    result = run_wrapper(module)
    assert result.returncode != 0
    assert "FAIL" in result.stdout


def test_newly_discovered_test_defaults_to_portable(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "test_added.py").write_text("", encoding="utf-8")
    (tmp_path / "test_tier_exceptions.json").write_text("{}", encoding="utf-8")
    (tmp_path / "python_script_test_allowlist.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(check_test_tiers, "TESTS", tmp_path)
    assert check_test_tiers.registry() == {"test_added.py": ("portable", "")}


@pytest.mark.parametrize(
    "exceptions, expected",
    [
        ('{"linux":[{"test_missing.py":"requires Linux"}]}', "name missing tests"),
        (
            '{"linux":[{"test_added.py":"requires Linux"}],'
            '"native":[{"test_added.py":"requires native build"}]}',
            "multiple tiers",
        ),
    ],
)
def test_registry_rejects_invalid_exceptions(
    tmp_path: Path, monkeypatch, exceptions: str, expected: str
) -> None:
    (tmp_path / "test_added.py").write_text("", encoding="utf-8")
    (tmp_path / "test_tier_exceptions.json").write_text(exceptions, encoding="utf-8")
    (tmp_path / "python_script_test_allowlist.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(check_test_tiers, "TESTS", tmp_path)
    with pytest.raises(ValueError, match=expected):
        check_test_tiers.registry()
