"""Pixiv account boundary checks with local fixtures and synthetic cookies only."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer, QUrl, QUrlQuery
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWidgets import QApplication, QDialog
if QApplication.instance() is None:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
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
    widget = login.LoginDialog(platform="pixiv", auto_load=False)
    widget.test_url = QUrl(login.PIXIV_HOME)
    monkeypatch.setattr(widget.page, "url", lambda: widget.test_url)
    # Capture ordinary read-only requests; never send a synthetic session online.
    widget.test_requests = []
    monkeypatch.setattr(widget.view, "load", lambda request: widget.test_requests.append(request.url().toString()))
    yield widget
    if not widget._disposed:
        widget.reject()
    wait_for_close(widget)
    widget.deleteLater()
    app.processEvents()


def php_cookie(value="synthetic-account-session"):
    cookie = QNetworkCookie(b"PHPSESSID", value.encode())
    cookie.setDomain(".pixiv.net")
    cookie.setPath("/")
    cookie.setSecure(True)
    cookie.setHttpOnly(True)
    return cookie


@pytest.mark.parametrize("url", ["https://accounts.pixiv.net/login", "https://www.pixiv.net/", "https://pixiv.net/"])
def test_pixiv_navigation_allows_only_official_https(url):
    assert login.is_navigation(QUrl(url), "pixiv")


@pytest.mark.parametrize("url", ["https://x.com/", "https://accounts.google.com/", "https://appleid.apple.com/", "http://www.pixiv.net/", "https://accounts.pixiv.net.attacker.example/", "https://person@www.pixiv.net/", "https://www.pixiv.net:8443/"])
def test_pixiv_navigation_rejects_other_platforms_and_external_credentials(url):
    assert not login.is_navigation(QUrl(url), "pixiv")


def test_pixiv_recaptcha_is_bounded_to_manual_challenge_frames():
    assert login.is_login_frame(QUrl("https://www.google.com/recaptcha/enterprise/anchor"), "pixiv")
    assert login.is_login_frame(QUrl("https://www.recaptcha.net/recaptcha/api2/bframe"), "pixiv")
    assert not login.is_login_frame(QUrl("https://www.google.com/accounts/Login"), "pixiv")
    assert not login.is_login_frame(QUrl("https://accounts.google.com/recaptcha/"), "pixiv")
    assert not login.is_login_frame(QUrl("https://www.google.com.attacker.example/recaptcha/"), "pixiv")
    assert not login.is_login_frame(QUrl("https://www.google.com/recaptcha/enterprise/anchor"), "x")


def test_english_official_login_and_isolated_profile(dialog):
    query = QUrlQuery(QUrl(dialog.login_url))
    assert query.queryItemValue("lang") == "en"
    assert query.queryItemValue("return_to", QUrl.ComponentFormattingOption.FullyDecoded) == login.PIXIV_HOME
    assert dialog.web_profile.httpAcceptLanguage() == "en-US,en;q=0.9"
    assert dialog.web_profile.isOffTheRecord()
    assert dialog.web_profile.persistentCookiesPolicy() == QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
    assert dialog.verify_button.text() == "Проверить вход"
    assert dialog.settings_button.text() == "Настройки показа"


def test_guest_cookie_cannot_enable_save_or_persist(dialog, monkeypatch):
    calls = []
    monkeypatch.setattr(session_vault, "save_session", lambda *args: calls.append(args))
    dialog._cookie_added(php_cookie())
    assert not dialog.save_button.isEnabled()
    dialog._save()
    assert not calls
    assert not dialog.test_requests
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda script, world, callback: callback(False))
    for _ in range(3):
        dialog._check_pixiv_identity()
    assert not dialog.save_button.isEnabled()
    assert "Гостевой" in dialog.status.text()


def test_verified_login_save_requires_fresh_request_and_recheck(dialog, monkeypatch):
    calls = []
    scripts = []
    monkeypatch.setattr(session_vault, "save_session", lambda *args: calls.append(args))
    def reply(script, world, callback):
        scripts.append((script, world))
        callback(True)
    monkeypatch.setattr(dialog.page, "runJavaScript", reply)
    dialog._cookie_added(php_cookie())
    dialog._check_pixiv_identity()
    assert dialog.save_button.isEnabled()
    assert not calls
    dialog._save()
    wait_for_close(dialog)
    assert not dialog.test_requests  # A same-origin check preserves settings/user pages.
    assert len(scripts) == 2 and scripts[0][0] != scripts[1][0]
    assert all(world == QWebEngineScript.ScriptWorldId.ApplicationWorld for _, world in scripts)
    assert len(calls) == 1 and calls[0][0] == "pixiv"
    assert len(calls[0][1]) == 1 and calls[0][1][0]["name"] == "PHPSESSID"
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_cookie_change_and_navigation_invalidate_verification(dialog, monkeypatch):
    callbacks = []
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda script, world, callback: callbacks.append(callback))
    dialog._cookie_added(php_cookie())
    dialog._check_pixiv_identity()
    dialog._cookie_added(php_cookie("changed-session"))
    callbacks.pop()(True)  # Stale response from a different session.
    assert not dialog.save_button.isEnabled()
    dialog._check_pixiv_identity()
    callbacks.pop()(True)
    assert dialog.save_button.isEnabled()
    dialog.test_url = QUrl(login.PIXIV_SETTINGS_URL)
    dialog._url_changed(dialog.test_url)
    assert not dialog.save_button.isEnabled()


def test_failed_recheck_never_saves_and_cancel_preserves_platform_vaults(dialog, monkeypatch):
    calls = []
    monkeypatch.setattr(session_vault, "save_session", lambda *args: calls.append("save"))
    monkeypatch.setattr(session_vault, "clear_session", lambda *args: calls.append("clear"))
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda script, world, callback: callback(True))
    dialog._cookie_added(php_cookie())
    dialog._check_pixiv_identity()
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda script, world, callback: callback(False))
    dialog._save()
    for _ in range(2):
        dialog._check_pixiv_identity()
    assert not dialog.save_button.isEnabled()
    assert not calls
    dialog.reject()
    assert not calls


def test_account_check_needs_secure_session_and_only_runs_on_www_origin(dialog, monkeypatch):
    calls = []
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda *args: calls.append(args))
    dialog._check_pixiv_identity()
    assert not calls and not dialog.save_button.isEnabled()
    for url in ("https://accounts.pixiv.net/login", "https://pixiv.net/en/"):
        dialog.test_url = QUrl(url)
        dialog._cookie_added(php_cookie())
        dialog._check_pixiv_identity()
    assert not calls
    dialog._start_pixiv_verification()
    assert dialog.test_requests == [login.PIXIV_HOME]


@pytest.mark.parametrize("path", ["/en/", "/en/users/123", "/settings/viewing"])
def test_load_and_late_cookie_automatically_schedule_verification(dialog, monkeypatch, path):
    dialog.test_url = QUrl("https://www.pixiv.net" + path)
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda script, world, callback: callback(True))
    dialog._load_finished(True)
    assert not dialog._verification_timer.isActive()  # Wait for the minimum cookie.
    dialog._cookie_added(php_cookie())
    assert dialog._verification_timer.isActive()
    dialog._verification_timer.timeout.emit()
    assert dialog.save_button.isEnabled()


def test_pending_poll_reuses_one_request_key_then_enables_save(dialog, monkeypatch):
    scripts = []
    results = iter(["pending", "pending", True])
    def reply(script, world, callback):
        scripts.append(script)
        callback(next(results))
    monkeypatch.setattr(dialog.page, "runJavaScript", reply)
    dialog._cookie_added(php_cookie())
    for _ in range(3):
        dialog._check_pixiv_identity()
    assert len(set(scripts)) == 1
    assert dialog._probe_attempts == 1 and dialog.save_button.isEnabled()


def test_negative_retries_are_bounded_gentle_and_manual_check_can_restart(dialog, monkeypatch):
    scripts = []
    def reply(script, world, callback):
        scripts.append(script)
        callback(False)
    monkeypatch.setattr(dialog.page, "runJavaScript", reply)
    dialog._cookie_added(php_cookie())
    for delay in (2000, 4000):
        dialog._check_pixiv_identity()
        assert dialog._verification_timer.isActive() and dialog._verification_timer.interval() == delay
    dialog._check_pixiv_identity()
    dialog._check_pixiv_identity()
    dialog._schedule_pixiv_verification()
    assert len(scripts) == len(set(scripts)) == 3
    assert not dialog._verification_timer.isActive() and not dialog.save_button.isEnabled()
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda script, world, callback: callback(True))
    dialog._start_pixiv_verification()
    assert dialog.save_button.isEnabled()


def test_missing_qt_callback_has_watchdog_and_late_reply_cannot_clear_new_probe(dialog, monkeypatch):
    callbacks = []
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda script, world, callback: callbacks.append(callback))
    dialog._cookie_added(php_cookie())
    dialog._check_pixiv_identity()
    assert dialog._probe_watchdog.isActive() and 0 < dialog._probe_watchdog.interval() <= 8000
    old = callbacks.pop()
    dialog._probe_watchdog.timeout.emit()
    assert not dialog._probe_callback_pending and dialog._verification_timer.interval() == 2000
    dialog._check_pixiv_identity()
    assert dialog._probe_callback_pending
    old(True)
    assert dialog._probe_callback_pending and not dialog.save_button.isEnabled()
    callbacks.pop()(True)
    assert dialog.save_button.isEnabled() and not dialog._probe_watchdog.isActive()


def test_watchdog_caps_an_unresponsive_renderer_at_three_attempts(dialog, monkeypatch):
    calls = []
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda *args: calls.append(args))
    dialog._cookie_added(php_cookie())
    for _ in range(3):
        dialog._check_pixiv_identity()
        assert dialog._probe_watchdog.isActive()
        dialog._probe_watchdog.timeout.emit()
    dialog._check_pixiv_identity()
    dialog._schedule_pixiv_verification()
    assert len(calls) == 3
    assert not dialog._verification_timer.isActive() and not dialog._probe_watchdog.isActive()
    assert not dialog.save_button.isEnabled() and not dialog._save_pending


@pytest.mark.parametrize("change", ["cookie", "navigation", "load"])
def test_explicit_save_is_cancelled_by_session_or_page_change(dialog, monkeypatch, change):
    calls, callbacks = [], []
    monkeypatch.setattr(session_vault, "save_session", lambda *args: calls.append(args))
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda script, world, callback: callbacks.append(callback))
    dialog._cookie_added(php_cookie())
    dialog._check_pixiv_identity()
    callbacks.pop()(True)
    dialog._save()
    assert dialog._save_pending and not dialog.save_button.isEnabled()
    old = callbacks.pop()
    if change == "cookie":
        dialog._cookie_added(php_cookie("changed-test-session"))
    elif change == "navigation":
        dialog.test_url = QUrl(login.PIXIV_SETTINGS_URL)
        dialog._url_changed(dialog.test_url)
    else:
        dialog._load_started()
    old(True)
    assert not dialog._save_pending and not calls and not dialog.save_button.isEnabled()
    dialog._check_pixiv_identity()
    callbacks.pop()(True)
    assert dialog.save_button.isEnabled() and not calls  # New explicit Save is required.


def test_close_cancels_pending_checks_and_late_callback_has_no_effect(dialog, monkeypatch):
    callbacks, calls = [], []
    monkeypatch.setattr(session_vault, "save_session", lambda *args: calls.append(args))
    monkeypatch.setattr(dialog.page, "runJavaScript", lambda script, world, callback: callbacks.append(callback))
    dialog._cookie_added(php_cookie())
    dialog._check_pixiv_identity()
    dialog.reject()
    wait_for_close(dialog)
    callbacks.pop()(True)
    assert not calls and not dialog._verification_timer.isActive() and not dialog._probe_watchdog.isActive()


AUTHENTICATED = {"error": False, "body": {"following": 0, "followers": 2, "mypixivCount": 0}}


def renderer_identity(app, *, body=AUTHENTICATED, status=200, content_type="application/json", redirected=False,
                      response_url="https://www.pixiv.net/ajax/user/extra?lang=en", page_url="https://www.pixiv.net/en/",
                      declared_size="", delay=0, raw_text=None):
    """Run the production JS with a generated fetch response, no network/account."""
    profile = QWebEngineProfile()
    class NoNetwork(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            if info.requestUrl().scheme() in {"http", "https"}:
                info.block(True)
    blocker = NoNetwork(profile)
    profile.setUrlRequestInterceptor(blocker)
    view = QWebEngineView()
    page = QWebEnginePage(profile)
    view.setPage(page)
    loop = QEventLoop()
    results = []
    config = {"status": status, "type": content_type, "redirected": redirected, "url": response_url,
              "size": declared_size, "delay": delay, "text": json.dumps(body) if raw_text is None else raw_text}
    bootstrap = """globalThis.__fixtureFetchCount = 0; globalThis.__fixtureOptionsValid = true;
globalThis.fetch = async (url, options) => {
  globalThis.__fixtureFetchCount++;
  globalThis.__fixtureOptionsValid = globalThis.__fixtureOptionsValid && url === '/ajax/user/extra?lang=en' &&
    options.method === 'GET' && options.credentials === 'same-origin' && options.redirect === 'error' &&
    options.cache === 'no-store' && options.signal instanceof AbortSignal;
  const config = CONFIG;
  if (config.delay) await new Promise(resolve => setTimeout(resolve, config.delay));
  return {status: config.status, redirected: config.redirected, url: config.url,
    headers: new Headers({'content-type': config.type, 'content-length': config.size}),
    body: new ReadableStream({start(controller) {
      controller.enqueue(new TextEncoder().encode(config.text)); controller.close();
    }})};
};""".replace("CONFIG", json.dumps(config))
    injected = QWebEngineScript()
    injected.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
    injected.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    injected.setSourceCode(bootstrap)
    page.scripts().insert(injected)
    def checked(value):
        if value == "pending":
            QTimer.singleShot(20, poll)
        else:
            results.append(value)
            page.runJavaScript("JSON.stringify([globalThis.__fixtureFetchCount, globalThis.__fixtureOptionsValid])",
                               QWebEngineScript.ScriptWorldId.ApplicationWorld,
                               lambda facts: (results.append(json.loads(facts)), loop.quit()))
    def poll():
        page.runJavaScript(login.pixiv_identity_script("synthetic-renderer-probe"),
                           QWebEngineScript.ScriptWorldId.ApplicationWorld, checked)
    def loaded(ok):
        assert ok
        poll()
    page.loadFinished.connect(loaded)
    # Misleading authenticated metadata must not override a guest API response.
    content = json.dumps({"props": {"pageProps": {"isLoggedIn": True, "gaUserData": {"login": True, "userId": "123"}}}})
    view.setHtml('<html><body><script id="__NEXT_DATA__" type="application/json">'+content+'</script></body></html>', QUrl(page_url))
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    release = QEventLoop()
    view.destroyed.connect(page.deleteLater)
    page.destroyed.connect(profile.deleteLater)
    profile.destroyed.connect(release.quit)
    view.deleteLater()
    QTimer.singleShot(2000, release.quit)
    release.exec()
    return results


@pytest.mark.parametrize("changes,expected", [
    ({}, True),
    ({"status": 400, "body": {"error": True, "body": []}}, False),
    ({"body": {"error": True, "body": AUTHENTICATED["body"]}}, False),
    ({"body": {"error": False, "body": {}}}, False),
    ({"body": {"error": False, "body": []}}, False),
    ({"body": {"error": False, "body": {"following": True, "followers": 0, "mypixivCount": 0}}}, False),
    ({"body": {"error": False, "body": {"following": -1, "followers": 0, "mypixivCount": 0}}}, False),
    ({"body": {"error": False, "body": {"following": "1", "followers": 0, "mypixivCount": 0}}}, False),
    ({"content_type": "text/html"}, False),
    ({"redirected": True}, False),
    ({"response_url": "https://accounts.pixiv.net/ajax/user/extra"}, False),
    ({"declared_size": "70000"}, False),
    ({"raw_text": "x" * 65537}, False),
    ({"raw_text": "not JSON"}, False),
])
def test_official_account_response_schema_in_real_renderer(app, changes, expected):
    assert renderer_identity(app, **changes) == [expected, [1, True]]


@pytest.mark.parametrize("path", ["/", "/en/", "/en/users/123", "/settings/viewing"])
def test_authenticated_api_works_after_language_user_and_settings_redirects(app, path):
    assert renderer_identity(app, page_url="https://www.pixiv.net" + path, delay=100) == [True, [1, True]]


@pytest.mark.parametrize("url", ["https://accounts.pixiv.net/login", "https://pixiv.net/en/", "https://x.com/"])
def test_renderer_never_forwards_account_check_to_other_origins(app, url):
    assert renderer_identity(app, page_url=url) == [False, [0, True]]


@pytest.mark.parametrize("accepted", [False, True])
def test_webengine_callback_can_close_dialog_without_teardown_deadlock(tmp_path, accepted):
    # Separate process bounds a teardown regression without leaving Qt's main
    # test application stuck. No site request, cookies, vault or account exists.
    script = """
import json,sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication,Qt,QTimer
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PySide6.QtWidgets import QApplication
from mira_media.login import LoginDialog
app=QApplication([])
app.setQuitOnLastWindowClosed(False)
dialog=LoginDialog(auto_load=False,platform='pixiv')
stages=[]
def finished(result):
    stages.append('finished')
    Path(sys.argv[1]).write_text(json.dumps({'stages':stages,'released':dialog._browser_released,'result':result}))
dialog.finished.connect(finished)
def callback(value):
    stages.append('callback')
    dialog.accept() if sys.argv[2]=='yes' else dialog.reject()
    assert dialog._disposed and not dialog._browser_released
    stages.append('callback-return')
QTimer.singleShot(0,lambda:dialog.page.runJavaScript('true',callback))
QTimer.singleShot(8000,app.quit)
result=dialog.exec()
assert dialog._browser_released
assert result == (1 if sys.argv[2]=='yes' else 0)
"""
    result_file = tmp_path / "close-result.json"
    with (tmp_path / "stderr.log").open("wb") as errors:
        result = subprocess.run([sys.executable, "-c", script, str(result_file), "yes" if accepted else "no"],
                                cwd=str(Path(__file__).resolve().parent.parent),
                                stdout=subprocess.DEVNULL, stderr=errors, timeout=12)
    assert result.returncode == 0
    report = json.loads(result_file.read_text())
    assert report == {"stages": ["callback", "callback-return", "finished"], "released": True,
                      "result": int(QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected)}


def test_renderer_probe_receipt_confirms_cleanup_and_post_close_loop(tmp_path):
    env = os.environ.copy()
    env["MIRA_SESSION_DIR"] = str(tmp_path / "empty-vault")
    with (tmp_path / "probe-stderr.log").open("wb") as errors:
        result = subprocess.run([sys.executable, "-m", "mira_media", "--login-probe", str(tmp_path / "probe"), "--login-platform", "pixiv"],
                                cwd=str(Path(__file__).resolve().parent.parent), env=env,
                                stdout=subprocess.DEVNULL, stderr=errors, timeout=12)
    assert result.returncode == 0
    report = json.loads((tmp_path / "probe" / "login-probe.json").read_text(encoding="utf-8"))
    assert all(report[name] for name in ("dialog_finished", "browser_released", "view_destroyed",
                                       "page_destroyed", "profile_destroyed", "post_close_heartbeat", "app_loop_returned"))
    assert report["modal_result"] == int(QDialog.DialogCode.Rejected)
    assert report["password_or_user_credentials_entered"] is False
    assert report["saved_session_available"] is False
