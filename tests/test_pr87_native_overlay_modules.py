from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pr87_build_native_overlay as overlay  # noqa: E402


def make_parent(tmp_path: Path) -> tuple[Path, Path]:
    parent = tmp_path / "parent"
    compile_dir = tmp_path / "fresh_compile"
    (parent / "compile").mkdir(parents=True)
    (parent / "kdm6_compile").mkdir()
    compile_dir.mkdir()
    return parent, compile_dir


def test_stage_modules_omits_only_obsolete_helper_genmod(tmp_path: Path) -> None:
    parent, compile_dir = make_parent(tmp_path)
    (parent / "compile" / overlay.REPLACED_EXTERNAL_INTERFACE).write_bytes(b"stale signature")
    (parent / "compile" / "module_physics.mod").write_bytes(b"physics module")
    (parent / "kdm6_compile" / "module_kdm6_support.mod").write_bytes(b"kdm6 support")

    staged = overlay.stage_modules(parent, compile_dir)

    names = {Path(row["path"]).name for row in staged}
    assert names == {"module_physics.mod", "module_kdm6_support.mod"}
    assert not (compile_dir / overlay.REPLACED_EXTERNAL_INTERFACE).exists()
    assert (compile_dir / "module_physics.mod").read_bytes() == b"physics module"


def test_stage_modules_still_rejects_conflicting_duplicate_modules(tmp_path: Path) -> None:
    parent, compile_dir = make_parent(tmp_path)
    (parent / "compile" / "module_shared.mod").write_bytes(b"compile signature")
    (parent / "kdm6_compile" / "module_shared.mod").write_bytes(b"different signature")

    with pytest.raises(ValueError, match="conflicting parent module files: module_shared.mod"):
        overlay.stage_modules(parent, compile_dir)


def test_final_modules_hashes_regenerated_interfaces_and_keeps_parent_identity(tmp_path: Path) -> None:
    parent, compile_dir = make_parent(tmp_path)
    initial = parent / 'compile/cloud_bal_joint_transport.mod'
    initial.write_bytes(b'parent interface')
    staged = overlay.stage_modules(parent, compile_dir)
    (compile_dir / initial.name).write_bytes(b'new per-pair interface')
    (compile_dir / 'generated_interface.mod').write_bytes(b'new helper')
    final = {Path(row['path']).name: row for row in overlay.final_modules(compile_dir, staged)}
    row = final[initial.name]
    assert row['sha256'] == overlay.sha256(compile_dir / initial.name)
    assert row['sha256'] != row['staged_sha256'] == row['parent_sha256']
    assert row['regenerated'] is True
    assert final['generated_interface.mod']['generated_in_build'] is True
    assert initial.read_bytes() == b'parent interface'


REPRO_FLAGS = ["-stand", "f08", "-warn", "all", "-fpe0", "-traceback", "-O2",
               "-fp-model", "strict", "-fimf-arch-consistency=true", "-no-ftz"]


def test_reproduction_compile_argv_replaces_only_known_free_audit_prefix() -> None:
    original = ["ifx", "-module", "mod", "-Iinc", *overlay.FREE_COMPILE_PREFIX,
                "-c", "-free", "-DCASE=1", "-Ihost", "input.f90", "-o", "out.o"]

    result = overlay.reproduction_compile_argv(original, REPRO_FLAGS)

    assert result == ["ifx", "-module", "mod", "-Iinc", *REPRO_FLAGS,
                      "-c", "-free", "-DCASE=1", "-Ihost", "input.f90", "-o", "out.o"]
    assert original[4:4 + len(overlay.FREE_COMPILE_PREFIX)] == list(overlay.FREE_COMPILE_PREFIX)


def test_reproduction_compile_argv_removes_inserted_audit_checks_only() -> None:
    original = ["ifx", "-module", "mod", "-Iinc", *overlay.CHECKED_COMPILE_PREFIXES[1],
                "-free", "-qopenmp", "-DWRF_CHEM=0", "input.f90", "-o", "out.o"]

    result = overlay.reproduction_compile_argv(original, REPRO_FLAGS)

    assert result == ["ifx", "-module", "mod", "-Iinc", *REPRO_FLAGS,
                      "-free", "-qopenmp", "-DWRF_CHEM=0", "input.f90", "-o", "out.o"]


@pytest.mark.parametrize("argv", [
    ["ifx", "-O0", "-fp-model", "strict", "input.f90"],
    ["ifx", *overlay.FREE_COMPILE_PREFIX, "-c", *overlay.FREE_COMPILE_PREFIX, "input.f90"],
])
def test_reproduction_compile_argv_rejects_missing_or_ambiguous_audit_prefix(argv: list[str]) -> None:
    with pytest.raises(ValueError, match="exactly one known Intel audit profile prefix"):
        overlay.reproduction_compile_argv(argv, REPRO_FLAGS)


def test_reproduction_flags_are_read_from_sourced_profile(tmp_path: Path) -> None:
    profile = tmp_path / "profile.sh"
    profile.write_text("CLOUD_BAL_REPRO_FLAGS=(-stand f08 -O2 -fp-model strict)\n")

    assert overlay.load_reproduction_flags(profile) == ["-stand", "f08", "-O2", "-fp-model", "strict"]
