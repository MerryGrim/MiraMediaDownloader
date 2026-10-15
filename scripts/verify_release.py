"""Exercise the actual Windows binary, its worker pipes and local state.

The default includes public login pages without credentials. UI-only releases
may use --offline to omit live requests. Neither mode claims an authenticated
profile archive was tested.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import threading
import time
import os
import base64
import ctypes
import sys

from PIL import Image


def worker(executable, root, name, pause_stop=False, settings=None, environment=None, expected_message=''):
    destination = root / name
    requests_dir = destination / '.mira' / 'tasks'
    requests_dir.mkdir(parents=True,exist_ok=True)
    task = requests_dir / 'test-request.json'
    options=dict(profile_url='https://x.com/NASA/media',destination=str(destination),mode='preview',request_delay=3.0,cookies_file='',auth_source='none')
    options.update(settings or {})
    task.write_text(json.dumps(options),encoding='utf-8')
    proc = subprocess.Popen([str(executable),'--worker',str(task)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW,env=environment)
    events=[]
    paused=threading.Event()
    def read():
        for line in iter(proc.stdout.readline,b''):
            try:
                value=json.loads(line.decode('utf-8'))
                events.append(value)
                if value.get('state')=='paused':
                    paused.set()
            except Exception:
                events.append({'type':'invalid'})
    reader=threading.Thread(target=read,daemon=True)
    reader.start()
    if pause_stop:
        proc.stdin.write(b'{"command":"pause"}\n')
        proc.stdin.flush()
        if not paused.wait(15):
            proc.kill()
            raise AssertionError('Packaged worker did not acknowledge pause')
        proc.stdin.write(b'{"command":"resume"}\n{"command":"stop"}\n')
        proc.stdin.flush()
    try:
        code=proc.wait(timeout=50)
    except subprocess.TimeoutExpired:
        proc.stdin.write(b'{"command":"stop"}\n')
        proc.stdin.flush()
        try:
            code=proc.wait(timeout=35)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise AssertionError('Packaged worker did not finish after stop')
    proc.stdin.close()
    reader.join(5)
    stderr=proc.stderr.read().decode('utf-8',errors='replace')
    assert not any(event['type']=='invalid' for event in events), 'Invalid worker JSON'
    assert not task.exists(), 'Task request was not consumed'
    states=[event.get('state') for event in events if event.get('type')=='state']
    assert states and states[-1] in {'stopped','error','completed'}, states
    if pause_stop:
        assert 'paused' in states and states[-1]=='stopped' and code==0, (states,code)
    else:
        assert not any('Неожиданная ошибка' in event.get('message','') for event in events), events
    if expected_message:
        assert code==1 and states==['authorizing','error'],states
        assert expected_message in events[-1].get('message',''),events
    assert not stderr.strip(), 'Unexpected stderr in packaged process'
    connection=sqlite3.connect(destination/'.mira'/'history.sqlite3')
    status,found=connection.execute('SELECT status,found FROM jobs ORDER BY updated_at DESC LIMIT 1').fetchone()
    connection.close()
    return {'exit_code':code,'states':states,'persisted_status':status,'found':found,'messages':[event['message'] for event in events if event.get('type')=='log']}


def protect_synthetic_key(key):
    """Current-user DPAPI roundtrip for generated QA data, never real sessions."""
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('length',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    crypt.CryptProtectData.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    crypt.CryptProtectData.restype=wintypes.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    kernel.LocalFree.restype=ctypes.c_void_p
    source=ctypes.create_string_buffer(key)
    incoming=Blob(len(key),ctypes.cast(source,ctypes.POINTER(ctypes.c_ubyte)))
    outgoing=Blob()
    assert crypt.CryptProtectData(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(outgoing))
    try:
        return ctypes.string_at(outgoing.data,outgoing.length)
    finally:
        kernel.LocalFree(outgoing.data)


def browser_fixtures(executable,root):
    """Actual packaged import against isolated synthetic SQLite profiles.

    Empty decrypted auth values deliberately stop BEFORE any network call.
    A missing-session error proves the native AES/DPAPI import ran successfully.
    """
    environment=dict(os.environ)
    environment['APPDATA']=str(root/'fixture-roaming')
    environment['LOCALAPPDATA']=str(root/'fixture-local')
    environment['PYTHONIOENCODING']='utf-8'
    ff=Path(environment['APPDATA'])/'Mozilla'/'Firefox'
    profile=ff/'Profiles'/'qa.default'
    profile.mkdir(parents=True,exist_ok=True)
    (ff/'profiles.ini').write_text('[Profile0]\nName=Mira QA\nIsRelative=1\nPath=Profiles/qa.default\n',encoding='utf-8')
    db=sqlite3.connect(profile/'cookies.sqlite')
    db.execute('CREATE TABLE moz_cookies(host TEXT,name TEXT,value TEXT,path TEXT,expiry INTEGER,isSecure INTEGER,originAttributes TEXT)')
    db.executemany('INSERT INTO moz_cookies VALUES(?,?,?,?,?,?,?)',[
        ('.x.com','auth_token','expired-synthetic-not-a-session','/',1,1,''),
        ('.unrelated.test','auth_token','unrelated-synthetic-sentinel','/',2147483647,1,'')])
    db.commit()
    db.close()
    before=hashlib.sha256((profile/'cookies.sqlite').read_bytes()).hexdigest()
    firefox=worker(executable,root,'browser-firefox',settings=dict(auth_source='browser',browser='firefox',browser_profile=str(profile)),environment=environment,expected_message='не найдена действующая сессия')
    assert before==hashlib.sha256((profile/'cookies.sqlite').read_bytes()).hexdigest()
    chrome=Path(environment['LOCALAPPDATA'])/'Google'/'Chrome'/'User Data'
    cp=chrome/'Default'
    (cp/'Network').mkdir(parents=True,exist_ok=True)
    key=os.urandom(32)
    state={'profile':{'info_cache':{'Default':{'name':'Mira QA'}}},'os_crypt':{'encrypted_key':base64.b64encode(b'DPAPI'+protect_synthetic_key(key)).decode('ascii')}}
    (chrome/'Local State').write_text(json.dumps(state),encoding='utf-8')
    database=cp/'Network'/'Cookies'
    db=sqlite3.connect(database)
    db.execute('CREATE TABLE cookies(host_key TEXT,name TEXT,value TEXT,encrypted_value BLOB,path TEXT,expires_utc INTEGER,top_frame_site_key TEXT)')
    db.execute('CREATE TABLE meta(key TEXT,value TEXT)')
    db.execute("INSERT INTO meta VALUES('version','24')")
    db.execute('INSERT INTO cookies VALUES(?,?,?,?,?,?,?)',('.x.com','auth_token','',b'v20protected-qa-placeholder','/',0,''))
    db.commit()
    db.close()
    protected=worker(executable,root,'browser-chrome-protected',settings=dict(auth_source='browser',browser='chrome',browser_profile=str(cp)),environment=environment,expected_message='App-Bound/v20')
    from Cryptodome.Cipher import AES
    nonce=os.urandom(12)
    cipher=AES.new(key,AES.MODE_GCM,nonce=nonce)
    ciphertext,tag=cipher.encrypt_and_digest(hashlib.sha256(b'.x.com').digest())
    db=sqlite3.connect(database)
    db.execute('UPDATE cookies SET encrypted_value=?',(b'v10'+nonce+ciphertext+tag,))
    db.commit()
    db.close()
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    aes=worker(executable,root,'browser-chrome-standard-crypto',settings=dict(auth_source='browser',browser='chrome',browser_profile=str(cp)),environment=environment,expected_message='не найдена действующая сессия')
    assert before==hashlib.sha256(database.read_bytes()).hexdigest()
    for result in (firefox,protected,aes):
        assert 'unrelated-synthetic-sentinel' not in json.dumps(result)
    return {'firefox_read_only':firefox,'chromium_app_bound_refused':protected,'chromium_standard_dpapi_aes':aes,'actual_user_cookies_accessed':False,'network_requests_in_browser_fixtures':0}


def login_probe(executable, directory, environment, *, platform='x', live=False, language='ru'):
    """Wait for the actual parent process, independent of child stdio handles."""
    directory.mkdir(parents=True, exist_ok=True)
    command=[str(executable),'--login-probe',str(directory),'--login-platform',platform,'--login-language',language]
    if live:
        command.append('--login-probe-live')
    started=time.monotonic()
    errors=directory/'process-stderr.log'
    with (directory/'process-stdout.log').open('wb') as output, errors.open('wb') as stderr:
        proc=subprocess.run(command, stdout=output, stderr=stderr, env=environment,
                            timeout=50, creationflags=subprocess.CREATE_NO_WINDOW)
    assert proc.returncode==0,errors.read_text(encoding='utf-8',errors='replace')[-1500:]
    result=json.loads((directory/'login-probe.json').read_text(encoding='utf-8'))
    assert all(result[name] for name in ('dialog_finished','browser_released','view_destroyed',
               'page_destroyed','profile_destroyed','post_close_heartbeat','app_loop_returned')),result
    result['parent_exit_code']=proc.returncode
    result['process_elapsed_seconds']=round(time.monotonic()-started,2)
    return result


def embedded_fixtures(executable,root,live_checks=True):
    """Verify the shipped renderer and current-user encrypted test vault."""
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from mira_media.session_vault import save_x_session, clear_x_session, session_path, save_session, clear_session
    vault=root/'isolated-app-session'
    previous=os.environ.get('MIRA_SESSION_DIR')
    os.environ['MIRA_SESSION_DIR']=str(vault)
    cookies=[dict(name=name,value=value,domain='.x.com',path='/',secure=True,expires=None)
             for name,value in [('auth_token','synthetic-exe-session-sentinel'),('ct0','synthetic-exe-csrf-sentinel')]]
    try:
        save_x_session(cookies,'Mira QA synthetic browser')
        save_session('pixiv',[dict(name='PHPSESSID',value='synthetic-pixiv-renderer-sentinel',
                                  domain='.pixiv.net',path='/',secure=True,expires=None)],
                     'Mira QA synthetic Pixiv browser')
        encrypted=session_path().read_bytes()
        assert b'synthetic-exe-session-sentinel' not in encrypted
        environment=dict(os.environ)
        environment['PYTHONIOENCODING']='utf-8'
        fixture=root/'embedded-renderer'
        renderer=login_probe(executable,fixture,environment)
        assert renderer['load_finished'] and renderer['off_the_record']
        assert renderer['cookie_policy']=='NoPersistentCookies' and renderer['cache_type']=='MemoryHttpCache'
        assert renderer['saved_session_available'] is True, 'Packaged process could not decode its current-user test vault'
        pixiv_fixture=root/'pixiv-embedded-renderer'
        pixiv_renderer=login_probe(executable,pixiv_fixture,environment,platform='pixiv')
        assert pixiv_renderer['saved_session_available'] and pixiv_renderer['off_the_record']
        assert not pixiv_renderer['save_button_enabled'], 'A saved/guest cookie alone must never enable Pixiv Save'
        locale_renderers = {}
        for language in ('en','zh_CN'):
            localized=login_probe(executable,root/('embedded-renderer-'+language),environment,
                                  platform='pixiv',language=language)
            assert localized['ui_language']==language and localized['load_finished']
            assert localized['saved_session_available'] and localized['off_the_record']
            assert localized['accept_language'].startswith('en-US')
            assert not any('\u0400' <= character <= '\u04ff' for character in localized['native_save_caption'])
            locale_renderers[language]=localized
        missing_env=dict(environment)
        missing_env['MIRA_SESSION_DIR']=str(root/'missing-app-session')
        missing=worker(executable,root,'embedded-missing-session',settings={'auth_source':'embedded'},environment=missing_env,expected_message='Войдите в X')
        missing_pixiv=worker(executable,root,'pixiv-embedded-missing-session',settings={'auth_source':'embedded','profile_url':'https://www.pixiv.net/users/20151243','pixiv_enabled':True},environment=missing_env,expected_message='Войдите в Pixiv')
        # Observe only the public login page. No account information is entered
        # and the off-the-record profile does not receive our synthetic vault.
        live_page = pixiv_page = None
        if live_checks:
            live=root/'embedded-live-page'
            live_env=dict(missing_env)
            live_page=login_probe(executable,live,live_env,live=True)
            assert live_page['official_x_origin'] and live_page['off_the_record']
            assert live_page['password_or_user_credentials_entered'] is False
            pixiv_live=root/'pixiv-live-page'
            pixiv_page=login_probe(executable,pixiv_live,live_env,platform='pixiv',live=True)
            assert pixiv_page['official_platform_origin'] and pixiv_page['off_the_record']
            assert pixiv_page['cookie_policy']=='NoPersistentCookies' and pixiv_page['cache_type']=='MemoryHttpCache'
            assert pixiv_page['password_or_user_credentials_entered'] is False
            assert not pixiv_page['save_button_enabled'] and not pixiv_page['saved_session_available']
            assert pixiv_page['login_text_visible'] and pixiv_page['english_login_text_visible']
            assert pixiv_page['accept_language'].startswith('en-US')
        return {'renderer_and_dpapi_vault':renderer,'localized_native_renderers':locale_renderers,'missing_session_no_fallback':missing,'live_login_page':live_page,'actual_account_login_tested':False,
                'pixiv':{'renderer_and_dpapi_vault':pixiv_renderer,'missing_session_no_fallback':missing_pixiv,'live_login_page':pixiv_page,'actual_account_login_tested':False}}
    finally:
        clear_x_session()
        clear_session('pixiv')
        if previous is None:
            os.environ.pop('MIRA_SESSION_DIR',None)
        else:
            os.environ['MIRA_SESSION_DIR']=previous


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('executable')
    parser.add_argument('output')
    parser.add_argument('--offline',action='store_true',help='Skip live platform requests for a UI-only release.')
    parser.add_argument('--design',action='store_true',help='Verify native design and popup contracts in this binary.')
    args=parser.parse_args()
    exe=Path(args.executable).resolve()
    root=Path(args.output).resolve()
    root.mkdir(parents=True,exist_ok=True)
    screenshot=root/'MiraMediaDownloader.png'
    proc=subprocess.run([str(exe),'--screenshot',str(screenshot)],timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    assert proc.returncode==0 and screenshot.is_file()
    with Image.open(screenshot) as image:
        size=image.size
        assert size[0]>=1000 and size[1]>=700
    design=None
    if args.design:
        design_root=root/'native-design'
        process=subprocess.run([str(exe),'--design-probe',str(design_root)],timeout=40,creationflags=subprocess.CREATE_NO_WINDOW)
        assert process.returncode==0,'Native design probe failed'
        design=json.loads((design_root/'design-probe.json').read_text(encoding='utf-8'))
        assert not design['errors'] and design['passed']
    result={'binary':str(exe),'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'native_gui_screenshot':{'path':str(screenshot),'size':size},'native_design':design,'worker_controls':worker(exe,root,'controls',True),'live_public_x_no_cookies':None if args.offline else worker(exe,root,'public-x',False),'browser_cookie_import':browser_fixtures(exe,root),'embedded_x_login':embedded_fixtures(exe,root,not args.offline),'offline':args.offline,'limits':'No actual user cookies or account credentials accessed. Crypto/session checks use isolated generated fixtures. Live account login and authorized X/Pixiv archives remain unverified in this release.'}
    (root/'release-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    # The Windows host console may still use cp1251; localized captions belong
    # in the UTF-8 JSON receipt, and escaped stdout works in every code page.
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
