"""The app's own site sessions, encrypted for the current Windows user with DPAPI.

This module never reads another browser's profile. Only allowlisted session
cookies supplied by the app's login window are retained. Plaintext remains in
memory; the vault and its atomic-write temporary file contain ciphertext only.
Local cookie validity does not establish a network-authenticated account;
Pixiv can issue PHPSESSID for guests, so its login UI verifies the account.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import ctypes
import json
import math
import os
from pathlib import Path
import threading
import time

import requests


class SessionError(ValueError):
    """A fixed user-facing message containing no session data."""


_MAGIC = b"MIRA-X-SESSION\x01\x00"
_VERSION = 1
_MAX_VAULT_BYTES = 128 * 1024
_MAX_COOKIE_BYTES = 16 * 1024
_MAX_USER_AGENT_BYTES = 2048
_MAX_INPUT_COOKIES = 2048
_DOMAINS = frozenset(("x.com", ".x.com", "twitter.com", ".twitter.com"))
_NAMES = ("auth_token", "ct0")
_COOKIE_FIELDS = frozenset(("name", "value", "domain", "path", "expires", "secure"))
_LOCK = threading.RLock()
_MISSING_ERROR = "Сессия X не сохранена. Войдите в X через окно приложения."
_INVALID_ERROR = "Сохранённая сессия X недоступна или истекла. Войдите в X заново."
_LOGIN_ERROR = "Не получена полная действующая сессия X. Завершите вход в окне приложения."
_SAVE_ERROR = "Не удалось безопасно сохранить сессию X для текущего пользователя Windows. Повторите вход."
_CLEAR_ERROR = "Не удалось удалить сохранённую сессию X. Закройте другие окна Mira и повторите."
_PLATFORMS = {
    "x": {"label": "X", "domains": _DOMAINS, "names": _NAMES,
          "domain": ".x.com", "magic": _MAGIC},
    "pixiv": {"label": "Pixiv", "domains": frozenset(("pixiv.net", ".pixiv.net", "www.pixiv.net", ".www.pixiv.net")),
              "names": ("PHPSESSID",), "domain": ".pixiv.net", "magic": b"MIRA-PIXIV-SESSION\x01\x00"},
}
_ERRORS = {"missing": _MISSING_ERROR, "invalid": _INVALID_ERROR, "login": _LOGIN_ERROR,
           "save": _SAVE_ERROR, "clear": _CLEAR_ERROR}


def _platform(platform: str) -> dict:
    if not isinstance(platform, str) or platform not in _PLATFORMS:
        raise SessionError("Неизвестная платформа для сохранённой сессии.")
    return _PLATFORMS[platform]


def _error(kind: str, platform: str) -> str:
    return _ERRORS[kind].replace(" X", " " + _platform(platform)["label"])


def session_path(platform: str = "x") -> Path:
    """Return the app-owned vault path without touching disk.

    MIRA_SESSION_DIR is an explicit data-location override, used for isolated
    tests as well. It must be absolute and never points into a browser profile.
    The ordinary location inherits the current user's LocalAppData ACLs.
    """
    _platform(platform)
    override = os.environ.get("MIRA_SESSION_DIR")
    local = os.environ.get("LOCALAPPDATA")
    root = Path(override) if override else (
        Path(local) / "Mira" / "MiraMediaDownloader" if local else
        Path.home() / "AppData" / "Local" / "Mira" / "MiraMediaDownloader"
    )
    if not root.is_absolute():
        raise SessionError(_error("save", platform))
    return root / f"{platform}-session.dpapi"


def _temporary_path(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def _safe_cookie_value(value: object, platform: str = "x") -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_COOKIE_BYTES:
        raise SessionError(_error("login", platform))
    # HTTP cookie values are ASCII. Reject separators as well as controls so a
    # supplied value cannot become an additional Cookie header field.
    if any(ord(char) < 0x21 or ord(char) > 0x7e or char in '\";,\\' for char in value):
        raise SessionError(_error("login", platform))
    return value


def _safe_user_agent(value: object, platform: str = "x") -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_USER_AGENT_BYTES:
        raise SessionError(_error("login", platform))
    if any(ord(char) < 0x20 or ord(char) > 0x7e for char in value):
        raise SessionError(_error("login", platform))
    return value


def normalize_cookies(platform: str, cookies: Iterable[dict]) -> list[dict]:
    """Select complete, unambiguous allowlisted cookies for a supported site.

    Only exact site domains, root-path secure authentication cookies qualify.
    Unrelated cookies are ignored. Expired records do not qualify.
    Duplicate identical records are harmless; conflicting accounts are rejected
    instead of silently selecting one. Pixiv's PHPSESSID may belong to a guest;
    this local validator cannot establish an authenticated account on the site.
    """
    rules = _platform(platform)
    error = _error("login", platform)
    now = time.time()
    found: dict[str, dict] = {}
    try:
        for index, record in enumerate(cookies):
            if index >= _MAX_INPUT_COOKIES or not isinstance(record, Mapping):
                raise SessionError(error)
            name = record.get("name")
            domain = record.get("domain")
            if not isinstance(name, str) or name not in rules["names"]:
                continue
            if not isinstance(domain, str) or domain not in rules["domains"] or record.get("path") != "/":
                continue
            if record.get("secure") is not True:
                raise SessionError(error)
            expires = record.get("expires")
            if expires is not None:
                if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not math.isfinite(expires):
                    raise SessionError(error)
                if expires == 0:
                    expires = None
                elif expires <= now:
                    continue
                elif expires > 253402300799 or int(expires) != expires:
                    raise SessionError(error)
                else:
                    expires = int(expires)
            normalized = {"name": name, "value": _safe_cookie_value(record.get("value"), platform),
                          "domain": rules["domain"], "path": "/", "expires": expires, "secure": True}
            previous = found.get(name)
            if previous is not None and previous != normalized:
                raise SessionError(error)
            found[name] = normalized
    except SessionError:
        raise
    except (TypeError, ValueError, OverflowError):
        raise SessionError(error) from None
    if set(found) != set(rules["names"]):
        raise SessionError(error)
    return [found[name] for name in rules["names"]]


def normalize_x_cookies(cookies: Iterable[dict]) -> list[dict]:
    """Backward-compatible X-specific cookie normalization."""
    return normalize_cookies("x", cookies)


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    """Normal current-user DPAPI, with UI forbidden and no elevation helpers."""
    if os.name != "nt" or not isinstance(data, bytes) or not data or len(data) > _MAX_VAULT_BYTES:
        raise SessionError(_SAVE_ERROR if protect else _INVALID_ERROR)
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    backing = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming = Blob(len(data), ctypes.cast(backing, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        operation = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        operation.restype = wintypes.BOOL
        # CRYPTPROTECT_UI_FORBIDDEN = 1. Deliberately omit LOCAL_MACHINE (4),
        # so another Windows account cannot decrypt the saved session.
        if not operation(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
            raise SessionError(_SAVE_ERROR if protect else _INVALID_ERROR)
        if not outgoing.data or not 0 < outgoing.size <= _MAX_VAULT_BYTES:
            raise SessionError(_SAVE_ERROR if protect else _INVALID_ERROR)
        return ctypes.string_at(outgoing.data, outgoing.size)
    except SessionError:
        raise
    except (OSError, ValueError, TypeError, AttributeError):
        raise SessionError(_SAVE_ERROR if protect else _INVALID_ERROR) from None
    finally:
        if outgoing.data:
            # Clear DPAPI's allocated plaintext before releasing it on reads.
            if not protect:
                ctypes.memset(outgoing.data, 0, outgoing.size)
            kernel32.LocalFree(outgoing.data)


def save_session(platform: str, cookies: Iterable[dict], user_agent: str) -> None:
    """Validate and atomically replace only this app's encrypted session vault."""
    rules = _platform(platform)
    canonical = normalize_cookies(platform, cookies)
    agent = _safe_user_agent(user_agent, platform)
    document = {"version": _VERSION, "cookies": canonical, "user_agent": agent, "saved_at": int(time.time())}
    if platform != "x":
        document["platform"] = platform
    payload = json.dumps(document, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    try:
        encrypted = rules["magic"] + _dpapi(payload, protect=True)
    except SessionError:
        raise SessionError(_error("save", platform)) from None
    if len(encrypted) > _MAX_VAULT_BYTES:
        raise SessionError(_error("save", platform))
    with _LOCK:
        temporary = None
        try:
            path = session_path(platform)
            temporary = _temporary_path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            # This is our own exact temporary filename. Removing a remnant from
            # a crashed write does not inspect or alter any browser data.
            temporary.unlink(missing_ok=True)
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except (OSError, ValueError, TypeError):
            raise SessionError(_error("save", platform)) from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def _json_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SessionError(_INVALID_ERROR)
        result[key] = value
    return result


def _load_records(platform: str = "x") -> tuple[list[dict], str]:
    rules = _platform(platform)
    try:
        path = session_path(platform)
        with path.open("rb") as stream:
            encrypted = stream.read(_MAX_VAULT_BYTES + 1)
    except FileNotFoundError:
        raise SessionError(_error("missing", platform)) from None
    except (OSError, ValueError, TypeError):
        raise SessionError(_error("invalid", platform)) from None
    try:
        if len(encrypted) > _MAX_VAULT_BYTES or not encrypted.startswith(rules["magic"]):
            raise SessionError(_INVALID_ERROR)
        plaintext = _dpapi(encrypted[len(rules["magic"]):], protect=False)
        payload = json.loads(plaintext.decode("utf-8"), object_pairs_hook=_json_object)
        fields = {"version", "cookies", "user_agent", "saved_at"}
        if platform != "x":
            fields.add("platform")
        if not isinstance(payload, dict) or set(payload) != fields:
            raise SessionError(_INVALID_ERROR)
        if platform != "x" and payload["platform"] != platform:
            raise SessionError(_INVALID_ERROR)
        if type(payload["version"]) is not int or payload["version"] != _VERSION:
            raise SessionError(_INVALID_ERROR)
        saved_at = payload["saved_at"]
        if type(saved_at) is not int or saved_at <= 0 or saved_at > time.time() + 300:
            raise SessionError(_INVALID_ERROR)
        records = payload["cookies"]
        if not isinstance(records, list) or len(records) != len(rules["names"]):
            raise SessionError(_INVALID_ERROR)
        if any(not isinstance(record, dict) or set(record) != _COOKIE_FIELDS for record in records):
            raise SessionError(_INVALID_ERROR)
        canonical = normalize_cookies(platform, records)
        if canonical != records:
            raise SessionError(_INVALID_ERROR)
        return canonical, _safe_user_agent(payload["user_agent"], platform)
    except (SessionError, UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        raise SessionError(_error("invalid", platform)) from None


def load_session(platform: str) -> tuple[requests.cookies.RequestsCookieJar, str]:
    """Return a fresh in-memory jar and the login browser's User-Agent.

    Missing, corrupt, wrong-user and expired sessions raise SessionError. There
    is deliberately no anonymous fallback or lookup in external browsers.
    A locally valid Pixiv cookie still requires the login UI's account check.
    """
    with _LOCK:
        records, agent = _load_records(platform)
    jar = requests.cookies.RequestsCookieJar()
    for record in records:
        jar.set(record["name"], record["value"], domain=record["domain"], path="/", secure=True,
                expires=record["expires"], rest={"HttpOnly": record["name"] in ("auth_token", "PHPSESSID")})
    return jar, agent


def has_session(platform: str) -> bool:
    """Check only our local vault, not whether the site's account is logged in."""
    _platform(platform)
    try:
        load_session(platform)
        return True
    except SessionError:
        return False


def clear_session(platform: str) -> None:
    """Delete our exact encrypted vault and its exact temporary file only."""
    _platform(platform)
    with _LOCK:
        try:
            path = session_path(platform)
            path.unlink(missing_ok=True)
            _temporary_path(path).unlink(missing_ok=True)
        except (OSError, ValueError, TypeError):
            raise SessionError(_error("clear", platform)) from None


def save_x_session(cookies: Iterable[dict], user_agent: str) -> None:
    """Backward-compatible X wrapper; preserves the original X vault format."""
    save_session("x", cookies, user_agent)


def load_x_session() -> tuple[requests.cookies.RequestsCookieJar, str]:
    """Backward-compatible X wrapper returning a fresh in-memory cookie jar."""
    return load_session("x")


def has_x_session() -> bool:
    """Backward-compatible local X vault check; never contacts the network."""
    return has_session("x")


def clear_x_session() -> None:
    """Backward-compatible X-only logout; leaves Pixiv's session untouched."""
    clear_session("x")
