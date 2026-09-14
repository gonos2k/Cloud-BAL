#!/usr/bin/env python3
"""Exercise dependency inspection from a private, potentially noexec directory."""

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main() -> None:
    tool = Path(__file__).resolve().parents[1] / "tools/inspect_bound_runtime.py"
    with tempfile.TemporaryDirectory(prefix="bound-runtime-") as temporary:
        root = Path(temporary)
        executable = root / "python"
        shutil.copy2(Path(sys.executable).resolve(), executable)
        manifest = root / "driver.sha256"
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        manifest.write_text(f"{digest}  {executable}\n")
        command = [sys.executable, str(tool), str(executable), "--sha256-file", str(manifest)]
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert "libc.so" in result.stdout
        executable.write_bytes(executable.read_bytes() + b"changed")
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 2
        assert "SHA-256 mismatch" in result.stderr
        assert "libc.so" not in result.stdout
    print("Bound runtime inspection tests passed")


if __name__ == "__main__":
    main()
