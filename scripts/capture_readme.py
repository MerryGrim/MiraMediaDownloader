"""Capture real, isolated Windows UI screenshots for the public README.

No platform requests, worker jobs, browser profiles or real collections are used.
The only presentation-only adjustment is omitting the version label in this
capture instance. Window corners and shadows are rendered by the compositor.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def native_capture(window, layers, destination: Path, settle) -> dict:
    """Capture only our HWNDs above an owned solid backdrop, without retouching."""
    from PIL import Image
    from mira_media.corner_capture import api, client_geometry

    user, gdi = api(), C.WinDLL("gdi32")
    user.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                                   C.c_int, C.c_int, C.c_int, C.c_int,
                                   W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p]
    user.CreateWindowExW.restype = W.HWND
    user.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
    user.DestroyWindow.argtypes = [W.HWND]
    user.GetWindowLongW.argtypes = [W.HWND, C.c_int]
    user.GetWindowLongW.restype = W.LONG
    user.GetDC.argtypes = [W.HWND]
    user.GetDC.restype = W.HDC
    user.ReleaseDC.argtypes = [W.HWND, W.HDC]
    gdi.CreateCompatibleDC.argtypes = [W.HDC]
    gdi.CreateCompatibleDC.restype = W.HDC
    gdi.CreateCompatibleBitmap.argtypes = [W.HDC, C.c_int, C.c_int]
    gdi.CreateCompatibleBitmap.restype = W.HBITMAP
    gdi.SelectObject.argtypes = [W.HDC, W.HANDLE]
    gdi.SelectObject.restype = W.HANDLE
    gdi.DeleteObject.argtypes = [W.HANDLE]
    gdi.DeleteDC.argtypes = [W.HDC]
    gdi.BitBlt.argtypes = [W.HDC, C.c_int, C.c_int, C.c_int, C.c_int, W.HDC, C.c_int, C.c_int, W.DWORD]
    gdi.BitBlt.restype = W.BOOL
    gdi.SetBkColor.argtypes = [W.HDC, W.DWORD]
    gdi.ExtTextOutW.argtypes = [W.HDC, C.c_int, C.c_int, W.UINT, C.POINTER(W.RECT), W.LPCWSTR, W.UINT, C.c_void_p]

    hwnd = int(window.winId())
    geometry = client_geometry(hwnd)
    left, top, right, bottom = geometry["window"]
    margin = 28
    x, y = left - margin, top - margin
    width, height = right - left + margin * 2, bottom - top + margin * 2
    # A real owned window supplies the neutral canvas behind DWM's clipped
    # corners and native shadow. No desktop pixels can enter the capture.
    background = (230, 235, 244)
    backdrop = user.CreateWindowExW(0x80, "STATIC", "Mira README owned backdrop", 0x80000000,
                                   x, y, width, height, None, None, None, None)
    assert backdrop
    states = [(int(widget.winId()), bool(user.GetWindowLongW(int(widget.winId()), -20) & 8))
              for widget in [window, *layers]]
    screen = memory = bitmap = previous = None
    try:
        user.SetWindowPos(backdrop, W.HWND(-1), x, y, width, height, 0x0050)
        for layer, _ in states:
            user.SetWindowPos(layer, W.HWND(-1), 0, 0, 0, 0, 0x0013)
        user.SetWindowPos(backdrop, hwnd, x, y, width, height, 0x0050)
        settle(100)
        dc = user.GetDC(backdrop)
        try:
            gdi.SetBkColor(dc, background[0] | background[1] << 8 | background[2] << 16)
            rect = W.RECT(0, 0, width, height)
            assert gdi.ExtTextOutW(dc, 0, 0, 2, C.byref(rect), "", 0, None)
        finally:
            user.ReleaseDC(backdrop, dc)
        C.WinDLL("dwmapi").DwmFlush()
        time.sleep(.18)
        screen = user.GetDC(None)
        memory = gdi.CreateCompatibleDC(screen)
        bitmap = gdi.CreateCompatibleBitmap(screen, width, height)
        previous = gdi.SelectObject(memory, bitmap)
        assert gdi.BitBlt(memory, 0, 0, width, height, screen, x, y, 0x00CC0020)
        gdi.SelectObject(memory, previous)
        previous = None

        class Header(C.Structure):
            _fields_ = [("size", W.DWORD), ("width", W.LONG), ("height", W.LONG),
                        ("planes", W.WORD), ("bits", W.WORD), ("compression", W.DWORD),
                        ("image", W.DWORD), ("x", W.LONG), ("y", W.LONG),
                        ("used", W.DWORD), ("important", W.DWORD)]

        header = Header(C.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        raw = C.create_string_buffer(width * height * 4)
        gdi.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, C.c_void_p, C.c_void_p, W.UINT]
        assert gdi.GetDIBits(memory, bitmap, 0, height, raw, C.byref(header), 0) == height
        image = Image.frombytes("RGB", (width, height), raw.raw, "raw", "BGRX")
        corner_pixels = [image.getpixel(point) for point in
                         [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]]
        # DWM's shadow may darken even the padded edge; its neutral tint must
        # still be that of our owned backdrop, never an unrelated desktop.
        assert all(g >= 120 and abs(r / g - background[0] / background[1]) < .02
                   and abs(b / g - background[2] / background[1]) < .02
                   for r, g, b in corner_pixels), (corner_pixels, geometry, [x, y, width, height])
        image.save(destination, optimize=True)
        return {"name": destination.name, "pixels": [width, height],
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "native_window": geometry, "owned_background_rgb": background,
                "native_chrome": window.chrome.native_diagnostics()}
    finally:
        if previous and memory:
            gdi.SelectObject(memory, previous)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if memory:
            gdi.DeleteDC(memory)
        if screen:
            user.ReleaseDC(None, screen)
        user.DestroyWindow(backdrop)
        for layer, was_topmost in reversed(states):
            if not was_topmost:
                user.SetWindowPos(layer, W.HWND(-2), 0, 0, 0, 0, 0x0013)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "screenshots")
    parser.add_argument("--work", type=Path, default=ROOT.parent / "readme-capture")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Native rounded-window captures require Windows.")
    output, work = args.output.resolve(), args.work.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    os.environ["APPDATA"] = str(work / "roaming")
    os.environ["LOCALAPPDATA"] = str(work / "local")
    os.environ["MIRA_SESSION_DIR"] = str(work / "empty-vault")

    from PySide6.QtCore import QDate, QEventLoop, QPoint, QSettings, Qt, QTimer
    from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap, QPolygon
    from PySide6.QtWidgets import QApplication, QDialog, QLabel
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(work / "settings"))
    settings = QSettings("Mira", "MiraMediaDownloader")
    settings.clear()
    settings.setValue("destination", str(work / "empty-collection"))
    settings.setValue("ui_language", "ru")
    settings.setValue("ui_theme", "dark")
    settings.sync()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    app.setStyle("Fusion")
    from mira_media.app_identity import apply_app_icon, set_windows_app_id
    from mira_media.themes import get_theme
    from mira_media.ui import MainWindow
    from mira_media.window_chrome import install_dialog_chrome_hook
    set_windows_app_id()
    apply_app_icon(app)
    install_dialog_chrome_hook(app)
    window = MainWindow()
    window.resize(1180, 770)
    available = window.screen().availableGeometry()
    window.move(available.center() - window.rect().center())
    window.show()

    def settle(milliseconds=120):
        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()
        app.processEvents()

    settle(400)
    # This label is the one intentional presentation change, local to the
    # screenshot instance. The application sources and saved settings keep it.
    eyebrow = window.findChild(QLabel, "eyebrow")
    assert eyebrow is not None
    eyebrow.setText("MEDIA DOWNLOADER")
    window.profile.setText("https://x.com/mira_gallery")
    # Set only the visible editor after construction; no destination_changed,
    # collection refresh, download, or filesystem action is invoked for D:.
    window.destination.setText(r"D:\Mira Media")
    palettes = [("#efd7c7", "#d9a2b5", "#f8e9c5", "#795e94"),
                ("#c6dcd9", "#87b5b1", "#ecddac", "#31575e"),
                ("#cdc7e7", "#9284b7", "#ead6ef", "#52436e"),
                ("#e4c39b", "#c4896b", "#f7d9a7", "#8b5646"),
                ("#b9c9dc", "#687ea3", "#e0deca", "#30435f"),
                ("#d6dfbd", "#92aa8b", "#eee2b6", "#48694e")]
    images = work / "demonstration-artwork"
    images.mkdir(exist_ok=True)
    # The same original QPainter landscapes as design_diagnostics.py.
    for index, palette in enumerate(palettes[:3]):
        image = QPixmap(720, 460)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, 720, 460)
        gradient.setColorAt(0, QColor(palette[0]))
        gradient.setColorAt(1, QColor(palette[1]))
        painter.fillRect(image.rect(), gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette[2]))
        painter.drawEllipse(200, 45, 300, 290)
        painter.setBrush(QColor(palette[3]))
        painter.drawPolygon(QPolygon([QPoint(0, 390), QPoint(190, 190), QPoint(350, 330),
                                      QPoint(510, 140), QPoint(720, 390), QPoint(720, 460), QPoint(0, 460)]))
        painter.end()
        path = images / f"90000{index}_01.png"
        assert image.save(str(path))
        window._event({"type": "item", "key": f"x:demo:{index}", "post_id": f"90000{index}",
                       "index": 1, "author_id": "mira_gallery", "platform": "x", "path": str(path)})
    window._event({"type": "stats", "found": 3, "downloaded": 3, "skipped": 0, "failed": 0})
    window._event({"type": "state", "state": "completed"})
    window.tabs.setCurrentIndex(0)
    window.gallery.clearSelection()
    window.gallery.setFocus()
    captures = []
    for language, filename in [("ru", "ru"), ("en", "en"), ("zh_CN", "zh-CN")]:
        window._change_language(language)
        for theme in ["dark", "light"]:
            if get_theme() != theme:
                window._toggle_theme()
            eyebrow.setText("MEDIA DOWNLOADER")
            settle(250)
            captures.append(native_capture(window, [], output / f"main-{filename}-{theme}.png", settle))

    window._change_language("ru")
    if get_theme() != "dark":
        window._toggle_theme()
    eyebrow.setText("MEDIA DOWNLOADER")
    # Give the actual calendar popup and help dialog enough physical room;
    # the main-view captures above stay compact with one complete gallery row.
    window.resize(1180, 940)
    window.move(available.center() - window.rect().center())
    settle(200)
    errors = []

    def capture_dates():
        try:
            from mira_media.date_filter import DateFilterDialog
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, DateFilterDialog)
            dialog.custom_dates.setChecked(True)
            dialog.from_enabled.setChecked(True)
            dialog.to_enabled.setChecked(True)
            dialog.date_from.setDate(QDate(2026, 10, 1))
            dialog.date_to.setDate(QDate(2026, 10, 15))
            settle(200)
            dialog.date_from.click()
            popup = dialog.date_from.popup
            assert popup is not None and popup.isVisible()
            settle(200)
            captures.append(native_capture(window, [dialog, popup], output / "date-filter.png", settle))
            popup.hide()
            dialog.reject()
        except Exception as exc:
            errors.append(f"date-filter: {type(exc).__name__}: {exc}")
            modal = QApplication.activeModalWidget()
            if modal is not None:
                modal.reject()

    QTimer.singleShot(180, capture_dates)
    window._show_date_filter()
    settle(200)

    def capture_help():
        try:
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, QDialog)
            overlay = getattr(window, "_mira_modal_backdrop", None)
            assert overlay is not None and overlay.isVisible()
            settle(250)
            captures.append(native_capture(window, [dialog], output / "help.png", settle))
            dialog.reject()
        except Exception as exc:
            errors.append(f"help: {type(exc).__name__}: {exc}")
            modal = QApplication.activeModalWidget()
            if modal is not None:
                modal.reject()

    QTimer.singleShot(180, capture_help)
    window._show_help()
    window.close()
    assert window.process is None
    report = {"passed": not errors and len(captures) == 8,
              "real_user_cookies_accessed": False, "worker_jobs_started": 0,
              "platform_logins_started": 0, "demonstration_images_only": True,
              "instance_only_label": "MEDIA DOWNLOADER", "errors": errors, "captures": captures}
    (work / "capture-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "captures": len(captures), "errors": errors,
                      "output": str(output), "report": str(work / "capture-report.json")}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
