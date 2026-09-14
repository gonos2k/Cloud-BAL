#!/usr/bin/env python3
"""Focused checks for the strict, direct-exec ncgen bridge."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
ICX = Path(
    "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/icx"
)
TOOLS = PROJECT / "tools"
NCGEN = (
    PROJECT.parent
    / "klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/bin/ncgen"
).resolve()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ldd_manifest(binary: Path, path: Path) -> None:
    result = subprocess.run(
        ["ldd", "-r", str(binary)],
        capture_output=True,
        text=True,
        check=True,
    )
    files: dict[Path, str] = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split()
        if not fields:
            continue
        candidate = fields[2] if len(fields) >= 3 and fields[1] == "=>" else fields[0]
        if candidate.startswith("/"):
            source = Path(candidate)  # Keep the requested SONAME basename in the snapshot.
            if source.is_file():
                files[source] = digest(source)
    assert files
    path.write_text(
        "".join(f"{sha}  {source}\n" for source, sha in sorted(files.items())),
        encoding="ascii",
    )


HARNESS = r'''
#include <errno.h>
#include <stdio.h>

int cloud_bal_ncgen_system(const char *command);

int main(int argc, char **argv)
{
    int result;

    if (argc != 2) {
        return 2;
    }
    errno = 0;
    result = cloud_bal_ncgen_system(argv[1]);
    printf("rc=%d errno=%d\n", result, errno);
    return 0;
}
'''


def compile_harness(directory: Path) -> Path:
    assert digest(ICX) == "9fe05a4aef59abce8d8f0631964dd0f12932345d0d38fc9e9d6f6af844e94b33"
    harness = directory / "harness.c"
    executable = directory / "bridge_harness"
    harness.write_text(HARNESS, encoding="ascii")
    subprocess.run(
        [
            str(ICX),
            "-std=gnu89",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(TOOLS / "cloud_bal_ncgen_system.c"),
            str(harness),
            "-o",
            str(executable),
        ],
        check=True,
        cwd=directory,
    )
    return executable


def test_bridge_fallback_and_strict_bound_direct_exec() -> None:
    with tempfile.TemporaryDirectory(prefix="ncgen-bridge-", dir=PROJECT / "scratch") as temporary:
        root = Path(temporary).resolve()
        harness = compile_harness(root)
        cdl = root / "input.cdl"
        cdl.write_text("netcdf fixture {}\n", encoding="ascii")
        output = root / "generated.nc"

        fallback = subprocess.run(
            [str(harness), "true"],
            capture_output=True,
            text=True,
            check=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        assert "rc=0" in fallback.stdout

        invalid_mode = subprocess.run(
            [str(harness), "true"],
            capture_output=True,
            text=True,
            check=True,
            env={"CLOUD_BAL_NCGEN_MODE": "unexpected", "PATH": "/usr/bin:/bin"},
        )
        assert "rc=-1 errno=22" in invalid_mode.stdout

        manifest = root / "runtime.sha256"
        ldd_manifest(Path("/bin/true"), manifest)
        sys.path.insert(0, str(TOOLS))
        from run_bound_executable import bind_executable  # noqa: PLC0415
        from run_detached_runtime import stage_runtime  # noqa: PLC0415

        snapshot = stage_runtime(manifest, root)
        ncgen_fd = bind_executable(Path("/bin/true").resolve(), digest(Path("/bin/true").resolve()))
        loader_fd = bind_executable(snapshot.loader.snapshot, snapshot.loader.sha256)
        try:
            environment = {
                "CLOUD_BAL_NCGEN_MODE": "bound",
                "CLOUD_BAL_NCGEN_FD": str(ncgen_fd),
                "CLOUD_BAL_NCGEN_LOADER_FD": str(loader_fd),
                "CLOUD_BAL_NCGEN_RUNTIME": str(snapshot.root),
                "PATH": "/usr/bin:/bin",
            }
            direct = subprocess.run(
                [str(harness), f"ncgen -o {output} {cdl}"],
                capture_output=True,
                text=True,
                check=True,
                env=environment,
                pass_fds=(ncgen_fd, loader_fd),
            )
            assert "rc=0" in direct.stdout, (direct.stdout, direct.stderr)
            assert not output.exists()

            unsealed_fd_environment = dict(environment)
            unsealed_fd_environment["CLOUD_BAL_NCGEN_FD"] = "1"
            unsealed = subprocess.run(
                [str(harness), f"ncgen -o {output} {cdl}"],
                capture_output=True,
                text=True,
                check=True,
                env=unsealed_fd_environment,
                pass_fds=(loader_fd,),
            )
            assert "rc=-1 errno=22" in unsealed.stdout
            assert not output.exists()

            marker = root / "shell-marker"
            injected = subprocess.run(
                [str(harness), f"ncgen -o {output} {cdl}; touch {marker}"],
                capture_output=True,
                text=True,
                check=True,
                env=environment,
                pass_fds=(ncgen_fd, loader_fd),
            )
            assert "rc=-1 errno=22" in injected.stdout
            assert not marker.exists()
        finally:
            os.close(ncgen_fd)
            os.close(loader_fd)


def test_bound_bridge_matches_direct_ncgen_bytes() -> None:
    with tempfile.TemporaryDirectory(prefix="ncgen-bridge-real-", dir=PROJECT / "scratch") as temporary:
        root = Path(temporary).resolve()
        harness = compile_harness(root)
        cdl = root / "input.cdl"
        cdl.write_text(
            "netcdf fixture {\n"
            " dimensions:\n"
            "   x = 2 ;\n"
            " variables:\n"
            "   int value(x) ;\n"
            " data:\n"
            "   value = 3, 7 ;\n"
            "}\n",
            encoding="ascii",
        )
        direct_output = root / "direct.nc"
        bound_output = root / "bound.nc"
        subprocess.run(
            [str(NCGEN), "-o", str(direct_output), str(cdl)],
            check=True,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )

        sys.path.insert(0, str(TOOLS))
        from run_bound_executable import bind_executable  # noqa: PLC0415
        from run_detached_runtime import stage_runtime, inspect_bound_loader, exec_detached_runtime
        from cloud_bal_stage_coordinator import _supervise_launch  # noqa: PLC0415

        manifest = root / "runtime.sha256"
        ldd_manifest(NCGEN, manifest)
        snapshot = stage_runtime(manifest, root)
        ncgen_fd = bind_executable(NCGEN, digest(NCGEN))
        loader_fd = bind_executable(snapshot.loader.snapshot, snapshot.loader.sha256)
        try:
            environment = {
                "CLOUD_BAL_NCGEN_MODE": "bound",
                "CLOUD_BAL_NCGEN_FD": str(ncgen_fd),
                "CLOUD_BAL_NCGEN_LOADER_FD": str(loader_fd),
                "CLOUD_BAL_NCGEN_RUNTIME": str(snapshot.root),
                "PATH": "/usr/bin:/bin",
                "LC_ALL": "C",
            }
            # Both closures must resolve entirely inside their detached snapshots.
            inspect_bound_loader(snapshot, ncgen_fd, loader_fd)
            main_manifest = root / "main.runtime.sha256"
            ldd_manifest(harness, main_manifest)
            main_snapshot = stage_runtime(main_manifest, root)
            main_fd = bind_executable(harness, digest(harness))
            main_loader_fd = bind_executable(main_snapshot.loader.snapshot, main_snapshot.loader.sha256)
            inspect_bound_loader(main_snapshot, main_fd, main_loader_fd)
            outputs = root / "outputs"
            outputs.mkdir()
            bound_output = outputs / "bound.nc"
            def execute():
                fd = os.open(root / "confined.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.dup2(fd, 1); os.dup2(fd, 2); os.close(fd)
                os.environ.clear(); os.environ.update(environment)
                exec_detached_runtime(main_snapshot, main_fd, main_loader_fd, str(harness),
                    (f"ncgen -o {bound_output} {cdl}",),
                    read_paths=[cdl, main_snapshot.root, snapshot.root], write_dirs=[outputs],
                    retain_fds=(ncgen_fd, loader_fd))
            try:
                lifetime = _supervise_launch(root, execute, 30)
                assert lifetime['exit_code'] == 0 and lifetime['closure']['status'] == 'ECHILD', lifetime
                log = (root / "confined.log").read_text()
                assert 'DETACHED_RUNTIME_LANDLOCK_PASS' in log and 'rc=0 errno=' in log, log
            finally:
                os.close(main_fd); os.close(main_loader_fd)
        finally:
            os.close(ncgen_fd)
            os.close(loader_fd)
        assert direct_output.read_bytes() == bound_output.read_bytes()


def main() -> None:
    test_bridge_fallback_and_strict_bound_direct_exec()
    test_bound_bridge_matches_direct_ncgen_bytes()
    print("ncgen bridge tests passed")


if __name__ == "__main__":
    main()
