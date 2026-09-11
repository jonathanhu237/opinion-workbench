#!/usr/bin/env python3
"""Create a UTF-8 ZIP preserving Unix executable bits and internal symlinks."""

import argparse
import os
import stat
import zipfile
from pathlib import Path


def package(root: Path, output: Path) -> None:
    root = root.resolve()
    if (root / "data").exists():
        raise ValueError("cannot package a used portable directory")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for directory, dirs, files in os.walk(root, followlinks=False):
            for name in sorted(dirs + files):
                path = Path(directory) / name
                member = path.relative_to(root.parent).as_posix()
                if path.is_symlink():
                    target = os.readlink(path)
                    if Path(target).is_absolute() or not path.resolve().is_relative_to(
                        root
                    ):
                        raise ValueError("external package symlink")
                    info = zipfile.ZipInfo(member)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, target.encode("utf-8"))
                else:
                    archive.write(path, member)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    package(args.root, args.output)
