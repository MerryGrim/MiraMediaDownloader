"""Coherent light/dark colors for native Qt widgets, never website content."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from .text_fields import CLEAR_BUTTON_STYLESHEET


_current_theme = "light"
_COLORS = {
    "light": {
        "window": "#ffffff", "surface": "#ffffff", "surface_alt": "#f6f7f9",
        "input": "#ffffff", "text": "#24272c", "muted": "#626b77",
        "border": "#d8dde5", "hover": "#f0f2f5", "pressed": "#e3e7ed",
        "selected": "#e3e9f1", "selection_text": "#202731",
        "accent": "#25282d", "accent_hover": "#41464e", "accent_pressed": "#14181d",
        "accent_text": "#ffffff", "focus": "#66758a", "success": "#2f6c49",
        "error": "#a73d38", "disabled": "#747e8b", "disabled_surface": "#f1f3f5",
        "disabled_border": "#e0e4e9", "disabled_accent": "#757f8d",
        "disabled_accent_text": "#ffffff", "placeholder": "#6b7481",
        "link": "#315f97", "link_visited": "#725c94",
        "tooltip": "#30353c", "tooltip_text": "#ffffff", "scrollbar": "#c7ced8",
    },
    "dark": {
        "window": "#181b20", "surface": "#20242b", "surface_alt": "#282d35",
        "input": "#20242b", "text": "#eef1f5", "muted": "#b3bbc8",
        "border": "#47515f", "hover": "#303742", "pressed": "#394453",
        "selected": "#3b4d65", "selection_text": "#ffffff",
        "accent": "#dfe6f0", "accent_hover": "#ffffff", "accent_pressed": "#c4cfdd",
        "accent_text": "#18202b", "focus": "#93b6e5", "success": "#89cda4",
        "error": "#f3a6a0", "disabled": "#929dad", "disabled_surface": "#222730",
        "disabled_border": "#39414d", "disabled_accent": "#4b5665",
        "disabled_accent_text": "#d5dce6", "placeholder": "#a0aaba",
        "link": "#9dc4ff", "link_visited": "#c6b4ed",
        "tooltip": "#ebeff5", "tooltip_text": "#20242b", "scrollbar": "#596575",
    },
}


def _validated(theme: str | None) -> str:
    value = _current_theme if theme is None else theme
    if value not in ("light", "dark"):
        raise ValueError("Theme must be 'light' or 'dark'.")
    return value


def get_theme() -> str:
    """Return the process's active native theme; persistence belongs to the UI."""
    return _current_theme


def colors(theme: str | None = None) -> dict[str, str]:
    """Return a copy of the native color tokens for delegates and painted icons."""
    return dict(_COLORS[_validated(theme)])


def stylesheet(theme: str | None = None) -> str:
    """Build the native widget stylesheet using one coherent color set."""
    c = colors(theme)
    return f"""
QWidget {{ font-family:'Segoe UI'; font-size:10pt; color:{c['text']}; }}
QMainWindow, QDialog, QMessageBox {{ background:{c['window']}; }}
QLabel {{ background:transparent; }}
QLabel#brand {{ font-size:17pt; font-weight:700; letter-spacing:-0.5px; }}
QLabel#hero {{ font-size:19pt; font-weight:500; margin:4px 0 2px 0; letter-spacing:-0.5px; }}
QLabel#eyebrow {{ color:{c['muted']}; font-size:8pt; font-weight:600; letter-spacing:1px; }}
QLabel#title {{ font-size:15pt; font-weight:600; }}
QLabel#section, QLabel#calendarMonthLabel {{ font-size:10pt; font-weight:600; }}
QLabel#muted, QLabel#subtitle {{ color:{c['muted']}; font-size:9pt; }}
QLabel#status {{ color:{c['muted']}; font-size:9pt; padding:4px 9px; background:{c['surface_alt']}; border-radius:5px; }}
QLabel#statNumber, QLabel#statNumberPrimary {{ font-size:19pt; font-weight:600; color:{c['text']}; }}
QLabel#error {{ color:{c['error']}; }}
QLabel:disabled {{ color:{c['disabled']}; }}
QFrame#card, QFrame#dateCalendarPopup {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:8px; }}
QLineEdit, QDateEdit, QSpinBox, QDoubleSpinBox {{
    color:{c['text']}; background:{c['input']}; border:1px solid {c['border']};
    border-radius:6px; padding:6px 9px; min-height:20px;
    selection-background-color:{c['selected']}; selection-color:{c['selection_text']};
}}
QLineEdit:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color:{c['focus']}; }}
QLineEdit:disabled, QDateEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color:{c['disabled']}; background:{c['disabled_surface']}; border-color:{c['disabled_border']};
}}
QAbstractSpinBox QLineEdit {{ border:none; padding:0; margin:0; min-height:0; background:transparent; }}
QComboBox {{ color:{c['text']}; background:{c['input']}; border:1px solid {c['border']}; border-radius:7px; padding:8px 36px 8px 12px; min-height:22px; }}
QComboBox:hover {{ border-color:{c['focus']}; }}
QComboBox:on {{ border-color:{c['focus']}; background:{c['surface_alt']}; }}
QComboBox:focus {{ border-color:{c['focus']}; }}
QComboBox:disabled {{ color:{c['disabled']}; background:{c['disabled_surface']}; border-color:{c['disabled_border']}; }}
QComboBox::drop-down {{ border:none; width:32px; }}
QComboBox QAbstractItemView {{ background:{c['surface']}; color:{c['text']}; border:1px solid {c['border']}; border-radius:8px; selection-background-color:{c['selected']}; selection-color:{c['selection_text']}; padding:5px; outline:0; }}
QComboBox QAbstractItemView::item {{ min-height:28px; padding:6px 10px; border-radius:5px; }}
QComboBox QAbstractItemView::item:hover {{ background:{c['hover']}; }}
QPushButton, QToolButton {{ color:{c['text']}; background:{c['surface']}; border:1px solid {c['border']}; border-radius:6px; padding:6px 10px; min-height:18px; font-weight:500; }}
QPushButton:hover, QToolButton:hover {{ background:{c['hover']}; border-color:{c['focus']}; }}
QPushButton:pressed, QToolButton:pressed {{ background:{c['pressed']}; }}
QPushButton:focus, QToolButton:focus {{ border-color:{c['focus']}; }}
QPushButton:disabled, QToolButton:disabled {{ color:{c['disabled']}; background:{c['disabled_surface']}; border-color:{c['disabled_border']}; }}
QPushButton#primary {{ background:{c['accent']}; color:{c['accent_text']}; border-color:{c['accent']}; padding:8px 17px; font-weight:600; }}
QPushButton#primary:hover {{ background:{c['accent_hover']}; border-color:{c['accent_hover']}; }}
QPushButton#primary:pressed {{ background:{c['accent_pressed']}; border-color:{c['accent_pressed']}; }}
QPushButton#primary:focus {{ border-color:{c['focus']}; }}
QPushButton#primary:disabled {{ background:{c['disabled_accent']}; border-color:{c['disabled_accent']}; color:{c['disabled_accent_text']}; }}
QPushButton#quiet {{ color:{c['muted']}; border-color:transparent; background:transparent; }}
QPushButton#quiet:hover {{ background:{c['hover']}; color:{c['text']}; }}
QPushButton#quiet:focus {{ border-color:{c['focus']}; }}
QPushButton#platform {{ color:{c['muted']}; background:{c['surface_alt']}; border-color:{c['border']}; }}
QPushButton#platform:checked {{ color:{c['text']}; background:{c['selected']}; border-color:{c['focus']}; font-weight:600; }}
QPushButton#platform:disabled {{ color:{c['disabled']}; border-color:{c['disabled_border']}; background:{c['disabled_surface']}; }}
QPushButton#datePickerButton {{ padding:8px 10px; text-align:left; }}
QPushButton#calendarNavigation, QPushButton#calendarToday {{ padding:5px 9px; min-height:24px; }}
QCheckBox, QRadioButton {{ spacing:7px; background:transparent; }}
QCheckBox:disabled, QRadioButton:disabled {{ color:{c['disabled']}; }}
QCheckBox::indicator {{ width:15px; height:15px; border:1px solid {c['focus']}; border-radius:3px; background:{c['input']}; }}
QCheckBox::indicator:checked {{ background:{c['accent']}; border-color:{c['accent']}; }}
QCheckBox::indicator:indeterminate {{ background:{c['muted']}; border-color:{c['muted']}; }}
QCheckBox::indicator:disabled {{ background:{c['disabled_surface']}; border-color:{c['disabled_border']}; }}
QRadioButton::indicator {{ width:14px; height:14px; border:1px solid {c['focus']}; border-radius:8px; background:{c['input']}; }}
QRadioButton::indicator:checked {{ background:{c['accent']}; border-color:{c['accent']}; }}
QRadioButton::indicator:disabled {{ background:{c['disabled_surface']}; border-color:{c['disabled_border']}; }}
QProgressBar {{ border:none; background:{c['surface_alt']}; border-radius:2px; min-height:4px; max-height:4px; }}
QProgressBar::chunk {{ background:{c['muted']}; border-radius:2px; }}
QTabWidget::pane {{ border:none; border-top:1px solid {c['border']}; background:{c['surface']}; top:-1px; }}
QTabBar::tab {{ background:transparent; padding:8px 18px; margin-right:8px; color:{c['muted']}; border-bottom:2px solid transparent; }}
QTabBar::tab:selected {{ color:{c['text']}; border-bottom-color:{c['accent']}; font-weight:600; }}
QTabBar::tab:hover {{ background:{c['hover']}; }}
QTabBar::tab:focus {{ border-bottom-color:{c['focus']}; }}
QListWidget {{ border:none; background:{c['surface']}; padding:0; outline:none; }}
QListWidget::item {{ border:1px solid {c['border']}; border-radius:6px; background:{c['surface_alt']}; padding:7px; margin:5px; color:{c['muted']}; }}
QListWidget::item:selected {{ background:{c['selected']}; color:{c['selection_text']}; border-color:{c['focus']}; }}
QListWidget::item:focus {{ border-color:{c['focus']}; }}
QTextEdit, QPlainTextEdit, QTextBrowser {{ background:{c['surface']}; color:{c['muted']}; border:1px solid {c['border']}; border-radius:6px; padding:8px; font-size:9pt; selection-background-color:{c['selected']}; selection-color:{c['selection_text']}; }}
QTableWidget, QTableView {{ background:{c['surface']}; color:{c['text']}; border:none; gridline-color:{c['border']}; alternate-background-color:{c['surface_alt']}; selection-background-color:{c['selected']}; selection-color:{c['selection_text']}; }}
QTableWidget::item:selected, QTableView::item:selected {{ background:{c['selected']}; color:{c['selection_text']}; }}
QHeaderView::section, QTableCornerButton::section {{ background:{c['surface_alt']}; color:{c['muted']}; border:none; border-bottom:1px solid {c['border']}; padding:9px; font-size:9pt; font-weight:600; }}
QScrollArea, QAbstractScrollArea {{ background:{c['surface']}; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:3px; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:3px; }}
QScrollBar::handle:vertical {{ background:{c['scrollbar']}; border-radius:3px; min-height:24px; }}
QScrollBar::handle:horizontal {{ background:{c['scrollbar']}; border-radius:3px; min-width:24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
QMenu, QMenuBar {{ color:{c['text']}; background:{c['surface']}; border:1px solid {c['border']}; border-radius:8px; padding:5px; }}
QMenu::item {{ padding:9px 25px 9px 13px; border-radius:5px; }}
QMenu::item:selected {{ color:{c['selection_text']}; background:{c['selected']}; }}
QMenu::item:disabled {{ color:{c['disabled']}; }}
QMenu::separator {{ height:1px; background:{c['border']}; margin:5px 8px; }}
QMenuBar::item:selected {{ background:{c['selected']}; }}
QToolTip {{ background:{c['tooltip']}; color:{c['tooltip_text']}; padding:7px; border:1px solid {c['border']}; }}
QCalendarWidget {{ color:{c['text']}; background:{c['surface']}; }}
QCalendarWidget QWidget {{ background:{c['surface']}; color:{c['text']}; }}
QCalendarWidget QAbstractItemView {{ background:{c['surface']}; alternate-background-color:{c['surface_alt']}; color:{c['text']}; selection-background-color:{c['accent']}; selection-color:{c['accent_text']}; border:none; outline:0; }}
QCalendarWidget QAbstractItemView:disabled {{ color:{c['disabled']}; }}
QGroupBox {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:6px; margin-top:10px; padding:12px; }}
QGroupBox::title {{ color:{c['muted']}; subcontrol-origin:margin; left:12px; padding:0 5px; }}
QSplitter::handle {{ background:{c['border']}; }}
""" + CLEAR_BUTTON_STYLESHEET


def apply_theme(application: QApplication, theme: str) -> None:
    """Apply native colors live. This does not inject styles into web pages."""
    global _current_theme
    selected = _validated(theme)
    if not isinstance(application, QApplication):
        raise RuntimeError("Create QApplication before applying a Mira theme.")
    _current_theme = selected
    c = colors(selected)
    # Fusion honors a complete application palette consistently on Windows.
    if application.style().objectName().casefold() != "fusion":
        application.setStyle("Fusion")
    palette = QPalette()
    roles = {
        "Window": c["window"], "WindowText": c["text"], "Base": c["input"],
        "AlternateBase": c["surface_alt"], "Text": c["text"], "Button": c["surface"],
        "ButtonText": c["text"], "Highlight": c["accent"], "HighlightedText": c["accent_text"],
        "ToolTipBase": c["tooltip"], "ToolTipText": c["tooltip_text"],
        "PlaceholderText": c["placeholder"], "Link": c["link"], "LinkVisited": c["link_visited"],
        "Light": c["hover"], "Midlight": c["surface_alt"], "Mid": c["border"],
        "Dark": c["border"], "Shadow": c["window"], "BrightText": c["error"],
        "Accent": c["accent"],
    }
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        for name, value in roles.items():
            role = getattr(QPalette.ColorRole, name, None)
            if role is not None:
                palette.setColor(group, role, QColor(value))
    for name in ("WindowText", "Text", "ButtonText", "PlaceholderText"):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, name), QColor(c["disabled"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(c["disabled_surface"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(c["disabled_surface"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(c["disabled_accent"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(c["disabled_accent_text"]))
    application.setPalette(palette)
    application.setStyleSheet(stylesheet(selected))
    application.setProperty("mira_theme", selected)
    for widget in application.allWidgets():
        widget.update()
