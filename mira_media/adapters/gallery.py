"""Isolated gallery-dl X extractor and experimental Pixiv website adapter."""

import copy
import hashlib
import http.cookiejar
import itertools
import re
import threading
import time
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests

from mira_media.models import MediaItem
from mira_media.control import Cancelled
from .profiles import IMAGE_EXTENSIONS, parse_profile, validate_media_url


class AdapterError(RuntimeError):
    """An intentionally sanitized, user-readable source/transport error."""


_GALLERY_LOCK = threading.Lock()
_AUTH_ERROR = "Платформа отклонила доступ (HTTP 401/403). Проверьте права доступа и выполните вход заново."
_RATE_ERROR = "Платформа ограничила запросы (HTTP 429). Задание остановлено; повторите позже."


def _allowed_transport(platform, url):
    try:
        p = urlsplit(url)
        if (p.scheme != "https" or p.username is not None or p.password is not None
                or p.port not in (None, 443) or "\\" in url
                or any(ord(ch) < 32 for ch in url)):
            return False
        host = (p.hostname or "").lower()
    except (TypeError, ValueError):
        return False
    if platform == "x":
        return (host in {"x.com", "api.x.com"}
                or (host == "abs.twimg.com" and p.path.startswith("/responsive-web/client-web/"))
                or validate_media_url("x", url))
    if platform == "pixiv":
        return ((host in {"www.pixiv.net", "pixiv.net"} and p.path.startswith("/ajax/"))
                or validate_media_url("pixiv", url))
    return False


class GuardedSession(requests.Session):
    """One interruptible pace gate covers API calls, pages, scripts and files.

    Redirects are followed explicitly after validation. Credentials cannot be
    redirected to another host. No requests/netrc, proxy environment or browser
    credential discovery is enabled. A failed request gets at most two retries.
    """

    def __init__(self, platform, options, control):
        super().__init__()
        self.platform = platform
        self.options = options
        self.control = control
        self.trust_env = False
        self._last_request = 0.0
        self._signature = None
        self._same_count = 0
        self._calls = 0
        self.headers.update({
            "User-Agent": "MiraMediaDownloader/1.3 (gallery-dl; personal local media archive)",
            "Accept": "*/*",
            "Referer": "https://x.com/" if platform == "x" else "https://www.pixiv.net/",
        })

    def request(self, method, url, **kwargs):
        if not _allowed_transport(self.platform, url):
            raise AdapterError("Источник предложил неподдерживаемый адрес. Загрузка остановлена.")
        method = method.upper()
        # Only gallery-dl's normal guest activation needs POST; there is no login.
        if method not in {"GET", "HEAD"} and not (
                self.platform == "x" and method == "POST"
                and urlsplit(url).hostname == "api.x.com"
                and urlsplit(url).path == "/1.1/guest/activate.json"):
            raise AdapterError("Источник запросил неподдерживаемое действие.")
        kwargs["verify"] = True
        timeout = kwargs.get("timeout", 25)
        if isinstance(timeout, (list, tuple)) and len(timeout) == 2:
            kwargs["timeout"] = tuple(min(float(part or 25), 30) for part in timeout)
        else:
            kwargs["timeout"] = min(float(timeout or 25), 30)
        redirects = kwargs.pop("allow_redirects", True)
        kwargs.pop("proxies", None)
        signature = hashlib.sha256(repr((method, url, kwargs.get("params"))).encode()).digest()
        if signature == self._signature:
            self._same_count += 1
        else:
            self._signature, self._same_count = signature, 1
        if self._same_count > 3:
            raise AdapterError("Источник повторяет одну страницу без продвижения. Задание остановлено.")

        for redirect in range(4):
            for attempt in range(3 if method in {"GET", "HEAD"} else 1):
                self.control.check()
                delay = max(1.0, float(self.options.request_delay))
                remaining = delay - (time.monotonic() - self._last_request)
                if remaining > 0:
                    self.control.wait(remaining)
                self.control.check()
                self._calls += 1
                if self._calls > 50000:
                    raise AdapterError("Достигнут предел запросов одного задания. Продолжите новым запуском.")
                self._last_request = time.monotonic()
                try:
                    response = super().request(method, url, allow_redirects=False, **kwargs)
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                    if attempt == 2 or method not in {"GET", "HEAD"}:
                        raise AdapterError("Не удалось связаться с платформой после ограниченного числа попыток.") from None
                    self.control.wait(2.0 * (attempt + 1))
                    continue
                except requests.exceptions.RequestException:
                    raise AdapterError("Ошибка безопасного соединения с платформой.") from None
                if response.status_code in (401, 403):
                    response.close()
                    raise AdapterError(_AUTH_ERROR)
                if response.status_code == 429:
                    response.close()
                    raise AdapterError(_RATE_ERROR)
                if response.is_redirect:
                    target = urljoin(url, response.headers.get("Location", ""))
                    login_path = urlsplit(target).path.lower()
                    if any(token in login_path for token in ("/login", "/account/access", "/i/flow/")):
                        response.close()
                        raise AdapterError(_AUTH_ERROR)
                if response.status_code >= 500 and attempt < 2 and method in {"GET", "HEAD"}:
                    response.close()
                    self.control.wait(2.0 * (attempt + 1))
                    continue
                break
            if not (redirects and response.is_redirect):
                return response
            next_url = urljoin(url, response.headers.get("Location", ""))
            response.close()
            if (redirect >= 3 or not _allowed_transport(self.platform, next_url)
                    or urlsplit(next_url).hostname != urlsplit(url).hostname):
                raise AdapterError("Платформа перенаправила запрос за пределы разрешённого источника.")
            url = next_url
            kwargs.pop("params", None)
        raise AdapterError("Слишком много перенаправлений платформы.")


def _load_cookies(filename, platform):
    result = requests.cookies.RequestsCookieJar()
    if not filename:
        return result
    path = Path(filename)
    try:
        if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            raise AdapterError("Выберите локальный Netscape cookies.txt размером не более 10 МБ.")
        jar = http.cookiejar.MozillaCookieJar(str(path))
        # MozillaCookieJar can emit a traceback containing malformed cookie
        # values. Only our fixed error text may leave this local import step.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            jar.load(ignore_discard=True, ignore_expires=False)
    except (OSError, http.cookiejar.LoadError, ValueError):
        raise AdapterError("Не удалось прочитать cookies. Нужен локальный файл Netscape cookies.txt.") from None
    valid_domains = {"x.com", "twitter.com", "www.x.com", "www.twitter.com"} if platform == "x" else {"pixiv.net", "www.pixiv.net"}
    names = {"auth_token", "ct0"} if platform == "x" else {"PHPSESSID"}
    for cookie in jar:
        if cookie.domain.lstrip(".").lower() in valid_domains and cookie.name in names:
            cookie = copy.copy(cookie)
            cookie.domain = ".x.com" if platform == "x" else ".pixiv.net"
            cookie.domain_specified = cookie.domain_initial_dot = True
            cookie.secure = True
            result.set_cookie(cookie)
    return result


class _QuietLogger:
    """Never forward upstream exception text, cookies, URLs or payloads to disk/UI."""

    def __init__(self, log):
        self._log = log
        self._reported = set()

    def _message(self, level, *args, **kwargs):
        if level not in self._reported:
            self._reported.add(level)
            self._log(level, "Источник сообщил о пропуске или изменении данных; доступность может быть ограничена.")

    def warning(self, *args, **kwargs):
        self._message("warning")

    def error(self, *args, **kwargs):
        self._message("warning")

    def debug(self, *args, **kwargs):
        pass

    info = debug
    traceback = debug
    exception = debug


def _posted(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if not isinstance(value, datetime):
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class GalleryAdapter:
    """Common platform interface consumed by the download/checkpoint engine."""

    def __init__(self, profile, options, control, log):
        self.profile = parse_profile(profile.url, options.pixiv_enabled)
        self.options, self.control, self.log = options, control, log
        self.session = GuardedSession(self.profile.platform, options, control)
        try:
            if options.effective_auth_source == 'embedded':
                from mira_media.session_vault import load_x_session, load_session
                cookies, user_agent = (load_x_session() if self.profile.platform == 'x'
                                       else load_session(self.profile.platform))
                self.session.cookies.update(cookies)
                self.session.headers['User-Agent'] = user_agent
                cookies.clear()
                label = 'X' if self.profile.platform == 'x' else 'Pixiv'
                log('info', f'Подключён сохранённый вход {label}. Сессия расшифрована только в памяти текущего задания.')
            elif options.effective_auth_source == 'browser':
                from mira_media.browser_auth import load_browser_cookies
                cookies = load_browser_cookies(options.browser, options.browser_profile,
                                              self.profile.platform, control)
                self.session.cookies.update(cookies)
                cookies.clear()
                log('info', 'Сессия прочитана из выбранного профиля браузера локально. Cookies используются только в памяти.')
            elif options.effective_auth_source == 'file':
                self.session.cookies.update(_load_cookies(options.cookies_file, self.profile.platform))
        except Exception:
            self.session.close()
            raise
        self._closed = False
        self._active = None
        try:
            self._date_from = date.fromisoformat(options.date_from) if options.date_from else None
            self._date_to = date.fromisoformat(options.date_to) if options.date_to else None
        except ValueError:
            raise AdapterError("Дата должна иметь формат ГГГГ-ММ-ДД.") from None
        if self._date_from and self._date_to and self._date_from > self._date_to:
            raise AdapterError("Начальная дата должна предшествовать конечной.")

    def close(self):
        self._closed = True
        self.session.cookies.clear()
        self.session.close()

    def _in_dates(self, posted):
        if not self._date_from and not self._date_to:
            return True
        if not posted:
            return False
        current = date.fromisoformat(posted[:10])
        return ((self._date_from is None or current >= self._date_from)
                and (self._date_to is None or current <= self._date_to))

    def iter_media(self):
        self.control.check()
        if self._closed:
            raise AdapterError("Задание уже закрыто.")
        if self.profile.platform == "pixiv":
            yield from self._iter_pixiv()
        else:
            yield from self._iter_x()

    def _iter_x(self):
        from gallery_dl.extractor.twitter import TwitterMediaExtractor
        from gallery_dl.extractor.common import Message

        adapter = self
        settings = {
            "retweets": False, "quoted": False, "quoted-expand": False,
            "videos": False, "previews": False, "cards": False, "ads": False,
            "articles": False, "twitpic": False, "unavailable": False,
            "expand": False, "showmore": False, "showreplies": False,
            "replies": True, "pinned": False, "size": ["orig", "4096x4096", "large", "medium", "small"],
            "include": ["media"], "fallback": False, "logout": False,
            "ratelimit": "abort", "locked": "abort", "retries-api": 1,
            "retries": 0, "sleep-request": 0, "sleep-429": 0,
            "timeout": 25, "verify": True, "netrc": False,
            "cookies": None, "cookies-update": False, "username": None,
            "password": None, "proxy-env": False, "write-pages": False,
            "metadata-user": False, "unique": True, "cursor": True,
            "transform": True,
        }

        class IsolatedTwitter(TwitterMediaExtractor):
            def __init__(self, match):
                super().__init__(match)
                self.session = adapter.session
                self.log = _QuietLogger(adapter.log)
                self._memory = {}

            def config(self, key, default=None):
                return settings.get(key, default)

            def _get_auth_info(self, password=None):
                return None, None

            def cache(self, func, *args, _key=0, _exp=0, _mem=True):
                # The upstream disk/memory caches are intentionally bypassed.
                key = (func.__module__, func.__name__, repr(args if _key is not None else ()))
                if key not in self._memory:
                    self._memory[key] = func(*args)
                return self._memory[key]

            def sleep(self, seconds, reason):
                adapter.control.wait(max(0, float(seconds)))

            def wait(self, seconds=None, until=None, adjust=1.0, reason="rate limit"):
                raise AdapterError(_RATE_ERROR)

            def input(self, *args, **kwargs):
                raise AdapterError("Источник требует повторного входа. Нажмите «Войти в X» либо войдите в выбранном браузере заново.")

        # No global configuration is loaded or mutated. Serializing prevents
        # simultaneous upstream class-level transaction-key initialization.
        while not _GALLERY_LOCK.acquire(timeout=0.2):
            self.control.check()
        try:
            extractor = IsolatedTwitter.from_url(self.profile.url)
            if extractor is None:
                raise AdapterError("Версия backend не поддерживает медиагалерею X.")
            self._active = extractor
            seen = set()
            try:
                for message in extractor:
                    self.control.check()
                    kind = message[0]
                    if kind == Message.Queue:
                        # /media should be flat. Never trust dynamic child URLs.
                        raise AdapterError("Источник изменил формат галереи; требуется обновление приложения.")
                    if kind != Message.Url:
                        continue
                    _, url, metadata = message
                    item = self._x_item(url, metadata)
                    if item and item.key not in seen and self._in_dates(item.posted):
                        seen.add(item.key)
                        yield item
            except AdapterError:
                raise
            except Cancelled:
                raise
            except Exception as exc:
                # Keep control's Cancelled exception intact without importing
                # the engine or exposing arbitrary backend exception payloads.
                self.control.check()
                name = type(exc).__name__
                if name in {"AuthenticationError", "AuthorizationError", "AuthRequired"}:
                    raise AdapterError("X требует действующую авторизацию или не разрешает доступ. Нажмите «Войти в X» либо проверьте выбранный способ авторизации.") from None
                raise AdapterError("Не удалось прочитать медиагалерею X. Проверьте доступ в браузере, cookies и обновление backend.") from None
        finally:
            if self._active is not None:
                self._active._memory.clear()
            self._active = None
            _GALLERY_LOCK.release()

    def _x_item(self, url, metadata):
        if not validate_media_url("x", url) or metadata.get("type", "photo") != "photo":
            return None
        if parse_qs(urlsplit(url).query).get("name") != ["orig"]:
            return None
        # A post may quote another post while carrying the author's own photos.
        # Only the explicit expanded-quote marker excludes quoted media; author
        # and source matching below remain mandatory for every image.
        if metadata.get("retweet_id") or metadata.get("quote_by"):
            return None
        author = metadata.get("author") or {}
        if str(author.get("name", "")).casefold() != self.profile.username.casefold():
            return None
        source = metadata.get("source_user") or {}
        if metadata.get("source_id") and str(source.get("name", "")).casefold() != self.profile.username.casefold():
            return None
        author_id = str(author.get("id") or author.get("id_str") or "")
        if not re.fullmatch(r"[1-9][0-9]*", author_id):
            raise AdapterError("X не предоставил числовой ID автора. Загрузка остановлена для корректного выбора каталога.")
        post_id = str(metadata.get("tweet_id") or "")
        if not re.fullmatch(r"[1-9][0-9]*", post_id):
            return None
        p = urlsplit(url)
        stem = p.path.rsplit("/", 1)[-1].split(".", 1)[0]
        ext = str(metadata.get("extension") or parse_qs(p.query).get("format", [""])[0]).lower()
        if ext not in IMAGE_EXTENSIONS:
            return None
        fallback_urls = tuple(candidate for candidate in itertools.islice(metadata.get("_fallback") or (), 4)
                              if validate_media_url("x", candidate)
                              and urlsplit(candidate).path == p.path
                              and candidate != url)
        return MediaItem(key="x:" + stem, post_id=post_id,
                         index=max(1, int(metadata.get("num", 1))), url=url,
                         extension="jpg" if ext == "jpeg" else ext,
                         posted=_posted(metadata.get("date")), author_id=author_id,
                         fallback_urls=fallback_urls)

    def _pixiv_json(self, path, optional=False):
        self.control.check()
        response = self.session.get("https://www.pixiv.net/ajax/" + path, params={"lang": "en"})
        try:
            if response.status_code == 404 and optional:
                if self.options.effective_auth_source != 'none':
                    self._verify_pixiv_session()
                return None
            if response.status_code >= 400:
                raise AdapterError("Pixiv не предоставил запрошенные данные. Проверьте доступность в браузере.")
            data = response.json()
            if not isinstance(data, dict) or "body" not in data or type(data.get("error")) is not bool:
                raise AdapterError("Pixiv изменил формат ответа; поиск остановлен.")
            if data["error"]:
                if optional:
                    if self.options.effective_auth_source != 'none':
                        self._verify_pixiv_session()
                    return None
                raise AdapterError("Pixiv не предоставил галерею. Проверьте вход и доступность профиля на сайте.")
            return data["body"]
        except (ValueError, requests.exceptions.RequestException):
            raise AdapterError("Pixiv вернул неожиданные данные; требуется проверка поддержки платформы.") from None
        finally:
            response.close()

    def _verify_pixiv_session(self):
        """A restored guest/expired cookie must not silently yield a partial archive.

        This normal read-only website endpoint is available to the signed-in
        account only. Keep its body in memory and retain no account metadata.
        """
        message = "Pixiv не подтвердил вход. Войдите в Pixiv заново и повторите задание."
        if not any(cookie.name == 'PHPSESSID' and cookie.value for cookie in self.session.cookies):
            raise AdapterError(message)
        self.control.check()
        response = self.session.get('https://www.pixiv.net/ajax/user/extra', params={'lang': 'en'})
        try:
            if response.status_code != 200:
                raise AdapterError(message)
            try:
                data = response.json()
            except ValueError:
                raise AdapterError(message) from None
            if (not isinstance(data, dict) or data.get('error') is not False
                    or not isinstance(data.get('body'), dict)
                    or any(type(data['body'].get(key)) is not int or data['body'][key] < 0
                           for key in ('following', 'followers', 'mypixivCount'))):
                raise AdapterError(message)
        finally:
            response.close()
        self.log('info', 'Pixiv подтвердил вход для текущего задания. Доступность работ определяется аккаунтом и настройками сайта.')

    def _iter_pixiv(self):
        if self.options.effective_auth_source != 'none':
            self._verify_pixiv_session()
        else:
            self.log('warning', 'Pixiv без входа: часть публикаций может не отображаться. Для доступной вашему аккаунту галереи выполните вход.')
        self.log("warning", "Pixiv: загружаются явно возвращённые оригиналы иллюстраций и манги; ugoira пропускается.")
        body = self._pixiv_json(f"user/{self.profile.username}/profile/all")
        if not isinstance(body, dict) or not {'illusts', 'manga'} <= body.keys():
            raise AdapterError("Pixiv изменил формат галереи.")
        ids = set()
        for category in ("illusts", "manga"):
            values = body.get(category) or {}
            if not isinstance(values, dict):
                raise AdapterError("Pixiv изменил формат списка публикаций.")
            ids.update(key for key in values if re.fullmatch(r"[1-9][0-9]*", str(key)))
        skipped_posts = 0
        skipped_pages = 0
        skipped_ugoira = 0
        for post_id in sorted(ids, key=int, reverse=True):
            self.control.check()
            detail = self._pixiv_json("illust/" + str(post_id), optional=True)
            if detail is None:
                skipped_posts += 1
                self.log("warning", "Pixiv: недоступная публикация пропущена.")
                continue
            if not isinstance(detail, dict):
                raise AdapterError("Pixiv изменил формат публикации; поиск остановлен.")
            if str(detail.get("userId")) != self.profile.username:
                skipped_posts += 1
                continue
            if detail.get("illustType") == 2:
                skipped_ugoira += 1
                continue
            posted = _posted(detail.get("createDate") or detail.get("uploadDate"))
            if not self._in_dates(posted):
                continue
            pages = self._pixiv_json(f"illust/{post_id}/pages", optional=True)
            if not isinstance(pages, list):
                skipped_posts += 1
                self.log("warning", "Pixiv: изображения недоступной публикации пропущены.")
                continue
            expected = detail.get('pageCount')
            if type(expected) is int and expected >= 0 and expected != len(pages):
                self.log('warning', f'Pixiv: публикация {post_id} содержит {expected} страниц, сайт вернул {len(pages)}. Сохранены только доступные оригиналы.')
                skipped_pages += max(0, expected - len(pages))
            for index, page in enumerate(pages, 1):
                self.control.check()
                if not isinstance(page, dict) or not isinstance(page.get('urls'), dict):
                    raise AdapterError("Pixiv изменил формат страниц публикации; поиск остановлен.")
                url = page['urls'].get("original", "")
                if not validate_media_url("pixiv", url):
                    skipped_pages += 1
                    self.log("warning", "Pixiv: оригинал отсутствует или имеет неподдерживаемый адрес; пропуск.")
                    continue
                ext = urlsplit(url).path.rsplit(".", 1)[-1].lower()
                yield MediaItem(key=f"pixiv:{post_id}:p{index - 1}", post_id=str(post_id),
                                index=index, url=url, extension="jpg" if ext == "jpeg" else ext,
                                posted=posted, author_id=self.profile.username)
        if skipped_posts or skipped_pages or skipped_ugoira:
            self.log('warning', f'Pixiv: недоступных публикаций — {skipped_posts}; недоступных страниц — {skipped_pages}; анимаций ugoira — {skipped_ugoira}. Они не включены в число найденных изображений.')
