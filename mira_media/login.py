"""Official platform sign-in in an isolated, ephemeral WebEngine profile.

Imported only after the user presses the sign-in button. The application's own
widgets never receive passwords, page contents or authentication challenges.
Only the platform's minimum session cookies are retained after explicit Save.
"""
from __future__ import annotations

import time
import json
import uuid

from PySide6.QtCore import QUrl, Signal, Qt, QTimer
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
    QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor, QWebEngineHttpRequest, QWebEngineScript,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from . import session_vault
from .localization import set_translated_text, translate_widget_tree
from .window_chrome import install_chrome


LOGIN_URL = "https://x.com/i/flow/login?lang=en"
PIXIV_HOME = "https://www.pixiv.net/"
PIXIV_SETTINGS_URL = "https://www.pixiv.net/settings/viewing"
PIXIV_LOGIN_URL = "https://accounts.pixiv.net/login?lang=en&return_to=https%3A%2F%2Fwww.pixiv.net%2F"
LOGIN_HOSTS = frozenset({"x.com", "www.x.com", "twitter.com", "www.twitter.com"})
COOKIE_DOMAINS = frozenset({"x.com", ".x.com", "twitter.com", ".twitter.com"})
COOKIE_NAMES = frozenset({"auth_token", "ct0"})
CHALLENGE_DOMAINS = ("arkoselabs.com", "funcaptcha.com")
PLATFORMS = {
    "x": {"label": "X", "url": LOGIN_URL, "hosts": LOGIN_HOSTS,
          "cookie_domains": COOKIE_DOMAINS, "cookie_names": COOKIE_NAMES},
    "pixiv": {"label": "Pixiv", "url": PIXIV_LOGIN_URL,
              "hosts": frozenset({"accounts.pixiv.net", "www.pixiv.net", "pixiv.net"}),
              "cookie_domains": frozenset({"pixiv.net", ".pixiv.net", "www.pixiv.net", ".www.pixiv.net"}),
              "cookie_names": frozenset({"PHPSESSID"})},
}

# The browser makes one bounded, ordinary same-origin account request. Its
# HttpOnly session stays inside Chromium; only pending/true/false reaches Python.
# State lives in ApplicationWorld, separate from the website's JS globals.
PIXIV_IDENTITY_SCRIPT = """(() => {
  if (location.protocol !== 'https:' || location.hostname !== 'www.pixiv.net' ||
      location.port !== '' && location.port !== '443') return false;
  const key = __MIRA_PROBE_KEY__;
  if (Object.prototype.hasOwnProperty.call(globalThis, key)) return globalThis[key].result;
  const state = {result: 'pending'};
  globalThis[key] = state;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  (async () => {
    try {
      const response = await fetch('/ajax/user/extra?lang=en', {
        method: 'GET', credentials: 'same-origin', redirect: 'error', cache: 'no-store',
        headers: {'Accept': 'application/json'}, signal: controller.signal
      });
      if (response.status !== 200 || response.redirected ||
          new URL(response.url).origin !== location.origin ||
          !/^application\\/json(?:;|$)/i.test(response.headers.get('content-type') || '') ||
          !response.body) return false;
      const declared = Number(response.headers.get('content-length'));
      if (declared > 65536) { controller.abort(); return false; }
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8', {fatal: true});
      let size = 0, text = '';
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        size += chunk.value.byteLength;
        if (size > 65536) { controller.abort(); return false; }
        text += decoder.decode(chunk.value, {stream: true});
      }
      text += decoder.decode();
      const data = JSON.parse(text);
      const body = data && data.body;
      return !!(data && data.error === false && body && typeof body === 'object' &&
        !Array.isArray(body) && ['following', 'followers', 'mypixivCount'].every(name =>
          Number.isSafeInteger(body[name]) && body[name] >= 0));
    } catch (_) { return false; }
    finally { clearTimeout(timeout); }
  })().then(result => { state.result = result === true; });
  return state.result;
})()"""


def pixiv_identity_script(probe_key: str) -> str:
    """Build an isolated idempotent check; the key contains no account data."""
    return PIXIV_IDENTITY_SCRIPT.replace("__MIRA_PROBE_KEY__", json.dumps(probe_key))


def is_navigation(url: QUrl, platform: str = "x") -> bool:
    return (url.isValid() and url.scheme().lower() == "https"
            and url.host().lower() in PLATFORMS[platform]["hosts"] and url.port(-1) in {-1, 443}
            and not url.userName() and not url.password())


def is_x_navigation(url: QUrl) -> bool:
    """Require an unambiguous official HTTPS X origin for every top-level page."""
    return is_navigation(url, "x")


def is_login_frame(url: QUrl, platform: str = "x") -> bool:
    """Frames can contain X or a bounded, manually solved site challenge."""
    if is_navigation(url, platform):
        return True
    host = url.host().lower()
    secure = (url.isValid() and url.scheme().lower() == "https" and url.port(-1) in {-1, 443}
            and not url.userName() and not url.password()
    )
    if platform == "pixiv":
        # Official Pixiv login uses Google's manually completed reCAPTCHA.
        # Restrict the frame to its challenge path, never Google account login.
        return secure and host in {"www.google.com", "www.recaptcha.net", "recaptcha.google.com"} and url.path().startswith("/recaptcha/")
    return secure and any(host == domain or host.endswith("." + domain) for domain in CHALLENGE_DOMAINS)


def session_cookie(cookie: QNetworkCookie, now: float | None = None, *, platform: str = "x") -> dict | None:
    """Validate and copy the minimum cookies; never serialize unrelated state."""
    try:
        name = bytes(cookie.name()).decode("ascii")
        value = bytes(cookie.value()).decode("ascii")
    except (UnicodeDecodeError, ValueError):
        return None
    domain = cookie.domain().lower()
    rules = PLATFORMS[platform]
    if (name not in rules["cookie_names"] or domain not in rules["cookie_domains"]
            or cookie.path() != "/" or not cookie.isSecure() or not value
            or len(value) > 16 * 1024
            or any(ord(character) < 33 or ord(character) > 126 or character in '\";,\\' for character in value)):
        return None
    expires = None if cookie.isSessionCookie() else cookie.expirationDate().toSecsSinceEpoch()
    if expires is not None and expires <= (time.time() if now is None else now):
        return None
    return {"name": name, "value": value, "domain": domain, "path": "/",
            "secure": True, "http_only": cookie.isHttpOnly(), "expires": expires}


class _HttpsRequests(QWebEngineUrlRequestInterceptor):
    """Allow ordinary HTTPS resources, but never an external top-level page."""

    def __init__(self, parent=None, *, platform: str = "x") -> None:
        super().__init__(parent)
        self.platform = platform

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        url = info.requestUrl()
        # data/blob resources are self-contained browser resources, not network
        # destinations. A top-level navigation must still be official HTTPS X.
        if info.resourceType() in {QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame,
                                   QWebEngineUrlRequestInfo.ResourceType.ResourceTypeNavigationPreloadMainFrame}:
            info.block(not is_navigation(url, self.platform))
        elif info.resourceType() in {QWebEngineUrlRequestInfo.ResourceType.ResourceTypeSubFrame,
                                     QWebEngineUrlRequestInfo.ResourceType.ResourceTypeNavigationPreloadSubFrame}:
            info.block(not is_login_frame(url, self.platform))
        elif url.scheme().lower() not in {"https", "data", "blob"}:
            info.block(True)


class _XLoginPage(QWebEnginePage):
    navigationBlocked = Signal()

    def __init__(self, profile, parent=None, *, platform: str = "x") -> None:
        super().__init__(profile, parent)
        self.platform = platform

    def acceptNavigationRequest(self, url: QUrl, navigation_type, is_main_frame: bool) -> bool:
        allowed = is_navigation(url, self.platform) if is_main_frame else is_login_frame(url, self.platform)
        # Passive external widgets sometimes attempt to create an empty frame
        # during ordinary X login. Keep blocking them without replacing the
        # user's main sign-in instructions with a false navigation warning.
        if not allowed and is_main_frame:
            self.navigationBlocked.emit()
        return allowed

    def createWindow(self, window_type):
        # Never delegate sign-in to an unlabelled popup or the user's browser.
        self.navigationBlocked.emit()
        return None

    def javaScriptConsoleMessage(self, level, message, line_number, source_id) -> None:
        # Website diagnostics may include ephemeral flow state. Do not mirror
        # page console content into Mira's logs or process output.
        pass


class LoginDialog(QDialog):
    def __init__(self, parent=None, *, auto_load: bool = True, platform: str = "x") -> None:
        if platform not in PLATFORMS:
            raise ValueError("Неизвестная платформа входа.")
        super().__init__(parent)
        self.platform = platform
        self.platform_label = PLATFORMS[platform]["label"]
        self.login_url = PLATFORMS[platform]["url"]
        self.setWindowTitle(f"Войти в {self.platform_label} — Mira")
        self.resize(800, 850)
        self.setMinimumSize(620, 600)
        self._cookies: dict[tuple[str, str, str], dict] = {}
        self._disposed = False
        self._browser_released = False
        self._browser_release_started = False
        self._closing_result = QDialog.DialogCode.Rejected
        self._pixiv_verified = False
        self._save_pending = False
        self._verification_epoch = 0
        self._verified_url = ""
        self._probe_token = uuid.uuid4().hex
        self._probe_key = ""
        self._probe_attempts = 0
        self._probe_deadline = 0.0
        self._probe_callback_pending = False
        self._verification_timer = QTimer(self)
        self._verification_timer.setSingleShot(True)
        self._verification_timer.timeout.connect(self._check_pixiv_identity)
        self._probe_watchdog = QTimer(self)
        self._probe_watchdog.setSingleShot(True)
        self._probe_watchdog.timeout.connect(self._pixiv_probe_failed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        title = QLabel(f"Вход на официальном сайте {self.platform_label}")
        title.setObjectName("title")
        title.setWordWrap(True)
        self.chrome = install_chrome(self, resizable=True, maximizable=False, minimizable=False)
        self.header_widget = QWidget(self)
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(title, 1)
        header.addWidget(self.chrome.controls)
        self.chrome.set_drag_area(self.header_widget)
        layout.addWidget(self.header_widget)
        self.address = QLineEdit(self.login_url)
        self.address.setReadOnly(True)
        self.address.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.address.setAccessibleName(f"Адрес официальной страницы {self.platform_label}; изменить нельзя")
        self.address.setToolTip("Пароль и коды вводятся только в официальную страницу сайта ниже.")
        layout.addWidget(self.address)
        helper = QLabel(f"Войдите обычным способом в {self.platform_label}. Пароль и коды получает сам сайт. "
                        "Внешние страницы Google, Apple и других способов входа в этом окне недоступны. "
                        "Ключи доступа Windows Hello здесь не поддерживаются — используйте вход по паролю.")
        helper.setWordWrap(True)
        layout.addWidget(helper)

        # A profile without a storage name is off-the-record by Qt contract.
        self.web_profile = QWebEngineProfile(self)
        self.web_profile.setHttpAcceptLanguage("en-US,en;q=0.9")
        self.web_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.web_profile.setPersistentPermissionsPolicy(QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime)
        self.web_profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.interceptor = _HttpsRequests(self.web_profile, platform=platform)
        self.web_profile.setUrlRequestInterceptor(self.interceptor)
        self.web_profile.downloadRequested.connect(lambda request: request.cancel())
        self._cookie_store = self.web_profile.cookieStore()
        self._cookie_store.cookieAdded.connect(self._cookie_added)
        self._cookie_store.cookieRemoved.connect(self._cookie_removed)

        self.page = _XLoginPage(self.web_profile, self, platform=platform)
        settings = self.page.settings()
        for attribute in (QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
                          QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
                          QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                          QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
                          QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript):
            settings.setAttribute(attribute, False)
        self.page.certificateError.connect(lambda error: error.rejectCertificate())
        self.page.permissionRequested.connect(lambda permission: permission.deny())
        self.page.desktopMediaRequested.connect(lambda request: request.cancel())
        self.page.fileSystemAccessRequested.connect(lambda request: request.reject())
        self.page.registerProtocolHandlerRequested.connect(lambda request: request.reject())
        self.page.selectClientCertificate.connect(lambda selection: selection.selectNone())
        self.page.fullScreenRequested.connect(lambda request: request.reject())
        self.page.navigationBlocked.connect(self._navigation_blocked)
        self.page.urlChanged.connect(self._url_changed)
        self.page.loadStarted.connect(self._load_started)
        self.page.loadFinished.connect(self._load_finished)
        self.view = QWebEngineView(self)
        self.view.setPage(self.page)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.view, 1)
        self.status = QLabel("Выполните вход и все проверки сайта. Затем нажмите «Сохранить вход».")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        platform_row = QHBoxLayout()
        self.reload_button = QPushButton("Повторить загрузку")
        self.reload_button.clicked.connect(lambda: self.view.setUrl(QUrl(self.login_url)))
        row.addWidget(self.reload_button)
        self.verify_button = QPushButton("Проверить вход")
        self.verify_button.setVisible(platform == "pixiv")
        self.verify_button.setToolTip("Проверить вход в Pixiv; гостевая сессия не подходит.")
        self.verify_button.clicked.connect(self._start_pixiv_verification)
        platform_row.addWidget(self.verify_button)
        self.settings_button = QPushButton("Настройки показа")
        self.settings_button.setVisible(platform == "pixiv")
        self.settings_button.setToolTip("Сначала настройте аккаунт Pixiv для показа нужного контента. Изменения выполняете вы на сайте Pixiv.")
        self.settings_button.clicked.connect(lambda: self.view.setUrl(QUrl(PIXIV_SETTINGS_URL)))
        platform_row.addWidget(self.settings_button)
        platform_row.addStretch()
        if platform == "pixiv":
            layout.addLayout(platform_row)
        row.addStretch()
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.clicked.connect(self.reject)
        row.addWidget(self.cancel_button)
        self.save_button = QPushButton("Сохранить вход")
        self.save_button.setObjectName("primary")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)
        row.addWidget(self.save_button)
        layout.addLayout(row)
        translate_widget_tree(self)
        if auto_load:
            self.view.setUrl(QUrl(self.login_url))

    def _navigation_blocked(self) -> None:
        if self._disposed:
            return
        set_translated_text(self.status, f"Внешняя страница заблокирована. Продолжайте обычный вход на сайте {self.platform_label}; "
                                        "внешние способы входа не поддерживаются.")

    def _url_changed(self, url: QUrl) -> None:
        if self._disposed:
            return
        self._invalidate_pixiv_verification()
        if is_navigation(url, self.platform):
            # Query/fragment can contain ephemeral site state. Show the origin
            # and path only, without copying identifiers into UI or logs.
            visible = QUrl(url)
            visible.setQuery(None)
            visible.setFragment(None)
            self.address.setText(visible.toString())
        self._update_ready()
        self._schedule_pixiv_verification()

    def _load_finished(self, successful: bool) -> None:
        if self._disposed:
            return
        if not successful:
            self._invalidate_pixiv_verification()
            self._save_pending = False
            set_translated_text(self.status, f"Страница {self.platform_label} не загрузилась. Проверьте соединение и повторите. "
                                            "Если сайт ограничивает встроенный вход, используйте другой способ в главном окне.")
        self._update_ready()
        if successful:
            self._schedule_pixiv_verification(0)

    def _load_started(self) -> None:
        if not self._disposed and self.platform == "pixiv":
            self._invalidate_pixiv_verification()
            self._update_ready()

    def _cookie_added(self, cookie: QNetworkCookie) -> None:
        if self._disposed:
            return
        value = session_cookie(cookie, platform=self.platform)
        if value:
            key = (value["name"], value["domain"], value["path"])
            if self._cookies.get(key) != value:
                self._invalidate_pixiv_verification()
            self._cookies[key] = value
        else:
            key = (bytes(cookie.name()).decode("ascii", errors="replace"), cookie.domain().lower(), cookie.path())
            if self._cookies.pop(key, None) is not None:
                self._invalidate_pixiv_verification()
        self._update_ready()
        self._schedule_pixiv_verification()

    def _cookie_removed(self, cookie: QNetworkCookie) -> None:
        if self._disposed:
            return
        key = (bytes(cookie.name()).decode("ascii", errors="replace"), cookie.domain().lower(), cookie.path())
        if self._cookies.pop(key, None) is not None:
            self._invalidate_pixiv_verification()
        self._update_ready()
        self._schedule_pixiv_verification()

    def _session_values(self) -> list[dict]:
        now = time.time()
        return [dict(value) for value in self._cookies.values()
                if value["expires"] is None or value["expires"] > now]

    def _update_ready(self) -> None:
        if self._disposed:
            return
        values = self._session_values()
        try:
            if self.platform == "x":
                session_vault.normalize_x_cookies(values)
            else:
                session_vault.normalize_cookies(self.platform, values)
            valid = True
        except session_vault.SessionError:
            valid = False
        ready = valid and is_navigation(self.page.url(), self.platform) and (
            self.platform == "x" or self._pixiv_verified and self._is_pixiv_context()
            and self.page.url().toString() == self._verified_url)
        self.save_button.setEnabled(ready)
        if ready:
            set_translated_text(self.status, f"Вход в {self.platform_label} подтверждён. Завершите проверки сайта, затем нажмите «Сохранить вход».")

    def _is_pixiv_context(self) -> bool:
        url = self.page.url()
        return is_navigation(url, "pixiv") and url.host().lower() == "www.pixiv.net"

    def _has_pixiv_cookie(self) -> bool:
        try:
            session_vault.normalize_cookies("pixiv", self._session_values())
            return True
        except session_vault.SessionError:
            return False

    def _invalidate_pixiv_verification(self) -> None:
        if self.platform != "pixiv":
            return
        self._verification_epoch += 1
        self._pixiv_verified = False
        self._verified_url = ""
        self._save_pending = False
        self._probe_key = ""
        self._probe_attempts = 0
        self._probe_callback_pending = False
        self._verification_timer.stop()
        self._probe_watchdog.stop()

    def _schedule_pixiv_verification(self, delay: int = 350) -> None:
        if (self._disposed or self.platform != "pixiv" or self._pixiv_verified
                or not self._is_pixiv_context() or not self._has_pixiv_cookie()
                or self._probe_attempts >= 3 and not self._probe_key):
            return
        if not self._verification_timer.isActive():
            self._verification_timer.start(delay)

    def _start_pixiv_verification(self, save_after: bool = False) -> None:
        if self._disposed or self.platform != "pixiv":
            return
        self._invalidate_pixiv_verification()
        self._save_pending = bool(save_after)
        self._update_ready()
        set_translated_text(self.status, "Проверяем вход в Pixiv. Пароли и содержимое форм не читаются.")
        if self._is_pixiv_context():
            self._check_pixiv_identity()
        else:
            # A manual check can leave accounts.pixiv.net or the bare domain.
            # Never forward an in-page credential request across origins.
            self._save_pending = False
            request = QWebEngineHttpRequest(QUrl(PIXIV_HOME))
            request.setHeader(b"Cache-Control", b"no-cache")
            request.setHeader(b"Pragma", b"no-cache")
            self.view.load(request)

    def _check_pixiv_identity(self) -> None:
        if (self._disposed or self.platform != "pixiv" or not self._is_pixiv_context()
                or not self._has_pixiv_cookie() or self._probe_callback_pending):
            return
        self._verification_timer.stop()
        if not self._probe_key:
            if self._probe_attempts >= 3:
                return
            self._probe_attempts += 1
            self._probe_key = f"__mira_pixiv_{self._probe_token}_{self._verification_epoch}_{self._probe_attempts}"
            self._probe_deadline = time.monotonic() + 8.0
            set_translated_text(self.status, "Проверяем вход в Pixiv. Пароли и содержимое форм не читаются.")
        epoch = self._verification_epoch
        url = self.page.url().toString()
        key = self._probe_key
        self._probe_callback_pending = True
        def checked(result) -> None:
            if (self._disposed or epoch != self._verification_epoch or not self._is_pixiv_context()
                    or self.page.url().toString() != url or self._probe_key != key):
                return
            self._probe_callback_pending = False
            self._probe_watchdog.stop()
            if result == "pending" and time.monotonic() < self._probe_deadline:
                self._verification_timer.start(250)
                return
            self._pixiv_verified = result is True
            self._verified_url = url if self._pixiv_verified else ""
            self._update_ready()
            if self._pixiv_verified:
                pending, self._save_pending = self._save_pending, False
                if pending and self.save_button.isEnabled():
                    self._persist_session()
            else:
                self._pixiv_probe_failed()
        self._probe_watchdog.start(max(1, int((self._probe_deadline - time.monotonic()) * 1000)))
        try:
            self.page.runJavaScript(pixiv_identity_script(key), QWebEngineScript.ScriptWorldId.ApplicationWorld, checked)
        except RuntimeError:
            self._pixiv_probe_failed()

    def _pixiv_probe_failed(self) -> None:
        if self._disposed:
            return
        self._probe_watchdog.stop()
        self._probe_callback_pending = False
        self._pixiv_verified = False
        self._verified_url = ""
        self._probe_key = ""
        self._update_ready()
        if self._is_pixiv_context() and self._has_pixiv_cookie() and self._probe_attempts < 3:
            self._verification_timer.start(2000 * self._probe_attempts)
            return
        self._save_pending = False
        set_translated_text(self.status, "Вход в аккаунт Pixiv пока не подтверждён. Завершите вход и нажмите «Проверить вход». "
                                        "Гостевой сессии недостаточно; при изменении сайта проверка может быть недоступна.")

    def _save(self) -> None:
        self._update_ready()
        if not self.save_button.isEnabled():
            return
        if self.platform == "pixiv":
            self._start_pixiv_verification(save_after=True)
            return
        self._persist_session()

    def _persist_session(self) -> None:
        try:
            if self.platform == "x":
                session_vault.save_x_session(self._session_values(), self.web_profile.httpUserAgent())
            else:
                session_vault.save_session(self.platform, self._session_values(), self.web_profile.httpUserAgent())
        except (session_vault.SessionError, OSError):
            set_translated_text(self.status, "Не удалось безопасно сохранить вход средствами Windows. "
                                            "Проверьте доступ к локальным данным приложения и попробуйте снова.")
            return
        self.accept()

    def done(self, result: int) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._verification_timer.stop()
        self._probe_watchdog.stop()
        self._closing_result = result
        self._cookies.clear()
        self._cookie_store.cookieAdded.disconnect(self._cookie_added)
        self._cookie_store.cookieRemoved.disconnect(self._cookie_removed)
        # Hiding a QDialog would end exec() before the eventual result is set.
        # Keep it present but inert until all engine objects are released.
        self.setEnabled(False)
        set_translated_text(self.status, "Закрываем окно входа…")
        # WebEngine may call accept/reject from a JavaScript or page-text
        # callback. Destroying its page/profile before that callback unwinds
        # can deadlock Chromium teardown. Release them on the next Qt turn,
        # then finish the modal dialog so callers can safely return/quit.
        QTimer.singleShot(0, self._release_browser)

    def _release_browser(self) -> None:
        if self._browser_release_started:
            return
        self._browser_release_started = True
        # Native DeferredDelete events run outside a Python callback holding
        # the GIL. In particular, profile teardown can wait for the IO thread's
        # Python request interceptor; a synchronous shiboken.delete(profile)
        # would prevent that interceptor from completing. Keep the Qt loop
        # alive and release the profile only after its page has been destroyed.
        self.view.destroyed.connect(self.page.deleteLater)
        self.page.destroyed.connect(self.web_profile.deleteLater)
        self.web_profile.destroyed.connect(self._browser_destroyed)
        self.view.deleteLater()

    def _browser_destroyed(self, _object=None) -> None:
        self._browser_released = True
        super().done(self._closing_result)


def open_x_login(parent=None) -> bool:
    return open_login(parent, "x")


def open_login(parent=None, platform: str = "x") -> bool:
    dialog = LoginDialog(parent, platform=platform)
    result = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return result
