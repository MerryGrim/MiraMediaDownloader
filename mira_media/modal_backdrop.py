"""Centered native dialogs with temporary, memory-only owner backdrops.

Only real QDialog windows participate. Anchored Qt.Popup menus, calendars and
combo lists retain their placement and behavior. The live owner receives no
graphics effect: a single blurred snapshot covers it until its last dialog
closes, while nested dialogs keep independent owner snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import weakref

import shiboken6
from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QGraphicsBlurEffect, QGraphicsScene, QWidget


def _valid(widget) -> bool:
    return widget is not None and shiboken6.isValid(widget)


def _blurred_pixmap(source: QPixmap) -> QPixmap:
    if source.isNull():
        return source
    scene = QGraphicsScene()
    item = scene.addPixmap(source)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(14)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    bounds = item.boundingRect()
    scene.setSceneRect(bounds)
    result = QPixmap(source.size())
    result.setDevicePixelRatio(source.devicePixelRatio())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    scene.render(painter, QRectF(0, 0, bounds.width(), bounds.height()), bounds)
    painter.end()
    scene.clear()
    return result


class _Backdrop(QWidget):
    def __init__(self, owner: QWidget, focus_dialog):
        super().__init__(owner)
        self.setObjectName("miraModalBackdrop")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._focus_dialog = focus_dialog
        self._pixmap = QPixmap()
        self._palette_key = ""
        self.capture_count = 0
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        owner = self.parentWidget()
        if not _valid(owner):
            return
        visible = self.isVisible()
        self.hide()
        self._pixmap = _blurred_pixmap(owner.grab())
        self.capture_count += 1
        self._palette_key = owner.palette().color(QPalette.ColorRole.Window).name()
        self.setGeometry(owner.rect())
        if visible:
            self.show()
            self.raise_()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if not self._pixmap.isNull():
            painter.drawPixmap(self.rect(), self._pixmap)
        dark = self.parentWidget().palette().color(QPalette.ColorRole.Window).lightness() < 128
        painter.fillRect(self.rect(), QColor(0, 0, 0, 76 if dark else 54))
        painter.end()

    def mousePressEvent(self, event) -> None:
        self._focus_dialog()
        event.accept()

    def release_snapshot(self) -> None:
        self.hide()
        self._pixmap = QPixmap()
        self.deleteLater()


@dataclass
class _Dialog:
    widget: weakref.ReferenceType
    owner: weakref.ReferenceType | None


@dataclass
class _Owner:
    widget: weakref.ReferenceType
    overlay: _Backdrop
    dialogs: list[int] = field(default_factory=list)


class _ModalBackdropHook(QObject):
    def __init__(self, application: QApplication):
        super().__init__(application)
        self._dialogs: dict[int, _Dialog] = {}
        self._owners: dict[int, _Owner] = {}
        self._pending: set[int] = set()
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._flush_layout)
        application.installEventFilter(self)

    @staticmethod
    def _is_dialog(widget) -> bool:
        return (isinstance(widget, QDialog) and widget.isWindow()
                and widget.windowType() not in {Qt.WindowType.Popup, Qt.WindowType.ToolTip})

    @staticmethod
    def _nearest_owner(dialog):
        parent = dialog.parentWidget()
        while _valid(parent):
            candidate = parent.window()
            if candidate is not dialog and candidate.isVisible() and not candidate.isMinimized():
                return candidate
            parent = parent.parentWidget()
        return None

    def _focus_owner_dialog(self, owner_key: int) -> None:
        owner = self._owners.get(owner_key)
        if owner:
            for key in reversed(owner.dialogs):
                entry = self._dialogs.get(key)
                dialog = entry.widget() if entry else None
                if _valid(dialog) and dialog.isVisible():
                    dialog.raise_()
                    dialog.activateWindow()
                    break

    def _attach(self, dialog) -> None:
        key = id(dialog)
        if key in self._dialogs:
            self._queue_layout(key)
            return
        owner = self._nearest_owner(dialog)
        self._dialogs[key] = _Dialog(weakref.ref(dialog), weakref.ref(owner) if owner is not None else None)
        if not getattr(dialog, "_mira_modal_dialog_destroy_watch", False):
            dialog.destroyed.connect(lambda _object=None, key=key: self._remove(key))
            dialog._mira_modal_dialog_destroy_watch = True
        dialog._mira_modal_owner = owner
        if owner is not None:
            self._add_owner_dialog(owner, key)
        self._center(key)
        self._queue_layout(key)

    def _add_owner_dialog(self, owner, key) -> None:
        owner_key = id(owner)
        if owner_key not in self._owners:
            overlay = _Backdrop(owner, lambda owner_key=owner_key: self._focus_owner_dialog(owner_key))
            self._owners[owner_key] = _Owner(weakref.ref(owner), overlay)
            owner._mira_modal_backdrop = overlay
            if not getattr(owner, "_mira_modal_owner_destroy_watch", False):
                owner.destroyed.connect(lambda _object=None, owner_key=owner_key: self._owner_destroyed(owner_key))
                owner._mira_modal_owner_destroy_watch = True
            overlay.show()
            overlay.raise_()
        self._owners[owner_key].dialogs.append(key)

    def _detach_owner_dialog(self, owner, key) -> None:
        if owner is None:
            return
        owner_key = id(owner)
        record = self._owners.get(owner_key)
        if record is None:
            return
        record.dialogs = [value for value in record.dialogs if value != key]
        if not record.dialogs:
            self._owners.pop(owner_key, None)
            if _valid(owner):
                owner._mira_modal_backdrop = None
            if _valid(record.overlay):
                record.overlay.release_snapshot()

    def _remove(self, key: int) -> None:
        record = self._dialogs.pop(key, None)
        self._pending.discard(key)
        if record:
            dialog = record.widget()
            if _valid(dialog):
                dialog._mira_modal_owner = None
            self._detach_owner_dialog(record.owner() if record.owner else None, key)

    def _owner_destroyed(self, owner_key: int) -> None:
        record = self._owners.pop(owner_key, None)
        if record:
            for key in record.dialogs:
                entry = self._dialogs.get(key)
                if entry:
                    entry.owner = None

    def _retarget_children(self, hidden_owner) -> None:
        for key, record in list(self._dialogs.items()):
            if record.owner is None or record.owner() is not hidden_owner:
                continue
            dialog = record.widget()
            if not _valid(dialog) or not dialog.isVisible():
                self._remove(key)
                continue
            self._detach_owner_dialog(hidden_owner, key)
            owner = self._nearest_owner(dialog)
            record.owner = weakref.ref(owner) if owner is not None else None
            dialog._mira_modal_owner = owner
            if owner is not None:
                self._add_owner_dialog(owner, key)
            self._queue_layout(key)

    def _queue_layout(self, key) -> None:
        self._pending.add(key)
        if not self._layout_timer.isActive():
            self._layout_timer.start(0)

    def _center(self, key) -> None:
        record = self._dialogs.get(key)
        dialog = record.widget() if record else None
        if not _valid(dialog) or not dialog.isVisible():
            return
        owner = record.owner() if record.owner else None
        geometry = owner.frameGeometry() if _valid(owner) and owner.isVisible() else None
        screen = QGuiApplication.screenAt(geometry.center()) if geometry is not None else dialog.screen()
        screen = screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        center = geometry.center() if geometry is not None else available.center()
        frame = dialog.frameGeometry()
        x = max(available.left(), min(center.x() - frame.width() // 2,
                                     available.right() - frame.width() + 1))
        y = max(available.top(), min(center.y() - frame.height() // 2,
                                    available.bottom() - frame.height() + 1))
        delta = QPoint(x, y) - frame.topLeft()
        if not delta.isNull():
            dialog.move(dialog.pos() + delta)

    def _flush_layout(self) -> None:
        pending, self._pending = self._pending, set()
        for key in pending:
            self._center(key)
        for record in list(self._owners.values()):
            owner = record.widget()
            overlay = record.overlay
            if _valid(owner) and _valid(overlay):
                if overlay._palette_key != owner.palette().color(QPalette.ColorRole.Window).name():
                    overlay.refresh_snapshot()

    def eventFilter(self, watched, event):
        if not isinstance(watched, QWidget):
            return False
        kind = event.type()
        key = id(watched)
        if self._is_dialog(watched):
            if kind == QEvent.Type.Show:
                self._attach(watched)
            elif kind == QEvent.Type.Hide:
                self._remove(key)
                self._retarget_children(watched)
            elif kind in {QEvent.Type.Resize, QEvent.Type.LayoutRequest} and key in self._dialogs:
                self._queue_layout(key)
        owner = self._owners.get(key)
        if owner:
            if kind in {QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.PaletteChange, QEvent.Type.Show}:
                if _valid(owner.overlay):
                    owner.overlay.setGeometry(watched.rect())
                    if kind == QEvent.Type.Show:
                        owner.overlay.show()
                        owner.overlay.raise_()
                for child in owner.dialogs:
                    self._queue_layout(child)
            elif kind == QEvent.Type.Hide and _valid(owner.overlay):
                owner.overlay.hide()
        return False


def install_modal_backdrop_hook(application: QApplication) -> QObject:
    """Install once before dialogs are shown; snapshots never leave RAM."""
    if not isinstance(application, QApplication) or application is not QApplication.instance():
        raise RuntimeError("Use the active QApplication for modal backdrops.")
    existing = getattr(application, "_mira_modal_backdrop_hook", None)
    if _valid(existing):
        return existing
    result = _ModalBackdropHook(application)
    application._mira_modal_backdrop_hook = result
    return result
