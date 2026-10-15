# Licensing and source code — Windows 1.4.4

Review date: 15 October 2026.

## License selection

Mira Media Downloader's original source, tests, build scripts and documentation
are offered under **GPL-2.0-or-later**, with the original-code dependency
permission in [COPYRIGHT](../COPYRIGHT). [LICENSE](../LICENSE) contains the full,
unmodified GNU GPL version 2 text. Third-party components retain their own terms.

The combined-program selection for this release uses **GPLv2** for gallery-dl
1.32.16 and for the shipped Qt/PySide portions that offer it. It does not
relicense gallery-dl as GPLv3 and does not select LGPLv3 for those portions.
Chromium, Python, Requests and other third-party code retain their applicable
licenses, copyright notices and permissions.

Requests is Apache-2.0. The reasoning for gallery-dl's intentional required
Requests dependency is the implicit permission recognized by the GNU FAQ,
§InterpreterIncompat. This is a documented interpretation of the published
dependency, not a fabricated written exception from upstream. Mira also gives
an explicit permission for its own original code. The full rationale and primary
references are in [DEPENDENCY_PERMISSION.md](DEPENDENCY_PERMISSION.md).

## Changes made for this public release

- The runtime uses **Qt/PySide 6.11.2**, with official release source archives
  whose publisher hashes were checked against the downloaded files. This avoids
  substituting an RC source archive for the separate 6.140.0 final wheel.
- Packaging excludes the unused Qt Virtual Keyboard DLL/plugin/data. Every
  retained Qt module is checked against the selected licensing options.
- Qt WebEngine/Chromium attribution texts are extracted byte-for-byte from the
  exact official 6.11.2 source archive. Their manifest records original paths,
  source archive provenance and SHA-256 values. Original notices remain intact.
- App-local Microsoft compiler runtime DLLs are excluded. The installer and
  native launcher check a separately installed system VC++ x64 Runtime; the
  installer offers Microsoft's separate official setup when necessary. These
  proprietary DLLs are not falsely claimed to be supplied as GPL source.
- The source companion supplies application source plus upstream dependency
  sources, license texts and build/install instructions alongside the binaries.
  Mutable home-page links are not used as a substitute for supplied source.

## Download the corresponding source

At [release v1.4.4](https://github.com/MerryGrim/MiraMediaDownloader/releases/tag/v1.4.4),
download **both**:

1. `MiraMediaDownloader-1.4.4-Source.zip`: original Mira source, assets, tests,
   dependency pins, native launcher, packaging and installer scripts.
2. `MiraMediaDownloader-1.4.4-DependencySources.zip`: official Qt 6.11.2 source
   including WebEngine/Chromium, PySide/Shiboken source, CPython source and its
   native dependencies, gallery-dl, Requests and the other runtime/build sources.
   Original archive layouts, notices, source URLs, build information and
   checksum manifests are preserved. Its README explains extraction/building.

`SHA256SUMS-1.4.4.txt` at the same release verifies the published assets. Sources
are available at the same public location as the executable packages without
an account, payment, or source-request procedure. This is direct source
distribution, not a promise to supply missing sources at a later date.
`SOURCE_CODE.txt` in each Windows package points to these exact release assets.

The dependency companion is intentionally larger than the application because
it contains Qt/Chromium source. It is a separate optional download for users
who need the source. Mira's application payload is self-contained. Installation
and launch work offline once the separately installed Microsoft VC++ x64 runtime
is present; acquiring a missing prerequisite needs the explicit Microsoft download
described below.

## Build and modification

Mira's build and installer scripts are under `scripts/`; instructions are in
[README.md](../README.md). The dependency companion contains upstream source
trees with their original build scripts and source/patch provenance. The build
environment manifest records actual package/runtime versions. No modifications
to third-party runtime source were made by Mira; only the collected file set is
reduced. Build-machine paths and timestamps can differ; bit-identical output is
not claimed.

Qt runtime DLLs remain in `runtime/_internal/PySide6` in the onedir package.
There is no runtime integrity check that rejects replacements or user-modified
libraries. License/attribution documents must be kept when redistributing.

The complete Qt source archive can contain extra independently licensed modules
that are absent from the binary. Including an original source archive does not
mean every module in that archive is linked into Mira or given a new license.
The actual component/file manifests identify the delivered runtime.

## Scope

This documents the licensing decisions and source delivery for **this** release,
not a new grant for another author's code or a certification of arbitrary
future modifications. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
and `licenses/` for original terms. Application-created artwork is offered
under GPL-2.0-or-later to the extent rights exist; its provenance is in
[assets/ARTWORK.md](../assets/ARTWORK.md). Downloaded images, website content
and platform names/marks retain their owners' rights.

## Microsoft system runtime prerequisite

The release does not bundle VCRUNTIME/MSVCP/CONCRT/VCAMP/VCOMP/MFC runtime DLLs.
They are supplied through a separately installed Microsoft VC++ x64 system
runtime, with minimum 14.44.35211. This follows the distinction in the
[GNU FAQ, WindowsRuntimeAndGPL](https://www.gnu.org/licenses/gpl-faq.en.html#WindowsRuntimeAndGPL)
instead of treating app-local proprietary DLLs as exempt corresponding source.
The minimum was checked with the actual CPython 3.14.8 and Qt 6.11.2 inputs.
Microsoft's redistributable remains separately licensed; its installer is
downloaded from Microsoft only on an explicit user action when required.
It is not inserted into the GPL release assets. Mira's installer remains per-user;
the system component's own installer can require administrator confirmation.
