"""Preserve exact Qt/Chromium notices from the pinned official source archive.

This offline maintainer action preserves original bytes. It deliberately avoids
moving Qt documentation branches describing a different patch level.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
from uuid import uuid4

VERSION = "6.11.2"
ARCHIVE_NAME = f"qt-everywhere-src-{VERSION}.tar.xz"
ARCHIVE_SHA256 = "6dcfbca271d76a6502741a2c0dc6fc98ef7dd0b7b4cfd0abcebb285a86a26f33"
SOURCE = f"https://download.qt.io/official_releases/qt/6.11/{VERSION}/single/{ARCHIVE_NAME}"
MODULES = {"qtbase", "qtdeclarative", "qtimageformats", "qtpositioning", "qtserialport", "qtsvg", "qtwebchannel", "qtwebengine", "qttranslations"}
NOTICE_NAME = re.compile(r"^(?:LICENSE|LICENCE|COPYING|COPYRIGHT|NOTICE|AUTHORS)(?:[._-].*|S)?$", re.I)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", required=True)
    parser.add_argument("--source-archive", type=Path, required=True, help=f"Unmodified official {ARCHIVE_NAME}")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "licenses" / "QtWebEngine-attributions")
    args = parser.parse_args()
    source_archive = args.source_archive.resolve(strict=True)
    if file_hash(source_archive) != ARCHIVE_SHA256:
        raise ValueError("Qt source archive does not match the pinned official SHA-256")
    destination = args.output.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Output must be empty; preserve the previous snapshot before refreshing")
    destination.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".qt-notices-{uuid4().hex}"
    staging.mkdir()
    prefix = f"qt-everywhere-src-{VERSION}"
    records = []
    # Stream inspection reads archive members without extracting arbitrary paths.
    with tarfile.open(source_archive, mode="r|xz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            relative = PurePosixPath(member.name)
            if len(relative.parts) < 3 or relative.parts[0] != prefix or relative.parts[1] not in MODULES:
                continue
            basename = relative.name
            if not NOTICE_NAME.fullmatch(basename) and basename != "README.chromium":
                continue
            if member.size > 8 * 1024 * 1024:
                raise ValueError(f"Unexpectedly large licence member: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Cannot read licence member: {member.name}")
            content = stream.read()
            filename = hashlib.sha256(member.name.encode("utf8")).hexdigest()[:20] + ".txt"
            (staging / filename).write_bytes(content)
            records.append({"file": filename, "upstream_file": member.name, "url": SOURCE, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
    records.sort(key=lambda record: record["upstream_file"].casefold())
    if len(records) < 100 or not any("/qtwebengine/src/3rdparty/chromium/" in r["upstream_file"] for r in records):
        raise ValueError("Missing exact Qt/Chromium source notices")
    manifest = {
        "module": f"Qt WebEngine {VERSION}", "distribution": f"PySide6-Addons {VERSION}", "source": SOURCE,
        "source_archive": {"file": ARCHIVE_NAME, "sha256": ARCHIVE_SHA256, "bytes": source_archive.stat().st_size},
        "retrieved_utc": datetime.now(timezone.utc).isoformat(), "notice_format": "unmodified-source-license-files",
        "notes": "Original LICENSE/LICENCE/COPYING/COPYRIGHT/NOTICE/AUTHORS and README.chromium files from the exact official Qt source archive, including Qt/Chromium third parties. Individual upstream licences apply. The complete corresponding-source release archive is supplied separately. These are source notices, not a moving documentation snapshot.",
        "files": records,
    }
    (staging / "snapshot-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    rows = "".join(f'<li><a href="{r["file"]}">{escape(r["upstream_file"])}</a></li>' for r in records)
    (staging / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Qt and Chromium notices</title>'
        f'<h1>Qt {VERSION} / Qt WebEngine {VERSION} / Chromium notices</h1>'
        '<p>Original upstream licence and attribution files, preserved without changes from the exact official source archive. '
        'Original paths, SHA-256 values and archive provenance are recorded in snapshot-manifest.json. '
        'The complete corresponding-source archive is provided with the release.</p>'
        f'<p><a href="{escape(SOURCE)}">Official source archive</a></p><ul>{rows}</ul></html>', encoding="utf8")
    for path in staging.iterdir():
        # Both resolved directories are confined to the explicitly selected output parent.
        if not path.resolve().is_relative_to(staging.resolve()) or not destination.is_relative_to(destination.parent):
            raise ValueError("Invalid notice output path")
        shutil.move(str(path), str(destination / path.name))
    staging.rmdir()
    print(f"Preserved {len(records)} exact Qt/Chromium source notices for {VERSION}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
