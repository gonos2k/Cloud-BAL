from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/var/tmp/pr89_sources_20261019_c1/module_mp_kdm6.F")
import sys
sys.path.insert(0, str(ROOT / "tools"))
from pr90_rain_producer_trace import (  # noqa: E402
    SOURCE_SHA256, TRACE_BEGIN, TRACE_END, TraceTransformError, add_t7_trace,
)


def test_transform_is_pinned_targeted_and_physics_text_neutral() -> None:
    original = SOURCE.read_text(encoding="utf-8")
    assert hashlib.sha256(original.encode()).hexdigest() == SOURCE_SHA256
    transformed = add_t7_trace(original)
    assert transformed.count("PR90_T7_TRACE_INSERT_BEGIN") == 10
    assert "if (rain_warm_search_status.eq.1 .or. &" in transformed
    assert "pr87_model_timestep.eq.7 .and. lat.eq.222 .and. i.eq.193 .and. k.eq.4" in transformed
    assert transformed.count("call pr90_t7_trace('") == 10
    helper = transformed[transformed.index(TRACE_BEGIN):transformed.index(TRACE_END) + len(TRACE_END)]
    body = transformed.replace("\n" + helper + "\n", "\n")
    body = re.sub(r"      ! PR90_T7_TRACE_INSERT_BEGIN [^\n]*\n.*?"
                  r"      ! PR90_T7_TRACE_INSERT_END [^\n]*\n", "", body, flags=re.S)
    body = body.replace("            if (rain_warm_search_status.eq.1 .or. &\n"
                        "                (pr87_model_timestep.eq.7 .and. lat.eq.222 .and. i.eq.193 .and. k.eq.4)) then\n",
                        "            if (rain_warm_search_status.eq.1) then\n")
    assert body == original
    with pytest.raises(TraceTransformError, match="unexpected KDM6 source hash"):
        add_t7_trace(original, "0" * 64)


def test_hex_trace_helper_compiles_and_writes_under_pinned_intel(tmp_path: Path) -> None:
    original = SOURCE.read_text(encoding="utf-8")
    transformed = add_t7_trace(original)
    helper = transformed[transformed.index(TRACE_BEGIN):transformed.index(TRACE_END) + len(TRACE_END)]
    helper = helper.replace(TRACE_BEGIN, "").replace(TRACE_END, "")
    program = """module trace_fixture
contains
""" + helper + """
end module trace_fixture
program check_trace
  use trace_fixture
  call pr90_t7_trace('CHECK',7,222,193,4,3,1.0,270.0,0.1,1.0e6, &
       1.e-12,2.e4,1.e-8,8.e3,0.0,0.0,1.e8,0.0,0.005,-1)
end program check_trace
"""
    source = tmp_path / "trace_fixture.F90"
    source.write_text(program, encoding="utf-8")
    outputs = []
    with tempfile.TemporaryDirectory(prefix="pr90_t7_trace_", dir="/var/tmp") as scratch:
        root = Path(scratch)
        for opt in ("O0", "O2"):
            build = root / opt
            build.mkdir()
            executable = build / "trace_fixture"
            cmd = ["bash", "-c",
                'source "$1/tests/intel_toolchain.sh" && '
                'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                '"$CLOUD_BAL_FC" "${flags[@]}" "$3" -o "$4" && "$4"',
                "bash", str(ROOT), opt, str(source), str(executable)]
            run = subprocess.run(cmd, cwd=build, text=True, capture_output=True)
            assert run.returncode == 0, run.stdout + run.stderr
            rows = (build / "pr90_t7_producer_trace.raw").read_text().split()
            assert rows[:7] == ["PR90_T7_PRODUCER", "CHECK", "7", "222", "193", "4", "3"]
            assert len(rows) == 21
            outputs.append(rows)
    assert outputs[0] == outputs[1]
