"""Official-page login boundary tests; synthetic cookies, no account or network."""
import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDateTime, QUrl, Qt, QEventLoop, QTimer
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWidgets import QApplication, QDialog

# WebEngine can be imported after QApplication only with this startup attribute.
if QApplication.instance() is None:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInfo
from mira_media import login, session_vault


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for_close(widget):
    if not widget._browser_released:
        loop = QEventLoop()
        widget.finished.connect(loop.quit)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
    assert widget._browser_released


@pytest.fixture
def dialog(app, monkeypatch):
    widget = login.LoginDialog(auto_load=False)
    # No website load and no fabricated cookie is sent to the network.
    monkeypatch.setattr(widget.page, "url", lambda: QUrl(login.LOGIN_URL))
    yield widget
    if not widget._disposed:
        widget.reject()
    wait_for_close(widget)
    widget.deleteLater()
    app.processEvents()


def cookie(name="auth_token", value="synthetic-local-only", domain=".x.com", secure=True, path="/", expires=None):
    result = QNetworkCookie(name.encode(), value.encode())
    result.setDomain(domain)
    result.setPath(path)
    result.setSecure(secure)
    result.setHttpOnly(name == "auth_token")
    if expires is not None:
        result.setExpirationDate(QDateTime.fromSecsSinceEpoch(expires))
    return result


@pytest.mark.parametrize("url", [
    "https://x.com/i/flow/login", "https://www.x.com/home",
    "https://twitter.com/home", "https://www.twitter.com:443/home",
])
def test_navigation_accepts_exact_official_https_origins(url):
    assert login.is_x_navigation(QUrl(url))


@pytest.mark.parametrize("url", [
    "http://x.com/i/flow/login", "file:///C:/passwords.txt", "javascript:alert(1)",
    "data:text/html,anything", "https://x.com.attacker.example/login", "https://attacker.example/x.com",
    "https://accounts.google.com/", "https://appleid.apple.com/", "https://x.com:8443/",
    "https://someone@x.com/", "https://x.com:password@attacker.example/", "https://x.com./", "about:blank",
])
def test_navigation_rejects_external_origins_and_confusing_urls(url):
    assert not login.is_x_navigation(QUrl(url))


def test_profile_is_ephemeral_and_has_no_persistent_cookies(dialog):
    profile = dialog.web_profile
    assert profile.isOffTheRecord()
    assert profile.storageName() == ""
    assert profile.persistentCookiesPolicy() == QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
    assert profile.httpCacheType() == QWebEngineProfile.HttpCacheType.MemoryHttpCache
    assert dialog.address.isReadOnly()
    assert dialog.address.text() == login.LOGIN_URL
    assert not dialog.save_button.isEnabled()
    assert profile.httpAcceptLanguage() == "en-US,en;q=0.9"
    assert QUrl(login.LOGIN_URL).query() == "lang=en"


def test_login_body_close_button_preserves_deferred_browser_cleanup(dialog, app):
    dialog.show()
    app.processEvents()
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert dialog.header_widget.isAncestorOf(dialog.chrome.controls)
    assert dialog.chrome.maximize_button is None and dialog.chrome.minimize_button is None
    dialog.chrome.close_button.click()
    wait_for_close(dialog)
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog._disposed and dialog._browser_released


@pytest.mark.parametrize("changes", [
    {"name": "password"}, {"name": "tracking"}, {"domain": ".evil-x.com"},
    {"domain": ".www.x.com"}, {"secure": False}, {"path": "/account"},
    {"expires": 1}, {"value": ""}, {"value": "bad;cookie"}, {"value": "bad\nheader"},
    {"value": 'bad"cookie'}, {"value": "bad\\cookie"},
])
def test_cookie_capture_rejects_unrelated_or_invalid_records(changes):
    assert login.session_cookie(cookie(**changes)) is None


def test_cookie_capture_preserves_required_scope_and_expiry():
    expiration = int(time.time()) + 3600
    record = login.session_cookie(cookie(expires=expiration))
    assert record == {"name": "auth_token", "value": "synthetic-local-only", "domain": ".x.com", "path": "/",
                      "secure": True, "http_only": True, "expires": expiration}
    assert login.session_cookie(cookie(name="ct0"))["expires"] is None


def test_save_needs_complete_session_and_only_explicit_click_persists(dialog, monkeypatch):
    calls = []
    monkeypatch.setattr(session_vault, "save_x_session", lambda records, ua: calls.append((records, ua)))
    dialog._cookie_added(cookie())
    assert not dialog.save_button.isEnabled()
    assert not calls
    dialog._cookie_added(cookie(name="ct0"))
    assert dialog.save_button.isEnabled()
    assert not calls
    dialog._save()
    wait_for_close(dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert len(calls) == 1
    assert {item["name"] for item in calls[0][0]} == {"auth_token", "ct0"}
    assert calls[0][1]
    assert dialog._disposed
    assert dialog._browser_released
    assert not dialog._cookies


def test_cookie_removal_disables_completion(dialog):
    dialog._cookie_added(cookie())
    dialog._cookie_added(cookie(name="ct0"))
    assert dialog.save_button.isEnabled()
    dialog._cookie_removed(cookie())
    assert not dialog.save_button.isEnabled()


def test_expired_and_conflicting_sessions_cannot_finish(dialog):
    dialog._cookie_added(cookie())
    dialog._cookie_added(cookie(name="ct0"))
    assert dialog.save_button.isEnabled()
    dialog._cookies[("ct0", ".x.com", "/")]["expires"] = 1
    dialog._update_ready()
    assert not dialog.save_button.isEnabled()
    dialog._cookie_added(cookie(name="ct0"))
    dialog._cookie_added(cookie(value="different-account", domain=".twitter.com"))
    assert not dialog.save_button.isEnabled()


def test_cancel_does_not_overwrite_or_clear_existing_saved_session(dialog, monkeypatch):
    calls = []
    monkeypatch.setattr(session_vault, "save_x_session", lambda *args: calls.append("save"))
    monkeypatch.setattr(session_vault, "clear_x_session", lambda: calls.append("clear"))
    dialog._cookie_added(cookie())
    dialog._cookie_added(cookie(name="ct0"))
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert not calls
    assert dialog._disposed
    assert not dialog._cookies


def test_failed_safe_storage_keeps_dialog_open_without_error_details(dialog, monkeypatch):
    def fail(*args):
        raise session_vault.SessionError("synthetic-secret-must-not-be-shown")
    monkeypatch.setattr(session_vault, "save_x_session", fail)
    dialog._cookie_added(cookie())
    dialog._cookie_added(cookie(name="ct0"))
    dialog._save()
    assert not dialog._disposed
    assert "Не удалось" in dialog.status.text()
    assert "synthetic-secret" not in dialog.status.text()


def test_page_blocks_external_navigation_and_popup(dialog):
    assert not dialog.page.acceptNavigationRequest(QUrl("https://attacker.example/"), None, True)
    assert "заблокирована" in dialog.status.text()
    assert dialog.page.acceptNavigationRequest(QUrl("https://x.com/home"), None, True)
    assert not dialog.page.acceptNavigationRequest(QUrl("https://accounts.google.com/login"), None, False)
    assert not dialog.page.acceptNavigationRequest(QUrl("https://appleid.apple.com/"), None, False)
    assert dialog.page.acceptNavigationRequest(QUrl("https://client-api.arkoselabs.com/frame"), None, False)
    assert dialog.page.acceptNavigationRequest(QUrl("https://x.com/account/access"), None, False)
    assert dialog.page.createWindow(None) is None


def test_passive_blocked_frames_do_not_replace_login_instructions(dialog):
    before = dialog.status.text()
    assert not dialog.page.acceptNavigationRequest(QUrl("about:blank"), None, False)
    assert not dialog.page.acceptNavigationRequest(QUrl("https://accounts.google.com/"), None, False)
    assert dialog.status.text() == before
    assert not dialog.page.acceptNavigationRequest(QUrl("https://accounts.google.com/"), None, True)
    assert "заблокирована" in dialog.status.text()


def test_resource_filter_enforces_https_and_x_top_frame(app):
    interceptor = login._HttpsRequests()
    def check(url, resource_type):
        blocked = []
        info = SimpleNamespace(requestUrl=lambda: QUrl(url), resourceType=lambda: resource_type,
                               block=lambda value: blocked.append(value))
        interceptor.interceptRequest(info)
        return blocked
    main = QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame
    script = QWebEngineUrlRequestInfo.ResourceType.ResourceTypeScript
    frame = QWebEngineUrlRequestInfo.ResourceType.ResourceTypeSubFrame
    assert check("https://accounts.google.com/", main) == [True]
    assert check("https://x.com/i/flow/login", main) == [False]
    assert check("http://abs.twimg.com/script.js", script) == [True]
    assert check("file:///C:/private.txt", script) == [True]
    assert check("https://abs.twimg.com/script.js", script) == []
    assert check("https://accounts.google.com/", frame) == [True]
    assert check("https://appleid.apple.com/", frame) == [True]
    assert check("https://x.com/login", frame) == [False]
    assert check("https://client-api.arkoselabs.com/frame", frame) == [False]
    assert check("https://funcaptcha.com/frame", frame) == [False]
    assert check("https://funcaptcha.com.attacker.example/frame", frame) == [True]
    assert check("http://arkoselabs.com/frame", frame) == [True]


def test_fixed_address_displays_actual_origin_without_query_state(dialog):
    dialog._url_changed(QUrl("https://x.com/account/access?flow_token=private-ephemeral#fragment"))
    assert dialog.address.text() == "https://x.com/account/access"
    assert "private-ephemeral" not in dialog.address.text()
