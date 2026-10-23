from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("guarded_replay", ROOT / "tools/pr101_guarded_replay.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@pytest.fixture
def tmp_path():
    # /tmp is noexec on the research host; diagnostic scratch is /var/tmp.
    with tempfile.TemporaryDirectory(prefix="pr101_guard_test_", dir="/var/tmp") as directory:
        yield Path(directory)


def recipe(tmp_path, code=None):
    source = tmp_path / "source.dat"
    source.write_bytes(b"answer")
    executable = Path(sys.executable).resolve()
    payload = {
        "schema": "pr101_guarded_replay_v1", "case": "fixture", "scope": "Python guard test only",
        "directory": str(tmp_path / "fresh"),
        "executable": {"path": str(executable), "sha256": guard.sha256(executable)},
        "inputs": {"pre.raw": {"path": str(source), "sha256": guard.sha256(source)}},
        "arguments": ["-c", code or
            "from pathlib import Path; Path('post.raw').write_bytes(Path('pre.raw').read_bytes()); print(Path.cwd()); print('DONE')"],
        "expected_outputs": {"post.raw": guard.sha256(source)}, "completion_markers": ["DONE"],
    }
    manifest = tmp_path / "recipe.json"
    manifest.write_text(json.dumps(payload))
    return manifest, payload


def test_fresh_cwd_bound_inputs_outputs_and_receipt(tmp_path):
    manifest, data = recipe(tmp_path)
    result = guard.run(manifest)
    assert result["status"] == "COMPLETE"
    directory = Path(data["directory"])
    assert str(directory) in (directory / "run.log").read_text()
    assert json.loads((directory / "receipt.json").read_text()) == result
    assert result["environment"]["OMP_NUM_THREADS"] == "1"
    with pytest.raises(ValueError, match="new absolute scratch"):
        guard.run(manifest)


@pytest.mark.parametrize("bad", ["executable", "input", "checkout", "external_argument"])
def test_bad_recipe_is_rejected_before_directory_creation(tmp_path, bad):
    manifest, data = recipe(tmp_path)
    if bad == "executable":
        data["executable"]["sha256"] = "0" * 64
    elif bad == "input":
        data["inputs"]["pre.raw"]["sha256"] = "0" * 64
    elif bad == "checkout":
        (tmp_path / ".git").write_text("gitdir: fixture")
    else:
        data["arguments"] = ["/outside.raw"]
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        guard.run(manifest)
    assert not Path(data["directory"]).exists()


def test_staged_input_mutation_is_not_accepted(tmp_path):
    manifest, data = recipe(tmp_path,
        "from pathlib import Path; Path('post.raw').write_bytes(Path('pre.raw').read_bytes()); "
        "Path('pre.raw').write_bytes(b'changed'); print('DONE')")
    result = guard.run(manifest)
    assert result["status"] == "INCOMPLETE"
    assert result["preservation_issues"] == ["staged file changed during replay: pre.raw"]
    assert (tmp_path / "source.dat").read_bytes() == b"answer"


def test_missing_marker_preserves_closed_failure_receipt(tmp_path):
    manifest, data = recipe(tmp_path,
        "from pathlib import Path; Path('post.raw').write_bytes(b'answer')")
    result = guard.run(manifest)
    assert result["returncode"] == 0 and result["status"] == "INCOMPLETE"
    assert result["completion_markers"] == {"DONE": False}
    assert (Path(data["directory"]) / "receipt.json").is_file()
