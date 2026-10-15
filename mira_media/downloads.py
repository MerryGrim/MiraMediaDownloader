from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import time
from urllib.parse import urljoin

from PIL import Image, UnidentifiedImageError
import requests

from .control import Cancelled
from .models import MediaItem


class DownloadError(Exception):
    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def media_path(root: Path, platform: str, item: MediaItem) -> Path:
    if not re.fullmatch(r'[0-9]{1,30}', item.author_id):
        raise DownloadError('Платформа не вернула числовой ID автора. Загрузка остановлена.', True)
    if not re.fullmatch(r'[0-9]{1,30}', item.post_id) or not 0 < item.index < 100000:
        raise DownloadError('Платформа вернула некорректный идентификатор изображения.', True)
    ext = item.extension.lower().lstrip('.')
    if ext == 'jpeg':
        ext = 'jpg'
    if ext not in ('jpg','png','webp','gif','avif'):
        raise DownloadError('Неподдерживаемый формат изображения.')
    folder = {'x':'X', 'pixiv':'Pixiv'}.get(platform)
    if not folder:
        raise DownloadError('Неизвестная платформа.', True)
    result = root / folder / item.author_id / f'{item.post_id}_{item.index:02d}.{ext}'
    if not result.resolve().is_relative_to(root.resolve()):
        raise DownloadError('Путь выходит за пределы выбранной папки.', True)
    return result


def fetch_image(session, item, platform, target, control, emit, delay, validate_url):
    """Restart an unfinished image; publish only verified, completely received files."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + '.part')
    urls = [item.url] + list(item.fallback_urls)
    url_index = 0
    for attempt in range(3):
        control.wait(delay if attempt == 0 else max(5,delay) * attempt)
        response = None
        try:
            url = urls[url_index]
            for redirects in range(4):
                if not validate_url(platform, url):
                    raise DownloadError('Адрес изображения не принадлежит разрешённому медиасерверу.', True)
                control.check()
                response = session.get(url,stream=True,timeout=(10,25),allow_redirects=False)
                if response.status_code in (301,302,303,307,308):
                    next_url = urljoin(url,response.headers.get('Location',''))
                    response.close()
                    response = None
                    if redirects == 3:
                        raise DownloadError('Слишком много перенаправлений медиасервера.')
                    url = next_url
                    control.wait(delay)
                    continue
                break
            status = response.status_code
            if status in (401,403):
                raise DownloadError(f'Медиасервер ограничил доступ (HTTP {status}). Проверьте свою авторизацию и повторите позже.', True)
            if status == 429:
                raise DownloadError('Достигнут лимит запросов (HTTP 429). Состояние сохранено; продолжите позже.', True)
            if status == 404 and url_index + 1 < len(urls):
                response.close()
                response = None
                # Only ordinary, extractor-supplied resolutions of this image.
                # Auth failures and rate limits never trigger a fallback.
                from dataclasses import replace
                emit({'type':'log','level':'warning','message':'Оригинальный размер не найден (HTTP 404). Проверяем следующий доступный размер.'})
                next_item = replace(item,url=urls[url_index+1],fallback_urls=tuple(urls[url_index+2:]))
                return fetch_image(session,next_item,platform,target,control,emit,delay,validate_url)
            if status >= 500:
                raise requests.ConnectionError('server unavailable')
            if status != 200:
                raise DownloadError(f'Изображение недоступно (HTTP {status}).')
            mime = response.headers.get('Content-Type','').split(';')[0].strip().lower()
            if mime and not (mime.startswith('image/') or mime == 'application/octet-stream'):
                raise DownloadError('Вместо изображения сервер вернул другой тип данных.')
            try:
                total = int(response.headers.get('Content-Length',0))
            except ValueError:
                total = 0
            if total > 512 * 1024 * 1024:
                raise DownloadError('Изображение превышает предел 512 МБ.')
            digest = hashlib.sha256()
            size = 0
            notified = 0.0
            with part.open('wb') as output:
                for chunk in response.iter_content(chunk_size=64*1024):
                    control.check()
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > 512 * 1024 * 1024:
                        raise DownloadError('Изображение превышает предел 512 МБ.')
                    output.write(chunk)
                    digest.update(chunk)
                    if time.monotonic() - notified > 0.15:
                        emit({'type':'progress','current':size,'total':total})
                        notified = time.monotonic()
                output.flush()
                os.fsync(output.fileno())
            # Content-Length can describe encoded bytes; compare only identity bodies.
            if not size or (total and not response.headers.get('Content-Encoding') and size != total):
                raise requests.ConnectionError('incomplete response')
            try:
                with Image.open(part) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                raise DownloadError('Полученное изображение повреждено или имеет неподдерживаемый формат.') from exc
            emit({'type':'progress','current':size,'total':size})
            return part, digest.hexdigest(), size
        except (requests.RequestException, TimeoutError) as exc:
            if attempt == 2:
                raise DownloadError('Сеть недоступна или ответ прервался. Повторите задание для продолжения.') from exc
            emit({'type':'log','level':'warning','message':f'Сетевой сбой: повтор {attempt + 1} из 2 после задержки.'})
        finally:
            if response is not None:
                response.close()
    raise DownloadError('Не удалось загрузить изображение.')
