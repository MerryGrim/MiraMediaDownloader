"""Native palette, contrast and rendered-control theme contracts; no WebEngine."""

import os
from collections import Counter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QCalendarWidget, QComboBox, QDialog, QDoubleSpinBox,
    QLineEdit, QListWidget, QMenu, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from mira_media import themes
from mira_media.icons import action_icon


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def restore_light(app):
    yield
    themes.apply_theme(app, "light")


def luminance(color):
    value = QColor(color)
    components = [value.redF(), value.greenF(), value.blueF()]
    linear = [part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4
              for part in components]
    return sum(part * weight for part, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(first, second):
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_reading_and_action_colors_have_normal_text_contrast(theme):
    c = themes.colors(theme)
    for foreground, background in (("text", "window"), ("text", "surface"),
                                   ("text", "input"), ("muted", "surface"),
                                   ("muted", "surface_alt"), ("selection_text", "selected"),
                                   ("accent_text", "accent"), ("accent_text", "accent_hover"),
                                   ("accent_text", "accent_pressed"), ("tooltip_text", "tooltip"),
                                   ("error", "surface"), ("link", "surface")):
        assert contrast(c[foreground], c[background]) >= 4.5, (theme, foreground, background)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_application_palette_covers_active_inactive_and_disabled_widgets(app, theme):
    themes.apply_theme(app, theme)
    c = themes.colors(theme)
    palette = app.palette()
    assert themes.get_theme() == theme
    assert app.property("mira_theme") == theme
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, token in ((QPalette.ColorRole.Window, "window"),
                            (QPalette.ColorRole.Base, "input"),
                            (QPalette.ColorRole.Text, "text"),
                            (QPalette.ColorRole.Button, "surface"),
                            (QPalette.ColorRole.Highlight, "accent"),
                            (QPalette.ColorRole.HighlightedText, "accent_text")):
            assert palette.color(group, role).name() == c[token]
    disabled = QPalette.ColorGroup.Disabled
    assert palette.color(disabled, QPalette.ColorRole.Text).name() == c["disabled"]
    assert contrast(palette.color(disabled, QPalette.ColorRole.Text),
                    palette.color(disabled, QPalette.ColorRole.Base)) >= 3


def test_live_theme_switch_recolors_existing_native_inputs_buttons_and_dialog(app, tmp_path):
    dialog = QDialog()
    dialog.resize(420, 240)
    layout = QVBoxLayout(dialog)
    field = QLineEdit("Native input")
    primary = QPushButton("Download")
    primary.setObjectName("primary")
    picker = QPushButton("15.10.2026")
    picker.setObjectName("datePickerButton")
    for widget in (field, primary, picker):
        layout.addWidget(widget)
    dialog.show()
    pictures = {}
    try:
        for theme in ("light", "dark", "light"):
            themes.apply_theme(app, theme)
            app.processEvents()
            c = themes.colors(theme)
            assert field.palette().color(QPalette.ColorRole.Base).name() == c["input"]
            assert primary.palette().color(QPalette.ColorRole.Button).name() == c["accent"]
            assert primary.palette().color(QPalette.ColorRole.ButtonText).name() == c["accent_text"]
            assert picker.palette().color(QPalette.ColorRole.ButtonText).name() == c["text"]
            image = dialog.grab().toImage()
            # Inspect actual native pixels away from children, not just the QSS.
            assert image.pixelColor(2, 2).name() == c["window"]
            button_image = primary.grab().toImage()
            assert button_image.pixelColor(12, 12).name() == c["accent"]
            assert image.save(str(tmp_path / f"native-{theme}.png"))
            pictures[theme] = image
        assert pictures["light"].pixelColor(2, 2) != pictures["dark"].pixelColor(2, 2)
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_dark_popups_history_log_and_calendar_get_readable_native_palettes(app):
    themes.apply_theme(app, "dark")
    dialog = QDialog()
    dialog.setObjectName("dateCalendarPopup")
    layout = QVBoxLayout(dialog)
    combo = QComboBox()
    combo.addItems(["Русский", "English", "简体中文"])
    interval = QDoubleSpinBox()
    interval.setRange(2, 60)
    interval.setValue(3)
    history = QTableWidget(1, 1)
    history.setItem(0, 0, QTableWidgetItem("History"))
    history.selectRow(0)
    log = QTextEdit("Log")
    gallery = QListWidget()
    gallery.addItem("Image")
    gallery.setCurrentRow(0)
    calendar = QCalendarWidget()
    calendar.setObjectName("dateCalendar")
    menu = QMenu(dialog)
    menu.addAction("English")
    for widget in (combo, interval, history, log, gallery, calendar):
        layout.addWidget(widget)
    dialog.show()
    try:
        app.processEvents()
        c = themes.colors()
        for widget in (combo, interval, history, log, gallery, calendar, menu):
            widget.ensurePolished()
            foreground = widget.palette().color(QPalette.ColorRole.Text)
            background = widget.palette().color(QPalette.ColorRole.Base)
            assert luminance(background) < 0.1, type(widget).__name__
            assert contrast(foreground, background) >= 4.5, type(widget).__name__
        assert history.palette().color(QPalette.ColorRole.Highlight).isValid()
        assert calendar.grab().toImage().pixelColor(2, 2).name() == c["surface"]
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def _dominant_opaque_color(icon):
    image = icon.pixmap(24, 24).toImage()
    pixels = Counter(image.pixelColor(x, y).name() for x in range(image.width())
                     for y in range(image.height()) if image.pixelColor(x, y).alpha() >= 250)
    assert pixels
    return pixels.most_common(1)[0][0]


def _assert_rendered_ink(actual, expected):
    # Premultiplied alpha rounding can move an almost opaque edge by one level.
    actual, expected = QColor(actual), QColor(expected)
    assert all(abs(a - b) <= 2 for a, b in zip(actual.getRgb()[:3], expected.getRgb()[:3]))


def test_painted_action_icons_use_current_theme_and_new_header_marks_render(app):
    for theme in ("light", "dark"):
        themes.apply_theme(app, theme)
        for name in ("calendar", "sun", "moon", "globe"):
            _assert_rendered_ink(_dominant_opaque_color(action_icon(name)), themes.colors()["muted"])
        _assert_rendered_ink(_dominant_opaque_color(action_icon("download", color=themes.colors()["accent_text"])), themes.colors()["accent_text"])


def test_invalid_theme_does_not_partially_change_application(app):
    themes.apply_theme(app, "dark")
    previous = app.palette().color(QPalette.ColorRole.Window)
    with pytest.raises(ValueError):
        themes.apply_theme(app, "neon")
    assert themes.get_theme() == "dark"
    assert app.palette().color(QPalette.ColorRole.Window) == previous
