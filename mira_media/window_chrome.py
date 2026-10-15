"""Integrated native window controls, drag regions and Windows resize edges.

Only the calling window is changed. Call before showing it, insert ``controls``
in its existing header, and designate that header with ``set_drag_area``.
Popup calendars, child widgets and website contents are not modified.

Win32 message/coordinate rules:
https://learn.microsoft.com/windows/win32/inputdev/wm-nchittest
https://learn.microsoft.com/windows/win32/api/winuser/ns-winuser-minmaxinfo
System dragging deliberately uses QWindow.startSystemMove, retaining OS snap:
https://doc.qt.io/qt-6/qwindow.html#startSystemMove
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import re
import sys
import weakref

from PySide6.QtCore import QAbstractNativeEventFilter, QEvent, QObject, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractSlider, QAbstractSpinBox,
    QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QMenuBar,
    QPlainTextEdit, QPushButton, QTabBar, QTextEdit, QWidget,
)
import shiboken6

from .localization import tr
from .themes import colors


WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_GETMINMAXINFO = 0x0024
WM_SYSCOMMAND = 0x0112
HTCLIENT, HTLEFT, HTRIGHT, HTTOP = 1, 10, 11, 12
HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 15, 16, 17
SC_MINIMIZE, SC_MAXIMIZE = 0xF020, 0xF030
WS_CAPTION, WS_THICKFRAME = 0x00C00000, 0x00040000
WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_SYSMENU = 0x00020000, 0x00010000, 0x00080000


class _MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT),
                ("lPrivate", wintypes.DWORD)]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [(name, wintypes.POINT) for name in
                ("ptReserved", "ptMaxSize", "ptMaxPosition", "ptMinTrackSize", "ptMaxTrackSize")]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def _edge_hit_test(rect: tuple[int, int, int, int], x: int, y: int,
                   border_x: int, border_y: int) -> int:
    left, top, right, bottom = rect
    if not (left <= x < right and top <= y < bottom):
        return HTCLIENT
    on_left, on_right = x < left + border_x, x >= right - border_x
    on_top, on_bottom = y < top + border_y, y >= bottom - border_y
    if on_top:
        return HTTOPLEFT if on_left else HTTOPRIGHT if on_right else HTTOP
    if on_bottom:
        return HTBOTTOMLEFT if on_left else HTBOTTOMRIGHT if on_right else HTBOTTOM
    return HTLEFT if on_left else HTRIGHT if on_right else HTCLIENT


def _maximized_geometry(monitor: tuple[int, int, int, int],
                        work: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Return physical max-position/max-size relative to the chosen monitor."""
    return work[0] - monitor[0], work[1] - monitor[1], work[2] - work[0], work[3] - work[1]


class _Windows:
    def __init__(self):
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.api.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.api.GetWindowRect.restype = wintypes.BOOL
        self.api.IsWindow.argtypes = [wintypes.HWND]
        self.api.IsWindow.restype = wintypes.BOOL
        self.api.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.GetWindowLongW.restype = wintypes.LONG
        self.api.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
        self.api.SetWindowLongW.restype = wintypes.LONG
        self.api.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.api.SetWindowPos.restype = wintypes.BOOL
        self.api.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        self.api.MonitorFromWindow.restype = wintypes.HMONITOR
        self.api.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
        self.api.GetMonitorInfoW.restype = wintypes.BOOL
        self.api.GetDpiForWindow.argtypes = [wintypes.HWND]
        self.api.GetDpiForWindow.restype = wintypes.UINT
        self.api.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
        self.api.GetSystemMetricsForDpi.restype = ctypes.c_int

    def rect(self, hwnd: int) -> tuple[int, int, int, int] | None:
        rect = wintypes.RECT()
        if self.api.GetWindowRect(hwnd, ctypes.byref(rect)):
            return rect.left, rect.top, rect.right, rect.bottom
        return None

    def monitor(self, hwnd: int):
        monitor = self.api.MonitorFromWindow(hwnd, 2)  # nearest monitor
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if monitor and self.api.GetMonitorInfoW(monitor, ctypes.byref(info)):
            r, w = info.rcMonitor, info.rcWork
            return (r.left, r.top, r.right, r.bottom), (w.left, w.top, w.right, w.bottom)
        return None

    def dpi(self, hwnd: int) -> int:
        return int(self.api.GetDpiForWindow(hwnd)) or 96

    def borders(self, hwnd: int) -> tuple[int, int]:
        dpi = self.dpi(hwnd)
        padding = self.api.GetSystemMetricsForDpi(92, dpi)  # SM_CXPADDEDBORDER
        return (max(4, self.api.GetSystemMetricsForDpi(32, dpi) + padding),
                max(4, self.api.GetSystemMetricsForDpi(33, dpi) + padding))


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = weakref.ref(owner)

    def nativeEventFilter(self, event_type, message):
        owner = self.owner()
        if owner is None or not shiboken6.isValid(owner) or bytes(event_type) != b"windows_generic_MSG":
            return False, 0
        try:
            msg = _MSG.from_address(int(message))
            if int(msg.hwnd or 0) != owner._hwnd:
                return False, 0
            return owner._native_message(msg)
        except (ValueError, TypeError, RuntimeError, OSError):
            # Let Qt handle a message if its window is being destroyed/recreated.
            return False, 0


class _ChromeButton(QPushButton):
    """A real accessible button with small, theme-aware vector window marks."""
    def __init__(self, action: str, parent: QWidget):
        super().__init__(parent)
        self.action = action
        self.setObjectName("windowChromeClose" if action == "close" else "windowChromeButton")
        self.setFixedSize(40, 34)
        self.setAutoDefault(False)
        self.setDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def paintEvent(self, event):
        c = colors()
        hover, pressed = self.underMouse(), self.isDown()
        danger = self.action == "close" and (hover or pressed) and self.isEnabled()
        background = c["error"] if danger else c["pressed"] if pressed else c["hover"] if hover else None
        ink = c["accent_text"] if danger else c["text"] if self.isEnabled() else c["disabled"]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if background:
            painter.setBrush(QColor(background))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 5, 5)
        if self.hasFocus():
            painter.setPen(QPen(QColor(c["focus"]), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 5, 5)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.setPen(QPen(QColor(ink), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.action == "minimize":
            painter.drawLine(-5, 3, 5, 3)
        elif self.action == "maximize":
            painter.drawRect(QRectF(-5, -5, 10, 10))
        elif self.action == "restore":
            painter.drawLine(-2, -5, 5, -5)
            painter.drawLine(5, -5, 5, 2)
            painter.drawRect(QRectF(-5, -2, 7, 7))
        else:
            painter.drawLine(-5, -5, 5, 5)
            painter.drawLine(-5, 5, 5, -5)
        painter.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class WindowChrome(QObject):
    def __init__(self, window: QWidget, *, resizable=True, minimizable=True, maximizable=True):
        super().__init__(window)
        self._window_ref = weakref.ref(window)
        self.resizable = bool(resizable)
        self.minimizable = bool(minimizable)
        self.maximizable = bool(maximizable and resizable)
        self._drag_area = None
        self._manual_drag = None
        self._hwnd = 0
        self._syncing = False
        self._native_counts = {"hit_test": 0, "minmax": 0}
        self._windows = _Windows() if sys.platform == "win32" and QApplication.platformName() == "windows" else None
        self._native_filter = None
        self.controls = QWidget(window)
        self.controls.setObjectName("windowChromeControls")
        self.controls.setSizePolicy(self.controls.sizePolicy().Policy.Fixed, self.controls.sizePolicy().Policy.Fixed)
        row = QHBoxLayout(self.controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self.minimize_button = _ChromeButton("minimize", self.controls) if self.minimizable else None
        self.maximize_button = _ChromeButton("maximize", self.controls) if self.maximizable else None
        self.close_button = _ChromeButton("close", self.controls)
        for name in ("minimize_button", "maximize_button", "close_button"):
            button = getattr(self, name)
            setattr(self.controls, name, button)
            if button is not None:
                row.addWidget(button)
        if self.minimize_button:
            self.minimize_button.clicked.connect(window.showMinimized)
        if self.maximize_button:
            self.maximize_button.clicked.connect(self.toggle_maximized)
        # Preserve application closeEvent, QDialog rejection and async login cleanup.
        self.close_button.clicked.connect(window.close)
        window.installEventFilter(self)
        window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        window.setWindowFlag(Qt.WindowType.WindowSystemMenuHint, True)
        window.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, self.minimizable)
        window.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, self.maximizable)
        if self._windows:
            app = QApplication.instance()
            native = self._native_filter = _NativeFilter(self)
            app.installNativeEventFilter(native)
            app_ref = weakref.ref(app)

            def detach(*_):
                application = app_ref()
                if application is not None and shiboken6.isValid(application):
                    application.removeNativeEventFilter(native)
            self.destroyed.connect(detach)
            self._sync_native(create=True)
        self.refresh()

    @property
    def window(self) -> QWidget | None:
        reference = getattr(self, "_window_ref", None)
        window = reference() if reference is not None else None
        return window if window is not None and shiboken6.isValid(window) else None

    def _sync_native(self, *, create=False):
        window = self.window
        if not self._windows or window is None or self._syncing:
            return
        self._syncing = True
        try:
            # WinIdChange also occurs while Qt destroys a native surface.
            # Never resurrect that surface merely to restyle a closing dialog.
            hwnd = int(window.winId() if create else window.effectiveWinId() or 0)
            if not hwnd:
                self._hwnd = 0
                return
            self._hwnd = hwnd
            old = self._windows.api.GetWindowLongW(self._hwnd, -16) & 0xFFFFFFFF
            style = old & ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
            style |= WS_SYSMENU
            if self.resizable:
                style |= WS_THICKFRAME
            if self.minimizable:
                style |= WS_MINIMIZEBOX
            if self.maximizable:
                style |= WS_MAXIMIZEBOX
            if old != style:
                self._windows.api.SetWindowLongW(self._hwnd, -16, ctypes.c_long(style).value)
                self._windows.api.SetWindowPos(self._hwnd, None, 0, 0, 0, 0, 0x0037)
        finally:
            self._syncing = False

    def _native_message(self, msg):
        window = self.window
        if window is None:
            return False, 0
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            return True, 0  # entire body is client area, including the header
        if msg.message == WM_SYSCOMMAND:
            command = msg.wParam & 0xFFF0
            if (command == SC_MINIMIZE and not self.minimizable) or (command == SC_MAXIMIZE and not self.maximizable):
                return True, 0
        if msg.message == WM_NCHITTEST:
            self._native_counts["hit_test"] += 1
            if self.resizable and not window.isMaximized() and not window.isFullScreen():
                rect = self._windows.rect(self._hwnd)
                if rect:
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    hit = _edge_hit_test(rect, x, y, *self._windows.borders(self._hwnd))
                    if hit != HTCLIENT:
                        return True, hit
            return True, HTCLIENT
        if msg.message == WM_GETMINMAXINFO and msg.lParam:
            self._native_counts["minmax"] += 1
            monitor = self._windows.monitor(self._hwnd)
            if monitor:
                info = _MINMAXINFO.from_address(msg.lParam)
                x, y, width, height = _maximized_geometry(*monitor)
                info.ptMaxPosition.x, info.ptMaxPosition.y = x, y
                info.ptMaxSize.x, info.ptMaxSize.y = width, height
                scale = self._windows.dpi(self._hwnd) / 96
                info.ptMinTrackSize.x = max(info.ptMinTrackSize.x, round(window.minimumWidth() * scale))
                info.ptMinTrackSize.y = max(info.ptMinTrackSize.y, round(window.minimumHeight() * scale))
                if window.maximumWidth() < 16777215:
                    info.ptMaxTrackSize.x = round(window.maximumWidth() * scale)
                if window.maximumHeight() < 16777215:
                    info.ptMaxTrackSize.y = round(window.maximumHeight() * scale)
                return True, 0
        return False, 0

    def native_diagnostics(self) -> dict:
        """Non-sensitive native facts for release smoke checks; no user input."""
        result = {"enabled": bool(self._windows), "counts": dict(self._native_counts),
                  "resizable": self.resizable, "minimizable": self.minimizable,
                  "maximizable": self.maximizable}
        result["window_exists"] = bool(self._windows and self._hwnd and self._windows.api.IsWindow(self._hwnd))
        if result["window_exists"]:
            style = self._windows.api.GetWindowLongW(self._hwnd, -16) & 0xFFFFFFFF
            monitor = self._windows.monitor(self._hwnd)
            result.update({"caption_present": bool(style & WS_CAPTION),
                           "thick_frame": bool(style & WS_THICKFRAME),
                           "minimize_box": bool(style & WS_MINIMIZEBOX),
                           "maximize_box": bool(style & WS_MAXIMIZEBOX),
                           "window_rect": self._windows.rect(self._hwnd),
                           "monitor_rect": monitor[0] if monitor else None,
                           "work_area": monitor[1] if monitor else None,
                           "border_pixels": self._windows.borders(self._hwnd),
                           "dpi": self._windows.dpi(self._hwnd)})
        return result

    def refresh(self):
        window = self.window
        if window is None:
            return
        for button, source in ((self.minimize_button, "Свернуть"), (self.close_button, "Закрыть")):
            if button is not None:
                button.setToolTip(tr(source))
                button.setAccessibleName(tr(source))
                button.update()
        if self.maximize_button:
            source = "Восстановить" if window.isMaximized() else "Развернуть"
            self.maximize_button.action = "restore" if window.isMaximized() else "maximize"
            self.maximize_button.setToolTip(tr(source))
            self.maximize_button.setAccessibleName(tr(source))
            self.maximize_button.update()

    def toggle_maximized(self):
        window = self.window
        if window is not None and self.maximizable:
            window.showNormal() if window.isMaximized() else window.showMaximized()
            self.refresh()

    def set_drag_area(self, widget: QWidget):
        window = self.window
        if window is None or (widget is not window and not window.isAncestorOf(widget)):
            raise ValueError("Drag area must belong to this window.")
        self._drag_area = weakref.ref(widget)
        self._watch_drag_widget(widget)

    def _watch_drag_widget(self, widget):
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget):
            child.installEventFilter(self)

    def _is_drag_target(self, widget) -> bool:
        area = self._drag_area() if self._drag_area else None
        if area is None or not isinstance(widget, QWidget) or not shiboken6.isValid(area):
            return False
        interactive = (QAbstractButton, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
                       QAbstractSpinBox, QAbstractItemView, QAbstractSlider, QMenu, QMenuBar, QTabBar)
        current = widget
        while current is not None:
            if isinstance(current, interactive):
                return False
            if isinstance(current, QLabel):
                flags = current.textInteractionFlags()
                selectable = (Qt.TextInteractionFlag.TextSelectableByMouse |
                              Qt.TextInteractionFlag.TextSelectableByKeyboard |
                              Qt.TextInteractionFlag.TextEditable)
                links = Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
                # Ordinary QLabel defaults permit links even for plain titles.
                # Only an actual anchor or selectable text is interactive here.
                if flags & selectable or (flags & links and re.search(r"<a\b", current.text(), re.IGNORECASE)):
                    return False
            if current is area:
                return True
            current = current.parentWidget()
        return False

    def _start_system_move(self) -> bool:
        window = self.window
        handle = window.windowHandle() if window is not None else None
        return bool(handle is not None and handle.startSystemMove())

    def eventFilter(self, watched, event):
        window = self.window
        if window is None:
            return False
        kind = event.type()
        if watched is window:
            if kind in (QEvent.Type.Show, QEvent.Type.WinIdChange):
                self._sync_native()
            if kind in (QEvent.Type.WindowStateChange, QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
                self.refresh()
        if kind == QEvent.Type.ChildAdded and self._is_drag_target(watched):
            child = event.child()
            if isinstance(child, QWidget):
                self._watch_drag_widget(child)
        if not self._is_drag_target(watched):
            return False
        if kind == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            if self.maximizable:
                self.toggle_maximized()
                return True
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._manual_drag = None
            if not self._start_system_move():
                self._manual_drag = (event.globalPosition().toPoint(), window.pos())
            return True
        if kind == QEvent.Type.MouseMove and self._manual_drag and event.buttons() & Qt.MouseButton.LeftButton:
            origin, position = self._manual_drag
            window.move(position + event.globalPosition().toPoint() - origin)
            return True
        if kind == QEvent.Type.MouseButtonRelease:
            self._manual_drag = None
        return False


def install_chrome(window: QWidget, *, resizable=True, minimizable=True, maximizable=True) -> WindowChrome:
    """Install once before show; consumers keep their existing header/layout."""
    if not isinstance(QApplication.instance(), QApplication):
        raise RuntimeError("Create QApplication before installing window chrome.")
    if not isinstance(window, QWidget) or not window.isWindow():
        raise ValueError("Window chrome requires a top-level QWidget or QDialog.")
    existing = getattr(window, "_mira_window_chrome", None)
    if existing is not None and shiboken6.isValid(existing):
        return existing
    result = WindowChrome(window, resizable=resizable, minimizable=minimizable, maximizable=maximizable)
    window._mira_window_chrome = result
    return result


class _DialogChromeHook(QObject):
    """Give stock Qt prompts a header without replacing their existing layout."""
    _HEADER_HEIGHT = 42

    def __init__(self, application):
        super().__init__(application)
        self._alive = True
        application.installEventFilter(self)

    def _position_header(self, dialog):
        header = getattr(dialog, "_mira_auto_chrome_header", None)
        margins = getattr(dialog, "_mira_auto_chrome_original_margins", None)
        if header is not None and margins is not None and shiboken6.isValid(header):
            left, top, right, _ = margins
            header.setGeometry(left, top, max(0, dialog.width() - left - right), self._HEADER_HEIGHT)
            header.raise_()

    def _fit_dialog(self, dialog):
        if (not hasattr(dialog, "_mira_auto_chrome_header") or
                getattr(dialog, "_mira_auto_chrome_fitting", False)):
            return
        dialog._mira_auto_chrome_fitting = True
        try:
            hint = dialog.sizeHint()
            if hint.isValid():
                needed = dialog.size().expandedTo(hint)
                # QMessageBox can set its own fixed size using content metrics
                # before our extra header margin is included. Expand its limit
                # as well; retain the same stock layout and button identities.
                if dialog.maximumSize().width() < needed.width() or dialog.maximumSize().height() < needed.height():
                    dialog.setMaximumSize(dialog.maximumSize().expandedTo(needed))
                if dialog.size() != needed:
                    dialog.resize(needed)
        finally:
            dialog._mira_auto_chrome_fitting = False

    def _schedule_fit(self, dialog):
        if not hasattr(dialog, "_mira_auto_chrome_header"):
            return
        timer = getattr(dialog, "_mira_auto_chrome_fit_timer", None)
        if timer is None:
            timer = QTimer(dialog)
            timer.setSingleShot(True)
            owner_ref, dialog_ref = weakref.ref(self), weakref.ref(dialog)

            def fit():
                owner, target = owner_ref(), dialog_ref()
                if (owner is not None and target is not None and
                        shiboken6.isValid(owner) and shiboken6.isValid(target) and target.isVisible()):
                    owner._fit_dialog(target)
                    owner._position_header(target)
            timer.timeout.connect(fit)
            dialog._mira_auto_chrome_fit_timer = timer
        # Qt updates stock QMessageBox child layout metrics after delivery of
        # LayoutRequest; fit once on the next turn using an owned, cancellable
        # timer rather than a callback retaining a destroyed native dialog.
        timer.start(0)

    def _prepare(self, dialog):
        if (not dialog.isWindow() or dialog.windowType() == Qt.WindowType.Popup or dialog.isVisible()
                or getattr(dialog, "_mira_skip_auto_chrome", False)
                or getattr(dialog, "_mira_window_chrome", None) is not None
                or getattr(dialog, "_mira_auto_chrome_preparing", False)):
            return
        dialog._mira_auto_chrome_preparing = True
        # Preserve every stock layout/model/widget/default button. The reserved
        # top contents margin increases the existing layout's own sizeHint.
        margins = dialog.contentsMargins()
        original = margins.left(), margins.top(), margins.right(), margins.bottom()
        old_size = dialog.size()
        explicitly_resized = dialog.testAttribute(Qt.WidgetAttribute.WA_Resized)
        chrome = install_chrome(dialog, resizable=False, minimizable=False, maximizable=False)
        header = QWidget(dialog)
        header.setObjectName("automaticDialogHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(10, 2, 4, 2)
        row.setSpacing(8)
        title = QLabel(dialog.windowTitle(), header)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setObjectName("section")
        row.addWidget(title, 1)
        row.addWidget(chrome.controls)
        dialog.windowTitleChanged.connect(title.setText)
        dialog._mira_auto_chrome_header = header
        dialog._mira_auto_chrome_original_margins = original
        dialog.setContentsMargins(original[0], original[1] + self._HEADER_HEIGHT, original[2], original[3])
        chrome.set_drag_area(header)
        if explicitly_resized:
            dialog.resize(old_size.width(), old_size.height() + self._HEADER_HEIGHT)
        dialog.updateGeometry()
        if dialog.layout() is not None:
            dialog.layout().activate()
        self._fit_dialog(dialog)
        self._position_header(dialog)
        dialog._mira_auto_chrome_preparing = False

    def eventFilter(self, watched, event):
        if not getattr(self, "_alive", False) or not isinstance(watched, QDialog):
            return False
        kind = event.type()
        # Polish precedes native show/exec. Changing window flags on Show could
        # hide a modal and cause exec() to return before its buttons are used.
        if kind == QEvent.Type.Polish:
            self._prepare(watched)
        elif kind in (QEvent.Type.Resize, QEvent.Type.LayoutRequest, QEvent.Type.Show):
            self._fit_dialog(watched)
            self._position_header(watched)
            if kind == QEvent.Type.LayoutRequest:
                self._schedule_fit(watched)
        elif kind in (QEvent.Type.Hide, QEvent.Type.Close):
            timer = getattr(watched, "_mira_auto_chrome_fit_timer", None)
            if timer is not None:
                timer.stop()
        return False


def install_dialog_chrome_hook(application: QApplication) -> QObject:
    """Install once before constructing dialogs, including stock Qt prompts.

    Explicitly integrated windows keep their own header. Existing visible
    dialogs, Qt.Popup calendars and embedded Qt.Widget choosers are untouched.
    An intentionally embedded dialog may set class attribute
    ``_mira_skip_auto_chrome = True`` before its Qt base constructor runs.
    No form field, web page, dialog button or original layout is read/reparented.
    """
    if not isinstance(application, QApplication) or application is not QApplication.instance():
        raise RuntimeError("Use the active QApplication for the dialog chrome hook.")
    from .modal_backdrop import install_modal_backdrop_hook
    install_modal_backdrop_hook(application)
    existing = getattr(application, "_mira_dialog_chrome_hook", None)
    if existing is not None and shiboken6.isValid(existing):
        return existing
    result = _DialogChromeHook(application)
    application._mira_dialog_chrome_hook = result
    return result
