# Runtime dependency permission and licence choices

This records the dependency selection for the Windows 1.4.4 release. Mira's original code remains **GPL-2.0-or-later**. The complete, unmodified GPLv2 text is in [`LICENSE`](../LICENSE); [`COPYRIGHT`](../COPYRIGHT) contains the project's explicit additional permission for its original code. Third-party components retain their own licences.

## gallery-dl and Requests

gallery-dl 1.32.16 specifies **GPL-2.0-only**. Its exact upstream release explicitly requires Requests and its extractor uses Requests directly. Mira subclasses the extractor in the same Python program. Accordingly, the combined-program selection uses **GPLv2**, rather than purporting to relicense gallery-dl to GPLv3. Mira's “or later” choice applies to Mira's original contributions and does not extend another author's grant. Sources: [release metadata](https://github.com/mikf/gallery-dl/blob/v1.32.16/setup.py), [extractor implementation](https://github.com/mikf/gallery-dl/blob/v1.32.16/gallery_dl/extractor/common.py).

Requests 2.34.2 remains **Apache-2.0**. The [Apache Software Foundation's compatibility explanation](https://apache.org/licenses/GPL-compatibility.html) distinguishes GPLv3 compatibility from GPLv2 incompatibility; the two licence identifiers alone therefore do not establish permission for this combination.

For gallery-dl's deliberate, required Requests dependency, this release relies on the intentional-dependency reasoning acknowledged by the [GNU FAQ, §InterpreterIncompat](https://www.gnu.org/licenses/gpl-faq.en.html#InterpreterIncompat): a copyright holder's release of a GPL program specifically designed for otherwise incompatible facilities can imply permission to link it with those facilities. The FAQ recommends an explicit statement. This is our documented interpretation of the upstream's published dependency, **not** a claim that gallery-dl includes a separately written Requests exception or that Mira can grant an exception for gallery-dl's authors.

Mira's own permission in `COPYRIGHT` explicitly covers the original Mira code's use of Requests and the named GUI/runtime libraries. It resolves the project's own licence choice without modifying any upstream licence or replacing the preceding rationale.

## Qt, PySide and Chromium

Where the shipped Qt/PySide module offers GPLv2, the release selects that GPLv2 option. It does not select LGPLv3 or GPLv3 for those portions of the combined GPLv2 program. Components that offer no suitable GPLv2 option must not be added merely because they are present in a broad development package; the actual shipped modules and source provenance are recorded in the release's component/source manifests.

[Qt WebEngine's licensing statement](https://doc.qt.io/qt-6.11/qtwebengine-licensing.html) expressly describes Chromium as part of WebEngine Core, offers GPLv2 for the Qt-specific parts, and requires compliance with Chromium's separate licences. The release uses that offered Qt licence choice for the intentionally distributed module. Chromium's BSD, Apache, LGPL and other component terms remain applicable; they are not relabelled GPLv2. Their licence texts and attribution records accompany the release.

The additional permission in `COPYRIGHT` applies only to original Mira contributions. It does not assert that the whole third-party dependency tree has a new blanket exception. Package-level SPDX metadata also does not override a module-specific notice.

## Distribution records

Mira's original installer script also has explicit permission to combine with
Inno Setup and RemObjects Pascal Script, as named in `COPYRIGHT`. This covers
only Mira's installer code; gallery-dl is a separate installed payload and is
not linked into the installer interpreter. Original installer-engine notices
and the required Pascal Script acknowledgement are retained. The release's
`InstallerSources.zip` provides the exact installer-engine source materials.

The small original Win32 launcher uses the compiler's static runtime so it can
display the prerequisite message before Qt/Python is available. That original
launcher code is covered by Mira's explicit dependency permission, including the
Microsoft compiler runtime; it contains no gallery-dl code. The frozen Core's
PyInstaller bootloader retains its upstream exception. App-local Microsoft
runtime **DLLs** are excluded; Python/Qt use the separately installed system
runtime as described in `LICENSING.md`. This does not relabel Microsoft's code
as GPL source or claim its proprietary source is in the dependency companion.

The binary release must be accompanied by its corresponding application and dependency source, original licence and copyright notices, component provenance, exact versions/checksums, and the scripts and instructions needed to build and install it. See [`LICENSING.md`](LICENSING.md) and [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) for those records and instructions. This permission does not waive source obligations or substitute mutable upstream home-page links for the release's supplied source materials.

This document records the project's licensing decisions and their basis. It does not claim a new permission from upstream authors or a legal certification of every possible modification or redistribution. Downloaded artwork, website content and third-party trademarks are outside the software licence grant.
