# Qt modules supplied with Windows 1.4.4

The release uses unmodified official Qt/PySide **6.11.2** Windows x64 libraries.
For Qt-authored portions of the modules below it selects the offered
**GPL-2.0-only** alternative. Each embedded third-party component keeps its
own licence. The release's runtime audit lists the actual files and hashes;
the table is a source-family map, not a new blanket licence grant.

| Collected Qt runtime family | Source subdirectory in the complete Qt archive |
| --- | --- |
| Core, Gui, Widgets, Network, OpenGL, PrintSupport and their native platform/style/TLS plugins | `qtbase` |
| Qml, QmlMeta, QmlModels, QmlWorkerScript, Quick, QuickWidgets | `qtdeclarative` |
| Positioning and positioning plugins | `qtpositioning` |
| SerialPort | `qtserialport` |
| Svg and SVG plugins | `qtsvg` |
| Additional raster image format plugins | `qtimageformats` |
| WebChannel | `qtwebchannel` |
| WebEngineCore, WebEngineWidgets and renderer | `qtwebengine` |
| **Pdf and `plugins/imageformats/qpdf.dll`** | **`qtwebengine/src/pdf`** |

Qt PDF is included by Qt's image-format plugin collection. Its Qt-authored
library and plugin sources offer GPLv2; it is not a GPLv3-only module. The
official [Qt PDF 6.11.2 licensing statement](https://doc.qt.io/qt-6.11/qtpdf-licensing.html)
offers GPLv2 or LGPLv3 and separately requires the licences of PDFium and its
third-party components. The exact-version source headers additionally list the
GPL-2.0-only alternative:

- [`src/pdf/qpdfdocument.h`, tag v6.11.2](https://code.qt.io/cgit/qt/qtwebengine.git/tree/src/pdf/qpdfdocument.h?h=v6.11.2).
- [`src/pdf/plugins/imageformats/pdf/qpdfiohandler.cpp`, tag v6.11.2](https://code.qt.io/cgit/qt/qtwebengine.git/tree/src/pdf/plugins/imageformats/pdf/qpdfiohandler.cpp?h=v6.11.2).
- [`src/pdf/plugins/imageformats/pdf/main.cpp`, tag v6.11.2](https://code.qt.io/cgit/qt/qtwebengine.git/tree/src/pdf/plugins/imageformats/pdf/main.cpp?h=v6.11.2).

The complete original `qt-everywhere-src-6.11.2.tar.xz` supplied in the
corresponding-source companion already contains the Qt PDF sources, PDFium and
their supporting code/build scripts. The preserved source-notice snapshot
includes the PDFium/Chromium notices; it is not a different PDF library fetched
after the binary build. Qt PDF's third-party notices remain unchanged.

The unused GPLv3-only **Qt Virtual Keyboard** module/plugin is excluded from the
Windows runtime. The build-time allowlist fails unknown Qt modules/plugins
instead of inferring their licence from generic PySide distribution metadata.
The runtime also preserves the separate Mesa/LLVM software OpenGL fallback
notices. Microsoft's compiler runtime is an independently installed system
prerequisite, as described in [LICENSING.md](LICENSING.md).

See [DEPENDENCY_PERMISSION.md](DEPENDENCY_PERMISSION.md) for the combined-program
licence selection and dependency-permission reasoning, and
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for the component records.
