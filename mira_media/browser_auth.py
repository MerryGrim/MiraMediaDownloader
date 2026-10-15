"""Explicit, local, current-user browser session import.

Only the selected site's authentication cookies are queried. Database access is
read-only and respects ordinary browser locks. No browser process is stopped,
no cookie database is copied, and Chromium app-bound encryption is not bypassed.
"""

from __future__ import annotations

import base64
import configparser
import copy
import ctypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time

import requests


class BrowserCookieError(ValueError):
    """A fixed, safe message that never includes browser data or cookie values."""


@dataclass(frozen=True)
class BrowserProfile:
    browser: str
    profile_id: str
    label: str
    path: str


BROWSER_LABELS = {"firefox": "Firefox", "chrome": "Chrome", "edge": "Edge", "brave": "Brave"}
_CHROMIUM_PATHS = {
    "chrome": ("Google", "Chrome", "User Data"),
    "edge": ("Microsoft", "Edge", "User Data"),
    "brave": ("BraveSoftware", "Brave-Browser", "User Data"),
}
_RULES = {
    "x": (("x.com", ".x.com", "twitter.com", ".twitter.com"), ("auth_token", "ct0"), "auth_token", ".x.com"),
    "pixiv": (("pixiv.net", ".pixiv.net", "www.pixiv.net", ".www.pixiv.net"), ("PHPSESSID",), "PHPSESSID", ".pixiv.net"),
}
_DB_ERROR = ("Не удалось прочитать cookies выбранного профиля. Браузер мог заблокировать базу или изменить её формат. "
             "Попробуйте Firefox либо собственный файл cookies; приложение не снимает блокировки браузера.")
_PROTECTED_ERROR = ("Браузер защищает выбранную сессию шифрованием, привязанным к приложению (App-Bound/v20). "
                    "Mira не обходит эту защиту. Выберите профиль Firefox либо собственный файл cookies.")
_DECRYPT_ERROR = ("Не удалось расшифровать cookies обычным механизмом Windows для текущего пользователя. "
                  "Выберите профиль Firefox либо собственный файл cookies.")


def _browser_name(browser: str) -> str:
    if browser not in BROWSER_LABELS:
        raise BrowserCookieError("Этот браузер не поддерживается. Выберите Firefox, Chrome, Edge или Brave.")
    return browser


def _rules(platform: str):
    try:
        return _RULES[platform]
    except (KeyError, TypeError):
        raise BrowserCookieError("Неизвестная платформа для импорта cookies.") from None


def _check(control) -> None:
    if control is not None:
        control.check()


def _label(value: str, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    return " ".join(value.split())[:100] or fallback


def _json_metadata(path: Path) -> dict:
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, UnicodeError, ValueError):
        return {}


def _chromium_root(browser: str) -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    return Path(local).joinpath(*_CHROMIUM_PATHS[browser]) if local else None


def discover_profiles(browser: str) -> list[BrowserProfile]:
    """Read profile metadata only; never open cookie databases during discovery.

    IDs are absolute profile paths. Loading requires a fresh discovery match, so
    an arbitrary path supplied in a saved job cannot become a cookie source.
    Firefox uses only normal/default-container cookies in the selected profile.
    """
    browser = _browser_name(browser)
    result = []
    if browser == "firefox":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return result
        base = Path(appdata) / "Mozilla" / "Firefox"
        ini = base / "profiles.ini"
        parser = configparser.ConfigParser(interpolation=None)
        try:
            if ini.stat().st_size > 1024 * 1024:
                return result
            parser.read_string(ini.read_text(encoding="utf-8-sig"))
            seen = set()
            for section in parser.sections():
                if not section.startswith("Profile"):
                    continue
                raw_path = parser.get(section, "Path", fallback="")
                if not raw_path:
                    continue
                path = Path(raw_path)
                if parser.get(section, "IsRelative", fallback="1") == "1":
                    path = base / path
                if not path.is_absolute():
                    continue
                path = path.resolve()
                key = str(path)
                if key in seen or not path.is_dir():
                    continue
                seen.add(key)
                name = _label(parser.get(section, "Name", fallback=""), section)
                result.append(BrowserProfile(browser, key, f"{name} · {path.name}", key))
        except (OSError, UnicodeError, ValueError, configparser.Error):
            return []
    else:
        root = _chromium_root(browser)
        if root is None or not root.is_dir():
            return []
        metadata = _json_metadata(root / "Local State")
        profile_info = metadata.get("profile", {})
        cache = profile_info.get("info_cache", {}) if isinstance(profile_info, dict) else {}
        if not isinstance(cache, dict):
            cache = {}
        try:
            candidates = sorted(root.iterdir(), key=lambda p: p.name.casefold())
            for path in candidates:
                if not re.fullmatch(r"Default|Profile [0-9]+", path.name) or not path.is_dir():
                    continue
                data = cache.get(path.name, {})
                name = _label(data.get("name", "") if isinstance(data, dict) else "", path.name)
                key = str(path.resolve())
                result.append(BrowserProfile(browser, key, f"{name} · {path.name}", key))
        except OSError:
            return []
    return result


def _connection(path: Path) -> sqlite3.Connection:
    connection = None
    try:
        if not path.is_file():
            raise BrowserCookieError("В выбранном профиле не найдена база cookies. Войдите на сайт в этом профиле браузера.")
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.15)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA temp_store=MEMORY")
        return connection
    except (OSError, sqlite3.Error):
        if connection is not None:
            connection.close()
        raise BrowserCookieError(_DB_ERROR) from None


def _selected_rows(connection, table, columns, domains, names, expiry_name, threshold, extra=""):
    # All identifiers originate in fixed module constants. Only selected site,
    # cookie names, root path and active sessions are materialized into Python.
    domain_column = "host" if table == "moz_cookies" else "host_key"
    sql = (f"SELECT {columns} FROM {table} WHERE {domain_column} IN ({','.join('?' for _ in domains)}) "
           f"AND name IN ({','.join('?' for _ in names)}) AND path='/' "
           f"AND ({expiry_name}=0 OR {expiry_name}>?) {extra} LIMIT 129")
    rows = connection.execute(sql, (*domains, *names, threshold)).fetchall()
    if len(rows) > 128:
        raise BrowserCookieError("В профиле слишком много подходящих записей cookies. Выберите другой собственный профиль.")
    return rows


def _firefox_rows(path, platform):
    domains, names, _, _ = _rules(platform)
    connection = _connection(path / "cookies.sqlite")
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(moz_cookies)")}
        if not {"host", "name", "value", "path", "expiry", "isSecure"}.issubset(columns):
            raise BrowserCookieError(_DB_ERROR)
        # Ignore containers, private sessions and partitioned storage. Choosing a
        # browser profile must never silently choose a different container login.
        extra = "AND originAttributes IN ('', '^userContextId=0')" if "originAttributes" in columns else ""
        rows = _selected_rows(connection, "moz_cookies", "host,name,value,expiry", domains, names,
                              "expiry", int(time.time()), extra)
        return [(domain, name, value, int(expiry) or None) for domain, name, value, expiry in rows]
    except BrowserCookieError:
        raise
    except (sqlite3.Error, TypeError, ValueError, OverflowError):
        raise BrowserCookieError(_DB_ERROR) from None
    finally:
        connection.close()


def _unprotect(data: bytes) -> bytes:
    """Ordinary current-user Windows DPAPI; no elevation or app-bound services."""
    if os.name != "nt":
        raise BrowserCookieError(_DECRYPT_ERROR)
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    # CRYPTPROTECT_UI_FORBIDDEN suppresses OS prompts; current-user context only.
    if not crypt32.CryptUnprotectData(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise BrowserCookieError(_DECRYPT_ERROR)
    try:
        return ctypes.string_at(outgoing.data, outgoing.length)
    finally:
        kernel32.LocalFree(outgoing.data)


def _chromium_key(profile: Path) -> bytes:
    metadata = _json_metadata(profile.parent / "Local State")
    try:
        encoded = metadata["os_crypt"]["encrypted_key"]
        key = base64.b64decode(encoded, validate=True)
        if not key.startswith(b"DPAPI"):
            raise BrowserCookieError(_DECRYPT_ERROR)
        result = _unprotect(key[5:])
        if len(result) not in (16, 24, 32):
            raise BrowserCookieError(_DECRYPT_ERROR)
        return result
    except BrowserCookieError:
        raise
    except (KeyError, TypeError, ValueError):
        raise BrowserCookieError(_DECRYPT_ERROR) from None


def _decrypt_cookie(encrypted: bytes, domain: str, version: int, key: bytes | None) -> str:
    if encrypted.startswith(b"v20"):
        raise BrowserCookieError(_PROTECTED_ERROR)
    try:
        if encrypted[:3] in (b"v10", b"v11"):
            if key is None or len(encrypted) < 31:
                raise BrowserCookieError(_DECRYPT_ERROR)
            from Cryptodome.Cipher import AES
            cipher = AES.new(key, AES.MODE_GCM, nonce=encrypted[3:15])
            value = cipher.decrypt_and_verify(encrypted[15:-16], encrypted[-16:])
        else:
            value = _unprotect(encrypted)
        if version >= 24:
            prefix = hashlib.sha256(domain.encode("utf-8")).digest()
            if not value.startswith(prefix):
                raise BrowserCookieError(_DECRYPT_ERROR)
            value = value[32:]
        return value.decode("utf-8")
    except BrowserCookieError:
        raise
    except (ImportError, OSError, ValueError, TypeError):
        raise BrowserCookieError(_DECRYPT_ERROR) from None


def _chromium_rows(path, platform, control):
    domains, names, _, _ = _rules(platform)
    database = path / "Network" / "Cookies"
    if not database.is_file():
        database = path / "Cookies"
    connection = _connection(database)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(cookies)")}
        if not {"host_key", "name", "value", "encrypted_value", "path", "expires_utc"}.issubset(columns):
            raise BrowserCookieError(_DB_ERROR)
        extra = "AND top_frame_site_key=''" if "top_frame_site_key" in columns else ""
        rows = _selected_rows(connection, "cookies", "host_key,name,value,encrypted_value,expires_utc", domains,
                              names, "expires_utc", int((time.time() + 11644473600) * 1000000), extra)
        # Check every relevant active cookie before decrypting any key. An
        # app-bound session must fail, never fall back to an anonymous request.
        if any(bytes(row[3] or b"").startswith(b"v20") for row in rows):
            raise BrowserCookieError(_PROTECTED_ERROR)
        version = 0
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
            record = connection.execute("SELECT value FROM meta WHERE key='version'").fetchone()
            version = int(record[0]) if record else 0
        key = None
        if any(not row[2] and bytes(row[3] or b"")[:3] in (b"v10", b"v11") for row in rows):
            _check(control)
            key = _chromium_key(path)
        result = []
        for domain, name, plaintext, encrypted, expiry in rows:
            _check(control)
            if not plaintext and not encrypted:
                continue
            value = plaintext or _decrypt_cookie(bytes(encrypted or b""), domain, version, key)
            expires = max(1, int(int(expiry) / 1000000 - 11644473600)) if int(expiry) else None
            result.append((domain, name, value, expires))
        return result
    except BrowserCookieError:
        raise
    except (sqlite3.Error, OSError, TypeError, ValueError, OverflowError):
        raise BrowserCookieError(_DB_ERROR) from None
    finally:
        connection.close()


def filter_cookie_jar(jar, platform: str) -> requests.cookies.RequestsCookieJar:
    """Keep only active platform auth cookies, canonicalized for the adapter.

    Conflicting root-domain sessions are rejected rather than selecting a
    different account. The returned jar is memory-only and carries no unrelated
    browsing cookies. auth_token/PHPSESSID validation belongs to browser import;
    this helper also supports an optional file with public/guest cookies.
    """
    domains, names, _, canonical = _rules(platform)
    result = requests.cookies.RequestsCookieJar()
    values = {}
    now = time.time()
    for cookie in jar:
        if cookie.domain.lower() not in domains or cookie.name not in names or cookie.path != "/":
            continue
        if cookie.expires is not None and cookie.expires <= now:
            continue
        if not isinstance(cookie.value, str) or not cookie.value:
            continue
        if len(cookie.value) > 16384 or any(ord(char) < 32 or ord(char) == 127 for char in cookie.value):
            raise BrowserCookieError("Некорректные данные сессии браузера. Войдите на сайт заново.")
        previous = values.get(cookie.name)
        if previous is not None and previous != cookie.value:
            raise BrowserCookieError("В выбранном профиле найдены разные сессии сайта. Выберите другой профиль или войдите на сайт заново.")
        values[cookie.name] = cookie.value
        item = copy.copy(cookie)
        item.domain = canonical
        item.domain_specified = True
        item.domain_initial_dot = True
        item.path = "/"
        item.secure = True
        result.set_cookie(item)
    return result


def load_browser_cookies(browser: str, profile_id: str, platform: str, control=None) -> requests.cookies.RequestsCookieJar:
    browser = _browser_name(browser)
    _, _, required, _ = _rules(platform)
    _check(control)
    selected = next((profile for profile in discover_profiles(browser) if profile.profile_id == profile_id), None)
    if selected is None:
        raise BrowserCookieError("Выбранный профиль браузера не найден. Обновите список и выберите собственный профиль.")
    _check(control)
    try:
        path = Path(selected.path)
        rows = _firefox_rows(path, platform) if browser == "firefox" else _chromium_rows(path, platform, control)
        jar = requests.cookies.RequestsCookieJar()
        seen = {}
        for domain, name, value, expiry in rows:
            _check(control)
            # CookieJar replaces duplicate domain/name/path entries. Detect
            # contradictory rows first, before that replacement can hide one.
            identity = (domain.lower(), name)
            if identity in seen and seen[identity] != value:
                raise BrowserCookieError("В выбранном профиле найдены разные сессии сайта. Выберите другой профиль или войдите на сайт заново.")
            seen[identity] = value
            jar.set(name, value, domain=domain, path="/", secure=True, expires=expiry)
        result = filter_cookie_jar(jar, platform)
        if not any(cookie.name == required for cookie in result):
            extra = " Используется обычный вход Firefox вне контейнеров и приватных окон." if browser == "firefox" else ""
            raise BrowserCookieError("В выбранном профиле не найдена действующая сессия сайта. Войдите на сайт в этом профиле браузера." + extra)
        _check(control)
        return result
    except BrowserCookieError:
        raise
    except (OSError, TypeError, ValueError, OverflowError):
        raise BrowserCookieError(_DB_ERROR) from None
