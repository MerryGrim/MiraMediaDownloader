"""Isolated, synthetic Pixiv and X sessions only; no browser or network I/O."""

import json
import os
from pathlib import Path
import time

import pytest
import requests

from mira_media import session_vault as vault


PIXIV_VALUE = "74200000_GENERATED-pixiv-session-not-a-real-account"
UA = "Mozilla/5.0 (Synthetic Mira Pixiv Test)"
WINDOWS = pytest.mark.skipif(os.name != "nt", reason="Genuine current-user Windows DPAPI integration")


@pytest.fixture(autouse=True)
def isolated_session_location(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "SyntheticLocalAppData"))
    monkeypatch.setenv("MIRA_SESSION_DIR", str(tmp_path / "SyntheticVault"))


def pixiv_cookie(**overrides):
    record = {"name": "PHPSESSID", "value": PIXIV_VALUE, "domain": ".pixiv.net", "path": "/",
              "secure": True, "expires": int(time.time()) + 3600}
    record.update(overrides)
    return record


def x_cookies():
    return [{"name": name, "value": "GENERATED-X-" + name, "domain": ".x.com", "path": "/",
             "secure": True, "expires": int(time.time()) + 3600} for name in ("auth_token", "ct0")]


def pixiv_payload():
    return {"version": 1, "platform": "pixiv", "cookies": [pixiv_cookie()], "user_agent": UA,
            "saved_at": int(time.time())}


def write_pixiv_payload(payload):
    path = vault.session_path("pixiv")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(vault._PLATFORMS["pixiv"]["magic"] +
                     vault._dpapi(json.dumps(payload).encode(), protect=True))


def test_platform_specific_paths_are_separate_and_default_remains_x(tmp_path, monkeypatch):
    assert vault.session_path() == vault.session_path("x")
    assert vault.session_path("pixiv") == tmp_path / "SyntheticVault" / "pixiv-session.dpapi"
    assert not vault.session_path("pixiv").parent.exists()
    monkeypatch.delenv("MIRA_SESSION_DIR")
    assert vault.session_path("pixiv") == (tmp_path / "SyntheticLocalAppData" / "Mira" /
                                            "MiraMediaDownloader" / "pixiv-session.dpapi")


@pytest.mark.parametrize("domain", ["pixiv.net", ".pixiv.net", "www.pixiv.net", ".www.pixiv.net"])
def test_exact_pixiv_domains_canonicalize(domain):
    records = vault.normalize_cookies("pixiv", [pixiv_cookie(domain=domain)])
    assert records == [pixiv_cookie()]


@pytest.mark.parametrize("domain", ["accounts.pixiv.net", ".accounts.pixiv.net", "pixiv.net.attacker.test",
                                     ".pixiv.net.attacker.test", "www.pixiv.net.attacker.test", "PIXIV.NET",
                                     "x.com", ".x.com", "pixiv.net.", ".pixiv.net."])
def test_accounts_only_subdomain_or_lookalike_does_not_qualify(domain):
    with pytest.raises(vault.SessionError) as caught:
        vault.normalize_cookies("pixiv", [pixiv_cookie(domain=domain)])
    assert "Pixiv" in str(caught.value)
    assert domain not in str(caught.value)


def test_minimal_allowlist_and_conflicting_sessions():
    record = pixiv_cookie()
    result = vault.normalize_cookies("pixiv", [record, dict(record, domain="www.pixiv.net"),
                                               pixiv_cookie(name="unrelated", value="GENERATED-other"),
                                               *x_cookies()])
    assert result == [record]
    with pytest.raises(vault.SessionError):
        vault.normalize_cookies("pixiv", [record, dict(record, value="GENERATED-other-account")])


@pytest.mark.parametrize("mutation", [{"path": "/accounts/"}, {"secure": False}, {"secure": 1},
                                      {"expires": 1}, {"expires": True}, {"expires": float("nan")},
                                      {"name": "auth_token"}, {"value": "GENERATED\r\nHeader:value"},
                                      {"value": "GENERATED;injected=value"}, {"value": ""}])
def test_pixiv_cookie_validation_uses_same_strict_safety_rules(mutation):
    with pytest.raises(vault.SessionError) as caught:
        vault.normalize_cookies("pixiv", [pixiv_cookie(**mutation)])
    assert "Pixiv" in str(caught.value)
    assert "GENERATED" not in str(caught.value)


@pytest.mark.parametrize("platform", ["", "unknown-platform-generated", "../x", "X", None, [], {}])
def test_unknown_platform_is_rejected_before_file_or_crypto_access(platform, monkeypatch):
    monkeypatch.setattr(vault, "_dpapi", lambda *a, **k: pytest.fail("invalid platform reached DPAPI"))
    for operation in (lambda: vault.session_path(platform),
                      lambda: vault.normalize_cookies(platform, [pixiv_cookie()]),
                      lambda: vault.save_session(platform, [pixiv_cookie()], UA),
                      lambda: vault.load_session(platform), lambda: vault.has_session(platform),
                      lambda: vault.clear_session(platform)):
        with pytest.raises(vault.SessionError) as caught:
            operation()
        assert str(caught.value) == "Неизвестная платформа для сохранённой сессии."
    assert not vault.session_path().parent.exists()


def test_local_pixiv_session_check_does_not_claim_authenticated_account_or_use_network(monkeypatch):
    monkeypatch.setattr(requests.Session, "request", lambda *a, **k: pytest.fail("vault contacted network"))
    # Missing data remains a site-specific local status. Authentication of a
    # PHPSESSID is the login UI's separate account-verification responsibility.
    assert not vault.has_session("pixiv")
    with pytest.raises(vault.SessionError) as caught:
        vault.load_session("pixiv")
    assert str(caught.value) == "Сессия Pixiv не сохранена. Войдите в Pixiv через окно приложения."


@WINDOWS
def test_genuine_pixiv_dpapi_roundtrip_and_no_plaintext_files():
    vault.save_session("pixiv", [pixiv_cookie(), pixiv_cookie(name="extra", value="GENERATED-unrelated")], UA)
    path = vault.session_path("pixiv")
    encrypted = path.read_bytes()
    assert encrypted.startswith(vault._PLATFORMS["pixiv"]["magic"])
    assert PIXIV_VALUE.encode() not in encrypted and UA.encode() not in encrypted
    assert not path.with_name(path.name + ".tmp").exists()
    assert not vault.session_path("x").exists()
    assert vault.has_session("pixiv")
    jar, agent = vault.load_session("pixiv")
    assert isinstance(jar, requests.cookies.RequestsCookieJar) and agent == UA
    assert {(c.name, c.value, c.domain, c.path, c.secure) for c in jar} == {
        ("PHPSESSID", PIXIV_VALUE, ".pixiv.net", "/", True)}
    assert all(c.has_nonstandard_attr("HttpOnly") for c in jar)
    jar.clear()
    assert len(vault.load_session("pixiv")[0]) == 1
    plaintext = vault._dpapi(encrypted[len(vault._PLATFORMS["pixiv"]["magic"]):], protect=False)
    payload = json.loads(plaintext)
    assert set(payload) == {"version", "platform", "cookies", "user_agent", "saved_at"}
    assert payload["platform"] == "pixiv"
    assert len(payload["cookies"]) == 1
    assert b"GENERATED-unrelated" not in plaintext


@WINDOWS
def test_legacy_x_v1_payload_loads_and_new_x_write_keeps_original_schema():
    legacy_payload = {"version": 1, "cookies": x_cookies(), "user_agent": UA, "saved_at": int(time.time())}
    path = vault.session_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(b"MIRA-X-SESSION\x01\x00" + vault._dpapi(json.dumps(legacy_payload).encode(), protect=True))
    assert vault.load_x_session()[1] == UA
    assert vault.load_session("x")[0].get_dict() == {c["name"]: c["value"] for c in x_cookies()}
    vault.save_session("x", x_cookies(), UA)
    rewritten = json.loads(vault._dpapi(path.read_bytes()[len(b"MIRA-X-SESSION\x01\x00"):], protect=False))
    assert set(rewritten) == {"version", "cookies", "user_agent", "saved_at"}
    assert "platform" not in rewritten
    assert vault.normalize_x_cookies(x_cookies()) == vault.normalize_cookies("x", x_cookies())


@WINDOWS
@pytest.mark.parametrize("source,target", [("x", "pixiv"), ("pixiv", "x")])
def test_copying_ciphertext_to_other_platform_filename_cannot_load(source, target):
    vault.save_session(source, x_cookies() if source == "x" else [pixiv_cookie()], UA)
    vault.session_path(target).write_bytes(vault.session_path(source).read_bytes())
    with pytest.raises(vault.SessionError) as caught:
        vault.load_session(target)
    assert str(caught.value) == vault._error("invalid", target)
    assert vault.has_session(source) and not vault.has_session(target)


@WINDOWS
@pytest.mark.parametrize("source,target", [("x", "pixiv"), ("pixiv", "x")])
def test_replacing_cleartext_magic_cannot_defeat_encrypted_platform_binding(source, target):
    vault.save_session(source, x_cookies() if source == "x" else [pixiv_cookie()], UA)
    encrypted = vault.session_path(source).read_bytes()
    body = encrypted[len(vault._PLATFORMS[source]["magic"]):]
    vault.session_path(target).write_bytes(vault._PLATFORMS[target]["magic"] + body)
    assert not vault.has_session(target)


@WINDOWS
@pytest.mark.parametrize("mutation", ["missing_platform", "wrong_platform", "unknown_field", "unknown_cookie_field",
                                      "extra_cookie", "wrong_name", "noncanonical_domain"])
def test_pixiv_encrypted_schema_and_platform_are_strict(mutation):
    payload = pixiv_payload()
    if mutation == "missing_platform":
        del payload["platform"]
    elif mutation == "wrong_platform":
        payload["platform"] = "x"
    elif mutation == "unknown_field":
        payload["password"] = "GENERATED-never-allowed"
    elif mutation == "unknown_cookie_field":
        payload["cookies"][0]["refresh_token"] = "GENERATED-never-allowed"
    elif mutation == "extra_cookie":
        payload["cookies"].append(dict(payload["cookies"][0]))
    elif mutation == "wrong_name":
        payload["cookies"][0]["name"] = "auth_token"
    elif mutation == "noncanonical_domain":
        payload["cookies"][0]["domain"] = "www.pixiv.net"
    write_pixiv_payload(payload)
    assert not vault.has_session("pixiv")
    with pytest.raises(vault.SessionError) as caught:
        vault.load_session("pixiv")
    assert str(caught.value) == vault._error("invalid", "pixiv")


@WINDOWS
def test_pixiv_expiry_and_tampering_fail_with_site_specific_error(monkeypatch):
    expiry = int(time.time()) + 60
    vault.save_session("pixiv", [pixiv_cookie(expires=expiry)], UA)
    with monkeypatch.context() as clock:
        clock.setattr(vault.time, "time", lambda: expiry + 1)
        assert not vault.has_session("pixiv")
        with pytest.raises(vault.SessionError) as caught:
            vault.load_session("pixiv")
        assert "Pixiv" in str(caught.value) and " X" not in str(caught.value)
    path = vault.session_path("pixiv")
    encrypted = bytearray(path.read_bytes())
    encrypted[-9] ^= 0x80
    path.write_bytes(encrypted)
    assert not vault.has_session("pixiv")


@WINDOWS
def test_pixiv_atomic_failure_keeps_both_old_sessions_and_leaves_no_plaintext(monkeypatch):
    vault.save_session("x", x_cookies(), UA)
    vault.save_session("pixiv", [pixiv_cookie()], UA)
    previous_x = vault.session_path("x").read_bytes()
    previous_pixiv = vault.session_path("pixiv").read_bytes()
    def failed_replace(source, target):
        temporary = Path(source).read_bytes()
        assert PIXIV_VALUE.encode() not in temporary and b"GENERATED-replacement" not in temporary
        raise OSError("GENERATED-sensitive-system-error")
    monkeypatch.setattr(vault.os, "replace", failed_replace)
    with pytest.raises(vault.SessionError) as caught:
        vault.save_session("pixiv", [pixiv_cookie(value="GENERATED-replacement")], UA)
    assert str(caught.value) == vault._error("save", "pixiv")
    assert vault.session_path("pixiv").read_bytes() == previous_pixiv
    assert vault.session_path("x").read_bytes() == previous_x
    assert not vault.session_path("pixiv").with_name("pixiv-session.dpapi.tmp").exists()


@pytest.mark.parametrize("protect", [True, False])
def test_pixiv_dpapi_failures_are_remapped_to_pixiv_errors(protect, monkeypatch):
    if not protect:
        path = vault.session_path("pixiv")
        path.parent.mkdir(parents=True)
        path.write_bytes(vault._PLATFORMS["pixiv"]["magic"] + b"GENERATED-unreadable")
    def failed_dpapi(*args, **kwargs):
        raise vault.SessionError(vault._SAVE_ERROR if protect else vault._INVALID_ERROR)
    monkeypatch.setattr(vault, "_dpapi", failed_dpapi)
    with pytest.raises(vault.SessionError) as caught:
        if protect:
            vault.save_session("pixiv", [pixiv_cookie()], UA)
        else:
            vault.load_session("pixiv")
    assert "Pixiv" in str(caught.value) and " X" not in str(caught.value)


@WINDOWS
def test_logout_clears_only_selected_platform_and_exact_temporary_files():
    vault.save_x_session(x_cookies(), UA)
    vault.save_session("pixiv", [pixiv_cookie()], UA)
    x_bytes = vault.session_path("x").read_bytes()
    pixiv = vault.session_path("pixiv")
    pixiv_tmp = pixiv.with_name(pixiv.name + ".tmp")
    pixiv_tmp.write_bytes(b"GENERATED-ciphertext-remnant")
    unrelated = pixiv.parent / "library.sqlite"
    unrelated.write_bytes(b"GENERATED-library")
    vault.clear_session("pixiv")
    assert not pixiv.exists() and not pixiv_tmp.exists()
    assert vault.session_path("x").read_bytes() == x_bytes
    assert vault.has_x_session() and not vault.has_session("pixiv")
    vault.save_session("pixiv", [pixiv_cookie()], UA)
    pixiv_bytes = pixiv.read_bytes()
    vault.clear_x_session()
    assert not vault.has_x_session() and vault.has_session("pixiv")
    assert pixiv.read_bytes() == pixiv_bytes
    assert unrelated.read_bytes() == b"GENERATED-library"
