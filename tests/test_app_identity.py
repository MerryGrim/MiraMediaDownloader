"""Existing brand ICO and process-only identity; no user settings or sessions."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from mira_media import app_identity as identity


def test_import_and_process_identity_do_not_import_qt():
    script = ('import sys; from mira_media.app_identity import set_windows_app_id; '
              'set_windows_app_id(); '
              'assert not any(n.startswith(("PySide6", "shiboken6")) for n in sys.modules)')
    run = subprocess.run([sys.executable, '-c', script], capture_output=True, timeout=10)
    assert run.returncode == 0, run.stderr.decode(errors='replace')


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows current-process AppID')
def test_windows_identity_round_trip_in_own_short_lived_process():
    script = '''
import ctypes as C
from mira_media.app_identity import APP_USER_MODEL_ID, set_windows_app_id
assert set_windows_app_id()
shell=C.WinDLL('shell32'); getter=shell.GetCurrentProcessExplicitAppUserModelID
getter.argtypes=[C.POINTER(C.c_void_p)]; getter.restype=C.c_long
allocated=C.c_void_p()
assert getter(C.byref(allocated)) == 0
try:
    assert C.wstring_at(allocated) == APP_USER_MODEL_ID
finally:
    ole=C.WinDLL('ole32'); ole.CoTaskMemFree.argtypes=[C.c_void_p]
    ole.CoTaskMemFree(allocated)
'''
    run = subprocess.run([sys.executable, '-c', script], capture_output=True, timeout=10)
    assert run.returncode == 0, run.stderr.decode(errors='replace')


def test_windows_identity_failure_is_optional_and_does_not_touch_files(monkeypatch):
    def denied(*args, **kwargs):
        raise OSError('GENERATED unavailable shell')
    monkeypatch.setattr(identity.ctypes, 'WinDLL', denied, raising=False)
    assert identity.set_windows_app_id() is False


def test_source_uses_existing_multi_resolution_ico():
    from PIL import Image
    path = identity.icon_path()
    assert path == Path(__file__).resolve().parents[1] / 'assets' / 'mira.ico'
    with Image.open(path) as image:
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= image.ico.sizes()


def test_frozen_uses_own_meipass_assets_and_never_source_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    assert identity.icon_path() is None
    packaged = tmp_path / 'assets' / 'mira.ico'
    packaged.parent.mkdir()
    packaged.write_bytes(b'GENERATED path-resolution fixture')
    assert identity.icon_path() == packaged
    monkeypatch.delattr(sys, '_MEIPASS')
    assert identity.icon_path() is None


@pytest.fixture(scope='module')
def app():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    return QApplication.instance() or QApplication([])


def test_ico_supplies_real_small_and_large_gui_bitmaps(app):
    from PySide6.QtWidgets import QWidget
    window = QWidget()
    try:
        assert identity.apply_app_icon(app, window)
        for size in (16, 32, 48):
            app_image = app.windowIcon().pixmap(size, size).toImage()
            window_image = window.windowIcon().pixmap(size, size).toImage()
            assert not app_image.isNull() and app_image == window_image
            colors = {app_image.pixelColor(x, y).rgba()
                      for y in range(app_image.height()) for x in range(app_image.width())}
            assert len(colors) > 10  # A rendered brand icon, not a blank solid tile.
    finally:
        window.deleteLater()
        app.processEvents()


def test_missing_packaged_icon_fails_without_replacing_current_icon(app, monkeypatch):
    assert identity.apply_app_icon(app)
    original = app.windowIcon().cacheKey()
    monkeypatch.setattr(identity, 'icon_path', lambda: None)
    assert identity.apply_app_icon(app) is False
    assert app.windowIcon().cacheKey() == original
