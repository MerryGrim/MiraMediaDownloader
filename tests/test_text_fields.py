"""Actual native clear-action alignment and unchanged editing behavior."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QToolButton, QVBoxLayout, QWidget

from mira_media.text_fields import CLEAR_BUTTON_STYLESHEET
from mira_media.themes import apply_theme, get_theme


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def restore_style(app):
    previous = get_theme()
    yield
    apply_theme(app, previous)


def _field(app, *, direction=Qt.LayoutDirection.LeftToRight, text="https://x.com/NASA"):
    window = QWidget()
    layout = QVBoxLayout(window)
    field = QLineEdit(text)
    field.setLayoutDirection(direction)
    field.setMinimumWidth(360)
    field.setClearButtonEnabled(True)
    layout.addWidget(field)
    window.show()
    app.processEvents()
    return window, field, field.findChild(QToolButton)


@pytest.mark.parametrize("direction", [Qt.LayoutDirection.LeftToRight, Qt.LayoutDirection.RightToLeft])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_embedded_clear_action_is_centered_and_reserves_text_space(app, theme, direction):
    apply_theme(app, theme)
    window, field, button = _field(app, direction=direction)
    try:
        assert button is not None and button.isVisible()
        assert abs(button.geometry().center().y() - field.rect().center().y()) <= 1
        assert field.rect().contains(button.geometry())
        assert button.geometry().left() < field.width() / 2 if direction == Qt.LayoutDirection.RightToLeft else button.geometry().right() > field.width() / 2
        # Keep the same native action and re-check after live theme changes.
        action = button.defaultAction()
        assert action is not None
        apply_theme(app, "dark" if theme == "light" else "light")
        app.processEvents()
        assert button.defaultAction() is action
        assert abs(button.geometry().center().y() - field.rect().center().y()) <= 1
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_native_action_clears_editing_and_undo_keeps_qt_semantics(app):
    apply_theme(app, 'light')
    window, field, button = _field(app, text="")
    changed, edited = [], []
    field.textChanged.connect(changed.append)
    field.textEdited.connect(edited.append)
    try:
        field.setFocus()
        QTest.keyClicks(field, "profile_text")
        assert field.text() == "profile_text" and field.isUndoAvailable()
        QTest.qWait(200)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert field.text() == "" and changed[-1] == "" and edited[-1] == ""
        field.undo()
        assert field.text() == "profile_text"
        field.setReadOnly(True)
        app.processEvents()
        QTest.qWait(200)
        assert not button.isEnabled()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert field.text() == "profile_text"
        field.setReadOnly(False)
        field.setEnabled(False)
        app.processEvents()
        assert not button.isEnabled()
        field.setEnabled(True)
        field.selectAll()
        QTest.keyClicks(field, "replacement")
        assert field.text() == "replacement"
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


@pytest.mark.skipif(sys.platform != 'win32', reason='Actual Windows DPI and icon pixels')
def test_native_windows_clear_icon_pixels_are_centered_in_both_themes(tmp_path):
    environment = dict(os.environ)
    environment['QT_QPA_PLATFORM'] = 'windows'
    environment['PYTHONIOENCODING'] = 'utf-8'
    project = Path(__file__).resolve().parents[1]
    environment['PYTHONPATH'] = str(project) + os.pathsep + environment.get('PYTHONPATH', '')
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--native-text-field-smoke', str(tmp_path)],
                            env=environment, cwd=project, capture_output=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, (result.stdout + result.stderr).decode('utf-8', errors='replace')
    data = json.loads((tmp_path / 'text-fields-native.json').read_text(encoding='utf-8'))
    assert data['passed'] and data['platform'] == 'windows'
    assert set(data['themes']) == {'light', 'dark'}
    assert all(item['icon_center_error_physical_pixels'] <= 2 for item in data['themes'].values())
    assert data['unfixed_regression_detected']


def _native_smoke(output):
    from PIL import Image
    from mira_media.themes import stylesheet
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    result = {'passed': False, 'platform': app.platformName(), 'themes': {}, 'errors': []}

    def icon_ink_center(path, scale):
        with Image.open(path) as source:
            image = source.convert('RGB')
            points = []
            for y in range(round(5 * scale), image.height - round(5 * scale)):
                for x in range(image.width - round(28 * scale), image.width - round(5 * scale)):
                    r, g, b = image.getpixel((x, y))
                    if min(r, g, b) >= 95 and max(r, g, b) <= 230 and max(r, g, b) - min(r, g, b) < 18:
                        points.append((x, y))
            if not points:
                raise AssertionError('No native clear icon ink captured')
            top, bottom = min(y for x, y in points), max(y for x, y in points)
            return (top + bottom) / 2, (image.height - 1) / 2, image.size

    def inspect():
        try:
            for name in ('unfixed', 'light', 'dark'):
                theme = 'dark' if name == 'unfixed' else name
                apply_theme(app, theme)
                if name == 'unfixed':
                    # Negative control: the previous generic toolbar padding.
                    app.setStyleSheet(stylesheet(theme).replace(CLEAR_BUTTON_STYLESHEET, ''))
                window = QWidget()
                layout = QVBoxLayout(window)
                field = QLineEdit('https://x.com/NASA')
                field.setClearButtonEnabled(True)
                field.setMinimumWidth(480)
                layout.addWidget(field)
                window.show()
                app.processEvents()
                QTest.qWait(200)
                field.clearFocus()
                app.processEvents()
                target = root / (name + '-clear-field.png')
                assert field.grab().save(str(target))
                scale = field.devicePixelRatioF()
                ink_y, field_y, image_size = icon_ink_center(target, scale)
                error = abs(ink_y - field_y)
                if name == 'unfixed':
                    result['unfixed_regression_detected'] = error > 4 * scale
                else:
                    result['themes'][theme] = {'screenshot': str(target), 'image_size': list(image_size),
                                               'device_pixel_ratio': scale,
                                               'icon_center_error_physical_pixels': error}
                    assert error <= 2, (theme, error)
                window.close()
                window.deleteLater()
                app.processEvents()
            assert result.get('unfixed_regression_detected')
            result['passed'] = True
        except Exception as exc:
            result['errors'].append(type(exc).__name__ + ': ' + str(exc))
        finally:
            app.quit()

    QTimer.singleShot(0, inspect)
    app.exec()
    (root / 'text-fields-native.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--native-text-field-smoke':
    raise SystemExit(_native_smoke(sys.argv[2]))
