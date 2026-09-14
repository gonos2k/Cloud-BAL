#!/usr/bin/env python3
"""Exercise the bounded compiler-process trace parser and pin contract."""

from pathlib import Path
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pin_compiler_inputs import (  # noqa: E402
    TraceError,
    _is_virtual_path,
    parse_trace_files,
    pin_compiler_inputs,
)


class CompilerInputTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.external = self.root / "external input.txt"
        self.external.write_bytes(b"stable compiler input\n")
        self.other = self.root / "additional input.h"
        self.other.write_bytes(b"second compiler input\n")
        self.tool = self.root / "compiler-tool"
        self.tool.write_bytes(b"executable bytes\n")
        self.generated = self.root / "generated"
        self.generated.mkdir()
        self.generated_file = self.generated / "object.o"
        self.generated_file.write_bytes(b"generated output\n")

    def write_trace(self, name, lines):
        trace_dir = self.root / name
        trace_dir.mkdir()
        (trace_dir / "events.1").write_text("\n".join(lines) + "\n")
        return trace_dir

    def open_line(self, path, flags="O_RDONLY", result=3):
        return f'openat(AT_FDCWD, "{path}", {flags}) = {result}<{path}>'

    def test_discovery_manifest_and_final_verification_allow_fresh_trace_metadata(self):
        discovery_trace = self.write_trace(
            "discovery-trace",
            [
                f'execve("{self.tool}", ["compiler-tool"], 0x0) = 0',
                self.open_line(self.external),
                self.open_line(self.generated_file),
            ],
        )
        manifest = self.root / "compiler_inputs.sha256"
        discovery_receipt = self.root / "discovery.receipt.json"
        pin_compiler_inputs(
            discovery_trace,
            [self.generated],
            manifest,
            discovery_receipt,
        )

        final_generated = self.root / "fresh-generated"
        final_generated.mkdir()
        final_file = final_generated / "object.o"
        final_file.write_bytes(b"fresh generated output\n")
        final_trace = self.write_trace(
            "final-trace",
            [
                f'execve("{self.tool}", ["compiler-tool"], 0x0) = 0',
                self.open_line(self.external),
                self.open_line(final_file),
            ],
        )
        final_receipt = self.root / "final.receipt.json"
        result = pin_compiler_inputs(
            final_trace,
            [final_generated],
            manifest,
            final_receipt,
            verify=True,
        )
        self.assertEqual(result["external_path_count"], 2)
        self.assertTrue(final_receipt.is_file())
        self.assertNotEqual(discovery_receipt.read_bytes(), final_receipt.read_bytes())
        with self.assertRaises(FileExistsError):
            pin_compiler_inputs(
                final_trace,
                [final_generated],
                manifest,
                final_receipt,
                verify=True,
            )

    def test_changed_or_added_external_dependency_rejected(self):
        discovery_trace = self.write_trace(
            "base-trace",
            [self.open_line(self.external)],
        )
        manifest = self.root / "base.sha256"
        pin_compiler_inputs(discovery_trace, [self.generated], manifest)

        self.external.write_bytes(b"changed compiler input\n")
        changed_trace = self.write_trace(
            "changed-trace",
            [self.open_line(self.external)],
        )
        with self.assertRaisesRegex(TraceError, "path set or bytes changed"):
            pin_compiler_inputs(
                changed_trace,
                [self.generated],
                manifest,
                self.root / "changed.receipt.json",
                verify=True,
            )
        self.external.write_bytes(b"stable compiler input\n")

        added_trace = self.write_trace(
            "added-trace",
            [self.open_line(self.external), self.open_line(self.other)],
        )
        with self.assertRaisesRegex(TraceError, "path set or bytes changed"):
            pin_compiler_inputs(
                added_trace,
                [self.generated],
                manifest,
                self.root / "added.receipt.json",
                verify=True,
            )

    def test_failed_and_missing_paths_are_preserved_without_being_pinned(self):
        missing = self.root / "does-not-exist"
        trace_dir = self.write_trace(
            "failure-trace",
            [
                f'openat(AT_FDCWD, "{missing}", O_RDONLY) = -1 ENOENT (No such file or directory)',
                self.open_line(missing),
            ],
        )
        parsed = parse_trace_files([trace_dir / "events.1"], [self.generated])
        self.assertEqual(parsed["external_paths"], [])
        classes = {entry["classification"] for entry in parsed["failed_or_nonexistent"]}
        self.assertIn("failed_nonexistent", classes)
        self.assertIn("successful_nonexistent", classes)

    def test_generated_and_nonregular_paths_are_classified_and_dev_shm_is_not_virtual(self):
        fifo = self.root / "input.fifo"
        os.mkfifo(fifo)
        trace_dir = self.write_trace(
            "classification-trace",
            [
                self.open_line(self.generated_file),
                self.open_line(fifo),
                self.open_line("/proc/filesystems"),
                self.open_line("/dev/null", flags="O_WRONLY|O_CREAT|O_TRUNC, 0600"),
            ],
        )
        parsed = parse_trace_files([trace_dir / "events.1"], [self.generated])
        by_path = {entry.get("canonical_path", entry["raw_path"]): entry for entry in parsed["observations"]}
        self.assertEqual(by_path[str(self.generated_file)]["classification"], "generated")
        self.assertEqual(by_path[str(fifo)]["classification"], "nonregular")
        self.assertEqual(by_path["/proc/filesystems"]["classification"], "kernel_virtual")
        self.assertEqual(by_path["/dev/null"]["classification"], "nonregular")
        self.assertFalse(_is_virtual_path("/dev/shm/compiler-input"))

    def test_successful_relative_unresolved_and_truncated_entries_fail_closed(self):
        cases = (
            [
                'execve("relative-tool", ["relative-tool"], 0x0) = 0',
            ],
            [
                'openat(AT_FDCWD, "relative-input", O_RDONLY) = 3<relative-input>',
            ],
            [
                f'execve("{self.tool}...", ["compiler-tool"], 0x0) = 0',
            ],
            [
                f'openat(AT_FDCWD, "{self.external}", O_RDONLY) = 3<{self.external}...>',
            ],
        )
        for index, lines in enumerate(cases):
            trace_dir = self.write_trace(f"invalid-{index}", lines)
            with self.assertRaises(TraceError):
                parse_trace_files([trace_dir / "events.1"], [self.generated])

    def test_unfinished_resumed_calls_are_reassembled(self):
        trace_dir = self.write_trace(
            "resumed-trace",
            [
                f'openat(AT_FDCWD, "{self.external}", O_RDONLY <unfinished ...>',
                f'<... openat resumed>) = 3<{self.external}>',
            ],
        )
        parsed = parse_trace_files([trace_dir / "events.1"], [self.generated])
        self.assertEqual(parsed["external_paths"], [str(self.external)])

    def test_execveat_uses_path_argument_or_empty_path_fd_annotation(self):
        trace_dir = self.write_trace(
            "execveat-trace",
            [
                f'execveat(AT_FDCWD, "{self.external}", ["argv0"], 0x0) = 0',
                f'execveat(3<{self.tool}>, "", ["argv0"], 0x0, AT_EMPTY_PATH) = 0',
            ],
        )
        parsed = parse_trace_files([trace_dir / "events.1"], [self.generated])
        self.assertEqual(
            parsed["external_paths"],
            sorted((str(self.external), str(self.tool))),
        )

    def test_trace_truncation_and_unfinished_tail_fail(self):
        no_newline = self.root / "no-newline"
        no_newline.mkdir()
        (no_newline / "events.1").write_bytes(self.open_line(self.external).encode())
        with self.assertRaisesRegex(TraceError, "newline-terminated"):
            parse_trace_files([no_newline / "events.1"], [self.generated])

        unfinished = self.write_trace(
            "unfinished-tail",
            [f'openat(AT_FDCWD, "{self.external}", O_RDONLY <unfinished ...>'],
        )
        with self.assertRaisesRegex(TraceError, "unfinished"):
            parse_trace_files([unfinished / "events.1"], [self.generated])


if __name__ == "__main__":
    unittest.main()
