"""Auth-source plumbing: never touches actual browser profiles or the network."""
from pathlib import Path
import requests
import pytest

from mira_media.adapters import GalleryAdapter, parse_profile
from mira_media.control import Control
from mira_media.engine import run_job
from mira_media.models import JobOptions
from mira_media.store import Store


class ImmediateControl(Control):
    def wait(self, seconds):
        self.check()


def browser_options(root, **kw):
    return JobOptions(profile_url='https://x.com/tester',destination=str(root),
                      auth_source='browser',browser='firefox',browser_profile=str(root/'chosen-profile'),**kw)


def test_old_cookie_requests_keep_working_and_none_ignores_unused_file(tmp_path):
    cookies=tmp_path/'old-cookies.txt'
    cookies.write_text('# Netscape HTTP Cookie File\n')
    assert JobOptions.from_dict({'destination':str(tmp_path),'cookies_file':str(cookies)}).effective_auth_source=='file'
    explicit_none=JobOptions.from_dict({'destination':str(tmp_path),'auth_source':'none','cookies_file':str(tmp_path/'missing')})
    assert explicit_none.effective_auth_source=='none'


@pytest.mark.parametrize('source,browser,profile',[('unknown','',''),('browser','',''),('browser','other','x'),('browser','firefox','')])
def test_invalid_auth_selection_fails_before_network(tmp_path,source,browser,profile):
    opts=JobOptions(destination=str(tmp_path),auth_source=source,browser=browser,browser_profile=profile)
    with pytest.raises(ValueError):
        opts.validate()


def test_selected_browser_is_loaded_into_memory_only_and_cleared(tmp_path,monkeypatch):
    from mira_media import browser_auth
    opts=browser_options(tmp_path)
    jar=requests.cookies.RequestsCookieJar()
    jar.set('auth_token','test-sensitive-auth-value',domain='.x.com',path='/',secure=True)
    jar.set('ct0','test-sensitive-csrf-value',domain='.x.com',path='/',secure=True)
    calls=[]
    def load(browser,profile,platform,control):
        calls.append((browser,profile,platform))
        return jar
    monkeypatch.setattr(browser_auth,'load_browser_cookies',load)
    logs=[]
    adapter=GalleryAdapter(parse_profile(opts.profile_url),opts,ImmediateControl(),lambda level,message:logs.append(message))
    assert calls==[('firefox',opts.browser_profile,'x')]
    assert adapter.session.cookies.get('auth_token',domain='.x.com')=='test-sensitive-auth-value'
    assert not jar, 'Temporary imported jar must be cleared after session copy'
    assert not any('test-sensitive' in line for line in logs)
    adapter.close()
    assert not adapter.session.cookies


def test_browser_failure_has_no_anonymous_fallback(tmp_path,monkeypatch):
    from mira_media import browser_auth
    from mira_media.adapters.gallery import GuardedSession
    def denied(*args):
        raise browser_auth.BrowserCookieError('Браузер защищает сессию. Выберите Firefox или файл cookies.')
    monkeypatch.setattr(browser_auth,'load_browser_cookies',denied)
    def forbidden(*args,**kwargs):
        raise AssertionError('Network must not be attempted after browser import failure')
    monkeypatch.setattr(GuardedSession,'request',forbidden)
    events=[]
    code=run_job(browser_options(tmp_path),events.append,ImmediateControl(events.append))
    states=[event['state'] for event in events if event['type']=='state']
    assert code==1 and states==['authorizing','error']
    assert 'защищает' in events[-1]['message']


def test_browser_secrets_never_reach_history_logs_or_tasks(tmp_path,monkeypatch):
    from mira_media import browser_auth
    def load(*args):
        jar=requests.cookies.RequestsCookieJar()
        jar.set('auth_token','sentinel-private-session-xyz',domain='.x.com',path='/')
        return jar
    monkeypatch.setattr(browser_auth,'load_browser_cookies',load)
    monkeypatch.setattr(GalleryAdapter,'iter_media',lambda self:iter(()))
    events=[]
    assert run_job(browser_options(tmp_path),events.append,ImmediateControl(events.append))==0
    assert [e['state'] for e in events if e['type']=='state']==['authorizing','scanning','completed']
    store=Store(tmp_path)
    dump='\n'.join(store.db.iterdump())
    store.close()
    assert 'sentinel-private-session-xyz' not in dump
    assert not any('sentinel-private-session-xyz' in str(event) for event in events)
    for log in (tmp_path/'.mira'/'logs').glob('*.log'):
        assert 'sentinel-private-session-xyz' not in log.read_text(encoding='utf-8')
