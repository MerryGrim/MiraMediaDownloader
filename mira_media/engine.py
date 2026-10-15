from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import time

from .control import Cancelled, Control
from .downloads import DownloadError, fetch_image, file_hash, media_path
from .locking import DestinationLock
from .models import JobOptions, within_dates
from .privacy import safe_message
from .store import Store


def run_job(options: JobOptions, emit, control: Control | None = None, adapter_factory=None) -> int:
    from .adapters import AdapterError, GalleryAdapter, parse_profile, validate_media_url
    options.validate()
    profile = parse_profile(options.profile_url, options.pixiv_enabled)
    options.profile_url = profile.url
    control = control or Control(emit)
    root = Path(options.destination).resolve()
    with DestinationLock(root):
        store = Store(root)
        adapter = None
        log_file = None
        job_id = ''
        original_control_emit = control.emit
        try:
            job_id = store.start_job(profile, options)
            options.job_id = job_id
            log_dir = root / '.mira' / 'logs'
            log_dir.mkdir(exist_ok=True)
            log_file = (log_dir / f'job-{job_id}.log').open('a', encoding='utf-8')

            def log(level, message):
                message = safe_message(message)
                log_file.write(f'{datetime.now(timezone.utc).isoformat(timespec="seconds")} [{level}] {message}\n')
                log_file.flush()
                emit({'type':'log','level':level,'message':message})

            def state(value, message):
                store.set_status(job_id,value,message)
                emit({'type':'state','state':value,'message':message,'job_id':job_id})

            def control_state(event):
                if event.get('type') == 'state':
                    store.set_status(job_id,event['state'],event.get('message',''))
                emit(event)
            control.emit = control_state

            last_stats = 0.0
            def stats(force=False):
                nonlocal last_stats
                if not force and time.monotonic() - last_stats < 0.15:
                    return None
                last_stats = time.monotonic()
                result = store.stats(job_id)
                emit({'type':'stats',**result})
                return result

            auth_messages = {'browser':'Читаем сессию из выбранного браузера локально',
                             'embedded':'Подключаем сохранённый вход ' + ('Pixiv' if profile.platform == 'pixiv' else 'X')}
            state('authorizing' if options.effective_auth_source in auth_messages else 'scanning',
                  auth_messages.get(options.effective_auth_source, 'Поиск изображений · уточняем количество'))
            stats()
            log('info','Предпросмотр: считаем доступные изображения без загрузки оригиналов.' if options.mode == 'preview' else 'Задание запущено. Очередь и результаты сохраняются после каждого изображения.')
            adapter = (adapter_factory or GalleryAdapter)(profile,options,control,log)
            if options.effective_auth_source in ('browser','embedded'):
                state('scanning','Поиск изображений · уточняем количество')
            seen = set()
            unknown_dates = 0
            # Always obtain fresh original URLs. Replaying the timeline safely
            # handles expired URLs and changed pagination without losing media.
            for item in adapter.iter_media():
                control.check()
                if not within_dates(item.posted,options):
                    if not item.posted:
                        unknown_dates += 1
                    continue
                identity = (item.author_id,item.key)
                if identity in seen:
                    continue
                seen.add(identity)
                # Validate identifiers before adding untrusted metadata to disk.
                target = media_path(root,profile.platform,item)
                record = store.register(profile,item,job_id)
                outcome = store.db.execute('SELECT outcome FROM job_items WHERE job_id=? AND media_id=?',(job_id,record['id'])).fetchone()[0]
                local = root / record['path'] if record['path'] else None
                exists = bool(local and local.resolve().is_relative_to(root) and local.is_file() and local.stat().st_size == record['size'])
                emit({'type':'item','key':item.key,'post_id':item.post_id,'author_id':item.author_id,'platform':profile.platform,'username':profile.username,'path':str(local) if exists else '', 'index':item.index})
                stats()
                if options.mode == 'preview':
                    continue
                if options.only_new and exists:
                    if outcome not in ('downloaded','skipped'):
                        store.result(job_id,record['id'],'skipped',path=record['path'],sha256=record['sha256'],size=record['size'])
                    stats()
                    continue
                try:
                    state('downloading',f'Загрузка · пост {item.post_id}, изображение {item.index}')
                    part,digest,size = fetch_image(adapter.session,item,profile.platform,target,control,emit,options.download_delay,validate_media_url)
                    duplicate = store.duplicate(profile.platform,item.author_id,digest,record['id'])
                    if duplicate:
                        part.unlink(missing_ok=True)
                        store.result(job_id,record['id'],'skipped',path=duplicate['path'],sha256=digest,size=size)
                        saved = root / duplicate['path']
                        log('info',f'Пост {item.post_id}: одинаковое содержимое уже есть, дополнительный файл не создан.')
                    else:
                        # Preserve unrelated files that happen to use our filename.
                        if target.exists() and record['path'] != str(target.relative_to(root)) and file_hash(target) != digest:
                            target = target.with_name(f'{target.stem}_{digest[:10]}{target.suffix}')
                        control.check()
                        os.replace(part,target)
                        saved = target
                        store.result(job_id,record['id'],'downloaded',path=str(saved.relative_to(root)),sha256=digest,size=size)
                    emit({'type':'item','key':item.key,'post_id':item.post_id,'author_id':item.author_id,'platform':profile.platform,'username':profile.username,'path':str(saved),'index':item.index})
                except (DownloadError,AdapterError) as exc:
                    log('error',f'Пост {item.post_id}, изображение {item.index}: {exc}')
                    store.result(job_id,record['id'],'failed',error=safe_message(exc))
                    if isinstance(exc,AdapterError) or exc.fatal:
                        raise
                stats()
                state('scanning','Продолжаем поиск · общее число ещё уточняется')
            if unknown_dates:
                log('warning',f'Не удалось определить дату у {unknown_dates} изображений: исключены фильтром периода.')
            result = stats(True)
            if result['failed']:
                state('partial',f'Поиск завершён с ошибками: найдено {result["found"]}, ошибок {result["failed"]}. Повторите для загрузки пропущенных.')
                return 2
            state('completed',f'Поиск завершён · найдено изображений: {result["found"]}')
            log('info','Количество относится только к изображениям, которые платформа вернула для текущего доступа и периода. Полнота всей истории не гарантируется.')
            return 0
        except Cancelled:
            if job_id:
                emit({'type':'stats',**store.stats(job_id)})
                store.set_status(job_id,'stopped','Поиск остановлен. Состояние сохранено.')
            emit({'type':'state','state':'stopped','message':'Поиск остановлен · продолжение доступно в истории'})
            return 0
        except Exception as exc:
            if isinstance(exc,(DownloadError,AdapterError,ValueError)):
                message = safe_message(exc)
            elif isinstance(exc,OSError):
                message = 'Не удалось записать данные. Проверьте свободное место и доступ к выбранной папке.'
            else:
                message = f'Неожиданная ошибка ({type(exc).__name__}). Состояние сохранено; повторите задание.'
            if job_id:
                emit({'type':'stats',**store.stats(job_id)})
                store.set_status(job_id,'error',message)
            if log_file:
                log_file.write(f'[error] {message}\n')
                log_file.flush()
            emit({'type':'log','level':'error','message':message})
            emit({'type':'state','state':'error','message':message})
            return 1
        finally:
            control.emit = original_control_emit
            if adapter:
                adapter.close()
            if log_file:
                log_file.close()
            store.close()
