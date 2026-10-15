"""Built-in login/vault integration without real accounts or network requests."""
from pathlib import Path

import pytest
import requests

from mira_media.adapters import GalleryAdapter, parse_profile
from mira_media.adapters.gallery import GuardedSession
from mira_media.control import Control
from mira_media.engine import run_job
from mira_media.models import JobOptions
from mira_media.store import Store


class ImmediateControl(Control):
    def wait(self, seconds):
        self.check()


def opts(root, **extra):
    return JobOptions(profile_url='https://x.com/tester',destination=str(root),auth_source='embedded',**extra)


def test_embedded_options_need_no_browser_or_cookie_file(tmp_path):
    options=JobOptions.from_dict(dict(profile_url='https://x.com/tester',destination=str(tmp_path),auth_source='embedded'))
    assert options.effective_auth_source=='embedded'
    assert not options.browser and not options.browser_profile and not options.cookies_file


def test_saved_app_session_uses_same_user_agent_and_memory_jar(tmp_path,monkeypatch):
    from mira_media import session_vault
    jar=requests.cookies.RequestsCookieJar()
    jar.set('auth_token','synthetic-app-session',domain='.x.com',path='/',secure=True)
    jar.set('ct0','synthetic-app-csrf',domain='.x.com',path='/',secure=True)
    monkeypatch.setattr(session_vault,'load_x_session',lambda:(jar,'Mira QA actual browser User-Agent'))
    adapter=GalleryAdapter(parse_profile('https://x.com/tester'),opts(tmp_path),ImmediateControl(),lambda *args:None)
    assert adapter.session.headers['User-Agent']=='Mira QA actual browser User-Agent'
    assert adapter.session.cookies.get('auth_token',domain='.x.com')=='synthetic-app-session'
    assert not jar
    adapter.close()
    assert not adapter.session.cookies


def test_missing_app_session_stops_before_network_and_does_not_fallback(tmp_path,monkeypatch):
    monkeypatch.setenv('MIRA_SESSION_DIR',str(tmp_path/'isolated-vault'))
    def forbidden(*args,**kw):
        raise AssertionError('Network attempted without a saved app session')
    monkeypatch.setattr(GuardedSession,'request',forbidden)
    events=[]
    code=run_job(opts(tmp_path),events.append,ImmediateControl(events.append))
    assert code==1
    assert [event['state'] for event in events if event['type']=='state']==['authorizing','error']
    assert 'Войдите' in events[-1]['message']


def test_embedded_pixiv_requires_its_own_saved_session(tmp_path,monkeypatch):
    monkeypatch.setenv('MIRA_SESSION_DIR',str(tmp_path/'isolated-vault'))
    def forbidden(*args,**kw):
        raise AssertionError('Network attempted for unsupported login platform')
    monkeypatch.setattr(GuardedSession,'request',forbidden)
    options=opts(tmp_path,pixiv_enabled=True)
    options.profile_url='https://www.pixiv.net/users/123'
    events=[]
    assert run_job(options,events.append,ImmediateControl(events.append))==1
    assert 'Pixiv' in events[-1]['message'] and 'Войдите' in events[-1]['message']


def test_current_user_encrypted_session_reaches_job_without_disk_plaintext(tmp_path,monkeypatch):
    from mira_media import session_vault
    monkeypatch.setenv('MIRA_SESSION_DIR',str(tmp_path/'isolated-vault'))
    cookies=[dict(name=name,value=value,domain='.x.com',path='/',secure=True,expires=None)
             for name,value in [('auth_token','qa-app-token-private-sentinel'),('ct0','qa-app-csrf-private-sentinel')]]
    session_vault.save_x_session(cookies,'Mira QA browser')
    monkeypatch.setattr(GalleryAdapter,'iter_media',lambda self:iter(()))
    events=[]
    assert run_job(opts(tmp_path),events.append,ImmediateControl(events.append))==0
    assert [event['state'] for event in events if event['type']=='state']==['authorizing','scanning','completed']
    store=Store(tmp_path)
    dump='\n'.join(store.db.iterdump())
    store.close()
    for sentinel in ('qa-app-token-private-sentinel','qa-app-csrf-private-sentinel'):
        assert sentinel not in dump and sentinel not in str(events)
        for file in tmp_path.rglob('*'):
            if file.is_file():
                assert sentinel.encode() not in file.read_bytes()
    session_vault.clear_x_session()
    assert not session_vault.has_x_session()
    assert run_job(opts(tmp_path),events.append,ImmediateControl(events.append))==1
