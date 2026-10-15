"""Native, asynchronous desktop interface for Mira Media Downloader.

A separate worker owns extraction, downloads and checkpoints and exchanges JSON
lines with this process. An explicitly opened official-site login dialog stores
its session through Windows protection; QSettings retain non-sensitive choices.
"""
from __future__ import annotations

import html
from collections import deque
import json
import os
from pathlib import Path
import re
import sys
import uuid

from PySide6.QtCore import QDate, QLocale, QProcess, QRect, QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextBrowser, QTextEdit, QVBoxLayout, QWidget, QStyle,
    QStyleOptionButton, QStyledItemDelegate, QStyleOptionViewItem,
)

from .localization import get_language, set_language, tr, translate_widget_tree, set_translated_text, localized_help_html
from .themes import apply_theme, colors, get_theme
from .dropdown import PolishedComboBox
from .window_chrome import install_chrome
from .app_identity import apply_app_icon


APP_NAME = "Mira Media Downloader"
STATUS_NAMES = {
    "authorizing": "Подготовка входа",
    "scanning": "Поиск изображений", "downloading": "Скачивание",
    "paused": "На паузе", "completed": "Готово", "stopped": "Остановлено",
    "error": "Ошибка", "interrupted": "Прервано", "pending": "В очереди",
    "running": "В работе", "created": "Создано", "preview": "Просмотр",
    "partial": "Завершено с ошибками",
}

STYLE = """
QWidget { font-family:'Segoe UI'; font-size:10pt; color:#24272c; }
QMainWindow, QDialog { background:#ffffff; }
QLabel#brand { font-size:17pt; font-weight:700; letter-spacing:-0.5px; }
QLabel#hero { font-size:19pt; font-weight:500; margin:4px 0 2px 0; letter-spacing:-0.5px; }
QLabel#eyebrow { color:#747b85; font-size:8pt; font-weight:600; letter-spacing:1px; }
QLabel#title { font-size:15pt; font-weight:600; }
QLabel#section { font-size:10pt; font-weight:600; }
QLabel#muted, QLabel#subtitle { color:#6d737c; font-size:9pt; }
QLabel#status { color:#616770; font-size:9pt; padding:4px 9px; background:#f5f6f7; border-radius:5px; }
QLabel#statNumber, QLabel#statNumberPrimary { font-size:19pt; font-weight:600; color:#25282d; }
QLabel#error { color:#b34c48; }
QLineEdit, QDateEdit, QDoubleSpinBox { background:#ffffff; border:1px solid #dfe2e6; border-radius:6px; padding:6px 9px; min-height:20px; selection-background-color:#e4e7eb; }
QLineEdit:focus, QDateEdit:focus, QDoubleSpinBox:focus { border-color:#747b85; }
QLineEdit:disabled, QDateEdit:disabled, QDoubleSpinBox:disabled { color:#aeb2b8; background:#f7f8f9; border-color:#e9ebed; }
QComboBox { background:#ffffff; border:1px solid #dfe2e6; border-radius:6px; padding:8px 10px; min-height:22px; }
QComboBox:disabled { color:#aeb2b8; background:#f7f8f9; }
QComboBox::drop-down { border:none; width:24px; }
QComboBox QAbstractItemView { background:white; selection-background-color:#eceef1; selection-color:#202329; padding:4px; }
QPushButton { background:#ffffff; border:1px solid #dfe2e6; border-radius:6px; padding:6px 10px; min-height:18px; font-weight:500; }
QPushButton:hover { background:#f5f6f7; border-color:#bdc3ca; }
QPushButton:pressed { background:#e9ecef; }
QPushButton:disabled { color:#afb3ba; background:#f8f9fa; border-color:#e9ecef; }
QPushButton#primary { background:#25282d; color:white; border-color:#25282d; padding:8px 17px; font-weight:600; }
QPushButton#primary:hover { background:#41464e; border-color:#41464e; }
QPushButton#primary:disabled { background:#c3c6cc; border-color:#c3c6cc; color:white; }
QPushButton#quiet { color:#666d77; border:none; background:transparent; }
QPushButton#quiet:hover { background:#f4f5f7; color:#24272c; }
QPushButton#platform { color:#777e88; background:#f8f9fa; border-color:#eef0f2; }
QPushButton#platform:checked { color:#22262c; background:#ffffff; border-color:#8a929e; font-weight:600; }
QPushButton#platform:disabled { color:#aeb2b8; border-color:#edf0f2; background:#f8f9fa; }
QCheckBox { spacing:7px; }
QCheckBox::indicator { width:15px; height:15px; border:1px solid #b6bdc6; border-radius:3px; background:white; }
QCheckBox::indicator:checked { background:#30353c; border-color:#30353c; }
QCheckBox::indicator:disabled { background:#eef0f2; border-color:#d5d9df; }
QProgressBar { border:none; background:#edf0f2; border-radius:2px; min-height:4px; max-height:4px; }
QProgressBar::chunk { background:#5b6471; border-radius:2px; }
QTabWidget::pane { border:none; border-top:1px solid #e5e8ec; background:white; top:-1px; }
QTabBar::tab { padding:8px 18px; margin-right:8px; color:#878d96; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#22262c; border-bottom-color:#30353c; font-weight:600; }
QTabBar::tab:hover { background:#f8f9fa; }
QListWidget { border:none; background:white; padding:0; outline:none; }
QListWidget::item { border:1px solid #edf0f2; border-radius:6px; background:#fafbfc; padding:7px; margin:5px; color:#666e79; }
QListWidget::item:selected { background:#edf0f3; border-color:#a8b0bb; }
QTextEdit, QTextBrowser { background:#ffffff; color:#626b77; border:1px solid #e5e8ec; border-radius:6px; padding:8px; font-size:9pt; }
QTableWidget { background:white; border:none; gridline-color:#eef0f2; alternate-background-color:#fafbfc; selection-background-color:#eceff3; selection-color:#25282d; }
QHeaderView::section { background:#f6f7f9; color:#777f8b; border:none; border-bottom:1px solid #e4e7eb; padding:9px; font-size:9pt; font-weight:600; }
QScrollBar:vertical { background:transparent; width:10px; margin:3px; }
QScrollBar::handle:vertical { background:#d7dce2; border-radius:3px; min-height:24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QToolTip { background:#30353c; color:white; padding:7px; border:none; }
"""


def _label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    result = QLabel(text)
    if name:
        result.setObjectName(name)
    result.setWordWrap(wrap)
    if wrap:
        result.setMinimumWidth(0)
    return result


class _CheckBox(QCheckBox):
    """Native checkbox behavior with a crisp high-contrast check mark."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.isChecked():
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = colors()
        painter.setPen(QPen(QColor(palette["accent_text"] if self.isEnabled() else palette["disabled"]), 1.8))
        x, y = rect.left(), rect.top()
        painter.drawLine(x + 4, y + 8, x + 7, y + 11)
        painter.drawLine(x + 7, y + 11, x + 12, y + 5)
        painter.end()


_ComboBox = PolishedComboBox


class _EmbeddedFileDialog(QFileDialog):
    # QFileDialog may polish itself inside its C++ constructor, before the
    # caller can set Qt.Widget. Its enclosing Mira dialog owns the header.
    _mira_skip_auto_chrome = True


def _dialog_header(dialog: QDialog, layout, title: str, *, resizable: bool = True) -> QWidget:
    dialog.chrome = install_chrome(dialog, resizable=resizable, maximizable=False, minimizable=False)
    dialog.header_widget = QWidget(dialog)
    header = QHBoxLayout(dialog.header_widget)
    header.setContentsMargins(0, 0, 0, 0)
    header.addWidget(_label(title, "title"), 1)
    header.addWidget(dialog.chrome.controls)
    dialog.chrome.set_drag_area(dialog.header_widget)
    layout.addWidget(dialog.header_widget)
    return dialog.header_widget


class _GalleryList(QListWidget):
    resized = Signal()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resized.emit()


class _IntervalSpinBox(QDoubleSpinBox):
    """Keep the native numeric editor usable without the small arrow buttons."""

    def _position_editor(self) -> None:
        # The styled NoButtons control can report a one-pixel edit field.
        # Lay out its existing editor inside the outer field's padding.
        self.lineEdit().setGeometry(self.contentsRect().adjusted(10, 7, -10, -7))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_editor()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._position_editor()


class _GalleryDelegate(QStyledItemDelegate):
    """Keep filename and status on separate, visible native caption lines."""

    def paint(self, painter, option, index) -> None:
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        title, _, status = str(index.data(Qt.ItemDataRole.DisplayRole) or "").partition("\n")
        icon = styled.icon
        painter.save()
        painter.setClipRect(styled.rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(styled.state & QStyle.StateFlag.State_Selected)
        palette = colors()
        painter.setPen(QColor(palette["focus"] if selected else palette["border"]))
        painter.setBrush(QColor(palette["selected"] if selected else palette["surface_alt"]))
        painter.drawRoundedRect(styled.rect.adjusted(5, 5, -5, -5), 6, 6)
        content = styled.rect.adjusted(14, 12, -14, -12)
        line_height = styled.fontMetrics.lineSpacing()
        caption_height = line_height * 2 + 6
        image_rect = QRect(content.x(), content.y(), content.width(), max(1, content.height() - caption_height - 8))
        icon.paint(painter, image_rect, Qt.AlignmentFlag.AlignCenter)
        painter.setFont(styled.font)
        painter.setPen(QColor(palette["text"]))
        title_rect = QRect(content.x(), image_rect.bottom() + 7, content.width(), line_height)
        title = styled.fontMetrics.elidedText(title, Qt.TextElideMode.ElideMiddle, title_rect.width())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, title)
        painter.setPen(QColor(palette["muted"]))
        painter.drawText(title_rect.translated(0, line_height + 3), Qt.AlignmentFlag.AlignCenter, status)
        painter.restore()


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 17, 18, 17)
    layout.setSpacing(12)
    return frame, layout


def _default_destination() -> str:
    if Path("D:/").exists():
        return "D:\\Mira Media"
    return str(Path.home() / "Pictures" / "Mira Media")


def _redact(message: object) -> str:
    # Workers already sanitize messages. Defense in depth for unexpected errors.
    value = str(message)
    value = re.sub(r"(?i)(auth_token|ct0|authorization|cookie|refresh_token|access_token|password)\s*[:=]\s*[^\s,;]+", r"\1=[скрыто]", value)
    value = re.sub(r"(?i)bearer\s+[^\s]+", "Bearer [скрыто]", value)
    return value[:3000]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 840)
        self.setMinimumSize(1020, 720)
        self.settings = QSettings("Mira", "MiraMediaDownloader")
        language = str(self.settings.value("ui_language", "ru"))
        theme = str(self.settings.value("ui_theme", "light"))
        set_language(language if language in {"ru", "en", "zh_CN"} else "ru")
        apply_theme(QApplication.instance(), theme if theme in {"light", "dark"} else "light")
        self._ui_ready = False
        self._log_entries = deque(maxlen=1000)
        self._platform = "x"
        self.process: QProcess | None = None
        self.stdout_buffer = b""
        self.active = False
        self.worker_state = "idle"
        self.current_mode = "download"
        self.current_job_id = ""
        self.current_destination = ""
        self.current_profile = ""
        self.last_terminal_state = ""
        self.closing = False
        self.stderr_seen = False
        self.media_items: dict[str, QListWidgetItem] = {}
        self.jobs: list[dict] = []
        self.total_stats = {"found": 0, "downloaded": 0, "skipped": 0, "failed": 0, "bytes": 0}
        self._build()
        self._load_preferences()
        self._refresh_history()
        self._load_recent()
        self._ui_ready = True
        self._refresh_appearance()
        apply_app_icon(QApplication.instance(), self)

    def _build(self) -> None:
        from .icons import action_icon, platform_icon
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(30, 20, 30, 18)
        outer.setSpacing(8)
        self.header_widget = QWidget(central)
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(_label("Mira", "brand"))
        from . import __version__
        header.addWidget(_label("MEDIA DOWNLOADER · " + __version__, "eyebrow"))
        header.addStretch()
        self.language_button = QPushButton("RU")
        self.language_button.setObjectName("quiet")
        self.language_button.setMinimumHeight(34)
        self.language_button.setIcon(action_icon("globe"))
        self.language_button.setToolTip("Язык интерфейса")
        self.language_menu = QMenu(self)
        self.language_actions = {}
        for code, title in (("ru", "Русский"), ("en", "English"), ("zh_CN", "简体中文")):
            action = self.language_menu.addAction(title)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, language=code: self._change_language(language))
            self.language_actions[code] = action
        self.language_button.clicked.connect(lambda: self.language_menu.popup(self.language_button.mapToGlobal(self.language_button.rect().bottomLeft())))
        header.addWidget(self.language_button)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("quiet")
        self.theme_button.setFixedSize(40, 38)
        self.theme_button.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_button)
        self.help_button = QPushButton("Помощь")
        self.help_button.setObjectName("quiet")
        self.help_button.setIcon(action_icon("help"))
        self.help_button.clicked.connect(self._show_help)
        header.addWidget(self.help_button)
        self.chrome = install_chrome(self)
        header.addWidget(self.chrome.controls)
        self.chrome.set_drag_area(self.header_widget)
        outer.addWidget(self.header_widget)
        outer.addWidget(_label("Сохраним то, что нравится.", "hero"))

        source_row = QHBoxLayout()
        source_row.setSpacing(10)
        self.platform_selector = QWidget()
        selector = QHBoxLayout(self.platform_selector)
        selector.setContentsMargins(0, 0, 0, 0)
        selector.setSpacing(4)
        self.platform_x_button = QPushButton("X")
        self.platform_pixiv_button = QPushButton("Pixiv")
        for button, platform in ((self.platform_x_button, "x"), (self.platform_pixiv_button, "pixiv")):
            button.setCheckable(True)
            button.setObjectName("platform")
            button.setIcon(platform_icon(platform))
            button.setIconSize(QSize(22, 22))
            button.setMinimumWidth(74 if platform == "x" else 96)
            button.clicked.connect(lambda _checked=False, selected=platform: self._choose_platform(selected))
            selector.addWidget(button)
        self.platform_x_button.setChecked(True)
        self.platform_pixiv_button.setToolTip("Pixiv · экспериментальный источник")
        source_row.addWidget(self.platform_selector)
        self.profile = QLineEdit()
        self.profile.setPlaceholderText("Ссылка на автора: https://x.com/username")
        self.profile.setClearButtonEnabled(True)
        self.profile.setMinimumWidth(150)
        self.profile.setToolTip("Вставьте ссылку на профиль автора. X или Pixiv определится автоматически.")
        source_row.addWidget(self.profile, 1)
        self.login_button = QPushButton("Войти в X")
        self.login_button.setIcon(action_icon("login"))
        self.login_button.setMinimumWidth(142)
        self.login_button.clicked.connect(self._login_selected)
        source_row.addWidget(self.login_button)
        self.platform_hint = _label("X / Twitter", "muted")
        self.platform_hint.hide()
        self.session_status = _label("Вход не выполнен", "muted")
        source_row.addWidget(self.session_status)
        outer.addLayout(source_row)
        self.pixiv_login_hint = _label(
            'Pixiv · экспериментально. Сначала настройте аккаунт для показа нужного контента: '
            '<a href="https://www.pixiv.net/settings/viewing">настройки показа</a>. '
            'В окне входа есть такая же кнопка.', "muted", True)
        self.pixiv_login_hint.setOpenExternalLinks(True)
        self.pixiv_login_hint.hide()
        outer.addWidget(self.pixiv_login_hint)

        # These compatibility controls retain the existing preferences/worker
        # contracts. Their visible editor is the transactional native popup.
        self._date_compat = QWidget(self)
        self._date_compat.hide()
        self.from_enabled = _CheckBox("С", self._date_compat)
        self.to_enabled = _CheckBox("По", self._date_compat)
        self.date_from = QDateEdit(QDate.currentDate().addMonths(-1), self._date_compat)
        self.date_to = QDateEdit(QDate.currentDate(), self._date_compat)
        for date in (self.date_from, self.date_to):
            date.setDateRange(QDate(1, 1, 1), QDate(9999, 12, 31))
            date.setDisplayFormat("dd.MM.yyyy")
            date.setCalendarPopup(True)
            date.setEnabled(False)
        self.from_enabled.toggled.connect(self.date_from.setEnabled)
        self.to_enabled.toggled.connect(self.date_to.setEnabled)
        self.pixiv = _CheckBox("Pixiv", self)
        self.pixiv.hide()

        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        self.destination = QLineEdit()
        self.destination.setMinimumWidth(170)
        self.destination.setToolTip("Папка хранения. Внутри создаются каталоги платформы и ID автора.")
        folder_row.addWidget(self.destination, 1)
        self.destination_pick = QPushButton("Выбрать")
        self.destination_pick.setIcon(action_icon("folder"))
        self.destination_pick.clicked.connect(self._pick_destination)
        folder_row.addWidget(self.destination_pick)
        self.only_new = _CheckBox("Только новые")
        self.only_new.setChecked(True)
        self.only_new.setToolTip("Уже сохранённые изображения проверяются по истории и пропускаются.")
        folder_row.addWidget(self.only_new)
        self.date_button = QPushButton("Все даты")
        self.date_button.setIcon(action_icon("calendar"))
        self.date_button.clicked.connect(self._show_date_filter)
        folder_row.addWidget(self.date_button)
        self.advanced_button = QPushButton("Дополнительно")
        self.advanced_button.setIcon(action_icon("settings"))
        self.advanced_button.clicked.connect(self._show_advanced)
        folder_row.addWidget(self.advanced_button)
        outer.addLayout(folder_row)
        self.folder_hint = _label("Внутри выбранной папки: X\\ID автора\\", "muted")
        outer.addWidget(self.folder_hint)
        self._build_advanced()
        self.profile.textChanged.connect(self._profile_changed)
        for check in (self.from_enabled, self.to_enabled):
            check.toggled.connect(self._update_date_button)
        for date in (self.date_from, self.date_to):
            date.dateChanged.connect(self._update_date_button)
        self._update_date_button()

        actions = QHBoxLayout()
        self.download_button = QPushButton("Найти и скачать")
        self.download_button.setObjectName("primary")
        self.download_button.setIcon(action_icon("download", color="#ffffff"))
        self.download_button.setMinimumWidth(190)
        self.download_button.setToolTip("За один запуск найти, посчитать и сохранить картинки по мере обнаружения. Предварительный подсчёт не нужен.")
        self.download_button.clicked.connect(lambda: self._start("download"))
        actions.addWidget(self.download_button)
        self.preview_button = QPushButton("Найти и посчитать")
        self.preview_button.setObjectName("quiet")
        self.preview_button.clicked.connect(lambda: self._start("preview"))
        actions.addWidget(self.preview_button)
        actions.addStretch()
        actions.addWidget(_label("Оригиналы в лучшем доступном качестве", "muted"))
        outer.addLayout(actions)

        stats = QHBoxLayout()
        stats.setSpacing(27)
        self.stat_labels = {}
        for key, title in (("found", "Найдено изображений"), ("downloaded", "Скачано"),
                           ("skipped", "Пропущено"), ("failed", "Ошибки")):
            column = QVBoxLayout()
            column.setSpacing(0)
            value = _label("0", "statNumber")
            self.stat_labels[key] = value
            column.addWidget(value)
            column.addWidget(_label(title, "muted"))
            stats.addLayout(column)
        stats.addStretch()
        self.pause_button = QPushButton("Пауза")
        self.pause_button.setIcon(action_icon("pause"))
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self._pause_resume)
        stats.addWidget(self.pause_button)
        self.stop_button = QPushButton("Стоп")
        self.stop_button.setIcon(action_icon("stop"))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        stats.addWidget(self.stop_button)
        outer.addLayout(stats)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setToolTip("Число изображений уточняется во время поиска; при скачивании показан прогресс текущего изображения.")
        outer.addWidget(self.progress)
        self.status_text = _label("Вставьте ссылку, выберите папку и нажмите «Найти и скачать».", "muted", True)
        outer.addWidget(self.status_text)
        self.count_note = _label("Счётчик растёт во время поиска. Итог известен после завершения.", "muted", True)
        self.count_note.hide()

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        gallery_page = QWidget()
        gallery_layout = QVBoxLayout(gallery_page)
        gallery_layout.setContentsMargins(0, 12, 0, 0)
        gallery_layout.setSpacing(6)
        caption = QHBoxLayout()
        caption.addWidget(_label("Найденные и сохранённые изображения", "section"))
        caption.addStretch()
        self.open_folder = QPushButton("Открыть папку")
        self.open_folder.setObjectName("quiet")
        self.open_folder.setIcon(action_icon("folder"))
        self.open_folder.clicked.connect(self._open_destination)
        caption.addWidget(self.open_folder)
        self.open_post = QPushButton("Открыть пост")
        self.open_post.setObjectName("quiet")
        self.open_post.setEnabled(False)
        self.open_post.clicked.connect(self._open_selected_post)
        caption.addWidget(self.open_post)
        gallery_layout.addLayout(caption)
        self.empty_note = _label("Здесь появятся изображения автора.\nМиниатюры доступны для сохранённых файлов.", "muted", True)
        self.empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_note.setMinimumHeight(50)
        gallery_layout.addWidget(self.empty_note)
        self.gallery = _GalleryList()
        self.gallery.setMinimumHeight(0)
        self.gallery.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setIconSize(QSize(320, 180))
        self.gallery.setGridSize(QSize(352, 258))
        self.gallery.setSpacing(1)
        self.gallery.setWordWrap(False)
        self.gallery.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.gallery.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.gallery.setItemDelegate(_GalleryDelegate(self.gallery))
        self.gallery.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.gallery.itemSelectionChanged.connect(self._selection_changed)
        self.gallery.itemDoubleClicked.connect(self._open_image)
        self.gallery.resized.connect(self._resize_gallery)
        gallery_layout.addWidget(self.gallery, 1)
        self.gallery_note = _label("Двойной щелчок открывает сохранённый файл. Подсчёт не скачивает оригиналы.", "muted", True)
        gallery_layout.addWidget(self.gallery_note)
        self.tabs.addTab(gallery_page, action_icon("image"), "Картинки")

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(0, 14, 0, 0)
        history_layout.addWidget(_label("Задания и контрольные точки", "section"))
        history_layout.addWidget(_label("Выберите задание, чтобы восстановить настройки или продолжить после остановки.", "muted", True))
        self.history = QTableWidget(0, 5)
        self.history.setHorizontalHeaderLabels(["Автор", "Статус", "Найдено", "Скачано", "Обновлено"])
        self.history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history.setAlternatingRowColors(True)
        self.history.verticalHeader().hide()
        self.history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            self.history.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.history.itemSelectionChanged.connect(self._history_selection_changed)
        self.history.itemDoubleClicked.connect(lambda _: self._restore_job(False))
        history_layout.addWidget(self.history, 1)
        history_actions = QHBoxLayout()
        self.load_job = QPushButton("Загрузить настройки")
        self.load_job.setEnabled(False)
        self.load_job.clicked.connect(lambda: self._restore_job(False))
        self.resume_job = QPushButton("Продолжить задание")
        self.resume_job.setIcon(action_icon("play"))
        self.resume_job.setEnabled(False)
        self.resume_job.clicked.connect(lambda: self._restore_job(True))
        history_actions.addWidget(self.load_job)
        history_actions.addWidget(self.resume_job)
        history_actions.addStretch()
        self.refresh_jobs = QPushButton("Обновить")
        self.refresh_jobs.clicked.connect(self._refresh_history)
        history_actions.addWidget(self.refresh_jobs)
        history_layout.addLayout(history_actions)
        self.tabs.addTab(history_page, action_icon("history"), "История")

        journal = QWidget()
        journal_layout = QVBoxLayout(journal)
        journal_layout.setContentsMargins(0, 14, 0, 0)
        journal_header = QHBoxLayout()
        journal_header.addWidget(_label("Ошибки и события", "section"))
        journal_header.addStretch()
        clear_log = QPushButton("Очистить журнал")
        clear_log.setObjectName("quiet")
        clear_log.clicked.connect(self._clear_log)
        journal_header.addWidget(clear_log)
        journal_layout.addLayout(journal_header)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(1000)
        self.log.setPlaceholderText("Ошибки и важные события появятся здесь. Текст можно выделить и скопировать.")
        journal_layout.addWidget(self.log, 1)
        self.tabs.addTab(journal, action_icon("log"), "Журнал")
        outer.addWidget(self.tabs, 1)
        self.destination.editingFinished.connect(self._destination_changed)

    def _resize_gallery(self) -> None:
        width = max(320, self.gallery.viewport().width())
        columns = 3 if width >= 850 else 2
        cell_width = max(160, (width - 18) // columns)
        image_size = QSize(max(140, cell_width - 28), max(80, int((cell_width - 28) * 0.5625)))
        grid_size = QSize(cell_width, image_size.height() + 78)
        if self.gallery.gridSize() == grid_size:
            return
        self.gallery.setIconSize(image_size)
        self.gallery.setGridSize(grid_size)
        for index in range(self.gallery.count()):
            self.gallery.item(index).setSizeHint(QSize(cell_width - 14, image_size.height() + 64))

    def _change_language(self, language: str) -> None:
        set_language(language)
        self._refresh_appearance()
        self._save_preferences()

    def _toggle_theme(self) -> None:
        apply_theme(QApplication.instance(), "dark" if get_theme() == "light" else "light")
        self._refresh_appearance()
        self._save_preferences()

    def _translate_runtime(self) -> None:
        for name in ("status_text", "count_note", "pause_button", "empty_note", "gallery_note",
                     "auth_hint", "browser_status", "session_status", "login_button", "logout_button",
                     "auth_source", "platform_hint", "profile", "folder_hint"):
            widget = getattr(self, name, None)
            if widget is not None:
                translate_widget_tree(widget)

    def _refresh_appearance(self) -> None:
        if not self._ui_ready:
            return
        translate_widget_tree(self)
        self._update_auth_controls()
        self._update_date_button()
        self.language_button.setText({"ru": "RU", "en": "EN", "zh_CN": "中文"}[get_language()])
        self.request_delay.setLocale(QLocale({"ru": "ru_RU", "en": "en_US", "zh_CN": "zh_CN"}[get_language()]))
        for code, action in self.language_actions.items():
            action.setChecked(code == get_language())
        # Language names stay in their own language in every version of the menu.
        for code, title in (("ru", "Русский"), ("en", "English"), ("zh_CN", "简体中文")):
            self.language_actions[code].setText(title)
        self._refresh_theme_visuals()
        self._localize_gallery()
        for row, job in enumerate(self.jobs):
            if row < self.history.rowCount():
                profile = str(job.get("username") or job.get("profile_url") or tr("Задание"))
                suffix = tr(" · подсчёт") if job.get("mode") == "preview" else ""
                self.history.item(row, 0).setText(f'{str(job.get("platform") or "x").upper()} / {profile}{suffix}')
                self.history.item(row, 1).setText(tr(STATUS_NAMES.get(str(job.get("status", "")), str(job.get("status", "")))))
        self._render_log()
        self._translate_runtime()
        self.gallery.viewport().update()

    def _refresh_theme_visuals(self) -> None:
        from .icons import action_icon
        palette = colors()
        for name, icon_name in (("help_button", "help"), ("language_button", "globe"),
                                ("destination_pick", "folder"), ("date_button", "calendar"),
                                ("advanced_button", "settings"), ("login_button", "login"),
                                ("logout_button", "logout"), ("open_folder", "folder"),
                                ("pause_button", "play" if self.worker_state == "paused" else "pause"),
                                ("stop_button", "stop")):
            getattr(self, name).setIcon(action_icon(icon_name))
        self.download_button.setIcon(action_icon("download", color=palette["accent_text"]))
        self.theme_button.setIcon(action_icon("moon" if get_theme() == "light" else "sun"))
        set_translated_text(self.theme_button, "")
        self.theme_button.setToolTip(tr("Тёмная тема" if get_theme() == "light" else "Светлая тема"))
        self.theme_button.setAccessibleName(self.theme_button.toolTip())
        for index, icon_name in enumerate(("image", "history", "log")):
            self.tabs.setTabIcon(index, action_icon(icon_name))
        self.request_delay.lineEdit().setStyleSheet(
            "border:none; padding:0; margin:0; min-height:0; background:transparent; "
            f'selection-color:{palette["selection_text"]}; selection-background-color:{palette["selected"]};')
        self.request_delay._position_editor()
        self.chrome.refresh()
        for dialog in self.findChildren(QDialog):
            chrome = getattr(dialog, "chrome", None)
            if chrome is not None:
                chrome.refresh()
        hint = re.sub(r'<a(?: style="[^"]*")? href=', f'<a style="color:{palette["link"]}" href=', self.pixiv_login_hint.text())
        self.pixiv_login_hint.setText(hint)
        self.pixiv_login_hint.setProperty("_mira_i18n_last_text", hint)
        apply_app_icon(QApplication.instance(), self)
        self.update()

    def _make_placeholder_icon(self) -> QIcon:
        placeholder = QPixmap(384, 216)
        placeholder.fill(QColor(colors()["surface_alt"]))
        painter = QPainter(placeholder)
        painter.setPen(QColor(colors()["muted"]))
        painter.setFont(QFont("Segoe UI", 13))
        painter.drawText(placeholder.rect(), Qt.AlignmentFlag.AlignCenter, tr("Картинка найдена"))
        painter.end()
        return QIcon(placeholder)

    def _localize_gallery(self) -> None:
        self._placeholder_icon = self._make_placeholder_icon()
        for item in self.media_items.values():
            data = item.data(Qt.ItemDataRole.UserRole) or {}
            if item.data(Qt.ItemDataRole.UserRole + 1):
                item.setText(Path(str(data.get("path") or "")).name + "\n" + tr("Сохранено"))
            else:
                post_id = str(data.get("post_id") or "")[-18:]
                title = tr("Пост {post_id}").format(post_id=post_id) if post_id else tr("Изображение автора")
                item.setText(title + "\n" + tr("Без локального превью"))
                item.setToolTip(tr("Оригинал ещё не сохранён. Во время подсчёта картинки не скачиваются."))
                item.setIcon(self._placeholder_icon)

    def _build_advanced(self) -> None:
        from .icons import action_icon
        self.advanced_dialog = QDialog(self)
        self.advanced_dialog.setWindowTitle("Дополнительные настройки — Mira")
        self.advanced_dialog.resize(590, 490)
        layout = QVBoxLayout(self.advanced_dialog)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        _dialog_header(self.advanced_dialog, layout, "Вход и ограничения запросов")
        layout.addWidget(_label("Основной способ — официальный вход в приложении. Дополнительные способы используют только ваши локальные данные.", "muted", True))
        self.auth_source = _ComboBox()
        for label, value in (("Войти в X в приложении", "embedded"), ("Из браузера", "browser"),
                             ("Из файла cookies.txt", "file"), ("Без авторизации", "none")):
            self.auth_source.addItem(label, value)
        self.auth_source.currentIndexChanged.connect(self._update_auth_controls)
        layout.addWidget(self.auth_source)
        self.browser_fields = QWidget()
        browser_layout = QVBoxLayout(self.browser_fields)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        self.browser = _ComboBox()
        for label, name in (("Firefox · рекомендуется", "firefox"), ("Chrome", "chrome"), ("Edge", "edge"), ("Brave", "brave")):
            self.browser.addItem(label, name)
        self.browser.currentIndexChanged.connect(lambda: self._refresh_browser_profiles(""))
        browser_layout.addWidget(self.browser)
        profile_row = QHBoxLayout()
        self.browser_profile = _ComboBox()
        self.browser_profile.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.browser_profile.currentIndexChanged.connect(self._update_auth_controls)
        profile_row.addWidget(self.browser_profile, 1)
        self.browser_refresh = QPushButton("Обновить")
        self.browser_refresh.clicked.connect(lambda: self._refresh_browser_profiles())
        profile_row.addWidget(self.browser_refresh)
        browser_layout.addLayout(profile_row)
        self.browser_status = _label("", "muted", True)
        browser_layout.addWidget(self.browser_status)
        layout.addWidget(self.browser_fields)
        self.file_fields = QWidget()
        file_layout = QHBoxLayout(self.file_fields)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.cookies = QLineEdit()
        self.cookies.setReadOnly(True)
        self.cookies.setPlaceholderText("Ваш файл cookies.txt")
        self.cookies.setToolTip("Файл Netscape. Путь и содержимое не сохраняются в настройках.")
        file_layout.addWidget(self.cookies, 1)
        self.cookie_pick = QPushButton("…")
        self.cookie_pick.setFixedWidth(42)
        self.cookie_pick.clicked.connect(self._pick_cookies)
        file_layout.addWidget(self.cookie_pick)
        self.cookie_clear = QPushButton("×")
        self.cookie_clear.setFixedWidth(42)
        self.cookie_clear.clicked.connect(self.cookies.clear)
        file_layout.addWidget(self.cookie_clear)
        layout.addWidget(self.file_fields)
        self.auth_hint = _label("", "muted", True)
        layout.addWidget(self.auth_hint)
        self.embedded_fields = QWidget()
        session_row = QHBoxLayout(self.embedded_fields)
        session_row.setContentsMargins(0, 0, 0, 0)
        session_row.addWidget(_label("Сохранённый вход Mira", "muted"))
        session_row.addStretch()
        self.logout_button = QPushButton("Выйти из X")
        self.logout_button.setIcon(action_icon("logout"))
        self.logout_button.setToolTip("Удалить только вход выбранной платформы, сохранённый Mira на этом компьютере.")
        self.logout_button.clicked.connect(self._logout_selected)
        session_row.addWidget(self.logout_button)
        layout.addWidget(self.embedded_fields)
        limits = QHBoxLayout()
        limits.addWidget(_label("Интервал запросов, с", "section"))
        limits.addStretch()
        self.request_delay = _IntervalSpinBox()
        self.request_delay.setRange(2.0, 120.0)
        self.request_delay.setSingleStep(0.5)
        self.request_delay.setDecimals(1)
        self.request_delay.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.request_delay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.request_delay.setFixedWidth(104)
        # The outer spin box owns the border/padding. Applying the generic
        # QLineEdit padding again to its internal editor clips its value.
        self.request_delay.lineEdit().setStyleSheet("border:none; padding:0; margin:0; min-height:0; background:transparent; selection-color:#24272c; selection-background-color:#e4e7eb;")
        self.request_delay.setValue(3.0)
        self.request_delay.setToolTip("Бережная пауза между запросами к сайту. При ограничениях увеличьте интервал.")
        self.request_delay_minus = QPushButton("−")
        self.request_delay_plus = QPushButton("+")
        for button, title, step in ((self.request_delay_minus, "Уменьшить интервал на полсекунды", -1),
                                    (self.request_delay_plus, "Увеличить интервал на полсекунды", 1)):
            button.setFixedSize(38, 38)
            button.setToolTip(title)
            button.clicked.connect(lambda _checked=False, direction=step: self.request_delay.stepBy(direction))
        limits.addWidget(self.request_delay_minus)
        limits.addWidget(self.request_delay)
        limits.addWidget(self.request_delay_plus)
        layout.addLayout(limits)
        layout.addStretch()
        done = QPushButton("Готово")
        done.setObjectName("primary")
        done.clicked.connect(self.advanced_dialog.accept)
        layout.addWidget(done, 0, Qt.AlignmentFlag.AlignRight)

    def _show_advanced(self) -> None:
        if not self.active:
            translate_widget_tree(self.advanced_dialog)
            self.advanced_dialog.exec()
            self._save_preferences()

    def _show_date_filter(self) -> None:
        if self.active:
            return
        from .date_filter import DateFilterDialog
        first, last = self._date_range()
        dialog = DateFilterDialog(self, date_from=first, date_to=last)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            first, last = dialog.selected_range()
            for value, check, date in ((first, self.from_enabled, self.date_from), (last, self.to_enabled, self.date_to)):
                parsed = QDate.fromString(value, "yyyy-MM-dd")
                check.setChecked(parsed.isValid())
                if parsed.isValid():
                    date.setDate(parsed)
            self._update_date_button()
            self._save_preferences()
        dialog.deleteLater()

    def _date_range(self) -> tuple[str, str]:
        return (self.date_from.date().toString("yyyy-MM-dd") if self.from_enabled.isChecked() else "",
                self.date_to.date().toString("yyyy-MM-dd") if self.to_enabled.isChecked() else "")

    def _update_date_button(self, *_args) -> None:
        if not hasattr(self, "date_button"):
            return
        from .date_filter import range_label
        first, last = self._date_range()
        label = range_label(first, last)
        self.date_button.setText(label)
        self.date_button.setToolTip(label + ". " + tr("Границы включительно, даты публикации в UTC."))

    def _apply_platform(self, platform: str) -> None:
        self._platform = platform
        self.platform_x_button.setChecked(platform == "x")
        self.platform_pixiv_button.setChecked(platform == "pixiv")
        self.pixiv.setChecked(platform == "pixiv")
        self.profile.setPlaceholderText("Ссылка на автора: https://www.pixiv.net/users/12345" if platform == "pixiv" else "Ссылка на автора: https://x.com/username")
        set_translated_text(self.folder_hint, "Внутри выбранной папки: " + ("Pixiv" if platform == "pixiv" else "X") + "\\ID автора\\")
        self._update_auth_controls()

    def _choose_platform(self, platform: str) -> None:
        if self.active:
            return
        from .adapters.profiles import parse_profile
        try:
            previous = parse_profile(self.profile.text(), True).platform
        except ValueError:
            host = QUrl(self.profile.text().strip()).host().lower()
            previous = ("x" if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
                        else "pixiv" if host in {"pixiv.net", "www.pixiv.net"} else None)
        if previous and previous != platform:
            self.profile.clear()
        self._apply_platform(platform)

    def _profile_changed(self, *_args) -> None:
        from .adapters.profiles import parse_profile
        try:
            self._apply_platform(parse_profile(self.profile.text(), True).platform)
        except ValueError:
            self._update_auth_controls()


    def _load_preferences(self) -> None:
        self.destination.setText(str(self.settings.value("destination", _default_destination())))
        self.destination.setCursorPosition(0)
        self.profile.setText(str(self.settings.value("profile_url", "")))
        self.only_new.setChecked(str(self.settings.value("only_new", "true")).lower() == "true")
        legacy_pixiv = str(self.settings.value("pixiv_enabled", "false")).lower() == "true"
        # Browser names and profile locations contain no session values. File
        # cookie paths deliberately remain session-only, as in previous versions.
        # Existing explicit file/browser choices remain available. A clean
        # installation requires no browser or profile selection.
        source = str(self.settings.value("auth_source", "embedded"))
        index = self.auth_source.findData(source)
        self.auth_source.setCurrentIndex(index if index >= 0 else 0)
        browser = str(self.settings.value("browser", "firefox"))
        index = self.browser.findData(browser)
        self.browser.blockSignals(True)
        self.browser.setCurrentIndex(index if index >= 0 else 0)
        self.browser.blockSignals(False)
        self._refresh_browser_profiles(str(self.settings.value("browser_profile", "")))
        try:
            self.request_delay.setValue(float(self.settings.value("request_delay", 3.0)))
        except (ValueError, TypeError):
            pass
        for key, check, date in (("date_from", self.from_enabled, self.date_from), ("date_to", self.to_enabled, self.date_to)):
            value = str(self.settings.value(key, ""))
            parsed = QDate.fromString(value, "yyyy-MM-dd")
            if parsed.isValid():
                date.setDate(parsed)
                check.setChecked(True)
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        from .adapters.profiles import parse_profile
        try:
            selected = parse_profile(self.profile.text(), True).platform
        except ValueError:
            selected = str(self.settings.value("selected_platform", "pixiv" if legacy_pixiv else "x"))
        self._apply_platform(selected if selected in {"x", "pixiv"} else "x")
        self._update_date_button()

    def _save_preferences(self) -> None:
        self.settings.setValue("ui_language", get_language())
        self.settings.setValue("ui_theme", get_theme())
        self.settings.setValue("destination", self.destination.text().strip())
        self.settings.setValue("profile_url", self.profile.text().strip())
        self.settings.setValue("only_new", self.only_new.isChecked())
        self.settings.setValue("pixiv_enabled", self.pixiv.isChecked())
        self.settings.setValue("selected_platform", self._selected_platform())
        self.settings.setValue("auth_source", self.auth_source.currentData())
        self.settings.setValue("browser", self.browser.currentData())
        self.settings.setValue("browser_profile", self.browser_profile.currentData() or "")
        self.settings.setValue("request_delay", self.request_delay.value())
        self.settings.setValue("date_from", self.date_from.date().toString("yyyy-MM-dd") if self.from_enabled.isChecked() else "")
        self.settings.setValue("date_to", self.date_to.date().toString("yyyy-MM-dd") if self.to_enabled.isChecked() else "")
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.sync()

    def _append_log(self, level: str, message: object) -> None:
        from datetime import datetime
        self._log_entries.append((datetime.now().strftime("%H:%M:%S"), level, _redact(message)))
        self._append_rendered_log(self._log_entries[-1])

    def _append_rendered_log(self, entry) -> None:
        timestamp, level, message = entry
        label = {"error": "Ошибка", "warning": "Внимание", "info": "Инфо"}.get(level, "Инфо")
        safe = html.escape(tr(message))
        palette = colors()
        color = palette["error"] if level == "error" else palette["muted"]
        self.log.append(f'<span style="color:{palette["muted"]}">{timestamp}</span> &nbsp; <span style="color:{color}">{html.escape(tr(label))}</span> &nbsp; {safe}')

    def _render_log(self) -> None:
        self.log.clear()
        for entry in self._log_entries:
            self._append_rendered_log(entry)

    def _clear_log(self) -> None:
        self._log_entries.clear()
        self.log.clear()

    def _inline_error(self, message: str) -> None:
        set_translated_text(self.status_text, message)
        self._append_log("error", message)

    def _pick_cookies(self) -> None:
        path = self._pick_path("Ваш локальный файл cookies", filters="Cookies Netscape (*.txt *.cookies);;Все файлы (*)")
        if path:
            self.cookies.setText(path)
            self.auth_source.setCurrentIndex(self.auth_source.findData("file"))

    def _pick_path(self, title: str, *, directory: bool = False, initial: str = "", filters: str = "") -> str:
        # Embed Qt's normal file chooser in Mira's header rather than opening
        # an OS-captioned picker. The chooser still validates its selection.
        dialog = QDialog(self)
        dialog.setWindowTitle(tr(title))
        dialog.resize(860, 600)
        dialog.setMinimumSize(680, 460)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 18)
        _dialog_header(dialog, layout, title)
        picker = _EmbeddedFileDialog(dialog, tr(title), initial, tr(filters))
        picker.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        picker.setWindowFlags(Qt.WindowType.Widget)
        picker.setFileMode(QFileDialog.FileMode.Directory if directory else QFileDialog.FileMode.ExistingFile)
        picker.setOption(QFileDialog.Option.ShowDirsOnly, directory)
        picker.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        picker.setSizeGripEnabled(False)
        for label, text in ((QFileDialog.DialogLabel.LookIn, "Папка:"),
                            (QFileDialog.DialogLabel.FileName, "Каталог:" if directory else "Имя файла:"),
                            (QFileDialog.DialogLabel.FileType, "Тип файлов:"),
                            (QFileDialog.DialogLabel.Accept, "Выбрать" if directory else "Открыть"),
                            (QFileDialog.DialogLabel.Reject, "Отмена")):
            picker.setLabelText(label, tr(text))
        picker.accepted.connect(dialog.accept)
        picker.rejected.connect(dialog.reject)
        layout.addWidget(picker, 1)
        dialog.file_picker = picker
        translate_widget_tree(dialog)
        selected = picker.selectedFiles() if dialog.exec() == QDialog.DialogCode.Accepted else []
        dialog.deleteLater()
        return selected[0] if selected else ""

    def _refresh_browser_profiles(self, selected_profile: str | None = None) -> None:
        """Discover profile metadata only; session cookies belong to the worker."""
        if self.active:
            return
        from .browser_auth import discover_profiles
        selected = selected_profile if selected_profile is not None else self.browser_profile.currentData()
        self.browser_profile.blockSignals(True)
        self.browser_profile.clear()
        self.browser_discovery_error = False
        try:
            profiles = discover_profiles(str(self.browser.currentData()))
        except (OSError, ValueError):
            profiles = []
            self.browser_discovery_error = True
        for profile in profiles:
            self.browser_profile.addItem(profile.label, profile.profile_id)
            self.browser_profile.setItemData(self.browser_profile.count() - 1, str(profile.path), Qt.ItemDataRole.ToolTipRole)
        if not profiles:
            self.browser_profile.addItem("Профили не найдены", "")
        elif selected:
            index = self.browser_profile.findData(str(selected))
            if index >= 0:
                self.browser_profile.setCurrentIndex(index)
            else:
                self.browser_profile.insertItem(0, "Выберите доступный профиль", "")
                self.browser_profile.setCurrentIndex(0)
        self.browser_profile.blockSignals(False)
        self._update_auth_controls()

    def _update_auth_controls(self, *_args) -> None:
        # Signals can arrive while _build() is assembling the auth fields.
        if not hasattr(self, "auth_hint"):
            return
        source = self.auth_source.currentData()
        self.browser_fields.setVisible(source == "browser")
        self.file_fields.setVisible(source == "file")
        self._refresh_session_status()
        label = "Pixiv" if self._selected_platform() == "pixiv" else "X"
        if source == "embedded":
            set_translated_text(self.auth_hint, f"Нажмите «Войти в {label}», войдите на официальной странице и сохраните вход. "
                                   "Сессии платформ хранятся отдельно и защищены Windows. Доступность контента зависит от аккаунта.")
        elif source == "browser":
            has_profile = bool(self.browser_profile.currentData())
            self.browser_profile.setEnabled(not self.active and any(self.browser_profile.itemData(i) for i in range(self.browser_profile.count())))
            if not has_profile:
                message = ("Не удалось прочитать список профилей. Проверьте доступ и нажмите «Обновить»."
                           if getattr(self, "browser_discovery_error", False) else
                           f"Профиль недоступен. Выберите профиль или запустите браузер, войдите в {label} и нажмите «Обновить».")
                set_translated_text(self.browser_status, message)
            else:
                set_translated_text(self.browser_status, f"Войдите в {label} в выбранном профиле. Cookies читаются локально только при запуске задания.")
            if self.browser.currentData() == "firefox":
                set_translated_text(self.auth_hint, "Firefox: используется обычная сессия профиля. Вход в отдельном контейнере не поддерживается.")
            else:
                set_translated_text(self.auth_hint, "Защищённая сессия Chrome, Edge или Brave может быть недоступна. В таком случае используйте Firefox или свой файл cookies.txt.")
        elif source == "file":
            set_translated_text(self.auth_hint, "Собственный файл Netscape. Путь не запоминается; cookies используются только для выбранной платформы.")
        else:
            set_translated_text(self.auth_hint, "Только доступ без входа. Доступность картинок ограничена платформой; при отказе задание покажет ошибку.")
        self._translate_runtime()

    def _selected_platform(self) -> str:
        return self._platform

    def _refresh_session_status(self) -> None:
        from .session_vault import has_x_session, has_session
        platform = self._selected_platform()
        label = "Pixiv" if platform == "pixiv" else "X"
        try:
            saved = has_x_session() if platform == "x" else has_session(platform)
        except (OSError, ValueError):
            saved = False
        set_translated_text(self.session_status, "Вход сохранён" if saved else "Вход не выполнен")
        set_translated_text(self.login_button, f"Войти в {label}")
        self.login_button.setToolTip(f"Открыть официальную страницу входа {label} прямо в приложении.")
        set_translated_text(self.logout_button, f"Выйти из {label}")
        self.auth_source.setItemText(self.auth_source.findData("embedded"), f"Войти в {label} в приложении")
        set_translated_text(self.platform_hint, "Pixiv — экспериментальный источник" if platform == "pixiv" else "X / Twitter — основной источник")
        self.pixiv_login_hint.setVisible(platform == "pixiv")
        self.login_button.setEnabled(not self.active)
        self.logout_button.setEnabled(not self.active and saved)
        self._translate_runtime()

    def _login_x(self) -> None:
        self._login_selected(platform="x")

    def _login_selected(self, _checked=False, *, platform: str | None = None) -> None:
        if self.active:
            return
        platform = platform or self._selected_platform()
        label = "Pixiv" if platform == "pixiv" else "X"
        try:
            # WebEngine is intentionally absent from ordinary native startup
            # and from worker processes; load it only on this explicit action.
            from .login import open_x_login, open_login
            saved = open_x_login(self) if platform == "x" else open_login(self, platform)
        except (ImportError, RuntimeError):
            self._inline_error(f"Не удалось открыть встроенный вход {label}. Проверьте комплектность приложения "
                               "или используйте дополнительный способ авторизации.")
            return
        if saved:
            self.auth_source.setCurrentIndex(self.auth_source.findData("embedded"))
            set_translated_text(self.status_text, f"Вход в {label} сохранён. Можно считать и скачивать картинки доступных авторов.")
        self._refresh_session_status()

    def _logout_x(self) -> None:
        self._logout_selected(platform="x")

    def _logout_selected(self, _checked=False, *, platform: str | None = None) -> None:
        if self.active:
            return
        platform = platform or self._selected_platform()
        label = "Pixiv" if platform == "pixiv" else "X"
        from .session_vault import clear_x_session, clear_session, SessionError
        try:
            clear_x_session() if platform == "x" else clear_session(platform)
        except (OSError, SessionError):
            self._inline_error("Не удалось удалить сохранённый вход Mira. Проверьте доступ к локальным данным приложения.")
            return
        self._refresh_session_status()
        set_translated_text(self.status_text, f"Вход {label} в Mira удалён с этого компьютера. Это не завершает другие сеансы {label}; "
                                 f"при необходимости отзовите их в настройках {label}.")

    def _pick_destination(self) -> None:
        initial = self.destination.text().strip() or _default_destination()
        folder = self._pick_path("Каталог коллекции", directory=True, initial=initial)
        if folder:
            self.destination.setText(str(Path(folder)))
            self.destination.setCursorPosition(0)
            self._destination_changed()

    def _destination_changed(self) -> None:
        if not self.active:
            self._save_preferences()
            self._refresh_history()
            self._load_recent()

    def _validated_options(self, mode: str, job_id: str = "") -> dict | None:
        profile = self.profile.text().strip()
        if not profile:
            self._inline_error("Вставьте ссылку на профиль автора.")
            self.profile.setFocus()
            return None
        from .adapters.profiles import parse_profile
        try:
            canonical = parse_profile(profile, self.pixiv.isChecked())
        except ValueError as error:
            self._inline_error(str(error))
            return None
        profile = canonical.url
        if canonical.platform != self._selected_platform():
            self._inline_error("Ссылка и выбранная платформа не совпадают. Выберите нужную платформу или вставьте другую ссылку.")
            return None
        if self.from_enabled.isChecked() and self.to_enabled.isChecked() and self.date_from.date() > self.date_to.date():
            self._inline_error("Начальная дата должна быть не позже конечной.")
            return None
        folder = self.destination.text().strip()
        if not folder:
            self._inline_error("Выберите каталог хранения.")
            return None
        try:
            target = Path(folder).expanduser().resolve()
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            self._inline_error("Не удалось открыть каталог хранения. Выберите доступную папку.")
            return None
        auth_source = str(self.auth_source.currentData())
        cookies = self.cookies.text().strip() if auth_source == "file" else ""
        browser = str(self.browser.currentData()) if auth_source == "browser" else ""
        browser_profile = str(self.browser_profile.currentData() or "") if auth_source == "browser" else ""
        if auth_source == "embedded":
            from .session_vault import has_x_session, has_session
            label = "Pixiv" if canonical.platform == "pixiv" else "X"
            try:
                saved = has_x_session() if canonical.platform == "x" else has_session(canonical.platform)
            except (OSError, ValueError):
                saved = False
            if not saved:
                self._inline_error(f"Нажмите «Войти в {label}», завершите вход на официальной странице и нажмите «Сохранить вход».")
                self.login_button.setFocus()
                self._refresh_session_status()
                return None
        if auth_source == "file" and (not cookies or not Path(cookies).is_file()):
            self._inline_error("Выберите свой существующий файл cookies.txt или другой способ авторизации.")
            return None
        if auth_source == "browser" and not browser_profile:
            self._inline_error("Профиль браузера недоступен. Выберите доступный профиль и нажмите «Обновить». Способ авторизации сохранён.")
            return None
        self.profile.setText(profile)
        self.destination.setText(str(target))
        return {
            "profile_url": profile, "destination": str(target),
            "date_from": self.date_from.date().toString("yyyy-MM-dd") if self.from_enabled.isChecked() else "",
            "date_to": self.date_to.date().toString("yyyy-MM-dd") if self.to_enabled.isChecked() else "",
            "cookies_file": cookies or "", "only_new": self.only_new.isChecked(),
            "auth_source": auth_source, "browser": browser, "browser_profile": browser_profile,
            "pixiv_enabled": self.pixiv.isChecked(), "request_delay": self.request_delay.value(),
            "download_delay": 1.5, "mode": mode, "job_id": job_id or uuid.uuid4().hex,
        }

    def _start(self, mode: str, job_id: str = "") -> None:
        if self.active:
            return
        options = self._validated_options(mode, job_id)
        if options is None:
            return
        self._save_preferences()
        try:
            request_dir = Path(options["destination"]) / ".mira" / "tasks"
            request_dir.mkdir(parents=True, exist_ok=True)
            request_file = request_dir / (uuid.uuid4().hex + ".json")
            request_file.write_text(json.dumps(options, ensure_ascii=False), encoding="utf-8")
        except OSError:
            self._inline_error("Не удалось сохранить запрос задания. Проверьте права на каталог.")
            return
        self.current_mode = mode
        self.current_job_id = options["job_id"]
        self.current_destination = options["destination"]
        self.current_profile = options["profile_url"]
        self.last_terminal_state = ""
        self.stdout_buffer = b""
        self.stderr_seen = False
        self.total_stats = {"found": 0, "downloaded": 0, "skipped": 0, "failed": 0, "bytes": 0}
        self._update_stats({})
        self.gallery.clear()
        self.media_items.clear()
        self.empty_note.show()
        set_translated_text(self.empty_note, "Ищем доступные изображения…\nСчётчик обновится по мере их обнаружения.")
        self.tabs.setCurrentIndex(0)
        self.progress.setRange(0, 0)
        set_translated_text(self.status_text, "Подготавливаем локальный обработчик…")
        set_translated_text(self.count_note, "Счётчик растёт во время поиска. Итог доступных картинок известен после завершения.")
        self._set_active(True)
        process = QProcess(self)
        self.process = process
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.finished.connect(self._worker_finished)
        process.errorOccurred.connect(self._worker_error)
        if getattr(sys, "frozen", False):
            arguments = ["--worker", str(request_file)]
        else:
            arguments = ["-m", "mira_media", "--worker", str(request_file)]
            process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
        process.setProgram(sys.executable)
        process.setArguments(arguments)
        environment = process.processEnvironment()
        # systemEnvironment is required: a newly constructed process environment
        # may otherwise be empty on older Qt builds.
        from PySide6.QtCore import QProcessEnvironment
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUNBUFFERED", "1")
        process.setProcessEnvironment(environment)
        process.start()
        self._append_log("info", "Запущен подсчёт доступных картинок." if mode == "preview" else "Задание запущено. Контрольные точки сохраняются автоматически.")

    def _set_active(self, value: bool) -> None:
        self.active = value
        for widget in (self.profile, self.pixiv, self.cookies, self.cookie_pick, self.cookie_clear,
                       self.platform_x_button, self.platform_pixiv_button, self.date_button, self.advanced_button,
                       self.auth_source, self.browser, self.browser_profile, self.browser_refresh,
                       self.login_button, self.logout_button,
                       self.destination, self.destination_pick, self.only_new, self.from_enabled,
                       self.to_enabled, self.request_delay, self.request_delay_minus, self.request_delay_plus,
                       self.preview_button, self.download_button):
            widget.setEnabled(not value)
        self.date_from.setEnabled(not value and self.from_enabled.isChecked())
        self.date_to.setEnabled(not value and self.to_enabled.isChecked())
        self.pause_button.setEnabled(value)
        self.stop_button.setEnabled(value)
        self.refresh_jobs.setEnabled(not value)
        set_translated_text(self.pause_button, "Пауза")
        from .icons import action_icon
        self.pause_button.setIcon(action_icon("pause"))
        self._update_auth_controls()
        self._history_selection_changed()

    def _read_stdout(self) -> None:
        if self.process is None:
            return
        self.stdout_buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.stdout_buffer:
            line, self.stdout_buffer = self.stdout_buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                event = json.loads(line.decode("utf-8-sig"))
                if isinstance(event, dict):
                    self._event(event)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
                self._append_log("warning", "Обработчик вернул нечитаемое сообщение. Задание продолжает работу.")
        if len(self.stdout_buffer) > 2_000_000:
            self.stdout_buffer = b""
            self._append_log("warning", "Слишком длинное служебное сообщение пропущено.")

    def _read_stderr(self) -> None:
        if self.process is not None:
            self.process.readAllStandardError()  # Never surface raw extractor output or cookies.
            self.stderr_seen = True

    def _event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "state":
            state = str(event.get("state", ""))
            self.worker_state = state
            if state in {'scanning', 'authorizing'}:
                self.progress.setRange(0, 0)
            elif state == 'downloading':
                self.progress.setRange(0, 1000)
                self.progress.setValue(0)
            message = _redact(event.get("message", ""))
            set_translated_text(self.status_text, message or STATUS_NAMES.get(state, "В работе"))
            if event.get("job_id"):
                self.current_job_id = str(event["job_id"])
            set_translated_text(self.pause_button, "Продолжить" if state == "paused" else "Пауза")
            from .icons import action_icon
            self.pause_button.setIcon(action_icon("play" if state == "paused" else "pause"))
            if state in {"completed", "partial", "stopped", "error"}:
                self.last_terminal_state = state
                self.pause_button.setEnabled(False)
                self.stop_button.setEnabled(False)
                if state == "completed":
                    set_translated_text(self.count_note, "Поиск завершён. Показано число доступных картинок в выбранных датах.")
                    self.progress.setRange(0, 100)
                    self.progress.setValue(100)
                elif state == "stopped":
                    set_translated_text(self.count_note, "Сохранена контрольная точка. Это число картинок, найденных до остановки.")
                elif state == "partial":
                    set_translated_text(self.count_note, "Поиск завершён, часть файлов не скачана. Продолжите задание из истории, чтобы повторить попытку.")
                    self.progress.setRange(0, 100)
                    self.progress.setValue(100)
                else:
                    set_translated_text(self.count_note, "Задание завершилось с ошибкой. Найденное число может быть неполным.")
        elif kind == "stats":
            self._update_stats(event)
        elif kind == "item":
            self._add_item(event)
        elif kind == "log":
            self._append_log(str(event.get("level", "info")), event.get("message", ""))
        elif kind == "progress":
            try:
                current = max(0, int(event.get("current", 0)))
                total = max(0, int(event.get("total", 0)))
                if total:
                    self.progress.setRange(0, 1000)
                    self.progress.setValue(min(1000, int(current / total * 1000)))
                else:
                    self.progress.setRange(0, 0)
            except (TypeError, ValueError):
                pass
        if kind == "state":
            self._translate_runtime()

    def _update_stats(self, event: dict) -> None:
        for key in self.total_stats:
            if key in event:
                try:
                    self.total_stats[key] = max(0, int(event[key]))
                except (ValueError, TypeError):
                    pass
        for key, label in self.stat_labels.items():
            label.setText(f"{self.total_stats[key]:,}".replace(",", " "))

    def _item_key(self, data: dict) -> str:
        return str(data.get("key") or data.get("media_id") or data.get("id") or data.get("path") or data.get("url") or (str(data.get("post_id", "")) + ":" + str(data.get("num", data.get("index", "")))))

    def _add_item(self, data: dict) -> None:
        key = self._item_key(data)
        if not key:
            key = uuid.uuid4().hex
        existing = self.media_items.get(key)
        if existing is None:
            # Keep the native list responsive for very large galleries. The full
            # count and manifest remain in SQLite, independent from this preview.
            if self.gallery.count() >= 800:
                if self.gallery.count() == 800:
                    set_translated_text(self.gallery_note, "Показаны первые 800 карточек. Полный результат и контрольные точки сохранены в коллекции.")
                return
            item = QListWidgetItem()
            item.setSizeHint(QSize(self.gallery.gridSize().width() - 14, self.gallery.iconSize().height() + 64))
            self.media_items[key] = item
            self.gallery.addItem(item)
        else:
            item = existing
            previous = item.data(Qt.ItemDataRole.UserRole) or {}
            data = {**previous, **data}
        item.setData(Qt.ItemDataRole.UserRole, data)
        path = str(data.get("path") or "")
        post_id = str(data.get("post_id") or "")
        pixmap = QPixmap(path) if path and Path(path).is_file() else QPixmap()
        if not pixmap.isNull():
            item.setData(Qt.ItemDataRole.UserRole + 1, True)
            preview = pixmap.scaled(384, 216, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            item.setIcon(QIcon(preview))
            item.setText(Path(path).name + "\n" + tr("Сохранено"))
            item.setToolTip(path)
        else:
            item.setData(Qt.ItemDataRole.UserRole + 1, False)
            if not hasattr(self, "_placeholder_icon"):
                self._placeholder_icon = self._make_placeholder_icon()
            item.setIcon(self._placeholder_icon)
            item.setText((tr("Пост {post_id}").format(post_id=post_id[-18:]) if post_id else tr("Изображение автора")) + "\n" + tr("Без локального превью"))
            item.setToolTip(tr("Оригинал ещё не сохранён. Во время подсчёта картинки не скачиваются."))
        self.empty_note.hide()

    def _selection_changed(self) -> None:
        self.open_post.setEnabled(bool(self.gallery.selectedItems()))

    def _open_image(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        path = str(data.get("path") or "")
        if path and Path(path).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))

    def _open_selected_post(self) -> None:
        selected = self.gallery.selectedItems()
        if not selected:
            return
        data = selected[0].data(Qt.ItemDataRole.UserRole) or {}
        platform = str(data.get("platform", "x"))
        post = str(data.get("post_id") or "")
        if post.isdigit():
            link = f"https://www.pixiv.net/artworks/{post}" if platform == "pixiv" else f"https://x.com/i/status/{post}"
            QDesktopServices.openUrl(QUrl(link))

    def _open_destination(self) -> None:
        path = Path(self.destination.text().strip() or _default_destination())
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
        else:
            set_translated_text(self.status_text, "Папка будет создана при запуске задания.")

    def _send(self, command: str) -> None:
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.write((json.dumps({"command": command}) + "\n").encode("utf-8"))

    def _pause_resume(self) -> None:
        if self.worker_state == "paused":
            self._send("resume")
            set_translated_text(self.status_text, "Продолжаем задание…")
        else:
            self._send("pause")
            set_translated_text(self.status_text, "Пауза будет применена после текущей операции…")

    def _stop(self) -> None:
        self._send("stop")
        set_translated_text(self.status_text, "Завершаем текущую операцию и сохраняем контрольную точку…")
        self.stop_button.setEnabled(False)
        self.pause_button.setEnabled(False)

    def _worker_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.last_terminal_state = "error"
            self._inline_error("Не удалось запустить обработчик. Проверьте комплектность приложения и доступ к каталогу.")
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self._set_active(False)
            if self.closing:
                QTimer.singleShot(0, self.close)

    def _worker_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._read_stdout()
        if self.stdout_buffer.strip():
            try:
                event = json.loads(self.stdout_buffer.decode("utf-8-sig"))
                if isinstance(event, dict):
                    self._event(event)
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        self.stdout_buffer = b""
        if not self.last_terminal_state:
            self.last_terminal_state = "error" if exit_code else "stopped"
            set_translated_text(self.status_text, "Обработчик завершил работу. Состояние доступно в истории заданий.")
            if exit_code:
                self._append_log("error", f"Обработчик завершился с кодом {exit_code}. Контрольная точка хранится в коллекции.")
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
        self._set_active(False)
        self._refresh_history()
        if not self.gallery.count():
            set_translated_text(self.empty_note, "В выбранном диапазоне пока нет карточек.\nПроверьте журнал, доступ к профилю и выбранные даты.")
        if self.process:
            self.process.deleteLater()
            self.process = None
        if self.closing:
            QTimer.singleShot(0, self.close)

    def _with_store(self, operation):
        from .store import Store
        destination = self.destination.text().strip()
        if not destination or not (Path(destination) / ".mira" / "history.sqlite3").exists():
            return []
        store = Store(destination)
        try:
            return operation(store)
        finally:
            store.close()

    def _refresh_history(self) -> None:
        if self.active:
            return
        try:
            def read_history(store):
                store.recover_interrupted()
                return store.list_jobs(limit=40)
            self.jobs = [dict(row) for row in self._with_store(read_history)]
        except Exception:
            self.jobs = []
            self._append_log("warning", "Не удалось прочитать историю из выбранной коллекции.")
        self.history.setRowCount(len(self.jobs))
        for row, job in enumerate(self.jobs):
            profile = str(job.get("username") or job.get("profile_url") or "Задание")
            platform = str(job.get("platform") or "x").upper()
            mode_label = tr(" · подсчёт") if job.get("mode") == "preview" else ""
            values = [f"{platform} / {profile}{mode_label}", tr(STATUS_NAMES.get(str(job.get("status", "")), str(job.get("status", "")))),
                      str(job.get("found", 0)), str(job.get("downloaded", 0)), str(job.get("updated_at", ""))[:16].replace("T", " ")]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col in {2, 3}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(str(job.get("profile_url", "")))
                self.history.setItem(row, col, item)
            self.history.setRowHeight(row, 42)
        self._history_selection_changed()

    def _load_recent(self) -> None:
        if self.active:
            return
        try:
            rows = self._with_store(lambda store: store.recent_files(limit=120))
        except Exception:
            return
        self.gallery.clear()
        self.media_items.clear()
        for row in rows:
            self._add_item(dict(row))
        self.empty_note.setVisible(self.gallery.count() == 0)

    def _history_selection_changed(self) -> None:
        selected = bool(self.history.selectionModel().selectedRows())
        self.load_job.setEnabled(selected and not self.active)
        self.resume_job.setEnabled(selected and not self.active)

    def _restore_job(self, resume: bool) -> None:
        selected = self.history.selectionModel().selectedRows()
        if not selected or self.active:
            return
        job = self.jobs[selected[0].row()]
        self.profile.setText(str(job.get("profile_url", "")))
        self.only_new.setChecked(bool(job.get("only_new", True)))
        self.pixiv.setChecked(str(job.get("platform", "")).lower() == "pixiv")
        for key, checkbox, edit in (("date_from", self.from_enabled, self.date_from), ("date_to", self.to_enabled, self.date_to)):
            date = QDate.fromString(str(job.get(key) or ""), "yyyy-MM-dd")
            checkbox.setChecked(date.isValid())
            if date.isValid():
                edit.setDate(date)
        self._update_stats(job)
        self._apply_platform(str(job.get("platform", "x")))
        self._update_date_button()
        set_translated_text(self.status_text, "Настройки задания восстановлены. Проверьте сохранённый вход X или выбранный дополнительный способ авторизации.")
        if resume:
            self._start(str(job.get("mode") or "download"), str(job.get("id") or ""))

    def _show_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Как пользоваться Mira")
        dialog.resize(690, 680)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 22)
        _dialog_header(dialog, layout, "Ваша коллекция, под вашим контролем")
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet("QTextBrowser { border:none; background:transparent; font-size:10pt; }")
        help_source = """
        <style>p,li{line-height:1.5}h3{margin-top:20px}a{text-decoration:underline}</style>
        <h3>1. Найдите автора</h3>
        <p>Вставьте ссылку на профиль X / Twitter, например https://x.com/username.
        Выберите папку хранения. Кнопка <b>Все даты</b> открывает фильтр публикаций:
        можно выбрать весь период, начало, конец или обе границы. «Применить» сохраняет выбор,
        «Отмена» оставляет прежний диапазон. Границы включительно, даты в UTC.</p>
        <p>Переключатели <b>X</b> и <b>Pixiv</b> находятся над папкой хранения.
        Вставленная ссылка автоматически выбирает платформу; явное переключение удаляет
        несовпадающую ссылку. Для Pixiv используйте https://www.pixiv.net/users/123.
        Pixiv остаётся экспериментальным источником; отдельного разрешающего флажка нет.</p>
        <h3>2. Посчитайте или скачайте</h3>
        <p><b>Найти и скачать</b> за один запуск находит доступные изображения, считает их и
        сохраняет их по мере обнаружения. Предварительный подсчёт не требуется.</p>
        <p><b>Найти и посчитать</b> — отдельный необязательный просмотр без скачивания оригиналов.
        Счётчик «Найдено изображений» увеличивается во время поиска; окончательное
        количество известно только после завершения. Каждая картинка поста учитывается отдельно.
        Во время подсчёта миниатюры доступны только для файлов, уже сохранённых локально.</p>
        <p>Скачивание сохраняет лучшее доступное разрешение в папки
        <b>X\\ID автора\\</b> (или <b>Pixiv\\ID автора\\</b>) внутри выбранной папки.
        Идентификатор сохраняет одну папку при переименовании профиля.
        Видеофайлы не скачиваются. «Скачать только новые»
        использует локальную историю. Физические дубликаты выявляются по содержимому.</p>
        <h3>3. Войти в X или Pixiv прямо в Mira</h3>
        <p>Вставьте ссылку автора: кнопка входа выберет платформу по ссылке.
        Нажмите <b>Войти в X</b> или <b>Войти в Pixiv</b>. Откроется официальная страница платформы; адрес виден над ней.
        Вводите имя пользователя, пароль и коды только в страницу сайта. Завершите проверки X,
        затем нажмите <b>Сохранить вход</b>. Для Pixiv одной гостевой сессии недостаточно:
        дождитесь автоматической проверки или нажмите <b>Проверить вход</b>.
        Mira проверяет аккаунт обычным запросом к Pixiv, в том числе на английской странице
        и в настройках; содержимое форм не читается. При сохранении проверка повторяется.
        Mira сохраняет только сессию в зашифрованном виде
        средствами Windows для текущего пользователя. Пароль приложение не читает и не сохраняет.</p>
        <p>Встроенное окно использует временный профиль без сохранения истории и браузерного кеша на диск.
        <b>Отмена</b> удаляет новую временную сессию и оставляет прежний сохранённый вход.
        <b>Выйти из X</b> или <b>Выйти из Pixiv</b> удаляет только локальный вход выбранной платформы.
        Сессии X и Pixiv независимы; другие сеансы аккаунтов остаются активны.
        Для их отзыва используйте настройки сеансов на самом сайте.</p>
        <p>Внешние страницы входа Google и Apple заблокированы; используйте обычный вход по имени пользователя X.
        Ключи доступа Windows Hello во встроенном окне не поддерживаются; используйте пароль и самостоятельно
        выполните обязательные проверки и двухфакторную авторизацию на сайте.
        Сайт может ограничить встроенные окна. Проверки выполняйте самостоятельно; Mira их не обходит.
        Если этот способ недоступен, выберите дополнительный способ ниже.</p>
        <p><b>Для Pixiv сначала настройте аккаунт для показа нужного контента.</b>
        Откройте <b>Настройки показа</b> в окне входа или
        <a href="https://www.pixiv.net/settings/viewing">официальные настройки Pixiv</a> в браузере с тем же аккаунтом.
        Настройки меняете вы вручную. Mira учитывает доступ аккаунта и не гарантирует показ или скачивание всего контента.
        После просмотра настроек нажмите <b>Проверить вход</b> и <b>Сохранить вход</b>.
        Для запуска выберите Pixiv или вставьте ссылку на автора Pixiv.</p>
        <h3>Дополнительные способы входа</h3>
        <p>Откройте <b>Дополнительно</b>. Здесь находятся способ входа, удаление сохранённого входа
        и интервал запросов. Выберите <b>Из браузера</b>, затем браузер и профиль, в котором вы самостоятельно
        вошли в X. Нажмите <b>Обновить</b>, если только что создали профиль. Список профилей
        содержит только их имена и каталоги; cookies читаются локально после нажатия
        <b>Найти и посчитать</b> или <b>Найти и скачать</b>. Расширение и ручной экспорт не нужны.</p>
        <p>Рекомендуется <b>Firefox</b> с обычной сессией профиля. Вход в отдельном контейнере
        Firefox не поддерживается. Защита Windows в Chrome, Edge и Brave может не разрешить
        чтение сессии. Приложение покажет причину; обход защиты и автоматический переход
        к работе без входа не выполняются. Можно использовать Firefox или выбрать
        <b>Из файла cookies.txt</b> и собственный файл Netscape. Храните такой файл как пароль.
        <b>Без авторизации</b> включается только вручную; X обычно требует входа.</p>
        <p>Пароль вводится только в официальный сайт X. Mira не передаёт сессию сторонним службам и не
        сохраняет их содержимое в настройках или журнале. Cookies используются только
        для запросов к соответствующей платформе. Выбор браузера и профиля запоминается,
        путь к файлу cookies — только до закрытия приложения.</p>
        <h3>Пауза и продолжение</h3>
        <p>Пауза и остановка применяются после текущей операции. Состояние задания
        сохраняется в каталоге коллекции. Для продолжения выберите задание в «Истории»
        и нажмите «Продолжить задание». Проверьте сохранённый вход; если используется файл,
        при необходимости выберите его заново.
        Превью и скачивание — отдельные задания.</p>
        <h3>Доступ и ограничения</h3>
        <p>Используйте материалы в рамках ваших прав и правил платформы. Приложение
        не обходит ограничения доступа. Закрытые, удалённые, ограниченные по региону
        или скрытые платформой публикации могут быть недоступны. Платформа может
        показывать неполную историю даже после успешного входа, поэтому «все медиа»
        не гарантируются. Фильтр дат не снимает ограничения платформы.</p>
        <p>При ограничении запросов приложение делает паузу или сообщает об ошибке.
        Увеличьте интервал запросов и попробуйте позже. Не запускайте множество
        одновременных заданий. X и Pixiv могут менять интерфейсы и правила, что
        потребует обновления gallery-dl.</p>
        <h3>Где находятся данные</h3>
        <p>Картинки: выбранная папка → платформа → числовой ID автора. История, контрольные точки
        и журнал: скрытая служебная папка <b>.mira</b> внутри коллекции. Не удаляйте
        её, если хотите сохранять историю и продолжать задания.</p>
        """
        browser.setHtml(f'<style>a{{color:{colors()["link"]};}}</style>' + localized_help_html(help_source))
        layout.addWidget(browser, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton("Понятно")
        close.setObjectName("primary")
        close.clicked.connect(dialog.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        translate_widget_tree(dialog)
        dialog.exec()

    def closeEvent(self, event) -> None:
        self._save_preferences()
        if self.active and self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            event.ignore()
            if not self.closing:
                self.closing = True
                self._stop()
                set_translated_text(self.status_text, "Сохраняем состояние")
                QTimer.singleShot(7000, self._close_timeout)
            return
        event.accept()

    def _close_timeout(self) -> None:
        if not self.closing or not self.active or not self.process:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Завершение задания"))
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 20)
        _dialog_header(dialog, layout, "Завершение задания", resizable=False)
        layout.addWidget(_label(tr("Текущая операция ещё завершается. Подождать её окончания?\n\n"
                                  "Если выбрать «Нет», обработчик будет закрыт принудительно. Уже сохранённые контрольные точки останутся, текущий файл может потребовать повторного скачивания."), wrap=True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        wait = [True]
        buttons.button(QDialogButtonBox.StandardButton.Yes).clicked.connect(dialog.accept)
        buttons.button(QDialogButtonBox.StandardButton.No).clicked.connect(lambda: (wait.__setitem__(0, False), dialog.reject()))
        layout.addWidget(buttons)
        translate_widget_tree(dialog)
        dialog.exec()
        dialog.deleteLater()
        if wait[0]:
            QTimer.singleShot(7000, self._close_timeout)
        elif self.process:
            self.process.kill()


def run_gui(screenshot: str = "") -> int:
    from .app_identity import set_windows_app_id
    set_windows_app_id()
    from .webengine_runtime import configure_login_runtime
    configure_login_runtime()
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    application = QApplication.instance() or QApplication(sys.argv)
    apply_app_icon(application)
    application.setApplicationName(APP_NAME)
    application.setOrganizationName("Mira")
    application.setStyle("Fusion")
    from .window_chrome import install_dialog_chrome_hook
    install_dialog_chrome_hook(application)
    window = MainWindow()
    from .startup import watch_first_paint
    watch_first_paint(window)
    window.show()
    if screenshot:
        def capture() -> None:
            target = Path(screenshot).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(target))
            application.quit()
        QTimer.singleShot(1200, capture)
    return application.exec()
