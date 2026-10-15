"""Bounded, account-free release checks for the optional login renderer."""
from __future__ import annotations

import json
from pathlib import Path
import time


def login_probe(output: str, live: bool = False, platform: str = "x", language: str = "ru") -> int:
    from .webengine_runtime import configure_login_runtime
    configure_login_runtime()
    from PySide6.QtCore import QCoreApplication, Qt, QTimer, QUrl
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    from .localization import set_language, get_language, tr
    set_language(language)
    from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, qWebEngineChromiumVersion
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from .login import LoginDialog, is_navigation
    from .themes import apply_theme

    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    from .app_identity import apply_app_icon
    from .window_chrome import install_dialog_chrome_hook
    apply_app_icon(app)
    install_dialog_chrome_hook(app)
    # A real Mira window remains alive while its modal sign-in closes. Preserve
    # that lifecycle here instead of implicitly quitting during profile teardown.
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    set_language(language)
    apply_theme(app, "dark" if language == "zh_CN" else "light")
    started = time.monotonic()
    parent = None
    if live:
        parent = QWidget()
        parent.setWindowTitle("Mira — проверка закрытия окна входа")
        parent.resize(520, 180)
        QVBoxLayout(parent).addWidget(QLabel("Проверка официальной страницы входа без учётных данных."))
        parent.show()
    dialog = LoginDialog(parent, auto_load=live, platform=platform)
    dialog.setWindowTitle("Проверка окна входа — не вводите данные")
    result = {
        "live": live, "platform": platform, "ui_language": get_language(), "chromium": qWebEngineChromiumVersion(),
        "native_save_caption": dialog.save_button.text(),
        "off_the_record": dialog.web_profile.isOffTheRecord(),
        "cookie_policy": dialog.web_profile.persistentCookiesPolicy().name,
        "cache_type": dialog.web_profile.httpCacheType().name,
        "accept_language": dialog.web_profile.httpAcceptLanguage(),
        "password_or_user_credentials_entered": False, "load_finished": False,
        "login_text_visible": False, "website_error_text": False,
        "dialog_finished": False, "browser_released": False,
        "view_destroyed": False, "page_destroyed": False, "profile_destroyed": False,
        "modal_result": None, "post_close_heartbeat": False, "app_loop_returned": False,
    }
    page_captured = False
    fixture = None
    fixture_profile = None
    timers = []

    def later(milliseconds, callback) -> None:
        timer = QTimer(app)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.timeout.connect(timer.deleteLater)
        timers.append(timer)
        timer.start(milliseconds)

    def cancel_timers() -> None:
        from shiboken6 import isValid
        for timer in timers:
            if isValid(timer):
                timer.stop()
                timer.timeout.disconnect()
                timer.deleteLater()
        timers.clear()
    dialog.view.destroyed.connect(lambda: result.update(view_destroyed=True))
    dialog.page.destroyed.connect(lambda: result.update(page_destroyed=True))
    dialog.web_profile.destroyed.connect(lambda: result.update(profile_destroyed=True))

    def post_close() -> None:
        # Runs after the profile's destroyed signal and modal exec() have
        # unwound. A live outer Qt loop must still respond at this point.
        result["post_close_heartbeat"] = True
        result["browser_released"] = dialog._browser_released
        cancel_timers()
        if parent is not None:
            parent.close()
            parent.deleteLater()
        dialog.deleteLater()
        later(0, app.quit)

    def dialog_finished(code: int) -> None:
        result["dialog_finished"] = True
        result["modal_result"] = int(code)
        # Never quit the application from inside a profile destructor callback.
        later(500, post_close)

    dialog.finished.connect(dialog_finished)

    def finish(text: str = "") -> None:
        nonlocal page_captured
        if page_captured:
            return
        page_captured = True
        cancel_timers()
        (dialog.page if live else fixture.page()).loadFinished.disconnect(loaded)
        folded = text.casefold()
        terms = ("pixiv id", "pixiv id or email", "email address", "log in", "ログイン", "ログインする", "login", "e-mail address") if platform == "pixiv" else ("sign in to x", "log in to x", "войти в x", "sign in with google", "next", "далее", "email or username", "phone, email", "continue", "продолжить")
        result["login_text_visible"] = any(term in folded for term in terms)
        result["english_login_text_visible"] = any(term in folded for term in ("log in", "sign in", "continue", "email address", "password"))
        result["website_error_text"] = any(term in folded for term in ("something went wrong", "try reloading", "unsupported browser", "что-то пошло не так"))
        result["page_elapsed_seconds"] = round(time.monotonic() - started, 2)
        result["official_platform_origin"] = is_navigation(dialog.page.url(), platform) if live else None
        result["official_x_origin"] = result["official_platform_origin"] if platform == "x" else None
        screenshot = root / ("login-live.png" if live else "login-renderer-fixture.png")
        (dialog if live else fixture).grab().save(str(screenshot))
        native_screenshot = root / "native-login-frame.png"
        dialog.grab().save(str(native_screenshot))
        result["native_screenshot"] = str(native_screenshot)
        result["screenshot"] = str(screenshot)
        from .session_vault import has_session
        result["saved_session_available"] = has_session(platform)
        result["save_button_enabled"] = dialog.save_button.isEnabled()

        def close_after_callback() -> None:
            if fixture is not None:
                from shiboken6 import delete
                delete(fixture.page())
                delete(fixture)
                delete(fixture_profile)
            dialog.reject()
        later(0, close_after_callback)

    def loaded(success: bool) -> None:
        result["load_finished"] = bool(success)
        def read_public_text() -> None:
            if page_captured:
                return
            (dialog.page if live else fixture.page()).toPlainText(finish)
        later(20000 if live else 300, read_public_text)

    if live:
        dialog.page.loadFinished.connect(loaded)
        def run_modal() -> None:
            result["modal_result"] = int(dialog.exec())
        later(0, run_modal)
    else:
        fixture_profile = QWebEngineProfile()
        fixture_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        fixture_profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        fixture = QWebEngineView()
        fixture.setWindowTitle("Mira — проверка встроенного браузера")
        fixture.resize(900, 650)
        fixture.setPage(QWebEnginePage(fixture_profile, fixture))
        fixture.page().loadFinished.connect(loaded)
        fixture.setHtml('<html><body style="font-family:Segoe UI;padding:48px;color:#503a6d"><h1>Mira · встроенное окно входа</h1><p>Chromium отрисовывает страницу внутри приложения.</p><p>Тест не использует учётную запись и не отправляет запросы к X.</p></body></html>', QUrl("https://x.com/"))
        fixture.show()
    later(35000, finish)
    app.exec()
    result["app_loop_returned"] = True
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    # Write the final receipt only after modal and browser cleanup, a responsive
    # outer-loop heartbeat, and normal application-loop return were observed.
    (root / "login-probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    complete = all(result[name] for name in ("load_finished", "off_the_record", "dialog_finished", "browser_released", "view_destroyed", "page_destroyed", "profile_destroyed", "post_close_heartbeat", "app_loop_returned"))
    return 0 if complete else 1
