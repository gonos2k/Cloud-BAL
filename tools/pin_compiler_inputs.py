#!/usr/bin/env python3
"""Pin external files observed by a bounded strace compiler-process trace.

The parser is deliberately narrower than a filesystem snapshot.  It records
successful execve/execveat paths and successful readable regular open/openat/
openat2 paths.  Explicit generated roots are retained in the receipt and are
excluded from the external byte manifest.  No other path is silently omitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Iterable

from pin_link_inputs import digest as stable_digest


SCHEMA = "cloud-bal-compiler-inputs-v1"
RECOMMENDED_TRACE_ARGS = [
    "strace",
    "-ff",
    "-yy",
    "-s4096",
    "-e",
    "trace=execve,execveat,open,openat,openat2",
]
SYSCALLS = {"execve", "execveat", "open", "openat", "openat2"}
SYSCALL_RE = re.compile(r"^(execveat|execve|openat2|openat|open)\(")
RESUMED_RE = re.compile(r"^<\.\.\.\s+(\w+)\s+resumed>(.*)$")
RETURN_RE = re.compile(r"\)\s+=\s+(-?\d+)(.*)$")
FD_ANNOTATION_RE = re.compile(r"^<(.+)>(?:\s+\(deleted\))?$")
QUOTED_RE = re.compile(r'"((?:\\.|[^"\\])*)"')


class TraceError(ValueError):
    """A trace cannot support a safe external-input manifest."""


def _decode_strace_string(value: str) -> str:
    """Decode the common C escapes emitted by strace without shell parsing."""

    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            result.append(char)
            index += 1
            continue
        index += 1
        if index == len(value):
            raise TraceError("unterminated escaped trace string")
        escaped = value[index]
        simple = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\", '"': '"'}
        if escaped in simple:
            result.append(simple[escaped])
            index += 1
        elif escaped == "x" and index + 2 < len(value):
            result.append(chr(int(value[index + 1 : index + 3], 16)))
            index += 3
        elif escaped in "01234567":
            end = index
            while end < min(index + 3, len(value)) and value[end] in "01234567":
                end += 1
            result.append(chr(int(value[index:end], 8)))
            index = end
        else:
            result.append(escaped)
            index += 1
    return "".join(result)


def _line_prefix(line: str) -> tuple[str, str]:
    """Return a stable pid key and the syscall text for common strace prefixes."""

    match = re.match(r"^\[pid\s+(\d+)\]\s+(.*)$", line)
    if match:
        return match.group(1), match.group(2)
    # `-f` without `-ff` may prefix a numeric PID.  Per-PID files normally do
    # not have it; recognize only a plain integer to avoid treating timestamps
    # as PIDs.
    match = re.match(r"^(\d+)\s+(?:execve|execveat|open|openat|openat2|<)", line)
    if match:
        return match.group(1), line[match.end(1) + 1 :]
    return "trace", line


def _has_truncation_marker(call: str) -> bool:
    """Detect path/argument truncation markers, excluding unfinished markers."""

    if re.search(r'"(?:\\.|[^"\\])*\.\.\."', call):
        return True
    if re.search(r"\[\.\.\.\]", call):
        return True
    if re.search(r"<[^>]*\.\.\.>", call):
        return True
    return False


def _quoted_strings(call: str) -> list[str]:
    return [_decode_strace_string(match.group(1)) for match in QUOTED_RE.finditer(call)]


def _syscall_name(call: str) -> str | None:
    match = SYSCALL_RE.match(call)
    return match.group(1) if match else None


def _return(call: str) -> tuple[int, str] | None:
    match = RETURN_RE.search(call)
    if not match:
        return None
    return int(match.group(1)), match.group(2)


def _path_from_exec(call: str, syscall: str) -> str | None:
    strings = _quoted_strings(call)
    if not strings:
        return None
    if syscall == "execveat" and not strings[0]:
        # With AT_EMPTY_PATH the executable is the already-open fd, whose
        # `-yy` annotation is attached to the dirfd argument.  argv[0] is a
        # different quoted string and must never be treated as the file.
        match = re.search(r"execveat\([^,]*<(.+)>,\s*$", call.split('""', 1)[0])
        if match:
            return match.group(1).partition("<")[0]
        return None
    return strings[0]


def _path_from_open_annotation(call: str) -> tuple[int, str] | None:
    returned = _return(call)
    if returned is None or returned[0] < 0:
        return None
    suffix = returned[1].strip()
    match = FD_ANNOTATION_RE.match(suffix)
    if not match:
        raise TraceError("successful open lacks resolved fd annotation")
    annotation = match.group(1)
    path, separator, _descriptor_detail = annotation.partition("<")
    if suffix.endswith(" (deleted)"):
        path += " (deleted)"
    return returned[0], path


def _open_is_readable(call: str) -> bool:
    """Apply the access mode before considering the resolved fd annotation."""

    # openat2 carries flags in `{flags=...}`; ordinary open calls carry a
    # symbolic or numeric second/third argument.  O_PATH and O_WRONLY are not
    # readable inputs.  Numeric zero is O_RDONLY.
    if "O_PATH" in call:
        return False
    if "O_WRONLY" in call and "O_RDWR" not in call:
        return False
    # Numeric access modes are uncommon in strace output but are valid.  For
    # openat2 they occur in `{flags=...}`; for open/openat they are the first
    # numeric argument after the pathname.  Do not mistake an O_CREAT mode
    # such as 0600 for the access flags.
    flags = re.search(r"\bflags\s*=\s*(0[xX][0-9a-fA-F]+|[0-9]+)", call)
    if flags is None and not re.search(r"\bO_[A-Z0-9_]+", call):
        pathname = re.search(r'"(?:\\.|[^"\\])*"', call)
        remainder = call[pathname.end() :] if pathname else ""
        flags = re.search(r",\s*(0[xX][0-9a-fA-F]+|[0-9]+)(?=\s*(?:,|\)|\}))", remainder)
    if flags:
        text = flags.group(1)
        value = int(text, 16 if text.lower().startswith("0x") else 8 if len(text) > 1 and text.startswith("0") else 10)
        if value & os.O_ACCMODE == os.O_WRONLY:
            return False
    return True


def _is_virtual_path(raw: str, canonical: Path | None = None) -> bool:
    candidates = [raw]
    if canonical is not None:
        candidates.append(str(canonical))
    return any(
        candidate == "/proc"
        or candidate.startswith("/proc/")
        or candidate == "/sys"
        or candidate.startswith("/sys/")
        for candidate in candidates
    )


def _inside(path: Path, roots: Iterable[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _normalise_root(path: Path) -> Path:
    if not path.exists() or not path.is_dir():
        raise TraceError(f"generated root is not an existing directory: {path}")
    return path.resolve()


def _normalise_trace_files(trace_dir: Path) -> list[Path]:
    if not trace_dir.exists() or not trace_dir.is_dir():
        raise TraceError(f"trace directory is not an existing directory: {trace_dir}")
    files = sorted(path for path in trace_dir.rglob("*") if path.is_file())
    if not files:
        raise TraceError(f"trace directory has no regular trace files: {trace_dir}")
    return files


def _record(
    *,
    kind: str,
    syscall: str,
    raw_path: str | None,
    trace_file: Path,
    line_number: int,
    result: str,
    roots: list[Path],
) -> dict[str, object]:
    record: dict[str, object] = {
        "kind": kind,
        "syscall": syscall,
        "raw_path": raw_path,
        "trace_file": str(trace_file),
        "line": line_number,
        "result": result,
    }
    if raw_path is None:
        record["classification"] = "unresolved"
        return record
    deleted = raw_path.endswith(" (deleted)")
    path_text = raw_path[: -len(" (deleted)")] if deleted else raw_path
    record["deleted_annotation"] = deleted
    # `-yy` also annotates descriptors that do not name filesystem paths.
    # They are observable kernel objects, outside the regular-file pin set.
    if path_text.startswith(("socket:[", "pipe:[", "anon_inode:", "memfd:", "netlink:")):
        record["classification"] = "kernel_virtual"
        return record
    if not path_text.startswith("/"):
        record["classification"] = "unresolved"
        return record
    try:
        canonical = Path(path_text).resolve(strict=False)
    except OSError:
        record["classification"] = "unresolved"
        return record
    record["canonical_path"] = str(canonical)
    if _is_virtual_path(path_text, canonical):
        record["classification"] = "kernel_virtual"
        return record
    if _inside(canonical, roots):
        record["classification"] = "generated"
        return record
    if not canonical.exists():
        record["classification"] = "successful_nonexistent" if result == "success" else "failed_nonexistent"
        return record
    try:
        mode = canonical.stat().st_mode
    except OSError:
        record["classification"] = "unresolved"
        return record
    if not stat.S_ISREG(mode):
        record["classification"] = "nonregular"
        return record
    record["classification"] = "external_regular"
    return record


def parse_trace_files(trace_files: Iterable[Path], generated_roots: Iterable[Path]) -> dict[str, object]:
    """Parse trace files and return observations plus externally pinned paths."""

    roots = [_normalise_root(path) for path in generated_roots]
    observations: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    truncated: list[dict[str, object]] = []
    unfinished: dict[tuple[Path, str], tuple[str, int]] = {}
    files = [Path(path) for path in trace_files]
    trace_hashes: dict[str, str] = {}

    for trace_file in files:
        data = trace_file.read_bytes()
        if not data.endswith(b"\n"):
            raise TraceError(f"trace file is not newline-terminated: {trace_file}")
        trace_hashes[str(trace_file)] = hashlib.sha256(data).hexdigest()
        try:
            lines = data.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise TraceError(f"trace file is not UTF-8: {trace_file}") from exc
        for line_number, original_line in enumerate(lines, 1):
            pid, line = _line_prefix(original_line)
            resumed = RESUMED_RE.match(line)
            key = (trace_file, pid)
            if resumed:
                pending = unfinished.pop(key, None)
                if pending is None:
                    raise TraceError(f"resumed syscall without prefix at {trace_file}:{line_number}")
                line = pending[0] + resumed.group(2)
                line_number = pending[1]
            elif "<unfinished ...>" in line:
                prefix = line.split("<unfinished ...>", 1)[0]
                syscall = _syscall_name(prefix)
                if syscall in SYSCALLS:
                    unfinished[key] = (prefix, line_number)
                continue
            syscall = _syscall_name(line)
            if syscall is None:
                continue
            returned = _return(line)
            if returned is None:
                continue
            success = returned[0] >= 0
            if success and _has_truncation_marker(line):
                entry = {"trace_file": str(trace_file), "line": line_number, "syscall": syscall, "text": line}
                truncated.append(entry)
                raise TraceError(f"truncated successful {syscall} at {trace_file}:{line_number}")
            if syscall in {"execve", "execveat"}:
                raw_path = _path_from_exec(line, syscall)
                record = _record(
                    kind="exec",
                    syscall=syscall,
                    raw_path=raw_path,
                    trace_file=trace_file,
                    line_number=line_number,
                    result="success" if success else "failed",
                    roots=roots,
                )
                if success and record.get("classification") == "unresolved":
                    unresolved.append(record)
                    raise TraceError(f"unresolved successful {syscall} at {trace_file}:{line_number}")
                if success or record.get("classification") not in {"unresolved", None}:
                    observations.append(record)
                if not success:
                    failures.append(record)
                continue
            if not success:
                strings = _quoted_strings(line)
                record = _record(
                    kind="open",
                    syscall=syscall,
                    raw_path=strings[0] if strings else None,
                    trace_file=trace_file,
                    line_number=line_number,
                    result="failed",
                    roots=roots,
                )
                failures.append(record)
                continue
            annotated = _path_from_open_annotation(line)
            assert annotated is not None
            _, annotation_path = annotated
            if annotation_path.endswith("..."):
                entry = {"trace_file": str(trace_file), "line": line_number, "syscall": syscall, "text": line}
                truncated.append(entry)
                raise TraceError(f"truncated successful {syscall} annotation at {trace_file}:{line_number}")
            record = _record(
                kind="open",
                syscall=syscall,
                raw_path=annotation_path,
                trace_file=trace_file,
                line_number=line_number,
                result="success",
                roots=roots,
            )
            if record.get("classification") == "unresolved":
                unresolved.append(record)
                raise TraceError(f"unresolved successful {syscall} at {trace_file}:{line_number}")
            if not _open_is_readable(line):
                record["selected"] = False
            observations.append(record)

    if unfinished:
        entries = [
            {"trace_file": str(path), "pid": pid, "line": line, "reason": "unfinished syscall"}
            for (path, pid), (_, line) in sorted(unfinished.items(), key=lambda item: (str(item[0][0]), item[0][1]))
        ]
        raise TraceError(f"unfinished trace syscall(s): {entries}")

    external = sorted(
        {
            str(record["canonical_path"])
            for record in observations
            if record.get("classification") == "external_regular"
            and record.get("result") == "success"
            and record.get("selected", True)
        }
    )
    generated = [record for record in observations if record.get("classification") == "generated"]
    return {
        "trace_files": [str(path) for path in files],
        "trace_sha256": trace_hashes,
        "observations": observations,
        "external_paths": external,
        "generated_observations": generated,
        "failed_or_nonexistent": failures
        + [record for record in observations if record.get("classification") == "successful_nonexistent"],
        "unresolved": unresolved,
        "truncated": truncated,
        "generated_observation_count": len(generated),
        "external_path_count": len(external),
    }


def manifest_contents(paths: Iterable[Path]) -> str:
    lines = []
    for path in sorted({Path(path).resolve(strict=True) for path in paths}):
        lines.append(f"{stable_digest(path)}  {path}\n")
    return "".join(lines)


def _manifest_paths(contents: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in contents.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (/.+)", line)
        if not match:
            raise TraceError("invalid compiler input manifest line")
        parsed[match.group(2)] = match.group(1)
    return parsed


def _receipt_path(manifest: Path, explicit: Path | None) -> Path:
    return explicit or manifest.with_name(manifest.name + ".receipt.json")


def _write_exclusive(path: Path, data: bytes) -> None:
    """Create an evidence file without replacing an existing sealed file."""

    with path.open("xb") as stream:
        stream.write(data)


def _receipt(
    *,
    trace_dir: Path,
    trace: dict[str, object],
    roots: list[Path],
    manifest: Path,
    manifest_text: str,
    tracer: Path | None,
) -> dict[str, object]:
    observations = trace["observations"]
    return {
        "schema": SCHEMA,
        "trace_dir": str(trace_dir.resolve()),
        "trace_files": trace["trace_files"],
        "trace_sha256": trace["trace_sha256"],
        "recommended_trace_args": RECOMMENDED_TRACE_ARGS,
        "tracer": {
            "path": str(tracer.resolve()) if tracer else None,
            "sha256": stable_digest(tracer.resolve()) if tracer and tracer.is_file() else None,
        },
        "generated_roots": [str(root) for root in roots],
        "generated_observation_count": trace["generated_observation_count"],
        "external_path_count": trace["external_path_count"],
        "observed_exec_count": sum(record["kind"] == "exec" for record in observations),
        "observed_readable_open_count": sum(
            record["kind"] == "open" and record.get("selected", True)
            for record in observations
        ),
        "observations": observations,
        "failed_or_nonexistent": trace["failed_or_nonexistent"],
        "unresolved": trace["unresolved"],
        "truncated": trace["truncated"],
        "manifest": str(manifest.resolve()),
        "manifest_sha256": hashlib.sha256(manifest_text.encode()).hexdigest(),
        "scope": "successful execve/execveat and successful readable regular open/openat/openat2; exact generated roots excluded and recorded; virtual/nonregular observations classified",
    }


def pin_compiler_inputs(
    trace_dir: Path,
    generated_roots: Iterable[Path],
    manifest: Path,
    receipt: Path | None = None,
    tracer: Path | None = None,
    verify: bool = False,
) -> dict[str, object]:
    roots = [_normalise_root(path) for path in generated_roots]
    trace_files = _normalise_trace_files(trace_dir)
    if tracer is not None:
        tracer = tracer.resolve(strict=True)
        if not tracer.is_file():
            raise TraceError(f"tracer is not a regular file: {tracer}")
    trace = parse_trace_files(trace_files, roots)
    paths = [Path(path) for path in trace["external_paths"]]
    contents = manifest_contents(paths)
    receipt_path = _receipt_path(manifest, receipt)
    expected_receipt = _receipt(
        trace_dir=trace_dir,
        trace=trace,
        roots=roots,
        manifest=manifest,
        manifest_text=contents,
        tracer=tracer,
    )
    if verify:
        if not manifest.is_file():
            raise TraceError(f"manifest missing for verification: {manifest}")
        if manifest.read_bytes() != contents.encode():
            raise TraceError("compiler input path set or bytes changed")
        # A fresh final build has different PIDs, trace files, generated
        # roots, and often a different set of helper-process observations.
        # Its receipt is therefore new evidence; only the selected canonical
        # external path/byte manifest is compared with discovery.
        if receipt_path.exists():
            raise FileExistsError(receipt_path)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        _write_exclusive(
            receipt_path,
            (json.dumps(expected_receipt, indent=2, sort_keys=True) + "\n").encode(),
        )
    else:
        if manifest.exists():
            raise FileExistsError(manifest)
        if receipt_path.exists():
            raise FileExistsError(receipt_path)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        _write_exclusive(manifest, contents.encode())
        _write_exclusive(
            receipt_path,
            (json.dumps(expected_receipt, indent=2, sort_keys=True) + "\n").encode(),
        )
    return expected_receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-dir", required=True, type=Path)
    parser.add_argument("--build-root", required=True, action="append", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--tracer", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        receipt = pin_compiler_inputs(
            args.trace_dir,
            args.build_root,
            args.manifest,
            args.receipt,
            args.tracer,
            args.verify,
        )
    except (TraceError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "status": "PASS",
                "manifest": receipt["manifest"],
                "manifest_sha256": receipt["manifest_sha256"],
                "external_path_count": receipt["external_path_count"],
                "generated_observation_count": receipt["generated_observation_count"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
