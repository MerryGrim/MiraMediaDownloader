"""Native popup centering/blur/cleanup with generated in-memory owner content."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QVBoxLayout, QWidget

from mira_media.modal_backdrop import install_modal_backdrop_hook
from mira_media.themes import apply_theme, get_theme


class Stripes(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        for x in range(0, self.width(), 6):
            painter.fillRect(x, 0, 6, self.height(), QColor("white" if x % 12 == 0 else "black"))
        painter.end()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def windows(app):
    previous = get_theme()
    apply_theme(app, "light")
    hook = install_modal_backdrop_hook(app)
    created = []
    def create(cls=QWidget, parent=None, size=(520, 380), position=(100, 80)):
        window = cls(parent)
        window.resize(*size)
        window.move(*position)
        created.append(window)
        return window
    yield create, hook
    for window in reversed(created):
        window.hide()
        window.deleteLater()
    app.processEvents()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    apply_theme(app, previous)


def settled(app):
    app.processEvents()
    QTest.qWait(15)


def assert_centered(dialog, owner):
    actual = dialog.frameGeometry().center()
    expected = owner.frameGeometry().center()
    assert abs(actual.x() - expected.x()) <= 2
    assert abs(actual.y() - expected.y()) <= 2


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_dialog_centered_and_owner_snapshot_blurred_in_each_theme(app, windows, theme):
    create, hook = windows
    apply_theme(app, theme)
    owner = create(Stripes)
    owner.show()
    settled(app)
    dialog = create(QDialog, owner, (220, 150))
    dialog.show()
    settled(app)
    assert_centered(dialog, owner)
    overlay = owner._mira_modal_backdrop
    assert overlay.isVisible() and overlay.geometry() == owner.rect()
    assert owner.graphicsEffect() is None and dialog.graphicsEffect() is None
    assert overlay.capture_count == 1
    image = overlay._pixmap.toImage()
    ratio = image.devicePixelRatio()
    # A generated six-pixel stripe loses its original 255-level hard edge.
    left = image.pixelColor(int(242 * ratio), int(180 * ratio)).lightness()
    right = image.pixelColor(int(248 * ratio), int(180 * ratio)).lightness()
    assert abs(left - right) < 120
    dialog.reject()
    settled(app)
    assert owner._mira_modal_backdrop is None
    assert not shiboken6.isValid(overlay)


def test_nested_dialogs_restore_underlying_modal_backdrop_and_then_owner(app, windows):
    create, hook = windows
    owner = create()
    owner.show()
    first = create(QDialog, owner, (320, 240))
    first.show()
    settled(app)
    outer_overlay = owner._mira_modal_backdrop
    second = create(QDialog, first, (180, 120))
    second.show()
    settled(app)
    assert_centered(second, first)
    assert first._mira_modal_backdrop.isVisible()
    assert owner._mira_modal_backdrop is outer_overlay and outer_overlay.capture_count == 1
    second.reject()
    settled(app)
    assert first._mira_modal_backdrop is None
    assert owner._mira_modal_backdrop is outer_overlay and outer_overlay.isVisible()
    first.reject()
    settled(app)
    assert owner._mira_modal_backdrop is None


def test_peer_dialogs_share_one_snapshot_until_last_close(app, windows):
    create, hook = windows
    owner = create()
    owner.show()
    first = create(QDialog, owner, (220, 150))
    second = create(QDialog, owner, (240, 160))
    first.show()
    settled(app)
    overlay = owner._mira_modal_backdrop
    second.show()
    settled(app)
    assert owner._mira_modal_backdrop is overlay and overlay.capture_count == 1
    first.reject()
    settled(app)
    assert overlay.isVisible()
    second.reject()
    settled(app)
    assert owner._mira_modal_backdrop is None


def test_owner_resize_and_move_recenters_without_continual_snapshot_capture(app, windows):
    create, hook = windows
    owner = create()
    owner.show()
    dialog = create(QDialog, owner, (180, 120))
    dialog.show()
    settled(app)
    overlay = owner._mira_modal_backdrop
    owner.move(60, 50)
    owner.resize(580, 430)
    settled(app)
    assert_centered(dialog, owner)
    assert overlay.geometry() == owner.rect() and overlay.capture_count == 1


def test_live_theme_change_refreshes_snapshot_once_and_close_cleans_it(app, windows):
    create, hook = windows
    owner = create()
    owner.show()
    dialog = create(QDialog, owner, (200, 140))
    dialog.show()
    settled(app)
    overlay = owner._mira_modal_backdrop
    apply_theme(app, "dark")
    settled(app)
    assert overlay.capture_count == 2
    assert overlay._palette_key == owner.palette().color(QPalette.ColorRole.Window).name()
    dialog.reject()
    settled(app)
    assert owner._mira_modal_backdrop is None


def test_owner_hide_and_restore_reuses_its_existing_backdrop(app, windows):
    create, hook = windows
    owner = create()
    owner.show()
    dialog = create(QDialog, owner, (200, 140))
    dialog.show()
    settled(app)
    overlay = owner._mira_modal_backdrop
    owner.hide()
    settled(app)
    assert not overlay.isVisible()
    owner.show()
    settled(app)
    assert dialog.isVisible() and overlay.isVisible()
    assert owner._mira_modal_backdrop is overlay and overlay.capture_count == 1
    dialog.reject()
    settled(app)
    assert owner._mira_modal_backdrop is None


def test_hiding_outer_dialog_never_leaves_an_orphaned_backdrop(app, windows):
    create, hook = windows
    owner = create()
    owner.show()
    outer = create(QDialog, owner, (300, 220))
    outer.show()
    inner = create(QDialog, outer, (180, 120))
    inner.show()
    settled(app)
    outer.hide()
    settled(app)
    if inner.isVisible():
        assert inner._mira_modal_owner is owner
        assert owner._mira_modal_backdrop.isVisible()
    inner.reject()
    settled(app)
    assert owner._mira_modal_backdrop is None


def test_center_is_clamped_to_monitor_work_area(app, windows):
    create, hook = windows
    owner = create(size=(300, 240))
    screen = owner.screen().availableGeometry()
    owner.move(screen.right() - 30, screen.bottom() - 30)
    owner.show()
    dialog = create(QDialog, owner, (240, 170))
    dialog.show()
    settled(app)
    assert screen.contains(dialog.frameGeometry())


def test_ignored_close_keeps_backdrop_until_dialog_actually_hides(app, windows):
    class DeferredClose(QDialog):
        def closeEvent(self, event):
            event.ignore()
    create, hook = windows
    owner = create()
    owner.show()
    dialog = create(DeferredClose, owner, (220, 150))
    dialog.show()
    settled(app)
    dialog.close()
    settled(app)
    assert dialog.isVisible() and owner._mira_modal_backdrop.isVisible()
    dialog.reject()
    settled(app)
    assert owner._mira_modal_backdrop is None


def test_anchored_popups_and_embedded_dialog_widgets_keep_position_without_blur(app, windows):
    create, hook = windows
    owner = create()
    owner.show()
    popup = create(QDialog, owner, (80, 60))
    popup.setWindowFlags(Qt.WindowType.Popup)
    popup.move(210, 170)
    expected = popup.pos()
    popup.show()
    settled(app)
    assert (popup.pos() - expected).manhattanLength() <= 4
    assert getattr(owner, "_mira_modal_backdrop", None) is None
    popup.hide()
    embedded = create(QDialog, owner, (100, 80))
    embedded.setWindowFlags(Qt.WindowType.Widget)
    embedded.show()
    settled(app)
    assert getattr(owner, "_mira_modal_backdrop", None) is None


def test_exec_cancel_preserves_owner_input_and_restores_overlay(app, windows):
    create, hook = windows
    owner = create()
    entry = QLineEdit("fixture-only-value", owner)
    owner.show()
    dialog = create(QDialog, owner, (200, 140))
    QTimer.singleShot(30, dialog.reject)
    assert dialog.exec() == QDialog.DialogCode.Rejected
    settled(app)
    assert entry.text() == "fixture-only-value"
    assert getattr(owner, "_mira_modal_backdrop", None) is None


def test_installation_is_idempotent_and_chrome_hook_installs_it(app):
    from mira_media.window_chrome import install_dialog_chrome_hook
    first = install_modal_backdrop_hook(app)
    install_dialog_chrome_hook(app)
    assert install_modal_backdrop_hook(app) is first
