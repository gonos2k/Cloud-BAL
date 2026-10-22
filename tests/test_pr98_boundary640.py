from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/pr98_boundary640.py"
SPEC = importlib.util.spec_from_file_location("pr98_boundary640", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_frozen_640_commands_bind_all_three_arms() -> None:
    for arm in MODULE.ARMS:
        command = MODULE.command_for(arm, Path(f"/lustre/{arm}"), execute=True)
        assert str(MODULE.FROZEN_RUNNER) in command
        assert "--duration-seconds" in command
        assert command[command.index("--duration-seconds") + 1] == "640"
        assert "--candidate-build" in command
        assert "--execute" in command
        assert ("--hydro-input-receipt" in command) == (arm == "HYDRO")


def test_snapshot_boundary_is_step_32_on_frozen_20_second_timestep() -> None:
    assert MODULE.DURATION_SECONDS // 20 == 32
    assert MODULE.DURATION_SECONDS == 640
    assert MODULE.EXPECTED_EXE_SHA256 == (
        "a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d"
    )
    assert MODULE.RUNNER_POST_KDM6_SNAPSHOT_SECONDS == (20, 60, 300, 320, 480, 500, 600, 640)
