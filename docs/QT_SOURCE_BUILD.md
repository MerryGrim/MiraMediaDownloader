# Qt / PySide / software OpenGL sources for Mira 1.4.4

These original upstream source archives accompany the Windows release. They are
separate from the installer and portable application. Their individual upstream
licences remain in force; this document does not relicense every file as GPLv2.
Qt-authored runtime portions used by this release offer GPLv2 as one of their
licence alternatives. The unused GPLv3-only Qt Virtual Keyboard runtime is
excluded from the Windows package.

The complete Qt archive contains Qt WebEngine and the Chromium submodule source,
including bundled third-party code. It also contains the source for the base,
Widgets, Quick/QML support, SVG, image-format plugins, Positioning, SerialPort,
WebChannel and translations used by the collected runtime. Keeping the complete
archive preserves upstream build scripts/configuration and avoids a source
snapshot missing Chromium or a supporting native module.

The PySide setup archive provides PySide6 and Shiboken6 source and the upstream
binding-generation/packaging scripts. The original `README.md`,
`README.pyside6.md`, `README.shiboken6.md`, `build_scripts/`, `coin/`, source CMake
files and documentation describe rebuilding the bindings. On Windows the Qt
DLLs are copied into the wheel by the upstream packaging scripts.

For Qt, start with the source archive's `configure`, CMake files, build
documentation and CI instructions. A release rebuild uses a supported Windows
MSVC x64 development environment, CMake/Ninja, and the prerequisites required by
Qt WebEngine/Chromium. The original Qt build and installation scripts are
included. For PySide, use the supplied setup script against the rebuilt Qt's
`qtpaths6` and a compatible Python interpreter, with the upstream limited-API
option when producing ABI3 bindings. This release uses unmodified official
PySide6 6.11.2 ABI3 Windows x64 wheels; it does not claim an independently
bit-for-bit-reproduced Qt build.

Software OpenGL fallback `opengl32sw.dll` contains Mesa 11.2.2 and LLVM 3.6.2.
Its native code/data sections match Qt's official prebuilt
`opengl32sw-64-mesa_11_2_2-signed_sha256.7z`. The whole-file hashes differ because
the signing envelope differs. `mesa-opengl32sw-identity.json` records all section
hashes. The unmodified Mesa tag archive and LLVM source archive are provided.
Mesa includes MIT-style and other notices, including LGPL notices for some
parts; LLVM 3.6.2 uses its historical University of Illinois/NCSA licence and
associated third-party notices, not the licence of today's LLVM versions.

For the historical software rasterizer build, Qt's documented 2016 toolchain is
MSVC 2015 Update 2, Python 2.7, SCons 2.4.1, CMake and the requisite parser/
template tools. First build LLVM 3.6.2 with the static release/debug MSVC runtime
options and an installation prefix. Then point Mesa's `LLVM` environment setting
at that LLVM installation and use its SCons Windows x64 release `libgl-gdi`
target. Rename the resulting software OpenGL DLL to `opengl32sw.dll` when using
Qt's software OpenGL fallback. The original source build scripts are included.
This is a factual description of the historical build process; consult the
[Qt maintainer's archived instructions](https://wiki.qt.io/index.php?title=MesaLlvmpipe&oldid=28758)
for the original context and commands.

The application is packaged with replaceable DLLs and no runtime integrity
enforcement preventing replacement of these libraries. Source build and
installation recipes for Mira itself are in the accompanying application source
archive and repository. If rebuilding the application against changed Qt
libraries, preserve the ABI/compiler compatibility required by those libraries.

The source and binary versions observed agree: Qt/PySide/WebEngine 6.11.2,
Chromium 140.0.7339.225 and the WebEngine security patch version 151.0.7922.71.
Exact archive sizes, SHA-256 values and upstream provenance are supplied in the
release manifest. Original notices are preserved in the Windows package under
`licenses/QtWebEngine-attributions` and `licenses/Mesa-LLVM-opengl32sw`.
