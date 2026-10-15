from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import threading
import time
import subprocess
import sys

from PIL import Image
import pytest

from mira_media.control import Cancelled, Control
from mira_media.downloads import DownloadError, fetch_image, media_path
from mira_media.engine import run_job
from mira_media.locking import DestinationBusy, DestinationLock
from mira_media.models import JobOptions, MediaItem, within_dates
from mira_media.privacy import safe_message
from mira_media.store import Store


def jpeg(color):
    buffer = BytesIO()
    Image.new('RGB',(24,20),color).save(buffer,'JPEG')
    return buffer.getvalue()


RED, BLUE = jpeg('red'), jpeg('blue')


class FastControl(Control):
    def wait(self, seconds):
        self.check()


class Response:
    def __init__(self, data=RED, status=200, headers=None):
        self.data,self.status_code = data,status
        self.headers = {'Content-Type':'image/jpeg','Content-Length':str(len(data)),**(headers or {})}
    def iter_content(self,chunk_size):
        yield self.data[:100]
        yield self.data[100:]
    def close(self):
        pass


class Session:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
    def get(self,url,**kwargs):
        self.calls.append(url)
        value = self.responses.get(url,RED)
        return value if isinstance(value,Response) else Response(value)


def item(number,index=1,post='1234',date='2026-10-14T12:00:00Z',author='8888'):
    return MediaItem(f'x:image{number}',post,index,f'https://pbs.twimg.com/media/Image{number}?format=jpg&name=orig','jpg',date,author)


def factory(items,session=None,after=None):
    session = session or Session({})
    class Adapter:
        def __init__(self,profile,options,control,log):
            self.session = session
            self.control = control
        def iter_media(self):
            for count,media in enumerate(items):
                if after:
                    after(count,self.control)
                yield media
        def close(self):
            pass
    return Adapter


def options(tmp_path,**kwargs):
    return JobOptions(profile_url='https://x.com/tester',destination=str(tmp_path),**kwargs)


def run(opts,adapter,control=None):
    events = []
    code = run_job(opts,events.append,control or FastControl(events.append),adapter)
    return code,events


def final_stats(events):
    return [e for e in events if e['type']=='stats'][-1]


def test_preview_counts_every_distinct_image_and_dates_without_download(tmp_path):
    a,b,c = item(1),item(2,index=2),item(3,post='1235',date='2026-10-13T23:59:59Z')
    session = Session({})
    code,events = run(options(tmp_path,mode='preview',date_from='2026-10-14',date_to='2026-10-14'),factory([a,b,b,c],session))
    assert code==0
    assert final_stats(events)['found']==2
    assert final_stats(events)['downloaded']==0
    states = [event for event in events if event['type'] == 'state']
    assert states[0]['state'] == 'scanning' and states[0]['message'] == 'Поиск изображений · уточняем количество'
    assert states[-1]['state'] == 'completed' and states[-1]['message'] == 'Поиск завершён · найдено изображений: 2'
    assert not session.calls
    assert not list(tmp_path.rglob('*.jpg'))
    store = Store(tmp_path)
    assert len(store.queued(__import__('mira_media.adapters',fromlist=['parse_profile']).parse_profile('https://x.com/tester')))==2
    store.close()


def test_download_multi_image_content_dedup_and_numeric_folder(tmp_path):
    a,b,c = item(1),item(2,index=2),item(3,post='1235')
    session = Session({a.url:RED,b.url:BLUE,c.url:RED})
    code,events = run(options(tmp_path),factory([a,b,c,b],session))
    assert code==0
    stats = final_stats(events)
    assert (stats['found'],stats['downloaded'],stats['skipped'],stats['failed'])==(3,2,1,0)
    files = list((tmp_path/'X'/'8888').glob('*.jpg'))
    assert len(files)==2
    assert {x.name for x in files}=={'1234_01.jpg','1234_02.jpg'}
    assert not list(tmp_path.rglob('*.part'))


def test_only_new_skips_network_and_missing_file_is_repaired(tmp_path):
    a,b = item(1),item(2,index=2)
    first = Session({a.url:RED,b.url:BLUE})
    run(options(tmp_path),factory([a,b],first))
    second = Session({})
    _,events = run(options(tmp_path),factory([a,b],second))
    assert not second.calls
    assert final_stats(events)['skipped']==2
    (tmp_path/'X'/'8888'/'1234_02.jpg').unlink()
    third = Session({b.url:BLUE})
    _,events = run(options(tmp_path),factory([a,b],third))
    assert third.calls==[b.url]
    assert final_stats(events)['downloaded']==1


def test_stop_then_resume_same_job_preserves_count_and_downloads(tmp_path):
    a,b = item(1),item(2,index=2)
    def stop_after_first(count,control):
        if count==1:
            control.command('stop')
    opts=options(tmp_path)
    code,events=run(opts,factory([a,b],Session({a.url:RED,b.url:BLUE}),stop_after_first))
    assert events[-1]['state']=='stopped'
    assert events[-1]['message'] == 'Поиск остановлен · продолжение доступно в истории'
    store = Store(tmp_path)
    assert store.list_jobs()[0]['status']=='stopped'
    store.close()
    resumed = Session({b.url:BLUE})
    code,events=run(opts,factory([a,b],resumed))
    assert code==0 and resumed.calls==[b.url]
    assert (final_stats(events)['found'],final_stats(events)['downloaded'])==(2,2)
    store = Store(tmp_path)
    assert len(store.list_jobs())==1
    store.close()


@pytest.mark.parametrize('status',[401,403,429])
def test_auth_and_rate_limit_stop_without_fallback(tmp_path,status):
    a=replace(item(1),fallback_urls=('https://pbs.twimg.com/media/Image1?format=jpg&name=large',))
    session=Session({a.url:Response(status=status)})
    code,events=run(options(tmp_path),factory([a,item(2,index=2)],session))
    assert code==1 and len(session.calls)==1
    assert final_stats(events)['failed']==1
    assert not list(tmp_path.rglob('*.jpg'))


def test_404_uses_next_returned_resolution(tmp_path):
    fallback='https://pbs.twimg.com/media/Image1?format=jpg&name=4096x4096'
    a=replace(item(1),fallback_urls=(fallback,))
    session=Session({a.url:Response(status=404),fallback:RED})
    code,events=run(options(tmp_path),factory([a],session))
    assert code==0 and session.calls==[a.url,fallback]
    assert final_stats(events)['downloaded']==1


def test_corrupt_response_never_becomes_completed_file(tmp_path):
    a=item(1)
    code,events=run(options(tmp_path),factory([a],Session({a.url:b'<html>not image</html>'})))
    assert code==2 and events[-1]['state']=='partial'
    assert events[-1]['message'].startswith('Поиск завершён с ошибками: найдено 1, ошибок 1.')
    assert final_stats(events)['failed']==1
    assert not list(tmp_path.rglob('*.jpg'))


def test_recheck_mode_restores_corrupt_existing_file(tmp_path):
    a=item(1)
    run(options(tmp_path),factory([a]))
    saved=tmp_path/'X'/'8888'/'1234_01.jpg'
    saved.write_bytes(b'bad')
    run(options(tmp_path,only_new=False),factory([a]))
    assert saved.read_bytes()==RED


def test_rename_keeps_author_id_directory_and_dedup(tmp_path):
    a=item(1)
    run(options(tmp_path),factory([a]))
    renamed=options(tmp_path)
    renamed.profile_url='https://x.com/new_handle'
    session=Session({})
    _,events=run(renamed,factory([a],session))
    assert final_stats(events)['skipped']==1 and not session.calls
    assert len(list(tmp_path.rglob('*.jpg')))==1


def test_lock_blocks_competing_worker_and_releases(tmp_path):
    with DestinationLock(tmp_path):
        with pytest.raises(DestinationBusy):
            with DestinationLock(tmp_path):
                pass
    with DestinationLock(tmp_path):
        pass


def test_pause_stops_progress_and_stop_unblocks_it():
    events=[]
    control=Control(events.append)
    control.command('pause')
    stopped=threading.Event()
    def check():
        with pytest.raises(Cancelled):
            control.check()
        stopped.set()
    thread=threading.Thread(target=check)
    thread.start()
    time.sleep(.05)
    assert not stopped.is_set()
    assert any(e['state']=='paused' for e in events)
    control.command('stop')
    thread.join(1)
    assert stopped.is_set()


def test_date_filter_is_inclusive_utc():
    opts=JobOptions(date_from='2026-10-14',date_to='2026-10-14')
    assert within_dates('2026-10-15T00:30:00+02:00',opts)
    assert within_dates('2026-10-14T23:59:59Z',opts)
    assert not within_dates('2026-10-13T23:59:59Z',opts)
    assert not within_dates('',opts)


def test_none_options_from_gui_are_normalized(tmp_path):
    opts=JobOptions.from_dict(dict(profile_url='https://x.com/test',destination=str(tmp_path),date_from=None,date_to=None,cookies_file=None))
    assert opts.date_from==opts.date_to==opts.cookies_file==''


def test_path_traversal_never_creates_media_outside_root(tmp_path):
    with pytest.raises(DownloadError):
        media_path(tmp_path,'x',replace(item(1),author_id='../other'))


def test_logs_redact_secret_values_and_urls():
    message=safe_message('auth_token=SECRET ct0=TOKEN PHPSESSID=cookie-sentinel https://x.com/test?auth=secret')
    assert not any(value in message for value in ('SECRET','TOKEN','cookie-sentinel','?auth=secret'))


def test_corrupt_same_size_duplicate_is_not_reused(tmp_path):
    a=item(1)
    run(options(tmp_path),factory([a]))
    saved=tmp_path/'X'/'8888'/'1234_01.jpg'
    saved.write_bytes(b'X' * len(RED))
    b=item(2,post='9999')
    _,events=run(options(tmp_path),factory([b]))
    repaired=tmp_path/'X'/'8888'/'9999_01.jpg'
    assert repaired.read_bytes()==RED
    assert final_stats(events)['downloaded']==1


def test_db_never_stores_cookie_path_or_values(tmp_path):
    cookie_file=tmp_path/'private-cookies.txt'
    cookie_file.write_text('not read by fixture adapter')
    run(options(tmp_path,cookies_file=str(cookie_file),mode='preview'),factory([item(1)]))
    store=Store(tmp_path)
    dump='\n'.join(store.db.iterdump())
    assert 'private-cookies' not in dump and 'not read by fixture' not in dump
    store.close()


def test_forced_process_exit_recovers_checkpoint_and_os_lock(tmp_path):
    code = '''
import os,sys
from pathlib import Path
from io import BytesIO
from PIL import Image
from mira_media.adapters import parse_profile
from mira_media.models import JobOptions,MediaItem
from mira_media.store import Store
from mira_media.locking import DestinationLock
from mira_media.downloads import file_hash
root=Path(sys.argv[1])
with DestinationLock(root):
    store=Store(root)
    profile=parse_profile('https://x.com/tester')
    opts=JobOptions(profile_url=profile.url,destination=str(root))
    job=store.start_job(profile,opts)
    item=MediaItem('x:image1','1234',1,'https://pbs.twimg.com/media/Image1?format=jpg&name=orig','jpg','2026-10-14T12:00:00Z','8888')
    record=store.register(profile,item,job)
    path=root/'X'/'8888'/'1234_01.jpg'
    path.parent.mkdir(parents=True)
    Image.new('RGB',(24,20),'red').save(path,'JPEG')
    store.result(job,record['id'],'downloaded',path=str(path.relative_to(root)),sha256=file_hash(path),size=path.stat().st_size)
    store.stats(job)
    store.set_status(job,'downloading')
    os._exit(23)
'''
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path)],timeout=15)
    assert result.returncode==23
    store=Store(tmp_path)
    store.recover_interrupted()
    job=store.list_jobs()[0]
    assert job['status']=='interrupted' and job['downloaded']==1
    store.close()
    opts=options(tmp_path,job_id=job['id'])
    a,b=item(1),item(2,index=2)
    session=Session({b.url:BLUE})
    result,events=run(opts,factory([a,b],session))
    assert result==0 and session.calls==[b.url]
    assert final_stats(events)['found']==2 and final_stats(events)['downloaded']==2
