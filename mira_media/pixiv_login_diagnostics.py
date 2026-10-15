"""Offline acceptance of the actual Pixiv Save dialog using generated data.

This module is reachable only through the explicit diagnostic CLI. It installs
a fetch fixture in an isolated JavaScript world, never modifies the production
identity script, and blocks every external request before adding a test cookie.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import uuid


_FIXTURE_SCRIPT = r"""(() => {
  const state = {mode: 'guest', requests: 0};
  globalThis.__miraSigninFixture = state;
  globalThis.fetch = async (input, options) => {
    state.requests++;
    document.title = 'MiraOfflineRequests:' + state.requests;
    if (input !== '/ajax/user/extra?lang=en' || options.method !== 'GET' ||
        options.credentials !== 'same-origin' || options.redirect !== 'error' ||
        options.cache !== 'no-store') throw new Error('Unexpected fixture request');
    const valid = state.mode === 'account';
    const data = valid ? {error: false, body: {following: 0, followers: 1, mypixivCount: 0}}
                       : {error: true, body: []};
    const response = new Response(JSON.stringify(data), {
      status: valid ? 200 : 400, headers: {'Content-Type': 'application/json'}
    });
    Object.defineProperty(response, 'url', {value: location.origin + '/ajax/user/extra?lang=en'});
    return response;
  };
})();"""


def pixiv_signin_probe(output: str) -> int:
    from .webengine_runtime import configure_login_runtime
    configure_login_runtime()
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    vault = root / 'synthetic-vault'
    vault.mkdir()
    previous = {name: os.environ.get(name) for name in ('MIRA_SESSION_DIR', 'APPDATA', 'LOCALAPPDATA')}
    os.environ.update(MIRA_SESSION_DIR=str(vault), APPDATA=str(root / 'isolated-roaming'),
                      LOCALAPPDATA=str(root / 'isolated-local'))

    from PySide6.QtCore import QEventLoop, Qt, QTimer, QUrl
    from PySide6.QtNetwork import QNetworkCookie
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout, QWidget
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineUrlRequestInterceptor
    from .login import LoginDialog
    from .localization import set_language
    from .themes import apply_theme
    from . import session_vault

    app = QApplication.instance() or QApplication([])
    from .app_identity import apply_app_icon
    from .window_chrome import install_dialog_chrome_hook
    apply_app_icon(app)
    install_dialog_chrome_hook(app)
    app.setQuitOnLastWindowClosed(False)
    set_language('en')
    apply_theme(app, 'light')
    started = time.monotonic()
    result = {'passed': False, 'checks': {}, 'errors': [], 'actual_user_cookies_accessed': False,
              'network_requests_allowed': 0, 'fixture_only': True, 'modal_result': None,
              'view_destroyed': False, 'page_destroyed': False, 'profile_destroyed': False,
              'post_close_heartbeat': False, 'app_loop_returned': False}
    parent = QWidget()
    parent.setWindowTitle('Mira · isolated Pixiv sign-in acceptance')
    QVBoxLayout(parent).addWidget(QLabel('Generated offline data only; no account is used.'))
    parent.show()
    dialog = LoginDialog(parent, auto_load=False, platform='pixiv')
    dialog.setWindowTitle('Mira · offline Pixiv fixture — do not enter credentials')
    requests_seen = 0

    class BlockNetwork(QWebEngineUrlRequestInterceptor):
        def __init__(self, owner):
            super().__init__(owner)
            self.blocked = 0

        def interceptRequest(self, info):
            # data/about/blob are generated local resources, never destinations.
            if info.requestUrl().scheme().lower() not in {'data', 'about', 'blob'}:
                self.blocked += 1
                info.block(True)

    blocker = BlockNetwork(dialog.web_profile)
    dialog.web_profile.setUrlRequestInterceptor(blocker)
    dialog.interceptor = blocker
    result['network_blocker_installed_before_cookie'] = True
    result['off_the_record'] = dialog.web_profile.isOffTheRecord()
    dialog.view.destroyed.connect(lambda: result.update(view_destroyed=True))
    dialog.page.destroyed.connect(lambda: result.update(page_destroyed=True))
    dialog.web_profile.destroyed.connect(lambda: result.update(profile_destroyed=True))

    def title_changed(title):
        nonlocal requests_seen
        if title.startswith('MiraOfflineRequests:'):
            try:
                requests_seen = max(requests_seen, int(title.partition(':')[2]))
            except ValueError:
                pass
    dialog.page.titleChanged.connect(title_changed)
    script = QWebEngineScript()
    script.setName('Mira diagnostic offline API fixture')
    script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setRunsOnSubFrames(False)
    script.setSourceCode(_FIXTURE_SCRIPT)
    dialog.page.scripts().insert(script)
    synthetic_value = 'mira-generated-not-an-account-' + uuid.uuid4().hex
    expected_cookie = [synthetic_value]

    def check(name, condition):
        result['checks'][name] = bool(condition)
        if not condition:
            raise AssertionError(name)

    def wait_until(predicate, seconds, label):
        loop = QEventLoop()
        timer = QTimer(parent)
        timer.setInterval(20)
        deadline = time.monotonic() + seconds
        state = {'done': False, 'error': None}

        def poll():
            try:
                if predicate():
                    state['done'] = True
                    loop.quit()
                elif time.monotonic() >= deadline:
                    loop.quit()
            except Exception as exc:
                state['error'] = exc
                loop.quit()
        timer.timeout.connect(poll)
        timer.start()
        poll()
        if not state['done'] and state['error'] is None:
            loop.exec()
        timer.stop()
        timer.deleteLater()
        if state['error']:
            raise state['error']
        if not state['done']:
            raise TimeoutError(label)

    def javascript(source):
        values = []
        dialog.page.runJavaScript(source, QWebEngineScript.ScriptWorldId.ApplicationWorld,
                                  lambda value: values.append(value))
        wait_until(lambda: bool(values), 2, 'Fixture JavaScript callback timed out')
        return values[0]

    def add_cookie(value):
        cookie = QNetworkCookie(b'PHPSESSID', value.encode('ascii'))
        cookie.setDomain('.pixiv.net')
        cookie.setPath('/')
        cookie.setSecure(True)
        cookie.setHttpOnly(True)
        dialog.web_profile.cookieStore().setCookie(cookie, QUrl('https://www.pixiv.net/'))

    def verified_at(path):
        return (dialog.page.url().path() == path and dialog._pixiv_verified
                and dialog._verified_url == dialog.page.url().toString() and dialog.save_button.isEnabled())

    def run_checks():
        try:
            wait_until(lambda: bool(dialog._cookies), 3, 'Generated cookie was not captured')
            wait_until(lambda: requests_seen >= 1 and dialog._probe_attempts >= 1
                       and not dialog._probe_callback_pending and not dialog._probe_key,
                       5, 'Guest response did not complete')
            check('guest_cookie_alone_does_not_enable_save', not dialog.save_button.isEnabled() and not dialog._pixiv_verified)
            check('guest_does_not_persist', not session_vault.session_path('pixiv').exists())
            check('guest_fixture_rendered', dialog.page.url().path() == '/en/')
            check('guest_screenshot_saved', dialog.grab().save(str(root / 'guest-save-disabled.png')))
            javascript("globalThis.__miraSigninFixture.mode = 'account'; true")
            # Rotate the actual cookie store value; the production cookie-change
            # callback must schedule automatic verification without Verify click.
            expected_cookie[0] = synthetic_value + '-rotated'
            add_cookie(expected_cookie[0])
            wait_until(lambda: verified_at('/en/'), 5, 'Automatic /en/ account detection failed')
            check('automatic_en_page_enables_save', True)
            check('automatic_verification_does_not_persist', not session_vault.session_path('pixiv').exists())
            for path, name in (('/settings/viewing', 'settings'), ('/users/20151243', 'user'), ('/en/', 'return_en')):
                before = requests_seen
                javascript('history.pushState({}, "", ' + json.dumps(path) + '); true')
                wait_until(lambda: verified_at(path) and requests_seen > before,
                           5, 'Automatic verification after local path change failed')
                check('automatic_' + name + '_page_enables_save', True)
            check('confirmed_screenshot_saved', dialog.grab().save(str(root / 'confirmed-save-enabled.png')))
            result['requests_before_explicit_save'] = requests_seen
            dialog.save_button.click()
            check('explicit_save_starts_fresh_verification', dialog._save_pending and not dialog.save_button.isEnabled())
        except Exception as exc:
            result['errors'].append(type(exc).__name__ + ': ' + str(exc))
            result['failure_state'] = {'cookie_count': len(dialog._cookies), 'probe_attempts': dialog._probe_attempts,
                                       'probe_pending': dialog._probe_callback_pending,
                                       'probe_key_present': bool(dialog._probe_key), 'requests_seen': requests_seen,
                                       'page_path': dialog.page.url().path(), 'page_host': dialog.page.url().host()}
            try:
                result['failure_fixture_state'] = javascript('JSON.stringify({protocol:location.protocol,host:location.hostname,path:location.pathname,fixture:!!globalThis.__miraSigninFixture,requests:globalThis.__miraSigninFixture?.requests})')
            except Exception:
                pass
            dialog.reject()

    # The network deny rule is already installed before either operation below.
    add_cookie(synthetic_value)
    # setHtml internally navigates to a generated data: document. The normal
    # login page intentionally refuses that scheme. Permit just this one local
    # fixture transport, then restore the ordinary production navigation guard.
    # The production authentication script/decision is never replaced.
    ordinary_navigation = dialog.page.acceptNavigationRequest
    fixture_navigation = {'used': False}

    def allow_generated_html(url, navigation_type, main_frame):
        if main_frame and url.scheme() == 'data' and not fixture_navigation['used']:
            fixture_navigation['used'] = True
            return True
        return ordinary_navigation(url, navigation_type, main_frame)

    def restore_navigation(_successful):
        dialog.page.acceptNavigationRequest = ordinary_navigation
        result['generated_local_document_loaded'] = fixture_navigation['used']
    dialog.page.acceptNavigationRequest = allow_generated_html
    dialog.page.loadFinished.connect(restore_navigation)
    dialog.page.setHtml('<!doctype html><html><body style="font:20px Segoe UI;padding:40px">'
                        '<h1>Offline Pixiv fixture</h1><p>Generated API responses only. '
                        'No password, account or external request.</p></body></html>', QUrl('https://www.pixiv.net/en/'))
    work = QTimer(parent)
    work.setSingleShot(True)
    work.timeout.connect(run_checks)
    watchdog = QTimer(parent)
    watchdog.setSingleShot(True)

    def timeout():
        result['errors'].append('TimeoutError: Offline sign-in fixture exceeded its deadline')
        dialog.reject()
    watchdog.timeout.connect(timeout)
    watchdog.start(25000)
    work.start(0)
    try:
        result['modal_result'] = int(dialog.exec())
        work.stop()
        watchdog.stop()
        check('modal_save_accepted', result['modal_result'] == int(QDialog.DialogCode.Accepted))
        check('explicit_save_made_new_api_request', requests_seen > result.get('requests_before_explicit_save', requests_seen))
        check('browser_released_before_modal_return', dialog._browser_released and dialog._disposed)
        check('all_browser_objects_destroyed', all(result[name] for name in ('view_destroyed', 'page_destroyed', 'profile_destroyed')))
        path = session_vault.session_path('pixiv')
        ciphertext = path.read_bytes()
        check('dpapi_ciphertext_has_no_cookie_plaintext', expected_cookie[0].encode('ascii') not in ciphertext)
        jar, user_agent = session_vault.load_session('pixiv')
        values = [cookie.value for cookie in jar if cookie.name == 'PHPSESSID']
        check('saved_session_reloaded_with_expected_cookie', values == expected_cookie and bool(user_agent))
        check('only_pixiv_fixture_session_saved', not session_vault.session_path('x').exists())
        result['fixture_api_requests'] = requests_seen
    except Exception as exc:
        result['errors'].append(type(exc).__name__ + ': ' + str(exc))
    finally:
        work.stop()
        watchdog.stop()
        # Finish native cleanup even if a check failed; never force the process.
        if not dialog._disposed:
            dialog.reject()
        if not dialog._browser_released:
            try:
                wait_until(lambda: dialog._browser_released, 5, 'Browser cleanup timed out')
            except Exception as exc:
                result['errors'].append(type(exc).__name__ + ': ' + str(exc))
        result['blocked_external_requests'] = blocker.blocked
        session_vault.clear_session('pixiv')
        result['synthetic_vault_cleared'] = not session_vault.session_path('pixiv').exists()

        def heartbeat():
            result['post_close_heartbeat'] = True
            parent.close()
            dialog.deleteLater()
            parent.deleteLater()
            app.quit()
        finish = QTimer(app)
        finish.setSingleShot(True)
        finish.timeout.connect(heartbeat)
        finish.start(100)
        app.exec()
        result['app_loop_returned'] = True
        finish.stop()
        finish.deleteLater()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    result['elapsed_seconds'] = round(time.monotonic() - started, 2)
    result['passed'] = (not result['errors'] and bool(result['checks']) and all(result['checks'].values())
                        and result['post_close_heartbeat'] and result['app_loop_returned']
                        and result['synthetic_vault_cleared'])
    (root / 'pixiv-signin-probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1
