"""Native UI contracts. These tests never contact a platform or load cookies."""
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QDialog, QFileDialog

from mira_media.adapters.profiles import parse_profile
from mira_media.models import JobOptions
from mira_media.store import Store
from mira_media.ui import MainWindow, STYLE


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    application = QApplication.instance() or QApplication([])
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE)
    previous_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("ui-settings")))
    yield application
    QSettings.setDefaultFormat(previous_format)


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    # Profile discovery is metadata-only; no test touches a real browser session.
    from mira_media import browser_auth, session_vault
    monkeypatch.setattr(session_vault, "has_x_session", lambda: False)
    monkeypatch.setattr(session_vault, "has_session", lambda platform: False)
    profiles = [SimpleNamespace(browser="firefox", profile_id="test-profile-id",
                                label="Default test profile", path=tmp_path / "profile")]
    monkeypatch.setattr(browser_auth, "discover_profiles", lambda browser: profiles)
    settings = QSettings("Mira", "MiraMediaDownloader")
    settings.clear()
    settings.setValue("destination", str(tmp_path / "chosen-collection"))
    widget = MainWindow()
    widget.auth_source.setCurrentIndex(widget.auth_source.findData("browser"))
    widget.destination.setText(str(tmp_path / "chosen-collection"))
    widget.profile.setText("https://twitter.com/NASA?s=20")
    widget.cookies.clear()
    widget.from_enabled.setChecked(False)
    widget.to_enabled.setChecked(False)
    widget.show()
    app.processEvents()
    yield widget
    widget._set_active(False)
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_options_share_worker_profile_validation_and_explicit_folder(window, tmp_path):
    options = window._validated_options("preview")
    assert options["profile_url"] == parse_profile("https://twitter.com/NASA").url
    assert options["destination"] == str((tmp_path / "chosen-collection").resolve())
    assert options["cookies_file"] == options["date_from"] == options["date_to"] == ""
    assert options["auth_source"] == "browser"
    assert options["browser"] == "firefox"
    assert options["browser_profile"] == "test-profile-id"
    assert options["mode"] == "preview"
    assert window.destination_pick.text() == "Выбрать"
    window.profile.setText("https://x.com/NASA/status/123")
    assert window._validated_options("preview") is None


def test_counter_and_discovery_to_local_preview_share_identity(window, tmp_path):
    window._event({"type": "stats", "found": 12, "downloaded": 2, "skipped": 1, "failed": 0})
    assert window.stat_labels["found"].text() == "12"
    window._event({"type": "item", "key": "x:one", "post_id": "123", "index": 1})
    original = window.gallery.item(0)
    assert window.gallery.count() == 1
    image_path = tmp_path / "local.png"
    image = QPixmap(30, 20)
    image.fill(QColor("#bea1d8"))
    assert image.save(str(image_path))
    window._event({"type": "item", "key": "x:one", "post_id": "123", "path": str(image_path)})
    assert window.gallery.count() == 1
    assert window.gallery.item(0) is original
    assert "Сохранено" in original.text()
    assert window.stat_labels["found"].text() == "12"


def test_gallery_renders_filename_and_saved_status_on_two_lines(window, app, tmp_path):
    path = tmp_path / "900000_01.png"
    image = QPixmap(720, 460)
    image.fill(QColor("#ffffff"))
    assert image.save(str(path))
    window._add_item({"key": "caption", "path": str(path)})
    app.processEvents()
    card = window.gallery.visualItemRect(window.gallery.item(0))
    rendered = window.gallery.viewport().grab(card).toImage()
    scale = rendered.devicePixelRatio()
    # A white source image isolates the two native caption lines. The previous
    # IconMode delegate collapsed both lines into one ellipsized filename.
    occupied_rows = []
    for y in range(max(0, rendered.height() - int(62 * scale)), rendered.height()):
        dark = sum(max(rendered.pixelColor(x, y).red(), rendered.pixelColor(x, y).green(),
                       rendered.pixelColor(x, y).blue()) < 175 for x in range(rendered.width()))
        if dark >= 3:
            occupied_rows.append(y)
    groups = sum(index == 0 or row > occupied_rows[index - 1] + 1
                 for index, row in enumerate(occupied_rows))
    assert groups >= 2
    assert window.gallery.item(0).text() == "900000_01.png\nСохранено"


def test_request_interval_has_comfortable_clamped_buttons(window, app):
    assert window.request_delay.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
    for button in (window.request_delay_minus, window.request_delay_plus):
        assert button.width() >= 36 and button.height() >= 36
    window.request_delay.setValue(3.0)
    window.request_delay_plus.click()
    assert window.request_delay.value() == 3.5
    window.request_delay_minus.click()
    assert window.request_delay.value() == 3.0
    for value, button in ((2.0, window.request_delay_minus), (120.0, window.request_delay_plus)):
        window.request_delay.setValue(value)
        button.click()
        assert window.request_delay.value() == value
    window.advanced_dialog.show()
    app.processEvents()
    editor = window.request_delay.lineEdit()
    assert editor.width() >= editor.fontMetrics().horizontalAdvance(editor.text()) + 4
    rendered = editor.grab().toImage()
    assert sum(max(rendered.pixelColor(x, y).red(), rendered.pixelColor(x, y).green(),
                   rendered.pixelColor(x, y).blue()) < 150
               for x in range(rendered.width()) for y in range(rendered.height())) > 8
    window.advanced_dialog.hide()
    window._set_active(True)
    assert not window.request_delay_minus.isEnabled()
    assert not window.request_delay_plus.isEnabled()


def test_pause_partial_and_compact_actions(window, app):
    window._set_active(True)
    window._event({"type": "state", "state": "paused", "message": "На паузе"})
    assert window.pause_button.text() == "Продолжить"
    assert not window.profile.isEnabled()
    assert not window.auth_source.isEnabled()
    assert not window.browser.isEnabled()
    assert not window.browser_profile.isEnabled()
    assert not window.browser_refresh.isEnabled()
    window._event({"type": "state", "state": "partial", "message": "Не все файлы скачаны"})
    assert window.last_terminal_state == "partial"
    assert window.status_text.text() == "Не все файлы скачаны"
    assert not window.stop_button.isEnabled()
    window._set_active(False)
    window.resize(1020, 720)
    app.processEvents()
    bottom = window.download_button.mapTo(window.centralWidget(), window.download_button.rect().bottomLeft())
    assert bottom.y() < window.centralWidget().height()
    assert window.download_button.isVisible()


def test_history_resume_keeps_job_identity_and_does_not_persist_cookie_path(window, tmp_path, monkeypatch):
    destination = Path(window.destination.text())
    profile = parse_profile("https://x.com/NASA")
    options = JobOptions(profile_url=profile.url, destination=str(destination))
    store = Store(destination)
    job_id = store.start_job(profile, options)
    store.set_status(job_id, "stopped")
    store.close()
    window._refresh_history()
    assert window.history.rowCount() == 1
    window.history.selectRow(0)
    calls = []
    monkeypatch.setattr(window, "_start", lambda mode, job_id="": calls.append((mode, job_id)))
    window._restore_job(True)
    assert calls == [("download", job_id)]
    cookie_path = str(tmp_path / "sensitive-cookies.txt")
    window.cookies.setText(cookie_path)
    window._save_preferences()
    saved = [str(window.settings.value(key)) for key in window.settings.allKeys()]
    assert cookie_path not in saved


def test_gallery_and_event_log_are_bounded_independently_of_count(window, monkeypatch):
    # Reuse a tiny placeholder to keep this stress contract fast.
    for index in range(810):
        window._event({"type": "item", "key": f"x:{index}", "post_id": str(index)})
    window._event({"type": "stats", "found": 10000, "downloaded": 7000})
    assert window.gallery.count() == 800
    assert window.stat_labels["found"].text() == "10 000"
    assert "800" in window.gallery_note.text()
    for index in range(1010):
        window._append_log("info", f"Event {index}")
    assert window.log.document().blockCount() <= 1000


def test_browser_source_does_not_need_cookie_file_or_start_an_import(window, monkeypatch, tmp_path):
    from mira_media import browser_auth
    def forbidden(*args, **kwargs):
        raise AssertionError("UI must never import private cookies")
    if hasattr(browser_auth, "load_browser_cookies"):
        monkeypatch.setattr(browser_auth, "load_browser_cookies", forbidden)
    window.cookies.setText(str(tmp_path / "missing.txt"))
    options = window._validated_options("download")
    assert options["auth_source"] == "browser"
    assert options["cookies_file"] == ""
    assert not window.browser_fields.isHidden()
    assert window.file_fields.isHidden()
    assert not window.advanced_dialog.isVisible()


def test_file_validation_is_conditional_and_explicit(window, tmp_path):
    window.auth_source.setCurrentIndex(window.auth_source.findData("file"))
    assert not window.file_fields.isHidden()
    assert window.browser_fields.isHidden()
    assert window._validated_options("preview") is None
    file = tmp_path / "own-cookies.txt"
    file.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    window.cookies.setText(str(file))
    options = window._validated_options("preview")
    assert options["auth_source"] == "file"
    assert options["cookies_file"] == str(file)
    assert options["browser"] == options["browser_profile"] == ""
    window.auth_source.setCurrentIndex(window.auth_source.findData("none"))
    file.unlink()
    options = window._validated_options("preview")
    assert options["auth_source"] == "none"
    assert options["cookies_file"] == ""


def test_profile_refresh_keeps_source_and_reports_unavailable_profile(window, monkeypatch, tmp_path):
    from mira_media import browser_auth
    calls = []
    monkeypatch.setattr(browser_auth, "discover_profiles", lambda browser: calls.append(browser) or [])
    window._refresh_browser_profiles()
    assert calls == ["firefox"]
    assert window.auth_source.currentData() == "browser"
    assert window.browser_profile.currentData() == ""
    assert "недоступен" in window.browser_status.text()
    assert window._validated_options("preview") is None
    assert window.auth_source.currentData() == "browser"
    monkeypatch.setattr(browser_auth, "discover_profiles", lambda browser: [
        SimpleNamespace(browser=browser, profile_id="new-profile", label="New", path=tmp_path / "new")])
    window._refresh_browser_profiles()
    assert window.browser_profile.currentData() == "new-profile"
    assert window._validated_options("preview")["browser_profile"] == "new-profile"
    window._refresh_browser_profiles("removed-profile")
    assert window.browser_profile.currentData() == ""
    assert window.browser_profile.isEnabled()
    assert window._validated_options("preview") is None


def test_browser_preferences_store_only_selected_metadata(window, tmp_path):
    cookie_path = str(tmp_path / "private-cookies.txt")
    window.cookies.setText(cookie_path)
    window._save_preferences()
    assert window.settings.value("auth_source") == "browser"
    assert window.settings.value("browser") == "firefox"
    assert window.settings.value("browser_profile") == "test-profile-id"
    saved = {key: str(window.settings.value(key)) for key in window.settings.allKeys()}
    assert cookie_path not in saved.values()
    assert "cookies_file" not in saved
    assert not any(key in saved for key in ("auth_token", "ct0", "cookies", "cookie_values"))


def test_clean_default_is_embedded_with_prominent_login(app, tmp_path, monkeypatch):
    from mira_media import session_vault, browser_auth
    monkeypatch.setattr(session_vault, "has_x_session", lambda: False)
    monkeypatch.setattr(session_vault, "has_session", lambda platform: False)
    monkeypatch.setattr(browser_auth, "discover_profiles", lambda _: [])
    QSettings("Mira", "MiraMediaDownloader").clear()
    QSettings("Mira", "MiraMediaDownloader").setValue("destination", str(tmp_path / "clean-collection"))
    widget = MainWindow()
    assert widget.auth_source.currentData() == "embedded"
    assert widget.session_status.text() == "Вход не выполнен"
    assert widget.login_button.text() == "Войти в X"
    assert widget.login_button.isEnabled()
    assert not widget.logout_button.isEnabled()
    widget.close()
    widget.deleteLater()


def test_embedded_validation_needs_session_and_never_serializes_tokens(window, monkeypatch):
    from mira_media import session_vault
    window.auth_source.setCurrentIndex(window.auth_source.findData("embedded"))
    assert window._validated_options("download") is None
    assert "Войти в X" in window.status_text.text()
    monkeypatch.setattr(session_vault, "has_x_session", lambda: True)
    window._refresh_session_status()
    options = window._validated_options("download")
    assert options["auth_source"] == "embedded"
    assert options["cookies_file"] == options["browser"] == options["browser_profile"] == ""
    assert not any(key in options for key in ("auth_token", "ct0", "cookies", "user_agent"))
    assert window.session_status.text() == "Вход сохранён"
    window._set_active(True)
    assert not window.login_button.isEnabled()
    assert not window.logout_button.isEnabled()


def test_login_action_saves_source_and_logout_only_clears_own_vault(window, monkeypatch):
    from mira_media import login, session_vault
    saved = [False]
    monkeypatch.setattr(session_vault, "has_x_session", lambda: saved[0])
    def open_dialog(parent):
        assert parent is window
        saved[0] = True
        return True
    monkeypatch.setattr(login, "open_x_login", open_dialog)
    monkeypatch.setattr(session_vault, "clear_x_session", lambda: saved.__setitem__(0, False))
    window._login_x()
    assert window.auth_source.currentData() == "embedded"
    assert window.logout_button.isEnabled()
    window._logout_x()
    assert window.session_status.text() == "Вход не выполнен"
    assert "не завершает другие сеансы" in window.status_text.text()


def test_x_session_cannot_authorize_pixiv(window, monkeypatch):
    from mira_media import session_vault
    monkeypatch.setattr(session_vault, "has_x_session", lambda: True)
    monkeypatch.setattr(session_vault, "has_session", lambda platform: False)
    window.auth_source.setCurrentIndex(window.auth_source.findData("embedded"))
    window.pixiv.setChecked(True)
    window.profile.setText("https://www.pixiv.net/users/12345")
    assert window._validated_options("preview") is None
    assert "Войти в Pixiv" in window.status_text.text()


def test_pixiv_link_selects_own_login_without_changing_x_session(window, monkeypatch):
    from mira_media import login, session_vault
    sessions = {"x": True, "pixiv": False}
    monkeypatch.setattr(session_vault, "has_x_session", lambda: sessions["x"])
    monkeypatch.setattr(session_vault, "has_session", lambda platform: sessions[platform])
    calls = []
    def open_dialog(parent, platform):
        calls.append(platform)
        sessions[platform] = True
        return True
    monkeypatch.setattr(login, "open_login", open_dialog)
    monkeypatch.setattr(session_vault, "clear_session", lambda platform: sessions.__setitem__(platform, False))
    window.profile.setText("https://www.pixiv.net/users/20151243")
    assert window.login_button.text() == "Войти в Pixiv"
    assert window.logout_button.text() == "Выйти из Pixiv"
    assert window.session_status.text() == "Вход не выполнен"
    assert window.pixiv.isChecked()  # Choosing Pixiv is the explicit experimental-source selection.
    assert window.platform_pixiv_button.isChecked()
    assert window.pixiv.isHidden()
    assert "Сначала настройте аккаунт" in window.pixiv_login_hint.text()
    window._login_selected()
    assert calls == ["pixiv"]
    assert window.session_status.text() == "Вход сохранён"
    window.pixiv.setChecked(True)
    options = window._validated_options("download")
    assert options["auth_source"] == "embedded" and options["pixiv_enabled"]
    assert options["cookies_file"] == options["browser"] == options["browser_profile"] == ""
    window._logout_selected()
    assert sessions == {"x": True, "pixiv": False}
    window.profile.setText("https://x.com/NASA")
    assert window.login_button.text() == "Войти в X"
    assert window.session_status.text() == "Вход сохранён"


def test_combined_primary_action_starts_download_without_preview(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "_start", lambda mode: calls.append(mode))
    assert window.download_button.text() == "Найти и скачать"
    assert "Предварительный подсчёт не нужен" in window.download_button.toolTip()
    window.download_button.click()
    assert calls == ["download"]


def test_live_language_switch_preserves_active_job_and_private_inputs(window, app, tmp_path):
    profile, destination = window.profile.text(), window.destination.text()
    cookie_path = str(tmp_path / "test-only.cookies")
    window.cookies.setText(cookie_path)
    window.current_job_id = "synthetic-active-job"
    window._event({"type": "stats", "found": 12, "downloaded": 3})
    window._add_item({"key": "unresolved", "post_id": "12345"})
    window._append_log("info", "Задание запущено. Контрольные точки сохраняются автоматически.")
    window._set_active(True)
    window._event({"type": "state", "state": "paused", "message": "На паузе"})
    try:
        for code, button, paused in (("en", "Find and download", "Resume"),
                                      ("zh_CN", "查找并下载", "继续"),
                                      ("ru", "Найти и скачать", "Продолжить")):
            window.language_actions[code].trigger()
            app.processEvents()
            assert window.download_button.text() == button
            assert window.pause_button.text() == paused
            assert window.active and window.worker_state == "paused"
            assert window.current_job_id == "synthetic-active-job"
            assert window.profile.text() == profile
            assert window.destination.text() == destination
            assert window.cookies.text() == cookie_path
            assert window.stat_labels["found"].text() == "12"
            assert window.gallery.count() == 1
            assert window.language_button.isEnabled() and window.theme_button.isEnabled()
            assert not window.download_button.isEnabled()
        assert "Без локального превью" in window.gallery.item(0).text()
        assert "Задание запущено" in window.log.toPlainText()
        assert len(window._log_entries) == 1
    finally:
        window._change_language("ru")
        window._set_active(False)


def test_language_and_theme_persist_and_apply_to_a_new_window(window, app):
    from mira_media.localization import get_language
    from mira_media.themes import colors, get_theme
    from PySide6.QtGui import QPalette
    other = None
    try:
        window._change_language("en")
        window.theme_button.click()
        assert get_theme() == "dark"
        assert window.settings.value("ui_language") == "en"
        assert window.settings.value("ui_theme") == "dark"
        assert app.palette().color(QPalette.ColorRole.Window).name() == colors()["window"]
        other = MainWindow()
        assert get_language() == "en" and get_theme() == "dark"
        assert other.download_button.text() == "Find and download"
        assert other.language_button.text() == "EN"
        other._toggle_theme()
        assert get_theme() == "light"
        assert other.profile.text() == window.profile.text()
    finally:
        if other is not None:
            other.close()
            other.deleteLater()
        window._change_language("ru")
        if get_theme() != "light":
            window._toggle_theme()


def test_journal_language_replay_is_bounded_and_keeps_redaction(window):
    try:
        for _ in range(1005):
            window._append_log("error", "auth_token=synthetic-test-value")
        window._change_language("en")
        assert len(window._log_entries) == 1000
        assert "synthetic-test-value" not in window.log.toPlainText()
        assert "Error" in window.log.toPlainText()
        window._clear_log()
        window._change_language("zh_CN")
        assert not window._log_entries and not window.log.toPlainText()
    finally:
        window._change_language("ru")


def test_main_window_controls_are_in_body_and_preserve_native_window_actions(window, app):
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.header_widget.isAncestorOf(window.chrome.controls)
    assert window.chrome.close_button.isVisible()
    window.chrome.maximize_button.click()
    app.processEvents()
    assert window.isMaximized()
    window.chrome.maximize_button.click()
    app.processEvents()
    assert not window.isMaximized()
    window.chrome.minimize_button.click()
    app.processEvents()
    assert window.isMinimized()
    window.showNormal()
    window.resize(1020, 720)
    app.processEvents()
    assert not window.isMinimized()


def test_frameless_qt_file_picker_closes_without_changing_destination(window, app, tmp_path):
    original = window.destination.text()
    observed = []
    def close_picker():
        dialog = QApplication.activeModalWidget()
        observed.append(isinstance(dialog, QDialog)
                        and bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
                        and dialog.file_picker.testOption(QFileDialog.Option.DontUseNativeDialog)
                        and not dialog.file_picker.isWindow()
                        and getattr(dialog.file_picker, "_mira_auto_chrome_header", None) is None)
        dialog.chrome.close_button.click()
    QTimer.singleShot(20, close_picker)
    assert window._pick_path("Каталог коллекции", directory=True, initial=str(tmp_path)) == ""
    assert observed == [True]
    assert window.destination.text() == original


def test_frameless_qt_file_picker_accepts_an_existing_local_file(window, app, tmp_path):
    chosen = tmp_path / "synthetic.txt"
    chosen.write_text("local selection fixture", encoding="utf-8")
    def choose_file():
        dialog = QApplication.activeModalWidget()
        dialog.file_picker.selectFile(str(chosen))
        dialog.file_picker.accept()
    QTimer.singleShot(20, choose_file)
    assert Path(window._pick_path("Ваш локальный файл cookies", initial=str(tmp_path))) == chosen


def test_advanced_and_help_have_close_only_body_headers(window, app):
    assert window.advanced_dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.advanced_dialog.chrome.minimize_button is None
    assert window.advanced_dialog.chrome.maximize_button is None
    observed = []
    def close_help():
        dialog = QApplication.activeModalWidget()
        observed.append(bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
                        and dialog.header_widget.isAncestorOf(dialog.chrome.controls)
                        and dialog.chrome.maximize_button is None)
        dialog.chrome.close_button.click()
    QTimer.singleShot(20, close_help)
    window.help_button.click()
    assert observed == [True]


def test_close_confirmation_body_close_keeps_waiting_instead_of_killing_worker(window, app):
    killed = []
    observed = []
    window.closing = window.active = True
    window.process = SimpleNamespace(kill=lambda: killed.append(True))
    def close_confirmation():
        dialog = QApplication.activeModalWidget()
        observed.append(bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint))
        dialog.chrome.close_button.click()
    QTimer.singleShot(20, close_confirmation)
    try:
        window._close_timeout()
        assert observed == [True] and not killed
    finally:
        window.closing = False
        window.active = False
        window.process = None
