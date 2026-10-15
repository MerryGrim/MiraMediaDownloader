"""One-shot readiness signal for Mira's native Windows startup launcher.

Imported without Qt. The process-local event name is removed before use so an
unrelated later worker cannot inherit or signal an old startup event. This
module neither reads preferences/session data nor writes files or logs.
"""

from __future__ import annotations

import ctypes
import os
import re


EVENT_ENVIRONMENT = "MIRA_STARTUP_EVENT"
_EVENT_NAME = re.compile(r"Local\\MiraStartup-[1-9][0-9]*-[0-9a-f]{32}\Z")


def _signal_event(name: str) -> bool:
    if os.name != "nt":
        return False
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenEventW.restype = wintypes.HANDLE
    kernel.SetEvent.argtypes = [wintypes.HANDLE]
    kernel.SetEvent.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # EVENT_MODIFY_STATE only. No process inspection, inheritance or elevation.
    handle = kernel.OpenEventW(0x0002, False, name)
    if not handle:
        return False
    try:
        return bool(kernel.SetEvent(handle))
    finally:
        kernel.CloseHandle(handle)


def notify_ready() -> bool:
    """Signal the owning launcher's event once, after the first native Qt paint.

    Returns False for a direct core/source launch or a stale/invalid event.
    Startup feedback is optional; failure must not prevent the main app opening.
    """
    name = os.environ.pop(EVENT_ENVIRONMENT, "")
    if not isinstance(name, str) or len(name) > 128 or not _EVENT_NAME.fullmatch(name):
        return False
    try:
        return _signal_event(name)
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def watch_first_paint(window) -> None:
    """Notify the launcher after this window's first completed paint.

    Qt is imported lazily, keeping worker/CLI startup free of UI dependencies.
    The filter is retained by its window and registering twice is harmless.
    """
    if getattr(window, "_mira_startup_watch", None) is not None:
        return
    from PySide6.QtCore import QEvent, QObject, QTimer

    class FirstPaint(QObject):
        def __init__(self, owner):
            super().__init__(owner)
            self.done = False

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint and not self.done:
                self.done = True
                watched.removeEventFilter(self)
                # Let Qt finish the paint before dismissing the native loader.
                QTimer.singleShot(0, notify_ready)
            return False

    watcher = FirstPaint(window)
    window._mira_startup_watch = watcher
    window.installEventFilter(watcher)
