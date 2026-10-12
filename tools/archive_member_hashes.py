"""Ordered object identities for GNU ar archives, including duplicate members."""
from __future__ import annotations

import hashlib
from pathlib import Path


def archive_member_hashes(path: Path) -> list[tuple[str, str]]:
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise ValueError(f"not a regular ar archive: {path}")
    offset = 8
    names = b""
    members = []
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[58:60] != b"`\n":
            raise ValueError(f"invalid ar member header: {path}")
        size = int(header[48:58])
        start = offset + 60
        end = start + size
        if size < 0 or end > len(data):
            raise ValueError(f"truncated ar member: {path}")
        name = header[:16].decode("ascii").rstrip()
        body = data[start:end]
        offset = end + size % 2
        if offset > len(data):
            raise ValueError(f"missing ar member padding: {path}")
        if name == "//":
            names = body
            continue
        if name in {"/", "/SYM64/"}:
            continue
        if name.startswith("/"):
            index = int(name[1:])
            terminator = names.find(b"/\n", index)
            if index < 0 or terminator < index:
                raise ValueError(f"invalid GNU ar long name: {path}")
            name = names[index:terminator].decode("utf-8")
        else:
            name = name.removesuffix("/")
        if not name or "/" in name:
            raise ValueError(f"unsupported ar member name: {name!r}")
        members.append((name, hashlib.sha256(body).hexdigest()))
    return members
