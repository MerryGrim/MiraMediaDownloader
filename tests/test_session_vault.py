"""Own-vault fixtures only; never access real user sessions or browser data."""

import json
import os
from pathlib import Path
import time

import pytest
import requests

from mira_media import session_vault as vault


UA = "Mozilla/5.0 (Synthetic Mira Test)"
AUTH = "GENERATED-vault-auth-sentinel-3482"
CSRF = "GENERATED-vault-csrf-sentinel-7641"


@pytest.fixture(autouse=True)
def isolated_session_location(tmp_path, monkeypatch):
    # Every test, including error paths and existence probes, remains under the
    # test fixture. A developer's LocalAppData vault must never be consulted.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "SyntheticLocalAppData"))
    monkeypatch.setenv("MIRA_SESSION_DIR", str(tmp_path / "SyntheticVault"))


def cookie(name="auth_token", value=AUTH, **overrides):
    record = {"name": name, "value": value, "domain": ".x.com", "path": "/",
              "secure": True, "expires": int(time.time()) + 3600}
    record.update(overrides)
    return record


def cookies(**overrides):
    return [cookie(**overrides), cookie("ct0", CSRF, **overrides)]


def valid_payload():
    return {"version": 1, "cookies": vault.normalize_x_cookies(cookies()),
            "user_agent": UA, "saved_at": int(time.time())}


def write_payload(payload):
    data = json.dumps(payload, separators=(",", ":")).encode()
    path = vault.session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(vault._MAGIC + vault._dpapi(data, protect=True))


def test_default_location_and_override_never_create_directories(tmp_path, monkeypatch):
    assert vault.session_path() == tmp_path / "SyntheticVault" / "x-session.dpapi"
    assert not vault.session_path().parent.exists()
    monkeypatch.delenv("MIRA_SESSION_DIR")
    expected = tmp_path / "SyntheticLocalAppData" / "Mira" / "MiraMediaDownloader" / "x-session.dpapi"
    assert vault.session_path() == expected
    assert not expected.parent.exists()


def test_relative_override_fails_without_writing(monkeypatch):
    monkeypatch.setenv("MIRA_SESSION_DIR", "relative-synthetic-vault")
    with pytest.raises(vault.SessionError):
        vault.session_path()
    assert not vault.has_x_session()


def test_normalization_retains_only_two_exact_root_secure_x_cookies():
    records = cookies()
    records.extend([cookie("preferences", "GENERATED-irrelevant"),
                    cookie(domain=".example.test"), cookie(domain="x.com.attacker.test"),
                    cookie(domain="subdomain.x.com"), cookie(domain="X.COM"),
                    cookie(path="/i/"), cookie(value="GENERATED-expired", expires=int(time.time()) - 60)])
    result = vault.normalize_x_cookies(records)
    assert [c["name"] for c in result] == ["auth_token", "ct0"]
    assert [c["value"] for c in result] == [AUTH, CSRF]
    assert all(c["domain"] == ".x.com" and c["path"] == "/" and c["secure"] for c in result)
    assert all(set(c) == vault._COOKIE_FIELDS for c in result)


@pytest.mark.parametrize("domain", ["x.com", ".x.com", "twitter.com", ".twitter.com"])
def test_normalizes_allowed_domain_aliases(domain):
    assert all(c["domain"] == ".x.com" for c in vault.normalize_x_cookies(cookies(domain=domain)))


def test_duplicate_identical_cookie_is_accepted_but_conflict_is_rejected():
    records = cookies()
    assert vault.normalize_x_cookies([*records, dict(records[0], domain="twitter.com")]) == records
    with pytest.raises(vault.SessionError):
        vault.normalize_x_cookies([*records, dict(records[0], value="GENERATED-other-account")])


def test_duplicate_conflicting_expiry_is_rejected():
    records = cookies()
    with pytest.raises(vault.SessionError):
        vault.normalize_x_cookies([*records, dict(records[0], expires=records[0]["expires"] + 1)])


@pytest.mark.parametrize("records", [[], [cookie()], [cookie("ct0", CSRF)], [None], "not-cookie-records", None])
def test_incomplete_or_malformed_cookie_collection_rejected(records):
    with pytest.raises(vault.SessionError):
        vault.normalize_x_cookies(records)


@pytest.mark.parametrize("value", ["", "GENERATED\r\nHeader:value", "GENERATED\x00value", "GENERATED\x7fvalue",
                                    "GENERATED value", "GENERATED;ct0=forged", 'GENERATED"value',
                                    "GENERATED,other", "GENERATED\\value", "GENERATED-ю", "x" * 16385,
                                    None, 77], ids=[f"unsafe-{i}" for i in range(13)])
def test_unsafe_cookie_values_rejected_without_echo(value):
    with pytest.raises(vault.SessionError) as caught:
        vault.normalize_x_cookies([cookie(value=value), cookie("ct0", CSRF)])
    assert str(caught.value) == vault._LOGIN_ERROR
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("secure", [False, None, 1, "true"])
def test_insecure_or_untyped_secure_cookie_rejected(secure):
    with pytest.raises(vault.SessionError):
        vault.normalize_x_cookies(cookies(secure=secure))


@pytest.mark.parametrize("expires", [float("nan"), float("inf"), "tomorrow", True, 253402300800,
                                      19999999999.75, -1, 1])
def test_invalid_or_expired_expiry_rejected(expires):
    with pytest.raises(vault.SessionError):
        vault.normalize_x_cookies(cookies(expires=expires))


@pytest.mark.parametrize("expires", [None, 0])
def test_session_cookies_qualify_without_persistent_expiry(expires):
    assert all(c["expires"] is None for c in vault.normalize_x_cookies(cookies(expires=expires)))


def test_cookie_iteration_is_bounded():
    def source():
        while True:
            yield cookie("irrelevant", "GENERATED")
    with pytest.raises(vault.SessionError):
        vault.normalize_x_cookies(source())


@pytest.mark.parametrize("agent", ["", "   ", "Synthetic\r\nAuthorization: value", "Synthetic\tAgent",
                                    "Synthetic\x00Agent", "Synthetic\x7fAgent", "Synthetic-ю", "x" * 2049,
                                    None, 72], ids=[f"unsafe-agent-{i}" for i in range(10)])
def test_invalid_user_agent_rejected_before_encryption(agent, monkeypatch):
    monkeypatch.setattr(vault, "_dpapi", lambda *a, **k: pytest.fail("invalid input reached encryption"))
    with pytest.raises(vault.SessionError) as caught:
        vault.save_x_session(cookies(), agent)
    assert str(caught.value) == vault._LOGIN_ERROR
    assert not vault.session_path().exists()


def test_missing_session_never_looks_in_browsers_or_contacts_network(monkeypatch):
    monkeypatch.setattr(requests.Session, "request", lambda *a, **k: pytest.fail("network access"))
    with pytest.raises(vault.SessionError) as caught:
        vault.load_x_session()
    assert str(caught.value) == vault._MISSING_ERROR
    assert not vault.has_x_session()


@pytest.mark.skipif(os.name != "nt", reason="Genuine current-user Windows DPAPI integration")
def test_genuine_dpapi_roundtrip_ciphertext_only_and_fresh_jar():
    vault.save_x_session(cookies(), UA)
    path = vault.session_path()
    ciphertext = path.read_bytes()
    assert ciphertext.startswith(vault._MAGIC)
    assert all(value.encode() not in ciphertext for value in (AUTH, CSRF, UA, '"cookies"'))
    assert not path.with_name(path.name + ".tmp").exists()
    jar, agent = vault.load_x_session()
    assert isinstance(jar, requests.cookies.RequestsCookieJar)
    assert agent == UA
    assert {(c.domain, c.path, c.name, c.value, c.secure) for c in jar} == {
        (".x.com", "/", "auth_token", AUTH, True), (".x.com", "/", "ct0", CSRF, True)}
    assert vault.has_x_session()
    jar.clear()
    assert len(vault.load_x_session()[0]) == 2
    assert path.read_bytes() == ciphertext


@pytest.mark.skipif(os.name != "nt", reason="Genuine current-user Windows DPAPI integration")
def test_only_selected_values_are_retained_after_encryption():
    vault.save_x_session([*cookies(), cookie("unrelated", "GENERATED-should-not-save"),
                          cookie(domain=".example.test", value="GENERATED-other-site")], UA)
    data = vault.session_path().read_bytes()[len(vault._MAGIC):]
    plaintext = vault._dpapi(data, protect=False)
    assert b"GENERATED-should-not-save" not in plaintext
    assert b"GENERATED-other-site" not in plaintext
    assert set(json.loads(plaintext)) == {"version", "cookies", "user_agent", "saved_at"}


@pytest.mark.skipif(os.name != "nt", reason="Genuine current-user Windows DPAPI integration")
def test_atomic_failure_preserves_previous_encrypted_vault(monkeypatch):
    vault.save_x_session(cookies(), UA)
    previous = vault.session_path().read_bytes()
    temporary_bytes = []

    def fail_replace(source, destination):
        assert Path(destination) == vault.session_path()
        temporary_bytes.append(Path(source).read_bytes())
        raise OSError("GENERATED-low-level-error-not-for-display")

    monkeypatch.setattr(vault.os, "replace", fail_replace)
    with pytest.raises(vault.SessionError) as caught:
        vault.save_x_session([cookie(value="GENERATED-replacement"), cookie("ct0", CSRF)], UA)
    assert str(caught.value) == vault._SAVE_ERROR
    assert vault.session_path().read_bytes() == previous
    assert not vault.session_path().with_name(vault.session_path().name + ".tmp").exists()
    assert temporary_bytes and all(AUTH.encode() not in data and b"GENERATED-replacement" not in data
                                   for data in temporary_bytes)
    assert vault.load_x_session()[0].get("auth_token", domain=".x.com", path="/") == AUTH


@pytest.mark.skipif(os.name != "nt", reason="Genuine current-user Windows DPAPI integration")
def test_failed_encryption_never_creates_vault_or_temporary(monkeypatch):
    def fail(*args, **kwargs):
        raise vault.SessionError(vault._SAVE_ERROR)
    monkeypatch.setattr(vault, "_dpapi", fail)
    with pytest.raises(vault.SessionError):
        vault.save_x_session(cookies(), UA)
    assert not vault.session_path().parent.exists()


@pytest.mark.skipif(os.name != "nt", reason="Genuine current-user Windows DPAPI integration")
def test_stale_own_ciphertext_temporary_is_replaced_safely():
    path = vault.session_path()
    path.parent.mkdir(parents=True)
    path.with_name(path.name + ".tmp").write_bytes(b"GENERATED-encrypted-crash-remnant")
    vault.save_x_session(cookies(), UA)
    assert vault.has_x_session()
    assert not path.with_name(path.name + ".tmp").exists()


@pytest.mark.skipif(os.name != "nt", reason="Genuine current-user Windows DPAPI integration")
def test_tampering_cannot_load_or_fallback():
    vault.save_x_session(cookies(), UA)
    path = vault.session_path()
    data = bytearray(path.read_bytes())
    data[-9] ^= 0x80
    path.write_bytes(data)
    with pytest.raises(vault.SessionError) as caught:
        vault.load_x_session()
    assert str(caught.value) == vault._INVALID_ERROR
    assert not vault.has_x_session()


def test_wrong_user_dpapi_failure_is_fixed_error(monkeypatch):
    path = vault.session_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(vault._MAGIC + b"GENERATED-unreadable-DPAPI-blob")

    def wrong_user(*args, **kwargs):
        raise vault.SessionError("GENERATED-internal-DPAPI-error")

    monkeypatch.setattr(vault, "_dpapi", wrong_user)
    with pytest.raises(vault.SessionError) as caught:
        vault.load_x_session()
    assert str(caught.value) == vault._INVALID_ERROR
    assert not vault.has_x_session()


@pytest.mark.parametrize("data", [b"", b"not-a-Mira-vault", vault._MAGIC, b"x" * (128 * 1024 + 1)],
                         ids=["empty", "wrong-format", "empty-payload", "oversize"])
def test_corrupt_or_oversize_vault_fails_safely(data):
    path = vault.session_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    with pytest.raises(vault.SessionError) as caught:
        vault.load_x_session()
    assert str(caught.value) == vault._INVALID_ERROR
    assert not vault.has_x_session()


@pytest.mark.skipif(os.name != "nt", reason="Genuine current-user Windows DPAPI integration")
def test_expired_vault_prompts_login_without_deleting_it(monkeypatch):
    expiry = int(time.time()) + 3600
    vault.save_x_session(cookies(expires=expiry), UA)
    previous = vault.session_path().read_bytes()
    monkeypatch.setattr(vault.time, "time", lambda: expiry + 1)
    with pytest.raises(vault.SessionError) as caught:
        vault.load_x_session()
    assert str(caught.value) == vault._INVALID_ERROR
    assert not vault.has_x_session()
    assert vault.session_path().read_bytes() == previous


@pytest.mark.skipif(os.name != "nt", reason="Genuine current-user Windows DPAPI integration")
@pytest.mark.parametrize("mutation", ["unknown_outer", "unknown_cookie", "unknown_version", "version_bool",
                                      "saved_future", "saved_bool", "saved_zero", "bad_agent", "extra_cookie",
                                      "unrelated_cookie", "missing_secure", "wrong_domain"])
def test_decrypted_payload_schema_is_strict(mutation):
    payload = valid_payload()
    if mutation == "unknown_outer":
        payload["other"] = "GENERATED-not-allowed"
    elif mutation == "unknown_cookie":
        payload["cookies"][0]["password"] = "GENERATED-not-allowed"
    elif mutation == "unknown_version":
        payload["version"] = 2
    elif mutation == "version_bool":
        payload["version"] = True
    elif mutation == "saved_future":
        payload["saved_at"] += 3600
    elif mutation == "saved_bool":
        payload["saved_at"] = True
    elif mutation == "saved_zero":
        payload["saved_at"] = 0
    elif mutation == "bad_agent":
        payload["user_agent"] = "GENERATED\r\nHeader:value"
    elif mutation == "extra_cookie":
        payload["cookies"].append(dict(payload["cookies"][0]))
    elif mutation == "unrelated_cookie":
        payload["cookies"][0]["name"] = "unrelated"
    elif mutation == "missing_secure":
        del payload["cookies"][0]["secure"]
    elif mutation == "wrong_domain":
        payload["cookies"][0]["domain"] = "twitter.com"
    write_payload(payload)
    with pytest.raises(vault.SessionError) as caught:
        vault.load_x_session()
    assert str(caught.value) == vault._INVALID_ERROR


@pytest.mark.skipif(os.name != "nt", reason="Genuine current-user Windows DPAPI integration")
def test_duplicate_json_keys_rejected():
    payload = json.dumps(valid_payload()).replace('"version": 1', '"version": 1, "version": 1').encode()
    path = vault.session_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(vault._MAGIC + vault._dpapi(payload, protect=True))
    assert not vault.has_x_session()


def test_clear_deletes_only_owned_exact_files_and_is_idempotent():
    path = vault.session_path()
    path.parent.mkdir(parents=True)
    temporary = path.with_name(path.name + ".tmp")
    unrelated = path.parent / "library.sqlite"
    browser = path.parent / "browser-cookies.sqlite"
    own_similar = path.parent / "x-session.dpapi.other"
    for item in (path, temporary, unrelated, browser, own_similar):
        item.write_bytes(b"GENERATED-existing-file")
    vault.clear_x_session()
    vault.clear_x_session()
    assert not path.exists() and not temporary.exists()
    assert all(item.read_bytes() == b"GENERATED-existing-file" for item in (unrelated, browser, own_similar))
    assert not vault.has_x_session()


def test_clear_permission_error_is_sanitized(monkeypatch):
    original = Path.unlink
    def denied(path, *args, **kwargs):
        if path == vault.session_path():
            raise OSError("GENERATED-private-location-error")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", denied)
    with pytest.raises(vault.SessionError) as caught:
        vault.clear_x_session()
    assert str(caught.value) == vault._CLEAR_ERROR
