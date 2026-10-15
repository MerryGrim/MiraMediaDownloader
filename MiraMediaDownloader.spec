# SPDX-License-Identifier: GPL-2.0-or-later
# Build with scripts/build.ps1 from this directory.
from pathlib import Path
import re

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata, get_package_paths

project = Path(SPECPATH)
datas = []
# Window/taskbar icons are loaded at runtime as well as embedded in the EXE.
datas.append((str(project / "assets" / "mira.ico"), "assets"))
for name in ("gallery-dl", "PySide6-Essentials", "PySide6-Addons", "shiboken6", "requests", "Pillow", "certifi", "pycryptodomex"):
    datas += copy_metadata(name)
datas += collect_data_files("gallery_dl")
qt_translations = Path(get_package_paths("PySide6")[1]) / "translations"
for locale in ("en", "ru", "zh_CN"):
    translation = qt_translations / f"qtbase_{locale}.qm"
    if translation.is_file():
        datas.append((str(translation), "PySide6/translations"))
# build.ps1 installs documentation/notices once at the public bundle root.
# They are not runtime resources and need no duplicate under _internal.

# gallery-dl discovers extractors dynamically; retaining them prevents a release
# from importing correctly in source mode but failing when frozen.
hiddenimports = collect_submodules("gallery_dl")
hiddenimports += ["PIL.Image", "PIL.JpegImagePlugin", "PIL.PngImagePlugin", "PIL.WebPImagePlugin", "PIL.GifImagePlugin"]
# The login view is imported lazily. Retain it and its Qt bindings explicitly;
# PyInstaller's QtWebEngineCore hook collects the renderer, resources/locales,
# and the helper's qt.conf in the matching PySide6 wheel layout.
hiddenimports += ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
                  "PySide6.QtWebChannel", "PySide6.QtPositioning"]

a = Analysis(
    [str(project / "run_mira.py")],
    pathex=[str(project)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Qt Widgets remains the main UI. QtWebEngineWidgets supplies only login;
    # its native dependencies are retained by the module hooks.
    excludes=["PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtSql", "PySide6.QtTest", "pytest", "tkinter"],
    noarchive=False,
    optimize=0,
)
# Qt's Windows wheel imports the operating system ICU with unversioned
# symbols. An unrelated Poppler/Conda ICU on a build-machine PATH exports
# versioned symbols and must never shadow Windows' ICU in the package.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() != 'icuuc.dll'
              and not Path(entry[0]).name.lower().startswith('icudt')]
# Qt's generic hooks collect input plugins even though Widgets uses the native
# Windows keyboard/IME. Do not redistribute the unused GPLv3 Virtual Keyboard.
a.binaries = [entry for entry in a.binaries
              if 'virtualkeyboard' not in entry[0].replace('\\', '/').lower()]
a.datas = [entry for entry in a.datas
           if 'virtualkeyboard' not in entry[0].replace('\\', '/').lower()]
# GPLv2's Windows runtime exception requires these proprietary compiler runtime
# DLLs to be supplied as a separately installed system prerequisite. The native
# launcher and installer check it; they are not part of this application's ZIP.
msvc_runtime = re.compile(r'^(?:vcruntime\d[^/]*|msvcp\d[^/]*|vccorlib\d[^/]*|concrt\d[^/]*|vcamp\d[^/]*|vcomp\d[^/]*|mfc\d[^/]*|ucrtbase)\.dll$', re.I)
a.binaries = [entry for entry in a.binaries
              if not msvc_runtime.fullmatch(Path(entry[0]).name)]
a.datas = [entry for entry in a.datas
           if not msvc_runtime.fullmatch(Path(entry[0]).name)]
# The release renderer uses the ordinary .pak files and V8 snapshot. Debug
# variants shipped in the wheel are developer assets and add about 80 MB.
a.datas = [entry for entry in a.datas if '.debug.' not in Path(entry[0]).name.lower()]
# The application ships Russian, English and Simplified Chinese. Keep their
# Chromium locales plus the English-GB fallback rather than fifty unused packs.
supported_browser_locales = {'en-us.pak', 'en-gb.pak', 'ru.pak', 'zh-cn.pak'}
a.datas = [entry for entry in a.datas
           if '/qtwebengine_locales/' not in entry[0].replace('\\', '/').lower()
           or Path(entry[0]).name.lower() in supported_browser_locales]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MiraMediaDownloaderCore",
    icon=str(project / 'assets' / 'mira.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MiraMediaDownloader")
