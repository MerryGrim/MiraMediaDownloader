"""Focused native 1.4 navigation/date contracts with isolated user data."""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate, QSettings, Qt
from PySide6.QtWidgets import QApplication, QDialog

from mira_media import browser_auth, session_vault
from mira_media.date_filter import DateFilterDialog
from mira_media.ui import MainWindow, STYLE


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    application = QApplication.instance() or QApplication([])
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE)
    original_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path_factory.mktemp("minimalism-settings")))
    yield application
    QSettings.setDefaultFormat(original_format)


@pytest.fixture
def windows(app, tmp_path, monkeypatch):
    monkeypatch.setenv("MIRA_SESSION_DIR", str(tmp_path / "empty-test-vault"))
    monkeypatch.setattr(session_vault, "has_x_session", lambda: False)
    monkeypatch.setattr(session_vault, "has_session", lambda platform: False)
    monkeypatch.setattr(browser_auth, "discover_profiles", lambda browser: [
        SimpleNamespace(browser=browser, profile_id="synthetic-profile", label="Synthetic profile",
                        path=tmp_path / "synthetic-profile")])
    created = []
    def create(**preferences):
        settings = QSettings("Mira", "MiraMediaDownloader")
        settings.clear()
        settings.setValue("destination", str(tmp_path / "isolated-collection"))
        for key, value in preferences.items():
            settings.setValue(key, value)
        settings.sync()
        widget = MainWindow()
        created.append(widget)
        widget.show()
        app.processEvents()
        return widget
    yield create
    for widget in created:
        widget._set_active(False)
        widget.close()
        widget.deleteLater()
    app.processEvents()


def test_saved_pixiv_url_overrides_old_false_opt_in_and_selects_matching_platform(windows):
    window = windows(profile_url="https://www.pixiv.net/users/20151243", pixiv_enabled=False,
                     selected_platform="x")
    assert window._selected_platform() == "pixiv"
    assert window.platform_pixiv_button.isChecked() and not window.platform_x_button.isChecked()
    assert window.pixiv.isChecked() and window.pixiv.isHidden()
    assert window.login_button.text() == "Войти в Pixiv"
    window._save_preferences()
    assert window.settings.value("selected_platform") == "pixiv"


def test_explicit_platform_switch_clears_conflicting_url_and_paste_syncs_back(windows):
    window = windows(profile_url="https://x.com/NASA")
    window.platform_pixiv_button.click()
    assert window._selected_platform() == "pixiv" and not window.profile.text()
    assert window.login_button.text() == "Войти в Pixiv"
    assert window.logout_button.text() == "Выйти из Pixiv"
    assert "pixiv.net/users/" in window.profile.placeholderText()
    window.profile.setText("https://twitter.com/NASA/media")
    assert window._selected_platform() == "x" and window.platform_x_button.isChecked()
    assert window.login_button.text() == "Войти в X"
    # A malformed post URL still has a recognized conflicting platform and
    # should not remain under an explicit Pixiv selection.
    window.profile.setText("https://x.com/NASA/status/123")
    window.platform_pixiv_button.click()
    assert window._selected_platform() == "pixiv" and not window.profile.text()


def test_date_cancel_keeps_main_range_button_and_saved_preferences(windows, monkeypatch):
    window = windows(date_from="2026-10-01", date_to="2026-10-14")
    window._save_preferences()
    initial = window._date_range()
    initial_button = window.date_button.text()
    saved = (window.settings.value("date_from"), window.settings.value("date_to"))
    def cancel_dialog(dialog):
        assert dialog.parent() is window
        dialog.date_from.setDate(QDate(2026, 10, 9))
        dialog.to_enabled.setChecked(False)
        dialog.reject()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(DateFilterDialog, "exec", cancel_dialog)
    window.date_button.click()
    assert window._date_range() == initial
    assert window.date_button.text() == initial_button
    assert (window.settings.value("date_from"), window.settings.value("date_to")) == saved


def test_date_accept_commits_early_iso_bounds_and_all_dates_reset(windows, monkeypatch):
    window = windows()
    def accept_early_range(dialog):
        dialog.custom_dates.setChecked(True)
        dialog.from_enabled.setChecked(True)
        dialog.to_enabled.setChecked(True)
        dialog.date_from.setDate(QDate(1700, 1, 2))
        dialog.date_to.setDate(QDate(1700, 1, 3))
        dialog.accept()
        return dialog.result()
    monkeypatch.setattr(DateFilterDialog, "exec", accept_early_range)
    window.date_button.click()
    assert window._date_range() == ("1700-01-02", "1700-01-03")
    assert window.date_button.text() == "02.01.1700 — 03.01.1700"
    assert (window.settings.value("date_from"), window.settings.value("date_to")) == ("1700-01-02", "1700-01-03")
    def accept_all_dates(dialog):
        dialog.all_dates.setChecked(True)
        dialog.accept()
        return dialog.result()
    monkeypatch.setattr(DateFilterDialog, "exec", accept_all_dates)
    window.date_button.click()
    assert window._date_range() == ("", "") and window.date_button.text() == "Все даты"
    assert (window.settings.value("date_from"), window.settings.value("date_to")) == ("", "")


def test_active_job_disables_platform_date_advanced_and_login_controls(windows, monkeypatch):
    window = windows(profile_url="https://x.com/NASA")
    window._set_active(True)
    for widget in (window.platform_x_button, window.platform_pixiv_button, window.profile, window.date_button,
                   window.advanced_button, window.login_button, window.logout_button, window.auth_source,
                   window.destination_pick, window.request_delay):
        assert not widget.isEnabled()
    def forbidden(*args):
        pytest.fail("Active job opened an editing dialog")
    monkeypatch.setattr(DateFilterDialog, "exec", forbidden)
    monkeypatch.setattr(window.advanced_dialog, "exec", forbidden)
    window._show_date_filter()
    window._show_advanced()
    selected = window._selected_platform()
    window._choose_platform("pixiv")
    assert window._selected_platform() == selected
    window._set_active(False)
    assert all(widget.isEnabled() for widget in (window.platform_x_button, window.platform_pixiv_button,
               window.date_button, window.advanced_button, window.login_button))


def test_three_tabs_main_action_and_gallery_fit_minimum_window(windows, app):
    window = windows()
    window.resize(1020, 720)
    app.processEvents()
    assert [window.tabs.tabText(index) for index in range(window.tabs.count())] == ["Картинки", "История", "Журнал"]
    assert window.download_button.text() == "Найти и скачать" and window.download_button.isVisible()
    central = window.centralWidget()
    action_top = window.download_button.mapTo(central, window.download_button.rect().topLeft())
    action_bottom = window.download_button.mapTo(central, window.download_button.rect().bottomRight())
    assert action_top.x() >= 0 and action_top.y() >= 0
    assert action_bottom.x() < central.width() and action_bottom.y() < central.height()
    assert window.gallery.isVisible() and window.gallery.height() > 2 * window.download_button.height()
    assert window.tabs.height() > central.height() / 4
    assert not window.advanced_dialog.isVisible()
