"""Actual synthetic DPAPI -> guarded Pixiv adapter -> engine contracts.

No real account, browser profile or network is accessed. HTTP replies are
synthetic fixtures at requests' transport boundary; adapter and engine remain
the production implementations.
"""

from dataclasses import asdict
from io import BytesIO
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
import pytest
import requests

from mira_media import browser_auth, session_vault as vault
from mira_media.adapters import AdapterError, GalleryAdapter, parse_profile
from mira_media.adapters import gallery
from mira_media.control import Control
from mira_media.engine import run_job
from mira_media.models import JobOptions
from mira_media.store import Store


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Actual current-user Windows DPAPI integration')
PIXIV_TOKEN = '77000000_GENERATED-private-Pixiv-session-integration'
X_TOKEN = 'GENERATED-private-X-session-integration'
X_CSRF = 'GENERATED-private-X-csrf-integration'
USER_AGENT = 'Mozilla/5.0 (Mira Synthetic Pixiv Browser 1.3)'
EXTRA = {'following': 0, 'followers': 7, 'mypixivCount': 0}
ORIGINAL_ONE = 'https://i.pximg.net/img-original/img/2026/10/14/00/00/00/456_p0.png'
ORIGINAL_TWO = 'https://i.pximg.net/img-original/img/2026/10/14/00/00/00/456_p1.jpg'
ORIGINAL_THREE = 'https://i.pximg.net/img-original/img/2026/10/14/00/00/00/452_p0.jpeg'


class ImmediateControl(Control):
    def wait(self, seconds):
        self.check()


@pytest.fixture(autouse=True)
def isolate_vault_and_forbid_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'SyntheticLocalAppData'))
    monkeypatch.setenv('MIRA_SESSION_DIR', str(tmp_path / 'SyntheticSessions'))
    def forbidden(*args, **kwargs):
        pytest.fail('Unexpected network, X-vault lookup, browser import or cookies-file fallback')
    monkeypatch.setattr(requests.Session, 'request', forbidden)
    monkeypatch.setattr(vault, 'load_x_session', forbidden)
    monkeypatch.setattr(browser_auth, 'load_browser_cookies', forbidden)
    monkeypatch.setattr(gallery, '_load_cookies', forbidden)


def save_sessions(pixiv=True):
    vault.save_x_session([dict(name=name, value=value, domain='.x.com', path='/', secure=True, expires=None)
                          for name, value in [('auth_token', X_TOKEN), ('ct0', X_CSRF)]], USER_AGENT)
    if pixiv:
        vault.save_session('pixiv', [dict(name='PHPSESSID', value=PIXIV_TOKEN, domain='.pixiv.net',
                                          path='/', secure=True, expires=None)], USER_AGENT)
    return vault.session_path('x').read_bytes()


def opts(tmp_path, **overrides):
    return JobOptions(profile_url='https://www.pixiv.net/users/123', destination=str(tmp_path / 'Collection'),
                      auth_source='embedded', pixiv_enabled=True, **overrides)


def envelope(body, error=False):
    return {'error': error, 'message': 'GENERATED-untrusted-PHPSESSID=' + PIXIV_TOKEN, 'body': body}


class Transport:
    def __init__(self, routes):
        self.routes = dict(routes)
        self.calls = []
        self.responses = []

    def install(self, monkeypatch):
        def request(session, method, url, **kwargs):
            return self.reply(session, method, url, **kwargs)
        monkeypatch.setattr(requests.Session, 'request', request)
        return self

    def reply(self, session, method, url, **kwargs):
        parsed = urlsplit(url)
        assert parsed.hostname in ('www.pixiv.net', 'i.pximg.net')
        assert method == 'GET' and kwargs['verify'] is True and not kwargs['allow_redirects']
        assert session.headers['User-Agent'] == USER_AGENT
        assert session.cookies.get('PHPSESSID', domain='.pixiv.net', path='/') == PIXIV_TOKEN
        assert all(c.name == 'PHPSESSID' and c.domain == '.pixiv.net' for c in session.cookies)
        prepared = session.prepare_request(requests.Request(method, url, params=kwargs.get('params')))
        sent_cookie = prepared.headers.get('Cookie', '')
        if parsed.hostname == 'www.pixiv.net':
            assert 'PHPSESSID=' + PIXIV_TOKEN in sent_cookie
            key = parsed.path.removeprefix('/ajax/')
        else:
            assert 'PHPSESSID' not in sent_cookie, 'Pixiv login must not be sent to the image CDN'
            key = url
        self.calls.append(key)
        assert key in self.routes, 'Unexpected fixture request: ' + key
        payload = self.routes[key]
        if isinstance(payload, list):
            assert payload, 'Unexpected repeated fixture request: ' + key
            payload = payload.pop(0)
        status, body = payload
        result = requests.Response()
        result.status_code = status
        result.url = url
        if isinstance(body, bytes):
            result._content = body
            result.headers['Content-Type'] = 'image/png' if parsed.path.endswith('.png') else 'image/jpeg'
        else:
            result._content = json.dumps(body).encode()
            result.headers['Content-Type'] = 'application/json'
        result.headers['Content-Length'] = str(len(result._content))
        result._content_consumed = True
        self.responses.append(result)
        return result


def successful_routes(extra=None):
    return {
        'user/extra': (200, envelope(EXTRA if extra is None else extra)),
        'user/123/profile/all': (200, envelope({'illusts': {'456': None, '455': None, '454': None, '453': None},
                                                'manga': {'456': None, '452': None}})),
        'illust/456': (200, envelope({'userId': '123', 'illustType': 0, 'pageCount': 4,
                                      'createDate': '2026-10-15T01:00:00+02:00'})),
        'illust/456/pages': (200, envelope([{'urls': {'original': ORIGINAL_ONE}},
                                            {'urls': {'original': ORIGINAL_TWO}},
                                            {'urls': {'original': 'https://i.pximg.net/img-master/456_p2.jpg'}}])),
        'illust/455': (200, envelope({'userId': '123', 'illustType': 0, 'createDate': '2026-10-13T12:00:00Z'})),
        'illust/454': (200, envelope({'userId': '999', 'illustType': 0, 'createDate': '2026-10-14T12:00:00Z'})),
        'illust/453': (200, envelope({'userId': '123', 'illustType': 2, 'createDate': '2026-10-14T12:00:00Z'})),
        'illust/452': (200, envelope({'userId': '123', 'illustType': 1, 'pageCount': 2,
                                      'createDate': '2026-10-14T12:00:00Z'})),
        'illust/452/pages': (200, envelope([{'urls': {'original': ORIGINAL_THREE}}, {'urls': {}}])),
    }


def last_stats(events):
    return [event for event in events if event['type'] == 'stats'][-1]


def assert_no_plaintext_secrets(root, events=()):
    serialized = str(events)
    for sentinel in (PIXIV_TOKEN, X_TOKEN, X_CSRF):
        assert sentinel not in serialized
        for file in root.rglob('*'):
            if file.is_file():
                assert sentinel.encode() not in file.read_bytes(), file.name


def test_actual_dpapi_pixiv_session_reaches_adapter_in_memory_without_using_x(tmp_path, monkeypatch):
    previous_x = save_sessions()
    logs = []
    adapter = GalleryAdapter(parse_profile('https://www.pixiv.net/users/123', True), opts(tmp_path),
                             ImmediateControl(), lambda *args: logs.append(args))
    try:
        assert adapter.session.headers['User-Agent'] == USER_AGENT
        assert adapter.session.cookies.get_dict() == {'PHPSESSID': PIXIV_TOKEN}
        assert {(c.domain, c.path, c.secure) for c in adapter.session.cookies} == {('.pixiv.net', '/', True)}
        assert not adapter.session.trust_env
    finally:
        adapter.close()
    assert not adapter.session.cookies
    assert vault.session_path('x').read_bytes() == previous_x
    assert vault.has_session('x') and vault.has_session('pixiv')
    assert_no_plaintext_secrets(tmp_path, logs)


def test_missing_pixiv_stops_before_network_and_never_reuses_saved_x(tmp_path):
    previous_x = save_sessions(pixiv=False)
    events = []
    assert run_job(opts(tmp_path, mode='preview'), events.append, ImmediateControl(events.append)) == 1
    assert [event['state'] for event in events if event['type'] == 'state'] == ['authorizing', 'error']
    assert 'Pixiv' in events[-1]['message'] and 'Войдите' in events[-1]['message']
    assert last_stats(events)['found'] == 0
    assert vault.session_path('x').read_bytes() == previous_x
    assert_no_plaintext_secrets(tmp_path, events)


BAD_PREFLIGHTS = [
    (400, envelope(None, True)),
    (200, envelope(EXTRA, True)),
    (200, {}),
    (200, []),
    (200, envelope({})),
    (200, envelope([])),
    (200, envelope(None)),
    (200, envelope(EXTRA, 0)),
    (200, b'GENERATED-not-JSON PHPSESSID=' + PIXIV_TOKEN.encode()),
]
for field in ('following', 'followers', 'mypixivCount'):
    for invalid in (-1, True, 1.5, '1', None):
        BAD_PREFLIGHTS.append((200, envelope({**EXTRA, field: invalid})))


@pytest.mark.parametrize('reply', BAD_PREFLIGHTS, ids=[f'preflight-{i}' for i in range(len(BAD_PREFLIGHTS))])
def test_guest_or_malformed_account_preflight_halts_before_any_gallery_request(tmp_path, monkeypatch, reply):
    previous_x = save_sessions()
    transport = Transport({'user/extra': reply}).install(monkeypatch)
    events = []
    assert run_job(opts(tmp_path, mode='preview'), events.append, ImmediateControl(events.append)) == 1
    assert transport.calls == ['user/extra']
    assert last_stats(events)['found'] == 0
    assert events[-1]['state'] == 'error' and 'Pixiv не подтвердил вход' in events[-1]['message']
    assert vault.session_path('x').read_bytes() == previous_x
    assert_no_plaintext_secrets(tmp_path, events)


@pytest.mark.parametrize('extra', [EXTRA, {'following': 0, 'followers': 0, 'mypixivCount': 0},
                                  {'following': 4, 'followers': 2, 'mypixivCount': 1}])
def test_valid_account_preflight_then_original_multipage_utc_filter_and_skip_totals(tmp_path, monkeypatch, extra):
    save_sessions()
    transport = Transport(successful_routes(extra)).install(monkeypatch)
    logs = []
    options = opts(tmp_path, mode='preview', date_from='2026-10-14', date_to='2026-10-14')
    adapter = GalleryAdapter(parse_profile(options.profile_url, True), options, ImmediateControl(),
                             lambda *args: logs.append(args))
    try:
        media = list(adapter.iter_media())
    finally:
        adapter.close()
    assert [(item.key, item.index, item.author_id) for item in media] == [
        ('pixiv:456:p0', 1, '123'), ('pixiv:456:p1', 2, '123'), ('pixiv:452:p0', 1, '123')]
    assert [item.url for item in media] == [ORIGINAL_ONE, ORIGINAL_TWO, ORIGINAL_THREE]
    assert media[0].posted == '2026-10-14T23:00:00Z'
    assert media[-1].extension == 'jpg'
    assert 'illust/455/pages' not in transport.calls
    assert 'illust/454/pages' not in transport.calls and 'illust/453/pages' not in transport.calls
    assert transport.calls[0] == 'user/extra'
    assert transport.calls.count('illust/456') == 1, 'An artwork in illusts and manga must not be counted twice'
    assert any('4 страниц' in message and 'вернул 3' in message for _, message in logs)
    assert any('недоступных публикаций — 1' in message and 'недоступных страниц — 3' in message
               and 'ugoira — 1' in message for _, message in logs)
    assert_no_plaintext_secrets(tmp_path, logs)


def test_engine_preview_counts_images_and_keeps_secrets_out_of_request_history_logs(tmp_path, monkeypatch):
    previous_x = save_sessions()
    transport = Transport(successful_routes()).install(monkeypatch)
    options = opts(tmp_path, mode='preview', date_from='2026-10-14', date_to='2026-10-14')
    request_file = Path(options.destination) / '.mira' / 'tasks' / 'synthetic-request.json'
    request_file.parent.mkdir(parents=True)
    request_file.write_text(json.dumps(asdict(options)), encoding='utf-8')
    # The real worker deserializes this same options contract; session data is
    # loaded later from the vault rather than being added to its request JSON.
    options = JobOptions.from_dict(json.loads(request_file.read_text(encoding='utf-8')))
    assert options.auth_source == 'embedded'
    assert not options.browser and not options.browser_profile and not options.cookies_file
    events = []
    assert run_job(options, events.append, ImmediateControl(events.append)) == 0
    assert last_stats(events) == {'type': 'stats', 'found': 3, 'downloaded': 0, 'skipped': 0, 'failed': 0, 'bytes': 0}
    assert [event['state'] for event in events if event['type'] == 'state'] == ['authorizing', 'scanning', 'completed']
    assert not any(call.startswith('https://i.pximg.net/') for call in transport.calls)
    store = Store(options.destination)
    try:
        assert store.list_jobs()[0]['found'] == 3
        assert len(store.queued(parse_profile(options.profile_url, True))) == 3
        dump = '\n'.join(store.db.iterdump())
    finally:
        store.close()
    assert all(secret not in dump for secret in (PIXIV_TOKEN, X_TOKEN, X_CSRF))
    assert vault.session_path('x').read_bytes() == previous_x
    assert_no_plaintext_secrets(tmp_path, events)


def image_bytes(color, format):
    stream = BytesIO()
    Image.new('RGB', (12, 12), color).save(stream, format)
    return stream.getvalue()


def test_engine_saves_returned_originals_under_pixiv_numeric_id_and_only_new_skips_files(tmp_path, monkeypatch):
    previous_x = save_sessions()
    routes = successful_routes()
    images = {ORIGINAL_ONE: image_bytes('red', 'PNG'), ORIGINAL_TWO: image_bytes('blue', 'JPEG'),
              ORIGINAL_THREE: image_bytes('green', 'JPEG')}
    routes.update({url: (200, data) for url, data in images.items()})
    transport = Transport(routes).install(monkeypatch)
    options = opts(tmp_path, date_from='2026-10-14', date_to='2026-10-14')
    events = []
    assert run_job(options, events.append, ImmediateControl(events.append)) == 0
    assert (last_stats(events)['found'], last_stats(events)['downloaded']) == (3, 3)
    files = {file.name: file.read_bytes() for file in (Path(options.destination) / 'Pixiv' / '123').iterdir()}
    assert files == {'456_01.png': images[ORIGINAL_ONE], '456_02.jpg': images[ORIGINAL_TWO],
                     '452_01.jpg': images[ORIGINAL_THREE]}
    assert not list(Path(options.destination).rglob('*.part'))
    transport.calls.clear()
    second_events = []
    assert run_job(opts(tmp_path, date_from='2026-10-14', date_to='2026-10-14'), second_events.append,
                   ImmediateControl(second_events.append)) == 0
    assert (last_stats(second_events)['found'], last_stats(second_events)['skipped']) == (3, 3)
    assert not any(call.startswith('https://i.pximg.net/') for call in transport.calls)
    assert vault.session_path('x').read_bytes() == previous_x
    assert_no_plaintext_secrets(tmp_path, [*events, *second_events])


@pytest.mark.parametrize('optional_reply', [(404, {}), (200, envelope(None, True))], ids=['404', 'error-true'])
def test_mid_job_guest_session_failure_stops_on_optional_post_instead_of_completing_partial(tmp_path, monkeypatch,
                                                                                         optional_reply):
    save_sessions()
    routes = {'user/extra': [(200, envelope(EXTRA)), (400, envelope(None, True))],
              'user/123/profile/all': (200, envelope({'illusts': {'456': None, '455': None}, 'manga': {}})),
              'illust/456': optional_reply}
    transport = Transport(routes).install(monkeypatch)
    events = []
    assert run_job(opts(tmp_path, mode='preview'), events.append, ImmediateControl(events.append)) == 1
    assert transport.calls == ['user/extra', 'user/123/profile/all', 'illust/456', 'user/extra']
    assert last_stats(events)['found'] == 0 and events[-1]['state'] == 'error'
    assert 'Pixiv не подтвердил вход' in events[-1]['message']
    assert_no_plaintext_secrets(tmp_path, events)


@pytest.mark.parametrize('optional_reply', [(404, {}), (200, envelope(None, True))], ids=['404', 'error-true'])
def test_unavailable_post_rechecks_still_valid_session_then_reports_skip(tmp_path, monkeypatch, optional_reply):
    save_sessions()
    routes = {'user/extra': (200, envelope(EXTRA)),
              'user/123/profile/all': (200, envelope({'illusts': {'456': None}, 'manga': {}})),
              'illust/456': optional_reply}
    transport = Transport(routes).install(monkeypatch)
    events = []
    assert run_job(opts(tmp_path, mode='preview'), events.append, ImmediateControl(events.append)) == 0
    assert transport.calls == ['user/extra', 'user/123/profile/all', 'illust/456', 'user/extra']
    assert last_stats(events)['found'] == 0
    assert [event for event in events if event['type'] == 'state'][-1]['state'] == 'completed'
    assert any('недоступных публикаций — 1' in event.get('message', '') for event in events)
    assert_no_plaintext_secrets(tmp_path, events)


@pytest.mark.parametrize('malformed', ['detail-list', 'page-item-list', 'page-urls-list', 'page-urls-missing'])
def test_malformed_detail_or_page_schema_stops_with_fixed_error(tmp_path, monkeypatch, malformed):
    save_sessions()
    routes = {'user/extra': (200, envelope(EXTRA)),
              'user/123/profile/all': (200, envelope({'illusts': {'456': None}, 'manga': {}})),
              'illust/456': (200, envelope({'userId': '123', 'illustType': 0,
                                           'createDate': '2026-10-14T12:00:00Z'}))}
    if malformed == 'detail-list':
        routes['illust/456'] = (200, envelope(['GENERATED-untrusted-data', PIXIV_TOKEN]))
    else:
        page = {'page-item-list': [], 'page-urls-list': {'urls': []}, 'page-urls-missing': {}}[malformed]
        routes['illust/456/pages'] = (200, envelope([page]))
    Transport(routes).install(monkeypatch)
    events = []
    assert run_job(opts(tmp_path, mode='preview'), events.append, ImmediateControl(events.append)) == 1
    assert last_stats(events)['found'] == 0 and events[-1]['state'] == 'error'
    assert 'Pixiv изменил формат' in events[-1]['message']
    assert_no_plaintext_secrets(tmp_path, events)


def test_pixiv_logout_blocks_next_job_without_reading_x_or_contacting_network(tmp_path):
    previous_x = save_sessions()
    vault.clear_session('pixiv')
    assert not vault.has_session('pixiv') and vault.has_session('x')
    events = []
    assert run_job(opts(tmp_path, mode='preview'), events.append, ImmediateControl(events.append)) == 1
    assert 'Pixiv' in events[-1]['message']
    assert vault.session_path('x').read_bytes() == previous_x
    assert_no_plaintext_secrets(tmp_path, events)
