#!/usr/bin/env python3
"""Fixture tests for the read-only Intel integration readiness audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "intel_audit", REPO_ROOT / "tools/audit_intel_integration.py"
)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IntegrationFixture:
    def __init__(self, root: Path, go: bool) -> None:
        self.root = root
        self.repo = root / "Cloud-BAL"
        self.ifx = root / "toolchain/ifx"
        self.version = "ifx (IFX) fixture-version"
        self._write(self.ifx, f"#!/bin/sh\nprintf '%s\\n' '{self.version}'\n", executable=True)
        self.ifx_hash = digest(self.ifx)
        self._write(self.repo / "tests/intel_toolchain.sh", "# fixture profile\n")
        job = root / AUDIT.JOB
        self._write(
            job,
            f"setenv KL05EXET {(root / 'ANAL/NE57/EXET').resolve()}\n"
            + "\n".join(
                str(AUDIT.STAGES[name]["job_token"])
                + "\nif ( $status != 0 ) exit 1"
                for name in AUDIT.STAGE_ORDER
            )
            + "\n",
        )
        dependency_text = []
        for name in AUDIT.DEPENDENCY_ROOTS:
            dependency = root / f"deps/{name.lower()}"
            if go:
                dependency.mkdir(parents=True, exist_ok=True)
                for alternatives in AUDIT.DEPENDENCY_ARTIFACT_GROUPS[name]:
                    artifact = dependency / alternatives[0].replace("*", "1")
                    artifact.parent.mkdir(parents=True, exist_ok=True)
                    if ".so" in artifact.name:
                        artifact.write_bytes(Path("/bin/true").read_bytes())
                    elif artifact.name == "netcdf.inc":
                        artifact.write_text("integer NF_NOERR\n", encoding="utf-8")
                    elif artifact.name == "hdf5.h":
                        artifact.write_text("#define H5_VERSION 1\n", encoding="utf-8")
                    elif artifact.name == "curl.h":
                        artifact.write_text("#define CURL_VERSION 1\n", encoding="utf-8")
                    else:
                        artifact.write_text("nonempty fixture\n", encoding="utf-8")
            dependency_text.append(f"{name}={dependency}")
        compiler = "$(CLOUD_BAL_FC)" if go else "ifort"
        self._write(
            root / AUDIT.COMMON_MAKEFILE,
            f"FC={compiler}\nCPP={compiler}\n" + "\n".join(dependency_text) + "\n",
        )
        self._write(
            root / AUDIT.TOP_MAKEFILE,
            "SRCROOT=.\n"
            "include $(SRCROOT)/src/include/makefile.inc\n"
            "cleanlib:\n\t$(MAKE) -C src/lib clean\n"
            "lib:\n\t$(MAKE) -C src/lib all\n",
        )
        self._write(
            root / AUDIT.BUILD_ROOT / "src/lib/Makefile",
            "SRCROOT=../..\n"
            "include $(SRCROOT)/src/include/makefile.inc\n"
            "all:\n\t@true\nclean:\n\t@true\n",
        )
        for stage in AUDIT.STAGE_ORDER:
            adapter = str(AUDIT.STAGES[stage]["adapter_token"])
            executable = str(AUDIT.STAGES[stage]["executable"])
            if go:
                self._write(root / AUDIT.STAGES[stage]["makefile"], (
                    "SRCROOT=../..\n"
                    "include $(SRCROOT)/src/include/makefile.inc\n"
                    f"EXE={executable}\n"
                    f"CLOUD_BAL_ADAPTER={adapter}.f90\n"
                    "all: $(EXE)\n"
                    "$(EXE): $(CLOUD_BAL_ADAPTER)\n"
                    "\t$(FC) $(CLOUD_BAL_ADAPTER) -o $(EXE)\n"
                    "clean:\n\t@true\n"
                ))
                entry = str(AUDIT.STAGES[stage]["entry_symbol"]).split("_MOD_", 1)[1]
                self._write(
                    (root / AUDIT.STAGES[stage]["makefile"]).parent
                    / f"{adapter}.f90",
                    f"module {adapter}\ncontains\nsubroutine {entry}\n"
                    f"end subroutine {entry}\nend module {adapter}\n",
                )
            else:
                self._write(root / AUDIT.STAGES[stage]["makefile"], "SRC=legacy.f\n")
            binary = root / AUDIT.STAGES[stage]["binary"]
            self._write(binary, f"ELF fixture {stage}\n", executable=True)
            if go:
                receipt = {
                    "schema": AUDIT.RECEIPT_SCHEMA,
                    "binary_sha256": digest(binary),
                    "compiler_path": str(self.ifx.resolve()),
                    "compiler_version": self.version,
                    "compiler_sha256": self.ifx_hash,
                    "link_command": [str(self.ifx.resolve()), "-o", str(binary)],
                }
                self._write(Path(str(binary) + ".ifx.json"), json.dumps(receipt))

    @staticmethod
    def _write(path: Path, content: str, executable: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(path.stat().st_mode | stat.S_IXUSR)


def command_result(argv: list[str], timeout: int = 30) -> dict[str, object]:
    del timeout
    command = Path(argv[0]).name
    if command == "ifx":
        return {"returncode": 0, "stdout": "ifx (IFX) fixture-version\n", "stderr": ""}
    if command == "file":
        return {"returncode": 0, "stdout": "ELF 64-bit LSB executable\n", "stderr": ""}
    if command.endswith("readelf") and "-dW" in argv:
        return {
            "returncode": 0,
            "stdout": " 0x1 (NEEDED) Shared library: [libc.so.6]\n",
            "stderr": "",
        }
    if command.endswith("readelf") and ".comment" in argv:
        return {
            "returncode": 0,
            "stdout": AUDIT.EXPECTED_IFX_COMMENT + "\n",
            "stderr": "",
        }
    if command.endswith("readelf"):
        return {"returncode": 0, "stdout": "Intel LLVM section\n", "stderr": ""}
    if command.endswith("nm"):
        binary = Path(argv[-1]).name
        stage = next(
            name
            for name in AUDIT.STAGE_ORDER
            if Path(str(AUDIT.STAGES[name]["binary"])).name == binary
        )
        entry_symbol = AUDIT.STAGES[stage]["entry_symbol"]
        return {
            "returncode": 0,
            "stdout": f"00000000 T {entry_symbol}\n",
            "stderr": "",
        }
    if command.endswith("strings"):
        return {
            "returncode": 0,
            "stdout": "Intel(R) Fortran Compiler for applications Version 2026.0\n",
            "stderr": "",
        }
    if command.endswith("ldd"):
        return {
            "returncode": 0,
            "stdout": "libc.so.6 => /lib64/libc.so.6 (0x0001)\n",
            "stderr": "",
        }
    raise AssertionError(f"unexpected command: {argv}")


def blocked_command_result(argv: list[str], timeout: int = 30) -> dict[str, object]:
    result = command_result(argv, timeout)
    command = Path(argv[0]).name
    if command.endswith("nm"):
        result["stdout"] = "00000000 T legacy_entry\n"
    elif command.endswith("strings"):
        result["stdout"] = (
            "Intel(R) Fortran Intel(R) 64 Compiler for applications, "
            "Version 19.1.3\n"
        )
    elif command.endswith("ldd"):
        result["stdout"] = (
            "libnetcdff.so.7 => not found\n"
            "undefined symbol: nf_open_ (fixture.exe)\n"
        )
    return result


def non_ifx_command_result(argv: list[str], timeout: int = 30) -> dict[str, object]:
    result = command_result(argv, timeout)
    command = Path(argv[0]).name
    if command.endswith("readelf") and "-dW" in argv:
        result["stdout"] = " 0x1 (NEEDED) Shared library: [libgfortran.so.5]\n"
    elif command.endswith("readelf") and ".comment" in argv:
        result["stdout"] = "GCC: GNU Fortran 14\n"
    elif command.endswith("strings"):
        result["stdout"] = "GNU Fortran 14\n"
    return result


def snapshot(root: Path) -> dict[str, tuple[str, int, int]]:
    return {
        str(path.relative_to(root)): (digest(path), path.stat().st_mode, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class IntelIntegrationAuditTest(unittest.TestCase):
    def test_go_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
            self.assertEqual("GO", report["summary"]["status"])
            self.assertEqual([], report["findings"])
            self.assertEqual(
                "IDENTIFIED_NOT_EXECUTED",
                report["copied_tree_full_link_plan"]["status"],
            )

    def test_blocked_fixture_has_actionable_machine_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=False)
            with mock.patch.object(
                AUDIT, "run_command", side_effect=blocked_command_result
            ):
                report = AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
            codes = set(report["summary"]["blocker_codes"])
            self.assertTrue(
                {
                    "MAKEFILE_FORBIDDEN_COMPILER",
                    "MAKEFILE_COMPILER_NOT_PINNED_IFX",
                    "CANONICAL_SOURCE_NOT_LINKED",
                    "DEPENDENCY_ROOT_MISSING",
                    "BINARY_LIBRARY_NOT_FOUND",
                    "BINARY_UNRESOLVED_SYMBOLS",
                    "BINARY_CANONICAL_SYMBOLS_MISSING",
                    "BINARY_LEGACY_IFORT_SIGNATURE",
                    "BINARY_IFX_PROVENANCE_MISSING",
                }.issubset(codes)
            )
            self.assertEqual("BLOCKED", report["summary"]["status"])

    def test_audit_does_not_modify_the_inspected_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            before = snapshot(fixture.root)
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
            self.assertEqual(before, snapshot(fixture.root))

    def test_external_binary_change_is_measured_not_hidden(self) -> None:
        changed: set[Path] = set()

        def mutating_inspector(argv: list[str], timeout: int = 30) -> dict[str, object]:
            if Path(argv[0]).name.endswith("ldd") and Path(argv[-1]) not in changed:
                binary = Path(argv[-1])
                binary.write_bytes(binary.read_bytes() + b"changed")
                changed.add(binary)
            return command_result(argv, timeout)

        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            with mock.patch.object(AUDIT, "run_command", side_effect=mutating_inspector):
                report = AUDIT.audit(
                    fixture.root, fixture.repo, fixture.ifx, fixture.version, fixture.ifx_hash
                )
            self.assertTrue(report["summary"]["selected_binary_changed_during_audit"])
            self.assertIn("BINARY_CHANGED_DURING_AUDIT", report["summary"]["blocker_codes"])

    def test_copied_link_plan_has_no_original_make_target_or_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            plan = AUDIT.copied_tree_link_plan(
                fixture.root, fixture.repo, fixture.ifx
            )
            commands = "\n".join(plan["shell_commands"])
            self.assertFalse(plan["mutates_original_tree"])
            for line in plan["shell_commands"]:
                if line.startswith("make "):
                    self.assertIn("$cloud_bal_link_copy", line)
            self.assertNotRegex(commands, AUDIT.FORBIDDEN_COMPILERS)
            self.assertIn("cp -a --reflink=auto", commands)
            self.assertIn("source symlink rejected", commands)
            self.assertIn("/usr/bin/make", commands)
            self.assertIn("--ro-bind / /", commands)

    def test_comments_cannot_fake_active_job_or_canonical_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            job = fixture.root / AUDIT.JOB
            job.write_text(
                "\n".join(
                    f"# {AUDIT.STAGES[name]['job_token']}" for name in AUDIT.STAGE_ORDER
                )
                + "\n",
                encoding="utf-8",
            )
            makefile = fixture.root / AUDIT.STAGES["deriv"]["makefile"]
            makefile.write_text("# cloud_bal_deriv_adapter.f90\nSRC=legacy.f\n")
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
            codes = {item["code"] for item in report["findings"]}
            self.assertIn("JOB_STAGE_INVOCATION_COUNT", codes)
            self.assertIn("CANONICAL_SOURCE_NOT_LINKED", codes)

    def test_dead_adapter_target_cannot_fake_linkage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            stage = "deriv"
            adapter = str(AUDIT.STAGES[stage]["adapter_token"])
            makefile = fixture.root / AUDIT.STAGES[stage]["makefile"]
            makefile.write_text(
                "SRCROOT=../..\n"
                "include $(SRCROOT)/src/include/makefile.inc\n"
                f"CLOUD_BAL_ADAPTER={adapter}.f90\n"
                "all:\n\t@true\n"
                "dead:\n\t$(FC) $(CLOUD_BAL_ADAPTER) -o dead\n"
                "clean:\n\t@true\n",
                encoding="utf-8",
            )
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root, fixture.repo, fixture.ifx, fixture.version, fixture.ifx_hash
                )
            self.assertIn("CANONICAL_SOURCE_NOT_LINKED", report["summary"]["blocker_codes"])

    def test_make_override_and_hidden_include_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            makefile = fixture.root / AUDIT.STAGES["deriv"]["makefile"]
            makefile.write_text(
                makefile.read_text(encoding="utf-8")
                + "include hidden.mk\noverride FC=/opt/flang\n",
                encoding="utf-8",
            )
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root, fixture.repo, fixture.ifx, fixture.version, fixture.ifx_hash
                )
            codes = report["summary"]["blocker_codes"]
            self.assertIn("MAKEFILE_UNSUPPORTED_CONTROL", codes)
            self.assertIn("MAKEFILE_FORBIDDEN_COMPILER", codes)

    def test_library_closure_forbidden_compiler_is_seen(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            self._write_fixture_file(
                fixture.root / AUDIT.BUILD_ROOT / "src/lib/hidden/Makefile",
                "SRCROOT=../../..\n"
                "include $(SRCROOT)/src/include/makefile.inc\n"
                "all:\n\tgfortran hidden.f90\n",
            )
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root, fixture.repo, fixture.ifx, fixture.version, fixture.ifx_hash
                )
            self.assertIn(
                "MAKEFILE_FORBIDDEN_COMPILER", report["summary"]["blocker_codes"]
            )

    @staticmethod
    def _write_fixture_file(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_job_commands_inside_false_branch_are_not_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            job = fixture.root / AUDIT.JOB
            body = [
                f"setenv KL05EXET {(fixture.root / 'ANAL/NE57/EXET').resolve()}",
                "if ( 0 ) then",
            ]
            for stage in AUDIT.STAGE_ORDER:
                body.extend(
                    [
                        str(AUDIT.STAGES[stage]["job_token"]),
                        "if ( $status != 0 ) exit 1",
                    ]
                )
            body.append("endif")
            job.write_text("\n".join(body) + "\n", encoding="utf-8")
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root, fixture.repo, fixture.ifx, fixture.version, fixture.ifx_hash
                )
            self.assertIn("JOB_STAGE_INVOCATION_COUNT", report["summary"]["blocker_codes"])

    def test_non_ifx_binary_evidence_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            with mock.patch.object(AUDIT, "run_command", side_effect=non_ifx_command_result):
                report = AUDIT.audit(
                    fixture.root, fixture.repo, fixture.ifx, fixture.version, fixture.ifx_hash
                )
            codes = report["summary"]["blocker_codes"]
            self.assertIn("BINARY_IFX_COMMENT_MISSING", codes)
            self.assertIn("BINARY_FORBIDDEN_FORTRAN_RUNTIME", codes)

    def test_text_file_cannot_fake_dependency_library(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            fake_library = fixture.root / "deps/netcdf/lib/libnetcdf.so1"
            fake_library.write_text("fixture\n", encoding="utf-8")
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root, fixture.repo, fixture.ifx, fixture.version, fixture.ifx_hash
                )
            self.assertIn("DEPENDENCY_ARTIFACT_MISSING", report["summary"]["blocker_codes"])

    def test_output_is_forbidden_below_original_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            repo = workspace / "Cloud-BAL"
            for name in ("ANAL", "MODL", str(AUDIT.BUILD_ROOT), "Cloud-BAL/tools"):
                (workspace / name).mkdir(parents=True)
                with self.assertRaises(ValueError):
                    AUDIT.require_safe_output(
                        workspace / name / "audit.json", workspace, repo
                    )
            allowed = repo / "scratch/audit.json"
            self.assertEqual(
                allowed, AUDIT.require_safe_output(allowed, workspace, repo)
            )

    def test_symlinked_scratch_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            scratch = fixture.repo / "scratch"
            scratch.symlink_to(fixture.root / "ANAL", target_is_directory=True)
            with self.assertRaises(ValueError):
                AUDIT.require_safe_output(
                    scratch / "audit.json", fixture.root, fixture.repo
                )
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root, fixture.repo, fixture.ifx, fixture.version, fixture.ifx_hash
                )
            self.assertIn("SCRATCH_ROOT_UNSAFE", report["summary"]["blocker_codes"])

    def test_local_or_suffix_symbol_cannot_fake_adapter_entry(self) -> None:
        def fake_symbol(argv: list[str], timeout: int = 30) -> dict[str, object]:
            result = command_result(argv, timeout)
            if Path(argv[0]).name.endswith("nm"):
                result["stdout"] = "00000000 t __cloud_bal_deriv_adapter_MOD_fake\n"
            return result

        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            with mock.patch.object(AUDIT, "run_command", side_effect=fake_symbol):
                report = AUDIT.audit(
                    fixture.root, fixture.repo, fixture.ifx, fixture.version, fixture.ifx_hash
                )
            self.assertIn(
                "BINARY_CANONICAL_SYMBOLS_MISSING",
                report["summary"]["blocker_codes"],
            )

    def test_receipt_requires_ifx_as_link_driver_and_object_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            binary = fixture.root / AUDIT.STAGES["deriv"]["binary"]
            receipt_path = Path(str(binary) + ".ifx.json")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["link_command"] = ["/usr/bin/ld", str(fixture.ifx.resolve())]
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
            self.assertIn(
                "BINARY_IFX_PROVENANCE_MISMATCH",
                report["summary"]["blocker_codes"],
            )

            receipt_path.write_text("[]\n", encoding="utf-8")
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                malformed = AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
            self.assertIn(
                "BINARY_IFX_PROVENANCE_INVALID",
                malformed["summary"]["blocker_codes"],
            )

    def test_relative_dependency_roots_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            common = fixture.root / AUDIT.COMMON_MAKEFILE
            text = common.read_text(encoding="utf-8")
            for name in AUDIT.DEPENDENCY_ROOTS:
                text = text.replace(
                    f"{name}={fixture.root}/deps/{name.lower()}",
                    f"{name}=deps/{name.lower()}",
                )
            common.write_text(text, encoding="utf-8")
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
            self.assertIn(
                "DEPENDENCY_ROOT_NOT_ABSOLUTE", report["summary"]["blocker_codes"]
            )

    def test_makefile_cannot_hide_an_unpinned_compiler_behind_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            common = fixture.root / AUDIT.COMMON_MAKEFILE
            common.write_text(
                "CLOUD_BAL_FC=/opt/other/flang\n" + common.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
            self.assertIn(
                "MAKEFILE_COMPILER_NOT_PINNED_IFX",
                report["summary"]["blocker_codes"],
            )

    def test_job_source_after_executable_binding_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            job = fixture.root / AUDIT.JOB
            lines = job.read_text(encoding="utf-8").splitlines()
            lines.insert(1, "source /tmp/unknown-environment")
            job.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                report = AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
            self.assertIn(
                "JOB_EXECUTABLE_ROOT_UNRESOLVED",
                report["summary"]["blocker_codes"],
            )

    def test_production_cli_rejects_policy_overrides(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            AUDIT.parse_args(["--ifx", "/tmp/fake-ifx"])
        self.assertEqual(2, raised.exception.code)

    def test_json_report_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IntegrationFixture(Path(temporary), go=True)
            with mock.patch.object(AUDIT, "run_command", side_effect=command_result):
                first = AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
                second = AUDIT.audit(
                    fixture.root,
                    fixture.repo,
                    fixture.ifx,
                    fixture.version,
                    fixture.ifx_hash,
                )
            encoded_first = json.dumps(first, indent=2, sort_keys=True) + "\n"
            encoded_second = json.dumps(second, indent=2, sort_keys=True) + "\n"
            self.assertEqual(encoded_first, encoded_second)


if __name__ == "__main__":
    unittest.main()
