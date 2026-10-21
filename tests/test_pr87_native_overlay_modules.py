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


def _link_receipt(tmp_path: Path) -> dict:
    return {
        "candidate_executable_path": "/parent/wrf.exe",
        "candidate_archive_path": "/parent/libwrf.a",
        "observer_object_path": "/parent/pr85_joint_stage_observer.o",
        "link_argv": ["ifx", "-o", "/parent/wrf.exe", "/parent/wrf.o",
                      "/parent/libwrf.a", "/parent/pr85_joint_stage_observer.o",
                      "/parent/solve_em.o"],
    }


def test_link_replaces_exact_parent_observer_and_keeps_extra_adjacent(tmp_path: Path) -> None:
    receipt = _link_receipt(tmp_path)
    executable = tmp_path / "overlay.exe"
    archive = tmp_path / "overlay.a"
    staged_wrf = tmp_path / "wrf.o"
    observer_object = tmp_path / "observer_override.o"
    extra_object = tmp_path / "extra.o"
    observer_object.write_bytes(b"replacement observer")
    staged_link_inputs = {"/parent/wrf.o": {"path": str(staged_wrf)}}

    argv = overlay.build_link_argv(
        receipt, executable, archive, staged_link_inputs,
        {"object_path": str(extra_object)},
        {"object_path": str(observer_object), "object_sha256": overlay.sha256(observer_object)},
    )

    assert argv == ["ifx", "-o", str(executable), str(staged_wrf), str(archive),
                    str(observer_object), str(extra_object), "/parent/solve_em.o"]
    assert receipt["link_argv"][5] == receipt["observer_object_path"]


def test_link_without_override_keeps_parent_observer_and_existing_extra_order(tmp_path: Path) -> None:
    receipt = _link_receipt(tmp_path)

    argv = overlay.build_link_argv(
        receipt, tmp_path / "overlay.exe", tmp_path / "overlay.a", {},
        {"object_path": "/extra/pr90_cycle_support.o"},
    )

    observer_index = argv.index(receipt["observer_object_path"])
    assert argv[observer_index + 1] == "/extra/pr90_cycle_support.o"
    assert receipt["observer_object_path"] in argv


def test_link_rejects_missing_parent_observer_link_input(tmp_path: Path) -> None:
    receipt = _link_receipt(tmp_path)
    receipt["link_argv"].remove(receipt["observer_object_path"])
    observer_object = tmp_path / "observer_override.o"
    observer_object.write_bytes(b"replacement observer")

    with pytest.raises(ValueError, match="parent observer object exactly once"):
        overlay.build_link_argv(
            receipt, tmp_path / "overlay.exe", tmp_path / "overlay.a", {}, None,
            {"object_path": str(observer_object), "object_sha256": overlay.sha256(observer_object)},
        )


def test_link_rejects_missing_or_mismatched_observer_override_object(tmp_path: Path) -> None:
    receipt = _link_receipt(tmp_path)
    missing = tmp_path / "missing_observer.o"
    with pytest.raises(ValueError, match="observer override object is missing"):
        overlay.build_link_argv(
            receipt, tmp_path / "overlay.exe", tmp_path / "overlay.a", {}, None,
            {"object_path": str(missing), "object_sha256": "0" * 64},
        )

    observer_object = tmp_path / "observer_override.o"
    observer_object.write_bytes(b"actual object")
    with pytest.raises(ValueError, match="observer override object hash mismatch"):
        overlay.build_link_argv(
            receipt, tmp_path / "overlay.exe", tmp_path / "overlay.a", {}, None,
            {"object_path": str(observer_object), "object_sha256": "0" * 64},
        )


def test_extra_source_object_and_log_defaults_remain_stable(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "observer.f90"
    source.write_text("subroutine observer()\nend\n")
    scratch = tmp_path / "scratch"
    compile_dir = scratch / "compile"
    (scratch / "logs").mkdir(parents=True)
    compile_dir.mkdir()

    def fake_run_pinned(argv, cwd, log, profile=overlay.PROFILE):
        output = Path(argv[argv.index("-o") + 1])
        output.write_bytes(b"compiled")
        log.write_text("compiled\n")

    monkeypatch.setattr(overlay, "run_pinned", fake_run_pinned)
    parent = {"observer_source_path": "/parent/observer.f90",
              "observer_compile_argv": ["ifx", "-O0", "-c", "-free",
                                        "/parent/observer.f90", "-o", "/parent/observer.o"]}

    result = overlay.compile_extra_source(source, parent, scratch, compile_dir, False)
    override = overlay.compile_extra_source(
        source, parent, scratch, compile_dir, False,
        object_name="pr87_stage_observer_override.o",
        log_name="stage_observer_override.compile.log",
        source_subdir="stage_observer_override",
    )

    assert Path(result["source_path"]) == scratch / "source" / "observer.f90"
    assert Path(result["object_path"]).name == "pr87_extra_observer.o"
    assert Path(result["compile_log"]).name == "extra_observer.compile.log"
    assert Path(override["source_path"]) == scratch / "source/stage_observer_override/observer.f90"
    assert Path(override["object_path"]).name == "pr87_stage_observer_override.o"
    assert Path(override["compile_log"]).name == "stage_observer_override.compile.log"
