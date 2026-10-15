"""Collect installed package notices without copying any user/session files."""
from __future__ import annotations

import importlib.metadata as metadata
import hashlib
import json
from pathlib import Path
import shutil
import sys


def main() -> int:
    project = Path(__file__).resolve().parents[1]
    output = project / "licenses"
    output.mkdir(exist_ok=True)
    packages = ["gallery-dl", "PySide6-Essentials", "PySide6-Addons", "shiboken6", "requests", "Pillow", "pycryptodomex", "certifi", "charset-normalizer", "idna", "urllib3", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile", "pywin32-ctypes"]
    manifest = []
    for name in packages:
        dist = metadata.distribution(name)
        record = {"name": dist.metadata["Name"], "version": dist.version, "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"), "project_urls": dist.metadata.get_all("Project-URL") or [], "files": []}
        target = output / (name.lower().replace("_", "-") + "-" + dist.version)
        target.mkdir(exist_ok=True)
        for entry in dist.files or []:
            path = Path(str(entry))
            # License paths come from installed package metadata, never a user directory.
            if any(word in path.name.lower() for word in ("license", "copying", "notice")) and ".dist-info" in str(path):
                source = Path(dist.locate_file(entry))
                if source.is_file():
                    metadata_index = next(index for index, part in enumerate(path.parts) if part.endswith(".dist-info"))
                    relative = Path(*path.parts[metadata_index + 1:])
                    destination = target / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    record["files"].append(str(destination.relative_to(output)).replace("\\", "/"))
        (target / "package-metadata.txt").write_text(dist.read_text("METADATA") or "", encoding="utf-8")
        manifest.append(record)
    # The Python runtime is redistributed by PyInstaller.
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, output / "Python-LICENSE.txt")
    # Preserve official module/Chromium attributions matching Qt 6.11.2 and
    # verify the saved snapshot offline before collecting a public release.
    attribution_root = output / "QtWebEngine-attributions"
    attribution_manifest = json.loads((attribution_root / "snapshot-manifest.json").read_text(encoding="utf-8"))
    if attribution_manifest.get("distribution") != "PySide6-Addons 6.11.2" or len(attribution_manifest.get("files", [])) < 100:
        raise ValueError("Missing or mismatched Qt WebEngine attribution snapshot")
    for record in attribution_manifest["files"]:
        filename = record["file"]
        if Path(filename).name != filename:
            raise ValueError("Invalid attribution filename")
        if hashlib.sha256((attribution_root / filename).read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Qt WebEngine attribution checksum mismatch")
    manifest.append({"name": "Qt-WebEngine-Chromium-attributions", "version": "6.11.2",
                     "license": "Individual upstream Qt/Chromium component licences (unmodified source notices)",
                     "project_urls": [attribution_manifest["source"]],
                     "files": [str(path.relative_to(output)).replace("\\", "/")
                               for path in sorted(attribution_root.iterdir()) if path.is_file()]})
    for directory, name, version, terms in (
        ("Native-codecs", "Python-Pillow-native-dependency-notices", "1.4.4", "Individual upstream licences; see NOTICE_INDEX.json"),
        ("Mesa-LLVM-opengl32sw", "Qt-software-OpenGL-Mesa-LLVM", "Mesa 11.2.2 / LLVM 3.6.2", "Individual Mesa and LLVM licences; see original notices"),
        ("MSVC-runtime", "Microsoft-VC-runtime-system-prerequisite", "14.44.35211 or newer", "Not redistributed in Mira; separately installed Microsoft system runtime. See original terms and provenance."),
    ):
        component_root = output / directory
        if component_root.is_dir():
            manifest.append({"name": name, "version": version, "license": terms,
                "files": [str(path.relative_to(output)).replace("\\", "/")
                          for path in sorted(component_root.rglob("*")) if path.is_file()]})
    (output / "component-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Collected notices for {len(manifest)} distributions into {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
