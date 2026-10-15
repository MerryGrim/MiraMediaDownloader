"""Window semantics plus a separate actual-Windows native-message smoke."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from mira_media.localization import get_language, set_language
from mira_media.themes import apply_theme, get_theme
from mira_media.window_chrome import (
    HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT, HTCLIENT, HTLEFT, HTRIGHT,
    HTTOP, HTTOPLEFT, HTTOPRIGHT, _edge_hit_test, _maximized_geometry, install_chrome,
    install_dialog_chrome_hook, DWMWCP_DONOTROUND, DWMWCP_ROUND,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def restore_appearance(app):
    language, theme = get_language(), get_theme()
    yield
    set_language(language)
    apply_theme(app, theme)


@pytest.mark.parametrize("point,expected", [
    ((-1199, -499), HTTOPLEFT), ((-801, -499), HTTOPRIGHT),
    ((-1199, -201), HTBOTTOMLEFT), ((-801, -201), HTBOTTOMRIGHT),
    ((-1000, -499), HTTOP), ((-1000, -201), HTBOTTOM),
    ((-1199, -350), HTLEFT), ((-801, -350), HTRIGHT),
    ((-1000, -350), HTCLIENT), ((0, 0), HTCLIENT),
])
def test_signed_multimonitor_edge_geometry(point, expected):
    assert _edge_hit_test((-1200, -500, -800, -200), *point, 8, 8) == expected


@pytest.mark.parametrize("monitor,work,expected", [
    ((0, 0, 1920, 1080), (0, 0, 1920, 1040), (0, 0, 1920, 1040)),
    ((-1600, -100, 0, 900), (-1560, -100, 0, 900), (40, 0, 1560, 1000)),
    ((1920, -400, 4480, 1040), (1920, -360, 4480, 1040), (0, 40, 2560, 1400)),
])
def test_maximize_uses_monitor_work_area_including_top_left_taskbars(monitor, work, expected):
    assert _maximized_geometry(monitor, work) == expected


def test_fallback_corners_follow_size_and_window_state_without_relayout(app, monkeypatch):
    window = QWidget()
    window.resize(460, 300)
    layout = QVBoxLayout(window)
    field = QLineEdit("unchanged", window)
    layout.addWidget(field)
    chrome = install_chrome(window)
    chrome._windows = type("LegacyWindows", (), {"native_corners": False})()
    chrome._hwnd = 1
    monkeypatch.setattr(chrome, "_sync_native", lambda **kwargs: chrome._sync_corners())
    margins = window.contentsMargins()
    try:
        for width, height in ((460, 300), (620, 420)):
            window.resize(width, height)
            chrome._sync_corners()
            assert chrome._corner_backend == "region"
            assert not window.mask().contains(window.rect().topLeft())
            assert window.mask().contains(window.rect().center())
            assert window.mask().boundingRect() == window.rect()
        for state in (Qt.WindowState.WindowMaximized, Qt.WindowState.WindowFullScreen):
            window.setWindowState(state)
            chrome._sync_corners()
            assert window.mask().isEmpty()
        window.setWindowState(Qt.WindowState.WindowNoState)
        chrome._sync_corners()
        assert not window.mask().isEmpty()
        assert window.layout() is layout and field.parentWidget() is window
        assert window.contentsMargins() == margins and field.text() == "unchanged"
    finally:
        chrome._windows = None
        window.deleteLater()
        app.processEvents()


def test_dwm_transition_clears_legacy_region_and_tracks_fullscreen(app, monkeypatch):
    window = QWidget()
    window.resize(420, 280)
    chrome = install_chrome(window)
    calls = []
    class DwmWindows:
        native_corners = True
        def corners(self, hwnd, rounded):
            calls.append(rounded)
            return True
    chrome._windows = DwmWindows()
    chrome._hwnd = 1
    monkeypatch.setattr(chrome, "_sync_native", lambda **kwargs: chrome._sync_corners())
    try:
        from mira_media.window_chrome import _rounded_region
        window.setMask(_rounded_region(window.width(), window.height()))
        for state, expected in ((Qt.WindowState.WindowNoState, True),
                                (Qt.WindowState.WindowMaximized, False),
                                (Qt.WindowState.WindowFullScreen, False),
                                (Qt.WindowState.WindowNoState, True)):
            window.setWindowState(state)
            chrome._sync_corners()
            assert calls[-1] is expected and window.mask().isEmpty()
            assert chrome._corner_backend == "dwm"
    finally:
        chrome._windows = None
        window.deleteLater()
        app.processEvents()


def test_minimized_maximized_window_does_not_reposition_its_iconic_hwnd(app, monkeypatch):
    window = QWidget()
    chrome = install_chrome(window)
    class DwmWindows:
        native_corners = True
        def monitor(self, hwnd):
            pytest.fail("A minimized HWND must retain its native restore placement")
        def corners(self, hwnd, rounded):
            return True
    chrome._windows = DwmWindows()
    chrome._hwnd = 1
    monkeypatch.setattr(chrome, "_sync_native", lambda **kwargs: chrome._sync_corners())
    try:
        window.setWindowState(Qt.WindowState.WindowMaximized | Qt.WindowState.WindowMinimized)
        assert window.isMaximized() and window.isMinimized()
        chrome._sync_corners()
    finally:
        chrome._windows = None
        window.deleteLater()
        app.processEvents()


def test_controls_are_accessible_idempotent_and_do_not_become_dialog_default(app):
    dialog = QDialog()
    chrome = install_chrome(dialog, minimizable=False, maximizable=False)
    assert install_chrome(dialog) is chrome
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert chrome.minimize_button is None and chrome.maximize_button is None
    assert chrome.controls.close_button is chrome.close_button
    assert chrome.close_button.width() >= 36 and chrome.close_button.height() >= 32
    assert chrome.close_button.accessibleName() and chrome.close_button.toolTip()
    assert not chrome.close_button.autoDefault() and not chrome.close_button.isDefault()
    QTimer.singleShot(0, chrome.close_button.click)
    assert dialog.exec() == QDialog.DialogCode.Rejected
    dialog.deleteLater()
    app.processEvents()


def test_drag_target_ignores_buttons_inputs_and_link_labels(app, monkeypatch):
    window = QWidget()
    outer = QVBoxLayout(window)
    header = QWidget()
    row = QHBoxLayout(header)
    title, action, field = QLabel("Title"), QPushButton("Action"), QLineEdit("Input")
    link = QLabel('<a href="https://example.invalid">Link</a>')
    link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    for widget in (title, action, field, link):
        row.addWidget(widget)
    outer.addWidget(header)
    chrome = install_chrome(window)
    row.addWidget(chrome.controls)
    chrome.set_drag_area(header)
    assert chrome._is_drag_target(header) and chrome._is_drag_target(title)
    for widget in (action, field, link, chrome.close_button):
        assert not chrome._is_drag_target(widget)
    called = []
    monkeypatch.setattr(chrome, "_start_system_move", lambda: called.append(True) or True)
    event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(20, 15), QPointF(100, 100),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    assert chrome.eventFilter(title, event) and called == [True]
    assert not chrome.eventFilter(action, event)
    window.close()
    window.deleteLater()
    app.processEvents()


def test_header_doubleclick_toggles_maximize_and_theme_language_refresh(app):
    window = QWidget()
    layout = QVBoxLayout(window)
    header = QLabel("Title")
    layout.addWidget(header)
    chrome = install_chrome(window)
    layout.addWidget(chrome.controls)
    chrome.set_drag_area(header)
    window.show()
    try:
        doubleclick = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(30, 15), QPointF(100, 100),
                                  Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        assert chrome.eventFilter(header, doubleclick)
        app.processEvents()
        assert window.isMaximized() and chrome.maximize_button.action == "restore"
        assert chrome.eventFilter(header, doubleclick)
        app.processEvents()
        assert not window.isMaximized() and chrome.maximize_button.action == "maximize"
        for language, close in (("ru", "Закрыть"), ("en", "Close"), ("zh_CN", "关闭")):
            set_language(language)
            chrome.refresh()
            assert chrome.close_button.accessibleName() == close
        for theme in ("dark", "light"):
            apply_theme(app, theme)
            chrome.refresh()
            app.processEvents()
            image = chrome.controls.grab().toImage()
            assert not image.isNull()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_close_button_honors_window_close_event_rejection(app):
    class Guarded(QWidget):
        def __init__(self):
            super().__init__()
            self.closes = 0
            self.allow_close = False

        def closeEvent(self, event):
            self.closes += 1
            event.accept() if self.allow_close else event.ignore()

    window = Guarded()
    chrome = install_chrome(window)
    window.show()
    QTest.mouseClick(chrome.close_button, Qt.MouseButton.LeftButton)
    assert window.closes == 1 and window.isVisible()
    window.allow_close = True
    chrome.close_button.click()
    assert window.closes == 2 and not window.isVisible()
    window.deleteLater()
    app.processEvents()


@pytest.fixture
def dialog_hook(app):
    previous = getattr(app, "_mira_dialog_chrome_hook", None)
    hook = install_dialog_chrome_hook(app)
    assert install_dialog_chrome_hook(app) is hook
    yield hook
    if previous is None:
        app.removeEventFilter(hook)
        del app._mira_dialog_chrome_hook
        hook.deleteLater()
        app.processEvents()


def _inspect_modal(dialog, callback):
    """Always end a modal if an assertion fails inside a Qt timer callback."""
    failures = []
    timer = QTimer(dialog)
    timer.setSingleShot(True)

    def inspect():
        try:
            callback()
        except BaseException as exc:
            failures.append(exc)
        finally:
            if dialog.isVisible():
                dialog.reject()
    timer.timeout.connect(inspect)
    timer.start(0)
    result = dialog.exec()
    timer.stop()
    if failures:
        raise failures[0]
    return result


def test_stock_input_dialog_close_rejects_without_replacing_input_or_layout(app, dialog_hook):
    dialog = QInputDialog()
    dialog.setWindowTitle("Create folder")
    dialog.setLabelText("Folder name")
    dialog.setTextValue("untouched input")
    original_layout = dialog.layout()
    original_field = dialog.findChild(QLineEdit)
    original_field_parent = original_field.parentWidget()
    observed = []

    def inspect_and_close():
        chrome = dialog._mira_window_chrome
        observed.append(dialog.isVisible())
        assert dialog.layout() is not None
        if original_layout is not None:
            assert dialog.layout() is original_layout
        assert dialog.findChild(QLineEdit) is original_field and original_field.parentWidget() is original_field_parent
        assert dialog.textValue() == "untouched input"
        assert chrome.minimize_button is None and chrome.maximize_button is None
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog.contentsMargins().top() >= 42
        assert dialog._mira_auto_chrome_header.isVisible()
        field = dialog.findChild(QLineEdit)
        assert field.mapTo(dialog, field.rect().topLeft()).y() >= 42
        chrome.close_button.click()

    assert _inspect_modal(dialog, inspect_and_close) == QDialog.DialogCode.Rejected
    assert observed == [True]
    dialog.deleteLater()
    app.processEvents()


def test_stock_message_box_keeps_default_buttons_and_dynamic_layout(app, dialog_hook):
    dialog = QMessageBox(QMessageBox.Icon.Question, "Replace file?", "A file already exists.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    dialog.setDefaultButton(QMessageBox.StandardButton.No)
    original_layout = dialog.layout()
    default = dialog.defaultButton()
    original_parent = default.parentWidget()
    observed = []

    def inspect_and_accept():
        assert dialog.isVisible()
        assert dialog.layout() is original_layout
        assert dialog.defaultButton() is default and default.parentWidget() is original_parent
        assert default.isDefault() and not dialog._mira_window_chrome.close_button.isDefault()
        header = dialog._mira_auto_chrome_header
        assert header.isVisible() and dialog.contentsMargins().top() >= header.height()
        dialog.setInformativeText("More information\n" * 8)
        app.processEvents()
        QTest.qWait(10)  # allow Qt's deferred child-layout metrics to update
        assert dialog.height() >= dialog.sizeHint().height()
        assert default.mapTo(dialog, default.rect().topLeft()).y() >= header.height()
        observed.append(True)
        dialog.button(QMessageBox.StandardButton.Yes).click()

    assert _inspect_modal(dialog, inspect_and_accept) == QMessageBox.StandardButton.Yes
    assert observed == [True]
    dialog.deleteLater()
    app.processEvents()


def test_dialog_hook_skips_popup_embedded_chooser_and_explicit_header(app, dialog_hook):
    explicit = QDialog()
    chrome = install_chrome(explicit, minimizable=False, maximizable=False)
    explicit.ensurePolished()
    assert explicit._mira_window_chrome is chrome
    assert not hasattr(explicit, "_mira_auto_chrome_header")
    popup = QDialog(None, Qt.WindowType.Popup)
    popup.ensurePolished()
    assert not hasattr(popup, "_mira_window_chrome")
    parent = QDialog()
    class EmbeddedChooser(QFileDialog):
        _mira_skip_auto_chrome = True
    chooser = EmbeddedChooser(parent)
    chooser.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    chooser.setWindowFlags(Qt.WindowType.Widget)
    chooser.ensurePolished()
    assert not chooser.isWindow() and not hasattr(chooser, "_mira_window_chrome")
    for widget in (explicit, popup, parent):
        widget.deleteLater()
    app.processEvents()


@pytest.mark.skipif(sys.platform != "win32", reason="Actual Win32 native message verification")
def test_actual_windows_frame_resize_minimize_maximize_restore_altf4_and_exit(tmp_path):
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "windows"
    environment["PYTHONIOENCODING"] = "utf-8"
    project = Path(__file__).resolve().parents[1]
    environment["PYTHONPATH"] = str(project) + os.pathsep + environment.get("PYTHONPATH", "")
    output = tmp_path / "native-window-chrome.json"
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--native-chrome-smoke", str(output)],
                            cwd=project, env=environment, capture_output=True, timeout=25,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, (result.stdout + result.stderr).decode("utf-8", errors="replace")
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["passed"], data
    assert data["platform"] == "windows" and data["native"]["enabled"]
    assert not data["native"]["caption_present"]
    assert data["native"]["counts"]["hit_test"] >= 5
    assert all(data["checks"].values()), data


def _native_smoke(output: str) -> int:
    """Own short-lived visible window; never sends input to another process."""
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app, "dark")
    set_language("en")
    install_dialog_chrome_hook(app)
    result = {"passed": False, "platform": app.platformName(), "checks": {}, "errors": []}

    class Window(QWidget):
        def closeEvent(self, event):
            result["checks"]["native_close_event"] = True
            event.accept()

    window = Window()
    window.setMinimumSize(360, 220)
    window.resize(620, 380)
    outer = QVBoxLayout(window)
    header = QWidget()
    row = QHBoxLayout(header)
    row.addWidget(QLabel("Mira native chrome QA"), 1)
    chrome = install_chrome(window)
    row.addWidget(chrome.controls)
    outer.addWidget(header)
    outer.addWidget(QLabel("Only this temporary window is tested."), 1)
    chrome.set_drag_area(header)
    window.show()
    user = chrome._windows.api
    user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    user.SendMessageW.restype = ctypes.c_ssize_t
    user.PostMessageW.argtypes = user.SendMessageW.argtypes
    user.PostMessageW.restype = wintypes.BOOL

    def check(name, value):
        result["checks"][name] = bool(value)
        if not value:
            raise AssertionError(name)

    def safe(function):
        def run():
            try:
                function()
            except Exception as exc:
                result["errors"].append(type(exc).__name__ + ": " + str(exc))
                window.hide()
                app.quit()
        return run

    def inspect():
        native = chrome.native_diagnostics()
        check("no_standard_caption", not native["caption_present"])
        check("full_client_without_frame_insets", native["client_rect"] == native["window_rect"])
        check("normal_corner_policy", native["corner_backend"] == "region" or native["corner_preference"] == DWMWCP_ROUND)
        check("native_style_actions", native["thick_frame"] and native["minimize_box"] and native["maximize_box"])
        rect = native["window_rect"]
        left, top, right, bottom = rect
        for name, point, expected in (
            ("native_resize_top_left", (left + 1, top + 1), HTTOPLEFT),
            ("native_resize_top_right", (right - 2, top + 1), HTTOPRIGHT),
            ("native_resize_bottom_left", (left + 1, bottom - 2), HTBOTTOMLEFT),
            ("native_resize_bottom_right", (right - 2, bottom - 2), HTBOTTOMRIGHT),
            ("native_client_center", ((left + right) // 2, (top + bottom) // 2), HTCLIENT),
        ):
            x, y = point
            packed = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
            check(name, user.SendMessageW(chrome._hwnd, 0x0084, 0, packed) == expected)
        result["normal_rect"] = rect
        chrome.maximize_button.click()
        QTimer.singleShot(200, safe(inspect_maximized))

    def inspect_maximized():
        native = chrome.native_diagnostics()
        check("maximize_state", window.isMaximized())
        check("maximize_square", native["corner_backend"] == "region" or native["corner_preference"] == DWMWCP_DONOTROUND)
        check("maximize_respects_work_area", all(abs(a - b) <= 1 for a, b in zip(native["window_rect"], native["work_area"])))
        chrome.maximize_button.click()
        QTimer.singleShot(200, safe(inspect_restored))

    def inspect_restored():
        native = chrome.native_diagnostics()
        check("restore_state", not window.isMaximized())
        check("restore_preserves_geometry", all(abs(a - b) <= 1 for a, b in zip(native["window_rect"], result["normal_rect"])))
        input_dialog = QInputDialog(window)
        input_dialog.setWindowTitle("Create folder")
        input_dialog.setLabelText("Folder name")
        input_dialog.setTextValue("local-only QA")

        def close_input():
            details = input_dialog._mira_window_chrome.native_diagnostics()
            result["stock_input_native"] = details
            check("stock_input_no_caption", details["window_exists"] and not details["caption_present"])
            check("stock_input_close_only", not details["minimize_box"] and not details["maximize_box"])
            check("stock_input_full_client", details["client_rect"] == details["window_rect"])
            rect = details["window_rect"]
            point = ((rect[1] + 1) & 0xFFFF) << 16 | ((rect[0] + 1) & 0xFFFF)
            check("stock_input_resize_hit_disabled", user.SendMessageW(input_dialog._mira_window_chrome._hwnd, 0x0084, 0, point) == HTCLIENT)
            user.SendMessageW(input_dialog._mira_window_chrome._hwnd, 0x0112, 0xF000, 0)
            check("stock_input_system_resize_disabled", details["window_rect"] == input_dialog._mira_window_chrome.native_diagnostics()["window_rect"])
            user.SendMessageW(input_dialog._mira_window_chrome._hwnd, 0x0112, 0xF030, 0)
            check("stock_input_system_maximize_disabled", not input_dialog.isMaximized() and
                  details["window_rect"] == input_dialog._mira_window_chrome.native_diagnostics()["window_rect"])
            check("stock_input_value_preserved", input_dialog.textValue() == "local-only QA")
            input_dialog._mira_window_chrome.close_button.click()
        check("stock_input_close_rejects", _inspect_modal(input_dialog, close_input) == QDialog.DialogCode.Rejected)
        message = QMessageBox(QMessageBox.Icon.Question, "Replace file?", "Local QA only.",
                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, window)
        message.setDefaultButton(QMessageBox.StandardButton.No)
        default = message.defaultButton()

        def accept_message():
            details = message._mira_window_chrome.native_diagnostics()
            result["stock_message_native"] = details
            check("stock_message_no_caption", details["window_exists"] and not details["caption_present"])
            check("stock_message_default_preserved", message.defaultButton() is default and default.isDefault())
            message.button(QMessageBox.StandardButton.Yes).click()
        check("stock_message_result_preserved", _inspect_modal(message, accept_message) == QMessageBox.StandardButton.Yes)
        input_dialog.deleteLater()
        message.deleteLater()
        chrome.minimize_button.click()
        QTimer.singleShot(200, safe(inspect_minimized))

    def inspect_minimized():
        check("minimize_state", window.isMinimized())
        window.showNormal()
        QTimer.singleShot(150, safe(close_native))

    def close_native():
        result["native"] = chrome.native_diagnostics()
        # This is the same SC_CLOSE route produced by Alt+F4, scoped to own HWND.
        check("native_alt_f4_route_posted", user.PostMessageW(chrome._hwnd, 0x0112, 0xF060, 0))
        QTimer.singleShot(150, safe(finish))

    def finish():
        check("native_close_hid_window", not window.isVisible())
        check("native_close_event", result["checks"].get("native_close_event"))
        result["passed"] = True
        app.quit()

    QTimer.singleShot(200, safe(inspect))
    QTimer.singleShot(12000, safe(lambda: (_ for _ in ()).throw(TimeoutError("Native chrome probe timed out."))))
    app.exec()
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    window.deleteLater()
    app.processEvents()
    return 0 if result["passed"] and not result["errors"] else 1


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--native-chrome-smoke":
    raise SystemExit(_native_smoke(sys.argv[2]))
