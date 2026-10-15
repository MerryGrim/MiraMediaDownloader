# Screenshot provenance

These are real Windows captures of Mira Media Downloader's native Qt widgets.
Russian, English and Simplified Chinese are shown in both light and dark themes.
The date selector and help window show the application's own modal presentation,
including its blurred backdrop.

The gallery pictures are original, synthetic QPainter landscapes, reproduced
from `mira_media/design_diagnostics.py`. The example URL and counters are demo
data. No third-party artwork, cookies, passwords or personal collection data
is present. No platform login or download job runs during capture.

`scripts/capture_readme.py` uses isolated settings, an empty session vault and a
scratch collection. The displayed `D:\Mira Media` path is only example text;
the capture does not create or inspect a collection at that location. The
capture instance's small header label reads `MEDIA DOWNLOADER` to keep the
project presentation independent of a release number. The production UI is
unchanged.

Windows renders the actual rounded window corners and shadows above an owned
solid backdrop. PNG files are saved directly from the compositor capture;
the interface is not generated, redrawn or retouched.

To reproduce on Windows, using the project's installed dependencies:

```powershell
python scripts/capture_readme.py
```

The output goes to this directory. The isolated capture workspace and its
validation report are placed beside the repository in `readme-capture`.
Keep other application windows out of the foreground during capture.
