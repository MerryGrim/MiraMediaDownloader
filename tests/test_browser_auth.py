"""Synthetic browser fixtures only: no developer's live cookies are accessed."""

import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import pytest
import requests

from mira_media import browser_auth as auth
from mira_media.control import Cancelled, Control


@pytest.fixture(autouse=True)
def browser_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))


def firefox(tmp_path, records=()):
    root = tmp_path / "Roaming" / "Mozilla" / "Firefox"
    profile = root / "Profiles" / "synthetic.default"
    profile.mkdir(parents=True)
    (root / "profiles.ini").write_text(
        "[Profile0]\nName=Synthetic Firefox\nIsRelative=1\nPath=Profiles/synthetic.default\nDefault=1\n",
        encoding="utf-8")
    with sqlite3.connect(profile / "cookies.sqlite") as db:
        db.execute("CREATE TABLE moz_cookies (host TEXT,name TEXT,value TEXT,path TEXT,expiry INTEGER,"
                   "isSecure INTEGER,isHttpOnly INTEGER,originAttributes TEXT)")
        db.executemany("INSERT INTO moz_cookies VALUES (?,?,?,?,?,?,?,?)", records)
    return profile


def ffrow(name="auth_token", value="synthetic-session", domain=".x.com", expiry=None, attrs="", path="/"):
    return domain, name, value, path, expiry if expiry is not None else int(time.time()) + 3600, 1, 1, attrs


def chromium(tmp_path, records=(), browser="chrome", version=0):
    root = tmp_path / "Local"
    root = root.joinpath(*auth._CHROMIUM_PATHS[browser])
    profile = root / "Default"
    (profile / "Network").mkdir(parents=True)
    (root / "Local State").write_text(json.dumps({
        "profile": {"info_cache": {"Default": {"name": "Synthetic Chrome"}, "../bad": {"name": "wrong"}}},
        "os_crypt": {"encrypted_key": base64.b64encode(b"DPAPIsynthetic-key-wrapper").decode()},
    }), encoding="utf-8")
    with sqlite3.connect(profile / "Network" / "Cookies") as db:
        db.execute("CREATE TABLE cookies(host_key TEXT,name TEXT,value TEXT,encrypted_value BLOB,path TEXT,expires_utc INTEGER)")
        db.execute("CREATE TABLE meta(key TEXT,value TEXT)")
        db.execute("INSERT INTO meta VALUES ('version',?)", (str(version),))
        db.executemany("INSERT INTO cookies VALUES (?,?,?,?,?,?)", records)
    return profile


def crrow(name="auth_token", value="synthetic-session", encrypted=b"", domain=".x.com", expiry=None):
    return domain, name, value, encrypted, "/", expiry if expiry is not None else int((time.time() + 11644473600 + 3600) * 1000000)


def loaded(browser, profile, platform="x", control=None):
    return auth.load_browser_cookies(browser, str(profile.resolve()), platform, control)


def test_discovery_only_reads_profile_metadata(tmp_path, monkeypatch):
    profile = firefox(tmp_path)
    monkeypatch.setattr(auth.sqlite3, "connect", lambda *a, **k: pytest.fail("discovery opened cookies"))
    profiles = auth.discover_profiles("firefox")
    assert len(profiles) == 1
    assert profiles[0].profile_id == str(profile.resolve())
    assert "Synthetic Firefox" in profiles[0].label
    assert profiles[0].browser == "firefox"


def test_firefox_explicit_external_profile_from_ini(tmp_path):
    profile = firefox(tmp_path)
    ini = profile.parent.parent / "profiles.ini"
    ini.write_text(f"[Profile0]\nName=Own profile\nIsRelative=0\nPath={profile.resolve()}\n", encoding="utf-8")
    assert auth.discover_profiles("firefox")[0].path == str(profile.resolve())


@pytest.mark.parametrize("browser", ["chrome", "edge", "brave"])
def test_chromium_discovery_uses_only_named_normal_profiles(tmp_path, browser, monkeypatch):
    profile = chromium(tmp_path, browser=browser)
    (profile.parent / "Guest Profile").mkdir()
    (profile.parent / "System Profile").mkdir()
    monkeypatch.setattr(auth.sqlite3, "connect", lambda *a, **k: pytest.fail("discovery opened cookies"))
    profiles = auth.discover_profiles(browser)
    assert [(p.browser, p.profile_id) for p in profiles] == [(browser, str(profile.resolve()))]
    assert "Synthetic Chrome" in profiles[0].label


def test_discovery_handles_absent_malformed_metadata(tmp_path):
    assert auth.discover_profiles("firefox") == []
    assert auth.discover_profiles("chrome") == []
    profile = firefox(tmp_path)
    (profile.parent.parent / "profiles.ini").write_text("unparseable-metadata", encoding="utf-8")
    assert auth.discover_profiles("firefox") == []


def test_firefox_only_active_target_site_auth_default_container(tmp_path):
    profile = firefox(tmp_path, [
        ffrow(), ffrow("ct0", "synthetic-csrf"), ffrow("unrelated", "not-loaded"),
        ffrow(domain=".x.com.evil.test", value="not-loaded"),
        ffrow(domain=".example.test", value="not-loaded"),
        ffrow(value="expired", expiry=int(time.time()) - 1),
        ffrow(value="container-login", attrs="^userContextId=2"),
        ffrow(value="private-login", attrs="^privateBrowsingId=1"),
        ffrow(value="partitioned-login", attrs="^partitionKey=(https,other.test)"),
        ffrow(value="scoped-login", path="/different/"),
        ffrow("PHPSESSID", "synthetic-pixiv", ".pixiv.net"),
    ])
    before = (profile / "cookies.sqlite").read_bytes()
    jar = loaded("firefox", profile)
    assert {(c.domain, c.name, c.value) for c in jar} == {
        (".x.com", "auth_token", "synthetic-session"), (".x.com", "ct0", "synthetic-csrf")}
    assert all(c.secure for c in jar)
    assert (profile / "cookies.sqlite").read_bytes() == before
    assert sorted(p.name for p in profile.iterdir()) == ["cookies.sqlite"]


def test_firefox_sql_fetches_only_selected_rows(tmp_path, monkeypatch):
    profile = firefox(tmp_path, [ffrow(), ffrow("other-cookie", "not-to-read"),
                                ffrow(domain=".example.test", value="not-to-read")])
    connect = sqlite3.connect
    queries = []

    def tracking(*args, **kwargs):
        db = connect(*args, **kwargs)
        db.set_trace_callback(queries.append)
        return db

    monkeypatch.setattr(auth.sqlite3, "connect", tracking)
    loaded("firefox", profile)
    query = next(q for q in queries if q.startswith("SELECT host,name,value"))
    assert "host IN" in query and "name IN" in query and "originAttributes IN" in query
    assert "not-to-read" not in " ".join(queries)


def test_firefox_container_only_account_is_not_silently_selected(tmp_path):
    profile = firefox(tmp_path, [ffrow(attrs="^userContextId=2")])
    with pytest.raises(auth.BrowserCookieError, match="контейнеров"):
        loaded("firefox", profile)


def test_firefox_pixiv_selects_only_pixiv_session(tmp_path):
    profile = firefox(tmp_path, [ffrow(), ffrow("PHPSESSID", "synthetic-pixiv", ".pixiv.net")])
    jar = loaded("firefox", profile, "pixiv")
    assert [(c.domain, c.name, c.value) for c in jar] == [(".pixiv.net", "PHPSESSID", "synthetic-pixiv")]


def test_profile_must_be_explicit_discovered_selection(tmp_path):
    profile = firefox(tmp_path, [ffrow()])
    for profile_id in ("", str(profile / "cookies.sqlite"), str(tmp_path / "other-profile")):
        with pytest.raises(auth.BrowserCookieError, match="профиль"):
            auth.load_browser_cookies("firefox", profile_id, "x")


def test_missing_login_fails_without_anonymous_fallback(tmp_path):
    profile = firefox(tmp_path, [ffrow("ct0", "synthetic-csrf")])
    with pytest.raises(auth.BrowserCookieError, match="не найдена действующая сессия"):
        loaded("firefox", profile)


def test_no_conflicting_accounts_selected_implicitly(tmp_path):
    profile = firefox(tmp_path, [ffrow(), ffrow(value="other-session", domain=".twitter.com")])
    with pytest.raises(auth.BrowserCookieError, match="разные сессии") as error:
        loaded("firefox", profile)
    assert "synthetic-session" not in str(error.value)
    assert "other-session" not in str(error.value)


def test_firefox_same_domain_duplicate_conflict_not_hidden_by_cookiejar(tmp_path):
    profile = firefox(tmp_path, [ffrow(), ffrow(value="different-session", attrs="^userContextId=0")])
    with pytest.raises(auth.BrowserCookieError, match="разные сессии"):
        loaded("firefox", profile)


def test_locked_database_no_copy_unlock_or_raw_error(tmp_path):
    profile = firefox(tmp_path, [ffrow()])
    with sqlite3.connect(profile / "cookies.sqlite") as lock:
        lock.execute("BEGIN EXCLUSIVE")
        with pytest.raises(auth.BrowserCookieError, match="заблокировать"):
            loaded("firefox", profile)
    assert sorted(p.name for p in profile.iterdir()) == ["cookies.sqlite"]


def test_malformed_database_error_sanitized(tmp_path):
    profile = firefox(tmp_path)
    (profile / "cookies.sqlite").write_bytes(b"synthetic-secret-not-a-database")
    with pytest.raises(auth.BrowserCookieError) as error:
        loaded("firefox", profile)
    assert "synthetic-secret" not in str(error.value)


def test_chromium_plaintext_and_session_expiry(tmp_path):
    profile = chromium(tmp_path, [crrow(expiry=0), crrow(name="ct0", value="synthetic-csrf"),
                                 crrow(name="other", value="not-loaded")])
    jar = loaded("chrome", profile)
    assert jar.get("auth_token", domain=".x.com") == "synthetic-session"
    assert next(c for c in jar if c.name == "auth_token").expires is None
    assert len(jar) == 2


def test_chromium_v20_blocked_before_any_decrypt(tmp_path, monkeypatch):
    profile = chromium(tmp_path, [crrow(value="", encrypted=b"v20synthetic-protected")])
    monkeypatch.setattr(auth, "_unprotect", lambda *a: pytest.fail("attempted app-bound decryption"))
    with pytest.raises(auth.BrowserCookieError, match="App-Bound/v20") as error:
        loaded("chrome", profile)
    assert "synthetic-protected" not in str(error.value)


def test_chromium_unrelated_or_expired_v20_does_not_get_read(tmp_path):
    profile = chromium(tmp_path, [crrow(),
                                 crrow(name="other", value="", encrypted=b"v20unrelated"),
                                 crrow(value="", encrypted=b"v20expired", expiry=1),
                                 crrow(value="", encrypted=b"v20wrong-site", domain=".other.test")])
    assert len(loaded("chrome", profile)) == 1


def test_chromium_partitioned_cookie_not_loaded_or_decrypted(tmp_path, monkeypatch):
    profile = chromium(tmp_path, [crrow(), crrow(value="", encrypted=b"v20partitioned")])
    with sqlite3.connect(profile / "Network" / "Cookies") as db:
        db.execute("ALTER TABLE cookies ADD COLUMN top_frame_site_key TEXT DEFAULT ''")
        db.execute("UPDATE cookies SET top_frame_site_key='https://embedded.test' WHERE value=''")
    monkeypatch.setattr(auth, "_unprotect", lambda *a: pytest.fail("decrypted unrelated partition"))
    assert len(loaded("chrome", profile)) == 1


def test_chromium_same_domain_duplicate_conflict_not_hidden_by_cookiejar(tmp_path):
    profile = chromium(tmp_path, [crrow(), crrow(value="different-session")])
    with pytest.raises(auth.BrowserCookieError, match="разные сессии"):
        loaded("chrome", profile)


@pytest.mark.parametrize("prefix", [b"v10", b"v11"])
@pytest.mark.parametrize("version", [23, 24])
def test_chromium_standard_user_dpapi_key_and_aes_gcm_synthetic(tmp_path, monkeypatch, prefix, version):
    from Cryptodome.Cipher import AES
    key = bytes(range(32))
    plaintext = b"synthetic-session"
    if version >= 24:
        plaintext = hashlib.sha256(b".x.com").digest() + plaintext
    nonce = b"fixture12345"
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    profile = chromium(tmp_path, [crrow(value="", encrypted=prefix + nonce + ciphertext + tag)], version=version)
    calls = []

    def unprotect(wrapped):
        calls.append(wrapped)
        assert wrapped == b"synthetic-key-wrapper"
        return key

    monkeypatch.setattr(auth, "_unprotect", unprotect)
    jar = loaded("chrome", profile)
    assert jar.get("auth_token", domain=".x.com") == "synthetic-session"
    assert calls == [b"synthetic-key-wrapper"]


def test_chromium_cookie_domain_hash_must_match(tmp_path, monkeypatch):
    from Cryptodome.Cipher import AES
    key = b"k" * 32
    nonce = b"n" * 12
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(hashlib.sha256(b".wrong.test").digest() + b"synthetic-session")
    profile = chromium(tmp_path, [crrow(value="", encrypted=b"v10" + nonce + ciphertext + tag)], version=24)
    monkeypatch.setattr(auth, "_unprotect", lambda value: key)
    with pytest.raises(auth.BrowserCookieError, match="расшифровать"):
        loaded("chrome", profile)


def test_current_user_windows_dpapi_roundtrip_synthetic_only():
    import ctypes
    import os
    from ctypes import wintypes
    if os.name != "nt":
        pytest.skip("ordinary Windows DPAPI")

    class Blob(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    value = b"synthetic-test-value-only"
    source = ctypes.create_string_buffer(value)
    incoming = Blob(len(value), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    assert crypt32.CryptProtectData(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    try:
        encrypted = ctypes.string_at(outgoing.data, outgoing.length)
    finally:
        kernel32.LocalFree(outgoing.data)
    assert auth._unprotect(encrypted) == value


def test_cookie_filter_canonicalizes_old_twitter_and_rejects_unrelated(tmp_path):
    jar = requests.cookies.RequestsCookieJar()
    jar.set("auth_token", "synthetic-session", domain=".twitter.com", path="/")
    jar.set("ct0", "synthetic-csrf", domain=".x.com", path="/")
    jar.set("auth_token", "not-loaded", domain=".x.com.evil.test", path="/")
    jar.set("other", "not-loaded", domain=".x.com", path="/")
    result = auth.filter_cookie_jar(jar, "x")
    assert len(result) == 2
    assert all(c.domain == ".x.com" and c.secure for c in result)


def test_control_cancel_prevents_cookie_access(tmp_path, monkeypatch):
    profile = firefox(tmp_path, [ffrow()])
    monkeypatch.setattr(auth.sqlite3, "connect", lambda *a, **k: pytest.fail("accessed cookies after cancel"))
    control = Control()
    control.command("stop")
    with pytest.raises(Cancelled):
        loaded("firefox", profile, control=control)


@pytest.mark.parametrize("browser,platform", [("unsupported", "x"), ("firefox", "unsupported")])
def test_unknown_browser_or_platform_rejected(browser, platform):
    with pytest.raises(auth.BrowserCookieError):
        auth.load_browser_cookies(browser, "", platform)
