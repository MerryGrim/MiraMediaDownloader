"""Offline live-caption translation contracts; never read actual preferences."""

import ast
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate, QLocale, Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QPushButton,
                              QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from mira_media import localization as loc
from mira_media.date_filter import DateFilterDialog, range_label


@pytest.fixture(scope="module")
def app():
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def reset_language(app):
    original = loc.get_language()
    loc.set_language("ru")
    yield
    loc.set_language(original)


@pytest.mark.parametrize("language,expected", [("ru", "Найти и скачать"), ("en", "Find and download"),
                                              ("zh_CN", "查找并下载")])
def test_primary_captions_and_local_qt_locale(language, expected):
    loc.set_language(language)
    assert loc.get_language() == language and loc.tr("Найти и скачать") == expected
    assert QLocale().name() == {"ru": "ru_RU", "en": "en_US", "zh_CN": "zh_CN"}[language]
    assert loc.calendar_locale_name() == QLocale().name()


def test_unknown_language_rejected_without_changing_current_language():
    with pytest.raises(ValueError):
        loc.set_language("unknown")
    assert loc.get_language() == "ru"


def test_bundled_qtbase_translates_common_native_dialog_buttons(app):
    for language, expected in (("ru", "Отмена"), ("en", "Cancel"), ("zh_CN", "取消")):
        loc.set_language(language)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        assert buttons.button(QDialogButtonBox.StandardButton.Cancel).text().replace("&", "") == expected
        buttons.deleteLater()


@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_static_native_widget_captions_in_current_sources_have_catalog_coverage(language):
    loc.set_language(language)
    folder = Path(loc.__file__).parent
    displayed_calls = {"_label", "QLabel", "QPushButton", "QCheckBox", "QRadioButton", "setText",
                       "setToolTip", "setPlaceholderText", "setWindowTitle", "setAccessibleName",
                       "tr", "set_translated_text"}
    missing = []
    for name in ("ui.py", "login.py", "date_filter.py"):
        for node in ast.walk(ast.parse((folder / name).read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if called not in displayed_calls:
                continue
            for value in node.args:
                if (isinstance(value, ast.Constant) and isinstance(value.value, str)
                        and any("\u0400" <= char <= "\u04ff" for char in value.value)
                        and len(value.value) < 1500 and loc.tr(value.value) == value.value):
                    missing.append((name, node.lineno, value.value))
    assert missing == []


def test_dynamic_engine_counts_platform_and_nested_error_keep_values():
    message = "Доступный обход завершён · найдено изображений: 24017"
    loc.set_language("en")
    assert loc.tr(message) == "Search completed · images found: 24017"
    assert loc.tr("Поиск завершён · найдено изображений: 24017") == loc.tr(message)
    assert loc.tr("Войти в Pixiv") == "Sign in to Pixiv"
    nested = loc.tr("Пост 12345, изображение 7: Не удалось загрузить изображение.")
    assert nested == "Post 12345, image 7: Could not download the image."
    loc.set_language("zh_CN")
    chinese = loc.tr(message)
    assert "24017" in chinese and "找到图片" in chinese
    assert loc.tr("Пост {post_id}").format(post_id="931100") == "帖子 931100"
    result = loc.translate_message({"type": "state", "count": 24017, "messages": [message]})
    assert result["type"] == "state" and result["count"] == 24017
    assert result["messages"] == [chinese]
    website_error = "REMOTE_GENERATED untranslated website response 123"
    assert loc.tr(website_error) == website_error


@pytest.mark.parametrize("language,expected", [
    ("ru", "Поиск завершён · найдено изображений: 24017"),
    ("en", "Search completed · images found: 24017"),
    ("zh_CN", "查找完成 · 找到图片：24017"),
])
def test_legacy_worker_history_wording_uses_current_search_captions(language, expected):
    loc.set_language(language)
    for stored in ("Доступный обход завершён · найдено изображений: 24017",
                   "Accessible scan completed · images found: 24017",
                   "可访问内容扫描完成 · 找到图片：24017"):
        assert loc.tr(stored) == expected
    assert "24017" in expected


def test_old_scanning_caption_cycles_to_current_plain_wording(app):
    label = QLabel("Обход медиагалереи")
    for language, expected in (("en", "Searching for images"), ("zh_CN", "正在查找图片"),
                               ("ru", "Поиск изображений")):
        loc.set_language(language)
        loc.translate_widget_tree(label)
        assert label.text() == expected
        assert label.property("_mira_i18n_source_text") == "Поиск изображений"


def test_widget_tree_live_cycle_and_new_dynamic_source_preserve_caption_origin(app):
    root = QWidget()
    label = QLabel("Скачивание", root)
    button = QPushButton("Пауза", root)
    root.setWindowTitle("Период загрузки")
    for language, label_text, button_text in [("en", "Downloading", "Pause"), ("zh_CN", "正在下载", "暂停"),
                                               ("ru", "Скачивание", "Пауза")]:
        loc.set_language(language)
        loc.translate_widget_tree(root)
        assert label.text() == label_text and button.text() == button_text
        assert label.property("_mira_i18n_source_text") == "Скачивание"
    loc.set_language("en")
    label.setText("На паузе")
    loc.translate_widget_tree(root)
    assert label.text() == "Paused"
    assert label.property("_mira_i18n_source_text") == "На паузе"
    loc.set_language("zh_CN")
    loc.translate_widget_tree(root)
    assert label.text() == "已暂停"
    root.deleteLater()


def test_explicit_dynamic_setter_retranslates_without_losing_russian_source(app):
    label = QLabel()
    loc.set_language("en")
    loc.set_translated_text(label, "Подключаем сохранённый вход Pixiv")
    assert label.text() == "Restoring saved Pixiv sign-in"
    loc.set_language("zh_CN")
    loc.translate_widget_tree(label)
    assert "Pixiv" in label.text() and "正在恢复" in label.text()
    loc.set_language("ru")
    loc.translate_widget_tree(label)
    assert label.text() == "Подключаем сохранённый вход Pixiv"
    label.deleteLater()


def test_editable_urls_paths_and_log_documents_never_translated(app):
    root = QWidget()
    url = QLineEdit("https://example.test/Помощь/Журнал", root)
    path = QLineEdit("D:/Мои картинки/Скачивание", root)
    exact_user_input = QLineEdit("Помощь", root)
    url.setPlaceholderText("Вставьте ссылку на профиль автора.")
    path.setToolTip("Выбрать")
    log = QTextEdit(root)
    log.setPlainText("Пауза\nGENERATED-private-log-data")
    log.setPlaceholderText("Ошибки и важные события появятся здесь. Текст можно выделить и скопировать.")
    loc.set_language("zh_CN")
    loc.translate_widget_tree(root)
    assert url.text() == "https://example.test/Помощь/Журнал"
    assert path.text() == "D:/Мои картинки/Скачивание" and exact_user_input.text() == "Помощь"
    assert url.placeholderText() == "请粘贴作者主页链接。" and path.toolTip() == "选择"
    assert log.toPlainText() == "Пауза\nGENERATED-private-log-data"
    assert "错误" in log.placeholderText()
    root.deleteLater()


def test_combo_tab_header_and_status_translation_preserves_item_data_and_author(app):
    root = QWidget()
    combo = QComboBox(root)
    combo.addItem("Из браузера", {"mode": "browser", "id": "GENERATED-stable"})
    tabs = QTabWidget(root)
    tabs.addTab(QWidget(), "Картинки")
    tabs.addTab(QWidget(), "История")
    table = QTableWidget(1, 2, root)
    table.setHorizontalHeaderLabels(["Автор", "Статус"])
    table.setItem(0, 0, QTableWidgetItem("Готово"))  # This is the creator's name.
    status = QTableWidgetItem("Готово")
    status.setData(Qt.ItemDataRole.UserRole, "GENERATED-job-id")
    table.setItem(0, 1, status)
    loc.set_language("en")
    loc.translate_widget_tree(root)
    assert combo.itemText(0) == "From browser"
    assert combo.itemData(0) == {"mode": "browser", "id": "GENERATED-stable"}
    assert tabs.tabText(0) == "Images" and tabs.tabText(1) == "History"
    assert table.horizontalHeaderItem(0).text() == "Creator"
    assert table.item(0, 0).text() == "Готово" and status.text() == "Done"
    assert status.data(Qt.ItemDataRole.UserRole) == "GENERATED-job-id"
    loc.set_language("ru")
    loc.translate_widget_tree(root)
    assert combo.itemText(0) == "Из браузера" and status.text() == "Готово"
    root.deleteLater()


def test_calendar_locale_and_period_labels_follow_language_without_changing_iso_bounds(app):
    dialog = DateFilterDialog(date_from="2026-10-14", date_to="2026-10-31")
    dialog.show()
    dialog.date_from.click()
    app.processEvents()
    calendar = dialog.date_from.popup.calendar
    for language, locale_name, all_dates in [("en", "en_US", "All dates"), ("zh_CN", "zh_CN", "所有日期"),
                                            ("ru", "ru_RU", "Все даты")]:
        loc.set_language(language)
        loc.translate_widget_tree(dialog)
        assert calendar.locale().name() == locale_name
        assert dialog.selected_range() == ("2026-10-14", "2026-10-31")
        assert range_label("", "") == all_dates
    loc.set_language("en")
    assert range_label("2026-10-14", "") == "From 14.10.2026"
    loc.set_language("zh_CN")
    assert range_label("", "2026-10-31") == "至 31.10.2026"
    dialog.reject()
    dialog.deleteLater()


@pytest.mark.parametrize("language", ["en", "zh_CN"])
def test_help_is_fully_localized_and_preserves_official_urls(language):
    loc.set_language(language)
    help_html = loc.localized_help_html("<p>Русская исходная справка</p>")
    assert not any("\u0400" <= char <= "\u04ff" for char in help_html)
    assert "https://www.pixiv.net/settings/viewing" in help_html
    assert "UTC" in help_html and ".mira" in help_html
    loc.set_language("ru")
    assert loc.localized_help_html("<p>Исходная справка</p>") == "<p>Исходная справка</p>"
