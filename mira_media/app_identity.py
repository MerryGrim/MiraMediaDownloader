"""Stable Windows identity and the application's existing multi-size icon.

The module and Windows identity function import no Qt, so CLI/worker startup
stays lightweight. The GUI applies the icon after creating QApplication.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys


APP_USER_MODEL_ID = "Mira.MiraMediaDownloader"


def set_windows_app_id() -> bool:
    """Assign only this process's taskbar identity before creating windows."""
    if os.name != "nt":
        return False
    try:
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        setter = shell.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        return setter(APP_USER_MODEL_ID) == 0
    except (OSError, AttributeError):
        return False


def icon_path() -> Path | None:
    """Resolve only our packaged/source ICO, never an external user icon."""
    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", None)
        if not bundle:
            return None
        root = Path(bundle)
    else:
        root = Path(__file__).resolve().parent.parent
    icon = root / "assets" / "mira.ico"
    return icon if icon.is_file() else None


def apply_app_icon(app, window=None) -> bool:
    """Apply the same ICO to QApplication and an optional top-level window."""
    path = icon_path()
    if path is None:
        return False
    from PySide6.QtGui import QIcon

    icon = QIcon(str(path))
    if icon.isNull():
        return False
    app.setWindowIcon(icon)
    if window is not None:
        window.setWindowIcon(icon)
    return True
