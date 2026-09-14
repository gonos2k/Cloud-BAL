#!/usr/bin/env python3
"""Pin linker-map LOAD bytes between discovery and final links.

This covers selected link inputs, including implicit static runtime/startup
objects. It does not certify compiler execution or unlisted header dependencies.
"""
import argparse
import hashlib
import os
from pathlib import Path
import stat


def link_paths(link_map):
    paths = set()
    for line in link_map.read_text().splitlines():
        if not line.startswith('LOAD '):
            continue
        name = line[5:]
        if not name.startswith('/') or any(c in name for c in '\r\n\\'):
            raise ValueError('link map must name absolute, unescaped LOAD paths')
        paths.add(Path(name).resolve(strict=True))
    if not paths:
        raise ValueError('link map has no LOAD inputs')
    return sorted(paths)


def digest(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('link input must be a regular file')
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(stream.fileno())
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if identity(before) != identity(after) or identity(after) != identity(path.stat()):
        raise ValueError('link input changed during hashing')
    return value


def pin_inputs(link_map, manifest, verify=False):
    contents = ''.join(f'{digest(p)}  {p}\n' for p in link_paths(link_map))
    if verify:
        if manifest.read_text() != contents:
            raise ValueError('final link input set or bytes changed')
    else:
        with manifest.open('x') as output:
            output.write(contents)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('link_map', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    pin_inputs(args.link_map, args.manifest, args.verify)


if __name__ == '__main__':
    main()
