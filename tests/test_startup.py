"""Launcher readiness uses generated local events, never a user process."""

import ctypes
import os
import subprocess
import sys
import uuid

import pytest

from mira_media import startup


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.delenv(startup.EVENT_ENVIRONMENT, raising=False)


def test_source_or_direct_core_launch_needs_no_event_or_qt(monkeypatch):
    monkeypatch.setattr(startup, "_signal_event", lambda name: pytest.fail("No event should be opened"))
    assert startup.notify_ready() is False
    code = ('import sys; from mira_media.startup import notify_ready; '
            'assert notify_ready() is False; '
            'assert not any(n.startswith(("PySide6", "shiboken6")) for n in sys.modules)')
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, timeout=10, check=False)
    assert result.returncode == 0


@pytest.mark.parametrize("name", ["Global\\MiraStartup-1-" + "a" * 32,
                                  "Local\\UnrelatedUserEvent", "Local\\MiraStartup-0-" + "a" * 32,
                                  "Local\\MiraStartup-1-not-a-nonce", "x" * 500])
def test_unrelated_or_malformed_names_are_removed_and_never_opened(monkeypatch, name):
    monkeypatch.setenv(startup.EVENT_ENVIRONMENT, name)
    monkeypatch.setattr(startup, "_signal_event", lambda event: pytest.fail("Invalid event opened"))
    assert startup.notify_ready() is False
    assert startup.EVENT_ENVIRONMENT not in os.environ


def test_readiness_is_one_shot_and_stale_events_cannot_reach_workers(monkeypatch):
    name = "Local\\MiraStartup-77-" + uuid.uuid4().hex
    calls = []
    def signal(event):
        assert startup.EVENT_ENVIRONMENT not in os.environ
        calls.append(event)
        return True
    monkeypatch.setattr(startup, "_signal_event", signal)
    monkeypatch.setenv(startup.EVENT_ENVIRONMENT, name)
    assert startup.notify_ready() is True
    assert startup.notify_ready() is False
    assert calls == [name]


def test_stale_event_or_windows_error_never_interrupts_app_startup(monkeypatch):
    monkeypatch.setenv(startup.EVENT_ENVIRONMENT, "Local\\MiraStartup-77-" + uuid.uuid4().hex)
    def fail(name):
        raise OSError("GENERATED-helper-error-not-for-logs")
    monkeypatch.setattr(startup, "_signal_event", fail)
    assert startup.notify_ready() is False
    assert startup.EVENT_ENVIRONMENT not in os.environ


@pytest.fixture(scope="module")
def qt_app():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    return QApplication.instance() or QApplication([])


def test_first_paint_watch_is_once_and_notifies_after_event_returns(monkeypatch, qt_app):
    from PySide6.QtCore import QCoreApplication, QEvent, QObject
    app = qt_app
    events = []

    class Window(QObject):
        def event(self, event):
            if event.type() == QEvent.Type.Paint:
                events.append("paint")
            return super().event(event)

    window = Window()
    monkeypatch.setattr(startup, "notify_ready", lambda: events.append("ready"))
    startup.watch_first_paint(window)
    watcher = window._mira_startup_watch
    startup.watch_first_paint(window)
    assert window._mira_startup_watch is watcher
    app.processEvents()
    assert events == []
    QCoreApplication.sendEvent(window, QEvent(QEvent.Type.Paint))
    assert events == ["paint"]
    app.processEvents()
    assert events == ["paint", "ready"]
    QCoreApplication.sendEvent(window, QEvent(QEvent.Type.Paint))
    app.processEvents()
    assert events == ["paint", "ready", "paint"]


def test_destroying_unpainted_window_does_not_dismiss_loader(monkeypatch, qt_app):
    from PySide6.QtCore import QCoreApplication, QEvent, QObject
    app = qt_app
    events = []
    window = QObject()
    monkeypatch.setattr(startup, "notify_ready", lambda: events.append("ready"))
    startup.watch_first_paint(window)
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    assert events == []


@pytest.mark.skipif(os.name != 'nt', reason='Actual Windows event handshake')
def test_generated_real_windows_event_is_signalled_once_and_handle_is_closed(monkeypatch):
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateEventW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    name = f"Local\\MiraStartup-{os.getpid()}-{uuid.uuid4().hex}"
    event = kernel.CreateEventW(None, True, False, name)
    assert event
    try:
        assert kernel.WaitForSingleObject(event, 0) == 258
        monkeypatch.setenv(startup.EVENT_ENVIRONMENT, name)
        assert startup.notify_ready() is True
        assert kernel.WaitForSingleObject(event, 0) == 0
        assert startup.EVENT_ENVIRONMENT not in os.environ
        assert startup.notify_ready() is False
    finally:
        kernel.CloseHandle(event)
    monkeypatch.setenv(startup.EVENT_ENVIRONMENT, name)
    assert startup.notify_ready() is False
