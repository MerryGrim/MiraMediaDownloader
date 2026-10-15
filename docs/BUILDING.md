# Building Mira Media Downloader

[Русский](../README.md) · [English](README.en.md) · [简体中文](README.zh-CN.md)

The Windows application uses native Qt Widgets, with a separate Qt WebEngine
view for signing in to X or Pixiv. Ready-to-use packages include Python and Qt;
end users do not need to install Python.

## Development environment

- Windows x64 and Python 3.12–3.14 x64, supported by the pinned bindings.
- The exact dependencies in [requirements.txt](../requirements.txt).
- Visual Studio C++ Build Tools x64 and the Windows SDK for the native launcher.
- Inno Setup 7 for the optional installer; pass its `ISCC.exe` through `-Compiler`.

Use a short working path, such as `D:\MiraBuild`, to avoid Windows path limits.

```powershell
git clone https://github.com/MerryGrim/MiraMediaDownloader.git
cd MiraMediaDownloader
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_mira.py
```

## Test and package

```powershell
.\.venv\Scripts\python.exe -m pip install pytest==9.1.1
.\.venv\Scripts\python.exe -m pytest
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Python .\.venv\Scripts\python.exe
```

The build script installs the pinned packaging tools, collects the runtime,
builds the small native startup launcher, and creates a complete portable
folder and ZIP. The user-facing executable stays at the root; the Core and
its dependencies stay in `runtime`.

The launcher build discovers MSVC using `vswhere`. For nonstandard tool
locations, pass `-BuildToolsRoot` and `-WindowsSdkRoot` to the build script.

To package the verified application folder as an installer:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-installer.ps1 -Python .\.venv\Scripts\python.exe -Compiler "C:\Path\To\Inno Setup\ISCC.exe"
```

Use `-Bundle` and `-OutputDirectory` to select an existing complete bundle and
the installer destination. Installing Mira is per-user. Microsoft Visual C++
x64 Runtime is a separate system prerequisite: its official installer is
offered only when needed and with the user's consent. Proprietary compiler
runtime DLLs are not bundled as if they were GPL source.

## Documentation screenshots

[`capture_readme.py`](../scripts/capture_readme.py) captures the actual widgets
with isolated settings, a generated collection and no real accounts. See
[`screenshots/README.md`](screenshots/README.md) for the screenshot provenance.

## Corresponding source and licensing

The [download page](https://github.com/MerryGrim/MiraMediaDownloader/releases/latest)
supplies application source, upstream dependency source and installer source
alongside the Windows packages. Their exact contents and build provenance are
documented in the source companions and their checksum manifests.

Read [LICENSING.md](LICENSING.md),
[DEPENDENCY_PERMISSION.md](DEPENDENCY_PERMISSION.md),
[QT_SOURCE_BUILD.md](QT_SOURCE_BUILD.md), [COPYRIGHT](../COPYRIGHT) and
[third-party notices](../THIRD_PARTY_NOTICES.md) before redistributing a modified
binary. The source archives preserve upstream build files and notices; an
identical binary hash is not promised for a different toolchain or build path.

Keep user cookies, DPAPI sessions, browser profiles, downloaded artwork,
personal settings and `.mira` out of public Git commits and release packages.
