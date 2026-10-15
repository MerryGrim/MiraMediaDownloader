"""Build-time inventory of the selected GPLv2-capable Qt runtime modules."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

QT_FAMILIES = {
    "Core": "qtbase", "Gui": "qtbase", "Network": "qtbase", "OpenGL": "qtbase",
    "PrintSupport": "qtbase", "Widgets": "qtbase", "Positioning": "qtpositioning",
    "Qml": "qtdeclarative", "QmlMeta": "qtdeclarative", "QmlModels": "qtdeclarative",
    "QmlWorkerScript": "qtdeclarative", "Quick": "qtdeclarative", "QuickWidgets": "qtdeclarative",
    "SerialPort": "qtserialport", "Svg": "qtsvg", "WebChannel": "qtwebchannel",
    "WebEngineCore": "qtwebengine", "WebEngineWidgets": "qtwebengine", "Pdf": "qtwebengine",
}
PLUGIN_FAMILIES = {
    "generic/qtuiotouchplugin.dll": "qtbase",
    "iconengines/qsvgicon.dll": "qtsvg",
    "imageformats/qgif.dll": "qtbase", "imageformats/qico.dll": "qtbase", "imageformats/qjpeg.dll": "qtbase",
    "imageformats/qicns.dll": "qtimageformats", "imageformats/qsvg.dll": "qtsvg",
    "imageformats/qpdf.dll": "qtwebengine",
    "imageformats/qtga.dll": "qtimageformats", "imageformats/qtiff.dll": "qtimageformats",
    "imageformats/qwbmp.dll": "qtimageformats", "imageformats/qwebp.dll": "qtimageformats",
    "networkinformation/qnetworklistmanager.dll": "qtbase",
    "platforms/qdirect2d.dll": "qtbase", "platforms/qminimal.dll": "qtbase",
    "platforms/qoffscreen.dll": "qtbase", "platforms/qwindows.dll": "qtbase",
    "position/qtposition_nmea.dll": "qtpositioning", "position/qtposition_positionpoll.dll": "qtpositioning",
    "position/qtposition_winrt.dll": "qtpositioning", "styles/qmodernwindowsstyle.dll": "qtbase",
    "tls/qcertonlybackend.dll": "qtbase", "tls/qopensslbackend.dll": "qtbase", "tls/qschannelbackend.dll": "qtbase",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve(strict=True)
    qt = bundle / "runtime" / "_internal" / "PySide6"
    if not qt.is_dir():
        raise SystemExit("Missing collected Qt directory")
    records, errors = [], []
    compiler_runtime = re.compile(r'^(?:vcruntime\d.*|msvcp\d.*|vccorlib\d.*|concrt\d.*|vcamp\d.*|vcomp\d.*|mfc\d.*|ucrtbase)\.dll$', re.I)
    for path in bundle.rglob('*.dll'):
        if compiler_runtime.fullmatch(path.name):
            errors.append('App-local proprietary compiler runtime present: ' + path.relative_to(bundle).as_posix())
    for path in sorted(qt.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".dll":
            continue
        relative = path.relative_to(qt).as_posix()
        family = None
        if path.name.startswith("Qt6"):
            family = QT_FAMILIES.get(path.stem[3:])
            if family is None:
                errors.append(f"Unreviewed Qt module: {relative}")
        elif relative.startswith("plugins/"):
            family = PLUGIN_FAMILIES.get(relative[len("plugins/"):])
            if family is None:
                errors.append(f"Unreviewed Qt plugin: {relative}")
        if "virtualkeyboard" in relative.lower():
            errors.append(f"Unnecessary GPLv3-only Virtual Keyboard present: {relative}")
        records.append({"file": relative, "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "source_family": family,
                        "qt_portion_license_choice": "GPL-2.0-only" if family else "separate-runtime-notice"})
    if not any(r["file"] == "Qt6WebEngineCore.dll" for r in records):
        errors.append("WebEngine runtime absent")
    report = {"qt_version": "6.11.2", "purpose": "Build-time release inventory; this is not a runtime integrity restriction.",
              "notes": "Qt-authored runtime portions select their GPLv2 option. Third-party licences are preserved separately. Source-family decisions are supported by the exact upstream source archive and licence headers, not inferred solely from generic Python package metadata.",
              "files": records, "errors": errors, "passed": not errors}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(f"Qt native runtime: {len(records)} DLLs; {len(errors)} unreviewed/prohibited entries")
    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
