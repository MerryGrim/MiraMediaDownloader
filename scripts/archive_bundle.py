# SPDX-License-Identifier: GPL-2.0-or-later
"""Create the complete portable ZIP, including Windows extended paths."""
import os
from pathlib import Path
import sys
import zipfile

def native_path(value):
    absolute = os.path.abspath(os.fspath(value))
    if os.name != "nt" or absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)

bundle = Path(os.path.abspath(sys.argv[1]))
archive = Path(os.path.abspath(sys.argv[2]))
if archive.parent != bundle.parent or archive.suffix.lower() != ".zip":
    raise RuntimeError("ZIP must be an exact sibling target of the application bundle.")
source = native_path(bundle)
target = native_path(archive)
if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
    raise RuntimeError("Refusing a linked ZIP target.")
files = []
for path in source.rglob("*"):
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise RuntimeError("Linked bundle entries cannot be archived.")
    if path.is_file():
        relative = path.relative_to(source).as_posix()
        files.append((relative, path))
files.sort(key=lambda item: (item[0].casefold(), item[0]))
with zipfile.ZipFile(target, mode="w", compression=zipfile.ZIP_DEFLATED,
                     compresslevel=9, strict_timestamps=False) as output:
    for relative, path in files:
        output.write(path, arcname="MiraMediaDownloader/" + relative)
print("ZIP payload files:", len(files))
